from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
    PropertyConditionSpec,
    ReadinessRequirementSpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import DataTree, Interval1D
from ea_node_editor.ui.support.port_flow_state import (
    PORT_FLOW_STATES,
    resolve_port_flow_state,
    resolve_runtime_port_flow_states,
)
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge


def _solution_fact(
    node_id: str,
    record_id: str = "run",
    *,
    freshness: SolutionFreshness = SolutionFreshness.CURRENT,
) -> NodeSolutionFact:
    return NodeSolutionFact(
        project_id="project",
        workspace_id="workspace",
        node_id=node_id,
        freshness=freshness,
        revision=1,
        retained_record_id=record_id,
        retained_solution_key="a" * 64,
        residency=SolutionResidency.SESSION,
        expiration_reason_code=(
            "graph_changed" if freshness is SolutionFreshness.EXPIRED else ""
        ),
        expiration_root_node_ids=(
            (node_id,) if freshness is SolutionFreshness.EXPIRED else ()
        ),
        last_disposition=SolutionDisposition.RECOMPUTED,
    )


@pytest.mark.parametrize(
    ("direction", "kind", "connected", "required", "inactive", "expected"),
    (
        # Connected always flows, regardless of direction/kind/requiredness.
        ("in", "data", True, True, False, "flowing"),
        ("in", "data", True, False, False, "flowing"),
        ("out", "data", True, False, False, "flowing"),
        ("in", "flow", True, False, False, "flowing"),
        # Unconnected data inputs without defaults wait or idle.
        ("in", "data", False, True, False, "waiting"),
        ("in", "data", False, False, False, "idle"),
        # Unconnected outputs idle.
        ("out", "data", False, False, False, "idle"),
        ("out", "data", False, True, False, "idle"),
        # Passive flow ports have no default/waiting semantics.
        ("in", "flow", False, True, False, "idle"),
        ("out", "flow", False, False, False, "idle"),
        # Inactive (driven-by-input / unavailable) ports stay quiet.
        ("in", "data", False, True, True, "idle"),
        ("in", "data", False, False, True, "idle"),
        # Kind/direction normalization.
        ("IN", "Data", False, True, False, "waiting"),
        ("OUT ", " FLOW", False, False, False, "idle"),
    ),
)
def test_resolve_port_flow_state_table(
    direction: str,
    kind: str,
    connected: bool,
    required: bool,
    inactive: bool,
    expected: str,
) -> None:
    state = resolve_port_flow_state(
        direction=direction,
        kind=kind,
        connected=connected,
        required=required,
        inactive=inactive,
    )
    assert state == expected
    assert state in PORT_FLOW_STATES


def test_reserved_invalid_states_are_declared_but_not_produced() -> None:
    # The topology fallback produces the first four. Runtime scene facts can
    # produce "invalid" from a declared type mismatch; "invalid_muted" stays
    # reserved until edges can be deactivated.
    assert PORT_FLOW_STATES == (
        "flowing",
        "default",
        "waiting",
        "idle",
        "invalid",
        "invalid_muted",
    )


def test_required_input_with_property_default_uses_default_flow_state() -> None:
    assert resolve_port_flow_state(
        direction="in",
        kind="data",
        connected=False,
        required=True,
        inactive=False,
        has_default=True,
    ) == "default"


def test_runtime_flow_states_use_output_presence_and_edge_type_warnings() -> None:
    nodes = [
        {
            "node_id": "source",
            "ports": [
                {
                    "key": "out",
                    "direction": "out",
                    "kind": "data",
                    "flow_state": "flowing",
                },
                {
                    "key": "empty_out",
                    "direction": "out",
                    "kind": "data",
                    "flow_state": "flowing",
                },
                {
                    "key": "failed_out",
                    "direction": "out",
                    "kind": "data",
                    "flow_state": "flowing",
                },
                {
                    "key": "inactive_out",
                    "direction": "out",
                    "kind": "data",
                    "inactive": True,
                    "flow_state": "flowing",
                },
            ],
        },
        {
            "node_id": "sink",
            "ports": [
                {
                    "key": "data_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                    "flow_state": "flowing",
                },
                {
                    "key": "waiting_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                    "flow_state": "flowing",
                },
                {
                    "key": "default_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": True,
                    "flow_state": "flowing",
                },
                {
                    "key": "unwired_default_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                    "default_property": {"key": "unwired_default_in", "value": "fallback"},
                    "flow_state": "flowing",
                },
                {
                    "key": "invalid_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                    "flow_state": "flowing",
                },
                {
                    "key": "failed_in",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                    "flow_state": "flowing",
                },
            ],
        },
    ]
    edges = [
        {
            "source_node_id": "source",
            "source_port_key": "out",
            "target_node_id": "sink",
            "target_port_key": "data_in",
        },
        {
            "source_node_id": "source",
            "source_port_key": "empty_out",
            "target_node_id": "sink",
            "target_port_key": "waiting_in",
        },
        {
            "source_node_id": "source",
            "source_port_key": "empty_out",
            "target_node_id": "sink",
            "target_port_key": "default_in",
        },
        {
            "source_node_id": "source",
            "source_port_key": "out",
            "target_node_id": "sink",
            "target_port_key": "invalid_in",
            "data_type_warning": True,
        },
        {
            "source_node_id": "source",
            "source_port_key": "failed_out",
            "target_node_id": "sink",
            "target_port_key": "failed_in",
        },
    ]
    records = {
        "source": {
            "old": {
                "observed_at_epoch_ms": 1.0,
                "outputs": {
                    "out": SettledPortResult(
                        status="value", value=DataTree.from_item("stale")
                    ),
                    "empty_out": SettledPortResult(status="empty"),
                },
                "stale": True,
            },
            "current": {
                "record_id": "current",
                "observed_at_epoch_ms": 2.0,
                "outputs": {
                    "out": SettledPortResult(
                        status="value", value=DataTree.from_item(None)
                    ),
                    "empty_out": SettledPortResult(status="empty"),
                    "failed_out": SettledPortResult(
                        status="failed",
                        errors=(
                            RootExecutionError(node_id="source", error="boom"),
                        ),
                    ),
                    "inactive_out": SettledPortResult(
                        status="value", value=DataTree.from_item("inactive")
                    ),
                },
                "stale": False,
            },
        }
    }

    states = resolve_runtime_port_flow_states(
        node_payloads=nodes,
        edge_payloads=edges,
        output_records_by_node=records,
        solution_facts_by_node={"source": _solution_fact("source", "current")},
    )

    assert states["source"] == {
        "out": "flowing",
        "empty_out": "idle",
        "failed_out": "idle",
        "inactive_out": "idle",
    }
    assert states["sink"] == {
        "data_in": "flowing",
        "waiting_in": "waiting",
        "default_in": "idle",
        "unwired_default_in": "default",
        "invalid_in": "invalid",
        "failed_in": "waiting",
    }


