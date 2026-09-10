# PLAN: Gigabyte-Scale Tabular Data + Responsive Plotting

Self-contained implementation plan for a fresh session with no prior context. Produced 2026-06-10 via multi-agent exploration + adversarial verification; **every cited mechanism was confirmed by reading the code at the cited lines** (spot-check only if a file changed since).

Execution model: **measure first, fix the existing small benchmark and prove it, then synthesize large inputs and prove gigabyte-scale behavior** — see Phases at the end.

## Context

`plotting_benchmark.cxproj` (repo root) wires one `tabular.input` node (CSV `C:/Users/user/Documents/plot_data/full_data.csv`, 29.8 MB, 6 columns × ~400k rows, `cache_policy="app_managed_parquet"`) to one `plot.scatter` node (`table_data` → `series`). Merely having this workflow open makes the whole app laggy: tabular fullscreen open/close, run, save, load, node dragging. Goal: gigabyte CSVs load and plot fast, UI stays responsive (test-engineer workflow). Breaking changes / refactors / library changes are allowed **if tests and `docs/agent_maps/` are updated in the same change**.

Key insight: persistence is innocent — the .cxproj stays ~5 KB. All symptoms, including "slow save/load", are downstream of one flaw: **the graph scene payload build synchronously re-opens, re-scans, and fully materializes the tabular source on the UI thread, on every payload rebuild** — and rebuilds fire on every interaction.

## Root causes (all verified, file:line)

