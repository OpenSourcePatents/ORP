# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Modified Newtonian aerodynamics — the reentry-default calculator.

Modified Newtonian theory is the standard first-order method for hypersonic blunt-body
aerodynamics: surface pressure follows ``Cp = Cp_max · sin²θ`` where θ is the local angle
between the surface and the free stream, and ``Cp_max`` is the stagnation pressure
coefficient behind a normal shock. Integrating that pressure law over the body's wetted
geometry yields the axial and normal coefficients, hence C_D, C_L, and C_m as functions of
Mach and angle of attack.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.aerodynamics.flight_conditions import FlightConditions
    from orp.core.vehicles.base import EntryVehicle

__all__ = ["ModifiedNewtonianCalculator"]


class ModifiedNewtonianCalculator(AerodynamicCalculator):
    """Modified Newtonian hypersonic aerodynamics for axisymmetric blunt bodies.

    Args:
        stall_angle: Angle of attack (radians) beyond which results are flagged invalid.
            Defaults to 180° (Newtonian theory itself imposes no stall).
    """

    def __init__(self, stall_angle: float = math.pi) -> None:
        self._stall_angle = stall_angle

    def calculate_forces(
        self,
        vehicle: "EntryVehicle",
        conditions: "FlightConditions",
    ) -> AerodynamicForces:
        """Compute Modified Newtonian force coefficients.

        --- PHYSICS SEAM ---
        Returns zero coefficients. The real implementation:

        1. Compute the stagnation pressure coefficient behind a normal shock::

               Cp_max = (2/(γ·M²)) · ( ((γ+1)²·M² / (4·γ·M² − 2·(γ−1)))^(γ/(γ−1))
                                       · ((1 − γ + 2·γ·M²)/(γ+1)) − 1 )

           (and the incompressible limit ``Cp_max → 2`` as M → ∞).
        2. Integrate ``Cp = Cp_max · sin²θ`` over the vehicle's wetted geometry at the
           current angle of attack ``α`` to obtain axial (C_A) and normal (C_N) coefficients.
        3. Rotate into the wind axes:
           ``C_D = C_A·cos α + C_N·sin α``, ``C_L = C_N·cos α − C_A·sin α``.
        4. Add a Sutton–Graves stagnation-point heat-rate channel using ``vehicle.nose_radius``.

        Inputs available at the seam: ``conditions.mach``, ``conditions.angle_of_attack``,
        ``conditions.atmosphere.specific_heat_ratio``, ``vehicle.reference_area.get()``,
        ``vehicle.nose_radius.get()``.
        """
        # SEAM: a real Cp_max/geometry integration replaces the zeros below. The vehicle and
        # conditions are accepted now so the call site and data flow are already correct.
        _ = (vehicle, conditions)
        return AerodynamicForces(
            drag_coefficient=0.0,
            lift_coefficient=0.0,
            side_coefficient=0.0,
            pitching_moment_coefficient=0.0,
            provenance=self.provenance,
        )

    def get_stall_angle(self) -> float:
        return self._stall_angle

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.NOT_VALIDATED,
            source="Modified Newtonian theory (Anderson, Hypersonic and High-Temperature Gas Dynamics)",
            notes="Placeholder: returns zero coefficients (PHYSICS SEAM).",
        )