def test_runtime_flow_states_do_not_fall_back_past_the_latest_stale_record() -> None:
    nodes = [
        {
            "node_id": "source",
            "ports": [{"key": "out", "direction": "out", "kind": "data"}],
        }
    ]
    records = {
        "source": {
            "older": {
                "observed_at_epoch_ms": 1.0,
                "outputs": {
                    "out": SettledPortResult(
                        status="value", value=DataTree.from_item("old")
                    )
                },
                "stale": False,
            },
            "latest": {
                "observed_at_epoch_ms": 2.0,
                "outputs": {
                    "out": SettledPortResult(
                        status="value", value=DataTree.from_item("stale")
                    )
                },
                "stale": True,
            },
        }
    }

    states = resolve_runtime_port_flow_states(
        node_payloads=nodes,
        edge_payloads=[],
        output_records_by_node=records,
    )

    assert states == {"source": {"out": "idle"}}


def test_runtime_flow_states_treat_empty_trees_and_disabled_edges_as_no_data() -> None:
    nodes = [
        {
            "node_id": "source",
            "ports": [
                {
                    "key": "empty_tree",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "tree",
                },
                {
                    "key": "value",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "item",
                },
                {
                    "key": "flow_out",
                    "direction": "out",
                    "kind": "flow",
                    "connected": True,
                },
            ],
        },
        {
            "node_id": "sink",
            "ports": [
                {
                    "key": "required",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                },
                {
                    "key": "optional",
                    "direction": "in",
                    "kind": "data",
                    "optional": True,
                },
                {
                    "key": "invalid",
                    "direction": "in",
                    "kind": "data",
                    "optional": False,
                },
                {
                    "key": "flow_in",
                    "direction": "in",
                    "kind": "flow",
                    "connected": True,
                },
            ],
        },
    ]
    edges = [
        {
            "source_node_id": "source",
            "source_port_key": "empty_tree",
            "target_node_id": "sink",
            "target_port_key": "required",
            "enabled": True,
        },
        {
            "source_node_id": "source",
            "source_port_key": "value",
            "target_node_id": "sink",
            "target_port_key": "optional",
            "enabled": False,
        },
        {
            "source_node_id": "source",
            "source_port_key": "value",
            "target_node_id": "sink",
            "target_port_key": "invalid",
            "enabled": False,
            "data_type_warning": True,
        },
        {
            "source_node_id": "source",
            "source_port_key": "flow_out",
            "target_node_id": "sink",
            "target_port_key": "flow_in",
            "enabled": True,
        },
    ]
    records = {
        "source": {
            "current": {
                "record_id": "current",
                "observed_at_epoch_ms": 1.0,
                "outputs": {
                    "empty_tree": SettledPortResult(status="empty"),
                    "value": SettledPortResult(
                        status="value", value=DataTree.from_item(None)
                    ),
                },
                "stale": False,
            }
        }
    }

    states = resolve_runtime_port_flow_states(
        node_payloads=nodes,
        edge_payloads=edges,
        output_records_by_node=records,
        solution_facts_by_node={"source": _solution_fact("source", "current")},
    )

    assert states["source"] == {
        "empty_tree": "idle",
        "value": "flowing",
        "flow_out": "flowing",
    }
    assert states["sink"] == {
        "required": "waiting",
        "optional": "idle",
        "invalid": "waiting",
        "flow_in": "flowing",
    }

    for edge in edges:
        if edge["target_port_key"] in {"optional", "invalid"}:
            edge["enabled"] = True

    restored_states = resolve_runtime_port_flow_states(
        node_payloads=nodes,
        edge_payloads=edges,
        output_records_by_node=records,
        solution_facts_by_node={"source": _solution_fact("source", "current")},
    )

    assert restored_states["sink"] == {
        "required": "waiting",
        "optional": "flowing",
        "invalid": "invalid",
        "flow_in": "flowing",
    }


class _FlowSceneStub(QObject):
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    workspace_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.workspace_id = "workspace"
        self.nodes_model = [
            {
                "node_id": "source",
                "ports": [{"key": "out", "direction": "out", "kind": "data"}],
            },
            {
                "node_id": "sink",
                "ports": [
                    {
                        "key": "in",
                        "direction": "in",
                        "kind": "data",
                        "optional": False,
                    }
                ],
            },
        ]
        self.backdrop_nodes_model = []
        self.minimap_nodes_model = []
        self.edges_model = [
            {
                "source_node_id": "source",
                "source_port_key": "out",
                "target_node_id": "sink",
                "target_port_key": "in",
            }
        ]
        self.node_delta_payload = {}
        self.edge_delta_payload = {}
        self.workspace_scene_bounds_payload = {}
        self.selected_node_ids = []
        self.selected_node_lookup = {}
        self.hide_optional_ports = False


