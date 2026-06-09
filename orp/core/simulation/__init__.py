# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The simulation core: engine, stepper, status, conditions, and flight-data output.

Architecture mirrors OpenRocket's flight-simulation subsystem (patterns only):

* :class:`~orp.core.simulation.engine.SimulationEngine` — the forward-only orchestrator.
* :class:`~orp.core.simulation.stepper.SimulationStepper` + ``RK4Stepper`` — the physics
  integrator (Strategy pattern).
* :class:`~orp.core.simulation.status.SimulationStatus` — mutable per-instant state.
* :class:`~orp.core.simulation.conditions.SimulationConditions` — immutable setup and the
  dependency-injection container for the pluggable physics models.
* :class:`~orp.core.simulation.flight_data.FlightData` / ``FlightDataBranch`` — the
  trajectory output column-store.
"""

from orp.core.simulation.conditions import SimulationConditions
from orp.core.simulation.engine import SimulationEngine
from orp.core.simulation.flight_data import (
    FlightData,
    FlightDataBranch,
    FlightDataType,
)
from orp.core.simulation.status import SimulationStatus
from orp.core.simulation.stepper import RK4Stepper, SimulationStepper

__all__ = [
    "SimulationEngine",
    "SimulationStepper",
    "RK4Stepper",
    "SimulationStatus",
    "SimulationConditions",
    "FlightData",
    "FlightDataBranch",
    "FlightDataType",
]
