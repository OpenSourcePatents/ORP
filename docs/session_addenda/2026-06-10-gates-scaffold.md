<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-10 — `gates-scaffold`

Branch **`gates-scaffold`**, based at **77b830a** (the codebase tip; `origin/skeleton` /
`origin/eom-invariants`). **Not merged, not pushed**, per instructions.

> **Repo-state note.** The task described "master at 77b830a." In this clone, both local and
> `origin/master` are at **f7c7bda** (the pre-code OpenRocket-reference commit); the codebase
> lives on `skeleton`/`eom-invariants` at 77b830a. master was therefore *not* used as the
> base and was *not* modified (no merge/push). If master is meant to track the work, it still
> needs a fast-forward to 77b830a.

Rules honored: no Co-Authored-By trailers; explicit-path `git add` only; full pytest green at
every commit (**164 passed**); SPDX on every new file; forward-only wall (bank schedules are
inputs, crossrange is an output, nothing accepts a target endpoint).

## Phase 1 — research intake (`docs/sources/`, `docs/data_availability_map.json`)
NTRS accessions pinned; D-4185-style inventories written (sourced-text vs figure-only tags):
- **AAS 13-419** Mendeck & McGrew, MSL commanded bank → NTRS **20130009519**.
- **AAS 13-306** Schoenenberger, MSL flight aero → NTRS **20130010088**.
- **AIAA 97-2304** Mitcheltree, Stardust aero → NTRS **20040105538**; OML + hypersonic CD
  text-extracted (60° sphere-cone, Rn 0.2286 m, D 0.8128 m, area 0.51887 m², CD≈1.61).
- **AIAA 2008-1201** Trumble, Stardust postflight aerothermal → **ABSENT from NTRS** (recorded
  explicitly); available via AIAA ARC doi:10.2514/1.41514.

## Phase 2 — Gate 3 Artemis scaffold (NOT_VALIDATED)
- `orp/core/frames.py`: `inertial_to_planet_relative()` (honest by construction — refuses on
  missing data) + `great_circle_bearing()`. Verified against AAS 24-174 (NTRS 20240000024):
  Table 1 inertial EI → relative azimuth **2.423°**, inside the **0.94018°** lateral corridor
  of the **2.195°** great-circle bearing to the Table 4 splashdown (bearing computed from
  sourced coords).
- `orp/gates/gate3_artemis.py`: encodes Tables 2 (phase times), 3 (reversals), 4 (endpoints),
  skip apogee 287.4 kft. `bank_schedule()` raises `NotImplementedError` — the
  convention-laundering rule: reversal *times* with a guessed initial *sign* do not lock a
  sign convention; the bank command (Fig 12(a)) needs human digitization.
- `orion.yaml`: mass range 9934–10387 kg, L/D 0.23–0.27 (midpoints stored, ranges in source)
  citing McNamara NTRS 20140004224; aero citing Bibb NTRS 20110013644; trim attitude
  figure-only → NOT_VALIDATED (vehicle's honest weakest link).

## Phase 3 — Stardust gate (forward sim; NOT_VALIDATED)
- `stardust.yaml` from Mitcheltree (ASSERTED) + reconstruction inputs.
- `orp/gates/gate_stardust.py`: ballistic forward run, rotation on, sourced CD; EI-latitude
  sweep. **Peak 32.3–32.8 g** vs flight **32.89 ± 3.64 g (3σ)** ✓; Mach 1.23 at ~32 km
  (truth 31.03); ~133 s to M1.23 (drogue 137.9 s). EI latitude is a weak sensitivity
  (0.47 g). **Centrifugal shallowing demonstrated:** flat-Earth Allen-Eggers ~60 g vs ORP
  curved ~32 g (external ref ~73 g no-curvature / ~38 g crude-curved; flight 32.89 g). Report:
  `docs/gates/stardust_gate.md`.

## Commits (this branch)
`faaa083` P1 · `5cd335f` P2a (frames) · `7db6053` P2b (gate3 + orion) · `ad3b2b0` P3 (Stardust)
· this addendum.

## Open items / not done
- Artemis bank command (Fig 12(a)) digitization → unlocks the Gate-3 skip trajectory.
- MSL bank profile (AAS 13-419) and reconstructed aero (AAS 13-306) are figure-only; a Mars
  guided-entry gate is future work.
- Stardust gate approximations: assumed EI latitude, constant hypersonic CD (CD-vs-Mach is
  figure-only), ISA held constant above 86 km (EI ~132 km), 3-DOF point mass.
- Earth atmosphere above 86 km: ISA clamp is a known limitation for high-altitude EIs.
