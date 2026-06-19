# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Modified Newtonian aerodynamics — the reentry-default calculator.

Modified Newtonian theory is the standard first-order method for hypersonic blunt-body
aerodynamics: surface pressure follows ``Cp = Cp_max · cos²θ`` where θ is the angle between
the freestream and the local *inward* surface normal (windward panels only; the lee side
sees ``Cp = 0``), and ``Cp_max`` is the stagnation pressure coefficient behind a normal shock
(from the Rayleigh pitot formula). Integrating that pressure law over the body's wetted
geometry yields the axial and normal coefficients, hence C_D, C_L, and L/D.

The body is modelled as a sphere-cone: a spherical nose cap (radius ``R_n``) blending into a
conical frustum of half-angle ``θ_c`` out to the base radius ``R_b = √(S/π)``. When the nose
radius is large enough that the sphere reaches the base before the cone tangency (a capsule
like Apollo), the body is a pure spherical segment and no cone is integrated.

Note on L/D: in Newtonian flow C_L and C_D are both proportional to ``Cp_max``, so **L/D is
independent of Mach** — it is a purely geometric function of the body shape and angle of
attack. ``Cp_max`` (hence Mach) sets the *magnitude* of the coefficients, not the ratio.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

if TYPE_CHECKING:
    from orp.core.aerodynamics.flight_conditions import FlightConditions
    from orp.core.vehicles.base import EntryVehicle

__all__ = ["ModifiedNewtonianCalculator", "stagnation_pressure_coefficient"]


def stagnation_pressure_coefficient(mach: float, gamma: float) -> float:
    """Return the stagnation (maximum) pressure coefficient ``Cp_max`` behind a normal shock.

    For supersonic/hypersonic flow this is the Rayleigh pitot result::

        p02/p∞ = [ (γ+1)²·M² / (4γ·M² − 2(γ−1)) ]^(γ/(γ−1)) · (1 − γ + 2γ·M²)/(γ+1)
        Cp_max = (p02/p∞ − 1) / (½·γ·M²)

    For subsonic flow the isentropic stagnation ratio is used; as M → 0, Cp_max → 1
    (incompressible). As M → ∞, Cp_max → a finite limit (≈1.839 for γ = 1.4).

    Args:
        mach: Freestream Mach number.
        gamma: Ratio of specific heats of the local gas (air ≈ 1.4, Mars CO₂ ≈ 1.29).
    """
    if mach < 1e-6:
        return 1.0
    if mach < 1.0:
        # Subsonic: isentropic stagnation pressure ratio.
        ratio = (1.0 + 0.5 * (gamma - 1.0) * mach * mach) ** (gamma / (gamma - 1.0))
    else:
        # Supersonic/hypersonic: Rayleigh pitot (normal-shock) stagnation pressure ratio.
        term1 = ((gamma + 1.0) ** 2 * mach * mach) / (4.0 * gamma * mach * mach - 2.0 * (gamma - 1.0))
        term2 = (1.0 - gamma + 2.0 * gamma * mach * mach) / (gamma + 1.0)
        ratio = term1 ** (gamma / (gamma - 1.0)) * term2
    return (ratio - 1.0) / (0.5 * gamma * mach * mach)


def _midpoints(a: float, b: float, n: int) -> tuple[np.ndarray, float]:
    """Midpoint sample centres over ``[a, b]`` and the (uniform) cell width."""
    edges = np.linspace(a, b, n + 1)
    return 0.5 * (edges[:-1] + edges[1:]), (b - a) / n


