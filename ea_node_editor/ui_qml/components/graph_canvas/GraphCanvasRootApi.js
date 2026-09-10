.pragma library
.import "GraphCanvasLogic.js" as GraphCanvasLogic

function invoke(target, methodName, args, fallbackValue) {
    if (!target || typeof target[methodName] !== "function")
        return fallbackValue;
    return target[methodName].apply(target, args || []);
}

function snapToGridEnabled(canvasStateBridge) {
    return canvasStateBridge ? Boolean(canvasStateBridge.snap_to_grid_enabled) : false;
}

function snapGridSize(canvasStateBridge) {
    return GraphCanvasLogic.normalizeSnapGridSize(
        canvasStateBridge ? canvasStateBridge.snap_grid_size : 20.0
    );
}

function snapToGridValue(canvasStateBridge, value) {
    return GraphCanvasLogic.snapToGridValue(value, snapGridSize(canvasStateBridge));
}

function snappedDragDelta(sceneState, canvasStateBridge, nodeId, rawDx, rawDy) {
    return GraphCanvasLogic.snappedDragDelta(
        rawDx,
        rawDy,
        snapToGridEnabled(canvasStateBridge),
        invoke(sceneState, "sceneNodePayload", [nodeId], null),
        snapGridSize(canvasStateBridge)
    );
}

function isPointInCanvas(canvasItem, screenX, screenY) {
    return GraphCanvasLogic.pointInCanvas(
        screenX,
        screenY,
        canvasItem ? canvasItem.width : 0,
        canvasItem ? canvasItem.height : 0
    );
}

function clampMenuPosition(canvasItem, x, y, menuWidth, menuHeight) {
    return GraphCanvasLogic.clampMenuPosition(
        x,
        y,
        menuWidth,
        menuHeight,
        canvasItem ? canvasItem.width : 0,
        canvasItem ? canvasItem.height : 0,
        4
    );
}
