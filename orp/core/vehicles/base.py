# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The :class:`EntryVehicle` base class — a reentry body described with full provenance.

Every physical property is a :class:`~orp.core.provenance.tags.TaggedValue`, so a value can
never be consumed without its validation level and source citation travelling with it. This
is the vehicle-side of the "provenance on everything" principle; the simulation-output side
lives in :mod:`orp.core.simulation.flight_data`.

An ``EntryVehicle`` is planet-agnostic: it describes the body, while the
:class:`~orp.core.planet.planet.Planet` it reenters is chosen in
:class:`~orp.core.simulation.conditions.SimulationConditions`. ``intended_planet`` is only
metadata recording what the definition was authored for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orp.core.provenance.tags import ProvenanceTag, TaggedValue, ValidationLevel, weakest

__all__ = ["EntryVehicle"]


@dataclass(frozen=True)
class EntryVehicle:
    """A reentry vehicle: provenance-tagged mass, geometry, and aerodynamic descriptors.

    Aerodynamic coefficients here are *nominal/reference* values (e.g. flight-reconstructed
    hypersonic C_D and L/D). Whether the simulation uses them directly or recomputes
    coefficients is the job of the injected
    :class:`~orp.core.aerodynamics.calculator.AerodynamicCalculator`; either way the vehicle
    carries them with provenance for reporting and for the ballistic-coefficient derivation.

    Attributes:
        name: Vehicle name.
        mass: Entry mass, kg.
        reference_area: Aerodynamic reference area S, m².
        nose_radius: Effective nose radius, m (stagnation-point heating & Newtonian Cp).
        drag_coefficient: Nominal hypersonic drag coefficient C_D (dimensionless).
        lift_to_drag: Nominal lift-to-drag ratio L/D (dimensionless; 0 ⇒ ballistic).
        trim_angle_of_attack: Trim angle of attack, radians.
        half_cone_angle: Forebody sphere-cone half-angle (radians, measured from the axis),
            used by the Modified Newtonian aerodynamics. For a near-spherical capsule (nose
            radius ≥ base radius) the value only needs to keep the body a spherical segment.
        intended_planet: Metadata — the planet this definition was authored for.
        description: Free-text description / notes.
    """

    name: str
    mass: TaggedValue[float]
    reference_area: TaggedValue[float]
    nose_radius: TaggedValue[float]
    drag_coefficient: TaggedValue[float]
    lift_to_drag: TaggedValue[float]
    trim_angle_of_attack: TaggedValue[float]
    half_cone_angle: TaggedValue[float] = field(
        default_factory=lambda: TaggedValue(
            value=0.0,
            provenance=ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="Not specified."),
        )
    )
    intended_planet: str = "earth"
    description: str = ""

    def tagged_values(self) -> dict[str, TaggedValue]:
        """Return every provenance-tagged property keyed by name.

        Used both for reporting and by the engine to fold the vehicle's provenance into a
        trajectory's overall validation level.
        """
        return {
            "mass": self.mass,
            "reference_area": self.reference_area,
            "nose_radius": self.nose_radius,
            "drag_coefficient": self.drag_coefficient,
            "lift_to_drag": self.lift_to_drag,
            "trim_angle_of_attack": self.trim_angle_of_attack,
            "half_cone_angle": self.half_cone_angle,
        }

    @property
    def provenance(self) -> ProvenanceTag:
        """Combined provenance across all properties (the weakest-link tag)."""
        return weakest(list(self.tagged_values().values()))

    def ballistic_coefficient(self) -> float:
        """Ballistic coefficient β = m / (C_D·S), kg/m². Zero if C_D·S is zero.

        β governs how deep into the atmosphere a body penetrates before decelerating; it is
        the single most important scalar in atmospheric entry, which is why it is derived
        here from provenanced inputs rather than stored loose.
        """
        cd = self.drag_coefficient.get()
        s = self.reference_area.get()
        denom = cd * s
        if denom == 0.0:
            return 0.0
        return self.mass.get() / denom

    def validate(self) -> None:
        """Check basic physical sanity of the vehicle definition.

        Raises:
            ValueError: if mass, reference area, or nose radius is non-positive.
        """
        if self.mass.get() <= 0.0:
            raise ValueError(f"{self.name}: mass must be positive (got {self.mass.get()}).")
        if self.reference_area.get() <= 0.0:
            raise ValueError(
                f"{self.name}: reference_area must be positive (got {self.reference_area.get()})."
            )
        if self.nose_radius.get() <= 0.0:
            raise ValueError(
                f"{self.name}: nose_radius must be positive (got {self.nose_radius.get()})."
            )
