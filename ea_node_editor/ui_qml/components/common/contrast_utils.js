.pragma library

function parseColor(value) {
    if (value === null || value === undefined)
        return null;
    var text = String(value).trim();
    if (text.length === 0)
        return null;

    if (text.charAt(0) === "#") {
        var hex = text.substring(1);
        if (hex.length === 3) {
            var r3 = parseInt(hex.charAt(0) + hex.charAt(0), 16);
            var g3 = parseInt(hex.charAt(1) + hex.charAt(1), 16);
            var b3 = parseInt(hex.charAt(2) + hex.charAt(2), 16);
            if (isNaN(r3) || isNaN(g3) || isNaN(b3))
                return null;
            return { r: r3, g: g3, b: b3 };
        }
        if (hex.length === 6 || hex.length === 8) {
            var offset = hex.length === 8 ? 2 : 0;
            var r = parseInt(hex.substring(offset, offset + 2), 16);
            var g = parseInt(hex.substring(offset + 2, offset + 4), 16);
            var b = parseInt(hex.substring(offset + 4, offset + 6), 16);
            if (isNaN(r) || isNaN(g) || isNaN(b))
                return null;
            return { r: r, g: g, b: b };
        }
        return null;
    }

    var rgbMatch = text.match(/^rgba?\s*\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*[0-9.]+\s*)?\)$/i);
    if (rgbMatch) {
        var rr = parseFloat(rgbMatch[1]);
        var gg = parseFloat(rgbMatch[2]);
        var bb = parseFloat(rgbMatch[3]);
        if (isNaN(rr) || isNaN(gg) || isNaN(bb))
            return null;
        return { r: Math.max(0, Math.min(255, rr)), g: Math.max(0, Math.min(255, gg)), b: Math.max(0, Math.min(255, bb)) };
    }

    return null;
}

function _linearize(channel) {
    var c = channel / 255.0;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function relativeLuminance(rgb) {
    if (!rgb)
        return 0;
    return 0.2126 * _linearize(rgb.r) + 0.7152 * _linearize(rgb.g) + 0.0722 * _linearize(rgb.b);
}

function contrastRatio(fg, bg) {
    var fgRgb = parseColor(fg);
    var bgRgb = parseColor(bg);
    if (!fgRgb || !bgRgb)
        return 0;
    var l1 = relativeLuminance(fgRgb);
    var l2 = relativeLuminance(bgRgb);
    var lighter = Math.max(l1, l2);
    var darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
}

function pickReadableForeground(preferred, fallback, background, minRatio) {
    var threshold = (typeof minRatio === "number" && minRatio > 0) ? minRatio : 3.0;
    if (contrastRatio(preferred, background) >= threshold)
        return preferred;
    return fallback;
}

function firstColor(palette, keys, fallback) {
    var source = palette || {};
    for (var i = 0; i < keys.length; i++) {
        var value = source[keys[i]];
        if (value !== undefined && value !== null && String(value).trim().length > 0)
            return String(value);
    }
    return String(fallback || "");
}

function inputForeground(palette) {
    return firstColor(palette, ["input_fg", "panel_fg", "panel_title_fg"], "#eef3ff");
}

function inputSelectionBackground(palette) {
    return firstColor(palette, ["input_selection_bg", "selection_bg", "accent"], "#5da9ff");
}

function inputSelectedForeground(palette) {
    var background = inputSelectionBackground(palette);
    var preferred = firstColor(palette, ["input_selected_fg", "selection_fg", "input_fg"], "");
    var darkFallback = firstColor(palette, ["panel_title_fg", "panel_fg"], "#111827");
    return pickHighestContrastForeground(preferred, darkFallback, "#ffffff", background, 4.5);
}

function pickHighestContrastForeground(preferred, fallbackA, fallbackB, background, minRatio) {
    var threshold = (typeof minRatio === "number" && minRatio > 0) ? minRatio : 3.0;
    if (contrastRatio(preferred, background) >= threshold)
        return preferred;
    return contrastRatio(fallbackA, background) >= contrastRatio(fallbackB, background) ? fallbackA : fallbackB;
}
