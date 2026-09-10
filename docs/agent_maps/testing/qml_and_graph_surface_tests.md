# QML And Graph Surface Tests

## Purpose
Use this for graph surface, QML bridge, passive host, inline input, pointer, modal, and graph-track regression routing.

## Start Here
- `tests/qml_quick/tst_graph_node_host.qml`
- `tests/qml_quick/tst_graph_surface_controls.qml`
- `tests/qml_quick/tst_graph_node_toolbar_popover_host.qml`
- `tests/qml_quick/tst_graph_canvas_surface_editor_overlays.qml`
- `tests/qml_quick/tst_edge_paint_policy.qml`
- `tests/qml_quick/tst_secret_editor.qml`
- `tests/graph_surface/`
- `tests/graph_track_b/`
- `tests/test_graph_canvas_split_bridges.py`
- `tests/test_graph_canvas_surface_snapshot.py`
- `tests/test_graph_surface_input_contract.py`
- `tests/test_graph_surface_input_controls.py`
- `tests/test_graph_surface_input_inline.py`
- `tests/test_graph_surface_probe_runner.py`
- `tests/test_boolean_toggle_surface.py`
- `tests/test_select_surface.py`
- `tests/test_trigger_surface.py`
- `tests/test_passive_graph_surface_host.py`
- `tests/test_media_panel_qml_surface.py`
- `tests/test_media_panel_source_resolution.py`
- `tests/test_data_type_ui_projection.py`
- `tests/test_flow_edge_labels.py`
- `tests/test_shell_theme.py`
- `tests/test_passive_image_nodes.py`
- `tests/test_graph_canvas_viewport_virtualization.py`
- `tests/test_viewer_surface_host.py`
- `tests/test_viewer_surface_contract.py`
- `tests/test_viewer_control_bridge.py`
- `tests/test_viewer_host_service.py`
- `tests/test_plot_detached_window.py`
- `tests/test_content_fullscreen_bridge.py`
- `tests/test_content_fullscreen_bridge_lifecycle.py`
- `tests/test_shell_window_lifecycle_isolated.py`
- `tests/test_corex_node_controls_visual.py`
- `tests/mechanical_catalogue/test_visuals.py`
- `tests/fixtures/node_controls/signal_plot_style_node_controls.py`

