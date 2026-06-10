# SPDX-License-Identifier: GPL-3.0-or-later
# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
"""Gate 3 — Artemis I (Orion) skip entry. NOT_VALIDATED scaffold.

Primary source: AAS 24-174, "Orion Artemis I Entry Performance," NTRS 20240000024.

WHAT THIS IS. A scaffold that encodes the AAS 24-174 sourced entry-interface state and
truth data and performs the *one* conversion that is unambiguously correct — converting the
published INERTIAL EI velocity/FPA/azimuth (Table 1) to ORP's canonical planet-relative
frame (orp.core.frames). It then checks that the relative azimuth lands inside the published
lateral corridor of the great-circle bearing to the Table 4 splashdown point. It is NOT a
validated trajectory: the bank-angle command (Fig 12(a)) is figure-only and not digitized,
so no forward skip trajectory is integrated and no apogee/endpoint is claimed.

SOURCED TRUTH DATA (all from AAS 24-174 text/tables):
  - Table 1: entry-interface state (inertial).
  - Table 2: PredGuid phase-transition times (s relative to EI), flight vs predicted.
  - Table 3: bank-reversal initiation times (s relative to EI), flight vs predicted.
  - Table 4: drogue / main / splashdown coordinates and altitudes.
  - skip apogee 287.4 kft (flight) / 293.5 kft (predicted).
  - lateral corridor ("Lateral Angle") = 0.94018 deg.

WHY THE BANK SCHEDULE REFUSES (the convention-laundering rule). Table 3 gives the bank
reversal *times* but NOT the initial bank *sign*. Reconstructing a bank schedule from
reversal times alone requires guessing the initial sign, and a guessed sign does not lock a
sign convention — it launders an assumption into apparent precision. Replaying a *known*
schedule is in scope (forward-only); fabricating one from reversal times is not. So
bank_schedule() raises NotImplementedError pending human digitization of Fig 12(a).

VALIDATION STATUS: NOT_VALIDATED. No flight trajectory comparison is made.
"""

from __future__ import annotations

import math

from orp.core.frames import (
    ConvertedEntryState,
    great_circle_bearing,
    inertial_to_planet_relative,
)
from orp.core.planet import EARTH

GATE3_STATUS = "NOT_VALIDATED"  # scaffold: bank command (Fig 12(a)) un-digitized

_FT = 0.3048

# ---------------- AAS 24-174 Table 1 — entry-interface state (INERTIAL) ----------------
EI_ALTITUDE_FT = 400000.0
EI_LATITUDE_DEG = -25.82847
EI_LONGITUDE_DEG = -120.08071
EI_VELOCITY_INERTIAL_FTPS = 36062.65680
EI_FPA_INERTIAL_DEG = -5.66367  # inertial topocentric flight-path angle
EI_AZIMUTH_INERTIAL_DEG = 4.65389  # inertial topocentric azimuth
EI_RANGE_TO_TARGET_NMI = 3176.65

# ---------------- AAS 24-174 Table 2 — PredGuid phase transition times (s rel. EI) ----
# name: (artemis_i_flight_s, predicted_s)
TABLE2_PHASE_TIMES: dict[str, tuple[float, float]] = {
    "PredGuid Initial Roll": (1.475, 3.00),
    "PredGuid Energy Management": (83.475, 82.00),
    "PredGuid Up Control": (102.475, 100.00),
    "PredGuid Ballistic": (256.450, 255.00),
    "PredGuid Final": (551.425, 560.00),
    "PredGuid Terminal": (882.400, 877.00),
}

# ---------------- AAS 24-174 Table 3 — bank reversal initiation times (s rel. EI) ------
# reversal_number: (artemis_i_flight_s, predicted_s)
TABLE3_BANK_REVERSAL_TIMES: dict[int, tuple[float, float]] = {
    1: (115.475, 113.0),
    2: (390.450, 248.0),
    3: (713.425, 707.0),
    4: (793.425, 782.0),
    5: (827.425, 819.0),
    6: (864.400, 854.0),
}

# ---------------- AAS 24-174 Table 4 — chute/splashdown coordinates --------------------
# event: {altitude_ft, latitude_deg, longitude_deg}
TABLE4_ENDPOINTS: dict[str, dict[str, float]] = {
    "drogue_deploy": {"altitude_ft": 22273.99, "latitude_deg": 27.34817, "longitude_deg": -118.12188},
    "main_deploy": {"altitude_ft": 6352.48, "latitude_deg": 27.35166, "longitude_deg": -118.11144},
    "splashdown": {"altitude_ft": 0.0, "latitude_deg": 27.34852, "longitude_deg": -118.10181},
}

# ---------------- AAS 24-174 — scalar truths ------------------------------------------
SKIP_APOGEE_KFT_FLIGHT = 287.4
SKIP_APOGEE_KFT_PREDICTED = 293.5
LATERAL_CORRIDOR_DEG = 0.94018
LANDING_REQUIREMENT_NMI = 5.4


