# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the InSight rotation experiment.

Stage A's ω = 0 numbers are hard validation targets: the external reference ablation
produced peak 10.93 g and azimuth-independent crossrange 9.28 km for this exact
configuration, and reproducing them validates the experiment harness against an
independent implementation. The rotating-case assertions pin the *characterized
structure* (azimuth dependence, shift magnitudes of order 1–1.8 km, peak-g band) —
signed per-azimuth values are documented in docs/experiments/insight_rotation.md rather
than gated, because the external reference explicitly never locked its bank-sign
convention (see ref_core/lateral_insight.py). Stage B numbers are *reported* against
flight, not expected to match (every approximation is flagged); tests pin only its
structural facts.
"""

from __future__ import annotations

import pytest

from orp.experiments import insight_rotation as exp


@pytest.fixture(scope="module")
def stage_a_still():
    return {az: exp.run_stage_a(az, rotating=False) for az in (0.0, 90.0, 200.0)}


@pytest.fixture(scope="module")
def stage_a_rotating():
    return {az: exp.run_stage_a(az, rotating=True) for az in (0.0, 45.0, 90.0, 180.0)}


class TestStageAOmegaZero:
    """Harness validation against the external reference ablation (ω = 0)."""

    def test_allen_eggers_closed_form(self) -> None:
        # V²·sin|γ| / (2·e·H) for V=5500, γ=−12°, H=11100 — the analytic anchor.
        assert exp.ALLEN_EGGERS_PEAK_G == pytest.approx(10.63, abs=0.01)

    def test_peak_g_matches_external_reference(self, stage_a_still) -> None:
        for metrics in stage_a_still.values():
            assert metrics.peak_g == pytest.approx(exp.EXPECTED_OMEGA0_PEAK_G, abs=0.02)

    def test_crossrange_matches_external_reference(self, stage_a_still) -> None:
        for metrics in stage_a_still.values():
            assert metrics.crossrange_km == pytest.approx(
                exp.EXPECTED_OMEGA0_CROSSRANGE_KM, abs=0.02
            )

    def test_crossrange_is_azimuth_independent(self, stage_a_still) -> None:
        # Central gravity + spherical planet + ω = 0 is rotationally symmetric, so the
        # crossrange must not depend on the entry azimuth (observed spread ≪ 1 m).
        values = [m.crossrange_km for m in stage_a_still.values()]
        assert max(values) - min(values) < 0.005

    def test_full_physics_peak_exceeds_allen_eggers(self, stage_a_still) -> None:
        # AE neglects gravity-along-track and γ evolution; full physics sits above it
        # here (10.93 vs 10.63), exactly as the external reference found.
        for metrics in stage_a_still.values():
            assert metrics.peak_g > exp.ALLEN_EGGERS_PEAK_G


class TestStageARotation:
    """Characterized rotation effects (2026-06-10): structure gated, signs documented."""

    def test_crossrange_becomes_azimuth_dependent(self, stage_a_rotating) -> None:
        shifts = [
            m.crossrange_km - exp.EXPECTED_OMEGA0_CROSSRANGE_KM
            for m in stage_a_rotating.values()
        ]
        # ω = 0 spread is < 5 m; with rotation the spread across azimuths is km-scale.
        assert max(shifts) - min(shifts) > 1.0

    def test_shift_magnitudes_are_order_1_to_1p8_km(self, stage_a_rotating) -> None:
        # External reference: omitted rotating-frame terms are "order 1.0-1.8 km" of
        # crossrange. Characterized here: |shift| = 1.51, 1.68, 1.04 km at azimuths
        # 0/45/90 (and ≤ 0.81 km at 135-270). Gate the peak of the effect.
        shifts = {
            az: abs(m.crossrange_km - exp.EXPECTED_OMEGA0_CROSSRANGE_KM)
            for az, m in stage_a_rotating.items()
        }
        assert max(shifts.values()) == pytest.approx(1.68, abs=0.25)
        for az in (0.0, 45.0, 90.0):
            assert 0.9 <= shifts[az] <= 1.9

    def test_peak_g_shifts_by_up_to_a_g(self, stage_a_rotating) -> None:
        # Characterized band across all azimuths: 10.11-11.65 g (external reference
        # recorded "order 0.5-0.8 g" of peak-g shift; both signs occur by azimuth).
        for metrics in stage_a_rotating.values():
            assert 10.0 <= metrics.peak_g <= 11.8
        shifts = [abs(m.peak_g - exp.EXPECTED_OMEGA0_PEAK_G) for m in stage_a_rotating.values()]
        assert max(shifts) > 0.5


class TestStageBFullModels:
    """Structural facts only — stage B is reported against flight, not gated to it."""

    def test_zero_lift_gives_zero_crossrange_without_rotation(self) -> None:
        metrics = exp.run_stage_b(0.0, rotating=False)
        # Trim α = 0 ⇒ Newtonian L/D = 0 ⇒ the σ=160° bank rotates a zero lift vector:
        # no rotation, no lift ⇒ the trajectory stays in its initial plane.
        assert abs(metrics.crossrange_km) < 0.01
        assert 5.0 < metrics.peak_g < 10.0  # reported vs flight 8.13 g, not gated

    def test_rotation_alone_produces_crossrange(self) -> None:
        metrics = exp.run_stage_b(0.0, rotating=True)
        # Characterized 2026-06-10: +2.26 km at azimuth 0 — rotation is the only
        # lateral mechanism available to a zero-lift static-trim model (flight: 6.1 km,
        # driven by rolling lift this model cannot represent; flagged, not tuned).
        assert abs(metrics.crossrange_km) > 0.5
        assert 5.0 < metrics.peak_g < 10.0
        assert 0.0 < metrics.stop_altitude_m < 20_000.0
