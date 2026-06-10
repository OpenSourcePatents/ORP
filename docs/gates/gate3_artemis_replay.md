<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Gate 3 replay report — Artemis I digitized bank command, forward replay

**Date:** 2026-06-10. **Module:** `orp/gates/gate3_artemis_replay.py`.
**Verdict: FAIL against the pre-registered tolerances — and documented exactly as it
fell.** The open-loop replay diverges in the skip (does not return from the first pass)
across the entire sourced parameter space. The bank-sign convention is therefore
**NOT LOCKED**. Nothing was tuned.

## 1. What was run

The MACHINE-DIGITIZED Artemis I commanded bank history
(`data/flights/artemis1_bank_commanded.csv`, from AAS 24-174 Fig 12(a); methods and
measured uncertainty in `docs/digitization/artemis1_bank_commanded.md`) was replayed
open-loop through ORP's forward simulator (rotation ON), from the Table-1 inertial EI
state converted to the planet-relative frame by `orp.core.frames`
(V 10965.7 m/s, γ −5.6772°, az 2.4230° relative). Forward-only wall intact: the bank
history is an input, crossrange is an output, no endpoint is targeted.

Sweeps: mass 9,934 / 10,160.5 / 10,387 kg × L/D 0.23 / 0.25 / 0.27 (the sourced
McNamara design ranges), CD 1.40 (ASSERTED), both figure-to-ORP sign mappings, plus the
flight-informed variant (0.90× density, 0.95× L/D per the paper's p.11 estimator
statements, dual-channel verified).

## 2. Pre-registered tolerances (written before any comparison ran)

From the measured digitization uncertainty (negligible here) plus the stated model
error budget (ISA >86 km, constant CD/L-D, the paper's own 10%/5% estimator findings,
open-loop replay of closed-loop commands — full derivation in the module docstring):

| Metric | Nominal | Flight-informed |
|---|---|---|
| Skip apogee | ±30 kft | ±20 kft |
| Endpoint miss (drogue point) | ≤250 nmi | ≤150 nmi |
| Phase proxies | ±60 s | ±40 s |
| Sign lock | wrong/correct crossrange-miss ratio ≥ 3 | same |

## 3. Model fix forced by the first run (sourced, not tuned)

The first replay used the existing Earth ISA, which is **held constant above 86 km**.
At the Artemis EI (121.92 km) that clamp overestimates density by ~300× and lofted the
vehicle off the dense layers entirely. The clamp was replaced for this gate by a US
Standard Atmosphere 1976 thermospheric extension (86–250 km,
`orp/core/atmosphere/us76_highalt.py`), pixel-transcribed from the defining document
(NTRS 19770009539, Table I) with node spot-checks — VERIFIED_SOURCE, 17 new tests.
This is a source-fidelity improvement, independent of any Artemis data.

## 4. Results (whichever way they fall: they fall outside)

All 12 runs (3×3 sweep + 2 sign-lock + flight-informed) behave the same way:

| Quantity | Flight truth | Replay (range across all runs) | Verdict |
|---|---|---|---|
| 1st-pass peak load | 4.03 g (Fig 10(a) callout) | 2.70–2.93 g | −1.1 to −1.3 g |
| 1st-pass exit speed | ~7,870 m/s (vis-viva from the 287.4-kft apogee) | 9,156–9,372 m/s | +1.3 to +1.5 km/s hot |
| Skip apogee | 287.4 kft | 18,512–21,730 kft, still rising at t=3000 s (never returns) | **FAIL** (vs ±30/20 kft) |
| Up Control→Ballistic proxy (drag <6 ft/s²) | 256.450 s | 164.8–172.5 s | **FAIL** (Δ −84…−92 s vs ±60 s) |
| Ballistic→Final proxy (drag >6 ft/s²) | 551.425 s | never (no return) | **FAIL** |
| Endpoint misses (Table 4) | — | unreachable (no return) | **FAIL** |
| Sign lock (crossrange ratio) | ≥3 required | indeterminate (both endpoints unreachable) | **NOT LOCKED** |

The flight-informed variant (0.90× density, 0.95× L/D) moves everything further from
flight (less drag, less bleed: pk1 2.70 g, exit 9,295 m/s), exactly as the sign of those
factors predicts for an open-loop replay.

## 5. Why (structural analysis, quantified)

