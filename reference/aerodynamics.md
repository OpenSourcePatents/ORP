# OpenRocket Aerodynamics Engine — Reimplementation Reference

This document maps the aerodynamics engine of OpenRocket (`info.openrocket.core.aerodynamics`)
so a Python port can reproduce its behaviour. It covers the public calculator contract, the
extended-Barrowman CP/CD computation, the per-component calculator pattern, the input
(`FlightConditions`) and output (`AerodynamicForces`) structures, and the CSV Mach/AoA lookup
table system.

Source packages (read-only reference):

- `core/src/main/java/info/openrocket/core/aerodynamics/`
- `core/src/main/java/info/openrocket/core/aerodynamics/barrowman/`
- `core/src/main/java/info/openrocket/core/aerodynamics/lookup/`

> Convention notes used throughout the codebase:
> - **CN** = normal force coefficient, **CNa** = its derivative w.r.t. AoA (`d CN / d alpha`).
> - **CP** carried as a `CoordinateIF` where the **weight** field holds CNa and X holds the axial CP position.
> - **CD** = total drag coefficient parallel to airflow; **CDaxial** (= CA) = axial drag coefficient.
> - All angles are in radians unless a name ends in `Degrees`.

---

## 1. The `AerodynamicCalculator` interface

File: `AerodynamicCalculator.java`. Extends `Monitorable` (exposes `ModID getModID()`).
This is the top-level contract the rest of the simulator calls.

```java
public interface AerodynamicCalculator extends Monitorable {

    double getStallAngle();                       // max stall angle, radians

    CoordinateIF getCP(FlightConfiguration configuration,
                       FlightConditions conditions,
                       WarningSet warnings);       // CP position in absolute coords (weight = CNa)

    AerodynamicForces getAerodynamicForces(FlightConfiguration configuration,
                                           FlightConditions conditions,
                                           WarningSet warnings);  // total forces on rocket

    Map<RocketComponent, AerodynamicForces> getForceAnalysis(FlightConfiguration configuration,
                                                             FlightConditions conditions,
                                                             WarningSet warnings); // per-component breakdown

    CoordinateIF getWorstCP(FlightConfiguration configuration,
                            FlightConditions conditions,
                            WarningSet warnings);   // foremost CP over all wind angles theta

    AerodynamicCalculator newInstance();           // independent copy (for parallel sims)

    void checkGeometry(FlightConfiguration configuration,
                       RocketComponent component,
                       WarningSet warnings);        // geometry sanity checks -> warnings
}
```

Return-value semantics:

- `getCP` → `CoordinateIF` (an immutable coordinate). `.getX()` = axial CP; `.getWeight()` = CNa.
  A weight near zero means CP is undefined (no normal-force gradient).
- `getAerodynamicForces` → a single `AerodynamicForces` for the whole rocket (CN, Cm, Cside, Cyaw,
  Croll, CD, CDaxial, damping moments already subtracted).
- `getForceAnalysis` → a `Map` keyed by `RocketComponent`. Contains an entry for every aerodynamic
  component **and** every `ComponentAssembly`; the entry for the root `Rocket` is the grand total.
  Order is preserved (`LinkedHashMap`).
- `getWorstCP` → see §2; mutates `conditions.theta` to the worst-case lateral wind angle.

### `AbstractAerodynamicCalculator` (base implementation)

File: `AbstractAerodynamicCalculator.java`. `implements AerodynamicCalculator`.

- `public static final int DIVISIONS = 360;` — angular resolution for worst-CP sweep.
- Provides a concrete `getWorstCP(...)`: clones conditions, sweeps `theta` over `2*pi*i/DIVISIONS`
  for `i in 0..360`, calls `getCP` each time, keeps the CP with the smallest (foremost) X among
  those with `weight > EPSILON`, and writes the winning theta back into the caller's `conditions`.
