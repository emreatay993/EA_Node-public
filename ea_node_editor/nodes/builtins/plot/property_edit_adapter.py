from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ea_node_editor.addons.property_edit_adapters import (
    PropertyEditAdapterContext,
    PropertyEditRewrite,
)
from ea_node_editor.nodes.builtins.plot.generic import (
    PLOT_AXIS_LIMITS_DEFAULT,
    PLOT_COLORMAP_VALUES,
    PLOT_LOG_SCALES_DEFAULT,
    PLOT_NODE_DEFINITIONS,
    PLOT_TABULAR_MAPPING_PROPERTY,
    PLOT_TYPE_BAR,
    PLOT_TYPE_CONTOUR,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_LINE,
    PLOT_TYPE_POINT_CLOUD,
    PLOT_TYPE_SCATTER,
    PLOT_TYPE_STREAMLINES,
    PLOT_TYPE_SURFACE,
)
from ea_node_editor.nodes.builtins.plot.signal_schema import connected_signal_value, enrich_signal_property_items

_PLOT_JSON_PROPERTY_KEYS = {
    "axis_limits",
    "log_scales",
    PLOT_TABULAR_MAPPING_PROPERTY,
    "plot_options",
}
_PLOT_OPTION_PREFIX = "plot_option_"
_AXIS_LIMIT_PREFIX = "axis_limit_"
_AXIS_CONTROL_PREFIX = "plot_axis_"
_LOG_SCALE_PREFIX = "log_scale_"
_TABULAR_MAPPING_PREFIX = "tabular_mapping_"
_UNSUPPORTED_OPTIONS_KEY = "plot_options_unsupported_summary"
_UNSUPPORTED_OPTIONS_RESET_KEY = "plot_options_reset_unsupported"
_PLOT_THEME_VALUES = ("system", "dark", "light")
_PLOT_INVESTIGATION_BOOL_OPTION_KEYS = frozenset({"hover_readout", "vertical_guide", "crosshair"})
_THREE_DIMENSIONAL_PLOT_TYPES = frozenset(
    {
        PLOT_TYPE_SURFACE,
        PLOT_TYPE_POINT_CLOUD,
        PLOT_TYPE_STREAMLINES,
    }
)
_TWO_DIMENSIONAL_LIVE_PLOT_TYPES = frozenset(
    {
        PLOT_TYPE_LINE,
        PLOT_TYPE_SCATTER,
        PLOT_TYPE_BAR,
        PLOT_TYPE_HISTOGRAM,
        PLOT_TYPE_HEATMAP,
        PLOT_TYPE_CONTOUR,
    }
)
_SUPPORTED_PLOT_OPTION_KEYS = frozenset(
    {
        "bins",
        "aspect",
        "show_edges",
        "point_size",
        "line_width",
        "color",
        "render_lines_as_tubes",
        "axes",
        "cmap",
        "colormap",
        "plot_theme",
        "hover_readout",
        "vertical_guide",
        "crosshair",
    }
)

_GENERIC_PLOT_TYPE_BY_NODE_TYPE = {
    definition.type_id: definition.plot_type for definition in PLOT_NODE_DEFINITIONS
}
_GENERIC_SUPPORTS_COLORMAP_BY_NODE_TYPE = {
    definition.type_id: definition.supports_colormap for definition in PLOT_NODE_DEFINITIONS
}


