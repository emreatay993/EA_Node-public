from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
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
from ea_node_editor.nodes import bootstrap
from ea_node_editor.nodes.builtin_functions import spatial as spatial_functions
from ea_node_editor.nodes.builtins import spatial_values as spatial
from ea_node_editor.nodes.builtins.core_media import (
    INTERVAL_2D_DATA_TYPE_ID,
    COREX_CORE_MEDIA_CONTRACT_MANIFEST,
    COREX_CORE_MEDIA_OWNER_ID,
    COREX_CORE_MEDIA_OWNER_VERSION,
    is_interval_2d_payload,
)
from ea_node_editor.nodes.builtins.geometry_contracts import (
    COORDINATE_SYSTEM_DATA_TYPE_ID,
    SPATIAL_OBJECT_DATA_TYPE_ID,
    COREX_GEOMETRY_CONTRACT_MANIFEST,
    COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_GEOMETRY_CONTRACTS_OWNER_ID,
    COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
)
from ea_node_editor.nodes.builtins.spatial_values import (
    IVECTOR_DATA_TYPE_ID,
    POINT_3D_DATA_TYPE_ID,
    COREX_SPATIAL_VALUE_DATA_TYPES,
    COREX_SPATIAL_VALUES_CONTRACT_MANIFEST,
    COREX_SPATIAL_VALUES_OWNER_ID,
    COREX_SPATIAL_VALUES_OWNER_VERSION,
    VECTOR_3D_DATA_TYPE_ID,
    make_point3d_value,
    make_vector3d_value,
    point3d_coordinates,
    vector3d_coordinates,
)
from ea_node_editor.nodes.core_data_types import (
    CLIPPABLE_GRAPH_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    RuntimeHandleRef,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


class _DictSubclass(dict):
    armed = False

    def __len__(self) -> int:
        if self.armed:
            raise AssertionError("dict subclass method executed")
        return super().__len__()

    def __iter__(self):
        if self.armed:
            raise AssertionError("dict subclass method executed")
        return super().__iter__()

    def __getitem__(self, key: object) -> object:
        if self.armed:
            raise AssertionError("dict subclass method executed")
        return super().__getitem__(key)


class _StringSubclass(str):
    armed = False

    def __hash__(self) -> int:
        if self.armed:
            raise AssertionError("string subclass hash executed")
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        if self.armed:
            raise AssertionError("string subclass equality executed")
        return super().__eq__(other)


class _IntSubclass(int):
    armed = False

    def __float__(self) -> float:
        if self.armed:
            raise AssertionError("integer subclass conversion executed")
        return super().__float__()

    def __eq__(self, other: object) -> bool:
        if self.armed:
            raise AssertionError("integer subclass equality executed")
        return super().__eq__(other)

    __hash__ = int.__hash__


class _FloatSubclass(float):
    armed = False

    def __float__(self) -> float:
        if self.armed:
            raise AssertionError("float subclass conversion executed")
        return super().__float__()

    def __eq__(self, other: object) -> bool:
        if self.armed:
            raise AssertionError("float subclass equality executed")
        return super().__eq__(other)

    __hash__ = float.__hash__


class _InlineSubclass(TypedInlineValue):
    pass


def _unchecked_inline_value(
    data_type_id: object,
    schema_version: object,
    payload: object,
) -> TypedInlineValue:
    value = object.__new__(TypedInlineValue)
    object.__setattr__(value, "data_type_id", data_type_id)
    object.__setattr__(value, "schema_version", schema_version)
    object.__setattr__(value, "payload", payload)
    return value


class _ListSubclass(list):
    def __len__(self) -> int:
        raise AssertionError("list subclass method executed")

    def __iter__(self):
        raise AssertionError("list subclass method executed")


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_SPATIAL_VALUES_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=COREX_SPATIAL_VALUES_OWNER_VERSION,
    )
    return registry


def _d024_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_CORE_MEDIA_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_CORE_MEDIA_OWNER_ID,
        owner_version=COREX_CORE_MEDIA_OWNER_VERSION,
    )
    registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_BOUNDING_INTERVAL_2D_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=spatial.COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=spatial.COREX_SPATIAL_VALUES_OWNER_VERSION,
    )
    return registry
















def _node_context(
    node_type_id: str,
    inputs: dict[str, object],
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id=node_type_id,
        workspace_id="workspace",
        inputs=inputs,
        properties={},
        emit_log=lambda _level, _message: None,
    )


@lru_cache(maxsize=1)
def _spatial_function_adapters() -> dict[str, PythonFunctionAdapter]:
    namespace: dict[str, object] = {}
    exec(compile(spatial_functions.SOURCE, "spatial.py", "exec"), namespace)
    declarations = discover_plugin_declarations(
        spatial_functions.SOURCE,
        filename="spatial.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    return {
        declaration.spec.type_id: PythonFunctionAdapter(
            declaration.spec,
            namespace[declaration.function_name],  # type: ignore[arg-type]
        )
        for declaration in declarations
    }


def _execute_spatial(
    node_type_id: str,
    inputs: dict[str, object],
) -> dict[str, object]:
    return _spatial_function_adapters()[node_type_id].execute(
        _node_context(node_type_id, inputs)
    ).outputs


def _catalog_value(value: object) -> object:
    if callable(value):
        return True
    if is_dataclass(value):
        return {
            field.name: _catalog_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _catalog_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_catalog_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_catalog_value(item) for item in value), key=str)
    if isinstance(value, Enum):
        return _catalog_value(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Unsupported catalog value: {type(value).__qualname__}")




_CONVERTED_SPATIAL_TYPE_IDS = (
    spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
    spatial.FIELD_VECTOR_CONTAINER_TYPE_ID,
    spatial.REVERSE_VECTOR_TYPE_ID,
    spatial.DECONSTRUCT_VECTOR_TYPE_ID,
    spatial.DECONSTRUCT_POINT_TYPE_ID,
    spatial.CONSTRUCT_POINT_TYPE_ID,
    spatial.CONSTRUCT_VECTOR_TYPE_ID,
    spatial.XY_PLANE_TYPE_ID,
    spatial.CONSTRUCT_PLANE_TYPE_ID,
    spatial.VECTOR_LENGTH_TYPE_ID,
    spatial.CHAIN_TRANSFORMS_TYPE_ID,
    spatial.UNCHAIN_TRANSFORMS_TYPE_ID,
    "geometry.construct_transform",
    "geometry.deconstruct_transform",
)


def test_converted_spatial_specs_match_golden_and_use_function_entries(
    tmp_path: Path,
) -> None:
    expected_rows = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in expected_rows
        if row["spec"]["type_id"] in _CONVERTED_SPATIAL_TYPE_IDS
    }
    registry = bootstrap.build_builtin_registry(generation_root=tmp_path / "generations")

    assert set(expected) == set(_CONVERTED_SPATIAL_TYPE_IDS)
    for type_id in _CONVERTED_SPATIAL_TYPE_IDS:
        entry = registry.get_entry(type_id)
        assert isinstance(entry, PythonFunctionEntry)
        assert entry.owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        assert registry.descriptor_or_none(type_id) is None
        assert _catalog_value(entry.spec) == expected[type_id]


