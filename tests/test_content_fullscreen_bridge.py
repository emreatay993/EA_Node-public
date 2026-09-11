from __future__ import annotations

import base64
import gc
import hashlib
import copy
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest import mock

from tests.web_snapshot_test_support import png_bytes
from ea_node_editor.common.board_snapshot import board_scene_digest
from ea_node_editor.web_host.bridge import WebSurfaceArtifactError

from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, QObject, QPointF, QMarginsF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.nodes.builtins.core import PYTHON_SCRIPT_DEFAULT_SOURCE
from ea_node_editor.nodes.builtins.engineering_viewer import ENGINEERING_VIEWER_NODE_TYPE_ID
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.builtins.jupyter_notebook import JUPYTER_NOTEBOOK_TYPE_ID
from ea_node_editor.nodes.builtins.passive_mail import (
    PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
)
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.web_viewer import WEB_PAGE_VIEWER_TYPE_ID
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
    TABULAR_SELECTED_COLUMNS_PROPERTY,
    TABULAR_TABLE_VIEW_STATE_PROPERTY,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload.fullscreen import build_content_fullscreen_media_payload
from ea_node_editor.ui_qml.script_editor_model import ScriptEditorModel
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from ea_node_editor.web_host.bridge import WebSurfaceArtifactService, WebSurfaceBridge
from tests.main_window_shell.base import MainWindowShellTestBase
from tests.qt_wait import wait_for_condition_or_raise


def _data_url(mime_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _payload_keys(value) -> list[str]:  # noqa: ANN001
    if isinstance(value, dict):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_payload_keys(item))
        return keys
    if isinstance(value, list):
        keys = []
        for item in value:
            keys.extend(_payload_keys(item))
        return keys
    return []


def test_content_fullscreen_media_payload_supports_mail_preview_url(tmp_path: Path) -> None:
    mail_path = tmp_path / "content-fullscreen-message.eml"
    mail_path.write_text(
        "Subject: Fullscreen Mail\r\n"
        "From: sender@example.com\r\n"
        "To: receiver@example.com\r\n"
        "\r\n"
        "Mail body",
        encoding="utf-8",
    )
    registry = build_default_registry()
    spec = registry.get_spec(PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID)
    node = NodeInstance(
        node_id="mail-fullscreen-node",
        type_id=PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
        title="Mail Panel",
        x=10.0,
        y=20.0,
        properties={"source_path": str(mail_path)},
    )

    payload = build_content_fullscreen_media_payload(
        workspace_id="workspace-mail",
        node=node,
        spec=spec,
    )

    assert payload["media_kind"] == "mail"
    assert payload["surface_spec"]["fullscreen"]["content_kind"] == "mail"
    assert payload["preview_state"] == "ready"
    assert str(payload["preview_url"]).startswith("file:")
    assert str(payload["resolved_source_url"]).startswith("file:")
    assert payload["metadata"]["subject"] == "Fullscreen Mail"
    assert payload["attachment_summary"] == "No attachments"


class _VideoTrimPresenterRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def request_trim_video_clip_replace(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        state: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(("replace", (video_node_id, start_ms, end_ms, dict(state))))
        return {
            "success": True,
            "created_node_id": "",
            "created_type_id": MEDIA_PANEL_TYPE_ID,
            "source_ref": "project-staged://fullscreen_replace",
            "error": {},
            "request_id": "fullscreen-replace",
        }

    def request_trim_video_clip_copy(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        scene_x: float,
        scene_y: float,
        state: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(("copy", (video_node_id, start_ms, end_ms, scene_x, scene_y, dict(state))))
        return {
            "success": True,
            "created_node_id": "fullscreen-copy",
            "created_type_id": MEDIA_PANEL_TYPE_ID,
            "source_ref": "project-staged://fullscreen_copy",
            "error": {},
            "request_id": "fullscreen-copy",
        }


class _FakeTabularWorkerPool:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, object]] = []
        self.job_finished = mock.Mock()

    def schedule(self, job_key: str, fn) -> bool:  # noqa: ANN001
        self.scheduled.append((job_key, fn))
        return True

    def shutdown(self) -> None:
        return None


class _SignalSource(QObject):
    changed = pyqtSignal()


