# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the static guide site (site/index.html + vercel.json).

The landing page is content under the same honesty rules as the app: claims must
never exceed the README, validation statuses mirror the gates' honest states, and
the wall vocabulary rules apply — the scan reuses THE GUI WALL's term list and
negation-aware scanner.
"""

from __future__ import annotations

import json
from pathlib import Path

from orp.tests.test_gui_wall import _violations

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestVercelConfig:
    def test_vercel_json_parses_and_serves_site_statically(self) -> None:
        config = json.loads((_REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))
        assert config.get("outputDirectory") == "site"
        assert config.get("buildCommand") is None  # static output, no build step
        assert config.get("framework") is None


class TestLandingPage:
    def _html(self) -> str:
        page = _REPO_ROOT / "site" / "index.html"
        assert page.is_file(), "site/index.html is missing"
        return page.read_text(encoding="utf-8")

    def test_no_endpoint_seeking_vocabulary(self) -> None:
        """Reuses the GUI wall term list (negation-aware) over the whole page."""
        html = self._html()
        violations = _violations(html)
        assert not violations, f"wall vocabulary on the landing page: {violations}"

    def test_honest_content_present(self) -> None:
        html = self._html()
        # Hand-maintained guard comment.
        assert "Claims on this page must never exceed the README" in html
        # Install instructions with the gui extra and the launch line.
        assert 'pip install -e ".[gui]"' in html
        assert "orp gui" in html
        # Validation summary mirrors the gates' honest states, Artemis FAIL included.
        assert html.count("NOT_VALIDATED") >= 3
        assert "FAIL" in html
        assert "pre-registered tolerances" in html
        assert "NOT LOCKED" in html
        assert "0 of 3 gates validated" in html
        # The README's weakest-link language, verbatim.
        assert "a trajectory is only as trustworthy as the weakest input" in html
        # Report-a-bug link: same prefilled pattern, static (title prefix + label only).
        assert (
            "https://github.com/OpenSourcePatents/ORP/issues/new?"
            "title=%5BGUI+feedback%5D+&amp;labels=bug" in html
        )
        # Repos, license, byline.
        assert "https://github.com/OpenSourcePatents/ORP" in html
        assert "https://github.com/OpenSourcePatents/OpenReentry" in html  # canonical casing
        assert "GPL-3.0-or-later" in html
        assert "Charles Walter Dowd Jr. / OpenSourcePatents LLC" in html

    def test_no_scripts_trackers_or_external_assets(self) -> None:
        html = self._html().lower()
        assert "<script" not in html  # no JavaScript at all
        # Real tracker signatures (the page's own "no analytics" pledge is allowed).
        for tracker in ("gtag(", "googletagmanager", "google-analytics", "plausible.io",
                        "posthog", "segment.com", "hotjar", "matomo"):
            assert tracker not in html, f"tracker signature {tracker!r} on the page"
        assert 'src="http' not in html and "src='http" not in html
        assert '<link rel="stylesheet"' not in html  # CSS is inline only
        assert "@import" not in html
        assert "fonts.googleapis" not in html and "cdn." not in html
