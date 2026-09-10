from __future__ import annotations

from collections.abc import Mapping

import pytest

from ea_node_editor.execution.compiler import compile_runtime_workspace_snapshot
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.effective_ports import port_compatibility, ports_compatible
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_payloads import (
    edge_instance_to_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.graph.transform_fragment_ops import insert_graph_fragment
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.subnode import SUBNODE_NODE_DESCRIPTORS
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    DataConversionSpec,
    DataTypeSpec,
    GRAPH_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.ui.graph_theme import resolve_graph_theme
from ea_node_editor.ui.shell.library_projection import (
    build_combined_library_items,
    build_registry_library_items,
)
from ea_node_editor.ui.shell.quick_insert_projection import (
    build_connection_quick_insert_items,
)
from ea_node_editor.ui_qml.edge_routing import build_edge_payload

_SOURCE_TYPE_ID = "COREX.Tests.TypeSource"
_TARGET_TYPE_ID = "COREX.Tests.TypeTarget"
_CHAIN_TARGET_TYPE_ID = "COREX.Tests.TypeChainTarget"


class _Node:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _context) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _register_spec(registry: NodeRegistry, spec: NodeTypeSpec) -> None:
    registry.register(lambda spec=spec: _Node(spec))


def _spec(
    type_id: str,
    port: PortSpec,
    *,
    properties: tuple[PropertySpec, ...] = (),
    dynamic_port_groups: tuple[DynamicPortGroupSpec, ...] = (),
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name=type_id,
        category_path=("Tests",),
        icon="",
        ports=(port,),
        properties=properties,
        dynamic_port_groups=dynamic_port_groups,
    )


