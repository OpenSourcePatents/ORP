<!--
ORP — Open Reentry Platform
Copyright (C) Charles W. Dowd Jr.
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Term-by-term verification of the ORP 3-DOF EOM against NASA CR-149170

**Date of verification:** 2026-06-10
**ORP code verified:** `orp/core/simulation/stepper.py`, `SimulationStepper.compute_derivatives`
(commit lineage: branch `eom-invariants`, from `skeleton` @ 6fb2211)
**Outcome: PASS** — every term of the implemented rotating-planet equations of motion matches
the source document under a documented, exact notation mapping. No discrepancies found.

## 1. Source document

| Field | Value |
|---|---|
| Accession | NASA NTRS **19760024112** (public use permitted) |
| Report | **NASA CR-149170** — *Final Technical Report, NASA Grant NSG 1056: "Preparation of Aeronautical Engineering Text Material on the Theory of Hypersonic Flight"* (the *Hypersonic Flight Mechanics* text) |
| Authors | Adolf Busemann, Nguyen X. Vinh, Robert D. Culp (University of Colorado, Boulder) |
| Period / date | June 1974 – September 1976 |
| Fetched from | `https://ntrs.nasa.gov/api/citations/19760024112/downloads/19760024112.pdf` (9,311,777 bytes, 440 PDF pages) |
| Material used | Chapter 2, *Equations for Flight Over a Spherical Planet*, printed pp. 2-1 … 2-13 (PDF pp. 37–49) |

Verification method: the chapter pages containing the equations were rendered to images at
200 dpi and the printed equations transcribed visually (the 1976 typescript's OCR text layer
is not reliable for mathematics). Each printed term was then matched against the
corresponding term in `compute_derivatives`.

## 2. Notation conventions of the source (printed p. 2-5, PDF p. 41)

* Longitude **θ**: "measured from the X-axis, in the equatorial plane, positively eastward".
* Latitude **φ**: "measured from the equatorial plane, along a meridian, and positively northward".
* Flight-path angle **γ**: "the angle between the local horizontal plane … and the velocity V̄ …
  positive when V̄ is above the horizontal plane".
* Heading **ψ**: "the angle between the local parallel of latitude and the projection of V̄ on
  the horizontal plane … measured positively in the right-handed direction about the x-axis"
  (x-axis along the position vector, i.e. local up). The document's heading is therefore
  measured **from East toward North**.
* Bank **σ**: the lift vector is "rotated out of this plane through an angle σ", where "this
  plane" is the vertical (r̄, V̄) plane (printed pp. 2-7/2-8); the positive sense follows from
  Eq. (2-31): positive σ drives dψ/dt > 0 (an East→North, i.e. leftward/counter-compass, turn).
* Velocity **V** is planet-relative; time derivatives are taken in planet-fixed axes
  (printed p. 2-5); the planet rotates at constant ω about the polar axis (printed p. 2-4).
* Gravity (Eq. 2-19): purely radial central force, `m·ḡ = −m·g·ī`.

### Mapping to ORP variables

ORP's heading ψ_ORP is a compass azimuth, **from North toward East** (`status.py`). The two
conventions are exact mirror parameterizations:

```
ψ_doc = π/2 − ψ_ORP   ⟺   sin ψ_doc = cos ψ_ORP ,  cos ψ_doc = sin ψ_ORP
dψ_ORP/dt = − dψ_doc/dt
```

Because the heading angle is mirrored, the steering (lift) term changes sign under the map;
ORP absorbs this in the bank-angle sign convention:

```
σ_ORP = − σ_doc
```

i.e. in ORP a positive bank produces dψ_ORP/dt > 0 (a North→East, rightward/compass-positive
turn), while in the document a positive bank produces dψ_doc/dt > 0 (an East→North turn).
Both describe identical physics — `cos σ` terms are unaffected (even), and `|L·sin σ|`
steering is identical with a mirrored positive direction. All other symbols (r, θ, φ, γ, V,
ω, m, D, L, g) map one-to-one. ORP integrates altitude h with r = R + h, so dr/dt = dh/dt.

For the entry (non-thrusting) case the document sets T = 0, **F_T = −D, F_N = L**
(printed p. 2-13, immediately above Eq. 2-34).

## 3. Term-by-term comparison

Source equations: kinematics **Eq. (2-28)** (printed p. 2-10, PDF p. 46); rotating-planet
force equations **Eq. (2-31)** (printed pp. 2-11/2-12, PDF pp. 47/48). ORP lines refer to
`compute_derivatives` in `orp/core/simulation/stepper.py`.

### Eq. (2-28a) — radial kinematics
| Printed term (doc) | Mapped to ORP variables | ORP implementation | Match |
|---|---|---|---|
| `dr/dt = V sin γ` | `dh/dt = V sin γ` | `d_altitude = velocity * sin_gamma` | ✓ |

