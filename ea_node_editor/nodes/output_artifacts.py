from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
import importlib
from pathlib import Path, PurePosixPath
from typing import Any

from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.core_data_types import CORE_DATA_TYPES
from ea_node_editor.runtime_contracts.value_refs import RuntimeArtifactRef
from ea_node_editor.runtime_contracts import PATH_DATA_TYPE_ID
from ea_node_editor.settings import (
    PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME,
    recent_session_path,
)

_INVALID_ARTIFACT_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_PATH_DATA_TYPE = next(
    spec for spec in CORE_DATA_TYPES if spec.type_id == PATH_DATA_TYPE_ID
)


@dataclass(frozen=True, slots=True)
class ManagedOutputWriteResult:
    path: Path
    artifact_ref: RuntimeArtifactRef


@dataclass(frozen=True, slots=True)
class ManagedOutputTarget:
    path: Path
    artifact_id: str
    relative_path: str
    slot: str
    format: str
    entry_metadata: dict[str, Any]


def _sanitize_artifact_token(value: Any, *, fallback: str) -> str:
    text = _INVALID_ARTIFACT_TOKEN_CHARS.sub("_", str(value).strip())
    text = text.strip("._-")
    return text or fallback


def _default_staging_workspace_root() -> Path:
    return recent_session_path().parent / PROJECT_ARTIFACT_SESSION_STAGING_DIRNAME


def _normalize_suffix(value: str) -> str:
    suffix = str(value or "").strip()
    if not suffix:
        return ""
    return suffix if suffix.startswith(".") else f".{suffix}"


def _normalize_artifact_format(value: str) -> str:
    return str(value or "").strip().casefold().lstrip(".")


def _normalize_managed_subdirectory(value: str) -> str:
    raw_path = PurePosixPath(str(value or "").replace("\\", "/"))
    parts = [part for part in raw_path.parts if part not in {"", ".", ".."}]
    return "/".join(parts) if parts else "generated"


def _artifact_resolver_type() -> type[Any]:
    module = importlib.import_module("ea_node_editor.persistence.artifact_resolution")
    return module.ProjectArtifactResolver


def _artifact_store_type() -> type[Any]:
    module = importlib.import_module("ea_node_editor.persistence.artifact_store")
    return module.ProjectArtifactStore


def _runtime_snapshot_context_type() -> type[Any]:
    module = importlib.import_module("ea_node_editor.execution.runtime_snapshot")
    return module.RuntimeSnapshotContext


def _managed_output_artifact_id(ctx: ExecutionContext, *, output_key: str) -> str:
    workspace_id = _sanitize_artifact_token(ctx.workspace_id, fallback="workspace")
    node_id = _sanitize_artifact_token(ctx.node_id, fallback="node")
    output_name = _sanitize_artifact_token(output_key, fallback="output")
    return f"generated.{workspace_id}.{node_id}.{output_name}"


def _managed_output_slot(ctx: ExecutionContext, *, output_key: str) -> str:
    return f"{ctx.workspace_id}:{ctx.node_id}:{output_key}"


def _artifact_provenance(ctx: ExecutionContext) -> str:
    raw_producer_id = str(ctx.node_type_id).strip()
    producer_id = _sanitize_artifact_token(raw_producer_id, fallback="")
    if not producer_id:
        raise ValueError(
            "artifact-producing execution contexts require node_type_id"
        )
    return f"corex.node:{producer_id}"


def _resolver_store_from_context(ctx: ExecutionContext) -> Any | None:
    owner = getattr(ctx.path_resolver, "__self__", None)
    if owner is None:
        return None
    artifact_resolver_type = _artifact_resolver_type()
    artifact_store_type = _artifact_store_type()
    if isinstance(owner, artifact_resolver_type):
        return owner.store

    direct_store = getattr(owner, "store", None)
    if isinstance(direct_store, artifact_store_type):
        return direct_store
    return None


def _artifact_store_for_context(ctx: ExecutionContext) -> Any:
    live_store = _resolver_store_from_context(ctx)
    if live_store is not None:
        _persist_runtime_artifact_store(ctx, live_store)
        return live_store

    if ctx.artifact_store is not None:
        return ctx.artifact_store

    store = _artifact_store_type().from_project_metadata(
        project_path=ctx.project_path or None,
        project_metadata=ctx.runtime_project_metadata(),
    )
    _persist_runtime_artifact_store(ctx, store)
    return store


def _persist_runtime_artifact_store(ctx: ExecutionContext, store: Any) -> None:
    if ctx.runtime_snapshot_context is not None:
        ctx.runtime_snapshot_context.artifact_store = store
        return

    if ctx.runtime_snapshot is None and not ctx.project_path:
        return

    ctx.runtime_snapshot_context = _runtime_snapshot_context_type().from_snapshot(
        ctx.runtime_snapshot,
        project_path=ctx.project_path,
        artifact_store=store,
    )


