# Run Controller And Selected Workspace State

## Purpose
Use this for Run, Run Selected, workspace solution mode, Auto evaluation, Trigger capture/publication, process output mode, active run scoping, and shell run presenter behavior.

## Start Here
- `ea_node_editor/ui/shell/controllers/run_controller.py`
- `ea_node_editor/ui/shell/controllers/run_event_controller.py`
- `ea_node_editor/ui/shell/controllers/run_projection_controller.py`
- `ea_node_editor/ui/shell/controllers/graph_action_controller.py`
- `ea_node_editor/ui/shell/graph_action_contracts.py`
- `ea_node_editor/ui/shell/run_flow.py`
- `ea_node_editor/ui/shell/state.py`
- `tests/test_run_projection_controller.py`
- `tests/test_run_event_controller.py`
- `ea_node_editor/ui/shell/presenters/workspace_presenter.py`
- `ea_node_editor/ui_qml/shell_workspace_bridge.py`
- `ea_node_editor/ui_qml/graph_scene/context.py`
- `ea_node_editor/ui/dialogs/selected_run_settings_dialog.py`
- `ea_node_editor/ui/shell/presenters/`
- `ea_node_editor/ui_qml/components/shell/ShellRunToolbar.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasActionRouter.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphSelectionEnvelopeOverlay.qml`
- `ea_node_editor/ui_qml/status_model.py`
- `ea_node_editor/execution/backend_client.py`
- `ea_node_editor/execution/runtime_requests.py`
- `ea_node_editor/execution/runtime.py`
- `ea_node_editor/execution/solution_store.py`
- `ea_node_editor/execution/run_messages.py`
- `ea_node_editor/execution/registry_agreement.py`
- `ea_node_editor/execution/protocol_codec.py`
- `ea_node_editor/execution/worker_runtime.py`

## Current Selected-Run Rules
- `Run` targets every active node, including ready isolated nodes and outputless sinks. Enabled data dependencies determine evaluation order; there is no control-edge queue or Start-node special case.
- `Run Selected` expands selected groups, sends the selected active node IDs as explicit targets, and lets the worker pull their enabled upstream dependencies. An explicitly selected isolated active node runs. Run Upstream Chain and selected-run cache seeding are removed.
- Before explicit Run or a confirmed manual Run Selected builds its snapshot, the controller applies a valid dirty selected Python Script draft. A failed Apply cancels dispatch and leaves the draft dirty; preview-only or unconfirmed Run Selected does not apply it.
- Manual, Run Selected, Auto, and Trigger build one `ExecutionRequest`, call `CorexRuntime.prepare_execution(...)`, and consume it once through `dispatch_prepared(...)`. Manual targets all active nodes, Selected uses explicit targets, Auto uses the exact invalidation result, and Trigger preserves clicked/capture fields. `CorexRuntime.start_run` and the legacy direct shell path are absent.
- Prepared dispatch reserves the execute-viewer subset of `PreparedExecution.recompute_node_ids` without visible mutation. `RunEventController` adopts partial-run state only from the ordered one-shot `viewer_invalidation_committed` event after worker preflight acceptance; worker-reset fallback calls the bridge's global `project_all_run_required(...)` path directly. Failed dispatch/preflight performs no viewer reset or invalidation. The shell has no live-viewer preflight/reset/rollback path.
- Every Run, Run Selected, Auto, and Trigger dispatch also calls `RunController._execution_backend_policy_for_runtime_snapshot(...)`. A non-empty project Workflow Override leaves selection to the execution client; otherwise a non-empty app default becomes the existing external policy. Blank app/project values keep built-in execution. The app path never enters the trigger or runtime snapshot.
- `RunEventController` is the sole shell runtime-event intake. It filters foreign and late run-scoped events before shell mutation, normalizes Trigger settlements with the active catalogue, routes logs/viewer/terminal transitions, and contains its own exceptions. After its run-state route completes, it calls `ViewerSessionBridge.handle_viewer_execution_event(...)` exactly once; viewer filtering stays in that bridge and viewer-delivery faults are logged without undoing run-state work. `ViewerSessionBridge` never subscribes to `ShellWindow.execution_event` itself. `RunProjectionController` alone owns node execution sets, timings, warnings, solution facts, port availability, failure focus, and run-control status. Shell output caching accepts only runtime-enriched settlements whose store acceptance result names the retained record ID/key/digest/disposition; rejected or late events cannot publish cache or availability state.
- Preview and settings actions route through graph actions; preview state is shell-owned and projects a compact QML list plus canvas node highlights with confirm and cancel actions. The `GraphCanvasRootLayers.qml` preview overlay sizes to measured row/header/action content, its `+N more` control expands the full row list inside a bounded scroll area, and wheel input over the overlay is consumed so preview scrolling does not also zoom the canvas.
- `Run Settings...` opens `SelectedRunSettingsDialog`, which edits the same `selected_run.preview_before_run` app preference exposed by the canvas options menu.
- `RunController` retains Manual/Selected/Trigger/Auto commands, preview, dirty-script Apply, backend/dispatch policy, pause/resume/stop, and history invalidation. Composition owns one queued connection from `ShellWindow.execution_event` directly to the retained `RunEventController`; the retired ShellWindow event, run-action, projection, status, cache, and failure forwarders must not return.

