<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-12 — branch `run-degrade`

Branch `run-degrade` off `master` @ b949a22. One commit. Not merged, not pushed.

`orp run` now degrades gracefully without matplotlib: the figure-writing step (the
only place matplotlib is imported, lazily, inside `plots.save_standard_plots`)
catches ImportError and prints exactly one line —
`Figures skipped: matplotlib is not installed; install with pip install "orp[plot]"
to enable them.` — while trajectory.csv, session.yaml, and provenance.txt are still
written, the closing summary still prints, and the exit code is 0 because the
simulation itself succeeded. Refusal semantics are untouched: this is a missing
*optional output dependency*, not bad input, so it degrades with an honest notice
instead of failing the run.

Tests: matplotlib poisoned in `sys.modules` → exit 0, the three data outputs
present, zero PNGs, exactly one notice line, summary intact; the matplotlib-present
case (all eight outputs, unchanged) stays covered by the existing end-to-end test.
README Quickstart gained one sentence stating the base install runs simulations and
writes data while figures need the `plot` or `gui` extra.
