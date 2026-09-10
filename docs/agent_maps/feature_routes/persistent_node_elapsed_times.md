# Persistent Node Elapsed Times

## Purpose
Use this for elapsed execution-time persistence, runtime projection, node chrome display, and retained timing proof.

## Start Here
- `ea_node_editor/persistence/serializer.py`
- `ea_node_editor/execution/`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml`
- `ea_node_editor/ui_qml/graph_canvas_state/`

## Common Changes
- Runtime elapsed values stay in milliseconds; `GraphNodeHost.formatExecutionElapsed(...)` owns display conversion for seconds or milliseconds using the app-wide `graphics.canvas.node_elapsed_time_unit` preference. `graphics.canvas.node_elapsed_time_visibility` controls Off, During run, or Always display without changing stored timing values.
- Running-node elapsed text comes from `running_node_started_at_ms_lookup`; completed/warning elapsed text comes from `node_elapsed_ms_lookup`.
- Execution-affecting history clears elapsed entries only for `InvalidationResult.expired_node_ids` and `removed_node_ids`; the renamed solution-invalidation history hook owns this projection. Cosmetic/passive-only edits preserve timing.
- `GraphNodeHost` always suppresses elapsed footers for `data.number_slider` and `core.constant`; extend that local type list only when another primitive node should never show timing.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_process_client.py tests/test_serializer.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/qml_preference_bindings.py tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q
```

## Breadcrumbs
- [Node Execution Visualization](node_execution_visualization.md)
- [Serialization, Migration, And Legacy Rejection](serialization_migration_legacy_rejection.md)

## Update Triggers
Update when elapsed-time storage, runtime events, node display, or persistence tests change.
