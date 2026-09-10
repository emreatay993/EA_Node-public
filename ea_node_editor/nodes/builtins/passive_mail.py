# Purpose: Declare the retained passive Mail Panel node.
# Map: feature_routes/media_image_video_pdf_refocus.md
# Tests: tests/test_mail_preview_provider.py

from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.file_dialog_filters import MAIL_FILES_FILTER
from ea_node_editor.nodes.node_specs import PropertySpec

PASSIVE_MEDIA_CATEGORY = "Media"
PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID = "passive.media.mail_panel"


class _PassiveMediaNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
    display_name="Mail Panel",
    category_path=(PASSIVE_MEDIA_CATEGORY,),
    description="Passive local-mail panel with rich HTML preview.",
    keywords=("mail", "email", "preview"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        PropertySpec(
            "source_path",
            "path",
            "",
            "Mail Source",
            inline_editor="path",
            file_filter=MAIL_FILES_FILTER,
        ),
        PropertySpec("show_title", "bool", True, "Show Title", inspector_visible=False),
        PropertySpec("show_frame", "bool", True, "Show Frame", inspector_visible=False),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="media",
    surface_variant="mail_panel",
    render_quality={
        "supported_quality_tiers": ["full", "proxy"],
    },
)
class PassiveMediaMailPanelNodePlugin(_PassiveMediaNodePlugin):
    pass


PASSIVE_MAIL_NODE_PLUGINS = (PassiveMediaMailPanelNodePlugin,)
PASSIVE_MAIL_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin) for plugin in PASSIVE_MAIL_NODE_PLUGINS
)


__all__ = [
    "PASSIVE_MEDIA_CATEGORY",
    "PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID",
    "PASSIVE_MAIL_NODE_DESCRIPTORS",
    "PASSIVE_MAIL_NODE_PLUGINS",
    "PassiveMediaMailPanelNodePlugin",
]
