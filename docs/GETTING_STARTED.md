# Getting Started

This guide is the fastest way to get COREX Node Editor running locally with the
current Windows-first workflow.

## Prerequisites

- Windows 10 or Windows 11
- Python 3.10 or newer
- Git
- Network access for `pip install` and optional architecture-diagram export

## Local Setup

From the repository root:

```powershell
py -3.10 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e ".[all,dev]"
```

Notes:

- `.[all,dev]` installs the optional spreadsheet, Ansys, viewer, and tabular dependencies, including PyMechanical, PyVista, DuckDB, Pandas, Polars, PyArrow, and PyTables, plus dependencies for standalone engineering utilities and the local dev tools used in this repo.
- QWebEngine-backed nodes such as `Excalidraw Board` and `Web Page Viewer` require a working `PyQt6-WebEngine` install. If they show a `QtWebEngineCore` DLL-load fallback after copying the repo to another machine or intranet share, follow [`docs/QT_WEBENGINE_INSTALLATION.md`](./QT_WEBENGINE_INSTALLATION.md).
- If you only need the dependency-gated `Data > Tabular Data Input` node, install `.[tabular]` instead. On Python 3.10, that extra intentionally resolves `tables>=3.10.1,<3.11`; Python 3.11+ uses `tables>=3.11`.
- The repo uses a Windows-style virtualenv layout even when opened from `bash`, so prefer `./venv/Scripts/python.exe` over a shell-default `python`.
- The examples below use native PowerShell path syntax. If you are in `bash`, use the same interpreter path with `./venv/Scripts/python.exe`.
- Editable install also exposes the `corex-node-editor` console entry point inside `venv/Scripts/`.

## First Launch

Start the application from the repository root:

```powershell
.\venv\Scripts\python.exe -m ea_node_editor.bootstrap
```

This package-module command is the source/dev launch path. Editable installs
also expose `.\venv\Scripts\corex-node-editor.exe`, which maps to
`ea_node_editor.bootstrap:main`. If you need a packaged Windows build that opens
without the repository checkout, follow
[`docs/PACKAGING_WINDOWS.md`](./PACKAGING_WINDOWS.md).

You should see:

- The QML main shell with library, canvas, inspector, workspace tabs, and console areas
- The default shell theme and graph theme resolved from `app_preferences.json`
- An empty workspace ready for either executable nodes or passive visual nodes
- `Data > Tabular Data Input` in the node library when the optional tabular stack is installed; its table/array refs can connect directly to generic `plot.*` nodes, and its preview/fullscreen surface can Save As the visible table preview or array slice

### Authoring dataflow and dynamic ports

Active nodes use ordinary data dependencies. Connect an output to an input to
set evaluation order; hold Shift while connecting to append another ordered
input source. Passive canvas objects keep their unrelated `flow` connectors.

Stream Gate uses metadata-driven dynamic-port controls. Inline Add, Remove, and
Rename controls appear only while the graph is writable, the node is unlocked
and expanded, and zoom is at least `0.95`. Right-click a dynamic port for Insert
Before, Insert After, Rename, or Remove. The node context menu keeps Add Output
available at low zoom and for a zero-port group. These controls have separate
connector and action hit targets, tooltips, Tab focus with standard keyboard
activation, and accessible names. There is no standalone port reorder action.

Insert Python Script directly from the library like any other registered node;
there is no creation wizard or generated-plugin step. Declare its named inputs,
outputs, and controls in the shared script editor, then click **Apply**; the
canvas does not author Python Script ports. Follow the
[Python Script guide](PYTHON_SCRIPT_GUIDE.md) for the copyable decorator form.
Explicit Run, confirmed Run Selected, and a Trigger click first apply a valid
dirty script draft before building the runtime snapshot. A failed Apply aborts
the dispatch without a partial graph mutation. Auto runs always use the applied
model and never consume an unsaved draft.

For a packaged build, the validated base flow is:

```powershell
.\scripts\build_windows_package.ps1 -PackageProfile base -Clean
```

