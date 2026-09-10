// Purpose: Draw the entire grid with one quad and continuous physical-pixel coverage.
// Map: subsystems/graph_canvas.md
// Tests: tests/test_graph_canvas_grid.py
import QtQuick 2.15

ShaderEffect {
    id: root
    objectName: "graphCanvasGridShaderRenderer"

    property string gridStyle: "lines"
    property color minorGridColor: "#2b3440"
    property color majorGridColor: "#3f4d5f"
    property real minorStep: 20.0
    property real majorStep: 100.0
    property vector2d minorOffset: Qt.vector2d(0, 0)
    property vector2d majorOffset: Qt.vector2d(0, 0)
    // The shader consumes physical pixels; defaults correspond to 1.25/2 logical pixels.
    property real minorPointSize: 1.25 * devicePixelRatio
    property real majorPointSize: 2.0 * devicePixelRatio
    property real devicePixelRatio: 1.0
    readonly property vector2d viewportSize: Qt.vector2d(width, height)
    readonly property real pointStyle: gridStyle === "points" ? 1.0 : 0.0

    fragmentShader: "shaders/grid.frag.qsb"
}
