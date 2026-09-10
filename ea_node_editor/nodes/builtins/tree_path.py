# Purpose: Declare the abstract COREX tree-path contract and its COREX carrier.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_tree_path_types.py

from __future__ import annotations

from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec, TypedInlineValue

COREX_TREE_PATH_OWNER_ID = "corex.tree_path"
COREX_TREE_PATH_OWNER_VERSION = "1"

COREX_PATH_DATA_TYPE_ID = "COREX.DataTree.Path"
TREE_PATH_DATA_TYPE_ID = "COREX.DataTree.Path"

_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def is_tree_path_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != 1:
        return False
    key = next(iter(value), None)
    if type(key) is not str or key != "indices":
        return False
    indices = value[key]
    return type(indices) is list and all(
        type(index) is int and _INT32_MIN <= index <= _INT32_MAX for index in indices
    )


def make_tree_path_value(indices: object) -> TypedInlineValue:
    payload = {"indices": indices}
    if not is_tree_path_payload(payload):
        raise ValueError("tree path indices must be exact signed Int32 values")
    return TypedInlineValue(TREE_PATH_DATA_TYPE_ID, 1, payload)


def tree_path_indices(value: object) -> list[int]:
    if (
        type(value) is not TypedInlineValue
        or value.data_type_id != TREE_PATH_DATA_TYPE_ID
        or value.schema_version != 1
        or not is_tree_path_payload(value.payload)
    ):
        raise ValueError("tree path value is invalid")
    return list(value.payload["indices"])


COREX_TREE_PATH_DATA_TYPES = (
    DataTypeSpec(
        TREE_PATH_DATA_TYPE_ID,
        "Tree Path",
        "container",
        is_tree_path_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
    ),
)

COREX_TREE_PATH_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_TREE_PATH_DATA_TYPES,
)

__all__ = [
    "COREX_PATH_DATA_TYPE_ID",
    "COREX_TREE_PATH_CONTRACT_MANIFEST",
    "COREX_TREE_PATH_DATA_TYPES",
    "COREX_TREE_PATH_OWNER_ID",
    "COREX_TREE_PATH_OWNER_VERSION",
    "TREE_PATH_DATA_TYPE_ID",
    "is_tree_path_payload",
    "make_tree_path_value",
    "tree_path_indices",
]
