# Purpose: Validate and encode callback-free durable settled runtime values.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_typed_runtime_values.py

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.common.payload_tools import (
    INLINE_PAYLOAD_MAX_BYTES,
    JSON_MAX_DEPTH,
    validate_payload_fields,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.data_types import (
    DataTypeCatalogError,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.runtime_contracts.image_value import (
    IMAGE_VALUE_DATA_TYPE_ID,
    IMAGE_VALUE_MAX_ENCODED_BYTES,
    ImageValue,
    _RUNTIME_IMAGE_MARKER_VALUE,
)
from ea_node_editor.runtime_contracts.interval_1d import Interval1D
from ea_node_editor.runtime_contracts.tabular_data import (
    ArrayDataRef,
    ArraySlice2DRef,
    TabularDataRef,
    TabularWindowRef,
)
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
    _RUNTIME_ARTIFACT_MARKER_VALUE,
    _RUNTIME_TYPED_INLINE_MARKER_VALUE,
    _RUNTIME_VALUE_MARKER_KEY,
)
from ea_node_editor.runtime_contracts.value_codec import (
    _RUNTIME_DATA_TREE_MARKER_VALUE,
    _RUNTIME_INTERVAL_1D_MARKER_VALUE,
)

if TYPE_CHECKING:
    from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog

_PRIVATE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_DRIVE_RELATIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:(?![\\/])")
_HOME_PATH_PATTERN = re.compile(r"^~(?:[^\\/]*[\\/]|$)")
_ENVIRONMENT_PATH_PATTERN = re.compile(
    r"^(?:%[A-Za-z_][A-Za-z0-9_]*%|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)"
)
_DURABLE_PRIVATE_RELATIVE_ROOTS = frozenset(
    {
        "private",
        "session-temp",
        "session-temporary",
        "session_temp",
        "session_temporary",
        "staging",
    }
)


@dataclass(slots=True, frozen=True)
class DurableRuntimeValueValidation:
    eligible: bool
    reason_code: str
    canonical_payload: bytes | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.eligible, bool):
            raise TypeError("eligible must be a boolean")
        if not isinstance(self.reason_code, str):
            raise TypeError("reason_code must be a string")
        if self.eligible:
            if self.reason_code != "durable_value_eligible":
                raise ValueError("eligible durable values require the success reason")
            if type(self.canonical_payload) is not bytes:
                raise TypeError("eligible durable values require canonical bytes")
        elif self.canonical_payload is not None:
            raise ValueError("ineligible durable values cannot carry canonical bytes")


def _durable_type_is_eligible(catalog: DataTypeCatalog, type_id: str) -> bool:
    try:
        spec = catalog.require(type_id)
    except (KeyError, TypeError, ValueError, DataTypeCatalogError):
        return False
    return spec.persistence != "never" and spec.sensitivity == "normal"


def _durable_semantic_carrier_is_eligible(
    catalog: DataTypeCatalog,
    *,
    actual_type_id: str,
    declared_type_id: str,
    carrier: str,
    schema_version: int | None,
) -> bool:
    try:
        actual = catalog.require(actual_type_id)
        declared = catalog.require(declared_type_id)
    except (KeyError, TypeError, ValueError, DataTypeCatalogError):
        return False
    return bool(
        actual.persistence != "never"
        and actual.sensitivity == "normal"
        and declared.persistence != "never"
        and declared.sensitivity == "normal"
        and carrier in actual.carriers
        and carrier in declared.carriers
        and catalog.is_assignable(actual_type_id, declared_type_id)
        and (schema_version is None or schema_version == actual.payload_schema_version)
    )


def _durable_string_is_private_path(value: str) -> bool:
    normalized = value.strip()
    portable = normalized.replace("\\", "/")
    parts = tuple(
        part.casefold() for part in portable.split("/") if part not in {"", "."}
    )
    return bool(
        normalized.casefold().startswith(("temp://", "saved://"))
        or _PRIVATE_PATH_PATTERN.match(normalized)
        or _DRIVE_RELATIVE_PATH_PATTERN.match(normalized)
        or _HOME_PATH_PATTERN.match(normalized)
        or _ENVIRONMENT_PATH_PATTERN.match(normalized)
        or os.path.isabs(normalized)
        or ".." in parts
        or (len(parts) > 1 and parts[0] in _DURABLE_PRIVATE_RELATIVE_ROOTS)
    )


