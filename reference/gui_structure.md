# OpenRocket Swing GUI — Structure Map for a Python Reimplementer

This document maps the OpenRocket Swing desktop GUI (package
`info.openrocket.swing.gui`) onto the concepts a PyQt/Tk reimplementer needs.
It describes the window layout, the model/view bindings, the simulation
execution flow, and the plotting subsystem. It is reference material only —
no Java was modified.

The dominant architectural idea throughout: **the GUI is a set of views over a
single mutable domain model (`OpenRocketDocument` → `Rocket` tree). Views do not
hold their own copy of state; they register as observers and rebuild/repaint
when the model fires change events.** The two core observer channels are:

- `ComponentChangeEvent` / `ComponentChangeListener` — fired by the `Rocket`
  component tree when any component is modified, added, removed, or moved.
- `DocumentChangeEvent` / `DocumentChangeListener` and
  `SimulationChangeEvent` — fired by the `OpenRocketDocument` for
  document-level and simulation-list changes.

Swing-specific adapters (`TreeModel`, `TableModel`, `SwingWorker`) bridge these
domain events to widget redraws. A Python port should replicate the same
observer wiring with whatever signal/slot or callback mechanism the GUI toolkit
provides (Qt signals map almost 1:1).

---

## 1. `BasicFrame` — the main window

File: `swing/src/main/java/info/openrocket/swing/gui/main/BasicFrame.java`
(`extends JFrame`).

One `BasicFrame` instance per open document. A static `List<BasicFrame> frames`
tracks open windows; the app exits when the list empties. The frame **owns the
document**:

```java
private final OpenRocketDocument document;
private final Rocket rocket;            // = document.getRocket()
```

### Overall layout

The content pane is a single vertical `JSplitPane` (`JSplitPane.VERTICAL_SPLIT`,
divider ~0.4, resize weight 0.5):

- **Top component**: a `JTabbedPane` with three tabs (constants on the class):
  - `DESIGN_TAB = 0` → `DesignPanel` (label `"Rocket design"`)
  - `FLIGHT_CONFIGURATION_TAB = 1` → `FlightConfigurationPanel` (label `"Flight configurations"`)
  - `SIMULATION_TAB = 2` → `SimulationPanel` (label `"Flight simulations"`)
- **Bottom component**: a `RocketPanel` (the 2D/3D schematic figure view),
  shared across all three tabs (always visible beneath them).

A `ChangeListener` on the tabbed pane (`BasicFrame_changeAdapter`) auto-runs
out-of-date simulations when the user switches to the Simulation tab.

### Selection models (shared MVC glue)

`BasicFrame` constructs and shares the selection models that tie the tree, the
figure, and the simulation table together:

```java
componentSelectionModel = new DefaultTreeSelectionModel();   // DISCONTIGUOUS
simulationSelectionModel = simulationPanel.getSimulationListSelectionModel();
selectionModel = new DocumentSelectionModel(document);       // combines both
selectionModel.attachComponentTreeSelectionModel(componentSelectionModel);
selectionModel.attachSimulationListSelectionModel(simulationSelectionModel);
actions = new RocketActions(document, selectionModel, this, simulationPanel);
```

- `tree = new ComponentTree(document)` and `tree.setSelectionModel(componentSelectionModel)`.
- `rocketpanel.setSelectionModel(tree.getSelectionModel())` — so selecting a
  component in the tree highlights it in the figure and vice-versa.
- `DocumentSelectionModel` + `DocumentSelectionListener` (file
  `DocumentSelectionModel.java`, `DocumentSelectionListener.java`) is the
  single "what is currently selected" facade that menu/toolbar actions query to
  enable/disable themselves.

### Menus, toolbar, popup

- `createMenu()` builds a `JMenuBar`: **File** (New/Open/Open Recent/Open
  Example/Import RASAero+RockSim, Save/Save As, Export As → RASAero/RockSim/
  Wavefront OBJ/SVG, Export decal, Print, Export sim table CSV, Properties,
  Close, Quit), **Edit** (Undo/Redo via `UndoRedoAction`, Cut/Copy/Paste/
  Duplicate/Delete via `RocketActions`, Select submenu, Scale, Visibility,
  Preferences), **Tools** (Component analysis, Optimize, Custom expressions,
  Photo studio), **Help**.
