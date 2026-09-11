from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ea_node_editor.app_preferences import (
    effective_graph_node_icon_pixel_size,
    normalize_edge_crossing_style,
    normalize_floating_toolbar_size,
    normalize_floating_toolbar_style,
    normalize_folder_explorer_column_widths,
    normalize_graph_label_pixel_size,
    normalize_graph_node_icon_pixel_size_override,
    normalize_status_bar_layout,
    normalize_canvas_background_variant,
    normalize_canvas_import_mode,
    normalize_grid_overlay_style,
    normalize_media_panel_settings,
    normalize_node_comment_editor_default,
    normalize_node_elapsed_time_unit,
    normalize_node_elapsed_time_visibility,
    normalize_passive_node_library_display_mode,
    normalize_plot_settings,
    normalize_property_pane_variant,
    normalize_selection_toolbar_minimal_menu_trigger,
    normalize_selection_toolbar_mode,
    normalize_shell_panel_collapsed,
)
from ea_node_editor.graph.type_forwarding import GraphTypeResolver, ResolvedSourceContract
from ea_node_editor.graph.hierarchy import is_node_in_scope
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.text_style import normalize_recent_text_colors
from ea_node_editor.ui.shell.tooltip_policy import normalize_tooltip_category_preferences
from ea_node_editor.ui.shell.quick_insert_projection import (
    build_canvas_quick_insert_items,
    build_connection_quick_insert_items,
)

UNSET = object()


@dataclass(slots=True)
class ShellWorkspaceUiState:
    canvas_background_variant: str
    canvas_import_mode: str
    show_grid: bool
    grid_style: str
    edge_crossing_style: str
    floating_toolbar_style: str
    floating_toolbar_size: str
    node_floating_toolbar_opens_on_hover: bool
    selection_toolbar_mode: str
    selection_toolbar_minimal_menu_trigger: str
    graph_label_pixel_size: int
    graph_node_icon_pixel_size_override: int | None
    node_title_icon_pixel_size: int
    recent_text_colors: list[str]
    show_canvas_options_button: bool
    show_minimap: bool
    show_port_labels: bool
    notched_ports: bool
    keep_expanded_node_width: bool
    node_elapsed_time_unit: str
    node_elapsed_time_visibility: str
    node_comment_editor_default: str
    node_shadow: bool
    shadow_strength: int
    shadow_softness: int
    shadow_offset: int
    status_bar_layout: str
    show_fps_telemetry: bool
    tab_strip_density: str
    property_pane_variant: str
    passive_node_library_display_mode: str
    shell_panel_collapsed: dict[str, bool]
    graphics_tooltip_categories: dict[str, bool]
    active_theme_id: str
    media_panel_default_show_title: bool
    media_panel_default_show_frame: bool
    media_panel_autoplay_animations: bool
    media_panel_source_input_exposed: bool
    folder_explorer_column_widths: dict[str, int]
    lightweight_canvas: bool
    plot_default_backend_per_type: dict[str, str]


