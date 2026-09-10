from __future__ import annotations

from dataclasses import asdict
import json
import socket
import sqlite3
import urllib.request
from pathlib import Path

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins import ai_ml_contracts as ai_ml_module
from ea_node_editor.nodes.builtin_functions.ai_vector_database import (
    SOURCE as AI_VECTOR_DATABASE_SOURCE,
)
from ea_node_editor.nodes.builtins.ai_ml_contracts import (
    BASE_PROBABILITY_DATA_TYPE_ID,
    CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
    DATASET_DATA_TYPE_ID,
    INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
    ML_MODEL_DATA_TYPE_ID,
    MULTI_AGENT_TOOL_DATA_TYPE_ID,
    OPENAI_CLIENT_DATA_TYPE_ID,
    OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
    REMOTE_MCP_SERVER_DATA_TYPE_ID,
    COREX_AI_ML_CONTRACT_MANIFEST,
    COREX_AI_ML_CONTRACTS_OWNER_ID,
    COREX_AI_ML_CONTRACTS_OWNER_VERSION,
    COREX_AI_ML_DATA_TYPES,
    COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_CONTRACT_MANIFEST,
    COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES,
    COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_CONTRACT_MANIFEST,
    COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES,
    COREX_AI_ML_VECTOR_RECORD_CANDIDATE_CONTRACT_MANIFEST,
    COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES,
    COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST,
    COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES,
    COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_CONTRACT_MANIFEST,
    COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES,
    SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
    VECTOR_COLLECTION_DATA_TYPE_ID,
    VECTOR_DB_CONNECTION_DATA_TYPE_ID,
    VECTOR_RECORD_DATA_TYPE_ID,
    WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
    WEB_CONTENT_DATA_TYPE_ID,
    execute_create_vector_collection,
    execute_inspect_vector_collection,
    execute_sqlite_vector_database,
)
from ea_node_editor.nodes.builtins.spatial_values import (
    FIELD_VECTOR_DATA_TYPE_ID,
    COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES,
)
from ea_node_editor.nodes.core_data_types import (
    CORE_DATA_TYPES,
    GRAPH_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.node_specs import PropertySpec
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalogError,
    RuntimeHandleRef,
    TypedInlineValue,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

_EXPECTED_TYPE_IDS = (
    "COREX.AI.IOpenAIClient",
    "COREX.DataTypes.MultiAgentSystem.ITool",
    "COREX.DataTypes.Web.IWebContent",
    "COREX.ML.IBaseProbability",
    "COREX.ML.IDataset",
    "COREX.ML.IMLModel",
)
_EXPECTED_VECTOR_RECORD_TYPE_IDS = _EXPECTED_TYPE_IDS + (
    "AdvancedAiModule.VectorDb.DataTypes.VectorRecord",
)
_EXPECTED_REMOTE_MCP_SERVER_TYPE_IDS = _EXPECTED_VECTOR_RECORD_TYPE_IDS + (
    "COREX.DataTypes.Web.RemoteMcpServer",
)
_EXPECTED_OPENAI_MCP_CONNECTOR_TYPE_IDS = _EXPECTED_REMOTE_MCP_SERVER_TYPE_IDS + (
    "COREX.DataTypes.AI.OpenAI.OpenAIMcpConnector",
)
_EXPECTED_WEB_CLIENT_SETTINGS_TYPE_IDS = _EXPECTED_OPENAI_MCP_CONNECTOR_TYPE_IDS + (
    "COREX.DataTypes.Web.WebClientSettings",
)
_EXPECTED_VECTOR_DATABASE_TYPE_IDS = _EXPECTED_WEB_CLIENT_SETTINGS_TYPE_IDS + (
    "AdvancedAiModule.VectorDb.DataTypes.VectorDbConnection",
    "AdvancedAiModule.VectorDb.DataTypes.VectorCollection",
)


def _registry(
    manifest: PluginContractManifest = COREX_AI_ML_CONTRACT_MANIFEST,
) -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        manifest,
        (),
        owner_id=COREX_AI_ML_CONTRACTS_OWNER_ID,
        owner_version=COREX_AI_ML_CONTRACTS_OWNER_VERSION,
        source_label=ai_ml_module.__name__,
    )
    return registry


def _handle(type_id: str) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=type_id,
        schema_version=1,
        handle_id="abstract-ai-ml-test",
        kind="test.abstract_ai_ml",
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )


def test_failed_standalone_registration_rolls_back_all_six_types() -> None:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        PluginContractManifest(data_types=(COREX_AI_ML_DATA_TYPES[-1],)),
        (),
        owner_id="test.ai_ml_conflict",
        owner_version="1",
    )
    before = registry.data_types.snapshot()

    with pytest.raises(DataTypeCatalogError, match="duplicate data-type ID"):
        registry.register_plugin_bundle(
            COREX_AI_ML_CONTRACT_MANIFEST,
            (),
            owner_id=COREX_AI_ML_CONTRACTS_OWNER_ID,
            owner_version=COREX_AI_ML_CONTRACTS_OWNER_VERSION,
        )

    assert registry.data_types.snapshot() == before
    assert registry.plugin_contract_manifest(COREX_AI_ML_CONTRACTS_OWNER_ID) is None
    assert registry.all_descriptors() == []


def test_exact_abstract_handle_spec_facts_have_no_extra_behavior() -> None:
    expected = (
        (
            OPENAI_CLIENT_DATA_TYPE_ID,
            "OpenAI Client",
            "secret",
        ),
        (MULTI_AGENT_TOOL_DATA_TYPE_ID, "Tool", "normal"),
        (WEB_CONTENT_DATA_TYPE_ID, "Web Content", "normal"),
        (BASE_PROBABILITY_DATA_TYPE_ID, "Base Probability", "normal"),
        (DATASET_DATA_TYPE_ID, "Dataset", "normal"),
        (ML_MODEL_DATA_TYPE_ID, "ML Model", "normal"),
    )
    assert [
        (
            spec.type_id,
            spec.display_name,
            spec.sensitivity,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        )
        for spec in COREX_AI_ML_DATA_TYPES
    ] == [
        (
            type_id,
            display_name,
            sensitivity,
            "runtime_ref",
            (GRAPH_DATA_TYPE_ID,),
            True,
            frozenset({"handle"}),
            "never",
            1,
            "1",
            "",
            frozenset(),
            None,
        )
        for type_id, display_name, sensitivity in expected
    ]
    assert {
        spec.type_id for spec in COREX_AI_ML_DATA_TYPES if spec.sensitivity == "secret"
    } == {OPENAI_CLIENT_DATA_TYPE_ID}
    assert {
        spec.type_id for spec in COREX_AI_ML_DATA_TYPES if spec.sensitivity == "normal"
    } == set(_EXPECTED_TYPE_IDS[1:])


def test_all_abstract_validators_and_catalog_carriers_reject() -> None:
    catalog = _registry().data_types
    for spec in COREX_AI_ML_DATA_TYPES:
        handle = _handle(spec.type_id)
        assert spec.validate_item(handle) is False
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            catalog.validate_carrier(spec.type_id, handle)


def test_vector_record_payload_validation_is_strict_and_reuses_member_contracts() -> (
    None
):
    spec = COREX_AI_ML_VECTOR_RECORD_CANDIDATE_DATA_TYPES[-1]
    field_vector_spec = next(
        candidate
        for candidate in COREX_SPATIAL_VALUES_PLANAR_TREE_PATTERN_CANDIDATE_DATA_TYPES
        if candidate.type_id == FIELD_VECTOR_DATA_TYPE_ID
    )
    graph_dictionary_spec = next(
        candidate
        for candidate in CORE_DATA_TYPES
        if candidate.type_id == GRAPH_DICTIONARY_DATA_TYPE_ID
    )
    assert ai_ml_module._FIELD_VECTOR_SPEC is field_vector_spec
    assert ai_ml_module._GRAPH_DICTIONARY_SPEC is graph_dictionary_spec

    valid_payload = {
        "vector": [1, -2.5, 3],
        "id": "",
        "source_reference": "source",
        "name": "record",
        "path": "",
        "category": "sample",
        "vector_space_tag": "space",
        "additional_metadata": {
            "score": 0.5,
            "nested": [True, None, "value"],
        },
    }
    assert spec.validate_item(valid_payload) is True

    class DictSubclass(dict):
        pass

    assert spec.validate_item(DictSubclass(valid_payload)) is False
    assert spec.validate_item([]) is False
    assert (
        spec.validate_item(
            {key: value for key, value in valid_payload.items() if key != "id"}
        )
        is False
    )
    assert spec.validate_item({**valid_payload, "extra": None}) is False
    for key in (
        "id",
        "source_reference",
        "name",
        "path",
        "category",
        "vector_space_tag",
    ):
        assert spec.validate_item({**valid_payload, key: 1}) is False

    vector_values = (
        [0],
        "bad",
        [],
        [float("inf")],
        [float("nan")],
        [10**400],
        [True],
        TypedInlineValue(FIELD_VECTOR_DATA_TYPE_ID, 1, [1, 2, 3]),
    )
    for vector in vector_values:
        assert spec.validate_item({**valid_payload, "vector": vector}) is bool(
            field_vector_spec.validate_item(vector)
        )

    metadata_values = (
        {},
        {"bad": (1,)},
        {"bad": float("inf")},
        {"__ea_runtime_value__": "typed_inline"},
        {"nested": {"__ea_runtime_value__": "typed_inline"}},
        TypedInlineValue(GRAPH_DICTIONARY_DATA_TYPE_ID, 1, {}),
    )
    for metadata in metadata_values:
        assert spec.validate_item(
            {**valid_payload, "additional_metadata": metadata}
        ) is bool(graph_dictionary_spec.validate_item(metadata))


