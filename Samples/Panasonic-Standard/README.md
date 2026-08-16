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
| Fujifilm Classic Neg. | 0.708 | 3.930 |
| Leica Classic | 0.493 | 3.293 |

The paths are not pixel-identical, but their mean difference is below one 8-bit code value. Larger local errors are concentrated around strongly clipped or high-contrast boundaries and come from rebaking two 33-point LUTs into one 33-point LUT. The original two-LUT chain remains preferable on cameras that support it.

## Controlled Standard / Native V-Log Comparison

`S1RII_Controlled_Standard_vs_NativeVLog.jpg` uses a controlled HIF pair from
DC-S1RM2 firmware 1.5:

- `P1024418.HIF`: Standard, ISO 800, 1/50 s, f/5.6, fixed manual white balance.
- `P1024415.HIF`: native V-Log, with the same ISO, shutter, aperture, white
  balance, light, and framing; registered to the Standard frame.

The panels show the published v1.5 conversion before and after Classic Neg
beside the official native V-Log paths. The displayed LUT outputs have no
post-alignment correction. Only the difference panel removes the median RGB
offset to isolate colour residuals. After that alignment, Classic Neg mean RGB
distance is `0.0305` over stable pixels and `0.0669` in the cyan region. Exact
metrics and registration data are in `controlled_profile_comparison.json`.

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

`Generated-LUTs` contains the S1RII v1.5 corrected example LUTs used by the equivalence images. Every file has `#LUMIXPHOTOSTYLE STD` on its second line.
