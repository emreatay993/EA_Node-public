from __future__ import annotations

import copy
import math
from collections.abc import Collection, Mapping
from numbers import Integral, Real
from typing import Any

from ea_node_editor.common.protected_values import secret_public_state
from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.nodes.node_specs import property_has_inline_editor
from ea_node_editor.runtime_contracts import Interval1D


def has_focused_selector(*object_names: str) -> bool:
    """Protect an active selector draft while runtime metadata is refreshed."""
    from PyQt6.QtGui import QGuiApplication

    focused = QGuiApplication.focusObject() if isinstance(QGuiApplication.instance(), QGuiApplication) else None
    while focused is not None:
        if focused.objectName() in object_names:
            return True
        focused = focused.parent()
    return False


_UPSTREAM_TEXT_LIMIT = 4096
_QML_SAFE_INTEGER_LIMIT = (1 << 53) - 1
_DATA_TYPE_LABEL_LIMIT = 160
_ACCEPTED_DATA_TYPE_LABEL_LIMIT = 8


def _bounded_data_type_label(value: object) -> str:
    label = " ".join(str(value or "").split())
    if len(label) <= _DATA_TYPE_LABEL_LIMIT:
        return label
    return label[: _DATA_TYPE_LABEL_LIMIT - 1] + "\u2026"


def build_data_type_ui_projection(data_types: Any) -> dict[str, Any]:
    """Build one compact, fingerprinted type lookup from one catalog snapshot."""
    records = tuple(data_types.snapshot())
    catalog_generation = data_types.fingerprint()
    families = {
        str(record.get("family_id", "")): {
            "label": _bounded_data_type_label(record.get("display_name", "")),
            "color_token": _bounded_data_type_label(record.get("color_token", "")),
            "icon_key": _bounded_data_type_label(record.get("icon_key", "")),
        }
        for record in records
        if record.get("kind") == "family"
    }
    type_items: dict[str, dict[str, str]] = {}
    for record in records:
        if record.get("kind") != "type":
            continue
        type_id = str(record.get("type_id", "") or "").strip()
        if not type_id:
            continue
        family_id = str(record.get("family_id", "") or "").strip()
        family = families.get(family_id, {})
        type_items[type_id] = {
            "label": _bounded_data_type_label(record.get("display_name", type_id)),
            "family": family_id if family else "",
            "family_label": str(family.get("label", "")),
            "color_token": str(family.get("color_token", "")),
            "icon_key": str(family.get("icon_key", "")),
        }
    return {
        "catalog_generation": catalog_generation,
        "types": type_items,
    }


