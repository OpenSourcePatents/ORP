# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mars atmosphere — thin CO₂ atmosphere model."""

from __future__ import annotations

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["MarsAtmosphereModel"]


class MarsAtmosphereModel(AtmosphericModel):
    """Mars atmosphere (predominantly CO₂), extended to entry-interface altitudes.

    Mars-CO₂ gas constants (real, used to parameterize the seam):

    * specific gas constant ``R ≈ 188.92`` J/(kg·K) (CO₂)
    * ratio of specific heats ``γ ≈ 1.29`` (CO₂)
    * near-surface reference ``T ≈ 210`` K, ``P ≈ 610`` Pa

    Mars' surface pressure is roughly 0.6 % of Earth's, which is exactly why reentry
    aerothermodynamics differ so sharply between the two planets — and why the
    Planet/Vehicle abstraction is built in from the start.
    """

    SPECIFIC_GAS_CONSTANT: float = 188.92
    SPECIFIC_HEAT_RATIO: float = 1.29
    SURFACE_TEMPERATURE: float = 210.0
    SURFACE_PRESSURE: float = 610.0
    MAX_ALTITUDE: float = 120_000.0

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return Mars conditions at ``altitude_msl`` meters above the reference areoid.

        --- PHYSICS SEAM ---
        Returns near-surface reference conditions for *all* altitudes. The real model is
        commonly a two-segment fit (e.g. the Mars-GRAM-derived NASA glenn curve fit):
        lower (h < 7000 m) ``T = −31 − 0.000998·h`` °C; upper ``T = −23.4 − 0.00222·h`` °C;
        with ``P = 0.699·exp(−0.00009·h)`` kPa and density ``ρ = P/(0.1921·(T+273.1))``.
        Replace this seam with that fit (or a tabulated Mars-GRAM profile) and bump the
        provenance level accordingly.
        """
        # SEAM: ignore altitude_msl and return the near-surface reference profile.
        return AtmosphericConditions(
            temperature=self.SURFACE_TEMPERATURE,
            pressure=self.SURFACE_PRESSURE,
            specific_gas_constant=self.SPECIFIC_GAS_CONSTANT,
            specific_heat_ratio=self.SPECIFIC_HEAT_RATIO,
        )

    def get_max_altitude(self) -> float:
        return self.MAX_ALTITUDE

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.NOT_VALIDATED,
            source="NASA Glenn Mars atmosphere curve fit (target reference)",
            notes="Placeholder: returns near-surface reference at all altitudes (PHYSICS SEAM).",
        )
