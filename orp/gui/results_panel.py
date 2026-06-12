# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Results panel: the eight plots, provenance report, landing summary, gates.

Every plot tab carries a colored provenance banner (the run's weakest-link level and
its limiting source); the provenance table colors every component row by its
ValidationLevel; the gates rows show each gate's status text exactly as the gate
states it — never reworded — colored by outcome. All content is read from AppState in
one atomic ``refresh`` pass on the main thread after the worker finishes.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from orp.gui.app_state import AppState
from orp.gui.info_icon import InfoIcon
from orp.gui.vehicle_panel import level_color

__all__ = ["ResultsPanel"]

#: The landing-summary rows: (display label, glossary key), in AppState's order.
_SUMMARY_ROWS: tuple[tuple[str, str], ...] = (
    ("Peak deceleration", "peak deceleration"),
    ("Peak heat rate", "peak heat rate"),
    ("Peak dynamic pressure", "peak dynamic pressure"),
    ("Impact velocity", "impact velocity"),
)

#: The eight standard plots: (tab title, plots-module function name).
PLOT_TABS: tuple[tuple[str, str], ...] = (
    ("Altitude", "plot_altitude_time"),
    ("Velocity", "plot_velocity_time"),
    ("G-load", "plot_g_load_time"),
    ("Heat rate", "plot_heat_rate_time"),
    ("Ground track", "plot_ground_track"),
    ("CD/CL vs Mach", "plot_coefficients_mach"),
    ("Dyn. pressure", "plot_dynamic_pressure_altitude"),
    ("Specific force", "plot_specific_force_time"),
)


