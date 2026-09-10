from __future__ import annotations

from ea_node_editor.nodes.builtins.rich_text_properties import rich_text_extra_slot_property_specs
from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.decorators import node_type, plugin_descriptor, prop_bool, prop_str
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult

PASSIVE_FLOWCHART_CATEGORY = "Flowchart"

PASSIVE_FLOWCHART_START_TYPE_ID = "passive.flowchart.start"
PASSIVE_FLOWCHART_END_TYPE_ID = "passive.flowchart.end"
PASSIVE_FLOWCHART_PROCESS_TYPE_ID = "passive.flowchart.process"
PASSIVE_FLOWCHART_DECISION_TYPE_ID = "passive.flowchart.decision"
PASSIVE_FLOWCHART_DOCUMENT_TYPE_ID = "passive.flowchart.document"
PASSIVE_FLOWCHART_CONNECTOR_TYPE_ID = "passive.flowchart.connector"
PASSIVE_FLOWCHART_INPUT_OUTPUT_TYPE_ID = "passive.flowchart.input_output"
PASSIVE_FLOWCHART_PREDEFINED_PROCESS_TYPE_ID = "passive.flowchart.predefined_process"
PASSIVE_FLOWCHART_DATABASE_TYPE_ID = "passive.flowchart.database"
PASSIVE_FLOWCHART_CARD_TYPE_ID = "passive.flowchart.card"
PASSIVE_FLOWCHART_CALLOUT_TYPE_ID = "passive.flowchart.callout"
PASSIVE_FLOWCHART_MULTI_DOCUMENT_TYPE_ID = "passive.flowchart.multi_document"
PASSIVE_FLOWCHART_TICK_TYPE_ID = "passive.flowchart.tick"
PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID = "passive.flowchart.timestamp"
PASSIVE_FLOWCHART_MESSAGE_TYPE_ID = "passive.flowchart.message"
PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID = "passive.flowchart.isometric_cube"
PASSIVE_FLOWCHART_CUBE_TYPE_ID = "passive.flowchart.cube"
PASSIVE_FLOWCHART_ACTOR_TYPE_ID = "passive.flowchart.actor"
PASSIVE_FLOWCHART_STAR_TYPE_ID = "passive.flowchart.star"
PASSIVE_FLOWCHART_X_TYPE_ID = "passive.flowchart.x"
PASSIVE_FLOWCHART_TIMESTAMP_BODY_PLACEHOLDER = "%date{ddd mmm dd yyyy HH:MM:ss}%"


class _PassiveFlowchartNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


def _flowchart_title_property(
    default_title: str,
    default_body: str | None = None,
    *,
    live_timestamp: bool = False,
    extra_body_fields: tuple[tuple[str, str], ...] = (),
):
    body_default = default_title if default_body is None else default_body
    properties = [
        prop_str("title", default_title, "Title"),
        prop_str("body", body_default, "Body", inspector_editor="textarea"),
    ]
    if not live_timestamp:
        properties.extend(rich_text_extra_slot_property_specs("body"))
    for key, label in extra_body_fields:
        properties.append(prop_str(key, "", label, inspector_editor="textarea"))
        properties.extend(rich_text_extra_slot_property_specs(key))
    if live_timestamp:
        properties.append(prop_bool("live", False, "Live"))
    return tuple(properties)


