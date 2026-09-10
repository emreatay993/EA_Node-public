# Nested Node Categories, Subnodes, And Grouping

## Purpose
Use this for `category_path`, nested library categories, subnodes, group transforms, and grouping/ungrouping behavior. The shell `Group Selection` action runs the structural subnode transform with `Ctrl+Alt+G`.

## Start Here
- `ea_node_editor/nodes/builtins/subnode.py`
- `ea_node_editor/nodes/`
- `ea_node_editor/graph/subnode_contract.py`
- `ea_node_editor/graph/hierarchy.py`
- `ea_node_editor/graph/transform_fragment_ops.py`
- `ea_node_editor/graph/transform_grouping_ops.py`
- `ea_node_editor/ui/shell/controllers/workspace_edit_controller.py`
- `ea_node_editor/ui_qml/shell_library_bridge.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_library_projection.py tests/graph_track_b/scene_model_graph_scene_suite.py --ignore=venv -q
```

## Routing Notes
- Subnode membership is stored as `NodeInstance.parent_node_id`. Parent topology checks live in `graph/hierarchy.py` and are enforced by validated mutation, private record writers, workspace sanitization, and fragment insertion.
- Subnode pin `data_type` values preserve canonical CLR-style casing. Grouping copies the inner port's primary type plus ordered `accepted_data_types` into hidden pin properties; shell ports, nested pin ports, and custom-workflow snapshots must project that same union. Flow pins use the canonical generic graph type rather than a retired scalar alias.

## Breadcrumbs
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)

## Update Triggers
Update when category paths, subnode contracts, grouping transforms, or library category tests change.
