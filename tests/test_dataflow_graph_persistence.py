from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ea_node_editor.app_preferences import normalize_app_preferences_document
from ea_node_editor.custom_workflows.global_store import (
    load_global_custom_workflow_definitions,
    save_global_custom_workflow_definitions,
)
from ea_node_editor.custom_workflows.file_codec import (
    CUSTOM_WORKFLOW_FILE_VERSION,
    from_custom_workflow_file_document,
    to_custom_workflow_file_document,
)
from ea_node_editor.graph.fragment_payloads import (
    GRAPH_FRAGMENT_VERSION,
    build_graph_fragment_payload,
    normalize_graph_fragment_payload,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.graph.subnode_contract import resolve_subnode_pin_definition
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.nodes.builtins.core import StreamGateNodePlugin
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    DynamicPortRenameMode,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    DOUBLE_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
)
from ea_node_editor.settings import (
    APP_PREFERENCES_KIND,
    APP_PREFERENCES_VERSION,
    SCHEMA_VERSION,
)


class _Plugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _dynamic_input_ports(properties) -> tuple[PortSpec, ...]:  # noqa: ANN001
    return tuple(
        PortSpec(
            str(key),
            "in",
            "data",
            INTEGER_DATA_TYPE_ID,
            label=f"Variable {key}",
            required=False,
        )
        for key in properties["input_names"]
    )


def _dynamic_input_key_factory(properties) -> str:  # noqa: ANN001
    used = set(properties["input_names"])
    suffix = 1
    while f"input{suffix}" in used:
        suffix += 1
    return f"input{suffix}"


def _colliding_dynamic_input_key_factory(_properties) -> str:  # noqa: ANN001
    return "alpha"


def _dynamic_input_key_renamer(
    _properties,
    _old_key: str,
    value: str,
) -> str:  # noqa: ANN001
    return value.strip()


def _dynamic_input_spec(
    *,
    type_id: str = "tests.dynamic_inputs",
    key_factory=_dynamic_input_key_factory,  # noqa: ANN001
    rename_mode: DynamicPortRenameMode = "key",
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name="Dynamic Inputs",
        category_path=("Tests",),
        icon="",
        ports=(),
        properties=(
            PropertySpec(
                "input_names",
                "json",
                ["alpha", "beta"],
                "Inputs",
                inspector_visible=False,
            ),
            PropertySpec("mode", "str", "unchanged", "Mode"),
        ),
        dynamic_port_groups=(
            DynamicPortGroupSpec(
                "inputs",
                "input_names",
                "in",
                _dynamic_input_ports,
                key_factory,
                rename_mode=rename_mode,
                key_renamer=(
                    _dynamic_input_key_renamer
                    if rename_mode == "key"
                    else None
                ),
            ),
        ),
    )


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    specs = (
        NodeTypeSpec(
            type_id="tests.source",
            display_name="Source",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", INTEGER_DATA_TYPE_ID),),
            properties=(),
        ),
        NodeTypeSpec(
            type_id="tests.sink",
            display_name="Sink",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value",
                    "in",
                    "data",
                    INTEGER_DATA_TYPE_ID,
                    required=True,
                ),
            ),
            properties=(),
        ),
        NodeTypeSpec(
            type_id="core.subnode",
            display_name="Subnode",
            category_path=("Core",),
            icon="",
            ports=(),
            properties=(),
        ),
        StreamGateNodePlugin().spec(),
        _dynamic_input_spec(),
        _dynamic_input_spec(
            type_id="tests.dynamic_collision",
            key_factory=_colliding_dynamic_input_key_factory,
        ),
        _dynamic_input_spec(
            type_id="tests.dynamic_no_rename",
            rename_mode="none",
        ),
    )
    for spec in specs:
        registry.register(lambda spec=spec: _Plugin(spec))
    return registry


def _fragment_node(ref_id: str, type_id: str) -> dict[str, object]:
    return {
        "ref_id": ref_id,
        "type_id": type_id,
        "title": type_id,
        "x": 0.0,
        "y": 0.0,
        "properties": {},
        "exposed_ports": {},
        "port_labels": {},
    }


