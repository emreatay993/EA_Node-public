# Purpose: Share bounded literal and control-metadata parsing across script and plugin declarations.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_declaration.py

from __future__ import annotations

import ast
import keyword
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from ea_node_editor.nodes.builtins.core_values import (
    COLOR_DATA_TYPE_ID,
    IMAGE_DATA_TYPE_ID,
)
from ea_node_editor.nodes.node_specs import PortSpec, PropertySpec
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
    Interval1D,
    TypedInlineValue,
)

MAX_SOURCE_BYTES = 256 * 1024
MAX_AST_NODES = 20_000
MAX_DECORATORS = 128
MAX_LITERAL_ITEMS = 2_048
MAX_LITERAL_DEPTH = 12
CONTROL_DECORATORS = frozenset(
    {
        "text",
        "number",
        "switch",
        "dropdown",
        "slider",
        "color",
        "path",
        "text_area",
        "interval",
        "list",
    }
)
KNOWN_DECORATORS = CONTROL_DECORATORS | {"node", "input", "output"}
TYPE_ALIASES = {
    "Any": GRAPH_DATA_TYPE_ID,
    "Image": IMAGE_DATA_TYPE_ID,
    "Color": COLOR_DATA_TYPE_ID,
    "Interval": INTERVAL_1D_GRAPH_DATA_TYPE_ID,
}
BUILTIN_TYPES = {
    "bool": BOOLEAN_DATA_TYPE_ID,
    "int": INTEGER_DATA_TYPE_ID,
    "float": DOUBLE_DATA_TYPE_ID,
    "str": STRING_DATA_TYPE_ID,
}
_COMMON_CONTROL_FIELDS = frozenset(
    {"default", "label", "description", "section", "port"}
)
CONTROL_ALLOWED_FIELDS = {
    "text": _COMMON_CONTROL_FIELDS,
    "text_area": _COMMON_CONTROL_FIELDS,
    "color": _COMMON_CONTROL_FIELDS,
    "path": _COMMON_CONTROL_FIELDS | {"file_filter"},
    "number": _COMMON_CONTROL_FIELDS | {"minimum", "maximum", "step"},
    "switch": _COMMON_CONTROL_FIELDS,
    "dropdown": _COMMON_CONTROL_FIELDS | {"options", "codes", "searchable"},
    "slider": _COMMON_CONTROL_FIELDS | {"minimum", "maximum", "step"},
    "interval": _COMMON_CONTROL_FIELDS | {"minimum", "maximum", "step", "direction"},
    "list": _COMMON_CONTROL_FIELDS
    | {"item_type", "options", "codes", "minimum", "maximum", "step"},
}
_INTERNAL_CONTROL_FIELDS = frozenset(
    {
        "_inline_editor",
        "_inspector_editor",
        "_inspector_visible",
        "_persistence_type",
        "_port_accepted_data_types",
        "_port_allow_empty_string",
        "_port_description",
        "_port_label",
        "_port_required",
        "_port_structure",
        "_port_uses_property_default",
        "_port_value_type",
        "_property_default",
        "_property_group",
        "_property_type",
        "_section_order",
        "_sensitive",
        "_sensitive_scope_key",
    }
)
INTERNAL_CONTROL_ALLOWED_FIELDS = {
    name: fields | _INTERNAL_CONTROL_FIELDS
    for name, fields in CONTROL_ALLOWED_FIELDS.items()
}

PROPERTY_TYPES = frozenset(
    {"str", "int", "float", "bool", "path", "enum", "json", "interval_1d"}
)
INLINE_EDITORS = frozenset(
    {
        "",
        "text",
        "number",
        "toggle",
        "enum",
        "path",
        "textarea",
        "color",
        "slider",
        "interval_slider",
        "interval_fields",
        "list",
        "secret",
    }
)
INSPECTOR_EDITORS = frozenset(
    {"", "text", "textarea", "path", "toggle", "enum", "color", "font_family", "secret"}
)
DATA_ACCESS_VALUES = frozenset({"item", "list", "tree"})

