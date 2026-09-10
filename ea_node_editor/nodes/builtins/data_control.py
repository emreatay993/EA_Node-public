# Purpose: Keep trusted control-node execution helpers, normalization, and size resolvers.
# Map: feature_routes/surface_input_and_inline_controls.md
# Tests: tests/test_boolean_toggle_node.py, tests/test_panel_node.py, tests/test_canvas_import_runtime.py
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ea_node_editor.graph.boundary_adapters import register_node_type_size_resolver
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.runtime_contracts import DataTree, RuntimeArtifactRef

BOOLEAN_TOGGLE_TYPE_ID = "data.boolean_toggle"
BOOLEAN_TOGGLE_SURFACE_VARIANT = "boolean_toggle"
NUMBER_SLIDER_TYPE_ID = "data.number_slider"
NUMBER_SLIDER_SURFACE_VARIANT = "number_slider"
PANEL_TYPE_ID = "data.panel"
PANEL_SURFACE_VARIANT = "panel"
SELECT_TYPE_ID = "data.select"
SELECT_SURFACE_VARIANT = "select"
# Fixed pill geometry shared by the Python metrics, the QML metrics mirror, and
# the size resolver; the pill body is width-resizable but height-locked.
NUMBER_SLIDER_PILL_HEIGHT = 40.0
NUMBER_SLIDER_DEFAULT_WIDTH = 280.0
NUMBER_SLIDER_MIN_WIDTH = 220.0
NUMBER_SLIDER_ROUNDING_DECIMAL = "decimal"
NUMBER_SLIDER_ROUNDING_INTEGER = "integer"
NUMBER_SLIDER_ROUNDINGS = (
    NUMBER_SLIDER_ROUNDING_DECIMAL,
    NUMBER_SLIDER_ROUNDING_INTEGER,
)
NUMBER_SLIDER_MAX_DECIMALS = 6
NUMBER_SLIDER_DEFAULT_VALUE = 5.0
NUMBER_SLIDER_DEFAULT_MINIMUM = 0.0
NUMBER_SLIDER_DEFAULT_MAXIMUM = 10.0
NUMBER_SLIDER_DEFAULT_DECIMALS = 2
PANEL_MODE_TEXT = 0
PANEL_MODE_DATA = 1
PANEL_DEFAULT_WIDTH = 280.0
PANEL_DEFAULT_HEIGHT = 180.0
PANEL_MIN_WIDTH = 120.0
PANEL_MIN_HEIGHT = 40.0
PANEL_PORT_CENTER_OFFSET = 20.0

_NUMBER_SLIDER_RANGE_KEYS = ("minimum", "maximum", "value")
_NUMBER_SLIDER_KEY_FALLBACKS = {
    "value": NUMBER_SLIDER_DEFAULT_VALUE,
    "minimum": NUMBER_SLIDER_DEFAULT_MINIMUM,
    "maximum": NUMBER_SLIDER_DEFAULT_MAXIMUM,
}


def _default_select_options() -> list[dict[str, str]]:
    return [
        {"name": "Option A", "value": "0"},
        {"name": "Option B", "value": "1"},
    ]


def execute_boolean_toggle(ctx: ExecutionContext) -> NodeResult:
    return NodeResult(
        outputs={"boolean": DataTree.from_item(bool(ctx.properties.get("value", False)))}
    )


def normalize_select_options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return _default_select_options()
    options = []
    for row in value:
        if not isinstance(row, Mapping):
            continue
        name = row.get("name", "")
        selected_value = row.get("value", "")
        options.append(
            {
                "name": "" if name is None else str(name),
                "value": "" if selected_value is None else str(selected_value),
            }
        )
    return options or _default_select_options()


