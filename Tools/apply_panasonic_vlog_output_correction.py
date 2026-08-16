#!/usr/bin/env python3
"""Apply the shared measured V-Log output correction to Panasonic S2V LUTs.

All Panasonic Standard-input adapters target the same V-Log/V-Gamut endpoint.
Controlled S1RII captures and an independent S9 field report show the same
high-chroma cyan/blue failure, so the measured output-domain correction is
shared by every published adapter.  The fit preserves each row's mean code
before final clipping and leaves every exactly neutral RGB value unchanged.

Inputs are hash-locked to the uncorrected release LUTs.  This prevents double
application and keeps the common post-process auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "Luts" / "Panasonic-Standard"
DEFAULT_CALIBRATION = PACKAGE_ROOT / "Calibration" / "PanasonicVLogOutput.json"
CORRECTION_MARKER = "# PANASONIC_VLOG_OUTPUT_CHROMA_CORRECTION"
CALIBRATION_REFERENCE = (
    "# Calibration: Luts/Panasonic-Standard/Calibration/PanasonicVLogOutput.json"
)


class CorrectionError(ValueError):
    """Raised for invalid calibration data or an incompatible LUT."""


def canonical_lf_sha256(text: str) -> str:
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def load_calibration(path: Path) -> dict[str, object]:
    try:
        calibration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorrectionError(f"Could not read calibration {path}: {exc}") from exc

    if calibration.get("schema_version") != 1:
        raise CorrectionError(f"{path}: unsupported calibration schema")
    if calibration.get("method") != "mean_preserving_opponent_chroma_polynomial":
        raise CorrectionError(f"{path}: unsupported correction method")
    if calibration.get("feature_order") != [
        "c1",
        "c2",
        "y*c1",
        "y*c2",
        "c1^2",
        "c1*c2",
        "c2^2",
    ]:
        raise CorrectionError(f"{path}: unexpected feature order")

    coefficients = calibration.get("coefficients")
    if not isinstance(coefficients, list) or len(coefficients) != 7:
        raise CorrectionError(f"{path}: coefficients must be a 7x2 matrix")
    for row in coefficients:
        if not isinstance(row, list) or len(row) != 2:
            raise CorrectionError(f"{path}: coefficients must be a 7x2 matrix")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in row):
            raise CorrectionError(f"{path}: coefficients must be finite numbers")

    strength = calibration.get("strength")
    if not isinstance(strength, (int, float)) or not 0.0 <= strength <= 1.0:
        raise CorrectionError(f"{path}: strength must be in [0, 1]")

    source_hashes = calibration.get("source_lut_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise CorrectionError(f"{path}: source_lut_sha256 must be a non-empty object")
    for key, digest in source_hashes.items():
        if not isinstance(key, str) or not key.startswith("Conversion/"):
            raise CorrectionError(f"{path}: invalid source LUT key {key!r}")
        if not isinstance(digest, str) or len(digest) != 64:
            raise CorrectionError(f"{path}: invalid source hash for {key}")

    corrected_hashes = calibration.get("corrected_lut_sha256")
    if not isinstance(corrected_hashes, dict) or set(corrected_hashes) != set(source_hashes):
        raise CorrectionError(f"{path}: corrected_lut_sha256 must cover every source LUT")
    for key, digest in corrected_hashes.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise CorrectionError(f"{path}: invalid corrected hash for {key}")
    return calibration


def opponent_features(rgb: Sequence[float]) -> tuple[float, ...]:
    red, green, blue = (float(value) for value in rgb)
    y = (red + green + blue) / 3.0
    c1 = red - green
    c2 = blue - green
    return (c1, c2, y * c1, y * c2, c1 * c1, c1 * c2, c2 * c2)


def correct_rgb(
    rgb: Sequence[float],
    coefficients: Sequence[Sequence[float]],
    strength: float,
) -> tuple[float, float, float]:
    red, green, blue = (float(value) for value in rgb)
    y = (red + green + blue) / 3.0
    c1 = red - green
    c2 = blue - green
    features = opponent_features(rgb)
    fitted_c1 = sum(feature * row[0] for feature, row in zip(features, coefficients))
    fitted_c2 = sum(feature * row[1] for feature, row in zip(features, coefficients))
    corrected_c1 = c1 + strength * (fitted_c1 - c1)
    corrected_c2 = c2 + strength * (fitted_c2 - c2)

    corrected_green = y - (corrected_c1 + corrected_c2) / 3.0
    corrected = (
        corrected_green + corrected_c1,
        corrected_green,
        corrected_green + corrected_c2,
    )
    return tuple(min(1.0, max(0.0, value)) for value in corrected)


def numeric_row(line: str) -> tuple[float, float, float] | None:
    content = line.split("#", 1)[0].strip()
    fields = content.split()
    if len(fields) != 3:
        return None
    try:
        values = tuple(float(field) for field in fields)
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in values):
        raise CorrectionError("LUT contains NaN or infinity")
    return values  # type: ignore[return-value]


def corrected_text(source: str, calibration: dict[str, object]) -> tuple[str, dict[str, object]]:
    lines = source.splitlines()
    if any(CORRECTION_MARKER in line for line in lines):
        raise CorrectionError("The shared output correction is already present")
    if len(lines) < 2 or not lines[0].startswith("TITLE "):
        raise CorrectionError("The input LUT must start with TITLE")
    if lines[1].strip() != "#LUMIXPHOTOSTYLE STD":
        raise CorrectionError("#LUMIXPHOTOSTYLE STD must immediately follow TITLE")

    size = None
    for line in lines:
        fields = line.split()
        if fields and fields[0].upper() == "LUT_3D_SIZE":
            if len(fields) != 2:
                raise CorrectionError("invalid LUT_3D_SIZE")
            size = int(fields[1])
            break
    if size is None:
        raise CorrectionError("missing LUT_3D_SIZE")

    coefficients = calibration["coefficients"]
    strength = float(calibration["strength"])
    output_lines: list[str] = []
    row_count = 0
    input_min = [math.inf, math.inf, math.inf]
    input_max = [-math.inf, -math.inf, -math.inf]
    output_min = [math.inf, math.inf, math.inf]
    output_max = [-math.inf, -math.inf, -math.inf]
    clipped_channel_count = 0
    max_mean_change = 0.0
    max_neutral_spread = 0.0

    for index, line in enumerate(lines):
        if index == 2:
            output_lines.extend(
                (
                    CORRECTION_MARKER,
                    "# Shared measured V-Log endpoint correction; exact neutral RGB is unchanged.",
                    CALIBRATION_REFERENCE,
                )
            )
        values = numeric_row(line)
        if values is None:
            output_lines.append(line)
            continue

        corrected = correct_rgb(values, coefficients, strength)  # type: ignore[arg-type]
        row_count += 1
        for channel in range(3):
            input_min[channel] = min(input_min[channel], values[channel])
            input_max[channel] = max(input_max[channel], values[channel])
            output_min[channel] = min(output_min[channel], corrected[channel])
            output_max[channel] = max(output_max[channel], corrected[channel])

        input_mean = sum(values) / 3.0
        output_mean = sum(corrected) / 3.0
        max_mean_change = max(max_mean_change, abs(output_mean - input_mean))
        if max(values) - min(values) <= 1e-12:
            max_neutral_spread = max(max_neutral_spread, max(corrected) - min(corrected))

        features = opponent_features(values)
        fitted_c1 = sum(
            feature * row[0] for feature, row in zip(features, coefficients)  # type: ignore[index]
        )
        fitted_c2 = sum(
            feature * row[1] for feature, row in zip(features, coefficients)  # type: ignore[index]
        )
        c1 = values[0] - values[1]
        c2 = values[2] - values[1]
        mixed_c1 = c1 + strength * (fitted_c1 - c1)
        mixed_c2 = c2 + strength * (fitted_c2 - c2)
        raw_green = input_mean - (mixed_c1 + mixed_c2) / 3.0
        raw_corrected = (raw_green + mixed_c1, raw_green, raw_green + mixed_c2)
        clipped_channel_count += sum(value < 0.0 or value > 1.0 for value in raw_corrected)
        output_lines.append(" ".join(f"{value:.10f}" for value in corrected))

    expected_rows = size**3
    if row_count != expected_rows:
        raise CorrectionError(f"expected {expected_rows} LUT rows, found {row_count}")
    report = {
        "grid_size": size,
        "row_count": row_count,
        "strength": strength,
        "input_min": input_min,
        "input_max": input_max,
        "output_min": output_min,
        "output_max": output_max,
        "clipped_channel_count": clipped_channel_count,
        "clipped_channel_fraction": clipped_channel_count / (row_count * 3),
        "max_mean_code_change_after_output_clipping": max_mean_change,
        "max_neutral_output_spread": max_neutral_spread,
    }
    return "\n".join(output_lines) + "\n", report


def source_key_for(path: Path, calibration: dict[str, object]) -> str:
    source_hashes = calibration["source_lut_sha256"]
    matches = [key for key in source_hashes if Path(key).name == path.name]  # type: ignore[union-attr]
    if len(matches) != 1:
        raise CorrectionError(f"No unique calibration source entry for {path.name}")
    return matches[0]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_correction(
    input_path: Path,
    output_path: Path,
    calibration_path: Path,
    source_key: str | None = None,
) -> dict[str, object]:
    calibration = load_calibration(calibration_path)
    try:
        source = input_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise CorrectionError(f"Could not read source LUT {input_path}: {exc}") from exc

    key = source_key or source_key_for(input_path, calibration)
    source_hashes = calibration["source_lut_sha256"]
    if key not in source_hashes:  # type: ignore[operator]
        raise CorrectionError(f"Calibration does not declare {key}")
    actual_source_hash = canonical_lf_sha256(source)
    corrected_hashes = calibration["corrected_lut_sha256"]
    if actual_source_hash == corrected_hashes[key]:  # type: ignore[index]
        if source.count(CORRECTION_MARKER) != 1:
            raise CorrectionError(f"{key} matches the corrected hash but has an invalid marker")
        if input_path.resolve() != output_path.resolve():
            write_atomic(output_path, source.replace("\r\n", "\n").replace("\r", "\n"))
        return {
            "status": "already_corrected",
            "source_key": key,
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "calibration": str(calibration_path.resolve()),
            "output_sha256": actual_source_hash,
        }
    expected_source_hash = source_hashes[key]  # type: ignore[index]
    if actual_source_hash != expected_source_hash:
        raise CorrectionError(
            f"{key} canonical SHA-256 mismatch: expected {expected_source_hash}, "
            f"got {actual_source_hash}. Use the uncorrected source and do not apply twice."
        )

    output, report = corrected_text(source, calibration)
    write_atomic(output_path, output)
    report.update(
        {
            "status": "corrected",
            "source_key": key,
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "calibration": str(calibration_path.resolve()),
            "source_sha256": actual_source_hash,
            "output_sha256": canonical_lf_sha256(output),
        }
    )
    return report


def apply_all(
    input_root: Path,
    output_root: Path,
    calibration_path: Path,
) -> list[dict[str, object]]:
    calibration = load_calibration(calibration_path)
    source_hashes = calibration["source_lut_sha256"]
    reports = []
    for key in source_hashes:  # type: ignore[union-attr]
        reports.append(
            apply_correction(input_root / key, output_root / key, calibration_path, key)
        )
    return reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="correct every declared adapter")
    mode.add_argument("--input", type=Path, help="one uncorrected input cube")
    parser.add_argument("--output", type=Path, help="single output cube; defaults to --input")
    parser.add_argument("--source-key", help="calibration key for a renamed single input")
    parser.add_argument("--input-root", type=Path, default=PACKAGE_ROOT)
    parser.add_argument("--output-root", type=Path, default=PACKAGE_ROOT)
    parser.add_argument("--report", type=Path, help="optional JSON transformation report")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    calibration_path = args.calibration.resolve()
    if args.all:
        result: object = apply_all(
            args.input_root.resolve(), args.output_root.resolve(), calibration_path
        )
    else:
        input_path = args.input.resolve()
        output_path = args.output.resolve() if args.output else input_path
        result = apply_correction(
            input_path, output_path, calibration_path, args.source_key
        )
    serialized = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