FailureFactory = Callable[[ast.AST | None, str], Exception]


class DeclarationValueError(ValueError):
    pass


def corex_decorator_name(node: ast.AST) -> str | None:
    target = node.func if isinstance(node, ast.Call) else node
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "corex"
    ):
        return target.attr
    return None


def bounded_literal(
    node: ast.AST,
    *,
    fail: FailureFactory,
    constants: Mapping[str, ast.AST] | None = None,
    cache: dict[str, Any] | None = None,
    resolving: set[str] | None = None,
    depth: int = 0,
) -> Any:
    if depth > MAX_LITERAL_DEPTH:
        raise fail(node, "Decorator literal nesting is too deep")
    if isinstance(node, ast.Name) and constants is not None and node.id in constants:
        resolved = cache if cache is not None else {}
        active = resolving if resolving is not None else set()
        if node.id in resolved:
            return resolved[node.id]
        if node.id in active:
            raise fail(node, f"Literal constant cycle includes {node.id!r}")
        active.add(node.id)
        try:
            value = bounded_literal(
                constants[node.id],
                fail=fail,
                constants=constants,
                cache=resolved,
                resolving=active,
                depth=depth + 1,
            )
        finally:
            active.remove(node.id)
        resolved[node.id] = value
        return value
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            if isinstance(node.value, str) and len(node.value) > 16_384:
                raise fail(node, "Decorator string literal is too long")
            return node.value
        raise fail(node, "Decorator arguments must use simple literals")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = bounded_literal(
            node.operand,
            fail=fail,
            constants=constants,
            cache=cache,
            resolving=resolving,
            depth=depth + 1,
        )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise fail(node, "Unary decorator literals must be numeric")
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, (ast.Tuple, ast.List)):
        if len(node.elts) > MAX_LITERAL_ITEMS:
            raise fail(node, "Decorator literal contains too many items")
        values = tuple(
            bounded_literal(
                item,
                fail=fail,
                constants=constants,
                cache=cache,
                resolving=resolving,
                depth=depth + 1,
            )
            for item in node.elts
        )
        return values if isinstance(node, ast.Tuple) else list(values)
    if isinstance(node, ast.Dict):
        if len(node.keys) > MAX_LITERAL_ITEMS or any(key is None for key in node.keys):
            raise fail(node, "Decorator mapping literal is too large or uses unpacking")
        result: dict[Any, Any] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            assert key_node is not None
            key = bounded_literal(
                key_node,
                fail=fail,
                constants=constants,
                cache=cache,
                resolving=resolving,
                depth=depth + 1,
            )
            if not isinstance(key, (str, int, float, bool)) or key in result:
                raise fail(key_node, "Decorator mapping keys must be unique scalar literals")
            result[key] = bounded_literal(
                value_node,
                fail=fail,
                constants=constants,
                cache=cache,
                resolving=resolving,
                depth=depth + 1,
            )
        return result
    raise fail(node, "Decorator arguments must be literals")


def declaration_type_id(
    node: ast.AST,
    *,
    fail: FailureFactory,
    constants: Mapping[str, ast.AST] | None = None,
    cache: dict[str, Any] | None = None,
) -> str:
    if isinstance(node, ast.Name) and node.id in BUILTIN_TYPES:
        return BUILTIN_TYPES[node.id]
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "corex"
        and node.attr in TYPE_ALIASES
    ):
        return TYPE_ALIASES[node.attr]
    if isinstance(node, ast.Name) and constants is not None and node.id in constants:
        value = bounded_literal(node, fail=fail, constants=constants, cache=cache)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
        return node.value.strip()
    raise fail(
        node,
        "value_type must be bool, int, float, str, a supported corex alias, or a type-ID string",
    )