- There is no separate persistent toolbar — action buttons live inside each
  tab panel (`DesignPanel` has move-up/down/edit/duplicate/delete buttons;
  `SimulationPanel` has new/edit/run/delete/plot buttons). Buttons are wired
  with `RocketActions.tieActionToButton(...)`.
- A `JPopupMenu` (`popupMenu`) is the context menu shown over the component tree
  (`doComponentTreePopup(MouseEvent)`), populated from the same `RocketActions`.

### Document/observer wiring at frame level

```java
rocket.addComponentChangeListener(e -> setTitle());      // dirty-flag title
document.addDocumentChangeListener(e -> setTitle());
```

`RocketActions` and `UndoRedoAction` are the **Command** objects (Swing
`AbstractAction`). They mutate the document and call `document.addUndoPosition(...)`
to checkpoint undo state. Undo/redo is a document-level service, not per-widget.

**Python mapping**: a `MainWindow` owning a `Document`; a tab widget with three
pages; a persistent figure pane below; shared selection state broadcast to all
views; a menu/action layer that reads selection state to set enabled/disabled.

---

## 2. Design tab — `DesignPanel` + `RocketPanel` + component tree

### `DesignPanel` (the design tab body)

File: `swing/.../gui/main/DesignPanel.java` (`extends JSplitPane`, horizontal).

- **Left**: the `ComponentTree` inside a `JScrollPane`, plus a vertical strip of
  buttons (Move Up, Move Down, Edit, Duplicate, Delete) tied to `RocketActions`.
- **Right**: a `ComponentAddButtons` panel inside a titled scroll pane
  ("Add new component") — the palette of component types you can append to the
  selected node.

### Editing flow (selection → config dialog)

`DesignPanel` installs mouse/selection listeners on the tree:

- **Double-click** a component → `ComponentConfigDialog.showDialog(parent, document, component)`
  opens a modeless config dialog for that component type. Shift/Ctrl+double-click
  adds the other selected components as *config listeners* of the primary one
  (`component.addConfigListener(c)`), giving multi-component simultaneous edit.
- **Right-click** → selects the path and calls `parent.doComponentTreePopup(e)`.
- **Selection change** (`TreeSelectionListener`): if a config dialog is already
  open it is disposed and reopened for the new selection; selecting a stage/
  rocket/podset highlights all its children in the figure
  (`highlightAssemblyChildren`).

The config dialogs live in `gui/configdialog/`. `ComponentConfigDialog` is the
dispatcher; one config panel class per component type
(`NoseConeConfig`, `BodyTubeConfig`, `TrapezoidFinSetConfig`,
`FreeformFinSetConfig`, `ParachuteConfig`, `MotorConfig`, etc.), all extending
`RocketComponentConfig`. Edits made in these panels mutate the live
`RocketComponent`, which fires `ComponentChangeEvent`s that ripple to every
view.

### `ComponentTree` and the `TreeModel` adapter (key binding contract)

Files: `gui/main/componenttree/ComponentTree.java`,
`ComponentTreeModel.java`, plus renderers and a drag/drop transfer handler.

- `ComponentTree extends BasicTree (JTree)`. Its constructor does
  `setModel(new ComponentTreeModel(document.getRocket(), this))`,
  sets a `ComponentTreeRenderer`, enables drag-and-drop
  (`ComponentTreeTransferHandler`), and expands the whole tree.

