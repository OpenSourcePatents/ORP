# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ORP command line: forward reentry runs, the vehicle library, and the gates.

FORWARD-ONLY WALL
=================
This interface composes existing pieces and adds no physics. A run takes a vehicle, a
planet, an explicit entry state (with a mandatory frame tag), and a **pre-recorded bank
schedule** — and produces a trajectory, figures, a reproducible session file, and a
provenance report. Bank schedules are inputs; the trajectory and its ground track are
outputs. No flag, argument, or subcommand accepts an endpoint and produces controls, and
``orp/tests/test_cli.py`` walks the parser tree to keep it that way.

REFUSAL OVER REPAIR
===================
Bad input is refused with a one-line plain-language reason and a nonzero exit — an unknown
vehicle or planet, a missing frame tag, a malformed bank-history CSV, an output path that
is an existing file. Nothing is substituted or repaired silently.

Frame handling: the engine consumes a planet-relative entry state. ``--frame inertial``
states are converted at this boundary via :mod:`orp.core.frames` (convert first, then
save — sessions always record the planet-relative state the engine consumed).
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import os
import sys
from pathlib import Path

__all__ = ["build_parser", "main"]


class _Refusal(Exception):
    """A plain-language refusal: printed as one line to stderr, exit nonzero, no traceback."""


