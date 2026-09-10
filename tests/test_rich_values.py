from __future__ import annotations

import copy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_builtin_registry,
    build_default_registry,
)
from ea_node_editor.nodes.builtin_functions.ai_agent import SOURCE as AI_AGENT_SOURCE
from ea_node_editor.nodes.builtin_functions.rich_values import (
    SOURCE as RICH_VALUES_SOURCE,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import (
    AGENT_MODEL_DATA_TYPE_ID,
    COLOR_MAP_DATA_TYPE_ID,
    IDENTITY_PLANE,
    LARGE_LANGUAGE_MODEL_NODE_TYPE_ID,
    NODE_VISUAL_DATA_TYPE_ID,
    PLANE_CONTAINER_NODE_TYPE_ID,
    PLANE_DATA_TYPE_ID,
    COREX_RICH_VALUE_CONTRACT_MANIFEST,
    COREX_RICH_VALUE_OWNER_ID,
    COREX_RICH_VALUE_OWNER_VERSION,
    is_agent_model_payload,
    is_color_map_payload,
    is_node_visual_payload,
    is_plane_payload,
    make_agent_model_value,
    plane_container_value,
)
from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    CORE_DATA_TYPE_OWNER_ID,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    DataTree,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.settings import SCHEMA_VERSION
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


def _plane(
    *,
    origin: list[float] | None = None,
    axes: list[list[float]] | None = None,
    normal: list[float] | None = None,
) -> TypedInlineValue:
    return TypedInlineValue(
        PLANE_DATA_TYPE_ID,
        1,
        {
            "origin": origin or [1.0, 2.0, 3.0],
            "axes": axes or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            "normal": normal or [0.0, 0.0, 1.0],
        },
    )


def _color_map() -> TypedInlineValue:
    return TypedInlineValue(
        COLOR_MAP_DATA_TYPE_ID,
        1,
        ["#FF0000FF", "#00ff00aa"],
    )


def _node_visual() -> TypedInlineValue:
    return TypedInlineValue(
        NODE_VISUAL_DATA_TYPE_ID,
        1,
        {"node_refs": ["node:alpha", "node/beta"]},
    )


def _agent_model() -> TypedInlineValue:
    return TypedInlineValue(
        AGENT_MODEL_DATA_TYPE_ID,
        1,
        {"provider_id": "corex-server", "model_id": "gpt-5.1"},
    )


def _context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
    )


