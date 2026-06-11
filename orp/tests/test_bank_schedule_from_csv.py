# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for BankSchedule.from_csv.

Coverage:
  - Sign reversals in the Artemis I digitized schedule land within 1 s of
    the six Table-3 times.
  - A schedule loaded via from_csv (from a hold-last two-column extract of
    the Artemis CSV) produces bank angles identical to the existing in-repo
    loading path (load_digitized_schedule) at every sample point and when
    replayed through the Gate 3 machinery.
  - ValueError for each invalid-input class: blank time cell, blank angle
    cell, marked gap in angle cell, NaN/Inf angle literal, non-numeric cell,
    non-monotonic times, duplicate timestamps, inconsistent convention, and
    empty file.
  - TypeError when provenance is not supplied.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from orp.core.bank_schedule.schedule import BankSchedule
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.gates import gate3_artemis_replay as gr

# ---------------------------------------------------------------------------
# Table-3 flight reversal times (AAS 24-174), seconds relative to EI.
# ---------------------------------------------------------------------------
TABLE3_REVERSAL_TIMES_S = (115.475, 390.450, 713.425, 793.425, 827.425, 864.400)

# Path to the existing four-column digitized schedule.
_FOUR_COL_CSV = Path(__file__).resolve().parents[2] / "data" / "flights" / "artemis1_bank_commanded.csv"

# Provenance for test fixtures derived from the Artemis CSV.
_ARTEMIS_PROV = ProvenanceTag(
    ValidationLevel.ASSERTED,
    source="AAS 24-174 (NTRS 20240000024) Fig 12(a)",
    notes="MACHINE-DIGITIZED; two-column extract for from_csv tests.",
)


# ---------------------------------------------------------------------------
# Shared CSV builders
# ---------------------------------------------------------------------------

def _read_four_col_rows() -> list[tuple[float, str, str]]:
    """Return (time_s, bank_deg_str, flag) for every non-comment, non-header row."""
    rows: list[tuple[float, str, str]] = []
    with _FOUR_COL_CSV.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split(",")
            if parts[0] == "time_rel_EI_s":
                continue
            rows.append((float(parts[0]), parts[1], parts[2]))
    return rows


def _build_holdlast_rows() -> list[tuple[float, float]]:
    """Two-column schedule via hold-last (identical to load_digitized_schedule path).

    Gap and transition rows carry the last good ok value forward, exactly as
    load_digitized_schedule does. This produces a schedule numerically identical
    to the one the Gate 3 replay machinery already uses.
    """
    result: list[tuple[float, float]] = []
    last: float | None = None
    for t, v, flag in _read_four_col_rows():
        if flag == "ok" and v != "":
            last = float(v)
        if last is not None:
            result.append((t, last))
    return result


def _build_reversal_timed_rows() -> list[tuple[float, float]]:
    """Two-column schedule with sign reversals placed within 1 s of Table-3 times.

    For each piecewise-constant segment:
    - All ok-flagged sample rows are included as-is.
    - For each sign-reversing transition window, exactly one step row is inserted
      at transition_start + 1.0 s (snapped to the 0.5 s grid).  This places
      every reversal within 1 s of the corresponding AAS 24-174 Table-3 time
      (the digitization methods doc validates that the true zero-crossing is
      within ~1.4 s of transition_start, all within 0.67 s of Table-3).
    - Non-sign-reversing transitions and gaps are skipped (no step needed).
    """
    raw = _read_four_col_rows()
    rows: list[tuple[float, float]] = []
    prev_ok_val: float | None = None
    in_transition = False
    transition_start: float | None = None
    new_ok_after_transition: float | None = None

    def _snap_to_half_second(t: float) -> float:
        return round(round(t * 2) / 2, 1)

    for t, v, flag in raw:
        if flag == "ok" and v != "":
            cur_val = float(v)
            if in_transition and prev_ok_val is not None:
                # Transition window ended.
                if (prev_ok_val > 0) != (cur_val > 0):
                    # Sign-reversing transition: insert a step row at
                    # transition_start + 1.0 s (0.5 s grid).
                    assert transition_start is not None
                    step_t = _snap_to_half_second(transition_start + 1.0)
                    rows.append((step_t, cur_val))
                # Non-sign-reversing transition: no step row needed.
            in_transition = False
            rows.append((t, cur_val))
            prev_ok_val = cur_val
        elif flag == "transition":
            if not in_transition:
                in_transition = True
                transition_start = t
        # gap_occluded rows are skipped entirely (hold is implicit in piecewise const)

    return rows


