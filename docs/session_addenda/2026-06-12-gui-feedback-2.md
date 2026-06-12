<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-12 — branch `gui-feedback-2`

Branch `gui-feedback-2` off `master` @ ee7e917 (second round of first-user feedback).
Four commits, full pytest green and the GUI wall test green after every commit; all
new user-facing text under the wall vocabulary rules. Not merged, not pushed.

## Commits

| Commit | Content | Tests |
|---|---|---|
| fa1a7c4 | App icon: programmatic QPainter lettermark (rounded square, palette VERIFIED_SOURCE blue, white "ORP"), rendered 16–256 px, set via QApplication.setWindowIcon in both launch paths; no binary assets committed. | 293 |
| a2389bb | Provenance display dedup. Identity confirmed first: the gray text under the GUI graphs is plots.py's figure-level stamp (dimgray, fig coords 0.01/0.01), duplicating the tab banner. Every plot function gained explicit `stamp_provenance: bool = True`; the GUI tab renderer passes False; every disk-written figure keeps the stamp (a saved image must carry its own provenance); never a global toggle. | 301 |
| 98c7740 | Report Bug / Feedback: `orp/gui/feedback.py` — one URL builder (`[GUI feedback]` title prefix, `bug` label, body = review-first line, ORP version, OS, Python, and only vehicle/planet/frame/schedule-source-type/last-run weakest link; never paths, usernames, or session contents); open via QDesktopServices with a copyable-URL fallback dialog; buttons on all three panels + Help menu, all one function; glossary `feedback` entry states the prefill. No tokens, no network calls, no middleware. | 306 |
| (this) | Vercel landing page: `vercel.json` (static `site/` output, `buildCommand: null`, no framework) + `site/index.html` — single hand-written page, inline CSS, zero JavaScript, no external assets; README-verbatim weakest-link language; validation summary mirrors `orp gates` exactly, Artemis FAIL included; static report-a-bug link with the same title-prefix/label pattern; repo + OpenReentry links; GPL-3.0-or-later; byline Charles Walter Dowd Jr. / OpenSourcePatents LLC. Top-of-file comment: hand-maintained, claims must never exceed the README. `orp/tests/test_site.py` parses vercel.json, requires the honest content, scans the page with THE GUI WALL's negation-aware term list, and rejects scripts/trackers/external assets. | 310 |

## Notes

1. Vercel domain attachment (orp.opensourceforall.com) is a dashboard setting, not a
   repo file; the repo side now produces a successful static deployment (no build
   step, `site/` served as-is).
2. The OpenReentry companion link uses
   `github.com/OpenSourcePatents/openreentry` — inferred from the org and project
   name; correct it on the page if the companion lives elsewhere.
3. Install instructions on the page say clone + `pip install -e ".[gui]"` because ORP
   is not on PyPI; writing `pip install orp` would have been a claim exceeding
   reality.
4. The site test initially failed on its own honesty: the page's "No analytics"
   pledge tripped a literal `"analytics" not in html` check; the test now matches
   real tracker signatures instead.
