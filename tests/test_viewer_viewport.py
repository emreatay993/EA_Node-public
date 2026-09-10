from __future__ import annotations

import json
import struct

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.builtins.spatial_values import (
    POINT_3D_DATA_TYPE_ID,
    COREX_SPATIAL_VALUE_DATA_TYPES,
    VECTOR_3D_DATA_TYPE_ID,
    make_point3d_value,
    make_vector3d_value,
)
from ea_node_editor.nodes.builtins.viewer_viewport import (
    CONSTRUCT_VIEW_TYPE_ID,
    DECONSTRUCT_VIEW_TYPE_ID,
    DEFAULT_CAMERA_POSITION,
    DEFAULT_CAMERA_TARGET,
    DEFAULT_CAMERA_UP_VECTOR,
    COREX_VIEWER_VIEWPORT_DATA_TYPES,
    COREX_VIEWER_VIEWPORT_OWNER_ID,
    VIEWER_VIEWPORT_DATA_TYPE_ID,
    execute_construct_view,
    execute_deconstruct_view,
    is_viewer_viewport_payload,
    make_viewer_viewport_value,
)
from ea_node_editor.nodes.core_data_types import (
    BOOLEAN_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.persistence.project_codec import JsonProjectCodec
from ea_node_editor.runtime_contracts import (
    TypedInlineValue,
)


_SINGLE_MAX = 3.4028234663852886e38

_registry = build_builtin_registry

_CONSTRUCT_DEFAULT_ROWS = (
    (
        "ConstructViewCameraPositionName",
        POINT_3D_DATA_TYPE_ID,
        "ConstructViewCameraPositionDescription",
        (-180.0, -180.0, 180.0),
    ),
    (
        "ConstructViewCameraTargetName",
        POINT_3D_DATA_TYPE_ID,
        "ConstructViewCameraTargetDescription",
        (0.0, 0.0, 0.0),
    ),
    (
        "ConstructViewCameraUpVectorName",
        VECTOR_3D_DATA_TYPE_ID,
        "ConstructViewCameraUpVectorDescription",
        (0.4082483, 0.4082483, 0.8164966),
    ),
    (
        "ConstructViewDisplayModeName",
        INTEGER_DATA_TYPE_ID,
        "ConstructViewDisplayModeDescription",
        1,
    ),
    (
        "ConstructViewProjectionModeName",
        INTEGER_DATA_TYPE_ID,
        "ConstructViewProjectionModeDescription",
        0,
    ),
    (
        "ConstructViewShowMeshEdgesName",
        BOOLEAN_DATA_TYPE_ID,
        "ConstructViewShowMeshEdgesDescription",
        True,
    ),
    (
        "ConstructViewShowAttributeColorsName",
        BOOLEAN_DATA_TYPE_ID,
        "ConstructViewShowAttributeColorsDescription",
        False,
    ),
    (
        "ConstructViewShowTriadName",
        BOOLEAN_DATA_TYPE_ID,
        "ConstructViewShowTriadDescription",
        True,
    ),
    (
        "ConstructViewShowViewCubeName",
        BOOLEAN_DATA_TYPE_ID,
        "ConstructViewShowViewCubeDescription",
        True,
    ),
    (
        "ConstructViewShowAxesName",
        BOOLEAN_DATA_TYPE_ID,
        "ConstructViewShowAxesDescription",
        True,
    ),
)

_DECONSTRUCT_OUTPUT_ROWS = (
    (
        "DeconstructViewCameraPositionName",
        POINT_3D_DATA_TYPE_ID,
        "DeconstructViewCameraPositionDescription",
    ),
    (
        "DeconstructViewCameraTargetName",
        POINT_3D_DATA_TYPE_ID,
        "DeconstructViewCameraTargetDescription",
    ),
    (
        "DeconstructViewUpDirectionName",
        VECTOR_3D_DATA_TYPE_ID,
        "DeconstructViewUpDirectionDescription",
    ),
    (
        "DeconstructViewDisplayModeName",
        INTEGER_DATA_TYPE_ID,
        "DeconstructViewDisplayModeDescription",
    ),
    (
        "DeconstructViewProjectionModeName",
        INTEGER_DATA_TYPE_ID,
        "DeconstructViewProjectionModeDescription",
    ),
    (
        "DeconstructViewShowMeshEdgesName",
        BOOLEAN_DATA_TYPE_ID,
        "DeconstructViewShowMeshEdgesDescription",
    ),
    (
        "DeconstructViewShowAttributeColorsName",
        BOOLEAN_DATA_TYPE_ID,
        "DeconstructViewShowAttributeColorsDescription",
    ),
    (
        "DeconstructViewShowTriadName",
        BOOLEAN_DATA_TYPE_ID,
        "DeconstructViewShowTriadDescription",
    ),
    (
        "DeconstructViewShowViewCubeName",
        BOOLEAN_DATA_TYPE_ID,
        "DeconstructViewShowViewCubeDescription",
    ),
    (
        "DeconstructViewShowAxesName",
        BOOLEAN_DATA_TYPE_ID,
        "DeconstructViewShowAxesDescription",
    ),
)


def _context(inputs: dict[str, object]) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=inputs,
        properties={},
        emit_log=lambda _level, _message: None,
    )


