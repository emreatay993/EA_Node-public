from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.common.payload_tools import (
    artifact_content_integrity,
    copy_json_safe,
)
from ea_node_editor.execution.compiler import compile_runtime_snapshot
from ea_node_editor.execution import execution_plan as _execution_plan
from ea_node_editor.execution.run_messages import (
    StartRunCommand,
)
from ea_node_editor.execution.registry_agreement import (
    normalize_addon_runtime_config,
)
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotContext,
)
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.common.artifact_refs import (
    ARTIFACT_REF_SCHEME,
    STAGED_ARTIFACT_REF_SCHEME,
    normalize_artifact_id,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2DRef,
    DataTree,
    DataTypeCatalog,
    Interval1D,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TabularDataRef,
    TabularWindowRef,
    TypedInlineValue,
    coerce_runtime_artifact_ref,
)

_UNTYPED_ARTIFACT_PREFIXES = (
    f"{ARTIFACT_REF_SCHEME}://",
    f"{STAGED_ARTIFACT_REF_SCHEME}://",
)


def load_runtime_snapshot(
    command: StartRunCommand,
) -> RuntimeSnapshot:
    if command.runtime_snapshot is None:
        raise ValueError("start_run requires runtime_snapshot.")
    return command.runtime_snapshot


@dataclass(slots=True)
class PreparedRuntime:
    registry: Any
    plugin_runtime: WorkerPluginRuntime
    runtime_snapshot: RuntimeSnapshot
    runtime_context: RuntimeSnapshotContext
    workspace: RuntimeWorkspace
    plan: _execution_plan.ExecutionPlan


