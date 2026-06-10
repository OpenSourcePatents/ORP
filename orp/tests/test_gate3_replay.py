# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Gate-3 Artemis replay.

These tests PIN THE HONEST OUTCOME documented in docs/gates/gate3_artemis_replay.md:
the open-loop replay of the digitized closed-loop commands diverges in the skip (does
not return), the endpoint discriminator is unreachable, and the sign convention is not
locked. If a future model change (e.g. Mach-dependent aero) makes the replay return,
these pins are EXPECTED to fail and must be updated alongside the gate report.
"""

from __future__ import annotations

import math

import pytest

from orp.core.provenance.tags import ValidationLevel
from orp.gates import gate3_artemis_replay as gr

# One forward replay for the whole module (midpoint vehicle, nominal atmosphere).
_RUN = gr.run_replay(mass_kg=10160.5, lift_to_drag=0.25, sign=+1.0)


class TestPreRegisteredTolerances:
    def test_constants_unchanged(self) -> None:
        # Pre-registered before any comparison ran (module docstring); do not tune.
        assert gr.TOL_SKIP_APOGEE_KFT_NOMINAL == 30.0
        assert gr.TOL_SKIP_APOGEE_KFT_INFORMED == 20.0
        assert gr.TOL_ENDPOINT_MISS_NMI_NOMINAL == 250.0
        assert gr.TOL_ENDPOINT_MISS_NMI_INFORMED == 150.0
        assert gr.TOL_PHASE_PROXY_S_NOMINAL == 60.0
        assert gr.TOL_PHASE_PROXY_S_INFORMED == 40.0
        assert gr.SIGN_LOCK_MIN_RATIO == 3.0


class TestDigitizedSchedule:
    def test_loads_with_asserted_provenance(self) -> None:
        s = gr.load_digitized_schedule(+1.0)
        assert len(s) > 2000
        assert s.provenance.level is ValidationLevel.ASSERTED
        assert "MACHINE-DIGITIZED" in s.provenance.notes

    def test_initial_segment_is_the_15deg_limit(self) -> None:
        s = gr.load_digitized_schedule(+1.0)
        assert math.degrees(s.bank_angle_at(50.0)) == pytest.approx(14.9, abs=1.0)

    def test_sign_mapping_mirrors(self) -> None:
        sp = gr.load_digitized_schedule(+1.0)
        sm = gr.load_digitized_schedule(-1.0)
        for t in (50.0, 200.0, 500.0, 800.0):
            assert sp.bank_angle_at(t) == pytest.approx(-sm.bank_angle_at(t))

    def test_first_reversal_sign_flip(self) -> None:
        s = gr.load_digitized_schedule(+1.0)
        assert s.bank_angle_at(110.0) > 0.0
        assert s.bank_angle_at(125.0) < 0.0


class TestHonestDivergencePins:
    """Pin the documented FAIL so silent regressions are impossible."""

    def test_first_pass_underbleeds_flight(self) -> None:
        # Flight: 4.03 g first peak (Fig 10(a)), ~7.87 km/s exit. Replay falls short.
        assert 2.0 < _RUN["first_peak_g"] < 3.5
        assert _RUN["exit_v_mps"] > 8500.0

    def test_skips_out_and_never_returns(self) -> None:
        assert _RUN["dipped_and_rose"]
        assert not _RUN["returned"]
        assert _RUN["skip_apogee_kft"] > 10 * gr.SKIP_APOGEE_KFT_FLIGHT

    def test_endpoints_unreachable_so_sign_not_lockable(self) -> None:
        assert all(ep is None for ep in _RUN["endpoints"].values())

    def test_phase_proxy_outside_preregistered_tolerance(self) -> None:
        flight_ballistic_s = 256.450
        assert _RUN["t_drag_fall6_s"] is not None
        assert abs(_RUN["t_drag_fall6_s"] - flight_ballistic_s) > gr.TOL_PHASE_PROXY_S_NOMINAL


class TestCrossTrack:
    def test_signed_cross_track_geometry(self) -> None:
        # Point due-east of a northward track is to the RIGHT (positive).
        lat1, lon1 = 0.0, 0.0
        lat2, lon2 = math.radians(10.0), 0.0
        lat3, lon3 = math.radians(5.0), math.radians(1.0)
        assert gr._cross_track_nmi(lat1, lon1, lat2, lon2, lat3, lon3) > 0.0
        assert gr._cross_track_nmi(lat1, lon1, lat2, lon2, lat3, -lon3) < 0.0
