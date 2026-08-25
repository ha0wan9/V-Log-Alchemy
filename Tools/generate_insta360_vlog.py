#!/usr/bin/env python3
"""Generate Insta360 I-Log -> Panasonic V-Log / V-Gamut conversion LUTs.

The output LUTs take Insta360 I-Log footage and re-encode it as V-Log /
V-Gamut, so every V-Log LUT in this repository can be applied to Insta360
cameras (Luna Ultra, Ace Pro 2, X5, GO Ultra, ...).

Unlike the DJI D-Log M path, nothing here is reverse engineered. Insta360
publishes the I-Log math itself, in the official ACES IDT shipped with
"Insta360 I-Log & ACES Workflow" (Insta360_I-Log_Rec2020_ACES_IDT_v2.dctl):

    I-Log -> linear
        x <  0.154402   ->  (x - beta) / alpha
        x >= 0.154402   ->  10^((x - delta) / eta) - theta

    gamut: Rec.2020, D65

Pipeline:

    I-Log / Rec.2020
      -> linear Rec.2020
      -> XYZ D65
      -> linear V-Gamut       (both spaces are D65, no adaptation needed)
      -> V-Log

The vendor IDT targets ACES AP0 and therefore carries a CAT02 adaptation from
D65 to the ACES white point. That step is deliberately skipped here: V-Gamut is
D65 too, so going through AP0 would adapt away from D65 and straight back,
which only costs precision. `verify` checks this implementation against the
vendor matrix by rebuilding their published Rec.2020 -> AP0 coefficients.
"""
import argparse
import json
import math
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = REPO_DIR / "Luts" / "Insta360"

D65 = (0.3127, 0.3290)
ACES_WHITE = (0.32168, 0.33767)
# ITU-R BT.2020 primaries, D65 white.
REC2020_PRIMARIES = (0.708, 0.292, 0.170, 0.797, 0.131, 0.046)
# Panasonic V-Gamut primaries (V-Log/V-Gamut reference manual), D65 white.
V_GAMUT_PRIMARIES = (0.730, 0.280, 0.165, 0.840, 0.100, -0.030)
# ACES AP0 primaries.
AP0_PRIMARIES = (0.7347, 0.2653, 0.0, 1.0, 0.0001, -0.0770)

CAT02 = [
    [0.7328, 0.4296, -0.1624],
    [-0.7036, 1.6975, 0.0061],
    [0.0030, 0.0136, 0.9834],
]

# Insta360 I-Log constants, verbatim from the official ACES IDT v2.
ILOG_ALPHA = 5.77837328
ILOG_BETA = 0.09055934
ILOG_DELTA = 0.623992
ILOG_THETA = 0.01
ILOG_ETA = 0.280055
ILOG_CUT_LOG = 0.154402
ILOG_CUT_LIN = 0.01104854

# Insta360's published Rec.2020 -> AP0 (CAT02) matrix, used by `verify`.
VENDOR_REC2020_TO_AP0 = [
    [0.6788911506, 0.1588684224, 0.1622404270],
    [0.0455708309, 0.8607127720, 0.0937163971],
    [-0.0004857104, 0.0250601957, 0.9754255146],
]


# --------------------------------------------------------------------------
# small matrix helpers
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


def chromatic_adaptation(src_white_xy, dst_white_xy, cone_matrix):
    inv = mat_inv_3(cone_matrix)
    src = mat_vec(cone_matrix, xy_to_xyz(*src_white_xy))
    dst = mat_vec(cone_matrix, xy_to_xyz(*dst_white_xy))
    scale = [
        [dst[0] / src[0], 0.0, 0.0],
        [0.0, dst[1] / src[1], 0.0],
        [0.0, 0.0, dst[2] / src[2]],
    ]
    return mat_mul(mat_mul(inv, scale), cone_matrix)


def build_rec2020_to_vgamut_matrix():
    rec2020_to_xyz = rgb_to_xyz_matrix(REC2020_PRIMARIES, D65)
    v_gamut_to_xyz = rgb_to_xyz_matrix(V_GAMUT_PRIMARIES, D65)
    return mat_mul(mat_inv_3(v_gamut_to_xyz), rec2020_to_xyz)


def build_rec2020_to_ap0_matrix():
    """Rebuild the vendor IDT's matrix, to check this implementation."""
    return mat_mul(
        mat_inv_3(rgb_to_xyz_matrix(AP0_PRIMARIES, ACES_WHITE)),
        mat_mul(
            chromatic_adaptation(D65, ACES_WHITE, CAT02),
            rgb_to_xyz_matrix(REC2020_PRIMARIES, D65),
        ),
    )


# --------------------------------------------------------------------------
# transfer functions
# --------------------------------------------------------------------------
def ilog_to_linear(v):
    if v < ILOG_CUT_LOG:
        return (v - ILOG_BETA) / ILOG_ALPHA
    return math.pow(10.0, (v - ILOG_DELTA) / ILOG_ETA) - ILOG_THETA


def linear_to_ilog(x):
    if x <= ILOG_CUT_LIN:
        return ILOG_ALPHA * x + ILOG_BETA
    return ILOG_DELTA + ILOG_ETA * math.log10(x + ILOG_THETA)