def _validate_durable_value(
    value: Any,
    *,
    catalog: DataTypeCatalog,
    artifact_context: Any,
    depth: int,
    declared_type_id: str = "",
) -> str:
    if depth > JSON_MAX_DEPTH:
        return "durable_value_ineligible"
    value_type = type(value)
    if value is None or value_type in {bool, int}:
        return ""
    if value_type is float:
        return "" if math.isfinite(value) else "durable_value_ineligible"
    if value_type is str:
        return (
            "durable_value_ineligible" if _durable_string_is_private_path(value) else ""
        )
    if value_type is RuntimeArtifactRef:
        if value.scope != "managed":
            return "durable_artifact_invalid"
        if not declared_type_id or not _durable_semantic_carrier_is_eligible(
            catalog,
            actual_type_id=value.data_type_id,
            declared_type_id=declared_type_id,
            carrier="artifact",
            schema_version=value.schema_version,
        ):
            return "durable_artifact_invalid"
        metadata_reason = _validate_durable_value(
            value.metadata,
            catalog=catalog,
            artifact_context=artifact_context,
            depth=depth + 1,
        )
        if metadata_reason:
            return metadata_reason
        inspector = getattr(artifact_context, "inspect_durable_artifact", None)
        if not callable(inspector):
            return "durable_artifact_invalid"
        try:
            inspector(value)
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            return "durable_artifact_invalid"
        return ""
    if value_type in {
        RuntimeHandleRef,
        TabularDataRef,
        ArrayDataRef,
        TabularWindowRef,
        ArraySlice2DRef,
    }:
        return "durable_value_ineligible"
    if value_type is ImageValue:
        if not declared_type_id or not _durable_semantic_carrier_is_eligible(
            catalog,
            actual_type_id=value.data_type_id,
            declared_type_id=declared_type_id,
            carrier="inline",
            schema_version=value.schema_version,
        ):
            return "durable_value_ineligible"
        try:
            encoded = json.dumps(
                _durable_inline_payload(value),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (AttributeError, TypeError, ValueError):
            return "durable_value_ineligible"
        return (
            ""
            if len(encoded) <= INLINE_PAYLOAD_MAX_BYTES
            else "durable_value_ineligible"
        )
    if value_type is TypedInlineValue:
        if not declared_type_id or not _durable_semantic_carrier_is_eligible(
            catalog,
            actual_type_id=value.data_type_id,
            declared_type_id=declared_type_id,
            carrier="inline",
            schema_version=value.schema_version,
        ):
            return "durable_value_ineligible"
        return _validate_durable_value(
            value.payload,
            catalog=catalog,
            artifact_context=artifact_context,
            depth=depth + 1,
        )
    if value_type is Interval1D:
        return (
            ""
            if declared_type_id
            and _durable_semantic_carrier_is_eligible(
                catalog,
                actual_type_id=INTERVAL_1D_GRAPH_DATA_TYPE_ID,
                declared_type_id=declared_type_id,
                carrier="inline",
                schema_version=1,
            )
            else "durable_value_ineligible"
        )
    if value_type is DataTree:
        for _path, items in value.branches:
            for item in items:
                reason = _validate_durable_value(
                    item,
                    catalog=catalog,
                    artifact_context=artifact_context,
                    depth=depth + 1,
                )
                if reason:
                    return reason
        return ""
    if value_type in {list, tuple}:
        for item in value:
            reason = _validate_durable_value(
                item,
                catalog=catalog,
                artifact_context=artifact_context,
                depth=depth + 1,
            )
            if reason:
                return reason
        return ""
    if value_type is dict:
        marker = value.get(_RUNTIME_VALUE_MARKER_KEY)
        if marker is not None:
            return "durable_value_ineligible"
        for key, item in value.items():
            if type(key) is not str or _durable_string_is_private_path(key):
                return "durable_value_ineligible"
            reason = _validate_durable_value(
                item,
                catalog=catalog,
                artifact_context=artifact_context,
                depth=depth + 1,
            )
            if reason:
                return reason
        return ""
    return "durable_value_ineligible"


def _durable_item_type_and_kind(
    value: Any,
    declared_type_id: str,
) -> tuple[str, str]:
    value_type = type(value)
    if value_type is RuntimeArtifactRef:
        return value.data_type_id, "artifact_ref"
    if value_type in {
        RuntimeHandleRef,
        TabularDataRef,
        ArrayDataRef,
        TabularWindowRef,
        ArraySlice2DRef,
    }:
        return "", "forbidden"
    if value_type in {TypedInlineValue, ImageValue}:
        return value.data_type_id, "inline"
    if value_type is Interval1D:
        return INTERVAL_1D_GRAPH_DATA_TYPE_ID, "inline"
    return declared_type_id, "inline"


def _durable_inline_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > JSON_MAX_DEPTH:
        raise ValueError("durable inline value exceeds the depth limit")
    value_type = type(value)
    if value is None or value_type in {bool, int}:
        return value
    if value_type is str:
        if _durable_string_is_private_path(value):
            raise ValueError("durable value contains a private path")
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError("durable inline value contains a non-finite number")
        return value
    if value_type is ImageValue:
        if len(value.encoded_bytes) > INLINE_PAYLOAD_MAX_BYTES:
            raise ValueError("durable image exceeds the inline limit")
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_IMAGE_MARKER_VALUE,
            "data_type_id": value.data_type_id,
            "schema_version": value.schema_version,
            "format": value.format,
            "width": value.width,
            "height": value.height,
            "sha256": value.sha256,
            "encoded_base64": base64.b64encode(value.encoded_bytes).decode("ascii"),
        }
    if value_type is RuntimeArtifactRef:
        payload = {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_ARTIFACT_MARKER_VALUE,
            "ref": value.ref,
            "artifact_id": value.artifact_id,
            "scope": value.scope,
            "data_type_id": value.data_type_id,
            "schema_version": value.schema_version,
            "format": value.format,
            "size_bytes": value.size_bytes,
            "sha256": value.sha256,
            "provenance": value.provenance,
        }
        if value.metadata:
            payload["metadata"] = _durable_inline_payload(
                value.metadata,
                depth=depth + 1,
            )
        return payload
    if value_type in {
        RuntimeHandleRef,
        TabularDataRef,
        ArrayDataRef,
        TabularWindowRef,
        ArraySlice2DRef,
    }:
        raise ValueError(
            "durable accepted outputs cannot contain session-only carriers"
        )
    if value_type is TypedInlineValue:
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_TYPED_INLINE_MARKER_VALUE,
            "data_type_id": value.data_type_id,
            "schema_version": value.schema_version,
            "payload": _durable_inline_payload(value.payload, depth=depth + 1),
        }
    if value_type is Interval1D:
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_INTERVAL_1D_MARKER_VALUE,
            "start": value.start,
            "end": value.end,
        }
    if value_type is DataTree:
        return {
            _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_DATA_TREE_MARKER_VALUE,
            "branches": [
                {
                    "path": list(path),
                    "items": [
                        _durable_inline_payload(item, depth=depth + 1) for item in items
                    ],
                }
                for path, items in value.branches
            ],
        }
    if value_type in {list, tuple}:
        return [_durable_inline_payload(item, depth=depth + 1) for item in value]
    if value_type is dict:
        if any(
            type(key) is not str or _durable_string_is_private_path(key)
            for key in value
        ):
            raise ValueError("durable mapping key contains a private path")
        return {
            key: _durable_inline_payload(item, depth=depth + 1)
            for key, item in value.items()
        }
    raise TypeError("durable inline value contains an unsupported carrier")


