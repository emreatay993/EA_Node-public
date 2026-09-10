.pragma library
// Purpose: Own renderer-neutral edge paint and drag-preview presentation facts.
// Map: feature_routes/edge_routing_labels_progress.md
// Tests: tests/qml_quick/tst_edge_paint_policy.qml

function edgeIsFlow(edge) {
    if (!edge)
        return false;
    if (String(edge.edge_family || "") === "flow")
        return true;
    return String(edge.source_port_kind || "") === "flow"
        && String(edge.target_port_kind || "") === "flow";
}

function flowStyle(edge) {
    if (!edge)
        return ({});
    if (edge.flow_style)
        return edge.flow_style;
    return edge.visual_style || ({});
}

function styleString(value) {
    return String(value || "").trim();
}

function stylePositiveNumber(value, fallback) {
    var numeric = Number(value);
    if (!isFinite(numeric) || numeric <= 0.0)
        return fallback;
    return numeric;
}

function flowStrokePattern(edge) {
    var style = flowStyle(edge);
    var pattern = styleString(style.stroke_pattern || style.stroke).toLowerCase();
    if (pattern === "dashed" || pattern === "dotted")
        return pattern;
    return "solid";
}

function flowArrowHead(edge) {
    var style = flowStyle(edge);
    var arrowHead = styleString(style.arrow_head).toLowerCase();
    if (!arrowHead && style.arrow)
        arrowHead = styleString(style.arrow.kind).toLowerCase();
    if (arrowHead === "open" || arrowHead === "none")
        return arrowHead;
    return "filled";
}

function flowStrokeColor(edgeLayer, edge, selected, previewed) {
    if (previewed)
        return edgeLayer.previewStrokeColor;
    var style = flowStyle(edge);
    var styledColor = styleString(style.stroke_color || style.color);
    if (styledColor)
        return styledColor;
    if (selected)
        return edgeLayer.selectedStrokeColor;
    return edgeLayer.flowDefaultStrokeColor;
}

function flowStrokeWidth(edge, selected, previewed, zoom) {
    var baseWidth = stylePositiveNumber(flowStyle(edge).stroke_width, 2.0);
    if (selected)
        baseWidth = Math.max(baseWidth, 3.0);
    else if (previewed)
        baseWidth = Math.max(baseWidth, 2.8);
    return Math.max(1.0, baseWidth * zoom);
}

function flowDashPattern(edge, zoom) {
    var unit = Math.max(1.0, zoom);
    var pattern = flowStrokePattern(edge);
    if (pattern === "dashed")
        return [Math.max(3.0, 8.0 * unit), Math.max(2.0, 5.0 * unit)];
    if (pattern === "dotted")
        return [Math.max(1.0, 1.0 * unit), Math.max(2.0, 4.0 * unit)];
    return [];
}

function standardEdgeActive(edge) {
    return Boolean(edge && edge.active_data_wire);
}

function standardEdgeBaseColor(edgeLayer, edge) {
    if (standardEdgeActive(edge))
        return edgeLayer.activeDefaultStrokeColor;
    return edge && edge.color ? edge.color : edgeLayer.fallbackStrokeColor;
}

function standardEdgeDataAccess(edge) {
    var access = String(edge && edge.data_access || "item").trim().toLowerCase();
    return access === "list" || access === "tree" ? access : "item";
}

function standardEdgeDisplayMode(edge) {
    if (!standardEdgeActive(edge))
        return "default";
    var mode = String((edge.visual_style || {}).display_mode || "default").trim().toLowerCase();
    return mode === "faint" || mode === "hidden" ? mode : "default";
}

function standardEdgeInvalid(edge) {
    return Boolean(edge && edge.data_type_warning);
}

function standardEdgeMuted(edgeLayer, edge) {
    if (!edge || standardEdgeInvalid(edge))
        return false;
    var state = edgeLayer ? edgeLayer.edgeValueState(edge) : "";
    return state === "disabled" || state === "empty" || state === "never";
}

function standardEdgeStrokeColor(edgeLayer, snapshot, edge) {
    if (standardEdgeInvalid(edge))
        return standardEdgeBaseColor(edgeLayer, edge);
    if (standardEdgeActive(edge)) {
        if (snapshot.selected || snapshot.previewed)
            return edgeLayer.activeSelectedStrokeColor;
        return standardEdgeBaseColor(edgeLayer, edge);
    }
    if (standardEdgeMuted(edgeLayer, edge))
        return edgeLayer.inactiveStrokeColor;
    if (snapshot.selected)
        return edgeLayer.selectedStrokeColor;
    if (snapshot.previewed)
        return edgeLayer.previewStrokeColor;
    return standardEdgeBaseColor(edgeLayer, edge);
}

function standardEdgeBaseWidthPx(snapshot, edge, structure, zoom) {
    if (standardEdgeActive(edge)) {
        if (structure === "empty")
            return 1.0;
        return 2.0;
    }
    if (snapshot.selected)
        return 3.0;
    if (snapshot.previewed)
        return 2.8;
    return 2.0;
}

