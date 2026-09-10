# Purpose: Generic (backend-neutral) plot node definition and plugin registration.
# Map: feature_routes/plotter_nodes
# Tests: tests/test_plot_node_contracts.py
# Landmarks: PlotNodeDefinition, GenericPlotNodePlugin
from __future__ import annotations

import copy
import math
import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type_spec
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.output_artifacts import (
    allocate_managed_output,
    artifact_store_for_context,
    persist_artifact_store,
    register_staged_path_artifact,
)
from ea_node_editor.nodes.plugin_contracts import PluginDescriptor
from ea_node_editor.runtime_contracts import (
    ARRAY_DATA_REF_TYPE_ID,
    ARRAY_SLICE_2D_REF_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    GRAPH_ARRAY_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
    TABULAR_WINDOW_REF_TYPE_ID,
    ArrayDataRef,
    ArraySlice2DRef,
    ArraySlice2DRequest,
    TabularDataRef,
    TabularWindowRef,
    coerce_array_data_ref,
    coerce_array_slice_2d_ref,
    coerce_tabular_data_ref,
    coerce_tabular_window_ref,
)

if TYPE_CHECKING:
    from ea_node_editor.execution.plot_backend import PlotExportResult, PlotRenderRequest

# Keep node registration independent from execution implementation imports.
AUTO_PLOT_BACKEND_ID = "auto"
MATPLOTLIB_PLOT_BACKEND_ID = "matplotlib"
PLOT_SURFACE_STATIC_EXPORT = "static_export"
PLOT_SURFACE_DATA_EXPORT = "data_export"
PLOT_TYPE_LINE = "line"
PLOT_TYPE_SCATTER = "scatter"
PLOT_TYPE_BAR = "bar"
PLOT_TYPE_HISTOGRAM = "histogram"
PLOT_TYPE_HEATMAP = "heatmap"
PLOT_TYPE_CONTOUR = "contour"
PLOT_TYPE_SURFACE = "surface"
PLOT_TYPE_POINT_CLOUD = "point_cloud"
PLOT_TYPE_STREAMLINES = "streamlines"
GENERIC_PLOT_SERIES_RUNTIME_SHAPES = (
    "numpy arrays",
    "lists of numbers",
    "dict-of-arrays",
)
PLOT_NODE_CATEGORY_PATH = ("Plot",)
PLOT_AXIS_LIMITS_DEFAULT = {
    "x": [None, None],
    "y": [None, None],
    "z": [None, None],
}
PLOT_LOG_SCALES_DEFAULT = {
    "x": False,
    "y": False,
    "z": False,
}
PLOT_COLORMAP_VALUES = (
    "viridis",
    "plasma",
    "inferno",
    "magma",
    "cividis",
    "turbo",
    "coolwarm",
)
PLOT_STATIC_EXPORT_FORMATS = ("png", "svg", "pdf")
PLOT_DATA_EXPORT_FORMATS = ("csv",)
PLOT_BACKEND_VALUES = (AUTO_PLOT_BACKEND_ID, MATPLOTLIB_PLOT_BACKEND_ID)
PLOT_RUNTIME_SHAPE_TEXT = ", ".join(GENERIC_PLOT_SERIES_RUNTIME_SHAPES)
PLOT_TABULAR_MAPPING_PROPERTY = "tabular_mapping"
# Plot surfaces render at canvas resolution; series read from tabular refs are
# decimated to this budget (min-max envelope / stride sampling — visually
# lossless). An explicit ``tabular_mapping.row_limit`` remains a hard source
# row cap applied before decimation. Data exports stream the full source.
TABULAR_PLOT_MAX_POINTS_PER_SERIES = 4000
TABULAR_PLOT_DIAGNOSTIC_HINT = (
    "Check Header Row, Skip Rows, selected columns, Tabular Mapping, and numeric formatting."
)


@dataclass(frozen=True, slots=True)
class PlotNodeDefinition:
    type_id: str
    display_name: str
    plot_type: str
    supports_colormap: bool = False
    description: str = ""
    keywords: tuple[str, ...] = ()


PLOT_NODE_DEFINITIONS = (
    PlotNodeDefinition(
        "plot.scatter",
        "Scatter Plot",
        PLOT_TYPE_SCATTER,
        keywords=("scatter", "points", "correlation"),
    ),
    PlotNodeDefinition("plot.bar", "Bar Plot", PLOT_TYPE_BAR, keywords=("bar", "chart", "categories")),
    PlotNodeDefinition(
        "plot.histogram",
        "Histogram Plot",
        PLOT_TYPE_HISTOGRAM,
        keywords=("histogram", "distribution", "bins"),
    ),
    PlotNodeDefinition(
        "plot.heatmap",
        "Heatmap Plot",
        PLOT_TYPE_HEATMAP,
        supports_colormap=True,
        keywords=("heatmap", "matrix", "colormap"),
    ),
    PlotNodeDefinition(
        "plot.contour",
        "Contour Plot",
        PLOT_TYPE_CONTOUR,
        supports_colormap=True,
        keywords=("contour", "levels", "colormap"),
    ),
    PlotNodeDefinition(
        "plot.surface",
        "Surface Plot",
        PLOT_TYPE_SURFACE,
        supports_colormap=True,
        keywords=("surface", "3d", "colormap"),
    ),
    PlotNodeDefinition(
        "plot.point_cloud",
        "Point Cloud Plot",
        PLOT_TYPE_POINT_CLOUD,
        supports_colormap=True,
        keywords=("point cloud", "3d", "scatter"),
    ),
    PlotNodeDefinition(
        "plot.streamlines",
        "Streamlines Plot",
        PLOT_TYPE_STREAMLINES,
        supports_colormap=True,
        keywords=("streamlines", "vector field", "flow"),
    ),
)
PLOT_NODE_DEFINITION_BY_TYPE_ID = {
    definition.type_id: definition for definition in PLOT_NODE_DEFINITIONS
}
PLOT_NODE_TYPE_IDS = tuple(definition.type_id for definition in PLOT_NODE_DEFINITIONS)


