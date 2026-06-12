# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vehicle panel: library dropdown, provenance-colored property table, reload.

Display-only: the table never edits a vehicle; the panel's only writes to AppState are
``load_vehicle`` calls. Per-field provenance is color-coded by ValidationLevel
(VERIFIED_FLIGHT green, VERIFIED_SOURCE blue, VERIFIED_CFD cyan, ASSERTED amber,
NOT_VALIDATED red) so the weakest links are visible at a glance.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orp.gui.app_state import LEVEL_COLOR_HEX, AppState

__all__ = ["VehiclePanel", "level_color"]


def level_color(level_name: str) -> QColor:
    """The display color for a ValidationLevel name (shared by all panels)."""
    return QColor(LEVEL_COLOR_HEX.get(level_name, "#616161"))


class VehiclePanel(QWidget):
    """Read-only view of one library vehicle with per-property provenance."""

    vehicle_loaded = pyqtSignal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("vehicle_panel")

        layout = QVBoxLayout(self)
        heading = QLabel("Vehicle library", self)
        heading.setObjectName("vehicle_panel_heading")
        layout.addWidget(heading)

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

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("vehicle_property_table")
        self.table.setHorizontalHeaderLabels(["Property", "Value", "Provenance", "Source"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, stretch=1)

        self.combo.addItems(self.state.available_vehicles())
        self.combo.currentTextChanged.connect(self._load_current)
        self.reload_button.clicked.connect(self._load_current)
        if self.combo.count() > 0:
            self._load_current()

    # ----- behavior -----------------------------------------------------------------

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

        # Worst tag first, then by property name (same order as the CLI listing).
        rows = sorted(tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0]))
        self.table.setRowCount(len(rows))
        for row_index, (prop, tv) in enumerate(rows):
            value_text = f"{tv.value:g}" + (f" {tv.unit}" if tv.unit else "")
            level_name = tv.provenance.level.name

            name_item = QTableWidgetItem(prop)
            value_item = QTableWidgetItem(value_text)
            level_item = QTableWidgetItem(level_name)
            level_item.setBackground(level_color(level_name))
            level_item.setForeground(QColor("white"))
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            source_item = QTableWidgetItem(tv.provenance.source)

            for column, item in enumerate((name_item, value_item, level_item, source_item)):
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.vehicle_loaded.emit(name)
