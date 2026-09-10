from __future__ import annotations

import json

import pytest

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.nodes.builtins.core_media import (
    ANIMATION_DATA_TYPE_ID,
    CELL_DATA_TYPE_ID,
    DATETIME_DATA_TYPE_ID,
    INTERVAL_2D_DATA_TYPE_ID,
    COREX_CORE_MEDIA_CONTRACT_MANIFEST,
    COREX_CORE_MEDIA_DATA_TYPES,
    COREX_CORE_MEDIA_OWNER_ID,
    COREX_CORE_MEDIA_OWNER_VERSION,
    TENSOR_DATA_TYPE_ID,
    is_animation_artifact,
    is_cell_payload,
    is_datetime_payload,
    is_interval_2d_payload,
    is_tensor_payload,
)
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    RuntimeArtifactRef,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)

_INT32_MAX = 2_147_483_647
_SYSTEM_SINGLE_MAX = 3.4028234663852886e38


class _IntSubclass(int):
    pass


class _FloatSubclass(float):
    pass


class _StrSubclass(str):
    pass


class _DictSubclass(dict):
    pass


class _ListSubclass(list):
    pass


class _ArtifactSubclass(RuntimeArtifactRef):
    pass


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_CORE_MEDIA_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_CORE_MEDIA_OWNER_ID,
        owner_version=COREX_CORE_MEDIA_OWNER_VERSION,
    )
    return registry


def _datetime_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "year": 2024,
        "month": 2,
        "day": 29,
        "hour": 23,
        "minute": 59,
        "second": 59,
        "millisecond": 999,
        "kind": "Utc",
    }
    payload.update(updates)
    return payload


def _tensor_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "data": [1.0, -2.0, 3.0, 4.0],
        "dimensions": [2, 2],
    }
    payload.update(updates)
    return payload


def _cell_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {"Column": "A", "Row": 1}
    payload.update(updates)
    return payload


def _interval_2d_payload(
    *,
    u: object | None = None,
    v: object | None = None,
) -> dict[str, object]:
    return {
        "u": {"start": 5.0, "end": -1.0} if u is None else u,
        "v": {"start": 2.0, "end": 2.0} if v is None else v,
    }


def _artifact(
    scope: str = "staged",
    *,
    data_type_id: str = ANIMATION_DATA_TYPE_ID,
    schema_version: int = 1,
    format: str = "gif",
) -> RuntimeArtifactRef:
    factory = (
        RuntimeArtifactRef.staged if scope == "staged" else RuntimeArtifactRef.managed
    )
    return factory(
        f"animation-{scope}",
        data_type_id=data_type_id,
        schema_version=schema_version,
        format=format,
        size_bytes=43,
        sha256="a" * 64,
        provenance="corex.test.corex_animation",
    )


def _inline_values() -> tuple[TypedInlineValue, ...]:
    return (
        TypedInlineValue(DATETIME_DATA_TYPE_ID, 1, _datetime_payload()),
        TypedInlineValue(TENSOR_DATA_TYPE_ID, 1, _tensor_payload()),
        TypedInlineValue(CELL_DATA_TYPE_ID, 1, _cell_payload()),
        TypedInlineValue(
            INTERVAL_2D_DATA_TYPE_ID,
            1,
            _interval_2d_payload(),
        ),
    )




def test_carriers_families_and_persistence_are_exact() -> None:
    facts = {
        spec.type_id: (spec.family_id, spec.carriers, spec.persistence)
        for spec in COREX_CORE_MEDIA_DATA_TYPES
    }
    assert facts == {
        DATETIME_DATA_TYPE_ID: ("scalar", frozenset({"inline"}), "inline"),
        TENSOR_DATA_TYPE_ID: ("container", frozenset({"inline"}), "inline"),
        CELL_DATA_TYPE_ID: ("corex_data", frozenset({"inline"}), "never"),
        INTERVAL_2D_DATA_TYPE_ID: (
            "interval",
            frozenset({"inline"}),
            "inline",
        ),
        ANIMATION_DATA_TYPE_ID: (
            "viewer",
            frozenset({"artifact"}),
            "saved_artifact",
        ),
    }


def test_datetime_accepts_calendar_and_dotnet_boundaries() -> None:
    assert is_datetime_payload(_datetime_payload())
    assert is_datetime_payload(
        _datetime_payload(
            year=1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            millisecond=0,
            kind="Unspecified",
        )
    )
    assert is_datetime_payload(
        _datetime_payload(
            year=9999,
            month=12,
            day=31,
            kind="Local",
        )
    )


