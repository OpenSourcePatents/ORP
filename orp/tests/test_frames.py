# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for inertial→planet-relative entry-state conversion (orp.core.frames).

The headline test is the Artemis I EI conversion: the AAS 24-174 Table 1 *inertial* state
must convert to a planet-relative azimuth near 2.42°, which lands inside the 0.94° lateral
corridor of the great-circle bearing (~2.20°) from EI to the Table 4 splashdown point. Both
the EI state and the splashdown coordinates are sourced from AAS 24-174 (NTRS 20240000024);
the bearing is computed from those coordinates, not hand-fed.
"""

from __future__ import annotations

import math

import pytest

from orp.core.frames import (
    Frame,
    FrameConversionError,
    great_circle_bearing,
    inertial_to_planet_relative,
)
from orp.core.planet import EARTH

_FT = 0.3048

# AAS 24-174 Table 1 — Artemis I entry-interface state (INERTIAL).
V_IN = 36062.6568 * _FT  # ft/s -> m/s = 10991.9 m/s
GAMMA_IN = math.radians(-5.66367)
AZ_IN = math.radians(4.65389)
LAT_EI = math.radians(-25.82847)
LON_EI = math.radians(-120.08071)
ALT_EI = 400000.0 * _FT
# AAS 24-174 Table 4 — splashdown coordinates.
SPLASH_LAT = math.radians(27.34852)
SPLASH_LON = math.radians(-118.10181)
# AAS 24-174 — lateral corridor ("Lateral Angle") = 0.94018 deg.
CORRIDOR_DEG = 0.94018


class TestInertialToRelativeArtemis:
    def setup_method(self) -> None:
        self.rel = inertial_to_planet_relative(
            EARTH,
            velocity=V_IN,
            flight_path_angle=GAMMA_IN,
            heading=AZ_IN,
            latitude=LAT_EI,
            altitude=ALT_EI,
        )

    def test_relative_azimuth_near_2p42_deg(self) -> None:
        assert math.degrees(self.rel.heading) == pytest.approx(2.42, abs=0.05)

    def test_relative_azimuth_within_lateral_corridor_of_splashdown_bearing(self) -> None:
        bearing_deg = math.degrees(
            great_circle_bearing(LAT_EI, LON_EI, SPLASH_LAT, SPLASH_LON)
        )
        # Computed bearing from sourced coordinates is ~2.2 deg.
        assert bearing_deg == pytest.approx(2.20, abs=0.1)
        # The converted relative azimuth lies inside the lateral corridor of that bearing.
        assert abs(math.degrees(self.rel.heading) - bearing_deg) < CORRIDOR_DEG

    def test_relative_speed_below_inertial(self) -> None:
        # Subtracting eastward rotation reduces the speed (small here: flight is near-meridional).
        assert self.rel.velocity < V_IN
        assert self.rel.velocity == pytest.approx(10966.0, abs=15.0)

    def test_relative_fpa_descending(self) -> None:
        assert self.rel.flight_path_angle < 0.0
        assert math.degrees(self.rel.flight_path_angle) == pytest.approx(-5.68, abs=0.05)

    def test_frame_tagged_and_carries_assumptions(self) -> None:
        assert self.rel.frame is Frame.PLANET_RELATIVE
        assert self.rel.assumptions  # audit trail of what the transform assumed


class TestRefusalNeverGuesses:
    @pytest.mark.parametrize("missing", ["velocity", "flight_path_angle", "heading", "latitude", "altitude"])
    def test_missing_required_datum_refuses(self, missing: str) -> None:
        kwargs = dict(
            velocity=V_IN,
            flight_path_angle=GAMMA_IN,
            heading=AZ_IN,
            latitude=LAT_EI,
            altitude=ALT_EI,
        )
        kwargs[missing] = None
        with pytest.raises(FrameConversionError):
            inertial_to_planet_relative(EARTH, **kwargs)


class TestGreatCircleBearing:
    def test_due_north(self) -> None:
        b = great_circle_bearing(0.0, 0.0, math.radians(10.0), 0.0)
        assert math.degrees(b) == pytest.approx(0.0, abs=1e-6)

    def test_due_east(self) -> None:
        b = great_circle_bearing(0.0, 0.0, 0.0, math.radians(10.0))
        assert math.degrees(b) == pytest.approx(90.0, abs=1e-6)