def test_rich_value_catalog_and_clippable_assignability_are_exact() -> None:
    registry = build_builtin_registry()
    catalog = registry.data_types
    expected = {
        PLANE_DATA_TYPE_ID: ("engineering", "inline"),
        COLOR_MAP_DATA_TYPE_ID: ("viewer", "inline"),
        NODE_VISUAL_DATA_TYPE_ID: ("viewer", "never"),
        AGENT_MODEL_DATA_TYPE_ID: ("graph", "inline"),
    }

    for type_id, (family, persistence) in expected.items():
        spec = catalog.require(type_id)
        assert spec.family_id == family
        assert spec.parents == (GRAPH_DATA_TYPE_ID,)
        assert spec.carriers == frozenset({"inline"})
        assert spec.persistence == persistence
        assert spec.payload_schema_version == 1
        assert spec.implementation_version == "1"
        assert spec.coerce_untyped_input is None
        assert catalog.owner_of(type_id) == COREX_RICH_VALUE_OWNER_ID

    clippable = catalog.require(CLIPPABLE_GRAPH_DATA_TYPE_ID)
    assert clippable.abstract is True
    assert clippable.family_id == "engineering"
    assert clippable.parents == (GRAPH_DATA_TYPE_ID,)
    assert clippable.carriers == frozenset({"handle"})
    assert clippable.persistence == "never"
    assert catalog.owner_of(CLIPPABLE_GRAPH_DATA_TYPE_ID) == CORE_DATA_TYPE_OWNER_ID
    assert catalog.require(ENGINEERING_SCENE_DATA_TYPE_ID).parents == (
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )
    assert catalog.is_assignable(
        ENGINEERING_SCENE_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "origin": [0, 0.0, 0],
            "axes": [[1, 0, 0], [0, 1, 0]],
            "normal": [0, 0, 1],
        },
        {
            "origin": [-1.5, 2.5, 0.0],
            "axes": [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],
            "normal": [0.0, 0.0, 1.0],
        },
    ),
)
def test_plane_payload_accepts_only_finite_right_handed_frames(
    payload: object,
) -> None:
    assert is_plane_payload(payload)


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {
            "origin": [0, 0, 0],
            "axes": [[1, 0, 0], [0, 1, 0]],
            "normal": [0, 0, 1],
            "extra": 1,
        },
        {
            "origin": [False, 0, 0],
            "axes": [[1, 0, 0], [0, 1, 0]],
            "normal": [0, 0, 1],
        },
        {
            "origin": [0, 0, float("inf")],
            "axes": [[1, 0, 0], [0, 1, 0]],
            "normal": [0, 0, 1],
        },
        {
            "origin": [0, 0, 0],
            "axes": [[1, 0, 0], [0, 1, 0]],
            "normal": [0, 0, -1],
        },
        {
            "origin": [0, 0, 0],
            "axes": [[1, 0, 0], [1, 0, 0]],
            "normal": [0, 0, 1],
        },
    ),
)
def test_plane_payload_rejects_invalid_shapes_and_frames(payload: object) -> None:
    assert not is_plane_payload(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (["#00000000"], True),
        (["#AABBCCDD", "#aabbccdd"], True),
        ([], False),
        (["#000000"], False),
        ([" #AABBCCDD"], False),
        (["#GG000000"], False),
        (["#00000000"] * 257, False),
        ({"colors": ["#00000000"]}, False),
    ),
)
def test_color_map_payload_matrix(payload: object, expected: bool) -> None:
    assert is_color_map_payload(payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        ({"node_refs": []}, True),
        ({"node_refs": ["node:1", "节点-2"]}, True),
        ({"node_refs": [""]}, False),
        ({"node_refs": [" node"]}, False),
        ({"node_refs": ["node\n2"]}, False),
        ({"node_refs": ["x" * 129]}, False),
        ({"node_refs": [object()]}, False),
        ({"node_refs": ["node"], "geometry": {}}, False),
        ({"node_refs": ["node"] * 257}, False),
    ),
)
def test_node_visual_payload_matrix(payload: object, expected: bool) -> None:
    assert is_node_visual_payload(payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        ({"provider_id": "corex-server", "model_id": "gpt-5.1"}, True),
        ({"provider_id": "azure/openai", "model_id": "deployment:01"}, True),
        ({"provider_id": "", "model_id": "model"}, False),
        ({"provider_id": "provider", "model_id": ""}, False),
        ({"provider_id": " provider", "model_id": "model"}, False),
        ({"provider_id": "provider id", "model_id": "model"}, False),
        ({"provider_id": "provider", "model_id": {"name": "model"}}, False),
        (
            {"provider_id": "provider", "model_id": "model", "token": "secret"},
            False,
        ),
        (
            {"provider_id": "provider", "model_id": "model", "client": object()},
            False,
        ),
    ),
)
def test_agent_model_payload_matrix(payload: object, expected: bool) -> None:
    assert is_agent_model_payload(payload) is expected


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "credential",
        "credentials",
        "session",
        "transcript",
        "weights",
        "tools",
        "client",
        "token",
        "api_key",
    ),
)
def test_agent_model_rejects_runtime_and_secret_bearing_fields(
    forbidden_key: str,
) -> None:
    payload = {
        "provider_id": "corex-server",
        "model_id": "gpt-5.1",
        forbidden_key: "must-not-be-stored",
    }
    assert not is_agent_model_payload(payload)