class _FlowExecutionStub(QObject):
    run_failure_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.run_state = SimpleNamespace(
            cached_node_output_records_by_workspace_id={
                "workspace": {
                    "source": {
                        "run": {
                            "record_id": "run",
                            "observed_at_epoch_ms": 1.0,
                            "outputs": {
                                "out": SettledPortResult(
                                    status="value",
                                    value=DataTree.from_item("__raw_runtime_value__"),
                                )
                            },
                        }
                    }
                }
            },
            node_solution_facts_by_workspace_id={
                "workspace": {"source": _solution_fact("source")}
            },
            node_output_run_counts_by_workspace_id={"workspace": {"source": 1}},
        )


def test_canvas_execution_facts_project_runtime_port_states() -> None:
    bridge = GraphCanvasStateBridge(
        scene_bridge=_FlowSceneStub(),
        execution_source=_FlowExecutionStub(),
    )

    assert bridge.port_flow_state_lookup == {
        "source": {"out": "flowing"},
        "sink": {"in": "flowing"},
    }
    assert bridge.node_solution_freshness_lookup == {"source": "current"}
    assert bridge.fresh_run_node_lookup == {"source": True}


def test_metadata_only_records_are_unavailable_without_runtime_flow() -> None:
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id["workspace"][
        "source"
    ]["run"]["outputs_available"] = False
    bridge = GraphCanvasStateBridge(
        scene_bridge=_FlowSceneStub(),
        execution_source=execution,
    )

    assert bridge.port_flow_state_lookup == {
        "source": {"out": "idle"},
        "sink": {"in": "waiting"},
    }
    preview = bridge.port_value_preview_lookup["source"]["out"]
    assert preview["state"] == "unavailable"
    assert preview["tooltip_text"] == "Unavailable"


def _property_presentation_bridge(
    *,
    property_item: dict[str, object],
    result: SettledPortResult | None,
    edge_enabled: bool = True,
    data_type_warning: bool = False,
    stale: bool = False,
) -> tuple[GraphCanvasStateBridge, dict[str, object]]:
    scene = _FlowSceneStub()
    authored_item = copy.deepcopy(property_item)
    scene.nodes_model[1]["ports"][0]["default_property"] = authored_item
    scene.edges_model[0].update(
        {
            "enabled": edge_enabled,
            "data_type_warning": data_type_warning,
            "target_port_key": str(property_item["key"]),
        }
    )
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id = {
        "workspace": {
            "source": {
                "run": {
                    "record_id": "run",
                    "observed_at_epoch_ms": 1.0,
                    "outputs": {} if result is None else {"out": result},
                }
            }
        }
    }
    execution.run_state.node_solution_facts_by_workspace_id = {
        "workspace": {
            "source": _solution_fact(
                "source",
                freshness=(
                    SolutionFreshness.EXPIRED if stale else SolutionFreshness.CURRENT
                ),
            )
        }
    }
    return (
        GraphCanvasStateBridge(scene_bridge=scene, execution_source=execution),
        authored_item,
    )


@pytest.mark.parametrize(
    ("property_type", "authored", "enum_values", "upstream", "expected"),
    (
        ("str", "local", (), "upstream", "upstream"),
        ("int", 2, (), 7, 7),
        ("float", 1.5, (), 7, 7.0),
        ("bool", True, (), False, False),
        ("enum", "None", ("None", "Manual"), "Manual", "Manual"),
        (
            "interval_1d",
            {"start": 0.0, "end": 1.0},
            (),
            Interval1D(10.0, 0.0),
            {"start": 10.0, "end": 0.0},
        ),
    ),
)
def test_property_presentations_show_only_supported_settled_item_values(
    property_type: str,
    authored: object,
    enum_values: tuple[str, ...],
    upstream: object,
    expected: object,
) -> None:
    property_item = {
        "key": "in",
        "type": property_type,
        "value": authored,
        "display_value": None,
        "display_value_available": False,
        "enum_values": list(enum_values),
        "override_input_port_keys": ["in"],
        "overridden_by_input": True,
        "condition_enabled": True,
        "canvas_interaction_enabled": True,
        "editor_enabled": False,
        "searchable": property_type == "enum",
    }
    bridge, authored_item = _property_presentation_bridge(
        property_item=property_item,
        result=SettledPortResult(
            status="value", value=DataTree.from_item(upstream)
        ),
    )

    presentation = bridge.property_presentation_lookup["sink"]["in"]
    assert presentation["value"] == authored
    assert presentation["display_value"] == expected
    assert presentation["display_value_available"] is True
    assert presentation["overridden_by_input"] is True
    assert presentation["condition_enabled"] is True
    assert presentation["editor_enabled"] is False
    assert presentation["searchable"] is (property_type == "enum")
    assert authored_item == property_item


@pytest.mark.parametrize(
    ("result", "data_type_warning", "stale"),
    (
        (None, False, False),
        (SettledPortResult(status="empty"), False, False),
        (
            SettledPortResult(
                status="value", value=DataTree((((0,), ("first", "second")),))
            ),
            False,
            False,
        ),
        (
            SettledPortResult(status="value", value=DataTree.from_item(object())),
            False,
            False,
        ),
        (
            SettledPortResult(
                status="value", value=DataTree.from_item("x" * 4097)
            ),
            False,
            False,
        ),
        (
            SettledPortResult(status="value", value=DataTree.from_item("upstream")),
            True,
            False,
        ),
        (
            SettledPortResult(status="value", value=DataTree.from_item("upstream")),
            False,
            True,
        ),
    ),
)
def test_connected_unavailable_or_invalid_property_values_use_placeholder_state(
    result: SettledPortResult | None,
    data_type_warning: bool,
    stale: bool,
) -> None:
    bridge, authored_item = _property_presentation_bridge(
        property_item={
            "key": "in",
            "type": "str",
            "value": "authored",
            "display_value": None,
            "display_value_available": False,
            "enum_values": [],
            "override_input_port_keys": ["in"],
            "overridden_by_input": True,
            "condition_enabled": True,
            "canvas_interaction_enabled": True,
            "editor_enabled": False,
            "searchable": False,
        },
        result=result,
        data_type_warning=data_type_warning,
        stale=stale,
    )

    presentation = bridge.property_presentation_lookup["sink"]["in"]
    assert presentation["value"] == "authored"
    assert presentation["display_value"] is None
    assert presentation["display_value_available"] is False
    assert presentation["overridden_by_input"] is True
    assert presentation["editor_enabled"] is False
    assert presentation["editor_disabled_reason"] == (
        "Value supplied by connected input."
    )
    assert authored_item["value"] == "authored"


