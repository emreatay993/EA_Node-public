from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.builtin_functions.security import SOURCE as SECURITY_SOURCE
from ea_node_editor.nodes.builtins import security_contracts as security_module
from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.nodes.builtins.security_contracts import (
    AUTHENTICATION_DATA_TYPE_ID,
    COREX_SECURITY_CONTRACT_MANIFEST,
    COREX_SECURITY_DATA_TYPES,
    COREX_SECURITY_OWNER_ID,
    COREX_SECURITY_OWNER_VERSION,
    WINDOWS_AUTHENTICATION_UNAVAILABLE_ERROR,
    WINDOWS_AUTHENTICATION_TYPE_ID,
    WINDOWS_IDENTITY_DATA_TYPE_ID,
    WINDOWS_IDENTITY_HANDLE_KIND,
    execute_windows_authentication,
    is_windows_identity_handle,
)
from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalogError,
    RuntimeHandleRef,
    TypedInlineValue,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


class _HandleSubclass(RuntimeHandleRef):
    pass


class _HostileMapping(Mapping[object, object]):
    def __getitem__(self, key: object) -> object:
        raise AssertionError("mapping-credential-secret")

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("mapping-credential-secret")

    def __len__(self) -> int:
        raise AssertionError("mapping-credential-secret")


class _HostileObject:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError("object-credential-secret")


class _HostileString(str):
    def __eq__(self, other: object) -> bool:
        raise AssertionError("string-credential-secret")


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register_plugin_bundle(
        COREX_SECURITY_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_SECURITY_OWNER_ID,
        owner_version=COREX_SECURITY_OWNER_VERSION,
    )
    return registry


def _services() -> WorkerServices:
    registry = _registry()
    registry.freeze()
    services = WorkerServices()
    services.bind_data_types(registry.data_types)
    return services


def _context(
    services: WorkerServices,
    *,
    run_id: str = "security-node-run",
    logs: list[tuple[str, str]] | None = None,
) -> ExecutionContext:
    captured_logs = logs if logs is not None else []
    return ExecutionContext(
        run_id=run_id,
        node_id="windows-authentication-node",
        workspace_id="security-workspace",
        inputs={},
        properties={},
        emit_log=lambda level, message: captured_logs.append((level, message)),
        worker_services=services,
    )


