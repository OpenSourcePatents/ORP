# Physics Environment Models — Reference for Python Reimplementation

This document maps the three pluggable physics-environment models in OpenRocket
(atmosphere, gravity, wind) and the contract by which the simulation engine consumes
them each tick. It is extracted from `core/src/main/java/info/openrocket/core/models/`
and `core/.../simulation/`.

## Design pattern

All three subsystems use the **strategy pattern**: a small interface defines the query
the simulator needs, and concrete classes provide interchangeable implementations.
The active implementations are held on `SimulationConditions` (one each for atmosphere,
gravity, wind) and looked up by the steppers via getters. A reimplementation should
mirror this: define an ABC/protocol per subsystem, swap implementations freely.

All model interfaces extend `Monitorable` (a `getModID()` "modification id" used only for
cache invalidation in the Java GUI — not physically relevant and can be ignored in Python).

---

## 1. Atmospheric model

### Interface `AtmosphericModel`
Package: `info.openrocket.core.models.atmosphere`

```java
public interface AtmosphericModel extends Monitorable {
    AtmosphericConditions getConditions(double altitude);
}
```

- Single method. `altitude` is **meters above mean sea level** (the stepper passes
  rocket-above-ground + launch-site altitude). There is no time/position variant — the
  atmosphere is purely a function of altitude.

### Value object `AtmosphericConditions`
Holds two primary state values, **temperature (K)** and **pressure (Pa)**, plus a
relative humidity (0..1). All other quantities are *derived* on demand:

Constants:
- `R = 287.053` J/(kg·K) — specific gas constant of dry air
- `GAMMA = 1.4` — specific heat ratio
- `EPSILON = 0.622` — molar-mass ratio water vapor / dry air
- `STANDARD_PRESSURE = 101325.0` Pa, `STANDARD_TEMPERATURE = 293.15` K, `STANDARD_HUMIDITY = 0`
  (Note: this object's "standard" temperature is 293.15 K = 20 °C, distinct from the ISA
  sea-level 288.15 K used by `ExtendedISAModel`.)

Derived getters (these are the formulas a reimplementer must replicate):

- **Gas constant** `getGasConstant()` — returns `R` when humidity is 0; otherwise corrects
  for humidity using saturation vapor pressure (`vaporPressureSaturation() = 611.3 * exp(19.854 - 5423/T)`,
  Clausius–Clapeyron). For dry-air sims this is just `R`.
- **Density** `getDensity() = pressure / (gasConstant * temperature)` (ideal gas law).
- **Speed of sound** `getMachSpeed() = 165.77 + 0.606 * temperature` (T in Kelvin; this is
  the `331.3 + 0.606*T_celsius` expansion folded into Kelvin).
- **Kinematic viscosity** `getKinematicViscosity()`:
  `v = 3.7291e-06 + 4.9944e-08 * temperature` (dynamic, linear Sutherland approx),
  then `return v / getDensity()`.

`equals`/`hashCode` consider only pressure and temperature.

### ISA implementation `ExtendedISAModel`
Extends `InterpolatingAtmosphericModel` (see caching below). Implements the **International
Standard Atmosphere** in geopotential altitude, extended to allow custom launch-site conditions.

Constants:
- `STANDARD_TEMPERATURE = 288.15` K, `STANDARD_PRESSURE = 101325` Pa (ISA sea level)
- `G = 9.80665` m/s² (used in the barometric formula only)
- `ISA_EARTH_RADIUS = 6356766.0` m (for geometric↔geopotential conversion)

ISA layers — `STANDARD_LAYERS` (geopotential meters where each layer begins) and
`STANDARD_TEMPERATURES` (base temperature K at each layer start):

| Layer base (m) | Base temp (K) | Region | Behavior |
|---|---|---|---|
| 0 | 288.15 | Troposphere | lapse −6.5 °C/km to 216.65 K |
| 11000 | 216.65 | Tropopause | isothermal |
| 20000 | 216.65 | Stratosphere 1 | +1.0 °C/km to 228.65 K |
| 32000 | 228.65 | Stratosphere 2 | +2.8 °C/km to 270.65 K |
| 47000 | 270.65 | Stratopause | isothermal |
| 51000 | 270.65 | Mesosphere 1 | −2.8 °C/km to 214.65 K |
| 71000 | 214.65 | Mesosphere 2 | −2.0 °C/km to 186.95 K |
| 84852 | 186.95 | Mesopause | constant above |

