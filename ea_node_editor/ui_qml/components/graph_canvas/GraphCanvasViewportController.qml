import QtQuick 2.15
import QtQml 2.15
import "GraphCanvasLogic.js" as GraphCanvasLogic

QtObject {
    id: root
    property Item canvasItem: null
    property var shellCommandBridge: null
    property var viewStateBridge: null
    property var viewCommandBridge: null
    property var interactionState: null
    property var backgroundLayer: null
    property var edgeLayer: null
    property var redrawFlushTimer: null
    property var frameScheduler: null
    property bool _viewportSizeUpdateScheduled: false

    function toggleMinimapExpanded() {
        if (!root.canvasItem)
            return;
        var nextExpanded = !root.canvasItem.minimapExpanded;
        var bridge = root.shellCommandBridge;
        if (bridge && bridge.set_graphics_minimap_expanded) {
            bridge.set_graphics_minimap_expanded(nextExpanded);
            return;
        }
        root.canvasItem.minimapExpanded = nextExpanded;
    }

    function beginViewportInteraction() {
        if (root.interactionState && root.interactionState.beginViewportInteraction)
            root.interactionState.beginViewportInteraction();
    }

    function finishViewportInteractionSoon() {
        if (root.interactionState && root.interactionState.finishViewportInteractionSoon)
            root.interactionState.finishViewportInteractionSoon();
    }

    function noteViewportInteraction() {
        if (root.interactionState && root.interactionState.noteViewportInteraction)
            root.interactionState.noteViewportInteraction();
    }

    function screenToSceneX(screenX) {
        var view = root.viewStateBridge;
        var canvas = root.canvasItem;
        return GraphCanvasLogic.screenToSceneX(
            screenX,
            (view ? view.center_x : 0.0),
            (canvas ? canvas.width : 0.0),
            (view ? view.zoom_value : 1.0)
        );
    }

    function screenToSceneY(screenY) {
        var view = root.viewStateBridge;
        var canvas = root.canvasItem;
        return GraphCanvasLogic.screenToSceneY(
            screenY,
            (view ? view.center_y : 0.0),
            (canvas ? canvas.height : 0.0),
            (view ? view.zoom_value : 1.0)
        );
    }

    function sceneToScreenX(sceneX) {
        var view = root.viewStateBridge;
        var canvas = root.canvasItem;
        return GraphCanvasLogic.sceneToScreenX(
            sceneX,
            (view ? view.center_x : 0.0),
            (canvas ? canvas.width : 0.0),
            (view ? view.zoom_value : 1.0)
        );
    }

    function sceneToScreenY(sceneY) {
        var view = root.viewStateBridge;
        var canvas = root.canvasItem;
        return GraphCanvasLogic.sceneToScreenY(
            sceneY,
            (view ? view.center_y : 0.0),
            (canvas ? canvas.height : 0.0),
            (view ? view.zoom_value : 1.0)
        );
    }

    function wheelDeltaY(eventObj) {
        return GraphCanvasLogic.wheelDeltaY(eventObj);
    }

    function _sceneNodePayloads() {
        var canvas = root.canvasItem;
        if (!canvas)
            return [];
        if (canvas.sceneNodesModel !== undefined && canvas.sceneNodesModel !== null)
            return canvas.sceneNodesModel || [];
        var bridge = canvas.sceneStateBridge || null;
        if (!bridge)
            return [];
        var visiblePayloads = bridge.visible_nodes_payloads;
        if (visiblePayloads !== undefined && visiblePayloads !== null)
            return visiblePayloads || [];
        var visibleModel = bridge.visible_nodes_model;
        if (Array.isArray(visibleModel))
            return visibleModel;
        if (bridge.nodes_model !== undefined && bridge.nodes_model !== null)
            return bridge.nodes_model || [];
        return [];
    }

    function _surfaceFamily(nodePayload) {
        if (!nodePayload)
            return "";
        var surfaceSpec = nodePayload.surface_spec || {};
        return String(nodePayload.surface_family || surfaceSpec.family || "").trim();
    }

    function _boolPayloadFlag(value) {
        if (value === undefined || value === null)
            return false;
        if (typeof value === "boolean")
            return value;
        var normalized = String(value || "").trim().toLowerCase();
        return normalized === "1"
            || normalized === "true"
            || normalized === "yes"
            || normalized === "on";
    }

    function _nodeUsesPlotViewportInteractionCache(nodePayload) {
        if (root._surfaceFamily(nodePayload) !== "plot")
            return false;
        if (!nodePayload || nodePayload.plot_surface === undefined || nodePayload.plot_surface === null)
            return false;
        var plotSurface = nodePayload.plot_surface || {};
        return !root._boolPayloadFlag(plotSurface.embedded_rendering_suppressed);
    }

    function _nodeUsesViewerViewportInteractionCache(nodePayload) {
        if (root._surfaceFamily(nodePayload) !== "viewer")
            return false;
        if (!nodePayload || nodePayload.viewer_surface === undefined || nodePayload.viewer_surface === null)
            return false;
        var viewerSurface = nodePayload.viewer_surface || {};
        return viewerSurface.live_surface_supported === undefined
            ? true
            : root._boolPayloadFlag(viewerSurface.live_surface_supported);
    }

    function _viewportInteractionCacheSurfacePresent() {
        var nodes = root._sceneNodePayloads();
        for (var index = 0; index < nodes.length; index++) {
            if (
                root._nodeUsesPlotViewportInteractionCache(nodes[index])
                || root._nodeUsesViewerViewportInteractionCache(nodes[index])
            )
                return true;
        }
        return false;
    }

    function shouldUseViewportInteractionQualityForWheelZoom() {
        return Boolean(root.canvasItem) && root._viewportInteractionCacheSurfacePresent();
    }

    function applyWheelZoom(eventObj) {
        var canvas = root.canvasItem;
        var viewCommand = root.viewCommandBridge;
        if (!canvas || !viewCommand)
            return false;
        var deltaY = root.wheelDeltaY(eventObj);
        if (Math.abs(deltaY) < 0.001)
            return false;
        if (root.shouldUseViewportInteractionQualityForWheelZoom())
            root.noteViewportInteraction();

        var cursorX = Number(eventObj && eventObj.x);
        var cursorY = Number(eventObj && eventObj.y);
        var hasCursor = isFinite(cursorX) && isFinite(cursorY);
        var sceneBeforeX = 0.0;
        var sceneBeforeY = 0.0;
        if (hasCursor) {
            sceneBeforeX = root.screenToSceneX(cursorX);
            sceneBeforeY = root.screenToSceneY(cursorY);
        }

        var steps = deltaY / 120.0;
        if (Math.abs(steps) < 0.01)
            steps = deltaY > 0 ? 1.0 : -1.0;
        steps = Math.max(-1.0, Math.min(1.0, steps));
        var factor = Math.pow(1.15, steps);
        if (hasCursor && viewCommand.adjust_zoom_at_viewport_point) {
            viewCommand.adjust_zoom_at_viewport_point(factor, cursorX, cursorY);
            return true;
        }

        if (viewCommand.adjust_zoom)
            viewCommand.adjust_zoom(factor);

        if (hasCursor) {
            var sceneAfterX = root.screenToSceneX(cursorX);
            var sceneAfterY = root.screenToSceneY(cursorY);
            if (viewCommand.pan_by)
                viewCommand.pan_by(sceneBeforeX - sceneAfterX, sceneBeforeY - sceneAfterY);
        }
        return true;
    }

    function normalizedSceneRectPayload(rectLike) {
        if (rectLike === undefined || rectLike === null)
            return null;

        var x = Number(rectLike.x);
        var y = Number(rectLike.y);
        var width = Number(rectLike.width);
        var height = Number(rectLike.height);
        if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(height))
            return null;

        if (width < 0.0) {
            x += width;
            width = Math.abs(width);
        }
        if (height < 0.0) {
            y += height;
            height = Math.abs(height);
        }

        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        };
    }

    function scenePaddingForViewportPixels(paddingPx) {
        var zoom = root.viewStateBridge ? Number(root.viewStateBridge.zoom_value) : 1.0;
        if (!isFinite(zoom) || zoom <= 0.0001)
            zoom = 1.0;

        var padding = Number(paddingPx);
        if (!isFinite(padding) || padding < 0.0)
            padding = 0.0;
        return padding / zoom;
    }

    function inflateSceneRectPayload(rectLike, horizontalPadding, verticalPadding) {
        var normalized = root.normalizedSceneRectPayload(rectLike);
        if (!normalized)
            return ({});

        var resolvedHorizontalPadding = Number(horizontalPadding);
        if (!isFinite(resolvedHorizontalPadding) || resolvedHorizontalPadding < 0.0)
            resolvedHorizontalPadding = 0.0;
        var resolvedVerticalPadding = verticalPadding === undefined || verticalPadding === null
            ? resolvedHorizontalPadding
            : Number(verticalPadding);
        if (!isFinite(resolvedVerticalPadding) || resolvedVerticalPadding < 0.0)
            resolvedVerticalPadding = 0.0;

        return {
            "x": normalized.x - resolvedHorizontalPadding,
            "y": normalized.y - resolvedVerticalPadding,
            "width": normalized.width + (resolvedHorizontalPadding * 2.0),
            "height": normalized.height + (resolvedVerticalPadding * 2.0)
        };
    }

    function frameSceneRectPayload(rectLike, paddingPx) {
        var normalized = root.normalizedSceneRectPayload(rectLike);
        var viewCommand = root.viewCommandBridge;
        if (!normalized || !viewCommand || !viewCommand.frame_scene_rect_payload)
            return false;

        var resolvedPadding = Number(paddingPx);
        if (!isFinite(resolvedPadding) || resolvedPadding < 0.0)
            resolvedPadding = 0.0;
        return viewCommand.frame_scene_rect_payload(
            normalized.x,
            normalized.y,
            normalized.width,
            normalized.height,
            resolvedPadding
        );
    }

    function frameScreenRect(screenX1, screenY1, screenX2, screenY2, paddingPx) {
        var sceneX1 = root.screenToSceneX(screenX1);
        var sceneY1 = root.screenToSceneY(screenY1);
        var sceneX2 = root.screenToSceneX(screenX2);
        var sceneY2 = root.screenToSceneY(screenY2);
        return root.frameSceneRectPayload(
            {
                "x": sceneX1,
                "y": sceneY1,
                "width": sceneX2 - sceneX1,
                "height": sceneY2 - sceneY1
            },
            paddingPx
        );
    }

    function requestViewStateRedraw() {
        if (root.frameScheduler && root.frameScheduler.requestViewStateRedraw) {
            root.frameScheduler.requestViewStateRedraw();
            return;
        }
        if (root.backgroundLayer && root.backgroundLayer.markViewStateRedrawDirty)
            root.backgroundLayer.markViewStateRedrawDirty();
        if (root.edgeLayer && root.edgeLayer.markViewStateRedrawDirty)
            root.edgeLayer.markViewStateRedrawDirty();
        if (root.redrawFlushTimer && !root.redrawFlushTimer.running)
            root.redrawFlushTimer.start();
    }

    function flushViewStateRedraw() {
        if (root.frameScheduler && root.frameScheduler.flushPendingRedraws) {
            root.frameScheduler.flushPendingRedraws();
            return;
        }
        if (root.backgroundLayer && root.backgroundLayer.flushViewStateRedraw)
            root.backgroundLayer.flushViewStateRedraw();
        if (root.edgeLayer && root.edgeLayer.flushViewStateRedraw)
            root.edgeLayer.flushViewStateRedraw();
    }

    function updateViewportSize() {
        if (!root.canvasItem)
            return;
        var view = root.viewCommandBridge;
        if (view && view.set_viewport_size)
            view.set_viewport_size(root.canvasItem.width, root.canvasItem.height);
    }

    function scheduleViewportSizeUpdate() {
        updateViewportSize();
        if (_viewportSizeUpdateScheduled)
            return;
        _viewportSizeUpdateScheduled = true;
        Qt.callLater(function() {
            root._viewportSizeUpdateScheduled = false;
            root.updateViewportSize();
        });
    }
}
