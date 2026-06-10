# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The forward-only simulation engine — ORP's orchestrator.

Mirrors OpenRocket's ``BasicEventSimulationEngine`` in role: it owns the main loop, decides
when to take a step and when to stop, and delegates the physics to a
:class:`~orp.core.simulation.stepper.SimulationStepper`. It does no physics itself.

FORWARD-ONLY WALL
=================
:meth:`SimulationEngine.simulate` takes a fully specified
:class:`~orp.core.simulation.conditions.SimulationConditions` — entry state plus a *replayed*
bank-angle schedule — and integrates the equations of motion **forward** until the vehicle
reaches the ground (or the time cap). It returns a :class:`~orp.core.simulation.flight_data.FlightData`
trajectory.

It does the opposite of a guidance/targeting solver. There is no parameter, overload, or
sibling method anywhere in this engine that accepts a desired landing point (or any terminal
condition) and returns a bank schedule, control law, or correction. That inverse problem is
permanently out of scope for ORP. Replaying control histories forward is the only thing this
engine — and this codebase — does.
"""

from __future__ import annotations

from orp.core.provenance.tags import weakest
from orp.core.simulation.conditions import SimulationConditions
from orp.core.simulation.flight_data import (
    ALL_TYPES,
    FlightData,
    FlightDataBranch,
)
from orp.core.simulation.status import SimulationStatus
from orp.core.simulation.stepper import RK4Stepper, SimulationStepper

__all__ = ["SimulationEngine"]

# Event/termination reason labels recorded on the branch.
_EVENT_ENTRY_INTERFACE = "ENTRY_INTERFACE"
_EVENT_GROUND_HIT = "GROUND_HIT"
_EVENT_SIMULATION_END = "SIMULATION_END"
_EVENT_STOPPED = "STOPPED"


class SimulationEngine:
    """Forward integrator of a reentry trajectory.

    Args:
        stepper: The physics integrator strategy. Defaults to
            :class:`~orp.core.simulation.stepper.RK4Stepper`.
    """

    def __init__(self, stepper: SimulationStepper | None = None) -> None:
        self.stepper: SimulationStepper = stepper if stepper is not None else RK4Stepper()

    def simulate(self, conditions: SimulationConditions) -> FlightData:
        """Integrate the reentry forward from ``conditions`` and return the trajectory.

        The bank angle is *replayed* from ``conditions.bank_schedule`` at each step; the
        integration proceeds until the vehicle reaches ``conditions.ground_altitude``, its
        speed drops below ``conditions.minimum_velocity``, or ``conditions.max_simulation_time``
        is reached — whichever comes first.

        Args:
            conditions: The immutable setup (entry state, models, replayed bank schedule).

        Returns:
            A :class:`~orp.core.simulation.flight_data.FlightData` whose provenance is the
            weakest of the contributing inputs (see
            :meth:`~orp.core.simulation.conditions.SimulationConditions.provenance`).
        """
        # The equations of motion are themselves a provenanced model: the run can be no
        # better validated than the EOM that produced it (weakest link, like every input).
        run_provenance = weakest([conditions.provenance, self.stepper.provenance])

        branch = FlightDataBranch("Reentry", types=ALL_TYPES)
        branch.provenance = run_provenance

        flight_data = FlightData(branch)
        flight_data.provenance = run_provenance

        status = conditions.create_initial_status()
        status.flight_data_branch = branch
        status = self.stepper.initialize(status)

        branch.add_event(_EVENT_ENTRY_INTERFACE, status.time)

        # Safety bound on iterations in case a (future) stepper fails to advance time.
        max_iterations = int(conditions.max_simulation_time / max(conditions.time_step, 1e-9)) + 16

        for _ in range(max_iterations):
            # Refresh the replayed control for this instant, then record the full data row.
            status.bank_angle = conditions.bank_schedule.bank_angle_at(status.time)
            self.stepper.record_point(status)

            terminate, reason = self._should_terminate(status, conditions)
            if terminate:
                if reason == _EVENT_GROUND_HIT:
                    status.landed = True
                branch.add_event(reason, status.time)
                break

            remaining = conditions.max_simulation_time - status.time
            step = min(conditions.time_step, remaining)
            if step <= 0.0:
                branch.add_event(_EVENT_SIMULATION_END, status.time)
                break

            self.stepper.step(status, step)
        else:
            # Loop exhausted its safety bound without an explicit terminator.
            branch.add_event(_EVENT_SIMULATION_END, status.time)

        flight_data.calculate_interesting_values()
        flight_data.immute()
        return flight_data

    @staticmethod
    def _should_terminate(
        status: SimulationStatus,
        conditions: SimulationConditions,
    ) -> tuple[bool, str]:
        """Decide whether the run should stop at the current instant, with a reason label."""
        if status.altitude <= conditions.ground_altitude:
            return True, _EVENT_GROUND_HIT
        if status.time >= conditions.max_simulation_time:
            return True, _EVENT_SIMULATION_END
        if status.time > 0.0 and status.velocity < conditions.minimum_velocity:
            return True, _EVENT_STOPPED
        return False, ""
