# QML Shell And Bridge Layer

## Purpose
Use this for QML shell composition, Python-to-QML bridge wiring, shell bridge models, and QML host setup.

## Lookup Aliases
- `script editor panel width`
- `script editor panel state`

## Start Here
- `ea_node_editor/ui_qml/MainShell.qml`
- `ea_node_editor/ui_qml/components/shell/ShellRunToolbar.qml`
- `ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorPane.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorPropertyEditor.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorChoicePropertyEditor.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorTextareaPropertyEditor.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorPathPropertyEditor.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorChipsPropertyEditor.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorRowsModel.qml`
- `tests/qml_quick/tst_inspector_lifecycle.qml`
- `ea_node_editor/ui_qml/components/shell/NodeLibraryPane.qml`
- `ea_node_editor/ui_qml/components/shell/NodeBrowserOverlay.qml`
- `ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml`
- `ea_node_editor/ui_qml/components/shell/ShellLabeledTabStrip.qml`
- `ea_node_editor/ui_qml/components/shell/ShellContextMenu.qml`
- `ea_node_editor/ui_qml/components/shell/ShellContextPopup.qml`
- `tests/qml_quick/tst_shell_context_popup.qml`
- `ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml`
- `ea_node_editor/ui_qml/components/shell/ScriptCodeEditorPane.qml`
- `ea_node_editor/ui_qml/components/shell/PythonScriptGuidePane.qml`
- `ea_node_editor/ui_qml/components/common/DialogSurface.qml`, `DialogTextField.qml`, and `DialogButton.qml`
- `ea_node_editor/ui_qml/components/common/SecretEditor.qml`
- `ea_node_editor/ui_qml/ContentFullscreenOverlay.qml`
- `ea_node_editor/ui_qml/qml_host_factory.py`
- `ea_node_editor/ui_qml/shell_context_bootstrap.py`
- `ea_node_editor/ui_qml/shell_workspace_bridge.py`
- `ea_node_editor/ui_qml/console_model.py`
- `ea_node_editor/ui_qml/shell_library_bridge.py`
- `ea_node_editor/ui_qml/shell_inspector_bridge.py`
- `ea_node_editor/ui_qml/script_editor_model.py`
- `tests/test_script_editor_dock.py`
- `ea_node_editor/ui_qml/components/GraphCanvas.qml`
- `ea_node_editor/ui_qml/graph_canvas_state/`
- `ea_node_editor/ui_qml/graph_canvas_command/`
- `ea_node_editor/ui_qml/viewport_bridge.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/policy.py`
- `ea_node_editor/ui_qml/graph_scene/policy_bridge.py`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml`
- `ea_node_editor/ui_qml/bridge_runtime.py`
- `ea_node_editor/ui_qml/graph_scene_payload/` (payload construction package; see the payload feature route)
- `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
- `ea_node_editor/ui_qml/plot_host_service.py`
- `ea_node_editor/ui/shell/context_bridges.py`
- `ea_node_editor/ui/shell/library_projection.py`
- `ea_node_editor/ui/shell/inspector_projection.py`
- `ea_node_editor/ui/shell/quick_insert_projection.py`
- `tests/test_data_type_ui_projection.py`
- `tests/test_graph_surface_input_controls.py`
- `docs/qml_navigation_index.md` and `docs/qml_navigation_index.json` for generated QML component, filename alias, property, signal, function, and dynamic-loader lookup.

## Do Not Start Here
- `ea_node_editor/graph/` for bridge presentation-only changes.
- `ea_node_editor/ui/editor/` for QML script-editor panel state.
- Generated QML cache files.