- **`ComponentTreeModel implements javax.swing.tree.TreeModel,
  ComponentChangeListener`** — this is the central adapter. It wraps the
  `Rocket` component tree as a Swing tree and *is itself a listener* on the
  rocket so model edits redraw the tree:

  ```java
  public ComponentTreeModel(RocketComponent root, JTree tree) {
      this.root = root; this.tree = tree;
      root.addComponentChangeListener(this);
  }

  // TreeModel contract — delegates straight to RocketComponent:
  Object  getRoot()                                  // returns root component
  Object  getChild(Object parent, int index)         // parent.getChild(index)
  int     getChildCount(Object parent)               // parent.getChildCount()
  int     getIndexOfChild(Object parent, Object child)
  boolean isLeaf(Object node)                         // !node.allowsChildren()
  void    addTreeModelListener / removeTreeModelListener

  // observer contract — domain event → tree event:
  void componentChanged(ComponentChangeEvent e) {
      if (e.isTreeChange() || e.isUndoChange()) fireTreeStructureChanged(e.getSource());
      else if (e.isTreeChildrenChange())        fireTreeNodeChanged(each child);
      else                                       fireTreeNodeChanged(e.getSource());
  }
  ```

  On a structure change it **preserves expansion and selection across the
  rebuild by remembering component UUIDs** (`getSelectedPathIds` /
  `restoreSelection` / `findNearestExistingComponent`), which matters because
  undo can replace component *instances* with new objects of the same id.

  Static helpers form the path/component conversion contract:
  ```java
  static RocketComponent componentFromPath(TreePath path)
  static List<RocketComponent> componentsFromPaths(TreePath[] paths)
  static TreePath makeTreePath(RocketComponent component)   // walks getParent() chain
  static List<TreePath> makeTreePaths(List<RocketComponent> components)
  ```

**Python mapping**: implement a tree-model adapter (e.g. `QAbstractItemModel`)
backed by the `Rocket` tree; subscribe it to component-change signals; emit
`layoutChanged`/`dataChanged` on structure vs. node changes; key selection/
expansion restoration on component ids, not object identity.

### `RocketPanel` — the schematic / figure view

File: `gui/scalefigure/RocketPanel.java` (`extends JPanel implements
TreeSelectionListener, ChangeSource, CAParametersListener`).

- Holds a 2D `RocketFigure` and a 3D `RocketFigure3d`, swapped in a
  `figureHolder` (BorderLayout). View modes enum includes side/back 2D views and
  `Figure3D`/`Unfinished`/`Finished` 3D modes.
- The 2D figure sits inside a **`ScaleScrollPane`** (`gui/scalefigure/
  ScaleScrollPane.java`, `extends JScrollPane`) which adds rulers in real units,
  drag-to-pan, and zoom. A `ScaleSelector` combo controls zoom; a
  `ViewRotationControl` rotates the view.
- `RocketFigure extends AbstractScaleFigure`. It renders each component by asking
  `RocketComponentShapeProvider` for `RocketComponentShapes` (AWT `Shape`s),
  drawing them with an `AffineTransform` (model coords → screen). It overlays
  `FigureElement`s such as `RocketInfo`, `CGCaret`, `CPCaret` (the CG/CP markers).
- `setSelectionModel(TreeSelectionModel m)` couples figure selection to the tree;
  clicking a shape in the figure selects the corresponding tree node and vice
  versa.
- The panel listens to the rocket: `rkt.addComponentChangeListener(...)` →
  `updateExtras(); updateFigures();` on every change, so the schematic and the
  CG/CP/stability readout stay live.

`updateExtras()` computes the data shown as overlay text (file lines ~1242+):
- `cp = aerodynamicCalculator.getCP(curConfig, conditions, warnings)`
  (a `BarrowmanCalculator`),
- `cg = MassCalculator.calculateLaunch(curConfig).getCM()`,
- and a `BackgroundSimulationWorker extends SimulationWorker` (inner class,
  ~line 1522) runs a quick flight in the background to fill in apogee/velocity
  figures shown in the `RocketInfo` overlay (`simulationDone()` →
  `figure.repaint()`).

**Python mapping**: a canvas/graphics-view that paints component outlines from
the model, supports zoom/pan with unit rulers, overlays CG/CP markers, and
recomputes CP/CG (via the core calculators) on every model change — ideally off
the UI thread for the flight estimate.

---

## 3. `SimulationPanel` — the simulation tab

File: `gui/main/SimulationPanel.java` (`extends JPanel`).

### Layout

- A row of action buttons (New, Edit, Run, Delete, Plot/Export) tied to
  `SimulationAction` subclasses.
- A `CardLayout` switching between a "help" card (shown when there are no
  simulations) and the "table" card.
- The table is a `ColumnTable` driven by a `ColumnTableModel` (custom
  column-oriented `TableModel` in `gui/adaptors/`). Columns are declared by id:
  status, warnings, name, configuration, simulation stepper, launch-rod velocity,
  apogee, deployment velocity, optimum coast time, max velocity, max
  acceleration, time-to-apogee, flight time, ground-hit velocity. A
  `ColumnVisibilityController` lets users hide/show columns (persisted in prefs).
  Sorting via `ColumnTableRowSorter`.