def test_vector_record_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = _registry(COREX_AI_ML_VECTOR_RECORD_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    payload = {
        "vector": [1, -2.5, 3],
        "id": "record-id",
        "source_reference": "source",
        "name": "record",
        "path": "/logical/path",
        "category": "sample",
        "vector_space_tag": "space",
        "additional_metadata": {"score": 0.5, "tags": ["a", "b"]},
    }
    value = TypedInlineValue(VECTOR_RECORD_DATA_TYPE_ID, 1, payload)
    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=VECTOR_RECORD_DATA_TYPE_ID,
    )
    restored = deserialize_runtime_value(
        json.loads(json.dumps(wire)),
        catalog=catalog,
        declared_type_id=VECTOR_RECORD_DATA_TYPE_ID,
    )
    assert restored == value
    assert restored.payload == payload

    invalid_values = (
        TypedInlineValue(OPENAI_CLIENT_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(VECTOR_RECORD_DATA_TYPE_ID, 2, payload),
        payload,
        TypedInlineValue(VECTOR_RECORD_DATA_TYPE_ID, 1, {**payload, "vector": []}),
    )
    for invalid_value in invalid_values:
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=VECTOR_RECORD_DATA_TYPE_ID,
            )

    wrong_identity_wire = json.loads(json.dumps(wire))
    wrong_identity_wire["data_type_id"] = OPENAI_CLIENT_DATA_TYPE_ID
    wrong_schema_wire = json.loads(json.dumps(wire))
    wrong_schema_wire["schema_version"] = 2
    invalid_payload_wire = json.loads(json.dumps(wire))
    invalid_payload_wire["payload"]["vector"] = []
    for invalid_wire in (
        wrong_identity_wire,
        wrong_schema_wire,
        payload,
        invalid_payload_wire,
    ):
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=VECTOR_RECORD_DATA_TYPE_ID,
            )


def test_remote_mcp_server_payload_validation_is_strict() -> None:
    spec = COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_DATA_TYPES[-1]
    payload = {
        "is_approved": True,
        "name": "  Server Name  ",
        "tool_names": ["second", "", "second", "first"],
        "url": "HTTPS://Example.COM:443/Path?token=visible-query",
    }
    original = json.loads(json.dumps(payload))
    original_tool_names = payload["tool_names"]
    assert spec.validate_item(payload) is True
    assert payload == original
    assert payload["tool_names"] is original_tool_names

    maximum_url_prefix = "https://example.com/"
    maximum_url = maximum_url_prefix + "a" * (32_768 - len(maximum_url_prefix))
    valid_payloads = (
        {**payload, "name": "x", "tool_names": None, "url": "http://x"},
        {**payload, "tool_names": []},
        {**payload, "name": "n" * 256},
        {**payload, "tool_names": [""] * 256},
        {**payload, "tool_names": ["t" * 256]},
        {**payload, "url": maximum_url},
        {**payload, "url": "https://example.com"},
        {**payload, "url": "http://example.com/path?x=1&x=2"},
        {**payload, "url": "https://example.com:0/path"},
        {**payload, "url": "https://example.com:65535/path"},
        {**payload, "url": "https://[2001:db8::1]:443/path?q=1"},
        {
            "url": "https://example.com",
            "tool_names": None,
            "name": "server",
            "is_approved": True,
        },
    )
    for candidate in valid_payloads:
        before = json.loads(json.dumps(candidate))
        tool_names = candidate["tool_names"]
        assert spec.validate_item(candidate) is True
        assert candidate == before
        assert candidate["tool_names"] is tool_names

    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class StringSubclass(str):
        pass

    class BoolLike:
        def __bool__(self) -> bool:
            raise AssertionError("bool-like value must not be coerced")

    class EqualityBomb:
        armed = False
        comparisons = 0

        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("non-string key equality must not run")
            return self is other

    class HostileString(str):
        armed = False
        comparisons = 0
        hashes = 0

        def __hash__(self) -> int:
            if self.armed:
                type(self).hashes += 1
                raise AssertionError("string-subclass key hash must not run")
            return super().__hash__()

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("string-subclass key equality must not run")
            return super().__eq__(other)

    non_string_key = EqualityBomb()
    non_string_key_payload = {
        non_string_key: True,
        "name": "server",
        "tool_names": None,
        "url": "https://example.com",
    }
    hostile_string_key = HostileString("is_approved")
    hostile_string_key_payload = {
        hostile_string_key: True,
        "name": "server",
        "tool_names": None,
        "url": "https://example.com",
    }
    EqualityBomb.armed = True
    HostileString.armed = True
    try:
        assert spec.validate_item(non_string_key_payload) is False
        assert spec.validate_item(hostile_string_key_payload) is False
        assert EqualityBomb.comparisons == 0
        assert HostileString.comparisons == 0
        assert HostileString.hashes == 0
    finally:
        EqualityBomb.armed = False
        HostileString.armed = False

    invalid_payloads = [
        None,
        object(),
        [],
        (),
        DictSubclass(payload),
        {key: value for key, value in payload.items() if key != "name"},
        {**payload, "extra": None},
        {
            "isApproved": True,
            "name": payload["name"],
            "tool_names": payload["tool_names"],
            "url": payload["url"],
        },
        {**payload, "is_approved": False},
        {**payload, "is_approved": 1},
        {**payload, "is_approved": None},
        {**payload, "is_approved": BoolLike()},
        {**payload, "name": ""},
        {**payload, "name": " \t "},
        {**payload, "name": "n" * 257},
        {**payload, "name": "name\n"},
        {**payload, "name": StringSubclass("name")},
        {**payload, "tool_names": ListSubclass(["tool"])},
        {**payload, "tool_names": [""] * 257},
        {**payload, "tool_names": ["t" * 257]},
        {**payload, "tool_names": [1]},
        {**payload, "tool_names": [None]},
        {**payload, "tool_names": ["tool\n"]},
        {**payload, "tool_names": [StringSubclass("tool")]},
        {**payload, "tool_names": ("tool",)},
        {**payload, "tool_names": {"tool"}},
        {**payload, "tool_names": iter(["tool"])},
        {**payload, "url": ""},
        {**payload, "url": " https://example.com"},
        {**payload, "url": "https://example.com "},
        {**payload, "url": maximum_url + "a"},
        {**payload, "url": StringSubclass("https://example.com")},
        {**payload, "url": "file:///tmp/value"},
        {**payload, "url": "ftp://example.com"},
        {**payload, "url": "javascript:alert(1)"},
        {**payload, "url": "data:text/plain,value"},
        {**payload, "url": "example.com/path"},
        {**payload, "url": "https:///path"},
        {**payload, "url": "https://"},
        {**payload, "url": "https://user@example.com"},
        {**payload, "url": "https://:password@example.com"},
        {**payload, "url": "https://@example.com"},
        {**payload, "url": "https://example.com:"},
        {**payload, "url": "https://example.com:not-a-port"},
        {**payload, "url": "https://example.com:-1"},
        {**payload, "url": "https://example.com:65536"},
        {**payload, "url": "https://[2001:db8::1"},
        {**payload, "url": "https://example.com/path with-space"},
        {**payload, "url": "https://example.com/path\n"},
        {**payload, "url": "https://example.com/\x00"},
        {**payload, "url": "https:\\example.com"},
        {**payload, "url": "https://example.com/#fragment"},
        {**payload, "url": "https://example.com/#"},
    ]
    for authentication_key in (
        "Authentication",
        "authentication",
        "auth",
        "credentials",
        "headers",
        "token",
        "secret_ref",
    ):
        invalid_payloads.append(
            {
                "is_approved": True,
                "name": "server",
                "url": "https://example.com",
                authentication_key: None,
            }
        )
    assert all(spec.validate_item(candidate) is False for candidate in invalid_payloads)

    sentinel = "D054_SECRET_SENTINEL"
    registry = _registry(COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_CONTRACT_MANIFEST)
    invalid_value = TypedInlineValue(
        REMOTE_MCP_SERVER_DATA_TYPE_ID,
        1,
        {**payload, "url": f"https://example.com/#{sentinel}"},
    )
    with pytest.raises(DataTypeCatalogError) as error:
        registry.data_types.validate_carrier(
            REMOTE_MCP_SERVER_DATA_TYPE_ID,
            invalid_value,
        )
    assert sentinel not in str(error.value)
    assert payload["url"] not in str(error.value)


