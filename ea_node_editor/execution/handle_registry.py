from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Iterator
from uuid import uuid4

from ea_node_editor.common.payload_tools import (
    REF_METADATA_MAX_BYTES,
    copy_json_mapping,
)
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
    RuntimeHandleRef,
    coerce_runtime_handle_ref,
)

_LOGGER = logging.getLogger(__name__)


def _copy_metadata_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return copy_json_mapping(
        value,
        field_name="metadata",
        max_encoded_bytes=REF_METADATA_MAX_BYTES,
        reject_sensitive_metadata=True,
    )


def _normalize_non_empty_string(field_name: str, value: object) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_worker_generation(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("worker_generation must be an integer")
    try:
        generation = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("worker_generation must be an integer") from exc
    if generation < 0:
        raise ValueError("worker_generation must be >= 0")
    return generation


class StaleHandleError(LookupError):
    """Raised when a runtime handle ref no longer matches live worker state."""


class HandleDisposalError(RuntimeError):
    """Raised when explicit final handle release cannot dispose its value."""


@dataclass(slots=True)
class _HandleRecord:
    value: Any
    data_type_id: str
    schema_version: int
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)
    dispose: Callable[[], None] | None = None
    leases: dict[str, int] = field(default_factory=dict)

    def to_ref(
        self,
        handle_id: str,
        *,
        owner_scope: str,
        worker_generation: int,
    ) -> RuntimeHandleRef:
        return RuntimeHandleRef(
            data_type_id=self.data_type_id,
            schema_version=self.schema_version,
            handle_id=handle_id,
            kind=self.kind,
            owner_scope=owner_scope,
            worker_generation=worker_generation,
            metadata=self.metadata,
        )


