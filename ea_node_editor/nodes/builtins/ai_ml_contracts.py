# Purpose: Declare strict COREX AI and machine-learning contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_ai_ml_contracts.py

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Callable
from urllib.parse import urlsplit

from ea_node_editor.common.payload_tools import copy_json_mapping
from ea_node_editor.nodes.builtins.spatial_values import (
    FIELD_VECTOR_DATA_TYPE_ID,
    COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES,
)
from ea_node_editor.nodes.core_data_types import (
    CORE_DATA_TYPES,
    GRAPH_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import DataTypeSpec, TypedInlineValue

COREX_AI_ML_CONTRACTS_OWNER_ID = "corex.ai_ml_contracts"
COREX_AI_ML_CONTRACTS_OWNER_VERSION = "1"

OPENAI_CLIENT_DATA_TYPE_ID = "COREX.AI.IOpenAIClient"
MULTI_AGENT_TOOL_DATA_TYPE_ID = "COREX.DataTypes.MultiAgentSystem.ITool"
WEB_CONTENT_DATA_TYPE_ID = "COREX.DataTypes.Web.IWebContent"
BASE_PROBABILITY_DATA_TYPE_ID = "COREX.ML.IBaseProbability"
DATASET_DATA_TYPE_ID = "COREX.ML.IDataset"
ML_MODEL_DATA_TYPE_ID = "COREX.ML.IMLModel"
VECTOR_RECORD_DATA_TYPE_ID = "AdvancedAiModule.VectorDb.DataTypes.VectorRecord"
REMOTE_MCP_SERVER_DATA_TYPE_ID = "COREX.DataTypes.Web.RemoteMcpServer"
OPENAI_MCP_CONNECTOR_DATA_TYPE_ID = "COREX.DataTypes.AI.OpenAI.OpenAIMcpConnector"
WEB_CLIENT_SETTINGS_DATA_TYPE_ID = "COREX.DataTypes.Web.WebClientSettings"
VECTOR_DB_CONNECTION_DATA_TYPE_ID = (
    "AdvancedAiModule.VectorDb.DataTypes.VectorDbConnection"
)
VECTOR_COLLECTION_DATA_TYPE_ID = "AdvancedAiModule.VectorDb.DataTypes.VectorCollection"

SQLITE_VECTOR_DATABASE_NODE_TYPE_ID = "ai.sqlite_vector_database"
CREATE_VECTOR_COLLECTION_NODE_TYPE_ID = "ai.create_vector_collection"
INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID = "ai.inspect_vector_collection"

_GRAPH_PARENT = (GRAPH_DATA_TYPE_ID,)
_HANDLE_CARRIER = frozenset({"handle"})
_VECTOR_RECORD_KEYS = frozenset(
    {
        "vector",
        "id",
        "source_reference",
        "name",
        "path",
        "category",
        "vector_space_tag",
        "additional_metadata",
    }
)
_VECTOR_RECORD_TEXT_KEYS = (
    "id",
    "source_reference",
    "name",
    "path",
    "category",
    "vector_space_tag",
)
_REMOTE_MCP_SERVER_KEYS = frozenset({"is_approved", "name", "tool_names", "url"})
_OPENAI_MCP_CONNECTOR_KEYS = frozenset(
    {"is_approved", "server_label", "tool_names", "mcp_tool_connector_id"}
)
_OPENAI_MCP_CONNECTOR_LABEL_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
_OPENAI_MCP_CONNECTOR_IDS = (
    "connector_dropbox",
    "connector_gmail",
    "connector_googlecalendar",
    "connector_googledrive",
    "connector_microsoftteams",
    "connector_outlookcalendar",
    "connector_outlookemail",
    "connector_sharepoint",
)
_WEB_CLIENT_SETTINGS_KEYS = frozenset(
    {
        "base_url",
        "retry_count",
        "timeout_seconds",
        "headers",
        "allow_insecure",
        "uses_windows_authentication",
    }
)
_FIELD_VECTOR_SPEC = next(
    spec
    for spec in COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES
    if spec.type_id == FIELD_VECTOR_DATA_TYPE_ID
)
_GRAPH_DICTIONARY_SPEC = next(
    spec for spec in CORE_DATA_TYPES if spec.type_id == GRAPH_DICTIONARY_DATA_TYPE_ID
)
_VECTOR_DB_CONNECTION_KEYS = frozenset({"provider", "file_path"})
_VECTOR_COLLECTION_KEYS = frozenset({"connection", "collection_name"})
_COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
_URI_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_RESERVED_BASENAME_PATTERN = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$",
    re.IGNORECASE,
)
_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
_SQLITE_PATH_ERROR = (
    "file_path must match the approved absolute local SQLite path syntax"
)
_SQLITE_OPERATION_ERROR = "SQLite vector database operation failed"
_SQLITE_SCHEMA_ERROR = "SQLite file is not an approved COREX vector database"
_COLLECTION_NAME_ERROR = "collection_name must match [A-Za-z][A-Za-z0-9_-]{0,63}"
_VECTOR_DIMENSION_ERROR = "vector_dimension must be an integer from 1 to 65536"
_DISTANCE_METRIC_ERROR = 'distance_metric must be exactly "Cosine" or "Euclidean"'
_METADATA_ERROR = "additional_metadata must be a bounded non-sensitive GraphDictionary"
_APPLICATION_ID = 1_129_271_896
_USER_VERSION = 1
_COLLECTION_TABLE_SQL = """CREATE TABLE corex_vector_collections (
    collection_name TEXT PRIMARY KEY NOT NULL,
    vector_dimension INTEGER NOT NULL
        CHECK(typeof(vector_dimension) = 'integer'
              AND vector_dimension BETWEEN 1 AND 65536),
    distance_metric INTEGER NOT NULL
        CHECK(typeof(distance_metric) = 'integer'
              AND distance_metric IN (0, 1)),
    metadata_json TEXT NOT NULL
)"""
_APPROVED_SCHEMA_ROWS = (
    (
        "table",
        "corex_vector_collections",
        "corex_vector_collections",
        _COLLECTION_TABLE_SQL,
    ),
)
_APPROVED_TABLE_INFO = (
    (0, "collection_name", "TEXT", 1, None, 1),
    (1, "vector_dimension", "INTEGER", 1, None, 0),
    (2, "distance_metric", "INTEGER", 1, None, 0),
    (3, "metadata_json", "TEXT", 1, None, 0),
)
_DISTANCE_METRIC_CODES = {"Cosine": 0, "Euclidean": 1}
_DISTANCE_METRIC_LABELS = {0: "Cosine", 1: "Euclidean"}


