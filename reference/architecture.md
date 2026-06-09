# OpenRocket Simulation Architecture (reference for a Python reimplementation)

This document maps the flight-simulation subsystem of OpenRocket
(`info.openrocket.core.simulation`) so that the architecture can be
reimplemented without reading the Java source. It is derived from a read-only
inspection of the `core/src/main/java/info/openrocket/core/simulation/`
package. Signatures are quoted verbatim (signatures only). Java method bodies
are described, not pasted.

## 0. Big picture and design patterns

The simulation is split into two cleanly separated responsibilities:

- **Engine** (`SimulationEngine` / `BasicEventSimulationEngine`) — the
  *orchestrator*. Owns the high-level control flow: the main loop, the flight
  **event queue**, stage handling / branching, and choosing which physics
  integrator to use at any moment. It does **no** physics itself.
- **Stepper** (`SimulationStepper` and its implementations) — the *physics
  integrator* (**Strategy pattern**). Each stepper advances the rocket state by
  one time step using a particular model (full 6-DOF RK4 flight, parachute
  descent, tumbling, sitting on the ground). The engine swaps the active
  strategy depending on flight phase.

Supporting roles:

- `SimulationStatus` — **mutable** per-instant state (the integration variable
  vector plus flags, motor states, and the event queue). Acts as the unit of
  work that is cloned for RK sub-steps and for new stage branches.
- `SimulationConditions` — **immutable** setup (launch params, time step,
  pluggable physics models). Strategy/dependency-injection container for the
  atmosphere / wind / gravity / aerodynamic / mass models.
- `FlightData` / `FlightDataBranch` — output accumulators. One branch per
  stage; the steppers append a data point per step.
- `FlightEvent` + `EventQueue` — the discrete-event layer driving phase
  transitions (ignition, burnout, separation, deployment, apogee, ground hit…).

Key collaboration contract (from `SimulationStepper` Javadoc): when `step()` is
called, a **new point is added to the flight data branch and the current
status is saved into that point first**, then the physics parameters for that
instant are computed and saved into the same point. Note the documented
caveat: for the RK4 stepper only the parameters at the *start* of the step are
stored even though they vary across the sub-steps.

---

## 1. `BasicEventSimulationEngine` — orchestration

File: `BasicEventSimulationEngine.java`. Implements `SimulationEngine`.

### 1.1 Steppers it holds

```java
private       SimulationStepper flightStepper = new RK4SimulationStepper();
private final SimulationStepper landingStepper = new BasicLandingStepper();
private final SimulationStepper tumbleStepper  = new BasicTumbleStepper();
private final SimulationStepper groundStepper  = new GroundStepper();
private SimulationStepper currentStepper;
```

`flightStepper` is reassigned in `simulate()` according to
`SimulationConditions.getSimulation().getOptions().getSimulationStepperMethodChoice()`
(`SimulationStepperMethod.RK4` → `RK4SimulationStepper`, `RK6` →
`RK6SimulationStepper`). The other three steppers are fixed.

`THRUST_TUMBLE_CONDITION = 0.01` N is the thrust threshold below which a tumble
transition is allowed (above it, tumbling under thrust is an abort).

### 1.2 Entry point — `simulate(...)`

```java
@Override
public void simulate(SimulationConditions simulationConditions) throws SimulationException
public FlightData getFlightData()
```

Flow:

1. Create a fresh `FlightData`.
2. Pick the flight stepper from the stepper-method option.
3. Resolve the `FlightConfigurationId`; **clone** the rocket's
   `FlightConfiguration` (and copy stage activation) so the sim never mutates
   the model.
4. Build the initial `SimulationStatus(simulationConfig, simulationConditions)`.
5. Create the initial `FlightDataBranch` named after the topmost active stage
   (or a localized fallback), seeded with `FlightDataType.TYPE_TIME`. Attach the
   shared `WarningSet` and the branch to the status.
6. **Sanity / abort checks**: no active stages →
   `SimulationAbort.Cause.NO_ACTIVE_STAGES`; no motors →
   `NO_MOTORS_DEFINED`; no recovery device → warning `NO_RECOVERY_DEVICE`.
7. Enqueue a `FlightEvent.Type.LAUNCH` at t=0 and `push` the status onto a
   `Deque<SimulationStatus> toSimulate` (the stack of branches to run).
8. **Branch loop** (`do { ... } while (!toSimulate.isEmpty())`): pop a status,
   register its branch into `flightData`, fire branch-start listeners, call
   `simulateLoop(...)`, then `immute()` the branch. Empty branches add a
   `Warning.EMPTY_BRANCH`. New booster branches are *pushed* during event
   handling (see §1.5 stage separation), so this loop processes the whole tree.
