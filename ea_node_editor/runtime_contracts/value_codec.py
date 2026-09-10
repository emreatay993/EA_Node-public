# Purpose: Serialize and deserialize recursive runtime values with exact tagged payloads.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_typed_runtime_values.py

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeAlias

from ea_node_editor.common.payload_tools import (
    JSON_MAX_DEPTH,
    copy_json_safe,
    validate_payload_fields,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.scientific_values import (
    ArrayValue, TableValue, snapshot_scientific_values,
)
from ea_node_editor.runtime_contracts.scientific_codec import (
    SCIENTIFIC_MARKER, check_scientific_budget,
    scientific_from_payload, scientific_to_payload,
)
from ea_node_editor.runtime_contracts.data_types import (
    ARRAY_DATA_REF_TYPE_ID,
    ARRAY_SLICE_2D_REF_TYPE_ID,
    DataTypeCatalogError,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    TABULAR_WINDOW_REF_TYPE_ID,
)
from ea_node_editor.runtime_contracts.image_value import (
    IMAGE_VALUE_DATA_TYPE_ID,
    ImageValue,
    _RUNTIME_IMAGE_MARKER_VALUE,
)
from ea_node_editor.runtime_contracts.interval_1d import (
    INTERVAL_1D_DATA_TYPE,
    Interval1D,
)
from ea_node_editor.runtime_contracts.tabular_data import (
    ARRAY_DATA_REF_MARKER_VALUE,
    ARRAY_SLICE_2D_REF_MARKER_VALUE,
    TABULAR_DATA_REF_MARKER_VALUE,
    TABULAR_WINDOW_REF_MARKER_VALUE,
    ArrayDataRef,
    ArraySlice2DRef,
    TabularDataRef,
    TabularWindowRef,
    coerce_array_data_ref,
    coerce_array_slice_2d_ref,
    coerce_tabular_data_ref,
    coerce_tabular_window_ref,
)
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
    _RUNTIME_ARTIFACT_MARKER_VALUE,
    _RUNTIME_HANDLE_MARKER_VALUE,
    _RUNTIME_TYPED_INLINE_MARKER_VALUE,
    _RUNTIME_VALUE_MARKER_KEY,
    coerce_runtime_artifact_ref,
    coerce_runtime_handle_ref,
)

if TYPE_CHECKING:
    from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog

_OPAQUE_MAPPING_RUNTIME_MARKERS = frozenset(
    {
        "secret_data",
        "ssh_sftp_host_data",
    }
)
_RUNTIME_DATA_TREE_MARKER_VALUE = "data_tree"
_RUNTIME_INTERVAL_1D_MARKER_VALUE = INTERVAL_1D_DATA_TYPE

RuntimeValueRef: TypeAlias = (
    ArrayValue
    | TableValue
    | TypedInlineValue
    | ImageValue
    | RuntimeArtifactRef
    | RuntimeHandleRef
    | TabularDataRef
    | ArrayDataRef
    | TabularWindowRef
    | ArraySlice2DRef
)


def _extract_runtime_marker(payload: Mapping[str, Any]) -> str | None:
    if _RUNTIME_VALUE_MARKER_KEY not in payload:
        return None
    marker = payload.get(_RUNTIME_VALUE_MARKER_KEY)
    if not isinstance(marker, str):
        raise ValueError("Runtime value marker must be a non-empty string")
    normalized_marker = marker.strip()
    if not normalized_marker:
        raise ValueError("Runtime value marker must be a non-empty string")
    return normalized_marker


