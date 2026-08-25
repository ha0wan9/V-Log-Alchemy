#!/usr/bin/env python3
"""Generate DJI -> Panasonic V-Log / V-Gamut conversion LUTs.

The output LUTs take DJI D-Log (or D-Log M) footage and re-encode it as
V-Log / V-Gamut, so every V-Log LUT in this repository can be applied to
DJI cameras.

Pipeline:

    DJI D-Log(-M) / D-Gamut
      -> linear D-Gamut          (D-Log math, or a fitted D-Log M curve)
      -> XYZ D65
      -> linear V-Gamut          (both spaces are D65, no adaptation needed)
      -> V-Log

D-Log's transfer function is published by DJI, so `--source dlog` is exact.
D-Log M's transfer function is not published; `--source dlogm` needs a curve
fitted from DJI's own official LUTs first, see `fit-dlogm`.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = REPO_DIR / "Luts" / "DJI"
DLOGM_CURVE = SCRIPT_DIR / "dji_dlogm_to_linear.json"

D65 = (0.3127, 0.3290)
# DJI D-Gamut primaries (DJI D-Log / D-Gamut white paper), D65 white.
D_GAMUT_PRIMARIES = (0.710, 0.290, 0.210, 0.880, 0.090, -0.080)
# Panasonic V-Gamut primaries (V-Log/V-Gamut reference manual), D65 white.
V_GAMUT_PRIMARIES = (0.730, 0.280, 0.165, 0.840, 0.100, -0.030)


# --------------------------------------------------------------------------
# small matrix helpers (same conventions as generate_hasselblad_vlog.py)
# --------------------------------------------------------------------------
def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def mat_inv_3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-15:
        raise ValueError("singular matrix")
    return [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]


def xy_to_xyz(x, y):
    return [x / y, 1.0, (1.0 - x - y) / y]


def rgb_to_xyz_matrix(primaries, white_xy):
    xr, yr, xg, yg, xb, yb = primaries
    r = xy_to_xyz(xr, yr)
    g = xy_to_xyz(xg, yg)
    b = xy_to_xyz(xb, yb)
    p = [
        [r[0], g[0], b[0]],
        [r[1], g[1], b[1]],
        [r[2], g[2], b[2]],
    ]
    w = xy_to_xyz(*white_xy)
    s = mat_vec(mat_inv_3(p), w)
    return [[p[row][col] * s[col] for col in range(3)] for row in range(3)]


def build_dgamut_to_vgamut_matrix():
    d_gamut_to_xyz = rgb_to_xyz_matrix(D_GAMUT_PRIMARIES, D65)
    v_gamut_to_xyz = rgb_to_xyz_matrix(V_GAMUT_PRIMARIES, D65)
    return mat_mul(mat_inv_3(v_gamut_to_xyz), d_gamut_to_xyz)


# --------------------------------------------------------------------------
# transfer functions
# --------------------------------------------------------------------------
def dlog_to_linear(v):
    # DJI D-Log white paper.
    if v <= 0.14:
        return (v - 0.0929) / 6.025
    return (math.pow(10.0, (v - 0.584555) / 0.256663) - 0.0108) / 0.9892


def linear_to_dlog(x):
    if x <= 0.0078:
        return 6.025 * x + 0.0929
    return math.log10(x * 0.9892 + 0.0108) * 0.256663 + 0.584555


def linear_to_vlog(x):
    # Panasonic V-Log reference manual constants.
    if x < 0.01:
        return 5.6 * x + 0.125
    return 0.241514 * math.log10(x + 0.00873) + 0.598206


def vlog_to_linear(v):
    if v < 0.181:
        return (v - 0.125) / 5.6
    return math.pow(10.0, (v - 0.598206) / 0.241514) - 0.00873


class SampledCurve:
    """Monotone 1D curve sampled on [0, 1], linearly interpolated."""

    def __init__(self, samples):
        if len(samples) < 2:
            raise ValueError("curve needs at least 2 samples")
        self.samples = list(samples)

    def __call__(self, x):
        n = len(self.samples) - 1
        if x <= 0.0:
            # extrapolate with the first segment so negatives stay meaningful
            slope = (self.samples[1] - self.samples[0]) * n
            return self.samples[0] + slope * x
        if x >= 1.0:
            slope = (self.samples[-1] - self.samples[-2]) * n
            return self.samples[-1] + slope * (x - 1.0)
        pos = x * n
        i = int(pos)
        frac = pos - i
        return self.samples[i] * (1.0 - frac) + self.samples[i + 1] * frac


def load_dlogm_curve(path):
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"missing D-Log M curve: {path}\n"
            "D-Log M's transfer function is not published by DJI. Fit it first:\n"
            "  python Tools/generate_dji_vlog.py fit-dlogm \\\n"
            "      --dlogm-lut <DJI D-Log M to Rec.709 .cube> \\\n"
            "      --dlog-lut  <DJI D-Log to Rec.709 .cube>"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return SampledCurve(data["linear_samples"])


# --------------------------------------------------------------------------
# .cube reading / writing
# --------------------------------------------------------------------------
def read_cube(path):
    size = None
    domain_min = [0.0, 0.0, 0.0]
    domain_max = [1.0, 1.0, 1.0]
    entries = []
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        key = parts[0].upper()
        if key == "LUT_3D_SIZE":
            size = int(parts[1])
        elif key == "DOMAIN_MIN":
            domain_min = [float(v) for v in parts[1:4]]
        elif key == "DOMAIN_MAX":
            domain_max = [float(v) for v in parts[1:4]]
        elif key in ("TITLE", "LUT_1D_SIZE"):
            if key == "LUT_1D_SIZE":
                raise SystemExit(f"{path}: 1D LUTs are not supported")
        else:
            try:
                entries.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except (ValueError, IndexError):
                continue
    if size is None:
        raise SystemExit(f"{path}: no LUT_3D_SIZE found")
    if len(entries) != size ** 3:
        raise SystemExit(f"{path}: expected {size ** 3} entries, got {len(entries)}")
    return size, domain_min, domain_max, entries


def cube_neutral_response(path):
    """Sample a 3D LUT along its neutral (r == g == b) diagonal."""
    size, domain_min, domain_max, entries = read_cube(path)
    inputs = []
    outputs = []
    for i in range(size):
        # .cube data order: red varies fastest.
        index = i * (1 + size + size * size)
        inputs.append(domain_min[1] + (domain_max[1] - domain_min[1]) * i / (size - 1))
        outputs.append(entries[index][1])
    return inputs, outputs


def clamp01(x):
    return max(0.0, min(1.0, x))


def write_cube(path, title, size, transform):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {size}\n\n")
        denom = size - 1
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    out = transform([r / denom, g / denom, b / denom])
                    f.write(f"{clamp01(out[0]):.9g} {clamp01(out[1]):.9g} {clamp01(out[2]):.9g}\n")


# --------------------------------------------------------------------------
# D-Log M curve fitting
# --------------------------------------------------------------------------
def invert_monotone(xs, ys, y):
    """Invert a monotonically increasing sampled response."""
    if y <= ys[0]:
        if ys[1] == ys[0]:
            return xs[0]
        slope = (xs[1] - xs[0]) / (ys[1] - ys[0])
        return xs[0] + slope * (y - ys[0])
    if y >= ys[-1]:
        if ys[-1] == ys[-2]:
            return xs[-1]
        slope = (xs[-1] - xs[-2]) / (ys[-1] - ys[-2])
        return xs[-1] + slope * (y - ys[-1])
    for i in range(len(ys) - 1):
        if ys[i] <= y <= ys[i + 1]:
            span = ys[i + 1] - ys[i]
            if span <= 0.0:
                return xs[i]
            frac = (y - ys[i]) / span
            return xs[i] + (xs[i + 1] - xs[i]) * frac
    return xs[-1]


def enforce_monotone(values):
    out = []
    running = None
    for v in values:
        if running is not None and v < running:
            v = running
        running = v
        out.append(v)
    return out


def pchip_slopes(xs, ys):
    """Fritsch-Carlson monotone cubic slopes (keeps the fit from overshooting)."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0] = delta[0]
    m[-1] = delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0.0:
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    return m


