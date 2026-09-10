.pragma library

function clamp(value, minValue, maxValue) {
    return Math.max(minValue, Math.min(maxValue, value));
}

function distanceSegment(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1;
    var dy = y2 - y1;
    var lengthSq = dx * dx + dy * dy;
    if (lengthSq <= 1e-9) {
        var ddx = px - x1;
        var ddy = py - y1;
        return Math.sqrt(ddx * ddx + ddy * ddy);
    }
    var t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
    t = clamp(t, 0.0, 1.0);
    var closestX = x1 + t * dx;
    var closestY = y1 + t * dy;
    var ddx2 = px - closestX;
    var ddy2 = py - closestY;
    return Math.sqrt(ddx2 * ddx2 + ddy2 * ddy2);
}

function cubicPoint(t, p0, p1, p2, p3) {
    var inv = 1.0 - t;
    var a = inv * inv * inv;
    var b = 3.0 * inv * inv * t;
    var c = 3.0 * inv * t * t;
    var d = t * t * t;
    return a * p0 + b * p1 + c * p2 + d * p3;
}

function distanceBezier(px, py, x0, y0, x1, y1, x2, y2, x3, y3, segments) {
    var sampleCount = Math.max(12, segments || 20);
    var prevX = x0;
    var prevY = y0;
    var minDistance = distanceSegment(px, py, prevX, prevY, prevX, prevY);
    for (var i = 1; i <= sampleCount; i++) {
        var t = i / sampleCount;
        var curX = cubicPoint(t, x0, x1, x2, x3);
        var curY = cubicPoint(t, y0, y1, y2, y3);
        minDistance = Math.min(minDistance, distanceSegment(px, py, prevX, prevY, curX, curY));
        prevX = curX;
        prevY = curY;
    }
    return minDistance;
}

function distancePolyline(px, py, points) {
    if (!points || points.length === 0)
        return Number.POSITIVE_INFINITY;
    if (points.length === 1)
        return distanceSegment(px, py, points[0].x, points[0].y, points[0].x, points[0].y);
    var minDistance = Number.POSITIVE_INFINITY;
    for (var i = 1; i < points.length; i++) {
        var a = points[i - 1];
        var b = points[i];
        minDistance = Math.min(minDistance, distanceSegment(px, py, a.x, a.y, b.x, b.y));
    }
    return minDistance;
}

function distancePoints(x1, y1, x2, y2) {
    var dx = Number(x2) - Number(x1);
    var dy = Number(y2) - Number(y1);
    return Math.sqrt(dx * dx + dy * dy);
}

function _normalizedPoint(pointLike) {
    if (!pointLike)
        return null;
    var x = Number(pointLike.x);
    var y = Number(pointLike.y);
    if (!isFinite(x) || !isFinite(y))
        return null;
    return {"x": x, "y": y};
}

function sampleBezierPolyline(x0, y0, x1, y1, x2, y2, x3, y3, sceneStep) {
    var step = Math.max(0.01, Number(sceneStep || 12.0));
    var approxLength = distancePoints(x0, y0, x1, y1)
        + distancePoints(x1, y1, x2, y2)
        + distancePoints(x2, y2, x3, y3);
    var sampleCount = Math.max(18, Math.min(160, Math.ceil(approxLength / step)));
    var points = [];
    for (var i = 0; i <= sampleCount; i++) {
        var t = i / sampleCount;
        points.push({
            "x": cubicPoint(t, x0, x1, x2, x3),
            "y": cubicPoint(t, y0, y1, y2, y3)
        });
    }
    return points;
}

function sampleGeometryPolyline(geometry, sceneStep) {
    if (!geometry)
        return [];
    if (geometry.route === "pipe") {
        var pipePoints = geometry.pipe_points || [];
        var copied = [];
        for (var i = 0; i < pipePoints.length; i++) {
            var point = _normalizedPoint(pipePoints[i]);
            if (point)
                copied.push(point);
        }
        return copied;
    }
    return sampleBezierPolyline(
        geometry.sx,
        geometry.sy,
        geometry.c1x,
        geometry.c1y,
        geometry.c2x,
        geometry.c2y,
        geometry.tx,
        geometry.ty,
        sceneStep
    );
}

