from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import replace

import pytest

import ea_node_editor.execution.registry_agreement as registry_agreement
from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.external_python_client import ExternalPythonExecutionClient
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.client_common import _ExecutionClientCommon
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
)
from ea_node_editor.execution.registry_agreement import (
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
    PythonFunctionRef,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import DataTypeCatalog, DataTypeCatalogError

_BUNDLE_DIGEST = "a" * 64
_SOURCE_DIGEST = "b" * 64
_PLUGIN_FINGERPRINT = "c" * 64


def _contract_factory():
    return None


def _resolve_contract_a(spec, _properties):  # noqa: ANN001
    return replace(spec, instance_spec_resolver=None)


def _resolve_contract_b(spec, _properties):  # noqa: ANN001
    return replace(spec, instance_spec_resolver=None)


def _snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        schema_version=1,
        active_workspace_id="ws",
        workspace_order=("ws",),
        workspaces=(RuntimeWorkspace(document_fields={"workspace_id": "ws"}),),
    )


def _bundle(generation_root) -> PluginBundleRef:  # noqa: ANN001
    generation = generation_root / _BUNDLE_DIGEST
    generation.mkdir(parents=True, exist_ok=True)
    function_ref = PythonFunctionRef(
        bundle_id="plugin:file:scale",
        bundle_digest=_BUNDLE_DIGEST,
        module_relative_path="scale.py",
        function_name="scale",
        source_digest=_SOURCE_DIGEST,
    )
    return PluginBundleRef(
        owner_id="plugin:file:scale",
        version="0.0.0",
        generation_id=_BUNDLE_DIGEST,
        bundle_digest=_BUNDLE_DIGEST,
        approved_generation_root=str(generation.resolve()),
        functions=(function_ref,),
    )


def _frozen_catalog() -> DataTypeCatalog:
    registry = NodeRegistry()
    registry.freeze()
    return registry.data_types


def test_start_run_plugin_bundle_round_trips_with_combined_fingerprint(
    tmp_path,
    monkeypatch,
) -> None:
    generation_root = tmp_path / "plugin_generations"
    monkeypatch.setattr(
        registry_agreement,
        "plugin_generations_dir",
        lambda: generation_root,
    )
    bundle = _bundle(generation_root)
    catalog = _frozen_catalog()
    expected_runtime = runtime_registry_fingerprint(
        catalog.fingerprint(),
        _PLUGIN_FINGERPRINT,
    )
    command = StartRunCommand(
        run_id="run-plugin",
        workspace_id="ws",
        runtime_snapshot=_snapshot(),
        plugin_bundles=(bundle,),
        plugin_fingerprint=_PLUGIN_FINGERPRINT,
        runtime_registry_fingerprint=expected_runtime,
        registry_contract_fingerprint="d" * 64,
        addon_runtime_config=(("mars.corex", False),),
    )

    payload = command_to_dict(command, catalog=catalog)
    restored = dict_to_command(json.loads(json.dumps(payload)), catalog=catalog)

    assert restored.plugin_bundles == (bundle,)
    assert restored.plugin_fingerprint == _PLUGIN_FINGERPRINT
    assert restored.runtime_registry_fingerprint == expected_runtime
    assert restored.registry_contract_fingerprint == "d" * 64
    assert restored.addon_runtime_config == (("mars.corex", False),)
    assert payload["addon_runtime_config"] == [
        {"addon_id": "mars.corex", "enabled": False}
    ]
    assert payload["plugin_bundles"][0]["functions"][0] == {
        "bundle_id": "plugin:file:scale",
        "bundle_digest": _BUNDLE_DIGEST,
        "module_relative_path": "scale.py",
        "function_name": "scale",
        "source_digest": _SOURCE_DIGEST,
        "is_async": False,
    }
    assert "source" not in payload["plugin_bundles"][0]
    assert "source_code" not in json.dumps(payload)