def test_remote_mcp_server_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = _registry(COREX_AI_ML_REMOTE_MCP_SERVER_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    payload = {
        "is_approved": True,
        "name": "  MCP Server  ",
        "tool_names": ["second", "", "second", "first"],
        "url": "HTTPS://Example.COM:443/Path?token=query-value&x=1",
    }
    value = TypedInlineValue(REMOTE_MCP_SERVER_DATA_TYPE_ID, 1, payload)
    assert catalog.is_assignable(
        REMOTE_MCP_SERVER_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    )
    for declared_type_id in (REMOTE_MCP_SERVER_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID):
        catalog.validate_carrier(declared_type_id, value)
        wire = serialize_runtime_value(
            value,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert wire == {
            "__ea_runtime_value__": "typed_inline",
            "data_type_id": REMOTE_MCP_SERVER_DATA_TYPE_ID,
            "schema_version": 1,
            "payload": payload,
        }
        assert "authentication" not in wire["payload"]
        restored = deserialize_runtime_value(
            json.loads(json.dumps(wire)),
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert restored == value
        assert restored.payload == payload
        assert restored.payload["tool_names"] is not payload["tool_names"]

    for tool_names in (None, []):
        distinct_payload = {**payload, "tool_names": tool_names}
        distinct_value = TypedInlineValue(
            REMOTE_MCP_SERVER_DATA_TYPE_ID,
            1,
            distinct_payload,
        )
        distinct_wire = serialize_runtime_value(
            distinct_value,
            catalog=catalog,
            declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
        )
        distinct_restored = deserialize_runtime_value(
            json.loads(json.dumps(distinct_wire)),
            catalog=catalog,
            declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
        )
        assert distinct_restored.payload["tool_names"] == tool_names
        assert (distinct_restored.payload["tool_names"] is None) is (tool_names is None)

    invalid_values = (
        TypedInlineValue(OPENAI_CLIENT_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(VECTOR_RECORD_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(REMOTE_MCP_SERVER_DATA_TYPE_ID, 2, payload),
        payload,
        TypedInlineValue(
            REMOTE_MCP_SERVER_DATA_TYPE_ID,
            1,
            {**payload, "is_approved": False},
        ),
    )
    for invalid_value in invalid_values:
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
            )

    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
    )
    wrong_identity_wire = json.loads(json.dumps(wire))
    wrong_identity_wire["data_type_id"] = OPENAI_CLIENT_DATA_TYPE_ID
    wrong_schema_wire = json.loads(json.dumps(wire))
    wrong_schema_wire["schema_version"] = 2
    invalid_payload_wire = json.loads(json.dumps(wire))
    invalid_payload_wire["payload"]["is_approved"] = False
    for invalid_wire in (
        wrong_identity_wire,
        wrong_schema_wire,
        payload,
        invalid_payload_wire,
    ):
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
            )

    sentinel = "D054_RUNTIME_SENTINEL"
    sentinel_value = TypedInlineValue(
        REMOTE_MCP_SERVER_DATA_TYPE_ID,
        1,
        {**payload, "url": f"https://example.com/#{sentinel}"},
    )
    with pytest.raises(DataTypeCatalogError) as error:
        serialize_runtime_value(
            sentinel_value,
            catalog=catalog,
            declared_type_id=REMOTE_MCP_SERVER_DATA_TYPE_ID,
        )
    assert sentinel not in str(error.value)


def test_openai_mcp_connector_payload_validation_is_strict() -> None:
    spec = COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_DATA_TYPES[-1]
    payload = {
        "is_approved": True,
        "server_label": "OpenAI_Server-1",
        "tool_names": ["second", "", "second", "first"],
        "mcp_tool_connector_id": "connector_outlookemail",
    }
    original = json.loads(json.dumps(payload))
    original_tool_names = payload["tool_names"]
    assert spec.validate_item(payload) is True
    assert payload == original
    assert payload["tool_names"] is original_tool_names

    connector_ids = (
        "connector_dropbox",
        "connector_gmail",
        "connector_googlecalendar",
        "connector_googledrive",
        "connector_microsoftteams",
        "connector_outlookcalendar",
        "connector_outlookemail",
        "connector_sharepoint",
    )
    valid_payloads = (
        {**payload, "server_label": "A", "tool_names": None},
        {**payload, "server_label": "A" + "z" * 255, "tool_names": []},
        {**payload, "server_label": "a-b_c9"},
        {**payload, "tool_names": [""] * 256},
        {**payload, "tool_names": ["t" * 256]},
        {**payload, "tool_names": [" ", "", " "]},
        {
            "mcp_tool_connector_id": "connector_dropbox",
            "tool_names": None,
            "server_label": "Server",
            "is_approved": True,
        },
        *(
            {**payload, "mcp_tool_connector_id": connector_id}
            for connector_id in connector_ids
        ),
    )
    for candidate in valid_payloads:
        before = json.loads(json.dumps(candidate))
        tool_names = candidate["tool_names"]
        assert spec.validate_item(candidate) is True
        assert candidate == before
        assert candidate["tool_names"] is tool_names

    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class StringSubclass(str):
        pass

    class BoolLike:
        def __bool__(self) -> bool:
            raise AssertionError("bool-like value must not be coerced")

    class EqualityBomb:
        armed = False
        comparisons = 0

        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("non-string key equality must not run")
            return self is other

    class HostileString(str):
        armed = False
        comparisons = 0
        hashes = 0

        def __hash__(self) -> int:
            if self.armed:
                type(self).hashes += 1
                raise AssertionError("string-subclass key hash must not run")
            return super().__hash__()

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("string-subclass key equality must not run")
            return super().__eq__(other)

    non_string_key = EqualityBomb()
    non_string_key_payload = {
        non_string_key: True,
        "server_label": "Server",
        "tool_names": None,
        "mcp_tool_connector_id": "connector_gmail",
    }
    hostile_string_key = HostileString("is_approved")
    hostile_string_key_payload = {
        hostile_string_key: True,
        "server_label": "Server",
        "tool_names": None,
        "mcp_tool_connector_id": "connector_gmail",
    }
    EqualityBomb.armed = True
    HostileString.armed = True
    try:
        assert spec.validate_item(non_string_key_payload) is False
        assert spec.validate_item(hostile_string_key_payload) is False
        assert EqualityBomb.comparisons == 0
        assert HostileString.comparisons == 0
        assert HostileString.hashes == 0
    finally:
        EqualityBomb.armed = False
        HostileString.armed = False

    invalid_payloads = [
        None,
        object(),
        [],
        (),
        DictSubclass(payload),
        {key: value for key, value in payload.items() if key != "server_label"},
        {**payload, "extra": None},
        {
            "isApproved": True,
            "server_label": payload["server_label"],
            "tool_names": payload["tool_names"],
            "mcp_tool_connector_id": payload["mcp_tool_connector_id"],
        },
        {**payload, "is_approved": False},
        {**payload, "is_approved": 1},
        {**payload, "is_approved": None},
        {**payload, "is_approved": BoolLike()},
        {**payload, "server_label": ""},
        {**payload, "server_label": "A" + "z" * 256},
        {**payload, "server_label": "1Server"},
        {**payload, "server_label": "_Server"},
        {**payload, "server_label": "-Server"},
        {**payload, "server_label": "Server Name"},
        {**payload, "server_label": "Server.Name"},
        {**payload, "server_label": "Server/Name"},
        {**payload, "server_label": "ÅServer"},
        {**payload, "server_label": "Server\n"},
        {**payload, "server_label": StringSubclass("Server")},
        {**payload, "server_label": None},
        {**payload, "tool_names": ListSubclass(["tool"])},
        {**payload, "tool_names": [""] * 257},
        {**payload, "tool_names": ["t" * 257]},
        {**payload, "tool_names": [1]},
        {**payload, "tool_names": [None]},
        {**payload, "tool_names": ["tool\n"]},
        {**payload, "tool_names": ["tool\x00"]},
        {**payload, "tool_names": [StringSubclass("tool")]},
        {**payload, "tool_names": ("tool",)},
        {**payload, "tool_names": {"tool"}},
        {**payload, "tool_names": iter(["tool"])},
        {**payload, "mcp_tool_connector_id": ""},
        {**payload, "mcp_tool_connector_id": "connector_Gmail"},
        {**payload, "mcp_tool_connector_id": "connector_gmail "},
        {**payload, "mcp_tool_connector_id": "prefix_connector_gmail"},
        {**payload, "mcp_tool_connector_id": "connector_gmail_suffix"},
        {**payload, "mcp_tool_connector_id": "connector_unknown"},
        {
            **payload,
            "mcp_tool_connector_id": StringSubclass("connector_gmail"),
        },
        {**payload, "mcp_tool_connector_id": None},
    ]
    for authentication_key in (
        "Authentication",
        "authentication",
        "auth",
        "credentials",
        "headers",
        "token",
        "secret_ref",
    ):
        invalid_payloads.append({**payload, authentication_key: None})
    assert all(spec.validate_item(candidate) is False for candidate in invalid_payloads)

    sentinel = "D055_CONNECTOR_SENTINEL"
    sensitive_label = "D055SensitiveLabel"
    sensitive_tool = "D055 sensitive tool"
    invalid_value = TypedInlineValue(
        OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        1,
        {
            "is_approved": True,
            "server_label": sensitive_label,
            "tool_names": [sensitive_tool],
            "mcp_tool_connector_id": sentinel,
        },
    )
    registry = _registry(COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_CONTRACT_MANIFEST)
    with pytest.raises(DataTypeCatalogError) as error:
        registry.data_types.validate_carrier(
            OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            invalid_value,
        )
    message = str(error.value)
    assert all(
        secret not in message
        for secret in (sentinel, sensitive_label, sensitive_tool, "Traceback")
    )


def test_openai_mcp_connector_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = _registry(COREX_AI_ML_OPENAI_MCP_CONNECTOR_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    payload = {
        "is_approved": True,
        "server_label": "OpenAI_Server-1",
        "tool_names": ["second", "", "second", "first"],
        "mcp_tool_connector_id": "connector_microsoftteams",
    }
    value = TypedInlineValue(OPENAI_MCP_CONNECTOR_DATA_TYPE_ID, 1, payload)
    assert catalog.is_assignable(OPENAI_MCP_CONNECTOR_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID)
    for declared_type_id in (OPENAI_MCP_CONNECTOR_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID):
        catalog.validate_carrier(declared_type_id, value)
        wire = serialize_runtime_value(
            value,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert wire == {
            "__ea_runtime_value__": "typed_inline",
            "data_type_id": OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            "schema_version": 1,
            "payload": payload,
        }
        assert set(wire["payload"]) == {
            "is_approved",
            "server_label",
            "tool_names",
            "mcp_tool_connector_id",
        }
        restored = deserialize_runtime_value(
            json.loads(json.dumps(wire)),
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert restored == value
        assert restored.payload == payload
        assert restored.payload["tool_names"] is not payload["tool_names"]

    for tool_names in (None, []):
        distinct_payload = {**payload, "tool_names": tool_names}
        distinct_value = TypedInlineValue(
            OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            1,
            distinct_payload,
        )
        distinct_wire = serialize_runtime_value(
            distinct_value,
            catalog=catalog,
            declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        )
        distinct_restored = deserialize_runtime_value(
            json.loads(json.dumps(distinct_wire)),
            catalog=catalog,
            declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        )
        assert distinct_restored.payload["tool_names"] == tool_names
        assert (distinct_restored.payload["tool_names"] is None) is (tool_names is None)

    invalid_values = (
        TypedInlineValue(OPENAI_CLIENT_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(REMOTE_MCP_SERVER_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(OPENAI_MCP_CONNECTOR_DATA_TYPE_ID, 2, payload),
        payload,
        TypedInlineValue(
            OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            1,
            {**payload, "is_approved": False},
        ),
        TypedInlineValue(
            OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            1,
            {**payload, "authentication": None},
        ),
    )
    for invalid_value in invalid_values:
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            )

    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
    )
    wrong_identity_wire = json.loads(json.dumps(wire))
    wrong_identity_wire["data_type_id"] = OPENAI_CLIENT_DATA_TYPE_ID
    wrong_schema_wire = json.loads(json.dumps(wire))
    wrong_schema_wire["schema_version"] = 2
    invalid_payload_wire = json.loads(json.dumps(wire))
    invalid_payload_wire["payload"]["mcp_tool_connector_id"] = "connector_unknown"
    authentication_wire = json.loads(json.dumps(wire))
    authentication_wire["payload"]["authentication"] = None
    for invalid_wire in (
        wrong_identity_wire,
        wrong_schema_wire,
        payload,
        invalid_payload_wire,
        authentication_wire,
    ):
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
            )

    sentinel = "D055_RUNTIME_SENTINEL"
    sentinel_value = TypedInlineValue(
        OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        1,
        {**payload, "mcp_tool_connector_id": sentinel},
    )
    with pytest.raises(DataTypeCatalogError) as error:
        serialize_runtime_value(
            sentinel_value,
            catalog=catalog,
            declared_type_id=OPENAI_MCP_CONNECTOR_DATA_TYPE_ID,
        )
    assert sentinel not in str(error.value)


def test_web_client_settings_payload_validation_is_strict() -> None:
    spec = COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES[-1]
    query_sentinel = "D056_QUERY_SENTINEL"
    payload = {
        "base_url": f"https://example.com/path/to/resource?api_key={query_sentinel}",
        "retry_count": 3,
        "timeout_seconds": 15,
        "headers": {},
        "allow_insecure": False,
        "uses_windows_authentication": False,
    }
    original = json.loads(json.dumps(payload))
    original_headers = payload["headers"]
    assert spec.validate_item(payload) is True
    assert payload == original
    assert payload["headers"] is original_headers

    max_length_url_prefix = "https://example.com/"
    max_length_url = max_length_url_prefix + "a" * (32_768 - len(max_length_url_prefix))
    valid_urls = (
        None,
        "http://x",
        "HTTP://example.com",
        "https://example.com/path",
        f"https://example.com/path?value={query_sentinel}",
        "http://localhost:0/path?value=one",
        "https://example.com:65535/path?value=two",
        max_length_url,
    )
    for base_url in valid_urls:
        candidate = {**payload, "base_url": base_url, "headers": {}}
        before = candidate.copy()
        headers = candidate["headers"]
        assert spec.validate_item(candidate) is True
        assert candidate == before
        assert candidate["base_url"] is base_url
        assert candidate["headers"] is headers

    for integer in (1, 3, 15, 2_147_483_647):
        retry_candidate = {**payload, "retry_count": integer, "headers": {}}
        timeout_candidate = {
            **payload,
            "timeout_seconds": integer,
            "headers": {},
        }
        assert spec.validate_item(retry_candidate) is True
        assert spec.validate_item(timeout_candidate) is True

    class DictSubclass(dict):
        def __len__(self) -> int:
            raise AssertionError("dict subclass length must not run")

    class StringSubclass(str):
        def strip(self, chars: str | None = None) -> str:
            raise AssertionError("string subclass methods must not run")

    class IntegerSubclass(int):
        pass

    class BoolLike:
        def __bool__(self) -> bool:
            raise AssertionError("bool-like value must not be coerced")

    class EqualityBomb:
        armed = False
        comparisons = 0

        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("non-string key equality must not run")
            return self is other

    class HostileString(str):
        armed = False
        comparisons = 0
        hashes = 0

        def __hash__(self) -> int:
            if self.armed:
                type(self).hashes += 1
                raise AssertionError("string-subclass key hash must not run")
            return super().__hash__()

        def __eq__(self, other: object) -> bool:
            if self.armed:
                type(self).comparisons += 1
                raise AssertionError("string-subclass key equality must not run")
            return super().__eq__(other)

    non_string_key = EqualityBomb()
    non_string_key_payload = {
        non_string_key: payload["base_url"],
        "retry_count": 3,
        "timeout_seconds": 15,
        "headers": {},
        "allow_insecure": False,
        "uses_windows_authentication": False,
    }
    hostile_string_key = HostileString("base_url")
    hostile_string_key_payload = {
        hostile_string_key: payload["base_url"],
        "retry_count": 3,
        "timeout_seconds": 15,
        "headers": {},
        "allow_insecure": False,
        "uses_windows_authentication": False,
    }
    EqualityBomb.armed = True
    HostileString.armed = True
    try:
        assert spec.validate_item(non_string_key_payload) is False
        assert spec.validate_item(hostile_string_key_payload) is False
        assert EqualityBomb.comparisons == 0
        assert HostileString.comparisons == 0
        assert HostileString.hashes == 0
    finally:
        EqualityBomb.armed = False
        HostileString.armed = False

    invalid_roots = (None, object(), [], (), DictSubclass(payload))
    assert all(spec.validate_item(candidate) is False for candidate in invalid_roots)

    invalid_shapes = [
        {key: value for key, value in payload.items() if key != "base_url"},
        {**payload, "extra": None},
        {
            "baseUrl": payload["base_url"],
            "retry_count": 3,
            "timeout_seconds": 15,
            "headers": {},
            "allow_insecure": False,
            "uses_windows_authentication": False,
        },
    ]
    for forbidden_key in (
        "api_key",
        "token",
        "windows_token",
        "authentication",
        "authorization",
        "credentials",
        "cookie",
        "proxy",
        "certificate",
        "secret_ref",
    ):
        invalid_shapes.append({**payload, forbidden_key: "D056_SENSITIVE_VALUE"})
    assert all(spec.validate_item(candidate) is False for candidate in invalid_shapes)

    invalid_urls = (
        StringSubclass("https://example.com"),
        "",
        max_length_url + "a",
        " https://example.com",
        "https://example.com ",
        "https://exa mple.com",
        "https://example.com\n",
        "https://example.com\x00",
        "https:\\example.com",
        "https://example.com/path#fragment",
        "https://user@example.com",
        "https://user:password@example.com",
        "https:///path",
        "https://",
        "https://example.com:",
        "https://example.com:not-a-port",
        "https://example.com:65536",
        "https://[::1",
        "ftp://example.com",
        "example.com/path",
    )
    for base_url in invalid_urls:
        candidate = {**payload, "base_url": base_url, "headers": {}}
        before = candidate.copy()
        headers = candidate["headers"]
        assert spec.validate_item(candidate) is False
        assert candidate == before
        assert candidate["headers"] is headers

    invalid_integers = (
        0,
        -1,
        2_147_483_648,
        True,
        False,
        1.0,
        "1",
        IntegerSubclass(1),
    )
    for integer in invalid_integers:
        assert spec.validate_item({**payload, "retry_count": integer}) is False
        assert spec.validate_item({**payload, "timeout_seconds": integer}) is False

    invalid_headers = (
        {"Authorization": "D056_SENSITIVE_VALUE"},
        DictSubclass(),
        [],
        (),
        None,
    )
    for headers in invalid_headers:
        assert spec.validate_item({**payload, "headers": headers}) is False

    invalid_security_values = (True, 1, None, BoolLike())
    for security_value in invalid_security_values:
        assert (
            spec.validate_item({**payload, "allow_insecure": security_value}) is False
        )
        assert (
            spec.validate_item(
                {**payload, "uses_windows_authentication": security_value}
            )
            is False
        )

    raw_url = f"https://example.com/path?api_key={query_sentinel}#fragment"
    sensitive_value = "D056_SENSITIVE_VALUE"
    invalid_payload = {
        **payload,
        "base_url": raw_url,
        "headers": {"Authorization": sensitive_value},
    }
    invalid_before = invalid_payload.copy()
    invalid_headers_object = invalid_payload["headers"]
    assert spec.validate_item(invalid_payload) is False
    assert invalid_payload == invalid_before
    assert invalid_payload["headers"] is invalid_headers_object
    registry = _registry(COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_CONTRACT_MANIFEST)
    with pytest.raises(DataTypeCatalogError) as error:
        registry.data_types.validate_carrier(
            WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            TypedInlineValue(WEB_CLIENT_SETTINGS_DATA_TYPE_ID, 1, invalid_payload),
        )
    message = str(error.value)
    assert all(
        secret not in message
        for secret in (raw_url, query_sentinel, sensitive_value, "Traceback")
    )


def test_web_client_settings_runtime_json_round_trip_is_catalog_checked() -> None:
    registry = _registry(COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    query_sentinel = "D056_RUNTIME_QUERY_SENTINEL"
    payload = {
        "base_url": f"https://example.com/path?api_key={query_sentinel}",
        "retry_count": 3,
        "timeout_seconds": 15,
        "headers": {},
        "allow_insecure": False,
        "uses_windows_authentication": False,
    }
    value = TypedInlineValue(WEB_CLIENT_SETTINGS_DATA_TYPE_ID, 1, payload)
    expected_keys = {
        "base_url",
        "retry_count",
        "timeout_seconds",
        "headers",
        "allow_insecure",
        "uses_windows_authentication",
    }
    assert set(payload) == expected_keys
    assert payload["headers"] == {}
    assert all(
        key not in payload
        for key in (
            "api_key",
            "token",
            "windows_token",
            "authentication",
            "authorization",
            "credentials",
            "cookie",
            "proxy",
            "certificate",
            "secret_ref",
        )
    )
    assert catalog.is_assignable(WEB_CLIENT_SETTINGS_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID)
    for declared_type_id in (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID):
        catalog.validate_carrier(declared_type_id, value)
        wire = serialize_runtime_value(
            value,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert wire == {
            "__ea_runtime_value__": "typed_inline",
            "data_type_id": WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            "schema_version": 1,
            "payload": payload,
        }
        assert set(wire["payload"]) == expected_keys
        restored = deserialize_runtime_value(
            json.loads(json.dumps(wire)),
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
        assert restored == value
        assert restored.payload == payload
        assert restored.payload["base_url"] == payload["base_url"]
        assert restored.payload["headers"] == {}
        assert restored.payload["headers"] is not payload["headers"]

    invalid_values = (
        (
            WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            TypedInlineValue(REMOTE_MCP_SERVER_DATA_TYPE_ID, 1, payload),
        ),
        (
            WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            TypedInlineValue(WEB_CLIENT_SETTINGS_DATA_TYPE_ID, 2, payload),
        ),
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, payload),
        (
            WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            TypedInlineValue(
                WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
                1,
                {**payload, "headers": {"Authorization": "not-allowed"}},
            ),
        ),
        (
            WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
            TypedInlineValue(
                WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
                1,
                {**payload, "authentication": None},
            ),
        ),
        (
            GRAPH_DATA_TYPE_ID,
            TypedInlineValue(OPENAI_CLIENT_DATA_TYPE_ID, 1, payload),
        ),
    )
    for declared_type_id, invalid_value in invalid_values:
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=declared_type_id,
            )

    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
    )
    wrong_identity_wire = json.loads(json.dumps(wire))
    wrong_identity_wire["data_type_id"] = REMOTE_MCP_SERVER_DATA_TYPE_ID
    wrong_schema_wire = json.loads(json.dumps(wire))
    wrong_schema_wire["schema_version"] = 2
    invalid_payload_wire = json.loads(json.dumps(wire))
    invalid_payload_wire["payload"]["headers"] = {"Authorization": "not-allowed"}
    authentication_wire = json.loads(json.dumps(wire))
    authentication_wire["payload"]["authentication"] = None
    abstract_identity_wire = json.loads(json.dumps(wire))
    abstract_identity_wire["data_type_id"] = OPENAI_CLIENT_DATA_TYPE_ID
    invalid_wires = (
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, wrong_identity_wire),
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, wrong_schema_wire),
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, payload),
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, invalid_payload_wire),
        (WEB_CLIENT_SETTINGS_DATA_TYPE_ID, authentication_wire),
        (GRAPH_DATA_TYPE_ID, abstract_identity_wire),
    )
    for declared_type_id, invalid_wire in invalid_wires:
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=declared_type_id,
            )

    raw_url = f"https://example.com/path?api_key={query_sentinel}"
    sensitive_value = "D056_RUNTIME_SENSITIVE_VALUE"
    sensitive_payload = {
        **payload,
        "base_url": raw_url,
        "headers": {"Authorization": sensitive_value},
    }
    sensitive_value_object = TypedInlineValue(
        WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
        1,
        sensitive_payload,
    )
    with pytest.raises(DataTypeCatalogError) as serialize_error:
        serialize_runtime_value(
            sensitive_value_object,
            catalog=catalog,
            declared_type_id=WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
        )
    sensitive_wire = json.loads(json.dumps(wire))
    sensitive_wire["payload"] = sensitive_payload
    with pytest.raises(DataTypeCatalogError) as deserialize_error:
        deserialize_runtime_value(
            sensitive_wire,
            catalog=catalog,
            declared_type_id=WEB_CLIENT_SETTINGS_DATA_TYPE_ID,
        )
    for error in (serialize_error, deserialize_error):
        message = str(error.value)
        assert all(
            secret not in message
            for secret in (raw_url, query_sentinel, sensitive_value, "Traceback")
        )


