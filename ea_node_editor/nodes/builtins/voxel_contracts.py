# Purpose: Declare strict COREX voxel interface contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_voxel_contracts.py

from __future__ import annotations

from ea_node_editor.nodes.builtins.geometry_contracts import (
    MEASURABLE_DATA_TYPE_ID,
    SPATIAL_OBJECT_DATA_TYPE_ID,
)
from ea_node_editor.nodes.core_data_types import CLIPPABLE_GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec

COREX_VOXEL_CONTRACTS_OWNER_ID = "corex.voxel_contracts"
COREX_VOXEL_CONTRACTS_OWNER_VERSION = "1"

VOXEL_MAP_DATA_TYPE_ID = "COREX.Voxel.IVoxelMap"
VOXEL_SKELETON_DATA_TYPE_ID = "COREX.Voxel.IVoxelSkeleton"

_HANDLE_CARRIER = frozenset({"handle"})

COREX_VOXEL_DATA_TYPES = (
    DataTypeSpec(
        VOXEL_MAP_DATA_TYPE_ID,
        "Voxel Map",
        "engineering",
        lambda _value: False,
        parents=(
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
            CLIPPABLE_GRAPH_DATA_TYPE_ID,
        ),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        VOXEL_SKELETON_DATA_TYPE_ID,
        "Voxel Skeleton",
        "engineering",
        lambda _value: False,
        parents=(
            SPATIAL_OBJECT_DATA_TYPE_ID,
            MEASURABLE_DATA_TYPE_ID,
        ),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_VOXEL_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_VOXEL_DATA_TYPES,
)

__all__ = [
    "COREX_VOXEL_CONTRACT_MANIFEST",
    "COREX_VOXEL_CONTRACTS_OWNER_ID",
    "COREX_VOXEL_CONTRACTS_OWNER_VERSION",
    "COREX_VOXEL_DATA_TYPES",
    "VOXEL_MAP_DATA_TYPE_ID",
    "VOXEL_SKELETON_DATA_TYPE_ID",
]
