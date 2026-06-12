# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared run-output rendering: the trajectory CSV and the provenance report.

One source of truth for every consumer (CLI, GUI): the same channel export and the
same provenance wording, so two front ends can never drift apart in what they tell
the user about the same run. Pure output of an already-integrated trajectory —
nothing here touches controls or the forward-only wall.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from orp.core.simulation import flight_data as fd

if TYPE_CHECKING:  # pragma: no cover - typing only
    from orp.core.simulation.conditions import SimulationConditions
    from orp.core.simulation.engine import SimulationEngine
    from orp.core.simulation.flight_data import FlightData

__all__ = ["write_trajectory_csv", "render_provenance_report"]


def write_trajectory_csv(result: "FlightData", path: Path | str) -> None:
    """Write every FlightData channel; one header row with each channel's unit."""
    branch = result.get_branch(0)
    columns = [(dtype, branch.get(dtype)) for dtype in fd.ALL_TYPES]
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([str(dtype) for dtype, _ in columns])  # e.g. "Altitude (m)"
        for i in range(branch.length):
            # repr() is the shortest round-trip representation: deterministic and exact.
            writer.writerow([repr(series[i]) for _, series in columns])


def render_provenance_report(
    *,
    result: "FlightData",
    conditions: "SimulationConditions",
    engine: "SimulationEngine",
    vehicle_name: str,
) -> str:
    """The run's provenance report: weakest link first, then every component."""
    lines: list[str] = []
    # First line: the run's weakest-link level exactly as the engine reported it on
    # the trajectory (conditions weakest-link folded with the stepper's EOM tag).
    lines.append(f"Run weakest-link provenance: {result.provenance.level.name}")
    lines.append(
        "(weakest link across vehicle, planet environment models, aerodynamics, "
        "bank schedule, and equations of motion, as reported on the trajectory)"
    )
    lines.append("")

    vehicle = conditions.vehicle
    lines.append(f"[vehicle: {vehicle_name} ({vehicle.name})]")
    lines.append(f"  overall (weakest link): {vehicle.provenance}")
    tagged = vehicle.tagged_values()
    for prop, tv in sorted(tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0])):
        lines.append(f"  {prop}: {tv.provenance}")
        if tv.provenance.notes:
            lines.append(f"      notes: {tv.provenance.notes}")
    lines.append("")

    planet = conditions.planet
    lines.append(f"[planet: {planet.name}]")
    lines.append(f"  environment (weakest link): {planet.provenance}")
    lines.append(f"  atmosphere: {planet.atmosphere.provenance}")
    if planet.atmosphere.provenance.notes:
        lines.append(f"      notes: {planet.atmosphere.provenance.notes}")
    lines.append(f"  gravity: {planet.gravity.provenance}")
    if planet.gravity.provenance.notes:
        lines.append(f"      notes: {planet.gravity.provenance.notes}")
    lines.append("")

    aero = conditions.aerodynamic_calculator
    lines.append("[aerodynamics]")
    lines.append(f"  {type(aero).__name__}: {aero.provenance}")
    if aero.provenance.notes:
        lines.append(f"      notes: {aero.provenance.notes}")
    lines.append("")

    stepper = engine.stepper
    lines.append("[equations of motion]")
    lines.append(f"  {type(stepper).__name__}: {stepper.provenance}")
    if stepper.provenance.notes:
        lines.append(f"      notes: {stepper.provenance.notes}")
    lines.append("")

    schedule = conditions.bank_schedule
    lines.append("[bank schedule]")
    lines.append(f"  {schedule.provenance}")
    if schedule.provenance.notes:
        lines.append(f"      notes: {schedule.provenance.notes}")
    lines.append("")

    return "\n".join(lines)
