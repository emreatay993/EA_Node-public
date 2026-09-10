import QtQuick 2.15
import QtQuick.Shapes 1.15

Item {
    id: root
    objectName: "graphFlowchartSilhouette"
    property string variant: "process"
    property color fillColor: "#1b1d22"
    property color strokeColor: "#3a3d45"
    property real strokeWidth: 1.0
    property bool gradientActive: false
    property color gradientStartColor: root.fillColor
    property color gradientEndColor: root.fillColor
    property string gradientDirection: "south"
    property bool showPreviewContent: false
    readonly property string outlinePathData: _outlinePathData()
    readonly property string detailPathData: _detailPathData()
    readonly property color outlineFillColor: root.fillColor
    readonly property string normalizedGradientDirection: _normalizedGradientDirection(root.gradientDirection)
    readonly property bool gradientRadial: root.normalizedGradientDirection === "radial"
    readonly property bool multiDocumentVisible: _normalizedVariant() === "multi_document"
    readonly property string multiDocumentBackPathData: root.multiDocumentVisible
        ? _traceMultiDocumentPage(_bounds(), 0.0, 0.0)
        : ""
    readonly property string multiDocumentMiddlePathData: root.multiDocumentVisible
        ? _traceMultiDocumentPage(_bounds(), 5.0, 5.0)
        : ""

    function _normalizedVariant() {
        var normalized = String(root.variant || "").trim().toLowerCase();
        if (normalized === "start" || normalized === "end" || normalized === "process" || normalized === "decision"
            || normalized === "document" || normalized === "connector" || normalized === "input_output"
            || normalized === "predefined_process" || normalized === "database" || normalized === "card"
            || normalized === "callout" || normalized === "multi_document" || normalized === "tick"
            || normalized === "timestamp" || normalized === "message" || normalized === "isometric_cube"
            || normalized === "cube" || normalized === "actor" || normalized === "star" || normalized === "x") {
            return normalized;
        }
        return "process";
    }

    function _normalizedGradientDirection(value) {
        var normalized = String(value || "").trim().toLowerCase();
        if (normalized === "north" || normalized === "east" || normalized === "south"
            || normalized === "west" || normalized === "radial") {
            return normalized;
        }
        return "south";
    }

    function _gradientX1(bounds) {
        if (root.normalizedGradientDirection === "west")
            return bounds.right;
        return bounds.left;
    }

    function _gradientY1(bounds) {
        if (root.normalizedGradientDirection === "north")
            return bounds.bottom;
        return bounds.top;
    }

    function _gradientX2(bounds) {
        if (root.normalizedGradientDirection === "east")
            return bounds.right;
        if (root.normalizedGradientDirection === "west")
            return bounds.left;
        return bounds.left;
    }

    function _gradientY2(bounds) {
        if (root.normalizedGradientDirection === "south")
            return bounds.bottom;
        if (root.normalizedGradientDirection === "north")
            return bounds.top;
        return bounds.top;
    }

    function _fmt(value) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = 0.0;
        return numeric.toFixed(3);
    }

    function _bounds() {
        var inset = Math.max(0.5, root.strokeWidth * 0.5);
        var left = inset;
        var top = inset;
        var right = Math.max(left + 1.0, root.width - inset);
        var bottom = Math.max(top + 1.0, root.height - inset);
        return {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "widthValue": Math.max(1.0, right - left),
            "heightValue": Math.max(1.0, bottom - top),
            "centerX": (left + right) * 0.5,
            "centerY": (top + bottom) * 0.5
        };
    }

    function _moveTo(x, y) {
        return "M " + _fmt(x) + " " + _fmt(y);
    }

    function _lineTo(x, y) {
        return "L " + _fmt(x) + " " + _fmt(y);
    }

    function _cubicTo(c1x, c1y, c2x, c2y, x, y) {
        return "C "
            + _fmt(c1x) + " " + _fmt(c1y) + " "
            + _fmt(c2x) + " " + _fmt(c2y) + " "
            + _fmt(x) + " " + _fmt(y);
    }

    function _arcTo(rx, ry, largeArc, sweep, x, y) {
        return "A "
            + _fmt(rx) + " " + _fmt(ry) + " 0 "
            + (largeArc ? "1" : "0") + " "
            + (sweep ? "1" : "0") + " "
            + _fmt(x) + " " + _fmt(y);
    }

    function _closePath() {
        return "Z";
    }

    function _boundsFromEdges(left, top, right, bottom) {
        var safeLeft = Math.min(left, right - 1.0);
        var safeTop = Math.min(top, bottom - 1.0);
        var safeRight = Math.max(safeLeft + 1.0, right);
        var safeBottom = Math.max(safeTop + 1.0, bottom);
        return {
            "left": safeLeft,
            "top": safeTop,
            "right": safeRight,
            "bottom": safeBottom,
            "widthValue": Math.max(1.0, safeRight - safeLeft),
            "heightValue": Math.max(1.0, safeBottom - safeTop),
            "centerX": (safeLeft + safeRight) * 0.5,
            "centerY": (safeTop + safeBottom) * 0.5
        };
    }

    function _insetBounds(bounds, leftInset, topInset, rightInset, bottomInset) {
        return _boundsFromEdges(
            bounds.left + leftInset,
            bounds.top + topInset,
            bounds.right - rightInset,
            bounds.bottom - bottomInset
        );
    }

    function _offsetBounds(bounds, dx, dy) {
        return _boundsFromEdges(
            bounds.left + dx,
            bounds.top + dy,
            bounds.right + dx,
            bounds.bottom + dy
        );
    }

    function _traceRect(bounds) {
        return [
            _moveTo(bounds.left, bounds.top),
            _lineTo(bounds.right, bounds.top),
            _lineTo(bounds.right, bounds.bottom),
            _lineTo(bounds.left, bounds.bottom),
            _closePath()
        ].join(" ");
    }

    function _traceTerminator(bounds) {
        var radius = Math.min(bounds.heightValue * 0.5, bounds.widthValue * 0.5);
        return [
            _moveTo(bounds.left + radius, bounds.top),
            _lineTo(bounds.right - radius, bounds.top),
            _arcTo(radius, radius, false, true, bounds.right - radius, bounds.bottom),
            _lineTo(bounds.left + radius, bounds.bottom),
            _arcTo(radius, radius, false, true, bounds.left + radius, bounds.top),
            _closePath()
        ].join(" ");
    }

    function _traceDecision(bounds) {
        return [
            _moveTo(bounds.centerX, bounds.top),
            _lineTo(bounds.right, bounds.centerY),
            _lineTo(bounds.centerX, bounds.bottom),
            _lineTo(bounds.left, bounds.centerY),
            _closePath()
        ].join(" ");
    }

    function _traceDocument(bounds) {
        var waveDepth = Math.min(bounds.heightValue * 0.11, 10.0 + root.strokeWidth * 1.5);
        var waveBase = bounds.bottom - waveDepth * 0.58;
        var waveCrest = bounds.bottom - waveDepth * 1.08;
        var waveTrough = bounds.bottom - waveDepth * 0.12;
        return [
            _moveTo(bounds.left, bounds.top),
            _lineTo(bounds.right, bounds.top),
            _lineTo(bounds.right, waveBase),
            _cubicTo(
                bounds.right - bounds.widthValue * 0.17,
                waveTrough,
                bounds.left + bounds.widthValue * 0.7,
                waveTrough,
                bounds.left + bounds.widthValue * 0.52,
                waveBase - waveDepth * 0.34
            ),
            _cubicTo(
                bounds.left + bounds.widthValue * 0.33,
                waveCrest,
                bounds.left + bounds.widthValue * 0.14,
                waveCrest,
                bounds.left,
                waveBase
            ),
            _closePath()
        ].join(" ");
    }

    function _traceConnector(bounds) {
        var rx = bounds.widthValue * 0.5;
        var ry = bounds.heightValue * 0.5;
        return [
            _moveTo(bounds.centerX - rx, bounds.centerY),
            _arcTo(rx, ry, true, false, bounds.centerX + rx, bounds.centerY),
            _arcTo(rx, ry, true, false, bounds.centerX - rx, bounds.centerY),
            _closePath()
        ].join(" ");
    }

    function _traceInputOutput(bounds) {
        var slant = Math.min(bounds.widthValue * 0.13, bounds.heightValue * 0.26);
        return [
            _moveTo(bounds.left + slant, bounds.top),
            _lineTo(bounds.right, bounds.top),
            _lineTo(bounds.right - slant, bounds.bottom),
            _lineTo(bounds.left, bounds.bottom),
            _closePath()
        ].join(" ");
    }

    function _traceDatabaseShell(bounds) {
        var rx = bounds.widthValue * 0.5;
        var cap = Math.min(bounds.heightValue * 0.13, 14.0 + root.strokeWidth);
        var topCy = bounds.top + cap;
        var bottomCy = bounds.bottom - cap;
        return [
            _moveTo(bounds.left, topCy),
            _arcTo(rx, cap, false, true, bounds.right, topCy),
            _lineTo(bounds.right, bottomCy),
            _arcTo(rx, cap, false, true, bounds.left, bottomCy),
            _lineTo(bounds.left, topCy),
            _closePath()
        ].join(" ");
    }

    function _tracePredefinedBars(bounds) {
        var barInset = Math.min(bounds.widthValue * 0.1, 16.0 + Math.max(0.5, root.strokeWidth * 0.5));
        return [
            _moveTo(bounds.left + barInset, bounds.top),
            _lineTo(bounds.left + barInset, bounds.bottom),
            _moveTo(bounds.right - barInset, bounds.top),
            _lineTo(bounds.right - barInset, bounds.bottom)
        ].join(" ");
    }

    function _traceDatabaseDetails(bounds) {
        var rx = bounds.widthValue * 0.5;
        var cap = Math.min(bounds.heightValue * 0.13, 14.0 + root.strokeWidth);
        var topCy = bounds.top + cap;
        var bottomCy = bounds.bottom - cap;
        return [
            _moveTo(bounds.left, topCy),
            _arcTo(rx, cap, true, false, bounds.right, topCy),
            _arcTo(rx, cap, true, false, bounds.left, topCy),
            _moveTo(bounds.right, bottomCy),
            _arcTo(rx, cap, false, true, bounds.left, bottomCy)
        ].join(" ");
    }

    function _traceCard(bounds) {
        var cut = Math.min(
            bounds.widthValue * 0.2,
            bounds.heightValue * 0.14,
            24.0 + root.strokeWidth * 2.0
        );
        return [
            _moveTo(bounds.left, bounds.top),
            _lineTo(bounds.right - cut, bounds.top),
            _lineTo(bounds.right, bounds.top + cut),
            _lineTo(bounds.right, bounds.bottom),
            _lineTo(bounds.left, bounds.bottom),
            _closePath()
        ].join(" ");
    }

    function _traceCallout(bounds) {
        var tailWidth = Math.min(bounds.widthValue * 0.18, 24.0 + root.strokeWidth * 2.0);
        var tailHeight = Math.min(bounds.heightValue * 0.3, 30.0 + root.strokeWidth * 2.0);
        var bodyBottom = bounds.bottom - tailHeight;
        var tailLeft = bounds.left + bounds.widthValue * 0.5;
        var tailTip = bounds.left + bounds.widthValue * 0.5;
        return [
            _moveTo(bounds.left, bounds.top),
            _lineTo(bounds.right, bounds.top),
            _lineTo(bounds.right, bodyBottom),
            _lineTo(tailLeft + tailWidth, bodyBottom),
            _lineTo(tailTip, bounds.bottom),
            _lineTo(tailLeft, bodyBottom),
            _lineTo(bounds.left, bodyBottom),
            _closePath()
        ].join(" ");
    }

    function _traceTick(bounds) {
        var sx = bounds.widthValue / 84.4;
        var sy = bounds.heightValue / 97.54;
        function x(value) {
            return bounds.left + value * sx;
        }
        function y(value) {
            return bounds.top + value * sy;
        }
        return [
            _moveTo(x(0.36), y(66.69)),
            _arcTo(12.0 * sx, 12.0 * sy, false, true, x(16.36), y(58.69)),
            _arcTo(20.0 * sx, 20.0 * sy, false, true, x(26.36), y(69.69)),
            _arcTo(200.0 * sx, 200.0 * sy, false, true, x(63.36), y(5.69)),
            _arcTo(18.0 * sx, 18.0 * sy, false, true, x(80.36), y(1.69)),
            _arcTo(4.5 * sx, 4.5 * sy, false, true, x(83.36), y(8.69)),
            _arcTo(230.0 * sx, 230.0 * sy, false, false, x(35.36), y(94.69)),
            _arcTo(20.0 * sx, 20.0 * sy, false, true, x(17.36), y(94.69)),
            _arcTo(100.0 * sx, 100.0 * sy, false, false, x(0.36), y(68.69)),
            _arcTo(2.0 * sx, 2.0 * sy, false, true, x(0.36), y(66.69)),
            _closePath()
        ].join(" ");
    }

    function _traceMessageDetails(bounds) {
        var left = bounds.left;
        var right = bounds.right;
        var flapY = bounds.top + bounds.heightValue * 0.47;
        return [
            _moveTo(left, bounds.top),
            _lineTo(bounds.centerX, flapY),
            _lineTo(right, bounds.top)
        ].join(" ");
    }

    function _traceMultiDocumentPage(bounds, offsetX, offsetY) {
        var sx = bounds.widthValue / 88.0;
        var sy = bounds.heightValue / 60.28;
        function x(value) {
            return bounds.left + value * sx;
        }
        function y(value) {
            return bounds.top + value * sy;
        }
        return [
            _moveTo(x(10.0 - offsetX), y(5.0 + offsetY)),
            _arcTo(5.0 * sx, 5.0 * sy, false, true, x(15.0 - offsetX), y(0.0 + offsetY)),
            _lineTo(x(83.0 - offsetX), y(0.0 + offsetY)),
            _arcTo(5.0 * sx, 5.0 * sy, false, true, x(88.0 - offsetX), y(5.0 + offsetY)),
            _lineTo(x(88.0 - offsetX), y(45.0 + offsetY)),
            _arcTo(50.0 * sx, 50.0 * sy, false, false, x(49.0 - offsetX), y(45.0 + offsetY)),
            _arcTo(50.0 * sx, 50.0 * sy, false, true, x(10.0 - offsetX), y(45.0 + offsetY)),
            _closePath()
        ].join(" ");
    }

    function _traceMultiDocumentOutline(bounds) {
        return _traceMultiDocumentPage(bounds, 10.0, 10.0);
    }

    function _traceIsometricCube(bounds) {
        var w = bounds.widthValue;
        var h = bounds.heightValue;
        var isoAngle = 15.0 * Math.PI / 200.0;
        var isoH = Math.min(w * Math.tan(isoAngle), h * 0.5);
        var topX = bounds.centerX;
        var topY = bounds.top;
        var rightX = bounds.right;
        var upperY = bounds.top + isoH;
        var rightBottomY = bounds.bottom - isoH;
        var bottomX = bounds.centerX;
        var bottomY = bounds.bottom;
        var leftX = bounds.left;
        var leftBottomY = rightBottomY;
        return [
            _moveTo(topX, topY),
            _lineTo(rightX, upperY),
            _lineTo(rightX, rightBottomY),
            _lineTo(bottomX, bottomY),
            _lineTo(leftX, leftBottomY),
            _lineTo(leftX, upperY),
            _closePath()
        ].join(" ");
    }

    function _traceIsometricCubeDetails(bounds) {
        var w = bounds.widthValue;
        var h = bounds.heightValue;
        var isoAngle = 15.0 * Math.PI / 200.0;
        var isoH = Math.min(w * Math.tan(isoAngle), h * 0.5);
        var rightX = bounds.right;
        var upperY = bounds.top + isoH;
        var bottomX = bounds.centerX;
        var bottomY = bounds.bottom;
        var leftX = bounds.left;
        var midY = bounds.top + isoH * 2.0;
        return [
            _moveTo(leftX, upperY),
            _lineTo(bottomX, midY),
            _lineTo(rightX, upperY),
            _moveTo(bottomX, midY),
            _lineTo(bottomX, bottomY)
        ].join(" ");
    }

    function _cubeDepth(bounds) {
        return Math.min(bounds.widthValue * 0.2, bounds.heightValue * 0.2);
    }

    function _traceCube(bounds) {
        var d = _cubeDepth(bounds);
        return [
            _moveTo(bounds.left, bounds.top + d),
            _lineTo(bounds.left + d, bounds.top),
            _lineTo(bounds.right, bounds.top),
            _lineTo(bounds.right, bounds.bottom - d),
            _lineTo(bounds.right - d, bounds.bottom),
            _lineTo(bounds.left, bounds.bottom),
            _closePath()
        ].join(" ");
    }

    function _traceCubeDetails(bounds) {
        var d = _cubeDepth(bounds);
        var innerX = bounds.right - d;
        var innerY = bounds.top + d;
        return [
            _moveTo(bounds.left, innerY),
            _lineTo(innerX, innerY),
            _lineTo(bounds.right, bounds.top),
            _moveTo(innerX, innerY),
            _lineTo(innerX, bounds.bottom)
        ].join(" ");
    }

    function _actorHeadRadius(bounds) {
        return Math.min(bounds.widthValue * 0.20, bounds.heightValue * 0.14);
    }

    function _actorHeadCenterY(bounds, headRadius) {
        return bounds.top + headRadius * 1.15;
    }

    function _traceActorOutline(bounds) {
        var headRadius = _actorHeadRadius(bounds);
        var headCenterY = _actorHeadCenterY(bounds, headRadius);
        var cx = bounds.centerX;
        return [
            _moveTo(cx - headRadius, headCenterY),
            _arcTo(headRadius, headRadius, false, true, cx + headRadius, headCenterY),
            _arcTo(headRadius, headRadius, false, true, cx - headRadius, headCenterY),
            _closePath()
        ].join(" ");
    }

    function _traceActorDetails(bounds) {
        var headRadius = _actorHeadRadius(bounds);
        var headCenterY = _actorHeadCenterY(bounds, headRadius);
        var cx = bounds.centerX;
        var neckGap = Math.max(1.5, headRadius * 0.22);
        var neckY = headCenterY + headRadius + neckGap;
        var bottomInset = Math.max(4.0, headRadius * 0.55);
        var feetY = bounds.bottom - bottomInset;
        var usableHeight = Math.max(1.0, feetY - bounds.top);
        var hipY = bounds.top + usableHeight * 0.62;
        var torsoHeight = Math.max(1.0, hipY - neckY);
        var shoulderY = neckY + torsoHeight * 0.10;
        var armEndY = neckY + torsoHeight * 0.85;
        var armSpan = bounds.widthValue * 0.30;
        var footSpread = bounds.widthValue * 0.18;
        return [
            _moveTo(cx, neckY),
            _lineTo(cx, hipY),
            _moveTo(cx, shoulderY),
            _lineTo(cx - armSpan, armEndY),
            _moveTo(cx, shoulderY),
            _lineTo(cx + armSpan, armEndY),
            _moveTo(cx, hipY),
            _lineTo(cx - footSpread, feetY),
            _moveTo(cx, hipY),
            _lineTo(cx + footSpread, feetY)
        ].join(" ");
    }

    function _traceStar(bounds) {
        var sx = bounds.widthValue / 95.0;
        var sy = bounds.heightValue / 90.0;
        function x(value) {
            return bounds.left + value * sx;
        }
        function y(value) {
            return bounds.top + value * sy;
        }
        return [
            _moveTo(x(0), y(33)),
            _lineTo(x(36.4), y(33)),
            _lineTo(x(47.5), y(0)),
            _lineTo(x(58.6), y(33)),
            _lineTo(x(95), y(33)),
            _lineTo(x(66), y(55.1)),
            _lineTo(x(77.5), y(90)),
            _lineTo(x(47.5), y(68.4)),
            _lineTo(x(17.5), y(90)),
            _lineTo(x(29), y(55.1)),
            _closePath()
        ].join(" ");
    }

    function _traceX(bounds) {
        var sx = bounds.widthValue / 96.0;
        var sy = bounds.heightValue / 98.0;
        function x(value) {
            return bounds.left + value * sx;
        }
        function y(value) {
            return bounds.top + value * sy;
        }
        return [
            _moveTo(x(0), y(0)),
            _lineTo(x(28), y(0)),
            _lineTo(x(48), y(29)),
            _lineTo(x(68), y(0)),
            _lineTo(x(96), y(0)),
            _lineTo(x(62), y(49)),
            _lineTo(x(96), y(98)),
            _lineTo(x(68), y(98)),
            _lineTo(x(48), y(69)),
            _lineTo(x(28), y(98)),
            _lineTo(x(0), y(98)),
            _lineTo(x(32), y(49)),
            _closePath()
        ].join(" ");
    }

    function _outlinePathData() {
        var bounds = _bounds();
        var variantKey = _normalizedVariant();
        if (variantKey === "timestamp")
            return "";
        if (variantKey === "start" || variantKey === "end")
            return _traceTerminator(bounds);
        if (variantKey === "decision")
            return _traceDecision(bounds);
        if (variantKey === "document")
            return _traceDocument(bounds);
        if (variantKey === "connector")
            return _traceConnector(bounds);
        if (variantKey === "input_output")
            return _traceInputOutput(bounds);
        if (variantKey === "database")
            return _traceDatabaseShell(bounds);
        if (variantKey === "card")
            return _traceCard(bounds);
        if (variantKey === "callout")
            return _traceCallout(bounds);
        if (variantKey === "multi_document")
            return _traceMultiDocumentOutline(bounds);
        if (variantKey === "tick")
            return _traceTick(bounds);
        if (variantKey === "isometric_cube")
            return _traceIsometricCube(bounds);
        if (variantKey === "cube")
            return _traceCube(bounds);
        if (variantKey === "actor")
            return _traceActorOutline(bounds);
        if (variantKey === "star")
            return _traceStar(bounds);
        if (variantKey === "x")
            return _traceX(bounds);
        return _traceRect(bounds);
    }

    function _detailPathData() {
        var bounds = _bounds();
        var variantKey = _normalizedVariant();
        if (variantKey === "predefined_process")
            return _tracePredefinedBars(bounds);
        if (variantKey === "database")
            return _traceDatabaseDetails(bounds);
        if (variantKey === "message")
            return _traceMessageDetails(bounds);
        if (variantKey === "isometric_cube")
            return _traceIsometricCubeDetails(bounds);
        if (variantKey === "cube")
            return _traceCubeDetails(bounds);
        if (variantKey === "actor")
            return _traceActorDetails(bounds);
        return "";
    }

    LinearGradient {
        id: flowchartLinearGradient
        readonly property var b: root._bounds()
        x1: root._gradientX1(b)
        y1: root._gradientY1(b)
        x2: root._gradientX2(b)
        y2: root._gradientY2(b)
        GradientStop { position: 0.0; color: root.gradientStartColor }
        GradientStop { position: 1.0; color: root.gradientEndColor }
    }

    RadialGradient {
        id: flowchartRadialGradient
        readonly property var b: root._bounds()
        centerX: b.centerX
        centerY: b.centerY
        centerRadius: Math.max(b.widthValue, b.heightValue) * 0.5
        focalX: centerX
        focalY: centerY
        GradientStop { position: 0.0; color: root.gradientStartColor }
        GradientStop { position: 1.0; color: root.gradientEndColor }
    }

    Shape {
        id: multiDocumentBackPageShape
        objectName: "graphFlowchartMultiDocumentBackPage"
        anchors.fill: parent
        visible: root.multiDocumentVisible
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.strokeColor
            strokeWidth: Math.max(1.0, root.strokeWidth)
            fillColor: root.gradientActive ? "transparent" : root.outlineFillColor
            fillGradient: root.gradientActive
                ? (root.gradientRadial ? flowchartRadialGradient : flowchartLinearGradient)
                : null
            joinStyle: ShapePath.RoundJoin
            capStyle: ShapePath.RoundCap

            PathSvg {
                path: root.multiDocumentBackPathData
            }
        }
    }

    Shape {
        id: multiDocumentMiddlePageShape
        objectName: "graphFlowchartMultiDocumentMiddlePage"
        anchors.fill: parent
        visible: root.multiDocumentVisible
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.strokeColor
            strokeWidth: Math.max(1.0, root.strokeWidth)
            fillColor: root.gradientActive ? "transparent" : root.outlineFillColor
            fillGradient: root.gradientActive
                ? (root.gradientRadial ? flowchartRadialGradient : flowchartLinearGradient)
                : null
            joinStyle: ShapePath.RoundJoin
            capStyle: ShapePath.RoundCap

            PathSvg {
                path: root.multiDocumentMiddlePathData
            }
        }
    }

    Shape {
        id: outlineShape
        objectName: "graphFlowchartVectorShape"
        anchors.fill: parent
        visible: root.outlinePathData.length > 0
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.strokeColor
            strokeWidth: Math.max(1.0, root.strokeWidth)
            fillColor: root.gradientActive ? "transparent" : root.outlineFillColor
            fillGradient: root.gradientActive
                ? (root.gradientRadial ? flowchartRadialGradient : flowchartLinearGradient)
                : null
            joinStyle: ShapePath.RoundJoin
            capStyle: ShapePath.RoundCap

            PathSvg {
                path: root.outlinePathData
            }
        }
    }

    Shape {
        id: detailShape
        objectName: "graphFlowchartVectorDetails"
        anchors.fill: parent
        visible: root.detailPathData.length > 0
        antialiasing: true
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: root.strokeColor
            strokeWidth: Math.max(1.0, root.strokeWidth)
            fillColor: "transparent"
            joinStyle: ShapePath.RoundJoin
            capStyle: ShapePath.RoundCap

            PathSvg {
                path: root.detailPathData
            }
        }
    }

    Text {
        id: timestampPreviewText
        objectName: "graphFlowchartTimestampPreviewText"
        visible: root.showPreviewContent && root._normalizedVariant() === "timestamp"
        anchors.fill: parent
        anchors.margins: Math.max(2, root.strokeWidth * 2)
        text: "Sun May 24 2026 17:35:45"
        color: root.strokeColor
        font.pixelSize: Math.max(8, Math.min(root.height * 0.34, root.width * 0.09))
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        renderType: Text.CurveRendering
    }
}
