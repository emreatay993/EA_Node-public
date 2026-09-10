# COREX Node Editor

A Windows-first visual node editor for engineering dataflow pipelines. Build
graphs on a QML canvas, run workflows in a separate worker process, author
passive visual layouts on the same graph, and automate file, spreadsheet,
tabular, process, and HPC-oriented tasks from a single desktop shell.

Recent UI/UX architecture highlights:

- App-wide Graphics Settings modal for grid, minimap, snap-to-grid default, shell-theme selection, and graph-theme follow-shell or explicit selection
- Split shell/chrome theming (`ThemeBridge` + `stitch_dark` / `stitch_light`) from node/edge graph theming (`graphThemeBridge` + built-in/custom graph themes)
- Bridge-first shell/canvas QML context using `shellLibraryBridge`, `shellWorkspaceBridge`, `shellInspectorBridge`, `graphCanvasStateBridge`, `graphCanvasCommandBridge`, `graphActionBridge`, and typed viewer/add-on/status bridges instead of raw `mainWindow` / `sceneBridge` / `viewBridge` globals
- Custom graph-theme library/editor with built-in read-only themes, custom duplication/CRUD, and live apply for the active explicit custom theme
- Graphics preferences now persist in `app_preferences.json` separately from project `.cxproj` files and `last_session.json`
- Passive visual node families now ship in the main graph model for flowcharting, planning, annotation, and local image/PDF presentation
- Dependency-gated `Tabular Data Input` now ships under `Data`, opening table and dense-array sources through lazy refs with bounded inline/fullscreen previews and direct generic plot-node auto-mapping
- Dedicated `Group` passive grouping nodes render on an under-edge layer, appear under `Utilities > Canvas`, wrap the current selection with shortcut `C`, derive nested membership from geometry, and keep collapse/clipboard behavior distinct from note-style annotation cards
- Passive `flow` edges support labels and per-edge style overrides while remaining excluded from runtime compilation and worker execution
- Passive node and flow-edge style overrides can be edited from context menus and saved as project-local presets in `.cxproj` metadata
- `Help > Keyboard and Mouse Reference` lists the current shortcuts, mouse gestures, hidden-port decluttering gestures, context-menu gestures, and focused editor controls users can invoke across the shell and graph canvas, with Context and Action filters for lookup
- Graph-surface input routing now keeps host body gestures under loaded surfaces, uses `embeddedInteractiveRects` for local control ownership, and reserves `blocksHostInteraction` for whole-surface modal tools such as crop mode
- Shared header inline title editing now spans standard, passive, collapsed, and scope-capable node shells, reusing the existing rename/history path while keeping a dedicated `OPEN` badge for subnode scope entry
- Connection-aware quick insert from a dangling wire drag
- Shared graph-surface controls now cover inline `toggle`, `enum`, `text`, `number`, `textarea`, and `path` editors without depending on selected-node timing
- Python-side compatibility filtering so quick insert follows the same effective-port rules as graph connections
- Inspector and script editing surfaces now use user-facing node labels and sequential IDs instead of exposing internal `node_*` references

## Getting Started

```powershell
# 1. Create the project virtual environment (Windows-first layout)
py -3.10 -m venv venv

# 2. Install runtime + developer dependencies into that venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e ".[all,dev]"

# 3. Launch the app
.\venv\Scripts\python.exe -m ea_node_editor.bootstrap
```

