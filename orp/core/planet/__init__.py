# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Planet abstraction — atmosphere + gravity + shape + rotation, bundled per body.

A :class:`~orp.core.planet.planet.Planet` is the environment a vehicle reenters into.
:mod:`~orp.core.planet.registry` provides the ready-made :data:`EARTH` and :data:`MARS`
instances. Multi-planet support is a day-one invariant of ORP, not a later extension.
"""

from orp.core.planet.planet import Planet, WorldCoordinate
from orp.core.planet.registry import EARTH, MARS, by_name

__all__ = [
    "Planet",
    "WorldCoordinate",
    "EARTH",
    "MARS",
    "by_name",
]
