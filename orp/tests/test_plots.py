# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the headless plotting module (no GUI, provenance stamped on every figure)."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("matplotlib", reason="plotting tests require matplotlib")

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.bank_schedule import BankSchedule
from orp.core.planet import EARTH
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.vehicles import VehicleLibrary
from orp.gui import plots


@pytest.fixture(scope="module")
def flight_data():
    """A short but real Apollo-like entry so every plotted channel has content."""
    apollo = VehicleLibrary().load("apollo")
    conditions = SimulationConditions(
        vehicle=apollo,
        planet=EARTH,
        bank_schedule=BankSchedule.constant(math.radians(30.0)),
        aerodynamic_calculator=ConstantCoefficientCalculator(
            apollo.drag_coefficient.get(),
            apollo.lift_to_drag.get(),
            provenance=ProvenanceTag(ValidationLevel.ASSERTED, "vehicle nominal coefficients"),
        ),
        entry_velocity=7800.0,
        entry_flight_path_angle=math.radians(-6.5),
        entry_altitude=122_000.0,
        entry_latitude=math.radians(28.5),
        time_step=2.0,
        max_simulation_time=120.0,
    )
    return SimulationEngine().simulate(conditions)


def _stamp_texts(figure) -> list[str]:
    return [text.get_text() for text in figure.texts]


class TestIndividualPlots:
    @pytest.mark.parametrize(
        "plotter",
        [
            plots.plot_altitude_time,
            plots.plot_velocity_time,
            plots.plot_g_load_time,
            plots.plot_heat_rate_time,
            plots.plot_ground_track,
            plots.plot_coefficients_mach,
            plots.plot_dynamic_pressure_altitude,
            plots.plot_specific_force_time,
        ],
    )
    def test_returns_figure_with_provenance_stamp(self, flight_data, plotter) -> None:
        figure = plotter(flight_data)
        stamps = [t for t in _stamp_texts(figure) if t.startswith("Provenance:")]
        assert len(stamps) == 1
        # The stamp names the run's weakest-link level — printed on the artifact itself.
        assert flight_data.provenance.level.name in stamps[0]

    @pytest.mark.parametrize(
        "plotter",
        [
            plots.plot_altitude_time,
            plots.plot_velocity_time,
            plots.plot_g_load_time,
            plots.plot_heat_rate_time,
            plots.plot_ground_track,
            plots.plot_coefficients_mach,
            plots.plot_dynamic_pressure_altitude,
            plots.plot_specific_force_time,
        ],
    )
    def test_stamp_suppressed_only_on_explicit_request(self, flight_data, plotter) -> None:
        """stamp_provenance=False drops the figure stamp (for displays that carry
        the provenance prominently themselves); the default stays stamped."""
        unstamped = plotter(flight_data, stamp_provenance=False)
        assert not [t for t in _stamp_texts(unstamped) if t.startswith("Provenance:")]
        stamped = plotter(flight_data)
        assert [t for t in _stamp_texts(stamped) if t.startswith("Provenance:")]

    def test_saves_png_when_path_given(self, flight_data, tmp_path) -> None:
        target = tmp_path / "altitude.png"
        plots.plot_altitude_time(flight_data, target)
        assert target.is_file()
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


class TestSaveStandardPlots:
    def test_writes_all_five_figures(self, flight_data, tmp_path) -> None:
        written = plots.save_standard_plots(flight_data, tmp_path / "out")
        assert [p.name for p in written] == [
            "altitude_time.png",
            "velocity_time.png",
            "g_load_time.png",
            "heat_rate_time.png",
            "ground_track.png",
        ]
        for path in written:
            assert path.is_file()
            assert path.stat().st_size > 0


class TestNewChannelPlots:
    """The three trajectory-channel plots: real content, PNG save, labeled axes."""

    def test_coefficients_mach_traces_flight(self, flight_data, tmp_path) -> None:
        target = tmp_path / "cd_cl_mach.png"
        figure = plots.plot_coefficients_mach(flight_data, target)
        axes = figure.axes[0]
        # Two coefficient traces plus the entry/end flight-point markers.
        assert len(axes.lines) >= 4
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_dynamic_pressure_altitude_axes(self, flight_data, tmp_path) -> None:
        target = tmp_path / "q_alt.png"
        figure = plots.plot_dynamic_pressure_altitude(flight_data, target)
        axes = figure.axes[0]
        assert "Dynamic pressure" in axes.get_xlabel()
        assert "Altitude" in axes.get_ylabel()
        assert target.is_file() and target.stat().st_size > 0

    def test_specific_force_decomposition_three_series(self, flight_data, tmp_path) -> None:
        target = tmp_path / "specific_force.png"
        figure = plots.plot_specific_force_time(flight_data, target)
        axes = figure.axes[0]
        labels = [line.get_label() for line in axes.lines]
        assert any("axial" in label for label in labels)
        assert any("lateral" in label for label in labels)
        assert any("RSS" in label for label in labels)
        assert target.is_file() and target.stat().st_size > 0


class TestHeadlessDiscipline:
    def test_module_import_does_not_require_matplotlib_import_machinery(self) -> None:
        # The module is import-safe without matplotlib; the lazy import lives inside the
        # plotting calls. (matplotlib IS installed here, so just verify no pyplot leak.)
        import sys

        import orp.gui.plots  # noqa: F401  (idempotent re-import)

        # Building figures via matplotlib.figure.Figure must not have pulled in pyplot —
        # pyplot is the GUI/state machinery this module promises never to touch.
        assert "matplotlib.pyplot" not in sys.modules

    def test_empty_flight_data_raises_cleanly(self) -> None:
        from orp.core.simulation.flight_data import FlightData

        with pytest.raises(ValueError):
            plots.plot_altitude_time(FlightData())