def test_viewport_type_facts_and_owner_are_exact() -> None:
    (viewport,) = COREX_VIEWER_VIEWPORT_DATA_TYPES
    assert (
        viewport.type_id,
        viewport.family_id,
        viewport.parents,
        viewport.abstract,
        viewport.carriers,
        viewport.persistence,
        viewport.sensitivity,
        viewport.payload_schema_version,
        viewport.implementation_version,
    ) == (
        VIEWER_VIEWPORT_DATA_TYPE_ID,
        "viewer",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "inline",
        "normal",
        1,
        "1",
    )
    registry = _registry()
    assert (
        registry.data_types.owner_of(VIEWER_VIEWPORT_DATA_TYPE_ID)
        == COREX_VIEWER_VIEWPORT_OWNER_ID
    )
    assert len(COREX_SPATIAL_VALUE_DATA_TYPES) == 3
    assert registry.data_types.snapshot()


def _valid_viewport() -> TypedInlineValue:
    return make_viewer_viewport_value(
        camera_position=make_point3d_value(10.0, 20.0, 30.0),
        camera_target=make_point3d_value(1.0, 2.0, 3.0),
        camera_up_vector=make_vector3d_value(0.0, 0.0, 1.0),
        field_width=12.5,
        field_height=12.5,
        display_mode=1,
        projection_mode=0,
        show_mesh_edges=False,
        show_attribute_colors=True,
        show_viewer_triad=True,
        show_view_cube=False,
        show_viewer_axes=True,
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload.pop("field_width"),
        lambda payload: payload.__setitem__("extra", 1),
        lambda payload: payload.__setitem__("field_width", 1),
        lambda payload: payload.__setitem__("field_height", float("nan")),
        lambda payload: payload.__setitem__("field_width", float("inf")),
        lambda payload: payload.__setitem__("field_width", _SINGLE_MAX * 2.0),
        lambda payload: payload.__setitem__("display_mode", True),
        lambda payload: payload.__setitem__("display_mode", 4),
        lambda payload: payload.__setitem__("projection_mode", -1),
        lambda payload: payload.__setitem__("show_mesh_edges", 1),
        lambda payload: payload.__setitem__("camera_position", {"x": 0}),
        lambda payload: payload.__setitem__(
            "camera_up_vector",
            {"x": 0, "y": 0, "z": float("nan")},
        ),
    ),
)
def test_payload_shape_and_bounds_fail_closed(mutate) -> None:
    payload = _valid_viewport().payload.copy()
    mutate(payload)
    assert is_viewer_viewport_payload(payload) is False


def test_payload_rejects_hostile_subclasses_without_running_them() -> None:
    class HostileDict(dict):
        def __len__(self) -> int:
            raise AssertionError("hostile dict read")

    class HostileString(str):
        armed = False

        def __hash__(self) -> int:
            if self.armed:
                raise AssertionError("hostile key hash")
            return super().__hash__()

        def __eq__(self, _other: object) -> bool:
            if self.armed:
                raise AssertionError("hostile key equality")
            return False

    class HostileFloat(float):
        def __float__(self) -> float:
            raise AssertionError("hostile float conversion")

    payload = _valid_viewport().payload
    hostile_key = HostileString("field_width")
    hostile_key_payload = dict(payload)
    hostile_key_payload[hostile_key] = hostile_key_payload.pop("field_width")
    HostileString.armed = True
    try:
        assert is_viewer_viewport_payload(HostileDict(payload)) is False
        assert is_viewer_viewport_payload(hostile_key_payload) is False
        hostile_value = dict(payload)
        hostile_value["field_width"] = HostileFloat(1.0)
        assert is_viewer_viewport_payload(hostile_value) is False
    finally:
        HostileString.armed = False


def test_construct_defaults_are_hidden_same_key_item_properties() -> None:
    construct = _registry().get_spec(CONSTRUCT_VIEW_TYPE_ID)
    inputs = tuple(port for port in construct.ports if port.direction == "in")
    assert len(inputs) == len(construct.properties) == 10
    assert tuple(port.key for port in inputs) == tuple(
        prop.key for prop in construct.properties
    )
    assert all(
        (
            port.required,
            port.uses_property_default,
            port.data_access,
            prop.inspector_visible,
        )
        == (True, True, "item", False)
        for port, prop in zip(inputs, construct.properties, strict=True)
    )
    properties = {prop.key: prop for prop in construct.properties}
    assert properties["camera_position"].default == DEFAULT_CAMERA_POSITION
    assert properties["camera_target"].default == DEFAULT_CAMERA_TARGET
    assert properties["camera_up_vector"].default == DEFAULT_CAMERA_UP_VECTOR
    assert all(
        type(properties[key].default) is TypedInlineValue
        for key in ("camera_position", "camera_target", "camera_up_vector")
    )
    assert (
        properties["camera_position"].persistence_data_type_id == POINT_3D_DATA_TYPE_ID
    )
    assert (
        properties["camera_up_vector"].persistence_data_type_id
        == VECTOR_3D_DATA_TYPE_ID
    )
    assert (
        properties["display_mode"].type,
        properties["display_mode"].minimum,
        properties["display_mode"].maximum,
    ) == (
        "int",
        0,
        3,
    )
    assert (
        properties["projection_mode"].type,
        properties["projection_mode"].minimum,
        properties["projection_mode"].maximum,
    ) == ("int", 0, 1)
    assert all(properties[key].type == "bool" for key in tuple(properties)[5:])


