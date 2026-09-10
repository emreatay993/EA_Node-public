// Shared canvas-background color mapping. Consumed by GraphCanvasBackground
// (the actual canvas fill) and GraphNodePortsLayer (port notch disks that must
// visually match the canvas behind the node edge). Keep the two in sync by
// editing only this file.
.pragma library

function effectiveVariant(variant) {
    var normalized = String(variant || "theme").toLowerCase().trim();
    if (normalized === "dark" || normalized === "light" || normalized === "white")
        return normalized;
    return "theme";
}

function fillColor(variant, themePalette) {
    var resolved = effectiveVariant(variant);
    if (resolved === "dark")
        return "#1d1f24";
    if (resolved === "light")
        return "#f3f5f8";
    if (resolved === "white")
        return "#ffffff";
    return themePalette && themePalette.canvas_bg ? themePalette.canvas_bg : "#1d1f24";
}