def build_default_shell_workspace_ui_state(
    graphics_settings: Any = DEFAULT_GRAPHICS_SETTINGS,
) -> ShellWorkspaceUiState:
    canvas = graphics_settings.get("canvas", {}) if isinstance(graphics_settings, dict) else {}
    interaction = graphics_settings.get("interaction", {}) if isinstance(graphics_settings, dict) else {}
    shell = graphics_settings.get("shell", {}) if isinstance(graphics_settings, dict) else {}
    theme = graphics_settings.get("theme", {}) if isinstance(graphics_settings, dict) else {}
    typography = graphics_settings.get("typography", {}) if isinstance(graphics_settings, dict) else {}
    media_panel = (
        graphics_settings.get("media_panel", {})
        if isinstance(graphics_settings, dict)
        else {}
    )
    folder_explorer = graphics_settings.get("folder_explorer", {}) if isinstance(graphics_settings, dict) else {}
    plot_settings = normalize_plot_settings(
        graphics_settings.get("plot") if isinstance(graphics_settings, dict) else None
    )
    media_panel_settings = normalize_media_panel_settings(media_panel)
    tooltip_categories = normalize_tooltip_category_preferences(shell.get("tooltip_categories"))
    graph_label_pixel_size = normalize_graph_label_pixel_size(
        typography.get("graph_label_pixel_size", DEFAULT_GRAPHICS_SETTINGS["typography"]["graph_label_pixel_size"])
    )
    graph_node_icon_pixel_size_override = normalize_graph_node_icon_pixel_size_override(
        typography.get("graph_node_icon_pixel_size_override")
    )
    return ShellWorkspaceUiState(
        canvas_import_mode=normalize_canvas_import_mode(interaction.get("canvas_import_mode")),
        canvas_background_variant=normalize_canvas_background_variant(
            canvas.get(
                "background_variant",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["background_variant"],
            )
        ),
        show_grid=bool(canvas.get("show_grid", DEFAULT_GRAPHICS_SETTINGS["canvas"]["show_grid"])),
        grid_style=normalize_grid_overlay_style(
            canvas.get("grid_style", DEFAULT_GRAPHICS_SETTINGS["canvas"]["grid_style"])
        ),
        edge_crossing_style=normalize_edge_crossing_style(
            canvas.get("edge_crossing_style", DEFAULT_GRAPHICS_SETTINGS["canvas"]["edge_crossing_style"])
        ),
        floating_toolbar_style=normalize_floating_toolbar_style(
            canvas.get(
                "floating_toolbar_style",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["floating_toolbar_style"],
            )
        ),
        floating_toolbar_size=normalize_floating_toolbar_size(
            canvas.get(
                "floating_toolbar_size",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["floating_toolbar_size"],
            )
        ),
        node_floating_toolbar_opens_on_hover=bool(
            canvas.get(
                "node_floating_toolbar_opens_on_hover",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_floating_toolbar_opens_on_hover"],
            )
        ),
        selection_toolbar_mode=normalize_selection_toolbar_mode(
            canvas.get(
                "selection_toolbar_mode",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["selection_toolbar_mode"],
            )
        ),
        selection_toolbar_minimal_menu_trigger=normalize_selection_toolbar_minimal_menu_trigger(
            canvas.get(
                "selection_toolbar_minimal_menu_trigger",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["selection_toolbar_minimal_menu_trigger"],
            )
        ),
        graph_label_pixel_size=graph_label_pixel_size,
        graph_node_icon_pixel_size_override=graph_node_icon_pixel_size_override,
        node_title_icon_pixel_size=effective_graph_node_icon_pixel_size(
            graph_label_pixel_size,
            graph_node_icon_pixel_size_override,
        ),
        recent_text_colors=normalize_recent_text_colors(
            typography.get("recent_text_colors")
        ),
        show_canvas_options_button=bool(
            canvas.get(
                "show_canvas_options_button",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["show_canvas_options_button"],
            )
        ),
        show_minimap=bool(canvas.get("show_minimap", DEFAULT_GRAPHICS_SETTINGS["canvas"]["show_minimap"])),
        show_port_labels=bool(
            canvas.get("show_port_labels", DEFAULT_GRAPHICS_SETTINGS["canvas"]["show_port_labels"])
        ),
        notched_ports=bool(
            canvas.get("notched_ports", DEFAULT_GRAPHICS_SETTINGS["canvas"]["notched_ports"])
        ),
        keep_expanded_node_width=bool(
            canvas.get("keep_expanded_node_width", DEFAULT_GRAPHICS_SETTINGS["canvas"]["keep_expanded_node_width"])
        ),
        node_elapsed_time_unit=normalize_node_elapsed_time_unit(
            canvas.get(
                "node_elapsed_time_unit",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_unit"],
            )
        ),
        node_elapsed_time_visibility=normalize_node_elapsed_time_visibility(
            canvas.get(
                "node_elapsed_time_visibility",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_elapsed_time_visibility"],
            )
        ),
        node_comment_editor_default=normalize_node_comment_editor_default(
            canvas.get(
                "node_comment_editor_default",
                DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_comment_editor_default"],
            )
        ),
        node_shadow=bool(canvas.get("node_shadow", DEFAULT_GRAPHICS_SETTINGS["canvas"]["node_shadow"])),
        shadow_strength=int(canvas.get("shadow_strength", DEFAULT_GRAPHICS_SETTINGS["canvas"]["shadow_strength"])),
        shadow_softness=int(canvas.get("shadow_softness", DEFAULT_GRAPHICS_SETTINGS["canvas"]["shadow_softness"])),
        shadow_offset=int(canvas.get("shadow_offset", DEFAULT_GRAPHICS_SETTINGS["canvas"]["shadow_offset"])),
        status_bar_layout=normalize_status_bar_layout(
            shell.get("status_bar_layout", DEFAULT_GRAPHICS_SETTINGS["shell"]["status_bar_layout"])
        ),
        show_fps_telemetry=bool(
            shell.get("show_fps_telemetry", DEFAULT_GRAPHICS_SETTINGS["shell"]["show_fps_telemetry"])
        ),
        tab_strip_density=str(
            shell.get("tab_strip_density", DEFAULT_GRAPHICS_SETTINGS["shell"]["tab_strip_density"])
        ),
        property_pane_variant=normalize_property_pane_variant(
            shell.get(
                "property_pane_variant",
                DEFAULT_GRAPHICS_SETTINGS["shell"]["property_pane_variant"],
            )
        ),
        passive_node_library_display_mode=normalize_passive_node_library_display_mode(
            shell.get(
                "passive_node_library_display_mode",
                DEFAULT_GRAPHICS_SETTINGS["shell"]["passive_node_library_display_mode"],
            )
        ),
        shell_panel_collapsed=normalize_shell_panel_collapsed(
            shell.get("panel_collapsed")
        ),
        graphics_tooltip_categories=tooltip_categories,
        active_theme_id=str(theme.get("theme_id", DEFAULT_GRAPHICS_SETTINGS["theme"]["theme_id"])),
        media_panel_default_show_title=bool(media_panel_settings["show_title"]),
        media_panel_default_show_frame=bool(media_panel_settings["show_frame"]),
        media_panel_autoplay_animations=bool(media_panel_settings["autoplay_animations"]),
        media_panel_source_input_exposed=bool(
            media_panel_settings["source_input_exposed"]
        ),
        folder_explorer_column_widths=normalize_folder_explorer_column_widths(
            folder_explorer.get("column_widths") if isinstance(folder_explorer, dict) else None
        ),
        lightweight_canvas=bool(plot_settings["lightweight_canvas"]),
        plot_default_backend_per_type=dict(
            plot_settings["plot_default_backend_per_type"]
        ),
    )