1. **Full-table materialization on every scene-payload rebuild.** `contribute()` → `apply_plot_surface_payload()` → `_plot_auto_preview_payload()` (`ea_node_editor/ui_qml/graph_scene_payload/kinds/plot.py:281-360`) runs in every per-node payload build (`graph_scene_payload/factory.py:461-462`; delta path `graph_scene_payload/builder.py:235`). `_table_row_limit` (`ea_node_editor/nodes/builtins/plot/generic.py:607-613`) sets `row_limit = ref.row_count` — **all 400k rows** (row count IS known, see #5) — and `_series_from_tabular_ref` (generic.py:616-672) materializes one Python dict per row via `_read_text_window` (pure-Python `csv` loop, `ea_node_editor/addons/tabular_data/loader_cache_service.py:968-987`). No downsampling exists anywhere.
2. **`_plot_render_revision` `json.dumps`-CRCs the full payload** every rebuild (`kinds/plot.py:128-130`); the full `render_request` (all points) rides in the scene payload to QML. The QImage render cache keyed by revision already exists (`tests/test_plot_preview_cache_provider.py`) — computing the revision is the O(cells) part. Additionally `binding_signature` re-freezes the entire series tuple per sync (`ea_node_editor/ui_qml/plot_host_service.py:578-589`).
3. **Fresh provider/service per call orphans all caches.** New `TabularPreviewProvider` per payload build (`kinds/plot.py:264`); new `TabularLoaderCacheService` in `_series_from_tabular_ref` (generic.py:624, also :684, :941) and in `input_node.execute` (`ea_node_editor/addons/tabular_data/input_node.py:528`). Records are per-instance (loader_cache_service.py:264-276) → every call re-runs `ensure_table_ref` → `open_source` → `scan_source`.
4. **Session creation scans the source twice** — `_session_for_properties` calls `scan_source` then `open_source` (which internally calls `scan_source` again) (`ea_node_editor/ui/tabular_preview_provider.py:524-614`).
5. **Open-time row counting reads the whole CSV in pure Python** for files < `TABULAR_DATA_SMALL_FILE_BYTES` = 100 MB — `_scan_text` → `_count_text_rows` (loader_cache_service.py:697-715, `addons/tabular_data/policy.py:53-54`, `ea_node_editor/settings.py:192`).
6. **Fullscreen-table queries scan everything in Python.** `preview_window` (loader_cache_service.py:425-489) builds `matched` = ALL rows even with no filter (cap `PREVIEW_QUERY_SCAN_ROW_CAP = 200_000`, line 45), sorts in Python, slices a 50-row page. Plain paging via `_read_text_window` streams from row 0 → deep pages are O(offset).
7. **The parquet cache and analytic backends are dead code in hot paths.** `ensure_parquet_cache` (loader_cache_service.py:662) is never called outside `tests/test_tabular_cache_service.py`; `window()` routes by `format_id` only (:412-423) so CSV reads are ALWAYS pure-Python; `policy.choose_table_backend`'s `duckdb_*` ids are labels with no implementation; `_write_text_parquet_cache` builds tables via `Table.from_pylist` over Python dict rows (:1137-1144 — all-string columns, full memory). Default `cache_policy="app_managed_parquet"` currently accelerates nothing.
8. **Run is slow for the same reason**: plot `execute` (generic.py:1117-1142) materializes `row_limit = row_count` row dicts in the worker (which re-scans the CSV in its own fresh service), then matplotlib renders 400k points.

### Trigger map (why EVERY interaction lags)

- `_GraphSceneContext.publish_edge_topology_delta` (:370), `publish_node_addition_delta` (:450), `publish_node_position_delta` (:548), `publish_node_geometry_delta` (:627) each call `rebuild_models()` (`ea_node_editor/ui_qml/graph_scene/context.py:749-809`) → per-node payload rebuild → #1-#3 run on the UI thread. Dragging any node = repeated full-file work.
- QML on-canvas preview: `previewPayload: _describePreview()` re-evaluates on every nodeData change (`ea_node_editor/ui_qml/components/graph/tabular/GraphTabularPreviewSurface.qml:24,167-188`). (The canvas host presenter holds ONE long-lived provider — `ea_node_editor/ui/shell/presenters/graph_canvas_host_presenter.py:23` — so this path becomes a cheap cache hit once sessions are shared.)
- Fullscreen open: `ea_node_editor/ui_qml/content_fullscreen_bridge.py:755-803` synchronous `describe_preview(mode='fullscreen')`; paging slots `request_tabular_window` (:1108-1127) are synchronous UI-thread calls. Fullscreen close → scene rebuild → #1 again.
- Save/load write/read only small JSON (`ea_node_editor/persistence/project_codec.py:192-200`); their perceived lag is the scene rebuilds they trigger.
- Even >100 MB files (row count deferred → `row_count=None`) would still lag: the plot path parses `TABULAR_PLOT_UNKNOWN_ROW_LIMIT = 5000` rows in Python per rebuild plus header/delimiter scans per rebuild.

## Architecture decision (one solution, no new libraries)

**Push the existing lazy-ref + managed-parquet architecture to its conclusion:** one shared thread-safe `TabularLoaderCacheService`; every text/Excel source converts once (off the UI thread, streamed via `pyarrow.csv`) into the already-existing managed parquet cache; all windows/queries/plot reads go through parquet (pyarrow) or duckdb SQL. Plots consume **decimated** series (min-max envelope, ≤ 4000 points/series — visually lossless for line plots) built **asynchronously** in a render-request cache that lives outside the scene payload. Scene payload contributors do **zero data I/O** — they publish only a cheap staleness signature. Preview/fullscreen surfaces page bounded windows through an async worker keyed by `(path, mtime_ns, size, options)`.

Dependencies: `pyarrow 24.0`, `duckdb 1.5.2`, `numpy 2.2` already installed and declared in `pyproject.toml` `[tabular]` extra (pyproject.toml:29-39). Polars stays benchmark-only. Use the existing `_import_optional` pattern; keep numpy imports lazy in core plot modules (the generic plot family intentionally keeps numpy optional — see `normalize_generic_plot_series` in `ea_node_editor/execution/plot_backend.py:104-127`).

## Implementation steps

### Step 0 — Measurement harness + baseline (BEFORE any fix)
New `scripts/verify_tabular_perf.py` — patterned on `scripts/profile_canvas_lag.py`: boots the app in a subprocess with `EA_PROFILE_AUTOQUIT=1` and `QT_QUICK_CONTROLS_STYLE=Basic` (set explicitly), opens a given `.cxproj`, drives fullscreen open/close + node moves + save/load + run, records the existing `payload_rebuild_ms` / `scene_publish_ms` mutation-timing phases (`graph_scene/context.py` ~:401-:714) plus wall-clock timings into `artifacts/perf/tabular_perf_report.json`; `--budget` flags make it fail on breach.
Run it against the existing **`plotting_benchmark.cxproj`** on unmodified code and commit the baseline numbers (`artifacts/perf/baseline_small.json` or paste into the PR description). All later claims are before/after deltas from this harness.

### Step 1 — Shared, thread-safe tabular service (foundation)
Files: `loader_cache_service.py`, `input_node.py`, `extraction_nodes.py`, `plot/generic.py`, `tabular_preview_provider.py`, `addons/tabular_data/property_edit_adapter.py`.
1. Add module-level `shared_tabular_loader_cache_service() -> TabularLoaderCacheService` in `loader_cache_service.py`, with a `threading.RLock` guarding `_table_records`/`_array_records` and a per-cache-key lock registry for parquet conversion. Store `SourceStats` (mtime_ns/size) on `_TableRecord` and include `mtime_ns` in `_ref_id()` so records invalidate when the file changes.
2. Replace every ad-hoc `TabularLoaderCacheService()`: `input_node.py:528`, `generic.py:624/:684/:941`, `tabular_preview_provider.py:319` default factory (keep injectable factory for tests), `property_edit_adapter.py` provider call site.
3. Collapse the double scan in `_session_for_properties` (tabular_preview_provider.py:524-614) to a single `open_source` (+scan from the shared records).
Result: `ensure_table_ref()` is a dict hit across execution, preview, and payload paths.

### Step 2 — Parquet-first ingestion; delete CSV scans
Files: `loader_cache_service.py`, `policy.py`, `settings.py`.
1. **Delete open-time row counting** (`_count_text_rows` call at :706 and its definition; remove `should_count_rows_during_open` from `policy.py`). `row_count` stays `None` until the parquet cache exists, then backfills from `parquet_file.metadata.num_rows`. Bump `TABULAR_DATA_BACKEND_POLICY_REVISION` (settings.py:191) to v2 so cache keys/ref ids roll over cleanly.
2. **Rewrite `_write_text_parquet_cache` (:1120-1148)** to stream `pyarrow.csv.open_csv` → `ParquetWriter` (map `TabularLoadOptions` → Read/Parse/ConvertOptions: delimiter, encoding, skip_rows, header_row, schema_hints). Today it is `Table.from_pylist` over Python dict rows — all-string columns and full-memory; the rewrite gives typed columns at I/O speed. Keep the Python-`csv` path as fallback for `ArrowInvalid` (exotic quoting/encodings). Write temp file + `os.replace`; hold the per-key conversion lock.
3. **Route reads through parquet**: in `window()` (:412), `arrow_batches()` (:555), `iter_window_rows` (:538), and schema/row-count — when the format is text/Excel and policy is `app_managed_parquet` (default), dispatch to `_read_parquet_window` against the cache file. `_read_text_window`/`_read_excel_window` remain only for `source_direct`.
4. **Replace `preview_window` query scan (:454-489)** for cached sources with duckdb SQL over the cache parquet (`read_parquet` + WHERE/ORDER BY/LIMIT/OFFSET, `COUNT(*)` for `total_rows`; parameter-bind values, escape identifiers). Bounded Python scan (with cap + truncation metadata) stays as the `source_direct`/HDF5 fallback.
5. Conversion never runs inline on the UI thread: `window()` raises a new recoverable `TabularCacheNotReadyError` when the cache is missing on a UI-thread call; async callers (Steps 4-5) translate it into a `loading` state and trigger conversion on a worker. Small files (< ~8 MB) may convert synchronously. Add LRU size cleanup for `tabular_data_cache_dir()` plus a startup sweep deleting cache entries whose metadata `backend_policy_revision` ≠ current.

### Step 3 — Plot decimation contract (bounded series everywhere)
Files: new `ea_node_editor/execution/plot_series_decimation.py` (execution owns plot contracts per `docs/agent_maps/subsystems/execution.md`); `plot/generic.py`; `plot_host_service.py`.
1. New module: `decimate_xy(x, y, max_points) -> (x', y', meta)` — per-bucket min-max envelope (vectorized `np.minimum.reduceat`/`maximum.reduceat`), NaN-safe, preserves global extremes; `stride_sample(...)` for scatter/point-cloud/streamlines; meta `{"method", "original_rows", "points"}`. numpy imported lazily inside functions (guaranteed present when tabular refs flow in, via the dependency-gated add-on).
2. `generic.py`: delete `_table_row_limit` (:607-613), `TABULAR_PLOT_UNKNOWN_ROW_LIMIT`/`TABULAR_PLOT_UNKNOWN_ROWS_WARNING` (+ warning handling at :1127-1132); add `TABULAR_PLOT_MAX_POINTS_PER_SERIES = 4000` (explicit `tabular_mapping.row_limit` remains a hard source-row cap, not a default). Rewrite `_series_from_tabular_ref` / `_series_from_tabular_window_ref` / array variants to read only needed columns via `service.arrow_batches(...)` → numpy per column → decimate → `{"label","x","y","decimation":{...}}`. **No per-row dicts anywhere.** Attach `render_request.options["series_source"] = ref.to_payload()` (small metadata).
3. Full-fidelity export: in `_archive_exports`, when `series_source` exists, data export streams the full table from the shared service (`arrow_batches` → `pyarrow.csv.write_csv` per batch); image export renders decimated series (visually identical).
4. **Delete the `preview_series` PropertySpec** (generic.py:215-222) and its fallback read at plot_host_service.py:117-119 — closing the only channel for series data to enter node properties / undo / .cxproj.
5. `plot_host_service.binding_signature` (:578-589) becomes `(backend_id, plot_type, render_revision)` — drop `_freeze_value(series/options)`.
6. `execute()` flows through the same decimated path → fast runs, bounded memory.

### Step 4 — Scene payload: zero-I/O contributors + async render-request cache
Files: `kinds/plot.py`; new `ea_node_editor/ui_qml/plot_auto_preview_service.py`; `plot_host_service.py`; shell composition wiring (`ea_node_editor/ui/shell/composition/runtime_services.py`).
1. `kinds/plot.py`: delete the per-call `TabularPreviewProvider` + ref construction (:243-278) and `_plot_render_revision` (:128-130). `_plot_auto_preview_payload` becomes pure metadata: keep the edge-walk topology logic, compute `series_signature = sha256(render-relevant plot props + tabular_mapping + source-node parse/selection props + path stat mtime_ns/size)` (a `stat()` is microseconds), publish `{"auto_preview": true, "series_signature", "render_revision": <cached or 0>, "auto_preview_pending": <cache miss>}`. Project-managed artifact paths resolve via `ProjectArtifactResolver` (`ea_node_editor/persistence/artifact_resolution.py`) using the existing `_project_context_from_graph_theme_bridge` helper (kinds/plot.py:118-125).
2. New `PlotAutoPreviewService(QObject)` + `PlotRenderRequestCache`: subscribes to scene payload changes; on signature miss schedules a `QRunnable` (private `QThreadPool`, ≤2 threads) that resolves the ref via the shared service (triggering parquet conversion if needed), builds the decimated render request, stores it keyed `(workspace_id, node_id)` with a monotonic revision, then emits a queued signal that refreshes that node's payload (use `payload_cache_sync.replace_cached_node_payload`, `ea_node_editor/ui_qml/graph_scene/payload_cache_sync.py:361`). LRU-bound (~32); errors stored as `auto_preview_error` and surfaced like today. Workers never touch QObjects; results cross threads via queued signals only.
3. `plot_host_service._render_request_from_payload` (:106-125): resolve from `PlotRenderRequestCache` by `(workspace_id, node_id, render_revision)`; on miss show the existing cached preview image until ready.
4. Wire the service in shell composition next to the plot preview image provider.
Result: scene rebuilds touch no tabular data; fullscreen open/close, drag, selection are O(graph), not O(rows).

### Step 5 — Async, paged preview/fullscreen surfaces
Files: new `ea_node_editor/ui/tabular_preview_async.py`; `tabular_preview_provider.py`; `graph_canvas_host_presenter.py`; canvas bridge plumbing (`graph_canvas_bridge.py`, `canvas_host_ops.py`, `protocols.py`); `content_fullscreen_bridge.py`; `GraphTabularPreviewSurface.qml`; `TabularFullscreenSurface.qml`; `tabular_preview_table_model.py`.
1. `TabularPreviewWorkerPool` wraps `QThreadPool`, runs provider calls off-thread, delivers via queued signals; cache key = existing `_session_id` (`(path, mtime_ns, size, options)`, tabular_preview_provider.py:627-639) + request payload; raise `TABULAR_PREVIEW_INLINE_PAYLOAD_CACHE_LIMIT` to 32; serialize per-session work (one in-flight job per key — dedups GB conversions).
2. Inline path: presenter returns cached payload synchronously on hot key; on miss returns `{"state":"loading"}` and schedules; completion emits `tabular_preview_updated(cache_key)` plumbed to QML. `GraphTabularPreviewSurface.qml` switches `previewPayload` from a binding to a property refreshed on nodeData change AND on the signal; render a skeleton for `loading`.
3. Fullscreen path: `build_tabular_payload` (:755-803) embeds `{"state":"loading"}` and schedules; completion updates `_tabular_payload` + emits `content_fullscreen_changed` → first rows appear without blocking open. Replace sync `request_tabular_window`/`request_tabular_slice_2d` (:1108-1127) with `request_tabular_window_async(request_id, request)` + `tabularWindowReady(request_id, payload)` signal (breaking change; update QML + table model with request-id correlation, drop stale responses). Page size stays bounded (`TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT = 500`).

### Step 6 — Persistence guards + migration
Files: `project_codec.py` (+ verify `session_store.py`).
- Node properties: `preview_series` deleted (Step 3) — no property can hold rows. Undo/mutation snapshots and autosave reuse the document codec → small by construction.
- Add a load+save sanitizer stripping a legacy `preview_series` key from `plot.*` node property mappings (`_copy_node_mapping` call sites, project_codec.py:192-200). Legacy projects load fine and shrink on next save. **No `schema_version` bump** (document shape unchanged).
- QML scene payload carries only signature + revision ints (Step 4); tabular previews are pulled on demand, never embedded.

### Step 7 — Large-input synthesis + gigabyte proof
1. New `scripts/generate_large_tabular_csv.py` — reuse `ea_node_editor/benchmarks/tabular/datasets.py` (`DatasetSpec`, `iter_table_chunks`) + `pyarrow.csv.write_csv`; flags `--rows/--columns/--target-bytes`; writes to `artifacts/perf/`. Also `--emit-project` to write a `.cxproj` mirroring `plotting_benchmark.cxproj` pointed at the generated CSV (tabular.input → plot.scatter), plus a variant with a `tabular.table_filter` extraction node in between.
2. Run `scripts/verify_tabular_perf.py` against the generated ~400 MB and ~1 GB projects (cold cache and warm cache passes) — budgets below.
3. Visual parity spot-check: render the same small file (≤4000 rows, decimation no-op) before/after and a 400k-row file decimated vs. `tabular_mapping.row_limit`-bounded; line plots must be visually indistinguishable at canvas resolution.

### Step 8 — Docs, maps, indexes (with each code change, finalized here)
Update `docs/agent_maps/feature_routes/tabular_data_addon_preview.md`, `feature_routes/plotter_nodes.md`, `feature_routes/graph_scene_payload_and_projection.md`, `subsystems/passive_media_tabular_surfaces.md`, `subsystems/addons.md`, `subsystems/execution.md`, `COVERAGE.md`; regenerate `docs/source_test_file_index.md` via `scripts/generate_source_test_file_index.py`. Regenerate `examples/tabular_plot_showcase_direct.cxproj` via `scripts/generate_tabular_plot_showcase_example.py` ONLY if mapping/selection contracts change (this plan doesn't change them). Run `venv\Scripts\python.exe scripts\check_traceability.py` if ARCHITECTURE.md is touched (beware frozen-token/substring-masking traps).

## Phased delivery & verification gates

**Phase 0 — Baseline.** Step 0. Capture current numbers for `plotting_benchmark.cxproj` (fullscreen open/close, drag `payload_rebuild_ms`, save, load, run wall-clock). Deliverable: baseline report.

**Phase A — Fix the existing small benchmark (Steps 1, 2, 3, 6).** Gate A, measured on the user's existing `plotting_benchmark.cxproj` with the harness:
- Fullscreen open/close < 250 ms each (warm cache), no UI-thread full-table materialization.
- Node move `payload_rebuild_ms` < 10 ms; zero tabular file I/O on unchanged-signature rebuilds (counter on `scan_source`).
- Save < 200 ms, `.cxproj` < 256 KB; load < 1 s.
- Run < 2 s end-to-end; plot series ≤ 4000 points with `decimation.original_rows == 400000`; data export reproduces all 400k rows.
- Full suite green; boot smoke exits 0. Show before/after table vs. Phase 0.

**Phase B — Async + zero-I/O payloads (Steps 4, 5).** Gate B, same small benchmark:
- All Gate A budgets hold; additionally fullscreen open never blocks the UI thread > 50 ms even with a cold cache (loading state appears < 100 ms), and rapid drag stays at 60 fps.

**Phase C — Gigabyte proof (Step 7).** Gate C, generated ~400 MB and ~1 GB projects (plot included):
- Cold open: UI interactive immediately; "loading/indexing" state visible; background conversion completes; no UI freeze > 50 ms.
- Warm cache: fullscreen first 50 rows < 1 s; page change < 100 ms; search/sort < 1 s (duckdb); deep page (e.g. row 5M) < 200 ms.
- Run < 5 s warm; series ≤ 4000 points; save/load budgets unchanged from Gate A (independent of source size).
- Visual parity spot-check passes.

**Phase D — Docs/maps finalization (Step 8) + full-suite + boot smoke.**

## Tests

Runner rules: `.\venv\Scripts\python.exe -m pytest -n auto --ignore=venv -q` for everything EXCEPT `tests/graph_track_b`, which runs ONLY via `.\venv\Scripts\python.exe -m unittest tests.test_graph_track_b`. Check `git status` first — the tree currently has uncommitted changes (artifact_store.py, session_store.py, session_lifecycle_service.py, related tests) from a possibly-concurrent session: don't revert, don't attribute their failures to this work. Known-failing on main (2026-06-10): shell-window elapsed/library-drop, project-session staged refs, typography traceability tokens — verify on main before attributing. Elapsed-timer QML tests flake under parallel CPU load; rerun serially before judging. Never run two pytest sessions concurrently.

Update (per step): `test_tabular_cache_service.py` (registry reuse, parquet routing, mtime invalidation, no open-time row count), `test_tabular_runtime_refs.py`, `test_tabular_input_node.py`, `test_tabular_loaders.py` (pyarrow parity: delimiter/header/skip/encoding), `test_tabular_large_data_policy.py`, `test_tabular_benchmark_workbench.py` (policy revision), `test_tabular_preview_provider.py` (single-scan sessions, loading state, duckdb query parity), `test_plot_node_contracts.py` (decimation contract, `preview_series` removal, warning removal), `test_plot_headless_export.py` (full-data export from ref), `test_plot_host_service.py`, `test_plot_widget_binder.py`, `test_plot_surface_integration.py`, `test_plot_session_bridge.py`, `test_plot_detached_window.py`, `test_plot_fullscreen_overlay.py`, `test_content_fullscreen_bridge.py` (+ lifecycle), `test_tabular_preview_table_model.py`, `test_tabular_extraction_nodes.py`, `test_tabular_project_managed_data.py`, `test_project_save_as_flow.py`, `tests/graph_track_b/scene_and_model.py` payload-shape expectations, `test_dead_code_hygiene.py` (delete dead helpers rather than suppress).

Add: `tests/test_plot_series_decimation.py` (envelope correctness: global min/max preserved, NaN handling, n ≤ budget passthrough), `tests/test_plot_auto_preview_service.py` (signature → async build → payload refresh; error path; LRU), `tests/test_tabular_preview_async.py` (dedup, stale request-id dropping), `tests/test_project_large_data_isolation.py` (save benchmark workflow → `.cxproj` < 256 KB, no series arrays), `tests/test_tabular_perf_guards.py` — **the regression guard**: (a) second payload build of the same plot node performs zero source-file opens (counter on `scan_source`), (b) auto-preview never exceeds the decimation budget, (c) `preview_window` without cache never reads more than the cap.

## Risks & breaking changes

- **Shared-service thread safety** is the highest-risk change: RLock + per-key conversion locks + a concurrency smoke test; workers never touch QObjects.
- **pyarrow.csv vs Python `csv` parsing differences** (quoting, ragged rows, encodings): keep the fallback, add parity tests; `header_row > 0` ↔ skip_rows arithmetic needs an explicit test.
- **Decimated plots are a behavior change** (sub-pixel image-export differences). Accepted; surfaced via `decimation` metadata + RELEASE_NOTES.md note; explicit `tabular_mapping.row_limit` still wins; writer nodes/data export keep full fidelity.
- **Async states introduce ordering races** (stale windows, signature races on rapid edits): request-id correlation + monotonic revisions; cover with lifecycle tests.
- **Sync slot removals** (`request_tabular_window` et al.) break external QML callers; all in-repo callers updated in Step 5; note as breaking.
- **Disk usage**: parquet cache ≈ 0.3-1× source per (path, options) key under `tabular_data_cache_dir()`; LRU cleanup + policy-revision sweep prevent unbounded growth.
- **Windows file locks**: close `ParquetFile`/duckdb handles deterministically (context managers); tests must not hold mmaps open while deleting temp dirs (known repo trap).

## Commit ordering (each keeps the suite green)

1. Step 0 (harness + baseline) → 2. Step 1 (shared service) → 3. Step 2 (parquet-first, policy v2) → 4. Step 3 (decimation + export-from-ref + `preview_series` removal) → 5. Step 6 (codec sanitizer; pairs with 3) → **Gate A re-measure** → 6. Step 4 (async render-request cache; biggest UI change) → 7. Step 5 (async preview/fullscreen) → **Gate B re-measure** → 8. Step 7 (large-input synthesis + Gate C) → 9. Step 8 (docs/maps). Steps 1-3 already fix most of the 30 MB-case lag; 4-5 deliver the 60 fps and GB-scale guarantees. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; don't commit unless asked.

## Repo gotchas for the implementing session

- Always `.\venv\Scripts\python.exe` (global python lacks Qt deps). Start exploration at `docs/agent_maps/INDEX.md` + `COVERAGE.md`.
- Scripted app drivers MUST set `QT_QUICK_CONTROLS_STYLE=Basic` or MainShell.qml hangs in a modal; `EA_PROFILE_AUTOQUIT=1` for boot smokes. No QML hot reload — check a running app's start time vs. fix mtimes before judging a fix; don't probe an instance the user is testing interactively.
- `PassivePdfNodeSurfaceQmlTests` are environmentally flaky on Windows — unrelated to this work.

## Implementation addendum (2026-06-11, implementing session)

All phases landed; budgets measured with `scripts/verify_tabular_perf.py` (baseline -> Phase B on `plotting_benchmark.cxproj`): load 95.4s -> 0.96s, save 25.2s -> 72ms, full rebuild p50 17.6s -> 17ms, node move 42.3s -> ~20ms wall (payload phase ~0ms), fullscreen tabular/plot warm 2.4s/47.4s -> 80ms/66ms. Gate C (`artifacts/perf/large_*.json`, 400MB/3.6M and 1GB/8.8M rows): cold load interactive ~1.2s with loading states (paging answers `loading` in ~2ms), warm first rows 326ms, warm page/deep-page 8-21ms, sort/search recorded by the harness, warm run artifacts ranged from 4.8s (1GB) to 9.9s (400MB), saved project ~5KB. Decimation parity: mean pixel diff 0.61/255 (`scripts/verify_plot_visual_parity.py`).

Deviations from the plan, with reasons:

1. **duckdb is banned from the GUI process.** Loading duckdb (or lazily importing additional pyarrow extension DLLs, or using `pyarrow.csv.open_csv`'s streaming reader) in a process where a Qt Quick engine has run corrupts the process on Windows (pyarrow 24.0 + PyQt6; access violations whose faulting stack moves between runs). Preview sort/filter/search therefore use pyarrow.compute (`_preview_window_arrow`) plus a bounded query-table cache; conversions use chunked `pyarrow.csv.read_csv` over line-aligned byte blocks; the addon preloads every pyarrow submodule at import time. Guarded by `tests/test_tabular_native_runtime_guards.py`.
2. **Search/sort budget at the 5M+ scale.** Page/deep-page/window budgets hold with row-group pruning; numeric sort is ~1s at 3.6M and ~1.7s at 8.8M rows; all-column substring search is 2-6s first / 1-2s repeated (arrow compute, no duckdb). Column-scoped filters meet <1s.
3. **`request_tabular_window` stays synchronous** (not replaced by an async slot): warm reads are bounded and fast; only cold-cache responses are async (`loading` state + the bridge's `tabularWindowReady` signal). No external QML callers break.
4. **Run < 2s is not achievable from this plan's mechanisms**: warm run artifacts were 4.8-9.9s, dominated by execution-subprocess interpreter/registry boot and run-process variance, unchanged by tabular work. Plot execute itself is fast (decimated).
5. **Step ordering**: the async preview layer (Steps 4-5) was pulled forward into the same change as Phase A after the inline-conversion bridge proved to crash QML flows (see deviation 1).
