# Purpose: Define bounded data-only Mechanical semantic values and metadata tables.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_contracts.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_workbench_save.py

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from ea_node_editor.common.payload_tools import (
    INLINE_PAYLOAD_MAX_BYTES,
    validate_payload_fields,
)
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import (
    DataTypeFamilySpec,
    DataTypeSpec,
    RuntimeHandleRef,
    TableValue,
    TypedInlineValue,
)
from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value

MODEL_TYPE_ID = "COREX.Mechanical.Model"
OBJECT_TYPE_ID = "COREX.Mechanical.Object"
PROPERTY_TYPE_ID = "COREX.Mechanical.Property"
CAMERA_VIEW_TYPE_ID = "COREX.Mechanical.CameraView"
MODEL_HANDLE_KIND = "mechanical.model"
SCHEMA_VERSION = 1
CATALOGUE_MAX_ROWS = 100_000
CATALOGUE_MAX_ENCODED_BYTES = 64 * 1024 * 1024

CATALOGUE_COLUMNS = (
    "schema_version",
    "model_revision",
    "producer_iteration",
    "record_kind",
    "catalogue_id",
    "producer_node_id",
    "producer_port",
    "producer_path",
    "run_id",
    "session_id",
    "document_id",
    "source_key",
    "system_key",
    "system_label",
    "selector_code",
    "object_id",
    "parent_id",
    "analysis_id",
    "object_path",
    "display_name",
    "api_type",
    "property_key",
    "property_caption",
    "display_value",
    "definition_kind",
    "scalar_value",
    "has_tabular_data",
    "unit",
    "quantity_name",
    "formula",
    "table_key",
    "table_family",
    "row_count",
    "column_count",
    "view_index",
    "omitted_rows",
    "view_key",
    "view_name",
    "status",
    "message",
    "catalogue_complete",
    "relation_kind",
    "relation_role",
    "related_label",
    "raw_source_id",
    "scope_kind",
    "relation_status",
    "activation_state",
    "related_object_id",
    "scope_count",
    "body_hidden",
)
DEFINITIONS_COLUMNS = (
    "table_index",
    "column_index",
    "column_key",
    "column_label",
    "unit",
    "quantity_name",
    "definition_kind",
    "formula",
    "object_path",
    "property_key",
    "result_set",
    "location",
    "coordinate_system",
    "notes",
)
SEARCH_DETAILS_COLUMNS = (
    "object_id",
    "object_path",
    "display_name",
    "api_type",
    "property_key",
    "property_caption",
    "display_value",
    "unit",
    "definition_kind",
    "has_tabular_data",
    "relation_kind",
    "relation_role",
    "related_label",
    "raw_source_id",
    "scope_kind",
    "scope_count",
    "body_hidden",
    "availability",
    "diagnostic",
)

