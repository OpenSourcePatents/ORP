# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bug/feedback reporting: one function that builds a pre-filled GitHub issue URL.

PRIVACY CONTRACT (tested): the pre-filled body contains the ORP version, the OS name
and release, the Python version, and — from AppState only — the vehicle name, planet,
frame, schedule source TYPE, and the last run's weakest-link level. Never file paths,
never usernames, never session contents, never anything else. The body's first line
tells the user to review and edit before submitting. No tokens, no network calls from
the app, no middleware: the URL opens in the user's browser and nothing is sent until
they submit on GitHub themselves.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PyQt6.QtWidgets import QWidget

    from orp.gui.app_state import AppState

__all__ = ["FEEDBACK_REPO", "feedback_url", "open_feedback"]

FEEDBACK_REPO = "OpenSourcePatents/ORP"
_TITLE_PREFIX = "[GUI feedback] "
_LABEL = "bug"


def feedback_url(state: "AppState | None" = None) -> str:
    """The GitHub new-issue URL with the pre-filled, user-reviewable report body."""
    import orp

    lines = [
        "Please review and edit this report before submitting - remove anything "
        "you do not want to share.",
        "",
        f"- ORP version: {orp.__version__}",
        f"- OS: {platform.system()} {platform.release()}",
        f"- Python: {platform.python_version()}",
    ]
    if state is not None:
        schedule_kind = (
            state.schedule_source.kind if state.schedule_source is not None else "none"
        )
        weakest = (
            state.flight_data.provenance.level.name
            if state.flight_data is not None
            else "no completed run"
        )
        lines += [
            f"- Vehicle: {state.vehicle_name or 'none'}",
            f"- Planet: {state.planet_name}",
            f"- Frame: {state.frame}",
            f"- Schedule source type: {schedule_kind}",
            f"- Last run weakest-link provenance: {weakest}",
        ]
    lines += ["", "**What happened:**", "", "**What I expected instead:**", ""]
    query = urlencode(
        {"title": _TITLE_PREFIX, "labels": _LABEL, "body": "\n".join(lines)}
    )
    return f"https://github.com/{FEEDBACK_REPO}/issues/new?{query}"


def open_feedback(state: "AppState | None" = None, parent: "QWidget | None" = None) -> bool:
    """Open the pre-filled issue in the browser; on failure show the URL to copy."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    url = feedback_url(state)
    if QDesktopServices.openUrl(QUrl(url)):
        return True

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setWindowTitle("Report Bug / Feedback")
    box.setText(
        "Could not open a browser. Copy this URL to file the report manually:"
    )
    box.setInformativeText(url)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.exec()
    return False
