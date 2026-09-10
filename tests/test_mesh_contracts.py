from __future__ import annotations

import json
from functools import lru_cache

import pytest

from ea_node_editor.nodes.builtins import mesh_contracts as mesh_module
from ea_node_editor.nodes.builtin_functions import engineering_geometry
from ea_node_editor.nodes.builtins.geometry_contracts import (
    MEASURABLE_DATA_TYPE_ID,
    COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CONTRACTS_OWNER_ID,
    COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.mesh_contracts import (
    MESH_FACE_DATA_TYPE_ID,
    MESH_PARAMETER_DATA_TYPE_ID,
    COREX_MESH_CONTRACT_MANIFEST,
    COREX_MESH_CONTRACTS_OWNER_ID,
    COREX_MESH_CONTRACTS_OWNER_VERSION,
    COREX_MESH_DATA_TYPES,
    COREX_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST,
    COREX_MESH_PARAMETER_CANDIDATE_DATA_TYPES,
)
from ea_node_editor.nodes.builtins.voxel_contracts import (
    COREX_VOXEL_CONTRACT_MANIFEST,
    COREX_VOXEL_CONTRACTS_OWNER_ID,
    COREX_VOXEL_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    RuntimeHandleRef,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)

_EXPECTED_TYPE_IDS = (
    "COREX.Mesh.IIsoMesh",
    "COREX.Mesh.IThickMesh",
)
_EXPECTED_CANDIDATE_TYPE_IDS = (
    *_EXPECTED_TYPE_IDS,
    "COREX.DataTypes.MeshFace",
)
_EXPECTED_MESH_PARAMETER_TYPE_IDS = (
    *_EXPECTED_CANDIDATE_TYPE_IDS,
    "COREX.DataTypes.MeshParameter",
)
_MESH_DATA_TYPE_ID = "COREX.Mesh.IMesh"


def _register_mesh(registry: NodeRegistry) -> None:
    registry.register_plugin_bundle(
        COREX_MESH_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_MESH_CONTRACTS_OWNER_ID,
        owner_version=COREX_MESH_CONTRACTS_OWNER_VERSION,
        source_label=mesh_module.__name__,
    )


def _composed_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_GEOMETRY_CLOSURE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label="ea_node_editor.nodes.builtins.geometry_contracts",
    )
    registry.register_plugin_bundle(
        COREX_VOXEL_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_VOXEL_CONTRACTS_OWNER_ID,
        owner_version=COREX_VOXEL_CONTRACTS_OWNER_VERSION,
        source_label="ea_node_editor.nodes.builtins.voxel_contracts",
    )
    _register_mesh(registry)
    return registry


def _handle(type_id: str) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=type_id,
        schema_version=1,
        handle_id="abstract-mesh-test",
        kind="test.abstract_mesh",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )










def _context(face: object) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs={"face": face},
        properties={},
        emit_log=lambda _level, _message: None,
    )


@lru_cache(maxsize=1)
def _deconstruct_adapter() -> PythonFunctionAdapter:
    namespace: dict[str, object] = {}
    exec(compile(engineering_geometry.SOURCE, "engineering_geometry.py", "exec"), namespace)
    declaration = next(
        declaration
        for declaration in discover_plugin_declarations(
            engineering_geometry.SOURCE,
            filename="engineering_geometry.py",
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )
        if declaration.spec.type_id == "mesh.deconstruct_mesh_face"
    )
    return PythonFunctionAdapter(
        declaration.spec,
        namespace[declaration.function_name],  # type: ignore[arg-type]
    )


def test_deconstruct_mesh_face_function_validates_carrier_and_preserves_indices() -> None:
    value = TypedInlineValue(
        MESH_FACE_DATA_TYPE_ID,
        1,
        {"a": 4, "b": 5, "c": 6, "d": -1},
    )
    assert _deconstruct_adapter().execute(_context(value)).outputs == {
        "index_a": 4,
        "index_b": 5,
        "index_c": 6,
        "index_d": -1,
    }
    with pytest.raises(ValueError, match="Mesh Face input is invalid"):
        _deconstruct_adapter().execute(
            _context(TypedInlineValue(MESH_FACE_DATA_TYPE_ID, 1, {"a": 1}))
        )




