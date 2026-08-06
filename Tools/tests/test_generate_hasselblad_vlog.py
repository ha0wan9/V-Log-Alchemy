import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPOSITORY_ROOT / "Tools" / "generate_hasselblad_vlog.py"
SPEC = importlib.util.spec_from_file_location("generate_hasselblad_vlog", GENERATOR_PATH)
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def numeric_rows(path):
    rows = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            rows.append(tuple(float(field) for field in fields))
        except ValueError:
            continue
    return rows


class HasselbladGeneratorTests(unittest.TestCase):
    def test_bundled_manifest_and_hashes_are_valid(self):
        artifact_path, artifact = GENERATOR.load_artifact(GENERATOR.DEFAULT_ARTIFACT)
        for name in (
            "daylight_color_correct_lut",
            "standard_film_curve",
            "nature_gradation",
        ):
            asset_path, _ = GENERATOR.resolve_asset(artifact_path, artifact, name)
            self.assertTrue(asset_path.is_file())

    def test_published_lut_checksums_are_complete_and_valid(self):
        lut_dir = REPOSITORY_ROOT / "Luts" / "Hasselblad"
        checksum_path = lut_dir / "SHA256SUMS.txt"
        declared = {}
        for line in checksum_path.read_text(encoding="ascii").splitlines():
            digest, filename = line.split(maxsplit=1)
            declared[filename] = digest
        published = {path.name for path in lut_dir.glob("*.cube")}
        self.assertEqual(set(declared), published)
        for filename, expected in declared.items():
            actual = hashlib.sha256((lut_dir / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)

    def test_display_transfer_reference_points(self):
        self.assertEqual(GENERATOR.encode_rec709(0.0), 0.0)
        self.assertAlmostEqual(GENERATOR.encode_rec709(0.018), 0.081, places=12)
        self.assertAlmostEqual(GENERATOR.encode_rec709(1.0), 1.0, places=12)
        self.assertEqual(GENERATOR.encode_srgb(0.0), 0.0)
        self.assertAlmostEqual(GENERATOR.encode_srgb(1.0), 1.0, places=12)

    def test_neutral_hasselblad_rgb_stays_neutral_in_display_spaces(self):
        _, artifact = GENERATOR.load_artifact(GENERATOR.DEFAULT_ARTIFACT)
        working_space = artifact["working_space"]
        matrix = GENERATOR.build_hasselblad_to_display_matrix(working_space)
        for output_space in ("rec709", "srgb"):
            for value in (0.0, 0.18, 0.5, 1.0):
                converted = GENERATOR.convert_output_space(
                    [value, value, value], output_space, working_space, matrix
                )
                self.assertLess(max(converted) - min(converted), 0.0005)

    def test_output_names_expose_nonlegacy_colour_space(self):
        output_dir = Path("output")
        self.assertEqual(
            GENERATOR.output_path_for_style(output_dir, "Standard", 33, "hasselblad-rgb").name,
            "Hasselblad_Standard_Phocus_X2D_VLog_HassRGBD50.cube",
        )
        self.assertEqual(
            GENERATOR.output_path_for_style(output_dir, "Nature", 65, "rec709").name,
            "Hasselblad_Nature_Phocus_X2D_VLog_Rec709_65.cube",
        )
        self.assertEqual(
            GENERATOR.output_path_for_style(output_dir, "Nature", 33, "srgb").name,
            "Hasselblad_Nature_Phocus_X2D_VLog_sRGB.cube",
        )

    def test_default_cli_output_is_rec709_complete_and_bounded(self):
        with tempfile.TemporaryDirectory(prefix="hasselblad-generator-test-") as temp_dir:
            output = Path(temp_dir) / "test.cube"
            subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR_PATH),
                    "--style",
                    "Nature",
                    "--size",
                    "2",
                    "--include-color-correct",
                    "--highlight-rolloff",
                    "--output",
                    str(output),
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            text = output.read_text(encoding="ascii")
            self.assertIn("# OUTPUT_COLORSPACE Rec.709 primaries / D65 / BT.709 OETF", text)
            rows = numeric_rows(output)
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(0.0 <= value <= 1.0 for row in rows for value in row))

    def test_published_display_luts_are_numerically_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="hasselblad-reproduction-test-") as temp_dir:
            for output_space, suffix, description in (
                ("rec709", "Rec709", "Rec.709 primaries / D65 / BT.709 OETF"),
                ("srgb", "sRGB", "sRGB primaries / D65 / sRGB transfer function"),
            ):
                for style in ("Standard", "Nature"):
                    output = Path(temp_dir) / f"{style}-{output_space}.cube"
                    subprocess.run(
                        [
                            sys.executable,
                            str(GENERATOR_PATH),
                            "--style",
                            style,
                            "--size",
                            "33",
                            "--include-color-correct",
                            "--highlight-rolloff",
                            "--output-space",
                            output_space,
                            "--output",
                            str(output),
                        ],
                        cwd=REPOSITORY_ROOT,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    published = (
                        REPOSITORY_ROOT
                        / "Luts"
                        / "Hasselblad"
                        / f"Hasselblad_{style}_Phocus_X2D_VLog_{suffix}.cube"
                    )
                    self.assertIn(f"# OUTPUT_COLORSPACE {description}", published.read_text(encoding="ascii"))
                    self.assertEqual(numeric_rows(output), numeric_rows(published))


if __name__ == "__main__":
    unittest.main()
