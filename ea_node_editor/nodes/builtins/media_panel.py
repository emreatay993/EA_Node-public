# Purpose: Declare and execute the active unified Media Panel node.
# Map: feature_routes/media_image_video_pdf_refocus.md
# Tests: tests/test_media_panel.py

from __future__ import annotations

import os

from ea_node_editor.nodes.builtins.core_values import IMAGE_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
    NodeResult,
)
from ea_node_editor.nodes.file_dialog_filters import (
    MEDIA_FILE_SUFFIXES,
    MEDIA_FILES_FILTER,
    is_supported_media_source_reference,
    media_kind_from_source,
)
from ea_node_editor.nodes.node_specs import PortSpec, PropertySpec
from ea_node_editor.runtime_contracts import ImageValue, RuntimeArtifactRef
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs

MEDIA_PANEL_TYPE_ID = "media.panel"
MEDIA_PANEL_CATEGORY = "Media"


def _validated_media_source(ctx: ExecutionContext) -> object:
    if ctx.iteration_count != 1:
        raise ValueError("Media Panel source requires exactly one runtime item.")
    inputs = resolve_single_run_inputs(ctx.inputs, node_name="Media Panel")
    if "source" not in inputs or inputs["source"] is None:
        raise NodeInputNotReadyError("Media Panel is waiting for a source input.")
    source = inputs["source"]
    if type(source) is ImageValue:
        return source
    if type(source) is RuntimeArtifactRef:
        resolved = ctx.resolve_path_value(source)
        artifact_kind = media_kind_from_source(f"source.{source.format}")
        if artifact_kind and media_kind_from_source(resolved) == artifact_kind:
            return source
    elif isinstance(source, (str, os.PathLike)):
        text = os.fspath(source).strip()
        if not text:
            raise NodeInputNotReadyError("Media Panel source input is empty.")
        if is_supported_media_source_reference(text):
            return text
        try:
            resolved = ctx.resolve_path_value(source)
        except (OSError, TypeError, ValueError):
            resolved = None
        if media_kind_from_source(resolved):
            return text
    suffixes = ", ".join(MEDIA_FILE_SUFFIXES)
    raise ValueError(
        "Media Panel source must be an Image value, a project media reference, "
        f"or a local/file/HTTP(S) media path using one of: {suffixes}."
    )


@builtin_node_type(
    type_id=MEDIA_PANEL_TYPE_ID,
    display_name="Media Panel",
    category_path=(MEDIA_PANEL_CATEGORY,),
    description="Displays image, PDF, or video media from an authored or connected source.",
    keywords=("media", "image", "pdf", "video", "preview"),
    ports=(
        PortSpec(
            "source",
            "in",
            "data",
            PATH_DATA_TYPE_ID,
            label="Source",
            required=False,
            uses_property_default=False,
            exposed=True,
            accepted_data_types=(STRING_DATA_TYPE_ID, IMAGE_DATA_TYPE_ID),
            data_access="item",
            description="Image, PDF, or video source to display.",
        ),
        PortSpec(
            "_surface_source",
            "out",
            "data",
            GRAPH_DATA_TYPE_ID,
            label="Surface Source",
            exposed=False,
            description="Validated media source retained for the panel surface.",
        ),
    ),
    properties=(
        PropertySpec(
            "source",
            "path",
            "",
            "Source",
            inline_editor="path",
            file_filter=MEDIA_FILES_FILTER,
        ),
        PropertySpec(
            "fit_mode",
            "enum",
            "contain",
            "Fit Mode",
            enum_values=("contain", "cover", "original"),
            inspector_visible=False,
        ),
        PropertySpec(
            "animation_playback_mode",
            "enum",
            "auto",
            "Animation Playback",
            enum_values=("auto", "play", "pause"),
            inspector_visible=False,
        ),
        PropertySpec(
            "lock_aspect_ratio",
            "bool",
            False,
            "Lock Aspect Ratio",
            inspector_visible=False,
        ),
        PropertySpec("show_title", "bool", True, "Show Title", inspector_visible=False),
        PropertySpec("show_frame", "bool", True, "Show Frame", inspector_visible=False),
        PropertySpec("crop_x", "float", 0.0, "Crop X", inspector_visible=False),
        PropertySpec("crop_y", "float", 0.0, "Crop Y", inspector_visible=False),
        PropertySpec("crop_w", "float", 1.0, "Crop Width", inspector_visible=False),
        PropertySpec("crop_h", "float", 1.0, "Crop Height", inspector_visible=False),
        PropertySpec("rotation_degrees", "int", 0, "Rotation", inspector_visible=False),
        PropertySpec(
            "mirror_horizontal",
            "bool",
            False,
            "Mirror Horizontal",
            inspector_visible=False,
        ),
        PropertySpec(
            "mirror_vertical", "bool", False, "Mirror Vertical", inspector_visible=False
        ),
        PropertySpec("page_number", "int", 1, "Page Number", inspector_visible=False),
        PropertySpec("auto_play", "bool", False, "Auto Play", inspector_visible=False),
        PropertySpec("loop", "bool", False, "Loop", inspector_visible=False),
        PropertySpec("muted", "bool", False, "Muted", inspector_visible=False),
        PropertySpec("volume", "float", 1.0, "Volume", inspector_visible=False),
        PropertySpec(
            "playback_rate",
            "float",
            1.0,
            "Playback Rate",
            inspector_visible=False,
        ),
        PropertySpec("position_ms", "int", 0, "Position", inspector_visible=False),
        PropertySpec(
            "timeline_bookmarks",
            "json",
            [],
            "Timeline Bookmarks",
            inspector_visible=False,
        ),
        PropertySpec(
            "clip_enabled",
            "bool",
            False,
            "Clip Range Enabled",
            inspector_visible=False,
        ),
        PropertySpec(
            "clip_start_ms", "int", 0, "Clip Start", inspector_visible=False
        ),
        PropertySpec(
            "clip_end_ms", "int", 0, "Clip End", inspector_visible=False
        ),
    ),
    collapsible=False,
    surface_family="media",
    surface_variant="media_panel",
    render_quality={"supported_quality_tiers": ["full", "proxy"]},
)
class MediaPanelNodePlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"_surface_source": _validated_media_source(ctx)})


MEDIA_PANEL_NODE_PLUGINS = (MediaPanelNodePlugin,)
MEDIA_PANEL_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin) for plugin in MEDIA_PANEL_NODE_PLUGINS
)


__all__ = [
    "MEDIA_PANEL_CATEGORY",
    "MEDIA_PANEL_NODE_DESCRIPTORS",
    "MEDIA_PANEL_NODE_PLUGINS",
    "MEDIA_PANEL_TYPE_ID",
    "MediaPanelNodePlugin",
]
