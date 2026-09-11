# Workspace Tabs And Library Context Menus

## Purpose
Use this for workspace tabs, view tabs, labeled tab strip visual states, library context menus, workspace bridge payloads, and library panes.

## Start Here
- `ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml`
- `ea_node_editor/ui_qml/components/shell/ShellLabeledTabStrip.qml`
- `ea_node_editor/ui_qml/components/shell/LibraryWorkflowContextPopup.qml`
- `ea_node_editor/ui_qml/components/shell/NodeLibraryPane.qml`
- `ea_node_editor/ui_qml/components/shell/NodeBrowserOverlay.qml`
- `ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml`
- `ea_node_editor/ui_qml/components/shell/LibraryNodeVisual.qml`
- `ea_node_editor/ui_qml/shell_workspace_bridge.py`
- `ea_node_editor/ui_qml/shell_library_bridge.py`
- `ea_node_editor/ui/shell/presenters/library_presenter.py`
- `ea_node_editor/ui/shell/library_projection.py`
- `ea_node_editor/ui/shell/quick_insert_projection.py`

## Design Reference
- `ShellLabeledTabStrip.qml` owns production view/workspace pill styling; production behavior stays in shell QML.
- Tab and library workflow menus use the shared `ShellContextPopup` with node-menu styling, window-relative placement, keyboard navigation, and focus restoration. Their existing owners retain the action lists and command dispatch.
- `NodeBrowserOverlay.qml` owns the explicit three-column browser opened through `ShellLibraryBridge.request_open_node_browser(...)`, including transient category/query/direction selection, category headers with two-column node rows in the middle pane, and optional scene-anchored insertion through the existing library and canvas-drop commands.
- `ConnectionQuickInsertOverlay.qml` owns the compact result list for both connection-origin and canvas-mode Quick Insert. Ctrl+B routes through `window_actions.py` to canvas mode at the viewport center; explicit Node Browser requests remain separate.
- Connection-origin Quick Insert compares the eventual output-to-input edge in both drag directions through graph-owned `source_port_compatibility(...)`, which retains the scalar catalog results for every inferred source member. Its shell-owned tiers are exact, assignable, convertible, flow, generic, and runtime-check; each node retains only equal-best ports in declaration order. Blank search hides generic/runtime tiers, explicit search reveals their labels, text rank precedes tier/count/name/type tie-breaks, and the cap is last. Cached Library port dictionaries are never annotated in place.
- `LibraryPresenter` refreshes connection context from the scene graph-contract revision before ranking or accepting. It preserves the highlighted item/port identity, drag anchor, and insertion coordinates; stale indices never select a reranked row. Model/workspace/scope replacement cancels the popup. Direct and explicitly forwarded source contracts share recommendation rows/order/labels; blank-search broad/runtime policy is unchanged. `tests/test_type_forwarding_ui.py` owns parity and live-popup regressions.
- `library_projection.py` is the sole node-library query/category owner. It derives filters, ancestor paths, category options/tree, grouped/display rows, and custom-workflow categories from the same cached combined projected items. `LibraryPresenter` builds one category tree per filtered cache request and keeps no separate registry-category cache; `NodeRegistry` exposes no Library filter/category API.
- `build_registry_library_items(...)` requires the active catalog and resolves default instance/dynamic ports before projection. Data-type options come from combined rows, not raw specs. Shared projected-port parsing returns no types for missing/blank/non-string primaries and preserves ordered unique alternatives; Library, Quick Insert, and QML fallback previews skip malformed ports.
- The overlay renders `compatible_port_summaries` and keeps valid empty connection searches open with the broader-search hint. Selection passes displayed keys into ordinary/workflow drop-connect; actual endpoints are resolved again and `GraphInvariantKernel` remains the final gate. Canvas-mode query behavior and passive flow orientation remain unchanged.
- `tests/qml_quick/tst_graph_node_host.qml` owns the pure-QML `LibraryNodeVisual` flowchart aspect-ratio fit check. `tests/test_flowchart_surfaces.py` retains geometry and Python-owned canvas drop-preview integration.

## Related Help Reference
- `ea_node_editor/ui/dialogs/input_reference_dialog.py` documents user-facing workspace tab, view tab, library row, library drag/drop, and custom workflow context-menu gestures. Update it when those interactions change.

## Focused Verification
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_node_host.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/shell_basics_and_search.py tests/test_library_projection.py tests/test_quick_insert_projection.py tests/test_shell_library_projection_cache.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_main_window_shell.py tests/test_workspace_navigation_controller.py --ignore=venv -q
```

## Breadcrumbs
- [Workspace, Projects, Session, And Library](../subsystems/workspace_projects_session_library.md)
- [Workflow Library And Drop Connect](workflow_library_drop_connect.md)

## Update Triggers
Update when workspace tabs, view tabs, labeled tab strip visual states, library menus or hidden internal descriptors, Node Browser or canvas Quick Insert behavior, shell bridge models, library tests, or Help reference tab/library coverage change.

## 2026-07-11 Performance Ownership

- Library rows and category paths cache until the registry/workflow revision changes; inspector pin/data-type projection follows the same owner revisions. Do not add a persistent or generic presenter cache.