- For a fuller setup and orientation guide, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).
- For QWebEngine / `PyQt6-WebEngine` installation and intranet repair steps, see [docs/QT_WEBENGINE_INSTALLATION.md](docs/QT_WEBENGINE_INSTALLATION.md).
- The package-module command above is the source/dev launch path. For packaged Windows builds and installer bundles, use [docs/PACKAGING_WINDOWS.md](docs/PACKAGING_WINDOWS.md).
- `.[all,dev]` includes the optional `tabular` extra. Use `.[tabular]` by itself when you only need the dependency-gated `Data > Tabular Data Input` node.
- On Windows, user data lives under `%APPDATA%\COREX_Node_Editor\`; public single-file plugin drop-ins live directly in `%APPDATA%\COREX_Node_Editor\plugins\`, and imported `.cxpkg` packages install as subdirectories beneath that same root.
- The console entry point installed by editable mode is `corex-node-editor`.
- PowerShell examples are shown here. If you still open the repo from `bash`, use the same `venv/Scripts/python.exe` interpreter with `./...` path syntax.

## Project Structure

Core source layout (package `__init__.py` files omitted for brevity):

```text
ea_node_editor/
  app.py
  settings.py
  addons/
    tabular_data/
      catalog.py
      input_node.py
      loader_cache_service.py
  custom_workflows/
    codec.py
    file_codec.py
    global_store.py
  execution/
    client.py
    compiler.py
    protocol.py
    worker.py
  graph/
    effective_ports.py
    hierarchy.py
    model.py
    normalization.py
    rules.py
    transforms.py
  nodes/
    bootstrap.py
    decorators.py
    package_manager.py
    plugin_loader.py
    registry.py
    types.py
    builtins/
      core.py
      hpc.py
      integrations.py
      integrations_common.py
      integrations_email.py
      integrations_file_io.py
      integrations_process.py
      integrations_spreadsheet.py
      passive_annotation.py
      passive_flowchart.py
      passive_media.py
      passive_planning.py
      subnode.py
  persistence/
    migration.py
    project_codec.py
    serializer.py
    session_store.py
    utils.py
  runtime_contracts/
    runtime_values.py
    tabular_data.py
  telemetry/
    frame_rate.py
    startup_profile.py
    system_metrics.py
  ui/perf/
    performance_harness.py
  ui/
    app_icon.py
    graph_interactions.py
    graph_theme/
      presentation.py
      registry.py
      runtime.py
      tokens.py
    dialogs/
      flow_edge_style_dialog.py
      graph_theme_editor_dialog.py
      graphics_settings_dialog.py
      passive_node_style_dialog.py
      passive_style_controls.py
      sectioned_settings_dialog.py
      workflow_settings_dialog.py
    editor/
      code_editor.py
    media_preview_provider.py
    passive_style_presets.py
    pdf_preview_provider.py
    tabular_preview_provider.py
    shell/
      state.py
      run_flow.py
      workspace_flow.py
      inspector_flow.py
      library_flow.py
      runtime_history.py
      runtime_clipboard.py
      window.py
      window_actions.py
      window_library_inspector.py
      window_search_scope_state.py
      controllers/
        app_preferences_controller.py
        run_controller.py
        project_session_controller.py
        workspace_selection_context.py
        workspace_navigation_controller.py
        workspace_edit_controller.py
        workflow_library_controller.py
        workspace_package_io_controller.py
        workspace_view_nav_ops.py
        workspace_drop_connect_controller.py
        workspace_io_ops.py
        result.py
    theme/
      registry.py
      styles.py
      tokens.py
  assets/
    app_icon/
      corex_app.svg
      corex_app_*.png
      corex_app_transparent.svg
      corex_app_transparent_*.png
      corex_app_minimal.svg
      corex_app_minimal_*.png
      corex_app.ico
  ui_qml/
    MainShell.qml
    graph_scene_bridge.py
    graph_theme_bridge.py
    viewport_bridge.py
    edge_routing.py
    console_model.py
    script_editor_model.py
    status_model.py
    syntax_bridge.py
    theme_bridge.py
    workspace_tabs_model.py
    components/
      GraphCanvas.qml
      graph/
        EdgeLayer.qml
        GraphInlinePropertiesLayer.qml
        GraphNodeHost.qml
        GraphNodeSurfaceMetrics.js
        GraphNodeSurfaceLoader.qml
        EdgeMath.js
        NodeCard.qml
        passive/
          FlowchartShapeCanvas.qml
          GraphAnnotationNoteSurface.qml
          GraphFlowchartNodeSurface.qml
          GraphMediaPanelSurface.qml
          GraphPlanningCardSurface.qml
        tabular/
          GraphTabularPreviewSurface.qml
          TabularDataGrid.qml
          TabularFullscreenSurface.qml
        surface_controls/
          GraphSurfaceButton.qml
          GraphSurfaceCheckBox.qml
          GraphSurfaceComboBox.qml
          GraphSurfaceInteractiveRegion.qml
          GraphSurfacePathEditor.qml
          GraphSurfaceTextArea.qml
          GraphSurfaceTextField.qml
          GraphSurfaceTextareaEditor.qml
          SurfaceControlGeometry.js
      graph_canvas/
        GraphCanvasBackground.qml
        GraphCanvasContextMenus.qml
        GraphCanvasDropPreview.qml
        GraphCanvasInputLayers.qml
        GraphCanvasLogic.js
        GraphCanvasMinimapOverlay.qml
      shell/
        ConnectionQuickInsertOverlay.qml
        GraphHintOverlay.qml
        GraphSearchOverlay.qml
        InspectorPane.qml
        LibraryWorkflowContextPopup.qml
        MainShellUtils.js
        NodeLibraryPane.qml
        ScriptEditorOverlay.qml
        ShellButton.qml
        ShellCollapsibleSidePane.qml
        ShellContextMenu.qml
        ShellCreateButton.qml
        ShellLabeledTabStrip.qml
        ShellRunToolbar.qml
        ShellStatusStrip.qml
        ShellTitleBar.qml
        WorkspaceCenterPane.qml
        icons/
          *.svg
  workspace/
    manager.py