def _coerce_runtime_value_ref(
    payload: Mapping[str, Any],
    *,
    catalog: DataTypeCatalog | None,
) -> RuntimeValueRef | None:
    marker = _extract_runtime_marker(payload)
    if marker is None:
        return None
    if marker == SCIENTIFIC_MARKER:
        return scientific_from_payload(payload)
    if marker == _RUNTIME_TYPED_INLINE_MARKER_VALUE:
        runtime_value = TypedInlineValue.from_payload(payload, catalog=catalog)
        if runtime_value is None:
            raise ValueError("Typed inline payload is incomplete")
        return runtime_value
    if marker == _RUNTIME_IMAGE_MARKER_VALUE:
        image = ImageValue.from_payload(payload, catalog=catalog)
        if image is None:
            raise ValueError("ImageValue payload is incomplete")
        return image
    if marker == _RUNTIME_ARTIFACT_MARKER_VALUE:
        runtime_ref = coerce_runtime_artifact_ref(payload, catalog=catalog)
        if runtime_ref is None:
            raise ValueError("Runtime artifact ref payload is incomplete")
        return runtime_ref
    if marker == _RUNTIME_HANDLE_MARKER_VALUE:
        runtime_ref = coerce_runtime_handle_ref(payload, catalog=catalog)
        if runtime_ref is None:
            raise ValueError("Runtime handle ref payload is incomplete")
        return runtime_ref
    if marker == TABULAR_DATA_REF_MARKER_VALUE:
        runtime_ref = coerce_tabular_data_ref(payload)
        if runtime_ref is None:
            raise ValueError("Tabular data ref payload is incomplete")
        return runtime_ref
    if marker == ARRAY_DATA_REF_MARKER_VALUE:
        runtime_ref = coerce_array_data_ref(payload)
        if runtime_ref is None:
            raise ValueError("Array data ref payload is incomplete")
        return runtime_ref
    if marker == TABULAR_WINDOW_REF_MARKER_VALUE:
        runtime_ref = coerce_tabular_window_ref(payload)
        if runtime_ref is None:
            raise ValueError("Tabular window ref payload is incomplete")
        return runtime_ref
    if marker == ARRAY_SLICE_2D_REF_MARKER_VALUE:
        runtime_ref = coerce_array_slice_2d_ref(payload)
        if runtime_ref is None:
            raise ValueError("Array slice 2D ref payload is incomplete")
        return runtime_ref
    raise ValueError(f"Unsupported runtime value marker: {marker!r}")


def _serialize_data_tree(
    value: DataTree,
    *,
    depth: int,
    catalog: DataTypeCatalog | None,
) -> dict[str, Any]:
    return {
        _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_DATA_TREE_MARKER_VALUE,
        "branches": [
            {
                "path": list(path),
                "items": [
                    _serialize_runtime_value(
                        item,
                        depth=depth + 1,
                        catalog=catalog,
                    )
                    for item in items
                ],
            }
            for path, items in value.branches
        ],
    }


def _deserialize_data_tree(
    payload: Mapping[str, Any],
    *,
    depth: int,
    catalog: DataTypeCatalog | None,
) -> DataTree:
    validate_payload_fields(
        payload,
        label="DataTree runtime payload",
        required=frozenset({_RUNTIME_VALUE_MARKER_KEY, "branches"}),
    )
    raw_branches = payload.get("branches")
    if isinstance(raw_branches, (str, bytes, bytearray)) or not isinstance(
        raw_branches, list
    ):
        raise ValueError("DataTree runtime payload branches must be a list")
    branches: list[tuple[tuple[int, ...], tuple[Any, ...]]] = []
    for raw_branch in raw_branches:
        if not isinstance(raw_branch, Mapping):
            raise ValueError("DataTree runtime payload branches must be mappings")
        validate_payload_fields(
            raw_branch,
            label="DataTree runtime branch",
            required=frozenset({"path", "items"}),
        )
        raw_path = raw_branch.get("path")
        raw_items = raw_branch.get("items")
        if isinstance(raw_path, (str, bytes, bytearray)) or not isinstance(
            raw_path, list
        ):
            raise ValueError("DataTree runtime payload paths must be lists")
        if isinstance(raw_items, (str, bytes, bytearray)) or not isinstance(
            raw_items, list
        ):
            raise ValueError("DataTree runtime payload items must be lists")
        branches.append(
            (
                tuple(raw_path),
                tuple(
                    _deserialize_runtime_value(
                        item,
                        depth=depth + 1,
                        catalog=catalog,
                    )
                    for item in raw_items
                ),
            )
        )
    return DataTree(branches)


def _serialize_interval_1d(value: Interval1D) -> dict[str, Any]:
    return {
        _RUNTIME_VALUE_MARKER_KEY: _RUNTIME_INTERVAL_1D_MARKER_VALUE,
        "start": value.start,
        "end": value.end,
    }


def _deserialize_interval_1d(payload: Mapping[str, Any]) -> Interval1D:
    expected_keys = {_RUNTIME_VALUE_MARKER_KEY, "start", "end"}
    missing_keys = expected_keys.difference(payload)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Interval 1D runtime payload is missing: {missing}")
    unexpected_keys = set(payload).difference(expected_keys)
    if unexpected_keys:
        unexpected = ", ".join(sorted(str(key) for key in unexpected_keys))
        raise ValueError(
            f"Interval 1D runtime payload has unexpected fields: {unexpected}"
        )
    return Interval1D(start=payload["start"], end=payload["end"])


