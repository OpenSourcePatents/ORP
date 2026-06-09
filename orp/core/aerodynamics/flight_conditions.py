# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Momentary flight conditions fed into every aerodynamic calculation.

Mirrors OpenRocket's ``FlightConditions``: a mutable bundle of the instantaneous state the
aerodynamics need. It is rebuilt (or updated in place) every integration sub-step from the
:class:`~orp.core.simulation.status.SimulationStatus` and the atmosphere model.

Air-relative velocity is the primary quantity (the natural reentry state variable); Mach,
dynamic pressure, and Reynolds number are derived from it and the local atmosphere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orp.core.atmosphere.model import AtmosphericConditions

__all__ = ["FlightConditions"]


@dataclass
class FlightConditions:
    """Instantaneous flight state for aerodynamic coefficient computation.

    Mutable by design (it is updated each step). Derived quantities are read-only
    properties so they cannot drift out of sync with the primary fields.

    Attributes:
        velocity: Air-relative speed, m/s (primary).
        angle_of_attack: Total angle of attack α, radians.
        atmosphere: Local :class:`~orp.core.atmosphere.model.AtmosphericConditions`.
        reference_area: Aerodynamic reference area S, m² (from the vehicle).
        reference_length: Aerodynamic reference length, m (from the vehicle; for moments
            and Reynolds number).
        bank_angle: Bank (roll about the velocity vector) σ, radians. Carried here for
            reporting/output only — it does **not** affect the force coefficients; the EOM
            uses it to orient the lift vector. It is set from the replayed
            :class:`~orp.core.bank_schedule.schedule.BankSchedule`, never solved for.
    """

    velocity: float = 0.0
    angle_of_attack: float = 0.0
    atmosphere: AtmosphericConditions = field(
        default_factory=lambda: AtmosphericConditions(
            temperature=0.0,
            pressure=0.0,
            specific_gas_constant=0.0,
            specific_heat_ratio=0.0,
        )
    )
    reference_area: float = 1.0
    reference_length: float = 1.0
    bank_angle: float = 0.0

    @property
    def mach(self) -> float:
        """Mach number M = V / a. Zero if the local speed of sound is zero."""
        a = self.atmosphere.speed_of_sound
        if a <= 0.0:
            return 0.0
        return self.velocity / a

    @property
    def dynamic_pressure(self) -> float:
        """Dynamic pressure q = ½·ρ·V², Pa."""
        return 0.5 * self.atmosphere.density * self.velocity * self.velocity

    @property
    def reynolds_number(self) -> float:
        """Reynolds number Re = V·L_ref / ν. Zero if kinematic viscosity is zero."""
        nu = self.atmosphere.kinematic_viscosity
        if nu <= 0.0:
            return 0.0
        return self.velocity * self.reference_length / nu
