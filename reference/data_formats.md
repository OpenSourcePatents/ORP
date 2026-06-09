# OpenRocket Data Formats — Reference for a Python Reimplementation

This document maps the file-I/O architecture of OpenRocket (Java) so that a Python
reimplementer knows exactly what to build. It covers the `.ork` design format, the
`simplesax` parsing framework, the component-saver pattern, motor/thrust-curve loaders
(`.eng` / `.rse`), and the component preset / database system (`.orc`).

All Java references are to packages under
`core/src/main/java/info/openrocket/core/`.

---

## 1. The `.ork` File Format

### 1.1 Container: a ZIP archive

A `.ork` file is **not** a bare XML file — it is a **ZIP archive**. The archive is
produced by `file/GeneralRocketSaver.java` (`saveAllPartsZipFile`), with these entries:

| ZIP entry | Contents |
|-----------|----------|
| `rocket.ork`             | The main XML document (described below). **Always present.** |
| `preview.png`            | 2D side-view preview image (optional, file format v1.11+). |
| `<decal-name>`           | Zero or more decal/texture image files referenced by component appearances. |
| `thrustcurves/<digest>.rse` | Zero or more embedded RockSim-engine thrust-curve files, one per unique `ThrustCurveMotor`, keyed by the motor **digest** (v1.11+). Written via `RockSimMotorWriter`. This makes a design self-contained when custom motors are used. |

ZIP details: compression level 9 (`zos.setLevel(9)`); `rocket.ork` is written first.
Unique motors are collected by walking every `MotorMount` over every
`FlightConfigurationId` and de-duplicating by digest (`collectUniqueMotors`).

`GeneralRocketSaver` also dispatches by `StorageOptions.FileType`: only `OPENROCKET`
produces the ZIP. `ROCKSIM` / `RASAERO` write a single bare XML stream instead.

> Note: `OpenRocketSaver`/`OpenRocketLoader` themselves operate on the **inner XML
> stream** (`rocket.ork`). The ZIP wrapping/unwrapping lives in `GeneralRocketSaver`
> and the loader's `DocumentLoadingContext` / attachment factory. A Python reader must
> therefore: open the ZIP → read `rocket.ork` → SAX-parse it; and resolve motors/decals
> from sibling ZIP entries on demand.

### 1.2 XML structure of `rocket.ork`

The root element is `<openrocket>` with two attributes:

- `version` — the **file-format version** (e.g. `"1.11"`). Drives forward/backward
  compatibility. See `fileformat.txt` for the full version history (1.0 → 1.11).
- `creator` — free-text software/version string (e.g. `"OpenRocket 24.12"`); optional,
  informational only.

Versions are integer-encoded internally as `major * 100 + minor`
(`FILE_VERSION_DIVISOR = 100`); `"1.11"` ⇒ `111`. The current writer always emits
version `1.11` (`calculateNecessaryFileVersion` returns `FILE_VERSION_DIVISOR + 11`).

Top-level skeleton (from `OpenRocketSaver.save`):

```xml
<?xml version='1.0' encoding='utf-8'?>
<openrocket version="1.11" creator="OpenRocket 24.12">
  <rocket>
    <name>...</name>
    <id>...</id>
    ... rocket-level params, motorconfiguration/flightconfiguration ...
    <subcomponents>
      <stage> ... <subcomponents> ... </subcomponents> </stage>
      ...
    </subcomponents>
  </rocket>

  <datatypes> ... </datatypes>          <!-- optional: custom-expression datatypes -->

  <simulations>
    <simulation status="..."> ... </simulation>
    ...
  </simulations>

  <photostudio> ... </photostudio>      <!-- PhotoStudio render settings -->
  <docprefs> ... </docprefs>            <!-- per-document preferences + materials -->
</openrocket>
```

#### The `<rocket>` component tree

The rocket is a recursive tree. Each component emits:

1. An **opening tag** named after the component type (`<nosecone>`, `<bodytube>`,
   `<trapezoidfinset>`, `<stage>`, `<parachute>`, `<railbutton>`, etc.).
