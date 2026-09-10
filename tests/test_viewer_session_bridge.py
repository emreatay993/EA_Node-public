from __future__ import annotations

import ast
import copy
import json
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QUrl, pyqtSignal

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.viewer_messages import (
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.execution.prepared_execution import InvalidationResult
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.common.scene_protocol import (
    ENGINEERING_VIEWER_BACKEND_ID,
    VIEWER_VIEW_OPTION_KEYS,
)
from ea_node_editor.nodes.builtins.engineering_viewer import ENGINEERING_VIEWER_NODE_TYPE_ID
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTree,
    RuntimeHandleRef,
)
from ea_node_editor.ui_qml import viewer_session_bridge as viewer_session_bridge_module
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.typed_handle_support import core_data_type_catalog

_SHOW_MESH_EDGES_PROPERTY = "show_mesh_edges"


class _ViewerExecutionClientStub:
    def __init__(self) -> None:
        self.next_run_id = "run_live"
        self.start_calls: list[dict[str, Any]] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.open_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.materialize_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.close_calls: list[dict[str, Any]] = []
        self.invalidate_viewer_calls: list[tuple[str, tuple[str, ...] | None]] = []
        self._solution_revisions: dict[str, int] = {}
        self._request_counter = 0

    def _next_request_id(self, prefix: str) -> str:
        self._request_counter += 1
        return f"{prefix}_{self._request_counter}"

    def start_run(
        self,
        project_path: str,
        workspace_id: str,
        trigger: dict[str, Any] | None = None,
        *,
        execution_backend: Any = None,
        target_node_ids: tuple[str, ...] | list[str] | None = None,
        trigger_publications: dict[str, Any] | None = None,
        trigger_captures: dict[str, Any] | None = None,
        clicked_trigger_node_id: str = "",
    ) -> str:
        self.start_calls.append(
            {
                "project_path": project_path,
                "workspace_id": workspace_id,
                "trigger": dict(trigger or {}),
                "execution_backend": execution_backend,
                "target_node_ids": tuple(target_node_ids or ()),
                "trigger_publications": dict(trigger_publications or {}),
                "trigger_captures": dict(trigger_captures or {}),
                "clicked_trigger_node_id": clicked_trigger_node_id,
            }
        )
        return self.next_run_id

    def pause_run(self, run_id: str) -> None:
        self.pause_calls.append(str(run_id))

    def resume_run(self, run_id: str) -> None:
        self.resume_calls.append(str(run_id))

    def stop_run(self, run_id: str) -> None:
        self.stop_calls.append(str(run_id))

    def open_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str = "",
        backend_id: str = "",
        data_refs: dict[str, Any] | None = None,
        transport: dict[str, Any] | None = None,
        transport_revision: int = 0,
        live_open_status: str = "",
        live_open_blocker: dict[str, Any] | None = None,
        camera_state: dict[str, Any] | None = None,
        playback_state: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        request_id = self._next_request_id("open")
        self.open_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "data_refs": dict(data_refs or {}),
                "transport": dict(transport or {}),
                "transport_revision": int(transport_revision),
                "live_open_status": str(live_open_status),
                "live_open_blocker": dict(live_open_blocker or {}),
                "camera_state": dict(camera_state or {}),
                "playback_state": dict(playback_state or {}),
                "summary": dict(summary or {}),
                "options": dict(options or {}),
            }
        )
        return request_id

    def update_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        backend_id: str = "",
        camera_state: dict[str, Any] | None = None,
        playback_state: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        request_id = self._next_request_id("update")
        self.update_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "camera_state": dict(camera_state or {}),
                "playback_state": dict(playback_state or {}),
                "summary": dict(summary or {}),
                "options": dict(options or {}),
            }
        )
        return request_id

    def close_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        request_id = self._next_request_id("close")
        self.close_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "options": dict(options or {}),
            }
        )
        return request_id

    def materialize_viewer_data(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        backend_id: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        request_id = self._next_request_id("materialize")
        self.materialize_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "options": dict(options or {}),
            }
        )
        return request_id

    def query_viewer_session(
        self,
        *,
        workspace_id: str,
        node_id: str,
        session_id: str,
        backend_id: str = "",
        query_type: str,
        payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        request_id = self._next_request_id("query")
        self.query_calls.append(
            {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "node_id": node_id,
                "session_id": session_id,
                "backend_id": backend_id,
                "query_type": query_type,
                "payload": dict(payload or {}),
                "options": dict(options or {}),
            }
        )
        return request_id

    def shutdown(self) -> None:
        return None

    def invalidate_viewer_requests(
        self,
        workspace_id: str,
        node_ids,
    ) -> int:
        normalized = None if node_ids is None else tuple(dict.fromkeys(node_ids))
        self.invalidate_viewer_calls.append((workspace_id, normalized))
        return 0

    def invalidate_solution(
        self,
        project_id: str,
        workspace_id: str,
        _runtime_snapshot,
        changed_root_node_ids,
        reason_code: str,
    ) -> InvalidationResult:
        self._solution_revisions[workspace_id] = (
            self._solution_revisions.get(workspace_id, 0) + 1
        )
        roots = tuple(changed_root_node_ids)
        return InvalidationResult(
            project_id=project_id,
            workspace_id=workspace_id,
            solution_revision=self._solution_revisions[workspace_id],
            changed_root_node_ids=roots,
            expired_node_ids=roots,
            removed_node_ids=(),
            reason_code=reason_code,
        )


class _SceneStub(QObject):
    workspace_changed = pyqtSignal(str)
    selection_changed = pyqtSignal()
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()

    def __init__(self, workspace_id: str = "ws_main") -> None:
        super().__init__()
        self.workspace_id = workspace_id
        self.selected_node_lookup: dict[str, bool] = {}

    def set_selected(self, *node_ids: str) -> None:
        self.selected_node_lookup = {
            str(node_id): True for node_id in node_ids if str(node_id).strip()
        }
        self.selection_changed.emit()


class _WorkspaceManagerStub:
    def __init__(self, scene: _SceneStub) -> None:
        self._scene = scene

    def active_workspace_id(self) -> str:
        return self._scene.workspace_id


@dataclass
class _WorkspaceState:
    nodes: dict[str, object]


@dataclass
class _ProjectState:
    workspaces: dict[str, _WorkspaceState]


@dataclass
class _ModelState:
    project: _ProjectState


class _HostStub(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.scene = _SceneStub()
        self.workspace_manager = _WorkspaceManagerStub(self.scene)
        self.execution_client = _ViewerExecutionClientStub()
        self.project_path = ""
        self.captured_camera_state: dict[str, Any] = {}
        self.capture_camera_calls: list[dict[str, str]] = []
        self.model = _ModelState(
            project=_ProjectState(
                workspaces={
                    "ws_main": _WorkspaceState(
                        nodes={
                            "node_viewer": object(),
                            "node_viewer_b": object(),
                            "node_viewer_restore": object(),
                            "node_viewer_other": object(),
                        }
                    )
                }
            )
        )
        self.model.project.metadata = {}

    def capture_overlay_camera_state(
        self, node_id: str, *, workspace_id: str = ""
    ) -> dict[str, Any]:
        self.capture_camera_calls.append(
            {
                "workspace_id": str(workspace_id),
                "node_id": str(node_id),
            }
        )
        return dict(self.captured_camera_state)

    @property
    def viewer_host_service(self):  # noqa: ANN201
        return self


def _viewer_opened_event(
    *,
    request_id: str,
    workspace_id: str,
    node_id: str,
    session_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    summary = {
        "cache_state": "proxy_ready",
        "result_name": "displacement",
    }
    summary.update(dict(overrides.pop("summary", {})))
    options = {
        "session_state": "open",
        "cache_state": summary["cache_state"],
        "playback_state": "paused",
        "live_mode": "proxy",
    }
    options.update(dict(overrides.pop("options", {})))
    payload = {
        "type": "viewer_session_opened",
        "request_id": request_id,
        "workspace_id": workspace_id,
        "node_id": node_id,
        "session_id": session_id,
        "data_refs": dict(overrides.pop("data_refs", {})),
        "live_open_status": "ready",
        "summary": summary,
        "options": options,
    }
    payload.update(overrides)
    return payload


def _viewer_session_handle(
    *,
    workspace_id: str = "ws_main",
    node_id: str = "node_viewer",
    session_id: str = "viewer_session_runtime_seeded",
    backend_id: str = ENGINEERING_VIEWER_BACKEND_ID,
) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
        schema_version=1,
        handle_id=f"handle:{session_id}",
        kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        owner_scope=f"cache:viewer_session:{workspace_id}:{session_id}",
        worker_generation=1,
        metadata={
            "workspace_id": workspace_id,
            "node_id": node_id,
            "session_id": session_id,
            "backend_id": backend_id,
        },
    )


class ViewerSessionBridgeUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.host = _HostStub()
        self.data_types = core_data_type_catalog()
        self.provider_calls = {"execution": 0, "active": 0, "workspace": 0}

        def execution_client_provider():  # noqa: ANN202
            self.provider_calls["execution"] += 1
            return self.host.execution_client

        def active_workspace_id_provider() -> str:
            self.provider_calls["active"] += 1
            return "ws_main"

        def workspace_provider(workspace_id: str):  # noqa: ANN202
            self.provider_calls["workspace"] += 1
            return self.host.model.project.workspaces.get(workspace_id)

        self.bridge = ViewerSessionBridge(
            self.host,
            execution_client_provider=execution_client_provider,
            active_workspace_id_provider=active_workspace_id_provider,
            workspace_provider=workspace_provider,
            scene_bridge=self.host.scene,
            data_types=self.data_types,
            capture_overlay_camera_state=self.host.capture_overlay_camera_state,
        )

    def test_viewer_session_bridge_facade_stays_within_packet_budget(self) -> None:
        ui_qml_dir = Path(__file__).resolve().parents[1] / "ea_node_editor" / "ui_qml"
        facade_path = ui_qml_dir / "viewer_session_bridge.py"
        support_path = ui_qml_dir / "viewer_session_bridge_support.py"
        facade_text = facade_path.read_text(encoding="utf-8")

        self.assertFalse(support_path.exists())
        self.assertNotIn("base64.b85decode", facade_text)
        self.assertNotIn("zlib.decompress", facade_text)
        self.assertIn("class ViewerSessionBridge", facade_text)

    def test_direct_providers_are_lazy_counted_and_follow_workspace_replacement(
        self,
    ) -> None:
        self.assertIs(self.bridge._execution_client(), self.host.execution_client)  # noqa: SLF001
        self.assertEqual(
            self.provider_calls, {"execution": 1, "active": 0, "workspace": 0}
        )

        self.host.scene.workspace_id = ""
        self.assertEqual(self.bridge.active_workspace_id, "ws_main")
        self.assertEqual(
            self.bridge._workspace_node_ids("ws_main"),  # noqa: SLF001
            {
                "node_viewer",
                "node_viewer_b",
                "node_viewer_restore",
                "node_viewer_other",
            },
        )
        self.assertEqual(
            self.provider_calls, {"execution": 1, "active": 1, "workspace": 1}
        )

        replacement_workspace = _WorkspaceState(nodes={"replacement": object()})
        self.host.model = _ModelState(
            project=_ProjectState(workspaces={"ws_main": replacement_workspace})
        )
        self.assertEqual(
            self.bridge._workspace_node_ids("ws_main"),  # noqa: SLF001
            {"replacement"},
        )
        self.assertEqual(
            self.provider_calls, {"execution": 1, "active": 1, "workspace": 2}
        )

    def test_pending_open_is_displayed_without_mutating_canonical_phase_or_playback(
        self,
    ) -> None:
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "playback_state": {"state": "playing", "step_index": 4},
            },
        )

        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")
        displayed = self.bridge.session_state("node_viewer")
        self.assertTrue(session_id)
        self.assertEqual(canonical.phase, "closed")
        self.assertEqual(canonical.playback_state, "paused")
        self.assertEqual(canonical.step_index, 0)
        self.assertEqual(canonical.options, {})
        self.assertEqual(displayed["phase"], "opening")
        self.assertEqual(displayed["playback_state"], "playing")
        self.assertEqual(displayed["step_index"], 4)

    def test_update_during_pending_open_preserves_opening_phase(self) -> None:
        self.assertTrue(
            self.bridge.open(
                "node_viewer",
                {"data_refs": {"fields": "fields_ref"}},
            )
        )

        self.assertTrue(
            self.bridge.sync_node_property_option(
                "node_viewer",
                _SHOW_MESH_EDGES_PROPERTY,
                True,
            )
        )

        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")
        self.assertEqual(canonical.phase, "closed")
        self.assertEqual(self.bridge.session_state("node_viewer")["phase"], "opening")

    def test_dispatch_failure_is_pending_error_without_overwriting_canonical_state(
        self,
    ) -> None:
        self._open_live_session()
        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")

        def fail_update(**_kwargs: Any) -> str:
            raise RuntimeError("viewer dispatch failed")

        self.host.execution_client.update_viewer_session = fail_update  # type: ignore[method-assign]
        self.assertFalse(self.bridge.play("node_viewer"))

        displayed = self.bridge.session_state("node_viewer")
        self.assertEqual(canonical.phase, "open")
        self.assertEqual(canonical.playback_state, "paused")
        self.assertEqual(displayed["phase"], "error")
        self.assertEqual(displayed["last_error"], "viewer dispatch failed")

    def test_worker_failure_preserves_canonical_state_and_discards_pending_update(
        self,
    ) -> None:
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "backend_id": "backend.rich",
            },
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                backend_id="backend.rich",
                data_refs={"dataset": {"kind": "mock_dataset", "id": "rich"}},
                transport={
                    "kind": "bundle",
                    "backend_id": "backend.rich",
                    "bundle_path": "C:/temp/rich_viewer_bundle",
                },
                transport_revision=7,
                live_open_status="ready",
                live_open_blocker={"code": "ready"},
                camera_state={"zoom": 1.75},
                playback_state={"state": "paused", "step_index": 2},
                summary={"cache_state": "live_ready", "source": "worker"},
                options={
                    "live_mode": "proxy",
                    "representation": "surface",
                    "playback_state": "paused",
                    "step_index": 2,
                },
            )
        )
        canonical_before = self.bridge.session_state("node_viewer")

        self.assertTrue(
            self.bridge.play(
                "node_viewer",
                {"options": {"representation": "wireframe"}},
            )
        )
        pending_state = self.bridge.session_state("node_viewer")
        self.assertEqual(pending_state["playback_state"], "playing")
        self.assertEqual(pending_state["options"]["representation"], "wireframe")
        update_call = self.host.execution_client.update_calls[-1]

        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_session_failed",
                "request_id": update_call["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "command": "update_viewer_session",
                "error": "backend rejected viewer update",
            }
        )

        failed_state = self.bridge.session_state("node_viewer")
        for field_name in (
            "workspace_id",
            "node_id",
            "session_id",
            "playback_state",
            "step_index",
            "playback",
            "cache_state",
            "invalidated_reason",
            "close_reason",
            "backend_id",
            "transport_revision",
            "live_mode",
            "live_open_status",
            "live_open_blocker",
            "data_refs",
            "transport",
            "camera_state",
            "summary",
            "options",
        ):
            self.assertEqual(failed_state[field_name], canonical_before[field_name])
        self.assertEqual(failed_state["phase"], "error")
        self.assertEqual(failed_state["request_id"], update_call["request_id"])
        self.assertEqual(failed_state["last_command"], "update_viewer_session")
        self.assertEqual(failed_state["last_error"], "backend rejected viewer update")
        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")
        self.assertIsNone(canonical.pending_display.phase)
        self.assertIsNone(canonical.pending_display.playback_state)
        self.assertEqual(canonical.pending_display.options, {})

    def test_authoritative_event_replaces_pending_display_and_normalizes_once(
        self,
    ) -> None:
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "playback_state": {"state": "playing", "step_index": 4},
            },
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.assertEqual(
            self.bridge.session_state("node_viewer")["playback_state"], "playing"
        )

        authoritative_event = _viewer_opened_event(
            request_id=open_call["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            options={
                "live_mode": "proxy",
                "playback_state": "paused",
                "step_index": 1,
            },
            summary={"cache_state": "proxy_ready", "source": "worker"},
        )
        with patch.object(
            viewer_session_bridge_module,
            "coerce_viewer_session_model",
            wraps=viewer_session_bridge_module.coerce_viewer_session_model,
        ) as normalize:
            self.bridge.handle_viewer_execution_event(authoritative_event)
            first_read = self.bridge.session_state("node_viewer")
            second_read = self.bridge.session_state("node_viewer")
            _ = self.bridge.sessions_model

        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")
        self.assertEqual(normalize.call_count, 1)
        self.assertEqual(canonical.phase, "open")
        self.assertEqual(canonical.playback_state, "paused")
        self.assertEqual(canonical.step_index, 1)
        self.assertIsNone(canonical.pending_display.phase)
        self.assertEqual(canonical.pending_display.options, {})
        self.assertEqual(first_read["playback_state"], "paused")
        self.assertEqual(first_read["step_index"], 1)
        self.assertEqual(first_read["summary"]["source"], "worker")
        self.assertEqual(second_read, first_read)

    def test_command_paths_do_not_write_canonical_viewer_state(self) -> None:
        source_path = Path(viewer_session_bridge_module.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        bridge_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ViewerSessionBridge"
        )
        command_methods = {
            "open",
            "close",
            "_update_session_command",
            "_send_materialize_command",
            "_apply_desired_live_mode",
        }
        forbidden_fields = {
            "phase",
            "options",
            "transport",
            "playback_state",
            "step_index",
        }
        offenders: list[str] = []
        normalization_owners: list[str] = []
        for method in bridge_class.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if method.name in command_methods:
                for node in ast.walk(method):
                    targets: list[ast.expr] = []
                    if isinstance(node, ast.Assign):
                        targets.extend(node.targets)
                    elif isinstance(node, ast.AnnAssign):
                        targets.append(node.target)
                    for target in targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "state"
                            and target.attr in forbidden_fields
                        ):
                            offenders.append(
                                f"{method.name}:{target.attr}:{node.lineno}"
                            )
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "coerce_viewer_session_model"
                for node in ast.walk(method)
            ):
                normalization_owners.append(method.name)

        self.assertEqual(offenders, [])
        self.assertEqual(normalization_owners, ["_apply_authoritative_projection"])

    def test_runtime_composition_injects_camera_capture_without_shell_lookup(
        self,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        runtime_source = (
            repo_root / "ea_node_editor/ui/shell/composition/runtime_services.py"
        ).read_text(encoding="utf-8")
        bridge_source = Path(viewer_session_bridge_module.__file__).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "capture_overlay_camera_state=capture_overlay_camera_state", runtime_source
        )
        self.assertIn(
            "viewer_host_service_ref[0] = viewer_host_service", runtime_source
        )
        self.assertNotIn('getattr(shell_window, "viewer_host_service"', bridge_source)

    def _open_live_session(self, node_id: str = "node_viewer") -> str:
        self.host.scene.set_selected(node_id)
        session_id = self.bridge.open(
            node_id, {"data_refs": {"fields": f"fields::{node_id}"}}
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id=node_id,
                session_id=session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": f"mock::{node_id}"}},
            )
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active(node_id, True)
        )
        return session_id

    def test_open_close_and_control_actions_route_through_execution_client_and_track_state(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "summary": {"result_name": "displacement"},
                "backend_id": "backend.custom",
                "camera_state": {"zoom": 1.2},
                "playback_state": {"state": "paused", "step_index": 3},
                "options": {"live_mode": "proxy"},
            },
        )

        self.assertTrue(session_id.startswith("viewer_session_"))
        self.assertEqual(len(self.host.execution_client.open_calls), 1)
        open_call = self.host.execution_client.open_calls[-1]
        self.assertEqual(open_call["workspace_id"], "ws_main")
        self.assertEqual(open_call["node_id"], "node_viewer")
        self.assertEqual(open_call["session_id"], session_id)
        self.assertEqual(open_call["backend_id"], "backend.custom")
        self.assertEqual(open_call["data_refs"], {"fields": "fields_ref"})
        self.assertEqual(open_call["camera_state"], {"zoom": 1.2})
        self.assertEqual(
            open_call["playback_state"], {"state": "paused", "step_index": 3}
        )
        self.assertEqual(open_call["options"]["live_mode"], "proxy")
        self.assertEqual(open_call["options"]["playback_state"], "paused")

        opening_state = self.bridge.session_state("node_viewer")
        self.assertEqual(opening_state["phase"], "opening")
        self.assertEqual(opening_state["playback_state"], "paused")

        self.assertEqual(opening_state["step_index"], 3)
        self.assertEqual(opening_state["backend_id"], "backend.custom")
        self.assertNotIn("session_model", opening_state)
        self.assertEqual(opening_state["live_mode"], "proxy")

        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                backend_id="backend.custom",
                camera_state={"zoom": 2.0},
                transport_revision=7,
                live_open_status="ready",
                transport={
                    "kind": "bundle",
                    "backend_id": "backend.custom",
                    "bundle_path": "C:/temp/viewer_bundle",
                },
            )
        )

        opened_state = self.bridge.session_state("node_viewer")
        self.assertEqual(opened_state["phase"], "open")
        self.assertEqual(opened_state["cache_state"], "live_ready")
        self.assertEqual(opened_state["summary"]["result_name"], "displacement")

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"],
            "full",
        )
        self.assertEqual(opened_state["backend_id"], "backend.custom")
        self.assertEqual(opened_state["transport_revision"], 7)
        self.assertEqual(opened_state["live_open_status"], "ready")
        self.assertEqual(
            opened_state["transport"]["bundle_path"], "C:/temp/viewer_bundle"
        )
        self.assertEqual(opened_state["camera_state"], {"zoom": 2.0})
        self.assertNotIn("session_model", opened_state)
        self.assertEqual(opened_state["transport_revision"], 7)
        self.assertEqual(opened_state["summary"]["result_name"], "displacement")

        self.assertTrue(self.bridge.play("node_viewer"))
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["playback_state"],
            "playing",
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["backend_id"], "backend.custom"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["camera_state"], {"zoom": 2.0}
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["playback_state"],
            {"state": "playing", "step_index": 3},
        )

        self.assertTrue(self.bridge.step("node_viewer"))
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["step_index"], 4
        )

        self.assertTrue(self.bridge.pause("node_viewer"))
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["playback_state"],
            "paused",
        )

        self.assertTrue(self.bridge.close("node_viewer"))
        close_call = self.host.execution_client.close_calls[-1]
        self.assertEqual(close_call["options"]["reason"], "user_close")

        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_session_closed",
                "request_id": close_call["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "summary": {"close_reason": "user_close", "cache_state": "proxy_ready"},
                "options": {
                    "session_state": "closed",
                    "cache_state": "proxy_ready",
                    "reason": "user_close",
                },
            }
        )

        closed_state = self.bridge.session_state("node_viewer")
        self.assertEqual(closed_state["phase"], "closed")
        self.assertEqual(closed_state["close_reason"], "user_close")
        self.assertNotIn("session_model", closed_state)
        self.assertEqual(closed_state["close_reason"], "user_close")

    def test_engineering_query_routes_asynchronously_and_emits_result(self) -> None:
        session_id = self._open_live_session()
        results: list[tuple[str, dict[str, Any]]] = []
        self.bridge.viewer_query_completed.connect(
            lambda node_id, result: results.append((str(node_id), dict(result)))
        )

        pending = self.bridge.query_session(
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            query_type="bounds",
            payload={"role": "primary"},
        )

        self.assertTrue(pending["pending"])
        query_call = self.host.execution_client.query_calls[-1]
        self.assertEqual(query_call["query_type"], "bounds")
        self.assertEqual(query_call["payload"], {"role": "primary"})
        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_query_result",
                "request_id": query_call["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "backend_id": query_call["backend_id"],
                "query_type": "bounds",
                "supported": True,
                "value": {"bounds": [0, 1, 0, 1, 0, 1]},
                "explanation": "",
            }
        )
        self.assertEqual(results[0][0], "node_viewer")
        self.assertTrue(results[0][1]["supported"])
        self.assertEqual(results[0][1]["value"]["bounds"], [0, 1, 0, 1, 0, 1])

    def test_node_property_option_sync_routes_mesh_edge_toggle_to_open_session(
        self,
    ) -> None:
        session_id = self._open_live_session()
        update_count = len(self.host.execution_client.update_calls)

        self.assertTrue(
            self.bridge.sync_node_property_option(
                "node_viewer",
                _SHOW_MESH_EDGES_PROPERTY,
                "true",
                {"workspace_id": "ws_main"},
            )
        )

        self.assertEqual(len(self.host.execution_client.update_calls), update_count + 1)
        update_call = self.host.execution_client.update_calls[-1]
        self.assertEqual(update_call["node_id"], "node_viewer")
        self.assertEqual(update_call["session_id"], session_id)
        self.assertTrue(update_call["options"][_SHOW_MESH_EDGES_PROPERTY])
        self.assertEqual(update_call["options"]["live_mode"], "full")

        projected_state = self.bridge.session_state("node_viewer")
        self.assertTrue(projected_state["options"][_SHOW_MESH_EDGES_PROPERTY])

        self.assertFalse(
            self.bridge.sync_node_property_option(
                "node_viewer",
                _SHOW_MESH_EDGES_PROPERTY,
                True,
                {"workspace_id": "ws_main"},
            )
        )
        self.assertEqual(len(self.host.execution_client.update_calls), update_count + 1)
        self.assertFalse(
            self.bridge.sync_node_property_option(
                "node_viewer",
                "unrelated_property",
                True,
                {"workspace_id": "ws_main"},
            )
        )

    def test_node_property_option_sync_routes_scalar_view_options(self) -> None:
        self._open_live_session()
        expected_updates = {
            "colormap": ("turbo", "turbo"),
            "result_component": ("Y", "y"),
            "scalar_range_mode": ("CUSTOM", "custom"),
            "scalar_range_min": (" 1.5 ", "1.5"),
            "scalar_range_max": ("nonsense", ""),
            "show_scalar_bar": ("false", False),
            "deform_scale": ("2.5", "2.5"),
            "hover_probe": ("true", True),
            "show_minmax_markers": (1, True),
            "viewer_background": ("WHITE", "white"),
        }
        self.assertEqual(
            set(expected_updates) | {_SHOW_MESH_EDGES_PROPERTY},
            set(VIEWER_VIEW_OPTION_KEYS),
        )
        for key, (raw_value, expected) in expected_updates.items():
            with self.subTest(key=key):
                self.assertTrue(
                    self.bridge.sync_node_property_option(
                        "node_viewer",
                        key,
                        raw_value,
                        {"workspace_id": "ws_main"},
                    )
                )
                self.assertEqual(
                    self.host.execution_client.update_calls[-1]["options"][key],
                    expected,
                )

    def test_engineering_viewer_options_sync_but_runtime_filter_does_not(self) -> None:
        self._open_live_session()
        expected_updates = {
            "representation": ("WIREFRAME_VISIBLE_EDGES", "wireframe_visible_edges"),
            "show_attribute_colors": ("true", True),
            "show_orientation_triad": ("false", False),
            "show_view_cube": ("false", False),
            "show_world_axes": ("true", True),
            "scene_styles": (
                {"scene_2": {"opacity": "0.3", "color": "#123456"}},
                {"scene_2": {"opacity": 0.3, "color": "#123456"}},
            ),
        }
        for key, (raw_value, expected) in expected_updates.items():
            with self.subTest(key=key):
                self.assertTrue(
                    self.bridge.sync_node_property_option(
                        "node_viewer",
                        key,
                        raw_value,
                        {"workspace_id": "ws_main"},
                    )
                )
                self.assertEqual(
                    self.host.execution_client.update_calls[-1]["options"][key],
                    expected,
                )
        update_count = len(self.host.execution_client.update_calls)
        for invalid in ({"scene_2": {"opacity": float("inf")}}, {"scene_2": {"color": "red"}}):
            self.assertFalse(self.bridge.sync_node_property_option(
                "node_viewer", "scene_styles", invalid, {"workspace_id": "ws_main"},
            ))
        self.assertFalse(
            self.bridge.sync_node_property_option(
                "node_viewer",
                "selection_filter",
                "cad_face",
                {"workspace_id": "ws_main"},
            )
        )
        self.assertEqual(len(self.host.execution_client.update_calls), update_count)

    def test_step_back_and_set_step_index_pause_and_clamp(self) -> None:
        self._open_live_session()

        self.assertTrue(self.bridge.step("node_viewer"))
        first_step = self.host.execution_client.update_calls[-1]["options"][
            "step_index"
        ]
        self.assertTrue(self.bridge.step("node_viewer"))
        second_step = self.host.execution_client.update_calls[-1]["options"][
            "step_index"
        ]
        self.assertEqual(second_step, first_step + 1)

        self.assertTrue(self.bridge.step_back("node_viewer"))
        update_call = self.host.execution_client.update_calls[-1]
        self.assertEqual(update_call["options"]["step_index"], second_step - 1)
        self.assertEqual(update_call["options"]["playback_state"], "paused")

        self.assertTrue(self.bridge.set_step_index("node_viewer", 7))
        update_call = self.host.execution_client.update_calls[-1]
        self.assertEqual(update_call["options"]["step_index"], 7)
        self.assertEqual(update_call["options"]["playback_state"], "paused")

        self.assertTrue(self.bridge.set_step_index("node_viewer", -4))
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["step_index"], 0
        )

        self.assertFalse(self.bridge.step_back("node_missing"))
        self.assertFalse(self.bridge.set_step_index("node_missing", 1))

    def test_update_during_pending_close_is_rejected_without_reopening_projection(
        self,
    ) -> None:
        self._open_live_session()
        self.assertTrue(self.bridge.close("node_viewer"))
        update_call_count = len(self.host.execution_client.update_calls)

        self.assertFalse(
            self.bridge.sync_node_property_option(
                "node_viewer",
                _SHOW_MESH_EDGES_PROPERTY,
                True,
            )
        )

        canonical = self.bridge._ensure_session_state("ws_main", "node_viewer")
        self.assertEqual(
            len(self.host.execution_client.update_calls), update_call_count
        )
        self.assertEqual(canonical.phase, "open")
        self.assertEqual(canonical.pending_display.phase, "closing")
        self.assertEqual(self.bridge.session_state("node_viewer")["phase"], "closing")

    def test_current_top_level_projection_is_authoritative_over_summary_options(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        session_id = self.bridge.open(
            "node_viewer", {"data_refs": {"fields": "fields_ref"}}
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )

        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_session_opened",
                "request_id": open_call["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "backend_id": "backend.authoritative",
                "transport_revision": 9,
                "live_open_status": "ready",
                "cache_state": "live_ready",
                "live_mode": "full",
                "data_refs": {"dataset": {"kind": "mock_dataset"}},
                "transport": {
                    "kind": "bundle",
                    "backend_id": "backend.authoritative",
                    "bundle_path": "C:/temp/viewer_bundle",
                },
                "camera_state": {"zoom": 1.4},
                "summary": {
                    "result_name": "displacement",
                    "backend_id": "backend.stale",
                    "transport_revision": 1,
                    "live_open_status": "blocked",
                },
                "options": {"live_mode": "proxy", "backend_id": "backend.stale"},
            }
        )

        opened_state = self.bridge.session_state("node_viewer")
        self.assertEqual(opened_state["backend_id"], "backend.authoritative")
        self.assertEqual(opened_state["transport_revision"], 9)
        self.assertEqual(opened_state["live_open_status"], "ready")
        self.assertEqual(opened_state["options"]["live_mode"], "full")
        self.assertEqual(
            opened_state["transport"]["backend_id"], "backend.authoritative"
        )
        self.assertNotIn("session_model", opened_state)

    def test_node_mutation_keeps_live_session_and_prunes_removed_node_projection(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        session_id = self.bridge.open(
            "node_viewer", {"data_refs": {"fields": "fields_ref"}}
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": "mock"}},
            )
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )

        self.host.scene.nodes_changed.emit()
        live_state = self.bridge.session_state("node_viewer")
        self.assertEqual(live_state["phase"], "open")
        self.assertEqual(live_state["options"]["live_mode"], "full")
        self.assertEqual(live_state["cache_state"], "live_ready")

        self.host.model.project.workspaces["ws_main"].nodes.pop("node_viewer")
        self.host.scene.nodes_changed.emit()
        self.assertEqual(self.bridge.session_state("node_viewer"), {})

    def test_explicit_inline_activation_is_exclusive_and_selection_does_not_activate(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        first_session_id = self.bridge.open(
            "node_viewer", {"data_refs": {"fields": "fields_a"}}
        )
        first_open = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=first_open["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=first_session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": "mock_a"}},
            )
        )

        second_session_id = self.bridge.open(
            "node_viewer_b", {"data_refs": {"fields": "fields_b"}}
        )
        second_open = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=second_open["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer_b",
                session_id=second_session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": "mock_b"}},
            )
        )

        self.assertEqual(
            self.bridge.session_state("node_viewer")["options"]["live_mode"], "proxy"
        )
        self.assertEqual(
            self.bridge.session_state("node_viewer_b")["options"]["live_mode"], "proxy"
        )

        update_count = len(self.host.execution_client.update_calls)
        self.host.scene.set_selected("node_viewer_b")
        self.assertEqual(len(self.host.execution_client.update_calls), update_count)
        self.assertEqual(
            self.bridge.session_state("node_viewer")["options"]["live_mode"], "proxy"
        )
        self.assertEqual(
            self.bridge.session_state("node_viewer_b")["options"]["live_mode"], "proxy"
        )

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["node_id"], "node_viewer"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"], "full"
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer_b", True)
        )
        self.assertEqual(
            [call["node_id"] for call in self.host.execution_client.update_calls[-2:]],
            ["node_viewer", "node_viewer_b"],
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-2]["options"]["live_mode"], "proxy"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"], "full"
        )
        self.assertEqual(self.host.execution_client.materialize_calls, [])
        self.assertEqual(
            self.bridge.session_state("node_viewer")["options"]["live_mode"], "proxy"
        )
        self.assertEqual(
            self.bridge.session_state("node_viewer_b")["options"]["live_mode"], "full"
        )
        self.assertEqual(
            self.bridge.session_state("node_viewer_b")["cache_state"], "live_ready"
        )

    def test_selection_loss_clears_explicit_activation_and_reselection_stays_proxy(
        self,
    ) -> None:
        session_id = self._open_live_session()
        update_count = len(self.host.execution_client.update_calls)
        self.host.capture_camera_calls.clear()

        self.host.scene.set_selected()
        deselected_state = self.bridge.session_state("node_viewer")
        self.assertEqual(len(self.host.execution_client.update_calls), update_count + 1)
        self.assertEqual(deselected_state["options"]["live_mode"], "proxy")
        self.assertEqual(
            self.host.capture_camera_calls[-1],
            {"workspace_id": "ws_main", "node_id": "node_viewer"},
        )
        self.host.scene.set_selected("node_viewer")
        reselected_state = self.bridge.session_state("node_viewer")
        self.assertEqual(len(self.host.execution_client.update_calls), update_count + 1)
        self.assertEqual(reselected_state["options"]["live_mode"], "proxy")
        self.assertEqual(reselected_state["session_id"], session_id)

    def test_presentation_hold_prevents_demotion_until_released(self) -> None:
        session_id = self._open_live_session()

        self.assertTrue(self.bridge.add_viewer_presentation_hold("node_viewer"))
        update_count = len(self.host.execution_client.update_calls)

        self.host.scene.set_selected()
        self.assertTrue(self.bridge.clear_viewer_focus())
        held_state = self.bridge.session_state("node_viewer")
        self.assertEqual(len(self.host.execution_client.update_calls), update_count)
        self.assertEqual(held_state["options"]["live_mode"], "full")
        self.assertEqual(held_state["session_id"], session_id)

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", False)
        )
        self.assertEqual(len(self.host.execution_client.update_calls), update_count)
        self.assertEqual(
            self.bridge.session_state("node_viewer")["options"]["live_mode"], "full"
        )

        self.assertTrue(self.bridge.remove_viewer_presentation_hold("node_viewer"))
        demote_call = self.host.execution_client.update_calls[-1]
        self.assertEqual(demote_call["node_id"], "node_viewer")
        self.assertEqual(demote_call["options"]["live_mode"], "proxy")
        self.assertEqual(
            self.bridge.session_state("node_viewer")["options"]["live_mode"], "proxy"
        )

    def test_superseded_proxy_response_cannot_override_newer_activation(self) -> None:
        session_id = self._open_live_session()
        initial_full_request = self.host.execution_client.update_calls[-1]
        initial_full_event = _viewer_opened_event(
            request_id=initial_full_request["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "full"},
            data_refs={"dataset": {"kind": "mock::node_viewer"}},
        )
        initial_full_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(initial_full_event)

        self.assertTrue(self.bridge.clear_viewer_focus())
        demotion_request = self.host.execution_client.update_calls[-1]
        self.assertEqual(demotion_request["options"]["live_mode"], "proxy")
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        promotion_request = self.host.execution_client.update_calls[-1]
        self.assertEqual(promotion_request["options"]["live_mode"], "full")

        projected_modes: list[str] = []
        self.bridge.sessions_changed.connect(
            lambda: projected_modes.append(
                self.bridge.session_state("node_viewer")["options"]["live_mode"]
            )
        )
        stale_proxy_event = _viewer_opened_event(
            request_id=demotion_request["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "proxy"},
            data_refs={"dataset": {"kind": "mock::node_viewer"}},
        )
        stale_proxy_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(stale_proxy_event)

        state_after_stale = self.bridge.session_state("node_viewer")
        self.assertEqual(projected_modes, [])
        self.assertEqual(state_after_stale["request_id"], promotion_request["request_id"])
        self.assertEqual(state_after_stale["options"]["live_mode"], "full")

        current_full_event = _viewer_opened_event(
            request_id=promotion_request["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "full"},
            data_refs={"dataset": {"kind": "mock::node_viewer"}},
        )
        current_full_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(current_full_event)

        self.assertTrue(projected_modes)
        self.assertEqual(set(projected_modes), {"full"})
        final_state = self.bridge.session_state("node_viewer")
        self.assertEqual(final_state["request_id"], promotion_request["request_id"])
        self.assertEqual(final_state["options"]["live_mode"], "full")

    def test_superseded_demotion_failure_cannot_override_newer_activation(
        self,
    ) -> None:
        session_id = self._open_live_session()
        initial_full_request = self.host.execution_client.update_calls[-1]
        initial_full_event = _viewer_opened_event(
            request_id=initial_full_request["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "full"},
            data_refs={"dataset": {"kind": "mock::node_viewer"}},
        )
        initial_full_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(initial_full_event)

        self.assertTrue(self.bridge.clear_viewer_focus())
        demotion_request = self.host.execution_client.update_calls[-1]
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        promotion_request = self.host.execution_client.update_calls[-1]

        projected_states: list[tuple[str, str]] = []
        self.bridge.sessions_changed.connect(
            lambda: projected_states.append(
                (
                    self.bridge.session_state("node_viewer")["phase"],
                    self.bridge.session_state("node_viewer")["options"]["live_mode"],
                )
            )
        )
        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_session_failed",
                "request_id": demotion_request["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "command": "update_viewer_session",
                "error": "superseded demotion failed",
            }
        )

        state_after_stale = self.bridge.session_state("node_viewer")
        self.assertEqual(projected_states, [])
        self.assertEqual(state_after_stale["phase"], "open")
        self.assertEqual(state_after_stale["request_id"], promotion_request["request_id"])
        self.assertEqual(state_after_stale["options"]["live_mode"], "full")

        current_full_event = _viewer_opened_event(
            request_id=promotion_request["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "full"},
            data_refs={"dataset": {"kind": "mock::node_viewer"}},
        )
        current_full_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(current_full_event)

        self.assertTrue(projected_states)
        self.assertEqual(set(projected_states), {("open", "full")})
        final_state = self.bridge.session_state("node_viewer")
        self.assertEqual(final_state["request_id"], promotion_request["request_id"])
        self.assertEqual(final_state["options"]["live_mode"], "full")

    def test_empty_request_failure_still_applies_to_current_session(self) -> None:
        session_id = self._open_live_session()

        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_session_failed",
                "request_id": "",
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "command": "update_viewer_session",
                "error": "uncorrelated worker failure",
            }
        )

        failed_state = self.bridge.session_state("node_viewer")
        self.assertEqual(failed_state["phase"], "error")
        self.assertEqual(failed_state["last_error"], "uncorrelated worker failure")

    def test_proxy_demotion_preserves_summary_until_explicit_reactivation(self) -> None:
        self.host.scene.set_selected("node_viewer_restore")
        restore_session_id = self.bridge.open(
            "node_viewer_restore",
            {
                "data_refs": {"fields": "restore_fields"},
                "summary": {"camera": {"zoom": 1.2}, "result_name": "displacement"},
            },
        )
        restore_open = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=restore_open["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer_restore",
                session_id=restore_session_id,
                summary={"cache_state": "live_ready", "camera": {"zoom": 1.2}},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": "restore_dataset"}},
            )
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active(
                "node_viewer_restore", True
            )
        )

        other_session_id = self.bridge.open(
            "node_viewer_other", {"data_refs": {"fields": "other_fields"}}
        )
        other_open = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=other_open["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer_other",
                session_id=other_session_id,
                summary={"cache_state": "live_ready"},
                options={"live_mode": "proxy"},
                data_refs={"dataset": {"kind": "other_dataset"}},
            )
        )

        self.host.scene.set_selected("node_viewer_other")
        demoted_state = self.bridge.session_state("node_viewer_restore")
        self.assertEqual(demoted_state["options"]["live_mode"], "proxy")
        self.assertEqual(demoted_state["summary"]["camera"], {"zoom": 1.2})
        self.assertNotIn("demoted_reason", demoted_state["summary"])

        self.host.scene.set_selected("node_viewer_restore")
        restored_state = self.bridge.session_state("node_viewer_restore")
        update_count = len(self.host.execution_client.update_calls)
        self.assertEqual(restored_state["options"]["live_mode"], "proxy")
        self.assertTrue(
            self.bridge.set_embedded_interaction_active(
                "node_viewer_restore", True
            )
        )
        restored_state = self.bridge.session_state("node_viewer_restore")
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["node_id"],
            "node_viewer_restore",
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"], "full"
        )
        self.assertEqual(restored_state["options"]["live_mode"], "full")
        self.assertEqual(restored_state["cache_state"], "live_ready")
        self.assertEqual(restored_state["summary"]["camera"], {"zoom": 1.2})
        self.assertNotIn("demoted_reason", restored_state["summary"])
        self.assertEqual(len(self.host.execution_client.update_calls), update_count + 1)

    def test_explicit_viewer_blur_demotes_to_proxy_without_png_snapshot_materialization(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        self.host.captured_camera_state = {
            "position": [9.0, 8.0, 7.0],
            "focal_point": [1.0, 2.0, 3.0],
            "viewup": [0.0, 1.0, 0.0],
            "view_angle": 24.0,
        }
        session_id = self.bridge.open(
            "node_viewer", {"data_refs": {"fields": "fields_ref"}}
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready", "camera": {"zoom": 1.1}},
                options={"live_mode": "full"},
                data_refs={"dataset": {"kind": "mock_dataset"}},
            )
        )

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertTrue(self.bridge.clear_viewer_focus())
        self.assertEqual(
            self.host.capture_camera_calls[-1],
            {"workspace_id": "ws_main", "node_id": "node_viewer"},
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["node_id"], "node_viewer"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"], "proxy"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["camera_state"],
            self.host.captured_camera_state,
        )
        preview_state = self.bridge.session_state("node_viewer")
        self.assertEqual(preview_state["camera_state"], self.host.captured_camera_state)
        self.assertEqual(preview_state["options"]["live_mode"], "proxy")
        self.assertNotIn("preview", preview_state["data_refs"])
        self.assertNotIn("png", preview_state["data_refs"])
        self.assertEqual(len(self.host.execution_client.materialize_calls), 0)

        demoted_event = _viewer_opened_event(
            request_id=self.host.execution_client.update_calls[-1]["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={
                "cache_state": "live_ready",
                "camera": dict(self.host.captured_camera_state),
            },
            options={"live_mode": "proxy"},
            data_refs={"dataset": {"kind": "mock_dataset"}},
            camera_state=dict(self.host.captured_camera_state),
        )
        demoted_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(demoted_event)

        proxy_state = self.bridge.session_state("node_viewer")
        self.assertEqual(proxy_state["options"]["live_mode"], "proxy")
        self.assertNotIn("png", proxy_state["data_refs"])
        self.assertEqual(proxy_state["camera_state"], self.host.captured_camera_state)
        self.assertEqual(self.host.execution_client.materialize_calls, [])

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["node_id"], "node_viewer"
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["options"]["live_mode"], "full"
        )

    def test_proxy_demotion_does_not_project_transient_preview_or_request_stored_png(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        self.host.captured_camera_state = {
            "position": [9.0, 8.0, 7.0],
            "focal_point": [1.0, 2.0, 3.0],
            "viewup": [0.0, 1.0, 0.0],
            "view_angle": 24.0,
        }
        session_id = self.bridge.open(
            "node_viewer", {"data_refs": {"fields": "fields_ref"}}
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready", "camera": {"zoom": 1.1}},
                options={"live_mode": "full"},
                data_refs={"dataset": {"kind": "mock_dataset"}},
            )
        )

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertTrue(self.bridge.clear_viewer_focus())

        proxy_state = self.bridge.session_state("node_viewer")
        self.assertEqual(proxy_state["options"]["live_mode"], "proxy")
        self.assertEqual(proxy_state["camera_state"], self.host.captured_camera_state)
        self.assertNotIn("preview", proxy_state["data_refs"])
        self.assertNotIn("png", proxy_state["data_refs"])
        self.assertEqual(self.host.execution_client.materialize_calls, [])

    def test_first_blur_refocus_preserves_camera_state_even_when_backend_returns_different_camera(
        self,
    ) -> None:
        captured = {
            "position": [5.0, 6.0, 7.0],
            "focal_point": [0.0, 0.0, 0.0],
            "viewup": [0.0, 1.0, 0.0],
            "view_angle": 30.0,
        }
        self.host.captured_camera_state = dict(captured)
        session_id = self._open_live_session()

        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertTrue(self.bridge.clear_viewer_focus())
        state_after_blur = self.bridge.session_state("node_viewer")
        self.assertEqual(state_after_blur["camera_state"], captured)

        # Backend responds with a DIFFERENT camera state (e.g. default)
        demoted_event = _viewer_opened_event(
            request_id=self.host.execution_client.update_calls[-1]["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready", "camera": {"zoom": 1.0}},
            options={"live_mode": "proxy"},
            camera_state={"zoom": 1.0},  # different from captured!
        )
        demoted_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(demoted_event)

        # Camera state must still be the locally captured one
        state_after_event = self.bridge.session_state("node_viewer")
        self.assertEqual(state_after_event["camera_state"], captured)

        self.assertEqual(self.host.execution_client.materialize_calls, [])

        # Re-focus must send the captured camera state to the backend
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        refocus_update = self.host.execution_client.update_calls[-1]
        self.assertEqual(refocus_update["options"]["live_mode"], "full")
        self.assertEqual(refocus_update["camera_state"], captured)
        internal_state = self.bridge._ensure_session_state("ws_main", "node_viewer")
        self.assertTrue(internal_state.camera_state_locally_captured)

        full_restore_event = _viewer_opened_event(
            request_id=refocus_update["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready", "camera": {"zoom": 1.0}},
            options={"live_mode": "full"},
            camera_state={"zoom": 1.0},
        )
        full_restore_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(full_restore_event)

        restored_state = self.bridge.session_state("node_viewer")
        self.assertEqual(restored_state["camera_state"], captured)
        self.assertFalse(
            self.bridge._ensure_session_state(
                "ws_main", "node_viewer"
            ).camera_state_locally_captured
        )

    def test_second_blur_refocus_cycle_also_preserves_camera(self) -> None:
        first_camera = {
            "position": [1.0, 2.0, 3.0],
            "focal_point": [0.0, 0.0, 0.0],
            "viewup": [0.0, 1.0, 0.0],
        }
        self.host.captured_camera_state = dict(first_camera)
        session_id = self._open_live_session()

        # First blur + backend response
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertTrue(self.bridge.clear_viewer_focus())
        demoted = _viewer_opened_event(
            request_id=self.host.execution_client.update_calls[-1]["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "proxy"},
            camera_state={},
        )
        demoted["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(demoted)

        # Re-focus
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        refocus_event = _viewer_opened_event(
            request_id=self.host.execution_client.update_calls[-1]["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "full"},
        )
        refocus_event["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(refocus_event)

        # Second blur with a different camera
        second_camera = {
            "position": [10.0, 20.0, 30.0],
            "focal_point": [5.0, 5.0, 5.0],
            "viewup": [0.0, 0.0, 1.0],
        }
        self.host.captured_camera_state = dict(second_camera)
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertTrue(self.bridge.clear_viewer_focus())
        self.assertEqual(
            self.bridge.session_state("node_viewer")["camera_state"], second_camera
        )

        # Explicit reactivation must use the second camera.
        demoted2 = _viewer_opened_event(
            request_id=self.host.execution_client.update_calls[-1]["request_id"],
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            summary={"cache_state": "live_ready"},
            options={"live_mode": "proxy"},
        )
        demoted2["type"] = "viewer_session_updated"
        self.bridge.handle_viewer_execution_event(demoted2)
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )
        self.assertEqual(
            self.host.execution_client.update_calls[-1]["camera_state"], second_camera
        )

    def test_live_open_not_ready_prevents_explicit_activation_materialization(self) -> None:
        session_id = self._open_live_session("node_viewer")
        self.assertTrue(session_id)

        self.assertTrue(self.bridge.clear_viewer_focus())
        state = self.bridge._ensure_session_state("ws_main", "node_viewer")
        state.live_open_status = "blocked"

        update_count = len(self.host.execution_client.update_calls)
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )

        session_state = self.bridge.session_state("node_viewer")
        self.assertEqual(session_state["options"]["live_mode"], "proxy")
        self.assertEqual(len(self.host.execution_client.update_calls), update_count)
        self.assertEqual(self.host.execution_client.materialize_calls, [])

    def test_project_loaded_seeds_viewer_nodes_as_run_required_projection(self) -> None:
        self.host.model.project.workspaces["ws_main"].nodes = {
            "node_viewer": SimpleNamespace(type_id=ENGINEERING_VIEWER_NODE_TYPE_ID),
        }
        state = self.bridge._ensure_session_state("ws_main", "node_viewer")
        state.phase = "open"
        state.backend_id = ENGINEERING_VIEWER_BACKEND_ID
        state.transport_revision = 11
        state.live_open_status = "ready"
        state.cache_state = "live_ready"
        state.step_index = 4
        state.data_refs = {"fields": "fields_ref"}
        state.transport = {
            "kind": "bundle",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            "bundle_path": "C:/temp/viewer_bundle",
        }
        state.camera_state = {"zoom": 1.4}
        state.summary = {
            "result_name": "displacement",
            "set_label": "Set 2",
        }
        state.options = {
            "live_mode": "full",
            "step_index": 4,
        }
        self.bridge._ensure_session_state("ws_old", "old_viewer")

        self.bridge.project_loaded(
            self.host.model.project,
            SimpleNamespace(
                spec_or_none=lambda _type_id: SimpleNamespace(surface_family="viewer")
            ),
        )

        self.assertIn(
            ("ws_main", None),
            self.host.execution_client.invalidate_viewer_calls,
        )
        self.assertIn(
            ("ws_old", None),
            self.host.execution_client.invalidate_viewer_calls,
        )

        projected_state = self.bridge.session_state("node_viewer")
        self.assertEqual(projected_state["phase"], "blocked")
        self.assertEqual(projected_state["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(projected_state["transport_revision"], 11)
        self.assertEqual(projected_state["live_open_status"], "blocked")
        self.assertTrue(projected_state["live_open_blocker"]["rerun_required"])
        self.assertEqual(projected_state["summary"]["result_name"], "displacement")
        self.assertEqual(
            projected_state["summary"]["live_transport_release_reason"],
            "project_reload",
        )
        self.assertTrue(projected_state["summary"]["rerun_required"])
        self.assertEqual(projected_state["options"]["live_mode"], "proxy")
        self.assertEqual(
            projected_state["transport"],
            {"kind": "bundle", "backend_id": ENGINEERING_VIEWER_BACKEND_ID},
        )
        self.assertEqual(projected_state["data_refs"], {})
        self.assertEqual(projected_state["camera_state"], {"zoom": 1.4})

    def test_project_all_run_required_projects_explicit_rerun_blocker(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            },
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready", "result_name": "displacement"},
                options={"live_mode": "full"},
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport_revision=5,
                live_open_status="ready",
                transport={
                    "kind": "bundle",
                    "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                    "bundle_path": "C:/temp/viewer_bundle",
                },
            )
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )

        self.bridge.project_all_run_required(reason="workspace_rerun")

        blocked_state = self.bridge.session_state("node_viewer")
        self.assertEqual(blocked_state["phase"], "blocked")
        self.assertEqual(blocked_state["live_open_status"], "blocked")
        self.assertEqual(blocked_state["live_open_blocker"]["code"], "rerun_required")
        self.assertTrue(blocked_state["live_open_blocker"]["rerun_required"])
        self.assertEqual(
            blocked_state["summary"]["live_transport_release_reason"], "workspace_rerun"
        )
        self.assertTrue(blocked_state["options"]["rerun_required"])
        self.assertEqual(
            blocked_state["transport"],
            {"kind": "bundle", "backend_id": ENGINEERING_VIEWER_BACKEND_ID},
        )

    def test_scoped_invalidation_preserves_other_viewer_and_rejects_late_events(
        self,
    ) -> None:
        session_a = self._open_live_session("viewer_a")
        self.bridge.clear_viewer_focus()
        self._open_live_session("viewer_b")
        viewer_b_before = copy.deepcopy(self.bridge.session_state("viewer_b"))
        stale_open_request = self.host.execution_client.open_calls[-2]["request_id"]

        workspace_epoch, node_epoch = self.bridge._viewer_epochs(  # noqa: SLF001
            "ws_main", "viewer_a"
        )
        node_epochs = (("viewer_a", node_epoch + 1),)
        self.assertTrue(
            self.bridge.adopt_committed_invalidation(
                workspace_id="ws_main",
                node_ids=("viewer_a",),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=viewer_epoch_snapshot_digest(
                    workspace_id="ws_main",
                    node_ids=("viewer_a",),
                    workspace_epoch=workspace_epoch,
                    node_epochs=node_epochs,
                ),
                reason="workspace_rerun",
                run_id="run_partial",
            )
        )

        self.assertEqual(self.bridge.session_state("viewer_b"), viewer_b_before)
        self.assertEqual(self.bridge.session_state("viewer_a")["phase"], "blocked")
        self.assertEqual(self.host.execution_client.invalidate_viewer_calls, [])
        before_empty = copy.deepcopy(self.bridge.sessions_model)
        self.assertTrue(
            self.bridge.adopt_committed_invalidation(
                workspace_id="ws_main",
                node_ids=(),
                workspace_epoch=workspace_epoch,
                node_epochs=(),
                snapshot_digest=viewer_epoch_snapshot_digest(
                    workspace_id="ws_main",
                    node_ids=(),
                    workspace_epoch=workspace_epoch,
                    node_epochs=(),
                ),
                reason="workspace_rerun",
            )
        )
        self.assertEqual(self.bridge.sessions_model, before_empty)

        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=stale_open_request,
                workspace_id="ws_main",
                node_id="viewer_a",
                session_id=session_a,
                summary={"cache_state": "live_ready"},
                transport={"kind": "late_transport"},
                workspace_invalidation_epoch=0,
                node_invalidation_epoch=0,
            )
        )
        self.assertEqual(self.bridge.session_state("viewer_a")["phase"], "blocked")

    def test_invalidated_query_emits_no_late_completion_signal(self) -> None:
        session_id = self._open_live_session()
        results: list[tuple[str, dict[str, Any]]] = []
        self.bridge.viewer_query_completed.connect(
            lambda node_id, result: results.append((str(node_id), dict(result)))
        )
        pending = self.bridge.query_session(
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id=session_id,
            query_type="bounds",
        )
        workspace_epoch, node_epoch = self.bridge._viewer_epochs(  # noqa: SLF001
            "ws_main", "node_viewer"
        )
        node_epochs = (("node_viewer", node_epoch + 1),)
        self.assertTrue(
            self.bridge.adopt_committed_invalidation(
                workspace_id="ws_main",
                node_ids=("node_viewer",),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=viewer_epoch_snapshot_digest(
                    workspace_id="ws_main",
                    node_ids=("node_viewer",),
                    workspace_epoch=workspace_epoch,
                    node_epochs=node_epochs,
                ),
                reason="workspace_rerun",
            )
        )
        self.bridge.handle_viewer_execution_event(
            {
                "type": "viewer_query_result",
                "request_id": pending["request_id"],
                "workspace_id": "ws_main",
                "node_id": "node_viewer",
                "session_id": session_id,
                "backend_id": "",
                "query_type": "bounds",
                "supported": True,
                "value": {"bounds": [0, 1]},
                "explanation": "",
                "workspace_invalidation_epoch": 0,
                "node_invalidation_epoch": 0,
            }
        )
        self.assertEqual(results, [])

    def test_committed_invalidation_adopts_exact_epoch_without_client_increment(
        self,
    ) -> None:
        self._open_live_session("viewer_a")
        self.bridge.clear_viewer_focus()
        self._open_live_session("viewer_b")
        viewer_b_before = copy.deepcopy(self.bridge.session_state("viewer_b"))
        workspace_epoch, node_epoch = self.bridge._viewer_epochs(  # noqa: SLF001
            "ws_main", "viewer_a"
        )
        node_epochs = (("viewer_a", node_epoch + 1),)
        digest = viewer_epoch_snapshot_digest(
            workspace_id="ws_main",
            node_ids=("viewer_a",),
            workspace_epoch=workspace_epoch,
            node_epochs=node_epochs,
        )
        invalidation_calls = list(
            self.host.execution_client.invalidate_viewer_calls
        )

        self.assertTrue(
            self.bridge.adopt_committed_invalidation(
                workspace_id="ws_main",
                node_ids=("viewer_a",),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=digest,
                reason="workspace_rerun",
                run_id="run_partial",
            )
        )

        self.assertEqual(
            self.bridge._viewer_epochs("ws_main", "viewer_a"),  # noqa: SLF001
            (workspace_epoch, node_epoch + 1),
        )
        self.assertEqual(self.bridge.session_state("viewer_a")["phase"], "blocked")
        self.assertEqual(self.bridge.session_state("viewer_b"), viewer_b_before)
        self.assertEqual(
            self.host.execution_client.invalidate_viewer_calls,
            invalidation_calls,
        )
        self.assertFalse(
            self.bridge.adopt_committed_invalidation(
                workspace_id="ws_main",
                node_ids=("viewer_a",),
                workspace_epoch=workspace_epoch,
                node_epochs=node_epochs,
                snapshot_digest=digest,
                reason="workspace_rerun",
            )
        )

    def test_node_settled_runtime_payload_clears_stale_rerun_blocker_after_workspace_rerun(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        session_id = self.bridge.open(
            "node_viewer",
            {
                "data_refs": {"fields": "fields_ref"},
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
            },
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.bridge.handle_viewer_execution_event(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id="ws_main",
                node_id="node_viewer",
                session_id=session_id,
                summary={"cache_state": "live_ready", "result_name": "displacement"},
                options={"live_mode": "full"},
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport_revision=5,
                live_open_status="ready",
                transport={
                    "kind": "bundle",
                    "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                    "bundle_path": "C:/temp/viewer_bundle",
                },
            )
        )
        self.assertTrue(
            self.bridge.set_embedded_interaction_active("node_viewer", True)
        )

        self.bridge.project_all_run_required(reason="workspace_rerun")

        runtime_session_payload = _viewer_opened_event(
            request_id="run_node_viewer",
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id="viewer_session_runtime_seeded",
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            summary={"cache_state": "live_ready", "result_name": "displacement"},
            options={"live_mode": "proxy"},
            data_refs={"dataset": {"kind": "mock_dataset"}},
            transport_revision=7,
            live_open_status="ready",
            transport={
                "kind": "bundle",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "bundle_path": "C:/temp/viewer_bundle",
            },
            workspace_invalidation_epoch=1,
            node_invalidation_epoch=0,
        )
        self.bridge.handle_viewer_execution_event(
            event_to_dict(
                NodeSettledEvent(
                    workspace_id="ws_main",
                    node_id="node_viewer",
                    status="completed",
                    outputs={
                        "session": SettledPortResult(
                            status="value",
                            value=DataTree.from_item(_viewer_session_handle()),
                        )
                    },
                ),
                catalog=self.data_types,
            )
        )
        seeded_open_call = self.host.execution_client.open_calls[-1]
        self.assertEqual(
            seeded_open_call["session_id"],
            "viewer_session_runtime_seeded",
        )
        self.bridge.handle_viewer_execution_event(
            {
                **runtime_session_payload,
                "request_id": seeded_open_call["request_id"],
            }
        )

        reseeded_state = self.bridge.session_state("node_viewer")
        self.assertEqual(reseeded_state["phase"], "open")
        self.assertEqual(reseeded_state["session_id"], "viewer_session_runtime_seeded")
        self.assertEqual(reseeded_state["cache_state"], "live_ready")
        self.assertEqual(reseeded_state["live_open_status"], "ready")
        self.assertEqual(reseeded_state["live_open_blocker"], {})
        self.assertNotIn("rerun_required", reseeded_state["summary"])
        self.assertNotIn("rerun_required", reseeded_state["options"])
        self.assertEqual(reseeded_state["options"]["live_mode"], "proxy")
        self.assertEqual(
            seeded_open_call["session_id"],
            "viewer_session_runtime_seeded",
        )

    def test_node_settled_runtime_session_handle_requests_authoritative_projection(
        self,
    ) -> None:
        self.host.scene.set_selected("node_viewer")
        runtime_session_payload = _viewer_opened_event(
            request_id="run_node_viewer",
            workspace_id="ws_main",
            node_id="node_viewer",
            session_id="viewer_session_runtime_seeded",
            backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            summary={"cache_state": "live_ready", "result_name": "displacement"},
            options={"live_mode": "proxy"},
            data_refs={"dataset": {"kind": "mock_dataset"}},
            transport_revision=7,
            live_open_status="ready",
            transport={
                "kind": "bundle",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "bundle_path": "C:/temp/viewer_bundle",
            },
        )

        open_call_count = len(self.host.execution_client.open_calls)
        self.bridge.handle_viewer_execution_event(
            event_to_dict(
                NodeSettledEvent(
                    workspace_id="ws_main",
                    node_id="node_viewer",
                    status="completed",
                    outputs={
                        "session": SettledPortResult(
                            status="value",
                            value=DataTree.from_item(_viewer_session_handle()),
                        )
                    },
                ),
                catalog=self.data_types,
            )
        )

        pending_state = self.bridge.session_state("node_viewer")
        self.assertEqual(pending_state["phase"], "opening")
        self.assertEqual(
            len(self.host.execution_client.open_calls), open_call_count + 1
        )
        open_call = self.host.execution_client.open_calls[-1]
        self.assertEqual(open_call["workspace_id"], "ws_main")
        self.assertEqual(open_call["node_id"], "node_viewer")
        self.assertEqual(open_call["session_id"], "viewer_session_runtime_seeded")
        self.assertEqual(
            open_call["backend_id"],
            ENGINEERING_VIEWER_BACKEND_ID,
        )
        self.assertEqual(open_call["data_refs"], {})
        self.assertEqual(open_call["transport"], {})

        self.bridge.handle_viewer_execution_event(
            {
                **runtime_session_payload,
                "request_id": open_call["request_id"],
            }
        )
        seeded_state = self.bridge.session_state("node_viewer")
        self.assertEqual(seeded_state["phase"], "open")
        self.assertEqual(seeded_state["session_id"], "viewer_session_runtime_seeded")
        self.assertEqual(seeded_state["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(seeded_state["cache_state"], "live_ready")
        self.assertEqual(seeded_state["live_open_status"], "ready")
        self.assertEqual(
            seeded_state["data_refs"], {"dataset": {"kind": "mock_dataset"}}
        )
        self.assertEqual(
            seeded_state["transport"],
            {
                "kind": "bundle",
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "bundle_path": "C:/temp/viewer_bundle",
            },
        )
        self.assertEqual(seeded_state["options"]["live_mode"], "proxy")
        self.assertEqual(
            len(self.host.execution_client.open_calls), open_call_count + 1
        )

    def test_node_settled_raw_session_projection_is_not_accepted(self) -> None:
        open_call_count = len(self.host.execution_client.open_calls)
        self.bridge.handle_viewer_execution_event(
            event_to_dict(
                NodeSettledEvent(
                    workspace_id="ws_main",
                    node_id="node_viewer",
                    status="completed",
                    outputs={
                        "session": SettledPortResult(
                            status="value",
                            value=DataTree.from_item(
                                _viewer_opened_event(
                                    request_id="legacy_raw_projection",
                                    workspace_id="ws_main",
                                    node_id="node_viewer",
                                    session_id="legacy_raw_projection",
                                )
                            ),
                        )
                    },
                )
            )
        )

        self.assertEqual(len(self.host.execution_client.open_calls), open_call_count)
        self.assertEqual(self.bridge.session_state("node_viewer"), {})


class ViewerSessionBridgeShellIntegrationTests(MainWindowShellTestBase):
    def _dispose_secondary_window(self, window) -> None:  # noqa: ANN001
        for timer_name in ("metrics_timer", "graph_hint_timer", "autosave_timer"):
            timer = getattr(window, timer_name, None)
            if timer is not None:
                timer.stop()
        window.close()
        quick_widget = getattr(window, "quick_widget", None)
        if quick_widget is not None:
            window.takeCentralWidget()
            quick_widget.setSource(QUrl())
            quick_widget.hide()
            quick_widget.deleteLater()
            window.quick_widget = None
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_new_project_clears_context_bound_viewer_session_state(self) -> None:
        self.window.execution_client = _ViewerExecutionClientStub()
        bridge = self.window.quick_widget.rootContext().contextProperty(
            "viewerSessionBridge"
        )
        self.assertIs(bridge, self.window.viewer_session_bridge)

        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=40.0)
        session_id = bridge.open(
            node_id,
            {
                "data_refs": {"fields": "fields_ref"},
                "summary": {"result_name": "displacement"},
            },
        )
        open_call = self.window.execution_client.open_calls[-1]

        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=self.window.workspace_manager.active_workspace_id(),
                node_id=node_id,
                session_id=session_id,
            )
        )
        self.app.processEvents()

        self.assertEqual(bridge.session_count, 1)
        for workspace in self.window.model.project.workspaces.values():
            workspace.dirty = False
        self.window._new_project()
        self.app.processEvents()
        self.assertEqual(bridge.session_count, 0)

    def test_restore_session_keeps_saved_viewer_project_recent_without_reopening(
        self,
    ) -> None:
        self.window.execution_client = _ViewerExecutionClientStub()
        bridge = self.window.viewer_session_bridge
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("model.viewer", x=80.0, y=40.0)
        session_id = bridge.open(
            node_id,
            {
                "data_refs": {
                    "fields": {"kind": "handle_ref", "handle_id": "handle::fields"}
                },
                "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                "camera_state": {"zoom": 1.5},
                "playback_state": {"state": "paused", "step_index": 4},
                "summary": {"result_name": "Displacement", "set_label": "Set 4"},
                "options": {"live_mode": "full"},
            },
        )
        open_call = self.window.execution_client.open_calls[-1]
        bundle_path = Path(self._temp_dir.name) / "viewer_bundle" / "bundle.vtp"
        self.window.execution_event.emit(
            _viewer_opened_event(
                request_id=open_call["request_id"],
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                transport_revision=9,
                live_open_status="ready",
                transport={
                    "kind": "bundle",
                    "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
                    "bundle_path": str(bundle_path),
                },
                camera_state={"zoom": 1.5},
                data_refs={
                    "fields": {"kind": "handle_ref", "handle_id": "handle::fields"}
                },
            )
        )
        self.app.processEvents()

        project_path = (
            Path(self._temp_dir.name) / "projects" / "viewer_restore_bridge.cxproj"
        )
        project_path.parent.mkdir(parents=True, exist_ok=True)
        self.window.serializer.save_document(
            str(project_path),
            self.window.serializer.to_document(self.window.model.project),
        )
        self._session_path.write_text(
            json.dumps(
                {
                    "project_path": str(project_path),
                    "last_manual_save_ts": project_path.stat().st_mtime,
                    "recent_project_paths": [str(project_path)],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        restored = self.window.__class__()
        restored.resize(1200, 800)
        restored.show()
        self.app.processEvents()
        try:
            self.assertEqual(restored.project_path, "")
            self.assertIn(
                str(project_path), restored.project_session_state.recent_project_paths
            )
            self.assertEqual(restored.viewer_session_bridge.session_state(node_id), {})
        finally:
            self._dispose_secondary_window(restored)


if __name__ == "__main__":
    unittest.main()
