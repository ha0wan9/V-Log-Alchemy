# V-Log Alchemy v1.3

## Added

- Panasonic Standard input support for the SILKYPIX model mappings covering GH6, S5II/S5IIX, G9II, GH7, S9, S1IIE, S1RII, S1II, and DC-L10.
- Ten 33-point `Standard -> V-Log` conversion LUTs. Every file is full range and places `#LUMIXPHOTOSTYLE STD` immediately after `TITLE`.
- `Tools/merge_standard_luts.py`, a CLI and Tkinter GUI that converts one or two V-Log creative LUTs into model-specific Standard-input LUTs.
- An explicit chain mode for baking `LUT2(LUT1(StandardToVLog(x)))`.
- A release manifest, SHA-256 list, per-model validation reports, and SILKYPIX RAW comparison samples.

## Camera Dual-LUT Use

On supported cameras, use My Photo Style with the model conversion LUT in `LUT1` and the original V-Log Alchemy creative LUT in `LUT2`. Start with both opacities at 100%. Panasonic applies LUT1 first, then LUT2, and takes the base Photo Style from LUT1.

Dual-LUT support requires firmware 3.1 or later on S5II, 2.1 or later on S5IIX, and 2.2 or later on G9II. GH6 only supports LUTs for V-Log View Assist and cannot bake this Standard dual-LUT chain into recorded photos or video.

## Limitation

Highlights, dynamic range, and saturated colors already clipped by Standard cannot be restored. The conversion uses a canonical pseudo-inverse to approximate the same RAW's SILKYPIX V-Log rendering in the reversible region; it does not turn a Standard capture back into true V-Log acquisition.
