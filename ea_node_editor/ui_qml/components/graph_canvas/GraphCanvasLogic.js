.pragma library
.import "../graph/GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

function screenToSceneX(screenX, centerX, viewportWidth, zoomValue) {
    var zoom = zoomValue;
    return centerX + (screenX - viewportWidth * 0.5) / Math.max(0.1, zoom);
}

function screenToSceneY(screenY, centerY, viewportHeight, zoomValue) {
    var zoom = zoomValue;
    return centerY + (screenY - viewportHeight * 0.5) / Math.max(0.1, zoom);
}

function wheelDeltaY(eventObj) {
    if (!eventObj)
        return 0.0;
    var delta = 0.0;
    if (eventObj.angleDelta && Number(eventObj.angleDelta.y) !== 0)
        delta = Number(eventObj.angleDelta.y);
    else if (eventObj.pixelDelta && Number(eventObj.pixelDelta.y) !== 0)
        delta = Number(eventObj.pixelDelta.y) * 0.5;
    if (eventObj.inverted)
        delta = -delta;
    return delta;
}

function sceneToScreenX(sceneX, centerX, viewportWidth, zoomValue) {
    var zoom = zoomValue;
    return viewportWidth * 0.5 + (sceneX - centerX) * zoom;
}

function sceneToScreenY(sceneY, centerY, viewportHeight, zoomValue) {
    var zoom = zoomValue;
    return viewportHeight * 0.5 + (sceneY - centerY) * zoom;
}

function normalizeSnapGridSize(gridSizeValue) {
    var size = Number(gridSizeValue);
    if (!(size > 0.0))
        size = 20.0;
    return size;
}

function snapToGridValue(value, gridSizeValue) {
    var size = normalizeSnapGridSize(gridSizeValue);
    return Math.round(Number(value) / size) * size;
}

function snappedDragDelta(rawDx, rawDy, snapEnabled, anchorPayload, gridSizeValue) {
    var deltaX = Number(rawDx);
    var deltaY = Number(rawDy);
    if (!isFinite(deltaX))
        deltaX = 0.0;
    if (!isFinite(deltaY))
        deltaY = 0.0;
    if (!snapEnabled)
        return {"dx": deltaX, "dy": deltaY};
    if (!anchorPayload)
        return {"dx": deltaX, "dy": deltaY};

    var anchorX = Number(anchorPayload.x);
    var anchorY = Number(anchorPayload.y);
    if (!isFinite(anchorX))
        anchorX = 0.0;
    if (!isFinite(anchorY))
        anchorY = 0.0;

    var snappedX = snapToGridValue(anchorX + deltaX, gridSizeValue);
    var snappedY = snapToGridValue(anchorY + deltaY, gridSizeValue);
    return {
        "dx": snappedX - anchorX,
        "dy": snappedY - anchorY
    };
}

function normalizeEdgeIds(values) {
    var normalized = [];
    var seen = {};
    var sourceValues = values || [];
    for (var i = 0; i < sourceValues.length; i++) {
        var id = String(sourceValues[i] || "").trim();
        if (!id || seen[id])
            continue;
        seen[id] = true;
        normalized.push(id);
    }
    return normalized;
}

function availableEdgeIdSet(edges) {
    var ids = {};
    var sourceEdges = edges || [];
    for (var i = 0; i < sourceEdges.length; i++) {
        ids[sourceEdges[i].edge_id] = true;
    }
    return ids;
}

function pruneSelectedEdgeIds(selectedEdgeIds, availableIds) {
    var next = [];
    var selected = selectedEdgeIds || [];
    var idSet = availableIds || {};
    for (var i = 0; i < selected.length; i++) {
        var edgeId = selected[i];
        if (idSet[edgeId])
            next.push(edgeId);
    }
    return next;
}

function normalizedPortSide(sideLike) {
    var normalized = String(sideLike || "").trim().toLowerCase();
    if (normalized === "top" || normalized === "right" || normalized === "bottom" || normalized === "left")
        return normalized;
    return "";
}

function portSide(port) {
    return normalizedPortSide(GraphNodeSurfaceMetrics.portCardinalSide(port));
}

function isFlowEdgePortKind(kindLike) {
    var kind = String(kindLike || "").trim().toLowerCase();
    return kind === "flow";
}