def linear_to_vlog(x):
    # Panasonic V-Log reference manual constants.
    if x < 0.01:
        return 5.6 * x + 0.125
    return 0.241514 * math.log10(x + 0.00873) + 0.598206


def vlog_to_linear(v):
    if v < 0.181:
        return (v - 0.125) / 5.6
    return math.pow(10.0, (v - 0.598206) / 0.241514) - 0.00873


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
        elif key == "LUT_1D_SIZE":
            raise SystemExit(f"{path}: 1D LUTs are not supported")
        elif key != "TITLE":
            try:
                entries.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except (ValueError, IndexError):
                continue
    if size is None:
        raise SystemExit(f"{path}: no LUT_3D_SIZE found")
    if len(entries) != size ** 3:
        raise SystemExit(f"{path}: expected {size ** 3} entries, got {len(entries)}")
    return size, domain_min, domain_max, entries


class Lut3D:
    """A .cube 3D LUT sampled with tetrahedral interpolation."""

    def __init__(self, path):
        self.size, self.domain_min, self.domain_max, self.data = read_cube(path)
        self.name = Path(path).name

    def _node(self, r, g, b):
        n = self.size
        return self.data[r + n * g + n * n * b]

    def __call__(self, rgb):
        last = self.size - 1
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
        return [w0 * c000[i] + w1 * p1[i] + w2 * p2[i] + w3 * c111[i] for i in range(3)]


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
# commands
# --------------------------------------------------------------------------
def generate(args):
    matrix = build_rec2020_to_vgamut_matrix()
    look = Lut3D(args.look) if args.look else None
    if look is not None:
        slug = args.look_name or Path(args.look).stem
        for strip in ("_VLog", "-VLog"):
            if not args.look_name and slug.endswith(strip):
                slug = slug[: -len(strip)]
        title = f"Insta360 I-Log to {slug.replace('_', ' ')} (via V-Log)"
        stem = f"Insta360_ILog_to_{slug}"
    else:
        title = "Insta360 I-Log / Rec.2020 to Panasonic V-Log / V-Gamut"
        stem = "Insta360_ILog_to_VLog"

    def transform(src_rgb):
        lin = [ilog_to_linear(c) * args.exposure_scale for c in src_rgb]
        vlog = [linear_to_vlog(c) for c in mat_vec(matrix, lin)]
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


def verify(args):
    """Check this implementation against the numbers Insta360 published."""
    ok = True

    mine = build_rec2020_to_ap0_matrix()
    worst = max(
        abs(mine[i][j] - VENDOR_REC2020_TO_AP0[i][j]) for i in range(3) for j in range(3)
    )
    print(f"Rec.2020 -> AP0 (CAT02) vs vendor IDT : max delta {worst:.2e}")
    ok &= worst < 1e-6

    # the curve's two branches must agree at the documented breakpoint
    below = (ILOG_CUT_LOG - ILOG_BETA) / ILOG_ALPHA
    above = math.pow(10.0, (ILOG_CUT_LOG - ILOG_DELTA) / ILOG_ETA) - ILOG_THETA
    print(f"curve continuity at {ILOG_CUT_LOG}          : {abs(below - above):.2e}")
    print(f"vendor linear breakpoint               : {abs(below - ILOG_CUT_LIN):.2e}")
    ok &= abs(below - above) < 1e-8

    trip = max(
        abs(ilog_to_linear(linear_to_ilog(x)) - x) for x in (i / 2000 for i in range(1, 2000))
    )
    print(f"I-Log round trip                       : {trip:.2e}")
    ok &= trip < 1e-9

    grey_in = linear_to_ilog(0.18)
    grey_out = linear_to_vlog(0.18)
    print(f"18% grey  I-Log {grey_in:.5f} -> V-Log {grey_out:.5f} (V-Log native {grey_out:.5f})")
    top = ilog_to_linear(1.0)
    print(f"I-Log 1.0 -> linear {top:.4f} (+{math.log(top / 0.18, 2.0):.2f} stops) "
          f"-> V-Log {linear_to_vlog(top):.5f}")
    ok &= linear_to_vlog(top) < 1.0

    print("\n" + ("PASS" if ok else "FAIL"))
    if not ok:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="write Insta360 -> V-Log .cube files (default)")
    gen.add_argument("--look", default="", help="bake a V-Log style .cube into the output")
    gen.add_argument("--look-name", default="", help="name for the baked look in the filename")
    gen.add_argument("--sizes", default="33,65")
    gen.add_argument("--exposure-scale", type=float, default=1.0)
    gen.add_argument("--output", default="")
    gen.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    gen.set_defaults(func=generate)

    ver = sub.add_parser("verify", help="check the math against Insta360's published IDT")
    ver.set_defaults(func=verify)

    mtx = sub.add_parser("matrix", help="print the Rec.2020 -> V-Gamut matrix")
    mtx.set_defaults(func=lambda a: print(json.dumps(build_rec2020_to_vgamut_matrix(), indent=2)))

    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["generate"])
    args.func(args)


if __name__ == "__main__":
    main()