class HandleRegistry:
    def __init__(
        self,
        *,
        worker_generation: int = 1,
        data_types: DataTypeCatalog | None = None,
    ) -> None:
        self._worker_generation = _normalize_worker_generation(worker_generation)
        self._data_types: DataTypeCatalog | None = None
        self._records: dict[str, _HandleRecord] = {}
        self._identity_index: dict[int, str] = {}
        self._owner_index: dict[str, set[str]] = defaultdict(set)
        self._disposing_identity_ids: set[int] = set()
        self._lock = RLock()
        self._operation_in_progress = False
        if data_types is not None:
            self.bind_data_types(data_types)

    def bind_data_types(self, data_types: DataTypeCatalog) -> None:
        if not isinstance(data_types, DataTypeCatalog):
            raise TypeError("data_types must be a DataTypeCatalog")
        if not data_types.is_frozen:
            raise DataTypeCatalogError("data_types must be a frozen catalog")
        with self._lock, self._operation_locked():
            for handle_id, record in self._records.items():
                owner_scope = next(iter(record.leases))
                data_types.validate_carrier(
                    record.data_type_id,
                    record.to_ref(
                        handle_id,
                        owner_scope=owner_scope,
                        worker_generation=self._worker_generation,
                    ),
                )
            self._data_types = data_types

    @property
    def worker_generation(self) -> int:
        with self._lock:
            return self._worker_generation

    @property
    def active_handle_count(self) -> int:
        with self._lock:
            return len(self._records)

    @property
    def is_catalog_bound(self) -> bool:
        with self._lock:
            return self._data_types is not None

    @property
    def active_lease_count(self) -> int:
        with self._lock:
            return sum(
                sum(record.leases.values())
                for record in self._records.values()
            )

    @property
    def data_types(self) -> DataTypeCatalog:
        with self._lock:
            return self._require_data_types_locked()

    def register(
        self,
        value: Any,
        *,
        data_type_id: str,
        kind: str,
        owner_scope: str,
        metadata: Mapping[str, Any] | None = None,
        dispose: Callable[[], None] | None = None,
    ) -> RuntimeHandleRef:
        normalized_data_type_id = _normalize_non_empty_string(
            "data_type_id",
            data_type_id,
        )
        normalized_kind = _normalize_non_empty_string("kind", kind)
        normalized_owner_scope = _normalize_non_empty_string("owner_scope", owner_scope)
        normalized_metadata = _copy_metadata_mapping(metadata)
        if dispose is not None and not callable(dispose):
            raise TypeError("dispose must be callable")

        identity_id = id(value)
        with self._lock, self._operation_locked():
            data_types = self._require_data_types_locked()
            spec = data_types.require(normalized_data_type_id)
            if spec.abstract:
                raise DataTypeCatalogError(
                    f"runtime handle data type {normalized_data_type_id!r} must be concrete"
                )
            if "handle" not in spec.carriers:
                raise DataTypeCatalogError(
                    f"data type {normalized_data_type_id!r} does not allow 'handle' carriers"
                )
            if identity_id in self._disposing_identity_ids:
                raise RuntimeError("runtime handle value is currently being disposed")
            existing_handle_id = self._identity_index.get(identity_id)
            if existing_handle_id is not None:
                existing = self._records.get(existing_handle_id)
                if existing is not None and existing.value is value:
                    self._validate_identity_reuse(
                        existing,
                        data_type_id=normalized_data_type_id,
                        schema_version=spec.payload_schema_version,
                        kind=normalized_kind,
                        metadata=normalized_metadata,
                        dispose=dispose,
                    )
                    runtime_ref = existing.to_ref(
                        existing_handle_id,
                        owner_scope=normalized_owner_scope,
                        worker_generation=self._worker_generation,
                    )
                    data_types.validate_carrier(
                        normalized_data_type_id,
                        runtime_ref,
                    )
                    if existing.dispose is None and dispose is not None:
                        existing.dispose = dispose
                    existing.leases[normalized_owner_scope] = (
                        existing.leases.get(normalized_owner_scope, 0) + 1
                    )
                    self._owner_index[normalized_owner_scope].add(
                        existing_handle_id
                    )
                    return runtime_ref
                self._identity_index.pop(identity_id, None)
            handle_id = uuid4().hex
            record = _HandleRecord(
                value=value,
                data_type_id=normalized_data_type_id,
                schema_version=spec.payload_schema_version,
                kind=normalized_kind,
                metadata=normalized_metadata,
                dispose=dispose,
                leases={normalized_owner_scope: 1},
            )
            runtime_ref = record.to_ref(
                handle_id,
                owner_scope=normalized_owner_scope,
                worker_generation=self._worker_generation,
            )
            data_types.validate_carrier(normalized_data_type_id, runtime_ref)
            self._records[handle_id] = record
            self._identity_index[identity_id] = handle_id
            self._owner_index[normalized_owner_scope].add(handle_id)
            return runtime_ref

    def lease(self, value: object, *, owner_scope: str) -> RuntimeHandleRef:
        normalized_owner_scope = _normalize_non_empty_string(
            "owner_scope",
            owner_scope,
        )
        with self._lock, self._operation_locked():
            handle_id, _, record = self._resolve_record_locked(value)
            runtime_ref = record.to_ref(
                handle_id,
                owner_scope=normalized_owner_scope,
                worker_generation=self._worker_generation,
            )
            self._require_data_types_locked().validate_carrier(
                record.data_type_id,
                runtime_ref,
            )
            record.leases[normalized_owner_scope] = (
                record.leases.get(normalized_owner_scope, 0) + 1
            )
            self._owner_index[normalized_owner_scope].add(handle_id)
            return runtime_ref

    def resolve(
        self,
        value: object,
        *,
        expected_data_type: str | None = None,
        expected_kind: str = "",
    ) -> Any:
        with self._lock, self._operation_locked():
            _, runtime_ref, record = self._resolve_record_locked(value)
            if expected_data_type is not None:
                normalized_expected_data_type = _normalize_non_empty_string(
                    "expected_data_type",
                    expected_data_type,
                )
                data_types = self._require_data_types_locked()
                data_types.require(normalized_expected_data_type)
                if not data_types.is_assignable(
                    record.data_type_id,
                    normalized_expected_data_type,
                ):
                    raise TypeError(
                        "Runtime handle data type mismatch: "
                        f"expected {normalized_expected_data_type!r} or a subtype, "
                        f"got {record.data_type_id!r}"
                    )
            if expected_kind:
                normalized_expected_kind = _normalize_non_empty_string(
                    "expected_kind",
                    expected_kind,
                )
                if (
                    normalized_expected_kind != record.kind
                    or runtime_ref.kind != normalized_expected_kind
                ):
                    raise TypeError(
                        "Runtime handle kind mismatch: "
                        f"expected {normalized_expected_kind!r}, got {record.kind!r}"
                    )
            return record.value

    def release(self, value: object) -> bool:
        with self._lock, self._operation_locked():
            handle_id, runtime_ref, record = self._resolve_record_locked(value)
            remaining = record.leases[runtime_ref.owner_scope] - 1
            if remaining:
                record.leases[runtime_ref.owner_scope] = remaining
                return False
            self._remove_owner_lease_locked(
                handle_id,
                record,
                runtime_ref.owner_scope,
            )
            if record.leases:
                return False
            self._detach_record_locked(handle_id, record)
        self._dispose_explicitly(record)
        return True

    def lease_count(
        self,
        value: object,
        *,
        owner_scope: str | None = None,
    ) -> int:
        with self._lock, self._operation_locked():
            _, _, record = self._resolve_record_locked(value)
            if owner_scope is None:
                return sum(record.leases.values())
            normalized_owner_scope = _normalize_non_empty_string(
                "owner_scope",
                owner_scope,
            )
            return record.leases.get(normalized_owner_scope, 0)

    def release_owner_scope(
        self,
        owner_scope: str,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> int:
        normalized_owner_scope = _normalize_non_empty_string("owner_scope", owner_scope)
        disposals: list[tuple[str, _HandleRecord]] = []
        released_count = 0
        with self._lock, self._operation_locked():
            handle_ids = tuple(self._owner_index.get(normalized_owner_scope, ()))
            for handle_id in handle_ids:
                record = self._records.get(handle_id)
                if record is None:
                    continue
                released_count += record.leases.get(normalized_owner_scope, 0)
                self._remove_owner_lease_locked(
                    handle_id,
                    record,
                    normalized_owner_scope,
                )
                if not record.leases:
                    self._detach_record_locked(handle_id, record)
                    disposals.append((handle_id, record))
        for _, record in disposals:
            self._dispose_automatically(record, warn=warn)
        return released_count

    def reset(
        self,
        *,
        warn: Callable[[str], None] | None = None,
    ) -> int:
        with self._lock, self._operation_locked():
            records = tuple(self._records.items())
            self._records.clear()
            self._identity_index.clear()
            self._owner_index.clear()
            for _, record in records:
                if record.dispose is not None:
                    self._disposing_identity_ids.add(id(record.value))
            self._worker_generation += 1
        for _, record in records:
            self._dispose_automatically(record, warn=warn)
        return len(records)

    def _require_data_types_locked(self) -> DataTypeCatalog:
        if self._data_types is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for runtime values"
            )
        return self._data_types

    @contextmanager
    def _operation_locked(self) -> Iterator[None]:
        if self._operation_in_progress:
            raise RuntimeError(
                "runtime handle registry operation is already in progress"
            )
        self._operation_in_progress = True
        try:
            yield
        finally:
            self._operation_in_progress = False

    def _remove_owner_lease_locked(
        self,
        handle_id: str,
        record: _HandleRecord,
        owner_scope: str,
    ) -> None:
        record.leases.pop(owner_scope, None)
        owner_handles = self._owner_index.get(owner_scope)
        if owner_handles is None:
            return
        owner_handles.discard(handle_id)
        if not owner_handles:
            self._owner_index.pop(owner_scope, None)

    def _detach_record_locked(
        self,
        handle_id: str,
        record: _HandleRecord,
    ) -> None:
        self._records.pop(handle_id, None)
        self._identity_index.pop(id(record.value), None)
        if record.dispose is not None:
            self._disposing_identity_ids.add(id(record.value))

    def _resolve_record_locked(
        self,
        value: object,
    ) -> tuple[str, RuntimeHandleRef, _HandleRecord]:
        runtime_ref = coerce_runtime_handle_ref(
            value,
            catalog=self._require_data_types_locked(),
        )
        if runtime_ref is None:
            raise TypeError("Runtime handle operations require a RuntimeHandleRef payload.")
        if runtime_ref.worker_generation != self._worker_generation:
            raise StaleHandleError(
                "Runtime handle ref worker_generation is stale: "
                f"{runtime_ref.worker_generation} != {self._worker_generation}"
            )
        record = self._records.get(runtime_ref.handle_id)
        if record is None:
            raise StaleHandleError(f"Runtime handle ref is stale or unknown: {runtime_ref.handle_id!r}")
        if record.leases.get(runtime_ref.owner_scope, 0) <= 0:
            raise StaleHandleError(
                "Runtime handle ref owner_scope is stale: "
                f"{runtime_ref.owner_scope!r}"
            )
        if runtime_ref.kind != record.kind:
            raise StaleHandleError(
                "Runtime handle ref kind is stale: "
                f"{runtime_ref.kind!r} != {record.kind!r}"
            )
        if runtime_ref.data_type_id != record.data_type_id:
            raise StaleHandleError(
                "Runtime handle ref data_type_id is stale: "
                f"{runtime_ref.data_type_id!r} != {record.data_type_id!r}"
            )
        if runtime_ref.schema_version != record.schema_version:
            raise StaleHandleError(
                "Runtime handle ref schema_version is stale: "
                f"{runtime_ref.schema_version!r} != {record.schema_version!r}"
            )
        if runtime_ref.metadata != record.metadata:
            raise StaleHandleError("Runtime handle ref metadata is stale.")
        return runtime_ref.handle_id, runtime_ref, record

    @staticmethod
    def _disposers_match(
        current: Callable[[], None],
        candidate: Callable[[], None],
    ) -> bool:
        if current is candidate:
            return True
        current_self = getattr(current, "__self__", None)
        candidate_self = getattr(candidate, "__self__", None)
        current_func = getattr(current, "__func__", None)
        candidate_func = getattr(candidate, "__func__", None)
        return (
            current_func is not None
            and current_self is candidate_self
            and current_func is candidate_func
        )

    def _validate_identity_reuse(
        self,
        record: _HandleRecord,
        *,
        data_type_id: str,
        schema_version: int,
        kind: str,
        metadata: Mapping[str, Any],
        dispose: Callable[[], None] | None,
    ) -> None:
        if (
            record.data_type_id != data_type_id
            or record.schema_version != schema_version
            or record.kind != kind
        ):
            raise ValueError(
                "runtime handle value is already registered with a conflicting contract"
            )
        if record.metadata != metadata:
            raise ValueError(
                "runtime handle value is already registered with conflicting metadata"
            )
        if (
            record.dispose is not None
            and dispose is not None
            and not self._disposers_match(record.dispose, dispose)
        ):
            raise ValueError(
                "runtime handle value is already registered with a conflicting disposer"
            )

    def _dispose_explicitly(
        self,
        record: _HandleRecord,
    ) -> None:
        if record.dispose is None:
            return
        try:
            record.dispose()
        except Exception as exc:
            raise HandleDisposalError("Runtime handle disposal failed.") from exc
        finally:
            with self._lock:
                self._disposing_identity_ids.discard(id(record.value))

    def _dispose_automatically(
        self,
        record: _HandleRecord,
        *,
        warn: Callable[[str], None] | None,
    ) -> None:
        if record.dispose is None:
            return
        try:
            record.dispose()
        except Exception:
            self._warn(
                "Runtime handle automatic disposal failed.",
                warn=warn,
            )
        finally:
            with self._lock:
                self._disposing_identity_ids.discard(id(record.value))

    @staticmethod
    def _warn(
        message: str,
        *,
        warn: Callable[[str], None] | None,
    ) -> None:
        try:
            if warn is None:
                _LOGGER.warning(message)
            else:
                warn(message)
        except Exception:
            _LOGGER.warning("Runtime handle cleanup warning sink failed.")


__all__ = [
    "HandleDisposalError",
    "HandleRegistry",
    "StaleHandleError",
]
