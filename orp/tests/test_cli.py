# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for orp.cli — the ORP command line.

Coverage:
  - End-to-end 'orp run' (Apollo, Earth, --bank-deg 60): all five figures plus
    trajectory.csv, session.yaml, provenance.txt are written; the session reloads
    cleanly; provenance.txt's first line matches the engine's reported weakest link.
  - Omitting --frame is a parse error.
  - Frame equivalence: the same physical entry state run once planet-relative and once
    expressed inertially produces bit-identical trajectory.csv bytes.
  - Refusals (one line, nonzero exit, no traceback): both schedule flags, neither
    schedule flag, unknown vehicle, unknown planet, --out existing as a file, and a
    bank-history CSV that fails from_csv validation.
  - 'orp vehicles' lists every library vehicle.
  - 'orp gates' exits 0 and the Artemis line contains NOT_VALIDATED.
  - THE UI WALL: the full parser tree (every subcommand, option string, dest, metavar,
    choice, and help text) contains no endpoint-seeking vocabulary.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

# Headless before any matplotlib import anywhere in the process (plots.py itself is
# Figure-based and never selects a backend; this pins the harness defensively).
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest

from orp.cli import build_parser, main
from orp.core.planet import EARTH
from orp.core.vehicles import VehicleLibrary

_RUN_BASE = [
    "run",
    "--vehicle", "apollo",
    "--planet", "earth",
    "--frame", "planet-relative",
    "--bank-deg", "60",
]


def _out(tmp_path: Path, name: str = "out") -> str:
    return str(tmp_path / name)


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------

