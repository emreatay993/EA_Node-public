# Purpose: Project shell execution state into QML-ready graph-canvas facts,
#          including runtime data-port flow state.
# Map: feature_routes/node_execution_visualization
# Tests: tests/test_port_flow_state.py, tests/mechanical_catalogue/test_controls.py
# Landmarks: safe rich-preview projection; resolve_runtime_property_presentations; ExecutionStateProps; Panel display/copy
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
import unicodedata

from PyQt6.QtCore import pyqtProperty, pyqtSignal, pyqtSlot

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.readiness import (
    evaluate_node_readiness,
    readiness_value_is_present,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.data_types import DataTypeCatalog, DataTypeSpec
from ea_node_editor.runtime_contracts.image_value import ImageValue
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
)
from ea_node_editor.ui.support.node_presentation import (
    project_supported_upstream_property_value,
)
from ea_node_editor.ui.support.port_flow_state import resolve_runtime_port_flow_states
from ea_node_editor.ui.support.solution_output_cache import (
    retained_output_records_by_node,
)
from ea_node_editor.ui.image_value_preview_provider import image_value_preview_source
from ea_node_editor.ui.media_panel_source import resolve_media_panel_source
from ea_node_editor.ui_qml.bridge_runtime import (
    copy_dict as _copy_dict,
    source_attr as _source_attr,
)
from ea_node_editor.ui_qml.graph_canvas_viewport_index import (
    normalize_node_id,
)

if TYPE_CHECKING:
    pass


_PREVIEW_ITEM_LIMIT = 8
_PREVIEW_SAMPLE_LIMIT = 160
_PREVIEW_TEXT_SCAN_LIMIT = _PREVIEW_SAMPLE_LIMIT * 4
_PREVIEW_CONTAINER_DEPTH_LIMIT = 3
_PREVIEW_INTEGER_LIMIT = (1 << 53) - 1
_INLINE_VALUE_DATA_TYPE_IDS = frozenset(
    {
        "COREX.DataTypes.Plane",
        "COREX.DataTypes.ColorMap",
        "COREX.DataTypes.NodeVisual",
        "COREX.DataTypes.MultiAgentSystem.AgentModel",
        "COREX.Mechanical.CameraView",
    }
)
_SENSITIVE_RUNTIME_MARKERS = frozenset({"secret_data", "ssh_sftp_host_data"})
_SAFE_HANDLE_PREVIEW_FAMILIES = frozenset(
    {"engineering", "fem", "geometry", "mesh"}
)
_SAFE_HANDLE_METADATA_LABELS = {
    "node_count": "nodes",
    "element_count": "elements",
    "entity_count": "entities",
    "component_count": "components",
}


def _readiness_spec_from_payload(node: Mapping[str, Any]) -> SimpleNamespace:
    readiness = node.get("readiness")
    readiness = readiness if isinstance(readiness, Mapping) else {}
    displayed_ports = {
        str(port.get("key", "") or "").strip(): port
        for port in node.get("ports", ())
        if isinstance(port, Mapping)
    }
    readiness_ports = readiness.get("ports")
    readiness_ports = (
        readiness_ports
        if isinstance(readiness_ports, (list, tuple))
        else node.get("ports", ())
    )
    ports = tuple(
        SimpleNamespace(
            key=str(port.get("key", "") or "").strip(),
            label=str(port.get("label", "") or port.get("key", "")).strip(),
            direction=str(port.get("direction", "") or "").strip(),
            kind=str(port.get("kind", "") or "").strip(),
            required=(
                str(port.get("direction", "") or "").strip().lower() == "in"
                and str(port.get("kind", "") or "").strip().lower() == "data"
                and (
                    port.get("required") is True
                    if "required" in port
                    else not bool(port.get("optional", False))
                )
                and not bool(
                    displayed_ports.get(
                        str(port.get("key", "") or "").strip(), {}
                    ).get("locked", False)
                )
                and not bool(
                    displayed_ports.get(
                        str(port.get("key", "") or "").strip(), {}
                    ).get("inactive", False)
                )
            ),
            uses_property_default=bool(
                port.get("uses_property_default", False)
                or port.get("default_property") is not None
            ),
            allow_empty_string=bool(port.get("allow_empty_string", False)),
        )
        for port in readiness_ports
        if isinstance(port, Mapping)
        and str(port.get("key", "") or "").strip()
    )
    property_labels = readiness.get("property_labels")
    property_labels = property_labels if isinstance(property_labels, Mapping) else {}
    properties = tuple(
        SimpleNamespace(key=str(key), label=str(label or key))
        for key, label in property_labels.items()
    )
    requirements = tuple(
        SimpleNamespace(
            any_of_ports=tuple(
                str(key) for key in raw_requirement.get("any_of_ports", ())
            ),
            any_of_properties=tuple(
                str(key) for key in raw_requirement.get("any_of_properties", ())
            ),
            when_ports_present=tuple(
                str(key) for key in raw_requirement.get("when_ports_present", ())
            ),
            when_properties=tuple(
                SimpleNamespace(
                    property_key=str(condition.get("property_key", "") or ""),
                    values=tuple(condition.get("values", ())),
                )
                for condition in raw_requirement.get("when_properties", ())
                if isinstance(condition, Mapping)
            ),
        )
        for raw_requirement in readiness.get("requirements", ())
        if isinstance(raw_requirement, Mapping)
    )
    return SimpleNamespace(
        ports=ports,
        properties=properties,
        readiness_requirements=requirements,
    )


def _readiness_issues_for_payload(
    node: Mapping[str, Any],
    port_states: Mapping[str, str],
    *,
    port_has_value: Mapping[str, bool] | None = None,
    overridden_port_keys: set[str] | None = None,
) -> tuple[Any, ...]:
    ports = node.get("ports", ())
    if port_has_value is None:
        port_has_value = {
            str(port.get("key", "") or "").strip(): str(
                port_states.get(str(port.get("key", "") or "").strip(), "") or ""
            ).strip().lower()
            in {"flowing", "invalid"}
            for port in (ports if isinstance(ports, (list, tuple)) else ())
            if isinstance(port, Mapping)
            and str(port.get("key", "") or "").strip()
        }
    if overridden_port_keys is None:
        overridden_port_keys = {
            str(port.get("key", "") or "").strip()
            for port in (ports if isinstance(ports, (list, tuple)) else ())
            if isinstance(port, Mapping)
            and isinstance(port.get("default_property"), Mapping)
            and bool(port["default_property"].get("overridden_by_input", False))
        }
    properties = node.get("properties")
    return evaluate_node_readiness(
        _readiness_spec_from_payload(node),
        port_has_value=port_has_value,
        overridden_port_keys=overridden_port_keys,
        properties=properties if isinstance(properties, Mapping) else {},
    )


def _bounded_preview_text(value: str) -> str:
    safe_characters: list[str] = []
    scan_count = min(len(value), _PREVIEW_TEXT_SCAN_LIMIT)
    truncated = len(value) > scan_count
    for index in range(scan_count):
        character = value[index]
        if unicodedata.category(character).startswith("C"):
            continue
        safe_characters.append(character)
        if len(safe_characters) >= _PREVIEW_SAMPLE_LIMIT:
            truncated = index + 1 < len(value)
            break
    sample = "".join(safe_characters)
    sample = " ".join(sample.split())
    if truncated:
        return sample[: _PREVIEW_SAMPLE_LIMIT - 1] + "\u2026"
    return sample