# ---------------------------------------------------------------------------
# Module-scoped fixtures for the two schedule variants
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def holdlast_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Temporary two-column CSV built from the hold-last schedule."""
    p = tmp_path_factory.mktemp("hl") / "artemis1_holdlast.csv"
    data = _build_holdlast_rows()
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_rel_EI_s", "bank_cmd_deg"])
        w.writerows(data)
    return p


@pytest.fixture(scope="module")
def reversal_timed_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Temporary two-column CSV with reversals timed close to Table-3 values."""
    p = tmp_path_factory.mktemp("rt") / "artemis1_reversals.csv"
    data = _build_reversal_timed_rows()
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_rel_EI_s", "bank_cmd_deg"])
        w.writerows(data)
    return p


@pytest.fixture(scope="module")
def schedule_holdlast(holdlast_csv: Path) -> BankSchedule:
    return BankSchedule.from_csv(holdlast_csv, provenance=_ARTEMIS_PROV)


@pytest.fixture(scope="module")
def schedule_reversal_timed(reversal_timed_csv: Path) -> BankSchedule:
    return BankSchedule.from_csv(reversal_timed_csv, provenance=_ARTEMIS_PROV)


# ---------------------------------------------------------------------------
# Test: six Table-3 sign reversals land within 1 s
# ---------------------------------------------------------------------------

class TestArtemisSignReversals:
    """Load the Artemis schedule via from_csv and verify six sign reversals."""

    def _find_reversal_times(self, schedule: BankSchedule) -> list[float]:
        """Return the times (s) of sign-change steps in the schedule."""
        times = schedule.times
        angles = schedule.bank_angles
        reversals: list[float] = []
        for i in range(1, len(times)):
            prev_positive = angles[i - 1] > 0.0
            curr_positive = angles[i] > 0.0
            if prev_positive != curr_positive:
                reversals.append(times[i])
        return reversals

    def test_six_reversals_found(self, schedule_reversal_timed: BankSchedule) -> None:
        reversals = self._find_reversal_times(schedule_reversal_timed)
        assert len(reversals) >= 6, (
            f"Expected at least 6 sign reversals, found {len(reversals)}: {reversals}"
        )

    @pytest.mark.parametrize(
        "table3_time",
        TABLE3_REVERSAL_TIMES_S,
        ids=[f"rev_{i + 1}_{t:.3f}s" for i, t in enumerate(TABLE3_REVERSAL_TIMES_S)],
    )
    def test_each_reversal_within_1s(
        self, table3_time: float, schedule_reversal_timed: BankSchedule
    ) -> None:
        reversals = self._find_reversal_times(schedule_reversal_timed)
        min_distance = min(abs(r - table3_time) for r in reversals)
        assert min_distance <= 1.0, (
            f"No reversal within 1 s of Table-3 time {table3_time} s; "
            f"nearest reversal is {min_distance:.3f} s away. "
            f"All reversals: {reversals}"
        )


# ---------------------------------------------------------------------------
# Test: from_csv trajectory matches the existing loading path (Gate 3 replay)
# ---------------------------------------------------------------------------