@pytest.mark.parametrize(
    ("property_type", "upstream", "minimum", "maximum"),
    (
        ("int", 1 << 53, None, None),
        ("float", 101.0, 0.0, 100.0),
        ("interval_1d", Interval1D(10.0, -1.0), 0.0, 100.0),
    ),
)
def test_out_of_editor_domain_property_values_use_placeholder_state(
    property_type: str,
    upstream: object,
    minimum: float | None,
    maximum: float | None,
) -> None:
    property_item = {
        "key": "in",
        "type": property_type,
        "value": 0,
        "display_value": None,
        "display_value_available": False,
        "enum_values": [],
        "minimum": minimum,
        "maximum": maximum,
        "override_input_port_keys": ["in"],
        "overridden_by_input": True,
        "condition_enabled": True,
        "canvas_interaction_enabled": True,
        "editor_enabled": False,
        "searchable": False,
    }
    bridge, authored_item = _property_presentation_bridge(
        property_item=property_item,
        result=SettledPortResult(
            status="value",
            value=DataTree.from_item(upstream),
        ),
    )

    presentation = bridge.property_presentation_lookup["sink"]["in"]
    assert presentation["display_value"] is None
    assert presentation["display_value_available"] is False
    assert presentation["overridden_by_input"] is True
    assert presentation["editor_enabled"] is False
    assert authored_item == property_item


def test_disabled_edge_restores_authored_property_presentation() -> None:
    bridge, _authored_item = _property_presentation_bridge(
        property_item={
            "key": "in",
            "type": "str",
            "value": "authored",
            "display_value": None,
            "display_value_available": False,
            "enum_values": [],
            "override_input_port_keys": ["in"],
            "overridden_by_input": True,
            "condition_enabled": True,
            "canvas_interaction_enabled": True,
            "editor_enabled": False,
            "searchable": False,
        },
        result=SettledPortResult(
            status="value", value=DataTree.from_item("upstream")
        ),
        edge_enabled=False,
    )

    presentation = bridge.property_presentation_lookup["sink"]["in"]
    assert presentation["value"] == "authored"
    assert presentation["display_value"] == "authored"
    assert presentation["display_value_available"] is True
    assert presentation["overridden_by_input"] is False
    assert presentation["editor_enabled"] is True


def test_property_condition_uses_safe_upstream_value_and_disables_while_unavailable() -> None:
    scene = _FlowSceneStub()
    mode_item = {
        "key": "mode",
        "type": "enum",
        "value": "None",
        "display_value": None,
        "display_value_available": False,
        "enum_values": ["None", "Manual"],
        "override_input_port_keys": ["mode"],
        "overridden_by_input": True,
        "condition_enabled": True,
        "canvas_interaction_enabled": True,
        "editor_enabled": False,
        "searchable": False,
    }
    sectors_item = {
        "key": "sectors",
        "type": "int",
        "value": 2,
        "display_value": 2,
        "display_value_available": True,
        "enum_values": [],
        "override_input_port_keys": ["sectors"],
        "overridden_by_input": False,
        "enabled_when": {
            "property_key": "mode",
            "property_label": "Cyclic symmetry mode",
            "values": ["Manual"],
            "source_type": "enum",
            "source_enum_values": ["None", "Manual"],
            "source_value": "None",
            "source_override_input_port_keys": ["mode"],
        },
        "condition_enabled": False,
        "condition_reason": "Available when Cyclic symmetry mode is Manual.",
        "canvas_interaction_enabled": True,
        "editor_enabled": False,
        "searchable": False,
    }
    scene.nodes_model[1]["ports"] = [
        {
            "key": "mode",
            "direction": "in",
            "kind": "data",
            "default_property": mode_item,
        }
    ]
    scene.nodes_model[1]["inline_properties"] = [sectors_item]
    scene.edges_model[0].update(
        {"target_port_key": "mode", "enabled": True, "data_type_warning": False}
    )
    execution = _FlowExecutionStub()
    outputs = execution.run_state.cached_node_output_records_by_workspace_id[
        "workspace"
    ]["source"]["run"]["outputs"]
    outputs["out"] = SettledPortResult(
        status="value", value=DataTree.from_item("Manual")
    )
    bridge = GraphCanvasStateBridge(scene_bridge=scene, execution_source=execution)

    lookup = bridge.property_presentation_lookup["sink"]
    assert lookup["mode"]["display_value"] == "Manual"
    assert lookup["sectors"]["condition_enabled"] is True
    assert lookup["sectors"]["editor_enabled"] is True

    outputs["out"] = SettledPortResult(status="empty")
    unavailable = bridge.property_presentation_lookup["sink"]
    assert unavailable["mode"]["display_value_available"] is False
    assert unavailable["sectors"]["condition_enabled"] is False
    assert unavailable["sectors"]["editor_enabled"] is False

    scene.edges_model[0]["enabled"] = False
    mode_item["value"] = "Manual"
    disabled_edge = bridge.property_presentation_lookup["sink"]
    assert disabled_edge["mode"]["display_value"] == "Manual"
    assert disabled_edge["sectors"]["condition_enabled"] is True
    assert disabled_edge["sectors"]["editor_enabled"] is True