function _segmentBounds(a, b) {
    return {
        "left": Math.min(Number(a.x), Number(b.x)),
        "top": Math.min(Number(a.y), Number(b.y)),
        "right": Math.max(Number(a.x), Number(b.x)),
        "bottom": Math.max(Number(a.y), Number(b.y))
    };
}

function polylineMetrics(points) {
    var sourcePoints = points || [];
    var normalized = [];
    var minX = Number.POSITIVE_INFINITY;
    var minY = Number.POSITIVE_INFINITY;
    var maxX = Number.NEGATIVE_INFINITY;
    var maxY = Number.NEGATIVE_INFINITY;
    var i;

    for (i = 0; i < sourcePoints.length; i++) {
        var point = _normalizedPoint(sourcePoints[i]);
        if (!point)
            continue;
        if (normalized.length > 0) {
            var prevPoint = normalized[normalized.length - 1];
            if (distancePoints(prevPoint.x, prevPoint.y, point.x, point.y) <= 1e-6)
                continue;
        }
        normalized.push(point);
        minX = Math.min(minX, point.x);
        minY = Math.min(minY, point.y);
        maxX = Math.max(maxX, point.x);
        maxY = Math.max(maxY, point.y);
    }

    var segments = [];
    var totalLength = 0.0;
    for (i = 1; i < normalized.length; i++) {
        var start = normalized[i - 1];
        var end = normalized[i];
        var length = distancePoints(start.x, start.y, end.x, end.y);
        if (length <= 1e-6)
            continue;
        segments.push({
            "a": start,
            "b": end,
            "length": length,
            "startDistance": totalLength,
            "endDistance": totalLength + length,
            "bounds": _segmentBounds(start, end)
        });
        totalLength += length;
    }

    return {
        "points": normalized,
        "segments": segments,
        "totalLength": totalLength,
        "bounds": isFinite(minX) && isFinite(minY) && isFinite(maxX) && isFinite(maxY)
            ? {
                "left": minX,
                "top": minY,
                "right": maxX,
                "bottom": maxY
            }
            : null
    };
}

function _vectorAngleDegrees(dx, dy) {
    return Math.atan2(dy, dx) * 180.0 / Math.PI;
}

function _normalizeVector(dx, dy) {
    var length = Math.sqrt(dx * dx + dy * dy);
    if (length <= 1e-9)
        return {"dx": 1.0, "dy": 0.0};
    return {"dx": dx / length, "dy": dy / length};
}

function cubicDerivative(t, p0, p1, p2, p3) {
    var inv = 1.0 - t;
    return 3.0 * inv * inv * (p1 - p0)
        + 6.0 * inv * t * (p2 - p1)
        + 3.0 * t * t * (p3 - p2);
}

function bezierPointTangent(t, x0, y0, x1, y1, x2, y2, x3, y3) {
    var px = cubicPoint(t, x0, x1, x2, x3);
    var py = cubicPoint(t, y0, y1, y2, y3);
    var dx = cubicDerivative(t, x0, x1, x2, x3);
    var dy = cubicDerivative(t, y0, y1, y2, y3);
    var normalized = _normalizeVector(dx, dy);
    return {
        "x": px,
        "y": py,
        "dx": normalized.dx,
        "dy": normalized.dy,
        "angle": _vectorAngleDegrees(normalized.dx, normalized.dy)
    };
}

function pointTangentAlongBezier(x0, y0, x1, y1, x2, y2, x3, y3, fraction, segments) {
    var sampleCount = Math.max(16, segments || 32);
    var clampedFraction = clamp(fraction, 0.0, 1.0);
    var samples = [];
    var totalLength = 0.0;
    var prev = bezierPointTangent(0.0, x0, y0, x1, y1, x2, y2, x3, y3);
    samples.push({"t": 0.0, "point": prev, "length": 0.0});
    for (var i = 1; i <= sampleCount; i++) {
        var t = i / sampleCount;
        var point = bezierPointTangent(t, x0, y0, x1, y1, x2, y2, x3, y3);
        totalLength += Math.sqrt(Math.pow(point.x - prev.x, 2) + Math.pow(point.y - prev.y, 2));
        samples.push({"t": t, "point": point, "length": totalLength});
        prev = point;
    }
    if (totalLength <= 1e-9)
        return samples[samples.length - 1].point;
    var targetLength = totalLength * clampedFraction;
    for (var index = 1; index < samples.length; index++) {
        var current = samples[index];
        if (current.length + 1e-9 < targetLength)
            continue;
        var previous = samples[index - 1];
        var span = current.length - previous.length;
        if (span <= 1e-9)
            return current.point;
        var localFraction = (targetLength - previous.length) / span;
        var interpolatedT = previous.t + (current.t - previous.t) * localFraction;
        return bezierPointTangent(interpolatedT, x0, y0, x1, y1, x2, y2, x3, y3);
    }
    return samples[samples.length - 1].point;
}