def _durable_runtime_value_from_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > JSON_MAX_DEPTH:
        raise ValueError("durable runtime value exceeds the depth limit")
    value_type = type(value)
    if value is None or value_type in {str, bool, int}:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError("durable runtime value contains a non-finite number")
        return value
    if value_type is list:
        return [
            _durable_runtime_value_from_payload(item, depth=depth + 1) for item in value
        ]
    if value_type is not dict:
        raise TypeError("durable runtime value contains an unsupported value")
    marker = value.get(_RUNTIME_VALUE_MARKER_KEY)
    if marker is None:
        if any(type(key) is not str for key in value):
            raise TypeError("durable runtime mapping keys must be strings")
        return {
            key: _durable_runtime_value_from_payload(item, depth=depth + 1)
            for key, item in value.items()
        }
    if marker == _RUNTIME_DATA_TREE_MARKER_VALUE:
        validate_payload_fields(
            value,
            label="durable DataTree",
            required=frozenset({_RUNTIME_VALUE_MARKER_KEY, "branches"}),
        )
        branches = value["branches"]
        if type(branches) is not list:
            raise TypeError("durable DataTree branches must be a list")
        decoded_branches = []
        for branch in branches:
            if type(branch) is not dict:
                raise TypeError("durable DataTree branch must be a mapping")
            validate_payload_fields(
                branch,
                label="durable DataTree branch",
                required=frozenset({"path", "items"}),
            )
            if type(branch["path"]) is not list or type(branch["items"]) is not list:
                raise TypeError("durable DataTree path/items must be lists")
            decoded_branches.append(
                (
                    tuple(branch["path"]),
                    tuple(
                        _durable_runtime_value_from_payload(
                            item,
                            depth=depth + 1,
                        )
                        for item in branch["items"]
                    ),
                )
            )
        return DataTree(decoded_branches)
    if marker == _RUNTIME_INTERVAL_1D_MARKER_VALUE:
        validate_payload_fields(
            value,
            label="durable Interval1D",
            required=frozenset({_RUNTIME_VALUE_MARKER_KEY, "start", "end"}),
        )
        return Interval1D(start=value["start"], end=value["end"])
    if marker == _RUNTIME_TYPED_INLINE_MARKER_VALUE:
        validate_payload_fields(
            value,
            label="durable TypedInlineValue",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "payload",
                }
            ),
        )
        return TypedInlineValue(
            data_type_id=value["data_type_id"],
            schema_version=value["schema_version"],
            payload=value["payload"],
        )
    if marker == _RUNTIME_IMAGE_MARKER_VALUE:
        validate_payload_fields(
            value,
            label="durable ImageValue",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "data_type_id",
                    "schema_version",
                    "format",
                    "width",
                    "height",
                    "sha256",
                    "encoded_base64",
                }
            ),
        )
        if value["data_type_id"] != IMAGE_VALUE_DATA_TYPE_ID:
            raise ValueError("durable ImageValue data type is invalid")
        encoded = value["encoded_base64"]
        if type(encoded) is not str or len(encoded) > IMAGE_VALUE_MAX_ENCODED_BYTES:
            raise ValueError("durable ImageValue payload is oversized")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("durable ImageValue payload is invalid") from exc
        return ImageValue(
            encoded_bytes=image_bytes,
            format=value["format"],
            width=value["width"],
            height=value["height"],
            sha256=value["sha256"],
            schema_version=value["schema_version"],
        )
    if marker == _RUNTIME_ARTIFACT_MARKER_VALUE:
        validate_payload_fields(
            value,
            label="durable RuntimeArtifactRef",
            required=frozenset(
                {
                    _RUNTIME_VALUE_MARKER_KEY,
                    "ref",
                    "artifact_id",
                    "scope",
                    "data_type_id",
                    "schema_version",
                    "format",
                    "size_bytes",
                    "sha256",
                    "provenance",
                }
            ),
            optional=frozenset({"metadata"}),
        )
        return RuntimeArtifactRef(
            ref=value["ref"],
            artifact_id=value["artifact_id"],
            scope=value["scope"],
            data_type_id=value["data_type_id"],
            schema_version=value["schema_version"],
            format=value["format"],
            size_bytes=value["size_bytes"],
            sha256=value["sha256"],
            provenance=value["provenance"],
            metadata=value.get("metadata"),
        )
    raise ValueError("durable runtime value marker is unsupported")


