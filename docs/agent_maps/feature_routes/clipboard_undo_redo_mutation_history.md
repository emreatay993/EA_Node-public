# Clipboard, Undo, Redo, And Mutation History

## Purpose
Use this for graph mutation history, undo/redo, clipboard fragments, runtime clipboard, and mutation replay routing.

## Start Here
- `ea_node_editor/ui_qml/graph_scene_mutation_history.py`
- `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
- `ea_node_editor/graph/fragment_payloads.py`
- `ea_node_editor/graph/transform_fragment_ops.py`
- `ea_node_editor/graph/record_mutation_ops.py`
- `ea_node_editor/graph/transforms.py`
- `ea_node_editor/ui/shell/runtime_clipboard.py`
- `ea_node_editor/ui/shell/clipboard_paste_nodes.py`
- `ea_node_editor/ui/shell/controllers/canvas_import_controller.py`
- `ea_node_editor/ui/shell/canvas_import_dialog.py`
- `ea_node_editor/ui/shell/canvas_drop_capture.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/node_creation_batch.py`
- `tests/test_canvas_import_runtime.py`
- `ea_node_editor/ui/shell/runtime_history.py`
- `ea_node_editor/ui/shell/controllers/workspace_edit_controller.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/selection_and_scope_ops.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_canvas_import_inputs.py tests/test_canvas_import_controller.py tests/test_canvas_import_preferences.py --ignore=venv -q -n 0
.\venv\Scripts\python.exe -m pytest tests/test_group_backdrop_clipboard.py tests/graph_track_b/scene_model_graph_scene_suite.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/edit_clipboard_history.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_workspace_edit_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_tree_ui.py tests/test_dataflow_graph_persistence.py --ignore=venv -q
```

## Mutation Routing Notes
- Fragment insertion is called directly through `ea_node_editor.graph.transform_fragment_ops.insert_graph_fragment`.
- `WorkspaceEditController.paste_nodes_from_clipboard()` owns graph-fragment MIME priority and validation; only external clipboard content delegates to the explicitly composed `CanvasImportController`.
- `clipboard_paste_nodes.py` captures owned MIME snapshots and classifies both clipboard and drop sources. It preserves every file/URL item, URL spelling, selected browser content and alternate formats. Automatic maps media to input-hidden Media Panel, local mail to Mail Panel, HTML/ordinary HTTP(S) to Web Viewer, folders/other files to Path Pointer, tables to Tabular Data Input, and plain/formatted text to Text Annotation.
- `CanvasImportController` owns Automatic/Ask selection, destination identity and scope revalidation, cascade/drop placement, unavailable-type errors, and project-staged byte recipes. `CanvasImportDialog` owns per-row and common bulk choices without remembering decisions. Text/Panel use literal values or exact managed refs for pathless media; cancellation stages nothing.
- `CanvasDropCapture` observes native Qt drops without consuming them; the canvas background retains insertion routing, while editors and explicit Path Pointer replacement keep priority. The controller consumes captured MIME before deferred import and expires unconsumed snapshots. Folder Explorer new-node releases use the same import route.
- `node_creation_batch.py` owns per-item creation results and one grouped history/invalidation boundary. A failed node removes only its owned creation/artifact work; successful items remain and failures are reported together.
- Imported artifacts include Path runtime descriptors. Execution admits registered canonical authored refs through `RuntimeArtifactService.materialize_authored_properties`, while Panel preserves the resulting carrier and Annotation remains passive/literal. Real process proof covers staged, reopened, and Save As inputs; untyped runtime/output refs remain rejected.
- Graph-fragment paste retargets fragment root nodes to `scope_parent_id(scene.active_scope_path)` before scene insertion, so copy/paste into and out of `core.subnode` scopes follows the visible canvas. Internal parent links inside the copied fragment stay unchanged.
- Fragment validation rejects internal self-parent and parent-cycle payloads. Direct fragment insertion still sanitizes remapped parent links before writing, dropping malformed parents to root while preserving valid internal and external parent links.
- Scene history uses focused validated and record mutation boundaries rather than the retired `WorkspaceMutationService`.
- Graph-scene grouped history uses opt-in `commit_if` gates for grouped operations that can prove they made no change after entering the history group. A false gate skips the expensive after-snapshot capture while preserving normal `RuntimeGraphHistory` snapshot equality for committed mutations.
- A settings-group toggle is one `toggle-settings-group` history entry containing declaration-ordered expansion state, exact custom-height correction, and any collision-avoidance neighbor moves. Toggling while the whole node is collapsed measures the hidden band with an isolated globally-expanded presentation probe so reopening preserves specialized body height.
- Dynamic group commands record `insert-dynamic-port`, `remove-dynamic-port`, or `rename-dynamic-port`. Each successful request is one history entry; invalid and no-op requests record none. Undo/redo restores the exact ordered keys, wires, labels, modifiers, and Principal state.
- Python Script Apply captures one `edit-node-property` history snapshot around `ValidatedGraphMutation.apply_python_script(...)`. The mutation validates the candidate source first; one successful entry reconciles source, resolved ports, ordinary settings, wires, sparse port state, and section expansion together.
- Python Script canvas handles use the same atomic mutation inside one `insert-dynamic-port` or `remove-dynamic-port` history entry. Undo/redo restores the exact source and topology together.
- `RuntimeGraphHistory.capture_workspace()` memoizes snapshots by exact `WorkspaceData.mutation_revision` and workspace object identity. Graph/view mutations and snapshot restore bump the runtime-only revision; undo/redo still replay full `WorkspaceSnapshot` entries.
- Undo/redo shell aftermath routes through `MutationUiEffects.after_history_replayed(...)`, which performs the full scene refresh, the registry-aware solution invalidation hook, and workspace-tab refresh. The classifier normalizes present active roots, removed executable IDs, and old/new edge targets; graph-scene code does not compute a downstream closure.

## Breadcrumbs
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)
- [Graph Scene Payload And Projection](graph_scene_payload_and_projection.md)

## Update Triggers
Update when shared import classification, MIME capture/lifecycle, chooser policy, import-mode routing, staged-reference handling, batch rollback/history, graph clipboard validation, or transform tests change.
