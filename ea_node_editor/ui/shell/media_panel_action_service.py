# Purpose: Own Media Panel crop, capture, timestamp, and trim actions.
# Map: feature_routes/media_image_video_pdf_refocus
# Tests: tests/test_media_panel_action_service.py
from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from PyQt6.QtCore import QObject, QThread, QUrl

from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.passive_annotation import (
    PASSIVE_ANNOTATION_TEXT_TYPE_ID,
)
from ea_node_editor.ui.image_crop import (
    ImageCropError,
    crop_image_file_to_png_bytes,
    crop_rect_is_effective,
)
from ea_node_editor.ui.media_panel_source import (
    MediaPanelSourceResolution,
    resolve_media_panel_source,
)
from ea_node_editor.ui.media_video_state import format_video_time
from ea_node_editor.ui.video_trim import VideoTrimResult, VideoTrimWorker

if TYPE_CHECKING:
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.graph.project_state import ProjectData
    from ea_node_editor.graph.workspace_state import WorkspaceData
    from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
        WorkspaceDropConnectController,
    )
    from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
        WorkspaceEditController,
    )
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


@dataclass(frozen=True, slots=True)
class _VideoTrimContext:
    action: str
    node_id: str
    start_ms: int
    end_ms: int
    scene_x: float
    scene_y: float
    properties: dict[str, Any]
    resolved_source_url: str


