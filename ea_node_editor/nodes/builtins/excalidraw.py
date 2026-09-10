from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import PropertySpec

EXCALIDRAW_CATEGORY = "Excalidraw"
EXCALIDRAW_BOARD_TYPE_ID = "excalidraw.board"
EXCALIDRAW_BOARD_SURFACE_FAMILY = "web"
EXCALIDRAW_BOARD_SURFACE_VARIANT = "excalidraw_board"
EXCALIDRAW_STATE_PROPERTY = "excalidraw_state"
EXCALIDRAW_PREVIEW_REF_PROPERTY = "excalidraw_preview_ref"


class _ExcalidrawNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=EXCALIDRAW_BOARD_TYPE_ID,
    display_name="Excalidraw Board",
    category_path=(EXCALIDRAW_CATEGORY,),
    description="Passive Excalidraw board backed by local web-surface state.",
    keywords=("excalidraw", "diagram", "whiteboard"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        PropertySpec(
            EXCALIDRAW_STATE_PROPERTY,
            "json",
            {},
            "Excalidraw State",
            inspector_visible=False,
        ),
        PropertySpec(
            EXCALIDRAW_PREVIEW_REF_PROPERTY,
            "json",
            "",
            "Preview Reference",
            inspector_visible=False,
        ),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family=EXCALIDRAW_BOARD_SURFACE_FAMILY,
    surface_variant=EXCALIDRAW_BOARD_SURFACE_VARIANT,
)
class ExcalidrawBoardNodePlugin(_ExcalidrawNodePlugin):
    pass


EXCALIDRAW_NODE_PLUGINS = (ExcalidrawBoardNodePlugin,)
EXCALIDRAW_NODE_DESCRIPTORS = tuple(plugin_descriptor(plugin) for plugin in EXCALIDRAW_NODE_PLUGINS)


__all__ = [
    "EXCALIDRAW_BOARD_SURFACE_FAMILY",
    "EXCALIDRAW_BOARD_SURFACE_VARIANT",
    "EXCALIDRAW_BOARD_TYPE_ID",
    "EXCALIDRAW_CATEGORY",
    "EXCALIDRAW_NODE_DESCRIPTORS",
    "EXCALIDRAW_NODE_PLUGINS",
    "EXCALIDRAW_PREVIEW_REF_PROPERTY",
    "EXCALIDRAW_STATE_PROPERTY",
    "ExcalidrawBoardNodePlugin",
]