def test_plugin_protocol_rejects_path_escape_bounds_and_fingerprint_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    generation_root = tmp_path / "plugin_generations"
    monkeypatch.setattr(
        registry_agreement,
        "plugin_generations_dir",
        lambda: generation_root,
    )
    catalog = _frozen_catalog()
    payload = command_to_dict(
        StartRunCommand(
            run_id="run-plugin",
            workspace_id="ws",
            runtime_snapshot=_snapshot(),
            plugin_bundles=(_bundle(generation_root),),
            plugin_fingerprint=_PLUGIN_FINGERPRINT,
        ),
        catalog=catalog,
    )

    escaped = copy.deepcopy(payload)
    outside = tmp_path / "outside" / _BUNDLE_DIGEST
    outside.mkdir(parents=True)
    escaped["plugin_bundles"][0]["approved_generation_root"] = str(outside)
    with pytest.raises(ValueError, match="direct immutable generation child"):
        dict_to_command(escaped, catalog=catalog)

    mismatched = copy.deepcopy(payload)
    mismatched["runtime_registry_fingerprint"] = "d" * 64
    with pytest.raises(ValueError, match="does not match"):
        dict_to_command(mismatched, catalog=catalog)

    oversized = copy.deepcopy(payload)
    oversized["plugin_bundles"] *= 129
    with pytest.raises(ValueError, match="too many bundles"):
        dict_to_command(oversized, catalog=catalog)

    too_many_functions = copy.deepcopy(payload)
    too_many_functions["plugin_bundles"][0]["functions"] = [{}] * 4097
    with pytest.raises(ValueError, match="too many functions"):
        dict_to_command(too_many_functions, catalog=catalog)

    missing_agreement = copy.deepcopy(payload)
    missing_agreement.pop("plugin_fingerprint")
    with pytest.raises(ValueError, match="requires plugin agreement fields"):
        dict_to_command(missing_agreement, catalog=catalog)

    malformed_contract = copy.deepcopy(payload)
    malformed_contract["registry_contract_fingerprint"] = "not-a-digest"
    with pytest.raises(ValueError, match="registry_contract_fingerprint"):
        dict_to_command(malformed_contract, catalog=catalog)

    malformed_config = copy.deepcopy(payload)
    malformed_config["addon_runtime_config"] = [
        {"addon_id": "mars.corex", "enabled": "yes"}
    ]
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        dict_to_command(malformed_config, catalog=catalog)

    path_config = copy.deepcopy(payload)
    path_config["addon_runtime_config"] = [
        {"addon_id": "C:/private/addon", "enabled": True}
    ]
    with pytest.raises(ValueError, match="path-free logical identifier"):
        dict_to_command(path_config, catalog=catalog)

    for field_name, invalid_value in (
        ("plugin_bundles", None),
        ("plugin_fingerprint", ""),
        ("runtime_registry_fingerprint", ""),
    ):
        invalid_agreement = copy.deepcopy(payload)
        invalid_agreement[field_name] = invalid_value
        with pytest.raises(ValueError):
            dict_to_command(invalid_agreement, catalog=catalog)

    long_reason = copy.deepcopy(payload)
    long_reason["plugin_bundles"][0]["unavailable_reason"] = "x" * 2049
    with pytest.raises(ValueError, match="too long"):
        dict_to_command(long_reason, catalog=catalog)


class _RecordingGenerationClient(_ExecutionClientCommon):
    def __init__(self) -> None:
        self._data_types = None
        self._catalog_generation_fingerprint = ""
        self._plugin_bundles = ()
        self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
        self._runtime_registry_generation_fingerprint = ""
        self._catalog_generation_token = 0
        self._physical_generation_token = 0
        self._accepted_physical_generation_token = 0
        self._run_generation_tokens = {}
        self._start_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._viewer_request_lock = threading.Lock()
        self._pending_viewer_requests = {}
        self._viewer_session_ids = set()
        self._viewer_session_generations = {}
        self._active_run_id = ""
        self._active_workspace_id = ""
        self._start_run_pending_id = ""
        self._run_thread = None
        self.recycled = 0

    def _viewer_generation_is_live(self) -> bool:
        return False

    def _recycle_catalog_generation(self) -> None:
        self.recycled += 1


