# Purpose: Provide the dependency-free public function-plugin authoring surface.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_declaration.py, tests/mechanical_catalogue/test_catalogue.py

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from collections.abc import Set as _Set
from difflib import get_close_matches as _get_close_matches
from types import MappingProxyType as _MappingProxyType


Any = "COREX.DataTypes.Any"
Image = "COREX.DataTypes.Image"
Color = "COREX.DataTypes.Color"
Interval = "COREX.DataTypes.Interval1D"


def _reject_unknown_private(
    metadata: _Mapping[str, object], allowed: _Set[str]
) -> None:
    unknown = sorted(
        key for key in metadata if key.startswith("_") and key not in allowed
    )
    if unknown:
        raise TypeError(f"Unsupported private decorator field {unknown[0]!r}")


def _identity_decorator(*_args: object, **_kwargs: object):
    def decorate(function):
        return function

    return decorate


def node(function=None, **_metadata: object):
    _reject_unknown_private(
        _metadata,
        {
            "_collapsible",
            "_default_expanded_settings_group_ids",
            "_property_output_collisions",
            "_readiness_requirements",
            "_render_quality_tiers",
            "_solution_reuse_scope",
            "_surface_family",
            "_surface_variant",
        },
    )
    if callable(function) and not _metadata:
        return function
    return _identity_decorator()


def _decorator(private_fields: _Set[str]):
    def decorate(*args: object, **metadata: object):
        _reject_unknown_private(metadata, private_fields)
        return _identity_decorator(*args, **metadata)

    return decorate


input = _decorator({"_accepted_data_types"})
output = _decorator(set())
_CONTROL_PRIVATE_FIELDS = {
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
text = _decorator(_CONTROL_PRIVATE_FIELDS)
text_area = _decorator(_CONTROL_PRIVATE_FIELDS)
number = _decorator(_CONTROL_PRIVATE_FIELDS)
switch = _decorator(_CONTROL_PRIVATE_FIELDS)
dropdown = _decorator(_CONTROL_PRIVATE_FIELDS)
slider = _decorator(_CONTROL_PRIVATE_FIELDS)
color = _decorator(_CONTROL_PRIVATE_FIELDS)
path = _decorator(_CONTROL_PRIVATE_FIELDS)
interval = _decorator(_CONTROL_PRIVATE_FIELDS)
list = _decorator(_CONTROL_PRIVATE_FIELDS)


def _unknown_setting_message(name: object, known_names: object) -> str:
    token = str(name)[:128]
    candidates = tuple(str(item) for item in known_names)
    suggestion = _get_close_matches(token, candidates, n=1, cutoff=0.6)
    suffix = f" Did you mean {suggestion[0]!r}?" if suggestion else ""
    return f"Unknown setting {token!r}.{suffix}"


def _deep_freeze(value: object) -> object:
    if isinstance(value, _Mapping):
        return _MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, _Sequence) and not isinstance(value, (str, bytes)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, _Set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _deep_mutable(value: object) -> object:
    if isinstance(value, _Mapping):
        return {key: _deep_mutable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_mutable(item) for item in value]
    if isinstance(value, frozenset):
        return {_deep_mutable(item) for item in value}
    return value


class _Settings:
    __slots__ = ("_values",)

    def __init__(self, values: _Mapping[str, object]) -> None:
        object.__setattr__(self, "_values", _deep_freeze(dict(values)))

    def __getattr__(self, name: str) -> object:
        values = object.__getattribute__(self, "_values")
        try:
            return values[name]
        except KeyError as exc:
            raise AttributeError(_unknown_setting_message(name, values)) from exc

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("Settings is immutable")

    def to_dict(self) -> dict[str, object]:
        values = object.__getattribute__(self, "_values")
        return _deep_mutable(values)  # type: ignore[return-value]


__all__ = [
    "node",
    "input",
    "output",
    "text",
    "text_area",
    "number",
    "switch",
    "dropdown",
    "slider",
    "color",
    "path",
    "interval",
    "list",
    "Any",
    "Image",
    "Color",
    "Interval",
]
