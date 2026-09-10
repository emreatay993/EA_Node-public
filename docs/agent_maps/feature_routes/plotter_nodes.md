# Plotter Nodes

## Purpose
Use this for plotter node planning, backend registry/static export work, generic node family routing, direct and extraction-ref tabular auto-plotting, display surfaces, packet docs, and retained plan paths.

## Start Here
- `ea_node_editor/execution/plot_backend.py`
- `ea_node_editor/execution/plot_backend_matplotlib.py`
- `ea_node_editor/execution/plot_backend_pyqtgraph.py`
- `ea_node_editor/execution/plot_backend_pyvista.py`
- `ea_node_editor/app_preferences.py`
- `ea_node_editor/ui/dialogs/graphics_settings_dialog.py`
- `ea_node_editor/ui_qml/graph_canvas_state/`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui_qml/plot_host_service.py`
- `ea_node_editor/ui_qml/plot_auto_preview_service.py` — async render-request builds + shared cache
- `ea_node_editor/execution/plot_series_decimation.py` — min-max envelope / stride sampling contract
- `ea_node_editor/nodes/builtin_functions/plot_signal.py` — inert decorated Signal Plot declaration and worker function
- `ea_node_editor/execution/signal_plot_renderer.py` — Signal Plot validation and ImageValue rendering
- `ea_node_editor/execution/signal_plot_inputs.py` — aligned read-only scientific/ref X/Y normalization
- `ea_node_editor/nodes/builtins/plot/signal_schema.py` — zero-I/O schema suggestions for shared property editors
- `scripts/generate_signal_plot_scientific_example.py`
- `scripts/benchmark_signal_plot.py`
- `docs/SIGNAL_PLOT_GUIDE.md`
- `ea_node_editor/ui_qml/plot_widget_binder.py`
- `ea_node_editor/ui_qml/components/graph/plot/GraphPlotSurface.qml`
- `ea_node_editor/ui_qml/components/graph/plot/GraphPlotSurfaceBody.qml`
- `ea_node_editor/persistence/project_codec.py`
- `ea_node_editor/persistence/migration.py`
- `ea_node_editor/graph/project_state.py`
- `ea_node_editor/addons/catalog.py`
- `ea_node_editor/nodes/builtins/plot/`
- `ea_node_editor/addons/tabular_data/`
- `ea_node_editor/nodes/bootstrap.py`
- `examples/tabular_plot_showcase.README.md`
- `examples/tabular_plot_showcase_direct.cxproj`
- `pyproject.toml`
- `ea_node_editor/nodes/builtins/`
- `ea_node_editor/ui_qml/components/graph/`
- `tests/test_plot_surface_integration.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_plot_node_contracts.py tests/test_plot_headless_export.py tests/test_registry_validation.py tests/test_passive_runtime_wiring.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_plot_backend_registry.py tests/test_plot_headless_export.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_inspector_projection.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_plot_node_contracts.py tests/test_passive_runtime_wiring.py --ignore=venv -q
$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_graphics_settings_preferences.py tests/test_graphics_settings_dialog.py tests/graph_track_b/qml_preference_bindings.py tests/test_plot_node_contracts.py --ignore=venv -q; $exitCode = $LASTEXITCODE; Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; exit $exitCode
$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_plot_preview_cache_provider.py tests/test_plot_widget_binder.py tests/test_plot_host_service.py tests/test_plot_surface_integration.py tests/test_plot_fullscreen_overlay.py tests/test_graph_surface_input_contract.py --ignore=venv -q; $exitCode = $LASTEXITCODE; Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; exit $exitCode
$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_plot_backend_registry.py tests/test_plot_detached_window.py tests/test_plot_surface_integration.py tests/test_plot_headless_export.py --ignore=venv -q; $exitCode = $LASTEXITCODE; Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; exit $exitCode
```

## Breadcrumbs
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)
- [Add-ons](../subsystems/addons.md)
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [Packaging And Generated Assets](../subsystems/packaging_generated_assets.md)
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [Retained Work-Packet QA Evidence And Spec Navigation](work_packet_docs_status_qa.md)

## Surface Ownership Notes
- Signal Plot is the sole function-SDK plot conversion: its full grouped-control contract is statically parsed from the internal inert source and executed through the verified function bundle, while rendering remains execution-owned. The eight generated generic plots remain trusted descriptors.
- The generic family contains eight retained nodes; `plot.line` is removed without alias or migration. Retained generic line-oriented fixtures use `plot.scatter`.
- `scripts/benchmark_signal_plot.py` owns full-resolution Matplotlib-versus-XY rendering and the separate scientific process/CorexRuntime workload. `--scientific --rows 2000000` records initial/repeated elapsed time, combined process RSS, all source samples, reduction counts and actual recomputation reasons. The trusted-fixture 64 MiB reuse gate is in `tests/test_signal_plot_scientific_integration.py`; retained measurements live in `docs/specs/perf/SIGNAL_PLOT_SCIENTIFIC_INPUTS_QA.md`.
- Signal Plot consumes immutable scientific values, numeric trees/matrices and table/array/window/slice refs through `signal_plot_inputs.py`. Shared column IO remains tabular-owned. The default 4000-point reduction is per rendered trace; zero is full resolution, gaps remain gaps, and source values are never reduced. Generic plot defaults remain independent.
- Signal data controls enter the early Signal branch of `PlotPropertyEditAdapter`. `signal_schema.py` enriches selectors from cached metadata/current accepted outputs only; the shared registered adapter route projects the same result to Inspector and canvas. It never opens a source or executes a script. Exact string names and integer positions retain their types through shared enum/list label-code fields.
- `PlotHostService` retargets native live widgets between embedded overlays, fullscreen, and detached windows. Inline live previews should remain available on hover/selection.
- Plot overlays use the overlay manager's `plot_host` owner; do not clear the default viewer overlay owner when synchronizing plot previews.
- Inline plot nodes keep an in-memory raster preview cache for the last real live widget frame after hover/selection exits. The cache is visual-only `QImage` state served through `image://plot-preview-cache/...`; do not persist it to `.cxproj` documents or temp files.
- Inline plot reactivation also restores an in-memory plot view state cache keyed by the same render signature. Keep pyqtgraph pan/zoom ranges and PyVista camera state as transient backend state, not project data.
- Inline plot live preview uses the resolved `plot_surface.live_backend_id` to decide whether a screen-size gate is needed. Keep the `graphNodeViewerViewport * currentViewportZoom` gate only for pyqtgraph live widgets, so zoomed-out 2D plots stay on cached/proxy preview while non-pyqtgraph live plotters are not blocked by the pyqtgraph clipping workaround.
- Matplotlib is both a headless static/data export backend and a live 2D Qt canvas backend. Keep the live path in `MatplotlibLive2DPlotBackend` / `MatplotlibPlotWidgetBinder` with lazy `FigureCanvasQTAgg` imports, and keep `headless_safe_surfaces` limited to static/data export.
- During live/cache handoff, keep the cached preview visible until `PlotHostService.embedded_live_overlay_ready(node_id)` reports that the native overlay widget is attached and exact viewport geometry is settled. Normalize cached preview images to the overlay container's logical size/DPR, and keep pyqtgraph live widgets on an opaque plot background with fixed axis layout so the cached raster cannot bleed through or appear to shift during the handoff frame.
- Inline plot surfaces should watch `PlotHostService.plot_overlay_revision` for live/cache handoff, because direct hover transitions from one live plot to another can keep the overlay count constant while the ready overlay identity changes. On embedded live exit, release the inactive overlay before the queued sync; while fullscreen content is open, suppress non-fullscreen inline plot overlays and inline cached plot images, publish only the fullscreen plot target, and keep the fullscreen scrim opaque so stale native or cached content does not flash.
- `GraphPlotSurfaceBody.qml` calls `PlotHostService.set_embedded_interaction_active` synchronously from its `liveSurfaceActive`/`plotNodeId`/`contentFullscreenOpen` change handlers (unlike `GraphViewerSurfaceBody.qml`, which had to defer the equivalent call through a coalesced `Qt.callLater` queue to fix a `bridgeSessionProjectionSeed` binding loop). The deactivation path (`_capture_cached_live_state_for_key` + `_release_inactive_embedded_overlay`) does re-emit `preview_cache_changed` and `state_changed` synchronously, but `liveSurfaceActive`'s own dependency set (`serviceAvailable`, `plotNodeId`, `plotLiveBackendId`, `embeddedSuppressed`, `contentFullscreenOpen`, `transientInteractionPreviewActive`, `liveSurfaceSizeViable`, `hostSurfaceActive`, `viewportHoverActive`, `autoPreviewPulse.running`) never reads `plot_overlay_revision`, `active_overlay_count`, or `preview_cache_revision` — those notifications only reach the strictly downstream `hostOverlayRevision`/`liveOverlayReady`/`cachedPreviewSource`/`cachedPreviewVisible` chain, which has no change handler that re-enters `_syncEmbeddedInteraction`. Verified with a synchronous-signal probe (`tests/test_plot_surface_integration.py::PlotSurfaceInteractionQmlTests::test_live_surface_deactivation_survives_synchronous_state_flip_without_binding_loop`) that mirrors the real `state_changed`/`preview_cache_changed` wiring and asserts no `Binding loop detected` message fires. If a future change makes `liveSurfaceActive` (or any of its dependencies) read one of those revision properties, re-apply the viewer's `Qt.callLater` deferral pattern here too.
- Plot fullscreen targeting should use the active fullscreen plot's workspace/node identity directly instead of trusting payload `native_overlay` metadata; stale or missing payload policy must not leave the live widget on the inline node viewport. Plot live overlays that are marked as the fullscreen target should wait hidden until `contentFullscreenViewerViewport` has real geometry rather than falling back to `graphNodeViewerViewport`.
- `PlotHostService` receives `ContentFullscreenBridge` directly from composition and connects exactly once until terminal shutdown; it does not discover fullscreen through `ShellWindow`. Fullscreen quick controls merge the changed key into the opened node's existing aggregate `plot_options` and commit through `GraphSceneBridge.set_node_property(...)`, preserving unrelated options, exact-node ownership, and one history entry per change even when another node is selected.
- Cached preview provider URLs must preserve exact workspace/node IDs without double-decoding percent-encoded text, and QML cached preview images should blank their source before applying a new node/source so a reused delegate cannot paint another plot's previous texture for one frame.
- During canvas viewport interaction or node drag, inline plot surfaces should use the cached raster preview instead of the native live overlay. Keep the plot eligibility checks paired between GraphCanvasViewportController.qml and `graph_canvas_state/` so wheel zoom enters the transient preview window for live plot surfaces.
- Plot session windows and `plot_session_layout` persistence were removed. Keep legacy `.cxproj` load compatibility by ignoring/stripping old `plot_session_layout` keys; do not restore user-facing session actions or retarget live widgets into a session presentation.
- PyVista/QVTK plot widgets should be finalized while their Qt/native window handle is still attached; avoid hidden/detached render-window cleanup paths that call into an invalid Win32 OpenGL context.
- Generic plot nodes accept `TabularDataRef`, `ArrayDataRef`, `TabularWindowRef`, and `ArraySlice2DRef` inputs through plot-side normalization. Keep backend contracts on existing `x`/`y`/`values`/`points` series shapes; ref reopening, selected-column/slice hints, and window/slice bounds are owned by the tabular add-on.
- Generic plot `series` compatibility is declared by runtime shape instead of the abstract Graph Data root: line/scatter/bar/histogram accept numeric, array/dictionary, and tabular/array-reference sources; heatmap/contour/surface accept array/dictionary and reference sources; point-cloud/streamline accept dictionary and reference sources. Keep Path and unrelated graph-root descendants out of these accepted-type unions while retaining runtime checks for genuinely abstract producers.
- Plot inspector controls project JSON-backed plot properties such as `axis_limits`, `log_scales`, `tabular_mapping`, and `plot_options` into structured rows such as numeric fields, toggles, searchable combos, and chip lists. Do not expose these plot fields as raw JSON textareas in the inspection pane.
- 2D live plot investigation options (`plot_theme`, `hover_readout`, `vertical_guide`, `crosshair`) persist inside `plot_options`. Inspector edits still use `PlotPropertyEditAdapter`; fullscreen quick controls use the exact-node aggregate mutation above through `ContentFullscreenBridge.set_active_plot_option`. Keep live interaction behavior in pyqtgraph-only paths unless another backend explicitly implements it.
- Tabular-to-plot auto-preview is a zero-I/O scene-payload projection: `kinds/plot.py` publishes only `plot_surface.series_signature` (sha256 of render-relevant plot props + source parse props + a source-file `stat`), `auto_preview*` flags, and the cached `render_revision`. The render request itself is built asynchronously by `PlotAutoPreviewService` (private QThreadPool, shared loader service) into the process-wide `PlotRenderRequestCache`; `plot_host_service` resolves requests from that cache by `(workspace_id, node_id, render_revision)` and returns no snapshot while pending (QML keeps the cached preview image). Targeted full-node payload rebuilds pass changed-field metadata so graph `node.title` renames may reuse the previous `plot_surface` without restatting the source; plot `properties["title"]`, source edge changes, and source-file stat changes still recompute the signature. This includes direct `tabular.input` connections and one-hop extraction nodes such as `tabular.table_filter` and `tabular.array_slice_2d`. Keep render requests out of scene payloads, node properties, and graph node output ports; user-facing plot outputs are Image Export (`static_export`), Data Export, and Exports, with no execution output.
- Tabular/array plot series are decimated to `TABULAR_PLOT_MAX_POINTS_PER_SERIES` (4000) through `execution/plot_series_decimation.py` — min-max envelope for x/y series (global extremes always survive), stride sampling for values/grids/points. Each series carries `decimation` metadata and a `source_ref`; the Data Export port streams the FULL source table through the shared loader service (`_write_full_fidelity_tabular_export`), so decimation never reduces export fidelity. An explicit `tabular_mapping.row_limit` is a hard source-row cap applied before decimation. The legacy `preview_series` plot property is deleted; `project_codec._copy_node_mapping` strips it from legacy documents on load and save.
- Tabular-to-plot normalization should raise clear plot-node errors when loaded headers, selected columns, mapping keys, empty rows, or numeric conversion prevent series generation; only completed-with-data caveats should remain `NodeResult.warnings`.
- Generic plot nodes use a required List-access `series` input. Plot sinks/side effects consume whole inputs through the audited data-access contract and expose no execution/completed/failed ports; keep catalog contract tests aligned when changing plot definitions.
- `examples/tabular_plot_showcase_direct.cxproj` is the no-adapter example for this path; keep it in sync with `scripts/generate_tabular_plot_showcase_example.py` when tabular-to-plot mapping behavior changes.

## Update Triggers
Update when plot backend registry contracts, backend capability flags, export behavior, plot List/Tree access declarations, optional plot dependencies, generic node definitions, structured plot-inspector control fields, tabular-to-plot mapping behavior, tabular auto-preview scene payloads, plot app preferences, legacy plot-session key stripping, sink-mode scene payloads, graph surface support, inline preview/view-state cache behavior, detached-window hosting, packet paths/prompts, or plotter verification changes.

## 2026-07-11 Performance Ownership

- Plot bridges remain stable while worker pools, host binders, and live backend internals allocate once on first use. Library/inspector plot pin/data-type projections reuse registry/workflow revisions; plot payload reuse still follows changed-field ownership.
