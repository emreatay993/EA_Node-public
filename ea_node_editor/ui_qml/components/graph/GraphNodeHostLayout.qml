import QtQuick 2.15

QtObject {
    id: root
    property var host: null

    readonly property bool chromeTitleVisible: !!host && (!host.chromeToggleCapableSurface || host.nodeChromeTitleVisible)
    readonly property bool chromeFrameVisible: !!host && (!host.chromeToggleCapableSurface || host.nodeChromeFrameVisible)
    readonly property bool useHostChrome: !!host
        && (host.isCollapsed || (Boolean(host.surfaceMetrics.use_host_chrome) && root.chromeFrameVisible))
    readonly property bool useHostShadow: !!host && host.surfaceMetrics.use_host_shadow !== false
    readonly property real titleTop: !host || !root.chromeTitleVisible ? 0.0 : (host.isCollapsed ? 4.0 : Number(host.surfaceMetrics.title_top))
    readonly property real titleHeight: !host || !root.chromeTitleVisible ? 0.0 : (host.isCollapsed ? 24.0 : Number(host.surfaceMetrics.title_height))
    readonly property real titleLeftMargin: !host || !root.chromeTitleVisible ? 0.0 : (host.isCollapsed ? 10.0 : Number(host.surfaceMetrics.title_left_margin))
    readonly property real titleRightMargin: !host || !root.chromeTitleVisible ? 0.0 : (host.isCollapsed ? 10.0 : Number(host.surfaceMetrics.title_right_margin))
    readonly property bool titleCentered: !!host && !host.isCollapsed && Boolean(host.surfaceMetrics.title_centered)
    readonly property bool portLabelsSuppressedBySurfaceRule: !!host
        && (host.usesCardinalNeutralFlowHandles || host.isCompactPillSurface || host.isPanelSurface)
    readonly property bool standardExpandedNonPassiveNode: !!host
        && !host.isCollapsed
        && host.surfaceFamily === "standard"
        && !host.isPassiveNode
    readonly property real standardLeftLabelMetricWidth: !host ? 0.0 : Math.max(0.0, Number(host.surfaceMetrics.standard_left_label_width))
    readonly property real standardRightLabelMetricWidth: !host ? 0.0 : Math.max(0.0, Number(host.surfaceMetrics.standard_right_label_width))
    readonly property real standardPortGutterMetric: !host ? 0.0 : Math.max(0.0, Number(host.surfaceMetrics.standard_port_gutter))
    readonly property real standardCenterGapMetric: !host ? 0.0 : Math.max(0.0, Number(host.surfaceMetrics.standard_center_gap))
    readonly property real standardPortLabelMinMetricWidth: !host
        ? 0.0
        : Math.max(0.0, Number(host.surfaceMetrics.standard_port_label_min_width))
    readonly property bool standardPortLabelMetricsReady: root.standardLeftLabelMetricWidth > 0.0
        || root.standardRightLabelMetricWidth > 0.0
        || root.standardPortLabelMinMetricWidth > 0.0
    readonly property bool usesStandardPortLabelColumns: !!host
        && root.standardExpandedNonPassiveNode
        && host.showPortLabelsPreference
        && !root.portLabelsSuppressedBySurfaceRule
        && root.standardPortLabelMetricsReady
    readonly property int standardVisibleLabelColumnCount: (root.standardLeftLabelMetricWidth > 0.0 ? 1 : 0)
        + (root.standardRightLabelMetricWidth > 0.0 ? 1 : 0)
    readonly property real standardExtraLabelWidthPerColumn: root.usesStandardPortLabelColumns
        && root.standardVisibleLabelColumnCount > 0
        ? Math.max(0.0, Number(host ? host.width : 0.0) - root.standardPortLabelMinMetricWidth) / root.standardVisibleLabelColumnCount
        : 0.0
    readonly property real standardLeftLabelWidth: root.usesStandardPortLabelColumns && root.standardLeftLabelMetricWidth > 0.0
        ? root.standardLeftLabelMetricWidth + root.standardExtraLabelWidthPerColumn
        : 0.0
    readonly property real standardRightLabelWidth: root.usesStandardPortLabelColumns && root.standardRightLabelMetricWidth > 0.0
        ? root.standardRightLabelMetricWidth + root.standardExtraLabelWidthPerColumn
        : 0.0
    readonly property real standardPortGutter: root.usesStandardPortLabelColumns ? root.standardPortGutterMetric : 0.0
    readonly property real standardCenterGap: root.usesStandardPortLabelColumns ? root.standardCenterGapMetric : 0.0
    readonly property real portLabelGap: {
        if (!host || !root.usesStandardPortLabelColumns)
            return 6.0;
        // Grips anchor on the card edge (dot spans [-radius, +radius]), so
        // labels start at gutter when gap = gutter - radius.
        var portDotRadius = Math.max(0.0, Number(host.surfaceMetrics.port_dot_radius));
        return Math.max(0.0, root.standardPortGutter - portDotRadius);
    }
    readonly property real portLabelMaxWidth: root.usesStandardPortLabelColumns
        ? Math.max(40.0, root.standardLeftLabelWidth, root.standardRightLabelWidth)
        : Math.max(40.0, Number(host ? host.width : 0.0) * 0.46)
    readonly property bool tooltipOnlyPortLabelsActive: root.standardExpandedNonPassiveNode
        && !!host
        && !host.showPortLabelsPreference
        && !root.portLabelsSuppressedBySurfaceRule
    readonly property bool portLabelsVisible: !root.portLabelsSuppressedBySurfaceRule && !root.tooltipOnlyPortLabelsActive
    readonly property bool hasRenderedPorts: !!host
        && ((host.inputPorts && host.inputPorts.length > 0)
            || (host.outputPorts && host.outputPorts.length > 0))
    readonly property bool notchedPortsPreferenceEnabled: !host || !host.prefs
        || host.prefs.notchedPortsEnabled === undefined
        || host.prefs.notchedPortsEnabled === null
        ? true
        : Boolean(host.prefs.notchedPortsEnabled)
    readonly property bool notchedPortsEffective: !!host
        && root.notchedPortsPreferenceEnabled
        && root.useHostChrome
        && root.chromeFrameVisible
        && !host.isCollapsed
        && host.portLayerActive
        && root.hasRenderedPorts
        && !host.isFlowchartSurface
        && !host.usesCardinalNeutralFlowHandles
    readonly property bool surfaceOwnsShadow: !!host && host.isFlowchartSurface && !root.useHostChrome
    readonly property bool backgroundShadowVisible: !!host
        && host.showShadow
        && root.useHostShadow
        && root.chromeFrameVisible
        && !root.surfaceOwnsShadow
    readonly property bool surfaceShadowVisible: !!host
        && host.showShadow
        && root.useHostShadow
        && root.surfaceOwnsShadow
    readonly property bool shadowVisible: root.backgroundShadowVisible || root.surfaceShadowVisible
    readonly property int nodeTextRenderType: Text.CurveRendering
    readonly property bool chromeCacheActive: root.useHostChrome
    readonly property bool shadowCacheActive: !!host && host.showShadow && root.useHostShadow && !root.surfaceOwnsShadow
    readonly property bool surfaceShadowCacheActive: !!host && host.showShadow && root.useHostShadow && root.surfaceOwnsShadow
    readonly property bool chromeShadowCacheActive: root.chromeCacheActive || root.shadowCacheActive
    readonly property string chromeShadowCacheKey: !host ? "" : [
        root.chromeCacheActive ? "chrome-active" : "chrome-inactive",
        root.shadowCacheActive ? "shadow-active" : "shadow-inactive",
        Number(host.width).toFixed(3),
        Number(host.height).toFixed(3),
        Number(host.resolvedCornerRadius).toFixed(3),
        Number(host.resolvedBorderWidth).toFixed(3),
        host.isSelected ? "selected" : "idle",
        String(host.surfaceColor),
        host.bodyGradientActive ? "body-gradient" : "body-flat",
        String(host.bodyGradientStartColor),
        String(host.bodyGradientEndColor),
        String(host.bodyGradientDirection),
        String(host.outlineColor),
        String(host.selectedOutlineColor),
        root.notchedPortsEffective ? "notched-ports" : "flat-ports",
        host.showShadow ? "shadow-enabled" : "shadow-disabled",
        String(Number(host.shadowStrength)),
        String(Number(host.shadowSoftness)),
        String(Number(host.shadowOffset))
    ].join("|")
    readonly property string surfaceShadowCacheKey: !host ? "" : [
        "surface-shadow",
        String(host.surfaceFamily),
        String(host.surfaceVariant),
        Number(host.width).toFixed(3),
        Number(host.height).toFixed(3),
        Number(host.resolvedBorderWidth).toFixed(3),
        host.isSelected ? "selected" : "idle",
        String(host.surfaceColor),
        host.bodyGradientActive ? "body-gradient" : "body-flat",
        String(host.bodyGradientStartColor),
        String(host.bodyGradientEndColor),
        String(host.bodyGradientDirection),
        String(host.outlineColor),
        String(host.selectedOutlineColor),
        host.showShadow ? "shadow-enabled" : "shadow-disabled",
        String(Number(host.shadowStrength)),
        String(Number(host.shadowSoftness)),
        String(Number(host.shadowOffset))
    ].join("|")
}
