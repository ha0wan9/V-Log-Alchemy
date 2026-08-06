# Hasselblad Phocus LUTs

The v1.4 Hasselblad set contains display-ready LUTs for Panasonic V-Log / V-Gamut
input. It is generated from the recovered Phocus 4.0.1 X2D rendering path with
the daylight-baked colour-correction stage:

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
  -> Rec.709 or sRGB display conversion
```

## Included styles

- `Standard`: the daylight `ColorCorrect` stage plus the Standard film curve,
  giving natural colour separation, smooth tonal transitions, restrained
  saturation, and film-like contrast.
- `Nature`: Standard plus the captured Phocus Nature RGB gradation table, with
  a fuller and more saturated response for outdoor colour.

The Phocus RAW `ColorCorrect` / CbCr stage changes with white balance. The
published LUTs use the daylight table because the daylight, cloudy, and shade
tables cluster tightly. Tungsten and warm captures are not bundled; a separately
prepared artifact manifest can be selected with `--artifact`.

A Reinhard-style highlight rolloff is applied before the film curve so V-Log
scene-linear highlights remain distinct instead of hard-clipping to white.

Style reference:

- https://www.hasselblad.com/learn/hasselblad-natural-colour-solution/

## Output colour spaces

The `.cube` format does not carry an ICC profile, and `#LUMIXPHOTOSTYLE VLOG`
declares the Panasonic input domain only. Every published v1.4 filename and LUT
header therefore states its output space explicitly:

| `--output-space` | Output definition | Following transform | Published |
| --- | --- | --- | --- |
| `rec709` (default) | BT.709 primaries, D65, BT.709 OETF | None | Yes |
| `srgb` | sRGB primaries, D65, sRGB transfer function | None | Yes |
| `hasselblad-rgb` | Hasselblad RGB, D50, Phocus film/style code values | Required | No; advanced analysis only |

For `rec709` and `srgb`, the generator interprets the film/style result using the
Hasselblad RGB ICC profile metadata recovered with Phocus:

- Hasselblad RGB white point: D50
- primaries: R `(0.681408, 0.313722)`, G `(0.212113, 0.739488)`,
  B `(0.133516, 0.046110)`
- ICC TRC gamma: `2.19921875`
- white-point conversion: Bradford D50 to D65

It then converts to BT.709/sRGB primaries and applies the selected output transfer
function. Values outside the display gamut are channel-clipped to the cube's
`0..1` range; no ACES AP1 interpretation or undocumented perceptual gamut mapping
is applied. These are explicit colourimetric conversions, not a claim to
reproduce Phocus's still-unrecovered export ICC intent or proprietary gamut
mapping exactly.

The four pre-v1.4 Hasselblad RGB/D50 intermediate LUTs were removed because they
were easy to misuse in normal camera and post workflows. They remain recoverable
from the `v1.3` tag. Do not treat those legacy values as ACES AP1.

## Published files

Rec.709, recommended for camera monitoring and video workflows:

- `Hasselblad_Standard_Phocus_X2D_VLog_Rec709.cube`
- `Hasselblad_Standard_Phocus_X2D_VLog_Rec709_65.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_Rec709.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_Rec709_65.cube`

sRGB, intended for sRGB-managed still and desktop workflows:

- `Hasselblad_Standard_Phocus_X2D_VLog_sRGB.cube`
- `Hasselblad_Standard_Phocus_X2D_VLog_sRGB_65.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_sRGB.cube`
- `Hasselblad_Nature_Phocus_X2D_VLog_sRGB_65.cube`

Each output is supplied as a 33-point LUT for camera/runtime use and a 65-point
LUT for higher-precision post workflows. `Square Crop` is not emitted because it
only changes geometry. `Portrait` and `Product` are not emitted because their
captured colour transform matches `Standard`; their differences are sharpening
and noise behaviour that a 3D LUT cannot encode.

File hashes are listed in `SHA256SUMS.txt`.

## Reproduction

The generator, compact daylight ColorCorrect table, Standard film curve, Nature
gradation, and SHA-256-checked artifact manifest are all included under `Tools`.
No Phocus installation, private module, or author-specific path is required.

From a clean checkout, regenerate the published Rec.709 set:

```powershell
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff
```

Regenerate the published sRGB set:

```powershell
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff --output-space srgb
```

Validate the bundled assets without writing LUTs:

```powershell
python Tools\generate_hasselblad_vlog.py --verify-assets-only
```

Use `--artifact PATH` for a different manifest bundle. Relative asset paths are
resolved next to that manifest and declared SHA-256 hashes are verified.
