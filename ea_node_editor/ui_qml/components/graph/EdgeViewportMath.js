.pragma library

function zoomValue(edgeLayer) {
    var zoom = edgeLayer && edgeLayer.viewBridge ? Number(edgeLayer.viewBridge.zoom_value) : 1.0;
    if (!isFinite(zoom) || zoom <= 0.0001)
        return 1.0;
    return zoom;
}

function viewportTransform(edgeLayer) {
    var zoom = zoomValue(edgeLayer);
    var centerX = edgeLayer && edgeLayer.viewBridge ? Number(edgeLayer.viewBridge.center_x) : 0.0;
    var centerY = edgeLayer && edgeLayer.viewBridge ? Number(edgeLayer.viewBridge.center_y) : 0.0;
    if (!isFinite(centerX))
        centerX = 0.0;
    if (!isFinite(centerY))
        centerY = 0.0;
    return {
        "zoom": zoom,
        "offsetX": Number(edgeLayer ? edgeLayer.width : 0.0) * 0.5 - centerX * zoom,
        "offsetY": Number(edgeLayer ? edgeLayer.height : 0.0) * 0.5 - centerY * zoom
    };
}

function sceneXToScreen(worldX, viewportTransformArg) {
    return Number(worldX) * viewportTransformArg.zoom + viewportTransformArg.offsetX;
}

function sceneYToScreen(worldY, viewportTransformArg) {
    return Number(worldY) * viewportTransformArg.zoom + viewportTransformArg.offsetY;
}

function screenToSceneX(screenX, viewportTransformArg) {
    return (Number(screenX) - viewportTransformArg.offsetX) / viewportTransformArg.zoom;
}

function screenToSceneY(screenY, viewportTransformArg) {
    return (Number(screenY) - viewportTransformArg.offsetY) / viewportTransformArg.zoom;
}

function screenLengthToScene(screenLengthPx, viewportTransformArg) {
    return Math.max(0.0, Number(screenLengthPx || 0.0)) / viewportTransformArg.zoom;
}

function screenMarginToScene(screenMarginPx, viewportTransformArg) {
    return screenLengthToScene(screenMarginPx, viewportTransformArg);
}

function dashPatternToScene(screenPattern, viewportTransformArg) {
    var pattern = screenPattern || [];
    var scenePattern = [];
    for (var i = 0; i < pattern.length; i++)
        scenePattern.push(screenLengthToScene(pattern[i], viewportTransformArg));
    return scenePattern;
}

function applyViewportTransform(ctx, viewportTransformArg) {
    ctx.translate(viewportTransformArg.offsetX, viewportTransformArg.offsetY);
    ctx.scale(viewportTransformArg.zoom, viewportTransformArg.zoom);
}