def test_transform_nodes_use_static_function_adapters() -> None:
    assert {
        "geometry.construct_transform",
        "geometry.deconstruct_transform",
    } <= _spatial_function_adapters().keys()
    for class_name in (
        "BoundingInterval2DNodePlugin",
        "FieldVectorContainerNodePlugin",
        "ReverseVectorNodePlugin",
        "DeconstructVectorNodePlugin",
        "DeconstructPointNodePlugin",
        "ConstructPointNodePlugin",
        "ConstructVectorNodePlugin",
        "XYPlaneNodePlugin",
        "ConstructPlaneNodePlugin",
        "VectorLengthNodePlugin",
        "ChainTransformsNodePlugin",
        "UnchainTransformsNodePlugin",
        "ConstructTransformNodePlugin",
        "DeconstructTransformNodePlugin",
    ):
        assert not hasattr(spatial, class_name)


def test_converted_spatial_vector_container_and_transform_behavior_is_exact() -> None:
    point = spatial.make_point3d_value(1, 2, 3)
    vector = spatial.make_vector3d_value(3, -4, 0)
    assert _execute_spatial(spatial.REVERSE_VECTOR_TYPE_ID, {"vector": vector}) == {
        "reversed_vector": spatial.make_vector3d_value(-3, 4, 0)
    }
    assert _execute_spatial(
        spatial.DECONSTRUCT_VECTOR_TYPE_ID,
        {"vector": vector},
    ) == {"x": 3, "y": -4, "z": 0}
    assert _execute_spatial(
        spatial.DECONSTRUCT_POINT_TYPE_ID,
        {"point": point},
    ) == {"x": 1, "y": 2, "z": 3}
    assert _execute_spatial(spatial.VECTOR_LENGTH_TYPE_ID, {"vector": vector}) == {
        "length": 5.0
    }

    field = TypedInlineValue(spatial.FIELD_VECTOR_DATA_TYPE_ID, 1, [1, -2.5])
    assert _execute_spatial(spatial.FIELD_VECTOR_CONTAINER_TYPE_ID, {}) == {}
    assert _execute_spatial(
        spatial.FIELD_VECTOR_CONTAINER_TYPE_ID,
        {"input": None},
    ) == {"output": None}
    assert _execute_spatial(
        spatial.FIELD_VECTOR_CONTAINER_TYPE_ID,
        {"input": field},
    ) == {"output": field}

    first = spatial.make_transform3d_value(
        [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 2, 3, 4, 1]
    )
    second = spatial.make_transform3d_value(
        [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1]
    )
    chained = _execute_spatial(
        spatial.CHAIN_TRANSFORMS_TYPE_ID,
        {"transforms": [first, second]},
    )["transform"]
    assert _execute_spatial(
        spatial.UNCHAIN_TRANSFORMS_TYPE_ID,
        {"transform": chained},
    ) == {"transforms": [first, second]}


def test_converted_spatial_validation_keeps_exact_failures() -> None:
    point = spatial.make_point3d_value(1, 2, 3)
    vector = spatial.make_vector3d_value(1, 0, 0)
    for type_id, inputs in (
        (spatial.REVERSE_VECTOR_TYPE_ID, {"vector": point}),
        (spatial.DECONSTRUCT_VECTOR_TYPE_ID, {"vector": point}),
        (spatial.DECONSTRUCT_POINT_TYPE_ID, {"point": vector}),
        (spatial.VECTOR_LENGTH_TYPE_ID, {"vector": point}),
    ):
        with pytest.raises(ValueError, match="spatial value is invalid"):
            _execute_spatial(type_id, inputs)
    with pytest.raises(ValueError, match="Field Vector input is invalid"):
        _execute_spatial(
            spatial.FIELD_VECTOR_CONTAINER_TYPE_ID,
            {"input": TypedInlineValue(spatial.FIELD_VECTOR_DATA_TYPE_ID, 1, [])},
        )
    with pytest.raises(ValueError, match="spatial coordinates are invalid"):
        _execute_spatial(
            spatial.CONSTRUCT_POINT_TYPE_ID,
            {"x": True, "y": 0, "z": 0},
        )
    with pytest.raises(ValueError, match="spatial coordinates are invalid"):
        _execute_spatial(
            spatial.CONSTRUCT_VECTOR_TYPE_ID,
            {"x": 0, "y": float("nan"), "z": 0},
        )
    with pytest.raises(ValueError, match="spatial value is invalid"):
        _execute_spatial(spatial.XY_PLANE_TYPE_ID, {"origin": vector})
    with pytest.raises(ValueError, match="ChainedTransform3D transforms are invalid"):
        _execute_spatial(spatial.CHAIN_TRANSFORMS_TYPE_ID, {"transforms": []})
    with pytest.raises(ValueError, match="ChainedTransform3D value is invalid"):
        _execute_spatial(
            spatial.UNCHAIN_TRANSFORMS_TYPE_ID,
            {"transform": spatial.make_transform3d_value(list(range(16)))},
        )
    required_inputs = {
        spatial.BOUNDING_INTERVAL_2D_TYPE_ID: {},
        spatial.REVERSE_VECTOR_TYPE_ID: {},
        spatial.DECONSTRUCT_VECTOR_TYPE_ID: {},
        spatial.DECONSTRUCT_POINT_TYPE_ID: {},
        spatial.CONSTRUCT_POINT_TYPE_ID: {"x": 0, "y": 0},
        spatial.CONSTRUCT_VECTOR_TYPE_ID: {"x": 0, "y": 0},
        spatial.XY_PLANE_TYPE_ID: {},
        spatial.CONSTRUCT_PLANE_TYPE_ID: {},
        spatial.VECTOR_LENGTH_TYPE_ID: {},
        spatial.CHAIN_TRANSFORMS_TYPE_ID: {},
        spatial.UNCHAIN_TRANSFORMS_TYPE_ID: {},
    }
    for type_id, inputs in required_inputs.items():
        with pytest.raises(KeyError):
            _execute_spatial(type_id, inputs)


