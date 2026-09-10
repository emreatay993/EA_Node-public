import QtQuick 2.15
import ".." as GraphShared
import QtQuick.Effects
import ".." as GraphComponents
import "../surface_controls" as SurfaceControls
import "../GraphNodeHostHitTesting.js" as GraphNodeHostHitTesting
import "../GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

GraphShared.GraphSurfaceBase {
    id: surface
    property bool editingTitle: false
    objectName: "graphNodeFlowchartSurface"
    property bool editingBody: false
    property bool editingBodyTop: false
    property bool editingBodyRight: false
    readonly property bool isCubeSurface: _variantKey() === "isometric_cube"
    readonly property var embeddedInteractiveRects: _activeInlineEditor() !== null
        ? _activeInlineEditor().embeddedInteractiveRects
        : inlinePropertiesLayer.embeddedInteractiveRects
    readonly property bool shapeShadowVisible: host ? Boolean(host._surfaceShadowVisible) : false
    readonly property bool shapeShadowCacheActive: host ? Boolean(host.surfaceShadowCacheActive) : false
    readonly property string shapeShadowCacheKey: host ? String(host.surfaceShadowCacheKey || "") : ""
    readonly property string bodyValue: _resolvedBodyText()
    readonly property color bodyTextColor: host ? host.headerTextColor : "#173247"
    readonly property real bodyFontSize: host ? Number(host.passiveFontPixelSize || 12) : 12
    readonly property bool bodyFontBold: host ? Boolean(host.passiveFontBold) : false
    readonly property real bodyVerticalInset: host
        ? Math.max(12, Number(host.surfaceMetrics.body_bottom_margin || 16))
        : 16
    readonly property real bodyLeftMargin: host ? Number(host.surfaceMetrics.body_left_margin || 18) : 18
    readonly property real bodyRightMargin: host ? Number(host.surfaceMetrics.body_right_margin || 18) : 18
    readonly property string bodyTextPlacement: GraphNodeSurfaceMetrics.flowchartBodyTextPlacement(_variantKey())
    readonly property real bodyTextBandFraction: 0.28
    readonly property real shapeCanvasHeight: bodyTextPlacement === "below_shape"
        ? Math.max(0, surface.height * (1.0 - bodyTextBandFraction))
        : surface.height
    readonly property real isometricCubeOffset: Math.min(surface.width * 0.24, surface.height * 0.5)
    readonly property real isometricFrontFaceCenterY: (surface.height + surface.isometricCubeOffset) * 0.5
    readonly property real isometricCubeStroke: host ? Math.max(1.0, Number(host.resolvedBorderWidth || 1)) : 1.0
    readonly property real cubeFrontFaceDepth: Math.min(surface.width * 0.2, surface.height * 0.2)
    readonly property real cubeFrontFaceCenterX: (surface.width - surface.cubeFrontFaceDepth) * 0.5
    readonly property real cubeFrontFaceCenterY: (surface.height + surface.cubeFrontFaceDepth) * 0.5
    readonly property real calloutTailHeight: Math.min(
        surface.height * 0.3,
        30.0 + 2.0 * (host ? Math.max(1.0, Number(host.resolvedBorderWidth || 1)) : 1.0)
    )
    readonly property bool bodyFallbackSuppressed: _bodyFallbackSuppressed()
    readonly property bool isTimestampSurface: _variantKey() === "timestamp"
    readonly property string timestampBodyPlaceholder: "%date{ddd mmm dd yyyy HH:MM:ss}%"
    readonly property bool timestampLive: surface.isTimestampSurface && surface._propertyBool("live", false)
    property bool timestampManualEditorOpen: false
    property string timestampSnapshotText: _timestampText()
    property string timestampNowText: _timestampText()
    readonly property string timestampManualEditorText: _timestampManualEditorText()
    readonly property var surfaceActions: surface.isTimestampSurface
        ? _surfaceActions()
        : (_activeRichTextBlock() !== null ? _activeRichTextBlock().surfaceActions : bodyRichText.surfaceActions)

    function _propertyText(key) {
        var value = nodeProperties[key];
        if (value === undefined || value === null)
            return "";
        return String(value);
    }

    function _propertyBool(key, fallback) {
        var value = nodeProperties[key];
        if (value === undefined || value === null)
            return Boolean(fallback);
        if (typeof value === "boolean")
            return value;
        if (typeof value === "number")
            return value !== 0;
        var normalized = String(value || "").trim().toLowerCase();
        if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on")
            return true;
        if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off")
            return false;
        return Boolean(fallback);
    }

    function _variantKey() {
        return host ? String(host.surfaceVariant || "").trim().toLowerCase() : "";
    }

    function _bodyFallbackSuppressed() {
        var variantKey = surface._variantKey();
        return variantKey === "card"
            || variantKey === "callout"
            || variantKey === "multi_document"
            || variantKey === "tick"
            || variantKey === "timestamp"
            || variantKey === "message"
            || variantKey === "isometric_cube"
            || variantKey === "cube"
            || variantKey === "actor"
            || variantKey === "star"
            || variantKey === "x";
    }

    function _formatTimestamp(date) {
        var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        function pad(value) {
            return value < 10 ? "0" + value : String(value);
        }
        return days[date.getDay()] + " "
            + months[date.getMonth()] + " "
            + pad(date.getDate()) + " "
            + date.getFullYear() + " "
            + pad(date.getHours()) + ":"
            + pad(date.getMinutes()) + ":"
            + pad(date.getSeconds());
    }

    function _timestampText() {
        return surface._formatTimestamp(new Date());
    }

    function _isTimestampPlaceholder(value) {
        return String(value || "").trim() === surface.timestampBodyPlaceholder;
    }

    function _timestampManualEditorText() {
        var body = surface._propertyText("body").trim();
        if (!surface.isTimestampSurface)
            return body;
        if (!body.length || surface._isTimestampPlaceholder(body) || surface.timestampLive)
            return surface.timestampNowText.length > 0 ? surface.timestampNowText : surface._timestampText();
        return body;
    }

    function _surfaceActions() {
        if (!surface.isTimestampSurface)
            return [];
        return [
            {
                "id": "timestamp_toggle_live",
                "label": surface.timestampLive ? "Freeze live timestamp" : "Live timestamp",
                "icon": "keep-live",
                "kind": "timestamp",
                "enabled": true,
                "primary": surface.timestampLive,
                "checked": surface.timestampLive
            },
            {
                "id": "timestamp_update_now",
                "label": "Update to current time",
                "icon": "clock-update",
                "kind": "timestamp",
                "enabled": !surface.timestampLive,
                "primary": false
            },
            {
                "id": "timestamp_edit_manual",
                "label": "Set timestamp manually",
                "icon": "calendar",
                "kind": "timestamp",
                "enabled": true,
                "primary": false
            }
        ];
    }

    function _resolvedBodyText() {
        var body = surface._propertyText("body");
        if (surface.isTimestampSurface) {
            if (surface.timestampLive)
                return surface.timestampNowText;
            if (surface._isTimestampPlaceholder(body))
                return surface.timestampSnapshotText;
        }
        if (body.trim().length > 0)
            return body;
        if (surface.bodyFallbackSuppressed)
            return "";
        var title = host && host.nodeData ? String(host.nodeData.title || "") : "";
        if (title.trim().length > 0)
            return title;
        return host && host.nodeData ? String(host.nodeData.display_name || "") : "";
    }

    function _titleValue() {
        if (!host || !host.nodeData)
            return "";
        var title = String(host.nodeData.title || "");
        if (title.trim().length > 0)
            return title;
        return String(host.nodeData.display_name || "");
    }

    function _commitProperty(key, value) {
        if (host && host.nodeData)
            host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), String(key || ""), value);
    }

    function _beginInteraction() {
        if (host && host.nodeData)
            host.surfaceControlInteractionStarted(String(host.nodeData.node_id || ""));
    }

    function _activeInlineEditor() {
        if (surface.editingTitle && titleEditor.visible)
            return titleEditor;
        if (!surface.isTimestampSurface && bodyRichText.editorVisible)
            return bodyRichText;
        if (surface.isCubeSurface && bodyTopRichText.editorVisible)
            return bodyTopRichText;
        if (surface.isCubeSurface && bodyRightRichText.editorVisible)
            return bodyRightRichText;
        if (surface.editingBody && bodyEditor.visible)
            return bodyEditor;
        return null;
    }

    function _commitActiveBodyEditor() {
        if (surface.isCubeSurface && bodyTopRichText.editorVisible)
            bodyTopRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (surface.isCubeSurface && bodyRightRichText.editorVisible)
            bodyRightRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (!surface.isTimestampSurface && bodyRichText.editorVisible)
            bodyRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (surface.editingBody && bodyEditor.visible)
            surface._commitBody(bodyEditor.draftText);
    }

    function _beginTitleEdit() {
        if (surface.editingTitle)
            return true;
        if (!host || !host.nodeData)
            return false;
        surface._commitActiveBodyEditor();
        surface.editingTitle = true;
        surface._beginInteraction();
        return true;
    }

    function _commitTitle(value) {
        var nextValue = String(value === undefined || value === null ? "" : value).trim();
        var current = surface._titleValue().trim();
        surface.editingTitle = false;
        if (!nextValue.length || nextValue === current) {
            titleEditor.text = surface._titleValue();
            return;
        }
        titleEditor.text = nextValue;
        surface._commitProperty("title", nextValue);
    }

    function _cancelTitleEdit() {
        titleEditor.text = surface._titleValue();
        surface.editingTitle = false;
    }

    function _activeRichTextBlock() {
        if (surface.isCubeSurface && bodyTopRichText.editorVisible)
            return bodyTopRichText;
        if (surface.isCubeSurface && bodyRightRichText.editorVisible)
            return bodyRightRichText;
        if (!surface.isTimestampSurface)
            return bodyRichText;
        return null;
    }

    function _commitActiveCubeFace() {
        if (surface.isCubeSurface && bodyTopRichText.editorVisible)
            bodyTopRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (surface.isCubeSurface && bodyRightRichText.editorVisible)
            bodyRightRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
    }

    function _beginBodyEdit() {
        if (surface.editingBody)
            return true;
        if (!host || !host.nodeData)
            return false;
        surface._commitActiveCubeFace();
        if (!surface.isTimestampSurface)
            return bodyRichText.requestInlineEditAt(bodyRichText.width * 0.5, bodyRichText.height * 0.5);
        surface.editingBody = true;
        surface._beginInteraction();
        Qt.callLater(function() {
            bodyEditor.syncDraftToCommitted();
            bodyEditor.activateEditor();
        });
        return true;
    }

    function _commitBody(value) {
        var nextValue = String(value === undefined || value === null ? "" : value);
        if (nextValue === surface._propertyText("body")) {
            surface.editingBody = false;
            return;
        }
        surface._commitProperty("body", nextValue);
        surface.editingBody = false;
    }

    function _beginBodyTopEdit() {
        if (surface.editingBodyTop)
            return true;
        if (!host || !host.nodeData)
            return false;
        if (bodyRichText.editorVisible)
            bodyRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (bodyRightRichText.editorVisible)
            bodyRightRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        return bodyTopRichText.requestInlineEditAt(bodyTopRichText.width * 0.5, bodyTopRichText.height * 0.5);
    }

    function _commitBodyTop(value) {
        var nextValue = String(value === undefined || value === null ? "" : value);
        if (nextValue === surface._propertyText("body_top")) {
            surface.editingBodyTop = false;
            return;
        }
        surface._commitProperty("body_top", nextValue);
        surface.editingBodyTop = false;
    }

    function _cancelBodyTopEdit() {
        bodyTopRichText._cancelTextEdit();
        surface.editingBodyTop = false;
    }

    function _beginBodyRightEdit() {
        if (surface.editingBodyRight)
            return true;
        if (!host || !host.nodeData)
            return false;
        if (bodyRichText.editorVisible)
            bodyRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        if (bodyTopRichText.editorVisible)
            bodyTopRichText.commitInlineEditFromExternalInteraction(-9999, -9999);
        return bodyRightRichText.requestInlineEditAt(bodyRightRichText.width * 0.5, bodyRightRichText.height * 0.5);
    }

    function _commitBodyRight(value) {
        var nextValue = String(value === undefined || value === null ? "" : value);
        if (nextValue === surface._propertyText("body_right")) {
            surface.editingBodyRight = false;
            return;
        }
        surface._commitProperty("body_right", nextValue);
        surface.editingBodyRight = false;
    }

    function _cancelBodyRightEdit() {
        bodyRightRichText._cancelTextEdit();
        surface.editingBodyRight = false;
    }

    function _commitLive(value) {
        var nextValue = Boolean(value);
        if (surface.timestampLive === nextValue)
            return;
        surface._commitProperty("live", nextValue);
    }

    function _setTimestampLive(enabled) {
        if (!surface.isTimestampSurface)
            return false;
        if (Boolean(enabled)) {
            surface.timestampNowText = surface._timestampText();
            surface._commitLive(true);
            return true;
        }
        var frozenText = surface._timestampText();
        surface.timestampNowText = frozenText;
        surface.timestampSnapshotText = frozenText;
        surface._commitLive(false);
        surface._commitBody(frozenText);
        return true;
    }

    function _updateTimestampNow() {
        if (!surface.isTimestampSurface || surface.timestampLive)
            return false;
        var nextValue = surface._timestampText();
        surface.timestampSnapshotText = nextValue;
        surface._commitLive(false);
        surface._commitBody(nextValue);
        return true;
    }

    function _openTimestampManualEditor() {
        if (!surface.isTimestampSurface)
            return false;
        surface.timestampManualEditorOpen = true;
        surface._beginInteraction();
        return true;
    }

    function acceptTimestampManualEdit(value) {
        if (!surface.isTimestampSurface)
            return false;
        var nextValue = String(value === undefined || value === null ? "" : value).trim();
        if (!nextValue.length)
            nextValue = surface._timestampText();
        surface.timestampManualEditorOpen = false;
        surface.timestampSnapshotText = nextValue;
        surface._commitLive(false);
        surface._commitBody(nextValue);
        return true;
    }

    function cancelTimestampManualEdit() {
        surface.timestampManualEditorOpen = false;
    }

    function _cancelBodyEdit() {
        bodyEditor.resetDraft();
        surface.editingBody = false;
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "timestamp_toggle_live")
            return surface._setTimestampLive(!surface.timestampLive);
        if (normalized === "timestamp_update_now")
            return surface._updateTimestampNow();
        if (normalized === "timestamp_edit_manual")
            return surface._openTimestampManualEditor();
        var richTextBlock = surface._activeRichTextBlock();
        if (richTextBlock !== null)
            return richTextBlock.dispatchSurfaceAction(actionId);
        return false;
    }

    function requestInlineEditAt(localX, localY) {
        if (surface.editingTitle)
            return GraphNodeHostHitTesting.pointInRect(localX, localY, titleEditor.interactiveRect);
        if (surface.isCubeSurface) {
            if (bodyTopRichText.requestInlineEditAt(localX, localY))
                return true;
            if (bodyRightRichText.requestInlineEditAt(localX, localY))
                return true;
        }
        if (!surface.isTimestampSurface)
            return bodyRichText.requestInlineEditAt(localX, localY);
        if (surface.editingBody)
            return GraphNodeHostHitTesting.pointInRect(localX, localY, bodyEditorInteractionRegion.interactiveRect);
        if (!GraphNodeHostHitTesting.pointInRect(localX, localY, bodyDisplayInteractionRegion.interactiveRect))
            return false;
        return surface._beginBodyEdit();
    }

    function beginInlineTitleEdit() {
        return surface._beginTitleEdit();
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        if (surface.editingTitle) {
            if (GraphNodeHostHitTesting.pointInRect(localX, localY, titleEditor.interactiveRect))
                return false;
            surface._commitTitle(titleEditor.text);
            return true;
        }
        if (surface.isCubeSurface && bodyTopRichText.editorVisible) {
            if (!bodyTopRichText.commitInlineEditFromExternalInteraction(localX, localY))
                return false;
            return true;
        }
        if (surface.isCubeSurface && bodyRightRichText.editorVisible) {
            if (!bodyRightRichText.commitInlineEditFromExternalInteraction(localX, localY))
                return false;
            return true;
        }
        if (!surface.isTimestampSurface)
            return bodyRichText.commitInlineEditFromExternalInteraction(localX, localY);
        if (!surface.editingBody)
            return false;
        if (GraphNodeHostHitTesting.pointInRect(localX, localY, bodyEditorInteractionRegion.interactiveRect))
            return false;
        surface._commitBody(bodyEditor.draftText);
        return true;
    }

    onTimestampLiveChanged: {
        surface.timestampNowText = surface._timestampText();
        if (!surface.timestampLive)
            surface.timestampSnapshotText = surface.timestampNowText;
    }

    onVisibleChanged: {
        if (!visible)
            surface.timestampManualEditorOpen = false;
    }

    Timer {
        id: timestampLiveTimer
        interval: 1000
        repeat: true
        running: surface.timestampLive && surface.visible
        triggeredOnStart: true
        onTriggered: {
            surface.timestampNowText = surface._timestampText();
        }
    }

    // Shape-aware selection glow: a glow-coloured copy of the flowchart silhouette
    // blurred by a MultiEffect, so the selection bloom follows the actual shape
    // (actor, cylinder, callout, …) instead of the card rectangle. Mirrors the shape
    // shadow pattern above. Full-fidelity only; suppressed under any execution state.
    // The rectangular card glow in GraphNodeChromeBackground is gated off for flowchart
    // surfaces (isFlowchartSurface) so the two never both render.
    FlowchartShapeCanvas {
        id: flowchartSelectedGlowSource
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: surface.shapeCanvasHeight
        visible: false
        variant: host ? host.surfaceVariant : ""
        gradientActive: false
        fillColor: host ? host.selectedGlowColor : "transparent"
        strokeColor: host ? host.selectedGlowColor : "transparent"
        strokeWidth: host ? Number(host.resolvedBorderWidth || 1) : 1
    }

    MultiEffect {
        id: flowchartSelectedHalo
        objectName: "graphNodeFlowchartSelectedHalo"
        anchors.fill: flowchartSelectedGlowSource
        source: flowchartSelectedGlowSource
        z: -1
        autoPaddingEnabled: true
        blurEnabled: true
        blur: 1.0
        blurMax: 40
        saturation: 0.35
        visible: opacity > 0.01
        opacity: (host
            && host.isSelected
            && !host.isRunningNode
            && !host.isFailedNode
            && !host.isWarningNode
            && !host.isCompletedNode
            && !host.isFreshRunNode
            && !host.isSelectedRunPreviewNode) ? 0.85 : 0.0
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.InOutCubic } }
    }

    FlowchartShapeCanvas {
        id: flowchartShapeSource
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: surface.shapeCanvasHeight
        visible: !surface.shapeShadowVisible
        variant: host ? host.surfaceVariant : ""
        fillColor: host ? host.surfaceColor : "#1b1d22"
        gradientActive: host ? host.bodyGradientActive : false
        gradientStartColor: host ? host.bodyGradientStartColor : fillColor
        gradientEndColor: host ? host.bodyGradientEndColor : fillColor
        gradientDirection: host ? host.bodyGradientDirection : "south"
        strokeColor: host
            ? (host.isFailedNode
                ? host.failureOutlineColor
                : (host.isRunningNode
                    ? host.runningOutlineColor
                    : (host.isWarningNode
                        ? host.warningOutlineColor
                        : (host.isCompletedNode || host.isFreshRunNode
                            ? host.completedOutlineColor
                            : (host.isSelected ? host.selectedOutlineColor : host.outlineColor)))))
            : "#3a3d45"
        strokeWidth: host ? Number(host.resolvedBorderWidth || 1) : 1
    }

    FlowchartShapeCanvas {
        id: flowchartShadowSource
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: surface.shapeCanvasHeight
        visible: false
        layer.enabled: surface.shapeShadowCacheActive
        variant: host ? host.surfaceVariant : ""
        fillColor: host ? host.surfaceColor : "#1b1d22"
        gradientActive: host ? host.bodyGradientActive : false
        gradientStartColor: host ? host.bodyGradientStartColor : fillColor
        gradientEndColor: host ? host.bodyGradientEndColor : fillColor
        gradientDirection: host ? host.bodyGradientDirection : "south"
        strokeColor: host
            ? (host.isSelected ? host.selectedOutlineColor : host.outlineColor)
            : "#3a3d45"
        strokeWidth: host ? Number(host.resolvedBorderWidth || 1) : 1
    }

    MultiEffect {
        id: flowchartShadow
        objectName: "graphNodeFlowchartShadow"
        property bool cacheActive: surface.shapeShadowCacheActive
        property string cacheKey: surface.shapeShadowCacheKey
        visible: surface.shapeShadowVisible
        anchors.fill: flowchartShadowSource
        source: flowchartShadowSource
        shadowEnabled: true
        shadowColor: "#000000"
        shadowOpacity: host ? Math.max(0.0, Math.min(1.0, Number(host.shadowStrength || 0) / 100.0)) : 0.7
        blurMax: 40
        shadowBlur: host ? Math.max(0.0, Math.min(1.0, Number(host.shadowSoftness || 0) / 100.0)) : 0.5
        shadowHorizontalOffset: 0
        shadowVerticalOffset: host ? Number(host.shadowOffset || 0) : 4
    }

    Item {
        id: bodyBounds
        readonly property real centeredWidth: Math.max(0, parent.width - surface.bodyLeftMargin - surface.bodyRightMargin)
        readonly property real aboveTailHeight: Math.max(
            0,
            parent.height - 2 * surface.bodyVerticalInset - surface.calloutTailHeight
        )
        readonly property real centeredHeight: Math.max(0, parent.height - 2 * surface.bodyVerticalInset)
        readonly property real belowShapeBandTop: parent.height * (1.0 - surface.bodyTextBandFraction)
        readonly property real belowShapeBandHeight: Math.max(
            0,
            parent.height * surface.bodyTextBandFraction - surface.bodyVerticalInset
        )
        readonly property real frontFaceWidth: Math.max(0, parent.width * 0.4)
        readonly property real frontFaceHeight: Math.max(
            16,
            Math.min(
                parent.height * 0.32,
                parent.height - 2 * surface.isometricCubeOffset - 2 * surface.bodyVerticalInset
            )
        )
        readonly property real cubeFrontFaceWidth: Math.max(
            0,
            parent.width - surface.cubeFrontFaceDepth - surface.bodyLeftMargin - surface.bodyRightMargin
        )
        readonly property real cubeFrontFaceHeight: Math.max(
            16,
            Math.min(
                parent.height * 0.5,
                parent.height - surface.cubeFrontFaceDepth - 2 * surface.bodyVerticalInset
            )
        )
        readonly property bool tickBelowShape: surface.bodyTextPlacement === "below_shape"
            && surface._variantKey() === "tick"
        readonly property real tickHorizontalShift: tickBelowShape ? -parent.width * 0.08 : 0.0
        readonly property real tickVerticalShift: tickBelowShape ? parent.height * 0.05 : 0.0

        x: {
            if (surface.bodyTextPlacement === "front_face")
                return parent.width * 0.05 + tickHorizontalShift;
            if (surface.bodyTextPlacement === "cube_front_face")
                return Math.max(surface.bodyLeftMargin, surface.cubeFrontFaceCenterX - cubeFrontFaceWidth * 0.5);
            return surface.bodyLeftMargin + tickHorizontalShift;
        }
        width: {
            if (surface.bodyTextPlacement === "front_face")
                return frontFaceWidth;
            if (surface.bodyTextPlacement === "cube_front_face")
                return cubeFrontFaceWidth;
            return centeredWidth;
        }
        y: {
            var base;
            if (surface.bodyTextPlacement === "below_shape")
                base = belowShapeBandTop;
            else if (surface.bodyTextPlacement === "front_face")
                base = Math.max(0, surface.isometricFrontFaceCenterY - frontFaceHeight * 0.5);
            else if (surface.bodyTextPlacement === "cube_front_face")
                base = Math.max(surface.bodyVerticalInset, surface.cubeFrontFaceCenterY - cubeFrontFaceHeight * 0.5);
            else
                base = surface.bodyVerticalInset;
            return base + tickVerticalShift;
        }
        height: {
            if (surface.bodyTextPlacement === "below_shape")
                return belowShapeBandHeight;
            if (surface.bodyTextPlacement === "front_face")
                return frontFaceHeight;
            if (surface.bodyTextPlacement === "cube_front_face")
                return cubeFrontFaceHeight;
            if (surface.bodyTextPlacement === "above_tail")
                return aboveTailHeight;
            return centeredHeight;
        }
        clip: true

        Text {
            id: flowchartBodyText
            objectName: surface.isTimestampSurface ? "graphNodeFlowchartBodyText" : ""
            property int effectiveRenderType: renderType
            visible: surface.isTimestampSurface && !surface.editingBody && !surface.editingTitle
            anchors.fill: parent
            text: surface.bodyValue
            color: surface.bodyTextColor
            font.pixelSize: surface.bodyFontSize
            font.bold: surface.bodyFontBold
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }

        GraphRichTextBlock {
            id: bodyRichText
            objectName: "graphNodeFlowchartRichTextBlock"
            visible: !surface.isTimestampSurface && !surface.editingTitle
            anchors.fill: parent
            host: surface.host
            contentPropertyKey: "body"
            formatPropertyKey: "body_format"
            stylePropertyPrefix: "body_"
            defaultText: surface.bodyValue
            useDefaultTextWhenBlank: true
            defaultFormat: "plain"
            placeholderValue: "Body"
            defaultFontSize: surface.bodyFontSize
            defaultFontBold: surface.bodyFontBold
            defaultTextColor: surface.bodyTextColor
            defaultHorizontalAlignment: "center"
            defaultVerticalAlignment: "middle"
            defaultLineHeight: 1.0
            defaultPadding: 0
            renderedTextObjectName: "graphNodeFlowchartBodyText"
            editorWrapperObjectName: "graphNodeFlowchartBodyEditor"
            editorObjectName: "graphNodeFlowchartBodyEditorField"
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyDisplayInteractionRegion
            host: surface.host
            targetItem: surface.isTimestampSurface ? flowchartBodyText : bodyRichText
            enabled: surface.isTimestampSurface ? flowchartBodyText.visible : bodyRichText.visible
        }

        SurfaceControls.GraphSurfaceInlineTextEditor {
            id: bodyEditor
            objectName: surface.isTimestampSurface ? "graphNodeFlowchartBodyEditor" : ""
            anchors.fill: parent
            visible: surface.isTimestampSurface && surface.editingBody && !surface.editingTitle
            host: surface.host
            committedText: surface._propertyText("body")
            fontPixelSize: surface.bodyFontSize
            fontBold: surface.bodyFontBold
            textColor: surface.bodyTextColor
            fieldObjectName: surface.isTimestampSurface ? "graphNodeFlowchartBodyEditorField" : ""
            horizontalAlignment: TextInput.AlignHCenter
            centerTextVertically: true
            onControlStarted: surface._beginInteraction()
            onCommitRequested: function(value) {
                surface._commitBody(value);
            }
            onCancelRequested: {
                surface._cancelBodyEdit();
            }
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyEditorInteractionRegion
            host: surface.host
            targetItem: bodyEditor
            enabled: bodyEditor.visible
        }

        SurfaceControls.GraphSurfaceTextField {
            id: titleEditor
            objectName: "graphNodeFlowchartTitleEditor"
            anchors.fill: parent
            visible: surface.editingTitle
            host: surface.host
            text: surface._titleValue()
            textColor: surface.bodyTextColor
            fillColor: "transparent"
            borderColor: "transparent"
            focusBorderColor: "transparent"
            leftPadding: 0
            rightPadding: 0
            horizontalAlignment: TextInput.AlignHCenter
            verticalAlignment: TextInput.AlignVCenter
            font.pixelSize: surface.bodyFontSize
            font.weight: surface.bodyFontBold ? Font.Bold : Font.Normal

            onVisibleChanged: {
                if (visible) {
                    text = surface._titleValue();
                    forceActiveFocus();
                    cursorPosition = text.length;
                    deselect();
                }
            }

            onAccepted: {
                surface._commitTitle(text);
            }

            onActiveFocusChanged: {
                if (!activeFocus && surface.editingTitle)
                    surface._commitTitle(text);
            }

            Keys.onEscapePressed: function(event) {
                surface._cancelTitleEdit();
                event.accepted = true;
            }
        }
    }

    Item {
        id: cubeTopFaceBounds
        visible: surface.isCubeSurface
        x: parent.width * 0.30
        width: parent.width * 0.40
        y: Math.max(0, surface.isometricCubeOffset * 0.5)
        height: Math.max(16, surface.isometricCubeOffset)
        clip: true

        Text {
            id: cubeTopFaceText
            objectName: ""
            anchors.fill: parent
            visible: false
            text: surface._propertyText("body_top")
            color: surface.bodyTextColor
            font.pixelSize: surface.bodyFontSize
            font.bold: surface.bodyFontBold
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }

        GraphRichTextBlock {
            id: bodyTopRichText
            objectName: "graphNodeFlowchartBodyTopRichTextBlock"
            anchors.fill: parent
            visible: surface.isCubeSurface
            host: surface.host
            contentPropertyKey: "body_top"
            formatPropertyKey: "body_top_format"
            stylePropertyPrefix: "body_top_"
            defaultText: ""
            defaultFormat: "plain"
            placeholderValue: "Top Face"
            defaultFontSize: surface.bodyFontSize
            defaultFontBold: surface.bodyFontBold
            defaultTextColor: surface.bodyTextColor
            defaultHorizontalAlignment: "center"
            defaultVerticalAlignment: "middle"
            defaultLineHeight: 1.0
            defaultPadding: 0
            renderedTextObjectName: "graphNodeFlowchartBodyTopText"
            editorWrapperObjectName: "graphNodeFlowchartBodyTopEditor"
            editorObjectName: "graphNodeFlowchartBodyTopEditorField"
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyTopDisplayInteractionRegion
            host: surface.host
            targetItem: bodyTopRichText
            enabled: bodyTopRichText.visible && surface.isCubeSurface
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyTopEditorInteractionRegion
            host: surface.host
            targetItem: bodyTopRichText
            enabled: bodyTopRichText.visible && bodyTopRichText.editorVisible
        }
    }

    Item {
        id: cubeRightFaceBounds
        visible: surface.isCubeSurface
        readonly property real rightFaceHeight: Math.max(
            16,
            Math.min(
                parent.height * 0.32,
                parent.height - 2 * surface.isometricCubeOffset - 2 * surface.bodyVerticalInset
            )
        )
        x: parent.width * 0.55
        width: parent.width * 0.40
        y: Math.max(0, surface.isometricFrontFaceCenterY - rightFaceHeight * 0.5)
        height: rightFaceHeight
        clip: true

        Text {
            id: cubeRightFaceText
            objectName: ""
            anchors.fill: parent
            visible: false
            text: surface._propertyText("body_right")
            color: surface.bodyTextColor
            font.pixelSize: surface.bodyFontSize
            font.bold: surface.bodyFontBold
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }

        GraphRichTextBlock {
            id: bodyRightRichText
            objectName: "graphNodeFlowchartBodyRightRichTextBlock"
            anchors.fill: parent
            visible: surface.isCubeSurface
            host: surface.host
            contentPropertyKey: "body_right"
            formatPropertyKey: "body_right_format"
            stylePropertyPrefix: "body_right_"
            defaultText: ""
            defaultFormat: "plain"
            placeholderValue: "Right Face"
            defaultFontSize: surface.bodyFontSize
            defaultFontBold: surface.bodyFontBold
            defaultTextColor: surface.bodyTextColor
            defaultHorizontalAlignment: "center"
            defaultVerticalAlignment: "middle"
            defaultLineHeight: 1.0
            defaultPadding: 0
            renderedTextObjectName: "graphNodeFlowchartBodyRightText"
            editorWrapperObjectName: "graphNodeFlowchartBodyRightEditor"
            editorObjectName: "graphNodeFlowchartBodyRightEditorField"
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyRightDisplayInteractionRegion
            host: surface.host
            targetItem: bodyRightRichText
            enabled: bodyRightRichText.visible && surface.isCubeSurface
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: bodyRightEditorInteractionRegion
            host: surface.host
            targetItem: bodyRightRichText
            enabled: bodyRightRichText.visible && bodyRightRichText.editorVisible
        }
    }

    GraphComponents.GraphInlinePropertiesLayer {
        id: inlinePropertiesLayer
        anchors.fill: parent
        host: surface.host
    }
}