def test_data_wires_replace_append_disable_and_round_trip_in_input_order() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source_a = mutations.add_node(type_id="tests.source", title="A", x=0, y=0)
    source_b = mutations.add_node(type_id="tests.source", title="B", x=0, y=100)
    source_c = mutations.add_node(type_id="tests.source", title="C", x=0, y=200)
    sink = mutations.add_node(type_id="tests.sink", title="Sink", x=200, y=0)

    first = mutations.add_edge(
        source_node_id=source_a.node_id,
        source_port_key="value",
        target_node_id=sink.node_id,
        target_port_key="value",
    )
    second = mutations.add_edge(
        source_node_id=source_b.node_id,
        source_port_key="value",
        target_node_id=sink.node_id,
        target_port_key="value",
        append_requested=True,
    )
    assert (first.input_order, second.input_order) == (0, 1)
    assert (
        mutations.add_edge(
            source_node_id=source_b.node_id,
            source_port_key="value",
            target_node_id=sink.node_id,
            target_port_key="value",
            append_requested=True,
        ).edge_id
        == second.edge_id
    )
    assert (
        mutations.add_edge(
            source_node_id=source_a.node_id,
            source_port_key="value",
            target_node_id=sink.node_id,
            target_port_key="value",
        ).edge_id
        == first.edge_id
    )
    assert len(workspace.edges) == 2
    assert mutations.set_edge_enabled(first.edge_id, False)
    mutations.set_port_modifiers(sink.node_id, "value", ["clean", "graft"])
    mutations.set_principal_input_port(sink.node_id, "value")
    assert not workspace.edges[first.edge_id].enabled
    assert workspace.nodes[sink.node_id].port_modifiers == {"value": ("graft", "clean")}
    assert workspace.nodes[sink.node_id].principal_input_port_id == "value"
    assert mutations.set_edge_enabled(first.edge_id, True)
    assert mutations.set_edge_enabled(first.edge_id, False)

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    edge_docs = document["workspaces"][0]["edges"]
    assert [edge["input_order"] for edge in edge_docs] == [0, 1]
    assert [edge["enabled"] for edge in edge_docs] == [False, True]
    loaded = JsonProjectSerializer(registry).from_document(document)
    loaded_workspace = loaded.workspaces[workspace.workspace_id]
    assert [edge.input_order for edge in loaded_workspace.edges.values()] == [0, 1]
    assert loaded_workspace.nodes[sink.node_id].port_modifiers == {
        "value": ("graft", "clean")
    }
    assert loaded_workspace.nodes[sink.node_id].principal_input_port_id == "value"

    replacement = model.validated_mutations(workspace.workspace_id, registry).add_edge(
        source_node_id=source_c.node_id,
        source_port_key="value",
        target_node_id=sink.node_id,
        target_port_key="value",
    )
    assert replacement.input_order == 0
    assert len(workspace.edges) == 1


def test_edge_display_mode_visual_style_round_trips() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source_a = mutations.add_node(type_id="tests.source", title="A", x=0, y=0)
    source_b = mutations.add_node(type_id="tests.source", title="B", x=0, y=100)
    sink = mutations.add_node(type_id="tests.sink", title="Sink", x=200, y=0)
    first = mutations.add_edge(
        source_node_id=source_a.node_id,
        source_port_key="value",
        target_node_id=sink.node_id,
        target_port_key="value",
        visual_style={
            "stroke_pattern": "dashed",
            "custom": {"weight": 2},
            "display_mode": "faint",
        },
    )
    second = mutations.add_edge(
        source_node_id=source_b.node_id,
        source_port_key="value",
        target_node_id=sink.node_id,
        target_port_key="value",
        append_requested=True,
        visual_style={"arrow": {"kind": "none"}, "display_mode": "default"},
    )

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    loaded = JsonProjectSerializer(registry).from_document(document)
    loaded_edges = loaded.workspaces[workspace.workspace_id].edges
    assert loaded_edges[first.edge_id].visual_style == workspace.edges[first.edge_id].visual_style
    assert loaded_edges[second.edge_id].visual_style == workspace.edges[second.edge_id].visual_style


def test_dynamic_port_insert_remove_is_ordered_and_cleans_all_incident_state() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    gate = mutations.add_node(type_id="core.stream_gate", title="Gate", x=0, y=0)
    sink_a = mutations.add_node(type_id="tests.sink", title="Sink A", x=200, y=0)
    sink_b = mutations.add_node(type_id="tests.sink", title="Sink B", x=200, y=100)

    inserted = mutations.insert_dynamic_port(gate.node_id, "outputs", 1)
    assert inserted == "output_2"
    assert gate.properties["output_port_ids"] == ["output_0", inserted, "output_1"]
    enabled_edge = mutations.add_edge(
        source_node_id=gate.node_id,
        source_port_key=inserted,
        target_node_id=sink_a.node_id,
        target_port_key="value",
    )
    disabled_edge = mutations.add_edge(
        source_node_id=gate.node_id,
        source_port_key=inserted,
        target_node_id=sink_b.node_id,
        target_port_key="value",
    )
    assert mutations.set_edge_enabled(disabled_edge.edge_id, False)
    gate.exposed_ports[inserted] = False
    gate.port_labels[inserted] = "Temporary"
    gate.port_modifiers[inserted] = ("graft",)

    removed, removed_edges = mutations.remove_dynamic_port(
        gate.node_id,
        "outputs",
        inserted,
    )

    assert removed == inserted
    assert removed_edges == (enabled_edge.edge_id, disabled_edge.edge_id)
    assert not set(removed_edges).intersection(workspace.edges)
    assert gate.properties["output_port_ids"] == ["output_0", "output_1"]
    assert inserted not in gate.exposed_ports
    assert inserted not in gate.port_labels
    assert inserted not in gate.port_modifiers


