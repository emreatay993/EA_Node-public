# Plan: Explicit-On-Demand Model Viewer Interaction

## Summary

Replace automatic Model Viewer activation with a strict, explicit interaction model:

- A newly executed Model Viewer starts as a lightweight proxy/placeholder.
- Selection, hover, and single-click never create or activate the native viewer.
- Double-clicking inside the proxy viewport activates inline live mode.
- Losing node selection, clicking the canvas, or deactivating the workspace returns the viewer to proxy mode.
- Fullscreen and detached viewing are separate explicit live requests.
- Obsolete automatic-live, initial warm-up, Keep Live, focus-policy, benchmark, and test code will be deleted rather than retained behind compatibility paths.
- One previously activated widget may remain hidden and non-updating for fast reactivation. A viewer that has only been opened fullscreen/detached is not eligible for inline retention.

Implementation begins only after this plan is saved, locked in the task ledger, and reread by the orchestrator at implementation start.

## Implementation Ledger

Baseline and exclusions:

- Branch: `main`
- Historical plan-start baseline `HEAD`: `030b7b23e197d14b6c2e8c438857f615a33656cf`
- Current publication base `HEAD`: `9d62955db1d929753acc1cf1f1a10ad7df6a797e`; local `main`, `origin/main`, and remote `main` have 0/0 parity at this commit.
- Concurrent user-owned publications preserved in the base: `7047023091359e1d739b1af22e2bef3a0c31746b` (`Fix CAD viewer rendering`), `2e9a7a5bbc00b427aaa19d8da3a970fca0e809e0` (`Restore CAD viewer lighting`), and `9d62955db1d929753acc1cf1f1a10ad7df6a797e` (`Hide CAD viewer footer metadata`).
- These concurrent CAD scalar/edge, lighting, and footer changes publish no explicit-live work and must not be amended or reverted.
- Accepted bootstrap SHA256: `DE5F8B964EA19EEB4ABDB67B5F86A0F9CF954C7FB95EFEEFC288D33D8DEF1152`
- Excluded unrelated dirty paths:
  - `docs/specs/INDEX.md`
  - `docs/PLAN_COREX_Physical_Simulation_Backend.md`
- No packet owner is assigned until the orchestrator dispatches that packet.
- This ledger is the durable source of packet status and must be reconciled with Git before every assignment, acceptance, commit, or push.

