# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The gravity-model interface.

Mirrors OpenRocket's ``GravityModel``: a single method returning the *scalar* gravity
magnitude, which the equations of motion apply along the local downward (−radial)
direction. The full vector field (J2 oblateness, etc.) is out of scope; reentry to first
order treats gravity as central.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from orp.core.provenance.tags import ProvenanceTag

if TYPE_CHECKING:  # avoid a runtime import cycle (planet imports gravity)
    from orp.core.planet.planet import WorldCoordinate

__all__ = ["GravityModel"]


class GravityModel(ABC):
    """Interface for a gravity model: world position → scalar gravity magnitude (m/s²)."""

    @abstractmethod
    def get_gravity(self, position: WorldCoordinate) -> float:
        """Return the local gravitational acceleration magnitude at ``position``.

        Args:
            position: A :class:`~orp.core.planet.planet.WorldCoordinate`
                (latitude, longitude, altitude).

        Returns:
            Gravity magnitude in m/s², applied by the EOM along the downward radial.
        """

    @property
    @abstractmethod
    def provenance(self) -> ProvenanceTag:
        """Validation level and citation for this gravity model."""
