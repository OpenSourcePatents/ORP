# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Invariant tests for the 3-DOF rotating-planet equations of motion.

These tests pin down the *mathematical structure* of
:meth:`~orp.core.simulation.stepper.SimulationStepper.compute_derivatives` rather than
end-to-end trajectory behaviour:

1. **No Coriolis term in dV/dt.** The Coriolis acceleration ``−2ω×V`` is perpendicular to
   the planet-relative velocity, so it does no work and must not appear in the speed
   equation. Coriolis terms are linear (odd) in ω while centrifugal terms are quadratic
   (even), so dV/dt must be an *even* function of ω, while dγ/dt and dψ/dt must carry the
   exact analytic odd (Coriolis) parts.
2. **Equatorial circular orbit hold.** In vacuum over a rotating planet with central
   μ/r² gravity, an eastward equatorial state with planet-relative speed
   ``V = √(μ/r) − ω·r`` is an exact fixed point of (h, V, γ): the ω²r centrifugal terms
   and the 2ωV Coriolis term must cancel gravity and curvature exactly. Absent
   centrifugal terms, the orbit drifts within steps.
3. **Jacobi energy conservation.** For vacuum flight over a rotating planet with central
   gravity, ``E = V²/2 − μ/r − ½·ω²·r²·cos²φ`` is the conserved Jacobi (rotating-frame)
   energy; the integrated drift must be at integrator-roundoff level.
4. **ω = 0 reduction.** With rotation off, the derivatives must equal the standard
   non-rotating planet-relative entry set, term for term, on a sampled state grid.
"""

from __future__ import annotations

import itertools
import math

import pytest

from orp.core.aerodynamics.calculator import AerodynamicCalculator, AerodynamicForces
from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.bank_schedule import BankSchedule
from orp.core.gravity.model import GravityModel
from orp.core.planet.planet import Planet, WorldCoordinate
from orp.core.provenance.tags import ProvenanceTag, TaggedValue, ValidationLevel
from orp.core.simulation import SimulationConditions
from orp.core.simulation.status import (
    IDX_ALTITUDE,
    IDX_FLIGHT_PATH_ANGLE,
    IDX_HEADING,
    IDX_LATITUDE,
    IDX_LONGITUDE,
    IDX_VELOCITY,
    SimulationStatus,
)
from orp.core.simulation.stepper import RK4Stepper

# Earth-like constants for the synthetic test planet (central gravity, no atmosphere).
_MU = 3.986_004_418e14  # m³/s²
_RADIUS = 6_371_000.0  # m
_OMEGA = 7.292_115e-5  # rad/s


class _VacuumAtmosphere(AtmosphericModel):
    """Zero-density atmosphere: isolates the EOM's gravity/rotation terms."""

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        return AtmosphericConditions(
            temperature=0.0, pressure=0.0, specific_gas_constant=0.0, specific_heat_ratio=0.0
        )

    def get_max_altitude(self) -> float:
        return float("inf")

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "vacuum (test fixture)")


class _UniformDensityAtmosphere(AtmosphericModel):
    """Constant-density atmosphere so aero terms are exercised with a known ρ."""

    def __init__(self, density: float, *, gas_constant: float = 287.0528, gamma: float = 1.4) -> None:
        self._rho = density
        self._r = gas_constant
        self._gamma = gamma

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        temperature = 250.0
        return AtmosphericConditions(
            temperature=temperature,
            pressure=self._rho * self._r * temperature,
            specific_gas_constant=self._r,
            specific_heat_ratio=self._gamma,
        )

    def get_max_altitude(self) -> float:
        return float("inf")

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "uniform density (test fixture)")


class _CentralGravity(GravityModel):
    """Exact inverse-square central gravity g = μ/(R+h)² (matches the EOM's r)."""

    def __init__(self, mu: float, mean_radius: float) -> None:
        self._mu = mu
        self._mean_radius = mean_radius

    def get_gravity(self, position: WorldCoordinate) -> float:
        r = self._mean_radius + position.altitude
        return self._mu / (r * r)

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "central μ/r² (test fixture)")


class _ConstantAero(AerodynamicCalculator):
    """Constant C_D / C_L calculator (EOM tests must not depend on the aero seam)."""

    def __init__(self, drag_coefficient: float, lift_coefficient: float) -> None:
        self._cd = drag_coefficient
        self._cl = lift_coefficient

    def calculate_forces(self, vehicle, conditions) -> AerodynamicForces:  # type: ignore[no-untyped-def]
        return AerodynamicForces(
            drag_coefficient=self._cd,
            lift_coefficient=self._cl,
            provenance=self.provenance,
        )

    def get_stall_angle(self) -> float:
        return math.pi

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "test constant coefficients")


