import QtQml 2.15
import "../common/TooltipPolicy.js" as TooltipPolicy

// Shared-by-reference canvas preference facts (grid, background, shadows,
// port labels, notched ports, tooltip categories, theme ids, pixel sizes,
// view-local port filters).
//
// Pass this object by reference instead of re-drilling each preference.
// New canvas preferences are added HERE (paired with the @pyqtProperty in
// graph_canvas_state/graphics_preferences_props.py); consumers read
// prefs.<fact> directly.
QtObject {
    id: facts
    property var stateBridge: null

    readonly property string canvasImportMode: facts.stateBridge
        ? String(facts.stateBridge.graphics_canvas_import_mode || "automatic")
        : "automatic"
    readonly property bool minimapExpanded: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_minimap_expanded)
        : true
    readonly property bool showGrid: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_show_grid)
        : true
    readonly property string canvasBackgroundVariant: facts.stateBridge
        ? String(facts.stateBridge.graphics_canvas_background_variant || "theme")
        : "theme"
    readonly property string gridStyle: facts.stateBridge
        ? String(facts.stateBridge.graphics_grid_style || "lines")
        : "lines"
    readonly property bool minimapVisible: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_show_minimap)
        : true
    readonly property bool showCanvasOptionsButton: facts.stateBridge
        && facts.stateBridge.graphics_show_canvas_options_button !== undefined
        ? Boolean(facts.stateBridge.graphics_show_canvas_options_button)
        : true
    readonly property bool showPortLabels: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_show_port_labels)
        : true
    readonly property bool notchedPortsEnabled: facts.stateBridge
        && facts.stateBridge.graphics_notched_ports !== undefined
        ? Boolean(facts.stateBridge.graphics_notched_ports)
        : true
    readonly property string nodeElapsedTimeVisibility: facts.stateBridge
        && facts.stateBridge.graphics_node_elapsed_time_visibility !== undefined
        ? String(facts.stateBridge.graphics_node_elapsed_time_visibility || "always")
        : "always"
    readonly property string nodeCommentEditorDefault: facts.stateBridge
        && facts.stateBridge.graphics_node_comment_editor_default !== undefined
        ? String(facts.stateBridge.graphics_node_comment_editor_default || "canvas_popover")
        : "canvas_popover"
    readonly property bool hideOptionalPorts: facts.stateBridge
        ? Boolean(facts.stateBridge.hide_optional_ports)
        : false
    readonly property string activeThemeId: facts.stateBridge
        ? String(facts.stateBridge.active_theme_id || "stitch_dark")
        : "stitch_dark"
    readonly property bool graphsFollowShellTheme: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_graph_follow_shell_theme)
        : true
    readonly property string selectedGraphThemeId: facts.stateBridge
        ? String(facts.stateBridge.graphics_selected_graph_theme_id || "graph_stitch_dark")
        : "graph_stitch_dark"
    readonly property var tooltipCategoryVisibility: TooltipPolicy.categoryVisibility(facts.stateBridge)
    readonly property bool showTooltips: facts.tooltipCategoryEnabled("general")
    readonly property int graphLabelPixelSize: {
        if (!facts.stateBridge)
            return 10;
        return facts._normalizePixelSize(facts.stateBridge.graphics_graph_label_pixel_size, 10, 50);
    }
    readonly property var graphNodeIconPixelSizeOverride: facts.stateBridge
        ? facts._normalizeNullablePixelSize(facts.stateBridge.graphics_graph_node_icon_pixel_size_override, 50)
        : null
    readonly property int nodeTitleIconPixelSize: {
        if (!facts.stateBridge)
            return facts.graphLabelPixelSize;
        return facts._normalizePixelSize(
            facts.stateBridge.graphics_node_title_icon_pixel_size,
            facts.graphLabelPixelSize,
            50
        );
    }
    readonly property string edgeCrossingStyle: facts.stateBridge
        ? String(facts.stateBridge.graphics_edge_crossing_style || "none")
        : "none"
    readonly property bool nodeShadowEnabled: facts.stateBridge
        ? Boolean(facts.stateBridge.graphics_node_shadow)
        : true
    readonly property int shadowStrength: facts.stateBridge
        ? facts.stateBridge.graphics_shadow_strength
        : 70
    readonly property int shadowSoftness: facts.stateBridge
        ? facts.stateBridge.graphics_shadow_softness
        : 50
    readonly property int shadowOffset: facts.stateBridge
        ? facts.stateBridge.graphics_shadow_offset
        : 4
    readonly property bool nodeFloatingToolbarOpensOnHover: facts.stateBridge
        && facts.stateBridge.graphics_node_floating_toolbar_opens_on_hover !== undefined
        ? Boolean(facts.stateBridge.graphics_node_floating_toolbar_opens_on_hover)
        : false
    readonly property bool mediaPanelAutoplayAnimations: facts.stateBridge
        && facts.stateBridge.graphics_media_panel_autoplay_animations !== undefined
        ? Boolean(facts.stateBridge.graphics_media_panel_autoplay_animations)
        : true

    function tooltipCategoryEnabled(category) {
        return TooltipPolicy.categoryEnabled(facts.stateBridge, category);
    }

    function _normalizePixelSize(value, fallback, maxValue) {
        if (typeof value === "boolean")
            return fallback;
        var numeric = Math.round(Number(value));
        if (!isFinite(numeric))
            return fallback;
        return Math.max(8, Math.min(maxValue, numeric));
    }

    function _normalizeNullablePixelSize(value, maxValue) {
        if (value === null || value === undefined || typeof value === "boolean")
            return null;
        var numeric = Math.round(Number(value));
        if (!isFinite(numeric))
            return null;
        return Math.max(8, Math.min(maxValue, numeric));
    }
}
