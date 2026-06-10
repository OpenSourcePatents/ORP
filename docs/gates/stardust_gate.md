<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Gate report — Stardust SRC ballistic entry

**Status: NOT_VALIDATED** (forward prediction; reproduces flight truths within 3-sigma,
not a locked validation — see caveats). Module: `orp/gates/gate_stardust.py`.

## Sources
- **Geometry & C_D:** Mitcheltree et al., AIAA 97-2304 (NTRS 20040105538) — 60° half-angle
  sphere-cone, nose radius 0.2286 m, base diameter 0.8128 m, frontal area 0.51887 m², zero-AoA
  hypersonic-continuum C_A 1.4816–1.5636 (Table 4, LAURA, M 12.2–42.7; constant 1.50 = mean
  used). Encoded in `stardust.yaml`. **Correction 2026-06-10:** the C_D ≈ 1.61 previously
  cited here does not appear anywhere in the source (dual-channel transcription verification);
  it was a mis-extraction.
- **EI state & truths:** Stardust entry reconstruction — EI radius 6503.14 km (≈132.1 km alt),
  12.9 km/s inertial, FPA −8.2°, azimuth 102.9°, mass 46 kg, spin ~13.5 rpm.

## Truths vs forward prediction
| Quantity | Flight truth | ORP (rotation on, CD 1.50) |
|---|---|---|
| Peak deceleration | 32.89 g (3σ 3.64) | **32.0–32.4 g** across the latitude sweep ✓ within 3σ |
| Mach 1.23 altitude | 31.03 km | ~31.6 km (~0.55 km high) |
| Time to Mach 1.23 | drogue at 137.9 s | ~133.4–133.7 s (drogue follows M1.23 by a few s) |

(Numbers re-run 2026-06-10 after the C_D source-fidelity correction 1.61 → 1.50. With the
previously mis-cited 1.61 the sweep read 32.3–32.8 g and M1.23 at ~32.0 km; the corrected CD
moves the M1.23 altitude ~0.45 km closer to flight. The change is a citation correction, not
a tuning step — recorded both ways.)

Entry-interface conversion is **inertial → planet-relative** with rotation on
(`orp.core.frames`): V 12.9 km/s inertial → ~12.44–12.58 km/s relative (the well-known
~12.6 km/s planet-relative figure), FPA −8.2° → ~−8.5°.

## Centrifugal shallowing (the expected first-order effect)
This is a **superorbital** entry, so the curvature term V²/r is large and shallows the
descent, cutting peak g far below the flat-Earth value:

- Flat-Earth Allen-Eggers (no curvature): **~60 g**.
- ORP full rotating-planet EOM: **~32 g** — matching the flight 32.89 g.
- External reference for context: ~73 g without curvature, ~38 g on crude curved models.

ORP's full curvature treatment lands closer to flight than the external crude-curved 38 g.

## EI latitude sweep
The primary does not text-state the EI latitude, so it is swept over −45°…+45°. Peak g varies
by only **0.47 g** and the Mach-1.23 altitude by <0.05 km across the sweep: the unknown EI
latitude is **not** a significant uncertainty for these truths (the rotation enters mainly
through the ~130 m/s spread in relative speed, which the ballistic deceleration washes out).

## Why NOT_VALIDATED (documented approximations)
1. **EI latitude assumed** (swept, not sourced) — though shown to be a weak sensitivity.
2. **Constant hypersonic C_D = 1.50** — the C_A-vs-Mach curve below Mach 12 is figure-only
   (Mitcheltree); using the continuum mean slightly overestimates low-Mach drag, consistent
   with the ~0.55 km-high Mach-1.23 altitude.
3. **ISA held constant above 86 km** — the EI is at ~132 km; the high-altitude density is an
   overestimate, but the peak g (≈54 km) and drogue (≈30 km) occur deep in the valid range,
   so the net effect on the headline truths is small.
4. **3-DOF point mass** — no spin dynamics, no ablation/shape change, no 6-DOF.

## Forward-only
Stardust is ballistic (L/D = 0); the bank schedule is inert here. The gate replays an entry
state forward and reports where it lands. No control is solved for and no endpoint is targeted.

## Transcription status (2026-06-10)
DUAL-CHANNEL VERIFIED - blind pixel transcripts (session scratch refs/transcripts/sdrecon-keyvalues.md, mitcheltree-OML.md, mitcheltree-CD.md) vs PDF text layers. EI radius 6503.14 km, 12.9 km/s inertial, FPA -8.2 deg, azimuth 102.9 deg, mass 46 kg, spin 13.5 rpm, peak 32.89 g (3-sigma 3.64, nominal 32.86), Mach 1.23 at 31.03 km, drogue 137.9 s: all agree exactly in both channels. One DISCREPANCY found and corrected: C_D 1.61 was not in Mitcheltree (see Sources).