@lru_cache(maxsize=2048)
def _geometry_factors(
    nose_radius: float,
    base_radius: float,
    half_cone_angle: float,
    alpha: float,
    n_ang: int = 90,
    n_phi: int = 180,
) -> tuple[float, float, float, float]:
    """Newtonian surface integral over a sphere-cone with ``Cp_max = 1``.

    Returns the geometry-only coefficient factors (drag, lift, axial, normal); the full
    coefficients are these times ``Cp_max``. Because the integral is linear in ``Cp_max`` and
    depends only on geometry and angle of attack — both constant through a trimmed entry — the
    result is cached, so the costly surface integral runs once per (geometry, α) rather than
    every integration sub-step.

    Axes: body x is axial (nose→base, downstream); the freestream direction (air relative to
    the body) is ``V̂ = (cosα, 0, sinα)``. Lift is taken along ``(sinα, 0, −cosα)`` so that a
    positive (trim) angle of attack yields positive lift — the entry-vehicle convention in
    which a zero bank angle (σ=0) places lift in the local "up" direction in the EOM. Pressure
    pushes along the inward normal, so each windward panel contributes ``Cp·(−n̂)·dA``.
    """
    v_hat = np.array([math.cos(alpha), 0.0, math.sin(alpha)])
    lift_hat = np.array([math.sin(alpha), 0.0, -math.cos(alpha)])
    force = np.zeros(3)

    tangency_lambda = 0.5 * math.pi - half_cone_angle
    tangency_radius = nose_radius * math.cos(half_cone_angle)  # = R_n·sin(λ_t)

    # Spherical nose cap: λ is the polar angle from the stagnation axis (−x).
    has_cone = half_cone_angle > 1e-3 and base_radius > tangency_radius
    if has_cone:
        lambda_max = tangency_lambda
    else:
        lambda_max = math.asin(min(base_radius / nose_radius, 1.0))

    lam_c, dlam = _midpoints(0.0, lambda_max, n_ang)
    phi_c, dphi = _midpoints(0.0, 2.0 * math.pi, n_phi)
    lam, phi = np.meshgrid(lam_c, phi_c, indexing="ij")
    nx = -np.cos(lam)
    ny = np.sin(lam) * np.cos(phi)
    nz = np.sin(lam) * np.sin(phi)
    cos_theta = -(v_hat[0] * nx + v_hat[1] * ny + v_hat[2] * nz)
    cp = np.clip(cos_theta, 0.0, None) ** 2  # Cp with Cp_max factored out (= 1)
    d_area = nose_radius * nose_radius * np.sin(lam) * dlam * dphi
    force[0] += float(np.sum(cp * (-nx) * d_area))
    force[1] += float(np.sum(cp * (-ny) * d_area))
    force[2] += float(np.sum(cp * (-nz) * d_area))

    # Conical frustum from the tangency ring out to the base radius.
    if has_cone:
        r_c, dr = _midpoints(tangency_radius, base_radius, n_ang)
        r, phi = np.meshgrid(r_c, phi_c, indexing="ij")
        sin_c, cos_c = math.sin(half_cone_angle), math.cos(half_cone_angle)
        nx = np.full_like(phi, -sin_c)
        ny = cos_c * np.cos(phi)
        nz = cos_c * np.sin(phi)
        cos_theta = -(v_hat[0] * nx + v_hat[1] * ny + v_hat[2] * nz)
        cp = np.clip(cos_theta, 0.0, None) ** 2  # Cp with Cp_max factored out (= 1)
        d_area = r * (dr / sin_c) * dphi  # slant area element = r · ds · dφ, ds = dr/sinθc
        force[0] += float(np.sum(cp * (-nx) * d_area))
        force[1] += float(np.sum(cp * (-ny) * d_area))
        force[2] += float(np.sum(cp * (-nz) * d_area))

    force /= math.pi * base_radius * base_radius  # reference area S = π·R_b²
    drag = float(force @ v_hat)
    lift = float(force @ lift_hat)
    axial = float(force[0])
    normal = float(force[2])
    return drag, lift, axial, normal


class ModifiedNewtonianCalculator(AerodynamicCalculator):
    """Modified Newtonian hypersonic aerodynamics for axisymmetric sphere-cone blunt bodies.

    Args:
        stall_angle: Angle of attack (radians) beyond which results are flagged invalid.
            Defaults to 180° (Newtonian theory itself imposes no stall).
    """

    def __init__(self, stall_angle: float = math.pi) -> None:
        self._stall_angle = stall_angle

    def calculate_forces(
        self,
        vehicle: "EntryVehicle",
        conditions: "FlightConditions",
    ) -> AerodynamicForces:
        """Compute Modified Newtonian force coefficients for ``vehicle`` at ``conditions``.

        Uses the vehicle's nose radius, base radius (from the reference area), and forebody
        half-cone angle; ``Cp_max`` comes from the Rayleigh pitot formula at the current Mach
        and the local gas's ratio of specific heats. Coefficients are referenced to the
        vehicle reference area; the pitching moment is left at zero (a CG-dependent refinement).
        """
        nose_radius = vehicle.nose_radius.get()
        reference_area = vehicle.reference_area.get()
        half_cone_angle = vehicle.half_cone_angle.get()
        gamma = conditions.atmosphere.specific_heat_ratio
        mach = conditions.mach
        alpha = conditions.angle_of_attack

        if nose_radius <= 0.0 or reference_area <= 0.0:
            return AerodynamicForces(provenance=self.provenance)

        base_radius = math.sqrt(reference_area / math.pi)
        # Newtonian Cp_max scales the coefficients; if Mach is unknown (0), use the
        # hypersonic-limit value so L/D (Mach-independent) is still correct.
        gamma_eff = gamma if gamma > 1.0 else 1.4
        cp_max = stagnation_pressure_coefficient(mach, gamma_eff) if mach > 0.0 else (
            stagnation_pressure_coefficient(50.0, gamma_eff)
        )

        # Geometry-only integral (cached); coefficients are these factors × Cp_max.
        drag_factor, lift_factor, _axial, _normal = _geometry_factors(
            nose_radius, base_radius, half_cone_angle, alpha
        )

        return AerodynamicForces(
            drag_coefficient=cp_max * drag_factor,
            lift_coefficient=cp_max * lift_factor,
            side_coefficient=0.0,
            pitching_moment_coefficient=0.0,
            provenance=self.provenance,
        )

    def get_stall_angle(self) -> float:
        return self._stall_angle

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.VERIFIED_SOURCE,
            source="Modified Newtonian theory (Anderson, Hypersonic and High-Temperature Gas Dynamics)",
            notes=(
                "Implemented from Anderson's published Modified Newtonian formulation; no CFD "
                "or wind-tunnel comparison was performed by this project. In the literature, "
                "Modified Newtonian agrees well with CFD/wind-tunnel for blunt-body hypersonic "
                "C_D and L/D, and is least accurate on lee sides and at low Mach."
            ),
        )
