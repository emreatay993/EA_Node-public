import QtQuick 2.15

Item {
    id: root
    property var canvasItem: null
    property var viewBridge: null
    property var sceneModel: []
    property bool backdropInputOverlay: false
    readonly property int visibleDelegateCount: nodeRepeater.count
    property var _hostByNodeId: ({})

    width: canvasItem ? canvasItem.worldSize : 0
    height: canvasItem ? canvasItem.worldSize : 0
    transformOrigin: Item.TopLeft
    scale: viewBridge ? viewBridge.zoom_value : 1.0
    x: canvasItem
        ? canvasItem.width * 0.5 - ((viewBridge ? viewBridge.center_x : 0) + canvasItem.worldOffset) * scale
        : 0.0
    y: canvasItem
        ? canvasItem.height * 0.5 - ((viewBridge ? viewBridge.center_y : 0) + canvasItem.worldOffset) * scale
        : 0.0

    Repeater {
        id: nodeRepeater
        model: root.sceneModel
        delegate: GraphCanvasNodeDelegate {
            canvasItem: root.canvasItem
            backdropInputOverlay: root.backdropInputOverlay
        }
        onItemAdded: function(_index, item) {
            root._registerHost(item);
            if (root.canvasItem && root.canvasItem.applyLiveDragOffsetToHost)
                root.canvasItem.applyLiveDragOffsetToHost(item);
        }
        onItemRemoved: function(_index, item) {
            root._unregisterHost(item);
        }
    }

    onSceneModelChanged: root._rebuildHostMap()

    function _nodeIdForHost(item) {
        if (!item || !item.nodeData)
            return "";
        return String(item.nodeData.node_id || "").trim();
    }

    function _registerHost(item) {
        var nodeId = root._nodeIdForHost(item);
        if (!nodeId)
            return;
        root._hostByNodeId[nodeId] = item;
    }

    function _unregisterHost(item) {
        var nodeId = root._nodeIdForHost(item);
        if (!nodeId)
            return;
        if (root._hostByNodeId[nodeId] === item)
            delete root._hostByNodeId[nodeId];
    }

    function _rebuildHostMap() {
        var next = {};
        for (var i = 0; i < nodeRepeater.count; i++) {
            var item = nodeRepeater.itemAt(i);
            var nodeId = root._nodeIdForHost(item);
            if (nodeId)
                next[nodeId] = item;
        }
        root._hostByNodeId = next;
    }

    function hostForNodeId(nodeId) {
        var normalized = String(nodeId || "");
        if (!normalized)
            return null;
        return root._hostByNodeId[normalized] || null;
    }

    function allHosts() {
        var hosts = [];
        for (var i = 0; i < nodeRepeater.count; i++) {
            var item = nodeRepeater.itemAt(i);
            if (item)
                hosts.push(item);
        }
        return hosts;
    }
}