def _test_vehicle(mass: float = 1200.0, area: float = 4.0):
    """A minimal provenance-tagged vehicle for EOM evaluation."""
    from orp.core.vehicles.base import EntryVehicle

    def tv(value: float, unit: str = "") -> TaggedValue[float]:
        return TaggedValue.asserted(value, "EOM invariant test fixture", unit=unit)

    return EntryVehicle(
        name="EOM test body",
        mass=tv(mass, "kg"),
        reference_area=tv(area, "m^2"),
        nose_radius=tv(1.0, "m"),
        drag_coefficient=tv(1.5),
        lift_to_drag=tv(0.3),
        trim_angle_of_attack=tv(0.0, "rad"),
        half_cone_angle=tv(1.2217, "rad"),
    )


def _make_planet(
    omega: float,
    *,
    atmosphere: AtmosphericModel | None = None,
    mu: float = _MU,
    radius: float = _RADIUS,
) -> Planet:
    return Planet(
        name="TestPlanet",
        atmosphere=atmosphere if atmosphere is not None else _VacuumAtmosphere(),
        gravity=_CentralGravity(mu, radius),
        mean_radius=radius,
        rotation_rate=omega,
        gravitational_parameter=mu,
    )


def _make_status(
    planet: Planet,
    *,
    altitude: float,
    latitude: float,
    longitude: float,
    velocity: float,
    gamma: float,
    heading: float,
    bank: float = 0.0,
    aero: AerodynamicCalculator | None = None,
) -> SimulationStatus:
    conditions = SimulationConditions(
        vehicle=_test_vehicle(),
        planet=planet,
        bank_schedule=BankSchedule.constant(bank),
        aerodynamic_calculator=aero if aero is not None else _ConstantAero(0.0, 0.0),
    )
    return SimulationStatus(
        conditions,
        altitude=altitude,
        latitude=latitude,
        longitude=longitude,
        velocity=velocity,
        flight_path_angle=gamma,
        heading=heading,
        bank_angle=bank,
    )


# A modest grid of dynamically distinct states (away from the pole/vertical guards).
_STATE_GRID = list(
    itertools.product(
        (math.radians(-55.0), math.radians(-10.0), 0.0, math.radians(28.5), math.radians(65.0)),  # φ
        (math.radians(-25.0), math.radians(-5.0), 0.0, math.radians(12.0)),  # γ
        (math.radians(0.0), math.radians(47.0), math.radians(90.0), math.radians(213.0)),  # ψ
        (450.0, 3200.0, 7800.0),  # V
    )
)


class TestNoCoriolisInSpeedEquation:
    """Test 1 — structural: dV/dt carries no Coriolis (2ωV) term.

    The Coriolis acceleration −2ω×V is perpendicular to the planet-relative velocity and
    does no work, so it must not enter the speed equation. Coriolis terms are odd in ω and
    centrifugal terms even, so flipping the sign of ω must leave dV/dt unchanged while the
    angular rates must change by exactly twice the analytic Coriolis contribution.
    """

    def test_dvdt_is_even_in_omega(self) -> None:
        stepper = RK4Stepper()
        planet_pos = _make_planet(_OMEGA)
        planet_neg = _make_planet(-_OMEGA)
        for phi, gamma, psi, velocity in _STATE_GRID:
            kwargs = dict(
                altitude=120_000.0, latitude=phi, longitude=0.1,
                velocity=velocity, gamma=gamma, heading=psi,
            )
            d_pos = stepper.compute_derivatives(_make_status(planet_pos, **kwargs))
            d_neg = stepper.compute_derivatives(_make_status(planet_neg, **kwargs))
            # Even in ω: no odd (Coriolis, 2ωV) contribution to the speed equation. A
            # Coriolis term would contribute O(2ωV) ≈ 1 m/s² here — 12 orders above tol.
            assert d_pos[IDX_VELOCITY] == pytest.approx(d_neg[IDX_VELOCITY], abs=1e-12)

    def test_angular_rates_carry_exact_coriolis(self) -> None:
        """The odd-in-ω parts of dγ/dt and dψ/dt are exactly the Coriolis accelerations."""
        stepper = RK4Stepper()
        planet_pos = _make_planet(_OMEGA)
        planet_neg = _make_planet(-_OMEGA)
        checked_gamma = checked_psi = 0
        for phi, gamma, psi, velocity in _STATE_GRID:
            kwargs = dict(
                altitude=120_000.0, latitude=phi, longitude=0.1,
                velocity=velocity, gamma=gamma, heading=psi,
            )
            d_pos = stepper.compute_derivatives(_make_status(planet_pos, **kwargs))
            d_neg = stepper.compute_derivatives(_make_status(planet_neg, **kwargs))

            odd_gamma = 0.5 * (d_pos[IDX_FLIGHT_PATH_ANGLE] - d_neg[IDX_FLIGHT_PATH_ANGLE])
            odd_psi = 0.5 * (d_pos[IDX_HEADING] - d_neg[IDX_HEADING])
            coriolis_gamma = 2.0 * _OMEGA * math.cos(phi) * math.sin(psi)
            coriolis_psi = -2.0 * _OMEGA * (
                math.tan(gamma) * math.cos(phi) * math.cos(psi) - math.sin(phi)
            )
            assert odd_gamma == pytest.approx(coriolis_gamma, rel=1e-12, abs=1e-18)
            assert odd_psi == pytest.approx(coriolis_psi, rel=1e-12, abs=1e-18)
            if abs(coriolis_gamma) > 1e-9:
                checked_gamma += 1
            if abs(coriolis_psi) > 1e-9:
                checked_psi += 1
        # The Coriolis terms must actually be present (non-vacuous comparison).
        assert checked_gamma > 0 and checked_psi > 0


