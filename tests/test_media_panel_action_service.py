# Purpose: Direct owner tests for Media Panel crop, capture, timestamp, trim, and staging.
# Map: feature_routes/media_image_video_pdf_refocus
# Tests: tests/test_media_panel_action_service.py
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QObject, QThread, QUrl
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QSignalSpy

from ea_node_editor.ui.shell import (
    media_panel_action_service as media_panel_action_service_module,
)
from ea_node_editor.ui.shell.media_panel_action_service import (
    MediaPanelActionService,
)
from ea_node_editor.ui.media_panel_source import MediaPanelSourceResolution
from ea_node_editor.ui.video_trim import VideoTrimResult
from tests.main_window_shell.base import MainWindowShellTestBase


class _StageRecorder:
    def __init__(self) -> None:
        self.result = "temp://staged"
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs) -> str:  # noqa: ANN003
        self.calls.append(dict(kwargs))
        return self.result


class _SceneMutationFake:
    def __init__(self, workspace) -> None:  # noqa: ANN001
        self.workspace = workspace
        self.raise_create = False
        self.empty_create = False
        self.link_result = "link-video"
        self.created_count = 0
        self.property_calls: list[tuple[str, dict[str, object]]] = []

    def set_node_properties(self, node_id: str, properties: dict[str, object]) -> None:
        self.property_calls.append((node_id, dict(properties)))
        self.workspace.nodes[node_id].properties.update(properties)

    def create_node_from_type(self, **kwargs) -> str:  # noqa: ANN003
        if self.raise_create:
            raise RuntimeError("create failed")
        if self.empty_create:
            return ""
        self.created_count += 1
        node_id = f"created-{self.created_count}"
        node = SimpleNamespace(
            node_id=node_id,
            type_id=str(kwargs["type_id"]),
            properties=dict(kwargs.get("property_overrides") or {}),
            exposed_ports=dict(kwargs.get("exposed_port_overrides") or {}),
            x=float(kwargs.get("x", 0.0)),
            y=float(kwargs.get("y", 0.0)),
            custom_width=kwargs.get("custom_width"),
            custom_height=kwargs.get("custom_height"),
            links=[],
        )
        self.workspace.nodes[node_id] = node
        after_create = kwargs.get("after_create")
        if callable(after_create) and not after_create(node, self):
            self.workspace.nodes.pop(node_id, None)
            return ""
        return node_id

    def upsert_node_link(
        self,
        node_id: str,
        _link_id: str,
        _kind: str,
        _label: str,
        target: str,
        subtitle: str,
    ) -> str:
        if self.link_result:
            self.workspace.nodes[node_id].links.append(
                SimpleNamespace(
                    link_id=self.link_result,
                    target_node_id=target,
                    subtitle=subtitle,
                )
            )
        return self.link_result


class MediaPanelActionServiceBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.parent = QObject()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.workspace = SimpleNamespace(
            workspace_id="workspace-media",
            nodes={},
            edges={},
        )
        self.project = SimpleNamespace(
            metadata={},
            workspaces={self.workspace.workspace_id: self.workspace},
        )
        self.model = SimpleNamespace(project=self.project)
        self.scene = _SceneMutationFake(self.workspace)
        self.stage = _StageRecorder()
        self.logs: list[tuple[str, str]] = []
        self.hints: list[tuple[str, int]] = []
        self.notifications: list[str] = []
        self.edit_controller = object()
        self.drop_controller = object()
        self.service = MediaPanelActionService(
            self.parent,
            scene_mutation=self.scene,  # type: ignore[arg-type]
            workspace_edit_controller=self.edit_controller,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.drop_controller,  # type: ignore[arg-type]
            model_provider=lambda: self.model,  # type: ignore[arg-type]
            active_workspace_provider=lambda: self.workspace,  # type: ignore[arg-type]
            project_provider=lambda: self.project,  # type: ignore[arg-type]
            stage_node_artifact_bytes=self.stage,
            run_state_provider=lambda: None,
            project_path_provider=lambda: None,
            append_console_log=lambda level, message: self.logs.append(
                (level, message)
            ),
            show_graph_hint=lambda message, timeout: self.hints.append(
                (message, timeout)
            ),
            update_notification_counters=lambda: self.notifications.append("updated"),
        )

    def tearDown(self) -> None:
        self.service.deleteLater()
        self.parent.deleteLater()
        self.temp_dir.cleanup()

    def _add_media_node(
        self,
        kind: str,
        *,
        exposed: bool = False,
        properties: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        suffix = ".png" if kind == "image" else ".mp4"
        source_path = self.temp_path / f"source-{len(self.workspace.nodes)}{suffix}"
        if kind == "image":
            image = QImage(40, 20, QImage.Format.Format_ARGB32)
            image.fill(QColor("#336699"))
            self.assertTrue(image.save(str(source_path), "PNG"))
        else:
            source_path.write_bytes(b"video")
        node = SimpleNamespace(
            node_id=f"source-{len(self.workspace.nodes)}",
            type_id="media.panel",
            properties={"source": str(source_path), **dict(properties or {})},
            exposed_ports={"source": exposed},
            x=10.0,
            y=20.0,
            links=[],
        )
        self.workspace.nodes[node.node_id] = node
        return node

    @staticmethod
    def _ready_resolution(
        path: Path,
        *,
        kind: str,
        exposed: bool = False,
        url: str | None = None,
    ) -> MediaPanelSourceResolution:
        resolved = url or QUrl.fromLocalFile(str(path)).toString()
        return MediaPanelSourceResolution(
            authority="input" if exposed else "property",
            input_exposed=exposed,
            input_connected=exposed,
            state="ready",
            media_kind=kind,
            source_ref=str(path),
            resolved_source_url=resolved,
            preview_source_url=resolved if kind == "image" else "",
        )

    def _trim_context(
        self,
        node: SimpleNamespace,
        *,
        action: str = "replace",
        start_ms: int = 1000,
        end_ms: int = 3000,
    ) -> media_panel_action_service_module._VideoTrimContext:
        resolution = self.service._active_media_source(
            node.node_id,
            expected_kind="video",
        )[1]
        assert resolution is not None
        return media_panel_action_service_module._VideoTrimContext(
            action=action,
            node_id=node.node_id,
            start_ms=start_ms,
            end_ms=end_ms,
            scene_x=0.0,
            scene_y=0.0,
            properties=dict(node.properties),
            resolved_source_url=resolution.resolved_source_url,
        )

    def test_crop_success_preserves_result_and_resets_crop(self) -> None:
        node = self._add_media_node(
            "image",
            properties={"crop_x": 0.25, "crop_y": 0.25, "crop_w": 0.5, "crop_h": 0.5},
        )

        result = self.service.request_save_image_crop_replace(
            node.node_id,
            {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["source_ref"], "temp://staged")
        self.assertEqual(
            {
                key: node.properties[key]
                for key in ("crop_x", "crop_y", "crop_w", "crop_h")
            },
            {"crop_x": 0.0, "crop_y": 0.0, "crop_w": 1.0, "crop_h": 1.0},
        )
        self.assertEqual(self.stage.calls[0]["artifact_kind"], "image_crop_source")

    def test_crop_validation_authority_staging_and_source_race_fail_closed(
        self,
    ) -> None:
        node = self._add_media_node("image")
        cases: list[tuple[str, dict[str, object]]] = [
            ("no_effective_crop", {}),
            ("invalid_crop", {"x": 0, "y": 0, "width": 0.0, "height": 0.5}),
        ]
        for code, crop in cases:
            with self.subTest(code=code):
                result = self.service.request_save_image_crop_replace(
                    node.node_id, crop
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["error"]["code"], code)

        path = Path(node.properties["source"])
        exposed = self._ready_resolution(path, kind="image", exposed=True)
        with patch.object(
            self.service,
            "_active_media_source",
            return_value=(node, exposed),
        ):
            result = self.service.request_save_image_crop_replace(
                node.node_id,
                {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
            )
        self.assertEqual(result["error"]["code"], "input_authority")

        self.stage.result = ""
        result = self.service.request_save_image_crop_replace(
            node.node_id,
            {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
        )
        self.assertEqual(result["error"]["code"], "stage_failed")

        self.stage.result = "temp://race"
        current = self.service._active_media_source(node.node_id, expected_kind="image")
        assert current[1] is not None
        changed = self._ready_resolution(
            path,
            kind="image",
            url="file:///changed.png",
        )
        with patch.object(
            self.service,
            "_active_media_source",
            side_effect=[current, (node, changed)],
        ):
            result = self.service.request_save_image_crop_replace(
                node.node_id,
                {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
            )
        self.assertEqual(result["error"]["code"], "source_changed")

    def test_frame_success_forces_hidden_source_and_preserves_capture_size(
        self,
    ) -> None:
        source = self._add_media_node("video", exposed=True)
        source_path = Path(source.properties["source"])
        ready = self._ready_resolution(source_path, kind="video", exposed=True)
        frame_path = self.temp_path / "frame.png"
        frame = QImage(24, 12, QImage.Format.Format_ARGB32)
        frame.fill(QColor("#ba4d68"))
        self.assertTrue(frame.save(str(frame_path), "PNG"))

        with patch.object(
            self.service,
            "_active_media_source",
            return_value=(source, ready),
        ):
            result = self.service.request_create_video_frame_image_node(
                source.node_id,
                str(frame_path),
                1200,
                30.0,
                40.0,
                240.0,
                120.0,
            )

        created = self.workspace.nodes[str(result["created_node_id"])]
        self.assertTrue(result["success"])
        self.assertFalse(created.exposed_ports["source"])
        self.assertEqual((created.custom_width, created.custom_height), (240.0, 120.0))
        self.assertEqual(self.stage.calls[0]["artifact_kind"], "video_frame_capture")

    def test_frame_missing_empty_and_source_race_clean_up_capture(self) -> None:
        source = self._add_media_node("video")
        missing = self.temp_path / "missing.png"
        result = self.service.request_create_video_frame_image_node(
            source.node_id,
            str(missing),
            0,
            0.0,
            0.0,
            0.0,
            0.0,
        )
        self.assertEqual(result["error"]["code"], "missing_frame")

        empty = self.temp_path / "empty.png"
        empty.write_bytes(b"")
        result = self.service.request_create_video_frame_image_node(
            source.node_id,
            str(empty),
            0,
            0.0,
            0.0,
            0.0,
            0.0,
        )
        self.assertEqual(result["error"]["code"], "empty_frame")
        self.assertFalse(empty.exists())

        frame = self.temp_path / "race.png"
        frame.write_bytes(b"frame")
        current = self.service._active_media_source(
            source.node_id, expected_kind="video"
        )
        assert current[1] is not None
        changed = self._ready_resolution(
            Path(source.properties["source"]),
            kind="video",
            url="file:///changed.mp4",
        )
        with patch.object(
            self.service,
            "_active_media_source",
            side_effect=[current, (source, changed)],
        ):
            result = self.service.request_create_video_frame_image_node(
                source.node_id,
                str(frame),
                0,
                0.0,
                0.0,
                0.0,
                0.0,
            )
        self.assertEqual(result["error"]["code"], "source_changed")
        self.assertFalse(frame.exists())

    def test_frame_creation_and_staging_failures_keep_result_shape(self) -> None:
        source = self._add_media_node("video")
        for mode, code in (("create", "create_failed"), ("stage", "stage_failed")):
            with self.subTest(mode=mode):
                frame_path = self.temp_path / f"{mode}.png"
                frame_path.write_bytes(b"frame")
                self.scene.raise_create = mode == "create"
                self.stage.result = "" if mode == "stage" else "temp://frame"
                result = self.service.request_create_video_frame_image_node(
                    source.node_id,
                    str(frame_path),
                    0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(
                    set(result),
                    {
                        "success",
                        "created_node_id",
                        "created_type_id",
                        "source_ref",
                        "link_id",
                        "request_id",
                        "error",
                    },
                )
                self.scene.raise_create = False

    def test_timestamp_success_creation_failure_and_link_failure(self) -> None:
        source = self._add_media_node("video")
        result = self.service.request_create_video_timestamp_annotation(
            source.node_id,
            1200,
            30.0,
            40.0,
        )
        note = self.workspace.nodes[str(result["created_node_id"])]
        self.assertTrue(result["success"])
        self.assertEqual(result["link_id"], "link-video")
        self.assertIn("corex-link:link-video", note.properties["text"])

        self.scene.raise_create = True
        failed = self.service.request_create_video_timestamp_annotation(
            source.node_id,
            1200,
            30.0,
            40.0,
        )
        self.assertEqual(failed["error"]["code"], "create_failed")

        self.scene.raise_create = False
        self.scene.link_result = ""
        unlinked = self.service.request_create_video_timestamp_annotation(
            source.node_id,
            1200,
            30.0,
            40.0,
        )
        unlinked_note = self.workspace.nodes[str(unlinked["created_node_id"])]
        self.assertTrue(unlinked["success"])
        self.assertEqual(unlinked["link_id"], "")
        self.assertEqual(unlinked_note.properties["text"], "Video note")

    def test_trim_replace_validation_authority_and_completion(self) -> None:
        source = self._add_media_node(
            "video",
            properties={
                "timeline_bookmarks": [
                    {"id": "keep", "label": "Keep", "position_ms": 1500},
                    {"id": "drop", "label": "Drop", "position_ms": 5000},
                ]
            },
        )
        invalid = self.service.request_trim_video_clip_replace(
            source.node_id,
            2000,
            1000,
        )
        self.assertEqual(invalid["error"]["code"], "invalid_clip_range")

        path = Path(source.properties["source"])
        exposed = self._ready_resolution(path, kind="video", exposed=True)
        with patch.object(
            self.service,
            "_active_media_source",
            return_value=(source, exposed),
        ):
            denied = self.service.request_trim_video_clip_replace(
                source.node_id,
                1000,
                2000,
            )
        self.assertEqual(denied["error"]["code"], "input_authority")

        context = self._trim_context(source)
        completed = self.service._complete_video_trim_replace(
            context,
            VideoTrimResult(True, data=b"trimmed", mode_used="fast_copy"),
        )
        self.assertTrue(completed["success"])
        self.assertEqual(source.properties["source"], "temp://staged")
        self.assertEqual(
            source.properties["timeline_bookmarks"],
            [{"id": "keep", "label": "Keep", "position_ms": 500}],
        )

    def test_trim_replace_staging_and_source_races_fail_closed(self) -> None:
        source = self._add_media_node("video")
        context = self._trim_context(source)
        self.stage.result = ""
        failed = self.service._complete_video_trim_replace(
            context,
            VideoTrimResult(True, data=b"trimmed", mode_used="fast_copy"),
        )
        self.assertEqual(failed["error"]["code"], "stage_failed")

        self.stage.result = "temp://trim"
        changed = self._ready_resolution(
            Path(source.properties["source"]),
            kind="video",
            url="file:///changed.mp4",
        )
        with patch.object(
            self.service,
            "_active_media_source",
            return_value=(source, changed),
        ):
            raced = self.service._complete_video_trim_replace(
                context,
                VideoTrimResult(True, data=b"trimmed", mode_used="fast_copy"),
            )
        self.assertEqual(raced["error"]["code"], "source_changed")

    def test_worker_failure_notifies_and_thread_signal_cleans_job(self) -> None:
        source = self._add_media_node("video")
        with patch.object(
            media_panel_action_service_module.QThread,
            "start",
            new=lambda _thread: None,
        ):
            submitted = self.service.request_trim_video_clip_copy(
                source.node_id,
                1000,
                2000,
                30.0,
                40.0,
            )
        request_id = str(submitted["request_id"])
        thread, worker, _context = self.service._video_trim_jobs[request_id]

        worker.finished.emit(
            request_id,
            VideoTrimResult(
                False,
                message="worker failed",
                diagnostics="diagnostic tail",
            ),
        )
        self.app.processEvents()

        self.assertIn(("error", "Video trim failed: worker failed"), self.logs)
        self.assertIn(("error", "diagnostic tail"), self.logs)
        self.assertEqual(self.notifications, ["updated"])
        self.assertEqual(self.hints[-1], ("worker failed", 4200))

        thread.finished.emit()
        self.app.processEvents()
        self.assertNotIn(request_id, self.service._video_trim_jobs)
        thread.deleteLater()
        worker.deleteLater()

    def test_timeline_bookmark_remapping_accepts_json_and_bounds(self) -> None:
        value = json.dumps(
            [
                {"id": "before", "position_ms": 999},
                {"id": "start", "label": "Start", "position_ms": 1000},
                {"id": "inside", "position_ms": 1500},
                {"id": "end", "label": "End", "position_ms": 2000},
                {"id": "after", "position_ms": 2001},
                "invalid",
            ]
        )

        result = media_panel_action_service_module._remap_timeline_bookmarks(
            value,
            1000,
            2000,
        )

        self.assertEqual(
            result,
            [
                {"id": "start", "label": "Start", "position_ms": 0},
                {"id": "inside", "label": "0:00", "position_ms": 500},
                {"id": "end", "label": "End", "position_ms": 1000},
            ],
        )


class MediaPanelActionServiceTests(MainWindowShellTestBase):
    def test_service_owns_lazy_trim_jobs_and_direct_dependencies(self) -> None:
        service = self.window.media_panel_action_service

        self.assertIsInstance(service, MediaPanelActionService)
        self.assertIsInstance(service, QObject)
        self.assertIs(service.parent(), self.window)
        self.assertIs(
            service._workspace_edit_controller,
            self.window.workspace_edit_controller,
        )
        self.assertIs(
            service._workspace_drop_connect_controller,
            self.window.workspace_drop_connect_controller,
        )
        self.assertEqual(service._video_trim_jobs, {})
        self.assertEqual(service.findChildren(QThread), [])
        self.assertFalse(hasattr(self.window, "graph_canvas_presenter"))

    def test_trim_worker_thread_is_created_lazily_and_cleaned_by_service(
        self,
    ) -> None:
        source_path = Path(self._env.temp_path) / "lazy-trim-source.mp4"
        source_path.write_bytes(b"video")
        node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={"source": str(source_path)},
            exposed_port_overrides={"source": False},
        )
        service = self.window.media_panel_action_service

        with patch.object(
            media_panel_action_service_module.QThread,
            "start",
            new=lambda _thread: None,
        ):
            result = service.request_trim_video_clip_copy(
                node_id,
                1000,
                2000,
                360.0,
                80.0,
            )

        request_id = str(result["request_id"])
        thread, worker, _context = service._video_trim_jobs[request_id]
        self.assertTrue(result["success"])
        self.assertIs(thread.parent(), service)
        self.assertIs(worker.thread(), thread)
        self.assertEqual(len(service._video_trim_jobs), 1)

        service._video_trim_thread_finished(request_id)

        self.assertEqual(service._video_trim_jobs, {})
        thread.deleteLater()
        worker.deleteLater()

    def test_media_panel_frame_staging_failure_rolls_back_created_node_and_history(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        video_path = Path(self._env.temp_path) / "frame-failure-source.mp4"
        video_path.write_bytes(b"video")
        video_node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={"source": str(video_path)},
            exposed_port_overrides={"source": False},
        )
        frame_path = Path(self._env.temp_path) / "failed-frame.png"
        frame = QImage(24, 12, QImage.Format.Format_ARGB32)
        frame.fill(QColor("#ba4d68"))
        workspace = self.window.model.project.workspaces[workspace_id]

        for pre_dirty, expected_revision in ((False, 419), (True, 503)):
            with self.subTest(pre_dirty=pre_dirty):
                self.assertTrue(frame.save(str(frame_path), "PNG"))
                workspace.dirty = pre_dirty
                workspace.mutation_revision = expected_revision
                self.window.runtime_history.clear_workspace(workspace_id)
                before_node_ids = set(workspace.nodes)
                before_edges = dict(workspace.edges)
                before_selection = tuple(self.window.scene.selected_node_ids)
                before_metadata = copy.deepcopy(self.window.model.project.metadata)

                with patch.object(
                    self.window.media_panel_action_service,
                    "_stage_video_frame_capture",
                    return_value="",
                ):
                    result = self.window.media_panel_action_service.request_create_video_frame_image_node(
                        video_node_id,
                        str(frame_path),
                        1200,
                        360.0,
                        80.0,
                        240.0,
                        120.0,
                    )

                self.assertFalse(result["success"])
                self.assertEqual(result["error"]["code"], "stage_failed")
                self.assertEqual(result["created_node_id"], "")
                self.assertEqual(set(workspace.nodes), before_node_ids)
                self.assertEqual(workspace.edges, before_edges)
                self.assertEqual(
                    tuple(self.window.scene.selected_node_ids),
                    before_selection,
                )
                self.assertEqual(self.window.model.project.metadata, before_metadata)
                self.assertEqual(workspace.dirty, pre_dirty)
                self.assertEqual(workspace.mutation_revision, expected_revision)
                self.assertEqual(
                    self.window.runtime_history.undo_depth(workspace_id),
                    0,
                )
                self.assertEqual(
                    self.window.runtime_history.redo_depth(workspace_id),
                    0,
                )

    def test_media_panel_trim_copy_staging_failure_rolls_back_created_node_and_history(
        self,
    ) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        video_path = Path(self._env.temp_path) / "trim-failure-source.mp4"
        video_path.write_bytes(b"video")
        video_node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={"source": str(video_path)},
            exposed_port_overrides={"source": False},
        )
        source_node, source_resolution = (
            self.window.media_panel_action_service._active_media_source(
                video_node_id,
                expected_kind="video",
            )
        )
        self.assertIsNotNone(source_node)
        self.assertIsNotNone(source_resolution)
        assert source_resolution is not None
        context = media_panel_action_service_module._VideoTrimContext(
            action="copy",
            node_id=video_node_id,
            start_ms=1000,
            end_ms=2000,
            scene_x=360.0,
            scene_y=80.0,
            properties=dict(source_node.properties),
            resolved_source_url=source_resolution.resolved_source_url,
        )
        workspace = self.window.model.project.workspaces[workspace_id]
        self.window.runtime_history.clear_workspace(workspace_id)
        before_node_ids = set(workspace.nodes)
        before_edges = dict(workspace.edges)
        before_selection = tuple(self.window.scene.selected_node_ids)
        before_metadata = dict(self.window.model.project.metadata)

        with patch.object(
            self.window.media_panel_action_service,
            "_stage_video_clip",
            return_value="",
        ):
            result = self.window.media_panel_action_service._complete_video_trim_copy(
                context,
                VideoTrimResult(
                    success=True,
                    data=b"trimmed",
                    mode_used="fast_copy",
                ),
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "stage_failed")
        self.assertEqual(result["created_node_id"], "")
        self.assertEqual(set(workspace.nodes), before_node_ids)
        self.assertEqual(workspace.edges, before_edges)
        self.assertEqual(
            tuple(self.window.scene.selected_node_ids),
            before_selection,
        )
        self.assertEqual(self.window.model.project.metadata, before_metadata)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 0)
        self.assertEqual(self.window.runtime_history.redo_depth(workspace_id), 0)

        metadata_spy = QSignalSpy(self.window.project_meta_changed)
        success = self.window.media_panel_action_service._complete_video_trim_copy(
            context,
            VideoTrimResult(
                success=True,
                data=b"trimmed",
                mode_used="fast_copy",
            ),
        )
        copied = workspace.nodes[str(success["created_node_id"])]
        self.assertTrue(success["success"])
        self.assertEqual(copied.type_id, "media.panel")
        self.assertFalse(copied.exposed_ports["source"])
        copied_ref = str(copied.properties["source"])
        self.assertTrue(copied_ref.startswith("temp://"))
        store = self.window.project_session_controller.project_artifact_store()
        copied_entry = store.staged_entry(copied_ref)
        copied_path = store.resolve_staged_path(copied_ref)
        self.assertIsNotNone(copied_entry)
        self.assertIsNotNone(copied_path)
        assert copied_entry is not None and copied_path is not None
        copied_bytes = copied_path.read_bytes()
        self.assertEqual(copied_bytes, b"trimmed")
        self.assertEqual(copied_entry.extra["artifact_kind"], "video_clip_source")
        self.assertEqual(copied_entry.extra["mime_type"], "video/mp4")
        self.assertEqual(copied_entry.extra["size"], len(copied_bytes))
        self.assertEqual(
            copied_entry.extra["sha256"],
            hashlib.sha256(copied_bytes).hexdigest(),
        )
        self.assertEqual(copied_entry.extra["node_id"], copied.node_id)
        self.assertEqual(len(metadata_spy), 1)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