def call_values(
    decorator: ast.AST,
    name: str,
    *,
    allowed: set[str] | frozenset[str],
    fail: FailureFactory,
    constants: Mapping[str, ast.AST] | None = None,
    cache: dict[str, Any] | None = None,
    reserved: frozenset[str] = frozenset({"ctx", "corex", "__builtins__"}),
    reject_private: bool = False,
) -> tuple[str, dict[str, Any], dict[str, ast.AST]]:
    if not isinstance(decorator, ast.Call):
        raise fail(decorator, f"@corex.{name} requires parentheses")
    if len(decorator.args) != 1:
        raise fail(decorator, f"@corex.{name} requires one positional name")
    key = bounded_literal(
        decorator.args[0], fail=fail, constants=constants, cache=cache
    )
    if not isinstance(key, str) or not key.isidentifier() or keyword.iskeyword(key):
        raise fail(decorator.args[0], "Decorator name must be a valid Python identifier")
    if key in reserved or (reject_private and key.startswith("_")):
        raise fail(decorator.args[0], f"Decorator name {key!r} is reserved")
    values: dict[str, Any] = {}
    nodes: dict[str, ast.AST] = {}
    for keyword_node in decorator.keywords:
        if keyword_node.arg is None:
            raise fail(keyword_node.value, "Decorator keyword unpacking is not allowed")
        if keyword_node.arg not in allowed:
            if keyword_node.arg.startswith("_"):
                raise fail(
                    keyword_node.value,
                    f"Private decorator field {keyword_node.arg!r} is reserved for internal built-ins",
                )
            raise fail(
                keyword_node.value,
                f"@corex.{name} does not accept {keyword_node.arg!r}",
            )
        if keyword_node.arg in values:
            raise fail(
                keyword_node.value,
                f"Duplicate decorator argument {keyword_node.arg!r}",
            )
        nodes[keyword_node.arg] = keyword_node.value
        values[keyword_node.arg] = (
            None
            if keyword_node.arg == "_persistence_type"
            and isinstance(keyword_node.value, ast.Constant)
            and keyword_node.value.value is None
            else declaration_type_id(
                keyword_node.value,
                fail=fail,
                constants=constants,
                cache=cache,
            )
            if keyword_node.arg
            in {
                "value_type",
                "item_type",
                "_persistence_type",
                "_port_value_type",
            }
            else bounded_literal(
                keyword_node.value,
                fail=fail,
                constants=constants,
                cache=cache,
            )
        )
        if keyword_node.arg in {
            "label",
            "description",
            "section",
            "structure",
            "file_filter",
            "direction",
            "_inline_editor",
            "_inspector_editor",
            "_port_description",
            "_port_label",
            "_port_structure",
            "_property_group",
            "_property_type",
            "_sensitive_scope_key",
        } and not isinstance(values[keyword_node.arg], str):
            raise fail(keyword_node.value, f"{keyword_node.arg} must be a string literal")
        if keyword_node.arg in {
            "required",
            "port",
            "searchable",
            "_port_required",
            "_port_uses_property_default",
            "_inspector_visible",
            "_sensitive",
        } and not isinstance(
            values[keyword_node.arg], bool
        ):
            raise fail(keyword_node.value, f"{keyword_node.arg} must be true or false")
        if keyword_node.arg == "_section_order" and (
            isinstance(values[keyword_node.arg], bool)
            or not isinstance(values[keyword_node.arg], int)
            or values[keyword_node.arg] < 0
        ):
            raise fail(
                keyword_node.value,
                "_section_order must be a non-negative integer",
            )
    return key, values, nodes


def string_value(values: Mapping[str, Any], key: str, default: str = "") -> str:
    value = values.get(key, default)
    if not isinstance(value, str):
        raise DeclarationValueError(f"{key} must be a string literal")
    normalized = value.strip()
    if not normalized and default:
        return default
    return normalized


