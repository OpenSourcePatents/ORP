# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Constant-coefficient aerodynamics — fixed hypersonic C_D and L/D.

The standard engineering idealization for entry trajectory work: blunt-body hypersonic
coefficients are nearly Mach-independent ("Mach-number independence principle"), so a single
trimmed C_D and L/D pair characterizes the vehicle through the deceleration pulse. This is
also the model used by closed-form entry theory (Allen-Eggers, equilibrium glide) and by
many reference implementations, which makes this calculator the natural bridge fixture when
comparing ORP against an external implementation with matched inputs.

Like every model in ORP it carries provenance: constant coefficients are only as trustworthy
as wherever they came from, so the tag must be supplied by the caller (defaulting to
``NOT_VALIDATED`` when omitted — an unsourced constant is, honestly, unvalidated).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.aerodynamics.flight_conditions import FlightConditions
    from orp.core.vehicles.base import EntryVehicle

__all__ = ["ConstantCoefficientCalculator"]


class ConstantCoefficientCalculator(AerodynamicCalculator):
    """Aerodynamics with a fixed drag coefficient and lift-to-drag ratio.

    The coefficients are independent of Mach, angle of attack, and atmosphere; the lift
    coefficient is derived as ``C_L = C_D · (L/D)``. The bank angle never enters here — it
    orients the lift vector in the EOM and is replayed, never solved for.

    Args:
        drag_coefficient: The fixed C_D (dimensionless, referenced to the vehicle's
            reference area).
        lift_to_drag: The fixed trimmed L/D ratio (0 ⇒ ballistic).
        provenance: Where these coefficients came from and how validated they are.
            Defaults to ``NOT_VALIDATED`` — pass a real tag for sourced coefficients.

    Raises:
        ValueError: if ``drag_coefficient`` is not positive (a dragless entry body is
            non-physical and would break ballistic-coefficient reasoning downstream).
    """

    def __init__(
        self,
        drag_coefficient: float,
        lift_to_drag: float = 0.0,
        *,
        provenance: ProvenanceTag | None = None,
    ) -> None:
        if drag_coefficient <= 0.0:
            raise ValueError(f"drag_coefficient must be positive (got {drag_coefficient}).")
        self._drag_coefficient = float(drag_coefficient)
        self._lift_to_drag = float(lift_to_drag)
        self._provenance = (
            provenance
            if provenance is not None
            else ProvenanceTag(
                ValidationLevel.NOT_VALIDATED,
                notes="Unsourced constant coefficients.",
            )
        )

    @property
    def drag_coefficient(self) -> float:
        """The fixed C_D."""
        return self._drag_coefficient

    @property
    def lift_to_drag(self) -> float:
        """The fixed L/D ratio."""
        return self._lift_to_drag

    def calculate_forces(
        self,
        vehicle: "EntryVehicle",
        conditions: "FlightConditions",
    ) -> AerodynamicForces:
        """Return the fixed coefficients, regardless of Mach or angle of attack."""
        return AerodynamicForces(
            drag_coefficient=self._drag_coefficient,
            lift_coefficient=self._drag_coefficient * self._lift_to_drag,
            side_coefficient=0.0,
            pitching_moment_coefficient=0.0,
            provenance=self._provenance,
        )

    def get_stall_angle(self) -> float:
        """Constant coefficients impose no angle-of-attack limit."""
        return math.pi

    @property
    def provenance(self) -> ProvenanceTag:
        return self._provenance