def test_hidden_numeric_condition_source_rejects_out_of_domain_upstream_value() -> None:
    source_metadata = {
        "property_key": "mode_number",
        "property_label": "Mode number",
        "values": [3],
        "source_type": "int",
        "source_enum_values": [],
        "source_minimum": 1,
        "source_maximum": 5,
        "source_value": 3,
        "source_override_input_port_keys": ["mode_number"],
    }
    dependent = {
        "key": "dependent",
        "type": "int",
        "value": 2,
        "display_value": 2,
        "display_value_available": True,
        "enum_values": [],
        "override_input_port_keys": ["dependent"],
        "overridden_by_input": False,
        "enabled_when": source_metadata,
        "condition_enabled": True,
        "condition_reason": "Available when Mode number is 3.",
        "canvas_interaction_enabled": True,
        "editor_enabled": True,
        "searchable": False,
    }
    scene = _FlowSceneStub()
    scene.nodes_model[1]["inline_properties"] = [dependent]
    scene.nodes_model[1]["ports"] = []
    scene.edges_model[0].update(
        {
            "target_port_key": "mode_number",
            "enabled": True,
            "data_type_warning": False,
        }
    )
    execution = _FlowExecutionStub()
    outputs = execution.run_state.cached_node_output_records_by_workspace_id[
        "workspace"
    ]["source"]["run"]["outputs"]
    outputs["out"] = SettledPortResult(
        status="value",
        value=DataTree.from_item(10),
    )

    lookup = GraphCanvasStateBridge(
        scene_bridge=scene,
        execution_source=execution,
    ).property_presentation_lookup["sink"]

    assert lookup["dependent"]["condition_enabled"] is False
    assert lookup["dependent"]["editor_enabled"] is False


def test_canvas_execution_facts_project_node_run_counts() -> None:
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id = {
        "workspace": {
            "select": {"run-1": {}, "run-2": {}},
            "ignored": [],
        }
    }
    execution.run_state.node_output_run_counts_by_workspace_id = {
        "workspace": {"select": 2}
    }
    bridge = GraphCanvasStateBridge(
        scene_bridge=_FlowSceneStub(),
        execution_source=execution,
    )

    assert bridge.node_run_count_lookup == {"select": 2}


def test_canvas_output_previews_are_bounded_and_distinguish_freshness() -> None:
    scene = _FlowSceneStub()
    scene.nodes_model = [
        {
            "node_id": "current",
            "ports": [
                {
                    "key": "item",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "item",
                },
                {
                    "key": "list",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "list",
                },
                {
                    "key": "tree",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "tree",
                },
                {
                    "key": "empty",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "tree",
                },
                {
                    "key": "failed",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "item",
                },
                {
                    "key": "missing",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "item",
                },
            ],
        },
        {
            "node_id": "stale",
            "ports": [
                {
                    "key": "out",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "tree",
                }
            ],
        },
        {
            "node_id": "never",
            "ports": [
                {
                    "key": "out",
                    "direction": "out",
                    "kind": "data",
                    "data_access": "item",
                }
            ],
        },
    ]
    scene.edges_model = []
    long_sample = "x" * 300
    tree = DataTree(
        ((0, branch), tuple(f"{branch}:{item}" for item in range(10)))
        for branch in range(10)
    )
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id = {
        "workspace": {
            "current": {
                "run": {
                    "record_id": "run",
                    "observed_at_epoch_ms": 2.0,
                    "outputs": {
                        "item": SettledPortResult(
                            status="value", value=DataTree.from_item(long_sample)
                        ),
                        "list": SettledPortResult(
                            status="value",
                            value=DataTree.from_list(tuple(range(10))),
                        ),
                        "tree": SettledPortResult(status="value", value=tree),
                        "empty": SettledPortResult(status="empty"),
                        "failed": SettledPortResult(
                            status="failed",
                            errors=(
                                RootExecutionError(
                                    node_id="current", error="preview failure"
                                ),
                            ),
                        ),
                    },
                }
            },
            "stale": {
                "run": {
                    "record_id": "run",
                    "observed_at_epoch_ms": 1.0,
                    "outputs": {
                        "out": SettledPortResult(
                            status="value",
                            value=DataTree((((0, 1), ("old", "again")),)),
                        )
                    },
                }
            },
        }
    }
    execution.run_state.node_solution_facts_by_workspace_id = {
        "workspace": {
            "current": _solution_fact("current"),
            "stale": _solution_fact(
                "stale", freshness=SolutionFreshness.EXPIRED
            ),
        }
    }

    previews = GraphCanvasStateBridge(
        scene_bridge=scene,
        execution_source=execution,
    ).port_value_preview_lookup

    assert previews["current"]["item"]["state"] == "current"
    assert previews["current"]["list"]["state"] == "current"
    assert previews["current"]["tree"]["state"] == "current"
    assert previews["current"]["empty"]["state"] == "empty"
    assert previews["current"]["failed"]["state"] == "failed"
    assert previews["current"]["missing"]["state"] == "empty"
    assert previews["stale"]["out"]["state"] == "stale"
    assert previews["never"]["out"]["state"] == "never"

    item_lines = previews["current"]["item"]["tooltip_text"].splitlines()
    assert len(item_lines[1]) <= 160
    assert long_sample not in repr(previews)
    assert "preview failure" not in repr(previews)
    assert "SettledPortResult" not in repr(previews)
    assert "DataTree" not in repr(previews)
    assert previews["current"]["failed"]["tooltip_text"] == "Failed"
    assert all(
        set(preview) == {
            "state",
            "access",
            "tooltip_text",
            "rows",
            "truncated",
            "rich_preview",
        }
        for node_previews in previews.values()
        for preview in node_previews.values()
    )
    item_rows = previews["current"]["item"]["rows"]
    assert item_rows[0] == {"kind": "branch", "path": "0"}
    assert {key: item_rows[1][key] for key in ("kind", "path", "index")} == {
        "kind": "item",
        "path": "0",
        "index": 0,
    }
    assert len(item_rows[1]["text"]) <= 160
    assert previews["current"]["item"]["truncated"] is False
    assert previews["stale"]["out"]["rows"] == [
        {"kind": "branch", "path": "0;1"},
        {"kind": "item", "path": "0;1", "index": 0, "text": "old"},
        {"kind": "item", "path": "0;1", "index": 1, "text": "again"},
    ]
    assert previews["stale"]["out"]["truncated"] is False
    assert all(
        preview["rows"] == [] and preview["truncated"] is False
        for preview in (
            previews["current"]["empty"],
            previews["current"]["failed"],
            previews["current"]["missing"],
            previews["never"]["out"],
        )
    )

    list_lines = previews["current"]["list"]["tooltip_text"].splitlines()
    assert "List: 10 items" in list_lines
    assert sum(line.startswith("[") for line in list_lines) == 8
    assert not any(line.startswith("[8]") for line in list_lines)
    assert previews["current"]["list"]["truncated"] is True

    tree_lines = previews["current"]["tree"]["tooltip_text"].splitlines()
    assert "Tree: 10 branches, 100 items" in tree_lines
    assert [line for line in tree_lines if line.startswith("{")] == [
        f"{{0;{index}}}" for index in range(8)
    ]
    first_branch = tree_lines[
        tree_lines.index("{0;0}") + 1 : tree_lines.index("{0;1}")
    ]
    assert len(first_branch) == 8
    assert not any(line.lstrip().startswith("[8]") for line in first_branch)
    tree_rows = previews["current"]["tree"]["rows"]
    branch_rows = [row for row in tree_rows if row["kind"] == "branch"]
    assert branch_rows == [
        {"kind": "branch", "path": f"0;{index}"} for index in range(8)
    ]
    assert [
        row["index"]
        for row in tree_rows
        if row["kind"] == "item" and row["path"] == "0;0"
    ] == list(range(8))
    assert next(
        row for row in tree_rows if row["kind"] == "item" and row["path"] == "0;1"
    )["index"] == 0
    assert previews["current"]["tree"]["truncated"] is True


