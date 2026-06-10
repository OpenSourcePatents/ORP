# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mars atmosphere — isothermal hydrostatic exponential model (CO₂).

Mars' thin CO₂ atmosphere is well approximated for entry work by an isothermal exponential:
pressure falls as ``P(h) = P₀·exp(−h/H)`` with scale height ``H = R·T/g``, density follows
from the ideal-gas relation on :class:`~orp.core.atmosphere.model.AtmosphericConditions`.

Surface anchor and the canonical-value inconsistency
----------------------------------------------------
The three most-quoted Mars surface values — T ≈ 210 K, P ≈ 636 Pa (6.36 mbar), and
ρ ≈ 0.020 kg/m³ — are **not mutually consistent** under the ideal-gas law for CO₂
(``ρ = P/(R·T)``): 636 / (188.92·210) = 0.0160 kg/m³, not 0.020. The famous "6 mbar" surface
pressure is a hard lander measurement (Viking), so this model anchors on the directly-measured
**P₀ = 636 Pa and T₀ = 210 K** with the correct CO₂ gas constant, giving a surface density of
**0.0160 kg/m³**. This matches the density used by standard Mars-EDL exponential models
(ρ₀ ≈ 0.0159 kg/m³); the often-cited 0.020 kg/m³ is a rounded fact-sheet figure inconsistent
with the measured P and T, and is intentionally not reproduced. (To anchor instead on
ρ₀ = 0.020 exactly, one would have to report P₀ ≈ 793 Pa, contradicting the 6 mbar measurement.)
"""

from __future__ import annotations

import math

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["MarsAtmosphereModel"]

_R = 188.92  # specific gas constant of Mars CO₂-dominated air, J/(kg·K)
_GAMMA = 1.29  # ratio of specific heats for CO₂
_SURFACE_TEMPERATURE = 210.0  # K (mean surface temperature)
_SURFACE_PRESSURE = 636.0  # Pa (6.36 mbar, Viking-class surface measurement)
_SURFACE_GRAVITY = 3.72076  # m/s² (used only to set the hydrostatic scale height)
_SCALE_HEIGHT = _R * _SURFACE_TEMPERATURE / _SURFACE_GRAVITY  # ≈ 10 663 m


class MarsAtmosphereModel(AtmosphericModel):
    """Isothermal exponential model of the Martian CO₂ atmosphere.

    Surface conditions are anchored to lander measurements; the isothermal exponential is the
    standard engineering profile used for Mars entry. The real atmosphere has substantial
    temperature structure aloft (a Mars-GRAM table or two-segment fit is the refinement seam),
    but the surface density and scale height — what dominate entry dynamics — are captured.
    """

    SPECIFIC_GAS_CONSTANT: float = _R
    SPECIFIC_HEAT_RATIO: float = _GAMMA
    SURFACE_TEMPERATURE: float = _SURFACE_TEMPERATURE
    SURFACE_PRESSURE: float = _SURFACE_PRESSURE
    SCALE_HEIGHT: float = _SCALE_HEIGHT
    MAX_ALTITUDE: float = 125_000.0

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return Mars conditions at ``altitude_msl`` meters above the reference areoid.

        Isothermal: ``T = T₀``. Hydrostatic exponential: ``P = P₀·exp(−h/H)`` with
        ``H = R·T₀/g``. Density follows from the ideal-gas relation. Altitudes below the datum
        (Mars has terrain down to roughly −8 km) are handled by the same exponential.
        """
        pressure = _SURFACE_PRESSURE * math.exp(-altitude_msl / _SCALE_HEIGHT)
        return AtmosphericConditions(
            temperature=_SURFACE_TEMPERATURE,
            pressure=pressure,
            specific_gas_constant=_R,
            specific_heat_ratio=_GAMMA,
        )

    def get_max_altitude(self) -> float:
        return self.MAX_ALTITUDE

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(
            level=ValidationLevel.VERIFIED_FLIGHT,
            source="NASA Mars Fact Sheet / Viking lander surface measurements (P≈636 Pa, T≈210 K)",
            notes=(
                "Surface P, T anchored to lander measurements; CO₂ ideal gas gives ρ₀=0.0160 "
                "kg/m³ (≈ standard EDL value 0.0159; the quoted 0.020 is a rounded, "
                "ideal-gas-inconsistent fact-sheet figure). Isothermal exponential profile "
                "aloft is an engineering approximation (Mars-GRAM profile is the refinement)."
            ),
        )