tests/
docs/specs/
```

## Creating a Custom Node

Choose the smallest authoring surface that fits:

| Use | Best for | Update |
| --- | --- | --- |
| **Python Script** | One synchronous transform stored in one project | Click **Apply** |
| **Plugin** | Reusable Python function nodes | Validate, save, then **Reload Plugins** |
| **Custom Workflow** | Reusing an existing graph as a node | Save/reload the `.cxwf` |

For a reusable plugin, choose **File > New Plugin...**. COREX generates a
stable `custom.<slug>.<8-hex>` ID and a one-file template:

```python
import corex


@corex.node(
    id="custom.scale_value.1234abcd",
    name="Scale Value",
    category=("Custom", "Math"),
)
@corex.input("value", value_type=float, required=True)
@corex.number("factor", default=2.0, port=True)
@corex.output("result", value_type=float)
def scale_value(ctx, value, settings):
    return {"result": value * settings.factor}
```

The complete public module contains exactly `node`, `input`, `output`,
`text`, `text_area`, `number`, `switch`, `dropdown`, `slider`,
`color`, `path`, `interval`, `list`, `Any`, `Image`, `Color`, and
`Interval`. Public plugins do not import COREX internals.

Validation and reload parse source without executing it. A successful reload
copies validated files into an immutable content-addressed generation; public
code imports only inside the process worker. Connected `port=True` settings
override by input presence, so `None`, `False`, `0`, empty strings, and
empty containers remain real supplied values. `settings` is immutable,
`settings.to_dict()` returns a defensive mutable copy, functions return an
output mapping, and `ctx.warn(...)` publishes ordered warnings.

See the [Plugin Authoring Guide](docs/PLUGIN_AUTHORING_GUIDE.md) for the novice
workflow, declaration grammar, controls, reload rules, package schema, security
limits, and the executable
[Strain Conditioner](docs/examples/strain_conditioner_plugin.py) and
[Signal Plot-style](docs/examples/signal_plot_function_plugin.py) examples.
Python Script keeps its separate project-local, synchronous, Apply-driven
contract in the [Python Script Guide](docs/PYTHON_SCRIPT_GUIDE.md).

## Optional Add-ons

The shipped add-on backend exposes `Add-On Manager` as a top-level menubar
entry and ships the Variant 4 inspector-style drawer. Add-ons carry dependency
facts and exactly one apply policy (`hot_apply` or `restart_required`);
unavailable nodes stay visible as locked projections, and repo-local
`hot_apply` add-ons rebuild registry/runtime state when availability changes.
The retained evidence lives in the
[Add-On Manager Backend Preparation QA Matrix](docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md).

The dependency-gated Tabular Data add-on supports CSV, TSV, TXT, XLSX, XLSM,
Parquet, HDF5, NPY, and NPZ sources. It keeps large data behind bounded refs and
previews; selected columns/slices can feed generic `plot.*` nodes directly.
Install `.[tabular]` (or `.[all,dev]`) to enable it.

## Sharing Node Packages

Loose `.py` files live directly in
`%APPDATA%\COREX_Node_Editor\plugins\`. Use **File > Export Node Package...**
for a deterministic schema-2 `.cxpkg` when sharing a plugin or adding helper
sources/assets. Use **File > Import Node Package...** for validated atomic
installation and registry reload.

Schema 2 declares every root-level Python source and supported image asset with
a SHA-256 digest. It rejects unknown/undeclared members, unsafe paths, links,
encrypted entries, nested Python packages, unsupported assets, and bounded-size
violations. Schema 1 and the removed class/descriptor APIs are unsupported
without shims; follow the
[Plugin Migration Guide](docs/PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1).

Reload is refused while run/viewer work is active or when open graphs would
become incompatible. A refusal leaves files, registry consumers, graphs, and
workers unchanged. Missing bundled imports leave nodes visible but locked;
COREX does not install dependencies or mutate environments.

## Graphics Settings

- Open `Settings > Graphics Settings` to configure the grid overlay, minimap visibility/default expansion, snap-to-grid default, shell theme, graph-theme follow-shell behavior, and explicit graph-theme selection.
- Use `Manage Graph Themes...` to duplicate built-in graph themes into editable custom themes, edit node/edge/category-accent/port-kind tokens, and choose an explicit graph theme.
- Shell-theme changes apply live to QWidget styling and QML shell/canvas chrome surfaces. Node and edge visuals resolve through the active graph theme.
- Graph themes affect `NodeCard` and `EdgeLayer` only; background, grid, minimap, marquee, and drop-preview chrome stay on the shell theme path.
- App-wide graphics preferences, including the inline custom graph-theme library, persist in `%APPDATA%\COREX_Node_Editor\app_preferences.json` and stay separate from project `.cxproj` files and `last_session.json`.

## Passive Visual Authoring

- Passive flowchart, planning, annotation, image, and PDF nodes stay in the normal workspace graph and save into the same `.cxproj` document as executable nodes.
- Passive visual nodes now share the same four logical-flow handles (`top`, `right`, `bottom`, `left`) for presentation-only `flow` authoring across flowchart, planning, annotation, and media families.
- `flow` edges are presentation-only graph connections. They support labels, branch styling, and multi-incoming targets where the target port spec allows it, but they do not reach the compiler or worker runtime graph.
- Passive nodes render through the graph host/factory path, which keeps standard `NodeCard` contracts stable while loading specialized flowchart, planning, annotation, and media surfaces.
- Right-click a passive node or `flow` edge to edit style overrides, copy/paste them, reset to defaults, or save them as project-local presets stored under `metadata.ui.passive_style_presets`.
- Image and PDF panels resolve local filesystem sources only. PDF panels intentionally stay in single-page preview mode.

## Running Tests

```powershell
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast
```

Use the repo-owned runner for the default day-to-day loop. It keeps the
`fast`, `gui`, `slow`, and `full` workflow stable, applies
`QT_QPA_PLATFORM=offscreen` to its child verification commands, and keeps the
shell-backed suites on a dedicated fresh-process shell-isolation phase in
`full` mode. The `gui` and `full` modes run the authoritative pure-QML Qt Quick
Test phase before their Python GUI tests; `fast` and `slow` do not require a Qt
SDK.

For `gui` and `full`, install a Qt Quick Test SDK whose Qt major/minor matches
the PyQt runtime, then either put `qmltestrunner` on `PATH` or set `QT_ROOT` to
the Qt installation root. Patch-level drift is accepted. A missing runner,
missing sibling `qtpaths6`/`qtpaths`, or major/minor mismatch is a hard error
for real runs; `--dry-run` instead prints a placeholder command and setup note.

If the project venv has a partial `pytest` install and early startup fails
with `ModuleNotFoundError` for a direct `pytest` dependency such as
`iniconfig` or `exceptiongroup`, run any `scripts/run_verification.py` mode
once. The runner now repairs the missing package in `venv` before launching
the requested phase.

Inspect or run the full workflow with:

```powershell
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full
```

When you change verification docs, release docs, or packet-owned proof links,
audit them with:

```powershell
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
```

The canonical script paths remain `scripts/check_traceability.py` and
`scripts/check_markdown_links.py`; the PowerShell form simply prefixes them
with `.\`.

- The current architecture/docs closeout evidence is summarized in
  `ARCHITECTURE.md`, `docs/specs/INDEX.md`,
  `docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md`,
  `docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md`,
  `docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md`, and
  `docs/specs/requirements/TRACEABILITY_MATRIX.md`.
- `fast` runs in two phases. The `fast.pytest` phase targets
  `pytest -m "not gui and not slow"` and, when `pytest-xdist` is available in
  the project venv, resolves an explicit worker count as
  `psutil.cpu_count(logical=True)`, else `os.cpu_count()`, else `1`, then
  passes `-n <resolved_count> --dist load` while deselecting known
  xdist-sensitive fast targets. The `fast.serial.pytest` phase then runs those
  targets serially.
- The repo-owned runner also preflights the project venv's direct `pytest`
  dependencies before phase execution. If a package such as `iniconfig` or
  `exceptiongroup` is missing, it installs the missing dependency into `venv`
  and retries automatically.
- Direct `.\venv\Scripts\python.exe -m pytest` runs now auto-enable xdist for
  the safe non-GUI path and focused `tests/test_shell_isolation_phase.py`
  reruns. Broad invocations default to the same `not gui and not slow` slice,
  excluding the serial-fast paths; focused GUI, slow, serial-fast, or direct
  shell-backed module targets stay off that automatic parallel path.
- `gui` and `slow` keep the QML-heavy phases explicit:
  `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui` and
  `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode slow`.
  `gui` first runs `qmltestrunner -input tests/qml_quick` with offscreen/Basic
  controls and zero input delays, then runs the parallel Python GUI pytest
  slice with `-n <gui_resolved_count> --dist load` when `pytest-xdist` is
  available, where `<gui_resolved_count>` is capped at `6` workers. It then
  runs `gui.serial.pytest`: one graph-surface selector, one DOCX selector, and
  `tests/test_viewer_surface_contract.py`, which are isolated from Windows
  Qt/xdist contention. `slow` remains serial by design.
- `full` runs the fast xdist-safe phase, fast serial phase, native QuickTest
  phase, parallel Python GUI phase, serial GUI phase, and slow phase first, then executes
  `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest -o faulthandler_timeout=330 --ignore=venv tests/test_shell_isolation_phase.py -q -n 4 --dist load`
  as the dedicated shell-isolation phase when `pytest-xdist` is available. The
  manifest-owned four-worker cap keeps the 47 parametrized targets bounded;
  each target still launches its own fresh child process with a 360-second hard
  timeout, while pytest's 330-second faulthandler timeout provides diagnostics.
  Those targets span
  the `tests.test_main_window_shell`, `tests.test_script_editor_dock`,
  `tests.test_shell_run_controller`, and
  `tests.test_shell_project_session_controller` catalogs; without
  `pytest-xdist`, the same phase falls back to serial pytest and preserves the
  fresh-process model. The manifest-owned contract for that phase now lives in
  `scripts/verification_manifest.py` (`SHELL_ISOLATION_SPEC` plus
  `SHELL_ISOLATION_CATALOG_SPECS`) and is executed through
  `tests/shell_isolation_runtime.py`.
- The direct module-level shell `unittest` commands listed in
  `docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md` remain supported for
  focused reruns outside the published `full` workflow.
- See `docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md` for the approved mode
  shapes, dedicated shell-isolation phase, benchmark evidence, companion
  proof-audit command, and current baseline-status notes.

Focused graph-surface regression gate in PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m unittest `
  tests.test_graph_surface_input_contract `
  tests.test_graph_surface_input_inline `
  tests.test_passive_graph_surface_host `
  tests.test_passive_image_nodes -v
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

## Interaction Notes

- Graphics settings are app-wide rather than project-local, so reopening the app restores the last saved grid/minimap/snap/theme choices.
- Standalone graph-theme editing previews only apply live when the edited theme is already the active explicit custom theme; Graph Themes opened from Graphics Settings do not mutate the running graph until Graphics Settings is accepted.
- Drag from a port to empty canvas space to open the connection-aware quick insert overlay.
- Quick insert only shows node types that can auto-connect to the dragged source port using the same compatibility rules as normal graph connections.
- Some node types expose inline property controls directly in the node card for faster editing, while the inspector remains the full editing surface.
- Graph Search is intentionally user-facing: it matches node titles, node types, safe note-like content, and exposed port labels, not internal runtime IDs.
- Inspector header metadata uses sequential per-type IDs for orientation, while internal node IDs stay implementation-only.
- The passive-node reference workspace used for manual visual checks lives at `tests/fixtures/passive_nodes/reference_flowchart.cxproj`.

## Building a Windows Installer

Build Windows releases from PowerShell using the project-local virtual
environment and the repo packaging scripts:

```powershell
# From a fresh clone
py -3.10 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e ".[all,dev]"