def test_mixed_rich_value_tree_survives_runtime_and_protocol_json_round_trips() -> None:
    registry = build_builtin_registry()
    tree = DataTree(
        (
            ((0,), (_plane(), {"nested": [_color_map(), _node_visual()]})),
            ((2, 3), (_agent_model(),)),
        )
    )

    wire = serialize_runtime_value(tree, catalog=registry.data_types)
    assert deserialize_runtime_value(wire, catalog=registry.data_types) == tree

    event = NodeSettledEvent(
        outputs={"result": SettledPortResult(status="value", value=tree)}
    )
    restored = dict_to_event(
        json.loads(json.dumps(event_to_dict(event, catalog=registry.data_types))),
        catalog=registry.data_types,
    )
    assert restored.outputs["result"].value == tree


def test_rich_value_function_specs_match_frozen_catalog() -> None:
    declarations = tuple(
        declaration
        for source, filename in (
            (AI_AGENT_SOURCE, "builtin_functions/ai_agent.py"),
            (RICH_VALUES_SOURCE, "builtin_functions/rich_values.py"),
        )
        for declaration in discover_plugin_declarations(
            source,
            filename=filename,
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )
    )
    ids = {LARGE_LANGUAGE_MODEL_NODE_TYPE_ID, PLANE_CONTAINER_NODE_TYPE_ID}
    golden = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden
        if row["spec"]["type_id"] in ids
    }

    assert {
        declaration.spec.type_id: json.loads(json.dumps(asdict(declaration.spec)))
        for declaration in declarations
    } == expected