def test_mesh_face_spec_and_validity_are_exact() -> None:
    registry = _composed_registry()
    registry.register_plugin_bundle(
        COREX_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_MESH_CONTRACTS_OWNER_ID,
        owner_version=COREX_MESH_CONTRACTS_OWNER_VERSION,
        source_label=mesh_module.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    spec = catalog.require(MESH_FACE_DATA_TYPE_ID)

    assert (
        spec.type_id,
        spec.display_name,
        spec.family_id,
        spec.parents,
        spec.abstract,
        spec.carriers,
        spec.persistence,
        spec.sensitivity,
        spec.payload_schema_version,
        spec.implementation_version,
        spec.description,
        spec.capabilities,
        spec.coerce_untyped_input,
    ) == (
        MESH_FACE_DATA_TYPE_ID,
        "Mesh Face",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "never",
        "normal",
        1,
        "1",
        "",
        frozenset(),
        None,
    )
    assert {
        target
        for target in (
            MESH_FACE_DATA_TYPE_ID,
            GRAPH_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            _MESH_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        )
        if catalog.is_assignable(MESH_FACE_DATA_TYPE_ID, target)
    } == {MESH_FACE_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID}

    valid_payloads = (
        {"a": 0, "b": 1, "c": 2, "d": -1},
        {"a": 0, "b": 1, "c": 2, "d": 2},
        {"a": 0, "b": 1, "c": 2, "d": 3},
        {"a": 5, "b": 5, "c": 5, "d": 5},
        {
            "a": 2_147_483_647,
            "b": 2_147_483_647,
            "c": 2_147_483_647,
            "d": 2_147_483_647,
        },
    )
    assert all(spec.validate_item(payload) is True for payload in valid_payloads)

    class IntSubclass(int):
        pass

    class DictSubclass(dict):
        pass

    invalid_payloads = [
        None,
        [],
        {"a": 0, "b": 1, "c": 2},
        {"a": 0, "b": 1, "c": 2, "D": -1},
        {"a": 0, "b": 1, "c": 2, "d": -1, "extra": 0},
        {1: 0, "b": 1, "c": 2, "d": -1},
        {"a": "0", "b": 1, "c": 2, "d": -1},
        {"a": 0.0, "b": 1, "c": 2, "d": -1},
        {"a": True, "b": 1, "c": 2, "d": -1},
        {"a": IntSubclass(0), "b": 1, "c": 2, "d": -1},
        DictSubclass({"a": 0, "b": 1, "c": 2, "d": -1}),
        {"a": 2_147_483_648, "b": 1, "c": 2, "d": -1},
        {"a": 0, "b": 2_147_483_648, "c": 2, "d": -1},
        {"a": 0, "b": 1, "c": 2_147_483_648, "d": -1},
        {"a": 0, "b": 1, "c": 2, "d": 2_147_483_648},
        {"a": -1, "b": 1, "c": 2, "d": -1},
        {"a": 0, "b": -1, "c": 2, "d": -1},
        {"a": 0, "b": 1, "c": -1, "d": -1},
        {"a": 0, "b": 1, "c": 2, "d": -2},
        {"a": float("nan"), "b": 1, "c": 2, "d": -1},
        {"a": float("inf"), "b": 1, "c": 2, "d": -1},
        {"a": float("-inf"), "b": 1, "c": 2, "d": -1},
        {"a": object(), "b": 1, "c": 2, "d": -1},
    ]
    assert all(spec.validate_item(payload) is False for payload in invalid_payloads)


def test_mesh_face_direct_datatree_and_stdio_json_round_trip() -> None:
    registry = _composed_registry()
    registry.register_plugin_bundle(
        COREX_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_MESH_CONTRACTS_OWNER_ID,
        owner_version=COREX_MESH_CONTRACTS_OWNER_VERSION,
        source_label=mesh_module.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    payloads = (
        {"a": 0, "b": 1, "c": 2, "d": -1},
        {"a": 0, "b": 1, "c": 2, "d": 2},
        {"a": 0, "b": 1, "c": 2, "d": 3},
        {"a": 7, "b": 7, "c": 7, "d": 7},
    )
    values = tuple(
        TypedInlineValue(MESH_FACE_DATA_TYPE_ID, 1, payload) for payload in payloads
    )
    assert values[1] != values[2]

    for value, payload in zip(values, payloads, strict=True):
        catalog.validate_carrier(MESH_FACE_DATA_TYPE_ID, value)
        direct_wire = serialize_runtime_value(
            value,
            catalog=catalog,
            declared_type_id=MESH_FACE_DATA_TYPE_ID,
        )
        assert direct_wire == {
            "__ea_runtime_value__": "typed_inline",
            "data_type_id": MESH_FACE_DATA_TYPE_ID,
            "schema_version": 1,
            "payload": payload,
        }
        stdio_wire = json.loads(json.dumps(direct_wire))
        assert stdio_wire == direct_wire
        assert (
            deserialize_runtime_value(
                stdio_wire,
                catalog=catalog,
                declared_type_id=MESH_FACE_DATA_TYPE_ID,
            )
            == value
        )

    tree = DataTree.from_list(values)
    tree_wire = serialize_runtime_value(
        tree,
        catalog=catalog,
        declared_type_id=MESH_FACE_DATA_TYPE_ID,
    )
    stdio_tree_wire = json.loads(json.dumps(tree_wire))
    assert stdio_tree_wire == tree_wire
    assert (
        deserialize_runtime_value(
            stdio_tree_wire,
            catalog=catalog,
            declared_type_id=MESH_FACE_DATA_TYPE_ID,
        )
        == tree
    )

    persistent_property = PropertySpec(
        "mesh_face",
        "json",
        values[0],
        "Mesh Face",
        persistence_data_type_id=MESH_FACE_DATA_TYPE_ID,
    )
    persistent_node = NodeTypeSpec(
        "tests.mesh_face_persistence",
        "Mesh Face Persistence",
        ("Tests",),
        "",
        (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
        (persistent_property,),
    )
    with pytest.raises(ValueError, match="does not permit persistence"):
        registry.register_descriptor(persistent_node, lambda: object())




def test_mesh_parameter_payload_validation_is_strict() -> None:
    spec = COREX_MESH_PARAMETER_CANDIDATE_DATA_TYPES[-1]
    valid_payloads = (
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": 2_147_483_647, "barycentric": [1, 0, 0, 0]},
        {
            "face_index": 42,
            "barycentric": [5e-10, 0.2, 0.3, 0.4999999995],
        },
    )
    assert all(spec.validate_item(payload) is True for payload in valid_payloads)

    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class TupleSubclass(tuple):
        pass

    class IntSubclass(int):
        pass

    class FloatSubclass(float):
        pass

    class StringSubclass(str):
        pass

    class HostileNumber:
        def __le__(self, _other: object) -> bool:
            raise AssertionError("hostile comparison must not run")

    invalid_payloads = (
        None,
        [],
        DictSubclass(valid_payloads[0]),
        {"face_index": 0},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, 0], "extra": 1},
        {
            StringSubclass("face_index"): 0,
            "barycentric": [0, 0.25, 0.75, 0],
        },
        {object(): 0, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": True, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": IntSubclass(0), "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": 0.0, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": -1, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": 2_147_483_648, "barycentric": [0, 0.25, 0.75, 0]},
        {"face_index": 0, "barycentric": (0, 0.25, 0.75, 0)},
        {"face_index": 0, "barycentric": ListSubclass([0, 0.25, 0.75, 0])},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, True]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, IntSubclass(0)]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, FloatSubclass(0)]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, "0"]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, HostileNumber()]},
        {"face_index": 0, "barycentric": [-1e-12, 0.25, 0.75, 0]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, 1.0000000001]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, float("nan")]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, float("inf")]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, float("-inf")]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.75, 10**400]},
        {"face_index": 0, "barycentric": [0, 0.2, 0.3, 0.4]},
        {"face_index": 0, "barycentric": [0, 0.25, 0.25, 0.500000002]},
        {"face_index": 0, "barycentric": [0.25, 0.25, 0.25, 0.25]},
        {
            "face_index": 0,
            "barycentric": [1.1e-9, 0.2, 0.3, 0.4999999989],
        },
    )
    assert all(spec.validate_item(payload) is False for payload in invalid_payloads)

    registry = _composed_registry()
    registry.register_plugin_bundle(
        COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_MESH_CONTRACTS_OWNER_ID,
        owner_version=COREX_MESH_CONTRACTS_OWNER_VERSION,
        source_label=mesh_module.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    normalized_values = (
        TypedInlineValue(
            MESH_PARAMETER_DATA_TYPE_ID,
            1,
            DictSubclass(
                {
                    "face_index": 4,
                    "barycentric": ListSubclass([0, 0.25, 0.75, 0]),
                }
            ),
        ),
        TypedInlineValue(
            MESH_PARAMETER_DATA_TYPE_ID,
            1,
            {"face_index": 5, "barycentric": TupleSubclass((0, 0.5, 0.5, 0))},
        ),
    )
    for value in normalized_values:
        assert type(value.payload) is dict
        assert type(value.payload["barycentric"]) is list
        catalog.validate_carrier(MESH_PARAMETER_DATA_TYPE_ID, value)

    tree = DataTree(
        (
            ((0,), normalized_values),
            (
                (1, 2),
                (
                    TypedInlineValue(
                        MESH_PARAMETER_DATA_TYPE_ID,
                        1,
                        {"face_index": 6, "barycentric": [0, 0, 0.25, 0.75]},
                    ),
                ),
            ),
        )
    )
    catalog.validate_carrier(MESH_PARAMETER_DATA_TYPE_ID, tree)
    invalid_tree = DataTree.from_item(
        TypedInlineValue(
            MESH_PARAMETER_DATA_TYPE_ID,
            1,
            {"face_index": 6, "barycentric": [0.25, 0.25, 0.25, 0.25]},
        )
    )
    with pytest.raises(DataTypeCatalogError):
        catalog.validate_carrier(MESH_PARAMETER_DATA_TYPE_ID, invalid_tree)


def test_mesh_parameter_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = _composed_registry()
    registry.register_plugin_bundle(
        COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_MESH_CONTRACTS_OWNER_ID,
        owner_version=COREX_MESH_CONTRACTS_OWNER_VERSION,
        source_label=mesh_module.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    payload = {"face_index": 42, "barycentric": [0, 0.25, 0.75, 0]}
    value = TypedInlineValue(MESH_PARAMETER_DATA_TYPE_ID, 1, payload)
    catalog.validate_carrier(MESH_PARAMETER_DATA_TYPE_ID, value)

    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=MESH_PARAMETER_DATA_TYPE_ID,
    )
    assert wire == {
        "__ea_runtime_value__": "typed_inline",
        "data_type_id": MESH_PARAMETER_DATA_TYPE_ID,
        "schema_version": 1,
        "payload": payload,
    }
    restored = deserialize_runtime_value(
        json.loads(json.dumps(wire)),
        catalog=catalog,
        declared_type_id=MESH_PARAMETER_DATA_TYPE_ID,
    )
    assert restored == value
    assert restored.payload == payload

    invalid_values = (
        TypedInlineValue(MESH_FACE_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(MESH_PARAMETER_DATA_TYPE_ID, 2, payload),
        payload,
        TypedInlineValue(
            MESH_PARAMETER_DATA_TYPE_ID,
            1,
            {"face_index": 42, "barycentric": [0.25, 0.25, 0.25, 0.25]},
        ),
    )
    for invalid_value in invalid_values:
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=MESH_PARAMETER_DATA_TYPE_ID,
            )

    wrong_identity_wire = json.loads(json.dumps(wire))
    wrong_identity_wire["data_type_id"] = MESH_FACE_DATA_TYPE_ID
    wrong_schema_wire = json.loads(json.dumps(wire))
    wrong_schema_wire["schema_version"] = 2
    invalid_payload_wire = json.loads(json.dumps(wire))
    invalid_payload_wire["payload"]["barycentric"] = [0.25, 0.25, 0.25, 0.25]
    for invalid_wire in (
        wrong_identity_wire,
        wrong_schema_wire,
        payload,
        invalid_payload_wire,
    ):
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=MESH_PARAMETER_DATA_TYPE_ID,
            )