def test_type_facts_and_parent_relations_are_exact() -> None:
    ivector, point, vector = COREX_SPATIAL_VALUE_DATA_TYPES
    assert (
        ivector.type_id,
        ivector.family_id,
        ivector.parents,
        ivector.abstract,
        ivector.carriers,
        ivector.persistence,
        ivector.sensitivity,
        ivector.payload_schema_version,
        ivector.implementation_version,
    ) == (
        IVECTOR_DATA_TYPE_ID,
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"inline"}),
        "never",
        "normal",
        1,
        "1",
    )
    for spec, type_id, parents in (
        (point, POINT_3D_DATA_TYPE_ID, (GRAPH_DATA_TYPE_ID,)),
        (vector, VECTOR_3D_DATA_TYPE_ID, (IVECTOR_DATA_TYPE_ID,)),
    ):
        assert (
            spec.type_id,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
        ) == (
            type_id,
            "engineering",
            parents,
            False,
            frozenset({"inline"}),
            "inline",
            "normal",
            1,
            "1",
        )

    catalog = _registry().data_types
    assert catalog.is_assignable(VECTOR_3D_DATA_TYPE_ID, IVECTOR_DATA_TYPE_ID)
    assert not catalog.is_assignable(POINT_3D_DATA_TYPE_ID, IVECTOR_DATA_TYPE_ID)

    candidate_registry = _d024_registry()
    candidate_registry.register_plugin_bundle(
        COREX_GEOMETRY_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
    )
    candidate_registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_VECTOR_2D_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=COREX_SPATIAL_VALUES_OWNER_VERSION,
        replace_owner=True,
    )
    candidate_catalog = candidate_registry.data_types
    vector2d = candidate_catalog.require(spatial.VECTOR_2D_DATA_TYPE_ID)
    assert (
        vector2d.type_id,
        vector2d.display_name,
        vector2d.family_id,
        vector2d.parents,
        vector2d.abstract,
        vector2d.carriers,
        vector2d.persistence,
        vector2d.sensitivity,
        vector2d.payload_schema_version,
        vector2d.implementation_version,
        vector2d.description,
        vector2d.capabilities,
        vector2d.coerce_untyped_input,
    ) == (
        "COREX.DataTypes.Vector2D",
        "Vector 2D",
        "engineering",
        (SPATIAL_OBJECT_DATA_TYPE_ID,),
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
    assert candidate_catalog.is_assignable(
        spatial.VECTOR_2D_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
    )
    assert not candidate_catalog.is_assignable(
        spatial.VECTOR_2D_DATA_TYPE_ID,
        IVECTOR_DATA_TYPE_ID,
    )
    assert not candidate_catalog.is_assignable(
        spatial.VECTOR_2D_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    )
    assert vector2d.validate_item({"x": 0, "y": -2.5}) is True
    assert vector2d.validate_item({"x": -0.0, "y": 7}) is True

    hostile_dict = _DictSubclass({"x": 1, "y": 2})
    hostile_key = _StringSubclass("x")
    hostile_key_payload = {hostile_key: 1, "y": 2}
    hostile_int = _IntSubclass(1)
    hostile_float = _FloatSubclass(2.0)
    invalid_payloads = (
        None,
        [],
        {},
        {"x": 1},
        {"x": 1, "y": 2, "z": 3},
        {"X": 1, "y": 2},
        {1: 1, "y": 2},
        hostile_dict,
        hostile_key_payload,
        {"x": "1", "y": 2},
        {"x": True, "y": 2},
        {"x": hostile_int, "y": 2},
        {"x": 1, "y": hostile_float},
        {"x": float("nan"), "y": 2},
        {"x": float("inf"), "y": 2},
        {"x": 1, "y": float("-inf")},
        {"x": 10**10_000, "y": 2},
    )
    _DictSubclass.armed = True
    _StringSubclass.armed = True
    _IntSubclass.armed = True
    _FloatSubclass.armed = True
    try:
        assert all(
            vector2d.validate_item(payload) is False for payload in invalid_payloads
        )
    finally:
        _DictSubclass.armed = False
        _StringSubclass.armed = False
        _IntSubclass.armed = False
        _FloatSubclass.armed = False

    candidate_registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=COREX_SPATIAL_VALUES_OWNER_VERSION,
        replace_owner=True,
    )
    candidate_catalog = candidate_registry.data_types
    field_vector = candidate_catalog.require(spatial.FIELD_VECTOR_DATA_TYPE_ID)
    assert (
        field_vector.type_id,
        field_vector.display_name,
        field_vector.family_id,
        field_vector.parents,
        field_vector.abstract,
        field_vector.carriers,
        field_vector.persistence,
        field_vector.sensitivity,
        field_vector.payload_schema_version,
        field_vector.implementation_version,
        field_vector.description,
        field_vector.capabilities,
        field_vector.coerce_untyped_input,
    ) == (
        "COREX.DataTypes.FieldVector",
        "Field Vector",
        "geometry_value",
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
    assert candidate_catalog.is_assignable(
        spatial.FIELD_VECTOR_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    )
    for unrelated_parent in (
        spatial.IVECTOR_DATA_TYPE_ID,
        spatial.ISPATIAL_FIELD_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    ):
        assert not candidate_catalog.is_assignable(
            spatial.FIELD_VECTOR_DATA_TYPE_ID,
            unrelated_parent,
        )

    # This positive, variable-length finite list is COREX transport policy. It
    # does not claim COREX constructor or serialization parity; 2048 is not fixed.
    short_payload = [1, -2.5, -0.0, 4]
    assert field_vector.validate_item([1]) is True
    assert field_vector.validate_item(short_payload) is True
    assert field_vector.validate_item([float(index) for index in range(2048)]) is True
    assert [type(item) for item in short_payload] == [int, float, float, int]
    assert math.copysign(1.0, short_payload[2]) == -1.0

    hostile_list = _ListSubclass([1.0])
    hostile_int = _IntSubclass(1)
    hostile_float = _FloatSubclass(2.0)
    invalid_field_vector_payloads = (
        None,
        [],
        (1.0,),
        {"value": 1.0},
        hostile_list,
        [True],
        [object()],
        [hostile_int],
        [hostile_float],
        [float("nan")],
        [float("inf")],
        [float("-inf")],
        [10**10_000],
    )
    _IntSubclass.armed = True
    _FloatSubclass.armed = True
    try:
        assert all(
            field_vector.validate_item(payload) is False
            for payload in invalid_field_vector_payloads
        )
    finally:
        _IntSubclass.armed = False
        _FloatSubclass.armed = False


def test_constructors_and_extractors_preserve_exact_copy_safe_coordinates() -> None:
    point = make_point3d_value(1, -2.5, 0)
    vector = make_vector3d_value(-0.0, 4, 8.25)
    assert point == TypedInlineValue(
        POINT_3D_DATA_TYPE_ID,
        1,
        {"x": 1, "y": -2.5, "z": 0},
    )
    assert vector == TypedInlineValue(
        VECTOR_3D_DATA_TYPE_ID,
        1,
        {"x": -0.0, "y": 4, "z": 8.25},
    )
    assert point3d_coordinates(point) == (1, -2.5, 0)
    assert vector3d_coordinates(vector) == (-0.0, 4, 8.25)
    assert type(point3d_coordinates(point)) is tuple
    assert type(vector3d_coordinates(vector)) is tuple


def test_corex_style_point_vector_and_plane_constructors_compose() -> None:
    point = _execute_spatial(
        spatial.CONSTRUCT_POINT_TYPE_ID,
        {"x": 2.0, "y": -3.0, "z": 5.0},
    )["point"]
    x_axis = _execute_spatial(
        spatial.CONSTRUCT_VECTOR_TYPE_ID,
        {"x": 2.0, "y": 0.0, "z": 0.0},
    )["vector"]
    y_axis = _execute_spatial(
        spatial.CONSTRUCT_VECTOR_TYPE_ID,
        {"x": 0.0, "y": 3.0, "z": 0.0},
    )["vector"]
    xy_plane = _execute_spatial(spatial.XY_PLANE_TYPE_ID, {"origin": point})["plane"]
    plane = _execute_spatial(
        spatial.CONSTRUCT_PLANE_TYPE_ID,
        {"origin": point, "x_axis": x_axis, "y_axis": y_axis},
    )["plane"]

    assert point3d_coordinates(point) == (2.0, -3.0, 5.0)
    assert vector3d_coordinates(x_axis) == (2.0, 0.0, 0.0)
    assert xy_plane.payload["normal"] == [0.0, 0.0, 1.0]
    assert plane.payload == {
        "origin": [2.0, -3.0, 5.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        "normal": [0.0, 0.0, 1.0],
    }
    with pytest.raises(ValueError, match="orthogonal"):
        _execute_spatial(
            spatial.CONSTRUCT_PLANE_TYPE_ID,
            {"origin": point, "x_axis": x_axis, "y_axis": x_axis},
        )


def test_none_is_optional_at_catalog_boundary_but_not_a_spatial_value() -> None:
    catalog = _registry().data_types
    for type_id in (
        IVECTOR_DATA_TYPE_ID,
        POINT_3D_DATA_TYPE_ID,
        VECTOR_3D_DATA_TYPE_ID,
    ):
        catalog.validate_carrier(type_id, None)
    for constructor in (make_point3d_value, make_vector3d_value):
        with pytest.raises(ValueError, match="invalid"):
            constructor(None, 0, 0)
    for extractor in (point3d_coordinates, vector3d_coordinates):
        with pytest.raises(ValueError, match="invalid"):
            extractor(None)


@pytest.mark.parametrize(
    "coordinates",
    (
        (True, 0, 0),
        (0, False, 0),
        (0, 0, float("nan")),
        (float("inf"), 0, 0),
        (0, float("-inf"), 0),
        (10**10_000, 0, 0),
    ),
)
def test_nonexact_nonfinite_and_huge_coordinates_fail_closed(
    coordinates: tuple[object, object, object],
) -> None:
    for constructor in (make_point3d_value, make_vector3d_value):
        with pytest.raises(ValueError, match="spatial coordinates are invalid"):
            constructor(*coordinates)


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"x": 1, "y": 2},
        {"x": 1, "y": 2, "z": 3, "extra": 4},
        {"x": 1, "y": 2, "wrong": 3},
        {"X": 1, "y": 2, "z": 3},
        {"x": "1", "y": 2, "z": 3},
        {"x": True, "y": 2, "z": 3},
        {"x": float("nan"), "y": 2, "z": 3},
    ),
)
def test_payload_shapes_fail_closed(payload: object) -> None:
    point_spec = COREX_SPATIAL_VALUE_DATA_TYPES[1]
    vector_spec = COREX_SPATIAL_VALUE_DATA_TYPES[2]
    assert point_spec.validate_item(payload) is False
    assert vector_spec.validate_item(payload) is False


