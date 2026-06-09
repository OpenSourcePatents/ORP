# OpenRocket Component / Vehicle Model — Architectural Reference

This document maps the OpenRocket vehicle model (the rocket-design "component tree") so it
can be reimplemented in Python. It covers the `RocketComponent` base class, the component
class hierarchy, tree composition, `FlightConfiguration` (the simulation snapshot), and the
visitor traversal subsystem.

Source packages (Java):
- `info.openrocket.core.rocketcomponent`
- `info.openrocket.core.rocketcomponent.position`
- `info.openrocket.core.rocketvisitors`

Design patterns in play:
- **Composite** — `RocketComponent` is a recursive parent/child tree; `Rocket` is the root.
- **Observer** — `ComponentChangeListener` / `ComponentChangeEvent` fired through the root `Rocket`.
- **Visitor** — `RocketComponentVisitor<R>` with `accept()` double-dispatch and recursive visitor base classes.
- **Memento / snapshot** — `FlightConfiguration` is a derived, clonable view of the rocket used by the sim engine.

---

## 1. `RocketComponent` — the base class

`public abstract class RocketComponent implements ChangeSource, Cloneable, Iterable<RocketComponent>`

Every physical and structural part of the rocket extends this abstract class. It owns:
the parent/child links, an identity (UUID), geometry (length + axial/radial position),
mass/CG/CD overrides, change notification, instancing, and cloning.

### 1.1 Core fields (state a Python class must hold)
- `protected RocketComponent parent` — parent, or `null` for the root.
- `protected ArrayList<RocketComponent> children` — ordered child list.
- `protected double length` — characteristic length (used to position the next `AFTER` sibling).
- `protected AxialMethod axialMethod` (default `AFTER`) and `protected double axialOffset` — how/where it sits relative to parent.
- `protected CoordinateIF position` — computed position relative to parent (X is along the rocket axis). Root is constrained to (0,0,0).
- `private UUID id` — unique identity (see §1.3).
- Override flags/values: `overrideMass`/`massOverridden`/`overrideSubcomponentsMass`, `overrideCGX`/`cgOverridden`/`overrideSubcomponentsCG`, `overrideCD`/`cdOverridden`/`overrideSubcomponentsCD`, plus `massOverriddenBy`/`CGOverriddenBy`/`CDOverriddenBy` pointers to the ancestor doing the overriding.
- `name`, `comment`, `color`, `lineStyle`, `appearance`, `presetComponent`, `isVisible`.
- Caches: `cachedComponentLocations`, `cachedComponentAngles` (invalidated on any change).

### 1.2 Tree-management methods (signatures, verbatim)
```java
public final void addChild(RocketComponent component)
public final void addChild(RocketComponent component, boolean trackStage)
public void addChild(RocketComponent component, int index)
public void addChild(RocketComponent component, int index, boolean trackStage)

public final void removeChild(int n)
public final void removeChild(int n, boolean trackStage)
public final boolean removeChild(RocketComponent component)
public final boolean removeChild(RocketComponent component, boolean trackStage)
public final void moveChild(RocketComponent component, int index)

public final int getChildCount()
public final RocketComponent getChild(int n)
public final List<RocketComponent> getChildren()            // clone of the child list
public final List<RocketComponent> getAllChildren()         // depth-first, all descendants
public final int getChildPosition(RocketComponent child)
public final boolean containsChild(RocketComponent component)

public final RocketComponent getParent()
public final List<RocketComponent> getParents()             // all ancestors up to root
public final RocketComponent getRoot()                      // walk parent links to top
public final Rocket getRocket()                             // getRoot() cast to Rocket (throws if not)
public final AxialStage getStage()                          // nearest AxialStage ancestor
public final ComponentAssembly getAssembly()                // nearest ComponentAssembly ancestor

public final Iterator<RocketComponent> iterator()           // == iterator(true)
public final Iterator<RocketComponent> iterator(boolean returnSelf)
```
Key behaviors a reimplementation must preserve:
- `addChild` validates: component not already parented, no cycles (`getRoot().equals(component)` guard),
  and `isCompatible(component)` must pass; it sets `component.parent = this`, propagates the
  `*OverriddenBy` pointers down, and — if the child is an `AxialStage` and `trackStage` is true —
  calls `getRocket().trackStage(...)`. Finally fires an add/remove event.
