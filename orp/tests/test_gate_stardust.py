# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Stardust gate — forward ballistic entry vs sourced flight truths.

Asserts the forward prediction (rotation on, sourced CD) reproduces the reconstruction
truths within the flight 3-sigma, that the EI-latitude assumption is a weak sensitivity, and
that the rotating-planet result sits well below the flat-Earth Allen-Eggers value (the
superorbital centrifugal shallowing).
"""

from __future__ import annotations

import pytest

from orp.gates import gate_stardust as gs
from orp.core.provenance.tags import ValidationLevel
from orp.core.vehicles import VehicleLibrary

# Run the (deterministic) latitude sweep once for the whole module — each run_sweep() is
# five forward integrations, so re-running it per test method would be needlessly slow.
_ROWS = gs.run_sweep()


class TestStardustGate:
    def setup_method(self) -> None:
        self.rows = _ROWS

    def test_status_not_validated(self) -> None:
        assert gs.GATE_STARDUST_STATUS == "NOT_VALIDATED"

    def test_sweep_covers_all_assumed_latitudes(self) -> None:
        assert len(self.rows) == len(gs.EI_LATITUDE_SWEEP_DEG)

    def test_peak_g_within_flight_three_sigma(self) -> None:
        for r in self.rows:
            assert abs(r["peak_g"] - gs.TRUTH_PEAK_G) <= gs.TRUTH_PEAK_G_3SIGMA, r

    def test_mach123_altitude_near_truth(self) -> None:
        # Truth 31.03 km; constant hypersonic CD overshoots slightly -> within a few km.
        for r in self.rows:
            assert r["h_at_mach123_km"] == pytest.approx(gs.TRUTH_MACH_ALTITUDE_KM, abs=3.0)

    def test_mach123_time_near_drogue(self) -> None:
        # Reaching Mach 1.23 precedes drogue deploy (137.9 s) by a few seconds.
        for r in self.rows:
            assert r["t_at_mach123_s"] == pytest.approx(gs.TRUTH_DROGUE_TIME_S, abs=10.0)

    def test_ei_latitude_is_a_weak_sensitivity(self) -> None:
        peaks = [r["peak_g"] for r in self.rows]
        assert max(peaks) - min(peaks) < 1.0  # < 1 g across the swept latitudes

    def test_centrifugal_shallowing_vs_flat_earth(self) -> None:
        # Flat-Earth Allen-Eggers is far higher than the rotating-planet result.
        for r in self.rows:
            assert r["allen_eggers_flat_g"] > 1.5 * r["peak_g"]
            assert r["allen_eggers_flat_g"] == pytest.approx(60.0, abs=5.0)


class TestStardustVehicle:
    def test_geometry_sourced_from_mitcheltree(self) -> None:
        v = VehicleLibrary().load("stardust")
        v.validate()
        assert v.nose_radius.get() == pytest.approx(0.2286)
        assert v.reference_area.get() == pytest.approx(0.51887)
        assert v.drag_coefficient.get() == pytest.approx(1.61)
        assert v.lift_to_drag.get() == 0.0  # ballistic
        # All properties are Mitcheltree-sourced -> vehicle is ASSERTED (not NOT_VALIDATED).
        assert v.provenance.level is ValidationLevel.ASSERTED
