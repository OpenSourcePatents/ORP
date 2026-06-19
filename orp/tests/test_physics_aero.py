# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics verification for Modified Newtonian aerodynamics."""

from __future__ import annotations

import math

import pytest

from orp.core.aerodynamics.calculator import AerodynamicForces
from orp.core.aerodynamics.flight_conditions import FlightConditions
from orp.core.aerodynamics.newtonian import (
    ModifiedNewtonianCalculator,
    stagnation_pressure_coefficient,
)
from orp.core.atmosphere.model import AtmosphericConditions
from orp.core.provenance.tags import ValidationLevel
from orp.core.vehicles import VehicleLibrary


def _conditions(velocity: float, alpha: float, reference_area: float, *, gamma: float = 1.4):
    """A FlightConditions at a chosen velocity/AoA with an atmosphere fixing the Mach number."""
    atmosphere = AtmosphericConditions(
        temperature=200.0, pressure=100.0, specific_gas_constant=287.0, specific_heat_ratio=gamma
    )
    return FlightConditions(
        velocity=velocity,
        angle_of_attack=alpha,
        atmosphere=atmosphere,
        reference_area=reference_area,
    )


class TestStagnationPressureCoefficient:
    """Rayleigh pitot Cp_max."""

    def test_hypersonic_asymptote_air(self) -> None:
        # γ = 1.4 hypersonic limit ≈ 1.839.
        assert stagnation_pressure_coefficient(30.0, 1.4) == pytest.approx(1.839, abs=0.005)

    def test_incompressible_limit(self) -> None:
        assert stagnation_pressure_coefficient(1e-9, 1.4) == pytest.approx(1.0, abs=0.01)

    def test_monotone_rise_through_transonic(self) -> None:
        assert stagnation_pressure_coefficient(0.5, 1.4) < stagnation_pressure_coefficient(3.0, 1.4)


class TestApolloNewtonian:
    """Apollo (modelled as a spherical-segment forebody)."""

    def setup_method(self) -> None:
        self.calc = ModifiedNewtonianCalculator()
        self.apollo = VehicleLibrary().load("apollo")

    def test_zero_lift_at_zero_alpha(self) -> None:
        # Axisymmetric body at α=0 → no lift.
        fc = _conditions(7000.0, 0.0, self.apollo.reference_area.get())
        forces = self.calc.calculate_forces(self.apollo, fc)
        assert abs(forces.lift_to_drag) < 0.01
        assert abs(forces.lift_coefficient) < 0.01

    def test_drag_positive_and_blunt(self) -> None:
        fc = _conditions(7000.0, 0.0, self.apollo.reference_area.get())
        forces = self.calc.calculate_forces(self.apollo, fc)
        assert forces.drag_coefficient > 1.0  # a very blunt body


class TestMSLNewtonian:
    """MSL 70° sphere-cone."""

    def setup_method(self) -> None:
        self.calc = ModifiedNewtonianCalculator()
        self.msl = VehicleLibrary().load("msl")
        self.area = self.msl.reference_area.get()
        self.trim = self.msl.trim_angle_of_attack.get()  # ~16°

    def test_drag_at_zero_alpha_matches_nominal(self) -> None:
        # Newtonian C_D for a 70° sphere-cone ≈ 1.66, close to the nominal 1.68.
        fc = _conditions(4000.0, 0.0, self.area, gamma=1.29)
        forces = self.calc.calculate_forces(self.msl, fc)
        assert forces.drag_coefficient == pytest.approx(1.66, abs=0.1)

    def test_trim_lift_to_drag(self) -> None:
        # The headline verification: MSL trimmed L/D ≈ 0.24.
        fc = _conditions(4000.0, self.trim, self.area, gamma=1.29)
        forces = self.calc.calculate_forces(self.msl, fc)
        assert forces.lift_to_drag == pytest.approx(0.24, abs=0.03)

    def test_lift_to_drag_is_mach_independent(self) -> None:
        # Newtonian L/D depends only on geometry + α, not Mach.
        slow = self.calc.calculate_forces(self.msl, _conditions(1500.0, self.trim, self.area, gamma=1.29))
        fast = self.calc.calculate_forces(self.msl, _conditions(6000.0, self.trim, self.area, gamma=1.29))
        assert slow.lift_to_drag == pytest.approx(fast.lift_to_drag, rel=1e-3)

    def test_lift_increases_with_alpha(self) -> None:
        ld = [
            self.calc.calculate_forces(self.msl, _conditions(4000.0, math.radians(a), self.area, gamma=1.29)).lift_to_drag
            for a in (0, 8, 16, 24)
        ]
        assert ld[0] == pytest.approx(0.0, abs=0.01)
        assert ld[1] < ld[2] < ld[3]  # L/D rises with angle of attack

    def test_provenance_verified_source(self) -> None:
        # Analytical textbook method (Anderson), not a CFD cross-check by this project.
        assert self.calc.provenance.level is ValidationLevel.VERIFIED_SOURCE


class TestFullPhysicsIntegration:
    """The whole physics chain (real atmosphere + gravity + Newtonian aero + EOM)."""

    def test_msl_mars_entry_with_real_newtonian(self) -> None:
        import math as _math

        from orp.core.bank_schedule import BankSchedule
        from orp.core.planet import MARS
        from orp.core.provenance.tags import ProvenanceTag
        from orp.core.simulation import SimulationConditions, SimulationEngine
        from orp.core.simulation import flight_data as fd

        msl = VehicleLibrary().load("msl")
        # A flight-reconstructed bank schedule (so only the vehicle's ASSERTED geometry limits us).
        schedule = BankSchedule.constant(
            _math.radians(0.0),
            provenance=ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "MSL EDL reconstruction"),
        )
        conditions = SimulationConditions(
            vehicle=msl,
            planet=MARS,
            bank_schedule=schedule,
            aerodynamic_calculator=ModifiedNewtonianCalculator(),
            entry_velocity=5800.0,
            entry_flight_path_angle=_math.radians(-15.5),
            entry_altitude=125_000.0,
            time_step=0.5,
            max_simulation_time=1500.0,
        )
        flight_data = SimulationEngine().simulate(conditions)
        branch = flight_data.get_branch(0)

        velocity = branch.get(fd.TYPE_VELOCITY)
        decel = [v for v in branch.get(fd.TYPE_DECELERATION) if math.isfinite(v)]
        heat = [v for v in branch.get(fd.TYPE_HEAT_RATE) if math.isfinite(v)]
        assert velocity[-1] < velocity[0]
        assert max(decel) > 1.0
        assert max(heat) > 0.0
        # Provenance propagation: all models are VERIFIED_*, but MSL's ASSERTED geometry
        # is the weakest link, so the trajectory is ASSERTED — exactly the point of the system.
        assert flight_data.provenance.level is ValidationLevel.ASSERTED