def test_hostile_subclasses_are_rejected_without_executing_overrides() -> None:
    point_spec = COREX_SPATIAL_VALUE_DATA_TYPES[1]

    hostile_dict = _DictSubclass({"x": 1, "y": 2, "z": 3})
    hostile_key = _StringSubclass("x")
    hostile_key_payload = {hostile_key: 1, "y": 2, "z": 3}
    hostile_int = _IntSubclass(1)
    hostile_float = _FloatSubclass(2.0)

    _DictSubclass.armed = True
    _StringSubclass.armed = True
    _IntSubclass.armed = True
    _FloatSubclass.armed = True
    try:
        assert point_spec.validate_item(hostile_dict) is False
        assert point_spec.validate_item(hostile_key_payload) is False
        assert point_spec.validate_item({"x": hostile_int, "y": 2, "z": 3}) is False
        assert point_spec.validate_item({"x": 1, "y": hostile_float, "z": 3}) is False
    finally:
        _DictSubclass.armed = False
        _StringSubclass.armed = False
        _IntSubclass.armed = False
        _FloatSubclass.armed = False


def test_raw_dict_and_abstract_identity_are_never_valid_port_values() -> None:
    catalog = _registry().data_types
    for type_id in (POINT_3D_DATA_TYPE_ID, VECTOR_3D_DATA_TYPE_ID):
        with pytest.raises(DataTypeCatalogError, match="does not allow 'native'"):
            catalog.validate_carrier(type_id, {"x": 1, "y": 2, "z": 3})
    with pytest.raises(DataTypeCatalogError, match="must be concrete"):
        catalog.validate_carrier(
            IVECTOR_DATA_TYPE_ID,
            TypedInlineValue(
                IVECTOR_DATA_TYPE_ID,
                1,
                {"x": 1, "y": 2, "z": 3},
            ),
        )