## Common Changes
- Use graph surface suites for QML node surface and input-contract changes.
- `tests/test_graph_canvas_split_bridges.py` owns the direct state/command bridge contract, while `tests/test_graph_canvas_surface_snapshot.py` freezes the surviving focused-owner meta-object surface against `tests/fixtures/graph_canvas_surface_snapshot.json`.
- Keep Boolean Toggle pill geometry and click-to-property commits in `tests/test_boolean_toggle_surface.py`; its node/runtime contract stays in `tests/test_boolean_toggle_node.py`.
- Keep Select pill geometry, shared Help tooltip, elapsed suppression, dropdown commits, settings draft operations, header/row selection, protected delete, both reorder directions, Cancel/close behavior, and atomic undoable OK persistence in `tests/test_select_surface.py`; its metadata, normalization, runtime, exposed Text Tree output, and persistence contract stays in `tests/test_select_node.py`.
- Keep Trigger pill geometry (both port dots at pill mid-height), rename-following button label, shared Help tooltip on button and pill hover, elapsed suppression, and `triggerNodeRequested` click routing in `tests/test_trigger_surface.py`; its spec copy, surface contract, and size-resolver clamps stay in `tests/test_trigger_node.py`, with sample-and-hold runtime behavior in `tests/test_dataflow_execution_runtime.py`.
- Keep resize-handle click/drag/double-click coverage in `tests/graph_surface/passive_host_interaction_suite.py`; pure-QML fit-width control and widest-row measurement coverage belongs in `tests/qml_quick/tst_graph_surface_controls.qml`.
- Use graph-track suites for scene model projection and behavior contracts.
- Named settings-group coverage is split across `tests/test_graph_scene_presentation_facts.py` (two groups, paired editor overrides, collapsed aggregate anchors, expanded real anchors, unchanged topology/output), `tests/graph_surface/passive_host_interaction_suite.py` (shared host rendering, live resize, signal and duplicate-label guards), `tests/graph_track_b/scene_model_graph_scene_suite.py` (command/history/custom height/collision/global collapse), `tests/test_graph_surface_input_controls.py` (Settings submenu and read-only guards), and `tests/test_viewer_surface_contract.py` (specialized body preservation).
- Use `tests/test_data_tree_ui.py`, `tests/test_graph_surface_input_controls.py`, `tests/test_flow_edge_labels.py`, and graph-track scene suites for read-only Item/List/Tree access, modifier/Principal checks, grip hover/target halo, replacement versus Shift append, bundle Ctrl move versus one-edge Ctrl+Shift copy, edge selection/W-marquee/jump, edge Enable/Ctrl+E, active-data solid/dotted/dashed/double-hairline wire rendering, Default/Faint/Hidden, bounded preview/status projection, and passive/flow isolation. Assert the complete absence of control rows, compact control endpoints, and execution-wire animation.
- `tests/qml_quick/tst_edge_paint_policy.qml` owns direct pure-JS structure/display/marker/drag-preview and `EdgeMath.edgeAnchor(...)` checks. `tests/test_flow_edge_labels.py` retains real Canvas/retained parity, hit geometry, label/crossing, and renderer-fallback integration.
- Use `tests/test_default_port_values.py`, graph-surface input suites, and graph-track scene suites for explicit `default_property` payloads, outlined grips, embedded editor reuse, duplicate-row suppression, override/restoration, and active lock-chrome removal. Keep unavailable add-on placeholder and passive-object lock assertions separate and unchanged.
- Declarative control coverage is split deliberately: `tests/test_registry_validation.py` and `tests/test_decorator_sdk.py` own SDK metadata; `tests/test_interval_1d.py` owns ordered value transport; `tests/test_graph_scene_presentation_facts.py` and `tests/test_default_port_values.py` own authored/display/condition facts; `tests/qml_quick/tst_graph_surface_controls.qml` and graph-surface input suites own shared canvas controls; `tests/test_library_projection.py`, `tests/test_inspector_projection.py`, `tests/test_quick_insert_projection.py`, `tests/test_inspector_smart_groups_variant.py`, and `tests/main_window_shell/view_library_inspector.py` own Library/search/Inspector interaction, settled-wire/authored restoration, and one-undo-entry parity. `tests/fixtures/node_controls/signal_plot_style_node_controls.py` is an internal visual fixture owned by `tests/test_corex_node_controls_visual.py`; it is not a public plugin example or production node.
- `tests/qml_quick/tst_secret_editor.qml` owns the shared masked Replace/Clear control behavior. `tests/test_sensitive_property_controls.py` owns redacted scene/Inspector payloads and the dedicated history-safe secret command path.
- Keep Ctrl-drag coverage on the existing edge/socket interaction path: complete incident-bundle move, sole-or-explicitly-selected one-edge Ctrl+Shift copy, blank disconnect without Quick Insert, metadata/order preservation, invalid/cancel no-op, and one-step undo. Keep held-W logical-route marquee, hidden-route reveal, and Ctrl+Left/Ctrl+Right endpoint jump coverage in the same graph-surface route.
- T08 type UI proof is split deliberately. `tests/test_data_type_ui_projection.py` owns one bounded catalog projection, current-effective-port endpoint snapshots, availability/type-warning separation, and rich-preview redaction/callback/I/O bounds. `GraphSurfaceCanvasInteractionTests.test_ctrl_drag_reassigns_selected_or_sole_edge_endpoint_without_quick_insert` proves one snapshot across repeated moves and release plus malformed/generation fail-closed behavior. `PortTypePresentationQmlTests.test_ports_use_projected_input_state_and_keep_edge_reason_out_of_port_text` and `test_family_accent_binding_updates_when_graph_theme_changes`, together with `ShellThemeServiceTests.test_graph_theme_bridge_resolves_family_tokens_to_the_active_data_role`, own the existing-ring/tooltips/accessibility/non-color cue and theme-reactive fallback.
- Keep edge enabled/order, sparse modifiers, Principal, dynamic-pin access, and format-migration persistence/history coverage in `tests/test_dataflow_graph_persistence.py`, `tests/test_data_tree_ui.py`, and serializer/graph-track suites.
- Use `tests/test_graph_scene_bridge_bind_regression.py` when scene mutation helpers are retargeted to direct graph mutation operations.
- Use `tests/test_mutation_ui_effects.py` for direct shell post-mutation effect semantics; keep scene payload/delta assertions in graph-track tests.
- Keep `QT_QPA_PLATFORM=offscreen` for QML-heavy focused gates.
- Mechanical control acceptance additionally runs `tests/mechanical_catalogue/test_visuals.py` directly in isolated Windows processes at observed effective DPR 1.0 and 1.5. It uses the production GraphCanvas/GraphSceneBridge state+command route, physical window-coordinate clicks, asserted fresh primary/advanced expansion defaults, QML font metrics, and retained captures; its ordinary pytest case remains the offscreen regression smoke.
- `tests/qml_quick/tst_graph_node_host.qml` owns pure `GraphNodeHost` component behavior: surface loading, text rendering, helper-layer stacking, render quality, port visibility, standard data-grip hover growth/compatible-target halo, shadow keys, resize-handle hover, flowchart variants, timestamp actions, planning/annotation host rendering, the library flowchart preview, and Group backdrop title/chrome behavior. It replaces the matching probes from the passive-host, planning, flowchart, and Group Python suites; do not recreate those checks in `run_qml_probe()`.
- T21 extends `tests/qml_quick/tst_graph_node_host.qml` with the direct `GraphNodePortRow` owner contract: normalized descendant/parent topology, exact geometry and Item/Loader/Canvas counts across unlocked and locked input/output rows, direction-only child identity, default override, flow/type/accessibility consumption, and dynamic remove/label-edit geometry. Python graph-surface tests retain scene projection, real mutations/history, host shadow/notch integration, and loaded-surface ownership rather than duplicating the row-local markup checks.
- `tests/qml_quick/tst_graph_node_port_context_menu.qml` owns the direct port Menu root/order/check state, open/close, modifier/Principal/dynamic layer calls, data visibility, and read-only guards. `tests/test_graph_surface_input_controls.py`, `tests/test_data_tree_ui.py`, and `tests/test_dataflow_graph_persistence.py` retain real command, mutation/history, Principal exclusivity, sparse-state cleanup, and persistence behavior.
- `tests/qml_quick/tst_graph_action_presentation.qml` owns pure action descriptor lookup, edge normalization/choices/menu/toolbar state, action fields and child extraction, stable grouping/filtering/checked indexes/menu projection, and node context/common/available action composition. Existing graph-action, context/options, edge/node toolbar, media/viewer/plot, bridge, and snapshot tests retain dispatch, policy, lifecycle, and integration.
- `tests/qml_quick/tst_graph_node_toolbar_popover_host.qml` owns the direct popover root/parent topology, toolbar-coordinate placement, same-owner toggle/flush behavior, bookmark refresh, font-size preview/commit/bounds, PDF navigation, source-storage selection, and font-family focus/filter/dispatch. These replace the five panel-local selectors formerly in `tst_graph_surface_controls.qml`.
- `tests/qml_quick/tst_graph_surface_controls.qml` owns pure-QML graph-surface control geometry, styling, native input, commit timing, dropdown state, filtering, inline fit-width behavior, node-toolbar chrome/primary-button/public-open/run-menu integration, and selection-envelope overlay behavior. Python retains the surrounding source, fullscreen bridge, scene/model, and provider contracts.
- `tests/qml_quick/tst_graph_canvas_surface_editor_overlays.qml` owns direct Web/Timestamp/Number Slider/Select/Panel layer identity, open/focus/position, active-toolbar reopen, outside-click cancellation, and commit callbacks. Real canvas and bridge tests retain loaded-surface identity, GraphCanvas dispatch, scene mutation, and Canvas-export exclusion.
- `tests/test_planning_annotation_catalog.py` retains catalogue and metric facts; `tests/test_flowchart_surfaces.py` retains geometry and Python-owned drop-preview integration; `tests/test_group_backdrop_contracts.py` retains its seven catalogue/model/serialization facts. Their former pure-QML launch wrappers are not fallback coverage.
- Keep Python QML probes for `GraphSceneBridge` and graph-model integration, registries, media providers/decoders, platform behavior, static source contracts, and shared-worker lifecycle/crash recovery. Qt Quick Test does not receive those Python-owned contexts.
- Qt Quick Test is the authoritative pure-QML phase and runs before Python GUI pytest in `gui` and `full`. The repository has no tracked CI workflow; an external job that invokes either mode must provision a matching Qt SDK and expose it through `QT_ROOT` or `PATH`.
- `tests/graph_surface_pointer_regression.py::run_qml_probe` routes probes through one persistent, crash-isolated child per test process. It retains the `QApplication` and import cache while each request receives fresh exec globals; the graph-surface probe setup continues to construct a fresh `QQmlEngine` per probe. A failed worker is discarded before the next probe.
- Its shared `hover_host_local_point` helper always moves outside the host before entering the requested point, so consecutive sibling probes remain order-independent while reusing the same worker.
- Use `tests/test_graph_surface_probe_runner.py` for shared-worker lifecycle, isolation, fault recovery, output, and native-log cleanup coverage.
- `tests/test_passive_graph_surface_host.py` aggregates its passive-host leaf suites. Select the aggregate test or an individual leaf suite, never both in the same command.
- Use `tests/test_viewer_surface_host.py` for viewer cached-preview, embedded interaction, and action-routing probes that instantiate real graph host QML.
- Use `tests/test_viewer_control_bridge.py` for node-scoped viewer options,
  bookmarks/selections/query/export, and projection synchronization. Use
  `tests/test_viewer_host_service.py` for same-widget inline/detached/fullscreen
  ownership, fit/isolate routing, shortcuts, and cleanup.
