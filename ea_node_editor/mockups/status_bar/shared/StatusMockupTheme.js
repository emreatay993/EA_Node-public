.pragma library

// Palette tokens for the status/performance-bar mockups. Values mirror the real
// shell theme tokens in ea_node_editor/ui/theme/tokens.py (STITCH dark/light),
// extended with status-bar tokens and semantic status colors that the five
// design routes need (success / warning / error tuned per theme for legibility).
function shellPalette(themeName) {
    if (String(themeName || "") === "light") {
        return {
            app_bg: "#eef2f6",
            panel_bg: "#f5f7fa",
            panel_alt_bg: "#ffffff",
            toolbar_bg: "#e5ebf2",
            border: "#b7c2ce",
            hover: "#dbe4ee",
            pressed: "#cfd9e6",
            input_bg: "#ffffff",
            input_border: "#96a6ba",
            input_fg: "#17212b",
            accent: "#1D8CE0",
            accent_strong: "#b9dcf7",
            canvas_bg: "#f3f5f8",
            canvas_minor_grid: "#d9dfe8",
            canvas_major_grid: "#c0c9d6",
            muted_fg: "#5f6b7a",
            panel_title_fg: "#1b2733",
            group_title_fg: "#4f5e70",
            tab_bg: "#dce4ec",
            tab_fg: "#314154",
            tab_selected_bg: "#edf3f8",
            tab_selected_fg: "#162231",
            // Status-bar specific tokens (real shell uses these for the strip)
            status_bg: "#dceefb",
            status_border: "#9ec8e5",
            status_fg: "#173449",
            status_hover_bg: "#14000000", // rgba(0,0,0,0.08)
            // Semantic status colors (darkened for contrast on light surfaces)
            success: "#1f9d57",
            warning: "#c77a06",
            error: "#c2403b",
            success_soft: "#d8f0e2",
            warning_soft: "#fbeacd",
            error_soft: "#f7dcda"
        };
    }
    return {
        app_bg: "#1f1f1f",
        panel_bg: "#1b1d22",
        panel_alt_bg: "#24262c",
        toolbar_bg: "#2a2b30",
        border: "#3a3d45",
        hover: "#33373f",
        pressed: "#2d3139",
        input_bg: "#22242a",
        input_border: "#4a4f5a",
        input_fg: "#f0f2f5",
        accent: "#60CDFF",
        accent_strong: "#1D8CE0",
        canvas_bg: "#1d1f24",
        canvas_minor_grid: "#2b2f38",
        canvas_major_grid: "#323746",
        muted_fg: "#d0d5de",
        panel_title_fg: "#f0f4fb",
        group_title_fg: "#bdc5d3",
        tab_bg: "#2a2d34",
        tab_fg: "#d8deea",
        tab_selected_bg: "#2f343e",
        tab_selected_fg: "#f2f4f8",
        status_bg: "#24a2dc",
        status_border: "#1b7daf",
        status_fg: "#ffffff",
        status_hover_bg: "#21ffffff", // rgba(255,255,255,0.13)
        success: "#67D487",
        warning: "#E8A838",
        error: "#D94F4F",
        success_soft: "#1f3a2c",
        warning_soft: "#3a3320",
        error_soft: "#3a2528"
    };
}

// Engine state -> signature color. States: ready | running | paused | error.
function stateColor(palette, state) {
    var s = String(state || "ready");
    if (s === "running")
        return palette.accent;
    if (s === "paused")
        return palette.warning;
    if (s === "error")
        return palette.error;
    return palette.success; // ready / idle
}

// Soft background tint that pairs with stateColor (used for state pills).
function stateSoftColor(palette, state) {
    var s = String(state || "ready");
    if (s === "running")
        return palette.accent_strong;
    if (s === "paused")
        return palette.warning_soft;
    if (s === "error")
        return palette.error_soft;
    return palette.success_soft;
}

// Human label for an engine state.
function stateLabel(state) {
    var s = String(state || "ready");
    if (s === "running")
        return "Running";
    if (s === "paused")
        return "Paused";
    if (s === "error")
        return "Error";
    return "Ready";
}

// Threshold color for a 0..1 utilization ratio (green -> amber -> red).
function metricColor(palette, ratio) {
    var r = Number(ratio);
    if (isNaN(r))
        r = 0;
    if (r >= 0.85)
        return palette.error;
    if (r >= 0.6)
        return palette.warning;
    return palette.success;
}