def _node_properties(node: Any) -> Mapping[str, Any]:
    properties = getattr(node, "properties", {})
    return properties if isinstance(properties, Mapping) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _plot_theme(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "auto":
        normalized = "system"
    return normalized if normalized in _PLOT_THEME_VALUES else "system"


def _numeric_or_none(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _positive_int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return None
    return max(1, number)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace(";", ",").split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        raw_values = ()
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        folded = text.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(text)
    return result


def _axis_limits(properties: Mapping[str, Any]) -> dict[str, list[Any]]:
    result = copy.deepcopy(PLOT_AXIS_LIMITS_DEFAULT)
    raw = properties.get("axis_limits")
    if isinstance(raw, Mapping):
        for axis in ("x", "y", "z"):
            value = raw.get(axis)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                values = list(value)
                result[axis] = [
                    _numeric_or_none(values[0]) if len(values) > 0 else None,
                    _numeric_or_none(values[1]) if len(values) > 1 else None,
                ]
    return result


def _log_scales(properties: Mapping[str, Any]) -> dict[str, bool]:
    result = dict(PLOT_LOG_SCALES_DEFAULT)
    raw = properties.get("log_scales")
    if isinstance(raw, Mapping):
        for axis in ("x", "y", "z"):
            result[axis] = _bool(raw.get(axis, result[axis]))
    return result


def _plot_type_from_context(context: PropertyEditAdapterContext) -> str:
    type_id = str(getattr(context.node, "type_id", "") or "").strip()
    return _GENERIC_PLOT_TYPE_BY_NODE_TYPE.get(type_id, "")


def _supports_colormap(context: PropertyEditAdapterContext) -> bool:
    type_id = str(getattr(context.node, "type_id", "") or "").strip()
    return bool(_GENERIC_SUPPORTS_COLORMAP_BY_NODE_TYPE.get(type_id))


def _is_plot(context: PropertyEditAdapterContext) -> bool:
    type_id = str(getattr(context.node, "type_id", "") or "").strip()
    return type_id in _GENERIC_PLOT_TYPE_BY_NODE_TYPE


def _connected_tabular_source_node(context: PropertyEditAdapterContext) -> Any | None:
    node_id = str(getattr(context.node, "node_id", "") or "").strip()
    nodes = context.workspace_nodes if isinstance(context.workspace_nodes, Mapping) else {}
    edges = context.workspace_edges or ()
    edge_values = edges.values() if isinstance(edges, Mapping) else edges
    for edge in edge_values:
        if (
            str(getattr(edge, "target_node_id", "") or "").strip() == node_id
            and str(getattr(edge, "target_port_key", "") or "").strip() == "series"
            and str(getattr(edge, "source_port_key", "") or "").strip() in {"table_data", "array_data"}
        ):
            source_node = nodes.get(str(getattr(edge, "source_node_id", "") or "").strip())
            if source_node is not None and str(getattr(source_node, "type_id", "") or "").strip() == "tabular.input":
                return source_node
    return None


def _tabular_column_options(context: PropertyEditAdapterContext) -> tuple[str, ...]:
    source_node = _connected_tabular_source_node(context)
    if source_node is None:
        return ()
    from ea_node_editor.ui.tabular_preview_provider import TabularPreviewProvider

    properties = dict(_node_properties(source_node))
    source_path = context.source_path_for_property("path")
    if source_path:
        properties["path"] = source_path

    def project_context() -> tuple[str | None, dict[str, Any] | None]:
        metadata = dict(context.project_metadata) if isinstance(context.project_metadata, Mapping) else None
        return context.project_path, metadata

    try:
        payload = TabularPreviewProvider(project_context_provider=project_context).table_window_payload(
            properties,
            {"row_limit": 1},
            mode="inline",
            include_schema=True,
        )
    except Exception:
        return ()
    if str(payload.get("state", "")).strip() != "ready":
        return ()
    schema = payload.get("schema")
    columns = schema.get("columns") if isinstance(schema, Mapping) else ()
    result: list[str] = []
    for column in columns if isinstance(columns, Iterable) else ():
        if not isinstance(column, Mapping):
            continue
        name = str(column.get("name", "") or "").strip()
        if name:
            result.append(name)
    return tuple(dict.fromkeys(result))


def _base_item(
    *,
    key: str,
    label: str,
    value: Any,
    type_: str = "str",
    editor_mode: str = "text",
    group: str,
    dirty: bool = False,
    enum_values: Iterable[str] = (),
    help_text: str = "",
    placeholder_text: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": key,
        "label": label,
        "type": type_,
        "value": value,
        "enum_values": list(enum_values),
        "inline_editor": "",
        "editor_mode": editor_mode,
        "group": group,
        "dirty": bool(dirty),
    }
    if help_text:
        item["help_text"] = help_text
    if placeholder_text:
        item["placeholder_text"] = placeholder_text
    return item


def _visible_axis_keys(context: PropertyEditAdapterContext) -> tuple[str, ...]:
    return ("x", "y", "z") if _plot_type_from_context(context) in _THREE_DIMENSIONAL_PLOT_TYPES else ("x", "y")


def _axis_field_item(
    *,
    key: str,
    role: str,
    label: str,
    value: Any,
    type_: str,
    editor_mode: str,
    dirty: bool,
    reset_value: Any,
    placeholder_text: str = "",
) -> dict[str, Any]:
    item = _base_item(
        key=key,
        label=label,
        type_=type_,
        value=value,
        editor_mode=editor_mode,
        group="Axes",
        dirty=dirty,
        placeholder_text=placeholder_text,
    )
    item["role"] = role
    item["reset_value"] = reset_value
    return item


def _axis_control_items(context: PropertyEditAdapterContext) -> list[dict[str, Any]]:
    properties = _node_properties(context.node)
    limits = _axis_limits(properties)
    log_scales = _log_scales(properties)
    items: list[dict[str, Any]] = []
    for item_index, axis in enumerate(_visible_axis_keys(context)):
        values = limits[axis]
        min_value = values[0] if len(values) > 0 else None
        max_value = values[1] if len(values) > 1 else None
        log_value = log_scales[axis]
        default_limits = PLOT_AXIS_LIMITS_DEFAULT[axis]
        default_log = PLOT_LOG_SCALES_DEFAULT[axis]
        fields = [
            _axis_field_item(
                key=f"{_AXIS_LIMIT_PREFIX}{axis}_min",
                role="min",
                label="Min",
                value="" if min_value is None else min_value,
                type_="float",
                editor_mode="text",
                dirty=min_value != default_limits[0],
                reset_value="",
                placeholder_text="Auto",
            ),
            _axis_field_item(
                key=f"{_AXIS_LIMIT_PREFIX}{axis}_max",
                role="max",
                label="Max",
                value="" if max_value is None else max_value,
                type_="float",
                editor_mode="text",
                dirty=max_value != default_limits[1],
                reset_value="",
                placeholder_text="Auto",
            ),
            _axis_field_item(
                key=f"{_LOG_SCALE_PREFIX}{axis}",
                role="log",
                label="Scale",
                value=log_value,
                type_="bool",
                editor_mode="toggle",
                dirty=log_value != default_log,
                reset_value=False,
            ),
        ]
        item = _base_item(
            key=f"{_AXIS_CONTROL_PREFIX}{axis}",
            label=f"{axis.upper()} Axis",
            type_="object",
            value={
                "axis": axis,
                "min": "" if min_value is None else min_value,
                "max": "" if max_value is None else max_value,
                "log": log_value,
            },
            editor_mode="axis_compact",
            group="Axes",
            dirty=any(bool(field.get("dirty")) for field in fields),
            help_text="Auto range unless Min or Max is set." if item_index == 0 else "",
        )
        item["fields"] = fields
        items.append(item)
    return items


def _tabular_mapping_roles(plot_type: str) -> tuple[tuple[str, str, str], ...]:
    if plot_type in {PLOT_TYPE_LINE, PLOT_TYPE_SCATTER}:
        return (("x", "X Column", "single"), ("y", "Y Columns", "multi"), ("columns", "Available Columns", "multi"))
    if plot_type == PLOT_TYPE_BAR:
        return (
            ("x", "X Column", "single"),
            ("category", "Category Column", "single"),
            ("y", "Y Columns", "multi"),
            ("columns", "Available Columns", "multi"),
        )
    if plot_type == PLOT_TYPE_HISTOGRAM:
        return (("values", "Value Columns", "multi"), ("columns", "Available Columns", "multi"))
    if plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR, PLOT_TYPE_SURFACE}:
        return (("z", "Z Column", "single"), ("values", "Value Columns", "multi"), ("columns", "Available Columns", "multi"))
    if plot_type in {PLOT_TYPE_POINT_CLOUD, PLOT_TYPE_STREAMLINES}:
        return (("x", "X Column", "single"), ("y", "Y Column", "single"), ("z", "Z Column", "single"), ("columns", "Available Columns", "multi"))
    return (("columns", "Available Columns", "multi"),)


def _tabular_mapping_items(context: PropertyEditAdapterContext) -> list[dict[str, Any]]:
    properties = _node_properties(context.node)
    mapping = _mapping(properties.get(PLOT_TABULAR_MAPPING_PROPERTY))
    column_options = _tabular_column_options(context)
    items: list[dict[str, Any]] = []
    for role, label, cardinality in _tabular_mapping_roles(_plot_type_from_context(context)):
        value = _string_list(mapping.get(role)) if cardinality == "multi" else _text(mapping.get(role)).strip()
        items.append(
            _base_item(
                key=f"{_TABULAR_MAPPING_PREFIX}{role}",
                label=label,
                type_="list" if cardinality == "multi" else "str",
                value=value,
                editor_mode="chip_list" if cardinality == "multi" else "editable_combo",
                group="Data",
                dirty=bool(value),
                enum_values=column_options,
                placeholder_text="Auto infer" if not column_options else "Search columns",
                help_text="Leave empty to infer from the connected tabular source.",
            )
        )
    row_limit = _positive_int_or_none(mapping.get("row_limit"))
    items.append(
        _base_item(
            key=f"{_TABULAR_MAPPING_PREFIX}row_limit",
            label="Row Limit",
            type_="int",
            value="" if row_limit is None else row_limit,
            group="Data",
            dirty=row_limit is not None,
            help_text="Blank uses the table row count, or the preview safety limit when the row count is unknown.",
        )
    )
    return items


def _option_items(context: PropertyEditAdapterContext) -> list[dict[str, Any]]:
    options = _mapping(_node_properties(context.node).get("plot_options"))
    plot_type = _plot_type_from_context(context)
    items: list[dict[str, Any]] = []
    if plot_type in _TWO_DIMENSIONAL_LIVE_PLOT_TYPES:
        theme = _plot_theme(options.get("plot_theme"))
        items.extend(
            [
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}plot_theme",
                    label="Plot Theme",
                    value=theme,
                    editor_mode="editable_combo",
                    enum_values=_PLOT_THEME_VALUES,
                    group="Investigation",
                    dirty="plot_theme" in options,
                    placeholder_text="system",
                ),
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}hover_readout",
                    label="Hover Readout",
                    type_="bool",
                    value=_bool(options.get("hover_readout", False)),
                    editor_mode="toggle",
                    group="Investigation",
                    dirty="hover_readout" in options,
                ),
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}vertical_guide",
                    label="Vertical Guide",
                    type_="bool",
                    value=_bool(options.get("vertical_guide", False)),
                    editor_mode="toggle",
                    group="Investigation",
                    dirty="vertical_guide" in options,
                ),
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}crosshair",
                    label="Crosshair",
                    type_="bool",
                    value=_bool(options.get("crosshair", False)),
                    editor_mode="toggle",
                    group="Investigation",
                    dirty="crosshair" in options,
                ),
            ]
        )
    if plot_type == PLOT_TYPE_HISTOGRAM:
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}bins",
                label="Histogram Bins",
                type_="int",
                value=options.get("bins", ""),
                group="Rendering",
                dirty="bins" in options,
            )
        )
    if plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR}:
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}aspect",
                label="Image Aspect",
                value=str(options.get("aspect", "") or ""),
                editor_mode="editable_combo",
                enum_values=("auto", "equal"),
                group="Rendering",
                dirty="aspect" in options,
                placeholder_text="auto",
            )
        )
    if plot_type == PLOT_TYPE_SURFACE:
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}show_edges",
                label="Show Mesh Edges",
                type_="bool",
                value=_bool(options.get("show_edges", False)),
                editor_mode="toggle",
                group="Rendering",
                dirty="show_edges" in options,
            )
        )
    if plot_type == PLOT_TYPE_POINT_CLOUD:
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}point_size",
                label="Point Size",
                type_="float",
                value=options.get("point_size", ""),
                group="Rendering",
                dirty="point_size" in options,
            )
        )
    if plot_type == PLOT_TYPE_STREAMLINES:
        items.extend(
            [
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}line_width",
                    label="Line Width",
                    type_="float",
                    value=options.get("line_width", ""),
                    group="Rendering",
                    dirty="line_width" in options,
                ),
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}color",
                    label="Line Color",
                    value=str(options.get("color", "") or ""),
                    editor_mode="color",
                    group="Rendering",
                    dirty="color" in options,
                ),
                _base_item(
                    key=f"{_PLOT_OPTION_PREFIX}render_lines_as_tubes",
                    label="Render Lines As Tubes",
                    type_="bool",
                    value=_bool(options.get("render_lines_as_tubes", True)),
                    editor_mode="toggle",
                    group="Rendering",
                    dirty="render_lines_as_tubes" in options,
                ),
            ]
        )
    if plot_type in {PLOT_TYPE_SURFACE, PLOT_TYPE_POINT_CLOUD, PLOT_TYPE_STREAMLINES}:
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}axes",
                label="Show 3D Axes",
                type_="bool",
                value=_bool(options.get("axes", True)),
                editor_mode="toggle",
                group="Rendering",
                dirty="axes" in options,
            )
        )
    if _supports_colormap(context):
        cmap = str(options.get("cmap", options.get("colormap", "")) or "").strip()
        items.append(
            _base_item(
                key=f"{_PLOT_OPTION_PREFIX}cmap",
                label="Backend Colormap Override",
                value=cmap,
                editor_mode="editable_combo",
                enum_values=PLOT_COLORMAP_VALUES,
                group="Rendering",
                dirty=bool(cmap),
                placeholder_text="Use Colormap property",
            )
        )
    unsupported = sorted(key for key in options if key not in _SUPPORTED_PLOT_OPTION_KEYS)
    if unsupported:
        items.append(
            _base_item(
                key=_UNSUPPORTED_OPTIONS_KEY,
                label="Unsupported Saved Options",
                value=", ".join(unsupported),
                editor_mode="summary",
                group="Rendering",
                dirty=False,
                help_text="These saved backend options are preserved but are not editable in the inspector.",
            )
        )
        items.append(
            _base_item(
                key=_UNSUPPORTED_OPTIONS_RESET_KEY,
                label="Clear Unsupported Options",
                type_="bool",
                value=False,
                editor_mode="toggle",
                group="Rendering",
                dirty=False,
                help_text="Enable once to remove unsupported saved backend options.",
            )
        )
    return items


