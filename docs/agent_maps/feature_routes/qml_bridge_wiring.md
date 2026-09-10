# QML Bridge Wiring

## Purpose
Use this for Python/QML bridge ownership, context properties, invokable methods, and bridge boundary tests.
Graph canvas toolbar mutations that bypass modal graph actions, including flow-edge label/style updates, are exposed through `GraphCanvasCommandBridge` and should be covered here.
Text annotation style copy/paste is also exposed through `GraphCanvasCommandBridge` as an internal app/session clipboard, not the OS clipboard.
Durable node link actions are split by owner: inspector rows/actions route through `ShellInspectorBridge`, while graph-canvas hover/open/delete actions route through `GraphCanvasCommandBridge` and the graph scene command source.
Media Panel actions are bridge-routed but service-owned: inline QML calls `GraphCanvasCommandBridge` through its dedicated concrete `MediaPanelActionService` source, while fullscreen QML calls `ContentFullscreenBridge` through the same service's two direct trim callbacks.
`ContentFullscreenBridge` owns one active fullscreen lifecycle/payload and receives live providers and focused owner callbacks from `ui/shell/composition/runtime_services.py`. It has no `ShellWindow` reference, policy facade, dependency bag, compatibility alias, or separate QML API.
Dynamic-port authoring follows `GraphNodePortsLayer.qml` / `GraphCanvasContextMenus.qml` -> `graph_canvas_command.scene_mutation_ops` -> `GraphSceneCommandBridge` -> `graph_scene_mutation.selection_and_scope_ops` -> `ValidatedGraphMutation`; QML never writes the hidden backing properties.
Sensitive-property authoring follows graph/Inspector `SecretEditor.qml` -> dedicated `set/clear_*_secret` slots -> `GraphSceneMutationHistory` -> `selection_and_scope_ops`; generic property setters reject sensitive keys, so plaintext is DPAPI-protected before graph mutation or history capture.
Optimization Setup-to-Pool authoring follows `GraphCanvasContextMenus.qml` -> `graph_canvas_command.scene_mutation_ops` -> `GraphSceneMutationHistory` -> graph-owned node-link mutation, so semantic links persist and undo/redo without a QML-only store.

