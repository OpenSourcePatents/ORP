# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The bank-angle schedule: σ(t), interpolated and replayed.

FORWARD-ONLY WALL
=================
A :class:`BankSchedule` is a **pre-recorded control input**. The only question it answers
is "what is the commanded bank angle at time t?" — :meth:`BankSchedule.bank_angle_at`.

It deliberately exposes **no** way to go the other direction. There is no constructor, no
method, and no factory anywhere in ORP that accepts a desired landing point (or any
terminal condition) and returns a schedule. That is the inverse guidance/targeting problem
and it is permanently out of scope for ORP. Trajectories are produced by *replaying* a
schedule forward through :class:`~orp.core.simulation.engine.SimulationEngine`, full stop.

If you find yourself wanting "give me the schedule that lands here," stop: that function
must not exist in this codebase. Raise, do not compute.
"""

from __future__ import annotations

import csv as _csv
import math
from bisect import bisect_right
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    import os

__all__ = ["BankSchedule"]


class BankSchedule:
    """A time history of commanded bank angle σ(t), replayed by linear interpolation.

    The schedule is sampled at ``times`` (seconds since entry) with bank angle ``bank_angles``
    (radians). :meth:`bank_angle_at` returns the piecewise-linear interpolation, clamped to
    the endpoints outside the sampled range (constant extrapolation).

    A schedule carries its own :class:`~orp.core.provenance.tags.ProvenanceTag`: it is a
    contributing input to the trajectory exactly like the vehicle's mass or the atmosphere
    model, so it must degrade the run's weakest-link provenance. The default is
    ``NOT_VALIDATED`` (an unsourced, hand-built control history); a schedule replayed from
    real telemetry should be tagged ``VERIFIED_FLIGHT`` with a source. This is *not* a
    crack in the forward-only wall: provenance describes how trustworthy the replayed
    history is, never how it was produced.

    Args:
        times: Strictly increasing sample times, seconds. Must be non-empty.
        bank_angles: Bank angle at each sample time, radians. Same length as ``times``.
        provenance: How this control history was validated/sourced. Defaults to
            ``NOT_VALIDATED``.

    Raises:
        ValueError: if the inputs are empty, mismatched in length, or ``times`` is not
            strictly increasing.
    """

    def __init__(
        self,
        times: Sequence[float],
        bank_angles: Sequence[float],
        *,
        provenance: ProvenanceTag | None = None,
    ) -> None:
        times = list(times)
        bank_angles = list(bank_angles)

        if not times:
            raise ValueError("BankSchedule requires at least one sample point.")
        if len(times) != len(bank_angles):
            raise ValueError(
                f"times and bank_angles must be equal length "
                f"(got {len(times)} and {len(bank_angles)})."
            )
        for earlier, later in zip(times, times[1:]):
            if later <= earlier:
                raise ValueError("BankSchedule times must be strictly increasing.")

        self._times: list[float] = times
        self._bank_angles: list[float] = bank_angles
        #: Provenance of this control history (folded into the trajectory's weakest-link tag).
        self.provenance: ProvenanceTag = (
            provenance
            if provenance is not None
            else ProvenanceTag(
                ValidationLevel.NOT_VALIDATED,
                notes="Unsourced bank-angle control history.",
            )
        )

    def bank_angle_at(self, time: float) -> float:
        """Return the commanded bank angle σ (radians) at ``time`` (seconds since entry).

        This is the schedule's sole purpose: a pure, forward replay of the control history.
        Before the first / after the last sample, the nearest endpoint value is held
        (constant extrapolation).

        Args:
            time: Simulation time in seconds since entry interface.

        Returns:
            The interpolated bank angle in radians.
        """
        times = self._times
        angles = self._bank_angles

        if time <= times[0]:
            return angles[0]
        if time >= times[-1]:
            return angles[-1]

        # Locate the interval [i-1, i] containing `time` and linearly interpolate.
        i = bisect_right(times, time)
        t0, t1 = times[i - 1], times[i]
        a0, a1 = angles[i - 1], angles[i]
        fraction = (time - t0) / (t1 - t0)
        return a0 + (a1 - a0) * fraction

    @property
    def duration(self) -> float:
        """Span of the schedule, seconds (last sample time − first sample time)."""
        return self._times[-1] - self._times[0]

    @property
    def times(self) -> tuple[float, ...]:
        """The sample times (seconds), as an immutable tuple."""
        return tuple(self._times)

    @property
    def bank_angles(self) -> tuple[float, ...]:
        """The sampled bank angles (radians), as an immutable tuple."""
        return tuple(self._bank_angles)

    def __len__(self) -> int:
        return len(self._times)

    def __repr__(self) -> str:
        return f"BankSchedule(n={len(self._times)}, duration={self.duration:.3g}s)"

    @classmethod
    def constant(
        cls,
        bank_angle: float,
        *,
        duration: float = 0.0,
        provenance: ProvenanceTag | None = None,
    ) -> "BankSchedule":
        """Create a constant-bank schedule (e.g. a pure ballistic or fixed-lift entry).

        Args:
            bank_angle: The fixed bank angle, radians.
            duration: Optional positive span; a two-point schedule is created so the
                duration is well-defined. With the default (0) a single-sample schedule is
                created (constant for all time).
            provenance: Provenance of this control history (default ``NOT_VALIDATED``).
        """
        if duration > 0.0:
            return cls([0.0, duration], [bank_angle, bank_angle], provenance=provenance)
        return cls([0.0], [bank_angle], provenance=provenance)

    @classmethod
    def from_degrees(
        cls,
        times: Sequence[float],
        bank_angles_deg: Sequence[float],
        *,
        provenance: ProvenanceTag | None = None,
    ) -> "BankSchedule":
        """Create a schedule from bank angles given in degrees (converted to radians)."""
        return cls(times, [math.radians(a) for a in bank_angles_deg], provenance=provenance)

    @classmethod
    def from_csv(
        cls,
        path: "str | os.PathLike[str]",
        *,
        provenance: ProvenanceTag,
    ) -> "BankSchedule":
        """Load a two-column CSV of (time_s, bank_angle_deg) and return a BankSchedule.

        The CSV must have exactly two data columns: time in seconds (column 1) and bank
        angle in degrees (column 2). Extra columns are ignored. A single header row is
        auto-detected (if the first cell cannot be parsed as a number the row is treated as
        a header and skipped). Lines whose first non-whitespace character is ``#`` are
        treated as comments and ignored.

        **Angle convention.** Angles may be given on either the −180..180 or the 0..360
        degree convention; the convention is auto-detected from the data and recorded in
        the provenance notes. The schedule is normalised internally to the −180..180
        convention (i.e. values in (180, 360] are shifted by −360°) before converting to
        radians.

        **Strict validation — the method refuses rather than repairs.**

        Raises:
            TypeError: if ``provenance`` is not supplied (it is keyword-only with no
                default and is mandatory).
            ValueError: for any of the following:
                - A cell in the time or angle column is blank or cannot be parsed as a
                  number (including cells that contain ``NaN`` or ``Inf`` literals).
                - A cell value is a float NaN or infinity after parsing.
                - A time value appears more than once (duplicate timestamps).
                - The time column is not strictly increasing (non-monotonic).
                - A row whose angle cell contains the literal text ``GAP`` (case-
                  insensitive) or a row flagged as a gap/occluded sample — the caller
                  must filter gap rows before passing the file to this method.
                - The file contains no data rows (after comment and header stripping).

        Args:
            path: Path to the CSV file (``str`` or ``pathlib.Path``).
            provenance: Mandatory provenance tag describing the source and validation
                status of this control history. There is no default; callers must supply
                one explicitly.

        Returns:
            A :class:`BankSchedule` with times in seconds and bank angles in radians,
            normalised to the −180..180 convention. The supplied ``provenance`` is
            preserved but its ``notes`` field is augmented with the detected angle
            convention.
        """
        path = Path(path)
        times: list[float] = []
        angles_deg: list[float] = []
        header_skipped = False

        with path.open(encoding="utf-8", newline="") as f:
            reader = _csv.reader(f)
            for lineno, row in enumerate(reader, start=1):
                # Skip comment lines (first non-whitespace character is #).
                if not row or row[0].lstrip().startswith("#"):
                    continue
                if len(row) < 2:
                    raise ValueError(
                        f"Row {lineno} in {path.name!r} has fewer than 2 columns; "
                        "expected time_s and bank_angle_deg."
                    )

                raw_t = row[0].strip()
                raw_a = row[1].strip()

                # Auto-detect header: if time cell is non-numeric on the very first data
                # row, treat it as a header and skip it (only once).
                if not header_skipped and not _is_numeric(raw_t):
                    header_skipped = True
                    continue

                # --- time cell ---
                if not raw_t:
                    raise ValueError(
                        f"Row {lineno} in {path.name!r}: time cell is blank. "
                        "Blank cells are not accepted; filter or remove the row."
                    )
                t = _parse_float(raw_t, "time", lineno, path.name)

                # --- angle cell ---
                if not raw_a:
                    raise ValueError(
                        f"Row {lineno} in {path.name!r}: bank angle cell is blank at "
                        f"t={raw_t} s. Blank cells are not accepted; do not interpolate "
                        "over gaps — filter or remove the row before loading."
                    )
                # Reject literal gap markers.
                if raw_a.lower() in ("gap", "gap_occluded", "occluded", "nan", "inf",
                                     "-inf", "+inf"):
                    raise ValueError(
                        f"Row {lineno} in {path.name!r}: bank angle cell contains "
                        f"{raw_a!r} at t={raw_t} s. Marked gaps and non-finite markers "
                        "are not accepted. Remove or filter these rows before loading."
                    )
                a = _parse_float(raw_a, "bank angle", lineno, path.name)

                times.append(t)
                angles_deg.append(a)

        if not times:
            raise ValueError(
                f"No data rows found in {path.name!r}. "
                "The file must contain at least one numeric time/angle pair."
            )

        # --- duplicate timestamp check ---
        seen: set[float] = set()
        for i, t in enumerate(times):
            if t in seen:
                raise ValueError(
                    f"Duplicate timestamp {t} s found in {path.name!r}. "
                    "Each time value must appear exactly once."
                )
            seen.add(t)

        # --- monotonicity check ---
        for i in range(1, len(times)):
            if times[i] <= times[i - 1]:
                raise ValueError(
                    f"Non-monotonic time at index {i} in {path.name!r}: "
                    f"{times[i - 1]} s followed by {times[i]} s. "
                    "Time values must be strictly increasing."
                )

        # --- angle-convention detection ---
        has_negative = any(a < 0.0 for a in angles_deg)
        has_above_180 = any(a > 180.0 for a in angles_deg)

        if has_negative and has_above_180:
            raise ValueError(
                f"Angle values in {path.name!r} are inconsistent: some are negative and "
                "some exceed 180 deg. Cannot determine a single convention (-180..180 or "
                "0..360). Normalise the angles to one convention before loading."
            )

        if has_above_180:
            convention_note = (
                "Angle convention detected: 0..360 degrees (values exceed 180 deg); "
                "normalised internally to the -180..180 convention."
            )
            angles_deg = [a - 360.0 if a > 180.0 else a for a in angles_deg]
        elif has_negative:
            convention_note = (
                "Angle convention detected: -180..180 degrees (negative values present); "
                "no normalisation needed."
            )
        else:
            # All angles in [0, 180]: ambiguous — assume -180..180 (no shift needed).
            convention_note = (
                "Angle convention: all values in [0, 180] — ambiguous. "
                "Assumed -180..180 (no normalisation applied)."
            )

        # Augment the provenance notes with the detected convention.
        aug_notes = (
            (provenance.notes + " " if provenance.notes else "") + convention_note
        ).strip()
        augmented_provenance = ProvenanceTag(
            level=provenance.level,
            source=provenance.source,
            notes=aug_notes,
        )

        bank_angles_rad = [math.radians(a) for a in angles_deg]
        return cls(times, bank_angles_rad, provenance=augmented_provenance)


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _is_numeric(text: str) -> bool:
    """Return True if *text* can be parsed as a float."""
    try:
        float(text)
        return True
    except (ValueError, TypeError):
        return False


def _parse_float(text: str, field: str, lineno: int, filename: str) -> float:
    """Parse *text* as a float; raise ValueError with a plain-language message on failure.

    Also rejects NaN and infinite values even if they parse successfully.
    """
    try:
        value = float(text)
    except ValueError:
        raise ValueError(
            f"Row {lineno} in {filename!r}: {field} cell {text!r} cannot be parsed as a "
            "number. Remove or fix the cell before loading."
        ) from None
    if math.isnan(value):
        raise ValueError(
            f"Row {lineno} in {filename!r}: {field} cell {text!r} is NaN. "
            "NaN values are not accepted."
        )
    if math.isinf(value):
        raise ValueError(
            f"Row {lineno} in {filename!r}: {field} cell {text!r} is infinite. "
            "Infinite values are not accepted."
        )
    return value
