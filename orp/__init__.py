# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ORP — Open Reentry Platform.

A forward-only atmospheric reentry simulator with first-class data provenance and a
multi-planet (Earth / Mars) vehicle + environment abstraction.

The public entry points live under :mod:`orp.core`. See :mod:`orp.core` for the two
architectural invariants this package enforces everywhere (forward-only simulation and
provenance-on-everything) and the placeholder-physics convention.
"""

__version__ = "0.0.1"
__author__ = "Charles W. Dowd Jr."
__license__ = "GPL-3.0-or-later"

__all__ = ["__version__", "__author__", "__license__"]
