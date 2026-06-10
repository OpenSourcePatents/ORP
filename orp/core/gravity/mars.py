# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mars gravity — central (GM/r²) field with an inverse-square altitude correction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orp.core.gravity.model import GravityModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.planet.planet import WorldCoordinate

__all__ = ["MarsGravityModel"]

# Mars gravitational parameter from spacecraft tracking (GMM-3 / JPL), and mean radius.
_GM = 4.282837e13  # m³/s²
_MEAN_RADIUS = 3_389_500.0  # m


class MarsGravityModel(GravityModel):
    """Central-field Mars gravity ``g = GM/(R+h)²``.

    Uses the spacecraft-tracked gravitational parameter GM; latitude variation (J2 oblateness)
    is neglected — a small effect that is the refinement seam for higher fidelity.
    """

    GRAVITATIONAL_PARAMETER: float = _GM
    MEAN_RADIUS: float = _MEAN_RADIUS

    def get_gravity(self, position: "WorldCoordinate") -> float:
        """Return Mars gravity magnitude (m/s²): ``GM/(R_mean + altitude)²``.

        At the surface this gives GM/R² = 4.282837e13 / 3 389 500² ≈ 3.728 m/s²
        (≈ the commonly cited 3.72 m/s²).
        """
        radius = _MEAN_RADIUS + position.altitude
        return _GM / (radius * radius)

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.VERIFIED_FLIGHT,
            source="Mars gravitational parameter GM from spacecraft tracking (GMM-3 / JPL)",
            notes=(
                "Central-field GM/r² with inverse-square altitude variation; "
                "latitude/J2 oblateness neglected (refinement seam)."
            ),
        )
