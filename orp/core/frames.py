# SPDX-License-Identifier: GPL-3.0-or-later
# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
"""Reference-frame conversions for entry states — inertial → planet-relative.

Honest by construction (the pattern of OpenReentry's ``conventions.py``): a conversion
carries its transform and assumptions, and **refuses** (raises :class:`FrameConversionError`)
rather than guessing when the data needed to convert is missing. ORP's canonical entry state
is planet-relative; published entry-interface states are frequently *inertial*, and near
escape speed the planet-rotation correction is first-order, so the conversion must be
explicit and frame-tagged. Frame mixing without an explicit conversion step is an error.

Forward-only: this converts a *given* entry state between frames. It never solves for a state
to hit a target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orp.core.planet.planet import Planet

__all__ = [
    "Frame",
    "FrameConversionError",
    "ConvertedEntryState",
    "inertial_to_planet_relative",
    "great_circle_bearing",
]


class Frame(Enum):
    """The reference frame a kinematic quantity is expressed in."""

    INERTIAL = "inertial"
    PLANET_RELATIVE = "planet_relative"

    def __str__(self) -> str:
        return self.value


class FrameConversionError(ValueError):
    """Raised when a frame conversion lacks the data to proceed — it refuses, never guesses."""


@dataclass(frozen=True)
class ConvertedEntryState:
    """A planet-relative entry state produced by a frame conversion, carrying its provenance.

    Attributes:
        velocity: Planet-relative speed, m/s.
        flight_path_angle: γ, radians, negative descending, relative frame.
        heading: ψ, radians, clockwise from north, in ``[0, 2π)``, relative frame.
        frame: The frame of these values (always :attr:`Frame.PLANET_RELATIVE` here).
        transform: Human-readable description of the transform applied.
        assumptions: The assumptions the transform made (for audit).
    """

    velocity: float
    flight_path_angle: float
    heading: float
    frame: Frame
    transform: str
    assumptions: tuple[str, ...] = ()


def inertial_to_planet_relative(
    planet: "Planet",
    *,
    velocity: float | None,
    flight_path_angle: float | None,
    heading: float | None,
    latitude: float | None,
    altitude: float | None,
) -> ConvertedEntryState:
    """Convert an inertial entry state to planet-relative by subtracting planet rotation.

    Subtracts the planet's eastward surface velocity ``v_rot = ω·(R+h)·cos(lat)`` from the
    eastward component of the (horizontal) inertial velocity vector, then recomposes the
    relative speed, flight-path angle, and heading. The vertical component is frame-invariant.

    All angles are radians; heading is clockwise from north. Every argument is required; any
    that is ``None`` causes a refusal (:class:`FrameConversionError`) — the conversion never
    guesses missing data.

    Args:
        planet: Supplies ``rotation_rate`` (ω) and ``mean_radius`` (R).
        velocity: Inertial speed, m/s.
        flight_path_angle: Inertial flight-path angle, radians (negative descending).
        heading: Inertial heading/azimuth, radians clockwise from north.
        latitude: Geodetic latitude, radians.
        altitude: Altitude above the mean radius, m.

    Returns:
        A planet-relative :class:`ConvertedEntryState`.

    Raises:
        FrameConversionError: if any required quantity is ``None``.
    """
    for name, val in (
        ("velocity", velocity),
        ("flight_path_angle", flight_path_angle),
        ("heading", heading),
        ("latitude", latitude),
        ("altitude", altitude),
    ):
        if val is None:
            raise FrameConversionError(
                f"inertial→planet-relative needs {name!r} to subtract planet rotation; "
                "refusing to guess (frame mixing without an explicit conversion is an error)"
            )

    omega = planet.rotation_rate
    r = planet.mean_radius + altitude
    v_rot = omega * r * math.cos(latitude)  # eastward surface speed of the rotating planet

    v_horizontal = velocity * math.cos(flight_path_angle)
    v_vertical = velocity * math.sin(flight_path_angle)  # frame-invariant
    v_north = v_horizontal * math.cos(heading)
    v_east = v_horizontal * math.sin(heading) - v_rot  # remove the frame's eastward motion

    v_horizontal_rel = math.hypot(v_north, v_east)
    v_rel = math.hypot(v_horizontal_rel, v_vertical)
    gamma_rel = math.atan2(v_vertical, v_horizontal_rel)
    heading_rel = math.atan2(v_east, v_north) % (2.0 * math.pi)

    return ConvertedEntryState(
        velocity=v_rel,
        flight_path_angle=gamma_rel,
        heading=heading_rel,
        frame=Frame.PLANET_RELATIVE,
        transform=(
            "inertial→planet-relative: subtract eastward planet rotation from the horizontal "
            "velocity vector, recompose speed/FPA/heading"
        ),
        assumptions=(
            f"v_rot={v_rot:.2f} m/s eastward (ω·r·cos(lat)) at lat={math.degrees(latitude):.5f}°, "
            f"alt={altitude / 1000.0:.1f} km",
            "rigid-planet rotation; geodetic latitude used for cos(lat) (geocentric difference neglected)",
            "horizontal velocity decomposed into north/east; vertical component frame-invariant",
        ),
    )


def great_circle_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2.

    All arguments in radians. Returns radians clockwise from north in ``[0, 2π)``. Used to
    relate a converted relative heading to the bearing toward a known landing point — a
    forward diagnostic (crossrange is an output), never a target solve.
    """
    d_lon = lon2 - lon1
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return math.atan2(y, x) % (2.0 * math.pi)