def test_dynamic_port_label_rename_preserves_identity_wires_and_can_clear() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    gate = mutations.add_node(type_id="core.stream_gate", title="Gate", x=0, y=0)
    sink = mutations.add_node(type_id="tests.sink", title="Sink", x=200, y=0)
    edge = mutations.add_edge(
        source_node_id=gate.node_id,
        source_port_key="output_0",
        target_node_id=sink.node_id,
        target_port_key="value",
    )

    assert mutations.set_port_label(
        gate.node_id,
        "output_0",
        "Direct",
    )
    assert gate.port_labels["output_0"] == "Direct"
    assert mutations.rename_dynamic_port(
        gate.node_id,
        "outputs",
        "output_0",
        "Accepted",
    ) == ("output_0", ())
    assert gate.properties["output_port_ids"] == ["output_0", "output_1"]
    assert gate.port_labels["output_0"] == "Accepted"
    assert edge.edge_id in workspace.edges
    assert mutations.rename_dynamic_port(
        gate.node_id,
        "outputs",
        "output_0",
        "Accepted",
    ) is None
    assert mutations.rename_dynamic_port(
        gate.node_id,
        "outputs",
        "output_0",
        "",
    ) == ("output_0", ())
    assert "output_0" not in gate.port_labels


def test_model_viewer_dynamic_scenes_preserve_identity_styles_and_serialization() -> None:
    from ea_node_editor.nodes.bootstrap import build_builtin_registry

    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    viewer = mutations.add_node(type_id="model.viewer", title="Viewer", x=0, y=0)
    source = mutations.add_node(type_id="geometry.cylinder", title="Body", x=0, y=100)
    second = mutations.insert_dynamic_port(viewer.node_id, "scenes", 1)
    third = mutations.insert_dynamic_port(viewer.node_id, "scenes", 1)
    assert viewer.properties["scene_input_ids"] == ["scene_1", third, second]
    edge = mutations.add_edge(source_node_id=source.node_id, source_port_key="body", target_node_id=viewer.node_id, target_port_key=second)
    mutations.rename_dynamic_port(viewer.node_id, "scenes", second, "Housing")
    mutations.set_node_property(viewer.node_id, "scene_styles", {second: {"opacity": 0.4, "color": "#AbCDef"}})
    serializer = JsonProjectSerializer(registry)
    document = serializer.to_persistent_document(model.project)
    loaded = serializer.from_document(document).workspaces[workspace.workspace_id]
    assert loaded.nodes[viewer.node_id].properties["scene_input_ids"] == ["scene_1", third, second]
    assert loaded.nodes[viewer.node_id].port_labels[second] == "Housing"
    assert loaded.nodes[viewer.node_id].properties["scene_styles"][second] == {"opacity": 0.4, "color": "#abcdef"}
    assert loaded.edges[edge.edge_id].target_port_key == second
    mutations.remove_dynamic_port(viewer.node_id, "scenes", third)
    assert workspace.edges[edge.edge_id].target_port_key == second
    _, removed_edges = mutations.remove_dynamic_port(viewer.node_id, "scenes", second)
    assert removed_edges == (edge.edge_id,)
    normalized = serializer.from_document(serializer.to_persistent_document(model.project))
    assert second not in normalized.workspaces[workspace.workspace_id].nodes[viewer.node_id].properties["scene_styles"]
    new_port = mutations.insert_dynamic_port(viewer.node_id, "scenes", 1)
    assert new_port not in {second, third}
    assert new_port not in viewer.properties["scene_styles"]
    mutations.remove_dynamic_port(viewer.node_id, "scenes", new_port)
    with pytest.raises(ValueError):
        mutations.remove_dynamic_port(viewer.node_id, "scenes", "scene_1")


