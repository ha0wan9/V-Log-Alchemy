from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


TOOL_PATH = Path(__file__).resolve().parents[1] / "fit_panasonic_forward_pairs.py"
SPEC = importlib.util.spec_from_file_location("fit_panasonic_forward_pairs", TOOL_PATH)
assert SPEC and SPEC.loader
TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOOL
SPEC.loader.exec_module(TOOL)


class ForwardPairFitTests(unittest.TestCase):
    def test_design_matches_cube_trilinear_sampler(self) -> None:
        rng = np.random.default_rng(11)
        size = 5
        data = rng.random((size, size, size, 3))
        cube = TOOL.CubeLUT("random", data, np.zeros(3), np.ones(3))
        points = rng.random((250, 3))
        design = TOOL.trilinear_design(points, size)
        flat = data.reshape(-1, 3)
        predicted = np.stack(
            [design.predict(flat[:, channel]) for channel in range(3)], axis=1
        )
        np.testing.assert_allclose(predicted, cube.sample(points), atol=1e-12, rtol=0.0)

    def test_curvature_operator_annihilates_affine_grid(self) -> None:
        size = 7
        axis = np.linspace(0.0, 1.0, size)
        rr, gg, bb = np.meshgrid(axis, axis, axis, indexing="ij")
        affine = 0.2 + 0.3 * rr - 0.1 * gg + 0.5 * bb
        result = TOOL.curvature_normal(affine.reshape(-1), size)
        np.testing.assert_allclose(result, 0.0, atol=1e-13, rtol=0.0)

    def test_global_solver_recovers_affine_mapping(self) -> None:
        rng = np.random.default_rng(13)
        size = 7
        points = rng.random((18000, 3))
        matrix = np.asarray(
            [
                [0.72, 0.08, 0.03],
                [0.04, 0.81, 0.06],
                [0.02, 0.11, 0.70],
            ]
        )
        offset = np.asarray([0.03, 0.02, 0.04])
        targets = points @ matrix.T + offset
        design = TOOL.trilinear_design(points, size)
        axis = np.linspace(0.0, 1.0, size)
        rr, gg, bb = np.meshgrid(axis, axis, axis, indexing="ij")
        grid = np.stack((rr, gg, bb), axis=-1)
        prior = TOOL.CubeLUT("identity", grid, np.zeros(3), np.ones(3))
        fitted, report = TOOL.fit_global_cube(
            design,
            targets,
            prior,
            smoothness=0.001,
            prior_weight=1e-8,
            prior_coverage_scale=0.0,
            cg_iterations=80,
            cg_tolerance=1e-9,
            title="test",
        )
        validation = rng.random((1000, 3))
        expected = validation @ matrix.T + offset
        error = np.max(np.abs(fitted.sample(validation) - expected))
        self.assertLess(error, 2e-5)
        self.assertTrue(all(channel["converged"] for channel in report["channel_solvers"]))

    def test_validation_supports_single_sample_component(self) -> None:
        grid = np.linspace(0.0, 1.0, 3)
        rr, gg, bb = np.meshgrid(grid, grid, grid, indexing="ij")
        data = np.stack((rr, gg, bb), axis=-1)
        identity = TOOL.CubeLUT("identity", data, np.zeros(3), np.ones(3))

        correlated_only = TOOL.validate_pipeline(
            identity,
            identity,
            identity,
            sample_count=100,
            uniform_fraction=0.0,
            seed=123,
            batch_size=64,
        )
        uniform_only = TOOL.validate_pipeline(
            identity,
            identity,
            identity,
            sample_count=100,
            uniform_fraction=1.0,
            seed=123,
            batch_size=64,
        )

        self.assertNotIn("uniform_rgb_error", correlated_only)
        self.assertIn("correlated_rgb_error", correlated_only)
        self.assertIn("uniform_rgb_error", uniform_only)
        self.assertNotIn("correlated_rgb_error", uniform_only)


if __name__ == "__main__":
    unittest.main()
