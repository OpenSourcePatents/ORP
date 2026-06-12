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
import csv
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
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _Refusal(f"cannot create --out directory {out}: {error}") from None
    _write_trajectory_csv(result, out / "trajectory.csv")

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
    _write_provenance_txt(
        out / "provenance.txt",
        result=result,
        conditions=conditions,
        engine=engine,
        vehicle_name=args.vehicle,
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
        f"heading {branch.get_last(fd.TYPE_HEADING):.4f} deg"
    )
    print(f"Run provenance (weakest link): {result.provenance.level.name}")
    print(f"Outputs written to {out}")
    return 0


def _write_trajectory_csv(result: object, path: Path) -> None:
    """Write every FlightData channel; one header row with each channel's unit."""
    from orp.core.simulation import flight_data as fd

    branch = result.get_branch(0)  # type: ignore[attr-defined]
    columns = [(dtype, branch.get(dtype)) for dtype in fd.ALL_TYPES]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([str(dtype) for dtype, _ in columns])  # e.g. "Altitude (m)"
        for i in range(branch.length):
            # repr() is the shortest round-trip representation: deterministic and exact.
            writer.writerow([repr(series[i]) for _, series in columns])


def _format_tag(tag: object) -> str:
    """LEVEL <source> (ProvenanceTag.__str__), stable for reports."""
    return str(tag)