def _patch_windows_user(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(security_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(security_module.getpass, "getuser", lambda: value)


def _identity_ref(
    *,
    data_type_id: str = WINDOWS_IDENTITY_DATA_TYPE_ID,
    schema_version: int = 1,
    kind: str = WINDOWS_IDENTITY_HANDLE_KIND,
    metadata: dict[str, object] | None = None,
) -> RuntimeHandleRef:
    return RuntimeHandleRef(
        data_type_id=data_type_id,
        schema_version=schema_version,
        handle_id="identity-001",
        kind=kind,
        owner_scope="run:security-test",
        worker_generation=3,
        metadata={} if metadata is None else metadata,
    )


def test_exact_identity_ref_validates_and_round_trips_without_metadata() -> None:
    registry = _registry()
    identity = _identity_ref()
    assert is_windows_identity_handle(identity)
    registry.data_types.validate_carrier(WINDOWS_IDENTITY_DATA_TYPE_ID, identity)
    registry.data_types.validate_carrier(GRAPH_DATA_TYPE_ID, identity)

    event = NodeSettledEvent(
        outputs={
            "identity": SettledPortResult(
                status="value",
                value=DataTree.from_item(identity),
            )
        }
    )
    wire = json.loads(json.dumps(event_to_dict(event, catalog=registry.data_types)))
    item = wire["outputs"]["identity"]["value"]["branches"][0]["items"][0]
    assert item == {
        "__ea_runtime_value__": "handle_ref",
        "data_type_id": WINDOWS_IDENTITY_DATA_TYPE_ID,
        "schema_version": 1,
        "handle_id": "identity-001",
        "kind": WINDOWS_IDENTITY_HANDLE_KIND,
        "owner_scope": "run:security-test",
        "worker_generation": 3,
    }
    assert "metadata" not in item
    restored = dict_to_event(wire, catalog=registry.data_types)
    assert restored.outputs["identity"].value == DataTree.from_item(identity)


def test_abstract_authentication_cannot_be_a_concrete_runtime_handle() -> None:
    registry = _registry()
    authentication = _identity_ref(data_type_id=AUTHENTICATION_DATA_TYPE_ID)
    assert not COREX_SECURITY_DATA_TYPES[0].validate_item(authentication)
    with pytest.raises(DataTypeCatalogError, match="must be concrete"):
        registry.data_types.validate_carrier(
            AUTHENTICATION_DATA_TYPE_ID,
            authentication,
        )
    with pytest.raises(DataTypeCatalogError, match="not assignable"):
        registry.data_types.validate_carrier(
            AUTHENTICATION_DATA_TYPE_ID,
            _identity_ref(),
        )
    registry.data_types.validate_carrier(AUTHENTICATION_DATA_TYPE_ID, None)
    registry.data_types.validate_carrier(WINDOWS_IDENTITY_DATA_TYPE_ID, None)


def test_identity_validator_rejects_forged_wrong_and_non_handle_values() -> None:
    valid = _identity_ref()
    subclass = _HandleSubclass(
        data_type_id=valid.data_type_id,
        schema_version=valid.schema_version,
        handle_id=valid.handle_id,
        kind=valid.kind,
        owner_scope=valid.owner_scope,
        worker_generation=valid.worker_generation,
    )
    invalid = (
        _identity_ref(data_type_id=AUTHENTICATION_DATA_TYPE_ID),
        _identity_ref(schema_version=2),
        _identity_ref(kind="corex.authentication"),
        _identity_ref(metadata={"label": "credential-string-secret"}),
        TypedInlineValue(WINDOWS_IDENTITY_DATA_TYPE_ID, 1, {}),
        "DOMAIN\\username-secret",
        "S-1-5-21-123456789-secret",
        987654321,
        {"username": "mapping-username-secret"},
        object(),
        subclass,
    )
    assert all(not is_windows_identity_handle(value) for value in invalid)

    catalog = _registry().data_types
    for value in invalid:
        with pytest.raises(DataTypeCatalogError):
            catalog.validate_carrier(WINDOWS_IDENTITY_DATA_TYPE_ID, value)


def test_hostile_mappings_objects_and_forged_fields_are_not_inspected() -> None:
    assert not is_windows_identity_handle(_HostileMapping())
    assert not is_windows_identity_handle(_HostileObject())

    hostile_metadata = _identity_ref()
    object.__setattr__(hostile_metadata, "metadata", _HostileMapping())
    assert not is_windows_identity_handle(hostile_metadata)

    hostile_kind = _identity_ref()
    object.__setattr__(
        hostile_kind,
        "kind",
        _HostileString(WINDOWS_IDENTITY_HANDLE_KIND),
    )
    assert not is_windows_identity_handle(hostile_kind)


@pytest.mark.parametrize(
    "value, secret",
    (
        ("DOMAIN\\credential-username", "credential-username"),
        ("S-1-5-21-credential-sid", "credential-sid"),
        ({"identity": "credential-mapping"}, "credential-mapping"),
        (
            _identity_ref(metadata={"label": "credential-metadata"}),
            "credential-metadata",
        ),
    ),
)
def test_rejection_errors_are_generic_and_do_not_leak_values(
    value: object,
    secret: str,
) -> None:
    with pytest.raises(DataTypeCatalogError) as exc_info:
        _registry().data_types.validate_carrier(
            WINDOWS_IDENTITY_DATA_TYPE_ID,
            value,
        )
    message = str(exc_info.value)
    assert secret not in message
    assert "DOMAIN\\" not in message
    assert "S-1-5-21-" not in message
    assert "credential-" not in message


def test_windows_authentication_function_spec_matches_frozen_catalog() -> None:
    (declaration,) = discover_plugin_declarations(
        SECURITY_SOURCE,
        filename="builtin_functions/security.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    golden = load_current_repo_owned_catalog()
    expected = next(
        row["spec"]
        for row in golden
        if row["spec"]["type_id"] == WINDOWS_AUTHENTICATION_TYPE_ID
    )

    assert json.loads(json.dumps(asdict(declaration.spec))) == expected


def test_windows_authentication_returns_fresh_run_scoped_opaque_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_windows_user(monkeypatch, "  DOMAIN\\alice  ")
    services = _services()
    logs: list[tuple[str, str]] = []
    ctx = _context(services, logs=logs)

    first = execute_windows_authentication(ctx)
    second = execute_windows_authentication(ctx)

    assert set(first) == {"authentication", "current_user"}
    assert first["current_user"] == "DOMAIN\\alice"
    assert second["current_user"] == "DOMAIN\\alice"
    first_ref = first["authentication"]
    second_ref = second["authentication"]
    assert type(first_ref) is RuntimeHandleRef
    assert type(second_ref) is RuntimeHandleRef
    assert first_ref != second_ref
    assert first_ref.handle_id != second_ref.handle_id
    assert first_ref.data_type_id == WINDOWS_IDENTITY_DATA_TYPE_ID
    assert first_ref.schema_version == 1
    assert first_ref.kind == WINDOWS_IDENTITY_HANDLE_KIND
    assert first_ref.owner_scope == "run:security-node-run"
    assert first_ref.metadata == {}
    assert second_ref.metadata == {}
    first_identity = ctx.resolve_handle(
        first_ref,
        expected_data_type=WINDOWS_IDENTITY_DATA_TYPE_ID,
        expected_kind=WINDOWS_IDENTITY_HANDLE_KIND,
    )
    second_identity = ctx.resolve_handle(
        second_ref,
        expected_data_type=WINDOWS_IDENTITY_DATA_TYPE_ID,
        expected_kind=WINDOWS_IDENTITY_HANDLE_KIND,
    )
    assert type(first_identity) is object
    assert type(second_identity) is object
    assert first_identity is not second_identity
    assert services.handle_registry.active_handle_count == 2
    assert logs == []

    serialized = first_ref.to_payload(catalog=services.data_types)
    assert "metadata" not in serialized
    assert "DOMAIN\\alice" not in json.dumps(serialized)
    record = services.handle_registry._records[first_ref.handle_id]
    assert record.metadata == {}
    assert record.dispose is None


@pytest.mark.parametrize(
    "failure_case",
    (
        "unsupported_platform",
        "lookup_exception",
        "non_string",
        "empty",
        "control_character",
        "too_long",
    ),
)
def test_windows_authentication_failures_are_redacted_and_register_nothing(
    monkeypatch: pytest.MonkeyPatch,
    failure_case: str,
) -> None:
    secret = r"C:\private\DOMAIN\credential-user"
    if failure_case == "unsupported_platform":
        monkeypatch.setattr(
            security_module.platform,
            "system",
            lambda: "not-windows-secret-platform",
        )

        def getuser() -> str:
            raise AssertionError("getpass must not run off Windows")

    elif failure_case == "lookup_exception":
        monkeypatch.setattr(
            security_module.platform,
            "system",
            lambda: "Windows",
        )

        def getuser() -> str:
            raise OSError(secret)

    else:
        invalid_values = {
            "non_string": {"user": secret},
            "empty": " \t ",
            "control_character": f"DOMAIN\\user\n{secret}",
            "too_long": secret * 32,
        }
        _patch_windows_user(monkeypatch, invalid_values[failure_case])
        getuser = security_module.getpass.getuser

    monkeypatch.setattr(security_module.getpass, "getuser", getuser)
    services = _services()
    ctx = _context(services)

    with pytest.raises(RuntimeError) as exc_info:
        execute_windows_authentication(ctx)

    message = str(exc_info.value)
    assert message == WINDOWS_AUTHENTICATION_UNAVAILABLE_ERROR
    assert len(message) < 64
    assert secret not in message
    assert "credential" not in message.lower()
    assert "platform" not in message.lower()
    assert services.handle_registry.active_handle_count == 0


def test_windows_identity_resolution_rejects_forged_and_stale_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_windows_user(monkeypatch, "alice")
    services = _services()
    ctx = _context(services, run_id="run-a")
    ref = execute_windows_authentication(ctx)["authentication"]
    identity = ctx.resolve_handle(
        ref,
        expected_data_type=WINDOWS_IDENTITY_DATA_TYPE_ID,
        expected_kind=WINDOWS_IDENTITY_HANDLE_KIND,
    )
    assert type(identity) is object

    rejected = (
        replace(ref, handle_id="forged-handle"),
        replace(ref, kind="corex.wrong_identity"),
        replace(ref, data_type_id=AUTHENTICATION_DATA_TYPE_ID),
        replace(ref, schema_version=2),
        replace(ref, worker_generation=ref.worker_generation + 1),
        replace(ref, owner_scope="run:run-b"),
    )
    for candidate in rejected:
        with pytest.raises(StaleHandleError):
            ctx.resolve_handle(candidate)

    assert ctx.release_handle(ref)
    assert services.handle_registry.active_handle_count == 0
    with pytest.raises(StaleHandleError):
        ctx.resolve_handle(ref)


def test_windows_identity_run_cleanup_prevents_cross_run_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_windows_user(monkeypatch, "alice")
    services = _services()
    first_context = _context(services, run_id="run-a")
    ref = execute_windows_authentication(first_context)["authentication"]
    assert services.handle_registry.active_handle_count == 1

    assert services.cleanup_run("run-a") == 1
    assert services.handle_registry.active_handle_count == 0
    second_context = _context(services, run_id="run-b")
    with pytest.raises(StaleHandleError):
        second_context.resolve_handle(ref)