def _typed_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.data_types.register_many(
        types=(
            DataTypeSpec(
                _SOURCE_TYPE_ID,
                "Test source",
                "scalar",
                lambda _value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
            DataTypeSpec(
                _TARGET_TYPE_ID,
                "Test target",
                "scalar",
                lambda _value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
            DataTypeSpec(
                _CHAIN_TARGET_TYPE_ID,
                "Test chain target",
                "scalar",
                lambda _value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
        ),
        conversions=(
            DataConversionSpec(
                _SOURCE_TYPE_ID,
                _TARGET_TYPE_ID,
                lambda value: value,
            ),
            DataConversionSpec(
                _TARGET_TYPE_ID,
                _CHAIN_TARGET_TYPE_ID,
                lambda value: value,
            ),
        ),
        owner_id="tests.graph_type_enforcement",
    )
    specs = (
        _spec(
            "tests.string_source",
            PortSpec("value", "out", "data", STRING_DATA_TYPE_ID),
        ),
        _spec(
            "tests.boolean_source",
            PortSpec("value", "out", "data", BOOLEAN_DATA_TYPE_ID),
        ),
        _spec(
            "tests.graph_source",
            PortSpec("value", "out", "data", GRAPH_DATA_TYPE_ID),
        ),
        _spec(
            "tests.convertible_source",
            PortSpec("value", "out", "data", _SOURCE_TYPE_ID),
        ),
        _spec(
            "tests.string_sink",
            PortSpec("value", "in", "data", STRING_DATA_TYPE_ID, required=True),
        ),
        _spec(
            "tests.boolean_sink",
            PortSpec("value", "in", "data", BOOLEAN_DATA_TYPE_ID, required=True),
        ),
        _spec(
            "tests.graph_sink",
            PortSpec("value", "in", "data", GRAPH_DATA_TYPE_ID, required=True),
        ),
        _spec(
            "tests.union_sink",
            PortSpec(
                "value",
                "in",
                "data",
                BOOLEAN_DATA_TYPE_ID,
                required=True,
                accepted_data_types=(STRING_DATA_TYPE_ID,),
            ),
        ),
        _spec(
            "tests.convertible_sink",
            PortSpec("value", "in", "data", _TARGET_TYPE_ID, required=True),
        ),
        _spec(
            "tests.chain_sink",
            PortSpec("value", "in", "data", _CHAIN_TARGET_TYPE_ID, required=True),
        ),
        _spec(
            "tests.flow_source",
            PortSpec("flow", "out", "flow", "flow"),
        ),
        _spec(
            "tests.flow_sink",
            PortSpec("flow", "in", "flow", "flow"),
        ),
    )
    for spec in specs:
        _register_spec(registry, spec)
    registry.register_descriptors(SUBNODE_NODE_DESCRIPTORS)
    registry.freeze()
    return registry


def test_structured_port_compatibility_is_the_boolean_authority() -> None:
    data_types = _typed_registry().data_types
    source = PortSpec("value", "out", "data", STRING_DATA_TYPE_ID)
    union_target = PortSpec(
        "value",
        "in",
        "data",
        BOOLEAN_DATA_TYPE_ID,
        accepted_data_types=(STRING_DATA_TYPE_ID,),
    )
    exact = port_compatibility(source, union_target, data_types=data_types)
    assert exact.status == "assignable"
    assert exact.reason_code == "exact"
    assert exact.matched_type_id == STRING_DATA_TYPE_ID
    assert ports_compatible(source, union_target, data_types=data_types)

    flow = port_compatibility(
        PortSpec("flow", "out", "flow", "flow"),
        PortSpec("flow", "in", "flow", "flow"),
        data_types=data_types,
    )
    assert (
        flow.status,
        flow.source_type_id,
        flow.target_type_id,
        flow.matched_type_id,
        flow.reason_code,
    ) == ("assignable", "flow", "flow", "flow", "flow_kind_match")

    mismatch = port_compatibility(
        PortSpec("flow", "out", "flow", "flow"),
        union_target,
        data_types=data_types,
    )
    assert mismatch.status == "incompatible"
    assert mismatch.reason_code == "port_kind_mismatch"
    assert not mismatch.is_compatible


def _add(
    mutations: ValidatedGraphMutation,
    type_id: str,
    x: float = 0.0,
    *,
    properties: dict[str, object] | None = None,
    parent_node_id: str | None = None,
) -> NodeInstance:
    return mutations.add_node(
        type_id=type_id,
        title=type_id,
        x=x,
        y=0.0,
        properties=properties,
        parent_node_id=parent_node_id,
    )


def test_graph_accepts_catalog_compatible_statuses_union_and_flow() -> None:
    registry = _typed_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)

    pairs = (
        ("tests.string_source", "tests.graph_sink", "assignable"),
        ("tests.graph_source", "tests.string_sink", "runtime_check"),
        ("tests.convertible_source", "tests.convertible_sink", "convertible"),
        ("tests.string_source", "tests.union_sink", "accepted union"),
        ("tests.flow_source", "tests.flow_sink", "flow"),
    )
    for index, (source_type, target_type, _case) in enumerate(pairs):
        source = _add(mutations, source_type, float(index * 200))
        target = _add(mutations, target_type, float(index * 200 + 100))
        source_port = "flow" if source_type == "tests.flow_source" else "value"
        target_port = "flow" if target_type == "tests.flow_sink" else "value"
        mutations.add_edge(
            source_node_id=source.node_id,
            source_port_key=source_port,
            target_node_id=target.node_id,
            target_port_key=target_port,
        )

    assert len(workspace.edges) == len(pairs)


def test_invalid_add_reassign_and_reenable_leave_graph_state_unchanged() -> None:
    registry = _typed_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    string_source = _add(mutations, "tests.string_source")
    boolean_source = _add(mutations, "tests.boolean_source", 100.0)
    string_sink = _add(mutations, "tests.string_sink", 200.0)
    boolean_sink = _add(mutations, "tests.boolean_sink", 300.0)
    string_edge = mutations.add_edge(
        source_node_id=string_source.node_id,
        source_port_key="value",
        target_node_id=string_sink.node_id,
        target_port_key="value",
    )
    boolean_edge = mutations.add_edge(
        source_node_id=boolean_source.node_id,
        source_port_key="value",
        target_node_id=boolean_sink.node_id,
        target_port_key="value",
    )

    before = workspace.capture_snapshot()
    before_revision = workspace.mutation_revision
    with pytest.raises(ValueError, match="Incompatible data types"):
        mutations.add_edge(
            source_node_id=string_source.node_id,
            source_port_key="value",
            target_node_id=boolean_sink.node_id,
            target_port_key="value",
        )
    assert workspace.capture_snapshot() == before
    assert workspace.mutation_revision == before_revision
    assert workspace.edges[boolean_edge.edge_id].input_order == 0

    with pytest.raises(ValueError, match="Incompatible data types"):
        mutations.move_edge_endpoint(
            string_edge.edge_id,
            "target",
            boolean_sink.node_id,
            "value",
        )
    assert workspace.capture_snapshot() == before
    assert workspace.mutation_revision == before_revision

    disabled_invalid = model._add_edge_record(
        workspace.workspace_id,
        source_node_id=string_source.node_id,
        source_port_key="value",
        target_node_id=boolean_sink.node_id,
        target_port_key="value",
        enabled=False,
        input_order=1,
    )
    before_enable = workspace.capture_snapshot()
    before_enable_revision = workspace.mutation_revision
    assert not mutations.set_edge_enabled(disabled_invalid.edge_id, True)
    assert workspace.capture_snapshot() == before_enable
    assert workspace.mutation_revision == before_enable_revision


def test_path_pointer_cannot_replace_number_slider_on_bar_series() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    path_pointer = _add(mutations, "io.path_pointer")
    number_slider = _add(mutations, "data.number_slider", 100.0)
    series_constant = _add(
        mutations,
        "core.constant",
        200.0,
        properties={"value": {"label": "Series", "values": [1, 2, 3]}},
    )
    bar_plot = _add(mutations, "plot.bar", 300.0)

    assert mutations.ports_compatible(
        source_node_id=number_slider.node_id,
        source_port_key="value",
        target_node_id=bar_plot.node_id,
        target_port_key="series",
    )
    assert mutations.ports_compatible(
        source_node_id=series_constant.node_id,
        source_port_key="value",
        target_node_id=bar_plot.node_id,
        target_port_key="series",
    )
    bar_series_port = next(
        port for port in registry.get_spec("plot.bar").ports if port.key == "series"
    )
    assert registry.data_types.compatibility(
        GRAPH_DATA_TYPE_ID,
        bar_series_port.data_type,
        bar_series_port.accepted_data_types,
    ).status == "runtime_check"
    number_edge = mutations.add_edge(
        source_node_id=number_slider.node_id,
        source_port_key="value",
        target_node_id=bar_plot.node_id,
        target_port_key="series",
    )
    assert not mutations.ports_compatible(
        source_node_id=path_pointer.node_id,
        source_port_key="path",
        target_node_id=bar_plot.node_id,
        target_port_key="series",
    )

    before = workspace.capture_snapshot()
    before_revision = workspace.mutation_revision
    with pytest.raises(ValueError, match="Incompatible data types"):
        mutations.add_edge(
            source_node_id=path_pointer.node_id,
            source_port_key="path",
            target_node_id=bar_plot.node_id,
            target_port_key="series",
        )
    assert workspace.capture_snapshot() == before
    assert workspace.mutation_revision == before_revision
    assert tuple(workspace.edges) == (number_edge.edge_id,)

    items = build_combined_library_items(
        registry_items=build_registry_library_items(registry_specs=registry.all_specs(), data_types=registry.data_types),
        custom_workflow_items=[],
    )
    path_results = build_connection_quick_insert_items(
        combined_items=items,
        data_types=registry.data_types,
        query="Bar Plot",
        source_direction="out",
        source_kind="data",
        source_data_type=PATH_DATA_TYPE_ID,
        limit=100,
    )
    number_results = build_connection_quick_insert_items(
        combined_items=items,
        data_types=registry.data_types,
        query="Bar Plot",
        source_direction="out",
        source_kind="data",
        source_data_type=DOUBLE_DATA_TYPE_ID,
        limit=100,
    )
    assert "plot.bar" not in {str(item["type_id"]) for item in path_results}
    assert "plot.bar" in {str(item["type_id"]) for item in number_results}


def test_dynamic_type_preflight_and_subnode_semantic_change_are_atomic() -> None:
    registry = NodeRegistry()

    def dynamic_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
        keys = properties.get("port_ids", [])
        if not isinstance(keys, list):
            return ()
        return tuple(
            PortSpec(str(key), "out", "data", "COREX.Tests.Unknown")
            for key in keys
        )

    dynamic_spec = _spec(
        "tests.dynamic_unknown",
        PortSpec("static", "out", "data", STRING_DATA_TYPE_ID),
        properties=(
            PropertySpec(
                "port_ids",
                "json",
                [],
                "Port IDs",
                inspector_visible=False,
            ),
        ),
        dynamic_port_groups=(
            DynamicPortGroupSpec(
                "outputs",
                "port_ids",
                "out",
                dynamic_ports,
                lambda _properties: "bad",
            ),
        ),
    )
    _register_spec(registry, dynamic_spec)
    _register_spec(
        registry,
        _spec(
            "tests.dynamic_sink",
            PortSpec("value", "in", "data", STRING_DATA_TYPE_ID, required=True),
        ),
    )
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = _add(mutations, dynamic_spec.type_id)
    before = workspace.capture_snapshot()
    before_revision = workspace.mutation_revision
    with pytest.raises(ValueError, match="unknown data-type ID"):
        mutations.insert_dynamic_port(node.node_id, "outputs", 0)
    assert workspace.capture_snapshot() == before
    assert workspace.mutation_revision == before_revision

    edge_free_fragment = build_graph_fragment_payload(
        nodes=[
            node_instance_to_mapping(
                NodeInstance(
                    "dynamic",
                    dynamic_spec.type_id,
                    "Dynamic",
                    0.0,
                    0.0,
                    properties={"port_ids": ["bad"]},
                ),
                node_id_key="ref_id",
            )
        ],
        edges=[],
    )
    before_fragment = workspace.capture_snapshot()
    before_fragment_revision = workspace.mutation_revision
    assert insert_graph_fragment(
        model=model,
        workspace_id=workspace.workspace_id,
        fragment_payload=edge_free_fragment,
        delta_x=20.0,
        delta_y=20.0,
        registry=registry,
    ) == []
    assert workspace.capture_snapshot() == before_fragment
    assert workspace.mutation_revision == before_fragment_revision

    raw_source = model._add_node_record(
        workspace.workspace_id,
        type_id=dynamic_spec.type_id,
        title="Raw invalid source",
        x=100.0,
        y=0.0,
        properties={"port_ids": ["bad"]},
    )
    raw_target = _add(mutations, "tests.dynamic_sink", 200.0)
    before_unresolved = workspace.capture_snapshot()
    with pytest.raises(ValueError, match="unresolved:unknown_source"):
        mutations.add_edge(
            source_node_id=raw_source.node_id,
            source_port_key="bad",
            target_node_id=raw_target.node_id,
            target_port_key="value",
        )
    assert workspace.capture_snapshot() == before_unresolved
    raw_unresolved = model._add_edge_record(
        workspace.workspace_id,
        source_node_id=raw_source.node_id,
        source_port_key="bad",
        target_node_id=raw_target.node_id,
        target_port_key="value",
    )
    assert compile_runtime_workspace_snapshot(
        RuntimeWorkspace.from_workspace_data(workspace),
        registry=registry,
    ).edges == ()
    normalize_project_for_registry(model.project, registry)
    assert raw_unresolved.edge_id not in workspace.edges

    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    source = _add(mutations, "core.constant")
    other_source = _add(mutations, "core.constant", 100.0)
    other_sink = _add(mutations, "core.python_script", 200.0)
    shell = _add(mutations, "core.subnode", 300.0)
    pin = _add(
        mutations,
        "core.subnode_input",
        400.0,
        properties={
            "kind": "data",
            "data_type": STRING_DATA_TYPE_ID,
            "accepted_data_types": [],
        },
        parent_node_id=shell.node_id,
    )
    pruned = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="as_text",
        target_node_id=shell.node_id,
        target_port_key=pin.node_id,
    )
    preserved = mutations.add_edge(
        source_node_id=other_source.node_id,
        source_port_key="value",
        target_node_id=other_sink.node_id,
        target_port_key="payload",
    )

    mutations.set_node_properties(
        pin.node_id,
        {
            "data_type": BOOLEAN_DATA_TYPE_ID,
            "accepted_data_types": [],
        },
    )
    assert pruned.edge_id not in workspace.edges
    assert preserved.edge_id in workspace.edges


def test_fragment_compiler_normalization_quick_insert_and_route_use_catalog() -> None:
    registry = _typed_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    source = _add(mutations, "tests.string_source")
    target = _add(mutations, "tests.boolean_sink", 200.0)

    fragment_edge = EdgeInstance(
        edge_id="fragment-edge",
        source_node_id="source",
        source_port_key="value",
        target_node_id="target",
        target_port_key="value",
    )
    fragment = build_graph_fragment_payload(
        nodes=[
            node_instance_to_mapping(
                NodeInstance("source", source.type_id, source.title, 0.0, 0.0),
                node_id_key="ref_id",
            ),
            node_instance_to_mapping(
                NodeInstance("target", target.type_id, target.title, 200.0, 0.0),
                node_id_key="ref_id",
            ),
        ],
        edges=[
            edge_instance_to_mapping(
                fragment_edge,
                edge_id_key=None,
                source_node_id_key="source_ref_id",
                target_node_id_key="target_ref_id",
            )
        ],
    )
    before_fragment = workspace.capture_snapshot()
    assert insert_graph_fragment(
        model=model,
        workspace_id=workspace.workspace_id,
        fragment_payload=fragment,
        delta_x=20.0,
        delta_y=20.0,
        registry=registry,
    ) == []
    assert workspace.capture_snapshot() == before_fragment

    invalid = model._add_edge_record(
        workspace.workspace_id,
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=target.node_id,
        target_port_key="value",
    )
    union_target = _add(mutations, "tests.union_sink", 400.0)
    valid = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=union_target.node_id,
        target_port_key="value",
    )
    compiled = compile_runtime_workspace_snapshot(
        RuntimeWorkspace.from_workspace_data(workspace),
        registry=registry,
    )
    assert {edge.edge_id for edge in compiled.edges} == {valid.edge_id}

    route_payload = build_edge_payload(
        graph_theme=resolve_graph_theme("stitch_light"),
        workspace_edges=[invalid, valid],
        workspace_nodes=dict(workspace.nodes),
        node_specs={
            source.node_id: registry.get_spec(source.type_id),
            target.node_id: registry.get_spec(target.type_id),
            union_target.node_id: registry.get_spec(union_target.type_id),
        },
        data_types=registry.data_types,
    )
    warnings = {
        str(item["edge_id"]): bool(item["data_type_warning"])
        for item in route_payload
    }
    assert warnings == {invalid.edge_id: True, valid.edge_id: False}

    items = build_combined_library_items(
        registry_items=build_registry_library_items(
            registry_specs=registry.all_specs(), data_types=registry.data_types,
        ),
        custom_workflow_items=[],
    )
    results = build_connection_quick_insert_items(
        combined_items=items,
        data_types=registry.data_types,
        query="",
        source_direction="out",
        source_kind="data",
        source_data_type=STRING_DATA_TYPE_ID,
        limit=100,
    )
    result_ids = {str(item["type_id"]) for item in results}
    assert "tests.union_sink" in result_ids
    assert "tests.boolean_sink" not in result_ids
    assert mutations.ports_compatible(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=union_target.node_id,
        target_port_key="value",
    )
    assert not mutations.ports_compatible(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=target.node_id,
        target_port_key="value",
    )

    normalize_project_for_registry(model.project, registry)
    assert invalid.edge_id not in workspace.edges


