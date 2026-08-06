#!/usr/bin/env python3
"""Generate V-Log LUTs from the recovered Hasselblad Phocus rendering path."""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ARTIFACT = SCRIPT_DIR / "hasselblad_x2d100c_standard_cc.json"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "Luts" / "Hasselblad"
COLOR_STYLES = ("Standard", "Nature")
OUTPUT_SPACES = ("rec709", "srgb", "hasselblad-rgb")
D65_WHITE_XY = (0.3127, 0.3290)
V_GAMUT_PRIMARIES = (0.730, 0.280, 0.165, 0.840, 0.100, -0.030)
REC709_PRIMARIES = (0.640, 0.330, 0.300, 0.600, 0.150, 0.060)


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


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_artifact(path):
    artifact_path = Path(path).expanduser().resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Hasselblad artifact manifest not found: {artifact_path}")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact.get("schema_version") != 1:
        raise ValueError(
            f"Unsupported artifact schema in {artifact_path}; expected schema_version 1"
        )
    for key in ("working_space", "color_correct", "assets"):
        if key not in artifact:
            raise ValueError(f"Artifact manifest is missing {key!r}: {artifact_path}")
    return artifact_path, artifact


def resolve_asset(artifact_path, artifact, name):
    try:
        spec = artifact["assets"][name]
        relative_path = spec["path"]
    except KeyError as exc:
        raise ValueError(f"Artifact manifest is missing asset {name!r}") from exc

    asset_path = Path(relative_path)
    if not asset_path.is_absolute():
        asset_path = artifact_path.parent / asset_path
    asset_path = asset_path.resolve()
    if not asset_path.is_file():
        raise FileNotFoundError(f"Bundled Hasselblad asset not found: {asset_path}")

    expected_hash = str(spec.get("sha256", "")).lower()
    if expected_hash:
        actual_hash = sha256_file(asset_path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"SHA-256 mismatch for {asset_path.name}: expected {expected_hash}, got {actual_hash}"
            )
    return asset_path, spec


def unpack_binary(path, scalar_format, expected_count, label):
    data = Path(path).read_bytes()
    scalar_size = struct.calcsize("<" + scalar_format)
    expected_size = expected_count * scalar_size
    if len(data) != expected_size:
        raise ValueError(
            f"Expected {expected_size} bytes for {label}, got {len(data)} from {path}"
        )
    return struct.unpack("<" + scalar_format * expected_count, data)


def load_float2_texture(path, width, height):
    values = unpack_binary(path, "f", width * height * 2, "float2 ColorCorrect texture")
    return [values[i : i + 2] for i in range(0, len(values), 2)]


def load_film_curve(path, entries):
    return unpack_binary(path, "f", entries, "Phocus film curve")


def load_u16_curve(path, entries):
    return unpack_binary(path, "H", entries, "Phocus style gradation")


def dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def sample_float2_linear(texture, coord, width, height):
    # The shader addresses integer texel centres with coordinates i + 0.5.
    x = coord[0] - 0.5
    y = coord[1] - 0.5
    x0 = math.floor(x)
    y0 = math.floor(y)
    fx = x - x0
    fy = y - y0

    def tex(ix, iy):
        ix = max(0, min(width - 1, int(ix)))
        iy = max(0, min(height - 1, int(iy)))
        return texture[iy * width + ix]

    c00 = tex(x0, y0)
    c10 = tex(x0 + 1, y0)
    c01 = tex(x0, y0 + 1)
    c11 = tex(x0 + 1, y0 + 1)
    out = []
    for channel in range(2):
        a = c00[channel] * (1.0 - fx) + c10[channel] * fx
        b = c01[channel] * (1.0 - fx) + c11[channel] * fx
        out.append(a * (1.0 - fy) + b * fy)
    return out


