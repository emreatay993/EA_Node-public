# Purpose: Execution backend selection, generation routing, viewer ownership, and invalidation commit.
# Map: subsystems/execution.md
# Tests: tests/test_backend_client.py
# Landmarks: ExecutionBackendClient
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ea_node_editor.common.coercions import normalize_path_text
from ea_node_editor.execution.backends import (
    EXTERNAL_SUBPROCESS_BACKEND,
    TRUSTED_IN_PROCESS_BACKEND,
    ExecutionBackendOrchestrator,
    ExecutionBackendSelection,
)
from ea_node_editor.execution.client_common import (
    _ExecutionClientCommon,
    _registry_admitted,
    _registry_contract_digest,
)
from ea_node_editor.execution.client_generation import (
    ExecutionGenerationSnapshot,
    ExecutionResourceLease,
    ExecutionRunReservation,
    ViewerInvalidationReservation,
    _participant_viewer_snapshot,
    _result_affecting_selection_payload,
    _ViewerInvalidationSnapshot,
)
from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.protocol_codec import (
    event_to_dict,
)
from ea_node_editor.execution.python_environment import (
    resolve_python_environment,
    workflow_python_path_from_snapshot,
)
from ea_node_editor.execution.registry_agreement import (
    EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
)
from ea_node_editor.execution.run_messages import (
    CancelRunPreflightCommand,
    CommitRunPreflightCommand,
    ProtocolErrorEvent,
)
from ea_node_editor.execution.solution_identity import canonical_digest
from ea_node_editor.execution.trusted_client import TrustedInProcessExecutionClient
from ea_node_editor.execution.viewer_messages import (
    VIEWER_RESPONSE_EVENT_TYPES,
    normalize_viewer_invalidation_node_ids,
    viewer_epoch_snapshot_digest,
)
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
    RuntimeHandleRef,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult

_EXTERNAL_RUNTIME_IDENTITY_PROBE = r"""
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

names = json.loads(sys.argv[1])
mapping = importlib.metadata.packages_distributions()
packages = []
for name in names:
    distributions = mapping.get(name, ()) or (name,)
    versions = []
    for distribution in sorted(set(distributions)):
        try:
            versions.append((distribution, importlib.metadata.version(distribution)))
        except importlib.metadata.PackageNotFoundError:
            continue
    packages.append((name, versions or [("", "missing")]))
executable = Path(sys.executable)
digest = hashlib.sha256()
with executable.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
print(json.dumps({
    "implementation": sys.implementation.name,
    "cache_tag": sys.implementation.cache_tag or "",
    "version": list(sys.version_info[:3]),
    "platform": [platform.system(), platform.release(), platform.machine()],
    "executable_size": executable.stat().st_size,
    "executable_sha256": digest.hexdigest(),
    "packages": packages,
}, sort_keys=True, separators=(",", ":")))
"""


def _package_versions(package_names: tuple[str, ...]) -> tuple[tuple[str, object], ...]:
    mapping = importlib.metadata.packages_distributions()
    result = []
    for name in package_names:
        distributions = mapping.get(name, ()) or (name,)
        versions = []
        for distribution in sorted(set(distributions)):
            try:
                versions.append(
                    (distribution, importlib.metadata.version(distribution))
                )
            except importlib.metadata.PackageNotFoundError:
                continue
        result.append((name, tuple(versions) or (("", "missing"),)))
    return tuple(result)


def _local_runtime_identity(package_names: tuple[str, ...]) -> dict[str, object]:
    executable = Path(sys.executable)
    digest = hashlib.sha256()
    with executable.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag or "",
        "version": tuple(sys.version_info[:3]),
        "platform": (platform.system(), platform.release(), platform.machine()),
        "executable_size": executable.stat().st_size,
        "executable_sha256": digest.hexdigest(),
        "packages": _package_versions(package_names),
    }


@dataclass(frozen=True)
class _BackendViewerInvalidationPlan:
    workspace_epochs: dict[str, int]
    node_epochs: dict[tuple[str, str], int]
    workspace_clients: dict[str, Any]
    workspace_client_generations: dict[str, int]
    session_clients: dict[tuple[str, str], Any]
    session_client_generations: dict[tuple[str, str], int]
    session_node_ids: dict[tuple[str, str], str]
    provisional_routes: dict[tuple[str, str], _ProvisionalViewerRoute]
    provisional_request_sessions: dict[str, tuple[str, str]]
    retired_request_ids: frozenset[str]


@dataclass
class _ProvisionalViewerRoute:
    session_key: tuple[str, str]
    baseline_client: Any | None
    baseline_generation: int
    baseline_request_order: int
    requests: list[tuple[int, str, Any, int]]


