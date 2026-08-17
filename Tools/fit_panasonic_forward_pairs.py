#!/usr/bin/env python3
"""Globally fit a Panasonic Standard -> V-Log LUT from paired forward maps.

This deliberately avoids pointwise inversion of the Standard forward map.
Instead, shared internal RGB samples are pushed through both decoded forward
maps and the complete output cube is solved in one regularized least-squares
problem::

    min_L sum_i w_i ||L(F_standard(x_i)) - F_vlog(x_i)||^2
          + smoothness * ||D2 L||^2
          + prior_weight * ||L - L_prior||^2

Trilinear playback makes the data term linear in the output cube nodes.  A
matrix-free conjugate-gradient solve keeps the implementation dependency-free
apart from NumPy.  The optional prior has negligible influence on supported
nodes and defines only unreachable/weakly supported corners.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class CubeLUT:
    title: str
    data: np.ndarray  # (R, G, B, output RGB)
    domain_min: np.ndarray
    domain_max: np.ndarray
    interpolation: str = "trilinear"

    @property
    def size(self) -> int:
        return int(self.data.shape[0])

    def sample(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64)
        original_shape = points.shape
        if original_shape[-1] != 3:
            raise ValueError("sample points must end in RGB")
        flat = points.reshape(-1, 3)
        span = self.domain_max - self.domain_min
        position = np.clip((flat - self.domain_min) / span, 0.0, 1.0) * (self.size - 1)
        lower = np.floor(position).astype(np.int64)
        upper = np.minimum(lower + 1, self.size - 1)
        fraction = position - lower
        r0, g0, b0 = lower.T
        r1, g1, b1 = upper.T
        fr, fg, fb = (fraction[:, axis, None] for axis in range(3))
        c000 = self.data[r0, g0, b0]
        c100 = self.data[r1, g0, b0]
        c010 = self.data[r0, g1, b0]
        c110 = self.data[r1, g1, b0]
        c001 = self.data[r0, g0, b1]
        c101 = self.data[r1, g0, b1]
        c011 = self.data[r0, g1, b1]
        c111 = self.data[r1, g1, b1]
        c00 = c000 * (1.0 - fr) + c100 * fr
        c10 = c010 * (1.0 - fr) + c110 * fr
        c01 = c001 * (1.0 - fr) + c101 * fr
        c11 = c011 * (1.0 - fr) + c111 * fr
        c0 = c00 * (1.0 - fg) + c10 * fg
        c1 = c01 * (1.0 - fg) + c11 * fg
        output = c0 * (1.0 - fb) + c1 * fb
        return output.reshape(original_shape)


@dataclass(frozen=True)
class BlendedLUT:
    first: CubeLUT
    second: CubeLUT
    mix: float

    @property
    def size(self) -> int:
        return self.first.size

    @property
    def domain_min(self) -> np.ndarray:
        return self.first.domain_min

    @property
    def domain_max(self) -> np.ndarray:
        return self.first.domain_max

    def sample(self, points: np.ndarray) -> np.ndarray:
        return (1.0 - self.mix) * self.first.sample(points) + self.mix * self.second.sample(points)


@dataclass(frozen=True)
class ShadowRefinedLUT:
    main: CubeLUT | BlendedLUT
    shadow: CubeLUT | BlendedLUT

    @property
    def size(self) -> int:
        return self.main.size

    @property
    def domain_min(self) -> np.ndarray:
        return self.main.domain_min

    @property
    def domain_max(self) -> np.ndarray:
        return self.main.domain_max

    def sample(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64)
        flat = points.reshape(-1, 3)
        output = self.main.sample(flat)
        use_shadow = np.all(
            (flat >= self.shadow.domain_min) & (flat < self.shadow.domain_max), axis=1
        )
        if np.any(use_shadow):
            output[use_shadow] = self.shadow.sample(flat[use_shadow])
        return output.reshape(points.shape)


ForwardLUT = CubeLUT | BlendedLUT | ShadowRefinedLUT


def read_cube(path: Path) -> CubeLUT:
    title = path.stem
    size = None
    domain_min = np.zeros(3, dtype=np.float64)
    domain_max = np.ones(3, dtype=np.float64)
    values: list[list[float]] = []
    with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            fields = line.split()
            key = fields[0].upper()
            try:
                if key == "TITLE":
                    title = line[len(fields[0]) :].strip().strip('"')
                elif key == "LUT_3D_SIZE":
                    size = int(fields[1])
                elif key == "DOMAIN_MIN":
                    domain_min = np.asarray(fields[1:4], dtype=np.float64)
                elif key == "DOMAIN_MAX":
                    domain_max = np.asarray(fields[1:4], dtype=np.float64)
                elif key == "LUT_3D_INPUT_RANGE":
                    low, high = float(fields[1]), float(fields[2])
                    domain_min = np.full(3, low)
                    domain_max = np.full(3, high)
                elif key == "LUT_1D_SIZE":
                    raise ValueError("1D LUTs are unsupported")
                else:
                    if len(fields) != 3:
                        raise ValueError(f"expected an RGB row, got {line!r}")
                    values.append([float(value) for value in fields])
            except (IndexError, TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    if size is None or len(values) != size**3:
        raise ValueError(f"{path}: incomplete 3D cube")
    file_order = np.asarray(values, dtype=np.float64).reshape(size, size, size, 3)
    data = np.transpose(file_order, (2, 1, 0, 3)).copy()
    return CubeLUT(title, data, domain_min, domain_max)


def read_forward_map(path: Path, domain_max: float | None) -> CubeLUT:
    if path.suffix.lower() != ".rgb16":
        if domain_max is not None:
            raise ValueError("--*-domain-max applies only to decoded .rgb16 maps")
        return read_cube(path)
    if domain_max is None or domain_max <= 0.0:
        raise ValueError(f"{path}: a positive decoded-map domain maximum is required")
    node_count, remainder = divmod(path.stat().st_size, 6)
    if remainder:
        raise ValueError(f"{path}: invalid uint16 RGB byte size")
    size = round(node_count ** (1.0 / 3.0))
    if size**3 != node_count:
        raise ValueError(f"{path}: {node_count} nodes do not form a cube")
    file_order = np.fromfile(path, dtype="<u2").reshape(size, size, size, 3)
    data = np.transpose(file_order, (2, 1, 0, 3)).astype(np.float32) / 4095.0
    return CubeLUT(
        path.stem,
        data,
        np.zeros(3, dtype=np.float64),
        np.full(3, domain_max, dtype=np.float64),
    )


def write_cube(path: Path, lut: CubeLUT, comments: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f'TITLE "{lut.title}"\n')
        handle.write("#LUMIXPHOTOSTYLE STD\n")
        for comment in comments:
            handle.write(f"# {comment}\n")
        handle.write(f"LUT_3D_SIZE {lut.size}\n\n")
        for b in range(lut.size):
            for g in range(lut.size):
                for r in range(lut.size):
                    handle.write(" ".join(f"{value:.10f}" for value in lut.data[r, g, b]) + "\n")


def sample_neutral_axis(lut: ForwardLUT, levels: np.ndarray) -> np.ndarray:
    levels = np.asarray(levels, dtype=np.float64).reshape(-1)
    if isinstance(lut, BlendedLUT):
        return (1.0 - lut.mix) * sample_neutral_axis(lut.first, levels) + lut.mix * sample_neutral_axis(
            lut.second, levels
        )
    if isinstance(lut, ShadowRefinedLUT):
        output = sample_neutral_axis(lut.main, levels)
        use_shadow = (levels >= lut.shadow.domain_min[0]) & (levels < lut.shadow.domain_max[0])
        if np.any(use_shadow):
            output[use_shadow] = sample_neutral_axis(lut.shadow, levels[use_shadow])
        return output
    span = lut.domain_max[0] - lut.domain_min[0]
    position = np.clip((levels - lut.domain_min[0]) / span, 0.0, 1.0) * (lut.size - 1)
    lower = np.floor(position).astype(np.int64)
    upper = np.minimum(lower + 1, lut.size - 1)
    fraction = (position - lower)[:, None]
    return lut.data[lower, lower, lower] * (1.0 - fraction) + lut.data[upper, upper, upper] * fraction


def enforce_neutral_axis(standard: ForwardLUT, vlog: ForwardLUT, data: np.ndarray) -> dict[str, float]:
    size = int(data.shape[0])
    source = np.linspace(standard.domain_min[0], standard.domain_max[0], max(4097, standard.size * 16))
    standard_axis = np.maximum.accumulate(sample_neutral_axis(standard, source).mean(axis=1))
    targets = np.linspace(0.0, 1.0, size)
    inverse_source = np.interp(targets, standard_axis, source)
    vlog_axis = sample_neutral_axis(vlog, inverse_source).mean(axis=1)
    before = np.asarray([np.ptp(data[index, index, index]) for index in range(size)])
    for index, value in enumerate(vlog_axis):
        data[index, index, index] = value
    # Constrain the two trilinear diagonal control groups in every cell.
    for lower in range(size - 1):
        low = float(data[lower, lower, lower, 0])
        high = float(data[lower + 1, lower + 1, lower + 1, 0])
        groups = (
            (2.0 * low + high, ((lower + 1, lower, lower), (lower, lower + 1, lower), (lower, lower, lower + 1))),
            (low + 2.0 * high, ((lower + 1, lower + 1, lower), (lower + 1, lower, lower + 1), (lower, lower + 1, lower + 1))),
        )
        for target, group in groups:
            correction = (np.full(3, target) - sum((data[index] for index in group))) / 3.0
            for index in group:
                data[index] += correction
    after = np.asarray([np.ptp(data[index, index, index]) for index in range(size)])
    return {
        "diagonal_node_max_channel_spread_before": float(np.max(before)),
        "diagonal_node_max_channel_spread_after": float(np.max(after)),
    }


def generate_internal_samples(
    count: int,
    domain_min: np.ndarray,
    domain_max: np.ndarray,
    uniform_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a uniform/correlated mixture and component labels (0/1)."""
    rng = np.random.default_rng(seed)
    uniform_count = round(count * uniform_fraction)
    correlated_count = count - uniform_count
    uniform = rng.random((uniform_count, 3))
    if correlated_count:
        levels = rng.random((correlated_count, 1))
        sigma_choices = np.asarray((0.05, 0.10, 0.20))
        sigmas = sigma_choices[np.arange(correlated_count) % len(sigma_choices), None]
        correlated = levels * np.exp(rng.normal(0.0, 1.0, (correlated_count, 3)) * sigmas)
        correlated /= np.maximum(1.0, np.max(correlated, axis=1, keepdims=True))
        unit = np.vstack((uniform, correlated))
        labels = np.concatenate((np.zeros(uniform_count, dtype=np.uint8), np.ones(correlated_count, dtype=np.uint8)))
    else:
        unit = uniform
        labels = np.zeros(uniform_count, dtype=np.uint8)
    source = domain_min + unit * (domain_max - domain_min)
    order = rng.permutation(len(source))
    return source[order], labels[order]