function pointTangentAlongPolyline(points, fraction) {
    if (!points || points.length === 0)
        return null;
    if (points.length === 1)
        return {"x": points[0].x, "y": points[0].y, "dx": 1.0, "dy": 0.0, "angle": 0.0};
    var segments = [];
    var totalLength = 0.0;
    for (var i = 1; i < points.length; i++) {
        var a = points[i - 1];
        var b = points[i];
        var dx = b.x - a.x;
        var dy = b.y - a.y;
        var length = Math.sqrt(dx * dx + dy * dy);
        segments.push({"a": a, "b": b, "dx": dx, "dy": dy, "length": length});
        totalLength += length;
    }
    if (totalLength <= 1e-9) {
        var lastPoint = points[points.length - 1];
        return {"x": lastPoint.x, "y": lastPoint.y, "dx": 1.0, "dy": 0.0, "angle": 0.0};
    }
    var clampedFraction = clamp(fraction, 0.0, 1.0);
    var targetLength = totalLength * clampedFraction;
    var traversed = 0.0;
    for (var index = 0; index < segments.length; index++) {
        var segment = segments[index];
        var nextLength = traversed + segment.length;
        if (segment.length <= 1e-9) {
            traversed = nextLength;
            continue;
        }
        if (targetLength - nextLength > 1e-9) {
            traversed = nextLength;
            continue;
        }
        var segmentFraction = (targetLength - traversed) / segment.length;
        var normalized = _normalizeVector(segment.dx, segment.dy);
        return {
            "x": segment.a.x + segment.dx * segmentFraction,
            "y": segment.a.y + segment.dy * segmentFraction,
            "dx": normalized.dx,
            "dy": normalized.dy,
            "angle": _vectorAngleDegrees(normalized.dx, normalized.dy)
        };
    }
    var tail = segments[segments.length - 1];
    var tailNormalized = _normalizeVector(tail.dx, tail.dy);
    return {
        "x": tail.b.x,
        "y": tail.b.y,
        "dx": tailNormalized.dx,
        "dy": tailNormalized.dy,
        "angle": _vectorAngleDegrees(tailNormalized.dx, tailNormalized.dy)
    };
}

function edgeAnchor(geometry, fraction) {
    if (!geometry)
        return null;
    if (geometry.route === "pipe")
        return pointTangentAlongPolyline(geometry.pipe_points || [], fraction);
    return pointTangentAlongBezier(
        geometry.sx,
        geometry.sy,
        geometry.c1x,
        geometry.c1y,
        geometry.c2x,
        geometry.c2y,
        geometry.tx,
        geometry.ty,
        fraction,
        40
    );
}

function rectsIntersect(a, b) {
    if (!a || !b)
        return false;
    return Number(a.left) <= Number(b.right) + 1e-6
        && Number(a.right) + 1e-6 >= Number(b.left)
        && Number(a.top) <= Number(b.bottom) + 1e-6
        && Number(a.bottom) + 1e-6 >= Number(b.top);
}

function _crossProduct(ax, ay, bx, by) {
    return ax * by - ay * bx;
}

function segmentIntersection(a1, a2, b1, b2) {
    var p = _normalizedPoint(a1);
    var p2 = _normalizedPoint(a2);
    var q = _normalizedPoint(b1);
    var q2 = _normalizedPoint(b2);
    if (!p || !p2 || !q || !q2)
        return null;
    var rx = p2.x - p.x;
    var ry = p2.y - p.y;
    var sx = q2.x - q.x;
    var sy = q2.y - q.y;
    var denominator = _crossProduct(rx, ry, sx, sy);
    if (Math.abs(denominator) <= 1e-9)
        return null;
    var qpx = q.x - p.x;
    var qpy = q.y - p.y;
    var t = _crossProduct(qpx, qpy, sx, sy) / denominator;
    var u = _crossProduct(qpx, qpy, rx, ry) / denominator;
    if (t < -1e-6 || t > 1.0 + 1e-6 || u < -1e-6 || u > 1.0 + 1e-6)
        return null;
    t = clamp(t, 0.0, 1.0);
    u = clamp(u, 0.0, 1.0);
    return {
        "x": p.x + rx * t,
        "y": p.y + ry * t,
        "tA": t,
        "tB": u
    };
}

