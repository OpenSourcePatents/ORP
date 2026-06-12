# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ORP main window (PyQt6).

Widgets in this module are a *view* over :class:`~orp.gui.app_state.AppState`: they
read from and write to the state object and call its methods; no widget constructs a
physics object directly. The forward-only wall therefore lives in AppState and the
core — and the GUI surface itself is walked by ``orp/tests/test_gui_wall.py`` (THE GUI
WALL) to keep endpoint-seeking vocabulary out of every label, tooltip, and menu.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from orp.gui.app_state import AppState

__all__ = ["MainWindow"]


class MainWindow(QMainWindow):
    """Top-level window: vehicle | conditions | results, over one AppState."""

    def __init__(self, state: AppState | None = None) -> None:
        super().__init__()
        self.state = state if state is not None else AppState()
        self.setWindowTitle("ORP - Open Reentry Platform")
        self.setObjectName("orp_main_window")

        self._splitter = QSplitter(self)
        self._splitter.setObjectName("orp_panel_splitter")
        self.setCentralWidget(self._splitter)

        status = QStatusBar(self)
        status.setObjectName("orp_status_bar")
        self.setStatusBar(status)
        status.showMessage(
            "Forward-only: bank schedules are inputs, trajectories are outputs."
        )

        self._build_panels()

    def _build_panels(self) -> None:
        """Panels are attached here as they land (vehicle, conditions, results)."""
        placeholder = QWidget(self)
        placeholder.setObjectName("orp_panel_placeholder")
        layout = QVBoxLayout(placeholder)
        note = QLabel(
            "Panels load here: vehicle library, entry conditions and bank schedule, "
            "results.",
            placeholder,
        )
        note.setObjectName("orp_placeholder_note")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._splitter.addWidget(placeholder)
