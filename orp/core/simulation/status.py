# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The mutable per-instant simulation state.

Mirrors OpenRocket's ``SimulationStatus``: the unit of work that is cloned for Runge-Kutta
sub-steps and carries the integration variables, the phase flags, and references to the
immutable conditions and the output branch.

The integration state for 3-DOF atmospheric reentry over a rotating planet is six scalars —
altitude, latitude, longitude, velocity, flight-path angle, heading — packed into a NumPy
vector for clean RK arithmetic. The bank angle σ is **not** integrated: it is a control,
read each step from the replayed :class:`~orp.core.bank_schedule.schedule.BankSchedule`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from orp.core.planet.planet import WorldCoordinate
from orp.core.simulation import flight_data as fd

if TYPE_CHECKING:
    from orp.core.simulation.conditions import SimulationConditions
    from orp.core.simulation.flight_data import FlightDataBranch

__all__ = [
    "SimulationStatus",
    "STATE_SIZE",
    "IDX_ALTITUDE",
    "IDX_LATITUDE",
    "IDX_LONGITUDE",
    "IDX_VELOCITY",
    "IDX_FLIGHT_PATH_ANGLE",
    "IDX_HEADING",
]

# Ordering of the packed integration state vector.
IDX_ALTITUDE = 0
IDX_LATITUDE = 1
IDX_LONGITUDE = 2
IDX_VELOCITY = 3
IDX_FLIGHT_PATH_ANGLE = 4
IDX_HEADING = 5
STATE_SIZE = 6


class SimulationStatus:
    """Mutable state at one instant of a reentry simulation.

    Attributes:
        time: Simulation time since entry interface, seconds.
        altitude: Altitude above the planet's mean surface, meters.
        latitude: Geodetic latitude, radians.
        longitude: Longitude, radians.
        velocity: Planet-relative speed, m/s.
        flight_path_angle: γ, radians (negative is descending).
        heading: ψ, radians, azimuth measured from north toward east.
        bank_angle: σ, radians — the *replayed* control, refreshed each step.
        landed: Set once the vehicle reaches the ground/termination altitude.
        conditions: The immutable :class:`~orp.core.simulation.conditions.SimulationConditions`.
        flight_data_branch: The output branch this status writes to (shared across clones).
    """

    def __init__(
        self,
        conditions: "SimulationConditions",
        *,
        time: float = 0.0,
        altitude: float = 0.0,
        latitude: float = 0.0,
        longitude: float = 0.0,
        velocity: float = 0.0,
        flight_path_angle: float = 0.0,
        heading: float = 0.0,
        bank_angle: float = 0.0,
        flight_data_branch: "FlightDataBranch | None" = None,
    ) -> None:
        self.conditions = conditions
        self.time = time
        self.altitude = altitude
        self.latitude = latitude
        self.longitude = longitude
        self.velocity = velocity
        self.flight_path_angle = flight_path_angle
        self.heading = heading
        self.bank_angle = bank_angle
        self.landed = False
        self.flight_data_branch = flight_data_branch

    # -- integration-vector view ----------------------------------------------------------
    def to_state_vector(self) -> np.ndarray:
        """Pack the six integration variables into a NumPy vector (see the ``IDX_*`` order)."""
        vector = np.empty(STATE_SIZE, dtype=float)
        vector[IDX_ALTITUDE] = self.altitude
        vector[IDX_LATITUDE] = self.latitude
        vector[IDX_LONGITUDE] = self.longitude
        vector[IDX_VELOCITY] = self.velocity
        vector[IDX_FLIGHT_PATH_ANGLE] = self.flight_path_angle
        vector[IDX_HEADING] = self.heading
        return vector

    def load_state_vector(self, vector: np.ndarray) -> None:
        """Write a packed integration vector back into the named state fields."""
        self.altitude = float(vector[IDX_ALTITUDE])
        self.latitude = float(vector[IDX_LATITUDE])
        self.longitude = float(vector[IDX_LONGITUDE])
        self.velocity = float(vector[IDX_VELOCITY])
        self.flight_path_angle = float(vector[IDX_FLIGHT_PATH_ANGLE])
        self.heading = float(vector[IDX_HEADING])

    # -- derived geometry -----------------------------------------------------------------
    def world_position(self) -> WorldCoordinate:
        """Return the current geodetic position as a :class:`WorldCoordinate`."""
        return WorldCoordinate(
            latitude_rad=self.latitude,
            longitude_rad=self.longitude,
            altitude=self.altitude,
        )

    def radius(self) -> float:
        """Geocentric/areocentric radius (m): planet mean radius + altitude."""
        return self.conditions.planet.mean_radius + self.altitude

    # -- cloning & output -----------------------------------------------------------------
    def clone(self) -> "SimulationStatus":
        """Shallow clone for RK sub-steps: copies scalar state, shares conditions & branch.

        Clones are used only to *evaluate* derivatives at trial sub-points; they never call
        :meth:`store_data`, so sharing the (write-once-per-accepted-step) branch is safe.
        """
        return SimulationStatus(
            self.conditions,
            time=self.time,
            altitude=self.altitude,
            latitude=self.latitude,
            longitude=self.longitude,
            velocity=self.velocity,
            flight_path_angle=self.flight_path_angle,
            heading=self.heading,
            bank_angle=self.bank_angle,
            flight_data_branch=self.flight_data_branch,
        )

    def store_data(self) -> None:
        """Open a new branch row and write the kinematic channels for this instant.

        Mirrors OpenRocket's contract: the new point is added and the current status saved
        into it *first*; the stepper then fills the physics channels into the same row. Angle
        channels are written in degrees for readability.
        """
        branch = self.flight_data_branch
        if branch is None:
            return
        branch.add_point()
        branch.set_value(fd.TYPE_TIME, self.time)
        branch.set_value(fd.TYPE_ALTITUDE, self.altitude)
        branch.set_value(fd.TYPE_LATITUDE, math.degrees(self.latitude))
        branch.set_value(fd.TYPE_LONGITUDE, math.degrees(self.longitude))
        branch.set_value(fd.TYPE_VELOCITY, self.velocity)
        branch.set_value(fd.TYPE_FLIGHT_PATH_ANGLE, math.degrees(self.flight_path_angle))
        branch.set_value(fd.TYPE_HEADING, math.degrees(self.heading))
        branch.set_value(fd.TYPE_BANK_ANGLE, math.degrees(self.bank_angle))

    def __repr__(self) -> str:
        return (
            f"SimulationStatus(t={self.time:.3g}s, h={self.altitude:.4g}m, "
            f"V={self.velocity:.4g}m/s, gamma={math.degrees(self.flight_path_angle):.3g}deg)"
        )