def test_wrong_type_schema_payload_and_carrier_subclass_fail_generically() -> None:
    point = make_point3d_value(1, 2, 3)
    vector = make_vector3d_value(1, 2, 3)
    bad_values = (
        (point3d_coordinates, vector),
        (vector3d_coordinates, point),
        (
            point3d_coordinates,
            TypedInlineValue(
                POINT_3D_DATA_TYPE_ID,
                2,
                {"x": 1, "y": 2, "z": 3},
            ),
        ),
        (
            point3d_coordinates,
            TypedInlineValue(
                POINT_3D_DATA_TYPE_ID,
                1,
                {"x": 1, "y": 2},
            ),
        ),
        (
            point3d_coordinates,
            _InlineSubclass(
                POINT_3D_DATA_TYPE_ID,
                1,
                {"x": 1, "y": 2, "z": 3},
            ),
        ),
    )
    for extractor, value in bad_values:
        with pytest.raises(ValueError, match="spatial value is invalid"):
            extractor(value)

    catalog = _registry().data_types
    with pytest.raises(DataTypeCatalogError, match="schema version"):
        catalog.validate_carrier(
            POINT_3D_DATA_TYPE_ID,
            TypedInlineValue(
                POINT_3D_DATA_TYPE_ID,
                2,
                {"x": 1, "y": 2, "z": 3},
            ),
        )
    with pytest.raises(DataTypeCatalogError, match="not assignable"):
        catalog.validate_carrier(POINT_3D_DATA_TYPE_ID, vector)


def test_direct_datatree_and_stdio_json_round_trip_through_catalog() -> None:
    registry = _d024_registry()
    registry.register_plugin_bundle(
        COREX_GEOMETRY_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
    )
    registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_FIELD_VECTOR_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=COREX_SPATIAL_VALUES_OWNER_VERSION,
        replace_owner=True,
    )
    point = make_point3d_value(1, -2.5, 3)
    vector = make_vector3d_value(0.0, 4, -8)
    vector2d_payload = {"x": -0.0, "y": 4}
    vector2d = TypedInlineValue(
        spatial.VECTOR_2D_DATA_TYPE_ID,
        1,
        vector2d_payload,
    )
    field_vector_payload = [1, -2.5, -0.0, 4]
    field_vector = TypedInlineValue(
        spatial.FIELD_VECTOR_DATA_TYPE_ID,
        1,
        field_vector_payload,
    )
    registry.data_types.validate_carrier(POINT_3D_DATA_TYPE_ID, point)
    registry.data_types.validate_carrier(VECTOR_3D_DATA_TYPE_ID, vector)
    registry.data_types.validate_carrier(IVECTOR_DATA_TYPE_ID, vector)
    registry.data_types.validate_carrier(spatial.VECTOR_2D_DATA_TYPE_ID, vector2d)
    registry.data_types.validate_carrier(
        spatial.FIELD_VECTOR_DATA_TYPE_ID,
        field_vector,
    )

    for value in (point, vector, vector2d, field_vector):
        wire = serialize_runtime_value(value, catalog=registry.data_types)
        assert deserialize_runtime_value(wire, catalog=registry.data_types) == value
        assert (
            deserialize_runtime_value(
                json.loads(json.dumps(wire)),
                catalog=registry.data_types,
            )
            == value
        )
    vector2d_wire = serialize_runtime_value(
        vector2d,
        catalog=registry.data_types,
        declared_type_id=spatial.VECTOR_2D_DATA_TYPE_ID,
    )
    assert vector2d_wire == {
        "__ea_runtime_value__": "typed_inline",
        "data_type_id": spatial.VECTOR_2D_DATA_TYPE_ID,
        "schema_version": 1,
        "payload": vector2d_payload,
    }
    restored_vector2d = deserialize_runtime_value(
        json.loads(json.dumps(vector2d_wire)),
        catalog=registry.data_types,
        declared_type_id=spatial.VECTOR_2D_DATA_TYPE_ID,
    )
    assert restored_vector2d == vector2d
    assert restored_vector2d.payload == {"x": -0.0, "y": 4}

    field_vector_wire = serialize_runtime_value(
        field_vector,
        catalog=registry.data_types,
        declared_type_id=spatial.FIELD_VECTOR_DATA_TYPE_ID,
    )
    assert field_vector_wire == {
        "__ea_runtime_value__": "typed_inline",
        "data_type_id": spatial.FIELD_VECTOR_DATA_TYPE_ID,
        "schema_version": 1,
        "payload": field_vector_payload,
    }
    restored_field_vector = deserialize_runtime_value(
        json.loads(json.dumps(field_vector_wire)),
        catalog=registry.data_types,
        declared_type_id=spatial.FIELD_VECTOR_DATA_TYPE_ID,
    )
    assert restored_field_vector == field_vector
    assert restored_field_vector.payload == field_vector_payload
    assert [type(item) for item in restored_field_vector.payload] == [
        int,
        float,
        float,
        int,
    ]
    assert math.copysign(1.0, restored_field_vector.payload[2]) == -1.0

    tree = DataTree(
        (
            ((0,), (point, vector, vector2d, field_vector)),
            ((2, -1), (field_vector, vector2d, vector, point)),
        )
    )
    tree_wire = serialize_runtime_value(tree, catalog=registry.data_types)
    assert (
        deserialize_runtime_value(
            json.loads(json.dumps(tree_wire)),
            catalog=registry.data_types,
        )
        == tree
    )

    event = NodeSettledEvent(
        outputs={"spatial": SettledPortResult(status="value", value=tree)}
    )
    restored = dict_to_event(
        json.loads(json.dumps(event_to_dict(event, catalog=registry.data_types))),
        catalog=registry.data_types,
    )
    assert restored.outputs["spatial"].value == tree

    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(spatial.VECTOR_2D_DATA_TYPE_ID, point)
    with pytest.raises(DataTypeCatalogError, match="does not allow 'native'"):
        registry.data_types.validate_carrier(
            spatial.VECTOR_2D_DATA_TYPE_ID,
            {"x": 1, "y": 2},
        )
    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(
            spatial.VECTOR_2D_DATA_TYPE_ID,
            TypedInlineValue(
                spatial.VECTOR_2D_DATA_TYPE_ID,
                2,
                {"x": 1, "y": 2},
            ),
        )
    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(
            spatial.VECTOR_2D_DATA_TYPE_ID,
            TypedInlineValue(
                spatial.VECTOR_2D_DATA_TYPE_ID,
                1,
                {"x": 1, "z": 2},
            ),
        )
    with pytest.raises(DataTypeCatalogError, match="does not allow 'native'"):
        registry.data_types.validate_carrier(
            spatial.FIELD_VECTOR_DATA_TYPE_ID,
            [1, -2.5, -0.0, 4],
        )
    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(
            spatial.FIELD_VECTOR_DATA_TYPE_ID,
            TypedInlineValue(spatial.VECTOR_2D_DATA_TYPE_ID, 1, field_vector_payload),
        )
    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(
            spatial.FIELD_VECTOR_DATA_TYPE_ID,
            TypedInlineValue(
                spatial.FIELD_VECTOR_DATA_TYPE_ID, 2, field_vector_payload
            ),
        )
    with pytest.raises(DataTypeCatalogError):
        registry.data_types.validate_carrier(
            spatial.FIELD_VECTOR_DATA_TYPE_ID,
            TypedInlineValue(spatial.FIELD_VECTOR_DATA_TYPE_ID, 1, []),
        )
    # Shared carrier classification accepts TypedInlineValue subclasses. This
    # Stage 1 type-only contract still rejects such a wrapper as payload data.
    assert (
        registry.data_types.require(spatial.FIELD_VECTOR_DATA_TYPE_ID).validate_item(
            _InlineSubclass(
                spatial.FIELD_VECTOR_DATA_TYPE_ID,
                1,
                field_vector_payload,
            )
        )
        is False
    )




