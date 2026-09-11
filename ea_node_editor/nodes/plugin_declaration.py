# Purpose: Discover novice function-plugin declarations statically without importing source.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_declaration.py, tests/mechanical_catalogue/test_controls.py
# Landmarks: _node_metadata; _readiness_requirements; _parse_function; discover_plugin_declarations

from __future__ import annotations

import ast
import re
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from corex import _unknown_setting_message
from ea_node_editor.nodes import declaration_engine as _engine
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.instance_resolution import validate_type_forwarding
from ea_node_editor.nodes.node_specs import (
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortSpec,
    PropertyConditionSpec,
    PropertySpec,
    ReadinessRequirementSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)

_CUSTOM_TYPE_ID = re.compile(
    r"^custom\.[a-z0-9]+(?:[._-][a-z0-9]+)*\.[0-9a-f]{8}$"
)
_NODE_FIELDS = frozenset(
    {"id", "name", "category", "description", "keywords", "icon"}
)
_INTERNAL_NODE_FIELDS = _NODE_FIELDS | {
    "_collapsible",
    "_default_expanded_settings_group_ids",
    "_property_output_collisions",
    "_readiness_requirements",
    "_render_quality_tiers",
    "_solution_reuse_scope",
    "_surface_family",
    "_surface_variant",
}
_RENDER_QUALITY_TIERS = frozenset({"full", "reduced", "proxy"})
_REQUIRED_NODE_FIELDS = frozenset({"id", "name", "category"})
_RESERVED_DECLARATION_NAMES = frozenset(
    {"ctx", "settings", "to_dict", "corex", "__builtins__"}
)
_INTROSPECTION_CALLS = frozenset({"dir", "getattr", "hasattr", "vars"})


class PluginDeclarationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        filename: str,
        line: int = 1,
        column: int = 1,
    ) -> None:
        self.message = str(message)
        self.filename = str(filename)
        self.line = max(1, int(line))
        self.column = max(1, int(column))
        super().__init__(
            f"{self.filename}:{self.line}:{self.column}: {self.message}"
        )


@dataclass(frozen=True, slots=True)
class PythonFunctionDeclaration:
    spec: NodeTypeSpec
    function_name: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    control_keys: tuple[str, ...]
    is_async: bool


def _failure(filename: str):
    def fail(node: ast.AST | None, message: str) -> PluginDeclarationError:
        return PluginDeclarationError(
            message,
            filename=filename,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0) + 1,
        )

    return fail


def _literal_assignments(module: ast.Module) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for statement in module.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            assignments[statement.targets[0].id] = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.value is not None
        ):
            assignments[statement.target.id] = statement.value
    return assignments


def _corex_aliases(module: ast.Module) -> set[str]:
    aliases: set[str] = set()
    for statement in module.body:
        if isinstance(statement, ast.Import):
            aliases.update(
                item.asname
                for item in statement.names
                if item.name == "corex" and item.asname and item.asname != "corex"
            )
        elif isinstance(statement, ast.ImportFrom) and statement.module == "corex":
            aliases.update(item.asname or item.name for item in statement.names)
    return aliases


def _has_corex_import(module: ast.Module) -> bool:
    return any(
        isinstance(statement, ast.Import)
        and any(
            item.name == "corex" and item.asname in {None, "corex"}
            for item in statement.names
        )
        for statement in module.body
    )


def _decorator_root_name(decorator: ast.AST) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return target.value.id
    return None


