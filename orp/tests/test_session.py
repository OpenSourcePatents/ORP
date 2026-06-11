# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for orp.core.session — reproducible-run sessions (save/load).

Coverage:
  - The determinism test (the heart of the task): save a run's session, reload it COLD
    (fresh objects, no shared state), rerun, and assert the two trajectories are
    bit-identical at the byte level across every FlightData channel, using the same
    struct-pack NaN-safe technique as the Task 1 from_csv follow-up test.
  - Refusal over repair: a tampered schedule value, a tampered vehicle YAML, and a
    missing frame tag each make load raise (naming the offending component, both hashes
    shown for integrity failures).
  - A round-trip for each of the three schedule source kinds: constant, arrays, csv.
  - Saving is pure recording: save_session does not mutate or upgrade provenance.
  - The forward-only wall: the session schema contains no field whose semantics are a
    target endpoint, inspected programmatically so the guard survives future edits.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from pathlib import Path

import pytest

from orp.core import session as S
from orp.core.bank_schedule.schedule import BankSchedule
from orp.core.planet import registry as planet_registry
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.core.simulation import SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.simulation.conditions import SimulationConditions
from orp.core.vehicles.library import load_vehicle

_VEHICLE = "apollo"


# ---------------------------------------------------------------------------
# Bit-identity helpers (same struct-pack NaN-safe technique as the Task 1 test)
# ---------------------------------------------------------------------------

def _bits(values: Sequence[float]) -> bytes:
    """IEEE-754 byte image of a float series (bit-level identity, NaN-safe)."""
    return struct.pack(f"<{len(values)}d", *values)


def _assert_trajectories_bit_identical(traj_a: object, traj_b: object) -> None:
    """Every FlightData channel of both runs must be bit-identical at the byte level."""
    branch_a = traj_a.get_branch(0)  # type: ignore[attr-defined]
    branch_b = traj_b.get_branch(0)  # type: ignore[attr-defined]
    for dtype in fd.ALL_TYPES:
        series_a = branch_a.get(dtype)
        series_b = branch_b.get(dtype)
        assert len(series_a) == len(series_b), (
            f"channel {dtype}: {len(series_a)} vs {len(series_b)} samples"
        )
        assert _bits(series_a) == _bits(series_b), (
            f"channel {dtype}: trajectories are not bit-identical"
        )


# ---------------------------------------------------------------------------
# Schedule / conditions builders for the three source kinds
# ---------------------------------------------------------------------------

def _arrays_schedule() -> tuple[BankSchedule, S.ScheduleSource]:
    times = [0.0, 50.0, 120.0, 300.0]
    angles = [math.radians(a) for a in (0.0, 45.0, -30.0, 60.0)]
    sched = BankSchedule(
        times, angles,
        provenance=ProvenanceTag(ValidationLevel.ASSERTED, source="unit test", notes="arrays"),
    )
    return sched, S.source_arrays(times, angles)


def _constant_schedule() -> tuple[BankSchedule, S.ScheduleSource]:
    sched = BankSchedule.constant(math.radians(55.0), duration=200.0)
    return sched, S.source_constant(math.radians(55.0), duration=200.0)


def _csv_schedule(tmp_path: Path) -> tuple[BankSchedule, S.ScheduleSource, Path]:
    csv_path = tmp_path / "sched.csv"
    csv_path.write_text(
        "time_s,bank_deg\n0,0\n60,40\n180,-20\n400,70\n", encoding="utf-8"
    )
    prov = ProvenanceTag(ValidationLevel.ASSERTED, source="unit test csv")
    sched = BankSchedule.from_csv(csv_path, provenance=prov)
    return sched, S.source_csv(csv_path), csv_path


def _conditions(sched: BankSchedule) -> SimulationConditions:
    return SimulationConditions(
        vehicle=load_vehicle(_VEHICLE),
        planet=planet_registry.by_name("Earth"),
        bank_schedule=sched,
        max_simulation_time=400.0,
    )


# ---------------------------------------------------------------------------
# The determinism test — the heart of the task
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_cold_reload_reruns_bit_identically(self, tmp_path: Path) -> None:
        # --- First run (original objects) ---
        sched1, source1 = _arrays_schedule()
        cond1 = _conditions(sched1)
        traj1 = SimulationEngine().simulate(cond1)

        session_path = tmp_path / "run.yaml"
        S.save_session(
            session_path,
            conditions=cond1,
            vehicle_name=_VEHICLE,
            schedule_source=source1,
        )

        # --- Cold reload: drop every reference to the original objects ---
        del sched1, source1, cond1
        cond2, _doc = S.load_session(session_path)
        # Fresh engine, fresh stepper, no shared state with the first run.
        traj2 = SimulationEngine().simulate(cond2)

        assert traj1.get_branch(0).length > 1  # the run actually produced a trajectory
        _assert_trajectories_bit_identical(traj1, traj2)


# ---------------------------------------------------------------------------
# Round-trip for each of the three schedule source kinds
# ---------------------------------------------------------------------------