def _empty_rich_preview() -> dict[str, Any]:
    return {
        "kind": "none",
        "text": "",
        "swatches": [],
        "thumbnail_ref": "",
    }


def _text_rich_preview(text: str) -> dict[str, Any]:
    bounded = _bounded_preview_text(text)
    return {
        "kind": "text" if bounded else "none",
        "text": bounded,
        "swatches": [],
        "thumbnail_ref": "",
    }


def _bounded_preview_label(value: str, limit: int) -> str:
    safe = _bounded_preview_text(value)
    return safe if len(safe) <= limit else safe[: limit - 1] + "\u2026"


def _preview_vector3(value: object) -> tuple[float, float, float] | None:
    if type(value) is not list or len(value) != 3:
        return None
    numbers: list[float] = []
    for item in value:
        if type(item) not in {int, float}:
            return None
        try:
            number = float(item)
        except OverflowError:
            return None
        if not math.isfinite(number):
            return None
        numbers.append(number)
    return numbers[0], numbers[1], numbers[2]


def _plane_preview_origin(payload: object) -> tuple[float, float, float] | None:
    if (
        type(payload) is not dict
        or len(payload) != 3
        or not all(key in payload for key in ("origin", "axes", "normal"))
    ):
        return None
    origin = _preview_vector3(payload["origin"])
    axes = payload["axes"]
    normal = _preview_vector3(payload["normal"])
    if type(axes) is not list or len(axes) != 2:
        return None
    x_axis = _preview_vector3(axes[0])
    y_axis = _preview_vector3(axes[1])
    if None in {origin, x_axis, y_axis, normal}:
        return None
    assert origin is not None and x_axis is not None
    assert y_axis is not None and normal is not None

    def dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=True))

    if any(
        not math.isclose(dot(vector, vector), 1.0, rel_tol=0.0, abs_tol=1.0e-9)
        for vector in (x_axis, y_axis, normal)
    ) or any(
        not math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1.0e-9)
        for value in (
            dot(x_axis, y_axis),
            dot(x_axis, normal),
            dot(y_axis, normal),
        )
    ):
        return None
    cross = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )
    if any(
        not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-9)
        for actual, expected in zip(cross, normal, strict=True)
    ):
        return None
    return origin


def _inline_value_preview(
    value: TypedInlineValue,
) -> tuple[str, dict[str, Any]] | None:
    payload = value.payload
    if value.data_type_id == "COREX.Mechanical.CameraView":
        if type(payload) is not dict:
            return None
        kind = payload.get("kind")
        name = payload.get("name")
        index = payload.get("index")
        if (
            kind not in {"saved", "current"}
            or type(name) is not str
            or not name
            or (kind == "saved" and (type(index) is not int or index < 0))
            or (kind == "current" and index is not None)
        ):
            return None
        suffix = f" (saved index {index})" if kind == "saved" else ""
        text = _bounded_preview_text(f"Mechanical Camera View: {name}{suffix}")
        return text, _text_rich_preview(text)
    if value.data_type_id == "COREX.DataTypes.Plane":
        origin = _plane_preview_origin(payload)
        if origin is None:
            return None
        text = (
            "Plane origin: (" + ", ".join(format(item, ".12g") for item in origin) + ")"
        )
        return text, _text_rich_preview(text)

    if value.data_type_id == "COREX.DataTypes.ColorMap":
        if (
            type(payload) is not list
            or not 1 <= len(payload) <= 256
            or any(
                type(color) is not str
                or len(color) != 9
                or color[0] != "#"
                or any(
                    character not in "0123456789abcdefABCDEF" for character in color[1:]
                )
                for color in payload
            )
        ):
            return None
        text = f"COREX Color Map: {len(payload)} color"
        if len(payload) != 1:
            text += "s"
        return text, {
            "kind": "swatches",
            "text": text,
            "swatches": list(payload[:_PREVIEW_ITEM_LIMIT]),
            "thumbnail_ref": "",
        }

    if value.data_type_id == "COREX.DataTypes.NodeVisual":
        if (
            type(payload) is not dict
            or len(payload) != 1
            or "node_refs" not in payload
            or type(payload["node_refs"]) is not list
            or len(payload["node_refs"]) > 256
            or any(
                type(reference) is not str
                or not 0 < len(reference) <= 128
                or reference.strip() != reference
                or not reference.isprintable()
                for reference in payload["node_refs"]
            )
        ):
            return None
        references = payload["node_refs"]
        text = f"Node Visual: {len(references)} node reference"
        if len(references) != 1:
            text += "s"
        if references:
            sample = ", ".join(
                _bounded_preview_label(reference, 24) for reference in references[:4]
            )
            suffix = ", \u2026" if len(references) > 4 else ""
            text += f" ({sample}{suffix})"
        text = _bounded_preview_text(text)
        return text, _text_rich_preview(text)

    if value.data_type_id == "COREX.DataTypes.MultiAgentSystem.AgentModel":
        if (
            type(payload) is not dict
            or len(payload) != 2
            or not all(key in payload for key in ("provider_id", "model_id"))
        ):
            return None
        provider = payload["provider_id"]
        model = payload["model_id"]
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/+-"
        if any(
            type(identifier) is not str
            or not 0 < len(identifier) <= maximum
            or identifier.strip() != identifier
            or identifier[0] not in allowed[:62]
            or any(character not in allowed for character in identifier)
            for identifier, maximum in ((provider, 128), (model, 256))
        ):
            return None
        text = (
            "Agent Model: provider="
            + _bounded_preview_label(provider, 56)
            + ", model="
            + _bounded_preview_label(model, 72)
        )
        text = _bounded_preview_text(text)
        return text, _text_rich_preview(text)
    return None


def _safe_handle_metadata_parts(metadata: object) -> list[str]:
    if type(metadata) is not dict:
        return []
    parts: list[str] = []
    for key, label in _SAFE_HANDLE_METADATA_LABELS.items():
        value = metadata.get(key)
        if type(value) is not int or value < 0 or value > _PREVIEW_INTEGER_LIMIT:
            continue
        rendered = str(value)
        parts.append(f"{label}: {rendered}")
    return parts