def connection_quick_insert_overlay_coordinate(context: dict[str, Any] | None, key: str) -> float:
    return float((context or {}).get(key, 0.0))


def connection_quick_insert_source_summary(context: dict[str, Any] | None) -> str:
    context = context or {}
    node_title = str(context.get("node_title", "")).strip()
    port_label = str(context.get("port_label", "")).strip()
    data_type = " | ".join(context.get("source_type_ids", ())) or str(context.get("data_type", "")).strip()
    if not node_title and not port_label:
        return ""
    summary = f"{node_title}.{port_label}" if node_title and port_label else (node_title or port_label)
    if data_type:
        summary += f" [{data_type}]"
    return summary


def connection_quick_insert_is_canvas_mode(context: dict[str, Any] | None) -> bool:
    return str((context or {}).get("mode", "")).strip() == "canvas_insert"


def update_connection_quick_insert_state(
    quick_insert: Any,
    *,
    open_: bool | None = None,
    query: str | None = None,
    results: list[dict[str, Any]] | None = None,
    highlight_index: int | None = None,
    context: dict[str, Any] | None | object = UNSET,
) -> bool:
    changed = False
    if open_ is not None:
        normalized_open = bool(open_)
        if normalized_open != quick_insert.open:
            quick_insert.open = normalized_open
            changed = True
    if query is not None:
        normalized_query = str(query)
        if normalized_query != quick_insert.query:
            quick_insert.query = normalized_query
            changed = True
    if results is not None:
        normalized_results = list(results)
        if normalized_results != quick_insert.results:
            quick_insert.results = normalized_results
            changed = True
    if highlight_index is not None:
        normalized_index = int(highlight_index)
        if normalized_index != quick_insert.highlight_index:
            quick_insert.highlight_index = normalized_index
            changed = True
    if context is not UNSET:
        normalized_context = dict(context) if isinstance(context, dict) else None
        if normalized_context != quick_insert.context:
            quick_insert.context = normalized_context
            changed = True
    return changed


