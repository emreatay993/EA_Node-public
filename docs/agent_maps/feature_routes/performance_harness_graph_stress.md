# Performance Harness And Graph Stress

## Purpose
Use this for graph canvas performance, stress tests, mutation latency, scene publish time, GPU stress, and performance harness commands.

Lookup aliases: `stress_1200_nodes`, `notched port rendering`, `benchmark report fields`.

## Start Here
- `ea_node_editor/ui/perf/performance_harness.py`
- `ea_node_editor/ui/perf/engineering_viewer_benchmark.py`
- `scripts/profile_canvas_lag.py`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasFrameScheduler.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHostRenderQuality.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml` edge churn counters: spatial query cache hits/misses, retained entry skips, and flow-label sync skips. Execution-flash scoped refreshes are removed with control-edge animation.
- `tests/test_track_h_perf_harness.py`
- `tests/test_graph_canvas_frame_coalescing.py`
- `tests/graph_surface/passive_host_boundary_suite.py`
- `docs/specs/perf/TRACK_H_BENCHMARK_REPORT.md`
- `docs/specs/perf/GRAPH_CANVAS_PERF_QA_MATRIX.md`
- `docs/specs/perf/COREX_CHANGE_LOCALITY_QA_MATRIX.md`
- `docs/specs/perf/COREX_INTERNAL_PERFORMANCE_IMPROVEMENT_QA_MATRIX.md`
- `docs/specs/perf/ENGINEERING_VIEWER_V1_NATIVE_PERF_REPORT.md`

## Current Measurement Ownership

- `scripts/profile_canvas_lag.py --selection` delegates to `scripts/canvas_selection_profile.py` for production canvas mouse clicks in a composed shell with isolated preferences and an inert execution client. It measures dispatch and click-to-QML-render completion separately, verifies selection bindings before the accepted render, and records cleared inspector visual counts across collapsed, Smart Groups, Accordion, and Palette modes. The Windows/D3D11 p95 gate is `<100 ms`; `afterRendering` excludes widget composition, GPU completion, and display presentation. See [Inspector Selection Performance](../../specs/perf/INSPECTOR_SELECTION_PERFORMANCE_QA.md).
- State-side `visible_node_model_update_ms` is the sole visible-publication timing source. Harness-forced exact refresh, Qt event drain, render callback, readback, and post-readback drain are separate non-additive phases.
- Fast-pan retained-row publication is coalesced to one refresh per GUI frame while the exact viewport remains inside the current retained region. A strict-viewport escape forces an immediate refresh; stress evidence should therefore report both bounded delegate counts and visible-host continuity rather than treating offscreen timing alone as UX acceptance.
- The canonical drag control uses `12` offsets and reports first offset, steady offsets, full gesture, and end/clear separately. The legacy single-offset value is continuity-only; the selected three-node control is supplemental diagnostic evidence and never replaces formal display gates.
- The `node_insertions` scenario measures confirmed insertion dispatch, including synchronous undo capture, through the first later `QQuickWindow.afterRendering` frame where every inserted active-scope primary `graphNodeCard` is visible with non-zero bounds. It runs `ordinary_node`, `group_backdrop`, `small_custom_workflow`, and `nested_custom_workflow` profiles with `3` warmups per profile and a `40`-sample measured budget balanced round-robin across those profiles by default, reports p50/p95, excludes readback and heavy-content readiness, and applies the strict `<100 ms` p95 gate only to display-attached Windows/D3D11 runs.
- Retained reports containing `current_creation_profile` are historical evidence superseded by creation-profile removal. Preserve them, but do not treat that profile as part of the current harness contract.
- Retain wall-clock insertion evidence only from an otherwise idle machine. Concurrent test/build agents contend with Qt's GUI/render callbacks; use unrelated load, pan/zoom, and no-readback frame controls to identify a contaminated run and keep those results diagnostic rather than replacing the retained baseline.
- `tests/test_track_h_perf_harness.py` owns baseline-compatible membership-freeze feature detection, attribution sums, and selected-control report schema. The retained interpretation lives in `COREX_INTERNAL_PERFORMANCE_IMPROVEMENT_QA_MATRIX.md`.
- `graph_mutations` accepts repeatable `--mutation-scenario` filters in canonical order; omitting the option runs all seven cases. `create_edge` measures programmatic production mutation dispatch through the first rendered frame, not pointer travel, port hit-testing, or the pointer gesture used to create an edge.
- Repeated baselines use isolated child processes by default. Completed and failed run JSON files are replaced atomically in the report directory, later runs continue after a child failure, and the aggregate records completed/failed counts plus failure details. `--baseline-in-process` is a diagnostic opt-out only.
- Harness progress is one flushed bounded line per mutation scenario and baseline run. `--compare-to` prints only the fixed load, pan/zoom, steady-drag, mutation-wall-p95, and RSS scalar table; it never expands `baseline_series` or raw sample arrays.
- Feature-parity evidence includes the default-on `graphics_notched_ports` preference as `notched_ports_enabled`; a disabled notch treatment is a zero-loss failure just like hidden grid, minimap, shadows, or port labels.
- The `animated_media` scenario creates input-hidden `media.panel` fixtures with authored GIF sources, uses `--nodes` with `--edges 0`, and reads the generic `GraphNodeHost.inVisibleViewport` fact. It reports confirmed animator instances, visible/playing/idle/offscreen counts, preview states, policy violations, process CPU, and RSS. Offscreen/software runs are regression evidence; retain three-run 20- and 100-panel CPU/RSS results as release baselines rather than absolute resource gates.
- The engineering-viewer benchmark generates CAD/FE overlay geometry under
  `artifacts/`, drives the real asynchronous binder, and accepts release metrics
  only on display-attached Windows with Qt Quick `Direct3D11Rhi`. Its retained
  report covers interaction p95, full-detail restoration, warm coarse frame,
  maximum UI-thread stall, and release-on-close.
- `scripts/profile_canvas_lag.py --engineering-step <path>` runs one production CAD Import/Model Viewer flow without a second benchmark framework. Its ordered phases prove initial proxy/no warm-up; selection, hover, and single-click inactivity; proxy-viewport double-click activation; temporary wheel/box/drag/resize/wire suppression; background demotion; retained reactivation; unrelated graph mutations; and deletion. Reports separate transition, continuous, and restoration counters plus `afterRendering` frame intervals, widget identity, binder lifecycle, cached-preview, native-geometry, and overlay-sync evidence.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --help
.\venv\Scripts\python.exe scripts/profile_canvas_lag.py --selection --qt-platform windows --qsg-rhi-backend d3d11 --samples 20 --warmup 3 --output-path artifacts/canvas_lag_profiling/inspector_selection/windows_d3d11.json
.\venv\Scripts\python.exe -m pytest tests/test_track_h_perf_harness.py --ignore=venv -q
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --scenario node_insertions --nodes 200 --edges 320 --seed 1337 --node-insertion-samples 40 --node-insertion-warmup-samples 3 --baseline-runs 1 --baseline-mode interactive --qt-platform windows --qsg-rhi-backend d3d11 --report-dir artifacts/perf_benchmarks/node_insert_typical
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --scenario node_insertions --stress-fixture real --node-insertion-samples 40 --node-insertion-warmup-samples 3 --baseline-runs 1 --baseline-mode interactive --qt-platform windows --qsg-rhi-backend d3d11 --report-dir artifacts/perf_benchmarks/node_insert_stress
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --scenario graph_mutations --mutation-scenario create_edge --nodes 12 --edges 20 --load-iterations 1 --interaction-samples 1 --interaction-warmup-samples 0 --baseline-runs 1 --qt-platform offscreen --qsg-rhi-backend software --report-dir artifacts/perf_benchmarks/create_edge_smoke
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --scenario graph_mutations --mutation-scenario create_edge --baseline-runs 3 --compare-to artifacts/perf_benchmarks/reference/track_h_benchmark_report.json --report-dir artifacts/perf_benchmarks/current
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness --scenario animated_media --nodes 20 --edges 0 --baseline-runs 3 --qt-platform offscreen --qsg-rhi-backend software
.\venv\Scripts\python.exe -m ea_node_editor.ui.perf.engineering_viewer_benchmark --report-dir artifacts/engineering_viewer_benchmark --resolution 160 --interaction-samples 20 --qt-platform windows --qsg-rhi-backend d3d11
```

## Breadcrumbs
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)
- [Packaging And Generated Assets](../subsystems/packaging_generated_assets.md)
- [Track H Benchmark Report](../../specs/perf/TRACK_H_BENCHMARK_REPORT.md)
- [Graph Canvas Perf QA Matrix](../../specs/perf/GRAPH_CANVAS_PERF_QA_MATRIX.md)
- [COREX Change Locality QA Matrix](../../specs/perf/COREX_CHANGE_LOCALITY_QA_MATRIX.md)
- [COREX Internal Performance Improvement QA Matrix](../../specs/perf/COREX_INTERNAL_PERFORMANCE_IMPROVEMENT_QA_MATRIX.md)
- [Engineering Viewer Native Performance Report](../../specs/perf/ENGINEERING_VIEWER_V1_NATIVE_PERF_REPORT.md)

## Update Triggers
Update when performance harness flags, activity-property names, viewport-fact reporting, stress fixtures, graph performance packets, benchmark commands, or mutation-churn closeout proof paths change.