- `removeChild` reverses this (clears parent, untracks stages, fires event, `updateBounds()`).
- `getChildren()` returns a **clone** — callers may not mutate the tree through it.
- The iterator is a depth-first traversal over descendants (optionally including self) and is
  **fail-fast**: it captures the root's `treeModID` and throws `IllegalStateException` if the rocket
  is modified mid-iteration.

### 1.3 Identity and change notification (Observer)
```java
public final UUID getID()
public void setID(UUID newID)
@Override public boolean equals(Object obj)   // equal iff same class AND same id
@Override public int hashCode()               // id.hashCode()
```
Each component gets a random `UUID` at construction (`newID()`); `copy()` re-IDs the whole copied
subtree, while `copyWithOriginalID()` preserves IDs (used by undo/redo).

Change events bubble to the **root `Rocket`**, which holds the single listener list for the whole tree:
```java
public void addComponentChangeListener(ComponentChangeListener l)   // delegates to getRocket()
public void removeComponentChangeListener(ComponentChangeListener l)
protected void fireComponentChangeEvent(ComponentChangeEvent e)     // delegates to getRoot()
public void fireComponentChangeEvent(int type)
protected void componentChanged(ComponentChangeEvent e)             // hook; clears caches + update()
```
- `ComponentChangeListener` is a one-method interface: `void componentChanged(ComponentChangeEvent e)`.
- `ComponentChangeEvent extends EventObject` carries a bit-field `type`. Constants (bit flags, combinable):
  `NONFUNCTIONAL_CHANGE`, `MASS_CHANGE`, `AERODYNAMIC_CHANGE`, `AEROMASS_CHANGE`/`BOTH_CHANGE`,
  `TREE_CHANGE`, `TREE_CHANGE_CHILDREN`, `UNDO_CHANGE`, `MOTOR_CHANGE`, `EVENT_CHANGE`,
  `TEXTURE_CHANGE`, `GRAPHIC_CHANGE`. (Backed by the nested `enum TYPE`.)
- If `parent == null` (detached/under-construction) or `bypassComponentChangeEvent` is set, events are dropped.
- The `Rocket` can `freeze()`/`thaw()` to coalesce a burst of events into one combined event.

### 1.4 Geometry / physical-property methods
Abstract (each concrete subclass must implement):
```java
public abstract String getComponentName();
public abstract double getComponentMass();
public abstract CoordinateIF getComponentCG();
public abstract double getLongitudinalUnitInertia();
public abstract double getRotationalUnitInertia();
public abstract boolean allowsChildren();
public abstract boolean isCompatible(Class<? extends RocketComponent> type);
public abstract Collection<CoordinateIF> getComponentBounds();
public abstract boolean isAerodynamic();
public abstract boolean isMassive();
```
Position / length:
```java
public double getLength();
public final AxialMethod getAxialMethod();
public void setAxialMethod(AxialMethod newAxialMethod);
public double getAxialOffset();
public double getAxialOffset(AxialMethod asMethod);   // side-effect-free conversion
public void setAxialOffset(double newOffset);
public CoordinateIF getPosition();
public double getRadiusOffset();
public RadiusMethod getRadiusMethod();   // default COAXIAL
public double getAngleOffset();
```
Mass / CG / CD (overrides resolved against `getComponentMass()` etc.):
```java
public final double getMass();             // override mass if set, else getComponentMass()
public final double getSectionMass();      // this + all descendants
public final CoordinateIF getCG();
public final double getLongitudinalInertia();
public final double getRotationalInertia();
public final double getOverrideMass();   public final void setOverrideMass(double m);
public final boolean isMassOverridden();  public final void setMassOverridden(boolean o);
// analogous getters/setters for CG (overrideCGX) and CD, plus
// setSubcomponentsOverriddenMass/CG/CD(boolean) to push the override down the subtree.
public Collection<CoordinateIF> getComponentBounds();   // bounding hull of *this* node only
```
Instancing (multiple fins / tubes / clustered motors / pods):
```java
public int getInstanceCount();                  // default 1; overridden by Instanceable components
public void setInstanceCount(int count);
public CoordinateIF[] getInstanceOffsets();     // per-instance offset from this component's ref point
public CoordinateIF[] getInstanceLocations();   // parent-relative instance locations
public double[]       getInstanceAngles();
public CoordinateIF[] getComponentLocations();  // ABSOLUTE locations, folds in ALL parent instancing
public CoordinateIF[] getComponentAngles();
```
Important nuance: `getComponentLocations()` length = product of this component's instance count
and **all ancestor instance counts** (e.g. a 2-instance rail button inside a 3-instance pod set →
6 absolute locations), whereas `getInstanceCount()` is only this component's own replication.
Locations/angles are cached and cleared by `clearCoordinateCaches()` on any change.

