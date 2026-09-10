// Purpose: Keep the grid aligned with the live viewport, using a single GPU draw.
// Map: subsystems/graph_canvas.md
// Tests: tests/test_graph_canvas_grid.py
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQml 2.15
import "GraphCanvasLogic.js" as GraphCanvasLogic
import "CanvasBackgroundStyle.js" as CanvasBackgroundStyle

Item {
    id: root
    property var viewBridge: null
    property string canvasBackgroundVariant: "theme"
    property bool showGrid: true
    property string gridStyle: "lines"
    property string gridRendererPreference: "shader"
    property int _redrawRequestCount: 0
    property bool _viewStateRedrawDirty: false
    property int profileGridUpdateCount: 0
    property real profileLastGridUpdateMs: 0.0
    property real profileLastGridPaintMs: 0.0
    readonly property int profileGridItemCount: effectiveShowGrid ? 1 : 0
    readonly property int profileGridMinorItemCount: 0
    readonly property int profileGridMajorItemCount: 0
    readonly property int profileGridRowCount: 0
    readonly property int profileGridColumnCount: 0
    // Match GraphCanvasWorldLayer immediately; the frame scheduler still
    // coalesces profiling and the software paint work.
    readonly property real _zoom: _normalizedZoom(viewBridge ? viewBridge.zoom_value : 1.0)
    readonly property real _centerX: viewBridge ? viewBridge.center_x : 0.0
    readonly property real _centerY: viewBridge ? viewBridge.center_y : 0.0
    readonly property var themePalette: themeBridge.palette
    readonly property string effectiveBackgroundVariant: CanvasBackgroundStyle.effectiveVariant(root.canvasBackgroundVariant)
    readonly property color backgroundTopColor: root.backgroundFillColor
    readonly property color backgroundBottomColor: root.effectiveBackgroundVariant === "theme"
        ? themePalette.panel_bg
        : root.backgroundFillColor
    readonly property color backgroundFillColor: CanvasBackgroundStyle.fillColor(
        root.canvasBackgroundVariant,
        themePalette
    )
    readonly property color minorGridColor: {
        if (root.effectiveBackgroundVariant === "dark")
            return "#2b2f38";
        if (root.effectiveBackgroundVariant === "light" || root.effectiveBackgroundVariant === "white")
            return "#d9dfe8";
        return themePalette.canvas_minor_grid;
    }
    readonly property color majorGridColor: {
        if (root.effectiveBackgroundVariant === "dark")
            return "#323746";
        if (root.effectiveBackgroundVariant === "light" || root.effectiveBackgroundVariant === "white")
            return "#c0c9d6";
        return themePalette.canvas_major_grid;
    }
    readonly property bool effectiveShowGrid: root.showGrid
    readonly property string effectiveGridStyle: root.gridStyle === "points" ? "points" : "lines"
    // Point sizes are logical pixels, so dots remain legible on high-DPI screens.
    readonly property real minorGridPointSize: 1.25
    readonly property real majorGridPointSize: 2.0
    readonly property color _pointContrastTint: (
        backgroundFillColor.r * 0.2126 + backgroundFillColor.g * 0.7152
        + backgroundFillColor.b * 0.0722) > 0.5
        ? Qt.rgba(0, 0, 0, 0.28) : Qt.rgba(1, 1, 1, 0.24)
    readonly property color pointMinorGridColor: Qt.tint(minorGridColor, _pointContrastTint)
    readonly property color pointMajorGridColor: Qt.tint(majorGridColor, _pointContrastTint)
    readonly property string activeGridRendererKind: root.gridRendererPreference === "canvas"
        || GraphicsInfo.api === GraphicsInfo.Software
        || shaderGridRenderer.status === ShaderEffect.Error ? "canvas" : "shader"
    readonly property string profileGridRendererKind: root.effectiveShowGrid ? root.activeGridRendererKind : "none"
    readonly property bool _useCanvasGridRenderer: root.activeGridRendererKind === "canvas"
    readonly property bool _useShaderGridRenderer: root.activeGridRendererKind === "shader"
    readonly property real _devicePixelRatio: Math.max(1.0, Number(Screen.devicePixelRatio || 1.0))

    function _normalizedZoom(value) {
        var zoom = Number(value);
        if (!isFinite(zoom) || zoom <= 0.0001)
            return 1.0;
        return zoom;
    }

    function _gridStepForZoom(zoomValue) {
        var step = 20.0 * _normalizedZoom(zoomValue);
        if (step < 10.0)
            step = 10.0;
        return step;
    }

    function requestGridRedraw() {
        var startedMs = Date.now();
        root._viewStateRedrawDirty = false;
        root._redrawRequestCount += 1;
        root.profileLastGridUpdateMs = 0.0;
        root.profileLastGridPaintMs = 0.0;
        if (!root.effectiveShowGrid)
            return;
        if (root._useCanvasGridRenderer && gridCanvas) {
            gridCanvas.requestPaint();
            return;
        }
        _recordGridUpdate(startedMs);
    }

    function markViewStateRedrawDirty() {
        root._viewStateRedrawDirty = true;
    }

    function flushViewStateRedraw() {
        if (!root._viewStateRedrawDirty)
            return false;
        requestGridRedraw();
        return true;
    }

    function _currentGridStep() {
        return root._gridStepForZoom(root._zoom);
    }

    function _currentGridPeriod() {
        return root._currentGridStep() * 5.0;
    }

    function _gridAnchorX() {
        return root.width * 0.5 - root._centerX * root._zoom;
    }

    function _gridAnchorY() {
        return root.height * 0.5 - root._centerY * root._zoom;
    }

    function _gridOffsetX(step) {
        var currentStep = _currentGridStep();
        if (step !== undefined)
            currentStep = Number(step);
        if (!(currentStep > 0.0))
            return 0.0;
        return GraphCanvasLogic.normalizedOffset(currentStep, root._gridAnchorX());
    }

    function _gridOffsetY(step) {
        var currentStep = _currentGridStep();
        if (step !== undefined)
            currentStep = Number(step);
        if (!(currentStep > 0.0))
            return 0.0;
        return GraphCanvasLogic.normalizedOffset(currentStep, root._gridAnchorY());
    }

    function _recordGridUpdate(startedMs) {
        root.profileGridUpdateCount += 1;
        root.profileLastGridUpdateMs = Math.max(0.0, Date.now() - Number(startedMs || Date.now()));
    }

    onEffectiveShowGridChanged: requestGridRedraw()
    onGridStyleChanged: requestGridRedraw()
    onCanvasBackgroundVariantChanged: requestGridRedraw()
    onActiveGridRendererKindChanged: requestGridRedraw()
    on_DevicePixelRatioChanged: requestGridRedraw()
    onThemePaletteChanged: requestGridRedraw()
    onWidthChanged: requestGridRedraw()
    onHeightChanged: requestGridRedraw()

    Component.onCompleted: requestGridRedraw()

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: root.backgroundTopColor }
            GradientStop { position: 1.0; color: root.backgroundBottomColor }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundFillColor
    }

    GraphCanvasGridShader {
        id: shaderGridRenderer
        anchors.fill: parent
        visible: root.effectiveShowGrid && root._useShaderGridRenderer
        gridStyle: root.effectiveGridStyle
        minorGridColor: root.effectiveGridStyle === "points" ? root.pointMinorGridColor : root.minorGridColor
        majorGridColor: root.effectiveGridStyle === "points" ? root.pointMajorGridColor : root.majorGridColor
        minorStep: root._currentGridStep()
        majorStep: root._currentGridPeriod()
        minorOffset: Qt.vector2d(root._gridOffsetX(minorStep), root._gridOffsetY(minorStep))
        majorOffset: Qt.vector2d(root._gridOffsetX(majorStep), root._gridOffsetY(majorStep))
        minorPointSize: root.minorGridPointSize * root._devicePixelRatio
        majorPointSize: root.majorGridPointSize * root._devicePixelRatio
        devicePixelRatio: root._devicePixelRatio
    }

    Connections {
        target: root.viewBridge
        function onView_state_changed() {
            // Canvas.requestPaint() coalesces requests at the next frame too.
            // Software rendering must not wait behind the graph's 16 ms timer.
            if (root.effectiveShowGrid && root._useCanvasGridRenderer)
                gridCanvas.requestPaint();
        }
    }

    Canvas {
        id: gridCanvas
        objectName: "graphCanvasGridCanvasFallback"
        anchors.fill: parent
        visible: root.effectiveShowGrid && root._useCanvasGridRenderer
        antialiasing: true

        function drawLineGrid(ctx, minorStep, majorStep) {
            var minorX = root._gridOffsetX(minorStep);
            var minorY = root._gridOffsetY(minorStep);
            var majorX = root._gridOffsetX(majorStep);
            var majorY = root._gridOffsetY(majorStep);

            var lineWidth = 1.0 / root._devicePixelRatio;
            ctx.fillStyle = root.minorGridColor;
            for (var x = minorX; x <= width; x += minorStep)
                ctx.fillRect(x - lineWidth * 0.5, 0, lineWidth, height);
            for (var y = minorY; y <= height; y += minorStep)
                ctx.fillRect(0, y - lineWidth * 0.5, width, lineWidth);

            ctx.fillStyle = root.majorGridColor;
            for (var majorVertical = majorX; majorVertical <= width; majorVertical += majorStep)
                ctx.fillRect(majorVertical - lineWidth * 0.5, 0, lineWidth, height);
            for (var majorHorizontal = majorY; majorHorizontal <= height; majorHorizontal += majorStep)
                ctx.fillRect(0, majorHorizontal - lineWidth * 0.5, width, lineWidth);
        }

        function drawPointGrid(ctx, minorStep, majorStep) {
            var minorX = root._gridOffsetX(minorStep);
            var minorY = root._gridOffsetY(minorStep);
            var majorX = root._gridOffsetX(majorStep);
            var majorY = root._gridOffsetY(majorStep);
            var minorSize = root.minorGridPointSize;
            var majorSize = root.majorGridPointSize;
            var minorHalf = minorSize * 0.5;
            var majorHalf = majorSize * 0.5;

            ctx.fillStyle = root.pointMinorGridColor;
            for (var y = minorY; y <= height; y += minorStep) {
                for (var x = minorX; x <= width; x += minorStep)
                    ctx.fillRect(x - minorHalf, y - minorHalf, minorSize, minorSize);
            }

            ctx.fillStyle = root.pointMajorGridColor;
            for (var majorRow = majorY; majorRow <= height; majorRow += majorStep) {
                for (var majorColumn = majorX; majorColumn <= width; majorColumn += majorStep) {
                    ctx.fillRect(
                        majorColumn - majorHalf,
                        majorRow - majorHalf,
                        majorSize,
                        majorSize
                    );
                }
            }
        }

        onPaint: {
            var startedMs = Date.now();
            var ctx = getContext("2d");
            ctx.reset();
            root.profileLastGridUpdateMs = 0.0;
            root.profileLastGridPaintMs = 0.0;

            if (!root.effectiveShowGrid || !root._useCanvasGridRenderer)
                return;

            var minorStep = root._currentGridStep();
            var majorStep = root._currentGridPeriod();
            if (!(minorStep > 0.0) || !(majorStep > 0.0))
                return;

            if (root.effectiveGridStyle === "points")
                drawPointGrid(ctx, minorStep, majorStep);
            else
                drawLineGrid(ctx, minorStep, majorStep);

            root._recordGridUpdate(startedMs);
            root.profileLastGridPaintMs = root.profileLastGridUpdateMs;
        }
    }
}
