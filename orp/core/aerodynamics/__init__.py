# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aerodynamics — momentary flight conditions in, force coefficients out.

Mirrors OpenRocket's aerodynamics split: a mutable
:class:`~orp.core.aerodynamics.flight_conditions.FlightConditions` carries the instantaneous
state (Mach, angle of attack, dynamic pressure, atmosphere), and an
:class:`~orp.core.aerodynamics.calculator.AerodynamicCalculator` (Strategy) turns it into
an :class:`~orp.core.aerodynamics.calculator.AerodynamicForces` coefficient bundle.
:class:`~orp.core.aerodynamics.newtonian.ModifiedNewtonianCalculator` is the reentry-default
implementation.
"""

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.aerodynamics.flight_conditions import FlightConditions
from orp.core.aerodynamics.newtonian import ModifiedNewtonianCalculator

__all__ = [
    "FlightConditions",
    "AerodynamicCalculator",
    "AerodynamicForces",
    "ModifiedNewtonianCalculator",
]
