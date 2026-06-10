# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""InSight rotation experiment — what planet rotation does to a Mars entry's outputs.

Two stages, both replaying a fixed constant bank (σ = 160°: lift mostly down with a
modest out-of-plane component) through the forward simulator. The bank schedule is always
an INPUT and crossrange always an OUTPUT; nothing here solves for controls.

**Stage A — external-reference ablation reproduction (harness validation).**
Reproduces, inside ORP, the rotating-frame ablation previously run outside this repo
against the `openreentry` InSight lateral sanity case (see
``ref_core/lateral_insight.py``, which records that ablation's results as ASSERTED):
constant coefficients C_D = 1.46, L/D = 0.25; exponential Mars atmosphere ρ₀ = 0.020
kg/m³, H = 11 100 m (CO₂ gas at 210 K); planet-relative entry V = 5500 m/s, γ = −12°,
h = 125 km, latitude 4.5° N; stop at Mach 1.56 using the CO₂ sound speed at 210 K.
Expected (external reference): at ω = 0, peak 10.93 g and azimuth-independent crossrange
9.28 km (Allen-Eggers closed form for these parameters: 10.63 g); with rotation on, an
azimuth-dependent crossrange shift of −1.0 to −1.8 km and peak g in 10.1–10.9.
Reproducing these numbers validates this harness against an independent implementation.

**Stage B — ORP's full models.**
Same entry state and bank, but the lander-anchored Mars atmosphere and Modified
Newtonian aerodynamics at the vehicle's trim angle of attack (InSight trims at α = 0 by
design, so Newtonian lift is zero — flagged below). Rotation off and on; peak g reported
against the flight 8.13 g and crossrange against the flight 6.1 km (Karlgaard et al.,
NASA NTRS 20200003204).

Flagged approximations (stage A is an ablation *reproduction*, not Mars truth):
- [APPROX-ATMOS-A] ρ₀ = 0.020 kg/m³ is the external reference's value — the rounded
  fact-sheet figure, ideal-gas-inconsistent with the 636 Pa / 210 K anchor ORP's own
  Mars model uses (ρ₀ = 0.0160; see ``orp/core/atmosphere/mars.py``). Kept verbatim
  because stage A must match the external configuration exactly.
- [APPROX-AERO-A] C_D = 1.46, L/D = 0.25 are the external reference's stand-ins; the
  sourced InSight values are C_D ≈ 1.68 at trim α = 0 with L/D = 0 (insight.yaml).
- [APPROX-LIFT] a constant bank stands in for InSight's real rolling, oscillating lift
  (bounded instability; lift down at entry) — the mechanism Karlgaard names for the
  flight's 6.1 km crossrange. Neither stage replays the (figure-only, undigitized)
  flight lift history.
- [APPROX-EI] entry-interface altitude 125 km assumed (the text gives V and γ, not h).
- [APPROX-STATE] flight initial state is OD-based inertial (5542.2 m/s, −12.57° relative
  at r = 3522.14 km); both stages use the paper's nominal planet-relative 5500 / −12.0.
- [APPROX-TRIM-B] stage B's static trim α = 0 gives zero Newtonian lift, so its
  crossrange comes from rotation alone — a static-trim model cannot produce the flight's
  lift-driven crossrange. Documented, not tuned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.aerodynamics.newtonian import ModifiedNewtonianCalculator
from orp.core.atmosphere.exponential import ExponentialAtmosphere
from orp.core.bank_schedule import BankSchedule
from orp.core.gravity.mars import MarsGravityModel
from orp.core.planet.planet import Planet
from orp.core.planet.registry import MARS
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary

__all__ = [
    "ALLEN_EGGERS_PEAK_G",
    "EXPECTED_OMEGA0_PEAK_G",
    "EXPECTED_OMEGA0_CROSSRANGE_KM",
    "FLIGHT_PEAK_G",
    "FLIGHT_CROSSRANGE_KM",
    "MACH_STOP_VELOCITY",
    "run_stage_a",
    "run_stage_b",
    "main",
]

