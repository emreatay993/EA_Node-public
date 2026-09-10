import QtQuick 2.15

Item {
    id: root
    objectName: "graphNodeOverlayToolbarLayer"

    property var canvasItem: null
    property var viewBridge: null
    property var sceneStateBridge: null
    property var visibleSceneRectPayload: ({})

    readonly property Item activeHost: root.canvasItem && root.canvasItem.activeToolbarHost
        ? root.canvasItem.activeToolbarHost
        : null

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
    z: 25

    GraphNodeFloatingToolbar {
        id: floatingToolbar
        host: root.activeHost
        canvasItem: root.canvasItem
        viewBridge: root.viewBridge
        visibleSceneRectPayload: root.visibleSceneRectPayload
    }
}