def _runtime_semantic_type_id(value: object) -> str:
    if isinstance(value, (ArrayValue, TableValue)):
        return value.data_type_id
    if isinstance(value, ImageValue):
        return IMAGE_VALUE_DATA_TYPE_ID
    if isinstance(value, TypedInlineValue):
        return value.data_type_id
    if isinstance(value, RuntimeArtifactRef):
        return value.data_type_id
    if isinstance(value, RuntimeHandleRef):
        return value.data_type_id
    if isinstance(value, TabularDataRef):
        return TABULAR_DATA_REF_TYPE_ID
    if isinstance(value, ArrayDataRef):
        return ARRAY_DATA_REF_TYPE_ID
    if isinstance(value, TabularWindowRef):
        return TABULAR_WINDOW_REF_TYPE_ID
    if isinstance(value, ArraySlice2DRef):
        return ARRAY_SLICE_2D_REF_TYPE_ID
    if isinstance(value, Interval1D):
        return INTERVAL_1D_GRAPH_DATA_TYPE_ID
    return ""


def _requires_active_catalog(value: object) -> bool:
    if isinstance(
        value,
        (ArrayValue, TableValue, TypedInlineValue, ImageValue, RuntimeArtifactRef, RuntimeHandleRef),
    ):
        return True
    if isinstance(value, DataTree):
        return any(
            _requires_active_catalog(item)
            for _path, items in value.branches
            for item in items
        )
    if isinstance(value, Mapping):
        marker = _extract_runtime_marker(value)
        if marker in {
            SCIENTIFIC_MARKER,
            _RUNTIME_TYPED_INLINE_MARKER_VALUE,
            _RUNTIME_IMAGE_MARKER_VALUE,
            _RUNTIME_ARTIFACT_MARKER_VALUE,
            _RUNTIME_HANDLE_MARKER_VALUE,
        }:
            return True
        return any(_requires_active_catalog(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_requires_active_catalog(item) for item in value)
    return False


def _validate_catalog_value(
    value: object,
    *,
    catalog: DataTypeCatalog,
    declared_type_id: str,
) -> None:
    if isinstance(value, DataTree):
        for _path, items in value.branches:
            for item in items:
                if isinstance(item, DataTree):
                    raise DataTypeCatalogError(
                        "nested DataTree runtime values are not supported"
                    )
                _validate_catalog_value(
                    item,
                    catalog=catalog,
                    declared_type_id=declared_type_id,
                )
        return
    semantic_type_id = _runtime_semantic_type_id(value)
    if semantic_type_id:
        catalog.validate_carrier(declared_type_id or semantic_type_id, value)
        return
    if declared_type_id:
        catalog.validate_carrier(declared_type_id, value)
    if isinstance(value, Mapping):
        nested_values = value.values()
    elif isinstance(value, (list, tuple)):
        nested_values = value
    else:
        return
    for item in nested_values:
        _validate_catalog_value(
            item,
            catalog=catalog,
            declared_type_id="",
        )


def _serialize_runtime_value(
    value: Any,
    *,
    depth: int,
    catalog: DataTypeCatalog | None,
) -> Any:
    if depth > JSON_MAX_DEPTH:
        raise ValueError(f"runtime value exceeds maximum JSON depth {JSON_MAX_DEPTH}")
    if isinstance(value, (ArrayValue, TableValue)):
        return scientific_to_payload(value)
    if isinstance(value, DataTree):
        return _serialize_data_tree(
            value,
            depth=depth,
            catalog=catalog,
        )
    if isinstance(value, Interval1D):
        return _serialize_interval_1d(value)
    if isinstance(
        value,
        (
            TypedInlineValue,
            ImageValue,
            RuntimeArtifactRef,
            RuntimeHandleRef,
            TabularDataRef,
            ArrayDataRef,
            TabularWindowRef,
            ArraySlice2DRef,
        ),
    ):
        if isinstance(
            value,
            (TypedInlineValue, ImageValue, RuntimeArtifactRef, RuntimeHandleRef),
        ):
            return value.to_payload(catalog=catalog)
        return value.to_payload()
    if isinstance(value, Mapping):
        marker = _extract_runtime_marker(value)
        if marker == _RUNTIME_DATA_TREE_MARKER_VALUE:
            return _serialize_data_tree(
                _deserialize_data_tree(
                    value,
                    depth=depth,
                    catalog=catalog,
                ),
                depth=depth,
                catalog=catalog,
            )
        if marker == _RUNTIME_INTERVAL_1D_MARKER_VALUE:
            return _serialize_interval_1d(_deserialize_interval_1d(value))
        payload_ref = (
            None
            if marker in _OPAQUE_MAPPING_RUNTIME_MARKERS
            else _coerce_runtime_value_ref(value, catalog=catalog)
        )
        if payload_ref is not None:
            if isinstance(payload_ref, (ArrayValue, TableValue)):
                return scientific_to_payload(payload_ref)
            if isinstance(
                payload_ref,
                (TypedInlineValue, ImageValue, RuntimeArtifactRef, RuntimeHandleRef),
            ):
                return payload_ref.to_payload(catalog=catalog)
            return payload_ref.to_payload()
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("runtime value mapping keys must be strings")
            copied[key] = _serialize_runtime_value(
                item,
                depth=depth + 1,
                catalog=catalog,
            )
        return copied
    if isinstance(value, (list, tuple)):
        return [
            _serialize_runtime_value(
                item,
                depth=depth + 1,
                catalog=catalog,
            )
            for item in value
        ]
    return copy_json_safe(value, field_name="runtime value")


def serialize_runtime_value(
    value: Any,
    *,
    catalog: DataTypeCatalog | None = None,
    declared_type_id: str = "",
) -> Any:
    value = snapshot_scientific_values(value)
    check_scientific_budget(value)
    if catalog is None and (declared_type_id or _requires_active_catalog(value)):
        raise DataTypeCatalogError(
            "an active data-type catalog is required for semantic runtime carriers"
        )
    if catalog is not None and declared_type_id:
        _validate_catalog_value(
            value,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
    serialized = _serialize_runtime_value(
        value,
        depth=0,
        catalog=catalog,
    )
    serialized = copy_json_safe(
        serialized,
        field_name="runtime value",
        max_depth=JSON_MAX_DEPTH,
    )
    if catalog is not None:
        restored = _deserialize_runtime_value(
            serialized,
            depth=0,
            catalog=catalog,
        )
        _validate_catalog_value(
            restored,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
    return serialized


def _deserialize_runtime_value(
    value: Any,
    *,
    depth: int,
    catalog: DataTypeCatalog | None,
) -> Any:
    if depth > JSON_MAX_DEPTH:
        raise ValueError(f"runtime value exceeds maximum JSON depth {JSON_MAX_DEPTH}")
    if isinstance(value, Mapping):
        marker = _extract_runtime_marker(value)
        if marker == _RUNTIME_DATA_TREE_MARKER_VALUE:
            return _deserialize_data_tree(
                value,
                depth=depth,
                catalog=catalog,
            )
        if marker == _RUNTIME_INTERVAL_1D_MARKER_VALUE:
            return _deserialize_interval_1d(value)
        payload_ref = (
            None
            if marker in _OPAQUE_MAPPING_RUNTIME_MARKERS
            else _coerce_runtime_value_ref(value, catalog=catalog)
        )
        if payload_ref is not None:
            return payload_ref
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("runtime value mapping keys must be strings")
            copied[key] = _deserialize_runtime_value(
                item,
                depth=depth + 1,
                catalog=catalog,
            )
        return copied
    if isinstance(value, (list, tuple)):
        return [
            _deserialize_runtime_value(
                item,
                depth=depth + 1,
                catalog=catalog,
            )
            for item in value
        ]
    return copy_json_safe(value, field_name="runtime value")


def deserialize_runtime_value(
    value: Any,
    *,
    catalog: DataTypeCatalog | None = None,
    declared_type_id: str = "",
) -> Any:
    check_scientific_budget(value)
    safe_value = copy_json_safe(
        value,
        field_name="runtime value",
        max_depth=JSON_MAX_DEPTH,
    )
    if catalog is None and (declared_type_id or _requires_active_catalog(safe_value)):
        raise DataTypeCatalogError(
            "an active data-type catalog is required for semantic runtime carriers"
        )
    restored = _deserialize_runtime_value(
        safe_value,
        depth=0,
        catalog=catalog,
    )
    if catalog is not None:
        _validate_catalog_value(
            restored,
            catalog=catalog,
            declared_type_id=declared_type_id,
        )
    return restored


__all__ = [
    "RuntimeValueRef",
    "deserialize_runtime_value",
    "serialize_runtime_value",
]