def test_key_rename_prunes_wires_and_old_sparse_state_without_transfer() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(type_id="tests.source", title="Source", x=0, y=0)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=200,
        y=0,
    )
    edge = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=dynamic.node_id,
        target_port_key="alpha",
    )
    dynamic.exposed_ports["alpha"] = False
    dynamic.port_labels["alpha"] = "Ignored"
    dynamic.port_modifiers["alpha"] = ("graft",)
    dynamic.principal_input_port_id = "alpha"

    renamed, removed_edges = mutations.rename_dynamic_port(
        dynamic.node_id,
        "inputs",
        "alpha",
        "gamma",
    )

    assert renamed == "gamma"
    assert removed_edges == (edge.edge_id,)
    assert dynamic.properties["input_names"] == ["gamma", "beta"]
    assert edge.edge_id not in workspace.edges
    assert "alpha" not in dynamic.exposed_ports
    assert "alpha" not in dynamic.port_labels
    assert "alpha" not in dynamic.port_modifiers
    assert dynamic.principal_input_port_id is None
    assert "gamma" not in dynamic.exposed_ports
    assert "gamma" not in dynamic.port_labels
    assert "gamma" not in dynamic.port_modifiers
    spec = registry.get_spec(dynamic.type_id)
    gamma = next(
        port
        for port in effective_ports(
            node=dynamic,
            spec=spec,
            workspace_nodes=workspace.nodes,
        )
        if port.key == "gamma"
    )
    assert gamma.label == "Variable gamma"


def test_registry_normalization_keeps_only_permitted_dynamic_port_labels() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=0,
        y=0,
    )
    gate = mutations.add_node(
        type_id="core.stream_gate",
        title="Gate",
        x=0,
        y=100,
    )
    no_rename = mutations.add_node(
        type_id="tests.dynamic_no_rename",
        title="No Rename",
        x=0,
        y=200,
    )
    with pytest.raises(ValueError, match="does not allow label rename"):
        mutations.set_port_label(dynamic.node_id, "alpha", "Rejected")
    with pytest.raises(ValueError, match="does not allow label rename"):
        mutations.set_port_label(no_rename.node_id, "alpha", "Rejected")
    assert dynamic.port_labels == {}
    assert no_rename.port_labels == {}
    dynamic.port_labels["alpha"] = "Not permitted"
    no_rename.port_labels["alpha"] = "Also not permitted"
    gate.port_labels["output_0"] = "Permitted"

    normalize_project_for_registry(model.project, registry)

    assert dynamic.port_labels == {}
    assert no_rename.port_labels == {}
    assert gate.port_labels == {"output_0": "Permitted"}


def test_dynamic_port_preflight_rejects_collisions_limits_and_backing_writes_atomically() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=0,
        y=0,
    )
    inserted = mutations.insert_dynamic_port(dynamic.node_id, "inputs", 1)
    assert inserted == "input1"
    assert dynamic.properties["input_names"] == ["alpha", "input1", "beta"]
    before = dict(dynamic.properties)
    with pytest.raises(ValueError, match="already exists"):
        mutations.rename_dynamic_port(dynamic.node_id, "inputs", "alpha", "beta")
    assert dynamic.properties == before
    with pytest.raises(IndexError):
        mutations.insert_dynamic_port(dynamic.node_id, "inputs", 99)
    assert dynamic.properties == before
    with pytest.raises(ValueError, match="backing properties"):
        mutations.set_node_property(dynamic.node_id, "input_names", ["changed"])
    with pytest.raises(ValueError, match="backing properties"):
        mutations.set_node_properties(
            dynamic.node_id,
            {"mode": "changed", "input_names": ["changed"]},
        )
    assert dynamic.properties == before

    colliding = mutations.add_node(
        type_id="tests.dynamic_collision",
        title="Collision",
        x=0,
        y=100,
    )
    collision_before = dict(colliding.properties)
    with pytest.raises(ValueError, match="already exists"):
        mutations.insert_dynamic_port(colliding.node_id, "inputs", 1)
    assert colliding.properties == collision_before

    one_output = mutations.add_node(
        type_id="core.stream_gate",
        title="One",
        x=0,
        y=200,
        properties={"output_port_ids": ["only"]},
    )
    with pytest.raises(ValueError, match="retain at least 1"):
        mutations.remove_dynamic_port(one_output.node_id, "outputs", "only")
    assert one_output.properties["output_port_ids"] == ["only"]


def test_dynamic_port_stream_gate_adapters_and_persistence_preserve_stable_ids() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    gate = mutations.add_node(
        type_id="core.stream_gate",
        title="Gate",
        x=0,
        y=0,
        properties={"output_port_ids": ["stable"]},
    )
    inserted = mutations.insert_dynamic_port(gate.node_id, "outputs", 1)
    assert gate.properties["output_port_ids"] == ["stable", inserted]
    removed, removed_edges = mutations.remove_dynamic_port(
        gate.node_id,
        "outputs",
        inserted,
    )
    assert (removed, removed_edges) == (inserted, ())

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    loaded = JsonProjectSerializer(registry).from_document(document)
    loaded_gate = loaded.workspaces[workspace.workspace_id].nodes[gate.node_id]
    assert loaded_gate.properties["output_port_ids"] == ["stable"]
    assert [
        port.key
        for port in effective_ports(
            node=loaded_gate,
            spec=registry.get_spec(loaded_gate.type_id),
            workspace_nodes=loaded.workspaces[workspace.workspace_id].nodes,
        )
        if port.direction == "out"
    ] == ["stable"]