function distanceNearPolylineEndpoints(distanceAlong, totalLength, margin) {
    var distance = Number(distanceAlong);
    var total = Number(totalLength);
    var threshold = Math.max(0.0, Number(margin || 0.0));
    if (!isFinite(distance) || !isFinite(total))
        return true;
    return distance <= threshold + 1e-6 || distance >= total - threshold - 1e-6;
}

function mergeBreakRanges(ranges, mergeGap, totalLength) {
    var sourceRanges = ranges || [];
    var maximumLength = Number(totalLength);
    var clamped = [];
    var i;

    for (i = 0; i < sourceRanges.length; i++) {
        var range = sourceRanges[i];
        if (!range)
            continue;
        var startDistance = Number(range.startDistance);
        var endDistance = Number(range.endDistance);
        if (!isFinite(startDistance) || !isFinite(endDistance))
            continue;
        if (endDistance < startDistance) {
            var swap = startDistance;
            startDistance = endDistance;
            endDistance = swap;
        }
        if (isFinite(maximumLength)) {
            startDistance = clamp(startDistance, 0.0, maximumLength);
            endDistance = clamp(endDistance, 0.0, maximumLength);
        }
        if (endDistance - startDistance <= 1e-6)
            continue;
        clamped.push({
            "startDistance": startDistance,
            "endDistance": endDistance
        });
    }

    clamped.sort(function(a, b) {
        if (Math.abs(a.startDistance - b.startDistance) > 1e-6)
            return a.startDistance - b.startDistance;
        return a.endDistance - b.endDistance;
    });

    var merged = [];
    var mergeDistance = Math.max(0.0, Number(mergeGap || 0.0));
    for (i = 0; i < clamped.length; i++) {
        var current = clamped[i];
        if (!merged.length) {
            merged.push(current);
            continue;
        }
        var last = merged[merged.length - 1];
        if (current.startDistance <= last.endDistance + mergeDistance + 1e-6) {
            last.endDistance = Math.max(last.endDistance, current.endDistance);
        } else {
            merged.push(current);
        }
    }
    return merged;
}

function normalizeCardinalSide(sideLike, fallback) {
    var normalized = String(sideLike || "").trim().toLowerCase();
    if (normalized === "top" || normalized === "right" || normalized === "bottom" || normalized === "left")
        return normalized;
    return String(fallback || "").trim().toLowerCase();
}

function flowAnchorNormal(sideLike) {
    var side = normalizeCardinalSide(sideLike, "");
    if (side === "top")
        return {"x": 0.0, "y": -1.0};
    if (side === "right")
        return {"x": 1.0, "y": 0.0};
    if (side === "bottom")
        return {"x": 0.0, "y": 1.0};
    if (side === "left")
        return {"x": -1.0, "y": 0.0};
    return {"x": 0.0, "y": 0.0};
}

function _axisValuePush(values, value) {
    var numeric = Number(value);
    if (!isFinite(numeric))
        return;
    for (var i = 0; i < values.length; i++) {
        if (Math.abs(values[i] - numeric) <= 0.001)
            return;
    }
    values.push(numeric);
}

function _sortedNumeric(values) {
    var next = (values || []).slice();
    next.sort(function(a, b) { return a - b; });
    return next;
}

function _axisGapOrOverlapInterval(aLow, aHigh, bLow, bHigh) {
    if (aHigh <= bLow)
        return {"low": aHigh, "high": bLow};
    if (bHigh <= aLow)
        return {"low": bHigh, "high": aLow};
    var overlapLow = Math.max(aLow, bLow);
    var overlapHigh = Math.min(aHigh, bHigh);
    if (overlapLow <= overlapHigh)
        return {"low": overlapLow, "high": overlapHigh};
    return null;
}