- `protected ignoreWarningSet` — used when the caller passes `warnings == null`.
- **Cache validity** via rocket modification IDs:
  ```java
  protected final void checkCache(FlightConfiguration configuration);  // voids cache if modIDs changed
  protected void voidAerodynamicCache();                               // override to clear caches
  ```
  `checkCache` compares the rocket's `getAerodynamicModID()` and `getTreeModID()` against stored
  IDs; on mismatch it calls `voidAerodynamicCache()`. Every public entry point calls `checkCache`
  first. **A Python port must replicate this invalidate-on-change pattern** (e.g. version counters).
- `getStallAngle`, `getCP`, `getAerodynamicForces`, `getForceAnalysis` remain abstract.

---

## 2. `BarrowmanCalculator` — CP and CD orchestration

File: `BarrowmanCalculator.java`. `extends AbstractAerodynamicCalculator`.

Key design point: **`BarrowmanCalculator` is a thin façade that delegates** to two collaborators,
injected via the constructor (strategy pattern):

```java
private final StabilityCalculator stabilityCalculator;  // non-axial: CP, CN, Cm, Cside, moments
private final DragCalculator      dragCalculator;        // axial: friction/pressure/base/override CD

public BarrowmanCalculator() {
    this(new BarrowmanStabilityCalculator(), new BarrowmanDragCalculator());
}
public BarrowmanCalculator(StabilityCalculator stabilityCalculator, DragCalculator dragCalculator);
```

This split lets the engine swap in lookup-table implementations (`LookupTableStabilityCalculator`,
`LookupTableDragCalculator`) without touching the façade — see §6.

### 2a. CP path (`getCP` / stability)

`BarrowmanCalculator.getCP` → `checkCache` → `stabilityCalculator.getCP(...)`.

`BarrowmanStabilityCalculator` (file `BarrowmanStabilityCalculator.java`, `implements
StabilityCalculator`) is the real extended-Barrowman engine:

- `STALL_ANGLE = 17.5 deg`.
- `getCP(...)` just returns `calculateNonAxialForces(...).getCP()`.
- **`calculateNonAxialForces`** is the heart of the Barrowman summation:
  1. `ensureCalcMap(configuration)` — lazily build a `Map<RocketComponent, RocketComponentCalc>`
     (see §3) for every aerodynamic component / assembly.
  2. Get the `InstanceMap` of active instances (`configuration.getActiveInstances()`).
  3. For each component, for each of its instance contexts, call the component's
     `calcObj.calculateNonaxialForces(conditions, context.transform, instanceForces, warnings)`.
  4. Transform the instance-local CP into absolute coordinates, zero Y/Z, and set
     `Cm = CN * CP.x / refLength` per instance.
  5. **Merge** all instance/component forces into one `AerodynamicForces` (the `merge()` method
     adds CN, Cm, Cside, Cyaw, Croll and accumulates the CNa-weighted CP — this is exactly the
     Barrowman "sum CNa, CP = sum(CNa_i * x_i)/sum(CNa_i)" rule, implemented through the weighted
     `cpCNa` coordinate; see §5).
- **`getForceAnalysis`** recurses the component tree (`calculateForceAnalysis`) producing two maps:
  `eachMap` (per leaf component) and `assemblyMap` (per assembly = aggregate of its children),
  bundled in a `StabilityForceBreakdown`.
- **Damping moments** (`calculateDampingMoments`): computes a `mul` term from a cached average
  body diameter, body length, fin planform/positions, then
  `pitchDampingMoment = sign(pitchRate) * min(mul*(pitchRate/v)^2, Cm)` (and similarly yaw).
  `mul` is multiplied by 3 ("Higher damping yields much more realistic apogee turn").
- **Caches** (`voidAerodynamicCache` clears): `calcMap`, `cacheDiameter`, `cacheLength`.
- **Calc-map construction** uses reflection by naming convention:
  ```java
  Reflection.construct("info.openrocket.core.aerodynamics.barrowman", comp, "Calc", comp);
  ```
  i.e. for a `FinSet` it instantiates `FinSetCalc`, for `BodyTube` → `BodyTubeCalc`/`TubeCalc`
  subclass, etc. A Python port can replace this with a `type(component) -> calc class` dict.