_CATALOGUE_KINDS = frozenset(
    {
        "session",
        "system",
        "object",
        "property",
        "table",
        "view",
        "operation",
        "relation",
    }
)
_RELATION_KINDS = frozenset(
    {"coordinate_system", "source_model", "body_visibility", "environment", "scope"}
)
_RELATION_STATUSES = frozenset({"available", "not_applicable", "unavailable"})
_MODEL_FIELDS = frozenset(
    {
        "workspace_id",
        "run_id",
        "session_id",
        "document_id",
        "source_key",
        "system_key",
        "model_revision",
        "connection_generation",
        "release_code",
        "backend_mode",
        "catalogue_id",
        "producer_node_id",
        "producer_port",
        "producer_path",
        "producer_iteration",
    }
)
_OBJECT_FIELDS = frozenset(
    {
        "run_id",
        "session_id",
        "document_id",
        "source_key",
        "system_key",
        "model_revision",
        "object_id",
        "parent_id",
        "object_path",
        "display_name",
        "api_type",
        "category",
        "analysis_id",
        "selector_code",
    }
)
_TABLE_DESCRIPTOR_FIELDS = frozenset(
    {"table_key", "table_family", "definition_kind", "row_count", "column_count"}
)
_PROPERTY_FIELDS = frozenset(
    {
        "run_id",
        "session_id",
        "document_id",
        "source_key",
        "system_key",
        "model_revision",
        "object_id",
        "object_path",
        "property_key",
        "caption",
        "definition_kind",
        "display_value",
        "value_status",
        "scalar_value",
        "unit",
        "quantity_name",
        "formula",
        "has_tabular_data",
        "tables",
        "selector_code",
    }
)
_CAMERA_FIELDS = frozenset(
    {
        "run_id",
        "session_id",
        "document_id",
        "source_key",
        "system_key",
        "model_revision",
        "kind",
        "name",
        "index",
        "focal_point",
        "up_vector",
        "view_vector",
        "scene_width",
        "scene_height",
        "length_unit",
        "availability_notes",
        "selector_code",
    }
)
_CAMERA_VALUE_FIELDS = frozenset(
    {
        "focal_point",
        "up_vector",
        "view_vector",
        "scene_width",
        "scene_height",
        "length_unit",
    }
)
_CATALOGUE_FIELD_KINDS = {
    "selector_code": frozenset({"system", "object", "property", "table", "view"}),
    "system_label": frozenset({"system"}),
    "object_id": frozenset({"object", "property", "table", "relation"}),
    "parent_id": frozenset({"object"}),
    "analysis_id": frozenset({"object", "property", "table", "relation"}),
    "object_path": frozenset({"object", "property", "table", "relation"}),
    "display_name": frozenset({"object", "property", "table", "relation"}),
    "api_type": frozenset({"object", "property", "table", "relation"}),
    "property_key": frozenset({"property", "table", "relation"}),
    "property_caption": frozenset({"property", "table"}),
    "display_value": frozenset({"property"}),
    "definition_kind": frozenset({"property", "table"}),
    "scalar_value": frozenset({"property"}),
    "has_tabular_data": frozenset({"property"}),
    "unit": frozenset({"property", "table"}),
    "quantity_name": frozenset({"property", "table"}),
    "formula": frozenset({"property", "table"}),
    "table_key": frozenset({"property", "table"}),
    "table_family": frozenset({"property", "table"}),
    "row_count": frozenset({"property", "table"}),
    "column_count": frozenset({"property", "table"}),
    "view_index": frozenset({"view"}),
    "omitted_rows": frozenset({"session"}),
    "view_key": frozenset({"view"}),
    "view_name": frozenset({"view"}),
    "status": frozenset({"session", "operation"}),
    "message": frozenset({"session", "operation"}),
    "catalogue_complete": frozenset({"session"}),
    "relation_kind": frozenset({"relation"}),
    "relation_role": frozenset({"relation"}),
    "related_label": frozenset({"relation"}),
    "raw_source_id": frozenset({"relation"}),
    "scope_kind": frozenset({"relation"}),
    "relation_status": frozenset({"relation"}),
    "activation_state": frozenset({"relation"}),
    "related_object_id": frozenset({"relation"}),
    "scope_count": frozenset({"relation"}),
    "body_hidden": frozenset({"relation"}),
}


