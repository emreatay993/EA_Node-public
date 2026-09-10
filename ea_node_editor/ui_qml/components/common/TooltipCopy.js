// Purpose: Thin QML wrapper around the tooltipCopyBridge registry lookup.
// Map: docs/agent_maps/feature_routes/tooltips_and_tiers.md
// Tests: tests/test_tooltip_copy_registry.py

var COPY_FILES = [
    "../../../ui/tooltips/actions.json",
    "../../../ui/tooltips/nodes.json",
    "../../../ui/tooltips/settings.json",
    "../../../ui/tooltips/graph.json",
    "../../../ui/tooltips/inspector.json",
    "../../../ui/tooltips/shell.json",
    "../../../ui/tooltips/fullscreen.json",
    "../../../ui/tooltips/viewer.json",
    "../../../ui/tooltips/tabular.json"
];

function text(bridge, key, fallback) {
    var defaultText = fallback === undefined ? "" : String(fallback);
    try {
        if (bridge)
            return String(bridge.text(String(key || ""), defaultText));
    } catch (error) {
        return defaultText;
    }
    return defaultText;
}

function category(bridge, key, fallback) {
    var defaultCategory = fallback === undefined ? "general" : String(fallback);
    try {
        if (bridge)
            return String(bridge.category(String(key || ""), defaultCategory));
    } catch (error) {
        return defaultCategory;
    }
    return defaultCategory;
}

function files() {
    return COPY_FILES.slice(0);
}