def _standard_plot_ports(plot_type: str) -> tuple[PortSpec, ...]:
    if plot_type in {
        PLOT_TYPE_LINE,
        PLOT_TYPE_SCATTER,
        PLOT_TYPE_BAR,
        PLOT_TYPE_HISTOGRAM,
    }:
        series_data_type = DOUBLE_DATA_TYPE_ID
        accepted_series_data_types = (
            INTEGER_DATA_TYPE_ID,
            GRAPH_ARRAY_DATA_TYPE_ID,
            GRAPH_DICTIONARY_DATA_TYPE_ID,
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        )
    elif plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR, PLOT_TYPE_SURFACE}:
        series_data_type = GRAPH_ARRAY_DATA_TYPE_ID
        accepted_series_data_types = (
            GRAPH_DICTIONARY_DATA_TYPE_ID,
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        )
    elif plot_type in {PLOT_TYPE_POINT_CLOUD, PLOT_TYPE_STREAMLINES}:
        series_data_type = GRAPH_DICTIONARY_DATA_TYPE_ID
        accepted_series_data_types = (
            ARRAY_DATA_REF_TYPE_ID,
            ARRAY_SLICE_2D_REF_TYPE_ID,
            TABULAR_DATA_REF_TYPE_ID,
            TABULAR_WINDOW_REF_TYPE_ID,
        )
    else:
        raise ValueError(f"Unknown generic plot type: {plot_type!r}.")

    return (
        PortSpec(
            "series",
            "in",
            "data",
            series_data_type,
            label="Series",
            required=True,
            data_access="list",
            accepted_data_types=accepted_series_data_types,
            description="One or more numeric series, array references, or tabular references to plot.",
        ),
        PortSpec(
            "static_export",
            "out",
            "data",
            'COREX.DataTypes.Path',
            label="Image Export",
            exposed=True,
            description="Path to the archived plot image when image export is enabled.",
        ),
        PortSpec(
            "data_export",
            "out",
            "data",
            'COREX.DataTypes.Path',
            label="Data Export",
            exposed=True,
            description="Path to the archived plot data file when data export is enabled.",
        ),
        PortSpec(
            "exports",
            "out",
            "data",
            'COREX.Plot.ExportBundle',
            label="Exports",
            exposed=True,
            description="Metadata describing the image and data artifacts created by this plot.",
        ),
    )


def _standard_plot_properties(*, supports_colormap: bool) -> tuple[PropertySpec, ...]:
    properties: list[PropertySpec] = [
        PropertySpec(
            "backend",
            "enum",
            AUTO_PLOT_BACKEND_ID,
            "Backend",
            enum_values=PLOT_BACKEND_VALUES,
            inspector_editor="enum",
            group="Rendering",
        ),
        PropertySpec("title", "str", "", "Title", inline_editor="text", group="Text"),
        PropertySpec("x_label", "str", "", "X Axis Label", inline_editor="text", group="Text"),
        PropertySpec("y_label", "str", "", "Y Axis Label", inline_editor="text", group="Text"),
        PropertySpec("z_label", "str", "", "Z Axis Label", inline_editor="text", group="Text"),
        PropertySpec(
            "axis_limits",
            "json",
            copy.deepcopy(PLOT_AXIS_LIMITS_DEFAULT),
            "Axis Limits",
            inspector_editor="textarea",
            group="Axes",
        ),
        PropertySpec(
            "log_scales",
            "json",
            copy.deepcopy(PLOT_LOG_SCALES_DEFAULT),
            "Log Scales",
            inspector_editor="textarea",
            group="Axes",
        ),
        PropertySpec("grid", "bool", True, "Grid", inspector_editor="toggle", group="Axes"),
        PropertySpec("legend", "bool", True, "Legend", inspector_editor="toggle", group="Text"),
        PropertySpec(
            PLOT_TABULAR_MAPPING_PROPERTY,
            "json",
            {},
            "Tabular Mapping",
            inspector_editor="textarea",
            group="Data",
        ),
    ]
    if supports_colormap:
        properties.append(
            PropertySpec(
                "colormap",
                "enum",
                "viridis",
                "Colormap",
                enum_values=PLOT_COLORMAP_VALUES,
                inspector_editor="enum",
                group="Rendering",
            )
        )
    properties.extend(
        [
            PropertySpec(
                "render_in_canvas",
                "bool",
                True,
                "Render In Canvas",
                inspector_editor="toggle",
                group="Rendering",
            ),
            PropertySpec(
                "archive_export_on_run",
                "bool",
                False,
                "Archive Export On Run",
                inspector_editor="toggle",
                group="Export",
            ),
            PropertySpec(
                "static_export_format",
                "enum",
                "png",
                "Image Export Format",
                enum_values=PLOT_STATIC_EXPORT_FORMATS,
                inspector_editor="enum",
                group="Export",
            ),
            PropertySpec(
                "data_export_format",
                "enum",
                "csv",
                "Data Export Format",
                enum_values=PLOT_DATA_EXPORT_FORMATS,
                inspector_editor="enum",
                group="Export",
            ),
            PropertySpec(
                "plot_options",
                "json",
                {},
                "Plot Options",
                inspector_editor="textarea",
                group="Rendering",
            ),
        ]
    )
    return tuple(properties)


def _plot_node_description(definition: PlotNodeDefinition) -> str:
    if definition.description:
        return definition.description
    return (
        f"Generic {definition.display_name.lower()} node. The variadic series input accepts "
        f"{PLOT_RUNTIME_SHAPE_TEXT} at runtime without requiring numpy as a core dependency."
    )


def _plot_node_spec(definition: PlotNodeDefinition) -> NodeTypeSpec:
    return builtin_node_type_spec(
        type_id=definition.type_id,
        display_name=definition.display_name,
        category_path=PLOT_NODE_CATEGORY_PATH,
        description=_plot_node_description(definition),
        keywords=definition.keywords,
        ports=_standard_plot_ports(definition.plot_type),
        properties=_standard_plot_properties(supports_colormap=definition.supports_colormap),
    )


def _property_defaults(spec: NodeTypeSpec) -> dict[str, Any]:
    return {prop.key: copy.deepcopy(prop.default) for prop in spec.properties}


def _string_property(properties: Mapping[str, Any], key: str) -> str:
    return str(properties.get(key, "") or "").strip()


def _mapping_property(properties: Mapping[str, Any], key: str, default: Mapping[str, Any]) -> dict[str, Any]:
    value = properties.get(key)
    if isinstance(value, Mapping):
        return {str(item_key): copy.deepcopy(item_value) for item_key, item_value in value.items()}
    return copy.deepcopy(dict(default))