class RuntimeArtifactService:
    def __init__(
        self,
        *,
        runtime_context: RuntimeSnapshotContext,
        data_types: DataTypeCatalog,
    ) -> None:
        self._runtime_context = runtime_context
        self._data_types = data_types
        self._project_path = str(runtime_context.project_path).strip()
        self._resolver = ProjectArtifactResolver(
            project_path=self._project_path or None,
            artifact_store=runtime_context.artifact_store,
        )

    @property
    def project_path(self) -> str:
        return self._project_path

    @property
    def runtime_context(self) -> RuntimeSnapshotContext:
        return self._runtime_context

    @property
    def store(self):
        return self._resolver.store

    def normalize_outputs(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ea_node_editor.runtime_contracts.value_codec import (
            deserialize_runtime_value,
            serialize_runtime_value,
        )

        normalized = deserialize_runtime_value(
            serialize_runtime_value(payload, catalog=self._data_types),
            catalog=self._data_types,
        )
        normalized_outputs = (
            dict(normalized) if isinstance(normalized, dict) else {}
        )
        self._verify_runtime_artifacts(normalized_outputs)
        return normalized_outputs

    def materialize_persisted_value(
        self,
        value: Any,
    ) -> Any:
        return self._materialize_persisted_value(
            value,
            _runtime_markers_decoded=False,
        )

    def materialize_authored_properties(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        """Admit registered project-import refs only at the authored-property boundary.

        Runtime values, outputs, and path resolution still require typed carriers.
        Authored temp refs become carriers only after store/descriptor/content checks.
        """
        return self._materialize_persisted_value(
            properties, _runtime_markers_decoded=False, _authored_staged_refs=True,
        )

    def _materialize_persisted_value(
        self,
        value: Any,
        *,
        _runtime_markers_decoded: bool,
        _authored_staged_refs: bool = False,
    ) -> Any:
        if isinstance(value, RuntimeArtifactRef):
            self._verify_runtime_artifact(value)
            return value
        if isinstance(
            value,
            (
                ArrayDataRef,
                ArraySlice2DRef,
                RuntimeHandleRef,
                TabularDataRef,
                TabularWindowRef,
                TypedInlineValue,
            ),
        ):
            self._data_types.validate_carrier(value.data_type_id, value)
            return value
        if isinstance(value, Interval1D):
            return value
        if isinstance(value, DataTree):
            return DataTree(
                (
                    path,
                    tuple(
                        self._materialize_persisted_value(
                            item,
                            _runtime_markers_decoded=_runtime_markers_decoded,
                            _authored_staged_refs=_authored_staged_refs,
                        )
                        for item in items
                    ),
                )
                for path, items in value.branches
            )
        if isinstance(value, Mapping):
            if not _runtime_markers_decoded and "__ea_runtime_value__" in value:
                from ea_node_editor.runtime_contracts.value_codec import (
                    deserialize_runtime_value,
                )

                decoded = deserialize_runtime_value(
                    value,
                    catalog=self._data_types,
                )
                if isinstance(decoded, DataTree) or not isinstance(
                    decoded, Mapping
                ):
                    return self._materialize_persisted_value(
                        decoded,
                        _runtime_markers_decoded=True,
                        _authored_staged_refs=_authored_staged_refs,
                    )
                value = decoded
                _runtime_markers_decoded = True
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(
                        "persisted runtime property mapping keys must be strings"
                    )
                copied[key] = self._materialize_persisted_value(
                    item,
                    _runtime_markers_decoded=_runtime_markers_decoded,
                    _authored_staged_refs=_authored_staged_refs,
                )
            return copied
        if isinstance(value, list):
            return [
                self._materialize_persisted_value(
                    item,
                    _runtime_markers_decoded=_runtime_markers_decoded,
                    _authored_staged_refs=_authored_staged_refs,
                )
                for item in value
            ]
        if isinstance(value, tuple):
            return tuple(
                self._materialize_persisted_value(
                    item,
                    _runtime_markers_decoded=_runtime_markers_decoded,
                    _authored_staged_refs=_authored_staged_refs,
                )
                for item in value
            )
        if not _is_untyped_artifact_reference(value):
            return copy_json_safe(
                value,
                field_name="persisted runtime property",
            )

        text = value.strip()
        saved_prefix = f"{ARTIFACT_REF_SCHEME}://"
        staged_prefix = f"{STAGED_ARTIFACT_REF_SCHEME}://"
        staged = text.casefold().startswith(staged_prefix)
        if staged and not _authored_staged_refs:
            raise TypeError(
                "artifact references must use RuntimeArtifactRef"
            )
        prefix = staged_prefix if staged else saved_prefix
        if not text.startswith(prefix) or (_authored_staged_refs and text != value):
            raise ValueError("persisted artifact reference is malformed")
        artifact_id = normalize_artifact_id(text[len(prefix) :])
        if not artifact_id or text != f"{prefix}{artifact_id}":
            raise ValueError("persisted artifact reference is malformed")

        entry = self.store.staged_entry(artifact_id) if staged else self.store.managed_entry(artifact_id)
        if entry is None:
            raise FileNotFoundError(
                f"artifact {artifact_id!r} is not registered in the active store"
            )
        if "runtime_artifact" not in entry.extra:
            raise ValueError(
                f"artifact {artifact_id!r} descriptor is missing"
            )
        descriptor = entry.extra["runtime_artifact"]
        if not isinstance(descriptor, Mapping):
            raise ValueError(
                f"artifact {artifact_id!r} descriptor is invalid"
            )
        try:
            runtime_ref = RuntimeArtifactRef.from_artifact_ref(
                text,
                data_type_id=descriptor["data_type_id"],
                schema_version=descriptor["schema_version"],
                format=descriptor["format"],
                size_bytes=descriptor["size_bytes"],
                sha256=descriptor["sha256"],
                provenance=descriptor["provenance"],
            )
            self._data_types.validate_carrier(
                runtime_ref.data_type_id,
                runtime_ref,
            )
            if set(descriptor) != set(runtime_ref.to_descriptor()):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"artifact {artifact_id!r} descriptor is invalid"
            ) from None
        if (
            runtime_ref.scope != ("staged" if staged else "managed")
            or runtime_ref.artifact_id != artifact_id
        ):
            raise ValueError(
                f"artifact {artifact_id!r} descriptor does not match"
            )
        self._verify_runtime_artifact(runtime_ref)
        return runtime_ref

    def resolve_path(self, value: Any) -> Any:
        if _is_untyped_artifact_reference(value):
            raise TypeError(
                "artifact references must use RuntimeArtifactRef"
            )
        runtime_ref = coerce_runtime_artifact_ref(
            value,
            catalog=self._data_types,
        )
        if runtime_ref is not None:
            return self._verify_runtime_artifact(runtime_ref)
        return self._resolver.resolve_to_path(value)

    def _verify_runtime_artifacts(self, value: Any) -> None:
        if _is_untyped_artifact_reference(value):
            raise TypeError(
                "artifact references must use RuntimeArtifactRef"
            )
        if isinstance(value, RuntimeArtifactRef):
            self._verify_runtime_artifact(value)
            return
        if isinstance(value, DataTree):
            for _path, items in value.branches:
                for item in items:
                    self._verify_runtime_artifacts(item)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                self._verify_runtime_artifacts(item)
            return
        if isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            for item in value:
                self._verify_runtime_artifacts(item)

    def _verify_runtime_artifact(
        self,
        runtime_ref: RuntimeArtifactRef,
    ) -> Path:
        artifact_id = runtime_ref.artifact_id
        self._data_types.validate_carrier(
            runtime_ref.data_type_id,
            runtime_ref,
        )
        if runtime_ref.scope == "staged":
            entry = self.store.staged_entry(artifact_id)
            resolved_path = self.store.resolve_staged_path(artifact_id)
            trusted_root = self.store.active_staging_root()
            relative_path = entry.relative_path if entry is not None else None
            try:
                trusted_target = (
                    self.store.staged_target_path(relative_path)
                    if relative_path
                    else None
                )
            except ValueError:
                trusted_target = None
        else:
            entry = self.store.managed_entry(artifact_id)
            resolved_path = self.store.resolve_managed_path(artifact_id)
            layout = self.store.layout
            trusted_root = layout.sidecar_root if layout is not None else None
            relative_path = entry.relative_path if entry is not None else None
            trusted_target = (
                layout.absolute_path_for_relative(relative_path)
                if layout is not None and relative_path
                else None
            )
        if (
            entry is None
            or resolved_path is None
            or trusted_root is None
            or trusted_target is None
            or not relative_path
        ):
            raise FileNotFoundError(
                f"artifact {artifact_id!r} is not registered in the active store"
            )
        if _normalized_absolute_path(resolved_path) != _normalized_absolute_path(
            trusted_target
        ):
            raise ValueError(
                f"artifact {artifact_id!r} store target does not match"
            )

        descriptor = entry.extra.get("runtime_artifact")
        expected_descriptor = runtime_ref.to_descriptor()
        if not isinstance(descriptor, Mapping):
            raise ValueError(
                f"artifact {artifact_id!r} descriptor is missing"
            )
        if set(descriptor) != set(expected_descriptor):
            raise ValueError(
                f"artifact {artifact_id!r} descriptor fields do not match"
            )
        for field_name, expected_value in expected_descriptor.items():
            actual_value = descriptor.get(field_name)
            if (
                type(actual_value) is not type(expected_value)
                or actual_value != expected_value
            ):
                raise ValueError(
                    f"artifact {artifact_id!r} descriptor field "
                    f"{field_name!r} does not match"
                )

        try:
            size_bytes, sha256 = artifact_content_integrity(
                trusted_root,
                relative_path,
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"artifact {artifact_id!r} payload is missing"
            ) from None
        except (OSError, ValueError):
            raise ValueError(
                f"artifact {artifact_id!r} payload could not be verified"
            ) from None
        if size_bytes != runtime_ref.size_bytes:
            raise ValueError(
                f"artifact {artifact_id!r} size_bytes does not match"
            )
        if sha256 != runtime_ref.sha256:
            raise ValueError(
                f"artifact {artifact_id!r} sha256 does not match"
            )
        return resolved_path


def _normalized_absolute_path(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def _is_untyped_artifact_reference(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold().startswith(
        _UNTYPED_ARTIFACT_PREFIXES
    )


def resolve_runtime_artifact_store(
    *,
    project_path: str = "",
    runtime_snapshot: RuntimeSnapshot | None = None,
    runtime_context: RuntimeSnapshotContext | None = None,
) -> ProjectArtifactStore:
    if runtime_context is not None:
        return runtime_context.artifact_store
    project_metadata = (
        runtime_snapshot.metadata if runtime_snapshot is not None else None
    )
    return ProjectArtifactStore.from_project_metadata(
        project_path=str(project_path).strip() or None,
        project_metadata=project_metadata
        if isinstance(project_metadata, Mapping)
        else None,
    )


class RuntimePreparationCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._registry: Any | None = None
        self._registry_provider_id: Any = 0
        self._registry_addon_runtime_config: tuple[tuple[str, bool], ...] | None = None
        self._compiled_workspaces: dict[tuple[int, str, str], RuntimeWorkspace] = {}
        self._plugin_runtime = WorkerPluginRuntime()

    def default_registry(
        self,
        addon_runtime_config: tuple[tuple[str, bool], ...] | None = None,
    ) -> Any:
        from ea_node_editor.nodes.bootstrap import build_default_registry

        provider_id = id(build_default_registry)
        normalized_config = (
            None
            if addon_runtime_config is None
            else normalize_addon_runtime_config(addon_runtime_config)
        )
        with self._lock:
            if (
                self._registry is not None
                and self._registry_provider_id == provider_id
                and self._registry_addon_runtime_config != normalized_config
            ):
                raise ValueError(
                    "Runtime preparation cache must be retired before add-on "
                    "configuration changes"
                )
            if (
                self._registry is None
                or self._registry_provider_id != provider_id
            ):
                self._plugin_runtime.clear()
                self._registry = build_default_registry(
                    include_public_plugins=False,
                    addon_runtime_config=normalized_config,
                )
                self._registry_provider_id = provider_id
                self._registry_addon_runtime_config = normalized_config
                self._compiled_workspaces.clear()
            return self._registry

    def prepare_plugin_registry(
        self,
        command: StartRunCommand,
        registry: Any,
    ) -> tuple[Any, WorkerPluginRuntime]:
        return (
            self._plugin_runtime.prepare_registry(command, registry),
            self._plugin_runtime,
        )

    def compiled_workspace(
        self,
        runtime_snapshot: RuntimeSnapshot,
        *,
        workspace_id: str,
        registry: Any,
    ) -> RuntimeWorkspace:
        cache_key = self._workspace_cache_key(
            runtime_snapshot,
            workspace_id=workspace_id,
            registry=registry,
        )
        with self._lock:
            cached = self._compiled_workspaces.get(cache_key)
            if cached is not None:
                return cached
        compiled = compile_runtime_snapshot(
            runtime_snapshot,
            workspace_id=workspace_id,
            registry=registry,
        )
        with self._lock:
            return self._compiled_workspaces.setdefault(cache_key, compiled)

    @staticmethod
    def _workspace_cache_key(
        runtime_snapshot: RuntimeSnapshot,
        *,
        workspace_id: str,
        registry: Any,
    ) -> tuple[int, str, str]:
        snapshot_payload = runtime_snapshot.to_document(catalog=registry.data_types)
        digest = hashlib.sha256(
            json.dumps(
                snapshot_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        return (id(registry), str(workspace_id).strip(), digest)

    def clear(self) -> None:
        with self._lock:
            self._plugin_runtime.clear()
            self._compiled_workspaces.clear()
            self._registry = None
            self._registry_provider_id = 0
            self._registry_addon_runtime_config = None


DEFAULT_RUNTIME_PREPARATION_CACHE = RuntimePreparationCache()


def prepare_runtime(
    command: StartRunCommand,
    *,
    cache: RuntimePreparationCache | None = None,
) -> PreparedRuntime:
    runtime_cache = cache or DEFAULT_RUNTIME_PREPARATION_CACHE
    trusted_registry = runtime_cache.default_registry(command.addon_runtime_config)
    registry, plugin_runtime = runtime_cache.prepare_plugin_registry(
        command,
        trusted_registry,
    )
    runtime_snapshot = load_runtime_snapshot(command)
    artifact_context_project_path = command.project_path
    runtime_context = RuntimeSnapshotContext.from_snapshot(
        runtime_snapshot,
        project_path=artifact_context_project_path,
    )
    workspace = runtime_cache.compiled_workspace(
        runtime_snapshot,
        workspace_id=command.workspace_id,
        registry=registry,
    )
    return PreparedRuntime(
        registry=registry,
        plugin_runtime=plugin_runtime,
        runtime_snapshot=runtime_snapshot,
        runtime_context=runtime_context,
        workspace=workspace,
        plan=_execution_plan.ExecutionPlan(
            workspace,
            registry,
            target_node_ids=tuple(command.target_node_ids),
            clicked_trigger_node_id=command.clicked_trigger_node_id,
            trigger_capture_node_ids=tuple(command.trigger_captures),
        ),
    )


__all__ = [
    "DEFAULT_RUNTIME_PREPARATION_CACHE",
    "PreparedRuntime",
    "RuntimePreparationCache",
    "RuntimeArtifactService",
    "load_runtime_snapshot",
    "prepare_runtime",
    "resolve_runtime_artifact_store",
]
