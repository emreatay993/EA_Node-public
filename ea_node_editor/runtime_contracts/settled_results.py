# Purpose: Define dependency-light settled execution result contracts and limits.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_solution_records.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any, Literal, TypeAlias

from ea_node_editor.common.payload_tools import (
    INLINE_PAYLOAD_MAX_BYTES,
    JSON_MAX_DEPTH,
    REF_METADATA_MAX_BYTES,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)

SettledStatus: TypeAlias = Literal["value", "empty", "failed"]

MAX_OUTPUTS_PER_NODE = 1_024
MAX_DATA_TREE_BRANCHES_PER_OUTPUT = 100_000
MAX_DATA_TREE_ITEMS_PER_OUTPUT = 1_000_000
MAX_ROOT_ERRORS_PER_RESULT = 64
MAX_TYPED_INLINE_BYTES = INLINE_PAYLOAD_MAX_BYTES
MAX_REFERENCE_METADATA_BYTES = REF_METADATA_MAX_BYTES
MAX_JSON_DEPTH = JSON_MAX_DEPTH

_RESULT_FIELDS = frozenset({"status", "value", "errors"})
_ERROR_FIELDS = frozenset({"node_id", "error", "traceback"})
_RUNTIME_VALUE_MARKER_KEY = "__ea_runtime_value__"
_DATA_TREE_MARKER = "data_tree"


def _exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    *,
    field_name: str,
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