- The **Status** column renders an icon per `Simulation.Status` (NOT SIMULATED /
  UP-TO-DATE / OUT-OF-DATE / EXTERNAL / LOADED) and the **Warnings** column
  renders a warning/error icon with a tooltip listing the `WarningSet` from the
  simulation's `FlightData`.

### Data source and actions

The table reads directly from `document.getSimulations()`. Actions
(`NewSimulationAction`, `RunSimulationAction`, `PlotSimulationAction`,
`DeleteSimulationAction`, `Duplicate`, `Cut/Copy/Paste`, CSV export):

- **New**: `new Simulation(document, document.getRocket())`,
  `document.addSimulation(sim)`, then opens the config dialog.
- **Run**: `getSelectedSimulations()` → `new SimulationRunDialog(window,
  document, sims).setVisible(true)` (modal progress dialog, see §5).
- **Delete**: confirm, then `document.removeSimulation(sim)` and
  `simulationTableModel.fireTableDataChanged()`.
- **Plot**: if `!sim.hasSimulationData()` it first runs it via
  `SimulationRunDialog`, then opens the plot/export config dialog
  (`SimulationConfigDialog` → `SimulationPlotPanel`/`SimulationExportPanel`).
- **Edit**: opens `SimulationConfigDialog` (launch conditions, simulation
  options, warnings tab).

The panel registers a selection listener and refreshes button enablement and
the table whenever the document's simulation list or a simulation's data
changes (`SimulationChangeEvent`). `getSimulationListSelectionModel()` exposes
the table's `ListSelectionModel` up to `BasicFrame`.

**Python mapping**: a table model bound to `document.simulations`, an icon-status
+ warnings column, an action layer that runs sims through a modal progress
dialog and opens plot/edit dialogs; refresh on simulation-change signals.

---

## 4. Plot subsystem — `gui/plot/` (+ `gui/simulation/SimulationPlotPanel`)

Built on **JFreeChart** (`org.jfree.chart.*`). The package is generic over data
type/branch so it can plot both simulation flight data and component-analysis
data; flight-data subclasses specialize the generics to
`FlightDataType` / `FlightDataBranch`.

### Classes and roles

| Class | Role |
|---|---|
| `Axis` | One plot axis (min/max range bookkeeping). |
| `PlotConfiguration<T extends DataType, B extends DataBranch<T>>` | The plot *spec*: which data types to plot, their units, which Y-axis (left/right/auto), and the domain (X) type/unit. Contains the auto-layout scoring logic (`BONUS_*` constants) that picks how series map onto the two axes. |
| `SimulationPlotConfiguration` | Flight-data subclass of `PlotConfiguration`; ships `DEFAULT_CONFIGURATIONS` presets (Vertical motion, Stability, Drag, Roll, etc.). |
| `Plot<T,B,C>` (abstract) | Builds the JFreeChart `JFreeChart`/`XYPlot` from a config + data branches: creates `XYSeries`/`XYSeriesCollection`, `NumberAxis`es, `XYLineAndShapeRenderer`s, legend, event markers (`ValueMarker`). Holds `ModifiedXYItemRenderer`s and `LegendItems`. |
| `SimulationPlot` | Concrete `Plot` for a `Simulation`: maps `FlightDataBranch`es to series, draws flight `FlightEvent` markers (launch, burnout, apogee, ejection, landing) via `EventGraphics`/`EventDisplayInfo`, supports per-branch show/hide (`setShowBranch`) and error annotations (`ErrorAnnotationSet`, `setShowErrors`). `create(simulation, config, showPoints)` is the factory. |
| `EventGraphics` | Icons/markers for `FlightEvent`s drawn on the chart. |
| `PlotTypeSelector<T,G>` | One UI row: a searchable/groupable combo to pick a `FlightDataType`, a `UnitSelector`, an axis (Auto/Left/Right) combo, and a remove button. Repeated per plotted series. |
| `PlotPanel` / `SimulationPlotPanel` | The configuration UI: a list of `PlotTypeSelector` rows + a domain-axis (X) selector + preset chooser + an event table. Builds a `SimulationPlotConfiguration` from user choices. `SimulationPlotPanel extends PlotPanel<...>`. |
| `PlotDialog` / `SimulationPlotDialog` | The window that actually shows the rendered chart (with show-points / show-events / show-errors checkboxes, branch selector). `SimulationPlotDialog.getPlot(parent, simulation, config)` builds a `SimulationPlot` and wraps it. |
| `SimulationChart` | Chart panel wrapper (embeds the JFreeChart `ChartPanel`). |
| `Util` | Helpers incl. the `PlotAxisSelection` enum (AUTO/LEFT/RIGHT). |

