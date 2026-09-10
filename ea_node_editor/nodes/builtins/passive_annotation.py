from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.builtins.rich_text_properties import (
    rich_text_extra_slot_property_specs,
    rich_text_slot_property_specs,
)
from ea_node_editor.nodes.decorators import (
    plugin_descriptor,
    prop_str,
)
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult

PASSIVE_ANNOTATION_CATEGORY = "Annotation"

PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID = "passive.annotation.sticky_note"
PASSIVE_ANNOTATION_CALLOUT_TYPE_ID = "passive.annotation.callout"
PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID = "passive.annotation.section_header"
PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
PASSIVE_ANNOTATION_TEXT_TYPE_ID = "passive.annotation.text"
PASSIVE_ANNOTATION_GROUP_BACKDROP_SURFACE_FAMILY = "group_backdrop"


class _PassiveAnnotationNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID,
    display_name="Sticky Note",
    category_path=(PASSIVE_ANNOTATION_CATEGORY,),
    description="Annotation sticky note for contextual comments.",
    keywords=("sticky note", "annotation", "comment"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Sticky Note", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="sticky_note",
)
class PassiveAnnotationStickyNoteNodePlugin(_PassiveAnnotationNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_ANNOTATION_CALLOUT_TYPE_ID,
    display_name="Callout",
    category_path=(PASSIVE_ANNOTATION_CATEGORY,),
    description="Annotation callout for emphasized contextual notes.",
    keywords=("callout", "annotation", "note"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Callout", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="callout",
)
class PassiveAnnotationCalloutNodePlugin(_PassiveAnnotationNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID,
    display_name="Section Header",
    category_path=(PASSIVE_ANNOTATION_CATEGORY,),
    description="Annotation section header with optional subtitle copy.",
    keywords=("section", "header", "annotation"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Section Header", "Title"),
        prop_str("subtitle", "", "Subtitle"),
        *rich_text_extra_slot_property_specs("subtitle"),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="section_header",
)
class PassiveAnnotationSectionHeaderNodePlugin(_PassiveAnnotationNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_ANNOTATION_TEXT_TYPE_ID,
    display_name="Text",
    category_path=(PASSIVE_ANNOTATION_CATEGORY,),
    description="Bare text annotation with markdown source and whole-object text styling.",
    keywords=("text", "markdown", "annotation"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=rich_text_slot_property_specs(
        "text",
        content_default="Text",
        content_label="Text",
        default_format="markdown",
        inherited_style_defaults=False,
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="text",
)
class PassiveAnnotationTextNodePlugin(_PassiveAnnotationNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID,
    display_name="Group",
    category_path=("Utilities", "Canvas"),
    description="Group related nodes on the canvas with passive flow ports.",
    keywords=("group", "canvas", "backdrop"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(PropertySpec("title", "str", "", "Title", inspector_visible=False),),
    collapsible=True,
    runtime_behavior="passive",
    surface_family=PASSIVE_ANNOTATION_GROUP_BACKDROP_SURFACE_FAMILY,
    surface_variant="group_backdrop",
)
class PassiveAnnotationGroupBackdropNodePlugin(_PassiveAnnotationNodePlugin):
    pass


PASSIVE_ANNOTATION_NODE_PLUGINS = (
    PassiveAnnotationStickyNoteNodePlugin,
    PassiveAnnotationCalloutNodePlugin,
    PassiveAnnotationSectionHeaderNodePlugin,
    PassiveAnnotationTextNodePlugin,
    PassiveAnnotationGroupBackdropNodePlugin,
)
PASSIVE_ANNOTATION_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin) for plugin in PASSIVE_ANNOTATION_NODE_PLUGINS
)


__all__ = [
    "PASSIVE_ANNOTATION_CALLOUT_TYPE_ID",
    "PASSIVE_ANNOTATION_CATEGORY",
    "PASSIVE_ANNOTATION_GROUP_BACKDROP_SURFACE_FAMILY",
    "PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID",
    "PASSIVE_ANNOTATION_NODE_DESCRIPTORS",
    "PASSIVE_ANNOTATION_NODE_PLUGINS",
    "PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID",
    "PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID",
    "PASSIVE_ANNOTATION_TEXT_TYPE_ID",
    "PassiveAnnotationCalloutNodePlugin",
    "PassiveAnnotationGroupBackdropNodePlugin",
    "PassiveAnnotationSectionHeaderNodePlugin",
    "PassiveAnnotationStickyNoteNodePlugin",
    "PassiveAnnotationTextNodePlugin",
]
