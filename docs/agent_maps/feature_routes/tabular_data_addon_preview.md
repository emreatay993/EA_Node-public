# Tabular Data Add-on And Preview

## Purpose
Use this for the tabular data add-on, tabular input node, preview provider, sheet/key selector UX, tabular QML surface, durable selected-column/slice hints, tabular-to-plot auto-preview payloads, and dependency-gated availability.

## Start Here
- `ea_node_editor/addons/tabular_data/catalog.py`
- `ea_node_editor/addons/tabular_data/function_nodes.py` — inert declarations for the seven executable shells
- `ea_node_editor/addons/tabular_data/input_node.py`
- `ea_node_editor/addons/tabular_data/`
- `ea_node_editor/addons/tabular_data/loader_cache_service.py` — shared parquet-first loader service (see notes)
- `ea_node_editor/addons/tabular_data/source_backends.py` — format-specific scan/read/array/conversion owner
- `ea_node_editor/addons/tabular_data/preview_query.py` — normalized preview request and Python/Arrow evaluators
- `ea_node_editor/addons/tabular_data/extraction_nodes.py`
- `ea_node_editor/addons/tabular_data/property_edit_adapter.py`
- `ea_node_editor/execution/plugin_worker_runtime.py`
- `ea_node_editor/ui/tabular_preview_provider.py`
- `ea_node_editor/ui/tabular_preview_async.py` — worker pool for cold preview resolution
- `ea_node_editor/ui/shell/inspector_projection.py`
- `ea_node_editor/ui_qml/tabular_preview_table_model.py`
- `ea_node_editor/ui_qml/components/graph/tabular/`
- `ea_node_editor/ui_qml/components/graph/tabular/GraphTabularPreviewSurface.qml`
- `ea_node_editor/ui_qml/components/graph/tabular/TabularTableViewport.qml`
- `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
- `ea_node_editor/ui/shell/host_presenter.py`
- `scripts/verify_tabular_perf.py` — perf harness (budgets + cold/warm cache runs)
- `scripts/generate_large_tabular_csv.py` — gigabyte fixture + benchmark project synthesis
- `tests/test_tabular_preview_provider.py`
- `tests/test_tabular_function_migration.py`
- `tests/test_tabular_input_node.py`
- `tests/test_tabular_extraction_nodes.py`
- `tests/test_tabular_preview_async.py`
- `tests/test_tabular_perf_guards.py`
- `tests/test_tabular_native_runtime_guards.py`
- `tests/test_content_fullscreen_bridge.py`
- `tests/test_passive_property_editors.py`
- `tests/test_graph_surface_input_controls.py`
- `tests/graph_surface/passive_host_interaction_suite.py`
- `tests/test_tabular_loaders.py`
- `tests/test_tabular_preview_query.py`
- `tests/test_tabular_project_managed_data.py`
- `examples/tabular_plot_showcase.README.md`
- `examples/tabular_plot_showcase_direct.cxproj`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_tabular_function_migration.py tests/test_tabular_addon_catalog.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_tabular_preview_provider.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_tabular_input_node.py tests/test_tabular_loaders.py tests/test_tabular_preview_query.py tests/test_tabular_project_managed_data.py tests/test_tabular_runtime_refs.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_tabular_extraction_nodes.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_passive_property_editors.py tests/test_graph_surface_input_controls.py tests/graph_surface/passive_host_interaction_suite.py --ignore=venv -q
```

## Breadcrumbs
- [Add-ons](../subsystems/addons.md)
- [Passive, Media, And Tabular Surfaces](../subsystems/passive_media_tabular_surfaces.md)
- [Plotter Nodes](plotter_nodes.md)

