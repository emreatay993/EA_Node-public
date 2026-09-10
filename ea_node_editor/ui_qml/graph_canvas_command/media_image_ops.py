from __future__ import annotations

from typing import Any

from PyQt6.QtCore import pyqtSlot

from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.ui_qml.bridge_runtime import invoke as _invoke


class MediaImageOps:
    """Image panel commands: destructive crop save."""

    @pyqtSlot(str, "QVariantMap", result="QVariantMap")
    def request_save_image_crop_replace(
        self,
        image_node_id: str,
        crop_rect: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(
            _invoke(
                self._media_action_source,
                "request_save_image_crop_replace",
                image_node_id,
                dict(crop_rect or {}),
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
