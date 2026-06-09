# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Earth atmosphere — International Standard Atmosphere (ISA) model."""

from __future__ import annotations

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["EarthISAModel"]


class EarthISAModel(AtmosphericModel):
    """International Standard Atmosphere for Earth, extended to reentry altitudes.

    Earth-air gas constants (real, used to parameterize the seam):

    * specific gas constant ``R = 287.053`` J/(kg·K)
    * ratio of specific heats ``γ = 1.4``
    * sea-level standard ``T₀ = 288.15`` K, ``P₀ = 101325`` Pa
    """

    SPECIFIC_GAS_CONSTANT: float = 287.053
    SPECIFIC_HEAT_RATIO: float = 1.4
    SEA_LEVEL_TEMPERATURE: float = 288.15
    SEA_LEVEL_PRESSURE: float = 101325.0
    MAX_ALTITUDE: float = 120_000.0  # ~entry interface; ISA layer set extends to ~86 km

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return ISA conditions at ``altitude_msl`` meters above mean sea level.

        --- PHYSICS SEAM ---
        Returns sea-level standard conditions for *all* altitudes. The real model converts
        geometric→geopotential altitude (``h_geo = R_e·h/(R_e+h)``, ``R_e=6356766 m``),
        locates the ISA layer (troposphere lapse −6.5 K/km to 11 km; isothermal tropopause
        to 20 km; +1.0 K/km to 32 km; +2.8 K/km to 47 km; isothermal to 51 km; −2.8 K/km to
        71 km; −2.0 K/km to 84.852 km), interpolates temperature by the layer lapse rate,
        and integrates the barometric formula for pressure
        (``P = P_b·(1 + Δh·L/T_b)^(−g/(L·R))`` non-isothermal; ``P = P_b·exp(−Δh·g/(R·T_b))``
        isothermal), chaining base pressures up the layers. ``g = 9.80665`` m/s².
        """
        # SEAM: ignore altitude_msl and return the sea-level reference profile.
        return AtmosphericConditions(
            temperature=self.SEA_LEVEL_TEMPERATURE,
            pressure=self.SEA_LEVEL_PRESSURE,
            specific_gas_constant=self.SPECIFIC_GAS_CONSTANT,
            specific_heat_ratio=self.SPECIFIC_HEAT_RATIO,
        )

    def get_max_altitude(self) -> float:
        return self.MAX_ALTITUDE

    @property
    def provenance(self) -> ProvenanceTag:
        # Placeholder profile → NOT_VALIDATED. Bump to ASSERTED (cite "U.S. Standard
        # Atmosphere, 1976") once the real ISA layer integration replaces the seam.
        return ProvenanceTag(
            level=ValidationLevel.NOT_VALIDATED,
            source="U.S. Standard Atmosphere, 1976 (target reference)",
            notes="Placeholder: returns sea-level reference at all altitudes (PHYSICS SEAM).",
        )
