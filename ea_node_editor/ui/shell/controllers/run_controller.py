# Purpose: Shell command controller for Manual/Selected/Trigger/Auto execution,
#          previews, dispatch policy, run control, and history invalidation.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_controller_unit.py
# Landmarks: RunController
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Literal, Protocol

from ea_node_editor.developer_mode import developer_mode_capability_enabled
from ea_node_editor.execution.backends import EXTERNAL_SUBPROCESS_BACKEND
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.prepared_execution import SolutionStateChangedEvent
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.execution.python_environment import (
    workflow_python_path_from_snapshot,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.hierarchy import root_node_ids_for_fragment, subtree_node_ids
from ea_node_editor.ui.shell.controllers.run_projection_controller import (
    RunProjectionController,
)
from ea_node_editor.ui.shell.runtime_history import (
    classify_history_execution_change,
)
from ea_node_editor.ui.shell.state import ShellRunState


class _WorkflowSettingsSourceProtocol(Protocol):
    def workflow_settings_payload(self) -> dict[str, Any]: ...


class _RunFailureFocusProtocol(Protocol):
    def focus_failed_node(self, workspace_id: str, node_id: str) -> None: ...


class _RunControllerHostProtocol(Protocol):
    run_state: ShellRunState
    project_path: str
    workspace_manager: Any
    serializer: Any
    model: Any
    registry: Any
    project_session_controller: _WorkflowSettingsSourceProtocol
    app_preferences_controller: Any
    console_panel: Any
    execution_client: Any
    script_editor: Any
    workspace_navigation_controller: _RunFailureFocusProtocol
    action_run: Any
    action_stop: Any
    action_pause: Any
    run_controls_changed: Any
    run_failure_changed: Any
    node_execution_state_changed: Any
    def update_notification_counters(
        self, warning_count: int, error_count: int
    ) -> None: ...

    def update_engine_status(self, state: str, details: str) -> None: ...

    def update_job_counters(
        self, running: int, queued: int, done: int, failed: int
    ) -> None: ...

    def show_selected_run_settings_dialog(self) -> None: ...


class RunController:
    def __init__(
        self,
        host: _RunControllerHostProtocol,
        *,
        projection_controller: RunProjectionController,
    ) -> None:
        self._host = host
        self._projection = projection_controller
        self._run_start_runtime_snapshots: dict[str, Any] = {}
        self._active_run_invalidated_node_ids: set[str] = set()
        self._solution_project_identity: int | None = None
        self._suppress_auto_run_for_script_apply = False

    @property
    def _state(self) -> ShellRunState:
        return self._host.run_state

    def _developer_mode_active(self) -> bool:
        return developer_mode_capability_enabled() and bool(
            self._state.developer_mode_active
        )

    def solution_mode(self, workspace_id: str = "") -> Literal["auto", "manual"]:
        normalized_workspace_id = str(
            workspace_id or self._host.workspace_manager.active_workspace_id()
        ).strip()
        if not normalized_workspace_id:
            return "manual"
        state = self._state
        mode = state.solution_mode_by_workspace_id.get(normalized_workspace_id)
        if mode is None:
            getter = getattr(
                self._host.app_preferences_controller, "solution_default_mode", None
            )
            mode = "auto" if callable(getter) and getter() == "auto" else "manual"
            state.solution_mode_by_workspace_id[normalized_workspace_id] = mode
        return mode

    def auto_run_enabled_for_workspace(self, workspace_id: str = "") -> bool:
        return self.solution_mode(workspace_id) == "auto"

    def set_auto_run_enabled(self, enabled: bool) -> None:
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        if not workspace_id:
            return
        mode: Literal["auto", "manual"] = "auto" if enabled else "manual"
        if self.solution_mode(workspace_id) == mode:
            return
        self._state.solution_mode_by_workspace_id[workspace_id] = mode
        if mode == "manual":
            self.clear_pending_auto_run()
        self._host.run_controls_changed.emit()

    def toggle_auto_run(self) -> None:
        if self.auto_run_enabled_for_workspace():
            self.set_auto_run_enabled(False)
            return
        self.set_auto_run_enabled(True)
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is not None:
            self._queue_auto_run(workspace_id, set(self._active_node_ids(workspace)))

    def clear_pending_auto_run(self) -> None:
        self._state.pending_auto_run_workspace_id = ""
        self._state.pending_auto_run_target_node_ids.clear()

    def reset_runtime_solution_state(self) -> None:
        state = self._state
        self.clear_pending_auto_run()
        state.solution_mode_by_workspace_id.clear()
        state.latest_trigger_inputs_by_workspace_id.clear()
        state.trigger_publications_by_workspace_id.clear()
        state.current_trigger_capture_node_ids_by_workspace_id.clear()
        self._projection.reset_runtime_projection()
        self.clear_active_run()
        self._run_start_runtime_snapshots.clear()
        self._solution_project_identity = id(self._host.model.project)

    def prune_runtime_solution_state(self) -> None:
        state = self._state
        workspaces = self._host.model.project.workspaces
        workspace_ids = set(workspaces)
        for mapping in (
            state.solution_mode_by_workspace_id,
            state.latest_trigger_inputs_by_workspace_id,
            state.trigger_publications_by_workspace_id,
            state.current_trigger_capture_node_ids_by_workspace_id,
        ):
            for workspace_id in tuple(mapping):
                if workspace_id not in workspace_ids:
                    mapping.pop(workspace_id, None)
        if state.pending_auto_run_workspace_id not in workspace_ids:
            self.clear_pending_auto_run()
        self._projection.prune_runtime_projection()
        for workspace_id, workspace in workspaces.items():
            trigger_ids = {
                node_id
                for node_id, node in workspace.nodes.items()
                if str(node.type_id) == "core.trigger"
            }
            for mapping in (
                state.latest_trigger_inputs_by_workspace_id,
                state.trigger_publications_by_workspace_id,
            ):
                workspace_mapping = mapping.get(workspace_id)
                if workspace_mapping is None:
                    continue
                for node_id in tuple(workspace_mapping):
                    if node_id not in trigger_ids:
                        workspace_mapping.pop(node_id, None)
                if not workspace_mapping:
                    mapping.pop(workspace_id, None)
            current_capture_ids = (
                state.current_trigger_capture_node_ids_by_workspace_id.get(workspace_id)
            )
            if current_capture_ids is not None:
                current_capture_ids.intersection_update(trigger_ids)
                if not current_capture_ids:
                    state.current_trigger_capture_node_ids_by_workspace_id.pop(
                        workspace_id, None
                    )

    def evaluate_workspace_on_open(self, workspace_id: str) -> None:
        if self._solution_project_identity != id(self._host.model.project):
            self.reset_runtime_solution_state()
        normalized_workspace_id = str(workspace_id or "").strip()
        if (
            self._state.pending_auto_run_workspace_id
            and self._state.pending_auto_run_workspace_id != normalized_workspace_id
        ):
            self.clear_pending_auto_run()
        workspace = self._host.model.project.workspaces.get(normalized_workspace_id)
        if workspace is None:
            return
        self.solution_mode(normalized_workspace_id)
        self._host.run_controls_changed.emit()
        if not self.auto_run_enabled_for_workspace(normalized_workspace_id):
            return
        target_node_ids = self._active_node_ids(workspace)
        if target_node_ids:
            self._queue_auto_run(normalized_workspace_id, set(target_node_ids))

    def run_workflow(self) -> None:
        if self._state.active_run_id:
            if self._state.engine_state_value == "paused":
                self.resume_workflow()
            else:
                self._host.console_panel.append_log(
                    "warning", "A workflow run is already active."
                )
                self._host.update_notification_counters(
                    self._host.console_panel.warning_count,
                    self._host.console_panel.error_count,
                )
            return

        if not self._apply_dirty_script_draft():
            return
        self._projection.clear_run_failure_focus()
        workspace_id = self._host.workspace_manager.active_workspace_id()
        self.prune_runtime_solution_state()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return
        runtime_snapshot = build_runtime_snapshot(
            self._host.model.project,
            workspace_id=workspace_id,
            registry=self._host.registry,
        )
        self._host.console_panel.clear_all()
        self.clear_selected_run_preview()
        run_id = self._prepare_and_dispatch(
            workspace_id=workspace_id,
            runtime_snapshot=runtime_snapshot,
            trigger_kind="manual",
            target_node_ids=self._active_node_ids(workspace),
        )
        if not run_id:
            self._host.console_panel.append_log(
                "error", "Failed to start workflow run."
            )
            self._host.update_notification_counters(
                self._host.console_panel.warning_count,
                self._host.console_panel.error_count,
            )
            self._projection.set_run_ui_state(
                "error",
                "Start Failed",
                0,
                0,
                0,
                1,
                clear_active_run=self.clear_active_run,
            )
            return
        self._projection.set_run_ui_state("running", "Starting", 1, 0, 0, 0)

    def run_selected_nodes(
        self,
        node_ids: Iterable[Any] | None = None,
        *,
        preview_only: bool = False,
        preview_confirmed: bool = False,
        trigger_kind: Literal["manual", "auto"] = "manual",
    ) -> None:
        normalized_trigger_kind = "auto" if trigger_kind == "auto" else "manual"
        if self._state.active_run_id:
            self._host.console_panel.append_log(
                "warning", "A workflow run is already active."
            )
            return
        workspace_id = self._host.workspace_manager.active_workspace_id()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            self._host.console_panel.append_log(
                "warning", "No active workspace is available."
            )
            return
        target_node_ids = (
            tuple(
                candidate
                for candidate in workspace.nodes
                if candidate
                in {str(node_id or "").strip() for node_id in (node_ids or ())}
                and self._node_is_active(workspace, candidate)
            )
            if normalized_trigger_kind == "auto"
            else self._selected_run_target_node_ids(workspace, node_ids)
        )
        if not target_node_ids:
            self._host.console_panel.append_log(
                "warning", "Select an executable node or group to run."
            )
            return

        preview_payload = self._selected_run_preview_payload(
            workspace=workspace,
            target_node_ids=target_node_ids,
        )
        preview_text = self._selected_run_preview_text(preview_payload)
        preview_enabled = (
            normalized_trigger_kind == "manual" and self._selected_run_preview_enabled()
        )
        if preview_only or (preview_enabled and not preview_confirmed):
            self._set_selected_run_preview(
                workspace_id=workspace_id,
                target_node_ids=target_node_ids,
                preview_payload=preview_payload,
            )
            self._host.console_panel.append_log("info", preview_text)
        if preview_only:
            return
        if preview_enabled and not preview_confirmed:
            return
        if normalized_trigger_kind == "manual" and not self._apply_dirty_script_draft():
            return
        self._projection.clear_run_failure_focus()
        self.prune_runtime_solution_state()
        runtime_snapshot = build_runtime_snapshot(
            self._host.model.project,
            workspace_id=workspace_id,
            registry=self._host.registry,
        )
        self._host.console_panel.clear_all()
        if preview_enabled:
            self._host.console_panel.append_log("info", preview_text)
        run_id = self._prepare_and_dispatch(
            workspace_id=workspace_id,
            runtime_snapshot=runtime_snapshot,
            trigger_kind=normalized_trigger_kind,
            target_node_ids=target_node_ids,
        )
        if not run_id:
            self._host.console_panel.append_log(
                "error", "Failed to start selected run."
            )
            self._projection.set_run_ui_state(
                "error",
                "Start Failed",
                0,
                0,
                0,
                1,
                clear_active_run=self.clear_active_run,
            )
            return
        self.clear_selected_run_preview()
        self._projection.set_run_ui_state("running", "Starting", 1, 0, 0, 0)

    def trigger_node(self, node_id: str) -> bool:
        if self._state.active_run_id:
            self._host.console_panel.append_log(
                "warning", "A workflow run is already active."
            )
            return False
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        normalized_node_id = str(node_id or "").strip()
        node = (
            workspace.nodes.get(normalized_node_id) if workspace is not None else None
        )
        if node is None or str(node.type_id) != "core.trigger":
            return False

        if not self._apply_dirty_script_draft():
            return False
        self._projection.clear_run_failure_focus()
        self.prune_runtime_solution_state()
        runtime_snapshot = build_runtime_snapshot(
            self._host.model.project,
            workspace_id=workspace_id,
            registry=self._host.registry,
        )
        latest_captures = self._state.latest_trigger_inputs_by_workspace_id.get(
            workspace_id, {}
        )
        current_capture_ids = (
            self._state.current_trigger_capture_node_ids_by_workspace_id.get(
                workspace_id, set()
            )
        )
        trigger_captures = (
            {normalized_node_id: latest_captures[normalized_node_id]}
            if normalized_node_id in current_capture_ids
            and normalized_node_id in latest_captures
            else {}
        )
        self._host.console_panel.clear_all()
        run_id = self._prepare_and_dispatch(
            workspace_id=workspace_id,
            runtime_snapshot=runtime_snapshot,
            trigger_kind="trigger",
            target_node_ids=(normalized_node_id,),
            trigger_captures=trigger_captures,
            clicked_trigger_node_id=normalized_node_id,
        )
        if not run_id:
            self._host.console_panel.append_log("error", "Failed to trigger node.")
            self._projection.set_run_ui_state(
                "error",
                "Start Failed",
                0,
                0,
                0,
                1,
                clear_active_run=self.clear_active_run,
            )
            return False
        self._projection.set_run_ui_state("running", "Starting", 1, 0, 0, 0)
        return True

    def _prepare_and_dispatch(
        self,
        *,
        workspace_id: str,
        runtime_snapshot: Any,
        trigger_kind: str,
        target_node_ids: tuple[str, ...],
        trigger_captures: Mapping[str, SettledPortResult] | None = None,
        clicked_trigger_node_id: str = "",
    ) -> str:
        client = self._host.execution_client
        request = ExecutionRequest(
            project_path=self._host.project_path,
            workspace_id=workspace_id,
            trigger={
                "kind": str(trigger_kind),
                "workflow_settings": self._host.project_session_controller.workflow_settings_payload(),
                "developer_mode": self._developer_mode_active(),
            },
            runtime_snapshot=runtime_snapshot,
            execution_backend=self._execution_backend_policy_for_runtime_snapshot(
                runtime_snapshot
            ),
            target_node_ids=tuple(target_node_ids),
            trigger_publications=dict(
                self._state.trigger_publications_by_workspace_id.get(workspace_id, {})
            ),
            trigger_captures=dict(trigger_captures or {}),
            clicked_trigger_node_id=clicked_trigger_node_id,
        )
        try:
            prepared = client.prepare_execution(request)
            self._projection.clear_port_availability_for_nodes(
                workspace_id,
                prepared.recompute_node_ids,
            )
            run_id = client.dispatch_prepared(prepared)
        except Exception as exc:  # noqa: BLE001
            self._host.console_panel.append_log("error", str(exc))
            run_id = ""
        self._projection.sync_solution_facts(workspace_id)
        if not run_id:
            return ""
        self._state.active_run_id = run_id
        self._state.active_run_workspace_id = workspace_id
        self._run_start_runtime_snapshots[run_id] = runtime_snapshot
        return run_id

    def _execution_backend_policy_for_runtime_snapshot(
        self,
        runtime_snapshot: Any,
    ) -> dict[str, Any] | None:
        if workflow_python_path_from_snapshot(runtime_snapshot):
            return None
        python_executable = (
            self._host.app_preferences_controller.default_python_executable()
        )
        if not python_executable:
            return None
        return {
            "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
            "allow_external_subprocess": True,
            "python_executable": python_executable,
            "reason": "application_default_python_executable",
        }

    def preview_selected_run(
        self,
        node_ids: Iterable[Any] | None = None,
    ) -> None:
        self.run_selected_nodes(node_ids, preview_only=True)

    def confirm_selected_run_preview(self) -> None:
        state = self._state
        target_node_ids = tuple(state.selected_run_preview_target_node_ids)
        if not state.selected_run_preview_workspace_id or not target_node_ids:
            self._host.console_panel.append_log(
                "warning", "No selected run preview is waiting."
            )
            return
        self.run_selected_nodes(
            target_node_ids,
            preview_confirmed=True,
        )

    def clear_selected_run_preview(self) -> None:
        self._clear_selected_run_preview()

    def _apply_dirty_script_draft(self) -> bool:
        editor = self._host.script_editor
        if not bool(editor.dirty):
            return True
        self._suppress_auto_run_for_script_apply = True
        try:
            applied = bool(editor.apply())
        finally:
            self._suppress_auto_run_for_script_apply = False
        if not applied:
            self._host.console_panel.append_log(
                "error",
                "Apply the Python script draft before running.",
            )
        return applied

    def open_selected_run_settings(self) -> None:
        opener = getattr(self._host, "show_selected_run_settings_dialog", None)
        if callable(opener):
            opener()
            return
        state = "on" if self._selected_run_preview_enabled() else "off"
        self._host.console_panel.append_log(
            "info",
            f"Selected run settings: preview before run is {state}.",
        )

    def _selected_run_preview_enabled(self) -> bool:
        controller = getattr(self._host, "app_preferences_controller", None)
        getter = getattr(controller, "selected_run_preview_before_run", None)
        if callable(getter):
            return bool(getter())
        return True

    def toggle_pause_resume(self) -> None:
        if not self._state.active_run_id:
            return
        if self._state.engine_state_value == "paused":
            self.resume_workflow()
        elif self._state.engine_state_value == "running":
            self.pause_workflow()

    def pause_workflow(self) -> None:
        if not self._state.active_run_id or self._state.engine_state_value != "running":
            return
        self._host.execution_client.pause_run(self._state.active_run_id)
        self._host.update_engine_status("running", "Pausing")

    def resume_workflow(self) -> None:
        if not self._state.active_run_id or self._state.engine_state_value != "paused":
            return
        self._host.execution_client.resume_run(self._state.active_run_id)
        self._host.update_engine_status("running", "Resuming")

    def stop_workflow(self) -> None:
        if not self._state.active_run_id:
            return
        self.clear_pending_auto_run()
        self._host.execution_client.stop_run(self._state.active_run_id)
        if self._state.engine_state_value == "paused":
            self._host.update_engine_status("paused", "Stopping")
        else:
            self._host.update_engine_status("running", "Stopping")
        self._projection.update_run_actions()

    def clear_active_run(self) -> None:
        self.consume_run_start_runtime_snapshot(self._state.active_run_id)
        self._state.active_run_id = ""
        self._state.active_run_workspace_id = ""
        self._active_run_invalidated_node_ids.clear()

    def _selected_node_ids_from_scene(self, workspace: Any) -> tuple[str, ...]:
        scope_selection = getattr(
            getattr(self._host, "scene", None), "_scope_selection", None
        )
        selected_in_workspace = getattr(
            scope_selection, "selected_node_ids_in_workspace", None
        )
        if callable(selected_in_workspace):
            return tuple(selected_in_workspace(workspace))
        selected_ids = getattr(scope_selection, "selected_node_ids", None)
        if selected_ids is None:
            selected_ids = getattr(
                getattr(self._host, "scene", None), "_selected_node_ids", ()
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_node_id in selected_ids or ():
            node_id = str(raw_node_id or "").strip()
            if node_id and node_id in workspace.nodes and node_id not in seen:
                seen.add(node_id)
                normalized.append(node_id)
        return tuple(normalized)

    def _selected_run_target_node_ids(
        self, workspace: Any, node_ids: Iterable[Any] | None
    ) -> tuple[str, ...]:
        raw_node_ids = (
            tuple(node_ids)
            if node_ids is not None
            else self._selected_node_ids_from_scene(workspace)
        )
        roots = root_node_ids_for_fragment(workspace, raw_node_ids)
        expanded = subtree_node_ids(workspace, roots or raw_node_ids)
        normalized: list[str] = []
        seen: set[str] = set()
        for node_id in expanded:
            node = workspace.nodes.get(node_id)
            if node is None or node_id in seen:
                continue
            try:
                spec = self._host.registry.get_spec(node.type_id)
            except Exception:  # noqa: BLE001
                continue
            runtime_behavior = (
                str(getattr(spec, "runtime_behavior", "") or "").strip().lower()
            )
            if runtime_behavior in {"passive", "compile_only"}:
                continue
            seen.add(node_id)
            normalized.append(node_id)
        return tuple(normalized)

    def _queue_auto_run(self, workspace_id: str, target_node_ids: set[str]) -> None:
        state = self._state
        normalized_workspace_id = str(workspace_id or "").strip()
        normalized_targets = {str(node_id or "").strip() for node_id in target_node_ids}
        normalized_targets.discard("")
        if (
            not self.auto_run_enabled_for_workspace(normalized_workspace_id)
            or not normalized_workspace_id
            or not normalized_targets
            or normalized_workspace_id
            != self._host.workspace_manager.active_workspace_id()
        ):
            return
        if state.pending_auto_run_workspace_id == normalized_workspace_id:
            state.pending_auto_run_target_node_ids.update(normalized_targets)
        else:
            state.pending_auto_run_workspace_id = normalized_workspace_id
            state.pending_auto_run_target_node_ids = normalized_targets
        if not state.active_run_id:
            self.drain_pending_auto_run()

    def drain_pending_auto_run(self) -> None:
        state = self._state
        workspace_id = state.pending_auto_run_workspace_id
        target_node_ids = set(state.pending_auto_run_target_node_ids)
        self.clear_pending_auto_run()
        if (
            not self.auto_run_enabled_for_workspace(workspace_id)
            or state.active_run_id
            or not workspace_id
            or workspace_id != self._host.workspace_manager.active_workspace_id()
        ):
            return
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            return
        ordered_target_node_ids = tuple(
            node_id
            for node_id in workspace.nodes
            if node_id in target_node_ids and self._node_is_active(workspace, node_id)
        )
        if not ordered_target_node_ids:
            return
        self.run_selected_nodes(
            ordered_target_node_ids,
            preview_confirmed=True,
            trigger_kind="auto",
        )

    def _active_node_ids(self, workspace: Any) -> tuple[str, ...]:
        return tuple(
            node_id
            for node_id in workspace.nodes
            if self._node_is_active(workspace, node_id)
        )

    def _node_is_active(self, workspace: Any, node_id: str) -> bool:
        node = workspace.nodes.get(str(node_id or "").strip())
        if node is None:
            return False
        try:
            spec = self._host.registry.get_spec(node.type_id)
        except Exception:  # noqa: BLE001
            return False
        runtime_behavior = (
            str(getattr(spec, "runtime_behavior", "") or "").strip().lower()
        )
        return runtime_behavior not in {"passive", "compile_only"}

    def _selected_run_preview_payload(
        self,
        *,
        workspace: Any,
        target_node_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        node_lookup: dict[str, str] = {}
        for node_id in target_node_ids:
            node = workspace.nodes.get(node_id)
            if node is None:
                continue
            title = str(getattr(node, "title", "") or node_id)
            rows.append(
                {
                    "section": "Will run",
                    "tone": "run",
                    "node_id": node_id,
                    "title": title,
                    "detail": "",
                }
            )
            node_lookup[node_id] = "run"
        return {
            "title": "Run Selected preview",
            "rows": rows,
            "node_lookup": node_lookup,
        }

    def _selected_run_preview_text(self, preview_payload: Mapping[str, Any]) -> str:
        lines = [f"{preview_payload.get('title', 'Selected run preview')}:"]
        current_section = ""
        rows = preview_payload.get("rows", ())
        if not isinstance(rows, (list, tuple)):
            return "\n".join(lines)
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            section = str(row.get("section", "") or "").strip()
            if section and section != current_section:
                lines.append(f"{section}:")
                current_section = section
            title = str(row.get("title", "") or row.get("node_id", "") or "").strip()
            detail = str(row.get("detail", "") or "").strip()
            lines.append(f"- {title}{f' ({detail})' if detail else ''}")
        return "\n".join(lines)

    def _set_selected_run_preview(
        self,
        *,
        workspace_id: str,
        target_node_ids: tuple[str, ...],
        preview_payload: Mapping[str, Any],
    ) -> None:
        state = self._state
        state.selected_run_preview_workspace_id = str(workspace_id or "").strip()
        state.selected_run_preview_target_node_ids = tuple(
            str(node_id) for node_id in target_node_ids
        )
        rows = preview_payload.get("rows", ())
        state.selected_run_preview_rows = (
            [dict(row) for row in rows if isinstance(row, Mapping)]
            if isinstance(rows, (list, tuple))
            else []
        )
        node_lookup = preview_payload.get("node_lookup", {})
        state.selected_run_preview_node_lookup = (
            {
                str(node_id): str(tone or "run")
                for node_id, tone in dict(node_lookup).items()
                if str(node_id).strip()
            }
            if isinstance(node_lookup, Mapping)
            else {}
        )
        state.selected_run_preview_revision += 1
        self._projection.commit_node_execution_state_change()

    def _clear_selected_run_preview(self) -> None:
        state = self._state
        if not (
            state.selected_run_preview_workspace_id
            or state.selected_run_preview_target_node_ids
            or state.selected_run_preview_rows
            or state.selected_run_preview_node_lookup
        ):
            return
        state.selected_run_preview_workspace_id = ""
        state.selected_run_preview_target_node_ids = ()
        state.selected_run_preview_rows.clear()
        state.selected_run_preview_node_lookup.clear()
        state.selected_run_preview_revision += 1
        self._projection.commit_node_execution_state_change()

    def invalidate_solution_for_history_action(
        self,
        workspace_id: str,
        action_type: str,
        *,
        before_snapshot: object | None = None,
        after_snapshot: object | None = None,
    ) -> bool:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return False
        change = classify_history_execution_change(
            action_type,
            registry=self._host.registry,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        if not change.affects_execution:
            return False
        workspace = self._host.model.project.workspaces.get(normalized_workspace_id)
        if workspace is None:
            return False
        changed_root_node_ids = change.changed_root_node_ids
        if not changed_root_node_ids and not change.removed_node_ids:
            changed_root_node_ids = self._active_node_ids(workspace)
        runtime_snapshot = build_runtime_snapshot(
            self._host.model.project,
            workspace_id=normalized_workspace_id,
            registry=self._host.registry,
        )
        result = self._host.execution_client.invalidate_solution(
            runtime_snapshot.project_id,
            normalized_workspace_id,
            runtime_snapshot,
            changed_root_node_ids,
            "graph_changed",
        )
        affected_node_ids = set(result.expired_node_ids)
        self._projection.handle_solution_state_changed(
            SolutionStateChangedEvent.from_invalidation(result).to_payload()
        )
        state = self._state
        current_capture_ids = (
            state.current_trigger_capture_node_ids_by_workspace_id.get(
                normalized_workspace_id
            )
        )
        if current_capture_ids is not None:
            stale_trigger_ids = {
                node_id
                for node_id in affected_node_ids
                if node_id in workspace.nodes
                and str(workspace.nodes[node_id].type_id) == "core.trigger"
            }
            if current_capture_ids.intersection(stale_trigger_ids):
                current_capture_ids.difference_update(stale_trigger_ids)
                if not current_capture_ids:
                    state.current_trigger_capture_node_ids_by_workspace_id.pop(
                        normalized_workspace_id, None
                    )
        if (
            state.active_run_id
            and state.active_run_workspace_id == normalized_workspace_id
        ):
            self._active_run_invalidated_node_ids.update(affected_node_ids)
        if not self._suppress_auto_run_for_script_apply and result.expired_node_ids:
            self._queue_auto_run(
                normalized_workspace_id,
                set(result.expired_node_ids),
            )
        return True

    def consume_run_start_runtime_snapshot(self, run_id: str) -> Any:
        normalized_run_id = str(run_id or self._state.active_run_id).strip()
        if not normalized_run_id:
            return None
        return self._run_start_runtime_snapshots.pop(normalized_run_id, None)

    def node_invalidated_during_active_run(
        self, workspace_id: str, node_id: str
    ) -> bool:
        return (
            str(workspace_id or "").strip() == self._state.active_run_workspace_id
            and str(node_id or "").strip() in self._active_run_invalidated_node_ids
        )
