# Graph Actions And Context Menus

## Purpose
Use this for graph action IDs, layout menu actions, context menu entries, selected node/group run actions, selection-envelope action routing, selected-edge toolbar action routing, quick-add action chaining, and shell-side dispatch.

## Start Here
- `ea_node_editor/ui/shell/graph_action_contracts.py`
- `ea_node_editor/ui_qml/components/graph/GraphActionPresentation.js`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasActionRouter.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasOptionsMenu.qml`
- `ea_node_editor/ui_qml/components/GraphCanvas.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphSelectionEnvelopeOverlay.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphEdgeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeToolbarPopoverHost.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortContextMenu.qml`
- `ea_node_editor/ui_qml/graph_action_bridge.py`
- `ea_node_editor/ui/shell/controllers/graph_action_controller.py`
- `ea_node_editor/ui/shell/presenters/graph_canvas_host_presenter.py`
- `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
- `ea_node_editor/ui/shell/controllers/workspace_edit_controller.py`
- `ea_node_editor/ui/shell/controllers/run_controller.py`
- `ea_node_editor/ui/shell/inspector_projection.py`
- `ea_node_editor/ui/shell/quick_insert_projection.py`
- `ea_node_editor/ui/shell/controllers/workspace_drop_connect_controller.py`
- `ea_node_editor/ui/shell/window_actions.py`

## Related Help Reference
- `ea_node_editor/ui/dialogs/input_reference_dialog.py` documents user-facing graph action shortcuts and context-menu gestures. Update it when graph shortcuts, menu entries, visibility rules, or dispatch behavior change.

## Context Menu Positioning
- Pure QML presentation shaping for already-authoritative action DTOs lives in stateless `GraphActionPresentation.js`: descriptor lookup, edge path/display normalization and choices, checked/enabled/label/icon projection, node/edge toolbar models, menu/popover extraction, filtering, ordering, and grouping. `GraphCanvasActionRouter.qml` remains the sole QML dispatch owner; graph mutation, media/fullscreen/viewer/plot eligibility, lifecycle, native state, and context policy remain in their existing QML/Python owners.
- `GraphNodeToolbarPopoverHost.qml` directly owns the node-toolbar action-popover root, panel state/focus/position, nested action callbacks, and dirty-draft flush. `GraphNodeFloatingToolbar.qml` keeps primary buttons, run-menu dispatch, anchor/chrome/hover grace, live state aliases, and public open-method delegation; neither component becomes an action-policy or mutation owner.
- Standard data-port access/modifier/Principal/dynamic rows live in the feature-owned `GraphNodePortContextMenu.qml`. `GraphNodePortsLayer.qml` owns the selected port context, anchor and open call, and existing mutation/history methods; the shared styled popup renders its descriptors and the feature menu calls those methods explicitly and introduces no graph action ID, registry, callback bag, or replacement policy.
- Node, edge, selection, and empty-canvas right-click context menus store scene anchors in `GraphCanvasInteractionState.qml` and resolve screen position in `GraphCanvasContextMenus.qml` so open menus move with pan/zoom. The top-right gear uses the screen-anchored `_openCanvasOptions` path.
- Graph-owned node, edge, selection, and Settings right-click popups use 30 px rows with 4 px content padding; keep the pre-open height estimates in `GraphCanvasInteractionState.qml` aligned with that density.
- Edge context menus expose local `Path: Auto/Pipe/Bezier` rows that write `visual_style.path_mode` through the existing scene command bridge instead of registering global graph action IDs.
- Passive-object Lock/Unlock is likewise a QML-local node-toolbar action routed to `GraphSceneCommandBridge.set_node_locked(...)`, not a global graph action ID. The native Edit-menu `Interact with Locked Objects` toggle is session-only on Ctrl+L; Connect Selected moves to Ctrl+Shift+L.
- Editable-node context menus expose QML-local `Add Link` and `Add Comment` rows. Add Link selects its source node and opens the `GraphNodeLinkHoverLayer.qml` create popover through `GraphCanvas.requestAddNodeLinkForNode`; Add Comment keeps its existing editor path. Neither action registers a graph action ID or mutates records before Save/Post.
- Rename first uses the shared inline title editor. When a compact surface such as Trigger has no inline editor, `GraphCanvasActionRouter.qml` retries the same action without `inline_title_edit` so the existing native rename dialog handles it; context-menu and floating-toolbar paths share this fallback.
- Parameter/Response Setup and Pool nodes additionally expose exact QML-local semantic-link actions. They route through the existing scene command and mutation-history chain to persist or remove the typed Setup-to-Pool node link; they do not register global graph action IDs.
- Nodes with declared settings groups expose a QML-local Settings submenu with one checked row per group. Header and menu toggles route directly through `GraphSceneCommandBridge.set_node_settings_group_expanded(...)`; locked/read-only nodes cannot toggle, and the aggregate socket never enters port connection routing.
- `data.panel` adds QML-local Edit values and interpretation, Copy, and Copy as tree rows. The editor and both copy requests dispatch through the loaded `GraphPanelSurface.qml`; they do not register global graph action IDs. Copy and Copy as tree stay available in read-only graphs, while every formatting/editor mutation remains blocked. The editor replaces the retired numeric-parsing checkbox with explicit Text/Automatic/Number interpretation.

## Passive Style Context Menu
- Passive node and flow-edge style actions are declared as graph action contracts, surfaced from graph context menus/toolbars, routed by `GraphCanvasActionRouter.qml`, and dispatched through `GraphActionController` directly to `GraphCanvasHostPresenter`. That presenter owns dialog/preset/clipboard/label policy and calls the graph scene mutation owner; `ShellHostPresenter` and `ShellWindow` are not on this route.
- Bare Text annotations are excluded from the generic passive `visual_style` actions because their chrome-free surface owns whole-object typography and colors as node properties through `GraphRichTextBlock.qml` and its floating toolbar.
- `Propagate Style` flood-fills the right-clicked passive node's style through its wire-connected component in the scene mutation layer, changing only passive nodes; keep its context-menu, graph-action contract, shell dispatch, and undo/redo tests together.

