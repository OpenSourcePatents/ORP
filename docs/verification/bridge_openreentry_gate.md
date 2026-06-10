<!--
ORP — Open Reentry Platform
Copyright (C) Charles W. Dowd Jr.
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Bridge gate: ORP vs. the `openreentry` reference implementation

**Date characterized:** 2026-06-10
**Result: PASS** — both gates_01 reference cases reproduced; integrator-level agreement.
**Gate test:** `orp/tests/test_bridge_openreentry.py` (skips, never fails, when the
reference clone or scipy is absent).

## 1. Reference identity (pinned)

| Field | Value |
|---|---|
| Source | `git clone C:\Users\cjdow\projects\openre\openreentry ref_core --branch master` |
| Pinned commit | `8ccb88d` — "Document rotation cost and harden scope boundary" |
| Location | `ref_core/` in the ORP repo root (gitignored — a pinned working copy, not vendored code; the live openreentry tree is never touched) |
| Reference engine | `openreentry.py`: planar 3-DOF state [r, V, γ, s], scipy `solve_ivp` RK45, rtol = atol = 1e-9, dense output |
| Cases | `gates_01.py`: Gate 0 (vacuum Keplerian arc, energy conservation), Gate 1 (steep ballistic entry vs. Allen-Eggers) |

## 2. Method — matched inputs, planar embedding

ORP is run at the equator heading due east with ω = 0. In that configuration ORP's six-state
EOM embed the reference's planar four-state problem exactly: latitude and heading remain
constant (verified to < 1e-12 deg in the gate) and downrange s = R·θ, since ORP's
dθ/dt = V·cosγ/(r·cosφ) at φ = 0 equals the reference's ds/dt = (R/r)·V·cosγ.

Matched elements: μ = 3.986004418e14, R = 6.371e6 (the reference's `EARTH`); central μ/r²
gravity; `ExponentialAtmosphere(ρ₀, H)` = the reference's exponential; constant C_D via
`ConstantCoefficientCalculator`; ORP's fixed RK4 dt set equal to the reference's `max_step`.
The reference trajectory is sampled at ORP's time grid via its dense output. The sensed
g-load definition is identical on both sides (‖aero force‖ / m / g₀, g₀ = 9.80665).

The remaining difference is therefore the **integrator pair**: fixed-step RK4 (ORP) vs.
adaptive RK45 at tight tolerance (reference) — which is exactly what this gate characterizes.

## 3. Characterized integrator difference (2026-06-10)

### Case A — Gate 0 mirror: vacuum arc (V₀=7000 m/s, γ₀=−2°, h₀=400 km, dt=0.5 s, 1500 s)

| Channel | max abs difference | Gate (never loosen) |
|---|---|---|
| h | 3.8e-8 m | < 1e-5 m |
| V | 6.7e-11 m/s | < 1e-8 m/s |
| γ | 3.2e-15 rad | < 1e-12 rad |
| downrange s | 3.0e-8 m | < 1e-5 m |
| ORP energy drift | 5.9e-15 (relative) | < 1e-12 |

(The reference's own Gate-0 criterion is 1e-7 energy drift; ORP beats it by ~7 orders.)

### Case B — Gate 1 mirror: steep ballistic entry (V₀=7000 m/s, γ₀=−89.9°, h₀=120 km, ρ₀=1.225, H=7200 m, m=2000 kg, A=2 m², C_D=1.2, dt=0.05 s, stop at h=5 km)

| Channel | max abs difference | Gate (never loosen) |
|---|---|---|
| h | 7.0e-6 m | < 1e-3 m |
| V | 4.2e-6 m/s | < 1e-3 m/s |
| γ | 1.5e-13 rad | < 1e-10 rad |
| downrange s | 1.2e-8 m | < 1e-5 m |
| peak g-load | ref 133.2926 g vs ORP 133.2931 g (rel 4e-6) | rel < 1e-4 |

Allen-Eggers closed form for this case: 127.65 g. Both full-physics results sit ≈ +4.4%
above it — the gravity-along-track contribution AE neglects, the same effect the reference
gate prints as documentation. The gate pins this anchor loosely (rel 6%, and
full-physics > AE) because AE is an approximation, not truth — per the reference's own
Gate-1 commentary.

## 4. Gate-setting policy

Gates are set at the characterized difference with ~2 orders of magnitude of margin for
platform and scipy-version variation; every gate remains physically negligible (≤ mm,
≤ mm/s). **The tolerances are never to be loosened to make a failing run pass.** A failure
beyond them means a real divergence (EOM, model, or integrator regression); investigate it
and record the outcome here, whichever way it falls.

## 5. Known structural differences (documented, not gated)

1. **Termination semantics.** The reference root-finds the h_stop crossing (scipy event);
   ORP's engine terminates on the first recorded point at/below the threshold, so end times
   differ by up to one dt (observed: 22.382 s vs 22.400 s in Case B). Channels are compared
   over the common time range only.
2. **Sub-datum density.** The reference clamps ρ(h<0) = ρ₀; ORP's exponential continues the
   exponential. Both cases terminate at or above the datum, so the difference is never
   exercised; revisit if a below-datum case is ever bridged.
3. **State dimensionality.** ORP integrates the full six-state rotating-planet EOM; the
   reference integrates four planar states. The planar embedding is exact at the equator
   heading east with ω = 0 (latitude/heading constancy is asserted in the gate).
