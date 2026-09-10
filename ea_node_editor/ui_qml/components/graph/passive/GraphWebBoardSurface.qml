import QtQuick 2.15
import ".." as GraphShared
import "../surface_controls" as GraphSurfaceControls
import "../surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "../../common/TooltipCopy.js" as TooltipCopy

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeWebBoardSurface"
    readonly property var boardState: _objectValue("excalidraw_state")
    readonly property var previewRef: _objectValue("excalidraw_preview_ref")
    readonly property string boardNodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string boardTitle: _boardTitle()
    readonly property int boardElementCount: _elementCount()
    readonly property int boardFileCount: _objectKeyCount(boardState.files)
    readonly property string previewReferenceLabel: _previewReferenceLabel()
    readonly property var metadataChips: [
        boardElementCount + " elements",
        boardFileCount + " files"
    ]
    readonly property bool webEnginePreviewAllowed: !(typeof graphWebBoardForceFallback !== "undefined"
        && Boolean(graphWebBoardForceFallback))
    readonly property bool webEngineAvailable: previewViewport.webEngineAvailable
    readonly property string previewMode: previewViewport.previewMode
    readonly property string webEngineFallbackReason: previewViewport.webEngineFallbackReason
    readonly property string previewDataUrl: previewViewport.previewDataUrl
    readonly property bool blocksHostInteraction: false
    readonly property var overlayViewportRect: Qt.rect(
        previewViewport.x,
        previewViewport.y,
        previewViewport.width,
        previewViewport.height
    )
    readonly property var overlayContentRect: overlayViewportRect
    readonly property var overlaySourceClipRect: Qt.rect(0, 0, previewViewport.width, previewViewport.height)
    readonly property string overlayPreviewKind: previewViewport.previewMode
    readonly property bool overlayPreviewVisible: previewViewport.visible
    readonly property color panelFillColor: host && host.hasPassiveFillOverride
        ? host.surfaceColor
        : Qt.darker(host ? host.surfaceColor : "#1b1d22", 1.03)
    readonly property color panelBorderColor: host && host.isSelected
        ? host.themeSelectedOutlineColor
        : (host && host.hasPassiveBorderOverride
            ? host.outlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a"))
    readonly property color viewportFillColor: host
        ? Qt.darker(host.inlineInputBackgroundColor, 1.02)
        : "#202228"
    readonly property color captionTextColor: host ? host.inlineInputTextColor : "#f0f2f5"
    readonly property color hintTextColor: host ? host.inlineDrivenTextColor : "#bdc5d3"
    readonly property color accentColor: host ? host.selectedOutlineColor : "#60cdff"
    readonly property real contentLeftMargin: host ? Number(host.surfaceMetrics.body_left_margin || 10) : 10
    readonly property real contentRightMargin: host ? Number(host.surfaceMetrics.body_right_margin || 10) : 10
    readonly property real contentTopMargin: host ? Number(host.surfaceMetrics.body_top || 30) : 30
    readonly property real contentBottomMargin: host ? Number(host.surfaceMetrics.body_bottom_margin || 10) : 10
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists([
        fullscreenButton.embeddedInteractiveRects
    ])
    readonly property bool fullscreenAvailable: host ? Boolean(host.surfaceFullscreenAvailable) : false
    readonly property var surfaceActions: {
        var action = host && host.surfaceFullscreenAction
            ? host.surfaceFullscreenAction(fullscreenAvailable, false)
            : null;
        return action ? [action] : [];
    }

    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    function _rawValue(key, fallback) {
        var value = nodeProperties[String(key || "")];
        return value === undefined || value === null ? fallback : value;
    }

    function _objectValue(key) {
        var value = _rawValue(key, ({}));
        if (value === undefined || value === null)
            return ({});
        if (typeof value === "string") {
            var trimmed = value.trim();
            if (!trimmed.length)
                return ({});
            try {
                var parsed = JSON.parse(trimmed);
                return parsed && typeof parsed === "object" ? parsed : ({});
            } catch (error) {
                return ({});
            }
        }
        return typeof value === "object" ? value : ({});
    }

    function _boardTitle() {
        var previewTitle = String(previewRef.title || previewRef.name || "").trim();
        if (previewTitle.length > 0)
            return previewTitle;
        var stateTitle = "";
        if (boardState.appState && boardState.appState.name !== undefined && boardState.appState.name !== null)
            stateTitle = String(boardState.appState.name || "").trim();
        if (stateTitle.length > 0)
            return stateTitle;
        if (boardState.name !== undefined && boardState.name !== null) {
            stateTitle = String(boardState.name || "").trim();
            if (stateTitle.length > 0)
                return stateTitle;
        }
        return host && host.nodeData ? String(host.nodeData.title || "Excalidraw board") : "Excalidraw board";
    }

    function _elementCount() {
        var elements = boardState.elements;
        if (!elements || elements.length === undefined || elements.length === null)
            return 0;
        var length = Number(elements.length);
        if (!isFinite(length) || length <= 0)
            return 0;
        var count = 0;
        for (var index = 0; index < length; index++) {
            var element = elements[index] || ({});
            if (!Boolean(element.isDeleted))
                count += 1;
        }
        return count;
    }

    function _objectKeyCount(value) {
        if (!value || typeof value !== "object")
            return 0;
        return Object.keys(value).length;
    }

    function _previewReferenceLabel() {
        var status = String(previewRef.status || "").trim();
        if (previewRef.uri || previewRef.artifact_ref || previewRef.preview_ref || previewRef.ref || previewRef.path || previewRef.artifact_id)
            return status.length > 0 ? status : "Preview ref";
        return status.length > 0 ? status : "No exported preview";
    }

    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
    }

    function dispatchSurfaceAction(actionId) {
        if (String(actionId || "") === "fullscreen")
            return _requestContentFullscreen();
        return false;
    }

    function _requestContentFullscreen() {
        if (!fullscreenAvailable || !host || !host.requestSurfaceContentFullscreen)
            return false;
        return Boolean(host.requestSurfaceContentFullscreen());
    }

    Rectangle {
        anchors.fill: parent
        radius: host ? Number(host.resolvedCornerRadius || 6) : 6
        color: surface.panelFillColor
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: surface.panelBorderColor
    }

    GraphWebBoardPreviewViewport {
        id: previewViewport
        anchors.left: parent.left
        anchors.leftMargin: surface.contentLeftMargin
        anchors.right: parent.right
        anchors.rightMargin: surface.contentRightMargin
        anchors.top: parent.top
        anchors.topMargin: surface.contentTopMargin
        anchors.bottom: parent.bottom
        anchors.bottomMargin: surface.contentBottomMargin
        surface: surface
    }

    GraphSurfaceControls.GraphSurfaceButton {
        id: fullscreenButton
        objectName: "graphNodeWebBoardFullscreenButton"
        host: surface.host
        anchors.top: previewViewport.top
        anchors.topMargin: 8
        anchors.right: previewViewport.right
        anchors.rightMargin: 8
        width: 28
        height: 28
        iconOnly: true
        iconName: "fullscreen"
        iconSize: 14
        text: ""
        tooltipText: surface.fullscreenAvailable
            ? TooltipCopy.text(tooltipCopyBridge, "fullscreen.web_board.open_editor")
            : TooltipCopy.text(tooltipCopyBridge, "fullscreen.web_board.editor_unavailable")
        tooltipCategory: surface.fullscreenAvailable
            ? TooltipCopy.category(tooltipCopyBridge, "fullscreen.web_board.open_editor")
            : TooltipCopy.category(tooltipCopyBridge, "fullscreen.web_board.editor_unavailable")
        enabled: surface.fullscreenAvailable
        opacity: enabled ? 1.0 : 0.68
        accentColor: surface.accentColor
        foregroundColor: surface.captionTextColor
        baseFillColor: Qt.alpha(surface.panelFillColor, 0.86)
        baseBorderColor: Qt.alpha(surface.panelBorderColor, 0.82)
        iconSourceResolver: surface._iconSource
        onClicked: surface._requestContentFullscreen()
    }
}
