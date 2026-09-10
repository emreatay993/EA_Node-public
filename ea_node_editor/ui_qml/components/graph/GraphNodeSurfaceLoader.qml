import QtQuick 2.15

Item {
    id: root
    objectName: "graphNodeSurfaceLoader"
    property Item host: null
    property var nodeData: host ? host.nodeData : null
    property var surfaceSpec: host ? host.surfaceSpec : ({})
    property string surfaceFamily: host ? host.surfaceFamily : "standard"
    property string surfaceVariant: host ? host.surfaceVariant : ""
    readonly property var renderQuality: host ? host.renderQuality : ({
        "supported_quality_tiers": ["full"]
    })
    readonly property string requestedQualityTier: host ? host.requestedQualityTier : "full"
    readonly property string resolvedQualityTier: host ? host.resolvedQualityTier : "full"
    readonly property bool proxySurfaceRequested: host ? Boolean(host.proxySurfaceRequested) : false
    readonly property bool renderActive: host ? Boolean(host.renderActive) : true
    readonly property var graphBrowserStateSink: host && host.graphBrowserStateSink !== undefined
        ? host.graphBrowserStateSink
        : null
    readonly property string surfaceIdentityKey: host && host.surfaceIdentityKey !== undefined
        ? String(host.surfaceIdentityKey || "")
        : [
            nodeData ? String(nodeData.node_id || "") : "",
            surfaceFamily,
            surfaceVariant,
            String(surfaceSpec && surfaceSpec.component_key ? surfaceSpec.component_key : "standard"),
            String(surfaceSpec && surfaceSpec.qml_component ? surfaceSpec.qml_component : "GraphStandardNodeSurface.qml")
        ].join("|")
    // The loaded surface owns its toolbar actions and their live dispatch.
    // Keep it available while the toolbar is open, even when its body is hidden.
    readonly property bool _surfaceLoadEligible: !!root.host && !!root.nodeData
        && (!Boolean(root.nodeData.collapsed) || Boolean(root.host.toolbarActive))
    readonly property bool _surfaceLoadActive: root._surfaceLoadEligible && root.renderActive
    property bool _asynchronousLoadInProgress: false
    readonly property bool hostReadOnly: host ? Boolean(host.graphReadOnly) : false
    readonly property bool surfaceLoaded: !!loader.item
    readonly property var loadedSurfaceItem: loader.item
    readonly property bool proxySurfaceActive: proxySurfaceRequested && loader.item
        ? Boolean(loader.item.proxySurfaceActive)
        : false
    readonly property var viewerSurfaceContract: {
        if (loader.item && loader.item.viewerSurfaceContract !== undefined && loader.item.viewerSurfaceContract !== null)
            return loader.item.viewerSurfaceContract;
        if (root.nodeData && root.nodeData.viewer_surface)
            return root.nodeData.viewer_surface;
        return ({});
    }
    readonly property rect viewerBodyRect: {
        if (root.loadedSurfaceKey !== "viewer")
            return Qt.rect(0.0, 0.0, 0.0, 0.0);
        return _rectValue(root.viewerSurfaceContract.body_rect);
    }
    readonly property rect viewerProxySurfaceRect: {
        if (root.loadedSurfaceKey !== "viewer")
            return Qt.rect(0.0, 0.0, 0.0, 0.0);
        var contract = root.viewerSurfaceContract;
        return _rectValue(contract.proxy_rect !== undefined ? contract.proxy_rect : contract.body_rect);
    }
    readonly property rect viewerLiveSurfaceRect: {
        if (root.loadedSurfaceKey !== "viewer")
            return Qt.rect(0.0, 0.0, 0.0, 0.0);
        var contract = root.viewerSurfaceContract;
        return _rectValue(contract.live_rect !== undefined ? contract.live_rect : contract.body_rect);
    }
    readonly property var viewerBridgeBinding: {
        if (root.loadedSurfaceKey !== "viewer")
            return ({});
        if (loader.item && loader.item.viewerBridgeBinding !== undefined && loader.item.viewerBridgeBinding !== null)
            return loader.item.viewerBridgeBinding;
        var contract = root.viewerSurfaceContract;
        if (contract && contract.bridge_binding !== undefined && contract.bridge_binding !== null)
            return contract.bridge_binding;
        return ({});
    }
    readonly property var viewerInteractiveRects: {
        if (root.loadedSurfaceKey !== "viewer")
            return [];
        if (loader.item && loader.item.viewerInteractiveRects !== undefined && loader.item.viewerInteractiveRects !== null)
            return loader.item.viewerInteractiveRects;
        var contract = root.viewerSurfaceContract;
        if (contract && contract.interactive_rects !== undefined && contract.interactive_rects !== null)
            return contract.interactive_rects;
        return [];
    }
    readonly property var surfaceQualityContext: host ? host.surfaceQualityContext : ({
        "requested_quality_tier": root.requestedQualityTier,
        "resolved_quality_tier": root.resolvedQualityTier,
        "render_quality": root.renderQuality,
        "proxy_surface_requested": root.proxySurfaceRequested
    })
    readonly property var surfaceLayout: surfaceSpec && surfaceSpec.layout && typeof surfaceSpec.layout === "object"
        ? surfaceSpec.layout
        : ({})
    readonly property string contentRegion: String(surfaceLayout.content_region || "host")
    readonly property bool bodyRegionSurface: contentRegion === "body"
        && !(root.host && root.host.lockedPlaceholderActive)
    readonly property rect bodyViewportRect: {
        if (!root.host || !root.host.surfaceMetrics)
            return Qt.rect(0.0, 0.0, root.width, root.height);
        var metrics = root.host.surfaceMetrics;
        var left = Math.max(0.0, Number(metrics.body_left_margin || 0.0));
        var right = Math.max(0.0, Number(metrics.body_right_margin || 0.0));
        var top = Math.max(0.0, Number(metrics.body_top || 0.0));
        var metricBodyHeight = Math.max(0.0, Number(metrics.body_height || 0.0));
        var chromeHeight = Math.max(0.0, Number(metrics.default_height || 0.0) - metricBodyHeight);
        var availableBodyHeight = Math.max(0.0, root.height - chromeHeight);
        var bodyHeight = Math.max(metricBodyHeight, root.minimumBodyHeight, availableBodyHeight);
        var portTop = Number(metrics.port_top);
        if (isFinite(portTop) && portTop > top)
            bodyHeight = Math.min(bodyHeight, Math.max(0.0, portTop - top));
        return Qt.rect(
            left,
            top,
            Math.max(0.0, root.width - left - right),
            bodyHeight
        );
    }
    readonly property var inputCapabilities: _surfaceInputCapabilities(surfaceSpec)
    readonly property string loadedSurfaceKey: String(surfaceSpec && surfaceSpec.component_key ? surfaceSpec.component_key : "standard")
    readonly property url loadedSurfaceSource: _loadedSurfaceSource(surfaceSpec)
    readonly property real minimumBodyWidth: {
        var itemWidth = loader.item && loader.item.minimumBodyWidth !== undefined
            ? Number(loader.item.minimumBodyWidth)
            : NaN;
        if (isFinite(itemWidth) && itemWidth > 0.0)
            return itemWidth;
        var layoutWidth = Number(surfaceLayout.min_body_width);
        return isFinite(layoutWidth) && layoutWidth > 0.0 ? layoutWidth : 0.0;
    }
    readonly property real minimumBodyHeight: {
        var itemHeight = loader.item && loader.item.minimumBodyHeight !== undefined
            ? Number(loader.item.minimumBodyHeight)
            : NaN;
        if (isFinite(itemHeight) && itemHeight > 0.0)
            return itemHeight;
        var layoutHeight = Number(surfaceLayout.min_body_height);
        return isFinite(layoutHeight) && layoutHeight > 0.0 ? layoutHeight : 0.0;
    }
    readonly property real contentHeight: {
        if (!host || !nodeData)
            return 0.0;
        if (loader.item && Number(loader.item.implicitHeight) > 0.0)
            return Number(loader.item.implicitHeight);
        if (host.surfaceMetrics)
            return Number(host.surfaceMetrics.body_height || 0.0);
        return 0.0;
    }
    readonly property bool blocksHostInteraction: hostReadOnly || (root.visible && loader.item ? Boolean(loader.item.blocksHostInteraction) : false)
    readonly property rect lockedPlaceholderActionRect: {
        if (!loader.item || loader.item.lockedPlaceholderActionRect === undefined || loader.item.lockedPlaceholderActionRect === null)
            return Qt.rect(0.0, 0.0, 0.0, 0.0);
        return _rectValue(loader.item.lockedPlaceholderActionRect);
    }
    readonly property var embeddedInteractiveRects: {
        if (hostReadOnly || !root.visible)
            return [];
        if (!loader.item || loader.item.embeddedInteractiveRects === undefined || loader.item.embeddedInteractiveRects === null)
            return [];
        return loader.item.embeddedInteractiveRects;
    }
    readonly property var surfaceActions: {
        if (hostReadOnly)
            return [];
        if (!loader.item || loader.item.surfaceActions === undefined || loader.item.surfaceActions === null)
            return [];
        return loader.item.surfaceActions;
    }
    property string _loadedSurfaceIdentityKey: ""

    onSurfaceIdentityKeyChanged: {
        if (root._loadedSurfaceIdentityKey.length > 0 && root._loadedSurfaceIdentityKey !== root.surfaceIdentityKey)
            root._loadedSurfaceIdentityKey = "";
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        var nonMutatingPanelAction = normalized === "panel_copy"
            || normalized === "panel_copy_tree";
        if (hostReadOnly && !nonMutatingPanelAction)
            return false;
        if (loader.item && loader.item.dispatchSurfaceAction)
            return Boolean(loader.item.dispatchSurfaceAction(normalized));
        return false;
    }

    function _surfaceInputCapabilities(spec) {
        if (spec && spec.input_capabilities && typeof spec.input_capabilities === "object")
            return spec.input_capabilities;
        return ({
            "devices": ["mouse"],
            "events": ["press", "release", "move", "wheel"],
            "hover": true,
            "pressure": false,
            "gestures": [],
            "plugin_gestures": []
        });
    }

    function _loadedSurfaceSource(spec) {
        var component = spec && spec.qml_component ? String(spec.qml_component || "") : "";
        if (!component.length)
            component = "GraphStandardNodeSurface.qml";
        return Qt.resolvedUrl(component);
    }

    function _rectValue(value) {
        var x = value !== undefined && value !== null ? Number(value.x) : NaN;
        var y = value !== undefined && value !== null ? Number(value.y) : NaN;
        var width = value !== undefined && value !== null ? Number(value.width) : NaN;
        var height = value !== undefined && value !== null ? Number(value.height) : NaN;
        if (!isFinite(x))
            x = 0.0;
        if (!isFinite(y))
            y = 0.0;
        if (!isFinite(width))
            width = 0.0;
        if (!isFinite(height))
            height = 0.0;
        return Qt.rect(x, y, Math.max(0.0, width), Math.max(0.0, height));
    }

    function triggerHoverAction() {
        if (loader.item && loader.item.triggerHoverAction)
            loader.item.triggerHoverAction();
    }

    function requestInlineEditAt(localX, localY) {
        if (loader.item && loader.item.requestInlineEditAt)
            return Boolean(loader.item.requestInlineEditAt(localX, localY));
        return false;
    }

    function beginInlineTitleEdit() {
        if (loader.item && loader.item.beginInlineTitleEdit)
            return Boolean(loader.item.beginInlineTitleEdit());
        return false;
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        if (loader.item && loader.item.commitInlineEditFromExternalInteraction)
            return Boolean(loader.item.commitInlineEditFromExternalInteraction(localX, localY));
        return false;
    }

    Loader {
        id: loader
        asynchronous: root._asynchronousLoadInProgress
            || (root.host ? !Boolean(root.host.inVisibleViewport) : false)
        x: root.bodyRegionSurface ? root.bodyViewportRect.x : 0.0
        y: root.bodyRegionSurface ? root.bodyViewportRect.y : 0.0
        width: root.bodyRegionSurface ? root.bodyViewportRect.width : root.width
        height: root.bodyRegionSurface ? root.bodyViewportRect.height : root.height
        active: root._surfaceLoadActive
        source: root.host && root.host.lockedPlaceholderActive ? "" : root.loadedSurfaceSource
        sourceComponent: root.host && root.host.lockedPlaceholderActive ? lockedPlaceholderComponent : null
        onStatusChanged: {
            if (status === Loader.Loading && asynchronous)
                root._asynchronousLoadInProgress = true;
            else if (status !== Loader.Loading)
                root._asynchronousLoadInProgress = false;
        }
        onLoaded: {
            root._loadedSurfaceIdentityKey = root.surfaceIdentityKey;
            if (item) {
                item.host = Qt.binding(function() { return root.host; });
                if (item.graphBrowserStateSink !== undefined)
                    item.graphBrowserStateSink = Qt.binding(function() { return root.graphBrowserStateSink; });
            }
        }
    }

    Component {
        id: lockedPlaceholderComponent

        Item {
            id: lockedPlaceholderSurface
            objectName: "graphNodeLockedPlaceholderSurface"
            anchors.fill: parent
            property Item host: root.host
            readonly property var graphSharedTypography: host ? host.graphSharedTypography : null
            readonly property var metrics: host && host.surfaceMetrics ? host.surfaceMetrics : ({})
            readonly property real bodyLeftMargin: Math.max(0.0, Number(metrics.body_left_margin || 0.0))
            readonly property real bodyRightMargin: Math.max(0.0, Number(metrics.body_right_margin || 0.0))
            readonly property real bodyTop: Math.max(0.0, Number(metrics.body_top || 0.0))
            readonly property real bodyBottomMargin: Math.max(0.0, Number(metrics.body_bottom_margin || 0.0))
            readonly property real bodyInnerPadding: 8.0
            readonly property real loadRowHeight: 14.0
            readonly property real loadRowSpacing: 6.0
            readonly property real ribbonNaturalHeight: 38.0
            readonly property bool loadRowVisible: host ? Boolean(host.lockedPlaceholderManagerAvailable) : false
            readonly property real ribbonHeight: ribbonNaturalHeight
            readonly property real ribbonWidth: Math.max(0.0, width - bodyLeftMargin - bodyRightMargin)
            readonly property real ribbonY: bodyTop + bodyInnerPadding
            readonly property rect lockedPlaceholderActionRect: loadLinkRow.visible
                ? Qt.rect(
                    loadLinkRow.x + loadLink.x,
                    loadLinkRow.y + loadLink.y,
                    loadLink.width,
                    loadLink.height
                )
                : Qt.rect(0.0, 0.0, 0.0, 0.0)
            readonly property bool blocksHostInteraction: true
            readonly property var embeddedInteractiveRects: []
            readonly property var surfaceActions: []

            Rectangle {
                id: ribbon
                objectName: "graphNodeLockedPlaceholderRibbon"
                x: lockedPlaceholderSurface.bodyLeftMargin
                y: lockedPlaceholderSurface.ribbonY
                width: lockedPlaceholderSurface.ribbonWidth
                height: lockedPlaceholderSurface.ribbonHeight
                radius: 4
                color: host ? host.lockedPlaceholderRibbonFillColor : "#1a1c21"
                border.width: 1
                border.color: host ? host.lockedPlaceholderRibbonBorderColor : "#4a4f5a"

                Canvas {
                    id: ribbonDashedBorder
                    objectName: "graphNodeLockedPlaceholderRibbonDashedBorder"
                    anchors.fill: parent
                    antialiasing: false

                    property color dashColor: host
                        ? host.lockedPlaceholderRibbonBorderColor
                        : "#4a4f5a"

                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.clearRect(0, 0, width, height);
                        if (width <= 2 || height <= 2)
                            return;
                        ctx.strokeStyle = String(dashColor);
                        ctx.lineWidth = 1;
                        ctx.setLineDash([3, 3]);
                        ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
                    }

                    Component.onCompleted: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onDashColorChanged: requestPaint()
                }

                Image {
                    id: ribbonPlugIcon
                    objectName: "graphNodeLockedPlaceholderPlugIcon"
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    readonly property int iconPixelSize: lockedPlaceholderSurface.graphSharedTypography
                        ? lockedPlaceholderSurface.graphSharedTypography.badgeIconPixelSize
                        : 11
                    width: iconPixelSize
                    height: iconPixelSize
                    sourceSize.width: iconPixelSize
                    sourceSize.height: iconPixelSize
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    source: (typeof uiIcons !== "undefined" && uiIcons && uiIcons.has && uiIcons.has("plug"))
                        ? uiIcons.sourceSized("plug", iconPixelSize, String(host ? host.lockedPlaceholderLabelColor : "#8a93a3"))
                        : ""
                }

                Column {
                    anchors.left: ribbonPlugIcon.right
                    anchors.leftMargin: 8
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        id: lockedLabel
                        objectName: "graphNodeLockedPlaceholderLabel"
                        width: parent.width
                        text: host ? host.lockedPlaceholderLabel : "Requires add-on"
                        color: host ? host.lockedPlaceholderLabelColor : "#8a93a3"
                        font.pixelSize: lockedPlaceholderSurface.graphSharedTypography
                            ? lockedPlaceholderSurface.graphSharedTypography.badgePixelSize
                            : 9
                        font.weight: lockedPlaceholderSurface.graphSharedTypography
                            ? lockedPlaceholderSurface.graphSharedTypography.badgeFontWeight
                            : Font.Bold
                        font.letterSpacing: 0.3
                        font.capitalization: Font.AllUppercase
                        elide: Text.ElideRight
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }

                    Text {
                        id: packageLabel
                        objectName: "graphNodeLockedPlaceholderPackage"
                        width: parent.width
                        text: host ? host.lockedPlaceholderPackageText : ""
                        color: host ? host.lockedPlaceholderPackageTextColor : "#d0d5de"
                        font.family: "Cascadia Mono, Cascadia Code, Consolas, monospace"
                        font.pixelSize: lockedPlaceholderSurface.graphSharedTypography
                            ? lockedPlaceholderSurface.graphSharedTypography.inlinePropertyPixelSize
                            : 10
                        elide: Text.ElideRight
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }
                }
            }

            Item {
                id: loadLinkRow
                objectName: "graphNodeLockedPlaceholderButton"
                visible: lockedPlaceholderSurface.loadRowVisible
                x: lockedPlaceholderSurface.bodyLeftMargin
                y: ribbon.y + ribbon.height + lockedPlaceholderSurface.loadRowSpacing
                width: lockedPlaceholderSurface.ribbonWidth
                height: lockedPlaceholderSurface.loadRowHeight

                Text {
                    id: loadLink
                    objectName: "graphNodeLockedPlaceholderButtonText"
                    anchors.right: parent.right
                    anchors.rightMargin: 2
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Load..."
                    color: host ? host.lockedPlaceholderLinkColor : "#60cdff"
                    font.pixelSize: lockedPlaceholderSurface.graphSharedTypography
                        ? lockedPlaceholderSurface.graphSharedTypography.inlinePropertyPixelSize
                        : 10
                    font.bold: true
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }
            }
        }
    }

}
