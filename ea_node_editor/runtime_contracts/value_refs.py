# Purpose: Define typed inline, artifact, and handle runtime references.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_typed_runtime_values.py

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ea_node_editor.common.artifact_refs import (
    ManagedArtifactRef,
    StagedArtifactRef,
    format_managed_artifact_ref,
    format_staged_artifact_ref,
    parse_artifact_ref,
)
from ea_node_editor.common.payload_tools import (
    INLINE_PAYLOAD_MAX_BYTES,
    REF_METADATA_MAX_BYTES,
    copy_json_mapping,
    copy_json_safe,
    validate_payload_fields,
)
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalogError

if TYPE_CHECKING:
    from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog

RuntimeArtifactScope = Literal["managed", "staged"]

_RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"
_RUNTIME_ARTIFACT_MARKER_VALUE = "artifact_ref"
_RUNTIME_HANDLE_MARKER_VALUE = "handle_ref"
_RUNTIME_TYPED_INLINE_MARKER_VALUE = "typed_inline"
_RUNTIME_ARTIFACT_FORMAT_MAX_LENGTH = 64
_RUNTIME_ARTIFACT_FORMAT_PATTERN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_RUNTIME_ARTIFACT_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_RUNTIME_ARTIFACT_PROVENANCE_MAX_LENGTH = 128
_RUNTIME_ARTIFACT_PROVENANCE_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:[._:-][A-Za-z0-9]+)*"
)


def _copy_metadata_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return copy_json_mapping(
        value,
        field_name="metadata",
        max_encoded_bytes=REF_METADATA_MAX_BYTES,
        reject_sensitive_metadata=True,
    )


def _normalize_required_runtime_string(field_name: str, value: object) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_data_type_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("data_type_id must be a string")
    return _normalize_required_runtime_string("data_type_id", value)


def _normalize_schema_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("schema_version must be an integer")
    if value < 1:
        raise ValueError("schema_version must be >= 1")
    return value


def _validate_artifact_format(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("format must be a string")
    if (
        not value
        or value != value.strip()
        or len(value) > _RUNTIME_ARTIFACT_FORMAT_MAX_LENGTH
        or _RUNTIME_ARTIFACT_FORMAT_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "format must be a nonblank, already-trimmed lowercase token of at "
            "most 64 characters; '.', '_', and '-' are allowed only between "
            "alphanumeric segments"
        )
    return value


def _validate_artifact_size_bytes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("size_bytes must be an integer")
    if value < 0:
        raise ValueError("size_bytes must be >= 0")
    return value


def _validate_artifact_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or _RUNTIME_ARTIFACT_SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("sha256 must be a lowercase 64-character hex digest")
    return value


def _validate_artifact_provenance(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("provenance must be a string")
    if (
        not value
        or value != value.strip()
        or len(value) > _RUNTIME_ARTIFACT_PROVENANCE_MAX_LENGTH
        or _RUNTIME_ARTIFACT_PROVENANCE_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "provenance must be a nonblank, already-trimmed identifier of at "
            "most 128 characters"
        )
    return value


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


@dataclass(slots=True, frozen=True)
class TypedInlineValue:
    data_type_id: str
    schema_version: int
    payload: Any

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_type_id",
            _normalize_data_type_id(self.data_type_id),
        )
        object.__setattr__(
            self,
            "schema_version",
            _normalize_schema_version(self.schema_version),
        )
        object.__setattr__(
            self,
            "payload",
            copy_json_safe(
                self.payload,
                field_name="inline payload",
                max_encoded_bytes=INLINE_PAYLOAD_MAX_BYTES,
            ),
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> TypedInlineValue | None:
        if (
            str(payload.get(_RUNTIME_VALUE_MARKER_KEY, "")).strip()
            != _RUNTIME_TYPED_INLINE_MARKER_VALUE
        ):
            return None
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for typed inline values"
            )
        validate_payload_fields(
            payload,
            label="Typed inline payload",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "payload",
                }
            ),
        )
        value = cls(
            data_type_id=payload["data_type_id"],
            schema_version=payload["schema_version"],
            payload=payload["payload"],
        )
        catalog.validate_carrier(value.data_type_id, value)
        return value

    def to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for typed inline values"
            )
        catalog.validate_carrier(self.data_type_id, self)
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_TYPED_INLINE_MARKER_VALUE,
            "data_type_id": self.data_type_id,
            "schema_version": self.schema_version,
            "payload": copy_json_safe(
                self.payload,
                field_name="inline payload",
                max_encoded_bytes=INLINE_PAYLOAD_MAX_BYTES,
            ),
        }


