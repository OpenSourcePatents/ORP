# ORP — Open Reentry Platform

ORP is a Python **atmospheric reentry simulator** for the descent phase of flight.
It integrates a vehicle's equations of motion **forward in time** from a set of entry
conditions and a *replayed* bank-angle schedule, across multiple planetary
environments (Earth and Mars from day one).

## Three non-negotiable principles

1. **Forward simulation only.**
   The simulator takes entry conditions plus a pre-recorded bank-angle schedule and
   integrates forward. **No function in this codebase accepts a desired landing point
   and returns a bank schedule.** ORP models what *did* / *would* happen given a control
   history; it never solves the inverse guidance/targeting problem. This is a hard,
   permanent architectural wall — see `orp/core/bank_schedule/schedule.py` and
   `orp/core/simulation/engine.py`. If a proposed feature is unsure whether it crosses
   this line, it does: raise, don't compute.

2. **Provenance on everything.**
   Every vehicle property and every simulation output carries a validation tag —
   `VERIFIED_FLIGHT`, `VERIFIED_CFD`, `ASSERTED`, or `NOT_VALIDATED` — and every vehicle
   property carries a source citation string. Provenance propagates: a trajectory is only
   as trustworthy as the weakest input that produced it. This is the product's core
   differentiator, not an afterthought. See `orp/core/provenance/`.

3. **Multi-planet.**
   The `Vehicle` + `Planet` abstraction is present from the start. A `Planet` bundles an
   atmosphere model, a gravity model, a mean radius, and a rotation rate. Earth and Mars
   ship in `orp/core/planet/registry.py`.

## Status

This is an **architectural skeleton**. The contracts (base classes, method signatures,
type hints, docstrings, the provenance system, the planet/vehicle/model wiring) are
complete. The *flight physics* — aerodynamic forces, equation-of-motion derivatives,
altitude-dependent atmosphere and gravity variation — are placeholders that return
zeros or planet reference constants, clearly marked with `# --- PHYSICS SEAM ---`, so
real implementations drop into named seams without reshaping the architecture. See
[`docs` in code]; the convention is documented in
`orp/core/__init__.py`.

## Architecture & credit

ORP's architecture deliberately mirrors **[OpenRocket](https://openrocket.info/)**, the
open-source model-rocketry simulator, adapted from ascent to the descent/reentry regime:

- an **Engine / Stepper** split (orchestrator vs. pluggable physics integrator — Strategy
  pattern),
- a mutable per-instant `SimulationStatus` vs. an immutable `SimulationConditions`
  dependency-injection container,
- a `FlightData` / `FlightDataBranch` column-store for trajectory output,
- pluggable `AtmosphericModel` / `GravityModel` / `AerodynamicCalculator` strategies, and
- a momentary `FlightConditions` input object feeding the aerodynamics.

ORP reuses these **design patterns only**. No OpenRocket source code is copied. OpenRocket
is gratefully acknowledged as architectural inspiration.

## License

ORP is licensed under the **GNU General Public License, version 3 or later
(GPL-3.0-or-later)**. OpenRocket is also GPL-licensed; mirroring its design patterns in a
GPL project is consistent with that license. See the license headers in source files.

Copyright © Charles W. Dowd Jr.

## Layout

```
orp/
  core/
    simulation/    engine, stepper (RK4), status, conditions, flight_data
    vehicles/      EntryVehicle base + YAML library loader
    aerodynamics/  AerodynamicCalculator interface, Modified Newtonian, FlightConditions
    atmosphere/    AtmosphericModel interface, Earth ISA, Mars
    gravity/       GravityModel interface, Earth WGS84, Mars
    bank_schedule/ forward-only bank-angle replay
    provenance/    ValidationLevel, ProvenanceTag, TaggedValue
    planet/        Planet bundle + EARTH/MARS registry
  data/vehicles/   apollo.yaml, msl.yaml
  gui/             (placeholder)
  tests/           smoke test over the import graph
```
