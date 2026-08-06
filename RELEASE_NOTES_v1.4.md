# V-Log Alchemy v1.4

## Hasselblad LUTs are now display-ready

The four Hasselblad RGB/D50 intermediate LUTs from v1.3 and earlier have been
replaced with eight explicitly named display-output LUTs:

- Hasselblad Standard and Nature
- Rec.709 and sRGB output spaces
- 33-point camera/runtime and 65-point post-production versions

Use Rec.709 for camera monitoring and video workflows. Use sRGB for sRGB-managed
still-image and desktop workflows. Both output families are complete display
transforms and require no following CST.

The former intermediate LUTs were easy to misuse because `.cube` files do not
carry ICC metadata. They remain available from the `v1.3` tag for reproducibility,
but they must not be interpreted as ACES AP1.

## Defined colour pipeline

The display conversion now explicitly performs:

1. Hasselblad RGB ICC TRC decode using gamma `2.19921875`;
2. Hasselblad RGB to XYZ D50;
3. Bradford adaptation from D50 to D65;
4. conversion to BT.709/sRGB primaries; and
5. the selected BT.709 or sRGB output transfer function.

Out-of-gamut values are channel-clipped to the LUT's `0..1` domain. This is a
defined colourimetric conversion, not a claim to reproduce Phocus's unrecovered
export ICC intent or proprietary gamut mapping exactly.

## Reproducible generator

- Removed all author-specific absolute paths and the external private Python
  module dependency.
- Bundled the compact daylight ColorCorrect table, Standard film curve, Nature
  gradation, and a relative-path artifact manifest with SHA-256 validation.
- Changed the generator default to Rec.709; the Hasselblad RGB/D50 intermediate
  remains available only as the explicitly named `hasselblad-rgb` advanced mode.
- Added clean-checkout regression tests and `Luts/Hasselblad/SHA256SUMS.txt`.
- Verified that a clean staged snapshot regenerates every published LUT
  byte-for-byte.

## Regeneration

```powershell
# Published Rec.709 set (default)
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff

# Published sRGB set
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff --output-space srgb
```

See `Luts/Hasselblad/README.md` for the complete output contracts and limitations.