@pytest.mark.parametrize(
    "payload",
    (
        _datetime_payload(year=0),
        _datetime_payload(year=10_000),
        _datetime_payload(year=2023, month=2, day=29),
        _datetime_payload(hour=24),
        _datetime_payload(second=60),
        _datetime_payload(millisecond=-1),
        _datetime_payload(millisecond=1000),
        _datetime_payload(kind="UTC"),
        _datetime_payload(year=True),
        _datetime_payload(year=_IntSubclass(2024)),
        _datetime_payload(kind=_StrSubclass("Utc")),
        {**_datetime_payload(), "extra": 1},
        {key: value for key, value in _datetime_payload().items() if key != "day"},
        _DictSubclass(_datetime_payload()),
        {
            **{
                key: value
                for key, value in _datetime_payload().items()
                if key != "kind"
            },
            _StrSubclass("kind"): "Utc",
        },
    ),
)
def test_datetime_rejects_invalid_shapes_values_and_subclasses(
    payload: object,
) -> None:
    assert not is_datetime_payload(payload)


def test_datetime_huge_integer_fails_validation_without_leaking_overflow() -> None:
    payload = _datetime_payload(year=10**100)
    assert not is_datetime_payload(payload)
    value = TypedInlineValue(DATETIME_DATA_TYPE_ID, 1, payload)
    with pytest.raises(
        DataTypeCatalogError,
        match="output value is invalid for declared data type",
    ):
        _registry().data_types.validate_carrier(DATETIME_DATA_TYPE_ID, value)


def test_tensor_accepts_exact_float32_payload_and_dimensions() -> None:
    assert is_tensor_payload(_tensor_payload())
    assert is_tensor_payload(
        {
            "data": [_SYSTEM_SINGLE_MAX, -_SYSTEM_SINGLE_MAX],
            "dimensions": [1, 2],
        }
    )


@pytest.mark.parametrize(
    "payload",
    (
        _tensor_payload(data=(1.0, 2.0, 3.0, 4.0)),
        _tensor_payload(data=_ListSubclass([1.0, 2.0, 3.0, 4.0])),
        _tensor_payload(data=[1, 2.0, 3.0, 4.0]),
        _tensor_payload(data=[_FloatSubclass(1.0), 2.0, 3.0, 4.0]),
        _tensor_payload(data=[float("nan"), 2.0, 3.0, 4.0]),
        _tensor_payload(data=[float("inf"), 2.0, 3.0, 4.0]),
        _tensor_payload(data=[_SYSTEM_SINGLE_MAX * 2.0, 2.0, 3.0, 4.0]),
        _tensor_payload(dimensions=()),
        _tensor_payload(dimensions=[]),
        _tensor_payload(dimensions=_ListSubclass([2, 2])),
        _tensor_payload(dimensions=[2, True]),
        _tensor_payload(dimensions=[2, _IntSubclass(2)]),
        _tensor_payload(dimensions=[2, 0]),
        _tensor_payload(dimensions=[2, _INT32_MAX + 1]),
        _tensor_payload(dimensions=[_INT32_MAX, 2]),
        _tensor_payload(dimensions=[4, 2]),
        {**_tensor_payload(), "extra": None},
        _DictSubclass(_tensor_payload()),
    ),
)
def test_tensor_rejects_nonexact_nonfinite_mismatched_and_overflow_values(
    payload: object,
) -> None:
    assert not is_tensor_payload(payload)


def test_tensor_retains_the_shared_one_mib_inline_limit() -> None:
    with pytest.raises(ValueError, match="1048576 bytes"):
        TypedInlineValue(
            TENSOR_DATA_TYPE_ID,
            1,
            {"data": [0.0] * 300_000, "dimensions": [300_000]},
        )


def test_cell_accepts_proven_bounds_without_excel_sheet_caps() -> None:
    assert is_cell_payload(_cell_payload(Column="A", Row=1))
    assert is_cell_payload(_cell_payload(Column="XFD", Row=1_048_576))
    assert is_cell_payload(_cell_payload(Column="ZZZZZZZZZZZZ", Row=_INT32_MAX))