9. `finally`: `flightData.calculateInterestingValues()` (max alt/vel/accel,
   apogee time, etc.).

### 1.3 Per-branch loop — `simulateLoop(...)`

```java
private void simulateLoop(SimulationConditions simulationConditions) throws SimulationException
```

**Initial stepper selection** (the phase decision logic; in priority order):

- `status.isLanded()` → `groundStepper`
- else `status.isTumbling()` → `tumbleStepper`
- else `!getDeployedRecoveryDevices().isEmpty()` → `landingStepper`
- else → `flightStepper` (RK4/RK6)

Then `currentStatus = currentStepper.initialize(currentStatus)` and the main
`while (handleEvents(...))` loop runs. Each iteration:

1. `handleEvents()` processes all due events and returns `false` to terminate.
2. `firePreStep` listener gate; compute `maxStepTime` = min of (next queued
   event time − now, floored at 0.001) or 0 if landed; if `> EPSILON`, call
   `currentStepper.step(currentStatus, maxStepTime)`. **The event queue thus
   bounds every integration step so the stepper never steps over an event.**
3. `firePostStep`, then `checkNaN()` (guards position, velocity, orientation
   quaternion, rotation velocity, launch-rod length).
4. Post-step bookkeeping that **generates new events** by inspecting state:
   - Add an `ALTITUDE` event (old→new Z as a `Pair`) unless landed.
   - Track `maxAlt`.
   - Pre-liftoff: clamp the rocket out of the ground; detect **LIFTOFF** when
     relative Z > 0.02 m.
   - Post-liftoff: detect **GROUND_HIT** when Z < EPSILON.
   - Detect **LAUNCHROD** clearance when distance from origin exceeds
     `getLaunchRodLength()`.
   - Detect **APOGEE** when Z drops 0.01 m below `maxAlt` (timestamped at the
     *previous* step time).
   - Fin-stall / large-AOA check: compares stall angle vs AOA using last CP, CG,
     AOA from the data branch. If unstable (CG behind CP) → **TUMBLE** event;
     if stable → `Warning.LargeAOA`.
   - If landed and queue empty → **SIMULATION_END**.

### 1.4 Event pump — `handleEvents(...)` and `nextEvent()`

```java
private boolean handleEvents(SimulationConditions simulationConditions) throws SimulationException
private FlightEvent nextEvent()
```

`nextEvent()` peeks the `EventQueue`; if no motor has ignited yet it
fast-forwards `simulationTime` to the next event time (so the sim doesn't crawl
in dead time). It returns/`poll()`s the event only if its time ≤ current sim
time, else `null` (meaning "stop handling, go take a step").

`handleEvents()` loops `nextEvent()` until `null`, and for each event:

- Tests every `MotorClusterState` for ignition (`testForIgnition`) and, on a
  match, queues an `IGNITION` event at now + ignition delay.
- Fires listener hooks (`fireHandleFlightEvent`, and for deployments
  `fireRecoveryDeviceDeployment`) which can veto handling.
- Checks each active stage's `StageSeparationConfiguration` against the event;
  queues a `STAGE_SEPARATION` (at event time + separation delay).
- Checks each `RecoveryDevice`'s `DeploymentConfiguration`; queues a
  `RECOVERY_DEVICE_DEPLOYMENT` (delayed by max(1 ms, deploy delay) so separation
  resolves first).
- Then a big `switch (event.getType())` (see §1.5).

After the loop, two global terminators: if `simulationTime ≥
getMaxSimulationTime()` it queues `SIMULATION_END` and returns `false`; if no
motor ever ignited it aborts (`NO_MOTORS_FIRED`).

### 1.5 Event switch (state transitions)

- **LAUNCH** — record to branch.
- **IGNITION** — ignore duplicate ignitions; `motorState.ignite()`, set
  `motorIgnited`, fire listener. **Queues one `ALTITUDE` event per motor
  thrust-curve time point** (this is how RK4 gets fine time steps across the
  burn) and queues the motor's **BURNOUT** at now + burn time.
- **LIFTOFF** — set `liftoff`.
- **LAUNCHROD** — set `launchRodCleared`.
- **BURNOUT** — abort if not lifted off (`NO_LIFTOFF`); `motorState.burnOut()`;
  if the motor has an ejection charge, queue **EJECTION_CHARGE** at now +
  ejection delay.
