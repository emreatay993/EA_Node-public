# Purpose: Carry per-invocation node inputs, services, outputs, and structured warnings.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_function_plugin.py

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Protocol

from ea_node_editor.runtime_contracts import (
    DataPath,
    DataTypeCatalog,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    coerce_runtime_artifact_ref,
    coerce_runtime_handle_ref,
)


class NodeInputNotReadyError(ValueError):
    """Signal that a node is waiting for user-provided input."""


class ExecutionHandleServices(Protocol):
    @property
    def data_types(self) -> DataTypeCatalog: ...

    def register_handle(
        self,
        value: Any,
        *,
        data_type_id: str,
        kind: str,
        run_id: str = "",
        owner_scope: str = "",
        metadata: Mapping[str, Any] | None = None,
        dispose: Callable[[], None] | None = None,
    ) -> RuntimeHandleRef: ...

    def resolve_handle(
        self,
        value: Any,
        *,
        expected_data_type: str | None = None,
        expected_kind: str = "",
    ) -> Any: ...

    def release_handle(self, value: Any) -> bool: ...

    def lease_handle(
        self,
        value: Any,
        *,
        owner_scope: str,
    ) -> RuntimeHandleRef: ...

    @property
    def mechanical_session_service(self) -> Any: ...


class RuntimeSnapshotPort(Protocol):
    metadata: Mapping[str, Any]


class RuntimeSnapshotContextPort(Protocol):
    artifact_store: Any

    def project_metadata(self) -> dict[str, Any]: ...


def _publish_node_state_unavailable(_node_id: str, _value: Any) -> None:
    raise RuntimeError("ExecutionContext does not have run-scoped node state.")


def _read_node_state_unavailable(_node_id: str) -> Any | None:
    raise RuntimeError("ExecutionContext does not have run-scoped node state.")


def _request_observation_invalidation_unavailable(
    _root_node_id: str, _reason_code: str
) -> None:
    raise RuntimeError("ExecutionContext does not have runtime invalidation authority.")


_PLUGIN_WARNING_CODE = re.compile(r"^[a-z][a-z0-9_.-]*$")


@dataclass(slots=True, frozen=True)
class PluginWarning:
    message: str
    code: str
    run_id: str
    node_id: str
    path: DataPath
    iteration: int


