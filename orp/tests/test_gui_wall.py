# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""THE GUI WALL — this test is never to be weakened.

Walks every QWidget, QAction, QLabel, QLineEdit, QComboBox, menu item, table cell,
and combo entry in the constructed ORP GUI and asserts that no user-facing string —
text, objectName, toolTip, whatsThis, windowTitle, placeholder, status tip, or
title — matches endpoint-seeking vocabulary: target, landing point, splashdown aim,
solve, guidance, or their semantic equivalents. If this test fires, someone is
building (or describing) an interface that accepts a desired endpoint and produces
controls, which is permanently out of scope for ORP.

One deliberate, spec-mandated carve-out (NOT a weakening): a forbidden term is
allowed when it appears in an explicit negation — e.g. the required heading label
"Initial heading (input, not target)" and its tooltip. Disclaimers like that are the
wall's own signage; the scanner therefore accepts a term only when it is immediately
preceded by "not"/"never"/"no". Extending the term list is always allowed; shrinking
it, or widening the negation window, is never allowed.
"""

from __future__ import annotations

import os
import re

# Headless before any Qt / matplotlib import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest

pytest.importorskip("PyQt6", reason="GUI tests require PyQt6")

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QComboBox, QTableWidget

from orp.gui.app_state import AppState
from orp.gui.main_window import MainWindow

# Endpoint-seeking vocabulary (lowercase). Extending is allowed; shrinking is not.
_FORBIDDEN_TERMS = (
    "target",
    "landing point",
    "landing-point",
    "landing_point",
    "splashdown aim",
    "splashdown-aim",
    "splashdown_aim",
    "solve",
    "guidance",
    "aimpoint",
    "aim point",
    "aim-point",
    "waypoint",
    "destination",
    "desired",
    "goal",
    "setpoint",
    "steer",
    "retarget",
    "miss distance",
    "miss-distance",
    "miss_distance",
    "optimi",
    "touchdown",
    "impact point",
)

#: A term is tolerated only when explicitly negated right before it ("not a target").
_NEGATION_BEFORE = re.compile(r"(\bnot\b|\bnever\b|\bno\b)\W{0,12}$")


def _violations(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for term in _FORBIDDEN_TERMS:
        for match in re.finditer(re.escape(term), lowered):
            window_before = lowered[max(0, match.start() - 24) : match.start()]
            if not _NEGATION_BEFORE.search(window_before):
                found.append(term)
    return found


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


_TEXT_GETTERS = (
    "text",
    "objectName",
    "toolTip",
    "whatsThis",
    "windowTitle",
    "placeholderText",
    "statusTip",
    "title",
)


def collect_gui_texts(root: QObject) -> list[str]:
    """Every user-facing string reachable from ``root`` (the walk is generic, so
    future widgets and panels are covered without editing this test)."""
    texts: list[str] = []
    for obj in (root, *root.findChildren(QObject)):
        for getter in _TEXT_GETTERS:
            fn = getattr(obj, getter, None)
            if not callable(fn):
                continue
            try:
                value = fn()
            except Exception:
                continue
            if isinstance(value, str) and value:
                texts.append(value)
        if isinstance(obj, QComboBox):
            texts.extend(obj.itemText(i) for i in range(obj.count()))
        if isinstance(obj, QTableWidget):
            for column in range(obj.columnCount()):
                header = obj.horizontalHeaderItem(column)
                if header is not None:
                    texts.append(header.text())
            for row in range(obj.rowCount()):
                for column in range(obj.columnCount()):
                    item = obj.item(row, column)
                    if item is not None:
                        texts.append(item.text())
    return texts


def assert_wall_holds(root: QObject) -> None:
    texts = collect_gui_texts(root)
    assert texts, "GUI walk collected no strings - the walk looks broken"
    offending = [
        (text, terms) for text in texts if (terms := _violations(text))
    ]
    assert not offending, (
        "THE GUI WALL: endpoint-seeking vocabulary found in the GUI surface: "
        + "; ".join(f"{terms} in {text!r}" for text, terms in offending)
    )


class TestGUIWall:
    def test_fresh_window_is_clean(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            assert_wall_holds(window)
        finally:
            window.deleteLater()
