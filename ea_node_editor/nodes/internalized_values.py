# Purpose: Decode strict JSON DataTree envelopes for typed inline values.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_core_value_codecs.py

from __future__ import annotations

import json
from typing import Any, Callable

from ea_node_editor.runtime_contracts import DataTree

_MAX_INTERNALIZED_PAYLOAD_BYTES = 1024 * 1024
_MAX_TREE_BRANCHES = 100_000
_MAX_TREE_ITEMS = 100_000
_MAX_TREE_PATH_LENGTH = 256
_MAX_TREE_INDEX = 2**31 - 1


class JsonFloatToken(str):
    """A JSON float literal kept distinct from JSON integer tokens."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _exact_dict(value: object, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("unsupported JSON object shape")
    return value


def decode_internalized_data_tree(
    *,
    payload: object,
    path_type: str,
    decode_leaf: Callable[[object], object],
    error_message: str,
) -> DataTree:
    """Decode a strict single-item typed-value DataTree envelope."""

    try:
        if (
            type(payload) is not bytes
            or len(payload) > _MAX_INTERNALIZED_PAYLOAD_BYTES
            or type(path_type) is not str
            or not path_type
        ):
            raise TypeError("payload must be bytes")
        document = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
            parse_float=JsonFloatToken,
        )
        root = _exact_dict(document, {"Branches", "Paths"})
        branches = root["Branches"]
        paths = root["Paths"]
        if (
            type(branches) is not list
            or type(paths) is not list
            or not branches
            or len(branches) != len(paths)
        ):
            raise ValueError("unaligned or empty tree")
        if len(branches) > _MAX_TREE_BRANCHES:
            raise ValueError("too many tree branches")

        decoded_branches: list[tuple[tuple[int, ...], tuple[object]]] = []
        item_count = 0
        for branch, path_value in zip(branches, paths, strict=True):
            if type(branch) is not list:
                raise ValueError("branch must be a list")
            item_count += len(branch)
            if item_count > _MAX_TREE_ITEMS:
                raise ValueError("too many tree items")
            if len(branch) != 1:
                raise ValueError("branch must contain exactly one item")
            path = _exact_dict(path_value, {"$type", "Indices"})
            if type(path["$type"]) is not str or path["$type"] != path_type:
                raise ValueError("unsupported path type")
            indices = path["Indices"]
            if (
                type(indices) is not list
                or not indices
                or len(indices) > _MAX_TREE_PATH_LENGTH
                or any(
                    type(index) is not int or not 0 <= index <= _MAX_TREE_INDEX
                    for index in indices
                )
            ):
                raise ValueError("invalid path indices")
            decoded_branches.append((tuple(indices), (decode_leaf(branch[0]),)))
        return DataTree(decoded_branches)
    except Exception:
        raise ValueError(error_message) from None


__all__ = ["JsonFloatToken", "decode_internalized_data_tree"]