### Flow

1. User picks data types/units/axes in `SimulationPlotPanel` → produces a
   `SimulationPlotConfiguration`.
2. `SimulationPlotDialog.getPlot(...)` → `SimulationPlot.create(sim, config, …)`
   pulls `simulation.getSimulatedData()` (a `FlightData` with one or more
   `FlightDataBranch`es), turns each plotted `FlightDataType` into an `XYSeries`
   keyed off the domain type (usually time), and assembles the `XYPlot`.
3. Flight events become vertical markers; multiple data branches (stages) become
   parallel series toggled by `setShowBranch`.
4. Export: chart can be saved as an image; numeric data export is handled
   separately via `SimulationExportPanel` (CSV) reachable from the same config
   dialog, and `SimulationTableCSVExport` for the summary table.

**Python mapping**: replace JFreeChart with pyqtgraph/Matplotlib. Keep the
`PlotConfiguration` value object (types, units, axis assignment, domain type)
as the serializable plot spec; build a "series selector row" widget equivalent
to `PlotTypeSelector`; render each `FlightDataType` from a `FlightDataBranch`
as an XY series, with event markers as vertical lines.

---

## 5. GUI ↔ simulation-engine binding (background execution + data return)

### The model

- `OpenRocketDocument` holds the `Rocket` and a `List<Simulation>`. It is the
  single source of truth and the hub for document/simulation change events and
  for undo (`addUndoPosition`).
- A `Simulation` (core class) couples a flight configuration + simulation
  options to the rocket. `simulation.simulate(listeners...)` runs the physics
  (the core `SimulationEngine`/stepper) and stores results;
  `simulation.getSimulatedData()` returns `FlightData`
  (→ `getBranch(i)`/`getBranches()` → `FlightDataBranch`es of time-series
  `FlightDataType` arrays); `simulation.getStatus()`,
  `hasSimulationData()`, `getWarnings()` report state.

### Background execution — `SimulationWorker` (the contract)

File: `gui/simulation/SimulationWorker.java`:

```java
public abstract class SimulationWorker extends SwingWorker<FlightData, SimulationStatus> {
    protected final Simulation simulation;

    protected FlightData doInBackground() {           // runs on worker thread
        SimulationListener[] listeners = getExtraListeners();
        // always append a CancelListener that throws SimulationCancelledException
        // when SwingWorker.isCancelled() — checked every postStep()
        try { simulation.simulate(listeners); }
        catch (Throwable e) { throwable = e; return null; }
        return simulation.getSimulatedData();
    }

    protected SimulationListener[] getExtraListeners();   // hook, default empty
    protected abstract void simulationDone();             // success, on EDT
    protected abstract void simulationInterrupted(Throwable t); // failure/cancel, on EDT

    protected final void done() {                         // EDT
        if (throwable == null) simulationDone(); else simulationInterrupted(throwable);
    }
}
```

Key points for a port:
- The simulation runs **off the UI thread**; cancellation is cooperative via a
  `SimulationListener.postStep` check (`CancelListener`).
- `getExtraListeners()` lets callers inject listeners — used for progress
  reporting, custom-expression evaluation
  (`CustomExpressionSimulationListener`), ground-hit detection, etc.
- Results (`FlightData`) come back through `doInBackground`'s return value and
  the worker's `done()` callback dispatched to the UI thread.

### Running from the GUI — `SimulationRunDialog`

File: `gui/simulation/SimulationRunDialog.java` (`extends JDialog`, modal).

- A single shared static `ThreadPoolExecutor` (size = `SwingPreferences.
  getMaxThreadCount()`, daemon threads) runs all sims — it is never shut down.
- For each selected `Simulation` it creates an
  `InteractiveSimulationWorker(document, sim, i)` (a `SimulationWorker` subclass)
  and `executor.execute(worker)`. So *N* sims run concurrently.