def _bare_execution_client(client_type):  # noqa: ANN001
    client = object.__new__(client_type)
    client._start_lock = threading.RLock()  # noqa: SLF001
    client._state_lock = threading.Lock()  # noqa: SLF001
    client._viewer_request_lock = threading.Lock()  # noqa: SLF001
    client._active_run_id = ""  # noqa: SLF001
    client._start_run_pending_id = ""  # noqa: SLF001
    client._run_thread = None  # noqa: SLF001
    client._pending_viewer_requests = {}  # noqa: SLF001
    client._viewer_session_ids = set()  # noqa: SLF001
    return client


@pytest.mark.parametrize(
    "client_type",
    (
        ProcessExecutionClient,
        ExternalPythonExecutionClient,
        TrustedInProcessExecutionClient,
    ),
)
@pytest.mark.parametrize(
    ("state_field", "state_value", "error"),
    (
        ("_active_run_id", "run-active", "active run"),
        ("_start_run_pending_id", "run-pending", "active run"),
        ("_pending_viewer_requests", {"viewer": object()}, "viewer requests"),
        ("_viewer_session_ids", {("ws", "session")}, "viewer requests"),
    ),
)
def test_concrete_client_registry_preflight_rejects_live_state(
    client_type,
    state_field,
    state_value,
    error,
) -> None:  # noqa: ANN001
    client = _bare_execution_client(client_type)
    setattr(client, state_field, state_value)

    with pytest.raises(DataTypeCatalogError, match=error):
        client.assert_registry_replaceable()


def test_trusted_client_registry_preflight_rejects_live_run_thread() -> None:
    client = _bare_execution_client(TrustedInProcessExecutionClient)
    client._run_thread = threading.current_thread()  # noqa: SLF001

    with pytest.raises(DataTypeCatalogError, match="active run"):
        client.assert_registry_replaceable()


def test_idle_client_registry_preflight_and_same_or_different_replacement() -> None:
    original = _registry_with_fingerprint(EMPTY_PLUGIN_FINGERPRINT)
    replacement = _registry_with_fingerprint(_PLUGIN_FINGERPRINT)
    client = _RecordingGenerationClient()
    assert client._prepare_start_run(  # noqa: SLF001
        "run-pin",
        "ws",
        original.data_types,
        original.plugin_bundle_refs(),
        original.plugin_fingerprint(),
        original.contract_fingerprint(),
        original.addon_runtime_config(),
    )
    client._release_start_run("run-pin")  # noqa: SLF001

    client.assert_registry_replaceable()
    assert client.replace_registry(original) is False
    assert client.replace_registry(replacement) is True
    assert client.recycled == 1


@pytest.mark.parametrize(
    ("state_field", "state_value", "error"),
    (
        ("_start_run_pending_id", "run-raced", "active run"),
        ("_pending_viewer_requests", {"viewer": object()}, "viewer requests"),
    ),
)
def test_client_registry_replace_rechecks_after_preflight_race(
    state_field,
    state_value,
    error,
) -> None:  # noqa: ANN001
    original = _registry_with_fingerprint(EMPTY_PLUGIN_FINGERPRINT)
    replacement = _registry_with_fingerprint(_PLUGIN_FINGERPRINT)
    client = _RecordingGenerationClient()
    assert client._prepare_start_run(  # noqa: SLF001
        "run-pin",
        "ws",
        original.data_types,
        original.plugin_bundle_refs(),
        original.plugin_fingerprint(),
        original.contract_fingerprint(),
        original.addon_runtime_config(),
    )
    client._release_start_run("run-pin")  # noqa: SLF001
    client.assert_registry_replaceable()

    setattr(client, state_field, state_value)
    with pytest.raises(DataTypeCatalogError, match=error):
        client.replace_registry(replacement)
    assert client.recycled == 0


