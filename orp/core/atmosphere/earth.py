# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Earth atmosphere — International Standard Atmosphere (ISA / U.S. Standard 1976).

Implements the seven-layer standard atmosphere from sea level to 86 km. Temperature is
piecewise-linear in geopotential altitude; pressure is the hydrostatic/barometric solution
within each layer; density and speed of sound follow from the ideal-gas relations on
:class:`~orp.core.atmosphere.model.AtmosphericConditions`.

Altitude convention: the input is treated as **geopotential** altitude (the variable in
which the ISA layer boundaries — 11 km, 20 km, … — are natively defined). This makes the
canonical boundary values exact (e.g. T = 216.65 K at 11 km). The geometric→geopotential
correction ``H = R_e·z/(R_e+z)`` is below 2.5 % at 86 km and is intentionally not applied,
so the model reproduces the standard tables; callers tracking geometric altitude may apply
:func:`geometric_to_geopotential` first if that last fraction of a percent matters.
"""

from __future__ import annotations

import math

from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["EarthISAModel", "geometric_to_geopotential"]

# ISA constants (U.S. Standard Atmosphere, 1976).
_R = 287.0528  # specific gas constant of dry air, J/(kg·K) (= R*/M0)
_GAMMA = 1.4  # ratio of specific heats for air
_G0 = 9.80665  # standard gravity used in the barometric formula, m/s²
_SEA_LEVEL_PRESSURE = 101325.0  # Pa
_EARTH_RADIUS_ISA = 6_356_766.0  # m, effective radius for geopotential conversion

# Layer base geopotential altitude (m), base temperature (K), lapse rate (K/m).
_LAYERS: tuple[tuple[float, float, float], ...] = (
    (0.0, 288.15, -0.0065),  # troposphere
    (11_000.0, 216.65, 0.0),  # tropopause (isothermal)
    (20_000.0, 216.65, 0.001),  # lower stratosphere
    (32_000.0, 228.65, 0.0028),  # upper stratosphere
    (47_000.0, 270.65, 0.0),  # stratopause (isothermal)
    (51_000.0, 270.65, -0.0028),  # lower mesosphere
    (71_000.0, 214.65, -0.0020),  # upper mesosphere
)
_TOP_ALTITUDE = 84_852.0  # m geopotential (~86 km geometric); top of the modelled region


def _compute_base_pressures() -> tuple[float, ...]:
    """Chain the barometric formula up the layers to get each layer's base pressure."""
    pressures = [_SEA_LEVEL_PRESSURE]
    for i in range(len(_LAYERS) - 1):
        h0, t0, lapse = _LAYERS[i]
        h1 = _LAYERS[i + 1][0]
        p0 = pressures[i]
        if abs(lapse) > 1e-12:
            t1 = t0 + lapse * (h1 - h0)
            pressures.append(p0 * (t1 / t0) ** (-_G0 / (lapse * _R)))
        else:
            pressures.append(p0 * math.exp(-_G0 * (h1 - h0) / (_R * t0)))
    return tuple(pressures)


_BASE_PRESSURES = _compute_base_pressures()


def geometric_to_geopotential(geometric_altitude: float) -> float:
    """Convert geometric altitude ``z`` (m) to geopotential altitude ``H = R_e·z/(R_e+z)``."""
    return _EARTH_RADIUS_ISA * geometric_altitude / (_EARTH_RADIUS_ISA + geometric_altitude)


class EarthISAModel(AtmosphericModel):
    """International Standard Atmosphere for Earth (0–86 km), seven layers.

    The gas constants are real Earth-air values; the temperature/pressure *profile* is now a
    full ISA implementation (no longer a seam).
    """

    SPECIFIC_GAS_CONSTANT: float = _R
    SPECIFIC_HEAT_RATIO: float = _GAMMA
    MAX_ALTITUDE: float = 86_000.0

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        """Return ISA conditions at ``altitude_msl`` (geopotential meters; see module note).

        Temperature: ``T = T_base + L·(H − H_base)`` within the layer containing ``H``.
        Pressure (barometric): non-isothermal layers use
        ``P = P_base·(T/T_base)^(−g₀/(L·R))``; isothermal layers use
        ``P = P_base·exp(−g₀·(H − H_base)/(R·T_base))``. Above 86 km the top-of-model values
        are held constant (the region is near-vacuum and outside ISA validity).
        """
        h = min(max(altitude_msl, 0.0), _TOP_ALTITUDE)

        index = len(_LAYERS) - 1
        for i in range(len(_LAYERS) - 1):
            if h < _LAYERS[i + 1][0]:
                index = i
                break

        h_base, t_base, lapse = _LAYERS[index]
        p_base = _BASE_PRESSURES[index]
        temperature = t_base + lapse * (h - h_base)
        if abs(lapse) > 1e-12:
            pressure = p_base * (temperature / t_base) ** (-_G0 / (lapse * _R))
        else:
            pressure = p_base * math.exp(-_G0 * (h - h_base) / (_R * t_base))

        return AtmosphericConditions(
            temperature=temperature,
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
            source="U.S. Standard Atmosphere, 1976 (NOAA-S/T 76-1562); ICAO ISA",
            notes=(
                "Seven-layer ISA, 0–86 km, in geopotential altitude. Internationally "
                "standardised model reconciled against decades of radiosonde/rocket/satellite "
                "measurements. Above 86 km the model is held constant (out of ISA validity)."
            ),
        )
