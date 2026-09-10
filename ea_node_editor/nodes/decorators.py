# Purpose: Define trusted-internal descriptor decorators for legacy exceptions.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_decorator_sdk.py

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Literal

from ea_node_editor.runtime_contracts import (
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    Interval1D,
)

from ea_node_editor.nodes.node_specs import (
    CategoryPath,
    DataAccess,
    DynamicPortGroupSpec,
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortKind,
    PortSpec,
    PropertyConditionSpec,
    PropertySpec,
    ReadinessRequirementSpec,
    SettingsGroupSpec,
    SolutionReuseScope,
)
from ea_node_editor.nodes.plugin_contracts import NodePlugin, PluginDescriptor


def in_port(
    key: str,
    *,
    kind: PortKind = "data",
    data_type: str = "COREX.DataTypes.Any",
    accepted_data_types: tuple[str, ...] = (),
    data_access: DataAccess = "item",
    required: bool | None = None,
    uses_property_default: bool = False,
    exposed: bool = True,
    allow_multiple_connections: bool = False,
    description: str = "",
) -> PortSpec:
    return PortSpec(
        key=key,
        direction="in",
        kind=kind,
        data_type=data_type,
        accepted_data_types=accepted_data_types,
        data_access=data_access,
        required=required,
        uses_property_default=uses_property_default,
        exposed=exposed,
        allow_multiple_connections=allow_multiple_connections,
        description=description,
    )


def out_port(
    key: str,
    *,
    kind: PortKind = "data",
    data_type: str = "COREX.DataTypes.Any",
    data_access: DataAccess = "item",
    required: bool | None = None,
    exposed: bool = True,
    allow_multiple_connections: bool = False,
    description: str = "",
) -> PortSpec:
    return PortSpec(
        key=key,
        direction="out",
        kind=kind,
        data_type=data_type,
        data_access=data_access,
        required=required,
        exposed=exposed,
        allow_multiple_connections=allow_multiple_connections,
        description=description,
    )


def prop_str(
    key: str,
    default: str,
    label: str,
    *,
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="str",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        enabled_when=enabled_when,
    )


def prop_int(
    key: str,
    default: int,
    label: str,
    *,
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    minimum: float | None = None,
    maximum: float | None = None,
    step: float = 0.0,
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="int",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        minimum=minimum,
        maximum=maximum,
        step=step,
        enabled_when=enabled_when,
    )


def prop_float(
    key: str,
    default: float,
    label: str,
    *,
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    minimum: float | None = None,
    maximum: float | None = None,
    step: float = 0.0,
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="float",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        minimum=minimum,
        maximum=maximum,
        step=step,
        enabled_when=enabled_when,
    )


def prop_bool(
    key: str,
    default: bool,
    label: str,
    *,
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="bool",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        enabled_when=enabled_when,
    )


def prop_enum(
    key: str,
    default: str,
    label: str,
    *,
    values: Iterable[str],
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    searchable: bool = False,
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="enum",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        enum_values=tuple(values),
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        searchable=searchable,
        enabled_when=enabled_when,
    )


def prop_json(
    key: str,
    default: Any,
    label: str,
    *,
    expose_port_toggle: bool = False,
    inline_editor: str = "",
    inspector_editor: str = "",
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="json",
        default=default,
        label=label,
        expose_port_toggle=expose_port_toggle,
        inline_editor=inline_editor,
        inspector_editor=inspector_editor,
        enabled_when=enabled_when,
    )


def prop_interval_1d(
    key: str,
    default: Interval1D,
    label: str,
    *,
    minimum: float,
    maximum: float,
    step: float = 0.0,
    direction: Literal["increasing", "decreasing"] = "increasing",
    enabled_when: PropertyConditionSpec | None = None,
) -> PropertySpec:
    return PropertySpec(
        key=key,
        type="interval_1d",
        default=default,
        label=label,
        minimum=minimum,
        maximum=maximum,
        step=step,
        inline_editor="interval_slider",
        enabled_when=enabled_when,
        interval_direction=direction,
        persistence_data_type_id=INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    )


def node_type(
    *,
    type_id: str,
    display_name: str,
    icon: str,
    ports: tuple[PortSpec, ...] | list[PortSpec],
    properties: tuple[PropertySpec, ...] | list[PropertySpec],
    category_path: CategoryPath | None = None,
    category: str = "",
    collapsible: bool = True,
    description: str = "",
    keywords: tuple[str, ...] | list[str] = (),
    runtime_behavior: str = "active",
    solution_reuse_scope: SolutionReuseScope = "never",
    surface_family: str = "standard",
    surface_variant: str = "",
    render_quality: NodeRenderQualitySpec | dict[str, Any] | None = None,
    dynamic_port_groups: tuple[DynamicPortGroupSpec, ...] | list[DynamicPortGroupSpec] = (),
    settings_groups: tuple[SettingsGroupSpec, ...] | list[SettingsGroupSpec] = (),
    default_expanded_settings_group_ids: tuple[str, ...] | list[str] = (),
    readiness_requirements: tuple[ReadinessRequirementSpec, ...] | list[ReadinessRequirementSpec] = (),
) -> Callable[[type[NodePlugin]], type[NodePlugin]]:
    resolved_category_path = category_path
    if resolved_category_path is None:
        legacy_category = str(category).strip()
        if not legacy_category:
            raise TypeError("node_type() missing required keyword-only argument: 'category_path'")
        resolved_category_path = (legacy_category,)

    spec = NodeTypeSpec(
        type_id=type_id,
        display_name=display_name,
        category_path=resolved_category_path,
        icon=icon,
        ports=tuple(ports),
        properties=tuple(properties),
        dynamic_port_groups=tuple(dynamic_port_groups),
        collapsible=collapsible,
        description=description,
        keywords=tuple(keywords),
        runtime_behavior=runtime_behavior,  # type: ignore[arg-type]
        solution_reuse_scope=solution_reuse_scope,
        surface_family=surface_family,  # type: ignore[arg-type]
        surface_variant=surface_variant,
        render_quality=render_quality,  # type: ignore[arg-type]
        settings_groups=tuple(settings_groups),
        default_expanded_settings_group_ids=tuple(
            default_expanded_settings_group_ids
        ),
        readiness_requirements=tuple(readiness_requirements),
    )

    def decorator(cls: type[NodePlugin]) -> type[NodePlugin]:
        def spec_method(self) -> NodeTypeSpec:  # noqa: ANN001
            return spec

        setattr(cls, "__node_type_spec__", spec)
        setattr(cls, "spec", spec_method)
        return cls

    return decorator


def plugin_descriptor(factory: Callable[[], NodePlugin]) -> PluginDescriptor:
    spec = getattr(factory, "__node_type_spec__", None)
    if not isinstance(spec, NodeTypeSpec):
        spec = factory().spec()
    return PluginDescriptor(spec=spec, factory=factory)
