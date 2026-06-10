# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ready-made planets: :data:`EARTH` and :data:`MARS`.

These bundle the concrete atmosphere and gravity models with each body's geometric and
rotational constants. The constants are real, sourced values; the *models* they bundle are
currently placeholder seams (see each model's ``provenance``).
"""

from __future__ import annotations

from orp.core.atmosphere.earth import EarthISAModel
from orp.core.atmosphere.mars import MarsAtmosphereModel
from orp.core.gravity.earth import EarthWGS84GravityModel
from orp.core.gravity.mars import MarsGravityModel
from orp.core.planet.planet import Planet

__all__ = ["EARTH", "MARS", "PLANETS", "by_name"]

#: Earth. Mean radius and rotation per IAU/WGS84; μ per WGS84.
EARTH: Planet = Planet(
    name="Earth",
    atmosphere=EarthISAModel(),
    gravity=EarthWGS84GravityModel(),
    mean_radius=6_371_000.0,
    rotation_rate=7.292_115e-5,
    gravitational_parameter=3.986_004_418e14,
    surface_pressure=101_325.0,
    sutton_graves_constant=1.7415e-4,  # Earth air
)

#: Mars. Mean radius and rotation per IAU; μ per Mars gravity field.
MARS: Planet = Planet(
    name="Mars",
    atmosphere=MarsAtmosphereModel(),
    gravity=MarsGravityModel(),
    mean_radius=3_389_500.0,
    rotation_rate=7.088_218e-5,
    gravitational_parameter=4.282_837e13,
    surface_pressure=636.0,
    sutton_graves_constant=1.9027e-4,  # Mars CO₂
)

#: Registry keyed by lowercase name.
PLANETS: dict[str, Planet] = {
    EARTH.name.lower(): EARTH,
    MARS.name.lower(): MARS,
}


def by_name(name: str) -> Planet:
    """Look up a built-in planet by (case-insensitive) name.

    Args:
        name: ``"Earth"`` or ``"Mars"`` (any case).

    Returns:
        The corresponding :class:`~orp.core.planet.planet.Planet`.

    Raises:
        KeyError: if no built-in planet matches ``name``.
    """
    key = name.strip().lower()
    if key not in PLANETS:
        valid = ", ".join(sorted(PLANETS)) or "(none)"
        raise KeyError(f"Unknown planet {name!r}; known planets: {valid}")
    return PLANETS[key]
