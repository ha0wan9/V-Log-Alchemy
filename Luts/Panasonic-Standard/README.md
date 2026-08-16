# Panasonic Standard Input Support

[English](README.md) | [简体中文](README_zh-CN.md)

V-Log Alchemy v1.3 adds camera-specific Panasonic `Standard` input support. The 33-point LUTs in `Conversion` approximate each supported model's Standard output as V-Log/V-Gamut before an existing V-Log Alchemy look is applied.

## Recommended: Two Camera LUTs

On cameras with dual-LUT My Photo Style support:

1. Load the matching `Conversion/*S2V.cube` as `LUT1`.
2. Load the original V-Log Alchemy creative LUT as `LUT2`.
3. Start with both LUT opacities at `100%`. To reduce the look, lower only `LUT2`.
4. Keep other Photo Style adjustments at zero and use full luminance range for video.

Panasonic applies the pair strictly as `LUT2(LUT1(image))`, and the base Photo Style comes from `LUT1`. The conversion LUT must therefore be LUT1 and its second line is:

```text
#LUMIXPHOTOSTYLE STD
```

Do not swap the order or reduce LUT1 opacity; LUT2 expects correctly encoded V-Log input.

## Single-LUT Baking

On Windows, double-click `Tools/merge_standard_luts.bat` to open the GUI, or run the CLI:

```powershell
py Tools\merge_standard_luts.py --model S1RII `
  --lut1 Luts\Fujifilm\FLog2C_to_CLASSIC-Neg_VLog.cube `
  --lut2 Luts\Leica\L-Log_to_Classic_VLog.cube `
  --output-dir Standard-LUTs
```

By default the two inputs are converted independently, producing two Standard-input looks. Running the Python script without arguments also opens its GUI. Select `chain` mode only when intentionally baking the camera-style LUT1 -> LUT2 sequence into one file.

Every output is a camera-ready 33-point full-range `.cube` with `#LUMIXPHOTOSTYLE STD` immediately after `TITLE`. Default names have at most eight basename characters for FAT32 cards.

## Models

| Model | Conversion LUT | SILKYPIX group | Camera use |
|---|---|---|---|
| GH6 | `GH6S2V.cube` | L001 | Post/research only; GH6 has V-Log View Assist but cannot bake a LUT into Standard capture |
| S5II | `S5IIS2V.cube` | L002 | Dual LUT requires firmware 3.1 or later |
| S5IIX | `S5IIXS2V.cube` | L002 | Dual LUT requires firmware 2.1 or later |
| G9II | `G9IIS2V.cube` | L003 | Dual LUT requires firmware 2.2 or later |
| GH7 | `GH7S2V.cube` | L004 | Dual LUT supported |
| S9 | `S9S2V.cube` | L005 | Dual LUT supported |
| S1IIE | `S1IIES2V.cube` | L006 | Dual LUT supported |
| S1RII / DC-S1RM2 | `S1RIIS2V.cube` | L007 | Dual LUT supported |
| S1II | `S1IIS2V.cube` | L008 | Dual LUT supported |
| DC-L10 | `L10S2V.cube` | L009 | Dual LUT supported |

S5II and S5IIX share one SILKYPIX mapping but retain separate file aliases. The decoded G9II and GH7 maps are identical, but both model entries are retained. Do not assume unlisted Panasonic bodies can reuse a LUT based only on sensor size or generation.

## Method

The LUTs were derived from paired model-specific forward tables in SILKYPIX Developer Studio 8 SE:

```text
Standard RGB = F_standard(internal RGB)
V-Log RGB    = F_vlog(internal RGB)
S2V RGB      = F_vlog(pseudo_inverse(F_standard(Standard RGB)))
```

Standard uses 129-point maps, the V-Log main maps are 257-point, and V-Log shadows use 17-point refinement maps. Baking uses SILKYPIX-style trilinear sampling, the midpoint of the odd/even table pair, and the shadow table when all three channels are below `1/64` of the main domain.

| Group | V-Log domain max | Shadow domain max |
|---|---:|---:|
| L001 | 2.0 | 0.03125 |
| L002 | 7.1 | 0.1109375 |
| L003 | 4.0 | 0.0625 |
| L004 | 4.0 | 0.0625 |
| L005 | 7.1 | 0.1109375 |
| L006 | 7.0 | 0.109375 |
| L007 | 2.8 | 0.04375 |
| L008 | 8.0 | 0.125 |
| L009 | 4.0 | 0.0625 |

### Shared V-Log output correction

All conversion LUTs add the same measured opponent-chroma correction after
their model-specific decoded-map pseudo-inverse. This is an output-domain step:
each Standard inverse remains model-specific, while the destination is the same
fixed Panasonic V-Log/V-Gamut encoding. The regularized correction preserves
every exact neutral RGB value and preserves mean RGB code before the final
`[0,1]` clip; it does not apply a hard per-channel V-Log floor.

Controlled S1RII firmware 1.5 captures at three chart exposures showed that the
uncorrected output could produce an implausibly low red component for saturated
cyan. An independent S9 report in GitHub issue #12 shows the same blue/cyan
failure with the conversion LUT alone, supporting use of the common endpoint
correction beyond L007.

Leave-one-exposure-out chart validation reduced cyan mean RGB error from
`0.1431` to `0.0652`. A separate nine-pair capture set reduced cyan error from
`0.0689` to `0.0402`, while overall mean RGB error fell from `0.01748` to
`0.01594`. Coefficients, constraints, and validation metrics are recorded in
[`Calibration/PanasonicVLogOutput.json`](Calibration/PanasonicVLogOutput.json).
The hash-locked all-model regeneration step is
`Tools/apply_panasonic_vlog_output_correction.py --all`. On the published
corrected files this command verifies and skips them; pass an uncorrected v1.3
package with `--input-root` to regenerate the outputs.

At identical nominal ISO, aperture, and shutter, the validated native V-Log RAW
signal was about `0.397x` the Standard RAW signal (about `1.33` stops). This is
an acquisition/gain-path difference: the output LUT cannot reproduce native
V-Log noise, highlight headroom, or exposure-index behavior.

## Comparison Samples

[`Samples/Panasonic-Standard/README.md`](../../Samples/Panasonic-Standard/README.md) contains three full-resolution two-LUT/single-LUT equivalence tests plus a native Standard ISO 4000 versus V-Log ISO 5000 capture-path reference.

## Limits

- Highlights, saturated colors, and dynamic range already clipped by Standard cannot be restored. This is a canonical pseudo-inverse.
- The conversion is only for Panasonic `Standard`, not Natural, Cinelike, 709 Like, or a differently adjusted in-camera curve.
- The two-LUT path avoids an extra 33-point rebake and is normally preferred on supported cameras.
- Panasonic does not document the camera's `.cube` interpolation method. A 33-point output reduces interpolation differences.
- The common correction is quantitatively validated on DC-S1RM2 firmware 1.5 and qualitatively supported on S9. Other model groups use the same fixed V-Log endpoint, but matched controlled captures are still pending.

Official references:

- [S1RII full manual PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/003/190/256/000000003190256/dc_s1rm2.pdf): Photo Style, LUT Library, dual-LUT order, and base Photo Style.
- [S5II LUT Library](https://eww.pavc.panasonic.co.jp/dscoi/DC-S5M2/html/DC-S5M2_DVQP2839_eng/0071.html): Cube size, full-range, and FAT32 filename limits.
- [DC-L10 full manual PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/004/377/759/000000004377759/dc_l10.pdf): dual-LUT and Standard base-tag support.