Constructors:
- `ExtendedISAModel()` — standard ISA.
- `ExtendedISAModel(double temperature, double pressure)` — custom MSL T/P.
- `ExtendedISAModel(double temperature, double pressure, double relativeHumidity)`
- `ExtendedISAModel(double altitude, double temperature, double pressure, double relativeHumidity)`
  — measurements taken at a given geometric `altitude`; must be below 11 km (first layer).
  It inserts an extra layer, back-calculates a sea-level temperature from the local lapse rate,
  and keeps standard ISA behavior above.

Core computation `protected AtmosphericConditions getExactConditions(double altitude)`:
1. Convert geometric → geopotential: `h_geo = R_e * h / (R_e + h)` with `R_e = ISA_EARTH_RADIUS`.
2. Clamp into `[layer[0], layer[last]]`, find the layer the altitude falls in.
3. **Temperature**: linear interpolation within the layer using the layer lapse rate
   `tempRate = (T_next - T_start) / (alt_next - alt_start)`, `T = T_start + altDiff*tempRate`.
4. **Pressure** via the barometric formula `calculatePressure`:
   - non-isothermal (`|tempRate| > 1e-6`): `P = P_base / (1 + (Δalt)*tempRate/T_base)^(-G/(tempRate*R))`
   - isothermal: `P = P_base / exp(-(Δalt)*G/(R*T_base))`
   Base pressures per layer are precomputed in the constructor by chaining this formula up the layers.
5. Humidity is currently carried unchanged between altitudes (TODO in source; treat as constant).

`geometricToGeopotential(h) = R_e*h/(R_e+h)`, `geopotentialToGeometric(h) = R_e*h/(R_e-h)`.
Max valid launch-site altitude ≈ just under 11 km. Note source TODO: values above 32 km
differ from textbook ISA by ~5%.

### Caching layer `InterpolatingAtmosphericModel` (abstract)
Performance wrapper that `ExtendedISAModel` extends. Strategy:
- `DELTA = 500` m layer spacing.
- On first `getConditions` call, lazily compute an array `levels[]` by calling the subclass
  `getExactConditions(i*DELTA)` from 0 up to `getMaxAltitude()` (thread-safe via a lock).
- `getConditions(altitude)` then:
  - `altitude <= 0` → `levels[0]`; `altitude >= DELTA*maxIndex` → top level.
  - otherwise **linear interpolation** of temperature, pressure, and humidity between the two
    bracketing 500 m levels (`fraction = (altitude - lowerIndex*DELTA)/DELTA`).
- Subclass contract: `protected abstract double getMaxAltitude();` and
  `protected abstract AtmosphericConditions getExactConditions(double altitude);`.

A Python port can either replicate the 500 m precompute+interpolate cache or just call the
exact ISA formula directly (simpler, slightly slower).

---

## 2. Gravity model

### Interface `GravityModel`
Package: `info.openrocket.core.models.gravity`

```java
public interface GravityModel extends Monitorable {
    double getGravity(WorldCoordinate wc);
}
```

- Returns a **scalar magnitude** in m/s² (not a vector). `WorldCoordinate` provides
  `getLatitudeRad()`, `getLongitudeDeg()`, `getAltitude()` (meters). The simulator treats
  this scalar as the downward (−Z, world frame) acceleration.

### `WGSGravityModel` (WGS84 ellipsoid, default)
Caches the last `(WorldCoordinate → g)` result to avoid recomputation. Computation `calcGravity`:

1. **Somigliana / WGS84 normal gravity vs latitude** (sea level):
   ```
   sin2lat = sin(latitudeRad)^2
   g_0 = 9.7803267714 * (1 + 0.00193185138639*sin2lat) / sqrt(1 - 0.00669437999013*sin2lat)
   ```
2. **Altitude correction** (inverse-square, spherical-Earth approximation):
   ```
   g = g_0 * ( REARTH / (REARTH + altitude) )^2
   ```
   where `WorldCoordinate.REARTH = 6371000.0` m. (Source notes the altitude term assumes a
   spherical Earth and ignores atmospheric mass — deliberate small approximations.)

### `ConstantGravityModel` (alternative)
A Java `record`: `record ConstantGravityModel(double gravity)`. `getGravity()` returns the
fixed value regardless of location. Also exposes `getConstantGravity()`.

### `GravityModelType` enum
`WGS("WGS")` and `CONSTANT("Constant")`, with `fromString`/`toStringValue` for persistence.
`SimulationOptions` stores a `GravityModelType` and builds the matching model.

