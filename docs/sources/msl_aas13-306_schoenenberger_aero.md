<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Source inventory — MSL flight aerodynamics (AAS 13-306)

**Citation.** Schoenenberger, M., et al., "Assessment of the Reconstructed
Aerodynamics of the Mars Science Laboratory Entry Vehicle," AAS 13-306, 23rd
AAS/AIAA Space-Flight Mechanics Meeting, Feb. 2013.
**NTRS accession:** `20130010088` (confirmed 2026-06-10).

**Role in ORP.** Primary source for MSL *reconstructed flight aerodynamics*
(axial/normal/pitching-moment coefficients vs Mach), to validate or replace the
ASSERTED aero in `msl.yaml`.

## FROM THE TEXT (directly sourceable)
- Aerodynamics extracted from onboard flight data: IMU accelerometer + rate gyro and
  **heatshield surface pressures** (MEADS), the most complete Mars-entry aero data set
  to date. *(text)*
- Reconstructed aero resolved to better accuracy than the preflight database
  uncertainties. *(text)*

## IN FIGURES / TABLES (needs digitization before use)
- **C_A, C_N, C_m vs Mach** reconstructed curves: figure/table. `fig`
- Trim angle of attack vs Mach: figure. `fig`
- Reconstructed L/D vs Mach: figure. `fig`

## Status
Citation + accession pinned. The `msl.yaml` aero (CD 1.68, L/D, trim α) stays ASSERTED
until these reconstructed curves are digitized; this inventory records where the
upgrade data lives. Companion: hypersonic/supersonic static aero NTRS `20120011936`.