- Content-fullscreen Python ownership is 42 direct methods plus two mounted methods in `tests/test_content_fullscreen_bridge.py`; `tests/test_content_fullscreen_bridge_lifecycle.py` owns dynamic-provider replacement, required Web artifact storage, terminal no-persist shutdown, signal disconnection, late-work rejection, and lazy tabular reuse. Viewer option/selection/bookmark behavior moved to `tests/test_viewer_control_bridge.py`, same-widget holds/cleanup to `tests/test_viewer_host_service.py`, and executable quick-control/accessibility/shortcut behavior to `tests/test_viewer_surface_contract.py`. Real-shell lifecycle keeps only overlay/viewport/quick-control mount and visibility smoke.
- Use `tests/test_viewer_session_bridge.py` for exact committed projection-snapshot adoption without double increment, direct/project/reset epoch advancement, late response/query/close rejection, and two-viewer projection preservation. Participant-local empty/`None`/scoped matrices, concrete-to-projection response translation, state-before-viewer barrier locking, no-reacquisition delivery, irreversible finalizer/gate cleanup, preflight rollback/buffering, selected-service equality, and worker cleanup stay in the execution client/headless/viewer suites.
- Media Panel direct crop/frame/timestamp/trim ownership lives in `tests/test_media_panel_action_service.py`; QML dispatch, renderer teardown, input-authority action gating, stable metrics, and fullscreen mode changes remain in `tests/test_media_panel_qml_surface.py`. `tests/test_passive_image_nodes.py` retains provider and renderer-source lifecycle checks; use `tests/test_shell_window_lifecycle_isolated.py::test_content_fullscreen_overlay_owns_animated_image_playback` for real-shell fullscreen ownership.
- Exact `GraphNodeHost.inVisibleViewport` geometry, fail-open/edge-contact behavior, live drag/resize, axis-aware retention margins, continuous pan look-ahead, stable host identity, far-behind teardown, per-frame burst coalescing, direction reversal, and strict-viewport emergency refresh belong in `tests/test_graph_canvas_viewport_virtualization.py` and `tests/graph_surface/passive_host_interaction_suite.py`. Keep exact work suspension assertions separate from buffered loader/delegate retention assertions.
- `tests/test_graph_canvas_split_bridges.py` owns the direct graphics/canvas source split, all command routes, and source notification behavior. `tests/test_graph_scene_bridge_bind_regression.py` owns explicit scene-source lifecycle and the four-fact rebuild fingerprint. Use `tests/graph_track_b/qml_preference_bindings.py` and `tests/graph_track_b/qml_preference_rendering_suite.py` for QML preference projections, including plot lightweight-canvas state; `tests/test_media_panel_creation_preferences.py` keeps future-blank-only Media Panel defaults.
- Keep notched-port render coverage in the graph-surface suites: default-on/explicit-off state, no-clip cached 9 x 18 px SVG half-discs for regular data ports, shared-source and input/output mirror behavior, node-contained bounds for retained-edge visibility, Theme/Dark/Light/White canvas-fill matching, curved-edge color/width matching the live chrome outline (including selected state), horizontal-only glow suppression with top/bottom spill retained, default/inactive endpoints, collapsed/chrome-free/flowchart exclusions, inset/full-width shadow geometry, and cache invalidation when the setting or canvas background changes. Preference projection remains in `tests/graph_track_b/qml_preference_bindings.py`; `tests/test_track_h_perf_harness.py` owns the benchmark parity fact.
- Keep retained-record-ID grip-state, property/Panel projection, generic freshness transport, and bounded-preview resolution in `tests/test_port_flow_state.py`, with one real-host green filled/hollow check in `tests/graph_surface/passive_host_interaction_suite.py`; expired runtime outputs must not appear current, empty/inactive outputs remain gray, and red means invalid type only. `tests/main_window_shell/bridge_qml_boundaries.py` proves the new freshness fact has no styling consumer.
- Keep flat-chrome coverage in the real-host graph-surface suites: action, passive, viewer, and collapsed hosts have no ordinary accent strip or header fill, while locked placeholders retain only their dashed diagnostic stripe plus hatch/ribbon/chip. Theme and persistence tests own removal of legacy header/category tokens and passive `visual_style` keys; QML state tests continue to prove body gradients and selected/execution borders and glows.
- Use graph-track tests for durable node link scene payload publication, shell bridge boundary tests for inspector link QML contracts, and graph-surface/rich-text suites when `GraphNodeLinkHoverLayer.qml` or `corex-link:` hover behavior changes.