def test_d024_types_have_exact_root_parents_carriers_and_rejecting_handle() -> None:
    spatial_field = spatial.ISPATIAL_FIELD_DATA_TYPE
    point = spatial.POINT_2D_DATA_TYPE
    assert (
        spatial_field.type_id,
        spatial_field.display_name,
        spatial_field.family_id,
        spatial_field.parents,
        spatial_field.abstract,
        spatial_field.carriers,
        spatial_field.persistence,
        spatial_field.sensitivity,
        spatial_field.payload_schema_version,
        spatial_field.implementation_version,
    ) == (
        "COREX.SpatialFields.ISpatialField",
        "Spatial Field",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
    )
    assert (
        point.type_id,
        point.display_name,
        point.family_id,
        point.parents,
        point.abstract,
        point.carriers,
        point.persistence,
        point.sensitivity,
        point.payload_schema_version,
        point.implementation_version,
    ) == (
        "COREX.DataTypes.Point2D",
        "Point 2D",
        "geometry_value",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "inline",
        "normal",
        1,
        "1",
    )
    handle = RuntimeHandleRef(
        data_type_id=spatial.ISPATIAL_FIELD_DATA_TYPE_ID,
        schema_version=1,
        handle_id="spatial-field",
        kind="test.spatial_field",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )
    assert spatial_field.validate_item(object()) is False
    assert spatial_field.validate_item(handle) is False
    with pytest.raises(DataTypeCatalogError, match="must be concrete"):
        _d024_registry().data_types.validate_carrier(
            spatial.ISPATIAL_FIELD_DATA_TYPE_ID,
            handle,
        )


def test_point2d_exact_payload_and_hostile_values_fail_closed() -> None:
    point = spatial.make_point2d_value(1, -2.5)
    assert point == TypedInlineValue(
        spatial.POINT_2D_DATA_TYPE_ID,
        1,
        {"x": 1, "y": -2.5},
    )
    assert spatial.point2d_coordinates(point) == (1, -2.5)
    assert type(spatial.point2d_coordinates(point)) is tuple

    for coordinates in (
        (True, 0),
        (0, False),
        (float("nan"), 0),
        (0, float("inf")),
        (10**10_000, 0),
        ("1", 0),
    ):
        with pytest.raises(ValueError, match="Point2D coordinates are invalid"):
            spatial.make_point2d_value(*coordinates)

    point_spec = spatial.POINT_2D_DATA_TYPE
    hostile_dict = _DictSubclass({"x": 1, "y": 2})
    hostile_key = _StringSubclass("x")
    hostile_key_payload = {hostile_key: 1, "y": 2}
    hostile_int = _IntSubclass(1)
    hostile_float = _FloatSubclass(2.0)
    _DictSubclass.armed = True
    _StringSubclass.armed = True
    _IntSubclass.armed = True
    _FloatSubclass.armed = True
    try:
        assert point_spec.validate_item(hostile_dict) is False
        assert point_spec.validate_item(hostile_key_payload) is False
        assert point_spec.validate_item({"x": hostile_int, "y": 2}) is False
        assert point_spec.validate_item({"x": 1, "y": hostile_float}) is False
    finally:
        _DictSubclass.armed = False
        _StringSubclass.armed = False
        _IntSubclass.armed = False
        _FloatSubclass.armed = False

    for bad_value in (
        TypedInlineValue(spatial.POINT_2D_DATA_TYPE_ID, 2, {"x": 1, "y": 2}),
        TypedInlineValue(spatial.POINT_2D_DATA_TYPE_ID, 1, {"x": 1}),
        _InlineSubclass(spatial.POINT_2D_DATA_TYPE_ID, 1, {"x": 1, "y": 2}),
        spatial.make_point3d_value(1, 2, 3),
    ):
        with pytest.raises(ValueError, match="Point2D value is invalid"):
            spatial.point2d_coordinates(bad_value)