def _validated_runtime_carrier(
    value: TypedInlineValue | ImageValue | RuntimeHandleRef | RuntimeArtifactRef,
    data_types: DataTypeCatalog | None,
) -> tuple[str, str, str] | None:
    carrier_kind = {
        TypedInlineValue: "inline",
        ImageValue: "inline",
        RuntimeHandleRef: "handle",
        RuntimeArtifactRef: "artifact",
    }.get(type(value))
    if carrier_kind is None or type(data_types) is not DataTypeCatalog:
        return None
    if type(value.data_type_id) is not str or type(value.schema_version) is not int:
        return None
    try:
        specs = object.__getattribute__(data_types, "_types")
    except AttributeError:
        return None
    if type(specs) is not dict:
        return None
    catalog_items = tuple(dict.items(specs))
    if any(type(key) is not str for key, _spec in catalog_items):
        return None
    spec = next(
        (candidate for key, candidate in catalog_items if key == value.data_type_id),
        None,
    )
    if type(spec) is not DataTypeSpec:
        return None
    try:
        spec_type_id = object.__getattribute__(spec, "type_id")
        display_name = object.__getattribute__(spec, "display_name")
        family_id = object.__getattribute__(spec, "family_id")
        abstract = object.__getattribute__(spec, "abstract")
        carriers = object.__getattribute__(spec, "carriers")
        payload_schema_version = object.__getattribute__(
            spec,
            "payload_schema_version",
        )
        sensitivity = object.__getattribute__(spec, "sensitivity")
    except AttributeError:
        return None
    if (
        type(spec_type_id) is not str
        or type(display_name) is not str
        or type(family_id) is not str
        or type(abstract) is not bool
        or type(carriers) is not frozenset
        or type(payload_schema_version) is not int
        or type(sensitivity) is not str
    ):
        return None
    if any(type(item) is not str for item in carriers):
        return None
    if (
        spec_type_id != value.data_type_id
        or abstract
        or carrier_kind not in carriers
        or value.schema_version != payload_schema_version
        or sensitivity != "normal"
    ):
        return None
    return carrier_kind, display_name, family_id


def _runtime_carrier_preview(
    value: TypedInlineValue | ImageValue | RuntimeHandleRef | RuntimeArtifactRef,
    data_types: DataTypeCatalog | None,
) -> tuple[str, dict[str, Any]]:
    validated = _validated_runtime_carrier(value, data_types)
    if validated is None:
        return "Value unavailable", _empty_rich_preview()
    carrier_kind, display_name, family_id = validated
    label = _bounded_preview_text(display_name) or "Typed value"
    if type(value) is ImageValue:
        text = f"{label}: {value.width} x {value.height} PNG"
        return text, {
            "kind": "thumbnail",
            "text": text,
            "swatches": [],
            "thumbnail_ref": image_value_preview_source(value),
        }
    if carrier_kind == "inline" and value.data_type_id in _INLINE_VALUE_DATA_TYPE_IDS:
        preview = _inline_value_preview(value)
        return (
            preview
            if preview is not None
            else ("Value unavailable", _empty_rich_preview())
        )
    if carrier_kind == "handle":
        if family_id not in _SAFE_HANDLE_PREVIEW_FAMILIES:
            return f"{label} value", _empty_rich_preview()
        parts = _safe_handle_metadata_parts(value.metadata)
        text = _bounded_preview_text(f"{label}: {', '.join(parts)}" if parts else label)
        return text, _text_rich_preview(text)
    if carrier_kind == "artifact":
        text = _bounded_preview_text(f"{label} artifact")
        return text, _text_rich_preview(text)
    return f"{label} value", _empty_rich_preview()


