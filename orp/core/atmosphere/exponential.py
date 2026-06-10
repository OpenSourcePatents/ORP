# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric exponential atmosphere — ``ρ(h) = ρ₀·exp(−h/H)``.

The classic analytically tractable entry atmosphere (the one Allen-Eggers and most
closed-form entry theory assume), parameterized directly by surface density ``ρ₀`` and
scale height ``H``. It is the natural bridge fixture for comparing ORP against external
reference implementations that use the same two-parameter model with matched inputs.

ORP's :class:`~orp.core.atmosphere.model.AtmosphericConditions` stores temperature and
pressure with density derived from the ideal-gas law, so this model represents the target
density exactly by holding the (configurable) gas state isothermal and setting
``P(h) = ρ(h)·R·T``. The gas constants also give a physically meaningful speed of sound —
e.g. CO₂ at 210 K for a Mars-like configuration — so Mach-based analyses work.

Like every ORP model it carries provenance, supplied by the caller: a parametric
atmosphere is only as trustworthy as wherever its ρ₀ and H came from (default
``NOT_VALIDATED``).
"""

from __future__ import annotations

import math

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["ExponentialAtmosphere"]


class ExponentialAtmosphere(AtmosphericModel):
    """Isothermal exponential-density atmosphere with caller-chosen parameters.

    Args:
        rho0: Surface (reference) density ρ₀, kg/m³. Zero gives a vacuum.
        scale_height: Density scale height H, m. Must be positive.
        temperature: Isothermal gas temperature, K (sets the speed of sound).
        specific_gas_constant: Specific gas constant R of the gas, J/(kg·K).
        specific_heat_ratio: Ratio of specific heats γ of the gas.
        max_altitude: Altitude above which the model is considered invalid, m
            (informational; the exponential is evaluated at any altitude).
        provenance: Where ρ₀ and H came from. Defaults to ``NOT_VALIDATED``.

    The default gas is Earth air; for a Mars-like CO₂ configuration pass
    ``temperature=210.0, specific_gas_constant=188.92, specific_heat_ratio=1.29``.
    Negative altitudes follow the same exponential (no clamping); callers comparing
    against references that clamp density below their datum should restrict the
    comparison to ``h ≥ 0``.
    """

    def __init__(
        self,
        rho0: float,
        scale_height: float,
        *,
        temperature: float = 288.15,
        specific_gas_constant: float = 287.0528,
        specific_heat_ratio: float = 1.4,
        max_altitude: float = float("inf"),
        provenance: ProvenanceTag | None = None,
    ) -> None:
        if rho0 < 0.0:
            raise ValueError(f"rho0 must be non-negative (got {rho0}).")
        if scale_height <= 0.0:
            raise ValueError(f"scale_height must be positive (got {scale_height}).")
        self._rho0 = float(rho0)
        self._scale_height = float(scale_height)
        self._temperature = float(temperature)
        self._gas_constant = float(specific_gas_constant)
        self._heat_ratio = float(specific_heat_ratio)
        self._max_altitude = float(max_altitude)
        self._provenance = (
            provenance
            if provenance is not None
            else ProvenanceTag(
                ValidationLevel.NOT_VALIDATED,
                notes="Unsourced exponential-atmosphere parameters.",
            )
        )

    @property
    def rho0(self) -> float:
        """Surface (reference) density ρ₀, kg/m³."""
        return self._rho0

    @property
    def scale_height(self) -> float:
        """Density scale height H, m."""
        return self._scale_height

    def density(self, altitude_msl: float) -> float:
        """Return ρ(h) = ρ₀·exp(−h/H), kg/m³ (the model's defining quantity)."""
        return self._rho0 * math.exp(-altitude_msl / self._scale_height)

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return isothermal conditions whose ideal-gas density equals :meth:`density`."""
        rho = self.density(altitude_msl)
        return AtmosphericConditions(
            temperature=self._temperature,
            pressure=rho * self._gas_constant * self._temperature,
            specific_gas_constant=self._gas_constant,
            specific_heat_ratio=self._heat_ratio,
        )

    def get_max_altitude(self) -> float:
        return self._max_altitude

    @property
    def provenance(self) -> ProvenanceTag:
        return self._provenance
