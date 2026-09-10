# Selected-Workspace Run Control States

## Summary
Make the top run controls selected-workspace aware under the current `main` shell architecture.

- `Run` is disabled only when the selected workspace owns the active run.
- `Pause` and `Stop` are enabled only when the selected workspace owns the active run.
- If workspace A is running and the user switches to workspace B, workspace B should show `Run` enabled and `Pause`/`Stop` disabled.
- The existing single-run warning stays in place if the user clicks `Run` while another workspace already owns the only active run.

## Main Architecture Mapping
On `main`, this work should target the current split ownership instead of the older direct-shell/QML path:

- Shared availability logic: `ea_node_editor/ui/shell/run_flow.py`
- QAction authority: `ea_node_editor/ui/shell/controllers/run_controller.py`
- Selected-workspace switch authority: `ea_node_editor/ui/shell/controllers/workspace_view_nav_ops.py`
- QML-facing workspace surface: `ea_node_editor/ui/shell/presenters/workspace_presenter.py`
- QML bridge: `ea_node_editor/ui_qml/shell_workspace_bridge.py`
- Toolbar consumer: `ea_node_editor/ui_qml/components/shell/ShellRunToolbar.qml`
- Composition wiring: `ea_node_editor/ui/shell/composition.py`

The plan should stay inside that flow rather than adding new direct QML dependencies on `ShellWindow`.

## Implementation Changes
- Extend `run_flow.py` from the current `run_action_state(...)` helper into a selected-workspace run-control projection that both Qt actions and QML can consume.
  - Compute `selected_workspace_owns_active_run = bool(active_run_id) and selected_workspace_id == active_run_workspace_id`.
  - Derive:
    - `can_run_active_workspace = not selected_workspace_owns_active_run`
    - `can_pause_active_workspace = selected_workspace_owns_active_run and engine_state in {"running", "paused"}`
    - `can_stop_active_workspace = selected_workspace_owns_active_run`
    - `pause_label = "Resume"` only when the selected workspace owns the active run and `engine_state == "paused"`, otherwise `"Pause"`
- Update `RunController.update_run_actions()` to use that shared projection for all three QAction surfaces.
  - Add `action_run` to `_RunControllerHostProtocol`.
  - Stop leaving `action_stop` always enabled.
  - Keep the existing pause/resume QAction label/icon behavior sourced from the shared projection.
  - Emit a new run-control notification after QAction state is recomputed so the presenter/bridge path stays in sync with menu and shortcut state.
- Refresh run controls when the selected workspace changes, not only when run events arrive.
  - Hook this into `WorkspaceViewNavOps.switch_workspace()` so changing workspace tabs immediately refreshes QAction state.
  - This same hook will also cover graph-search jumps and failure focus paths that switch workspaces through the shared workspace-navigation path.
- Add a dedicated run-control signal and read-only properties to the current presenter/bridge stack used by `main`.
  - Add `run_controls_changed` to `ShellWindow`, `_ShellWorkspacePresenterHostProtocol`, `ShellWorkspacePresenter`, `_ShellWorkspaceSource`, and `ShellWorkspaceBridge`.
  - Add `run_state` to `_ShellWorkspacePresenterHostProtocol` so `ShellWorkspacePresenter` can compute the selected-workspace projection without reaching into controller internals.
  - Expose new presenter/bridge properties:
    - `active_workspace_can_run`
    - `active_workspace_can_pause`
    - `active_workspace_can_stop`
  - Have `ShellWorkspaceBridge` re-emit `run_controls_changed` and expose those properties with `notify=run_controls_changed`.
- Bind the three buttons in `ShellRunToolbar.qml` to the new bridge properties via `enabled: ...`.
  - Keep the QML toolbar on `shellWorkspaceBridge`; do not reintroduce direct `mainWindowRef` run-control ownership.
- Update `ShellButton.qml` so disabled controls look disabled, not merely non-clickable.
  - Dim icon/text color while disabled.
  - Mute hover/pressed treatment while disabled.
- Add stable `objectName`s to the QML run buttons so runtime tests can assert enablement without depending on child order.
  - `shellRunToolbarRunButton`
  - `shellRunToolbarPauseButton`
  - `shellRunToolbarStopButton`

## Public Interface Additions
- `ShellWindow.run_controls_changed`
- `ShellWorkspacePresenter.run_controls_changed`
- `ShellWorkspacePresenter.active_workspace_can_run: bool`
- `ShellWorkspacePresenter.active_workspace_can_pause: bool`
- `ShellWorkspacePresenter.active_workspace_can_stop: bool`
- `ShellWorkspaceBridge.run_controls_changed`
- `ShellWorkspaceBridge.active_workspace_can_run: bool`
- `ShellWorkspaceBridge.active_workspace_can_pause: bool`
- `ShellWorkspaceBridge.active_workspace_can_stop: bool`

Internal protocol/test surfaces that must be updated with the same contract:

- `ea_node_editor/ui/shell/presenters/contracts.py`
- `ea_node_editor/ui_qml/shell_workspace_bridge.py` source protocol
- `tests/main_window_shell/bridge_support.py` workspace-source stubs

## Test Plan
Run with `venv/Scripts/python.exe`.

- `tests/test_run_controller_unit.py`
  - Idle state: `Run` enabled, `Pause` disabled, `Stop` disabled.
  - Active run on selected workspace: `Run` disabled, `Pause` enabled, `Stop` enabled.
  - Paused selected workspace: `Run` disabled, `Pause` enabled with `Resume` label, `Stop` enabled.
  - Active run on a different selected workspace: `Run` enabled, `Pause` disabled, `Stop` disabled.
  - Workspace-switch refresh updates QAction state immediately, without waiting for another execution event.
  - Completion/stop/failure returns controls to idle availability.
- `tests/main_window_shell/bridge_support.py`
  - The workspace bridge stub exposes the new signal/properties.
  - `ShellWorkspaceBridge` re-emits `run_controls_changed`.
- `tests/main_window_shell/bridge_contracts_workspace_and_console.py`
  - Contract coverage includes the new bridge signal/properties.
- `tests/main_window_shell/bridge_qml_boundaries.py`
  - `ShellRunToolbar.qml` references `shellWorkspaceBridge.active_workspace_can_run`.
  - `ShellRunToolbar.qml` references `shellWorkspaceBridge.active_workspace_can_pause`.
  - `ShellRunToolbar.qml` references `shellWorkspaceBridge.active_workspace_can_stop`.
  - The new run-button `objectName`s are present.
- `tests/test_shell_run_controller.py`
  - Start a run in workspace A, switch to workspace B, and assert the QML toolbar button `enabled` states flip immediately.
  - Switch back to workspace A and assert the running-workspace states restore immediately.
  - Verify the existing single-run warning still appears if `Run` is triggered from workspace B while workspace A owns the active run.
- `tests/main_window_shell/shell_basics_and_search.py`
  - Adjust any QAction shortcut smoke checks that assume `Stop` is always enabled.

## Assumptions
- No backend execution or protocol changes are required; this is a UI/control-state change.
- The app remains single-run globally.
- `Run` staying enabled on a non-owning selected workspace is intentional; the existing run-start guard still enforces the single-run rule.
- QML does not need a dedicated pause/resume label or icon property for this change; selected-workspace enablement and disabled styling are the required behavior changes.