| Packet | Task | Owner | Dependencies | Write scope | Status | Deliverables | Verification | Diff evidence | Deviation | Commit | Remaining risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P00 | Bootstrap: save and lock this plan | `/root/plan_ledger_owner` | None | This plan only | Accepted | 523-line durable plan | `git diff --check` and Markdown links passed | New plan file | Personal benchmark path neutralized for public privacy | Pending | None |
| P01 | T01 Session Contract Cleanup | `/root/cad_scene_trace` | P00 | Existing `viewer_session_bridge.py` and focused bridge test scope only | Accepted | Generic stale-failure guard ignores nonempty mismatched `request_id` values before they can overwrite newer state or clear pending work; empty-ID and current-ID failures remain unchanged; query and close paths are unchanged; no new policy layer | Exact failure-order cases: 3 passed; full bridge: 36 passed plus 15 subtests; compile, audit, and scoped diff checks passed | `viewer_session_bridge.py` and its focused tests only | Approved bounded failure-order correctness remediation from second independent review | Pending | None |
| P02 | T02 Explicit Viewer Gesture | `/root/viewer_regression_history` | P01 | T02 scope plus `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml`, `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeSurfaceBridge.qml`, and `tests/test_graph_canvas_frame_coalescing.py` | Accepted | Proxy `TapHandler.onTapped` selects immediately; the same `TapHandler` uses `exclusiveSignals: TapHandler.DoubleTap` so `doubleTapped` repeats idempotent selection, then uses `Qt.callLater` to activate only when selected; deselection and session loss cancel a queued request; the full actual-pointer sequence passes without latent activation | Focused surface/contract/canvas tests: 42 passed plus 18 subtests; full actual-pointer sequence passed; compile and scoped diff check passed; manual PASS with zero retries: selected activation, deselection demotion, deselected-proxy double-click select-and-activate, and title single-select remaining proxy | Existing P02 files plus `GraphCanvasNodeDelegate.qml`, `GraphCanvasNodeSurfaceBridge.qml`, and `tests/test_graph_canvas_frame_coalescing.py` | Approved bounded cleanup/correctness extension implementing the locked interaction contract plus exact test-scope extension to `tests/test_graph_canvas_frame_coalescing.py`; no new behavior | Pending | None for the explicit activation contract; detached behavior remains owned by P03/P07 |
| P03 | T03 Presentation Holds and Retention | `/root/model_viewer_perf_review` | P01 and T02 contract | Existing binder lifecycle source/test scope only | Accepted | Terminal detached release follows prepare, binder release, detach, then the existing close plus `deleteLater` exactly once; nonterminal redock performs no close; parentless renderer and handoff behavior remain | Focused lifecycle: 3 passed; binder: 22 passed; host: 54 passed; compile and scoped diff checks passed | Existing engineering viewer binder and lifecycle tests only | Approved bounded terminal-ownership remediation from second independent review | Pending | None |
| P04 | T04 Canvas Hold Regression | `/root/canvas_delta_viewer_trace` | P00 | Existing graph input and exact selection/focus test scope only | Accepted | Eager background `clearViewerFocus` is removed; authoritative `selection_changed` demotes only on actual selection loss; additive Ctrl/Shift/W marquee or wire selection preserving the viewer keeps full; ordinary empty click still demotes | Exact selection regression: 1 passed; full frame-coalescing module: 12 passed; concurrency prehash remained stable | Existing graph input QML and focused tests only | Approved bounded selection-authority remediation from second independent review | Pending | None |
| P05 | T05 Engineering Benchmark | `/root/cad_canvas_benchmark_impl` | P01-P04 | Existing profiler/evaluator source/test scope only | Accepted | Nested and top-level engineering renderer diagnostics consistently report `grab_window_readback_included=false`; evaluator rejects contradictory nested metadata; thresholds and production behavior remain unchanged | Full profiler: 46 passed plus 6 subtests; compile and scoped diff checks passed; no benchmark rerun required under user narrowing | `scripts/profile_canvas_lag.py` and `tests/test_track_h_perf_harness.py` only | Approved bounded evidence-consistency remediation from second independent review | Pending | None |
| P06 | T06 Test and Documentation Cleanup | `/root/viewer_benchmark_path` | P01-P05 | `docs/agent_maps/feature_routes/viewer_session_overlay_fullscreen.md` only | Accepted | Map now states that transient interactions retain the explicit/full session, locally suppress the overlay, and send zero worker updates | Agent-map, Markdown-link, contradiction, and scoped diff checks passed; generated indexes did not embed the sentence, so no regeneration was needed | One viewer-session map; no generated artifact change | Approved bounded documentation correction from second review; production behavior remains accepted | Pending | None |
| P07 | T07 Independent Verification | `/root/viewer_perf_attribution` | P01-P06 | Read-only except ignored benchmark and verification artifacts | Accepted | Explicit user-narrowed final targeted verification passes after the P04 direct scheduler fix; all prior focused, GUI, release, lifecycle, mutation, and manual acceptance evidence remains accepted | Post-fix two-sequence p95: S1 proxy/live 25.84/30.78 ms, S2 proxy/live 30.07/27.48 ms, all no greater than 33.3 ms; improvement 28.0-45.7%; dispatch p95 improved 18.1-48.4%; environment Windows/Direct3D11Rhi/QQuickWidget/DPR2 with feature parity and no readback; zero binder, render, load, release, or execution updates; post-idle native restoration occurred outside measured samples | `artifacts/canvas_lag_profiling/zoom_discriminator_20260827/zoom_discriminator_after_frame_scheduler_ref.json` | Explicit user-narrowed final verification accepted; no broad rerun or new CV gate | Pending | None |
| P08 | T08 Independent Review | `/root/explicit_live_second_review` | P07 | Read-only | Accepted | Original and second independent reviews are clear with no remaining findings | Final P01 stale-failure branch and all previously accepted remediation/evidence rereviewed against current source, tests, maps, plan, and ledger; no broad rerun required | Read-only final publication-readiness review | None | Pending | None |
| P09 | T08 Publication | `/root/explicit_live_publisher` | P08 and accepted remediation | Exact 53-path inventory below; Git state only | Active/Authorized | Publish one atomic commit because T01-T06 production, tests, generated indexes, documentation, and this ledger are cross-dependent; preserve all concurrent user-owned commits | Publication base local `HEAD`/`origin/main` `9d62955db1d929753acc1cf1f1a10ad7df6a797e` at 0/0 parity; stage only the exact inventory; exclude `docs/specs/INDEX.md` and `docs/PLAN_COREX_Physical_Simulation_Backend.md`; run staged privacy/provenance scan, `git diff --cached --check`, commit, push, and verify local/tracking/remote parity; no broad rerun required | Exact 53 paths listed below | One atomic commit is required because no T01-T06 slice is independently publishable from its tests/docs/ledger; concurrent commits remain immutable | publication commit containing this ledger | None |