def _has_exact_keys(value: object, keys: frozenset[str]) -> bool:
    return (
        type(value) is dict
        and len(value) == len(keys)
        and all(type(key) is str for key in value)
        and frozenset(value) == keys
    )


def _validate_sqlite_file_path(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 32_768
        or value != value.strip()
        or not all(character.isprintable() for character in value)
    ):
        raise ValueError(_SQLITE_PATH_ERROR)

    drive_path = _WINDOWS_DRIVE_PATH_PATTERN.match(value) is not None
    if not drive_path and _URI_SCHEME_PATTERN.match(value) is not None:
        raise ValueError(_SQLITE_PATH_ERROR)

    if os.name == "nt":
        if not drive_path:
            raise ValueError(_SQLITE_PATH_ERROR)
        components = re.split(r"[\\/]", value[3:])
        if (
            not components
            or any(
                not component or component in {".", ".."} for component in components
            )
            or any(
                any(character in '<>"|?*:' for character in component)
                or component.endswith((".", " "))
                or _WINDOWS_RESERVED_BASENAME_PATTERN.fullmatch(
                    component.split(".", 1)[0]
                )
                is not None
                for component in components
            )
        ):
            raise ValueError(_SQLITE_PATH_ERROR)
    elif os.name == "posix":
        if (
            drive_path
            or not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
        ):
            raise ValueError(_SQLITE_PATH_ERROR)
        components = value[1:].split("/")
        if not components or any(
            not component or component in {".", ".."} for component in components
        ):
            raise ValueError(_SQLITE_PATH_ERROR)
    else:
        raise ValueError(_SQLITE_PATH_ERROR)

    if not value.lower().endswith(_SQLITE_SUFFIXES) or os.path.isdir(value):
        raise ValueError(_SQLITE_PATH_ERROR)
    return value


