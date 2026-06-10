# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests: import every core module, and exercise the wiring end-to-end.

The first test guarantees the whole import graph is sound (no circular imports, no syntax
errors). The remaining tests confirm the architectural seams actually connect: a vehicle
loads with provenance, a forward simulation runs and returns provenanced flight data, and the
provenance-propagation and forward-only invariants hold.
"""

from __future__ import annotations

import importlib

import pytest

# Every importable module in the package — the core of this smoke test.
ALL_MODULES = [
    "orp",
    "orp.core",
    "orp.core.provenance",
    "orp.core.provenance.tags",
    "orp.core.planet",
    "orp.core.planet.planet",
    "orp.core.planet.registry",
    "orp.core.atmosphere",
    "orp.core.atmosphere.model",
    "orp.core.atmosphere.earth",
    "orp.core.atmosphere.mars",
    "orp.core.gravity",
    "orp.core.gravity.model",
    "orp.core.gravity.earth",
    "orp.core.gravity.mars",
    "orp.core.aerodynamics",
    "orp.core.aerodynamics.flight_conditions",
    "orp.core.aerodynamics.calculator",
    "orp.core.aerodynamics.newtonian",
    "orp.core.bank_schedule",
    "orp.core.bank_schedule.schedule",
    "orp.core.vehicles",
    "orp.core.vehicles.base",
    "orp.core.vehicles.library",
    "orp.core.simulation",
    "orp.core.simulation.status",
    "orp.core.simulation.conditions",
    "orp.core.simulation.flight_data",
    "orp.core.simulation.stepper",
    "orp.core.simulation.engine",
    "orp.core.frames",
    "orp.gui",
]


@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_module_imports(module_name: str) -> None:
    """Every core module imports cleanly."""
    assert importlib.import_module(module_name) is not None


def test_planet_registry_has_earth_and_mars() -> None:
    """The multi-planet abstraction ships Earth and Mars from day one."""
    from orp.core.planet import EARTH, MARS, by_name

    assert EARTH.name == "Earth"
    assert MARS.name == "Mars"
    assert by_name("earth") is EARTH
    assert by_name("MARS") is MARS
    # Distinct atmospheres prove the abstraction is real, not Earth-with-a-label.
    assert EARTH.mean_radius != MARS.mean_radius
    assert (
        EARTH.atmosphere.get_conditions(0.0).specific_gas_constant
        != MARS.atmosphere.get_conditions(0.0).specific_gas_constant
    )


def test_provenance_weakest_link() -> None:
    """Provenance combines to the weakest input level."""
    from orp.core.provenance import ProvenanceTag, ValidationLevel, weakest

    combined = weakest(
        [
            ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "telemetry"),
            ProvenanceTag(ValidationLevel.NOT_VALIDATED, "guess"),
        ]
    )
    assert combined.level is ValidationLevel.NOT_VALIDATED


def test_vehicle_library_loads_apollo_with_provenance() -> None:
    """Apollo loads from YAML, every property is provenance-tagged, and it validates."""
    from orp.core.provenance import ValidationLevel
    from orp.core.vehicles import VehicleLibrary

    library = VehicleLibrary()
    assert set(library.list_available()) >= {"apollo", "msl"}

    apollo = library.load("apollo")
    apollo.validate()
    assert apollo.mass.get() > 0.0
    assert apollo.mass.provenance.source != ""  # citation required in spirit
    assert apollo.mass.level is ValidationLevel.VERIFIED_FLIGHT
    # Weakest-link: ASSERTED properties drag the vehicle down from VERIFIED_FLIGHT.
    assert apollo.provenance.level is ValidationLevel.ASSERTED
    assert apollo.ballistic_coefficient() > 0.0


def test_forward_simulation_runs_and_is_provenanced() -> None:
    """A forward reentry simulation runs end-to-end and returns provenanced flight data."""
    from orp.core.bank_schedule import BankSchedule
    from orp.core.planet import EARTH
    from orp.core.provenance import ValidationLevel
    from orp.core.simulation import SimulationConditions, SimulationEngine
    from orp.core.vehicles import VehicleLibrary

    vehicle = VehicleLibrary().load("apollo")
    conditions = SimulationConditions(
        vehicle=vehicle,
        planet=EARTH,
        bank_schedule=BankSchedule.constant(0.0),
        entry_altitude=120_000.0,
        time_step=1.0,
        max_simulation_time=5.0,
    )

    flight_data = SimulationEngine().simulate(conditions)

    branch = flight_data.get_branch(0)
    assert branch.length > 0
    assert flight_data.branch_count == 1
    # Placeholder atmosphere/gravity/aero models are NOT_VALIDATED, so the whole
    # trajectory must come back NOT_VALIDATED — proof that provenance propagates.
    assert flight_data.provenance.level is ValidationLevel.NOT_VALIDATED
    assert branch.provenance.level is ValidationLevel.NOT_VALIDATED
    # The run terminated with a recorded event.
    assert branch.events[-1].name in {"SIMULATION_END", "GROUND_HIT", "STOPPED"}


# Vocabulary that would signal an inverse/guidance/targeting API — the forward-only wall
# forbids any of these tokens appearing in a public field or method name across the seams.
_FORBIDDEN_TOKENS = (
    "target",
    "solve",
    "optimize",
    "optimise",
    "guidance",
    "desired",
    "miss_distance",
    "downrange",
    "crossrange",
    "setpoint",
    "inverse",
    "retarget",
    "from_landing",
    "to_target",
)


def _offending(names: object) -> set[str]:
    """Return the public names that contain a forbidden targeting token."""
    return {
        name
        for name in names  # type: ignore[union-attr]
        if not name.startswith("_") and any(tok in name.lower() for tok in _FORBIDDEN_TOKENS)
    }


def test_bank_schedule_is_a_forward_replay() -> None:
    """The bank schedule is a pure, interpolated replay of σ(t) — never a solved control."""
    from orp.core.bank_schedule import BankSchedule
    from orp.core.provenance import ProvenanceTag, ValidationLevel

    schedule = BankSchedule(times=[0.0, 10.0], bank_angles=[0.0, 1.0])
    assert schedule.bank_angle_at(-1.0) == 0.0  # clamped to first sample
    assert schedule.bank_angle_at(5.0) == pytest.approx(0.5)  # linear interpolation
    assert schedule.bank_angle_at(99.0) == 1.0  # clamped to last sample

    # A schedule is a provenanced input (default unsourced; a real one can be tagged).
    assert schedule.provenance.level is ValidationLevel.NOT_VALIDATED
    flown = BankSchedule.constant(
        0.0, provenance=ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "telemetry")
    )
    assert flown.provenance.level is ValidationLevel.VERIFIED_FLIGHT

    # The forward-only wall: the schedule exposes no inverse/targeting API.
    assert _offending(dir(schedule)) == set()


def test_forward_only_wall_spans_all_three_seams() -> None:
    """No targeting/inverse API on the bank schedule, conditions, OR engine (the real seams)."""
    import dataclasses

    from orp.core.bank_schedule import BankSchedule
    from orp.core.simulation import SimulationConditions, SimulationEngine

    condition_fields = {f.name for f in dataclasses.fields(SimulationConditions)}
    assert _offending(condition_fields) == set(), "SimulationConditions gained a targeting field"
    assert _offending(dir(SimulationEngine)) == set(), "SimulationEngine gained a targeting method"
    assert _offending(dir(BankSchedule)) == set(), "BankSchedule gained a targeting method"
