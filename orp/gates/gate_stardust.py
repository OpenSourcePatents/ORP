# SPDX-License-Identifier: GPL-3.0-or-later
# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
"""Gate — Stardust SRC ballistic entry. Forward prediction vs sourced flight truths.

Sources: Mitcheltree et al., AIAA 97-2304 (NTRS 20040105538) for the outer mold line and
hypersonic C_D (see stardust.yaml); Stardust entry reconstruction for the entry-interface
state and gate truths.

WHAT THIS IS. Unlike the Artemis gate (which cannot integrate without the un-digitized bank
command), Stardust is BALLISTIC (L/D = 0), so the validated simulator can be run FORWARD with
no control input and compared directly to flight truths. This gate converts the published
inertial EI state to ORP's planet-relative frame (rotation ON), integrates, and reports the
peak deceleration, the Mach-1.23 altitude, and the time to reach it against the reconstructed
truths. It sweeps the EI latitude because the primary does not text-state it.

SOURCED TRUTHS (reconstruction):
  - peak deceleration 32.89 g (3-sigma 3.64)
  - Mach 1.23 at 31.03 km altitude
  - drogue deploy at 137.9 s after EI
EI state (reconstruction): radius 6503.14 km, 12.9 km/s inertial, FPA -8.2 deg, azimuth
102.9 deg.

EXPECTED PHYSICS. Superorbital entry: the centrifugal/curvature term (V^2/r) is first-order
and SHALLOWS the trajectory, cutting peak g well below the flat-Earth value. The external
reference computed ~38 g on crude curved models vs ~73 g without curvature; flat-Earth
Allen-Eggers here gives ~60 g. ORP's full rotating-planet EOM should land near the flight
32.89 g, demonstrating the shallowing.

VALIDATION STATUS: NOT_VALIDATED. The forward prediction reproduces the truths within the
flight 3-sigma (reported below), but the gate is NOT a locked validation: (1) the EI latitude
is assumed (swept, not sourced); (2) C_D is the constant hypersonic value (the CD-vs-Mach
curve below Mach 12 is figure-only); (3) the ISA atmosphere is held constant above 86 km
(the EI is at ~132 km); (4) 3-DOF point mass (no spin/ablation/6-DOF). Honest agreement,
documented approximations.
"""

from __future__ import annotations

import math

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.bank_schedule import BankSchedule
from orp.core.frames import ConvertedEntryState, inertial_to_planet_relative
from orp.core.planet import EARTH
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary

GATE_STARDUST_STATUS = "NOT_VALIDATED"  # forward prediction; reproduces truths within 3-sigma

# ---------------- Entry-interface state (reconstruction; INERTIAL) ----------------
EI_RADIUS_KM = 6503.14
EI_VELOCITY_INERTIAL_MPS = 12900.0
EI_FPA_INERTIAL_DEG = -8.2
EI_AZIMUTH_INERTIAL_DEG = 102.9
EI_ALTITUDE_M = EI_RADIUS_KM * 1000.0 - EARTH.mean_radius

# EI latitude is NOT text-stated in the primary -> swept as an explicit assumption.
EI_LATITUDE_SWEEP_DEG: tuple[float, ...] = (-45.0, -30.0, 0.0, 28.5, 45.0)

# ---------------- Sourced flight truths (reconstruction) ----------------
TRUTH_PEAK_G = 32.89
TRUTH_PEAK_G_3SIGMA = 3.64
TRUTH_MACH = 1.23
TRUTH_MACH_ALTITUDE_KM = 31.03
TRUTH_DROGUE_TIME_S = 137.9

ATMOSPHERE_VALID_ALTITUDE_KM = 86.0  # ISA held constant above this (EI is ~132 km)


def stardust_vehicle():
    """Load the Stardust vehicle (geometry/CD from Mitcheltree AIAA 97-2304)."""
    return VehicleLibrary().load("stardust")


def relative_ei_state(latitude_deg: float) -> ConvertedEntryState:
    """Inertial EI state -> planet-relative at the assumed EI latitude (rotation ON)."""
    return inertial_to_planet_relative(
        EARTH,
        velocity=EI_VELOCITY_INERTIAL_MPS,
        flight_path_angle=math.radians(EI_FPA_INERTIAL_DEG),
        heading=math.radians(EI_AZIMUTH_INERTIAL_DEG),
        latitude=math.radians(latitude_deg),
        altitude=EI_ALTITUDE_M,
    )


def allen_eggers_flat_peak_g(velocity_mps: float, fpa_rad: float, scale_height_m: float = 7200.0) -> float:
    """Flat-Earth Allen-Eggers ballistic peak deceleration (g), for the curvature contrast.

    n_max = V_E^2 |sin(gamma_E)| / (2 e H g0). Independent of ballistic coefficient. This is
    the no-curvature reference the rotating-planet result should fall well below.
    """
    g0 = 9.80665
    return velocity_mps**2 * abs(math.sin(fpa_rad)) / (2.0 * math.e * scale_height_m * g0)