def _sequence_value(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _string_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Sequence[object] = (value,)
    elif _sequence_value(value):
        values = value  # type: ignore[assignment]
    else:
        values = (value,)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _positive_int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _column_lookup(columns: Sequence[str]) -> dict[str, str]:
    return {column.casefold(): column for column in columns}


def _existing_columns(columns: Sequence[str], requested: Sequence[str]) -> tuple[str, ...]:
    lookup = _column_lookup(columns)
    selected: list[str] = []
    for item in requested:
        column = lookup.get(str(item).casefold())
        if column and column not in selected:
            selected.append(column)
    return tuple(selected)


def _mapping_column(mapping: Mapping[str, Any], key: str, available: Sequence[str]) -> str:
    selected = _existing_columns(available, _string_list(mapping.get(key)))
    return selected[0] if selected else ""


def _mapping_columns(mapping: Mapping[str, Any], key: str, available: Sequence[str]) -> tuple[str, ...]:
    return _existing_columns(available, _string_list(mapping.get(key)))


def _format_column_names(columns: Sequence[str], *, limit: int = 8) -> str:
    normalized = tuple(str(column) for column in columns if str(column))
    if not normalized:
        return "none"
    visible = ", ".join(repr(column) for column in normalized[:limit])
    remaining = len(normalized) - limit
    if remaining > 0:
        return f"{visible}, and {remaining} more"
    return visible


def _plot_type_label(plot_type: str) -> str:
    return str(plot_type or "plot").replace("_", " ")


def _missing_columns(available: Sequence[str], requested: Sequence[str]) -> tuple[str, ...]:
    lookup = _column_lookup(available)
    return tuple(column for column in requested if column.casefold() not in lookup)


def _tabular_column_details(available: Sequence[str], all_columns: Sequence[str]) -> str:
    details = f"Loaded columns: {_format_column_names(all_columns)}."
    if tuple(available) != tuple(all_columns):
        details += f" Columns available to this plot: {_format_column_names(available)}."
    return details


def _validate_tabular_columns(
    *,
    plot_type: str,
    source: str,
    requested: Sequence[str],
    available: Sequence[str],
    all_columns: Sequence[str],
) -> None:
    missing = _missing_columns(available, requested)
    if not missing:
        return
    noun = "columns" if len(missing) != 1 else "column"
    raise ValueError(
        f"Tabular {_plot_type_label(plot_type)} plot cannot use {source} {noun} "
        f"{_format_column_names(missing)}. "
        f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
    )


def _validate_tabular_mapping_keys(
    *,
    plot_type: str,
    mapping: Mapping[str, Any],
    keys: Sequence[str],
    available: Sequence[str],
    all_columns: Sequence[str],
) -> None:
    for key in keys:
        _validate_tabular_columns(
            plot_type=plot_type,
            source=f"tabular_mapping.{key}",
            requested=_string_list(mapping.get(key)),
            available=available,
            all_columns=all_columns,
        )


def _raise_empty_tabular_plot(
    *,
    plot_type: str,
    available: Sequence[str],
    all_columns: Sequence[str],
) -> None:
    raise ValueError(
        f"Tabular {_plot_type_label(plot_type)} plot input has no data rows after parsing. "
        f"{_tabular_column_details(available, all_columns)} "
        "Check Header Row, Skip Rows, and any tabular_mapping row_limit."
    )


def _raise_no_numeric_tabular_columns(
    *,
    plot_type: str,
    available: Sequence[str],
    all_columns: Sequence[str],
) -> None:
    raise ValueError(
        f"Tabular {_plot_type_label(plot_type)} plot needs numeric columns, but none of the "
        "columns available to this plot contain numeric values. "
        f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
    )


def _raise_empty_tabular_series(
    *,
    plot_type: str,
    columns: Sequence[str],
    available: Sequence[str],
    all_columns: Sequence[str],
) -> None:
    raise ValueError(
        f"Tabular {_plot_type_label(plot_type)} plot produced no numeric points from "
        f"{_format_column_names(columns)}. "
        f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
    )


def _ref_selected_columns(ref: TabularDataRef) -> tuple[str, ...]:
    metadata = ref.metadata if isinstance(ref.metadata, Mapping) else {}
    node_options = metadata.get("node_options")
    candidates: object = ()
    if isinstance(node_options, Mapping):
        candidates = node_options.get("selected_columns", ())
    if not candidates:
        candidates = metadata.get("selected_columns", ())
    return _string_list(candidates)


def _array_slice_metadata(ref: ArrayDataRef) -> dict[str, int]:
    metadata = ref.metadata if isinstance(ref.metadata, Mapping) else {}
    node_options = metadata.get("node_options")
    raw = node_options.get("array_slice_2d") if isinstance(node_options, Mapping) else None
    if not isinstance(raw, Mapping):
        raw = metadata.get("array_slice_2d") if isinstance(metadata.get("array_slice_2d"), Mapping) else {}
    return {
        "row_offset": max(0, int(raw.get("row_offset", 0) or 0)),
        "column_offset": max(0, int(raw.get("column_offset", 0) or 0)),
        "row_limit": max(1, int(raw.get("row_limit", 50) or 50)),
        "column_limit": max(1, int(raw.get("column_limit", 50) or 50)),
    }


def _numeric_value(value: object) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _json_safe_plot_cell(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _column_dtype_is_numeric(dtype: str) -> bool:
    normalized = str(dtype or "").casefold()
    if not normalized or "bool" in normalized:
        return False
    return any(token in normalized for token in ("int", "float", "double", "decimal", "number"))


def _semantic_x_column(
    columns: Sequence[Any],
    numeric_columns: Sequence[str],
    available: Sequence[str],
) -> str:
    numeric = set(numeric_columns)
    by_name = {str(getattr(column, "name", "") or ""): column for column in columns}
    for name in available:
        column = by_name.get(name)
        dtype = str(getattr(column, "dtype", "") or "").casefold() if column is not None else ""
        lowered = name.casefold()
        if name not in numeric and (
            "date" in dtype
            or "time" in dtype
            or "date" in lowered
            or "time" in lowered
            or "index" in lowered
        ):
            return name
    for name in available:
        if name not in numeric:
            return name
    return ""


def _series_label(column: str, fallback: str = "") -> str:
    return str(column or fallback or "series").strip()


def _import_numpy() -> Any:
    import numpy

    return numpy


def _float_array_or_none(np: Any, values: Any) -> Any | None:
    """Coerce one column to float64 (NaN for empty cells) or None when the
    column holds non-numeric values — mirrors ``_column_values_are_numeric``."""

    kind = getattr(getattr(values, "dtype", None), "kind", "O")
    if kind in "iuf":
        return values.astype(np.float64, copy=False)
    if kind == "b":
        return None
    converted = np.empty(len(values), dtype=np.float64)
    for index, value in enumerate(values):
        numeric = _numeric_value(value)
        if numeric is None:
            if value is None or str(value).strip() == "":
                converted[index] = math.nan
                continue
            return None
        converted[index] = float(numeric)
    return converted


def _numeric_arrays_from_columns(
    np: Any,
    schema_columns: Sequence[Any],
    columns_data: Mapping[str, Any],
    available: Sequence[str],
) -> tuple[tuple[str, ...], dict[str, Any]]:
    by_name = {str(getattr(column, "name", "") or ""): column for column in schema_columns}
    numeric: dict[str, Any] = {}
    names: list[str] = []
    for name in available:
        values = columns_data.get(name)
        if values is None:
            continue
        column = by_name.get(name)
        dtype = str(getattr(column, "dtype", "") or "") if column is not None else ""
        coerced = _float_array_or_none(np, values)
        if coerced is None:
            continue
        if _column_dtype_is_numeric(dtype) or bool(np.isfinite(coerced).any()):
            numeric[name] = coerced
            names.append(name)
    return tuple(names), numeric


def _decimation_meta(method: str, original_rows: int, points: int) -> dict[str, Any]:
    return {"method": method, "original_rows": int(original_rows), "points": int(points)}


def _xy_series_from_arrays(
    np: Any,
    *,
    columns_data: Mapping[str, Any],
    numeric_arrays: Mapping[str, Any],
    x_column: str,
    y_column: str,
    max_points: int,
    label: str = "",
) -> dict[str, Any]:
    from ea_node_editor.execution.plot_series_decimation import (
        DECIMATION_METHOD_NONE,
        DECIMATION_METHOD_STRIDE,
        decimate_xy,
        stride_sample_indices,
    )

    y_values = numeric_arrays[y_column]
    total_rows = int(len(y_values))
    series: dict[str, Any] = {"label": _series_label(label or y_column)}
    if x_column and x_column not in numeric_arrays:
        # Label axis: positions stay sequential after dropping empty y cells;
        # the label subset follows the sampled rows.
        labels = columns_data[x_column]
        finite = np.isfinite(y_values)
        kept_y = y_values[finite]
        kept_labels = (
            labels[finite]
            if hasattr(labels, "__getitem__") and hasattr(labels, "dtype")
            else np.asarray(list(labels), dtype=object)[finite]
        )
        if len(kept_y) > max_points:
            indices = stride_sample_indices(len(kept_y), max_points)
            kept_y = kept_y[indices]
            kept_labels = kept_labels[indices]
            method = DECIMATION_METHOD_STRIDE
        else:
            method = DECIMATION_METHOD_NONE
        series.update(
            {
                "x": list(range(len(kept_y))),
                "y": kept_y.tolist(),
                "x_labels": ["" if value is None else str(value) for value in kept_labels.tolist()],
                "decimation": _decimation_meta(method, total_rows, len(kept_y)),
            }
        )
    else:
        x_values = (
            numeric_arrays[x_column]
            if x_column
            else np.arange(total_rows, dtype=np.float64)
        )
        out_x, out_y, meta = decimate_xy(x_values, y_values, max_points)
        series.update({"x": out_x, "y": out_y, "decimation": meta})
    if x_column:
        series["x_column"] = x_column
    series["y_column"] = y_column
    return series


def _values_series_from_arrays(
    np: Any,
    column: str,
    numeric_arrays: Mapping[str, Any],
    max_points: int,
) -> dict[str, Any]:
    from ea_node_editor.execution.plot_series_decimation import (
        DECIMATION_METHOD_NONE,
        DECIMATION_METHOD_STRIDE,
        stride_sample_indices,
    )

    values = numeric_arrays.get(column)
    if values is None:
        return {
            "label": _series_label(column),
            "values": [],
            "value_column": column,
            "decimation": _decimation_meta(DECIMATION_METHOD_NONE, 0, 0),
        }
    total_rows = int(len(values))
    finite = values[np.isfinite(values)]
    if len(finite) > max_points:
        finite = finite[stride_sample_indices(len(finite), max_points)]
        method = DECIMATION_METHOD_STRIDE
    else:
        method = DECIMATION_METHOD_NONE
    return {
        "label": _series_label(column),
        "values": finite.tolist(),
        "value_column": column,
        "decimation": _decimation_meta(method, total_rows, len(finite)),
    }


def _grid_from_arrays(
    np: Any,
    columns: Sequence[str],
    numeric_arrays: Mapping[str, Any],
    total_rows: int,
    max_points: int,
) -> tuple[list[list[float]], dict[str, Any]]:
    from ea_node_editor.execution.plot_series_decimation import (
        DECIMATION_METHOD_NONE,
        DECIMATION_METHOD_STRIDE,
        stride_sample_indices,
    )

    stacked = np.column_stack(
        [
            np.nan_to_num(
                numeric_arrays.get(column, np.zeros(total_rows, dtype=np.float64)),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
            for column in columns
        ]
    )
    if stacked.shape[0] > max_points:
        stacked = stacked[stride_sample_indices(stacked.shape[0], max_points)]
        method = DECIMATION_METHOD_STRIDE
    else:
        method = DECIMATION_METHOD_NONE
    return stacked.tolist(), _decimation_meta(method, total_rows, stacked.shape[0])


def _points_from_arrays(
    np: Any,
    columns: Sequence[str],
    numeric_arrays: Mapping[str, Any],
    max_points: int,
) -> tuple[list[list[float]], dict[str, Any]] | None:
    from ea_node_editor.execution.plot_series_decimation import (
        DECIMATION_METHOD_NONE,
        DECIMATION_METHOD_STRIDE,
        stride_sample_indices,
    )

    arrays = [numeric_arrays.get(column) for column in columns[:3]]
    if any(array is None for array in arrays):
        return None
    stacked = np.column_stack(arrays)
    mask = np.isfinite(stacked).all(axis=1)
    total_rows = int(stacked.shape[0])
    stacked = stacked[mask]
    if stacked.shape[0] == 0:
        return None
    if stacked.shape[0] > max_points:
        stacked = stacked[stride_sample_indices(stacked.shape[0], max_points)]
        method = DECIMATION_METHOD_STRIDE
    else:
        method = DECIMATION_METHOD_NONE
    return stacked.tolist(), _decimation_meta(method, total_rows, stacked.shape[0])


def _named_or_numeric_columns(
    available: Sequence[str],
    numeric_columns: Sequence[str],
    names: Sequence[str],
) -> tuple[str, ...]:
    lookup = _column_lookup(available)
    matched: list[str] = []
    for name in names:
        column = lookup.get(name.casefold())
        if column and column not in matched:
            matched.append(column)
    if len(matched) == len(names):
        return tuple(matched)
    return tuple(numeric_columns[: len(names)])


def _series_from_tabular_ref(
    ref: TabularDataRef,
    *,
    plot_type: str,
    mapping: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )

    service = shared_tabular_loader_cache_service()
    service.ensure_table_ref(ref)
    schema = service.schema(ref)
    all_columns = tuple(column.name for column in schema.columns)
    requested_mapped_columns = _string_list(mapping.get("columns"))
    _validate_tabular_columns(
        plot_type=plot_type,
        source="tabular_mapping.columns",
        requested=requested_mapped_columns,
        available=all_columns,
        all_columns=all_columns,
    )
    mapped_columns = _existing_columns(all_columns, requested_mapped_columns)
    requested_selected_columns = _ref_selected_columns(ref)
    _validate_tabular_columns(
        plot_type=plot_type,
        source="selected",
        requested=requested_selected_columns,
        available=all_columns,
        all_columns=all_columns,
    )
    selected_columns = _existing_columns(all_columns, requested_selected_columns)
    available = mapped_columns or selected_columns or all_columns
    if not available:
        raise ValueError(
            f"Tabular {_plot_type_label(plot_type)} plot input has no columns to plot. "
            f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
        )
    row_limit = _positive_int_or_none(mapping.get("row_limit"))
    columns_data = service.column_arrays(ref, columns=available, row_limit=row_limit)
    series, warnings = _series_from_tabular_columns(
        columns_data=columns_data,
        schema_columns=schema.columns,
        available=available,
        all_columns=all_columns,
        plot_type=plot_type,
        mapping=mapping,
        warnings=(),
    )
    source_ref = {"ref": ref.to_payload(), "row_offset": 0, "row_limit": row_limit}
    for item in series:
        item.setdefault("source_ref", source_ref)
    return series, warnings


def _series_from_tabular_window_ref(
    ref: TabularWindowRef,
    *,
    plot_type: str,
    mapping: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    from ea_node_editor.addons.tabular_data.extraction_nodes import _table_window_request_from_ref
    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )

    service = shared_tabular_loader_cache_service()
    service.ensure_table_ref(ref.table_data)
    schema = service.schema(ref.table_data)
    all_columns = tuple(column.name for column in schema.columns)
    window_request = _table_window_request_from_ref(ref)
    window_columns = service.window_columns(ref.table_data, window_request)
    requested_mapped_columns = _string_list(mapping.get("columns"))
    _validate_tabular_columns(
        plot_type=plot_type,
        source="tabular_mapping.columns",
        requested=requested_mapped_columns,
        available=window_columns,
        all_columns=all_columns,
    )
    available = _existing_columns(window_columns, requested_mapped_columns) or tuple(window_columns)
    if not available:
        raise ValueError(
            f"Tabular {_plot_type_label(plot_type)} plot input has no columns to plot. "
            f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
        )
    mapping_limit = _positive_int_or_none(mapping.get("row_limit"))
    window_limit = window_request.row_limit if window_request.row_limit > 0 else None
    limits = [limit for limit in (mapping_limit, window_limit) if limit is not None]
    effective_limit = min(limits) if limits else None
    columns_data = service.column_arrays(
        ref.table_data,
        columns=available,
        row_offset=window_request.row_offset,
        row_limit=effective_limit,
    )
    series, warnings = _series_from_tabular_columns(
        columns_data=columns_data,
        schema_columns=schema.columns,
        available=available,
        all_columns=all_columns,
        plot_type=plot_type,
        mapping=mapping,
        warnings=(),
    )
    source_ref = {
        "ref": ref.table_data.to_payload(),
        "row_offset": window_request.row_offset,
        "row_limit": effective_limit,
        "columns": list(window_columns),
    }
    for item in series:
        item.setdefault("source_ref", source_ref)
    return series, warnings


def _series_from_tabular_columns(
    *,
    columns_data: Mapping[str, Any],
    schema_columns: Sequence[Any],
    available: Sequence[str],
    all_columns: Sequence[str],
    plot_type: str,
    mapping: Mapping[str, Any],
    warnings: tuple[str, ...],
    max_points: int = TABULAR_PLOT_MAX_POINTS_PER_SERIES,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    np = _import_numpy()
    numeric_columns, numeric_arrays = _numeric_arrays_from_columns(
        np, schema_columns, columns_data, available
    )
    total_rows = max((len(values) for values in columns_data.values()), default=0)
    if total_rows == 0:
        _raise_empty_tabular_plot(plot_type=plot_type, available=available, all_columns=all_columns)

    x_column = _mapping_column(mapping, "x", available)
    category_column = _mapping_column(mapping, "category", available)
    y_columns = _mapping_columns(mapping, "y", available)
    explicit_x_column = bool(x_column)
    explicit_y_columns = bool(y_columns)
    value_columns = _mapping_columns(mapping, "values", available)
    z_column = _mapping_column(mapping, "z", available)

    if plot_type in {PLOT_TYPE_LINE, PLOT_TYPE_SCATTER}:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("x", "y"),
            available=available,
            all_columns=all_columns,
        )
        if not x_column:
            semantic = _semantic_x_column(schema_columns, numeric_columns, available)
            if semantic:
                x_column = semantic
            elif len(numeric_columns) > 1:
                x_column = numeric_columns[0]
        if not y_columns:
            y_columns = tuple(column for column in numeric_columns if column != x_column)
        if not y_columns and x_column in numeric_columns:
            y_columns = (x_column,)
            x_column = ""
        if plot_type == PLOT_TYPE_SCATTER and len(numeric_columns) >= 2 and not explicit_x_column and not explicit_y_columns:
            x_column = numeric_columns[0]
            y_columns = (numeric_columns[1],)
        if not y_columns:
            _raise_no_numeric_tabular_columns(
                plot_type=plot_type,
                available=available,
                all_columns=all_columns,
            )
        series = tuple(
            _xy_series_from_arrays(
                np,
                columns_data=columns_data,
                numeric_arrays=numeric_arrays,
                x_column=x_column,
                y_column=column,
                max_points=max_points,
            )
            for column in y_columns
        )
        if not any(item.get("y") for item in series):
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=y_columns,
                available=available,
                all_columns=all_columns,
            )
        return series, warnings

    if plot_type == PLOT_TYPE_BAR:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("x", "category", "y"),
            available=available,
            all_columns=all_columns,
        )
        if not x_column:
            x_column = category_column or _semantic_x_column(schema_columns, numeric_columns, available)
        if not y_columns:
            y_columns = tuple(column for column in numeric_columns if column != x_column)
        if not y_columns and numeric_columns:
            y_columns = (numeric_columns[0],)
            if x_column == y_columns[0]:
                x_column = ""
        if not y_columns:
            _raise_no_numeric_tabular_columns(
                plot_type=plot_type,
                available=available,
                all_columns=all_columns,
            )
        series = tuple(
            _xy_series_from_arrays(
                np,
                columns_data=columns_data,
                numeric_arrays=numeric_arrays,
                x_column=x_column,
                y_column=column,
                max_points=max_points,
            )
            for column in y_columns
        )
        if not any(item.get("y") for item in series):
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=y_columns,
                available=available,
                all_columns=all_columns,
            )
        return series, warnings

    if plot_type == PLOT_TYPE_HISTOGRAM:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("values",),
            available=available,
            all_columns=all_columns,
        )
        columns = value_columns or numeric_columns
        if not columns:
            _raise_no_numeric_tabular_columns(
                plot_type=plot_type,
                available=available,
                all_columns=all_columns,
            )
        series = tuple(
            _values_series_from_arrays(np, column, numeric_arrays, max_points)
            for column in columns
        )
        if not any(item.get("values") for item in series):
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=columns,
                available=available,
                all_columns=all_columns,
            )
        return series, warnings

    if plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR, PLOT_TYPE_SURFACE}:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("values", "z"),
            available=available,
            all_columns=all_columns,
        )
        columns = value_columns or tuple(column for column in numeric_columns if column != z_column)
        if z_column and z_column not in columns:
            columns = (z_column,)
        if not columns:
            _raise_no_numeric_tabular_columns(
                plot_type=plot_type,
                available=available,
                all_columns=all_columns,
            )
        if not any(column in numeric_columns for column in columns):
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=columns,
                available=available,
                all_columns=all_columns,
            )
        grid, decimation = _grid_from_arrays(np, columns, numeric_arrays, total_rows, max_points)
        return (
            {
                "label": "tabular grid",
                "values": grid,
                "columns": list(columns),
                "decimation": decimation,
            },
        ), warnings

    if plot_type == PLOT_TYPE_POINT_CLOUD:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("x", "y", "z"),
            available=available,
            all_columns=all_columns,
        )
        xyz = (
            _mapping_column(mapping, "x", available),
            _mapping_column(mapping, "y", available),
            _mapping_column(mapping, "z", available),
        )
        columns = tuple(column for column in xyz if column) or _named_or_numeric_columns(
            available,
            numeric_columns,
            ("x", "y", "z"),
        )
        if len(columns) < 3:
            raise ValueError(
                "Point cloud auto tabular plotting requires x, y, and z columns. "
                f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
            )
        sampled = _points_from_arrays(np, columns, numeric_arrays, max_points)
        if sampled is None:
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=columns[:3],
                available=available,
                all_columns=all_columns,
            )
        points, decimation = sampled
        return (
            {
                "label": "tabular point cloud",
                "points": points,
                "columns": list(columns[:3]),
                "decimation": decimation,
            },
        ), warnings

    if plot_type == PLOT_TYPE_STREAMLINES:
        _validate_tabular_mapping_keys(
            plot_type=plot_type,
            mapping=mapping,
            keys=("x", "y", "z"),
            available=available,
            all_columns=all_columns,
        )
        columns = _named_or_numeric_columns(available, numeric_columns, ("x", "y", "z"))
        if len(columns) < 3:
            raise ValueError(
                "Streamline auto tabular plotting requires named or mapped x, y, and z columns. "
                f"{_tabular_column_details(available, all_columns)} {TABULAR_PLOT_DIAGNOSTIC_HINT}"
            )
        sampled = _points_from_arrays(np, columns, numeric_arrays, max_points)
        if sampled is None:
            _raise_empty_tabular_series(
                plot_type=plot_type,
                columns=columns[:3],
                available=available,
                all_columns=all_columns,
            )
        points, decimation = sampled
        return (
            {
                "label": "tabular streamlines",
                "points": points,
                "columns": list(columns[:3]),
                "decimation": decimation,
            },
        ), warnings

    from ea_node_editor.execution.plot_backend import normalize_generic_plot_series
    from ea_node_editor.execution.plot_series_decimation import stride_sample_indices

    # Unknown plot types fall back to bounded row mappings.
    indices = stride_sample_indices(total_rows, max_points)
    bounded_rows = [
        {name: _json_safe_plot_cell(columns_data[name][int(index)]) for name in available}
        for index in indices
    ]
    return normalize_generic_plot_series(bounded_rows), warnings


