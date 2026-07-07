# Hasselblad Phocus LUTs

These LUTs are generated for Panasonic V-Log / V-Gamut input from the recovered
Phocus 4.0.1 X2D rendering path, including the daylight-baked color-correction
stage:

```text
V-Log / V-Gamut
  -> linear V-Gamut
  -> XYZ D65
  -> Bradford D50 adaptation
  -> Hasselblad RGB
  -> Phocus daylight CbCr ColorCorrect (input matrix + 105x89 CbCr table + output matrix)
  -> highlight rolloff
  -> Phocus Standard film curve
  -> optional Phocus style gradation
```

Included color styles:

- `Standard`: Hasselblad RGB plus the captured daylight `ColorCorrect` stage and
  the Standard film curve. It follows Hasselblad's Natural Colour Solution (HNCS):
  natural, true-to-life colour, smooth tonal transitions, restrained but rich
  saturation, and film-like contrast.
- `Nature`: Standard plus the Phocus Nature RGB gradation table captured from
  `SetFilmAndGradation` while switching the preset in Phocus. It keeps the
  HNCS-like Standard foundation while adding a fuller tone response for outdoor
  colour and saturated scenes.

The Phocus RAW `ColorCorrect` / CbCr stage is now included, unlike earlier
releases that shipped only the film curve. The stage was captured across the full
range of Phocus white-balance settings; the daylight table is used because the
daylight, cloudy, and shade tables cluster tightly (mean per-channel difference
under 0.02), so one daylight-baked LUT covers the daylight-and-up range. The
tungsten and warm tables encode genuinely different color science and are not
merged in: a 3D LUT has no scene-level color-temperature input to select between
them, and all captured tables render neutral gray identically, so the difference
cannot be keyed off pixel values. Warmer color temperatures remain available from
`Tools/generate_hasselblad_vlog.py --include-color-correct` with the corresponding
captures.

A Reinhard-style highlight rolloff is applied before the film curve so V-Log
scene-linear highlights stay smooth and distinct instead of hard-clipping to
white.

Style reference:

- https://www.hasselblad.com/learn/hasselblad-natural-colour-solution/

Generated files:

- `Hasselblad_Standard_Phocus_X2D_VLog.cube`
- `Hasselblad_Standard_Phocus_X2D_VLog_65.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_65.cube`

`Square Crop` is not emitted as a LUT because it only changes crop geometry.
`Portrait` and `Product` are also not emitted because their captured color
transform matches `Standard`; their preset differences are sharpening/noise
behavior, which a 3D LUT cannot encode.

Each style is emitted as a 33-point LUT for camera/runtime use and a 65-point LUT
for higher-precision post workflows.

Regenerate the set with:

```powershell
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff
```