def _construct_inputs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "camera_position": make_point3d_value(3.0, 4.0, 12.0),
        "camera_target": make_point3d_value(0.0, 0.0, 0.0),
        "camera_up_vector": make_vector3d_value(3.0, 4.0, 5.0),
        "display_mode": 1,
        "projection_mode": 0,
        "show_mesh_edges": False,
        "show_attribute_colors": True,
        "show_triad": False,
        "show_view_cube": True,
        "show_axes": False,
    }
    values.update(overrides)
    return values


def _single(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def test_construct_uses_two_stage_single_rounding_and_preserves_up_vector() -> None:
    result = execute_construct_view(_context(_construct_inputs()))
    viewport = result.outputs["viewport"]
    assert type(viewport) is TypedInlineValue
    payload = viewport.payload
    assert payload["field_width"] == _single(_single(13.0) / 2.5)
    assert payload["field_height"] == _single(_single(13.0) / 2.5)
    assert payload["camera_up_vector"] == {"x": 3.0, "y": 4.0, "z": 5.0}
    assert payload["show_mesh_edges"] is False


@pytest.mark.parametrize("display_mode", (2, 3))
def test_construct_forces_mesh_edges_only_for_edge_display_modes(
    display_mode: int,
) -> None:
    result = execute_construct_view(
        _context(
            _construct_inputs(
                display_mode=display_mode,
                show_mesh_edges=False,
            )
        )
    )
    assert result.outputs["viewport"].payload["show_mesh_edges"] is True


def test_degenerate_camera_is_zero_and_overflow_fails_safely() -> None:
    same = make_point3d_value(1.0, 2.0, 3.0)
    result = execute_construct_view(
        _context(_construct_inputs(camera_position=same, camera_target=same))
    )
    assert result.outputs["viewport"].payload["field_width"] == 0.0
    with pytest.raises(ValueError, match="Single range"):
        execute_construct_view(
            _context(
                _construct_inputs(
                    camera_position=make_point3d_value(1e308, 0.0, 0.0),
                )
            )
        )


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("display_mode", True),
        ("display_mode", 4),
        ("projection_mode", -1),
        ("show_axes", 1),
        ("camera_target", make_vector3d_value(0.0, 0.0, 0.0)),
    ),
)
def test_construct_runtime_inputs_fail_closed(key: str, value: object) -> None:
    with pytest.raises(ValueError):
        execute_construct_view(
            _context(_construct_inputs(**{key: value}))
        )


def test_construct_deconstruct_runtime_round_trip_omits_field_dimensions() -> None:
    constructed = execute_construct_view(_context(_construct_inputs())).outputs[
        "viewport"
    ]
    outputs = execute_deconstruct_view(constructed).outputs
    assert set(outputs) == set(_construct_inputs())
    assert outputs == _construct_inputs()
    assert "field_width" not in outputs
    assert "field_height" not in outputs
    with pytest.raises(ValueError, match="ViewerViewport input is invalid"):
        execute_deconstruct_view(
            TypedInlineValue(
                VIEWER_VIEWPORT_DATA_TYPE_ID,
                2,
                constructed.payload,
            )
        )
















def test_static_typed_defaults_survive_fresh_registry_project_codec_round_trip() -> (
    None
):
    source_registry = _registry()
    properties = source_registry.default_properties(CONSTRUCT_VIEW_TYPE_ID)
    model = GraphModel()
    source = model.add_node(
        model.active_workspace.workspace_id,
        CONSTRUCT_VIEW_TYPE_ID,
        "Construct View",
        0.0,
        0.0,
        properties=properties,
    )

    codec = JsonProjectCodec(_registry())
    document = codec.to_persistent_document(model.project)
    restored = codec.from_document(json.loads(json.dumps(document)))
    restored_source = next(
        node
        for workspace in restored.workspaces.values()
        for node in workspace.nodes.values()
        if node.node_id == source.node_id
    )

    for key, expected in (
        ("camera_position", DEFAULT_CAMERA_POSITION),
        ("camera_target", DEFAULT_CAMERA_TARGET),
        ("camera_up_vector", DEFAULT_CAMERA_UP_VECTOR),
    ):
        assert type(properties[key]) is TypedInlineValue
        assert type(restored_source.properties[key]) is TypedInlineValue
        assert restored_source.properties[key] == expected