@dataclass(slots=True, frozen=True)
class RuntimeArtifactRef:
    ref: str
    artifact_id: str
    scope: RuntimeArtifactScope
    data_type_id: str
    schema_version: int
    format: str
    size_bytes: int
    sha256: str
    provenance: str
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        parsed = parse_artifact_ref(self.ref)
        if self.scope == "managed":
            if not isinstance(parsed, ManagedArtifactRef):
                raise ValueError("Runtime artifact ref does not use the saved scheme")
            normalized_ref = parsed.as_string()
        elif self.scope == "staged":
            if not isinstance(parsed, StagedArtifactRef):
                raise ValueError("Runtime artifact ref does not use the temp scheme")
            normalized_ref = parsed.as_string()
        else:
            raise ValueError("Unsupported runtime artifact scope")

        if self.artifact_id != parsed.artifact_id:
            raise ValueError(
                "Runtime artifact ref artifact_id does not match the ref payload"
            )

        object.__setattr__(self, "ref", normalized_ref)
        object.__setattr__(
            self,
            "data_type_id",
            _normalize_data_type_id(self.data_type_id),
        )
        object.__setattr__(
            self,
            "schema_version",
            _normalize_schema_version(self.schema_version),
        )
        object.__setattr__(self, "format", _validate_artifact_format(self.format))
        object.__setattr__(
            self,
            "size_bytes",
            _validate_artifact_size_bytes(self.size_bytes),
        )
        object.__setattr__(self, "sha256", _validate_artifact_sha256(self.sha256))
        object.__setattr__(
            self,
            "provenance",
            _validate_artifact_provenance(self.provenance),
        )
        object.__setattr__(self, "metadata", _copy_metadata_mapping(self.metadata))

    @classmethod
    def managed(
        cls,
        artifact_id: str,
        *,
        data_type_id: str,
        schema_version: int,
        format: str,
        size_bytes: int,
        sha256: str,
        provenance: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeArtifactRef:
        try:
            ref = format_managed_artifact_ref(artifact_id)
        except ValueError:
            raise ValueError(
                "artifact_id must be a valid artifact identifier"
            ) from None
        return cls(
            ref=ref,
            artifact_id=str(artifact_id).strip(),
            scope="managed",
            data_type_id=data_type_id,
            schema_version=schema_version,
            format=format,
            size_bytes=size_bytes,
            sha256=sha256,
            provenance=provenance,
            metadata=_copy_metadata_mapping(metadata),
        )

    @classmethod
    def staged(
        cls,
        artifact_id: str,
        *,
        data_type_id: str,
        schema_version: int,
        format: str,
        size_bytes: int,
        sha256: str,
        provenance: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeArtifactRef:
        try:
            ref = format_staged_artifact_ref(artifact_id)
        except ValueError:
            raise ValueError(
                "artifact_id must be a valid artifact identifier"
            ) from None
        return cls(
            ref=ref,
            artifact_id=str(artifact_id).strip(),
            scope="staged",
            data_type_id=data_type_id,
            schema_version=schema_version,
            format=format,
            size_bytes=size_bytes,
            sha256=sha256,
            provenance=provenance,
            metadata=_copy_metadata_mapping(metadata),
        )

    @classmethod
    def from_artifact_ref(
        cls,
        value: object,
        *,
        data_type_id: str,
        schema_version: int,
        format: str,
        size_bytes: int,
        sha256: str,
        provenance: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeArtifactRef:
        parsed = parse_artifact_ref(value)
        if isinstance(parsed, ManagedArtifactRef):
            return cls.managed(
                parsed.artifact_id,
                data_type_id=data_type_id,
                schema_version=schema_version,
                format=format,
                size_bytes=size_bytes,
                sha256=sha256,
                provenance=provenance,
                metadata=metadata,
            )
        if isinstance(parsed, StagedArtifactRef):
            return cls.staged(
                parsed.artifact_id,
                data_type_id=data_type_id,
                schema_version=schema_version,
                format=format,
                size_bytes=size_bytes,
                sha256=sha256,
                provenance=provenance,
                metadata=metadata,
            )
        raise ValueError("Unsupported runtime artifact ref value")

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> RuntimeArtifactRef | None:
        if (
            str(payload.get(_RUNTIME_VALUE_MARKER_KEY, "")).strip()
            != _RUNTIME_ARTIFACT_MARKER_VALUE
        ):
            return None
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for runtime artifact refs"
            )
        validate_payload_fields(
            payload,
            label="Runtime artifact ref payload",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "ref",
                    "artifact_id",
                    "scope",
                    "format",
                    "size_bytes",
                    "sha256",
                    "provenance",
                }
            ),
            optional=frozenset({"metadata"}),
        )
        metadata = payload.get("metadata")
        ref_value = str(payload["ref"]).strip()
        if not ref_value:
            raise ValueError("Runtime artifact ref payload is missing ref")
        payload_scope = str(payload["scope"]).strip()
        if not payload_scope:
            raise ValueError("Runtime artifact ref payload scope must be non-empty")
        payload_artifact_id = str(payload["artifact_id"]).strip()
        if not payload_artifact_id:
            raise ValueError(
                "Runtime artifact ref payload artifact_id must be non-empty"
            )
        runtime_ref = cls.from_artifact_ref(
            ref_value,
            data_type_id=payload["data_type_id"],
            schema_version=payload["schema_version"],
            format=payload["format"],
            size_bytes=payload["size_bytes"],
            sha256=payload["sha256"],
            provenance=payload["provenance"],
            metadata=metadata,
        )
        if payload_scope != runtime_ref.scope:
            raise ValueError(
                "Runtime artifact ref payload scope does not match the ref value"
            )
        if payload_artifact_id != runtime_ref.artifact_id:
            raise ValueError(
                "Runtime artifact ref payload artifact_id does not match the ref value"
            )
        catalog.validate_carrier(runtime_ref.data_type_id, runtime_ref)
        return runtime_ref

    def to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for runtime artifact refs"
            )
        catalog.validate_carrier(self.data_type_id, self)
        payload: dict[str, Any] = {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_ARTIFACT_MARKER_VALUE,
            "ref": self.ref,
            "artifact_id": self.artifact_id,
            "scope": self.scope,
            "data_type_id": self.data_type_id,
            "schema_version": self.schema_version,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "provenance": self.provenance,
        }
        if self.metadata:
            payload["metadata"] = _copy_metadata_mapping(self.metadata)
        return payload

    def __str__(self) -> str:
        return self.ref

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "data_type_id": self.data_type_id,
            "schema_version": self.schema_version,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "provenance": self.provenance,
        }