class TestEquatorialCircularOrbitHold:
    """Test 2 — an eastward equatorial circular orbit is an exact fixed point.

    Vacuum, rotation on, central μ/r² gravity, r = R + 250 km, planet-relative speed
    V = √(μ/r) − ω·r heading due east. Over one full orbital period with RK4 at dt = 1 s
    the radius and flight-path angle must not drift: this requires the ω²r centrifugal
    terms (and the 2ωV Coriolis term) to cancel gravity minus curvature exactly.
    """

    def test_orbit_holds_for_one_period(self) -> None:
        altitude = 250_000.0
        r = _RADIUS + altitude
        v_rel = math.sqrt(_MU / r) - _OMEGA * r
        period = 2.0 * math.pi * math.sqrt(r**3 / _MU)

        planet = _make_planet(_OMEGA)
        status = _make_status(
            planet,
            altitude=altitude, latitude=0.0, longitude=0.0,
            velocity=v_rel, gamma=0.0, heading=math.radians(90.0),
        )
        stepper = RK4Stepper()

        max_radius_drift = 0.0
        max_abs_gamma = 0.0
        time_left = period
        while time_left > 0.0:
            stepper.step(status, min(1.0, time_left))
            time_left -= 1.0
            max_radius_drift = max(max_radius_drift, abs(status.altitude - altitude))
            max_abs_gamma = max(max_abs_gamma, abs(status.flight_path_angle))

        assert max_radius_drift < 1e-6  # meters; reference implementation achieved 0.0
        assert max_abs_gamma < 1e-12  # radians; reference implementation achieved 8.5e-16

    def test_orbit_drifts_without_rotation_terms(self) -> None:
        """Control: the same state over a non-rotating planet is NOT a fixed point.

        This guards the test itself against vacuous passing: the hold in the rotating case
        is meaningful only because removing the ω terms (ω = 0) visibly breaks it.
        """
        altitude = 250_000.0
        r = _RADIUS + altitude
        v_rel = math.sqrt(_MU / r) - _OMEGA * r  # tuned for the *rotating* planet

        planet = _make_planet(0.0)
        status = _make_status(
            planet,
            altitude=altitude, latitude=0.0, longitude=0.0,
            velocity=v_rel, gamma=0.0, heading=math.radians(90.0),
        )
        stepper = RK4Stepper()
        for _ in range(600):
            stepper.step(status, 1.0)
        assert abs(status.altitude - altitude) > 100.0  # drifts by ≫ the 1e-6 m hold