def test_dynamic_port_properties_and_sparse_state_round_trip_in_schema_five() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(type_id="tests.source", title="Source", x=0, y=0)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=200,
        y=0,
        properties={"input_names": ["beta", "alpha"]},
    )
    edge = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=dynamic.node_id,
        target_port_key="alpha",
    )
    dynamic.exposed_ports["beta"] = False
    mutations.set_port_modifiers(dynamic.node_id, "alpha", ["graft"])
    mutations.set_principal_input_port(dynamic.node_id, "alpha")

    cloned_dynamic = dynamic.clone()
    duplicated_workspace = model.duplicate_workspace(workspace.workspace_id)
    duplicated_dynamic = duplicated_workspace.nodes[dynamic.node_id]
    for copied in (cloned_dynamic, duplicated_dynamic):
        assert copied.properties["input_names"] == ["beta", "alpha"]
        assert copied.exposed_ports["beta"] is False
        assert copied.port_modifiers == {"alpha": ("graft",)}
        assert copied.principal_input_port_id == "alpha"

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    loaded = JsonProjectSerializer(registry).from_document(document)
    loaded_workspace = loaded.workspaces[workspace.workspace_id]
    loaded_dynamic = loaded_workspace.nodes[dynamic.node_id]

    assert document["schema_version"] == SCHEMA_VERSION == 5
    assert loaded_dynamic.properties["input_names"] == ["beta", "alpha"]
    assert loaded_dynamic.exposed_ports["beta"] is False
    assert loaded_dynamic.port_modifiers == {"alpha": ("graft",)}
    assert loaded_dynamic.principal_input_port_id == "alpha"
    assert loaded_workspace.edges[edge.edge_id].target_port_key == "alpha"


def test_dynamic_port_registry_normalization_resolves_defaults_before_edges() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    gate = mutations.add_node(type_id="core.stream_gate", title="Gate", x=0, y=0)
    sink = mutations.add_node(type_id="tests.sink", title="Sink", x=200, y=0)
    edge = mutations.add_edge(
        source_node_id=gate.node_id,
        source_port_key="output_0",
        target_node_id=sink.node_id,
        target_port_key="value",
    )

    gate.properties["output_port_ids"] = {"wrong": "shape"}
    normalize_project_for_registry(model.project, registry)
    assert gate.properties["output_port_ids"] == ["output_0", "output_1"]
    assert edge.edge_id in workspace.edges

    gate.properties.pop("output_port_ids")
    normalize_project_for_registry(model.project, registry)
    assert "output_port_ids" not in gate.properties
    assert edge.edge_id in workspace.edges
    assert [
        port.key
        for port in effective_ports(
            node=gate,
            spec=registry.get_spec(gate.type_id),
            workspace_nodes=workspace.nodes,
        )
        if port.direction == "out"
    ] == ["output_0", "output_1"]


def test_current_fragment_preserves_ordered_dynamic_keys_and_endpoints() -> None:
    registry = _registry()
    fragment = {
        "kind": "ea-node-editor/graph-fragment",
        "version": GRAPH_FRAGMENT_VERSION,
        "nodes": [
            _fragment_node("source", "tests.source"),
            {
                **_fragment_node("dynamic", "tests.dynamic_inputs"),
                "properties": {
                    "input_names": ["beta", "alpha"],
                    "mode": "unchanged",
                },
                "exposed_ports": {"beta": False},
                "port_modifiers": {"alpha": ["graft"]},
                "principal_input_port_id": "alpha",
            },
        ],
        "edges": [
            {
                "source_ref_id": "source",
                "source_port_key": "value",
                "target_ref_id": "dynamic",
                "target_port_key": "alpha",
            }
        ],
    }

    normalized = normalize_graph_fragment_payload(fragment, registry=registry)

    assert normalized is not None
    assert normalized["version"] == GRAPH_FRAGMENT_VERSION == 2
    assert normalized["nodes"][1]["properties"]["input_names"] == ["beta", "alpha"]
    assert normalized["nodes"][1]["exposed_ports"]["beta"] is False
    assert normalized["nodes"][1]["port_modifiers"] == {"alpha": ["graft"]}
    assert normalized["nodes"][1]["principal_input_port_id"] == "alpha"
    assert normalized["edges"][0]["target_port_key"] == "alpha"


