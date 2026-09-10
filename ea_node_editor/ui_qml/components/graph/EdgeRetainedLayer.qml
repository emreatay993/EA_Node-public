import QtQuick 2.15
import QtQml 2.15
import QtQuick.Shapes 1.15
import "EdgeMath.js" as EdgeMath
import "EdgePaintPolicy.js" as EdgePaintPolicy
import "EdgeViewportMath.js" as EdgeViewportMath

Item {
    id: root
    objectName: "graphCanvasEdgeRetainedLayer"
    property Item edgeLayer: null
    property bool rendererSupported: true
    property real profileLastPaintMs: 0.0
    property int profilePaintCount: 0
    property int profileRetainedDelegateCreateCount: 0
    property int profileRetainedDelegateDestroyCount: 0
    property int profileRetainedModelEntryUpdateCount: 0
    property int profileRetainedModelEntrySkipCount: 0
    property var _paintDiagnosticsByEdgeId: ({})
    property int _paintDiagnosticsRevision: 0
    property var _retainedEdgeModel: []
    property real _paintViewportZoom: 1.0
    property real _paintViewportOffsetX: 0.0
    property real _paintViewportOffsetY: 0.0
    readonly property var _currentViewportTransform: root.edgeLayer
        ? EdgeViewportMath.viewportTransform(root.edgeLayer)
        : ({"zoom": root._paintViewportZoom, "offsetX": root._paintViewportOffsetX, "offsetY": root._paintViewportOffsetY})
    readonly property bool viewportTransformCompensationActive: root.edgeLayer
        ? Boolean(root.edgeLayer._viewStateRedrawDirty)
        : false
    readonly property real viewportTransformCompensationScale: {
        if (!root.viewportTransformCompensationActive)
            return 1.0;
        var paintedZoom = Number(root._paintViewportZoom);
        var currentZoom = Number((root._currentViewportTransform || {}).zoom);
        if (!isFinite(paintedZoom) || paintedZoom <= 0.0001)
            paintedZoom = 1.0;
        if (!isFinite(currentZoom) || currentZoom <= 0.0001)
            currentZoom = paintedZoom;
        return currentZoom / paintedZoom;
    }
    readonly property real viewportTransformCompensationX: {
        if (!root.viewportTransformCompensationActive)
            return 0.0;
        var current = root._currentViewportTransform || ({});
        return Number(current.offsetX || 0.0) - root._paintViewportOffsetX * root.viewportTransformCompensationScale;
    }
    readonly property real viewportTransformCompensationY: {
        if (!root.viewportTransformCompensationActive)
            return 0.0;
        var current = root._currentViewportTransform || ({});
        return Number(current.offsetY || 0.0) - root._paintViewportOffsetY * root.viewportTransformCompensationScale;
    }
    readonly property int retainedEdgeCount: retainedEdgeModel.count

    ListModel {
        id: retainedEdgeModel
        dynamicRoles: true
    }

    function _recordPaint(startedMs) {
        root.profileLastPaintMs = Math.max(0.0, Date.now() - Number(startedMs || Date.now()));
        root.profilePaintCount += 1;
    }

    function _rememberPaintViewport(viewportTransform) {
        var viewport = viewportTransform || ({});
        var zoom = Number(viewport.zoom);
        root._paintViewportZoom = isFinite(zoom) && zoom > 0.0001 ? zoom : 1.0;
        var offsetX = Number(viewport.offsetX);
        var offsetY = Number(viewport.offsetY);
        root._paintViewportOffsetX = isFinite(offsetX) ? offsetX : 0.0;
        root._paintViewportOffsetY = isFinite(offsetY) ? offsetY : 0.0;
    }

    function _compatibleSnapshot(snapshot) {
        if (!snapshot || snapshot.culled || !snapshot.geometry)
            return false;
        if (snapshot.flowEdge)
            return false;
        if (snapshot.hiddenUnrevealed)
            return false;
        if (snapshot.activeDataWire
                && Boolean(snapshot.edgeData && snapshot.edgeData.data_type_warning))
            return false;
        if (!snapshot.selected && (snapshot.sourceNodeSelected || snapshot.targetNodeSelected))
            return false;
        if ((snapshot.crossingBreaks || []).length > 0)
            return false;
        var route = String(snapshot.geometry.route || "bezier");
        return route === "bezier" || route === "pipe";
    }

    function canRenderSnapshots(snapshots) {
        if (!root.rendererSupported || !root.edgeLayer)
            return false;
        if (root.edgeLayer.dragConnectionList().length > 0)
            return false;
        var source = snapshots || [];
        for (var i = 0; i < source.length; i++) {
            var snapshot = source[i];
            if (!snapshot || snapshot.culled)
                continue;
            if (!root._compatibleSnapshot(snapshot))
                return false;
        }
        return true;
    }

    function _screenBezier(geometry, viewportTransform) {
        return {
            "sx": EdgeViewportMath.sceneXToScreen(Number(geometry.sx || 0.0), viewportTransform),
            "sy": EdgeViewportMath.sceneYToScreen(Number(geometry.sy || 0.0), viewportTransform),
            "c1x": EdgeViewportMath.sceneXToScreen(Number(geometry.c1x || 0.0), viewportTransform),
            "c1y": EdgeViewportMath.sceneYToScreen(Number(geometry.c1y || 0.0), viewportTransform),
            "c2x": EdgeViewportMath.sceneXToScreen(Number(geometry.c2x || 0.0), viewportTransform),
            "c2y": EdgeViewportMath.sceneYToScreen(Number(geometry.c2y || 0.0), viewportTransform),
            "tx": EdgeViewportMath.sceneXToScreen(Number(geometry.tx || 0.0), viewportTransform),
            "ty": EdgeViewportMath.sceneYToScreen(Number(geometry.ty || 0.0), viewportTransform)
        };
    }

    function _screenPolyline(points, viewportTransform) {
        var source = points || [];
        var screenPoints = [];
        for (var i = 0; i < source.length; i++) {
            var point = source[i] || ({});
            screenPoints.push({
                "x": EdgeViewportMath.sceneXToScreen(Number(point.x || 0.0), viewportTransform),
                "y": EdgeViewportMath.sceneYToScreen(Number(point.y || 0.0), viewportTransform)
            });
        }
        return screenPoints;
    }

    function _polylineSegments(points) {
        var segments = [];
        var source = points || [];
        for (var i = 1; i < source.length; i++) {
            segments.push({
                "sx": Number(source[i - 1].x || 0.0),
                "sy": Number(source[i - 1].y || 0.0),
                "tx": Number(source[i].x || 0.0),
                "ty": Number(source[i].y || 0.0)
            });
        }
        return segments;
    }

    function _endpointNodeId(edge, prefix) {
        return String(edge && (edge[prefix + "_anchor_node_id"] || edge[prefix + "_node_id"]) || "").trim();
    }

    function _nodeIsDragged(nodeId) {
        var normalized = String(nodeId || "").trim();
        return Boolean(normalized && root.edgeLayer && root.edgeLayer.dragNodeLookup[normalized]);
    }

    function _paintScreenDragDeltaX(nodeId, appliedDx) {
        var current = root._nodeIsDragged(nodeId) ? Number(root.edgeLayer.dragDx || 0.0) : 0.0;
        var applied = Number(appliedDx || 0.0);
        if (!isFinite(applied))
            applied = 0.0;
        return (current - applied) * root._paintViewportZoom;
    }

    function _paintScreenDragDeltaY(nodeId, appliedDy) {
        var current = root._nodeIsDragged(nodeId) ? Number(root.edgeLayer.dragDy || 0.0) : 0.0;
        var applied = Number(appliedDy || 0.0);
        if (!isFinite(applied))
            applied = 0.0;
        return (current - applied) * root._paintViewportZoom;
    }

    function _fixed(value, digits) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = 0.0;
        return numeric.toFixed(digits);
    }

    function _segmentKey(segments) {
        var parts = [];
        var source = segments || [];
        for (var i = 0; i < source.length; i++) {
            var segment = source[i] || ({});
            parts.push(
                root._fixed(segment.sx, 2),
                root._fixed(segment.sy, 2),
                root._fixed(segment.tx, 2),
                root._fixed(segment.ty, 2)
            );
        }
        return parts.join(",");
    }

    function _offsetKey(offsets) {
        var parts = [];
        var source = offsets || [];
        for (var i = 0; i < source.length; ++i) {
            parts.push(root._fixed(source[i].x, 3), root._fixed(source[i].y, 3));
        }
        return parts.join(",");
    }

    function _numberArrayKey(values) {
        var parts = [];
        for (var i = 0; i < (values || []).length; i++)
            parts.push(root._fixed(values[i], 3));
        return parts.join(",");
    }

    function _shapeDashPattern(screenPattern, strokeWidthScreenPx) {
        var width = Math.max(1.0, Number(strokeWidthScreenPx || 1.0));
        var result = [];
        for (var i = 0; i < (screenPattern || []).length; i++)
            result.push(Math.max(0.1, Number(screenPattern[i] || 0.0) / width));
        return result;
    }

    function _contentKeyForEntry(entry) {
        return [
            String(entry.route || "bezier"),
            root._fixed(entry.drawOrderIndex, 4),
            String(entry.sourceNodeId || ""),
            String(entry.targetNodeId || ""),
            root._fixed(entry.sx, 2),
            root._fixed(entry.sy, 2),
            root._fixed(entry.c1x, 2),
            root._fixed(entry.c1y, 2),
            root._fixed(entry.c2x, 2),
            root._fixed(entry.c2y, 2),
            root._fixed(entry.tx, 2),
            root._fixed(entry.ty, 2),
            root._segmentKey(entry.segments),
            root._fixed(entry.appliedSourceDragDx, 2),
            root._fixed(entry.appliedSourceDragDy, 2),
            root._fixed(entry.appliedTargetDragDx, 2),
            root._fixed(entry.appliedTargetDragDy, 2),
            String(entry.strokeColor || ""),
            root._fixed(entry.strokeAlpha, 4),
            root._fixed(entry.strokeWidthScreenPx, 4),
            root._offsetKey(entry.strokeOffsets),
            root._numberArrayKey(entry.dashPattern),
            entry.disabledMarkerVisible ? "disabled" : "enabled",
            String(entry.disabledMarkerColor || ""),
            root._fixed(entry.disabledMarkerAlpha, 4),
            root._fixed(entry.markerX, 2),
            root._fixed(entry.markerY, 2)
        ].join("|");
    }

    function _screenStrokeOffsets(geometry, strokeOffsetsScreenPx) {
        var dx = Number(geometry.tx || 0.0) - Number(geometry.sx || 0.0);
        var dy = Number(geometry.ty || 0.0) - Number(geometry.sy || 0.0);
        var length = Math.sqrt(dx * dx + dy * dy);
        var offsets = strokeOffsetsScreenPx || [0.0];
        var result = [];
        for (var i = 0; i < offsets.length; ++i) {
            var offset = Number(offsets[i] || 0.0);
            result.push(length > 1e-6
                ? {"x": -dy * offset / length, "y": dx * offset / length}
                : {"x": 0.0, "y": 0.0});
        }
        return result;
    }

    function _entryForSnapshot(snapshot, viewportTransform, zoom) {
        var edge = snapshot.edgeData || ({});
        var paintState = EdgePaintPolicy.standardEdgePaintState(
            root.edgeLayer,
            snapshot,
            edge,
            zoom
        );
        var sourceGeometry = snapshot.geometry || ({});
        var route = String(sourceGeometry.route || "bezier");
        var sourceNodeId = root._endpointNodeId(edge, "source");
        var targetNodeId = root._endpointNodeId(edge, "target");
        var sourceDragged = root._nodeIsDragged(sourceNodeId);
        var targetDragged = root._nodeIsDragged(targetNodeId);
        var dragDx = root.edgeLayer ? Number(root.edgeLayer.dragDx || 0.0) : 0.0;
        var dragDy = root.edgeLayer ? Number(root.edgeLayer.dragDy || 0.0) : 0.0;
        var geometry = route === "pipe"
            ? {"sx": 0.0, "sy": 0.0, "c1x": 0.0, "c1y": 0.0, "c2x": 0.0, "c2y": 0.0, "tx": 0.0, "ty": 0.0}
            : root._screenBezier(sourceGeometry, viewportTransform);
        var screenPolyline = route === "pipe"
            ? root._screenPolyline(sourceGeometry.pipe_points || [], viewportTransform)
            : [];
        var offsetGeometry = geometry;
        if (route === "pipe" && screenPolyline.length > 0) {
            offsetGeometry = {
                "sx": screenPolyline[0].x,
                "sy": screenPolyline[0].y,
                "tx": screenPolyline[screenPolyline.length - 1].x,
                "ty": screenPolyline[screenPolyline.length - 1].y
            };
        }
        var entry = {
            "edgeId": String(snapshot.edgeId || ""),
            "drawOrderIndex": Number(snapshot.drawOrderIndex || 0),
            "route": route,
            "sx": geometry.sx,
            "sy": geometry.sy,
            "c1x": geometry.c1x,
            "c1y": geometry.c1y,
            "c2x": geometry.c2x,
            "c2y": geometry.c2y,
            "tx": geometry.tx,
            "ty": geometry.ty,
            "segments": root._polylineSegments(screenPolyline),
            "sourceNodeId": sourceNodeId,
            "targetNodeId": targetNodeId,
            "appliedSourceDragDx": sourceDragged ? dragDx : 0.0,
            "appliedSourceDragDy": sourceDragged ? dragDy : 0.0,
            "appliedTargetDragDx": targetDragged ? dragDx : 0.0,
            "appliedTargetDragDy": targetDragged ? dragDy : 0.0,
            "strokeColor": paintState.strokeColor,
            "strokeAlpha": Number(paintState.strokeAlpha || 0.0),
            "strokeWidthScreenPx": Number(paintState.strokeWidthScreenPx || 1.0),
            "strokeOffsets": root._screenStrokeOffsets(
                offsetGeometry,
                paintState.strokeOffsetsScreenPx || [0.0]
            ),
            "dashed": (paintState.dashPatternScreenPx || []).length > 0,
            "dashPattern": root._shapeDashPattern(
                paintState.dashPatternScreenPx || [],
                paintState.strokeWidthScreenPx
            ),
            "disabledMarkerVisible": Boolean(paintState.disabledMarkerVisible),
            "disabledMarkerColor": paintState.disabledMarkerColor,
            "disabledMarkerAlpha": Number(paintState.disabledMarkerAlpha || 0.0),
            "paintState": paintState
        };
        var markerAnchor = EdgeMath.edgeAnchor(sourceGeometry, 0.5);
        entry.markerX = markerAnchor
            ? EdgeViewportMath.sceneXToScreen(Number(markerAnchor.x), viewportTransform)
            : 0.0;
        entry.markerY = markerAnchor
            ? EdgeViewportMath.sceneYToScreen(Number(markerAnchor.y), viewportTransform)
            : 0.0;
        entry.contentKey = root._contentKeyForEntry(entry);
        return entry;
    }

    function clearRetainedPaint() {
        root._retainedEdgeModel = [];
        retainedEdgeModel.clear();
        root._paintDiagnosticsByEdgeId = ({});
        root._paintDiagnosticsRevision += 1;
    }

    function _retainedModelEdgeId(index) {
        var entry = retainedEdgeModel.get(index);
        return String(entry && entry.edgeId || "");
    }

    function _findRetainedModelIndex(edgeId, startIndex) {
        var normalized = String(edgeId || "");
        for (var i = Math.max(0, Number(startIndex || 0)); i < retainedEdgeModel.count; i++) {
            if (root._retainedModelEdgeId(i) === normalized)
                return i;
        }
        return -1;
    }

    function _setRetainedModelEntry(index, entry) {
        var current = retainedEdgeModel.get(index);
        var currentEntry = current ? (current.edgeEntry || ({})) : ({});
        var currentEdgeId = current ? String(current.edgeId || "") : "";
        if (currentEntry.contentKey === entry.contentKey && currentEdgeId === String(entry.edgeId || "")) {
            root.profileRetainedModelEntrySkipCount += 1;
            return;
        }
        retainedEdgeModel.setProperty(index, "edgeId", entry.edgeId);
        retainedEdgeModel.setProperty(index, "edgeEntry", entry);
        root.profileRetainedModelEntryUpdateCount += 1;
    }

    function _syncRetainedEdgeModel(entries) {
        var source = entries || [];
        var nextLookup = {};
        for (var i = 0; i < source.length; i++)
            nextLookup[String(source[i].edgeId || "")] = true;
        for (var removeIndex = retainedEdgeModel.count - 1; removeIndex >= 0; removeIndex--) {
            if (!nextLookup[root._retainedModelEdgeId(removeIndex)])
                retainedEdgeModel.remove(removeIndex);
        }
        for (var targetIndex = 0; targetIndex < source.length; targetIndex++) {
            var entry = source[targetIndex];
            var edgeId = String(entry.edgeId || "");
            if (targetIndex < retainedEdgeModel.count
                    && root._retainedModelEdgeId(targetIndex) === edgeId) {
                root._setRetainedModelEntry(targetIndex, entry);
                continue;
            }
            var existingIndex = root._findRetainedModelIndex(edgeId, targetIndex + 1);
            if (existingIndex >= 0) {
                retainedEdgeModel.move(existingIndex, targetIndex, 1);
                root._setRetainedModelEntry(targetIndex, entry);
                continue;
            }
            retainedEdgeModel.insert(targetIndex, {"edgeId": edgeId, "edgeEntry": entry});
        }
        while (retainedEdgeModel.count > source.length)
            retainedEdgeModel.remove(retainedEdgeModel.count - 1);
    }

    function requestRetainedPaint() {
        var startedMs = Date.now();
        if (!root.edgeLayer) {
            root.clearRetainedPaint();
            root._recordPaint(startedMs);
            return;
        }
        var snapshots = root.edgeLayer._visibleEdgeSnapshots || [];
        var viewportTransform = EdgeViewportMath.viewportTransform(root.edgeLayer);
        var zoom = EdgeViewportMath.zoomValue(root.edgeLayer);
        root._rememberPaintViewport(viewportTransform);
        var retainedModel = [];
        var diagnosticsByEdgeId = {};
        for (var i = 0; i < snapshots.length; i++) {
            var snapshot = snapshots[i];
            if (!root._compatibleSnapshot(snapshot))
                continue;
            var entry = root._entryForSnapshot(snapshot, viewportTransform, zoom);
            retainedModel.push(entry);
            diagnosticsByEdgeId[entry.edgeId] = entry.paintState;
        }
        root._retainedEdgeModel = retainedModel;
        root._syncRetainedEdgeModel(retainedModel);
        root._paintDiagnosticsByEdgeId = diagnosticsByEdgeId;
        root._paintDiagnosticsRevision += 1;
        root._recordPaint(startedMs);
    }

    Item {
        id: retainedTransformLayer
        objectName: "graphCanvasEdgeRetainedTransformLayer"
        width: root.width
        height: root.height
        transformOrigin: Item.TopLeft
        x: root.viewportTransformCompensationX
        y: root.viewportTransformCompensationY
        scale: root.viewportTransformCompensationScale

        Repeater {
            model: retainedEdgeModel
            delegate: Item {
                id: retainedEdgeDelegate
                property var edgeEntry: model.edgeEntry || ({})
                readonly property real sourceDragDx: root._paintScreenDragDeltaX(
                    edgeEntry.sourceNodeId,
                    edgeEntry.appliedSourceDragDx
                )
                readonly property real sourceDragDy: root._paintScreenDragDeltaY(
                    edgeEntry.sourceNodeId,
                    edgeEntry.appliedSourceDragDy
                )
                readonly property real targetDragDx: root._paintScreenDragDeltaX(
                    edgeEntry.targetNodeId,
                    edgeEntry.appliedTargetDragDx
                )
                readonly property real targetDragDy: root._paintScreenDragDeltaY(
                    edgeEntry.targetNodeId,
                    edgeEntry.appliedTargetDragDy
                )
                z: Number(edgeEntry.drawOrderIndex || 0)
                anchors.fill: parent
                Component.onCompleted: root.profileRetainedDelegateCreateCount += 1
                Component.onDestruction: root.profileRetainedDelegateDestroyCount += 1

                Repeater {
                    model: retainedEdgeDelegate.edgeEntry.strokeOffsets || [{"x": 0.0, "y": 0.0}]
                    delegate: Item {
                        id: retainedStrokeDelegate
                        readonly property var strokeOffset: modelData || ({"x": 0.0, "y": 0.0})
                        anchors.fill: parent

                        Shape {
                            anchors.fill: parent
                            visible: String(retainedEdgeDelegate.edgeEntry.route || "bezier") === "bezier"
                            opacity: Math.max(0.0, Math.min(1.0, Number(retainedEdgeDelegate.edgeEntry.strokeAlpha || 0.0)))
                            containsMode: Shape.FillContains

                            ShapePath {
                                fillColor: "transparent"
                                strokeColor: retainedEdgeDelegate.edgeEntry.strokeColor
                                strokeWidth: Math.max(1.0, Number(retainedEdgeDelegate.edgeEntry.strokeWidthScreenPx || 1.0))
                                capStyle: ShapePath.RoundCap
                                joinStyle: ShapePath.RoundJoin
                                strokeStyle: retainedEdgeDelegate.edgeEntry.dashed
                                    ? ShapePath.DashLine
                                    : ShapePath.SolidLine
                                dashPattern: retainedEdgeDelegate.edgeEntry.dashPattern || []
                                startX: Number(retainedEdgeDelegate.edgeEntry.sx || 0.0)
                                    + retainedEdgeDelegate.sourceDragDx
                                    + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                startY: Number(retainedEdgeDelegate.edgeEntry.sy || 0.0)
                                    + retainedEdgeDelegate.sourceDragDy
                                    + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                PathCubic {
                                    control1X: Number(retainedEdgeDelegate.edgeEntry.c1x || 0.0)
                                        + retainedEdgeDelegate.sourceDragDx
                                        + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                    control1Y: Number(retainedEdgeDelegate.edgeEntry.c1y || 0.0)
                                        + retainedEdgeDelegate.sourceDragDy
                                        + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                    control2X: Number(retainedEdgeDelegate.edgeEntry.c2x || 0.0)
                                        + retainedEdgeDelegate.targetDragDx
                                        + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                    control2Y: Number(retainedEdgeDelegate.edgeEntry.c2y || 0.0)
                                        + retainedEdgeDelegate.targetDragDy
                                        + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                    x: Number(retainedEdgeDelegate.edgeEntry.tx || 0.0)
                                        + retainedEdgeDelegate.targetDragDx
                                        + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                    y: Number(retainedEdgeDelegate.edgeEntry.ty || 0.0)
                                        + retainedEdgeDelegate.targetDragDy
                                        + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                }
                            }
                        }

                        Repeater {
                            model: String(retainedEdgeDelegate.edgeEntry.route || "bezier") === "pipe"
                                ? (retainedEdgeDelegate.edgeEntry.segments || [])
                                : []
                            delegate: Shape {
                                anchors.fill: parent
                                opacity: Math.max(0.0, Math.min(1.0, Number(retainedEdgeDelegate.edgeEntry.strokeAlpha || 0.0)))
                                containsMode: Shape.FillContains

                                ShapePath {
                                    fillColor: "transparent"
                                    strokeColor: retainedEdgeDelegate.edgeEntry.strokeColor
                                    strokeWidth: Math.max(1.0, Number(retainedEdgeDelegate.edgeEntry.strokeWidthScreenPx || 1.0))
                                    capStyle: ShapePath.RoundCap
                                    joinStyle: ShapePath.RoundJoin
                                    strokeStyle: retainedEdgeDelegate.edgeEntry.dashed
                                        ? ShapePath.DashLine
                                        : ShapePath.SolidLine
                                    dashPattern: retainedEdgeDelegate.edgeEntry.dashPattern || []
                                    startX: Number(modelData.sx || 0.0)
                                        + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                    startY: Number(modelData.sy || 0.0)
                                        + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                    PathLine {
                                        x: Number(modelData.tx || 0.0)
                                            + Number(retainedStrokeDelegate.strokeOffset.x || 0.0)
                                        y: Number(modelData.ty || 0.0)
                                            + Number(retainedStrokeDelegate.strokeOffset.y || 0.0)
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    visible: Boolean(retainedEdgeDelegate.edgeEntry.disabledMarkerVisible)
                    opacity: Math.max(0.0, Math.min(1.0, Number(retainedEdgeDelegate.edgeEntry.disabledMarkerAlpha || 0.0)))
                    x: Number(retainedEdgeDelegate.edgeEntry.markerX || 0.0)
                        + (retainedEdgeDelegate.sourceDragDx + retainedEdgeDelegate.targetDragDx) * 0.5
                    y: Number(retainedEdgeDelegate.edgeEntry.markerY || 0.0)
                        + (retainedEdgeDelegate.sourceDragDy + retainedEdgeDelegate.targetDragDy) * 0.5

                    Rectangle {
                        x: -6
                        y: -1
                        width: 12
                        height: 2
                        radius: 1
                        color: retainedEdgeDelegate.edgeEntry.disabledMarkerColor
                        rotation: 45
                    }

                    Rectangle {
                        x: -6
                        y: -1
                        width: 12
                        height: 2
                        radius: 1
                        color: retainedEdgeDelegate.edgeEntry.disabledMarkerColor
                        rotation: -45
                    }
                }
            }
        }
    }
}
