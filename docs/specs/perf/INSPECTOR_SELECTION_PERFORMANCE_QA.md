# Inspector selection performance

Status: implemented and focused acceptance passed, 2026-09-10.

## Cause and change

Ordinary graph selection already avoided node-payload rebuilding. Its synchronous
inspector notification nevertheless created property editors while Properties
was collapsed. Each property row instantiated every editor type. In particular,
the unused chip-list editor passed numeric scalar properties to a QML Repeater,
where a number means an item count. Selecting a default Signal Plot therefore
created about 50,000 visual items for 25 property rows.

The composed offscreen shell reproduced approximately 2,676 ms selecting and
2,002 ms clearing Signal Plot. Disabling the property body in that diagnostic
reduced these to 32 ms and 8 ms. These were synchronous diagnostic measurements,
not display latency or a matched native before/after benchmark.

The shared inspector now creates only the effective editor type; chip values
must be arrays. Property/group rows retain identity through value refreshes.
Smart Groups and Accordion initialize bodies on first expansion and retain
opened groups for the same selection, preserving drafts. Collapsed Properties
and the Help tab suspend detail and runtime-schema projection. Reopening reads
current metadata; selection changes retire old content. Workspace/node/property
guards prevent stale editor callbacks writing into a different selection.

## Native measurement

```powershell
.\venv\Scripts\python.exe scripts/profile_canvas_lag.py --selection --qt-platform windows --qsg-rhi-backend d3d11 --samples 20 --warmup 3 --output-path artifacts/canvas_lag_profiling/inspector_selection/windows_d3d11.json
```

The recorded run used Windows, Direct3D11Rhi, QQuickWidget, and DPR 2.0. Each
operation has 20 measured samples following three warmup cycles. Production
canvas mouse clicks, selection, shell presenters, inspector, and QML rendering
run with isolated preference/session files and an inert execution client. The
fixture contains Constant, Signal Plot, and Media Panel; grouped layouts start
with their normal closed groups. Palette realizes its property rows.

| Properties layout | Select Signal Plot p95 | Switch back to Signal Plot p95 | Clear Signal Plot p95 |
| --- | ---: | ---: | ---: |
| Collapsed | 36.76 ms | 22.99 ms | 14.16 ms |
| Smart Groups | 61.07 ms | 47.64 ms | 16.31 ms |
| Accordion | 61.41 ms | 52.95 ms | 15.69 ms |
| Palette | 80.65 ms | 68.65 ms | 17.77 ms |

All 24 operation/layout combinations passed the strict **p95 < 100 ms** gate.
The cleared inspector returned to exactly **229 visual items** after every cycle
in all four layouts. A never-opened collapsed inspector creates zero property
editors. An expanded native inspector was also rendered and visually inspected.

Timing ends at `QQuickWindow.afterRendering`, only after synchronization observes
the expected selection on all fixture node cards. It excludes readback, widget
composition, GPU completion, and display presentation. These are click-to-QML-render
measurements, not end-to-end screen presentation latency. The local JSON retains
individual samples, dispatch timings, renderer facts, and object counts.

## Regression evidence

- Inspector projection/reflection, all three layout variants, sensitive controls,
  and graph selection/cache/virtualization routes: **104 tests passed**, plus
  **7 subtests**.
- Composed-shell property-editor interactions and hidden-pane lifecycle:
  **10 tests passed**. Includes hidden selection/runtime zero-projection checks,
  same-selection draft retention, and hidden selection replacement.
- Inspector bridge forwarding and QML ownership boundary: **6 tests passed**.
- Matching Qt 6.11 Quick Test SDK: **9 lifecycle checks** and **7 selector checks
  passed**, including setup/cleanup cases. Covers lazy construction, bounded
  scalar work, malformed chip values, stale node/workspace blur callbacks,
  focused draft identity, and exact integer/string selectors.
- Independent read-only reviews checked the QML lifecycle, commit guards,
  activity projection, and render attribution. Main-agent implementation and
  focused verification own the change.
- Agent-map, traceability, Markdown-link, Ruff, and diff hygiene checks passed;
  generated navigation, packaging, and documentation regression checks also
  passed after updating the pinned QML file count for the five new components.

Run the focused Python routes with the project venv. Qt Quick inputs are
`tests/qml_quick/tst_inspector_lifecycle.qml` and
`tests/qml_quick/tst_signal_selectors.qml`; the SDK must match PyQt's Qt
major/minor version. The full verification suite is not claimed by this focused
inspector closeout.

## Ownership

- [QML shell map](../../agent_maps/subsystems/qml_shell_and_bridges.md):
  snapshots, lazy editor bodies, keyed rows, bridge and presenter activity.
- [Performance route](../../agent_maps/feature_routes/performance_harness_graph_stress.md):
  composed-shell selection profiler and measurement boundaries.