def _execution_context(
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="d058-test",
        node_id="d058-node",
        workspace_id="d058-workspace",
        inputs={} if inputs is None else inputs,
        properties={} if properties is None else properties,
        emit_log=lambda _level, _message: None,
    )


def _execute_node(
    node_type_id: str,
    *,
    inputs: dict[str, object] | None = None,
    properties: dict[str, object] | None = None,
) -> object:
    operation = {
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID: execute_sqlite_vector_database,
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID: execute_create_vector_collection,
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID: execute_inspect_vector_collection,
    }[node_type_id]
    return operation(_execution_context(inputs=inputs, properties=properties))


def _connection_value(file_path: str) -> TypedInlineValue:
    return TypedInlineValue(
        VECTOR_DB_CONNECTION_DATA_TYPE_ID,
        1,
        {"provider": "sqlite", "file_path": file_path},
    )


def _collection_value(file_path: str, collection_name: str) -> TypedInlineValue:
    return TypedInlineValue(
        VECTOR_COLLECTION_DATA_TYPE_ID,
        1,
        {
            "connection": {"provider": "sqlite", "file_path": file_path},
            "collection_name": collection_name,
        },
    )


def _initialize_database(file_path: str) -> TypedInlineValue:
    result = _execute_node(
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
        properties={"file_path": file_path},
    )
    return result.outputs["vector_database"]


