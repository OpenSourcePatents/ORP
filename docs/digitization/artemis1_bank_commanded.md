<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Methods & uncertainty — Artemis I commanded bank schedule (MACHINE-DIGITIZED)

**Dataset:** `data/flights/artemis1_bank_commanded.csv`
**Tag:** MACHINE-DIGITIZED — pixel extraction from a published figure, not flight telemetry.
**Source:** AAS 24-174 ("Orion Artemis I Entry Performance", NTRS 20240000024),
Figure 12(a), blue "Commanded Bank Angle" trace. Cross-validation source: Figure 19,
red "Command" trace, digitized fully independently.
**Date:** 2026-06-10.

## 1. Pre-extraction figure metadata (recorded BEFORE any extraction)

Per the mandatory digitization order, the axis labels, units, tick values, legends, and
the sign convention as the figures define it were read from pixels and written down
before any calibration or masking was run. Record (verbatim):

### Figure 12(a) — PDF page 12, embedded raster xref 402, native 1554x1263 px
- Page caption: "Figure 12: Artemis I Bank Angle vs. Time Relative to EI";
  subcaption "(a) Whole Atmospheric Entry".
- Plot title: "Bank Angle vs. Time".
- X axis: "Time Relative to EI (s)"; ticks 0, 200, 400, 600, 800, 1000, 1200.
- Y axis: "Bank Angle (d)" — the label is CLIPPED IN THE SOURCE IMAGE itself (the
  glyphs after "(d" are cut off); Figure 19's y-label "Bank Angle (deg)" and the
  +/-200 tick range imply degrees.
- Y ticks: -200, -150, -100, -50, 0, 50, 100, 150, 200.
- Legend: blue = "Commanded Bank Angle"; green = "Bank Angle";
  red = "FBC Pilot Chute Deploy" (vertical event line at t ~ 950 s).
- Sign convention AS DEFINED BY THE FIGURE: bank angle is plotted SIGNED in degrees,
  -200..+200; initial commanded segment small POSITIVE (~+15 deg); first reversal
  positive-to-negative. **The figure does not print a left/right-of-track meaning for
  the sign, and the paper text never defines one** (pages 3–7 searched verbatim; the
  only directional language is "switches command to lift-down", p. 4, and a
  sign-comparison sentence on p. 7). The dataset therefore preserves the PLOTTED sign
  as-is; the physical meaning of the sign is locked only at the Gate-3 crossrange
  comparison. Flagged for export to OpenReentry's [APPROX-ROTATION] caveat.

### Figure 19 — PDF page 16, embedded raster xref 509, native 1554x867 px
- Page caption: "Figure 19: Bank Tracking".
- X axis: "Time Relative to EI (s)", ticks 0..900 by 100. Y axis: "Bank Angle (deg)",
  ticks -150..150 by 50.
- Legend: blue = "Bank Angle"; red = "Command"; green band = "Bank Reversal"
  (six numbered bands). COLOR ROLES ARE SWAPPED relative to Fig 12(a).

## 2. Method

1. **Native-pixel extraction.** Both figures are embedded rasters; the exact source
   pixels were extracted from the PDF (no re-rendering/resampling). Fig 12(a) uses pure
   unantialiased colors: blue exactly (0,0,255), green (0,128,0), red (255,0,0),
   gridlines (229,229,229) — color masking is exact (`B - max(R,G) > 60` etc.).
2. **Calibration.** Linear px→data maps fit on gridlines via ladder assignment
   (tolerates gridlines occluded by traces — e.g. the t=400 line under the ±180° wrap),
   anchored on axis lines carrying a labeled tick (Fig 12(a): left axis = t 0, bottom
   axis = −200 deg). Fit residuals < 0.4 px on every axis. Pixel pitch: 0.947 s/px,
   0.374 deg/px (Fig 12(a)); 0.789 s/px, 0.509 deg/px (Fig 19). Sanity anchors: t at
   left axis −0.64 s; top/bottom edges ±200.4 deg. Fig 19's x-ladder was confirmed
   against its printed tick labels and its six "Bank Reversal" bands, which bracket the
   Table-3 reversal times under this calibration.
3. **Column-wise trace extraction.** For each pixel column inside the plot box
   (legend box masked out): no masked pixel → `gap`; vertical run > 9 px → `transition`
   (step connector); else value = run center. Commanded bank is piecewise constant, so
   steps appear as transition columns and occluded stretches as gaps. **Gaps are
   marked, never interpolated.** Fig 12(a) columns: 979 ok / 209 gap_occluded /
   183 transition (the green actual-bank trace is drawn over the blue command and hides
   it wherever they coincide).
4. **CSV export.** 0.5 s grid, nearest-pixel-column sampling (no interpolation; column
   pitch 0.947 s, so consecutive grid points may share a source column —
   `source_col_time_s` records it). Value empty wherever flag != ok. Replay guidance:
   hold the last `ok` value through gap/transition samples.

## 3. Validation gates (all mandatory, all PASS)

### 3a. Sign flips within ±2 s of all six Table 3 reversal times
Flip-time estimator: zero-crossing transition columns between the bracketing valid
samples (the vertical step connector crosses y=0 at the command step instant);
half-uncertainty = max(spread/2, 1 column).

| Reversal | Table 3 (s) | Extracted (s) | Δ (s) | PASS (±2 s) |
|---|---|---|---|---|
| 1 | 115.475 | 114.867 | −0.61 | ✓ |
| 2 | 390.450 | 390.379 | −0.07 | ✓ |
| 3 | 713.425 | 713.229 | −0.20 | ✓ |
| 4 | 793.425 | 792.758 | −0.67 | ✓ |
| 5 | 827.425 | 826.842 | −0.58 | ✓ |
| 6 | 864.400 | 863.767 | −0.63 | ✓ |