- **EJECTION_CHARGE** — `motorState.expend()`.
- **STAGE_SEPARATION** — *branching*. If the stage above is active: record
  event; warn on bad separation order / early separation; create a **new
  `SimulationStatus(currentStatus)`** for the booster with a new
  `FlightDataBranch` copied from the parent; `clearStagesBelow` on the current
  (sustainer) status and `clearStagesAbove` on the booster; drop now-unattached
  events from each; `toSimulate.push(boosterStatus)`; re-`checkGeometry`.
- **APOGEE** — set `apogeeReached`; if no recovery deployed yet, record the
  optimum altitude/time on the branch.
- **RECOVERY_DEVICE_DEPLOYMENT** — only if its stage is active. Abort if any
  motor is still thrusting (`DEPLOY_UNDER_THRUST`); warn on launch-rod /
  high-speed deployment; add device to `deployedRecoveryDevices`; if apogee not
  reached, run a **nested coast simulation** (`computeCoastTime()`) to find the
  optimum altitude; **switch to `landingStepper`** and re-`initialize`.
- **GROUND_HIT** — set `landed`; take one final `step(status, Double.NaN)` to
  freeze impact values; switch to `groundStepper`; re-`initialize`.
- **SIM_ABORT** — `storeData()`, record event, return `false`.
- **SIMULATION_END** — record event, return `false`.
- **ALTITUDE** — no-op (only used to bound RK4 step size).
- **TUMBLE** — inhibited if recovery deployed or landed; abort if thrust above
  `THRUST_TUMBLE_CONDITION` (`TUMBLE_UNDER_THRUST`); else switch to
  `tumbleStepper`, set `tumbling`.

Any non-`ALTITUDE`/`GROUND_HIT`/`SIMULATION_END` event after landing →
`Warning.EventAfterLanding`.

### 1.6 Helper methods

```java
private void checkGeometry(SimulationStatus currentStatus) throws SimulationException
private void checkNaN() throws SimulationException
private FlightData computeCoastTime() throws SimulationException
```

- `checkGeometry` — run at branch start and after each separation: aborts on
  zero aerodynamic length (`ACTIVE_LENGTH_ZERO`), on un-computable CP for the
  sustainer (`NO_CP`) or transitions a booster to tumbling, and adds filtered
  open-airframe geometry warnings.
- `computeCoastTime` — clones conditions, strips user listeners, adds the system
  `OptimumCoastListener`, runs a whole **nested** `BasicEventSimulationEngine`
  to determine optimum (coast-to-apogee) altitude/time for delay optimization.

### 1.7 Termination conditions (summary)

A branch ends when `handleEvents` returns `false`, which happens on:
`SIMULATION_END` (queued by ground-hit + empty queue, by max-sim-time, or
externally), `SIM_ABORT`, or a `SimulationException` propagating out. The whole
simulation ends when `toSimulate` is empty.

---

## 2. `SimulationStepper` — the strategy contract

File: `SimulationStepper.java`. Full interface:

```java
public interface SimulationStepper {
    public SimulationStatus initialize(SimulationStatus status);
    public void step(SimulationStatus status, double maxTimeStep) throws SimulationException;
}
```

- **`initialize(status)`** — return a `SimulationStatus` suitable for this
  stepper (typically a copy, possibly a different concrete state type). The
  engine reassigns `currentStatus` to the return value every time it switches
  steppers.
- **`step(status, maxTimeStep)`** — advance one time step, at most `maxTimeStep`
  (used to avoid stepping past the next event). A special call with
  `maxTimeStep = Double.NaN` means "this is the final ground-impact step: record
  current status/params, then set the status to a resting-on-ground state, but
  don't actually advance" (see `landedValues`).

There is **no `getMethodName()`** in this interface (despite the task's
guess); stepper identity/selection is handled by the `SimulationStepperMethod`
enum on the engine side, not by the stepper. The enum's contract:

```java
public enum SimulationStepperMethod { RK4, RK6;
    public abstract String getName();
    public abstract String getShortName();
    public abstract String getDescription();
}
```

### 2.1 `AbstractSimulationStepper` (shared base)

File: `AbstractSimulationStepper.java`. `implements SimulationStepper`.
`MIN_TIME_STEP = 0.001`. Provides the shared physics-model plumbing that every
concrete stepper reuses, each method wrapped with pre/post simulation-listener
hooks that can override results:

```java
abstract void calculateAcceleration(SimulationStatus status, DataStore store) throws SimulationException;
protected void calculateFlightConditions(SimulationStatus status, DataStore store) throws SimulationException;
protected AtmosphericConditions modelAtmosphericConditions(SimulationStatus status) throws SimulationException;
protected CoordinateIF modelWindVelocity(SimulationStatus status) throws SimulationException;
protected double modelGravity(SimulationStatus status) throws SimulationException;
protected RigidBody calculateStructureMass(SimulationStatus status) throws SimulationException;
protected RigidBody calculateMotorMass(SimulationStatus status) throws SimulationException;
protected void landedValues(SimulationStatus status, DataStore store) throws SimulationException;
protected void checkNaN(double d, String var);
protected void checkNaN(CoordinateIF c, String var);
protected void checkNaN(Quaternion q, String var);
```