def _is_vector_db_connection_payload(value: object) -> bool:
    if not _has_exact_keys(value, _VECTOR_DB_CONNECTION_KEYS):
        return False
    try:
        return (
            type(value["provider"]) is str
            and value["provider"] == "sqlite"
            and _validate_sqlite_file_path(value["file_path"]) == value["file_path"]
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _validate_collection_name(value: object) -> str:
    if type(value) is not str or _COLLECTION_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(_COLLECTION_NAME_ERROR)
    return value


def _is_vector_collection_payload(value: object) -> bool:
    if not _has_exact_keys(value, _VECTOR_COLLECTION_KEYS):
        return False
    try:
        return (
            _is_vector_db_connection_payload(value["connection"])
            and _validate_collection_name(value["collection_name"])
            == value["collection_name"]
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _validate_vector_dimension(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 65_536:
        raise ValueError(_VECTOR_DIMENSION_ERROR)
    return value


def _validate_distance_metric(value: object) -> str:
    if type(value) is not str or value not in _DISTANCE_METRIC_CODES:
        raise ValueError(_DISTANCE_METRIC_ERROR)
    return value


def _copy_additional_metadata(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(_METADATA_ERROR)
    try:
        return copy_json_mapping(
            value,
            field_name="additional_metadata",
            max_encoded_bytes=65_536,
            reject_sensitive_metadata=True,
        )
    except (TypeError, ValueError, OverflowError, UnicodeError):
        raise ValueError(_METADATA_ERROR) from None


def _typed_payload(
    value: object,
    data_type_id: str,
    validator: Callable[[object], bool],
    error: str,
) -> dict[str, object]:
    if (
        type(value) is not TypedInlineValue
        or type(value.data_type_id) is not str
        or value.data_type_id != data_type_id
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or not validator(value.payload)
    ):
        raise ValueError(error)
    return value.payload


def _connection_payload(value: object) -> dict[str, object]:
    return _typed_payload(
        value,
        VECTOR_DB_CONNECTION_DATA_TYPE_ID,
        _is_vector_db_connection_payload,
        "Vector database input is invalid",
    )


def _collection_payload(value: object) -> dict[str, object]:
    return _typed_payload(
        value,
        VECTOR_COLLECTION_DATA_TYPE_ID,
        _is_vector_collection_payload,
        "Vector collection input is invalid",
    )


def _schema_state(connection: sqlite3.Connection) -> str:
    application_id_row = connection.execute("PRAGMA application_id").fetchone()
    user_version_row = connection.execute("PRAGMA user_version").fetchone()
    schema_rows = tuple(
        connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE substr(name, 1, 7) != 'sqlite_' ORDER BY type, name"
        ).fetchall()
    )
    if application_id_row == (0,) and user_version_row == (0,) and schema_rows == ():
        return "fresh"
    if (
        application_id_row == (_APPLICATION_ID,)
        and user_version_row == (_USER_VERSION,)
        and schema_rows == _APPROVED_SCHEMA_ROWS
        and tuple(
            connection.execute("PRAGMA table_info(corex_vector_collections)").fetchall()
        )
        == _APPROVED_TABLE_INFO
    ):
        return "approved"
    return "rejected"


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.rollback()
    except (sqlite3.Error, OSError):
        raise RuntimeError(_SQLITE_OPERATION_ERROR) from None


def _close(connection: sqlite3.Connection) -> None:
    try:
        connection.close()
    except (sqlite3.Error, OSError):
        raise RuntimeError(_SQLITE_OPERATION_ERROR) from None


def _is_vector_record_payload(value: object) -> bool:
    try:
        return (
            type(value) is dict
            and len(value) == len(_VECTOR_RECORD_KEYS)
            and all(type(key) is str and key in _VECTOR_RECORD_KEYS for key in value)
            and all(type(value[key]) is str for key in _VECTOR_RECORD_TEXT_KEYS)
            and _FIELD_VECTOR_SPEC.validate_item(value["vector"])
            and _GRAPH_DICTIONARY_SPEC.validate_item(value["additional_metadata"])
        )
    except (KeyError, TypeError, OverflowError):
        return False


def _is_http_url(value: object) -> bool:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 32_768
        or value != value.strip()
        or not all(character.isprintable() for character in value)
        or any(character.isspace() for character in value)
        or "\\" in value
        or "#" in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.netloc.endswith(":")
        ):
            return False
        port = parsed.port
        return (port is None or 0 <= port <= 65_535) and parsed.fragment == ""
    except (TypeError, ValueError, UnicodeError, OverflowError, OSError):
        return False


def _is_remote_mcp_server_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_REMOTE_MCP_SERVER_KEYS):
        return False
    keys = tuple(value)
    if not all(type(key) is str for key in keys):
        return False
    if frozenset(keys) != _REMOTE_MCP_SERVER_KEYS:
        return False
    try:
        is_approved = value["is_approved"]
        name = value["name"]
        tool_names = value["tool_names"]
        url = value["url"]
        if type(is_approved) is not bool or is_approved is not True:
            return False
        if (
            type(name) is not str
            or not 1 <= len(name) <= 256
            or not any(not character.isspace() for character in name)
            or not all(character.isprintable() for character in name)
        ):
            return False
        if tool_names is not None:
            if type(tool_names) is not list or len(tool_names) > 256:
                return False
            if not all(type(tool_name) is str for tool_name in tool_names):
                return False
            if not all(
                len(tool_name) <= 256
                and all(character.isprintable() for character in tool_name)
                for tool_name in tool_names
            ):
                return False
        return _is_http_url(url)
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, OSError):
        return False


