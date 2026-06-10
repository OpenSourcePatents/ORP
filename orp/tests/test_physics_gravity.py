# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics verification for the gravity models (Earth WGS84, Mars GM/r²)."""

from __future__ import annotations

import pytest

from orp.core.gravity.earth import EarthWGS84GravityModel
from orp.core.gravity.mars import MarsGravityModel
from orp.core.planet.planet import WorldCoordinate
from orp.core.provenance.tags import ValidationLevel


class TestEarthWGS84Gravity:
    """WGS84 Somigliana normal gravity verification."""

    def setup_method(self) -> None:
        self.model = EarthWGS84GravityModel()

    def test_equator_surface(self) -> None:
        g = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        assert g == pytest.approx(9.7803, abs=0.0005)

    def test_pole_surface(self) -> None:
        g = self.model.get_gravity(WorldCoordinate.from_degrees(90.0, 0.0, 0.0))
        assert g == pytest.approx(9.8322, abs=0.0005)

    def test_altitude_100km(self) -> None:
        # At mid-latitude (≈standard surface gravity) gravity at 100 km is ~9.505 m/s².
        g = self.model.get_gravity(WorldCoordinate.from_degrees(45.0, 0.0, 100_000.0))
        assert g == pytest.approx(9.505, abs=0.005)

    def test_gravity_decreases_with_altitude(self) -> None:
        g0 = self.model.get_gravity(WorldCoordinate.from_degrees(45.0, 0.0, 0.0))
        g100 = self.model.get_gravity(WorldCoordinate.from_degrees(45.0, 0.0, 100_000.0))
        assert g100 < g0

    def test_pole_exceeds_equator(self) -> None:
        g_eq = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        g_pole = self.model.get_gravity(WorldCoordinate.from_degrees(90.0, 0.0, 0.0))
        assert g_pole > g_eq

    def test_provenance_verified_flight(self) -> None:
        prov = self.model.provenance
        assert prov.level is ValidationLevel.VERIFIED_FLIGHT
        assert "WGS84" in prov.source


class TestMarsGravity:
    """Mars central-field gravity verification."""

    def setup_method(self) -> None:
        self.model = MarsGravityModel()

    def test_surface_gravity(self) -> None:
        g = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        # GM/R² ≈ 3.728 m/s² ≈ the commonly cited 3.72 m/s².
        assert g == pytest.approx(3.72, abs=0.01)

    def test_gravity_decreases_with_altitude(self) -> None:
        g0 = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        g125 = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 125_000.0))
        assert g125 < g0

    def test_much_weaker_than_earth(self) -> None:
        # Mars surface gravity is ~38% of Earth's — proves the multi-planet abstraction.
        mars = self.model.get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        earth = EarthWGS84GravityModel().get_gravity(WorldCoordinate.from_degrees(0.0, 0.0, 0.0))
        assert mars / earth == pytest.approx(0.38, abs=0.02)

    def test_provenance_verified_flight(self) -> None:
        assert self.model.provenance.level is ValidationLevel.VERIFIED_FLIGHT