def _passive_flowchart_node_type(
    *,
    type_id: str,
    display_name: str,
    description: str,
    keywords: tuple[str, ...],
    surface_variant: str,
    body_default: str | None = None,
    live_timestamp: bool = False,
    extra_body_fields: tuple[tuple[str, str], ...] = (),
):
    return node_type(
        type_id=type_id,
        display_name=display_name,
        category_path=(PASSIVE_FLOWCHART_CATEGORY,),
        icon="",
        ports=CARDINAL_PASSIVE_FLOW_PORTS,
        properties=_flowchart_title_property(
            display_name,
            body_default,
            live_timestamp=live_timestamp,
            extra_body_fields=extra_body_fields,
        ),
        collapsible=False,
        description=description,
        keywords=keywords,
        runtime_behavior="passive",
        surface_family="flowchart",
        surface_variant=surface_variant,
    )


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_START_TYPE_ID,
    display_name="Start",
    description="Marks the visual starting point of a flowchart.",
    keywords=("start", "flowchart", "terminator"),
    surface_variant="start",
)
class PassiveFlowchartStartNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_END_TYPE_ID,
    display_name="End",
    description="Marks a visual endpoint or termination in a flowchart.",
    keywords=("end", "flowchart", "terminator"),
    surface_variant="end",
)
class PassiveFlowchartEndNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_PROCESS_TYPE_ID,
    display_name="Process",
    description="Represents an action or processing step in a flowchart.",
    keywords=("process", "flowchart", "step"),
    surface_variant="process",
)
class PassiveFlowchartProcessNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_DECISION_TYPE_ID,
    display_name="Decision",
    description="Represents a decision that branches a flowchart into alternative paths.",
    keywords=("decision", "branch", "flowchart"),
    surface_variant="decision",
)
class PassiveFlowchartDecisionNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_DOCUMENT_TYPE_ID,
    display_name="Document",
    description="Represents a document created, read, or used by a flowchart step.",
    keywords=("document", "flowchart", "artifact"),
    surface_variant="document",
)
class PassiveFlowchartDocumentNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_CONNECTOR_TYPE_ID,
    display_name="Connector",
    description="Links separated sections or continuation points of a flowchart.",
    keywords=("connector", "continuation", "flowchart"),
    surface_variant="connector",
)
class PassiveFlowchartConnectorNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_INPUT_OUTPUT_TYPE_ID,
    display_name="Input / Output",
    description="Represents data entering or leaving a flowchart process.",
    keywords=("input", "output", "flowchart"),
    surface_variant="input_output",
)
class PassiveFlowchartInputOutputNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_PREDEFINED_PROCESS_TYPE_ID,
    display_name="Predefined Process",
    description="Represents a named process defined in another flowchart or procedure.",
    keywords=("predefined process", "subprocess", "flowchart"),
    surface_variant="predefined_process",
)
class PassiveFlowchartPredefinedProcessNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_DATABASE_TYPE_ID,
    display_name="Database",
    description="Represents a database or persistent data store in a flowchart.",
    keywords=("database", "storage", "flowchart"),
    surface_variant="database",
)
class PassiveFlowchartDatabaseNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_CARD_TYPE_ID,
    display_name="Card",
    description="Flowchart card or punched-card artifact.",
    keywords=("card", "record", "flowchart"),
    surface_variant="card",
    body_default="",
)
class PassiveFlowchartCardNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_CALLOUT_TYPE_ID,
    display_name="Callout",
    description="Adds a speech-bubble callout for explanatory flowchart text.",
    keywords=("callout", "speech bubble", "flowchart"),
    surface_variant="callout",
    body_default="",
)
class PassiveFlowchartCalloutNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_MULTI_DOCUMENT_TYPE_ID,
    display_name="Multi-Document",
    description="Flowchart stacked multi-document artifact.",
    keywords=("documents", "stack", "flowchart"),
    surface_variant="multi_document",
    body_default="",
)
class PassiveFlowchartMultiDocumentNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_TICK_TYPE_ID,
    display_name="Tick",
    description="Marks a completed, accepted, or verified point in a flowchart.",
    keywords=("tick", "checkmark", "complete"),
    surface_variant="tick",
    body_default="",
)
class PassiveFlowchartTickNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID,
    display_name="Timestamp",
    description="Displays a fixed or live timestamp inside a flowchart.",
    keywords=("timestamp", "date", "time"),
    surface_variant="timestamp",
    body_default=PASSIVE_FLOWCHART_TIMESTAMP_BODY_PLACEHOLDER,
    live_timestamp=True,
)
class PassiveFlowchartTimestampNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_MESSAGE_TYPE_ID,
    display_name="Message",
    description="Flowchart message or envelope artifact.",
    keywords=("message", "envelope", "flowchart"),
    surface_variant="message",
    body_default="",
)
class PassiveFlowchartMessageNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID,
    display_name="Isometric Cube",
    description="Represents a three-faced isometric object with optional face labels.",
    keywords=("isometric", "cube", "flowchart"),
    surface_variant="isometric_cube",
    body_default="",
    extra_body_fields=(
        ("body_top", "Top Face"),
        ("body_right", "Right Face"),
    ),
)
class PassiveFlowchartIsometricCubeNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_CUBE_TYPE_ID,
    display_name="Cube",
    description="Represents a cube-shaped system, package, or object in a flowchart.",
    keywords=("cube", "object", "flowchart"),
    surface_variant="cube",
    body_default="",
)
class PassiveFlowchartCubeNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_ACTOR_TYPE_ID,
    display_name="Actor",
    description="Represents a person, role, or external actor in a flowchart.",
    keywords=("actor", "person", "role"),
    surface_variant="actor",
    body_default="",
)
class PassiveFlowchartActorNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_STAR_TYPE_ID,
    display_name="Star",
    description="Flowchart five-pointed star marker.",
    keywords=("star", "marker", "flowchart"),
    surface_variant="star",
    body_default="",
)
class PassiveFlowchartStarNodePlugin(_PassiveFlowchartNodePlugin):
    pass


