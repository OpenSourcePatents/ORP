# SPDX-License-Identifier: GPL-3.0-or-later
# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
"""Gate 3 (replay) — Artemis I skip entry: digitized bank command replayed forward.

WHAT THIS IS. The Artemis I commanded bank history (AAS 24-174 Fig 12(a)) was
MACHINE-DIGITIZED on 2026-06-10 (data/flights/artemis1_bank_commanded.csv; methods and
measured uncertainty in docs/digitization/artemis1_bank_commanded.md). That unlocks the
replay the Gate-3 scaffold refused: convert the Table-1 inertial EI state to ORP's
planet-relative frame (orp.core.frames), replay the digitized schedule through the
forward sim, and report against the published truths. Forward-only wall intact: the bank
schedule is an INPUT (a pre-recorded control history), crossrange is an OUTPUT, and no
endpoint is targeted anywhere.

THE SIGN-CONVENTION LOCK. AAS 24-174 never defines its bank sign convention in text
(pages 3-7 searched verbatim — see docs/digitization/artemis1_bank_commanded.md §5), so
the figure's plotted sign has two possible mappings onto ORP's bank angle:
  mapping A: sigma_ORP = +sigma_figure
  mapping B: sigma_ORP = -sigma_figure
ORP's own convention is pinned by docs/verification/eom_vinh_culp_cr149170.md §2
(verbatim): "in ORP a positive bank produces dpsi_ORP/dt > 0 (a North->East,
rightward/compass-positive turn)". Both mappings are replayed; the one whose endpoint
crossrange agrees with the Table-4 splashdown side LOCKS the convention. This is not
convention laundering: the schedule (magnitudes AND reversal times AND relative sign
pattern) is sourced; only the figure-to-ORP sign mapping is binary, and it is
discriminated by comparing a forward OUTPUT against flight truth.

PRE-REGISTERED PASS TOLERANCES — written BEFORE any comparison was run (2026-06-10),
derived from the measured digitization uncertainty plus the stated model error budget:

  Digitization (measured, docs/digitization/artemis1_bank_commanded.md §4):
    bank amplitude +/-1 deg (95%) on holds; reversal timing +/-1 s (validated <=0.67 s
    against Table 3). Trajectory impact: ~2-3 nmi crossrange per reversal-second,
    sub-kft on skip apogee — NEGLIGIBLE next to the model terms below.
  Model error budget (documented limitations):
    (a) Earth ISA held constant above 86 km: the EI is at 121.92 km and the skip apogee
        (287.4 kft = 87.6 km) sits right at the clamp boundary, so first-pass and
        skip-arc densities above 86 km are overestimated.
    (b) Constant CD = 1.40 (ASSERTED order-of-magnitude; Orion CD-vs-Mach is
        figure-only) and constant L/D (no Mach dependence, no trim modulation).
    (c) The paper's own estimators: the flight saw ~10% lower density than the 1976
        standard atmosphere and ~5% lower L/D than predicted (AAS 24-174 p.11,
        dual-channel verified) — and with flight-quality models the paper's own
        predictor still missed reversal-2 timing by 142 s and skip apogee by 6.1 kft.
    (d) Open-loop replay of CLOSED-LOOP commands: the flown commands corrected for the
        real atmosphere; replaying them through a different atmosphere accumulates
        downrange error with no corrective feedback.
  Therefore (pre-registered):
    TOL_SKIP_APOGEE_KFT   = 30.0 nominal / 20.0 flight-informed
    TOL_ENDPOINT_MISS_NMI = 250.0 nominal / 150.0 flight-informed (drogue-deploy point;
                            main/splashdown reported with the no-parachute caveat)
    TOL_PHASE_PROXY_S     = 60.0 nominal / 40.0 flight-informed
    SIGN_LOCK_MIN_RATIO   = 3.0 (wrong-sign crossrange miss must exceed correct-sign
                            by at least this factor for the lock to be declared)
  Results are reported whichever way they fall. Nothing here is tuned.

PHASE-TIMING PROXIES. The sim runs no guidance, so Table-2 phase initiations are
compared through trajectory-observable proxies: D_Upc_Min = D_Upc_End = 6 ft/s^2
(paper pp. 6-8): Up Control->Ballistic when drag acceleration FALLS below 6 ft/s^2
(flight 256.450 s), Ballistic->Final when it RISES back above (flight 551.425 s), and
the FBC pilot-chute time (950.125 s) against the sim's crossing of the Table-4
drogue-deploy altitude (22273.99 ft) — the FBC deploy precedes drogue by seconds.

VALIDATION STATUS: see report (docs/gates/gate3_artemis_replay.md).
"""

