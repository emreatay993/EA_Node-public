# Global Gap Break Edge Crossing Variant QA Matrix

- Updated: `2026-03-29`
- Packet set: `GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT` (`P00` through `P03`)
- Scope: final closeout matrix for the shipped canvas-global `edge_crossing_style` preference, gap-break renderer adoption, and traceability/docs evidence.

## Locked Scope

- `graphics.canvas.edge_crossing_style` remains a canvas-global app preference limited to `none` and `gap_break`; the default is `none`.
- The shipped UI surface is one Graphics Settings `Crossing style` control; there is no per-edge override.
- Gap breaks are render-only decoration: hit testing, culling, routing, label anchors, arrowheads, selection geometry, and stored graph data continue to use the original edge path.
- Crossing priority remains deterministic: previewed and selected edges render above non-previewed/non-selected edges, and remaining ties resolve by visible-edge payload order.
- Gap sizing stays in screen space and does not mutate stored graph coordinates or expand `.cxproj` persistence payloads.

## Retained Automated Verification

| Coverage Area | Packet | Primary Requirement Anchors | Command | Recorded Source |
|---|---|---|---|---|
| Preference pipeline, Graphics Settings wiring, and app-preference persistence | `P01` | `REQ-UI-033`, `AC-REQ-UI-033-01` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_graphics_settings_preferences.py tests/test_graphics_settings_dialog.py tests/graph_track_b/qml_preference_bindings.py tests/main_window_shell/shell_basics_and_search.py --ignore=venv -q` | PASS in `docs/specs/work_packets/global_gap_break_edge_crossing_variant/P01_edge_crossing_preference_pipeline_WRAPUP.md` (`8a4e163aaed20d42af09e4457d969209920dd425`) |
| Gap-break renderer ordering, hit-geometry preservation, and suppression behavior | `P02` | `REQ-PERF-009`, `AC-REQ-PERF-009-01` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/graph_track_b/qml_preference_bindings.py tests/test_flow_edge_labels.py --ignore=venv -q` | PASS in `docs/specs/work_packets/global_gap_break_edge_crossing_variant/P02_gap_break_renderer_adoption_WRAPUP.md` (`86e214a11b2590a35d04c51a2b1f8ebcded9bf47`) |

## 2026-03-29 Execution Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q` | PASS | Packet-owned traceability tests confirmed the new requirement anchors, QA matrix facts, and traceability rows for the edge-crossing closeout surface |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | Review-gate proof audit passed after the index, requirements, QA matrix, and traceability updates landed in this packet worktree |

## Remaining Manual Smoke Checks

1. Desktop Graphics Settings check: start the app in a desktop Qt session, open `Settings > Graphics Settings`, and confirm `Crossing style` offers only `None` and `Gap break`, defaults to `None` in a clean app-preferences state, and restores the last saved choice after relaunch.
2. Crossing decoration check: load a graph with intersecting edges, switch `Crossing style` between `None` and `Gap break`, and confirm only the under-edge gains a visual gap while labels, arrowheads, and general edge routing stay unchanged.
3. Priority and hit-testing check: with `Gap break` enabled, select or preview one of two crossing edges, then click through the visible break area on the under-edge path. Confirm the selected/previewed edge renders continuously above the other edge, and the under-edge remains hittable on its original geometry even inside the visible gap.

## Residual Desktop-Only Validation

- Offscreen automated coverage does not validate final stroke-cap aesthetics, anti-aliasing, or perceived gap width on a real Windows desktop compositor.
- The contract intentionally keeps hit testing on the original path geometry, so manual desktop QA should confirm that selecting through the visual gap matches user expectations.
- No packet in this set adds per-edge overrides or persistence-payload changes; future follow-up work must revalidate this matrix if that contract changes.

## Residual Risks

- Closeout evidence is split across retained `P01` and `P02` wrap-ups plus this `P03` packet because the packet spec keeps the closeout verification narrow to docs/traceability.
- Manual desktop validation remains the only proof for final visual polish under the actual GPU-backed Qt path.
