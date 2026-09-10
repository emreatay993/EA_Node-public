from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
import math
from pathlib import Path
from typing import Any

from ea_node_editor.addons.tabular_data.loader_cache_service import (
    LargeDataMaterializationError,
    MissingTabularDependencyError,
    SelectionRequiredError,
    TabularLoadOptions,
    UnsupportedTabularFormatError,
    shared_tabular_loader_cache_service,
)
from ea_node_editor.nodes.builtins.integrations_common import pick_path, require_existing_file
from ea_node_editor.common.payload_tools import REF_METADATA_MAX_BYTES
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.file_dialog_filters import TABULAR_DATA_FILES_FILTER
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    TabularDataRef,
)

TABULAR_DATA_INPUT_NODE_TYPE_ID = "tabular.input"
TABULAR_DATA_INPUT_DISPLAY_NAME = "Tabular Data Input"
TABULAR_DATA_TABLE_OUTPUT_KEY = "table_data"
TABULAR_DATA_ARRAY_OUTPUT_KEY = "array_data"
TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET = "app_managed_parquet"
TABULAR_DATA_INPUT_CACHE_POLICY_SOURCE_DIRECT = "source_direct"
TABULAR_DATA_INPUT_CACHE_POLICIES = (
    TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET,
    TABULAR_DATA_INPUT_CACHE_POLICY_SOURCE_DIRECT,
)
TABULAR_DATA_INPUT_PATH_FILTER = TABULAR_DATA_FILES_FILTER

TABULAR_DATA_INPUT_ERROR_SELECTOR_REQUIRED = "selector_required"
TABULAR_DATA_INPUT_ERROR_MISSING_BACKEND = "missing_backend"
TABULAR_DATA_INPUT_ERROR_LARGE_DATA_GATED = "large_data_materialization_gated"
TABULAR_DATA_INPUT_ERROR_UNSUPPORTED_FORMAT = "unsupported_format"
TABULAR_ARRAY_SLICE_2D_PROPERTY = "array_slice_2d"
TABULAR_ARRAY_ROW_START_PROPERTY = "array_slice_2d_row_start"
TABULAR_ARRAY_ROW_COUNT_PROPERTY = "array_slice_2d_row_count"
TABULAR_ARRAY_COLUMN_START_PROPERTY = "array_slice_2d_column_start"
TABULAR_ARRAY_COLUMN_COUNT_PROPERTY = "array_slice_2d_column_count"
TABULAR_ARRAY_SELECTION_SUMMARY_PROPERTY = "array_slice_2d_summary"
TABULAR_ARRAY_SELECTION_PROPERTY_KEYS = frozenset(
    {
        TABULAR_ARRAY_ROW_START_PROPERTY,
        TABULAR_ARRAY_ROW_COUNT_PROPERTY,
        TABULAR_ARRAY_COLUMN_START_PROPERTY,
        TABULAR_ARRAY_COLUMN_COUNT_PROPERTY,
    }
)
TABULAR_SELECTED_COLUMNS_PROPERTY = "tabular_selected_columns"
TABULAR_TABLE_VIEW_STATE_PROPERTY = "tabular_table_view_state"
TABULAR_TABLE_VIEW_STATE_VERSION = 1
TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH = 48
TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH = 480

_DEFAULT_ARRAY_SLICE_2D = {
    "row_offset": 0,
    "column_offset": 0,
    "row_limit": 50,
    "column_limit": 50,
}


def _mapping_from_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items()}
    return {}


def _schema_hints_from_value(value: Any) -> dict[str, str]:
    return {
        str(key).strip(): str(item).strip()
        for key, item in _mapping_from_value(value).items()
        if str(key).strip() and str(item).strip()
    }


def _optional_int(value: Any, *, default: int | None = 0) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _non_negative_int(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, normalized)


