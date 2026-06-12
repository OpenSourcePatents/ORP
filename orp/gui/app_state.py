# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""AppState — the single owner of simulation state for the ORP GUI.

Widgets read from and write to this object; they never construct physics objects
themselves. AppState is pure Python (no Qt import anywhere in this module), so the
entire GUI data flow is testable headless, and the construction paths are exactly the
ones the CLI uses — same aero calculator, same frame conversion, same report renderer —
so the two front ends cannot produce different physics from the same inputs.

FORWARD-ONLY WALL: AppState holds an entry state, a planet, a vehicle, and a
**replayed** bank schedule. There is no field for any terminal endpoint, and no method
derives controls from anything. Schedules in, trajectories out.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.bank_schedule import BankSchedule
from orp.core.frames import inertial_to_planet_relative
from orp.core.planet import by_name
from orp.core.provenance import ProvenanceTag, ValidationLevel, weakest
from orp.core.report import render_provenance_report, write_trajectory_csv
from orp.core.session import (
    FRAME_INERTIAL,
    FRAME_PLANET_RELATIVE,
    save_session,
    source_arrays,
    source_constant,
    source_csv,
)
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary

if TYPE_CHECKING:  # pragma: no cover - typing only
    from orp.core.session import ScheduleSource
    from orp.core.simulation.flight_data import FlightData
    from orp.core.vehicles.base import EntryVehicle
    from orp.gates.summary import GatesReport

__all__ = ["AppState", "EntryStateFields", "RunRecord", "LEVEL_COLOR_HEX"]

#: ValidationLevel -> display color (hex), shared by every provenance-colored widget.
LEVEL_COLOR_HEX: dict[str, str] = {
    "VERIFIED_FLIGHT": "#2e7d32",   # green
    "VERIFIED_SOURCE": "#1565c0",   # blue
    "VERIFIED_CFD": "#00838f",      # cyan
    "ASSERTED": "#ff8f00",          # amber
    "NOT_VALIDATED": "#c62828",     # red
}


def _conditions_defaults() -> dict[str, object]:
    return {
        f.name: f.default
        for f in dataclasses.fields(SimulationConditions)
        if f.default is not dataclasses.MISSING
    }


_DEFAULTS = _conditions_defaults()


@dataclass
class EntryStateFields:
    """The user-editable entry state, in display units (deg / m / m/s)."""

    velocity: float = float(_DEFAULTS["entry_velocity"])
    fpa_deg: float = math.degrees(float(_DEFAULTS["entry_flight_path_angle"]))
    heading_deg: float = math.degrees(float(_DEFAULTS["entry_heading"]))
    altitude: float = float(_DEFAULTS["entry_altitude"])
    lat_deg: float = math.degrees(float(_DEFAULTS["entry_latitude"]))
    lon_deg: float = math.degrees(float(_DEFAULTS["entry_longitude"]))


@dataclass
class RunRecord:
    """One completed run this launch — in-memory only, nothing persisted to disk."""

    label: str
    vehicle_name: str | None
    planet_name: str
    conditions: SimulationConditions
    flight_data: "FlightData"
    provenance_report: str
    frame_conversion_note: str | None
    schedule_source: "ScheduleSource | None"
    gates_report: "GatesReport | None" = None