def relative_ei_state() -> ConvertedEntryState:
    """Convert the published inertial EI state (Table 1) to ORP's planet-relative frame.

    This is the one unambiguously-correct operation in the gate. Near escape speed the
    rotation correction is first-order, so the inertial→relative conversion is mandatory
    before any (future) integration.
    """
    return inertial_to_planet_relative(
        EARTH,
        velocity=EI_VELOCITY_INERTIAL_FTPS * _FT,
        flight_path_angle=math.radians(EI_FPA_INERTIAL_DEG),
        heading=math.radians(EI_AZIMUTH_INERTIAL_DEG),
        latitude=math.radians(EI_LATITUDE_DEG),
        altitude=EI_ALTITUDE_FT * _FT,
    )


def splashdown_bearing_deg() -> float:
    """Great-circle bearing (deg, clockwise from north) from EI to the splashdown point.

    Computed from the sourced Table 1 (EI) and Table 4 (splashdown) coordinates — a forward
    diagnostic relating the converted heading to where the vehicle actually landed.
    """
    splash = TABLE4_ENDPOINTS["splashdown"]
    return math.degrees(
        great_circle_bearing(
            math.radians(EI_LATITUDE_DEG),
            math.radians(EI_LONGITUDE_DEG),
            math.radians(splash["latitude_deg"]),
            math.radians(splash["longitude_deg"]),
        )
    )


def lateral_corridor_check() -> dict[str, float | bool]:
    """Relative azimuth vs splashdown bearing, and whether it sits inside the corridor."""
    az_rel_deg = math.degrees(relative_ei_state().heading)
    bearing_deg = splashdown_bearing_deg()
    residual = abs(az_rel_deg - bearing_deg)
    return {
        "relative_azimuth_deg": az_rel_deg,
        "splashdown_bearing_deg": bearing_deg,
        "residual_deg": residual,
        "corridor_deg": LATERAL_CORRIDOR_DEG,
        "within_corridor": residual < LATERAL_CORRIDOR_DEG,
    }


def bank_schedule():
    """The Artemis I bank command — REFUSES (NotImplementedError); see the convention rule.

    CONVENTION-LAUNDERING RULE: AAS 24-174 Table 3 gives the bank-reversal *times* but not
    the initial bank *sign*; the full bank command is Fig 12(a), which is figure-only. A
    schedule reconstructed from reversal times with a *guessed* initial sign does not lock a
    sign convention — it launders an assumption into false precision. Replaying a known
    schedule is in scope (forward-only); fabricating one is not. This slot refuses until
    Fig 12(a) is digitized by a human.
    """
    raise NotImplementedError(
        "Artemis I bank command is figure-only (AAS 24-174 Fig 12(a)); Table 3 gives reversal "
        "TIMES but not the initial SIGN. A guessed initial sign does not lock a sign "
        "convention (convention laundering). Bank schedule pending Fig 12(a) digitization -- "
        "Gate 3 NOT_VALIDATED."
    )


if __name__ == "__main__":  # pragma: no cover
    print("=" * 70)
    print(f"GATE 3: Artemis I (Orion) skip entry  --  STATUS: {GATE3_STATUS}")
    print("AAS 24-174 (NTRS 20240000024). SCAFFOLD ONLY: no skip trajectory integrated")
    print("(bank command Fig 12(a) un-digitized). Zero fabricated flight points.")
    print("=" * 70)
    rel = relative_ei_state()
    print("\nFrame conversion (inertial -> planet-relative), the one correct operation:")
    print(f"  inertial : V = {EI_VELOCITY_INERTIAL_FTPS * _FT:.1f} m/s, "
          f"gamma = {EI_FPA_INERTIAL_DEG:.5f} deg, az = {EI_AZIMUTH_INERTIAL_DEG:.5f} deg")
    print(f"  relative : V = {rel.velocity:.1f} m/s, "
          f"gamma = {math.degrees(rel.flight_path_angle):.5f} deg, "
          f"az = {math.degrees(rel.heading):.5f} deg")
    chk = lateral_corridor_check()
    print("\nLateral corridor check (relative azimuth vs splashdown bearing):")
    print(f"  relative azimuth   = {chk['relative_azimuth_deg']:.4f} deg")
    print(f"  splashdown bearing = {chk['splashdown_bearing_deg']:.4f} deg "
          f"(great-circle, EI -> Table 4 splashdown)")
    print(f"  residual {chk['residual_deg']:.4f} deg  vs corridor {chk['corridor_deg']:.4f} deg "
          f"-> within: {chk['within_corridor']}")
    print(f"\nTruth data encoded (not compared -- no trajectory): "
          f"{len(TABLE2_PHASE_TIMES)} phase times, {len(TABLE3_BANK_REVERSAL_TIMES)} bank "
          f"reversals, {len(TABLE4_ENDPOINTS)} endpoints, skip apogee {SKIP_APOGEE_KFT_FLIGHT} kft.")
    print(f"\nRESULT: {GATE3_STATUS}. Bank command pending Fig 12(a) digitization.")
    try:
        bank_schedule()
    except NotImplementedError as exc:
        print(f"  bank_schedule() refuses: {exc}")