class TestSourceRoundTrips:
    def test_constant_round_trip(self, tmp_path: Path) -> None:
        sched, source = _constant_schedule()
        cond = _conditions(sched)
        p = tmp_path / "c.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)
        cond2, doc = S.load_session(p)
        assert doc["bank_schedule"]["source"]["kind"] == S.SOURCE_CONSTANT
        for t in (0.0, 10.0, 250.0):
            assert cond2.bank_schedule.bank_angle_at(t) == pytest.approx(
                sched.bank_angle_at(t)
            )

    def test_arrays_round_trip(self, tmp_path: Path) -> None:
        sched, source = _arrays_schedule()
        cond = _conditions(sched)
        p = tmp_path / "a.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)
        cond2, doc = S.load_session(p)
        assert doc["bank_schedule"]["source"]["kind"] == S.SOURCE_ARRAYS
        assert cond2.bank_schedule.times == sched.times
        assert cond2.bank_schedule.bank_angles == sched.bank_angles

    def test_csv_round_trip(self, tmp_path: Path) -> None:
        sched, source, _csv = _csv_schedule(tmp_path)
        cond = _conditions(sched)
        p = tmp_path / "v.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)
        cond2, doc = S.load_session(p)
        assert doc["bank_schedule"]["source"]["kind"] == S.SOURCE_CSV
        assert cond2.bank_schedule.times == sched.times
        assert cond2.bank_schedule.bank_angles == sched.bank_angles


# ---------------------------------------------------------------------------
# Refusal over repair
# ---------------------------------------------------------------------------

class TestRefusalOverRepair:
    def test_schedule_tamper_refused_naming_schedule(self, tmp_path: Path) -> None:
        sched, source = _arrays_schedule()
        cond = _conditions(sched)
        p = tmp_path / "s.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)

        text = p.read_text(encoding="utf-8")
        # Tamper with exactly one schedule value in the recorded source arrays.
        # The first bank angle is 0.0; nudge it. The content hash must then mismatch.
        tampered = text.replace("- 0.0\n", "- 0.0123\n", 1)
        assert tampered != text, "test setup: expected to find a schedule value to tamper"
        p.write_text(tampered, encoding="utf-8")

        with pytest.raises(S.SessionIntegrityError) as exc:
            S.load_session(p)
        msg = str(exc.value)
        assert "schedule" in msg.lower()
        assert "content_sha256" in msg  # both hashes named
        assert msg.count("sha256=") >= 2 or msg.count("content_sha256=") >= 2

    def test_vehicle_tamper_refused_naming_vehicle(self, tmp_path: Path) -> None:
        # Copy the vehicle YAML into a private dir so we can tamper without touching the
        # bundled library; the session records hashes against this dir.
        veh_dir = tmp_path / "vehicles"
        veh_dir.mkdir()
        bundled = load_vehicle  # noqa: F841 (just to keep import meaningful)
        from orp.core.vehicles.library import VehicleLibrary

        src_yaml = VehicleLibrary().data_dir / f"{_VEHICLE}.yaml"
        dst_yaml = veh_dir / f"{_VEHICLE}.yaml"
        dst_yaml.write_bytes(src_yaml.read_bytes())

        sched, source = _constant_schedule()
        cond = SimulationConditions(
            vehicle=VehicleLibrary(veh_dir).load(_VEHICLE),
            planet=planet_registry.by_name("Earth"),
            bank_schedule=sched,
        )
        p = tmp_path / "vt.yaml"
        S.save_session(
            p, conditions=cond, vehicle_name=_VEHICLE,
            schedule_source=source, vehicle_data_dir=veh_dir,
        )

        # Tamper the vehicle YAML after save.
        body = dst_yaml.read_text(encoding="utf-8")
        dst_yaml.write_text(body + "\n# tampered comment\n", encoding="utf-8")

        with pytest.raises(S.SessionIntegrityError) as exc:
            S.load_session(p, vehicle_data_dir=veh_dir)
        msg = str(exc.value)
        assert "vehicle" in msg.lower()
        assert msg.count("sha256=") >= 2  # both saved and current hashes shown

    def test_missing_frame_tag_refused(self, tmp_path: Path) -> None:
        sched, source = _constant_schedule()
        cond = _conditions(sched)
        p = tmp_path / "nf.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)

        text = p.read_text(encoding="utf-8")
        stripped = text.replace(f"  frame: {S.FRAME_PLANET_RELATIVE}\n", "")
        assert stripped != text, "test setup: expected a frame line to remove"
        p.write_text(stripped, encoding="utf-8")

        with pytest.raises(S.SessionFormatError) as exc:
            S.load_session(p)
        assert "frame" in str(exc.value).lower()

    def test_invalid_frame_tag_refused(self, tmp_path: Path) -> None:
        sched, source = _constant_schedule()
        cond = _conditions(sched)
        p = tmp_path / "if.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)

        text = p.read_text(encoding="utf-8")
        bad = text.replace(
            f"  frame: {S.FRAME_PLANET_RELATIVE}\n", "  frame: body-fixed\n"
        )
        assert bad != text
        p.write_text(bad, encoding="utf-8")

        with pytest.raises(S.SessionFormatError) as exc:
            S.load_session(p)
        assert "frame" in str(exc.value).lower()

    def test_unknown_vehicle_refused(self, tmp_path: Path) -> None:
        sched, source = _constant_schedule()
        cond = _conditions(sched)
        p = tmp_path / "uv.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                f"name: {_VEHICLE}", "name: no_such_vehicle", 1
            ),
            encoding="utf-8",
        )
        with pytest.raises(FileNotFoundError):
            S.load_session(p)

    def test_unknown_planet_refused(self, tmp_path: Path) -> None:
        sched, source = _constant_schedule()
        cond = _conditions(sched)
        p = tmp_path / "up.yaml"
        S.save_session(p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source)
        p.write_text(
            p.read_text(encoding="utf-8").replace("name: Earth", "name: Pluto", 1),
            encoding="utf-8",
        )
        with pytest.raises(KeyError):
            S.load_session(p)


