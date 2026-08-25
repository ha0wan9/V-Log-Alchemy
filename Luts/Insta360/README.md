# Insta360 -> V-Log Adapter LUTs

These convert **Insta360 I-Log footage into V-Log / V-Gamut**, so every V-Log
LUT in this repository (Fujifilm, Leica, Hasselblad, ARRI, RED, Cineon, Nikon)
can be applied to an Insta360 camera.

```text
I-Log / Rec.2020
  -> linear Rec.2020
  -> XYZ D65
  -> linear V-Gamut       (both spaces are D65, so no adaptation is applied)
  -> V-Log
```

Chain it in front of any style LUT:

```text
Insta360 clip -> Insta360_ILog_to_VLog.cube -> FLog2C_to_CLASSIC-Neg_VLog.cube
```

## This one is not reverse engineered

Unlike the DJI D-Log M path, no fitting was needed. Insta360 publishes the I-Log
math itself, in the official ACES IDT shipped inside the
**Insta360 I-Log & ACES Workflow** package (Post-production -> ACES on their
download site), as `Insta360_I-Log_Rec2020_ACES_IDT_v2.dctl`:

```c
alpha = 5.77837328   beta = 0.09055934   delta = 0.623992
theta = 0.01         eta   = 0.280055

I-Log -> linear:  x <  0.154402  ->  (x - beta) / alpha
                  x >= 0.154402  ->  10^((x - delta) / eta) - theta
gamut:            Rec.2020, D65
```

Package sha256 `26cb89e0a5914b3f...` (`Insta360_I-Log&ACES_Workflow.zip`, v1.0,
2026-06-09).

## Why the CAT02 step is dropped

The vendor IDT ends with a `Rec.2020 -> AP0 /w CAT02` matrix, because ACES AP0
uses the ACES white point rather than D65. V-Gamut is D65, same as Rec.2020, so
this path goes straight from one to the other. Routing through AP0 would adapt
away from D65 and immediately back, which only costs precision.

That is also the check that validates this implementation: rebuilding Insta360's
published Rec.2020 -> AP0 coefficients from the same primaries and CAT02 matrix
reproduces all nine of their numbers to **5.9e-11**, which confirms the Rec.2020
primaries, the AP0 primaries, the ACES white point and the adaptation are all
correct here.

Run the full check with:

```bash
python3 Tools/generate_insta360_vlog.py verify
```

| Check | Result |
| --- | --- |
| Rec.2020 -> AP0 vs vendor IDT | 5.9e-11 |
| curve continuity at the 0.154402 breakpoint | 4.3e-10 |
| vendor's stated linear breakpoint 0.01104854 | 1.2e-08 |
| I-Log round trip | 5.6e-16 |

## Levels

Exposure lines up on its own, no gain fudge:

| | I-Log | -> V-Log |
| --- | --- | --- |
| black (linear 0) | 0.09056 | 0.12500 (V-Log black) |
| 18% grey | 0.42200 | 0.42331 (V-Log native grey) |
| clip (linear 22.0) | 1.00000 | 0.92246 |

I-Log clips at +6.93 stops over grey, which lands well inside V-Log, so nothing
is lost at the top.

## Generated files

- `Insta360_ILog_to_VLog.cube` / `_65.cube`
- `Insta360_ILog_to_Leica_Classic.cube` / `_65.cube` (baked example)

33-point for runtime use, 65-point for post.

```bash
python3 Tools/generate_insta360_vlog.py generate
python3 Tools/generate_insta360_vlog.py generate \
    --look Luts/Leica/L-Log_to_Classic_VLog.cube --look-name Leica_Classic
```

See `Luts/DJI/README.md` for the measured accuracy trade-off between baking a
style LUT in and chaining two LUTs; the same numbers apply here.

These LUTs carry no `#LUMIXPHOTOSTYLE VLOG` tag on purpose: their input is
I-Log, not V-Log, so a Lumix body must not treat them as V-Log LUTs.