# Build the default/base packaged app bundle
.\scripts\build_windows_package.ps1 -PackageProfile base -Clean

# Wrap that bundle into the distributable installer package
.\scripts\build_windows_installer.ps1 -PackageProfile base
```

Key outputs:

- Packaged app bundle:
  `artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe`
- Installer bundle zip:
  `artifacts\releases\installer\base\<runId>\COREX_Node_Editor_installer_bundle_<runId>.zip`

Notes:

- Use `venv\Scripts\python.exe`; the packaging scripts expect the project-local
  Windows-style virtual environment.
- This is a one-folder PyInstaller build, not a single-file standalone `.exe`.
- `build_windows_package.ps1` runs an offscreen startup smoke test by default.
  The smoke enables startup autoquit and fails on timeout, startup error dialog,
  or nonzero exit. Add `-SkipSmoke` only when you intentionally need to bypass
  it.
- Keep the same `-PackageProfile` across all packaging steps. The default
  profile is `base`.

Viewer packaging uses the same flow with `-PackageProfile viewer`:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile viewer -Clean -SkipSmoke
.\scripts\build_windows_installer.ps1 -PackageProfile viewer
```

The `viewer` profile requires the optional viewer/runtime imports to exist in
the project venv, including `pyvista`, `pyvistaqt`, and `vtk`.