def _database_facts(file_path: str) -> tuple[object, ...]:
    connection = sqlite3.connect(file_path, timeout=5.0, uri=False)
    try:
        return (
            connection.execute("PRAGMA application_id").fetchone(),
            connection.execute("PRAGMA user_version").fetchone(),
            tuple(
                connection.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                    "WHERE substr(name, 1, 7) != 'sqlite_' ORDER BY type, name"
                ).fetchall()
            ),
            tuple(
                connection.execute(
                    "PRAGMA table_info(corex_vector_collections)"
                ).fetchall()
            ),
        )
    finally:
        connection.close()


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in D058 tests")

    monkeypatch.setattr(socket, "socket", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", deny_network)


class _TrackingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        events: list[tuple[object, ...]],
        *,
        fail_on: str = "",
    ) -> None:
        self._connection = connection
        self._events = events
        self._fail_on = fail_on

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        self._events.append(("execute", sql, parameters))
        if self._fail_on and self._fail_on in sql:
            raise sqlite3.OperationalError("injected D058 failure")
        return self._connection.execute(sql, parameters)

    def commit(self) -> None:
        self._events.append(("commit",))
        if self._fail_on == "commit":
            raise sqlite3.OperationalError("injected D058 failure")
        self._connection.commit()

    def rollback(self) -> None:
        self._events.append(("rollback",))
        self._connection.rollback()

    def close(self) -> None:
        self._events.append(("close",))
        self._connection.close()


def test_vector_collection_contract_facts_and_owner_inventory_are_exact(
    tmp_path: Path,
) -> None:
    assert (
        VECTOR_COLLECTION_DATA_TYPE_ID
        == "AdvancedAiModule.VectorDb.DataTypes.VectorCollection"
    )
    assert (
        COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[:10]
        == COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES
    )
    assert all(
        successor is predecessor
        for successor, predecessor in zip(
            COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[:10],
            COREX_AI_ML_WEB_CLIENT_SETTINGS_CANDIDATE_DATA_TYPES,
            strict=True,
        )
    )
    assert (
        tuple(spec.type_id for spec in COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES)
        == _EXPECTED_VECTOR_DATABASE_TYPE_IDS
    )
    spec = COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-1]
    assert (
        spec.type_id,
        spec.display_name,
        spec.family_id,
        spec.parents,
        spec.abstract,
        spec.carriers,
        spec.persistence,
        spec.sensitivity,
        spec.payload_schema_version,
        spec.implementation_version,
        spec.description,
        spec.capabilities,
        spec.coerce_untyped_input,
    ) == (
        VECTOR_COLLECTION_DATA_TYPE_ID,
        "Vector Collection",
        "container",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "never",
        "sensitive",
        1,
        "1",
        "",
        frozenset(),
        None,
    )
    assert COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST == (
        PluginContractManifest(
            data_types=COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES
        )
    )
    assert spec.validate_item(
        {
            "connection": {
                "provider": "sqlite",
                "file_path": str(tmp_path / "collection.db"),
            },
            "collection_name": "Collection_1",
        }
    )

    registry = build_builtin_registry()
    assert registry.plugin_contract_manifest(COREX_AI_ML_CONTRACTS_OWNER_ID) is (
        COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST
    )
    assert {
        record["type_id"]
        for record in registry.data_types.snapshot()
        if record["kind"] == "type"
        and record["owner_id"] == COREX_AI_ML_CONTRACTS_OWNER_ID
    } == set(_EXPECTED_VECTOR_DATABASE_TYPE_IDS)
    converted_ids = {
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
    }
    assert {
        type_id: registry.get_entry(type_id).owner_id for type_id in converted_ids
    } == {
        type_id: INTERNAL_BUILTIN_FUNCTION_OWNER_ID for type_id in converted_ids
    }


def test_vector_collection_payload_validation_is_strict(tmp_path: Path) -> None:
    class DictSubclass(dict):
        pass

    class StrSubclass(str):
        pass

    spec = COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-1]
    file_path = str(tmp_path / "strict.sqlite")
    connection = {"provider": "sqlite", "file_path": file_path}
    valid = {"connection": connection, "collection_name": "Collection-1"}
    assert spec.validate_item(valid)
    invalid = (
        DictSubclass(valid),
        {**valid, "extra": None},
        {"connection": connection},
        {**valid, "collection_name": StrSubclass("Collection-1")},
        {**valid, "collection_name": ""},
        {**valid, "collection_name": "1Collection"},
        {**valid, "collection_name": "A" * 65},
        {**valid, "connection": DictSubclass(connection)},
        {
            **valid,
            "connection": {
                "provider": StrSubclass("sqlite"),
                "file_path": file_path,
            },
        },
        {
            **valid,
            "connection": TypedInlineValue(
                VECTOR_DB_CONNECTION_DATA_TYPE_ID,
                1,
                connection,
            ),
        },
    )
    assert all(spec.validate_item(value) is False for value in invalid)

    source_connection = dict(connection)
    value = TypedInlineValue(
        VECTOR_COLLECTION_DATA_TYPE_ID,
        1,
        {"connection": source_connection, "collection_name": "Collection-1"},
    )
    source_connection["file_path"] = "changed"
    assert value.payload == valid
    assert type(value.payload) is dict
    assert type(value.payload["connection"]) is dict


def test_vector_collection_runtime_json_round_trip_is_catalog_checked(
    tmp_path: Path,
) -> None:
    registry = _registry(COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    payload = {
        "connection": {
            "provider": "sqlite",
            "file_path": str(tmp_path / "round-trip.sqlite3"),
        },
        "collection_name": "RoundTrip",
    }
    value = TypedInlineValue(VECTOR_COLLECTION_DATA_TYPE_ID, 1, payload)
    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=VECTOR_COLLECTION_DATA_TYPE_ID,
    )
    restored = deserialize_runtime_value(
        json.loads(json.dumps(wire)),
        catalog=catalog,
        declared_type_id=VECTOR_COLLECTION_DATA_TYPE_ID,
    )
    assert restored == value
    assert restored.payload == payload
    assert restored.payload is not payload
    assert restored.payload["connection"] is not payload["connection"]

    for field, replacement in (
        ("data_type_id", VECTOR_DB_CONNECTION_DATA_TYPE_ID),
        ("schema_version", 2),
    ):
        invalid_wire = json.loads(json.dumps(wire))
        invalid_wire[field] = replacement
        with pytest.raises(DataTypeCatalogError):
            deserialize_runtime_value(
                invalid_wire,
                catalog=catalog,
                declared_type_id=VECTOR_COLLECTION_DATA_TYPE_ID,
            )
    invalid_wire = json.loads(json.dumps(wire))
    invalid_wire["payload"]["extra"] = None
    with pytest.raises(DataTypeCatalogError):
        deserialize_runtime_value(
            invalid_wire,
            catalog=catalog,
            declared_type_id=VECTOR_COLLECTION_DATA_TYPE_ID,
        )