def test_exact_abstract_handle_specs_have_the_reduced_direct_parent_dag() -> None:
    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_MESH_DATA_TYPES
    ] == [
        (
            type_id,
            display_name,
            "engineering",
            (MEASURABLE_DATA_TYPE_ID,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name in zip(
            _EXPECTED_TYPE_IDS,
            ("Iso Mesh", "Thick Mesh"),
            strict=True,
        )
    ]

    catalog = _composed_registry().data_types
    for type_id in _EXPECTED_TYPE_IDS:
        assert {
            target
            for target in (
                *_EXPECTED_TYPE_IDS,
                MEASURABLE_DATA_TYPE_ID,
                GRAPH_DATA_TYPE_ID,
                CLIPPABLE_GRAPH_DATA_TYPE_ID,
                _MESH_DATA_TYPE_ID,
            )
            if catalog.is_assignable(type_id, target)
        } == {type_id, MEASURABLE_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID}
        assert not catalog.is_assignable(type_id, _MESH_DATA_TYPE_ID)
        assert not catalog.is_assignable(type_id, CLIPPABLE_GRAPH_DATA_TYPE_ID)
        assert catalog.require(type_id).abstract
    assert {
        spec.type_id
        for spec in catalog.all_specs()
        if not spec.abstract
        and catalog.is_assignable(spec.type_id, CLIPPABLE_GRAPH_DATA_TYPE_ID)
    } == {ENGINEERING_SCENE_DATA_TYPE_ID}


def test_all_abstract_validators_and_exact_handles_reject() -> None:
    catalog = _composed_registry().data_types
    for spec in COREX_MESH_DATA_TYPES:
        handle = _handle(spec.type_id)
        assert spec.validate_item(object()) is False
        assert spec.validate_item(handle) is False
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            catalog.validate_carrier(spec.type_id, handle)
