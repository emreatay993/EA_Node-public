import QtQuick 2.15

// Base component for passive/viewer node surfaces.
//
// Owns the host/null-safe property plumbing every surface used to copy:
// node-property accessors (propRaw/propValue/propString/propBool/propNumber)
// and the chrome facts (surfaceShowTitle/surfaceShowFrame/surfaceContentOnly,
// the single derivation consistent with host.chromeToggleCapableSurface).
// Surfaces set their root to GraphSurfaceBase, set `chromeToggleAvailable`
// when their family supports chrome toggles, and must not re-declare local
// accessor copies. Dispatch stays unchanged: GraphNodeSurfaceLoader resolves
// qml_component paths from surface_contracts.py and assigns `host`.
Item {
    id: surfaceBase
    property Item host: null

    readonly property var nodeProperties: host && host.nodeData && host.nodeData.properties
        ? host.nodeData.properties
        : ({})

    // Chrome facts. Surfaces whose family supports the show-title/show-frame
    // toggles bind chromeToggleAvailable (default follows the host's
    // chromeToggleCapableSurface contract).
    property bool chromeToggleAvailable: host ? Boolean(host.chromeToggleCapableSurface) : false
    readonly property bool surfaceShowTitle: !chromeToggleAvailable || propBool("show_title", true)
    readonly property bool surfaceShowFrame: !chromeToggleAvailable || propBool("show_frame", true)
    readonly property bool surfaceContentOnly: chromeToggleAvailable
        && !propBool("show_title", true)
        && !propBool("show_frame", true)

    // Standard content margin for framed surface bodies.
    readonly property real surfaceContentMargin: 8.0
    readonly property real surfaceBodyBottomMargin: {
        if (!host || !host.surfaceMetrics)
            return 0.0;
        var metrics = host.surfaceMetrics;
        var bodyEnd = Number(metrics.port_top);
        if (!isFinite(bodyEnd))
            bodyEnd = Number(metrics.body_top || 0.0) + Number(metrics.body_height || 0.0);
        return Math.max(0.0, Number(host.height) - bodyEnd);
    }

    function propRaw(key, fallback) {
        var value = surfaceBase.nodeProperties[key];
        return value === undefined || value === null ? fallback : value;
    }

    function propValue(key) {
        var value = surfaceBase.nodeProperties[key];
        if (value === undefined || value === null)
            return "";
        return String(value);
    }

    function propString(key, fallback) {
        var value = surfaceBase.nodeProperties[key];
        if (value === undefined || value === null)
            return String(fallback !== undefined ? fallback : "");
        return String(value);
    }

    function propBool(key, fallback) {
        var value = surfaceBase.propRaw(key, fallback);
        if (typeof value === "boolean")
            return value;
        if (typeof value === "string") {
            var normalized = value.trim().toLowerCase();
            if (normalized === "true" || normalized === "1" || normalized === "yes")
                return true;
            if (normalized === "false" || normalized === "0" || normalized === "no")
                return false;
        }
        return Boolean(value);
    }

    function propNumber(key, fallback) {
        var numeric = Number(surfaceBase.propRaw(key, fallback));
        return isFinite(numeric) ? numeric : fallback;
    }
}
