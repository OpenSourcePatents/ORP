# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conditions panel: entry state, frame selector, bank-schedule modes, run arming.

Everything here writes plain values into :class:`~orp.gui.app_state.AppState`; the
schedule modes call AppState's schedule setters (which mint the provenance tags), and
the run button only emits a request — the physics is constructed inside AppState.

There is no field for any terminal coordinate anywhere on this panel. The entry
latitude/longitude are where the vehicle STARTS; heading is an initial condition
replayed forward (its label and tooltip say so explicitly, as the wall requires).
"""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orp.core.session import FRAME_INERTIAL, FRAME_PLANET_RELATIVE
from orp.gui.app_state import AppState, EntryStateFields
from orp.gui.info_icon import InfoIcon, label_with_info
from orp.gui.vehicle_panel import level_color

__all__ = ["ConditionsPanel"]


class ConditionsPanel(QWidget):
    """Entry state + frame + schedule; arms the run only when AppState.can_run."""

    run_requested = pyqtSignal()

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("conditions_panel")
        layout = QVBoxLayout(self)

        heading_label = QLabel("Entry conditions", self)
        heading_label.setObjectName("conditions_panel_heading")
        layout.addWidget(heading_label)

        # ----- entry state fields ----------------------------------------------------
        form = QFormLayout()
        self.velocity_edit = self._field("entry_velocity_edit", state.entry.velocity)
        form.addRow(label_with_info("Entry speed (m/s)", "entry speed", self),
                    self.velocity_edit)
        self.fpa_edit = self._field("entry_fpa_edit", state.entry.fpa_deg)
        form.addRow(label_with_info("Flight-path angle (deg)", "flight path angle", self),
                    self.fpa_edit)

        self.heading_edit = self._field("entry_heading_edit", state.entry.heading_deg)
        self.heading_edit.setToolTip(
            "Heading is an initial condition replayed forward from entry interface. "
            "It is an input, not a target: ORP never accepts an endpoint and "
            "produces controls."
        )
        form.addRow(
            label_with_info(
                "Initial heading (input, not target)", "initial heading", self
            ),
            self.heading_edit,
        )

        self.altitude_edit = self._field("entry_altitude_edit", state.entry.altitude)
        form.addRow(label_with_info("Entry altitude (m)", "entry altitude", self),
                    self.altitude_edit)
        self.lat_edit = self._field("entry_lat_edit", state.entry.lat_deg)
        form.addRow(label_with_info("Entry latitude (deg)", "entry latitude", self),
                    self.lat_edit)
        self.lon_edit = self._field("entry_lon_edit", state.entry.lon_deg)
        form.addRow(label_with_info("Entry longitude (deg)", "entry longitude", self),
                    self.lon_edit)

        # ----- planet + frame ----------------------------------------------------------
        self.planet_combo = QComboBox(self)
        self.planet_combo.setObjectName("planet_combo")
        self.planet_combo.addItems(["earth", "mars"])
        form.addRow(label_with_info("Planet", "planet", self), self.planet_combo)

        self.frame_combo = QComboBox(self)
        self.frame_combo.setObjectName("frame_combo")
        self.frame_combo.addItems([FRAME_PLANET_RELATIVE, FRAME_INERTIAL])
        self.frame_combo.setToolTip(
            "Frame the entry state is expressed in. Mandatory; the engine consumes a "
            "planet-relative state."
        )
        frame_holder = QWidget(self)
        frame_row = QHBoxLayout(frame_holder)
        frame_row.setContentsMargins(0, 0, 0, 0)
        frame_row.setSpacing(3)
        frame_row.addWidget(self.frame_combo, stretch=1)
        # One icon per frame meaning, right where the choice is made.
        frame_row.addWidget(InfoIcon("planet-relative", frame_holder))
        frame_row.addWidget(InfoIcon("inertial", frame_holder))
        form.addRow(label_with_info("Entry-state frame", "frame", self), frame_holder)
        layout.addLayout(form)

        self.inertial_warning = QLabel(
            "Inertial entry state: it will be converted to planet-relative at this "
            "boundary via orp.core.frames before the run (convert first, then run; "
            "the saved session records the converted state).",
            self,
        )
        self.inertial_warning.setObjectName("inertial_frame_warning")
        self.inertial_warning.setWordWrap(True)
        self.inertial_warning.setStyleSheet("color: #b26a00;")
        self.inertial_warning.setVisible(False)
        layout.addWidget(self.inertial_warning)

        # ----- schedule sub-panel ------------------------------------------------------
        schedule_heading_row = QHBoxLayout()
        schedule_heading = QLabel("Bank schedule (a pre-recorded control input)", self)
        schedule_heading.setObjectName("schedule_subpanel_heading")
        schedule_heading_row.addWidget(schedule_heading)
        schedule_heading_row.addWidget(InfoIcon("bank angle", self))
        schedule_heading_row.addStretch(1)
        layout.addLayout(schedule_heading_row)

        mode_row = QHBoxLayout()
        self.constant_radio = QRadioButton("Constant angle", self)
        self.constant_radio.setObjectName("schedule_mode_constant")
        self.csv_radio = QRadioButton("CSV import", self)
        self.csv_radio.setObjectName("schedule_mode_csv")
        self.piecewise_radio = QRadioButton("Piecewise editor", self)
        self.piecewise_radio.setObjectName("schedule_mode_piecewise")
        for radio, key in (
            (self.constant_radio, "constant angle"),
            (self.csv_radio, "CSV import"),
            (self.piecewise_radio, "piecewise editor"),
        ):
            mode_row.addWidget(radio)
            mode_row.addWidget(InfoIcon(key, self))
        layout.addLayout(mode_row)

        self.schedule_stack = QStackedWidget(self)
        self.schedule_stack.setObjectName("schedule_mode_stack")
        self.schedule_stack.addWidget(self._build_constant_page())
        self.schedule_stack.addWidget(self._build_csv_page())
        self.schedule_stack.addWidget(self._build_piecewise_page())
        layout.addWidget(self.schedule_stack)

        self.schedule_status = QLabel("No bank schedule chosen yet.", self)
        self.schedule_status.setObjectName("schedule_status_label")
        self.schedule_status.setWordWrap(True)
        layout.addWidget(self.schedule_status)

        # ----- run arming ---------------------------------------------------------------
        ceiling_row = QHBoxLayout()
        self.ceiling_label = QLabel("Provenance ceiling: (load a vehicle and schedule)", self)
        self.ceiling_label.setObjectName("provenance_ceiling_label")
        self.ceiling_label.setToolTip(
            "The best the run's weakest-link provenance can be, given these inputs."
        )
        ceiling_row.addWidget(self.ceiling_label)
        ceiling_row.addWidget(InfoIcon("weakest link", self))
        ceiling_row.addStretch(1)
        layout.addLayout(ceiling_row)

        self.run_button = QPushButton("Run forward simulation", self)
        self.run_button.setObjectName("run_button")
        self.run_button.setEnabled(False)
        self.run_button.setToolTip(
            "Replay the chosen bank schedule forward through the engine. Arms only "
            "when a frame is set and a schedule is chosen."
        )
        layout.addWidget(self.run_button)
        layout.addStretch(1)

        # ----- wiring ---------------------------------------------------------------------
        self.frame_combo.currentTextChanged.connect(self._frame_changed)
        self.planet_combo.currentTextChanged.connect(self._planet_changed)
        self.constant_radio.toggled.connect(self._mode_changed)
        self.csv_radio.toggled.connect(self._mode_changed)
        self.piecewise_radio.toggled.connect(self._mode_changed)
        self.run_button.clicked.connect(self._request_run)
        for edit in (
            self.velocity_edit, self.fpa_edit, self.heading_edit,
            self.altitude_edit, self.lat_edit, self.lon_edit,
        ):
            edit.editingFinished.connect(self.sync_entry_state)

        self._frame_changed(self.frame_combo.currentText())
        self.rearm()

    # ----- builders --------------------------------------------------------------------

    def _field(self, object_name: str, value: float) -> QLineEdit:
        edit = QLineEdit(f"{value:g}", self)
        edit.setObjectName(object_name)
        return edit

    def _build_constant_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("schedule_constant_page")
        row = QHBoxLayout(page)
        self.constant_slider = QSlider(Qt.Orientation.Horizontal, page)
        self.constant_slider.setObjectName("constant_bank_slider")
        self.constant_slider.setRange(-180, 180)
        self.constant_slider.setValue(0)
        self.constant_value_label = QLabel("0 deg", page)
        self.constant_value_label.setObjectName("constant_bank_value_label")
        row.addWidget(self.constant_slider, stretch=1)
        row.addWidget(self.constant_value_label)
        self.constant_slider.valueChanged.connect(self._constant_changed)
        return page

    def _build_csv_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("schedule_csv_page")
        row = QHBoxLayout(page)
        self.csv_button = QPushButton("Import bank-history CSV...", page)
        self.csv_button.setObjectName("schedule_csv_button")
        self.csv_button.setToolTip(
            "Two-column CSV (time_s, bank_deg) loaded via BankSchedule.from_csv - "
            "strict validation, refuses rather than repairs."
        )
        row.addWidget(self.csv_button)
        # Digitized flight datasets carry this tag; its meaning matters when importing.
        row.addWidget(InfoIcon("MACHINE-DIGITIZED", page))
        row.addStretch(1)
        self.csv_button.clicked.connect(self._pick_csv)
        return page

    def _build_piecewise_page(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("schedule_piecewise_page")
        column = QVBoxLayout(page)
        self.piecewise_table = QTableWidget(2, 2, page)
        self.piecewise_table.setObjectName("piecewise_schedule_table")
        self.piecewise_table.setHorizontalHeaderLabels(["Time (s)", "Bank (deg)"])
        self.piecewise_table.verticalHeader().setVisible(False)
        self.piecewise_table.setEditTriggers(
            QAbstractItemView.EditTrigger.AllEditTriggers
        )
        self.piecewise_table.setItem(0, 0, QTableWidgetItem("0"))
        self.piecewise_table.setItem(0, 1, QTableWidgetItem("0"))
        self.piecewise_table.setItem(1, 0, QTableWidgetItem("100"))
        self.piecewise_table.setItem(1, 1, QTableWidgetItem("0"))
        column.addWidget(self.piecewise_table)
        buttons = QHBoxLayout()
        self.piecewise_add_button = QPushButton("Add row", page)
        self.piecewise_add_button.setObjectName("piecewise_add_row_button")
        self.piecewise_apply_button = QPushButton("Apply schedule (tagged ASSERTED)", page)
        self.piecewise_apply_button.setObjectName("piecewise_apply_button")
        buttons.addWidget(self.piecewise_add_button)
        buttons.addWidget(self.piecewise_apply_button)
        column.addLayout(buttons)
        self.piecewise_add_button.clicked.connect(self._piecewise_add_row)
        self.piecewise_apply_button.clicked.connect(self._piecewise_apply)
        return page

    # ----- behavior ----------------------------------------------------------------------

    def sync_entry_state(self) -> None:
        """Write the edited entry fields into AppState (refuse-on-parse stays simple:
        a non-numeric field keeps the previous state value and is restored)."""
        entry = self.state.entry
        for attribute, edit in (
            ("velocity", self.velocity_edit),
            ("fpa_deg", self.fpa_edit),
            ("heading_deg", self.heading_edit),
            ("altitude", self.altitude_edit),
            ("lat_deg", self.lat_edit),
            ("lon_deg", self.lon_edit),
        ):
            try:
                setattr(entry, attribute, float(edit.text()))
            except ValueError:
                edit.setText(f"{getattr(entry, attribute):g}")

    def _frame_changed(self, frame: str) -> None:
        self.state.frame = frame
        self.inertial_warning.setVisible(frame == FRAME_INERTIAL)
        self.rearm()

    def _planet_changed(self, planet: str) -> None:
        self.state.planet_name = planet
        self.rearm()

    def _mode_changed(self, *_args: object) -> None:
        if self.constant_radio.isChecked():
            self.schedule_stack.setCurrentIndex(0)
            self._constant_changed(self.constant_slider.value())
        elif self.csv_radio.isChecked():
            self.schedule_stack.setCurrentIndex(1)
        elif self.piecewise_radio.isChecked():
            self.schedule_stack.setCurrentIndex(2)
        self.rearm()

    def _constant_changed(self, value: int) -> None:
        self.constant_value_label.setText(f"{value} deg")
        if self.constant_radio.isChecked():
            self.state.set_schedule_constant(float(value))
            self.schedule_status.setText(self.state.schedule_summary)
            self.rearm()

    def _pick_csv(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import bank-history CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self.import_csv(path)

    def import_csv(self, path: str) -> None:
        """Import via AppState (the ONLY ingestion path is BankSchedule.from_csv)."""
        try:
            self.state.set_schedule_csv(path)
        except (ValueError, OSError) as error:
            self.schedule_status.setText(f"Refused: {error}")
            self.schedule_status.setStyleSheet("color: #c62828;")
            self.rearm()
            return
        self.schedule_status.setStyleSheet("")
        self.schedule_status.setText(self.state.schedule_summary)
        self.rearm()

    def _piecewise_add_row(self) -> None:
        self.piecewise_table.insertRow(self.piecewise_table.rowCount())

    def _piecewise_apply(self) -> None:
        times: list[float] = []
        angles: list[float] = []
        try:
            for row in range(self.piecewise_table.rowCount()):
                time_item = self.piecewise_table.item(row, 0)
                angle_item = self.piecewise_table.item(row, 1)
                if time_item is None or angle_item is None:
                    continue
                if not time_item.text().strip() and not angle_item.text().strip():
                    continue
                times.append(float(time_item.text()))
                angles.append(float(angle_item.text()))
            self.state.set_schedule_piecewise(times, angles)
        except ValueError as error:
            self.schedule_status.setText(f"Refused: {error}")
            self.schedule_status.setStyleSheet("color: #c62828;")
            self.rearm()
            return
        self.schedule_status.setStyleSheet("")
        self.schedule_status.setText(self.state.schedule_summary)
        self.rearm()

    def rearm(self) -> None:
        """Run arms only when AppState says so; the label states the ceiling."""
        self.run_button.setEnabled(self.state.can_run)
        ceiling = self.state.provenance_ceiling()
        if ceiling is None:
            self.ceiling_label.setText(
                "Provenance ceiling: (load a vehicle and choose a schedule)"
            )
            self.ceiling_label.setStyleSheet("")
        else:
            self.ceiling_label.setText(f"Provenance ceiling: {ceiling.name}")
            self.ceiling_label.setStyleSheet(
                f"color: {level_color(ceiling.name).name()}; font-weight: bold;"
            )

    def _request_run(self) -> None:
        self.sync_entry_state()
        self.run_requested.emit()

    def reset_to_defaults(self) -> None:
        """New Run: every input back to the engine defaults, no schedule chosen."""
        self.state.entry = EntryStateFields()
        for attribute, edit in (
            ("velocity", self.velocity_edit),
            ("fpa_deg", self.fpa_edit),
            ("heading_deg", self.heading_edit),
            ("altitude", self.altitude_edit),
            ("lat_deg", self.lat_edit),
            ("lon_deg", self.lon_edit),
        ):
            edit.setText(f"{getattr(self.state.entry, attribute):g}")
        self.frame_combo.setCurrentText(FRAME_PLANET_RELATIVE)
        self.planet_combo.setCurrentText("earth")
        for radio in (self.constant_radio, self.csv_radio, self.piecewise_radio):
            radio.setAutoExclusive(False)
            radio.setChecked(False)
            radio.setAutoExclusive(True)
        self.constant_slider.setValue(0)
        self.state.schedule = None
        self.state.schedule_source = None
        self.state.schedule_summary = ""
        self.schedule_status.setStyleSheet("")
        self.schedule_status.setText("No bank schedule chosen yet.")
        self.rearm()

    def set_running(self, running: bool) -> None:
        """Disable the run button while a worker is active (re-armed on finish)."""
        if running:
            self.run_button.setEnabled(False)
        else:
            self.rearm()
