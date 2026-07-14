#!/usr/bin/env python3
"""Bake V-Log creative LUTs into Panasonic Standard-input camera LUTs."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import tempfile
import threading
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
CONVERSION_DIR = REPO_DIR / "Luts" / "Panasonic-Standard" / "Conversion"
DEFAULT_OUTPUT_DIR = REPO_DIR / "Luts" / "Panasonic-Standard" / "Generated"

MODEL_FILES = {
    "GH6": "GH6S2V.cube",
    "S5II": "S5IIS2V.cube",
    "S5IIX": "S5IIXS2V.cube",
    "G9II": "G9IIS2V.cube",
    "GH7": "GH7S2V.cube",
    "S9": "S9S2V.cube",
    "S1IIE": "S1IIES2V.cube",
    "S1RII": "S1RIIS2V.cube",
    "S1II": "S1IIS2V.cube",
    "DC-L10": "L10S2V.cube",
}

MODEL_ALIASES = {
    "GH6": "GH6",
    "DCGH6": "GH6",
    "S5II": "S5II",
    "DCS5M2": "S5II",
    "S5M2": "S5II",
    "S5IIX": "S5IIX",
    "DCS5M2X": "S5IIX",
    "S5M2X": "S5IIX",
    "G9II": "G9II",
    "DCG9M2": "G9II",
    "G9M2": "G9II",
    "GH7": "GH7",
    "DCGH7": "GH7",
    "S9": "S9",
    "DCS9": "S9",
    "S1IIE": "S1IIE",
    "DCS1M2E": "S1IIE",
    "S1M2E": "S1IIE",
    "DCS1M2ES": "S1IIE",
    "S1M2ES": "S1IIE",
    "S1RII": "S1RII",
    "DCS1RM2": "S1RII",
    "S1RM2": "S1RII",
    "S1II": "S1II",
    "DCS1M2": "S1II",
    "S1M2": "S1II",
    "DCL10": "DC-L10",
    "L10": "DC-L10",
}

CAMERA_NAME_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")
DOS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class MergeError(Exception):
    """An error that can be shown directly to the user."""


@dataclass(frozen=True)
class CubeLUT:
    path: Path
    title: str
    size: int
    domain_min: tuple[float, float, float]
    domain_max: tuple[float, float, float]
    values: tuple[tuple[float, float, float], ...]

    def value(self, r: int, g: int, b: int) -> tuple[float, float, float]:
        return self.values[(b * self.size + g) * self.size + r]


def normalize_model(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    try:
        return MODEL_ALIASES[key]
    except KeyError as exc:
        supported = ", ".join(MODEL_FILES)
        raise MergeError(f"Unsupported camera model '{value}'. Supported models: {supported}.") from exc


def conversion_path_for_model(model: str) -> tuple[str, Path]:
    canonical = normalize_model(model)
    path = CONVERSION_DIR / MODEL_FILES[canonical]
    if not path.is_file():
        raise MergeError(
            f"The Standard-to-V-Log conversion LUT for {canonical} was not found:\n{path}\n"
            "Restore the repository's Luts/Panasonic-Standard/Conversion directory."
        )
    return canonical, path


def _parse_float_list(tokens: Sequence[str], path: Path, line_number: int) -> list[float]:
    try:
        values = [float(token) for token in tokens]
    except ValueError as exc:
        raise MergeError(f"{path}:{line_number}: expected numeric values.") from exc
    if not all(math.isfinite(value) for value in values):
        raise MergeError(f"{path}:{line_number}: NaN and infinity are not supported.")
    return values


def _parse_title(line: str, path: Path, line_number: int) -> str:
    value = line[len(line.split(maxsplit=1)[0]) :].strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    if not value:
        raise MergeError(f"{path}:{line_number}: TITLE is empty.")
    return value


def load_cube(path_value: os.PathLike[str] | str) -> CubeLUT:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise MergeError(f"LUT file not found: {path}")

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise MergeError(f"{path}: the LUT must be UTF-8 or ASCII text.") from exc
    except OSError as exc:
        raise MergeError(f"Could not read LUT file {path}: {exc}") from exc

    title = path.stem
    size: int | None = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    data: list[tuple[float, float, float]] = []

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        tokens = content.split()
        directive = tokens[0].upper()

        if directive == "TITLE":
            title = _parse_title(content, path, line_number)
        elif directive == "LUT_1D_SIZE":
            raise MergeError(f"{path}:{line_number}: 1D LUTs are not supported; select a 3D .cube LUT.")
        elif directive == "LUT_3D_SIZE":
            if len(tokens) != 2:
                raise MergeError(f"{path}:{line_number}: LUT_3D_SIZE requires one integer.")
            try:
                parsed_size = int(tokens[1])
            except ValueError as exc:
                raise MergeError(f"{path}:{line_number}: invalid LUT_3D_SIZE '{tokens[1]}'.") from exc
            if parsed_size < 2 or parsed_size > 256:
                raise MergeError(f"{path}:{line_number}: LUT_3D_SIZE must be between 2 and 256.")
            if size is not None and size != parsed_size:
                raise MergeError(f"{path}:{line_number}: conflicting LUT_3D_SIZE directives.")
            size = parsed_size
        elif directive in {"DOMAIN_MIN", "DOMAIN_MAX"}:
            values = _parse_float_list(tokens[1:], path, line_number)
            if len(values) != 3:
                raise MergeError(f"{path}:{line_number}: {directive} requires three values.")
            triple = (values[0], values[1], values[2])
            if directive == "DOMAIN_MIN":
                domain_min = triple
            else:
                domain_max = triple
        elif directive == "LUT_3D_INPUT_RANGE":
            values = _parse_float_list(tokens[1:], path, line_number)
            if len(values) == 2:
                domain_min = (values[0], values[0], values[0])
                domain_max = (values[1], values[1], values[1])
            elif len(values) == 6:
                domain_min = (values[0], values[1], values[2])
                domain_max = (values[3], values[4], values[5])
            else:
                raise MergeError(
                    f"{path}:{line_number}: LUT_3D_INPUT_RANGE requires two scalar values "
                    "or three minimum values followed by three maximum values."
                )
        else:
            try:
                float(tokens[0])
            except ValueError:
                # Nonstandard metadata is harmless and common in vendor .cube files.
                continue
            values = _parse_float_list(tokens, path, line_number)
            if len(values) != 3:
                raise MergeError(f"{path}:{line_number}: each 3D LUT row must contain exactly three values.")
            data.append((values[0], values[1], values[2]))

    if size is None:
        raise MergeError(f"{path}: missing LUT_3D_SIZE; 1D or non-.cube LUTs are not supported.")
    if any(hi <= lo for lo, hi in zip(domain_min, domain_max)):
        raise MergeError(f"{path}: every input domain maximum must be greater than its minimum.")

    expected_rows = size**3
    if len(data) != expected_rows:
        raise MergeError(
            f"{path}: LUT_3D_SIZE {size} requires {expected_rows} RGB rows, but {len(data)} were found."
        )

    return CubeLUT(path, title, size, domain_min, domain_max, tuple(data))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _add_scaled(
    target: list[float],
    scale: float,
    end: Sequence[float],
    start: Sequence[float],
) -> None:
    for channel in range(3):
        target[channel] += scale * (end[channel] - start[channel])


def sample_tetrahedral(lut: CubeLUT, rgb: Sequence[float]) -> tuple[float, float, float]:
    bases: list[int] = []
    fractions: list[float] = []
    scale = lut.size - 1
    for channel in range(3):
        normalized = (rgb[channel] - lut.domain_min[channel]) / (
            lut.domain_max[channel] - lut.domain_min[channel]
        )
        position = _clamp(normalized, 0.0, 1.0) * scale
        base = min(int(math.floor(position)), lut.size - 2)
        bases.append(base)
        fractions.append(position - base)

    ordered_axes = sorted(range(3), key=lambda axis: fractions[axis], reverse=True)
    r0, g0, b0 = bases
    vertices = [lut.value(r0, g0, b0)]
    coords = [r0, g0, b0]
    for axis in ordered_axes:
        coords[axis] += 1
        vertices.append(lut.value(coords[0], coords[1], coords[2]))

    result = list(vertices[0])
    _add_scaled(result, fractions[ordered_axes[0]], vertices[1], vertices[0])
    _add_scaled(result, fractions[ordered_axes[1]], vertices[2], vertices[1])
    _add_scaled(result, fractions[ordered_axes[2]], vertices[3], vertices[2])
    return (result[0], result[1], result[2])


def sample_trilinear(lut: CubeLUT, rgb: Sequence[float]) -> tuple[float, float, float]:
    bases: list[int] = []
    fractions: list[float] = []
    scale = lut.size - 1
    for channel in range(3):
        normalized = (rgb[channel] - lut.domain_min[channel]) / (
            lut.domain_max[channel] - lut.domain_min[channel]
        )
        position = _clamp(normalized, 0.0, 1.0) * scale
        base = min(int(math.floor(position)), lut.size - 2)
        bases.append(base)
        fractions.append(position - base)

    r0, g0, b0 = bases
    fr, fg, fb = fractions
    result = [0.0, 0.0, 0.0]
    for db in range(2):
        wb = fb if db else 1.0 - fb
        for dg in range(2):
            wg = fg if dg else 1.0 - fg
            for dr in range(2):
                wr = fr if dr else 1.0 - fr
                weight = wr * wg * wb
                value = lut.value(r0 + dr, g0 + dg, b0 + db)
                for channel in range(3):
                    result[channel] += weight * value[channel]
    return (result[0], result[1], result[2])


def sampler_for(name: str) -> Callable[[CubeLUT, Sequence[float]], tuple[float, float, float]]:
    if name == "tetrahedral":
        return sample_tetrahedral
    if name == "trilinear":
        return sample_trilinear
    raise MergeError(f"Unsupported interpolation method '{name}'.")


def _ascii_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "replace").decode("ascii")
    return ascii_value.replace("\\", "/").replace('"', "'")


def _safe_stem_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^A-Za-z0-9]", "", normalized).upper()
    for suffix in ("VLOG", "LUT", "CUBE"):
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
    return token or "STD"


def _base36(value: int, width: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chars = []
    for _ in range(width):
        value, remainder = divmod(value, 36)
        chars.append(alphabet[remainder])
    return "".join(reversed(chars))


def validate_camera_name(value: str, option_name: str) -> str:
    stem = Path(value).stem if value.lower().endswith(".cube") else value
    if not CAMERA_NAME_RE.fullmatch(stem) or stem.upper() in DOS_RESERVED_NAMES:
        raise MergeError(
            f"{option_name} must be a camera-safe basename of 1-8 ASCII letters or digits."
        )
    return stem


def default_camera_name(
    creative: CubeLUT,
    model: str,
    output_dir: Path,
    reserved: set[str],
) -> str:
    prefix = _safe_stem_token(creative.path.stem)[:5]
    identity = f"{model}|{creative.path}|{creative.title}"
    for salt in range(36**3):
        checksum = zlib.crc32(f"{identity}|{salt}".encode("utf-8")) % (36**3)
        stem = f"{prefix}{_base36(checksum, 3)}"[:8]
        key = stem.upper()
        if key not in reserved and not (output_dir / f"{stem}.cube").exists():
            reserved.add(key)
            return stem
    raise MergeError("Could not allocate an unused 8-character output filename.")


def _output_path(
    requested_name: str | None,
    creative: CubeLUT,
    model: str,
    output_dir: Path,
    option_name: str,
    reserved: set[str],
) -> Path:
    if requested_name:
        stem = validate_camera_name(requested_name, option_name)
        key = stem.upper()
        path = output_dir / f"{stem}.cube"
        if key in reserved:
            raise MergeError(f"The requested output name '{stem}' is used more than once.")
        if path.exists():
            raise MergeError(f"Output file already exists: {path}\nChoose another {option_name} value.")
        reserved.add(key)
        return path
    return output_dir / f"{default_camera_name(creative, model, output_dir, reserved)}.cube"


def iter_composed_rows(
    conversion: CubeLUT,
    creative: CubeLUT,
    size: int,
    interpolation: str,
    creative2: CubeLUT | None = None,
) -> Iterable[tuple[float, float, float]]:
    sample_creative = sampler_for(interpolation)
    denominator = size - 1
    for b in range(size):
        blue = b / denominator
        for g in range(size):
            green = g / denominator
            for r in range(size):
                standard_rgb = (r / denominator, green, blue)
                vlog_rgb = sample_trilinear(conversion, standard_rgb)
                result = sample_creative(creative, vlog_rgb)
                if creative2 is not None:
                    result = sample_creative(creative2, result)
                yield result


def write_composed_cube(
    output_path: Path,
    model: str,
    conversion: CubeLUT,
    creative: CubeLUT,
    size: int,
    interpolation: str,
    creative2: CubeLUT | None = None,
) -> None:
    creative_title = creative.path.stem
    if creative2 is not None:
        creative_title = f"{creative.path.stem} then {creative2.path.stem}"
    title = _ascii_title(f"{model} Standard - {creative_title}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            newline="\n",
            prefix=f".{output_path.stem}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(f'TITLE "{title}"\n')
            handle.write("#LUMIXPHOTOSTYLE STD\n")
            handle.write(f"LUT_3D_SIZE {size}\n\n")
            for rgb in iter_composed_rows(conversion, creative, size, interpolation, creative2):
                clipped = tuple(_clamp(value, 0.0, 1.0) for value in rgb)
                handle.write(f"{clipped[0]:.9f} {clipped[1]:.9f} {clipped[2]:.9f}\n")
        os.replace(temporary_path, output_path)
    except OSError as exc:
        raise MergeError(f"Could not write output LUT {output_path}: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def merge_standard_luts(
    model_value: str,
    lut1_value: os.PathLike[str] | str,
    lut2_value: os.PathLike[str] | str | None,
    output_dir_value: os.PathLike[str] | str,
    name1: str | None = None,
    name2: str | None = None,
    size: int = 33,
    interpolation: str = "tetrahedral",
    mode: str = "separate",
) -> list[Path]:
    if size < 2 or size > 33:
        raise MergeError("Camera output LUT size must be between 2 and 33.")
    sampler_for(interpolation)
    if mode not in {"separate", "chain"}:
        raise MergeError("Mode must be 'separate' or 'chain'.")
    if name2 and not lut2_value:
        raise MergeError("--name2 requires --lut2.")
    if mode == "chain" and not lut2_value:
        raise MergeError("Chain mode requires --lut2 because it bakes LUT 2 after LUT 1.")
    if mode == "chain" and name2:
        raise MergeError("Chain mode creates one output; use --name1 for its filename, not --name2.")

    model, conversion_path = conversion_path_for_model(model_value)
    conversion = load_cube(conversion_path)
    creatives = [load_cube(lut1_value)]
    requested_names = [name1]
    if lut2_value:
        creatives.append(load_cube(lut2_value))
        requested_names.append(name2)

    output_dir = Path(output_dir_value).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MergeError(f"Could not create output directory {output_dir}: {exc}") from exc
    if not output_dir.is_dir():
        raise MergeError(f"Output path is not a directory: {output_dir}")

    reserved: set[str] = set()
    if mode == "chain":
        output_paths = [
            _output_path(name1, creatives[0], model, output_dir, "--name1", reserved)
        ]
        write_composed_cube(
            output_paths[0], model, conversion, creatives[0], size, interpolation, creatives[1]
        )
    else:
        output_paths = [
            _output_path(requested, creative, model, output_dir, f"--name{index}", reserved)
            for index, (creative, requested) in enumerate(zip(creatives, requested_names), 1)
        ]
        for creative, output_path in zip(creatives, output_paths):
            write_composed_cube(output_path, model, conversion, creative, size, interpolation)
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bake V-Log creative 3D LUTs into Panasonic Standard-input camera LUTs. "
            "Separate mode creates independent outputs; chain mode bakes LUT 2 after LUT 1."
        )
    )
    parser.add_argument("--model", required=True, help="Camera model, for example S1RII or DC-S1RM2.")
    parser.add_argument("--lut1", required=True, help="First V-Log creative .cube LUT.")
    parser.add_argument("--lut2", help="Optional second V-Log creative .cube LUT.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated camera LUTs.")
    parser.add_argument("--name1", help="Optional camera-safe output basename for LUT 1 (maximum 8 characters).")
    parser.add_argument("--name2", help="Optional camera-safe output basename for LUT 2 (maximum 8 characters).")
    parser.add_argument("--size", type=int, default=33, help="Output cube size from 2 through 33 (default: 33).")
    parser.add_argument(
        "--interpolation",
        choices=("trilinear", "tetrahedral"),
        default="tetrahedral",
        help="Interpolation for creative LUTs (default: tetrahedral; conversion LUT stays trilinear).",
    )
    parser.add_argument(
        "--mode",
        choices=("separate", "chain"),
        default="separate",
        help=(
            "separate writes creative1(S2V(x)) and creative2(S2V(x)) as independent LUTs; "
            "chain writes one creative2(creative1(S2V(x))) LUT (default: separate)."
        ),
    )
    return parser


def cli_main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        paths = merge_standard_luts(
            args.model,
            args.lut1,
            args.lut2,
            args.output_dir,
            args.name1,
            args.name2,
            args.size,
            args.interpolation,
            args.mode,
        )
    except MergeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path in paths:
        print(path)
    return 0


def launch_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise SystemExit("Tkinter is unavailable. Run this tool with CLI arguments instead.") from exc

    root = tk.Tk()
    root.title("Panasonic Standard LUT Merger")
    root.minsize(700, 350)

    model_var = tk.StringVar(value="S1RII")
    lut1_var = tk.StringVar()
    lut2_var = tk.StringVar()
    output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
    size_var = tk.StringVar(value="33")
    interpolation_var = tk.StringVar(value="tetrahedral")
    mode_var = tk.StringVar(value="separate (independent outputs)")
    status_var = tk.StringVar(value="Select a camera model and at least one V-Log 3D LUT.")

    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    def browse_lut(variable: "tk.StringVar") -> None:
        selected = filedialog.askopenfilename(
            title="Select a V-Log creative LUT",
            filetypes=(("Cube LUT", "*.cube"), ("All files", "*.*")),
        )
        if selected:
            variable.set(selected)

    def browse_output() -> None:
        selected = filedialog.askdirectory(title="Select output directory", initialdir=output_var.get())
        if selected:
            output_var.set(selected)

    ttk.Label(frame, text="Camera model").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
    model_box = ttk.Combobox(frame, textvariable=model_var, values=tuple(MODEL_FILES), state="readonly")
    model_box.grid(row=0, column=1, sticky="ew", pady=6)

    ttk.Label(frame, text="V-Log LUT 1").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
    ttk.Entry(frame, textvariable=lut1_var).grid(row=1, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Browse...", command=lambda: browse_lut(lut1_var)).grid(row=1, column=2, padx=(8, 0), pady=6)

    ttk.Label(frame, text="V-Log LUT 2 (optional)").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
    ttk.Entry(frame, textvariable=lut2_var).grid(row=2, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Browse...", command=lambda: browse_lut(lut2_var)).grid(row=2, column=2, padx=(8, 0), pady=6)

    ttk.Label(frame, text="Output directory").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
    ttk.Entry(frame, textvariable=output_var).grid(row=3, column=1, sticky="ew", pady=6)
    ttk.Button(frame, text="Browse...", command=browse_output).grid(row=3, column=2, padx=(8, 0), pady=6)

    ttk.Label(frame, text="Two-LUT mode").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=6)
    ttk.Combobox(
        frame,
        textvariable=mode_var,
        values=("separate (independent outputs)", "chain (LUT 2 after LUT 1)"),
        state="readonly",
    ).grid(row=4, column=1, sticky="ew", pady=6)

    options = ttk.Frame(frame)
    options.grid(row=5, column=1, sticky="w", pady=6)
    ttk.Label(options, text="Size").grid(row=0, column=0, padx=(0, 6))
    ttk.Spinbox(options, from_=2, to=33, width=5, textvariable=size_var).grid(row=0, column=1, padx=(0, 20))
    ttk.Label(options, text="Creative interpolation").grid(row=0, column=2, padx=(0, 6))
    ttk.Combobox(
        options,
        textvariable=interpolation_var,
        values=("tetrahedral", "trilinear"),
        state="readonly",
        width=14,
    ).grid(row=0, column=3)

    action_button = ttk.Button(frame, text="Generate Standard LUTs")
    action_button.grid(row=6, column=1, sticky="w", pady=(14, 8))
    ttk.Label(frame, textvariable=status_var, wraplength=650, justify="left").grid(
        row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0)
    )

    def finish_success(paths: list[Path]) -> None:
        action_button.configure(state="normal")
        status_var.set("Generated:\n" + "\n".join(str(path) for path in paths))
        messagebox.showinfo("LUT generation complete", "Generated:\n\n" + "\n".join(str(path) for path in paths))

    def finish_error(message: str) -> None:
        action_button.configure(state="normal")
        status_var.set(f"Error: {message}")
        messagebox.showerror("LUT generation failed", message)

    def worker(values: tuple[str, str, str | None, str, None, None, int, str, str]) -> None:
        try:
            paths = merge_standard_luts(*values)
        except (MergeError, OSError) as exc:
            root.after(0, finish_error, str(exc))
        except Exception as exc:  # Keep Tk alive while surfacing unexpected failures.
            root.after(0, finish_error, f"Unexpected error: {exc}")
        else:
            root.after(0, finish_success, paths)

    def generate() -> None:
        lut1 = lut1_var.get().strip()
        lut2 = lut2_var.get().strip() or None
        output = output_var.get().strip()
        if not lut1:
            finish_error("Select V-Log LUT 1.")
            return
        if not output:
            finish_error("Select an output directory.")
            return
        try:
            size = int(size_var.get())
        except ValueError:
            finish_error("Size must be an integer from 2 through 33.")
            return
        action_button.configure(state="disabled")
        status_var.set("Generating LUTs...")
        mode = mode_var.get().split(" ", 1)[0]
        values = (model_var.get(), lut1, lut2, output, None, None, size, interpolation_var.get(), mode)
        threading.Thread(target=worker, args=(values,), daemon=True).start()

    action_button.configure(command=generate)
    root.mainloop()


def main() -> int:
    if len(sys.argv) == 1:
        launch_gui()
        return 0
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