def _update_axis_limits(properties: Mapping[str, Any], key: str, value: Any) -> PropertyEditRewrite | None:
    suffix = key.removeprefix(_AXIS_LIMIT_PREFIX)
    axis, _, bound = suffix.partition("_")
    if axis not in {"x", "y", "z"} or bound not in {"min", "max"}:
        return None
    limits = _axis_limits(properties)
    index = 0 if bound == "min" else 1
    limits[axis][index] = _numeric_or_none(value)
    return PropertyEditRewrite("axis_limits", limits)


def _update_log_scales(properties: Mapping[str, Any], key: str, value: Any) -> PropertyEditRewrite | None:
    axis = key.removeprefix(_LOG_SCALE_PREFIX)
    if axis not in {"x", "y", "z"}:
        return None
    values = _log_scales(properties)
    values[axis] = _bool(value)
    return PropertyEditRewrite("log_scales", values)


def _update_tabular_mapping(properties: Mapping[str, Any], key: str, value: Any) -> PropertyEditRewrite | None:
    role = key.removeprefix(_TABULAR_MAPPING_PREFIX)
    if role not in {"x", "y", "z", "category", "values", "columns", "row_limit"}:
        return None
    mapping = _mapping(properties.get(PLOT_TABULAR_MAPPING_PROPERTY))
    if role == "row_limit":
        row_limit = _positive_int_or_none(value)
        if row_limit is None:
            mapping.pop(role, None)
        else:
            mapping[role] = row_limit
    elif role in {"y", "values", "columns"}:
        values = _string_list(value)
        if values:
            mapping[role] = values
        else:
            mapping.pop(role, None)
    else:
        text = _text(value).strip()
        if text:
            mapping[role] = text
        else:
            mapping.pop(role, None)
    return PropertyEditRewrite(PLOT_TABULAR_MAPPING_PROPERTY, mapping)