class _ContentFullscreenDirectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self._temporary_directory.name)
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)
        self.run_state = ShellRunState()
        self.execution_state = _SignalSource()
        self.project_meta = _SignalSource()
        self.project_path = ""
        self.script_editor = ScriptEditorModel()
        self.viewer_session_bridge = ViewerSessionBridge(
            execution_client_provider=lambda: None,
            active_workspace_id_provider=lambda: self.workspace_id,
            workspace_provider=lambda workspace_id: (
                self.model.project.workspaces.get(workspace_id)
            ),
            scene_bridge=self.scene,
            data_types=self.registry.data_types,
        )
        self.serializer = JsonProjectSerializer(self.registry)
        self._artifact_store: ProjectArtifactStore | None = None
        self.artifact_factory_calls: list[tuple[str, str, str, str, str]] = []
        self.project_metadata_events: list[int] = []
        self.project_meta.changed.connect(
            lambda: self.project_metadata_events.append(
                self.model.project.project_document_revision
            )
        )
        self.save_file_dialog_result = ""
        self.save_file_dialog_calls: list[
            tuple[tuple[object, ...], dict[str, object]]
        ] = []
        self.video_trim_presenter = _VideoTrimPresenterRecorder()
        self.bridge = ContentFullscreenBridge(
            model_provider=lambda: self.model,
            registry_provider=lambda: self.registry,
            active_workspace_id_provider=lambda: self.workspace_id,
            project_context_provider=self._project_context,
            scene_bridge=self.scene,
            viewer_session_bridge=self.viewer_session_bridge,
            run_state=self.run_state,
            execution_state_changed_signal=self.execution_state.changed,
            script_editor=self.script_editor,
            save_file_dialog=self._save_file_dialog,
            trim_video_clip_replace=self._trim_video_clip_replace,
            trim_video_clip_copy=self._trim_video_clip_copy,
            create_web_surface_artifact_service=(
                self._create_web_surface_artifact_service
            ),
        )

    def tearDown(self) -> None:
        self.bridge.shutdown()
        self.app.processEvents()
        self._temporary_directory.cleanup()

    def _project_context(self) -> tuple[str | None, dict[str, Any] | None]:
        return self.project_path or None, dict(self.model.project.metadata)

    def _project_artifact_store(self) -> ProjectArtifactStore:
        if self._artifact_store is None:
            self._artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=self.project_path or None,
                project_metadata=self.model.project.metadata,
            )
        return self._artifact_store

    def _persist_project_artifact_store(self, store: ProjectArtifactStore) -> None:
        self._artifact_store = store
        metadata = dict(self.model.project.metadata)
        metadata["artifact_store"] = store.metadata
        if self.model.project.replace_metadata(metadata):
            self.project_meta.changed.emit()

    def _ensure_project_staging_root(self) -> Path:
        return self._project_artifact_store().ensure_staging_root(
            temporary_root_parent=self.temp_path
        )

    def _create_web_surface_artifact_service(
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
            artifact_store=self._project_artifact_store,
            persist_artifact_store=self._persist_project_artifact_store,
            temporary_root_parent=self.temp_path,
            node_workspace_id=workspace_id,
            node_workspace_name=workspace_name,
            node_id=node_id,
            node_title=node_title,
            node_type=node_type,
        )

    def _save_file_dialog(self, *args: object, **kwargs: object) -> str:
        self.save_file_dialog_calls.append((args, dict(kwargs)))
        return self.save_file_dialog_result

    def _trim_video_clip_replace(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return self.video_trim_presenter.request_trim_video_clip_replace(
            *args, **kwargs
        )

    def _trim_video_clip_copy(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return self.video_trim_presenter.request_trim_video_clip_copy(*args, **kwargs)

    def _add_viewer_node(self) -> str:
        return self.scene.add_node_from_type(
            ENGINEERING_VIEWER_NODE_TYPE_ID, x=120.0, y=80.0
        )

    def _write_test_image(self, name: str) -> Path:
        path = self.temp_path / name
        image = QImage(32, 20, QImage.Format.Format_ARGB32)
        image.fill(0xFF336699)
        self.assertTrue(image.save(str(path)))
        return path

    def _write_test_pdf(self, name: str, *, page_count: int = 1) -> Path:
        path = self.temp_path / name
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
        painter = QPainter(writer)
        for page_index in range(page_count):
            if page_index > 0:
                writer.newPage()
            painter.drawText(QRectF(80.0, 120.0, 420.0, 120.0), f"PDF page {page_index + 1}")
        painter.end()
        del painter
        del writer
        gc.collect()
        return path

    def _add_image_node(self, *, name: str = "content-fullscreen-image.png") -> str:
        image_path = self._write_test_image(name)
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": str(image_path),
                "fit_mode": "cover",
                "crop_x": 0.1,
                "crop_y": 0.2,
                "crop_w": 0.5,
                "crop_h": 0.6,
                "rotation_degrees": 90,
                "mirror_horizontal": True,
                "mirror_vertical": False,
            },
        )
        self.app.processEvents()
        return node_id

    def _add_video_node(self, *, name: str = "content-fullscreen-video.mp4") -> str:
        video_path = self.temp_path / name
        video_path.write_bytes(b"not a decoded fixture")
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": str(video_path),
                "fit_mode": "cover",
                "auto_play": True,
                "loop": True,
                "muted": True,
                "volume": 0.4,
                "playback_rate": 1.25,
                "position_ms": 3200,
                "timeline_bookmarks": [{"id": "mark-1", "label": "Mark 1", "position_ms": 3000}],
                "clip_enabled": True,
                "clip_start_ms": 2000,
                "clip_end_ms": 6000,
            },
        )
        self.app.processEvents()
        return node_id

    def _add_pdf_node(
        self,
        *,
        name: str = "content-fullscreen-pages.pdf",
        page_count: int = 3,
        page_number: int = 1,
    ) -> str:
        pdf_path = self._write_test_pdf(name, page_count=page_count)
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": str(pdf_path),
                "page_number": page_number,
            },
        )
        self.app.processEvents()
        return node_id

    def _add_excalidraw_node(self) -> tuple[str, dict, dict]:
        node_id = self.scene.add_node_from_type(
            EXCALIDRAW_BOARD_TYPE_ID, x=160.0, y=120.0
        )
        state = {
            "type": "excalidraw",
            "elements": [{"id": "rect-1", "type": "rectangle", "isDeleted": False}],
            "appState": {"name": "Fullscreen map"},
            "files": {},
        }
        preview_ref = {
            "uri": "saved://excalidraw-preview",
            "mime_type": "image/png",
            "status": "ready",
        }
        self.scene.set_node_properties(
            node_id,
            {
                EXCALIDRAW_STATE_PROPERTY: state,
                EXCALIDRAW_PREVIEW_REF_PROPERTY: preview_ref,
            },
        )
        self.app.processEvents()
        return node_id, state, preview_ref

    def _ensure_tabular_function_registered(self) -> None:
        self.assertIsNotNone(
            self.registry.spec_or_none(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        )

    def _add_tabular_node(self) -> tuple[str, Path]:
        self._ensure_tabular_function_registered()
        source = self.temp_path / "content-fullscreen-tabular.csv"
        rows = ["station,temp,count"]
        rows.extend(f"S{index},{20 + index / 10:.1f},{index}" for index in range(120))
        source.write_text("\n".join(rows) + "\n", encoding="utf-8")
        node_id = self.scene.add_node_from_type(
            TABULAR_DATA_INPUT_NODE_TYPE_ID, x=180.0, y=120.0
        )
        self.scene.set_node_properties(
            node_id,
            {
                "path": str(source),
                "delimiter": ",",
                "encoding": "utf-8",
                "header_row": 0,
                "skip_rows": 0,
                "schema_hints": {"temp": "float64", "count": "int64"},
            },
        )
        self.app.processEvents()
        return node_id, source

    def _add_web_page_node(self, **properties) -> str:  # noqa: ANN003
        self.assertIsNotNone(self.registry.spec_or_none(WEB_PAGE_VIEWER_TYPE_ID))
        node_id = self.scene.add_node_from_type(
            WEB_PAGE_VIEWER_TYPE_ID, x=220.0, y=120.0
        )
        if properties:
            self.scene.set_node_properties(node_id, properties)
        self.app.processEvents()
        return node_id

    def _add_jupyter_node(self, **properties) -> str:  # noqa: ANN003
        self.assertIsNotNone(self.registry.spec_or_none(JUPYTER_NOTEBOOK_TYPE_ID))
        node_id = self.scene.add_node_from_type(
            JUPYTER_NOTEBOOK_TYPE_ID, x=240.0, y=140.0
        )
        if properties:
            self.scene.set_node_properties(node_id, properties)
        self.app.processEvents()
        return node_id

    def _bridge(self) -> ContentFullscreenBridge:
        return self.bridge


class ContentFullscreenBridgeTests(_ContentFullscreenDirectTestCase):
    def test_content_fullscreen_bridge_opens_image_media_with_preview_contract(self) -> None:
        node_id = self._add_image_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        signal_count = 0

        def _record_change() -> None:
            nonlocal signal_count
            signal_count += 1

        bridge.content_fullscreen_changed.connect(_record_change)

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertEqual(signal_count, 1)
        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "media")
        self.assertEqual(bridge.title, "Media Panel")
        self.assertEqual(bridge.last_error, "")
        self.assertEqual(bridge.viewer_payload, {})

        media_payload = bridge.media_payload
        self.assertEqual(media_payload["media_kind"], "image")
        self.assertEqual(media_payload["workspace_id"], workspace_id)
        self.assertEqual(media_payload["node_id"], node_id)
        self.assertEqual(media_payload["fit_mode"], "cover")
        self.assertAlmostEqual(float(media_payload["crop"]["x"]), 0.1)
        self.assertAlmostEqual(float(media_payload["crop"]["y"]), 0.2)
        self.assertAlmostEqual(float(media_payload["crop"]["width"]), 0.5)
        self.assertAlmostEqual(float(media_payload["crop"]["height"]), 0.6)
        self.assertEqual(media_payload["rotation_degrees"], 90)
        self.assertTrue(media_payload["mirror_horizontal"])
        self.assertFalse(media_payload["mirror_vertical"])
        self.assertEqual(media_payload["source_pixel_width"], 32)
        self.assertEqual(media_payload["source_pixel_height"], 20)
        self.assertTrue(str(media_payload["resolved_source_url"]).startswith("file:"))
        self.assertTrue(str(media_payload["preview_url"]).startswith("image://local-media-preview/preview?source="))

        previous_signal_count = signal_count
        self.scene.set_node_properties(
            node_id,
            {
                "fit_mode": "original",
                "crop_x": 0.0,
                "crop_y": 0.0,
                "crop_w": 1.0,
                "crop_h": 1.0,
                "rotation_degrees": 180,
                "mirror_horizontal": False,
                "mirror_vertical": True,
            },
        )
        self.app.processEvents()
        media_payload = bridge.media_payload
        self.assertGreater(signal_count, previous_signal_count)
        self.assertEqual(media_payload["fit_mode"], "original")
        self.assertEqual(media_payload["crop"], {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
        self.assertEqual(media_payload["rotation_degrees"], 180)
        self.assertFalse(media_payload["mirror_horizontal"])
        self.assertTrue(media_payload["mirror_vertical"])

        node_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        self.assertEqual(node_payload["surface_spec"]["component_key"], "media")
        self.assertEqual(media_payload["surface_spec"]["fullscreen"]["content_kind"], "media")
        self.assertIn("stylus", node_payload["surface_spec"]["input_capabilities"]["devices"])
        self.assertNotIn("content_fullscreen", json.dumps(_payload_keys(node_payload)).lower())
        document = self.serializer.to_document(self.model.project)
        self.assertNotIn("surface_spec", json.dumps(_payload_keys(document)).lower())
        self.assertNotIn("fullscreen", json.dumps(_payload_keys(document)).lower())

    def test_content_fullscreen_media_refreshes_on_exposure_edge_and_execution(self) -> None:
        node_id = self._add_image_node(name="content-fullscreen-refresh.png")
        workspace_id = self.workspace_id
        image_path = self.temp_path / "content-fullscreen-refresh.png"
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        self.assertEqual(bridge.media_payload["source_state"], "ready")

        self.scene.set_exposed_port(node_id, "source", True)
        self.app.processEvents()
        self.assertEqual(bridge.media_payload["source_state"], "waiting")
        self.assertEqual(bridge.media_payload["resolved_source_url"], "")
        self.assertEqual(bridge.media_payload["source_ref"], "")

        source_id = self.scene.add_node_from_type(
            "io.path_pointer", x=20.0, y=80.0
        )
        self.scene.add_edge(source_id, "path", node_id, "source")
        self.app.processEvents()
        self.assertTrue(bridge.media_payload["input_connected"])
        self.assertEqual(bridge.media_payload["source_state"], "waiting")

        self.run_state.cached_node_output_records_by_workspace_id = {
            workspace_id: {
                node_id: {
                    "run-1": {
                        "record_id": "run-1",
                        "observed_at_epoch_ms": 1.0,
                        "outputs": {
                            "_surface_source": SettledPortResult(
                                status="value",
                                value=DataTree.from_item(str(image_path)),
                            )
                        },
                    }
                }
            }
        }
        self.run_state.node_solution_facts_by_workspace_id = {
            workspace_id: {
                node_id: NodeSolutionFact(
                    project_id=self.model.project.project_id,
                    workspace_id=workspace_id,
                    node_id=node_id,
                    freshness=SolutionFreshness.CURRENT,
                    revision=1,
                    retained_record_id="run-1",
                    retained_solution_key="a" * 64,
                    residency=SolutionResidency.SESSION,
                    last_disposition=SolutionDisposition.RECOMPUTED,
                )
            }
        }
        self.run_state.node_execution_workspace_id = workspace_id
        self.run_state.completed_node_ids.add(node_id)
        self.execution_state.changed.emit()
        self.app.processEvents()

        self.assertEqual(bridge.media_payload["source_state"], "ready")
        self.assertEqual(bridge.media_payload["authority"], "input")
        self.assertEqual(bridge.media_payload["source_ref"], str(image_path))

        self.run_state.completed_node_ids.discard(node_id)
        self.run_state.running_node_ids.add(node_id)
        self.execution_state.changed.emit()
        self.app.processEvents()
        self.assertEqual(bridge.media_payload["source_state"], "running")
        self.assertEqual(bridge.media_payload["resolved_source_url"], "")

    def test_content_fullscreen_bridge_exposes_animated_image_runtime_metadata(self) -> None:
        image_path = Path(__file__).resolve().parent / "fixtures" / "media" / "animated-small.gif"
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": str(image_path),
                "fit_mode": "contain",
                "animation_playback_mode": "pause",
            },
        )
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        media_payload = bridge.media_payload

        self.assertEqual(media_payload["preview_state"], "ready")
        self.assertEqual(media_payload["format"], "gif")
        self.assertEqual(media_payload["frame_count"], 3)
        self.assertTrue(media_payload["animation_supported"])
        self.assertTrue(media_payload["is_animated"])
        self.assertEqual(
            (media_payload["source_pixel_width"], media_payload["source_pixel_height"]),
            (24, 18),
        )
        resolved_path = Path(QUrl(media_payload["resolved_source_url"]).toLocalFile())
        self.assertEqual(resolved_path, image_path)

    def test_content_fullscreen_bridge_opens_pdf_media_with_page_preview_contract(self) -> None:
        pdf_path = Path(__file__).resolve().parent / "fixtures" / "passive_nodes" / "reference_preview.pdf"
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": str(pdf_path),
                "page_number": 1,
            },
        )
        self.app.processEvents()

        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.content_kind, "media")
        media_payload = bridge.media_payload
        self.assertEqual(media_payload["media_kind"], "pdf")
        self.assertEqual(media_payload["surface_spec"]["fullscreen"]["content_kind"], "media")
        self.assertEqual(media_payload["fit_mode"], "contain")
        self.assertEqual(media_payload["page_number"], 1)
        self.assertEqual(media_payload["pdf_preview"]["state"], "ready")
        self.assertEqual(media_payload["resolved_page_number"], 1)
        self.assertTrue(str(media_payload["preview_url"]).startswith("image://local-pdf-preview/preview?"))

    def test_content_fullscreen_bridge_navigates_pdf_pages(self) -> None:
        node_id = self._add_pdf_node(page_count=3, page_number=1)
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertEqual(bridge.content_kind, "media")
        self.assertEqual(bridge.media_payload["pdf_preview"]["page_count"], 3)
        self.assertEqual(bridge.media_payload["resolved_page_number"], 1)

        self.assertTrue(bridge.request_pdf_page_delta(-1))
        self.assertEqual(bridge.media_payload["resolved_page_number"], 1)

        self.assertTrue(bridge.request_pdf_page_delta(1))
        self.assertEqual(bridge.media_payload["page_number"], 2)
        self.assertEqual(bridge.media_payload["resolved_page_number"], 2)

        self.assertTrue(bridge.request_pdf_page_number(99))
        self.assertEqual(bridge.media_payload["page_number"], 3)
        self.assertEqual(bridge.media_payload["resolved_page_number"], 3)

        self.assertTrue(bridge.request_pdf_page_delta(1))
        self.assertEqual(bridge.media_payload["resolved_page_number"], 3)

        self.assertTrue(bridge.request_pdf_page_number(0))
        self.assertEqual(bridge.media_payload["page_number"], 1)
        self.assertEqual(bridge.media_payload["resolved_page_number"], 1)

    def test_content_fullscreen_bridge_opens_video_media_with_playback_contract(self) -> None:
        node_id = self._add_video_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "media")
        media_payload = bridge.media_payload
        self.assertEqual(media_payload["media_kind"], "video")
        self.assertEqual(media_payload["surface_spec"]["fullscreen"]["content_kind"], "media")
        self.assertEqual(media_payload["fit_mode"], "cover")
        self.assertTrue(media_payload["auto_play"])
        self.assertTrue(media_payload["loop"])
        self.assertTrue(media_payload["muted"])
        self.assertEqual(media_payload["volume"], 0.4)
        self.assertEqual(media_payload["playback_rate"], 1.25)
        self.assertEqual(media_payload["position_ms"], 3200)
        self.assertEqual(
            media_payload["timeline_bookmarks"],
            [{"id": "mark-1", "label": "Mark 1", "position_ms": 3000}],
        )
        self.assertTrue(media_payload["clip_enabled"])
        self.assertEqual(media_payload["clip_start_ms"], 2000)
        self.assertEqual(media_payload["clip_end_ms"], 6000)
        self.assertTrue(str(media_payload["resolved_source_url"]).startswith("file:"))
        self.assertEqual(media_payload["preview_url"], "")

    def test_content_fullscreen_bridge_forwards_video_trim_requests(self) -> None:
        node_id = self._add_video_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))

        replace_result = bridge.request_trim_video_clip_replace(
            {
                "position_ms": 3400,
                "playing": True,
                "muted": True,
                "volume": 0.25,
                "playback_rate": 1.5,
                "loop": True,
                "fit_mode": "cover",
                "timeline_bookmarks": [
                    {"id": "in", "label": "In", "position_ms": 2500},
                ],
                "clip_enabled": True,
                "clip_start_ms": 2500,
                "clip_end_ms": 5500,
            }
        )
        copy_result = bridge.request_trim_video_clip_copy(
            {
                "clip_enabled": True,
                "clip_start_ms": 2500,
                "clip_end_ms": 5500,
                "timeline_bookmarks": [
                    {"id": "out", "label": "Out", "position_ms": 5000},
                ],
            }
        )

        self.assertEqual(replace_result["request_id"], "fullscreen-replace")
        self.assertEqual(copy_result["created_node_id"], "fullscreen-copy")
        self.assertEqual(self.video_trim_presenter.calls[0][0], "replace")
        self.assertEqual(
            self.video_trim_presenter.calls[0][1][0:3],
            (node_id, 2500, 5500),
        )
        replace_state = self.video_trim_presenter.calls[0][1][3]
        self.assertEqual(replace_state["position_ms"], 3400)
        self.assertEqual(replace_state["timeline_bookmarks"], [{"id": "in", "label": "In", "position_ms": 2500}])
        self.assertEqual(self.video_trim_presenter.calls[1][0], "copy")
        self.assertEqual(
            self.video_trim_presenter.calls[1][1][0:5],
            (node_id, 2500, 5500, 0.0, 0.0),
        )
        copy_state = self.video_trim_presenter.calls[1][1][5]
        self.assertEqual(copy_state["timeline_bookmarks"], [{"id": "out", "label": "Out", "position_ms": 5000}])

        bridge._trim_video_clip_replace = None
        bridge._trim_video_clip_copy = None
        for unavailable in (
            bridge.request_trim_video_clip_replace({"clip_start_ms": 1, "clip_end_ms": 2}),
            bridge.request_trim_video_clip_copy({"clip_start_ms": 1, "clip_end_ms": 2}),
        ):
            self.assertEqual(unavailable["error"]["code"], "mutation_unavailable")
            self.assertEqual(
                unavailable["error"]["message"],
                "Media Panel actions are unavailable.",
            )

        bridge.request_close()
        unavailable = bridge.request_trim_video_clip_copy({})
        self.assertEqual(
            unavailable["error"]["message"],
            "No fullscreen Media Panel in video mode is active.",
        )

    def test_content_fullscreen_bridge_opens_managed_video_media_source(self) -> None:
        project_path = self.temp_path / "fullscreen-managed-video.cxproj"
        self.project_path = str(project_path)
        workspace_id = self.workspace_id
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)

        staging_root = self._ensure_project_staging_root()
        store = self._project_artifact_store()
        paths = store.node_artifact_paths(
            artifact_id="managed_video",
            workspace_id=workspace_id,
            node_id=node_id,
            node_title="Video Panel",
            node_type="Video Panel",
            io_dir="in",
            subdirectory="media",
            filename="managed-video.mp4",
        )
        staged_path = staging_root.joinpath(*Path(paths.staged_relative_path).parts)
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(b"managed video fixture")
        store.register_staged_entry("managed_video", relative_path=paths.staged_relative_path, extra=paths.metadata)
        self.model.project.metadata = {
            **dict(self.model.project.metadata),
            "artifact_store": store.metadata,
        }
        self.scene.set_node_properties(
            node_id,
            {
                "source": store.staged_ref("managed_video"),
                "fit_mode": "contain",
            },
        )
        self.app.processEvents()

        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        media_payload = bridge.media_payload
        self.assertEqual(media_payload["media_kind"], "video")
        self.assertEqual(Path(QUrl(media_payload["resolved_source_url"]).toLocalFile()), staged_path)
        self.assertEqual(media_payload["source_ref"], store.staged_ref("managed_video"))

    def test_content_fullscreen_bridge_accepts_video_remote_source(self) -> None:
        node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=120.0, y=80.0
        )
        self.scene.set_exposed_port(node_id, "source", False)
        self.scene.set_node_properties(
            node_id,
            {
                "source": "https://example.com/video.mp4",
                "fit_mode": "contain",
            },
        )
        self.app.processEvents()
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))
        self.assertTrue(bridge.open)
        self.assertEqual(bridge.content_kind, "media")
        self.assertEqual(bridge.media_payload["media_kind"], "video")
        self.assertEqual(
            bridge.media_payload["resolved_source_url"],
            "https://example.com/video.mp4",
        )

    def test_content_fullscreen_bridge_hands_off_video_state_and_persists_close_state(self) -> None:
        node_id = self._add_video_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        close_events: list[tuple[str, dict]] = []
        bridge.video_fullscreen_closed.connect(lambda closed_node_id, state: close_events.append((closed_node_id, state)))

        self.assertTrue(
            bridge.request_open_node_with_state(
                node_id,
                {
                    "position_ms": 9000,
                    "playing": True,
                    "muted": False,
                    "volume": 0.75,
                    "playback_rate": 1.5,
                    "loop": False,
                    "fit_mode": "contain",
                    "timeline_bookmarks": [
                        {"id": "intro", "label": "Intro", "position_ms": 1000},
                    ],
                    "clip_enabled": True,
                    "clip_start_ms": 1000,
                    "clip_end_ms": 8000,
                },
            )
        )

        media_payload = bridge.media_payload
        self.assertEqual(media_payload["transient_state"]["position_ms"], 9000)
        self.assertTrue(media_payload["transient_state"]["playing"])
        self.assertEqual(media_payload["transient_state"]["volume"], 0.75)
        self.assertEqual(media_payload["transient_state"]["playback_rate"], 1.5)
        self.assertEqual(
            media_payload["transient_state"]["timeline_bookmarks"],
            [{"id": "intro", "label": "Intro", "position_ms": 1000}],
        )
        self.assertTrue(media_payload["transient_state"]["clip_enabled"])
        self.assertEqual(media_payload["transient_state"]["clip_start_ms"], 1000)
        self.assertEqual(media_payload["transient_state"]["clip_end_ms"], 8000)

        self.assertTrue(
            bridge.request_close_with_state(
                {
                    "position_ms": 12345,
                    "playing": True,
                    "muted": True,
                    "volume": 0.2,
                    "playback_rate": 2.0,
                    "loop": True,
                    "fit_mode": "cover",
                    "timeline_bookmarks": [
                        {"id": "clip-start", "label": "Clip start", "position_ms": 12000},
                    ],
                    "clip_enabled": True,
                    "clip_start_ms": 12000,
                    "clip_end_ms": 15000,
                }
            )
        )

        self.assertFalse(bridge.open)
        self.assertEqual(bridge.media_payload, {})
        workspace = self.model.project.workspaces[workspace_id]
        node = workspace.nodes[node_id]
        self.assertEqual(node.properties["position_ms"], 12345)
        self.assertEqual(node.properties["playback_rate"], 2.0)
        self.assertEqual(node.properties["volume"], 0.2)
        self.assertTrue(node.properties["muted"])
        self.assertTrue(node.properties["loop"])
        self.assertEqual(node.properties["fit_mode"], "cover")
        self.assertEqual(
            node.properties["timeline_bookmarks"],
            [{"id": "clip-start", "label": "Clip start", "position_ms": 12000}],
        )
        self.assertTrue(node.properties["clip_enabled"])
        self.assertEqual(node.properties["clip_start_ms"], 12000)
        self.assertEqual(node.properties["clip_end_ms"], 15000)
        self.assertEqual(close_events, [(node_id, {
            "position_ms": 12345,
            "playing": True,
            "muted": True,
            "volume": 0.2,
            "playback_rate": 2.0,
            "loop": True,
            "fit_mode": "cover",
            "timeline_bookmarks": [{"id": "clip-start", "label": "Clip start", "position_ms": 12000}],
            "clip_enabled": True,
            "clip_start_ms": 12000,
            "clip_end_ms": 15000,
        })])

    def test_content_fullscreen_bridge_opens_viewer_with_session_metadata(self) -> None:
        node_id = self._add_viewer_node()
        self.app.processEvents()

        bridge = self._bridge()
        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.content_kind, "viewer")
        self.assertEqual(bridge.media_payload, {})
        viewer_payload = bridge.viewer_payload
        self.assertEqual(viewer_payload["workspace_id"], self.workspace_id)
        self.assertEqual(viewer_payload["node_id"], node_id)
        self.assertEqual(viewer_payload["type_id"], ENGINEERING_VIEWER_NODE_TYPE_ID)
        self.assertEqual(viewer_payload["surface_spec"]["component_key"], "viewer")
        self.assertTrue(viewer_payload["surface_spec"]["native_overlay"]["required"])
        self.assertIn("viewer.pluginGesture", viewer_payload["surface_spec"]["input_capabilities"]["plugin_gestures"])
        self.assertEqual(viewer_payload["phase"], "closed")
        self.assertIsInstance(viewer_payload["session_state"], dict)
        self.assertIsInstance(viewer_payload["viewer_surface"], dict)