# ---------------- entry state (Karlgaard NTRS 20200003204, text values) ----------------
_ENTRY_VELOCITY = 5500.0  # m/s, planet-relative (nominal, p. 2)
_ENTRY_GAMMA = math.radians(-12.0)  # planet-relative FPA (nominal, p. 2)
_ENTRY_ALTITUDE = 125_000.0  # m [APPROX-EI]
_ENTRY_LATITUDE = math.radians(4.5)  # ~landing-site latitude band (site: 4.50238 N)
_BANK = math.radians(160.0)  # [APPROX-LIFT] lift ~20° off straight-down

# ---------------- stage A external-reference ablation configuration --------------------
_RHO0_A = 0.020  # kg/m³ [APPROX-ATMOS-A] — external reference's value, kept verbatim
_SCALE_HEIGHT_A = 11_100.0  # m
_CD_A, _LD_A = 1.46, 0.25  # [APPROX-AERO-A]
_CO2_R, _CO2_GAMMA, _CO2_T = 188.92, 1.29, 210.0

#: Stop speed: Mach 1.56 at the CO₂ sound speed for 210 K, a = √(γRT) ≈ 226.2 m/s.
MACH_STOP_VELOCITY = 1.56 * math.sqrt(_CO2_GAMMA * _CO2_R * _CO2_T)

# ---------------- comparison targets ----------------------------------------------------
#: Allen-Eggers closed-form peak deceleration for the stage-A parameters (g).
ALLEN_EGGERS_PEAK_G = (
    _ENTRY_VELOCITY**2 * abs(math.sin(_ENTRY_GAMMA)) / (2.0 * math.e * _SCALE_HEIGHT_A)
) / 9.80665
#: External-reference ablation at ω = 0 (validation targets for stage A).
EXPECTED_OMEGA0_PEAK_G = 10.93
EXPECTED_OMEGA0_CROSSRANGE_KM = 9.28
#: Flight reconstruction (Karlgaard NTRS 20200003204): comparison targets for stage B.
FLIGHT_PEAK_G = 8.13
FLIGHT_CROSSRANGE_KM = 6.1

_TIME_STEP = 0.5
_MAX_TIME = 2000.0


@dataclass(frozen=True)
class ExperimentMetrics:
    """Outputs of one run, evaluated at the Mach-1.56 stop condition."""

    azimuth_deg: float
    rotating: bool
    peak_g: float
    crossrange_km: float
    downrange_km: float
    stop_time_s: float
    stop_altitude_m: float
    provenance_level: str


def _central_angle(phi1: float, lam1: float, phi2: float, lam2: float) -> float:
    """Great-circle central angle (haversine), radians."""
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _crosstrack_angle(phi0: float, lam0: float, psi0: float, phi: float, lam: float) -> float:
    """Signed cross-track angle to the great circle through (φ0, λ0) on heading ψ0.

    Positive to the RIGHT of the initial heading — the same convention as the
    `openreentry` reference (`eom_3dof.crosstrack_angle`), so crossrange numbers are
    directly comparable.
    """
    d13 = _central_angle(phi0, lam0, phi, lam)
    bearing13 = math.atan2(
        math.sin(lam - lam0) * math.cos(phi),
        math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(lam - lam0),
    )
    return math.asin(max(-1.0, min(1.0, math.sin(d13) * math.sin(bearing13 - psi0))))