def normalize_select_properties(values: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    if "options" in normalized:
        normalized["options"] = normalize_select_options(normalized["options"])
    if "selected_index" in normalized:
        try:
            selected_index = int(normalized["selected_index"])
        except (TypeError, ValueError):
            selected_index = 0
        option_count = len(normalized.get("options") or _default_select_options())
        normalized["selected_index"] = max(0, min(option_count - 1, selected_index))
    return normalized


def select_settings(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    provided = dict(properties or {})
    return normalize_select_properties(
        {
            "options": provided.get("options", _default_select_options()),
            "selected_index": provided.get("selected_index", 0),
        }
    )


def execute_select(ctx: ExecutionContext) -> NodeResult:
    settings = select_settings(ctx.properties)
    selected_value = settings["options"][settings["selected_index"]]["value"]
    return NodeResult(outputs={"selected_value": DataTree.from_item(selected_value)})


def _panel_item(value: str, *, parse_numbers: bool) -> Any:
    value = value.strip()
    if not parse_numbers:
        return value
    if not value:
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        number = float(value)
    except ValueError:
        return value
    return number if math.isfinite(number) else value


def _panel_path(header: str) -> tuple[int, ...]:
    parts = header[1:].strip().split(";")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f"Invalid Panel branch header: {header!r}")
    try:
        return tuple(int(part.strip()) for part in parts)
    except ValueError as exc:
        raise ValueError(f"Invalid Panel branch header: {header!r}") from exc


def parse_panel_data(value: str, *, parse_numbers: bool = False) -> DataTree:
    text = str(value or "")
    if not text:
        return DataTree()
    branches: dict[tuple[int, ...], list[Any]] = {}
    path = (0,)
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("*"):
            path = _panel_path(stripped)
            branches.setdefault(path, [])
            continue
        branches.setdefault(path, []).append(
            _panel_item(line, parse_numbers=parse_numbers)
        )
    return DataTree(branches)


def execute_panel(ctx: ExecutionContext) -> NodeResult:
    if "input" in ctx.inputs:
        return NodeResult(outputs={"output": ctx.inputs["input"]})
    value = ctx.properties.get("value", "")
    if isinstance(value, RuntimeArtifactRef):
        return NodeResult(outputs={"output": DataTree.from_item(value)})
    value = str(value or "")
    if ctx.properties.get("mode", PANEL_MODE_TEXT) == PANEL_MODE_DATA:
        output = parse_panel_data(
            value,
            parse_numbers=bool(ctx.properties.get("parse_numbers", False)),
        )
    else:
        output = DataTree.from_item(value)
    return NodeResult(outputs={"output": output})


def normalize_number_slider_rounding(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in NUMBER_SLIDER_ROUNDINGS else NUMBER_SLIDER_ROUNDING_DECIMAL


def normalize_number_slider_decimals(value: Any) -> int:
    try:
        decimals = int(value)
    except (TypeError, ValueError):
        return NUMBER_SLIDER_DEFAULT_DECIMALS
    return max(0, min(NUMBER_SLIDER_MAX_DECIMALS, decimals))


def number_slider_step(rounding: str, decimals: int) -> float:
    if normalize_number_slider_rounding(rounding) == NUMBER_SLIDER_ROUNDING_INTEGER:
        return 1.0
    return 10.0 ** -normalize_number_slider_decimals(decimals)


def _finite_float(value: Any, fallback: float) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(candidate):
        return fallback
    return candidate


def number_slider_snapped_value(
    value: float,
    *,
    minimum: float,
    maximum: float,
    rounding: str,
    decimals: int,
) -> float:
    if normalize_number_slider_rounding(rounding) == NUMBER_SLIDER_ROUNDING_INTEGER:
        snapped = float(round(value))
    else:
        snapped = round(value, normalize_number_slider_decimals(decimals))
    return max(minimum, min(maximum, snapped))


def normalize_number_slider_properties(values: dict[str, Any]) -> dict[str, Any]:
    """Sanitize slider properties; cross-field repair only when the full range is present.

    Partial dicts (e.g. per-key creation overrides) must not be clamped against
    defaults — the node's actual bounds may differ from the spec defaults.
    """
    normalized = dict(values)
    if "rounding" in normalized:
        normalized["rounding"] = normalize_number_slider_rounding(normalized["rounding"])
    if "decimals" in normalized:
        normalized["decimals"] = normalize_number_slider_decimals(normalized["decimals"])
    for key in _NUMBER_SLIDER_RANGE_KEYS:
        if key in normalized:
            normalized[key] = _finite_float(normalized[key], _NUMBER_SLIDER_KEY_FALLBACKS[key])
    if not all(key in normalized for key in _NUMBER_SLIDER_RANGE_KEYS):
        return normalized
    rounding = normalize_number_slider_rounding(
        normalized.get("rounding", NUMBER_SLIDER_ROUNDING_DECIMAL)
    )
    decimals = normalize_number_slider_decimals(
        normalized.get("decimals", NUMBER_SLIDER_DEFAULT_DECIMALS)
    )
    step = number_slider_step(rounding, decimals)
    if rounding == NUMBER_SLIDER_ROUNDING_INTEGER:
        normalized["minimum"] = float(round(normalized["minimum"]))
        normalized["maximum"] = float(round(normalized["maximum"]))
    if normalized["maximum"] <= normalized["minimum"]:
        normalized["maximum"] = normalized["minimum"] + step
    normalized["value"] = number_slider_snapped_value(
        normalized["value"],
        minimum=normalized["minimum"],
        maximum=normalized["maximum"],
        rounding=rounding,
        decimals=decimals,
    )
    return normalized


def normalize_number_slider_property_value(key: str, value: Any) -> Any:
    if key in _NUMBER_SLIDER_RANGE_KEYS:
        return _finite_float(value, _NUMBER_SLIDER_KEY_FALLBACKS[key])
    if key == "decimals":
        return normalize_number_slider_decimals(value)
    if key == "rounding":
        return normalize_number_slider_rounding(value)
    return value


def number_slider_settings(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    provided = dict(properties or {})
    return normalize_number_slider_properties(
        {
            "value": provided.get("value", NUMBER_SLIDER_DEFAULT_VALUE),
            "minimum": provided.get("minimum", NUMBER_SLIDER_DEFAULT_MINIMUM),
            "maximum": provided.get("maximum", NUMBER_SLIDER_DEFAULT_MAXIMUM),
            "rounding": provided.get("rounding", NUMBER_SLIDER_ROUNDING_DECIMAL),
            "decimals": provided.get("decimals", NUMBER_SLIDER_DEFAULT_DECIMALS),
        }
    )


def execute_number_slider(ctx: ExecutionContext) -> NodeResult:
    settings = number_slider_settings(ctx.properties)
    if settings["rounding"] == NUMBER_SLIDER_ROUNDING_INTEGER:
        return NodeResult(outputs={"value": int(round(settings["value"]))})
    return NodeResult(outputs={"value": float(settings["value"])})


def _number_slider_node_size(node, _spec, *, base_width: float, base_height: float) -> tuple[float, float]:
    del base_height
    width = float(base_width)
    if getattr(node, "custom_width", None) is None:
        width = max(width, NUMBER_SLIDER_DEFAULT_WIDTH)
    return max(width, NUMBER_SLIDER_MIN_WIDTH), NUMBER_SLIDER_PILL_HEIGHT


def _panel_node_size(node, _spec, *, base_width: float, base_height: float) -> tuple[float, float]:
    width = float(base_width)
    height = float(base_height)
    if getattr(node, "custom_width", None) is None:
        width = max(width, PANEL_DEFAULT_WIDTH)
    if getattr(node, "custom_height", None) is None:
        height = max(height, PANEL_DEFAULT_HEIGHT)
    return max(width, PANEL_MIN_WIDTH), max(height, PANEL_MIN_HEIGHT)


register_node_type_size_resolver(NUMBER_SLIDER_TYPE_ID, _number_slider_node_size)
register_node_type_size_resolver(BOOLEAN_TOGGLE_TYPE_ID, _number_slider_node_size)
register_node_type_size_resolver(PANEL_TYPE_ID, _panel_node_size)
register_node_type_size_resolver(SELECT_TYPE_ID, _number_slider_node_size)