def tabular_array_slice_2d_from_value(value: Any) -> dict[str, int]:
    payload = {**_DEFAULT_ARRAY_SLICE_2D, **_mapping_from_value(value)}
    return {
        "row_offset": _non_negative_int(payload.get("row_offset"), default=0),
        "column_offset": _non_negative_int(payload.get("column_offset"), default=0),
        "row_limit": max(1, _non_negative_int(payload.get("row_limit"), default=50)),
        "column_limit": max(1, _non_negative_int(payload.get("column_limit"), default=50)),
    }


def _column_label_from_offset(offset: int) -> str:
    normalized = max(0, int(offset))
    label = ""
    while True:
        normalized, remainder = divmod(normalized, 26)
        label = chr(ord("A") + remainder) + label
        if normalized == 0:
            return label
        normalized -= 1


def _column_offset_from_user_value(value: Any, *, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return max(0, int(default))
    try:
        return max(0, int(text) - 1)
    except ValueError:
        pass
    normalized = text.upper()
    if not normalized.isalpha():
        return max(0, int(default))
    offset = 0
    for character in normalized:
        offset = offset * 26 + (ord(character) - ord("A") + 1)
    return max(0, offset - 1)


def _positive_int_from_user_value(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return max(1, int(default))
    return max(1, normalized)


def tabular_array_column_label_from_offset(offset: Any) -> str:
    return _column_label_from_offset(_non_negative_int(offset, default=0))


def tabular_array_slice_2d_summary(value: Any) -> str:
    selection = tabular_array_slice_2d_from_value(value)
    row_start = selection["row_offset"] + 1
    row_end = selection["row_offset"] + selection["row_limit"]
    column_start = _column_label_from_offset(selection["column_offset"])
    column_end = _column_label_from_offset(selection["column_offset"] + selection["column_limit"] - 1)
    return f"Rows {row_start}-{row_end}, Columns {column_start}-{column_end}"


def tabular_array_slice_2d_with_property_update(
    current_value: Any,
    property_key: str,
    user_value: Any,
) -> dict[str, int] | None:
    if property_key not in TABULAR_ARRAY_SELECTION_PROPERTY_KEYS:
        return None
    selection = tabular_array_slice_2d_from_value(current_value)
    if property_key == TABULAR_ARRAY_ROW_START_PROPERTY:
        selection["row_offset"] = max(
            0,
            _positive_int_from_user_value(user_value, default=selection["row_offset"] + 1) - 1,
        )
    elif property_key == TABULAR_ARRAY_ROW_COUNT_PROPERTY:
        selection["row_limit"] = _positive_int_from_user_value(user_value, default=selection["row_limit"])
    elif property_key == TABULAR_ARRAY_COLUMN_START_PROPERTY:
        selection["column_offset"] = _column_offset_from_user_value(user_value, default=selection["column_offset"])
    elif property_key == TABULAR_ARRAY_COLUMN_COUNT_PROPERTY:
        selection["column_limit"] = _positive_int_from_user_value(user_value, default=selection["column_limit"])
    return selection


def _cache_policy_from_value(value: Any) -> str:
    normalized = str(value or TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET).strip()
    if normalized in TABULAR_DATA_INPUT_CACHE_POLICIES:
        return normalized
    return TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET


def _clamped_column_width(value: Any) -> int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return max(
        TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH,
        min(TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH, int(round(numeric))),
    )


def normalize_tabular_table_view_state(value: Any) -> dict[str, Any]:
    payload = _mapping_from_value(value)
    raw_widths = _mapping_from_value(payload.get("column_widths", {}))
    column_widths: dict[str, int] = {}
    for key, width_value in raw_widths.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        width = _clamped_column_width(width_value)
        if width is None:
            continue
        column_widths[normalized_key] = width
    return {
        "version": TABULAR_TABLE_VIEW_STATE_VERSION,
        "column_widths": column_widths,
    }


def normalize_tabular_selected_columns(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items: Any = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = []
    selected: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(normalized)
    return selected


def tabular_load_options_from_node_properties(properties: Mapping[str, Any]) -> TabularLoadOptions:
    delimiter = str(properties.get("delimiter", "") or "")
    return TabularLoadOptions(
        delimiter=delimiter or None,
        encoding=str(properties.get("encoding", "utf-8") or "utf-8"),
        header_row=_optional_int(properties.get("header_row", 0), default=0),
        skip_rows=_non_negative_int(properties.get("skip_rows", 0), default=0),
        schema_hints=_schema_hints_from_value(properties.get("schema_hints", {})),
        selected_object=str(properties.get("selected_object", "") or ""),
        allow_npz_archive_preview=bool(properties.get("allow_npz_archive_preview", False)),
        cache_policy=_cache_policy_from_value(properties.get("cache_policy")),
    )


def _node_options_metadata(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cache_policy": _cache_policy_from_value(properties.get("cache_policy")),
        "project_managed_source": bool(properties.get("project_managed_source", False)),
        "project_managed_cache": bool(properties.get("project_managed_cache", False)),
        "array_slice_2d": tabular_array_slice_2d_from_value(
            properties.get(TABULAR_ARRAY_SLICE_2D_PROPERTY, {})
        ),
        "selected_columns": normalize_tabular_selected_columns(
            properties.get(TABULAR_SELECTED_COLUMNS_PROPERTY, [])
        ),
    }


def tabular_input_warning_facts(
    warning_codes: tuple[str, ...],
    *,
    ref: TabularDataRef | ArrayDataRef,
    source_path: Path,
) -> tuple[dict[str, Any], ...]:
    format_id = str(ref.metadata.get("format_id", "") or "")
    size_bytes = int(ref.metadata.get("size_bytes", 0) or 0)
    return tuple(
        {
            "code": str(code),
            "severity": "warning",
            "node_type_id": TABULAR_DATA_INPUT_NODE_TYPE_ID,
            "source_name": source_path.name,
            "format_id": format_id,
            "size_bytes": size_bytes,
        }
        for code in warning_codes
        if str(code).strip()
    )


def tabular_input_error_fact(error: BaseException, *, source_path: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": "error",
        "node_type_id": TABULAR_DATA_INPUT_NODE_TYPE_ID,
        "message": str(error),
    }
    if source_path is not None:
        payload["source_path"] = str(source_path)
    if isinstance(error, SelectionRequiredError):
        payload.update(
            {
                "code": TABULAR_DATA_INPUT_ERROR_SELECTOR_REQUIRED,
                "format_id": error.format_id,
                "choices": [choice.to_payload() for choice in error.choices],
                "recoverable": bool(error.recoverable),
            }
        )
        return payload
    if isinstance(error, MissingTabularDependencyError):
        payload.update(
            {
                "code": TABULAR_DATA_INPUT_ERROR_MISSING_BACKEND,
                "format_id": error.format_id,
                "dependency": error.dependency,
                "purpose": error.purpose,
                "recoverable": bool(error.recoverable),
            }
        )
        return payload
    if isinstance(error, LargeDataMaterializationError):
        payload.update(
            {
                "code": TABULAR_DATA_INPUT_ERROR_LARGE_DATA_GATED,
                "size_bytes": error.size_bytes,
                "recoverable": bool(error.recoverable),
            }
        )
        return payload
    if isinstance(error, UnsupportedTabularFormatError):
        payload.update(
            {
                "code": TABULAR_DATA_INPUT_ERROR_UNSUPPORTED_FORMAT,
                "source_path": str(error.path),
                "recoverable": bool(error.recoverable),
            }
        )
        return payload
    payload["code"] = error.__class__.__name__
    return payload


def _attach_structured_error(error: BaseException, *, source_path: Path) -> BaseException:
    setattr(error, "structured_error", tabular_input_error_fact(error, source_path=source_path))
    return error


def _ref_with_node_metadata(
    ref: TabularDataRef | ArrayDataRef,
    *,
    source_path: Path,
    properties: Mapping[str, Any],
) -> tuple[TabularDataRef | ArrayDataRef, tuple[str, ...]]:
    metadata = dict(ref.metadata)
    warning_codes = tuple(str(code) for code in metadata.get("warnings", ()) if str(code).strip())
    warning_facts = tabular_input_warning_facts(warning_codes, ref=ref, source_path=source_path)
    if warning_facts:
        metadata["warning_facts"] = [dict(fact) for fact in warning_facts]
    metadata["node_options"] = _node_options_metadata(properties)
    if "column_schema" in metadata and len(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > REF_METADATA_MAX_BYTES:
        del metadata["column_schema"]
    return replace(ref, metadata=metadata), warning_codes


def execute_tabular_input(ctx: ExecutionContext) -> NodeResult:
    source_path = pick_path(
        ctx,
        input_key="path",
        property_key="path",
        node_name=TABULAR_DATA_INPUT_DISPLAY_NAME,
    )
    require_existing_file(source_path, node_name=TABULAR_DATA_INPUT_DISPLAY_NAME)
    options = tabular_load_options_from_node_properties(ctx.properties)
    service = shared_tabular_loader_cache_service()
    try:
        ref = service.open_source(source_path, options)
    except (
        SelectionRequiredError,
        MissingTabularDependencyError,
        LargeDataMaterializationError,
        UnsupportedTabularFormatError,
    ) as exc:
        raise _attach_structured_error(exc, source_path=source_path)

    ref, warning_codes = _ref_with_node_metadata(
        ref,
        source_path=source_path,
        properties=ctx.properties,
    )
    outputs: dict[str, Any] = {}
    if isinstance(ref, TabularDataRef):
        outputs[TABULAR_DATA_TABLE_OUTPUT_KEY] = ref
    else:
        outputs[TABULAR_DATA_ARRAY_OUTPUT_KEY] = ref
    return NodeResult(outputs=outputs, warnings=warning_codes)

__all__ = [
    "TABULAR_DATA_INPUT_CACHE_POLICIES",
    "TABULAR_DATA_INPUT_CACHE_POLICY_APP_MANAGED_PARQUET",
    "TABULAR_DATA_INPUT_CACHE_POLICY_SOURCE_DIRECT",
    "TABULAR_DATA_ARRAY_OUTPUT_KEY",
    "TABULAR_DATA_INPUT_DISPLAY_NAME",
    "TABULAR_DATA_INPUT_ERROR_LARGE_DATA_GATED",
    "TABULAR_DATA_INPUT_ERROR_MISSING_BACKEND",
    "TABULAR_DATA_INPUT_ERROR_SELECTOR_REQUIRED",
    "TABULAR_DATA_INPUT_ERROR_UNSUPPORTED_FORMAT",
    "TABULAR_DATA_INPUT_NODE_TYPE_ID",
    "TABULAR_DATA_INPUT_PATH_FILTER",
    "TABULAR_DATA_TABLE_OUTPUT_KEY",
    "TABULAR_ARRAY_COLUMN_COUNT_PROPERTY",
    "TABULAR_ARRAY_COLUMN_START_PROPERTY",
    "TABULAR_ARRAY_ROW_COUNT_PROPERTY",
    "TABULAR_ARRAY_ROW_START_PROPERTY",
    "TABULAR_ARRAY_SELECTION_PROPERTY_KEYS",
    "TABULAR_ARRAY_SELECTION_SUMMARY_PROPERTY",
    "TABULAR_ARRAY_SLICE_2D_PROPERTY",
    "TABULAR_SELECTED_COLUMNS_PROPERTY",
    "TABULAR_TABLE_VIEW_STATE_MAX_COLUMN_WIDTH",
    "TABULAR_TABLE_VIEW_STATE_MIN_COLUMN_WIDTH",
    "TABULAR_TABLE_VIEW_STATE_PROPERTY",
    "TABULAR_TABLE_VIEW_STATE_VERSION",
    "execute_tabular_input",
    "normalize_tabular_table_view_state",
    "normalize_tabular_selected_columns",
    "tabular_array_column_label_from_offset",
    "tabular_array_slice_2d_from_value",
    "tabular_array_slice_2d_summary",
    "tabular_array_slice_2d_with_property_update",
    "tabular_input_error_fact",
    "tabular_input_warning_facts",
    "tabular_load_options_from_node_properties",
]