### 1.5 Visitor hook & cloning
```java
public <R> R accept(RocketComponentVisitor<R> visitor)   // visitor.visit(this); return visitor.getResult();
public final RocketComponent copy();                     // deep copy, new IDs
protected RocketComponent copyWithOriginalID();          // deep copy, same IDs (undo/redo)
```

---

## 2. Component class hierarchy

```
RocketComponent (abstract)
├── ExternalComponent (abstract)         outer/aerodynamic surface; has Finish + density material
│   ├── BodyComponent (abstract)
│   │   └── SymmetricComponent (abstract, implements RadialParent, BoxBounded)
│   │       ├── BodyTube           (MotorMount, Coaxial, InsideColorComponent)
│   │       └── Transition         (cone/shoulder; InsideColorComponent)
│   │           └── NoseCone       (specialization of Transition)
│   ├── FinSet (abstract)                fin arrays; instanced (fin count)
│   │   ├── TrapezoidFinSet
│   │   ├── EllipticalFinSet
│   │   └── FreeformFinSet
│   ├── Tube (abstract, Coaxial)
│   │   ├── LaunchLug              (AnglePositionable, LineInstanceable, BoxBounded)
│   │   └── TubeFinSet             (RingInstanceable)
│   └── RailButton
│
├── InternalComponent (abstract, AxialPositionable)   lives inside a parent body
│   ├── StructuralComponent (abstract)
│   │   └── RingComponent (abstract, Coaxial, BoxBounded)
│   │       ├── ThicknessRingComponent (abstract)
│   │       │   ├── InnerTube          (MotorMount; Clusterable)
│   │       │   ├── EngineBlock
│   │       │   └── TubeCoupler        (RadialParent)
│   │       ├── RadiusRingComponent (abstract)
│   │       │   ├── CenteringRing
│   │       │   └── Bulkhead
│   │       └── Sleeve
│   └── MassObject (abstract)                          point/line mass-like internals
│       ├── MassComponent          (generic ballast/payload mass)
│       ├── ShockCord
│       └── RecoveryDevice (abstract, FlightConfigurableComponent)
│           ├── Parachute
│           └── Streamer
│
└── ComponentAssembly (abstract, AxialPositionable, BoxBounded)  groups children; no mass/bounds of its own
    ├── Rocket                      THE ROOT; owns flight configurations + stage map
    ├── AxialStage                  (FlightConfigurableComponent) an in-line (centerline) stage
    │   └── ParallelStage           (RingInstanceable) booster cluster mounted off-axis
    └── PodSet                      (RingInstanceable) off-axis pod assembly
```

### Roles of the major abstract classes
- **`ExternalComponent`** — components on the outside contributing to aerodynamics; adds a surface
  `Finish` and a bulk-density material. `isAerodynamic()` true.
- **`BodyComponent` / `SymmetricComponent`** — axially-symmetric bodies of revolution; `SymmetricComponent`
  implements `RadialParent` (provides radius vs. x) and `BoxBounded` (returns a bounding box).
  `BodyTube`, `Transition`, and `NoseCone` are the concrete body shapes.
