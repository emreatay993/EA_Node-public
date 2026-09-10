import QtQml 2.15
import "GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

QtObject {
    id: root
    property var host: null

    function _localPortPoint(direction, rowIndex, portData, forLayout) {
        if (!root.host || !root.host.nodeData)
            return {"x": 0.0, "y": 0.0};
        var widthValue = Number(root.host.width);
        if (!isFinite(widthValue) || widthValue <= 0.0)
            widthValue = Number(root.host.nodeData.width);
        if (!isFinite(widthValue) || widthValue <= 0.0)
            widthValue = Number(root.host.surfaceMetrics.default_width);
        var heightValue = Number(root.host.settingsGroupLayoutHeight);
        if (!isFinite(heightValue) || heightValue <= 0.0)
            heightValue = Number(root.host.nodeData.height);
        if (!isFinite(heightValue) || heightValue <= 0.0)
            heightValue = Number(root.host.surfaceMetrics.default_height);
        if (portData) {
            var point = GraphNodeSurfaceMetrics.localPortPointForPort(
                root.host.nodeData,
                portData,
                direction === "in" ? rowIndex : -1,
                direction === "out" ? rowIndex : -1,
                widthValue,
                heightValue,
                root.host.effectiveGraphLabelPixelSize
            );
            point.y += forLayout
                ? Number(root.host.settingsGroupOffsets[String(portData.settings_group_id || "")] || 0)
                : Number(root.host.settingsGroupPortOffsets[String(portData.key)] || 0);
            return point;
        }
        return GraphNodeSurfaceMetrics.localPortPoint(
            root.host.nodeData,
            direction,
            rowIndex,
            widthValue,
            heightValue,
            root.host.effectiveGraphLabelPixelSize
        );
    }

    function localPortPoint(direction, rowIndex) {
        return root._localPortPoint(direction, rowIndex, null);
    }

    function localPortPointForPort(direction, rowIndex, portData) {
        return root._localPortPoint(direction, rowIndex, portData, false);
    }

    function _portScenePos(direction, rowIndex, portData) {
        if (!root.host || !root.host.nodeData)
            return {"x": 0.0, "y": 0.0};
        var point = root._localPortPoint(direction, rowIndex, portData);
        var nodeX = root.host._liveGeometryActive ? Number(root.host._liveX) : Number(root.host.nodeData.x);
        var nodeY = root.host._liveGeometryActive ? Number(root.host._liveY) : Number(root.host.nodeData.y);
        return {
            "x": nodeX + point.x,
            "y": nodeY + point.y
        };
    }

    function portScenePos(direction, rowIndex) {
        return root._portScenePos(direction, rowIndex, null);
    }

    function portScenePosForPort(direction, rowIndex, portData) {
        return root._portScenePos(direction, rowIndex, portData);
    }

    function browseNodePropertyPath(key, currentPath) {
        if (!root.host || !root.host.nodeData || !root.host.canvasItem || !root.host.canvasItem.browseNodePropertyPath)
            return "";
        var sourceMode = arguments.length > 2 ? String(arguments[2] || "").trim() : "";
        if (sourceMode.length > 0) {
            return String(
                root.host.canvasItem.browseNodePropertyPath(root.host.nodeData.node_id, key, currentPath, sourceMode) || ""
            );
        }
        return String(
            root.host.canvasItem.browseNodePropertyPath(root.host.nodeData.node_id, key, currentPath) || ""
        );
    }

    function internalizeNodePropertyPath(key, currentPath) {
        if (!root.host || !root.host.nodeData || !root.host.canvasItem || !root.host.canvasItem.internalizeNodePropertyPath)
            return "";
        return String(
            root.host.canvasItem.internalizeNodePropertyPath(root.host.nodeData.node_id, key, currentPath) || ""
        );
    }

    function resolveLocalFileSourceUrl(source) {
        if (!root.host || !root.host.canvasItem || !root.host.canvasItem.resolveNodeSurfaceLocalFileSource)
            return "";
        return String(root.host.canvasItem.resolveNodeSurfaceLocalFileSource(String(source || "")) || "");
    }

    function describeImagePreview(source) {
        if (!root.host || !root.host.canvasItem || !root.host.canvasItem.describeNodeSurfaceImagePreview)
            return ({});
        return root.host.canvasItem.describeNodeSurfaceImagePreview(String(source || ""));
    }

    function describeMailPreview(source) {
        if (!root.host || !root.host.canvasItem || !root.host.canvasItem.describeNodeSurfaceMailPreview)
            return ({});
        return root.host.canvasItem.describeNodeSurfaceMailPreview(String(source || ""));
    }

    function openLocalFileSource(source, chooser) {
        if (!root.host || !root.host.canvasItem || !root.host.canvasItem.openNodeSurfaceLocalFileSource)
            return ({"success": false, "error": {"code": "bridge_unavailable"}});
        return root.host.canvasItem.openNodeSurfaceLocalFileSource(String(source || ""), Boolean(chooser));
    }

    function pickNodePropertyColor(key, currentValue) {
        if (!root.host || !root.host.nodeData || !root.host.canvasItem || !root.host.canvasItem.pickNodePropertyColor)
            return "";
        return String(
            root.host.canvasItem.pickNodePropertyColor(root.host.nodeData.node_id, key, currentValue) || ""
        );
    }

    function currentViewportZoom() {
        var viewBridge = root.host && root.host.canvasItem ? root.host.canvasItem.viewBridge : null;
        var zoom = viewBridge ? Number(viewBridge.zoom_value) : 1.0;
        if (!isFinite(zoom) || zoom <= 0.0001)
            return 1.0;
        return zoom;
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

    function nodeSceneRect() {
        if (!root.host || !root.host.nodeData)
            return null;

        var x = root.host._liveGeometryActive ? Number(root.host._liveX) : Number(root.host.nodeData.x);
        var y = root.host._liveGeometryActive ? Number(root.host._liveY) : Number(root.host.nodeData.y);
        x += Number(root.host.liveDragDx || 0.0);
        y += Number(root.host.liveDragDy || 0.0);
        var width = root.host._liveGeometryActive ? Number(root.host._liveWidth) : Number(root.host.nodeData.width);
        var height = root.host._liveGeometryActive ? Number(root.host._liveHeight) : Number(root.host.nodeData.height);
        if (!isFinite(width) || width <= 0.0)
            width = Number(root.host.surfaceMetrics.default_width);
        if (!isFinite(height) || height <= 0.0)
            height = Number(root.host.surfaceMetrics.default_height);
        if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(height))
            return null;

        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        };
    }

    function sceneRectsIntersect(firstRectLike, secondRectLike) {
        var firstRect = root.normalizedSceneRectPayload(firstRectLike);
        var secondRect = root.normalizedSceneRectPayload(secondRectLike);
        if (!firstRect || !secondRect)
            return true;

        var firstRight = firstRect.x + firstRect.width;
        var firstBottom = firstRect.y + firstRect.height;
        var secondRight = secondRect.x + secondRect.width;
        var secondBottom = secondRect.y + secondRect.height;
        return firstRect.x < secondRight
            && firstRight > secondRect.x
            && firstRect.y < secondBottom
            && firstBottom > secondRect.y;
    }
}