## Current Session Auto-Run Rules
- App preference `solution.default_mode` defaults to Auto. Each opened workspace copies that value into live runtime-only state; switching to Manual/Pause changes only that workspace and is not persisted.
- Auto evaluates all active nodes when a project opens or Manual transitions to Auto. After execution-affecting history, `CorexRuntime.invalidate_solution(...)` and the shared `ExecutionPlan.affected_downstream_closure(...)` return the exact Auto target set; the shell does not calculate another closure. Disabled edges and Trigger boundaries remain execution-plan rules.
- Apply consumed by explicit dispatch still invalidates runtime state but suppresses its duplicate Auto rerun. An Auto run never applies an unsaved script draft.
- An active run finishes against its captured snapshot. Concurrent invalidations union exact expired targets and successful `run_completed` drains one pending Auto run. Failed/stopped/cancelled/protocol/infrastructure outcomes, Manual/Pause, project replacement, or active-workspace mismatch clear the pending set without retry.
- The history classifier in `runtime_history.py` compares before/after snapshots with the registry: cosmetic/passive-only changes do nothing, present active roots invalidate, old/new edge targets are considered, and removed-only executable changes advance the solution revision with an empty root tuple.

## Trigger Rules
- `core.trigger` is a runtime-only sample-and-hold boundary. Upstream changes refresh `latest_input` without republishing downstream; before the first click its publication is EMPTY.
- A click first consumes a valid dirty selected Python Script draft, then publishes the newest settled value, EMPTY, or root failure and reruns downstream until the next Trigger boundary. Failed Apply aborts the click dispatch. An unconnected Trigger publishes `True`; a stale input refreshes upstream first.
- Stop or infrastructure failure cancels a pending capture while preserving the old publication. Reopen, duplicate, and delete reset publication state.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_shell_run_controller.py tests/main_window_shell/shell_runtime_contracts.py tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py tests/test_selected_run_settings_dialog.py tests/test_execution_worker.py tests/test_backend_client.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_event_controller.py tests/test_run_projection_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_projection_controller.py tests/test_port_availability.py tests/test_port_flow_state.py --ignore=venv -q
.\venv\Scripts\python.exe -m unittest tests.test_graph_canvas_viewport_virtualization.GraphCanvasViewportVirtualizationTests.test_selected_run_preview_overlay_shrinks_and_expands_overflow_rows -v
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py tests/test_dataflow_execution_runtime.py -k "run_selected or solution_mode or auto or trigger" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py -k "application_default_python" --ignore=venv -q
```

## Breadcrumbs
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)
- [Node Execution Visualization](node_execution_visualization.md)
- [QML Bridge Wiring](qml_bridge_wiring.md)
- [Clipboard, Undo/Redo, And Mutation History](clipboard_undo_redo_mutation_history.md)

## Update Triggers
Update when Run/Run Selected targeting, catalog-aware dispatch, app-default external-policy injection, script Apply synchronization, workspace solution mode, Auto-on-open/invalidation/coalescing, dynamic-port Auto invalidation, Trigger capture/publication, cached output freshness, active run scoping, graph-action run dispatch, or run-controller tests change.