def test_panel_copy_text_formats_latest_current_output() -> None:
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id = {
        "workspace": {
            "panel": {
                "older": {
                    "record_id": "older",
                    "observed_at_epoch_ms": 1.0,
                    "outputs": {
                        "output": SettledPortResult(
                            status="value", value=DataTree.from_item("old")
                        )
                    },
                    "stale": False,
                },
                "latest": {
                    "record_id": "latest",
                    "observed_at_epoch_ms": 2.0,
                    "outputs": {
                        "output": SettledPortResult(
                            status="value",
                            value=DataTree(
                                (
                                    ((0, 1), ("alpha", 2)),
                                    ((3,), ("beta",)),
                                )
                            ),
                        )
                    },
                    "stale": False,
                },
            }
        }
    }
    execution.run_state.node_solution_facts_by_workspace_id = {
        "workspace": {"panel": _solution_fact("panel", "latest")}
    }
    bridge = GraphCanvasStateBridge(
        scene_bridge=_FlowSceneStub(), execution_source=execution
    )

    assert bridge.panel_copy_text("panel", False) == "alpha\n2\nbeta"
    assert bridge.panel_copy_text("panel", True) == (
        "* 0;1\nalpha\n2\n* 3\nbeta"
    )
    assert bridge.panel_display_rows("panel") == [
        {"kind": "branch", "path": "0;1"},
        {"kind": "item", "path": "0;1", "index": 0, "text": "alpha"},
        {"kind": "item", "path": "0;1", "index": 1, "text": "2"},
        {"kind": "branch", "path": "3"},
        {"kind": "item", "path": "3", "index": 0, "text": "beta"},
    ]


@pytest.mark.parametrize(
    "latest_record",
    (
        {
            "observed_at_epoch_ms": 2.0,
            "outputs": {
                "output": SettledPortResult(
                    status="value", value=DataTree.from_item("stale")
                )
            },
            "stale": True,
        },
        {
            "observed_at_epoch_ms": 2.0,
            "outputs": {
                "other": SettledPortResult(
                    status="value", value=DataTree.from_item("wrong port")
                )
            },
            "stale": False,
        },
        {
            "observed_at_epoch_ms": 2.0,
            "outputs": {"output": SettledPortResult(status="empty")},
            "stale": False,
        },
    ),
)
def test_panel_copy_text_rejects_stale_missing_or_non_value_output(
    latest_record: dict[str, object],
) -> None:
    execution = _FlowExecutionStub()
    execution.run_state.cached_node_output_records_by_workspace_id = {
        "workspace": {"panel": {"latest": latest_record}}
    }
    bridge = GraphCanvasStateBridge(
        scene_bridge=_FlowSceneStub(), execution_source=execution
    )

    assert bridge.panel_copy_text("panel", False) == ""
    assert bridge.panel_copy_text("panel", True) == ""
    assert bridge.panel_display_rows("panel") == []


