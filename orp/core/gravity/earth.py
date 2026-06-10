# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Earth gravity — WGS84 Somigliana normal gravity with an altitude correction."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from orp.core.gravity.model import GravityModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.planet.planet import WorldCoordinate

__all__ = ["EarthWGS84GravityModel"]

# WGS84 normal-gravity (Somigliana) constants.
_GAMMA_EQUATOR = 9.7803253359  # m/s², normal gravity at the equator
_SOMIGLIANA_K = 0.00193185265241  # gravity formula constant
_E2 = 0.00669437999014  # first eccentricity squared of the WGS84 ellipsoid
_MEAN_RADIUS = 6_371_000.0  # m, used for the inverse-square altitude term


class EarthWGS84GravityModel(GravityModel):
    """WGS84 ellipsoidal normal gravity vs. latitude, with an inverse-square altitude term.

    Surface gravity follows the Somigliana closed form (exact on the WGS84 ellipsoid); the
    altitude variation uses the inverse-square (free-air) approximation about the mean radius.
    """

    EQUATOR_GRAVITY: float = _GAMMA_EQUATOR
    MEAN_RADIUS: float = _MEAN_RADIUS

    def get_gravity(self, position: "WorldCoordinate") -> float:
        """Return Earth gravity magnitude (m/s²) at ``position``.

        Somigliana surface gravity::

            sin2 = sin(latitude)²
            g₀(φ) = γ_e · (1 + k·sin2) / sqrt(1 − e²·sin2)

        with γ_e = 9.7803253359, k = 0.00193185265241, e² = 0.00669437999014. The altitude
        correction is the inverse-square free-air term ``g = g₀·(R/(R+h))²`` with
        R = 6 371 000 m.
        """
        sin2 = math.sin(position.latitude_rad) ** 2
        g0 = _GAMMA_EQUATOR * (1.0 + _SOMIGLIANA_K * sin2) / math.sqrt(1.0 - _E2 * sin2)
        altitude = position.altitude
        return g0 * (_MEAN_RADIUS / (_MEAN_RADIUS + altitude)) ** 2

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.VERIFIED_FLIGHT,
            source="WGS84 (NIMA TR8350.2); Somigliana normal gravity formula",
            notes=(
                "Somigliana ellipsoidal surface gravity (exact on WGS84) with an inverse-square "
                "free-air altitude term about the mean radius; J2/higher harmonics neglected."
            ),
        )
