# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""U.S. Standard Atmosphere 1976 high-altitude extension (86–250 km, held above).

Removes the >86 km clamp limitation of :class:`~orp.core.atmosphere.earth.EarthISAModel`
for high-altitude entry interfaces (Artemis EI 121.92 km, Stardust EI ~132 km, skip arcs).
Below 86 km it delegates to the wrapped base model unchanged.

SOURCE. "U.S. Standard Atmosphere, 1976" (NOAA / NASA / USAF), NTRS 19770009539,
Table I (Geometric Altitude, Metric Units), printed pages 68–73 (PDF pages 83–88).
The node values below were transcribed from page pixels on 2026-06-10 (the NTRS scan has
no usable text layer; 400-DPI column crops). Where the rho column was clipped in the
crop, rho was recovered as (rho/rho_0) x 1.2250 kg/m^3 — the rho/rho_0 column of the same
table and the document's own sea-level density. Spot checks against independently known
US76 values agree exactly at 86, 90, 100, 110, 120, 130, 140, 150, 200, and 250 km.

MODELING NOTES (documented approximations, not seams):
- Between nodes: temperature linear in Z, density LOG-linear in Z. The log-linear choice
  reproduces the document's own intermediate rows (e.g. the printed 95-km density
  1.393e-6 equals the 94/96-km log-midpoint to 4 digits).
- Pressure is returned as rho*R_air*T so that the DENSITY (the dynamically relevant
  quantity) is exact-as-tabulated under ORP's fixed air gas constant. Above ~100 km the
  real mean molecular weight drops, so the true static pressure deviates from this
  value; Mach/viscosity diagnostics up there are indicative only.
- Above 250 km the 250-km values are held constant. Density there is < 6.1e-11 kg/m^3
  (drag acceleration ~1e-5 m/s^2 at 8 km/s for capsule-class ballistic coefficients) —
  a deliberate, documented cut-off, far below trajectory-relevant levels, in place of
  the document's exospheric rows.
