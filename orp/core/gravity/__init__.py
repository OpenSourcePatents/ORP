# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gravity models — downward acceleration magnitude as a function of world position.

Strategy pattern: :class:`~orp.core.gravity.model.GravityModel` returns a scalar gravity
magnitude (m/s²) for a :class:`~orp.core.planet.planet.WorldCoordinate`; concrete models
(:class:`~orp.core.gravity.earth.EarthWGS84GravityModel`,
:class:`~orp.core.gravity.mars.MarsGravityModel`) plug into a
:class:`~orp.core.planet.planet.Planet`.
"""

from orp.core.gravity.earth import EarthWGS84GravityModel
from orp.core.gravity.mars import MarsGravityModel
from orp.core.gravity.model import GravityModel

__all__ = [
    "GravityModel",
    "EarthWGS84GravityModel",
    "MarsGravityModel",
]