### P09 Authorized Staging Inventory (48 retained paths)

2. `docs/PLAN_COREX_Model_Viewer_Explicit_Live_Interaction.md`
3. `docs/agent_maps/feature_routes/graph_canvas_input_layers.md`
4. `docs/agent_maps/feature_routes/neutral_cad_fe_engineering_viewer.md`
5. `docs/agent_maps/feature_routes/performance_harness_graph_stress.md`
6. `docs/agent_maps/feature_routes/viewer_session_overlay_fullscreen.md`
7. `docs/agent_maps/subsystems/viewer_surfaces.md`
8. `docs/agent_route_index.json`
9. `docs/agent_route_index.md`
10. `docs/fix_empty_proxy_pane_on_viewer_blur.md` (delete)
11. `docs/qml_navigation_index.json`
12. `docs/qml_navigation_index.md`
14. `docs/specs/requirements/20_UI_UX.md`
15. `docs/specs/requirements/40_NODE_SDK.md`
16. `ea_node_editor/execution/viewer_session_service.py`
19. `ea_node_editor/nodes/builtins/engineering_viewer.py`
20. `ea_node_editor/ui/dialogs/input_reference_dialog.py`
21. `ea_node_editor/ui/shell/composition/runtime_services.py`
22. `ea_node_editor/ui/shell/window.py`
23. `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurface.qml`
24. `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurfaceBody.qml`
25. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasFrameScheduler.qml`
26. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml`
27. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml`
28. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeSurfaceBridge.qml`
29. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasViewportController.qml`
30. `ea_node_editor/ui_qml/embedded_viewer_overlay_manager.py`
31. `ea_node_editor/ui_qml/engineering_viewer_widget_binder.py`
32. `ea_node_editor/ui_qml/viewer_host_service.py`
33. `ea_node_editor/ui_qml/viewer_session_bridge.py`
34. `scripts/profile_canvas_lag.py`
35. `tests/graph_surface/media_and_scope_suite.py`
36. `tests/test_content_fullscreen_bridge.py`
38. `tests/test_embedded_viewer_overlay_manager.py`
39. `tests/test_engineering_viewer_example_project.py`
40. `tests/test_engineering_viewer_node.py`
41. `tests/test_engineering_viewer_widget_binder.py`
42. `tests/test_execution_viewer_protocol.py`
43. `tests/test_execution_viewer_service.py`
44. `tests/test_graph_canvas_frame_coalescing.py`
45. `tests/test_shell_project_session_controller.py`
46. `tests/test_shell_run_controller.py`
47. `tests/test_shell_window_lifecycle.py`
48. `tests/test_traceability_checker.py`
49. `tests/test_track_h_perf_harness.py`
50. `tests/test_viewer_host_service.py`
51. `tests/test_viewer_session_bridge.py`
52. `tests/test_viewer_surface_contract.py`
53. `tests/test_viewer_surface_host.py`

## T00 — Mandatory Orchestration Operating Model

This operating model applies during planning, exploration, implementation, verification, review, remediation, committing, and pushing.

### Parent orchestrator responsibilities

The parent agent will:

- Remain orchestration-only.
- Maintain the full plan and task ledger.
- Delegate all repository exploration, source edits, test edits, documentation edits, test execution, benchmark execution, review, remediation, Git staging, commits, and pushing.
- Assign one owner to each overlapping file family.
- Compare every returned result with the assigned packet and ledger.
- Reject unjustified scope expansion.
- Return legitimate findings to the owning implementation agent rather than fixing them directly.
- Prevent implementation while an exploration pass affecting the same scope is active.
- Ensure every implementation packet names its exact write scope, deliverables, tests, non-goals, and stopping condition.

The parent will not:

- Edit production code, tests, documentation, or generated artifacts.
- Produce its own correctness review as a substitute for delegated review.
- Silently broaden a packet.
- Allow compatibility shims, new policy layers, widget pools, or speculative abstractions.
- Accept "tests pass" without exact commands and outcomes.
- Permit two subagents to edit the same file family concurrently.

### Task ledger

The plan document maintains a ledger with these fields:

| Field | Required content |
|---|---|
| Task | Stable `Txx` identifier |
| Owner | Assigned subagent |
| Dependencies | Tasks that must already be accepted |
| Write scope | Exact files or narrowly bounded file family |
| Status | Pending, active, review, remediation, accepted, committed |
| Deliverables | Expected code, deletions, tests, docs, or reports |
| Verification | Commands and exact outcomes |
| Diff evidence | Changed paths and summary |
| Deviation | None, or evidence-backed explanation |
| Commit | Commit SHA after acceptance |
| Remaining risk | Known unresolved concern or `none` |

### Implementation start and context-compaction recovery

Before the first implementation packet is issued, the orchestrator must:

1. Reread this entire full plan from disk.
2. Reread the complete current Implementation Ledger.
3. Reread the repository `AGENTS.md`.
4. Check the current branch, `HEAD`, working-tree status, accepted commits, and active subagents.
5. Reconcile the ledger with the actual Git state.
6. Supply every assigned subagent with the relevant locked behavior, dependencies, write scope, exclusions, and current ledger state.
7. Begin implementation only after confirming that P00 is accepted and the excluded dirty paths remain untouched.

After every context compaction, before issuing another task, accepting work, changing scope, committing, or pushing, the orchestrator must:

1. Reread this entire full plan from disk.
2. Reread the complete current Implementation Ledger.
3. Reread the repository `AGENTS.md`.
4. Check the current branch, `HEAD`, working-tree status, accepted commits, and active subagents.
5. Reconcile the ledger with the actual Git state.
6. Resupply every active or newly assigned subagent with the refreshed contract, dependencies, accepted deviations, and current ledger state.
7. Resume only after confirming that no work packet has been lost, duplicated, or assigned from stale context.

The orchestrator may not rely only on a compacted conversation summary.

### Drift control

A deviation is acceptable only when a subagent finds unforeseen source evidence demonstrating that the deviation:

- is required for correctness; or
- removes more obsolete code; or
- materially reduces duplicated state or ownership; or
- produces a cleaner and more maintainable implementation without changing the locked user behavior.

The subagent must report before widening its write scope:

- the unexpected fact;
- the planned approach;
- the proposed deviation;
- affected files and tasks;
- why the deviation is cleaner;
- new or changed verification.

The orchestrator may approve bounded technical deviations. Any deviation that changes the user-facing interaction contract, persistence, external formats, or viewer capabilities requires user approval.

## Key Changes

### Locked user interaction contract

1. **Initial state**
   - Model Viewer session opens in `proxy`.
   - No native widget is created.
   - No dataset is loaded into a GUI binder.
   - No hidden initial live warm-up is permitted.
   - Until the first live activation, the proxy displays a lightweight placeholder such as "Double-click to activate 3D view."

2. **Selection and hover**
   - Single-click selects the graph node only.
   - Hover may change normal visual affordances but cannot activate live mode.
   - Selecting a ready viewer cannot create a native widget.
   - Reselecting a previously demoted viewer cannot reactivate it.

3. **Explicit activation**
   - Only a left-button double-click inside the proxy viewport activates inline live mode.
   - Double-clicking the title, node body outside the viewport, ports, canvas, or another node cannot activate it.
   - Only one inline viewer may be explicitly active per workspace.

4. **Focus loss**
   - Selecting another node, clearing selection, clicking the canvas, closing the session, invalidation, workspace change, or window deactivation demotes inline live mode to proxy.
   - The viewer remains proxy after reselecting it until another viewport double-click.

5. **Continuous interaction**
   - Dragging or resizing the currently active viewer does not lose its explicit activation.
   - Wheel zoom, box zoom, node drag/resize, canvas pan, and wire drag temporarily suppress the native overlay.
   - When the gesture ends, live presentation returns only if explicit activation remains valid.
   - A canvas click that clears selection permanently demotes the viewer.

6. **Fullscreen and detached**
   - Opening fullscreen or detached view from an initial proxy is an explicit live request.
   - A presentation hold keeps it full while that presentation exists, regardless of graph selection.
   - Closing a fullscreen/detached viewer opened from proxy returns it to proxy and releases it.
   - If it was explicitly inline-live beforehand and remains selected, closing the external presentation restores inline live mode.

7. **Retention**
   - At most one widget previously created by explicit inline activation may be retained hidden.
   - Retained means invisible, non-interactive, and updates disabled.
   - Retention must produce no rendering or native geometry work.
   - A fullscreen-only or detached-only widget is not eligible for automatic inline retention.
   - Session close, node deletion, invalidation, backend/transport identity change, replacement, workspace loss, reset, or shutdown releases it exactly once.

8. **Keep Live**
   - The inline Keep Live action is removed.
   - `live_policy`, `keep_live`, `set_live_policy()`, and `set_keep_live()` are removed from internal session projection and built-in defaults.
   - `live_mode=proxy|full` remains.

## Public Interface Changes

- Model Viewer proxy viewport gains a documented double-click activation gesture.
- Selection and hover stop activating the viewer.
- The Keep Live viewer action is removed.
- Initial proxy state may show a placeholder instead of a rendered CAD image until the user activates the viewer once.
- Reselecting a viewer no longer restores live mode automatically.
- Existing fullscreen, detached, camera, playback, screenshot, and export controls remain.
- Internal `focus_session()` and focus-only/keep-live policy APIs are removed where no longer used.

## Execution Tasks

### T01 — Remove the obsolete session policy

- **Goal:** Replace focus-policy arbitration with one explicit inline-active key plus existing presentation holds.
- **Preconditions:** T00 accepted; implementation based on `main` at `030b7b23` unless the ledger records a newer accepted baseline.
- **Conservative write scope:**
  - `ea_node_editor/execution/viewer_session_service.py`
  - `ea_node_editor/ui_qml/viewer_session_bridge.py`
  - `ea_node_editor/nodes/builtins/engineering_viewer.py`
  - `tests/test_viewer_session_bridge.py`
  - `tests/test_execution_viewer_service.py`
  - `tests/test_engineering_viewer_node.py`
- **Deliverables:**
  - Delete `live_policy` and `keep_live` projection fields and defaults.
  - Delete their normalization and command slots.
  - Delete `focus_session()` and the focused-node map/helper family.
  - Simplify `clear_viewer_focus()` to clear explicit inline-active keys.
  - Make `set_embedded_interaction_active(True)` exclusively activate one inline viewer per workspace and demote any previous one.
  - Make selection loss remove explicit activation.
  - Make `_desired_live_mode_map()` return full only for the explicit inline key and presentation holds.
  - Delete tests authorizing Keep Live and automatic selection activation.
  - Rewrite session tests around initial proxy, explicit activation, exclusive arbitration, demotion, and presentation holds.
- **Verification:**
  - Focused bridge, execution-service, and engineering-viewer tests.
  - Zero remaining production references to `keep_live`, `live_policy`, `set_keep_live`, `set_live_policy`, and `focus_session`, except deliberate migration documentation if any.
- **Non-goals:**
  - Do not remove `live_mode`.
  - Do not change transport descriptors or worker scene ownership.
  - Do not add a replacement policy abstraction.
- **Packetization notes:** `P01`; may run in parallel with T04 because their write scopes do not overlap.

### T02 — Implement explicit proxy double-click activation

- **Goal:** Make double-click inside the proxy viewport the only inline activation gesture.
- **Preconditions:** T01 contract accepted.
- **Conservative write scope:**
  - `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurfaceBody.qml`
  - `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurface.qml`
  - `tests/test_viewer_surface_host.py`
  - `tests/test_viewer_surface_contract.py`
- **Deliverables:**
  - Delete `hostSurfaceActive`, viewport-hover activation, Keep Live action plumbing, initial warm-up state/functions, implicit focus calls, and obsolete hover forwarding.
  - Remove the initial native warm-up.
  - Add explicit inline-live request state owned by the viewer surface.
  - Single tap selects the node but does not activate the viewer.
  - Double tap inside the proxy viewport requests inline live mode once.
  - Clear the explicit request on deselection, identity change, session close, invalidation, run-required state, or destruction.
  - Preserve deferred `Qt.callLater` synchronization to avoid the known binding loop.
  - Ensure playback, camera, screenshot, fullscreen, and detached actions do not implicitly activate inline mode.
- **Verification:**
  - Initial selected viewer remains proxy with zero activation.
  - Hover and single click remain proxy.
  - Proxy viewport double-click activates exactly once.
  - Double-click outside the viewport does not activate.
  - Deselect demotes; reselect remains proxy.
  - No initial warm-up or native-widget request occurs.
- **Non-goals:**
  - Do not redesign general graph-node double-click behavior.
  - Do not change plot-surface hover behavior.
  - Do not introduce a reusable gesture framework.
- **Packetization notes:** `P02`; one QML owner only.

### T03 — Make external presentations explicit and retention eligibility precise

- **Goal:** Make fullscreen/detached activation independent of removed focus policy while retaining only widgets created by explicit inline activation.
- **Preconditions:** T01 accepted; T02's explicit-inline state contract available.
- **Conservative write scope:**
  - `ea_node_editor/ui_qml/viewer_host_service.py`
  - `ea_node_editor/ui_qml/embedded_viewer_overlay_manager.py`
  - `tests/test_viewer_host_service.py`
  - `tests/test_embedded_viewer_overlay_manager.py`
  - `tests/test_content_fullscreen_bridge.py`
- **Deliverables:**
  - Detached open acquires a presentation hold without `focus_session()`.
  - Fullscreen open/target change/close acquires and releases its own hold.
  - Hold cleanup accounts for both detached and fullscreen ownership.
  - Retention eligibility requires prior explicit inline activation.
  - A merely selected, ready, fullscreen-only, or detached-only viewer cannot enter the retained-inline slot.
  - Existing identity/revision/backend/session invalidation releases remain destructive.
  - Fix retained-to-detached handoff by restoring `setUpdatesEnabled(True)` before refresh/display.
  - Confirm the same widget is reused without release or rebind.
- **Verification:**
  - Fullscreen and detached open directly from an initial proxy.
  - Their holds survive graph selection loss.
  - Closing a presentation opened from proxy returns to proxy without leaving a retained-inline entry.
  - Explicitly activated inline viewer can be retained and reused.
  - Retained-to-detached widget is update-enabled and repaints.
  - Viewer deletion and invalidation release exactly once.
- **Non-goals:**
  - No widget pool.
  - No parking container.
  - No additional viewer cache.
  - No persistence changes.
- **Packetization notes:** `P03`; may run parallel to T02 only after T01 and only with strict non-overlapping files.

### T04 — Correct wheel-recovery to box-zoom suppression

- **Goal:** Ensure a box zoom always holds native-overlay suppression until release.
- **Preconditions:** T00 accepted; independent of T01-T03.
- **Conservative write scope:**
  - `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml`
  - `tests/test_graph_canvas_frame_coalescing.py`
  - Narrowly related graph-canvas pointer tests only if required.
- **Deliverables:**
  - When box zoom crosses its movement threshold, call `beginViewportInteraction()` whenever `viewportInteractionHeld` is false, even if wheel recovery has left `interactionActive=true`.
  - Preserve idle timing through `noteViewportInteraction()`.
  - Add the real wheel-recovery to paused box-zoom to release regression.
- **Verification:**
  - Wheel recovery cannot end `interactionActive` or native-overlay suppression while box zoom is held.
  - Release remains the only path that permits suppression to clear.
- **Non-goals:**
  - No general input-state rewrite.
  - No timing-constant change unless runtime evidence requires it.
- **Packetization notes:** `P04`; safe to run parallel with T01.

### T05 — Replace the benchmark with one production interaction flow

- **Goal:** Prove the new interaction contract and all requested node/wire mutations using the real STEP workflow.
- **Preconditions:** T01-T04 accepted.
- **Conservative write scope:**
  - `scripts/profile_canvas_lag.py`
  - `tests/test_track_h_perf_harness.py`
  - Benchmark-owned helper code only if an existing helper cannot be reused.
- **Deliverables:**
  - Remove `--engineering-condition`.
  - Make `--engineering-step` run one end-to-end production flow.
  - Drive actual QML input for hover, single click, double-click, canvas click, wheel zoom, and box zoom.
  - Include these labelled phases:
    1. startup proxy
    2. proxy pan control
    3. proxy zoom control
    4. selection without activation
    5. hover without activation
    6. single click without activation
    7. proxy double-click activation
    8. live wheel zoom
    9. live box zoom
    10. active viewer drag
    11. active viewer resize
    12. canvas-click demotion
    13. retained-proxy pan
    14. retained-proxy zoom
    15. double-click reactivation
    16. active wire drag
    17. unrelated property edit
    18. unrelated node add with normal selection behavior
    19. unrelated node delete
    20. unrelated wire create
    21. unrelated wire reroute/reconnect
    22. unrelated wire delete
    23. viewer deletion
  - Separate counters for transition, continuous frames, and restoration.
  - Record widget identity/visibility/update state, retained key, holds, live mode, explicit activation, transport revision, binder calls, widget creation, dataset loads, renders, preview capture, overlay sync classification, native geometry calls, and execution commands.
  - Add a small pure report evaluator with synthetic passing and failing unit tests.
- **Verification:**
  - Profiler contract tests.
  - One diagnostic run using the user-provided STEP benchmark path supplied through `COREX_BENCHMARK_STEP`.
  - No Qt/CAD launch inside ordinary unit tests.
- **Non-goals:**
  - No second benchmark framework.
  - No generalized input-recording system.
  - No committed machine-specific absolute artifact path.
- **Packetization notes:** `P05`; begins only after behavior stabilizes.

### T06 — Remove obsolete tests and documentation, then run a zero-reference audit

- **Goal:** Leave no dead code, stale test contract, or misleading documentation from the old automatic-live design.
- **Preconditions:** T01-T05 accepted.
- **Conservative write scope:**
  - Viewer-related tests named in T01-T05.
  - `ea_node_editor/ui/dialogs/input_reference_dialog.py`
  - `docs/agent_maps/feature_routes/viewer_session_overlay_fullscreen.md`
  - `docs/agent_maps/feature_routes/neutral_cad_fe_engineering_viewer.md`
  - `docs/agent_maps/feature_routes/performance_harness_graph_stress.md`
  - `docs/agent_maps/feature_routes/graph_canvas_input_layers.md`
  - `docs/agent_maps/subsystems/viewer_surfaces.md`
  - Generated route indexes only when their cited paths change.
- **Deliverables:**
  - Delete obsolete warm-up and Keep Live tests rather than skip or rename them.
  - Rewrite tests that previously activated through selection, hover, or `focus_session()`.
  - Document double-click activation and focus-loss demotion.
  - Add the input-reference entry.
  - Remove map statements describing automatic warm-up, automatic focus-only binding, selection/hover promotion, and inline Keep Live.
  - Run exact-symbol and semantic zero-reference searches for removed concepts.
- **Verification:**
  - `check_agent_maps.py`
  - `check_markdown_links.py`
  - Regenerated route index if citations changed.
  - No stale production/test references.
- **Non-goals:**
  - Do not edit `docs/specs/INDEX.md`.
  - Do not touch the unrelated Physical Simulation plan.
  - Do not broadly rewrite viewer documentation.
- **Packetization notes:** `P06`; documentation owner works only after implementation behavior is final.

### T07 — Delegated verification and performance acceptance

- **Goal:** Establish correctness and high-performance acceptance independently of implementers.
- **Preconditions:** T01-T06 accepted; no active editor agents.
- **Conservative write scope:** None, except generated benchmark artifacts under the existing ignored artifact root.
- **Deliverables:**
  - Focused viewer, QML, graph-delta, fullscreen, binder, and profiler results.
  - GUI verification summary.
  - Three isolated display-attached Windows/D3D11 benchmark reports.
  - Manual handoff observation where automation is insufficient.
- **Hard acceptance gates:**
  - Before activation: no widget, bind, load, render, create, or release.
  - Selection, hover, and single-click: all lifecycle counters unchanged.
  - Activation: widget creation/loading occurs only here; transport revision unchanged.
  - Continuous wheel/box/drag/resize/wire gestures: zero bind, release, load, create, or native geometry churn during the measured interval.
  - After a gesture: same widget, visible, update-enabled, and geometry-ready.
  - Demotion: same widget retained hidden without release.
  - Retained-proxy pan/zoom p95 must be no more than 8 ms worse than initial proxy control.
  - Continuous operation timing and frame-interval p95 no greater than 33.3 ms; no greater than 16.7 ms remains the preferred target.
  - Three-run coefficient of variation no greater than 0.20.
  - Unrelated committed node/wire mutations perform zero binder/native work and increment skipped-delta counters.
  - Viewer deletion releases exactly once and clears the projection and retained key.
- **Focused verification:**
  - Surface/QML tests.
  - Session/host/binder/fullscreen tests.
  - Canvas interaction and graph-delta tests.
  - Profiler contract tests.
  - Agent-map and Markdown checks.
- **Broad verification:**
  - `run_verification.py --mode gui --summarize-output`
  - `full` is required only if implementation unexpectedly changes shell composition, startup, persistence, or packaging.
- **Manual acceptance:**
  - No native-window flash or black frame during handoff.
  - Retained-to-detached viewer visibly repaints and resizes.
  - Double-click timing feels normal under Windows DPI and mouse settings.
- **Non-goals:**
  - Offscreen/software results cannot be called release acceptance.
  - Busy-desktop diagnostic timing cannot override failed stable-run thresholds.
- **Packetization notes:** `P07`; verification agent must not be an implementation owner.

### T08 — Independent review, remediation, commit, and push

- **Goal:** Close the plan only after independent review and verified publication.
- **Preconditions:** T07 passes.
- **Conservative write scope:** Review is read-only; remediation returns to the original owner; publication touches Git state only.
- **Deliverables:**
  - Independent diff-versus-plan audit.
  - Regression review covering every changed production file and caller.
  - Obsolete-code audit.
  - Test-quality review distinguishing behavior tests from source-string checks.
  - Performance-evidence review.
  - Remediation packets for every actionable finding.
  - Final accepted commits on `main`.
  - Push to `origin/main`.
  - Verified local, tracking, and remote SHA parity.
- **Review rules:**
  - Reviewer cannot be an implementation agent.
  - Reviewer reports findings only; it does not edit.
  - Findings return to the original packet owner.
  - A second reviewer verifies remediation.
  - The orchestrator compares the final diff, ledger, and plan before authorizing publication.
- **Git rules:**
  - Stage only approved paths.
  - Preserve untouched:
    - `docs/specs/INDEX.md`
    - `docs/PLAN_COREX_Physical_Simulation_Backend.md`
  - Run staged privacy and provenance scans.
  - Run `git diff --cached --check`.
  - Use coherent behavioral commits; interdependent T01-T03 may share one commit because none is independently complete.
  - T04 and T05-T06 may remain separate commits when each accepted state is independently green.
  - Push only after all commits and final review pass.
- **Non-goals:**
  - No unrelated cleanup.
  - No force push.
  - No history rewriting.
- **Packetization notes:** `P08` review, remediation packets as needed, then `P09` publication.

## Work Packet Conversion Map

1. `P00 Bootstrap`: lock the plan, initialize the ledger, record Git baseline and dirty-file exclusions.
2. `P01 Session Contract Cleanup`: T01.
3. `P02 Explicit Viewer Gesture`: T02.
4. `P03 Presentation Holds and Retention`: T03.
5. `P04 Canvas Hold Regression`: T04.
6. `P05 Engineering Benchmark`: T05.
7. `P06 Test/Documentation Cleanup`: T06.
8. `P07 Independent Verification`: T07.
9. `P08 Independent Review`: T08 review portion.
10. Remediation packets: issued only for evidence-backed findings and returned to original owners.
11. `P09 Publication`: exact staging, coherent commits, push, and parity check.

Permitted parallelism:

- `P01` and `P04` may run concurrently.
- `P02` and `P03` may run concurrently only after `P01` and only with non-overlapping files.
- `P05` starts after `P01-P04`.
- `P06`, `P07`, `P08`, and `P09` are sequential.

## Test Plan

The delegated verification agent will run the focused commands identified during planning, followed by:

```powershell
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui --summarize-output
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
```

Display-attached acceptance uses the user-provided STEP file without committing its machine-specific path:

```powershell
$env:COREX_BENCHMARK_STEP = '<user-provided-step-path>'
.\venv\Scripts\python.exe .\scripts\profile_canvas_lag.py `
  --engineering-step $env:COREX_BENCHMARK_STEP `
  --samples 30 `
  --warmup 3 `
  --qt-platform windows `
  --qml-host qquickwidget `
  --qsg-rhi-backend d3d11
Remove-Item Env:COREX_BENCHMARK_STEP -ErrorAction SilentlyContinue
```

It must run three times in isolated processes on a quiet desktop.

## Assumptions

- The implementation baseline is `main` at `030b7b23` unless the P00 ledger records otherwise.
- The two unrelated dirty documentation paths remain user-owned and untouched.
- Showing a placeholder before first explicit activation is acceptable and preferred over hidden native warm-up.
- A hidden retained widget after prior explicit activation is acceptable because it performs no rendering or composition work.
- Breaking internal APIs are allowed; compatibility shims are not required.
- No new dependency is needed.
- This adopts an explicit interaction concept without claiming parity with any third-party product.
- The previous detached repaint and box-zoom findings are part of this plan, not deferred work.

Planning is complete. Repository implementation remains paused until P00 is accepted and the orchestrator begins implementation by rereading this full plan and ledger from disk.