- A `Timer`-driven `updateProgress()` (every `UPDATE_MS = 200`) polls each
  worker's `getProgress()` and `publish`ed `SimulationStatus` to update the
  progress bar and the live time/altitude/velocity labels. Progress is mapped to
  flight phases (`BURNOUT_PROGRESS = 0.4`, `APOGEE_PROGRESS = 0.7`).
- Cancel button / window-close → `cancelSimulations()` calls `worker.cancel(true)`
  on every worker and `executor.purge()`.
- Static convenience: `SimulationRunDialog.runSimulations(parent, document, sims...)`.
- When all workers finish, the dialog disposes; the resulting `FlightData` is now
  stored in each `Simulation`, so the table refreshes and plots can read it.

### Observer wiring summary (who listens to what)

- **`Rocket` → views**: `ComponentChangeListener` on the rocket drives the
  `ComponentTreeModel` (tree redraw), the `RocketPanel`/`RocketFigure` (schematic
  + CP/CG recompute), and `BasicFrame` (dirty title). Editing a component in a
  config dialog fires these events.
- **`OpenRocketDocument` → views**: `DocumentChangeListener` (title/dirty) and
  `SimulationChangeEvent` (simulation table refresh / status icons).
- **Selection**: `DocumentSelectionModel` aggregates the tree's
  `TreeSelectionModel` and the table's `ListSelectionModel`; `RocketActions` and
  menu items read it to enable/disable; the figure and tree mirror each other's
  selection.
- **Simulation execution**: `Simulation` + `SimulationListener` callbacks feed
  `SimulationWorker`/`SimulationRunDialog`; results return as `FlightData`,
  which then feeds the simulation table columns and the plot subsystem.

### Design patterns in play

- **MVC / Observer** — `Rocket`/`OpenRocketDocument` are the model; tree, figure,
  table, config dialogs are views; all subscribe to change events.
- **Swing TreeModel adapter** — `ComponentTreeModel` adapts the domain tree to
  Swing's `TreeModel` and translates `ComponentChangeEvent` → `TreeModelEvent`.
- **TableModel adapter** — `ColumnTableModel` adapts `List<Simulation>` to a
  Swing `JTable`.
- **Command** — `AbstractAction` subclasses (`RocketActions`, `SimulationAction`,
  `UndoRedoAction`) encapsulate user operations and integrate with the undo
  stack (`document.addUndoPosition`).
- **SwingWorker background threading** — `SimulationWorker` runs the engine off
  the EDT, publishes progress, returns results to the EDT in `done()`.
- **Listener-injection / Strategy** — `SimulationListener`s injected into a run
  customize behavior (cancel, progress, custom expressions, ground-hit).

---

## Quick file index

| Concern | Key files |
|---|---|
| Main window / layout / menus | `gui/main/BasicFrame.java` |
| Design tab | `gui/main/DesignPanel.java`, `gui/main/ComponentAddButtons.java`, `gui/main/RocketActions.java` |
| Component tree adapter | `gui/main/componenttree/ComponentTree.java`, `ComponentTreeModel.java`, `ComponentTreeRenderer.java`, `ComponentTreeTransferHandler.java` |
| Schematic figure | `gui/scalefigure/RocketPanel.java`, `RocketFigure.java`, `AbstractScaleFigure.java`, `ScaleScrollPane.java`, `ScaleSelector.java` |
| Component editing dialogs | `gui/configdialog/ComponentConfigDialog.java` + per-type `*Config.java` |
| Simulation tab | `gui/main/SimulationPanel.java`, `gui/adaptors/ColumnTable*.java` |
| Run a simulation | `gui/simulation/SimulationRunDialog.java`, `SimulationWorker.java`, `SimulationConfigDialog.java` |
| Plotting | `gui/plot/Plot.java`, `PlotConfiguration.java`, `SimulationPlot.java`, `SimulationPlotConfiguration.java`, `SimulationPlotDialog.java`, `PlotTypeSelector.java`, `gui/simulation/SimulationPlotPanel.java`, `gui/simulation/SimulationExportPanel.java` |
| Selection glue | `gui/main/DocumentSelectionModel.java`, `DocumentSelectionListener.java` |

*All paths relative to `swing/src/main/java/info/openrocket/swing/`.*
