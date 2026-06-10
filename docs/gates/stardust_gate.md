<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Gate report — Stardust SRC ballistic entry

**Status: NOT_VALIDATED** (forward prediction; reproduces flight truths within 3-sigma,
not a locked validation — see caveats). Module: `orp/gates/gate_stardust.py`.

## Sources
- **Geometry & C_D:** Mitcheltree et al., AIAA 97-2304 (NTRS 20040105538) — 60° half-angle
  sphere-cone, nose radius 0.2286 m, base diameter 0.8128 m, frontal area 0.51887 m², zero-AoA
  hypersonic-continuum C_D ≈ 1.61. Encoded in `stardust.yaml`.
- **EI state & truths:** Stardust entry reconstruction — EI radius 6503.14 km (≈132.1 km alt),
  12.9 km/s inertial, FPA −8.2°, azimuth 102.9°, mass 46 kg, spin ~13.5 rpm.

## Truths vs forward prediction
| Quantity | Flight truth | ORP (rotation on) |
|---|---|---|
| Peak deceleration | 32.89 g (3σ 3.64) | **32.3–32.8 g** across the latitude sweep ✓ within 3σ |
| Mach 1.23 altitude | 31.03 km | ~32.0 km (~1 km high) |
| Time to Mach 1.23 | drogue at 137.9 s | ~133 s (drogue follows M1.23 by a few s) |

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
2. **Constant hypersonic C_D = 1.61** — the CD-vs-Mach curve below Mach 12 is figure-only
   (Mitcheltree); using the hypersonic value slightly overestimates low-Mach drag, consistent
   with the ~1 km-high Mach-1.23 altitude.
3. **ISA held constant above 86 km** — the EI is at ~132 km; the high-altitude density is an
   overestimate, but the peak g (≈54 km) and drogue (≈30 km) occur deep in the valid range,
   so the net effect on the headline truths is small.
4. **3-DOF point mass** — no spin dynamics, no ablation/shape change, no 6-DOF.

## Forward-only
Stardust is ballistic (L/D = 0); the bank schedule is inert here. The gate replays an entry
state forward and reports where it lands. No control is solved for and no endpoint is targeted.