### Eq. (2-28c) — latitude kinematics
| Printed term | Mapped | ORP | Match |
|---|---|---|---|
| `dφ/dt = V cos γ sin ψ_doc / r` | `V cos γ cos ψ_ORP / r` | `d_latitude = velocity * cos_gamma * cos_psi / radius` | ✓ |

### Eq. (2-28b) — longitude kinematics
| Printed term | Mapped | ORP | Match |
|---|---|---|---|
| `dθ/dt = V cos γ cos ψ_doc / (r cos φ)` | `V cos γ sin ψ_ORP / (r cos φ)` | `d_longitude = velocity * cos_gamma * sin_psi / (radius * cos_phi_safe)` | ✓ |

### Eq. (2-31a) — speed equation, with F_T = −D
| Printed term | Mapped | ORP | Match |
|---|---|---|---|
| `(1/m)·F_T` = `−D/m` | `−D/m` | `-drag / mass` | ✓ |
| `−g sin γ` | `−g sin γ` | `- gravity * sin_gamma` | ✓ |
| `+ω²r cos φ (sin γ cos φ − cos γ sin φ sin ψ_doc)` | `+ω²r cos φ (sin γ cos φ − cos γ sin φ cos ψ_ORP)` | `+ omega*omega*radius*cos_phi*(sin_gamma*cos_phi - cos_gamma*sin_phi*cos_psi)` | ✓ |
| *(no 2ωV term printed)* | *(none)* | *(none implemented)* | ✓ |

### Eq. (2-31b) — flight-path-angle equation (×1/V), with F_N = L
| Printed term | Mapped | ORP | Match |
|---|---|---|---|
| `(1/m)·F_N cos σ_doc` | `L cos σ_ORP / m` (cos is even) | `lift * cos_sigma / mass` | ✓ |
| `−g cos γ + (V²/r) cos γ` | same | `(velocity*velocity/radius - gravity) * cos_gamma` | ✓ |
| `+2ωV cos φ cos ψ_doc` | `+2ωV cos φ sin ψ_ORP` | `+ 2.0*omega*velocity*cos_phi*sin_psi` | ✓ |
| `+ω²r cos φ (cos γ cos φ + sin γ sin φ sin ψ_doc)` | `+ω²r cos φ (cos γ cos φ + sin γ sin φ cos ψ_ORP)` | `+ omega*omega*radius*cos_phi*(cos_gamma*cos_phi + sin_gamma*sin_phi*cos_psi)` | ✓ |

### Eq. (2-31c, continued) — heading equation (×1/V), with F_N = L, then negated by the map
Printed (p. 2-12 top): `V dψ/dt = (1/m)·F_N sin σ / cos γ − (V²/r) cos γ cos ψ tan φ + 2ωV(tan γ cos φ sin ψ − sin φ) − (ω²r/cos γ) sin φ cos φ cos ψ`

| Printed term | After `ψ_doc→ψ_ORP`, `dψ_ORP/dt = −dψ_doc/dt`, `σ_ORP = −σ_doc` | ORP | Match |
|---|---|---|---|
| `+(1/m)·F_N sin σ_doc / cos γ` | `+L sin σ_ORP/(m cos γ)` | `lift * sin_sigma / (mass * cos_gamma_safe)` | ✓ |
| `−(V²/r) cos γ cos ψ_doc tan φ` | `+(V²/r) cos γ sin ψ_ORP tan φ` | `+ velocity*velocity/radius * cos_gamma * sin_psi * sin_phi/cos_phi_safe` | ✓ |
| `+2ωV (tan γ cos φ sin ψ_doc − sin φ)` | `−2ωV (tan γ cos φ cos ψ_ORP − sin φ)` | `- 2.0*omega*velocity*(sin_gamma/cos_gamma_safe*cos_phi*cos_psi - sin_phi)` | ✓ |
| `−(ω²r/cos γ) sin φ cos φ cos ψ_doc` | `+(ω²r/cos γ) sin φ cos φ sin ψ_ORP` | `+ omega*omega*radius/cos_gamma_safe * sin_phi*cos_phi*sin_psi` | ✓ |

### Eq. (2-32) / (2-34) — the ω = 0 reduction and the entry equations
Printed p. 2-12 gives the ω = 0 set (2-32); printed p. 2-13 gives the non-thrusting entry
form (2-34): `dV/dt = −D/m − g sin γ`, `V dγ/dt = (L cos σ)/m − g cos γ + (V²/r) cos γ`,
`V dψ/dt = (L sin σ)/(m cos γ) − (V²/r) cos γ cos ψ tan φ`. ORP with ω = 0 reduces to
exactly this set under the same mapping — verified numerically term-for-term on a 240-state
grid by `TestOmegaZeroReduction` in `orp/tests/test_eom_invariants.py`.