def _is_openai_mcp_connector_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_OPENAI_MCP_CONNECTOR_KEYS):
        return False
    keys = tuple(value)
    if not all(type(key) is str for key in keys):
        return False
    if frozenset(keys) != _OPENAI_MCP_CONNECTOR_KEYS:
        return False
    try:
        is_approved = value["is_approved"]
        server_label = value["server_label"]
        tool_names = value["tool_names"]
        mcp_tool_connector_id = value["mcp_tool_connector_id"]
        if type(is_approved) is not bool or is_approved is not True:
            return False
        if (
            type(server_label) is not str
            or not 1 <= len(server_label) <= 256
            or _OPENAI_MCP_CONNECTOR_LABEL_PATTERN.fullmatch(server_label) is None
        ):
            return False
        if tool_names is not None:
            if type(tool_names) is not list or len(tool_names) > 256:
                return False
            if not all(type(tool_name) is str for tool_name in tool_names):
                return False
            if not all(
                len(tool_name) <= 256
                and all(character.isprintable() for character in tool_name)
                for tool_name in tool_names
            ):
                return False
        return (
            type(mcp_tool_connector_id) is str
            and mcp_tool_connector_id in _OPENAI_MCP_CONNECTOR_IDS
        )
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, OSError):
        return False


def _is_web_client_settings_payload(value: object) -> bool:
    if type(value) is not dict or len(value) != len(_WEB_CLIENT_SETTINGS_KEYS):
        return False
    keys = tuple(value)
    if not all(type(key) is str for key in keys):
        return False
    if frozenset(keys) != _WEB_CLIENT_SETTINGS_KEYS:
        return False
    try:
        base_url = value["base_url"]
        retry_count = value["retry_count"]
        timeout_seconds = value["timeout_seconds"]
        headers = value["headers"]
        allow_insecure = value["allow_insecure"]
        uses_windows_authentication = value["uses_windows_authentication"]
        return (
            (base_url is None or _is_http_url(base_url))
            and type(retry_count) is int
            and 1 <= retry_count <= 2_147_483_647
            and type(timeout_seconds) is int
            and 1 <= timeout_seconds <= 2_147_483_647
            and type(headers) is dict
            and len(headers) == 0
            and type(allow_insecure) is bool
            and allow_insecure is False
            and type(uses_windows_authentication) is bool
            and uses_windows_authentication is False
        )
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError, OSError):
        return False


