# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Gate 3 Artemis scaffold and the Orion vehicle definition.

These assert the scaffold is honest by construction: declared NOT_VALIDATED, the inertial→
relative conversion lands inside the lateral corridor, the bank schedule refuses (the
convention-laundering rule), and orion.yaml is fully tagged with its NOT_VALIDATED weakest
link being the un-digitized trim attitude.
"""

from __future__ import annotations

import pytest

from orp.gates import gate3_artemis as g3
from orp.core.provenance.tags import ValidationLevel
from orp.core.vehicles import VehicleLibrary


class TestGate3Scaffold:
    def test_status_not_validated(self) -> None:
        assert g3.GATE3_STATUS == "NOT_VALIDATED"

    def test_relative_ei_azimuth_near_2p42(self) -> None:
        from orp.core.frames import Frame

        rel = g3.relative_ei_state()
        assert rel.frame is Frame.PLANET_RELATIVE
        import math

        assert math.degrees(rel.heading) == pytest.approx(2.42, abs=0.05)
        assert rel.velocity < g3.EI_VELOCITY_INERTIAL_FTPS * g3._FT  # rotation removed

    def test_splashdown_bearing_and_corridor(self) -> None:
        chk = g3.lateral_corridor_check()
        assert chk["splashdown_bearing_deg"] == pytest.approx(2.20, abs=0.1)
        assert chk["within_corridor"] is True
        assert chk["residual_deg"] < g3.LATERAL_CORRIDOR_DEG

    def test_bank_schedule_refuses(self) -> None:
        # The convention-laundering rule: reversal times do not lock a sign convention.
        with pytest.raises(NotImplementedError, match="convention"):
            g3.bank_schedule()

    def test_truth_tables_encoded(self) -> None:
        assert len(g3.TABLE2_PHASE_TIMES) == 6
        assert len(g3.TABLE3_BANK_REVERSAL_TIMES) == 6
        assert set(g3.TABLE4_ENDPOINTS) == {"drogue_deploy", "main_deploy", "splashdown"}
        assert g3.SKIP_APOGEE_KFT_FLIGHT == 287.4
        assert g3.LATERAL_CORRIDOR_DEG == pytest.approx(0.94018)


class TestOrionVehicle:
    def setup_method(self) -> None:
        self.orion = VehicleLibrary().load("orion")

    def test_loads_and_validates(self) -> None:
        self.orion.validate()
        assert self.orion.name == "Orion Crew Module"

    def test_mass_midpoint_of_design_range(self) -> None:
        # Midpoint of the McNamara 9934-10387 kg design range.
        assert self.orion.mass.get() == pytest.approx(10160.5, abs=0.5)
        assert self.orion.mass.level is ValidationLevel.ASSERTED
        assert "20140004224" in self.orion.mass.provenance.source

    def test_lift_to_drag_midpoint(self) -> None:
        assert self.orion.lift_to_drag.get() == pytest.approx(0.25, abs=0.005)

    def test_overall_provenance_not_validated_via_trim(self) -> None:
        # Weakest link is the un-digitized trim attitude -> scaffold is honestly NOT_VALIDATED.
        assert self.orion.trim_angle_of_attack.level is ValidationLevel.NOT_VALIDATED
        assert self.orion.provenance.level is ValidationLevel.NOT_VALIDATED

    def test_every_property_tagged(self) -> None:
        for name, tv in self.orion.tagged_values().items():
            assert tv.provenance.level in set(ValidationLevel)
            # sourced properties carry a citation; the NOT_VALIDATED placeholder need not.
            if tv.level is not ValidationLevel.NOT_VALIDATED:
                assert tv.provenance.source != "", f"{name} missing source"
