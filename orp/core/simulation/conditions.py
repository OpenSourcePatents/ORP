# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable simulation setup and the model dependency-injection container.

Mirrors OpenRocket's ``SimulationConditions``: it holds everything that does **not** change
during a run — the entry state, the integrator parameters, and (critically) the pluggable
physics strategies: the planet (atmosphere + gravity), the aerodynamic calculator, and the
*replayed* bank-angle schedule.

Note the deliberate shape of this object: it accepts a :class:`BankSchedule` (a control
history) and entry conditions, and the engine integrates them forward. There is no field for
a target landing site, because ORP never solves for one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from orp.core.aerodynamics.calculator import AerodynamicCalculator
from orp.core.aerodynamics.newtonian import ModifiedNewtonianCalculator
from orp.core.bank_schedule.schedule import BankSchedule
from orp.core.planet.planet import Planet
from orp.core.provenance.tags import ProvenanceTag, weakest
from orp.core.simulation.status import SimulationStatus
from orp.core.vehicles.base import EntryVehicle

__all__ = ["SimulationConditions"]


@dataclass(frozen=True)
class SimulationConditions:
    """Immutable inputs to one forward reentry simulation.

    Args:
        vehicle: The reentry vehicle (mass, geometry, aero descriptors).
        planet: The environment (atmosphere + gravity + shape + rotation).
        bank_schedule: The replayed bank-angle control history σ(t).
        aerodynamic_calculator: Strategy turning flight conditions into force coefficients.
            Defaults to :class:`ModifiedNewtonianCalculator`.
        entry_velocity: Planet-relative speed at entry interface, m/s.
        entry_flight_path_angle: γ at entry, radians (negative = descending).
        entry_altitude: Altitude at entry interface, m.
        entry_heading: ψ at entry, radians (from north toward east).
        entry_latitude: Latitude at entry, radians.
        entry_longitude: Longitude at entry, radians.
        time_step: Nominal integrator time step, seconds.
        max_simulation_time: Hard cap on simulated time, seconds.
        ground_altitude: Altitude at which the run terminates (landing), m.
        minimum_velocity: Speed below which the run is considered stopped, m/s.
    """

    vehicle: EntryVehicle
    planet: Planet
    bank_schedule: BankSchedule
    aerodynamic_calculator: AerodynamicCalculator = field(default_factory=ModifiedNewtonianCalculator)

    entry_velocity: float = 7800.0
    entry_flight_path_angle: float = math.radians(-6.5)
    entry_altitude: float = 120_000.0
    entry_heading: float = math.radians(90.0)
    entry_latitude: float = 0.0
    entry_longitude: float = 0.0

    time_step: float = 0.1
    max_simulation_time: float = 1200.0
    ground_altitude: float = 0.0
    minimum_velocity: float = 1.0e-3

    def create_initial_status(self) -> SimulationStatus:
        """Build the seeded :class:`SimulationStatus` at the entry interface (t = 0).

        The bank angle is initialized from the replayed schedule at t = 0.
        """
        return SimulationStatus(
            self,
            time=0.0,
            altitude=self.entry_altitude,
            latitude=self.entry_latitude,
            longitude=self.entry_longitude,
            velocity=self.entry_velocity,
            flight_path_angle=self.entry_flight_path_angle,
            heading=self.entry_heading,
            bank_angle=self.bank_schedule.bank_angle_at(0.0),
        )

    @property
    def provenance(self) -> ProvenanceTag:
        """Weakest-link provenance across every contributing input.

        This is the basis for the trajectory's overall validation tag: a result is only as
        trustworthy as the least-validated input that produced it. The replayed bank
        schedule is one such input (it drives the lift-vector orientation in the EOM), so
        its provenance is folded in alongside the vehicle, planet, and aerodynamic model.
        """
        return weakest(
            [
                self.vehicle.provenance,
                self.planet.provenance,
                self.aerodynamic_calculator.provenance,
                self.bank_schedule.provenance,
            ]
        )