## Common Changes
- Add Python bridge APIs and QML bindings together.
- `GraphCanvas.qml` composes `GraphCanvasStateBridge`, `GraphCanvasCommandBridge`, and `ViewportBridge` directly through `canvasStateBridgeRef`, `canvasCommandBridgeRef`, and `_canvasViewportBridge`; do not restore an aggregate graph-canvas bridge or private facade aliases.
- Production graph-canvas composition is per-domain: state uses session state/signal/size, app preferences, persisted graphics, execution/project, scene, and viewport; command uses run, scope/hint, Inspector, Library, edit/drop, media, graphics, host, scene, viewport, and navigation/model owners. `canvas_source` and shell-window fallback/accessors are absent while QML metadata stays frozen.
- Keep `ShellLibraryBridge` and `NodeLibraryPane.qml` aligned when node-library row models or passive display modes change.
- Keep `ShellLibraryBridge`, `NodeBrowserOverlay.qml`, `ConnectionQuickInsertOverlay.qml`, and `window_actions.py` aligned. The typed `node_browser_requested(str, float, float)` signal carries explicit detailed-browser requests into `MainShell.openNodeBrowser(...)`; Ctrl+B instead opens canvas-mode Quick Insert at the viewport center.
- Shared QML dialog chrome, fields, focus, and actions live in `components/common/DialogSurface.qml`, `DialogTextField.qml`, and `DialogButton.qml`. They are app-theme surfaces used by Node Browser, Number Slider settings, Timestamp, and Web Address only; do not route menus, command palettes, inline graph controls, panes, or fullscreen overlays through them.
- `ShellContextMenu.qml` owns context-menu rows, measured label/shortcut widths, accessibility, and keyboard selection using 30 px rows and 4 px padding. `ShellContextPopup.qml` hosts it for ports, Folder Explorer, workspace/view tabs, and library workflows; window-overlay parenting avoids graph scaling/clipping, and the popup owns bounded scrolling, dismissal, and focus restoration. Action descriptors and dispatch stay with each feature owner; scene-anchored graph menus retain their existing positioning.
- Authored passive-object locking projects through `GraphSceneReadBridge.interact_with_locked_objects` and `GraphSceneCommandBridge.set_node_locked(...)`. The interaction override is scene-session state, not an app preference or project field.
- `ConnectionQuickInsertOverlay.qml` owns both connection-origin and canvas-mode Quick Insert. `MainShell.qml` no longer mounts `CanvasInsertRadialMenu.qml`; keep the presenter state, shell bridge properties, and focus-loss close path aligned with the shared overlay.
- Python compatibility flows query the active scene registry catalog; do not add a parallel QML type table or equality rule. Real drag snapshots flow through `GraphSceneMutationPolicy.compatible_endpoint_snapshot(...)` -> `GraphScenePolicyBridge` -> `graph_canvas_state/scene_models_props.py` -> the existing `GraphCanvasInteractionState.wireDragState`, where one generation-checked result is reused for the gesture. Quick Insert continues to query Python catalog compatibility and the primary/accepted union directly.
- Fullscreen bridge methods that persist node surface state, including tabular selected columns, must stay aligned with their QML callers and focused bridge tests.
- `ContentFullscreenBridge` owns one active fullscreen lifecycle and receives live providers plus focused callbacks from shell composition. It has no `ShellWindow` lookup, policy facade, compatibility alias, or second QML API. `ViewerSessionBridge`, `ViewerControlBridge`, `ViewerHostService`, and `PlotHostService` likewise receive explicit live providers/direct collaborators from runtime composition and use their parent only for QObject lifetime. Exactly two bounded construction-cycle callbacks remain: session camera capture to the host and host bookmark cycling to viewer control. Terminal shutdown disconnects and does not persist after project close.
- `NativePresentationHandoff` is not a QML surface or QObject. Separate viewer/plot instances own only cached-preview render gating and queued completion; QML context names, meta-objects, viewer/plot public slots, native widget identity, and overlay geometry stay with the existing bridges/hosts.
- Keep shell context bootstrapping centralized.
- Keep Run, Run Selected, runtime-only Auto/Manual/Pause state, active scope breadcrumbs, and the compact project file label together in `ShellRunToolbar.qml`. `ShellWorkspaceBridge` projects the selected workspace's live solution mode; `RunController` initializes it from the app-wide default, evaluates Auto on open, and owns Trigger click/capture requests.
- Keep production view/workspace tab styling in `ShellLabeledTabStrip.qml`.
- View-tab canvas export actions route from `WorkspaceCenterPane.qml` through `ShellWorkspaceBridge.request_export_view(...)` / `request_export_all_views(...)` to the workspace and graph-canvas presenters.
- Keep `WorkspaceCenterPane.qml` bottom-console channel tabs, scroll views, and vertical resize handle aligned with `ShellWorkspaceBridge` console text/count properties and focused QML tests.
- `ShellStatusStrip.qml` telemetry HUD canvas paints are change-gated; FPS gauge repaint keys include rounded FPS, gauge colors, and canvas size.
- Keep outer shell pane collapse restore/write behavior aligned across `ShellCollapsibleSidePane.qml`, `WorkspaceCenterPane.qml`, and `ShellWorkspaceBridge.shell_panel_collapsed`.
- Keep `ScriptCodeEditorPane.qml` as the shared Python script editor body for `ScriptEditorOverlay.qml` and script-editor content fullscreen. The fullscreen-only Guide button opens the local theme-aware rich-HTML `PythonScriptGuidePane.qml`; it does not create a second editor or web/PDF host. `ScriptEditorModel` owns the side overlay's interactive width: drag frames stay local in QML, resize release calls `ScriptEditorModel.set_width(...)` once, and project document I/O only snapshots/restores `ScriptEditorSessionState.width` for save/open persistence.
- Explicit Run, confirmed Run Selected, and Trigger consume a valid selected dirty script draft before snapshot assembly; failed Apply aborts dispatch. The consumed Apply still invalidates execution state but suppresses only its duplicate Auto rerun. Auto itself never applies an unsaved draft. Keep dynamic-port topology editing on the graph command/scene bridges rather than `ScriptEditorModel`.
- Canvas dynamic-port edits consult `WorkspaceEditController` before changing source: a matching dirty draft blocks the click with an Apply/Revert hint. Successful edits refresh the matching clean script editor so later Apply cannot restore obsolete topology.
- History replay refreshes the editor's applied-source baseline while preserving a matching dirty draft; Revert then restores the graph's current source rather than an undone port declaration.
- Register QML image providers, including transient/in-memory providers, in `shell_context_bootstrap.py` and create them from shell composition.
- QML context property names stay centralized in `shell_context_bootstrap.py`; shell composition passes the binding set from `ShellServices.qml_context`.
- Keep QML shell commands bridge-first. Do not add QML callers to retired `ShellWindow` helper-facade names when a bridge already owns the command.
- `InspectorNodeLinksSection.qml` consumes selected-node link rows/actions and node/workspace picker options from `ShellInspectorBridge`; keep it bridge-first and avoid `mainWindowRef` helper calls for link commands.
- `InspectorNodeCommentsSection.qml` consumes selected-node comment rows/actions from `ShellInspectorBridge`; keep it bridge-first and synchronized with canvas comment popover mutations.
- `InspectorPropertyEditor.qml` shares declared property metadata with the graph surface: scalar and `interval_slider` editors consume authored/display facts, `PropertyConditionSpec` enablement, and `interval_direction`; `searchable=True` selects `InspectorEditableComboBox` while ordinary enums use `InspectorComboBox`. Inspector rendering must not mutate the authored property merely to show an upstream value.
- Inspector rows instantiate only their effective editor mode. Stateful choice, textarea, path, and chip bodies have focused owners; color/axis controls emit commit requests to the row's workspace/node/property guard. Chip values must be arrays so a scalar can never become a QML Repeater count.
- `InspectorRowsModel.qml` retains group/property delegate identities across value refreshes. Smart/Accordion groups create editors on first expansion and retain them while the same selection context lives, preserving explicit-Apply drafts. `InspectorPane.qml` owns demand-driven detail snapshots: collapsed Properties and the Help tab suspend projection; same-selection hiding retains editors, while selection replacement retires them. Its `set_content_active` bridge call also suspends presenter runtime-schema work. Reopening projects current metadata. The lifecycle QML tests and `tests/main_window_shell/passive_property_editors.py` own these boundaries.
- `SecretEditor.qml` is the shared masked Replace/Clear control used by graph inline properties and `InspectorPropertyEditor.qml`. It receives redacted state only; QML never receives ciphertext or existing plaintext, and both callers use the dedicated graph-scene secret command path.
- `MainShell.qml` owns node-link pick mode. `WorkspaceCenterPane.qml` intercepts workspace tabs while picking, and `GraphCanvas.qml` reports picked nodes back to the inspector without auto-saving.
- Regenerate `docs/qml_navigation_index.md` and `docs/qml_navigation_index.json` when QML files are added, renamed, or structurally changed so agents can route to QML owners by component name, filename alias, path, property, signal, function, or dynamic construct.
- Prefer focused bridge boundary tests for QML/Python contract changes.
- Content-fullscreen Python coverage is 42 direct methods plus two mounted wiring/QML methods in `tests/test_content_fullscreen_bridge.py`, with terminal/provider/laziness coverage in `tests/test_content_fullscreen_bridge_lifecycle.py`. Detailed viewer controls belong to viewer control/host/surface owner tests; shell lifecycle retains mount/visibility smoke only.
- `ShellAddOnManagerBridge` owns transient managed-install progress; worker signals queue the latest runtime output line to `AddOnManagerPane.qml`, and thread cleanup clears it.

