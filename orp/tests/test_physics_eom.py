# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics verification for the 3-DOF entry equations of motion (+ Sutton-Graves heating).

Modified Newtonian aerodynamics is implemented in a later seam; to exercise the EOM in
isolation these tests inject a constant-coefficient calculator that returns the vehicle's
flight-derived nominal C_D and L/D, so drag and lift are present and the trajectory actually
decelerates and heats.
"""

from __future__ import annotations

import math

import pytest

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.bank_schedule import BankSchedule
from orp.core.planet import EARTH
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary


class _ConstantAero(AerodynamicCalculator):
    """Constant C_D / C_L calculator (isolates the EOM from the Newtonian aero seam)."""

    def __init__(self, drag_coefficient: float, lift_coefficient: float) -> None:
        self._cd = drag_coefficient
        self._cl = lift_coefficient

    def calculate_forces(self, vehicle, conditions) -> AerodynamicForces:  # type: ignore[no-untyped-def]
        return AerodynamicForces(
            drag_coefficient=self._cd,
            lift_coefficient=self._cl,
            provenance=ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "test constant coefficients"),
        )

    def get_stall_angle(self) -> float:
        return math.pi

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "test constant coefficients")


def _run_apollo_entry(bank_angle: float, *, max_time: float = 1500.0):
    """Run the canonical Apollo-like Earth entry at a fixed bank angle; return the branch."""
    apollo = VehicleLibrary().load("apollo")
    cd = apollo.drag_coefficient.get()
    cl = cd * apollo.lift_to_drag.get()
    conditions = SimulationConditions(
        vehicle=apollo,
        planet=EARTH,
        bank_schedule=BankSchedule.constant(bank_angle),
        aerodynamic_calculator=_ConstantAero(cd, cl),
        entry_velocity=7800.0,
        entry_flight_path_angle=math.radians(-6.5),
        entry_altitude=122_000.0,
        entry_latitude=math.radians(28.5),
        time_step=0.5,
        max_simulation_time=max_time,
    )
    return SimulationEngine().simulate(conditions).get_branch(0)


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if math.isfinite(v)]


class TestApolloEntryEOM:
    """The canonical Apollo-like entry (V=7800 m/s, γ=−6.5°, h=122 km)."""

    def setup_method(self) -> None:
        # Lift-up (σ=0) is the realistic Apollo full-lift orientation.
        self.branch = _run_apollo_entry(bank_angle=0.0)

    def test_decelerates(self) -> None:
        velocity = self.branch.get(fd.TYPE_VELOCITY)
        assert velocity[0] == pytest.approx(7800.0, abs=1.0)
        assert velocity[-1] < 0.5 * velocity[0]  # substantial deceleration

    def test_descends(self) -> None:
        altitude = self.branch.get(fd.TYPE_ALTITUDE)
        assert altitude[0] == pytest.approx(122_000.0, abs=1.0)
        assert min(_finite(altitude)) < 60_000.0  # penetrates the atmosphere

    def test_deceleration_peak_exists_and_is_interior(self) -> None:
        decel = _finite(self.branch.get(fd.TYPE_DECELERATION))
        peak = max(decel)
        peak_index = decel.index(peak)
        assert peak > 3.0  # Apollo-class entry pulls several g
        assert 0 < peak_index < len(decel) - 1  # a genuine peak: rises then falls

    def test_heating_peak_exists_and_is_interior(self) -> None:
        heat = _finite(self.branch.get(fd.TYPE_HEAT_RATE))
        peak = max(heat)
        peak_index = heat.index(peak)
        assert peak > 0.0
        assert 0 < peak_index < len(heat) - 1  # heating rises then falls (a peak)

    def test_dynamic_pressure_peaks(self) -> None:
        q = _finite(self.branch.get(fd.TYPE_DYNAMIC_PRESSURE))
        assert max(q) > 0.0
        assert 0 < q.index(max(q)) < len(q) - 1

    def test_no_nans_in_trajectory(self) -> None:
        for channel in (fd.TYPE_ALTITUDE, fd.TYPE_VELOCITY, fd.TYPE_FLIGHT_PATH_ANGLE):
            assert all(math.isfinite(v) for v in self.branch.get(channel))


class TestBankAngleRotatesLift:
    """The replayed bank angle σ rotates the lift vector (forward replay, not a solve)."""

    def test_lift_down_is_steeper_than_lift_up(self) -> None:
        # σ=0 puts lift up (lofts, gentler); σ=180° puts lift down (steeper, higher g).
        up = _finite(_run_apollo_entry(bank_angle=0.0).get(fd.TYPE_DECELERATION))
        down = _finite(_run_apollo_entry(bank_angle=math.pi).get(fd.TYPE_DECELERATION))
        assert max(down) > max(up)  # lift-down entry pulls more g than lift-up

    def test_ninety_degree_bank_zero_vertical_lift(self) -> None:
        # σ=90° → cosσ=0 → no vertical lift → near-ballistic; still decelerates to the ground.
        branch = _run_apollo_entry(bank_angle=math.pi / 2)
        assert min(_finite(branch.get(fd.TYPE_ALTITUDE))) < 30_000.0


class TestMultiPlanetEntry:
    """The same EOM runs an MSL Mars entry through the injected Mars planet."""

    def test_mars_entry_decelerates_and_heats(self) -> None:
        from orp.core.planet import MARS

        msl = VehicleLibrary().load("msl")
        cd = msl.drag_coefficient.get()
        cl = cd * msl.lift_to_drag.get()
        conditions = SimulationConditions(
            vehicle=msl,
            planet=MARS,
            bank_schedule=BankSchedule.constant(0.0),
            aerodynamic_calculator=_ConstantAero(cd, cl),
            entry_velocity=5800.0,
            entry_flight_path_angle=math.radians(-15.5),
            entry_altitude=125_000.0,
            time_step=0.5,
            max_simulation_time=1500.0,
        )
        branch = SimulationEngine().simulate(conditions).get_branch(0)
        velocity = branch.get(fd.TYPE_VELOCITY)
        assert velocity[-1] < velocity[0]
        assert max(_finite(branch.get(fd.TYPE_DECELERATION))) > 1.0
        assert max(_finite(branch.get(fd.TYPE_HEAT_RATE))) > 0.0