def _write_provenance_txt(
    path: Path,
    *,
    result: object,
    conditions: object,
    engine: object,
    vehicle_name: str,
) -> None:
    """The run's provenance report: weakest link first, then every component."""
    lines: list[str] = []
    # First line: the run's weakest-link level exactly as the engine reported it on
    # the trajectory (conditions weakest-link folded with the stepper's EOM tag).
    lines.append(f"Run weakest-link provenance: {result.provenance.level.name}")  # type: ignore[attr-defined]
    lines.append(
        "(weakest link across vehicle, planet environment models, aerodynamics, "
        "bank schedule, and equations of motion, as reported on the trajectory)"
    )
    lines.append("")

    vehicle = conditions.vehicle  # type: ignore[attr-defined]
    lines.append(f"[vehicle: {vehicle_name} ({vehicle.name})]")
    lines.append(f"  overall (weakest link): {_format_tag(vehicle.provenance)}")
    tagged = vehicle.tagged_values()
    for prop, tv in sorted(tagged.items(), key=lambda kv: (kv[1].provenance.level.rank, kv[0])):
        lines.append(f"  {prop}: {_format_tag(tv.provenance)}")
        if tv.provenance.notes:
            lines.append(f"      notes: {tv.provenance.notes}")
    lines.append("")

    planet = conditions.planet  # type: ignore[attr-defined]
    lines.append(f"[planet: {planet.name}]")
    lines.append(f"  environment (weakest link): {_format_tag(planet.provenance)}")
    lines.append(f"  atmosphere: {_format_tag(planet.atmosphere.provenance)}")
    if planet.atmosphere.provenance.notes:
        lines.append(f"      notes: {planet.atmosphere.provenance.notes}")
    lines.append(f"  gravity: {_format_tag(planet.gravity.provenance)}")
    if planet.gravity.provenance.notes:
        lines.append(f"      notes: {planet.gravity.provenance.notes}")
    lines.append("")

    aero = conditions.aerodynamic_calculator  # type: ignore[attr-defined]
    lines.append("[aerodynamics]")
    lines.append(f"  {type(aero).__name__}: {_format_tag(aero.provenance)}")
    if aero.provenance.notes:
        lines.append(f"      notes: {aero.provenance.notes}")
    lines.append("")

    stepper = engine.stepper  # type: ignore[attr-defined]
    lines.append("[equations of motion]")
    lines.append(f"  {type(stepper).__name__}: {_format_tag(stepper.provenance)}")
    if stepper.provenance.notes:
        lines.append(f"      notes: {stepper.provenance.notes}")
    lines.append("")

    schedule = conditions.bank_schedule  # type: ignore[attr-defined]
    lines.append("[bank schedule]")
    lines.append(f"  {_format_tag(schedule.provenance)}")
    if schedule.provenance.notes:
        lines.append(f"      notes: {schedule.provenance.notes}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


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
# orp gates
# ---------------------------------------------------------------------------

def _cmd_gates(args: argparse.Namespace) -> int:
    """Run the gates; print each status exactly as the gate states it; exit 0 only
    when every gate reports its own pinned expected status (an honest FAIL that the
    gate's tests pin counts as expected)."""
    from orp.gates import gate3_artemis as g3
    from orp.gates import gate3_artemis_replay as gr
    from orp.gates import gate_stardust as gs

    rows: list[tuple[str, bool]] = []  # (printed line, matches pinned expectation)

    # --- Gate 3 scaffold (Artemis I) — pinned by orp/tests/test_gate3_artemis.py ----
    deviations: list[str] = []
    if g3.GATE3_STATUS != "NOT_VALIDATED":
        deviations.append(
            f"GATE3_STATUS is {g3.GATE3_STATUS!r}; pinned expectation is 'NOT_VALIDATED'"
        )
    if g3.lateral_corridor_check()["within_corridor"] is not True:
        deviations.append("lateral corridor check no longer holds")
    try:
        g3.bank_schedule()
        deviations.append(
            "bank_schedule() no longer refuses (the un-locked sign convention is pinned)"
        )
    except NotImplementedError:
        pass
    line = f"GATE 3: Artemis I (Orion) skip entry  --  STATUS: {g3.GATE3_STATUS}"
    if deviations:
        line += f"  [UNEXPECTED DEVIATION: {'; '.join(deviations)}]"
    rows.append((line, not deviations))

    # --- Stardust gate — pinned by orp/tests/test_gate_stardust.py -------------------
    deviations = []
    if gs.GATE_STARDUST_STATUS != "NOT_VALIDATED":
        deviations.append(
            f"GATE_STARDUST_STATUS is {gs.GATE_STARDUST_STATUS!r}; "
            "pinned expectation is 'NOT_VALIDATED'"
        )
    entry = gs.run_entry(28.5)
    if abs(entry["peak_g"] - gs.TRUTH_PEAK_G) > gs.TRUTH_PEAK_G_3SIGMA:
        deviations.append(
            f"peak g {entry['peak_g']:.2f} no longer within the flight 3-sigma "
            f"({gs.TRUTH_PEAK_G} +/- {gs.TRUTH_PEAK_G_3SIGMA})"
        )
    line = f"GATE: Stardust SRC ballistic entry  --  STATUS: {gs.GATE_STARDUST_STATUS}"
    if deviations:
        line += f"  [UNEXPECTED DEVIATION: {'; '.join(deviations)}]"
    rows.append((line, not deviations))

    # --- Gate 3 replay (Artemis I digitized bank) — honest FAIL pinned by
    # orp/tests/test_gate3_replay.py; verdict wording from docs/gates/gate3_artemis_replay.md:
    # "FAIL against the pre-registered tolerances", sign "NOT LOCKED",
    # "The gate stays NOT_VALIDATED". Re-evaluated here, never reworded. ----------------
    replay = gr.run_replay(mass_kg=10160.5, lift_to_drag=0.25, sign=+1.0)
    flight_ballistic_s = g3.TABLE2_PHASE_TIMES["PredGuid Ballistic"][0]
    deviations = []
    if not (replay["dipped_and_rose"] and not replay["returned"]):
        deviations.append("the replay now returns from the first pass (pinned: it does not)")
    if not replay["skip_apogee_kft"] > 10 * gr.SKIP_APOGEE_KFT_FLIGHT:
        deviations.append(
            f"skip apogee {replay['skip_apogee_kft']:.0f} kft no longer >10x flight "
            f"(pinned divergence)"
        )
    if not all(ep is None for ep in replay["endpoints"].values()):
        deviations.append("a Table-4 altitude crossing is now reached (pinned: none)")
    if not (
        replay["t_drag_fall6_s"] is not None
        and abs(replay["t_drag_fall6_s"] - flight_ballistic_s) > gr.TOL_PHASE_PROXY_S_NOMINAL
    ):
        deviations.append(
            "the phase proxy now agrees within the pre-registered tolerance "
            "(pinned: it does not)"
        )
    line = (
        "GATE 3 REPLAY: Artemis I digitized bank command, forward replay  --  STATUS: "
        "FAIL against the pre-registered tolerances; bank-sign convention NOT LOCKED; "
        "the gate stays NOT_VALIDATED"
    )
    if deviations:
        line = (
            "GATE 3 REPLAY: Artemis I digitized bank command, forward replay  --  "
            f"STATUS: UNEXPECTED DEVIATION from the pinned honest FAIL: "
            f"{'; '.join(deviations)}"
        )
    rows.append((line, not deviations))

    # --- report -----------------------------------------------------------------------
    for line, _ in rows:
        print(line)
    # A gate counts as validated only if its own status says neither NOT_VALIDATED
    # nor FAIL — derived from the status text, so this line tracks future gates.
    validated = sum(
        1 for line, _ in rows if "NOT_VALIDATED" not in line and "FAIL" not in line
    )
    scaffolded = len(rows) - validated
    all_expected = all(ok for _, ok in rows)
    closing = (
        "all gates report their pinned expected statuses."
        if all_expected
        else "UNEXPECTED DEVIATION from the pinned statuses detected."
    )
    print(
        f"Summary: {validated} of {len(rows)} gates validated, "
        f"{scaffolded} scaffolded or honest-FAIL; {closing}"
    )
    return 0 if all_expected else 1


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