function standardEdgeStructure(edgeLayer, edge) {
    if (standardEdgeActive(edge)
            && edgeLayer
            && edgeLayer.edgeValueState(edge) === "empty") {
        return "empty";
    }
    var access = standardEdgeDataAccess(edge);
    return access === "tree" ? "tree" : (access === "list" ? "list" : "single");
}

function standardEdgeStrokeCount(edge, structure) {
    if (standardEdgeActive(edge))
        return structure === "empty" ? 2 : 1;
    var count = Math.round(Number(edge && edge.stroke_count || 1));
    return Math.max(1, Math.min(3, isFinite(count) ? count : 1));
}

function standardEdgeStrokeOffsetsScreenPx(edge, structure) {
    if (standardEdgeActive(edge))
        return structure === "empty" ? [-1.5, 1.5] : [0.0];
    var count = standardEdgeStrokeCount(edge, structure);
    if (count === 2)
        return [-2.25, 2.25];
    if (count === 3)
        return [-3.5, 0.0, 3.5];
    return [0.0];
}

function standardEdgeDashPattern(edgeLayer, edge, structure, replacementPreviewed, zoom) {
    if (standardEdgeActive(edge)) {
        if (replacementPreviewed || structure === "list")
            return [1.0, 4.0];
        if (structure === "tree")
            return [8.0, 5.0];
        return [];
    }
    if (!standardEdgeMuted(edgeLayer, edge))
        return [];
    var unit = Math.max(1.0, zoom);
    return [Math.max(3.0, 8.0 * unit), Math.max(2.0, 5.0 * unit)];
}

function dragConnectionMode(connection) {
    var mode = String(connection && connection.connection_mode || "connect").trim().toLowerCase();
    return mode === "append" || mode === "replace" || mode === "noop"
            || mode === "disconnect" || mode === "copy" || mode === "rewire"
        ? mode
        : "connect";
}

function dragConnectionDashPattern(edgeLayer, connection, zoom) {
    var unit = Math.max(1.0, zoom);
    var mode = dragConnectionMode(connection);
    var activeDataWire = edgeLayer && edgeLayer.dragConnectionActiveDataWire(connection);
    if (activeDataWire)
        return mode === "disconnect" || mode === "rewire"
            ? [Math.max(4.0, 10.0 * unit), Math.max(2.0, 4.0 * unit)]
            : [];
    if (mode === "append" || mode === "copy")
        return [Math.max(1.0, 2.0 * unit), Math.max(2.0, 3.0 * unit)];
    if (mode === "replace" || mode === "disconnect" || mode === "rewire")
        return [Math.max(4.0, 10.0 * unit), Math.max(2.0, 4.0 * unit)];
    if (mode === "noop")
        return [Math.max(1.0, 1.0 * unit), Math.max(3.0, 5.0 * unit)];
    return [Math.max(2.0, 6.0 * unit), Math.max(1.0, 4.0 * unit)];
}

function dragConnectionMarkerText(edgeLayer, connection) {
    var mode = dragConnectionMode(connection);
    if (mode === "append" || mode === "copy")
        return "+";
    if (edgeLayer && edgeLayer.dragConnectionActiveDataWire(connection))
        return "";
    return mode === "replace" ? "R" : (mode === "noop" ? "=" : "");
}

function dragConnectionMarkerVisible(edgeLayer, connection) {
    var markerText = dragConnectionMarkerText(edgeLayer, connection);
    if (!markerText.length)
        return false;
    if (!Boolean(connection && connection.valid_drop))
        return false;
    return !(edgeLayer
        && edgeLayer.dragConnectionActiveDataWire(connection)
        && dragConnectionMode(connection) === "noop");
}

function dragConnectionMarkerColor(edgeLayer, connection, dragStrokeColor) {
    var mode = dragConnectionMode(connection);
    if (edgeLayer
            && edgeLayer.dragConnectionActiveDataWire(connection)
            && (mode === "append" || mode === "copy")) {
        return "#419248";
    }
    return dragStrokeColor;
}

function dragConnectionMarkerPlain(edgeLayer, connection) {
    var mode = dragConnectionMode(connection);
    return Boolean(edgeLayer
        && edgeLayer.dragConnectionActiveDataWire(connection)
        && (mode === "append" || mode === "copy"));
}

function dragConnectionStrokeColor(edgeLayer, connection) {
    if (edgeLayer && edgeLayer.dragConnectionActiveDataWire(connection))
        return edgeLayer.activeDefaultStrokeColor;
    return connection && connection.valid_drop
        ? edgeLayer.validDragStrokeColor
        : edgeLayer.invalidDragStrokeColor;
}

function dragConnectionStrokeWidthScreenPx(edgeLayer, connection, zoom) {
    if (edgeLayer && edgeLayer.dragConnectionActiveDataWire(connection))
        return 2.0;
    return Math.max(1.0, (connection && connection.valid_drop ? 2.7 : 2.0) * zoom);
}

