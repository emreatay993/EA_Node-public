import QtQuick

// Throwaway mockup theme. One instance lives in Main.qml, passed by reference
// into everything, so flipping `isDark` re-themes instantly. NOT a singleton
// (per project rule); values mirror the real app's Stitch Dark / Stitch Light
// tokens (ea_node_editor/ui/theme/tokens.py), plus execution-state colours.
QtObject {
    id: t

    property bool isDark: true

    // ---- surfaces ----
    readonly property color appBg:      isDark ? "#1f1f1f" : "#eef2f6"
    readonly property color panelBg:    isDark ? "#1b1d22" : "#f5f7fa"
    readonly property color panelAltBg: isDark ? "#24262c" : "#ffffff"
    readonly property color toolbarBg:  isDark ? "#2a2b30" : "#e5ebf2"
    readonly property color canvasBg:   isDark ? "#1d1f24" : "#f3f5f8"
    readonly property color inputBg:    isDark ? "#22242a" : "#ffffff"

    // ---- lines ----
    readonly property color border:      isDark ? "#3a3d45" : "#b7c2ce"
    readonly property color inputBorder: isDark ? "#4a4f5a" : "#96a6ba"
    readonly property color gridMinor:   isDark ? "#2b2f38" : "#d9dfe8"
    readonly property color gridMajor:   isDark ? "#323746" : "#c0c9d6"

    // ---- states ----
    readonly property color hover:   isDark ? "#33373f" : "#dbe4ee"
    readonly property color pressed: isDark ? "#2d3139" : "#cfd9e6"

    // ---- text ----
    readonly property color appFg:   isDark ? "#e8e8e8" : "#17212b"
    readonly property color inputFg: isDark ? "#f0f2f5" : "#17212b"
    readonly property color mutedFg: isDark ? "#9aa3af" : "#5b6b7b"

    // ---- accent ----
    readonly property color accent:       isDark ? "#60CDFF" : "#1D8CE0"
    readonly property color accentStrong: isDark ? "#1D8CE0" : "#1473c4"
    readonly property color onAccent:     isDark ? "#0c2230" : "#ffffff"

    // ---- node card ----
    readonly property color nodeBg:       isDark ? "#20232a" : "#ffffff"
    readonly property color nodeHeaderBg: isDark ? "#2a2d35" : "#e9eef4"
    readonly property color nodeBodyBg:   isDark ? "#191b20" : "#fbfcfe"

    // ---- execution-state palette (traffic light) ----
    readonly property color stIdle:       isDark ? "#5a6170" : "#9aa7b6"
    readonly property color stConfigured: isDark ? "#7f93ad" : "#6d8198"
    readonly property color stQueued:     isDark ? "#e6b450" : "#c98a18"
    readonly property color stRunning:    accent
    readonly property color stDone:       isDark ? "#46c98b" : "#1c9e63"
    readonly property color stError:      isDark ? "#ef5d6b" : "#d23b4a"
    readonly property color stBlocked:    isDark ? "#7a5a60" : "#9a7a80"
    readonly property color stBypassed:   isDark ? "#565c68" : "#aab4c0"

    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFamily: "Consolas"

    function stateColor(s) {
        var m = {
            idle: stIdle, configured: stConfigured, queued: stQueued,
            running: stRunning, done: stDone, error: stError,
            blocked: stBlocked, bypassed: stBypassed
        };
        return m[s] !== undefined ? m[s] : stIdle;
    }

    function stateLabel(s) {
        var m = {
            idle: "Idle", configured: "Ready", queued: "Queued",
            running: "Running", done: "Done", error: "Error",
            blocked: "Blocked", bypassed: "Bypassed"
        };
        return m[s] !== undefined ? m[s] : s;
    }
}