def _run(conditions: SimulationConditions, radius: float, psi0: float) -> ExperimentMetrics:
    """Simulate forward and evaluate metrics at the first crossing of the stop speed."""
    flight_data = SimulationEngine().simulate(conditions)
    branch = flight_data.get_branch(0)
    time = branch.get(fd.TYPE_TIME)
    velocity = branch.get(fd.TYPE_VELOCITY)
    altitude = branch.get(fd.TYPE_ALTITUDE)
    latitude = [math.radians(v) for v in branch.get(fd.TYPE_LATITUDE)]
    longitude = [math.radians(v) for v in branch.get(fd.TYPE_LONGITUDE)]
    g_load = branch.get(fd.TYPE_DECELERATION)

    stop = next(
        (i for i in range(1, len(velocity)) if velocity[i] <= MACH_STOP_VELOCITY), None
    )
    if stop is None:
        raise RuntimeError(
            f"Run never decelerated to the stop speed {MACH_STOP_VELOCITY:.1f} m/s "
            f"(final V = {velocity[-1]:.1f} m/s at h = {altitude[-1]:.0f} m)."
        )
    # Linear interpolation in V between the bracketing samples for the stop instant.
    fraction = (MACH_STOP_VELOCITY - velocity[stop - 1]) / (velocity[stop] - velocity[stop - 1])

    def at_stop(channel: list[float]) -> float:
        return channel[stop - 1] + fraction * (channel[stop] - channel[stop - 1])

    phi0, lam0 = latitude[0], longitude[0]
    phi_stop, lam_stop = at_stop(latitude), at_stop(longitude)
    crossrange = radius * _crosstrack_angle(phi0, lam0, psi0, phi_stop, lam_stop)
    downrange = radius * _central_angle(phi0, lam0, phi_stop, lam_stop)

    return ExperimentMetrics(
        azimuth_deg=math.degrees(psi0),
        rotating=conditions.planet.rotation_rate != 0.0,
        peak_g=max(g_load[: stop + 1]),
        crossrange_km=crossrange / 1000.0,
        downrange_km=downrange / 1000.0,
        stop_time_s=at_stop(time),
        stop_altitude_m=at_stop(altitude),
        provenance_level=flight_data.provenance.level.name,
    )


def run_stage_a(azimuth_deg: float, *, rotating: bool) -> ExperimentMetrics:
    """Stage A: external-reference ablation configuration, ORP EOM underneath."""
    tag = ProvenanceTag(
        ValidationLevel.ASSERTED,
        source="External reference ablation values (ref_core/lateral_insight.py header)",
        notes="[APPROX-ATMOS-A]/[APPROX-AERO-A] stand-ins kept verbatim for reproduction.",
    )
    planet = Planet(
        name="Mars (stage-A ablation)",
        atmosphere=ExponentialAtmosphere(
            _RHO0_A,
            _SCALE_HEIGHT_A,
            temperature=_CO2_T,
            specific_gas_constant=_CO2_R,
            specific_heat_ratio=_CO2_GAMMA,
            provenance=tag,
        ),
        gravity=MarsGravityModel(),
        mean_radius=MARS.mean_radius,
        rotation_rate=MARS.rotation_rate if rotating else 0.0,
        gravitational_parameter=MARS.gravitational_parameter,
        surface_pressure=MARS.surface_pressure,
        sutton_graves_constant=MARS.sutton_graves_constant,
    )
    conditions = _conditions(
        planet,
        aerodynamic_calculator=ConstantCoefficientCalculator(_CD_A, _LD_A, provenance=tag),
        azimuth_deg=azimuth_deg,
    )
    return _run(conditions, planet.mean_radius, math.radians(azimuth_deg))


def run_stage_b(azimuth_deg: float, *, rotating: bool) -> ExperimentMetrics:
    """Stage B: ORP's full models — lander-anchored Mars atmosphere, Newtonian at trim."""
    planet = MARS if rotating else replace(MARS, rotation_rate=0.0)
    conditions = _conditions(
        planet,
        aerodynamic_calculator=ModifiedNewtonianCalculator(),
        azimuth_deg=azimuth_deg,
    )
    return _run(conditions, planet.mean_radius, math.radians(azimuth_deg))


