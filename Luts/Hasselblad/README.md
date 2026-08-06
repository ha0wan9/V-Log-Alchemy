# Hasselblad Phocus LUTs

These LUTs are generated for Panasonic V-Log / V-Gamut input from the recovered
Phocus 4.0.1 X2D rendering path, including the daylight-baked colour-correction
stage:

```text
V-Log / V-Gamut
  -> linear V-Gamut
  -> XYZ D65
  -> Bradford D50 adaptation
  -> linear Hasselblad RGB
  -> Phocus daylight CbCr ColorCorrect
  -> highlight rolloff
  -> Phocus Standard film curve
  -> optional Phocus style gradation
  -> selected output-space conversion
```

## Included styles

- `Standard`: Hasselblad RGB plus the captured daylight `ColorCorrect` stage and
  the Standard film curve. It follows Hasselblad's Natural Colour Solution (HNCS):
  natural, true-to-life colour, smooth tonal transitions, restrained but rich
  saturation, and film-like contrast.
- `Nature`: Standard plus the Phocus Nature RGB gradation table captured from
  `SetFilmAndGradation` while switching the preset in Phocus. It keeps the
  HNCS-like Standard foundation while adding a fuller tone response for outdoor
  colour and saturated scenes.

The Phocus RAW `ColorCorrect` / CbCr stage was captured across the full range of
Phocus white-balance settings. The published LUTs use the daylight table because
the daylight, cloudy, and shade tables cluster tightly (mean per-channel
difference under 0.02). The tungsten and warm tables encode genuinely different
colour science and cannot be selected from pixel values inside one 3D LUT.

A Reinhard-style highlight rolloff is applied before the film curve so V-Log
scene-linear highlights stay smooth and distinct instead of hard-clipping to
white.

Style reference:

- https://www.hasselblad.com/learn/hasselblad-natural-colour-solution/

## Output colour spaces

The `.cube` format does not carry an ICC profile, and `#LUMIXPHOTOSTYLE VLOG`
declares the Panasonic input domain only. Choose the output contract explicitly
when generating a LUT:

| `--output-space` | Output definition | Following transform |
| --- | --- | --- |
| `hasselblad-rgb` (default) | Hasselblad RGB, D50, with captured Phocus film/style code values | Required for a strictly colour-managed display workflow |
| `rec709` | BT.709 primaries, D65, BT.709 OETF | None |
| `srgb` | sRGB primaries, D65, sRGB transfer function | None |

The four published files retain the original `hasselblad-rgb` output so existing
camera looks and downstream Panasonic Standard adapters do not change silently.
They stop after the Phocus film/style stage: they are not ACES AP1, and AP1 must
not be selected as a following CST merely because it looks plausible.

For `rec709` and `srgb`, the generator interprets the film/style result using the
installed Hasselblad RGB profile metadata recovered with Phocus:

- Hasselblad RGB white point: D50
- primaries: R `(0.681408, 0.313722)`, G `(0.212113, 0.739488)`,
  B `(0.133516, 0.046110)`
- ICC TRC gamma: `2.19921875`
- white-point conversion: Bradford D50 to D65

It then converts to BT.709/sRGB primaries and applies the selected output transfer
function. Values outside the display gamut are channel-clipped to the cube's
`0..1` range; no undocumented AP1 interpretation or perceptual gamut mapping is
applied. These modes are explicit colourimetric display conversions, not a claim
to reproduce Phocus's still-unrecovered export ICC intent or proprietary gamut
mapping exactly.

Generated names use `_Rec709` or `_sRGB` before the optional size suffix. For
example:

```text
Hasselblad_Standard_Phocus_X2D_VLog_Rec709.cube
Hasselblad_Nature_Phocus_X2D_VLog_sRGB_65.cube
```

## Published files

- `Hasselblad_Standard_Phocus_X2D_VLog.cube`
- `Hasselblad_Standard_Phocus_X2D_VLog_65.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_65.cube`

`Square Crop` is not emitted because it only changes crop geometry. `Portrait`
and `Product` are also not emitted because their captured colour transform
matches `Standard`; their differences are sharpening/noise behaviour that a 3D
LUT cannot encode.

Each style is emitted as a 33-point LUT for camera/runtime use and a 65-point LUT
for higher-precision post workflows.

## Reproduction

The generator, compact daylight ColorCorrect table, Standard film curve, Nature
gradation, and a SHA-256-checked manifest are all included under `Tools`. No
Phocus installation, private module, or author-specific path is required.

From a clean checkout, reproduce the four published backward-compatible files:

```powershell
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff
```

Generate complete display-referred variants instead:

```powershell
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff --output-space rec709
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff --output-space srgb
```

Validate the bundled assets without writing LUTs:

```powershell
python Tools\generate_hasselblad_vlog.py --verify-assets-only
```

Use `--artifact PATH` for a different manifest bundle. Relative asset paths are
resolved next to that manifest and any declared SHA-256 hashes are verified.