def pchip_eval(xs, ys, m, x):
    if x <= xs[0]:
        return ys[0] + m[0] * (x - xs[0])
    if x >= xs[-1]:
        return ys[-1] + m[-1] * (x - xs[-1])
    i = 0
    while i < len(xs) - 2 and x > xs[i + 1]:
        i += 1
    h = xs[i + 1] - xs[i]
    s = (x - xs[i]) / h
    s2 = s * s
    s3 = s2 * s
    return (
        (2 * s3 - 3 * s2 + 1) * ys[i]
        + (s3 - 2 * s2 + s) * h * m[i]
        + (-2 * s3 + 3 * s2) * ys[i + 1]
        + (s3 - s2) * h * m[i + 1]
    )


LOG_FLOOR = 0.002


def densify(node_codes, node_linear, count):
    """Resample recovered nodes onto `count` samples.

    A log encoding is only smooth in log space, so interpolate log2(linear)
    above LOG_FLOOR and stay linear through the toe, where values reach zero
    and go slightly negative.
    """
    log_x, log_y, lin_x, lin_y = [], [], [], []
    for c, v in zip(node_codes, node_linear):
        if v >= LOG_FLOOR:
            log_x.append(c)
            log_y.append(math.log(v, 2.0))
        else:
            lin_x.append(c)
            lin_y.append(v)
    if len(log_x) < 2:
        raise SystemExit("not enough usable samples above the toe")
    # carry the first log node into the toe fit so the two halves meet
    lin_x.append(log_x[0])
    lin_y.append(node_linear[node_codes.index(log_x[0])])
    log_m = pchip_slopes(log_x, log_y)
    lin_m = pchip_slopes(lin_x, lin_y)
    split = log_x[0]

    out = []
    for i in range(count):
        c = i / (count - 1)
        if c >= split:
            out.append(math.pow(2.0, pchip_eval(log_x, log_y, log_m, c)))
        else:
            out.append(pchip_eval(lin_x, lin_y, lin_m, c))
    return out


