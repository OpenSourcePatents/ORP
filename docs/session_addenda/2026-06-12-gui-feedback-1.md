<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-12 — branch `gui-feedback-1`

Branch `gui-feedback-1` off `master` @ 98521ac. **These changes come from first-user
feedback** on the GUI: the wide vehicle table, the missing menu bar, no dark mode,
and no in-place explanations. Four commits, full pytest green and the GUI wall test
green after every commit. Not merged, not pushed, per instruction.

## Commits

| Commit | Content | Tests |
|---|---|---|
| 2a47ee3 | Vehicle panel: vertical provenance cards (bold name / value / color-coded tag chip / word-wrapped citation) in a vertical-only QScrollArea — no horizontal scrollbar possible; content fills the previously dead lower half. | 282 |
| 614b004 | Menu bar: File (Save Session, Export Trajectory CSV, Exit — same slots as the panel buttons, which stay) and Runs (New Run resets the conditions panel; session-scoped in-memory run history, selecting an entry restores that run's results panels from `AppState.run_history`, FlightData restored by object identity; nothing persisted). | 286 |
| a86bee2 | Settings → Theme → Light/Dark (checkable, exclusive): dark QPalette + matplotlib `dark_background`, all eight plot tabs re-render with the chrome; Light restores both; light on launch, no QSettings. | 287 |
| (this) | `orp/gui/glossary.py` + (i) info icons everywhere (hover = tooltip, click = popover); addendum. | 292 |

## The glossary (content, not chrome)

All definitions live in one reviewable module, `orp/gui/glossary.py`. The
provenance-related entries restate the documented meanings **exactly** and the test
suite pins them verbatim: every `ValidationLevel.description` from
`orp/core/provenance/tags.py` must appear inside its entry, MACHINE-DIGITIZED must
contain "pixel extraction from a published figure; not flight telemetry"
(the dataset header's wording), the weakest-link entry must contain "a trajectory is
only as trustworthy as the weakest input that produced it", and the heading entry
states "an input, not a target". The wall scanner (negation-aware, same as THE GUI
WALL) runs over every glossary string; icon coverage is asserted both ways (every
key renders in the GUI, every icon resolves to a non-empty entry that is its
tooltip). Icons fail construction on unknown keys, so none can dangle.

## Defects found and fixed along the way

1. `matplotlib.style` is a submodule: the bare attribute access in `apply_theme`
   raised inside a Qt slot, which PyQt6 escalates to a process abort (0xC0000409).
   Explicit `import matplotlib.style` fixes it; the standalone repro is in the
   commit message of a86bee2.
2. Repeated plot refreshes queue `deleteLater` canvas deletions that, without an
   event loop, Qt destroys in arbitrary order at interpreter exit and crashes on
   Windows. The GUI tests now flush `DeferredDelete` events after every test
   (autouse fixture).

## Notes

- The summary table gained a third (icon) column and static rows; values fill on
  refresh, so the quantities and their definitions are visible before the first run.
- The frame row carries one icon per frame meaning (planet-relative, inertial) next
  to the selector, and the vehicle panel gained a five-level color legend with one
  icon per ValidationLevel — that is what guarantees every provenance definition is
  reachable in the UI, not just the levels the current vehicle happens to use.
