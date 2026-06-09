# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics integrator — :class:`SimulationStepper` (Strategy) and :class:`RK4Stepper`.

Mirrors OpenRocket's ``SimulationStepper`` / ``RK4SimulationStepper`` split: the stepper
advances the state by one time step using a chosen integration scheme, while the engine
decides *when* to step and *which* stepper to use. All the shared physics plumbing (build
flight conditions, query atmosphere/gravity/aero, write the derived output channels) lives
on :class:`SimulationStepper`; :class:`RK4Stepper` adds the classic 4th-order Runge-Kutta
advance.

The equation-of-motion derivative is the central physics seam; see
:meth:`SimulationStepper.compute_derivatives`.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np

from orp.core.aerodynamics.calculator import AerodynamicForces
from orp.core.aerodynamics.flight_conditions import FlightConditions
from orp.core.simulation import flight_data as fd
from orp.core.simulation.status import STATE_SIZE, SimulationStatus

__all__ = ["SimulationStepper", "RK4Stepper"]

#: Standard gravity used only to express deceleration as a "g" load (a reporting unit).
_STANDARD_GRAVITY = 9.80665


class SimulationStepper(ABC):
    """Strategy interface for a one-step physics integrator, plus shared model plumbing.

    Concrete steppers implement :meth:`step`. The base provides everything that is common
    across integration schemes: flight-condition assembly, the aerodynamic/gravity queries,
    the equation-of-motion seam, and writing the derived output channels for a data point.
    """

    def initialize(self, status: SimulationStatus) -> SimulationStatus:
        """Prepare ``status`` for stepping by this stepper; returns the status to use.

        Mirrors OpenRocket's ``initialize``: the engine reassigns its current status to the
        return value whenever it switches steppers. The default is a no-op pass-through.
        """
        return status

    @abstractmethod
    def step(self, status: SimulationStatus, max_time_step: float) -> None:
        """Advance ``status`` in place by at most ``max_time_step`` seconds."""

    # -- shared physics plumbing ----------------------------------------------------------
    def build_flight_conditions(self, status: SimulationStatus) -> FlightConditions:
        """Assemble the momentary :class:`FlightConditions` from ``status`` and the models.

        Pulls the local atmosphere from the planet, the trim angle of attack and reference
        geometry from the vehicle, and the current (replayed) bank angle from the status.
        """
        conditions = status.conditions
        vehicle = conditions.vehicle
        atmosphere = conditions.planet.atmosphere.get_conditions(status.altitude)

        reference_area = vehicle.reference_area.get()
        # Effective reference length (diameter) from the reference area: d = sqrt(4S/pi).
        reference_length = math.sqrt(4.0 * reference_area / math.pi) if reference_area > 0 else 1.0

        return FlightConditions(
            velocity=status.velocity,
            angle_of_attack=vehicle.trim_angle_of_attack.get(),
            atmosphere=atmosphere,
            reference_area=reference_area,
            reference_length=reference_length,
            bank_angle=status.bank_angle,
        )

    def compute_aerodynamic_forces(
        self,
        status: SimulationStatus,
        conditions: FlightConditions,
    ) -> AerodynamicForces:
        """Query the injected aerodynamic calculator for force coefficients."""
        return status.conditions.aerodynamic_calculator.calculate_forces(
            status.conditions.vehicle, conditions
        )

    def compute_derivatives(self, status: SimulationStatus) -> np.ndarray:
        """Return d/dt of the six-element state vector (the equation-of-motion seam).

        --- PHYSICS SEAM ---
        Returns zeros. The real 3-DOF planet-relative equations of motion over a rotating
        spherical planet (state order: altitude h, latitude φ, longitude θ, speed V,
        flight-path angle γ, heading ψ; with bank σ, lift L = C_L·q·S, drag D = C_D·q·S,
        mass m, gravity g, planet rate ω, radius r = R + h) are::

            dh/dt = V·sinγ
            dφ/dt = V·cosγ·cosψ / r
            dθ/dt = V·cosγ·sinψ / (r·cosφ)
            dV/dt = −D/m − g·sinγ
                    + ω²·r·cosφ·(sinγ·cosφ − cosγ·sinφ·cosψ)
            dγ/dt = (1/V)·[ (L·cosσ)/m − g·cosγ + (V²/r)·cosγ
                    + 2·ω·V·cosφ·sinψ
                    + ω²·r·cosφ·(cosγ·cosφ + sinγ·sinφ·cosψ) ]
            dψ/dt = (1/V)·[ (L·sinσ)/(m·cosγ) + (V²/r)·cosγ·sinψ·tanφ
                    − 2·ω·V·(tanγ·cosφ·cosψ − sinφ)
                    + (ω²·r/cosγ)·sinφ·cosφ·sinψ ]

        Everything those equations need is already wired below; only the final assignment is
        a placeholder. Note σ enters solely as a *replayed* control (``status.bank_angle``),
        never as an unknown to solve for — that is the forward-only wall in physics form.
        """
        conditions = status.conditions
        flight_conditions = self.build_flight_conditions(status)
        forces = self.compute_aerodynamic_forces(status, flight_conditions)

        # The quantities the real EOM consume (computed now so the seam is fully wired).
        # Every planet-specific value flows from the injected Planet — nothing is Earth-baked.
        mass = conditions.vehicle.mass.get()  # noqa: F841
        gravity = conditions.planet.gravity.get_gravity(status.world_position())  # noqa: F841
        rotation_rate = conditions.planet.rotation_rate  # noqa: F841  (ω, Coriolis/centrifugal)
        radius = status.radius()  # noqa: F841  (r = planet mean radius + altitude)
        dynamic_pressure = flight_conditions.dynamic_pressure
        reference_area = flight_conditions.reference_area
        drag = forces.drag_force(dynamic_pressure, reference_area)  # noqa: F841
        lift = forces.lift_force(dynamic_pressure, reference_area)  # noqa: F841
        bank = status.bank_angle  # noqa: F841  (replayed control, never solved for)

        # SEAM: replace these zeros with the equations documented above.
        return np.zeros(STATE_SIZE, dtype=float)

    def record_point(self, status: SimulationStatus) -> None:
        """Write one full data row: kinematics (via the status) plus derived physics channels.

        Follows OpenRocket's documented contract — open the point and store the kinematic
        state first, then fill the physics channels into the same row.
        """
        status.store_data()
        branch = status.flight_data_branch
        if branch is None:
            return

        conditions = status.conditions
        flight_conditions = self.build_flight_conditions(status)
        forces = self.compute_aerodynamic_forces(status, flight_conditions)

        dynamic_pressure = flight_conditions.dynamic_pressure
        reference_area = flight_conditions.reference_area
        drag = forces.drag_force(dynamic_pressure, reference_area)
        lift = forces.lift_force(dynamic_pressure, reference_area)
        gravity = conditions.planet.gravity.get_gravity(status.world_position())
        mass = conditions.vehicle.mass.get()
        deceleration_g = drag / (mass * _STANDARD_GRAVITY) if mass > 0 else 0.0

        branch.set_value(fd.TYPE_MACH, flight_conditions.mach)
        branch.set_value(fd.TYPE_DYNAMIC_PRESSURE, dynamic_pressure)
        branch.set_value(fd.TYPE_DENSITY, flight_conditions.atmosphere.density)
        branch.set_value(fd.TYPE_DRAG_FORCE, drag)
        branch.set_value(fd.TYPE_LIFT_FORCE, lift)
        branch.set_value(fd.TYPE_GRAVITY, gravity)
        branch.set_value(fd.TYPE_DECELERATION, deceleration_g)
        # --- PHYSICS SEAM --- stagnation heat rate (Sutton-Graves):
        #   qdot = k * sqrt(rho / R_nose) * V^3,  k_earth ~ 1.7415e-4 (SI).
        branch.set_value(fd.TYPE_HEAT_RATE, 0.0)