def _persistence_registry() -> tuple[NodeRegistry, NodeTypeSpec]:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_RICH_VALUE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_RICH_VALUE_OWNER_ID,
        owner_version=COREX_RICH_VALUE_OWNER_VERSION,
    )
    spec = NodeTypeSpec(
        "tests.rich_type_persistence",
        "Rich Type Persistence",
        ("Tests",),
        "",
        (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
        (
            PropertySpec(
                "plane",
                "json",
                _plane().payload,
                "Plane",
                persistence_data_type_id=PLANE_DATA_TYPE_ID,
            ),
            PropertySpec(
                "color_map",
                "json",
                _color_map().payload,
                "Color Map",
                persistence_data_type_id=COLOR_MAP_DATA_TYPE_ID,
            ),
            PropertySpec(
                "agent_model",
                "json",
                _agent_model().payload,
                "Agent Model",
                persistence_data_type_id=AGENT_MODEL_DATA_TYPE_ID,
            ),
            PropertySpec("visual", "json", {}, "Visual"),
        ),
    )
    registry.register_descriptor(spec, lambda: object(), owner_id="tests.rich_types")
    return registry, spec


def test_real_project_serializer_round_trips_persistent_rich_values_without_schema_change() -> (
    None
):
    registry, spec = _persistence_registry()
    serializer = JsonProjectSerializer(registry)
    values = {
        "plane": _plane(),
        "color_map": _color_map(),
        "agent_model": _agent_model(),
        "visual": {},
    }
    model = GraphModel()
    model.add_node(
        model.active_workspace.workspace_id,
        spec.type_id,
        spec.display_name,
        0.0,
        0.0,
        properties=values,
    )

    document = serializer.to_persistent_document(model.project)
    assert document["schema_version"] == SCHEMA_VERSION
    loaded = serializer.from_document(document)
    loaded_node = next(iter(next(iter(loaded.workspaces.values())).nodes.values()))
    assert loaded_node.properties == values

    rejected = copy.deepcopy(model)
    next(iter(rejected.active_workspace.nodes.values())).properties["visual"] = (
        _node_visual()
    )
    with pytest.raises(ValueError, match="typed persistence"):
        serializer.to_persistent_document(rejected.project)


def test_production_plane_container_default_is_independent_and_round_trips(
    tmp_path,
) -> None:
    registry = build_builtin_registry()
    spec = registry.get_spec(PLANE_CONTAINER_NODE_TYPE_ID)
    prop = next(item for item in spec.properties if item.key == "input")
    assert type(prop.default) is TypedInlineValue
    assert prop.default == IDENTITY_PLANE
    assert prop.default is not IDENTITY_PLANE
    assert prop.default.payload is not IDENTITY_PLANE.payload
    assert prop.persistence_data_type_id == PLANE_DATA_TYPE_ID
    registry.data_types.validate_carrier(PLANE_DATA_TYPE_ID, prop.default)

    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    first = mutations.add_node(
        type_id=PLANE_CONTAINER_NODE_TYPE_ID,
        title="Plane A",
        x=0.0,
        y=0.0,
    )
    second = mutations.add_node(
        type_id=PLANE_CONTAINER_NODE_TYPE_ID,
        title="Plane B",
        x=100.0,
        y=0.0,
    )
    first_default = first.properties["input"]
    second_default = second.properties["input"]
    assert first_default == second_default == IDENTITY_PLANE
    assert first_default is not second_default
    assert first_default is not IDENTITY_PLANE
    assert first_default.payload is not second_default.payload
    assert first_default.payload is not IDENTITY_PLANE.payload

    serializer = JsonProjectSerializer(registry)
    project_path = tmp_path / "plane_container.cxproj"
    serializer.save(str(project_path), model.project)
    document = json.loads(project_path.read_text(encoding="utf-8"))
    node_documents = {
        node["node_id"]: node for node in document["workspaces"][0]["nodes"]
    }
    assert (
        node_documents[first.node_id]["properties"]["input"]["__ea_runtime_value__"]
        == "typed_inline"
    )
    loaded = serializer.load(str(project_path))
    loaded_first = loaded.workspaces[workspace.workspace_id].nodes[first.node_id]
    loaded_second = loaded.workspaces[workspace.workspace_id].nodes[second.node_id]
    assert loaded_first.properties["input"] == IDENTITY_PLANE
    assert loaded_second.properties["input"] == IDENTITY_PLANE

    first_default.payload["origin"][0] = 99.0
    assert second_default.payload["origin"] == [0.0, 0.0, 0.0]
    assert IDENTITY_PLANE.payload["origin"] == [0.0, 0.0, 0.0]


def test_plane_container_and_agent_model_nodes_are_offline_value_nodes() -> None:
    incoming = _plane(origin=[9.0, 8.0, 7.0])
    assert (
        plane_container_value(
            _context(inputs={"input": incoming}, properties={"input": IDENTITY_PLANE}),
            incoming,
            IDENTITY_PLANE,
        )
        is incoming
    )
    assert (
        plane_container_value(
            _context(properties={"input": IDENTITY_PLANE}),
            None,
            IDENTITY_PLANE,
        )
        == IDENTITY_PLANE
    )
    with pytest.raises(ValueError, match="typed Plane"):
        plane_container_value(
            _context(inputs={"input": None}, properties={"input": IDENTITY_PLANE}),
            None,
            IDENTITY_PLANE,
        )

    model = make_agent_model_value(
        "corex-server",
        "engineering-model",
    )
    assert model == TypedInlineValue(
        AGENT_MODEL_DATA_TYPE_ID,
        1,
        {
            "provider_id": "corex-server",
            "model_id": "engineering-model",
        },
    )
    assert set(model.payload) == {
        "provider_id",
        "model_id",
    }
    with pytest.raises(ValueError, match="non-empty identifiers"):
        make_agent_model_value("corex-server", "")


@pytest.mark.parametrize(
    "value",
    (
        IDENTITY_PLANE.payload,
        TypedInlineValue(PLANE_DATA_TYPE_ID, 2, IDENTITY_PLANE.payload),
        TypedInlineValue(
            PLANE_DATA_TYPE_ID,
            1,
            {
                "origin": [0.0, 0.0, 0.0],
                "axes": [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                "normal": [0.0, 0.0, 1.0],
            },
        ),
        _color_map(),
    ),
)
def test_plane_container_rejects_untyped_or_catalog_invalid_values(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="Plane input"):
        plane_container_value(
            _context(inputs={"input": value}, properties={"input": IDENTITY_PLANE}),
            value,
            IDENTITY_PLANE,
        )
