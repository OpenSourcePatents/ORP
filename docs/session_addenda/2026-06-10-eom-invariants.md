<!--
ORP — Open Reentry Platform
Copyright (C) Charles W. Dowd Jr.
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Session addendum — 2026-06-10 — branch `eom-invariants`

Branched from `skeleton` @ 6fb2211. Eight commits, full pytest green at every one
(87 → 130 tests). Not merged, not pushed, per instruction. Standing scope wall held
throughout: the bank schedule is always an input, crossrange always an output; no
function, test, plot, or affordance takes a target endpoint and returns controls.

## Commits

| Commit | Phase | Content |
|---|---|---|
| 6955359 | 1 | EOM invariant tests 1–4 (`orp/tests/test_eom_invariants.py`) |
| b955d74 | 1 | Test 5: CR-149170 term-by-term verification; `VERIFIED_SOURCE` level |
| dd88db5 | 2 | `ConstantCoefficientCalculator` + `ExponentialAtmosphere` + unit tests |
| b82432d | 2 | Bridge gate vs pinned `openreentry` clone + characterization doc |
| f4bc2f0 | 3 | Headless plotting (`orp/gui/plots.py`) + tests |
| 3886afb | 4 | `insight.yaml` with per-property provenance |
| 2f7c8da | 4 | InSight rotation experiment + tests + results doc |
| (this)  | — | Session addendum |

## Phase 1 — EOM invariants (tests 1–4) and source verification (test 5)

* **Test 1 (structural):** dV/dt is even in ω (no Coriolis 2ωV term — Coriolis is ⊥ to
  planet-relative velocity and does no work); the odd-in-ω parts of dγ/dt and dψ/dt equal
  the analytic Coriolis terms exactly, on a 240-state grid.
* **Test 2 (orbit hold):** eastward equatorial circular orbit (r = R + 250 km,
  V_rel = √(μ/r) − ωr), one full period, RK4 dt = 1.0: measured |r − r₀| = 0 m and
  max|γ| ≲ 1e-15 rad (required < 1e-6 m, < 1e-12 rad; reference impl had 0.0 / 8.5e-16).
  A control test shows the same state drifts > 100 m without the rotation terms.
* **Test 3 (Jacobi):** E = V²/2 − μ/r − ½ω²r²cos²φ conserved over an eccentric orbit to
  max relative drift < 1e-10 (measured ~1e-14-level; reference 6.3e-15).
* **Test 4 (ω = 0 reduction):** matches an independently coded non-rotating
  planet-relative set term-for-term (rel 1e-12) with lift, drag, and bank active.
* **Test 5 (source verification):** fetched NTRS **19760024112** (Busemann, Vinh & Culp,
  *Hypersonic Flight Mechanics*, NASA CR-149170, Univ. of Colorado, Grant NSG 1056, 1976;
  public use permitted; 440 pp). Verified the EOM term-by-term against Ch. 2 Eqs. (2-28),
  (2-31), (2-34) by reading the rendered pages (OCR unreliable for math). Every term
  matched under the exact mapping ψ_doc = π/2 − ψ_ORP (the document's heading is measured
  from the local parallel of latitude, i.e. East-toward-North; ORP's is compass
  North-toward-East) and σ_ORP = −σ_doc. The document states verbatim that 2ωV "called
  the Coriolis acceleration" matters for long-range flight, and its printed dV/dt carries
  no such term. Full table: `docs/verification/eom_vinh_culp_cr149170.md`.

**Provenance consequences (committed):** `ValidationLevel.VERIFIED_SOURCE` added between
ASSERTED and VERIFIED_CFD (ranks now 0/1/2/3/4); the EOM tagged VERIFIED_SOURCE
(`SimulationStepper.provenance`) and folded into every run by the engine (weakest link —
a new test proves an all-VERIFIED_FLIGHT-inputs run comes back VERIFIED_SOURCE); Earth ISA
and Mars atmospheres retagged VERIFIED_FLIGHT → VERIFIED_SOURCE (spot-checks verify the
implementation against defining documents, not flight); `mars.py` citation now names the
Viking datasets behind the 636 Pa / 210 K anchor — Hess et al. (1977) JGR 82, 4559–4574,
DOI 10.1029/JS082i028p04559, and Seiff & Kirk (1977) JGR 82, 4364–4378, DOI
10.1029/JS082i028p04364 (verified against publisher records; the NSSDC Mars Fact Sheet
page itself was offline for maintenance on this date). **Vehicle yamls unaffected:** their
VERIFIED_FLIGHT properties are flight-reconstructed quantities; the provenance describes
the value's origin, which genuinely is flight data. Gravity models were not retagged
(out of the instructed scope; their GM/Somigliana constants are measurement-derived).

