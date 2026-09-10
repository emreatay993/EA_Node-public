from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ea_node_editor.runtime_contracts import GRAPH_DATA_TYPE_ID

SUBNODE_TYPE_ID = "core.subnode"
SUBNODE_INPUT_TYPE_ID = "core.subnode_input"
SUBNODE_OUTPUT_TYPE_ID = "core.subnode_output"

SUBNODE_PIN_PORT_KEY = "pin"
SUBNODE_PIN_LABEL_PROPERTY = "label"
SUBNODE_PIN_KIND_PROPERTY = "kind"
SUBNODE_PIN_DATA_TYPE_PROPERTY = "data_type"
SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY = "accepted_data_types"
SUBNODE_PIN_DATA_ACCESS_PROPERTY = "data_access"
SUBNODE_PIN_KIND_VALUES = ("data", "flow")
SUBNODE_PIN_DATA_ACCESS_VALUES = ("item", "list", "tree")
SUBNODE_PIN_TYPE_IDS = frozenset({SUBNODE_INPUT_TYPE_ID, SUBNODE_OUTPUT_TYPE_ID})
SUBNODE_AUTHORING_TYPE_IDS = frozenset({SUBNODE_TYPE_ID, *SUBNODE_PIN_TYPE_IDS})


@dataclass(slots=True, frozen=True)
class SubnodePinDefinition:
    pin_type_id: str
    label: str
    kind: str
    data_type: str
    accepted_data_types: tuple[str, ...]
    data_access: str
    pin_port_direction: str
    shell_port_direction: str


def is_subnode_shell_type(type_id: object) -> bool:
    return str(type_id).strip() == SUBNODE_TYPE_ID


def is_subnode_input_type(type_id: object) -> bool:
    return str(type_id).strip() == SUBNODE_INPUT_TYPE_ID


def is_subnode_output_type(type_id: object) -> bool:
    return str(type_id).strip() == SUBNODE_OUTPUT_TYPE_ID


def is_subnode_pin_type(type_id: object) -> bool:
    return str(type_id).strip() in SUBNODE_PIN_TYPE_IDS


def is_subnode_authoring_type(type_id: object) -> bool:
    return str(type_id).strip() in SUBNODE_AUTHORING_TYPE_IDS


def default_subnode_pin_label(pin_type_id: object) -> str:
    return "Input" if is_subnode_input_type(pin_type_id) else "Output"


def normalize_subnode_pin_kind(value: object) -> str:
    normalized = str(value or "data").strip().lower()
    if normalized not in set(SUBNODE_PIN_KIND_VALUES):
        return "data"
    return normalized


def normalize_subnode_pin_data_type(kind: object, value: object) -> str:
    if normalize_subnode_pin_kind(kind) == "flow":
        return GRAPH_DATA_TYPE_ID
    normalized = str(value or GRAPH_DATA_TYPE_ID).strip()
    return normalized or GRAPH_DATA_TYPE_ID


def normalize_subnode_pin_accepted_data_types(
    kind: object,
    data_type: object,
    value: object,
) -> tuple[str, ...]:
    if normalize_subnode_pin_kind(kind) == "flow":
        return ()
    primary = normalize_subnode_pin_data_type(kind, data_type)
    raw_values = (
        value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
        else ()
    )
    normalized: list[str] = []
    seen = {primary}
    for raw_value in raw_values:
        type_id = str(raw_value).strip()
        if not type_id or type_id in seen:
            continue
        normalized.append(type_id)
        seen.add(type_id)
    return tuple(normalized)


def normalize_subnode_pin_data_access(value: object) -> str:
    normalized = str(value or "item").strip().lower()
    return normalized if normalized in SUBNODE_PIN_DATA_ACCESS_VALUES else "item"


def resolve_subnode_pin_definition(
    pin_type_id: object,
    properties: Mapping[str, object] | None = None,
) -> SubnodePinDefinition:
    normalized_type_id = str(pin_type_id).strip()
    if not is_subnode_pin_type(normalized_type_id):
        raise ValueError(f"Unsupported subnode pin type: {pin_type_id!r}")
    raw_properties = properties if properties is not None else {}
    default_label = default_subnode_pin_label(normalized_type_id)
    label = str(raw_properties.get(SUBNODE_PIN_LABEL_PROPERTY, default_label)).strip() or default_label
    kind = normalize_subnode_pin_kind(raw_properties.get(SUBNODE_PIN_KIND_PROPERTY, "data"))
    data_type = normalize_subnode_pin_data_type(
        kind,
        raw_properties.get(SUBNODE_PIN_DATA_TYPE_PROPERTY, GRAPH_DATA_TYPE_ID),
    )
    accepted_data_types = normalize_subnode_pin_accepted_data_types(
        kind,
        data_type,
        raw_properties.get(SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY, ()),
    )
    data_access = normalize_subnode_pin_data_access(
        raw_properties.get(SUBNODE_PIN_DATA_ACCESS_PROPERTY, "item")
    )
    pin_port_direction = "out" if is_subnode_input_type(normalized_type_id) else "in"
    shell_port_direction = "in" if is_subnode_input_type(normalized_type_id) else "out"
    return SubnodePinDefinition(
        pin_type_id=normalized_type_id,
        label=label,
        kind=kind,
        data_type=data_type,
        accepted_data_types=accepted_data_types,
        data_access=data_access,
        pin_port_direction=pin_port_direction,
        shell_port_direction=shell_port_direction,
    )


__all__ = [
    "SUBNODE_AUTHORING_TYPE_IDS",
    "SUBNODE_INPUT_TYPE_ID",
    "SUBNODE_OUTPUT_TYPE_ID",
    "SUBNODE_PIN_DATA_TYPE_PROPERTY",
    "SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY",
    "SUBNODE_PIN_DATA_ACCESS_PROPERTY",
    "SUBNODE_PIN_DATA_ACCESS_VALUES",
    "SUBNODE_PIN_KIND_PROPERTY",
    "SUBNODE_PIN_KIND_VALUES",
    "SUBNODE_PIN_LABEL_PROPERTY",
    "SUBNODE_PIN_PORT_KEY",
    "SUBNODE_PIN_TYPE_IDS",
    "SUBNODE_TYPE_ID",
    "SubnodePinDefinition",
    "default_subnode_pin_label",
    "is_subnode_authoring_type",
    "is_subnode_input_type",
    "is_subnode_output_type",
    "is_subnode_pin_type",
    "is_subnode_shell_type",
    "normalize_subnode_pin_data_type",
    "normalize_subnode_pin_accepted_data_types",
    "normalize_subnode_pin_data_access",
    "normalize_subnode_pin_kind",
    "resolve_subnode_pin_definition",
]
