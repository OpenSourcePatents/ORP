# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Atmospheric models — the air the vehicle flies through, as a function of altitude.

Strategy pattern: :class:`~orp.core.atmosphere.model.AtmosphericModel` defines the single
query the simulator needs (density / pressure / temperature / speed of sound at an
altitude), and concrete models (:class:`~orp.core.atmosphere.earth.EarthISAModel`,
:class:`~orp.core.atmosphere.mars.MarsAtmosphereModel`) provide interchangeable
implementations bundled into a :class:`~orp.core.planet.planet.Planet`.
"""

from orp.core.atmosphere.earth import EarthISAModel
from orp.core.atmosphere.exponential import ExponentialAtmosphere
from orp.core.atmosphere.mars import MarsAtmosphereModel
from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel

__all__ = [
    "AtmosphericModel",
    "AtmosphericConditions",
    "EarthISAModel",
    "ExponentialAtmosphere",
    "MarsAtmosphereModel",
]