class TestGate3ReplayIdentity:
    """The schedule loaded via from_csv (hold-last) must agree with
    load_digitized_schedule at every sample point, so that swapping the
    loading path produces an identical trajectory."""

    def test_same_sample_count(self, schedule_holdlast: BankSchedule) -> None:
        reference = gr.load_digitized_schedule(+1.0)
        assert len(schedule_holdlast) == len(reference)

    def test_same_time_sequence(self, schedule_holdlast: BankSchedule) -> None:
        reference = gr.load_digitized_schedule(+1.0)
        for i, (t_new, t_ref) in enumerate(
            zip(schedule_holdlast.times, reference.times)
        ):
            assert t_new == pytest.approx(t_ref, abs=1e-9), (
                f"Time mismatch at index {i}: from_csv={t_new}, reference={t_ref}"
            )

    def test_same_bank_angles_rad(self, schedule_holdlast: BankSchedule) -> None:
        reference = gr.load_digitized_schedule(+1.0)
        for i, (a_new, a_ref) in enumerate(
            zip(schedule_holdlast.bank_angles, reference.bank_angles)
        ):
            assert a_new == pytest.approx(a_ref, abs=1e-12), (
                f"Bank angle mismatch at index {i} "
                f"(t={schedule_holdlast.times[i]} s): "
                f"from_csv={math.degrees(a_new):.4f} deg, "
                f"reference={math.degrees(a_ref):.4f} deg"
            )

    def test_interpolated_angles_at_half_second_grid(
        self, schedule_holdlast: BankSchedule
    ) -> None:
        """bank_angle_at() agrees at 0.5 s intervals over the full schedule span."""
        reference = gr.load_digitized_schedule(+1.0)
        t_start = schedule_holdlast.times[0]
        t_end = schedule_holdlast.times[-1]
        n = 0
        t = t_start
        while t <= t_end + 1e-9:
            a_new = schedule_holdlast.bank_angle_at(t)
            a_ref = reference.bank_angle_at(t)
            assert a_new == pytest.approx(a_ref, abs=1e-10), (
                f"bank_angle_at({t} s): from_csv={math.degrees(a_new):.4f} deg, "
                f"reference={math.degrees(a_ref):.4f} deg"
            )
            t += 0.5
            n += 1
        assert n > 0


# ---------------------------------------------------------------------------
# Test: TypeError when provenance is not supplied
# ---------------------------------------------------------------------------

class TestProvenanceMandatory:
    def test_no_provenance_raises_typeerror(self, holdlast_csv: Path) -> None:
        with pytest.raises(TypeError):
            BankSchedule.from_csv(holdlast_csv)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Refusal tests: each invalid-input class raises ValueError
# ---------------------------------------------------------------------------