class MediaPanelActionService(QObject):
    def __init__(
        self,
        parent: QObject,
        *,
        scene_mutation: "GraphSceneBridge",
        workspace_edit_controller: "WorkspaceEditController",
        workspace_drop_connect_controller: "WorkspaceDropConnectController",
        model_provider: Callable[[], "GraphModel"],
        active_workspace_provider: Callable[[], "WorkspaceData | None"],
        project_provider: Callable[[], "ProjectData"],
        stage_node_artifact_bytes: Callable[..., str],
        run_state_provider: Callable[[], object | None],
        project_path_provider: Callable[[], str | None],
        append_console_log: Callable[[str, str], None],
        show_graph_hint: Callable[[str, int], None],
        update_notification_counters: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._scene_mutation = scene_mutation
        self._workspace_edit_controller = workspace_edit_controller
        self._workspace_drop_connect_controller = workspace_drop_connect_controller
        self._model_provider = model_provider
        self._active_workspace_provider = active_workspace_provider
        self._project_provider = project_provider
        self._stage_node_artifact_bytes = stage_node_artifact_bytes
        self._run_state_provider = run_state_provider
        self._project_path_provider = project_path_provider
        self._append_console_log = append_console_log
        self._show_graph_hint = show_graph_hint
        self._update_notification_counters = update_notification_counters
        self._video_trim_jobs: dict[
            str,
            tuple[QThread, VideoTrimWorker, _VideoTrimContext],
        ] = {}

    def request_save_image_crop_replace(
        self,
        image_node_id: str,
        crop_rect: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        normalized_image_node_id = str(image_node_id or "").strip()
        node, source_resolution = self._active_media_source(
            normalized_image_node_id,
            expected_kind="image",
        )
        if node is None or source_resolution is None:
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="missing_image_node",
                message="The source Media Panel is not showing a ready image.",
            )
        if source_resolution.input_exposed:
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="input_authority",
                message="Hide the Source input before replacing the Media Panel source.",
            )
        normalized_crop = dict(crop_rect or {})
        try:
            if not crop_rect_is_effective(normalized_crop):
                return self._image_command_result(
                    success=False,
                    created_type_id=MEDIA_PANEL_TYPE_ID,
                    code="no_effective_crop",
                    message="Set a crop before saving the cropped image.",
                )
        except ImageCropError as exc:
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="invalid_crop",
                message=str(exc) or "The selected crop is invalid.",
            )

        source_path = self._local_media_source_path(source_resolution)
        if source_path is None or not source_path.exists() or not source_path.is_file():
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_unavailable",
                message="The source image file could not be found.",
            )
        try:
            crop_result = crop_image_file_to_png_bytes(source_path, normalized_crop)
        except ImageCropError as exc:
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="crop_failed",
                message=str(exc) or "The cropped image could not be saved.",
            )

        staged_ref = self._stage_image_crop(crop_result.data, node)
        if not staged_ref:
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="stage_failed",
                message="The cropped image could not be staged into the project.",
            )

        _current_node, current_resolution = self._active_media_source(
            normalized_image_node_id,
            expected_kind="image",
        )
        if (
            current_resolution is None
            or current_resolution.input_exposed
            or current_resolution.resolved_source_url
            != source_resolution.resolved_source_url
        ):
            return self._image_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_changed",
                message="The Media Panel source changed before the crop could be saved.",
            )
        self._scene_mutation.set_node_properties(
            normalized_image_node_id,
            {
                "source": staged_ref,
                "crop_x": 0.0,
                "crop_y": 0.0,
                "crop_w": 1.0,
                "crop_h": 1.0,
            },
        )
        self._append_console_log(
            "info",
            "Cropped Media Panel source saved internally.",
        )
        self._show_graph_hint("Cropped image saved internally.", 2800)
        return self._image_command_result(
            success=True,
            created_node_id=normalized_image_node_id,
            created_type_id=MEDIA_PANEL_TYPE_ID,
            source_ref=staged_ref,
        )

    def video_frame_capture_path(self, video_node_id: str, position_ms: int) -> str:
        safe_node_id = (
            "".join(
                character if character.isalnum() or character in {"-", "_"} else "-"
                for character in str(video_node_id or "").strip()
            )[:48]
            or "video"
        )
        position = max(0, int(position_ms or 0))
        return str(
            Path(tempfile.gettempdir())
            / f"corex-video-frame-{safe_node_id}-{position}-{uuid4().hex}.png"
        )

    def request_create_video_frame_image_node(
        self,
        video_node_id: str,
        frame_path: str,
        position_ms: int,
        scene_x: float,
        scene_y: float,
        capture_width: float,
        capture_height: float,
    ) -> dict[str, object]:
        normalized_video_node_id = str(video_node_id or "").strip()
        _source_node, source_resolution = self._active_media_source(
            normalized_video_node_id,
            expected_kind="video",
        )
        if source_resolution is None:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="missing_video_node",
                message="The source Media Panel is not showing a ready video.",
            )

        path = Path(str(frame_path or "").strip())
        try:
            frame_data = path.read_bytes()
        except OSError:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="missing_frame",
                message="The captured video frame could not be read.",
            )
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        if not frame_data:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="empty_frame",
                message="The captured video frame was empty.",
            )

        source_ref: dict[str, str] = {"value": ""}
        initial_width = self._positive_capture_dimension(capture_width)
        initial_height = self._positive_capture_dimension(capture_height)

        def _after_create(node, mutations) -> bool:  # noqa: ANN001
            staged_ref = self._stage_video_frame_capture(
                frame_data,
                node,
                max(0, int(position_ms or 0)),
            )
            if not staged_ref:
                return False
            source_ref["value"] = staged_ref
            mutations.set_node_properties(node.node_id, {"source": staged_ref})
            return True

        _current_node, current_resolution = self._active_media_source(
            normalized_video_node_id,
            expected_kind="video",
        )
        if (
            current_resolution is None
            or current_resolution.resolved_source_url
            != source_resolution.resolved_source_url
        ):
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_changed",
                message="The Media Panel source changed before the frame could be saved.",
            )

        try:
            node_id = str(
                self._scene_mutation.create_node_from_type(
                    type_id=MEDIA_PANEL_TYPE_ID,
                    x=float(scene_x),
                    y=float(scene_y),
                    parent_node_id=None,
                    select_node=True,
                    property_overrides={},
                    exposed_port_overrides={"source": False},
                    custom_width=initial_width,
                    custom_height=initial_height,
                    after_create=_after_create,
                )
                or ""
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="create_failed",
                message=str(exc) or "Media Panel creation failed.",
            )

        if not node_id or not source_ref["value"]:
            return self._video_command_result(
                success=False,
                created_node_id=node_id,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="stage_failed",
                message="The captured frame could not be staged into the project.",
            )
        return self._video_command_result(
            success=True,
            created_node_id=node_id,
            created_type_id=MEDIA_PANEL_TYPE_ID,
            source_ref=source_ref["value"],
        )

    def request_create_video_timestamp_annotation(
        self,
        video_node_id: str,
        position_ms: int,
        scene_x: float,
        scene_y: float,
    ) -> dict[str, object]:
        normalized_video_node_id = str(video_node_id or "").strip()
        _source_node, source_resolution = self._active_media_source(
            normalized_video_node_id,
            expected_kind="video",
        )
        if source_resolution is None:
            return self._video_command_result(
                success=False,
                created_type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
                code="missing_video_node",
                message="The source Media Panel is not showing a ready video.",
            )

        position = max(0, int(position_ms or 0))
        time_label = format_video_time(position)
        try:
            node_id = str(
                self._scene_mutation.create_node_from_type(
                    type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
                    x=float(scene_x),
                    y=float(scene_y),
                    parent_node_id=None,
                    select_node=True,
                    property_overrides={
                        "text": "Video note",
                        "format": "markdown",
                    },
                )
                or ""
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            return self._video_command_result(
                success=False,
                created_type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
                code="create_failed",
                message=str(exc) or "Text annotation creation failed.",
            )
        if not node_id:
            return self._video_command_result(
                success=False,
                created_type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
                code="create_failed",
                message="Text annotation creation failed.",
            )

        link_id = str(
            self._scene_mutation.upsert_node_link(
                node_id,
                "",
                "node",
                f"Video {time_label}",
                normalized_video_node_id,
                f"video_position_ms={position}",
            )
            or ""
        )
        if link_id:
            self._scene_mutation.set_node_properties(
                node_id,
                {
                    "text": f"[Video {time_label}](corex-link:{link_id})\n\nVideo note",
                    "format": "markdown",
                },
            )
        return self._video_command_result(
            success=True,
            created_node_id=node_id,
            created_type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
            link_id=link_id,
        )

    def request_trim_video_clip_replace(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        state: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        return self._request_trim_video_clip(
            action="replace",
            video_node_id=video_node_id,
            start_ms=start_ms,
            end_ms=end_ms,
            scene_x=0.0,
            scene_y=0.0,
            state=state,
        )

    def request_trim_video_clip_copy(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        scene_x: float,
        scene_y: float,
        state: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        return self._request_trim_video_clip(
            action="copy",
            video_node_id=video_node_id,
            start_ms=start_ms,
            end_ms=end_ms,
            scene_x=float(scene_x),
            scene_y=float(scene_y),
            state=state,
        )

    @staticmethod
    def _positive_capture_dimension(value: object) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not isfinite(number) or number <= 0:
            return None
        return number

    def _active_media_source(
        self,
        node_id: str,
        *,
        expected_kind: str,
    ) -> tuple[object | None, MediaPanelSourceResolution | None]:
        model = self._model_provider()
        workspace = self._active_workspace_provider()
        project = self._project_provider()
        if model is None or workspace is None or project is None:
            return None, None
        node = workspace.nodes.get(str(node_id or "").strip())
        if node is None or str(node.type_id) != MEDIA_PANEL_TYPE_ID:
            return None, None
        try:
            resolution = resolve_media_panel_source(
                node=node,
                workspace=workspace,
                run_state=self._run_state_provider(),
                project_path=(str(self._project_path_provider() or "").strip() or None),
                project_metadata=(
                    dict(project.metadata)
                    if isinstance(project.metadata, Mapping)
                    else None
                ),
            )
        except (OSError, TypeError, ValueError):
            return node, None
        if resolution.state != "ready" or resolution.media_kind != expected_kind:
            return node, None
        return node, resolution

    @staticmethod
    def _local_media_source_path(
        resolution: MediaPanelSourceResolution,
    ) -> Path | None:
        url = QUrl(str(resolution.resolved_source_url or "").strip())
        if not url.isLocalFile():
            return None
        path = str(url.toLocalFile() or "").strip()
        return Path(path) if path else None

    def _request_trim_video_clip(
        self,
        *,
        action: str,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        scene_x: float,
        scene_y: float,
        state: dict[str, Any] | None,
    ) -> dict[str, object]:
        normalized_node_id = str(video_node_id or "").strip()
        node, source_resolution = self._active_media_source(
            normalized_node_id,
            expected_kind="video",
        )
        if node is None or source_resolution is None:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="missing_video_node",
                message="The source Media Panel is not showing a ready video.",
            )
        if action == "replace" and source_resolution.input_exposed:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="input_authority",
                message="Hide the Source input before replacing the Media Panel source.",
            )
        start = max(0, int(start_ms or 0))
        end = max(0, int(end_ms or 0))
        if end <= start:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="invalid_clip_range",
                message="Set a clip out point after the clip in point.",
            )
        source_path = self._local_media_source_path(source_resolution)
        if source_path is None or not source_path.exists() or not source_path.is_file():
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_unavailable",
                message="Video trim is available only for ready local Media Panel sources.",
            )

        request_id = f"video_trim_{uuid4().hex}"
        properties = dict(getattr(node, "properties", {}) or {})
        properties.update(dict(state or {}))
        context = _VideoTrimContext(
            action=str(action or "replace"),
            node_id=normalized_node_id,
            start_ms=start,
            end_ms=end,
            scene_x=float(scene_x),
            scene_y=float(scene_y),
            properties=properties,
            resolved_source_url=source_resolution.resolved_source_url,
        )
        thread = QThread(self)
        worker = VideoTrimWorker(
            request_id=request_id,
            source_path=source_path,
            start_ms=start,
            end_ms=end,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._finish_video_trim_job)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda request_id=request_id: self._video_trim_thread_finished(request_id)
        )
        self._video_trim_jobs[request_id] = (thread, worker, context)
        self._append_console_log(
            "info",
            f"Trimming Media Panel clip ({format_video_time(start)}-{format_video_time(end)}).",
        )
        self._show_graph_hint("Trimming video clip...", 2400)
        thread.start()
        return self._video_command_result(
            success=True,
            created_type_id=MEDIA_PANEL_TYPE_ID,
            request_id=request_id,
        )

    def _finish_video_trim_job(self, request_id: str, result: object) -> None:
        record = self._video_trim_jobs.get(str(request_id or ""))
        if record is None:
            return
        _thread, _worker, context = record
        if not isinstance(result, VideoTrimResult) or not result.success:
            error_result = result if isinstance(result, VideoTrimResult) else None
            message = (
                error_result.message
                if error_result is not None
                else "Video trim failed."
            )
            diagnostics = error_result.diagnostics if error_result is not None else ""
            self._append_console_log("error", f"Video trim failed: {message}")
            if diagnostics:
                self._append_console_log("error", diagnostics)
            self._update_notification_counters()
            self._show_graph_hint(message, 4200)
            return

        if context.action == "copy":
            command_result = self._complete_video_trim_copy(context, result)
        else:
            command_result = self._complete_video_trim_replace(context, result)

        if bool(command_result.get("success")):
            mode = str(result.mode_used or "ffmpeg")
            self._append_console_log(
                "info",
                f"Video trim saved internally ({mode}).",
            )
            self._show_graph_hint("Trimmed video saved internally.", 2800)
        else:
            error = (
                command_result.get("error")
                if isinstance(command_result.get("error"), dict)
                else {}
            )
            message = str(error.get("message") or "Video trim could not be saved.")
            self._append_console_log("error", message)
            self._update_notification_counters()
            self._show_graph_hint(message, 4200)

    def _complete_video_trim_replace(
        self,
        context: _VideoTrimContext,
        result: VideoTrimResult,
    ) -> dict[str, object]:
        node, source_resolution = self._active_media_source(
            context.node_id,
            expected_kind="video",
        )
        if (
            node is None
            or source_resolution is None
            or source_resolution.input_exposed
            or source_resolution.resolved_source_url != context.resolved_source_url
        ):
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_changed",
                message="The Media Panel source or authority changed before trim replacement completed.",
            )
        staged_ref = self._stage_video_clip(
            result.data,
            node,
            context.start_ms,
            context.end_ms,
        )
        if not staged_ref:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="stage_failed",
                message="The trimmed video could not be staged into the project.",
            )
        self._scene_mutation.set_node_properties(
            context.node_id,
            self._trimmed_video_properties(context, staged_ref),
        )
        return self._video_command_result(
            success=True,
            created_node_id=context.node_id,
            created_type_id=MEDIA_PANEL_TYPE_ID,
            source_ref=staged_ref,
        )

    def _complete_video_trim_copy(
        self,
        context: _VideoTrimContext,
        result: VideoTrimResult,
    ) -> dict[str, object]:
        source_node, source_resolution = self._active_media_source(
            context.node_id,
            expected_kind="video",
        )
        if (
            source_node is None
            or source_resolution is None
            or source_resolution.resolved_source_url != context.resolved_source_url
        ):
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="source_changed",
                message="The Media Panel source changed before trim copy completed.",
            )
        source_ref: dict[str, str] = {"value": ""}
        copy_properties = self._trimmed_video_properties(context, "")
        for key in (
            "fit_mode",
            "show_title",
            "show_frame",
            "auto_play",
            "muted",
            "loop",
            "volume",
            "playback_rate",
        ):
            if key in context.properties:
                copy_properties[key] = context.properties[key]
        x = (
            context.scene_x
            if isfinite(context.scene_x) and context.scene_x
            else float(getattr(source_node, "x", 0.0)) + 48.0
        )
        y = (
            context.scene_y
            if isfinite(context.scene_y) and context.scene_y
            else float(getattr(source_node, "y", 0.0)) + 48.0
        )

        def _after_create(node, mutations) -> bool:  # noqa: ANN001
            staged_ref = self._stage_video_clip(
                result.data,
                node,
                context.start_ms,
                context.end_ms,
            )
            if not staged_ref:
                return False
            source_ref["value"] = staged_ref
            properties = dict(copy_properties)
            properties["source"] = staged_ref
            mutations.set_node_properties(node.node_id, properties)
            return True

        try:
            node_id = str(
                self._scene_mutation.create_node_from_type(
                    type_id=MEDIA_PANEL_TYPE_ID,
                    x=x,
                    y=y,
                    parent_node_id=None,
                    select_node=True,
                    property_overrides={},
                    exposed_port_overrides={"source": False},
                    after_create=_after_create,
                )
                or ""
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            return self._video_command_result(
                success=False,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="create_failed",
                message=str(exc) or "Media Panel creation failed.",
            )
        if not node_id or not source_ref["value"]:
            return self._video_command_result(
                success=False,
                created_node_id=node_id,
                created_type_id=MEDIA_PANEL_TYPE_ID,
                code="stage_failed",
                message="The trimmed video could not be staged into the project.",
            )
        return self._video_command_result(
            success=True,
            created_node_id=node_id,
            created_type_id=MEDIA_PANEL_TYPE_ID,
            source_ref=source_ref["value"],
        )

    def _video_trim_thread_finished(self, request_id: str) -> None:
        self._video_trim_jobs.pop(str(request_id or ""), None)

    def _trimmed_video_properties(
        self,
        context: _VideoTrimContext,
        staged_ref: str,
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "position_ms": 0,
            "clip_enabled": False,
            "clip_start_ms": 0,
            "clip_end_ms": 0,
            "timeline_bookmarks": _remap_timeline_bookmarks(
                context.properties.get("timeline_bookmarks"),
                context.start_ms,
                context.end_ms,
            ),
        }
        if staged_ref:
            properties["source"] = staged_ref
        return properties

    def _stage_image_crop(self, image_data: bytes, node) -> str:  # noqa: ANN001
        try:
            return str(
                self._stage_node_artifact_bytes(
                    data=bytes(image_data or b""),
                    filename=f"image-crop-{uuid4().hex[:8]}.png",
                    mime_type="image/png",
                    artifact_prefix="image_crop",
                    subdirectory="media",
                    artifact_kind="image_crop_source",
                    node_id=node.node_id,
                )
                or ""
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return ""

    def _stage_video_frame_capture(
        self,
        frame_data: bytes,
        node,
        position_ms: int,
    ) -> str:  # noqa: ANN001
        try:
            return str(
                self._stage_node_artifact_bytes(
                    data=bytes(frame_data or b""),
                    filename=(
                        f"video-frame-{max(0, int(position_ms or 0))}-"
                        f"{uuid4().hex[:8]}.png"
                    ),
                    mime_type="image/png",
                    artifact_prefix="video_frame",
                    subdirectory="media",
                    artifact_kind="video_frame_capture",
                    node_id=node.node_id,
                )
                or ""
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return ""

    def _stage_video_clip(
        self,
        video_data: bytes,
        node,
        start_ms: int,
        end_ms: int,
    ) -> str:  # noqa: ANN001
        try:
            return str(
                self._stage_node_artifact_bytes(
                    data=bytes(video_data or b""),
                    filename=(
                        f"video-clip-{max(0, int(start_ms or 0))}-"
                        f"{max(0, int(end_ms or 0))}-{uuid4().hex[:8]}.mp4"
                    ),
                    mime_type="video/mp4",
                    artifact_prefix="video_clip",
                    subdirectory="media",
                    artifact_kind="video_clip_source",
                    node_id=node.node_id,
                )
                or ""
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return ""

    def _image_command_result(
        self,
        *,
        success: bool,
        created_node_id: str = "",
        created_type_id: str = "",
        source_ref: str = "",
        link_id: str = "",
        request_id: str = "",
        code: str = "",
        message: str = "",
    ) -> dict[str, object]:
        return self._media_command_result(
            success=success,
            created_node_id=created_node_id,
            created_type_id=created_type_id,
            source_ref=source_ref,
            link_id=link_id,
            request_id=request_id,
            code=code,
            message=message,
            default_message="Image action failed.",
        )

    def _video_command_result(
        self,
        *,
        success: bool,
        created_node_id: str = "",
        created_type_id: str = "",
        source_ref: str = "",
        link_id: str = "",
        request_id: str = "",
        code: str = "",
        message: str = "",
    ) -> dict[str, object]:
        return self._media_command_result(
            success=success,
            created_node_id=created_node_id,
            created_type_id=created_type_id,
            source_ref=source_ref,
            link_id=link_id,
            request_id=request_id,
            code=code,
            message=message,
            default_message="Video action failed.",
        )

    @staticmethod
    def _media_command_result(
        *,
        success: bool,
        created_node_id: str = "",
        created_type_id: str = "",
        source_ref: str = "",
        link_id: str = "",
        request_id: str = "",
        code: str = "",
        message: str = "",
        default_message: str,
    ) -> dict[str, object]:
        return {
            "success": bool(success),
            "created_node_id": str(created_node_id or ""),
            "created_type_id": str(created_type_id or ""),
            "source_ref": str(source_ref or ""),
            "link_id": str(link_id or ""),
            "request_id": str(request_id or ""),
            "error": (
                {}
                if success
                else {
                    "code": str(code or "failed"),
                    "message": str(message or default_message),
                }
            ),
        }


def _remap_timeline_bookmarks(
    value: object,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, object]]:
    raw_items = value
    if isinstance(value, str):
        try:
            import json

            raw_items = json.loads(value)
        except (TypeError, ValueError):
            raw_items = []
    if not isinstance(raw_items, list):
        return []
    start = max(0, int(start_ms or 0))
    end = max(start + 1, int(end_ms or 0))
    remapped: list[dict[str, object]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        try:
            position = max(0, int(round(float(item.get("position_ms", 0)))))
        except (TypeError, ValueError):
            continue
        if position < start or position > end:
            continue
        label = str(item.get("label", "") or "").strip() or format_video_time(
            position - start
        )
        bookmark_id = (
            str(item.get("id", "") or "").strip() or f"bookmark-{index}-{position}"
        )
        remapped.append(
            {
                "id": bookmark_id,
                "label": label,
                "position_ms": position - start,
            }
        )
    return remapped


__all__ = ["MediaPanelActionService"]