## Phase 2 — bridge gate vs `openreentry`

Pinned clone at `ref_core/` (commit 8ccb88d, gitignored; live tree untouched). ORP run
equatorial-eastward at ω = 0 embeds the reference's planar [r, V, γ, s] problem exactly.
Both gates_01 cases mirrored with matched inputs and matched step. Characterized
integrator difference (RK4 fixed vs RK45 adaptive 1e-9): vacuum arc ≤ 3.8e-8 m in h,
6.7e-11 m/s in V; steep ballistic entry ≤ 7.0e-6 m, 4.2e-6 m/s; peak g 133.2926 vs
133.2931 (rel 4e-6); Allen-Eggers 127.65 g sits 4.4% below both (gravity-along-track).
Gates set at characterized level with ~2 orders margin, **never to be loosened**;
structural differences (event-interpolated vs step-quantized termination; sub-datum
density clamp) documented in `docs/verification/bridge_openreentry_gate.md`.

## Phase 3 — headless plotting

`orp/gui/plots.py`: altitude–time, velocity–time, g-load–time, heat-rate–time, lat-lon
ground track from `FlightData`. Built on `matplotlib.figure.Figure` directly — no pyplot,
no backend, no GUI (a test asserts pyplot is never imported); matplotlib lazy-imported,
declared as the `orp[plot]` extra. Every figure carries a provenance stamp (level +
limiting source).

## Phase 4 — InSight rotation experiment

`insight.yaml`: mass 605.6 kg VERIFIED_FLIGHT (Karlgaard NTRS 20200003204 p. 2; full
extraction of that paper's printed values was done from the downloaded PDF); D = 2.65 m,
70° sphere-cone; nose radius 0.6625 m, trim α = 0, C_D ≈ 1.68 ASSERTED from the Phoenix
aerodynamics paper (Edquist et al. NTRS 20080034648 Fig. 2 / Table 1 — Karlgaard defers
to the Phoenix aerodatabase and prints no geometry/trim numbers).

**Stage A (harness validation): reproduced.** At ω = 0: peak 10.928 g (target 10.93),
crossrange 9.283 km (target 9.28), azimuth-independent to < 5 m across 8 azimuths;
Allen-Eggers 10.63 g. With rotation: azimuth-dependent shifts, peak magnitude
1.04–1.68 km on azimuths 0–90° (the recorded "order 1.0–1.8 km") and peak g 10.11–11.65
(recorded "order 0.5–0.8 g" shifts). **Caveat recorded:** the external expectation's
signed band (−1.0..−1.8 km, 10.1–10.9 g) does not transfer sign-for-sign; the external
reference never locked its bank-sign convention, and under a mirrored sign ORP's
+1.0..+1.68 km at azimuths 0–90° is that band. Documented, not tuned.

**Stage B (full models): reported, not matched.** Peak 7.07 g (ω=0) / 7.05 g (rotating)
vs flight 8.13 g (−13%); crossrange exactly 0 at ω = 0 (L/D = 0 at static trim α = 0 —
no lift + no rotation cannot leave the plane) and +2.26 km rotation-only vs flight
6.1 km, which was driven by rolling lift a static-trim model cannot represent. Every
approximation flagged ([APPROX-ATMOS-A], [APPROX-AERO-A], [APPROX-LIFT], [APPROX-EI],
[APPROX-STATE], [APPROX-TRIM-B]); full tables in `docs/experiments/insight_rotation.md`.

## Tooling notes for future sessions

* NTRS PDFs download fine via `curl.exe` to the gitignored `refs/`; the Read tool cannot
  render PDFs on this machine (no poppler) — use PyMuPDF (`pip install pymupdf`, already
  installed) to extract text and render equation pages to PNG for visual reading.
  Set `$env:PYTHONIOENCODING='utf-8'` for scripts printing extracted PDF text.
* Background subagents cannot pass permission prompts (network/shell denied); do
  network fetches in the main loop, then hand local files to agents.
* PowerShell 5.1 mangles git commit messages containing double quotes; use
  `git commit -F <file>`.

## Open seams / candidate next steps (not started)

* Oscillatory/replayed-attitude lift model for InSight-class bounded-instability entries
  (the stage-B crossrange gap's refinement seam).
* Mars atmosphere thermal structure (Mars-GRAM or two-segment profile).
* Engine termination event interpolation (currently stops on the first at/below-threshold
  step; bridging doc records the ≤ 1 dt end-time difference).
* `AtmosphericConditions.dynamic_viscosity` still returns 0.0 (pre-existing seam).
* If a VERIFIED_CFD/VERIFIED_FLIGHT reconciliation of the atmospheres is ever done, the
  retag ladder is ready for it.