- **`FinSet`** — a set of identical fins around the body; multi-instance (fin count). Leaves:
  `TrapezoidFinSet`, `EllipticalFinSet`, `FreeformFinSet`.
- **`InternalComponent`** — components mounted *inside* a parent (positioned via `AxialPositionable`);
  not aerodynamic.
- **`StructuralComponent` / `RingComponent`** — internal structure (tubes, rings, bulkheads, couplers).
  `InnerTube` doubles as a `MotorMount` and is `Clusterable` (motor clusters).
- **`MassObject`** — internal mass-bearing objects with no aerodynamic effect. `RecoveryDevice`
  (`Parachute`, `Streamer`) extends it and is `FlightConfigurableComponent` (per-configuration deployment).
- **`ComponentAssembly`** — pure container: zero mass/CG/bounds of its own, `allowsChildren()==true`.
  Concrete assemblies are `Rocket` (root), `AxialStage`, `ParallelStage`, and `PodSet`.

### Concrete leaf components (buildable parts)
`BodyTube`, `NoseCone`, `Transition`, `TrapezoidFinSet`, `EllipticalFinSet`, `FreeformFinSet`,
`TubeFinSet`, `LaunchLug`, `RailButton`, `InnerTube`, `EngineBlock`, `TubeCoupler`, `CenteringRing`,
`Bulkhead`, `Sleeve`, `MassComponent`, `ShockCord`, `Parachute`, `Streamer`, plus the assemblies
`AxialStage`, `ParallelStage`, `PodSet`, and the root `Rocket`.

### Notable cross-cutting interfaces
- `MotorMount` — a component that can hold motor configurations (implemented by `BodyTube`, `InnerTube`).
- `Instanceable` (+ `RingInstanceable`, `LineInstanceable`, `Clusterable`) — components that replicate
  into multiple instances; supply `getInstanceCount()/getInstanceOffsets()/getPatternName()`.
- `Coaxial`, `RadialParent`, `AxialPositionable`, `AnglePositionable`, `RadiusPositionable`,
  `BoxBounded`, `FlightConfigurableComponent`, `InsideColorComponent`.

---

## 3. How components compose into a tree

- The tree is a **composite**: every node keeps an ordered `children` list and a back-pointer `parent`.
  The single root is always a `Rocket` (`getRocket()` enforces this).
- **Type compatibility** governs what may nest where: `addChild` calls `isCompatible(Class)` and
  `allowsChildren()`. e.g. a `Rocket`'s direct children are `AxialStage`s; a `BodyTube` accepts
  internal components, fins, lugs, etc.; `MassObject`s and leaves accept no children.
- **Axial order matters**: sibling order in `children` plus the `AxialMethod.AFTER` default means each
  component is laid out behind the previous active sibling (`setAfter()` chains `position.x`). Other
  `AxialMethod`s (ABSOLUTE/TOP/MIDDLE/BOTTOM) place relative to the parent.
- **Stages & assemblies**: a `Rocket` contains one or more `AxialStage`s (centerline). Off-axis
  structures are `ParallelStage` (boosters) and `PodSet` (pods), which are `ComponentAssembly`s
  positioned both axially and radially/angularly. `Rocket` maintains a `stageMap`
  (`trackStage`/`forgetStage`) and assigns stage numbers.
- **Instancing** lets one component represent many physical copies: fin sets (N fins), `LineInstanceable`
  rail buttons/lugs, `Clusterable` inner tubes (motor clusters), and `RingInstanceable` parallel
  stages / pod sets. Absolute placement multiplies through every instancing ancestor (see §1.4).

---

## 4. `FlightConfiguration` — the simulation snapshot

`public class FlightConfiguration implements FlightConfigurableParameter<FlightConfiguration>, Monitorable`

A `FlightConfiguration` is a **derived, configuration-specific view** of a `Rocket` that the
simulation engine consumes. It does *not* copy components; it references the live `Rocket` and
stores per-configuration choices (which stages are active, which motors are loaded) plus cached
geometry.