@pytest.mark.parametrize(
    "payload",
    (
        _cell_payload(Column=""),
        _cell_payload(Column="a"),
        _cell_payload(Column="A1"),
        _cell_payload(Column="Å"),
        _cell_payload(Column=_StrSubclass("A")),
        _cell_payload(Row=0),
        _cell_payload(Row=_INT32_MAX + 1),
        _cell_payload(Row=True),
        _cell_payload(Row=_IntSubclass(1)),
        {"Column": "A"},
        {"Column": "A", "Row": 1, "extra": None},
        _DictSubclass(_cell_payload()),
        {_StrSubclass("Column"): "A", "Row": 1},
    ),
)
def test_cell_rejects_bad_datacontract_shapes_and_subclasses(
    payload: object,
) -> None:
    assert not is_cell_payload(payload)


def test_interval_2d_preserves_reversed_and_equal_endpoint_order() -> None:
    reversed_and_equal = _interval_2d_payload()
    assert is_interval_2d_payload(reversed_and_equal)
    assert reversed_and_equal == {
        "u": {"start": 5.0, "end": -1.0},
        "v": {"start": 2.0, "end": 2.0},
    }


@pytest.mark.parametrize(
    "payload",
    (
        _interval_2d_payload(u={"start": 0, "end": 1.0}),
        _interval_2d_payload(u={"start": _FloatSubclass(0.0), "end": 1.0}),
        _interval_2d_payload(u={"start": float("nan"), "end": 1.0}),
        _interval_2d_payload(v={"start": 0.0, "end": float("inf")}),
        _interval_2d_payload(u={"start": 0.0}),
        _interval_2d_payload(u={"start": 0.0, "end": 1.0, "extra": 2.0}),
        _interval_2d_payload(u=[0.0, 1.0]),
        {"u": {"start": 0.0, "end": 1.0}},
        {**_interval_2d_payload(), "extra": None},
        _DictSubclass(_interval_2d_payload()),
    ),
)
def test_interval_2d_rejects_nonexact_nonfinite_and_wrong_shapes(
    payload: object,
) -> None:
    assert not is_interval_2d_payload(payload)


def test_gif_artifact_contract_accepts_staged_and_managed_transport() -> None:
    registry = _registry()
    for artifact in (_artifact("staged"), _artifact("managed")):
        assert is_animation_artifact(artifact)
        registry.data_types.validate_carrier(ANIMATION_DATA_TYPE_ID, artifact)
        wire = serialize_runtime_value(artifact, catalog=registry.data_types)
        assert (
            deserialize_runtime_value(
                json.loads(json.dumps(wire)),
                catalog=registry.data_types,
            )
            == artifact
        )


def test_animation_rejects_raw_non_gif_wrong_identity_schema_and_subclass() -> None:
    valid = _artifact()
    subclass = _ArtifactSubclass(
        ref=valid.ref,
        artifact_id=valid.artifact_id,
        scope=valid.scope,
        data_type_id=valid.data_type_id,
        schema_version=valid.schema_version,
        format=valid.format,
        size_bytes=valid.size_bytes,
        sha256=valid.sha256,
        provenance=valid.provenance,
        metadata=valid.metadata,
    )
    invalid = (
        b"GIF89a",
        "animation.gif",
        {"format": "gif"},
        _artifact(format="png"),
        _artifact(data_type_id=GRAPH_DATA_TYPE_ID),
        _artifact(schema_version=2),
        subclass,
    )
    assert all(not is_animation_artifact(value) for value in invalid)
    registry = _registry()
    for value in invalid:
        with pytest.raises((TypeError, ValueError)):
            registry.data_types.validate_carrier(ANIMATION_DATA_TYPE_ID, value)


def test_direct_inline_and_nested_datatree_stdio_round_trips() -> None:
    registry = _registry()
    values = _inline_values()
    for value in values:
        registry.data_types.validate_carrier(value.data_type_id, value)
        wire = serialize_runtime_value(value, catalog=registry.data_types)
        assert (
            deserialize_runtime_value(
                json.loads(json.dumps(wire)),
                catalog=registry.data_types,
            )
            == value
        )

    tree = DataTree(
        (
            ((0,), (*values, _artifact("staged"))),
            ((2, 1), (_artifact("managed"), values[0])),
        )
    )
    wire = serialize_runtime_value(tree, catalog=registry.data_types)
    assert (
        deserialize_runtime_value(
            json.loads(json.dumps(wire)),
            catalog=registry.data_types,
        )
        == tree
    )

    event = NodeSettledEvent(
        outputs={"value": SettledPortResult(status="value", value=tree)}
    )
    restored = dict_to_event(
        json.loads(json.dumps(event_to_dict(event, catalog=registry.data_types))),
        catalog=registry.data_types,
    )
    assert restored.outputs["value"].value == tree