def source_id(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"name": path.name, "sha256": digest}


def fit_dlogm(args):
    """Recover D-Log M -> linear from DJI's own official display LUTs.

    Both official LUTs render the same Rec.709 look, so on the neutral axis

        dlogm_to_709(x) == dlog_to_709(f(x))

    which gives f = dlog_to_709^-1 . dlogm_to_709, i.e. D-Log M -> D-Log.
    D-Log's transfer function is published, so that yields D-Log M -> linear.

    The inversion is only solved at the D-Log M LUT's own nodes: the reference
    LUT's Rec.709 shoulder is nearly flat, so inverting it on a finer grid
    invents precision that is not in the data. The nodes are then densified
    with a monotone fit in log space.
    """
    m_in, m_out = cube_neutral_response(args.dlogm_lut)
    d_in, d_out = cube_neutral_response(args.dlog_lut)
    d_in = enforce_monotone(d_in)
    d_out = enforce_monotone(d_out)

    node_codes = list(m_in)
    node_linear = []
    weakest = None
    for value in enforce_monotone(m_out):
        code = invert_monotone(d_in, d_out, value)
        node_linear.append(dlog_to_linear(code))
        # local slope of the reference LUT at the point we inverted through
        for k in range(len(d_out) - 1):
            if d_in[k] <= code <= d_in[k + 1]:
                slope = (d_out[k + 1] - d_out[k]) / (d_in[k + 1] - d_in[k])
                weakest = slope if weakest is None else min(weakest, slope)
                break
    node_linear = enforce_monotone(node_linear)
    samples = enforce_monotone(densify(node_codes, node_linear, args.samples))

    payload = {
        "description": "DJI D-Log M -> scene linear, fitted from DJI official Rec.709 LUTs",
        "dlogm_lut": source_id(args.dlogm_lut),
        "dlog_lut": source_id(args.dlog_lut),
        "nodes": len(node_codes),
        "node_codes": node_codes,
        "node_linear": node_linear,
        "linear_samples": samples,
    }
    out_path = Path(args.output or DLOGM_CURVE)
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    curve = SampledCurve(samples)
    grey = invert_monotone(node_codes, node_linear, 0.18)
    print(out_path)
    print(f"  {len(node_codes)} nodes -> {len(samples)} samples")
    print(f"  18% grey at D-Log M {grey * 100:.2f}%")
    print(f"  clip at D-Log M 1.0 -> linear {node_linear[-1]:.4f} "
          f"({math.log(node_linear[-1] / 0.18, 2.0):+.2f} stops over grey)")
    if weakest is not None and weakest < 0.05:
        print(f"  note: reference LUT slope falls to {weakest:.4f}/code in the highlights; "
              "the top of the curve is the least certain part of the fit")
    for code in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        print(f"  D-Log M {code:.2f} -> linear {curve(code):.5f}")