Full developer-style packaging uses `-PackageProfile full` from a venv with
`.[all,dev]` or `.[dev]` installed:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile full -Clean -SkipSmoke
.\scripts\build_windows_installer.ps1 -PackageProfile full
```

The `full` profile requires every current application runtime extra, including
PyMechanical, viewer/plot backends, tabular data backends, Excel, HPC, web, and
media. Ansys DPF is excluded from every application package profile; its
optional dependency is retained only for standalone engineering utilities.
Missing optional runtime imports fail the package build instead of silently
producing a dependency-gated app.

There is no separate tabular packaging profile. Build from a venv with
`.[tabular]`, `.[all,dev]`, or `.[dev]` installed when the base packaged app
should expose `Data > Tabular Data Input`; otherwise the add-on remains visible
only as dependency-gated unavailable metadata.

Optional code signing happens after the installer bundle is created:

```powershell
$env:EA_SIGN_CERT_THUMBPRINT = "YOUR_CERT_THUMBPRINT"
$env:EA_SIGN_TIMESTAMP_URL = "https://your.timestamp.server"
$env:EA_SIGN_REQUIRE_SIGNED = "1"
.\scripts\sign_release_artifacts.ps1 -PackageProfile base
```

For the full packaging reference, installer layout, and signing details, see
[docs/PACKAGING_WINDOWS.md](docs/PACKAGING_WINDOWS.md).

Regenerate the committed app icon asset set with:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_app_icons.py
```