def apply_color_correct(rgb, params, texture, width, height):
    rgb16 = [max(0.0, float(channel)) * 65535.0 for channel in rgb]
    avg = max(sum(rgb16) / 3.0, 1e-5)
    chroma_distance = max(abs(rgb16[0] - avg), abs(rgb16[1] - avg), abs(rgb16[2] - avg)) / avg

    lo, hi = params["desat_gray"]
    gray_factor = max(0.0, min(1.0, (chroma_distance - lo) / (hi - lo))) if hi > lo else 1.0

    input_matrix = params["input_matrix"]
    y = dot3(rgb16, input_matrix[0])
    cb = dot3(rgb16, input_matrix[1])
    cr = dot3(rgb16, input_matrix[2])
    safe_y = max(y, 1e-5)

    dark_x, dark_a, dark_b, dark_c = params["dark_params"]
    dark_limit = dark_a * y * y + dark_b * y + dark_c if y < dark_x else 1.0
    chroma_scale = min(gray_factor, dark_limit)

    div = params["div_factor"]
    start_cb, start_cr = params["start_cbcr"]
    limit_cb, limit_cr = params["cbcr_limits"]
    cc_x = cb * (div / safe_y) - start_cb + 0.5
    cc_y = cr * (div / safe_y) - start_cr + 0.5
    cc_x = max(0.5, min(limit_cb - 0.5, cc_x))
    cc_y = max(0.5, min(limit_cr - 0.5, cc_y))

    lut = sample_float2_linear(texture, (cc_x, cc_y), width, height)
    ycc = [safe_y, chroma_scale * safe_y * lut[0], chroma_scale * safe_y * lut[1]]
    out16 = [dot3(ycc, row) for row in params["output_matrix"]]
    return [max(channel / 65535.0, 0.0) for channel in out16]


def apply_film_curve(rgb, film_curve):
    out = []
    for channel in rgb:
        channel = max(0.0, min(0.9999, float(channel)))
        index = int(math.floor(channel * 65536.0))
        index = max(0, min(65535, index))
        out.append(max(0.0, min(1.0, film_curve[index] / 65535.0)))
    return out


def vlog_to_linear(value):
    # Panasonic V-Log reference manual constants.
    cut = 0.181
    b = 0.00873
    c = 0.241514
    d = 0.598206
    if value < cut:
        return (value - 0.125) / 5.6
    return math.pow(10.0, (value - d) / c) - b


def build_vgamut_to_hasselblad_rgb_matrix(working_space):
    hasselblad_white = tuple(working_space["white_xy"])
    hasselblad_rgb_to_xyz = working_space["rgb_to_xyz"]
    vgamut_to_xyz_d65 = rgb_to_xyz_matrix(V_GAMUT_PRIMARIES, D65_WHITE_XY)
    d65_to_hasselblad_white = chromatic_adaptation_bradford(D65_WHITE_XY, hasselblad_white)
    vgamut_to_hasselblad_xyz = mat_mul(d65_to_hasselblad_white, vgamut_to_xyz_d65)
    return mat_mul(mat_inv_3(hasselblad_rgb_to_xyz), vgamut_to_hasselblad_xyz)


def build_hasselblad_to_display_matrix(working_space):
    hasselblad_white = tuple(working_space["white_xy"])
    hasselblad_rgb_to_xyz = working_space["rgb_to_xyz"]
    source_to_d65 = chromatic_adaptation_bradford(hasselblad_white, D65_WHITE_XY)
    rec709_to_xyz_d65 = rgb_to_xyz_matrix(REC709_PRIMARIES, D65_WHITE_XY)
    return mat_mul(mat_inv_3(rec709_to_xyz_d65), mat_mul(source_to_d65, hasselblad_rgb_to_xyz))


def encode_rec709(value):
    # Continuous form of the BT.709 OETF (the published 1.099/0.018 values are
    # rounded and otherwise introduce a small discontinuity at the join).
    alpha = 1.09929682680944
    cut = 0.018053968510807
    if value < cut:
        return 4.5 * value
    return alpha * math.pow(value, 0.45) - (alpha - 1.0)


def encode_srgb(value):
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * math.pow(value, 1.0 / 2.4) - 0.055