- `calculateFlightConditions` builds a `FlightConditions`: atmosphere, wind,
  air-speed in body frame, theta (lateral wind direction), velocity, AOA, and
  roll/pitch/yaw rates; also fills `store.thetaRotation` and
  `store.lateralPitchRate`.
- Structural mass is **cached** by the configuration's `ModID` and recomputed
  only on change (e.g. a stage drop). Motor mass is recomputed every call.
- `landedValues` sets the status to a resting-on-ground state: NaN time step,
  zeroed forces/rates, zero velocity, Z position forced to 0.

#### `DataStore` (inner scratch/transfer object)

A mutable per-step bag of computed quantities (`timeStep`, `accelerationData`,
`flightConditions`, `rocketMass`, `motorMass`, `coriolisAcceleration`,
`launchRodDirection`, `forces`, `windVelocity`, `gravity`, `thrustForce`,
`dragForce`, `lateralPitchRate`, `thetaRotation`). Its key method:

```java
void storeData(SimulationStatus status)
```

writes ~50 `FlightDataType` channels into the current branch point (forces,
accelerations in world & body frame, mass/inertia/CG, flight conditions, drag
coefficients, CP/CNa/stability when off the rod, plus derived damping-moment,
corrective-moment, damping-ratio and natural-frequency analysis values). A
Python port should treat `DataStore` as the "compute one instant, then dump all
output channels" structure.

---

## 3. `RK4SimulationStepper` — one integration tick

File: `RK4SimulationStepper.java`. `extends AbstractSimulationStepper`.

Constants: `RECOMMENDED_TIME_STEP = 0.05`, `RECOMMENDED_MAX_TIME = 1200`,
`RECOMMENDED_ANGLE_STEP = 3°`, `PITCH_YAW_RANDOM = 0.0005`,
`MAX_ROLL_STEP_ANGLE ≈ 2·28.32°`, `MAX_ROLL_RATE_CHANGE = 2°`,
`MAX_PITCH_YAW_CHANGE = 4°`.

```java
@Override public SimulationStatus initialize(SimulationStatus original)
@Override public void step(SimulationStatus status, double maxTimeStep) throws SimulationException
private RK4Parameters computeParameters(SimulationStatus status, DataStore store) throws SimulationException
@Override void calculateAcceleration(SimulationStatus status, DataStore store) throws SimulationException
protected double calculateThrust(SimulationStatus status, DataStore store) throws SimulationException
private AccelerationData computeAcceleration(SimulationStatus status, DataStore store) throws SimulationException
private void calculateForces(SimulationStatus status, DataStore store) throws SimulationException
```

`initialize` precomputes the launch-rod direction unit vector from the rod
angle/direction and seeds a per-run `Random` from `randomSeed ^ 0x23E3A01F`
(used to add tiny pitch/yaw noise so flight is never "too perfect").

### 3.1 The integration variable vector

The RK state `y` consists of four `Coordinate`/`Quaternion` quantities held in
`SimulationStatus`:

- position `p` (`getRocketPosition`)
- linear velocity `v` (`getRocketVelocity`)
- orientation quaternion `q` (`getRocketOrientationQuaternion`)
- rotational (angular) velocity `ω` (`getRocketRotationVelocity`)

`RK4Parameters` is the derivative tuple at a point: `a` (linear accel), `v`
(linear vel), `ra` (rotational accel), `rv` (rotational vel).

### 3.2 `step()` flow

1. `status.storeData()` — open a new branch point and record kinematics.
2. `calculateFlightConditions(status, store)` — atmosphere etc. for the start
   point.
3. `k1 = computeParameters(status, store)`.
4. **NaN-maxTimeStep short-circuit**: if `maxTimeStep` is NaN this is the final
   ground-impact tick — store params, call `landedValues`, return.
