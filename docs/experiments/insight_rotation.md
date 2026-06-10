<!--
ORP — Open Reentry Platform
Copyright (C) Charles W. Dowd Jr.
SPDX-License-Identifier: GPL-3.0-or-later
-->

# InSight rotation experiment — results

**Date run:** 2026-06-10 · **Harness:** `orp/experiments/insight_rotation.py` ·
**Tests:** `orp/tests/test_experiment_insight.py` · **Vehicle:** `orp/data/vehicles/insight.yaml`
**Flight targets** (Karlgaard et al., NASA NTRS 20200003204): peak deceleration **8.13 g**,
landing **6.1 km crossrange** (and 12.3 km uprange) of target.

The bank schedule is an input (constant σ = 160°), crossrange an output. Nothing here
solves for controls.

## Stage A — external-reference ablation reproduction: **VALIDATED at ω = 0**

Configuration (kept verbatim from the external rotating-frame ablation recorded in
`ref_core/lateral_insight.py`): C_D = 1.46, L/D = 0.25 (constant coefficients);
exponential Mars atmosphere ρ₀ = 0.020 kg/m³, H = 11 100 m, CO₂ at 210 K; entry
V = 5500 m/s, γ = −12°, h = 125 km, latitude 4.5° N; stop at Mach 1.56 with the CO₂
sound speed at 210 K (V_stop ≈ 352.9 m/s); RK4 dt = 0.5 s.

### ω = 0 (validation targets — reproduced)

| Quantity | External reference | ORP (this run) | Status |
|---|---|---|---|
| Peak deceleration | 10.93 g | **10.928 g** | ✓ reproduced |
| Crossrange at stop | 9.28 km, azimuth-independent | **9.283 km**, identical at all 8 azimuths (spread < 5 m) | ✓ reproduced |
| Allen-Eggers closed form | 10.63 g | **10.63 g** (analytic) | ✓ |

The azimuth-independence is the rotational symmetry of central gravity over a spherical
non-rotating planet; its observation is a nontrivial correctness check of the lateral
channels. Reproducing all three numbers validates this harness against an independent
implementation. (The reference's own non-rotating run reports crossrange 7.14 km at its
h = 10 km stop; the 9.28 km figure corresponds to the deeper Mach-1.56 stop used here.)

### Rotation on (ω = 7.088218e-5 rad/s) — azimuth sweep

| Azimuth (° from N) | Peak g | Crossrange (km) | Shift vs ω=0 (km) |
|---:|---:|---:|---:|
| 0 | 10.904 | 10.794 | **+1.510** |
| 45 | 10.349 | 10.963 | **+1.679** |
| 90 | 10.112 | 10.322 | **+1.039** |
| 135 | 10.355 | 9.258 | −0.025 |
| 180 | 10.911 | 8.506 | −0.777 |
| 225 | 11.438 | 8.477 | −0.806 |
| 270 | 11.649 | 9.097 | −0.186 |
| 315 | 11.434 | 10.020 | +0.737 |

