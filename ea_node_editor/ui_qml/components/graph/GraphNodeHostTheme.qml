import QtQuick 2.15

QtObject {
    id: root
    property var host: null

    readonly property var passiveStyle: host && host.isPassiveNode && host.nodeData && host.nodeData.visual_style
        ? host.nodeData.visual_style
        : ({})
    readonly property string passiveFillOverride: host ? host._styleString(root.passiveStyle.fill_color) : ""
    readonly property string passiveBorderOverride: host ? host._styleString(root.passiveStyle.border_color) : ""
    readonly property string passiveTextOverride: host ? host._styleString(root.passiveStyle.text_color) : ""
    readonly property string passiveBodyGradientColorOverride: host ? host._styleString(root.passiveStyle.gradient_color) : ""
    readonly property bool hasPassiveFillOverride: !!host && host.isPassiveNode && root.passiveFillOverride.length > 0
    readonly property bool hasPassiveBorderOverride: !!host && host.isPassiveNode && root.passiveBorderOverride.length > 0
    readonly property bool hasPassiveTextOverride: !!host && host.isPassiveNode && root.passiveTextOverride.length > 0
    readonly property bool hasPassiveBodyGradientEnabledOverride: !!host
        && host.isPassiveNode
        && root._hasStyleKey(root.passiveStyle, "gradient_enabled")
    readonly property bool usesPathPointerActiveInlineContrast: !!host
        && host.isPassiveNode
        && host.nodeData
        && String(host.nodeData.type_id || "") === "io.path_pointer"

    readonly property color themeSurfaceColor: host && host.nodePalette ? (host.nodePalette.card_bg || "#1b1d22") : "#1b1d22"
    readonly property bool themeBodyGradientEnabled: root._styleBool(
        host && host.nodePalette ? host.nodePalette.card_gradient_enabled : false,
        false
    )
    readonly property color themeBodyGradientColor: host && host.nodePalette
        ? (host.nodePalette.card_gradient_color || root.themeSurfaceColor)
        : root.themeSurfaceColor
    readonly property string themeBodyGradientDirection: root._gradientDirection(
        host && host.nodePalette ? host.nodePalette.card_gradient_direction : "south"
    )
    readonly property color themeOutlineColor: host && host.nodePalette ? (host.nodePalette.card_border || "#3a3d45") : "#3a3d45"
    readonly property color themeSelectedOutlineColor: host && host.nodePalette
        ? (host.nodePalette.card_selected_border || "#60CDFF")
        : "#60CDFF"
    readonly property color themeHeaderTextColor: host && host.nodePalette
        ? (host.nodePalette.header_fg || "#f0f4fb")
        : "#f0f4fb"
    readonly property color themeScopeBadgeColor: host && host.nodePalette
        ? (host.nodePalette.scope_badge_bg || "#1D8CE0")
        : "#1D8CE0"
    readonly property color themeScopeBadgeBorderColor: host && host.nodePalette
        ? (host.nodePalette.scope_badge_border || "#60CDFF")
        : "#60CDFF"
    readonly property color themeScopeBadgeTextColor: host && host.nodePalette
        ? (host.nodePalette.scope_badge_fg || "#f2f4f8")
        : "#f2f4f8"
    readonly property color themeInlineRowColor: host && host.nodePalette
        ? (host.nodePalette.inline_row_bg || "#24262c")
        : "#24262c"
    readonly property color themeInlineRowBorderColor: host && host.nodePalette
        ? (host.nodePalette.inline_row_border || "#4a4f5a")
        : "#4a4f5a"
    readonly property color themeInlineLabelColor: host && host.nodePalette
        ? (host.nodePalette.inline_label_fg || "#d0d5de")
        : "#d0d5de"
    readonly property color themeInlineInputTextColor: host && host.nodePalette
        ? (host.nodePalette.inline_input_fg || "#f0f2f5")
        : "#f0f2f5"
    readonly property color themeInlineInputBackgroundColor: host && host.nodePalette
        ? (host.nodePalette.inline_input_bg || "#22242a")
        : "#22242a"
    readonly property color themeInlineInputBorderColor: host && host.nodePalette
        ? (host.nodePalette.inline_input_border || "#4a4f5a")
        : "#4a4f5a"
    readonly property color themeInlineDrivenTextColor: host && host.nodePalette
        ? (host.nodePalette.inline_driven_fg || "#bdc5d3")
        : "#bdc5d3"
    readonly property color themePortLabelColor: host && host.nodePalette
        ? (host.nodePalette.port_label_fg || "#d0d5de")
        : "#d0d5de"

    readonly property var shellThemeBridge: host
        && typeof host.shellContextRef !== "undefined"
        && host.shellContextRef
        ? host.shellContextRef.themeBridge
        : null
    readonly property string activeShellThemeId: root.shellThemeBridge
        && typeof root.shellThemeBridge.theme_id !== "undefined"
        ? String(root.shellThemeBridge.theme_id || "").trim().toLowerCase()
        : (host && host.prefs && typeof host.prefs.activeThemeId !== "undefined"
            ? String(host.prefs.activeThemeId || "").trim().toLowerCase()
            : "")
    readonly property bool usesDarkActivePalette: root.activeShellThemeId.length > 0
        ? root.activeShellThemeId.indexOf("light") < 0
        : ((0.2126 * root.themeSurfaceColor.r
            + 0.7152 * root.themeSurfaceColor.g
            + 0.0722 * root.themeSurfaceColor.b) < 0.5)
    readonly property bool reservedDisabledActive: !!host
        && !host.isPassiveNode
        && typeof host.isDisabledNode !== "undefined"
        && Boolean(host.isDisabledNode)
    readonly property string activeSemanticState: !host || host.isPassiveNode
        ? "passive"
        : (host.isSelected
            ? "selected"
            : (root.reservedDisabledActive
                ? "disabled"
                : (host.isFailedNode
                    ? "error"
                    : (host.isWarningChromeNode ? "warning" : "default"))))
    readonly property var activeSemanticColors: root._activeStateColors(
        root.activeSemanticState,
        root.usesDarkActivePalette
    )
    readonly property var activeContentColors: root.reservedDisabledActive
        ? root._activeStateColors("disabled", root.usesDarkActivePalette)
        : root.activeSemanticColors
    readonly property color flowchartDefaultFillColor: "#F5FAFD"
    readonly property color flowchartDefaultOutlineColor: "#61798B"
    readonly property color flowchartDefaultTextColor: "#173247"
    readonly property color failureOutlineColor: root._activeStateColors("error", root.usesDarkActivePalette).outline
    readonly property color failureBadgeFillColor: root.failureOutlineColor
    readonly property color failureBadgeBorderColor: root.failureOutlineColor
    readonly property color failureBadgeTextColor: "#FFFFFF"
    readonly property color runningOutlineColor: "#4A9EFF"
    readonly property color warningOutlineColor: root._activeStateColors("warning", root.usesDarkActivePalette).outline
    readonly property color completedOutlineColor: "#4ADE80"
    readonly property color runningElapsedFooterColor: root.runningOutlineColor
    readonly property color warningElapsedFooterColor: root.warningOutlineColor
    readonly property color completedElapsedFooterColor: root.completedOutlineColor
    readonly property real runningElapsedFooterOpacity: 0.88
    readonly property real warningElapsedFooterOpacity: 0.84
    readonly property real completedElapsedFooterOpacity: 0.72

    readonly property color surfaceColor: host && host.isPassiveNode
        ? (root.passiveFillOverride || (host.isFlowchartSurface ? root.flowchartDefaultFillColor : root.themeSurfaceColor))
        : root.activeSemanticColors.start
    readonly property color outlineColor: host && host.isPassiveNode
        ? (root.passiveBorderOverride || (host.isFlowchartSurface ? root.flowchartDefaultOutlineColor : root.themeOutlineColor))
        : root.activeSemanticColors.outline
    readonly property color selectedOutlineColor: host && host.isPassiveNode
        ? root.themeSelectedOutlineColor
        : root._activeStateColors("selected", root.usesDarkActivePalette).outline
    readonly property color selectedGlowColor: Qt.lighter(root.selectedOutlineColor, 1.25)
    readonly property bool bodyGradientEnabled: !!host
        && !host.lockedPlaceholderActive
        && (host.isPassiveNode
            ? (root.hasPassiveBodyGradientEnabledOverride
                ? root._styleBool(root.passiveStyle.gradient_enabled, false)
                : root.themeBodyGradientEnabled)
            : true)
    readonly property color bodyGradientStartColor: root.surfaceColor
    readonly property color bodyGradientEndColor: host && host.isPassiveNode
        ? (root.passiveBodyGradientColorOverride.length > 0
            ? root.passiveBodyGradientColorOverride
            : root.themeBodyGradientColor)
        : root.activeSemanticColors.end
    readonly property string bodyGradientDirection: host && host.isPassiveNode && root.passiveBodyGradientColorOverride.length > 0
        ? root._gradientDirection(root.passiveStyle.gradient_direction)
        : (host && host.isPassiveNode ? root.themeBodyGradientDirection : "south")
    readonly property bool bodyGradientActive: root.bodyGradientEnabled && String(root.bodyGradientEndColor).length > 0
    readonly property color headerTextColor: host && host.isPassiveNode
        ? (root.passiveTextOverride || (host.isFlowchartSurface ? root.flowchartDefaultTextColor : root.themeHeaderTextColor))
        : root.activeContentColors.title
    readonly property color scopeBadgeColor: host && host.isPassiveNode
        ? (host.isFlowchartSurface ? root.selectedOutlineColor : root.themeScopeBadgeColor)
        : root.activeSemanticColors.outline
    readonly property color scopeBadgeBorderColor: host && host.isPassiveNode
        ? Qt.lighter(root.scopeBadgeColor, 1.16)
        : root.activeSemanticColors.outline
    readonly property color scopeBadgeTextColor: host && host.isPassiveNode
        ? "#f2f4f8"
        : root.activeContentColors.title
    readonly property color inlineRowColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineRowColor : "#ffffff")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineRowColor
        : (host && host.isPassiveNode ? Qt.darker(root.surfaceColor, 1.04) : root.themeInlineRowColor))
    readonly property color inlineRowBorderColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineRowBorderColor : "#ccd6e0")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineRowBorderColor
        : (host && host.isPassiveNode
        ? Qt.alpha(root.outlineColor, 0.85)
        : root.themeInlineRowBorderColor))
    readonly property color inlineLabelColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineLabelColor : "#5f6b7a")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineLabelColor
        : (host && host.isPassiveNode
        ? Qt.alpha(root.headerTextColor, 0.82)
        : root.themeInlineLabelColor))
    readonly property color inlineInputTextColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineInputTextColor : "#17212b")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineInputTextColor
        : (host && host.isPassiveNode
        ? root.headerTextColor
        : root.themeInlineInputTextColor))
    readonly property color inlineInputBackgroundColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineInputBackgroundColor : "#ffffff")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineInputBackgroundColor
        : (host && host.isPassiveNode
        ? Qt.darker(root.surfaceColor, 1.08)
        : root.themeInlineInputBackgroundColor))
    readonly property color inlineInputBorderColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineInputBorderColor : "#c2cedb")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineInputBorderColor
        : (host && host.isPassiveNode
        ? Qt.alpha(root.outlineColor, 0.9)
        : root.themeInlineInputBorderColor))
    readonly property color inlineDrivenTextColor: host && !host.isPassiveNode
        ? (root.usesDarkActivePalette ? root.themeInlineDrivenTextColor : "#4f5e70")
        : (root.usesPathPointerActiveInlineContrast
        ? root.themeInlineDrivenTextColor
        : (host && host.isPassiveNode
        ? Qt.alpha(root.headerTextColor, 0.72)
        : root.themeInlineDrivenTextColor))
    readonly property color portLabelColor: host && host.isPassiveNode
        ? Qt.alpha(root.headerTextColor, host.usesCardinalNeutralFlowHandles ? 0.74 : 0.84)
        : root.activeContentColors.ports
    readonly property color portInteractiveFillColor: host && host.usesCardinalNeutralFlowHandles
        ? Qt.alpha(root.selectedOutlineColor, 0.18)
        : ((host && host.nodePalette) ? (host.nodePalette.port_interactive_fill || "#FFDA6B") : "#FFDA6B")
    readonly property color portInteractiveBorderColor: host && host.usesCardinalNeutralFlowHandles
        ? root.selectedOutlineColor
        : ((host && host.nodePalette) ? (host.nodePalette.port_interactive_border || "#FFE48B") : "#FFE48B")
    readonly property color portInteractiveRingFillColor: host && host.usesCardinalNeutralFlowHandles
        ? Qt.alpha(root.selectedOutlineColor, 0.1)
        : ((host && host.nodePalette) ? (host.nodePalette.port_interactive_ring_fill || "#44FFC857") : "#44FFC857")
    readonly property color portInteractiveRingBorderColor: host && host.usesCardinalNeutralFlowHandles
        ? Qt.alpha(root.selectedOutlineColor, 0.38)
        : ((host && host.nodePalette) ? (host.nodePalette.port_interactive_ring_border || "#66FFE29A") : "#66FFE29A")
    readonly property color flowchartConnectedPortFillColor: Qt.alpha(root.outlineColor, 0.18)

    readonly property real flowchartRestPortDiameter: 6.0
    readonly property real flowchartConnectedPortDiameter: 7.0
    readonly property real flowchartSelectedPortDiameter: 8.0
    readonly property real flowchartInteractivePortDiameter: 11.0
    readonly property real flowchartInteractiveRingDiameter: 15.0
    readonly property real passiveBorderWidth: host ? host._styleNumber(root.passiveStyle.border_width, 1.0, false) : 1.0
    readonly property real passiveCornerRadius: host ? host._styleNumber(root.passiveStyle.corner_radius, 6.0, true) : 6.0
    readonly property real passiveFontPixelSize: host ? host._styleNumber(root.passiveStyle.font_size, 12.0, false) : 12.0
    readonly property int passiveFontWeight: host
        ? (host._styleString(root.passiveStyle.font_weight).toLowerCase() === "bold"
            ? Font.Bold
            : Font.Normal)
        : Font.Normal
    readonly property bool passiveFontBold: root.passiveFontWeight >= Font.Bold
    readonly property real resolvedBorderWidth: host && host.isPassiveNode
        ? (host.isSelected ? Math.max(3.0, root.passiveBorderWidth + 1.0) : root.passiveBorderWidth)
        : 2.0
    readonly property real resolvedCornerRadius: host && host.isCompactPillSurface
        ? Math.max(0.0, Number(host.height) * 0.5)
        : (host && host.isPanelSurface
            ? 16.0
            : (host && host.isPassiveNode ? root.passiveCornerRadius : 9.0))

    function _hasStyleKey(style, key) {
        if (style === undefined || style === null)
            return false;
        return Object.prototype.hasOwnProperty.call(style, key);
    }

    function _activeStateColors(state, dark) {
        var key = String(state || "default");
        if (dark) {
            if (key === "warning")
                return {"start": "#5A4A28", "end": "#4E4024", "outline": "#D9A93C", "title": "#F8F4E8", "ports": "#E6D6B1"};
            if (key === "error")
                return {"start": "#5D2F30", "end": "#51292A", "outline": "#E36155", "title": "#FBEAE8", "ports": "#E7C2BE"};
            if (key === "disabled")
                return {"start": "#404244", "end": "#393B3D", "outline": "#5D6164", "title": "#B3B7BC", "ports": "#9EA3A8"};
            if (key === "selected")
                return {"start": "#1F5369", "end": "#1A485B", "outline": "#00A5E4", "title": "#F2F7FA", "ports": "#C9E8F3"};
            return {"start": "#403C2D", "end": "#3A372A", "outline": "#81795C", "title": "#F3F3F1", "ports": "#D7D5CE"};
        }
        if (key === "warning")
            return {"start": "#FADB8E", "end": "#FCDD90", "outline": "#F0B72D", "title": "#17174B", "ports": "#43436D"};
        if (key === "error")
            return {"start": "#FAA59A", "end": "#FCA79C", "outline": "#E15949", "title": "#17174B", "ports": "#43436D"};
        if (key === "disabled")
            return {"start": "#CDD0D1", "end": "#CFD2D3", "outline": "#BDC3C7", "title": "#9697A8", "ports": "#A2A4B2"};
        if (key === "selected")
            return {"start": "#ACDCF0", "end": "#ADDDF1", "outline": "#009EE0", "title": "#17174B", "ports": "#43436D"};
        return {"start": "#F6F8F8", "end": "#F9FBFC", "outline": "#6B7277", "title": "#17174B", "ports": "#43436D"};
    }

    function _styleBool(value, fallback) {
        if (value === undefined || value === null)
            return Boolean(fallback);
        if (typeof value === "boolean")
            return value;
        if (typeof value === "string") {
            var normalized = value.trim().toLowerCase();
            if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on")
                return true;
            if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off")
                return false;
        }
        if (typeof value === "number" && (value === 0 || value === 1))
            return Boolean(value);
        return Boolean(fallback);
    }

    function _gradientDirection(value) {
        var normalized = String(value || "").trim().toLowerCase();
        if (normalized === "north" || normalized === "east" || normalized === "south"
            || normalized === "west" || normalized === "radial") {
            return normalized;
        }
        return "south";
    }
}
