from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.ui_qml.bridge_runtime import (
    invoke as _invoke,
)

if TYPE_CHECKING:
    pass


class MediaVideoOps:
    """Video panel commands: frame capture, timestamp annotation, trim save/copy."""

    @pyqtSlot(str, int, result=str)
    def video_frame_capture_path(self, video_node_id: str, position_ms: int) -> str:
        return str(
            _invoke(
                self._media_action_source,
                "video_frame_capture_path",
                video_node_id,
                int(position_ms),
                default="",
            )
            or ""
        )

    @pyqtSlot(str, str, int, float, float, float, float, result="QVariantMap")
    def request_create_video_frame_image_node(
        self,
        video_node_id: str,
        frame_path: str,
        position_ms: int,
        scene_x: float,
        scene_y: float,
        capture_width: float,
        capture_height: float,
    ) -> dict[str, Any]:
        return dict(
            _invoke(
                self._media_action_source,
                "request_create_video_frame_image_node",
                video_node_id,
                frame_path,
                int(position_ms),
                float(scene_x),
                float(scene_y),
                float(capture_width),
                float(capture_height),
                default={
                    "success": False,
                    "created_node_id": "",
                    "created_type_id": MEDIA_PANEL_TYPE_ID,
                    "source_ref": "",
                    "error": {
                        "code": "mutation_unavailable",
                        "message": "Media Panel actions are unavailable.",
                    },
                },
            )
            or {}
        )

    @pyqtSlot(str, int, float, float, result="QVariantMap")
    def request_create_video_timestamp_annotation(
        self,
        video_node_id: str,
        position_ms: int,
        scene_x: float,
        scene_y: float,
    ) -> dict[str, Any]:
        return dict(
            _invoke(
                self._media_action_source,
                "request_create_video_timestamp_annotation",
                video_node_id,
                int(position_ms),
                float(scene_x),
                float(scene_y),
                default={
                    "success": False,
                    "created_node_id": "",
                    "created_type_id": "passive.annotation.text",
                    "link_id": "",
                    "error": {
                        "code": "mutation_unavailable",
                        "message": "Media Panel actions are unavailable.",
                    },
                },
            )
            or {}
        )

    @pyqtSlot(str, int, int, "QVariantMap", result="QVariantMap")
    def request_trim_video_clip_replace(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(
            _invoke(
                self._media_action_source,
                "request_trim_video_clip_replace",
                video_node_id,
                int(start_ms),
                int(end_ms),
                dict(state or {}),
                default={
                    "success": False,
                    "created_node_id": "",
                    "created_type_id": MEDIA_PANEL_TYPE_ID,
                    "source_ref": "",
                    "request_id": "",
                    "error": {
                        "code": "mutation_unavailable",
                        "message": "Media Panel actions are unavailable.",
                    },
                },
            )
            or {}
        )

    @pyqtSlot(str, int, int, float, float, "QVariantMap", result="QVariantMap")
    def request_trim_video_clip_copy(
        self,
        video_node_id: str,
        start_ms: int,
        end_ms: int,
        scene_x: float,
        scene_y: float,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(
            _invoke(
                self._media_action_source,
                "request_trim_video_clip_copy",
                video_node_id,
                int(start_ms),
                int(end_ms),
                float(scene_x),
                float(scene_y),
                dict(state or {}),
                default={
                    "success": False,
                    "created_node_id": "",
                    "created_type_id": MEDIA_PANEL_TYPE_ID,
                    "source_ref": "",
                    "request_id": "",
                    "error": {
                        "code": "mutation_unavailable",
                        "message": "Media Panel actions are unavailable.",
                    },
                },
            )
            or {}
        )
