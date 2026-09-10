import QtQuick 2.15
import QtQml 2.15

Item {
    id: root
    objectName: "graphCanvasFrameScheduler"
    visible: false
    width: 0
    height: 0

    property var backgroundLayer: null
    property var edgeLayer: null
    property int requestedRedrawCount: 0
    property int viewStateRedrawRequestCount: 0
    property int edgeRedrawRequestCount: 0
    property int overlayRedrawRequestCount: 0
    property int flushedFrameCount: 0
    property int coalescedRedrawRequestCount: 0
    property int rawPanInputEventCount: 0
    property int flushedPanUpdateCount: 0
    property int rawZoomInputEventCount: 0
    property int flushedZoomUpdateCount: 0
    property int rawLiveDragInputEventCount: 0
    property int flushedLiveDragUpdateCount: 0
    property int rawLiveNodeGeometryInputEventCount: 0
    property int flushedLiveNodeGeometryUpdateCount: 0
    property int rawWireDragInputEventCount: 0
    property int flushedWireDragUpdateCount: 0
    property int flushedOverlayUpdateCount: 0
    property int flushedGridUpdateCount: 0
    property int frameBudgetMs: 16
    property bool _viewStateRedrawDirty: false
    property bool _edgeRedrawDirty: false
    property bool _overlayRedrawDirty: false
    property bool _flushPending: false
    property bool _panDirty: false
    property real _pendingPanDx: 0.0
    property real _pendingPanDy: 0.0
    property var _pendingPanBridge: null
    property bool _zoomDirty: false
    property real _pendingZoomSteps: 0.0
    property real _pendingZoomCursorX: 0.0
    property real _pendingZoomCursorY: 0.0
    property bool _pendingZoomHasCursor: false
    property var _pendingZoomCanvas: null
    property var _pendingZoomBridge: null
    property bool _liveDragDirty: false
    property var _pendingLiveDragSceneState: null
    property real _pendingLiveDragDx: 0.0
    property real _pendingLiveDragDy: 0.0
    property bool _liveNodeGeometryDirty: false
    property var _pendingLiveNodeGeometrySceneState: null
    property var _pendingLiveNodeGeometryById: ({})
    property bool _wireDragDirty: false
    property var _pendingWireDragCanvas: null
    property var _pendingWireDragPayload: null

    function _finiteNumber(value, fallbackValue) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : Number(fallbackValue || 0.0);
    }

    function _markViewStateDirty() {
        root._viewStateRedrawDirty = true;
        if (root.backgroundLayer && root.backgroundLayer.markViewStateRedrawDirty)
            root.backgroundLayer.markViewStateRedrawDirty();
        if (root.edgeLayer && root.edgeLayer.markViewStateRedrawDirty)
            root.edgeLayer.markViewStateRedrawDirty();
    }

    function _markEdgeDirty() {
        root._edgeRedrawDirty = true;
        if (root.edgeLayer && root.edgeLayer.markScheduledRedrawDirty)
            root.edgeLayer.markScheduledRedrawDirty();
    }

    function _resetPendingZoom() {
        root._zoomDirty = false;
        root._pendingZoomSteps = 0.0;
        root._pendingZoomCursorX = 0.0;
        root._pendingZoomCursorY = 0.0;
        root._pendingZoomHasCursor = false;
        root._pendingZoomCanvas = null;
        root._pendingZoomBridge = null;
    }

    function _hasDirtyWork() {
        return root._viewStateRedrawDirty
            || root._edgeRedrawDirty
            || root._overlayRedrawDirty
            || root._panDirty
            || root._zoomDirty
            || root._liveDragDirty
            || root._liveNodeGeometryDirty
            || root._wireDragDirty;
    }

    function _settleIdleFlushIfClean() {
        if (root._hasDirtyWork())
            return;
        root._flushPending = false;
        if (frameFlushTimer.running)
            frameFlushTimer.stop();
    }

    function _endProgrammaticViewportInteractionIfClean() {
        if (root._hasDirtyWork())
            return;
        var canvas = root.parent;
        if (canvas && canvas.interactionActive !== undefined && Boolean(canvas.interactionActive))
            canvas.interactionActive = false;
    }

    function _queueFlush() {
        if (root._flushPending) {
            root.coalescedRedrawRequestCount += 1;
        } else {
            root._flushPending = true;
        }
        if (!frameFlushTimer.running)
            frameFlushTimer.start();
    }

    function requestViewStateRedraw() {
        root.requestedRedrawCount += 1;
        root.viewStateRedrawRequestCount += 1;
        root._markViewStateDirty();
        root._queueFlush();
    }

    function requestEdgeRedraw() {
        root.requestedRedrawCount += 1;
        root.edgeRedrawRequestCount += 1;
        root._markEdgeDirty();
        root._queueFlush();
    }

    function requestOverlayRedraw() {
        root.requestedRedrawCount += 1;
        root.overlayRedrawRequestCount += 1;
        root._overlayRedrawDirty = true;
        root._queueFlush();
    }

    function queuePanBy(viewCommandBridge, dx, dy) {
        var deltaX = root._finiteNumber(dx, 0.0);
        var deltaY = root._finiteNumber(dy, 0.0);
        if (Math.abs(deltaX) < 0.0001 && Math.abs(deltaY) < 0.0001)
            return false;
        if (!viewCommandBridge || !viewCommandBridge.pan_by)
            return false;
        root.rawPanInputEventCount += 1;
        viewCommandBridge.pan_by(deltaX, deltaY);
        root._pendingPanBridge = null;
        root._pendingPanDx += deltaX;
        root._pendingPanDy += deltaY;
        root._panDirty = true;
        root._markViewStateDirty();
        root._queueFlush();
        return true;
    }

    function queueWheelZoom(canvasItem, viewCommandBridge, deltaY, cursorX, cursorY) {
        var resolvedDeltaY = root._finiteNumber(deltaY, 0.0);
        if (Math.abs(resolvedDeltaY) < 0.001)
            return false;
        if (!viewCommandBridge)
            return false;
        var steps = resolvedDeltaY / 120.0;
        if (Math.abs(steps) < 0.01)
            steps = resolvedDeltaY > 0 ? 1.0 : -1.0;
        steps = Math.max(-1.0, Math.min(1.0, steps));
        root.rawZoomInputEventCount += 1;
        root._pendingZoomSteps += steps;
        root._pendingZoomCursorX = Number(cursorX);
        root._pendingZoomCursorY = Number(cursorY);
        root._pendingZoomHasCursor = isFinite(root._pendingZoomCursorX) && isFinite(root._pendingZoomCursorY);
        if (
            canvasItem
            && canvasItem.noteViewportInteraction
            && canvasItem.shouldUseViewportInteractionQualityForWheelZoom
            && canvasItem.shouldUseViewportInteractionQualityForWheelZoom()
        ) {
            canvasItem.noteViewportInteraction();
        }
        root._applyWheelZoomNow(
            canvasItem,
            viewCommandBridge,
            steps,
            root._pendingZoomCursorX,
            root._pendingZoomCursorY,
            root._pendingZoomHasCursor
        );
        root._pendingZoomCanvas = null;
        root._pendingZoomBridge = null;
        root._zoomDirty = true;
        root._markViewStateDirty();
        root._queueFlush();
        return true;
    }

    property var _toolbarGraceHost: null
    property var _elapsedHosts: []

    function queueLiveDragOffset(sceneState, dx, dy) {
        if (!sceneState || !sceneState.applyLiveDragOffsetNow)
            return false;
        root.rawLiveDragInputEventCount += 1;
        root._pendingLiveDragSceneState = sceneState;
        root._pendingLiveDragDx = root._finiteNumber(dx, 0.0);
        root._pendingLiveDragDy = root._finiteNumber(dy, 0.0);
        root._liveDragDirty = true;
        root._markEdgeDirty();
        root._queueFlush();
        return true;
    }

    function hasPendingLiveDragOffset(sceneState) {
        return root._liveDragDirty && root._pendingLiveDragSceneState === sceneState;
    }

    function cancelLiveDragOffset(sceneState) {
        if (root._pendingLiveDragSceneState !== sceneState)
            return false;
        root._liveDragDirty = false;
        root._pendingLiveDragSceneState = null;
        root._pendingLiveDragDx = 0.0;
        root._pendingLiveDragDy = 0.0;
        root._settleIdleFlushIfClean();
        return true;
    }

    function queueLiveNodeGeometry(sceneState, nodeId, x, y, width, height, active) {
        var normalized = String(nodeId || "").trim();
        if (!sceneState || !sceneState.applyLiveNodeGeometryNow || normalized.length === 0)
            return false;
        root.rawLiveNodeGeometryInputEventCount += 1;
        var next = {};
        var source = root._pendingLiveNodeGeometryById || {};
        for (var key in source) {
            if (Object.prototype.hasOwnProperty.call(source, key))
                next[key] = source[key];
        }
        next[normalized] = {
            "node_id": normalized,
            "x": root._finiteNumber(x, 0.0),
            "y": root._finiteNumber(y, 0.0),
            "width": Math.max(1.0, root._finiteNumber(width, 1.0)),
            "height": Math.max(1.0, root._finiteNumber(height, 1.0)),
            "active": Boolean(active)
        };
        root._pendingLiveNodeGeometrySceneState = sceneState;
        root._pendingLiveNodeGeometryById = next;
        root._liveNodeGeometryDirty = true;
        root._queueFlush();
        return true;
    }

    function cancelLiveNodeGeometry(sceneState) {
        if (root._pendingLiveNodeGeometrySceneState !== sceneState)
            return false;
        root._liveNodeGeometryDirty = false;
        root._pendingLiveNodeGeometrySceneState = null;
        root._pendingLiveNodeGeometryById = ({});
        root._settleIdleFlushIfClean();
        return true;
    }

    function hasPendingLiveNodeGeometry(sceneState) {
        return root._liveNodeGeometryDirty && root._pendingLiveNodeGeometrySceneState === sceneState;
    }

    function queueWireDragUpdate(canvasItem, nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, dragActive, modifiers) {
        if (!canvasItem || !canvasItem.updatePortWireDrag)
            return false;
        root.rawWireDragInputEventCount += 1;
        root._pendingWireDragCanvas = canvasItem;
        root._pendingWireDragPayload = {
            "node_id": String(nodeId || ""),
            "port_key": String(portKey || ""),
            "direction": String(direction || ""),
            "scene_x": root._finiteNumber(sceneX, 0.0),
            "scene_y": root._finiteNumber(sceneY, 0.0),
            "screen_x": root._finiteNumber(screenX, 0.0),
            "screen_y": root._finiteNumber(screenY, 0.0),
            "drag_active": Boolean(dragActive),
            "modifiers": Number(modifiers || 0)
        };
        root._wireDragDirty = true;
        root._markEdgeDirty();
        root._queueFlush();
        return true;
    }

    function cancelWireDragUpdate(canvasItem) {
        if (root._pendingWireDragCanvas !== canvasItem)
            return false;
        root._wireDragDirty = false;
        root._pendingWireDragCanvas = null;
        root._pendingWireDragPayload = null;
        root._settleIdleFlushIfClean();
        return true;
    }

    function _applyWheelZoomNow(canvas, bridge, steps, cursorX, cursorY, hasCursor) {
        if (!bridge || Math.abs(steps) < 0.001)
            return false;
        var factor = Math.pow(1.15, steps);
        if (hasCursor && bridge.adjust_zoom_at_viewport_point) {
            bridge.adjust_zoom_at_viewport_point(factor, cursorX, cursorY);
            return true;
        }
        var sceneBeforeX = 0.0;
        var sceneBeforeY = 0.0;
        if (hasCursor && canvas && canvas.screenToSceneX && canvas.screenToSceneY) {
            sceneBeforeX = canvas.screenToSceneX(cursorX);
            sceneBeforeY = canvas.screenToSceneY(cursorY);
        }
        if (bridge.adjust_zoom)
            bridge.adjust_zoom(factor);
        if (hasCursor && canvas && canvas.screenToSceneX && canvas.screenToSceneY && bridge.pan_by) {
            var sceneAfterX = canvas.screenToSceneX(cursorX);
            var sceneAfterY = canvas.screenToSceneY(cursorY);
            bridge.pan_by(sceneBeforeX - sceneAfterX, sceneBeforeY - sceneAfterY);
        }
        return true;
    }

    function _flushPendingPan() {
        if (!root._panDirty)
            return false;
        var deltaX = root._pendingPanDx;
        var deltaY = root._pendingPanDy;
        root._panDirty = false;
        root._pendingPanBridge = null;
        root._pendingPanDx = 0.0;
        root._pendingPanDy = 0.0;
        if (Math.abs(deltaX) < 0.0001 && Math.abs(deltaY) < 0.0001)
            return false;
        root.flushedPanUpdateCount += 1;
        return true;
    }

    function _flushPendingZoom() {
        if (!root._zoomDirty)
            return false;
        var steps = root._pendingZoomSteps;
        root._resetPendingZoom();
        if (Math.abs(steps) < 0.001)
            return false;
        root.flushedZoomUpdateCount += 1;
        return true;
    }

    function _flushPendingLiveDragOffset() {
        if (!root._liveDragDirty)
            return false;
        var sceneState = root._pendingLiveDragSceneState;
        var dx = root._pendingLiveDragDx;
        var dy = root._pendingLiveDragDy;
        root._liveDragDirty = false;
        root._pendingLiveDragSceneState = null;
        root._pendingLiveDragDx = 0.0;
        root._pendingLiveDragDy = 0.0;
        if (!sceneState || !sceneState.applyLiveDragOffsetNow)
            return false;
        sceneState.applyLiveDragOffsetNow(dx, dy, false);
        root.flushedLiveDragUpdateCount += 1;
        return true;
    }

    function _flushPendingLiveNodeGeometry() {
        if (!root._liveNodeGeometryDirty)
            return false;
        var sceneState = root._pendingLiveNodeGeometrySceneState;
        var pending = root._pendingLiveNodeGeometryById || {};
        root._liveNodeGeometryDirty = false;
        root._pendingLiveNodeGeometrySceneState = null;
        root._pendingLiveNodeGeometryById = ({});
        if (!sceneState || !sceneState.applyLiveNodeGeometryNow)
            return false;
        var flushedAny = false;
        for (var key in pending) {
            if (!Object.prototype.hasOwnProperty.call(pending, key))
                continue;
            var payload = pending[key] || {};
            if (sceneState.applyLiveNodeGeometryNow(
                payload.node_id,
                payload.x,
                payload.y,
                payload.width,
                payload.height,
                payload.active,
                false
            )) {
                root._markEdgeDirty();
            }
            flushedAny = true;
        }
        if (flushedAny)
            root.flushedLiveNodeGeometryUpdateCount += 1;
        return flushedAny;
    }

    function _flushPendingWireDragUpdate() {
        if (!root._wireDragDirty)
            return false;
        var canvas = root._pendingWireDragCanvas;
        var payload = root._pendingWireDragPayload;
        root._wireDragDirty = false;
        root._pendingWireDragCanvas = null;
        root._pendingWireDragPayload = null;
        if (!canvas || !payload || !canvas.updatePortWireDrag)
            return false;
        canvas.updatePortWireDrag(
            payload.node_id,
            payload.port_key,
            payload.direction,
            payload.scene_x,
            payload.scene_y,
            payload.screen_x,
            payload.screen_y,
            payload.drag_active,
            payload.modifiers
        );
        root.flushedWireDragUpdateCount += 1;
        return true;
    }

    function scheduleToolbarGrace(host) {
        var previousHost = root._toolbarGraceHost;
        if (previousHost && previousHost !== host && previousHost.finishToolbarGrace)
            previousHost.finishToolbarGrace();
        root._toolbarGraceHost = host;
        toolbarGraceTimer.restart();
    }

    function cancelToolbarGrace(host) {
        if (root._toolbarGraceHost !== host)
            return;
        toolbarGraceTimer.stop();
        root._toolbarGraceHost = null;
    }

    function registerElapsedHost(host, active) {
        var hosts = root._elapsedHosts || [];
        var index = hosts.indexOf(host);
        if (active && index < 0) {
            var added = hosts.slice(0);
            added.push(host);
            root._elapsedHosts = added;
            if (host && host.updateSharedElapsed)
                host.updateSharedElapsed(Date.now());
        } else if (!active && index >= 0) {
            var removed = hosts.slice(0);
            removed.splice(index, 1);
            root._elapsedHosts = removed;
        }
    }

    function unregisterHost(host) {
        root.cancelToolbarGrace(host);
        root.registerElapsedHost(host, false);
    }

    function _tickElapsedHosts() {
        var hosts = root._elapsedHosts || [];
        var nowMs = Date.now();
        for (var i = 0; i < hosts.length; i++) {
            var host = hosts[i];
            if (host && host.updateSharedElapsed)
                host.updateSharedElapsed(nowMs);
        }
    }

    function flushPendingRedraws() {
        var hadDirtyWork = root._hasDirtyWork();
        if (!hadDirtyWork) {
            root._flushPending = false;
            return false;
        }
        var hadViewStateRedraw = root._viewStateRedrawDirty;
        var hadCoalescedViewportInput = root._panDirty || root._zoomDirty;

        var flushedAny = false;
        var edgeFlushed = false;
        flushedAny = root._flushPendingPan() || flushedAny;
        flushedAny = root._flushPendingZoom() || flushedAny;
        flushedAny = root._flushPendingLiveDragOffset() || flushedAny;
        flushedAny = root._flushPendingLiveNodeGeometry() || flushedAny;
        flushedAny = root._flushPendingWireDragUpdate() || flushedAny;

        if (root._viewStateRedrawDirty) {
            root._viewStateRedrawDirty = false;
            var backgroundFlushed = false;
            if (root.backgroundLayer && root.backgroundLayer.flushViewStateRedraw) {
                backgroundFlushed = Boolean(root.backgroundLayer.flushViewStateRedraw());
                flushedAny = backgroundFlushed || flushedAny;
            }
            if (backgroundFlushed)
                root.flushedGridUpdateCount += 1;
            if (root.edgeLayer && root.edgeLayer.flushViewStateRedraw) {
                edgeFlushed = Boolean(root.edgeLayer.flushViewStateRedraw()) || edgeFlushed;
                flushedAny = edgeFlushed || flushedAny;
            }
        }

        if (root._edgeRedrawDirty) {
            root._edgeRedrawDirty = false;
            if (!edgeFlushed && root.edgeLayer) {
                if (root.edgeLayer.flushScheduledRedraw)
                    edgeFlushed = Boolean(root.edgeLayer.flushScheduledRedraw());
                else if (root.edgeLayer.requestImmediateRedraw)
                    edgeFlushed = Boolean(root.edgeLayer.requestImmediateRedraw());
                else if (root.edgeLayer.requestRedraw) {
                    root.edgeLayer.requestRedraw();
                    edgeFlushed = true;
                }
                flushedAny = edgeFlushed || flushedAny;
            }
        }

        if (root._overlayRedrawDirty) {
            root._overlayRedrawDirty = false;
            root.flushedOverlayUpdateCount += 1;
        }
        root._flushPending = false;
        if (hadViewStateRedraw && !hadCoalescedViewportInput)
            root._endProgrammaticViewportInteractionIfClean();
        if (flushedAny)
            root.flushedFrameCount += 1;
        return flushedAny;
    }

    Timer {
        id: frameFlushTimer
        interval: Math.max(1, Number(root.frameBudgetMs || 16))
        repeat: false
        onTriggered: root.flushPendingRedraws()
    }

    Timer {
        id: toolbarGraceTimer
        interval: 120
        repeat: false
        onTriggered: {
            var host = root._toolbarGraceHost;
            root._toolbarGraceHost = null;
            if (host && host.finishToolbarGrace)
                host.finishToolbarGrace();
        }
    }

    Timer {
        id: elapsedHostTicker
        interval: 100
        repeat: true
        running: root._elapsedHosts.length > 0
        onTriggered: root._tickElapsedHosts()
    }
}