def durable_settled_outputs_from_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Decode durable settled outputs structurally without catalog callbacks."""

    from ea_node_editor.runtime_contracts.settled_results import (
        MAX_OUTPUTS_PER_NODE,
        SettledPortResult,
    )

    if type(payload) is not dict:
        raise TypeError("durable settled outputs must be a mapping")
    if len(payload) > MAX_OUTPUTS_PER_NODE:
        raise ValueError("durable settled outputs exceed the output limit")
    outputs: dict[str, SettledPortResult] = {}
    for port_key, result_payload in payload.items():
        if (
            type(port_key) is not str
            or not port_key
            or port_key != port_key.strip()
            or type(result_payload) is not dict
        ):
            raise ValueError("durable settled output entry is invalid")
        validate_payload_fields(
            result_payload,
            label="durable settled output",
            required=frozenset({"status", "value", "errors"}),
        )
        status = result_payload["status"]
        if status not in {"value", "empty"} or result_payload["errors"] != []:
            raise ValueError("durable settled output status/errors are invalid")
        value = (
            _durable_runtime_value_from_payload(result_payload["value"])
            if status == "value"
            else None
        )
        if status == "empty" and result_payload["value"] is not None:
            raise ValueError("empty durable settled output cannot carry a value")
        outputs[port_key] = SettledPortResult(status=status, value=value)
    normalized = durable_settled_outputs_to_payload(outputs)
    if normalized != payload:
        raise ValueError("durable settled outputs are not canonical")
    return outputs


def durable_settled_outputs_to_payload(
    outputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Encode validated durable settled outputs without catalog callbacks."""

    from ea_node_editor.runtime_contracts.settled_results import SettledPortResult

    if type(outputs) is not dict or any(
        type(port_key) is not str or not isinstance(result, SettledPortResult)
        for port_key, result in outputs.items()
    ):
        raise TypeError("durable settled outputs must contain settled results")
    return {
        port_key: {
            "status": result.status,
            "value": (
                _durable_inline_payload(result.value)
                if result.status == "value"
                else None
            ),
            "errors": [],
        }
        for port_key, result in sorted(outputs.items())
    }


