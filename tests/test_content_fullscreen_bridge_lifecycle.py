from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_STATE_PROPERTY,
    ExcalidrawBoardNodePlugin,
)
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_TYPE_ID,
    WebPageViewerNodePlugin,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.ui_qml import content_fullscreen_bridge as bridge_module
from ea_node_editor.ui_qml.content_fullscreen_bridge import (
    ContentFullscreenBridge,
    _FullscreenWebSurfaceBridge,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from ea_node_editor.web_host.bridge import WebSurfaceArtifactService


class _ExecutionSignalSource(QObject):
    changed = pyqtSignal()


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(WebPageViewerNodePlugin)
    registry.register(ExcalidrawBoardNodePlugin)
    return registry


class ContentFullscreenBridgeLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temporary_directory.name)
        workspace = WorkspaceData(workspace_id="ws-lifecycle", name="Lifecycle")
        project = ProjectData(
            project_id="proj-lifecycle",
            name="Lifecycle",
            active_workspace_id=workspace.workspace_id,
            workspaces={workspace.workspace_id: workspace},
        )
        self.current_model = GraphModel(project)
        self.current_registry = _registry()
        self.current_workspace_id = workspace.workspace_id
        self.current_project_path: str | None = None
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(
            self.current_model,
            self.current_registry,
            self.current_workspace_id,
        )
        self.execution = _ExecutionSignalSource()
        self.run_state = ShellRunState()
        self.script_editor = ScriptEditorModel()
        self.viewer_session_bridge = ViewerSessionBridge(
            execution_client_provider=lambda: None,
            active_workspace_id_provider=lambda: self.current_workspace_id,
            workspace_provider=lambda workspace_id: (
                self.current_model.project.workspaces.get(workspace_id)
            ),
            scene_bridge=self.scene,
            data_types=self.current_registry.data_types,
        )
        self.artifact_store = ProjectArtifactStore.from_project_metadata(
            project_path=None,
            project_metadata=self.current_model.project.metadata,
        )
        self.artifact_factory_calls: list[tuple[str, str, str, str, str]] = []
        self.persist_calls = 0
        self.provider_calls: dict[str, list[object]] = {
            "model": [],
            "registry": [],
            "workspace": [],
            "project": [],
        }
        self.bridge = self._make_bridge()

    def tearDown(self) -> None:
        self.bridge.shutdown()
        self._temporary_directory.cleanup()

    def _model_provider(self) -> GraphModel:
        self.provider_calls["model"].append(self.current_model)
        return self.current_model

    def _registry_provider(self) -> NodeRegistry:
        self.provider_calls["registry"].append(self.current_registry)
        return self.current_registry

    def _active_workspace_id_provider(self) -> str:
        self.provider_calls["workspace"].append(self.current_workspace_id)
        return self.current_workspace_id

    def _project_context_provider(self) -> tuple[str | None, dict[str, object]]:
        result = (
            self.current_project_path,
            dict(self.current_model.project.metadata),
        )
        self.provider_calls["project"].append(result)
        return result

    def _persist_artifact_store(self, store: ProjectArtifactStore) -> None:
        self.persist_calls += 1
        self.artifact_store = store
        metadata = dict(self.current_model.project.metadata)
        metadata["artifact_store"] = store.metadata
        self.current_model.project.replace_metadata(metadata)

    def _create_artifact_service(
        self,
        workspace_id: str,
        workspace_name: str,
        node_id: str,
        node_title: str,
        node_type: str,
    ) -> WebSurfaceArtifactService:
        self.artifact_factory_calls.append(
            (workspace_id, workspace_name, node_id, node_title, node_type)
        )
        return WebSurfaceArtifactService(
            artifact_store=lambda: self.artifact_store,
            persist_artifact_store=self._persist_artifact_store,
            temporary_root_parent=self.temp_path,
            node_workspace_id=workspace_id,
            node_workspace_name=workspace_name,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )

    def _make_bridge(self) -> ContentFullscreenBridge:
        return ContentFullscreenBridge(
            model_provider=self._model_provider,
            registry_provider=self._registry_provider,
            active_workspace_id_provider=self._active_workspace_id_provider,
            project_context_provider=self._project_context_provider,
            scene_bridge=self.scene,
            viewer_session_bridge=self.viewer_session_bridge,
            run_state=self.run_state,
            execution_state_changed_signal=self.execution.changed,
            script_editor=self.script_editor,
            save_file_dialog=lambda *_args, **_kwargs: "",
            trim_video_clip_replace=lambda *_args: {},
            trim_video_clip_copy=lambda *_args: {},
            create_web_surface_artifact_service=self._create_artifact_service,
        )

    def _add_open_web_node(self) -> str:
        node = self.current_model.add_node(
            self.current_workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Web Page Viewer",
            0.0,
            0.0,
            properties={"start_location": "https://example.com"},
        )
        self.assertTrue(self.bridge.request_open_node(node.node_id))
        self.assertTrue(self.bridge.open)
        self.assertEqual(self.bridge.node_id, node.node_id)
        return node.node_id

    def _add_open_web_editor(self) -> str:
        node = self.current_model.add_node(
            self.current_workspace_id,
            EXCALIDRAW_BOARD_TYPE_ID,
            "Excalidraw Board",
            0.0,
            0.0,
            properties={
                EXCALIDRAW_STATE_PROPERTY: {
                    "type": "excalidraw",
                    "elements": [],
                    "appState": {},
                    "files": {},
                }
            },
        )
        self.assertTrue(self.bridge.request_open_node(node.node_id))
        self.assertIsNotNone(self.bridge.web_surface_bridge)
        return node.node_id

    def test_workspace_changed_closes_without_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "artifact storage is required"):
            _FullscreenWebSurfaceBridge(
                {},
                artifact_service=None,  # type: ignore[arg-type]
                artifact_scope="ws:node",
            )

        old_node_id = self._add_open_web_node()
        self.assertEqual(
            {key: len(values) for key, values in self.provider_calls.items()},
            {"model": 1, "registry": 1, "workspace": 1, "project": 1},
        )
        self.scene.workspace_changed.emit("ws-other")
        self.assertFalse(self.bridge.open)
        self.assertEqual(self.bridge.node_id, "")
        self.assertEqual(self.bridge.last_error, "")

        replacement_workspace = WorkspaceData(
            workspace_id="ws-replacement",
            name="Replacement",
        )
        replacement_project = ProjectData(
            project_id="proj-replacement",
            name="Replacement",
            active_workspace_id=replacement_workspace.workspace_id,
            workspaces={replacement_workspace.workspace_id: replacement_workspace},
            metadata={"provider_marker": "replacement"},
        )
        replacement_model = GraphModel(replacement_project)
        replacement_registry = _registry()
        replacement_node = replacement_model.add_node(
            replacement_workspace.workspace_id,
            WEB_PAGE_VIEWER_TYPE_ID,
            "Replacement Page",
            0.0,
            0.0,
            properties={"start_location": "https://replacement.example"},
        )
        self.current_model = replacement_model
        self.current_registry = replacement_registry
        self.current_workspace_id = replacement_workspace.workspace_id
        self.current_project_path = str(self.temp_path / "replacement.cxproj")
        self.scene.set_workspace(
            replacement_model,
            replacement_registry,
            replacement_workspace.workspace_id,
        )

        self.assertFalse(self.bridge.can_open_node(old_node_id))
        self.assertEqual(
            {key: len(values) for key, values in self.provider_calls.items()},
            {"model": 2, "registry": 2, "workspace": 2, "project": 1},
        )
        self.assertTrue(self.bridge.request_open_node(replacement_node.node_id))
        self.assertEqual(
            {key: len(values) for key, values in self.provider_calls.items()},
            {"model": 3, "registry": 3, "workspace": 3, "project": 2},
        )
        self.assertEqual(self.bridge.workspace_id, replacement_workspace.workspace_id)
        self.assertEqual(self.bridge.node_id, replacement_node.node_id)
        self.assertIs(self.provider_calls["model"][-1], replacement_model)
        self.assertIs(self.provider_calls["registry"][-1], replacement_registry)
        self.assertEqual(
            self.provider_calls["workspace"][-1],
            replacement_workspace.workspace_id,
        )
        project_path, metadata = self.provider_calls["project"][-1]
        self.assertEqual(project_path, self.current_project_path)
        self.assertEqual(metadata, {"provider_marker": "replacement"})

    def test_nodes_changed_closes_when_active_node_disappears(self) -> None:
        node_id = self._add_open_web_node()
        self.scene.remove_workspace_node(node_id)

        self.assertFalse(self.bridge.open)
        self.assertEqual(self.bridge.node_id, "")
        self.assertEqual(self.bridge.last_error, "")

    def test_tabular_provider_and_worker_pool_are_lazy_reused_and_shutdown_safely(self) -> None:
        self._add_open_web_editor()
        self.assertIsNotNone(self.bridge.web_surface_bridge)
        fake_provider = Mock()
        fake_pool = Mock()
        fake_pool.job_finished = Mock()

        with (
            patch.object(
                bridge_module,
                "TabularPreviewProvider",
                return_value=fake_provider,
            ) as provider_factory,
            patch(
                "ea_node_editor.ui.tabular_preview_async.TabularPreviewWorkerPool",
                return_value=fake_pool,
            ) as pool_factory,
        ):
            self.assertIs(self.bridge._ensure_tabular_preview_provider(), fake_provider)  # noqa: SLF001
            self.assertIs(self.bridge._ensure_tabular_preview_provider(), fake_provider)  # noqa: SLF001
            self.assertIs(self.bridge._ensure_tabular_preview_worker_pool(), fake_pool)  # noqa: SLF001
            self.assertIs(self.bridge._ensure_tabular_preview_worker_pool(), fake_pool)  # noqa: SLF001
            provider_factory.assert_called_once_with(
                project_context_provider=self.bridge._project_context  # noqa: SLF001
            )
            pool_factory.assert_called_once_with(self.bridge)
            fake_pool.job_finished.connect.assert_called_once_with(
                self.bridge._on_tabular_preview_job_finished  # noqa: SLF001
            )

            self.bridge._pending_tabular_payload_job = "payload-job"  # noqa: SLF001
            self.bridge._pending_tabular_payload_node_id = self.bridge.node_id  # noqa: SLF001
            self.bridge._latest_tabular_window_request_id = "request-1"  # noqa: SLF001
            self.bridge._pending_tabular_window_jobs["window-job"] = {  # noqa: SLF001
                "node_id": self.bridge.node_id,
                "request_id": "request-1",
                "result": {"state": "ready"},
            }
            factory_count = len(self.artifact_factory_calls)

            self.bridge.shutdown()
            self.bridge.shutdown()
            fake_pool.shutdown.assert_called_once_with()

            self.scene.workspace_changed.emit("late")
            self.scene.nodes_changed.emit()
            self.scene.edges_changed.emit()
            self.execution.changed.emit()
            self.bridge._on_tabular_preview_job_finished("payload-job", "")  # noqa: SLF001
            self.bridge._on_tabular_preview_job_finished("window-job", "")  # noqa: SLF001

            self.assertFalse(self.bridge.open)
            self.assertIsNone(self.bridge.web_surface_bridge)
            self.assertIsNone(self.bridge._tabular_preview_provider)  # noqa: SLF001
            self.assertIsNone(self.bridge._tabular_preview_worker_pool)  # noqa: SLF001
            self.assertEqual(self.bridge._pending_tabular_window_jobs, {})  # noqa: SLF001
            self.assertEqual(self.bridge._pending_tabular_payload_job, "")  # noqa: SLF001
            self.assertEqual(self.persist_calls, 0)
            self.assertFalse(self.bridge.request_open_node("late-node"))
            self.assertEqual(len(self.artifact_factory_calls), factory_count)
            with self.assertRaisesRegex(RuntimeError, "shut down"):
                self.bridge._ensure_tabular_preview_provider()  # noqa: SLF001
            with self.assertRaisesRegex(RuntimeError, "shut down"):
                self.bridge._ensure_tabular_preview_worker_pool()  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