function _axisIntervalCandidates(values, preferred, interval, laneBias) {
    if (!interval)
        return;
    var low = Number(interval.low);
    var high = Number(interval.high);
    var center = (low + high) * 0.5;
    var biased = clamp(center + Number(laneBias || 0.0) * 0.35, low, high);
    _axisValuePush(values, center);
    preferred.push(center);
    if (Math.abs(biased - center) > 0.001) {
        _axisValuePush(values, biased);
        preferred.unshift(biased);
    }
}

function _flowPipeStubLength(sourcePoint, targetPoint) {
    var dx = Math.abs(Number(targetPoint.x) - Number(sourcePoint.x));
    var dy = Math.abs(Number(targetPoint.y) - Number(sourcePoint.y));
    var dominantGap = Math.max(dx, dy);
    return Math.min(72.0, Math.max(32.0, Math.max(44.0, dominantGap * 0.2)));
}

function _flowPipeStubPoint(point, sideLike, stubLength) {
    var normal = flowAnchorNormal(sideLike);
    return {
        "x": Number(point.x) + normal.x * stubLength,
        "y": Number(point.y) + normal.y * stubLength
    };
}

function _flowPipeCandidateAxes(sourcePoint, targetPoint, sourceStub, targetStub, sourceBounds, targetBounds, laneBias, clearance) {
    var xValues = [
        Number(sourcePoint.x),
        Number(targetPoint.x),
        Number(sourceStub.x),
        Number(targetStub.x),
        (Number(sourceStub.x) + Number(targetStub.x)) * 0.5
    ];
    var yValues = [
        Number(sourcePoint.y),
        Number(targetPoint.y),
        Number(sourceStub.y),
        Number(targetStub.y),
        (Number(sourceStub.y) + Number(targetStub.y)) * 0.5
    ];
    var preferredXs = [];
    var preferredYs = [];

    if (sourceBounds && targetBounds) {
        var leftBound = Math.min(Number(sourceBounds.left), Number(targetBounds.left));
        var rightBound = Math.max(Number(sourceBounds.right), Number(targetBounds.right));
        var topBound = Math.min(Number(sourceBounds.top), Number(targetBounds.top));
        var bottomBound = Math.max(Number(sourceBounds.bottom), Number(targetBounds.bottom));
        _axisValuePush(xValues, leftBound - clearance - Math.max(0.0, laneBias));
        _axisValuePush(xValues, rightBound + clearance + Math.max(0.0, -laneBias));
        _axisValuePush(yValues, topBound - clearance - Math.max(0.0, laneBias));
        _axisValuePush(yValues, bottomBound + clearance + Math.max(0.0, -laneBias));
        _axisIntervalCandidates(
            xValues,
            preferredXs,
            _axisGapOrOverlapInterval(
                Number(sourceBounds.left),
                Number(sourceBounds.right),
                Number(targetBounds.left),
                Number(targetBounds.right)
            ),
            laneBias
        );
        _axisIntervalCandidates(
            yValues,
            preferredYs,
            _axisGapOrOverlapInterval(
                Number(sourceBounds.top),
                Number(sourceBounds.bottom),
                Number(targetBounds.top),
                Number(targetBounds.bottom)
            ),
            laneBias
        );
    }

    return {
        "xValues": _sortedNumeric(xValues),
        "yValues": _sortedNumeric(yValues),
        "preferredXs": preferredXs,
        "preferredYs": preferredYs
    };
}

function _pointInsideBounds(point, bounds) {
    if (!bounds)
        return false;
    return Number(bounds.left) + 0.001 < Number(point.x)
        && Number(point.x) < Number(bounds.right) - 0.001
        && Number(bounds.top) + 0.001 < Number(point.y)
        && Number(point.y) < Number(bounds.bottom) - 0.001;
}

