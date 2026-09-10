# Purpose: Proven shared state, agreement, run-control, and viewer-request behavior for concrete execution clients.
# Map: subsystems/execution.md
# Tests: tests/test_client_common.py
# Landmarks: _ExecutionClientCommon
from __future__ import annotations

import time
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any

from ea_node_editor.execution.protocol_codec import (
    WorkerCommand,
    WorkerEvent,
    command_to_dict,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.execution.registry_agreement import (
    EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
    catalog_agreement,
    normalize_addon_runtime_config,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import (
    PauseRunCommand,
    ProtocolErrorEvent,
    ResumeRunCommand,
    StopRunCommand,
    RetireWorkspaceCommand,
)
from ea_node_editor.execution.viewer_messages import (
    VIEWER_COMMAND_TYPES,
    VIEWER_RESPONSE_EVENT_TYPES,
    CloseViewerSessionCommand,
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    QueryViewerSessionCommand,
    UpdateViewerSessionCommand,
    ViewerSessionFailedEvent,
)
from ea_node_editor.nodes.function_plugin import (
    EMPTY_PLUGIN_FINGERPRINT,
    PluginBundleRef,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
)

_LISTENER_SHUTDOWN_SENTINEL = {"type": "__listener_shutdown__"}


def _registry_contract_digest(value: object) -> str:
    digest = str(value)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(
            "registry_contract_fingerprint must be a lowercase SHA-256 digest"
        )
    return digest


def _registry_admitted(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self.registry_publication_guard():
            return method(self, *args, **kwargs)

    return guarded


@dataclass(frozen=True)
class _PendingViewerRequest:
    request_id: str
    command: str
    workspace_id: str
    node_id: str
    session_id: str
    generation_token: int = 0
    workspace_invalidation_epoch: int = 0
    node_invalidation_epoch: int = 0


@dataclass(frozen=True)
class _ConcreteViewerInvalidationPlan:
    workspace_epochs: dict[str, int]
    node_epochs: dict[tuple[str, str], int]
    pending_requests: dict[str, _PendingViewerRequest]
    session_ids: set[tuple[str, str]]
    session_generations: dict[tuple[str, str], int]
    session_node_ids: dict[tuple[str, str], str]
    retired_request_ids: frozenset[str]


def _coerce_positive_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 0.0
    return timeout if timeout > 0.0 else 0.0


def _python_script_timeout_by_node_id(
    runtime_snapshot: Any, workspace_id: str
) -> dict[str, float]:
    if runtime_snapshot is None:
        return {}
    workspaces: list[Any] = []
    normalized_workspace_id = str(workspace_id or "").strip()
    if normalized_workspace_id:
        try:
            workspaces.append(runtime_snapshot.workspace(normalized_workspace_id))
        except (AttributeError, KeyError, ValueError):
            workspaces = []
    if not workspaces:
        workspaces = list(getattr(runtime_snapshot, "workspaces", ()) or ())

    timeouts: dict[str, float] = {}
    for workspace in workspaces:
        for node in getattr(workspace, "nodes", ()) or ():
            if str(getattr(node, "type_id", "") or "").strip() != "core.python_script":
                continue
            node_id = str(getattr(node, "node_id", "") or "").strip()
            if not node_id:
                continue
            properties = getattr(node, "properties", {}) or {}
            if not isinstance(properties, dict):
                continue
            timeout = _coerce_positive_timeout(properties.get("timeout_sec"))
            if timeout > 0.0:
                timeouts[node_id] = timeout
    return timeouts


class _ExecutionClientCommon:
    _TERMINAL_EVENT_TYPES = {"run_completed", "run_failed", "run_stopped"}

    @contextmanager
    def registry_publication_guard(self):  # noqa: ANN201
        with self._start_lock:
            yield

    def _bind_data_types(
        self,
        data_types: DataTypeCatalog | None,
        *,
        plugin_bundles: tuple[PluginBundleRef, ...] = (),
        plugin_fingerprint: str = EMPTY_PLUGIN_FINGERPRINT,
        registry_contract_fingerprint: str,
        addon_runtime_config: tuple[tuple[str, bool], ...],
    ) -> None:
        if not isinstance(data_types, DataTypeCatalog):
            raise DataTypeCatalogError(
                "start_run requires the authoritative data-type catalog"
            )
        if not data_types.is_frozen:
            raise DataTypeCatalogError("data-type catalog must be frozen")
        requested_fingerprint = data_types.fingerprint()
        requested_runtime_fingerprint = runtime_registry_fingerprint(
            requested_fingerprint,
            plugin_fingerprint,
        )
        requested_contract_fingerprint = _registry_contract_digest(
            registry_contract_fingerprint
        )
        normalized_addon_runtime_config = normalize_addon_runtime_config(
            addon_runtime_config
        )
        pinned_fingerprint = getattr(
            self,
            "_registry_contract_generation_fingerprint",
            "",
        )
        if pinned_fingerprint and pinned_fingerprint != requested_contract_fingerprint:
            raise DataTypeCatalogError(
                "registry contract differs from the active worker generation"
            )
        self._data_types = data_types
        self._catalog_generation_fingerprint = requested_fingerprint
        self._plugin_bundles = tuple(plugin_bundles)
        self._plugin_fingerprint = plugin_fingerprint
        self._runtime_registry_generation_fingerprint = requested_runtime_fingerprint
        self._registry_contract_generation_fingerprint = requested_contract_fingerprint
        self._addon_runtime_config = normalized_addon_runtime_config

    def _catalog_agreement(self) -> tuple[str, tuple[Any, ...]]:
        return catalog_agreement(self._data_types)

    def _plugin_agreement(
        self,
    ) -> tuple[tuple[PluginBundleRef, ...], str, str]:
        catalog_fingerprint = self._data_types.fingerprint()
        plugin_bundles = tuple(getattr(self, "_plugin_bundles", ()))
        plugin_fingerprint = str(
            getattr(self, "_plugin_fingerprint", EMPTY_PLUGIN_FINGERPRINT)
        )
        return (
            plugin_bundles,
            plugin_fingerprint,
            runtime_registry_fingerprint(
                catalog_fingerprint,
                plugin_fingerprint,
            ),
        )

    def _registry_contract_agreement(
        self,
    ) -> tuple[str, tuple[tuple[str, bool], ...]]:
        return (
            _registry_contract_digest(
                getattr(self, "_registry_contract_generation_fingerprint", "")
            ),
            normalize_addon_runtime_config(getattr(self, "_addon_runtime_config", ())),
        )

    def _catalog_generation_fingerprint_value(self) -> str:
        with self._state_lock:
            return self._catalog_generation_fingerprint

    def _runtime_registry_fingerprint_value(self) -> str:
        with self._state_lock:
            return str(getattr(self, "_runtime_registry_generation_fingerprint", ""))

    def _catalog_generation_token_value(self) -> int:
        with self._state_lock:
            return int(getattr(self, "_catalog_generation_token", 0))

    def _install_physical_generation(self) -> int:
        with self._state_lock:
            catalog_generation = int(getattr(self, "_catalog_generation_token", 0))
            physical_generation = int(getattr(self, "_physical_generation_token", 0))
            if catalog_generation <= 0:
                catalog_generation = 1
            elif physical_generation > 0 and physical_generation == catalog_generation:
                catalog_generation += 1
            self._catalog_generation_token = catalog_generation
            self._physical_generation_token = catalog_generation
            self._accepted_physical_generation_token = catalog_generation
            self._execution_environment_digest = ""
            self._execution_environment_registry_fingerprint = ""
            self._execution_environment_selection_digest = ""
            self._run_generation_tokens.clear()
            if (
                self._active_run_id
                and self._start_run_pending_id == self._active_run_id
            ):
                self._run_generation_tokens[self._active_run_id] = catalog_generation
            return catalog_generation

    def _invalidate_physical_generation(self) -> int:
        with self._state_lock:
            generation_token = int(getattr(self, "_physical_generation_token", 0))
            self._accepted_physical_generation_token = -1
            self._execution_environment_digest = ""
            self._execution_environment_registry_fingerprint = ""
            self._execution_environment_selection_digest = ""
            return generation_token

    def _restore_physical_generation(self, generation_token: int) -> None:
        with self._state_lock:
            if (
                self._physical_generation_token == generation_token
                and self._accepted_physical_generation_token == -1
            ):
                self._accepted_physical_generation_token = generation_token

    def _source_generation_is_current(self, generation_token: int) -> bool:
        with self._state_lock:
            return (
                self._catalog_generation_token == generation_token
                and int(
                    getattr(
                        self,
                        "_accepted_physical_generation_token",
                        generation_token,
                    )
                )
                == generation_token
            )

    def _drop_stale_viewer_generation(self, error: str) -> None:
        with self._viewer_request_lock:
            if not hasattr(self, "_workspace_viewer_epochs"):
                self._workspace_viewer_epochs = {}
            if not hasattr(self, "_node_viewer_epochs"):
                self._node_viewer_epochs = {}
            if not hasattr(self, "_viewer_session_node_ids"):
                self._viewer_session_node_ids = {}
            workspace_ids = {
                *self._workspace_viewer_epochs,
                *(
                    pending.workspace_id
                    for pending in self._pending_viewer_requests.values()
                ),
                *(
                    workspace_id
                    for workspace_id, _session_id in self._viewer_session_ids
                ),
            }
            for workspace_id in workspace_ids:
                self._workspace_viewer_epochs[workspace_id] = (
                    self._workspace_viewer_epochs.get(workspace_id, 0) + 1
                )
            self._node_viewer_epochs.clear()
            pending_requests = tuple(self._pending_viewer_requests.values())
            self._pending_viewer_requests.clear()
            self._viewer_session_ids.clear()
            self._viewer_session_generations.clear()
            self._viewer_session_node_ids.clear()
        for pending in pending_requests:
            self._dispatch_viewer_request_failure(
                pending,
                error,
                generation_token=pending.generation_token,
            )

    def _viewer_generation_is_live(self) -> bool:
        return True

    def _assert_registry_replaceable_locked(self) -> None:
        with self._state_lock:
            run_thread = getattr(self, "_run_thread", None)
            if (
                self._active_run_id
                or self._start_run_pending_id
                or (run_thread is not None and run_thread.is_alive())
            ):
                raise DataTypeCatalogError(
                    "Cannot replace the registry during an active run"
                )
        with self._viewer_request_lock:
            if self._pending_viewer_requests or self._viewer_session_ids:
                raise DataTypeCatalogError(
                    "Cannot replace the registry while viewer requests or sessions remain active"
                )

    def assert_registry_replaceable(self) -> None:
        with self._start_lock:
            self._assert_registry_replaceable_locked()

    def replace_registry(self, registry: NodeRegistry) -> bool:
        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be a NodeRegistry")
        if not registry.data_types.is_frozen:
            raise DataTypeCatalogError("replacement data-type catalog must be frozen")
        requested_fingerprint = registry.contract_fingerprint()
        with self._start_lock:
            with self._state_lock:
                pinned_fingerprint = str(
                    getattr(
                        self,
                        "_registry_contract_generation_fingerprint",
                        "",
                    )
                )
            if not pinned_fingerprint or pinned_fingerprint == requested_fingerprint:
                return False
            self._assert_registry_replaceable_locked()
            self._recycle_catalog_generation()
            with self._state_lock:
                self._data_types = None
                self._catalog_generation_fingerprint = ""
                self._plugin_bundles = ()
                self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
                self._runtime_registry_generation_fingerprint = ""
                self._registry_contract_generation_fingerprint = ""
                self._addon_runtime_config = ()
            return True

    def _prepare_start_run(
        self,
        run_id: str,
        workspace_id: str,
        data_types: DataTypeCatalog | None,
        plugin_bundles: tuple[PluginBundleRef, ...] = (),
        plugin_fingerprint: str = EMPTY_PLUGIN_FINGERPRINT,
        registry_contract_fingerprint: str = EMPTY_REGISTRY_CONTRACT_FINGERPRINT,
        addon_runtime_config: tuple[tuple[str, bool], ...] = (),
    ) -> bool:
        if not isinstance(data_types, DataTypeCatalog):
            raise DataTypeCatalogError(
                "start_run requires the authoritative data-type catalog"
            )
        if not data_types.is_frozen:
            raise DataTypeCatalogError("data-type catalog must be frozen")
        requested_fingerprint = data_types.fingerprint()
        requested_contract_fingerprint = _registry_contract_digest(
            registry_contract_fingerprint
        )
        with self._start_lock:
            with self._state_lock:
                run_thread = getattr(self, "_run_thread", None)
                if self._active_run_id or (
                    run_thread is not None and run_thread.is_alive()
                ):
                    return False
                pinned_fingerprint = getattr(
                    self,
                    "_registry_contract_generation_fingerprint",
                    "",
                )
                physical_generation = int(
                    getattr(self, "_physical_generation_token", 0)
                )
                accepted_physical_generation = int(
                    getattr(
                        self,
                        "_accepted_physical_generation_token",
                        0,
                    )
                )
                reuse_unpinned_physical_generation = (
                    not pinned_fingerprint
                    and physical_generation > 0
                    and self._catalog_generation_token
                    == physical_generation
                    == accepted_physical_generation
                )
            contract_changed = bool(
                pinned_fingerprint
                and pinned_fingerprint != requested_contract_fingerprint
            )
            dropped_dead_viewer_generation = False
            if contract_changed and not self._viewer_generation_is_live():
                self._invalidate_physical_generation()
                self._drop_stale_viewer_generation(
                    "The worker generation ended before the viewer request completed."
                )
                dropped_dead_viewer_generation = True
            with self._viewer_request_lock:
                if contract_changed and (
                    self._pending_viewer_requests or self._viewer_session_ids
                ):
                    raise DataTypeCatalogError(
                        "Cannot start a different registry contract while viewer "
                        "requests or sessions from the current worker generation "
                        "remain active."
                    )
            if contract_changed:
                try:
                    self._recycle_catalog_generation()
                except Exception as exc:  # noqa: BLE001
                    if dropped_dead_viewer_generation:
                        self._invalidate_physical_generation()
                    raise DataTypeCatalogError(
                        "Failed to recycle the idle worker generation for "
                        "the requested registry contract."
                    ) from exc
                with self._state_lock:
                    self._data_types = None
                    self._catalog_generation_fingerprint = ""
                    self._plugin_bundles = ()
                    self._plugin_fingerprint = EMPTY_PLUGIN_FINGERPRINT
                    self._runtime_registry_generation_fingerprint = ""
                    self._registry_contract_generation_fingerprint = ""
                    self._addon_runtime_config = ()
            new_generation = contract_changed or (
                not pinned_fingerprint and not reuse_unpinned_physical_generation
            )
            if new_generation:
                with self._viewer_request_lock:
                    self._viewer_session_generations.clear()
            with self._state_lock:
                if new_generation:
                    self._catalog_generation_token += 1
                    self._run_generation_tokens.clear()
                    self._execution_environment_digest = ""
                    self._execution_environment_registry_fingerprint = ""
                    self._execution_environment_selection_digest = ""
                self._bind_data_types(
                    data_types,
                    plugin_bundles=plugin_bundles,
                    plugin_fingerprint=plugin_fingerprint,
                    registry_contract_fingerprint=requested_contract_fingerprint,
                    addon_runtime_config=addon_runtime_config,
                )
                self._active_run_id = run_id
                self._active_workspace_id = workspace_id
                self._start_run_pending_id = run_id
                self._run_generation_tokens[run_id] = self._catalog_generation_token
        return True

    def _release_start_run(self, run_id: str) -> None:
        with self._state_lock:
            self._run_generation_tokens.pop(run_id, None)
            if self._active_run_id == run_id:
                self._clear_active_run_state_locked()

    def _mark_start_run_dispatched(self, run_id: str) -> None:
        with self._state_lock:
            if self._start_run_pending_id == run_id:
                self._start_run_pending_id = ""

    def _encode_command(self, command: WorkerCommand) -> dict[str, Any]:
        return command_to_dict(command, catalog=getattr(self, "_data_types", None))

    def _deliver_run_preflight_command(
        self, command: WorkerCommand
    ) -> tuple[bool, str]:
        payload = self._encode_run_preflight_command(command)
        with self._state_lock:
            transport = self._pin_run_preflight_transport_locked()
        return self._deliver_encoded_run_preflight_command(payload, transport)

    def _decode_command(self, payload: dict[str, Any]) -> WorkerCommand:
        from ea_node_editor.execution.protocol_codec import (
            dict_to_command,
        )

        return dict_to_command(payload, catalog=getattr(self, "_data_types", None))

    def _decode_event(self, payload: dict[str, Any]) -> WorkerEvent:
        return dict_to_event(payload, catalog=getattr(self, "_data_types", None))

    def subscribe(
        self,
        callback: Callable[..., None],
        *,
        include_generation: bool = False,
    ) -> None:
        if include_generation:
            self._generation_callbacks.append(callback)
            return
        self._callbacks.append(callback)

    def _dispatch_event(
        self,
        event: WorkerEvent,
        *,
        generation_token: int | None = None,
    ) -> None:
        payload = event_to_dict(event, catalog=getattr(self, "_data_types", None))
        if payload.get("type") == "workspace_retired":
            waiters = getattr(self, "_workspace_retirement_waiters", {})
            waiter = waiters.get(str(payload.get("request_id", "")))
            if waiter is not None:
                waiter[1]["count"] = int(payload.get("retired_count", "0"))
                waiter[0].set()
        elif payload.get("type") == "protocol_error":
            waiters = getattr(self, "_workspace_retirement_waiters", {})
            request_id = str(payload.get("request_id", ""))
            matched = {request_id: waiters[request_id]} if request_id in waiters else {}
            for waiter in matched.values():
                waiter[1]["error"] = str(payload.get("error", "Protocol error"))
                waiter[0].set()
        for callback in list(self._callbacks):
            try:
                callback(dict(payload))
            except Exception:
                continue
        token = (
            self._catalog_generation_token_value()
            if generation_token is None
            else int(generation_token)
        )
        for callback in list(getattr(self, "_generation_callbacks", ())):
            try:
                callback(dict(payload), token)
            except Exception:
                continue

    def _retire_workspace_via_transport(self, workspace_id: str, *, timeout_sec: float = 10.0) -> int:
        normalized = str(workspace_id or "").strip()
        if not normalized:
            raise ValueError("workspace_id is required")
        request_id = uuid.uuid4().hex
        event = threading.Event()
        result: dict[str, Any] = {}
        waiters = getattr(self, "_workspace_retirement_waiters", None)
        if waiters is None:
            waiters = {}
            self._workspace_retirement_waiters = waiters
        waiters[request_id] = (event, result)
        try:
            if not self._post_command(RetireWorkspaceCommand(request_id=request_id, workspace_id=normalized)):
                raise RuntimeError("Failed to dispatch workspace retirement")
            if not event.wait(timeout_sec):
                raise TimeoutError("Execution worker did not acknowledge workspace retirement")
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            return result.get("count", 0)
        finally:
            waiters.pop(request_id, None)

    def _fail_workspace_retirements(self, error: str) -> None:
        for waiter in tuple(
            getattr(self, "_workspace_retirement_waiters", {}).values()
        ):
            waiter[1]["error"] = str(error).strip() or "Execution transport closed"
            waiter[0].set()

    def _notify_generation_change(
        self,
        *,
        reason: str,
        generation_token: int,
    ) -> None:
        payload = {
            "type": "execution_generation_changed",
            "reason": str(reason).strip(),
        }
        for callback in list(getattr(self, "_generation_callbacks", ())):
            try:
                callback(dict(payload), int(generation_token))
            except Exception:
                continue

    def _clear_active_node_state_locked(self) -> None:
        self._active_node_id = ""
        self._active_node_deadline = 0.0
        self._active_node_timeout_sec = 0.0

    def _clear_active_run_state_locked(self) -> None:
        self._active_run_id = ""
        self._active_workspace_id = ""
        self._start_run_pending_id = ""
        self._script_timeout_by_node_id = {}
        self._clear_active_node_state_locked()

    def _record_execution_event_state(
        self,
        payload: dict[str, Any],
        *,
        expected_generation_token: int | None = None,
    ) -> None:
        event_type = str(payload.get("type", "") or "")
        event_run_id = str(payload.get("run_id", "") or "")
        node_id = str(payload.get("node_id", "") or "").strip()
        with self._state_lock:
            if expected_generation_token is not None and (
                self._catalog_generation_token != expected_generation_token
                or int(
                    getattr(
                        self,
                        "_accepted_physical_generation_token",
                        expected_generation_token,
                    )
                )
                != expected_generation_token
            ):
                return
            if (
                event_run_id
                and self._active_run_id
                and event_run_id != self._active_run_id
            ):
                return
            if event_type == "node_started":
                self._active_node_id = node_id
                timeout_sec = self._script_timeout_by_node_id.get(node_id, 0.0)
                self._active_node_timeout_sec = timeout_sec
                self._active_node_deadline = (
                    time.monotonic() + timeout_sec if timeout_sec > 0.0 else 0.0
                )
            elif event_type == "node_settled":
                if not node_id or node_id == self._active_node_id:
                    self._clear_active_node_state_locked()
            elif event_type in self._TERMINAL_EVENT_TYPES:
                self._clear_active_run_state_locked()

    def _emit_protocol_error(
        self,
        message: str,
        *,
        run_id: str = "",
        request_id: str = "",
        command: str = "",
    ) -> None:
        with self._state_lock:
            workspace_id = self._active_workspace_id
        self._dispatch_event(
            ProtocolErrorEvent(
                run_id=run_id,
                workspace_id=workspace_id,
                request_id=request_id,
                command=command,
                error=message,
            )
        )

    @staticmethod
    def _next_viewer_request_id() -> str:
        return f"viewer_{uuid.uuid4().hex[:8]}"

    def _viewer_epochs(self, workspace_id: str, node_id: str) -> tuple[int, int]:
        with self._viewer_request_lock:
            if not hasattr(self, "_workspace_viewer_epochs"):
                self._workspace_viewer_epochs = {}
            if not hasattr(self, "_node_viewer_epochs"):
                self._node_viewer_epochs = {}
            return (
                self._workspace_viewer_epochs.get(workspace_id, 0),
                self._node_viewer_epochs.get((workspace_id, node_id), 0),
            )

    @staticmethod
    def _normalize_viewer_node_ids(
        node_ids: Iterable[str] | None,
    ) -> tuple[str, ...] | None:
        if node_ids is None:
            return None
        if isinstance(node_ids, (str, bytes)):
            raise TypeError("node_ids must be an iterable of node IDs or None")
        normalized: list[str] = []
        for value in node_ids:
            node_id = str(value or "").strip()
            if node_id and node_id not in normalized:
                normalized.append(node_id)
        return tuple(normalized)

    def invalidate_viewer_requests(
        self,
        workspace_id: str,
        node_ids: Iterable[str] | None,
    ) -> int:
        return len(self._invalidate_viewer_requests_with_ids(workspace_id, node_ids))

    def _invalidate_viewer_requests_with_ids(
        self,
        workspace_id: str,
        node_ids: Iterable[str] | None,
    ) -> set[str]:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            raise ValueError("workspace_id is required")
        normalized_node_ids = self._normalize_viewer_node_ids(node_ids)
        if normalized_node_ids == ():
            return set()
        with self._viewer_request_lock:
            workspace_epoch = self._workspace_viewer_epochs.get(
                normalized_workspace_id, 0
            ) + (1 if normalized_node_ids is None else 0)
            node_epochs = tuple(
                (
                    node_id,
                    self._node_viewer_epochs.get((normalized_workspace_id, node_id), 0)
                    + 1,
                )
                for node_id in (normalized_node_ids or ())
            )
        return self._commit_viewer_invalidation_snapshot(
            normalized_workspace_id,
            normalized_node_ids,
            workspace_epoch,
            node_epochs,
        )

    def _commit_viewer_invalidation_snapshot(
        self,
        workspace_id: str,
        node_ids: tuple[str, ...] | None,
        workspace_epoch: int,
        node_epochs: tuple[tuple[str, int], ...],
    ) -> set[str]:
        with self._viewer_request_lock:
            plan = self._plan_viewer_invalidation_snapshot_locked(
                workspace_id,
                node_ids,
                workspace_epoch,
                node_epochs,
            )
            self._apply_viewer_invalidation_plan_locked(plan)
        return set(plan.retired_request_ids)

    def _plan_viewer_invalidation_snapshot_locked(
        self,
        workspace_id: str,
        node_ids: tuple[str, ...] | None,
        workspace_epoch: int,
        node_epochs: tuple[tuple[str, int], ...],
    ) -> _ConcreteViewerInvalidationPlan:
        workspace_epochs = dict(self._workspace_viewer_epochs)
        planned_node_epochs = dict(self._node_viewer_epochs)
        pending_requests = dict(self._pending_viewer_requests)
        session_ids = set(self._viewer_session_ids)
        session_generations = dict(self._viewer_session_generations)
        session_node_ids = dict(self._viewer_session_node_ids)
        retired_request_ids: set[str] = set()
        current_workspace_epoch = workspace_epochs.get(workspace_id, 0)
        node_epoch_lookup = dict(node_epochs)
        if node_ids is None:
            if node_epochs:
                raise ValueError("global viewer invalidation forbids node epochs")
            if workspace_epoch != current_workspace_epoch + 1:
                raise ValueError(
                    "global viewer workspace epoch must advance locally once"
                )
            workspace_epochs[workspace_id] = workspace_epoch
            planned_node_epochs = {
                key: epoch
                for key, epoch in planned_node_epochs.items()
                if key[0] != workspace_id
            }
        else:
            if workspace_epoch != current_workspace_epoch:
                raise ValueError(
                    "scoped viewer invalidation must retain the local workspace epoch"
                )
            if tuple(node_epoch_lookup) != node_ids:
                raise ValueError("viewer node epochs do not match the filter")
            for node_id in node_ids:
                key = (workspace_id, node_id)
                target_node_epoch = node_epoch_lookup[node_id]
                if target_node_epoch != planned_node_epochs.get(key, 0) + 1:
                    raise ValueError("viewer node epoch must advance locally once")
                planned_node_epochs[key] = target_node_epoch
        cleanup_node_ids = node_ids
        for request_id, pending in tuple(pending_requests.items()):
            if pending.workspace_id == workspace_id and (
                cleanup_node_ids is None or pending.node_id in cleanup_node_ids
            ):
                retired_request_ids.add(request_id)
                pending_requests.pop(request_id, None)
        for session_key, node_id in tuple(session_node_ids.items()):
            if session_key[0] == workspace_id and (
                cleanup_node_ids is None or node_id in cleanup_node_ids
            ):
                session_ids.discard(session_key)
                session_generations.pop(session_key, None)
                session_node_ids.pop(session_key, None)
        return _ConcreteViewerInvalidationPlan(
            workspace_epochs=workspace_epochs,
            node_epochs=planned_node_epochs,
            pending_requests=pending_requests,
            session_ids=session_ids,
            session_generations=session_generations,
            session_node_ids=session_node_ids,
            retired_request_ids=frozenset(retired_request_ids),
        )

    def _apply_viewer_invalidation_plan_locked(
        self, plan: _ConcreteViewerInvalidationPlan
    ) -> None:
        self._workspace_viewer_epochs = plan.workspace_epochs
        self._node_viewer_epochs = plan.node_epochs
        self._pending_viewer_requests = plan.pending_requests
        self._viewer_session_ids = plan.session_ids
        self._viewer_session_generations = plan.session_generations
        self._viewer_session_node_ids = plan.session_node_ids

    def _track_viewer_request(self, pending: _PendingViewerRequest) -> None:
        generation_token = self._catalog_generation_token_value()
        with self._viewer_request_lock:
            if pending.generation_token != generation_token:
                pending = replace(
                    pending,
                    generation_token=generation_token,
                )
            self._pending_viewer_requests[pending.request_id] = pending

    @staticmethod
    def _pending_viewer_request(command: WorkerCommand) -> _PendingViewerRequest:
        return _PendingViewerRequest(
            request_id=str(getattr(command, "request_id", "")),
            command=str(getattr(command, "type", "")),
            workspace_id=str(getattr(command, "workspace_id", "")),
            node_id=str(getattr(command, "node_id", "")),
            session_id=str(getattr(command, "session_id", "")),
            workspace_invalidation_epoch=int(
                getattr(command, "workspace_invalidation_epoch", 0)
            ),
            node_invalidation_epoch=int(getattr(command, "node_invalidation_epoch", 0)),
        )

    def _complete_viewer_request(self, request_id: str) -> _PendingViewerRequest | None:
        if not request_id:
            return None
        with self._viewer_request_lock:
            return self._pending_viewer_requests.pop(request_id, None)

    def _record_viewer_response_state(
        self,
        payload: Mapping[str, Any],
        *,
        default_generation_token: int,
        expected_generation_token: int | None = None,
    ) -> int:
        event_type = str(payload.get("type", "") or "")
        workspace_id = str(payload.get("workspace_id", "") or "").strip()
        node_id = str(payload.get("node_id", "") or "").strip()
        session_id = str(payload.get("session_id", "") or "").strip()
        request_id = str(payload.get("request_id", "") or "").strip()
        workspace_epoch = int(payload.get("workspace_invalidation_epoch", 0))
        node_epoch = int(payload.get("node_invalidation_epoch", 0))
        state_context = (
            self._state_lock if expected_generation_token is not None else nullcontext()
        )
        with state_context:
            if expected_generation_token is not None and (
                self._catalog_generation_token != expected_generation_token
                or self._accepted_physical_generation_token != expected_generation_token
            ):
                return -1
            with self._viewer_request_lock:
                pending = self._pending_viewer_requests.get(request_id)
                current_workspace_epoch = self._workspace_viewer_epochs.get(
                    workspace_id, 0
                )
                current_node_epoch = self._node_viewer_epochs.get(
                    (workspace_id, node_id), 0
                )
                if (
                    workspace_epoch != current_workspace_epoch
                    or node_epoch != current_node_epoch
                    or request_id
                    and (
                        pending is None
                        or pending.workspace_id != workspace_id
                        or pending.node_id != node_id
                        or pending.session_id
                        and pending.session_id != session_id
                        or pending.workspace_invalidation_epoch != workspace_epoch
                        or pending.node_invalidation_epoch != node_epoch
                    )
                ):
                    return -1
                generation_token = (
                    pending.generation_token
                    if pending is not None
                    else self._viewer_session_generations.get(
                        (workspace_id, session_id),
                        default_generation_token,
                    )
                )
                if workspace_id and session_id:
                    session_key = (workspace_id, session_id)
                    if event_type == "viewer_session_closed":
                        self._viewer_session_ids.discard(session_key)
                        self._viewer_session_generations.pop(session_key, None)
                        self._viewer_session_node_ids.pop(session_key, None)
                    elif event_type != "viewer_session_failed":
                        self._viewer_session_ids.add(session_key)
                        self._viewer_session_generations[session_key] = generation_token
                        self._viewer_session_node_ids[session_key] = node_id
                if request_id:
                    self._pending_viewer_requests.pop(request_id, None)
        return generation_token

    def _event_generation_token(self, payload: Mapping[str, Any]) -> int:
        event_type = str(payload.get("type", "") or "")
        run_id = str(payload.get("run_id", "") or "").strip()
        request_id = str(payload.get("request_id", "") or "").strip()
        workspace_id = str(payload.get("workspace_id", "") or "").strip()
        session_id = str(payload.get("session_id", "") or "").strip()
        with self._state_lock:
            current_generation = self._catalog_generation_token
            run_generation = self._run_generation_tokens.get(run_id, 0)
        if run_id:
            return run_generation
        with self._viewer_request_lock:
            pending = self._pending_viewer_requests.get(request_id)
            if pending is not None:
                return pending.generation_token
            if workspace_id and session_id:
                return self._viewer_session_generations.get(
                    (workspace_id, session_id),
                    0,
                )
        if (
            event_type in VIEWER_RESPONSE_EVENT_TYPES
            or run_id
            or request_id
            or workspace_id
            or session_id
        ):
            return 0
        return current_generation

    def _dispatch_viewer_request_failure(
        self,
        pending: _PendingViewerRequest,
        error: str,
        *,
        generation_token: int | None = None,
    ) -> None:
        self._dispatch_event(
            ViewerSessionFailedEvent(
                request_id=pending.request_id,
                workspace_id=pending.workspace_id,
                node_id=pending.node_id,
                session_id=pending.session_id,
                command=pending.command,
                error=error,
                workspace_invalidation_epoch=(pending.workspace_invalidation_epoch),
                node_invalidation_epoch=pending.node_invalidation_epoch,
            ),
            generation_token=(
                pending.generation_token
                if generation_token is None and pending.generation_token
                else generation_token
            ),
        )

    def _viewer_protocol_error_failure(
        self,
        payload: dict[str, Any],
        *,
        expected_generation_token: int | None = None,
    ) -> ViewerSessionFailedEvent | None:
        command = str(payload.get("command", ""))
        if command not in VIEWER_COMMAND_TYPES:
            return None
        request_id = str(payload.get("request_id", ""))
        if expected_generation_token is None:
            pending = self._complete_viewer_request(request_id)
        else:
            with self._state_lock:
                if (
                    self._catalog_generation_token != expected_generation_token
                    or self._accepted_physical_generation_token
                    != expected_generation_token
                ):
                    return None
                pending = self._complete_viewer_request(request_id)
        if pending is None:
            return None
        return ViewerSessionFailedEvent(
            request_id=pending.request_id,
            workspace_id=pending.workspace_id or str(payload.get("workspace_id", "")),
            node_id=pending.node_id,
            session_id=pending.session_id,
            command=command,
            error=str(payload.get("error", "")),
            workspace_invalidation_epoch=(pending.workspace_invalidation_epoch),
            node_invalidation_epoch=pending.node_invalidation_epoch,
        )

    def pause_run(self, run_id: str) -> None:
        if run_id:
            self._post_command(PauseRunCommand(run_id=run_id))

    def resume_run(self, run_id: str) -> None:
        if run_id:
            self._post_command(ResumeRunCommand(run_id=run_id))

    def stop_run(self, run_id: str) -> None:
        if run_id:
            self._post_command(StopRunCommand(run_id=run_id))

    @_registry_admitted
    def open_viewer_session(
        self,
        workspace_id: str,
        node_id: str,
        *,
        session_id: str = "",
        backend_id: str = "",
        data_refs: dict[str, Any] | None = None,
        transport: dict[str, Any] | None = None,
        transport_revision: int = 0,
        live_open_status: str = "",
        live_open_blocker: dict[str, Any] | None = None,
        camera_state: dict[str, Any] | None = None,
        playback_state: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        _request_id: str = "",
    ) -> str:
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return self._send_viewer_command(
            OpenViewerSessionCommand(
                request_id=_request_id or self._next_viewer_request_id(),
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=backend_id,
                data_refs=dict(data_refs or {}),
                transport=dict(transport or {}),
                transport_revision=int(transport_revision),
                live_open_status=live_open_status,
                live_open_blocker=dict(live_open_blocker or {}),
                camera_state=dict(camera_state or {}),
                playback_state=dict(playback_state or {}),
                summary=dict(summary or {}),
                options=dict(options or {}),
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            )
        )

    def update_viewer_session(
        self,
        workspace_id: str,
        node_id: str,
        session_id: str,
        *,
        backend_id: str = "",
        data_refs: dict[str, Any] | None = None,
        transport: dict[str, Any] | None = None,
        transport_revision: int = 0,
        live_open_status: str = "",
        live_open_blocker: dict[str, Any] | None = None,
        camera_state: dict[str, Any] | None = None,
        playback_state: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return self._send_viewer_command(
            UpdateViewerSessionCommand(
                request_id=self._next_viewer_request_id(),
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=backend_id,
                data_refs=dict(data_refs or {}),
                transport=dict(transport or {}),
                transport_revision=int(transport_revision),
                live_open_status=live_open_status,
                live_open_blocker=dict(live_open_blocker or {}),
                camera_state=dict(camera_state or {}),
                playback_state=dict(playback_state or {}),
                summary=dict(summary or {}),
                options=dict(options or {}),
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            ),
            require_session_id=True,
        )

    def close_viewer_session(
        self,
        workspace_id: str,
        node_id: str,
        session_id: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return self._send_viewer_command(
            CloseViewerSessionCommand(
                request_id=self._next_viewer_request_id(),
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                options=dict(options or {}),
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            ),
            require_session_id=True,
        )

    def materialize_viewer_data(
        self,
        workspace_id: str,
        node_id: str,
        session_id: str,
        *,
        backend_id: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return self._send_viewer_command(
            MaterializeViewerDataCommand(
                request_id=self._next_viewer_request_id(),
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=backend_id,
                options=dict(options or {}),
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            ),
            require_session_id=True,
        )

    def query_viewer_session(
        self,
        workspace_id: str,
        node_id: str,
        session_id: str,
        *,
        backend_id: str = "",
        query_type: str,
        payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        workspace_epoch, node_epoch = self._viewer_epochs(workspace_id, node_id)
        return self._send_viewer_command(
            QueryViewerSessionCommand(
                request_id=self._next_viewer_request_id(),
                workspace_id=workspace_id,
                node_id=node_id,
                session_id=session_id,
                backend_id=backend_id,
                query_type=str(query_type or "").strip(),
                payload=dict(payload or {}),
                options=dict(options or {}),
                workspace_invalidation_epoch=workspace_epoch,
                node_invalidation_epoch=node_epoch,
            ),
            require_session_id=True,
        )
