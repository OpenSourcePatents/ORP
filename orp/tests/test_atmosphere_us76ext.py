# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the US76 86-250 km high-altitude extension.

Node values are pinned to the defining document (NTRS 19770009539 Table I, printed
pp. 68-73, pixel-transcribed 2026-06-10). The 95-km interpolation check exercises the
log-linear choice against the document's own printed intermediate row.
"""

from __future__ import annotations

import pytest

from orp.core.atmosphere import EarthISAModel, US76HighAltitudeExtension
from orp.core.provenance.tags import ValidationLevel

ATM = US76HighAltitudeExtension()


class TestUS76Nodes:
    @pytest.mark.parametrize(
        "z_m, rho",
        [
            (86_000.0, 6.958e-6),
            (90_000.0, 3.416e-6),
            (100_000.0, 5.604e-7),
            (110_000.0, 9.708e-8),
            (120_000.0, 2.222e-8),
            (130_000.0, 8.152e-9),
            (150_000.0, 2.076e-9),
            (200_000.0, 2.541e-10),
            (250_000.0, 6.073e-11),
        ],
    )
    def test_node_densities_exact(self, z_m: float, rho: float) -> None:
        assert ATM.get_conditions(z_m).density == pytest.approx(rho, rel=1e-3)

    def test_interpolation_log_linear_reproduces_printed_95km_row(self) -> None:
        # Document prints rho(95 km) = 1.393e-6 (rho/rho0 1.137e-6 x 1.2250); the
        # 94/96-km log-midpoint reproduces it to better than 0.2%.
        assert ATM.get_conditions(95_000.0).density == pytest.approx(1.393e-6, rel=2e-3)

    def test_temperature_nodes(self) -> None:
        assert ATM.get_conditions(110_000.0).temperature == pytest.approx(240.00, abs=0.2)
        assert ATM.get_conditions(120_000.0).temperature == pytest.approx(360.00, abs=0.2)


class TestUS76Structure:
    def test_continuity_at_86km_with_base_isa(self) -> None:
        base = EarthISAModel()
        below = base.get_conditions(85_999.0).density
        above = ATM.get_conditions(86_001.0).density
        assert above == pytest.approx(below, rel=0.02)

    def test_monotonic_decrease_86_to_250(self) -> None:
        zs = range(86_000, 250_001, 1_000)
        rhos = [ATM.get_conditions(float(z)).density for z in zs]
        assert all(b < a for a, b in zip(rhos, rhos[1:]))

    def test_held_above_250km(self) -> None:
        r250 = ATM.get_conditions(250_000.0).density
        assert ATM.get_conditions(400_000.0).density == pytest.approx(r250)
        assert ATM.get_conditions(1_000_000.0).density == pytest.approx(r250)

    def test_below_86_delegates_to_base(self) -> None:
        base = EarthISAModel()
        assert ATM.get_conditions(50_000.0).density == pytest.approx(
            base.get_conditions(50_000.0).density)

    def test_provenance_verified_source(self) -> None:
        assert ATM.provenance.level is ValidationLevel.VERIFIED_SOURCE
        assert "19770009539" in ATM.provenance.source

    def test_clamp_pathology_removed(self) -> None:
        # The old clamp held 6.958e-6 at all altitudes above 86 km; the extension is
        # orders of magnitude thinner at the Artemis EI (121.92 km).
        assert ATM.get_conditions(121_920.0).density < 2.5e-8