def _mapping(value: object, label: str, fields: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    validate_payload_fields(value, label=label, required=fields)
    return value


def _text(value: object, field: str, *, empty: bool = False) -> str:
    if type(value) is not str or (not empty and not value):
        raise TypeError(f"{field} must be {'text' if empty else 'non-empty text'}")
    return value


def _integer(value: object, field: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    return value


def _nonnegative(value: object, field: str, *, nullable: bool = False) -> int | None:
    result = _integer(value, field, nullable=nullable)
    if result is not None and result < 0:
        raise ValueError(f"{field} must be non-negative")
    if result is not None and result > 2**63 - 1:
        raise ValueError(f"{field} exceeds signed 64-bit range")
    return result


def _uuid(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise ValueError(f"{field} must be a canonical UUID")
    return text


def _path(value: object, field: str) -> tuple[int, ...]:
    if type(value) not in {list, tuple} or any(
        type(item) is not int or not 0 <= item <= 2**63 - 1 for item in value
    ):
        raise TypeError(f"{field} must be a non-negative integer path")
    return tuple(value)


def _identity(payload: Mapping[str, Any]) -> None:
    for field in ("run_id", "session_id", "document_id", "source_key", "system_key"):
        _text(payload[field], field)
    _nonnegative(payload["model_revision"], "model_revision")


def encode_selector(
    kind: str,
    *,
    document_id: str,
    system_key: str,
    object_path: str,
    native_id: str | int,
) -> str:
    """Encode a stable identity without collapsing integer and string IDs."""
    _text(kind, "kind")
    _text(document_id, "document_id")
    _text(system_key, "system_key")
    path = _text(object_path, "object_path", empty=True)
    if type(native_id) not in {str, int} or type(native_id) is str and not native_id:
        raise TypeError("native_id must be a non-empty string or an integer")
    if type(native_id) is int:
        _nonnegative(native_id, "native_id")
    encoded = json.dumps(
        {
            "schema_version": 1,
            "kind": kind,
            "document_id": document_id,
            "system_key": system_key,
            "object_path": path,
            "native_id": native_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > INLINE_PAYLOAD_MAX_BYTES:
        raise ValueError("selector exceeds the inline payload limit")
    return encoded


def decode_selector(value: object) -> dict[str, Any]:
    if type(value) is not str:
        raise TypeError("selector must be text")
    if len(value.encode("utf-8")) > INLINE_PAYLOAD_MAX_BYTES:
        raise ValueError("selector exceeds the inline payload limit")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("selector must be valid JSON") from exc
    payload = dict(
        _mapping(
            payload,
            "selector",
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "document_id",
                    "system_key",
                    "object_path",
                    "native_id",
                }
            ),
        )
    )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("unsupported selector schema version")
    _text(payload["kind"], "kind")
    _text(payload["document_id"], "document_id")
    _text(payload["system_key"], "system_key")
    _text(payload["object_path"], "object_path", empty=True)
    if (
        type(payload["native_id"]) not in {str, int}
        or type(payload["native_id"]) is str
        and not payload["native_id"]
    ):
        raise TypeError("native_id must be a non-empty string or an integer")
    if type(payload["native_id"]) is int:
        _nonnegative(payload["native_id"], "native_id")
    return payload


def _selector_matches(
    payload: Mapping[str, Any],
    *,
    kind: str,
    native_id: object,
    object_path: str | None = None,
) -> None:
    selector = decode_selector(payload["selector_code"])
    if (
        selector["kind"] != kind
        or selector["document_id"] != payload["document_id"]
        or selector["system_key"] != payload["system_key"]
        or selector["object_path"]
        != (object_path if object_path is not None else payload["object_path"])
        or type(selector["native_id"]) is not type(native_id)
        or selector["native_id"] != native_id
    ):
        raise ValueError("selector identity does not match its snapshot")


def validate_model(value: object) -> bool:
    if (
        type(value) is not RuntimeHandleRef
        or value.data_type_id != MODEL_TYPE_ID
        or value.schema_version != 1
        or value.kind != MODEL_HANDLE_KIND
    ):
        return False
    payload = _mapping(value.metadata, "Mechanical Model metadata", _MODEL_FIELDS)
    _identity(payload)
    _text(payload["workspace_id"], "workspace_id")
    _nonnegative(payload["connection_generation"], "connection_generation")
    _nonnegative(payload["release_code"], "release_code")
    if payload["release_code"] < 261:
        raise ValueError("release_code must be at least 261")
    if payload["backend_mode"] not in {"background", "interactive"}:
        raise ValueError("backend_mode is invalid")
    _uuid(payload["catalogue_id"], "catalogue_id")
    _text(payload["producer_node_id"], "producer_node_id")
    if payload["producer_port"] not in {"info", "report"}:
        raise ValueError("producer_port is invalid")
    _path(payload["producer_path"], "producer_path")
    _nonnegative(payload["producer_iteration"], "producer_iteration")
    return True


def model_handle(
    *,
    handle_id: str,
    owner_scope: str,
    worker_generation: int,
    metadata: Mapping[str, Any],
) -> RuntimeHandleRef:
    value = RuntimeHandleRef(
        data_type_id=MODEL_TYPE_ID,
        schema_version=1,
        handle_id=handle_id,
        kind=MODEL_HANDLE_KIND,
        owner_scope=owner_scope,
        worker_generation=worker_generation,
        metadata=metadata,
    )
    validate_model(value)
    return value


def validate_object(value: object) -> bool:
    if type(value) is TypedInlineValue:
        if value.data_type_id != OBJECT_TYPE_ID or value.schema_version != 1:
            return False
        value = value.payload
    payload = _mapping(value, "Mechanical Object", _OBJECT_FIELDS)
    _identity(payload)
    _nonnegative(payload["object_id"], "object_id")
    _nonnegative(payload["parent_id"], "parent_id", nullable=True)
    _nonnegative(payload["analysis_id"], "analysis_id", nullable=True)
    _text(payload["object_path"], "object_path")
    for field in ("display_name", "api_type", "category"):
        _text(payload[field], field, empty=True)
    _selector_matches(payload, kind="object", native_id=payload["object_id"])
    return True


def validate_property(value: object) -> bool:
    if type(value) is TypedInlineValue:
        if value.data_type_id != PROPERTY_TYPE_ID or value.schema_version != 1:
            return False
        value = value.payload
    payload = _mapping(value, "Mechanical Property", _PROPERTY_FIELDS)
    _identity(payload)
    _nonnegative(payload["object_id"], "object_id")
    _text(payload["object_path"], "object_path")
    for field in ("property_key", "caption", "definition_kind"):
        _text(payload[field], field)
    for field in ("display_value", "unit", "quantity_name", "formula"):
        _text(payload[field], field, empty=True)
    if payload["value_status"] not in {
        "available",
        "free",
        "unreadable",
        "unsupported",
        "unknown",
    }:
        raise ValueError("value_status is invalid")
    scalar = payload["scalar_value"]
    if scalar is not None and (
        type(scalar) not in {int, float} or not math.isfinite(scalar)
    ):
        raise TypeError("scalar_value must be a finite number or null")
    if type(payload["has_tabular_data"]) is not bool:
        raise TypeError("has_tabular_data must be Boolean")
    if type(payload["tables"]) is not list:
        raise TypeError("tables must be a list")
    if payload["value_status"] != "available" and scalar is not None:
        raise ValueError(
            "unavailable and free property values require null scalar_value"
        )
    if bool(payload["tables"]) != payload["has_tabular_data"]:
        raise ValueError("has_tabular_data must match available table descriptors")
    for descriptor in payload["tables"]:
        descriptor = _mapping(descriptor, "table descriptor", _TABLE_DESCRIPTOR_FIELDS)
        for field in ("table_key", "table_family", "definition_kind"):
            _text(descriptor[field], field, empty=True)
        _nonnegative(descriptor["row_count"], "row_count", nullable=True)
        _nonnegative(descriptor["column_count"], "column_count", nullable=True)
    _selector_matches(payload, kind="property", native_id=payload["property_key"])
    return True


def validate_camera_view(value: object) -> bool:
    if type(value) is TypedInlineValue:
        if value.data_type_id != CAMERA_VIEW_TYPE_ID or value.schema_version != 1:
            return False
        value = value.payload
    payload = _mapping(value, "Mechanical CameraView", _CAMERA_FIELDS)
    _identity(payload)
    if payload["kind"] not in {"current", "saved"}:
        raise ValueError("camera kind is invalid")
    _text(payload["name"], "name", empty=payload["kind"] == "current")
    _nonnegative(payload["index"], "index", nullable=payload["kind"] == "current")
    if payload["kind"] == "saved" and payload["index"] is None:
        raise ValueError("saved camera requires an index")
    if payload["kind"] == "current" and payload["index"] is not None:
        raise ValueError("current camera must not have a saved-view index")
    notes = payload["availability_notes"]
    if type(notes) is not dict or not set(notes).issubset(_CAMERA_VALUE_FIELDS):
        raise ValueError("availability_notes must name only camera value fields")
    for field, note in notes.items():
        _text(note, f"availability_notes.{field}")
    for field in ("focal_point", "up_vector", "view_vector"):
        vector = payload[field]
        if vector is None:
            if field not in notes:
                raise ValueError(f"unavailable {field} requires an availability note")
            continue
        if (
            type(vector) is not list
            or len(vector) != 3
            or any(
                type(item) not in {int, float} or not math.isfinite(item)
                for item in vector
            )
        ):
            raise ValueError(f"{field} must contain three finite numbers")
        if field != "focal_point" and not any(vector):
            raise ValueError(f"{field} must be non-zero")
    for field in ("scene_width", "scene_height"):
        number = payload[field]
        if number is None:
            if field not in notes:
                raise ValueError(f"unavailable {field} requires an availability note")
            continue
        if type(number) not in {int, float} or not math.isfinite(number) or number < 0:
            raise ValueError(f"{field} must be a finite non-negative number")
    if payload["length_unit"] is None:
        if "length_unit" not in notes:
            raise ValueError("unavailable length_unit requires an availability note")
    else:
        _text(payload["length_unit"], "length_unit")
    if any(payload[field] is not None for field in notes):
        raise ValueError("availability notes are only valid for null camera fields")
    _selector_matches(
        payload,
        kind="camera_view",
        native_id=payload["index"] if payload["kind"] == "saved" else "current",
        object_path="",
    )
    return True


def _inline(type_id: str, payload: Mapping[str, Any], validator) -> TypedInlineValue:
    value = TypedInlineValue(type_id, 1, payload)
    validator(value)
    return value


def object_value(payload: Mapping[str, Any]) -> TypedInlineValue:
    return _inline(OBJECT_TYPE_ID, payload, validate_object)


def property_value(payload: Mapping[str, Any]) -> TypedInlineValue:
    return _inline(PROPERTY_TYPE_ID, payload, validate_property)


def camera_view_value(payload: Mapping[str, Any]) -> TypedInlineValue:
    return _inline(CAMERA_VIEW_TYPE_ID, payload, validate_camera_view)


def _table(
    rows: Sequence[Mapping[str, Any]], columns: tuple[str, ...], *, catalogue: bool
) -> TableValue:
    if type(rows) not in {list, tuple} or any(
        not isinstance(row, Mapping) for row in rows
    ):
        raise TypeError("table rows must be a list or tuple of mappings")
    if catalogue and len(rows) > CATALOGUE_MAX_ROWS:
        raise ValueError("Mechanical catalogue exceeds 100000 rows")
    normalized = []
    for row in rows:
        validate_payload_fields(
            row, label="Mechanical table row", required=frozenset(columns)
        )
        normalized.append(dict(row))
    if catalogue:
        size = len(
            json.dumps(
                normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
        if size > CATALOGUE_MAX_ENCODED_BYTES:
            raise ValueError("Mechanical catalogue exceeds 64 MiB")
        _validate_catalogue_rows(normalized)
    import pandas as pd

    frame = pd.DataFrame(normalized, columns=columns)
    if catalogue:
        for column in (
            "schema_version",
            "model_revision",
            "producer_iteration",
            "object_id",
            "parent_id",
            "analysis_id",
            "row_count",
            "column_count",
            "view_index",
            "omitted_rows",
            "related_object_id",
            "scope_count",
        ):
            frame[column] = frame[column].astype("Int64")
        frame["scalar_value"] = frame["scalar_value"].astype("Float64")
        for column in ("has_tabular_data", "catalogue_complete", "body_hidden"):
            frame[column] = frame[column].astype("boolean")
    else:
        for column in ("table_index", "column_index", "result_set"):
            frame[column] = frame[column].astype("Int64")
    result = snapshot_scientific_value(frame)
    if type(result) is not TableValue:
        raise TypeError("Mechanical table construction did not produce TableValue")
    return result


def _validate_catalogue_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    summaries = [row for row in rows if row["record_kind"] == "session"]
    if len(summaries) != 1 or rows[0]["record_kind"] != "session":
        raise ValueError("Mechanical catalogue requires exactly one session summary")
    summary = summaries[0]
    identity_fields = (
        "schema_version",
        "model_revision",
        "producer_iteration",
        "catalogue_id",
        "producer_node_id",
        "producer_port",
        "producer_path",
        "run_id",
        "session_id",
        "document_id",
        "source_key",
    )
    for field in identity_fields:
        if any(row[field] != summary[field] for row in rows):
            raise ValueError(f"Mechanical catalogue {field} must agree across rows")
    _integer(summary["schema_version"], "schema_version")
    if summary["schema_version"] != 1:
        raise ValueError("unsupported Mechanical catalogue schema")
    _nonnegative(summary["model_revision"], "model_revision")
    _nonnegative(summary["producer_iteration"], "producer_iteration")
    _uuid(summary["catalogue_id"], "catalogue_id")
    for field in (
        "producer_node_id",
        "run_id",
        "session_id",
        "document_id",
        "source_key",
    ):
        _text(summary[field], field)
    if summary["producer_port"] not in {"info", "report"}:
        raise ValueError("producer_port is invalid")
    path = json.loads(summary["producer_path"])
    if json.dumps(path, separators=(",", ":")) != summary["producer_path"]:
        raise ValueError("producer_path must use canonical JSON spelling")
    _path(path, "producer_path")
    if (
        summary["catalogue_complete"] is not True
        and summary["catalogue_complete"] is not False
    ):
        raise TypeError("session catalogue_complete must be Boolean")
    _nonnegative(summary["omitted_rows"], "omitted_rows", nullable=True)
    if summary["catalogue_complete"] and summary["omitted_rows"] != 0:
        raise ValueError("complete catalogue must report zero omitted rows")
    selectors: set[str] = set()
    descriptor_seen = False
    for index, row in enumerate(rows):
        for field in (
            "record_kind",
            "catalogue_id",
            "producer_node_id",
            "producer_port",
            "producer_path",
            "run_id",
            "session_id",
            "document_id",
            "source_key",
            "system_key",
            "system_label",
            "selector_code",
            "object_path",
            "display_name",
            "api_type",
            "property_key",
            "property_caption",
            "display_value",
            "definition_kind",
            "unit",
            "quantity_name",
            "formula",
            "table_key",
            "table_family",
            "view_key",
            "view_name",
            "status",
            "message",
            "relation_kind",
            "relation_role",
            "related_label",
            "raw_source_id",
            "scope_kind",
            "relation_status",
            "activation_state",
        ):
            _text(row[field], field, empty=True)
        _integer(row["schema_version"], "schema_version")
        _nonnegative(row["model_revision"], "model_revision")
        _nonnegative(row["producer_iteration"], "producer_iteration")
        for field in (
            "object_id",
            "parent_id",
            "analysis_id",
            "row_count",
            "column_count",
            "view_index",
            "omitted_rows",
            "related_object_id",
            "scope_count",
        ):
            _nonnegative(row[field], field, nullable=True)
        scalar = row["scalar_value"]
        if scalar is not None and (
            type(scalar) not in {int, float} or not math.isfinite(scalar)
        ):
            raise TypeError("scalar_value must be a finite number or null")
        for field in ("has_tabular_data", "catalogue_complete", "body_hidden"):
            if row[field] is not None and type(row[field]) is not bool:
                raise TypeError(f"{field} must be Boolean or null")
        if row["record_kind"] not in _CATALOGUE_KINDS:
            raise ValueError("invalid Mechanical catalogue record_kind")
        for field, allowed_kinds in _CATALOGUE_FIELD_KINDS.items():
            if row["record_kind"] not in allowed_kinds and row[field] not in {"", None}:
                raise ValueError(
                    f"{field} is not applicable to {row['record_kind']} rows"
                )
        if index and row["record_kind"] == "operation":
            if descriptor_seen:
                raise ValueError("operation rows must precede descriptor rows")
        elif index:
            descriptor_seen = True
        if row["record_kind"] != "session" and row["catalogue_complete"] is not None:
            raise ValueError("catalogue_complete is only valid on the session row")
        if row["selector_code"]:
            selector = decode_selector(row["selector_code"])
            if row["selector_code"] in selectors:
                raise ValueError("duplicate Mechanical selector identity")
            selectors.add(row["selector_code"])
            if (
                selector["document_id"] != row["document_id"]
                or selector["system_key"] != row["system_key"]
            ):
                raise ValueError("selector belongs to another model or system")
            if selector["object_path"] != row["object_path"]:
                raise ValueError("selector path does not match its catalogue row")
            expected_native_id = (
                row["system_key"]
                if row["record_kind"] == "system"
                else row["object_id"]
                if row["record_kind"] == "object"
                else row["property_key"]
                if row["record_kind"] == "property"
                else row["table_key"]
                if row["record_kind"] == "table"
                else row["view_index"]
                if row["record_kind"] == "view"
                else None
            )
            if selector["kind"] != row["record_kind"]:
                raise ValueError("selector kind does not match its catalogue row")
            if expected_native_id is not None and (
                type(selector["native_id"]) is not type(expected_native_id)
                or selector["native_id"] != expected_native_id
            ):
                raise ValueError(
                    "selector native identity does not match its catalogue row"
                )
        relation = row["record_kind"] == "relation"
        if relation:
            if (
                row["relation_kind"] not in _RELATION_KINDS
                or row["relation_status"] not in _RELATION_STATUSES
            ):
                raise ValueError("invalid Mechanical relation metadata")
        elif any(
            row[field] not in {"", None}
            for field in (
                "relation_kind",
                "relation_role",
                "related_label",
                "raw_source_id",
                "scope_kind",
                "relation_status",
                "activation_state",
                "related_object_id",
                "scope_count",
                "body_hidden",
            )
        ):
            raise ValueError("relation fields are only valid on relation rows")


def catalogue_table(rows: Sequence[Mapping[str, Any]]) -> TableValue:
    return _table(rows, CATALOGUE_COLUMNS, catalogue=True)


def definitions_table(rows: Sequence[Mapping[str, Any]]) -> TableValue:
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("Definitions rows must be mappings")
        validate_payload_fields(
            row, label="Definitions row", required=frozenset(DEFINITIONS_COLUMNS)
        )
        _nonnegative(row["table_index"], "table_index")
        _nonnegative(row["column_index"], "column_index")
        for field in (
            "column_key",
            "column_label",
            "unit",
            "quantity_name",
            "definition_kind",
            "formula",
            "object_path",
            "property_key",
            "location",
            "coordinate_system",
            "notes",
        ):
            _text(row[field], field, empty=True)
        _nonnegative(row["result_set"], "result_set", nullable=True)
    return _table(rows, DEFINITIONS_COLUMNS, catalogue=False)


def search_details_table(rows: Sequence[Mapping[str, Any]]) -> TableValue:
    normalized = []
    for row in rows:
        validate_payload_fields(
            row, label="Mechanical search detail", required=frozenset(SEARCH_DETAILS_COLUMNS)
        )
        item = dict(row)
        _nonnegative(item["object_id"], "object_id")
        _nonnegative(item["scope_count"], "scope_count", nullable=True)
        for field in SEARCH_DETAILS_COLUMNS:
            if field not in {"object_id", "scope_count", "has_tabular_data", "body_hidden"}:
                _text(item[field], field, empty=True)
        for field in ("has_tabular_data", "body_hidden"):
            if item[field] is not None and type(item[field]) is not bool:
                raise TypeError(f"{field} must be Boolean or null")
        normalized.append(item)
    import pandas as pd

    frame = pd.DataFrame(normalized, columns=SEARCH_DETAILS_COLUMNS)
    for column in ("object_id", "scope_count"):
        frame[column] = frame[column].astype("Int64")
    for column in ("has_tabular_data", "body_hidden"):
        frame[column] = frame[column].astype("boolean")
    value = snapshot_scientific_value(frame)
    if type(value) is not TableValue:
        raise TypeError("Mechanical search details did not produce TableValue")
    return value


MECHANICAL_DATA_TYPE_FAMILY = DataTypeFamilySpec(
    family_id="corex.mechanical",
    display_name="Mechanical",
    color_token="mechanical",
    icon_key="mechanical",
)
MECHANICAL_DATA_TYPES = (
    DataTypeSpec(
        MODEL_TYPE_ID,
        "Mechanical Model",
        MECHANICAL_DATA_TYPE_FAMILY.family_id,
        validate_model,
        carriers=frozenset({"handle"}),
        persistence="never",
    ),
    DataTypeSpec(
        OBJECT_TYPE_ID,
        "Mechanical Object",
        MECHANICAL_DATA_TYPE_FAMILY.family_id,
        validate_object,
        carriers=frozenset({"inline"}),
        persistence="never",
    ),
    DataTypeSpec(
        PROPERTY_TYPE_ID,
        "Mechanical Property",
        MECHANICAL_DATA_TYPE_FAMILY.family_id,
        validate_property,
        carriers=frozenset({"inline"}),
        persistence="never",
    ),
    DataTypeSpec(
        CAMERA_VIEW_TYPE_ID,
        "Mechanical Camera View",
        MECHANICAL_DATA_TYPE_FAMILY.family_id,
        validate_camera_view,
        carriers=frozenset({"inline"}),
        persistence="never",
    ),
)
MECHANICAL_CONTRACT_MANIFEST = PluginContractManifest(
    data_type_families=(MECHANICAL_DATA_TYPE_FAMILY,),
    data_types=MECHANICAL_DATA_TYPES,
)

__all__ = [
    "CAMERA_VIEW_TYPE_ID",
    "CATALOGUE_COLUMNS",
    "CATALOGUE_MAX_ENCODED_BYTES",
    "CATALOGUE_MAX_ROWS",
    "DEFINITIONS_COLUMNS",
    "SEARCH_DETAILS_COLUMNS",
    "MECHANICAL_CONTRACT_MANIFEST",
    "MECHANICAL_DATA_TYPES",
    "MODEL_HANDLE_KIND",
    "MODEL_TYPE_ID",
    "OBJECT_TYPE_ID",
    "PROPERTY_TYPE_ID",
    "camera_view_value",
    "catalogue_table",
    "decode_selector",
    "definitions_table",
    "encode_selector",
    "object_value",
    "property_value",
    "search_details_table",
    "model_handle",
    "validate_camera_view",
    "validate_model",
    "validate_object",
    "validate_property",
]