`getWorstCP` is inherited from `AbstractAerodynamicCalculator` (360-way theta sweep).

### 2b. CD path (`BarrowmanDragCalculator`)

File: `BarrowmanDragCalculator.java`, `implements DragCalculator`. CD is **split into four additive
parts**, each summed over instances and components:

```
CD_total = frictionCD + pressureCD + baseCD + overrideCD
```

`calculateDrag(...)` sets `frictionCD/pressureCD/baseCD/overrideCD`, then `CD` and
`CDaxial = calculateAxialCD(conditions, CD)` on the target `AerodynamicForces`.

- **Friction drag** (`calculateFrictionCD`):
  - Reynolds number `Re = velocity * lengthAerodynamic / kinematicViscosity`.
  - Skin-friction coefficient `Cf` from `calculateFrictionCoefficient(config, mach, Re)` —
    branch on `isPerfectFinish()`; laminar/turbulent regimes with compressibility corrections
    `c1`,`c2` blended across Mach 0.9–1.1.
  - Surface-roughness limit per `Finish` enum:
    `0.032 * (roughnessSize / lengthAerodynamic)^0.2 * roughnessCorrection(mach)`.
  - Each component's `calculateFrictionCD(conditions, componentCf, warnings)` is called; body
    (symmetric) contributions and "other" contributions tracked separately, multiplied by instance
    count. A fineness-ratio correction `(1 + 1/(2*fB))` (where `fB = (maxX-minX+1e-4)/maxR`) is
    applied to the body friction total.
- **Pressure drag** (`calculatePressureCD`):
  - Computes `stagnationCD = calculateStagnationCD(mach)` and `baseCD = calculateBaseCD(mach)`
    (static helpers, see formulas below).
  - Sums each component's `calculatePressureCD(conditions, stagnationCD, baseCD, warnings)`.
  - Adds a **forward-facing disk** term for diameter increases between successive symmetric
    components: `stagnation * pi*(foreR^2 - prevAftR^2) / refArea`.
- **Base drag** (`calculateBaseCD`):
  - `base = calculateBaseCD(mach)`.
  - For symmetric components, a trailing-edge step term when the next component is narrower:
    `base * pi*(aftR^2 - nextForeR^2) / refArea`.
  - For non-symmetric aero components (fins, etc.) calls
    `calculateComponentBaseCD(conditions, base, warnings)`.
- **Override drag** (`calculateOverrideCD`): when a component/assembly has its CD overridden by the
  user (`isCDOverridden()` and not overridden by an ancestor), uses `instanceCount * getOverrideCD()`.

Static drag-coefficient helpers (also re-exported as statics on `BarrowmanCalculator`):

```java
public static double calculateStagnationCD(double m);
public static double calculateBaseCD(double m);
```
with the implemented formulas:
- Stagnation: `pressure = (m<=1) ? 1 + m^2/4 + m^4/40 : 1.84 - 0.76/m^2 + 0.166/m^4 + 0.035/m^6`,
  then `stagnationCD = 0.85 * pressure`.
- Base: `(m<=1) ? 0.12 + 0.13*m^2 : 0.25/m`.

**Axial conversion** (`calculateAxialCD` / `toAxialDrag`): maps total CD to axial CD as a function
of AoA using two precomputed polynomials (`axialDragPoly1` for AoA < 17°, `axialDragPoly2` for
17°..90°) built once via `PolyInterpolator`. Multiplier is ~1.0 at AoA 0, ~1.3 near 17°, falling to
0 at 90°; sign flips for AoA > 90°.

---

## 3. Per-component calculator pattern

Base class: `barrowman/RocketComponentCalc.java` (abstract). One subclass per component family.
The stability and drag calculators each build their own `Map<RocketComponent,
RocketComponentCalc>` by reflection (`<ComponentSimpleName> + "Calc"` in the `barrowman` package).

### Base class contract