class TestJacobiEnergyConservation:
    """Test 3 — the rotating-frame (Jacobi) energy is conserved in vacuum.

    E = V²/2 − μ/r − ½·ω²·r²·cos²φ is the energy integral of the planet-relative EOM
    over a rotating planet with central gravity (the Coriolis force does no work; the
    centrifugal force is the gradient of −½ω²r²cos²φ). Drag/lift are off (vacuum), so E
    must be constant to integrator roundoff along an eccentric orbit.
    """

    @staticmethod
    def _jacobi_energy(status: SimulationStatus) -> float:
        r = status.radius()
        return (
            0.5 * status.velocity**2
            - _MU / r
            - 0.5 * _OMEGA**2 * r**2 * math.cos(status.latitude) ** 2
        )

    def test_jacobi_energy_drift_below_1e10(self) -> None:
        altitude = 300_000.0
        r = _RADIUS + altitude
        v_circular = math.sqrt(_MU / r)

        planet = _make_planet(_OMEGA)
        status = _make_status(
            planet,
            altitude=altitude,
            latitude=math.radians(15.0),
            longitude=math.radians(10.0),
            velocity=1.05 * v_circular,  # eccentric (e ≈ 0.11), stays well above ground
            gamma=math.radians(2.0),
            heading=math.radians(45.0),
        )
        stepper = RK4Stepper()

        e0 = self._jacobi_energy(status)
        max_rel_drift = 0.0
        for _ in range(6000):  # ≈ one full orbital period at dt = 1 s
            stepper.step(status, 1.0)
            drift = abs(self._jacobi_energy(status) - e0) / abs(e0)
            max_rel_drift = max(max_rel_drift, drift)

        assert max_rel_drift < 1e-10  # reference implementation achieved 6.3e-15


class TestOmegaZeroReduction:
    """Test 4 — with ω = 0 the EOM reduce to the standard non-rotating set.

    An independent reference implementation of the classic non-rotating planet-relative
    entry equations (with lift, drag, and bank) is compared term-for-term against
    ``compute_derivatives`` on a sampled state grid, with aerodynamics active.
    """

    @staticmethod
    def _reference_nonrotating(
        *,
        radius: float,
        latitude: float,
        velocity: float,
        gamma: float,
        psi: float,
        bank: float,
        gravity: float,
        drag_accel: float,
        lift_accel: float,
    ) -> tuple[float, float, float, float, float, float]:
        """The textbook non-rotating planet-relative 3-DOF entry equations."""
        sin_g, cos_g = math.sin(gamma), math.cos(gamma)
        sin_p, cos_p = math.sin(psi), math.cos(psi)
        d_h = velocity * sin_g
        d_lat = velocity * cos_g * cos_p / radius
        d_lon = velocity * cos_g * sin_p / (radius * math.cos(latitude))
        d_v = -drag_accel - gravity * sin_g
        d_gamma = (
            lift_accel * math.cos(bank) + (velocity**2 / radius - gravity) * cos_g
        ) / velocity
        d_psi = (
            lift_accel * math.sin(bank) / cos_g
            + (velocity**2 / radius) * cos_g * sin_p * math.tan(latitude)
        ) / velocity
        return d_h, d_lat, d_lon, d_v, d_gamma, d_psi

    def test_matches_reference_on_state_grid(self) -> None:
        density = 0.02  # uniform; representative of high-altitude entry conditions
        cd, lift_to_drag = 1.5, 0.3
        aero = _ConstantAero(cd, cd * lift_to_drag)
        planet = _make_planet(0.0, atmosphere=_UniformDensityAtmosphere(density))
        vehicle = _test_vehicle()
        mass = vehicle.mass.get()
        area = vehicle.reference_area.get()
        stepper = RK4Stepper()

        for (phi, gamma, psi, velocity), bank in itertools.product(
            _STATE_GRID, (0.0, math.radians(60.0), math.radians(160.0))
        ):
            altitude = 60_000.0
            status = _make_status(
                planet,
                altitude=altitude, latitude=phi, longitude=0.2,
                velocity=velocity, gamma=gamma, heading=psi, bank=bank,
                aero=aero,
            )
            derivative = stepper.compute_derivatives(status)

            r = _RADIUS + altitude
            q = 0.5 * density * velocity**2
            expected = self._reference_nonrotating(
                radius=r,
                latitude=phi,
                velocity=velocity,
                gamma=gamma,
                psi=psi,
                bank=bank,
                gravity=_MU / (r * r),
                drag_accel=cd * q * area / mass,
                lift_accel=cd * lift_to_drag * q * area / mass,
            )
            actual = (
                derivative[IDX_ALTITUDE],
                derivative[IDX_LATITUDE],
                derivative[IDX_LONGITUDE],
                derivative[IDX_VELOCITY],
                derivative[IDX_FLIGHT_PATH_ANGLE],
                derivative[IDX_HEADING],
            )
            for got, want in zip(actual, expected):
                assert got == pytest.approx(want, rel=1e-12, abs=1e-15)