def test_plugin_fingerprint_change_recycles_client_generation() -> None:
    catalog = _frozen_catalog()
    client = _RecordingGenerationClient()

    assert client._prepare_start_run(  # noqa: SLF001
        "run-1",
        "ws",
        catalog,
        (),
        _PLUGIN_FINGERPRINT,
        "1" * 64,
        (),
    )
    first_token = client._catalog_generation_token_value()  # noqa: SLF001
    client._release_start_run("run-1")  # noqa: SLF001

    assert client._prepare_start_run(  # noqa: SLF001
        "run-2",
        "ws",
        catalog,
        (),
        _PLUGIN_FINGERPRINT,
        "1" * 64,
        (),
    )
    assert client.recycled == 0
    assert client._catalog_generation_token_value() == first_token  # noqa: SLF001
    client._release_start_run("run-2")  # noqa: SLF001

    assert client._prepare_start_run(  # noqa: SLF001
        "run-3",
        "ws",
        catalog,
        (),
        "d" * 64,
        "2" * 64,
        (),
    )
    assert client.recycled == 1
    assert client._catalog_generation_token_value() > first_token  # noqa: SLF001
    assert client._runtime_registry_fingerprint_value() == (  # noqa: SLF001
        runtime_registry_fingerprint(catalog.fingerprint(), "d" * 64)
    )
    client._release_start_run("run-3")  # noqa: SLF001


def _registry_with_fingerprint(fingerprint: str) -> NodeRegistry:
    registry = NodeRegistry()
    registry.set_python_plugin_catalog((), plugin_fingerprint=fingerprint)
    registry.freeze()
    return registry


def _contract_registry(
    spec: NodeTypeSpec,
    *,
    addon_runtime_config: tuple[tuple[str, bool], ...] = (),
) -> NodeRegistry:
    registry = NodeRegistry(addon_runtime_config=addon_runtime_config)
    registry.register_descriptor(spec, _contract_factory, owner_id="tests.contract")
    registry.freeze()
    return registry


def test_registry_contract_fingerprint_covers_structure_config_and_callables() -> None:
    base_spec = NodeTypeSpec(
        type_id="tests.contract_node",
        display_name="Contract",
        category_path=("Tests",),
        icon="",
        ports=(),
        properties=(),
        instance_spec_resolver=_resolve_contract_a,
    )
    base = _contract_registry(
        base_spec,
        addon_runtime_config=(("mars.corex", False),),
    )
    candidates = (
        _contract_registry(
            replace(
                base_spec,
                ports=(
                    PortSpec(
                        "value",
                        "in",
                        "data",
                        "COREX.DataTypes.Any",
                        required=False,
                    ),
                ),
            ),
            addon_runtime_config=(("mars.corex", False),),
        ),
        _contract_registry(
            replace(
                base_spec,
                properties=(PropertySpec("mode", "str", "a", "Mode"),),
            ),
            addon_runtime_config=(("mars.corex", False),),
        ),
        _contract_registry(
            base_spec,
            addon_runtime_config=(("mars.corex", True),),
        ),
        _contract_registry(
            replace(base_spec, instance_spec_resolver=_resolve_contract_b),
            addon_runtime_config=(("mars.corex", False),),
        ),
    )

    assert all(
        candidate.data_types.fingerprint() == base.data_types.fingerprint()
        and candidate.plugin_fingerprint() == base.plugin_fingerprint()
        and candidate.contract_fingerprint() != base.contract_fingerprint()
        for candidate in candidates
    )


