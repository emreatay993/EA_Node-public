# Graph Canvas Performance QA Matrix

- Status: `PASS`
- Canonical harness: `ea_node_editor.ui.perf.performance_harness`
- Canonical artifacts: `artifacts/graph_canvas_perf_docs/TRACK_H_BENCHMARK_REPORT.md` and `artifacts/graph_canvas_perf_docs/track_h_benchmark_report.json`

## Locked Scope

- Exercise the real `ea_node_editor/ui_qml/components/GraphCanvas.qml` path.
- Record scenario, graph size, sample counts, renderer/backend/host diagnostics, readback semantics, and p50/p95 metrics.
- Keep offscreen/software runs as regression evidence only; display-attached Windows/D3D11 runs own release acceptance.
- Preserve zero-loss checks for grid, minimap, shadows, edge and port labels, embedded media surfaces, and execution visualization.

## Approved Regression Commands

| Purpose | Command | Evidence |
|---|---|---|
| Traceability checker tests | `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q` | Focused checker contract |
| Heavy-media offscreen regression | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m ea_node_editor.ui.perf.performance_harness --nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 --baseline-runs 3 --scenario heavy_media --report-dir artifacts/graph_canvas_perf_docs` | Canonical same-machine regression snapshot |
| Windows desktop reference | `./venv/Scripts/python.exe -m ea_node_editor.ui.perf.performance_harness --nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 --baseline-runs 3 --baseline-mode interactive --baseline-tag desktop_reference --scenario heavy_media --qt-platform windows --report-dir artifacts/graph_canvas_interaction_perf_p09_desktop_reference` | Display-attached qualitative exit gate |
| Proof audit | `./venv/Scripts/python.exe scripts/check_traceability.py` | Requirements, matrix, report, and artifact alignment |

## 2026-03-21 Execution Results

The numeric benchmark results below are retained historical evidence. The benchmark interface has since been simplified, so the current commands must be rerun before using those numbers as a current baseline.

| Command | Result | Evidence |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q` | PASS | Focused checker contract passed after the single-path documentation update |
| `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m ea_node_editor.ui.perf.performance_harness --nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 --baseline-runs 3 --scenario heavy_media --report-dir artifacts/graph_canvas_perf_docs` | NOT RUN | Retained 2026-03-21 same-machine metrics: load p95 `67.842 ms`, pan p95 `97.890 ms`, zoom p95 `16.657 ms`, node-drag p95 `48.352 ms`; these do not prove the current code |
| `./venv/Scripts/python.exe -m ea_node_editor.ui.perf.performance_harness --nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 --baseline-runs 3 --baseline-mode interactive --baseline-tag desktop_reference --scenario heavy_media --qt-platform windows --report-dir artifacts/graph_canvas_interaction_perf_p09_desktop_reference` | NOT RUN | Retained desktop metrics: load p95 `146.767 ms`, pan p95 `191.553 ms`, zoom p95 `276.627 ms`, node-drag p95 `413.152 ms` |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | Proof audit passed after the requirements and evidence refresh |

## Retained Stress and Mutation Evidence

| Evidence | Result | Interpretation |
|---|---|---|
| Stress-1200 display-final | load p95 `164.320 ms`; pan p95 `99.602 ms`; zoom p95 `80.825 ms`; node-drag p95 `315.023 ms`; no-readback frame p95 `322.075 ms` | `REQ-PERF-003` passes; `REQ-PERF-002` remains failed |
| Mutation-latency final | rename `3809.505 ms`; drag `5590.535 ms`; multi-drag `5296.380 ms`; create-edge `23421.623 ms`; remove-edge `29652.571 ms`; delete-node `31814.525 ms`; undo/redo `20627.377 ms` | Historical same-machine offscreen guardrails, not display acceptance |
| Structural edge delta final | create-edge `5270.063 ms`; remove-edge `7602.023 ms`; delete-node `12520.669 ms`; undo/redo `32280.323 ms` | Ordinary structural dirties stayed at p95 `2` nodes / `1` edge; broad undo/redo remained explicit |

## Desktop/Manual Exit Gate

- Status: `PASS`
- Historical artifact: `artifacts/graph_canvas_interaction_perf_p09_desktop_reference/TRACK_H_BENCHMARK_REPORT.md`
- The 2026-03-21 manual review accepted smoothness and visual parity for that build. It is qualitative historical evidence, not current quantitative release sign-off.

## Limitations

- Offscreen/software timings do not represent desktop compositor cost.
- Readback-inclusive interaction samples and no-readback frame intervals are separate, non-additive metrics.
- Absolute timings are machine- and load-dependent; compare only like-for-like runs.
- No benchmark rerun was required for this interface deletion. Run the approved commands when a fresh performance baseline is needed.