2. **Parameter elements** (`<name>`, `<id>`, `<length>`, `<radius>`, `<thickness>`,
   `<material>`, `<axialoffset>`, overrides, appearance, etc.).
3. An optional `<subcomponents>` element wrapping child components (recursive).
4. The matching **closing tag**.

`OpenRocketSaver.saveComponent` drives the recursion: it asks the component's Saver for
a `List<String>` of XML lines (`getElements`), writes line 0 (open tag), the middle
lines (params), recurses into children inside `<subcomponents>`, then writes the last
line (close tag). Indentation is two spaces per level (`INDENT = "  "`).

#### `<simulations>` / `<simulation>`

Each `<simulation status="...">` contains `<name>`, `<simulator>`, `<calculator>`, a
`<conditions>` block (launch rod, wind models, atmosphere, gravity, time step, drag/
stability lookup CSV tables), simulation `<extension>`s, and optional `<flightdata>`
with `<warning>` elements, `<event>`s, and `<datapoint>` rows inside one or more
`<databranch>` elements. See `OpenRocketSaver.saveSimulation` /
`saveFlightDataBranch` for the exact attributes.

### 1.3 Serialization (`OpenRocketSaver`)

`file/openrocket/OpenRocketSaver.java` (extends `file/RocketSaver`).

- `save(OutputStream, OpenRocketDocument, StorageOptions, WarningSet, ErrorSet)` — writes
  the XML header + `<openrocket>` wrapper, then recursively `saveComponent(rocket)`,
  custom datatypes, simulations, photo settings, doc prefs.
- **Reflection-based saver lookup**: `findGetElementsMethod(component)` walks the
  component's class hierarchy, looking for a class named
  `info.openrocket.core.file.openrocket.savers.<SimpleClassName>Saver` exposing a static
  `getElements(RocketComponent)`. (See §3.)
- Helpers: `writeln`, `writeElement(name, content)`, `writeEntry(tag, key, value, …)`
  for typed key/value entries, `enumToXMLName(enum)` ⇒ lowercased, underscores stripped.
- All textual values pass through `TextUtil.escapeXML`.

### 1.4 Parsing (`OpenRocketLoader`)

`file/openrocket/importt/OpenRocketLoader.java` (extends `AbstractRocketLoader`).

- `loadFromStream(DocumentLoadingContext, InputStream, fileName)` wraps the stream in a
  SAX `InputSource` and calls `SimpleSAX.readXML(source, new OpenRocketHandler(context),
  warnings)`. Malformed XML ⇒ `RocketLoadException`.
- After parsing it does post-processing: applies preloaded stage activeness, syncs
  simulation mod-IDs, decides default storage options, and calls each simulation
  extension's `documentLoaded(...)`.

**Handler chain** (the object tree is built top-down via `simplesax`, §2):

- `OpenRocketHandler` — accepts exactly one `<openrocket>`, validates `version` against
  `DocumentConfig.SUPPORTED_VERSIONS`, parses the version into an int, delegates to →
- `OpenRocketContentHandler` — dispatches `<rocket>` → `ComponentParameterHandler`,
  `<datatypes>` → `DatatypeHandler`, `<simulations>` → `SimulationsHandler`,
  `<photostudio>`, `<docprefs>`.
- `ComponentParameterHandler` — populates one component. Container sub-elements
  (`<subcomponents>`, `<appearance>`, `<motormount>`, `<finpoints>`,
  `<motorconfiguration>`, `<deploymentconfiguration>`, …) delegate to dedicated
  handlers; everything else falls through to `closeElement`, which looks up a **`Setter`**
  by the key `"<ComponentSimpleClassName>:<elementName>"` in `DocumentConfig.setters`
  and applies it (walking up the superclass chain). Unknown keys ⇒ a warning.
  `<subcomponents>` delegates to `ComponentHandler`, which constructs the correct child
  `RocketComponent` and recurses with a new `ComponentParameterHandler`.

The `Setter` SPI (`importt/Setter.java`):

