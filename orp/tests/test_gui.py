# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI tests (headless, QT_QPA_PLATFORM=offscreen).

Coverage:
  - End-to-end through AppState: all eight plot tabs populated with real figures and
    every tab's provenance banner matching the level the engine stamped on the run.
  - The run button is disabled on a fresh launch (no schedule chosen yet).
  - The inertial-frame warning appears on selection and cites orp.core.frames.
  - The CSV importer's only ingestion path is BankSchedule.from_csv.
  - The threaded run keeps the main thread responsive (timer ticks observed while the
    worker runs) and results land after the worker finishes.
  - THE GUI WALL holds on the fully populated window (post-run walk).
  - CLI and GUI runs with identical inputs produce identical FlightData (byte-equal
    trajectory CSVs through the shared writer).
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

# Headless before any Qt / matplotlib import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest

pytest.importorskip("PyQt6", reason="GUI tests require PyQt6")
pytest.importorskip("matplotlib", reason="GUI results tests require matplotlib")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from orp.core.bank_schedule import BankSchedule
from orp.gui.app_state import LEVEL_COLOR_HEX, AppState
from orp.gui.main_window import MainWindow
from orp.tests.test_gui_wall import assert_wall_holds


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _flush_deferred_deletes(qapp: QApplication):
    """Process deleteLater() backlogs after every test.

    Plot refreshes replace FigureCanvasQTAgg widgets via deleteLater; without an
    event loop those deferred deletions pile up and Qt tears them down in an
    arbitrary order at interpreter exit, which crashes the process on Windows
    (0xC0000409). Flushing per-test keeps destruction deterministic.
    """
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent

    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, int(QEvent.Type.DeferredDelete))
    qapp.processEvents()


def _fast_state() -> AppState:
    """Apollo / Earth / constant 60 deg, short and coarse so tests stay quick."""
    state = AppState()
    state.load_vehicle("apollo")
    state.set_schedule_constant(60.0)
    state.time_step = 1.0
    state.max_simulation_time = 120.0
    return state


# ---------------------------------------------------------------------------
# End-to-end through AppState
# ---------------------------------------------------------------------------

class TestEndToEndThroughAppState:
    def test_eight_figures_populated_and_banners_match_engine(
        self, qapp: QApplication
    ) -> None:
        state = _fast_state()
        window = MainWindow(state)
        try:
            state.run_simulation()  # the AppState path the worker uses
            window.results_panel.refresh(state)

            engine_level = state.flight_data.provenance.level.name
            pages = window.results_panel._plot_pages
            assert len(pages) == 8
            for function_name, page in pages.items():
                layout = page.layout()
                # banner + canvas
                assert layout.count() == 2, f"{function_name}: no canvas attached"
                banner = layout.itemAt(0).widget()
                assert banner.text().startswith(f"Provenance: {engine_level}"), (
                    f"{function_name}: banner {banner.text()!r} does not match the "
                    f"engine-stamped level {engine_level}"
                )
                assert LEVEL_COLOR_HEX[engine_level] in banner.styleSheet()
                canvas = layout.itemAt(1).widget()
                figure = canvas.figure
                assert figure.axes, f"{function_name}: figure has no axes"
                axes = figure.axes[0]
                assert axes.lines, f"{function_name}: figure has no plotted data"

            # Landing summary populated with units.
            summary = window.results_panel.summary_table
            assert summary.rowCount() == 4
            labels = [summary.item(r, 0).text() for r in range(4)]
            assert labels == [
                "Peak deceleration",
                "Peak heat rate",
                "Peak dynamic pressure",
                "Impact velocity",
            ]
            values = [summary.item(r, 1).text() for r in range(4)]
            for value, unit in zip(values, ("g", "W/m^2", "Pa", "m/s")):
                assert value.endswith(unit)

            # Provenance table has the per-component rows, colored by level.
            table = window.results_panel.provenance_table
            assert table.rowCount() >= 9  # run + vehicle overall + 7 props + models...
            components = [table.item(r, 0).text() for r in range(table.rowCount())]
            assert "equations of motion" in components
            assert "bank schedule" in components
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# Arming and frame warning
# ---------------------------------------------------------------------------