**Reading vs. the external expectation** ("shift −1.0 to −1.8 km azimuth-dependent, peak
g 10.1–10.9"):

* **Magnitudes and structure agree.** The shift is azimuth-dependent with peak magnitude
  1.04–1.68 km over the 0–90° quadrant — exactly the "order 1.0–1.8 km" the external
  ablation recorded (`ref_core/lateral_insight.py` header). Peak-g shifts reach ±0.7–0.8 g
  by azimuth, matching the recorded "order 0.5–0.8 g".
* **Signs do not transfer.** ORP's shifts span −0.81 to +1.68 km depending on azimuth,
  not a uniformly negative −1.0..−1.8 band; eastward-quadrant azimuths (0–90°) give
  *positive* (rightward) shifts here. The external reference itself states its bank-sign
  convention was **never locked** ("does NOT lock the bank-sign (left/right) convention");
  under a mirrored crossrange or bank sign, ORP's +1.04..+1.68 km at azimuths 0–90° is
  the external −1.0..−1.8 km band. This is a convention ambiguity in the *recorded
  expectation*, not a physics discrepancy — but it is recorded here as not reproduced
  sign-for-sign, and the per-azimuth signed values above are the ORP ground truth
  (crossrange positive to the right of the initial heading, ORP positive bank turns
  right). Peak g across the full sweep spans 10.11–11.65; the external 10.1–10.9 band is
  matched on azimuths 0–180° but exceeded (up to 11.65) on the westward quadrant 225–315°,
  consistent with the same azimuth-labeling ambiguity.
* Tests gate the reproduced ω = 0 targets tightly and the rotation *structure*
  (azimuth dependence, shift magnitudes, peak band); signed per-azimuth values are
  documented here, not gated.

## Stage B — ORP's full models: **reported, not matched** (as expected; all flags below)

Same entry state and σ = 160°, with the lander-anchored Mars atmosphere
(P₀ = 636 Pa, T = 210 K → ρ₀ = 0.0160 kg/m³, H ≈ 10 663 m) and Modified Newtonian
aerodynamics at the vehicle trim (InSight trims at α = 0 → **L/D = 0**); azimuth 0°.

| Case | Peak g | Flight | Crossrange | Flight | Downrange | Stop (t, h) |
|---|---:|---:|---:|---:|---:|---|
| ω = 0 | 7.071 g | 8.13 g | −0.000 km | 6.1 km | 689.8 km | 221.7 s, 6.71 km |
| rotating | 7.049 g | 8.13 g | **+2.262 km** | 6.1 km | 690.8 km | 222.2 s, 6.75 km |

**Reading:**

* **Peak g 7.05–7.07 vs flight 8.13 (−13%).** Flagged contributors: the isothermal
  exponential atmosphere (no thermal structure; the flight reconstruction found density
  ~1σ *below* the a-priori model, with the vehicle penetrating deeper and meeting higher
  density at a given velocity — NTRS 20200003204 p. 19); zero lift at static trim (the
  real lift pointed *down* at entry, steepening the pulse); and the nominal entry state
  (5500 m/s, −12.0°) vs the reconstructed 5542.2 m/s, −12.57° — both steeper and faster
  than nominal, each raising peak g.
* **Crossrange: 0.0 km (ω = 0) and +2.26 km (rotating) vs flight 6.1 km.** The exact
  zero at ω = 0 is the structural consequence of L/D = 0 — with no lift and no rotation
  the trajectory cannot leave its plane, and σ = 160° rotates a zero-length lift vector.
  Rotation alone contributes ≈ 2.3 km. The flight's 6.1 km was driven by the rolling,
  oscillating lift of the hypersonic bounded instability (lift down at entry, a lift
  component directed north during entry — Karlgaard p. 18), which a static-trim model
  cannot represent. A future oscillatory-trim or replayed-attitude model is the
  refinement seam; **the gap is documented, not tuned away.**
* Stop time 222 s is hypersonic-to-Mach-1.56 only; the flight's 349.0 s EDL timeline
  includes parachute and terminal descent, so the timelines are not comparable.
* Run provenance: ASSERTED (weakest links: the σ = 160° representative bank and the
  ASSERTED vehicle geometry/coefficients), correctly below the VERIFIED_SOURCE EOM/
  atmosphere tags — the weakest-link rule reporting honestly.

## Approximation flags (both stages)

[APPROX-ATMOS-A] stage A keeps the external ρ₀ = 0.020 kg/m³ (rounded fact-sheet figure,
ideal-gas-inconsistent with ORP's own 636 Pa / 210 K anchor → 0.0160) verbatim for the
reproduction. · [APPROX-AERO-A] C_D = 1.46 / L/D = 0.25 are the external stand-ins; the
sourced InSight values are C_D ≈ 1.68, L/D = 0 at trim (insight.yaml). · [APPROX-LIFT]
constant σ = 160° stands in for the flight's rolling lift. · [APPROX-EI] EI altitude
125 km assumed. · [APPROX-STATE] nominal planet-relative entry state used; flight OD
state differs (5542.2 m/s, −12.57°). · [APPROX-TRIM-B] static trim α = 0 ⇒ zero Newtonian
lift in stage B.