class TestEndToEndRun:
    def test_apollo_earth_run_writes_everything(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pytest.importorskip("matplotlib", reason="the run writes the five figures")
        from orp.core.session import load_session
        from orp.core.simulation import SimulationEngine
        from orp.core.simulation import flight_data as fd

        out_dir = tmp_path / "out"
        rc = main(_RUN_BASE + ["--out", str(out_dir)])
        assert rc == 0
        stdout = capsys.readouterr().out

        # All five standard figures plus the three data/report files.
        expected_files = (
            "altitude_time.png",
            "velocity_time.png",
            "g_load_time.png",
            "heat_rate_time.png",
            "ground_track.png",
            "trajectory.csv",
            "session.yaml",
            "provenance.txt",
        )
        for name in expected_files:
            target = out_dir / name
            assert target.is_file(), f"missing output {name}"
            assert target.stat().st_size > 0, f"empty output {name}"

        # trajectory.csv: one header row naming every channel with its unit.
        header = (out_dir / "trajectory.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == [str(t) for t in fd.ALL_TYPES]
        assert "Time (s)" in header
        assert "Stagnation heat rate (W/m^2)" in header

        # The session reloads cleanly (hash checks pass, conditions rebuild).
        conditions, document = load_session(out_dir / "session.yaml")
        assert document["vehicle"]["name"] == "apollo"
        assert document["entry_state"]["frame"] == "planet-relative"

        # provenance.txt's first line states the run's weakest link, which must match
        # the engine's own report: rerun the engine on the reloaded conditions and
        # compare against the provenance it stamps on the trajectory (not a value
        # re-derived the same way the CLI derives it).
        engine_reported = SimulationEngine().simulate(conditions).provenance.level.name
        first_line = (
            (out_dir / "provenance.txt").read_text(encoding="utf-8").splitlines()[0]
        )
        assert first_line == f"Run weakest-link provenance: {engine_reported}"

        # Every component appears in the provenance report.
        report = (out_dir / "provenance.txt").read_text(encoding="utf-8")
        for prop in conditions.vehicle.tagged_values():
            assert f"{prop}:" in report
        for fragment in (
            "[vehicle: apollo",
            "atmosphere:",
            "gravity:",
            "[aerodynamics]",
            "[equations of motion]",
            "[bank schedule]",
        ):
            assert fragment in report, f"provenance.txt is missing {fragment!r}"

        # Closing summary on stdout.
        for fragment in (
            "Run complete:",
            "Peak deceleration:",
            "Peak heat rate:",
            "Final state:",
            "Run provenance (weakest link):",
        ):
            assert fragment in stdout, f"stdout is missing {fragment!r}"


# ---------------------------------------------------------------------------
# Frame handling
# ---------------------------------------------------------------------------

class TestFrameHandling:
    def test_missing_frame_is_a_parse_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = [
            "run", "--vehicle", "apollo", "--planet", "earth",
            "--bank-deg", "60", "--out", _out(tmp_path),
        ]
        with pytest.raises(SystemExit) as excinfo:
            main(argv)
        assert excinfo.value.code == 2
        err = capsys.readouterr().err
        lines = [ln for ln in err.splitlines() if ln.strip()]
        assert len(lines) == 1, f"parse error is not one line:\n{err}"
        assert "--frame" in lines[0]
        assert "Traceback" not in err

    @staticmethod
    def _deg_string_exact(target_rad: float) -> str:
        """A decimal string s such that math.radians(float(s)) == target_rad exactly.

        radians(degrees(x)) is not the identity in floating point, so the degree
        value is searched within a few ulp of degrees(target) for one whose radians
        image is bit-exact. repr() round-trips floats exactly, so the CLI's
        float(s) -> math.radians chain reproduces target_rad to the bit.
        """
        candidate = math.degrees(target_rad)
        candidates = [candidate]
        up = down = candidate
        for _ in range(16):
            up = math.nextafter(up, math.inf)
            down = math.nextafter(down, -math.inf)
            candidates.extend((up, down))
        for value in candidates:
            if math.radians(value) == target_rad:
                return repr(value)
        pytest.fail(
            f"no degree string maps bit-exactly onto {target_rad!r} rad within 16 ulp"
        )

    @staticmethod
    def _planet_relative_to_inertial(
        planet: object,
        *,
        velocity: float,
        flight_path_angle: float,
        heading: float,
        latitude: float,
        altitude: float,
    ) -> tuple[float, float, float]:
        """The inverse frame conversion (relative -> inertial), used as a cross-check.

        orp.core.frames is deliberately forward-only (inertial -> planet-relative);
        this test-local inverse adds the eastward rotation velocity back and
        recomposes speed/FPA/heading, mirroring the forward transform.
        """
        v_rot = (
            planet.rotation_rate  # type: ignore[attr-defined]
            * (planet.mean_radius + altitude)  # type: ignore[attr-defined]
            * math.cos(latitude)
        )
        vertical = velocity * math.sin(flight_path_angle)
        horizontal = velocity * math.cos(flight_path_angle)
        north = horizontal * math.cos(heading)
        east = horizontal * math.sin(heading) + v_rot
        horizontal_inertial = math.hypot(north, east)
        velocity_inertial = math.hypot(horizontal_inertial, vertical)
        fpa_inertial = math.asin(vertical / velocity_inertial)
        heading_inertial = math.atan2(east, north) % (2.0 * math.pi)
        return velocity_inertial, fpa_inertial, heading_inertial

    def test_frame_equivalence_bit_identical_trajectories(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """One physical entry state, two frame expressions, identical bytes out.

        The pair is constructed exactly: the inertial expression is fixed decimal
        strings; its planet-relative expression is what orp.core.frames produces
        from those exact floats (the same function the CLI calls), re-encoded as
        degree strings that parse back bit-exactly. The test-local inverse
        conversion independently confirms the two expressions describe the same
        physical state.
        """
        pytest.importorskip("matplotlib", reason="the run writes the five figures")
        from orp.core.frames import inertial_to_planet_relative

        vel_inertial = "7800.0"
        fpa_inertial = "-6.5"
        heading_inertial = "70.0"
        lat, lon, alt = "30.0", "10.0", "120000.0"

        relative = inertial_to_planet_relative(
            EARTH,
            velocity=float(vel_inertial),
            flight_path_angle=math.radians(float(fpa_inertial)),
            heading=math.radians(float(heading_inertial)),
            latitude=math.radians(float(lat)),
            altitude=float(alt),
        )

        # Cross-check: the inverse conversion recovers the inertial expression.
        v_i, fpa_i, head_i = self._planet_relative_to_inertial(
            EARTH,
            velocity=relative.velocity,
            flight_path_angle=relative.flight_path_angle,
            heading=relative.heading,
            latitude=math.radians(float(lat)),
            altitude=float(alt),
        )
        assert v_i == pytest.approx(float(vel_inertial), rel=1e-12)
        assert fpa_i == pytest.approx(math.radians(float(fpa_inertial)), rel=1e-9)
        assert head_i == pytest.approx(math.radians(float(heading_inertial)), rel=1e-9)

        common = [
            "run", "--vehicle", "apollo", "--planet", "earth",
            "--bank-deg", "45", "--dt", "0.5", "--max-time", "120",
            "--lat", lat, "--lon", lon, "--altitude", alt,
        ]

        out_rel = tmp_path / "rel"
        rc = main(common + [
            "--frame", "planet-relative",
            "--velocity", repr(relative.velocity),
            "--fpa", self._deg_string_exact(relative.flight_path_angle),
            "--heading", self._deg_string_exact(relative.heading),
            "--out", str(out_rel),
        ])
        assert rc == 0
        stdout_rel = capsys.readouterr().out
        assert "Converted entry state" not in stdout_rel  # no conversion happened

        out_inertial = tmp_path / "inertial"
        rc = main(common + [
            "--frame", "inertial",
            "--velocity", vel_inertial,
            "--fpa", fpa_inertial,
            "--heading", heading_inertial,
            "--out", str(out_inertial),
        ])
        assert rc == 0
        stdout_inertial = capsys.readouterr().out
        assert "Converted entry state inertial -> planet-relative" in stdout_inertial

        bytes_rel = (out_rel / "trajectory.csv").read_bytes()
        bytes_inertial = (out_inertial / "trajectory.csv").read_bytes()
        assert bytes_rel == bytes_inertial, (
            "trajectory.csv bytes differ between the planet-relative and inertial "
            "expressions of the same physical entry state"
        )


# ---------------------------------------------------------------------------
# Refusals: one line, nonzero exit, no traceback
# ---------------------------------------------------------------------------

class TestRefusals:
    @staticmethod
    def _assert_one_line_parse_error(
        argv: list[str], fragment: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(argv)
        assert excinfo.value.code == 2
        err = capsys.readouterr().err
        lines = [ln for ln in err.splitlines() if ln.strip()]
        assert len(lines) == 1, f"parse error is not one line:\n{err}"
        assert fragment in lines[0]
        assert "Traceback" not in err

    def test_both_schedule_flags_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = _RUN_BASE + ["--bank-csv", "x.csv", "--out", _out(tmp_path)]
        self._assert_one_line_parse_error(argv, "not allowed with", capsys)

    def test_neither_schedule_flag_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = [
            "run", "--vehicle", "apollo", "--planet", "earth",
            "--frame", "planet-relative", "--out", _out(tmp_path),
        ]
        self._assert_one_line_parse_error(argv, "is required", capsys)

    def test_zero_time_step_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = _RUN_BASE + ["--dt", "0", "--out", _out(tmp_path)]
        self._assert_refusal(argv, "--dt must be positive", capsys)

    def _assert_refusal(
        self, argv: list[str], fragment: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(argv)
        captured = capsys.readouterr()
        assert rc != 0
        assert "Traceback" not in captured.err
        [line] = [ln for ln in captured.err.splitlines() if ln.strip()]  # one line
        assert line.startswith("orp: ")
        assert fragment in line

    def test_unknown_vehicle_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = [
            "run", "--vehicle", "no_such_vehicle", "--planet", "earth",
            "--frame", "planet-relative", "--bank-deg", "60",
            "--out", _out(tmp_path),
        ]
        self._assert_refusal(argv, "No vehicle named", capsys)

    def test_unknown_planet_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = [
            "run", "--vehicle", "apollo", "--planet", "venus",
            "--frame", "planet-relative", "--bank-deg", "60",
            "--out", _out(tmp_path),
        ]
        self._assert_refusal(argv, "Unknown planet", capsys)

    def test_out_existing_as_file_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        argv = _RUN_BASE + ["--out", str(blocker)]
        self._assert_refusal(argv, "exists as a file", capsys)

    def test_bad_bank_csv_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = tmp_path / "bad.csv"
        bad.write_text("time_s,bank_deg\n0.0,nan\n", encoding="utf-8")
        argv = [
            "run", "--vehicle", "apollo", "--planet", "earth",
            "--frame", "planet-relative", "--bank-csv", str(bad),
            "--out", _out(tmp_path),
        ]
        self._assert_refusal(argv, "not accepted", capsys)


# ---------------------------------------------------------------------------
# orp vehicles / orp gates
# ---------------------------------------------------------------------------

class TestVehiclesCommand:
    def test_every_library_vehicle_listed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["vehicles"])
        stdout = capsys.readouterr().out
        assert rc == 0
        names = VehicleLibrary().list_available()
        assert names, "test setup: the vehicle library is empty"
        for name in names:
            assert name in stdout, f"vehicle {name!r} missing from 'orp vehicles' output"
        assert "weakest link:" in stdout


class TestGatesCommand:
    def test_exit_zero_and_artemis_line_not_validated(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["gates"])
        stdout = capsys.readouterr().out
        assert rc == 0, f"orp gates reported unexpected deviation:\n{stdout}"
        artemis_lines = [
            line for line in stdout.splitlines() if "Artemis I (Orion)" in line
        ]
        assert artemis_lines, "no Artemis gate line in 'orp gates' output"
        assert "NOT_VALIDATED" in artemis_lines[0]
        assert "Summary:" in stdout

    def test_missing_flight_data_exits_3_with_one_honest_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An installed package has no repo-root data/flights/: orp gates says so in
        one line and exits 3 — distinct from 0 (as pinned) and 1 (deviation)."""
        import orp.gates.gate3_artemis_replay as gr

        monkeypatch.setattr(gr, "SCHEDULE_CSV", tmp_path / "absent.csv")
        rc = main(["gates"])
        captured = capsys.readouterr()
        assert rc == 3
        assert rc not in (0, 1)
        [line] = [ln for ln in captured.out.splitlines() if ln.strip()]
        assert "source checkout" in line
        assert "Traceback" not in captured.err

    def test_unexpected_deviation_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A gate whose status drifts from its pinned expectation must fail the run."""
        import orp.gates.gate_stardust as gs

        monkeypatch.setattr(gs, "GATE_STARDUST_STATUS", "VALIDATED")
        rc = main(["gates"])
        stdout = capsys.readouterr().out
        assert rc != 0
        assert "UNEXPECTED DEVIATION" in stdout


# ---------------------------------------------------------------------------
# orp run without matplotlib: graceful degradation to data outputs
# ---------------------------------------------------------------------------

class TestRunWithoutMatplotlib:
    def test_degrades_to_data_outputs_with_one_line_notice(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """matplotlib poisoned: the run still succeeds (exit 0), writes the three
        data outputs, prints exactly one figures-skipped line, and the closing
        summary still prints. (The matplotlib-present case — all eight outputs,
        behavior unchanged — is TestEndToEndRun above.)"""
        import sys

        # Poison the lazy import inside the figure-writing step (the from-import
        # consults sys.modules first, so None makes it raise ImportError).
        monkeypatch.setitem(sys.modules, "matplotlib", None)
        monkeypatch.setitem(sys.modules, "matplotlib.figure", None)

        out_dir = tmp_path / "out"
        rc = main(_RUN_BASE + ["--out", str(out_dir)])
        stdout = capsys.readouterr().out
        assert rc == 0  # the simulation itself succeeded

        for name in ("trajectory.csv", "session.yaml", "provenance.txt"):
            assert (out_dir / name).is_file(), f"missing data output {name}"
            assert (out_dir / name).stat().st_size > 0
        assert not list(out_dir.glob("*.png")), "figures written despite no matplotlib"

        notice_lines = [ln for ln in stdout.splitlines() if "Figures skipped" in ln]
        assert len(notice_lines) == 1, f"expected exactly one notice:\n{stdout}"
        assert 'pip install "orp[plot]"' in notice_lines[0]
        # The closing summary still prints.
        for fragment in ("Run complete:", "Peak deceleration:",
                         "Run provenance (weakest link):"):
            assert fragment in stdout


# ---------------------------------------------------------------------------
# orp gui (launch path only; the GUI itself is tested in test_gui*.py)
# ---------------------------------------------------------------------------

class TestGuiSubcommand:
    def test_gui_appears_in_parser_tree(self) -> None:
        """'orp gui' is a real subcommand — and therefore the UI wall test below
        walks its help text automatically."""
        parser = build_parser()
        subcommand_choices: list[str] = []
        for action in parser._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                subcommand_choices.extend(choices.keys())
        assert "gui" in subcommand_choices

    def test_missing_pyqt6_is_one_line_refusal(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With PyQt6 unimportable, 'orp gui' refuses in one plain-language line
        naming pip install orp[gui] — no display, no QApplication, no traceback."""
        import sys

        monkeypatch.setitem(sys.modules, "PyQt6", None)
        monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", None)
        rc = main(["gui"])
        captured = capsys.readouterr()
        assert rc != 0
        assert "Traceback" not in captured.err
        [line] = [ln for ln in captured.err.splitlines() if ln.strip()]
        assert "pip install orp[gui]" in line


# ---------------------------------------------------------------------------
# THE UI WALL — never to be weakened.
# ---------------------------------------------------------------------------

class TestUIWall:
    """THE UI WALL: the CLI surface must never grow endpoint-seeking vocabulary.

    Bank schedules are inputs; crossrange is an output. If any subcommand, flag, help
    text, metavar, dest, or choice ever matches the terms below, someone is building
    (or describing) an interface that accepts a desired endpoint and produces
    controls — which is permanently out of scope for ORP. This test walks the parser
    tree programmatically, so it covers future subcommands and refactors
    automatically. Do not weaken it, do not special-case new flags around it.
    """

    # Endpoint-seeking vocabulary, lowercase substrings. Extending this list is
    # always allowed; shrinking it is never allowed.
    _ENDPOINT_SEEKING_TERMS = (
        "target",
        "landing-point",
        "landing_point",
        "landingpoint",
        "splashdown-aim",
        "splashdown_aim",
        "aimpoint",
        "aim-point",
        "aim_point",
        "waypoint",
        "way-point",
        "destination",
        "desired",
        "goal",
        "setpoint",
        "set-point",
        "solve",
        "optimi",        # optimize / optimise / optimizer
        "guidance",      # guidance-to and any other guidance-flavored flag
        "steer",
        "retarget",
        "miss-distance",
        "miss_distance",
        "missdistance",
        "impact-point",
        "impact_point",
        "touchdown",
        "to-target",
        "inverse",
        "land-at",
        "land_at",
        "landat",
        "fly-to",
        "fly_to",
        "flyto",
        "reach",
        "arrive",
        "deadband",
        "correct-to",
        "correct_to",
    )

    @classmethod
    def _walk_parser_texts(cls, parser: argparse.ArgumentParser) -> list[str]:
        """Collect every user-facing string in the parser tree, recursively.

        Recurses into subparsers generically (any action whose ``choices`` maps
        names to ArgumentParser instances), so new subcommands are covered without
        editing this test.
        """
        texts: list[str] = [
            parser.prog or "",
            parser.description or "",
            parser.epilog or "",
            parser.usage or "",
            # The fully rendered help: catches group titles/descriptions, usage
            # synthesis, and %(default)s substitutions that raw fields would miss.
            parser.format_help(),
        ]
        for group in parser._action_groups:
            texts.append(group.title or "")
            texts.append(group.description or "")
        for action in parser._actions:  # the only complete view argparse offers
            texts.extend(action.option_strings)
            if isinstance(action.dest, str):
                texts.append(action.dest)
            metavar = action.metavar
            if isinstance(metavar, tuple):
                texts.extend(str(m) for m in metavar)
            elif metavar is not None:
                texts.append(str(metavar))
            if action.help and action.help is not argparse.SUPPRESS:
                texts.append(action.help)
            # Subcommand one-line helps live on pseudo-actions.
            for pseudo in getattr(action, "_choices_actions", []) or []:
                if pseudo.help:
                    texts.append(pseudo.help)
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for name, sub in choices.items():
                    texts.append(str(name))
                    if isinstance(sub, argparse.ArgumentParser):
                        texts.extend(cls._walk_parser_texts(sub))
            elif choices is not None:
                texts.extend(str(choice) for choice in choices)
        return texts

    def test_no_endpoint_seeking_vocabulary_anywhere(self) -> None:
        texts = self._walk_parser_texts(build_parser())
        assert len(texts) > 20, "parser walk looks broken (too few strings collected)"
        violations = [
            (text, term)
            for text in texts
            for term in self._ENDPOINT_SEEKING_TERMS
            if term in text.lower()
        ]
        assert not violations, (
            "THE UI WALL: endpoint-seeking vocabulary found in the CLI surface: "
            + "; ".join(f"{term!r} in {text!r}" for text, term in violations)
        )