function isNeutralFlowPort(portLike) {
    if (!portLike)
        return false;
    var direction = String(
        portLike.direction !== undefined
            ? portLike.direction
            : (portLike.source_direction !== undefined ? portLike.source_direction : "")
    ).trim().toLowerCase();
    var side = normalizedPortSide(
        portLike.origin_side !== undefined
            ? portLike.origin_side
            : portSide(portLike)
    );
    var kind = String(portLike.kind || "").trim().toLowerCase();
    var dataType = String(portLike.data_type || "").trim().toLowerCase();
    return direction === "neutral"
        && !!side
        && (!kind || kind === "flow")
        && (!dataType || dataType === "flow");
}

function authoredConnection(sourceDrag, candidate) {
    var gestureOrderedNeutral = isNeutralFlowPort(sourceDrag) && isNeutralFlowPort(candidate);
    var sourceDirection = String(sourceDrag && sourceDrag.source_direction || "").trim().toLowerCase();
    var candidateDirection = String(candidate && candidate.direction || "").trim().toLowerCase();
    var sourceFirst = true;
    if (gestureOrderedNeutral)
        sourceFirst = true;
    else if (sourceDirection === "out")
        sourceFirst = true;
    else if (sourceDirection === "in")
        sourceFirst = false;
    else if (candidateDirection === "in")
        sourceFirst = true;
    else if (candidateDirection === "out")
        sourceFirst = false;
    return sourceFirst
        ? {
            "source_node_id": sourceDrag.node_id,
            "source_port_key": sourceDrag.port_key,
            "target_node_id": candidate.node_id,
            "target_port_key": candidate.port_key,
            "target_kind": String(candidate.kind || ""),
            "target_allows_multiple": Boolean(candidate.allow_multiple_connections),
            "gesture_ordered_neutral": gestureOrderedNeutral
        }
        : {
            "source_node_id": candidate.node_id,
            "source_port_key": candidate.port_key,
            "target_node_id": sourceDrag.node_id,
            "target_port_key": sourceDrag.port_key,
            "target_kind": String(sourceDrag.kind || ""),
            "target_allows_multiple": Boolean(sourceDrag.allow_multiple_connections),
            "gesture_ordered_neutral": gestureOrderedNeutral
        };
}

function dropTargetInput(sourceDrag, candidate) {
    var connection = authoredConnection(sourceDrag, candidate);
    return {
        "node_id": connection.target_node_id,
        "port_key": connection.target_port_key
    };
}

function isExactDuplicate(sourceDrag, candidate, edge) {
    var connection = authoredConnection(sourceDrag, candidate);
    return edge.source_node_id === connection.source_node_id
        && edge.source_port_key === connection.source_port_key
        && edge.target_node_id === connection.target_node_id
        && edge.target_port_key === connection.target_port_key;
}

function isDropAllowedWithCompatibility(sourceDrag, candidate, edges, kindsCompatible, typesCompatible) {
    if (!sourceDrag || !candidate)
        return false;
    if (candidate.node_id === sourceDrag.node_id && candidate.port_key === sourceDrag.port_key)
        return false;
    if (
        candidate.node_id === sourceDrag.node_id
        && isFlowEdgePortKind(sourceDrag.kind)
        && isFlowEdgePortKind(candidate.kind)
    )
        return false;
    var connection = authoredConnection(sourceDrag, candidate);
    if (!connection.gesture_ordered_neutral && candidate.direction === sourceDrag.source_direction)
        return false;
    if (!kindsCompatible)
        return false;
    if (!typesCompatible)
        return false;

    var targetInput = {
        "node_id": connection.target_node_id,
        "port_key": connection.target_port_key
    };
    var targetAllowsMultiple = connection.target_allows_multiple;
    var edgePayload = edges || [];
    for (var i = 0; i < edgePayload.length; i++) {
        var edge = edgePayload[i];
        var sameTargetInput = edge.target_node_id === targetInput.node_id && edge.target_port_key === targetInput.port_key;
        if (!sameTargetInput)
            continue;
        if (isExactDuplicate(sourceDrag, candidate, edge))
            continue;
        if (targetAllowsMultiple || !isFlowEdgePortKind(connection.target_kind))
            continue;
        return false;
    }
    return true;
}

function portsCompatibleForAuto(sourcePort, targetPort, kindsCompatible, typesCompatible) {
    if (!sourcePort || !targetPort)
        return false;
    return kindsCompatible && typesCompatible;
}