class ContentFullscreenBridgeContentTests(_ContentFullscreenDirectTestCase):
    def test_content_fullscreen_bridge_opens_python_script_editor_and_retargets_model(self) -> None:
        node_id = self.scene.add_node_from_type(
            "core.python_script", x=120.0, y=80.0
        )
        workspace_id = self.workspace_id
        workspace = self.model.project.workspaces[workspace_id]
        workspace.nodes[node_id].properties["script"] = PYTHON_SCRIPT_DEFAULT_SOURCE
        self.app.processEvents()

        bridge = self._bridge()
        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "script_editor")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})
        self.assertEqual(bridge.web_editor_payload, {})
        self.assertEqual(bridge.tabular_payload, {})
        self.assertEqual(self.script_editor.current_node_id, node_id)
        self.assertEqual(self.script_editor.script_text, PYTHON_SCRIPT_DEFAULT_SOURCE)

class ContentFullscreenMountedIntegrationTests(MainWindowShellTestBase):
    def test_collapsed_script_toolbar_keeps_working_surface_actions(self) -> None:
        scene = self.window.scene
        node_id = scene.add_node_from_type("core.python_script", x=240.0, y=140.0)
        canvas = self._graph_canvas_item()
        workspace = self.window.model.active_workspace
        scene.select_node(node_id, False)

        def toolbar_button(action_id: str):
            name = "graphNodeFloatingToolbarAction_" + action_id
            wait_for_condition_or_raise(
                lambda: (item := self._find_qml_item(name)) is not None
                and item.isVisible()
                and self._find_qml_item("graphNodeFloatingToolbar").property("opacity") >= 0.99,
                app=self.app,
            )
            return self._find_qml_item(name)

        def click_action(action_id: str) -> None:
            button = toolbar_button(action_id)
            # Wait for Row layout after the toolbar is recreated.
            wait_for_condition_or_raise(
                lambda: self._find_qml_item("graphNodeFloatingToolbarAction_remove_node")
                .mapToScene(QPointF()).x() > button.mapToScene(QPointF()).x() + button.width(),
                app=self.app,
            )
            self.assertTrue(button.isEnabled(), action_id)
            clicks = []
            button.clicked.connect(lambda: clicks.append(action_id))
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
            QTest.mouseMove(button.window(), point.toPoint())
            self.app.processEvents()
            QTest.mouseClick(button.window(), Qt.MouseButton.LeftButton, pos=point.toPoint())
            self.app.processEvents()
            self.assertEqual(clicks, [action_id], str(point))

        def action_ids() -> list[str]:
            host = canvas.hostForNodeId(node_id)
            return [action["id"] for action in host.property("availableActions").toVariant()]

        toolbar_button("fullscreen")
        self.assertTrue(canvas.hostForNodeId(node_id).frameNodeInView())
        canvas.property("viewBridge").set_zoom(1.0)
        self.app.processEvents()
        expanded_actions = action_ids()
        click_action("toggle_node_collapsed")
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.assertEqual(action_ids(), expanded_actions)
        loader = canvas.hostForNodeId(node_id).findChild(QObject, "graphNodeSurfaceLoader")
        self.assertTrue(loader.property("surfaceLoaded"))
        self.assertFalse(loader.property("visible"))
        self.assertEqual(loader.property("embeddedInteractiveRects").toVariant(), [])

        # Release the surface, then select the already-collapsed node again.
        scene.clear_selection()
        QTest.mouseMove(self.window.quick_widget, canvas.mapToScene(QPointF(20, 20)).toPoint())
        wait_for_condition_or_raise(lambda: not loader.property("surfaceLoaded"), app=self.app)
        scene.select_node(node_id, False)
        toolbar_button("fullscreen")
        self.assertEqual(action_ids(), expanded_actions)
        click_action("fullscreen")
        self.assertTrue(self.window.content_fullscreen_bridge.open, self.window.content_fullscreen_bridge.last_error)
        self.assertEqual(self.window.content_fullscreen_bridge.node_id, node_id)
        self.assertEqual(self.window.script_editor.current_node_id, node_id)
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.window.content_fullscreen_bridge.request_close()
        click_action("toggle_node_collapsed")
        self.assertFalse(workspace.nodes[node_id].collapsed)
        self.assertEqual(action_ids(), expanded_actions)

    def test_content_fullscreen_script_editor_attaches_syntax_highlighter(self) -> None:
        node_id = self.window.scene.add_node_from_type(
            "core.python_script", x=240.0, y=140.0
        )
        existing_documents = set(self.window.script_highlighter._highlighters)

        self.assertTrue(self.window.content_fullscreen_bridge.request_open_node(node_id))
        self.app.processEvents()

        new_documents = set(self.window.script_highlighter._highlighters) - existing_documents
        self.assertEqual(len(new_documents), 1)
        document, highlighter = self.window.script_highlighter._highlighters[
            new_documents.pop()
        ]
        highlighter.rehighlight()
        colors = {
            color_range.format.foreground().color().name()
            for block_number in range(document.blockCount())
            for color_range in document.findBlockByNumber(block_number).layout().formats()
        }
        self.assertIn("#68a5ff", colors)

    def test_content_fullscreen_script_editor_tab_and_history_stay_local(self) -> None:
        node_id = self.window.scene.add_node_from_type(
            "core.python_script", x=240.0, y=140.0
        )
        self.assertTrue(self.window.content_fullscreen_bridge.request_open_node(node_id))
        self.app.processEvents()
        editor = next(
            item
            for item in self._qml_root_object().findChildren(QObject, "scriptEditorArea")
            if item.isVisible()
        )
        self.window.quick_widget.setFocus()
        editor.setProperty("text", "pass")
        editor.setProperty("cursorPosition", 4)
        editor.forceActiveFocus()

        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertEqual(editor.property("text"), "pass    ")
        self.assertTrue(editor.property("activeFocus"))

        QTest.keyClick(
            self.window.quick_widget,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier,
        )
        self.app.processEvents()
        self.assertEqual(editor.property("text"), "pass")
        QTest.keyClick(
            self.window.quick_widget,
            Qt.Key.Key_Y,
            Qt.KeyboardModifier.ControlModifier,
        )
        self.app.processEvents()
        self.assertEqual(editor.property("text"), "pass    ")