## 4. The Coriolis statement (printed p. 2-12, PDF p. 48)

The document states, verbatim: *"the term 2ω V , called the Coriolis acceleration, has an
important effect in a high-speed, long-range flight. For an accurate analysis, especially in
the problem of computing the trajectory of a ballistic missile, the term should be
retained."* Consistent with Coriolis acceleration being perpendicular to the
planet-relative velocity (it does no work), the printed Eq. (2-31a) speed equation contains
**no** 2ωV term — the 2ωV terms appear only in the dγ/dt and dψ/dt equations. ORP matches:
`TestNoCoriolisInSpeedEquation` in `orp/tests/test_eom_invariants.py` pins this structurally.

## 5. Deviations / generalizations (flagged, none affecting the match)

1. **Gravity magnitude.** The document's gravity is a central, radial g (Eq. 2-19; spherical
   planet). ORP inserts the magnitude returned by the injected `GravityModel` into the same
   `−g sin γ` / `−g cos γ` slots. For Mars (central GM/r²) this is identical to the source.
   For Earth, the Somigliana latitude-dependent magnitude is a refinement of the *value* of
   g; the *direction* is still treated as radial, so the deflection-of-the-vertical
   (ellipsoidal normal vs. radial) component is neglected. The EOM form is unchanged.
2. **Heading/bank conventions.** Mirror mapping documented in §2; exact, not approximate.
3. **State variable.** ORP integrates altitude h instead of radius r (dr/dt = dh/dt, R constant).
4. **Thrust.** ORP implements the non-thrusting entry case (T = 0, F_T = −D, F_N = L) — the
   document's own specialization on p. 2-13.

## 6. Consequences applied to ORP provenance

1. A new validation level **`VERIFIED_SOURCE`** is added to `ValidationLevel`, ranked between
   `ASSERTED` and `VERIFIED_CFD`: *implementation verified against its defining source
   document* — stronger than citing a source, weaker than independent reproduction against
   CFD or flight data.
2. The EOM (`SimulationStepper.provenance`) is tagged `VERIFIED_SOURCE` citing this document
   and folded into every simulation's weakest-link provenance by the engine.
3. The Earth ISA and Mars atmosphere models are retagged from `VERIFIED_FLIGHT` to
   `VERIFIED_SOURCE`: ORP's spot-check tests verify the *implementation* against the models'
   defining documents (U.S. Standard Atmosphere 1976 tables; the lander-anchored 636 Pa /
   210 K datum), not against flight telemetry. The underlying standards are themselves
   measurement-reconciled, but ORP has not independently reconciled its implementation
   against flight data, so claiming `VERIFIED_FLIGHT` overstated ORP's own validation.
4. The Mars surface anchor's source datasets are added to `mars.py`'s citation: the Viking
   lander measurements behind the canonical 636 Pa / 210 K pair — Hess, S. L., Henry, R. M.,
   Leovy, C. B., Ryan, J. A., and Tillman, J. E., "Meteorological results from the surface of
   Mars: Viking 1 and 2," *J. Geophys. Res.* **82**(28), 4559–4574 (1977), DOI
   10.1029/JS082i028p04559; and Seiff, A., and Kirk, D. B., "Structure of the atmosphere of
   Mars in summer at mid-latitudes," *J. Geophys. Res.* **82**(28), 4364–4378 (1977), DOI
   10.1029/JS082i028p04364. (Both citations verified against the publisher's records
   2026-06-10; the NASA Mars Fact Sheet page that distills them was offline for maintenance
   on the verification date.)
5. The vehicle YAMLs (`apollo.yaml`, `msl.yaml`) are **not** retagged: their
   `VERIFIED_FLIGHT` properties (entry mass, trimmed L/D) are flight-reconstructed
   *quantities* taken from flight-reconstruction documents — the provenance describes the
   origin of the value, which genuinely is flight data. No citation strings were affected by
   the atmosphere retag.

## Transcription status (2026-06-10)
DUAL-CHANNEL VERIFIED - a second, independent blind pixel-channel transcription of printed pages 2-5..2-13 (600-DPI half-page renders plus up-to-1400-DPI crops) reproduced verbatim every equation and convention sentence this document relies on: the theta/phi/gamma/psi/sigma definitions (p. 2-5, 2-7/2-8), Eq. (2-28) kinematics, Eq. (2-31) force equations including the absence of a 2*omega*V term in dV/dt, the Coriolis passage (p. 2-12, word-for-word), F_T = -D / F_N = L, and Eq. (2-34). The 1976 typescript has no reliable text layer for mathematics, so the two independent pixel readings (this session's and the original verification's) are the two channels. Two source typesetting defects found in equations ORP does not rely on: Eq. (2-30) middle equation runs off the right margin (closing 'phi)' missing), and Eq. (2-32) third equation's leading 'V' is printed with a descender resembling lowercase 'y'.