"""

from __future__ import annotations

import math
from bisect import bisect_right

from orp.core.atmosphere.earth import EarthISAModel
from orp.core.atmosphere.model import AtmosphericConditions, AtmosphericModel
from orp.core.provenance.tags import ProvenanceTag, ValidationLevel

__all__ = ["US76HighAltitudeExtension"]

_R = EarthISAModel.SPECIFIC_GAS_CONSTANT
_GAMMA = EarthISAModel.SPECIFIC_HEAT_RATIO

# (geometric altitude Z m, kinetic temperature K, density kg/m^3)
# NTRS 19770009539 Table I, printed pp. 68-70. 'direct' = rho column read directly;
# 'via ratio' = (rho/rho_0) x 1.2250 (rho column clipped in the 400-DPI crop).
_NODES: tuple[tuple[float, float, float], ...] = (
    (86_000.0, 186.87, 6.958e-6),   # direct (also the prior model's clamp value)
    (88_000.0, 186.87, 4.875e-6),   # via ratio 3.980e-6
    (90_000.0, 186.87, 3.416e-6),   # via ratio 2.789e-6; matches known US76 value
    (92_000.0, 186.96, 2.393e-6),   # via ratio 1.953e-6
    (94_000.0, 187.74, 1.670e-6),   # via ratio 1.363e-6
    (96_000.0, 189.31, 1.162e-6),   # via ratio 9.486e-7
    (98_000.0, 191.72, 8.070e-7),   # via ratio 6.588e-7
    (100_000.0, 195.08, 5.604e-7),  # via ratio 4.575e-7; matches known US76 value
    (102_000.0, 199.53, 3.935e-7),  # via ratio 3.212e-7
    (104_000.0, 205.31, 2.769e-7),  # via ratio 2.260e-7
    (106_000.0, 212.89, 1.954e-7),  # via ratio 1.595e-7
    (108_000.0, 223.29, 1.382e-7),  # via ratio 1.128e-7
    (110_000.0, 240.00, 9.708e-8),  # via ratio 7.925e-8; matches known US76 value
    (112_000.0, 264.00, 6.838e-8),  # via ratio 5.582e-8
    (114_000.0, 288.00, 4.975e-8),  # via ratio 4.061e-8
    (116_000.0, 312.00, 3.720e-8),  # via ratio 3.037e-8
    (118_000.0, 336.00, 2.847e-8),  # via ratio 2.324e-8
    (120_000.0, 360.00, 2.222e-8),  # via ratio 1.814e-8; matches known US76 value
    (122_000.0, 383.55, 1.766e-8),  # via ratio 1.442e-8
    (124_000.0, 406.22, 1.428e-8),  # via ratio 1.166e-8
    (126_000.0, 428.04, 1.171e-8),  # via ratio 9.557e-9
    (130_000.0, 469.27, 8.152e-9),  # via ratio 6.655e-9; matches known US76 value
    (140_000.0, 559.63, 3.832e-9),  # via ratio 3.128e-9
    (150_000.0, 634.39, 2.076e-9),  # direct
    (160_000.0, 696.29, 1.233e-9),  # direct
    (170_000.0, 747.57, 7.815e-10), # direct
    (180_000.0, 790.07, 5.194e-10), # direct
    (190_000.0, 825.31, 3.581e-10), # direct
    (200_000.0, 854.56, 2.541e-10), # direct
    (210_000.0, 878.84, 1.846e-10), # direct
    (220_000.0, 899.01, 1.367e-10), # direct
    (230_000.0, 915.78, 1.029e-10), # direct
    (240_000.0, 929.73, 7.858e-11), # direct
    (250_000.0, 941.33, 6.073e-11), # direct
)
_Z = [n[0] for n in _NODES]


class US76HighAltitudeExtension(AtmosphericModel):
    """US76 86–250 km extension over a base (<86 km) Earth atmosphere model."""

    MAX_ALTITUDE: float = 1_000_000.0  # accepts queries up to 1000 km (held >250 km)

    def __init__(self, base: AtmosphericModel | None = None) -> None:
        self._base = base if base is not None else EarthISAModel()
        self._provenance = ProvenanceTag(
            ValidationLevel.VERIFIED_SOURCE,
            source=("U.S. Standard Atmosphere, 1976 (NOAA/NASA/USAF), NTRS 19770009539, "
                    "Table I (geometric altitude, metric), printed pp. 68-73"),
            notes=("86-250 km T/rho nodes pixel-transcribed 2026-06-10; log-linear rho / "
                   "linear T between nodes; pressure returned as rho*R_air*T (density "
                   "exact, pressure nominal above ~100 km); values held above 250 km. "
                   f"Below 86 km delegates to {type(self._base).__name__}."),
        )

    def get_conditions(self, altitude_msl: float) -> AtmosphericConditions:
        if altitude_msl <= _Z[0]:
            return self._base.get_conditions(altitude_msl)
        if altitude_msl >= _Z[-1]:
            _, t, rho = _NODES[-1]
            return AtmosphericConditions(
                temperature=t, pressure=rho * _R * t,
                specific_gas_constant=_R, specific_heat_ratio=_GAMMA)
        i = bisect_right(_Z, altitude_msl)
        z0, t0, r0 = _NODES[i - 1]
        z1, t1, r1 = _NODES[i]
        f = (altitude_msl - z0) / (z1 - z0)
        t = t0 + (t1 - t0) * f
        rho = math.exp(math.log(r0) + (math.log(r1) - math.log(r0)) * f)
        return AtmosphericConditions(
            temperature=t, pressure=rho * _R * t,
            specific_gas_constant=_R, specific_heat_ratio=_GAMMA)

    def get_max_altitude(self) -> float:
        return self.MAX_ALTITUDE

    @property
    def provenance(self) -> ProvenanceTag:
        return self._provenance