@dataclass(slots=True, frozen=True)
class RuntimeHandleRef:
    data_type_id: str
    schema_version: int
    handle_id: str
    kind: str
    owner_scope: str
    worker_generation: int
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_type_id",
            _normalize_data_type_id(self.data_type_id),
        )
        object.__setattr__(
            self,
            "schema_version",
            _normalize_schema_version(self.schema_version),
        )
        object.__setattr__(
            self,
            "handle_id",
            _normalize_required_runtime_string("handle_id", self.handle_id),
        )
        object.__setattr__(
            self, "kind", _normalize_required_runtime_string("kind", self.kind)
        )
        object.__setattr__(
            self,
            "owner_scope",
            _normalize_required_runtime_string("owner_scope", self.owner_scope),
        )
        object.__setattr__(
            self,
            "worker_generation",
            _normalize_worker_generation(self.worker_generation),
        )
        object.__setattr__(self, "metadata", _copy_metadata_mapping(self.metadata))

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> RuntimeHandleRef | None:
        if (
            str(payload.get(_RUNTIME_VALUE_MARKER_KEY, "")).strip()
            != _RUNTIME_HANDLE_MARKER_VALUE
        ):
            return None
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for runtime handle refs"
            )
        validate_payload_fields(
            payload,
            label="Runtime handle ref payload",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "handle_id",
                    "kind",
                    "owner_scope",
                    "worker_generation",
                }
            ),
            optional=frozenset({"metadata"}),
        )
        value = cls(
            data_type_id=payload["data_type_id"],
            schema_version=payload["schema_version"],
            handle_id=payload.get("handle_id", ""),
            kind=payload.get("kind", ""),
            owner_scope=payload.get("owner_scope", ""),
            worker_generation=payload.get("worker_generation", 0),
            metadata=payload.get("metadata"),
        )
        catalog.validate_carrier(value.data_type_id, value)
        return value

    def to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        if catalog is None:
            raise DataTypeCatalogError(
                "an active data-type catalog is required for runtime handle refs"
            )
        catalog.validate_carrier(self.data_type_id, self)
        payload: dict[str, Any] = {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_HANDLE_MARKER_VALUE,
            "data_type_id": self.data_type_id,
            "schema_version": self.schema_version,
            "handle_id": self.handle_id,
            "kind": self.kind,
            "owner_scope": self.owner_scope,
            "worker_generation": self.worker_generation,
        }
        if self.metadata:
            payload["metadata"] = _copy_metadata_mapping(self.metadata)
        return payload


def coerce_runtime_artifact_ref(
    value: object,
    *,
    catalog: DataTypeCatalog | None = None,
) -> RuntimeArtifactRef | None:
    if isinstance(value, RuntimeArtifactRef):
        return value
    if isinstance(value, Mapping):
        return RuntimeArtifactRef.from_payload(value, catalog=catalog)
    return None


def coerce_runtime_handle_ref(
    value: object,
    *,
    catalog: DataTypeCatalog | None = None,
) -> RuntimeHandleRef | None:
    if isinstance(value, RuntimeHandleRef):
        return value
    if isinstance(value, Mapping):
        return RuntimeHandleRef.from_payload(value, catalog=catalog)
    return None


__all__ = [
    "RuntimeArtifactRef",
    "RuntimeArtifactScope",
    "RuntimeHandleRef",
    "TypedInlineValue",
    "coerce_runtime_artifact_ref",
    "coerce_runtime_handle_ref",
]