def convert_output_space(rgb, output_space, working_space, hasselblad_to_display):
    if output_space == "hasselblad-rgb":
        return rgb

    # The film/gradation values are interpreted as Hasselblad RGB ICC code
    # values. Decode the profile TRC before the colour-primary conversion.
    gamma = float(working_space["icc_trc_gamma"])
    hasselblad_linear = [math.pow(max(channel, 0.0), gamma) for channel in rgb]
    display_linear = mat_vec(hasselblad_to_display, hasselblad_linear)
    encoder = encode_rec709 if output_space == "rec709" else encode_srgb
    return [encoder(channel) for channel in display_linear]


def clamp01(value):
    return max(0.0, min(1.0, value))


def highlight_rolloff(rgb, knee, ceiling=1.0):
    # Reinhard-style shoulder applied to render-linear RGB before the film curve.
    span = ceiling - knee
    if span <= 0.0:
        return [min(channel, ceiling) for channel in rgb]
    out = []
    for channel in rgb:
        if channel <= knee:
            out.append(channel)
        else:
            excess = channel - knee
            out.append(knee + span * (excess / (excess + span)))
    return out


def apply_u16_curve(rgb, curve):
    out = []
    for channel in rgb:
        index = int(math.floor(clamp01(channel) * 65535.0 + 0.5))
        index = max(0, min(65535, index))
        out.append(curve[index] / 65535.0)
    return out


def output_path_for_style(output_dir, style, size, output_space):
    space_suffix = {
        "hasselblad-rgb": "_HassRGBD50",
        "rec709": "_Rec709",
        "srgb": "_sRGB",
    }[output_space]
    size_suffix = "" if size == 33 else f"_{size}"
    return output_dir / f"Hasselblad_{style}_Phocus_X2D_VLog{space_suffix}{size_suffix}.cube"


def output_description(output_space):
    return {
        "hasselblad-rgb": "Hasselblad RGB / D50 / Phocus film-curve code values",
        "rec709": "Rec.709 primaries / D65 / BT.709 OETF",
        "srgb": "sRGB primaries / D65 / sRGB transfer function",
    }[output_space]


def write_cube(path, title, size, output_space, transform):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(f'TITLE "{title}"\n')
        stream.write("#LUMIXPHOTOSTYLE VLOG\n")
        stream.write("# INPUT_COLORSPACE Panasonic V-Log / V-Gamut\n")
        stream.write(f"# OUTPUT_COLORSPACE {output_description(output_space)}\n")
        stream.write(f"LUT_3D_SIZE {size}\n\n")
        denominator = size - 1
        for blue in range(size):
            for green in range(size):
                for red in range(size):
                    out = transform([red / denominator, green / denominator, blue / denominator])
                    stream.write(
                        f"{clamp01(out[0]):.9g} {clamp01(out[1]):.9g} {clamp01(out[2]):.9g}\n"
                    )


