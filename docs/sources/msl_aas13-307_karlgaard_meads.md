<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Source inventory — MSL EDL trajectory & atmosphere reconstruction (AAS 13-307)

**Citation.** Karlgaard et al., "Mars Science Laboratory Entry, Descent, and Landing
Trajectory and Atmosphere Reconstruction" (MEADS/MEDLI Kalman-filter reconstruction),
AAS 13-307.
**NTRS accession:** `20130010087` (PDF at `C:\Users\cjdow\projects\openre\sources\`;
confirmed 2026-06-10). NOTE: the pinned OpenReentry clone (`ref_core/README.md`) cites
the same paper as NTRS `20130003195` (and J. Spacecraft & Rockets, 10.2514/1.A32770) —
two accessions appear to exist; the discrepancy is recorded, not adjudicated.

**Identity note.** A prior session prompt framed AAS 13-307 as an Orion paper; the pixels
are unambiguous that it is the MSL (Curiosity) EDL reconstruction — MEADS, Gale crater,
Mars radii throughout. ORP itself cites nothing from this paper yet (msl.yaml's aero
inventory is AAS 13-306); this inventory exists because the paper is load-bearing for the
OpenReentry bridge reference and was in scope for dual-channel verification.

## Dual-channel verified values (blind pixel transcript vs PDF text layer, 2026-06-10)

- **Table 1 — MEADS Systematic Error Estimates** (p. 16): all 7 ports × (bias Pa, scale
  factor, nonlinearity 1/Pa) — 21 cells verified exactly, e.g. port 1: −3.19 / 1.54E-03 /
  −1.83E-08. Inline capital-E notation in the source.
- **Table 2 — Initial Conditions** (p. 18): all rows (r, φ, θ, u, v, w, Φ, Θ, Ψ; OD/Nav
  vs Filter, each with 1σ) verified exactly. r: 5082657.04 / 5082655.62 m.
- **Table 3 — Landing Site Location** (p. 18): verified exactly. Filter r 3391157.7 m
  (1σ 2.7 m), φ −4.5898°, θ 137.4406°.
- **EIP definition** (p. 3): "the Entry Interface Point (EIP) defined at 3522.2 km from
  the center of Mars". Figure-2 callout (raster-only, pixel channel): altitude 125.0 km,
  velocity 5.8 km/s.
- **Surface pressure** (p. 10): "tuned to match surface pressure measurements of 695 Pa
  from Curiosity". (ORP's `mars.py` anchor remains the Viking 636 Pa / 210 K datum —
  different site/mission; no conflict.)

## The θ-sigma 6.76E-4 question — resolved from pixels

Table 2, θ row, Filter-Estimates 1σ column prints, character by character at 1400 DPI:
**`6.76E-4`** — inline uppercase E, single-digit exponent, no leading zero. The PDF text
layer agrees. So the source genuinely prints E-4; it is not an extraction artifact.
However the cell is doubly anomalous (the only single-digit exponent on the page; every
other sci-notation cell uses two-digit leading-zero exponents) and its row-mate OD/Nav
value is `6.78e-05` with a nearly identical mantissa, while the φ row's filter
uncertainty is unchanged from OD/Nav. Internal evidence therefore strongly suggests an
**exponent typo for 6.76E-05**; the pixels cannot prove intent. Status: source prints
6.76E-4 (DUAL-CHANNEL VERIFIED as printed); flagged SUSPECTED SOURCE TYPO. Nothing in
ORP consumes this value.

## Transcription status (2026-06-10)

DUAL-CHANNEL VERIFIED (Tables 1–3, EIP radius, surface pressure) with the 6.76E-4
anomaly recorded above. Pixel channel: blind transcripts (session scratch
refs/transcripts/aas13307-*.md); text channel: PDF text-layer dump
(openre/sources/aas13-307.txt).
