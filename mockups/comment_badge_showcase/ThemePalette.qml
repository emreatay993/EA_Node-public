import QtQuick

// Throwaway mockup theme source. One instance lives in Main.qml and is passed
// by reference into every concept + shared component, so flipping `isDark`
// re-themes the whole gallery instantly. NOT a singleton (per project rule);
// values mirror the real app's Stitch Dark / Stitch Light tokens plus the
// node_comments mockup's comment amber family (NodeCommentMockupTheme.js).
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
    readonly property color accentStrong: isDark ? "#1D8CE0" : "#b9dcf7"
    // contrast colour to lay text/glyphs on top of a solid accent fill
    readonly property color onAccent:     isDark ? "#0c2230" : "#ffffff"

    // ---- node card specifics ----
    readonly property color nodeBg:       isDark ? "#1b1d22" : "#f5f7fa"
    readonly property color nodeHeaderBg: isDark ? "#2a2b30" : "#e5ebf2"

    // ---- comment family (amber; matches the node_comments in-package mockup) ----
    readonly property color comment:       isDark ? "#F2B84B" : "#D58E1E"
    readonly property color commentSoft:   isDark ? "#3c321f" : "#FFF4DA"
    readonly property color commentBorder: isDark ? "#765f2b" : "#E3B660"
    // contrast colour for text/glyphs on a solid `comment` fill
    readonly property color onComment:     isDark ? "#241a08" : "#ffffff"

    // ---- resolution states ----
    readonly property color success:     isDark ? "#64C88A" : "#247B4F"
    readonly property color successSoft: isDark ? "#20372a" : "#DDF3E8"
    readonly property color danger:      isDark ? "#ff7a7a" : "#B34B55"

    readonly property string fontFamily: "Segoe UI"

    // "Nora Vance" -> "NV" (peek-card avatar discs)
    function initials(name) {
        var words = String(name || "").trim().split(/\s+/);
        if (!words.length || !words[0].length)
            return "?";
        if (words.length === 1)
            return words[0].slice(0, 1).toUpperCase();
        return (words[0].slice(0, 1) + words[1].slice(0, 1)).toUpperCase();
    }
}