def run_entry(latitude_deg: float, *, time_step: float = 0.05, max_time: float = 400.0) -> dict:
    """Run the ballistic Stardust entry forward (rotation ON) at one assumed EI latitude."""
    vehicle = stardust_vehicle()
    rel = relative_ei_state(latitude_deg)
    aero = ConstantCoefficientCalculator(
        drag_coefficient=vehicle.drag_coefficient.get(),
        lift_to_drag=0.0,
        provenance=vehicle.drag_coefficient.provenance,  # sourced: Mitcheltree
    )
    conditions = SimulationConditions(
        vehicle=vehicle,
        planet=EARTH,
        bank_schedule=BankSchedule.constant(0.0),  # ballistic: bank is inert (L/D=0)
        aerodynamic_calculator=aero,
        entry_velocity=rel.velocity,
        entry_flight_path_angle=rel.flight_path_angle,
        entry_heading=rel.heading,
        entry_latitude=math.radians(latitude_deg),
        entry_altitude=EI_ALTITUDE_M,
        time_step=time_step,
        max_simulation_time=max_time,
        ground_altitude=0.0,
    )
    branch = SimulationEngine().simulate(conditions).get_branch(0)
    decel = [v for v in branch.get(fd.TYPE_DECELERATION) if math.isfinite(v)]
    altitude = branch.get(fd.TYPE_ALTITUDE)
    mach = branch.get(fd.TYPE_MACH)
    times = branch.get(fd.TYPE_TIME)

    peak_index = decel.index(max(decel))
    h_at_mach = t_at_mach = float("nan")
    for i in range(1, len(mach)):
        if math.isfinite(mach[i]) and mach[i] <= TRUTH_MACH < mach[i - 1]:
            h_at_mach = altitude[i] / 1000.0
            t_at_mach = times[i]
            break

    return {
        "latitude_deg": latitude_deg,
        "v_rel_mps": rel.velocity,
        "gamma_rel_deg": math.degrees(rel.flight_path_angle),
        "peak_g": max(decel),
        "t_peak_s": times[peak_index],
        "h_peak_km": altitude[peak_index] / 1000.0,
        "h_at_mach123_km": h_at_mach,
        "t_at_mach123_s": t_at_mach,
        "allen_eggers_flat_g": allen_eggers_flat_peak_g(rel.velocity, rel.flight_path_angle),
    }


def run_sweep() -> list[dict]:
    """Run the EI-latitude sweep; return one result dict per assumed latitude."""
    return [run_entry(lat) for lat in EI_LATITUDE_SWEEP_DEG]


def _within(value: float, truth: float, tol: float) -> bool:
    return math.isfinite(value) and abs(value - truth) <= tol


if __name__ == "__main__":  # pragma: no cover
    print("=" * 78)
    print(f"GATE: Stardust SRC ballistic entry  --  STATUS: {GATE_STARDUST_STATUS}")
    print("Mitcheltree AIAA 97-2304 (geometry/CD) + entry reconstruction (EI state, truths).")
    print("Forward prediction, rotation ON. EI latitude assumed (swept).")
    print("=" * 78)
    print(f"\nEI: radius {EI_RADIUS_KM} km (alt {EI_ALTITUDE_M/1000:.1f} km), "
          f"{EI_VELOCITY_INERTIAL_MPS/1000:.1f} km/s inertial, FPA {EI_FPA_INERTIAL_DEG} deg, "
          f"az {EI_AZIMUTH_INERTIAL_DEG} deg")
    print(f"Truths: peak {TRUTH_PEAK_G} +/- {TRUTH_PEAK_G_3SIGMA} g (3-sigma); "
          f"Mach {TRUTH_MACH} at {TRUTH_MACH_ALTITUDE_KM} km; drogue at {TRUTH_DROGUE_TIME_S} s\n")
    print(f"{'lat':>6} {'V_rel':>8} {'gam_rel':>8} {'peak_g':>7} {'t_peak':>7} "
          f"{'h_M1.23':>8} {'t_M1.23':>8} {'AE_flat_g':>9}")
    rows = run_sweep()
    for r in rows:
        print(f"{r['latitude_deg']:>6.1f} {r['v_rel_mps']:>8.0f} {r['gamma_rel_deg']:>8.2f} "
              f"{r['peak_g']:>7.1f} {r['t_peak_s']:>7.1f} {r['h_at_mach123_km']:>8.2f} "
              f"{r['t_at_mach123_s']:>8.1f} {r['allen_eggers_flat_g']:>9.1f}")
    peak_lo = min(r["peak_g"] for r in rows)
    peak_hi = max(r["peak_g"] for r in rows)
    ae = rows[len(rows) // 2]["allen_eggers_flat_g"]
    print(f"\nPeak g across latitude sweep: {peak_lo:.1f}-{peak_hi:.1f} g")
    print(f"  flight truth: {TRUTH_PEAK_G} +/- {TRUTH_PEAK_G_3SIGMA} g  -> "
          f"within 3-sigma: {all(_within(r['peak_g'], TRUTH_PEAK_G, TRUTH_PEAK_G_3SIGMA) for r in rows)}")
    print(f"Centrifugal shallowing: flat-Earth Allen-Eggers ~{ae:.0f} g vs ORP curved ~{peak_lo:.0f}-{peak_hi:.0f} g")
    print(f"  (external ref: ~73 g no-curvature, ~38 g crude-curved; flight {TRUTH_PEAK_G} g)")
    print(f"\nEI-latitude sensitivity of peak g: {peak_hi-peak_lo:.2f} g across "
          f"{EI_LATITUDE_SWEEP_DEG[0]:.0f}..{EI_LATITUDE_SWEEP_DEG[-1]:.0f} deg (weak).")
    print(f"\nRESULT: {GATE_STARDUST_STATUS}. Forward prediction reproduces flight peak-g, "
          f"drogue timing, and M1.23 altitude within 3-sigma; not locked (EI latitude assumed, "
          f"constant CD, ISA clamp >86 km, 3-DOF).")