```java
interface Setter {
    void set(RocketComponent component, String value,
             HashMap<String, String> attributes, WarningSet warnings);
}
```

Concrete setters (`DoubleSetter`, `IntSetter`, `BooleanSetter`, `StringSetter`,
`EnumSetter`, `MaterialSetter`, `AxialPositionSetter`, …) are registered per
`Class:element` key in `DocumentConfig`. This is the read-side mirror of the
write-side per-type saver dispatch.

---

## 2. The `simplesax` Parsing Framework (the reusable core pattern)

Package `file/simplesax/`. A thin layer over the standard SAX `XMLReader`. **Key
simplifying constraint** (from `SimpleSAX` Javadoc): an element may contain *either*
non-whitespace text *or* child elements, **never both**. This holds for the OpenRocket,
RockSim design, and RockSim engine formats.

### 2.1 The `ElementHandler` contract

`file/simplesax/ElementHandler.java`. Each handler is responsible for one element and
its immediate children. Method signatures (verbatim):

```java
public interface ElementHandler {

    public ElementHandler openElement(String element,
            HashMap<String, String> attributes,
            WarningSet warnings) throws SAXException;

    public abstract void closeElement(String element,
            HashMap<String, String> attributes,
            String content,
            WarningSet warnings) throws SAXException;

    public abstract void endHandler(String element,
            HashMap<String, String> attributes,
            String content,
            WarningSet warnings) throws SAXException;
}
```

Semantics:

- **`openElement`** — called when a child opening tag is seen. Returns the
  `ElementHandler` that will handle that child's contents, `this` (handle it myself), or
  `null` (ignore the element **and its entire subtree**).
- **`closeElement`** — called on the **parent** handler when a child closes; receives the
  child's name, attributes, and accumulated text `content`. This is where simple
  text/attribute values are consumed.
- **`endHandler`** — called on the handler **itself** when its own element closes (its
  last callback). Not called for the initial/root handler.

### 2.2 Call-order example

For `<foo><bar>message</bar></foo>` with initial handler `initHandler`:

1. `initHandler.openElement("foo", …)` → returns `fooHandler`
2. `fooHandler.openElement("bar", …)` → returns `barHandler`
3. `barHandler.endHandler("bar", …, "message", …)`
4. `fooHandler.closeElement("bar", …, "message", …)`
5. `fooHandler.endHandler("foo", …, …)`
6. `initHandler.closeElement("foo", …, …)`

So a parent receives child values via its **own** `closeElement`, and a handler finalizes
its built object in its **own** `endHandler`. This is how the nested XML is assembled into
an object tree: each handler builds one object and hands children off to sub-handlers.

### 2.3 Supporting classes

- **`SimpleSAX`** — entry point. `public static void readXML(InputSource source,
  ElementHandler initialHandler, WarningSet warnings) throws IOException, SAXException`.
  Pools/caches namespace-aware `XMLReader`s.
- **`DelegatorHandler`** (package-private, extends `org.xml.sax.helpers.DefaultHandler`) —
  the real SAX `ContentHandler`. Maintains three parallel stacks: handlers, accumulated
  character data (`StringBuilder`), and copied attributes (`HashMap<String,String>`).
  In `startElement` it calls the current handler's `openElement`; a `null` return starts
  an *ignore counter* that skips the whole subtree. `characters` appends text.
  `endElement` pops the data/attrs, calls `endHandler` on the popped handler, then
  `closeElement` on the new top handler. Attributes are flattened to a
  `HashMap<localName, value>`.
- **`AbstractElementHandler`** — base class; default `closeElement` warns about unexpected
  text/attributes (useful for catching unknown XML); default `endHandler` is a no-op;
  provides `parseDouble(str, warnings, warn)`.
- **`PlainTextHandler.INSTANCE`** — singleton for leaf text elements; warns on (and
  ignores) any child elements.
- **`NullElementHandler.INSTANCE`** — accepts/ignores anything (used e.g. for RSE
  `<eng-data>` whose data lives entirely in attributes).

