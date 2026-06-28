# Hasselblad Phocus LUTs

These LUTs are generated for Panasonic V-Log / V-Gamut input from the recovered
Phocus 4.0.1 X2D Standard rendering path:

```text
V-Log / V-Gamut
  -> linear V-Gamut
  -> XYZ D65
  -> Bradford D50 adaptation
  -> Hasselblad RGB
  -> Phocus X2D Standard ColorCorrect
  -> Phocus Standard film curve
  -> optional Phocus style gradation
```

Included color styles:

- `Standard`: X2D Standard ColorCorrect plus the captured Standard film curve.
- `Nature`: Standard plus the Phocus Nature RGB gradation table captured from
  `SetFilmAndGradation` while switching the preset in Phocus.

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