class ResultsPanel(QWidget):
    """All run outputs; populated atomically by :meth:`refresh`."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setObjectName("results_panel")
        layout = QVBoxLayout(self)

        heading = QLabel("Results", self)
        heading.setObjectName("results_panel_heading")
        layout.addWidget(heading)

        self.message_label = QLabel("No run yet.", self)
        self.message_label.setObjectName("results_message_label")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("results_tabs")
        layout.addWidget(self.tabs, stretch=1)

        # Plot tabs (canvas attaches on refresh; banner is per-tab).
        self._plot_pages: dict[str, QWidget] = {}
        for title, function_name in PLOT_TABS:
            page = QWidget(self)
            page.setObjectName(f"plot_page_{function_name}")
            page_layout = QVBoxLayout(page)
            banner = QLabel("(run pending)", page)
            banner.setObjectName(f"provenance_banner_{function_name}")
            banner.setAutoFillBackground(True)
            banner.setWordWrap(True)
            page_layout.addWidget(banner)
            self._plot_pages[function_name] = page
            self.tabs.addTab(page, title)

        # Provenance report tab: per-component colored rows.
        provenance_page = QWidget(self)
        provenance_page.setObjectName("provenance_report_page")
        provenance_layout = QVBoxLayout(provenance_page)
        self.provenance_table = QTableWidget(0, 3, provenance_page)
        self.provenance_table.setObjectName("provenance_report_table")
        self.provenance_table.setHorizontalHeaderLabels(["Component", "Level", "Source"])
        self.provenance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.provenance_table.verticalHeader().setVisible(False)
        provenance_layout.addWidget(self.provenance_table)
        self.tabs.addTab(provenance_page, "Provenance")

        # Gates tab (updated after every run; text never reworded).
        gates_page = QWidget(self)
        gates_page.setObjectName("gates_page")
        self._gates_layout = QVBoxLayout(gates_page)
        self._gates_layout.addStretch(1)
        self.tabs.addTab(gates_page, "Gates")

        # Landing summary + export row. Rows are static (label, value, info icon);
        # refresh fills the value column.
        self.summary_table = QTableWidget(len(_SUMMARY_ROWS), 3, self)
        self.summary_table.setObjectName("landing_summary_table")
        self.summary_table.setHorizontalHeaderLabels(["Quantity", "Value", ""])
        self.summary_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setMaximumHeight(150)
        for index, (label, key) in enumerate(_SUMMARY_ROWS):
            self.summary_table.setItem(index, 0, QTableWidgetItem(label))
            self.summary_table.setItem(index, 1, QTableWidgetItem("-"))
            self.summary_table.setCellWidget(index, 2, InfoIcon(key, self))
        self.summary_table.resizeColumnsToContents()
        layout.addWidget(self.summary_table)

        buttons = QHBoxLayout()
        self.save_session_button = QPushButton("Save session...", self)
        self.save_session_button.setObjectName("save_session_button")
        self.save_session_button.setEnabled(False)
        self.export_csv_button = QPushButton("Export trajectory CSV...", self)
        self.export_csv_button.setObjectName("export_csv_button")
        self.export_csv_button.setEnabled(False)
        buttons.addWidget(self.save_session_button)
        buttons.addWidget(self.export_csv_button)
        layout.addLayout(buttons)

        self.save_session_button.clicked.connect(self._save_session)
        self.export_csv_button.clicked.connect(self._export_csv)

    # ----- refresh (atomic, main thread) ----------------------------------------------

    def refresh(self, state: AppState | None = None) -> None:
        """Rebuild every tab from AppState in one pass (called after the worker ends)."""
        state = state if state is not None else self.state
        if state.flight_data is None:
            self.message_label.setText("No run yet.")
            return

        branch = state.flight_data.get_branch(0)
        end_event = branch.events[-1].name if branch.events else "(no events)"
        message = f"Run complete: {branch.length} samples, terminated by {end_event}."
        if state.frame_conversion_note:
            message += f"\n{state.frame_conversion_note}"
        self.message_label.setText(message)

        self._refresh_plots(state)
        self._refresh_provenance(state)
        self._refresh_summary(state)
        self.refresh_gates(state)

        self.save_session_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _banner_text_and_color(self, state: AppState) -> tuple[str, QColor]:
        provenance = state.flight_data.provenance  # type: ignore[union-attr]
        text = f"Provenance: {provenance.level.name}"
        if provenance.source:
            text += f" - {provenance.source}"
        return text, level_color(provenance.level.name)

    def _refresh_plots(self, state: AppState) -> None:
        # Lazy import: matplotlib only when results actually render.
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

        from orp.gui import plots

        banner_text, banner_color = self._banner_text_and_color(state)
        for function_name, page in self._plot_pages.items():
            page_layout = page.layout()
            # Drop the previous canvas (banner stays at index 0).
            while page_layout.count() > 1:
                item = page_layout.takeAt(1)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            banner = page_layout.itemAt(0).widget()
            banner.setText(banner_text)
            banner.setStyleSheet(
                f"background-color: {banner_color.name()}; color: white; "
                "padding: 3px; font-weight: bold;"
            )
            # The colored banner above is the single in-GUI provenance display;
            # the figure-level stamp stays on every figure written to disk.
            figure = getattr(plots, function_name)(
                state.flight_data, stamp_provenance=False
            )
            canvas = FigureCanvasQTAgg(figure)
            page_layout.addWidget(canvas, stretch=1)

    def _refresh_provenance(self, state: AppState) -> None:
        rows = state.provenance_rows()
        self.provenance_table.setRowCount(len(rows))
        for index, (component, tag) in enumerate(rows):
            component_item = QTableWidgetItem(component)
            level_item = QTableWidgetItem(tag.level.name)
            level_item.setBackground(level_color(tag.level.name))
            level_item.setForeground(QColor("white"))
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            source_item = QTableWidgetItem(tag.source)
            for column, item in enumerate((component_item, level_item, source_item)):
                self.provenance_table.setItem(index, column, item)
        self.provenance_table.resizeColumnsToContents()

    def _refresh_summary(self, state: AppState) -> None:
        rows = state.landing_summary()
        assert [label for label, _ in rows] == [label for label, _ in _SUMMARY_ROWS]
        for index, (_label, value) in enumerate(rows):
            self.summary_table.item(index, 1).setText(value)
        self.summary_table.resizeColumnsToContents()

    def refresh_gates(self, state: AppState | None = None) -> None:
        """Gate status rows, text exactly as the gates state it, colored by outcome."""
        state = state if state is not None else self.state
        # Clear previous rows (keep the trailing stretch).
        while self._gates_layout.count() > 1:
            item = self._gates_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        report = state.gates_report
        if report is None:
            placeholder = QLabel("Gates run after every simulation run.", self)
            placeholder.setObjectName("gates_placeholder_label")
            self._gates_layout.insertWidget(0, placeholder)
            return
        for index, row in enumerate(report.rows):
            label = QLabel(row.line, self)  # verbatim — never reworded
            label.setObjectName(f"gate_status_row_{index}")
            label.setWordWrap(True)
            if not row.as_expected:
                color = "#c62828"  # unexpected deviation: red
            elif "NOT_VALIDATED" in row.line or "FAIL" in row.line:
                color = "#ff8f00"  # honest scaffold/FAIL, as pinned: amber
            else:
                color = "#2e7d32"  # validated: green
            label.setStyleSheet(
                f"background-color: {color}; color: white; padding: 3px;"
            )
            self._gates_layout.insertWidget(index, label)
        summary = QLabel(report.summary_line, self)
        summary.setObjectName("gates_summary_label")
        summary.setWordWrap(True)
        self._gates_layout.insertWidget(len(report.rows), summary)

    # ----- exports ----------------------------------------------------------------------

    def _save_session(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save session", "session.yaml", "YAML files (*.yaml);;All files (*)"
        )
        if path:
            self.state.save_session_to(path)
            self.message_label.setText(f"Session saved to {path}")

    def _export_csv(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export trajectory CSV", "trajectory.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if path:
            self.state.export_csv_to(path)
            self.message_label.setText(f"Trajectory exported to {path}")
