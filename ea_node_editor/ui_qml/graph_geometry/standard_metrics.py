# Purpose: Measure standard node content and resolve fitted or dedicated-surface dimensions.
# Map: feature_routes/graph_scene_payload_and_projection.md
# Tests: tests/test_graph_scene_presentation_facts.py, tests/test_graph_surface_input_controls.py
# Landmarks: standard_port_row_count; standard_inline_body_height; _standard_inline_min_width; uses_content_sizing; resolved_node_surface_size
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import math
from typing import Any

from ea_node_editor.graph.boundary_adapters import resolve_node_type_size_override
from ea_node_editor.graph.effective_ports import EffectivePort
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.core import (
    TRIGGER_DEFAULT_WIDTH,
    TRIGGER_MIN_WIDTH,
    TRIGGER_SURFACE_VARIANT,
)
from ea_node_editor.nodes.builtins.data_control import (
    BOOLEAN_TOGGLE_SURFACE_VARIANT,
    NUMBER_SLIDER_DEFAULT_WIDTH,
    NUMBER_SLIDER_MIN_WIDTH,
    NUMBER_SLIDER_PILL_HEIGHT,
    NUMBER_SLIDER_SURFACE_VARIANT,
    PANEL_DEFAULT_HEIGHT,
    PANEL_DEFAULT_WIDTH,
    PANEL_MIN_HEIGHT,
    PANEL_MIN_WIDTH,
    PANEL_PORT_CENTER_OFFSET,
    PANEL_SURFACE_VARIANT,
    SELECT_SURFACE_VARIANT,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, inline_property_specs
from ea_node_editor.settings import (
    DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    GRAPH_LABEL_PIXEL_SIZE_MAX,
    GRAPH_LABEL_PIXEL_SIZE_MIN,
    GRAPH_NODE_ICON_PIXEL_SIZE_MAX,
)
from ea_node_editor.ui_qml.surface_contracts import SurfaceLayoutMetrics, surface_spec_for_node_type

from .surface_contract import (
    GraphNodeSurfaceMetrics,
    STANDARD_BODY_LEFT_MARGIN,
    STANDARD_BODY_RIGHT_MARGIN,
    STANDARD_BODY_TOP,
    STANDARD_BOTTOM_PADDING,
    STANDARD_CENTER_GAP,
    STANDARD_COLLAPSED_HEIGHT,
    STANDARD_COLLAPSED_WIDTH,
    STANDARD_DEFAULT_WIDTH,
    STANDARD_HEADER_HEIGHT,
    STANDARD_HEADER_TOP_MARGIN,
    STANDARD_INLINE_ROW_SPACING,
    STANDARD_INLINE_SECTION_PADDING,
    STANDARD_MIN_HEIGHT,
    STANDARD_PORT_CENTER_OFFSET,
    STANDARD_PORT_DOT_RADIUS,
    STANDARD_PORT_GUTTER,
    STANDARD_PORT_HEIGHT,
    STANDARD_PORT_SIDE_MARGIN,
    STANDARD_RESIZE_HANDLE_SIZE,
    STANDARD_TITLE_LEFT_MARGIN,
    STANDARD_TITLE_RIGHT_MARGIN,
    STANDARD_USE_HOST_CHROME,
    VIEWER_BODY_BOTTOM_PADDING,
    VIEWER_LEGACY_DEFAULT_BODY_HEIGHTS,
    _StandardWidthContract,
    _resolved_dimensions,
    _visible_ports_for_layout,
)

_STANDARD_NARROW_TEXT_CHARS = frozenset(" !\"'`.,:;|ijlItfr")
_STANDARD_WIDE_TEXT_CHARS = frozenset("MWQG@#%&wm")
_STANDARD_PUNCTUATION_TEXT_CHARS = frozenset("_-/\\+=*~^()[]{}")
_STANDARD_TEXT_WIDTH_PADDING = 2.0
_STANDARD_TITLE_ICON_SPACING = 6.0
_COLLAPSED_TITLE_LEFT_MARGIN = 10.0
_COLLAPSED_TITLE_RIGHT_MARGIN = 10.0
_COLLAPSED_TITLE_WIDTH_SAFETY_PADDING = 8.0
_COLLAPSED_TITLE_ICON_MAX_RENDER_SIZE = 24.0
_COLLAPSED_GROUP_TITLE_ICON_SPACING = 6.0
_STANDARD_INLINE_LABEL_MIN_WIDTH = 78.0
_STANDARD_INLINE_LABEL_MAX_WIDTH = 320.0
_STANDARD_INLINE_LABEL_TEXT_PADDING = 4.0
_STANDARD_INLINE_ROW_HORIZONTAL_MARGIN = 6.0
_STANDARD_INLINE_ENUM_COMBO_CHROME_WIDTH = 62.0
_STANDARD_INLINE_ENUM_COMBO_MIN_WIDTH = 124.0
_STANDARD_INLINE_LIST_ADD_GAP = 4.0
_STANDARD_INLINE_LIST_ADD_HEIGHT = 26.0
_STANDARD_INLINE_LIST_FALLBACK_ROW_HEIGHT = 142.0
_STANDARD_INLINE_LIST_ITEM_HEIGHT = 28.0
_STANDARD_INLINE_LIST_ITEM_SPACING = 3.0
_STANDARD_INLINE_LIST_VISIBLE_ITEM_CAP = 3
_STANDARD_INLINE_LIST_VALUE_UNSET = object()
_STANDARD_HEADER_BODY_GAP = max(
    0.0,
    STANDARD_BODY_TOP - (STANDARD_HEADER_TOP_MARGIN + STANDARD_HEADER_HEIGHT),
)
_STANDARD_HEADER_CONTENT_VERTICAL_PADDING = max(
    0.0,
    STANDARD_HEADER_HEIGHT - float(GRAPH_LABEL_PIXEL_SIZE_MAX + 2),
)
_FOLDER_EXPLORER_DEFAULT_WIDTH = 620.0
_FOLDER_EXPLORER_DEFAULT_HEIGHT = 420.0
_FOLDER_EXPLORER_PORT_BOTTOM_RESERVE = 30.0
_COMPACT_PILL_BODY_SIDE_MARGIN = 10.0
_COMPACT_SECTION_TITLE_PADDING = 26.0
_COMPACT_SECTION_MIN_WIDTH = 82.0
_TRIGGER_LABEL_PADDING = 14.0
_TRIGGER_LABEL_MIN_WIDTH = 68.0
_DYNAMIC_PORT_HANDLE_TARGET_RADIUS = 7.0
_DYNAMIC_PORT_HANDLE_REST_RADIUS = 3.0
_DYNAMIC_PORT_REMOVE_TARGET_WIDTH = 14.0
_DYNAMIC_PORT_REMOVE_CENTER_INTERVAL = 9.0
_DYNAMIC_PORT_HANDLE_BOTTOM_INSET = 4.0
_DYNAMIC_PORT_HANDLE_CENTER_INTERVAL = 9.0


def _compact_pill_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> GraphNodeSurfaceMetrics:
    variant = str(getattr(spec, "surface_variant", "") or "").strip()
    is_trigger = variant == TRIGGER_SURFACE_VARIANT
    default_width = TRIGGER_DEFAULT_WIDTH if is_trigger else NUMBER_SLIDER_DEFAULT_WIDTH
    min_width = TRIGGER_MIN_WIDTH if is_trigger else NUMBER_SLIDER_MIN_WIDTH
    baseline_title = str(getattr(spec, "display_name", "") or "")
    if is_trigger:
        pixel_size = standard_inline_property_pixel_size(graph_label_pixel_size)
        title_width = max(
            _estimate_standard_text_width(
                node.title,
                pixel_size=pixel_size,
                font_weight="demibold",
            )
            + _TRIGGER_LABEL_PADDING,
            _TRIGGER_LABEL_MIN_WIDTH,
        )
        baseline_title_width = max(
            _estimate_standard_text_width(
                baseline_title,
                pixel_size=pixel_size,
                font_weight="demibold",
            )
            + _TRIGGER_LABEL_PADDING,
            _TRIGGER_LABEL_MIN_WIDTH,
        )
        title_overflow = max(0.0, title_width - baseline_title_width)
    else:
        pixel_size = standard_node_title_pixel_size(graph_label_pixel_size)
        title_section_width = max(
            _estimate_standard_text_width(
                node.title,
                pixel_size=pixel_size,
                font_weight="bold",
            )
            + _COMPACT_SECTION_TITLE_PADDING,
            _COMPACT_SECTION_MIN_WIDTH,
        )
        baseline_section_width = max(
            _estimate_standard_text_width(
                baseline_title,
                pixel_size=pixel_size,
                font_weight="bold",
            )
            + _COMPACT_SECTION_TITLE_PADDING,
            _COMPACT_SECTION_MIN_WIDTH,
        )
        title_overflow = max(0.0, title_section_width - baseline_section_width)
    default_width = round(default_width + title_overflow, 3)
    min_width = round(min_width + title_overflow, 3)
    pill_height = NUMBER_SLIDER_PILL_HEIGHT
    return GraphNodeSurfaceMetrics(
        default_width=default_width,
        default_height=pill_height,
        min_width=min_width,
        min_height=pill_height,
        collapsed_width=STANDARD_COLLAPSED_WIDTH,
        collapsed_height=STANDARD_COLLAPSED_HEIGHT,
        header_height=0.0,
        header_top_margin=0.0,
        body_top=0.0,
        body_height=pill_height,
        port_top=0.0,
        port_height=pill_height,
        port_center_offset=pill_height * 0.5,
        port_side_margin=STANDARD_PORT_SIDE_MARGIN,
        port_dot_radius=STANDARD_PORT_DOT_RADIUS,
        resize_handle_size=STANDARD_RESIZE_HANDLE_SIZE,
        title_top=0.0,
        title_height=0.0,
        title_left_margin=0.0,
        title_right_margin=0.0,
        title_centered=False,
        body_left_margin=_COMPACT_PILL_BODY_SIDE_MARGIN,
        body_right_margin=_COMPACT_PILL_BODY_SIDE_MARGIN,
        body_bottom_margin=0.0,
        # Host chrome draws the pill itself (resolvedCornerRadius is height/2
        # for this variant): state-aware border, shadow, and port notches all
        # come from the chrome/ports layers, not the surface.
        use_host_chrome=True,
        use_host_shadow=True,
    )


def _panel_surface_metrics() -> GraphNodeSurfaceMetrics:
    return GraphNodeSurfaceMetrics(
        default_width=PANEL_DEFAULT_WIDTH,
        default_height=PANEL_DEFAULT_HEIGHT,
        min_width=PANEL_MIN_WIDTH,
        min_height=PANEL_MIN_HEIGHT,
        collapsed_width=STANDARD_COLLAPSED_WIDTH,
        collapsed_height=STANDARD_COLLAPSED_HEIGHT,
        header_height=0.0,
        header_top_margin=0.0,
        body_top=0.0,
        body_height=PANEL_DEFAULT_HEIGHT,
        port_top=0.0,
        port_height=0.0,
        port_center_offset=PANEL_PORT_CENTER_OFFSET,
        port_side_margin=STANDARD_PORT_SIDE_MARGIN,
        port_dot_radius=STANDARD_PORT_DOT_RADIUS,
        resize_handle_size=STANDARD_RESIZE_HANDLE_SIZE,
        title_top=0.0,
        title_height=0.0,
        title_left_margin=0.0,
        title_right_margin=0.0,
        title_centered=False,
        body_left_margin=12.0,
        body_right_margin=12.0,
        body_bottom_margin=0.0,
        use_host_chrome=True,
        use_host_shadow=True,
    )


def standard_inline_row_height(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> float:
    return float(max(24, standard_inline_property_pixel_size(value) + 16))


def standard_inline_stacked_row_height(
    value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    base_row_height = standard_inline_row_height(value)
    return float(base_row_height * 2.0 + STANDARD_INLINE_ROW_SPACING)


def standard_inline_slider_row_height(
    value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    base_row_height = standard_inline_row_height(value)
    return float(
        base_row_height * 2.0
        + standard_inline_property_pixel_size(value)
        + STANDARD_INLINE_ROW_SPACING
    )


def standard_inline_label_anchor_offset(
    value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    return standard_inline_row_height(value) * 0.5


def standard_inline_textarea_row_height(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> float:
    return float(max(96, int(round(standard_inline_row_height(value) * 4.0))))


def standard_inline_list_row_height(
    list_value: object = _STANDARD_INLINE_LIST_VALUE_UNSET,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    if list_value is _STANDARD_INLINE_LIST_VALUE_UNSET:
        return _STANDARD_INLINE_LIST_FALLBACK_ROW_HEIGHT
    try:
        item_count = max(0, len(list_value))
    except TypeError:
        item_count = 0
    visible_item_count = min(item_count, _STANDARD_INLINE_LIST_VISIBLE_ITEM_CAP)
    visible_items_height = (
        visible_item_count * _STANDARD_INLINE_LIST_ITEM_HEIGHT
        + max(0, visible_item_count - 1) * _STANDARD_INLINE_LIST_ITEM_SPACING
    )
    return float(
        standard_inline_row_height(graph_label_pixel_size)
        + visible_items_height
        + _STANDARD_INLINE_LIST_ADD_GAP
        + _STANDARD_INLINE_LIST_ADD_HEIGHT
    )


def standard_inline_property_row_height(
    editor: object,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    list_value: object = _STANDARD_INLINE_LIST_VALUE_UNSET,
) -> float:
    editor_name = str(editor or "").strip().lower()
    if not editor_name:
        return 0.0
    if editor_name == "textarea":
        return standard_inline_textarea_row_height(graph_label_pixel_size)
    if editor_name in {"slider", "interval_slider"}:
        return standard_inline_slider_row_height(graph_label_pixel_size)
    if editor_name == "list":
        return standard_inline_list_row_height(
            list_value,
            graph_label_pixel_size=graph_label_pixel_size,
        )
    if editor_name == "interval_fields":
        return standard_inline_stacked_row_height(graph_label_pixel_size)
    if editor_name in {"text", "number", "enum", "secret"}:
        return standard_inline_stacked_row_height(graph_label_pixel_size)
    return standard_inline_row_height(graph_label_pixel_size)


def standard_port_row_count(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> int:
    in_ports, out_ports = _visible_ports_for_layout(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    grouped_port_keys = {
        str(item.port_key)
        for group in getattr(spec, "settings_groups", ()) or ()
        for item in group.items
        if str(item.port_key)
    }
    property_by_key = {str(prop.key): prop for prop in spec.properties}
    port_row_height = standard_port_row_height(
        graph_label_pixel_size=graph_label_pixel_size,
    )

    def _direction_row_count(ports: list[EffectivePort]) -> int:
        row_count = 0
        for port in ports:
            port_key = str(port.key)
            if port_key in grouped_port_keys:
                continue
            row_span = 1
            if bool(port.uses_property_default):
                property_spec = property_by_key.get(port_key)
                if property_spec is not None:
                    editor_height = standard_inline_property_row_height(
                        property_spec.inline_editor,
                        graph_label_pixel_size=graph_label_pixel_size,
                    )
                    row_span = max(
                        1,
                        int(math.ceil(editor_height / port_row_height)),
                    )
            row_count += row_span
        return row_count

    return max(
        _direction_row_count(in_ports),
        _direction_row_count(out_ports),
    )


def standard_inline_body_height(
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    grouped_property_keys = {
        str(item.property_key)
        for group in getattr(spec, "settings_groups", ()) or ()
        for item in group.items
        if str(item.property_key)
    }
    default_property_keys = {
        str(port.key)
        for port in spec.ports
        if str(port.direction) == "in" and bool(port.uses_property_default)
    }
    inline_specs = tuple(
        property_spec
        for property_spec in inline_property_specs(spec)
        if str(property_spec.key) not in grouped_property_keys
        and str(property_spec.key) not in default_property_keys
    )
    if len(inline_specs) <= 0:
        return 0.0
    total_row_height = 0.0
    for property_spec in inline_specs:
        total_row_height += standard_inline_property_row_height(
            property_spec.inline_editor,
            graph_label_pixel_size=graph_label_pixel_size,
        )
    return (
        STANDARD_INLINE_SECTION_PADDING
        + total_row_height
        + max(0, len(inline_specs) - 1) * STANDARD_INLINE_ROW_SPACING
    )


def _estimated_standard_text_unit_width(character: str) -> float:
    if not character:
        return 0.0
    if character.isspace() or character in _STANDARD_NARROW_TEXT_CHARS:
        return 0.24
    if character in _STANDARD_WIDE_TEXT_CHARS:
        return 0.62
    if character in _STANDARD_PUNCTUATION_TEXT_CHARS:
        return 0.34
    if character.isupper() or character.isdigit():
        return 0.48
    return 0.44


def _normalize_graph_label_pixel_size(value: object) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return DEFAULT_GRAPH_LABEL_PIXEL_SIZE
    return max(GRAPH_LABEL_PIXEL_SIZE_MIN, min(numeric, GRAPH_LABEL_PIXEL_SIZE_MAX))


def standard_graph_label_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return _normalize_graph_label_pixel_size(value)


def standard_node_title_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value) + 2


def standard_node_title_icon_pixel_size(
    value: object | None = None,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> int:
    fallback = standard_graph_label_pixel_size(graph_label_pixel_size)
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(GRAPH_LABEL_PIXEL_SIZE_MIN, min(numeric, GRAPH_NODE_ICON_PIXEL_SIZE_MAX))


def standard_header_height(
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    title_pixel_size = standard_node_title_pixel_size(graph_label_pixel_size)
    icon_pixel_size = standard_node_title_icon_pixel_size(
        graph_node_icon_pixel_size,
        graph_label_pixel_size=graph_label_pixel_size,
    )
    content_height = max(title_pixel_size, icon_pixel_size)
    return float(
        max(
            STANDARD_HEADER_HEIGHT,
            content_height + _STANDARD_HEADER_CONTENT_VERTICAL_PADDING,
        )
    )


def standard_body_top(
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    return float(
        STANDARD_HEADER_TOP_MARGIN
        + standard_header_height(
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        + _STANDARD_HEADER_BODY_GAP
    )


def standard_port_label_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value)


def standard_elapsed_footer_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value)


def standard_inline_property_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value)


def standard_badge_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return max(9, standard_graph_label_pixel_size(value) - 1)


def standard_edge_label_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value) + 1


def standard_edge_pill_pixel_size(value: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE) -> int:
    return standard_graph_label_pixel_size(value) + 2


def standard_port_row_height(
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    return float(
        max(
            STANDARD_PORT_HEIGHT,
            standard_port_label_pixel_size(graph_label_pixel_size) + 8,
        )
    )


def standard_viewer_port_row_height(
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
) -> float:
    return standard_port_row_height(graph_label_pixel_size=graph_label_pixel_size)


@lru_cache(maxsize=1024)
def _qt_standard_text_width(
    content: str,
    pixel_size: int,
    font_description: str,
    font_weight: str = "",
) -> float:
    from PyQt6.QtGui import QFont, QFontMetricsF

    font = QFont()
    if font_description:
        font.fromString(font_description)
    font.setPixelSize(max(1, int(pixel_size)))
    if font_weight == "bold":
        font.setWeight(QFont.Weight.Bold)
    elif font_weight == "demibold":
        font.setWeight(QFont.Weight.DemiBold)
    metrics = QFontMetricsF(font)
    return round(max(0.0, metrics.horizontalAdvance(content) + _STANDARD_TEXT_WIDTH_PADDING), 3)


def _estimate_standard_text_width(text: Any, *, pixel_size: float, font_weight: str = "") -> float:
    content = str(text or "")
    if not content:
        return 0.0
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        QApplication = None
    if QApplication is not None:
        app = QApplication.instance()
        if app is not None:
            return _qt_standard_text_width(
                content,
                int(round(float(pixel_size))),
                app.font().toString(),
                font_weight,
            )
    width = sum(_estimated_standard_text_unit_width(character) for character in content) * float(pixel_size)
    return round(max(0.0, width + _STANDARD_TEXT_WIDTH_PADDING), 3)


def _standard_title_full_width(
    node: NodeInstance,
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    title_width = _estimate_standard_text_width(
        node.title,
        pixel_size=standard_node_title_pixel_size(graph_label_pixel_size),
        font_weight="bold",
    )
    icon_reserve = _standard_title_icon_reserve_width(
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    return round(
        title_width
        + STANDARD_TITLE_LEFT_MARGIN
        + STANDARD_TITLE_RIGHT_MARGIN
        + icon_reserve,
        3,
    )


def _standard_title_icon_reserve_width(
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    if not str(getattr(spec, "icon", "") or "").strip():
        return 0.0
    icon_size = standard_node_title_icon_pixel_size(
        graph_node_icon_pixel_size,
        graph_label_pixel_size=graph_label_pixel_size,
    )
    render_size = min(
        float(icon_size),
        standard_header_height(
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        ),
    )
    if render_size <= 0.0:
        return 0.0
    return round(render_size + _STANDARD_TITLE_ICON_SPACING, 3)


def _standard_visible_label_widths(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> tuple[float, float]:
    port_label_pixel_size = standard_port_label_pixel_size(graph_label_pixel_size)
    in_ports, out_ports = _visible_ports_for_layout(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    removable_keys = set()
    for group in spec.dynamic_port_groups:
        group_ports = group.ports_resolver(node.properties)
        if len(group_ports) > group.minimum:
            removable_keys.update(port.key for port in group_ports)
    # Columns include the remove target, measured from the gutter.
    remove_reserve = (
        _DYNAMIC_PORT_REMOVE_CENTER_INTERVAL
        + _DYNAMIC_PORT_REMOVE_TARGET_WIDTH * 0.5 - STANDARD_PORT_GUTTER
    )
    grouped_keys = {
        item.port_key for group in spec.settings_groups for item in group.items
    } if str(spec.surface_family or "standard").strip() == "standard" else set()
    left_label_width = max(
        (
            _estimate_standard_text_width(port.label or port.key, pixel_size=port_label_pixel_size)
            + (remove_reserve if port.key in removable_keys else 0.0)
            for port in in_ports
            if port.key not in grouped_keys
        ),
        default=0.0,
    )
    right_label_width = max(
        (
            _estimate_standard_text_width(port.label or port.key, pixel_size=port_label_pixel_size)
            + (remove_reserve if port.key in removable_keys else 0.0)
            for port in out_ports
            if port.key not in grouped_keys
        ),
        default=0.0,
    )
    return round(left_label_width, 3), round(right_label_width, 3)


def _standard_port_label_min_width(left_label_width: float, right_label_width: float) -> float:
    return round(
        float(left_label_width) + float(right_label_width) + (STANDARD_PORT_GUTTER * 2.0) + STANDARD_CENTER_GAP,
        3,
    )


def _standard_inline_enum_label_width(label: Any, *, pixel_size: float) -> float:
    desired_width = _estimate_standard_text_width(label, pixel_size=pixel_size) + _STANDARD_INLINE_LABEL_TEXT_PADDING
    return round(
        min(
            _STANDARD_INLINE_LABEL_MAX_WIDTH,
            max(_STANDARD_INLINE_LABEL_MIN_WIDTH, desired_width),
        ),
        3,
    )


def _standard_inline_enum_control_width(enum_values: tuple[str, ...], *, pixel_size: float) -> float:
    longest_value_width = max(
        (
            _estimate_standard_text_width(value, pixel_size=pixel_size)
            for value in enum_values
        ),
        default=0.0,
    )
    return round(
        max(
            _STANDARD_INLINE_ENUM_COMBO_MIN_WIDTH,
            longest_value_width + _STANDARD_INLINE_ENUM_COMBO_CHROME_WIDTH,
        ),
        3,
    )


def _standard_inline_min_width(
    node: NodeInstance,
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    keep_expanded_node_width: bool = False,
) -> float:
    inline_pixel_size = standard_inline_property_pixel_size(graph_label_pixel_size)
    row_chrome_width = (
        STANDARD_BODY_LEFT_MARGIN
        + STANDARD_BODY_RIGHT_MARGIN
        + (_STANDARD_INLINE_ROW_HORIZONTAL_MARGIN * 2.0)
    )
    default_property_keys = {
        port.key for port in spec.ports if port.uses_property_default
    }
    grouped_keys = {
        item.property_key or (item.port_key if item.port_key in default_property_keys else "")
        for group in spec.settings_groups for item in group.items
    }
    expanded_keys = {
        item.property_key or (item.port_key if item.port_key in default_property_keys else "")
        for group in spec.settings_groups
        if keep_expanded_node_width or group.group_id in node.expanded_settings_group_ids
        for item in group.items
    }
    # Group headers span the card, independently of the two port-label columns.
    required_widths = [
        _estimate_standard_text_width(group.label, pixel_size=inline_pixel_size)
        + 52.0  # 12px side insets, 12px chevron, and two 8px gaps.
        for group in spec.settings_groups
    ]
    grouped_port_keys = {
        item.port_key
        for group in spec.settings_groups
        if keep_expanded_node_width or group.group_id in node.expanded_settings_group_ids
        for item in group.items
        if not item.property_key and item.port_key not in default_property_keys
    }
    required_widths.extend(
        _estimate_standard_text_width(
            node.port_labels.get(port.key) or port.label or port.key,
            pixel_size=inline_pixel_size,
        ) + 2.0 * STANDARD_PORT_GUTTER
        for port in spec.ports if port.key in grouped_port_keys
    )
    for property_spec in inline_property_specs(spec):
        grouped = property_spec.key in grouped_keys
        if grouped and property_spec.key not in expanded_keys:
            continue
        editor = str(property_spec.inline_editor or "").strip().lower()
        if not grouped and (editor != "enum" or not property_spec.enum_values):
            continue
        label_width = _standard_inline_enum_label_width(
            property_spec.label or property_spec.key,
            pixel_size=inline_pixel_size,
        )
        if editor == "color":
            # Inline color rows place label, swatch, and a hex field side by side.
            control_width = 26.0 + 6.0 + 16.0 + _estimate_standard_text_width(
                "#ffffffff", pixel_size=inline_pixel_size,
            )
            content_width = label_width + 6.0 + control_width
        elif editor == "toggle":
            content_width = label_width + 6.0 + 32.0
        else:
            control_width = _standard_inline_enum_control_width(
                tuple(str(value) for value in property_spec.enum_values),
                pixel_size=inline_pixel_size,
            )
            content_width = max(label_width, control_width)
        required_widths.append(row_chrome_width + content_width)
    return round(max(required_widths, default=0.0), 3)


def _standard_surface_layout(spec: NodeTypeSpec) -> SurfaceLayoutMetrics:
    return surface_spec_for_node_type(type_id=spec.type_id, spec=spec).layout


def _standard_body_layout_min_width(layout: SurfaceLayoutMetrics) -> float:
    if float(layout.min_body_width) <= 0.0:
        return 0.0
    return round(
        STANDARD_BODY_LEFT_MARGIN
        + float(layout.min_body_width)
        + STANDARD_BODY_RIGHT_MARGIN,
        3,
    )


def _standard_uses_body_region_layout(layout: SurfaceLayoutMetrics) -> bool:
    return str(layout.content_region or "host").strip().lower() == "body"


def _standard_reserves_body_layout_metrics(layout: SurfaceLayoutMetrics) -> bool:
    return (
        _standard_uses_body_region_layout(layout)
        or float(layout.min_body_width) > 0.0
        or float(layout.min_body_height) > 0.0
        or float(layout.preferred_body_height) > 0.0
    )


def _standard_surface_min_width_contract(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> _StandardWidthContract:
    left_label_width, right_label_width = _standard_visible_label_widths(
        node,
        spec,
        workspace_nodes,
        graph_label_pixel_size=graph_label_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    return _StandardWidthContract(
        title_full_width=_standard_title_full_width(
            node,
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        ),
        left_label_width=left_label_width,
        right_label_width=right_label_width,
        port_gutter=STANDARD_PORT_GUTTER,
        center_gap=STANDARD_CENTER_GAP,
        port_label_min_width=_standard_port_label_min_width(left_label_width, right_label_width),
    )


def _collapsed_title_icon_reserve_width(
    spec: NodeTypeSpec,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    if str(spec.surface_family or "").strip() == "group_backdrop":
        icon_size = standard_node_title_icon_pixel_size(
            graph_node_icon_pixel_size,
            graph_label_pixel_size=graph_label_pixel_size,
        )
        return (
            min(icon_size, _COLLAPSED_TITLE_ICON_MAX_RENDER_SIZE)
            + _COLLAPSED_GROUP_TITLE_ICON_SPACING
        )
    if str(getattr(spec, "runtime_behavior", "") or "") == "passive" and not bool(getattr(spec, "show_title_icon", False)):
        return 0.0
    return _standard_title_icon_reserve_width(
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )


def collapsed_node_title_width(
    node: NodeInstance,
    spec: NodeTypeSpec,
    base_width: float,
    *,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
) -> float:
    title_width = _estimate_standard_text_width(
        str(node.title or ""),
        pixel_size=standard_node_title_pixel_size(graph_label_pixel_size),
        font_weight="bold",
    )
    required_width = (
        title_width
        + _COLLAPSED_TITLE_LEFT_MARGIN
        + _COLLAPSED_TITLE_RIGHT_MARGIN
        + _collapsed_title_icon_reserve_width(
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        + _COLLAPSED_TITLE_WIDTH_SAFETY_PADDING
    )
    return round(max(float(base_width), required_width), 3)


def _dynamic_port_bottom_padding(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None,
    *,
    port_count: int,
    port_row_height: float,
    port_center_offset: float,
    graph_label_pixel_size: object,
    visible_ports_override: tuple[EffectivePort, ...] | None,
) -> float:
    groups = tuple(getattr(spec, "dynamic_port_groups", ()) or ())
    if not groups:
        return float(STANDARD_BOTTOM_PADDING)
    in_ports, out_ports = _visible_ports_for_layout(
        node,
        spec,
        workspace_nodes,
        visible_ports_override=visible_ports_override,
    )
    static_keys = {str(port.key) for port in spec.ports}
    static_keys.difference_update(
        port.key
        for group in groups if group.property_editor is not None
        for port in group.ports_resolver(node.properties)
    )
    grouped_port_keys = {
        str(item.port_key)
        for settings_group in getattr(spec, "settings_groups", ()) or ()
        for item in settings_group.items
        if str(item.port_key)
    }
    property_by_key = {str(prop.key): prop for prop in spec.properties}

    def _add_center(ports: list[EffectivePort]) -> float:
        last_dynamic_row: int | None = None
        visible_row_count = 0
        layout_row = 0
        for port in ports:
            port_key = str(port.key)
            if port_key in grouped_port_keys:
                continue
            if port_key not in static_keys:
                last_dynamic_row = layout_row
            visible_row_count += 1
            row_span = 1
            if bool(port.uses_property_default):
                property_spec = property_by_key.get(port_key)
                if property_spec is not None:
                    editor_height = standard_inline_property_row_height(
                        property_spec.inline_editor,
                        graph_label_pixel_size=graph_label_pixel_size,
                    )
                    row_span = max(
                        1,
                        int(math.ceil(editor_height / port_row_height)),
                    )
            layout_row += row_span
        if last_dynamic_row is None:
            return port_center_offset + visible_row_count * port_row_height
        return (
            port_center_offset
            + last_dynamic_row * port_row_height
            + _DYNAMIC_PORT_HANDLE_CENTER_INTERVAL
        )

    ports_by_direction = {"in": in_ports, "out": out_ports}
    add_centers = [
        _add_center(ports_by_direction[group.direction])
        for group in groups
        if group.direction in ports_by_direction
    ]
    if not add_centers:
        return float(STANDARD_BOTTOM_PADDING)
    return max(
        float(STANDARD_BOTTOM_PADDING),
        max(add_centers)
        # Hover targets may overflow the chrome; only the resting dot sizes it.
        + _DYNAMIC_PORT_HANDLE_REST_RADIUS
        + _DYNAMIC_PORT_HANDLE_BOTTOM_INSET
        - float(port_count) * port_row_height,
    )


def _standard_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
    keep_expanded_node_width: bool = False,
) -> GraphNodeSurfaceMetrics:
    variant = str(getattr(spec, "surface_variant", "") or "").strip()
    if variant == PANEL_SURFACE_VARIANT:
        return _panel_surface_metrics()
    if variant in {
        BOOLEAN_TOGGLE_SURFACE_VARIANT,
        NUMBER_SLIDER_SURFACE_VARIANT,
        SELECT_SURFACE_VARIANT,
        TRIGGER_SURFACE_VARIANT,
    }:
        return _compact_pill_surface_metrics(
            node,
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
        )
    port_count = standard_port_row_count(
        node,
        spec,
        workspace_nodes,
        graph_label_pixel_size=graph_label_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    layout = _standard_surface_layout(spec)
    header_height = standard_header_height(
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    body_top = standard_body_top(
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
    )
    body_height = standard_inline_body_height(
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
    )
    body_region_layout = _standard_uses_body_region_layout(layout)
    body_layout_metrics = _standard_reserves_body_layout_metrics(layout)
    if body_layout_metrics:
        body_height = max(
            body_height,
            float(layout.min_body_height),
            float(layout.preferred_body_height),
        )
    port_row_height = standard_port_row_height(graph_label_pixel_size=graph_label_pixel_size)
    port_center_offset = max(STANDARD_PORT_CENTER_OFFSET, port_row_height * 0.5)
    bottom_padding = _dynamic_port_bottom_padding(
        node,
        spec,
        workspace_nodes,
        port_count=port_count,
        port_row_height=port_row_height,
        port_center_offset=port_center_offset,
        graph_label_pixel_size=graph_label_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    if str(spec.type_id or "") == "io.folder_explorer":
        target_height = float(node.custom_height) if node.custom_height is not None else _FOLDER_EXPLORER_DEFAULT_HEIGHT
        body_height = max(
            body_height,
            max(0.0, target_height - body_top - _FOLDER_EXPLORER_PORT_BOTTOM_RESERVE),
        )
    default_body_height = body_height
    if body_region_layout and node.custom_height is not None:
        body_height = max(
            body_height,
            float(node.custom_height) - body_top - port_count * port_row_height - bottom_padding,
        )
    default_height = body_top + default_body_height + port_count * port_row_height + bottom_padding
    inline_min_width = _standard_inline_min_width(
        node,
        spec,
        graph_label_pixel_size=graph_label_pixel_size,
        keep_expanded_node_width=keep_expanded_node_width and uses_content_sizing(spec),
    )
    body_layout_min_width = _standard_body_layout_min_width(layout)
    width_contract = _standard_surface_min_width_contract(
        node,
        spec,
        workspace_nodes,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    min_width = width_contract.min_width_with_labels if show_port_labels else width_contract.min_width_without_labels
    min_width = max(min_width, inline_min_width, body_layout_min_width)
    default_width = max(STANDARD_DEFAULT_WIDTH, min_width)
    if str(spec.type_id or "") == "io.folder_explorer":
        default_width = max(default_width, _FOLDER_EXPLORER_DEFAULT_WIDTH)
        default_height = max(default_height, _FOLDER_EXPLORER_DEFAULT_HEIGHT)
    min_height = max(float(STANDARD_MIN_HEIGHT), float(default_height))
    return GraphNodeSurfaceMetrics(
        default_width=default_width,
        default_height=default_height,
        min_width=min_width,
        min_height=min_height,
        collapsed_width=collapsed_node_title_width(
            node,
            spec,
            STANDARD_COLLAPSED_WIDTH,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        ),
        collapsed_height=STANDARD_COLLAPSED_HEIGHT,
        header_height=header_height,
        header_top_margin=STANDARD_HEADER_TOP_MARGIN,
        body_top=body_top,
        body_height=body_height,
        port_top=body_top + body_height,
        port_height=port_row_height,
        port_center_offset=port_center_offset,
        port_side_margin=STANDARD_PORT_SIDE_MARGIN,
        port_dot_radius=STANDARD_PORT_DOT_RADIUS,
        resize_handle_size=STANDARD_RESIZE_HANDLE_SIZE,
        title_top=STANDARD_HEADER_TOP_MARGIN,
        title_height=header_height,
        title_left_margin=STANDARD_TITLE_LEFT_MARGIN,
        title_right_margin=STANDARD_TITLE_RIGHT_MARGIN,
        title_centered=False,
        body_left_margin=STANDARD_BODY_LEFT_MARGIN,
        body_right_margin=STANDARD_BODY_RIGHT_MARGIN,
        body_bottom_margin=bottom_padding,
        use_host_chrome=STANDARD_USE_HOST_CHROME,
        standard_title_full_width=width_contract.title_full_width,
        standard_left_label_width=width_contract.left_label_width,
        standard_right_label_width=width_contract.right_label_width,
        standard_port_gutter=width_contract.port_gutter,
        standard_center_gap=width_contract.center_gap,
        standard_port_label_min_width=width_contract.port_label_min_width,
    )


def uses_content_sizing(spec: NodeTypeSpec) -> bool:
    """Ordinary processing cards fit contents; dedicated surfaces retain sizing."""
    surface = surface_spec_for_node_type(type_id=spec.type_id, spec=spec)
    return (
        spec.runtime_behavior in {"active", "compile_only"}
        and surface.family == "standard"
        and surface.component_key == "standard"
        and not _standard_reserves_body_layout_metrics(surface.layout)
    )


def resolved_node_surface_size(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    surface_metrics: GraphNodeSurfaceMetrics | None = None,
    clamp_height: bool = False,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
) -> tuple[float, float]:
    metrics = surface_metrics or node_surface_metrics(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
    )
    if node.collapsed:
        return float(metrics.collapsed_width), float(metrics.collapsed_height)

    if uses_content_sizing(spec):
        return (
            max(float(metrics.min_width), float(metrics.default_width)),
            max(float(metrics.min_height), float(metrics.default_height)),
        )

    width, height = _resolved_dimensions(
        node,
        default_width=metrics.default_width,
        default_height=metrics.default_height,
    )
    resolved_width = max(float(metrics.min_width), float(width))
    resolved_height = float(height)
    if node.custom_height is None:
        resolved_height = max(float(metrics.min_height), resolved_height)
    family = str(spec.surface_family or "standard").strip() or "standard"
    if family != "viewer" and node.custom_height is not None:
        baseline_node = node.clone()
        baseline_node.custom_height = None
        baseline_metrics = node_surface_metrics(
            baseline_node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=None,
            visible_ports_override=visible_ports_override,
        )
        if abs(float(node.custom_height) - float(baseline_metrics.default_height)) <= 1.0:
            resolved_height = float(metrics.default_height)
    if family == "viewer" and node.custom_height is not None:
        viewer_height_tolerance = 1.0

        def _matches_viewer_height(value: float, expected: float) -> bool:
            return abs(float(value) - float(expected)) <= viewer_height_tolerance

        baseline_node = node.clone()
        baseline_node.custom_height = None
        baseline_metrics = node_surface_metrics(
            baseline_node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=None,
            visible_ports_override=visible_ports_override,
        )
        from .surface_contract import _visible_port_count

        port_count = _visible_port_count(
            node,
            spec,
            workspace_nodes,
            visible_ports_override=visible_ports_override,
        )
        body_top = standard_body_top(
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
        port_row_height = standard_viewer_port_row_height(
            graph_label_pixel_size=graph_label_pixel_size,
        )
        inline_body_height = standard_inline_body_height(
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
        )
        legacy_default_heights = {
            float(
                body_top
                + max(float(legacy_body_height), float(inline_body_height))
                + port_count * port_row_height
                + VIEWER_BODY_BOTTOM_PADDING
            )
            for legacy_body_height in VIEWER_LEGACY_DEFAULT_BODY_HEIGHTS
        }
        if _matches_viewer_height(float(node.custom_height), float(baseline_metrics.default_height)) or any(
            _matches_viewer_height(float(node.custom_height), legacy_height)
            for legacy_height in legacy_default_heights
        ):
            resolved_height = float(metrics.default_height)
    if clamp_height:
        resolved_height = max(float(metrics.min_height), resolved_height)
    resolved_width, resolved_height = resolve_node_type_size_override(
        node,
        spec,
        base_width=resolved_width,
        base_height=resolved_height,
    )
    resolved_width = max(float(metrics.min_width), resolved_width)
    resolved_height = max(float(metrics.min_height), resolved_height)
    return resolved_width, resolved_height


def node_surface_metrics(
    node: NodeInstance,
    spec: NodeTypeSpec,
    workspace_nodes: Mapping[str, NodeInstance] | None = None,
    *,
    show_port_labels: bool = True,
    graph_label_pixel_size: object = DEFAULT_GRAPH_LABEL_PIXEL_SIZE,
    graph_node_icon_pixel_size: object | None = None,
    visible_ports_override: tuple[EffectivePort, ...] | None = None,
    keep_expanded_node_width: bool = False,
) -> GraphNodeSurfaceMetrics:
    family = str(spec.surface_family or "standard").strip() or "standard"
    if family == "flowchart":
        from .flowchart_metrics import _flowchart_surface_metrics

        return _flowchart_surface_metrics(
            node,
            spec,
            workspace_nodes,
            visible_ports_override=visible_ports_override,
        )
    if family == "planning":
        from .panel_metrics import _planning_surface_metrics

        return _planning_surface_metrics(node, spec)
    if family == "annotation":
        from .panel_metrics import _annotation_surface_metrics

        return _annotation_surface_metrics(node, spec)
    if family == "group_backdrop":
        from .panel_metrics import _group_backdrop_surface_metrics

        return _group_backdrop_surface_metrics(
            node,
            spec,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        )
    if family == "media":
        from .panel_metrics import _media_surface_metrics

        return _media_surface_metrics(
            node,
            spec,
            workspace_nodes,
            graph_label_pixel_size=graph_label_pixel_size,
            visible_ports_override=visible_ports_override,
        )
    if family == "viewer":
        from .viewer_metrics import _viewer_surface_metrics

        return _viewer_surface_metrics(
            node,
            spec,
            workspace_nodes,
            show_port_labels=show_port_labels,
            graph_label_pixel_size=graph_label_pixel_size,
            graph_node_icon_pixel_size=graph_node_icon_pixel_size,
            visible_ports_override=visible_ports_override,
        )
    return _standard_surface_metrics(
        node,
        spec,
        workspace_nodes,
        show_port_labels=show_port_labels,
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size=graph_node_icon_pixel_size,
        visible_ports_override=visible_ports_override,
        keep_expanded_node_width=keep_expanded_node_width,
    )