def parse_sizes(parser, args):
    raw_sizes = (args.sizes or "33,65").split(",") if args.all_styles else [str(args.size)]
    try:
        sizes = [int(value.strip()) for value in raw_sizes if value.strip()]
    except ValueError as exc:
        parser.error(f"invalid LUT size: {exc}")
    if not sizes or any(size < 2 for size in sizes):
        parser.error("LUT sizes must be integers greater than or equal to 2")
    return sizes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        default=str(DEFAULT_ARTIFACT),
        help="Artifact manifest; relative asset paths are resolved next to it.",
    )
    parser.add_argument("--style", choices=COLOR_STYLES, default="Standard")
    parser.add_argument("--all-styles", action="store_true")
    parser.add_argument("--size", type=int, default=33)
    parser.add_argument("--sizes", default="", help="Comma-separated sizes for --all-styles (default: 33,65).")
    parser.add_argument("--exposure-scale", type=float, default=1.0)
    parser.add_argument(
        "--highlight-rolloff",
        action="store_true",
        help="Apply a smooth highlight shoulder before the film curve.",
    )
    parser.add_argument(
        "--rolloff-knee",
        type=float,
        default=0.5,
        help="Render-linear value where the highlight shoulder starts (default: 0.5).",
    )
    parser.add_argument(
        "--include-color-correct",
        action="store_true",
        help="Include the captured daylight Phocus ColorCorrect/CbCr stage.",
    )
    parser.add_argument(
        "--output-space",
        choices=OUTPUT_SPACES,
        default="rec709",
        help=(
            "rec709 (default) and srgb emit complete display conversions; "
            "hasselblad-rgb emits the D50 intermediate for advanced analysis only."
        ),
    )
    parser.add_argument("--output", default="", help="Output path for one style; invalid with --all-styles.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--verify-assets-only",
        action="store_true",
        help="Validate the bundled artifact files and exit without generating LUTs.",
    )
    args = parser.parse_args(argv)

    if args.output and args.all_styles:
        parser.error("--output cannot be combined with --all-styles; use --output-dir")
    if args.exposure_scale <= 0.0:
        parser.error("--exposure-scale must be greater than zero")
    if args.highlight_rolloff and not 0.0 <= args.rolloff_knee < 1.0:
        parser.error("--rolloff-knee must be in the range [0, 1)")
    sizes = parse_sizes(parser, args)

    artifact_path, artifact = load_artifact(args.artifact)
    film_path, film_spec = resolve_asset(artifact_path, artifact, "standard_film_curve")
    nature_path, nature_spec = resolve_asset(artifact_path, artifact, "nature_gradation")
    texture_path, texture_spec = resolve_asset(artifact_path, artifact, "daylight_color_correct_lut")
    if args.verify_assets_only:
        print(f"Verified Hasselblad artifact bundle: {artifact_path}")
        return 0

    film_curve = load_film_curve(film_path, int(film_spec["entries"]))
    texture_width = int(texture_spec["width"])
    texture_height = int(texture_spec["height"])
    cc_texture = None
    if args.include_color_correct:
        cc_texture = load_float2_texture(texture_path, texture_width, texture_height)
    params = artifact["color_correct"]["params"]
    working_space = artifact["working_space"]
    vgamut_to_hasselblad = build_vgamut_to_hasselblad_rgb_matrix(working_space)
    hasselblad_to_display = build_hasselblad_to_display_matrix(working_space)

    styles = COLOR_STYLES if args.all_styles else (args.style,)
    for style in styles:
        style_curve = None
        if style == "Nature":
            style_curve = load_u16_curve(nature_path, int(nature_spec["entries"]))

        def transform(vlog_rgb, style_curve=style_curve):
            vgamut_linear = [vlog_to_linear(channel) for channel in vlog_rgb]
            hasselblad_rgb = mat_vec(vgamut_to_hasselblad, vgamut_linear)
            hasselblad_rgb = [max(0.0, channel * args.exposure_scale) for channel in hasselblad_rgb]
            if cc_texture is not None:
                hasselblad_rgb = apply_color_correct(
                    hasselblad_rgb,
                    params,
                    cc_texture,
                    texture_width,
                    texture_height,
                )
            if args.highlight_rolloff:
                hasselblad_rgb = highlight_rolloff(hasselblad_rgb, args.rolloff_knee)
            rendered = apply_film_curve(hasselblad_rgb, film_curve)
            if style_curve is not None:
                rendered = apply_u16_curve(rendered, style_curve)
            return convert_output_space(
                rendered,
                args.output_space,
                working_space,
                hasselblad_to_display,
            )

        for size in sizes:
            if args.output:
                out_path = Path(args.output)
            else:
                out_path = output_path_for_style(Path(args.output_dir), style, size, args.output_space)
            path_description = "ColorCorrect" if args.include_color_correct else "Curve"
            title = f"Hasselblad {style} Phocus X2D {path_description} from V-Log"
            title += {
                "rec709": " to Rec.709",
                "srgb": " to sRGB",
                "hasselblad-rgb": " to Hasselblad RGB D50",
            }[args.output_space]
            write_cube(out_path, title, size, args.output_space, transform)
            print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
