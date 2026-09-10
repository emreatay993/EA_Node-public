# Purpose: Own the Qt-free CorexRuntime lifecycle, preparation/dispatch, solution state, and viewer forwarding.
# Map: subsystems/execution.md
# Tests: tests/test_runtime.py, tests/test_runtime_current_results.py
# Landmarks: CorexRuntime; prepare_execution; dispatch_prepared; run
"""Qt-free Corex runtime API and CLI entry point."""

from __future__ import annotations

import copy
import json
import os
import queue
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution.execution_plan import ExecutionPlan
from ea_node_editor.execution.prepared_execution import (
    MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION,
    MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES,
    MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION,
    InvalidationResult,
    PreparedAction,
    PreparedDispatchEnvelope,
    PreparedExecution,
    PreparedNodeDecision,
    RecomputeMode,
    SolutionStateChangedEvent,
)
from ea_node_editor.execution.project_loader import LoadedProject, load_project
from ea_node_editor.execution.project_solution import (
    ProjectSolutionAdoptionResult,
    ProjectSolutionCandidateResult,
    ProjectSolutionGcResult,
    ProjectSolutionSaveResult,
    ProjectSolutionSaveSnapshot,
    project_solution_snapshot_token,
)
from ea_node_editor.execution.protocol_codec import (
    coerce_start_run_command,
)
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.runtime_requests import (
    CancellationRequest,
    ExecutionEvent,
    ExecutionEventCallback,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    WorkspaceSelection,
)
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotContext,
    build_runtime_snapshot,
    coerce_runtime_snapshot,
)
from ea_node_editor.execution.solution_backend import (
    DurableBackendOpenResult,
    DurableSolutionBackendFactory,
)
from ea_node_editor.execution.solution_identity import (
    assemble_node_solution,
    canonical_digest,
)
from ea_node_editor.execution.solution_store import (
    CapturedNodeSolution,
    SolutionStore,
)
from ea_node_editor.execution.worker_runtime import RuntimeArtifactService
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2DRef,
    DataTree,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TabularDataRef,
    TabularWindowRef,
)
from ea_node_editor.runtime_contracts.settled_results import (
    SettledPortResult,
    settled_output_mapping_from_payload,
)
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionRecord,
    SolutionResidency,
)

TERMINAL_EVENT_TYPES = frozenset({"run_completed", "run_failed", "run_stopped"})


RUN_SCOPED_EVENT_TYPES = frozenset(
    {
        "run_preflight_accepted",
        "viewer_invalidation_committed",
        "run_started",
        "run_state",
        "run_completed",
        "run_failed",
        "run_stopped",
        "node_started",
        "node_settled",
        "observation_invalidation_requested",
        "trigger_capture_settled",
        "trigger_published",
        "log",
        "protocol_error",
    }
)


@dataclass(slots=True)
class _ProjectSolutionSaveContext:
    snapshot: ProjectSolutionSaveSnapshot
    binding_revision: int
    destination_project_path: str = ""
    result: ProjectSolutionSaveResult | None = None
    candidate: DurableBackendOpenResult | None = None
    adopted: bool = False
    gc_candidate_relative_paths: tuple[str, ...] = ()
    gc_scan_complete: bool = True


class ExecutionEventStream:
    def __init__(self) -> None:
        self._events: queue.Queue[ExecutionEvent] = queue.Queue()
        self._callbacks: list[ExecutionEventCallback] = []
        self._lock = threading.RLock()

    def subscribe(self, callback: ExecutionEventCallback) -> Callable[[], None]:
        with self._lock:
            self._callbacks.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._callbacks.remove(callback)
                except ValueError:
                    return

        return _unsubscribe

    def publish(self, event: Mapping[str, Any]) -> None:
        payload = copy.deepcopy(dict(event))
        self._events.put(payload)
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback(copy.deepcopy(payload))
            except Exception:
                continue

    def next_event(self, timeout: float | None = None) -> ExecutionEvent:
        return self._events.get(timeout=timeout)

    def iter_events(
        self,
        *,
        timeout: float | None = None,
        stop_after_terminal: bool = False,
    ) -> Iterator[ExecutionEvent]:
        while True:
            event = self.next_event(timeout=timeout)
            yield event
            if (
                stop_after_terminal
                and str(event.get("type", "")) in TERMINAL_EVENT_TYPES
            ):
                return


