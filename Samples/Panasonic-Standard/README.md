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

## Native Capture Paths

`S1RII_Standard4000_vs_NativeVLog5000.jpg` uses consecutive RAW captures:

- `P1013120.RW2`: Standard, ISO 4000, 1/60 s, F4, 19:31:16.
- `P1013121.RW2`: native V-Log, ISO 5000, 1/60 s, F4, 19:31:26.

The lower row compares Standard plus the baked STD LUT against native V-Log plus the original LUT. This is qualitative only: the captures are ten seconds apart and use different ISO settings, so brightness, noise, white balance, and sensor-gain differences are not merger error.

## Same-RAW SILKYPIX Probe

SILKYPIX 8 SE does not list V-Log in the GUI for a RAW captured as Standard, but its engine accepts this sidecar enum:

```ini
COLOR_STATE=SPECIFIED
COLOR_PROPERTY=COLORUI_PROPERTY_PANA
COLOR_MODE=COLORUI_PROPERTY_VLOG
```

This confirms that the V-Log tables are called. However, a Standard-shot RAW lacks the native V-Log capture gain/Photo Style metadata, so the forced render is not used as the final equality reference. Endpoints and details are recorded in `comparison_report.json`.

`Generated-LUTs` contains the S1RII v1.5 corrected example LUTs used by the equivalence images. Every file has `#LUMIXPHOTOSTYLE STD` on its second line.
