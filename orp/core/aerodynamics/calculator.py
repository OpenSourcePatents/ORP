# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The aerodynamic-calculator interface and its force-coefficient output structure.

Mirrors OpenRocket's ``AerodynamicCalculator`` / ``AerodynamicForces`` contract, reduced to
the coefficients that matter for a (largely axisymmetric) reentry body: axial drag, normal
lift, side force, and pitching moment. The calculator is a Strategy injected into
:class:`~orp.core.simulation.conditions.SimulationConditions`; the engine never constructs
forces itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.aerodynamics.flight_conditions import FlightConditions
    from orp.core.vehicles.base import EntryVehicle

__all__ = ["AerodynamicForces", "AerodynamicCalculator"]


@dataclass
class AerodynamicForces:
    """Non-dimensional aerodynamic coefficients for one instant of flight.

    All coefficients are referenced to the vehicle's reference area (and reference length
    for the moment). Convert to dimensional forces with :meth:`drag_force` / :meth:`lift_force`
    given the local dynamic pressure and reference area.

    Attributes:
        drag_coefficient: C_D, parallel to the air-relative velocity.
        lift_coefficient: C_L, perpendicular to velocity in the pitch plane.
        side_coefficient: C_Y, perpendicular to velocity in the yaw plane.
        pitching_moment_coefficient: C_m about the reference point (CG).
        provenance: How these coefficients were validated/produced.
    """

    drag_coefficient: float = 0.0
    lift_coefficient: float = 0.0
    side_coefficient: float = 0.0
    pitching_moment_coefficient: float = 0.0
    provenance: ProvenanceTag = field(
        default_factory=lambda: ProvenanceTag(ValidationLevel.NOT_VALIDATED)
    )

    @property
    def lift_to_drag(self) -> float:
        """Lift-to-drag ratio L/D = C_L / C_D. Zero if drag is zero."""
        if self.drag_coefficient == 0.0:
            return 0.0
        return self.lift_coefficient / self.drag_coefficient

    def drag_force(self, dynamic_pressure: float, reference_area: float) -> float:
        """Dimensional drag force D = C_D·q·S, newtons."""
        return self.drag_coefficient * dynamic_pressure * reference_area

    def lift_force(self, dynamic_pressure: float, reference_area: float) -> float:
        """Dimensional lift force L = C_L·q·S, newtons."""
        return self.lift_coefficient * dynamic_pressure * reference_area

    def zero(self) -> "AerodynamicForces":
        """Set all coefficients to zero (keeping provenance). Returns self."""
        self.drag_coefficient = 0.0
        self.lift_coefficient = 0.0
        self.side_coefficient = 0.0
        self.pitching_moment_coefficient = 0.0
        return self


class AerodynamicCalculator(ABC):
    """Interface: (vehicle, flight conditions) → :class:`AerodynamicForces`.

    Implementations may compute coefficients analytically (Modified Newtonian) or by
    interpolating a CFD/wind-tunnel table; the rest of the simulator depends only on this
    contract, exactly as OpenRocket's Barrowman/lookup calculators sit behind one interface.
    """

    @abstractmethod
    def calculate_forces(
        self,
        vehicle: "EntryVehicle",
        conditions: "FlightConditions",
    ) -> AerodynamicForces:
        """Compute the aerodynamic force coefficients on ``vehicle`` at ``conditions``.

        Args:
            vehicle: The reentry vehicle supplying geometry (reference area, nose radius).
            conditions: The momentary Mach / angle-of-attack / atmosphere state.

        Returns:
            An :class:`AerodynamicForces` coefficient bundle tagged with this calculator's
            provenance.
        """

    @abstractmethod
    def get_stall_angle(self) -> float:
        """Return the angle of attack (radians) beyond which the model is invalid."""

    @property
    @abstractmethod
    def provenance(self) -> ProvenanceTag:
        """Validation level and citation for this aerodynamic model."""
