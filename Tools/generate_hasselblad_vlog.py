#!/usr/bin/env python3
import argparse
import importlib.util
import json
import math
import struct
from pathlib import Path


PHOCUS_REVERSE = Path(r"C:\Users\shenm\Desktop\test\phocus_reverse")
PHOCUS_CC_SCRIPT = PHOCUS_REVERSE / "phocus_color_correct.py"
DEFAULT_ARTIFACT = PHOCUS_REVERSE / "hasselblad_x2d100c_standard_cc.json"
DEFAULT_OUTPUT_DIR = Path(r"E:\V-Log-Alchemy\Luts\Hasselblad")
SCRIPT_DIR = Path(__file__).resolve().parent
NATURE_GRADATION_U16 = SCRIPT_DIR / "hasselblad_nature_gradation_u16.bin"
COLOR_STYLES = ("Standard", "Nature")


def load_phocus_module():
    spec = importlib.util.spec_from_file_location("phocus_color_correct", PHOCUS_CC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def chromatic_adaptation_bradford(src_white_xy, dst_white_xy):
    bradford = [
        [0.8951, 0.2664, -0.1614],
        [-0.7502, 1.7135, 0.0367],
        [0.0389, -0.0685, 1.0296],
    ]
    bradford_inv = mat_inv_3(bradford)
    src_lms = mat_vec(bradford, xy_to_xyz(*src_white_xy))
    dst_lms = mat_vec(bradford, xy_to_xyz(*dst_white_xy))
    scale = [
        [dst_lms[0] / src_lms[0], 0.0, 0.0],
        [0.0, dst_lms[1] / src_lms[1], 0.0],
        [0.0, 0.0, dst_lms[2] / src_lms[2]],
    ]
    return mat_mul(mat_mul(bradford_inv, scale), bradford)


def vlog_to_linear(v):
    # Panasonic V-Log reference manual constants.
    cut = 0.181
    b = 0.00873
    c = 0.241514
    d = 0.598206
    if v < cut:
        return (v - 0.125) / 5.6
    return math.pow(10.0, (v - d) / c) - b


def build_vgamut_to_hasselblad_rgb_matrix():
    d65 = (0.3127, 0.3290)
    d50 = (0.3457, 0.3585)
    v_gamut_primaries = (0.730, 0.280, 0.165, 0.840, 0.100, -0.030)
    v_gamut_to_xyz_d65 = rgb_to_xyz_matrix(v_gamut_primaries, d65)
    d65_to_d50 = chromatic_adaptation_bradford(d65, d50)
    v_gamut_to_xyz_d50 = mat_mul(d65_to_d50, v_gamut_to_xyz_d65)
    hasselblad_rgb_to_xyz_d50 = [
        [0.6491241455, 0.1885833740, 0.1264953613],
        [0.2988586426, 0.6574554443, 0.0436859131],
        [0.0046386719, 0.0430297852, 0.7772369385],
    ]
    xyz_d50_to_hasselblad = mat_inv_3(hasselblad_rgb_to_xyz_d50)
    return mat_mul(xyz_d50_to_hasselblad, v_gamut_to_xyz_d50)


def clamp01(x):
    return max(0.0, min(1.0, x))


def load_u16_curve(path):
    data = Path(path).read_bytes()
    values = struct.unpack("<" + "H" * (len(data) // 2), data)
    if len(values) != 65536:
        raise ValueError(f"Expected 65536 u16 curve entries, got {len(values)}")
    return values


def apply_u16_curve(rgb, curve):
    out = []
    for c in rgb:
        idx = int(math.floor(clamp01(c) * 65535.0 + 0.5))
        idx = max(0, min(65535, idx))
        out.append(curve[idx] / 65535.0)
    return out


def load_style_gradation(style):
    if style == "Nature":
        return load_u16_curve(NATURE_GRADATION_U16)
    return None


def apply_style_gradation(rgb, style_curve):
    if style_curve is None:
        return rgb
    return apply_u16_curve(rgb, style_curve)


def output_path_for_style(output_dir, style, size):
    suffix = "" if size == 33 else f"_{size}"
    return output_dir / f"Hasselblad_{style}_Phocus_X2D_VLog{suffix}.cube"


def write_cube(path, title, size, transform):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as f:
        f.write(f'TITLE "{title}"\n')
        f.write("#LUMIXPHOTOSTYLE VLOG\n")
        f.write(f"LUT_3D_SIZE {size}\n\n")
        denom = size - 1
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    out = transform([r / denom, g / denom, b / denom])
                    f.write(f"{clamp01(out[0]):.9g} {clamp01(out[1]):.9g} {clamp01(out[2]):.9g}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate Hasselblad Phocus-derived V-Log LUTs.")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--style", choices=COLOR_STYLES, default="Standard")
    parser.add_argument("--all-styles", action="store_true")
    parser.add_argument("--size", type=int, default=33)
    parser.add_argument("--sizes", default="", help="Comma-separated LUT sizes for --all-styles, default: 33,65")
    parser.add_argument("--exposure-scale", type=float, default=1.0)
    parser.add_argument(
        "--include-color-correct",
        action="store_true",
        help="Experimental: include the captured WB-dependent Phocus ColorCorrect/CbCr stage.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path for one style. Ignored with --all-styles.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    phocus = load_phocus_module()
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    params = None
    cc_texture = None
    if args.include_color_correct:
        params = phocus.load_params(artifact["set_color_correct_meta"])
        cc_texture = phocus.load_float4_texture(artifact["color_map_float4_256x256"])
    film_curve = phocus.load_film_curve(artifact["film_curve_float_65536"])
    vgamut_to_hass = build_vgamut_to_hasselblad_rgb_matrix()

    styles = COLOR_STYLES if args.all_styles else (args.style,)
    if args.all_styles:
        sizes = [int(s.strip()) for s in (args.sizes or "33,65").split(",") if s.strip()]
    else:
        sizes = [args.size]

    for style in styles:
        style_curve = load_style_gradation(style)

        def transform(vlog_rgb, style_curve=style_curve):
            vgamut_lin = [vlog_to_linear(c) for c in vlog_rgb]
            hass_rgb = mat_vec(vgamut_to_hass, vgamut_lin)
            hass_rgb = [max(0.0, c * args.exposure_scale) for c in hass_rgb]
            if args.include_color_correct:
                hass_rgb = phocus.apply_color_correct(hass_rgb, params, cc_texture)
            rendered = phocus.apply_film_curve(hass_rgb, film_curve)
            return apply_style_gradation(rendered, style_curve)

        for size in sizes:
            if args.output and not args.all_styles:
                out_path = Path(args.output)
            else:
                out_path = output_path_for_style(Path(args.output_dir), style, size)
            path_desc = "ColorCorrect" if args.include_color_correct else "Curve"
            title = f"Hasselblad {style} Phocus X2D {path_desc} from V-Log"
            write_cube(out_path, title, size, transform)
            print(out_path)


if __name__ == "__main__":
    main()
