# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ORP main window (PyQt6).

Widgets in this module are a *view* over :class:`~orp.gui.app_state.AppState`: they
read from and write to the state object and call its methods; no widget constructs a
physics object directly. The forward-only wall therefore lives in AppState and the
core — and the GUI surface itself is walked by ``orp/tests/test_gui_wall.py`` (THE GUI
WALL) to keep endpoint-seeking vocabulary out of every label, tooltip, and menu.

Runs execute on a :class:`RunWorker` QThread (simulation plus the gates refresh), so
the UI stays responsive; results land in one atomic refresh on the main thread when
the worker finishes.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QProgressBar, QSplitter, QStatusBar

from orp.gui.app_state import AppState
from orp.gui.conditions_panel import ConditionsPanel
from orp.gui.results_panel import ResultsPanel
from orp.gui.vehicle_panel import VehiclePanel

__all__ = ["MainWindow", "RunWorker"]

#: Default splitter proportions (vehicle | conditions | results), restored by
#: View -> Reset Layout. Nothing is persisted; every launch starts from these.
_DEFAULT_SPLITTER_SIZES = [320, 380, 560]


class RunWorker(QThread):
    """Runs the simulation (and the gates refresh) off the main thread.

    Pure AppState calls — no Qt objects are touched inside :meth:`run`; results are
    delivered back to the main thread via queued signals.
    """

    succeeded = pyqtSignal(object)  # the FlightData
    failed = pyqtSignal(str)

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state

    def run(self) -> None:  # executes on the worker thread
        try:
            result = self._state.run_simulation()
            self._state.refresh_gates()
        except Exception as error:  # surfaced to the user, never swallowed
            self.failed.emit(str(error))
            return
        self.succeeded.emit(result)


class MainWindow(QMainWindow):
    """Top-level window: vehicle | conditions | results, over one AppState."""

    def __init__(self, state: AppState | None = None) -> None:
        super().__init__()
        self.state = state if state is not None else AppState()
        self._worker: RunWorker | None = None
        self.setWindowTitle("ORP - Open Reentry Platform")
        self.setObjectName("orp_main_window")

        self._splitter = QSplitter(self)
        self._splitter.setObjectName("orp_panel_splitter")
        # Drag the dividers to resize; drag fully to collapse a panel in place.
        self._splitter.setChildrenCollapsible(True)
        self.setCentralWidget(self._splitter)

        status = QStatusBar(self)
        status.setObjectName("orp_status_bar")
        self.setStatusBar(status)
        status.showMessage(
            "Forward-only: bank schedules are inputs, trajectories are outputs."
        )
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("run_progress_bar")
        self.progress_bar.setVisible(False)
        status.addPermanentWidget(self.progress_bar)

        self._build_panels()

    def _build_panels(self) -> None:
        self.vehicle_panel = VehiclePanel(self.state, self)
        self._splitter.addWidget(self.vehicle_panel)

        self.conditions_panel = ConditionsPanel(self.state, self)
        self._splitter.addWidget(self.conditions_panel)
        # Loading/reloading a vehicle can change the provenance ceiling.
        self.vehicle_panel.vehicle_loaded.connect(
            lambda _name: self.conditions_panel.rearm()
        )

        self.results_panel = ResultsPanel(self.state, self)
        self._splitter.addWidget(self.results_panel)

        self.conditions_panel.run_requested.connect(self.start_run)

        self._splitter.setSizes(list(_DEFAULT_SPLITTER_SIZES))
        self._build_view_menu()

    def _build_view_menu(self) -> None:
        """View menu: one checkable action per panel, plus Reset Layout.

        Action names are exactly Vehicle / Conditions / Results / Reset Layout (the
        GUI wall test walks QAction text automatically).
        """
        self.view_menu = self.menuBar().addMenu("View")
        self.view_menu.setObjectName("view_menu")
        self.panel_actions: dict[str, QAction] = {}
        for name, panel in (
            ("Vehicle", self.vehicle_panel),
            ("Conditions", self.conditions_panel),
            ("Results", self.results_panel),
        ):
            action = QAction(name, self)
            action.setObjectName(f"view_toggle_{name.lower()}")
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(panel.setVisible)
            self.view_menu.addAction(action)
            self.panel_actions[name] = action

        self.view_menu.addSeparator()
        self.reset_layout_action = QAction("Reset Layout", self)
        self.reset_layout_action.setObjectName("view_reset_layout")
        self.reset_layout_action.triggered.connect(self.reset_layout)
        self.view_menu.addAction(self.reset_layout_action)

    def reset_layout(self) -> None:
        """Restore the default arrangement: all panels shown, default proportions."""
        for action in self.panel_actions.values():
            action.setChecked(True)  # toggled -> setVisible(True)
        self._splitter.setSizes(list(_DEFAULT_SPLITTER_SIZES))

    # ----- run orchestration --------------------------------------------------------

    def start_run(self) -> None:
        """Launch the worker (no-op if one is already running)."""
        if self._worker is not None and self._worker.isRunning():
            return
        self.conditions_panel.set_running(True)
        self.progress_bar.setRange(0, 0)  # indeterminate while the engine integrates
        self.progress_bar.setVisible(True)
        self.statusBar().showMessage("Running forward simulation...")

        self._worker = RunWorker(self.state, self)
        self._worker.succeeded.connect(self._run_succeeded)
        self._worker.failed.connect(self._run_failed)
        self._worker.start()

    def _run_succeeded(self, _result: object) -> None:
        self.progress_bar.setVisible(False)
        self.results_panel.refresh(self.state)  # one atomic pass
        self.conditions_panel.set_running(False)
        self.statusBar().showMessage(
            f"Run complete - weakest-link provenance "
            f"{self.state.flight_data.provenance.level.name}."
        )

    def _run_failed(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        self.conditions_panel.set_running(False)
        self.results_panel.message_label.setText(f"Run refused/failed: {message}")
        self.statusBar().showMessage("Run did not complete.")


def main() -> int:
    """Launch the ORP desktop interface (also reachable as ``orp gui``)."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    window = MainWindow(AppState())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
