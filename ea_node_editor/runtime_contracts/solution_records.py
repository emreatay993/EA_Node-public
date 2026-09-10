# Purpose: Define immutable, persistence-neutral solution facts and records.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_solution_records.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass
from enum import Enum
import re
import unicodedata
from typing import Any

from ea_node_editor.runtime_contracts.settled_results import MAX_OUTPUTS_PER_NODE
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.durable_values import (
    DurableRuntimeValueValidation,
    validate_durable_settled_outputs,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_ID_BYTES = 1_024
MAX_DURABLE_LOGICAL_ID_UTF8_BYTES = 4_096
MAX_DURABLE_RECORD_ID_UTF8_BYTES = 128
MAX_DURABLE_BLOBS_PER_RECORD = 1
_MAX_DESCRIPTOR_VARIANTS = 64


class SolutionFreshness(str, Enum):
    NEVER = "never"
    CURRENT = "current"
    EXPIRED = "expired"


class SolutionResidency(str, Enum):
    SESSION = "session"
    DURABLE = "durable"


class SolutionDisposition(str, Enum):
    REUSED = "reused"
    RECOMPUTED = "recomputed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


def _exact_fields(
    payload: Mapping[str, Any], expected: frozenset[str], *, field_name: str
) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected, key=str)
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unexpected:
            details.append(f"unexpected {unexpected}")
        raise ValueError(f"{field_name} fields are invalid: {', '.join(details)}")