Max |Δ| = 0.67 s. (Table 3 times themselves were dual-channel verified this session:
blind 600-DPI pixel transcription and PDF text layer agree on every cell.) A seventh
sign change at 892.6 ± 1.4 s is the terminal transition to the post-guidance −75 deg
hold (PredGuid Terminal at 882.400 s per Table 2), not a guided reversal: 6 reversals +
1 terminal transition = exactly the expected count; no spurious flips anywhere.

### 3b. Sign-constant segments between reversals
Segments 1–6 (between EI and reversal 6) are sign-constant in every valid sample
(72/242/301/52/15/8 samples). The post-reversal-6 stretch (867–902 s) has zero valid
samples (fully occluded by the actual-bank trace) — its sign-constancy is evidenced by
the connector method instead: the only zero-crossing in it is the terminal transition
at 892.6 s. PASS.

### 3c. Initial segment vs the paper's statement
Extracted initial command (1–60 s): +14.91 deg mean, range [+14.53, +15.28] — i.e. the
+15 deg limit value with sub-pixel scatter. Paper, p. 4 (read blind from pixels,
verbatim): "The pre-selected bank angle command was 0°, however PredGuid preserves
lateral capability by limiting the bank command to 15°." Consistent: the commanded
magnitude is the 15° limit, plotted at +15. PASS.

### 3d. Fig 19 independent digitization — RMS as extraction uncertainty
Fig 19's red Command trace was digitized with its own calibration and masks. Findings:

- **Constant-command segments agree to RMS 0.2–0.7 deg** (per-50 s bins over the holds;
  e.g. 200–350 s: 0.2–0.5 deg). This is the amplitude-channel extraction uncertainty.
- **Fig 19's traces lead Fig 12(a) by a near-constant epoch offset**: per-reversal lead
  4.9–5.7 s (mean 5.3 s), global RMS-minimizing shift +5.8 s. Reversal-to-reversal
  INTERVALS agree across Fig 12(a), Fig 19, and Table 3 to ~0.1 s, so this is a pure
  time-origin inconsistency in the published Fig 19, not an extraction error — and
  Fig 12(a) is the channel that matches Table 3 (≤0.67 s). The dataset uses Fig 12(a)
  timing exclusively.
- Raw cross-figure RMS (no shift): 35.0 deg — dominated by step misalignment under the
  epoch offset. After the +5.8 s alignment: 19.0 deg full-overlap (residual ramps),
  2.2 deg over flat windows (p95 1.6 deg). Reported per the gate definition: raw RMS
  35.0 deg; epoch-aligned flat-window RMS 2.2 deg; constant-segment RMS 0.2–0.7 deg.

### 3e. Vision spot-reads vs programmatic curve
8 blind spot-reads (fresh readers, given only a y-axis ruler + one narrow time slice
each, no access to the extracted curve):

| t (s) | vision (deg) | programmatic (deg) | dev (deg) |
|---|---|---|---|
| 50 | 13.5 ± 4 | 14.90 | −1.40 |
| 220 | −83 ± 4 | −85.31 | +2.31 |
| 320 | −88 ± 5 | −91.29 | +3.29 |
| 480 | 91 ± 4 | 91.19 | −0.19 |
| 640 | 60 ± 4 | 60.34 | −0.34 |
| 750 | −50 ± 8 | −38.19 (nearest valid, 1.1 s away) | −11.81 |
| 810 | 77 ± 8 | 80.72 | −3.72 |
| 935 | −70 ± 5 | −74.84 | +4.84 |

**Maximum deviation: 11.81 deg**, at the one deliberately-dynamic point (t=750 s sits
on a ~10 deg/s ramp where the exact column is a transition; the nearest valid sample is
1.1 s away — slope-corrected the read is consistent within ~2 deg). All 7 static-point
reads within ±4.84 deg; mean |dev| 3.5 deg.

## 4. Uncertainty statement (for consumers)

- **Amplitude:** ±1 deg (95%) on constant-command holds (pixel quantization 0.37 deg/px;
  cross-figure constant-segment RMS 0.2–0.7 deg). During maneuvers, instantaneous values
  carry slope × timing uncertainty (up to ~10 deg at ~10 deg/s ramps).
- **Timing:** ±1 s (reversal connectors; validated ≤0.67 s against Table 3). Pixel
  column pitch 0.947 s.
- **Coverage:** plotted domain ~1.3–1210 s rel. EI; 209 of 1371 columns occluded
  (marked, not interpolated), concentrated where the actual bank tracked the command
  exactly (notably 830–905 s).
- **Known publication inconsistency:** Fig 19's time base leads Fig 12(a)/Table 3 by
  ~5.3–5.8 s (documented above; dataset unaffected — built solely from Fig 12(a)).

## 5. Sign convention lock (for Gate 3 / OpenReentry export)

The dataset's sign is the figure's plotted sign, nothing more. AAS 24-174 never defines
the bank sign convention in text — the convention is lockable only by replaying the
schedule through a sim whose own convention is pinned (ORP: σ_ORP positive banks lift
toward compass-positive heading change, i.e. dψ/dt > 0 North→East, per
docs/verification/eom_vinh_culp_cr149170.md §2) and comparing the resulting crossrange
against the Table-4 endpoints — Gate 3, PART 3 of this session. Until that comparison
is recorded, treat the sign as plotted-sign-only. Flag carried for OpenReentry's
[APPROX-ROTATION] caveat.