5. **Time-step selection.** Compute `dt[0..7]` and take the minimum (records the
   limiting factor):
   - `dt[0]` user time step (`getTimeStep()`, floored at `MIN_TIME_STEP`;
     divided by 5 while on the rod),
   - `dt[1]` = `maxTimeStep`,
   - `dt[2]` = max angle step / lateral pitch rate,
   - `dt[3]` = `MAX_ROLL_STEP_ANGLE` / roll rate,
   - `dt[4]` = `MAX_ROLL_RATE_CHANGE` / rotational-accel Z,
   - `dt[5]` = `MAX_PITCH_YAW_CHANGE` / max(|rot-accel X|,|rot-accel Y|),
   - `dt[6]` = launch-rod length / |v| / 10 (while on rod),
   - `dt[7]` = 1.5 × previous time step.
   If the chosen step is within `userStep/20` of `maxTimeStep`, snap to
   `maxTimeStep`; never go below `userStep/20`. (This is adaptive **step-size
   limiting**, not RK error estimation — there is no embedded
   error-estimate/Richardson controller.)
6. `store.storeData(status)` then NaN-check the chosen step.
7. **k2, k3, k4** via three `status.clone()`s, each advanced by the appropriate
   fraction of the step using the previous `k`:
   - `k2 = f(t + h/2, y + k1·h/2)`
   - `k3 = f(t + h/2, y + k2·h/2)`
   - `k4 = f(t + h, y + k3·h)`
   Orientation is advanced by left-multiplying `q` with
   `Quaternion.rotation(rv·dt)`.
8. **Combine**: `Δ = h/6 · (k1 + 2·k2 + 2·k3 + k4)` for velocity, position and
   rotation velocity; orientation by the composed quaternion rotation, then
   `normalizeIfNecessary()`.
9. Update world position via `GeodeticComputationStrategy.addCoordinate`,
   advance `simulationTime` by `h`, reject backward/NaN steps, and throw
   `SimulationCalculationException` if any state magnitude² exceeds 1e18.

### 3.3 `computeParameters` / `computeAcceleration` (the `f`)

`computeParameters` calls `calculateAcceleration` (which fires pre/post
listeners around `computeAcceleration`) and packs the derivative tuple,
NaN-checking each component.

`computeAcceleration` is the 6-DOF force/torque model:

- `calculateStructureMass` + `calculateMotorMass` → combined `RigidBody`
  (abort if total mass < EPSILON, `ACTIVE_MASS_ZERO`).
- `calculateForces` (pre/post listeners, `calculateFlightConditions`, then
  `aerodynamicCalculator.getAerodynamicForces(...)`, plus the small random
  pitch/yaw moment perturbation).
- Dynamic pressure `q = ½ρV²`; axial drag, normal force `fN = CN·q·A`, side
  force `fSide = Cside·q·A`. `thrustForce = calculateThrust` (sum of motor
  thrust at current time). Linear accel in rocket frame, rotated to world via
  the orientation quaternion.
- Add gravity (`modelGravity`) and Coriolis acceleration.
- **Phase-specific constraints**: pre-liftoff → zero angular accel and clamp
  downward accel; on-rod → project linear accel onto rod direction, zero angular
  accel; free flight → compute moments shifted to CG (`Cm`, `Cyaw`, `Croll`),
  divide by inertias for angular acceleration, rotate to world frame.
- Returns an `AccelerationData` (linear + angular accel, in world and rocket
  coords).

---

## 4. `SimulationStatus` — mutable per-instant state

File: `SimulationStatus.java`. `implements Cloneable, Monitorable`.

Two constructors:

```java
public SimulationStatus(FlightConfiguration configuration, SimulationConditions simulationConditions)
public SimulationStatus(SimulationStatus orig)   // deep-ish copy for stage branching / stepper conversion
```

The first seeds t=0, launch position/velocity/world-position from the
conditions, initial orientation (roll angle of least wind stability, then rod
angle + direction), the effective launch-rod length (reduced by launch-lug
position), and `populateMotors()` (one `MotorClusterState` per motor config).
The copy constructor deep-clones conditions, configuration, motor list and event
queue, **shallow-copies** the flight data branch, and resets the warning set.

### 4.1 Core state (the integration vector + flags)

| Field | Getter / Setter |
| --- | --- |
| `time` | `getSimulationTime()` / `setSimulationTime(double)` |
| `position` (rel. to launch) | `getRocketPosition()` / `setRocketPosition(CoordinateIF)` |
| `worldPosition` (lat/lon/alt) | `getRocketWorldPosition()` / `setRocketWorldPosition(WorldCoordinate)` |
| `velocity` | `getRocketVelocity()` / `setRocketVelocity(CoordinateIF)` |
| `orientation` (quaternion) | `getRocketOrientationQuaternion()` / `setRocketOrientationQuaternion(Quaternion)` |
| `rotationVelocity` (angular) | `getRocketRotationVelocity()` / `setRocketRotationVelocity(CoordinateIF)` |
| `effectiveLaunchRodLength` | `get/setEffectiveLaunchRodLength` |
| `maxAlt`, `maxAltTime`, `maxZVelocity` | `getMaxAlt`/`setMaxAlt`, `getMaxAltTime`/`setMaxAltTime`, `getMaxZVelocity` |

