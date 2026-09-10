# COREX Node Editor - Release Candidate Notes

Date: `2026-05-03`

## Shipped Capabilities

- Core editor shell/workspaces/views, graph model, node SDK, execution engine, persistence, and integration nodes (Tracks A-H).
- App-wide Graphics Settings modal for grid, minimap, snap-to-grid default, shell-theme selection, graph-theme follow-shell or explicit selection, and graph-theme manager access.
- Dedicated graph-theme pipeline for node/edge visuals: `ThemeBridge` keeps shell/canvas chrome on `stitch_dark` / `stitch_light`, while `graphThemeBridge` resolves built-in and custom graph themes for `NodeCard`, `EdgeLayer`, and graph payload presentation.
- Custom graph-theme library/editor with built-in read-only themes, custom duplication/CRUD, inline token editing, and live apply when editing the active explicit custom theme.
- Versioned `app_preferences.json` persistence for graphics, shell-theme, and graph-theme preferences, kept separate from project `.cxproj` data and `last_session.json`.
- Passive visual authoring families for flowchart, planning, annotation, and local media panels, all stored in the existing workspace graph model.
- Shared header inline node-title editing across standard, passive, collapsed, and scope-capable node shells, using the same rename/history mutation path and preserving a dedicated `OPEN` badge for scope entry on subnode shells.
- Passive `flow` edge routing, labels, and style overrides with runtime exclusion from compiler/worker execution.
- Project-local passive node and flow-edge style presets persisted inside `.cxproj` metadata.
- Local image preview panels and single-page local PDF preview panels on the passive media surface path.
- Add-On Manager with repo-local `hot_apply` add-ons, dependency facts, unavailable-add-on projections, and rebuild-based lifecycle refresh for shipped add-ons.
- Dependency-gated `Data > Tabular Data Input` node for CSV, TSV, TXT, XLSX, XLSM, Parquet, HDF5, NPY, and NPZ sources, using lazy `TabularDataRef` / `ArrayDataRef` outputs, bounded inline/fullscreen previews, persisted selected-column/slice hints, and direct generic plot-node auto-mapping.
- Reference passive workspace fixture and manual visual checklist for reopen, preset, and media-preview verification.
- Full automated QA gate coverage (`unittest` suite) and offscreen performance harness reporting.
- Windows PyInstaller packaging pipeline:
  `ea_node_editor.spec` + `scripts/build_windows_package.ps1`.
- Packaging operator documentation and RC packaging evidence report.

## Gigabyte-Scale Tabular & Plot Performance (2026-06-11)

- Tabular sources now flow through one shared, thread-safe loader service with parquet-first ingestion: text/Excel sources convert once (chunked pyarrow, off the UI thread) into the managed parquet cache, and every preview window, sort/filter/search query, and plot read uses parquet or arrow compute. Open never scans rows; row counts backfill from cache metadata.
- Plot nodes connected to tabular data render decimated series (min-max envelope / stride sampling, <=4000 points per series - visually lossless for line plots at canvas resolution; each series carries `decimation` metadata). The Data Export port still streams every source row. **Behavior change:** static image exports of very dense series may differ at sub-pixel level from previous releases; an explicit `tabular_mapping.row_limit` remains a hard source-row cap.
- Scene payload rebuilds do zero tabular I/O: plot auto-previews publish a staleness signature and resolve asynchronously; tabular previews show a loading state while gigabyte caches build in the background. The legacy `preview_series` plot property was removed and is stripped from legacy projects on load/save.
- Measured on the 400k-row / 30 MB reference workflow: project load 95 s -> <1 s, save 25 s -> 72 ms, scene rebuild 17.6 s -> 17 ms, node move 42 s -> ~20 ms, plot fullscreen open 47 s -> <100 ms warm. A 1 GB / 8.8M-row CSV loads with the UI interactive immediately; warm deep-page reads land in ~20 ms.

## Known Risks

- Performance baselines in CI/automation are offscreen and may differ from desktop GPU/compositor behavior.
- Packaging smoke test validates startup/liveness only; it is not a full interactive UI acceptance run.
- Shell-theme and graph-theme coverage are automated and offscreen in repo validation; real-display visual sign-off still matters for packaged builds.
- Passive media panels intentionally accept local filesystem sources only, and PDF scope remains single-page preview rather than a full reader/editor.
- Passive-only workspaces are presentation artifacts; `Run` intentionally ignores passive nodes and `flow` edges.
- Signing scripts are present, but signed release artifacts still require a local certificate thumbprint and timestamp service configuration.
- Excel and Tabular Data paths remain runtime dependency-gated when their optional Python packages are not installed; direct tabular plotting needs the tabular loader stack available at runtime so plot nodes can reopen refs.

## Run and Build Commands

- Run the normal regression slice:
  `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast`
- Inspect or run the full verification workflow:
  `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run`
  `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full`
- Run the focused graph-surface regression gate:
  `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m unittest tests.test_graph_surface_input_contract tests.test_graph_surface_input_inline tests.test_passive_graph_surface_host tests.test_passive_image_nodes -v`
- Run benchmark harness:
  `.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness`
- Run app from source:
  `.\venv\Scripts\python.exe -m ea_node_editor.bootstrap`
- Build Windows package (+default smoke):
  `.\scripts\build_windows_package.ps1 -PackageProfile base -Clean`
- Build only (skip smoke):
  `.\scripts\build_windows_package.ps1 -PackageProfile base -Clean -SkipSmoke`
