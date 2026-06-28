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
- `Nature`: Standard plus the Phocus Nature RGB gradation curve.
- `Portrait`: color transform matches Standard; the Phocus preset difference is
  sharpening/noise behavior, which a 3D LUT cannot encode.
- `Product`: color transform matches Standard; the Phocus preset difference is
  sharpening behavior, which a 3D LUT cannot encode.

`Square Crop` is not emitted as a LUT because it only changes crop geometry.

Each style is emitted as a 33-point LUT for camera/runtime use and a 65-point LUT
for higher-precision post workflows.