---

## 3. Wind model

### Interface `WindModel`
Package: `info.openrocket.core.models.wind`. Extends `Monitorable, Cloneable, ChangeSource`.

```java
enum AltitudeReference { MSL, AGL }

CoordinateIF getWindVelocity(double time, double altitudeMSL, double altitudeAGL);
CoordinateIF getWindVelocity(double time, double altitude);
WindModel clone();
```

- Returns a wind-velocity **vector** (`Coordinate` = x,y,z in m/s; z is always 0 for wind).
  The model itself chooses whether it keys off MSL or AGL altitude (the 3-arg overload).
- `time` is seconds since simulation start; must be `>= 0`.

### `PinkNoiseWindModel` (single-level, turbulent)
Generates a fluctuating wind speed as **pink (1/f) noise** around an average. Currently
altitude-independent (the 3-arg form ignores AGL and forwards to the 2-arg form).

Parameters / state:
- `average` (m/s) — mean wind speed. Setter keeps **turbulence intensity** constant when
  average changes, and reverses `direction` if a negative average is supplied.
- `direction` (radians; default `PI/2` = wind toward +x / an "East" wind). Wind vector is
  `(speed*sin(direction), speed*cos(direction), 0)`.
- `standardDeviation` (m/s) — clamped to ≥ 0.
- `turbulenceIntensity = standardDeviation / average` (0 if average is 0). `setTurbulenceIntensity(i)`
  sets `standardDeviation = i * average`. There's also a text classifier
  (`getIntensityDescription`: None / Very low / Low / Medium / High / Very high / Extreme).
- `seed` — XORed with `SEED_RANDOMIZATION = 0x7343AA03`; drives a `PinkNoise(ALPHA, POLES, Random)`.

Pink-noise constants:
- `ALPHA = 5.0/3.0` (Kolmogorov-like spectral slope), `POLES = 2` (IIR filter poles),
  `STDDEV = 2.252` (empirical std-dev of the raw generator output, used to normalize),
  `DELTA_T = 0.05` s (sample interval).

`getWindVelocity(time, altitude)` algorithm:
1. Lazily init the `PinkNoise` source and two samples `value1, value2` at `time1 = 0`.
2. If requested `time < time1`, reset and restart (non-monotonic guard).
3. Advance the two-sample window by drawing new pink-noise samples until `time1+DELTA_T >= time`.
4. Linearly interpolate within the window: `a = (time - time1)/DELTA_T`.
5. `speed = average + (value1*(1-a) + value2*a) * standardDeviation / STDDEV`.
6. Return `Coordinate(speed*sin(direction), speed*cos(direction), 0)`.

### `MultiLevelPinkNoiseWindModel` (altitude-layered)
Holds a sorted list of `LevelWindModel` entries, each `= (altitude, PinkNoiseWindModel)`,
plus an `AltitudeReference` (MSL or AGL, default MSL). Each level has its own average / direction /
std-dev / turbulence intensity (delegated to its inner `PinkNoiseWindModel`).

- `addWindLevel(altitude, speed, direction[, standardDeviation])` — inserts sorted by altitude;
  rejects a duplicate altitude.
- `getWindVelocity(time, altitudeMSL, altitudeAGL)` picks MSL or AGL per `altitudeReference`,
  then calls the 2-arg form.
