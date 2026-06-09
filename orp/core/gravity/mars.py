# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mars gravity model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orp.core.gravity.model import GravityModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.planet.planet import WorldCoordinate

__all__ = ["MarsGravityModel"]


class MarsGravityModel(GravityModel):
    """Mars normal gravity with altitude correction.

    Mean surface gravity ``g₀ = 3.72076`` m/s² is a real parameter; latitude and altitude
    variation is the physics seam.
    """

    SURFACE_GRAVITY: float = 3.72076
    MEAN_RADIUS: float = 3_389_500.0

    def get_gravity(self, position: WorldCoordinate) -> float:
        """Return Mars gravity magnitude (m/s²) at ``position``.

        --- PHYSICS SEAM ---
        Returns the constant mean surface gravity (ignores latitude and altitude). The
        real model applies an inverse-square altitude correction
        ``g = g₀·(R_m/(R_m+altitude))²`` (``R_m = 3_389_500 m``) and, for higher fidelity, a
        latitude term from the Mars gravity field (e.g. the GMM-3 ``J₂`` harmonic).
        """
        # SEAM: constant gravity; ignore position.
        return self.SURFACE_GRAVITY

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.NOT_VALIDATED,
            source="Mars GMM-3 gravity field (target reference)",
            notes="Placeholder: constant surface gravity; lat/alt variation is a seam.",
        )