def test_dynamic_port_fragment_copy_paste_preserves_keys_edges_and_sparse_state() -> (
    None
):
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(type_id="tests.source", title="Source", x=0, y=0)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=200,
        y=0,
        properties={"input_names": ["beta", "alpha"]},
    )
    mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=dynamic.node_id,
        target_port_key="alpha",
    )
    dynamic.exposed_ports["beta"] = False
    mutations.set_port_modifiers(dynamic.node_id, "alpha", ["graft"])
    mutations.set_principal_input_port(dynamic.node_id, "alpha")

    fragment_data = build_subtree_fragment_payload_data(
        workspace=workspace,
        selected_node_ids=[source.node_id, dynamic.node_id],
    )
    assert fragment_data is not None
    fragment = build_graph_fragment_payload(**fragment_data)
    pasted_source_id, pasted_dynamic_id = insert_graph_fragment(
        model=model,
        workspace_id=workspace.workspace_id,
        fragment_payload=fragment,
        delta_x=300.0,
        delta_y=0.0,
        registry=registry,
    )
    pasted_dynamic = workspace.nodes[pasted_dynamic_id]
    pasted_edges = [
        edge
        for edge in workspace.edges.values()
        if edge.source_node_id == pasted_source_id
        and edge.target_node_id == pasted_dynamic_id
    ]

    assert pasted_dynamic.properties["input_names"] == ["beta", "alpha"]
    assert pasted_dynamic.exposed_ports["beta"] is False
    assert pasted_dynamic.port_modifiers == {"alpha": ("graft",)}
    assert pasted_dynamic.principal_input_port_id == "alpha"
    assert len(pasted_edges) == 1
    assert pasted_edges[0].target_port_key == "alpha"


def test_dynamic_port_key_rename_snapshot_restore_restores_exact_state() -> None:
    registry = _registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(type_id="tests.source", title="Source", x=0, y=0)
    dynamic = mutations.add_node(
        type_id="tests.dynamic_inputs",
        title="Dynamic",
        x=200,
        y=0,
    )
    edge = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="value",
        target_node_id=dynamic.node_id,
        target_port_key="alpha",
    )
    dynamic.exposed_ports["alpha"] = True
    mutations.set_port_modifiers(dynamic.node_id, "alpha", ["graft"])
    mutations.set_principal_input_port(dynamic.node_id, "alpha")
    before = workspace.capture_snapshot()

    assert mutations.rename_dynamic_port(
        dynamic.node_id,
        "inputs",
        "alpha",
        "gamma",
    ) == ("gamma", (edge.edge_id,))
    assert dynamic.properties["input_names"] == ["gamma", "beta"]
    assert edge.edge_id not in workspace.edges
    assert "alpha" not in dynamic.exposed_ports
    assert "alpha" not in dynamic.port_modifiers
    assert dynamic.principal_input_port_id is None

    workspace.restore_snapshot(before)
    restored = workspace.nodes[dynamic.node_id]
    assert workspace.capture_snapshot() == before
    assert restored.properties["input_names"] == ["alpha", "beta"]
    assert restored.exposed_ports["alpha"] is True
    assert restored.port_modifiers == {"alpha": ("graft",)}
    assert restored.principal_input_port_id == "alpha"
    assert workspace.edges[edge.edge_id].target_port_key == "alpha"


