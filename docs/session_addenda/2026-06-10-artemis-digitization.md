<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — artemis-digitization (2026-06-10)

Branch `artemis-digitization` off `master` @ 9f9af31. Four commits, 191 tests green at
every commit. NOT merged, NOT pushed (per instruction). Reference scratch (rendered
pages, blind transcripts, extraction tooling) lives in gitignored `refs/`.

## Part 0 — full-history secrets scan (report only, no commit)

Scanned all 222 git objects (every ref + reflog-reachable + unreachable; no binary
blobs exist in history), `git log -p`-equivalent content, reflog, stash (empty),
`.git/config` / FETCH_HEAD, with pattern + entropy detection. **No credentials of any
kind**: no API keys/tokens/JWTs/PEM/SSH keys/passwords/basic-auth URLs/phone numbers.
All 97 high-entropy candidates adjudicate to git SHAs and GitHub web-flow GPG
signature blocks (public by nature). Findings to weigh before the public flip:

1. **Identity disclosure (review before flip):** `pyproject.toml` authors field carries
   the maintainer's real name + personal email while the commit identity is the
   pseudonymous OpenSourcePatents account — confirm this pseudonymity break is
   intentional.
2. **Co-Authored-By trailer in public-bound history:** the root code commit `bc1a3dd`
   ("ORP skeleton...") carries "Co-Authored-By: Claude Opus 4.8 (1M context)
   <noreply@anthropic.com>" — it is reachable from master and already on origin.
   Removing it requires a history rewrite; later commits comply with the no-trailer
   rule.
3. **Private absolute paths with the OS username** in committed files:
   `orp/tests/test_bridge_openreentry.py` (skip message), `docs/verification/
   bridge_openreentry_gate.md` (clone source), `reference/models.md` (file references).
   Path style also correlates the username with the real name in pyproject.

## Part 1 — dual-channel pixel-vs-text transcription verification (commit 2096242)

19 blind transcription assignments (images-only contract, 300–1400 DPI, fresh
transcript files written BEFORE any inventory was opened) over AAS 24-174, AAS 13-307,
Mitcheltree 97-2304, McNamara 20140004224, Desai & Qualls 20080008567, CR-149170 Ch. 2,
Phoenix 20080034648; then diffed against PDF text layers + repo citations.

- **DUAL-CHANNEL VERIFIED:** AAS 24-174 Tables 1–4 (incl. the miss-distance column —
  bare integers 1/1/2 nmi at 1200 DPI), skip apogee 287.4/293.5 kft, the p.11
  estimator percentages (~10% less dense, ~5% less L/D), the p.4 initial-roll 0°/15°
  statement; McNamara Table 3; all Desai & Qualls gate truths (now text-pinned, no
  longer "lit"); Mitcheltree OML; AAS 13-307 Tables 1–3 + EIP 3522.2 km + 695 Pa;
  CR-149170 equations/conventions underpinning the EOM verification doc; Phoenix
  values feeding insight.yaml.
- **One real DISCREPANCY, corrected:** Stardust `CD 1.61` attributed to Mitcheltree
  appears nowhere in that source (zero text-layer hits; full pixel transcription of
  Tables 4/5/6 gives zero-AoA continuum C_A 1.4816–1.5636). Replaced with the Table-4
  LAURA continuum mean **1.50** across yaml/docs/map/test. Stardust gate re-run:
  peak 32.0–32.4 g (truth 32.89 ± 3.64 — still within 3σ), M1.23 altitude improved to
  ~31.6 km vs truth 31.03. Citation correction, not tuning; both states recorded.
- **Source anomalies recorded:** AAS 13-307 is the MSL/MEADS reconstruction (new
  inventory doc `docs/sources/msl_aas13-307_karlgaard_meads.md`); its θ-sigma cell
  prints `6.76E-4` verbatim in both channels but is doubly typographically anomalous
  with a mantissa adjacent to its row-mate's `6.78e-05` — recorded as SUSPECTED SOURCE
  TYPO for e-05 (nothing in ORP consumes it). Phoenix Table 1 prints X_cg/D −0.25 vs
  −0.253 in every figure box. ref_core cites AAS 13-307 under a different NTRS
  accession (20130003195 vs 20130010087).
- Transcription-status lines appended to every affected inventory/source doc/yaml.

## Part 2 — Artemis bank-schedule digitization (commit bf30b50)

`data/flights/artemis1_bank_commanded.csv` (MACHINE-DIGITIZED, 0.5-s grid, occlusion
gaps marked never interpolated), extracted from Fig 12(a)'s native embedded raster
(pure-color, no antialiasing; gridline-ladder calibration, residuals <0.4 px). All
mandatory gates passed: six Table-3 reversal times within −0.67…−0.07 s (gate ±2 s);
sign-constant segments; initial segment +14.9° matching the p.4 verbatim statement;
8 blind vision spot-reads (max dev 11.8° at the single ramp point, ≤4.84° at all 7
static points). Independent Fig 19 digitization: constant-segment RMS 0.2–0.7°;
**discovered Fig 19's published time base leads Fig 12(a)/Table 3 by ~5.3–5.8 s**
(reversal intervals agree to ~0.1 s — pure epoch offset in the publication; Fig 12(a)
matches Table 3 and is the authoritative channel). Methods + uncertainty:
`docs/digitization/artemis1_bank_commanded.md`.

## Part 3 — Gate-3 replay (commit 5bfbe58): honest FAIL, convention NOT locked

Pre-registered tolerances were written before any comparison ran. First run exposed
the ISA >86 km clamp (~300× density overestimate at the 121.92-km EI) — replaced with
a **US76 thermospheric extension 86–250 km** (`orp/core/atmosphere/us76_highalt.py`),
pixel-transcribed from NTRS 19770009539 Table I, VERIFIED_SOURCE, 17 tests (the
printed 95-km row is reproduced by the log-linear interpolation choice).

Outcome across the full sourced space (mass × L/D sweep, both sign mappings,
0.90×ρ/0.95×L/D flight-informed variant): the first pass under-bleeds (peak 2.70–2.93 g
vs flight 4.03 g per the Fig 10(a) callout; exit 9.16–9.37 km/s vs ~7.87 needed for the
287.4-kft apogee) and the vehicle skips out without returning → endpoint metrics
unreachable → **FAIL against every pre-registered tolerance; bank-sign convention NOT
LOCKED** (both mappings are vertically identical, cos σ even). Quantified root-cause
class: open-loop, constant-coefficient, instant-bank 3-DOF replay of closed-loop
commands in the divergent skip regime; sourced sweeps move exit speed ~±110 m/s, two
orders below the 1.4 km/s gap. The dataset keeps its plotted-sign-only caveat and the
**[APPROX-ROTATION]** flag for OpenReentry export (recorded verbatim in
`docs/gates/gate3_artemis_replay.md` §6). Unlock path: digitize Orion CD/CL-vs-Mach
(Bibb NTRS 20110013644), bank-rate-limited replay, achieved-bank (green-trace) replay,
or a published mid-flight state for a second-entry-only replay. Tests pin the honest
outcome so it cannot silently regress.

## Session notes

- Five of seven diff agents were killed mid-Part-1 by the account's monthly spend
  limit; the remaining diffs were completed inline in the main session with identical
  protocol (text-layer greps + cell-by-cell comparison). Recorded for methodology
  transparency.
- Stardust gate still runs the clamped ISA (its EI is steep; results barely move) —
  switching it to the US76 extension is a one-line follow-up left deliberate.
- The Fig 12(a) green ACHIEVED-bank trace is digitizable with the existing pipeline
  and is the cheapest next experiment for the replay gap.