@dataclass(slots=True)
class ExecutionContext:
    run_id: str
    node_id: str
    workspace_id: str
    inputs: dict[str, Any]
    properties: dict[str, Any]
    emit_log: Callable[[str, str], None]
    trigger: dict[str, Any] = field(default_factory=dict)
    target_path: DataPath = (0,)
    target_iteration: int = 0
    iteration_count: int = 1
    should_stop: Callable[[], bool] = field(default=lambda: False)
    register_cancel: Callable[[Callable[[], None]], None] = field(default=lambda _callback: None)
    project_path: str = ""
    workspace_name: str = ""
    runtime_snapshot: RuntimeSnapshotPort | None = None
    runtime_snapshot_context: RuntimeSnapshotContextPort | None = None
    path_resolver: Callable[[Any], Path | None] = field(default=lambda _value: None)
    worker_services: ExecutionHandleServices | None = None
    developer_mode: bool = False
    node_title: str = ""
    node_type_id: str = ""
    node_type_display_name: str = ""
    node_port_labels: Mapping[str, str] = field(default_factory=dict)
    semantic_links: tuple[Mapping[str, Any], ...] = ()
    workspace_node_types: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    _publish_node_state: Callable[[str, Any], None] = field(
        default=_publish_node_state_unavailable,
        repr=False,
    )
    _read_node_state: Callable[[str], Any | None] = field(
        default=_read_node_state_unavailable,
        repr=False,
    )
    _request_observation_invalidation: Callable[[str, str], None] = field(
        default=_request_observation_invalidation_unavailable,
        repr=False,
    )
    _plugin_warnings: list[PluginWarning] = field(default_factory=list, repr=False)

    @property
    def artifact_store(self) -> Any | None:
        context = self.runtime_snapshot_context
        if context is None:
            return None
        return context.artifact_store

    def runtime_project_metadata(self) -> dict[str, Any]:
        context = self.runtime_snapshot_context
        if context is not None:
            return context.project_metadata()
        if self.runtime_snapshot is None:
            return {}
        return copy.deepcopy(self.runtime_snapshot.metadata)

    def log_info(self, message: str) -> None:
        self.emit_log("info", message)

    def log_warning(self, message: str) -> None:
        self.emit_log("warning", message)

    def log_error(self, message: str) -> None:
        self.emit_log("error", message)

    def warn(self, message: str, *, code: str = "plugin_warning") -> None:
        if not isinstance(message, str):
            raise TypeError("Plugin warning message must be a string")
        if not message.strip():
            raise ValueError("Plugin warning message must not be empty")
        if len(message) > 2048:
            raise ValueError("Plugin warning message must contain at most 2048 characters")
        if not isinstance(code, str):
            raise TypeError("Plugin warning code must be a string")
        if len(code) > 64 or _PLUGIN_WARNING_CODE.fullmatch(code) is None:
            raise ValueError(
                "Plugin warning code must match [a-z][a-z0-9_.-]* and contain at most 64 characters"
            )
        self._plugin_warnings.append(
            PluginWarning(
                message=message,
                code=code,
                run_id=self.run_id,
                node_id=self.node_id,
                path=self.target_path,
                iteration=self.target_iteration,
            )
        )

    def _plugin_warning_cursor(self) -> int:
        return len(self._plugin_warnings)

    def _plugin_warnings_since(self, cursor: int) -> tuple[PluginWarning, ...]:
        return tuple(self._plugin_warnings[max(0, int(cursor)) :])

    def publish_node_state(self, node_id: str, value: Any) -> None:
        normalized_node_id = str(node_id or "").strip()
        if normalized_node_id not in self.workspace_node_types:
            raise KeyError(f"Unknown workspace node ID: {normalized_node_id!r}")
        self._publish_node_state(normalized_node_id, value)

    def read_node_state(self, node_id: str) -> Any | None:
        normalized_node_id = str(node_id or "").strip()
        if normalized_node_id not in self.workspace_node_types:
            raise KeyError(f"Unknown workspace node ID: {normalized_node_id!r}")
        return self._read_node_state(normalized_node_id)

    def request_observation_invalidation(
        self, root_node_id: str, *, reason_code: str
    ) -> None:
        root = str(root_node_id or "").strip()
        reason = str(reason_code or "").strip()
        if root not in self.workspace_node_types:
            raise KeyError(f"Unknown workspace node ID: {root!r}")
        if not reason or len(reason) > 256:
            raise ValueError("Observation invalidation reason must be bounded non-empty text")
        self._request_observation_invalidation(root, reason)

    def runtime_artifact_ref(self, value: Any) -> RuntimeArtifactRef | None:
        return coerce_runtime_artifact_ref(value)

    def runtime_handle_ref(self, value: Any) -> RuntimeHandleRef | None:
        catalog = (
            self.worker_services.data_types
            if self.worker_services is not None
            else None
        )
        return coerce_runtime_handle_ref(value, catalog=catalog)

    def _require_worker_services(self) -> ExecutionHandleServices:
        if self.worker_services is None:
            raise RuntimeError("ExecutionContext does not have worker services.")
        return self.worker_services

    @property
    def mechanical_sessions(self) -> Any:
        return self._require_worker_services().mechanical_session_service

    def register_handle(
        self,
        value: Any,
        *,
        data_type_id: str,
        kind: str,
        owner_scope: str = "",
        metadata: Mapping[str, Any] | None = None,
        dispose: Callable[[], None] | None = None,
    ) -> RuntimeHandleRef:
        return self._require_worker_services().register_handle(
            value,
            data_type_id=data_type_id,
            kind=kind,
            run_id=self.run_id,
            owner_scope=owner_scope,
            metadata=metadata,
            dispose=dispose,
        )

    def resolve_handle(
        self,
        value: Any,
        *,
        expected_data_type: str | None = None,
        expected_kind: str = "",
    ) -> Any:
        runtime_ref = self.runtime_handle_ref(value)
        if runtime_ref is None:
            raise TypeError("ExecutionContext.resolve_handle requires a RuntimeHandleRef payload.")
        return self._require_worker_services().resolve_handle(
            runtime_ref,
            expected_data_type=expected_data_type,
            expected_kind=expected_kind,
        )

    def release_handle(self, value: Any) -> bool:
        runtime_ref = self.runtime_handle_ref(value)
        if runtime_ref is None:
            raise TypeError("ExecutionContext.release_handle requires a RuntimeHandleRef payload.")
        return self._require_worker_services().release_handle(runtime_ref)

    def lease_handle(
        self,
        value: Any,
        *,
        owner_scope: str,
    ) -> RuntimeHandleRef:
        runtime_ref = self.runtime_handle_ref(value)
        if runtime_ref is None:
            raise TypeError(
                "ExecutionContext.lease_handle requires a RuntimeHandleRef payload."
            )
        return self._require_worker_services().lease_handle(
            runtime_ref,
            owner_scope=owner_scope,
        )

    def resolve_path_value(self, value: Any) -> Path | None:
        runtime_ref = self.runtime_artifact_ref(value)
        candidate = runtime_ref if runtime_ref is not None else value
        return self.path_resolver(candidate)

    def resolve_input_path(self, input_key: str, *, property_key: str = "") -> Path | None:
        candidates = [self.inputs.get(input_key)]
        if property_key:
            candidates.append(self.properties.get(property_key))
        for candidate in candidates:
            path = self.resolve_path_value(candidate)
            if path is not None:
                return path
        return None


@dataclass(slots=True)
class NodeResult:
    outputs: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    plugin_warnings: tuple[PluginWarning, ...] = ()


__all__ = [
    "ExecutionContext",
    "ExecutionHandleServices",
    "NodeInputNotReadyError",
    "NodeResult",
]