### 4.2 Phase flags (all boolean get/set)

`motorIgnited`, `liftoff`, `launchRodCleared`, `apogeeReached`, `tumbling`,
`landed` — these drive the engine's stepper selection and event guards.
`setLaunchRodCleared(true)` also arms `startWarningsTime = now + 0.25 s`.

### 4.3 Collections & sub-objects

- `getConfiguration()` → `FlightConfiguration` (mutable stage activation).
- `getMotors()` / `getActiveMotors()` → `MotorClusterState` list (active =
  mount is active in current config).
- `getDeployedRecoveryDevices()` → `MonitorableSet<RecoveryDevice>`.
- `getEventQueue()` → the per-branch `EventQueue`.
- `getSimulationConditions()`, `getFlightDataBranch()`, `getWarnings()`.
- `getExtraData(String)` / `putExtraData(String,Object)` — scratchpad for
  listeners.

### 4.4 Behavior methods

```java
public void storeData()                              // open a branch point, write kinematic channels
public void addEvent(FlightEvent) throws SimulationException
public void abortSimulation(SimulationAbort.Cause) throws SimulationException
public void addWarning(Warning) / addWarnings(WarningSet)
public void removeUnattachedEvents()                 // drop events from detached components
public void copyProperties(SimulationStatus orig)    // copy kinematics + flags
@Override public SimulationStatus clone()            // shallow clone (used for RK sub-steps)
boolean recordWarnings()                             // warning-suppression policy
```

`storeData()` writes time, altitude (AGL & MSL), X/Y position, lat/lon, planar
position+direction, planar/Z/total velocity, orientation theta/phi, and
wall-clock computation time. `addEvent` is gated by an `fireAddFlightEvent`
listener; `abortSimulation` enqueues a `SIM_ABORT` event carrying a
`SimulationAbort`. `recordWarnings()` suppresses most warnings until 0.25 s
after rod clearance and once Z-velocity drops below 20 % of max.

---

## 5. `SimulationConditions` — immutable setup

File: `SimulationConditions.java`. `implements Monitorable, Cloneable`. A
holder of values that do **not** change during flight, and the
**dependency-injection point** for the pluggable physics models. Defaults shown.

Launch geometry / kinematics:

```java
double getLaunchRodLength()     // default 1 m
double getLaunchRodAngle()      // radians from vertical, default 0
double getLaunchRodDirection()  // 0 = north
WorldCoordinate getLaunchSite() // (lat,lon,alt) default (0,0,0)
CoordinateIF getLaunchPosition()// sim-frame start, default origin (air-start overrides)
CoordinateIF getLaunchVelocity()// default zero
GeodeticComputationStrategy getGeodeticComputation() // default SPHERICAL
```

Pluggable models (the strategy injection):

```java
WindModel getWindModel();
AtmosphericModel getAtmosphericModel();
GravityModel getGravityModel();
AerodynamicCalculator getAerodynamicCalculator();
MassCalculator getMassCalculator();
```

Integrator / run parameters:

```java
double getTimeStep();          // default RK4SimulationStepper.RECOMMENDED_TIME_STEP = 0.05
double getMaxSimulationTime();  // default RECOMMENDED_MAX_TIME = 1200
double getMaximumAngleStep();   // default RECOMMENDED_ANGLE_STEP = 3°
int    getRandomSeed();         // default 0
List<SimulationListener> getSimulationListenerList();
Simulation getSimulation();     // parent; supplies Rocket and FlightConfigurationId
```

`getRocket()`, `getFlightConfigurationID()`/`getMotorConfigurationID()` delegate
to the parent `Simulation`. `clone()` shallow-copies fields but deep-copies the
listener list (each listener is cloned). Every setter bumps a `ModID` for
change tracking.

---

## 6. `FlightData` / `FlightDataBranch` — output accumulation

### 6.1 `DataBranch<T extends DataType>` (generic base)

File: `DataBranch.java`. A column store: `Map<T, ArrayList<Double>> values`
plus per-type running `minValues`/`maxValues`, a `name`, a `Mutable` flag and a
`ModID`. Key methods:

```java
public void addType(T type);
public void addPoint();                      // append a new row (all NaN)
public void setValue(T type, double value);  // set value of `type` at the latest row; auto-creates new columns
public List<Double> get(T type);             // unmodifiable view
public List<Double> getClone(T type);
public Double getByIndex(T type, int index);
public double getLast(T type);               // NaN if absent
public double getMinimum(T type);  public double getMaximum(T type);
public int getLength();
public T[] getTypes();                       // sorted
public void immute();  public boolean isMutable();
```

