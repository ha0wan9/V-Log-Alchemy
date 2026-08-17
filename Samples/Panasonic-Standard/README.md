# Panasonic Standard Comparison Samples

[English](README.md) | [简体中文](README_zh-CN.md)

The camera is a Panasonic DC-S1RM2 / S1RII. SILKYPIX exports were 8144x5424 uncompressed RGB 16-bit TIFFs with embedded sRGB ICC profiles. Only resized JPEG comparisons and the numeric report are published here, not the source RAW/TIFF files.

## Merger Equivalence

Each `*_Merge_Equality.jpg` uses one Standard TIFF and compares:

```text
Path A: Standard -> S1RII S2V LUT -> original V-Log creative LUT
Path B: Standard -> one baked STD LUT
```

The lower-right panel shows absolute difference at 16x gain. Full-resolution results:

| Look | Mean error (8-bit LSB) | P99 (8-bit LSB) |
|---|---:|---:|
| Fujifilm Classic Neg. | 0.153 | 0.735 |
| Leica Classic | 0.147 | 0.840 |

The paths are not pixel-identical, but their mean difference is below one 8-bit code value. Larger local errors are concentrated around strongly clipped or high-contrast boundaries and come from rebaking two 33-point LUTs into one 33-point LUT. The original two-LUT chain remains preferable on cameras that support it.

## Controlled Standard / Native V-Log Comparison

`S1RII_Controlled_Standard_vs_NativeVLog.jpg` uses a controlled HIF pair from
DC-S1RM2 firmware 1.5 at +2 EV:

- `P1024433.HIF`: Standard, ISO 800, 1/13 s, f/5.6, fixed custom white balance.
- `P1024430.HIF`: native V-Log, with the same ISO, shutter, aperture, white
  balance, light, and framing; registered to the Standard frame.

The panels show the v1.6 conversion and native V-Log before and after Classic
Neg, plus an amplified difference panel. Evaluation removes only one scalar
neutral-derived V-Log code offset per exposure; opponent colour is never
aligned away. Across all four chart exposures, v1.6 cyan mean RGB distance is
`0.00423` in V-Log and `0.01225` after Classic Neg. On the fully held-out
four-exposure hand set, the corresponding aggregate is `0.00392` and `0.00961`.
Exact metrics and registration data are in `controlled_profile_comparison.json`
and `Luts/Panasonic-Standard/Calibration/S1RIIControlledValidation.json`.

The remaining difference is real: Standard clipping is irreversible, and the
native V-Log RAW acquisition/gain path cannot be reproduced by an output LUT.

## Same-RAW SILKYPIX Probe

SILKYPIX 8 SE does not list V-Log in the GUI for a RAW captured as Standard, but its engine accepts this sidecar enum:

```ini
COLOR_STATE=SPECIFIED
COLOR_PROPERTY=COLORUI_PROPERTY_PANA
COLOR_MODE=COLORUI_PROPERTY_VLOG
```

This confirms that the V-Log tables are called. However, a Standard-shot RAW lacks the native V-Log capture gain/Photo Style metadata, so the forced render is not used as the final equality reference. Legacy probe endpoints and merger details are recorded in `comparison_report.json`.

`Generated-LUTs` contains the S1RII v1.6 global-fit example LUTs used by the equivalence images. Every file has `#LUMIXPHOTOSTYLE STD` on its second line.
