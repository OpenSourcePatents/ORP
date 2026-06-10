<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Source inventory — Stardust SRC aerodynamics (AIAA 97-2304)

**Citation.** Mitcheltree, R. A., Wilmoth, R. G., Cheatwood, F. M., Brauckmann,
G. J., and Greene, F. A., "Aerodynamics of Stardust Sample Return Capsule,"
AIAA 97-2304, 32nd AIAA Thermophysics Conference, June 1997.
**NTRS accession:** `20040105538` (PDF available; confirmed 2026-06-10).

**Role in ORP.** Primary source for the Stardust **outer mold line** and
**CD-vs-Mach** feeding `stardust.yaml`. Text was extracted via pymupdf (the NTRS scan
is image-wrapped; WebFetch could not read it directly).

## FROM THE TEXT (directly sourceable — used in stardust.yaml)
- Forebody: **60-degree half-angle sphere-cone**. `text`
- Nose radius **0.2286 m**; shoulder radius **0.01905 m**. `text`
- Overall (base) diameter **0.8128 m**. `text`
- Reference area = frontal area **0.51887 m²**; reference length = diameter
  0.8128 m; moments taken about the nose unless noted. `text`
- Afterbody: 30-degree cone with a flat stern. `text`
- As-flown **c.g. at 0.35D** back from the nose (statically unstable about the c.p.;
  paper recommends moving forward toward ~0.26D). `text`
- Zero-AoA hypersonic continuum **axial coefficient ≈ 1.61** (continuum valid above
  Mach 12; transitional above ~Mach 38). `text/table`

## IN FIGURES / TABLES (needs digitization for a full curve)
- **Full CD-vs-Mach** (and C_N, C_m vs Mach, α = 0/5/10°): CFD (LAURA/DSMC) + JPL
  wind-tunnel, Mach 35→0.6. CD **decreases below ~Mach 12** as the sonic line shifts
  from the nose to the shoulder. `fig`
- Subsonic **dynamic instability** (drogue required): figure/discussion. `fig`
- Ablated-shape aerodynamics (nose radius grows to 0.2405 m): figure. `fig`

## Status
OML + hypersonic CD are `text`-sourced and used in `stardust.yaml` (ASSERTED). The full
CD-vs-Mach curve is `fig` — `stardust.yaml` carries a single hypersonic CD and the
forward sim runs at that constant CD; the Mach-varying curve is flagged future work.
