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
            on_accent: "#eef8ff",
            accent_soft: "#d9edf9",
            canvas_bg: "#f3f5f8",
            canvas_minor_grid: "#d9dfe8",
            canvas_major_grid: "#c0c9d6",
            muted_fg: "#5f6b7a",
            panel_title_fg: "#1b2733",
            group_title_fg: "#4f5e70",
            comment: "#D58E1E",
            comment_soft: "#FFF4DA",
            comment_border: "#E3B660",
            success: "#247B4F",
            success_soft: "#DDF3E8",
            danger: "#B34B55"
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
        on_accent: "#0c2230",
        accent_soft: "#183344",
        canvas_bg: "#1d1f24",
        canvas_minor_grid: "#2b2f38",
        canvas_major_grid: "#323746",
        muted_fg: "#d0d5de",
        panel_title_fg: "#f0f4fb",
        group_title_fg: "#bdc5d3",
        comment: "#F2B84B",
        comment_soft: "#3c321f",
        comment_border: "#765f2b",
        success: "#64C88A",
        success_soft: "#20372a",
        danger: "#ff7a7a"
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
            header_gradient: "#d7e2ee",
            inline_row_bg: "#ffffff",
            inline_row_border: "#96a6ba",
            inline_label_fg: "#5f6b7a",
            inline_input_fg: "#17212b",
            inline_driven_fg: "#4f5e70",
            scope_badge_bg: "#1D8CE0",
            scope_badge_border: "#5DADE2",
            scope_badge_fg: "#eef8ff"
        };
    }
    return {
        card_bg: "#1b1d22",
        card_border: "#3a3d45",
        card_selected_border: "#60CDFF",
        header_bg: "#2a2b30",
        header_fg: "#f0f4fb",
        header_gradient: "#20252f",
        inline_row_bg: "#24262c",
        inline_row_border: "#4a4f5a",
        inline_label_fg: "#d0d5de",
        inline_input_fg: "#f0f2f5",
        inline_driven_fg: "#bdc5d3",
        scope_badge_bg: "#1D8CE0",
        scope_badge_border: "#60CDFF",
        scope_badge_fg: "#f2f4f8"
    };
}

function initials(name) {
    var words = String(name || "").trim().split(/\s+/);
    if (!words.length || !words[0].length)
        return "?";
    if (words.length === 1)
        return words[0].slice(0, 1).toUpperCase();
    return (words[0].slice(0, 1) + words[1].slice(0, 1)).toUpperCase();
}