class RK4Stepper(SimulationStepper):
    """Classic fixed-order 4th-order Runge-Kutta integrator for the reentry EOM.

    The engine bounds ``max_time_step`` so the stepper never integrates past a termination
    instant; within that bound this performs a standard RK4 advance of the six-element state
    vector. The bank angle is refreshed from the replayed schedule at every sub-step time, so
    a time-varying control is honored mid-step.
    """

    def step(self, status: SimulationStatus, max_time_step: float) -> None:
        """Advance ``status`` by ``max_time_step`` seconds using RK4 (in place)."""
        h = max_time_step
        if not math.isfinite(h) or h <= 0.0:
            return

        schedule = status.conditions.bank_schedule
        y0 = status.to_state_vector()
        t0 = status.time

        k1 = self.compute_derivatives(status)
        k2 = self._derivatives_at(status, y0 + 0.5 * h * k1, t0 + 0.5 * h)
        k3 = self._derivatives_at(status, y0 + 0.5 * h * k2, t0 + 0.5 * h)
        k4 = self._derivatives_at(status, y0 + h * k3, t0 + h)

        y_next = y0 + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        status.load_state_vector(y_next)
        status.time = t0 + h
        status.bank_angle = schedule.bank_angle_at(status.time)

    def _derivatives_at(
        self,
        base_status: SimulationStatus,
        state_vector: np.ndarray,
        time: float,
    ) -> np.ndarray:
        """Evaluate the EOM at a trial (state, time) on a throwaway clone of ``base_status``.

        The clone never writes to the data branch; it exists only to evaluate the derivative
        at an RK sub-point, with the replayed bank angle sampled at the sub-point time.
        """
        trial = base_status.clone()
        trial.load_state_vector(state_vector)
        trial.time = time
        trial.bank_angle = base_status.conditions.bank_schedule.bank_angle_at(time)
        return self.compute_derivatives(trial)