class _ModuleBindingCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def _bind(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def _visit_function_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        self._bind(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_header(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name)
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword_node in node.keywords:
            self.visit(keyword_node.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._bind(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self._bind(item.asname or item.name.partition(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for item in node.names:
            if item.name != "*":
                self._bind(item.asname or item.name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest)
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)


def _module_binding_counts(module: ast.Module) -> dict[str, int]:
    visitor = _ModuleBindingCounter()
    visitor.visit(module)
    return visitor.counts


def _node_metadata(
    decorator: ast.AST,
    *,
    fail,
    constants: Mapping[str, ast.AST],
    cache: dict[str, Any],
    allow_reserved_ids: bool,
    allow_internal_metadata: bool,
) -> dict[str, Any]:
    if not isinstance(decorator, ast.Call):
        raise fail(decorator, "@corex.node requires parentheses and metadata")
    if decorator.args:
        raise fail(decorator.args[0], "@corex.node accepts keyword arguments only")
    values: dict[str, Any] = {}
    for keyword_node in decorator.keywords:
        if keyword_node.arg is None:
            raise fail(keyword_node.value, "@corex.node keyword unpacking is not allowed")
        allowed_fields = (
            _INTERNAL_NODE_FIELDS if allow_internal_metadata else _NODE_FIELDS
        )
        if keyword_node.arg not in allowed_fields:
            if keyword_node.arg.startswith("_"):
                raise fail(
                    keyword_node.value,
                    f"Private decorator field {keyword_node.arg!r} is reserved for internal built-ins",
                )
            raise fail(
                keyword_node.value,
                f"@corex.node does not accept {keyword_node.arg!r}",
            )
        if keyword_node.arg in values:
            raise fail(
                keyword_node.value,
                f"Duplicate @corex.node argument {keyword_node.arg!r}",
            )
        values[keyword_node.arg] = _engine.bounded_literal(
            keyword_node.value,
            fail=fail,
            constants=constants,
            cache=cache,
        )
    missing = sorted(_REQUIRED_NODE_FIELDS - values.keys())
    if missing:
        raise fail(decorator, "@corex.node is missing: " + ", ".join(missing))

    type_id = values["id"]
    if not isinstance(type_id, str) or type_id != type_id.strip():
        raise fail(decorator, "@corex.node id must be a trimmed string literal")
    if not allow_reserved_ids and _CUSTOM_TYPE_ID.fullmatch(type_id) is None:
        raise fail(
            decorator,
            "External node ids must match custom.<readable-slug>.<8-lowercase-hex>",
        )
    if allow_reserved_ids and not type_id:
        raise fail(decorator, "@corex.node id must not be empty")

    display_name = values["name"]
    if (
        not isinstance(display_name, str)
        or not display_name
        or display_name != display_name.strip()
    ):
        raise fail(decorator, "@corex.node name must be a non-empty trimmed string")
    category = values["category"]
    if (
        not isinstance(category, (list, tuple))
        or not category
        or not all(
            isinstance(item, str) and item and item == item.strip()
            for item in category
        )
    ):
        raise fail(
            decorator,
            "@corex.node category must contain non-empty trimmed strings",
        )
    description = values.get("description", "")
    icon = values.get("icon", "")
    if not isinstance(description, str) or not isinstance(icon, str):
        raise fail(decorator, "@corex.node description and icon must be strings")
    keywords = values.get("keywords", ())
    if (
        not isinstance(keywords, (list, tuple))
        or not all(
            isinstance(item, str) and item and item == item.strip()
            for item in keywords
        )
        or len(set(keywords)) != len(keywords)
    ):
        raise fail(decorator, "@corex.node keywords must be unique non-empty strings")
    collapsible = values.get("_collapsible", True)
    if not isinstance(collapsible, bool):
        raise fail(decorator, "_collapsible must be true or false")
    surface_family = values.get("_surface_family", "standard")
    if (
        not isinstance(surface_family, str)
        or not surface_family
        or surface_family != surface_family.strip()
    ):
        raise fail(decorator, "_surface_family must be a non-empty trimmed string")
    surface_variant = values.get("_surface_variant", "")
    if not isinstance(surface_variant, str) or surface_variant != surface_variant.strip():
        raise fail(decorator, "_surface_variant must be a trimmed string")
    render_quality_tiers = values.get("_render_quality_tiers", ("full",))
    if not isinstance(render_quality_tiers, (list, tuple)):
        raise fail(decorator, "_render_quality_tiers must be a tuple or list literal")
    if not 1 <= len(render_quality_tiers) <= len(_RENDER_QUALITY_TIERS):
        raise fail(decorator, "_render_quality_tiers must contain one to three tiers")
    if any(
        not isinstance(tier, str) or tier not in _RENDER_QUALITY_TIERS
        for tier in render_quality_tiers
    ):
        raise fail(
            decorator,
            "_render_quality_tiers values must be 'full', 'reduced', or 'proxy'",
        )
    if len(set(render_quality_tiers)) != len(render_quality_tiers):
        raise fail(decorator, "_render_quality_tiers must not contain duplicates")
    solution_reuse_scope = values.get("_solution_reuse_scope", "never")
    if (
        not isinstance(solution_reuse_scope, str)
        or solution_reuse_scope not in {"never", "session", "durable"}
    ):
        raise fail(
            decorator,
            "_solution_reuse_scope must be 'never', 'session', or 'durable'",
        )
    property_output_collisions = _key_tuple(
        values.get("_property_output_collisions", ()),
        field="_property_output_collisions",
        fail=fail,
        node=decorator,
    )
    default_expanded_settings_group_ids = _key_tuple(
        values.get("_default_expanded_settings_group_ids", ()),
        field="_default_expanded_settings_group_ids",
        fail=fail,
        node=decorator,
    )
    return {
        "type_id": type_id,
        "display_name": display_name,
        "category_path": tuple(category),
        "description": description,
        "keywords": tuple(keywords),
        "icon": icon,
        "collapsible": collapsible,
        "default_expanded_settings_group_ids": default_expanded_settings_group_ids,
        "property_output_collisions": property_output_collisions,
        "readiness_requirements": values.get("_readiness_requirements", ()),
        "render_quality_tiers": tuple(render_quality_tiers),
        "solution_reuse_scope": solution_reuse_scope,
        "surface_family": surface_family,
        "surface_variant": surface_variant,
    }


def _key_tuple(value: Any, *, field: str, fail, node: ast.AST) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise fail(node, f"{field} must be a tuple or list literal")
    if len(value) > 32:
        raise fail(node, f"{field} contains too many keys")
    keys: list[str] = []
    for key in value:
        if not isinstance(key, str) or not key.isidentifier() or key.startswith("_"):
            raise fail(node, f"{field} must contain public declaration keys")
        if key in keys:
            raise fail(node, f"{field} must not contain duplicates")
        keys.append(key)
    return tuple(keys)


def _readiness_requirements(
    value: Any,
    *,
    ports: tuple[PortSpec, ...],
    properties: tuple[PropertySpec, ...],
    fail,
    node: ast.AST,
) -> tuple[ReadinessRequirementSpec, ...]:
    if not isinstance(value, (list, tuple)):
        raise fail(node, "_readiness_requirements must be a tuple or list literal")
    if len(value) > 32:
        raise fail(node, "_readiness_requirements declares too many requirements")
    port_by_key = {
        port.key: port
        for port in ports
        if port.direction == "in" and port.kind == "data"
    }
    port_keys = port_by_key.keys()
    property_by_key = {prop.key: prop for prop in properties}
    requirements: list[ReadinessRequirementSpec] = []
    allowed_requirement_fields = {
        "any_of_ports",
        "any_of_properties",
        "when_ports_present",
        "when_properties",
    }
    for raw in value:
        if not isinstance(raw, dict) or not set(raw) <= allowed_requirement_fields:
            raise fail(
                node,
                "Each readiness requirement must be a mapping with supported fields",
            )
        any_of_ports = _key_tuple(
            raw.get("any_of_ports", ()), field="any_of_ports", fail=fail, node=node
        )
        any_of_properties = _key_tuple(
            raw.get("any_of_properties", ()),
            field="any_of_properties",
            fail=fail,
            node=node,
        )
        when_ports_present = _key_tuple(
            raw.get("when_ports_present", ()),
            field="when_ports_present",
            fail=fail,
            node=node,
        )
        if not any_of_ports and not any_of_properties:
            raise fail(node, "Each readiness requirement must declare at least one target")
        unknown_ports = (set(any_of_ports) | set(when_ports_present)) - port_keys
        if unknown_ports:
            raise fail(
                node,
                "Readiness requirement references unknown input port: "
                + sorted(unknown_ports)[0],
            )
        if set(any_of_ports) & set(when_ports_present):
            raise fail(node, "A readiness port cannot be both target and condition")
        if any(port_by_key[key].required is True for key in any_of_ports):
            raise fail(
                node,
                "A readiness target port cannot duplicate required=True",
            )
        unknown_properties = set(any_of_properties) - property_by_key.keys()
        if unknown_properties:
            raise fail(
                node,
                "Readiness requirement references unknown property: "
                + sorted(unknown_properties)[0],
            )
        if set(any_of_ports) & set(any_of_properties):
            raise fail(node, "Readiness target keys must be unambiguous")

        raw_conditions = raw.get("when_properties", ())
        if not isinstance(raw_conditions, (list, tuple)):
            raise fail(node, "when_properties must be a tuple or list literal")
        if len(raw_conditions) > 32:
            raise fail(node, "when_properties declares too many conditions")
        conditions: list[PropertyConditionSpec] = []
        condition_keys: set[str] = set()
        for raw_condition in raw_conditions:
            if (
                not isinstance(raw_condition, dict)
                or not set(raw_condition) <= {"property_key", "values"}
                or "property_key" not in raw_condition
            ):
                raise fail(
                    node,
                    "Each readiness property condition requires property_key and optional values",
                )
            property_key = raw_condition["property_key"]
            if (
                not isinstance(property_key, str)
                or not property_key.isidentifier()
                or property_key not in property_by_key
            ):
                raise fail(node, "Readiness condition references an unknown property")
            if property_key in condition_keys:
                raise fail(node, "Readiness conditions must use unique property keys")
            raw_values = raw_condition.get("values", ())
            if not isinstance(raw_values, (list, tuple)) or len(raw_values) > 32:
                raise fail(node, "Readiness condition values must be a bounded tuple or list")
            if any(
                not isinstance(item, (str, int, float, bool)) and item is not None
                for item in raw_values
            ):
                raise fail(node, "Readiness condition values must be scalar literals")
            if len({repr(item) for item in raw_values}) != len(raw_values):
                raise fail(node, "Readiness condition values must be unique")
            conditions.append(PropertyConditionSpec(property_key, tuple(raw_values)))
            condition_keys.add(property_key)
        if set(any_of_properties) & condition_keys:
            raise fail(node, "A readiness property cannot be both target and condition")
        requirement = ReadinessRequirementSpec(
            any_of_ports=any_of_ports,
            any_of_properties=any_of_properties,
            when_ports_present=when_ports_present,
            when_properties=tuple(conditions),
        )
        if requirement in requirements:
            raise fail(node, "Readiness requirements must not contain duplicates")
        requirements.append(requirement)

    for prop in properties:
        if not prop.sensitive_scope_key:
            continue
        scope = property_by_key.get(prop.sensitive_scope_key)
        if scope is None or scope.type != "enum":
            raise fail(
                node,
                f"Sensitive property {prop.key!r} scope must reference an enum property",
            )
    return tuple(requirements)


def _validate_settings_body(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    control_names: tuple[str, ...],
    *,
    fail,
) -> None:
    allowed = frozenset(control_names)
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _INTROSPECTION_CALLS
            and any(isinstance(arg, ast.Name) and arg.id == "settings" for arg in node.args)
        ):
            raise fail(node, "Dynamic Settings introspection is unsupported")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "settings":
                raise fail(node, "Settings supports attributes and to_dict() only")
        if isinstance(node, ast.Name) and node.id == "settings" and isinstance(
            node.ctx, ast.Store
        ):
            raise fail(node, "settings is immutable and cannot be rebound")
        if (
            not control_names
            and isinstance(node, ast.Name)
            and node.id == "settings"
            and isinstance(node.ctx, ast.Load)
        ):
            raise fail(node, "settings is available only when controls are declared")
        if not (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "settings"
        ):
            continue
        if not isinstance(node.ctx, ast.Load):
            raise fail(node, "Settings values are immutable")
        if node.attr.startswith("_"):
            raise fail(node, "Private Settings members are unsupported")
        if node.attr == "to_dict":
            continue
        if node.attr not in allowed:
            raise fail(node, _unknown_setting_message(node.attr, allowed))


def _parse_function(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    filename: str,
    constants: Mapping[str, ast.AST],
    cache: dict[str, Any],
    allow_reserved_ids: bool,
    allow_internal_metadata: bool,
) -> PythonFunctionDeclaration:
    fail = _failure(filename)
    decorators = function.decorator_list
    if len(decorators) > _engine.MAX_DECORATORS:
        raise fail(function, "Node function declares too many decorators")
    names = tuple(_engine.corex_decorator_name(item) for item in decorators)
    if not names or names[0] != "node":
        raise fail(function, "Exactly one @corex.node must be the first decorator")
    if names.count("node") != 1:
        raise fail(function, "Node function must declare exactly one @corex.node")
    for decorator, name in zip(decorators, names, strict=True):
        if name is None:
            raise fail(decorator, "Node decorators must use the corex namespace")
        if name not in _engine.KNOWN_DECORATORS:
            raise fail(decorator, f"Unknown corex decorator @corex.{name}")

    metadata = _node_metadata(
        decorators[0],
        fail=fail,
        constants=constants,
        cache=cache,
        allow_reserved_ids=allow_reserved_ids,
        allow_internal_metadata=allow_internal_metadata,
    )
    ports: list[PortSpec] = []
    properties: list[PropertySpec] = []
    input_keys: list[str] = []
    output_keys: list[str] = []
    control_keys: list[str] = []
    used_keys: set[str] = set()
    section_items: OrderedDict[
        str, list[tuple[int | None, int, SettingsGroupItemSpec]]
    ] = OrderedDict()

    for decorator, name in zip(decorators[1:], names[1:], strict=True):
        assert name is not None
        section_order: int | None = None
        if name == "input":
            key, values, _nodes = _engine.call_values(
                decorator,
                name,
                allowed=(
                    {
                        "value_type",
                        "structure",
                        "required",
                        "label",
                        "description",
                        "section",
                        "_accepted_data_types",
                    }
                    if allow_internal_metadata
                    else {
                        "value_type",
                        "structure",
                        "required",
                        "label",
                        "description",
                        "section",
                    }
                ),
                fail=fail,
                constants=constants,
                cache=cache,
                reserved=_RESERVED_DECLARATION_NAMES,
                reject_private=True,
            )
            if "value_type" not in values:
                raise fail(decorator, "@corex.input requires explicit value_type=")
            structure = _engine.string_value(values, "structure", "item")
            if structure not in {"item", "list", "tree"}:
                raise fail(decorator, "structure must be 'item', 'list', or 'tree'")
            try:
                accepted_data_types = (
                    _engine.type_id_tuple(
                        values["_accepted_data_types"],
                        field="_accepted_data_types",
                    )
                    if "_accepted_data_types" in values
                    else ()
                )
                port = _engine.port_spec(
                    key,
                    direction="in",
                    data_type=values["value_type"],
                    label=_engine.label_value(key, values),
                    description=_engine.string_value(values, "description"),
                    required=_engine.bool_value(values, "required"),
                    data_access=structure,
                    accepted_data_types=accepted_data_types,
                )
            except _engine.DeclarationValueError as exc:
                raise fail(decorator, str(exc)) from exc
            prop = None
            section = _engine.string_value(values, "section")
            input_keys.append(key)
        elif name == "output":
            key, values, _nodes = _engine.call_values(
                decorator,
                name,
                allowed={"value_type", "structure", "label", "description", "type_from_input"},
                fail=fail,
                constants=constants,
                cache=cache,
                reserved=_RESERVED_DECLARATION_NAMES,
                reject_private=True,
            )
            if "value_type" not in values:
                raise fail(decorator, "@corex.output requires explicit value_type=")
            structure = _engine.string_value(values, "structure", "item")
            if structure not in {"item", "list", "tree"}:
                raise fail(decorator, "structure must be 'item', 'list', or 'tree'")
            port = _engine.port_spec(
                key,
                direction="out",
                data_type=values["value_type"],
                label=_engine.label_value(key, values),
                description=_engine.string_value(values, "description"),
                data_access=structure,
                type_from_input=_engine.string_value(values, "type_from_input"),
            )
            prop = None
            section = ""
            output_keys.append(key)
        elif name in _engine.CONTROL_DECORATORS:
            key, values, _nodes = _engine.call_values(
                decorator,
                name,
                allowed=(
                    _engine.INTERNAL_CONTROL_ALLOWED_FIELDS[name]
                    if allow_internal_metadata
                    else _engine.CONTROL_ALLOWED_FIELDS[name]
                ),
                fail=fail,
                constants=constants,
                cache=cache,
                reserved=_RESERVED_DECLARATION_NAMES,
                reject_private=True,
            )
            try:
                prop, data_type, accepted, data_access = _engine.control_spec(
                    name, key, values
                )
                if allow_internal_metadata:
                    prop, data_type, accepted, data_access = (
                        _engine.apply_internal_control_overrides(
                            prop,
                            data_type,
                            accepted,
                            data_access,
                            values,
                        )
                    )
            except (OverflowError, _engine.DeclarationValueError) as exc:
                message = (
                    "Decorator numeric literal is outside the supported range"
                    if isinstance(exc, OverflowError)
                    else str(exc)
                )
                raise fail(decorator, message) from exc
            section = _engine.string_value(values, "section")
            section_order = values.get("_section_order")
            if section_order is not None and not section:
                raise fail(
                    decorator,
                    "_section_order requires a non-empty section",
                )
            private_port_fields = {
                "_port_accepted_data_types",
                "_port_allow_empty_string",
                "_port_description",
                "_port_label",
                "_port_required",
                "_port_structure",
                "_port_uses_property_default",
                "_port_value_type",
            }
            if private_port_fields & values.keys() and not _engine.bool_value(
                values, "port"
            ):
                raise fail(
                    decorator,
                    "Private port metadata requires port=True",
                )
            port = (
                _engine.port_spec(
                    key,
                    direction="in",
                    data_type=data_type,
                    label=str(values.get("_port_label", prop.label)).strip(),
                    description=str(
                        values.get("_port_description", prop.description)
                    ).strip(),
                    required=values.get("_port_required", False),
                    data_access=data_access,
                    uses_property_default=values.get(
                        "_port_uses_property_default", True
                    ),
                    accepted_data_types=accepted,
                    allow_empty_string=_engine.bool_value(
                        values, "_port_allow_empty_string"
                    ),
                )
                if _engine.bool_value(values, "port")
                else None
            )
            if port is not None and not port.uses_property_default:
                input_keys.append(key)
            control_keys.append(key)
        else:
            raise fail(decorator, f"Unsupported decorator @corex.{name}")

        allowed_property_output_collision = (
            allow_internal_metadata
            and key in metadata["property_output_collisions"]
            and (
                (
                    name in _engine.CONTROL_DECORATORS
                    and port is None
                    and key in output_keys
                    and control_keys.count(key) == 1
                )
                or (
                    name == "output"
                    and key in control_keys
                    and output_keys.count(key) == 1
                    and not any(
                        existing.key == key and existing.direction == "in"
                        for existing in ports
                    )
                )
            )
        )
        if key in used_keys and not allowed_property_output_collision:
            raise fail(decorator, f"Duplicate or cross-direction key {key!r}")
        used_keys.add(key)
        if port is not None:
            ports.append(port)
        if prop is not None:
            properties.append(prop)
        if section:
            items = section_items.setdefault(section, [])
            if section_order is not None and any(
                item_order == section_order for item_order, _index, _item in items
            ):
                raise fail(
                    decorator,
                    f"Duplicate _section_order {section_order} in section {section!r}",
                )
            items.append(
                (
                    section_order,
                    len(items),
                    SettingsGroupItemSpec(
                        port_key=key if port is not None else "",
                        property_key=key if prop is not None else "",
                    ),
                )
            )

    actual_property_output_collisions = {
        prop.key for prop in properties
    } & set(output_keys)
    if set(metadata["property_output_collisions"]) != actual_property_output_collisions:
        raise fail(
            decorators[0],
            "_property_output_collisions must name every actual property/output collision",
        )

    args = function.args
    if (
        args.posonlyargs
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
        or args.defaults
        or args.kw_defaults
    ):
        raise fail(
            function,
            "Node functions use plain required parameters without defaults, positional-only, keyword-only, *args, or **kwargs",
        )
    signature = tuple(argument.arg for argument in args.args)
    expected = ("ctx", *input_keys, *(("settings",) if control_keys else ()))
    if signature != expected:
        raise fail(
            function,
            "Node function parameters must exactly be " + ", ".join(expected),
        )
    _validate_settings_body(function, tuple(control_keys), fail=fail)

    used_group_ids: set[str] = set()
    settings_groups = tuple(
        SettingsGroupSpec(
            _engine.group_id(label, used_group_ids),
            label,
            tuple(
                item
                for _order, _index, item in sorted(
                    items,
                    key=lambda entry: (
                        entry[0] is None,
                        entry[0] if entry[0] is not None else entry[1],
                        entry[1],
                    ),
                )
            ),
        )
        for label, items in section_items.items()
    )
    is_async = isinstance(function, ast.AsyncFunctionDef)
    readiness_requirements = _readiness_requirements(
        metadata["readiness_requirements"],
        ports=tuple(ports),
        properties=tuple(properties),
        fail=fail,
        node=decorators[0],
    )
    try:
        validate_type_forwarding(metadata["type_id"], tuple(ports))
    except ValueError as exc:
        raise fail(function, str(exc)) from exc
    return PythonFunctionDeclaration(
        spec=NodeTypeSpec(
            type_id=metadata["type_id"],
            display_name=metadata["display_name"],
            category_path=metadata["category_path"],
            icon=metadata["icon"],
            ports=tuple(ports),
            properties=tuple(properties),
            collapsible=metadata["collapsible"],
            description=metadata["description"],
            is_async=is_async,
            solution_reuse_scope=metadata["solution_reuse_scope"],
            surface_family=metadata["surface_family"],
            surface_variant=metadata["surface_variant"],
            render_quality=NodeRenderQualitySpec(
                supported_quality_tiers=metadata["render_quality_tiers"]
            ),
            keywords=metadata["keywords"],
            settings_groups=settings_groups,
            default_expanded_settings_group_ids=metadata[
                "default_expanded_settings_group_ids"
            ],
            readiness_requirements=readiness_requirements,
        ),
        function_name=function.name,
        input_keys=tuple(input_keys),
        output_keys=tuple(output_keys),
        control_keys=tuple(control_keys),
        is_async=is_async,
    )


@lru_cache(maxsize=128)
def _discover(
    source: str,
    filename: str,
    allow_reserved_ids: bool,
    allow_internal_metadata: bool,
) -> tuple[PythonFunctionDeclaration, ...]:
    fail = _failure(filename)
    if len(source.encode("utf-8")) > _engine.MAX_SOURCE_BYTES:
        raise fail(None, "Plugin source is too large")
    try:
        module = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError as exc:
        raise PluginDeclarationError(
            exc.msg,
            filename=filename,
            line=exc.lineno or 1,
            column=exc.offset or 1,
        ) from exc
    if sum(1 for _ in ast.walk(module)) > _engine.MAX_AST_NODES:
        raise fail(module, "Plugin syntax tree is too large")

    top_level_functions = tuple(
        item
        for item in module.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    if any(
        isinstance(statement, ast.ImportFrom)
        and any(item.name == "*" for item in statement.names)
        for statement in module.body
    ):
        raise fail(module, "Star imports are unsupported in plugin modules")
    aliases = _corex_aliases(module)
    for function in top_level_functions:
        for decorator in function.decorator_list:
            if _decorator_root_name(decorator) in aliases:
                raise fail(decorator, "Imported corex aliases are unsupported")
    top_level_ids = {id(item) for item in top_level_functions}
    decorator_ids = {
        id(decorator)
        for function in top_level_functions
        for decorator in function.decorator_list
    }
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if id(node) not in top_level_ids and any(
                _engine.corex_decorator_name(item) == "node"
                for item in node.decorator_list
            ):
                raise fail(node, "Node functions must be top-level")
        if (
            isinstance(node, ast.Call)
            and id(node) not in decorator_ids
            and _engine.corex_decorator_name(node) == "node"
        ):
            raise fail(node, "Dynamically generated node functions are unsupported")

    functions = tuple(
        function
        for function in top_level_functions
        if any(
            _engine.corex_decorator_name(item) == "node"
            for item in function.decorator_list
        )
    )
    if functions and not _has_corex_import(module):
        raise fail(functions[0], "Plugin source must contain `import corex`")
    if sum(len(function.decorator_list) for function in functions) > _engine.MAX_DECORATORS:
        raise fail(module, "Plugin source declares too many decorators")
    binding_counts = _module_binding_counts(module)
    for function in functions:
        if binding_counts.get(function.name) != 1:
            raise fail(
                function,
                f"Node function name {function.name!r} must be unique in its module",
            )

    constants = _literal_assignments(module)
    cache: dict[str, Any] = {}
    declarations = tuple(
        _parse_function(
            function,
            filename=filename,
            constants=constants,
            cache=cache,
            allow_reserved_ids=allow_reserved_ids,
            allow_internal_metadata=allow_internal_metadata,
        )
        for function in functions
    )
    type_ids = [declaration.spec.type_id for declaration in declarations]
    if len(type_ids) != len(set(type_ids)):
        duplicate = next(type_id for type_id in type_ids if type_ids.count(type_id) > 1)
        raise fail(module, f"Node id {duplicate!r} is duplicated")
    return declarations


def discover_plugin_declarations(
    source: str,
    *,
    filename: str = "<plugin>",
    allow_reserved_ids: bool = False,
    owner_id: str = "",
    allow_internal_metadata: bool = False,
) -> tuple[PythonFunctionDeclaration, ...]:
    if allow_internal_metadata and (
        not allow_reserved_ids
        or not isinstance(owner_id, str)
        or not owner_id.strip()
    ):
        raise ValueError(
            "Internal metadata requires reserved node ids and a non-empty owner"
        )
    if (
        allow_reserved_ids
        and owner_id != INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        and not allow_internal_metadata
    ):
        raise ValueError("Reserved node ids require the internal built-in owner")
    internal_metadata = (
        owner_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID or allow_internal_metadata
    )
    return _discover(
        str(source),
        str(filename),
        bool(allow_reserved_ids),
        bool(internal_metadata),
    )


__all__ = [
    "PluginDeclarationError",
    "PythonFunctionDeclaration",
    "discover_plugin_declarations",
]
