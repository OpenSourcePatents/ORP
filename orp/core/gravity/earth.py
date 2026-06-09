# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Earth gravity — WGS84 normal-gravity model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orp.core.gravity.model import GravityModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.planet.planet import WorldCoordinate

__all__ = ["EarthWGS84GravityModel"]


class EarthWGS84GravityModel(GravityModel):
    """WGS84 ellipsoidal normal gravity with altitude correction.

    Standard surface gravity ``g₀ = 9.80665`` m/s² is a real parameter; the latitude
    (Somigliana) and altitude variation is the physics seam.
    """

    STANDARD_GRAVITY: float = 9.80665
    MEAN_RADIUS: float = 6_371_000.0

    def get_gravity(self, position: WorldCoordinate) -> float:
        """Return Earth gravity magnitude (m/s²) at ``position``.

        --- PHYSICS SEAM ---
        Returns the constant standard gravity ``g₀`` (i.e. ignores latitude and altitude).
        The real model is Somigliana normal gravity plus an inverse-square altitude term::

            sin2 = sin(lat)**2
            g0   = 9.7803267714 * (1 + 0.00193185138639*sin2)
                                / sqrt(1 - 0.00669437999013*sin2)
            g    = g0 * (R_e / (R_e + altitude))**2     # R_e = 6_371_000 m

        Drop that in here using ``position.latitude_rad`` and ``position.altitude``.
        """
        # SEAM: constant gravity; ignore position.
        return self.STANDARD_GRAVITY

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.NOT_VALIDATED,
            source="WGS84 / Somigliana normal gravity (target reference)",
            notes="Placeholder: constant standard gravity; lat/alt variation is a seam.",
        )
