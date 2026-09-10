.pragma library

function shellPalette(themeName) {
    if (String(themeName || "") === "light") {
        return {
            app_bg: "#eef2f6",
            app_fg: "#17212b",
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
            inspector_danger_bg: "#fae7e9",
            inspector_danger_border: "#d28c94",
            inspector_danger_fg: "#98434c"
        };
    }
    return {
        app_bg: "#1f1f1f",
        app_fg: "#e8e8e8",
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
        inspector_danger_bg: "#392629",
        inspector_danger_border: "#b96a72",
        inspector_danger_fg: "#f1b0b7"
    };
}

function nodePalette(themeName) {
    if (String(themeName || "") === "light") {
        return {
            card_bg: "#f5f7fa",
            card_border: "#b7c2ce",
            card_selected_border: "#1D8CE0",
            header_bg: "#e5ebf2",
            header_fg: "#1b2733",
            inline_row_bg: "#ffffff",
            inline_row_border: "#96a6ba",
            inline_label_fg: "#5f6b7a",
            inline_input_fg: "#17212b",
            inline_input_bg: "#ffffff",
            inline_input_border: "#96a6ba",
            inline_driven_fg: "#4f5e70",
            port_label_fg: "#5f6b7a",
            port_interactive_fill: "#FFDA6B",
            port_interactive_border: "#E7C35D",
            port_interactive_ring_fill: "#33A7D98A",
            port_interactive_ring_border: "#5598C971"
        };
    }
    return {
        card_bg: "#1b1d22",
        card_border: "#3a3d45",
        card_selected_border: "#60CDFF",
        header_bg: "#2a2b30",
        header_fg: "#f0f4fb",
        inline_row_bg: "#24262c",
        inline_row_border: "#4a4f5a",
        inline_label_fg: "#d0d5de",
        inline_input_fg: "#f0f2f5",
        inline_input_bg: "#22242a",
        inline_input_border: "#4a4f5a",
        inline_driven_fg: "#bdc5d3",
        port_label_fg: "#d0d5de",
        port_interactive_fill: "#FFDA6B",
        port_interactive_border: "#FFE48B",
        port_interactive_ring_fill: "#44FFC857",
        port_interactive_ring_border: "#66FFE29A"
    };
}

function edgePalette(themeName) {
    if (String(themeName || "") === "light") {
        return {
            selected_stroke: "#1b2733",
            preview_stroke: "#1D8CE0",
            warning_stroke: "#D58E1E"
        };
    }
    return {
        selected_stroke: "#f0f4fb",
        preview_stroke: "#60CDFF",
        warning_stroke: "#E8A838"
    };
}