function _segmentClear(start, end, obstacles) {
    var x1 = Number(start.x);
    var y1 = Number(start.y);
    var x2 = Number(end.x);
    var y2 = Number(end.y);
    var sourceObstacles = obstacles || [];

    if (Math.abs(x1 - x2) <= 0.001) {
        var x = x1;
        var lowY = Math.min(y1, y2);
        var highY = Math.max(y1, y2);
        for (var i = 0; i < sourceObstacles.length; i++) {
            var bounds = sourceObstacles[i];
            if (!bounds)
                continue;
            if (!(Number(bounds.left) + 0.001 < x && x < Number(bounds.right) - 0.001))
                continue;
            var overlapLowY = Math.max(lowY, Number(bounds.top) + 0.001);
            var overlapHighY = Math.min(highY, Number(bounds.bottom) - 0.001);
            if (overlapLowY < overlapHighY)
                return false;
        }
        return true;
    }

    if (Math.abs(y1 - y2) <= 0.001) {
        var y = y1;
        var lowX = Math.min(x1, x2);
        var highX = Math.max(x1, x2);
        for (var j = 0; j < sourceObstacles.length; j++) {
            var obstacle = sourceObstacles[j];
            if (!obstacle)
                continue;
            if (!(Number(obstacle.top) + 0.001 < y && y < Number(obstacle.bottom) - 0.001))
                continue;
            var overlapLowX = Math.max(lowX, Number(obstacle.left) + 0.001);
            var overlapHighX = Math.min(highX, Number(obstacle.right) - 0.001);
            if (overlapLowX < overlapHighX)
                return false;
        }
        return true;
    }

    return false;
}

function _simplifyOrthogonalPoints(points) {
    var deduped = [];
    var i;
    for (i = 0; i < (points || []).length; i++) {
        var point = points[i];
        if (!point)
            continue;
        if (deduped.length > 0) {
            var prev = deduped[deduped.length - 1];
            if (Math.abs(Number(prev.x) - Number(point.x)) <= 0.001
                && Math.abs(Number(prev.y) - Number(point.y)) <= 0.001) {
                continue;
            }
        }
        deduped.push({"x": Number(point.x), "y": Number(point.y)});
    }

    var simplified = [];
    for (i = 0; i < deduped.length; i++) {
        var current = deduped[i];
        if (simplified.length < 2) {
            simplified.push(current);
            continue;
        }
        var prevPoint = simplified[simplified.length - 1];
        var prevPrevPoint = simplified[simplified.length - 2];
        var sameX = Math.abs(Number(prevPrevPoint.x) - Number(prevPoint.x)) <= 0.001
            && Math.abs(Number(prevPoint.x) - Number(current.x)) <= 0.001;
        var sameY = Math.abs(Number(prevPrevPoint.y) - Number(prevPoint.y)) <= 0.001
            && Math.abs(Number(prevPoint.y) - Number(current.y)) <= 0.001;
        if (sameX || sameY)
            simplified[simplified.length - 1] = current;
        else
            simplified.push(current);
    }
    return simplified;
}

function _polylineScore(points, preferredXs, preferredYs) {
    var bends = Math.max(0, (points || []).length - 2);
    var length = 0.0;
    var lanePenalty = 0.0;
    for (var i = 1; i < (points || []).length; i++) {
        var start = points[i - 1];
        var end = points[i];
        length += Math.abs(Number(end.x) - Number(start.x)) + Math.abs(Number(end.y) - Number(start.y));
        if (Math.abs(Number(end.x) - Number(start.x)) <= 0.001 && (preferredXs || []).length > 0) {
            var bestXPenalty = Number.POSITIVE_INFINITY;
            for (var px = 0; px < preferredXs.length; px++)
                bestXPenalty = Math.min(bestXPenalty, Math.abs(Number(start.x) - Number(preferredXs[px])));
            lanePenalty += bestXPenalty;
        } else if (Math.abs(Number(end.y) - Number(start.y)) <= 0.001 && (preferredYs || []).length > 0) {
            var bestYPenalty = Number.POSITIVE_INFINITY;
            for (var py = 0; py < preferredYs.length; py++)
                bestYPenalty = Math.min(bestYPenalty, Math.abs(Number(start.y) - Number(preferredYs[py])));
            lanePenalty += bestYPenalty;
        }
    }
    return {
        "bends": bends,
        "length": length,
        "lanePenalty": lanePenalty
    };
}

function _scoreLessThan(a, b) {
    if (!b)
        return true;
    if (a.bends !== b.bends)
        return a.bends < b.bends;
    if (Math.abs(a.length - b.length) > 0.001)
        return a.length < b.length;
    return a.lanePenalty < b.lanePenalty - 0.001;
}

