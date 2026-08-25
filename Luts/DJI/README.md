# DJI -> V-Log Adapter LUTs

These LUTs are the opposite direction from the rest of the repository: instead of
turning V-Log into another brand's look, they turn **DJI footage into V-Log /
V-Gamut**, so every V-Log LUT here (Fujifilm, Leica, Hasselblad, ARRI, RED,
Cineon, Nikon) can be applied to DJI cameras.

```text
DJI D-Log(-M) / D-Gamut
  -> linear D-Gamut
  -> XYZ D65
  -> linear V-Gamut        (both spaces are D65, so no adaptation is applied)
  -> V-Log
```

Chain it in front of any style LUT:

```text
DJI clip -> DJI_DLogM_to_VLog.cube -> FLog2C_to_CLASSIC-Neg_VLog.cube -> Rec.709
```

## Generated files

- `DJI_DLog_to_VLog.cube` / `_65.cube`
- `DJI_DLogM_to_VLog.cube` / `_65.cube`

33-point for in-camera / runtime use, 65-point for post.

```bash
python3 Tools/generate_dji_vlog.py generate --source dlog
python3 Tools/generate_dji_vlog.py generate --source dlogm
```

Exposure lines up on its own, no gain fudge needed: 18% scene grey sits at D-Log
39.87% and D-Log M 41.65%, and both land on V-Log 0.4232, which is V-Log's own
18% grey point. D-Log code 1.0 maps to V-Log 0.990, so nothing clips at the top.

### Confidence in the D-Log M curve

The recovery above rests on **one** LUT pairing. DJI ships no second D-Log M
LUT with a different look for the same camera (the "vivid" D-Log M download for
the Osmo Nano is byte-identical to the plain Mavic 3 file), so the result cannot
be cross-validated against an independent pairing. What supports it is indirect:
the method validates at 0.015 stops on synthetic data, the recovered curve is
smooth and log-like through the mid range, and the recovered 18% grey (41.65%)
sits where the format is generally reported to place it.

Treat it as a good measurement, not as vendor math.

## D-Log2: attempted and rejected

The same method was tried on D-Log2, using the Osmo Pocket 4P, which is the only
camera that ships both formats. **It does not work, and no D-Log2 LUT is
published here.**

Pocket 4P has two independent look families (plain and vivid), each with a
D-Log -> Rec.709 and a D-Log2 -> Rec.709 LUT, so for once the cancellation can be
cross-checked: both pairings must recover the same curve. They do not.

| D-Log2 code | plain pairing | vivid pairing | disagreement |
| --- | --- | --- | --- |
| 0.4375 | 0.7823 | 0.7837 | 0.002 stops |
| 0.6250 | 4.1040 | 3.2383 | 0.342 stops |
| 0.7500 | 11.1523 | 7.2425 | 0.623 stops |
| 0.8750 | 34.1082 | 16.1264 | **1.081 stops** |

The disagreement grows systematically with code value, which means DJI's
D-Log -> 709 and D-Log2 -> 709 renders are not the same look. The look therefore
does not cancel, and any curve fitted this way is wrong in the highlights.

Two warning signs were visible before the cross-check confirmed it: the recovered
mid-range slope drifted from 15.6 to 11.3 stops per unit code instead of holding
constant as a log curve must, and the reference LUT's Rec.709 shoulder saturates
by D-Log2 code 0.93, so the top 7% of the range inverts to a flat 41.999.

Other notes from the attempt:

- The 65-point and 33-point D-Log2 LUTs give **identical** results (0.0000 stops
  apart). The bottleneck is the 33-point D-Log reference LUT, so the higher
  resolution on the source side buys nothing.
- Pocket 4P's D-Log -> 709 exists in a V1.0 and a V2.0. V1.0 is the one that
  belongs with the D-Log2 LUTs; pairing with V2.0 gives a much worse
  log-linearity residual (0.62 vs 0.16 stops).

### What did survive

Below and around grey, the two pairings agree to within about 1% of code value,
so that part of the curve is cross-validated:

| | plain | vivid |
| --- | --- | --- |
| black (linear 0) | 7.00% | 6.26% |
| 18% grey | 29.91% | 30.47% |
| +1 stop | 36.28% | 36.47% |

**D-Log2 places 18% grey near 30%**, far below D-Log (39.88%) and D-Log M
(41.65%), and close to ARRI LogC4 (27.49%). It reserves about 70% of its code
range above grey, which is the modern wide-headroom log design rather than the
D-Log / V-Log family. Solving it properly needs either published vendor math or
a physical characterisation of the camera.

## Baking a style LUT in (one-LUT workflow)

`--look` composes the conversion with any V-Log style LUT from this repository
using tetrahedral interpolation, so DJI footage only needs one LUT:

```bash
python3 Tools/generate_dji_vlog.py generate --source dlogm \
    --look Luts/Leica/L-Log_to_Classic_VLog.cube --look-name Leica_Classic
```