class _ArgumentParser(argparse.ArgumentParser):
    """argparse with one-line parse errors (refusal over usage spam).

    Parse-stage refusals (missing --frame, both or neither schedule flags, unknown
    subcommand) exit 2 with exactly one plain-language line on stderr, matching the
    behaviour of the post-parse refusals. Subparsers inherit this class.
    """

    def error(self, message: str):  # noqa: D102 — argparse contract
        self.exit(2, f"{self.prog}: {message}\n")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _conditions_defaults() -> dict[str, object]:
    """The engine's current defaults, read from SimulationConditions itself."""
    from orp.core.simulation.conditions import SimulationConditions

    return {
        f.name: f.default
        for f in dataclasses.fields(SimulationConditions)
        if f.default is not dataclasses.MISSING
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the ``orp`` argument parser (public so tests can walk the whole tree)."""
    defaults = _conditions_defaults()

    parser = _ArgumentParser(
        prog="orp",
        description=(
            "ORP - Open Reentry Platform. Forward-only atmospheric reentry runs with "
            "first-class provenance: bank schedules are inputs, the trajectory and its "
            "ground track are outputs."
        ),
    )
    subparsers = parser.add_subparsers(
        title="commands", dest="command", required=True, metavar="{run,vehicles,gates}"
    )

    # ----- orp run ---------------------------------------------------------
    run = subparsers.add_parser(
        "run",
        help="run one forward reentry simulation and write its outputs",
        description=(
            "Run one forward reentry simulation: replay the given bank schedule through "
            "the engine and write trajectory.csv, the five standard figures, "
            "session.yaml, and provenance.txt into --out."
        ),
    )
    run.add_argument("--vehicle", required=True, metavar="NAME",
                     help="vehicle library name (see 'orp vehicles')")
    run.add_argument("--planet", required=True, metavar="NAME",
                     help="planet name from the registry (earth or mars)")
    run.add_argument("--velocity", type=float, metavar="M_PER_S",
                     default=float(defaults["entry_velocity"]),
                     help="entry speed in m/s, expressed in --frame (default: %(default)s)")
    run.add_argument("--fpa", type=float, metavar="DEG",
                     default=math.degrees(float(defaults["entry_flight_path_angle"])),
                     help=("entry flight-path angle in degrees, negative descending, "
                           "expressed in --frame (default: %(default).4g)"))
    run.add_argument("--heading", type=float, metavar="DEG",
                     default=math.degrees(float(defaults["entry_heading"])),
                     help=("entry heading in degrees clockwise from north, expressed in "
                           "--frame (default: %(default).4g)"))
    run.add_argument("--altitude", type=float, metavar="M",
                     default=float(defaults["entry_altitude"]),
                     help="entry altitude in meters above the mean radius (default: %(default)s)")
    run.add_argument("--lat", type=float, metavar="DEG",
                     default=math.degrees(float(defaults["entry_latitude"])),
                     help="entry latitude in degrees (default: %(default)s)")
    run.add_argument("--lon", type=float, metavar="DEG",
                     default=math.degrees(float(defaults["entry_longitude"])),
                     help="entry longitude in degrees (default: %(default)s)")
    run.add_argument("--frame", required=True, choices=("inertial", "planet-relative"),
                     help=("frame the entry state is expressed in (REQUIRED, no default). "
                           "'inertial' is converted to planet-relative at this boundary "
                           "via orp.core.frames before the run; sessions record the "
                           "converted state."))

    schedule = run.add_mutually_exclusive_group(required=True)
    schedule.add_argument("--bank-deg", type=float, metavar="CONST",
                          help=("constant commanded bank angle in degrees - a "
                                "pre-recorded control input, replayed as-is"))
    schedule.add_argument("--bank-csv", metavar="PATH",
                          help=("two-column CSV (time_s, bank_angle_deg) commanded-bank "
                                "history, loaded via BankSchedule.from_csv and replayed "
                                "as-is"))

    run.add_argument("--dt", type=float, metavar="S",
                     default=float(defaults["time_step"]),
                     help="integrator time step in seconds (engine default: %(default)s)")
    run.add_argument("--max-time", type=float, metavar="S",
                     default=float(defaults["max_simulation_time"]),
                     help="maximum simulated time in seconds (engine default: %(default)s)")
    run.add_argument("--out", required=True, metavar="DIR",
                     help=("output directory for this run's files (created if needed; "
                           "refused if it exists as a file)"))
    run.set_defaults(func=_cmd_run)

    # ----- orp vehicles ----------------------------------------------------
    vehicles = subparsers.add_parser(
        "vehicles",
        help="list library vehicles with per-property provenance",
        description=("List every vehicle in the library: name, source citation count, "
                     "and a per-property provenance summary (worst tag first)."),
    )
    vehicles.set_defaults(func=_cmd_vehicles)

    # ----- orp gui ---------------------------------------------------------
    gui = subparsers.add_parser(
        "gui",
        help="launch the ORP desktop interface (needs the gui extra)",
        description=(
            "Launch the ORP desktop interface (PyQt6). Requires the optional gui "
            "dependencies: pip install orp[gui]."
        ),
    )
    gui.set_defaults(func=_cmd_gui)

    # ----- orp gates -------------------------------------------------------
    gates = subparsers.add_parser(
        "gates",
        help="run the validation gates and report their statuses",
        description=("Run the validation gates and print each gate's status exactly as "
                     "the gate states it (NOT_VALIDATED and honest FAIL included, never "
                     "reworded). Exit 0 when every gate reports its own pinned expected "
                     "status; nonzero on unexpected deviation."),
    )
    gates.set_defaults(func=_cmd_gates)

    return parser


# ---------------------------------------------------------------------------
# orp run
# ---------------------------------------------------------------------------

def _require_finite(name: str, value: float, *, positive: bool = False) -> float:
    """Refuse non-finite (and, where demanded, non-positive) numeric arguments."""
    if not math.isfinite(value):
        raise _Refusal(f"{name} must be a finite number (got {value!r}).")
    if positive and value <= 0.0:
        raise _Refusal(f"{name} must be positive (got {value!r}).")
    return float(value)


def _cmd_run(args: argparse.Namespace) -> int:
    from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
    from orp.core.bank_schedule import BankSchedule
    from orp.core.frames import FrameConversionError, inertial_to_planet_relative
    from orp.core.planet import by_name
    from orp.core.provenance import ProvenanceTag, ValidationLevel, weakest
    from orp.core.session import save_session, source_constant, source_csv
    from orp.core.simulation import SimulationConditions, SimulationEngine
    from orp.core.vehicles import VehicleLibrary
    from orp.gui import plots

    # Fail fast on numbers the engine cannot meaningfully consume. --dt and
    # --max-time must be positive (a zero time step would never advance).
    velocity = _require_finite("--velocity", args.velocity, positive=True)
    fpa_deg = _require_finite("--fpa", args.fpa)
    heading_deg = _require_finite("--heading", args.heading)
    altitude = _require_finite("--altitude", args.altitude)
    lat_deg = _require_finite("--lat", args.lat)
    lon_deg = _require_finite("--lon", args.lon)
    dt = _require_finite("--dt", args.dt, positive=True)
    max_time = _require_finite("--max-time", args.max_time, positive=True)
    if args.bank_deg is not None:
        _require_finite("--bank-deg", args.bank_deg)

    out = Path(args.out)
    if out.is_file():
        raise _Refusal(
            f"--out {out} already exists as a file; pass a directory "
            "(it is created if missing)."
        )

    try:
        vehicle = VehicleLibrary().load(args.vehicle)
    except (OSError, ValueError) as error:
        # Unknown name (FileNotFoundError) or a malformed/unreadable vehicle YAML.
        raise _Refusal(str(error)) from None

    try:
        planet = by_name(args.planet)
    except KeyError as error:
        raise _Refusal(error.args[0] if error.args else str(error)) from None

    # --- bank schedule: a pre-recorded control input, replayed as-is -------
    if args.bank_csv is not None:
        schedule_provenance = ProvenanceTag(
            ValidationLevel.ASSERTED,
            source=f"user-supplied CSV: {args.bank_csv}",
            notes="Commanded bank history supplied via CLI --bank-csv; replayed as-is.",
        )
        try:
            bank_schedule = BankSchedule.from_csv(
                args.bank_csv, provenance=schedule_provenance
            )
        except (ValueError, OSError) as error:
            raise _Refusal(str(error)) from None
        # Record the absolute path: session CSV sources resolve against the session
        # file's directory at load time, so a cwd-relative path would not reload.
        schedule_source = source_csv(Path(args.bank_csv).resolve())
    else:
        bank_rad = math.radians(args.bank_deg)
        schedule_provenance = ProvenanceTag(
            ValidationLevel.NOT_VALIDATED,
            source=f"user-supplied constant via CLI --bank-deg {args.bank_deg}",
            notes="Hand-entered constant bank command; unsourced.",
        )
        bank_schedule = BankSchedule.constant(bank_rad, provenance=schedule_provenance)
        schedule_source = source_constant(bank_rad)

    # --- entry state (SI / radians), frame handled at this boundary --------
    flight_path_angle = math.radians(fpa_deg)
    heading = math.radians(heading_deg)
    latitude = math.radians(lat_deg)
    longitude = math.radians(lon_deg)

    if args.frame == "inertial":
        try:
            relative = inertial_to_planet_relative(
                planet,
                velocity=velocity,
                flight_path_angle=flight_path_angle,
                heading=heading,
                latitude=latitude,
                altitude=altitude,
            )
        except FrameConversionError as error:
            raise _Refusal(str(error)) from None
        velocity = relative.velocity
        flight_path_angle = relative.flight_path_angle
        heading = relative.heading
        print(
            "Converted entry state inertial -> planet-relative (eastward "
            "planet-rotation velocity subtracted): "
            f"velocity {velocity:.6f} m/s, "
            f"flight-path angle {math.degrees(flight_path_angle):.6f} deg, "
            f"heading {math.degrees(heading):.6f} deg."
        )

    # Constant-coefficient aero from the vehicle's own cited nominal coefficients
    # (the repo's gate/plot convention); provenance is their weakest link.
    aero = ConstantCoefficientCalculator(
        vehicle.drag_coefficient.get(),
        vehicle.lift_to_drag.get(),
        provenance=weakest([vehicle.drag_coefficient, vehicle.lift_to_drag]),
    )

    conditions = SimulationConditions(
        vehicle=vehicle,
        planet=planet,
        bank_schedule=bank_schedule,
        aerodynamic_calculator=aero,
        entry_velocity=velocity,
        entry_flight_path_angle=flight_path_angle,
        entry_altitude=altitude,
        entry_heading=heading,
        entry_latitude=latitude,
        entry_longitude=longitude,
        time_step=dt,
        max_simulation_time=max_time,
    )

    engine = SimulationEngine()
    result = engine.simulate(conditions)

    # --- outputs ------------------------------------------------------------
    from orp.core.report import render_provenance_report, write_trajectory_csv

    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _Refusal(f"cannot create --out directory {out}: {error}") from None
    write_trajectory_csv(result, out / "trajectory.csv")

    # plots.py is Figure-based (never pyplot), headless by construction; the env var
    # additionally pins any future backend selection to Agg without importing matplotlib.
    os.environ.setdefault("MPLBACKEND", "Agg")
    plots.save_standard_plots(result, out)

    save_session(
        out / "session.yaml",
        conditions=conditions,
        vehicle_name=args.vehicle,
        schedule_source=schedule_source,
    )
    (out / "provenance.txt").write_text(
        render_provenance_report(
            result=result,
            conditions=conditions,
            engine=engine,
            vehicle_name=args.vehicle,
        ),
        encoding="utf-8",
    )

    # --- closing summary ----------------------------------------------------
    from orp.core.simulation import flight_data as fd

    branch = result.get_branch(0)
    end_event = branch.events[-1].name if branch.events else "(no events)"
    print(
        f"Run complete: {branch.length} samples, "
        f"terminated by {end_event} at t={branch.get_last(fd.TYPE_TIME):.3f} s."
    )
    print(f"Peak deceleration: {result.summary.get('peak_deceleration', float('nan')):.4f} g")
    print(f"Peak heat rate: {result.summary.get('peak_heat_rate', float('nan')):.6g} W/m^2")
    print(
        "Final state: "
        f"altitude {branch.get_last(fd.TYPE_ALTITUDE):.1f} m, "
        f"velocity {branch.get_last(fd.TYPE_VELOCITY):.2f} m/s, "
        f"latitude {branch.get_last(fd.TYPE_LATITUDE):.5f} deg, "
        f"longitude {branch.get_last(fd.TYPE_LONGITUDE):.5f} deg, "
        f"flight-path angle {branch.get_last(fd.TYPE_FLIGHT_PATH_ANGLE):.4f} deg, "
        # Display-only wrap to [0, 360); the recorded channel (trajectory.csv) is
        # left exactly as the engine integrated it.
        f"heading {branch.get_last(fd.TYPE_HEADING) % 360.0:.4f} deg"
    )
    print(f"Run provenance (weakest link): {result.provenance.level.name}")
    print(f"Outputs written to {out}")
    return 0


# ---------------------------------------------------------------------------
# orp vehicles
# ---------------------------------------------------------------------------

def _cmd_vehicles(args: argparse.Namespace) -> int:
    from orp.core.vehicles import VehicleLibrary

    library = VehicleLibrary()
    names = library.list_available()
    if not names:
        print(f"No vehicles found in {library.data_dir}.")
        return 0
    for name in names:
        vehicle = library.load(name)
        tagged = vehicle.tagged_values()
        citations = {tv.provenance.source for tv in tagged.values() if tv.provenance.source}
        print(
            f"{name}  ({vehicle.name}): {len(tagged)} properties, "
            f"{len(citations)} distinct source citation(s); "
            f"weakest link: {vehicle.provenance.level.name}"
        )
        # Per-property provenance, worst tag first (then by property name).
        for prop, tv in sorted(
            tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0])
        ):
            source = f" <{tv.provenance.source}>" if tv.provenance.source else ""
            print(f"    {prop}: {tv.provenance.level.name}{source}")
        print()
    return 0


# ---------------------------------------------------------------------------
# orp gui
# ---------------------------------------------------------------------------

def _cmd_gui(args: argparse.Namespace) -> int:
    """Launch the desktop interface. PyQt6 is imported lazily HERE so that run,
    vehicles, and gates keep working when the gui extra is not installed."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        raise _Refusal(
            "the desktop interface needs PyQt6, which is not installed; "
            "install it with: pip install orp[gui]"
        ) from None

    from orp.gui.app_state import AppState
    from orp.gui.icon import orp_icon
    from orp.gui.main_window import MainWindow

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setWindowIcon(orp_icon())
    window = MainWindow(AppState())
    window.show()
    return app.exec()


# ---------------------------------------------------------------------------
# orp gates
# ---------------------------------------------------------------------------

def _cmd_gates(args: argparse.Namespace) -> int:
    """Run the gates; print each status exactly as the gate states it; exit 0 only
    when every gate reports its own pinned expected status (an honest FAIL that the
    gate's tests pin counts as expected). Evaluation lives in orp.gates.summary,
    shared with every other front end so the wording can never drift."""
    from orp.gates.summary import evaluate_gates

    report = evaluate_gates()
    for row in report.rows:
        print(row.line)
    print(report.summary_line)
    return 0 if report.all_expected else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """The ``orp`` console entry point. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except _Refusal as refusal:
        print(f"orp: {refusal}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
