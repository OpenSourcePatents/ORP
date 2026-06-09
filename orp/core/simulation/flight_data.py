# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trajectory output — the :class:`FlightData` / :class:`FlightDataBranch` column-store.

Mirrors OpenRocket's ``FlightData`` / ``FlightDataBranch`` / ``FlightDataType`` design: a
branch is a column store (one growable array per output channel), filled with the
"append a row, then set the columns of that row" pattern. Channels may appear mid-flight;
earlier rows are back-filled with NaN.

Provenance lives here too: every branch and the top-level :class:`FlightData` carry a
:class:`~orp.core.provenance.tags.ProvenanceTag`, so a trajectory is never read without the
question "how validated is this?" being answerable. The engine sets these to the weakest of
the contributing inputs (see :meth:`SimulationConditions.provenance`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["FlightDataType", "FlightDataBranch", "FlightData"]

_NAN = float("nan")


@dataclass(frozen=True)
class FlightDataType:
    """A flyweight describing one output channel (column).

    Identity is the case-insensitive :attr:`symbol`, so two descriptors with the same symbol
    compare and hash equal (matching OpenRocket's ``FlightDataType`` semantics).

    Attributes:
        symbol: Short key, e.g. ``"h"``, ``"V"``, ``"q"``.
        name: Human-readable channel name.
        unit: SI (or stated) unit string for display/export.
    """

    symbol: str
    name: str
    unit: str = ""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FlightDataType):
            return NotImplemented
        return self.symbol.lower() == other.symbol.lower()

    def __hash__(self) -> int:
        return hash(self.symbol.lower())

    def __str__(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name


# --- Predefined channels for reentry trajectories -----------------------------------------
TYPE_TIME = FlightDataType("t", "Time", "s")
TYPE_ALTITUDE = FlightDataType("h", "Altitude", "m")
TYPE_LATITUDE = FlightDataType("lat", "Latitude", "deg")
TYPE_LONGITUDE = FlightDataType("lon", "Longitude", "deg")
TYPE_VELOCITY = FlightDataType("V", "Velocity", "m/s")
TYPE_FLIGHT_PATH_ANGLE = FlightDataType("gamma", "Flight-path angle", "deg")
TYPE_HEADING = FlightDataType("psi", "Heading", "deg")
TYPE_BANK_ANGLE = FlightDataType("sigma", "Bank angle", "deg")
TYPE_MACH = FlightDataType("M", "Mach number", "")
TYPE_DYNAMIC_PRESSURE = FlightDataType("q", "Dynamic pressure", "Pa")
TYPE_DENSITY = FlightDataType("rho", "Atmospheric density", "kg/m^3")
TYPE_DRAG_FORCE = FlightDataType("D", "Drag force", "N")
TYPE_LIFT_FORCE = FlightDataType("L", "Lift force", "N")
TYPE_DECELERATION = FlightDataType("nload", "Deceleration", "g")
TYPE_GRAVITY = FlightDataType("g", "Gravity", "m/s^2")
TYPE_HEAT_RATE = FlightDataType("qdot", "Stagnation heat rate", "W/m^2")

#: All predefined channels, in a sensible default plotting order.
ALL_TYPES: tuple[FlightDataType, ...] = (
    TYPE_TIME,
    TYPE_ALTITUDE,
    TYPE_LATITUDE,
    TYPE_LONGITUDE,
    TYPE_VELOCITY,
    TYPE_FLIGHT_PATH_ANGLE,
    TYPE_HEADING,
    TYPE_BANK_ANGLE,
    TYPE_MACH,
    TYPE_DYNAMIC_PRESSURE,
    TYPE_DENSITY,
    TYPE_DRAG_FORCE,
    TYPE_LIFT_FORCE,
    TYPE_DECELERATION,
    TYPE_GRAVITY,
    TYPE_HEAT_RATE,
)


@dataclass(frozen=True)
class FlightEvent:
    """A discrete flight event recorded on a branch (entry interface, landing, …)."""

    name: str
    time: float
    data: object = None


class FlightDataBranch:
    """A column store of time-series output for one continuous phase of flight.

    The fill pattern, per step: call :meth:`add_point` once (appends a NaN row to every
    column), then :meth:`set_value` for each channel computed at that instant. Channels added
    after some rows already exist are back-filled with NaN.

    Args:
        name: Branch name (e.g. ``"Reentry"``).
        types: Channels to pre-declare (optional; columns also auto-create on first
            :meth:`set_value`).
    """

    def __init__(self, name: str, types: tuple[FlightDataType, ...] = ()) -> None:
        self.name = name
        self._values: dict[FlightDataType, list[float]] = {}
        self._length: int = 0
        self._mutable: bool = True
        self.events: list[FlightEvent] = []
        #: Provenance of this branch's data (set by the engine to the weakest input).
        self.provenance: ProvenanceTag = ProvenanceTag(ValidationLevel.NOT_VALIDATED)
        for data_type in types:
            self.add_type(data_type)

    # -- mutation -------------------------------------------------------------------------
    def _check_mutable(self) -> None:
        if not self._mutable:
            raise RuntimeError(f"FlightDataBranch {self.name!r} is immutable; cannot modify.")

    def add_type(self, data_type: FlightDataType) -> None:
        """Declare a channel, back-filling existing rows with NaN."""
        self._check_mutable()
        if data_type not in self._values:
            self._values[data_type] = [_NAN] * self._length

    def add_point(self) -> None:
        """Append a new (all-NaN) row to every channel."""
        self._check_mutable()
        self._length += 1
        for column in self._values.values():
            column.append(_NAN)

    def set_value(self, data_type: FlightDataType, value: float) -> None:
        """Set ``value`` for ``data_type`` in the most recent row (auto-creating the column).

        Raises:
            IndexError: if called before any :meth:`add_point`.
        """
        self._check_mutable()
        if self._length == 0:
            raise IndexError("set_value called before add_point; no row to write to.")
        if data_type not in self._values:
            self.add_type(data_type)
        self._values[data_type][-1] = value

    def add_event(self, name: str, time: float, data: object = None) -> None:
        """Record a discrete flight event on this branch."""
        self._check_mutable()
        self.events.append(FlightEvent(name=name, time=time, data=data))

    def immute(self) -> None:
        """Freeze the branch against further modification."""
        self._mutable = False

    # -- access ---------------------------------------------------------------------------
    def get(self, data_type: FlightDataType) -> list[float]:
        """Return the column for ``data_type`` (empty list if the channel is absent)."""
        return list(self._values.get(data_type, []))

    def get_last(self, data_type: FlightDataType) -> float:
        """Return the most recent value of ``data_type`` (NaN if absent/empty)."""
        column = self._values.get(data_type)
        if not column:
            return _NAN
        return column[-1]

    def get_maximum(self, data_type: FlightDataType) -> float:
        """Return the maximum finite value of ``data_type`` (NaN if none)."""
        finite = [v for v in self._values.get(data_type, []) if math.isfinite(v)]
        return max(finite) if finite else _NAN

    def get_minimum(self, data_type: FlightDataType) -> float:
        """Return the minimum finite value of ``data_type`` (NaN if none)."""
        finite = [v for v in self._values.get(data_type, []) if math.isfinite(v)]
        return min(finite) if finite else _NAN

    @property
    def length(self) -> int:
        """Number of recorded rows (time points)."""
        return self._length

    @property
    def is_mutable(self) -> bool:
        """True while the branch may still be modified (cleared by :meth:`immute`)."""
        return self._mutable

    def types(self) -> list[FlightDataType]:
        """The channels present in this branch, sorted by symbol."""
        return sorted(self._values.keys(), key=lambda t: t.symbol.lower())

    def __len__(self) -> int:
        return self._length

    def __repr__(self) -> str:
        return f"FlightDataBranch(name={self.name!r}, length={self._length}, channels={len(self._values)})"


class FlightData:
    """Top-level trajectory result: one or more :class:`FlightDataBranch` plus a summary.

    For reentry there is normally a single branch; the multi-branch container is kept to
    mirror OpenRocket and to allow future phase splits (e.g. parachute deployment).
    """

    def __init__(self, *branches: FlightDataBranch) -> None:
        self._branches: list[FlightDataBranch] = list(branches)
        #: Overall provenance of the run (weakest contributing input). Set by the engine.
        self.provenance: ProvenanceTag = ProvenanceTag(ValidationLevel.NOT_VALIDATED)
        #: Summary scalars, filled by :meth:`calculate_interesting_values`.
        self.summary: dict[str, float] = {}

    def add_branch(self, branch: FlightDataBranch) -> None:
        """Append a :class:`FlightDataBranch` to this result."""
        self._branches.append(branch)

    def get_branch(self, index: int) -> FlightDataBranch:
        """Return the branch at ``index`` (branch 0 is the primary trajectory)."""
        return self._branches[index]

    @property
    def branches(self) -> list[FlightDataBranch]:
        """A shallow copy of the branch list (callers may not mutate the result in place)."""
        return list(self._branches)

    @property
    def branch_count(self) -> int:
        """Number of branches in this result."""
        return len(self._branches)

    def calculate_interesting_values(self) -> None:
        """Derive summary scalars from the primary branch (branch 0).

        Fills :attr:`summary` with flight time, max velocity, min altitude, peak
        deceleration, peak dynamic pressure, and peak heat rate. Safe on empty data (values
        come back NaN). With placeholder physics these reflect whatever the seams produced.

        Forward-only: this deliberately computes only quantities *derived from the integrated
        trajectory*. OpenRocket's analogue additionally derives optimum-altitude / optimum-delay
        scalars; those require an inverse/optimization (solve-for-a-condition) computation and
        are permanently out of scope for ORP — do not add them here.
        """
        if not self._branches or self._branches[0].length == 0:
            return
        primary = self._branches[0]
        self.summary = {
            "flight_time": primary.get_last(TYPE_TIME),
            "max_velocity": primary.get_maximum(TYPE_VELOCITY),
            "min_altitude": primary.get_minimum(TYPE_ALTITUDE),
            "peak_deceleration": primary.get_maximum(TYPE_DECELERATION),
            "peak_dynamic_pressure": primary.get_maximum(TYPE_DYNAMIC_PRESSURE),
            "peak_heat_rate": primary.get_maximum(TYPE_HEAT_RATE),
        }

    def immute(self) -> None:
        """Freeze all branches against further modification."""
        for branch in self._branches:
            branch.immute()

    def __repr__(self) -> str:
        return f"FlightData(branches={self.branch_count}, provenance={self.provenance.level.name})"
