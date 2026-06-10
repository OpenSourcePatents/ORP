# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the parametric bridge-fixture models.

:class:`~orp.core.aerodynamics.constant.ConstantCoefficientCalculator` and
:class:`~orp.core.atmosphere.exponential.ExponentialAtmosphere` exist so ORP can be run
with *matched inputs* against external reference implementations (and closed-form entry
theory). These tests pin their contracts: exact constancy, exact exponential density, the
provenance-required-by-construction rule, and scope (no targeting affordances).
"""

from __future__ import annotations

import math

import pytest

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.aerodynamics.flight_conditions import FlightConditions
from orp.core.atmosphere.exponential import ExponentialAtmosphere
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel


class TestConstantCoefficientCalculator:
    def test_coefficients_are_constant_across_conditions(self) -> None:
        calc = ConstantCoefficientCalculator(1.46, 0.25)
        atmos = ExponentialAtmosphere(0.020, 11_100.0)
        for altitude, velocity, alpha in (
            (120_000.0, 5500.0, 0.0),
            (40_000.0, 3000.0, 0.3),
            (5_000.0, 400.0, -0.2),
        ):
            conditions = FlightConditions(
                velocity=velocity,
                angle_of_attack=alpha,
                atmosphere=atmos.get_conditions(altitude),
                reference_area=5.515,
            )
            forces = calc.calculate_forces(None, conditions)  # vehicle unused by design
            assert forces.drag_coefficient == 1.46
            assert forces.lift_coefficient == pytest.approx(1.46 * 0.25)
            assert forces.lift_to_drag == pytest.approx(0.25)

    def test_ballistic_default(self) -> None:
        forces = ConstantCoefficientCalculator(1.2).calculate_forces(None, FlightConditions())
        assert forces.lift_coefficient == 0.0
        assert forces.lift_to_drag == 0.0

    def test_requires_positive_drag(self) -> None:
        with pytest.raises(ValueError):
            ConstantCoefficientCalculator(0.0)

    def test_unsourced_coefficients_are_not_validated(self) -> None:
        assert (
            ConstantCoefficientCalculator(1.0).provenance.level
            is ValidationLevel.NOT_VALIDATED
        )

    def test_carries_caller_provenance(self) -> None:
        tag = ProvenanceTag(ValidationLevel.ASSERTED, "external reference, case 3")
        calc = ConstantCoefficientCalculator(1.46, 0.25, provenance=tag)
        assert calc.provenance is tag
        assert calc.calculate_forces(None, FlightConditions()).provenance is tag


class TestExponentialAtmosphere:
    def test_density_is_exact_exponential(self) -> None:
        atmos = ExponentialAtmosphere(0.020, 11_100.0)
        assert atmos.density(0.0) == pytest.approx(0.020, rel=1e-15)
        assert atmos.density(11_100.0) == pytest.approx(0.020 * math.exp(-1.0), rel=1e-12)
        assert atmos.get_conditions(33_300.0).density == pytest.approx(
            0.020 * math.exp(-3.0), rel=1e-12
        )

    def test_conditions_density_matches_defining_density(self) -> None:
        atmos = ExponentialAtmosphere(1.225, 7_200.0)
        for h in (0.0, 1_000.0, 50_000.0, 120_000.0):
            assert atmos.get_conditions(h).density == pytest.approx(
                atmos.density(h), rel=1e-12
            )

    def test_vacuum_allowed(self) -> None:
        vacuum = ExponentialAtmosphere(0.0, 7_200.0)
        assert vacuum.density(0.0) == 0.0
        assert vacuum.get_conditions(10_000.0).density == 0.0

    def test_co2_gas_gives_co2_speed_of_sound(self) -> None:
        # Mars-like configuration: CO₂ at 210 K → a = √(1.29·188.92·210) ≈ 226.2 m/s.
        atmos = ExponentialAtmosphere(
            0.020, 11_100.0,
            temperature=210.0, specific_gas_constant=188.92, specific_heat_ratio=1.29,
        )
        assert atmos.get_conditions(0.0).speed_of_sound == pytest.approx(226.2, abs=0.5)

    def test_rejects_bad_parameters(self) -> None:
        with pytest.raises(ValueError):
            ExponentialAtmosphere(-1.0, 7_200.0)
        with pytest.raises(ValueError):
            ExponentialAtmosphere(1.0, 0.0)

    def test_unsourced_parameters_are_not_validated(self) -> None:
        assert (
            ExponentialAtmosphere(1.225, 7_200.0).provenance.level
            is ValidationLevel.NOT_VALIDATED
        )

    def test_carries_caller_provenance(self) -> None:
        tag = ProvenanceTag(ValidationLevel.ASSERTED, "matched to external reference")
        assert ExponentialAtmosphere(0.02, 11_100.0, provenance=tag).provenance is tag