from __future__ import annotations

import csv
import dataclasses
import math
from pathlib import Path

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator
from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.atmosphere.us76_highalt import US76HighAltitudeExtension
from orp.core.bank_schedule import BankSchedule
from orp.core.frames import great_circle_bearing
from orp.core.planet import EARTH
from orp.core.provenance.tags import ProvenanceTag, TaggedValue, ValidationLevel
from orp.core.simulation import SimulationConditions, SimulationEngine
from orp.core.simulation import flight_data as fd
from orp.core.vehicles import VehicleLibrary
from orp.gates.gate3_artemis import (
    EI_ALTITUDE_FT,
    EI_LATITUDE_DEG,
    EI_LONGITUDE_DEG,
    SKIP_APOGEE_KFT_FLIGHT,
    TABLE2_PHASE_TIMES,
    TABLE4_ENDPOINTS,
    relative_ei_state,
)

_FT = 0.3048
_NMI = 1852.0

# ---------------- PRE-REGISTERED TOLERANCES (see module docstring; do not tune) -------
TOL_SKIP_APOGEE_KFT_NOMINAL = 30.0
TOL_SKIP_APOGEE_KFT_INFORMED = 20.0
TOL_ENDPOINT_MISS_NMI_NOMINAL = 250.0
TOL_ENDPOINT_MISS_NMI_INFORMED = 150.0
TOL_PHASE_PROXY_S_NOMINAL = 60.0
TOL_PHASE_PROXY_S_INFORMED = 40.0
SIGN_LOCK_MIN_RATIO = 3.0

# ---------------- sourced sweep ranges (orion.yaml / McNamara NTRS 20140004224) -------
MASS_SWEEP_KG = (9934.0, 10160.5, 10387.0)
LD_SWEEP = (0.23, 0.25, 0.27)
ORION_CD = 1.40  # ASSERTED order-of-magnitude (Bibb NTRS 20110013644); documented limit

# Flight-informed variant per AAS 24-174 p.11 (dual-channel verified verbatim):
# "roughly a 10% less dense atmosphere than the 1976 standard atmosphere" and
# "roughly 5% less L/D than predicted".
INFORMED_DENSITY_FACTOR = 0.90
INFORMED_LD_FACTOR = 0.95

DRAG_THRESHOLD_FTPS2 = 6.0  # D_Upc_Min = D_Upc_End (AAS 24-174 pp. 6-8)

SCHEDULE_CSV = Path(__file__).resolve().parents[2] / "data" / "flights" / "artemis1_bank_commanded.csv"


class ScaledDensityAtmosphere(AtmosphericModel):
    """Wrap an atmosphere with a constant density factor (pressure scaled, T unchanged).

    Scaling pressure at fixed temperature scales rho = P/(R T) by the same factor and
    leaves the speed of sound unchanged — exactly a 'density factor' in the PredGuid
    estimator sense (Dens_Fact_Filt applied to the on-board 1976 standard atmosphere).
    """

    def __init__(self, base: AtmosphericModel, density_factor: float, note: str) -> None:
        self._base = base
        self._factor = float(density_factor)
        self._provenance = ProvenanceTag(
            ValidationLevel.ASSERTED,
            notes=(f"Density factor {density_factor:g} applied to "
                   f"{type(base).__name__}: {note}"),
        )

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        c = self._base.get_conditions(altitude_msl)
        return dataclasses.replace(c, pressure=c.pressure * self._factor)

    @property
    def provenance(self) -> ProvenanceTag:
        return self._provenance

    def get_max_altitude(self) -> float:
        return self._base.get_max_altitude()