def test_vector_db_connection_contract_facts_and_owner_inventory_are_exact(
    tmp_path: Path,
) -> None:
    assert (
        VECTOR_DB_CONNECTION_DATA_TYPE_ID
        == "AdvancedAiModule.VectorDb.DataTypes.VectorDbConnection"
    )
    spec = COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-2]
    assert (
        spec.type_id,
        spec.display_name,
        spec.family_id,
        spec.parents,
        spec.abstract,
        spec.carriers,
        spec.persistence,
        spec.sensitivity,
        spec.payload_schema_version,
        spec.implementation_version,
        spec.description,
        spec.capabilities,
        spec.coerce_untyped_input,
    ) == (
        VECTOR_DB_CONNECTION_DATA_TYPE_ID,
        "Vector DB Connection",
        "container",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "never",
        "sensitive",
        1,
        "1",
        "",
        frozenset(),
        None,
    )
    assert spec.validate_item(
        {"provider": "sqlite", "file_path": str(tmp_path / "connection.db")}
    )
    assert (
        COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-2].type_id,
        COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-1].type_id,
    ) == (VECTOR_DB_CONNECTION_DATA_TYPE_ID, VECTOR_COLLECTION_DATA_TYPE_ID)
    registry = build_builtin_registry()
    assert (
        registry.data_types.owner_of(VECTOR_DB_CONNECTION_DATA_TYPE_ID)
        == COREX_AI_ML_CONTRACTS_OWNER_ID
    )
    assert (
        len(
            [
                record
                for record in registry.data_types.snapshot()
                if record["kind"] == "type"
                and record["owner_id"] == COREX_AI_ML_CONTRACTS_OWNER_ID
            ]
        )
        == 12
    )


def test_vector_db_connection_payload_validation_is_strict(tmp_path: Path) -> None:
    class DictSubclass(dict):
        pass

    class StrSubclass(str):
        pass

    spec = COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES[-2]
    file_path = str(tmp_path / "strict.db")
    valid = {"provider": "sqlite", "file_path": file_path}
    assert spec.validate_item(valid)
    invalid = (
        DictSubclass(valid),
        {**valid, "extra": None},
        {"provider": "sqlite"},
        {"provider": "SQLite", "file_path": file_path},
        {"provider": StrSubclass("sqlite"), "file_path": file_path},
        {"provider": "sqlite", "file_path": StrSubclass(file_path)},
        {"provider": "sqlite", "file_path": "relative.db"},
    )
    assert all(spec.validate_item(value) is False for value in invalid)


def test_vector_db_connection_runtime_json_round_trip_is_catalog_checked(
    tmp_path: Path,
) -> None:
    registry = _registry(COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST)
    catalog = registry.data_types
    payload = {
        "provider": "sqlite",
        "file_path": str(tmp_path / "round-trip.DB"),
    }
    value = TypedInlineValue(VECTOR_DB_CONNECTION_DATA_TYPE_ID, 1, payload)
    wire = serialize_runtime_value(
        value,
        catalog=catalog,
        declared_type_id=VECTOR_DB_CONNECTION_DATA_TYPE_ID,
    )
    assert wire == {
        "__ea_runtime_value__": "typed_inline",
        "data_type_id": VECTOR_DB_CONNECTION_DATA_TYPE_ID,
        "schema_version": 1,
        "payload": payload,
    }
    restored = deserialize_runtime_value(
        json.loads(json.dumps(wire)),
        catalog=catalog,
        declared_type_id=VECTOR_DB_CONNECTION_DATA_TYPE_ID,
    )
    assert restored == value
    assert restored.payload is not payload
    for invalid_value in (
        TypedInlineValue(VECTOR_COLLECTION_DATA_TYPE_ID, 1, payload),
        TypedInlineValue(VECTOR_DB_CONNECTION_DATA_TYPE_ID, 2, payload),
        payload,
    ):
        with pytest.raises(DataTypeCatalogError):
            serialize_runtime_value(
                invalid_value,
                catalog=catalog,
                declared_type_id=VECTOR_DB_CONNECTION_DATA_TYPE_ID,
            )


def test_sqlite_vector_function_specs_and_successor_inventory_are_exact() -> None:
    assert len(ai_ml_module.__all__) == len(set(ai_ml_module.__all__))
    assert {
        "VECTOR_DB_CONNECTION_DATA_TYPE_ID",
        "VECTOR_COLLECTION_DATA_TYPE_ID",
        "SQLITE_VECTOR_DATABASE_NODE_TYPE_ID",
        "CREATE_VECTOR_COLLECTION_NODE_TYPE_ID",
        "INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID",
        "COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_DATA_TYPES",
        "COREX_AI_ML_VECTOR_DATABASE_CANDIDATE_CONTRACT_MANIFEST",
        "execute_create_vector_collection",
        "execute_inspect_vector_collection",
        "execute_sqlite_vector_database",
    }.issubset(ai_ml_module.__all__)
    declarations = discover_plugin_declarations(
        AI_VECTOR_DATABASE_SOURCE,
        filename="builtin_functions/ai_vector_database.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    ids = {
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
    }
    golden = load_current_repo_owned_catalog()
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in golden
        if row["spec"]["type_id"] in ids
    }
    assert {
        declaration.spec.type_id: json.loads(json.dumps(asdict(declaration.spec)))
        for declaration in declarations
    } == expected
    assert tuple(declaration.spec.type_id for declaration in declarations) == (
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
    )
    sqlite_spec, create_spec, inspect_spec = (
        declaration.spec for declaration in declarations
    )
    assert all(
        (
            spec.category_path,
            spec.icon,
            spec.runtime_behavior,
            spec.is_async,
            spec.dynamic_port_groups,
        )
        == (("AI", "Vector Database"), "database", "active", False, ())
        for spec in (sqlite_spec, create_spec, inspect_spec)
    )
    assert (
        sqlite_spec.display_name,
        tuple((port.key, port.direction, port.data_type) for port in sqlite_spec.ports),
    ) == (
        "SQLite Vector Database",
        (
            ("file_path", "in", STRING_DATA_TYPE_ID),
            ("vector_database", "out", VECTOR_DB_CONNECTION_DATA_TYPE_ID),
        ),
    )
    assert sqlite_spec.ports[0].required is True
    assert sqlite_spec.ports[0].uses_property_default is True
    assert sqlite_spec.properties == (
        PropertySpec(
            "file_path",
            "path",
            "",
            "File Path",
            file_filter="SQLite database (*.db *.sqlite *.sqlite3)",
        ),
    )
    assert (
        create_spec.display_name,
        tuple((port.key, port.direction, port.data_type) for port in create_spec.ports),
    ) == (
        "Create Vector Collection",
        (
            ("vector_database", "in", VECTOR_DB_CONNECTION_DATA_TYPE_ID),
            ("collection_name", "in", STRING_DATA_TYPE_ID),
            ("vector_dimension", "in", INTEGER_DATA_TYPE_ID),
            ("distance_metric", "in", STRING_DATA_TYPE_ID),
            ("additional_metadata", "in", GRAPH_DICTIONARY_DATA_TYPE_ID),
            ("vector_collection", "out", VECTOR_COLLECTION_DATA_TYPE_ID),
        ),
    )
    assert [port.required for port in create_spec.ports] == [
        True,
        True,
        True,
        True,
        False,
        None,
    ]
    assert [port.uses_property_default for port in create_spec.ports] == [
        False,
        True,
        True,
        True,
        True,
        False,
    ]
    assert [
        (
            prop.key,
            prop.type,
            prop.default,
            prop.minimum,
            prop.maximum,
            prop.enum_values,
            prop.inline_editor,
        )
        for prop in create_spec.properties
    ] == [
        ("collection_name", "str", "", None, None, (), ""),
        ("vector_dimension", "int", 1, 1, 65_536, (), ""),
        (
            "distance_metric",
            "enum",
            "Cosine",
            None,
            None,
            ("Cosine", "Euclidean"),
            "enum",
        ),
        ("additional_metadata", "json", {}, None, None, (), ""),
    ]
    assert (
        inspect_spec.display_name,
        tuple(
            (port.key, port.direction, port.data_type) for port in inspect_spec.ports
        ),
        inspect_spec.properties,
    ) == (
        "Inspect Vector Collection",
        (
            ("vector_collection", "in", VECTOR_COLLECTION_DATA_TYPE_ID),
            ("name", "out", STRING_DATA_TYPE_ID),
            ("record_count", "out", INTEGER_DATA_TYPE_ID),
            ("vector_dimension", "out", INTEGER_DATA_TYPE_ID),
            ("distance_metric", "out", STRING_DATA_TYPE_ID),
            ("metadata", "out", GRAPH_DICTIONARY_DATA_TYPE_ID),
        ),
        (),
    )
    assert [len(spec.ports) for spec in (sqlite_spec, create_spec, inspect_spec)] == [
        2,
        6,
        6,
    ]
    assert not hasattr(ai_ml_module, "COREX_AI_ML_VECTOR_DATABASE_NODE_DESCRIPTORS")


