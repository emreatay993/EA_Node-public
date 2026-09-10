import QtQuick 2.15
import "EdgeMath.js" as EdgeMath
import "EdgePaintPolicy.js" as EdgePaintPolicy
import "EdgeViewportMath.js" as EdgeViewportMath

Item {
    id: root
    objectName: "graphCanvasEdgeCanvasLayer"
    property Item edgeLayer: null
    readonly property var canvasStateBridgeRef: root.edgeLayer
        && root.edgeLayer.sceneBridge
        ? root.edgeLayer.sceneBridge
        : null
    property real profileLastPaintMs: 0.0
    property int profilePaintCount: 0
    property var _paintDiagnosticsByEdgeId: ({})
    property int _paintDiagnosticsRevision: 0
    property real _paintViewportZoom: 1.0
    property real _paintViewportOffsetX: 0.0
    property real _paintViewportOffsetY: 0.0
    readonly property var _currentViewportTransform: root.edgeLayer
        ? EdgeViewportMath.viewportTransform(root.edgeLayer)
        : ({"zoom": root._paintViewportZoom, "offsetX": root._paintViewportOffsetX, "offsetY": root._paintViewportOffsetY})
    readonly property int effectiveGraphLabelPixelSize: {
        var numeric = NaN;
        if (root.canvasStateBridgeRef)
            numeric = Number(root.canvasStateBridgeRef.graphics_graph_label_pixel_size);
        if (root.edgeLayer
                && root.edgeLayer.parent
                && root.edgeLayer.parent.canvasItem
                && root.edgeLayer.parent.canvasItem.prefs) {
            numeric = Number(root.edgeLayer.parent.canvasItem.prefs.graphLabelPixelSize);
        }
        if (!isFinite(numeric) && root.edgeLayer && root.edgeLayer.graphLabelPixelSize !== undefined)
            numeric = Number(root.edgeLayer.graphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = 10;
        return Math.max(8, Math.min(18, Math.round(numeric)));
    }
    readonly property var graphSharedTypography: edgeLabelGapTypography
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
    function clearCanvasPaintDiagnostics() {
        root._paintDiagnosticsByEdgeId = ({});
        root._paintDiagnosticsRevision += 1;
    }
    function standardStrokeOffsetVector(geometry, offsetScreenPx, viewportTransform) {
        var dx = Number(geometry.tx || 0.0) - Number(geometry.sx || 0.0);
        var dy = Number(geometry.ty || 0.0) - Number(geometry.sy || 0.0);
        var length = Math.sqrt(dx * dx + dy * dy);
        if (!isFinite(length) || length <= 1e-6)
            return {"x": 0.0, "y": 0.0};
        var sceneOffset = EdgeViewportMath.screenLengthToScene(offsetScreenPx, viewportTransform);
        return {"x": -dy * sceneOffset / length, "y": dx * sceneOffset / length};
    }
    function drawDragConnectionMarker(ctx, geometry, markerText, strokeColor, viewportTransform, plain) {
        if (!ctx || !geometry || !String(markerText || "").length)
            return;
        var dx = Number(geometry.tx || 0.0) - Number(geometry.sx || 0.0);
        var dy = Number(geometry.ty || 0.0) - Number(geometry.sy || 0.0);
        var length = Math.sqrt(dx * dx + dy * dy);
        if (!isFinite(length) || length <= 1e-6)
            return;
        var lead = EdgeViewportMath.screenLengthToScene(16.0, viewportTransform);
        var radius = EdgeViewportMath.screenLengthToScene(7.0, viewportTransform);
        var centerX = Number(geometry.tx) - dx * lead / length;
        var centerY = Number(geometry.ty) - dy * lead / length;
        ctx.save();
        ctx.setLineDash([]);
        if (!plain) {
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius, 0.0, Math.PI * 2.0);
            ctx.fillStyle = String(root.shellPalette.canvas_bg || "#151821");
            ctx.fill();
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = EdgeViewportMath.screenLengthToScene(1.5, viewportTransform);
            ctx.stroke();
        }
        ctx.fillStyle = strokeColor;
        ctx.font = "600 " + EdgeViewportMath.screenLengthToScene(plain ? 13.0 : 10.0, viewportTransform) + "px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(markerText), centerX, centerY);
        ctx.restore();
    }
    function traceBezierGeometry(ctx, geometry) {
        ctx.moveTo(geometry.sx, geometry.sy);
        ctx.bezierCurveTo(geometry.c1x, geometry.c1y, geometry.c2x, geometry.c2y, geometry.tx, geometry.ty);
    }
    function tracePolylineGeometry(ctx, points) {
        var polylinePoints = points || [];
        for (var i = 0; i < polylinePoints.length; i++) {
            var point = polylinePoints[i];
            if (i === 0)
                ctx.moveTo(point.x, point.y);
            else
                ctx.lineTo(point.x, point.y);
        }
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
    }
    function _tracePolylineSegmentSpan(ctx, segment, startDistance, endDistance) {
        if (!segment || segment.length <= 1e-6 || endDistance - startDistance <= 1e-6)
            return;
        var startFraction = EdgeMath.clamp((startDistance - segment.startDistance) / segment.length, 0.0, 1.0);
        var endFraction = EdgeMath.clamp((endDistance - segment.startDistance) / segment.length, 0.0, 1.0);
        if (endFraction - startFraction <= 1e-6)
            return;
        var startPoint = {
            "x": segment.a.x + (segment.b.x - segment.a.x) * startFraction,
            "y": segment.a.y + (segment.b.y - segment.a.y) * startFraction
        };
        var endPoint = {
            "x": segment.a.x + (segment.b.x - segment.a.x) * endFraction,
            "y": segment.a.y + (segment.b.y - segment.a.y) * endFraction
        };
        ctx.moveTo(startPoint.x, startPoint.y);
        ctx.lineTo(endPoint.x, endPoint.y);
    }

    function _tracePolylineRange(ctx, segments, startDistance, endDistance) {
        for (var i = 0; i < (segments || []).length; i++)
            root._tracePolylineSegmentSpan(ctx, segments[i], startDistance, endDistance);
    }

    function traceBrokenGeometry(ctx, geometry, sampledPoints, breakRanges) {
        var metrics = EdgeMath.polylineMetrics(sampledPoints || []);
        if (!metrics.points.length) {
            traceGeometry(ctx, geometry);
            return;
        }
        if (!(breakRanges || []).length) {
            tracePolylineGeometry(ctx, metrics.points);
            return;
        }
        var ranges = breakRanges || [];
        var rangeIndex = 0;
        var segments = metrics.segments || [];
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        for (var i = 0; i < segments.length; i++) {
            var segment = segments[i];
            var segmentStart = segment.startDistance;
            var segmentEnd = segment.endDistance;
            while (rangeIndex < ranges.length && Number(ranges[rangeIndex].endDistance) <= segmentStart + 1e-6)
                rangeIndex += 1;
            var visibleStart = segmentStart;
            var scanIndex = rangeIndex;
            while (scanIndex < ranges.length && Number(ranges[scanIndex].startDistance) < segmentEnd - 1e-6) {
                var gapRange = ranges[scanIndex];
                var gapStart = Number(gapRange.startDistance);
                var gapEnd = Number(gapRange.endDistance);
                if (gapStart > visibleStart + 1e-6)
                    _tracePolylineSegmentSpan(ctx, segment, visibleStart, Math.min(gapStart, segmentEnd));
                visibleStart = Math.max(visibleStart, Math.min(segmentEnd, gapEnd));
                if (gapEnd <= segmentEnd + 1e-6)
                    scanIndex += 1;
                else
                    break;
            }
            if (visibleStart < segmentEnd - 1e-6)
                _tracePolylineSegmentSpan(ctx, segment, visibleStart, segmentEnd);
            rangeIndex = scanIndex;
        }
    }

    function strokeStandardGeometry(ctx, geometry, sampledPoints, breakRanges, dashPatternScene) {
        if (!(breakRanges || []).length) {
            ctx.beginPath();
            root.traceGeometry(ctx, geometry);
            ctx.stroke();
            return;
        }
        var metrics = EdgeMath.polylineMetrics(sampledPoints || []);
        if (!metrics.points.length || metrics.totalLength <= 1e-6) {
            ctx.beginPath();
            root.traceGeometry(ctx, geometry);
            ctx.stroke();
            return;
        }
        var cursor = 0.0;
        var ranges = breakRanges || [];
        for (var i = 0; i <= ranges.length; i++) {
            var visibleEnd = i < ranges.length
                ? Math.max(0.0, Math.min(metrics.totalLength, Number(ranges[i].startDistance)))
                : metrics.totalLength;
            if (visibleEnd > cursor + 1e-6) {
                ctx.beginPath();
                root._tracePolylineRange(ctx, metrics.segments, cursor, visibleEnd);
                ctx.lineDashOffset = (dashPatternScene || []).length ? -cursor : 0.0;
                ctx.stroke();
            }
            if (i < ranges.length)
                cursor = Math.max(cursor, Math.min(metrics.totalLength, Number(ranges[i].endDistance)));
        }
        ctx.lineDashOffset = 0.0;
    }

    function traceGeometry(ctx, geometry) {
        if (!geometry)
            return;
        if (geometry.route === "pipe") {
            tracePolylineGeometry(ctx, geometry.pipe_points || []);
            return;
        }
        traceBezierGeometry(ctx, geometry);
    }

    function standardEdgeStrokeStyle(ctx, geometry, paintState) {
        if (!ctx || !geometry || !paintState || paintState.gradientKind === "none")
            return paintState ? paintState.strokeColor : root.edgeLayer.fallbackStrokeColor;
        var gradient = ctx.createLinearGradient(
            Number(geometry.sx),
            Number(geometry.sy),
            Number(geometry.tx),
            Number(geometry.ty)
        );
        var sampled = EdgeMath.sampleGeometryPolyline(geometry, 12.0);
        var totalLength = EdgeMath.polylineMetrics(sampled).totalLength;
        var viewport = root.edgeLayer ? EdgeViewportMath.viewportTransform(root.edgeLayer) : ({"zoom": 1.0});
        var fadeScene = EdgeViewportMath.screenLengthToScene(96.0, viewport);
        var fadeRatio = totalLength > 1e-6
            ? Math.max(0.02, Math.min(0.5, fadeScene / totalLength))
            : 0.5;
        var stops = EdgePaintPolicy.standardEdgeGradientStops(root.edgeLayer, paintState, fadeRatio);
        for (var i = 0; i < stops.length; i++)
            gradient.addColorStop(Number(stops[i].position), stops[i].color);
        return gradient;
    }

    function drawHiddenEndpointArcs(ctx, geometry, paintState, viewportTransform) {
        var sourceAnchor = EdgeMath.edgeAnchor(geometry, 0.0);
        var targetAnchor = EdgeMath.edgeAnchor(geometry, 1.0);
        if (!sourceAnchor || !targetAnchor)
            return;
        var sampleStep = EdgeViewportMath.screenLengthToScene(4.0, viewportTransform);
        var sampledPoints = EdgeMath.sampleGeometryPolyline(geometry, sampleStep);
        var sampledMetrics = EdgeMath.polylineMetrics(sampledPoints);
        if (!sampledMetrics || !sampledMetrics.segments || sampledMetrics.segments.length === 0)
            return;
        var firstSegment = sampledMetrics.segments[0];
        var lastSegment = sampledMetrics.segments[sampledMetrics.segments.length - 1];
        var sourceColor = paintState.sourceNodeSelected
            ? root.edgeLayer.activeSelectedStrokeColor
            : paintState.baseColor;
        var targetColor = paintState.invalid
            ? root.edgeLayer.dangerStrokeColor
            : (paintState.targetNodeSelected ? root.edgeLayer.activeSelectedStrokeColor : paintState.baseColor);
        ctx.save();
        ctx.globalAlpha = 0.72;
        ctx.lineWidth = EdgeViewportMath.screenLengthToScene(1.6, viewportTransform);
        ctx.lineCap = "round";
        ctx.setLineDash([]);
        var sourceAngle = Math.atan2(
            Number(firstSegment.b.y) - Number(firstSegment.a.y),
            Number(firstSegment.b.x) - Number(firstSegment.a.x)
        );
        var targetAngle = Math.atan2(
            Number(lastSegment.a.y) - Number(lastSegment.b.y),
            Number(lastSegment.a.x) - Number(lastSegment.b.x)
        );
        var radii = root.hiddenEndpointArcRadiiScreenPx();
        for (var i = 0; i < radii.length; i++) {
            var radius = EdgeViewportMath.screenLengthToScene(Number(radii[i]), viewportTransform);
            ctx.strokeStyle = sourceColor;
            ctx.beginPath();
            ctx.arc(
                Number(sourceAnchor.x),
                Number(sourceAnchor.y),
                radius,
                sourceAngle - Math.PI * 0.5,
                sourceAngle + Math.PI * 0.5
            );
            ctx.stroke();
            ctx.strokeStyle = targetColor;
            ctx.beginPath();
            ctx.arc(
                Number(targetAnchor.x),
                Number(targetAnchor.y),
                radius,
                targetAngle - Math.PI * 0.5,
                targetAngle + Math.PI * 0.5
            );
            ctx.stroke();
        }
        ctx.restore();
    }

    function hiddenEndpointArcRadiiScreenPx() {
        return [9.0, 12.0, 15.0];
    }

    function drawDisabledMarker(ctx, geometry, strokeColor, strokeAlpha, viewportTransform) {
        var anchor = EdgeMath.edgeAnchor(geometry, 0.5);
        if (!anchor)
            return;
        var radius = EdgeViewportMath.screenLengthToScene(5.0, viewportTransform);
        ctx.save();
        ctx.globalAlpha = Number(strokeAlpha || 1.0);
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = EdgeViewportMath.screenLengthToScene(1.8, viewportTransform);
        ctx.lineCap = "round";
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(anchor.x - radius, anchor.y - radius);
        ctx.lineTo(anchor.x + radius, anchor.y + radius);
        ctx.moveTo(anchor.x - radius, anchor.y + radius);
        ctx.lineTo(anchor.x + radius, anchor.y - radius);
        ctx.stroke();
        ctx.restore();
    }

    function drawFlowArrowHead(ctx, geometry, edge, strokeColor, zoom, viewportTransform) {
        var arrowHead = EdgePaintPolicy.flowArrowHead(edge);
        if (arrowHead === "none")
            return;
        var anchor = EdgeMath.edgeAnchor(geometry, 1.0);
        if (!anchor)
            return;
        var tipX = anchor.x;
        var tipY = anchor.y;
        var size = EdgeViewportMath.screenLengthToScene(Math.max(6.0, 8.0 * zoom), viewportTransform);
        var wing = EdgeViewportMath.screenLengthToScene(Math.max(3.0, 4.5 * zoom), viewportTransform);
        var baseX = tipX - anchor.dx * size;
        var baseY = tipY - anchor.dy * size;
        var normalX = -anchor.dy;
        var normalY = anchor.dx;
        var leftX = baseX + normalX * wing;
        var leftY = baseY + normalY * wing;
        var rightX = baseX - normalX * wing;
        var rightY = baseY - normalY * wing;

        ctx.save();
        ctx.setLineDash([]);
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.strokeStyle = strokeColor;
        ctx.fillStyle = strokeColor;
        ctx.lineWidth = EdgeViewportMath.screenLengthToScene(Math.max(1.0, 1.4 * zoom), viewportTransform);
        ctx.beginPath();
        ctx.moveTo(leftX, leftY);
        ctx.lineTo(tipX, tipY);
        ctx.lineTo(rightX, rightY);
        if (arrowHead === "filled") {
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        } else {
            ctx.stroke();
        }
        ctx.restore();
    }

    function decorationEnabled() {
        return root.edgeLayer.edgeCrossingStyle === "gap_break";
    }

    function shouldReuseCrossingMetadata() {
        return root.edgeLayer.edgeCrossingStyle === "gap_break"
            && root.edgeLayer.viewportInteractionActive;
    }

    function _resetSnapshot(snapshot, preserveCrossingMetadata) {
        if (!snapshot)
            return;
        if (!preserveCrossingMetadata) {
            snapshot.crossingBreaks = [];
            snapshot.crossingSamplePoints = [];
        }
        snapshot.drawOrderIndex = -1;
    }

    function orderSnapshotsForDraw(snapshots, preserveCrossingMetadata) {
        var background = [];
        var emphasized = [];
        var elevated = [];
        var sourceSnapshots = snapshots || [];
        var preserve = Boolean(preserveCrossingMetadata);
        for (var i = 0; i < sourceSnapshots.length; i++) {
            var snapshot = sourceSnapshots[i];
            if (!snapshot)
                continue;
            _resetSnapshot(snapshot, preserve);
            if (snapshot.previewed || snapshot.selected)
                elevated.push(snapshot);
            else if (snapshot.activeDataWire
                    && (snapshot.sourceNodeSelected
                        || snapshot.targetNodeSelected
                        || Boolean(snapshot.edgeData && snapshot.edgeData.data_type_warning)))
                emphasized.push(snapshot);
            else
                background.push(snapshot);
        }
        var ordered = background.concat(emphasized).concat(elevated);
        for (i = 0; i < ordered.length; i++)
            ordered[i].drawOrderIndex = i;
        return ordered;
    }

    function _samplingModelForSnapshot(snapshot, viewportTransform) {
        if (!snapshot || snapshot.culled || !snapshot.geometry)
            return null;
        if (snapshot.displayMode === "hidden")
            return null;
        var sceneStep = EdgeViewportMath.screenLengthToScene(root.edgeLayer.edgeCrossingSampleStepScreenPx, viewportTransform);
        var points = EdgeMath.sampleGeometryPolyline(snapshot.geometry, sceneStep);
        var metrics = EdgeMath.polylineMetrics(points);
        if (!metrics.points.length || !metrics.segments.length || !metrics.bounds)
            return null;
        snapshot.crossingSamplePoints = metrics.points;
        return {"snapshot": snapshot, "points": metrics.points, "metrics": metrics};
    }

    function _snapshotNeedsLabelBreak(snapshot) {
        if (!snapshot || snapshot.culled || !snapshot.geometry || !snapshot.flowEdge)
            return false;
        if (!snapshot.labelAnchorScene)
            return false;
        if (String(snapshot.labelMode || "hidden") === "hidden")
            return false;
        return String(snapshot.labelText || "").trim().length > 0;
    }

    function _hasLabelBreakCandidates(snapshots) {
        var source = snapshots || [];
        for (var i = 0; i < source.length; i++) {
            if (root._snapshotNeedsLabelBreak(source[i]))
                return true;
        }
        return false;
    }

    function _flowLabelScale(viewportTransform) {
        if (!root.edgeLayer)
            return 1.0;
        var zoom = Number((viewportTransform || {}).zoom);
        var threshold = Number(root.edgeLayer.flowLabelHideZoomThreshold);
        if (!isFinite(zoom) || !isFinite(threshold) || threshold <= 0.0 || zoom >= threshold)
            return 1.0;
        return Math.max(0.35, Math.min(1.0, zoom / threshold));
    }

    function _flowLabelMeasuredSize(labelText, labelMode) {
        var pillMode = String(labelMode || "hidden") === "pill";
        labelGapMetrics.text = String(labelText || "").length ? String(labelText || "") : "M";
        labelGapMetrics.font.pixelSize = pillMode
            ? root.graphSharedTypography.edgePillPixelSize
            : root.graphSharedTypography.edgeLabelPixelSize;
        labelGapMetrics.font.weight = pillMode
            ? root.graphSharedTypography.edgePillFontWeight
            : root.graphSharedTypography.edgeLabelFontWeight;
        var maximumTextWidth = pillMode ? 220.0 : 120.0;
        var horizontalPadding = pillMode ? 10.0 : 8.0;
        var verticalPadding = pillMode ? 6.0 : 3.0;
        return {
            "width": Math.min(maximumTextWidth, Math.ceil(labelGapMetrics.advanceWidth)) + horizontalPadding * 2.0,
            "height": Math.ceil(labelGapMetrics.height) + verticalPadding * 2.0
        };
    }

    function _distanceAlongMetricsNearestPoint(metrics, x, y) {
        if (!metrics || !(metrics.segments || []).length)
            return NaN;
        var bestDistance = NaN;
        var bestDistanceSq = Number.POSITIVE_INFINITY;
        var segments = metrics.segments || [];
        for (var i = 0; i < segments.length; i++) {
            var segment = segments[i];
            var dx = Number(segment.b.x) - Number(segment.a.x);
            var dy = Number(segment.b.y) - Number(segment.a.y);
            var lengthSq = dx * dx + dy * dy;
            if (lengthSq <= 1e-9)
                continue;
            var t = ((Number(x) - Number(segment.a.x)) * dx + (Number(y) - Number(segment.a.y)) * dy) / lengthSq;
            t = EdgeMath.clamp(t, 0.0, 1.0);
            var closestX = Number(segment.a.x) + dx * t;
            var closestY = Number(segment.a.y) + dy * t;
            var deltaX = Number(x) - closestX;
            var deltaY = Number(y) - closestY;
            var distanceSq = deltaX * deltaX + deltaY * deltaY;
            if (distanceSq < bestDistanceSq) {
                bestDistanceSq = distanceSq;
                bestDistance = Number(segment.startDistance) + Number(segment.length) * t;
            }
        }
        return bestDistance;
    }

    function _labelBreakRangeForModel(model, viewportTransform) {
        if (!model || !root._snapshotNeedsLabelBreak(model.snapshot))
            return null;
        var snapshot = model.snapshot;
        var anchor = snapshot.labelAnchorScene || ({});
        var centerDistance = root._distanceAlongMetricsNearestPoint(model.metrics, anchor.x, anchor.y);
        if (!isFinite(centerDistance))
            return null;
        var labelSize = root._flowLabelMeasuredSize(snapshot.labelText, snapshot.labelMode);
        var labelScale = root._flowLabelScale(viewportTransform);
        var tangentX = Number(anchor.dx);
        var tangentY = Number(anchor.dy);
        if (!isFinite(tangentX) || !isFinite(tangentY)) {
            var centerFraction = model.metrics.totalLength > 1e-6 ? centerDistance / model.metrics.totalLength : 0.5;
            var tangent = EdgeMath.pointTangentAlongPolyline(model.points, centerFraction);
            tangentX = tangent ? Number(tangent.dx) : 1.0;
            tangentY = tangent ? Number(tangent.dy) : 0.0;
        }
        var widthScreen = Number(labelSize.width) * labelScale;
        var heightScreen = Number(labelSize.height) * labelScale;
        var halfGapScreen = Math.abs(tangentX) * widthScreen * 0.5
            + Math.abs(tangentY) * heightScreen * 0.5
            + 3.0;
        var halfGapScene = EdgeViewportMath.screenLengthToScene(Math.max(6.0, halfGapScreen), viewportTransform);
        return {
            "startDistance": centerDistance - halfGapScene,
            "endDistance": centerDistance + halfGapScene
        };
    }

    function _applyLabelBreakMetadata(samplingModels, viewportTransform, mergeGapScene) {
        var models = samplingModels || [];
        for (var i = 0; i < models.length; i++) {
            var model = models[i];
            var labelBreak = root._labelBreakRangeForModel(model, viewportTransform);
            if (!labelBreak)
                continue;
            var rawRanges = (model.snapshot.crossingBreaks || []).concat([labelBreak]);
            var merged = EdgeMath.mergeBreakRanges(rawRanges, mergeGapScene, model.metrics.totalLength);
            model.snapshot.crossingBreaks = root._enrichedBreakRanges(merged, model.points, model.metrics.totalLength);
        }
    }

    function _rawBreakRangesForPair(underModel, overModel, gapHalfScene, anchorMarginScene) {
        var ranges = [];
        if (!underModel || !overModel)
            return ranges;
        var underMetrics = underModel.metrics;
        var overMetrics = overModel.metrics;
        if (!EdgeMath.rectsIntersect(underMetrics.bounds, overMetrics.bounds))
            return ranges;
        var underSegments = underMetrics.segments || [];
        var overSegments = overMetrics.segments || [];
        for (var i = 0; i < underSegments.length; i++) {
            var underSegment = underSegments[i];
            for (var j = 0; j < overSegments.length; j++) {
                var overSegment = overSegments[j];
                if (!EdgeMath.rectsIntersect(underSegment.bounds, overSegment.bounds))
                    continue;
                var intersection = EdgeMath.segmentIntersection(underSegment.a, underSegment.b, overSegment.a, overSegment.b);
                if (!intersection)
                    continue;
                var underDistance = underSegment.startDistance + underSegment.length * intersection.tA;
                var overDistance = overSegment.startDistance + overSegment.length * intersection.tB;
                if (EdgeMath.distanceNearPolylineEndpoints(underDistance, underMetrics.totalLength, anchorMarginScene))
                    continue;
                if (EdgeMath.distanceNearPolylineEndpoints(overDistance, overMetrics.totalLength, anchorMarginScene))
                    continue;
                ranges.push({
                    "startDistance": underDistance - gapHalfScene,
                    "endDistance": underDistance + gapHalfScene
                });
            }
        }
        return ranges;
    }

    function _enrichedBreakRanges(ranges, points, totalLength) {
        var enriched = [];
        var mergedRanges = ranges || [];
        for (var i = 0; i < mergedRanges.length; i++) {
            var range = mergedRanges[i];
            var centerDistance = (Number(range.startDistance) + Number(range.endDistance)) * 0.5;
            var fraction = totalLength > 1e-6 ? centerDistance / totalLength : 0.5;
            var tangent = EdgeMath.pointTangentAlongPolyline(points, fraction);
            enriched.push({
                "startDistance": Number(range.startDistance),
                "endDistance": Number(range.endDistance),
                "centerDistance": centerDistance,
                "centerX": tangent ? Number(tangent.x) : 0.0,
                "centerY": tangent ? Number(tangent.y) : 0.0,
                "tangentX": tangent ? Number(tangent.dx) : 1.0,
                "tangentY": tangent ? Number(tangent.dy) : 0.0
            });
        }
        return enriched;
    }

    function applyCrossingMetadata(snapshots, viewportTransform) {
        var ordered = orderSnapshotsForDraw(snapshots, false);
        var crossingDecorationEnabled = decorationEnabled();
        var labelBreaksNeeded = root._hasLabelBreakCandidates(ordered);
        if (!crossingDecorationEnabled && !labelBreaksNeeded)
            return ordered;

        var gapHalfScene = EdgeViewportMath.screenLengthToScene(root.edgeLayer.edgeCrossingGapScreenPx * 0.5, viewportTransform);
        var anchorMarginScene = EdgeViewportMath.screenLengthToScene(root.edgeLayer.edgeCrossingAnchorGuardScreenPx, viewportTransform);
        var mergeGapScene = EdgeViewportMath.screenLengthToScene(root.edgeLayer.edgeCrossingMergeScreenPx, viewportTransform);
        var samplingModels = [];
        var i;

        for (i = 0; i < ordered.length; i++) {
            var model = _samplingModelForSnapshot(ordered[i], viewportTransform);
            if (model)
                samplingModels.push(model);
        }

        for (i = 0; i < samplingModels.length; i++) {
            var underModel = samplingModels[i];
            var rawRanges = [];
            if (crossingDecorationEnabled && !underModel.snapshot.selected && !underModel.snapshot.previewed) {
                for (var j = i + 1; j < samplingModels.length; j++) {
                    rawRanges = rawRanges.concat(
                        _rawBreakRangesForPair(underModel, samplingModels[j], gapHalfScene, anchorMarginScene)
                    );
                }
                var merged = EdgeMath.mergeBreakRanges(rawRanges, mergeGapScene, underModel.metrics.totalLength);
                underModel.snapshot.crossingBreaks = _enrichedBreakRanges(merged, underModel.points, underModel.metrics.totalLength);
            }
        }
        if (labelBreaksNeeded)
            root._applyLabelBreakMetadata(samplingModels, viewportTransform, mergeGapScene);

        return ordered;
    }

    function requestCanvasPaint() {
        edgeCanvas.requestPaint();
    }

    Item {
        id: canvasTransformLayer
        objectName: "graphCanvasEdgeCanvasTransformLayer"
        width: root.width
        height: root.height
        transformOrigin: Item.TopLeft
        x: root.viewportTransformCompensationX
        y: root.viewportTransformCompensationY
        scale: root.viewportTransformCompensationScale

        Canvas {
            id: edgeCanvas
            anchors.fill: parent
            renderTarget: Canvas.Image

            onPaint: {
                var startedMs = Date.now();
                var ctx = getContext("2d");
                ctx.reset();
                if (!root.edgeLayer) {
                    root._paintDiagnosticsByEdgeId = ({});
                    root._paintDiagnosticsRevision += 1;
                    root._recordPaint(startedMs);
                    return;
                }
                var zoom = EdgeViewportMath.zoomValue(root.edgeLayer);
                var snapshots = root.edgeLayer._visibleEdgeSnapshots || [];
                var viewportTransform = EdgeViewportMath.viewportTransform(root.edgeLayer);
                var paintDiagnosticsByEdgeId = {};
                root._rememberPaintViewport(viewportTransform);
                ctx.save();
                EdgeViewportMath.applyViewportTransform(ctx, viewportTransform);

                for (var i = 0; i < snapshots.length; i++) {
                    var snapshot = snapshots[i];
                    if (!snapshot || snapshot.culled || !snapshot.geometry)
                        continue;
                    var edge = snapshot.edgeData;
                    var geometry = snapshot.geometry;
                    var selected = snapshot.selected;
                    var previewed = snapshot.previewed;
                    var crossingBreaks = snapshot.crossingBreaks || [];
                    ctx.save();

                    if (snapshot.flowEdge) {
                        ctx.beginPath();
                        if (crossingBreaks.length > 0)
                            root.traceBrokenGeometry(ctx, geometry, snapshot.crossingSamplePoints || [], crossingBreaks);
                        else
                            root.traceGeometry(ctx, geometry);
                        var flowStrokeColor = EdgePaintPolicy.flowStrokeColor(
                            root.edgeLayer,
                            edge,
                            selected,
                            previewed
                        );
                        var flowStrokeWidthScreenPx = EdgePaintPolicy.flowStrokeWidth(
                            edge,
                            selected,
                            previewed,
                            zoom
                        );
                        var flowDashPatternScreenPx = EdgePaintPolicy.flowDashPattern(edge, zoom);
                        ctx.strokeStyle = flowStrokeColor;
                        ctx.lineWidth = EdgeViewportMath.screenLengthToScene(
                            flowStrokeWidthScreenPx,
                            viewportTransform
                        );
                        ctx.setLineDash(
                            EdgeViewportMath.dashPatternToScene(flowDashPatternScreenPx, viewportTransform)
                        );
                        ctx.stroke();
                        root.drawFlowArrowHead(ctx, geometry, edge, flowStrokeColor, zoom, viewportTransform);
                        paintDiagnosticsByEdgeId[snapshot.edgeId] = {
                            "flowEdge": true,
                            "selected": Boolean(selected),
                            "previewed": Boolean(previewed),
                            "baseColor": flowStrokeColor,
                            "strokeColor": flowStrokeColor,
                            "strokeAlpha": 1.0,
                            "strokeWidthScreenPx": flowStrokeWidthScreenPx,
                            "strokeCount": 1,
                            "strokeOffsetsScreenPx": [0.0],
                            "dashPatternScreenPx": flowDashPatternScreenPx,
                            "muted": false,
                            "invalid": false
                        };
                    } else {
                        var standardPaint = EdgePaintPolicy.standardEdgePaintState(
                            root.edgeLayer,
                            snapshot,
                            edge,
                            zoom
                        );
                        if (standardPaint.endpointArcsVisible) {
                            root.drawHiddenEndpointArcs(
                                ctx,
                                geometry,
                                standardPaint,
                                viewportTransform
                            );
                        } else if (standardPaint.bodyVisible) {
                            ctx.globalAlpha = standardPaint.strokeAlpha;
                            ctx.strokeStyle = root.standardEdgeStrokeStyle(ctx, geometry, standardPaint);
                            ctx.lineWidth = EdgeViewportMath.screenLengthToScene(
                                standardPaint.strokeWidthScreenPx,
                                viewportTransform
                            );
                            var standardDashPatternScene = EdgeViewportMath.dashPatternToScene(
                                standardPaint.dashPatternScreenPx,
                                viewportTransform
                            );
                            ctx.setLineDash(standardDashPatternScene);
                            ctx.lineCap = "round";
                            ctx.lineJoin = "round";
                            var strokeOffsets = standardPaint.strokeOffsetsScreenPx || [0.0];
                            for (var strokeIndex = 0; strokeIndex < strokeOffsets.length; ++strokeIndex) {
                                var offset = root.standardStrokeOffsetVector(
                                    geometry,
                                    Number(strokeOffsets[strokeIndex] || 0.0),
                                    viewportTransform
                                );
                                ctx.save();
                                ctx.translate(offset.x, offset.y);
                                root.strokeStandardGeometry(
                                    ctx,
                                    geometry,
                                    snapshot.crossingSamplePoints || [],
                                    crossingBreaks,
                                    standardDashPatternScene
                                );
                                ctx.restore();
                            }
                        }
                        if (standardPaint.disabledMarkerVisible) {
                            root.drawDisabledMarker(
                                ctx,
                                geometry,
                                standardPaint.disabledMarkerColor,
                                standardPaint.disabledMarkerAlpha,
                                viewportTransform
                            );
                        }
                        paintDiagnosticsByEdgeId[snapshot.edgeId] = standardPaint;
                    }
                    ctx.restore();
                }

                var liveDrags = root.edgeLayer.dragConnectionList();
                for (var liveDragIndex = 0; liveDragIndex < liveDrags.length; liveDragIndex++) {
                    var liveDrag = liveDrags[liveDragIndex];
                    var dragGeometry = root.edgeLayer._dragGeometry(liveDrag);
                    if (dragGeometry) {
                        var dragStrokeColor = EdgePaintPolicy.dragConnectionStrokeColor(
                            root.edgeLayer,
                            liveDrag
                        );
                        ctx.save();
                        ctx.beginPath();
                        root.traceGeometry(ctx, dragGeometry);
                        ctx.strokeStyle = dragStrokeColor;
                        ctx.lineWidth = EdgeViewportMath.screenLengthToScene(
                            EdgePaintPolicy.dragConnectionStrokeWidthScreenPx(
                                root.edgeLayer,
                                liveDrag,
                                zoom
                            ),
                            viewportTransform
                        );
                        ctx.setLineDash(
                            EdgeViewportMath.dashPatternToScene(
                                EdgePaintPolicy.dragConnectionDashPattern(
                                    root.edgeLayer,
                                    liveDrag,
                                    zoom
                                ),
                                viewportTransform
                            )
                        );
                        ctx.lineCap = "round";
                        ctx.stroke();
                        if (EdgePaintPolicy.dragConnectionMarkerVisible(root.edgeLayer, liveDrag)) {
                            root.drawDragConnectionMarker(
                                ctx,
                                dragGeometry,
                                EdgePaintPolicy.dragConnectionMarkerText(root.edgeLayer, liveDrag),
                                EdgePaintPolicy.dragConnectionMarkerColor(
                                    root.edgeLayer,
                                    liveDrag,
                                    dragStrokeColor
                                ),
                                viewportTransform,
                                EdgePaintPolicy.dragConnectionMarkerPlain(root.edgeLayer, liveDrag)
                            );
                        }
                        ctx.restore();
                    }
                }

                ctx.restore();
                root._paintDiagnosticsByEdgeId = paintDiagnosticsByEdgeId;
                root._paintDiagnosticsRevision += 1;
                root._recordPaint(startedMs);
            }
        }
    }

    GraphSharedTypography {
        id: edgeLabelGapTypography
        objectName: "graphEdgeCanvasSharedTypography"
        graphLabelPixelSize: root.effectiveGraphLabelPixelSize
    }

    TextMetrics {
        id: labelGapMetrics
        text: "M"
    }
}