class ExecutionBackendClient:
    _TERMINAL_EVENT_TYPES = {"run_completed", "run_failed", "run_stopped"}
    _RETAINED_VIEWER_RUN_LIMIT = 64

    def __init__(
        self, *, orchestrator: ExecutionBackendOrchestrator | None = None
    ) -> None:
        self._orchestrator = orchestrator or ExecutionBackendOrchestrator()
        self._process_client = ProcessExecutionClient()
        self._trusted_client = TrustedInProcessExecutionClient()
        self._external_python_client = ExternalPythonExecutionClient()
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._generation_callbacks: list[
            Callable[[dict[str, Any], ExecutionGenerationSnapshot], None]
        ] = []
        self._published_registry: NodeRegistry | None = None
        self._run_reservations: dict[str, tuple[ExecutionRunReservation, Any]] = {}
        self._viewer_invalidation_reservations: dict[
            str, ViewerInvalidationReservation
        ] = {}
        self._client_selections: dict[int, ExecutionBackendSelection] = {
            id(self._process_client): ExecutionBackendSelection(),
            id(self._trusted_client): ExecutionBackendSelection(
                backend_id=TRUSTED_IN_PROCESS_BACKEND,
                isolation="in_process",
                reason="trusted_in_process_opt_in",
                trusted_in_process=True,
            ),
            id(self._external_python_client): ExecutionBackendSelection(
                backend_id=EXTERNAL_SUBPROCESS_BACKEND,
                isolation="external_subprocess",
                reason="external_runtime_contract",
                external_subprocess=True,
            ),
        }
        self._active_clients: dict[str, Any] = {}
        self._run_clients: dict[str, Any] = {}
        self._run_client_generations: dict[str, int] = {}
        self._run_generation_snapshots: dict[
            str,
            ExecutionGenerationSnapshot,
        ] = {}
        self._run_workspace_ids: dict[str, str] = {}
        self._workspace_clients: dict[str, Any] = {}
        self._workspace_client_generations: dict[str, int] = {}
        self._session_clients: dict[tuple[str, str], Any] = {}
        self._session_client_generations: dict[tuple[str, str], int] = {}
        self._session_node_ids: dict[tuple[str, str], str] = {}
        self._workspace_viewer_epochs: dict[str, int] = {}
        self._node_viewer_epochs: dict[tuple[str, str], int] = {}
        self._provisional_viewer_routes: dict[
            tuple[str, str],
            _ProvisionalViewerRoute,
        ] = {}
        self._provisional_request_sessions: dict[
            str,
            tuple[str, str],
        ] = {}
        self._next_viewer_request_order = 0
        self._terminal_run_ids_seen: set[str] = set()
        self._active_lock = threading.Lock()
        self._viewer_invalidation_lock = threading.RLock()
        self._registry_publication_lock = threading.RLock()
        self._process_client.subscribe(
            lambda event, generation: self._dispatch_client_event(
                self._process_client,
                event,
                generation_token=generation,
            ),
            include_generation=True,
        )
        self._trusted_client.subscribe(
            lambda event, generation: self._dispatch_client_event(
                self._trusted_client,
                event,
                generation_token=generation,
            ),
            include_generation=True,
        )
        self._external_python_client.subscribe(
            lambda event, generation: self._dispatch_client_event(
                self._external_python_client,
                event,
                generation_token=generation,
            ),
            include_generation=True,
        )

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._callbacks.append(callback)

    def _ensure_viewer_invalidation_state(self) -> None:
        if not hasattr(self, "_viewer_invalidation_lock"):
            self._viewer_invalidation_lock = threading.RLock()
        if not hasattr(self, "_viewer_invalidation_reservations"):
            self._viewer_invalidation_reservations = {}
        if not hasattr(self, "_viewer_commit_publication_pending"):
            self._viewer_commit_publication_pending = set()
        if not hasattr(self, "_viewer_commit_event_buffers"):
            self._viewer_commit_event_buffers = {}

    def subscribe_generation_events(
        self,
        callback: Callable[[dict[str, Any], ExecutionGenerationSnapshot], None],
    ) -> None:
        self._generation_callbacks.append(callback)

    def _client_for_selection(self, selection: ExecutionBackendSelection) -> Any:
        if selection.backend_id == EXTERNAL_SUBPROCESS_BACKEND:
            return self._external_python_client
        if selection.backend_id == TRUSTED_IN_PROCESS_BACKEND:
            return self._trusted_client
        return self._process_client

    def resolve_execution_selection(
        self,
        policy: Any,
        runtime_snapshot: Any = None,
    ) -> ExecutionBackendSelection:
        workflow_python_path = workflow_python_path_from_snapshot(runtime_snapshot)
        raw_policy = policy
        if raw_policy is None and workflow_python_path:
            raw_policy = {
                "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                "allow_external_subprocess": True,
                "python_executable": workflow_python_path,
                "reason": "workflow_python_path",
            }
        selection = self._orchestrator.select(raw_policy)
        if selection.backend_id != EXTERNAL_SUBPROCESS_BACKEND:
            return selection
        python_executable = normalize_path_text(selection.python_executable)
        if not python_executable:
            python_executable = workflow_python_path
        if not python_executable:
            raise ValueError(
                "External Python workflow execution requires python_executable or "
                "Workflow Settings > Environment > Workflow Override."
            )
        python_environment = resolve_python_environment(python_executable)
        if not python_environment.valid:
            raise ValueError(python_environment.error)
        return replace(
            selection,
            python_executable=python_environment.python_executable,
            reason=selection.reason
            or ("workflow_python_path" if workflow_python_path else ""),
        )

    def _generation_snapshot_for_client(
        self,
        client: Any,
        selection: ExecutionBackendSelection,
        *,
        registry_contract_fingerprint: str = "",
    ) -> ExecutionGenerationSnapshot:
        with client._state_lock:  # noqa: SLF001
            backend_generation = int(getattr(client, "_catalog_generation_token", 0))
            runtime_generation = int(
                getattr(client, "_physical_generation_token", backend_generation)
            )
            accepted_generation = int(
                getattr(
                    client,
                    "_accepted_physical_generation_token",
                    runtime_generation,
                )
            )
            registry_fingerprint = str(
                getattr(client, "_registry_contract_generation_fingerprint", "")
            )
            concrete_environment_digest = str(
                getattr(client, "_execution_environment_digest", "")
            )
            environment_registry_fingerprint = str(
                getattr(
                    client,
                    "_execution_environment_registry_fingerprint",
                    "",
                )
            )
            environment_selection_digest = str(
                getattr(
                    client,
                    "_execution_environment_selection_digest",
                    "",
                )
            )
        live = bool(client._viewer_generation_is_live())  # noqa: SLF001
        available = bool(
            backend_generation > 0
            and runtime_generation > 0
            and backend_generation == runtime_generation == accepted_generation
            and live
        )
        if registry_contract_fingerprint:
            registry_fingerprint = _registry_contract_digest(
                registry_contract_fingerprint
            )
        expected_registry = getattr(self, "_published_registry", None)
        if not registry_fingerprint and expected_registry is not None:
            registry_fingerprint = expected_registry.contract_fingerprint()
        expected_registry_fingerprint = (
            registry_fingerprint or EMPTY_REGISTRY_CONTRACT_FINGERPRINT
        )
        environment_ready = bool(
            len(concrete_environment_digest) == 64
            and environment_registry_fingerprint == expected_registry_fingerprint
            and environment_selection_digest
            == canonical_digest(_result_affecting_selection_payload(selection))
        )
        environment_digest = (
            concrete_environment_digest
            if environment_ready
            else canonical_digest(
                {
                    "kind": "execution_environment_unavailable",
                    "backend_id": selection.backend_id,
                    "isolation": selection.isolation,
                    "runtime_backend_ids": selection.runtime_backend_ids,
                    "registry_contract_fingerprint": expected_registry_fingerprint,
                }
            )
        )
        available = available and environment_ready
        return ExecutionGenerationSnapshot(
            selection=selection,
            backend_generation=backend_generation,
            runtime_generation=runtime_generation,
            environment_digest=environment_digest,
            available=available,
            reason=(
                ""
                if available
                else (
                    "execution_environment_unavailable"
                    if live and backend_generation > 0
                    else "execution_generation_unavailable"
                )
            ),
        )

    def _bind_route_environment(
        self,
        client: Any,
        selection: ExecutionBackendSelection,
        registry: NodeRegistry,
        *,
        publish: bool = True,
    ) -> str:
        registry_fingerprint = registry.contract_fingerprint()
        selection_payload = _result_affecting_selection_payload(selection)
        selection_digest = canonical_digest(selection_payload)
        with client._state_lock:  # noqa: SLF001
            if (
                len(getattr(client, "_execution_environment_digest", "")) == 64
                and getattr(
                    client,
                    "_execution_environment_registry_fingerprint",
                    "",
                )
                == registry_fingerprint
                and getattr(
                    client,
                    "_execution_environment_selection_digest",
                    "",
                )
                == selection_digest
            ):
                return str(client._execution_environment_digest)  # noqa: SLF001
        declared_facts = registry.execution_environment_facts()
        package_names = tuple(declared_facts.get("python_packages", ()))
        if selection.backend_id == EXTERNAL_SUBPROCESS_BACKEND:
            result = subprocess.run(
                [
                    selection.python_executable,
                    "-c",
                    _EXTERNAL_RUNTIME_IDENTITY_PROBE,
                    json.dumps(package_names, separators=(",", ":")),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=10.0,
            )
            if result.returncode != 0:
                raise RuntimeError("External Python runtime identity handshake failed.")
            try:
                runtime_facts = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "External Python runtime identity handshake was invalid."
                ) from exc
            if not isinstance(runtime_facts, Mapping):
                raise RuntimeError(
                    "External Python runtime identity handshake was invalid."
                )
        else:
            runtime_facts = _local_runtime_identity(package_names)
        environment_digest = canonical_digest(
            {
                "schema_version": 1,
                "selection": selection_payload,
                "runtime": dict(runtime_facts),
                "declared": declared_facts,
                "registry_contract_fingerprint": registry_fingerprint,
            }
        )
        if publish:
            with client._state_lock:  # noqa: SLF001
                client._execution_environment_digest = environment_digest  # noqa: SLF001
                client._execution_environment_registry_fingerprint = (  # noqa: SLF001
                    registry_fingerprint
                )
                client._execution_environment_selection_digest = (  # noqa: SLF001
                    selection_digest
                )
        return environment_digest

    def execution_generation_snapshot(
        self,
        selection: ExecutionBackendSelection,
        *,
        registry_contract_fingerprint: str = "",
    ) -> ExecutionGenerationSnapshot:
        if not isinstance(selection, ExecutionBackendSelection):
            raise TypeError("selection must be an ExecutionBackendSelection")
        client = self._client_for_selection(selection)
        return self._generation_snapshot_for_client(
            client,
            selection,
            registry_contract_fingerprint=registry_contract_fingerprint,
        )

    def preview_execution_environment(
        self,
        selection: ExecutionBackendSelection,
        registry: NodeRegistry,
    ) -> str:
        """Compute the exact result-affecting environment without starting a run."""

        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        client = self._client_for_selection(selection)
        return self._bind_route_environment(
            client,
            selection,
            registry,
            publish=False,
        )

    @_registry_admitted
    def reserve_run(
        self,
        selection: ExecutionBackendSelection,
        workspace_id: str,
    ) -> ExecutionRunReservation:
        registry = self._published_registry
        if registry is None:
            raise RuntimeError("reserve_run requires a published registry")
        client = self._client_for_selection(selection)
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        normalized_workspace_id = str(workspace_id).strip()
        if not normalized_workspace_id:
            raise ValueError("workspace_id must be non-empty")
        try:
            if client is self._process_client:
                client._ensure_process()  # noqa: SLF001
            elif client is self._external_python_client:
                python_executable = str(selection.python_executable).strip()
                client._assert_process_transition_allowed()  # noqa: SLF001
                client._verify_runtime_available(python_executable)  # noqa: SLF001
                client._ensure_process(python_executable)  # noqa: SLF001
            prepared = client._prepare_start_run(  # noqa: SLF001
                run_id,
                normalized_workspace_id,
                registry.data_types,
                registry.plugin_bundle_refs(),
                registry.plugin_fingerprint(),
                registry.contract_fingerprint(),
                registry.addon_runtime_config(),
            )
            if not prepared:
                raise RuntimeError("execution backend already has an active run")
            if client is self._trusted_client:
                with client._state_lock:  # noqa: SLF001
                    client._accepted_physical_generation_token = (  # noqa: SLF001
                        client._catalog_generation_token  # noqa: SLF001
                    )
            self._bind_route_environment(client, selection, registry)
            self._client_selections[id(client)] = selection
            snapshot = self._generation_snapshot_for_client(client, selection)
            if not snapshot.available:
                raise RuntimeError(snapshot.reason)
        except Exception:
            client._release_start_run(run_id)  # noqa: SLF001
            raise
        reservation = ExecutionRunReservation(
            run_id=run_id,
            workspace_id=normalized_workspace_id,
            selection=selection,
            generation_snapshot=snapshot,
        )
        with self._active_lock:
            self._run_reservations[run_id] = (reservation, client)
        return reservation

    def reserve_viewer_invalidation(
        self,
        run_reservation: ExecutionRunReservation,
        preparation_id: str,
        node_ids: Iterable[str] | None,
    ) -> ViewerInvalidationReservation:
        self._ensure_viewer_invalidation_state()
        if not isinstance(run_reservation, ExecutionRunReservation):
            raise TypeError("run_reservation must be an ExecutionRunReservation")
        normalized_node_ids = normalize_viewer_invalidation_node_ids(node_ids)
        workspace_id = run_reservation.workspace_id
        process = self._process_client
        trusted = self._trusted_client
        external = self._external_python_client
        selected_client = self._client_for_selection(run_reservation.selection)
        with self._viewer_invalidation_lock:
            with self._active_lock:
                self._ensure_route_generation_maps_locked()
                projection_snapshot = _participant_viewer_snapshot(
                    workspace_id=workspace_id,
                    node_ids=normalized_node_ids,
                    workspace_epochs=self._workspace_viewer_epochs,
                    node_epochs=self._node_viewer_epochs,
                    generation=None,
                )
                with process._state_lock:  # noqa: SLF001
                    with process._viewer_request_lock:  # noqa: SLF001
                        process_snapshot = _participant_viewer_snapshot(
                            workspace_id=workspace_id,
                            node_ids=normalized_node_ids,
                            workspace_epochs=process._workspace_viewer_epochs,  # noqa: SLF001
                            node_epochs=process._node_viewer_epochs,  # noqa: SLF001
                            generation=process._catalog_generation_token,  # noqa: SLF001
                        )
                        with trusted._state_lock:  # noqa: SLF001
                            with trusted._viewer_request_lock:  # noqa: SLF001
                                trusted_snapshot = _participant_viewer_snapshot(
                                    workspace_id=workspace_id,
                                    node_ids=normalized_node_ids,
                                    workspace_epochs=trusted._workspace_viewer_epochs,  # noqa: SLF001
                                    node_epochs=trusted._node_viewer_epochs,  # noqa: SLF001
                                    generation=trusted._catalog_generation_token,  # noqa: SLF001
                                )
                                with external._state_lock:  # noqa: SLF001
                                    with external._viewer_request_lock:  # noqa: SLF001
                                        external_snapshot = _participant_viewer_snapshot(
                                            workspace_id=workspace_id,
                                            node_ids=normalized_node_ids,
                                            workspace_epochs=(
                                                external._workspace_viewer_epochs  # noqa: SLF001
                                            ),
                                            node_epochs=external._node_viewer_epochs,  # noqa: SLF001
                                            generation=(
                                                external._catalog_generation_token  # noqa: SLF001
                                            ),
                                        )
            snapshot_by_client_id = {
                id(process): process_snapshot,
                id(trusted): trusted_snapshot,
                id(external): external_snapshot,
            }
            selected_snapshot = snapshot_by_client_id[id(selected_client)]
            if (
                selected_snapshot.generation
                != run_reservation.generation_snapshot.backend_generation
            ):
                raise ValueError("viewer invalidation reservation generation changed")
            reservation = ViewerInvalidationReservation(
                reservation_id=f"viewer_inv_{uuid.uuid4().hex}",
                run_id=run_reservation.run_id,
                preparation_id=str(preparation_id).strip(),
                workspace_id=workspace_id,
                node_ids=normalized_node_ids,
                process_snapshot=process_snapshot,
                trusted_snapshot=trusted_snapshot,
                external_snapshot=external_snapshot,
                projection_snapshot=projection_snapshot,
                selected_snapshot=selected_snapshot,
                client=selected_client,
            )
            self._viewer_invalidation_reservations[reservation.reservation_id] = (
                reservation
            )
            return reservation

    def commit_viewer_invalidation(
        self,
        reservation: ViewerInvalidationReservation,
    ) -> set[str]:
        self._ensure_viewer_invalidation_state()
        if not isinstance(reservation, ViewerInvalidationReservation):
            raise TypeError("reservation must be a ViewerInvalidationReservation")
        delivery_error = ""
        delivered = False
        retired_request_ids: set[str] = set()
        process = self._process_client
        trusted = self._trusted_client
        external = self._external_python_client
        commit_command = CommitRunPreflightCommand(
            run_id=reservation.run_id,
            viewer_invalidation_reservation_id=reservation.reservation_id,
            viewer_epoch_snapshot_digest=reservation.snapshot_digest,
        )
        encoded_commit = reservation.client._encode_run_preflight_command(  # noqa: SLF001
            commit_command
        )
        with self._viewer_invalidation_lock:
            with self._active_lock:
                with process._state_lock:  # noqa: SLF001
                    with process._viewer_request_lock:  # noqa: SLF001
                        with trusted._state_lock:  # noqa: SLF001
                            with trusted._viewer_request_lock:  # noqa: SLF001
                                with external._state_lock:  # noqa: SLF001
                                    with external._viewer_request_lock:  # noqa: SLF001
                                        participants = (
                                            (process, reservation.process_snapshot),
                                            (trusted, reservation.trusted_snapshot),
                                            (external, reservation.external_snapshot),
                                        )
                                        stored = (
                                            self._viewer_invalidation_reservations.get(
                                                reservation.reservation_id
                                            )
                                        )
                                        if stored != reservation:
                                            raise ValueError(
                                                "viewer invalidation reservation is unknown"
                                            )
                                        for child, snapshot in participants:
                                            if (
                                                child._catalog_generation_token  # noqa: SLF001
                                                != snapshot.generation
                                            ):
                                                raise ValueError(
                                                    "viewer invalidation participant generation changed"
                                                )
                                        if (
                                            reservation.client._accepted_physical_generation_token  # noqa: SLF001
                                            != reservation.backend_generation
                                        ):
                                            raise ValueError(
                                                "viewer invalidation reservation generation changed"
                                            )
                                        process_plan = process._plan_viewer_invalidation_snapshot_locked(  # noqa: SLF001
                                            reservation.workspace_id,
                                            reservation.node_ids,
                                            reservation.process_snapshot.workspace_epoch,
                                            reservation.process_snapshot.node_epochs,
                                        )
                                        trusted_plan = trusted._plan_viewer_invalidation_snapshot_locked(  # noqa: SLF001
                                            reservation.workspace_id,
                                            reservation.node_ids,
                                            reservation.trusted_snapshot.workspace_epoch,
                                            reservation.trusted_snapshot.node_epochs,
                                        )
                                        external_plan = external._plan_viewer_invalidation_snapshot_locked(  # noqa: SLF001
                                            reservation.workspace_id,
                                            reservation.node_ids,
                                            reservation.external_snapshot.workspace_epoch,
                                            reservation.external_snapshot.node_epochs,
                                        )
                                        backend_plan = self._plan_backend_viewer_invalidation_snapshot_locked(
                                            reservation
                                        )
                                        transport = reservation.client._pin_run_preflight_transport_locked()  # noqa: SLF001
                                        try:
                                            delivered, delivery_error = (
                                                reservation.client._deliver_encoded_run_preflight_command(  # noqa: SLF001
                                                    encoded_commit,
                                                    transport,
                                                )
                                            )
                                        except Exception as exc:  # noqa: BLE001
                                            delivered = False
                                            delivery_error = str(exc)
                                        if delivered:
                                            process._apply_viewer_invalidation_plan_locked(  # noqa: SLF001
                                                process_plan
                                            )
                                            trusted._apply_viewer_invalidation_plan_locked(  # noqa: SLF001
                                                trusted_plan
                                            )
                                            external._apply_viewer_invalidation_plan_locked(  # noqa: SLF001
                                                external_plan
                                            )
                                            self._apply_backend_viewer_invalidation_plan_locked(
                                                backend_plan
                                            )
                                            retired_request_ids.update(
                                                process_plan.retired_request_ids
                                            )
                                            retired_request_ids.update(
                                                trusted_plan.retired_request_ids
                                            )
                                            retired_request_ids.update(
                                                external_plan.retired_request_ids
                                            )
                                            retired_request_ids.update(
                                                backend_plan.retired_request_ids
                                            )
                                            self._viewer_commit_publication_pending.add(
                                                reservation.run_id
                                            )
                                        self._viewer_invalidation_reservations.pop(
                                            reservation.reservation_id, None
                                        )
        if delivery_error or not delivered:
            try:
                reservation.client._deliver_run_preflight_command(  # noqa: SLF001
                    CancelRunPreflightCommand(
                        run_id=reservation.run_id,
                        viewer_invalidation_reservation_id=(reservation.reservation_id),
                        viewer_epoch_snapshot_digest=reservation.snapshot_digest,
                    )
                )
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                delivery_error or "Failed to deliver run preflight commit."
            )
        return retired_request_ids

    def cancel_viewer_invalidation(
        self,
        reservation: ViewerInvalidationReservation,
    ) -> None:
        self._ensure_viewer_invalidation_state()
        if not isinstance(reservation, ViewerInvalidationReservation):
            return
        with self._viewer_invalidation_lock:
            stored = self._viewer_invalidation_reservations.pop(
                reservation.reservation_id, None
            )
            self._viewer_commit_publication_pending.discard(reservation.run_id)
            self._viewer_commit_event_buffers.pop(reservation.run_id, None)
        if stored != reservation:
            return
        with self._active_lock:
            active_client = self._active_clients.get(reservation.run_id)
        if active_client is reservation.client:
            active_client._post_command(  # noqa: SLF001
                CancelRunPreflightCommand(
                    run_id=reservation.run_id,
                    viewer_invalidation_reservation_id=reservation.reservation_id,
                    viewer_epoch_snapshot_digest=reservation.snapshot_digest,
                )
            )

    def release_run_reservation(
        self,
        reservation: ExecutionRunReservation,
        reason: str,
    ) -> None:
        del reason
        with self._active_lock:
            stored = self._run_reservations.pop(reservation.run_id, None)
        if stored is not None:
            stored[1]._release_start_run(reservation.run_id)  # noqa: SLF001

    @_registry_admitted
    def start_reserved_run(
        self,
        reservation: ExecutionRunReservation,
        command: Any,
    ) -> str:
        # CorexRuntime retires the workspace before taking its activation lock.
        # Consume and validate the reservation only after that blocking sweep.
        from ea_node_editor.execution.run_messages import (
            StartRunCommand,
        )

        if not isinstance(reservation, ExecutionRunReservation):
            raise TypeError("reservation must be an ExecutionRunReservation")
        if not isinstance(command, StartRunCommand):
            raise TypeError("command must be a StartRunCommand")
        with self._active_lock:
            stored = self._run_reservations.pop(reservation.run_id, None)
        if stored is None or stored[0] != reservation:
            raise ValueError("run reservation is unknown or already consumed")
        client = stored[1]
        registry = self._published_registry
        if registry is None:
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            raise RuntimeError("start_reserved_run requires a published registry")
        if (
            command.run_id != reservation.run_id
            or command.workspace_id != reservation.workspace_id
            or command.execution_backend != reservation.selection
        ):
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            raise ValueError("reserved command does not match the reservation")
        current_generation = self._generation_snapshot_for_client(
            client,
            reservation.selection,
        )
        if not current_generation.compatible_with(reservation.generation_snapshot):
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            raise ValueError("reserved execution generation changed before start")
        if (
            command.dispatch_runtime_generation
            != reservation.generation_snapshot.runtime_generation
            or command.execution_environment_digest
            != reservation.generation_snapshot.environment_digest
            or command.dispatch_runtime_generation
            != current_generation.runtime_generation
            or command.execution_environment_digest
            != current_generation.environment_digest
        ):
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            raise ValueError(
                "prepared command generation does not match the reserved execution"
            )
        with self._viewer_invalidation_lock:
            viewer_reservation = self._viewer_invalidation_reservations.get(
                command.viewer_invalidation_reservation_id
            )
        if (
            viewer_reservation is None
            or viewer_reservation.run_id != reservation.run_id
            or viewer_reservation.preparation_id != command.preparation_id
            or viewer_reservation.client is not client
            or viewer_reservation.snapshot_digest
            != command.viewer_epoch_snapshot_digest
            or viewer_reservation.workspace_epoch
            != command.viewer_workspace_invalidation_epoch
            or viewer_reservation.node_epochs != command.viewer_node_invalidation_epochs
            or viewer_reservation.node_ids != command.viewer_invalidation_node_ids
        ):
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            raise ValueError("prepared viewer invalidation reservation changed")
        with self._active_lock:
            self._active_clients[reservation.run_id] = client
            self._run_clients[reservation.run_id] = client
            self._run_client_generations[reservation.run_id] = (
                reservation.generation_snapshot.backend_generation
            )
            self._run_generation_snapshots[reservation.run_id] = (
                reservation.generation_snapshot
            )
            self._run_workspace_ids[reservation.run_id] = reservation.workspace_id
        try:
            run_id = client.start_run(
                command.project_path,
                command.workspace_id,
                trigger={
                    **dict(command.trigger),
                    "runtime_snapshot": command.runtime_snapshot,
                    "developer_mode": command.developer_mode,
                },
                execution_backend=command.execution_backend,
                target_node_ids=command.target_node_ids,
                trigger_publications=command.trigger_publications,
                trigger_captures=command.trigger_captures,
                clicked_trigger_node_id=command.clicked_trigger_node_id,
                data_types=registry.data_types,
                plugin_bundles=registry.plugin_bundle_refs(),
                plugin_fingerprint=registry.plugin_fingerprint(),
                registry_contract_fingerprint=registry.contract_fingerprint(),
                addon_runtime_config=registry.addon_runtime_config(),
                _reserved_run_id=reservation.run_id,
                _reservation_prepared=True,
                _prepared_command=command,
            )
        except Exception:
            client._release_start_run(reservation.run_id)  # noqa: SLF001
            with self._active_lock:
                self._active_clients.pop(reservation.run_id, None)
                self._run_clients.pop(reservation.run_id, None)
                self._run_client_generations.pop(reservation.run_id, None)
                self._run_generation_snapshots.pop(reservation.run_id, None)
                self._run_workspace_ids.pop(reservation.run_id, None)
            raise
        if run_id == reservation.run_id:
            return run_id
        client._release_start_run(reservation.run_id)  # noqa: SLF001
        with self._active_lock:
            self._active_clients.pop(reservation.run_id, None)
            self._run_clients.pop(reservation.run_id, None)
            self._run_client_generations.pop(reservation.run_id, None)
            self._run_generation_snapshots.pop(reservation.run_id, None)
            self._run_workspace_ids.pop(reservation.run_id, None)
        return ""

    @staticmethod
    def _client_generation_token(client: Any) -> int:
        getter = getattr(client, "_catalog_generation_token_value", None)
        if not callable(getter):
            return 0
        try:
            return int(getter())
        except (TypeError, ValueError):
            return 0

    def _ensure_route_generation_maps_locked(self) -> None:
        if not hasattr(self, "_run_client_generations"):
            self._run_client_generations = {}
        if not hasattr(self, "_run_generation_snapshots"):
            self._run_generation_snapshots = {}
        if not hasattr(self, "_workspace_client_generations"):
            self._workspace_client_generations = {}
        if not hasattr(self, "_session_client_generations"):
            self._session_client_generations = {}
        if not hasattr(self, "_provisional_viewer_routes"):
            self._provisional_viewer_routes = {}
        if not hasattr(self, "_provisional_request_sessions"):
            self._provisional_request_sessions = {}
        if not hasattr(self, "_next_viewer_request_order"):
            self._next_viewer_request_order = 0
        if not hasattr(self, "_session_node_ids"):
            self._session_node_ids = {}
        if not hasattr(self, "_workspace_viewer_epochs"):
            self._workspace_viewer_epochs = {}
        if not hasattr(self, "_node_viewer_epochs"):
            self._node_viewer_epochs = {}

    def _apply_provisional_viewer_route_locked(
        self,
        route: _ProvisionalViewerRoute,
    ) -> None:
        session_key = route.session_key
        retained_requests: list[tuple[int, str, Any, int]] = []
        for request_order, request_id, client, generation in route.requests:
            if generation != self._client_generation_token(client):
                self._provisional_request_sessions.pop(request_id, None)
                continue
            retained_requests.append((request_order, request_id, client, generation))
        route.requests = retained_requests
        eligible_requests = [
            record
            for record in retained_requests
            if record[0] > route.baseline_request_order
        ]
        if eligible_requests:
            _order, _request_id, client, generation = eligible_requests[-1]
            self._session_clients[session_key] = client
            self._session_client_generations[session_key] = generation
            return
        baseline_client = route.baseline_client
        if (
            baseline_client is not None
            and route.baseline_generation
            == self._client_generation_token(baseline_client)
        ):
            self._session_clients[session_key] = baseline_client
            self._session_client_generations[session_key] = route.baseline_generation
            return
        self._session_clients.pop(session_key, None)
        self._session_client_generations.pop(session_key, None)

    def _resolve_provisional_viewer_route_locked(
        self,
        *,
        request_id: str,
        succeeded: bool,
        client: Any,
        generation_token: int,
    ) -> None:
        session_key = self._provisional_request_sessions.pop(
            request_id,
            None,
        )
        if session_key is None:
            return
        route = self._provisional_viewer_routes.get(session_key)
        if route is None:
            return
        request_record = next(
            (record for record in route.requests if record[1] == request_id),
            None,
        )
        route.requests = [
            record for record in route.requests if record[1] != request_id
        ]
        if (
            succeeded
            and request_record is not None
            and request_record[2] is client
            and request_record[3] == generation_token
            and request_record[0] > route.baseline_request_order
        ):
            route.baseline_client = client
            route.baseline_generation = generation_token
            route.baseline_request_order = request_record[0]
            workspace_id, _session_id = session_key
            self._workspace_clients[workspace_id] = client
            self._workspace_client_generations[workspace_id] = generation_token
        self._apply_provisional_viewer_route_locked(route)
        if not route.requests:
            self._provisional_viewer_routes.pop(session_key, None)

    def _refresh_provisional_request_generation_locked(
        self,
        *,
        request_id: str,
        client: Any,
        generation_token: int,
    ) -> None:
        session_key = self._provisional_request_sessions.get(request_id)
        if session_key is None:
            return
        route = self._provisional_viewer_routes.get(session_key)
        if route is None:
            return
        route.requests = [
            (
                request_order,
                record_request_id,
                record_client,
                (
                    generation_token
                    if (record_request_id == request_id and record_client is client)
                    else record_generation
                ),
            )
            for (
                request_order,
                record_request_id,
                record_client,
                record_generation,
            ) in route.requests
        ]

    def _prune_provisional_viewer_routes_locked(self, client: Any) -> None:
        current_generation = self._client_generation_token(client)
        for session_key, route in tuple(self._provisional_viewer_routes.items()):
            retained_requests = []
            for request_order, request_id, owner, generation in route.requests:
                if owner is client and generation != current_generation:
                    self._provisional_request_sessions.pop(request_id, None)
                    continue
                retained_requests.append((request_order, request_id, owner, generation))
            route.requests = retained_requests
            if (
                route.baseline_client is client
                and route.baseline_generation != current_generation
            ):
                route.baseline_client = None
                route.baseline_generation = 0
                route.baseline_request_order = 0
            self._apply_provisional_viewer_route_locked(route)
            if not route.requests:
                self._provisional_viewer_routes.pop(session_key, None)

    def _trim_viewer_run_owners_locked(self) -> None:
        self._ensure_route_generation_maps_locked()
        if len(self._run_clients) <= self._RETAINED_VIEWER_RUN_LIMIT:
            return
        active_run_ids = set(self._active_clients)
        for run_id in tuple(self._run_clients):
            if len(self._run_clients) <= self._RETAINED_VIEWER_RUN_LIMIT:
                break
            workspace_id = self._run_workspace_ids.get(run_id, "")
            if run_id in active_run_ids:
                continue
            client = self._run_clients.pop(run_id, None)
            self._run_client_generations.pop(run_id, None)
            self._run_generation_snapshots.pop(run_id, None)
            self._run_workspace_ids.pop(run_id, None)
            if (
                workspace_id
                and self._workspace_clients.get(workspace_id) is client
                and not any(
                    candidate_workspace_id == workspace_id
                    for candidate_workspace_id in self._run_workspace_ids.values()
                )
                and not any(
                    session_workspace_id == workspace_id
                    for session_workspace_id, _session_id in self._session_clients
                )
            ):
                self._workspace_clients.pop(workspace_id, None)
                self._workspace_client_generations.pop(workspace_id, None)

    def _forget_client_generation_locked(self, client: Any) -> None:
        self._ensure_route_generation_maps_locked()
        current_generation = self._client_generation_token(client)
        stale_run_ids = tuple(
            run_id
            for run_id, owner in self._run_clients.items()
            if owner is client
            and self._run_client_generations.get(
                run_id,
                current_generation,
            )
            != current_generation
        )
        for run_id in stale_run_ids:
            self._active_clients.pop(run_id, None)
            self._run_clients.pop(run_id, None)
            self._run_client_generations.pop(run_id, None)
            self._run_generation_snapshots.pop(run_id, None)
            self._run_workspace_ids.pop(run_id, None)
            self._terminal_run_ids_seen.discard(run_id)
        stale_session_keys = tuple(
            session_key
            for session_key, owner in self._session_clients.items()
            if owner is client
            and self._session_client_generations.get(
                session_key,
                current_generation,
            )
            != current_generation
        )
        for session_key in stale_session_keys:
            self._session_clients.pop(session_key, None)
            self._session_client_generations.pop(session_key, None)
            self._session_node_ids.pop(session_key, None)
        for workspace_id, owner in tuple(self._workspace_clients.items()):
            if (
                owner is client
                and self._workspace_client_generations.get(
                    workspace_id,
                    current_generation,
                )
                != current_generation
            ):
                self._workspace_clients.pop(workspace_id, None)
                self._workspace_client_generations.pop(workspace_id, None)
        self._prune_provisional_viewer_routes_locked(client)

    def _release_closed_session_owner_locked(
        self,
        *,
        session_id: str,
        workspace_id: str,
    ) -> None:
        self._ensure_route_generation_maps_locked()
        if session_id and workspace_id:
            session_key = (workspace_id, session_id)
            self._session_clients.pop(session_key, None)
            self._session_client_generations.pop(session_key, None)
            self._session_node_ids.pop(session_key, None)
        if not workspace_id:
            return
        remaining_session_client = None
        remaining_session_generation = 0
        for session_key, session_client in self._session_clients.items():
            session_workspace_id, _session_id = session_key
            if session_workspace_id != workspace_id:
                continue
            session_generation = self._session_client_generations.get(
                session_key,
                self._client_generation_token(session_client),
            )
            if session_generation != self._client_generation_token(session_client):
                continue
            remaining_session_client = session_client
            remaining_session_generation = session_generation
            break
        if remaining_session_client is not None:
            self._workspace_clients[workspace_id] = remaining_session_client
            self._workspace_client_generations[workspace_id] = (
                remaining_session_generation
            )
            return
        if workspace_id in {
            self._run_workspace_ids.get(run_id, "") for run_id in self._active_clients
        }:
            return
        self._workspace_clients.pop(workspace_id, None)
        self._workspace_client_generations.pop(workspace_id, None)
        for run_id, run_workspace_id in tuple(self._run_workspace_ids.items()):
            if run_workspace_id == workspace_id and run_id not in self._active_clients:
                self._run_workspace_ids.pop(run_id, None)
                self._run_clients.pop(run_id, None)
                self._run_client_generations.pop(run_id, None)
                self._run_generation_snapshots.pop(run_id, None)

    def _dispatch_committed_preflight(
        self,
        *,
        client: Any,
        reservation: ViewerInvalidationReservation,
        accepted_event: dict[str, Any],
        committed_event: dict[str, Any],
    ) -> None:
        run_id = str(accepted_event.get("run_id", ""))
        drain_buffered_events = True
        if self._client_generation_token(client) != reservation.backend_generation:
            retired_request_count = self.invalidate_viewer_requests(
                reservation.workspace_id,
                None,
            )
            with self._active_lock:
                projection_workspace_epoch = self._workspace_viewer_epochs.get(
                    reservation.workspace_id,
                    0,
                )
                projection = _ViewerInvalidationSnapshot(
                    generation=None,
                    workspace_epoch=projection_workspace_epoch,
                    node_epochs=(),
                    snapshot_digest=viewer_epoch_snapshot_digest(
                        workspace_id=reservation.workspace_id,
                        node_ids=None,
                        workspace_epoch=projection_workspace_epoch,
                        node_epochs=(),
                    ),
                )
            committed_event = {
                **committed_event,
                "viewer_invalidation_node_ids": None,
                "viewer_workspace_invalidation_epoch": projection.workspace_epoch,
                "viewer_node_invalidation_epochs": [],
                "viewer_epoch_snapshot_digest": projection.snapshot_digest,
                "retired_request_count": (
                    int(committed_event.get("retired_request_count", 0))
                    + retired_request_count
                ),
                "reason": "execution_generation_retired",
            }
            drain_buffered_events = False
        with self._active_lock:
            generation_snapshot = self._run_generation_snapshots.get(run_id)
        if generation_snapshot is None:
            selection = self._client_selections.get(
                id(client),
                ExecutionBackendSelection(),
            )
            generation_snapshot = self._generation_snapshot_for_client(
                client,
                selection,
            )
        try:
            for callback in tuple(self._generation_callbacks):
                try:
                    callback(dict(accepted_event), generation_snapshot)
                except Exception:
                    continue
            for callback in tuple(self._callbacks):
                try:
                    callback(dict(accepted_event))
                except Exception:
                    continue
        finally:
            self._finalize_viewer_invalidation_commit(
                committed_event,
                drain_buffered_events=drain_buffered_events,
            )

    def _finalize_viewer_invalidation_commit(
        self,
        committed_event: dict[str, Any],
        *,
        drain_buffered_events: bool,
    ) -> None:
        run_id = str(committed_event.get("run_id", ""))
        with self._viewer_invalidation_lock:
            publish_adoption = run_id in self._viewer_commit_publication_pending
            if not publish_adoption:
                self._viewer_commit_event_buffers.pop(run_id, None)
                return
        try:
            for callback in tuple(self._callbacks):
                try:
                    callback(dict(committed_event))
                except Exception:
                    continue
        finally:
            with self._viewer_invalidation_lock:
                self._viewer_commit_publication_pending.discard(run_id)
                buffered_events = tuple(
                    self._viewer_commit_event_buffers.pop(run_id, ())
                )
            if not drain_buffered_events:
                return
            for buffered_client, buffered_event, buffered_generation in buffered_events:
                self._dispatch_client_event(
                    buffered_client,
                    buffered_event,
                    generation_token=buffered_generation,
                )

    def _dispatch_client_event(
        self,
        client: Any,
        event: dict[str, Any],
        *,
        generation_token: int | None = None,
    ) -> None:
        self._ensure_viewer_invalidation_state()
        event_type = str(event.get("type", ""))
        run_id = str(event.get("run_id", ""))
        workspace_id = str(event.get("workspace_id", "")).strip()
        session_id = str(event.get("session_id", "")).strip()
        request_id = str(event.get("request_id", "")).strip()
        node_id = str(event.get("node_id", "")).strip()
        if event_type != "run_preflight_accepted" and run_id:
            with self._viewer_invalidation_lock:
                if run_id in self._viewer_commit_publication_pending:
                    self._viewer_commit_event_buffers.setdefault(run_id, []).append(
                        (client, dict(event), generation_token)
                    )
                    return
        if event_type in self._TERMINAL_EVENT_TYPES and run_id:
            with self._viewer_invalidation_lock:
                for reservation_id, pending_reservation in tuple(
                    self._viewer_invalidation_reservations.items()
                ):
                    if pending_reservation.run_id == run_id:
                        self._viewer_invalidation_reservations.pop(reservation_id, None)
        if event_type == "run_preflight_accepted":
            reservation_id = str(
                event.get("viewer_invalidation_reservation_id", "")
            ).strip()
            with self._viewer_invalidation_lock:
                candidate = self._viewer_invalidation_reservations.get(reservation_id)
            if (
                candidate is None
                or candidate.client is not client
                or candidate.run_id != run_id
                or candidate.workspace_id != workspace_id
                or candidate.preparation_id
                != str(event.get("preparation_id", "")).strip()
                or candidate.snapshot_digest
                != str(event.get("viewer_epoch_snapshot_digest", "")).strip()
                or (
                    generation_token is not None
                    and candidate.backend_generation != int(generation_token)
                )
            ):
                if candidate is not None:
                    self.cancel_viewer_invalidation(candidate)
                return
            try:
                retired_request_ids = self.commit_viewer_invalidation(candidate)
            except (RuntimeError, TypeError, ValueError) as exc:
                self.cancel_viewer_invalidation(candidate)
                self._emit_protocol_error(
                    f"Run preflight commit failed: {exc}",
                    run_id=run_id,
                    command="commit_run_preflight",
                )
                return
            projection = candidate.projection_snapshot
            committed_viewer_event = {
                "type": "viewer_invalidation_committed",
                "run_id": candidate.run_id,
                "preparation_id": candidate.preparation_id,
                "workspace_id": candidate.workspace_id,
                "viewer_invalidation_node_ids": (
                    None if candidate.node_ids is None else list(candidate.node_ids)
                ),
                "viewer_workspace_invalidation_epoch": projection.workspace_epoch,
                "viewer_node_invalidation_epochs": [
                    [item_node_id, epoch]
                    for item_node_id, epoch in projection.node_epochs
                ],
                "viewer_invalidation_reservation_id": candidate.reservation_id,
                "viewer_epoch_snapshot_digest": projection.snapshot_digest,
                "retired_request_count": len(retired_request_ids),
                "reason": "workspace_rerun",
            }
            self._dispatch_committed_preflight(
                client=client,
                reservation=candidate,
                accepted_event=dict(event),
                committed_event=committed_viewer_event,
            )
            return
        failed_open = (
            event_type == "viewer_session_failed"
            and str(event.get("command", "")).strip() == "open_viewer_session"
        )
        opened_session = event_type == "viewer_session_opened"
        releases_session = event_type == "viewer_session_closed"
        retains_route = not releases_session and not failed_open
        pinned_generation_snapshot = None
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            current_generation = 0
            event_generation = 0
            if client is not None:
                event_generation = (
                    int(generation_token) if generation_token is not None else 0
                )
                with client._state_lock:  # noqa: SLF001
                    current_generation = int(  # noqa: SLF001
                        client._catalog_generation_token
                    )
                    if generation_token is None:
                        event_generation = current_generation
                    if event_generation != current_generation:
                        return
                    if event_type in VIEWER_RESPONSE_EVENT_TYPES:
                        with client._viewer_request_lock:  # noqa: SLF001
                            if int(
                                event.get("workspace_invalidation_epoch", 0)
                            ) != client._workspace_viewer_epochs.get(  # noqa: SLF001
                                workspace_id,
                                0,
                            ) or int(
                                event.get("node_invalidation_epoch", 0)
                            ) != client._node_viewer_epochs.get(  # noqa: SLF001
                                (workspace_id, node_id),
                                0,
                            ):
                                return
                if event_type in VIEWER_RESPONSE_EVENT_TYPES:
                    event = dict(event)
                    event["workspace_invalidation_epoch"] = (
                        self._workspace_viewer_epochs.get(workspace_id, 0)
                    )
                    event["node_invalidation_epoch"] = self._node_viewer_epochs.get(
                        (workspace_id, node_id),
                        0,
                    )
            if event_type in VIEWER_RESPONSE_EVENT_TYPES and (
                int(event.get("workspace_invalidation_epoch", 0))
                != self._workspace_viewer_epochs.get(workspace_id, 0)
                or int(event.get("node_invalidation_epoch", 0))
                != self._node_viewer_epochs.get((workspace_id, node_id), 0)
            ):
                return
            if run_id:
                pinned_generation_snapshot = self._run_generation_snapshots.get(run_id)
            tracked_open = bool(
                opened_session
                and request_id
                and request_id in self._provisional_request_sessions
            )
            if client is not None and request_id:
                self._refresh_provisional_request_generation_locked(
                    request_id=request_id,
                    client=client,
                    generation_token=event_generation,
                )
            if client is not None:
                self._forget_client_generation_locked(client)
            if event_type in self._TERMINAL_EVENT_TYPES and run_id:
                self._active_clients.pop(run_id, None)
                self._terminal_run_ids_seen.add(run_id)
                while (
                    len(self._terminal_run_ids_seen) > self._RETAINED_VIEWER_RUN_LIMIT
                ):
                    self._terminal_run_ids_seen.pop()
            if (
                client is not None
                and workspace_id
                and retains_route
                and not tracked_open
            ):
                self._workspace_clients[workspace_id] = client
                self._workspace_client_generations[workspace_id] = event_generation
            if (
                client is not None
                and session_id
                and workspace_id
                and event_type in VIEWER_RESPONSE_EVENT_TYPES
                and retains_route
                and not tracked_open
            ):
                session_key = (workspace_id, session_id)
                self._session_clients[session_key] = client
                self._session_client_generations[session_key] = event_generation
                self._session_node_ids[session_key] = node_id
            if client is not None and releases_session:
                self._release_closed_session_owner_locked(
                    session_id=session_id,
                    workspace_id=workspace_id,
                )
            if client is not None and request_id and (opened_session or failed_open):
                self._resolve_provisional_viewer_route_locked(
                    request_id=request_id,
                    succeeded=opened_session,
                    client=client,
                    generation_token=event_generation,
                )
            self._trim_viewer_run_owners_locked()
        generation_callbacks = tuple(getattr(self, "_generation_callbacks", ()))
        if client is not None and generation_callbacks:
            generation_snapshot = pinned_generation_snapshot
            if generation_snapshot is not None:
                current_snapshot = self._generation_snapshot_for_client(
                    client,
                    generation_snapshot.selection,
                )
                if not current_snapshot.available:
                    generation_snapshot = current_snapshot
            if generation_snapshot is None:
                selection = getattr(self, "_client_selections", {}).get(
                    id(client),
                    ExecutionBackendSelection(),
                )
                generation_snapshot = self._generation_snapshot_for_client(
                    client,
                    selection,
                )
            for callback in generation_callbacks:
                try:
                    callback(dict(event), generation_snapshot)
                except Exception:
                    continue
        if event_type == "execution_generation_changed":
            return
        for callback in list(self._callbacks):
            try:
                callback(dict(event))
            except Exception:
                continue

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        self._dispatch_client_event(None, event, generation_token=0)

    def _require_start_catalog(
        self,
        data_types: DataTypeCatalog | None,
    ) -> bool:
        if not isinstance(data_types, DataTypeCatalog):
            self._emit_protocol_error(
                "start_run requires the authoritative data-type catalog"
            )
            return False
        if not data_types.is_frozen:
            self._emit_protocol_error("data-type catalog must be frozen")
            return False
        return True

    @staticmethod
    def _viewer_route_ids(
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> tuple[str, str, str]:
        run_id = str(kwargs.pop("run_id", "") or "").strip()
        workspace_id = str(
            kwargs.get("workspace_id", args[0] if args else "") or ""
        ).strip()
        session_id = str(
            kwargs.get("session_id", args[2] if len(args) > 2 else "") or ""
        ).strip()
        return run_id, workspace_id, session_id

    def _remember_requested_session_owner(
        self,
        *,
        client: Any,
        workspace_id: str,
        session_id: str,
        node_id: str = "",
        request_id: str = "",
    ) -> None:
        if not workspace_id or not session_id:
            return
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            session_key = (workspace_id, session_id)
            self._session_node_ids[session_key] = node_id
            if request_id:
                route = self._provisional_viewer_routes.get(session_key)
                if route is None:
                    previous_client = self._session_clients.get(session_key)
                    previous_generation = self._session_client_generations.get(
                        session_key,
                        (
                            self._client_generation_token(previous_client)
                            if previous_client is not None
                            else 0
                        ),
                    )
                    if (
                        previous_client is not None
                        and previous_generation
                        != self._client_generation_token(previous_client)
                    ):
                        previous_client = None
                        previous_generation = 0
                    route = _ProvisionalViewerRoute(
                        session_key=session_key,
                        baseline_client=previous_client,
                        baseline_generation=previous_generation,
                        baseline_request_order=0,
                        requests=[],
                    )
                    self._provisional_viewer_routes[session_key] = route
                generation = self._client_generation_token(client)
                self._next_viewer_request_order += 1
                route.requests.append(
                    (
                        self._next_viewer_request_order,
                        request_id,
                        client,
                        generation,
                    )
                )
                self._provisional_request_sessions[request_id] = session_key
                self._apply_provisional_viewer_route_locked(route)
            else:
                self._session_clients[session_key] = client
                self._session_client_generations[session_key] = (
                    self._client_generation_token(client)
                )

    def _viewer_client(
        self,
        *,
        run_id: str = "",
        workspace_id: str = "",
        session_id: str = "",
        allow_unowned_fallback: bool = False,
    ) -> Any | None:
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            if run_id and run_id in self._run_clients:
                client = self._run_clients[run_id]
                route_generation = self._run_client_generations.get(
                    run_id,
                    self._client_generation_token(client),
                )
                if route_generation == self._client_generation_token(client):
                    return client
                self._active_clients.pop(run_id, None)
                self._run_clients.pop(run_id, None)
                self._run_client_generations.pop(run_id, None)
                self._run_generation_snapshots.pop(run_id, None)
                self._run_workspace_ids.pop(run_id, None)
                if not allow_unowned_fallback:
                    return None
            session_key = (workspace_id, session_id)
            if workspace_id and session_id and session_key in self._session_clients:
                client = self._session_clients[session_key]
                route_generation = self._session_client_generations.get(
                    session_key,
                    self._client_generation_token(client),
                )
                if route_generation == self._client_generation_token(client):
                    return client
                self._session_clients.pop(session_key, None)
                self._session_client_generations.pop(session_key, None)
                if not allow_unowned_fallback:
                    return None
            if workspace_id and workspace_id in self._workspace_clients:
                client = self._workspace_clients[workspace_id]
                route_generation = self._workspace_client_generations.get(
                    workspace_id,
                    self._client_generation_token(client),
                )
                if route_generation == self._client_generation_token(client):
                    return client
                self._workspace_clients.pop(workspace_id, None)
                self._workspace_client_generations.pop(workspace_id, None)
                if not allow_unowned_fallback:
                    return None
            if not allow_unowned_fallback:
                return None
            active_clients = tuple(
                {
                    id(client): client for client in self._active_clients.values()
                }.values()
            )
        if len(active_clients) == 1:
            return active_clients[0]
        return self._process_client

    def _clear_viewer_owners(self) -> None:
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            self._active_clients.clear()
            self._run_clients.clear()
            self._run_client_generations.clear()
            self._run_generation_snapshots.clear()
            self._run_workspace_ids.clear()
            self._workspace_clients.clear()
            self._workspace_client_generations.clear()
            self._session_clients.clear()
            self._session_client_generations.clear()
            self._session_node_ids.clear()
            self._provisional_viewer_routes.clear()
            self._provisional_request_sessions.clear()
            self._next_viewer_request_order = 0
            self._terminal_run_ids_seen.clear()

    def _assert_registry_replaceable_locked(self) -> None:
        self._ensure_route_generation_maps_locked()
        if self._active_clients:
            raise DataTypeCatalogError(
                "Cannot replace the registry during an active run"
            )
        if self._session_clients or self._provisional_viewer_routes:
            raise DataTypeCatalogError(
                "Cannot replace the registry while viewer routes remain active"
            )

    @contextmanager
    def registry_publication_guard(self):  # noqa: ANN201
        lock = getattr(self, "_registry_publication_lock", None)
        if lock is None:
            lock = self._registry_publication_lock = threading.RLock()
        with lock:
            yield

    @_registry_admitted
    def assert_registry_replaceable(self) -> None:
        with self._active_lock:
            self._assert_registry_replaceable_locked()
        for client in (
            self._process_client,
            self._external_python_client,
            self._trusted_client,
        ):
            client.assert_registry_replaceable()

    @_registry_admitted
    def replace_registry(self, registry: NodeRegistry) -> bool:
        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        requested_fingerprint = registry.contract_fingerprint()
        published_registry = self._published_registry
        if (
            published_registry is not None
            and published_registry.contract_fingerprint() == requested_fingerprint
        ):
            return False
        with self._active_lock:
            self._assert_registry_replaceable_locked()
        retirement_results = tuple(
            client.replace_registry(registry)
            for client in (
                self._process_client,
                self._external_python_client,
                self._trusted_client,
            )
        )
        retired = any(retirement_results)
        self._published_registry = registry
        if retired:
            self._clear_viewer_owners()
        return retired

    def _emit_protocol_error(
        self,
        message: str,
        *,
        run_id: str = "",
        command: str = "start_run",
    ) -> None:
        self._dispatch_event(
            event_to_dict(
                ProtocolErrorEvent(
                    run_id=run_id,
                    command=command,
                    error=message,
                ),
                catalog=None,
            )
        )

    @_registry_admitted
    def start_run(
        self,
        project_path: str,
        workspace_id: str,
        trigger: dict[str, Any] | None = None,
        *,
        execution_backend: Any = None,
        target_node_ids: tuple[str, ...] | list[str] | None = None,
        trigger_publications: dict[str, SettledPortResult] | None = None,
        trigger_captures: dict[str, SettledPortResult] | None = None,
        clicked_trigger_node_id: str = "",
        data_types: DataTypeCatalog | None = None,
        plugin_bundles: tuple[PluginBundleRef, ...] = (),
        plugin_fingerprint: str = EMPTY_PLUGIN_FINGERPRINT,
        registry_contract_fingerprint: str = EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
        addon_runtime_config: tuple[tuple[str, bool], ...] = (),
    ) -> str:
        if not self._require_start_catalog(data_types):
            return ""
        trigger_payload = dict(trigger or {})
        command_target_node_ids = trigger_payload.pop(
            "target_node_ids", target_node_ids or ()
        )
        command_trigger_publications = trigger_payload.pop(
            "trigger_publications", trigger_publications or {}
        )
        command_trigger_captures = trigger_payload.pop(
            "trigger_captures", trigger_captures or {}
        )
        command_clicked_trigger_node_id = trigger_payload.pop(
            "clicked_trigger_node_id", clicked_trigger_node_id
        )
        raw_backend_policy = execution_backend
        explicit_backend = raw_backend_policy is not None
        if raw_backend_policy is None:
            if "execution_backend" in trigger_payload:
                raw_backend_policy = trigger_payload.pop("execution_backend", None)
                explicit_backend = True
        else:
            trigger_payload.pop("execution_backend", None)

        runtime_snapshot = trigger_payload.get("runtime_snapshot")
        workflow_python_path = workflow_python_path_from_snapshot(runtime_snapshot)
        if not explicit_backend:
            if workflow_python_path:
                raw_backend_policy = {
                    "requested_backend": EXTERNAL_SUBPROCESS_BACKEND,
                    "allow_external_subprocess": True,
                    "python_executable": workflow_python_path,
                    "reason": "workflow_python_path",
                }
        try:
            selection = self._orchestrator.select(raw_backend_policy)
        except (TypeError, ValueError) as exc:
            self._emit_protocol_error(str(exc))
            return ""

        if selection.backend_id == EXTERNAL_SUBPROCESS_BACKEND:
            python_executable = normalize_path_text(selection.python_executable)
            if not python_executable:
                if workflow_python_path:
                    python_executable = workflow_python_path
                else:
                    self._emit_protocol_error(
                        "External Python workflow execution requires python_executable "
                        "or Workflow Settings > Environment > Workflow Override. "
                        "Use Create / Repair Managed Runtime to create a managed "
                        "Python environment."
                    )
                    return ""
            python_environment = resolve_python_environment(python_executable)
            if not python_environment.valid:
                self._emit_protocol_error(python_environment.error)
                return ""
            selection = replace(
                selection,
                python_executable=python_environment.python_executable,
                reason=(
                    selection.reason
                    or ("workflow_python_path" if workflow_python_path else "")
                ),
            )

        if selection.backend_id == EXTERNAL_SUBPROCESS_BACKEND:
            client = self._external_python_client
        elif selection.backend_id == TRUSTED_IN_PROCESS_BACKEND:
            client = self._trusted_client
        else:
            client = self._process_client
        self._client_selections[id(client)] = selection
        self.retire_workspace(workspace_id)
        previous_catalog_generation = self._client_generation_token(client)
        run_id = client.start_run(
            project_path,
            workspace_id,
            trigger=trigger_payload,
            execution_backend=selection,
            target_node_ids=command_target_node_ids,
            trigger_publications=command_trigger_publications,
            trigger_captures=command_trigger_captures,
            clicked_trigger_node_id=command_clicked_trigger_node_id,
            data_types=data_types,
            plugin_bundles=plugin_bundles,
            plugin_fingerprint=plugin_fingerprint,
            registry_contract_fingerprint=registry_contract_fingerprint,
            addon_runtime_config=addon_runtime_config,
        )
        current_catalog_generation = self._client_generation_token(client)
        run_generation_snapshot = (
            self._generation_snapshot_for_client(
                client,
                selection,
                registry_contract_fingerprint=registry_contract_fingerprint,
            )
            if run_id
            else None
        )
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            if previous_catalog_generation != current_catalog_generation:
                self._forget_client_generation_locked(client)
            if run_id:
                if run_id not in self._terminal_run_ids_seen:
                    self._active_clients[run_id] = client
                else:
                    self._terminal_run_ids_seen.discard(run_id)
                self._run_clients[run_id] = client
                self._run_client_generations[run_id] = current_catalog_generation
                if run_generation_snapshot is not None:
                    self._run_generation_snapshots[run_id] = run_generation_snapshot
                self._run_workspace_ids[run_id] = str(workspace_id).strip()
                if str(workspace_id).strip():
                    self._workspace_clients[str(workspace_id).strip()] = client
                    self._workspace_client_generations[str(workspace_id).strip()] = (
                        current_catalog_generation
                    )
                self._trim_viewer_run_owners_locked()
        return run_id

    def retire_workspace(self, workspace_id: str) -> int:
        normalized = str(workspace_id or "").strip()
        if not normalized:
            raise ValueError("workspace_id is required")
        results: list[int] = []
        errors: list[BaseException] = []
        result_lock = threading.Lock()

        def retire(client: Any) -> None:
            try:
                count = client.retire_workspace(normalized)
                with result_lock:
                    results.append(count)
            except BaseException as exc:  # noqa: BLE001
                with result_lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=retire, args=(client,), daemon=True)
            for client in (
                self._process_client,
                self._trusted_client,
                self._external_python_client,
            )
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 11.0
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            raise TimeoutError("Workspace retirement exceeded its shared bound")
        if errors:
            raise RuntimeError(f"Workspace retirement failed: {errors[0]}") from errors[0]
        return sum(results)

    def _client_for_run(self, run_id: str) -> Any:
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            client = self._active_clients.get(run_id)
            if client is None:
                return None
            route_generation = self._run_client_generations.get(
                run_id,
                self._client_generation_token(client),
            )
            if route_generation == self._client_generation_token(client):
                return client
            self._active_clients.pop(run_id, None)
            self._run_clients.pop(run_id, None)
            self._run_client_generations.pop(run_id, None)
            self._run_generation_snapshots.pop(run_id, None)
            self._run_workspace_ids.pop(run_id, None)
        return None

    def lease_solution_resource(
        self,
        run_id: str,
        value: Any,
        *,
        owner_scope: str,
    ) -> tuple[Any, ExecutionResourceLease] | None:
        if not isinstance(value, RuntimeHandleRef):
            return None
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            client = self._run_clients.get(str(run_id).strip())
            snapshot = self._run_generation_snapshots.get(str(run_id).strip())
        if (
            client is not self._trusted_client
            or snapshot is None
            or value.worker_generation != snapshot.runtime_generation
        ):
            return None
        try:
            leased = client._worker_services.lease_handle(  # noqa: SLF001
                value,
                owner_scope=str(owner_scope).strip(),
            )
        except (LookupError, RuntimeError, TypeError, ValueError):
            return None
        return leased, ExecutionResourceLease(client=client, value=leased)

    @staticmethod
    def release_solution_resource(lease: Any) -> None:
        if not isinstance(lease, ExecutionResourceLease):
            return
        try:
            lease.client._worker_services.release_handle(lease.value)  # noqa: SLF001
        except (LookupError, RuntimeError, TypeError, ValueError):
            return

    def pause_run(self, run_id: str) -> None:
        client = self._client_for_run(run_id)
        if client is not None:
            client.pause_run(run_id)

    def resume_run(self, run_id: str) -> None:
        client = self._client_for_run(run_id)
        if client is not None:
            client.resume_run(run_id)

    def stop_run(self, run_id: str) -> None:
        client = self._client_for_run(run_id)
        if client is not None:
            client.stop_run(run_id)

    @_registry_admitted
    def open_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        run_id, workspace_id, session_id = self._viewer_route_ids(args, kwargs)
        client = self._viewer_client(
            run_id=run_id,
            workspace_id=workspace_id,
            session_id=session_id,
            allow_unowned_fallback=True,
        )
        if client is None:
            return ""
        request_id_factory = getattr(client, "_next_viewer_request_id", None)
        request_id = str(request_id_factory()) if callable(request_id_factory) else ""
        self._remember_requested_session_owner(
            client=client,
            workspace_id=workspace_id,
            session_id=session_id,
            node_id=str(
                kwargs.get("node_id", args[1] if len(args) > 1 else "") or ""
            ).strip(),
            request_id=request_id,
        )
        if request_id:
            kwargs["_request_id"] = request_id
        result = client.open_viewer_session(*args, **kwargs)
        if request_id:
            with self._active_lock:
                self._refresh_provisional_request_generation_locked(
                    request_id=request_id,
                    client=client,
                    generation_token=self._client_generation_token(client),
                )
        return result

    def update_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        run_id, workspace_id, session_id = self._viewer_route_ids(args, kwargs)
        client = self._viewer_client(
            run_id=run_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if client is None:
            return ""
        return client.update_viewer_session(*args, **kwargs)

    def close_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        run_id, workspace_id, session_id = self._viewer_route_ids(args, kwargs)
        client = self._viewer_client(
            run_id=run_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if client is None:
            return ""
        return client.close_viewer_session(*args, **kwargs)

    def materialize_viewer_data(self, *args: Any, **kwargs: Any) -> str:
        run_id, workspace_id, session_id = self._viewer_route_ids(args, kwargs)
        client = self._viewer_client(
            run_id=run_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if client is None:
            return ""
        return client.materialize_viewer_data(*args, **kwargs)

    def query_viewer_session(
        self,
        workspace_id: str,
        node_id: str,
        session_id: str,
        *,
        run_id: str = "",
        backend_id: str = "",
        query_type: str,
        payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        client = self._viewer_client(
            run_id=run_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if client is None:
            return ""
        return client.query_viewer_session(
            workspace_id,
            node_id,
            session_id,
            backend_id=backend_id,
            query_type=query_type,
            payload=payload,
            options=options,
        )

    def _commit_backend_viewer_invalidation_snapshot(
        self,
        reservation: ViewerInvalidationReservation,
    ) -> set[str]:
        with self._active_lock:
            plan = self._plan_backend_viewer_invalidation_snapshot_locked(reservation)
            self._apply_backend_viewer_invalidation_plan_locked(plan)
        return set(plan.retired_request_ids)

    def _plan_backend_viewer_invalidation_snapshot_locked(
        self,
        reservation: ViewerInvalidationReservation,
    ) -> _BackendViewerInvalidationPlan:
        self._ensure_route_generation_maps_locked()
        retired_request_ids: set[str] = set()
        workspace_epochs = dict(self._workspace_viewer_epochs)
        node_epochs = dict(self._node_viewer_epochs)
        workspace_clients = dict(self._workspace_clients)
        workspace_client_generations = dict(self._workspace_client_generations)
        session_clients = dict(self._session_clients)
        session_client_generations = dict(self._session_client_generations)
        session_node_ids = dict(self._session_node_ids)
        provisional_routes = dict(self._provisional_viewer_routes)
        provisional_request_sessions = dict(self._provisional_request_sessions)
        snapshot = reservation.projection_snapshot
        node_epoch_lookup = dict(snapshot.node_epochs)
        current_workspace_epoch = workspace_epochs.get(reservation.workspace_id, 0)
        if reservation.node_ids is None:
            if snapshot.node_epochs:
                raise ValueError("global viewer invalidation forbids node epochs")
            if snapshot.workspace_epoch != current_workspace_epoch + 1:
                raise ValueError(
                    "global backend viewer workspace epoch must advance locally once"
                )
            workspace_epochs[reservation.workspace_id] = snapshot.workspace_epoch
            node_epochs = {
                key: epoch
                for key, epoch in node_epochs.items()
                if key[0] != reservation.workspace_id
            }
        else:
            if snapshot.workspace_epoch != current_workspace_epoch:
                raise ValueError(
                    "scoped backend viewer invalidation must retain the local workspace epoch"
                )
            if tuple(node_epoch_lookup) != reservation.node_ids:
                raise ValueError("backend viewer node epochs do not match filter")
            for node_id, epoch in snapshot.node_epochs:
                key = (reservation.workspace_id, node_id)
                if epoch != node_epochs.get(key, 0) + 1:
                    raise ValueError(
                        "backend viewer node epoch must advance locally once"
                    )
                node_epochs[key] = epoch
        cleanup_node_ids = reservation.node_ids
        affected_session_keys = tuple(
            session_key
            for session_key, node_id in session_node_ids.items()
            if session_key[0] == reservation.workspace_id
            and (cleanup_node_ids is None or node_id in cleanup_node_ids)
        )
        for session_key in affected_session_keys:
            session_clients.pop(session_key, None)
            session_client_generations.pop(session_key, None)
            session_node_ids.pop(session_key, None)
            route = provisional_routes.pop(session_key, None)
            if route is not None:
                for _order, request_id, _client, _generation in route.requests:
                    retired_request_ids.add(request_id)
                    provisional_request_sessions.pop(request_id, None)
        remaining_workspace_sessions = any(
            session_key[0] == reservation.workspace_id
            for session_key in session_clients
        )
        if cleanup_node_ids is None or not remaining_workspace_sessions:
            workspace_clients.pop(reservation.workspace_id, None)
            workspace_client_generations.pop(reservation.workspace_id, None)
        return _BackendViewerInvalidationPlan(
            workspace_epochs=workspace_epochs,
            node_epochs=node_epochs,
            workspace_clients=workspace_clients,
            workspace_client_generations=workspace_client_generations,
            session_clients=session_clients,
            session_client_generations=session_client_generations,
            session_node_ids=session_node_ids,
            provisional_routes=provisional_routes,
            provisional_request_sessions=provisional_request_sessions,
            retired_request_ids=frozenset(retired_request_ids),
        )

    def _apply_backend_viewer_invalidation_plan_locked(
        self, plan: _BackendViewerInvalidationPlan
    ) -> None:
        self._workspace_viewer_epochs = plan.workspace_epochs
        self._node_viewer_epochs = plan.node_epochs
        self._workspace_clients = plan.workspace_clients
        self._workspace_client_generations = plan.workspace_client_generations
        self._session_clients = plan.session_clients
        self._session_client_generations = plan.session_client_generations
        self._session_node_ids = plan.session_node_ids
        self._provisional_viewer_routes = plan.provisional_routes
        self._provisional_request_sessions = plan.provisional_request_sessions

    def invalidate_viewer_requests(
        self,
        workspace_id: str,
        node_ids: Iterable[str] | None,
    ) -> int:
        self._ensure_viewer_invalidation_state()
        with self._viewer_invalidation_lock:
            return self._invalidate_viewer_requests_now(workspace_id, node_ids)

    def _invalidate_viewer_requests_now(
        self,
        workspace_id: str,
        node_ids: Iterable[str] | None,
    ) -> int:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            raise ValueError("workspace_id is required")
        normalized_node_ids = _ExecutionClientCommon._normalize_viewer_node_ids(
            node_ids
        )
        if normalized_node_ids == ():
            return 0
        retired_request_ids: set[str] = set()
        for child in (
            self._process_client,
            self._trusted_client,
            self._external_python_client,
        ):
            retired_request_ids.update(
                child._invalidate_viewer_requests_with_ids(  # noqa: SLF001
                    normalized_workspace_id, normalized_node_ids
                )
            )
        with self._active_lock:
            self._ensure_route_generation_maps_locked()
            if normalized_node_ids is None:
                self._workspace_viewer_epochs[normalized_workspace_id] = (
                    self._workspace_viewer_epochs.get(normalized_workspace_id, 0) + 1
                )
                for key in tuple(self._node_viewer_epochs):
                    if key[0] == normalized_workspace_id:
                        self._node_viewer_epochs.pop(key, None)
            else:
                for node_id in normalized_node_ids:
                    key = (normalized_workspace_id, node_id)
                    self._node_viewer_epochs[key] = (
                        self._node_viewer_epochs.get(key, 0) + 1
                    )
            affected_session_keys = tuple(
                session_key
                for session_key, node_id in self._session_node_ids.items()
                if session_key[0] == normalized_workspace_id
                and (normalized_node_ids is None or node_id in normalized_node_ids)
            )
            for session_key in affected_session_keys:
                self._session_clients.pop(session_key, None)
                self._session_client_generations.pop(session_key, None)
                self._session_node_ids.pop(session_key, None)
                route = self._provisional_viewer_routes.pop(session_key, None)
                if route is not None:
                    for _order, request_id, _client, _generation in route.requests:
                        retired_request_ids.add(request_id)
                        self._provisional_request_sessions.pop(request_id, None)
            remaining_workspace_sessions = any(
                session_key[0] == normalized_workspace_id
                for session_key in self._session_clients
            )
            if normalized_node_ids is None or not remaining_workspace_sessions:
                self._workspace_clients.pop(normalized_workspace_id, None)
                self._workspace_client_generations.pop(normalized_workspace_id, None)
        return len(retired_request_ids)

    def shutdown(self) -> None:
        self._ensure_viewer_invalidation_state()
        with self._viewer_invalidation_lock:
            viewer_reservations = tuple(self._viewer_invalidation_reservations.values())
        for viewer_reservation in viewer_reservations:
            self.cancel_viewer_invalidation(viewer_reservation)
        with self._viewer_invalidation_lock:
            self._viewer_commit_publication_pending.clear()
            self._viewer_commit_event_buffers.clear()
        with self._active_lock:
            reservation_map = getattr(self, "_run_reservations", {})
            reservations = tuple(reservation_map.values())
            reservation_map.clear()
        for reservation, client in reservations:
            client._release_start_run(reservation.run_id)  # noqa: SLF001
        self._process_client.shutdown()
        self._trusted_client.shutdown()
        self._external_python_client.shutdown()
        self._clear_viewer_owners()