```java
public abstract class RocketComponentCalc {
    public RocketComponentCalc(RocketComponent component);

    // Normal/side forces, pitch/yaw/roll moments, CP (local coords), CNa -> into `forces`.
    public abstract void calculateNonaxialForces(FlightConditions conditions,
                                                 Transformation transform,
                                                 AerodynamicForces forces,
                                                 WarningSet warnings);

    public abstract double calculateFrictionCD(FlightConditions conditions,
                                               double componentCf,
                                               WarningSet warnings);

    // Fore/pressure drag (NOT base drag, NOT body discontinuities).
    public abstract double calculatePressureCD(FlightConditions conditions,
                                               double stagnationCD, double baseCD,
                                               WarningSet warnings);

    // Trailing-edge / base drag. Default returns 0; override where meaningful (fins).
    public double calculateComponentBaseCD(FlightConditions conditions,
                                           double baseCD, WarningSet warnings) { return 0; }

    public double calculateReynoldsNumber(double length, FlightConditions conditions);
}
```

### Concrete calculators present (in `barrowman/`)

| Calculator | Handles | Notes |
|---|---|---|
| `SymmetricComponentCalc` | `SymmetricComponent` (nose cones, body tubes, transitions) | Barrowman CP/CNa extended with Galejs body-lift (`BODY_LIFT_K = 1.1`). Supersonic CNa/CP assumed equal to subsonic. There is **no separate `NoseConeCalc`/`TransitionCalc`/`BodyTubeCalc`** — all symmetric airframe parts share this one class. |
| `FinSetCalc` | `FinSet` | Largest calculator. `STALL_ANGLE = 20 deg`. Divides each fin chord into `DIVISIONS = 48`; computes MAC length/lead/span, fin area, aspect ratio, sweep cosines, roll damping. Overrides `calculateComponentBaseCD` for fin trailing-edge drag. |
| `TubeCalc` (abstract) | `Tube` | Base for tube-like internal/flow components; implements `calculatePressureCD` (inner/outer area, internal flow). |
| `TubeFinSetCalc` | tube fins | Own `calculateNonaxialForces`/`calculateFrictionCD`/`calculatePressureCD`. |
| `LaunchLugCalc` | launch lugs | Friction + nonaxial. |
| `RailButtonCalc` | rail buttons | Friction + pressure + nonaxial. |
| `ComponentAssemblyCalc` | `ComponentAssembly` (stages, pods) | All methods return 0 / no-op — an assembly is only a summation of its children. |

Constructors take the concrete component type, precompute geometry once (e.g.
`SymmetricComponentCalc` caches `length`, `foreRadius`, `aftRadius`, `fineness`, `frontalArea`,
`fullVolume`, `planformArea`, `wetArea`, `sinphi`; `FinSetCalc` caches MAC/aspect-ratio/chord
arrays). A Python port should likewise build a calc object per component and cache geometry.

Verbatim example signatures from `SymmetricComponentCalc`:

```java
public void   calculateNonaxialForces(FlightConditions conditions, Transformation transform,
                                       AerodynamicForces forces, WarningSet warningSet);
public double calculateFrictionCD(FlightConditions conditions, double componentCf, WarningSet warningSet);
public double calculatePressureCD(FlightConditions conditions, double stagnationCD, double baseCD,
                                  WarningSet warningSet);
```
and from `FinSetCalc` additionally:
```java
public double calculateComponentBaseCD(FlightConditions conditions, double baseCD, WarningSet warnings);
```

---

## 4. `FlightConditions` — input state

File: `FlightConditions.java`. `implements Cloneable, ChangeSource, Monitorable`. This is the
momentary flight state fed into every aero calculation. It is **mutable and fires change events**;
it is `clone()`-able (used by the worst-CP sweep and per-sim copies).

Fields and their getters/setters:

