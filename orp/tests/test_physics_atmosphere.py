# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics verification for the atmosphere models (Earth ISA, Mars exponential)."""

from __future__ import annotations

import math

import pytest

from orp.core.atmosphere.earth import EarthISAModel
from orp.core.atmosphere.mars import MarsAtmosphereModel
from orp.core.provenance.tags import ValidationLevel


class TestEarthISA:
    """U.S. Standard Atmosphere 1976 verification."""

    def setup_method(self) -> None:
        self.model = EarthISAModel()

    def test_sea_level_temperature(self) -> None:
        assert self.model.get_conditions(0.0).temperature == pytest.approx(288.15, abs=0.01)

    def test_tropopause_temperature(self) -> None:
        # T at the 11 km tropopause boundary is the ISA's defining value.
        assert self.model.get_conditions(11_000.0).temperature == pytest.approx(216.65, abs=0.01)

    def test_sea_level_density(self) -> None:
        assert self.model.get_conditions(0.0).density == pytest.approx(1.225, abs=0.001)

    def test_sea_level_pressure(self) -> None:
        assert self.model.get_conditions(0.0).pressure == pytest.approx(101325.0, rel=1e-4)

    def test_sea_level_speed_of_sound(self) -> None:
        # Standard ISA sea-level speed of sound ≈ 340.29 m/s.
        assert self.model.get_conditions(0.0).speed_of_sound == pytest.approx(340.29, abs=0.1)

    def test_tropopause_pressure_matches_standard_table(self) -> None:
        # ISA tropopause pressure ≈ 22 632 Pa (standard table value).
        assert self.model.get_conditions(11_000.0).pressure == pytest.approx(22_632.0, rel=2e-3)

    def test_stratopause_temperature(self) -> None:
        # 47 km stratopause base temperature is 270.65 K.
        assert self.model.get_conditions(47_000.0).temperature == pytest.approx(270.65, abs=0.01)

    def test_pressure_decreases_monotonically(self) -> None:
        prev = float("inf")
        for h in range(0, 86_000, 1000):
            p = self.model.get_conditions(float(h)).pressure
            assert p < prev
            prev = p

    def test_temperature_profile_finite_and_positive(self) -> None:
        for h in range(0, 90_000, 500):
            c = self.model.get_conditions(float(h))
            assert math.isfinite(c.temperature) and c.temperature > 0.0
            assert math.isfinite(c.density) and c.density >= 0.0

    def test_above_model_top_is_clamped(self) -> None:
        top = self.model.get_conditions(84_852.0)
        above = self.model.get_conditions(120_000.0)
        assert above.temperature == pytest.approx(top.temperature)
        assert above.pressure == pytest.approx(top.pressure)

    def test_provenance_verified_flight(self) -> None:
        prov = self.model.provenance
        assert prov.level is ValidationLevel.VERIFIED_FLIGHT
        assert "1976" in prov.source


class TestMarsAtmosphere:
    """Mars isothermal exponential model verification."""

    def setup_method(self) -> None:
        self.model = MarsAtmosphereModel()

    def test_surface_temperature(self) -> None:
        assert self.model.get_conditions(0.0).temperature == pytest.approx(210.0, abs=1.0)

    def test_surface_pressure(self) -> None:
        # The famous Mars surface pressure: ~636 Pa (6.36 mbar).
        assert self.model.get_conditions(0.0).pressure == pytest.approx(636.0, rel=0.02)

    def test_surface_density_is_ideal_gas_consistent(self) -> None:
        # ρ = P/(R·T) = 636/(188.92·210) = 0.0160 kg/m³ — the ideal-gas-consistent value
        # (≈ the 0.0159 used by standard Mars-EDL exponential models). The frequently-quoted
        # 0.020 kg/m³ is a rounded fact-sheet figure inconsistent with the measured P and T.
        rho = self.model.get_conditions(0.0).density
        assert rho == pytest.approx(0.0160, abs=0.0005)
        assert 0.015 < rho < 0.017

    def test_surface_speed_of_sound(self) -> None:
        # CO₂ at 210 K: a = sqrt(1.29·188.92·210) ≈ 226 m/s.
        assert self.model.get_conditions(0.0).speed_of_sound == pytest.approx(226.0, abs=2.0)

    def test_exponential_decay_one_scale_height(self) -> None:
        h = self.model.SCALE_HEIGHT
        ratio = self.model.get_conditions(h).pressure / self.model.get_conditions(0.0).pressure
        assert ratio == pytest.approx(math.exp(-1.0), rel=1e-6)

    def test_scale_height_reasonable(self) -> None:
        # Mars scale height is ~10–11 km.
        assert 10_000.0 < self.model.SCALE_HEIGHT < 11_500.0

    def test_density_decreases_with_altitude(self) -> None:
        prev = float("inf")
        for h in range(0, 120_000, 2000):
            rho = self.model.get_conditions(float(h)).density
            assert rho < prev
            prev = rho

    def test_uses_co2_gas_constant(self) -> None:
        # Distinct from Earth air — proves the multi-planet abstraction.
        assert self.model.get_conditions(0.0).specific_gas_constant == pytest.approx(188.92)

    def test_provenance_verified_flight(self) -> None:
        assert self.model.provenance.level is ValidationLevel.VERIFIED_FLIGHT
