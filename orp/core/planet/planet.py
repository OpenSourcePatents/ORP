# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The :class:`Planet` bundle and the :class:`WorldCoordinate` value object.

A planet ties together the two pluggable environment strategies (atmosphere, gravity) with
the geometric and rotational constants the equations of motion need (mean radius, rotation
rate, gravitational parameter). The simulator never special-cases Earth vs. Mars; it asks
the injected ``Planet`` for everything.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.gravity.model import GravityModel
from orp.core.provenance.tags import ProvenanceTag, weakest

__all__ = ["Planet", "WorldCoordinate"]


@dataclass(frozen=True)
class WorldCoordinate:
    """A geodetic position: latitude, longitude (both radians), and altitude (meters).

    Angles are stored in radians (the unit the EOM operate in); degree accessors are
    provided for I/O and human-facing reports.

    Attributes:
        latitude_rad: Geodetic latitude, radians, north-positive in ``[-π/2, π/2]``.
        longitude_rad: Longitude, radians, east-positive.
        altitude: Geometric altitude above the planet's mean reference surface, meters.
    """

    latitude_rad: float = 0.0
    longitude_rad: float = 0.0
    altitude: float = 0.0

    @property
    def latitude_deg(self) -> float:
        """Latitude in degrees."""
        return math.degrees(self.latitude_rad)

    @property
    def longitude_deg(self) -> float:
        """Longitude in degrees."""
        return math.degrees(self.longitude_rad)

    @classmethod
    def from_degrees(
        cls,
        latitude_deg: float,
        longitude_deg: float,
        altitude: float = 0.0,
    ) -> "WorldCoordinate":
        """Construct from degrees (convenience for human-entered launch/entry sites)."""
        return cls(
            latitude_rad=math.radians(latitude_deg),
            longitude_rad=math.radians(longitude_deg),
            altitude=altitude,
        )


@dataclass(frozen=True)
class Planet:
    """A reentry environment: atmosphere + gravity + shape + rotation.

    Attributes:
        name: Human-readable body name (``"Earth"``, ``"Mars"``).
        atmosphere: The injected :class:`~orp.core.atmosphere.model.AtmosphericModel`.
        gravity: The injected :class:`~orp.core.gravity.model.GravityModel`.
        mean_radius: Mean (volumetric) radius, meters — the EOM's reference sphere radius.
        rotation_rate: Sidereal rotation rate ω, rad/s (drives Coriolis/centrifugal terms).
        gravitational_parameter: Standard gravitational parameter μ = G·M, m³/s²
            (for orbital/entry-interface bookkeeping).
        surface_pressure: Reference surface pressure, Pa (informational).
        sutton_graves_constant: Sutton-Graves stagnation-point convective-heating constant
            ``k`` for this planet's gas, such that ``q̇ = k·√(ρ/R_n)·V³`` (W/m²). Earth air
            ≈ 1.7415e-4; Mars CO₂ ≈ 1.9027e-4.
    """

    name: str
    atmosphere: AtmosphericModel
    gravity: GravityModel
    mean_radius: float
    rotation_rate: float
    gravitational_parameter: float
    surface_pressure: float = 0.0
    sutton_graves_constant: float = 1.7415e-4

    def radius_at(self, altitude: float) -> float:
        """Return the geocentric/areocentric radius (m) for a given altitude above surface."""
        return self.mean_radius + altitude

    def altitude_of(self, radius: float) -> float:
        """Return the altitude above mean surface (m) for a given radius."""
        return radius - self.mean_radius

    def conditions_at(self, altitude_msl: float) -> AtmosphericConditions:
        """Convenience: atmospheric conditions at an altitude (delegates to the model)."""
        return self.atmosphere.get_conditions(altitude_msl)

    def gravity_at(self, position: WorldCoordinate) -> float:
        """Convenience: gravity magnitude at a world position (delegates to the model)."""
        return self.gravity.get_gravity(position)

    @property
    def provenance(self) -> ProvenanceTag:
        """Combined provenance of this planet's environment models (weakest link)."""
        return weakest([self.atmosphere.provenance, self.gravity.provenance])