**Append model**: a stepper calls `addPoint()` once per step (via
`status.storeData()`), then many `setValue(type, v)` calls fill that row.
Unset channels remain NaN. Columns can appear mid-flight; earlier rows are
back-filled with NaN.

### 6.2 `FlightDataBranch`

File: `FlightDataBranch.java`. `extends DataBranch<FlightDataType>`. One branch
per stage. Adds:

- A list of `FlightEvent`s with `addEvent`, `getEvents`, `getFirstEvent(type)`,
  `getLastEvent(type)`, `findEvent(UUID)`, `getDataIndexOfTime(double)`.
- Optimum-altitude bookkeeping: `get/setOptimumAltitude`,
  `get/setTimeToOptimumAltitude`, `getOptimumDelay()` (optimum time − last
  burnout), `getSeparationTime()`.
- Constructors: `(String name, FlightDataType... types)`; a copy constructor
  `(String name, RocketComponent srcComponent, FlightDataBranch parent)` that
  copies all parent rows + this stage's events (used at stage separation so the
  new branch starts with the pre-separation history); and a no-arg "empty"
  branch with all `FlightDataType.ALL_TYPES` defined and immuted.

### 6.3 `FlightDataType`

File: `FlightDataType.java`. `implements Comparable, Groupable, DataType`. A
flyweight describing one output channel: a localized name, a **symbol** (the
map key, e.g. `t`, `h`, `Vz`, `Vt`, `Az`), a `UnitGroup`, a
`FlightDataTypeGroup`, and a priority for ordering. Dozens of predefined static
constants (`TYPE_TIME`, `TYPE_ALTITUDE`, `TYPE_VELOCITY_TOTAL`,
`TYPE_THRUST_FORCE`, `TYPE_DRAG_FORCE`, `TYPE_MACH_NUMBER`, `TYPE_CP_LOCATION`,
`TYPE_CG_LOCATION`, `TYPE_STABILITY`, `TYPE_AOA`, …). New types can be created
on the fly via `newType(...)` / `getType(...)`; identity is the
case-insensitive symbol.

### 6.4 `FlightData` (top-level result)

File: `FlightData.java`. Holds an ordered `List<FlightDataBranch>` (branch 0 =
main/sustainer), a shared `WarningSet`, and summary scalars. Key methods:

```java
public void addBranch(FlightDataBranch branch);
public int getBranchCount();  public FlightDataBranch getBranch(int);  public List<FlightDataBranch> getBranches();
public WarningSet getWarningSet();
public void calculateInterestingValues();   // fills the summary scalars from branch 0
public void immute();
```

`calculateInterestingValues()` derives `maxAltitude`, `maxVelocity`,
`maxMachNumber`, `flightTime`, `timeToApogee`, `maxAcceleration` (pre-first-
deployment), and interpolates `launchRodVelocity` / `deploymentVelocity` /
`groundHitVelocity` at the times of the LAUNCHROD / RECOVERY_DEVICE_DEPLOYMENT /
GROUND_HIT events, plus `optimumDelay`. `FlightData.NaN_DATA` is a shared
immutable all-NaN instance.

---

## 7. Event system

### 7.1 `FlightEvent`

File: `FlightEvent.java`. `implements Comparable<FlightEvent>`. Immutable record
of `{UUID id, Type type, double time, RocketComponent source, Object data}`.
Constructors range from `(type, time)` to
`(type, time, source, data, UUID)`; `validate()` enforces payload types per
event type (e.g. IGNITION/BURNOUT source must be a `MotorMount`, data a
`MotorClusterState`; SIM_WARN data must be a `Warning`; SIM_ABORT data a
`SimulationAbort`).

```java
public Type getType();  public double getTime();
public RocketComponent getSource();  public Object getData();  public UUID getID();
@Override public int compareTo(FlightEvent o);
```

**`Type` enum (complete list, in ordinal order):**

`LAUNCH`, `IGNITION`, `LIFTOFF`, `LAUNCHROD`, `BURNOUT`, `EJECTION_CHARGE`,
`STAGE_SEPARATION`, `APOGEE`, `RECOVERY_DEVICE_DEPLOYMENT`, `GROUND_HIT`,
`SIMULATION_END`, `ALTITUDE`, `TUMBLE`, `SIM_WARN`, `SIM_ABORT`, `EXCEPTION`.

