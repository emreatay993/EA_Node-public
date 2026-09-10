from __future__ import annotations

"""Graph scene payload construction package.

Decomposed from the former graph_scene_payload_builder.py module:
normalization helpers, theme inputs, per-node payload factory, comment-
backdrop partitioner, builder composition root, and fullscreen builders.
"""

from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_scene_payload.fullscreen import (
    build_content_fullscreen_media_payload,
    build_content_fullscreen_plot_payload,
    build_content_fullscreen_web_editor_payload,
    build_content_fullscreen_web_page_payload,
    build_jupyter_notebook_payload,
)
from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    PLOT_CONTENT_KIND,
    WEB_PAGE_CONTENT_KIND,
)

__all__ = [
    "PLOT_CONTENT_KIND",
    "WEB_PAGE_CONTENT_KIND",
    "GraphScenePayloadBuilder",
    "build_content_fullscreen_media_payload",
    "build_content_fullscreen_plot_payload",
    "build_content_fullscreen_web_page_payload",
    "build_content_fullscreen_web_editor_payload",
    "build_jupyter_notebook_payload",
]