def sample_forward_pairs(
    standard: ForwardLUT,
    vlog: ForwardLUT,
    source: np.ndarray,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    standard_values = np.empty_like(source, dtype=np.float64)
    vlog_values = np.empty_like(source, dtype=np.float64)
    for start in range(0, len(source), batch_size):
        stop = min(start + batch_size, len(source))
        standard_values[start:stop] = standard.sample(source[start:stop])
        vlog_values[start:stop] = vlog.sample(source[start:stop])
    return standard_values, vlog_values


@dataclass(frozen=True)
class TrilinearDesign:
    indices: np.ndarray  # (samples, 8), flat node indices
    basis: np.ndarray  # (samples, 8)
    sample_weight: np.ndarray  # (samples,)
    size: int

    @property
    def node_count(self) -> int:
        return self.size**3

    def predict(self, nodes: np.ndarray) -> np.ndarray:
        return np.sum(nodes[self.indices] * self.basis, axis=1)

    def transpose(self, sample_values: np.ndarray) -> np.ndarray:
        weights = self.basis * (self.sample_weight * sample_values)[:, None]
        return np.bincount(
            self.indices.reshape(-1),
            weights=weights.reshape(-1),
            minlength=self.node_count,
        )

    def data_normal(self, nodes: np.ndarray) -> np.ndarray:
        return self.transpose(self.predict(nodes))

    def diagonal(self) -> np.ndarray:
        weights = self.basis * self.basis * self.sample_weight[:, None]
        return np.bincount(
            self.indices.reshape(-1),
            weights=weights.reshape(-1),
            minlength=self.node_count,
        )


def trilinear_design(points: np.ndarray, size: int, sample_weight: np.ndarray | None = None) -> TrilinearDesign:
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    position = np.clip(points, 0.0, 1.0) * (size - 1)
    lower = np.floor(position).astype(np.int32)
    lower = np.minimum(lower, size - 2)
    fraction = position - lower
    indices = np.empty((len(points), 8), dtype=np.int32)
    basis = np.empty((len(points), 8), dtype=np.float64)
    column = 0
    for dr in (0, 1):
        wr = fraction[:, 0] if dr else 1.0 - fraction[:, 0]
        for dg in (0, 1):
            wg = fraction[:, 1] if dg else 1.0 - fraction[:, 1]
            for db in (0, 1):
                wb = fraction[:, 2] if db else 1.0 - fraction[:, 2]
                r = lower[:, 0] + dr
                g = lower[:, 1] + dg
                b = lower[:, 2] + db
                indices[:, column] = (r * size + g) * size + b
                basis[:, column] = wr * wg * wb
                column += 1
    if sample_weight is None:
        sample_weight = np.ones(len(points), dtype=np.float64)
    return TrilinearDesign(indices, basis, np.asarray(sample_weight, dtype=np.float64), size)


def curvature_normal(nodes: np.ndarray, size: int) -> np.ndarray:
    grid = np.asarray(nodes).reshape(size, size, size)
    output = np.zeros_like(grid)
    for axis in range(3):
        second = np.diff(grid, n=2, axis=axis)
        first_slice = [slice(None)] * 3
        middle_slice = [slice(None)] * 3
        last_slice = [slice(None)] * 3
        first_slice[axis] = slice(0, size - 2)
        middle_slice[axis] = slice(1, size - 1)
        last_slice[axis] = slice(2, size)
        output[tuple(first_slice)] += second
        output[tuple(middle_slice)] -= 2.0 * second
        output[tuple(last_slice)] += second
    return output.reshape(-1)


def curvature_diagonal(size: int) -> np.ndarray:
    one = np.full(size, 6.0)
    one[0] = one[-1] = 1.0
    if size > 2:
        one[1] = one[-2] = 5.0
    return (
        one[:, None, None] + one[None, :, None] + one[None, None, :]
    ).reshape(-1)


def conjugate_gradient(
    matvec,
    rhs: np.ndarray,
    initial: np.ndarray,
    diagonal: np.ndarray,
    iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, dict[str, object]]:
    solution = initial.astype(np.float64, copy=True)
    residual = rhs - matvec(solution)
    preconditioned = residual / np.maximum(diagonal, 1e-12)
    direction = preconditioned.copy()
    rz = float(residual @ preconditioned)
    initial_norm = float(np.linalg.norm(residual))
    history = [initial_norm]
    converged = initial_norm == 0.0
    for _ in range(iterations):
        product = matvec(direction)
        denominator = float(direction @ product)
        if not math.isfinite(denominator) or denominator <= 0.0:
            break
        alpha = rz / denominator
        solution += alpha * direction
        residual -= alpha * product
        norm = float(np.linalg.norm(residual))
        history.append(norm)
        if norm <= tolerance * max(initial_norm, 1e-30):
            converged = True
            break
        preconditioned = residual / np.maximum(diagonal, 1e-12)
        next_rz = float(residual @ preconditioned)
        direction = preconditioned + (next_rz / rz) * direction
        rz = next_rz
    return solution, {
        "iterations": len(history) - 1,
        "converged": converged,
        "initial_residual_norm": initial_norm,
        "final_residual_norm": history[-1],
        "relative_residual_norm": history[-1] / max(initial_norm, 1e-30),
    }


def fit_global_cube(
    design: TrilinearDesign,
    targets: np.ndarray,
    prior: CubeLUT | None,
    smoothness: float,
    prior_weight: float,
    prior_coverage_scale: float,
    cg_iterations: int,
    cg_tolerance: float,
    title: str,
) -> tuple[CubeLUT, dict[str, object]]:
    size = design.size
    if prior is not None:
        grid = np.linspace(0.0, 1.0, size)
        rr, gg, bb = np.meshgrid(grid, grid, grid, indexing="ij")
        points = np.stack((rr, gg, bb), axis=-1)
        prior_data = prior.sample(points).reshape(-1, 3)
    else:
        prior_data = np.zeros((size**3, 3), dtype=np.float64)
    data_diagonal = design.diagonal()
    if prior_coverage_scale > 0.0:
        # A strong prior is useful only where no forward-pair sample reaches a
        # cube node.  Exponential support gating makes its influence vanish on
        # measured nodes instead of blending the old solution into the fit.
        prior_diagonal = prior_weight * np.exp(-data_diagonal / prior_coverage_scale)
    else:
        prior_diagonal = np.full(size**3, prior_weight, dtype=np.float64)
    normal_diagonal = data_diagonal + smoothness * curvature_diagonal(size) + prior_diagonal
    channel_reports = []
    fitted = np.empty_like(prior_data)
    for channel in range(3):
        rhs = design.transpose(targets[:, channel]) + prior_diagonal * prior_data[:, channel]

        def matvec(nodes: np.ndarray) -> np.ndarray:
            return (
                design.data_normal(nodes)
                + smoothness * curvature_normal(nodes, size)
                + prior_diagonal * nodes
            )

        fitted[:, channel], channel_report = conjugate_gradient(
            matvec,
            rhs,
            prior_data[:, channel],
            normal_diagonal,
            cg_iterations,
            cg_tolerance,
        )
        channel_reports.append(channel_report)
    lut = CubeLUT(
        title,
        fitted.reshape(size, size, size, 3),
        np.zeros(3, dtype=np.float64),
        np.ones(3, dtype=np.float64),
    )
    coverage = design.transpose(np.ones(len(design.sample_weight)))
    prediction = lut.sample_from_design(design) if hasattr(lut, "sample_from_design") else np.stack(
        [design.predict(fitted[:, channel]) for channel in range(3)], axis=1
    )
    training_error = np.linalg.norm(prediction - targets, axis=1)
    return lut, {
        "channel_solvers": channel_reports,
        "node_data_diagonal": percentile_metrics(data_diagonal),
        "node_prior_diagonal": percentile_metrics(prior_diagonal),
        "node_weighted_coverage": percentile_metrics(coverage),
        "unsupported_node_fraction": float(np.mean(coverage < 1e-8)),
        "training_rgb_error": percentile_metrics(training_error),
    }


def percentile_metrics(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(values)),
        "rmse": float(np.sqrt(np.mean(values * values))),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(np.max(values)),
    }