def test_canvas_execution_facts_project_waiting_and_retained_warning_diagnostics_without_values() -> (
    None
):
    scene = _FlowSceneStub()
    scene.edges_model.append(
        {
            "source_node_id": "empty-source",
            "source_port_key": "out",
            "target_node_id": "blocked",
            "target_port_key": "required",
            "enabled": True,
        }
    )
    scene.nodes_model.extend(
        [
            {
                "node_id": "blocked",
                "runtime_behavior": "active",
                "properties": {"required": "configured value"},
                "ports": [
                    {
                        "key": "required",
                        "label": "Required Mesh",
                        "direction": "in",
                        "kind": "data",
                        "optional": False,
                        "inactive": False,
                        "uses_property_default": True,
                        "default_property": {
                            "value": "configured value",
                            "overridden_by_input": True,
                        },
                        "flow_state": "default",
                    }
                ],
            },
            {
                "node_id": "alternative",
                "runtime_behavior": "active",
                "properties": {"path": ""},
                "readiness": {
                    "property_labels": {"path": "Result path"},
                    "requirements": [
                        {
                            "any_of_ports": ["data"],
                            "any_of_properties": ["path"],
                            "when_ports_present": [],
                            "when_properties": [],
                        }
                    ],
                },
                "ports": [
                    {
                        "key": "data",
                        "label": "Result data",
                        "direction": "in",
                        "kind": "data",
                        "optional": True,
                        "inactive": False,
                        "flow_state": "idle",
                    }
                ],
            },
            {
                "node_id": "conditional-inactive",
                "runtime_behavior": "active",
                "properties": {"mode": "static", "fatigue_curve": ""},
                "readiness": {
                    "property_labels": {"mode": "Mode", "fatigue_curve": "Fatigue curve"},
                    "requirements": [
                        {
                            "any_of_ports": [],
                            "any_of_properties": ["fatigue_curve"],
                            "when_ports_present": [],
                            "when_properties": [
                                {"property_key": "mode", "values": ["fatigue"]}
                            ],
                        }
                    ],
                },
                "ports": [],
            },
            {
                "node_id": "false-zero-values",
                "runtime_behavior": "active",
                "properties": {"enabled": False, "count": 0},
                "readiness": {
                    "property_labels": {"enabled": "Enabled", "count": "Count"},
                    "requirements": [
                        {"any_of_properties": ["enabled"]},
                        {"any_of_properties": ["count"]},
                    ],
                },
                "ports": [],
            },
            {
                "node_id": "ready-unrun",
                "runtime_behavior": "active",
                "ports": [
                    {
                        "key": "optional",
                        "label": "Optional Mesh",
                        "direction": "in",
                        "kind": "data",
                        "optional": False,
                        "locked": True,
                        "inactive": False,
                        "flow_state": "waiting",
                    }
                ],
            },
        ]
    )
    blocked_warning = (
        "The node has not been computed because the Required Mesh input did not "
        "receive any data yet. Please provide data for all mandatory inputs and "
        "check your upstream workflow for errors or missing wires."
    )
    execution = _FlowExecutionStub()
    execution.run_state.runtime_warning_messages_by_workspace_id = {
        "workspace": {
            "blocked": (blocked_warning,),
            "source": ("Mesh quality was reduced.", "Mesh quality was reduced.")
        }
    }
    bridge = GraphCanvasStateBridge(scene_bridge=scene, execution_source=execution)

    diagnostics = bridge.node_diagnostic_lookup
    assert diagnostics["blocked"]["severity"] == "warning"
    blocked_row = diagnostics["blocked"]["rows"][0]
    assert blocked_row["code"] == "required_input_waiting"
    assert blocked_row["port_key"] == "required"
    assert blocked_row["target_keys"] == ["required"]
    assert blocked_row["target_labels"] == ["Required Mesh"]
    assert blocked_row["message"] == blocked_warning
    assert [row["code"] for row in diagnostics["blocked"]["rows"]] == [
        "required_input_waiting"
    ]
    assert bridge.port_flow_state_lookup["blocked"]["required"] == "waiting"

    alternative_row = diagnostics["alternative"]["rows"][0]
    assert alternative_row["target_keys"] == ["data", "path"]
    assert alternative_row["target_labels"] == ["Result data", "Result path"]
    assert bridge.port_flow_state_lookup["alternative"]["data"] == "waiting"
    assert diagnostics["source"]["rows"] == [
        {
            "severity": "warning",
            "code": "runtime_warning",
            "port_key": "",
            "port_label": "",
            "message": "Mesh quality was reduced.",
        }
    ]
    assert "Mesh quality was reduced." in diagnostics["source"]["tooltip_text"]
    assert "ready-unrun" not in diagnostics
    assert "conditional-inactive" not in diagnostics
    assert "false-zero-values" not in diagnostics
    assert "__raw_runtime_value__" not in repr(diagnostics)


def test_canvas_readiness_uses_runtime_values_for_blank_false_and_zero() -> None:
    scene = _FlowSceneStub()
    sink = scene.nodes_model[1]
    sink["runtime_behavior"] = "active"
    sink["properties"] = {}
    sink["ports"][0]["label"] = "Required Value"

    blank_execution = _FlowExecutionStub()
    blank_execution.run_state.cached_node_output_records_by_workspace_id["workspace"][
        "source"
    ]["run"]["outputs"]["out"] = SettledPortResult(
        status="value",
        value=DataTree.from_item("  "),
    )
    blank_bridge = GraphCanvasStateBridge(
        scene_bridge=scene,
        execution_source=blank_execution,
    )
    assert blank_bridge.node_diagnostic_lookup["sink"]["rows"][0]["target_keys"] == [
        "in"
    ]
    assert blank_bridge.port_flow_state_lookup["sink"]["in"] == "waiting"

    for supplied in (False, 0):
        execution = _FlowExecutionStub()
        execution.run_state.cached_node_output_records_by_workspace_id["workspace"][
            "source"
        ]["run"]["outputs"]["out"] = SettledPortResult(
            status="value",
            value=DataTree.from_item(supplied),
        )
        bridge = GraphCanvasStateBridge(
            scene_bridge=scene,
            execution_source=execution,
        )
        assert "sink" not in bridge.node_diagnostic_lookup
        assert bridge.port_flow_state_lookup["sink"]["in"] == "flowing"


def test_port_flow_notifications_are_isolated_from_other_execution_facts() -> None:
    scene = _FlowSceneStub()
    execution = _FlowExecutionStub()
    bridge = GraphCanvasStateBridge(
        scene_bridge=scene,
        execution_source=execution,
    )
    port_flow_changes: list[None] = []
    execution_changes: list[None] = []
    bridge.port_flow_state_changed.connect(lambda: port_flow_changes.append(None))
    bridge.node_execution_state_changed.connect(lambda: execution_changes.append(None))

    scene.nodes_changed.emit()
    scene.edges_changed.emit()
    assert len(port_flow_changes) == 2
    assert execution_changes == []

    execution.node_execution_state_changed.emit()
    assert len(port_flow_changes) == 3
    assert len(execution_changes) == 1

    scene.workspace_id = "other-workspace"
    scene.workspace_changed.emit(scene.workspace_id)
    assert len(port_flow_changes) == 4
    assert len(execution_changes) == 2