def test_sqlite_vector_database_initialization_and_path_policy_are_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_network(monkeypatch)
    real_connect = sqlite3.connect
    events: list[tuple[object, ...]] = []

    def tracking_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        events.append(("connect", database, timeout, uri))
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            events,
        )

    database_path = str(tmp_path / "nested" / "vectors.DB")
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    result = _execute_node(
        SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
        properties={"file_path": database_path},
    )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert result.outputs == {"vector_database": _connection_value(database_path)}
    assert Path(database_path).is_file()
    assert events[0] == ("connect", database_path, 5.0, False)
    statements = [event[1] for event in events if event[0] == "execute"]
    assert statements[0] == "BEGIN IMMEDIATE"
    assert statements[1:4] == [
        "PRAGMA application_id",
        "PRAGMA user_version",
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE substr(name, 1, 7) != 'sqlite_' ORDER BY type, name",
    ]
    assert statements.index(ai_ml_module._COLLECTION_TABLE_SQL) < statements.index(
        f"PRAGMA application_id = {ai_ml_module._APPLICATION_ID}"
    )
    assert statements[-1] == "PRAGMA table_info(corex_vector_collections)"
    assert events[-2:] == [("commit",), ("close",)]

    expected_sql = """CREATE TABLE corex_vector_collections (
    collection_name TEXT PRIMARY KEY NOT NULL,
    vector_dimension INTEGER NOT NULL
        CHECK(typeof(vector_dimension) = 'integer'
              AND vector_dimension BETWEEN 1 AND 65536),
    distance_metric INTEGER NOT NULL
        CHECK(typeof(distance_metric) = 'integer'
              AND distance_metric IN (0, 1)),
    metadata_json TEXT NOT NULL
)"""
    assert _database_facts(database_path) == (
        (1_129_271_896,),
        (1,),
        (
            (
                "table",
                "corex_vector_collections",
                "corex_vector_collections",
                expected_sql,
            ),
        ),
        (
            (0, "collection_name", "TEXT", 1, None, 1),
            (1, "vector_dimension", "INTEGER", 1, None, 0),
            (2, "distance_metric", "INTEGER", 1, None, 0),
            (3, "metadata_json", "TEXT", 1, None, 0),
        ),
    )
    before_idempotent = Path(database_path).read_bytes()
    events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    assert _initialize_database(database_path) == result.outputs["vector_database"]
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert events[-2:] == [("commit",), ("close",)]
    assert Path(database_path).read_bytes() == before_idempotent

    invalid_paths = (
        "",
        "relative.db",
        "C:drive-relative.db",
        "/cross-host.db",
        r"\\server\share\network.db",
        r"\\.\C:\device.db",
        r"\\?\C:\extended.db",
        r"FiLe:C:\uri.db",
        r"sqlite:C:\uri.db",
        f" {database_path}",
        f"{database_path} ",
        database_path.replace("vectors.DB", "bad\nname.db"),
        database_path.replace("vectors.DB", "bad\x00name.db"),
        str(tmp_path) + r"\\repeated.db",
        str(tmp_path) + r"\.\dot.db",
        str(tmp_path) + r"\..\dot.db",
        str(tmp_path) + r"\bad?.db",
        str(tmp_path) + r"\bad:name.db",
        str(tmp_path) + r"\trailing.\file.db",
        str(tmp_path) + r"\trailing \file.db",
        str(tmp_path) + "\\folder\\",
        str(tmp_path / "wrong.txt"),
        *(
            str(tmp_path) + f"\\{name}\\file.db"
            for name in (
                "CON",
                "prn.txt",
                "AUX",
                "nul.bin",
                "COM1",
                "com9.log",
                "LPT1",
                "lpt9.txt",
            )
        ),
    )
    for invalid_path in invalid_paths:
        with pytest.raises(ValueError) as error:
            _execute_node(
                SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
                inputs={"file_path": invalid_path},
            )
        assert str(error.value) == (
            "file_path must match the approved absolute local SQLite path syntax"
        )
        if invalid_path:
            assert invalid_path not in str(error.value)

    directory_path = tmp_path / "existing.sqlite"
    directory_path.mkdir()
    with pytest.raises(ValueError, match="approved absolute local SQLite path syntax"):
        _execute_node(
            SQLITE_VECTOR_DATABASE_NODE_TYPE_ID,
            inputs={"file_path": str(directory_path)},
        )
    for permitted in ("COM0", "COM10", "LPT0", "LPT10"):
        assert ai_ml_module._validate_sqlite_file_path(
            str(tmp_path) + f"\\{permitted}\\file.sqlite"
        ).endswith("file.sqlite")
    maximum_path = "C:\\" + "a" * (32_768 - 3 - len(".db")) + ".db"
    assert len(maximum_path) == 32_768
    assert ai_ml_module._validate_sqlite_file_path(maximum_path) == maximum_path
    with pytest.raises(ValueError, match="approved absolute local SQLite path syntax"):
        ai_ml_module._validate_sqlite_file_path(maximum_path + "x")

    real_os_name = ai_ml_module.os.name
    try:
        monkeypatch.setattr(ai_ml_module.os, "name", "posix")
        assert ai_ml_module._validate_sqlite_file_path("/tmp/corex.sqlite3") == (
            "/tmp/corex.sqlite3"
        )
        for invalid_posix in (
            "//server/file.db",
            "/tmp//file.db",
            "/tmp/./file.db",
            "/tmp/../file.db",
            r"C:\cross-host.db",
            r"/tmp\cross-host.db",
        ):
            with pytest.raises(ValueError):
                ai_ml_module._validate_sqlite_file_path(invalid_posix)
    finally:
        monkeypatch.setattr(ai_ml_module.os, "name", real_os_name)

    foreign_path = str(tmp_path / "foreign.db")
    connection = real_connect(foreign_path, timeout=5.0, uri=False)
    try:
        connection.execute("CREATE TABLE foreign_table (value INTEGER)")
        connection.commit()
    finally:
        connection.close()
    foreign_bytes = Path(foreign_path).read_bytes()
    with pytest.raises(ValueError) as foreign_error:
        _initialize_database(foreign_path)
    assert str(foreign_error.value) == (
        "SQLite file is not an approved COREX vector database"
    )
    assert Path(foreign_path).read_bytes() == foreign_bytes

    rejected_paths: list[str] = []
    partial_path = str(tmp_path / "partial.db")
    connection = real_connect(partial_path, timeout=5.0, uri=False)
    try:
        connection.execute("PRAGMA application_id = 1129271896")
        connection.commit()
    finally:
        connection.close()
    rejected_paths.append(partial_path)

    version_path = str(tmp_path / "version-drift.db")
    _initialize_database(version_path)
    connection = real_connect(version_path, timeout=5.0, uri=False)
    try:
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    finally:
        connection.close()
    rejected_paths.append(version_path)

    schema_path = str(tmp_path / "schema-drift.db")
    connection = real_connect(schema_path, timeout=5.0, uri=False)
    try:
        connection.execute("PRAGMA application_id = 1129271896")
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "CREATE TABLE corex_vector_collections ("
            "collection_name TEXT PRIMARY KEY NOT NULL, "
            "vector_dimension INTEGER NOT NULL, "
            "distance_metric INTEGER NOT NULL, metadata_json TEXT NOT NULL)"
        )
        connection.commit()
    finally:
        connection.close()
    rejected_paths.append(schema_path)

    extra_schema = (
        "CREATE TABLE extra_table (value INTEGER)",
        "CREATE INDEX extra_index ON corex_vector_collections(vector_dimension)",
        "CREATE VIEW extra_view AS SELECT collection_name FROM corex_vector_collections",
        "CREATE TRIGGER extra_trigger AFTER INSERT ON corex_vector_collections "
        "BEGIN SELECT 1; END",
    )
    for index, statement in enumerate(extra_schema):
        extra_path = str(tmp_path / f"extra-{index}.db")
        _initialize_database(extra_path)
        connection = real_connect(extra_path, timeout=5.0, uri=False)
        try:
            connection.execute(statement)
            connection.commit()
        finally:
            connection.close()
        rejected_paths.append(extra_path)
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    for rejected_path in rejected_paths:
        events.clear()
        with pytest.raises(ValueError) as rejected_error:
            _initialize_database(rejected_path)
        assert str(rejected_error.value) == (
            "SQLite file is not an approved COREX vector database"
        )
        assert rejected_path not in str(rejected_error.value)
        assert events[-2:] == [("rollback",), ("close",)]
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)

    failed_path = str(tmp_path / "retry" / "failed.sqlite3")
    failure_events: list[tuple[object, ...]] = []
    failure_mode = "PRAGMA application_id ="

    def failing_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            failure_events,
            fail_on=failure_mode,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", failing_connect)
    with pytest.raises(RuntimeError) as initialization_error:
        _initialize_database(failed_path)
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(initialization_error.value) == "SQLite vector database operation failed"
    assert failed_path not in str(initialization_error.value)
    assert failure_events[-2:] == [("rollback",), ("close",)]
    assert Path(failed_path).is_file()
    assert _database_facts(failed_path) == ((0,), (0,), (), ())
    assert _initialize_database(failed_path) == _connection_value(failed_path)

    commit_failure_path = str(tmp_path / "retry" / "commit-failed.sqlite3")
    failure_mode = "commit"
    failure_events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", failing_connect)
    with pytest.raises(RuntimeError) as commit_error:
        _initialize_database(commit_failure_path)
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(commit_error.value) == "SQLite vector database operation failed"
    assert commit_failure_path not in str(commit_error.value)
    assert failure_events[-3:] == [("commit",), ("rollback",), ("close",)]
    assert _database_facts(commit_failure_path) == ((0,), (0,), (), ())
    assert _initialize_database(commit_failure_path) == _connection_value(
        commit_failure_path
    )


