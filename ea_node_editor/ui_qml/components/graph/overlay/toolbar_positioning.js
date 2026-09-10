.pragma library

function _number(value, fallback) {
    var numeric = Number(value);
    if (isFinite(numeric))
        return numeric;
    return Number(fallback) || 0;
}

function _rect(value) {
    var source = value || {};
    return {
        x: _number(source.x, 0),
        y: _number(source.y, 0),
        width: Math.max(0, _number(source.width, 0)),
        height: Math.max(0, _number(source.height, 0))
    };
}

function _size(value) {
    var source = value || {};
    return {
        width: Math.max(0, _number(source.width, 0)),
        height: Math.max(0, _number(source.height, 0))
    };
}

function computeAnchor(nodeRect, toolbarSize, viewportRect, metrics, previousFlipped) {
    var node = _rect(nodeRect);
    var size = _size(toolbarSize);
    var viewport = _rect(viewportRect);
    var options = metrics || {};
    var gap = Math.max(0, _number(options.gap_from_node, 6));
    var safety = Math.max(0, _number(options.safety_margin, 8));
    var hysteresis = Math.max(0, _number(options.hysteresis, 8));

    var topY = node.y - size.height - gap;
    var bottomY = node.y + node.height + gap;

    var viewportValid = viewport.width > 0 && viewport.height > 0;
    var flipped = false;
    if (viewportValid) {
        var minTop = viewport.y + safety;
        if (previousFlipped) {
            flipped = topY < minTop + hysteresis;
        } else {
            flipped = topY < minTop;
        }
    }

    // Toolbar tracks the node's horizontal center unconditionally — no viewport
    // clamp. When the node scrolls off-screen the toolbar follows it rather than
    // pinning to the viewport edge and detaching from its owner.
    var anchorY = flipped ? bottomY : topY;
    var anchorX = node.x + node.width / 2 - size.width / 2;

    return {
        x: anchorX,
        y: anchorY,
        flipped: flipped
    };
}