function standardEdgePaintState(edgeLayer, snapshot, edge, zoom) {
    var activeDataWire = standardEdgeActive(edge);
    var dataAccess = standardEdgeDataAccess(edge);
    var displayMode = standardEdgeDisplayMode(edge);
    var structure = standardEdgeStructure(edgeLayer, edge);
    var hidden = activeDataWire
        && displayMode === "hidden"
        && !(edgeLayer && edgeLayer.wireSelectionModeHeld)
        && !snapshot.selected
        && !snapshot.previewed
        && !snapshot.replacementPreviewed;
    var faint = activeDataWire && (displayMode === "faint" || snapshot.replacementPreviewed)
        && !snapshot.selected
        && !snapshot.previewed;
    var invalidGradient = activeDataWire && standardEdgeInvalid(edge);
    var nodeSelectionGradient = activeDataWire
        && !snapshot.selected
        && Boolean(snapshot.sourceNodeSelected || snapshot.targetNodeSelected);
    var gradientKind = invalidGradient
        ? "invalid_target"
        : (nodeSelectionGradient
            ? (snapshot.sourceNodeSelected
                ? (snapshot.targetNodeSelected ? "selected_both" : "selected_source")
                : "selected_target")
            : "none");
    var baseWidthPx = standardEdgeBaseWidthPx(snapshot, edge, structure, zoom);
    var strokeAlpha = 1.0;
    if (faint)
        strokeAlpha = Math.min(strokeAlpha, 0.30);
    if (snapshot.selected || snapshot.previewed)
        strokeAlpha = 1.0;
    var disabledMarkerColor = edgeLayer.dangerStrokeColor;
    if (!invalidGradient && (snapshot.selected || snapshot.previewed))
        disabledMarkerColor = edgeLayer.activeSelectedStrokeColor;
    var disabledMarkerAlpha = faint ? 0.30 : 1.0;
    return {
        "flowEdge": false,
        "activeDataWire": activeDataWire,
        "dataAccess": dataAccess,
        "displayMode": displayMode,
        "structure": structure,
        "selected": Boolean(snapshot.selected),
        "previewed": Boolean(snapshot.previewed),
        "replacementPreviewed": Boolean(snapshot.replacementPreviewed),
        "sourceNodeSelected": Boolean(snapshot.sourceNodeSelected),
        "targetNodeSelected": Boolean(snapshot.targetNodeSelected),
        "baseColor": standardEdgeBaseColor(edgeLayer, edge),
        "strokeColor": standardEdgeStrokeColor(edgeLayer, snapshot, edge),
        "strokeAlpha": strokeAlpha,
        "strokeWidthScreenPx": Math.max(1.0, activeDataWire ? baseWidthPx : baseWidthPx * zoom),
        "strokeCount": standardEdgeStrokeCount(edge, structure),
        "strokeOffsetsScreenPx": standardEdgeStrokeOffsetsScreenPx(edge, structure),
        "dashPatternScreenPx": standardEdgeDashPattern(
            edgeLayer,
            edge,
            structure,
            Boolean(snapshot.replacementPreviewed),
            zoom
        ),
        "muted": standardEdgeMuted(edgeLayer, edge),
        "invalid": standardEdgeInvalid(edge),
        "bodyVisible": !hidden && !(activeDataWire && invalidGradient && structure === "empty"),
        "endpointArcsVisible": hidden,
        "disabledMarkerVisible": activeDataWire && edge.enabled === false && !hidden,
        "disabledMarkerColor": disabledMarkerColor,
        "disabledMarkerAlpha": disabledMarkerAlpha,
        "nodeSelectionGradient": nodeSelectionGradient,
        "invalidGradient": invalidGradient,
        "gradientKind": gradientKind
    };
}

function standardEdgeGradientStops(edgeLayer, paintState, fadeRatio) {
    var baseColor = paintState.baseColor;
    var selectedColor = edgeLayer.activeSelectedStrokeColor;
    var dangerColor = edgeLayer.dangerStrokeColor;
    var ratio = Math.max(0.02, Math.min(0.5, Number(fadeRatio)));
    if (paintState.invalidGradient) {
        var sourceSelected = paintState.selected
            || paintState.previewed
            || paintState.sourceNodeSelected;
        return [
            {"position": 0.0, "color": sourceSelected ? selectedColor : baseColor},
            {"position": ratio, "color": dangerColor},
            {"position": 1.0, "color": dangerColor}
        ];
    }
    if (paintState.gradientKind === "selected_source")
        return [
            {"position": 0.0, "color": selectedColor},
            {"position": 1.0 - ratio, "color": selectedColor},
            {"position": 1.0, "color": baseColor}
        ];
    if (paintState.gradientKind === "selected_target")
        return [
            {"position": 0.0, "color": baseColor},
            {"position": ratio, "color": selectedColor},
            {"position": 1.0, "color": selectedColor}
        ];
    if (paintState.gradientKind === "selected_both")
        return [
            {"position": 0.0, "color": selectedColor},
            {"position": 1.0, "color": selectedColor}
        ];
    return [
        {"position": 0.0, "color": baseColor},
        {"position": 1.0 - ratio, "color": baseColor},
        {"position": 1.0, "color": paintState.strokeColor}
    ];
}
