from __future__ import annotations

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.tree_path import (
    TREE_PATH_DATA_TYPE_ID,
    is_tree_path_payload,
    make_tree_path_value,
    tree_path_indices,
)
from ea_node_editor.runtime_contracts import (
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)


@pytest.mark.parametrize(
    "indices",
    ([], [0], [0, -2, 7], [-(2**31), 2**31 - 1]),
)
def test_tree_path_preserves_signed_int32_indices(indices: list[int]) -> None:
    value = make_tree_path_value(indices)
    assert tree_path_indices(value) == indices


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"indices": [2**31]},
        {"indices": [-(2**31) - 1]},
        {"indices": [True]},
        {"indices": ["0"]},
        {"indices": (0,)},
        {"other": []},
    ),
)
def test_tree_path_rejects_invalid_payloads(payload: object) -> None:
    assert is_tree_path_payload(payload) is False


def test_tree_path_round_trips_through_runtime_json() -> None:
    registry = build_builtin_registry()
    value = make_tree_path_value([3, -1, 4])
    wire = serialize_runtime_value(
        value,
        catalog=registry.data_types,
        declared_type_id=TREE_PATH_DATA_TYPE_ID,
    )
    assert deserialize_runtime_value(wire, catalog=registry.data_types) == value
    registry.data_types.validate_carrier(TREE_PATH_DATA_TYPE_ID, value)

    with pytest.raises(ValueError):
        tree_path_indices(
            TypedInlineValue(TREE_PATH_DATA_TYPE_ID, 2, {"indices": [0]})
        )