def _update_plot_options(properties: Mapping[str, Any], key: str, value: Any) -> PropertyEditRewrite | None:
    options = _mapping(properties.get("plot_options"))
    if key == _UNSUPPORTED_OPTIONS_RESET_KEY:
        if _bool(value):
            options = {option_key: option_value for option_key, option_value in options.items() if option_key in _SUPPORTED_PLOT_OPTION_KEYS}
        return PropertyEditRewrite("plot_options", options)
    option_key = key.removeprefix(_PLOT_OPTION_PREFIX)
    if option_key not in _SUPPORTED_PLOT_OPTION_KEYS:
        return None
    if option_key in {"show_edges", "render_lines_as_tubes", "axes"} | _PLOT_INVESTIGATION_BOOL_OPTION_KEYS:
        options[option_key] = _bool(value)
    elif option_key == "plot_theme":
        text = _text(value).strip()
        if text:
            options[option_key] = _plot_theme(text)
        else:
            options.pop(option_key, None)
    elif option_key == "bins":
        numeric = _positive_int_or_none(value)
        if numeric is None:
            options.pop(option_key, None)
        else:
            options[option_key] = numeric
    elif option_key in {"point_size", "line_width"}:
        numeric_value = _numeric_or_none(value)
        if numeric_value is None:
            options.pop(option_key, None)
        else:
            options[option_key] = numeric_value
    elif option_key == "cmap":
        text = _text(value).strip()
        options.pop("colormap", None)
        if text:
            options["cmap"] = text
        else:
            options.pop("cmap", None)
    else:
        text = _text(value).strip()
        if text:
            options[option_key] = text
        else:
            options.pop(option_key, None)
    return PropertyEditRewrite("plot_options", options)