function autoConnectCompatibleWithTarget(targetPort, nodePort, kindsCompatible, typesCompatible) {
    if (!portsCompatibleForAuto(nodePort, targetPort, kindsCompatible, typesCompatible))
        return false;
    var targetNeutral = isNeutralFlowPort(targetPort);
    var nodeNeutral = isNeutralFlowPort(nodePort);
    if (targetNeutral || nodeNeutral)
        return targetNeutral && nodeNeutral;
    var targetDirection = String(targetPort.direction || "").trim().toLowerCase();
    if (targetDirection === "in")
        return String(nodePort.direction || "").trim().toLowerCase() === "out";
    if (targetDirection === "out")
        return String(nodePort.direction || "").trim().toLowerCase() === "in";
    return false;
}

function autoConnectCompatibleAsInsertedInput(sourcePort, nodePort, kindsCompatible, typesCompatible) {
    if (!portsCompatibleForAuto(sourcePort, nodePort, kindsCompatible, typesCompatible))
        return false;
    var sourceNeutral = isNeutralFlowPort(sourcePort);
    var nodeNeutral = isNeutralFlowPort(nodePort);
    if (sourceNeutral || nodeNeutral)
        return sourceNeutral && nodeNeutral;
    return String(nodePort.direction || "").trim().toLowerCase() === "in";
}

function autoConnectCompatibleAsInsertedOutput(nodePort, targetPort, kindsCompatible, typesCompatible) {
    if (!portsCompatibleForAuto(nodePort, targetPort, kindsCompatible, typesCompatible))
        return false;
    var targetNeutral = isNeutralFlowPort(targetPort);
    var nodeNeutral = isNeutralFlowPort(nodePort);
    if (targetNeutral || nodeNeutral)
        return targetNeutral && nodeNeutral;
    return String(nodePort.direction || "").trim().toLowerCase() === "out";
}

function libraryPorts(payload) {
    var ports = [];
    if (!payload || !payload.ports)
        return ports;
    for (var i = 0; i < payload.ports.length; i++) {
        var sourcePort = payload.ports[i];
        if (!sourcePort)
            continue;
        ports.push(
            {
                "key": String(sourcePort.key || ""),
                "direction": String(sourcePort.direction || ""),
                "kind": String(sourcePort.kind || ""),
                "data_type": String(sourcePort.data_type || ""),
                "side": GraphNodeSurfaceMetrics.portCardinalSide(sourcePort),
                "exposed": sourcePort.exposed !== false
            }
        );
    }
    return ports;
}

function scenePortPoint(node, port, inputRow, outputRow) {
    return GraphNodeSurfaceMetrics.portScenePointForPort(node, port, inputRow, outputRow);
}

function previewNodeMetrics(payload) {
    return GraphNodeSurfaceMetrics.surfaceMetrics(payload);
}

function previewVisiblePorts(payload, direction) {
    return GraphNodeSurfaceMetrics.visiblePortsForDirection(payload, direction);
}

function previewPortColor(kind) {
    return "#7AA8FF";
}

function previewNodeScreenExtent(worldExtent, zoomValue) {
    return worldExtent * zoomValue;
}

function previewPortLabelsVisible(zoomValue, previewNodeWidth) {
    return zoomValue >= 0.95 && previewNodeWidth >= 155;
}

function pointInCanvas(screenX, screenY, canvasWidth, canvasHeight) {
    return Number(screenX) >= 0
        && Number(screenY) >= 0
        && Number(screenX) <= canvasWidth
        && Number(screenY) <= canvasHeight;
}

function clampMenuPosition(x, y, menuWidth, menuHeight, canvasWidth, canvasHeight, padding) {
    var safePadding = Number(padding);
    if (!(safePadding >= 0.0))
        safePadding = 4.0;
    return {
        "x": Math.max(safePadding, Math.min(x, canvasWidth - menuWidth - safePadding)),
        "y": Math.max(safePadding, Math.min(y, canvasHeight - menuHeight - safePadding))
    };
}

function normalizedOffset(period, anchor) {
    var raw = anchor % period;
    if (raw < 0)
        raw += period;
    return raw;
}

function normalizeRectPayload(payload, fallbackX, fallbackY, fallbackWidth, fallbackHeight) {
    var x = Number(payload && payload.x);
    var y = Number(payload && payload.y);
    var width = Number(payload && payload.width);
    var height = Number(payload && payload.height);
    if (!isFinite(x))
        x = Number(fallbackX);
    if (!isFinite(y))
        y = Number(fallbackY);
    if (!(width > 0.0))
        width = Number(fallbackWidth);
    if (!(height > 0.0))
        height = Number(fallbackHeight);
    return {
        "x": x,
        "y": y,
        "width": Math.max(1.0, width),
        "height": Math.max(1.0, height)
    };
}