## Start Here
- `ea_node_editor/ui_qml/components/GraphCanvas.qml` — directly composes the focused state, command, and viewport owners; no aggregate facade or adapter.
- `ea_node_editor/ui_qml/graph_canvas_state/` — state bridge package. The composition root owns construction/source resolution only and receives session state/signal/size, app preferences, persisted graphics, execution/project, scene, and viewport separately. A new QML-visible canvas fact remains one `@pyqtProperty` in the matching projection mixin; QML metadata is snapshot-frozen.
- Solution-state notifications reuse `ShellWindow.node_execution_state_changed` -> `GraphCanvasStateBridge.node_execution_state_changed`/`port_flow_state_changed`. `ExecutionStateProps.node_solution_freshness_lookup` feeds `GraphCanvasExecutionFacts.nodeSolutionFreshnessLookup`; keep this generic fact off the canvas-root compatibility property list and out of styling until the deferred UI task.
- `ea_node_editor/ui_qml/graph_canvas_command/` — command bridge package. Its constructor receives run, scope/hint, Inspector, Library, T14 edit/drop, T15 media, graphics, host, scene, viewport, model/navigation, and folder owners separately; it has no `canvas_source`, shell-window fallback, or aggregate protocol. Slots remain in their existing mixins and meta-object bytes remain frozen.
- `ea_node_editor/ui_qml/viewport_bridge.py` — authoritative pan, zoom, viewport-size, centering, and visible-scene owner used by `GraphCanvas.qml` through `_canvasViewportBridge`.
- `ea_node_editor/ui_qml/graph_scene_bridge.py` — composition calls `bind_graphics_preferences_source(ShellWorkspacePresenter)`. The source can be replaced or cleared safely; the scene carries only `(show_port_labels, graph_label_pixel_size, node_title_icon_pixel_size, lightweight_canvas)` into payload rebuild decisions.
- `ea_node_editor/ui_qml/graph_scene/policy_bridge.py`
- `ea_node_editor/ui_qml/graph_scene_mutation_history.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/`
- `ea_node_editor/ui_qml/graph_scene_mutation/policy.py`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml`
- `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
- `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
- `ea_node_editor/ui/shell/composition/runtime_services.py`
- `tests/test_content_fullscreen_bridge.py`
- `tests/test_content_fullscreen_bridge_lifecycle.py`
- `ea_node_editor/ui_qml/shell_context_bootstrap.py`
- `ea_node_editor/ui/shell/context_bridges.py`
- `tests/test_data_type_ui_projection.py`

## Frozen QML-Visible Surface
- The QML-visible meta-object surface of the focused graph-canvas owner family (slots, properties, and signals on `GraphCanvasStateBridge`, `GraphCanvasCommandBridge`, `ViewportBridge`, the graph-scene read/command/policy bridges, `GraphSceneBridge`, and `ShellContextBundle`) is snapshot-frozen by `tests/test_graph_canvas_surface_snapshot.py` against `tests/fixtures/graph_canvas_surface_snapshot.json`. Additions are allowed (regenerate with `--write`); removals/renames fail.
- The snapshot includes `insert_dynamic_port`, `remove_dynamic_port`, and `rename_dynamic_port` on the graph command/scene chain.
- Dedicated `set_node_secret` and `clear_node_secret` slots are part of the graph-scene bridge chain; Inspector wrappers forward to the same owner.
- Drag compatibility follows `GraphSceneMutationPolicy.compatible_endpoint_snapshot(...)` -> `GraphScenePolicyBridge` -> `graph_canvas_state/scene_models_props.py` -> `GraphCanvasInteractionState.wireDragState`. The bridge publishes one fingerprinted endpoint identity snapshot per real gesture; it does not publish the catalog or compatibility graph.
- Bridge slots/properties/signals may live in plain-Python mixin modules composed with QObject; `tests/test_bridge_mixin_meta_registration.py` permanently pins the PyQt6 meta-object registration guarantees (including double-decorated overload slots and property/notify pairs) that the mixin packages rely on.
- Content fullscreen keeps the existing QML-visible slots, properties, signals, context name, and `ContentFullscreenOverlay.qml` contract unchanged. Python ownership is 42 direct methods plus two mounted methods; terminal/lazy-provider behavior is in the three direct lifecycle tests.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_split_bridges.py tests/main_window_shell/bridge_qml_boundaries.py tests/test_graph_scene_bridge_bind_regression.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_content_fullscreen_bridge_lifecycle.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_surface_snapshot.py tests/test_bridge_mixin_meta_registration.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py tests/test_graph_surface_input_controls.py -k "compatible_endpoint or ctrl_drag_reassigns" --ignore=venv -q
```

## Breadcrumbs
- [QML Shell And Bridge Layer](../subsystems/qml_shell_and_bridges.md)
- [Graph Scene Payload And Projection](graph_scene_payload_and_projection.md)
- [Durable Node Linking](durable_node_linking.md)
- [SSH/SFTP Nodes](ssh_sftp_nodes.md)

## Update Triggers
Update when bridge APIs, graphics/canvas source ownership, scene graphics binding/fingerprint, compatible-endpoint snapshot wiring, dynamic-port, sensitive-property, or optimization semantic-link command methods, durable node link bridge methods, fullscreen content bridge persistence or trim methods, context setup, QML bindings, or bridge tests change.

## 2026-05-31 Mutation UI Effects Update

- QML graph-scene mutation helpers still own payload rebuilds, node/edge delta publication, selection signals, and history replay deltas. Shell-only aftermath for graph edit actions now lives in `MutationUiEffects`; do not move QML scene publishers into the shell effect layer.

## 2026-07-11 Performance Ownership

- Stable bridge QObjects remain context-bound while their heavyweight internals allocate on first use. Fullscreen and Add-On Manager panes are retained URL-backed loaders; public context names, bridge types, focus, close, and object identity remain unchanged.