def test_bounding_interval_node_has_exact_ports_and_pure_min_max_results() -> None:
    spec = _spatial_function_adapters()[spatial.BOUNDING_INTERVAL_2D_TYPE_ID].spec()
    assert (spec.type_id, spec.properties) == ("math.bounding_interval_2d", ())
    assert [
        (port.key, port.direction, port.data_type, port.data_access, port.required)
        for port in spec.ports
    ] == [
        (
            "coordinates",
            "in",
            spatial.POINT_2D_DATA_TYPE_ID,
            "list",
            True,
        ),
        ("interval", "out", INTERVAL_2D_DATA_TYPE_ID, "item", None),
    ]
    assert spec.dynamic_port_groups == ()
    assert spec.settings_groups == ()
    assert spec.readiness_requirements == ()
    assert spec.runtime_behavior == "active"
    assert all(port.uses_property_default is False for port in spec.ports)

    one = _execute_spatial(
        spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
        {"coordinates": [spatial.make_point2d_value(4, -3.5)]},
    )
    assert one == {
        "interval": TypedInlineValue(
            INTERVAL_2D_DATA_TYPE_ID,
            1,
            {
                "u": {"start": 4.0, "end": 4.0},
                "v": {"start": -3.5, "end": -3.5},
            },
        )
    }

    multiple = _execute_spatial(
        spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
        {
            "coordinates": [
                spatial.make_point2d_value(4, -3.5),
                spatial.make_point2d_value(-2.25, 8),
                spatial.make_point2d_value(1.5, 0),
            ]
        },
    )
    interval = multiple["interval"]
    assert interval == TypedInlineValue(
        INTERVAL_2D_DATA_TYPE_ID,
        1,
        {
            "u": {"start": -2.25, "end": 4.0},
            "v": {"start": -3.5, "end": 8.0},
        },
    )
    assert is_interval_2d_payload(interval.payload)
    assert all(
        type(endpoint) is float
        for axis in interval.payload.values()
        for endpoint in axis.values()
    )


def test_bounding_interval_rejects_empty_nonlist_and_invalid_points() -> None:
    for coordinates in (
        [],
        (spatial.make_point2d_value(0, 0),),
        _ListSubclass([spatial.make_point2d_value(0, 0)]),
    ):
        with pytest.raises(ValueError, match="nonempty Point2D list"):
            _execute_spatial(
                spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
                {"coordinates": coordinates},
            )
    with pytest.raises(ValueError, match="Point2D value is invalid"):
        _execute_spatial(
            spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
            {"coordinates": [spatial.make_point3d_value(0, 0, 0)]},
        )


def test_point2d_and_interval2d_round_trip_through_foreign_owner_catalog() -> None:
    registry = _d024_registry()
    point = spatial.make_point2d_value(1, -2.5)
    interval = _execute_spatial(
        spatial.BOUNDING_INTERVAL_2D_TYPE_ID,
        {"coordinates": [point]},
    )["interval"]
    registry.data_types.validate_carrier(spatial.POINT_2D_DATA_TYPE_ID, point)
    registry.data_types.validate_carrier(INTERVAL_2D_DATA_TYPE_ID, interval)
    assert registry.data_types.owner_of(INTERVAL_2D_DATA_TYPE_ID) == (
        COREX_CORE_MEDIA_OWNER_ID
    )
    for value in (point, interval):
        wire = serialize_runtime_value(value, catalog=registry.data_types)
        assert (
            deserialize_runtime_value(
                json.loads(json.dumps(wire)),
                catalog=registry.data_types,
            )
            == value
        )






























def test_planar_tree_pattern_spec_is_abstract_handle_and_graph_root_only() -> None:
    candidate_types = (
        spatial.COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES
    )
    spec = candidate_types[-1]
    assert (
        spec.type_id,
        spec.display_name,
        spec.family_id,
        spec.description,
        spec.parents,
        spec.abstract,
        spec.carriers,
        spec.persistence,
        spec.sensitivity,
        spec.capabilities,
        spec.payload_schema_version,
        spec.implementation_version,
        spec.coerce_untyped_input,
    ) == (
        "COREX.SpatialPatterns.IPlanarTreePattern",
        "Planar Tree Pattern",
        "engineering",
        "",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        frozenset(),
        1,
        "1",
        None,
    )

    registry = bootstrap.build_builtin_registry()
    registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=spatial.COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=spatial.COREX_SPATIAL_VALUES_OWNER_VERSION,
        source_label=spatial.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    assert catalog.require(spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID) is spec
    assert catalog.is_assignable(
        spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    )
    for unrelated_parent in (
        spatial.IVECTOR_DATA_TYPE_ID,
        spatial.ISPATIAL_FIELD_DATA_TYPE_ID,
        spatial.TRANSFORM_3D_DATA_TYPE_ID,
        spatial.FIELD_VECTOR_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    ):
        assert not catalog.is_assignable(
            spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID,
            unrelated_parent,
        )


def test_planar_tree_pattern_abstract_validator_and_exact_handle_reject() -> None:
    spec = spatial.COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES[-1]
    handle = RuntimeHandleRef(
        data_type_id=spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID,
        schema_version=1,
        handle_id="planar-tree-pattern",
        kind="test.planar_tree_pattern",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )
    raw_values = (object(), {}, [], "planar-tree-pattern")
    assert all(spec.validate_item(value) is False for value in raw_values)
    assert spec.validate_item(handle) is False

    registry = bootstrap.build_builtin_registry()
    registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=spatial.COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=spatial.COREX_SPATIAL_VALUES_OWNER_VERSION,
        source_label=spatial.__name__,
        replace_owner=True,
    )
    for value in raw_values:
        with pytest.raises(DataTypeCatalogError, match="does not allow 'native'"):
            registry.data_types.validate_carrier(
                spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID,
                value,
            )
    with pytest.raises(DataTypeCatalogError, match="must be concrete"):
        registry.data_types.validate_carrier(
            spatial.PLANAR_TREE_PATTERN_DATA_TYPE_ID,
            handle,
        )






