## Surface Ownership Notes
- `loader_cache_service.py::column_arrays` is the shared selected-column reader for generic and Signal plots. Source opening caches bounded `metadata.column_schema` name/dtype facts; omit that whole field if merged ref metadata exceeds 64 KiB. Signal Plot honors ArrayDataRef's authored preview slice (50 rows by default); an explicit ArraySlice2DRef overrides those hints and zero limits select all remaining data.
- The seven executable Tabular shells are inert `corex` declarations in `function_nodes.py`, statically parsed as one digest-pinned function bundle owned by `ea_node_editor.builtins.tabular_data`. `catalog.py` retains dependency gating, manifest/toolchain facts, zero descriptors, exact function IDs, and lazy source loading. The worker accepts private declaration metadata only because the trusted registry already carries that exact owner contract; public bundles do not inherit this trust.
- Enable, disable, and dependency-unavailable rebuilds add or remove the Tabular manifest, seven entries, and bundle together. Add-on discovery reports declared IDs without loading or executing the function source, and the existing full registry-replacement coordinator remains the hot-apply owner.
- All tabular consumers share one process-wide `shared_tabular_loader_cache_service()` (thread-safe records + scan cache + per-key conversion locks). Format-specific scan/read/array/conversion behavior lives in `source_backends.py`; text/Excel sources convert once into the managed parquet cache (chunked `pyarrow.csv.read_csv` blocks — NEVER `open_csv`, see `tests/test_tabular_native_runtime_guards.py`). Row counts are never computed by rescanning the source; they backfill from cache metadata. `EA_TABULAR_CACHE_DIR` overrides the cache dir.
- Tabular output availability learned from settlement is node-scoped solution state. Exact invalidation/recompute IDs clear only affected observations; graph mutation helpers no longer clear every node in the workspace, and only a store-accepted current settlement may observe a replacement output kind.
- Cold large sources never convert on the UI thread: `window()` raises `TabularCacheNotReadyError`, the provider returns a `loading` payload, and `TabularPreviewWorkerPool` (canvas host presenter + fullscreen bridge) resolves it on a worker. `GraphTabularPreviewSurface.qml` re-describes on a retry timer while loading and refreshes again when the canvas/command bridge arrives after the surface was completed; `TabularFullscreenSurface.qml` applies async window results from the bridge's `tabularWindowReady` signal. Small files (≤ `TABULAR_DATA_INLINE_CONVERSION_BYTES`) still convert synchronously.
- `preview_query.py` normalizes selected columns, filters, search, sort, offset, and limit once. Parquet-backed sources use its Arrow evaluator with exact totals and typed values; `source_direct`/HDF5 use its bounded Python evaluator with the existing 200k cap, truncated totals, and source typing. Missing/null/blank named-column values share the locked operator policy. duckdb must NOT be imported in the GUI process.
- App startup explicitly calls `_preload_native_tabular_runtime()` before QML construction because lazy Arrow DLL loads after Qt Quick has run crash the process. The Tabular package and catalog stay import-light for discovery; extend the explicit preload list when using a new PyArrow submodule.
- `examples/tabular_plot_showcase_direct.cxproj` demonstrates direct `TabularDataRef` / `ArrayDataRef` plotting without Python Script adapter nodes. Regenerate it through `scripts/generate_tabular_plot_showcase_example.py` when selected-column, array-slice, or plot-side mapping contracts change.
- `selected_object` is the persisted sheet/key/dataset choice. The property pane and `GraphTabularPreviewSurface.qml` use `TabularPreviewProvider.describe_selector(...)` / `describe_tabular_selector(...)` to scan object IDs without materializing the selected object.
- Tabular Input's source path dialog filter is declared on its `PropertySpec.file_filter` using the shared tabular filter constant. The Path property disables its inline editor, so the node shows the Path port without a path box or Browse button; source selection remains in the inspector and surface toolbar. Its graph-surface Source toolbar dropdown routes `path` browse requests through the same generic shell forwarding with `external_link` / `managed_copy` source modes. Keep tabular file-extension changes in the add-on node metadata/shared filter list and let shell browse forwarding stay generic.
- Excel-style table paste creates the same `tabular.input` node with a staged `.tsv` source path. Shared parsing belongs to `clipboard_paste_nodes.py`; `CanvasImportController` creates data immediately in Automatic mode or offers data, Markdown, plain Text, and Panel in the common Ask dialog. Disabled Tabular support is reported without silently substituting a note. Do not add an add-on-specific paste path.
- Shipped `tabular.input` receives exact registry-owned file-content provenance for `path`; the add-on declaration stays unchanged and public/package rows cannot opt into the overlay.
- Property-pane `selected_object` combo payloads and friendly `array_slice_2d_*` editor rows are add-on-owned policy in `property_edit_adapter.py`, registered through the add-on catalog. Generic shell inspector/edit code should call the adapter hook and should not import tabular constants for these rewrites.
- Lazy extraction execution helpers live in `extraction_nodes.py`: `tabular.table_filter` and `tabular.array_slice_2d` produce `TabularWindowRef` / `ArraySlice2DRef`; writer nodes and generic plot nodes consume those refs directly; materializer nodes are explicit memory-loading escape hatches for scripts/debugging.
- Preview surfaces expose user-facing visible export. `GraphTabularPreviewSurface.qml` and `TabularFullscreenSurface.qml` route `Export` through `ContentFullscreenBridge`, which prompts Save As through `ShellHostPresenter.save_file_dialog(...)` and writes the current bounded preview window/page after search/filter/sort. This is a surface convenience path; keep graph-level batch/automation export in the writer nodes.
- Extraction-node row/column bounds are stored as hidden zero-based canonical properties and projected by the add-on property adapter into one-based row controls, spreadsheet-style column controls, column chips, and summary rows. `0` row/column limits mean all remaining data and should remain visible in help/summary text.
- The selection-required inline sheet/key/dataset picker uses `GraphSurfaceSearchableComboBox`; keep popup sizing fixes in the shared surface-control component rather than the tabular call site.
- Durable selected-column/slice hints feed plot-side auto-preview scene payloads through direct tabular refs and one-hop extraction refs, with structured plot controls owning mapping choices; do not route this path through raw inspector JSON fields.

## Update Triggers
Update when tabular dependencies, input node ports, source path browse filters, preview model, tabular QML, tabular clipboard paste behavior, or managed data tests change.
Update when selected-column or array-slice hints are persisted for downstream consumers such as plot nodes.
Update when lazy tabular extraction refs, writer/materializer nodes, output path filters, or `0` full-limit semantics change.
Update when Tabular function declarations, dependency-gated bundle registration, worker identity, or hot-apply membership changes.
Update when selector scan payloads, property-pane `selected_object` editors, property edit adapters, tabular-to-plot auto-preview payloads, visible export behavior, Save As routing, or tabular surface selection-required UX changes.

## 2026-07-11 Performance Ownership

- `.txt` delimiter detection consumes at most the first `4096` characters. Shared tabular cache/service internals allocate on first use, but coordinated PyArrow preload remains explicitly before QML construction.
