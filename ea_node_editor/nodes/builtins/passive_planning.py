from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.builtins.rich_text_properties import rich_text_extra_slot_property_specs
from ea_node_editor.nodes.decorators import plugin_descriptor, prop_enum, prop_str
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult

PASSIVE_PLANNING_CATEGORY = "Planning"

PASSIVE_PLANNING_TASK_CARD_TYPE_ID = "passive.planning.task_card"
PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID = "passive.planning.milestone_card"
PASSIVE_PLANNING_RISK_CARD_TYPE_ID = "passive.planning.risk_card"
PASSIVE_PLANNING_DECISION_CARD_TYPE_ID = "passive.planning.decision_card"


class _PassivePlanningNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=PASSIVE_PLANNING_TASK_CARD_TYPE_ID,
    display_name="Task Card",
    category_path=(PASSIVE_PLANNING_CATEGORY,),
    description="Planning task card with owner, due date, and status fields.",
    keywords=("task", "planning", "status"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Task", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
        prop_str("owner", "", "Owner"),
        prop_str("due_date", "", "Due Date"),
        prop_enum(
            "status",
            "todo",
            "Status",
            values=("todo", "in_progress", "blocked", "done"),
        ),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="planning",
    surface_variant="task_card",
)
class PassivePlanningTaskCardNodePlugin(_PassivePlanningNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID,
    display_name="Milestone Card",
    category_path=(PASSIVE_PLANNING_CATEGORY,),
    description="Planning milestone card with target date and delivery status.",
    keywords=("milestone", "planning", "delivery"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Milestone", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
        prop_str("target_date", "", "Target Date"),
        prop_enum(
            "status",
            "planned",
            "Status",
            values=("planned", "at_risk", "done"),
        ),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="planning",
    surface_variant="milestone_card",
)
class PassivePlanningMilestoneCardNodePlugin(_PassivePlanningNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_PLANNING_RISK_CARD_TYPE_ID,
    display_name="Risk Card",
    category_path=(PASSIVE_PLANNING_CATEGORY,),
    description="Planning risk card with severity and mitigation notes.",
    keywords=("risk", "planning", "mitigation"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Risk", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
        prop_enum(
            "severity",
            "medium",
            "Severity",
            values=("low", "medium", "high", "critical"),
        ),
        prop_str("mitigation", "", "Mitigation", inspector_editor="textarea"),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="planning",
    surface_variant="risk_card",
)
class PassivePlanningRiskCardNodePlugin(_PassivePlanningNodePlugin):
    pass


@builtin_node_type(
    type_id=PASSIVE_PLANNING_DECISION_CARD_TYPE_ID,
    display_name="Decision Card",
    category_path=(PASSIVE_PLANNING_CATEGORY,),
    description="Planning decision card with state tracking and outcome notes.",
    keywords=("decision", "planning", "outcome"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        prop_str("title", "Decision", "Title"),
        prop_str("body", "", "Body", inspector_editor="textarea"),
        *rich_text_extra_slot_property_specs("body"),
        prop_enum(
            "state",
            "open",
            "State",
            values=("open", "decided", "deferred"),
        ),
        prop_str("outcome", "", "Outcome", inspector_editor="textarea"),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family="planning",
    surface_variant="decision_card",
)
class PassivePlanningDecisionCardNodePlugin(_PassivePlanningNodePlugin):
    pass


PASSIVE_PLANNING_NODE_PLUGINS = (
    PassivePlanningTaskCardNodePlugin,
    PassivePlanningMilestoneCardNodePlugin,
    PassivePlanningRiskCardNodePlugin,
    PassivePlanningDecisionCardNodePlugin,
)
PASSIVE_PLANNING_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin)
    for plugin in PASSIVE_PLANNING_NODE_PLUGINS
)


__all__ = [
    "PASSIVE_PLANNING_CATEGORY",
    "PASSIVE_PLANNING_DECISION_CARD_TYPE_ID",
    "PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID",
    "PASSIVE_PLANNING_NODE_DESCRIPTORS",
    "PASSIVE_PLANNING_NODE_PLUGINS",
    "PASSIVE_PLANNING_RISK_CARD_TYPE_ID",
    "PASSIVE_PLANNING_TASK_CARD_TYPE_ID",
    "PassivePlanningDecisionCardNodePlugin",
    "PassivePlanningMilestoneCardNodePlugin",
    "PassivePlanningRiskCardNodePlugin",
    "PassivePlanningTaskCardNodePlugin",
]