def test_create_vector_collection_is_transactional_idempotent_and_conflict_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_network(monkeypatch)
    database_path = str(tmp_path / "create.sqlite")
    vector_database = _initialize_database(database_path)
    metadata = {"z": [1, "ö"], "a": {"enabled": True}}
    real_connect = sqlite3.connect
    events: list[tuple[object, ...]] = []

    def tracking_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        events.append(("connect", database, timeout, uri))
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            events,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    result = _execute_node(
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={"vector_database": vector_database},
        properties={
            "collection_name": "Main_Collection",
            "vector_dimension": 384,
            "distance_metric": "Cosine",
            "additional_metadata": metadata,
        },
    )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    collection = result.outputs["vector_collection"]
    assert collection == _collection_value(database_path, "Main_Collection")
    assert type(collection.payload) is dict
    assert type(collection.payload["connection"]) is dict
    assert not isinstance(collection.payload["connection"], TypedInlineValue)
    statements = [event[1] for event in events if event[0] == "execute"]
    select_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT vector_dimension")
    )
    insert_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("INSERT INTO corex_vector_collections")
    )
    assert statements[0] == "BEGIN IMMEDIATE"
    assert (
        statements.index("PRAGMA table_info(corex_vector_collections)") < select_index
    )
    assert select_index < insert_index
    assert events[-2:] == [("commit",), ("close",)]
    parameterized = [
        event
        for event in events
        if event[0] == "execute" and "collection_name = ?" in event[1]
    ]
    assert parameterized[-1][2] == ("Main_Collection",)
    assert "Main_Collection" not in parameterized[-1][1]

    connection = real_connect(database_path, timeout=5.0, uri=False)
    try:
        row = connection.execute(
            "SELECT collection_name, vector_dimension, distance_metric, metadata_json "
            "FROM corex_vector_collections WHERE collection_name = ?",
            ("Main_Collection",),
        ).fetchone()
    finally:
        connection.close()
    assert row == (
        "Main_Collection",
        384,
        0,
        '{"a":{"enabled":true},"z":[1,"ö"]}',
    )
    metadata["a"]["enabled"] = False
    before_idempotent = Path(database_path).read_bytes()
    events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    idempotent = _execute_node(
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={
            "vector_database": vector_database,
            "collection_name": "Main_Collection",
            "vector_dimension": 384,
            "distance_metric": "Cosine",
            "additional_metadata": {"a": {"enabled": True}, "z": [1, "ö"]},
        },
    )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert idempotent.outputs["vector_collection"] == collection
    assert events[-2:] == [("commit",), ("close",)]
    assert Path(database_path).read_bytes() == before_idempotent

    conflict_events: list[tuple[object, ...]] = []

    def conflict_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            conflict_events,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", conflict_connect)
    with pytest.raises(ValueError) as conflict_error:
        _execute_node(
            CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_database": vector_database,
                "collection_name": "Main_Collection",
                "vector_dimension": 768,
                "distance_metric": "Cosine",
                "additional_metadata": {"a": {"enabled": True}, "z": [1, "ö"]},
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(conflict_error.value) == (
        "vector collection already exists with different metadata"
    )
    assert "Main_Collection" not in str(conflict_error.value)
    assert conflict_events[-2:] == [("rollback",), ("close",)]
    assert Path(database_path).read_bytes() == before_idempotent

    failure_events: list[tuple[object, ...]] = []
    failure_mode = "INSERT INTO corex_vector_collections"

    def failing_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            failure_events,
            fail_on=failure_mode,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", failing_connect)
    with pytest.raises(RuntimeError) as insertion_error:
        _execute_node(
            CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_database": vector_database,
                "collection_name": "RetryCollection",
                "vector_dimension": 3,
                "distance_metric": "Euclidean",
                "additional_metadata": {},
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(insertion_error.value) == "SQLite vector database operation failed"
    assert failure_events[-2:] == [("rollback",), ("close",)]

    failure_mode = "commit"
    failure_events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", failing_connect)
    with pytest.raises(RuntimeError) as commit_error:
        _execute_node(
            CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_database": vector_database,
                "collection_name": "CommitFailureCollection",
                "vector_dimension": 3,
                "distance_metric": "Euclidean",
                "additional_metadata": {},
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(commit_error.value) == "SQLite vector database operation failed"
    assert "CommitFailureCollection" not in str(commit_error.value)
    assert failure_events[-3:] == [("commit",), ("rollback",), ("close",)]

    euclidean = _execute_node(
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={
            "vector_database": vector_database,
            "collection_name": "EuclideanCollection",
            "vector_dimension": 3,
            "distance_metric": "Euclidean",
            "additional_metadata": {},
        },
    )
    assert euclidean.outputs["vector_collection"] == _collection_value(
        database_path, "EuclideanCollection"
    )
    connection = real_connect(database_path, timeout=5.0, uri=False)
    try:
        assert connection.execute(
            "SELECT distance_metric FROM corex_vector_collections "
            "WHERE collection_name = ?",
            ("EuclideanCollection",),
        ).fetchone() == (1,)
        assert (
            connection.execute(
                "SELECT 1 FROM corex_vector_collections WHERE collection_name = ?",
                ("RetryCollection",),
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM corex_vector_collections WHERE collection_name = ?",
                ("CommitFailureCollection",),
            ).fetchone()
            is None
        )
    finally:
        connection.close()

    invalid_inputs = (
        (
            {"collection_name": "bad name"},
            "collection_name must match [A-Za-z][A-Za-z0-9_-]{0,63}",
        ),
        (
            {"vector_dimension": True},
            "vector_dimension must be an integer from 1 to 65536",
        ),
        (
            {"vector_dimension": 0},
            "vector_dimension must be an integer from 1 to 65536",
        ),
        (
            {"vector_dimension": 65_537},
            "vector_dimension must be an integer from 1 to 65536",
        ),
        (
            {"distance_metric": "cosine"},
            'distance_metric must be exactly "Cosine" or "Euclidean"',
        ),
        (
            {"distance_metric": 0},
            'distance_metric must be exactly "Cosine" or "Euclidean"',
        ),
    )
    for replacement, message in invalid_inputs:
        inputs = {
            "vector_database": vector_database,
            "collection_name": "ValidName",
            "vector_dimension": 3,
            "distance_metric": "Cosine",
            "additional_metadata": {},
            **replacement,
        }
        with pytest.raises(ValueError) as validation_error:
            _execute_node(CREATE_VECTOR_COLLECTION_NODE_TYPE_ID, inputs=inputs)
        assert str(validation_error.value) == message

    deep_metadata: dict[str, object] = {}
    cursor = deep_metadata
    for _ in range(34):
        nested: dict[str, object] = {}
        cursor["nested"] = nested
        cursor = nested

    class DictSubclass(dict):
        pass

    invalid_metadata = (
        DictSubclass({}),
        {"api_key": "secret"},
        {"path": str(tmp_path / "secret.txt")},
        {"value": float("nan")},
        {"__ea_runtime_value__": "secret_data"},
        deep_metadata,
        {"value": "x" * 65_536},
        {"value": object()},
    )
    for metadata_value in invalid_metadata:
        with pytest.raises(ValueError) as metadata_error:
            _execute_node(
                CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
                inputs={
                    "vector_database": vector_database,
                    "collection_name": "MetadataCollection",
                    "vector_dimension": 3,
                    "distance_metric": "Cosine",
                    "additional_metadata": metadata_value,
                },
            )
        assert str(metadata_error.value) == (
            "additional_metadata must be a bounded non-sensitive GraphDictionary"
        )
        assert database_path not in str(metadata_error.value)

    drift_path = str(tmp_path / "create-schema-drift.db")
    drift_database = _initialize_database(drift_path)
    connection = real_connect(drift_path, timeout=5.0, uri=False)
    try:
        connection.execute("CREATE TABLE extra_table (value INTEGER)")
        connection.commit()
    finally:
        connection.close()
    drift_events: list[tuple[object, ...]] = []

    def drift_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            drift_events,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", drift_connect)
    with pytest.raises(ValueError) as schema_error:
        _execute_node(
            CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_database": drift_database,
                "collection_name": "SchemaDrift",
                "vector_dimension": 3,
                "distance_metric": "Cosine",
                "additional_metadata": {},
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert (
        str(schema_error.value)
        == "SQLite file is not an approved COREX vector database"
    )
    assert drift_events[-2:] == [("rollback",), ("close",)]


def test_inspect_vector_collection_returns_exact_outputs_and_rejects_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_network(monkeypatch)
    database_path = str(tmp_path / "inspect.db")
    vector_database = _initialize_database(database_path)
    create_result = _execute_node(
        CREATE_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={
            "vector_database": vector_database,
            "collection_name": "InspectMe",
            "vector_dimension": 1536,
            "distance_metric": "Euclidean",
            "additional_metadata": {"purpose": "test", "rank": 1},
        },
    )
    vector_collection = create_result.outputs["vector_collection"]
    real_connect = sqlite3.connect
    events: list[tuple[object, ...]] = []
    failure_mode = ""

    def tracking_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        events.append(("connect", database, timeout, uri))
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            events,
            fail_on=failure_mode,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    result = _execute_node(
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={"vector_collection": vector_collection},
    )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert result.outputs == {
        "name": "InspectMe",
        "record_count": 0,
        "vector_dimension": 1536,
        "distance_metric": "Euclidean",
        "metadata": {"purpose": "test", "rank": 1},
    }
    assert type(result.outputs["record_count"]) is int
    statements = [event[1] for event in events if event[0] == "execute"]
    assert statements[0] == "BEGIN"
    select_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT collection_name, vector_dimension")
    )
    assert (
        statements.index("PRAGMA table_info(corex_vector_collections)") < select_index
    )
    assert not any(
        statement.startswith(
            ("INSERT", "UPDATE", "DELETE", "CREATE", "PRAGMA application_id =")
        )
        for statement in statements
    )
    assert events[-2:] == [("commit",), ("close",)]
    result.outputs["metadata"]["rank"] = 2
    assert _execute_node(
        INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
        inputs={"vector_collection": vector_collection},
    ).outputs["metadata"] == {"purpose": "test", "rank": 1}

    missing_events: list[tuple[object, ...]] = []

    def missing_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            missing_events,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", missing_connect)
    with pytest.raises(ValueError) as missing_error:
        _execute_node(
            INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_collection": _collection_value(
                    database_path, "MissingCollection"
                )
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(missing_error.value) == "vector collection was not found"
    assert "MissingCollection" not in str(missing_error.value)
    assert missing_events[-2:] == [("rollback",), ("close",)]

    connection = real_connect(database_path, timeout=5.0, uri=False)
    try:
        connection.execute(
            "INSERT INTO corex_vector_collections "
            "(collection_name, vector_dimension, distance_metric, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            ("BadMetadata", 3, 0, '{"z": 1}'),
        )
        connection.commit()
    finally:
        connection.close()
    events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    with pytest.raises(RuntimeError) as row_error:
        _execute_node(
            INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={
                "vector_collection": _collection_value(database_path, "BadMetadata")
            },
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(row_error.value) == "SQLite vector database operation failed"
    assert all(
        secret not in str(row_error.value)
        for secret in (database_path, "BadMetadata", '{"z": 1}')
    )
    assert events[-2:] == [("rollback",), ("close",)]

    failure_mode = "commit"
    events.clear()
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", tracking_connect)
    with pytest.raises(RuntimeError) as commit_error:
        _execute_node(
            INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={"vector_collection": vector_collection},
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert str(commit_error.value) == "SQLite vector database operation failed"
    assert all(
        secret not in str(commit_error.value) for secret in (database_path, "InspectMe")
    )
    assert events[-3:] == [("commit",), ("rollback",), ("close",)]

    connection = real_connect(database_path, timeout=5.0, uri=False)
    try:
        connection.execute(
            "CREATE VIEW extra_view AS SELECT collection_name "
            "FROM corex_vector_collections"
        )
        connection.commit()
    finally:
        connection.close()
    drift_events: list[tuple[object, ...]] = []

    def drift_connect(
        database: str,
        *,
        timeout: float,
        uri: bool,
    ) -> _TrackingConnection:
        return _TrackingConnection(
            real_connect(database, timeout=timeout, uri=uri),
            drift_events,
        )

    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", drift_connect)
    with pytest.raises(ValueError) as schema_error:
        _execute_node(
            INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
            inputs={"vector_collection": vector_collection},
        )
    monkeypatch.setattr(ai_ml_module.sqlite3, "connect", real_connect)
    assert (
        str(schema_error.value)
        == "SQLite file is not an approved COREX vector database"
    )
    assert database_path not in str(schema_error.value)
    assert drift_events[-2:] == [("rollback",), ("close",)]

    invalid_values = (
        None,
        _connection_value(database_path),
        TypedInlineValue(VECTOR_COLLECTION_DATA_TYPE_ID, 2, vector_collection.payload),
        vector_collection.payload,
    )
    for invalid_value in invalid_values:
        with pytest.raises(ValueError) as input_error:
            _execute_node(
                INSPECT_VECTOR_COLLECTION_NODE_TYPE_ID,
                inputs={"vector_collection": invalid_value},
            )
        assert str(input_error.value) == "Vector collection input is invalid"
        assert database_path not in str(input_error.value)
