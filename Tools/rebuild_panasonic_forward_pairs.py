#!/usr/bin/env python3
"""Rebuild all Panasonic Standard -> V-Log adapters by global forward-pair fitting.

The v1.3 conversion cubes are used only as weak priors in sparsely covered
corners.  Each camera group keeps its own decoded SILKYPIX Standard and V-Log
forward maps, while controlled S1RII pairs constrain their common fixed
Panasonic V-Log/V-Gamut endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from fit_panasonic_forward_pairs import read_cube


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_ROOT = REPOSITORY_ROOT / "Luts" / "Panasonic-Standard"
DEFAULT_ANCHORS = DEFAULT_PACKAGE_ROOT / "Calibration" / "PanasonicForwardPairAnchors.npz"
FIT_TOOL = Path(__file__).resolve().with_name("fit_panasonic_forward_pairs.py")


@dataclass(frozen=True)
class ModelBuild:
    group: str
    filename: str
    title: str
    main_suffix: int
    shadow_suffix: int
    vlog_domain: float
    models: tuple[str, ...]
    camera_recording: bool = True
    dual_lut_min_firmware: str | None = None


BUILDS = (
    ModelBuild("L001", "GH6S2V.cube", "GH6 Standard to V-Log", 27, 31, 2.0, ("GH6",), False),
    ModelBuild(
        "L002",
        "S5IIS2V.cube",
        "S5II Standard to V-Log",
        27,
        31,
        7.1,
        ("S5II", "DC-S5M2"),
        dual_lut_min_firmware="3.1",
    ),
    ModelBuild(
        "L002",
        "S5IIXS2V.cube",
        "S5IIX Standard to V-Log",
        27,
        31,
        7.1,
        ("S5IIX", "DC-S5M2X"),
        dual_lut_min_firmware="2.1",
    ),
    ModelBuild(
        "L003",
        "G9IIS2V.cube",
        "G9II Standard to V-Log",
        27,
        31,
        4.0,
        ("G9II", "DC-G9M2"),
        dual_lut_min_firmware="2.2",
    ),
    ModelBuild("L004", "GH7S2V.cube", "GH7 Standard to V-Log", 27, 31, 4.0, ("GH7", "DC-GH7")),
    ModelBuild("L005", "S9S2V.cube", "S9 Standard to V-Log", 27, 31, 7.1, ("S9", "DC-S9")),
    ModelBuild(
        "L006",
        "S1IIES2V.cube",
        "S1IIE Standard to V-Log",
        29,
        33,
        7.0,
        ("S1IIE", "DC-S1M2ES"),
    ),
    ModelBuild(
        "L007",
        "S1RIIS2V.cube",
        "S1RII Standard to V-Log",
        29,
        33,
        2.8,
        ("S1RII", "DC-S1RM2"),
    ),
    ModelBuild("L008", "S1IIS2V.cube", "S1II Standard to V-Log", 29, 33, 8.0, ("S1II", "DC-S1M2")),
    ModelBuild("L009", "L10S2V.cube", "DC-L10 Standard to V-Log", 33, 37, 4.0, ("DC-L10", "L10")),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_lf_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="ascii")
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def map_path(decoded_root: Path, group: str, suffix: int) -> Path:
    directory = "decoded_math" if group == "L001" and suffix in (2, 28, 32) else f"decoded_{group}"
    return decoded_root / directory / f"{group}{suffix:02d}.rgb16"


def prior_path(prior_root: Path, filename: str) -> Path:
    direct = prior_root / filename
    nested = prior_root / "Conversion" / filename
    if direct.is_file():
        return direct
    if nested.is_file():
        return nested
    raise FileNotFoundError(f"v1.3 prior not found: {nested}")


def validate_inputs(decoded_root: Path, prior_root: Path, anchors: Path) -> None:
    if not FIT_TOOL.is_file():
        raise FileNotFoundError(FIT_TOOL)
    if not anchors.is_file():
        raise FileNotFoundError(anchors)
    for model in BUILDS:
        paths = (
            map_path(decoded_root, model.group, 1),
            map_path(decoded_root, model.group, 2),
            map_path(decoded_root, model.group, model.main_suffix),
            map_path(decoded_root, model.group, model.main_suffix + 1),
            map_path(decoded_root, model.group, model.shadow_suffix),
            map_path(decoded_root, model.group, model.shadow_suffix + 1),
            prior_path(prior_root, model.filename),
        )
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(path)


def fit_model(args: argparse.Namespace, model: ModelBuild) -> None:
    output = args.package_root / "Conversion" / model.filename
    report = args.package_root / "Reports" / f"{output.stem}.json"
    prior = prior_path(args.prior_root, model.filename)
    command = [
        sys.executable,
        str(FIT_TOOL),
        str(map_path(args.decoded_root, model.group, 1)),
        str(map_path(args.decoded_root, model.group, model.main_suffix)),
        str(output),
        "--title",
        model.title,
        "--standard-domain-max",
        "1",
        "--vlog-domain-max",
        f"{model.vlog_domain:g}",
        "--standard-map-b",
        str(map_path(args.decoded_root, model.group, 2)),
        "--vlog-map-b",
        str(map_path(args.decoded_root, model.group, model.main_suffix + 1)),
        "--vlog-shadow-map",
        str(map_path(args.decoded_root, model.group, model.shadow_suffix)),
        "--vlog-shadow-map-b",
        str(map_path(args.decoded_root, model.group, model.shadow_suffix + 1)),
        "--vlog-shadow-domain-max",
        f"{model.vlog_domain / 64.0:.10g}",
        "--pair-blend",
        "0.5",
        "--prior-cube",
        str(prior),
        "--anchor-npz",
        str(args.anchor_npz),
        "--anchor-weight-scale",
        f"{args.anchor_weight_scale:g}",
        "--size",
        str(args.solve_size),
        "--output-size",
        "33",
        "--samples",
        str(args.samples),
        "--uniform-fraction",
        f"{args.uniform_fraction:g}",
        "--neutral-weight",
        f"{args.neutral_weight:g}",
        "--smoothness",
        f"{args.smoothness:g}",
        "--prior-weight",
        f"{args.prior_weight:g}",
        "--prior-coverage-scale",
        f"{args.prior_coverage_scale:g}",
        "--cg-iterations",
        str(args.cg_iterations),
        "--cg-tolerance",
        f"{args.cg_tolerance:g}",
        "--validation-samples",
        str(args.validation_samples),
        "--random-seed",
        str(args.random_seed),
        "--report",
        str(report),
    ]
    print(f"Fitting {model.filename} from {model.group} forward maps...", flush=True)
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True, stdout=subprocess.DEVNULL)
    sanitize_report(report, model, args)


def sanitize_report(path: Path, model: ModelBuild, args: argparse.Namespace) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "standard_map",
        "vlog_map",
        "standard_map_b",
        "vlog_map_b",
        "vlog_shadow_map",
        "vlog_shadow_map_b",
    ):
        value = report.get(key)
        if value:
            report[key] = f"decoded/{Path(value).name}"
    report["output_cube"] = f"Conversion/{model.filename}"
    report["prior_cube"] = f"v1.3/Conversion/{model.filename}"
    for anchor in report.get("camera_pair_anchors", []):
        anchor["path"] = "Calibration/PanasonicForwardPairAnchors.npz"
    report["release_fit"] = {
        "package_version": args.package_version,
        "training_camera": "DC-S1RM2 firmware 1.5",
        "endpoint": "fixed Panasonic V-Log/V-Gamut",
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_cube(path: Path) -> None:
    basename = path.stem
    if len(basename) > 8 or not re.fullmatch(r"[A-Za-z0-9]+", basename):
        raise ValueError(f"not FAT32-safe: {path.name}")
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 6 or lines[1] != "#LUMIXPHOTOSTYLE STD":
        raise ValueError(f"invalid LUMIX header: {path}")
    if not any("Globally fitted from paired decoded" in line for line in lines[:10]):
        raise ValueError(f"missing global-fit provenance: {path}")
    lut = read_cube(path)
    if lut.size != 33 or not np.all(np.isfinite(lut.data)):
        raise ValueError(f"invalid 33-point cube: {path}")
    if float(np.min(lut.data)) < 0.0 or float(np.max(lut.data)) > 1.0:
        raise ValueError(f"out-of-range cube: {path}")
    diagonal = lut.data[np.arange(33), np.arange(33), np.arange(33)]
    if float(np.max(np.ptp(diagonal, axis=1))) > 1e-9:
        raise ValueError(f"neutral axis is not exact: {path}")


def validation_status(model: ModelBuild) -> dict[str, object]:
    if model.group == "L007":
        return {
            "status": "controlled_quantitative",
            "camera": "DC-S1RM2",
            "firmware": "1.5",
            "report": "Calibration/S1RIIControlledValidation.json",
        }
    if model.group == "L005":
        return {
            "status": "qualitative_field_report",
            "issue": "https://github.com/shenmintao/V-Log-Alchemy/issues/12",
        }
    return {"status": "fixed_endpoint_extrapolation", "controlled_model_pair_pending": True}


def write_controlled_validation(source: Path | None, package_root: Path) -> str | None:
    if source is None:
        return None
    data = json.loads(source.read_text(encoding="utf-8"))
    data["candidate"] = "Conversion/S1RIIS2V.cube"
    data["name"] = "v1.6 global forward-pair fit"
    output = package_root / "Calibration" / "S1RIIControlledValidation.json"
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(output.relative_to(package_root)).replace("\\", "/")


def finalize_package(args: argparse.Namespace) -> None:
    source_hashes: dict[str, str] = {}
    output_hashes: dict[str, str] = {}
    checksum_lines: list[str] = []
    entries: list[dict[str, object]] = []
    forward_validation: dict[str, object] = {}
    controlled_report = write_controlled_validation(args.controlled_comparison, args.package_root)

    for model in BUILDS:
        relative = f"Conversion/{model.filename}"
        cube_path = args.package_root / relative
        report_path = args.package_root / "Reports" / f"{cube_path.stem}.json"
        validate_cube(cube_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        solvers = report["fit"]["channel_solvers"]
        if not all(channel["converged"] for channel in solvers):
            raise ValueError(f"global solver did not converge for {model.filename}")
        lut = read_cube(cube_path)
        digest = sha256(cube_path)
        source_hashes[relative] = canonical_lf_text_sha256(
            prior_path(args.prior_root, model.filename)
        )
        output_hashes[relative] = digest
        checksum_lines.append(f"{digest}  {relative}")
        neutral = lut.sample(np.repeat(np.asarray((0.0, 0.45, 1.0))[:, None], 3, axis=1)).mean(axis=1)
        status = validation_status(model)
        if model.group == "L007" and controlled_report:
            status["report"] = controlled_report
        validation = report["validation"]
        anchor_report = report["camera_pair_anchors"][0]
        forward_validation[model.filename] = {
            "synthetic_rgb_error": validation["rgb_error"],
            "correlated_rgb_error": validation.get("correlated_rgb_error"),
            "camera_anchor_rgb_error": anchor_report["rgb_error"],
        }
        entries.append(
            {
                "group": model.group,
                "models": list(model.models),
                "path": relative,
                "title": lut.title,
                "sha256": digest,
                "grid_size": 33,
                "lumix_photo_style": "STD",
                "range": "full_0_1",
                "camera_recording": model.camera_recording,
                "dual_lut_min_firmware": model.dual_lut_min_firmware,
                "vlog_domain_max": model.vlog_domain,
                "shadow_domain_max": model.vlog_domain / 64.0,
                "pair_blend": 0.5,
                "forward_interpolation": "trilinear",
                "fit_method": "global_forward_pair_regression",
                "solve_grid_size": args.solve_size,
                "neutral_axis_enforced": True,
                "output_min": float(np.min(lut.data)),
                "output_max": float(np.max(lut.data)),
                "neutral_black": float(neutral[0]),
                "standard_0_45_to_vlog": float(neutral[1]),
                "neutral_white": float(neutral[2]),
                "validation_samples": report["validation"]["sample_count"],
                "in_camera_tested": model.group in ("L005", "L007"),
                "global_fit_calibration": "Calibration/PanasonicForwardPairGlobalFit.json",
                "validation": status,
            }
        )

    anchor_metadata_path = args.anchor_npz.with_suffix(".json")
    anchor_metadata = (
        json.loads(anchor_metadata_path.read_text(encoding="utf-8"))
        if anchor_metadata_path.is_file()
        else None
    )
    calibration = {
        "schema_version": 1,
        "package_version": args.package_version,
        "method": "global regularized forward-pair regression; no pointwise Standard inverse or empirical output colour patch",
        "endpoint": "fixed Panasonic V-Log/V-Gamut",
        "training_camera": "DC-S1RM2 firmware 1.5",
        "fit_parameters": {
            "samples": args.samples,
            "validation_samples": args.validation_samples,
            "uniform_fraction": args.uniform_fraction,
            "solve_size": args.solve_size,
            "output_size": 33,
            "neutral_samples": 4097,
            "neutral_weight": args.neutral_weight,
            "smoothness": args.smoothness,
            "prior_weight": args.prior_weight,
            "prior_coverage_scale": args.prior_coverage_scale,
            "anchor_weight_scale": args.anchor_weight_scale,
            "cg_iterations": args.cg_iterations,
            "cg_tolerance": args.cg_tolerance,
            "random_seed": args.random_seed,
        },
        "anchor_artifact": {
            "path": "Calibration/PanasonicForwardPairAnchors.npz",
            "sha256": sha256(args.anchor_npz),
            "metadata": anchor_metadata,
        },
        "v1.3_prior_lut_sha256": source_hashes,
        "fitted_lut_sha256": output_hashes,
        "forward_pair_validation": forward_validation,
        "controlled_validation": controlled_report,
        "limitations": [
            "Standard clipping and gamut compression are many-to-one and cannot be exactly inverted.",
            "The fitted value in ambiguous regions depends on the source and camera-anchor distributions.",
            "Controlled quantitative validation is currently limited to DC-S1RM2/S1RII firmware 1.5.",
            "An output LUT cannot reproduce native V-Log acquisition gain, noise, or highlight headroom.",
        ],
    }
    calibration_path = args.package_root / "Calibration" / "PanasonicForwardPairGlobalFit.json"
    calibration_path.write_text(json.dumps(calibration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "package": "V-Log-Alchemy Panasonic Standard Input",
        "package_version": args.package_version,
        "silkypix_version": "8.0.30.4",
        "algorithm": "global regularized regression over paired model-specific Standard/V-Log forward maps with shared controlled-camera endpoint constraints",
        "limitations": calibration["limitations"],
        "global_fit": {
            "calibration": "Calibration/PanasonicForwardPairGlobalFit.json",
            "prior": "content-exact v1.3 conversion LUTs with canonical-LF hashes, weakly gated to sparsely covered nodes",
            "scope": "all published Standard-input adapters",
            "target": "fixed Panasonic V-Log/V-Gamut endpoint",
            "training_camera": "DC-S1RM2 firmware 1.5",
        },
        "luts": entries,
    }
    (args.package_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.package_root / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="ascii"
    )
    print(f"Validated and finalized {len(entries)} Panasonic adapters for v{args.package_version}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoded-root", type=Path, required=True, help="SILKYPIX analysis root containing decoded_L001 ... decoded_L009")
    parser.add_argument("--prior-root", type=Path, required=True, help="v1.3 Panasonic package or Conversion directory")
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_ROOT)
    parser.add_argument("--anchor-npz", type=Path, default=DEFAULT_ANCHORS)
    parser.add_argument("--controlled-comparison", type=Path)
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="validate existing fitted cubes/reports and regenerate package metadata without fitting",
    )
    parser.add_argument("--package-version", default="1.6")
    parser.add_argument("--samples", type=int, default=300000)
    parser.add_argument("--validation-samples", type=int, default=20000)
    parser.add_argument("--uniform-fraction", type=float, default=0.0)
    parser.add_argument("--solve-size", type=int, default=9)
    parser.add_argument("--neutral-weight", type=float, default=20.0)
    parser.add_argument("--smoothness", type=float, default=0.01)
    parser.add_argument("--prior-weight", type=float, default=1.0)
    parser.add_argument("--prior-coverage-scale", type=float, default=0.01)
    parser.add_argument("--anchor-weight-scale", type=float, default=100.0)
    parser.add_argument("--cg-iterations", type=int, default=1000)
    parser.add_argument("--cg-tolerance", type=float, default=1e-7)
    parser.add_argument("--random-seed", type=int, default=20260817)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validate_inputs(args.decoded_root, args.prior_root, args.anchor_npz)
    (args.package_root / "Conversion").mkdir(parents=True, exist_ok=True)
    (args.package_root / "Reports").mkdir(parents=True, exist_ok=True)
    (args.package_root / "Calibration").mkdir(parents=True, exist_ok=True)
    if not args.finalize_only:
        for model in BUILDS:
            fit_model(args, model)
    finalize_package(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
