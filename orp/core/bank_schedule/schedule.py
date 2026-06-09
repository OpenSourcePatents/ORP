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

import math
from bisect import bisect_right
from collections.abc import Sequence

from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

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