- `getWindVelocity(time, altitude)`:
  - empty list → `Coordinate.ZERO`.
  - exact altitude match → that level's wind.
  - below lowest / above highest → **clamp** (extrapolate with the nearest level's value).
  - between two levels → **linear interpolation** of the two level velocity vectors,
    `fraction = (altitude - lowerAlt)/(upperAlt - lowerAlt)`, via `lowerVel.interpolate(upperVel, fraction)`.
- `getWindDirection(time, altitude) = atan2(vx, vy)` normalized to [0, 2π).
- Supports CSV import (`importLevelsFromCSV`, columns altitude/speed/direction/stddev with units).

### `WindModelType` enum
Selects between the single-level average model and the multi-level model (used by preferences/options).

---

## 4. How the simulation engine consumes the models

### Where the models live
`SimulationConditions` (`core/.../simulation/SimulationConditions.java`) holds one instance of
each, with plain getters/setters:
- `AtmosphericModel getAtmosphericModel()`
- `GravityModel getGravityModel()`
- `WindModel getWindModel()`

`SimulationStatus` carries the live rocket state, including `getRocketPosition()` (launch-frame,
z = AGL altitude) and `getRocketWorldPosition()` (a `WorldCoordinate` with lat/lon/altitude),
plus `getSimulationTime()`. The launch-site altitude comes from
`status.getSimulationConditions().getLaunchSite().getAltitude()`.

### Per-tick query points — `AbstractSimulationStepper`
All three steppers (`RK4SimulationStepper`, `RK6SimulationStepper`, the Euler steppers) share the
base `AbstractSimulationStepper`, which wraps each model query in a pre/post simulation-listener
hook (listeners may override the value):

- **Atmosphere** — `modelAtmosphericConditions(status)`:
  ```java
  double altitude = status.getRocketPosition().getZ()
                  + status.getSimulationConditions().getLaunchSite().getAltitude();   // MSL
  conditions = status.getSimulationConditions().getAtmosphericModel().getConditions(altitude);
  ```
  Stored into `FlightConditions` via `flightConditions.setAtmosphericConditions(...)` inside
  `calculateFlightConditions`. From there the aerodynamics read density / temperature / pressure /
  speed-of-sound / kinematic-viscosity (e.g. Reynolds number, Mach number, and dynamic pressure
  `dynP = 0.5 * density * v²` in `RK4SimulationStepper`).

- **Wind** — `modelWindVelocity(status)`:
  ```java
  double altitudeAGL = status.getRocketPosition().getZ();
  double altitudeMSL = altitudeAGL + launchSite.getAltitude();
  wind = windModel.getWindVelocity(status.getSimulationTime(), altitudeMSL, altitudeAGL);
  ```
  In `calculateFlightConditions`, wind is **added to the rocket velocity** to form the air-relative
  velocity, which is then rotated into the body frame to derive angle of attack, lateral direction
  (`theta`), and total airspeed used by all aerodynamic force/coefficient calculations.

- **Gravity** — `modelGravity(status)`:
  ```java
  gravity = status.getSimulationConditions().getGravityModel().getGravity(status.getRocketWorldPosition());
  ```
  Returns a scalar. In `RK4SimulationStepper.calculateAcceleration`, after aerodynamic + thrust
  acceleration is assembled and rotated into the world frame, gravity is applied as a pure −Z term:
  ```java
  store.gravity = modelGravity(status);
  linearAcceleration.sub(0, 0, store.gravity);   // world-frame downward
  linearAcceleration.add(store.coriolisAcceleration);
  ```
  (Coriolis is handled separately by the geodetic-computation strategy, not by the gravity model.)
  The scalar is also reused for reporting, e.g. thrust-to-weight `= thrustForce / (mass * gravity)`.

### Consumption contract summary (for the Python port)
Each integration sub-step, given current `time`, AGL/MSL altitude, and world position:
1. `atmosphere.get_conditions(altitude_msl)` → object exposing `density`, `temperature`,
   `pressure`, `speed_of_sound (mach_speed)`, `kinematic_viscosity`.
2. `wind.get_wind_velocity(time, altitude_msl, altitude_agl)` → 3-vector (z=0); add to rocket
   velocity to get air-relative velocity before computing aero forces.
3. `gravity.get_gravity(world_coordinate)` → scalar m/s²; subtract along world −Z.
Compute aerodynamic force from `0.5 * density * v² * area * Cd(...)` (drag), gravitational force
from `mass * gravity` downward, integrate.

### Key file references (absolute paths)
- `C:\Users\cjdow\Projects\OpenReentryApp\core\src\main\java\info\openrocket\core\models\atmosphere\AtmosphericModel.java`
- `...\models\atmosphere\AtmosphericConditions.java`
- `...\models\atmosphere\ExtendedISAModel.java`
- `...\models\atmosphere\InterpolatingAtmosphericModel.java`
- `...\models\gravity\GravityModel.java`, `WGSGravityModel.java`, `ConstantGravityModel.java`, `GravityModelType.java`
- `...\models\wind\WindModel.java`, `PinkNoiseWindModel.java`, `MultiLevelPinkNoiseWindModel.java`, `WindModelType.java`
- `...\simulation\SimulationConditions.java` (model storage)
- `...\simulation\AbstractSimulationStepper.java` (modelAtmosphericConditions / modelWindVelocity / modelGravity)
- `...\simulation\RK4SimulationStepper.java` (calculateAcceleration: gravity applied; dynamic pressure)
- `...\util\WorldCoordinate.java` (`REARTH = 6371000.0`, latitude/altitude accessors)