**Python port hint:** model `ElementHandler` as a base class with `open_element`,
`close_element`, `end_handler`; drive it with `xml.sax` and replicate the three-stack
delegator (including the `null` ⇒ ignore-subtree counter). The
"text-XOR-children" invariant means you can safely accumulate `characters` per element.

---

## 3. The Component Saver Pattern (`savers/`)

Package `file/openrocket/savers/`. There is **one Saver class per RocketComponent type**,
mirroring the component class hierarchy. The Saver emits that component's XML
attributes/elements.

Convention each concrete Saver follows (e.g. `BodyTubeSaver`, `NoseConeSaver`):

```java
public class BodyTubeSaver extends SymmetricComponentSaver {
    private static final BodyTubeSaver instance = new BodyTubeSaver();

    // Static entry point found reflectively by OpenRocketSaver.
    public static List<String> getElements(RocketComponent c) {
        List<String> list = new ArrayList<>();
        list.add("<bodytube>");          // line 0: open tag
        instance.addParams(c, list);     // middle: parameter lines
        list.add("</bodytube>");         // last line: close tag
        return list;
    }

    @Override
    protected void addParams(RocketComponent c, List<String> elements) {
        super.addParams(c, elements);    // walk up the hierarchy
        ... // type-specific elements, e.g. <radius>, motorMountParams(...)
    }
}
```

Key points:

- **Static `getElements(RocketComponent)`** is the contract `OpenRocketSaver` discovers by
  reflection (`<SimpleName>Saver` in the savers package). It returns a `List<String>`:
  index 0 = open tag, last = close tag, middle = parameters. Empty list ⇒ skip; length 1
  is a bug.
- **`addParams` chains via `super`** up the saver hierarchy
  (`BodyTubeSaver` → `SymmetricComponentSaver` → `BodyComponentSaver` →
  `ExternalComponentSaver` → `RocketComponentSaver`), so each level adds only its own
  fields — exactly paralleling the component class hierarchy.
- **`RocketComponentSaver`** is the common base. Its `addParams` emits the shared
  elements: `<name>`, `<id>`, optional `<preset .../>`, `<appearance>` /
  `<insideappearance>`, `<color>` / `<linestyle>`, instance count / separation, radius/
  angle/axial offsets (with both new and legacy tag names for backward compat), mass/CG/CD
  overrides, and `<comment>`. It also provides `materialParam(...)` (emits
  `<material type="bulk|surface|line" density="..." group="...">name</material>`) and
  `motorMountParams(MotorMount)` (emits the `<motormount>` block including per-config
  `<motor>` metadata: manufacturer, digest, designation, diameter, length, delay).
- Output is plain string concatenation (not a DOM); indentation is applied later by
  `OpenRocketSaver.writeln`.

**Python port hint:** a dict/registry mapping component class → "emit elements" function
reproduces this without reflection; keep the inheritance-style layering so shared fields
are emitted once.

---

## 4. Motor / Thrust-Curve File Loading

Package `file/motor/`. Two on-disk formats plus a zip wrapper.

### 4.1 `MotorLoader` interface

`file/motor/MotorLoader.java` (extends `file/Loader<ThrustCurveMotor.Builder>`):

```java
public interface MotorLoader extends Loader<ThrustCurveMotor.Builder> {
    @Override
    public List<ThrustCurveMotor.Builder> load(InputStream stream, String filename) throws IOException;
}
```

A loader returns a **list of `ThrustCurveMotor.Builder`** (a file may define many motors).
Callers `.build()` each builder to get an immutable `ThrustCurveMotor`.

### 4.2 `AbstractMotorLoader` (shared base)

`file/motor/AbstractMotorLoader.java`:

- `load(InputStream, filename)` wraps the stream in an `InputStreamReader` with the
  loader's `getDefaultCharset()` and delegates to the abstract
  `load(Reader reader, String filename)`.
- Abstract methods: `protected abstract List<ThrustCurveMotor.Builder> load(Reader, String)`
  and `protected abstract Charset getDefaultCharset()`.