class _FlowProbePlugin:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id="tests.flow_probe",
            display_name="Flow Probe",
            category_path=("Tests",),
            icon="test",
            ports=(
                PortSpec(
                    "req_in",
                    "in",
                    "data",
                    'COREX.DataTypes.String',
                    required=True,
                    uses_property_default=True,
                    description="Mesh data required by the probe.",
                ),
                PortSpec("opt_in", "in", "data", 'COREX.DataTypes.String', required=False),
                PortSpec("out", "out", "data", 'COREX.DataTypes.String'),
                PortSpec("aux_out", "out", "data", 'COREX.DataTypes.String'),
            ),
            properties=(
                PropertySpec("req_in", "str", "fallback", "Required Input", inline_editor="text"),
                PropertySpec(
                    "dynamic_names",
                    "json",
                    ["dynamic"],
                    "Dynamic Inputs",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    "inputs",
                    "dynamic_names",
                    "in",
                    _flow_probe_dynamic_ports,
                    _next_flow_probe_dynamic_port,
                    maximum=1,
                ),
            ),
            description="Reports whether mesh data is available.",
            keywords=("mesh", "availability"),
            readiness_requirements=(
                ReadinessRequirementSpec(
                    any_of_ports=("opt_in",),
                    when_properties=(
                        PropertyConditionSpec("req_in", ("special",)),
                    ),
                ),
            ),
        )

    def execute(self, _ctx):  # noqa: ANN001
        raise NotImplementedError

    @classmethod
    def create(cls) -> "_FlowProbePlugin":
        return cls()


def _flow_probe_dynamic_ports(properties) -> tuple[PortSpec, ...]:  # noqa: ANN001
    return tuple(
        PortSpec(
            str(key),
            "in",
            "data",
            'COREX.DataTypes.String',
            label="Dynamic Input",
            required=True,
        )
        for key in properties["dynamic_names"]
    )


def _next_flow_probe_dynamic_port(_properties) -> str:  # noqa: ANN001
    return "dynamic"


def _flow_probe_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(_FlowProbePlugin)
    return registry


def test_dynamic_port_graph_payload_carries_port_flow_state() -> None:
    registry = _flow_probe_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(workspace.workspace_id, "tests.flow_probe", "Source", 0, 0, properties={"dynamic_names": ["dynamic"]})
    sink = model.add_node(workspace.workspace_id, "tests.flow_probe", "Sink", 240, 0, properties={"dynamic_names": ["dynamic"]})
    empty = model.add_node(
        workspace.workspace_id,
        "tests.flow_probe",
        "Empty Group",
        480,
        0,
        properties={"dynamic_names": []},
    )
    model.add_edge(
        workspace.workspace_id, source.node_id, "out", sink.node_id, "req_in"
    )

    nodes_payload, _backdrops, _minimap, _edges = (
        GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
    )

    source_ports = {
        port["key"]: port
        for port in next(
            item for item in nodes_payload if item["node_id"] == source.node_id
        )["ports"]
    }
    source_payload = next(
        item for item in nodes_payload if item["node_id"] == source.node_id
    )
    empty_payload = next(
        item for item in nodes_payload if item["node_id"] == empty.node_id
    )
    assert source_payload["help_text"] == "Reports whether mesh data is available."
    assert source_payload["category_path"] == ["Tests"]
    assert source_payload["keywords"] == ["mesh", "availability"]
    assert source_payload["readiness"]["requirements"] == [
        {
            "any_of_ports": ["opt_in"],
            "any_of_properties": [],
            "when_ports_present": [],
            "when_properties": [
                {"property_key": "req_in", "values": ["special"]}
            ],
        }
    ]
    assert next(
        port
        for port in source_payload["readiness"]["ports"]
        if port["key"] == "dynamic"
    ) == {
        "key": "dynamic",
        "label": "Dynamic Input",
        "direction": "in",
        "kind": "data",
        "required": True,
        "uses_property_default": False,
        "allow_empty_string": False,
    }
    assert source_payload["dynamic_port_groups"] == [
        {
            "id": "inputs",
            "direction": "in",
            "port_keys": ["dynamic"],
            "can_insert": False,
            "removable_port_keys": ["dynamic"],
            "rename_mode": "none",
        }
    ]
    assert empty_payload["dynamic_port_groups"] == [
        {
            "id": "inputs",
            "direction": "in",
            "port_keys": [],
            "can_insert": True,
            "removable_port_keys": [],
            "rename_mode": "none",
        }
    ]
    assert source_ports["req_in"]["help_text"] == "Mesh data required by the probe."
    sink_ports = {
        port["key"]: port
        for port in next(
            item for item in nodes_payload if item["node_id"] == sink.node_id
        )["ports"]
    }

    assert source_ports["out"]["flow_state"] == "flowing"
    assert source_ports["aux_out"]["flow_state"] == "idle"
    assert source_ports["req_in"]["flow_state"] == "default"
    default_property = source_ports["req_in"]["default_property"]
    assert {
        key: default_property[key]
        for key in (
            "key",
            "label",
            "type",
            "value",
            "enum_values",
            "minimum",
            "maximum",
            "step",
            "inline_editor",
            "file_filter",
            "overridden_by_input",
        )
    } == {
        "key": "req_in",
        "label": "Required Input",
        "type": "str",
        "value": "fallback",
        "enum_values": [],
        "minimum": None,
        "maximum": None,
        "step": 0.0,
        "inline_editor": "text",
        "file_filter": "",
        "overridden_by_input": False,
    }
    assert default_property["display_value"] == "fallback"
    assert default_property["display_value_available"] is True
    assert default_property["condition_enabled"] is True
    assert default_property["editor_enabled"] is True
    assert default_property["searchable"] is False
    assert source_ports["opt_in"]["flow_state"] == "idle"
    assert source_ports["dynamic"]["flow_state"] == "waiting"
    assert sink_ports["req_in"]["flow_state"] == "flowing"
    assert sink_ports["req_in"]["default_property"]["overridden_by_input"] is True
    assert sink_ports["opt_in"]["flow_state"] == "idle"
