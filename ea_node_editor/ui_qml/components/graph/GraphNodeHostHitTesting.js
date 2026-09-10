.pragma library

function pointInRect(localX, localY, rectLike) {
    if (!rectLike)
        return false;
    var rectX = Number(rectLike.x || 0);
    var rectY = Number(rectLike.y || 0);
    var rectWidth = Number(rectLike.width || 0);
    var rectHeight = Number(rectLike.height || 0);
    return rectWidth > 0
        && rectHeight > 0
        && localX >= rectX
        && localX <= rectX + rectWidth
        && localY >= rectY
        && localY <= rectY + rectHeight;
}

function pointInAnyRect(localX, localY, rects) {
    if (!rects || rects.length <= 0)
        return false;
    for (var index = 0; index < rects.length; index++) {
        if (pointInRect(localX, localY, rects[index]))
            return true;
    }
    return false;
}

function claimsBodyInteraction(localX, localY, rects) {
    return pointInAnyRect(localX, localY, rects);
}

function cornerTriangleContainsPoint(localX, localY, widthValue, heightValue, leftCorner, topCorner) {
    var width = Number(widthValue);
    var height = Number(heightValue);
    if (!isFinite(width) || !isFinite(height) || width <= 0.0 || height <= 0.0)
        return false;

    var xEdge = Boolean(leftCorner) ? Number(localX) : width - Number(localX);
    var yEdge = Boolean(topCorner) ? Number(localY) : height - Number(localY);
    if (!isFinite(xEdge) || !isFinite(yEdge))
        return false;

    return xEdge >= 0.0
        && xEdge <= width
        && yEdge >= 0.0
        && yEdge <= height
        && (xEdge + yEdge) <= Math.min(width, height);
}

function resizeHandleContainsPoint(localX, localY, widthValue, heightValue, handleSize, hitSizeValue, collapsed) {
    if (collapsed)
        return false;
    var width = Number(widthValue);
    var height = Number(heightValue);
    var visualSize = Number(handleSize);
    var hitSize = Number(hitSizeValue);
    if (!isFinite(hitSize) || hitSize <= 0.0)
        hitSize = visualSize;
    if (!isFinite(width) || !isFinite(height) || !isFinite(hitSize) || hitSize <= 0.0)
        return false;
    hitSize = Math.min(hitSize, width, height);
    return cornerTriangleContainsPoint(localX, localY, hitSize, hitSize, true, true)
        || cornerTriangleContainsPoint(localX - (width - hitSize), localY, hitSize, hitSize, false, true)
        || cornerTriangleContainsPoint(localX, localY - (height - hitSize), hitSize, hitSize, true, false)
        || cornerTriangleContainsPoint(
            localX - (width - hitSize),
            localY - (height - hitSize),
            hitSize,
            hitSize,
            false,
            false
        );
}