def _string(value: Any, *, field_name: str, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _validate_tree(tree: DataTree) -> None:
    if tree.branch_count > MAX_DATA_TREE_BRANCHES_PER_OUTPUT:
        raise ValueError(
            "settled result exceeds maximum DataTree branch count "
            f"{MAX_DATA_TREE_BRANCHES_PER_OUTPUT}"
        )
    if tree.item_count > MAX_DATA_TREE_ITEMS_PER_OUTPUT:
        raise ValueError(
            "settled result exceeds maximum DataTree item count "
            f"{MAX_DATA_TREE_ITEMS_PER_OUTPUT}"
        )


def _preflight_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"runtime value exceeds maximum JSON depth {MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("runtime value mapping keys must be strings")
        if value.get(_RUNTIME_VALUE_MARKER_KEY) == _DATA_TREE_MARKER:
            _preflight_data_tree_payload(value, depth=depth)
            return
        for item in value.values():
            _preflight_json_value(item, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _preflight_json_value(item, depth=depth + 1)
        return
    raise TypeError("runtime value must contain only transport values")


def _preflight_data_tree_payload(
    payload: Mapping[str, Any],
    *,
    depth: int,
) -> None:
    _exact_fields(
        payload,
        frozenset({_RUNTIME_VALUE_MARKER_KEY, "branches"}),
        field_name="DataTree runtime payload",
    )
    branches = payload["branches"]
    if not isinstance(branches, (list, tuple)):
        raise TypeError("DataTree runtime payload branches must be a list")
    if len(branches) > MAX_DATA_TREE_BRANCHES_PER_OUTPUT:
        raise ValueError(
            "settled result exceeds maximum DataTree branch count "
            f"{MAX_DATA_TREE_BRANCHES_PER_OUTPUT}"
        )
    item_count = 0
    for index, branch in enumerate(branches):
        if not isinstance(branch, Mapping):
            raise TypeError(f"DataTree branch {index} must be a mapping")
        _exact_fields(
            branch,
            frozenset({"path", "items"}),
            field_name=f"DataTree branch {index}",
        )
        path = branch["path"]
        items = branch["items"]
        if not isinstance(path, (list, tuple)):
            raise TypeError(f"DataTree branch {index} path must be a list")
        if not isinstance(items, (list, tuple)):
            raise TypeError(f"DataTree branch {index} items must be a list")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in path):
            raise TypeError(f"DataTree branch {index} path must contain integers")
        item_count += len(items)
        if item_count > MAX_DATA_TREE_ITEMS_PER_OUTPUT:
            raise ValueError(
                "settled result exceeds maximum DataTree item count "
                f"{MAX_DATA_TREE_ITEMS_PER_OUTPUT}"
            )
    for branch in branches:
        for item in branch["items"]:
            _preflight_json_value(item, depth=depth + 1)


@dataclass(frozen=True, slots=True)
class RootExecutionError:
    node_id: str = ""
    error: str = ""
    traceback: str = ""

    def __post_init__(self) -> None:
        _string(self.node_id, field_name="root error node_id")
        _string(self.error, field_name="root error error")
        _string(self.traceback, field_name="root error traceback")

    def to_payload(self) -> dict[str, str]:
        payload = {
            "node_id": self.node_id,
            "error": self.error,
            "traceback": self.traceback,
        }
        return self.from_payload(payload)._to_payload()

    def _to_payload(self) -> dict[str, str]:
        return {
            "node_id": self.node_id,
            "error": self.error,
            "traceback": self.traceback,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RootExecutionError:
        _exact_fields(payload, _ERROR_FIELDS, field_name="root execution error")
        return cls(
            node_id=_string(payload["node_id"], field_name="root error node_id"),
            error=_string(payload["error"], field_name="root error error"),
            traceback=_string(
                payload["traceback"], field_name="root error traceback"
            ),
        )


@dataclass(frozen=True, slots=True)
class SettledPortResult:
    status: SettledStatus | str = "empty"
    value: DataTree | None = None
    errors: tuple[RootExecutionError, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"value", "empty", "failed"}:
            raise ValueError(f"invalid settled port status: {self.status!r}")
        if not isinstance(self.errors, tuple) or any(
            not isinstance(error, RootExecutionError) for error in self.errors
        ):
            raise TypeError("settled result errors must be RootExecutionError values")
        if len(self.errors) > MAX_ROOT_ERRORS_PER_RESULT:
            raise ValueError(
                "settled result exceeds maximum root error count "
                f"{MAX_ROOT_ERRORS_PER_RESULT}"
            )
        if self.status == "value":
            if not isinstance(self.value, DataTree):
                raise ValueError("value settled port results require a DataTree")
            if self.errors:
                raise ValueError("value settled port results cannot contain errors")
            _validate_tree(self.value)
        elif self.value is not None:
            raise ValueError(f"{self.status} settled port results cannot contain a value")
        elif self.status == "empty" and self.errors:
            raise ValueError("empty settled port results cannot contain errors")
        elif self.status == "failed" and not self.errors:
            raise ValueError("failed settled port results require a root error")

    def to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> dict[str, Any]:
        payload = self._to_payload(catalog=catalog)
        return self.from_payload(payload, catalog=catalog)._to_payload(catalog=catalog)

    def _to_payload(
        self,
        *,
        catalog: DataTypeCatalog | None,
    ) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": serialize_runtime_value(self.value, catalog=catalog),
            "errors": [error._to_payload() for error in self.errors],
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        catalog: DataTypeCatalog | None = None,
    ) -> SettledPortResult:
        _exact_fields(payload, _RESULT_FIELDS, field_name="settled port result")
        _preflight_json_value(payload["value"])
        status = _string(
            payload["status"], field_name="settled port result status", allow_empty=False
        ).lower()
        value = payload["value"]
        tree = (
            None
            if value is None
            else deserialize_runtime_value(value, catalog=catalog)
        )
        raw_errors = payload["errors"]
        if not isinstance(raw_errors, (list, tuple)):
            raise TypeError("settled result errors must be a list")
        if len(raw_errors) > MAX_ROOT_ERRORS_PER_RESULT:
            raise ValueError(
                "settled result exceeds maximum root error count "
                f"{MAX_ROOT_ERRORS_PER_RESULT}"
            )
        errors = tuple(RootExecutionError.from_payload(error) for error in raw_errors)
        return cls(status=status, value=tree, errors=errors)


def normalize_root_execution_errors(value: Any) -> tuple[RootExecutionError, ...]:
    if isinstance(value, RootExecutionError):
        candidates = (value,)
    elif isinstance(value, (list, tuple)):
        candidates = tuple(value)
    else:
        raise ValueError("settled result errors must be a list")
    if len(candidates) > MAX_ROOT_ERRORS_PER_RESULT:
        raise ValueError(
            "settled result exceeds maximum root error count "
            f"{MAX_ROOT_ERRORS_PER_RESULT}"
        )
    normalized = []
    for candidate in candidates:
        if isinstance(candidate, RootExecutionError):
            normalized.append(candidate)
            continue
        if not isinstance(candidate, Mapping):
            raise ValueError("settled result errors must be RootExecutionError mappings")
        normalized.append(
            RootExecutionError(
                node_id=_string(candidate.get("node_id", ""), field_name="node_id"),
                error=_string(candidate.get("error", ""), field_name="error"),
                traceback=_string(
                    candidate.get("traceback", ""), field_name="traceback"
                ),
            )
        )
    return tuple(normalized)


def root_execution_errors_from_payload(
    value: Any,
) -> tuple[RootExecutionError, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError("settled result errors must be a list")
    if len(value) > MAX_ROOT_ERRORS_PER_RESULT:
        raise ValueError(
            "settled result exceeds maximum root error count "
            f"{MAX_ROOT_ERRORS_PER_RESULT}"
        )
    return tuple(RootExecutionError.from_payload(item) for item in value)


def normalize_settled_port_result(
    value: Any,
    *,
    catalog: DataTypeCatalog | None = None,
) -> SettledPortResult:
    if isinstance(value, SettledPortResult):
        return SettledPortResult(
            status=value.status,
            value=value.value,
            errors=tuple(value.errors),
        )
    if not isinstance(value, Mapping):
        value = deserialize_runtime_value(value, catalog=catalog)
    if not isinstance(value, Mapping):
        raise ValueError("settled port result must be a mapping")
    status = _string(
        value.get("status", "empty"),
        field_name="settled port result status",
        allow_empty=False,
    ).lower()
    tree = value.get("value")
    if tree is not None and not isinstance(tree, DataTree):
        tree = deserialize_runtime_value(tree, catalog=catalog)
    return SettledPortResult(
        status=status,
        value=tree,
        errors=normalize_root_execution_errors(value.get("errors", ())),
    )


def normalize_settled_output_mapping(
    value: Any,
    *,
    catalog: DataTypeCatalog | None = None,
    max_outputs: int = MAX_OUTPUTS_PER_NODE,
) -> dict[str, SettledPortResult]:
    if not isinstance(value, Mapping):
        value = deserialize_runtime_value(value, catalog=catalog)
    if not isinstance(value, Mapping):
        raise ValueError("settled output mapping must be a mapping")
    if len(value) > max_outputs:
        raise ValueError(f"settled output mapping exceeds maximum count {max_outputs}")
    normalized: dict[str, SettledPortResult] = {}
    for raw_key, raw_result in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("settled output mapping keys must be non-empty strings")
        key = raw_key.strip()
        if key in normalized:
            raise ValueError(f"settled output mapping contains duplicate key {key!r}")
        normalized[key] = normalize_settled_port_result(raw_result, catalog=catalog)
    return normalized


def settled_output_mapping_from_payload(
    value: Any,
    *,
    catalog: DataTypeCatalog | None = None,
    max_outputs: int = MAX_OUTPUTS_PER_NODE,
) -> dict[str, SettledPortResult]:
    if not isinstance(value, Mapping):
        raise TypeError("settled output mapping must be a mapping")
    if len(value) > max_outputs:
        raise ValueError(f"settled output mapping exceeds maximum count {max_outputs}")
    normalized: dict[str, SettledPortResult] = {}
    for raw_key, raw_result in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("settled output mapping keys must be non-empty strings")
        key = raw_key.strip()
        if key in normalized:
            raise ValueError(f"settled output mapping contains duplicate key {key!r}")
        normalized[key] = SettledPortResult.from_payload(
            raw_result,
            catalog=catalog,
        )
    return normalized


def preflight_settled_output_mapping_payload(
    value: Any,
    *,
    max_outputs: int = MAX_OUTPUTS_PER_NODE,
) -> int:
    if not isinstance(value, Mapping):
        raise TypeError("settled output mapping must be a mapping")
    if len(value) > max_outputs:
        raise ValueError(f"settled output mapping exceeds maximum count {max_outputs}")
    seen: set[str] = set()
    for raw_key, raw_result in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("settled output mapping keys must be non-empty strings")
        key = raw_key.strip()
        if key in seen:
            raise ValueError(f"settled output mapping contains duplicate key {key!r}")
        seen.add(key)
        if not isinstance(raw_result, Mapping):
            raise TypeError("settled port result must be a mapping")
        _exact_fields(raw_result, _RESULT_FIELDS, field_name="settled port result")
        _preflight_json_value(raw_result["value"])
        errors = raw_result["errors"]
        if not isinstance(errors, (list, tuple)):
            raise TypeError("settled result errors must be a list")
        if len(errors) > MAX_ROOT_ERRORS_PER_RESULT:
            raise ValueError(
                "settled result exceeds maximum root error count "
                f"{MAX_ROOT_ERRORS_PER_RESULT}"
            )
    return len(value)


def settled_outputs_to_payload(
    values: Mapping[str, SettledPortResult],
    *,
    catalog: DataTypeCatalog | None = None,
    max_outputs: int = MAX_OUTPUTS_PER_NODE,
) -> dict[str, Any]:
    normalized = normalize_settled_output_mapping(
        values,
        catalog=catalog,
        max_outputs=max_outputs,
    )
    payload = {
        key: result._to_payload(catalog=catalog)
        for key, result in normalized.items()
    }
    reparsed = normalize_settled_output_mapping(
        payload,
        catalog=catalog,
        max_outputs=max_outputs,
    )
    return {
        key: result._to_payload(catalog=catalog)
        for key, result in reparsed.items()
    }


def settled_outputs_payload_size(
    values: Mapping[str, SettledPortResult],
    *,
    catalog: DataTypeCatalog | None = None,
) -> int:
    return len(
        json.dumps(
            settled_outputs_to_payload(values, catalog=catalog),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


__all__ = [
    "MAX_DATA_TREE_BRANCHES_PER_OUTPUT",
    "MAX_DATA_TREE_ITEMS_PER_OUTPUT",
    "MAX_OUTPUTS_PER_NODE",
    "MAX_JSON_DEPTH",
    "MAX_REFERENCE_METADATA_BYTES",
    "MAX_ROOT_ERRORS_PER_RESULT",
    "MAX_TYPED_INLINE_BYTES",
    "RootExecutionError",
    "SettledPortResult",
    "SettledStatus",
    "normalize_root_execution_errors",
    "normalize_settled_output_mapping",
    "normalize_settled_port_result",
    "preflight_settled_output_mapping_payload",
    "settled_outputs_payload_size",
    "settled_outputs_to_payload",
    "settled_output_mapping_from_payload",
    "root_execution_errors_from_payload",
]