### 4.1 What it stores
- `protected final Rocket rocket` — the design it describes (shared, not copied).
- `protected final FlightConfigurationId fcid` — the configuration's identity (see §4.4).
- `Map<Integer, StageFlags> stages` — per stage-number active/inactive flags (`StageFlags` holds
  `stageNumber`, `stageId` UUID, `active`). Rebuilt from the rocket's stage list by `updateStages()`.
- `Map<MotorConfigurationId, MotorConfiguration> motors` and `Collection<MotorConfiguration> activeMotors`
  — the motors loaded per mount for *this* fcid, derived from each `MotorMount.getMotorConfig(fcid)`.
- `InstanceMap activeInstances` / `extraRenderInstances` — fully-resolved instance contexts (component +
  instance index + absolute `Transformation`) for active components, computed by `updateActiveInstances()`.
- Cached `BoundingBox`/length (aerodynamic and total), reference length, and a `ModID` for invalidation.
- `configurationName` (defaults to a motor-derived label `"[{motors}]"`).

### 4.2 How it is derived from the Rocket
- Constructed as `new FlightConfiguration(rocket, fcid)`; the constructor immediately calls
  `updateStages()`, `updateMotors()`, `updateActiveInstances()`.
- `updateStages()` walks `rocket.getStageList()`, preserving prior active flags by `stageId`.
- `updateMotors()` walks active components, pulling each acting `MotorMount`'s `MotorConfiguration`
  for this `fcid`.
- `updateActiveInstances()` recursively transforms every component instance into absolute space,
  emitting `InstanceContext`s into the `InstanceMap`. Inactive `ParallelStage`s with no children still
  go into `extraRenderInstances` so they render.
- The `Rocket` owns the set of configurations: `createFlightConfiguration(fcid)`,
  `getFlightConfiguration(fcid)`, `removeFlightConfiguration(fcid)`, `getIds()`, `getConfigurationCount()`,
  plus a currently-`selectedConfiguration` (`getSelectedConfiguration()` / `setSelectedConfiguration(fcid)`).

### 4.3 Key methods (signatures)
```java
public boolean isStageActive(int stageNumber);
public List<AxialStage> getAllStages();
public List<AxialStage> getActiveStages();
public int getActiveStageCount();
public int getStageCount();
public AxialStage getBottomStage();
public boolean isComponentActive(RocketComponent c);   // c is in an active stage
public Collection<RocketComponent> getAllActiveComponents();
public Collection<RocketComponent> getActiveComponents();   // @Deprecated (ignores instancing)
public InstanceMap getActiveInstances();
public Collection<MotorConfiguration> getActiveMotors();
public boolean hasMotors();   public boolean hasRecoveryDevice();
public BoundingBox getBoundingBoxAerodynamic();  public double getLengthAerodynamic();
public double getReferenceLength();

// stage activation
public void setAllStages();   public void clearAllStages();
public void setOnlyStage(int stageNumber);
public void _setStageActive(int stageNumber, boolean active, boolean activateSubStages);
public void toggleStage(int stageNumber);
public void activateStagesThrough(AxialStage stage);

// identity / lifecycle
public FlightConfigurationId getFlightConfigurationID();  public FlightConfigurationId getId();
@Override public FlightConfiguration clone();             // shallow clone, same fcid, same rocket
public FlightConfiguration clone(Rocket rocket);
@Override public FlightConfiguration copy(FlightConfigurationId newId);   // deep-ish; copies motors under newId
@Override public void update();   @Override public ModID getModID();
```
`isStageActive` returns false for stages with no children. `clone()` is a shallow snapshot (shares
the rocket, copies stage activeness and cached bounds, keeps the same fcid); `copy(newId)` produces a
new configuration under a new id and clones motor instances onto it.

### 4.4 Relationship to `FlightConfigurationId`
`public final class FlightConfigurationId implements Comparable<FlightConfigurationId>` — an immutable
`UUID` wrapper (replaces a raw `String` key) used to key configurations, per-mount motor configs, and
recovery/deployment settings. Sentinels: `DEFAULT_VALUE_FCID` (the always-present default config) and
`ERROR_FCID`. Methods: `isValid()`, `hasError()`, `isDefaultId()`, `toShortKey()`, `equals`/`hashCode`
by `key`. A `FlightConfiguration` and its `fcid` are 1:1; `FlightConfiguration.equals` compares fcids.