def test_v4_project_and_v1_fragments_cut_over_without_overwriting_source_state() -> (
    None
):
    registry = _registry()
    fragment_v1 = {
        "kind": "ea-node-editor/graph-fragment",
        "version": 1,
        "nodes": [
            _fragment_node("source", "tests.source"),
            _fragment_node("source_b", "tests.source"),
            _fragment_node("sink", "tests.sink"),
            {
                **_fragment_node("shell", "core.subnode"),
                "exposed_ports": {"failed_pin": True},
            },
            {
                **_fragment_node("failed_pin", "core.subnode_output"),
                "properties": {"kind": "failed", "data_type": "any"},
                "parent_node_id": "shell",
            },
            _fragment_node("start", "core.start"),
            _fragment_node("hpc_status", "hpc.on_status"),
        ],
        "edges": [
            {
                "source_ref_id": "source",
                "source_port_key": "value",
                "target_ref_id": "sink",
                "target_port_key": "value",
            },
            {
                "source_ref_id": "source_b",
                "source_port_key": "value",
                "target_ref_id": "sink",
                "target_port_key": "value",
                "enabled": False,
                "input_order": 99,
            },
            {
                "source_ref_id": "start",
                "source_port_key": "exec_out",
                "target_ref_id": "sink",
                "target_port_key": "exec_in",
            },
        ],
    }
    fragment_report: list[str] = []
    migrated_fragment = normalize_graph_fragment_payload(
        fragment_v1,
        registry=registry,
        migration_report=fragment_report,
    )
    assert migrated_fragment is not None
    assert fragment_report == sorted(fragment_report)
    assert migrated_fragment["version"] == GRAPH_FRAGMENT_VERSION
    assert [node["ref_id"] for node in migrated_fragment["nodes"]] == [
        "source",
        "source_b",
        "sink",
        "shell",
    ]
    assert migrated_fragment["nodes"][3]["exposed_ports"] == {}
    assert [edge["enabled"] for edge in migrated_fragment["edges"]] == [True, True]
    assert [edge["input_order"] for edge in migrated_fragment["edges"]] == [0, 1]
    assert (
        "Removed retired node hpc_status (hpc.on_status) from graph fragment."
        in fragment_report
    )

    project_v4 = {
        "schema_version": 4,
        "project_id": "project_v4",
        "name": "Legacy",
        "active_workspace_id": "workspace",
        "workspace_order": ["workspace"],
        "workspaces": [
            {
                "workspace_id": "workspace",
                "name": "Workspace",
                "active_view_id": "view",
                "views": [{"view_id": "view", "name": "V1"}],
                "nodes": [
                    {
                        **_fragment_node("source", "tests.source"),
                        "node_id": "source",
                        "exposed_ports": {"value": True, "on_failed": True},
                        "locked_ports": {"on_failed": True},
                        "port_labels": {"on_failed": "On Failure"},
                    },
                    {**_fragment_node("sink", "tests.sink"), "node_id": "sink"},
                    {**_fragment_node("start", "core.start"), "node_id": "start"},
                    {
                        **_fragment_node("hpc_status", "hpc.on_status"),
                        "node_id": "hpc_status",
                    },
                ],
                "edges": [
                    {
                        "edge_id": "data",
                        "source_node_id": "source",
                        "source_port_key": "value",
                        "target_node_id": "sink",
                        "target_port_key": "value",
                    },
                    {
                        "edge_id": "control",
                        "source_node_id": "start",
                        "source_port_key": "exec_out",
                        "target_node_id": "sink",
                        "target_port_key": "exec_in",
                    },
                    {
                        "edge_id": "failure-control",
                        "source_node_id": "source",
                        "source_port_key": "on_failed",
                        "target_node_id": "sink",
                        "target_port_key": "value",
                    },
                ],
            }
        ],
        "metadata": {
            "custom_workflows": [
                {
                    "workflow_id": "empty_workflow",
                    "name": "Empty after cutover",
                    "fragment": {
                        "kind": "ea-node-editor/graph-fragment",
                        "version": 1,
                        "nodes": [_fragment_node("start_only", "core.start")],
                        "edges": [],
                    },
                },
                {
                    "workflow_id": "surviving_workflow",
                    "name": "Survives",
                    "fragment": {
                        "kind": "ea-node-editor/graph-fragment",
                        "version": 1,
                        "nodes": [
                            _fragment_node("source_only", "tests.source"),
                            _fragment_node("retired_start", "core.start"),
                        ],
                        "edges": [
                            {
                                "source_ref_id": "retired_start",
                                "source_port_key": "exec_out",
                                "target_ref_id": "source_only",
                                "target_port_key": "value",
                            }
                        ],
                    },
                },
            ]
        },
    }
    serializer = JsonProjectSerializer(registry)
    loaded = serializer.from_document(project_v4)
    assert project_v4["schema_version"] == 4
    assert project_v4["metadata"]["custom_workflows"][0]["fragment"]["version"] == 1
    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.migration_source_schema_version == 4
    assert loaded.migration_report == tuple(sorted(loaded.migration_report))
    assert loaded.workspaces["workspace"].dirty
    assert set(loaded.workspaces["workspace"].nodes) == {"source", "sink"}
    assert set(loaded.workspaces["workspace"].edges) == {"data"}
    assert (
        "Removed retired node hpc_status (hpc.on_status)."
        in loaded.migration_report
    )
    assert (
        "on_failed" not in loaded.workspaces["workspace"].nodes["source"].exposed_ports
    )
    assert not hasattr(loaded.workspaces["workspace"].nodes["source"], "locked_ports")
    assert "on_failed" not in loaded.workspaces["workspace"].nodes["source"].port_labels
    assert [item["workflow_id"] for item in loaded.metadata["custom_workflows"]] == [
        "surviving_workflow"
    ]
    assert (
        loaded.metadata["custom_workflows"][0]["fragment"]["version"]
        == GRAPH_FRAGMENT_VERSION
    )
    assert "Removed empty custom workflow empty_workflow." in loaded.migration_report
    assert (
        "Removed retired node retired_start (core.start) from custom workflow surviving_workflow."
        in loaded.migration_report
    )

    unresolved = {**project_v4, "project_id": "unresolved"}
    unresolved["workspaces"] = [
        {
            **project_v4["workspaces"][0],
            "nodes": [
                {
                    **_fragment_node("missing", "addon.missing.node"),
                    "node_id": "missing",
                }
            ],
            "edges": [],
        }
    ]
    try:
        serializer.from_document(unresolved)
    except ValueError as exc:
        assert "unresolved add-ons" in str(exc)
    else:
        raise AssertionError("Legacy unresolved add-ons must be rejected")