| Field | Default | Getter / Setter | Meaning |
|---|---|---|---|
| `refLength` | 1.0 m | `getRefLength` / `setRefLength` | reference length; setting it recomputes `refArea = pi*(L/2)^2` |
| `refArea` | `pi/4` | `getRefArea` / `setRefArea` | reference area; setting it recomputes `refLength` |
| `aoa` | 0 | `getAOA` / `setAOA(aoa)` / `setAOA(aoa, sinAOA)` | angle of attack, clamped to `[0, pi]` |
| `sinAOA` | 0 | `getSinAOA` | sine of AoA (cached) |
| `sincAOA` | 1.0 | `getSincAOA` | `sin(aoa)/aoa`, equals 1 at AoA 0 (avoids div-by-zero) |
| `theta` | 0 | `getTheta` / `setTheta` | lateral (roll-plane) wind direction |
| `mach` | 0.3 | `getMach` / `setMach` | Mach number; clamped `>= 0`; setting recomputes `beta` |
| `beta` | from mach | `getBeta` | Prandtl-Glauert factor `sqrt(|1-M^2|)`, floored at `MIN_BETA = 0.25` |
| `rollRate` | 0 | `getRollRate` / `setRollRate` | roll angular rate |
| `pitchRate` | 0 | `getPitchRate` / `setPitchRate` | pitch angular rate (damping) |
| `yawRate` | 0 | `getYawRate` / `setYawRate` | yaw angular rate (damping) |
| `pitchCenter` | `Coordinate.NUL` | `getPitchCenter` / `setPitchCenter` | reference point (CG) for damping moments |
| `atmosphericConditions` | new `AtmosphericConditions` | `getAtmosphericConditions` / `setAtmosphericConditions` | density, speed of sound, kinematic viscosity |

Derived velocity helpers:

```java
public double getVelocity();             // mach * atmosphericConditions.getMachSpeed()
public void   setVelocity(double v);     // setMach(v / machSpeed)
```

Constructor `FlightConditions(FlightConfiguration config)` seeds `refLength` from
`config.getReferenceLength()` (or 1 m if null). `setReference(config)` re-syncs it.
`beta` is floored to 0.25 (`MIN_BETA`) so supersonic/transonic divisions stay finite. AoA is always
clamped to `[0, pi]`; `setAOA` recomputes `sinAOA`/`sincAOA` (using the small-angle shortcut below
0.001 rad). Any setter that changes a value calls `fireChangeEvent()` and bumps `modID`.

---

## 5. `AerodynamicForces` — output structure

File: `AerodynamicForces.java`. `implements Cloneable, Monitorable`. Carries the full force/moment
coefficient set for one component, one assembly, or the whole rocket (`getComponent()` identifies
which; the `Rocket` component marks the grand total).

Stored coefficients (all `double`, initialised to `NaN`):

| Field | Getter/Setter | Meaning |
|---|---|---|
| `cpCNa` (a `CoordinateIF`) | `getCP` / `setCP` | CP position with **weight = CNa**. Internally stored CNa-weighted: `setCP(cp)` stores `(x*CNa, y*CNa, z*CNa, CNa)`; `getCP()` divides back out. This is what makes `merge()` perform the Barrowman CNa-weighted CP average. |
| `CN` | `getCN` / `setCN` | normal force coefficient |
| `Cm` | `getCm` / `setCm` | pitching moment coefficient (about coord origin) |
| `Cside` | `getCside` / `setCside` | side force coefficient (Cy) |
| `Cyaw` | `getCyaw` / `setCyaw` | yaw moment coefficient (Cn) |
| `Croll` | `getCroll` / `setCroll` | roll moment coefficient (Cl) |
| `CrollDamp` | `getCrollDamp` / `setCrollDamp` | roll damping coefficient |
| `CrollForce` | `getCrollForce` / `setCrollForce` | roll forcing coefficient |
| `CDaxial` | `getCDaxial` / `setCDaxial` | axial drag coefficient (CA) |
| `CD` | `getCD` / `setCD` | total drag coefficient (parallel to airflow) |
| `pressureCD` | `getPressureCD` / `setPressureCD` | fore/pressure drag part |
| `baseCD` | `getBaseCD` / `setBaseCD` | base (trailing-edge) drag part |
| `frictionCD` | `getFrictionCD` / `setFrictionCD` | skin-friction drag part |
| `overrideCD` | `getOverrideCD` / `setOverrideCD` | user override drag part |
| `pitchDampingMoment` | `getPitchDampingMoment` / `setPitchDampingMoment` | pitch damping moment |
| `yawDampingMoment` | `getYawDampingMoment` / `setYawDampingMoment` | yaw damping moment |
| `axisymmetric` | `isAxisymmetric` / `setAxisymmetric` | flag |