def test_compiler_revalidates_synthetic_edges_without_conversion_chaining() -> None:
    registry = _typed_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    source = _add(mutations, "tests.convertible_source")
    shell = _add(mutations, "core.subnode", 100.0)
    pin = _add(
        mutations,
        "core.subnode_input",
        200.0,
        properties={
            "kind": "data",
            "data_type": _TARGET_TYPE_ID,
            "accepted_data_types": [],
        },
        parent_node_id=shell.node_id,
    )
    target = _add(
        mutations,
        "tests.chain_sink",
        300.0,
        parent_node_id=shell.node_id,
    )
    mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=shell.node_id,
        target_port_key=pin.node_id,
    )
    mutations.add_edge(
        source_node_id=pin.node_id,
        source_port_key="pin",
        target_node_id=target.node_id,
        target_port_key="value",
    )

    compiled = compile_runtime_workspace_snapshot(
        RuntimeWorkspace.from_workspace_data(workspace),
        registry=registry,
    )

    assert {node.node_id for node in compiled.nodes} == {
        source.node_id,
        target.node_id,
    }
    assert compiled.edges == ()


def test_compiler_prunes_unresolved_registry_endpoints_only_with_registry() -> None:
    registry = _typed_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    missing = model._add_node_record(
        workspace.workspace_id,
        type_id="addon.missing.node",
        title="Missing add-on",
        x=0.0,
        y=0.0,
    )
    target = _add(mutations, "tests.string_sink", 200.0)
    edge = model._add_edge_record(
        workspace.workspace_id,
        source_node_id=missing.node_id,
        source_port_key="value",
        target_node_id=target.node_id,
        target_port_key="value",
    )
    runtime_workspace = RuntimeWorkspace.from_workspace_data(workspace)

    registry_compiled = compile_runtime_workspace_snapshot(
        runtime_workspace,
        registry=registry,
    )
    structural_compiled = compile_runtime_workspace_snapshot(
        runtime_workspace,
        registry=None,
    )

    assert registry_compiled.edges == ()
    assert {candidate.edge_id for candidate in structural_compiled.edges} == {
        edge.edge_id
    }
