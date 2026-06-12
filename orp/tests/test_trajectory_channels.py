# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the first-class trajectory channels added in trajectory-channels.

Coverage:
  - CD, CL, L/D, angle of attack, dynamic pressure, Mach, and the two specific-force
    components are present and non-empty after a real Apollo run, with one value per
    recorded sample.
  - The specific-force RSS reproduces the existing g-load channel exactly (machine
    precision: the g-load is computed FROM the components, so the identity is bit-exact
    by construction).
  - Channel values are physically coherent with their sources (CD matches the constant
    calculator, alpha matches the vehicle trim value, L/D = CL/CD).
"""

from __future__ import annotations

import math

import pytest

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.bank_schedule import BankSchedule
from orp.core.planet import EARTH
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary

#: Standard gravity as the stepper uses it for the g-load reporting unit.
_STANDARD_GRAVITY = 9.80665

_NEW_CHANNELS = (
    fd.TYPE_DRAG_COEFFICIENT,
    fd.TYPE_LIFT_COEFFICIENT,
    fd.TYPE_LIFT_TO_DRAG,
    fd.TYPE_ANGLE_OF_ATTACK,
    fd.TYPE_DYNAMIC_PRESSURE,
    fd.TYPE_MACH,
    fd.TYPE_SPECIFIC_FORCE_AXIAL,
    fd.TYPE_SPECIFIC_FORCE_LATERAL,
)


@pytest.fixture(scope="module")
def apollo_run():
    """One real Apollo entry with the constant-coefficient calculator."""
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
        time_step=1.0,
        max_simulation_time=240.0,
    )
    result = SimulationEngine().simulate(conditions)
    return apollo, result.get_branch(0)


class TestChannelsPresent:
    def test_all_new_channels_present_and_full_length(self, apollo_run) -> None:
        _, branch = apollo_run
        assert branch.length > 1
        for dtype in _NEW_CHANNELS:
            series = branch.get(dtype)
            assert series, f"channel {dtype} is empty"
            assert len(series) == branch.length, (
                f"channel {dtype}: {len(series)} values for {branch.length} samples"
            )

    def test_channels_in_all_types_export_order(self) -> None:
        """The channels are first-class: every one is in ALL_TYPES (so trajectory.csv
        and any ALL_TYPES consumer exports them automatically)."""
        for dtype in _NEW_CHANNELS:
            assert dtype in fd.ALL_TYPES

    def test_values_match_their_sources(self, apollo_run) -> None:
        apollo, branch = apollo_run
        cd = branch.get(fd.TYPE_DRAG_COEFFICIENT)
        cl = branch.get(fd.TYPE_LIFT_COEFFICIENT)
        ld = branch.get(fd.TYPE_LIFT_TO_DRAG)
        alpha = branch.get(fd.TYPE_ANGLE_OF_ATTACK)

        # The constant calculator: CD fixed, CL = CD * (L/D), L/D = CL/CD.
        expected_cd = apollo.drag_coefficient.get()
        expected_cl = expected_cd * apollo.lift_to_drag.get()
        assert all(value == expected_cd for value in cd)
        assert all(value == pytest.approx(expected_cl, rel=1e-12) for value in cl)
        for cd_i, cl_i, ld_i in zip(cd, cl, ld):
            assert ld_i == (cl_i / cd_i if cd_i != 0.0 else 0.0)

        # Angle of attack records the vehicle trim value, in degrees like all angles.
        expected_alpha_deg = math.degrees(apollo.trim_angle_of_attack.get())
        assert all(value == expected_alpha_deg for value in alpha)

        # Dynamic pressure is positive once in the sensible atmosphere.
        q = branch.get(fd.TYPE_DYNAMIC_PRESSURE)
        assert max(q) > 0.0


class TestSpecificForce:
    def test_rss_matches_g_load_exactly(self, apollo_run) -> None:
        """hypot(axial, lateral) / g0 must equal the g-load channel bit-for-bit."""
        _, branch = apollo_run
        axial = branch.get(fd.TYPE_SPECIFIC_FORCE_AXIAL)
        lateral = branch.get(fd.TYPE_SPECIFIC_FORCE_LATERAL)
        g_load = branch.get(fd.TYPE_DECELERATION)
        assert len(axial) == len(lateral) == len(g_load) == branch.length
        for i, (ax, lat, nload) in enumerate(zip(axial, lateral, g_load)):
            assert math.hypot(ax, lat) / _STANDARD_GRAVITY == nload, (
                f"sample {i}: RSS(specific force)/g0 = "
                f"{math.hypot(ax, lat) / _STANDARD_GRAVITY!r} != g-load {nload!r}"
            )

    def test_components_are_force_per_mass(self, apollo_run) -> None:
        """Axial = drag/m and lateral = lift/m, against the recorded force channels."""
        apollo, branch = apollo_run
        mass = apollo.mass.get()
        drag = branch.get(fd.TYPE_DRAG_FORCE)
        lift = branch.get(fd.TYPE_LIFT_FORCE)
        axial = branch.get(fd.TYPE_SPECIFIC_FORCE_AXIAL)
        lateral = branch.get(fd.TYPE_SPECIFIC_FORCE_LATERAL)
        for d, l, ax, lat in zip(drag, lift, axial, lateral):
            assert ax == d / mass
            assert lat == l / mass