@pytest.mark.parametrize(
    "client_type",
    (
        ProcessExecutionClient,
        ExternalPythonExecutionClient,
        TrustedInProcessExecutionClient,
    ),
)
def test_addon_contract_change_retires_every_backend_generation(
    client_type,
    monkeypatch,
) -> None:  # noqa: ANN001
    disabled = NodeRegistry(addon_runtime_config=(("mars.corex", False),))
    disabled.freeze()
    enabled = NodeRegistry(addon_runtime_config=(("mars.corex", True),))
    enabled.freeze()
    assert disabled.data_types.fingerprint() == enabled.data_types.fingerprint()
    assert disabled.plugin_fingerprint() == enabled.plugin_fingerprint()

    client = client_type()
    recycled = []
    monkeypatch.setattr(client, "_recycle_catalog_generation", lambda: recycled.append(1))
    try:
        assert client._prepare_start_run(  # noqa: SLF001
            "run-disabled",
            "ws",
            disabled.data_types,
            (),
            disabled.plugin_fingerprint(),
            disabled.contract_fingerprint(),
            disabled.addon_runtime_config(),
        )
        client._release_start_run("run-disabled")  # noqa: SLF001
        assert client._prepare_start_run(  # noqa: SLF001
            "run-enabled",
            "ws",
            enabled.data_types,
            (),
            enabled.plugin_fingerprint(),
            enabled.contract_fingerprint(),
            enabled.addon_runtime_config(),
        )
        assert recycled == [1]
        assert client._addon_runtime_config == (("mars.corex", True),)  # noqa: SLF001
    finally:
        client.shutdown()


def test_corex_runtime_replace_registry_retires_client_without_legacy_start() -> None:
    class RecordingBackend:
        def __init__(self) -> None:
            self.preflights = 0
            self.replacements = []

        def subscribe(self, _callback):  # noqa: ANN001
            return None

        def replace_registry(self, registry):  # noqa: ANN001
            self.replacements.append(registry)
            return True

        def assert_registry_replaceable(self) -> None:
            self.preflights += 1

    original = _registry_with_fingerprint(EMPTY_PLUGIN_FINGERPRINT)
    replacement = _registry_with_fingerprint(_PLUGIN_FINGERPRINT)
    backend = RecordingBackend()
    runtime = CorexRuntime(client=backend, registry=original)

    runtime.assert_registry_replaceable()
    assert backend.preflights == 1
    assert runtime.replace_registry(replacement)
    assert backend.replacements == [replacement]
    assert not hasattr(runtime, "start_run")


def test_execution_backend_registry_replacement_visits_every_client(monkeypatch) -> None:
    backend = ExecutionBackendClient()
    registry = _registry_with_fingerprint(_PLUGIN_FINGERPRINT)
    calls = []
    try:
        backend._workspace_clients["completed-ws"] = backend._process_client  # noqa: SLF001
        backend._workspace_client_generations["completed-ws"] = 0  # noqa: SLF001
        for index, client in enumerate(
            (
                backend._process_client,  # noqa: SLF001
                backend._external_python_client,  # noqa: SLF001
                backend._trusted_client,  # noqa: SLF001
            )
        ):
            monkeypatch.setattr(
                client,
                "replace_registry",
                lambda value, index=index: calls.append((index, value)) or index == 0,
            )

        assert backend.replace_registry(registry)
        assert calls == [(0, registry), (1, registry), (2, registry)]
        assert backend._workspace_clients == {}  # noqa: SLF001
    finally:
        backend.shutdown()


@pytest.mark.parametrize("route_state", ("active", "session", "provisional"))
def test_execution_backend_registry_preflight_rejects_live_routes(
    route_state,
) -> None:  # noqa: ANN001
    backend = ExecutionBackendClient()
    try:
        if route_state == "active":
            backend._active_clients["run"] = backend._process_client  # noqa: SLF001
            error = "active run"
        elif route_state == "session":
            backend._session_clients[("ws", "session")] = (  # noqa: SLF001
                backend._process_client  # noqa: SLF001
            )
            error = "viewer routes"
        else:
            backend._provisional_viewer_routes[("ws", "session")] = object()  # type: ignore[assignment]  # noqa: SLF001
            error = "viewer routes"

        with pytest.raises(DataTypeCatalogError, match=error):
            backend.assert_registry_replaceable()
    finally:
        backend.shutdown()