def build_connection_quick_insert_context(host: Any, node_id: str, port_key: str) -> dict[str, Any] | None:
    workspace = host.model.project.workspaces.get(host.workspace_manager.active_workspace_id())
    if workspace is None:
        return None
    normalized_node_id = str(node_id).strip()
    normalized_port_key = str(port_key).strip()
    if not normalized_node_id or not normalized_port_key:
        return None
    node = workspace.nodes.get(normalized_node_id)
    if node is None:
        return None
    scene = getattr(host, "scene", None)
    if scene is not None and not is_node_in_scope(workspace, normalized_node_id, tuple(scene.active_scope_path)):
        return None
    spec = host.registry.spec_or_none(node.type_id)
    if spec is None:
        return None
    resolver = GraphTypeResolver(
        registry=host.registry,
        workspace_nodes=workspace.nodes,
        workspace_edges=workspace.edges.values(),
    )
    port = resolver.port(normalized_node_id, normalized_port_key)
    if port is None or not bool(port.exposed):
        return None
    return {
        "node_id": normalized_node_id,
        "node_title": str(node.title),
        "type_id": str(node.type_id),
        "port_key": normalized_port_key,
        "port_label": str(port.label or port.key),
        "direction": str(port.direction),
        "kind": str(port.kind),
        "data_type": str(port.data_type),
        "accepted_data_types": list(port.accepted_data_types),
        "source_type_ids": list(resolver.source_contract(normalized_node_id, normalized_port_key).type_ids) if port.direction == "out" else [],
        "source_types_unresolved": resolver.source_contract(normalized_node_id, normalized_port_key).has_unresolved_sources,
    }


def build_connection_quick_insert_results(
    host: Any,
    combined_items: list[dict[str, Any]],
    query: str,
    quick_insert: Any,
) -> tuple[list[dict[str, Any]], int]:
    context = quick_insert.context
    if context is None:
        return [], -1
    normalized_query = str(query)
    results: list[dict[str, Any]] = []
    if connection_quick_insert_is_canvas_mode(context):
        results = build_canvas_quick_insert_items(
            combined_items=combined_items,
            query=normalized_query,
            limit=host._CONNECTION_QUICK_INSERT_LIMIT,
        )
    else:
        results = build_connection_quick_insert_items(
            combined_items=combined_items,
            data_types=host.registry.data_types,
            query=normalized_query,
            source_direction=str(context.get("direction", "")),
            source_kind=str(context.get("kind", "")),
            source_data_type=str(context.get("data_type", "")),
            source_accepted_data_types=context.get("accepted_data_types", ()),
            source_contract=ResolvedSourceContract(
                tuple(context.get("source_type_ids", ())),
                bool(context.get("source_types_unresolved", False)),
            ) if context.get("direction") == "out" else None,
            limit=host._CONNECTION_QUICK_INSERT_LIMIT,
        )
    highlight_index = 0 if results else -1
    if 0 <= quick_insert.highlight_index < len(results):
        highlight_index = quick_insert.highlight_index
    return results, highlight_index