def _array_rows_from_ref(ref: ArrayDataRef) -> tuple[tuple[Any, ...], ...]:
    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )

    service = shared_tabular_loader_cache_service()
    service.ensure_array_ref(ref)
    selection = _array_slice_metadata(ref)
    array_slice = service.slice_2d(
        ref,
        ArraySlice2DRequest(
            row_offset=selection["row_offset"],
            row_limit=selection["row_limit"],
            column_offset=selection["column_offset"],
            column_limit=selection["column_limit"],
        ),
    )
    return tuple(tuple(row) for row in array_slice.values)


def _array_rows_from_slice_ref(ref: ArraySlice2DRef) -> tuple[tuple[Any, ...], ...]:
    from ea_node_editor.addons.tabular_data.extraction_nodes import load_array_slice_2d

    array_slice = load_array_slice_2d(ref)
    return tuple(tuple(row) for row in array_slice.values)


def _series_from_array_rows(rows: Sequence[Sequence[Any]], *, plot_type: str) -> tuple[dict[str, Any], ...]:
    if not rows:
        return ()
    from ea_node_editor.execution.plot_series_decimation import stride_sample_rows

    rows, decimation = stride_sample_rows(rows, TABULAR_PLOT_MAX_POINTS_PER_SERIES)
    width = max((len(row) for row in rows), default=0)
    if plot_type in {PLOT_TYPE_HEATMAP, PLOT_TYPE_CONTOUR, PLOT_TYPE_SURFACE}:
        return ({"label": "array grid", "values": [list(row) for row in rows], "decimation": decimation},)
    if plot_type == PLOT_TYPE_HISTOGRAM:
        return ({"label": "array values", "values": [value for row in rows for value in row], "decimation": decimation},)
    if plot_type == PLOT_TYPE_SCATTER and width >= 2:
        return (
            {
                "label": "array scatter",
                "x": [row[0] for row in rows],
                "y": [row[1] for row in rows],
                "decimation": decimation,
            },
        )
    if plot_type == PLOT_TYPE_POINT_CLOUD and width >= 3:
        return ({"label": "array point cloud", "points": [list(row[:3]) for row in rows], "decimation": decimation},)
    if plot_type == PLOT_TYPE_STREAMLINES and width >= 3:
        return ({"label": "array streamlines", "points": [list(row[:3]) for row in rows], "decimation": decimation},)
    series: list[dict[str, Any]] = []
    for column in range(width):
        values = [row[column] for row in rows if column < len(row)]
        series.append({"label": f"column_{column + 1}", "values": values, "decimation": decimation})
    return tuple(series)


