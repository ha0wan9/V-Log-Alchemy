# Hasselblad Phocus LUTs

These LUTs are generated for Panasonic V-Log / V-Gamut input from the stable
film-curve/gradation portion of the recovered Phocus 4.0.1 X2D rendering path:

```text
V-Log / V-Gamut
  -> linear V-Gamut
  -> XYZ D65
  -> Bradford D50 adaptation
  -> Hasselblad RGB
  -> Phocus Standard film curve
  -> optional Phocus style gradation
```

Included color styles:

- `Standard`: Hasselblad RGB plus the captured Standard film curve.
  It is described against Hasselblad's Natural Colour Solution (HNCS): natural,
  true-to-life colour, smooth tonal transitions, restrained but rich saturation,
  and film-like contrast.
- `Nature`: Standard plus the Phocus Nature RGB gradation table captured from
  `SetFilmAndGradation` while switching the preset in Phocus. It keeps the
  HNCS-like Standard foundation while adding a fuller tone response for outdoor
  colour and saturated scenes.

The recovered Phocus RAW `ColorCorrect` / CbCr stage is not included in these
stable LUTs. It was captured separately and confirmed to change with white
balance, so it remains an experimental path available from
`Tools/generate_hasselblad_vlog.py --include-color-correct`.

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
python Tools\generate_hasselblad_vlog.py --all-styles
```
