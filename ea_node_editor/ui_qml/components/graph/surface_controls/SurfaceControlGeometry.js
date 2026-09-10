.pragma library

function _number(value, fallback) {
    var numeric = Number(value);
    return isFinite(numeric) ? numeric : (fallback === undefined ? 0 : fallback);
}

function listEditorRowHeight(value, baseRowHeight) {
    var itemCount = value && value.length !== undefined
        ? Math.max(0, Math.floor(_number(value.length, 0)))
        : 0;
    var visibleItemCount = Math.min(itemCount, 3);
    return _number(baseRowHeight, 26)
        + visibleItemCount * 28
        + Math.max(0, visibleItemCount - 1) * 3
        + 4
        + 26;
}

function normalizedRect(rectLike) {
    if (!rectLike)
        return null;
    var width = _number(rectLike.width, 0);
    var height = _number(rectLike.height, 0);
    if (!(width > 0) || !(height > 0))
        return null;
    return {
        "x": _number(rectLike.x, 0),
        "y": _number(rectLike.y, 0),
        "width": width,
        "height": height
    };
}

function rectFromItem(item, hostItem) {
    if (!item || !hostItem || !item.visible)
        return null;
    var localX = _number(item.x, 0);
    var localY = _number(item.y, 0);
    var dependencyX = localX;
    var dependencyY = localY;
    var ancestor = item.parent;
    while (ancestor && ancestor !== hostItem) {
        dependencyX += _number(ancestor.x, 0);
        dependencyY += _number(ancestor.y, 0);
        ancestor = ancestor.parent;
    }
    var width = _number(item.width, 0);
    var height = _number(item.height, 0);
    if (!(width > 0) || !(height > 0))
        return null;
    var topLeft = item.mapToItem(hostItem, 0, 0);
    return normalizedRect({
        "x": _number(topLeft.x, dependencyX),
        "y": _number(topLeft.y, dependencyY),
        "width": width,
        "height": height
    });
}

function rectList(rectLike) {
    var rect = normalizedRect(rectLike);
    return rect ? [rect] : [];
}

function collectVisibleItemRects(items, hostItem) {
    var rects = [];
    if (!items || !hostItem)
        return rects;
    for (var index = 0; index < items.length; index++) {
        var rect = rectFromItem(items[index], hostItem);
        if (rect)
            rects.push(rect);
    }
    return rects;
}

function combineRectLists(rectLists) {
    var combined = [];
    if (!rectLists)
        return combined;
    for (var index = 0; index < rectLists.length; index++) {
        var list = rectLists[index];
        if (!list)
            continue;
        for (var rectIndex = 0; rectIndex < list.length; rectIndex++) {
            var rect = normalizedRect(list[rectIndex]);
            if (rect)
                combined.push(rect);
        }
    }
    return combined;
}
