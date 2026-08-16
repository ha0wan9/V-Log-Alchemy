# V-Log Alchemy v1.5

## Panasonic Standard high-chroma correction

Issue #12 reported that the Panasonic `Standard -> V-Log` adapters could drive
high-chroma cyan and blue-green regions toward implausibly low red values. The
failure is visible with the conversion LUT alone, before any creative LUT.

v1.5 applies a shared measured V-Log/V-Gamut output correction to all ten
Panasonic Standard adapters: GH6, S5II/S5IIX, G9II, GH7, S9, S1IIE, S1RII,
S1II, and DC-L10. Each model keeps its own Standard pseudo-inverse; the new
stage operates only after that model-specific step, in the common Panasonic
V-Log/V-Gamut output domain.

The correction is a ridge-regularized opponent-chroma polynomial at 80%
strength. It preserves exact neutral RGB values and preserves mean RGB code
before final `[0,1]` clipping. It does not impose a hard `0.125` per-channel
floor.

## Controlled S1RII validation

The fit uses DC-S1RM2/S1RII firmware 1.5 captures of a SpyderCHECKR 24 under
fixed indoor lighting, fixed custom white balance, ISO 800, f/5.6, and three
exposures. Separate held-out scenes and an older nine-pair set were retained
for validation.

| Validation set | Before | After |
|---|---:|---:|
| Leave-one-exposure-out colour patches, mean RGB distance | 0.1152 | 0.0942 |
| Leave-one-exposure-out cyan patches | 0.1431 | 0.0652 |
| Held-out scene, stable pixels | 0.0607 | 0.0565 |
| Held-out scene, cyan region | 0.1624 | 0.0616 |
| Older nine-pair set, mean RGB distance | 0.01748 | 0.01593 |
| Older nine-pair set, cyan region | 0.06894 | 0.03999 |

Distances are Euclidean RGB code-space errors in normalized `[0,1]` V-Log
output, not perceptual Delta E values. The older nine-pair set has a corrected
mean absolute per-channel error of `0.00805`, or about `8.2` ten-bit code
values.

S1RII has controlled quantitative validation. S9 has independent field
evidence of the same pre-fix symptom in issue #12. The remaining models share
the fixed V-Log/V-Gamut endpoint but still need matched model-specific
Standard/native-V-Log capture validation.

## Reproducibility and integrity

- Added `Calibration/PanasonicVLogOutput.json` with coefficients, constraints,
  source hashes, corrected hashes, and validation metrics.
- Added `Tools/apply_panasonic_vlog_output_correction.py`; all inputs are
  hash-locked and double application is rejected or safely detected.
- Updated all ten per-model reports, the manifest, and `SHA256SUMS.txt`.
- Forced LF line endings for published Panasonic LUTs so raw SHA-256 values are
  stable across platforms.
- Regenerated the included S1RII baked example LUTs and full-resolution merger
  comparisons. Mean two-LUT versus baked-LUT error is below one 8-bit code
  value for both published examples.
- Thirteen regression tests pass, and all ten LUTs are byte-exact reproducible
  from their declared uncorrected v1.3 source hashes.

## Limits

Standard clipping, gamut compression, and non-unique inverse regions remain
irreversible. At identical nominal ISO, aperture, and shutter in the S1RII
test, native V-Log RAW signal was about `0.397x` the Standard RAW signal, a
roughly `1.33`-stop acquisition/gain-path difference. An output LUT cannot
recreate native V-Log noise, highlight headroom, or exposure-index behaviour.

## 中文说明

[查看 v1.5 中文发布说明](https://github.com/shenmintao/V-Log-Alchemy/blob/v1.5/RELEASE_NOTES_v1.5_zh-CN.md)