def validate_pipeline(
    standard: ForwardLUT,
    vlog: ForwardLUT,
    baked: CubeLUT,
    sample_count: int,
    uniform_fraction: float,
    seed: int,
    batch_size: int,
) -> dict[str, object]:
    source, labels = generate_internal_samples(
        sample_count, standard.domain_min, standard.domain_max, uniform_fraction, seed
    )
    standard_values, expected = sample_forward_pairs(standard, vlog, source, batch_size)
    predicted = baked.sample(standard_values)
    errors = np.linalg.norm(predicted - expected, axis=1)
    clipped = np.any((standard_values <= 1.0 / 1023.0) | (standard_values >= 1.0 - 1.0 / 1023.0), axis=1)
    report = {
        "sample_count": sample_count,
        "rgb_error": percentile_metrics(errors),
        "clipped_fraction": float(np.mean(clipped)),
    }
    uniform = labels == 0
    correlated = labels == 1
    if np.any(uniform):
        report["uniform_rgb_error"] = percentile_metrics(errors[uniform])
    if np.any(correlated):
        report["correlated_rgb_error"] = percentile_metrics(errors[correlated])
    if np.any(~clipped):
        report["unclipped_rgb_error"] = percentile_metrics(errors[~clipped])
    if np.any(clipped):
        report["clipped_rgb_error"] = percentile_metrics(errors[clipped])
    return report


