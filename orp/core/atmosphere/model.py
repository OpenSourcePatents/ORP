# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The atmospheric-model interface and its value object.

Mirrors OpenRocket's ``AtmosphericModel`` / ``AtmosphericConditions`` split: the model is a
pure function of altitude returning an immutable conditions value, and all other gas
quantities are derived from temperature, pressure, and the gas's two thermodynamic
constants (so the same value object serves Earth air and Mars CO₂).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from orp.core.provenance.tags import ProvenanceTag

__all__ = ["AtmosphericModel", "AtmosphericConditions"]


@dataclass(frozen=True)
class AtmosphericConditions:
    """Immutable thermodynamic state of the atmosphere at one altitude.

    Stores the two primary state variables (temperature, pressure) plus the gas's two
    thermodynamic constants; everything else is derived exactly from those via standard
    relations. Carrying the gas constants on the value object is what makes the type
    planet-agnostic: an Earth-air sample and a Mars-CO₂ sample are the same type with
    different constants. The gas constants have **no defaults** on purpose — every
    construction must declare its gas, so a Mars sample can never silently inherit Earth-air
    thermodynamics. (Each concrete model supplies them; see ``EarthISAModel`` / ``MarsAtmosphereModel``.)

    Attributes:
        temperature: Static temperature, kelvin.
        pressure: Static pressure, pascals.
        specific_gas_constant: Specific gas constant ``R`` of the local gas, J/(kg·K).
        specific_heat_ratio: Ratio of specific heats ``γ`` of the local gas (dimensionless).
    """

    temperature: float
    pressure: float
    specific_gas_constant: float
    specific_heat_ratio: float

    @property
    def density(self) -> float:
        """Mass density ρ = P / (R·T), kg/m³ (ideal gas). Zero if T or R is non-positive."""
        if self.temperature <= 0.0 or self.specific_gas_constant <= 0.0:
            return 0.0
        return self.pressure / (self.specific_gas_constant * self.temperature)

    @property
    def speed_of_sound(self) -> float:
        """Speed of sound a = √(γ·R·T), m/s. Zero if T or R is non-positive."""
        if self.temperature <= 0.0 or self.specific_gas_constant <= 0.0:
            return 0.0
        return math.sqrt(self.specific_heat_ratio * self.specific_gas_constant * self.temperature)

    @property
    def dynamic_viscosity(self) -> float:
        """Dynamic viscosity μ, Pa·s.

        --- PHYSICS SEAM ---
        Returns 0.0 (placeholder, like every other physics seam). Viscosity is gas-specific,
        so a correct implementation must be driven by the gas rather than hardcoded for air.
        Real form (Sutherland): ``μ = μ₀·(T/T₀)^1.5·(T₀+S)/(T+S)`` with per-gas constants
        (air: ``μ₀=1.716e-5``, ``T₀=273.15``, ``S=110.4``). When implemented, carry the
        Sutherland constants per gas (e.g. alongside ``R`` and ``γ``) so Mars CO₂ is correct.
        Feeds only the Reynolds number in
        :class:`~orp.core.aerodynamics.flight_conditions.FlightConditions`; with placeholder
        aerodynamics it does not affect the trajectory.
        """
        # SEAM: gas-specific Sutherland viscosity replaces this zero.
        return 0.0

    @property
    def kinematic_viscosity(self) -> float:
        """Kinematic viscosity ν = μ / ρ, m²/s. Zero if density is zero."""
        rho = self.density
        if rho <= 0.0:
            return 0.0
        return self.dynamic_viscosity / rho


class AtmosphericModel(ABC):
    """Interface for an atmosphere: altitude → :class:`AtmosphericConditions`.

    Concrete models are pure functions of mean-sea-level (areoid for Mars) altitude — there
    is no time or horizontal-position dependence, matching the reentry use case where the
    descent is short compared with weather timescales.
    """

    @abstractmethod
    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return atmospheric conditions at ``altitude_msl`` (meters above the reference).

        Args:
            altitude_msl: Geometric altitude above mean sea level / reference areoid, m.

        Returns:
            The :class:`AtmosphericConditions` at that altitude.
        """

    @abstractmethod
    def get_max_altitude(self) -> float:
        """Return the altitude (m) above which the model is no longer considered valid."""

    @property
    @abstractmethod
    def provenance(self) -> ProvenanceTag:
        """Validation level and citation for this atmospheric model."""