Important methods:

```java
public AerodynamicForces zero();                     // set all coefficients to 0 (component kept)
public void              reset();                     // set all to NaN / null
public AerodynamicForces merge(AerodynamicForces o);  // CNa-weighted CP add + sum CN,Cm,Cside,Cyaw,Croll,CrollDamp,CrollForce
public AerodynamicForces clone();
public double getCD();        // returns override if component CD-overridden; 0 if overridden by ancestor
public double getCDTotal();   // getCD() * component.getInstanceCount()
```

The override-aware getters (`getCD`, `getPressureCD`, `getBaseCD`, `getFrictionCD`, `getOverrideCD`)
return 0 or the override value depending on `component.isCDOverridden()` /
`isCDOverriddenByAncestor()` — replicate this conditional logic in a port.

Related container: `StabilityForceBreakdown` (file `StabilityForceBreakdown.java`) simply holds the
two maps from the stability analysis:
```java
Map<RocketComponent, AerodynamicForces> getComponentForces();  // per leaf component
Map<RocketComponent, AerodynamicForces> getAssemblyForces();   // per assembly (incl. Rocket total)
```

---

## 6. Lookup-table system (CSV Mach/AoA)

An alternative to analytic Barrowman: precomputed `(Mach, AoA) -> coefficients` tables, e.g. from
CFD. Wired in through the same `StabilityCalculator` / `DragCalculator` interfaces so a
`BarrowmanCalculator` can be constructed with lookup-backed collaborators.

### `MachAoALookup` (file `lookup/MachAoALookup.java`)

Immutable interpolating table. Internals:

- `NavigableMap<Double, List<Row>> rowsByMach` — rows grouped and sorted by Mach (a `TreeMap`);
  within each Mach, rows are sorted by AoA. `hasAoA` flags whether the table has an AoA dimension.
- A `Row` holds `mach`, `aoa`, and an unmodifiable `Map<String,Double> values` (the coefficient
  columns, e.g. `cd`, or `cn`/`cm`/`cp`).
- Bounds: `minMach/maxMach/minAoA/maxAoA`.

Public API:

```java
public double interpolate(double mach, double aoaDegrees, String column);
public boolean hasAoA();
public double getMinMach(); public double getMaxMach();
public double getMinAoA();  public double getMaxAoA();
public Set<String> getValueColumns();

public static Builder builder(Collection<String> valueColumns);
public static Builder dragBuilder();       // columns {"cd"}
public static Builder stabilityBuilder();  // columns {"cn","cm","cp"}
```

Interpolation (**bilinear: Mach outer, AoA inner**):

1. Clamp Mach to `[minMach, maxMach]` (logs a one-time warning when out of range).
2. `floorKey` / `ceilingKey` on `rowsByMach` give the bracketing Mach values.
3. For each bracket, `interpolateAoA(...)` clamps AoA to `[minAoA, maxAoA]`, finds the bracketing
   AoA rows, and linearly interpolates the column value (or returns the single value if `!hasAoA`).
4. Linearly interpolate between the two Mach results: `lerp(a, b, frac) = a + (b-a)*frac`.

Column-name handling is forgiving: `normalize()` lowercases and strips spaces/underscores, and
`"angleofattack"`/`"angle of attack"` is aliased to `aoa`.

### `CsvMachAoALookup` (file `lookup/CsvMachAoALookup.java`)

Static factory that loads/parses CSV into a `MachAoALookup`. No instances (private constructor).

```java
public static MachAoALookup fromCsv(Path path, Collection<String> requiredValueColumns);
public static MachAoALookup fromCsv(Path path, Collection<String> requiredValueColumns, char separator);
public static MachAoALookup parse(List<String> lines, Collection<String> requiredValueColumns, char separator);
```

CSV format / parsing rules:

