import QtQuick 2.15

Item {
    id: surface
    objectName: "graphNodePlotSurface"
    property Item host: null
    readonly property var plotHostServiceRef: typeof plotHostService !== "undefined"
        ? plotHostService
        : null
    readonly property var plotPayload: host && host.nodeData && host.nodeData.plot_surface
        ? host.nodeData.plot_surface
        : ({})
    readonly property string plotNodeId: host && host.nodeData
        ? String(host.nodeData.node_id || "")
        : ""
    readonly property string plotType: String(plotPayload.plot_type || (host && host.nodeData ? host.nodeData.surface_variant || "" : ""))
    readonly property string plotLiveBackendId: String(plotPayload.live_backend_id || "")
    readonly property bool liveSurfaceSizeGateRequired: plotLiveBackendId === "pyqtgraph"
    readonly property bool embeddedSuppressed: Boolean(plotPayload.embedded_rendering_suppressed)
    readonly property bool hostSurfaceActive: host
        ? Boolean(host.hoverActive || host.isSelected)
        : false
    readonly property bool viewportHoverActive: plotViewportHover.hovered
    readonly property int plotRenderRevision: Number(plotPayload.render_revision || 0)
    readonly property bool autoPreviewPulseEligible: Boolean(plotPayload.auto_preview_active)
        && surface.plotRenderRevision > 0
        && surface.plotRenderRevision !== surface._lastAutoPreviewRevision
    readonly property bool transientInteractionPreviewActive: host
        ? Boolean(host.viewportInteractionCacheActive || host.hostDragActive)
        : false
    readonly property bool contentFullscreenOpen: typeof contentFullscreenBridge !== "undefined"
        && contentFullscreenBridge
        ? Boolean(contentFullscreenBridge.open)
        : false
    readonly property bool liveSurfaceSizeViable: !surface.liveSurfaceSizeGateRequired || _liveSurfaceSizeViable()
    readonly property bool serviceAvailable: surface.plotHostServiceRef !== null
        && surface.plotHostServiceRef.set_embedded_interaction_active !== undefined
    readonly property bool liveSurfaceActive: surface.serviceAvailable
        && surface.visible
        && surface.plotNodeId.length > 0
        && surface.plotLiveBackendId.length > 0
        && !surface.embeddedSuppressed
        && !surface.contentFullscreenOpen
        && !surface.transientInteractionPreviewActive
        && surface.liveSurfaceSizeViable
        && (surface.hostSurfaceActive || surface.viewportHoverActive || autoPreviewPulse.running)
    readonly property int hostOverlayRevision: surface.plotHostServiceRef !== null
        && surface.plotHostServiceRef.plot_overlay_revision !== undefined
        ? Number(surface.plotHostServiceRef.plot_overlay_revision)
        : (surface.plotHostServiceRef !== null && surface.plotHostServiceRef.active_overlay_count !== undefined
            ? Number(surface.plotHostServiceRef.active_overlay_count)
            : 0)
    readonly property bool liveOverlayReady: surface.liveSurfaceActive
        && surface._embeddedLiveOverlayReady()
    readonly property bool proxySurfaceActive: !surface.liveOverlayReady
    readonly property int previewCacheRevision: surface.plotHostServiceRef !== null
        && surface.plotHostServiceRef.preview_cache_revision !== undefined
        ? Number(surface.plotHostServiceRef.preview_cache_revision)
        : 0
    readonly property string cachedPreviewSource: _cachedPreviewSource()
    readonly property bool cachedPreviewVisible: !surface.contentFullscreenOpen
        && !surface.liveOverlayReady
        && surface.cachedPreviewSource.length > 0
    readonly property bool placeholderPreviewVisible: !surface.contentFullscreenOpen
        && !surface.liveOverlayReady
        && !surface.cachedPreviewVisible
    readonly property bool blocksHostInteraction: false
    readonly property rect surfaceBodyRect: _resolvedBodyRect()
    readonly property rect liveSurfaceRect: _resolvedLiveRect()
    readonly property var embeddedInteractiveRects: surface.liveSurfaceActive
        ? [surface.liveSurfaceRect]
        : []
    readonly property var surfaceActions: {
        var actions = [];
        var nodeIdLength = surface.plotNodeId ? String(surface.plotNodeId).length : 0;
        var fullscreenAvailable = host ? Boolean(host.surfaceFullscreenAvailable) : false;
        var fullscreenAction = host && host.surfaceFullscreenAction
            ? host.surfaceFullscreenAction(fullscreenAvailable && nodeIdLength > 0, false)
            : null;
        if (fullscreenAction)
            actions.push(fullscreenAction);
        actions.push({
            "id": "plot_detach",
            "label": "Detach",
            "icon": "browser-detach",
            "kind": "plot",
            "enabled": surface.serviceAvailable && nodeIdLength > 0,
            "primary": false
        });
        return actions;
    }
    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0
    property string _activeInteractionNodeId: ""
    property string _cachedPreviewImageSource: ""
    property int _cachedPreviewImageSerial: 0
    property int _lastAutoPreviewRevision: 0

    onLiveSurfaceActiveChanged: _syncEmbeddedInteraction()
    onPlotRenderRevisionChanged: _triggerAutoPreviewPulse()
    onAutoPreviewPulseEligibleChanged: _triggerAutoPreviewPulse()
    onPlotNodeIdChanged: {
        _clearCachedPreviewImage();
        _syncEmbeddedInteraction();
        _queueCachedPreviewImageRefresh();
    }
    onCachedPreviewSourceChanged: _queueCachedPreviewImageRefresh()
    onCachedPreviewVisibleChanged: _queueCachedPreviewImageRefresh()
    onContentFullscreenOpenChanged: {
        if (surface.contentFullscreenOpen)
            _clearCachedPreviewImage();
        _syncEmbeddedInteraction();
        _queueCachedPreviewImageRefresh();
    }
    Component.onCompleted: {
        _triggerAutoPreviewPulse();
        _syncEmbeddedInteraction();
        _queueCachedPreviewImageRefresh();
    }
    Component.onDestruction: {
        if (surface.plotHostServiceRef && surface.plotHostServiceRef.set_embedded_interaction_active) {
            var nodeId = surface._activeInteractionNodeId.length > 0
                ? surface._activeInteractionNodeId
                : surface.plotNodeId;
            if (nodeId.length > 0)
                surface.plotHostServiceRef.set_embedded_interaction_active(nodeId, false);
        }
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "fullscreen")
            return Boolean(surface.requestContentFullscreen());
        if (normalized === "plot_detach")
            return Boolean(surface.requestDetachedWindow());
        return false;
    }

    function triggerHoverAction() {
        surface._syncEmbeddedInteraction();
    }

    function requestContentFullscreen() {
        if (!host || !host.requestSurfaceContentFullscreen || !surface.plotNodeId.length)
            return false;
        return Boolean(host.requestSurfaceContentFullscreen());
    }

    function requestDetachedWindow() {
        if (!surface.plotHostServiceRef || !surface.plotHostServiceRef.open_detached_plot || !surface.plotNodeId.length)
            return false;
        return Boolean(surface.plotHostServiceRef.open_detached_plot(surface.plotNodeId));
    }

    function _syncEmbeddedInteraction() {
        if (!surface.plotHostServiceRef || !surface.plotHostServiceRef.set_embedded_interaction_active)
            return;
        var currentNodeId = surface.plotNodeId;
        if (surface._activeInteractionNodeId.length > 0 && surface._activeInteractionNodeId !== currentNodeId) {
            surface.plotHostServiceRef.set_embedded_interaction_active(surface._activeInteractionNodeId, false);
            surface._activeInteractionNodeId = "";
        }
        if (!currentNodeId.length)
            return;
        surface.plotHostServiceRef.set_embedded_interaction_active(currentNodeId, surface.liveSurfaceActive);
        surface._activeInteractionNodeId = surface.liveSurfaceActive ? currentNodeId : "";
    }

    function _triggerAutoPreviewPulse() {
        if (!surface.autoPreviewPulseEligible)
            return;
        surface._lastAutoPreviewRevision = surface.plotRenderRevision;
        autoPreviewPulse.restart();
        surface._syncEmbeddedInteraction();
    }

    function _cachedPreviewSource() {
        var revision = surface.previewCacheRevision;
        if (revision < 0)
            return "";
        if (!surface.plotHostServiceRef || !surface.plotHostServiceRef.cached_preview_source)
            return "";
        if (!surface.plotNodeId.length)
            return "";
        return String(surface.plotHostServiceRef.cached_preview_source(surface.plotNodeId) || "");
    }

    function _embeddedLiveOverlayReady() {
        var revision = surface.hostOverlayRevision;
        if (revision < 0)
            return false;
        if (!surface.plotHostServiceRef || !surface.plotHostServiceRef.embedded_live_overlay_ready)
            return false;
        if (!surface.plotNodeId.length)
            return false;
        return Boolean(surface.plotHostServiceRef.embedded_live_overlay_ready(surface.plotNodeId));
    }

    function _clearCachedPreviewImage() {
        surface._cachedPreviewImageSerial += 1;
        surface._cachedPreviewImageSource = "";
    }

    Timer {
        id: autoPreviewPulse
        interval: 900
        repeat: false
        onRunningChanged: surface._syncEmbeddedInteraction()
    }

    function _queueCachedPreviewImageRefresh() {
        surface._cachedPreviewImageSerial += 1;
        var serial = surface._cachedPreviewImageSerial;
        var nextSource = surface.cachedPreviewVisible ? surface.cachedPreviewSource : "";
        surface._cachedPreviewImageSource = "";
        if (!nextSource.length)
            return;
        Qt.callLater(function() {
            if (surface._cachedPreviewImageSerial !== serial)
                return;
            if (!surface.cachedPreviewVisible || surface.cachedPreviewSource !== nextSource)
                return;
            surface._cachedPreviewImageSource = nextSource;
            surface._notifyCachedPreviewSwapped(nextSource);
        });
    }

    function _notifyCachedPreviewSwapped(source) {
        // Confirms the live-exit handoff frame to the host service so the
        // native overlay is only released after this image has rendered.
        // Runs from a Qt.callLater callback, never inside a binding update.
        if (!surface.plotHostServiceRef
                || !surface.plotHostServiceRef.notify_cached_preview_swapped
                || !surface.plotNodeId.length)
            return;
        surface.plotHostServiceRef.notify_cached_preview_swapped(surface.plotNodeId, String(source || ""));
    }

    function _number(value, fallback) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : fallback;
    }

    function _resolvedBodyRect() {
        if (!host || !host.surfaceMetrics)
            return Qt.rect(0.0, 0.0, surface.width, surface.height);
        var metrics = host.surfaceMetrics;
        var left = Math.max(0.0, _number(metrics.body_left_margin, 0.0));
        var top = Math.max(0.0, _number(metrics.body_top, 0.0));
        var right = Math.max(0.0, _number(metrics.body_right_margin, 0.0));
        var bodyHeight = Math.max(0.0, _number(metrics.body_height, surface.height - top));
        return Qt.rect(
            left,
            top,
            Math.max(0.0, surface.width - left - right),
            bodyHeight
        );
    }

    function _resolvedLiveRect() {
        var fallback = surface.surfaceBodyRect;
        var viewportWidth = _number(plotViewport ? plotViewport.width : NaN, NaN);
        var viewportHeight = _number(plotViewport ? plotViewport.height : NaN, NaN);
        if (!isFinite(viewportWidth) || !isFinite(viewportHeight) || viewportWidth <= 0.0 || viewportHeight <= 0.0)
            return fallback;
        var viewportX = _number(bodyFrame ? bodyFrame.x : fallback.x, fallback.x)
            + _number(plotViewport ? plotViewport.x : 0.0, 0.0);
        var viewportY = _number(bodyFrame ? bodyFrame.y : fallback.y, fallback.y)
            + _number(plotViewport ? plotViewport.y : 0.0, 0.0);
        return Qt.rect(
            Math.max(0.0, viewportX),
            Math.max(0.0, viewportY),
            Math.max(0.0, viewportWidth),
            Math.max(0.0, viewportHeight)
        );
    }

    function _currentViewportZoom() {
        if (!host || !host.currentViewportZoom)
            return 1.0;
        return Math.max(0.000001, _number(host.currentViewportZoom(), 1.0));
    }

    function _liveSurfaceSizeViable() {
        var rect = surface.liveSurfaceRect;
        var zoom = surface._currentViewportZoom();
        return (rect.width * zoom) >= 220.0 && (rect.height * zoom) >= 110.0;
    }

    function _statusText() {
        if (surface.embeddedSuppressed)
            return "Embedded rendering suppressed";
        if (!surface.serviceAvailable)
            return "Live backend unavailable";
        if (!surface.plotLiveBackendId.length)
            return "Live backend unavailable";
        if (!surface.liveSurfaceSizeViable)
            return "Preview";
        return surface.liveSurfaceActive ? "Live" : "Preview";
    }

    Item {
        id: bodyFrame
        objectName: "graphNodeViewerBodyFrame"
        x: surface.surfaceBodyRect.x
        y: surface.surfaceBodyRect.y
        width: surface.surfaceBodyRect.width
        height: surface.surfaceBodyRect.height
        clip: true

        Rectangle {
            anchors.fill: parent
            radius: host ? Math.max(6, Number(host.resolvedCornerRadius || 6) - 1) : 6
            color: host ? Qt.darker(host.inlineInputBackgroundColor, 1.04) : "#1a202b"
            border.width: 1
            border.color: host
                ? Qt.alpha(surface.liveSurfaceActive ? host.selectedOutlineColor : host.outlineColor, 0.72)
                : "#5da9ff"
        }

        Rectangle {
            id: plotViewport
            objectName: "graphNodeViewerViewport"
            anchors.fill: parent
            anchors.margins: 8
            radius: 5
            color: host ? Qt.alpha(host.surfaceColor, 0.12) : "#101724"
            border.width: 1
            border.color: host
                ? Qt.alpha(host.inlineDrivenTextColor, 0.24)
                : "#42506a"
            clip: true

            HoverHandler {
                id: plotViewportHover
            }

            TapHandler {
                objectName: "graphNodePlotViewportTapHandler"
                acceptedButtons: Qt.LeftButton
                onTapped: surface._syncEmbeddedInteraction()
            }

            Image {
                id: cachedPreviewImage
                objectName: "graphNodePlotCachedPreviewImage"
                anchors.fill: parent
                visible: surface.cachedPreviewVisible && String(source).length > 0
                source: surface._cachedPreviewImageSource
                fillMode: Image.Stretch
                smooth: true
                asynchronous: false
                cache: false
            }

            Canvas {
                id: previewCanvas
                anchors.fill: parent
                visible: surface.placeholderPreviewVisible
                opacity: 0.42

                onPaint: {
                    var ctx = getContext("2d");
                    ctx.clearRect(0, 0, width, height);
                    var base = host ? String(host.inlineDrivenTextColor || "#9aa7bc") : "#9aa7bc";
                    var accent = host ? String(host.selectedOutlineColor || "#5da9ff") : "#5da9ff";
                    ctx.globalAlpha = 0.35;
                    ctx.strokeStyle = base;
                    ctx.lineWidth = 1;
                    var stepX = Math.max(24, width / 5);
                    var stepY = Math.max(20, height / 4);
                    for (var gx = stepX; gx < width; gx += stepX) {
                        ctx.beginPath();
                        ctx.moveTo(gx, 0);
                        ctx.lineTo(gx, height);
                        ctx.stroke();
                    }
                    for (var gy = stepY; gy < height; gy += stepY) {
                        ctx.beginPath();
                        ctx.moveTo(0, gy);
                        ctx.lineTo(width, gy);
                        ctx.stroke();
                    }
                    ctx.globalAlpha = 1.0;
                    ctx.strokeStyle = accent;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(10, height * 0.72);
                    ctx.bezierCurveTo(width * 0.22, height * 0.28, width * 0.45, height * 0.82, width * 0.62, height * 0.44);
                    ctx.bezierCurveTo(width * 0.75, height * 0.18, width * 0.86, height * 0.32, width - 10, height * 0.22);
                    ctx.stroke();
                }

                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
            }

            Text {
                id: statusLabel
                objectName: "graphNodePlotStatusText"
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.right: typeBadge.left
                anchors.rightMargin: 8
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 8
                visible: surface.placeholderPreviewVisible
                text: surface._statusText()
                color: host ? host.inlineDrivenTextColor : "#b5c0d4"
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideRight
                renderType: host ? host.nodeTextRenderType : Text.CurveRendering
            }

            Rectangle {
                id: typeBadge
                objectName: "graphNodePlotTypeBadge"
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 6
                visible: surface.placeholderPreviewVisible
                radius: 4
                height: typeLabel.implicitHeight + 6
                width: Math.max(38, typeLabel.implicitWidth + 12)
                color: host ? Qt.alpha(host.selectedOutlineColor, 0.16) : "#233045"
                border.width: 1
                border.color: host ? Qt.alpha(host.selectedOutlineColor, 0.42) : "#5da9ff"

                Text {
                    id: typeLabel
                    anchors.centerIn: parent
                    text: surface.plotType.length > 0 ? surface.plotType : "plot"
                    color: host ? host.headerTextColor : "#eef3ff"
                    font.pixelSize: 9
                    font.bold: true
                    elide: Text.ElideRight
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }
            }
        }
    }
}