def register_staged_artifact(
    *,
    store: Any,
    artifact_id: str,
    payload_path: str | Path,
    relative_path: str,
    slot: str | None,
    data_type_id: str,
    schema_version: int,
    format: str,
    provenance: str,
    entry_metadata: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeArtifactRef:
    artifact_store_type = _artifact_store_type()
    if not isinstance(store, artifact_store_type):
        raise TypeError("artifact registration requires ProjectArtifactStore")
    normalized_format = _normalize_artifact_format(format)
    if not normalized_format:
        raise ValueError("artifact format must be a non-empty string")
    trusted_root = store.active_staging_root()
    if trusted_root is None:
        raise ValueError("artifact store staging root has not been allocated")
    trusted_target = store.staged_target_path(relative_path)
    if _normalized_absolute_path(payload_path) != _normalized_absolute_path(
        trusted_target
    ):
        raise ValueError(
            "artifact payload path must match the active store target"
        )
    size_bytes, sha256 = artifact_content_integrity(
        trusted_root,
        relative_path,
    )
    runtime_ref = RuntimeArtifactRef.staged(
        artifact_id,
        data_type_id=data_type_id,
        schema_version=schema_version,
        format=normalized_format,
        size_bytes=size_bytes,
        sha256=sha256,
        provenance=provenance,
        metadata=metadata,
    )
    extra = dict(entry_metadata or {})
    extra["runtime_artifact"] = runtime_ref.to_descriptor()
    store.register_staged_entry(
        artifact_id,
        relative_path=relative_path,
        slot=slot,
        extra=extra,
    )
    return runtime_ref


def _normalized_absolute_path(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def register_staged_path_artifact(
    ctx: ExecutionContext,
    *,
    store: Any,
    artifact_id: str,
    payload_path: str | Path,
    relative_path: str,
    slot: str | None,
    format: str,
    entry_metadata: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeArtifactRef:
    artifact_type = _PATH_DATA_TYPE
    if ctx.worker_services is not None:
        artifact_type = ctx.worker_services.data_types.require(PATH_DATA_TYPE_ID)
    return register_staged_artifact(
        store=store,
        artifact_id=artifact_id,
        payload_path=payload_path,
        relative_path=relative_path,
        slot=slot,
        data_type_id=artifact_type.type_id,
        schema_version=artifact_type.payload_schema_version,
        format=format,
        provenance=_artifact_provenance(ctx),
        entry_metadata=entry_metadata,
        metadata=metadata,
    )


def allocate_managed_output(
    ctx: ExecutionContext,
    *,
    output_key: str,
    default_suffix: str,
    managed_subdirectory: str = "generated",
) -> ManagedOutputTarget:
    store = _artifact_store_for_context(ctx)
    artifact_id = _managed_output_artifact_id(ctx, output_key=output_key)
    suffix = _normalize_suffix(default_suffix)
    artifact_format = _normalize_artifact_format(suffix)
    if not artifact_format:
        raise ValueError("default_suffix must define an artifact format")
    artifact_paths = store.node_artifact_paths(
        artifact_id=artifact_id,
        workspace_id=ctx.workspace_id,
        workspace_name=ctx.workspace_name,
        node_id=ctx.node_id,
        node_title=ctx.node_title,
        node_type=ctx.node_type_display_name or ctx.node_type_id,
        io_dir="out",
        subdirectory=_normalize_managed_subdirectory(managed_subdirectory),
        filename=f"{artifact_id}{suffix}",
    )
    store.ensure_staging_root(
        temporary_root_parent=_default_staging_workspace_root(),
    )
    store.discard_staged_entries((artifact_id,))
    store.discard_staged_paths((artifact_paths.staged_relative_path,))
    output_path = store.staged_target_path(
        artifact_paths.staged_relative_path
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _persist_runtime_artifact_store(ctx, store)
    return ManagedOutputTarget(
        path=output_path,
        artifact_id=artifact_id,
        relative_path=artifact_paths.staged_relative_path,
        slot=_managed_output_slot(ctx, output_key=output_key),
        format=artifact_format,
        entry_metadata=artifact_paths.metadata,
    )


def write_managed_output(
    ctx: ExecutionContext,
    *,
    output_key: str,
    default_suffix: str,
    managed_subdirectory: str = "generated",
    write_payload: Callable[[Path], None],
) -> ManagedOutputWriteResult:
    target = allocate_managed_output(
        ctx,
        output_key=output_key,
        default_suffix=default_suffix,
        managed_subdirectory=managed_subdirectory,
    )
    store = _artifact_store_for_context(ctx)
    try:
        write_payload(target.path)
        runtime_ref = register_staged_path_artifact(
            ctx,
            store=store,
            artifact_id=target.artifact_id,
            payload_path=target.path,
            relative_path=target.relative_path,
            slot=target.slot,
            format=target.format,
            entry_metadata=target.entry_metadata,
        )
        _persist_runtime_artifact_store(ctx, store)
    except BaseException:
        try:
            store.discard_staged_entries((target.artifact_id,))
        except BaseException:
            pass
        try:
            store.discard_staged_paths((target.relative_path,))
        except BaseException:
            pass
        try:
            _persist_runtime_artifact_store(ctx, store)
        except BaseException:
            pass
        raise
    return ManagedOutputWriteResult(
        path=target.path,
        artifact_ref=runtime_ref,
    )


def default_staging_workspace_root() -> Path:
    return _default_staging_workspace_root()


def artifact_store_for_context(ctx: ExecutionContext) -> Any:
    return _artifact_store_for_context(ctx)


def persist_artifact_store(ctx: ExecutionContext, store: Any) -> None:
    _persist_runtime_artifact_store(ctx, store)


__all__ = [
    "ManagedOutputTarget",
    "ManagedOutputWriteResult",
    "allocate_managed_output",
    "artifact_store_for_context",
    "default_staging_workspace_root",
    "persist_artifact_store",
    "register_staged_artifact",
    "register_staged_path_artifact",
    "write_managed_output",
]