def validate_durable_settled_outputs(
    outputs: Mapping[str, Any],
    descriptors: Any,
    catalog: DataTypeCatalog,
    artifact_context: Any,
) -> DurableRuntimeValueValidation:
    """Validate and canonically encode durable settled outputs without callbacks."""

    try:
        if not isinstance(outputs, Mapping) or not isinstance(
            descriptors, (list, tuple)
        ):
            raise TypeError
        descriptors_by_port = {item.port_key: item for item in descriptors}
        if len(descriptors_by_port) != len(descriptors):
            raise ValueError
        if set(outputs) != set(descriptors_by_port):
            raise ValueError
        for port_key, result in outputs.items():
            if type(port_key) is not str:
                raise TypeError
            descriptor = descriptors_by_port[port_key]
            if result.status != descriptor.status:
                raise ValueError
            if result.status == "empty":
                continue
            if result.status != "value" or not isinstance(result.value, DataTree):
                raise ValueError
            type_ids = (descriptor.data_type_id, *descriptor.concrete_data_type_ids)
            if any(
                not _durable_type_is_eligible(catalog, type_id) for type_id in type_ids
            ):
                return DurableRuntimeValueValidation(False, "durable_value_ineligible")
            if any(
                not catalog.is_assignable(type_id, descriptor.data_type_id)
                for type_id in descriptor.concrete_data_type_ids
            ):
                return DurableRuntimeValueValidation(False, "durable_value_ineligible")
            observed_types: set[str] = set()
            observed_kinds: set[str] = set()
            for _path, items in result.value.branches:
                for item in items:
                    actual_type_id, payload_kind = _durable_item_type_and_kind(
                        item,
                        descriptor.data_type_id,
                    )
                    if payload_kind == "forbidden":
                        return DurableRuntimeValueValidation(
                            False,
                            "durable_value_ineligible",
                        )
                    observed_types.add(actual_type_id)
                    observed_kinds.add(payload_kind)
                    reason = _validate_durable_value(
                        item,
                        catalog=catalog,
                        artifact_context=artifact_context,
                        depth=0,
                        declared_type_id=descriptor.data_type_id,
                    )
                    if reason:
                        return DurableRuntimeValueValidation(False, reason)
                    if payload_kind == "inline":
                        inline_payload = _durable_inline_payload(item)
                        if (
                            len(
                                json.dumps(
                                    inline_payload,
                                    allow_nan=False,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                    sort_keys=True,
                                ).encode("utf-8")
                            )
                            > INLINE_PAYLOAD_MAX_BYTES
                        ):
                            return DurableRuntimeValueValidation(
                                False,
                                "durable_value_ineligible",
                            )
            if not observed_types:
                observed_types.add(descriptor.data_type_id)
                observed_kinds.add("inline")
            if (
                tuple(sorted(observed_types)) != descriptor.concrete_data_type_ids
                or tuple(sorted(observed_kinds)) != descriptor.payload_kinds
            ):
                return DurableRuntimeValueValidation(
                    False,
                    "durable_value_ineligible",
                )
        payload = {
            port_key: {
                "status": result.status,
                "value": (
                    _durable_inline_payload(result.value)
                    if result.status == "value"
                    else None
                ),
                "errors": [],
            }
            for port_key, result in sorted(outputs.items())
        }
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(canonical) > 67_108_864:
            return DurableRuntimeValueValidation(False, "durable_value_ineligible")
        for port_key, descriptor in descriptors_by_port.items():
            if descriptor.status != "value":
                continue
            digest = hashlib.sha256(
                json.dumps(
                    {port_key: payload[port_key]},
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if digest != descriptor.payload_digest:
                return DurableRuntimeValueValidation(False, "durable_value_ineligible")
        return DurableRuntimeValueValidation(
            True,
            "durable_value_eligible",
            canonical,
        )
    except (AttributeError, KeyError, TypeError, ValueError, DataTypeCatalogError):
        return DurableRuntimeValueValidation(False, "durable_value_ineligible")


__all__ = [
    "DurableRuntimeValueValidation",
    "durable_settled_outputs_from_payload",
    "durable_settled_outputs_to_payload",
    "validate_durable_settled_outputs",
]
