# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vehicle panel: library dropdown, vertically scrolling provenance cards, reload.

Display-only: the cards never edit a vehicle; the panel's only writes to AppState are
``load_vehicle`` calls. One card per property — name (bold), value with units, the
provenance tag color-coded by ValidationLevel (VERIFIED_FLIGHT green, VERIFIED_SOURCE
blue, VERIFIED_CFD cyan, ASSERTED amber, NOT_VALIDATED red), and the source citation —
stacked vertically at full panel width, word-wrapped, scrolling vertically only (no
horizontal scrollbar exists anywhere in the panel).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from orp.gui.app_state import LEVEL_COLOR_HEX, AppState
from orp.gui.info_icon import InfoIcon, label_with_info

__all__ = ["VehiclePanel", "level_color"]


def level_color(level_name: str) -> QColor:
    """The display color for a ValidationLevel name (shared by all panels)."""
    return QColor(LEVEL_COLOR_HEX.get(level_name, "#616161"))


class VehiclePanel(QWidget):
    """Read-only card view of one library vehicle with per-property provenance."""

    vehicle_loaded = pyqtSignal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("vehicle_panel")

        layout = QVBoxLayout(self)
        layout.addWidget(label_with_info("Vehicle library", "vehicle", self))

        # Color legend: one chip + (i) per ValidationLevel, worst first — the same
        # five-color code every panel uses.
        legend_row = QHBoxLayout()
        for level_name in (
            "NOT_VALIDATED",
            "ASSERTED",
            "VERIFIED_SOURCE",
            "VERIFIED_CFD",
            "VERIFIED_FLIGHT",
        ):
            chip = QLabel(level_name, self)
            chip.setObjectName(f"legend_chip_{level_name}")
            chip.setStyleSheet(
                f"background-color: {level_color(level_name).name()}; color: white; "
                "padding: 0px 3px; font-size: 7pt;"
            )
            legend_row.addWidget(chip)
            legend_row.addWidget(InfoIcon(level_name, self))
        legend_row.addStretch(1)
        layout.addLayout(legend_row)

        chooser_row = QHBoxLayout()
        self.combo = QComboBox(self)
        self.combo.setObjectName("vehicle_combo")
        self.combo.setToolTip("Vehicles from the YAML library (orp/data/vehicles).")
        chooser_row.addWidget(self.combo, stretch=1)

        self.reload_button = QPushButton("Reload from disk", self)
        self.reload_button.setObjectName("vehicle_reload_button")
        self.reload_button.setToolTip(
            "Re-read the selected vehicle's YAML from disk (display refreshes)."
        )
        chooser_row.addWidget(self.reload_button)
        layout.addLayout(chooser_row)

        self.summary_label = QLabel("", self)
        self.summary_label.setObjectName("vehicle_summary_label")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # Vertically scrolling card list: full width, word-wrapped, no horizontal
        # scrollbar possible (policy AlwaysOff + resizable widget tracking width).
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("vehicle_card_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self._card_host = QWidget(self.scroll_area)
        self._card_host.setObjectName("vehicle_card_host")
        self._card_layout = QVBoxLayout(self._card_host)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.addStretch(1)
        self.scroll_area.setWidget(self._card_host)
        layout.addWidget(self.scroll_area, stretch=1)

        #: Per-property card labels, keyed by property name then field name
        #: ("name", "value", "level", "source") — populated on load, read by tests.
        self.cards: dict[str, dict[str, QLabel]] = {}

        self.combo.addItems(self.state.available_vehicles())
        self.combo.currentTextChanged.connect(self._load_current)
        self.reload_button.clicked.connect(self._load_current)
        if self.combo.count() > 0:
            self._load_current()

    # ----- behavior -----------------------------------------------------------------

    def _clear_cards(self) -> None:
        while self._card_layout.count() > 1:  # keep the trailing stretch
            item = self._card_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards = {}

    def _make_card(self, prop: str, tv) -> QWidget:
        card = QFrame(self._card_host)
        card.setObjectName(f"vehicle_card_{prop}")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)

        name_label = QLabel(prop, card)
        name_label.setObjectName(f"vehicle_card_{prop}_name")
        name_label.setWordWrap(True)
        font = name_label.font()
        font.setBold(True)
        name_label.setFont(font)
        card_layout.addWidget(name_label)

        value_text = f"{tv.value:g}" + (f" {tv.unit}" if tv.unit else "")
        value_label = QLabel(value_text, card)
        value_label.setObjectName(f"vehicle_card_{prop}_value")
        value_label.setWordWrap(True)
        card_layout.addWidget(value_label)

        level_name = tv.provenance.level.name
        level_label = QLabel(level_name, card)
        level_label.setObjectName(f"vehicle_card_{prop}_level")
        level_label.setWordWrap(True)
        level_label.setStyleSheet(
            f"background-color: {level_color(level_name).name()}; color: white; "
            "padding: 1px 4px; font-weight: bold;"
        )
        # Keep the colored chip snug instead of full-row.
        level_label.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        card_layout.addWidget(level_label)

        source_label = QLabel(tv.provenance.source, card)
        source_label.setObjectName(f"vehicle_card_{prop}_source")
        source_label.setWordWrap(True)
        card_layout.addWidget(source_label)

        self.cards[prop] = {
            "name": name_label,
            "value": value_label,
            "level": level_label,
            "source": source_label,
        }
        return card

    def _load_current(self, *_args: object) -> None:
        name = self.combo.currentText()
        if not name:
            return
        vehicle = self.state.load_vehicle(name)
        tagged = vehicle.tagged_values()
        self.summary_label.setText(
            f"{vehicle.name} - {len(tagged)} properties; "
            f"weakest link: {vehicle.provenance.level.name}"
        )

        self._clear_cards()
        # Worst tag first, then by property name (same order as the CLI listing).
        for prop, tv in sorted(
            tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0])
        ):
            self._card_layout.insertWidget(self._card_layout.count() - 1,
                                           self._make_card(prop, tv))
        self.vehicle_loaded.emit(name)