- First non-blank, non-`#` line is the **header**; remaining lines are data.
- Blank lines and lines starting with `#` are skipped (comments).
- The header **must** contain a `mach` column; an `aoa` (or `angle of attack`) column is optional —
  its presence determines `hasAoA`. All `requiredValueColumns` must be present or it throws
  `IllegalArgumentException`.
- Each value cell is parsed with `Double.parseDouble`; bad numbers / missing cells throw
  `IllegalArgumentException`.
- AoA values in the CSV are **degrees** (stored as degrees; `interpolate` takes `aoaDegrees`).

### Lookup-backed calculators

- `LookupTableDragCalculator` (file `LookupTableDragCalculator.java`, `implements DragCalculator`):
  - Constructed from a `Path` (CSV with column `cd`) or a prebuilt `MachAoALookup`.
  - `calculateDrag` looks up `cd = table.interpolate(mach, toDegrees(aoa), "cd")`, assigns the whole
    value to the total `frictionCD`+`CD` (pressure/base/override set to 0), zeroes per-component
    maps, and computes `CDaxial` via the same AoA polynomial scheme as Barrowman.
- `LookupTableStabilityCalculator` (file `LookupTableStabilityCalculator.java`, `implements
  StabilityCalculator`):
  - CSV columns `cn`, `cm`, `cp`. Stall angle is `toRadians(maxAoA)` if the table has an AoA
    dimension (otherwise infinite — never stalls).

These let a port either compute coefficients analytically (Barrowman) or interpolate them from a
data table behind one common interface.

---

## 7. `WarningSet` usage in the aero calcs (brief)

`WarningSet` (package `info.openrocket.core.logging`) is a sink for non-fatal modelling warnings,
threaded through every aero method as the trailing `warnings` parameter.

- If a caller passes `null`, calculators substitute a private `ignoreWarningSet` so warnings are
  silently dropped.
- Component calcs accumulate geometry warnings during construction (e.g. `FinSetCalc` keeps a
  `geometryWarnings` set and does `warnings.addAll(geometryWarnings)` inside
  `calculateNonaxialForces`).
- `BarrowmanStabilityCalculator.checkGeometry(...)` adds typed warnings such as
  `OPEN_AIRFRAME_FORWARD`, `DIAMETER_DISCONTINUITY`, `ZERO_VOLUME_BODY`, `AIRFRAME_GAP`,
  `AIRFRAME_OVERLAP`, `PODSET_FORWARD`, `PODSET_OVERLAP` via `warnings.add(Warning.X, component)`.
- A Python port can model this as a collecting set/list of warning records passed down the call
  chain, with a no-op default.

---

## Reimplementation checklist (summary)

1. **Two strategies behind one calculator façade**: stability (CP/CN/Cm/moments) + drag
   (friction/pressure/base/override CD). Keep them swappable (analytic vs lookup table).
2. **Per-component calc objects** built once per component (cache geometry), dispatched by component
   type, implementing `calculateNonaxialForces`, `calculateFrictionCD`, `calculatePressureCD`, and
   optionally `calculateComponentBaseCD`.
3. **Barrowman summation** via CNa-weighted CP accumulation (`merge`) over active instances;
   `Cm = CN * CP.x / refLength`.
4. **CD = friction + pressure + base + override**, each summed over instances with the body
   fineness correction and inter-component step (disk/base) terms; convert to axial CD via the AoA
   polynomial.
5. **Cache invalidation** keyed on rocket modification IDs (`checkCache` / `voidAerodynamicCache`).
6. **FlightConditions** as the mutable input state (Mach, AoA + sin/sinc, theta, roll/pitch/yaw
   rates, beta floored at 0.25, ref length/area, atmospheric conditions).
7. **AerodynamicForces** as the output coefficient bundle (CN, Cm, Cside, Cyaw, Croll, CD split,
   CDaxial, damping moments, CP-with-CNa-weight).
8. **MachAoALookup** bilinear (Mach outer / AoA inner) interpolation with range clamping, loaded
   from CSV by `CsvMachAoALookup`.