def _conditions(planet: Planet, *, aerodynamic_calculator, azimuth_deg: float) -> SimulationConditions:
    return SimulationConditions(
        vehicle=VehicleLibrary().load("insight"),
        planet=planet,
        bank_schedule=BankSchedule.constant(
            _BANK,
            provenance=ProvenanceTag(
                ValidationLevel.ASSERTED,
                source="Representative constant bank (lift ~20° off straight-down), "
                "ref_core/lateral_insight.py [APPROX-LIFT]; stands in for the flight's "
                "rolling lift (NTRS 20200003204)",
            ),
        ),
        aerodynamic_calculator=aerodynamic_calculator,
        entry_velocity=_ENTRY_VELOCITY,
        entry_flight_path_angle=_ENTRY_GAMMA,
        entry_altitude=_ENTRY_ALTITUDE,
        entry_heading=math.radians(azimuth_deg),
        entry_latitude=_ENTRY_LATITUDE,
        entry_longitude=0.0,
        time_step=_TIME_STEP,
        max_simulation_time=_MAX_TIME,
        ground_altitude=0.0,
    )


def main() -> dict[str, object]:
    """Run the full experiment and print the report. Returns all metrics."""
    azimuths = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)

    print("=" * 78)
    print("InSight rotation experiment — bank is an INPUT, crossrange an OUTPUT")
    print("Flight targets (Karlgaard NTRS 20200003204): peak 8.13 g, crossrange 6.1 km")
    print("=" * 78)

    print("\nSTAGE A — external-reference ablation reproduction (harness validation)")
    print(f"  Allen-Eggers closed form for these parameters: {ALLEN_EGGERS_PEAK_G:.2f} g")
    print(f"  expected (external ref, w=0): peak {EXPECTED_OMEGA0_PEAK_G} g, "
          f"crossrange {EXPECTED_OMEGA0_CROSSRANGE_KM} km (azimuth-independent)")
    print(f"  expected (external ref, rotating): shift -1.0..-1.8 km, peak 10.1-10.9 g")
    a_still = [run_stage_a(az, rotating=False) for az in azimuths]
    a_rot = [run_stage_a(az, rotating=True) for az in azimuths]
    print(f"  {'azimuth':>8} {'w=0 peak g':>11} {'w=0 xr km':>10} "
          f"{'rot peak g':>11} {'rot xr km':>10} {'shift km':>9}")
    for still, rot in zip(a_still, a_rot):
        print(
            f"  {still.azimuth_deg:8.0f} {still.peak_g:11.3f} {still.crossrange_km:10.3f} "
            f"{rot.peak_g:11.3f} {rot.crossrange_km:10.3f} "
            f"{rot.crossrange_km - still.crossrange_km:9.3f}"
        )
    print(f"  [provenance of stage-A runs: {a_still[0].provenance_level}]")

    print("\nSTAGE B — ORP full models (lander-anchored atmosphere, Newtonian at trim)")
    print("  [APPROX-TRIM-B] InSight trims at alpha=0 => Newtonian L/D=0: stage-B")
    print("  crossrange is rotation-only; the flight's lift-driven 6.1 km cannot arise.")
    b_still = run_stage_b(0.0, rotating=False)
    b_rot = run_stage_b(0.0, rotating=True)
    for label, m in (("w=0", b_still), ("rotating", b_rot)):
        print(
            f"  {label:>9}: peak {m.peak_g:6.3f} g (flight {FLIGHT_PEAK_G}), "
            f"crossrange {m.crossrange_km:7.3f} km (flight {FLIGHT_CROSSRANGE_KM}), "
            f"downrange {m.downrange_km:6.1f} km, stop t={m.stop_time_s:6.1f} s "
            f"h={m.stop_altitude_m / 1000:5.2f} km"
        )
    print(f"  [provenance of stage-B runs: {b_still.provenance_level}]")
    print("\nEvery approximation is flagged in the module docstring; results are")
    print("documented whichever way they fall (docs/experiments/insight_rotation.md).")

    return {
        "stage_a_still": a_still,
        "stage_a_rotating": a_rot,
        "stage_b_still": b_still,
        "stage_b_rotating": b_rot,
    }


if __name__ == "__main__":
    main()
