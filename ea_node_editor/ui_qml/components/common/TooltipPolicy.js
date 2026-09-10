.pragma library

var GENERAL = "general";
var TUTORIAL = "tutorial";
var ADVANCED = "advanced";
var WARNING = "warning";
var INACTIVE = "inactive";
var CRITICAL = "critical";

var DEFAULT_VISIBILITY = {
    "general": true,
    "tutorial": true,
    "advanced": false,
    "warning": true,
    "inactive": true,
    "critical": true
};

function normalizeCategory(category) {
    return String(category === undefined || category === null ? "" : category).trim().toLowerCase();
}

function isRegisteredCategory(category) {
    var normalized = normalizeCategory(category);
    return DEFAULT_VISIBILITY[normalized] !== undefined;
}

function defaultCategoryVisible(category) {
    var normalized = normalizeCategory(category);
    if (!isRegisteredCategory(normalized))
        return false;
    return Boolean(DEFAULT_VISIBILITY[normalized]);
}

function mapCategoryValue(payload, category) {
    if (!payload)
        return undefined;

    var normalized = normalizeCategory(category);
    if (payload[normalized] !== undefined)
        return payload[normalized];

    for (var key in payload) {
        if (normalizeCategory(key) === normalized)
            return payload[key];
    }
    return undefined;
}

function categoryEnabled(bridge, category) {
    var normalized = normalizeCategory(category);
    if (!isRegisteredCategory(normalized))
        return false;

    if (normalized === CRITICAL)
        return true;

    if (bridge) {
        var visibleValue = mapCategoryValue(bridge.graphics_tooltip_category_visibility, normalized);
        if (visibleValue !== undefined)
            return Boolean(visibleValue);

        var categoryValue = mapCategoryValue(bridge.graphics_tooltip_categories, normalized);
        if (categoryValue !== undefined)
            return Boolean(categoryValue);

        if (typeof bridge.tooltip_category_enabled === "function")
            return Boolean(bridge.tooltip_category_enabled(normalized));

        if (normalized === GENERAL && bridge.graphics_show_tooltips !== undefined)
            return Boolean(bridge.graphics_show_tooltips);
    }

    return defaultCategoryVisible(normalized);
}

function tooltipVisible(bridge, category, requestedVisible) {
    return Boolean(requestedVisible) && categoryEnabled(bridge, category);
}

function categoryVisibility(bridge) {
    return {
        "general": categoryEnabled(bridge, GENERAL),
        "tutorial": categoryEnabled(bridge, TUTORIAL),
        "advanced": categoryEnabled(bridge, ADVANCED),
        "warning": categoryEnabled(bridge, WARNING),
        "inactive": categoryEnabled(bridge, INACTIVE),
        "critical": categoryEnabled(bridge, CRITICAL)
    };
}