class TestArmingAndFrame:
    def test_run_button_disabled_on_fresh_launch(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            # A vehicle auto-loads, but no schedule is chosen yet: must not arm.
            assert window.state.schedule is None
            assert not window.conditions_panel.run_button.isEnabled()
        finally:
            window.deleteLater()

    def test_inertial_warning_appears_on_selection(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        window.show()
        try:
            warning = window.conditions_panel.inertial_warning
            assert not warning.isVisible()
            window.conditions_panel.frame_combo.setCurrentText("inertial")
            assert warning.isVisible()
            assert "orp.core.frames" in warning.text()
            assert window.state.frame == "inertial"
            window.conditions_panel.frame_combo.setCurrentText("planet-relative")
            assert not warning.isVisible()
        finally:
            window.close()
            window.deleteLater()

    def test_arming_requires_schedule_then_arms(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            panel = window.conditions_panel
            assert not panel.run_button.isEnabled()
            panel.constant_radio.setChecked(True)  # picks constant mode, sets schedule
            assert window.state.schedule is not None
            assert panel.run_button.isEnabled()
            assert "Provenance ceiling: NOT_VALIDATED" in panel.ceiling_label.text()
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# CSV importer
# ---------------------------------------------------------------------------

class TestCsvImporter:
    def test_importer_calls_from_csv_only(
        self, qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        csv_path = tmp_path / "bank.csv"
        csv_path.write_text(
            "time_s,bank_deg\n0,60\n100,-60\n200,60\n", encoding="utf-8"
        )

        calls: list[str] = []
        real_from_csv = BankSchedule.from_csv.__func__

        def _spy(cls, path, *, provenance):
            calls.append(str(path))
            return real_from_csv(cls, path, provenance=provenance)

        monkeypatch.setattr(BankSchedule, "from_csv", classmethod(_spy))

        window = MainWindow(AppState())
        try:
            window.conditions_panel.csv_radio.setChecked(True)
            window.conditions_panel.import_csv(str(csv_path))
            # from_csv was the (one and only) ingestion path.
            assert calls == [str(csv_path)]
            assert window.state.schedule is not None
            assert len(window.state.schedule) == 3
            # Status shows the tag and the reversal count.
            status = window.conditions_panel.schedule_status.text()
            assert "ASSERTED" in status
            assert "2 sign reversal(s)" in status
        finally:
            window.deleteLater()

    def test_importer_shows_refusal_verbatim(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text("time_s,bank_deg\n0,nan\n", encoding="utf-8")
        window = MainWindow(AppState())
        try:
            window.conditions_panel.csv_radio.setChecked(True)
            window.conditions_panel.import_csv(str(bad))
            assert window.state.schedule is None
            assert window.conditions_panel.schedule_status.text().startswith("Refused:")
            assert not window.conditions_panel.run_button.isEnabled()
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# Threaded run
# ---------------------------------------------------------------------------

class TestThreadedRun:
    def test_main_thread_not_blocked_and_results_land(self, qapp: QApplication) -> None:
        state = _fast_state()
        window = MainWindow(state)
        try:
            ticks: list[float] = []
            timer = QTimer(window)
            timer.setInterval(5)
            timer.timeout.connect(lambda: ticks.append(time.monotonic()))
            timer.start()

            window.start_run()
            assert window._worker is not None
            deadline = time.monotonic() + 60.0
            while window._worker.isRunning() and time.monotonic() < deadline:
                qapp.processEvents()
            # Flush the queued succeeded-signal delivery and the atomic refresh.
            for _ in range(50):
                qapp.processEvents()
            timer.stop()

            assert not window._worker.isRunning(), "worker did not finish in time"
            # The main thread processed timer events WHILE the worker ran: not blocked.
            assert len(ticks) >= 5, "main thread looks blocked during the run"
            assert state.flight_data is not None
            assert state.gates_report is not None  # gates update after every run
            assert window.results_panel.message_label.text().startswith("Run complete")
            # Run button re-armed after completion.
            assert window.conditions_panel.run_button.isEnabled()
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# Vehicle panel: vertical card list, no horizontal scrolling
# ---------------------------------------------------------------------------

class TestVehicleCards:
    def test_no_horizontal_scrollbar_possible(self, qapp: QApplication) -> None:
        from PyQt6.QtCore import Qt

        window = MainWindow(AppState())
        window.show()
        try:
            panel = window.vehicle_panel
            assert (
                panel.scroll_area.horizontalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            assert not panel.scroll_area.horizontalScrollBar().isVisible()
            assert panel.scroll_area.widgetResizable()  # cards track panel width
        finally:
            window.close()
            window.deleteLater()

    def test_every_property_has_all_four_fields(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            panel = window.vehicle_panel
            vehicle = window.state.vehicle
            assert vehicle is not None
            tagged = vehicle.tagged_values()
            assert set(panel.cards) == set(tagged)
            for prop, tv in tagged.items():
                card = panel.cards[prop]
                assert card["name"].text() == prop
                assert card["name"].font().bold()
                assert card["value"].text().startswith(f"{tv.value:g}")
                if tv.unit:
                    assert tv.unit in card["value"].text()
                level_name = tv.provenance.level.name
                assert card["level"].text() == level_name
                # The existing five-color code, rendered on the tag chip.
                assert LEVEL_COLOR_HEX[level_name] in card["level"].styleSheet()
                assert card["source"].text() == tv.provenance.source
                for field in ("name", "value", "source"):
                    assert card[field].wordWrap()
        finally:
            window.deleteLater()

    def test_reload_rebuilds_cards(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            panel = window.vehicle_panel
            before = set(panel.cards)
            panel.reload_button.click()
            assert set(panel.cards) == before  # rebuilt, same property set
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# Panel layout: resizable splitter, View-menu visibility toggles, Reset Layout
# ---------------------------------------------------------------------------

class TestPanelLayout:
    def test_view_actions_hide_and_reshow_each_panel(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        window.show()
        try:
            panels = {
                "Vehicle": window.vehicle_panel,
                "Conditions": window.conditions_panel,
                "Results": window.results_panel,
            }
            assert set(window.panel_actions) == set(panels)
            for name, panel in panels.items():
                action = window.panel_actions[name]
                assert action.text() == name  # exact names; walked by the GUI wall
                assert action.isCheckable() and action.isChecked()
                assert panel.isVisible()
                action.setChecked(False)
                assert not panel.isVisible(), f"{name} did not hide"
                action.setChecked(True)
                assert panel.isVisible(), f"{name} did not come back"
        finally:
            window.close()
            window.deleteLater()

    def test_splitter_handles_exist_for_resizing(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        window.show()
        try:
            splitter = window._splitter
            assert splitter.count() == 3
            assert splitter.childrenCollapsible()
            # Handles 1 and 2 are the draggable dividers between the three panels.
            assert splitter.handle(1) is not None
            assert splitter.handle(2) is not None
            assert all(size > 0 for size in splitter.sizes())
        finally:
            window.close()
            window.deleteLater()

    def test_reset_layout_restores_default_arrangement(
        self, qapp: QApplication
    ) -> None:
        window = MainWindow(AppState())
        window.show()
        try:
            assert window.reset_layout_action.text() == "Reset Layout"
            window.panel_actions["Vehicle"].setChecked(False)
            window.panel_actions["Results"].setChecked(False)
            window._splitter.setSizes([50, 900, 50])
            window.reset_layout_action.trigger()
            for name, action in window.panel_actions.items():
                assert action.isChecked(), f"{name} not re-checked by Reset Layout"
            assert window.vehicle_panel.isVisible()
            assert window.conditions_panel.isVisible()
            assert window.results_panel.isVisible()
            assert all(size > 0 for size in window._splitter.sizes())
        finally:
            window.close()
            window.deleteLater()


# ---------------------------------------------------------------------------
# File and Runs menus
# ---------------------------------------------------------------------------

class TestFileMenu:
    def test_actions_exist_and_gate_on_a_completed_run(
        self, qapp: QApplication
    ) -> None:
        window = MainWindow(AppState())
        try:
            assert window.save_session_action.text() == "Save Session"
            assert window.export_csv_action.text() == "Export Trajectory CSV"
            assert window.exit_action.text() == "Exit"
            assert not window.save_session_action.isEnabled()
            assert not window.export_csv_action.isEnabled()
            # The panel buttons remain alongside the menu entries.
            assert window.results_panel.save_session_button is not None
            assert window.results_panel.export_csv_button is not None
        finally:
            window.deleteLater()

    def test_menu_actions_wire_to_the_panel_code_paths(
        self, qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PyQt6.QtWidgets import QFileDialog

        state = _fast_state()
        window = MainWindow(state)
        try:
            state.run_simulation()
            window.results_panel.refresh(state)
            window.save_session_action.setEnabled(True)
            window.export_csv_action.setEnabled(True)

            session_path = tmp_path / "menu_session.yaml"
            monkeypatch.setattr(
                QFileDialog, "getSaveFileName",
                staticmethod(lambda *a, **k: (str(session_path), "")),
            )
            window.save_session_action.trigger()
            assert session_path.is_file()
            assert "Session saved to" in window.results_panel.message_label.text()

            csv_path = tmp_path / "menu_trajectory.csv"
            monkeypatch.setattr(
                QFileDialog, "getSaveFileName",
                staticmethod(lambda *a, **k: (str(csv_path), "")),
            )
            window.export_csv_action.trigger()
            assert csv_path.is_file()
            assert "Trajectory exported to" in window.results_panel.message_label.text()

            # The panel button drives the identical slot and overwrites identically.
            button_csv = csv_path.read_bytes()
            window.results_panel.export_csv_button.click()
            assert csv_path.read_bytes() == button_csv
        finally:
            window.deleteLater()


class TestRunsMenu:
    def test_new_run_resets_conditions_to_defaults(self, qapp: QApplication) -> None:
        window = MainWindow(AppState())
        try:
            panel = window.conditions_panel
            panel.constant_radio.setChecked(True)
            panel.constant_slider.setValue(45)
            panel.velocity_edit.setText("9999")
            panel.sync_entry_state()
            panel.frame_combo.setCurrentText("inertial")
            assert window.state.can_run

            assert window.new_run_action.text() == "New Run"
            window.new_run_action.trigger()
            assert window.state.schedule is None
            assert not window.state.can_run
            assert not panel.run_button.isEnabled()
            assert window.state.frame == "planet-relative"
            assert float(panel.velocity_edit.text()) == window.state.entry.velocity
            assert window.state.entry.velocity != 9999.0
        finally:
            window.deleteLater()

    def test_history_restores_a_previous_runs_flight_data_identity(
        self, qapp: QApplication
    ) -> None:
        state = _fast_state()
        window = MainWindow(state)
        try:
            first = state.run_simulation()
            state.set_schedule_constant(15.0)  # different schedule, different run
            second = state.run_simulation()
            assert first is not second
            assert len(state.run_history) == 2

            window.rebuild_run_history()
            actions = window.run_history_actions
            assert len(actions) == 2
            assert actions[-1].isChecked()  # latest run selected

            actions[0].trigger()
            assert state.flight_data is first  # FlightData identity restored
            assert window.results_panel.message_label.text().startswith("Run complete")
            actions[1].trigger()
            assert state.flight_data is second
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# Dark mode
# ---------------------------------------------------------------------------

class TestDarkMode:
    def test_dark_flips_palette_and_figures_and_light_restores(
        self, qapp: QApplication
    ) -> None:
        from PyQt6.QtGui import QPalette

        state = _fast_state()
        window = MainWindow(state)
        try:
            state.run_simulation()
            window.results_panel.refresh(state)

            def window_color() -> str:
                return qapp.palette().color(QPalette.ColorRole.Window).name()

            def first_figure_facecolor() -> tuple:
                page = next(iter(window.results_panel._plot_pages.values()))
                return page.layout().itemAt(1).widget().figure.get_facecolor()

            default_color = window_color()
            light_face = first_figure_facecolor()
            assert window.theme == "light"
            assert window.theme_actions["Light"].isChecked()

            window.theme_actions["Dark"].trigger()
            assert window.theme == "dark"
            assert window_color() == "#353535"
            dark_face = first_figure_facecolor()
            assert dark_face != light_face
            assert dark_face[:3] == pytest.approx((0.0, 0.0, 0.0))  # dark_background
            # Every plot tab re-rendered to the dark style.
            for page in window.results_panel._plot_pages.values():
                face = page.layout().itemAt(1).widget().figure.get_facecolor()
                assert face[:3] == pytest.approx((0.0, 0.0, 0.0))

            window.theme_actions["Light"].trigger()
            assert window.theme == "light"
            assert window_color() == default_color
            assert first_figure_facecolor() == pytest.approx(light_face)
        finally:
            # Never leak a dark palette/style into other tests.
            window.apply_theme("light")
            window.deleteLater()


# ---------------------------------------------------------------------------
# Glossary and (i) info icons
# ---------------------------------------------------------------------------

class TestGlossary:
    def test_every_glossary_key_renders_in_the_gui(self, qapp: QApplication) -> None:
        from orp.gui.glossary import GLOSSARY
        from orp.gui.info_icon import InfoIcon

        window = MainWindow(AppState())
        try:
            icons = window.findChildren(InfoIcon)
            rendered_keys = {icon.glossary_key for icon in icons}
            assert rendered_keys == set(GLOSSARY), (
                f"missing from GUI: {set(GLOSSARY) - rendered_keys}; "
                f"unknown keys: {rendered_keys - set(GLOSSARY)}"
            )
        finally:
            window.deleteLater()

    def test_every_icon_resolves_to_a_nonempty_entry_as_tooltip(
        self, qapp: QApplication
    ) -> None:
        from orp.gui.glossary import GLOSSARY
        from orp.gui.info_icon import InfoIcon

        window = MainWindow(AppState())
        try:
            for icon in window.findChildren(InfoIcon):
                entry = GLOSSARY[icon.glossary_key]
                assert entry.strip(), f"empty glossary entry for {icon.glossary_key!r}"
                assert icon.toolTip() == entry
        finally:
            window.deleteLater()

    def test_click_shows_the_glossary_text_in_a_popover(
        self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from PyQt6.QtWidgets import QMessageBox

        from orp.gui.glossary import GLOSSARY
        from orp.gui.info_icon import InfoIcon

        shown: list[tuple[str, str]] = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda _parent, title, text: shown.append((title, text))),
        )
        window = MainWindow(AppState())
        try:
            icon = window.findChildren(InfoIcon)[0]
            icon.click()
            assert shown == [(icon.glossary_key, GLOSSARY[icon.glossary_key])]
        finally:
            window.deleteLater()

    def test_no_glossary_text_contains_endpoint_seeking_vocabulary(self) -> None:
        """The honesty guard and the wall apply to tooltip content too (the same
        negation-aware scanner as THE GUI WALL: 'an input, not a target' is the
        wall's own signage)."""
        from orp.gui.glossary import GLOSSARY
        from orp.tests.test_gui_wall import _violations

        offending = {
            key: terms for key, text in GLOSSARY.items() if (terms := _violations(text))
        }
        assert not offending, f"endpoint-seeking vocabulary in glossary: {offending}"

    def test_provenance_definitions_restate_the_documented_meanings_exactly(
        self,
    ) -> None:
        """The tag entries must contain the documented sentences verbatim — plain
        language may follow, but the meaning is never paraphrased or softened."""
        from orp.core.provenance.tags import ValidationLevel
        from orp.gui.glossary import GLOSSARY

        for level in ValidationLevel:
            assert level.description in GLOSSARY[level.name], (
                f"{level.name}: glossary entry does not restate the documented "
                f"meaning exactly ({level.description!r})"
            )
        # The dataset tag, verbatim from data/flights/artemis1_bank_commanded.csv.
        assert (
            "pixel extraction from a published figure; not flight telemetry"
            in GLOSSARY["MACHINE-DIGITIZED"]
        )
        # The weakest-link principle, verbatim from the README/provenance docs.
        assert (
            "a trajectory is only as trustworthy as the weakest input that produced it"
            in GLOSSARY["weakest link"]
        )
        # The heading entry states input, not target.
        assert "an input, not a target" in GLOSSARY["initial heading"]


# ---------------------------------------------------------------------------
# THE GUI WALL on the fully populated window
# ---------------------------------------------------------------------------

class TestWallOnPopulatedWindow:
    def test_wall_holds_after_full_run(self, qapp: QApplication) -> None:
        state = _fast_state()
        window = MainWindow(state)
        try:
            state.run_simulation()
            state.refresh_gates()
            window.results_panel.refresh(state)
            assert_wall_holds(window)
        finally:
            window.deleteLater()


# ---------------------------------------------------------------------------
# CLI / GUI identity
# ---------------------------------------------------------------------------

class TestCliGuiIdentity:
    def test_identical_flight_data_byte_equal_csv(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The same inputs through the CLI and through AppState must yield identical
        FlightData — asserted as byte-equality of the shared trajectory CSV export."""
        from orp.cli import main as cli_main

        out_dir = tmp_path / "cli_out"
        rc = cli_main([
            "run", "--vehicle", "apollo", "--planet", "earth",
            "--frame", "planet-relative", "--bank-deg", "60",
            "--dt", "1.0", "--max-time", "120", "--out", str(out_dir),
        ])
        assert rc == 0

        state = _fast_state()  # apollo / earth / constant 60 / dt 1.0 / 120 s
        state.run_simulation()
        gui_csv = tmp_path / "gui_trajectory.csv"
        state.export_csv_to(gui_csv)

        cli_bytes = (out_dir / "trajectory.csv").read_bytes()
        gui_bytes = gui_csv.read_bytes()
        assert cli_bytes == gui_bytes, (
            "CLI and GUI produced different FlightData from identical inputs"
        )
