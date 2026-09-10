from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from collections.abc import Mapping
from typing import Any

from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.file_dialog_filters import WEB_PAGE_FILES_FILTER
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.web_host.navigation_policy import normalize_web_page_browser_state

WEB_PAGE_VIEWER_CATEGORY = "Web"
WEB_PAGE_VIEWER_TYPE_ID = "web.page_viewer"
WEB_PAGE_VIEWER_SURFACE_FAMILY = "web"
WEB_PAGE_VIEWER_SURFACE_VARIANT = "page_viewer"
WEB_PAGE_VIEWER_START_LOCATION_PROPERTY = "start_location"
WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY = "display_mode"
WEB_PAGE_VIEWER_SHOW_TITLE_PROPERTY = "show_title"
WEB_PAGE_VIEWER_SHOW_FRAME_PROPERTY = "show_frame"
WEB_PAGE_VIEWER_PERSIST_BROWSER_STATE_PROPERTY = "persist_browser_state"
WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY = "browser_state"
WEB_PAGE_VIEWER_PREVIEW_REF_PROPERTY = "preview_ref"
WEB_PAGE_VIEWER_DISPLAY_MODE_RESPONSIVE = "responsive"
WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH = "fit_width"
WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE = "fit_page"
WEB_PAGE_VIEWER_DISPLAY_MODES = (
    WEB_PAGE_VIEWER_DISPLAY_MODE_RESPONSIVE,
    WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
    WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE,
)


def web_page_viewer_browser_state_persistence_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return True


def normalize_web_page_viewer_browser_state(
    value: Mapping[str, Any] | None,
    *,
    fallback_location: str = "",
    require_location: bool = False,
) -> dict[str, Any]:
    return normalize_web_page_browser_state(
        value,
        fallback_location=fallback_location,
        require_location=require_location,
    )


def normalize_web_page_viewer_display_mode(value: Any) -> str:
    normalized = str(value or WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH).strip().lower()
    return normalized if normalized in WEB_PAGE_VIEWER_DISPLAY_MODES else WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH


def normalize_web_page_viewer_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        WEB_PAGE_VIEWER_START_LOCATION_PROPERTY,
        WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY,
        WEB_PAGE_VIEWER_SHOW_TITLE_PROPERTY,
        WEB_PAGE_VIEWER_SHOW_FRAME_PROPERTY,
        WEB_PAGE_VIEWER_PERSIST_BROWSER_STATE_PROPERTY,
        WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY,
        WEB_PAGE_VIEWER_PREVIEW_REF_PROPERTY,
    }
    normalized = {
        str(key): item
        for key, item in properties.items()
        if str(key) in allowed_keys
    }
    normalized[WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY] = normalize_web_page_viewer_display_mode(
        normalized.get(WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY)
    )
    if not web_page_viewer_browser_state_persistence_enabled(
        normalized.get(WEB_PAGE_VIEWER_PERSIST_BROWSER_STATE_PROPERTY, True)
    ):
        normalized[WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY] = {}
        return normalized
    normalized[WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY] = normalize_web_page_viewer_browser_state(
        normalized.get(WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY, {})
    )
    return normalized


class _WebPageViewerNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=WEB_PAGE_VIEWER_TYPE_ID,
    display_name="Web Page Viewer",
    category_path=(WEB_PAGE_VIEWER_CATEGORY,),
    description="Passive Chromium-backed page viewer for URLs and local web documents.",
    keywords=("web", "browser", "website"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        PropertySpec(
            WEB_PAGE_VIEWER_START_LOCATION_PROPERTY,
            "str",
            "",
            "Start Location",
            inspector_editor="path",
            group="Source",
            file_filter=WEB_PAGE_FILES_FILTER,
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY,
            "enum",
            WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH,
            "Display Mode",
            enum_values=WEB_PAGE_VIEWER_DISPLAY_MODES,
            inspector_editor="enum",
            group="Display",
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_SHOW_TITLE_PROPERTY,
            "bool",
            True,
            "Show Title",
            inspector_visible=False,
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_SHOW_FRAME_PROPERTY,
            "bool",
            True,
            "Show Frame",
            inspector_visible=False,
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_PERSIST_BROWSER_STATE_PROPERTY,
            "bool",
            True,
            "Persist Browser State",
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY,
            "json",
            {},
            "Browser State",
            inspector_visible=False,
        ),
        PropertySpec(
            WEB_PAGE_VIEWER_PREVIEW_REF_PROPERTY,
            "json",
            {},
            "Preview Reference",
            inspector_visible=False,
        ),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family=WEB_PAGE_VIEWER_SURFACE_FAMILY,
    surface_variant=WEB_PAGE_VIEWER_SURFACE_VARIANT,
    render_quality={
        "supported_quality_tiers": ["full", "proxy"],
    },
)
class WebPageViewerNodePlugin(_WebPageViewerNodePlugin):
    pass


WEB_PAGE_VIEWER_NODE_PLUGINS = (WebPageViewerNodePlugin,)
WEB_PAGE_VIEWER_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin)
    for plugin in WEB_PAGE_VIEWER_NODE_PLUGINS
)


__all__ = [
    "WEB_PAGE_VIEWER_CATEGORY",
    "WEB_PAGE_VIEWER_BROWSER_STATE_PROPERTY",
    "WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_PAGE",
    "WEB_PAGE_VIEWER_DISPLAY_MODE_FIT_WIDTH",
    "WEB_PAGE_VIEWER_DISPLAY_MODE_PROPERTY",
    "WEB_PAGE_VIEWER_DISPLAY_MODE_RESPONSIVE",
    "WEB_PAGE_VIEWER_DISPLAY_MODES",
    "WEB_PAGE_VIEWER_NODE_DESCRIPTORS",
    "WEB_PAGE_VIEWER_NODE_PLUGINS",
    "WEB_PAGE_VIEWER_PERSIST_BROWSER_STATE_PROPERTY",
    "WEB_PAGE_VIEWER_PREVIEW_REF_PROPERTY",
    "WEB_PAGE_VIEWER_SHOW_FRAME_PROPERTY",
    "WEB_PAGE_VIEWER_SHOW_TITLE_PROPERTY",
    "WEB_PAGE_VIEWER_START_LOCATION_PROPERTY",
    "WEB_PAGE_VIEWER_SURFACE_FAMILY",
    "WEB_PAGE_VIEWER_SURFACE_VARIANT",
    "WEB_PAGE_VIEWER_TYPE_ID",
    "WebPageViewerNodePlugin",
    "normalize_web_page_viewer_display_mode",
    "normalize_web_page_viewer_browser_state",
    "normalize_web_page_viewer_properties",
    "web_page_viewer_browser_state_persistence_enabled",
]
