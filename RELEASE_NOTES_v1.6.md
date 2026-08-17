# V-Log Alchemy v1.6

## Global Panasonic forward-pair rebuild

v1.6 replaces the Panasonic Standard adapters' pointwise pseudo-inverse and
the v1.5 opponent-chroma output patch with a single global reconstruction
method. The complete LUT node lattice is solved from paired decoded forward
samples:

```text
Standard RGB = F_standard(internal RGB)
V-Log RGB    = F_vlog(internal RGB)
fit L so that L(F_standard(x_i)) ~= F_vlog(x_i)
```

The data term, second-order smoothness, exact neutral axis, weak v1.3 prior,
and controlled-camera pairs are optimized together. There is no pointwise
Standard inverse and no post-fit colour patch.

All ten adapters are independently rebuilt: GH6, S5II, S5IIX, G9II, GH7, S9,
S1IIE, S1RII, S1II, and DC-L10. Each file retains its own model-group Standard
and V-Log forward maps. They share only the fixed Panasonic V-Log/V-Gamut
endpoint and controlled S1RII constraints; the S1RII cube is not copied to
other cameras.

## Controlled S1RII validation

The fit uses DC-S1RM2/S1RII firmware 1.5 captures under fixed indoor light,
fixed custom white balance, ISO 800, and f/5.6:

- 72 chromatic SpyderCHECKR 24 samples across 0/+1/+2/+3 EV;
- 20,519 low-gradient registered scene samples at +1/+2 EV;
- all four hand-scene exposures excluded from fitting.

Distances below are Euclidean RGB code-space errors in normalized `[0,1]`
V-Log, not Delta E. Evaluation removes one scalar neutral-derived code offset
per exposure and never aligns opponent colour.

| Validation set | v1.3 | v1.5 | v1.6 |
|---|---:|---:|---:|
| All chart colours, V-Log | 0.09232 | 0.07293 | **0.00335** |
| All chart colours, Classic Neg | 0.16896 | 0.13270 | **0.00508** |
| Cyan patches, V-Log | 0.10412 | 0.04571 | **0.00423** |
| Cyan patches, Classic Neg | 0.31953 | 0.08173 | **0.01225** |
| Fully held-out hand, V-Log | 0.02180 | 0.02135 | **0.00392** |
| Fully held-out hand, Classic Neg | 0.03228 | 0.05644 | **0.00961** |

The displayed +2 EV doll upper-arm median RGB error is `0.00255` in V-Log and
`0.00454` after Classic Neg. Four-exposure scene aggregates are `0.01062` and
`0.01742`.

## Reproducibility and package changes

- Added `Tools/fit_panasonic_forward_pairs.py`, a matrix-free regularized
  global solver with trilinear playback and strict convergence reporting.
- Added `Tools/rebuild_panasonic_forward_pairs.py` to rebuild and finalize all
  ten model adapters from decoded maps and content-exact v1.3 priors.
- Added the hash-locked 20,591-sample controlled anchor artifact and metadata.
- Added complete fit settings, source/output hashes, per-model validation, and
  full S1RII controlled results under `Calibration`.
- All 30 RGB solver channels converged below the `1e-7` relative-residual
  threshold. Published cubes retain exact neutral axes and camera-safe headers.
- Retired the v1.5 polynomial correction and its application tool; v1.6 LUTs
  are direct global fits, not corrected v1.5 outputs.
- Rebuilt the two included S1RII single-LUT examples. Full-resolution two-LUT
  versus baked-LUT mean error is `0.153` and `0.147` 8-bit LSB.

## Limits

Standard clipping, gamut compression, and many-to-one regions remain
irreversible. The fitted result in ambiguous regions is a globally regularized
conditional estimate. Controlled quantitative capture validation is currently
limited to S1RII; S9 has independent field evidence in issue #12, and the
remaining model groups still need matched Standard/native-V-Log captures.

An output LUT also cannot reproduce native V-Log acquisition gain, noise, or
highlight headroom.

## 中文说明

[查看 v1.6 中文发布说明](https://github.com/shenmintao/V-Log-Alchemy/blob/v1.6/RELEASE_NOTES_v1.6_zh-CN.md)