def project_port_data_type_presentation(
    *,
    data_type: object,
    accepted_data_types: Collection[object] = (),
    data_access: object = "item",
    kind: object = "data",
    projection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return bounded per-port type facts without exposing the catalog graph."""
    type_id = str(data_type or "").strip()
    normalized_kind = str(kind or "").strip().lower()
    access = str(data_access or "item").strip().lower()
    if access not in {"item", "list", "tree"}:
        access = "item"
    projection = projection if isinstance(projection, Mapping) else {}
    type_lookup = projection.get("types")
    type_lookup = type_lookup if isinstance(type_lookup, Mapping) else {}
    type_item = type_lookup.get(type_id)
    type_item = type_item if isinstance(type_item, Mapping) else {}
    is_flow = normalized_kind == "flow" or type_id == "flow"
    label = (
        "Flow"
        if is_flow
        else _bounded_data_type_label(type_item.get("label", "") or type_id)
    )
    accepted_labels: list[str] = []
    seen_labels: set[str] = set()
    for accepted_type_id in accepted_data_types:
        normalized_id = str(accepted_type_id or "").strip()
        if not normalized_id:
            continue
        accepted_item = type_lookup.get(normalized_id)
        accepted_item = accepted_item if isinstance(accepted_item, Mapping) else {}
        accepted_label = _bounded_data_type_label(
            accepted_item.get("label", "") or normalized_id
        )
        if accepted_label and accepted_label not in seen_labels:
            seen_labels.add(accepted_label)
            accepted_labels.append(accepted_label)
        if len(accepted_labels) >= _ACCEPTED_DATA_TYPE_LABEL_LIMIT:
            break
    return {
        "data_type": type_id,
        "data_type_label": label,
        "data_type_family": "" if is_flow else str(type_item.get("family", "")),
        "data_type_family_label": (
            "" if is_flow else str(type_item.get("family_label", ""))
        ),
        "data_type_color_token": (
            "" if is_flow else str(type_item.get("color_token", ""))
        ),
        "data_type_icon_key": "" if is_flow else str(type_item.get("icon_key", "")),
        "accepted_data_type_labels": accepted_labels,
        "data_access": access,
        "catalog_generation": str(projection.get("catalog_generation", "")),
    }


def _inside_declared_domain(
    property_item: Mapping[str, Any],
    *values: float | int,
) -> bool:
    minimum = property_item.get("minimum")
    maximum = property_item.get("maximum")
    try:
        return all(
            (minimum is None or value >= float(minimum))
            and (maximum is None or value <= float(maximum))
            for value in values
        )
    except (TypeError, ValueError, OverflowError):
        return False


def qml_safe_property_value(value: Any) -> Any:
    if isinstance(value, Interval1D):
        return {"start": float(value.start), "end": float(value.end)}
    return copy.deepcopy(value)


def qml_safe_spec_property_value(property_spec: Any, value: Any) -> Any:
    if bool(getattr(property_spec, "sensitive", False)):
        return secret_public_state(value)
    return qml_safe_property_value(value)


def project_supported_upstream_property_value(
    property_item: Mapping[str, Any],
    value: object,
) -> tuple[bool, Any]:
    """Return one bounded editor-supported runtime item for QML display."""
    property_type = str(property_item.get("type", "") or "").strip()
    if property_type in {"str", "path"}:
        if not isinstance(value, str) or len(value) > _UPSTREAM_TEXT_LIMIT:
            return False, None
        return True, value
    if property_type == "enum":
        options = tuple(str(option) for option in property_item.get("enum_values", ()))
        if (
            not isinstance(value, str)
            or len(value) > _UPSTREAM_TEXT_LIMIT
            or value not in options
        ):
            return False, None
        return True, value
    if property_type == "bool":
        return (True, value) if isinstance(value, bool) else (False, None)
    if property_type == "int":
        if isinstance(value, bool) or not isinstance(value, Integral):
            return False, None
        try:
            projected = int(value)
        except (TypeError, ValueError, OverflowError):
            return False, None
        if (
            abs(projected) > _QML_SAFE_INTEGER_LIMIT
            or not _inside_declared_domain(property_item, projected)
        ):
            return False, None
        return True, projected
    if property_type == "float":
        if isinstance(value, bool) or not isinstance(value, Real):
            return False, None
        try:
            projected = float(value)
        except (TypeError, ValueError, OverflowError):
            return False, None
        return (
            (True, projected)
            if math.isfinite(projected)
            and _inside_declared_domain(property_item, projected)
            else (False, None)
        )
    if property_type == "interval_1d" and isinstance(value, Interval1D):
        if not _inside_declared_domain(property_item, value.start, value.end):
            return False, None
        return True, qml_safe_property_value(value)
    return False, None


def _inline_property_presentation(
    *,
    node: Any,
    property_key: str,
    property_value: Any,
) -> dict[str, Any]:
    if str(getattr(node, "type_id", "")).strip() != "io.process_run":
        return {}
    if str(property_key).strip() != "output_mode":
        return {}

    output_mode = str(property_value or "memory").strip().lower()
    if output_mode == "stored":
        return {
            "status_chip_text": "Stored transcripts",
            "status_chip_variant": "stored",
            "status_chip_description": "stdout/stderr emit staged artifact refs",
        }
    return {
        "status_chip_text": "Inline capture",
        "status_chip_variant": "memory",
        "status_chip_description": "stdout/stderr stay inline strings",
    }


def _overriding_input_port(
    *,
    node: Any,
    property_key: str,
    resolved_input_ports: Mapping[str, Any],
    enabled_input_port_keys: Collection[str] | None,
    port_connection_counts: Mapping[tuple[str, str], int],
) -> Any | None:
    node_id = str(getattr(node, "node_id", "")).strip()
    candidate_port_keys = (str(property_key).strip(),)
    enabled_keys = (
        {str(key) for key in enabled_input_port_keys}
        if enabled_input_port_keys is not None
        else None
    )
    for port_key in candidate_port_keys:
        port = resolved_input_ports.get(port_key)
        if port is None:
            continue
        if (
            port_key in enabled_keys
            if enabled_keys is not None
            else port_connection_counts.get((node_id, port_key), 0) > 0
        ):
            return port
    return None


def build_property_input_override_state(
    *,
    node: Any,
    property_key: str,
    resolved_input_ports: Mapping[str, Any],
    enabled_input_port_keys: Collection[str] | None = None,
    port_connection_counts: Mapping[tuple[str, str], int] | None = None,
) -> dict[str, Any]:
    candidate_port_keys = tuple(
        key
        for key in (str(property_key).strip(),)
        if key in resolved_input_ports
    )
    overriding_input_port = _overriding_input_port(
        node=node,
        property_key=property_key,
        resolved_input_ports=resolved_input_ports,
        enabled_input_port_keys=enabled_input_port_keys,
        port_connection_counts=port_connection_counts or {},
    )
    return {
        "overridden_by_input": overriding_input_port is not None,
        "override_input_port_key": (
            str(overriding_input_port.key) if overriding_input_port is not None else ""
        ),
        "override_input_port_keys": list(candidate_port_keys),
        "input_port_label": (
            str(overriding_input_port.label or overriding_input_port.key)
            if overriding_input_port is not None
            else ""
        ),
        "override_reason": (
            f"Driven by {str(overriding_input_port.label or overriding_input_port.key).strip()}"
            if overriding_input_port is not None
            else ""
        ),
    }


def _condition_reason(*, source_label: str, allowed_values: tuple[object, ...]) -> str:
    values = [str(value) for value in allowed_values]
    if len(values) == 1:
        requirement = values[0]
    else:
        requirement = "one of " + ", ".join(values)
    return f"Available when {source_label} is {requirement}."


def build_user_facing_node_instance_number(
    *,
    node: Any,
    workflow_nodes: Mapping[str, Any],
) -> int:
    instance_number = 1
    node_type_id = str(getattr(node, "type_id", "")).strip()
    node_id = str(getattr(node, "node_id", "")).strip()
    if not node_type_id or not node_id:
        return instance_number

    matching_count = 0
    for workflow_node in workflow_nodes.values():
        if str(getattr(workflow_node, "type_id", "")).strip() != node_type_id:
            continue
        matching_count += 1
        if str(getattr(workflow_node, "node_id", "")).strip() == node_id:
            return matching_count
    return instance_number


def build_inline_property_items(
    *,
    node: Any,
    spec: Any,
    workspace_nodes: Mapping[str, Any],
    enabled_input_port_keys: Collection[str] | None = None,
    port_connection_counts: Mapping[tuple[str, str], int] | None = None,
) -> list[dict[str, Any]]:
    counts = port_connection_counts or {}
    resolved_input_ports = {
        port.key: port
        for port in effective_ports(node=node, spec=spec, workspace_nodes=workspace_nodes)
        if str(port.direction).strip().lower() == "in" and bool(port.exposed)
    }
    default_property_keys = {
        str(port.key)
        for port in spec.ports
        if str(port.direction).strip().lower() == "in"
        and bool(port.uses_property_default)
    }
    property_by_key = {str(prop.key): prop for prop in spec.properties}
    raw_value_by_key = {
        str(prop.key): node.properties.get(prop.key, prop.default)
        for prop in spec.properties
    }
    override_state_by_key = {
        str(prop.key): build_property_input_override_state(
            node=node,
            property_key=str(prop.key),
            resolved_input_ports=resolved_input_ports,
            enabled_input_port_keys=enabled_input_port_keys,
            port_connection_counts=counts,
        )
        for prop in spec.properties
    }
    items: list[dict[str, Any]] = []
    for prop in spec.properties:
        if not property_has_inline_editor(prop) and str(prop.key) not in default_property_keys:
            continue
        property_value = raw_value_by_key[str(prop.key)]
        qml_value = qml_safe_spec_property_value(prop, property_value)
        override_state = override_state_by_key[str(prop.key)]
        condition = getattr(prop, "enabled_when", None)
        condition_payload = None
        condition_enabled = True
        condition_reason = ""
        if condition is not None:
            source = property_by_key[str(condition.property_key)]
            source_key = str(source.key)
            source_override_state = override_state_by_key[source_key]
            allowed_values = tuple(condition.values)
            condition_enabled = not bool(
                source_override_state["overridden_by_input"]
            ) and raw_value_by_key[source_key] in allowed_values
            condition_reason = _condition_reason(
                source_label=str(source.label or source.key),
                allowed_values=allowed_values,
            )
            condition_payload = {
                "property_key": source_key,
                "property_label": str(source.label or source.key),
                "values": qml_safe_property_value(list(allowed_values)),
                "source_type": str(source.type),
                "source_enum_values": list(source.enum_values),
                "source_minimum": source.minimum,
                "source_maximum": source.maximum,
                "source_value": qml_safe_spec_property_value(
                    source,
                    raw_value_by_key[source_key],
                ),
                "source_override_input_port_keys": list(
                    source_override_state["override_input_port_keys"]
                ),
            }
        overridden = bool(override_state["overridden_by_input"])
        canvas_interaction_enabled = not bool(getattr(node, "locked", False))
        editor_enabled = (
            canvas_interaction_enabled and condition_enabled and not overridden
        )
        items.append(
            {
                "key": prop.key,
                "label": prop.label,
                "help_text": str(
                    getattr(prop, "description", "")
                    or getattr(
                        next(
                            (
                                port
                                for port in resolved_input_ports
                                if str(getattr(port, "key", "")) == str(prop.key)
                            ),
                            None,
                        ),
                        "description",
                        "",
                    )
                    or ""
                ),
                "type": prop.type,
                "value": qml_value,
                "display_value": None if overridden else copy.deepcopy(qml_value),
                "display_value_available": not overridden,
                "enum_values": list(prop.enum_values),
                "enum_codes": list(getattr(prop, "enum_codes", ())),
                "minimum": prop.minimum,
                "maximum": prop.maximum,
                "step": prop.step,
                "inline_editor": prop.inline_editor,
                "sensitive": bool(getattr(prop, "sensitive", False)),
                "sensitive_scope_key": str(
                    getattr(prop, "sensitive_scope_key", "") or ""
                ),
                "file_filter": str(prop.file_filter),
                "searchable": bool(getattr(prop, "searchable", False)),
                "interval_direction": str(
                    getattr(prop, "interval_direction", "") or ""
                ),
                "nullable": bool(getattr(prop, "nullable", False)),
                "list_item_type": str(getattr(prop, "list_item_type", "") or ""),
                "list_item_enum_values": list(
                    getattr(prop, "list_item_enum_values", ())
                ),
                "list_item_enum_codes": list(
                    getattr(prop, "list_item_enum_codes", ())
                ),
                "list_item_minimum": getattr(prop, "list_item_minimum", None),
                "list_item_maximum": getattr(prop, "list_item_maximum", None),
                "list_item_step": getattr(prop, "list_item_step", 0.0),
                "enabled_when": condition_payload,
                "condition_enabled": bool(condition_enabled),
                "condition_reason": condition_reason,
                "canvas_interaction_enabled": canvas_interaction_enabled,
                "editor_enabled": editor_enabled,
                "editor_disabled_reason": (
                    "Value supplied by connected input."
                    if overridden
                    else condition_reason if not condition_enabled else ""
                ),
                **override_state,
                **_inline_property_presentation(
                    node=node,
                    property_key=prop.key,
                    property_value=property_value,
                ),
            }
        )
    return items


__all__ = [
    "build_data_type_ui_projection",
    "build_property_input_override_state",
    "build_inline_property_items",
    "build_user_facing_node_instance_number",
    "project_port_data_type_presentation",
    "project_supported_upstream_property_value",
    "qml_safe_property_value",
    "qml_safe_spec_property_value",
]