def _series_with_source_ref(
    series: tuple[dict[str, Any], ...],
    source_ref: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    return tuple({**item, "source_ref": dict(source_ref)} for item in series)


def _series_from_array_ref(ref: ArrayDataRef, *, plot_type: str) -> tuple[dict[str, Any], ...]:
    selection = _array_slice_metadata(ref)
    source_ref = {"kind": "array_ref", "ref": ref.to_payload(), **selection}
    return _series_with_source_ref(
        _series_from_array_rows(_array_rows_from_ref(ref), plot_type=plot_type),
        source_ref,
    )


def _series_from_array_slice_ref(ref: ArraySlice2DRef, *, plot_type: str) -> tuple[dict[str, Any], ...]:
    source_ref = {"kind": "array_slice_2d_ref", "ref": ref.to_payload()}
    return _series_with_source_ref(
        _series_from_array_rows(_array_rows_from_slice_ref(ref), plot_type=plot_type),
        source_ref,
    )


def _coerces_to_tabular_or_array_ref(value: object) -> bool:
    return (
        coerce_tabular_data_ref(value) is not None
        or coerce_array_data_ref(value) is not None
        or coerce_tabular_window_ref(value) is not None
        or coerce_array_slice_2d_ref(value) is not None
    )


def _normalize_plot_series_for_context(
    value: object,
    *,
    plot_type: str,
    properties: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    mapping = _mapping_property(properties, PLOT_TABULAR_MAPPING_PROPERTY, {})
    table_ref = coerce_tabular_data_ref(value)
    if table_ref is not None:
        return _series_from_tabular_ref(table_ref, plot_type=plot_type, mapping=mapping)
    array_ref = coerce_array_data_ref(value)
    if array_ref is not None:
        return _series_from_array_ref(array_ref, plot_type=plot_type), ()
    window_ref = coerce_tabular_window_ref(value)
    if window_ref is not None:
        return _series_from_tabular_window_ref(window_ref, plot_type=plot_type, mapping=mapping)
    array_slice_ref = coerce_array_slice_2d_ref(value)
    if array_slice_ref is not None:
        return _series_from_array_slice_ref(array_slice_ref, plot_type=plot_type), ()
    if _sequence_value(value) and any(_coerces_to_tabular_or_array_ref(item) for item in value):  # type: ignore[union-attr]
        series: list[dict[str, Any]] = []
        warnings: list[str] = []
        for item in value:  # type: ignore[union-attr]
            item_series, item_warnings = _normalize_plot_series_for_context(
                item,
                plot_type=plot_type,
                properties=properties,
            )
            series.extend(item_series)
            warnings.extend(item_warnings)
        return tuple(series), tuple(dict.fromkeys(warnings))
    from ea_node_editor.execution.plot_backend import normalize_generic_plot_series

    return normalize_generic_plot_series(value), ()


def _plot_options(definition: PlotNodeDefinition, properties: Mapping[str, Any]) -> dict[str, Any]:
    options = _mapping_property(properties, "plot_options", {})
    options.update(
        {
            "axis_limits": _mapping_property(properties, "axis_limits", PLOT_AXIS_LIMITS_DEFAULT),
            "log_scales": _mapping_property(properties, "log_scales", PLOT_LOG_SCALES_DEFAULT),
            "grid": bool(properties.get("grid", True)),
            "legend": bool(properties.get("legend", True)),
            "render_in_canvas": bool(properties.get("render_in_canvas", False)),
            "z_label": _string_property(properties, "z_label"),
        }
    )
    if definition.supports_colormap:
        options["cmap"] = _string_property(properties, "colormap") or "viridis"
    return options


def build_generic_plot_render_request(
    *,
    node_type_id: str,
    properties: Mapping[str, Any],
    series_input: Any,
) -> tuple[Any, tuple[str, ...]]:
    from ea_node_editor.execution.plot_backend import build_plot_render_request

    definition = PLOT_NODE_DEFINITION_BY_TYPE_ID.get(str(node_type_id or "").strip())
    if definition is None:
        raise ValueError(f"Unknown generic plot node type: {node_type_id!r}.")
    series, warnings = _normalize_plot_series_for_context(
        series_input,
        plot_type=definition.plot_type,
        properties=properties,
    )
    return (
        build_plot_render_request(
            plot_type=definition.plot_type,
            series=series,
            properties=properties,
            options=_plot_options(definition, properties),
        ),
        warnings,
    )


def _default_backend_per_type(definition: PlotNodeDefinition) -> dict[str, str]:
    return {
        "default": MATPLOTLIB_PLOT_BACKEND_ID,
        definition.plot_type: MATPLOTLIB_PLOT_BACKEND_ID,
    }


def _export_format(properties: Mapping[str, Any], key: str, default: str) -> str:
    normalized = str(properties.get(key, default) or default).strip().lower().lstrip(".")
    return normalized or default


def _runtime_artifact_metadata(result: PlotExportResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "backend_id": result.backend_id,
        "format": result.format,
        "metadata": copy.deepcopy(result.metadata),
    }


class GenericPlotNodePlugin:
    def __init__(self, definition: PlotNodeDefinition) -> None:
        self._definition = definition
        self._spec = _plot_node_spec(definition)

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        from ea_node_editor.execution.plot_backend import build_plot_render_request

        properties = _property_defaults(self._spec)
        properties.update(dict(ctx.properties or {}))
        series, warnings = _normalize_plot_series_for_context(
            ctx.inputs.get("series"),
            plot_type=self._definition.plot_type,
            properties=properties,
        )
        render_request = build_plot_render_request(
            plot_type=self._definition.plot_type,
            series=series,
            properties=properties,
            options=_plot_options(self._definition, properties),
        )
        outputs: dict[str, Any] = {}
        if bool(properties.get("archive_export_on_run", False)):
            outputs.update(self._archive_exports(ctx, render_request, properties))
        return NodeResult(outputs=outputs, warnings=warnings)

    def _archive_exports(
        self,
        ctx: ExecutionContext,
        render_request: PlotRenderRequest,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        from ea_node_editor.execution.plot_backend import (
            PlotDataExportRequest,
            PlotStaticExportRequest,
            create_plot_backend_registry,
        )

        backend_id = _string_property(properties, "backend") or AUTO_PLOT_BACKEND_ID
        registry = create_plot_backend_registry()
        default_backend_per_type = _default_backend_per_type(self._definition)
        static_backend = registry.resolve(
            backend_id,
            plot_type=self._definition.plot_type,
            surface=PLOT_SURFACE_STATIC_EXPORT,
            plot_default_backend_per_type=default_backend_per_type,
            require_headless_safe=True,
        )
        data_backend = registry.resolve(
            backend_id,
            plot_type=self._definition.plot_type,
            surface=PLOT_SURFACE_DATA_EXPORT,
            plot_default_backend_per_type=default_backend_per_type,
            require_headless_safe=True,
        )

        static_format = _export_format(properties, "static_export_format", "png")
        data_format = _export_format(properties, "data_export_format", "csv")
        static_result: PlotExportResult | None = None
        data_result: PlotExportResult | None = None

        def write_static(output_path):
            nonlocal static_result
            static_result = static_backend.export_static(
                PlotStaticExportRequest(
                    render_request=render_request,
                    output_path=output_path,
                    format=static_format,
                )
            )

        def write_data(output_path):
            nonlocal data_result
            data_result = _write_full_fidelity_tabular_export(render_request, output_path, data_format)
            if data_result is None:
                data_result = _write_full_fidelity_array_export(render_request, output_path, data_format)
            if data_result is not None:
                return
            data_result = data_backend.export_data(
                PlotDataExportRequest(
                    render_request=render_request,
                    output_path=output_path,
                    format=data_format,
                )
            )

        store = artifact_store_for_context(ctx)
        touched_relative_paths: list[str] = []
        registered_ids: list[str] = []
        try:
            static_target = allocate_managed_output(
                ctx,
                output_key="static_export",
                default_suffix=f".{static_format}",
                managed_subdirectory="plots",
            )
            touched_relative_paths.append(static_target.relative_path)
            write_static(static_target.path)
            registered_ids.append(static_target.artifact_id)
            static_ref = register_staged_path_artifact(
                ctx,
                store=store,
                artifact_id=static_target.artifact_id,
                payload_path=static_target.path,
                relative_path=static_target.relative_path,
                slot=static_target.slot,
                format=static_target.format,
                entry_metadata=static_target.entry_metadata,
            )

            data_target = allocate_managed_output(
                ctx,
                output_key="data_export",
                default_suffix=f".{data_format}",
                managed_subdirectory="plots",
            )
            touched_relative_paths.append(data_target.relative_path)
            write_data(data_target.path)
            registered_ids.append(data_target.artifact_id)
            data_ref = register_staged_path_artifact(
                ctx,
                store=store,
                artifact_id=data_target.artifact_id,
                payload_path=data_target.path,
                relative_path=data_target.relative_path,
                slot=data_target.slot,
                format=data_target.format,
                entry_metadata=data_target.entry_metadata,
            )
            persist_artifact_store(ctx, store)
        except BaseException:
            try:
                store.discard_staged_entries(registered_ids)
            except BaseException:
                pass
            try:
                store.discard_staged_paths(touched_relative_paths)
            except BaseException:
                pass
            try:
                persist_artifact_store(ctx, store)
            except BaseException:
                pass
            raise
        return {
            "static_export": static_ref,
            "data_export": data_ref,
            "exports": {
                "static_export": static_ref,
                "data_export": data_ref,
                "static_metadata": _runtime_artifact_metadata(static_result),
                "data_metadata": _runtime_artifact_metadata(data_result),
            },
        }


def _write_full_fidelity_tabular_export(
    render_request: "PlotRenderRequest",
    output_path: Any,
    data_format: str,
) -> "PlotExportResult | None":
    """Stream the full source table for the data export.

    Plot surfaces consume decimated series; the data export must reproduce
    every source row. When all series originate from one tabular ref, the
    export streams that ref through the shared loader service instead of
    writing the decimated points.
    """

    if data_format != "csv":
        return None
    series = render_request.series
    if not series:
        return None
    sources = [item.get("source_ref") for item in series]
    if any(not isinstance(source, Mapping) for source in sources):
        return None
    first = sources[0]
    if any(source != first for source in sources[1:]):
        return None
    ref = coerce_tabular_data_ref(first.get("ref"))
    if ref is None:
        return None

    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )
    from ea_node_editor.execution.plot_backend import PlotExportResult
    from ea_node_editor.runtime_contracts import TabularArrowBatchOptions

    try:
        import pyarrow
        import pyarrow.csv as pa_csv
    except ModuleNotFoundError:
        return None

    service = shared_tabular_loader_cache_service()
    service.ensure_table_ref(ref)
    schema = service.schema(ref)
    schema_columns = tuple(column.name for column in schema.columns)
    requested_columns = _string_list(first.get("columns"))
    columns = tuple(name for name in requested_columns if name in schema_columns) or schema_columns
    if not columns:
        return None
    row_limit = first.get("row_limit")
    exported_rows = 0
    options = TabularArrowBatchOptions(
        row_limit=int(row_limit) if isinstance(row_limit, int) and row_limit > 0 else 2_147_483_647,
        batch_size=65_536,
        row_offset=int(first.get("row_offset") or 0),
        columns=columns,
    )
    writer = None
    try:
        for batch in service.arrow_batches(ref, options):
            if isinstance(batch, list):
                batch = pyarrow.Table.from_pylist(
                    [{name: row.get(name) for name in columns} for row in batch]
                )
            if writer is None:
                writer = pa_csv.CSVWriter(str(output_path), batch.schema)
            writer.write(batch)
            exported_rows += int(getattr(batch, "num_rows", 0) or 0)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        return None
    return PlotExportResult(
        backend_id="tabular_full_fidelity",
        output_path=output_path,
        format=data_format,
        metadata={
            "row_count": exported_rows,
            "column_count": len(columns),
            "columns": list(columns),
            "source": "tabular_ref",
        },
    )


def _write_full_fidelity_array_export(
    render_request: "PlotRenderRequest",
    output_path: Any,
    data_format: str,
) -> "PlotExportResult | None":
    if data_format != "csv":
        return None
    series = render_request.series
    if not series:
        return None
    sources = [item.get("source_ref") for item in series]
    if any(not isinstance(source, Mapping) for source in sources):
        return None
    first = sources[0]
    if any(source != first for source in sources[1:]):
        return None

    kind = str(first.get("kind", "") or "")
    rows: tuple[tuple[Any, ...], ...]
    if kind == "array_ref":
        ref = coerce_array_data_ref(first.get("ref"))
        if ref is None:
            return None
        rows = _array_rows_from_ref(ref)
    elif kind == "array_slice_2d_ref":
        ref = coerce_array_slice_2d_ref(first.get("ref"))
        if ref is None:
            return None
        rows = _array_rows_from_slice_ref(ref)
    else:
        return None

    from ea_node_editor.execution.plot_backend import PlotExportResult

    column_count = max((len(row) for row in rows), default=0)
    if column_count <= 0:
        return None
    columns = [f"column_{index + 1}" for index in range(column_count)]
    with open(output_path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[index] if index < len(row) else "" for index in range(column_count)])
    return PlotExportResult(
        backend_id="array_full_fidelity",
        output_path=output_path,
        format=data_format,
        metadata={
            "row_count": len(rows),
            "column_count": column_count,
            "columns": columns,
            "source": kind,
        },
    )


def _plot_descriptor(definition: PlotNodeDefinition) -> PluginDescriptor:
    spec = _plot_node_spec(definition)
    return PluginDescriptor(
        spec=spec,
        factory=lambda definition=definition: GenericPlotNodePlugin(definition),
    )


PLOT_NODE_DESCRIPTORS = tuple(_plot_descriptor(definition) for definition in PLOT_NODE_DEFINITIONS)

__all__ = [
    "GenericPlotNodePlugin",
    "PLOT_AXIS_LIMITS_DEFAULT",
    "PLOT_BACKEND_VALUES",
    "PLOT_COLORMAP_VALUES",
    "PLOT_DATA_EXPORT_FORMATS",
    "PLOT_LOG_SCALES_DEFAULT",
    "PLOT_NODE_CATEGORY_PATH",
    "PLOT_NODE_DEFINITION_BY_TYPE_ID",
    "PLOT_NODE_DEFINITIONS",
    "PLOT_NODE_DESCRIPTORS",
    "PLOT_NODE_TYPE_IDS",
    "PLOT_RUNTIME_SHAPE_TEXT",
    "PLOT_STATIC_EXPORT_FORMATS",
    "PlotNodeDefinition",
    "TABULAR_PLOT_MAX_POINTS_PER_SERIES",
    "build_generic_plot_render_request",
]