- `GraphCanvasStateBridge` projects `node_solution_freshness_lookup` through `GraphCanvasExecutionFacts.nodeSolutionFreshnessLookup`; missing means never. This is transport-only—no badge, color, tooltip, animation, or action consumes it yet. The unchanged `freshRunNodeLookup` is derived from current solution facts for existing neutral chrome.

- `ConnectionQuickInsertOverlay.qml` renders Python-owned compatibility summaries and the exact blank/nonblank empty messages; it owns no type table or matching policy. Valid empty wire-release searches retain focus and remain searchable. `graph_scene_payload/builder.py` reuses Library-owned declared-type parsing for fallback previews, retaining the preview node while dropping malformed ports and preserving valid accepted types.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_script_editor_dock.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/bridge_qml_boundaries.py tests/main_window_shell/test_qml_shell_roots.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_content_fullscreen_bridge_lifecycle.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_split_bridges.py tests/test_graph_canvas_surface_snapshot.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/qml_preference_bindings.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py tests/test_graph_surface_input_controls.py -k "compatible_endpoint or ctrl_drag_reassigns" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py tests/main_window_shell/bridge_qml_boundaries.py -k "solution_mode or trigger or run_selected" --ignore=venv -q
$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_plot_detached_window.py --ignore=venv -q; $exitCode = $LASTEXITCODE; Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; exit $exitCode
```

## Breadcrumbs
- [QML Bridge Wiring](../feature_routes/qml_bridge_wiring.md)
- [Workspace Tabs And Library Context Menus](../feature_routes/workspace_tabs_library_context_menus.md)
- [Durable Node Linking](../feature_routes/durable_node_linking.md)
- [SSH/SFTP Nodes](../feature_routes/ssh_sftp_nodes.md)

## Update Triggers
Update when bridge properties, graphics/canvas source ownership, scene graphics binding/fingerprint, compatible-endpoint snapshot wiring, invokable methods, script-editor Apply/run synchronization, solution-mode/Trigger or run-control projection, Node Browser/canvas Quick Insert bindings, shared QML dialog styling, Inspector declarative property controls, inspector node link/comment bindings, fullscreen content bridge APIs, view/workspace tab rendering or tab actions, shell pane collapse persistence, bottom-console tab/scroll/resize behavior, QML image providers, QML context setup, QML shell roots, generated QML navigation coverage, graph-canvas preference projections, or plot host detached-window/preview-cache APIs change.

## 2026-05-31 Shell Services Bundle Update

- `ShellServices.qml_context` owns the context bundle, context-property bindings, and QML host image-provider bindings used during shell startup.
- The P02 service-bundle cleanup did not rename public QML context properties; update Python/QML callers directly if future packets intentionally change those names.

## 2026-05-31 Shell Facade Retirement Update

- QML context bootstrapping remains bridge-first after `window_state_helpers.py` removal. `ShellWindow` no longer assembles QML-visible host slots from dynamic facade binding maps; add new QML-facing behavior on the owning bridge or an explicit ShellWindow method only when the shell itself is the owner.

## 2026-07-11 Performance Ownership

- `MainShell.qml` retains first-created fullscreen and Add-On Manager objects through URL-backed `Loader`s. Stable bridge QObjects remain eager; heavyweight tabular/Jupyter/plot/viewer/folder internals allocate inside their owning services on first use.
