# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reentry vehicles — provenance-tagged geometry, mass, and aerodynamic descriptors.

:class:`~orp.core.vehicles.base.EntryVehicle` holds every physical property as a
:class:`~orp.core.provenance.tags.TaggedValue` (value + validation level + source citation).
:class:`~orp.core.vehicles.library.VehicleLibrary` loads vehicle definitions from YAML.
"""

from orp.core.vehicles.base import EntryVehicle
from orp.core.vehicles.library import VehicleLibrary, load_vehicle

__all__ = [
    "EntryVehicle",
    "VehicleLibrary",
    "load_vehicle",
]
