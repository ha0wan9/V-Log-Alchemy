#!/usr/bin/env python3
"""Bake a V-Log style LUT into a Rec.709-input LUT.

Every look in this repository expects scene-referred V-Log. Footage from a
camera that only shoots a "Normal" / "Standard" profile (DJI Neo 2, phones,
most action cams in their non-log mode) is already display-referred Rec.709,
and feeding it straight into a V-Log look does not work:

    Rec.709 white (1.0) -> linear 1.0 -> V-Log 0.599 -> Leica Classic 0.769

The look never sees white. Rec.709 only carries 2.47 stops above 18% grey,
while the Leica Classic look needs about 7.3 stops to reach its own white
point, so everything above grey lands in a narrow, washed-out band.

This tool inserts an inverse tone mapping step that expands the highlights back
out into scene-referred space before the look is applied:

    Rec.709 -> display linear -> [highlight expansion] -> V-Gamut -> V-Log -> look

Grey is an anchor: 18% stays at 18%, and the expansion has unit slope there, so
the shadows and mid-tones pass through the plain inverse EOTF untouched. Only
the region above grey is stretched, by `--highlight-stops`.

This is an approximation, not a recovery. The camera's own display rendering is
not invertible from the outside (see Luts/DJI/README.md for a worked proof on
DJI's Rec.709 LUTs), so the expansion is a plausible shape, not the real one.
Shooting log remains strictly better when the camera offers it.
"""
import argparse
import math
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = REPO_DIR / "Luts" / "Rec709-Input"

D65 = (0.3127, 0.3290)
REC709_PRIMARIES = (0.640, 0.330, 0.300, 0.600, 0.150, 0.060)
V_GAMUT_PRIMARIES = (0.730, 0.280, 0.165, 0.840, 0.100, -0.030)

GREY = 0.18
# stops from 18% grey to Rec.709 white in a display-linear signal
REC709_HEADROOM = math.log(1.0 / GREY, 2.0)


# --------------------------------------------------------------------------
# matrix helpers
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
    r, g, b = xy_to_xyz(xr, yr), xy_to_xyz(xg, yg), xy_to_xyz(xb, yb)
    p = [[r[0], g[0], b[0]], [r[1], g[1], b[1]], [r[2], g[2], b[2]]]
    s = mat_vec(mat_inv_3(p), xy_to_xyz(*white_xy))
    return [[p[row][col] * s[col] for col in range(3)] for row in range(3)]


def build_rec709_to_vgamut_matrix():
    # both spaces are D65, so no chromatic adaptation
    return mat_mul(
        mat_inv_3(rgb_to_xyz_matrix(V_GAMUT_PRIMARIES, D65)),
        rgb_to_xyz_matrix(REC709_PRIMARIES, D65),
    )


# --------------------------------------------------------------------------
# transfer functions
# --------------------------------------------------------------------------
def linear_to_vlog(x):
    if x < 0.01:
        return 5.6 * x + 0.125
    return 0.241514 * math.log10(x + 0.00873) + 0.598206


def expand_highlights(code, gamma, stops, power):
    """Rec.709 code value -> approximate scene-referred linear.

    Below grey this is just the inverse EOTF. Above grey the log-space distance
    from grey is stretched from REC709_HEADROOM stops to `stops`, with a shape
    that has unit slope at grey so the two halves join smoothly.
    """
    display = math.pow(max(code, 0.0), gamma)
    if display <= GREY or stops <= REC709_HEADROOM:
        return display
    t = math.log(display / GREY, 2.0)
    stretched = t + (stops - REC709_HEADROOM) * math.pow(t / REC709_HEADROOM, power)
    return GREY * math.pow(2.0, stretched)


# --------------------------------------------------------------------------
# .cube io
# --------------------------------------------------------------------------
def read_cube(path):
    size = None
    domain_min, domain_max = [0.0] * 3, [1.0] * 3
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
def build(args):
    matrix = build_rec709_to_vgamut_matrix()
    look = Lut3D(args.look)

    def transform(rgb):
        scene = [expand_highlights(c, args.gamma, args.highlight_stops, args.power) for c in rgb]
        vlog = [linear_to_vlog(c) for c in mat_vec(matrix, scene)]
        return look([clamp01(c) for c in vlog])

    slug = args.name
    if not slug:
        slug = Path(args.look).stem
        for strip in ("_VLog", "-VLog"):
            if slug.endswith(strip):
                slug = slug[: -len(strip)]
    title = f"Rec.709 to {slug.replace('_', ' ')}"

    # diagnostics on the neutral axis, before writing anything
    ramp = [(i / 100.0, transform([i / 100.0] * 3)[1]) for i in range(101)]
    white = ramp[-1][1]
    grey_in = math.pow(GREY, 1.0 / args.gamma)
    grey_out = transform([grey_in] * 3)[1]
    slopes = [(ramp[i + 1][1] - ramp[i][1]) / 0.01 for i in range(len(ramp) - 1)]
    monotone = all(ramp[i + 1][1] >= ramp[i][1] - 1e-9 for i in range(len(ramp) - 1))
    print(f"look            : {look.name} ({look.size}-point)")
    print(f"highlight expand: {REC709_HEADROOM:.2f} -> {args.highlight_stops:.2f} stops "
          f"above grey (power {args.power})")
    print(f"18% grey        : Rec.709 {grey_in:.4f} -> {grey_out:.4f}")
    print(f"white           : Rec.709 1.0000 -> {white:.4f}")
    print(f"composite slope : min {min(slopes):.2f}  max {max(slopes):.2f}")
    print(f"monotone        : {monotone}")
    if white < 0.95:
        print("  warning: white lands below 0.95, the result will look washed out; "
              "raise --highlight-stops")
    if max(slopes) > 2.0:
        print("  warning: composite slope above 2.0 will amplify 8-bit banding; "
              "lower --highlight-stops")

    for size in [int(s) for s in args.sizes.split(",") if s.strip()]:
        suffix = "" if size == 33 else f"_{size}"
        out = Path(args.output_dir) / f"Rec709_to_{slug}{suffix}.cube"
        write_cube(out, title, size, transform)
        print(out)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--look", required=True, help="a V-Log style .cube from this repository")
    p.add_argument("--name", default="", help="name for the look in the output filename")
    p.add_argument("--gamma", type=float, default=2.4,
                   help="display EOTF for the source footage (default 2.4 / BT.1886)")
    p.add_argument("--highlight-stops", type=float, default=5.5,
                   help="stops above grey to expand Rec.709 white to (default 5.5)")
    p.add_argument("--power", type=float, default=2.0,
                   help="expansion shape; higher keeps more of the mid-tones untouched")
    p.add_argument("--sizes", default="33,65")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.set_defaults(func=build)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
