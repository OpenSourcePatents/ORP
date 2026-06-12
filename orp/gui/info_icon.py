# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The (i) info icon: hover for the glossary tooltip, click for a popover.

Every icon is bound to one key in :mod:`orp.gui.glossary`; construction fails on an
unknown key, so an icon can never dangle without a definition. The glossary strings
are content, not chrome — they live in one reviewable module and the GUI wall test
walks every icon's tooltip automatically.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QToolButton, QWidget

from orp.gui.glossary import glossary_text

__all__ = ["InfoIcon", "label_with_info"]


class InfoIcon(QToolButton):
    """A small (i) button: tooltip on hover, plain-language popover on click."""

    def __init__(self, glossary_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.glossary_key = glossary_key
        text = glossary_text(glossary_key)  # KeyError on unknown key, by design
        self.setText("i")
        self.setObjectName(f"info_icon_{glossary_key}")
        self.setAutoRaise(True)
        self.setFixedSize(18, 18)
        self.setToolTip(text)
        self.clicked.connect(self._show_popover)

    def _show_popover(self) -> None:
        QMessageBox.information(self, self.glossary_key, glossary_text(self.glossary_key))


def label_with_info(text: str, glossary_key: str, parent: QWidget | None = None) -> QWidget:
    """A label followed by its (i) icon, for use as a form-row label widget."""
    holder = QWidget(parent)
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    label = QLabel(text, holder)
    label.setObjectName(f"label_{glossary_key}")
    layout.addWidget(label)
    layout.addWidget(InfoIcon(glossary_key, holder))
    layout.addStretch(1)
    return holder