def test_dynamic_port_custom_workflow_and_preferences_versions_cut_over() -> None:
    fragment = {
        "kind": "ea-node-editor/graph-fragment",
        "version": 1,
        "nodes": [
            {
                **_fragment_node("dynamic", "tests.dynamic_inputs"),
                "properties": {"input_names": ["beta", "alpha"]},
            }
        ],
        "edges": [],
    }
    legacy_workflow = {
        "kind": "ea-node-editor/custom-workflow",
        "version": 1,
        "workflow": {
            "workflow_id": "workflow",
            "name": "Workflow",
            "ports": [],
            "fragment": fragment,
        },
    }
    registry = _registry()
    workflow_report: list[str] = []
    definition = from_custom_workflow_file_document(
        legacy_workflow,
        registry=registry,
        migration_report=workflow_report,
    )
    assert definition["fragment"]["version"] == GRAPH_FRAGMENT_VERSION
    assert definition["fragment"]["nodes"][0]["properties"]["input_names"] == [
        "beta",
        "alpha",
    ]
    assert (
        to_custom_workflow_file_document(definition)["version"]
        == CUSTOM_WORKFLOW_FILE_VERSION
    )
    assert workflow_report == sorted(workflow_report)
    assert "Migrated custom workflow file version 1 to 2." in workflow_report

    unresolved_workflow = {
        **legacy_workflow,
        "workflow": {
            **legacy_workflow["workflow"],
            "fragment": {
                **fragment,
                "nodes": [_fragment_node("missing", "addon.missing.node")],
            },
        },
    }
    try:
        from_custom_workflow_file_document(unresolved_workflow, registry=registry)
    except ValueError as exc:
        assert "unresolved add-ons" in str(exc)
    else:
        raise AssertionError(
            "Legacy custom workflow unresolved add-ons must be rejected"
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "custom_workflows_global.json"
        legacy_store = {
            "kind": "ea-node-editor/custom-workflow-library",
            "version": 1,
            "custom_workflows": [
                legacy_workflow["workflow"],
                {
                    "workflow_id": "empty_workflow",
                    "name": "Empty Workflow",
                    "ports": [],
                    "fragment": {
                        "kind": "ea-node-editor/graph-fragment",
                        "version": 1,
                        "nodes": [_fragment_node("start", "core.start")],
                        "edges": [],
                    },
                },
            ],
        }
        source_text = json.dumps(legacy_store)
        store_path.write_text(source_text, encoding="utf-8")
        store_report: list[str] = []
        with patch(
            "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
            return_value=store_path,
        ):
            stored_definitions = load_global_custom_workflow_definitions(
                registry=registry,
                migration_report=store_report,
            )
            assert store_path.read_text(encoding="utf-8") == source_text
            save_global_custom_workflow_definitions(stored_definitions)
        assert stored_definitions[0]["fragment"]["version"] == GRAPH_FRAGMENT_VERSION
        assert stored_definitions[0]["fragment"]["nodes"][0]["properties"][
            "input_names"
        ] == ["beta", "alpha"]
        assert [item["workflow_id"] for item in stored_definitions] == ["workflow"]
        assert store_report == sorted(store_report)
        assert "Removed empty custom workflow empty_workflow." in store_report
        assert json.loads(store_path.read_text(encoding="utf-8"))["version"] == 2

        unresolved_store = {
            **legacy_store,
            "custom_workflows": [unresolved_workflow["workflow"]],
        }
        unresolved_source = json.dumps(unresolved_store)
        store_path.write_text(unresolved_source, encoding="utf-8")
        with patch(
            "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
            return_value=store_path,
        ):
            try:
                load_global_custom_workflow_definitions(registry=registry)
            except ValueError as exc:
                assert "unresolved add-ons" in str(exc)
            else:
                raise AssertionError(
                    "Legacy global workflow unresolved add-ons must be rejected"
                )
        assert store_path.read_text(encoding="utf-8") == unresolved_source

    preferences = normalize_app_preferences_document(
        {
            "kind": APP_PREFERENCES_KIND,
            "version": 5,
            "authoring": {"connected_control_port_policy": "auto_expand"},
            "solution": {"default_mode": "invalid"},
        }
    )
    assert preferences["version"] == APP_PREFERENCES_VERSION
    assert preferences["solution"] == {"default_mode": "auto"}
    assert "authoring" not in preferences

    pin = resolve_subnode_pin_definition(
        "core.subnode_input",
        {
            "kind": "data",
            "data_type": DOUBLE_DATA_TYPE_ID,
            "data_access": "list",
        },
    )
    assert pin.data_access == "list"