def test_coordinate_system_payload_validation_is_strict() -> None:
    spec = spatial.COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_DATA_TYPES[-1]
    maximum = float.fromhex("0x1.fffffffffffffp+1023")
    minimum = float.fromhex("0x0.0000000000001p-1022")
    tolerance = 1e-12
    beyond_tolerance = math.nextafter(tolerance, math.inf)
    valid_payloads = (
        {
            "entries": [
                1,
                -2.5,
                -0.0,
                2,
                0.0,
                0,
                0,
                3.5,
                0.0,
                0.0,
                0,
                4,
            ]
        },
        {
            "entries": [
                0,
                0,
                0,
                2,
                0,
                0,
                0,
                3,
                0,
                0,
                0,
                -4,
            ]
        },
        {
            "entries": [
                maximum,
                minimum,
                -0.0,
                maximum,
                0.0,
                0,
                0,
                minimum,
                0.0,
                0,
                0.0,
                minimum,
            ]
        },
        {
            "entries": [
                0,
                0,
                0,
                1,
                0,
                0,
                tolerance,
                1,
                0,
                0,
                0,
                1,
            ]
        },
    )
    for payload in valid_payloads:
        entries = payload["entries"]
        entry_types = [type(entry) for entry in entries]
        signed_zero = math.copysign(1.0, entries[2])
        assert spec.validate_item(payload) is True
        assert payload["entries"] is entries
        assert [type(entry) for entry in entries] == entry_types
        assert math.copysign(1.0, entries[2]) == signed_zero

    baseline_entries = [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]
    hostile_dict = _DictSubclass({"entries": baseline_entries})
    hostile_key = _StringSubclass("entries")
    hostile_key_payload = {hostile_key: baseline_entries}
    hostile_int = _IntSubclass(1)
    hostile_float = _FloatSubclass(1.0)
    invalid_payloads = (
        None,
        object(),
        [],
        (),
        {},
        {"wrong": baseline_entries},
        {1: baseline_entries},
        {"entries": baseline_entries, "extra": None},
        {"entries": None},
        {"entries": tuple(baseline_entries)},
        {"entries": baseline_entries[:-1]},
        {"entries": [*baseline_entries, 0]},
        {"entries": [*baseline_entries[:3], [1, 0, 0], *baseline_entries[4:]]},
        {"entries": _ListSubclass(baseline_entries)},
        hostile_dict,
        hostile_key_payload,
        {"entries": [*baseline_entries[:3], True, *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], hostile_int, *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], hostile_float, *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], 10**400, *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], float("nan"), *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], float("inf"), *baseline_entries[4:]]},
        {"entries": [*baseline_entries[:3], float("-inf"), *baseline_entries[4:]]},
        {"entries": [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1]},
        {"entries": [0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 0, 1]},
        {
            "entries": [
                0,
                0,
                0,
                1,
                0,
                0,
                beyond_tolerance,
                1,
                0,
                0,
                0,
                1,
            ]
        },
    )
    _DictSubclass.armed = True
    _StringSubclass.armed = True
    _IntSubclass.armed = True
    _FloatSubclass.armed = True
    try:
        assert all(spec.validate_item(payload) is False for payload in invalid_payloads)
    finally:
        _DictSubclass.armed = False
        _StringSubclass.armed = False
        _IntSubclass.armed = False
        _FloatSubclass.armed = False


def test_coordinate_system_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = bootstrap.build_builtin_registry()
    registry.register_plugin_bundle(
        COREX_GEOMETRY_COORDINATE_SYSTEM_VALUE_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_GEOMETRY_CONTRACTS_OWNER_ID,
        owner_version=COREX_GEOMETRY_CONTRACTS_OWNER_VERSION,
        source_label="ea_node_editor.nodes.builtins.geometry_contracts",
        replace_owner=True,
    )
    registry.register_plugin_bundle(
        spatial.COREX_SPATIAL_VALUES_COORDINATE_SYSTEM_CANDIDATE_CONTRACT_MANIFEST,
        (),
        owner_id=spatial.COREX_SPATIAL_VALUES_OWNER_ID,
        owner_version=spatial.COREX_SPATIAL_VALUES_OWNER_VERSION,
        source_label=spatial.__name__,
        replace_owner=True,
    )
    catalog = registry.data_types
    entries = [1, -2.5, -0.0, 2, 0.0, 0, 0, 3.5, 0.0, 0.0, 0, -4]
    value = TypedInlineValue(
        spatial.CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID,
        1,
        {"entries": entries},
    )
    declarations = (
        spatial.CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID,
        COORDINATE_SYSTEM_DATA_TYPE_ID,
        SPATIAL_OBJECT_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    )
    for declared_type_id in declarations:
        assert catalog.is_assignable(value.data_type_id, declared_type_id)
        catalog.validate_carrier(declared_type_id, value)
        wire = serialize_runtime_value(
            value,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert wire == {
            "__ea_runtime_value__": "typed_inline",
            "data_type_id": spatial.CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID,
            "schema_version": 1,
            "payload": {"entries": entries},
        }
        restored = deserialize_runtime_value(
            json.loads(json.dumps(wire)),
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert restored == value
        assert [type(entry) for entry in restored.payload["entries"]] == [
            type(entry) for entry in entries
        ]
        assert math.copysign(1.0, restored.payload["entries"][2]) == -1.0

    vector2d = TypedInlineValue(
        spatial.VECTOR_2D_DATA_TYPE_ID,
        1,
        {"x": -0.0, "y": 2},
    )
    catalog.validate_carrier(SPATIAL_OBJECT_DATA_TYPE_ID, vector2d)
    for unrelated_type_id in (
        spatial.VECTOR_3D_DATA_TYPE_ID,
        CLIPPABLE_GRAPH_DATA_TYPE_ID,
    ):
        with pytest.raises(DataTypeCatalogError, match="not assignable"):
            catalog.validate_carrier(unrelated_type_id, value)

    assert (
        catalog.require(spatial.CONCRETE_COORDINATE_SYSTEM_DATA_TYPE_ID).persistence,
        catalog.require(COORDINATE_SYSTEM_DATA_TYPE_ID).persistence,
        catalog.require(SPATIAL_OBJECT_DATA_TYPE_ID).persistence,
    ) == ("never", "never", "never")
