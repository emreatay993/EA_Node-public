// Purpose: Render PDF preview and page controls for Media Panel.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15
import ".." as GraphShared

GraphShared.GraphSurfaceBase {
    id: renderer
    objectName: "graphNodeMediaPdfRenderer"
    property var sourceResolution: ({})
    property var pdfPreviewInfo: ({})
    property bool rendererReleased: false
    property bool refreshQueued: false

    readonly property bool blocksHostInteraction: false
    readonly property var embeddedInteractiveRects: []
    readonly property bool aspectRatioLocked: false
    readonly property int requestedPageNumber: Math.max(1, Math.round(propNumber("page_number", 1)))
    readonly property int pageCount: Math.max(0, Number(pdfPreviewInfo.page_count || 0))
    readonly property int resolvedPageNumber: Math.max(
        1,
        Number(pdfPreviewInfo.resolved_page_number || requestedPageNumber)
    )
    readonly property string resolvedSourceUrl: rendererReleased
        ? ""
        : String(sourceResolution.resolved_source_url || "")
    readonly property string previewSourceUrl: rendererReleased
        ? ""
        : String(pdfPreviewInfo.preview_url || sourceResolution.preview_source_url || "")
    readonly property real previewRenderScale: Math.max(1.0, Number(Screen.devicePixelRatio || 1.0))
        * Math.max(1.0, host && host.currentViewportZoom ? Number(host.currentViewportZoom()) : 1.0)
    readonly property string previewState: {
        if (String(sourceResolution.state || "") !== "ready")
            return "error";
        if (!previewSourceUrl.length)
            return "unavailable";
        if (previewImage.status === Image.Error)
            return "error";
        if (previewImage.status === Image.Ready)
            return "ready";
        return "loading";
    }
    readonly property string previewMessage: {
        var message = String(pdfPreviewInfo.message || sourceResolution.message || "");
        if (message.length)
            return message;
        if (previewState === "loading")
            return "Loading PDF...";
        if (previewState === "unavailable")
            return "Open fullscreen to view this PDF.";
        return previewState === "error" ? "PDF preview is unavailable." : "";
    }
    readonly property color panelFillColor: host && host.hasPassiveFillOverride
        ? host.surfaceColor
        : Qt.darker(host ? host.surfaceColor : "#1b1d22", 1.03)
    readonly property color panelBorderColor: host && host.isSelected
        ? host.themeSelectedOutlineColor
        : (host && host.hasPassiveBorderOverride
            ? host.outlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a"))
    readonly property real contentInset: host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14
    readonly property real contentLeftMargin: surfaceShowFrame ? contentInset : 0
    readonly property real contentRightMargin: surfaceShowFrame ? contentInset : 0
    readonly property real contentTopMargin: surfaceShowTitle
        ? (host ? Number(host.surfaceMetrics.body_top || 44) : 44)
        : (surfaceShowFrame ? contentInset : 0)
    readonly property real contentBottomMargin: host ? surfaceBodyBottomMargin : (surfaceShowFrame ? 12 : 0)
    readonly property var surfaceActions: {
        var count = pageCount;
        var page = Math.max(1, Math.min(Math.max(1, count), resolvedPageNumber));
        return [{
            "id": "pdf_page_navigation",
            "label": "Navigate",
            "icon": "navigate",
            "kind": "media",
            "enabled": count > 0,
            "primary": false,
            "popover_layout": "pdf_page",
            "page_value": page,
            "page_min": 1,
            "page_max": Math.max(1, count),
            "page_set_action_prefix": "pdf_page_set:",
            "popoverActions": [
                {
                    "id": "pdf_page_previous",
                    "label": "Previous page",
                    "icon": "navigate-previous",
                    "kind": "media",
                    "enabled": count > 0 && page > 1
                },
                {
                    "id": "pdf_page_next",
                    "label": "Next page",
                    "icon": "navigate-next",
                    "kind": "media",
                    "enabled": count > 0 && page < count
                }
            ]
        }];
    }

    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    onRequestedPageNumberChanged: _queueRefresh()
    onResolvedSourceUrlChanged: _queueRefresh()

    Component.onCompleted: _queueRefresh()
    Component.onDestruction: release()

    function release() {
        rendererReleased = true;
        pdfPreviewInfo = ({});
    }

    function _canvasItem() {
        return host && host.canvasItem ? host.canvasItem : null;
    }

    function _queueRefresh() {
        if (refreshQueued || rendererReleased)
            return;
        refreshQueued = true;
        Qt.callLater(function() {
            renderer.refreshQueued = false;
            renderer._refresh();
        });
    }

    function _refresh() {
        if (rendererReleased || String(sourceResolution.state || "") !== "ready") {
            pdfPreviewInfo = ({});
            return;
        }
        var canvasItem = _canvasItem();
        if (canvasItem && canvasItem.describeNodeSurfacePdfPreview) {
            try {
                var described = canvasItem.describeNodeSurfacePdfPreview(
                    resolvedSourceUrl,
                    requestedPageNumber
                );
                if (described && String(described.state || "") === "ready") {
                    pdfPreviewInfo = described;
                    return;
                }
            } catch (error) {
            }
        }
        pdfPreviewInfo = {
            "state": "ready",
            "message": "",
            "resolved_source_url": resolvedSourceUrl,
            "preview_url": String(sourceResolution.preview_source_url || ""),
            "page_count": 0,
            "requested_page_number": requestedPageNumber,
            "resolved_page_number": requestedPageNumber
        };
    }

    function _setPageNumber(value) {
        if (pageCount <= 0)
            return false;
        var page = Number(value);
        if (!isFinite(page))
            page = 1;
        page = Math.max(1, Math.min(pageCount, Math.floor(page)));
        if (page === resolvedPageNumber)
            return true;
        if (host && host.nodeData)
            host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), "page_number", page);
        return true;
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "pdf_page_previous")
            return _setPageNumber(resolvedPageNumber - 1);
        if (normalized === "pdf_page_next")
            return _setPageNumber(resolvedPageNumber + 1);
        if (normalized.indexOf("pdf_page_set:") === 0)
            return _setPageNumber(Number(normalized.substring("pdf_page_set:".length)));
        return false;
    }

    Rectangle {
        visible: renderer.surfaceShowFrame
        anchors.fill: parent
        radius: host ? Number(host.resolvedCornerRadius || 6) : 6
        color: renderer.panelFillColor
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: renderer.panelBorderColor
    }

    Rectangle {
        objectName: "graphNodeMediaPageBadge"
        z: 5
        visible: renderer.pageCount > 0
        anchors.right: parent.right
        anchors.rightMargin: host ? Number(host.surfaceMetrics.title_right_margin || 10) : 10
        y: host
            ? Number(host.surfaceMetrics.title_top || 0)
                + Math.max(0, (Number(host.surfaceMetrics.title_height || 24) - height) * 0.5)
            : 6
        radius: 10
        color: host ? Qt.alpha(host.scopeBadgeColor, 0.92) : "#2C85BF"
        border.width: 1
        border.color: host ? Qt.alpha(host.scopeBadgeBorderColor, 0.96) : "#7FC7FF"
        height: pageBadgeLabel.implicitHeight + 10
        width: pageBadgeLabel.implicitWidth + 16

        Text {
            id: pageBadgeLabel
            anchors.centerIn: parent
            text: "Page " + renderer.resolvedPageNumber + " / " + renderer.pageCount
            color: host ? host.scopeBadgeTextColor : "#F4F8FC"
            font.pixelSize: 10
            font.bold: true
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: renderer.contentLeftMargin
        anchors.right: parent.right
        anchors.rightMargin: renderer.contentRightMargin
        anchors.top: parent.top
        anchors.topMargin: renderer.contentTopMargin
        anchors.bottom: parent.bottom
        anchors.bottomMargin: renderer.contentBottomMargin
        radius: renderer.surfaceShowFrame ? 8 : 0
        color: host ? Qt.darker(host.inlineInputBackgroundColor, 1.02) : "#202228"
        border.width: renderer.surfaceShowFrame ? 1 : 0
        border.color: Qt.alpha(renderer.panelBorderColor, 0.82)
        clip: true

        Image {
            id: previewImage
            objectName: "graphNodeMediaPdfPreviewImage"
            anchors.fill: parent
            anchors.margins: 1
            asynchronous: true
            cache: true
            mipmap: true
            fillMode: Image.PreserveAspectFit
            source: renderer.previewSourceUrl
            sourceSize.width: Math.max(1, Math.ceil(width * renderer.previewRenderScale))
            sourceSize.height: Math.max(1, Math.ceil(height * renderer.previewRenderScale))
            visible: renderer.previewState === "ready"
            smooth: true
        }

        Text {
            objectName: "graphNodeMediaPreviewHint"
            anchors.centerIn: parent
            width: Math.min(parent.width - 24, 240)
            visible: renderer.previewState !== "ready"
            text: renderer.previewMessage
            color: host ? host.inlineDrivenTextColor : "#bdc5d3"
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }
    }
}