- The first pass must shed ~3.1 km/s (10.97 → ~7.87 km/s) for the published 287.4-kft
  apogee. The replay sheds 1.70–1.81 km/s. The deficit is insensitive to every sourced
  parameter: the full mass × L/D sweep moves exit speed by only ±110 m/s, CD 1.40→1.55
  by ~75 m/s — two orders short of the 1.4 km/s gap.
- γ at 86 km is −3.76° in EVERY variant including L/D = 0 (pure superorbital
  centrifugal flattening of the −5.68° EI angle — physics, not a model artifact), so
  arrival geometry is pinned. With L/D = 0 the vehicle digs in completely (6.85 g,
  lands); with the sourced L/D and the replayed lift-up initial segment it pulls out at
  63 km / 2.8–2.9 g. The flight, with the same commands and nominally the same vehicle,
  reached 4.03 g and stayed in the high-drag regime until 256 s.
- Both sign mappings produce IDENTICAL vertical dynamics (cos σ is even), so the
  divergence cannot be a sign-mapping artifact — and conversely the endpoint
  crossrange discriminator is unreachable, so the mapping cannot be locked here.
- Root cause class: an open-loop, constant-coefficient, instant-bank, 3-DOF replay of
  CLOSED-LOOP commands in a skip entry. The skip exit is dynamically divergent: small
  vertical-plane model errors (CD/CL vs Mach not modeled — Orion aero database is
  figure-only in Bibb NTRS 20110013644; bank-rate-limited swings not modeled; ISA-day
  vs flight-day density) integrate into exit-energy error that the real guidance
  corrected and a replay cannot. The paper itself documents this sensitivity: its own
  flight-quality predictor missed the reversal-2 timing by 142 s, and "the timing of
  the second bank reversal is sensitive to small perturbations in the EI state,
  atmospheric density, and vehicle L/D" (p. 6, verbatim).

## 6. Bank-sign convention — recorded verbatim, NOT locked

- ORP's pinned convention (docs/verification/eom_vinh_culp_cr149170.md §2, verbatim):
  "σ_ORP = − σ_doc", i.e. "in ORP a positive bank produces dψ_ORP/dt > 0 (a
  North→East, rightward/compass-positive turn), while in the document a positive bank
  produces dψ_doc/dt > 0 (an East→North turn)."
- The source figure's convention (pre-extraction metadata record, verbatim): "bank
  angle is plotted SIGNED, range -200..+200 deg; the initial commanded segment is at a
  small POSITIVE value (~+15 deg); first reversal goes positive-to-negative. The
  figure itself does not print a left/right-of-track definition for the sign."
  AAS 24-174's text never defines the sign convention (pages 3–7 searched verbatim;
  only "switches command to lift-down", p. 4, and a sign-comparison sentence, p. 7).
- **Status: the figure-to-ORP mapping (σ_ORP = ±σ_figure) remains UNDETERMINED.** The
  dataset carries its plotted sign only.
- **[APPROX-ROTATION] export flag for OpenReentry:** any consumer replaying
  `artemis1_bank_commanded.csv` must treat the bank sign as plotted-sign-only; the
  lateral/crossrange sense of the schedule is NOT validated, and the convention lock
  attempted here did not succeed. This caveat must travel with the data.

## 7. What would unlock Gate 3 (future work, in scope order)

1. Digitize the Orion CD/CL-vs-Mach trim curves (Bibb NTRS 20110013644, figure-only) —
   removes the constant-coefficient approximation that dominates the first-pass bleed.
2. Model the bank-rate limit (±15–20 deg/s, paper p. 12) in the replay so reversal
   sweeps spend realistic time at intermediate angles.
3. Replay the digitized ACHIEVED bank (Fig 12(a) green trace) instead of the command —
   removes the control-tracking difference (the green trace is digitizable with the
   same pipeline).
4. If a mid-flight state (e.g. at Ballistic-phase start) is ever published in tabular
   form, replay the second entry alone — the post-skip segment is not divergent and
   would both validate the lower-atmosphere models and lock the sign convention from
   the drogue/main/splash endpoints.

## 8. Honest summary

The digitized schedule passed every digitization gate (PART-2 report), the EI frame
conversion is verified, the atmosphere now carries a sourced 86–250 km extension, and
the forward replay machinery works end-to-end (zero fabricated values, provenance
weakest-link intact). What failed is the thing the pre-registered analysis already
named as the dominant risk: open-loop replay of closed-loop commands through a
constant-coefficient model in the one flight regime that amplifies model error
exponentially. The gate stays NOT_VALIDATED, the numbers above are recorded
un-tuned, and the sign convention remains explicitly unlocked.