Payload notes: `IGNITION`/`BURNOUT`/`EJECTION_CHARGE` carry the motor mount as
source and a `MotorClusterState` as data; `ALTITUDE` data is a
`Pair<Double,Double>` (old, new altitude); `SIM_WARN` data is a `Warning`;
`SIM_ABORT` data is a `SimulationAbort`. Placing `SIMULATION_END` (or
`SIM_ABORT`) on the queue ends the branch.

### 7.2 `EventQueue` and ordering

File: `EventQueue.java`. `extends PriorityQueue<FlightEvent> implements
Monitorable` — a min-heap that bumps a `ModID` on every mutation
(`add`/`offer`/`poll`/`remove`/`clear`).

Ordering is defined by `FlightEvent.compareTo`, applied in order:

1. **Time** ascending (earliest event first).
2. **Source presence**: events with `source == null` sort first.
3. **Stage order**: larger stage number first (so lower/booster stages are
   processed before upper stages at the same time).
4. **Type ordinal** as the final tiebreaker (the enum order above).

`equals` treats two `SIM_WARN` events as equal iff their `Warning` payloads are
equal; otherwise equality is `compareTo == 0`.

### 7.3 Dispatch summary

Events are produced both by the engine's per-step state inspection (LIFTOFF,
LAUNCHROD, APOGEE, GROUND_HIT, ALTITUDE, TUMBLE) and by event handling itself
(IGNITION→BURNOUT→EJECTION_CHARGE chains, STAGE_SEPARATION, RECOVERY_DEVICE_
DEPLOYMENT). `handleEvents` drains all events whose time ≤ current sim time each
loop iteration; the next event's time also caps the next integration step so no
event is skipped. Each branch has its own queue; on separation the booster's
queue is the parent's clone minus events from detached components.

---

## 8. The other steppers (brief)

- **`AbstractEulerStepper`** (`extends AbstractSimulationStepper`) — shared
  base for descent phases. `initialize` returns the status unchanged. Uses a
  forward-Euler integrator (`eulerIntegrate`: `v += a·dt`,
  `p += v·dt + ½a·dt²`) with `RECOVERY_TIME_STEP = 0.5 s`, shrunk by
  acceleration magnitude and by `maxTimeStep`. Detects sign changes in Z, Ż, Z̈
  within a step to land exactly on ground hit / apogee / descent-rate inflection
  and recomputes the step to that instant. Its `calculateAcceleration` models
  only drag + gravity + Coriolis (no moments; angular velocity stays zero) using
  an abstract `computeCD(status)`. Subclasses implement only `computeCD`:
  - **`BasicLandingStepper`** — `CD` = Σ over deployed recovery devices of
    `count·Cd·area / referenceArea` (parachute/streamer descent).
  - **`BasicTumbleStepper`** — `CD` from projected fin and body-tube planform
    areas with empirical constants (`cDFin = 1.42`, `cDBt = 0.56`, a fin-count
    efficiency table) — models a rocket tumbling without recovery.
- **`GroundStepper`** (`extends AbstractSimulationStepper`) — terminal "sitting
  on the ground" stepper. `calculateAcceleration` is empty; `step` calls
  `landedValues`, optionally inserts a `MIN_TIME_STEP` transition point, then
  advances time and stores resting data. Used after `GROUND_HIT`.
- **`RK6SimulationStepper`** — alternative higher-order Runge-Kutta flight
  stepper selectable via `SimulationStepperMethod.RK6` (used in place of
  `RK4SimulationStepper` as the `flightStepper`; same contract/role).

---

## 9. Notable gaps / caveats for a reimplementation

- The RK4 stepper does **not** do classical embedded error estimation; its
  "time step control" is a set of physical step-size *limits* (§3.2). A Python
  port can mimic this exactly or swap in a real adaptive controller.
- Only start-of-step physics parameters are recorded per RK4 step (documented
  inaccuracy). Output channels therefore lag the true sub-step values slightly.
- Listener hooks (`SimulationListenerHelper.fire*`) are woven through every
  model call and event; they can override or veto results. A minimal port can
  omit them, but the override points are real extensibility seams.
- Several physics collaborators live **outside** this package and are treated as
  black boxes here: `AerodynamicCalculator` (force/CP analysis), `MassCalculator`
  / `RigidBody`, the `WindModel`/`AtmosphericModel`/`GravityModel`,
  `GeodeticComputationStrategy` (Coriolis + world-coordinate mapping), and
  `Quaternion`/`Coordinate` math. Their interfaces must be reproduced for a full
  port but were not in scope of this read.
- The nested coast simulation (`computeCoastTime`) recursively instantiates a
  whole engine — a Python port must guard against listener double-firing the
  same way (it strips non-system listeners).
