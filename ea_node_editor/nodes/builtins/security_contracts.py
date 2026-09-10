# Purpose: Declare strict COREX authentication and Windows identity contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_security_contracts.py

from __future__ import annotations

import getpass
import platform

from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec, RuntimeHandleRef

COREX_SECURITY_OWNER_ID = "corex.security_contracts"
COREX_SECURITY_OWNER_VERSION = "1"

AUTHENTICATION_DATA_TYPE_ID = "COREX.DataTypes.Web.IAuthentication"
WINDOWS_IDENTITY_DATA_TYPE_ID = "COREX.DataTypes.WindowsIdentity"
WINDOWS_IDENTITY_HANDLE_KIND = "corex.windows_identity"
WINDOWS_AUTHENTICATION_TYPE_ID = "security.windows_authentication"
WINDOWS_AUTHENTICATION_UNAVAILABLE_ERROR = "Windows authentication is unavailable."


def is_windows_identity_handle(value: object) -> bool:
    if type(value) is not RuntimeHandleRef:
        return False
    data_type_id = value.data_type_id
    schema_version = value.schema_version
    kind = value.kind
    metadata = value.metadata
    return (
        type(data_type_id) is str
        and data_type_id == WINDOWS_IDENTITY_DATA_TYPE_ID
        and type(schema_version) is int
        and schema_version == 1
        and type(kind) is str
        and kind == WINDOWS_IDENTITY_HANDLE_KIND
        and type(metadata) is dict
        and len(metadata) == 0
    )


_GRAPH_PARENT = (GRAPH_DATA_TYPE_ID,)

COREX_SECURITY_DATA_TYPES = (
    DataTypeSpec(
        AUTHENTICATION_DATA_TYPE_ID,
        "Authentication",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="secret",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        WINDOWS_IDENTITY_DATA_TYPE_ID,
        "Windows Identity",
        "runtime_ref",
        is_windows_identity_handle,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="secret",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_SECURITY_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_SECURITY_DATA_TYPES,
)


def _current_windows_user() -> str:
    try:
        if platform.system() != "Windows":
            raise RuntimeError
        candidate = getpass.getuser()
        if type(candidate) is not str:
            raise TypeError
        normalized = candidate.strip()
        if not normalized or len(normalized) > 256 or not normalized.isprintable():
            raise ValueError
    except Exception:
        raise RuntimeError(WINDOWS_AUTHENTICATION_UNAVAILABLE_ERROR) from None
    return normalized


def execute_windows_authentication(ctx: ExecutionContext) -> dict[str, object]:
    current_user = _current_windows_user()
    authentication = ctx.register_handle(
        object(),
        data_type_id=WINDOWS_IDENTITY_DATA_TYPE_ID,
        kind=WINDOWS_IDENTITY_HANDLE_KIND,
        metadata={},
    )
    return {"authentication": authentication, "current_user": current_user}


__all__ = [
    "AUTHENTICATION_DATA_TYPE_ID",
    "COREX_SECURITY_CONTRACT_MANIFEST",
    "COREX_SECURITY_DATA_TYPES",
    "COREX_SECURITY_OWNER_ID",
    "COREX_SECURITY_OWNER_VERSION",
    "WINDOWS_AUTHENTICATION_TYPE_ID",
    "WINDOWS_AUTHENTICATION_UNAVAILABLE_ERROR",
    "WINDOWS_IDENTITY_DATA_TYPE_ID",
    "WINDOWS_IDENTITY_HANDLE_KIND",
    "execute_windows_authentication",
    "is_windows_identity_handle",
]