- Shared static helpers a Python port will need:
  - `calculateMass(time, thrust, totalMass, propMass)` — derives the **mass vs. time
    curve** from the thrust curve assuming constant exhaust velocity
    (`F = m'·v`; trapezoidal integration of thrust, scaled so total burned mass = propellant
    mass). Used when a file lacks explicit mass data.
  - `removeDelay(designation)` — strips a trailing `-<digits>` or `-P` delay token.
  - `sortLists(primary, others…)` — co-sorts parallel arrays by time.
  - `finalizeThrustCurve(time, thrust, lists…)` — cleans the curve: inserts a
    `(t=0, F=0)` point if missing, removes duplicate/zero-thrust artifacts at the ends.
  - `split(str[, delim])` — whitespace/regex tokenizer.

### 4.3 RASP `.eng` format — `RASPMotorLoader`

Plain-text, charset `ISO-8859-1`. Selected for the `.eng` extension.

- Lines beginning with `;` are comments. The first non-comment line is the **header**
  with exactly **7 whitespace-separated fields**:
  `designation  diameter(mm)  length(mm)  delays  propWeight(kg)  totalWeight(kg)  manufacturer`
  Example: `F32 24 124 5-10-15-P .0377 .0695 RV`.
  - `diameter`/`length` are millimetres in the file → divided by 1000 (stored in metres).
  - `delays` is a `-`/`,`-separated list; `P`/`plugged` ⇒ `Motor.PLUGGED_DELAY`; the
    value `100` (a common "no delay" sentinel) is dropped (`d < 99`).
- Following lines are `time thrust` pairs (2 columns) until the next comment/EOF.
- The CG is assumed at the **center of the casing** (`length/2`); mass is computed via
  `calculateMass`. A `MotorDigest` is computed from the time array, specific mass, and
  force-per-time. Errors: header ≠ 7 fields, non-2-column data, `propW > totalW`,
  thrust curve shorter than 2 points.

### 4.4 RockSim `.rse` format — `RockSimMotorLoader`

XML, charset `UTF-8`, parsed via `simplesax` (`RSEHandler` → `RSEMotorHandler` →
`RSEMotorDataHandler`). Selected for the `.rse` extension. Structure:

```xml
<engine-database>           <!-- or <engine-list> -->
  <engine mfg="..." code="F32-5" Type="single-use" dia="24" len="70"
          initWt="..." propWt="..." delays="5,10,P"
          auto-calc-mass="1" auto-calc-cg="1">
    <comments>...</comments>
    <data>
      <eng-data t="0.0" f="0.0" m="..." cg="..."/>   <!-- m, cg in grams/mm -->
      ...
    </data>
  </engine>
</engine-database>
```

- All scalar motor metadata is in **`<engine>` attributes** (`mfg`, `code`, `dia`, `len`,
  `initWt`, `propWt`, `delays`, `Type`, `auto-calc-mass`, `auto-calc-cg`). Lengths are mm,
  masses grams → converted to metres / kg.
- `Type` maps `single-use`→SINGLE, `hybrid`→HYBRID, `reloadable`→RELOAD, else UNKNOWN.
- Data points carry explicit time `t`, thrust `f`, mass `m`, CG `cg` per `<eng-data>`.
  If `auto-calc-mass`/`auto-calc-cg` are set (or any value is NaN/illegal), mass/CG are
  recomputed (`calculateMass`, CG = `length/2`). Delays ≥ 90 ⇒ plugged.
- A `MotorDigest` is built from whatever real data is present.

`RockSimMotorWriter` performs the reverse (used to embed `.rse` files in the `.ork` ZIP).

### 4.5 Dispatch & zip — `GeneralMotorLoader`

`file/motor/GeneralMotorLoader.java` picks a delegate by **filename extension**:
`.eng`→`RASPMotorLoader`, `.rse`→`RockSimMotorLoader`, `.zip`→`ZipFileMotorLoader`
(recursively loads contained motor files). `getSupportedExtensions()` ⇒
`{ "rse", "eng", "zip" }`. Unknown extension ⇒ `UnknownFileTypeException`.