That command writes the packaged app under
`artifacts\pyinstaller\dist\base\COREX_Node_Editor\` and runs the packaged exe
under `QT_QPA_PLATFORM=offscreen` with startup autoquit enabled. The smoke must
exit cleanly before its timeout, so modal startup error dialogs fail the build.

## Useful First Checks

Start an implementation with the smallest route-owned test that proves the
changed behavior. Use `scripts/nav.py` to find the owning tests and commands:

```powershell
.\venv\Scripts\python.exe .\scripts\nav.py find <feature-or-test-term>
.\venv\Scripts\python.exe -m pytest <affected-test-or-node-id> --ignore=venv -q
```

Run the owning route suite once after the last related task when adjacent proof
is useful. The verification runner modes are broader integration lanes: use
`fast` for cross-route or shared-infrastructure changes, `gui` for broad
multi-surface QML work, `slow` for performance closeout, and `full` for
shell-wide composition or release confidence. Focused UI, performance, and
shell fixes should run their exact tests, benchmark, or shell target instead.
The `gui` and `full` modes start with the authoritative pure-QML Qt Quick Test
phase; `fast` and `slow` remain independent of the external Qt SDK.

Before a real `gui` or `full` run, install a Qt Quick Test SDK whose Qt
major/minor matches the project PyQt runtime and either put `qmltestrunner` on
`PATH` or set `QT_ROOT` to the Qt installation root. Patch-only version drift
is accepted. Missing or mismatched tooling stops a real run; `--dry-run`
remains available and prints a placeholder command plus setup guidance.

If the project venv has a partial `pytest` install and startup dies with
`ModuleNotFoundError` for a direct dependency such as `iniconfig` or
`exceptiongroup`, rerun one of the `scripts/run_verification.py` modes. The
runner now repairs the missing package in `venv` before invoking `pytest`.

For shell-wide or release work, inspect or run the full workflow:

```powershell
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full
```

- After editing packet-owned verification docs, perf reports, or traceability
  links, run `.\venv\Scripts\python.exe .\scripts\check_traceability.py` to audit
  the proof layer.
- After editing canonical markdown docs or spec-index links, run
  `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` to catch broken
  local references before handoff.
- The canonical script paths remain `scripts/check_traceability.py` and
  `scripts/check_markdown_links.py`; the PowerShell form simply prefixes them
  with `.\`.
- The current architecture/docs closeout evidence is summarized in
  `ARCHITECTURE.md`, `docs/specs/INDEX.md`,
  `docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md`,
  `docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md`,
  `docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md`,
  `docs/specs/perf/NESTED_NODE_CATEGORIES_QA_MATRIX.md`, and
  `docs/specs/requirements/TRACEABILITY_MATRIX.md`.
- The runner applies `QT_QPA_PLATFORM=offscreen` to its child verification
  commands.
- The native `gui.qml_quick` phase also applies
  `QT_QUICK_CONTROLS_STYLE=Basic`, runs `tests/qml_quick` with zero event/key/
  mouse delays, and precedes the parallel Python GUI pytest and serial GUI
  pytest phases in `gui` and `full`.
- The runner also preflights the project venv's direct `pytest` dependencies.
  If a package such as `iniconfig` or `exceptiongroup` is missing, it installs
  the missing dependency into `venv` and retries automatically before phase
  execution.
- Direct `.\venv\Scripts\python.exe -m pytest` now auto-parallelizes the safe
  non-GUI path and focused `tests/test_shell_isolation_phase.py` reruns. Broad
  invocations default to the `not gui and not slow` slice, while focused GUI,
  slow, serial-fast, and direct shell-backed module targets stay off that
  automatic parallel path.
- `fast` runs as `fast.pytest` plus `fast.serial.pytest`. The first phase uses
  `-n <resolved_count> --dist load` when `pytest-xdist` is installed in the
  project venv and deselects known xdist-sensitive fast targets; the second
  phase runs those targets serially. `<resolved_count>` resolves as
  `psutil.cpu_count(logical=True)` when available, else `os.cpu_count()`,
  else `1`.
- `gui` runs native QuickTest first, then parallel Python GUI pytest using the
  same worker-resolution path capped at `6`. It finishes with
  `gui.serial.pytest`, which owns one graph-surface selector, one DOCX selector,
  and `tests/test_viewer_surface_contract.py` because Windows Qt/xdist
  contention makes those targets unreliable in the parallel slice.
- When `pytest-xdist` is unavailable, all xdist-enabled phases fall back to
  serial pytest automatically and the runner prints the notice.
- `full` keeps the fast, serial-fast, native QuickTest, parallel Python GUI,
  serial GUI, and slow phases first, then runs
  `tests/test_shell_isolation_phase.py` as the dedicated fresh-process
  shell-isolation phase. Its manifest-owned four-worker cap bounds the 47
  targets; pytest's 330-second faulthandler timeout supplies diagnostics before
  each child process's 360-second hard timeout. The target catalogs cover the
  shell-backed suites from `tests.test_main_window_shell`,
  `tests.test_script_editor_dock`, `tests.test_shell_run_controller`, and
  `tests.test_shell_project_session_controller`.
- The direct module-level shell `unittest` commands remain supported for
  focused manual reruns, but they are no longer the documented `full`
  workflow.
- The previously documented serializer spot-check
  `.\venv\Scripts\python.exe -m pytest tests/test_serializer.py -k passive_image_panel_properties_and_size -q`
  now passes in the project venv, so the QA matrix no longer carries that
  caveat as an open out-of-scope baseline.

If you only need the graph-surface gate:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m unittest `
  tests.test_graph_surface_input_contract `
  tests.test_graph_surface_input_inline `
  tests.test_passive_graph_surface_host `
  tests.test_passive_image_nodes -v
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Manual passive-media fixture:

- Open `tests/fixtures/passive_nodes/reference_flowchart.cxproj` to check passive nodes, `flow` edges, and local image/PDF preview behavior.

## Common Paths

- User data directory: `%APPDATA%\COREX_Node_Editor\`
- Plugin directory root: `%APPDATA%\COREX_Node_Editor\plugins\`
- App-wide graphics preferences: `%APPDATA%\COREX_Node_Editor\app_preferences.json`
- Session state: `%APPDATA%\COREX_Node_Editor\last_session.json`
- Autosave project: `%APPDATA%\COREX_Node_Editor\autosave.cxproj`

## Plugins and Node Packages

- Choose **File > New Plugin...** to create a reusable function node. The
  editor generates one stable `custom.<slug>.<8-hex>` ID, validates source
  without executing it, and saves a direct-child `.py` file under
  `%APPDATA%\COREX_Node_Editor\plugins\`.
- Public source imports only `corex`. It declares top-level functions with
  `corex.node`, inputs, outputs, and controls; the full API and copyable Strain
  Conditioner tutorial are in the
  [Plugin Authoring Guide](PLUGIN_AUTHORING_GUIDE.md).
- Click **Validate**, **Save**, then **Reload** in the editor, or choose
  **File > Reload Plugins** after an external edit. A successful reload pins an
  immutable source generation for process-worker execution. Incompatible open
  graphs or active run/viewer work refuse reload without partial mutation.
- Use **File > Export Node Package...** and **Import Node Package...** for
  deterministic schema-2 `.cxpkg` files. Multi-file packages may contain
  root-level Python helpers and declared `.svg`, `.png`, `.jpg`, or `.jpeg`
  assets. Schema 1 is unsupported; use the
  [Plugin Migration Guide](PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1).
- Missing bundled imports keep declared nodes visible but locked. COREX does
  not install plugin dependencies or mutate an environment.
- Python Script remains project-local and Apply-driven; Custom Workflows reuse
  graphs. The [extension chooser](PLUGIN_AUTHORING_GUIDE.md#choose-the-right-extension)
  compares all three.

## Repo Orientation

- [README.md](../README.md): top-level feature summary, structure map, and doc links
- [ARCHITECTURE.md](../ARCHITECTURE.md): runtime architecture, QML composition, and Mermaid diagrams
- [docs/agent_maps/INDEX.md](./agent_maps/INDEX.md): agent/human lookup atlas for subsystem owners, feature routes, focused tests, and maintenance triggers
- [docs/specs/INDEX.md](./specs/INDEX.md): canonical requirements, ADRs, and traceability
- [docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md](./specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md): retained P01-P12 ownership, verification, residual-risk, and closeout evidence for the clean architecture restructure
- [docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md](./specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md): active no-legacy architecture closeout proof for canonical launch/import paths and retired compatibility seams
- [docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md](./specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md): historical pointer retained for older release-doc guardrails
- [docs/specs/perf/PASSIVE_NODES_VISUAL_CHECKLIST.md](./specs/perf/PASSIVE_NODES_VISUAL_CHECKLIST.md): short manual passive-node validation pass
- [docs/specs/perf/GRAPH_SURFACE_INPUT_QA_MATRIX.md](./specs/perf/GRAPH_SURFACE_INPUT_QA_MATRIX.md): current graph-surface regression matrix and shell-module verification status
- [docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md](./specs/perf/VERIFICATION_SPEED_QA_MATRIX.md): approved verification-runner modes, dedicated shell-isolation phase, benchmark evidence, proof-audit command, and baseline-status notes
- [docs/specs/perf/NESTED_NODE_CATEGORIES_QA_MATRIX.md](./specs/perf/NESTED_NODE_CATEGORIES_QA_MATRIX.md): retained automated and manual evidence for the `category_path` node-authoring rollout
- [docs/specs/perf/HYBRID_DIRECT_TABULAR_AUTO_PLOTTING_QA_MATRIX.md](./specs/perf/HYBRID_DIRECT_TABULAR_AUTO_PLOTTING_QA_MATRIX.md): follow-up proof for direct tabular/array refs feeding generic plot nodes
- `docs/specs/INDEX.md` lists the retained work-packet manifests, status ledgers, and closeout QA matrices that stay canonical on this branch.

## Updating Architecture Diagrams

The generated architecture assets under `docs/architecture_diagrams/` come from
the Mermaid blocks in `ARCHITECTURE.md`.

Regenerate them with:

```powershell
.\venv\Scripts\python.exe .\scripts\export_architecture_diagrams.py
```

That exporter writes `.mmd`, `.svg`, and `.png` files and uses the Kroki
Mermaid rendering service, so it requires network access.