## Focused Verification
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_surface_controls.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_node_toolbar_popover_host.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_canvas_surface_editor_overlays.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_edge_paint_policy.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_inline.py tests/test_passive_graph_surface_host.py tests/test_media_panel_qml_surface.py tests/test_passive_image_nodes.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_viewport_virtualization.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_split_bridges.py tests/test_graph_canvas_surface_snapshot.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_content_fullscreen_bridge_lifecycle.py --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/test_viewer_control_bridge.py tests/test_viewer_host_service.py tests/test_viewer_surface_host.py tests/test_viewer_surface_contract.py --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/qml_preference_bindings.py --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/test_plot_detached_window.py --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m pytest tests/test_data_tree_ui.py tests/test_default_port_values.py tests/test_graph_surface_input_controls.py tests/test_port_flow_state.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py tests/test_graph_surface_input_controls.py tests/graph_track_b/scene_model_graph_scene_suite.py -k "active_data_wire or display_mode or request_rewire_edges or ctrl_drag" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py tests/test_passive_graph_surface_host.py tests/test_shell_theme.py -k "ctrl_drag_reassigns_selected_or_sole_edge_endpoint_without_quick_insert or ports_use_projected_input_state_and_keep_edge_reason_out_of_port_text or family_accent_binding_updates_when_graph_theme_changes or graph_theme_bridge_resolves_family_tokens_to_the_active_data_role" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_planning_annotation_catalog.py tests/test_flowchart_surfaces.py tests/test_group_backdrop_contracts.py --ignore=venv -q -n 0
.\venv\Scripts\python.exe -m pytest tests/test_select_surface.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_trigger_surface.py tests/test_trigger_node.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_corex_node_controls_visual.py --ignore=venv -q
```

### Authoritative Qt Quick Test
```powershell
$runner = Join-Path $env:QT_ROOT "bin\qmltestrunner.exe"
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& $runner -input tests/qml_quick -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
```

Set `QT_ROOT` to a Qt SDK with the same major/minor version as the project's
PyQt Qt runtime; patch drift is accepted. Normal project-wide use is
`.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui`, which
discovers and validates the runner before executing this phase and Python GUI
pytest. A real `gui`/`full` run fails when the runner or compatible SDK is
missing; dry-run renders a placeholder and setup note. `fast` and `slow` never
require this SDK.

## Update Triggers
Update when QML surface test ownership, compact type projection/drag compatibility/rich-preview security coverage, declarative scalar/Interval 1D/searchable-enum/secret control coverage, viewport visibility/retention coverage,
durable node link hover/inline-link coverage, data-access/default/modifier/Principal/edge-enabled/display-mode presentation,
standard-node port hover/notch/shadow coverage, graph-track suites, passive host tests, viewer control/host/surface tests,
default-grip editors, bundle Ctrl-drag/copy, wire marquee/jump, flat node chrome, detached-window tests, or graph input gates change.