def load_digitized_schedule(sign: float = 1.0) -> BankSchedule:
    """Load the MACHINE-DIGITIZED commanded-bank CSV as a replayable schedule.

    Hold-last across gap/transition samples (the command is piecewise constant; gaps are
    occlusions, not data). ``sign`` selects the figure-to-ORP mapping (+1 = mapping A,
    sigma_ORP = +sigma_figure; -1 = mapping B).
    """
    times: list[float] = []
    angles_deg: list[float] = []
    last: float | None = None
    with open(SCHEDULE_CSV, encoding="utf-8") as f:
        for row in csv.reader(line for line in f if not line.startswith("#")):
            if row[0] == "time_rel_EI_s":
                continue
            t, v, flag = float(row[0]), row[1], row[2]
            if flag == "ok" and v != "":
                last = float(v)
            if last is not None:
                times.append(t)
                angles_deg.append(sign * last)
    provenance = ProvenanceTag(
        ValidationLevel.ASSERTED,
        notes=("MACHINE-DIGITIZED from AAS 24-174 Fig 12(a) (NTRS 20240000024); "
               "amplitude +/-1 deg, timing +/-1 s; all six Table-3 reversal times "
               "reproduced within 0.67 s; docs/digitization/artemis1_bank_commanded.md. "
               f"Figure-to-ORP sign mapping: sigma_ORP = {'+' if sign > 0 else '-'}"
               "sigma_figure."),
    )
    return BankSchedule.from_degrees(times, angles_deg, provenance=provenance)


def orion_vehicle(mass_kg: float, lift_to_drag: float):
    """Orion vehicle with swept mass / L/D (sourced design ranges, McNamara Table 3)."""
    v = VehicleLibrary().load("orion")
    note = "Swept within the McNamara NTRS 20140004224 design range (9,934-10,387 kg / 0.23-0.27)."
    return dataclasses.replace(
        v,
        mass=TaggedValue(value=mass_kg, provenance=ProvenanceTag(ValidationLevel.ASSERTED, notes=note), unit="kg"),
        lift_to_drag=TaggedValue(value=lift_to_drag, provenance=ProvenanceTag(ValidationLevel.ASSERTED, notes=note), unit=""),
    )


def _cross_track_nmi(lat1, lon1, lat2, lon2, lat3, lon3) -> float:
    """Signed cross-track distance (nmi) of point 3 from the great circle 1->2.

    Positive = right of track (looking along 1->2). Spherical, EARTH mean radius.
    """
    r = EARTH.mean_radius
    d13 = _great_circle_distance_m(lat1, lon1, lat3, lon3) / r
    brg12 = great_circle_bearing(lat1, lon1, lat2, lon2)
    brg13 = great_circle_bearing(lat1, lon1, lat3, lon3)
    return math.asin(math.sin(d13) * math.sin(brg13 - brg12)) * r / _NMI