def _text(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool = False,
    max_bytes: int = _MAX_ID_BYTES,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    if len(normalized.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds {max_bytes} bytes")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{field_name} must not contain control characters")
    return normalized


def _digest(value: Any, *, field_name: str, allow_empty: bool = False) -> str:
    normalized = _text(value, field_name=field_name, allow_empty=allow_empty)
    if normalized or not allow_empty:
        if _SHA256.fullmatch(normalized) is None:
            raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _integer(value: Any, *, field_name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if (positive and value <= 0) or (not positive and value < 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be {qualifier}")
    return value


def _enum(value: Any, enum_type: type[Enum], *, field_name: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _string_tuple(
    value: Any,
    *,
    field_name: str,
    digests: bool = False,
    unique: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list")
    normalized = tuple(
        _digest(item, field_name=f"{field_name}[{index}]")
        if digests
        else _text(item, field_name=f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if unique and len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


@dataclass(slots=True, frozen=True)
class NodeSolutionFact:
    project_id: str
    workspace_id: str
    node_id: str
    freshness: SolutionFreshness
    revision: int
    retained_record_id: str | None = None
    retained_solution_key: str | None = None
    residency: SolutionResidency | None = None
    expiration_reason_code: str = ""
    expiration_root_node_ids: tuple[str, ...] = ()
    last_disposition: SolutionDisposition | None = None

    def __post_init__(self) -> None:
        for field_name in ("project_id", "workspace_id", "node_id"):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name=field_name)
            )
        object.__setattr__(
            self,
            "freshness",
            _enum(self.freshness, SolutionFreshness, field_name="freshness"),
        )
        _integer(self.revision, field_name="revision")
        retained_record_id = (
            None
            if self.retained_record_id is None
            else _text(self.retained_record_id, field_name="retained_record_id")
        )
        retained_solution_key = (
            None
            if self.retained_solution_key is None
            else _digest(
                self.retained_solution_key, field_name="retained_solution_key"
            )
        )
        residency = (
            None
            if self.residency is None
            else _enum(self.residency, SolutionResidency, field_name="residency")
        )
        disposition = (
            None
            if self.last_disposition is None
            else _enum(
                self.last_disposition,
                SolutionDisposition,
                field_name="last_disposition",
            )
        )
        reason = _text(
            self.expiration_reason_code,
            field_name="expiration_reason_code",
            allow_empty=True,
        )
        roots = _string_tuple(
            self.expiration_root_node_ids,
            field_name="expiration_root_node_ids",
        )
        retained = (retained_record_id, retained_solution_key, residency)
        if any(item is None for item in retained) and any(
            item is not None for item in retained
        ):
            raise ValueError("retained record, solution key, and residency form one triple")
        if self.freshness is SolutionFreshness.NEVER:
            if any(item is not None for item in retained) or disposition is not None:
                raise ValueError("never solution facts cannot retain solution state")
            if reason or roots:
                raise ValueError("never solution facts cannot have expiration facts")
        elif self.freshness is SolutionFreshness.CURRENT:
            if any(item is None for item in retained):
                raise ValueError("current solution facts require the retained triple")
            if disposition not in {
                SolutionDisposition.REUSED,
                SolutionDisposition.RECOMPUTED,
            }:
                raise ValueError(
                    "current solution facts require reused or recomputed disposition"
                )
            if reason or roots:
                raise ValueError("current solution facts cannot have expiration facts")
        elif not reason or not roots:
            raise ValueError("expired solution facts require reason and root node IDs")
        object.__setattr__(self, "retained_record_id", retained_record_id)
        object.__setattr__(self, "retained_solution_key", retained_solution_key)
        object.__setattr__(self, "residency", residency)
        object.__setattr__(self, "expiration_reason_code", reason)
        object.__setattr__(self, "expiration_root_node_ids", roots)
        object.__setattr__(self, "last_disposition", disposition)

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    def _to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "node_id": self.node_id,
            "freshness": self.freshness.value,
            "revision": self.revision,
            "retained_record_id": self.retained_record_id,
            "retained_solution_key": self.retained_solution_key,
            "residency": self.residency.value if self.residency else None,
            "expiration_reason_code": self.expiration_reason_code,
            "expiration_root_node_ids": list(self.expiration_root_node_ids),
            "last_disposition": (
                self.last_disposition.value if self.last_disposition else None
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> NodeSolutionFact:
        _exact_fields(payload, _NODE_FACT_FIELDS, field_name="node solution fact")
        return cls(**dict(payload))


@dataclass(slots=True, frozen=True)
class SolutionOutputDescriptor:
    port_key: str
    status: str
    data_type_id: str
    concrete_data_type_ids: tuple[str, ...]
    data_access: str
    item_count: int
    payload_kinds: tuple[str, ...]
    payload_digest: str
    payload_schema_version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "port_key", _text(self.port_key, field_name="port_key"))
        status = _text(self.status, field_name="status")
        if status not in {"value", "empty"}:
            raise ValueError("status must be value or empty")
        data_type_id = _text(
            self.data_type_id, field_name="data_type_id", allow_empty=status == "empty"
        )
        data_access = _text(
            self.data_access, field_name="data_access", allow_empty=status == "empty"
        )
        if data_access and data_access not in {"item", "list", "tree"}:
            raise ValueError("data_access must be item, list, or tree")
        item_count = _integer(self.item_count, field_name="item_count")
        concrete_data_type_ids = _string_tuple(
            self.concrete_data_type_ids,
            field_name="concrete_data_type_ids",
        )
        payload_kinds = _string_tuple(
            self.payload_kinds,
            field_name="payload_kinds",
        )
        if concrete_data_type_ids != tuple(sorted(concrete_data_type_ids)):
            raise ValueError("concrete_data_type_ids must be sorted")
        if payload_kinds != tuple(sorted(payload_kinds)):
            raise ValueError("payload_kinds must be sorted")
        if len(concrete_data_type_ids) > _MAX_DESCRIPTOR_VARIANTS:
            raise ValueError("concrete_data_type_ids exceeds maximum count 64")
        if len(payload_kinds) > _MAX_DESCRIPTOR_VARIANTS:
            raise ValueError("payload_kinds exceeds maximum count 64")
        if any(
            payload_kind not in {"inline", "artifact_ref", "handle_ref", "blob_ref"}
            for payload_kind in payload_kinds
        ):
            raise ValueError("payload_kinds contains an invalid value")
        schema_version = _integer(
            self.payload_schema_version, field_name="payload_schema_version"
        )
        if status == "value":
            payload_digest = _digest(
                self.payload_digest, field_name="payload_digest"
            )
            if not concrete_data_type_ids or not payload_kinds:
                raise ValueError(
                    "value descriptors require concrete data types and payload kinds"
                )
            if schema_version <= 0:
                raise ValueError("value descriptors require a positive payload schema")
        else:
            payload_digest = _digest(
                self.payload_digest,
                field_name="payload_digest",
                allow_empty=True,
            )
            if (
                item_count != 0
                or concrete_data_type_ids
                or payload_kinds
                or schema_version != 0
            ):
                raise ValueError(
                    "empty descriptors require zero items, empty variants, and schema 0"
                )
            if payload_digest:
                raise ValueError("empty descriptors cannot have a payload digest")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "data_type_id", data_type_id)
        object.__setattr__(self, "concrete_data_type_ids", concrete_data_type_ids)
        object.__setattr__(self, "data_access", data_access)
        object.__setattr__(self, "item_count", item_count)
        object.__setattr__(self, "payload_kinds", payload_kinds)
        object.__setattr__(self, "payload_digest", payload_digest)
        object.__setattr__(self, "payload_schema_version", schema_version)

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    def _to_payload(self) -> dict[str, Any]:
        return {
            "port_key": self.port_key,
            "status": self.status,
            "data_type_id": self.data_type_id,
            "concrete_data_type_ids": list(self.concrete_data_type_ids),
            "data_access": self.data_access,
            "item_count": self.item_count,
            "payload_kinds": list(self.payload_kinds),
            "payload_digest": self.payload_digest,
            "payload_schema_version": self.payload_schema_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SolutionOutputDescriptor:
        _exact_fields(payload, _OUTPUT_DESCRIPTOR_FIELDS, field_name="output descriptor")
        return cls(**dict(payload))


@dataclass(slots=True, frozen=True)
class SolutionPayloadLocator:
    kind: SolutionResidency
    reference_id: str
    blob_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        kind = _enum(self.kind, SolutionResidency, field_name="kind")
        reference_id = (
            _text(self.reference_id, field_name="reference_id")
            if kind is SolutionResidency.SESSION
            else _digest(self.reference_id, field_name="reference_id")
        )
        blob_digests = _string_tuple(
            self.blob_digests,
            field_name="blob_digests",
            digests=True,
        )
        if kind is SolutionResidency.SESSION and blob_digests:
            raise ValueError("session payload locators cannot contain blob digests")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "reference_id", reference_id)
        object.__setattr__(self, "blob_digests", blob_digests)

    def to_payload(self) -> dict[str, Any]:
        return self.from_payload(self._to_payload())._to_payload()

    def _to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "reference_id": self.reference_id,
            "blob_digests": list(self.blob_digests),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SolutionPayloadLocator:
        _exact_fields(payload, _PAYLOAD_LOCATOR_FIELDS, field_name="payload locator")
        return cls(**dict(payload))


@dataclass(slots=True, frozen=True, kw_only=True)
class SolutionRecord:
    record_id: str
    project_id: str
    workspace_id: str
    node_id: str
    solution_key: str
    node_interface_revision: int
    node_interface_digest: str
    node_contract_digest: str
    dependency_solution_keys: tuple[str, ...]
    input_provenance_digest: str
    execution_policy_digest: str
    implementation_digest: str
    execution_environment_digest: str
    settlement_status: str
    result_digest: str
    reuse_eligible: bool
    output_descriptors: tuple[SolutionOutputDescriptor, ...]
    payload_locator: SolutionPayloadLocator | None
    residency: SolutionResidency
    runtime_generation: int | None
    created_at_epoch_ms: int
    schema_version: int = 1
    catalog: InitVar[DataTypeCatalog | None] = None

    def __post_init__(self, catalog: DataTypeCatalog | None) -> None:
        if _integer(self.schema_version, field_name="schema_version") != 1:
            raise ValueError("solution record schema_version must be 1")
        object.__setattr__(
            self,
            "record_id",
            _text(
                self.record_id,
                field_name="record_id",
                max_bytes=MAX_DURABLE_RECORD_ID_UTF8_BYTES,
            ),
        )
        for field_name in ("project_id", "workspace_id", "node_id"):
            object.__setattr__(
                self,
                field_name,
                _text(
                    getattr(self, field_name),
                    field_name=field_name,
                    max_bytes=MAX_DURABLE_LOGICAL_ID_UTF8_BYTES,
                ),
            )
        for field_name in (
            "solution_key",
            "node_interface_digest",
            "node_contract_digest",
            "input_provenance_digest",
            "execution_policy_digest",
            "implementation_digest",
            "execution_environment_digest",
            "result_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(getattr(self, field_name), field_name=field_name),
            )
        _integer(
            self.node_interface_revision,
            field_name="node_interface_revision",
        )
        dependencies = _string_tuple(
            self.dependency_solution_keys,
            field_name="dependency_solution_keys",
            digests=True,
        )
        settlement_status = _text(
            self.settlement_status, field_name="settlement_status"
        )
        if settlement_status not in {"completed", "empty"}:
            raise ValueError("reusable solution records must be completed or empty")
        if not isinstance(self.reuse_eligible, bool):
            raise TypeError("reuse_eligible must be a boolean")
        if not isinstance(self.output_descriptors, (list, tuple)) or any(
            not isinstance(item, SolutionOutputDescriptor)
            for item in self.output_descriptors
        ):
            raise TypeError("output_descriptors must contain SolutionOutputDescriptor")
        descriptors = tuple(self.output_descriptors)
        if len(descriptors) > MAX_OUTPUTS_PER_NODE:
            raise ValueError(
                "output_descriptors exceeds maximum count "
                f"{MAX_OUTPUTS_PER_NODE}"
            )
        port_keys = tuple(item.port_key for item in descriptors)
        if len(port_keys) != len(set(port_keys)):
            raise ValueError("output_descriptors must not contain duplicate port keys")
        if self.payload_locator is not None and not isinstance(
            self.payload_locator, SolutionPayloadLocator
        ):
            raise TypeError("payload_locator must be a SolutionPayloadLocator or None")
        residency = _enum(self.residency, SolutionResidency, field_name="residency")
        if self.payload_locator is not None and self.payload_locator.kind is not residency:
            raise ValueError("payload locator kind must match record residency")
        has_value = any(item.status == "value" for item in descriptors)
        if settlement_status == "empty" and has_value:
            raise ValueError("empty solution records cannot contain value descriptors")
        if settlement_status == "completed" and descriptors and not has_value:
            raise ValueError(
                "completed solution records with outputs require a value descriptor"
            )
        if has_value and self.payload_locator is None:
            raise ValueError("value descriptors require a payload locator")
        if residency is SolutionResidency.DURABLE:
            if not self.reuse_eligible:
                raise ValueError("durable solution records must be reuse eligible")
            if any("handle_ref" in item.payload_kinds for item in descriptors):
                raise ValueError(
                    "durable solution records cannot contain session-only carriers"
                )
            value_descriptors = tuple(
                item for item in descriptors if item.status == "value"
            )
            if value_descriptors and catalog is None:
                raise ValueError(
                    "durable solution records with outputs require a data-type catalog"
                )
            for descriptor in value_descriptors:
                declared_spec = catalog.require(descriptor.data_type_id)
                if (
                    declared_spec.persistence == "never"
                    or declared_spec.sensitivity != "normal"
                ):
                    raise ValueError(
                        "durable solution records cannot contain session-only carriers"
                    )
                for concrete_type_id in descriptor.concrete_data_type_ids:
                    concrete_spec = catalog.require(concrete_type_id)
                    if (
                        concrete_spec.persistence == "never"
                        or concrete_spec.sensitivity != "normal"
                        or not catalog.is_assignable(
                            concrete_type_id,
                            descriptor.data_type_id,
                        )
                    ):
                        raise ValueError(
                            "durable solution records cannot contain ineligible concrete types"
                        )
            if value_descriptors:
                if (
                    self.payload_locator is None
                    or self.payload_locator.blob_digests
                    != (self.payload_locator.reference_id,)
                ):
                    raise ValueError(
                        "durable value records require one matching result blob digest"
                    )
            elif self.payload_locator is not None:
                raise ValueError(
                    "durable outputless or empty records cannot have a payload locator"
                )
            if (
                self.payload_locator is not None
                and len(self.payload_locator.blob_digests)
                > MAX_DURABLE_BLOBS_PER_RECORD
            ):
                raise ValueError("durable payload locator exceeds the blob limit")
        if residency is SolutionResidency.SESSION:
            if self.runtime_generation is None:
                raise ValueError("session records require a runtime generation")
            _integer(
                self.runtime_generation,
                field_name="runtime_generation",
                positive=True,
            )
        elif self.runtime_generation is not None:
            raise ValueError("durable records cannot have a runtime generation")
        _integer(self.created_at_epoch_ms, field_name="created_at_epoch_ms")
        object.__setattr__(self, "dependency_solution_keys", dependencies)
        object.__setattr__(self, "settlement_status", settlement_status)
        object.__setattr__(self, "output_descriptors", descriptors)
        object.__setattr__(self, "residency", residency)

    def to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        return self.from_payload(
            self._to_payload(),
            catalog=catalog,
        )._to_payload()

    def validate_durable_outputs(
        self,
        outputs: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog,
        artifact_context: Any,
    ) -> DurableRuntimeValueValidation:
        if self.residency is not SolutionResidency.DURABLE:
            raise ValueError("durable output validation requires durable residency")
        return validate_durable_settled_outputs(
            outputs,
            self.output_descriptors,
            catalog,
            artifact_context,
        )

    def _to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "node_id": self.node_id,
            "solution_key": self.solution_key,
            "node_interface_revision": self.node_interface_revision,
            "node_interface_digest": self.node_interface_digest,
            "node_contract_digest": self.node_contract_digest,
            "dependency_solution_keys": list(self.dependency_solution_keys),
            "input_provenance_digest": self.input_provenance_digest,
            "execution_policy_digest": self.execution_policy_digest,
            "implementation_digest": self.implementation_digest,
            "execution_environment_digest": self.execution_environment_digest,
            "settlement_status": self.settlement_status,
            "result_digest": self.result_digest,
            "reuse_eligible": self.reuse_eligible,
            "output_descriptors": [item._to_payload() for item in self.output_descriptors],
            "payload_locator": (
                self.payload_locator._to_payload() if self.payload_locator else None
            ),
            "residency": self.residency.value,
            "runtime_generation": self.runtime_generation,
            "created_at_epoch_ms": self.created_at_epoch_ms,
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> SolutionRecord:
        _exact_fields(payload, _SOLUTION_RECORD_FIELDS, field_name="solution record")
        raw_descriptors = payload["output_descriptors"]
        if not isinstance(raw_descriptors, (list, tuple)):
            raise TypeError("output_descriptors must be a list")
        if len(raw_descriptors) > MAX_OUTPUTS_PER_NODE:
            raise ValueError(
                "output_descriptors exceeds maximum count "
                f"{MAX_OUTPUTS_PER_NODE}"
            )
        raw_locator = payload["payload_locator"]
        return cls(
            **{
                **dict(payload),
                "output_descriptors": tuple(
                    SolutionOutputDescriptor.from_payload(item)
                    for item in raw_descriptors
                ),
                "payload_locator": (
                    None
                    if raw_locator is None
                    else SolutionPayloadLocator.from_payload(raw_locator)
                ),
                "catalog": catalog,
            }
        )


_NODE_FACT_FIELDS = frozenset(NodeSolutionFact.__dataclass_fields__)
_OUTPUT_DESCRIPTOR_FIELDS = frozenset(SolutionOutputDescriptor.__dataclass_fields__)
_PAYLOAD_LOCATOR_FIELDS = frozenset(SolutionPayloadLocator.__dataclass_fields__)
_SOLUTION_RECORD_FIELDS = frozenset(SolutionRecord.__dataclass_fields__) - {
    "catalog"
}

__all__ = [
    "MAX_DURABLE_BLOBS_PER_RECORD",
    "MAX_DURABLE_LOGICAL_ID_UTF8_BYTES",
    "MAX_DURABLE_RECORD_ID_UTF8_BYTES",
    "NodeSolutionFact",
    "SolutionDisposition",
    "SolutionFreshness",
    "SolutionOutputDescriptor",
    "SolutionPayloadLocator",
    "SolutionRecord",
    "SolutionResidency",
]