@_passive_flowchart_node_type(
    type_id=PASSIVE_FLOWCHART_X_TYPE_ID,
    display_name="X",
    description="Marks a rejected, blocked, or cancelled point in a flowchart.",
    keywords=("x", "cross", "blocked"),
    surface_variant="x",
    body_default="",
)
class PassiveFlowchartXNodePlugin(_PassiveFlowchartNodePlugin):
    pass


PASSIVE_FLOWCHART_NODE_PLUGINS = (
    PassiveFlowchartStartNodePlugin,
    PassiveFlowchartEndNodePlugin,
    PassiveFlowchartProcessNodePlugin,
    PassiveFlowchartDecisionNodePlugin,
    PassiveFlowchartDocumentNodePlugin,
    PassiveFlowchartConnectorNodePlugin,
    PassiveFlowchartInputOutputNodePlugin,
    PassiveFlowchartPredefinedProcessNodePlugin,
    PassiveFlowchartDatabaseNodePlugin,
    PassiveFlowchartCardNodePlugin,
    PassiveFlowchartCalloutNodePlugin,
    PassiveFlowchartMultiDocumentNodePlugin,
    PassiveFlowchartTickNodePlugin,
    PassiveFlowchartTimestampNodePlugin,
    PassiveFlowchartMessageNodePlugin,
    PassiveFlowchartIsometricCubeNodePlugin,
    PassiveFlowchartCubeNodePlugin,
    PassiveFlowchartActorNodePlugin,
    PassiveFlowchartStarNodePlugin,
    PassiveFlowchartXNodePlugin,
)
PASSIVE_FLOWCHART_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin)
    for plugin in PASSIVE_FLOWCHART_NODE_PLUGINS
)


__all__ = [
    "PASSIVE_FLOWCHART_ACTOR_TYPE_ID",
    "PASSIVE_FLOWCHART_CALLOUT_TYPE_ID",
    "PASSIVE_FLOWCHART_CARD_TYPE_ID",
    "PASSIVE_FLOWCHART_CATEGORY",
    "PASSIVE_FLOWCHART_CONNECTOR_TYPE_ID",
    "PASSIVE_FLOWCHART_CUBE_TYPE_ID",
    "PASSIVE_FLOWCHART_DATABASE_TYPE_ID",
    "PASSIVE_FLOWCHART_DECISION_TYPE_ID",
    "PASSIVE_FLOWCHART_DOCUMENT_TYPE_ID",
    "PASSIVE_FLOWCHART_END_TYPE_ID",
    "PASSIVE_FLOWCHART_INPUT_OUTPUT_TYPE_ID",
    "PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID",
    "PASSIVE_FLOWCHART_MESSAGE_TYPE_ID",
    "PASSIVE_FLOWCHART_MULTI_DOCUMENT_TYPE_ID",
    "PASSIVE_FLOWCHART_NODE_DESCRIPTORS",
    "PASSIVE_FLOWCHART_NODE_PLUGINS",
    "PASSIVE_FLOWCHART_PREDEFINED_PROCESS_TYPE_ID",
    "PASSIVE_FLOWCHART_PROCESS_TYPE_ID",
    "PASSIVE_FLOWCHART_STAR_TYPE_ID",
    "PASSIVE_FLOWCHART_START_TYPE_ID",
    "PASSIVE_FLOWCHART_TICK_TYPE_ID",
    "PASSIVE_FLOWCHART_TIMESTAMP_BODY_PLACEHOLDER",
    "PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID",
    "PASSIVE_FLOWCHART_X_TYPE_ID",
    "PassiveFlowchartActorNodePlugin",
    "PassiveFlowchartCalloutNodePlugin",
    "PassiveFlowchartCardNodePlugin",
    "PassiveFlowchartConnectorNodePlugin",
    "PassiveFlowchartCubeNodePlugin",
    "PassiveFlowchartDatabaseNodePlugin",
    "PassiveFlowchartDecisionNodePlugin",
    "PassiveFlowchartDocumentNodePlugin",
    "PassiveFlowchartEndNodePlugin",
    "PassiveFlowchartInputOutputNodePlugin",
    "PassiveFlowchartIsometricCubeNodePlugin",
    "PassiveFlowchartMessageNodePlugin",
    "PassiveFlowchartMultiDocumentNodePlugin",
    "PassiveFlowchartPredefinedProcessNodePlugin",
    "PassiveFlowchartProcessNodePlugin",
    "PassiveFlowchartStarNodePlugin",
    "PassiveFlowchartStartNodePlugin",
    "PassiveFlowchartTickNodePlugin",
    "PassiveFlowchartTimestampNodePlugin",
    "PassiveFlowchartXNodePlugin",
]