# ---------------------------------------------------------------------------
# Saving is pure recording: no mutation, no provenance upgrade
# ---------------------------------------------------------------------------

class TestSaveIsPureRecording:
    def test_save_does_not_mutate_or_upgrade_provenance(self, tmp_path: Path) -> None:
        sched = BankSchedule.constant(
            math.radians(40.0),
            duration=100.0,
            provenance=ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="hand-built"),
        )
        cond = _conditions(sched)

        # Snapshot provenance levels of every component before saving.
        before = {
            "vehicle": cond.vehicle.provenance.level,
            "planet": cond.planet.provenance.level,
            "aero": cond.aerodynamic_calculator.provenance.level,
            "schedule": cond.bank_schedule.provenance.level,
            "overall": cond.provenance.level,
        }

        p = tmp_path / "pure.yaml"
        doc = S.save_session(
            p, conditions=cond, vehicle_name=_VEHICLE,
            schedule_source=S.source_constant(math.radians(40.0), duration=100.0),
        )

        after = {
            "vehicle": cond.vehicle.provenance.level,
            "planet": cond.planet.provenance.level,
            "aero": cond.aerodynamic_calculator.provenance.level,
            "schedule": cond.bank_schedule.provenance.level,
            "overall": cond.provenance.level,
        }
        assert before == after, "save_session must not mutate any provenance level"

        # And it must record the schedule level AS-IS (not_validated), not upgrade it.
        assert doc["provenance_levels"]["bank_schedule"] == (
            ValidationLevel.NOT_VALIDATED.key
        )
        assert cond.bank_schedule.provenance.level is ValidationLevel.NOT_VALIDATED


# ---------------------------------------------------------------------------
# The forward-only wall
# ---------------------------------------------------------------------------

class TestForwardOnlyWall:
    """The session schema must never name a target endpoint.

    Inspect the saved schema programmatically (collect every leaf key path) so this guard
    survives future edits to the schema: if anyone later adds a field whose name implies a
    desired landing point or terminal target, this test fails.
    """

    # Substrings whose presence in a field name would imply a solved-for terminal target.
    _FORBIDDEN_KEY_SUBSTRINGS = (
        "target", "landing_site", "landing_point", "desired", "goal",
        "aimpoint", "aim_point", "waypoint", "destination",
        "downrange_target", "crossrange_target", "miss_distance",
        "terminal_target", "impact_target", "setpoint",
    )

    @staticmethod
    def _all_key_paths(node: object, prefix: str = "") -> list[str]:
        paths: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{prefix}.{key}" if prefix else str(key)
                paths.append(str(key))
                paths.extend(TestForwardOnlyWall._all_key_paths(value, here))
        elif isinstance(node, (list, tuple)):
            for item in node:
                paths.extend(TestForwardOnlyWall._all_key_paths(item, prefix))
        return paths

    def test_schema_has_no_target_endpoint_field(self, tmp_path: Path) -> None:
        # Build a session covering every block (use arrays so the source mapping is rich).
        sched, source = _arrays_schedule()
        cond = _conditions(sched)
        p = tmp_path / "wall.yaml"
        doc = S.save_session(
            p, conditions=cond, vehicle_name=_VEHICLE, schedule_source=source
        )

        keys = self._all_key_paths(doc)
        assert keys, "test setup: schema produced no keys"
        for key in keys:
            lowered = key.lower()
            for forbidden in self._FORBIDDEN_KEY_SUBSTRINGS:
                assert forbidden not in lowered, (
                    f"forward-only wall: session schema field {key!r} names a target "
                    f"endpoint (matched {forbidden!r}). Sessions record forward-run "
                    "inputs only; they must never carry a solved-for terminal target."
                )

        # The recorded entry-state must be an entry interface, never a terminus: assert the
        # state block carries the entry-* kinematic fields and no *_landing / *_impact field.
        entry_keys = set(doc["entry_state"].keys())
        assert {"entry_altitude", "entry_velocity", "entry_flight_path_angle"} <= entry_keys
        assert not any(
            ("landing" in k.lower() or "impact" in k.lower()) for k in entry_keys
        )