class CorexRuntime:
    def __init__(
        self,
        *,
        client: Any | None = None,
        registry: NodeRegistry | None = None,
        solution_store: SolutionStore | None = None,
        solution_repository_factory: DurableSolutionBackendFactory | None = None,
    ) -> None:
        self._client = client or ExecutionBackendClient()
        self._owns_client = client is None
        self._registry = registry
        self._lifecycle_lock = threading.RLock()
        self._registry_publication_lock = threading.RLock()
        self._solution_store = solution_store or SolutionStore()
        self._solution_repository_factory = solution_repository_factory
        self._project_solution_binding_revision = 0
        self._project_solution_save_contexts: dict[
            str, _ProjectSolutionSaveContext
        ] = {}
        self._retired_solution_backends: list[Any] = []
        self._generation_snapshots: dict[str, Any] = {}
        self._run_artifact_services: dict[str, RuntimeArtifactService] = {}
        self._event_stream = ExecutionEventStream()
        self._generation_event_local = threading.local()
        self._client.subscribe(self._handle_client_event)
        subscribe_generation_events = getattr(
            self._client,
            "subscribe_generation_events",
            None,
        )
        if callable(subscribe_generation_events):
            subscribe_generation_events(self._handle_generation_event)

    @property
    def solution_store(self) -> SolutionStore:
        return self._solution_store

    @property
    def events(self) -> ExecutionEventStream:
        return self._event_stream

    def subscribe(self, callback: ExecutionEventCallback) -> Callable[[], None]:
        return self._event_stream.subscribe(callback)

    @contextmanager
    def registry_publication_guard(self) -> Iterator[None]:
        with self._lifecycle_lock:
            client_guard = getattr(self._client, "registry_publication_guard", None)
            if callable(
                getattr(type(self._client), "registry_publication_guard", None)
            ):
                with client_guard():
                    yield
                return
            with self._registry_publication_lock:
                yield

    def assert_registry_replaceable(self) -> None:
        with self.registry_publication_guard():
            assert_replaceable = getattr(
                self._client,
                "assert_registry_replaceable",
                None,
            )
            if callable(assert_replaceable):
                assert_replaceable()

    def replace_registry(self, registry: NodeRegistry) -> bool:
        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        solution_events: tuple[InvalidationResult, ...] = ()
        with self._lifecycle_lock, self.registry_publication_guard():
            previous_fingerprint = (
                self._registry.contract_fingerprint()
                if self._registry is not None
                else ""
            )
            replace_client_registry = getattr(self._client, "replace_registry", None)
            retired = (
                bool(replace_client_registry(registry))
                if callable(replace_client_registry)
                else False
            )
            self._registry = registry
            if (
                previous_fingerprint
                and previous_fingerprint != registry.contract_fingerprint()
            ):
                self._project_solution_binding_revision += 1
                self._release_all_solution_resources()
                solution_events = self._solution_store.reset_runtime_generation(
                    "registry_generation_replaced"
                )
                self._run_artifact_services.clear()
        self._publish_solution_state_results(solution_events)
        return retired

    def load_project(
        self,
        project_path: str | Path,
        *,
        extra_plugin_dirs: Sequence[Path] | None = None,
    ) -> LoadedProject:
        return load_project(
            project_path,
            registry=self._registry,
            extra_plugin_dirs=extra_plugin_dirs,
        )

    def prepare_request(self, request: ExecutionRequest) -> ExecutionRequest:
        trigger, raw_snapshot, execution_backend = (
            request.trigger_without_runtime_snapshot()
        )
        if raw_snapshot is not None and self._registry is None:
            raise ValueError(
                "raw runtime snapshots require an authoritative node registry"
            )
        catalog = self._registry.data_types if self._registry is not None else None
        runtime_snapshot = coerce_runtime_snapshot(raw_snapshot, catalog=catalog)
        workspace_id = str(request.workspace_id or "").strip()
        project_path = str(request.project_path or "").strip()

        if runtime_snapshot is None:
            loaded_project = self.load_project(project_path)
            self.replace_registry(loaded_project.registry)
            workspace = loaded_project.select_workspace(
                WorkspaceSelection(workspace_id)
            )
            runtime_snapshot = build_runtime_snapshot(
                loaded_project.project,
                workspace_id=workspace.workspace_id,
                registry=loaded_project.registry,
            )
            workspace_id = workspace.workspace_id
            project_path = str(loaded_project.project_path)
        else:
            if not workspace_id:
                workspace_id = str(runtime_snapshot.active_workspace_id or "").strip()
            runtime_snapshot.workspace(workspace_id)

        return ExecutionRequest(
            project_path=project_path,
            workspace_id=workspace_id,
            trigger=trigger,
            runtime_snapshot=runtime_snapshot,
            execution_backend=execution_backend,
            target_node_ids=tuple(request.target_node_ids),
            trigger_publications=dict(request.trigger_publications),
            trigger_captures=dict(request.trigger_captures),
            clicked_trigger_node_id=str(request.clicked_trigger_node_id),
            recompute_mode=request.recompute_mode,
        )

    def prepare_execution(self, request: ExecutionRequest) -> PreparedExecution:
        with self._lifecycle_lock:
            prepared_request, candidate_registry = self._prepare_candidate_request(
                request
            )
            runtime_snapshot = prepared_request.runtime_snapshot
            assert isinstance(runtime_snapshot, RuntimeSnapshot)
            resolve_selection = getattr(
                self._client,
                "resolve_execution_selection",
                None,
            )
            if not callable(resolve_selection):
                raise RuntimeError(
                    "execution client does not support prepared generation routing"
                )
            selection = resolve_selection(
                prepared_request.execution_backend,
                runtime_snapshot,
            )
            preview_environment = getattr(
                self._client,
                "preview_execution_environment",
                None,
            )
            preview_environment_digest = ""
            if callable(preview_environment):
                preview_environment_digest = preview_environment(
                    selection,
                    candidate_registry,
                )
            generation_snapshot = self._client.execution_generation_snapshot(
                selection,
                registry_contract_fingerprint=(
                    candidate_registry.contract_fingerprint()
                ),
            )
            if not generation_snapshot.available and preview_environment_digest:
                generation_snapshot = replace(
                    generation_snapshot,
                    environment_digest=preview_environment_digest,
                )
            workspace = compile_runtime_snapshot(
                runtime_snapshot,
                workspace_id=prepared_request.workspace_id,
                registry=candidate_registry,
            )
            plan = ExecutionPlan(
                workspace,
                candidate_registry,
                target_node_ids=prepared_request.target_node_ids,
                clicked_trigger_node_id=prepared_request.clicked_trigger_node_id,
                trigger_capture_node_ids=tuple(
                    sorted(prepared_request.trigger_captures)
                ),
            )
            interface_plan = (
                plan
                if not prepared_request.target_node_ids
                and not prepared_request.clicked_trigger_node_id
                else ExecutionPlan(workspace, candidate_registry)
            )
            project_id = str(runtime_snapshot.project_id).strip()
            namespace_id = self._solution_store.ensure_project(
                project_id,
                str(prepared_request.project_path),
            )
            preparation_id = f"preparation_{uuid.uuid4().hex}"
            trigger_reservation_id = ""
            reserved_trigger_generation: int | None = None
            if prepared_request.clicked_trigger_node_id and plan.is_trigger(
                prepared_request.clicked_trigger_node_id
            ):
                (
                    trigger_reservation_id,
                    reserved_trigger_generation,
                ) = self._solution_store.reserve_trigger_generation(
                    project_id=project_id,
                    workspace_id=workspace.workspace_id,
                    trigger_node_id=prepared_request.clicked_trigger_node_id,
                    preparation_id=preparation_id,
                )
            try:
                trigger = copy.deepcopy(dict(prepared_request.trigger))
                developer_mode = trigger.pop("developer_mode", False)
                if not isinstance(developer_mode, bool):
                    raise TypeError("developer_mode must be a boolean")
                catalog_fingerprint, catalog_revisions = catalog_agreement(
                    candidate_registry.data_types
                )
                plugin_fingerprint = candidate_registry.plugin_fingerprint()
                registry_fingerprint = candidate_registry.contract_fingerprint()
                trigger_publication_generations = tuple(
                    sorted(
                        (
                            node_id,
                            (
                                reserved_trigger_generation
                                if node_id == prepared_request.clicked_trigger_node_id
                                and reserved_trigger_generation is not None
                                else self._solution_store.trigger_generation(
                                    project_id,
                                    workspace.workspace_id,
                                    node_id,
                                )
                            ),
                        )
                        for node_id in plan.nodes
                        if plan.is_trigger(node_id)
                    )
                )
                envelope = PreparedDispatchEnvelope(
                    project_path=str(prepared_request.project_path),
                    project_id=project_id,
                    workspace_id=workspace.workspace_id,
                    trigger=trigger,
                    runtime_snapshot=runtime_snapshot,
                    execution_backend=selection,
                    target_node_ids=plan.target_nodes,
                    clicked_trigger_node_id=prepared_request.clicked_trigger_node_id,
                    trigger_capture_node_ids=tuple(
                        sorted(prepared_request.trigger_captures)
                    ),
                    trigger_publications=prepared_request.trigger_publications,
                    trigger_captures=prepared_request.trigger_captures,
                    recompute_mode=prepared_request.recompute_mode,
                    developer_mode=developer_mode,
                    catalog_fingerprint=catalog_fingerprint,
                    catalog_revisions=catalog_revisions,
                    plugin_bundles=candidate_registry.plugin_bundle_refs(),
                    plugin_fingerprint=plugin_fingerprint,
                    runtime_registry_fingerprint=runtime_registry_fingerprint(
                        catalog_fingerprint,
                        plugin_fingerprint,
                    ),
                    registry_contract_fingerprint=registry_fingerprint,
                    addon_runtime_config=candidate_registry.addon_runtime_config(),
                    catalog=candidate_registry.data_types,
                )
                decisions, accepted, captures = self._prepare_node_decisions(
                    preparation_id=preparation_id,
                    namespace_id=namespace_id,
                    project_id=project_id,
                    plan=plan,
                    registry=candidate_registry,
                    generation_snapshot=generation_snapshot,
                    recompute_mode=RecomputeMode(prepared_request.recompute_mode),
                    trigger_publication_generations=dict(
                        trigger_publication_generations
                    ),
                    artifact_service=RuntimeArtifactService(
                        runtime_context=RuntimeSnapshotContext.from_snapshot(
                            runtime_snapshot,
                            project_path=prepared_request.project_path,
                        ),
                        data_types=candidate_registry.data_types,
                    ),
                )
                prepared = PreparedExecution(
                    preparation_id=preparation_id,
                    dispatch_envelope=envelope,
                    solution_namespace_id=namespace_id,
                    execution_affecting_workspace_revision=(
                        self._solution_store.workspace_revision(
                            project_id,
                            workspace.workspace_id,
                        )
                    ),
                    runtime_snapshot_fingerprint=canonical_digest(
                        runtime_snapshot.to_document(
                            catalog=candidate_registry.data_types
                        )
                    ),
                    execution_plan_fingerprint=plan.fingerprint,
                    registry_contract_fingerprint=registry_fingerprint,
                    workflow_interface_revision=(
                        interface_plan.workflow_interface_revision
                    ),
                    workflow_interface_digest=(
                        interface_plan.workflow_interface_digest
                    ),
                    execution_environment_digest=generation_snapshot.environment_digest,
                    trigger_publication_generations=(trigger_publication_generations),
                    node_decisions=decisions,
                    accepted_output_payloads=accepted,
                    recompute_node_ids=tuple(
                        item.node_id
                        for item in decisions
                        if item.action is PreparedAction.EXECUTE
                    ),
                    reused_node_ids=tuple(
                        item.node_id
                        for item in decisions
                        if item.action.uses_accepted_output
                    ),
                )
                encoded_size = len(
                    json.dumps(
                        prepared.to_payload(catalog=candidate_registry.data_types),
                        allow_nan=False,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                )
                self._solution_store.register_preparation(
                    prepared,
                    candidate_registry=candidate_registry,
                    plan=plan,
                    captured_nodes=captures,
                    generation_snapshot=generation_snapshot,
                    encoded_size=encoded_size,
                    trigger_reservation_id=trigger_reservation_id,
                )
                return prepared
            except Exception:
                self._solution_store.release_trigger_reservation(trigger_reservation_id)
                raise

    def _prepare_candidate_request(
        self,
        request: ExecutionRequest,
    ) -> tuple[ExecutionRequest, NodeRegistry]:
        trigger, raw_snapshot, execution_backend = (
            request.trigger_without_runtime_snapshot()
        )
        candidate_registry = self._registry
        if raw_snapshot is not None and candidate_registry is None:
            raise ValueError(
                "raw runtime snapshots require an authoritative node registry"
            )
        catalog = (
            candidate_registry.data_types if candidate_registry is not None else None
        )
        runtime_snapshot = coerce_runtime_snapshot(raw_snapshot, catalog=catalog)
        workspace_id = str(request.workspace_id or "").strip()
        project_path = str(request.project_path or "").strip()
        if runtime_snapshot is None:
            loaded_project = load_project(
                project_path,
                registry=candidate_registry,
            )
            candidate_registry = loaded_project.registry
            workspace = loaded_project.select_workspace(
                WorkspaceSelection(workspace_id)
            )
            runtime_snapshot = build_runtime_snapshot(
                loaded_project.project,
                workspace_id=workspace.workspace_id,
                registry=candidate_registry,
            )
            workspace_id = workspace.workspace_id
            project_path = str(loaded_project.project_path)
        else:
            assert candidate_registry is not None
            if not workspace_id:
                workspace_id = str(runtime_snapshot.active_workspace_id).strip()
            runtime_snapshot.workspace(workspace_id)
        assert candidate_registry is not None
        return (
            ExecutionRequest(
                project_path=project_path,
                workspace_id=workspace_id,
                trigger=trigger,
                runtime_snapshot=runtime_snapshot,
                execution_backend=execution_backend,
                target_node_ids=tuple(request.target_node_ids),
                trigger_publications=dict(request.trigger_publications),
                trigger_captures=dict(request.trigger_captures),
                clicked_trigger_node_id=str(request.clicked_trigger_node_id),
                recompute_mode=request.recompute_mode,
            ),
            candidate_registry,
        )

    def _prepare_node_decisions(
        self,
        *,
        preparation_id: str,
        namespace_id: str,
        project_id: str,
        plan: ExecutionPlan,
        registry: NodeRegistry,
        generation_snapshot: Any,
        recompute_mode: RecomputeMode,
        trigger_publication_generations: Mapping[str, int],
        artifact_service: RuntimeArtifactService,
    ) -> tuple[
        tuple[PreparedNodeDecision, ...],
        tuple[Any, ...],
        tuple[CapturedNodeSolution, ...],
    ]:
        workspace_id = plan.workspace.workspace_id
        solution_revision = self._solution_store.workspace_revision(
            project_id, workspace_id
        )
        captures: dict[str, CapturedNodeSolution] = {}
        identity_reasons: dict[str, str] = {}
        keys_by_node: dict[str, str] = {}
        reusable_keys: dict[str, bool] = {}
        for node_id in plan.execution_order:
            if plan.node_specs[node_id].runtime_behavior != "active":
                continue
            capture, identity_reasons[node_id] = self._captured_node_solution(
                preparation_id=preparation_id,
                namespace_id=namespace_id,
                project_id=project_id,
                plan=plan,
                registry=registry,
                node_id=node_id,
                keys_by_node=keys_by_node,
                generation_snapshot=generation_snapshot,
                solution_revision=solution_revision,
                trigger_publication_generations=trigger_publication_generations,
            )
            # Volatile lineage cannot promise repeatable computations. Its detached
            # completed values remain available as CURRENT observations.
            capture = replace(
                capture,
                identity_reuse_eligible=(
                    capture.identity_reuse_eligible
                    and all(
                        reusable_keys[key] for key in capture.dependency_solution_keys
                    )
                ),
            )
            captures[node_id] = capture
            keys_by_node[node_id] = capture.solution_key
            reusable_keys[capture.solution_key] = capture.identity_reuse_eligible

        dependencies = {node_id: [] for node_id in plan.execution_order}
        successors = {node_id: [] for node_id in plan.execution_order}
        for target in plan.execution_order:
            for edge in plan.incoming_edges_for(target):
                if edge.source_node_id in dependencies:
                    dependencies[target].append(
                        (edge.source_node_id, edge.source_port_key)
                    )
                    if not plan.is_trigger(edge.source_node_id):
                        successors[edge.source_node_id].append(target)
        for source, target in plan.hidden_ordering_pairs:
            if source in dependencies and target in dependencies:
                dependencies[target].append((source, None))
                successors[source].append(target)
        for node_id in dependencies:
            if plan.is_trigger(node_id) and (
                node_id != plan.clicked_trigger_node_id
                and node_id not in plan.target_nodes
                or node_id == plan.clicked_trigger_node_id
                and node_id in plan.trigger_capture_node_ids
            ):
                dependencies[node_id] = []

        allow_current = (
            bool(plan.target_nodes)
            and not plan.clicked_trigger_node_id
            and recompute_mode is RecomputeMode.REUSE_VALID
        )
        pending = deque()
        queued: set[str] = set()
        requested_ports: dict[str, set[str]] = {}
        effect_required: set[str] = set()
        recomputed = deque()
        required: set[str] = set()
        tainted: set[str] = set()
        actions: dict[str, PreparedAction] = {}
        reasons: dict[str, str] = {}
        accepted: dict[str, Any] = {}
        sizes: dict[str, int] = {}
        accepted_ports = 0
        accepted_bytes = 0

        def require(node_id: str, port_key: str | None = None) -> None:
            if port_key is None:
                changed = node_id not in effect_required
                effect_required.add(node_id)
            else:
                ports = requested_ports.setdefault(node_id, set())
                changed = port_key not in ports
                ports.add(port_key)
            if (changed or node_id not in required) and node_id not in queued:
                queued.add(node_id)
                pending.append(node_id)

        def require_dependencies(node_id: str) -> None:
            for source, port_key in dependencies[node_id]:
                require(source, port_key)

        for node_id in plan.target_nodes if allow_current else plan.execution_order:
            if node_id in dependencies:
                require(node_id)

        def discard_output(node_id: str) -> None:
            nonlocal accepted_ports, accepted_bytes
            payload = accepted.pop(node_id, None)
            if payload is not None:
                accepted_ports -= payload.output_count
                accepted_bytes -= sizes.pop(node_id)

        def retain_output(node_id: str, payload: Any) -> bool:
            nonlocal accepted_ports, accepted_bytes
            self._validate_prepared_artifacts(
                payload,
                artifact_service=artifact_service,
                catalog=registry.data_types,
            )
            size = len(
                json.dumps(
                    payload.to_payload(catalog=registry.data_types),
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            if (
                len(accepted) + 1 > MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION
                or accepted_ports + payload.output_count
                > MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION
                or accepted_bytes + size > MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES
            ):
                return False
            accepted[node_id] = payload
            sizes[node_id] = size
            accepted_ports += payload.output_count
            accepted_bytes += size
            return True

        def execution_reason(node_id: str) -> str:
            if recompute_mode is RecomputeMode.FORCE_RECOMPUTE:
                return "force_recompute"
            if identity_reasons[node_id]:
                return identity_reasons[node_id]
            if plan.node_specs[node_id].solution_reuse_scope == "never":
                return "solution_reuse_scope_never"
            if not generation_snapshot.available:
                return generation_snapshot.reason or "execution_generation_unavailable"
            if node_id in tainted:
                return "upstream_recompute_required"
            if not captures[node_id].identity_reuse_eligible:
                return "volatile_dependency"
            return ""

        # Demand moves upstream; recomputation moves downstream. Each flag changes
        # once, so a shared executing branch deoptimizes boundaries without rescans.
        while pending or recomputed:
            if recomputed:
                node_id = recomputed.popleft()
                if node_id in tainted:
                    continue
                tainted.add(node_id)
                recomputed.extend(successors[node_id])
                if node_id in required and node_id in captures:
                    if actions[node_id] is PreparedAction.READ_CURRENT:
                        require_dependencies(node_id)
                    discard_output(node_id)
                    actions[node_id] = PreparedAction.EXECUTE
                continue
            node_id = pending.popleft()
            queued.discard(node_id)
            if (
                node_id in required
                and actions.get(node_id) is not PreparedAction.READ_CURRENT
            ):
                continue
            required.add(node_id)
            if node_id not in captures:
                require_dependencies(node_id)
                continue
            discard_output(node_id)
            capture = captures[node_id]
            lookup = dict(
                solution_key=capture.solution_key,
                project_id=project_id,
                workspace_id=workspace_id,
                node_id=node_id,
                runtime_generation=generation_snapshot.runtime_generation,
                catalog=registry.data_types,
            )
            if (
                allow_current
                and node_id not in effect_required
                and not plan.is_trigger(node_id)
                and node_id not in tainted
                and generation_snapshot.available
                and not identity_reasons[node_id]
            ):
                try:
                    current = self._solution_store.current_outputs(
                        **lookup,
                        artifact_context=artifact_service.store,
                        port_keys=tuple(sorted(requested_ports[node_id])),
                    )
                    if current is not None and retain_output(node_id, current[1]):
                        actions[node_id] = PreparedAction.READ_CURRENT
                        continue
                except (KeyError, OSError, TypeError, ValueError):
                    pass  # Invalid or evicted observations require ordinary execution.
            require_dependencies(node_id)
            reason = execution_reason(node_id)
            if not reason:
                record = self._solution_store.select_record(**lookup)
                reason = "no_reusable_record"
                if record is not None:
                    try:
                        payload = self._solution_store.accepted_outputs(
                            record,
                            catalog=registry.data_types,
                            runtime_generation=generation_snapshot.runtime_generation,
                            artifact_context=artifact_service.store,
                        )
                        if retain_output(node_id, payload):
                            actions[node_id] = PreparedAction.REUSE
                            continue
                        reason = "reuse_payload_budget_exceeded"
                    except (KeyError, OSError, TypeError, ValueError):
                        reason = "accepted_output_invalid"
            actions[node_id] = PreparedAction.EXECUTE
            reasons[node_id] = reason
            recomputed.extend(successors[node_id])

        boundaries = frozenset(
            node_id
            for node_id, action in actions.items()
            if action is PreparedAction.READ_CURRENT
        )
        if required != plan.required_node_ids(boundaries):
            raise RuntimeError(
                "current-result demand does not match the execution plan"
            )
        if plan.current_result_ports(boundaries) != {
            node_id: tuple(sorted(requested_ports[node_id])) for node_id in boundaries
        }:
            raise RuntimeError("current-result ports do not match execution demand")
        decisions = []
        for node_id, capture in captures.items():
            action = actions.get(node_id, PreparedAction.PRUNE)
            if action is PreparedAction.READ_CURRENT:
                reason = "current_result_accepted"
            elif action is PreparedAction.REUSE:
                reason = "reusable_record_accepted"
            elif action is PreparedAction.PRUNE:
                reason = "dependency_not_required"
            else:
                reason = execution_reason(node_id) or reasons[node_id]
            decisions.append(
                PreparedNodeDecision(
                    node_id=node_id,
                    action=action,
                    reason_code=reason,
                    solution_key=capture.solution_key,
                    dependency_solution_keys=capture.dependency_solution_keys,
                    accepted_record_id=accepted[node_id].record_id
                    if node_id in accepted
                    else None,
                    accepted_payload_digest=accepted[node_id].commitment_digest()
                    if node_id in accepted
                    else None,
                )
            )
        return (
            tuple(decisions),
            tuple(accepted[node_id] for node_id in captures if node_id in accepted),
            tuple(captures.values()),
        )

    @staticmethod
    def _validate_prepared_artifacts(
        payload: Any,
        *,
        artifact_service: RuntimeArtifactService,
        catalog: Any,
    ) -> None:
        def validate(value: Any) -> None:
            if isinstance(value, RuntimeArtifactRef):
                artifact_service.resolve_path(value)
                return
            if isinstance(value, DataTree):
                for _path, items in value.branches:
                    for item in items:
                        validate(item)
                return
            if isinstance(value, Mapping):
                for item in value.values():
                    validate(item)
                return
            if isinstance(value, Sequence) and not isinstance(
                value,
                (str, bytes, bytearray),
            ):
                for item in value:
                    validate(item)

        for result in payload.decode_outputs(catalog=catalog).values():
            if result.status == "value":
                validate(result.value)

    def _captured_node_solution(
        self,
        *,
        preparation_id: str,
        namespace_id: str,
        project_id: str,
        plan: ExecutionPlan,
        registry: NodeRegistry,
        node_id: str,
        keys_by_node: Mapping[str, str],
        generation_snapshot: Any,
        solution_revision: int,
        trigger_publication_generations: Mapping[str, int],
    ) -> tuple[CapturedNodeSolution, str]:
        spec = plan.node_specs[node_id]
        assembled = assemble_node_solution(
            preparation_id=preparation_id,
            solution_namespace_id=namespace_id,
            workspace_solution_revision=solution_revision,
            plan=plan,
            registry=registry,
            node_id=node_id,
            keys_by_node=keys_by_node,
            execution_environment_digest=generation_snapshot.environment_digest,
            trigger_publication_generations=trigger_publication_generations,
        )
        return (
            CapturedNodeSolution(
                node_id=node_id,
                solution_key=assembled.solution_key,
                captured_revision=self._solution_store.node_revision(
                    project_id,
                    plan.workspace.workspace_id,
                    node_id,
                ),
                dependency_solution_keys=assembled.dependency_solution_keys,
                node_interface_revision=assembled.node_interface_revision,
                node_interface_digest=assembled.node_interface_digest,
                node_contract_digest=assembled.node_contract_digest,
                input_provenance_digest=assembled.input_provenance_digest,
                execution_policy_digest=assembled.execution_policy_digest,
                implementation_digest=assembled.implementation_digest,
                execution_environment_digest=generation_snapshot.environment_digest,
                output_specs=assembled.output_specs,
                solution_reuse_scope=spec.solution_reuse_scope,
                identity_reuse_eligible=(
                    not assembled.reason_code
                    and generation_snapshot.available
                    and spec.solution_reuse_scope != "never"
                ),
            ),
            assembled.reason_code,
        )

    def dispatch_prepared(self, prepared: PreparedExecution) -> str:
        if not isinstance(prepared, PreparedExecution):
            raise TypeError("prepared must be a PreparedExecution")
        solution_events: list[InvalidationResult] = []
        reservation: Any | None = None
        viewer_reservation: Any | None = None
        command: Any | None = None
        candidate_fingerprint = ""
        dispatch_workspace_revision = -1
        preparation_validated = False
        try:
            with self._lifecycle_lock, self.registry_publication_guard():
                entry = self._solution_store.preparation(prepared.preparation_id)
                if entry.prepared != prepared:
                    raise ValueError(
                        "prepared execution does not match registered state"
                    )
                preparation_validated = True
                candidate_registry = entry.candidate_registry
                previous_fingerprint = (
                    self._registry.contract_fingerprint()
                    if self._registry is not None
                    else ""
                )
                candidate_fingerprint = candidate_registry.contract_fingerprint()
                replace_client_registry = getattr(
                    self._client, "replace_registry", None
                )
                if callable(replace_client_registry):
                    replace_client_registry(candidate_registry)
                self._registry = candidate_registry
                if (
                    previous_fingerprint
                    and previous_fingerprint != candidate_fingerprint
                ):
                    self._release_all_solution_resources()
                    solution_events.extend(
                        self._solution_store.adopt_expected_generation(
                            prepared.preparation_id,
                            "registry_generation_replaced",
                        )
                    )
                    self._run_artifact_services.clear()
                pre_reservation_snapshot = self._client.execution_generation_snapshot(
                    prepared.dispatch_envelope.execution_backend,
                    registry_contract_fingerprint=candidate_fingerprint,
                )
                if (
                    entry.generation_snapshot.available
                    and not pre_reservation_snapshot.compatible_with(
                        entry.generation_snapshot
                    )
                ):
                    raise ValueError("prepared_runtime_generation_changed")
                reservation = self._client.reserve_run(
                    prepared.dispatch_envelope.execution_backend,
                    prepared.dispatch_envelope.workspace_id,
                )
                if (
                    entry.generation_snapshot.available
                    and not reservation.generation_snapshot.compatible_with(
                        entry.generation_snapshot
                    )
                ):
                    raise ValueError("prepared_runtime_generation_changed")
                self._validate_prepared_dispatch(
                    prepared,
                    entry=entry,
                    generation_snapshot=reservation.generation_snapshot,
                )
                viewer_node_ids = tuple(
                    decision.node_id
                    for decision in prepared.node_decisions
                    if decision.action is PreparedAction.EXECUTE
                    and entry.plan.node_specs[decision.node_id].surface_family
                    == "viewer"
                )
                viewer_reservation = self._client.reserve_viewer_invalidation(
                    reservation,
                    prepared.preparation_id,
                    viewer_node_ids,
                )
                if not entry.generation_snapshot.available:
                    self._release_all_solution_resources()
                    solution_events.extend(
                        self._solution_store.adopt_expected_generation(
                            prepared.preparation_id,
                            "runtime_generation_replaced",
                        )
                    )
                    self._solution_store.adopt_preparation_generation(
                        prepared.preparation_id,
                        reservation.generation_snapshot,
                    )
                    self._run_artifact_services.clear()
                self._generation_snapshots[reservation.selection.backend_id] = (
                    reservation.generation_snapshot
                )
                runtime_snapshot = prepared.dispatch_envelope.decode_runtime_snapshot(
                    catalog=candidate_registry.data_types
                )
                self._run_artifact_services[reservation.run_id] = (
                    RuntimeArtifactService(
                        runtime_context=RuntimeSnapshotContext.from_snapshot(
                            runtime_snapshot,
                            project_path=prepared.dispatch_envelope.project_path,
                        ),
                        data_types=candidate_registry.data_types,
                    )
                )
                self._solution_store.consume_preparation(
                    prepared.preparation_id,
                    run_id=reservation.run_id,
                    generation_snapshot=reservation.generation_snapshot,
                )
                envelope = prepared.dispatch_envelope
                command = coerce_start_run_command(
                    StartRunCommand(
                        run_id=reservation.run_id,
                        project_path=envelope.project_path,
                        workspace_id=envelope.workspace_id,
                        trigger=envelope.decode_trigger(
                            catalog=candidate_registry.data_types
                        ),
                        runtime_snapshot=runtime_snapshot,
                        execution_backend=envelope.execution_backend,
                        target_node_ids=envelope.target_node_ids,
                        recompute_mode=envelope.recompute_mode.value,
                        trigger_publications=envelope.decode_trigger_publications(
                            catalog=candidate_registry.data_types
                        ),
                        trigger_captures=envelope.decode_trigger_captures(
                            catalog=candidate_registry.data_types
                        ),
                        clicked_trigger_node_id=envelope.clicked_trigger_node_id,
                        developer_mode=envelope.developer_mode,
                        catalog_fingerprint=envelope.catalog_fingerprint,
                        catalog_revisions=envelope.catalog_revisions,
                        plugin_bundles=envelope.plugin_bundles,
                        plugin_fingerprint=envelope.plugin_fingerprint,
                        runtime_registry_fingerprint=envelope.runtime_registry_fingerprint,
                        registry_contract_fingerprint=envelope.registry_contract_fingerprint,
                        addon_runtime_config=envelope.addon_runtime_config,
                        preparation_id=prepared.preparation_id,
                        solution_namespace_id=prepared.solution_namespace_id,
                        execution_affecting_workspace_revision=(
                            prepared.execution_affecting_workspace_revision
                        ),
                        dispatch_runtime_generation=(
                            reservation.generation_snapshot.runtime_generation
                        ),
                        runtime_snapshot_fingerprint=prepared.runtime_snapshot_fingerprint,
                        execution_plan_fingerprint=prepared.execution_plan_fingerprint,
                        workflow_interface_revision=prepared.workflow_interface_revision,
                        workflow_interface_digest=prepared.workflow_interface_digest,
                        execution_environment_digest=prepared.execution_environment_digest,
                        trigger_publication_generations=(
                            prepared.trigger_publication_generations
                        ),
                        node_decisions=prepared.node_decisions,
                        accepted_output_payloads=prepared.accepted_output_payloads,
                        viewer_invalidation_node_ids=viewer_reservation.node_ids,
                        viewer_workspace_invalidation_epoch=(
                            viewer_reservation.workspace_epoch
                        ),
                        viewer_node_invalidation_epochs=(
                            viewer_reservation.node_epochs
                        ),
                        viewer_invalidation_reservation_id=(
                            viewer_reservation.reservation_id
                        ),
                        viewer_epoch_snapshot_digest=(
                            viewer_reservation.snapshot_digest
                        ),
                    ),
                    catalog=candidate_registry.data_types,
                )
                dispatch_workspace_revision = self._solution_store.workspace_revision(
                    envelope.project_id,
                    envelope.workspace_id,
                )
        except Exception:
            if reservation is not None:
                with self._lifecycle_lock, self.registry_publication_guard():
                    if viewer_reservation is not None:
                        self._client.cancel_viewer_invalidation(viewer_reservation)
                    self._solution_store.release_run(
                        reservation.run_id,
                        "dispatch_preparation_failed",
                    )
                    self._run_artifact_services.pop(reservation.run_id, None)
                    self._solution_store.discard_preparation(
                        prepared.preparation_id,
                        "prepared_dispatch_failed",
                    )
                    self._client.release_run_reservation(
                        reservation,
                        "dispatch_preparation_failed",
                    )
            elif preparation_validated:
                self._solution_store.discard_preparation(
                    prepared.preparation_id,
                    "prepared_dispatch_failed",
                )
            self._publish_solution_state_results(solution_events)
            raise

        self._publish_solution_state_results(solution_events)
        assert reservation is not None and command is not None
        started = False
        try:
            # The reader must finish earlier runtime callbacks before it can
            # receive the retirement ACK. Revalidate dispatch after this wait.
            self.retire_workspace(reservation.workspace_id)
            with self._lifecycle_lock, self.registry_publication_guard():
                envelope = prepared.dispatch_envelope
                current_generation = self._client.execution_generation_snapshot(
                    reservation.selection,
                    registry_contract_fingerprint=candidate_fingerprint,
                )
                if (
                    self._solution_store.workspace_revision(
                        envelope.project_id,
                        envelope.workspace_id,
                    )
                    != dispatch_workspace_revision
                    or not current_generation.compatible_with(
                        reservation.generation_snapshot
                    )
                ):
                    raise ValueError("prepared_dispatch_changed_before_start")
                started = True
                run_id = self._client.start_reserved_run(reservation, command)
                if run_id == reservation.run_id:
                    return run_id
        except Exception:
            reason = "start_failed" if started else "dispatch_changed_before_start"
            with self._lifecycle_lock, self.registry_publication_guard():
                if viewer_reservation is not None:
                    self._client.cancel_viewer_invalidation(viewer_reservation)
                self._solution_store.release_run(reservation.run_id, reason)
                self._run_artifact_services.pop(reservation.run_id, None)
                self._client.release_run_reservation(reservation, reason)
            raise

        with self._lifecycle_lock, self.registry_publication_guard():
            if viewer_reservation is not None:
                self._client.cancel_viewer_invalidation(viewer_reservation)
            self._solution_store.release_run(reservation.run_id, "start_failed")
            self._run_artifact_services.pop(reservation.run_id, None)
            self._client.release_run_reservation(reservation, "start_failed")
        return ""

    def _validate_prepared_dispatch(
        self,
        prepared: PreparedExecution,
        *,
        entry: Any,
        generation_snapshot: Any,
    ) -> None:
        registry = entry.candidate_registry
        envelope = prepared.dispatch_envelope
        if registry.contract_fingerprint() != prepared.registry_contract_fingerprint:
            raise ValueError("prepared_registry_contract_changed")
        if not generation_snapshot.route_compatible_with(envelope.execution_backend):
            raise ValueError("prepared_backend_route_changed")
        if not generation_snapshot.available:
            raise ValueError("prepared_runtime_generation_unavailable")
        if (
            entry.generation_snapshot.available
            and generation_snapshot.environment_digest
            != prepared.execution_environment_digest
        ):
            raise ValueError("prepared_execution_environment_changed")
        workspace_revision = self._solution_store.workspace_revision(
            envelope.project_id,
            envelope.workspace_id,
        )
        if (
            workspace_revision != prepared.execution_affecting_workspace_revision
            and entry.adopted_workspace_revision != workspace_revision
        ):
            raise ValueError("prepared_workspace_revision_changed")
        snapshot = envelope.decode_runtime_snapshot(catalog=registry.data_types)
        if (
            canonical_digest(snapshot.to_document(catalog=registry.data_types))
            != prepared.runtime_snapshot_fingerprint
        ):
            raise ValueError("prepared_runtime_snapshot_changed")
        workspace = compile_runtime_snapshot(
            snapshot,
            workspace_id=envelope.workspace_id,
            registry=registry,
        )
        plan = ExecutionPlan(
            workspace,
            registry,
            target_node_ids=envelope.target_node_ids,
            clicked_trigger_node_id=envelope.clicked_trigger_node_id,
            trigger_capture_node_ids=envelope.trigger_capture_node_ids,
        )
        if plan.fingerprint != prepared.execution_plan_fingerprint:
            raise ValueError("prepared_execution_plan_changed")

    def invalidate_solution(
        self,
        project_id: str,
        workspace_id: str,
        runtime_snapshot: RuntimeSnapshot | Mapping[str, Any],
        changed_root_node_ids: Sequence[str],
        reason_code: str,
    ) -> InvalidationResult:
        released_leases: tuple[Any, ...] = ()
        with self._lifecycle_lock:
            registry = self._registry
            if registry is None:
                raise ValueError(
                    "solution invalidation requires an authoritative registry"
                )
            snapshot = coerce_runtime_snapshot(
                runtime_snapshot,
                catalog=registry.data_types,
            )
            if snapshot is None or snapshot.project_id != str(project_id).strip():
                raise ValueError("runtime snapshot project does not match project_id")
            workspace = compile_runtime_snapshot(
                snapshot,
                workspace_id=str(workspace_id).strip(),
                registry=registry,
            )
            self._solution_store.ensure_project(str(project_id).strip())
            plan = ExecutionPlan.for_invalidation(workspace, registry)
            result, released_leases = self._solution_store.invalidate(
                project_id=str(project_id).strip(),
                workspace_id=workspace.workspace_id,
                plan=plan,
                changed_root_node_ids=changed_root_node_ids,
                reason_code=str(reason_code).strip(),
            )
        self._release_resource_leases(released_leases)
        self._publish_solution_state_results((result,))
        return result

    def solution_facts(
        self,
        project_id: str,
        workspace_id: str,
    ) -> tuple[NodeSolutionFact, ...]:
        return self._solution_store.facts(
            str(project_id).strip(),
            str(workspace_id).strip(),
        )

    def expired_node_ids(
        self,
        project_id: str,
        workspace_id: str,
    ) -> tuple[str, ...]:
        return self._solution_store.expired_node_ids(
            str(project_id).strip(),
            str(workspace_id).strip(),
        )

    def solution_record(self, record_id: str) -> SolutionRecord | None:
        return self._solution_store.record(record_id)

    def capture_project_solution_save(
        self,
        project_id: str,
        source_project_path: str,
        retained_owner_ids: Iterable[tuple[str, str]],
        source_artifact_context: object,
    ) -> ProjectSolutionSaveSnapshot:
        if self._solution_repository_factory is None or self._registry is None:
            raise ValueError("project_solution_save_source_invalid")
        normalized_source_path = (
            os.path.normcase(os.path.abspath(source_project_path))
            if str(source_project_path).strip()
            else ""
        )
        context_digest = getattr(
            source_artifact_context,
            "project_save_context_digest",
            None,
        )
        if not callable(context_digest):
            raise ValueError("project_solution_save_source_invalid")
        source_artifact_context_digest = context_digest()
        registry_contract_fingerprint = self._registry.contract_fingerprint()
        with self._lifecycle_lock:
            binding_revision = self._project_solution_binding_revision
            (
                namespace_id,
                source_generation_id,
                source_manifest_set_digest,
                owners,
                supplemental_records,
                _required_artifact_ids,
                _estimated_copy_bytes,
            ) = self._solution_store.project_solution_save_inputs(
                project_id,
                retained_owner_ids,
                catalog=self._registry.data_types,
            )
        snapshot = self._solution_repository_factory.export_project_solution_save(
            project_id,
            normalized_source_path,
            namespace_id,
            source_generation_id,
            source_manifest_set_digest,
            owners,
            supplemental_records,
            binding_revision,
            registry_contract_fingerprint,
            source_artifact_context_digest,
            self._registry.data_types,
            source_artifact_context,
        )
        if not isinstance(snapshot, ProjectSolutionSaveSnapshot):
            raise TypeError("project solution factory returned an invalid snapshot")
        with self._lifecycle_lock:
            if (
                binding_revision != self._project_solution_binding_revision
                or self._solution_store.solution_namespace_id(project_id)
                != snapshot.solution_namespace_id
                or snapshot.binding_revision != binding_revision
                or snapshot.registry_contract_fingerprint
                != registry_contract_fingerprint
                or snapshot.source_artifact_context_digest
                != source_artifact_context_digest
                or project_solution_snapshot_token(snapshot) != snapshot.snapshot_token
            ):
                raise ValueError("project_solution_save_snapshot_stale")
            self._project_solution_save_contexts[snapshot.snapshot_token] = (
                _ProjectSolutionSaveContext(
                    snapshot=snapshot,
                    binding_revision=binding_revision,
                )
            )
        return snapshot

    def project_solution_save_snapshot_is_current(self, snapshot_token: str) -> bool:
        token = str(snapshot_token).strip()
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(token)
            return bool(
                context is not None
                and not context.adopted
                and project_solution_snapshot_token(context.snapshot)
                == context.snapshot.snapshot_token
                and context.binding_revision == self._project_solution_binding_revision
                and self._solution_store.solution_namespace_id(
                    context.snapshot.project_id
                )
                == context.snapshot.solution_namespace_id
            )

    def stage_project_solution_save(
        self,
        snapshot: ProjectSolutionSaveSnapshot,
        destination_project_path: str,
        destination_artifact_context: object,
    ) -> ProjectSolutionSaveResult:
        if self._solution_repository_factory is None or self._registry is None:
            raise ValueError("project_solution_save_destination_invalid")
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(snapshot.snapshot_token)
            snapshot_matches = bool(
                context is not None
                and context.snapshot == snapshot
                and project_solution_snapshot_token(snapshot) == snapshot.snapshot_token
                and not context.adopted
                and context.binding_revision == self._project_solution_binding_revision
            )
        if not snapshot_matches:
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                reason_code="project_solution_save_snapshot_stale",
                diagnostic="The project solution snapshot changed before staging.",
            )
        result = self._solution_repository_factory.stage_project_solution_save(
            snapshot,
            destination_project_path,
            self._registry.data_types,
            destination_artifact_context,
        )
        if not isinstance(result, ProjectSolutionSaveResult):
            raise TypeError("project solution factory returned an invalid save result")
        if result.reason_code != "project_solution_save_staged":
            return result
        if (
            result.snapshot_token != snapshot.snapshot_token
            or result.solution_namespace_id != snapshot.solution_namespace_id
            or result.estimated_copy_bytes != snapshot.estimated_copy_bytes
            or result.staged_new_bytes > snapshot.estimated_copy_bytes
        ):
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                reason_code="project_solution_save_capacity_exceeded",
                diagnostic="The destination solution generation exceeded its estimate.",
            )
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(snapshot.snapshot_token)
            if (
                context is None
                or context.snapshot != snapshot
                or context.binding_revision != self._project_solution_binding_revision
                or self._solution_store.solution_namespace_id(snapshot.project_id)
                != snapshot.solution_namespace_id
            ):
                stale = True
            else:
                stale = False
                context.destination_project_path = str(destination_project_path)
                context.result = result
                context.gc_candidate_relative_paths = (
                    result.orphan_candidate_relative_paths
                )
                context.gc_scan_complete = result.orphan_scan_complete
        if stale:
            return ProjectSolutionSaveResult(
                snapshot_token=snapshot.snapshot_token,
                solution_namespace_id=snapshot.solution_namespace_id,
                reason_code="project_solution_save_snapshot_stale",
                diagnostic="The project solution binding changed during staging.",
            )
        return result

    def prepare_project_solution_adoption(
        self,
        result: ProjectSolutionSaveResult,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        destination_artifact_context: object,
    ) -> ProjectSolutionCandidateResult:
        if self._solution_repository_factory is None or self._registry is None:
            return ProjectSolutionCandidateResult(
                False,
                "project_solution_candidate_invalid",
                "Project solution storage is unavailable.",
            )
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(result.snapshot_token)
            snapshot = context.snapshot if context is not None else None
            valid = bool(
                context is not None
                and snapshot is not None
                and project_solution_snapshot_token(snapshot) == snapshot.snapshot_token
                and context.result == result
                and context.binding_revision == self._project_solution_binding_revision
                and snapshot.project_id == str(project_id).strip()
                and context.destination_project_path == str(destination_project_path)
                and result.solution_namespace_id == snapshot.solution_namespace_id
                and result.metadata_solution_store == metadata_solution_store
                and context.candidate is None
            )
        if not valid or snapshot is None:
            return ProjectSolutionCandidateResult(
                False,
                "project_solution_candidate_snapshot_stale",
                "The project solution snapshot changed before candidate reopen.",
            )
        try:
            candidate = (
                self._solution_repository_factory.open_project_solution_save_candidate(
                    snapshot.project_id,
                    destination_project_path,
                    metadata_solution_store,
                    snapshot.solution_namespace_id,
                    self._registry.data_types,
                    destination_artifact_context,
                )
            )
        except Exception:  # noqa: BLE001 - committed candidate reopen fails closed.
            candidate = None
        if not isinstance(candidate, DurableBackendOpenResult) or not (
            candidate.backend is not None
            and candidate.status_code == "durable_bound_active"
            and candidate.solution_namespace_id == snapshot.solution_namespace_id
            and candidate.active_generation_id == result.candidate_generation_id
            and candidate.active_manifest_set_digest
            == result.candidate_manifest_set_digest
        ):
            self._close_durable_backend(
                candidate.backend
                if isinstance(candidate, DurableBackendOpenResult)
                else None
            )
            return ProjectSolutionCandidateResult(
                False,
                "project_solution_candidate_invalid",
                "The committed project solution candidate is invalid.",
            )
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(result.snapshot_token)
            if (
                context is None
                or context.snapshot != snapshot
                or context.result != result
                or context.binding_revision != self._project_solution_binding_revision
                or context.candidate is not None
            ):
                stale = True
            else:
                stale = False
                context.candidate = candidate
        if stale:
            self._close_durable_backend(candidate.backend)
            return ProjectSolutionCandidateResult(
                False,
                "project_solution_candidate_snapshot_stale",
                "The project solution snapshot changed during candidate reopen.",
            )
        return ProjectSolutionCandidateResult(
            True,
            "project_solution_candidate_prepared",
        )

    def adopt_project_solution_save(
        self,
        result: ProjectSolutionSaveResult,
        project_id: str,
        destination_project_path: str,
        metadata_solution_store: object,
        destination_artifact_context: object,
    ) -> ProjectSolutionAdoptionResult:
        del destination_artifact_context
        if not isinstance(result, ProjectSolutionSaveResult):
            raise TypeError("result must be ProjectSolutionSaveResult")
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(result.snapshot_token)
            candidate = context.candidate if context is not None else None
            if (
                context is None
                or project_solution_snapshot_token(context.snapshot)
                != context.snapshot.snapshot_token
                or context.binding_revision != self._project_solution_binding_revision
            ):
                reason = "project_solution_adoption_snapshot_stale"
            elif (
                context.snapshot.project_id != str(project_id).strip()
                or context.destination_project_path != str(destination_project_path)
                or result.solution_namespace_id
                != context.snapshot.solution_namespace_id
            ):
                reason = "project_solution_adoption_namespace_mismatch"
            elif (
                candidate is None
                or candidate.backend is None
                or context.result != result
                or result.metadata_solution_store != metadata_solution_store
            ):
                reason = "project_solution_adoption_candidate_invalid"
            else:
                previous = self._solution_store.install_durable_backend(
                    context.snapshot.project_id,
                    candidate,
                )
                if previous is not None:
                    self._retired_solution_backends.append(previous)
                context.candidate = None
                context.adopted = True
                self._project_solution_binding_revision += 1
                context.binding_revision = self._project_solution_binding_revision
                reason = "project_solution_adopted"
        if reason == "project_solution_adopted":
            return ProjectSolutionAdoptionResult(True, reason)
        return ProjectSolutionAdoptionResult(
            False,
            reason,
            "The prepared project solution candidate could not be adopted.",
        )

    def cancel_project_solution_save(self, snapshot_token: str) -> None:
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.pop(
                str(snapshot_token).strip(),
                None,
            )
        self._close_durable_backend(
            context.candidate.backend
            if context is not None and context.candidate is not None
            else None
        )

    def collect_project_solution_garbage(
        self,
        result: ProjectSolutionSaveResult,
        *,
        protect_previous_generation: bool,
        limit: int = 10_000,
    ) -> ProjectSolutionGcResult:
        if self._solution_repository_factory is None or self._registry is None:
            return ProjectSolutionGcResult(
                (), (), False, "project_solution_gc_skipped_invalid"
            )
        with self._lifecycle_lock:
            context = self._project_solution_save_contexts.get(result.snapshot_token)
            retired = tuple(self._retired_solution_backends)
            self._retired_solution_backends.clear()
        for backend in retired:
            self._close_durable_backend(backend)
        if context is None or context.result != result:
            return ProjectSolutionGcResult(
                (), (), False, "project_solution_gc_skipped_invalid"
            )
        protected = (
            ((result.previous_generation_id, result.previous_manifest_set_digest),)
            if protect_previous_generation and result.previous_generation_id
            else ()
        )
        active_generation_id = result.candidate_generation_id
        active_manifest_set_digest = result.candidate_manifest_set_digest
        if not protect_previous_generation:
            current_pointer = self._solution_store.durable_binding_pointer(
                context.snapshot.project_id
            )
            if all(current_pointer):
                active_generation_id, active_manifest_set_digest = current_pointer
        gc_result = self._solution_repository_factory.collect_project_solution_garbage(
            context.snapshot.project_id,
            context.destination_project_path,
            active_generation_id,
            active_manifest_set_digest,
            protected,
            context.gc_candidate_relative_paths,
            context.gc_scan_complete,
            limit,
            self._registry.data_types,
        )
        remaining = tuple(
            sorted(
                set(gc_result.candidate_relative_paths).difference(
                    gc_result.removed_relative_paths
                )
            )
        )
        with self._lifecycle_lock:
            current_context = self._project_solution_save_contexts.get(
                result.snapshot_token
            )
            if current_context is context:
                current_context.gc_candidate_relative_paths = remaining
                if not gc_result.has_more:
                    current_context.gc_scan_complete = True
        if not protect_previous_generation and not gc_result.has_more:
            with self._lifecycle_lock:
                self._project_solution_save_contexts.pop(result.snapshot_token, None)
        return gc_result

    def bind_project_solution_store(
        self,
        project_id: str,
        project_path: str,
        metadata_solution_store: object,
    ) -> DurableBackendOpenResult:
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            raise ValueError("project_id must be non-empty")
        with self._lifecycle_lock:
            active_project_ids = self._solution_store.project_ids()
            if active_project_ids and normalized_project_id not in active_project_ids:
                raise ValueError("project solution session is not active")
            namespace_id = self._solution_store.ensure_project(
                normalized_project_id,
                project_path,
            )
            binding_revision = self._project_solution_binding_revision
        if not str(project_path).strip():
            result = DurableBackendOpenResult(
                None,
                namespace_id,
                "durable_session_only_metadata_absent",
                "Unsaved projects use session-only solution reuse.",
            )
        elif self._solution_repository_factory is None or self._registry is None:
            result = DurableBackendOpenResult(
                None,
                namespace_id,
                "durable_session_only_factory_unavailable",
                "Durable solution storage is unavailable; results will be recomputed.",
            )
        else:
            try:
                result = self._solution_repository_factory.open_backend(
                    normalized_project_id,
                    project_path,
                    metadata_solution_store,
                    self._registry.data_types,
                )
                if not isinstance(result, DurableBackendOpenResult):
                    raise TypeError(
                        "durable backend factory returned an invalid result"
                    )
            except Exception:  # noqa: BLE001 - factory failures fail closed.
                result = DurableBackendOpenResult(
                    None,
                    namespace_id,
                    "durable_session_only_io_error",
                    "Durable solution storage could not be opened; results will be recomputed.",
                )
        with self._lifecycle_lock:
            if (
                binding_revision != self._project_solution_binding_revision
                or self._solution_store.solution_namespace_id(normalized_project_id)
                != namespace_id
            ):
                candidate = result.backend
                result = DurableBackendOpenResult(
                    None,
                    self._solution_store.solution_namespace_id(normalized_project_id)
                    or namespace_id,
                    "durable_session_only_io_error",
                    "Project solution binding changed while durable data was opening.",
                )
                previous = None
            else:
                candidate = None
                previous = self._solution_store.install_durable_backend(
                    normalized_project_id,
                    result,
                )
                self._project_solution_binding_revision += 1
        self._close_durable_backend(candidate)
        self._close_durable_backend(previous)
        return result

    def detach_project_solution_store(self, project_id: str, reason: str) -> None:
        del reason
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            raise ValueError("project_id must be non-empty")
        with self._lifecycle_lock:
            if not self._solution_store.solution_namespace_id(normalized_project_id):
                raise ValueError("project solution session is not active")
            self._project_solution_binding_revision += 1
            self._generation_snapshots.clear()
            self._run_artifact_services.clear()
            self._release_all_solution_resources()
            backend = self._solution_store.detach_durable_backend()
            _namespace, solution_events = self._solution_store.reset_project_session(
                normalized_project_id,
                "",
            )
        self._close_durable_backend(backend)
        self._publish_solution_state_results(solution_events)

    def reset_project_session(self, project_id: str, project_path: str = "") -> str:
        with self._lifecycle_lock:
            self._project_solution_binding_revision += 1
            self._generation_snapshots.clear()
            self._run_artifact_services.clear()
            self._release_all_solution_resources()
            backend = self._solution_store.detach_durable_backend()
            namespace_id, solution_events = self._solution_store.reset_project_session(
                project_id,
                project_path,
            )
        self._close_durable_backend(backend)
        self._publish_solution_state_results(solution_events)
        return namespace_id

    @staticmethod
    def _close_durable_backend(backend: Any | None) -> None:
        if backend is None:
            return
        try:
            backend.close()
        except Exception:  # noqa: BLE001 - detach must preserve authored state.
            return

    def _release_resource_leases(self, leases: Sequence[Any]) -> None:
        release = getattr(self._client, "release_solution_resource", None)
        if not callable(release):
            return
        for lease in leases:
            release(lease)

    def _release_all_solution_resources(self) -> None:
        self._release_resource_leases(self._solution_store.take_all_resource_leases())

    def _validated_event_resources(
        self,
        event: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool, tuple[Any, ...]]:
        payload = dict(event)
        if str(payload.get("type", "")) != "node_settled" or self._registry is None:
            return payload, True, ()
        raw_outputs = payload.get("outputs", {})
        try:
            if isinstance(raw_outputs, Mapping) and all(
                isinstance(value, SettledPortResult) for value in raw_outputs.values()
            ):
                outputs = dict(raw_outputs)
            else:
                outputs = settled_output_mapping_from_payload(
                    raw_outputs,
                    catalog=self._registry.data_types,
                )
        except (TypeError, ValueError):
            return payload, False, ()
        run_id = str(payload.get("run_id", "")).strip()
        node_id = str(payload.get("node_id", "")).strip()
        owner_scope = f"solution:{run_id}:{node_id}:{uuid.uuid4().hex}"
        artifact_service = self._run_artifact_services.get(run_id)
        lease_resource = getattr(self._client, "lease_solution_resource", None)
        leases: list[Any] = []
        reused_event = str(payload.get("disposition", "")).strip() == "reused"

        def validate(value: Any) -> Any:
            if isinstance(value, RuntimeArtifactRef):
                if artifact_service is None:
                    raise ValueError("artifact resolver is unavailable")
                artifact_service.resolve_path(value)
                return value
            if isinstance(
                value,
                (
                    RuntimeHandleRef,
                    ArrayDataRef,
                    ArraySlice2DRef,
                    TabularDataRef,
                    TabularWindowRef,
                ),
            ):
                if not callable(lease_resource):
                    raise ValueError("session resource resolver is unavailable")
                leased = lease_resource(
                    run_id,
                    value,
                    owner_scope=owner_scope,
                )
                if leased is None:
                    raise ValueError("session resource is not live")
                normalized, lease = leased
                leases.append(lease)
                return value if reused_event else normalized
            if isinstance(value, DataTree):
                return DataTree(
                    (
                        path,
                        tuple(validate(item) for item in items),
                    )
                    for path, items in value.branches
                )
            if isinstance(value, Mapping):
                return {key: validate(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return tuple(validate(item) for item in value)
            if isinstance(value, list):
                return [validate(item) for item in value]
            return value

        try:
            normalized_outputs = {
                port_key: replace(
                    result,
                    value=(
                        validate(result.value)
                        if result.status == "value"
                        else result.value
                    ),
                )
                for port_key, result in outputs.items()
            }
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            self._release_resource_leases(leases)
            return payload, False, ()
        payload["outputs"] = normalized_outputs
        return payload, True, tuple(leases)

    def _handle_generation_event(
        self,
        event: Mapping[str, Any],
        generation_snapshot: Any,
    ) -> None:
        if str(event.get("type", "")) == "observation_invalidation_requested":
            with self._lifecycle_lock:
                result, released_leases = (
                    self._solution_store.invalidate_current_observations(
                        run_id=str(event.get("run_id", "")).strip(),
                        workspace_id=str(event.get("workspace_id", "")).strip(),
                        requesting_node_id=str(event.get("node_id", "")).strip(),
                        root_node_id=str(event.get("root_node_id", "")).strip(),
                        reason_code=str(event.get("reason_code", "")).strip(),
                        generation_snapshot=generation_snapshot,
                    )
                )
            self._release_resource_leases(released_leases)
            if result is not None:
                self._publish_solution_state_results((result,))
            self._generation_event_local.forwarded = dict(event)
            return
        backend_id = generation_snapshot.selection.backend_id
        solution_events: tuple[InvalidationResult, ...] = ()
        diagnostics: tuple[dict[str, Any], ...] = ()
        enriched_event = dict(event)
        with self._lifecycle_lock:
            previous = self._generation_snapshots.get(backend_id)
            if previous is not None and not previous.compatible_with(
                generation_snapshot
            ):
                self._release_all_solution_resources()
                solution_events = self._solution_store.reset_runtime_generation(
                    "runtime_generation_replaced"
                )
                self._run_artifact_services.clear()
            self._generation_snapshots[backend_id] = generation_snapshot
            if self._registry is None:
                return
            validated_event, resources_reusable, resource_leases = (
                self._validated_event_resources(event)
            )
            run_artifact_service = self._run_artifact_services.get(
                str(event.get("run_id", "")).strip()
            )
            diagnostics, released_leases, acceptance = (
                self._solution_store.handle_event(
                    validated_event,
                    generation_snapshot,
                    catalog=self._registry.data_types,
                    resources_reusable=resources_reusable,
                    resource_leases=resource_leases,
                    artifact_context=(
                        run_artifact_service.store
                        if run_artifact_service is not None
                        else None
                    ),
                )
            )
            enriched_event = dict(validated_event)
            if str(enriched_event.get("type", "")) == "node_settled":
                enriched_event["accepted_solution_record"] = acceptance is not None
                enriched_event["record_id"] = (
                    acceptance.record_id if acceptance is not None else ""
                )
                enriched_event["result_digest"] = (
                    acceptance.result_digest if acceptance is not None else ""
                )
                if acceptance is not None:
                    enriched_event["solution_key"] = acceptance.solution_key
                    enriched_event["disposition"] = acceptance.disposition.value
                    enriched_event["solution_fact_revision"] = acceptance.fact_revision
            self._release_resource_leases(released_leases)
            if str(event.get("type", "")) in TERMINAL_EVENT_TYPES:
                self._run_artifact_services.pop(
                    str(event.get("run_id", "")).strip(),
                    None,
                )
        self._publish_solution_state_results(solution_events)
        if str(event.get("type", "")) != "execution_generation_changed":
            self._event_stream.publish(enriched_event)
        self._generation_event_local.forwarded = dict(event)
        for diagnostic in diagnostics:
            self._event_stream.publish(diagnostic)

    def _handle_client_event(self, event: Mapping[str, Any]) -> None:
        forwarded = getattr(self._generation_event_local, "forwarded", None)
        if isinstance(forwarded, Mapping) and dict(event) == dict(forwarded):
            self._generation_event_local.forwarded = None
            return
        self._event_stream.publish(dict(event))

    def _publish_solution_state_results(
        self, results: Sequence[InvalidationResult]
    ) -> None:
        for result in results:
            self._event_stream.publish(
                SolutionStateChangedEvent.from_invalidation(result).to_payload()
            )

    def start(self, request: ExecutionRequest) -> str:
        return self.dispatch_prepared(self.prepare_execution(request))

    def run(
        self,
        request: ExecutionRequest,
        *,
        timeout: float | None = None,
        on_event: ExecutionEventCallback | None = None,
    ) -> ExecutionResult:
        condition = threading.Condition()
        events: list[ExecutionEvent] = []
        terminal_event: ExecutionEvent | None = None
        run_id_holder = {"run_id": ""}

        def _capture(event: ExecutionEvent) -> None:
            nonlocal terminal_event
            event_type = str(event.get("type", ""))
            event_run_id = str(event.get("run_id", ""))
            active_run_id = run_id_holder["run_id"]
            if (
                active_run_id
                and event_type in RUN_SCOPED_EVENT_TYPES
                and event_run_id
                and event_run_id != active_run_id
            ):
                return
            payload = copy.deepcopy(dict(event))
            with condition:
                events.append(payload)
                if (
                    active_run_id
                    and event_type in TERMINAL_EVENT_TYPES
                    and event_run_id == active_run_id
                ):
                    terminal_event = payload
                condition.notify_all()
            if on_event is not None:
                on_event(copy.deepcopy(payload))

        unsubscribe = self.subscribe(_capture)
        try:
            prepared = self.prepare_execution(request)
            workspace_id = prepared.dispatch_envelope.workspace_id
            run_id = self.dispatch_prepared(prepared)
            run_id_holder["run_id"] = run_id
            if not run_id:
                terminal_event = self._start_failure_event(events, workspace_id)
                return self._result_from_terminal(
                    run_id="",
                    workspace_id=workspace_id,
                    terminal_event=terminal_event,
                    events=events,
                )

            with condition:
                terminal_event = self._terminal_event_for_run(events, run_id)
            deadline = time.monotonic() + timeout if timeout is not None else None
            with condition:
                while terminal_event is None:
                    if deadline is None:
                        condition.wait(timeout=0.2)
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    condition.wait(timeout=min(remaining, 0.2))

            if terminal_event is None:
                self.cancel(CancellationRequest(run_id=run_id, reason="timeout"))
                terminal_event = {
                    "type": "run_timeout",
                    "run_id": run_id,
                    "workspace_id": workspace_id,
                    "reason": "timeout",
                }
                with condition:
                    events.append(copy.deepcopy(terminal_event))

            return self._result_from_terminal(
                run_id=run_id,
                workspace_id=workspace_id,
                terminal_event=terminal_event,
                events=events,
            )
        finally:
            unsubscribe()

    def cancel(self, request: CancellationRequest) -> None:
        if request.run_id:
            self.stop_run(request.run_id)

    def pause_run(self, run_id: str) -> None:
        self._client.pause_run(run_id)

    def resume_run(self, run_id: str) -> None:
        self._client.resume_run(run_id)

    def stop_run(self, run_id: str) -> None:
        self._client.stop_run(run_id)

    def open_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        with self.registry_publication_guard():
            return self._client.open_viewer_session(*args, **kwargs)

    def update_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        return self._client.update_viewer_session(*args, **kwargs)

    def close_viewer_session(self, *args: Any, **kwargs: Any) -> str:
        return self._client.close_viewer_session(*args, **kwargs)

    def materialize_viewer_data(self, *args: Any, **kwargs: Any) -> str:
        return self._client.materialize_viewer_data(*args, **kwargs)

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
        return self._client.query_viewer_session(
            workspace_id,
            node_id,
            session_id,
            run_id=run_id,
            backend_id=backend_id,
            query_type=query_type,
            payload=payload,
            options=options,
        )

    def invalidate_viewer_requests(
        self,
        workspace_id: str,
        node_ids: Iterable[str] | None,
    ) -> int:
        return self._client.invalidate_viewer_requests(workspace_id, node_ids)

    def retire_workspace(self, workspace_id: str) -> int:
        return int(self._client.retire_workspace(workspace_id))

    def shutdown(self) -> None:
        with self._lifecycle_lock:
            self._project_solution_binding_revision += 1
            self._release_all_solution_resources()
            self._run_artifact_services.clear()
            backend = self._solution_store.detach_durable_backend()
            candidates = tuple(
                context.candidate.backend
                for context in self._project_solution_save_contexts.values()
                if context.candidate is not None
                and context.candidate.backend is not None
            )
            retired = tuple(self._retired_solution_backends)
            self._project_solution_save_contexts.clear()
            self._retired_solution_backends.clear()
            self._solution_store.shutdown()
            if self._owns_client:
                self._client.shutdown()
        self._close_durable_backend(backend)
        for candidate in (*candidates, *retired):
            self._close_durable_backend(candidate)

    @staticmethod
    def _start_failure_event(
        events: list[ExecutionEvent], workspace_id: str
    ) -> ExecutionEvent:
        for event in reversed(events):
            if str(event.get("type", "")) == "protocol_error":
                return copy.deepcopy(event)
        return {
            "type": "run_failed",
            "run_id": "",
            "workspace_id": workspace_id,
            "error": "Execution client did not start a run.",
            "traceback": "",
        }

    @staticmethod
    def _terminal_event_for_run(
        events: list[ExecutionEvent], run_id: str
    ) -> ExecutionEvent | None:
        for event in events:
            if (
                str(event.get("type", "")) in TERMINAL_EVENT_TYPES
                and str(event.get("run_id", "")) == run_id
            ):
                return copy.deepcopy(event)
        return None

    @staticmethod
    def _result_from_terminal(
        *,
        run_id: str,
        workspace_id: str,
        terminal_event: ExecutionEvent,
        events: list[ExecutionEvent],
    ) -> ExecutionResult:
        event_type = str(terminal_event.get("type", ""))
        if event_type == "run_completed":
            status: ExecutionStatus = "completed"
        elif event_type == "run_stopped":
            status = "stopped"
        elif event_type == "run_timeout":
            status = "timeout"
        else:
            status = "failed"
        return ExecutionResult(
            run_id=str(terminal_event.get("run_id") or run_id),
            workspace_id=str(terminal_event.get("workspace_id") or workspace_id),
            status=status,
            events=tuple(copy.deepcopy(event) for event in events),
            terminal_event=copy.deepcopy(terminal_event),
            error=str(terminal_event.get("error", "")),
            traceback=str(terminal_event.get("traceback", "")),
        )