def _great_circle_distance_m(lat1, lon1, lat2, lon2) -> float:
    """Haversine distance, meters, on the EARTH mean-radius sphere."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2.0 * EARTH.mean_radius * math.asin(min(1.0, math.sqrt(a)))


def _crossing_index(values: list[float], threshold: float, *, rising: bool,
                    start: int = 0) -> int | None:
    for i in range(max(1, start + 1), len(values)):
        lo, hi = values[i - 1], values[i]
        if rising and lo < threshold <= hi:
            return i
        if not rising and lo > threshold >= hi:
            return i
    return None


def run_replay(*, mass_kg: float, lift_to_drag: float, sign: float,
               density_factor: float = 1.0, time_step: float = 0.1,
               max_time: float = 3000.0) -> dict:
    """One forward replay. Returns truth-comparison observables (never targets)."""
    vehicle = orion_vehicle(mass_kg, lift_to_drag)
    rel = relative_ei_state()
    # The EI (121.92 km) and skip arc live above the ISA's 86-km clamp, which the
    # first (clamped) run showed dominates everything: the clamp's ~300x density
    # overestimate at EI lofts the vehicle off the dense layers and it skips out
    # (documented in the gate report). All replays therefore use the US76 86-250 km
    # extension (VERIFIED_SOURCE, orp/core/atmosphere/us76_highalt.py).
    atmosphere: AtmosphericModel = US76HighAltitudeExtension(EARTH.atmosphere)
    if density_factor != 1.0:
        atmosphere = ScaledDensityAtmosphere(
            atmosphere, density_factor,
            "flight-informed variant per AAS 24-174 p.11 estimator statements")
    planet = dataclasses.replace(EARTH, atmosphere=atmosphere)
    aero = ConstantCoefficientCalculator(
        drag_coefficient=ORION_CD,
        lift_to_drag=lift_to_drag,
        provenance=vehicle.lift_to_drag.provenance,
    )
    conditions = SimulationConditions(
        vehicle=vehicle,
        planet=planet,
        bank_schedule=load_digitized_schedule(sign),
        aerodynamic_calculator=aero,
        entry_velocity=rel.velocity,
        entry_flight_path_angle=rel.flight_path_angle,
        entry_heading=rel.heading,
        entry_latitude=math.radians(EI_LATITUDE_DEG),
        entry_longitude=math.radians(EI_LONGITUDE_DEG),
        entry_altitude=EI_ALTITUDE_FT * _FT,
        time_step=time_step,
        max_simulation_time=max_time,
        ground_altitude=0.0,
    )
    branch = SimulationEngine().simulate(conditions).get_branch(0)
    t = branch.get(fd.TYPE_TIME)
    h = branch.get(fd.TYPE_ALTITUDE)
    lat = branch.get(fd.TYPE_LATITUDE)
    lon = branch.get(fd.TYPE_LONGITUDE)
    drag = branch.get(fd.TYPE_DRAG_FORCE)

    # --- skip apogee: first dip bottom, then the max of the post-dip arc --------------
    i_dip = min(range(len(h)), key=lambda i: h[i] if t[i] < 500.0 else float("inf"))
    i_apo = max(range(i_dip, len(h)), key=lambda i: h[i])
    skip_apogee_kft = h[i_apo] / _FT / 1000.0
    dipped_and_rose = h[i_apo] > h[i_dip] + 1000.0
    returned = h[-1] < 5_000.0  # reached the surface region before max_simulation_time

    # --- phase proxies: drag acceleration through 6 ft/s^2 ----------------------------
    drag_acc_ftps2 = [d / mass_kg / _FT for d in drag]
    i_first_peak = max(range(len(t)), key=lambda i: drag_acc_ftps2[i] if t[i] < 300.0 else -1.0)
    i_fall = _crossing_index(drag_acc_ftps2, DRAG_THRESHOLD_FTPS2, rising=False, start=i_first_peak)
    i_rise = _crossing_index(drag_acc_ftps2, DRAG_THRESHOLD_FTPS2, rising=True,
                             start=i_fall if i_fall is not None else 0)
    # first-pulse diagnostics vs Fig 10(a) callout (flight 1st peak 4.03 g) and the
    # vis-viva exit speed a 287.4-kft apogee implies (~7.87 km/s)
    g0 = 9.80665
    first_peak_g = drag_acc_ftps2[i_first_peak] * _FT / g0
    v = branch.get(fd.TYPE_VELOCITY)
    exit_v_mps = v[i_fall] if i_fall is not None else float("nan")

    # --- endpoint misses at the Table-4 altitude crossings (descending, post-skip) ----
    endpoints = {}
    for name, ep in TABLE4_ENDPOINTS.items():
        h_target = ep["altitude_ft"] * _FT
        idx = None
        for i in range(i_apo + 1, len(h)):
            if h[i - 1] > h_target >= h[i]:
                idx = i
                break
        if idx is None and name == "splashdown" and h[-1] <= h_target + 5.0:
            idx = len(h) - 1
        if idx is None:
            endpoints[name] = None
            continue
        lat_t = math.radians(ep["latitude_deg"])
        lon_t = math.radians(ep["longitude_deg"])
        lat_s = math.radians(lat[idx])
        lon_s = math.radians(lon[idx])
        miss_nmi = _great_circle_distance_m(lat_t, lon_t, lat_s, lon_s) / _NMI
        xtrack = _cross_track_nmi(
            math.radians(EI_LATITUDE_DEG), math.radians(EI_LONGITUDE_DEG),
            math.radians(TABLE4_ENDPOINTS["splashdown"]["latitude_deg"]),
            math.radians(TABLE4_ENDPOINTS["splashdown"]["longitude_deg"]),
            lat_s, lon_s)
        endpoints[name] = {"t_s": t[idx], "miss_nmi": miss_nmi,
                           "cross_track_nmi": xtrack,
                           "lat_deg": lat[idx], "lon_deg": lon[idx]}

    return {
        "mass_kg": mass_kg, "lift_to_drag": lift_to_drag, "sign": sign,
        "density_factor": density_factor,
        "v_rel_mps": rel.velocity,
        "gamma_rel_deg": math.degrees(rel.flight_path_angle),
        "heading_rel_deg": math.degrees(rel.heading),
        "skip_apogee_kft": skip_apogee_kft,
        "t_apogee_s": t[i_apo],
        "dipped_and_rose": dipped_and_rose,
        "returned": returned,
        "t_drag_fall6_s": t[i_fall] if i_fall is not None else None,
        "t_drag_rise6_s": t[i_rise] if i_rise is not None else None,
        "t_first_peak_s": t[i_first_peak],
        "first_peak_g": first_peak_g,
        "exit_v_mps": exit_v_mps,
        "endpoints": endpoints,
        "t_end_s": t[-1], "h_end_m": h[-1],
    }


def lock_sign_convention(*, mass_kg: float = 10160.5, lift_to_drag: float = 0.25) -> dict:
    """Replay both figure-to-ORP sign mappings; the drogue-point crossrange decides."""
    runs = {s: run_replay(mass_kg=mass_kg, lift_to_drag=lift_to_drag, sign=s)
            for s in (+1.0, -1.0)}
    misses = {}
    for s, r in runs.items():
        ep = r["endpoints"].get("drogue_deploy")
        misses[s] = abs(ep["cross_track_nmi"] -
                        _truth_cross_track("drogue_deploy")) if ep else float("inf")
    correct = min(misses, key=misses.get)
    wrong = -correct
    ratio = misses[wrong] / misses[correct] if misses[correct] > 0 else float("inf")
    return {"runs": runs, "crossrange_residual_nmi": misses,
            "locked_sign": correct, "ratio": ratio,
            "locked": ratio >= SIGN_LOCK_MIN_RATIO}


def _truth_cross_track(name: str) -> float:
    """Cross-track (nmi) of a Table-4 truth point relative to the EI->splashdown track."""
    ep = TABLE4_ENDPOINTS[name]
    return _cross_track_nmi(
        math.radians(EI_LATITUDE_DEG), math.radians(EI_LONGITUDE_DEG),
        math.radians(TABLE4_ENDPOINTS["splashdown"]["latitude_deg"]),
        math.radians(TABLE4_ENDPOINTS["splashdown"]["longitude_deg"]),
        math.radians(ep["latitude_deg"]), math.radians(ep["longitude_deg"]))


def run_matrix(sign: float) -> list[dict]:
    """Mass x L/D sweep (sourced ranges) at the locked sign, nominal atmosphere."""
    return [run_replay(mass_kg=m, lift_to_drag=ld, sign=sign)
            for m in MASS_SWEEP_KG for ld in LD_SWEEP]


def run_flight_informed(sign: float) -> dict:
    """0.90x density / 0.95x L/D variant per the paper's estimator findings (p.11)."""
    return run_replay(mass_kg=10160.5, lift_to_drag=0.25 * INFORMED_LD_FACTOR,
                      sign=sign, density_factor=INFORMED_DENSITY_FACTOR)


