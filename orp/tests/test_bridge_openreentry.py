# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge gate: ORP vs. the pinned `openreentry` reference implementation (`ref_core/`).

The reference is an independent planar 3-DOF entry integrator (state [r, V, γ, s],
scipy RK45 adaptive). ORP run at the equator heading due east with ω = 0 embeds that
planar problem exactly: latitude and heading stay constant and downrange equals
R·longitude. Both gates_01.py reference cases are mirrored with **matched** inputs —
the same constant coefficients (:class:`ConstantCoefficientCalculator`), the same
exponential atmosphere (:class:`ExponentialAtmosphere`), the same gravity (central μ/r²),
and a matched step (ORP's fixed RK4 dt = the reference's max_step cap).

The remaining difference is the integrator pair itself (fixed-step RK4 vs. adaptive RK45
at rtol=atol=1e-9, dense-output sampled at ORP's time grid). That difference was
characterized on 2026-06-10 (see ``docs/verification/bridge_openreentry_gate.md``) and the
gates below are set at the characterized level with ~2 orders of magnitude of margin for
platform/scipy-version variation. **Policy: these tolerances are never to be loosened to
make a failure pass.** A failure beyond them indicates a real divergence and must be
investigated and recorded in the verification document.

Known structural differences (documented, excluded from the comparison):
- Termination: the reference root-finds the h_stop crossing; ORP's engine stops on the
  first recorded point at/below it (no event interpolation), so end times differ by up to
  one dt. Channels are compared over the common time range only.
- The reference clamps density below its datum (ρ(h<0) = ρ₀); ORP's exponential does not.
  Both cases here terminate at or above the datum, so the clamp is never exercised.

Skipped (not failed) when the pinned clone or scipy is unavailable.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

_REF_CORE = Path(__file__).resolve().parents[2] / "ref_core"
if not _REF_CORE.is_dir():
    pytest.skip(
        "ref_core/ reference clone not present (git clone "
        "<path-to-local-openreentry-clone> ref_core --branch master)",
        allow_module_level=True,
    )
pytest.importorskip("scipy", reason="the openreentry reference requires scipy")

if str(_REF_CORE) not in sys.path:
    sys.path.insert(0, str(_REF_CORE))

from openreentry import EARTH as REF_EARTH  # noqa: E402  (reference, path-injected above)
from openreentry import ExponentialAtmosphere as RefExponentialAtmosphere  # noqa: E402
from openreentry import Vehicle as RefVehicle  # noqa: E402
from openreentry import integrate_entry  # noqa: E402

from orp.core.aerodynamics.constant import ConstantCoefficientCalculator  # noqa: E402
from orp.core.atmosphere.exponential import ExponentialAtmosphere  # noqa: E402
from orp.core.bank_schedule import BankSchedule  # noqa: E402
from orp.core.gravity.model import GravityModel  # noqa: E402
from orp.core.planet.planet import Planet, WorldCoordinate  # noqa: E402
from orp.core.provenance.tags import ProvenanceTag, TaggedValue, ValidationLevel  # noqa: E402
from orp.core.simulation import SimulationConditions, SimulationEngine  # noqa: E402
from orp.core.simulation import flight_data as fd  # noqa: E402
from orp.core.vehicles.base import EntryVehicle  # noqa: E402

# Matched constants: the reference's EARTH (mu, R) — identical to ORP's Earth values.
_MU = REF_EARTH.mu  # 3.986004418e14
_RADIUS = REF_EARTH.R  # 6.371e6


class _CentralGravity(GravityModel):
    """g = μ/(R+h)², the reference's exact gravity model."""

    def get_gravity(self, position: WorldCoordinate) -> float:
        r = _RADIUS + position.altitude
        return _MU / (r * r)

    @property
    def provenance(self) -> ProvenanceTag:
        return ProvenanceTag(ValidationLevel.VERIFIED_FLIGHT, "central μ/r² (bridge fixture)")


def _orp_planar_run(
    *,
    rho0: float,
    scale_height: float,
    mass: float,
    area: float,
    cd: float,
    entry_velocity: float,
    entry_gamma_deg: float,
    entry_altitude: float,
    time_step: float,
    max_time: float,
    ground_altitude: float,
) -> dict[str, np.ndarray]:
    """Run ORP with matched inputs, equatorial eastward, ω = 0 (planar embedding)."""

    def tv(value: float, unit: str = "") -> TaggedValue[float]:
        return TaggedValue.asserted(value, "bridge case (matched to openreentry)", unit=unit)

    planet = Planet(
        name="BridgeEarth",
        atmosphere=ExponentialAtmosphere(
            rho0,
            scale_height,
            provenance=ProvenanceTag(ValidationLevel.ASSERTED, "matched to reference case"),
        ),
        gravity=_CentralGravity(),
        mean_radius=_RADIUS,
        rotation_rate=0.0,
        gravitational_parameter=_MU,
    )
    vehicle = EntryVehicle(
        name="bridge body",
        mass=tv(mass, "kg"),
        reference_area=tv(area, "m^2"),
        nose_radius=tv(1.0, "m"),
        drag_coefficient=tv(cd),
        lift_to_drag=tv(0.0),
        trim_angle_of_attack=tv(0.0, "rad"),
        half_cone_angle=tv(1.0, "rad"),
    )
    conditions = SimulationConditions(
        vehicle=vehicle,
        planet=planet,
        bank_schedule=BankSchedule.constant(0.0),
        aerodynamic_calculator=ConstantCoefficientCalculator(
            cd, 0.0, provenance=ProvenanceTag(ValidationLevel.ASSERTED, "matched to reference case")
        ),
        entry_velocity=entry_velocity,
        entry_flight_path_angle=math.radians(entry_gamma_deg),
        entry_altitude=entry_altitude,
        entry_heading=math.radians(90.0),  # due east at the equator: planar embedding
        entry_latitude=0.0,
        entry_longitude=0.0,
        time_step=time_step,
        max_simulation_time=max_time,
        ground_altitude=ground_altitude,
    )
    branch = SimulationEngine().simulate(conditions).get_branch(0)
    return {
        "t": np.array(branch.get(fd.TYPE_TIME)),
        "h": np.array(branch.get(fd.TYPE_ALTITUDE)),
        "V": np.array(branch.get(fd.TYPE_VELOCITY)),
        "gamma": np.radians(np.array(branch.get(fd.TYPE_FLIGHT_PATH_ANGLE))),
        # Downrange: equatorial eastward ⇒ s = R·θ, identical to the reference's
        # ds/dt = (R/r)·V·cosγ (ORP: dθ/dt = V·cosγ/(r·cosφ) with φ ≡ 0).
        "s": _RADIUS * np.radians(np.array(branch.get(fd.TYPE_LONGITUDE))),
        "g_load": np.array(branch.get(fd.TYPE_DECELERATION)),
        "lat_deg": np.array(branch.get(fd.TYPE_LATITUDE)),
    }


def _channel_diffs(orp: dict[str, np.ndarray], ref: dict, t_end: float) -> dict[str, float]:
    """Max abs differences over the common time range, sampling the reference densely."""
    mask = orp["t"] <= t_end
    t = orp["t"][mask]
    y = ref["sol"].sol(t)  # rows: r, V, gamma, s
    return {
        "h": float(np.max(np.abs(orp["h"][mask] - (y[0] - REF_EARTH.R)))),
        "V": float(np.max(np.abs(orp["V"][mask] - y[1]))),
        "gamma": float(np.max(np.abs(orp["gamma"][mask] - y[2]))),
        "s": float(np.max(np.abs(orp["s"][mask] - y[3]))),
    }


class TestGate0VacuumArc:
    """gates_01 Gate 0 mirror: Keplerian arc in vacuum, energy conserved, channels match.

    Characterized 2026-06-10: max|Δh| 3.8e-8 m, max|ΔV| 6.7e-11 m/s, max|Δγ| 3.2e-15 rad,
    max|Δs| 3.0e-8 m, ORP energy drift 5.9e-15. Gates set ~2 orders above (see module
    docstring for the never-loosen policy).
    """

    def test_vacuum_arc_matches_reference(self) -> None:
        ref = integrate_entry(
            REF_EARTH,
            RefExponentialAtmosphere(rho0=0.0, H=7200.0),
            RefVehicle(mass=1000.0, area=1.0, CD=1.0, CL=0.0),
            7000.0,
            -2.0,
            400e3,
            t_max=1500.0,
            h_stop=-1e9,
            max_step=0.5,
        )
        orp = _orp_planar_run(
            rho0=0.0, scale_height=7200.0, mass=1000.0, area=1.0, cd=1.0,
            entry_velocity=7000.0, entry_gamma_deg=-2.0, entry_altitude=400e3,
            time_step=0.5, max_time=1500.0, ground_altitude=-1e9,
        )

        # The planar embedding must be exact: latitude never leaves the equator.
        assert np.max(np.abs(orp["lat_deg"])) < 1e-12

        # ORP energy conservation on the arc (the reference gate's own criterion is 1e-7).
        energy = 0.5 * orp["V"] ** 2 - _MU / (_RADIUS + orp["h"])
        drift = np.max(np.abs((energy - energy[0]) / energy[0]))
        assert drift < 1e-12  # characterized 5.9e-15

        diffs = _channel_diffs(orp, ref, min(ref["t"][-1], orp["t"][-1]))
        assert diffs["h"] < 1e-5  # m       (characterized 3.8e-8)
        assert diffs["V"] < 1e-8  # m/s     (characterized 6.7e-11)
        assert diffs["gamma"] < 1e-12  # rad (characterized 3.2e-15)
        assert diffs["s"] < 1e-5  # m       (characterized 3.0e-8)


class TestGate1SteepBallisticEntry:
    """gates_01 Gate 1 mirror: steep ballistic entry through the deceleration pulse.

    Matched step dt = max_step = 0.05 s, terminated at h = 5 km (covers the full pulse;
    avoids the slow terminal fall). Characterized 2026-06-10: max|Δh| 7.0e-6 m,
    max|ΔV| 4.2e-6 m/s, max|Δγ| 1.5e-13 rad, max|Δs| 1.2e-8 m; peak g 133.2926 (ref) vs
    133.2931 (ORP), relative 4e-6. Allen-Eggers closed form for this case: 127.65 g —
    both full-physics results sit ~4.4% above it (gravity-along-track, which AE neglects),
    matching the reference gate's own documentation of that effect.
    """

    def test_steep_entry_matches_reference(self) -> None:
        ref = integrate_entry(
            REF_EARTH,
            RefExponentialAtmosphere(rho0=1.225, H=7200.0),
            RefVehicle(mass=2000.0, area=2.0, CD=1.2, CL=0.0),
            7000.0,
            -89.9,
            120e3,
            t_max=400.0,
            h_stop=5e3,
            max_step=0.05,
        )
        orp = _orp_planar_run(
            rho0=1.225, scale_height=7200.0, mass=2000.0, area=2.0, cd=1.2,
            entry_velocity=7000.0, entry_gamma_deg=-89.9, entry_altitude=120e3,
            time_step=0.05, max_time=400.0, ground_altitude=5e3,
        )

        diffs = _channel_diffs(orp, ref, min(ref["t"][-1], orp["t"][-1]))
        assert diffs["h"] < 1e-3  # m       (characterized 7.0e-6)
        assert diffs["V"] < 1e-3  # m/s     (characterized 4.2e-6)
        assert diffs["gamma"] < 1e-10  # rad (characterized 1.5e-13)
        assert diffs["s"] < 1e-5  # m       (characterized 1.2e-8)

        # Peak sensed load: same definition both sides (aero force / m / g0).
        g_ref = float(np.max(ref["g_load"]))
        g_orp = float(np.max(orp["g_load"]))
        assert g_orp == pytest.approx(g_ref, rel=1e-4)  # characterized 4e-6

        # Sanity anchor: Allen-Eggers analytic peak for these parameters, ~4.4% below
        # full physics (AE neglects gravity-along-track). Loose band on purpose: this
        # pins the *scale*, not the integrator difference.
        allen_eggers_g = (
            7000.0**2 * abs(math.sin(math.radians(-89.9))) / (2.0 * math.e * 7200.0)
        ) / 9.80665
        assert g_orp == pytest.approx(allen_eggers_g, rel=0.06)
        assert g_orp > allen_eggers_g  # full physics adds gravity-along-track