def test_execution_backend_registry_preflight_visits_every_client(
    monkeypatch,
) -> None:
    backend = ExecutionBackendClient()
    calls = []
    try:
        for index, client in enumerate(
            (
                backend._process_client,  # noqa: SLF001
                backend._external_python_client,  # noqa: SLF001
                backend._trusted_client,  # noqa: SLF001
            )
        ):
            monkeypatch.setattr(
                client,
                "assert_registry_replaceable",
                lambda index=index: calls.append(index),
            )

        backend.assert_registry_replaceable()
        assert calls == [0, 1, 2]
    finally:
        backend.shutdown()


def test_execution_backend_replace_rechecks_after_preflight_race() -> None:
    backend = ExecutionBackendClient()
    registry = _registry_with_fingerprint(_PLUGIN_FINGERPRINT)
    try:
        backend.assert_registry_replaceable()
        backend._active_clients["run-raced"] = backend._process_client  # noqa: SLF001

        with pytest.raises(DataTypeCatalogError, match="active run"):
            backend.replace_registry(registry)
    finally:
        backend.shutdown()


def test_registry_publication_guard_blocks_run_and_viewer_admission(
    monkeypatch,
) -> None:
    registry = _registry_with_fingerprint(EMPTY_PLUGIN_FINGERPRINT)
    backend = ExecutionBackendClient()
    entered = [threading.Event(), threading.Event()]
    finished = [threading.Event(), threading.Event()]
    results: list[str] = []
    monkeypatch.setattr(
        backend._process_client,  # noqa: SLF001
        "start_run",
        lambda *_args, **_kwargs: "run-guard",
    )
    monkeypatch.setattr(
        backend._process_client,  # noqa: SLF001
        "open_viewer_session",
        lambda *_args, **_kwargs: "viewer-guard",
    )

    def start_run() -> None:
        entered[0].set()
        results.append(
            backend.start_run(
                "",
                "ws",
                data_types=registry.data_types,
                plugin_fingerprint=registry.plugin_fingerprint(),
                registry_contract_fingerprint=registry.contract_fingerprint(),
                addon_runtime_config=registry.addon_runtime_config(),
            )
        )
        finished[0].set()

    def open_viewer() -> None:
        entered[1].set()
        results.append(
            backend.open_viewer_session("ws", "node", session_id="session")
        )
        finished[1].set()

    try:
        with backend.registry_publication_guard():
            threads = (
                threading.Thread(target=start_run),
                threading.Thread(target=open_viewer),
            )
            for thread in threads:
                thread.start()
            assert all(event.wait(1.0) for event in entered)
            time.sleep(0.05)
            assert not any(event.is_set() for event in finished)
            assert backend.replace_registry(registry) is False

        for thread in threads:
            thread.join(timeout=2.0)
        assert all(event.is_set() for event in finished)
        assert set(results) == {"run-guard", "viewer-guard"}
    finally:
        backend.shutdown()


def test_plugin_refs_never_enter_project_persistence(tmp_path) -> None:
    generation_root = tmp_path / "plugin_generations"
    bundle = _bundle(generation_root)
    spec = NodeTypeSpec(
        type_id="custom.persist.1234abcd",
        display_name="Persist",
        category_path=("Tests",),
        icon="",
        ports=(),
        properties=(),
    )
    registry = NodeRegistry()
    registry.register_python_function(spec, bundle.functions[0])
    registry.set_python_plugin_catalog(
        (bundle,),
        plugin_fingerprint=_PLUGIN_FINGERPRINT,
    )
    model = GraphModel()
    ValidatedGraphMutation(
        model,
        model.active_workspace.workspace_id,
        registry,
    ).add_node(type_id=spec.type_id, title="Persist", x=0.0, y=0.0)

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    serialized = json.dumps(document, sort_keys=True)

    assert spec.type_id in serialized
    assert bundle.approved_generation_root not in serialized
    assert _BUNDLE_DIGEST not in serialized
    assert _SOURCE_DIGEST not in serialized
    assert "plugin_bundles" not in serialized
    assert "function_name" not in serialized