### 4.6 `ThrustCurveMotor` data model & `Builder`

`motor/ThrustCurveMotor.java` (immutable; implements `Motor`, `Comparable`,
`Serializable`). Core fields a Python data class should mirror:

| Field | Meaning |
|-------|---------|
| `manufacturer` (`Manufacturer`) | Motor manufacturer. |
| `designation` / `commonName` / `code` | Motor naming (e.g. `"F32-5"`, simplified name). |
| `description` | Free text / comments. |
| `type` (`Motor.Type`) | SINGLE / RELOAD / HYBRID / UNKNOWN. |
| `delays` (`double[]`) | Available ejection delays; `Motor.PLUGGED_DELAY` = plugged. |
| `diameter`, `length` (`double`, metres) | Physical dimensions. |
| `time` (`double[]`) | Thrust-curve time points (strictly increasing, starting at 0). |
| `thrust` (`double[]`) | Thrust (N) at each time point — **parallel to `time`**. |
| `cg` (`CoordinateIF[]`) | Per-time-point CG **and mass** (mass is the coordinate's weight). |
| `digest` (`String`) | MD5-style functional fingerprint (matches across files/databases). |
| derived: `initialMass`, `maxThrust`, `averageThrust`, `totalImpulse`, `burnTimeEstimate`, unit inertias | Computed in `build()`. |
| optional metadata: `tcMotorId`, `infoUrl`, `dataFiles`, `updatedOn`, `dataSource`, `sparky`, `caseInfo`, `propellantInfo`, `available` | Database/API extras. |

`ThrustCurveMotor.Builder` is a fluent builder — chained setters
(`setManufacturer`, `setDesignation`, `setDescription`, `setMotorType`,
`setStandardDelays`, `setDiameter`, `setLength`, `setTimePoints(double[])`,
`setThrustPoints(double[])`, `setCGPoints(CoordinateIF[])`, `setDigest`, plus the optional
metadata setters) each `return this`. `build()` **validates** invariants:
`time.length == thrust.length == cg.length`, length ≥ 2, and `time` strictly increasing;
then derives the summary quantities. `Builder.simplifyDesignation(str)` reduces a
designation to impulse-class+thrust (e.g. `"F32"`).

### 4.7 Motor lookup in `.ork` load — `MotorHandler`

When loading a design, `<motor>` elements only carry **metadata** (type, manufacturer,
designation, digest, diameter, length, delay). `importt/MotorHandler.getMotor` resolves
the actual motor by:
1. Querying the motor database via `DocumentLoadingContext.getMotorFinder()` (matched
   primarily by **digest**).
2. Falling back to the embedded `thrustcurves/<digest>.rse` ZIP entry (loaded with
   `GeneralMotorLoader`).

### 4.8 Motor database SPI — `MotorDatabase`

`database/motor/MotorDatabase.java`:

```java
public interface MotorDatabase {
    public List<? extends Motor> findMotors(String digest, Motor.Type type,
            String manufacturer, String designation,
            double diameter, double length);
}
```

Any `null`/`NaN` criterion is ignored. Implementations include
`ThrustCurveMotorSetDatabase` / `ThrustCurveMotorSQLiteDatabase`. `ThrustCurveMotorSet`
groups motors that differ only by delay.

---

## 5. Preset / Database System (`.orc` files)

Packages `preset/`, `preset/xml/`, `preset/loader/`, and `database/`.

### 5.1 `ComponentPreset` — a typed key/value property map

`preset/ComponentPreset.java`. A preset is **not** a fixed struct; it is a
`TypedPropertyMap` (`preset/TypedPropertyMap.java`, a `LinkedHashMap<TypedKey<?>, Object>`)
keyed by **`TypedKey<T>`** instances.

`preset/TypedKey.java`:

```java
public class TypedKey<T> {
    public TypedKey(String name, Class<T> type);
    public TypedKey(String name, Class<T> type, UnitGroup unitGroup);
    public String getName();
    public Class<T> getType();
    public UnitGroup getUnitGroup();
}
```

Well-known keys are static constants on `ComponentPreset`, e.g. `MANUFACTURER`
(`Manufacturer`), `PARTNO` (`String`), `DESCRIPTION`, `TYPE` (`Type`), `LENGTH`,
`OUTER_DIAMETER`, `INNER_DIAMETER`, `MASS`, `MATERIAL` (`Material`), `SHAPE`,
`FINISH`, plus rail-button- and parachute-specific keys. Length/mass keys carry a
`UnitGroup` so values are stored in SI internally.

Access is type-safe: `<T> T get(TypedKey<T>)`, `boolean has(Object key)`. Each preset
also has a **`digest`** (MD5 over its sorted, non-`LEGACY` key/values — see
`computeDigest()`); `equals`/`hashCode` are digest-based.

### 5.2 `ComponentPreset.Type`

An enum enumerating the supported preset categories, each declaring its **displayed
columns** (an ordered `TypedKey<?>[]`):

`BODY_TUBE, NOSE_CONE, TRANSITION, TUBE_COUPLER, BULK_HEAD, CENTERING_RING,
ENGINE_BLOCK, LAUNCH_LUG, RAIL_BUTTON, STREAMER, PARACHUTE`.

`getDisplayedColumns()` returns the keys relevant to that type (used for both UI tables
and which properties a valid preset of that type must carry).

### 5.3 `ComponentPresetDatabase` — registry / query

`database/ComponentPresetDatabase.java` extends `Database<ComponentPreset>` and implements
the query SPI `database/ComponentPresetDao.java`:

```java
public interface ComponentPresetDao {
    List<ComponentPreset> listAll();
    void insert(ComponentPreset preset);
    List<ComponentPreset> listForType(ComponentPreset.Type type);
    List<ComponentPreset> listForType(ComponentPreset.Type type, boolean favorite);
    List<ComponentPreset> listForTypes(ComponentPreset.Type... type);
    List<ComponentPreset> listForTypes(List<ComponentPreset.Type> types);
    void setFavorite(ComponentPreset preset, ComponentPreset.Type type, boolean favorite);
    List<ComponentPreset> find(String manufacturer, String partNo);
}
```

It is an in-memory list with linear filtering by `TYPE`, favorites (via user prefs), and
`(manufacturer, partNo)`. `ComponentPresetDatabaseLoader` / `AsynchronousDatabaseLoader`
populate it from bundled `.orc` files at startup.

### 5.4 `.orc` XML serialization (`preset/xml/`)

Preset component files use the `.orc` extension and are marshalled with **JAXB**
(`jakarta.xml.bind`), unlike the hand-rolled `.ork` writer.

- **`OpenRocketComponentSaver`** — entry point for read/write of `.orc`.
  - `marshalToOpenRocketComponent(List<Material>, List<ComponentPreset> [, boolean legacy])`
    → ORC XML string (sorted by material name / manufacturer+partNo, pretty-printed).
  - `save(File|OutputStream, materials, presets)` writes UTF-8.
  - `unmarshalFromOpenRocketComponent(Reader)` → `OpenRocketComponentDTO`.
  - Uses one shared thread-safe `JAXBContext` over `OpenRocketComponentDTO`; creates a
    local `Marshaller`/`Unmarshaller` per call.
- **`OpenRocketComponentDTO`** — JAXB root, `@XmlRootElement(name="OpenRocketComponent")`.
  Contains `<Version>` (`"0.1"`), optional `<Legacy>`, a `<Materials>` wrapper of
  `<Material>` (`MaterialDTO`), and a `<Components>` wrapper holding a polymorphic list of
  component DTOs via `@XmlElementRefs` (`BodyTubeDTO`, `NoseConeDTO`, `TransitionDTO`,
  `TubeCouplerDTO`, `BulkHeadDTO`, `CenteringRingDTO`, `EngineBlockDTO`, `LaunchLugDTO`,
  `RailButtonDTO`, `StreamerDTO`, `ParachuteDTO`).
  - `asComponentPresets()` / `asMaterialList()` convert the DTO graph back into domain
    objects.
- **`BaseComponentDTO` + per-type DTOs** — each DTO subclass maps one preset type. Pattern
  (see `BodyTubeDTO`):
  - Constructor `XxxDTO(ComponentPreset preset)` pulls values out via `preset.get(KEY)`
    into JAXB-annotated fields (e.g. `<InsideDiameter>`, `<OutsideDiameter>`, `<Length>`,
    each wrapped as `AnnotatedLengthDTO` carrying value+unit).
  - `asComponentPreset(legacy, materials)` rebuilds a `TypedPropertyMap` (`put(KEY, value)`
    + `put(TYPE, ...)`) and calls `ComponentPresetFactory.create(props)`.
- The `toComponentDTO(preset)` factory (`OpenRocketComponentSaver`) switches on
  `preset.getType()` to pick the right DTO subclass — the marshalling counterpart of the
  saver/handler dispatch elsewhere.

> Note: there is a separate **RockSim CSV preset loader** path under `preset/loader/`
> (`RockSimComponentFileLoader` + per-type `*Loader` and `*ColumnParser` classes) that
> imports vendor CSV component libraries into `ComponentPreset`s. It is column-driven
> (a `BaseColumnParser`/`*ColumnParser` per field) rather than XML, and feeds the same
> `ComponentPresetFactory.create(TypedPropertyMap)`.

---

## 6. Design Patterns Summary (for the port)

- **SAX handler delegation** (`simplesax`): a stack of single-element handlers; parents
  receive child values via `closeElement`, finalize themselves via `endHandler`, and
  return child handlers (or `null` to skip subtrees) from `openElement`. The single most
  important reusable pattern.
- **Per-type Saver/Setter dispatch** (reflection on the write side, a `Class:element`
  registry on the read side) parallels the component class hierarchy via `super` chaining.
  In Python, replace reflection with explicit registries/dicts.
- **Builder** (`ThrustCurveMotor.Builder`): fluent setters + a validating `build()`.
- **Registry / Database** (`ComponentPresetDatabase` / `MotorDatabase`): in-memory
  collections queried by type, digest, manufacturer/part. Motors are matched primarily by
  **digest**, which is the stable cross-file identity.
- **DTO + JAXB marshalling** for `.orc`, vs. hand-written streaming XML for `.ork` — a
  Python port can use a single XML library for both but should preserve the element/
  attribute names exactly.
- **Self-contained ZIP container** for `.ork`: `rocket.ork` + `preview.png` + decals +
  `thrustcurves/<digest>.rse`. Resolve motors/decals lazily from sibling ZIP entries.

### Key source files

- `.ork` write: `file/openrocket/OpenRocketSaver.java`, `file/GeneralRocketSaver.java`
- `.ork` read: `file/openrocket/importt/OpenRocketLoader.java`,
  `OpenRocketHandler.java`, `OpenRocketContentHandler.java`,
  `ComponentParameterHandler.java`, `Setter.java`, `DocumentConfig.java`,
  `MotorHandler.java`
- simplesax: `file/simplesax/{ElementHandler,AbstractElementHandler,DelegatorHandler,SimpleSAX,PlainTextHandler,NullElementHandler}.java`
- savers: `file/openrocket/savers/RocketComponentSaver.java` + per-type `*Saver.java`
- motors: `file/motor/{MotorLoader,AbstractMotorLoader,GeneralMotorLoader,RASPMotorLoader,RockSimMotorLoader,RockSimMotorWriter,ZipFileMotorLoader}.java`,
  `motor/ThrustCurveMotor.java`, `database/motor/MotorDatabase.java`
- presets: `preset/{ComponentPreset,TypedKey,TypedPropertyMap,ComponentPresetFactory}.java`,
  `preset/xml/{OpenRocketComponentSaver,OpenRocketComponentDTO,BaseComponentDTO,*DTO}.java`,
  `database/{ComponentPresetDao,ComponentPresetDatabase}.java`, `preset/loader/*`
- format history: repo-root `fileformat.txt`