Shipped example: `DJI_DLogM_to_Leica_Classic.cube` / `_65.cube`.

Baking is a convenience, not an accuracy win. Measured against the exact math
(uniform random inputs, max channel error):

| Path | median | p99 | max |
| --- | --- | --- | --- |
| chain 33 + 33 | 0.00049 | 0.052 | 0.150 |
| chain 65 + 33 | 0.00013 | 0.015 | 0.043 |
| baked 33 | 0.00137 | 0.100 | 0.279 |
| baked 65 | 0.00041 | 0.039 | 0.072 |

Chaining wins on typical error because it never resamples the composed function
onto one coarse grid; baking wins on worst case, because chaining lets the
conversion LUT's own interpolation error get amplified by the style LUT's
contrast. Use the 65-point baked LUT in post, the 33-point one only where a
single runtime LUT is required. The large errors in all rows sit in deeply
out-of-gamut corners of the cube that real footage does not reach.

Note these DJI LUTs deliberately carry **no** `#LUMIXPHOTOSTYLE VLOG` tag: their
input is D-Log(-M), not V-Log, so a Lumix body must not treat them as V-Log LUTs.

## D-Log: exact

DJI publishes the D-Log transfer function and the D-Gamut primaries, so this
transform is closed-form. See `DCTL/DJI_DLog_to_VLog.dctl`.

## D-Log M: recovered from DJI's own LUTs

DJI has never published the D-Log M curve, so it was reverse engineered.

**What does not work:** you cannot recover it from a single official
`D-Log M to Rec.709` LUT. Two structural models were tested against DJI's LUT
data and both fail badly (residual rms 0.046 and 0.093 respectively):

- a per-channel tone curve applied *after* the D-Gamut -> Rec.709 matrix
- a per-channel tone curve applied *before* the matrix

DJI's Rec.709 render is a genuine 3D transform with cross-channel compression:
hold G and B at mid grey, push R from 0 to 1, and the G/B outputs fall from 0.515
to 0.29. That makes the problem unidentifiable in principle, not just in
practice: any monotone reparameterisation of the transfer curve can be absorbed
into the unknown 3D look.

**What works:** two official LUTs that share the same look. On the neutral axis

```text
dlogm_to_709(x) == dlog_to_709(f(x))
    =>  f = dlog_to_709^-1 . dlogm_to_709      (D-Log M -> D-Log)
```

and D-Log's published math turns that into D-Log M -> linear. The look cancels
because it is the same on both sides. Validated end to end on synthetic LUTs
built from a known curve: **max error 0.015 stops**.

Sources used for the shipped curve, both from DJI's official Mavic 3 download
page (Mavic 3 shoots both formats, so the pair shares one look):

| File | sha256 |
| --- | --- |
| `DJI Mavic 3 D-Log M to Rec.709 V1.cube` | `b18162854ab477...` |
| `DJI Mavic 3 D-Log to Rec.709 V1.cube` | `5e21b78dc23af8...` |

The result is `Tools/dji_dlogm_to_linear.json`. Regenerate with:

```bash
python3 Tools/generate_dji_vlog.py fit-dlogm \
    --dlogm-lut "DJI Mavic 3 D-Log M to Rec.709 V1.cube" \
    --dlog-lut  "DJI Mavic 3 D-Log to Rec.709 V1.cube"
```

### Notes on the fit

- **D-Log M is one curve across DJI's line.** The `DJI OSMO Osmo Nano D-Log M to
  Rec.709 V1.cube` shipped for the Osmo Nano is byte-identical to the Mavic 3
  file (md5 `1993aa7288033b31afd7a621b0b07c86`), and its header still reads
  `Mavic 3 Pro, D-Log M, 2023-03-24`. So this curve also covers Osmo Action /
  Osmo Nano / Mini-series D-Log M footage.
- **The `vivid` variant is the wrong partner.** Pairing the D-Log M LUT with
  `D-Log to Rec.709 vivid` produces a curve that diverges to 8e11 at code 1.0,
  because the vivid LUT tops out at 0.9888 instead of 1.0. Different look, so
  the cancellation does not hold. Use the plain pair.
- **The inversion is solved only at the LUT's own 33 nodes**, then densified with
  a monotone (Fritsch-Carlson) fit in log space. Inverting on a finer grid would
  invent precision that is not in the data.
- **The top of the curve is the least certain part.** DJI's D-Log Rec.709
  shoulder is nearly flat above code 0.85 (0.9899 -> 1.0 over the last four
  nodes), so the inverse is ill-conditioned there. The endpoint itself is safe:
  both LUTs reach exactly 1.0 at code 1.0, which pins D-Log M clip to the same
  scene level as D-Log, 42.0 linear (+7.87 stops over grey).
- The recovered curve is not vendor math. It is a measurement, and it inherits
  whatever DJI baked into the neutral axis of those two LUTs.