# --------------------------------------------------------------------------
# 3D LUT sampling (for baking a style LUT into the conversion)
# --------------------------------------------------------------------------
class Lut3D:
    """A .cube 3D LUT sampled with tetrahedral interpolation."""

    def __init__(self, path):
        self.size, self.domain_min, self.domain_max, entries = read_cube(path)
        self.data = entries
        self.name = Path(path).name

    def _node(self, r, g, b):
        n = self.size
        return self.data[r + n * g + n * n * b]

    def __call__(self, rgb):
        n = self.size
        last = n - 1
        pos = []
        for i in range(3):
            span = self.domain_max[i] - self.domain_min[i]
            x = (rgb[i] - self.domain_min[i]) / span if span else 0.0
            pos.append(min(max(x, 0.0), 1.0) * last)
        base = [min(int(p), last - 1) for p in pos]
        fx, fy, fz = (pos[i] - base[i] for i in range(3))
        r0, g0, b0 = base

        c000 = self._node(r0, g0, b0)
        c111 = self._node(r0 + 1, g0 + 1, b0 + 1)
        # tetrahedral: pick the tetrahedron from the ordering of the fractions
        if fx > fy:
            if fy > fz:
                p1, p2 = self._node(r0 + 1, g0, b0), self._node(r0 + 1, g0 + 1, b0)
                w0, w1, w2, w3 = 1 - fx, fx - fy, fy - fz, fz
            elif fx > fz:
                p1, p2 = self._node(r0 + 1, g0, b0), self._node(r0 + 1, g0, b0 + 1)
                w0, w1, w2, w3 = 1 - fx, fx - fz, fz - fy, fy
            else:
                p1, p2 = self._node(r0, g0, b0 + 1), self._node(r0 + 1, g0, b0 + 1)
                w0, w1, w2, w3 = 1 - fz, fz - fx, fx - fy, fy
        else:
            if fz > fy:
                p1, p2 = self._node(r0, g0, b0 + 1), self._node(r0, g0 + 1, b0 + 1)
                w0, w1, w2, w3 = 1 - fz, fz - fy, fy - fx, fx
            elif fz > fx:
                p1, p2 = self._node(r0, g0 + 1, b0), self._node(r0, g0 + 1, b0 + 1)
                w0, w1, w2, w3 = 1 - fy, fy - fz, fz - fx, fx
            else:
                p1, p2 = self._node(r0, g0 + 1, b0), self._node(r0 + 1, g0 + 1, b0)
                w0, w1, w2, w3 = 1 - fy, fy - fx, fx - fz, fz
        return [
            w0 * c000[i] + w1 * p1[i] + w2 * p2[i] + w3 * c111[i]
            for i in range(3)
        ]


# --------------------------------------------------------------------------
# LUT generation
# --------------------------------------------------------------------------
def generate(args):
    matrix = build_dgamut_to_vgamut_matrix()
    if args.source == "dlog":
        to_linear = dlog_to_linear
        label = "D-Log"
        slug = "DLog"
    else:
        to_linear = load_dlogm_curve(args.curve or DLOGM_CURVE)
        label = "D-Log M"
        slug = "DLogM"

    look = Lut3D(args.look) if args.look else None
    if look is not None:
        look_slug = args.look_name
        if not look_slug:
            look_slug = Path(args.look).stem
            for strip in ("_VLog", "-VLog"):
                if look_slug.endswith(strip):
                    look_slug = look_slug[: -len(strip)]
        title = f"DJI {label} to {look_slug.replace(chr(95), chr(32))} (via V-Log)"
        stem = f"DJI_{slug}_to_{look_slug}"
    else:
        title = f"DJI {label} / D-Gamut to Panasonic V-Log / V-Gamut"
        stem = f"DJI_{slug}_to_VLog"

    def transform(src_rgb):
        lin = [to_linear(c) * args.exposure_scale for c in src_rgb]
        v_lin = mat_vec(matrix, lin)
        vlog = [linear_to_vlog(c) for c in v_lin]
        if look is None:
            return vlog
        # the style LUTs are defined on [0, 1] V-Log, so clamp before sampling
        return look([clamp01(c) for c in vlog])

    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    for size in sizes:
        suffix = "" if size == 33 else f"_{size}"
        if args.output and len(sizes) == 1:
            out_path = Path(args.output)
        else:
            out_path = Path(args.output_dir) / f"{stem}{suffix}.cube"
        write_cube(out_path, title, size, transform)
        print(out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="write DJI -> V-Log .cube files (default)")
    gen.add_argument("--source", choices=("dlog", "dlogm"), default="dlog")
    gen.add_argument("--curve", default="", help="fitted D-Log M curve JSON (for --source dlogm)")
    gen.add_argument("--look", default="", help="bake a V-Log style .cube into the output")
    gen.add_argument("--look-name", default="", help="name to use for the baked look in the filename/title")
    gen.add_argument("--sizes", default="33,65")
    gen.add_argument("--exposure-scale", type=float, default=1.0)
    gen.add_argument("--output", default="")
    gen.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    gen.set_defaults(func=generate)

    fit = sub.add_parser("fit-dlogm", help="fit the D-Log M transfer curve from DJI's official LUTs")
    fit.add_argument("--dlogm-lut", required=True, help="DJI official 'D-Log M to Rec.709' .cube")
    fit.add_argument("--dlog-lut", required=True, help="DJI official 'D-Log to Rec.709' .cube")
    fit.add_argument("--samples", type=int, default=4096)
    fit.add_argument("--output", default="")
    fit.set_defaults(func=fit_dlogm)

    mtx = sub.add_parser("matrix", help="print the D-Gamut -> V-Gamut matrix")
    mtx.set_defaults(func=lambda a: print(json.dumps(build_dgamut_to_vgamut_matrix(), indent=2)))

    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["generate"])
    args.func(args)


if __name__ == "__main__":
    main()