def _safe_preview_projection_impl(
    value: object,
    *,
    data_types: DataTypeCatalog | None,
    depth: int = 0,
    active_container_ids: set[int] | None = None,
) -> tuple[str, dict[str, Any]]:
    value_type = type(value)
    if value_type is dict:
        marker = next(
            (
                item
                for key, item in dict.items(value)
                if type(key) is str and key == "__ea_runtime_value__"
            ),
            None,
        )
        if type(marker) is str and marker in _SENSITIVE_RUNTIME_MARKERS:
            return "Value unavailable", _empty_rich_preview()
    if value_type in {TypedInlineValue, ImageValue, RuntimeHandleRef, RuntimeArtifactRef}:
        return _runtime_carrier_preview(value, data_types)
    if value is None:
        return "None", _text_rich_preview("None")
    if value_type is bool:
        text = "True" if value else "False"
        return text, _text_rich_preview(text)
    if value_type is int:
        if abs(value) > _PREVIEW_INTEGER_LIMIT:
            return "Number unavailable", _empty_rich_preview()
        text = str(value)
        return text, _text_rich_preview(text)
    if value_type is float:
        if not math.isfinite(value):
            return "Number unavailable", _empty_rich_preview()
        text = format(value, ".12g")
        return text, _text_rich_preview(text)
    if value_type is str:
        text = _bounded_preview_text(value)
        return text, _text_rich_preview(text)
    if value_type not in {list, tuple, dict}:
        return "Unsupported value", _empty_rich_preview()
    if depth >= _PREVIEW_CONTAINER_DEPTH_LIMIT:
        text = "{\u2026}" if value_type is dict else "[\u2026]"
        return text, _text_rich_preview(text)

    active_container_ids = (
        active_container_ids if active_container_ids is not None else set()
    )
    identity = id(value)
    if identity in active_container_ids:
        return "Recursive value", _empty_rich_preview()
    active_container_ids.add(identity)
    try:
        child_texts: list[str] = []
        all_children_rich = True
        if value_type is dict:
            item_count = len(value)
            for index, (key, item) in enumerate(value.items()):
                if index >= _PREVIEW_ITEM_LIMIT:
                    break
                key_text, key_rich = _safe_preview_projection_impl(
                    key,
                    data_types=data_types,
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
                item_text, item_rich = _safe_preview_projection_impl(
                    item,
                    data_types=data_types,
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
                child_texts.append(f"{key_text}: {item_text}")
                all_children_rich = all_children_rich and all(
                    preview["kind"] == "text" for preview in (key_rich, item_rich)
                )
            if item_count > _PREVIEW_ITEM_LIMIT:
                child_texts.append("\u2026")
            text = _bounded_preview_text("{" + ", ".join(child_texts) + "}")
        else:
            item_count = len(value)
            for index in range(min(item_count, _PREVIEW_ITEM_LIMIT)):
                child_text, child_rich = _safe_preview_projection_impl(
                    value[index],
                    data_types=data_types,
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
                child_texts.append(child_text)
                all_children_rich = all_children_rich and child_rich["kind"] == "text"
            if item_count > _PREVIEW_ITEM_LIMIT:
                child_texts.append("\u2026")
            opening, closing = ("(", ")") if value_type is tuple else ("[", "]")
            text = _bounded_preview_text(opening + ", ".join(child_texts) + closing)
        return (
            text,
            _text_rich_preview(text) if all_children_rich else _empty_rich_preview(),
        )
    finally:
        active_container_ids.remove(identity)


def _safe_preview_projection(
    value: object,
    *,
    data_types: DataTypeCatalog | None,
) -> tuple[str, dict[str, Any]]:
    try:
        return _safe_preview_projection_impl(value, data_types=data_types)
    except Exception:
        return "Value unavailable", _empty_rich_preview()


def _bounded_sample(
    value: object,
    *,
    data_types: DataTypeCatalog | None = None,
) -> str:
    """Return one bounded, callback-free display sample."""
    return _safe_preview_projection(value, data_types=data_types)[0]


def _bounded_row_sample(
    value: object,
    *,
    data_types: DataTypeCatalog | None = None,
) -> str:
    return _bounded_sample(value, data_types=data_types)


def _item_preview_lines(
    value: DataTree,
    *,
    data_types: DataTypeCatalog | None,
) -> list[str]:
    for _path, items in value.branches[:_PREVIEW_ITEM_LIMIT]:
        if items:
            return [_bounded_sample(items[0], data_types=data_types)]
    return ["Empty"]


def _list_preview_lines(
    value: DataTree,
    *,
    data_types: DataTypeCatalog | None,
) -> list[str]:
    item_count = value.item_count
    samples: list[object] = []
    for _path, items in value.branches[:_PREVIEW_ITEM_LIMIT]:
        if len(samples) >= _PREVIEW_ITEM_LIMIT:
            break
        samples.extend(items[: _PREVIEW_ITEM_LIMIT - len(samples)])
    lines = [f"List: {item_count} item" + ("" if item_count == 1 else "s")]
    lines.extend(
        f"[{index}] {_bounded_sample(item, data_types=data_types)}"
        for index, item in enumerate(samples)
    )
    return lines


def _format_data_path(path: object) -> str:
    if type(path) not in {list, tuple}:
        return "{}"
    parts = [
        str(index)
        for index in path[:_PREVIEW_ITEM_LIMIT]
        if type(index) is int and abs(index) <= _PREVIEW_INTEGER_LIMIT
    ]
    if len(path) > _PREVIEW_ITEM_LIMIT:
        parts.append("\u2026")
    return "{" + ";".join(parts) + "}"


def _tree_preview_lines(
    value: DataTree,
    *,
    data_types: DataTypeCatalog | None,
) -> list[str]:
    branch_count = value.branch_count
    item_count = value.item_count
    if not branch_count:
        return ["Tree: 0 branches, 0 items"]
    lines = [
        f"Tree: {branch_count} branch"
        + ("" if branch_count == 1 else "es")
        + f", {item_count} item"
        + ("" if item_count == 1 else "s")
    ]
    for path, items in value.branches[:_PREVIEW_ITEM_LIMIT]:
        lines.append(_format_data_path(path))
        lines.extend(
            f"  [{index}] {_bounded_sample(item, data_types=data_types)}"
            for index, item in enumerate(items[:_PREVIEW_ITEM_LIMIT])
        )
    return lines


def _tree_preview_rows(
    value: DataTree,
    *,
    data_types: DataTypeCatalog | None,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    truncated = value.branch_count > _PREVIEW_ITEM_LIMIT
    for path, items in value.branches[:_PREVIEW_ITEM_LIMIT]:
        path_text = _format_data_path(path)[1:-1]
        rows.append({"kind": "branch", "path": path_text})
        rows.extend(
            {
                "kind": "item",
                "path": path_text,
                "index": index,
                "text": _bounded_row_sample(item, data_types=data_types),
            }
            for index, item in enumerate(items[:_PREVIEW_ITEM_LIMIT])
        )
        truncated = truncated or len(items) > _PREVIEW_ITEM_LIMIT
    return rows, truncated


def _preview_lines(
    value: DataTree,
    access: str,
    *,
    data_types: DataTypeCatalog | None,
) -> list[str]:
    if access == "tree":
        return _tree_preview_lines(value, data_types=data_types)
    if access == "list":
        return _list_preview_lines(value, data_types=data_types)
    return _item_preview_lines(value, data_types=data_types)


def _rich_preview_for_tree(
    value: DataTree,
    *,
    data_types: DataTypeCatalog | None,
) -> dict[str, Any]:
    for _path, items in value.branches[:_PREVIEW_ITEM_LIMIT]:
        if not items:
            continue
        return _safe_preview_projection(items[0], data_types=data_types)[1]
    return _empty_rich_preview()


def _latest_output_record(records: object) -> Mapping[str, Any] | None:
    if not isinstance(records, Mapping):
        return None
    latest: Mapping[str, Any] | None = None
    latest_observed_at = float("-inf")
    for record in records.values():
        if not isinstance(record, Mapping):
            continue
        try:
            observed_at = float(record.get("observed_at_epoch_ms", 0.0) or 0.0)
        except (TypeError, ValueError):
            observed_at = 0.0
        if latest is None or observed_at >= latest_observed_at:
            latest = record
            latest_observed_at = observed_at
    return latest


def _readiness_input_facts(
    *,
    node_payloads: object,
    edge_payloads: object,
    output_records_by_node: object,
) -> tuple[dict[str, dict[str, bool]], dict[str, set[str]]]:
    records_by_node = (
        output_records_by_node
        if isinstance(output_records_by_node, Mapping)
        else {}
    )
    output_presence: dict[tuple[str, str], tuple[bool, bool]] = {}
    for raw_node_id, records in records_by_node.items():
        node_id = normalize_node_id(raw_node_id)
        latest = _latest_output_record(records)
        outputs = latest.get("outputs") if latest is not None else None
        if (
            not node_id
            or latest is None
            or not bool(latest.get("outputs_available", True))
            or bool(latest.get("stale", False))
            or not isinstance(outputs, Mapping)
        ):
            continue
        for raw_port_key, result in outputs.items():
            port_key = str(raw_port_key or "").strip()
            if (
                not port_key
                or not isinstance(result, SettledPortResult)
                or str(result.status).strip().lower() != "value"
                or not isinstance(result.value, DataTree)
            ):
                continue
            ordinary_present = False
            empty_string_present = False
            for _path, items in result.value.branches:
                for item in items:
                    if readiness_value_is_present(item):
                        ordinary_present = True
                        break
                    if isinstance(item, str) and item == "":
                        empty_string_present = True
                if ordinary_present:
                    break
            output_presence[(node_id, port_key)] = (
                ordinary_present,
                empty_string_present,
            )

    allow_empty_targets = {
        (normalize_node_id(node.get("node_id")), str(port.get("key", "") or "").strip())
        for node in (node_payloads if isinstance(node_payloads, (list, tuple)) else ())
        if isinstance(node, Mapping)
        for port in node.get("readiness", {}).get("ports", ())
        if isinstance(port, Mapping) and bool(port.get("allow_empty_string", False))
    }

    presence_by_node: dict[str, dict[str, bool]] = {}
    overridden_by_node: dict[str, set[str]] = {}
    for edge in edge_payloads if isinstance(edge_payloads, (list, tuple)) else ():
        if not isinstance(edge, Mapping) or not bool(edge.get("enabled", True)):
            continue
        source_node_id = normalize_node_id(edge.get("source_node_id"))
        source_port_key = str(edge.get("source_port_key", "") or "").strip()
        target_node_id = normalize_node_id(edge.get("target_node_id"))
        target_port_key = str(edge.get("target_port_key", "") or "").strip()
        if not all((source_node_id, source_port_key, target_node_id, target_port_key)):
            continue
        overridden_by_node.setdefault(target_node_id, set()).add(target_port_key)
        target_presence = presence_by_node.setdefault(target_node_id, {})
        target_presence[target_port_key] = bool(
            target_presence.get(target_port_key, False)
            or edge.get("data_type_warning", False)
            or edge.get("availability_warning", False)
            or output_presence.get((source_node_id, source_port_key), (False, False))[0]
            or (
                (target_node_id, target_port_key) in allow_empty_targets
                and output_presence.get((source_node_id, source_port_key), (False, False))[1]
            )
        )
    return presence_by_node, overridden_by_node


def _property_presentations_by_key(
    node: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    items: list[Mapping[str, Any]] = []
    inline_properties = node.get("inline_properties")
    if isinstance(inline_properties, (list, tuple)):
        items.extend(item for item in inline_properties if isinstance(item, Mapping))
    settings_groups = node.get("settings_groups")
    if isinstance(settings_groups, (list, tuple)):
        for group in settings_groups:
            if not isinstance(group, Mapping):
                continue
            group_items = group.get("items")
            if not isinstance(group_items, (list, tuple)):
                continue
            items.extend(
                property_item
                for item in group_items
                if isinstance(item, Mapping)
                and isinstance((property_item := item.get("property")), Mapping)
            )
    ports = node.get("ports")
    if isinstance(ports, (list, tuple)):
        items.extend(
            property_item
            for port in ports
            if isinstance(port, Mapping)
            and isinstance((property_item := port.get("default_property")), Mapping)
        )
    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        property_key = str(item.get("key", "") or "").strip()
        if property_key and property_key not in lookup:
            lookup[property_key] = dict(item)
    return lookup


def _enabled_incoming_edges_by_port(
    edge_payloads: object,
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    lookup: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for edge in edge_payloads if isinstance(edge_payloads, (list, tuple)) else ():
        if not isinstance(edge, Mapping) or not bool(edge.get("enabled", True)):
            continue
        node_id = normalize_node_id(edge.get("target_node_id"))
        port_key = str(edge.get("target_port_key", "") or "").strip()
        if node_id and port_key:
            lookup.setdefault((node_id, port_key), []).append(edge)
    return lookup


def _settled_edge_item(
    edge: Mapping[str, Any],
    *,
    output_records_by_node: Mapping[str, Any],
) -> tuple[bool, object | None]:
    if bool(edge.get("data_type_warning", False)) or bool(
        edge.get("availability_warning", False)
    ):
        return False, None
    source_node_id = normalize_node_id(edge.get("source_node_id"))
    source_port_key = str(edge.get("source_port_key", "") or "").strip()
    latest = _latest_output_record(output_records_by_node.get(source_node_id, {}))
    outputs = latest.get("outputs") if latest is not None else None
    result = outputs.get(source_port_key) if isinstance(outputs, Mapping) else None
    if (
        not source_node_id
        or not source_port_key
        or latest is None
        or bool(latest.get("stale", False))
        or not isinstance(result, SettledPortResult)
        or str(result.status).strip().lower() != "value"
        or not isinstance(result.value, DataTree)
        or result.value.item_count != 1
    ):
        return False, None
    for _path, branch_items in result.value.branches:
        if branch_items:
            return True, branch_items[0]
    return False, None


def _effective_property_presentation(
    *,
    node_id: str,
    property_item: Mapping[str, Any],
    incoming_by_port: Mapping[tuple[str, str], list[Mapping[str, Any]]],
    output_records_by_node: Mapping[str, Any],
) -> dict[str, Any]:
    property_key = str(property_item.get("key", "") or "").strip()
    candidate_keys = property_item.get("override_input_port_keys")
    candidate_keys = (
        tuple(str(key) for key in candidate_keys if str(key))
        if isinstance(candidate_keys, (list, tuple))
        else (property_key,) if property_key else ()
    )
    overriding_port_key = ""
    incoming: list[Mapping[str, Any]] = []
    for port_key in candidate_keys:
        incoming = incoming_by_port.get((node_id, port_key), [])
        if incoming:
            overriding_port_key = port_key
            break

    presentation = copy.deepcopy(dict(property_item))
    overridden = bool(incoming)
    display_available = not overridden
    display_value = (
        copy.deepcopy(property_item.get("value")) if not overridden else None
    )
    if len(incoming) == 1:
        settled, runtime_value = _settled_edge_item(
            incoming[0], output_records_by_node=output_records_by_node
        )
        if settled:
            display_available, display_value = project_supported_upstream_property_value(
                property_item,
                runtime_value,
            )
    presentation.update(
        {
            "display_value": display_value if display_available else None,
            "display_value_available": bool(display_available),
            "overridden_by_input": overridden,
            "override_input_port_key": overriding_port_key,
            "override_reason": (
                str(property_item.get("override_reason", "") or "")
                if overridden
                else ""
            ),
        }
    )
    return presentation


def resolve_runtime_property_presentations(
    *,
    node_payloads: object,
    edge_payloads: object,
    output_records_by_node: object,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Overlay safe settled input values without touching authored properties."""
    records_by_node = (
        output_records_by_node
        if isinstance(output_records_by_node, Mapping)
        else {}
    )
    incoming_by_port = _enabled_incoming_edges_by_port(edge_payloads)
    lookup: dict[str, dict[str, dict[str, Any]]] = {}
    for node in node_payloads if isinstance(node_payloads, (list, tuple)) else ():
        if not isinstance(node, Mapping):
            continue
        node_id = normalize_node_id(node.get("node_id"))
        if not node_id:
            continue
        property_items = _property_presentations_by_key(node)
        if not property_items:
            continue
        node_lookup = {
            property_key: _effective_property_presentation(
                node_id=node_id,
                property_item=property_item,
                incoming_by_port=incoming_by_port,
                output_records_by_node=records_by_node,
            )
            for property_key, property_item in property_items.items()
        }
        for property_key, property_item in property_items.items():
            presentation = node_lookup[property_key]
            condition = property_item.get("enabled_when")
            adapter_condition_enabled = bool(
                property_item.get("adapter_condition_enabled", True)
            )
            declarative_condition_enabled = True
            if isinstance(condition, Mapping):
                source_key = str(condition.get("property_key", "") or "").strip()
                source_presentation = node_lookup.get(source_key)
                if source_presentation is None:
                    source_presentation = _effective_property_presentation(
                        node_id=node_id,
                        property_item={
                            "key": source_key,
                            "type": str(condition.get("source_type", "") or ""),
                            "value": condition.get("source_value"),
                            "enum_values": list(
                                condition.get("source_enum_values", ())
                            ),
                            "minimum": condition.get("source_minimum"),
                            "maximum": condition.get("source_maximum"),
                            "override_input_port_keys": list(
                                condition.get(
                                    "source_override_input_port_keys", ()
                                )
                            ),
                        },
                        incoming_by_port=incoming_by_port,
                        output_records_by_node=records_by_node,
                    )
                allowed_values = condition.get("values")
                allowed_values = (
                    tuple(allowed_values)
                    if isinstance(allowed_values, (list, tuple))
                    else ()
                )
                declarative_condition_enabled = bool(
                    source_presentation.get("display_value_available", False)
                    and source_presentation.get("display_value") in allowed_values
                )
            condition_enabled = (
                adapter_condition_enabled and declarative_condition_enabled
            )
            canvas_enabled = bool(
                property_item.get("canvas_interaction_enabled", True)
            )
            overridden = bool(presentation.get("overridden_by_input", False))
            condition_reason = str(
                property_item.get("condition_reason", "") or ""
            )
            adapter_reason = str(
                property_item.get("adapter_condition_reason", "") or ""
            )
            presentation.update(
                {
                    "condition_enabled": condition_enabled,
                    "editor_enabled": (
                        canvas_enabled and condition_enabled and not overridden
                    ),
                    "editor_disabled_reason": (
                        "Value supplied by connected input."
                        if overridden
                        else adapter_reason
                        if not adapter_condition_enabled
                        else condition_reason
                        if not declarative_condition_enabled or not canvas_enabled
                        else ""
                    ),
                }
            )
        lookup[node_id] = node_lookup
    return lookup


def _output_preview(
    value: object,
    access: str,
    *,
    stale: bool,
    data_types: DataTypeCatalog | None = None,
) -> dict[str, Any]:
    if not isinstance(value, SettledPortResult):
        return _missing_output_preview(access, never_run=False, stale=stale)
    status = str(value.status).strip().lower()
    if status != "value" or not isinstance(value.value, DataTree):
        label = {"empty": "Empty", "failed": "Failed"}.get(status, "Pending")
        return {
            "state": "stale" if stale else status if status in {"empty", "failed"} else "pending",
            "access": access,
            "tooltip_text": f"Stale\n{label}" if stale else label,
            "rows": [],
            "truncated": False,
            "rich_preview": _empty_rich_preview(),
        }
    tree = value.value
    empty = tree.item_count == 0
    state = "stale" if stale else ("empty" if empty else "current")
    state_label = {"stale": "Stale", "empty": "Empty", "current": "Current"}[state]
    lines = _preview_lines(tree, access, data_types=data_types)
    rows, truncated = _tree_preview_rows(tree, data_types=data_types)
    return {
        "state": state,
        "access": access,
        "tooltip_text": "\n".join([state_label, *lines]),
        "rows": rows,
        "truncated": truncated,
        "rich_preview": _rich_preview_for_tree(tree, data_types=data_types),
    }


def _missing_output_preview(
    access: str, *, never_run: bool, stale: bool = False
) -> dict[str, Any]:
    state = "never" if never_run else ("stale" if stale else "empty")
    label = {"never": "Never run", "stale": "Stale", "empty": "Empty"}[state]
    return {
        "state": state,
        "access": access,
        "tooltip_text": label,
        "rows": [],
        "truncated": False,
        "rich_preview": _empty_rich_preview(),
    }


def _unavailable_output_preview(access: str) -> dict[str, Any]:
    return {
        "state": "unavailable",
        "access": access,
        "tooltip_text": "Unavailable",
        "rows": [],
        "truncated": False,
        "rich_preview": _empty_rich_preview(),
    }


def _lookup_node_ids(lookup: object) -> set[str]:
    if not isinstance(lookup, dict):
        return set()
    return {
        node_id
        for node_id in (
            normalize_node_id(key) for key, active in lookup.items() if active
        )
        if node_id
    }


def _node_ids_from_values(values: object) -> set[str]:
    if not isinstance(values, (set, frozenset, list, tuple)):
        return set()
    return {
        node_id for node_id in (normalize_node_id(value) for value in values) if node_id
    }


class ExecutionStateProps:
    """Execution-state projections: failed/running/completed/warning/fresh-run
    lookups, started-at/elapsed timing, selected-run preview, revisions."""

    failure_highlight_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()
    port_flow_state_changed = pyqtSignal()

    @pyqtProperty("QVariantMap", notify=failure_highlight_changed)
    def failed_node_lookup(self) -> dict[str, bool]:
        execution_source = self._execution_source
        if execution_source is None:
            return {}
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return {}
        failed_node_id = str(getattr(run_state, "failed_node_id", "") or "").strip()
        failed_workspace_id = str(
            getattr(run_state, "failed_workspace_id", "") or ""
        ).strip()
        active_workspace_id = self._active_workspace_id()
        if not failed_node_id or failed_workspace_id != active_workspace_id:
            return {}
        return {failed_node_id: True}

    @pyqtProperty(str, notify=failure_highlight_changed)
    def failed_node_title(self) -> str:
        execution_source = self._execution_source
        if execution_source is None:
            return ""
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return ""
        return str(getattr(run_state, "failed_node_title", "") or "")

    def _active_workspace_id(self) -> str:
        workspace_id = str(
            _source_attr(self._scene_state_source, "workspace_id", "") or ""
        ).strip()
        if workspace_id:
            return workspace_id
        return ""

    def _run_state_lookup(
        self, workspace_attribute_name: str, ids_attribute_name: str
    ) -> dict[str, bool]:
        execution_source = self._execution_source
        if execution_source is None:
            return {}
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return {}
        active_workspace_id = self._active_workspace_id()
        execution_workspace_id = str(
            getattr(run_state, workspace_attribute_name, "") or ""
        ).strip()
        if not active_workspace_id or execution_workspace_id != active_workspace_id:
            return {}
        ids = getattr(run_state, ids_attribute_name, ())
        if not isinstance(ids, (set, frozenset, list, tuple)):
            return {}
        lookup: dict[str, bool] = {}
        for value in ids:
            normalized_value = str(value or "").strip()
            if normalized_value:
                lookup[normalized_value] = True
        return lookup

    def _node_execution_lookup(self, attribute_name: str) -> dict[str, bool]:
        return self._run_state_lookup("node_execution_workspace_id", attribute_name)

    def _node_execution_timing_lookup(self, attribute_name: str) -> dict[str, Any]:
        execution_source = self._execution_source
        if execution_source is None:
            return {}
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return {}
        active_workspace_id = self._active_workspace_id()
        execution_workspace_id = str(
            getattr(run_state, "node_execution_workspace_id", "") or ""
        ).strip()
        if not active_workspace_id or execution_workspace_id != active_workspace_id:
            return {}
        return _copy_dict(getattr(run_state, attribute_name, {}))

    def _active_workspace_lookup(self, attribute_name: str) -> dict[str, Any]:
        execution_source = self._execution_source
        if execution_source is None:
            return {}
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return {}
        active_workspace_id = self._active_workspace_id()
        if not active_workspace_id:
            return {}
        lookup_by_workspace = getattr(run_state, attribute_name, None)
        if not isinstance(lookup_by_workspace, dict):
            return {}
        return _copy_dict(lookup_by_workspace.get(active_workspace_id, {}))

    def _active_workspace_solution_facts(self) -> dict[str, Any]:
        return self._active_workspace_lookup("node_solution_facts_by_workspace_id")

    def _active_workspace_retained_records(
        self, *, current_only: bool = False
    ) -> dict[str, dict[str, dict[str, Any]]]:
        execution_source = self._execution_source
        run_state = (
            getattr(execution_source, "run_state", None)
            if execution_source is not None
            else None
        )
        return retained_output_records_by_node(
            run_state,
            self._active_workspace_id(),
            current_only=current_only,
        )

    def _selected_run_preview_workspace_matches(self) -> bool:
        execution_source = self._execution_source
        if execution_source is None:
            return False
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return False
        active_workspace_id = self._active_workspace_id()
        preview_workspace_id = str(
            getattr(run_state, "selected_run_preview_workspace_id", "") or ""
        ).strip()
        return bool(active_workspace_id and preview_workspace_id == active_workspace_id)

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def running_node_lookup(self) -> dict[str, bool]:
        return self._node_execution_lookup("running_node_ids")

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def completed_node_lookup(self) -> dict[str, bool]:
        return self._node_execution_lookup("completed_node_ids")

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def warning_node_lookup(self) -> dict[str, bool]:
        return self._node_execution_lookup("warning_node_ids")

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def running_node_started_at_ms_lookup(self) -> dict[str, Any]:
        return self._node_execution_timing_lookup(
            "running_node_started_at_epoch_ms_by_node_id"
        )

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def node_elapsed_ms_lookup(self) -> dict[str, Any]:
        return self._active_workspace_lookup("cached_node_elapsed_ms_by_workspace_id")

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def node_run_count_lookup(self) -> dict[str, int]:
        return self._active_workspace_lookup(
            "node_output_run_counts_by_workspace_id"
        )

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def fresh_run_node_lookup(self) -> dict[str, bool]:
        return {
            node_id: True
            for node_id, fact in self._active_workspace_solution_facts().items()
            if str(getattr(getattr(fact, "freshness", ""), "value", ""))
            == "current"
        }

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def node_solution_freshness_lookup(self) -> dict[str, str]:
        return {
            node_id: freshness
            for node_id, fact in self._active_workspace_solution_facts().items()
            if (freshness := str(
                getattr(getattr(fact, "freshness", ""), "value", "")
            ))
            in {"current", "expired"}
        }

    @pyqtProperty("QVariantMap", notify=port_flow_state_changed)
    def property_presentation_lookup(self) -> dict[str, dict[str, dict[str, Any]]]:
        records_by_node = self._active_workspace_retained_records(
            current_only=True
        )
        node_payloads = [
            *(_source_attr(self._scene_state_source, "nodes_model", []) or []),
            *(_source_attr(self._scene_state_source, "backdrop_nodes_model", []) or []),
        ]
        return resolve_runtime_property_presentations(
            node_payloads=node_payloads,
            edge_payloads=_source_attr(self._scene_state_source, "edges_model", []),
            output_records_by_node=records_by_node,
        )

    @pyqtProperty("QVariantMap", notify=port_flow_state_changed)
    def media_panel_source_lookup(self) -> dict[str, dict[str, Any]]:
        project_source = self._project_source
        model = getattr(project_source, "model", None)
        project = getattr(model, "project", None)
        workspaces = getattr(project, "workspaces", {})
        workspace = (
            workspaces.get(self._active_workspace_id())
            if isinstance(workspaces, Mapping)
            else None
        )
        if workspace is None:
            return {}
        execution_source = self._execution_source
        run_state = (
            getattr(execution_source, "run_state", None)
            if execution_source is not None
            else None
        )
        metadata = getattr(project, "metadata", None)
        project_path = str(getattr(project_source, "project_path", "") or "").strip()
        lookup: dict[str, dict[str, Any]] = {}
        for node in getattr(workspace, "nodes", {}).values():
            if str(getattr(node, "type_id", "") or "").strip() != MEDIA_PANEL_TYPE_ID:
                continue
            node_id = normalize_node_id(getattr(node, "node_id", ""))
            if node_id:
                lookup[node_id] = resolve_media_panel_source(
                    node=node,
                    workspace=workspace,
                    run_state=run_state,
                    project_path=project_path or None,
                    project_metadata=metadata if isinstance(metadata, Mapping) else None,
                ).to_qml_payload()
        return lookup

    @pyqtProperty("QVariantMap", notify=port_flow_state_changed)
    def port_flow_state_lookup(self) -> dict[str, dict[str, str]]:
        records_by_node = self._active_workspace_retained_records(current_only=True)
        solution_facts_by_node = self._active_workspace_solution_facts()
        node_payloads = [
            *(_source_attr(self._scene_state_source, "nodes_model", []) or []),
            *(_source_attr(self._scene_state_source, "backdrop_nodes_model", []) or []),
        ]
        edge_payloads = _source_attr(self._scene_state_source, "edges_model", [])
        lookup = resolve_runtime_port_flow_states(
            node_payloads=node_payloads,
            edge_payloads=edge_payloads,
            output_records_by_node=records_by_node,
            solution_facts_by_node=solution_facts_by_node,
        )
        presence_by_node, overridden_by_node = _readiness_input_facts(
            node_payloads=node_payloads,
            edge_payloads=edge_payloads,
            output_records_by_node=records_by_node,
        )
        for node in node_payloads:
            if not isinstance(node, Mapping):
                continue
            node_id = normalize_node_id(node.get("node_id"))
            if not node_id or str(node.get("runtime_behavior", "active")) != "active":
                continue
            node_states = lookup.get(node_id, {})
            input_ports = {
                str(port.get("key", "") or "").strip(): port
                for port in node.get("ports", ())
                if isinstance(port, Mapping)
                and str(port.get("direction", "") or "").strip().lower() == "in"
                and str(port.get("kind", "") or "").strip().lower() == "data"
            }
            for issue in _readiness_issues_for_payload(
                node,
                node_states,
                port_has_value=presence_by_node.get(node_id, {}),
                overridden_port_keys=overridden_by_node.get(node_id, set()),
            ):
                for target_key in issue.target_keys:
                    port = input_ports.get(str(target_key))
                    if (
                        port is not None
                        and not bool(port.get("inactive", False))
                        and node_states.get(str(target_key)) != "invalid"
                    ):
                        node_states[str(target_key)] = "waiting"
        return lookup

    @pyqtProperty("QVariantMap", notify=port_flow_state_changed)
    def port_value_preview_lookup(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Project bounded output summaries from the existing workspace cache."""
        records_by_node = self._active_workspace_retained_records()
        node_payloads = [
            *(_source_attr(self._scene_state_source, "nodes_model", []) or []),
            *(_source_attr(self._scene_state_source, "backdrop_nodes_model", []) or []),
        ]
        registry = getattr(getattr(self, "_scene_bridge", None), "_registry", None)
        data_types = getattr(registry, "data_types", None)
        lookup: dict[str, dict[str, dict[str, Any]]] = {}
        for node in node_payloads:
            if not isinstance(node, Mapping):
                continue
            node_id = normalize_node_id(node.get("node_id"))
            ports = node.get("ports")
            if not node_id or not isinstance(ports, (list, tuple)):
                continue
            latest_record = _latest_output_record(records_by_node.get(node_id, {}))
            outputs = (
                latest_record.get("outputs") if latest_record is not None else None
            )
            stale = bool(latest_record and latest_record.get("stale", False))
            port_lookup: dict[str, dict[str, Any]] = {}
            for port in ports:
                if not isinstance(port, Mapping):
                    continue
                port_key = str(port.get("key", "") or "").strip()
                if (
                    not port_key
                    or str(port.get("direction", "") or "").strip().lower() != "out"
                    or str(port.get("kind", "") or "").strip().lower() != "data"
                ):
                    continue
                access = str(port.get("data_access", "item") or "item").strip().lower()
                if access not in {"item", "list", "tree"}:
                    access = "item"
                if latest_record is not None and not bool(
                    latest_record.get("outputs_available", True)
                ):
                    preview = _unavailable_output_preview(access)
                elif latest_record is None:
                    preview = _missing_output_preview(access, never_run=True)
                elif not isinstance(outputs, Mapping) or port_key not in outputs:
                    preview = _missing_output_preview(
                        access, never_run=False, stale=stale
                    )
                else:
                    preview = _output_preview(
                        outputs[port_key],
                        access,
                        stale=stale,
                        data_types=data_types,
                    )
                port_lookup[port_key] = preview
            if port_lookup:
                lookup[node_id] = port_lookup
        return lookup

    def _current_panel_tree(self, node_id: str) -> DataTree | None:
        normalized_node_id = normalize_node_id(node_id)
        records_by_node = self._active_workspace_retained_records(
            current_only=True
        )
        latest_record = _latest_output_record(
            records_by_node.get(normalized_node_id, {})
            if normalized_node_id
            else {}
        )
        outputs = latest_record.get("outputs") if latest_record is not None else None
        output = outputs.get("output") if isinstance(outputs, Mapping) else None
        if (
            latest_record is None
            or bool(latest_record.get("stale", False))
            or not isinstance(output, SettledPortResult)
            or str(output.status).strip().lower() != "value"
            or not isinstance(output.value, DataTree)
        ):
            return None
        return output.value

    @pyqtSlot(str, result="QVariantList")
    def panel_display_rows(self, node_id: str) -> list[dict[str, Any]]:
        """Return the complete current Panel tree for its scrollable table."""
        tree = self._current_panel_tree(node_id)
        if tree is None:
            return []
        registry = getattr(getattr(self, "_scene_bridge", None), "_registry", None)
        data_types = getattr(registry, "data_types", None)
        rows: list[dict[str, Any]] = []
        for path, items in tree.branches:
            path_text = _format_data_path(path)[1:-1]
            rows.append({"kind": "branch", "path": path_text})
            rows.extend(
                {
                    "kind": "item",
                    "path": path_text,
                    "index": index,
                    "text": _bounded_sample(item, data_types=data_types),
                }
                for index, item in enumerate(items)
            )
        return rows

    @pyqtSlot(str, bool, result=str)
    def panel_copy_text(self, node_id: str, as_tree: bool) -> str:
        """Return the current Panel output as native-clipboard-friendly text."""
        tree = self._current_panel_tree(node_id)
        if tree is None:
            return ""
        registry = getattr(getattr(self, "_scene_bridge", None), "_registry", None)
        data_types = getattr(registry, "data_types", None)
        lines: list[str] = []
        for path, items in tree.branches:
            if as_tree:
                lines.append(f"* {_format_data_path(path)[1:-1]}")
            lines.extend(_bounded_sample(item, data_types=data_types) for item in items)
        return "\n".join(lines)

    @pyqtProperty("QVariantMap", notify=port_flow_state_changed)
    def node_diagnostic_lookup(self) -> dict[str, dict[str, Any]]:
        warning_messages_by_node = self._active_workspace_lookup(
            "runtime_warning_messages_by_workspace_id"
        )
        port_states_by_node = self.port_flow_state_lookup
        node_payloads = [
            *(_source_attr(self._scene_state_source, "nodes_model", []) or []),
            *(_source_attr(self._scene_state_source, "backdrop_nodes_model", []) or []),
        ]
        records_by_node = self._active_workspace_retained_records(
            current_only=True
        )
        presence_by_node, overridden_by_node = _readiness_input_facts(
            node_payloads=node_payloads,
            edge_payloads=_source_attr(self._scene_state_source, "edges_model", []),
            output_records_by_node=records_by_node,
        )
        lookup: dict[str, dict[str, Any]] = {}
        for node in node_payloads:
            if not isinstance(node, dict):
                continue
            node_id = normalize_node_id(node.get("node_id"))
            if not node_id or str(node.get("runtime_behavior", "active")) != "active":
                continue
            node_states = port_states_by_node.get(node_id, {})
            rows: list[dict[str, Any]] = []
            seen_rows: set[tuple[str, str, str]] = set()
            port_keys = {
                str(port.get("key", "") or "").strip()
                for port in node.get("ports", ())
                if isinstance(port, Mapping)
            }
            for issue in _readiness_issues_for_payload(
                node,
                node_states,
                port_has_value=presence_by_node.get(node_id, {}),
                overridden_port_keys=overridden_by_node.get(node_id, set()),
            ):
                target_keys = tuple(str(key) for key in issue.target_keys)
                target_labels = tuple(str(label) for label in issue.target_labels)
                port_key = next((key for key in target_keys if key in port_keys), "")
                port_label = (
                    target_labels[target_keys.index(port_key)] if port_key else ""
                )
                message = str(issue.message).strip()
                row_key = (str(issue.code), port_key, message)
                if row_key not in seen_rows:
                    seen_rows.add(row_key)
                    rows.append(
                        {
                            "severity": "warning",
                            "code": str(issue.code),
                            "port_key": port_key,
                            "port_label": port_label,
                            "target_keys": list(target_keys),
                            "target_labels": list(target_labels),
                            "message": message,
                        }
                    )
            seen_messages = {row["message"] for row in rows}
            raw_warning_messages = warning_messages_by_node.get(node_id, ())
            if isinstance(raw_warning_messages, str):
                raw_warning_messages = (raw_warning_messages,)
            if isinstance(raw_warning_messages, (list, tuple)):
                for raw_message in raw_warning_messages:
                    message = str(raw_message).strip()
                    if not message or message in seen_messages:
                        continue
                    seen_messages.add(message)
                    rows.append(
                        {
                            "severity": "warning",
                            "code": "runtime_warning",
                            "port_key": "",
                            "port_label": "",
                            "message": message,
                        }
                    )
            if not rows:
                continue
            title = f"{len(rows)} warning" + ("" if len(rows) == 1 else "s")
            lookup[node_id] = {
                "severity": "warning",
                "rows": rows,
                "tooltip_text": "\n".join(
                    [title, *(f"- {row['message']}" for row in rows)]
                ),
            }
        return lookup

    @pyqtProperty("QVariantList", notify=node_execution_state_changed)
    def selected_run_preview_rows(self) -> list[dict[str, Any]]:
        if not self._selected_run_preview_workspace_matches():
            return []
        execution_source = self._execution_source
        run_state = (
            getattr(execution_source, "run_state", None)
            if execution_source is not None
            else None
        )
        rows = (
            getattr(run_state, "selected_run_preview_rows", ())
            if run_state is not None
            else ()
        )
        if not isinstance(rows, (list, tuple)):
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    @pyqtProperty("QVariantMap", notify=node_execution_state_changed)
    def selected_run_preview_node_lookup(self) -> dict[str, str]:
        if not self._selected_run_preview_workspace_matches():
            return {}
        execution_source = self._execution_source
        run_state = (
            getattr(execution_source, "run_state", None)
            if execution_source is not None
            else None
        )
        return _copy_dict(getattr(run_state, "selected_run_preview_node_lookup", {}))

    @pyqtProperty(bool, notify=node_execution_state_changed)
    def selected_run_preview_visible(self) -> bool:
        return bool(self.selected_run_preview_rows)

    @pyqtProperty(int, notify=node_execution_state_changed)
    def selected_run_preview_revision(self) -> int:
        execution_source = self._execution_source
        run_state = (
            getattr(execution_source, "run_state", None)
            if execution_source is not None
            else None
        )
        return (
            int(getattr(run_state, "selected_run_preview_revision", 0))
            if run_state is not None
            else 0
        )

    @pyqtProperty(int, notify=node_execution_state_changed)
    def node_execution_revision(self) -> int:
        execution_source = self._execution_source
        if execution_source is None:
            return 0
        run_state = getattr(execution_source, "run_state", None)
        if run_state is None:
            return 0
        return int(getattr(run_state, "node_execution_revision", 0))
