import QtQml 2.15

QtObject {
    id: root
    property var canvasItem: null

    function sceneSelectionBridge() {
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        if (bridge && bridge.select_node)
            return bridge;
        return null;
    }

    function pendingActionBridge() {
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        if (bridge && bridge.set_pending_surface_action && bridge.consume_pending_surface_action)
            return bridge;
        return null;
    }

    function propertyBridge() {
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        if (bridge && bridge.set_node_properties)
            return bridge;
        return null;
    }

    function cursorBridge() {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (bridge && bridge.set_graph_cursor_shape && bridge.clear_graph_cursor_shape)
            return bridge;
        return null;
    }

    function pdfPreviewBridge() {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (bridge && bridge.describe_pdf_preview)
            return bridge;
        return null;
    }

    function clearCanvasSelectionState() {
        if (!root.canvasItem)
            return false;
        if (root.canvasItem._closeContextMenus)
            root.canvasItem._closeContextMenus();
        if (root.canvasItem.clearPendingConnection)
            root.canvasItem.clearPendingConnection();
        if (root.canvasItem.clearEdgeSelection)
            root.canvasItem.clearEdgeSelection();
        return true;
    }

    function resetSurfaceInteractionState() {
        var handled = root.clearCanvasSelectionState();
        if (root.canvasItem && root.canvasItem.cancelWireDrag)
            root.canvasItem.cancelWireDrag();
        return handled;
    }

    function selectedNodeIds() {
        if (!root.canvasItem || !root.canvasItem.selectedNodeIds)
            return [];
        return root.canvasItem.selectedNodeIds();
    }
}