@dataclass
class AppState:
    """Owns SimulationConditions, FlightData, and the provenance report."""

    vehicle_name: str | None = None
    vehicle: "EntryVehicle | None" = None
    planet_name: str = "earth"
    #: The frame the entry state is expressed in. Defaults to planet-relative; a frame
    #: must be set (non-empty) before a run can arm.
    frame: str = FRAME_PLANET_RELATIVE
    entry: EntryStateFields = field(default_factory=EntryStateFields)
    time_step: float = float(_DEFAULTS["time_step"])
    max_simulation_time: float = float(_DEFAULTS["max_simulation_time"])

    schedule: BankSchedule | None = None
    schedule_source: "ScheduleSource | None" = None
    schedule_summary: str = ""

    conditions: SimulationConditions | None = None
    flight_data: "FlightData | None" = None
    provenance_report: str | None = None
    frame_conversion_note: str | None = None
    gates_report: "GatesReport | None" = None
    #: Completed runs this launch (session-scoped; never written to disk).
    run_history: list[RunRecord] = field(default_factory=list)

    # ----- inputs -----------------------------------------------------------------

    def available_vehicles(self) -> list[str]:
        return VehicleLibrary().list_available()

    def load_vehicle(self, name: str) -> "EntryVehicle":
        """Load (or reload from disk) a library vehicle into the state."""
        self.vehicle = VehicleLibrary().load(name)
        self.vehicle_name = name
        return self.vehicle

    def set_schedule_constant(self, bank_deg: float) -> None:
        """A constant commanded bank angle — hand-entered, therefore NOT_VALIDATED."""
        bank_rad = math.radians(bank_deg)
        provenance = ProvenanceTag(
            ValidationLevel.NOT_VALIDATED,
            source=f"user-supplied constant bank angle ({bank_deg:g} deg) via GUI",
            notes="Hand-entered constant bank command; unsourced.",
        )
        self.schedule = BankSchedule.constant(bank_rad, provenance=provenance)
        self.schedule_source = source_constant(bank_rad)
        self.schedule_summary = (
            f"Constant {bank_deg:g} deg - {ValidationLevel.NOT_VALIDATED.name}"
        )

    def set_schedule_csv(self, path: str | Path) -> None:
        """Import a two-column commanded-bank CSV via BankSchedule.from_csv (the only
        CSV ingestion path; refusal-over-repair semantics belong to from_csv)."""
        provenance = ProvenanceTag(
            ValidationLevel.ASSERTED,
            source=f"user-supplied CSV: {path}",
            notes="Commanded bank history imported via the GUI; replayed as-is.",
        )
        schedule = BankSchedule.from_csv(path, provenance=provenance)
        self.schedule = schedule
        self.schedule_source = source_csv(Path(path).resolve())
        reversals = self.count_reversals(schedule)
        self.schedule_summary = (
            f"CSV {Path(path).name} - {schedule.provenance.level.name}, "
            f"{len(schedule)} samples, {reversals} sign reversal(s)"
        )

    def set_schedule_piecewise(self, times: list[float], angles_deg: list[float]) -> None:
        """A hand-edited piecewise schedule — tagged ASSERTED per the editor contract."""
        provenance = ProvenanceTag(
            ValidationLevel.ASSERTED,
            source="hand-entered piecewise bank schedule via GUI editor",
            notes="Piecewise-linear commanded bank history entered point by point.",
        )
        angles_rad = [math.radians(a) for a in angles_deg]
        self.schedule = BankSchedule(times, angles_rad, provenance=provenance)
        self.schedule_source = source_arrays(times, angles_rad)
        self.schedule_summary = (
            f"Piecewise ({len(times)} points) - {ValidationLevel.ASSERTED.name}"
        )

    @staticmethod
    def count_reversals(schedule: BankSchedule) -> int:
        """Number of sign reversals in the commanded bank history."""
        angles = schedule.bank_angles
        return sum(1 for a, b in zip(angles, angles[1:]) if a * b < 0.0)

    # ----- arming / ceiling --------------------------------------------------------

    @property
    def can_run(self) -> bool:
        """Run arms only when a frame is set, a vehicle is loaded, and a schedule chosen."""
        frame_ok = self.frame in (FRAME_PLANET_RELATIVE, FRAME_INERTIAL)
        return frame_ok and self.vehicle is not None and self.schedule is not None

    def provenance_ceiling(self) -> ValidationLevel | None:
        """The best the run's weakest link can possibly be, given the current inputs."""
        if self.vehicle is None or self.schedule is None:
            return None
        planet = by_name(self.planet_name)
        aero = self._build_aero(self.vehicle)
        stepper_tag = SimulationEngine().stepper.provenance
        return weakest(
            [
                self.vehicle.provenance,
                planet.provenance,
                aero.provenance,
                self.schedule.provenance,
                stepper_tag,
            ]
        ).level

    # ----- physics construction (HERE, never in widgets) ----------------------------

    @staticmethod
    def _build_aero(vehicle: "EntryVehicle") -> ConstantCoefficientCalculator:
        """Same aero composition as the CLI: the vehicle's cited nominal coefficients."""
        return ConstantCoefficientCalculator(
            vehicle.drag_coefficient.get(),
            vehicle.lift_to_drag.get(),
            provenance=weakest([vehicle.drag_coefficient, vehicle.lift_to_drag]),
        )

    def build_conditions(self) -> SimulationConditions:
        """Construct SimulationConditions from the current inputs (frame handled here)."""
        if not self.can_run:
            raise ValueError(
                "Cannot build conditions: a vehicle, a frame, and a bank schedule "
                "must all be set first."
            )
        assert self.vehicle is not None and self.schedule is not None
        planet = by_name(self.planet_name)

        velocity = float(self.entry.velocity)
        flight_path_angle = math.radians(self.entry.fpa_deg)
        heading = math.radians(self.entry.heading_deg)
        latitude = math.radians(self.entry.lat_deg)
        longitude = math.radians(self.entry.lon_deg)
        altitude = float(self.entry.altitude)

        self.frame_conversion_note = None
        if self.frame == FRAME_INERTIAL:
            relative = inertial_to_planet_relative(
                planet,
                velocity=velocity,
                flight_path_angle=flight_path_angle,
                heading=heading,
                latitude=latitude,
                altitude=altitude,
            )
            velocity = relative.velocity
            flight_path_angle = relative.flight_path_angle
            heading = relative.heading
            self.frame_conversion_note = (
                "Converted entry state inertial -> planet-relative (eastward "
                "planet-rotation velocity subtracted): "
                f"velocity {velocity:.6f} m/s, "
                f"flight-path angle {math.degrees(flight_path_angle):.6f} deg, "
                f"heading {math.degrees(heading):.6f} deg."
            )

        self.conditions = SimulationConditions(
            vehicle=self.vehicle,
            planet=planet,
            bank_schedule=self.schedule,
            aerodynamic_calculator=self._build_aero(self.vehicle),
            entry_velocity=velocity,
            entry_flight_path_angle=flight_path_angle,
            entry_altitude=altitude,
            entry_heading=heading,
            entry_latitude=latitude,
            entry_longitude=longitude,
            time_step=float(self.time_step),
            max_simulation_time=float(self.max_simulation_time),
        )
        return self.conditions

    # ----- running -----------------------------------------------------------------

    def run_simulation(self) -> "FlightData":
        """Build conditions and run the engine; pure Python (callable off-thread)."""
        conditions = self.build_conditions()
        engine = SimulationEngine()
        result = engine.simulate(conditions)
        self.flight_data = result
        self.provenance_report = render_provenance_report(
            result=result,
            conditions=conditions,
            engine=engine,
            vehicle_name=self.vehicle_name or (self.vehicle.name if self.vehicle else "?"),
        )
        self.run_history.append(
            RunRecord(
                label=(
                    f"Run {len(self.run_history) + 1}: "
                    f"{self.vehicle_name or '?'} on {self.planet_name}"
                ),
                vehicle_name=self.vehicle_name,
                planet_name=self.planet_name,
                conditions=conditions,
                flight_data=result,
                provenance_report=self.provenance_report,
                frame_conversion_note=self.frame_conversion_note,
                schedule_source=self.schedule_source,
            )
        )
        return result

    def refresh_gates(self) -> "GatesReport":
        """Re-evaluate the gates (statuses exactly as the gates state them)."""
        from orp.gates.summary import evaluate_gates

        self.gates_report = evaluate_gates()
        if self.run_history:
            self.run_history[-1].gates_report = self.gates_report
        return self.gates_report

    def restore_run(self, index: int) -> RunRecord:
        """Restore a completed run's results into the live state (in-memory only).

        Only the RESULT side is restored (flight data, conditions, reports) so the
        results panels can re-render it; the input panels are not touched.
        """
        record = self.run_history[index]
        self.conditions = record.conditions
        self.flight_data = record.flight_data
        self.provenance_report = record.provenance_report
        self.frame_conversion_note = record.frame_conversion_note
        self.gates_report = record.gates_report
        self.vehicle_name = record.vehicle_name
        self.planet_name = record.planet_name
        self.schedule_source = record.schedule_source
        return record

    # ----- outputs -----------------------------------------------------------------

    def landing_summary(self) -> list[tuple[str, str]]:
        """Rows for the landing summary table (label, value-with-unit)."""
        if self.flight_data is None:
            return []
        branch = self.flight_data.get_branch(0)
        summary = self.flight_data.summary
        return [
            ("Peak deceleration", f"{summary.get('peak_deceleration', float('nan')):.4f} g"),
            ("Peak heat rate", f"{summary.get('peak_heat_rate', float('nan')):.6g} W/m^2"),
            (
                "Peak dynamic pressure",
                f"{summary.get('peak_dynamic_pressure', float('nan')):.6g} Pa",
            ),
            ("Impact velocity", f"{branch.get_last(fd.TYPE_VELOCITY):.2f} m/s"),
        ]

    def provenance_rows(self) -> list[tuple[str, ProvenanceTag]]:
        """Per-component provenance rows for display (same components as the report)."""
        if self.conditions is None:
            return []
        conditions = self.conditions
        rows: list[tuple[str, ProvenanceTag]] = []
        if self.flight_data is not None:
            rows.append(("run (weakest link)", self.flight_data.provenance))
        rows.append(
            (f"vehicle {self.vehicle_name} (overall)", conditions.vehicle.provenance)
        )
        tagged = conditions.vehicle.tagged_values()
        for prop, tv in sorted(
            tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0])
        ):
            rows.append((f"vehicle.{prop}", tv.provenance))
        rows.append(("planet environment", conditions.planet.provenance))
        rows.append(("atmosphere", conditions.planet.atmosphere.provenance))
        rows.append(("gravity", conditions.planet.gravity.provenance))
        rows.append(("aerodynamics", conditions.aerodynamic_calculator.provenance))
        rows.append(("equations of motion", SimulationEngine().stepper.provenance))
        rows.append(("bank schedule", conditions.bank_schedule.provenance))
        return rows

    def save_session_to(self, path: str | Path) -> None:
        if self.conditions is None or self.schedule_source is None:
            raise ValueError("No completed run to save: run the simulation first.")
        save_session(
            path,
            conditions=self.conditions,
            vehicle_name=self.vehicle_name or "",
            schedule_source=self.schedule_source,
        )

    def export_csv_to(self, path: str | Path) -> None:
        if self.flight_data is None:
            raise ValueError("No trajectory to export: run the simulation first.")
        write_trajectory_csv(self.flight_data, path)