function flowPipeRoute(sourcePoint, targetPoint, options) {
    var config = options || {};
    var source = {"x": Number(sourcePoint.x), "y": Number(sourcePoint.y)};
    var target = {"x": Number(targetPoint.x), "y": Number(targetPoint.y)};
    var laneBias = Number(config.laneBias || 0.0);
    var sourceSide = normalizeCardinalSide(config.sourceSide, "right");
    var targetSide = normalizeCardinalSide(config.targetSide, "left");
    var sourceBounds = config.sourceBounds || null;
    var targetBounds = config.targetBounds || null;
    var stubLength = _flowPipeStubLength(source, target);
    var sourceStub = _flowPipeStubPoint(source, sourceSide, stubLength);
    var targetStub = _flowPipeStubPoint(target, targetSide, stubLength);
    var clearance = 56.0 * 0.6 + Math.abs(laneBias) * 0.8;
    var axisModel = _flowPipeCandidateAxes(
        source,
        target,
        sourceStub,
        targetStub,
        sourceBounds,
        targetBounds,
        laneBias,
        clearance
    );
    var obstacles = [];
    if (sourceBounds)
        obstacles.push(sourceBounds);
    if (targetBounds)
        obstacles.push(targetBounds);

    var candidates = [
        [sourceStub, targetStub],
        [sourceStub, {"x": sourceStub.x, "y": targetStub.y}, targetStub],
        [sourceStub, {"x": targetStub.x, "y": sourceStub.y}, targetStub]
    ];
    var xValues = axisModel.xValues;
    var yValues = axisModel.yValues;
    var xIndex;
    var yIndex;
    for (xIndex = 0; xIndex < xValues.length; xIndex++) {
        candidates.push([
            sourceStub,
            {"x": xValues[xIndex], "y": sourceStub.y},
            {"x": xValues[xIndex], "y": targetStub.y},
            targetStub
        ]);
    }
    for (yIndex = 0; yIndex < yValues.length; yIndex++) {
        candidates.push([
            sourceStub,
            {"x": sourceStub.x, "y": yValues[yIndex]},
            {"x": targetStub.x, "y": yValues[yIndex]},
            targetStub
        ]);
    }
    for (xIndex = 0; xIndex < xValues.length; xIndex++) {
        for (yIndex = 0; yIndex < yValues.length; yIndex++) {
            candidates.push([
                sourceStub,
                {"x": xValues[xIndex], "y": sourceStub.y},
                {"x": xValues[xIndex], "y": yValues[yIndex]},
                {"x": targetStub.x, "y": yValues[yIndex]},
                targetStub
            ]);
            candidates.push([
                sourceStub,
                {"x": sourceStub.x, "y": yValues[yIndex]},
                {"x": xValues[xIndex], "y": yValues[yIndex]},
                {"x": xValues[xIndex], "y": targetStub.y},
                targetStub
            ]);
        }
    }

    var bestPoints = null;
    var bestScore = null;
    for (var i = 0; i < candidates.length; i++) {
        var routedPoints = _simplifyOrthogonalPoints(candidates[i]);
        var valid = true;
        for (var p = 1; p < routedPoints.length - 1 && valid; p++) {
            for (var o = 0; o < obstacles.length; o++) {
                if (_pointInsideBounds(routedPoints[p], obstacles[o])) {
                    valid = false;
                    break;
                }
            }
        }
        for (var s = 1; s < routedPoints.length && valid; s++) {
            if (!_segmentClear(routedPoints[s - 1], routedPoints[s], obstacles))
                valid = false;
        }
        if (!valid)
            continue;
        var fullPoints = _simplifyOrthogonalPoints([source].concat(routedPoints).concat([target]));
        var score = _polylineScore(fullPoints, axisModel.preferredXs, axisModel.preferredYs);
        if (_scoreLessThan(score, bestScore)) {
            bestScore = score;
            bestPoints = fullPoints;
        }
    }

    if (bestPoints)
        return bestPoints;
    return _simplifyOrthogonalPoints([
        source,
        sourceStub,
        {"x": sourceStub.x, "y": targetStub.y},
        targetStub,
        target
    ]);
}

function pipeControlHandles(pipePoints) {
    var points = pipePoints || [];
    if (points.length <= 0)
        return {
            "first": {"x": 0.0, "y": 0.0},
            "last": {"x": 0.0, "y": 0.0}
        };
    return {
        "first": points[Math.min(1, points.length - 1)],
        "last": points[Math.max(0, points.length - 2)]
    };
}