def build_forward_pipeline(args: argparse.Namespace) -> tuple[ForwardLUT, ForwardLUT]:
    standard: ForwardLUT = read_forward_map(args.standard_map, args.standard_domain_max)
    vlog: ForwardLUT = read_forward_map(args.vlog_map, args.vlog_domain_max)
    pair_options = (args.standard_map_b, args.vlog_map_b, args.pair_blend)
    if any(value is not None for value in pair_options):
        if any(value is None for value in pair_options):
            raise ValueError("--standard-map-b, --vlog-map-b and --pair-blend are required together")
        standard = BlendedLUT(
            standard,
            read_forward_map(args.standard_map_b, args.standard_domain_max),
            args.pair_blend,
        )
        vlog = BlendedLUT(
            vlog,
            read_forward_map(args.vlog_map_b, args.vlog_domain_max),
            args.pair_blend,
        )
    shadow_options = (args.vlog_shadow_map, args.vlog_shadow_map_b, args.vlog_shadow_domain_max)
    if any(value is not None for value in shadow_options):
        if args.vlog_shadow_map is None or args.vlog_shadow_domain_max is None:
            raise ValueError("--vlog-shadow-map and --vlog-shadow-domain-max are required together")
        shadow: ForwardLUT = read_forward_map(args.vlog_shadow_map, args.vlog_shadow_domain_max)
        if args.vlog_shadow_map_b is not None:
            if args.pair_blend is None:
                raise ValueError("a paired shadow map requires --pair-blend")
            shadow = BlendedLUT(
                shadow,
                read_forward_map(args.vlog_shadow_map_b, args.vlog_shadow_domain_max),
                args.pair_blend,
            )
        vlog = ShadowRefinedLUT(vlog, shadow)
    if np.any(standard.domain_min < vlog.domain_min) or np.any(standard.domain_max > vlog.domain_max):
        raise ValueError("the Standard internal domain must be contained in the V-Log domain")
    return standard, vlog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("standard_map", type=Path)
    parser.add_argument("vlog_map", type=Path)
    parser.add_argument("output_cube", type=Path)
    parser.add_argument("--standard-domain-max", type=float)
    parser.add_argument("--vlog-domain-max", type=float)
    parser.add_argument("--standard-map-b", type=Path)
    parser.add_argument("--vlog-map-b", type=Path)
    parser.add_argument("--vlog-shadow-map", type=Path)
    parser.add_argument("--vlog-shadow-map-b", type=Path)
    parser.add_argument("--vlog-shadow-domain-max", type=float)
    parser.add_argument("--pair-blend", type=float)
    parser.add_argument("--prior-cube", type=Path)
    parser.add_argument(
        "--anchor-npz",
        type=Path,
        action="append",
        default=[],
        help="optional camera-pair anchors with standard, target and optional weight arrays",
    )
    parser.add_argument(
        "--anchor-weight-scale",
        type=float,
        default=1.0,
        help="multiply every camera-pair anchor weight by this value",
    )
    parser.add_argument("--title", default="Panasonic Standard to V-Log global forward-pair fit")
    parser.add_argument("--size", type=int, default=33)
    parser.add_argument(
        "--output-size",
        type=int,
        help="optional final cube size after solving on the --size control lattice",
    )
    parser.add_argument("--samples", type=int, default=300000)
    parser.add_argument("--uniform-fraction", type=float, default=0.5)
    parser.add_argument("--neutral-weight", type=float, default=20.0)
    parser.add_argument("--neutral-samples", type=int, default=4097)
    parser.add_argument("--smoothness", type=float, default=0.01)
    parser.add_argument("--prior-weight", type=float, default=1e-4)
    parser.add_argument(
        "--prior-coverage-scale",
        type=float,
        default=0.0,
        help="if positive, exponentially suppress the prior on data-supported nodes",
    )
    parser.add_argument("--cg-iterations", type=int, default=100)
    parser.add_argument("--cg-tolerance", type=float, default=1e-7)
    parser.add_argument("--batch-size", type=int, default=65536)
    parser.add_argument("--validation-samples", type=int, default=100000)
    parser.add_argument("--random-seed", type=int, default=20260817)
    parser.add_argument("--no-enforce-neutral-axis", action="store_true")
    parser.add_argument("--no-clip-output", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.size < 2 or (args.output_size is not None and args.output_size < 2) or args.samples < 1 or args.validation_samples < 1:
        raise ValueError("size and sample counts must be positive")
    if not 0.0 <= args.uniform_fraction <= 1.0:
        raise ValueError("--uniform-fraction must be in [0,1]")
    if min(
        args.neutral_weight,
        args.smoothness,
        args.prior_weight,
        args.prior_coverage_scale,
    ) < 0.0:
        raise ValueError("weights must be nonnegative")
    if args.anchor_weight_scale <= 0.0:
        raise ValueError("--anchor-weight-scale must be positive")
    if args.prior_weight and args.prior_cube is None:
        raise ValueError("a nonzero --prior-weight requires --prior-cube")

    standard, vlog = build_forward_pipeline(args)
    source, component = generate_internal_samples(
        args.samples,
        standard.domain_min,
        standard.domain_max,
        args.uniform_fraction,
        args.random_seed,
    )
    standard_values, targets = sample_forward_pairs(standard, vlog, source, args.batch_size)
    sample_weight = np.ones(args.samples, dtype=np.float64)
    anchor_sets: list[tuple[Path, np.ndarray, np.ndarray, np.ndarray]] = []
    for anchor_path in args.anchor_npz:
        with np.load(anchor_path) as archive:
            if "standard" not in archive or "target" not in archive:
                raise ValueError(f"{anchor_path}: expected 'standard' and 'target' arrays")
            anchor_standard = np.asarray(archive["standard"], dtype=np.float64)
            anchor_target = np.asarray(archive["target"], dtype=np.float64)
            if anchor_standard.shape != anchor_target.shape or anchor_standard.ndim != 2 or anchor_standard.shape[1] != 3:
                raise ValueError(f"{anchor_path}: standard and target must both have shape (N,3)")
            if "weight" in archive:
                anchor_weight = np.asarray(archive["weight"], dtype=np.float64).reshape(-1)
            else:
                anchor_weight = np.ones(len(anchor_standard), dtype=np.float64)
            anchor_weight *= args.anchor_weight_scale
            if len(anchor_weight) != len(anchor_standard) or np.any(anchor_weight <= 0.0):
                raise ValueError(f"{anchor_path}: weights must be positive and match the sample count")
        anchor_sets.append((anchor_path, anchor_standard, anchor_target, anchor_weight))
        standard_values = np.vstack((standard_values, anchor_standard))
        targets = np.vstack((targets, anchor_target))
        sample_weight = np.concatenate((sample_weight, anchor_weight))
    if args.neutral_samples:
        levels = np.linspace(standard.domain_min[0], standard.domain_max[0], args.neutral_samples)
        neutral_source = np.repeat(levels[:, None], 3, axis=1)
        neutral_standard, neutral_target = sample_forward_pairs(
            standard, vlog, neutral_source, args.batch_size
        )
        standard_values = np.vstack((standard_values, neutral_standard))
        targets = np.vstack((targets, neutral_target))
        sample_weight = np.concatenate(
            (sample_weight, np.full(args.neutral_samples, args.neutral_weight))
        )

    design = trilinear_design(standard_values, args.size, sample_weight)
    prior = read_cube(args.prior_cube) if args.prior_cube else None
    baked, fit_report = fit_global_cube(
        design,
        targets,
        prior,
        args.smoothness,
        args.prior_weight,
        args.prior_coverage_scale,
        args.cg_iterations,
        args.cg_tolerance,
        args.title,
    )
    solve_size = baked.size
    output_size = args.output_size or solve_size
    if output_size != solve_size:
        axis = np.linspace(0.0, 1.0, output_size)
        rr, gg, bb = np.meshgrid(axis, axis, axis, indexing="ij")
        output_grid = np.stack((rr, gg, bb), axis=-1)
        baked = CubeLUT(
            args.title,
            baked.sample(output_grid),
            np.zeros(3, dtype=np.float64),
            np.ones(3, dtype=np.float64),
        )
    neutral_report = None
    if not args.no_enforce_neutral_axis:
        neutral_report = enforce_neutral_axis(standard, vlog, baked.data)
    unclipped_min = np.min(baked.data, axis=(0, 1, 2))
    unclipped_max = np.max(baked.data, axis=(0, 1, 2))
    if not args.no_clip_output:
        np.clip(baked.data, 0.0, 1.0, out=baked.data)

    validation = validate_pipeline(
        standard,
        vlog,
        baked,
        args.validation_samples,
        args.uniform_fraction,
        args.random_seed + 1,
        args.batch_size,
    )
    prior_validation = None
    if prior is not None:
        prior_validation = validate_pipeline(
            standard,
            vlog,
            prior,
            args.validation_samples,
            args.uniform_fraction,
            args.random_seed + 1,
            args.batch_size,
        )
    anchor_reports = []
    for anchor_path, anchor_standard, anchor_target, anchor_weight in anchor_sets:
        anchor_error = np.linalg.norm(baked.sample(anchor_standard) - anchor_target, axis=1)
        anchor_reports.append(
            {
                "path": str(anchor_path.resolve()),
                "sample_count": len(anchor_standard),
                "weight_sum": float(np.sum(anchor_weight)),
                "rgb_error": percentile_metrics(anchor_error),
            }
        )
    report = {
        "method": "global regularized forward-pair regression; no pointwise Standard inverse",
        "standard_map": str(args.standard_map.resolve()),
        "vlog_map": str(args.vlog_map.resolve()),
        "standard_map_b": str(args.standard_map_b.resolve()) if args.standard_map_b else None,
        "vlog_map_b": str(args.vlog_map_b.resolve()) if args.vlog_map_b else None,
        "vlog_shadow_map": str(args.vlog_shadow_map.resolve()) if args.vlog_shadow_map else None,
        "vlog_shadow_map_b": str(args.vlog_shadow_map_b.resolve()) if args.vlog_shadow_map_b else None,
        "output_cube": str(args.output_cube.resolve()),
        "solve_size": solve_size,
        "output_size": output_size,
        "samples": args.samples,
        "uniform_samples": int(np.count_nonzero(component == 0)),
        "correlated_samples": int(np.count_nonzero(component == 1)),
        "uniform_fraction": args.uniform_fraction,
        "neutral_samples": args.neutral_samples,
        "neutral_weight": args.neutral_weight,
        "smoothness": args.smoothness,
        "prior_cube": str(args.prior_cube.resolve()) if args.prior_cube else None,
        "prior_weight": args.prior_weight,
        "prior_coverage_scale": args.prior_coverage_scale,
        "standard_domain_max": args.standard_domain_max,
        "vlog_domain_max": args.vlog_domain_max,
        "vlog_shadow_domain_max": args.vlog_shadow_domain_max,
        "pair_blend": args.pair_blend,
        "anchor_weight_scale": args.anchor_weight_scale,
        "cg_iterations": args.cg_iterations,
        "cg_tolerance": args.cg_tolerance,
        "random_seed": args.random_seed,
        "camera_pair_anchors": anchor_reports,
        "fit": fit_report,
        "neutral_axis_constraint": neutral_report,
        "unclipped_output_min": unclipped_min.tolist(),
        "unclipped_output_max": unclipped_max.tolist(),
        "output_clipped_to_0_1": not args.no_clip_output,
        "validation": validation,
        "prior_validation": prior_validation,
        "limitations": [
            "Standard clipping is many-to-one; the fitted value is a globally regularized conditional estimate.",
            "The source distribution controls the estimate in ambiguous regions.",
            "An output LUT cannot reproduce native V-Log acquisition gain, noise, or highlight headroom.",
        ],
    }
    write_cube(
        args.output_cube,
        baked,
        (
            "Globally fitted from paired decoded Standard/V-Log forward maps.",
            "No pointwise Standard inverse or empirical output colour patch is used.",
            f"Samples={args.samples}, smoothness={args.smoothness:g}, prior_weight={args.prior_weight:g}.",
        ),
    )
    report_path = args.report or args.output_cube.with_suffix(".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