## Documentation

- [Getting Started](docs/GETTING_STARTED.md) -- environment setup, first launch, smoke checks, and common paths
- [Plugin Authoring Guide](docs/PLUGIN_AUTHORING_GUIDE.md) -- novice reusable-node tutorial, public API, schema 2, security rules, and examples
- [Plugin Migration Guide](docs/PLUGIN_MIGRATION_GUIDE.md) -- clean-break legacy and schema-1 migration
- [Python Script Guide](docs/PYTHON_SCRIPT_GUIDE.md) -- project-local synchronous script declarations and Apply workflow
- [Architecture Guide](ARCHITECTURE.md) -- runtime/component architecture and flow maps
- [Architecture Diagrams](docs/architecture_diagrams/) -- generated Mermaid exports (`.mmd`, `.svg`, `.png`)
- [Spec Pack Index](docs/specs/INDEX.md) -- requirements, ADRs, traceability
- [Release Notes](RELEASE_NOTES.md) -- shipped capabilities and known risks
- [Pilot Runbook](docs/PILOT_RUNBOOK.md) -- validation steps for pilot deployments
- [Architecture Maintainability Refactor QA Matrix](docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md) -- current docs/release guardrails, shell-isolation contract, historical pointers, and Windows-only follow-ups
- [COREX Architecture Modernization QA Matrix](docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md) -- final `P00` through `P12` closeout proof for the headless Corex kernel, QML shell client, strict current `.cxproj`, explicit extension contracts, execution backend policy, full verification, and residual risks
- [COREX Clean Architecture Restructure QA Matrix](docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md) -- retained P01-P12 ownership, verification, residual-risk, and closeout evidence for the clean architecture restructure
- [COREX No-Legacy Architecture Cleanup QA Matrix](docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md) -- active no-legacy architecture closeout proof for focused bridges, current-schema persistence, descriptor-only loading, snapshot-only runtime payloads, typed viewer transport, and canonical launch/import paths
- [Add-On Manager Backend Preparation QA Matrix](docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md) -- current add-on catalog, Variant 4 manager, locked projection, and Tabular/MARS evidence
- [Hybrid Direct Tabular Auto-Plotting QA Matrix](docs/specs/perf/HYBRID_DIRECT_TABULAR_AUTO_PLOTTING_QA_MATRIX.md) -- direct `TabularDataRef` / `ArrayDataRef` plotting proof and residual risks
- [Passive Visual Checklist](docs/specs/perf/PASSIVE_NODES_VISUAL_CHECKLIST.md) -- short manual pass for passive flowchart/media styling and reopen checks
- [Graph Surface Input QA Matrix](docs/specs/perf/GRAPH_SURFACE_INPUT_QA_MATRIX.md) -- current host/inline/media/shell coverage and shell-module verification status
- [Verification Speed QA Matrix](docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md) -- approved `fast`/`gui`/`slow`/`full` workflow, dedicated shell-isolation phase, benchmark evidence, proof-audit command, and baseline-status notes
- [Nested Node Categories QA Matrix](docs/specs/perf/NESTED_NODE_CATEGORIES_QA_MATRIX.md) -- retained SDK, registry, library, QML, manual, and traceability evidence for `category_path` node authoring
- The Spec Pack Index lists the retained work-packet manifests, status ledgers, and closeout QA matrices that remain canonical on this branch.

Regenerate architecture diagrams after updating Mermaid blocks in `ARCHITECTURE.md`:

```powershell
.\venv\Scripts\python.exe .\scripts\export_architecture_diagrams.py
```

The exporter writes `.mmd`, `.svg`, and `.png` assets into `docs/architecture_diagrams/` and uses the Kroki Mermaid rendering service, so it requires network access.