## Selection Envelope Actions
- Multi-node selection actions are declared in `GraphCanvasActionRouter.selectionContextActionDescriptors`, rendered in `GraphCanvasContextMenus.qml` and `GraphSelectionEnvelopeOverlay.qml`, and dispatched through `handleSelectionContextAction`.
- Keep action eligibility visible but muted for disabled rows/buttons: align needs 2+ selected node-like items, distribute needs 3+, wrap needs 2+, and straighten needs an internal selected connection.
- `Set Same Width` and `Set Same Height` are right-click selection context menu actions only. They are enabled only for passive exact-`type_id` pairs; mixed selections ignore active and compile-only nodes, then resize non-primary passive nodes per bucket with one grouped resize history entry.

## Selected Run Actions
- `run_selected`, `preview_selected_run`, `confirm_selected_run_preview`, `clear_selected_run_preview`, and `open_selected_run_settings` are graph action contracts surfaced from node, selection context, selection-envelope, and preview-overlay routes. Run Upstream Chain and stale cache-reuse confirmation are removed.
- `run_selected` is the primary floating toolbar action for active selected nodes/groups; `GraphCanvasActionRouter.nodeDelegateActionDescriptors` routes its toolbar menu actions, and context menus expose preview and settings alternatives only for runnable nodes/groups.
- Dispatch flows through `GraphActionController` to `RunController`; payloads may carry one node ID, multiple selected node IDs, or fall back to current scene selection.
- Workspace actions dispatch through explicit typed calls to `WorkspaceEditController`; custom-workflow publication calls `WorkflowLibraryController` directly. `GraphActionController` has no string method table, `getattr` route, umbrella workspace controller, alternate delete owner, or publication fallback.
- `open_selected_run_settings` opens the shell-owned selected-run settings dialog instead of only logging the current preference.
- Public PyQt/QML shell graph-action request slots live in `window_state/workspace_graph_actions.py` on `ShellWindowWorkspaceGraphActionsMixin`; keep them there and do not add a dynamic facade binding map.

## Dataflow Authoring Actions
- Edge Enable is a QML-local checked action shared by the edge context menu, selected-edge floating toolbar, and Ctrl+E. It routes `toggle_edge_enabled` through the scene command bridge to graph mutation/history without registering a global `GraphActionId`.
- Port context actions are likewise QML-local: checked Graft, Flatten, Simplify, Reverse, Clean, and eligible Principal route to `set_port_modifiers` / `set_principal_input_port`.
- Metadata-driven dynamic-group Add from the node context menu and inline Insert/Remove/Rename from `GraphNodePortsLayer.qml` route through `GraphCanvasCommandBridge` and graph-scene mutation/history. They are not global `GraphActionId`s, never write backing properties directly, and apply to both Stream Gate and Python Script.

## Open / Open-With Path Actions
- `open_node_path` and `open_node_path_with` are node-delegate graph action contracts surfaced only on the Path Pointer (`io.path_pointer`) floating toolbar. `GraphCanvasActionRouter` routes the two sub-actions, `GraphActionController` resolves the node path and calls `platform_open.py`, and composition injects the direct graph-hint callback. "Open with..." is disabled for folders.
- The Folder Explorer row right-click menu (`GraphNativeExplorerSurface.qml`) adds the matching `folder_explorer_open_with` action (alongside the existing `folder_explorer_open`), both routing through the command bridge to the same `platform_open` helpers.
- All OS launch logic lives in `platform_open.py` (default handler vs app chooser) — do not inline `os.startfile`/`QDesktopServices`/`rundll32` at the call sites.

## Quick-Add Chaining
- Connection quick-add resolves compatible data inputs and creates a real data edge using the same normal-replacement or Shift-append contract as direct wiring.
- Ambiguous multi-port cases should stay on the normal connection-choice path rather than guessing.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_action_contracts.py tests/test_transform_layout_ops.py tests/main_window_shell/passive_style_context_menus.py tests/test_group_backdrop_membership.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_host_presenter.py tests/test_passive_style_presets.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py -k SelectionEnvelope --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py -k floating_toolbar_run_action_exposes_selected_run_menu --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/scene_model_graph_scene_suite.py -k propagate_passive_node_style --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_inspector_projection.py tests/test_quick_insert_projection.py tests/test_graph_canvas_split_bridges.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py -k "port_and_edge_authoring or dynamic_port" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py tests/test_graph_node_link_hover_layer.py -k "node_context_menu_routes_editors or link" --ignore=venv -q
```

## Breadcrumbs
- [UI Shell, Controllers, And Presenters](../subsystems/ui_shell.md)
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)

## Update Triggers
Update when action IDs, selected-run action routing, modifier/Principal/dynamic-port authoring, edge Enable/Ctrl+E, quick-add chaining, menu visibility, selection-envelope eligibility, selected-edge toolbar payloads, Add Link/Add Comment or optimization semantic-link routing, context payloads, controller dispatch, or user-facing shortcut/reference behavior changes.

## 2026-05-31 Mutation UI Effects Update

- Composition creates one `MutationUiEffects` and injects that same instance into `WorkspaceEditController` and `WorkspaceDropConnectController`. Use action-specific methods there for selected-node refreshes, tab refreshes, history replay scene refresh/invalidation, and layout overlap hints instead of adding repeated aftermath clusters.