def bool_value(values: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise DeclarationValueError(f"{key} must be true or false")
    return value


def label_value(key: str, values: Mapping[str, Any]) -> str:
    if "label" in values:
        return string_value(values, "label")
    return key.replace("_", " ").strip().title()


def type_id_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise DeclarationValueError(f"{field} must be a tuple or list literal")
    if len(value) > 64:
        raise DeclarationValueError(f"{field} contains too many type IDs")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or item != item.strip():
            raise DeclarationValueError(
                f"{field} must contain non-empty canonical type-ID strings"
            )
        if any(character.isspace() for character in item):
            raise DeclarationValueError(
                f"{field} must contain non-empty canonical type-ID strings"
            )
        if item in normalized:
            raise DeclarationValueError(f"{field} must not contain duplicates")
        normalized.append(item)
    return tuple(normalized)


def _validate_property_default(prop: PropertySpec) -> None:
    value = prop.default
    valid = (
        isinstance(value, str)
        if prop.type in {"str", "path"}
        else isinstance(value, int) and not isinstance(value, bool)
        if prop.type == "int"
        else isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        if prop.type == "float"
        else isinstance(value, bool)
        if prop.type == "bool"
        else value in (prop.enum_codes or prop.enum_values)
        if prop.type == "enum"
        else True
        if prop.type == "json"
        else isinstance(value, Interval1D) or (value is None and prop.nullable)
    )
    if not valid:
        raise DeclarationValueError(
            f"_property_default does not match property type {prop.type!r}"
        )


def _materialize_typed_inline_default(
    value: Any,
    persistence_type: str,
) -> Any:
    if not persistence_type or not isinstance(value, Mapping):
        return value
    fields = set(value)
    expected = {"data_type_id", "schema_version", "payload"}
    looks_like_carrier = bool(fields & expected)
    if not looks_like_carrier:
        return value
    if fields != expected:
        raise DeclarationValueError(
            "_property_default typed carrier must contain only data_type_id, schema_version, and payload"
        )
    if value["data_type_id"] != persistence_type:
        raise DeclarationValueError(
            "_property_default typed carrier data_type_id must match _persistence_type"
        )
    schema_version = value["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version < 1
    ):
        raise DeclarationValueError(
            "_property_default typed carrier schema_version must be a positive integer"
        )
    payload = value["payload"]
    if not isinstance(payload, Mapping):
        raise DeclarationValueError(
            "_property_default typed carrier payload must be a mapping"
        )
    return TypedInlineValue(persistence_type, schema_version, payload)


def apply_internal_control_overrides(
    prop: PropertySpec,
    data_type: str,
    accepted_data_types: tuple[str, ...],
    data_access: str,
    values: Mapping[str, Any],
) -> tuple[PropertySpec, str, tuple[str, ...], str]:
    property_type = values.get("_property_type", prop.type)
    if property_type not in PROPERTY_TYPES:
        raise DeclarationValueError(
            "_property_type must be str, int, float, bool, path, enum, json, or interval_1d"
        )
    inline_editor = values.get("_inline_editor", prop.inline_editor)
    if inline_editor not in INLINE_EDITORS:
        raise DeclarationValueError("_inline_editor is unsupported")
    inspector_editor = values.get("_inspector_editor", prop.inspector_editor)
    if inspector_editor not in INSPECTOR_EDITORS:
        raise DeclarationValueError("_inspector_editor is unsupported")
    inspector_visible = values.get("_inspector_visible", prop.inspector_visible)
    if not isinstance(inspector_visible, bool):
        raise DeclarationValueError("_inspector_visible must be true or false")
    property_group = values.get("_property_group", prop.group)
    if not isinstance(property_group, str):
        raise DeclarationValueError("_property_group must be a string literal")
    persistence_type = values.get(
        "_persistence_type", prop.persistence_data_type_id
    )
    sensitive = values.get("_sensitive", prop.sensitive)
    sensitive_scope_key = values.get(
        "_sensitive_scope_key", prop.sensitive_scope_key
    )
    if sensitive_scope_key and (
        not sensitive_scope_key.isidentifier() or sensitive_scope_key.startswith("_")
    ):
        raise DeclarationValueError(
            "_sensitive_scope_key must be a public declaration key"
        )
    if sensitive_scope_key and not sensitive:
        raise DeclarationValueError(
            "_sensitive_scope_key requires _sensitive=True"
        )
    secret_editor = inline_editor == "secret" or inspector_editor == "secret"
    if secret_editor and not sensitive:
        raise DeclarationValueError("secret editors require _sensitive=True")
    if sensitive and (property_type != "json" or not secret_editor):
        raise DeclarationValueError(
            "sensitive properties require type json and a secret editor"
        )
    default = values.get("_property_default", prop.default)
    if "_property_default" in values and persistence_type:
        default = _materialize_typed_inline_default(default, persistence_type)
    prop = replace(
        prop,
        type=property_type,
        default=default,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        inspector_visible=inspector_visible,
        group=property_group.strip(),
        sensitive=sensitive,
        sensitive_scope_key=sensitive_scope_key,
        persistence_data_type_id="" if persistence_type is None else persistence_type,
    )
    _validate_property_default(prop)

    port_data_type = values.get("_port_value_type", data_type)
    port_accepted = (
        type_id_tuple(
            values["_port_accepted_data_types"],
            field="_port_accepted_data_types",
        )
        if "_port_accepted_data_types" in values
        else accepted_data_types
    )
    port_access = values.get("_port_structure", data_access)
    if port_access not in DATA_ACCESS_VALUES:
        raise DeclarationValueError(
            "_port_structure must be 'item', 'list', or 'tree'"
        )
    return prop, port_data_type, port_accepted, port_access


def port_spec(
    key: str,
    *,
    direction: str,
    data_type: str,
    label: str,
    description: str,
    required: bool | None = None,
    data_access: str = "item",
    uses_property_default: bool = False,
    accepted_data_types: tuple[str, ...] = (),
    allow_empty_string: bool = False,
) -> PortSpec:
    return PortSpec(
        key,
        direction,  # type: ignore[arg-type]
        "data",
        data_type,
        label=label,
        description=description,
        required=required,
        data_access=data_access,  # type: ignore[arg-type]
        uses_property_default=uses_property_default,
        accepted_data_types=accepted_data_types,
        allow_empty_string=allow_empty_string,
    )


def _numeric_type(value: Any, *, field: str = "default") -> tuple[str, str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeclarationValueError(f"{field} must be an int or float literal")
    if not math.isfinite(float(value)):
        raise DeclarationValueError(f"{field} must be finite")
    return (
        ("int", INTEGER_DATA_TYPE_ID)
        if isinstance(value, int)
        else ("float", DOUBLE_DATA_TYPE_ID)
    )


def _numeric_metadata(values: Mapping[str, Any], *keys: str) -> None:
    for key in keys:
        value = values.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DeclarationValueError(f"{key} must be a number literal")
        if not math.isfinite(float(value)):
            raise DeclarationValueError(f"{key} must be finite")


def control_spec(
    decorator_name: str,
    key: str,
    values: Mapping[str, Any],
) -> tuple[PropertySpec, str, tuple[str, ...], str]:
    label = label_value(key, values)
    description = string_value(values, "description")
    section = string_value(values, "section")
    accepted: tuple[str, ...] = ()

    if decorator_name in {"text", "text_area", "color", "path"}:
        default = values.get("default", "")
        if not isinstance(default, str):
            raise DeclarationValueError("default must be a string literal")
        property_type = "path" if decorator_name == "path" else "str"
        editor = {
            "text": "text",
            "text_area": "textarea",
            "color": "color",
            "path": "path",
        }[decorator_name]
        data_type = {
            "color": COLOR_DATA_TYPE_ID,
            "path": PATH_DATA_TYPE_ID,
        }.get(decorator_name, STRING_DATA_TYPE_ID)
        if decorator_name in {"color", "path"}:
            accepted = (STRING_DATA_TYPE_ID,)
        prop = PropertySpec(
            key,
            property_type,  # type: ignore[arg-type]
            default,
            label,
            inline_editor=editor,  # type: ignore[arg-type]
            file_filter=string_value(values, "file_filter"),
            description=description,
            group=section,
        )
        return prop, data_type, accepted, "item"

    if decorator_name == "switch":
        default = values.get("default", False)
        if not isinstance(default, bool):
            raise DeclarationValueError("default must be true or false")
        return (
            PropertySpec(
                key,
                "bool",
                default,
                label,
                inline_editor="toggle",
                description=description,
                group=section,
            ),
            BOOLEAN_DATA_TYPE_ID,
            (),
            "item",
        )

    if decorator_name in {"number", "slider"}:
        default = values.get("default", 0.0)
        property_type, data_type = _numeric_type(default)
        _numeric_metadata(values, "minimum", "maximum", "step")
        minimum = values.get("minimum")
        maximum = values.get("maximum")
        step = values.get("step", 0.0)
        if decorator_name == "slider" and (minimum is None or maximum is None):
            raise DeclarationValueError("slider requires minimum and maximum")
        if minimum is not None and float(default) < float(minimum):
            raise DeclarationValueError("default must be at least minimum")
        if maximum is not None and float(default) > float(maximum):
            raise DeclarationValueError("default must be at most maximum")
        return (
            PropertySpec(
                key,
                property_type,  # type: ignore[arg-type]
                default,
                label,
                minimum=minimum,
                maximum=maximum,
                step=step,
                inline_editor="slider" if decorator_name == "slider" else "number",
                description=description,
                group=section,
            ),
            data_type,
            (),
            "item",
        )

    if decorator_name == "dropdown":
        options = values.get("options")
        if (
            not isinstance(options, (list, tuple))
            or not options
            or not all(isinstance(item, str) and item for item in options)
        ):
            raise DeclarationValueError("dropdown options must be non-empty strings")
        enum_values = tuple(options)
        if len(set(enum_values)) != len(enum_values):
            raise DeclarationValueError("dropdown options must be unique")
        codes_value = values.get("codes")
        searchable = bool_value(values, "searchable")
        if codes_value is None:
            default = values.get("default", enum_values[0])
            if default not in enum_values:
                raise DeclarationValueError("dropdown default must be one of options")
            return (
                PropertySpec(
                    key,
                    "enum",
                    default,
                    label,
                    enum_values=enum_values,
                    inline_editor="enum",
                    searchable=searchable,
                    description=description,
                    group=section,
                ),
                STRING_DATA_TYPE_ID,
                (),
                "item",
            )
        if not isinstance(codes_value, (list, tuple)) or len(codes_value) != len(
            enum_values
        ):
            raise DeclarationValueError("dropdown codes must match options")
        if searchable:
            raise DeclarationValueError(
                "searchable dropdowns cannot use integer-backed codes"
            )
        codes = tuple(codes_value)
        if len(set(codes)) != len(codes):
            raise DeclarationValueError("dropdown codes must be unique")
        if any(isinstance(code, bool) or not isinstance(code, int) for code in codes):
            raise DeclarationValueError("dropdown codes must be integer literals")
        default = values.get("default", codes[0])
        if default not in codes:
            raise DeclarationValueError("dropdown default must be one of codes")
        return (
            PropertySpec(
                key,
                "int",
                default,
                label,
                enum_values=enum_values,
                enum_codes=codes,
                inline_editor="enum",
                searchable=searchable,
                description=description,
                group=section,
            ),
            INTEGER_DATA_TYPE_ID,
            (),
            "item",
        )

    if decorator_name == "interval":
        default = values.get("default")
        nullable = default is None
        if default is not None:
            if (
                not isinstance(default, (list, tuple))
                or len(default) != 2
                or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in default
                )
            ):
                raise DeclarationValueError(
                    "interval default must be None or two numbers"
                )
            default = Interval1D(float(default[0]), float(default[1]))
        minimum = values.get("minimum")
        maximum = values.get("maximum")
        _numeric_metadata(values, "minimum", "maximum", "step")
        slider = minimum is not None or maximum is not None
        if not slider and "direction" in values:
            raise DeclarationValueError(
                "interval direction requires minimum and maximum"
            )
        if slider and (minimum is None or maximum is None or default is None):
            raise DeclarationValueError(
                "interval sliders require minimum, maximum, and a non-null default"
            )
        direction = string_value(values, "direction", "increasing") if slider else ""
        persistence_type = values.get(
            "_persistence_type", INTERVAL_1D_GRAPH_DATA_TYPE_ID
        )
        if persistence_type not in {None, INTERVAL_1D_GRAPH_DATA_TYPE_ID}:
            raise DeclarationValueError(
                "_persistence_type must be corex.Interval, its type-ID, or None"
            )
        return (
            PropertySpec(
                key,
                "interval_1d",
                default,
                label,
                minimum=minimum,
                maximum=maximum,
                step=values.get("step", 0.0),
                inline_editor="interval_slider" if slider else "interval_fields",
                interval_direction=direction,  # type: ignore[arg-type]
                nullable=nullable,
                persistence_data_type_id=(
                    "" if persistence_type is None else INTERVAL_1D_GRAPH_DATA_TYPE_ID
                ),
                description=description,
                group=section,
            ),
            INTERVAL_1D_GRAPH_DATA_TYPE_ID,
            (),
            "item",
        )

    if decorator_name == "list":
        default = values.get("default", [])
        if not isinstance(default, list):
            raise DeclarationValueError("list default must be a list literal")
        options = values.get("options")
        codes = values.get("codes")
        if codes is not None and options is None:
            raise DeclarationValueError("list codes require options")
        item_type_id = values.get("item_type", STRING_DATA_TYPE_ID)
        item_type = {
            STRING_DATA_TYPE_ID: "str",
            INTEGER_DATA_TYPE_ID: "int",
            DOUBLE_DATA_TYPE_ID: "float",
            COLOR_DATA_TYPE_ID: "color",
        }.get(item_type_id)
        enum_values: tuple[str, ...] = ()
        enum_codes: tuple[Any, ...] = ()
        if options is not None:
            if (
                not isinstance(options, (list, tuple))
                or not options
                or not all(isinstance(item, str) and item for item in options)
            ):
                raise DeclarationValueError("list options must be non-empty strings")
            enum_values = tuple(options)
            if len(set(enum_values)) != len(enum_values):
                raise DeclarationValueError("list options must be unique")
            enum_codes = tuple(options if codes is None else codes)
            if len(enum_codes) != len(enum_values):
                raise DeclarationValueError("list codes must match options")
            if len(set(enum_codes)) != len(enum_codes):
                raise DeclarationValueError("list codes must be unique")
            item_type = "enum"
            if codes is not None and any(
                isinstance(code, bool) or not isinstance(code, int)
                for code in enum_codes
            ):
                raise DeclarationValueError("list codes must be integer literals")
            sample = enum_codes[0]
            item_type_id = (
                INTEGER_DATA_TYPE_ID
                if isinstance(sample, int)
                else DOUBLE_DATA_TYPE_ID
                if isinstance(sample, float)
                else STRING_DATA_TYPE_ID
            )
        if item_type is None:
            raise DeclarationValueError(
                "list item_type must be str, int, float, or corex.Color"
            )
        _numeric_metadata(values, "minimum", "maximum", "step")
        if item_type == "enum":
            if any(item not in enum_codes for item in default):
                raise DeclarationValueError("list default contains an invalid code")
        else:
            expected_type = {
                "str": str,
                "color": str,
                "int": int,
                "float": (int, float),
            }[item_type]
            if any(
                isinstance(item, bool) or not isinstance(item, expected_type)
                for item in default
            ):
                raise DeclarationValueError(
                    f"list default items must match {item_type}"
                )
        return (
            PropertySpec(
                key,
                "json",
                default,
                label,
                inline_editor="list",
                list_item_type=item_type,  # type: ignore[arg-type]
                list_item_enum_values=enum_values,
                list_item_enum_codes=enum_codes,
                list_item_minimum=values.get("minimum"),
                list_item_maximum=values.get("maximum"),
                list_item_step=values.get("step", 0.0),
                description=description,
                group=section,
            ),
            str(item_type_id),
            (STRING_DATA_TYPE_ID,) if item_type_id == COLOR_DATA_TYPE_ID else (),
            "list",
        )

    raise DeclarationValueError(f"Unsupported control decorator: {decorator_name}")


def group_id(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "section"
    if not base[0].isalpha():
        base = f"section_{base}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