### 4.5 How the sim engine consumes it
The simulator runs against a selected `FlightConfiguration`: it reads `getActiveStages()` /
`getAllActiveComponents()` for the participating mass & aero components, `getActiveMotors()` for thrust,
`getBoundingBoxAerodynamic()` / `getReferenceLength()` for reference geometry, and `getActiveInstances()`
to know the absolute placement (transform) of every instance. Stage separation during flight corresponds
to flipping `StageFlags.active`. Because the configuration references the live rocket, recomputation is
driven by `ModID` invalidation rather than data copies.

---

## 5. Visitor subsystem (`rocketvisitors`)

### 5.1 The visitor interface (double dispatch)
```java
public interface RocketComponentVisitor<R> {
    void visit(RocketComponent visitable);   // 2nd leg of double-dispatch (called from accept())
    R getResult();                           // final accumulated result
}
```
On the component side:
```java
public <R> R accept(RocketComponentVisitor<R> visitor) {
    visitor.visit(this);
    return visitor.getResult();
}
```
So `component.accept(visitor)` invokes `visitor.visit(component)` and returns the visitor's result.

### 5.2 Recursive traversal base classes
**Depth-first** (most common):
```java
public abstract class DepthFirstRecursiveVisitor<R> implements RocketComponentVisitor<R> {
    @Override public final void visit(RocketComponent visitable) {
        this.doAction(visitable);
        for (RocketComponent child : visitable.getChildren())
            this.visit(child);                 // recurse: node then each subtree
    }
    protected abstract void doAction(RocketComponent visitable);
}
```
Order: act on the node, then recurse into each child's full subtree (pre-order DFS). Subclasses only
implement `doAction`.

**Breadth-ish** variant `BredthFirstRecusiveVisitor<R>` (note the source spelling): visits the node,
then runs `doAction` on each direct child, then recurses — a level-leaning traversal.

### 5.3 Example concrete visitors
- **`ListComponents<T extends RocketComponent>`** — a `DepthFirstRecursiveVisitor<List<T>>` that
  collects every component assignable to a given class:
  ```java
  public ListComponents(Class<T> componentClazz)
  @Override public List<T> getResult()                         // the accumulated list
  @Override protected void doAction(RocketComponent visitable) // add if componentClazz.isAssignableFrom(...)
  ```
- **`ListMotorMounts`** — extends `ListComponents<RocketComponent>`; overrides `doAction` to collect
  only components that are an acting `MotorMount` (`instanceof MotorMount && isMotorMount()`).

These provide the template for a Python reimplementation: define a visitor with an accumulator and a
`doAction` callback, and reuse a single depth-first recursion that mirrors `getChildren()` order.

---

## Reimplementation checklist (Python)
1. A `RocketComponent` base with: `parent`, ordered `children`, `id` (uuid4), `length`,
   `axial_method`/`axial_offset`, `position`, mass/CG/CD overrides, and the abstract hooks
   (`component_name`, `component_mass`, `component_cg`, inertias, `allows_children`, `is_compatible`,
   `component_bounds`, `is_aerodynamic`, `is_massive`).
2. Tree ops with cycle/compatibility checks and stage tracking on add/remove; clone-on-read `get_children`.
3. A root `Rocket` holding the listener list, the stage map, and the set of `FlightConfiguration`s
   keyed by `FlightConfigurationId`; events bubble to the root and may be frozen/coalesced.
4. `AxialMethod`/`RadiusMethod` enums implementing the `get_as_position`/`get_as_offset` conversions
   exactly as in §1.4 (ABSOLUTE/AFTER/TOP/MIDDLE/BOTTOM; COAXIAL/FREE/RELATIVE/SURFACE).
5. Instancing (`get_instance_count`/`get_instance_offsets`) and absolute-location resolution that
   multiplies through ancestor instancing.
6. `FlightConfiguration` as a derived view (stage flags + per-mount motors + instance map), not a copy.
7. A visitor protocol with depth-first recursion and `ListComponents`-style collectors.