class PlotPropertyEditAdapter:
    def rewrite_property_edit(
        self,
        context: PropertyEditAdapterContext,
        *,
        key: str,
        value: Any,
    ) -> PropertyEditRewrite | None:
        if getattr(context.node, "type_id", "") == "plot.signal":
            if key == "x_column":
                if type(value) not in {str, int} or type(value) is int and value < 0:
                    raise ValueError("X column must be an exact name or zero-based position")
                return PropertyEditRewrite(key, value)
            if key == "y_columns":
                if not isinstance(value, (list, tuple)) or any(type(item) not in {str, int} or type(item) is int and item < 0 for item in value):
                    raise ValueError("Y columns must be an ordered list of exact names or zero-based positions")
                return PropertyEditRewrite(key, list(dict.fromkeys(value)))
            return None
        if not _is_plot(context):
            return None
        normalized_key = str(key or "").strip()
        properties = _node_properties(context.node)
        if normalized_key.startswith(_AXIS_LIMIT_PREFIX):
            return _update_axis_limits(properties, normalized_key, value)
        if normalized_key.startswith(_LOG_SCALE_PREFIX):
            return _update_log_scales(properties, normalized_key, value)
        if normalized_key.startswith(_TABULAR_MAPPING_PREFIX):
            return _update_tabular_mapping(properties, normalized_key, value)
        if normalized_key.startswith(_PLOT_OPTION_PREFIX) or normalized_key == _UNSUPPORTED_OPTIONS_RESET_KEY:
            return _update_plot_options(properties, normalized_key, value)
        return None

    def build_property_items(
        self,
        context: PropertyEditAdapterContext,
        items: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if getattr(context.node, "type_id", "") == "plot.signal":
            return enrich_signal_property_items(items, connected_signal_value(
                context.node.node_id, context.workspace_edges, context.current_output_provider,
            ))
        if not _is_plot(context):
            return [dict(item) for item in items]

        properties = _node_properties(context.node)
        hidden_keys = set(_PLOT_JSON_PROPERTY_KEYS)
        result: list[dict[str, Any]] = []
        axis_controls_inserted = False
        mapping_inserted = False
        options_inserted = False
        for raw_item in items:
            item = dict(raw_item)
            key = str(item.get("key", "") or "").strip()
            if key in {"axis_limits", "log_scales"}:
                if not axis_controls_inserted:
                    result.extend(_axis_control_items(context))
                    axis_controls_inserted = True
                continue
            if key == PLOT_TABULAR_MAPPING_PROPERTY:
                result.extend(_tabular_mapping_items(context))
                mapping_inserted = True
                continue
            if key == "plot_options":
                result.extend(_option_items(context))
                options_inserted = True
                continue
            if key in hidden_keys:
                continue
            result.append(item)

        if not axis_controls_inserted:
            result.extend(_axis_control_items(context))
        if not mapping_inserted:
            result.extend(_tabular_mapping_items(context))
        if not options_inserted:
            result.extend(_option_items(context))
        return result


def create_plot_property_edit_adapters() -> tuple[PlotPropertyEditAdapter, ...]:
    return (PlotPropertyEditAdapter(),)


__all__ = [
    "PlotPropertyEditAdapter",
    "create_plot_property_edit_adapters",
]