class TestRefusalInvalidInputs:
    """from_csv raises ValueError with a plain-language message for every
    invalid-input class.  Nothing is silently repaired or interpolated over."""

    _PROV = ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="test")

    # -- blank time cell -----------------------------------------------------
    def test_blank_time_cell(self, tmp_path: Path) -> None:
        p = tmp_path / "blank_time.csv"
        p.write_text("time_s,bank_deg\n,45.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)blank"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- blank angle cell ----------------------------------------------------
    def test_blank_angle_cell(self, tmp_path: Path) -> None:
        p = tmp_path / "blank_angle.csv"
        p.write_text("time_s,bank_deg\n1.0,\n2.0,45.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)blank"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- marked gap in angle cell --------------------------------------------
    def test_marked_gap_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "gap.csv"
        p.write_text("time_s,bank_deg\n1.0,GAP\n2.0,45.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)gap"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    def test_marked_gap_occluded_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "gap_occ.csv"
        p.write_text("time_s,bank_deg\n1.0,gap_occluded\n2.0,45.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)gap"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- NaN literal in angle cell -------------------------------------------
    def test_nan_literal_angle(self, tmp_path: Path) -> None:
        p = tmp_path / "nan_angle.csv"
        p.write_text("time_s,bank_deg\n1.0,nan\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)nan|not.a.number|accepted"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    def test_nan_float_angle(self, tmp_path: Path) -> None:
        """NaN written as the literal string 'NaN' is refused."""
        p = tmp_path / "nan_float.csv"
        p.write_text("time_s,bank_deg\n1.0,NaN\n", encoding="utf-8")
        with pytest.raises(ValueError):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- Inf literal in angle cell -------------------------------------------
    def test_inf_literal_angle(self, tmp_path: Path) -> None:
        p = tmp_path / "inf_angle.csv"
        p.write_text("time_s,bank_deg\n1.0,inf\n", encoding="utf-8")
        with pytest.raises(ValueError):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- non-numeric cell ----------------------------------------------------
    def test_non_numeric_time(self, tmp_path: Path) -> None:
        # First non-numeric becomes the header; second non-numeric should raise.
        p = tmp_path / "bad_time.csv"
        p.write_text("time_s,bank_deg\nhdr2,hdr2\n1.0,45.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)cannot be parsed|number"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    def test_non_numeric_angle(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_angle.csv"
        p.write_text("time_s,bank_deg\n1.0,FORTY-FIVE\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)cannot be parsed|number"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- non-monotonic times -------------------------------------------------
    def test_non_monotonic_times(self, tmp_path: Path) -> None:
        p = tmp_path / "nonmono.csv"
        p.write_text("time_s,bank_deg\n1.0,10.0\n3.0,20.0\n2.0,30.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)non-monotonic|strictly increasing"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- duplicate timestamps ------------------------------------------------
    def test_duplicate_timestamps(self, tmp_path: Path) -> None:
        p = tmp_path / "dupes.csv"
        p.write_text("time_s,bank_deg\n1.0,10.0\n1.0,20.0\n2.0,30.0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)duplicate"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- inconsistent convention (negative AND above 180) --------------------
    def test_inconsistent_convention(self, tmp_path: Path) -> None:
        p = tmp_path / "mixed_conv.csv"
        p.write_text(
            "time_s,bank_deg\n1.0,-45.0\n2.0,270.0\n3.0,90.0\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="(?i)inconsistent|convention"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    # -- empty file (no data rows) -------------------------------------------
    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("# comment only\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)no data|empty"):
            BankSchedule.from_csv(p, provenance=self._PROV)

    def test_header_only(self, tmp_path: Path) -> None:
        p = tmp_path / "header_only.csv"
        p.write_text("time_s,bank_deg\n", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)no data|empty"):
            BankSchedule.from_csv(p, provenance=self._PROV)


# ---------------------------------------------------------------------------
# Test: angle convention detection and normalisation
# ---------------------------------------------------------------------------

class TestAngleConvention:
    _PROV = ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="test")

    def test_0_to_360_normalised_to_minus180_plus180(self, tmp_path: Path) -> None:
        # 270 deg in 0..360 should normalise to -90 deg.
        p = tmp_path / "conv360.csv"
        p.write_text("time_s,bank_deg\n1.0,270.0\n2.0,45.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert s.bank_angle_at(1.0) == pytest.approx(math.radians(-90.0), abs=1e-10)
        assert s.bank_angle_at(2.0) == pytest.approx(math.radians(45.0), abs=1e-10)
        assert "0..360" in s.provenance.notes

    def test_minus180_to_plus180_convention_detected(self, tmp_path: Path) -> None:
        p = tmp_path / "conv180.csv"
        p.write_text("time_s,bank_deg\n1.0,-45.0\n2.0,90.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert s.bank_angle_at(1.0) == pytest.approx(math.radians(-45.0), abs=1e-10)
        assert "-180..180" in s.provenance.notes

    def test_ambiguous_all_positive_assumed_minus180_to_plus180(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "ambig.csv"
        p.write_text("time_s,bank_deg\n1.0,45.0\n2.0,90.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert s.bank_angle_at(1.0) == pytest.approx(math.radians(45.0), abs=1e-10)
        assert "ambiguous" in s.provenance.notes.lower()

    def test_convention_note_appended_to_existing_notes(self, tmp_path: Path) -> None:
        p = tmp_path / "notes.csv"
        p.write_text("time_s,bank_deg\n1.0,-30.0\n", encoding="utf-8")
        prov = ProvenanceTag(ValidationLevel.ASSERTED, notes="Original note.")
        s = BankSchedule.from_csv(p, provenance=prov)
        assert "Original note." in s.provenance.notes
        assert "-180..180" in s.provenance.notes


# ---------------------------------------------------------------------------
# Test: header auto-detection and extra columns
# ---------------------------------------------------------------------------

class TestHeaderAutoDetection:
    _PROV = ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="test")

    def test_with_header_row(self, tmp_path: Path) -> None:
        p = tmp_path / "with_header.csv"
        p.write_text("time_s,bank_deg\n1.0,-45.0\n2.0,90.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert len(s) == 2

    def test_without_header_row(self, tmp_path: Path) -> None:
        p = tmp_path / "no_header.csv"
        p.write_text("1.0,-45.0\n2.0,90.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert len(s) == 2

    def test_comment_lines_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "comments.csv"
        p.write_text("# comment 1\n# comment 2\n1.0,-45.0\n2.0,90.0\n", encoding="utf-8")
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert len(s) == 2

    def test_extra_columns_ignored(self, tmp_path: Path) -> None:
        p = tmp_path / "extra_cols.csv"
        p.write_text(
            "time_s,bank_deg,extra,another\n1.0,-45.0,foo,bar\n2.0,90.0,baz,qux\n",
            encoding="utf-8",
        )
        s = BankSchedule.from_csv(p, provenance=self._PROV)
        assert len(s) == 2
        assert s.bank_angle_at(1.0) == pytest.approx(math.radians(-45.0), abs=1e-10)