class ContentFullscreenBridgeRemainingTests(_ContentFullscreenDirectTestCase):
    def test_content_fullscreen_script_reopen_preserves_same_node_dirty_draft(
        self,
    ) -> None:
        node_id = self.scene.add_node_from_type(
            "core.python_script",
            x=120.0,
            y=80.0,
        )
        self.scene.focus_node(node_id)
        self.app.processEvents()
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.script_editor.set_node(node)
        draft = PYTHON_SCRIPT_DEFAULT_SOURCE.replace("payload}", "payload + 1}")
        self.script_editor.set_script_text(draft)

        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertEqual(self.script_editor.current_node_id, node_id)
        self.assertEqual(self.script_editor.script_text, draft)
        self.assertTrue(self.script_editor.dirty)

    def test_content_fullscreen_bridge_opens_excalidraw_board_as_web_editor_payload(self) -> None:
        node_id, state, preview_ref = self._add_excalidraw_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "web_editor")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})
        self.assertIsInstance(bridge.web_surface_bridge, WebSurfaceBridge)
        self.assertEqual(bridge.web_surface_bridge.load_state(), state)

        payload = bridge.web_editor_payload
        self.assertEqual(payload["workspace_id"], workspace_id)
        self.assertEqual(payload["node_id"], node_id)
        self.assertEqual(payload["type_id"], EXCALIDRAW_BOARD_TYPE_ID)
        self.assertEqual(payload["title"], "Excalidraw Board")
        self.assertEqual(payload["surface_family"], "web")
        self.assertEqual(payload["surface_variant"], "excalidraw_board")
        self.assertEqual(payload["surface_spec"]["component_key"], "web_excalidraw_board")
        self.assertTrue(payload["surface_spec"]["input_capabilities"]["pressure"])
        self.assertEqual(payload["excalidraw_state"], state)
        self.assertEqual(payload["excalidraw_preview_ref"], preview_ref)
        self.assertTrue(str(payload["asset_url"]).startswith("file:"))
        self.assertTrue(Path(str(payload["asset_path"])).is_file())
        self.assertIn("webengine_available", payload)

    def test_content_fullscreen_bridge_opens_web_page_payload_without_privileged_bridge(self) -> None:
        node_id = self._add_web_page_node(
            start_location="https://example.com/docs",
            browser_state={"zoom_factor": 1.25},
        )
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "web_page")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})
        self.assertEqual(bridge.web_editor_payload, {})
        self.assertEqual(bridge.tabular_payload, {})
        self.assertIsNone(bridge.web_surface_bridge)

        payload = bridge.web_page_payload
        self.assertEqual(payload["workspace_id"], workspace_id)
        self.assertEqual(payload["node_id"], node_id)
        self.assertEqual(payload["type_id"], WEB_PAGE_VIEWER_TYPE_ID)
        self.assertEqual(payload["content_kind"], "web_page")
        self.assertEqual(payload["surface_family"], "web")
        self.assertEqual(payload["surface_variant"], "page_viewer")
        self.assertEqual(payload["surface_spec"]["component_key"], "web_page")
        self.assertEqual(payload["surface_spec"]["qml_component"], "../web/WebPageHost.qml")
        self.assertEqual(payload["surface_spec"]["fullscreen"]["content_kind"], "web_page")
        self.assertEqual(payload["navigation_decision"]["target_url"], "https://example.com/docs")
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertFalse(payload["navigation_decision"]["qwebchannel_allowed"])
        self.assertFalse(payload["qwebchannel_allowed"])
        self.assertNotIn("allowed_origins", payload)
        self.assertNotIn("access_profile", payload)
        self.assertIn("webengine_available", payload)
        self.assertNotIn("excalidraw", json.dumps(_payload_keys(payload)).lower())

    def test_content_fullscreen_bridge_opens_jupyter_live_borrow_shell_only(self) -> None:
        node_id = self._add_jupyter_node(
            notebook_ref="saved://notebook-local",
            server_state={
                "zoom": 1.25,
                "token": "super-secret",
                "url": "http://127.0.0.1:50101/notebooks/x.ipynb",
            },
        )
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "jupyter_notebook")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})
        self.assertEqual(bridge.web_editor_payload, {})
        self.assertEqual(bridge.web_page_payload, {})
        self.assertEqual(bridge.tabular_payload, {})
        self.assertIsNone(bridge.web_surface_bridge)

        serialized_bridge_payloads = json.dumps(
            {
                "media": bridge.media_payload,
                "viewer": bridge.viewer_payload,
                "web_editor": bridge.web_editor_payload,
                "web_page": bridge.web_page_payload,
                "tabular": bridge.tabular_payload,
            },
            sort_keys=True,
        ).lower()
        self.assertNotIn("super-secret", serialized_bridge_payloads)
        self.assertNotIn("127.0.0.1", serialized_bridge_payloads)
        self.assertNotIn("excalidraw", json.dumps(_payload_keys(bridge.web_page_payload)).lower())

    def test_content_fullscreen_bridge_persists_safe_web_page_browser_state(self) -> None:
        node_id = self._add_web_page_node(
            start_location="https://example.com/docs",
            browser_state={"zoom_factor": 1.25},
        )
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        self.assertTrue(
            bridge.save_web_page_browser_state(
                {
                    "current_url": "https://example.com/current",
                    "zoom_factor": 2.75,
                    "page_title": "  Example Docs  ",
                    "cookies": "must not persist",
                    "local_storage": {"must": "not persist"},
                    "page_content": "<html>must not persist</html>",
                }
            )
        )

        workspace = self.model.project.workspaces[workspace_id]
        self.assertEqual(
            workspace.nodes[node_id].properties["browser_state"],
            {
                "current_url": "https://example.com/current",
                "zoom_factor": 2.75,
                "page_title": "Example Docs",
            },
        )
        payload = bridge.web_page_payload
        self.assertEqual(payload["current_location"], "https://example.com/current")
        self.assertEqual(payload["browser_state"]["current_url"], "https://example.com/current")
        self.assertEqual(payload["navigation_decision"]["target_url"], "https://example.com/current")
        self.assertNotIn("cookies", json.dumps(payload["browser_state"], sort_keys=True).lower())
        self.assertNotIn("local_storage", json.dumps(payload["browser_state"], sort_keys=True).lower())
        self.assertNotIn("page_content", json.dumps(payload["browser_state"], sort_keys=True).lower())

    def test_content_fullscreen_bridge_skips_web_page_browser_state_when_disabled(self) -> None:
        node_id = self._add_web_page_node(
            start_location="https://example.com/docs",
            persist_browser_state=False,
            browser_state={
                "current_url": "https://example.com/original",
                "zoom_factor": 1.25,
            },
        )
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        self.assertFalse(
            bridge.save_web_page_browser_state(
                {
                    "current_url": "https://example.com/current",
                    "zoom_factor": 2.75,
                }
            )
        )

        workspace = self.model.project.workspaces[workspace_id]
        self.assertEqual(workspace.nodes[node_id].properties["browser_state"], {})
        payload = bridge.web_page_payload
        self.assertFalse(payload["persist_browser_state"])
        self.assertEqual(payload["browser_state"], {})
        self.assertEqual(payload["current_location"], "https://example.com/docs")

    def test_content_fullscreen_bridge_persists_offline_html_browser_state_as_file_url(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "web_page_viewer" / "index.html"
        node_id = self._add_web_page_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        self.assertTrue(
            bridge.save_web_page_browser_state(
                {
                    "current_url": str(fixture),
                    "zoom_factor": 1.5,
                }
            )
        )

        workspace = self.model.project.workspaces[workspace_id]
        self.assertEqual(
            workspace.nodes[node_id].properties["browser_state"],
            {
                "current_url": fixture.resolve().as_uri(),
                "zoom_factor": 1.5,
            },
        )
        payload = bridge.web_page_payload
        self.assertEqual(payload["current_location"], fixture.resolve().as_uri())
        self.assertTrue(payload["navigation_decision"]["allowed"])
        self.assertEqual(payload["navigation_decision"]["origin"], "file://")

    def test_content_fullscreen_bridge_keeps_invalid_web_page_visible_and_bridge_free(self) -> None:
        node_id = self._add_web_page_node(
            start_location="javascript:alert(1)",
        )
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.content_kind, "web_page")
        self.assertIsNone(bridge.web_surface_bridge)
        payload = bridge.web_page_payload
        self.assertFalse(payload["navigation_decision"]["allowed"])
        self.assertIn("Unsupported web navigation scheme", payload["navigation_decision"]["reason"])

    def test_content_fullscreen_bridge_opens_tabular_payload_as_windowed_preview(self) -> None:
        node_id, source = self._add_tabular_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.can_open_node(node_id))
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, node_id)
        self.assertEqual(bridge.workspace_id, workspace_id)
        self.assertEqual(bridge.content_kind, "tabular")
        self.assertEqual(bridge.media_payload, {})
        self.assertEqual(bridge.viewer_payload, {})
        self.assertEqual(bridge.web_editor_payload, {})

        payload = bridge.tabular_payload
        self.assertEqual(payload["workspace_id"], workspace_id)
        self.assertEqual(payload["node_id"], node_id)
        self.assertEqual(payload["type_id"], TABULAR_DATA_INPUT_NODE_TYPE_ID)
        self.assertEqual(payload["surface_spec"]["fullscreen"]["content_kind"], "tabular")
        self.assertEqual(payload["surface_spec"]["fullscreen"]["action_kind"], "tabular")
        self.assertEqual(payload["preview_state"], "ready")
        self.assertEqual(payload[TABULAR_TABLE_VIEW_STATE_PROPERTY], {"version": 1, "column_widths": {}})
        self.assertEqual(payload[TABULAR_SELECTED_COLUMNS_PROPERTY], [])
        preview = payload["preview"]
        self.assertEqual(preview["preview_kind"], "table")
        self.assertEqual(preview["source"]["resolved_path"], str(source))
        self.assertEqual(preview["window"]["row_offset"], 0)
        self.assertEqual(preview["window"]["column_offset"], 0)
        self.assertEqual(len(preview["window"]["rows"]), 50)
        self.assertEqual(preview["window"]["columns"], ["station", "temp", "count"])
        self.assertTrue(preview["window"]["bounded"])
        self.assertFalse(preview["window"]["client_side_full_scan"])
        self.assertIn("request_tabular_window", json.dumps(preview["request_contracts"]))

        next_window = bridge.request_tabular_window(
            {"row_offset": 60, "row_limit": 5, "column_offset": 1, "column_limit": 1}
        )
        self.assertEqual(next_window["state"], "ready")
        self.assertEqual(next_window["window"]["row_offset"], 60)
        self.assertEqual(next_window["window"]["columns"], ["temp"])
        self.assertEqual(len(next_window["window"]["rows"]), 5)
        # Managed-cache reads return typed values (float64 via schema hint).
        self.assertEqual(next_window["window"]["rows"][0]["temp"], 26.0)

        document = self.serializer.to_document(self.model.project)
        self.assertNotIn("tabular_payload", json.dumps(_payload_keys(document)).lower())
        self.assertNotIn("request_tabular_window", json.dumps(document))

    def test_content_fullscreen_bridge_persists_tabular_table_view_state(self) -> None:
        node_id, _source = self._add_tabular_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        state = {
            "version": 1,
            "column_widths": {
                "table:station": 144,
                "array:2": 96,
                "bad": "wide",
            },
        }

        self.assertTrue(bridge.save_tabular_table_view_state(state))
        expected = {
            "version": 1,
            "column_widths": {
                "table:station": 144,
                "array:2": 96,
            },
        }
        self.assertEqual(bridge.tabular_payload[TABULAR_TABLE_VIEW_STATE_PROPERTY], expected)

        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties[TABULAR_TABLE_VIEW_STATE_PROPERTY], expected)

        document = self.serializer.to_document(self.model.project)
        serialized = json.dumps(document)
        self.assertIn(TABULAR_TABLE_VIEW_STATE_PROPERTY, serialized)
        self.assertNotIn("tabular_payload", json.dumps(_payload_keys(document)).lower())
        self.assertNotIn("request_tabular_window", serialized)

    def test_content_fullscreen_bridge_persists_tabular_selected_columns(self) -> None:
        node_id, _source = self._add_tabular_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(node_id))
        self.assertTrue(bridge.save_tabular_selected_columns(["station", "temp", "station", ""]))

        expected = ["station", "temp"]
        self.assertEqual(bridge.tabular_payload[TABULAR_SELECTED_COLUMNS_PROPERTY], expected)

        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties[TABULAR_SELECTED_COLUMNS_PROPERTY], expected)

        serialized = json.dumps(self.serializer.to_document(self.model.project))
        self.assertIn(TABULAR_SELECTED_COLUMNS_PROPERTY, serialized)

    def test_content_fullscreen_bridge_exports_visible_tabular_rows_after_query(self) -> None:
        node_id, _source = self._add_tabular_node()
        bridge = self._bridge()
        output = self.temp_path / "visible-filtered.csv"
        self.save_file_dialog_result = str(output)
        self.assertTrue(bridge.request_open_node(node_id))

        request = {
            "row_offset": 0,
            "row_limit": 3,
            "column_offset": 0,
            "column_limit": 3,
            "search": "S11",
            "sort": {"column": "count", "descending": True},
        }
        visible = bridge.request_tabular_window(request)
        self.assertEqual(visible["state"], "ready")
        self.assertEqual(visible["window"]["rows"][0]["station"], "S119")

        result = bridge.export_tabular_visible_rows(
            {
                "preview_kind": "table",
                "request": visible["window"]["request"],
            }
        )

        self.assertEqual(result, {"ok": True, "path": str(output), "error": ""})
        save_call = self.save_file_dialog_calls[0][1]
        self.assertEqual(save_call["title"], "Export Visible Rows")
        self.assertIn("Table Output", str(save_call["file_filter"]))
        self.assertEqual(
            output.read_text(encoding="utf-8").splitlines(),
            [
                "station,temp,count",
                "S119,31.9,119",
                "S118,31.8,118",
                "S117,31.7,117",
            ],
        )

        node_export = self.temp_path / "visible-inline.csv"
        self.save_file_dialog_result = str(node_export)
        node_result = bridge.export_tabular_visible_rows_for_node(
            node_id,
            {
                "preview_kind": "table",
                "request": visible["window"]["request"],
            },
        )
        self.assertEqual(node_result["path"], str(node_export))
        self.assertTrue(node_export.exists())

    def test_content_fullscreen_bridge_drops_stale_tabular_window_jobs(self) -> None:
        node_id, _source = self._add_tabular_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        fake_pool = _FakeTabularWorkerPool()
        bridge._tabular_preview_worker_pool = fake_pool  # noqa: SLF001
        emitted: list[tuple[str, dict]] = []
        bridge.tabular_window_ready.connect(lambda request_id, payload: emitted.append((request_id, payload)))
        properties = bridge._current_tabular_node_properties()  # noqa: SLF001
        self.assertIsInstance(properties, dict)

        first_id = bridge._schedule_tabular_window_job(  # noqa: SLF001
            properties,
            {"row_offset": 0, "row_limit": 5},
            kind="table",
        )
        second_id = bridge._schedule_tabular_window_job(  # noqa: SLF001
            properties,
            {"row_offset": 5, "row_limit": 5},
            kind="table",
        )
        pending = {
            item["request_id"]: (job_key, item)
            for job_key, item in bridge._pending_tabular_window_jobs.items()  # noqa: SLF001
        }
        pending[first_id][1]["result"].update({"state": "ready", "window": {"row_offset": 0}})
        bridge._on_tabular_preview_job_finished(pending[first_id][0], "")  # noqa: SLF001
        self.assertEqual(emitted, [])

        pending[second_id][1]["result"].update({"state": "ready", "window": {"row_offset": 5}})
        bridge._on_tabular_preview_job_finished(pending[second_id][0], "")  # noqa: SLF001
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], second_id)
        self.assertEqual(emitted[0][1]["request_id"], second_id)
        self.assertEqual(emitted[0][1]["window"]["row_offset"], 5)

    def test_content_fullscreen_bridge_clears_pending_tabular_jobs_on_close(self) -> None:
        node_id, _source = self._add_tabular_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        bridge._pending_tabular_payload_job = "payload-job"  # noqa: SLF001
        bridge._pending_tabular_payload_node_id = node_id  # noqa: SLF001
        bridge._latest_tabular_window_request_id = "request-1"  # noqa: SLF001
        bridge._pending_tabular_window_jobs["window-job"] = {  # noqa: SLF001
            "node_id": node_id,
            "request_id": "request-1",
            "result": {"state": "ready"},
        }

        bridge.request_close()
        bridge._on_tabular_preview_job_finished("payload-job", "")  # noqa: SLF001
        bridge._on_tabular_preview_job_finished("window-job", "")  # noqa: SLF001

        self.assertFalse(bridge.open)
        self.assertEqual(bridge._pending_tabular_payload_job, "")  # noqa: SLF001
        self.assertEqual(bridge._pending_tabular_payload_node_id, "")  # noqa: SLF001
        self.assertEqual(bridge._latest_tabular_window_request_id, "")  # noqa: SLF001
        self.assertEqual(bridge._pending_tabular_window_jobs, {})  # noqa: SLF001

    def test_content_fullscreen_bridge_reports_tabular_window_worker_errors(self) -> None:
        node_id, _source = self._add_tabular_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        bridge._tabular_preview_worker_pool = _FakeTabularWorkerPool()  # noqa: SLF001
        emitted: list[tuple[str, dict]] = []
        bridge.tabular_window_ready.connect(lambda request_id, payload: emitted.append((request_id, payload)))
        properties = bridge._current_tabular_node_properties()  # noqa: SLF001
        self.assertIsInstance(properties, dict)

        request_id = bridge._schedule_tabular_window_job(  # noqa: SLF001
            properties,
            {"row_offset": 0, "row_limit": 5},
            kind="table",
        )
        pending = {
            item["request_id"]: (job_key, item)
            for job_key, item in bridge._pending_tabular_window_jobs.items()  # noqa: SLF001
        }
        bridge._on_tabular_preview_job_finished(pending[request_id][0], "cache failed")  # noqa: SLF001

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], request_id)
        self.assertEqual(emitted[0][1]["state"], "error")
        self.assertIn("cache failed", emitted[0][1]["message"])

    def test_content_fullscreen_bridge_rejects_tabular_table_view_state_without_active_tabular_node(self) -> None:
        node_id = self._add_image_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()

        self.assertFalse(bridge.save_tabular_table_view_state({"column_widths": {"table:station": 144}}))
        self.assertFalse(bridge.save_tabular_selected_columns(["station"]))
        self.assertTrue(bridge.request_open_node(node_id))
        self.assertFalse(bridge.save_tabular_table_view_state({"column_widths": {"table:station": 144}}))
        self.assertFalse(bridge.save_tabular_selected_columns(["station"]))

        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertNotIn(TABULAR_TABLE_VIEW_STATE_PROPERTY, node.properties)
        self.assertNotIn(TABULAR_SELECTED_COLUMNS_PROPERTY, node.properties)

    def test_content_fullscreen_web_editor_save_updates_drawing_and_hides_previous_preview(self) -> None:
        node_id, _state, preview_ref = self._add_excalidraw_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(web_bridge, WebSurfaceBridge)

        updated_state = {
            "type": "excalidraw",
            "elements": [{"id": "text-1", "type": "text", "text": "saved"}],
            "appState": {"name": "Saved map", "theme": "light"},
            "files": {},
            "excalidraw_preview_ref": {"should_not": "persist"},
        }
        self.assertTrue(web_bridge.save_state(updated_state))
        self.app.processEvents()

        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], updated_state)
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["status"], "updating")
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["uri"], preview_ref["uri"])
        self.assertEqual(bridge.web_surface_bridge.load_state(), updated_state)

    def test_content_fullscreen_web_editor_save_uses_project_artifact_callbacks(self) -> None:
        project_path = self.temp_path / "fullscreen-artifact-board.cxproj"
        self.project_path = str(project_path)
        node_id, _state, _preview_ref = self._add_excalidraw_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(web_bridge, WebSurfaceBridge)

        image_payload = b"\x89PNG\r\n\x1a\nfullscreen-artifact-image"
        image_hash = hashlib.sha256(image_payload).hexdigest()
        updated_state = {
            "type": "excalidraw",
            "elements": [],
            "appState": {"name": "Artifact save"},
            "files": {
                "file-1": {
                    "mimeType": "image/png",
                    "dataURL": _data_url("image/png", image_payload),
                    "created": 10,
                    "lastRetrieved": 20,
                    "name": "managed.png",
                }
            },
        }

        self.assertTrue(web_bridge.save_state(updated_state))
        self.app.processEvents()

        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        saved_file = node.properties[EXCALIDRAW_STATE_PROPERTY]["files"]["file-1"]
        self.assertNotIn("dataURL", saved_file)
        self.assertTrue(saved_file["artifact_ref"].startswith("temp://"))
        self.assertEqual(saved_file["sha256"], image_hash)
        self.assertIn("artifact_store", self.model.project.metadata)

        store = self._project_artifact_store()
        staged_path = store.resolve_staged_path(saved_file["artifact_ref"])
        self.assertIsNotNone(staged_path)
        self.assertEqual(staged_path.read_bytes(), image_payload)
        hydrated = web_bridge.asset_request({"asset_id": "file-1"})
        self.assertTrue(hydrated["ok"])
        self.assertEqual(hydrated["sha256"], image_hash)

    def test_content_fullscreen_web_editor_close_export_persists_preview_ref(self) -> None:
        project_path = self.temp_path / "fullscreen-preview-board.cxproj"
        self.project_path = str(project_path)
        node_id, _state, _preview_ref = self._add_excalidraw_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(web_bridge, WebSurfaceBridge)
        before_revision = self.model.project.project_document_revision
        self.project_metadata_events.clear()

        preview_payload = png_bytes()
        preview_hash = hashlib.sha256(preview_payload).hexdigest()
        project = self.model.project
        replace_metadata_impl = ProjectData.replace_metadata
        with (
            mock.patch.object(
                ProjectData,
                "replace_metadata",
                autospec=True,
                side_effect=replace_metadata_impl,
            ) as replace_metadata,
            mock.patch.object(self.serializer, "save") as save_project,
        ):
            web_bridge.snapshot_status({"revision": 0, "state": "updating", "attempt": "test"})
            result = web_bridge.commit_snapshot(
                {
                    "revision": 0, "attempt": "test",
                    "dataURL": _data_url("image/png", preview_payload),
                    "width": 640,
                    "height": 360,
                    "name": "fullscreen-preview.png",
                }
            )
            replace_metadata.assert_called_once()
            save_project.assert_not_called()

        self.assertTrue(result["ok"])
        web_bridge.finish_close(result)
        self.app.processEvents()

        self.assertFalse(bridge.open)
        self.assertEqual(
            self.model.project.project_document_revision,
            before_revision + 1,
        )
        self.assertEqual(self.project_metadata_events, [before_revision + 1])
        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        preview_ref = node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]
        self.assertEqual(preview_ref["artifact_ref"], result["preview_ref"])
        self.assertEqual(preview_ref["mime_type"], "image/png")
        self.assertEqual(preview_ref["width"], 640)
        self.assertEqual(preview_ref["height"], 360)
        self.assertEqual(preview_ref["size"], len(preview_payload))
        self.assertEqual(preview_ref["sha256"], preview_hash)
        self.assertNotIn("data_url", json.dumps(preview_ref))

        store = self._project_artifact_store()
        preview_path = store.resolve_staged_path(preview_ref["artifact_ref"])
        self.assertIsNotNone(preview_path)
        self.assertEqual(preview_path.read_bytes(), preview_payload)

    def test_content_fullscreen_web_editor_preview_staging_is_scoped_per_board(self) -> None:
        project_path = self.temp_path / "fullscreen-two-preview-boards.cxproj"
        self.project_path = str(project_path)
        first_node_id, _first_state, _first_preview_ref = self._add_excalidraw_node()
        second_node_id, _second_state, _second_preview_ref = self._add_excalidraw_node()
        self.scene.set_node_title(first_node_id, "First Board")
        self.scene.set_node_title(second_node_id, "Second Board")
        workspace_id = self.workspace_id
        workspace = self.model.project.workspaces[workspace_id]
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(first_node_id))
        first_web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(first_web_bridge, WebSurfaceBridge)
        first_payload = png_bytes(color="#ff0000")
        first_web_bridge.snapshot_status({"revision": 0, "state": "updating", "attempt": "test"})
        first_result = first_web_bridge.commit_snapshot(
            {
                "revision": 0, "attempt": "test",
                    "dataURL": _data_url("image/png", first_payload),
                "width": 640,
                "height": 360,
                "name": "first-fullscreen-preview.png",
            }
        )
        self.assertTrue(first_result["ok"])
        first_web_bridge.finish_close(first_result)
        self.app.processEvents()

        self.assertTrue(bridge.request_open_node(second_node_id))
        second_web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(second_web_bridge, WebSurfaceBridge)
        second_payload = png_bytes(color="#00ff00")
        second_web_bridge.snapshot_status({"revision": 0, "state": "updating", "attempt": "test"})
        second_result = second_web_bridge.commit_snapshot(
            {
                "revision": 0, "attempt": "test",
                    "dataURL": _data_url("image/png", second_payload),
                "width": 640,
                "height": 360,
                "name": "second-fullscreen-preview.png",
            }
        )
        self.assertTrue(second_result["ok"])
        second_web_bridge.finish_close(second_result)
        self.app.processEvents()

        first_node = self.model.project.workspaces[workspace_id].nodes[first_node_id]
        second_node = self.model.project.workspaces[workspace_id].nodes[second_node_id]
        first_ref = first_node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]
        second_ref = second_node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]
        self.assertNotEqual(first_ref["artifact_ref"], second_ref["artifact_ref"])
        node_type = self.registry.get_spec(EXCALIDRAW_BOARD_TYPE_ID).display_name
        self.assertEqual(
            self.artifact_factory_calls,
            [
                (
                    workspace_id,
                    workspace.name,
                    first_node_id,
                    "First Board",
                    node_type,
                ),
                (
                    workspace_id,
                    workspace.name,
                    second_node_id,
                    "Second Board",
                    node_type,
                ),
            ],
        )

        store = self._project_artifact_store()
        first_path = store.resolve_staged_path(first_ref["artifact_ref"])
        second_path = store.resolve_staged_path(second_ref["artifact_ref"])
        self.assertIsNotNone(first_path)
        self.assertIsNotNone(second_path)
        self.assertEqual(first_path.read_bytes(), first_payload)
        self.assertEqual(second_path.read_bytes(), second_payload)

    def test_web_snapshot_storage_failure_preserves_drawing_and_hidden_last_good_png(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.snapshot_status({"revision": 0, "state": "updating", "attempt": "first"})
        first = web.commit_snapshot({"revision": 0, "attempt": "first", "data_url": _data_url("image/png", png_bytes())})
        self.assertTrue(first["ok"])
        store = self._project_artifact_store()
        old_path = store.resolve_staged_path(first["artifact_ref"])
        old_bytes = old_path.read_bytes()
        current = {"elements": [{"id": "new-shape", "type": "rectangle"}], "appState": {}, "files": {}}
        web.note_revision(1)
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["status"], "updating")
        self.assertTrue(web.save_scene({"revision": 1, "scene_state": current}))
        web.snapshot_status({"revision": 1, "state": "closing", "attempt": "failed"})
        with mock.patch.object(web._artifact_service, "stage_preview", side_effect=WebSurfaceArtifactError("Disk full")):
            failed = web.commit_snapshot({"revision": 1, "attempt": "failed", "data_url": _data_url("image/png", png_bytes(color="#ff0000"))})
        self.assertFalse(failed["ok"])
        self.assertFalse(web.finish_close(failed))
        self.assertTrue(bridge.open)
        self.assertEqual(web.last_error, "Disk full")
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], current)
        hidden = node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]
        self.assertEqual(hidden["artifact_ref"], first["artifact_ref"])
        self.assertEqual(hidden["status"], "error")
        self.assertEqual(old_path.read_bytes(), old_bytes)
        web.snapshot_status({"revision": 1, "state": "closing", "attempt": "retry"})
        retried = web.commit_snapshot({"revision": 1, "attempt": "retry", "data_url": _data_url("image/png", png_bytes(color="#ff0000"))})
        self.assertTrue(web.finish_close(retried))
        self.assertFalse(bridge.open)
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["scene_sha256"], board_scene_digest(current))

    def test_web_snapshot_rejects_stale_scene_and_late_attempt_without_storage(self) -> None:
        node_id, initial, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.snapshot_status({"revision": 0, "state": "updating", "attempt": "old"})
        web.note_revision(1)
        current = {"elements": [{"id": "new", "type": "rectangle"}]}
        self.assertTrue(web.save_scene({"revision": 1, "scene_state": current}))
        with mock.patch.object(web._artifact_service, "stage_preview") as stage:
            self.assertFalse(web.save_scene({"revision": 0, "scene_state": initial}))
            self.assertTrue(web.commit_snapshot({"revision": 0, "attempt": "old"})["stale"])
            web.snapshot_status({"revision": 1, "state": "updating", "attempt": "retry"})
            self.assertTrue(web.commit_snapshot({"revision": 1, "attempt": "old"})["stale"])
            stage.assert_not_called()
        self.assertEqual(web.load_state(), current)
        self.assertTrue(bridge.open)

    def test_web_snapshot_close_request_requires_saved_current_revision(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        requested = []
        web.close_requested.connect(lambda: requested.append(True))
        bridge.request_close()
        self.assertEqual(requested, [True])
        self.assertTrue(bridge.open)
        web.note_revision(1)
        web.snapshot_status({"revision": 1, "state": "closing", "attempt": "pending"})
        self.assertTrue(web.commit_snapshot({"revision": 1, "attempt": "pending"})["stale"])
        self.assertFalse(web.finish_close({"ok": True, "revision": 1}))
        self.assertTrue(bridge.open)

    def test_web_snapshot_meta_object_dispatch_runs_revision_gate_and_persistence(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        meta = web.metaObject()
        methods = [bytes(meta.method(index).name()).decode() for index in range(meta.methodCount())]
        self.assertEqual(methods.count("commit_snapshot"), 1)
        web.snapshot_status({"revision": 0, "state": "updating", "attempt": "qt"})
        result = QMetaObject.invokeMethod(
            web, "commit_snapshot", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariantMap"),
            Q_ARG("QVariant", {"revision": 0, "attempt": "qt", "data_url": _data_url("image/png", png_bytes())}),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(web.snapshot_state, "ready")
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["artifact_ref"], result["artifact_ref"])

    def test_web_editor_retarget_keeps_pending_scene_owner_until_explicit_close(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        other_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.note_revision(1)
        self.assertFalse(bridge.request_open_node(other_id))
        self.assertIs(bridge.web_surface_bridge, web)
        self.assertEqual(bridge.node_id, node_id)
        self.assertIn("Close this drawing editor", web.last_error)
        self.assertTrue(bridge.request_open_node(node_id))
        self.assertIs(bridge.web_surface_bridge, web)

    def test_web_editor_content_equivalent_scene_refresh_keeps_bridge(self) -> None:
        node_id, state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        state = copy.deepcopy(state)
        state.setdefault("appState", {})["scrollX"] = 999
        self.scene.set_node_property(node_id, EXCALIDRAW_STATE_PROPERTY, state)
        self.app.processEvents()
        self.assertIs(bridge.web_surface_bridge, web)

    def test_web_snapshot_empty_board_requires_no_renderer_or_artifact(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.note_revision(1)
        self.assertTrue(web.save_scene({"revision": 1, "scene_state": {"elements": []}}))
        web.snapshot_status({"revision": 1, "state": "closing", "attempt": "empty"})
        with mock.patch.object(web._artifact_service, "stage_preview") as stage:
            result = web.commit_snapshot({"revision": 1, "attempt": "empty", "empty": True})
            stage.assert_not_called()
        self.assertTrue(web.finish_close(result))
        self.assertFalse(bridge.open)
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["status"], "empty")
        self.assertNotIn("artifact_ref", node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY])

    def test_web_snapshot_digest_survives_artifact_promotion_and_editor_metadata(self) -> None:
        state = {"elements": [{"type": "image", "fileId": "f", "x": 12, "version": 1}], "files": {"f": {"sha256": "abc", "artifact_ref": "temp://img", "mimeType": "image/png", "lastRetrieved": 1}}, "appState": {"viewBackgroundColor": "#ffffff", "scrollX": 12}}
        saved = copy.deepcopy(state)
        saved["files"]["f"].update(artifact_ref="saved://renamed-img", lastRetrieved=1234, name="renamed.png")
        saved["elements"][0]["version"] = 2
        saved["appState"].update(scrollX=999, selectedElementIds={"image": True})
        self.assertEqual(board_scene_digest(state), board_scene_digest(saved))
        saved["elements"][0]["x"] = 13
        self.assertNotEqual(board_scene_digest(state), board_scene_digest(saved))

    def test_web_snapshot_save_ack_requires_actual_graph_property_commit(self) -> None:
        node_id, original, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.note_revision(1)
        changed = {"elements": [{"id": "new", "type": "rectangle"}]}
        with mock.patch.object(self.scene, "set_node_property", side_effect=RuntimeError("mutation rejected")):
            self.assertFalse(web.save_scene({"revision": 1, "scene_state": changed}))
            self.assertFalse(web.finish_without_preview({"revision": 1, "action": "close"}))
            self.assertFalse(web.finish_close({"ok": True, "revision": 1}))
        self.assertTrue(bridge.open)
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], original)
        self.assertTrue(web.save_scene({"revision": 1, "scene_state": changed}))
        self.assertTrue(web.finish_without_preview({"revision": 1, "action": "close"}))
        self.assertFalse(bridge.open)
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], changed)

    def test_web_snapshot_reference_commit_failure_rolls_back_artifact_replacement(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        web.snapshot_status({"revision": 0, "state": "updating", "attempt": "first"})
        first = web.commit_snapshot({"revision": 0, "attempt": "first", "data_url": _data_url("image/png", png_bytes())})
        self.assertTrue(first["ok"])
        store = self._project_artifact_store()
        old_path = store.resolve_staged_path(first["artifact_ref"])
        old_bytes = old_path.read_bytes()
        original_metadata = copy.deepcopy(store.metadata)
        web.snapshot_status({"revision": 0, "state": "updating", "attempt": "next"})
        with mock.patch.object(self.scene, "set_node_property", side_effect=RuntimeError("mutation rejected")):
            result = web.commit_snapshot({"revision": 0, "attempt": "next", "data_url": _data_url("image/png", png_bytes(color="#ff0000"))})
        self.assertFalse(result["ok"])
        self.assertEqual(store.metadata, original_metadata)
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertTrue(bridge.open)

    def test_retired_web_editor_cannot_write_to_or_close_new_owner(self) -> None:
        first_id, _state, _ref = self._add_excalidraw_node()
        second_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(first_id))
        old = bridge.web_surface_bridge
        bridge._complete_close()
        self.assertTrue(bridge.request_open_node(second_id))
        node = self.model.project.workspaces[self.workspace_id].nodes[second_id]
        before = copy.deepcopy(node.properties)
        old.snapshot_status({"revision": 0, "state": "error", "error": "Late first editor failure"})
        old.note_revision(99)
        self.assertFalse(old.save_scene({"revision": 0, "scene_state": {}}))
        self.assertFalse(old.commit_snapshot({"revision": 0, "attempt": "old"})["ok"])
        self.assertFalse(old.finish_without_preview({"revision": 0, "action": "close"}))
        old.close_ready.emit()
        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, second_id)
        self.assertEqual(node.properties, before)

    def test_unstarted_web_editor_can_close_but_started_draft_requires_ack(self) -> None:
        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        self.assertTrue(bridge.web_surface_bridge.recover_unstarted_editor("close"))
        self.assertFalse(bridge.open)
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        self.assertTrue(web.start_editor())
        web.note_revision(1)
        self.assertFalse(web.recover_unstarted_editor("close"))
        self.assertFalse(web.finish_without_preview({"revision": 1, "action": "reload"}))
        self.assertTrue(bridge.open)
        self.assertTrue(web.save_scene({"revision": 1, "scene_state": {"elements": []}}))
        self.assertTrue(web.finish_without_preview({"revision": 1, "action": "reload"}))
        self.assertTrue(bridge.open)
        self.assertIsNot(bridge.web_surface_bridge, web)
        self.assertFalse(web.start_editor())

    def test_interrupted_snapshot_session_restores_as_actionable_error(self) -> None:
        from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder

        node_id, _state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        bridge.web_surface_bridge.note_revision(1)
        restored = GraphModel(self.serializer.from_document(self.serializer.to_document(self.model.project)))
        nodes, *_rest = GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=restored, registry=self.registry, workspace_id=self.workspace_id,
            scope_path=(), graph_theme_bridge=None,
        )
        ref = next(node for node in nodes if node["node_id"] == node_id)["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY]
        self.assertEqual(ref["status"], "error")
        self.assertFalse(ref["current"])
        self.assertIn("interrupted", ref["error"])
        bridge._complete_close()
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["status"], "error")

    def test_malformed_board_documents_have_no_snapshot_identity(self) -> None:
        for state in ({"elements": None}, {"elements": 5}, {"elements": [None]}, {"files": []}, {"appState": []}, {"elements": [{"fileId": []}]}, {"elements": [{"fileId": {}}]}):
            with self.subTest(state=state):
                self.assertEqual(board_scene_digest(state), "")

    def test_web_editor_crash_recovery_keeps_saved_graph_drawing(self) -> None:
        node_id, original, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        self.assertTrue(web.start_editor())
        web.note_revision(1)
        self.assertFalse(web.recover_unstarted_editor("reload"))
        web.editor_stopped()
        self.assertTrue(web.recover_unstarted_editor("reload"))
        self.assertTrue(bridge.open)
        self.assertIsNot(bridge.web_surface_bridge, web)
        self.assertEqual(bridge.web_surface_bridge.load_state(), original)

    def test_web_editor_crash_recovers_received_draft_before_missing_later_revision(self) -> None:
        node_id, original, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        self.assertTrue(web.start_editor())
        received = {"elements": [{"id": "recoverable", "type": "rectangle"}]}
        web.note_revision(1)
        with mock.patch.object(self.scene, "set_node_property", side_effect=RuntimeError("mutation rejected")):
            self.assertFalse(web.save_scene({"revision": 1, "scene_state": received}))
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], original)
        web.note_revision(2)
        web.editor_stopped()
        self.assertIn("cannot be recovered", web.last_error)
        self.assertTrue(web.recover_unstarted_editor("reload"))
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], received)
        self.assertEqual(bridge.web_surface_bridge.load_state(), received)
        self.assertEqual(web._saved_revision, 1)

    def test_content_equivalent_promotion_keeps_snapshot_close_acknowledged(self) -> None:
        node_id, state, _ref = self._add_excalidraw_node()
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web = bridge.web_surface_bridge
        state = {"elements": [{"type": "image", "fileId": "f", "x": 10}], "files": {"f": {"artifact_ref": "temp://image", "sha256": "abc", "mimeType": "image/png"}}}
        self.assertTrue(web.save_state(state))
        web.snapshot_status({"revision": 1, "state": "updating", "attempt": "preview"})
        result = web.commit_snapshot({"revision": 1, "attempt": "preview", "data_url": _data_url("image/png", png_bytes())})
        self.assertTrue(result["ok"])
        promoted = copy.deepcopy(state)
        promoted["files"]["f"]["artifact_ref"] = "saved://renamed-image"
        self.scene.set_node_property(node_id, EXCALIDRAW_STATE_PROPERTY, promoted)
        self.assertIs(bridge.web_surface_bridge, web)
        self.assertTrue(web.finish_close(result))
        node = self.model.project.workspaces[self.workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], promoted)

    def test_content_fullscreen_web_editor_invalid_payload_stays_visible_and_non_mutating(self) -> None:
        node_id, state, preview_ref = self._add_excalidraw_node()
        workspace_id = self.workspace_id
        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))
        web_bridge = bridge.web_surface_bridge
        self.assertIsInstance(web_bridge, WebSurfaceBridge)

        self.assertFalse(web_bridge.save_state("{not-json"))
        self.app.processEvents()

        self.assertTrue(web_bridge.has_error)
        self.assertIn("valid JSON", web_bridge.last_error)
        self.assertTrue(bridge.open)
        node = self.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties[EXCALIDRAW_STATE_PROPERTY], state)
        self.assertEqual(node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY], preview_ref)

    def test_content_fullscreen_bridge_replaces_and_toggles_single_active_node(self) -> None:
        first_node_id = self._add_image_node(name="content-fullscreen-first.png")
        second_node_id = self._add_image_node(name="content-fullscreen-second.png")
        bridge = self._bridge()

        self.assertTrue(bridge.request_open_node(first_node_id))
        self.assertEqual(bridge.node_id, first_node_id)

        self.assertTrue(bridge.request_open_node(second_node_id))
        self.assertTrue(bridge.open)
        self.assertEqual(bridge.node_id, second_node_id)

        self.assertTrue(bridge.request_toggle_for_node(second_node_id))
        self.assertFalse(bridge.open)
        self.assertEqual(bridge.node_id, "")
        self.assertEqual(bridge.media_payload, {})

    def test_content_fullscreen_bridge_rejects_ineligible_nodes_and_clears_active_state(self) -> None:
        node_id = self._add_image_node()
        unsupported_node_id = self.scene.add_node_from_type(
            "core.constant", x=420.0, y=80.0
        )
        missing_source_node_id = self.scene.add_node_from_type(
            MEDIA_PANEL_TYPE_ID, x=620.0, y=80.0
        )
        self.app.processEvents()

        bridge = self._bridge()
        self.assertTrue(bridge.request_open_node(node_id))

        self.assertFalse(bridge.request_open_node(unsupported_node_id))
        self.assertFalse(bridge.open)
        self.assertIn("does not support", bridge.last_error)

        self.assertTrue(bridge.request_open_node(missing_source_node_id))
        self.assertTrue(bridge.open)
        self.assertEqual(bridge.media_payload["source_state"], "waiting")
        self.assertEqual(bridge.media_payload["resolved_source_url"], "")