COREX_AI_ML_DATA_TYPES = (
    DataTypeSpec(
        OPENAI_CLIENT_DATA_TYPE_ID,
        "OpenAI Client",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="secret",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        MULTI_AGENT_TOOL_DATA_TYPE_ID,
        "Tool",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        WEB_CONTENT_DATA_TYPE_ID,
        "Web Content",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        BASE_PROBABILITY_DATA_TYPE_ID,
        "Base Probability",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        DATASET_DATA_TYPE_ID,
        "Dataset",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        ML_MODEL_DATA_TYPE_ID,
        "ML Model",
        "runtime_ref",
        lambda _value: False,
        parents=_GRAPH_PARENT,
        abstract=True,
        carriers=_HANDLE_CARRIER,
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_DATA_TYPES,
)

COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES = (
    *COREX_AI_ML_DATA_TYPES,
    DataTypeSpec(
        VECTOR_RECORD_DATA_TYPE_ID,
        "Vector Record",
        "container",
        _is_vector_record_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_VECTOR_RECORD_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES,
)

COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES = (
    *COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        REMOTE_MCP_SERVER_DATA_TYPE_ID,
        "Remote MCP Server",
        "container",
        _is_remote_mcp_server_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES,
)

COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES = (
    *COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        "OpenAI MCP Connector",
        "container",
        _is_openai_mcp_connector_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES,
)

COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES = (
    *COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
        "Web Client Settings",
        "container",
        _is_web_client_settings_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES,
)

COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES = (
    *COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES,
    DataTypeSpec(
        VECTOR_DB_CONNECTION_DATA_TYPE_ID,
        "Vector DB Connection",
        "container",
        _is_vector_db_connection_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
    DataTypeSpec(
        VECTOR_COLLECTION_DATA_TYPE_ID,
        "Vector Collection",
        "container",
        _is_vector_collection_payload,
        parents=_GRAPH_PARENT,
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="sensitive",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES,
)


def execute_sqlite_vector_database(ctx: ExecutionContext) -> NodeResult:
    file_path = _validate_sqlite_file_path(
        ctx.inputs.get("file_path", ctx.properties.get("file_path", ""))
    )
    connection: sqlite3.Connection | None = None
    transaction_started = False
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        connection = sqlite3.connect(file_path, timeout=5.0, uri=False)
        try:
            connection.execute("BEGIN IMMEDIATE")
            transaction_started = True
            state = _schema_state(connection)
            if state == "fresh":
                connection.execute(_COLLECTION_TABLE_SQL)
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {_USER_VERSION}")
                if _schema_state(connection) != "approved":
                    raise ValueError(_SQLITE_SCHEMA_ERROR)
            elif state != "approved":
                raise ValueError(_SQLITE_SCHEMA_ERROR)
            connection.commit()
            transaction_started = False
        finally:
            try:
                if transaction_started:
                    _rollback(connection)
            finally:
                _close(connection)
    except (sqlite3.Error, OSError):
        raise RuntimeError(_SQLITE_OPERATION_ERROR) from None
    return NodeResult(
        outputs={
            "vector_database": TypedInlineValue(
                VECTOR_DB_CONNECTION_DATA_TYPE_ID,
                1,
                {"provider": "sqlite", "file_path": file_path},
            )
        }
    )


def execute_create_vector_collection(ctx: ExecutionContext) -> NodeResult:
    connection_payload = _connection_payload(ctx.inputs.get("vector_database"))
    file_path = connection_payload["file_path"]
    collection_name = _validate_collection_name(
        ctx.inputs.get(
            "collection_name",
            ctx.properties.get("collection_name", ""),
        )
    )
    vector_dimension = _validate_vector_dimension(
        ctx.inputs.get(
            "vector_dimension",
            ctx.properties.get("vector_dimension", 1),
        )
    )
    distance_metric = _validate_distance_metric(
        ctx.inputs.get(
            "distance_metric",
            ctx.properties.get("distance_metric", "Cosine"),
        )
    )
    metadata = _copy_additional_metadata(
        ctx.inputs.get(
            "additional_metadata",
            ctx.properties.get("additional_metadata", {}),
        )
    )
    metadata_json = json.dumps(
        metadata,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    metric_code = _DISTANCE_METRIC_CODES[distance_metric]

    connection: sqlite3.Connection | None = None
    transaction_started = False
    try:
        connection = sqlite3.connect(file_path, timeout=5.0, uri=False)
        try:
            connection.execute("BEGIN IMMEDIATE")
            transaction_started = True
            if _schema_state(connection) != "approved":
                raise ValueError(_SQLITE_SCHEMA_ERROR)
            row = connection.execute(
                "SELECT vector_dimension, distance_metric, metadata_json "
                "FROM corex_vector_collections WHERE collection_name = ?",
                (collection_name,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO corex_vector_collections "
                    "(collection_name, vector_dimension, distance_metric, metadata_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        collection_name,
                        vector_dimension,
                        metric_code,
                        metadata_json,
                    ),
                )
            elif (
                type(row) is not tuple
                or len(row) != 3
                or type(row[0]) is not int
                or type(row[1]) is not int
                or type(row[2]) is not str
            ):
                raise RuntimeError(_SQLITE_OPERATION_ERROR)
            elif row != (vector_dimension, metric_code, metadata_json):
                raise ValueError(
                    "vector collection already exists with different metadata"
                )
            connection.commit()
            transaction_started = False
        finally:
            try:
                if transaction_started:
                    _rollback(connection)
            finally:
                _close(connection)
    except (sqlite3.Error, OSError):
        raise RuntimeError(_SQLITE_OPERATION_ERROR) from None

    return NodeResult(
        outputs={
            "vector_collection": TypedInlineValue(
                VECTOR_COLLECTION_DATA_TYPE_ID,
                1,
                {
                    "connection": {
                        "provider": "sqlite",
                        "file_path": file_path,
                    },
                    "collection_name": collection_name,
                },
            )
        }
    )


def execute_inspect_vector_collection(ctx: ExecutionContext) -> NodeResult:
    collection_payload = _collection_payload(ctx.inputs.get("vector_collection"))
    raw_connection = collection_payload["connection"]
    file_path = raw_connection["file_path"]
    collection_name = collection_payload["collection_name"]

    connection: sqlite3.Connection | None = None
    transaction_started = False
    try:
        connection = sqlite3.connect(file_path, timeout=5.0, uri=False)
        try:
            connection.execute("BEGIN")
            transaction_started = True
            if _schema_state(connection) != "approved":
                raise ValueError(_SQLITE_SCHEMA_ERROR)
            row = connection.execute(
                "SELECT collection_name, vector_dimension, distance_metric, "
                "metadata_json FROM corex_vector_collections "
                "WHERE collection_name = ?",
                (collection_name,),
            ).fetchone()
            if row is None:
                raise ValueError("vector collection was not found")
            try:
                if (
                    type(row) is not tuple
                    or len(row) != 4
                    or type(row[0]) is not str
                    or row[0] != collection_name
                    or type(row[1]) is not int
                    or not 1 <= row[1] <= 65_536
                    or type(row[2]) is not int
                    or row[2] not in _DISTANCE_METRIC_LABELS
                    or type(row[3]) is not str
                ):
                    raise ValueError
                metadata = _copy_additional_metadata(json.loads(row[3]))
                if (
                    json.dumps(
                        metadata,
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    != row[3]
                ):
                    raise ValueError
            except (TypeError, ValueError, OverflowError, UnicodeError):
                raise RuntimeError(_SQLITE_OPERATION_ERROR) from None
            connection.commit()
            transaction_started = False
        finally:
            try:
                if transaction_started:
                    _rollback(connection)
            finally:
                _close(connection)
    except (sqlite3.Error, OSError):
        raise RuntimeError(_SQLITE_OPERATION_ERROR) from None

    return NodeResult(
        outputs={
            "name": row[0],
            "record_count": 0,
            "vector_dimension": row[1],
            "distance_metric": _DISTANCE_METRIC_LABELS[row[2]],
            "metadata": metadata,
        }
    )


__all__ = [
    "BASE_PROBABILITY_DATA_TYPE_ID",
    "DATASET_DATA_TYPE_ID",
    "ML_MODEL_DATA_TYPE_ID",
    "MULTI_AGENT_TOOL_DATA_TYPE_ID",
    "OPENAI_CLIENT_DATA_TYPE_ID",
    "OPENAI_MCP_CONNECTOR_DATA_TYPE_ID",
    "REMOTE_MCP_SERVER_DATA_TYPE_ID",
    "COREX_AI_ML_CONTRACT_MANIFEST",
    "COREX_AI_ML_CONTRACTS_OWNER_ID",
    "COREX_AI_ML_CONTRACTS_OWNER_VERSION",
    "COREX_AI_ML_DATA_TYPES",
    "COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES",
    "COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES",
    "COREX_AI_ML_VECTOR_RECORD_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES",
    "COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES",
    "COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_CONTRACT_MANIFEST",
    "COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES",
    "CREATE_VECTOR_COLLECTION_NODE_TYPE_ID",
    "INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID",
    "SQLITE_VECTOR_DATABASE_NODE_TYPE_ID",
    "VECTOR_COLLECTION_DATA_TYPE_ID",
    "VECTOR_DB_CONNECTION_DATA_TYPE_ID",
    "VECTOR_RECORD_DATA_TYPE_ID",
    "WEB_CLIENT_SETTINGS_DATA_TYPE_ID",
    "WEB_CONTENT_DATA_TYPE_ID",
    "execute_create_vector_collection",
    "execute_inspect_vector_collection",
    "execute_sqlite_vector_database",
]
