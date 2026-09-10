# Purpose: Declare strict COREX mesh interface contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_mesh_contracts.py

from __future__ import annotations

import math

from ea_node_editor.nodes.builtins.geometry_contracts import (
    MEASURABLE_DATA_TYPE_ID,
)
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest,
)
from ea_node_editor.runtime_contracts import DataTypeSpec, TypedInlineValue

COREX_MESH_CONTRACTS_OWNER_ID = "corex.mesh_contracts"
COREX_MESH_CONTRACTS_OWNER_VERSION = "1"

ISO_MESH_DATA_TYPE_ID = "COREX.Mesh.IIsoMesh"
THICK_MESH_DATA_TYPE_ID = "COREX.Mesh.IThickMesh"
MESH_FACE_DATA_TYPE_ID = "COREX.DataTypes.MeshFace"
MESH_PARAMETER_DATA_TYPE_ID = "COREX.DataTypes.MeshParameter"

DECONSTRUCT_MESH_FACE_TYPE_ID = "mesh.deconstruct_mesh_face"

_HANDLE_CARRIER = frozenset({"handle"})


def _is_mesh_face_payload(value: object) -> bool:
    return (
        type(value) is dict
        and set(value) == {"a", "b", "c", "d"}
        and all(type(item) is int for item in value.values())
        and all(0 <= value[key] <= 2_147_483_647 for key in ("a", "b", "c"))
        and -1 <= value["d"] <= 2_147_483_647
    )


def _is_mesh_parameter_payload(value: object) -> bool:
    if type(value) is not dict:
        return False
    if any(type(key) is not str for key in value):
        return False
    if set(value) != {"face_index", "barycentric"}:
        return False

    face_index = value["face_index"]
    weights = value["barycentric"]
    if type(face_index) is not int or not 0 <= face_index <= 2_147_483_647:
        return False
    if type(weights) is not list or len(weights) != 4:
        return False
    if any(type(weight) not in (int, float) for weight in weights):
        return False
    if any(not 0 <= weight <= 1 for weight in weights):
        return False
    if any(type(weight) is float and not math.isfinite(weight) for weight in weights):
        return False
    return math.isclose(
        math.fsum(weights),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ) and any(
        math.isclose(weight, 0.0, rel_tol=0.0, abs_tol=1e-9) for weight in weights
    )












COREX_MESH_DATA_TYPES = (
    DataTypeSpec(
        ISO_MESH_DATA_TYPE_ID,
        "Iso Mesh",
        "engineering",
        lambda _value: False,
        parents=(MEASURABLE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        THICK_MESH_DATA_TYPE_ID,
        "Thick Mesh",
        "engineering",
        lambda _value: False,
        parents=(MEASURABLE_DATA_TYPE_ID,),
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_MESH_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_MESH_DATA_TYPES,
)

COREX_MESH_FACE_CANDIDATE_DATA_TYPES = (
    *COREX_MESH_DATA_TYPES,
    DataTypeSpec(
        MESH_FACE_DATA_TYPE_ID,
        "Mesh Face",
        "engineering",
        _is_mesh_face_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_MESH_FACE_CANDIDATE_DATA_TYPES,
)

COREX_MESH_PARAMETER_CANDIDATE_DATA_TYPES = (
    *COREX_MESH_FACE_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        MESH_PARAMETER_DATA_TYPE_ID,
        "Mesh Parameter",
        "engineering",
        _is_mesh_parameter_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)


def execute_deconstruct_mesh_face(ctx: ExecutionContext) -> NodeResult:
    value = ctx.inputs["face"]
    if (
        not isinstance(value, TypedInlineValue)
        or value.data_type_id != MESH_FACE_DATA_TYPE_ID
        or value.schema_version != 1
        or not _is_mesh_face_payload(value.payload)
    ):
        raise ValueError("Mesh Face input is invalid")
    payload = value.payload
    return NodeResult(
        outputs={
            "index_a": payload["a"],
            "index_b": payload["b"],
            "index_c": payload["c"],
            "index_d": payload["d"],
        }
    )


COREX_DECONSTRUCT_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_MESH_FACE_CANDIDATE_DATA_TYPES,
)

COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_MESH_PARAMETER_CANDIDATE_DATA_TYPES,
)

__all__ = [
    "DECONSTRUCT_MESH_FACE_TYPE_ID",
    "MESH_FACE_DATA_TYPE_ID",
    "MESH_PARAMETER_DATA_TYPE_ID",
    "COREX_DECONSTRUCT_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_MESH_CONTRACT_MANIFEST",
    "COREX_MESH_CONTRACTS_OWNER_ID",
    "COREX_MESH_CONTRACTS_OWNER_VERSION",
    "COREX_MESH_DATA_TYPES",
    "COREX_MESH_FACE_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_MESH_FACE_CANDIDATE_DATA_TYPES",
    "COREX_MESH_PARAMETER_CANDIDATE_DATA_TYPES",
    "COREX_MESH_PARAMETER_CANDIDATE_CONTRACT_MANIFEST",
    "ISO_MESH_DATA_TYPE_ID",
    "THICK_MESH_DATA_TYPE_ID",
    "execute_deconstruct_mesh_face",
]
