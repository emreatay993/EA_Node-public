# Workflow Library And Drop Connect

## Purpose
Use this for workflow library actions, drag/drop connect, workflow IO, and custom workflow library behavior.

## Start Here
- `ea_node_editor/ui/shell/controllers/workflow_library_controller.py`
- `ea_node_editor/ui/shell/controllers/workspace_drop_connect_controller.py`
- `ea_node_editor/ui/shell/controllers/workspace_package_io_controller.py`
- `ea_node_editor/ui/shell/controllers/workspace_selection_context.py`
- `ea_node_editor/custom_workflows/`
- `ea_node_editor/ui_qml/shell_library_bridge.py`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasDropPreview.qml`
- `tests/test_workspace_drop_connect_controller.py`
- `tests/test_workflow_library_controller.py`
- `tests/test_workspace_package_io_controller.py`

## Notes
- `.cxwf` is v2 and the global custom-workflow store is v2. Legacy workflows migrate with the same control-edge/node/pin removal and data-access defaults as project graphs; workflows left empty are removed and included in the one sorted migration report.
- Current workflow preview ports preserve canonical type-ID casing and ordered unique accepted alternatives excluding the primary. `codec.py` rejects malformed newly published data types; legacy normalization retains the workflow/fragment while omitting malformed previews, and the publication controller returns failure before storage or signals.
- Ordinary drop-connect remains graph-legal for assignable, convertible, and runtime-check relations. Quick Insert recommendations additionally gate broad/runtime matches behind explicit search. Both directions use the existing target input's primary/accepted union and graph-owned structured compatibility; flow remains structurally matched.
- `WorkspaceDropConnectController` accepts optional `compatible_port_keys`: `None` preserves unrestricted Library behavior, while any tuple, including empty, restricts auto-connect. Ordinary nodes filter actual effective keys; workflows filter public preview keys before mapping to actual node/port endpoints. Restricted choices reuse the chooser and revalidate through the final graph gate; stale workflow keys never fall back to shell ports, and failed auto-connect leaves the inserted node intact.
- Normal library/drop-connect validates first and atomically replaces every existing wire at the target data input. Holding Shift appends in persisted order, exact duplicates are no-ops, and preview/release must agree. Active data inputs use universal Shift fan-in; only passive `flow` ports retain capacity behavior from `allow_multiple_connections`.
- Standard/add-on library insertion paths record the chosen type id only after node creation succeeds. This single seam covers library rows, Node Browser insertion/drag, and radial learned shortcuts; paste, duplicate, automatic/file-drop, custom-workflow, and failed choices do not affect learned usage.
- Standard/add-on library insertion, including ordinary and property-seeded variants, preserves the current graph selection and leaves the new node unselected. Python Script uses this normal registry/validated-graph insertion path directly; there is no creation wizard or generated-plugin route. Paste, duplicate, and custom-workflow fragments keep their explicit selection behavior.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_output_mode_ui.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/drop_connect_and_workflow_io.py tests/test_library_projection.py tests/test_quick_insert_projection.py tests/test_workspace_drop_connect_controller.py tests/test_workflow_library_controller.py tests/test_workspace_package_io_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_dataflow_graph_persistence.py tests/main_window_shell/view_library_inspector.py -k "replaces_occupied_data_input or workflow" --ignore=venv -q
```

## Breadcrumbs
- [Workspace, Projects, Session, And Library](../subsystems/workspace_projects_session_library.md)
- [Workspace Tabs And Library Context Menus](workspace_tabs_library_context_menus.md)

## Update Triggers
Update when workflow/store versions, workflow migration, normal-replacement/Shift drop-connect behavior, successful-choice usage recording, custom workflows, or workflow IO tests change.

## 2026-07-14 Node Insertion Performance

- Standard library drop and quick insert share the targeted single-node scene publication path. Graph-only insertion no longer rebuilds workspace tabs after returning from the scene command.
- Custom workflow paste publishes inserted active-scope nodes and internal edges as one batch scene delta; nested records remain committed but render only when their scope is active.
- Single-node and workflow insertions publish their new rows before notifying selection listeners, so the canvas can reuse the inserted rows instead of querying the full visible scope again. Ordinary offscreen selection keeps the existing full-query fallback.
