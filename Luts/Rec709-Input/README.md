# Rec.709-Input Looks

Every other look in this repository expects scene-referred **V-Log**. These take
**Rec.709** instead, for footage from a camera that has no log profile at all:
DJI Neo 2 (`Normal` is its only colour profile), phones, most action cams in
their non-log mode.

```text
Rec.709 -> display linear -> [highlight expansion] -> V-Gamut -> V-Log -> look
```

## Why the expansion step is needed

Feeding Rec.709 straight into a V-Log look does not work:

```text
Rec.709 white (1.0) -> linear 1.0 -> V-Log 0.599 -> Leica Classic 0.769
```

The look never sees white. Rec.709 carries only **2.47 stops** above 18% grey,
while Leica Classic needs about **7.3 stops** to reach its own white point, so
everything above grey lands in a narrow washed-out band ending at 0.77.

So the highlights are stretched back out before the look is applied. 18% grey is
an anchor and the stretch has unit slope there, so shadows and mid-tones pass
through the plain inverse EOTF untouched; only the region above grey moves.

`--highlight-stops` sets how far. Measured on Leica Classic:

| `--highlight-stops` | Rec.709 white becomes | max composite slope |
| --- | --- | --- |
| 2.47 (no expansion) | 0.769 — washed out | 1.14 |
| 5.0 | 0.969 | 1.60 |
| **5.5 (default)** | **0.977** | **1.77** |
| 7.32 | 0.990 | 2.12 — amplifies 8-bit banding |

## Known limitation: shadows get crushed

This is a **double render**. The camera already applied its own tone curve, and
the look applies a second one on top. It shows up in the shadows. Leica Classic,
8-bit input:

| 8-bit in | 0 | 8 | 16 | 24 | 32 | 40 |
| --- | --- | --- | --- | --- | --- | --- |
| 8-bit out | 2.75 | 2.88 | 3.43 | 4.54 | 6.61 | 10.21 |

The bottom 32 input levels collapse into about 4 output levels, and the full
ramp goes from 256 distinct input codes to **198** distinct output codes.

Contracting the shadow range to compensate was tried and rejected: it recovers
only 25 -> 29 levels, and past a mild setting it makes the transfer curve
non-monotone and spikes the slope to 9.85. The crush is inherent to grading a
signal that has already been rendered, not a tuning problem. If it hurts a
particular shot, lift the shadows *before* the LUT, or lower the LUT's opacity.

None of this applies to log footage. Shooting log, where the camera offers it,
remains strictly better — see the top-level README.

## What this is not

It is not a recovery of the camera's rendering. That rendering is not invertible
from the outside; `Luts/DJI/README.md` carries a worked proof on DJI's own
Rec.709 LUTs, where two structural models fail at residuals of 0.046 and 0.093
because the render is a genuine 3D transform. The expansion here is a plausible
shape, chosen for a well-behaved composite curve, not the real inverse.

## Generated files

- `Rec709_to_Leica_Classic.cube` / `_65.cube`
- `Rec709_to_Leica_Natural.cube` / `_65.cube`

Any V-Log look in this repository can be converted the same way:

```bash
python3 Tools/generate_rec709_look.py \
    --look Luts/Fujifilm/FLog2C_to_CLASSIC-Neg_VLog.cube --name Fuji_Classic_Neg
```

The tool prints the grey point, the white point, the composite slope range and a
monotonicity check before writing, and warns if white lands below 0.95 or the
slope exceeds 2.0.

These LUTs carry no `#LUMIXPHOTOSTYLE VLOG` tag on purpose: their input is
Rec.709, not V-Log.
