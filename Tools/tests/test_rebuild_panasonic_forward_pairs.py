from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "Tools"
sys.path.insert(0, str(TOOLS_ROOT))
TOOL_PATH = TOOLS_ROOT / "rebuild_panasonic_forward_pairs.py"
SPEC = importlib.util.spec_from_file_location("rebuild_panasonic_forward_pairs", TOOL_PATH)
assert SPEC and SPEC.loader
TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOOL
SPEC.loader.exec_module(TOOL)


class PanasonicForwardPairReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = REPOSITORY_ROOT / "Luts" / "Panasonic-Standard"
        cls.manifest = json.loads((cls.package / "manifest.json").read_text(encoding="utf-8"))
        cls.calibration = json.loads(
            (cls.package / "Calibration" / "PanasonicForwardPairGlobalFit.json").read_text(
                encoding="utf-8"
            )
        )

    def test_manifest_calibration_and_hashes_are_consistent(self) -> None:
        self.assertEqual(self.manifest["package_version"], "1.6")
        self.assertIn("global regularized regression", self.manifest["algorithm"])
        self.assertEqual(self.calibration["package_version"], "1.6")
        manifest_hashes = {entry["path"]: entry["sha256"] for entry in self.manifest["luts"]}
        self.assertEqual(manifest_hashes, self.calibration["fitted_lut_sha256"])
        self.assertEqual(set(manifest_hashes), set(self.calibration["v1.3_prior_lut_sha256"]))
        self.assertEqual(len(manifest_hashes), 10)

        checksums = {}
        for line in (self.package / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
            digest, relative = line.split("  ", 1)
            checksums[relative] = digest
        self.assertEqual(checksums, manifest_hashes)
        for relative, expected in manifest_hashes.items():
            actual = hashlib.sha256((self.package / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_anchor_artifact_is_hash_locked_and_well_formed(self) -> None:
        artifact = self.package / "Calibration" / "PanasonicForwardPairAnchors.npz"
        actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertEqual(actual_hash, self.calibration["anchor_artifact"]["sha256"])
        metadata = json.loads(artifact.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(actual_hash, metadata["sha256"])
        with np.load(artifact) as archive:
            self.assertEqual(set(archive.files), {"standard", "target", "weight"})
            self.assertEqual(archive["standard"].shape, (20591, 3))
            self.assertEqual(archive["target"].shape, (20591, 3))
            self.assertEqual(archive["weight"].shape, (20591,))
            self.assertTrue(all(np.all(np.isfinite(archive[key])) for key in archive.files))
            self.assertTrue(np.all(archive["weight"] > 0.0))

    def test_every_adapter_is_camera_ready_and_has_exact_neutral_axis(self) -> None:
        for entry in self.manifest["luts"]:
            path = self.package / entry["path"]
            TOOL.validate_cube(path)
            lines = path.read_text(encoding="ascii").splitlines()
            self.assertEqual(lines[1], "#LUMIXPHOTOSTYLE STD")
            self.assertTrue(any("Globally fitted" in line for line in lines[:10]))
            self.assertFalse(
                any(line.startswith(("DOMAIN_MIN", "DOMAIN_MAX", "LUT_3D_INPUT_RANGE")) for line in lines)
            )
            self.assertLessEqual(len(path.stem), 8)

    def test_reports_use_v1_3_priors_and_all_solvers_converged(self) -> None:
        for model in TOOL.BUILDS:
            report_path = self.package / "Reports" / f"{Path(model.filename).stem}.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["method"],
                "global regularized forward-pair regression; no pointwise Standard inverse",
            )
            self.assertEqual(report["prior_cube"], f"v1.3/Conversion/{model.filename}")
            self.assertEqual(report["output_cube"], f"Conversion/{model.filename}")
            self.assertEqual(
                report["camera_pair_anchors"][0]["path"],
                "Calibration/PanasonicForwardPairAnchors.npz",
            )
            self.assertTrue(all(channel["converged"] for channel in report["fit"]["channel_solvers"]))
            self.assertLessEqual(
                max(channel["relative_residual_norm"] for channel in report["fit"]["channel_solvers"]),
                1e-7,
            )

    def test_controlled_s1rii_validation_beats_v1_5(self) -> None:
        path = self.package / self.calibration["controlled_validation"]
        variants = json.loads(path.read_text(encoding="utf-8"))["variants"]
        current = variants["candidate"]
        previous = variants["v1.5"]
        current_cyan = current["chart"]["all_exposures"]["cyan_R1C6_R3C6"]
        previous_cyan = previous["chart"]["all_exposures"]["cyan_R1C6_R3C6"]
        self.assertLess(current_cyan["vlog_mean_rgb"], previous_cyan["vlog_mean_rgb"])
        self.assertLess(current_cyan["classic_neg_mean_rgb"], previous_cyan["classic_neg_mean_rgb"])
        self.assertLess(
            current["hand_skin"]["aggregate"]["vlog_median_rgb_distance"],
            previous["hand_skin"]["aggregate"]["vlog_median_rgb_distance"],
        )
        self.assertLess(
            current["hand_skin"]["aggregate"]["classic_neg_median_rgb_distance"],
            previous["hand_skin"]["aggregate"]["classic_neg_median_rgb_distance"],
        )

    def test_published_s1rii_baked_examples_are_reproducible(self) -> None:
        import merge_standard_luts

        specifications = (
            (
                REPOSITORY_ROOT / "Luts" / "Fujifilm" / "FLog2C_to_CLASSIC-Neg_VLog.cube",
                "CNEGSTD",
            ),
            (
                REPOSITORY_ROOT / "Luts" / "Leica" / "L-Log_to_Classic_VLog.cube",
                "LEICASTD",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            for creative, name in specifications:
                generated = merge_standard_luts.merge_standard_luts(
                    "S1RII",
                    creative,
                    None,
                    directory,
                    name1=name,
                )[0]
                published = (
                    REPOSITORY_ROOT
                    / "Samples"
                    / "Panasonic-Standard"
                    / "Generated-LUTs"
                    / f"{name}.cube"
                )
                self.assertEqual(generated.read_bytes(), published.read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
