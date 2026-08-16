import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPOSITORY_ROOT / "Tools" / "apply_panasonic_vlog_output_correction.py"
SPEC = importlib.util.spec_from_file_location("apply_panasonic_vlog_output_correction", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class PanasonicVLogOutputCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_root = REPOSITORY_ROOT / "Luts" / "Panasonic-Standard"
        cls.calibration_path = cls.package_root / "Calibration" / "PanasonicVLogOutput.json"
        cls.calibration = TOOL.load_calibration(cls.calibration_path)
        cls.coefficients = cls.calibration["coefficients"]
        cls.strength = cls.calibration["strength"]

    def test_exact_neutral_axis_is_unchanged(self):
        for value in (0.0, 0.1250305325, 0.4227795256, 0.6778301256, 1.0):
            corrected = TOOL.correct_rgb(
                (value, value, value), self.coefficients, self.strength
            )
            self.assertEqual(corrected, (value, value, value))

    def test_mean_code_is_preserved_when_no_output_clips(self):
        samples = (
            (0.2, 0.3, 0.4),
            (0.45, 0.25, 0.15),
            (0.1, 0.4, 0.35),
            (0.55, 0.5, 0.3),
        )
        for sample in samples:
            corrected = TOOL.correct_rgb(sample, self.coefficients, self.strength)
            self.assertTrue(all(0.0 < value < 1.0 for value in corrected))
            self.assertAlmostEqual(sum(corrected), sum(sample), places=12)

    def test_cyan_low_red_is_lifted_without_a_hard_floor(self):
        sample = (0.02, 0.35, 0.38)
        corrected = TOOL.correct_rgb(sample, self.coefficients, self.strength)
        self.assertGreater(corrected[0], 0.125)
        self.assertGreater(corrected[1], corrected[0])
        self.assertGreater(corrected[2], corrected[0])
        self.assertAlmostEqual(sum(corrected), sum(sample), places=12)

    def test_every_published_adapter_has_marker_hash_grid_and_neutral_axis(self):
        manifest = json.loads((self.package_root / "manifest.json").read_text(encoding="utf-8"))
        manifest_hashes = {item["path"]: item["sha256"] for item in manifest["luts"]}
        corrected_hashes = self.calibration["corrected_lut_sha256"]
        self.assertEqual(set(manifest_hashes), set(self.calibration["source_lut_sha256"]))
        self.assertEqual(manifest_hashes, corrected_hashes)

        for relative_path, expected_hash in manifest_hashes.items():
            lut = self.package_root / relative_path
            text = lut.read_text(encoding="ascii")
            lines = text.splitlines()
            self.assertEqual(lines[1], "#LUMIXPHOTOSTYLE STD", relative_path)
            self.assertIn(TOOL.CORRECTION_MARKER, lines, relative_path)
            rows = [TOOL.numeric_row(line) for line in lines]
            rows = [row for row in rows if row is not None]
            self.assertEqual(len(rows), 33**3, relative_path)
            self.assertTrue(
                all(0.0 <= value <= 1.0 for row in rows for value in row), relative_path
            )
            digest = hashlib.sha256(text.replace("\r\n", "\n").encode("ascii")).hexdigest()
            self.assertEqual(digest, expected_hash, relative_path)
            for index in range(33):
                row = rows[(index * 33 + index) * 33 + index]
                self.assertLess(max(row) - min(row), 1e-10, relative_path)

    def test_double_application_is_rejected(self):
        lut = self.package_root / "Conversion" / "S9S2V.cube"
        with self.assertRaisesRegex(TOOL.CorrectionError, "already present"):
            TOOL.corrected_text(lut.read_text(encoding="ascii"), self.calibration)

    def test_all_mode_is_idempotent_on_published_outputs(self):
        reports = TOOL.apply_all(self.package_root, self.package_root, self.calibration_path)
        self.assertEqual(len(reports), 10)
        self.assertTrue(all(report["status"] == "already_corrected" for report in reports))


if __name__ == "__main__":
    unittest.main()