def _fmt_run(r: dict) -> str:
    ep = r["endpoints"]
    def m(name, key="miss_nmi"):
        return f"{ep[name][key]:8.1f}" if ep.get(name) else "    n/a "
    return (f"m={r['mass_kg']:7.1f} L/D={r['lift_to_drag']:5.3f} rho_x={r['density_factor']:4.2f} "
            f"sgn={r['sign']:+.0f} | pk1 {r['first_peak_g']:4.2f} g exitV {r['exit_v_mps']:6.0f} | "
            f"apo {r['skip_apogee_kft']:7.1f} kft returned={r['returned']} | "
            f"fall6 {r['t_drag_fall6_s'] or float('nan'):6.1f} rise6 {r['t_drag_rise6_s'] or float('nan'):6.1f} | "
            f"drogue miss {m('drogue_deploy')} xtk {m('drogue_deploy', 'cross_track_nmi')} | "
            f"splash miss {m('splashdown')}")


if __name__ == "__main__":  # pragma: no cover
    print("=" * 100)
    print("GATE 3 REPLAY: Artemis I digitized bank command, forward replay (rotation ON)")
    print("Tolerances pre-registered in module docstring BEFORE any comparison. Never tuned.")
    print("=" * 100)
    rel = relative_ei_state()
    print(f"\nEI relative state: V {rel.velocity:.1f} m/s, gamma {math.degrees(rel.flight_path_angle):.4f} deg, "
          f"az {math.degrees(rel.heading):.4f} deg")
    print(f"Truths: skip apogee {SKIP_APOGEE_KFT_FLIGHT} kft; Ballistic {TABLE2_PHASE_TIMES['PredGuid Ballistic'][0]} s; "
          f"Final {TABLE2_PHASE_TIMES['PredGuid Final'][0]} s; FBC chute 950.125 s; Table-4 endpoints.")

    print("\n--- SIGN-CONVENTION LOCK (midpoint vehicle, nominal atmosphere) ---")
    lock = lock_sign_convention()
    for s in (+1.0, -1.0):
        print(f"  sign {s:+.0f}: {_fmt_run(lock['runs'][s])}")
    print(f"  crossrange residual vs truth (drogue): +1 -> {lock['crossrange_residual_nmi'][+1.0]:.1f} nmi, "
          f"-1 -> {lock['crossrange_residual_nmi'][-1.0]:.1f} nmi")
    print(f"  LOCKED SIGN: {lock['locked_sign']:+.0f} (ratio {lock['ratio']:.1f} "
          f">= {SIGN_LOCK_MIN_RATIO} required -> locked={lock['locked']})")

    sgn = lock["locked_sign"]
    print(f"\n--- MASS x L/D SWEEP (sourced ranges, sign {sgn:+.0f}, nominal ISA) ---")
    rows = run_matrix(sgn)
    for r in rows:
        print("  " + _fmt_run(r))

    print(f"\n--- FLIGHT-INFORMED VARIANT (0.90x density, 0.95x L/D, sign {sgn:+.0f}) ---")
    fi = run_flight_informed(sgn)
    print("  " + _fmt_run(fi))

    print("\n(Full comparison + pass/fail vs pre-registered tolerances: "
          "docs/gates/gate3_artemis_replay.md)")
