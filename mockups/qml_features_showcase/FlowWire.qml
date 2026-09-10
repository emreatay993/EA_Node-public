import QtQuick
import QtQuick.Shapes

// Feature (1): animated data-flow wire. A cubic Bézier "noodle" (like the real
// EdgeRetainedLayer.qml) plus a dashed overlay whose dashOffset animates while
// `flowing`, so data visibly travels output -> input. Goes solid accent when the
// downstream node is `active` (done). Note: ShapePath is not an Item, so opacity
// is set on the enclosing Shape, not the ShapePath.
Item {
    id: w
    property var theme
    property real startX: 0
    property real startY: 0
    property real endX: 0
    property real endY: 0
    property bool flowing: false
    property bool active: false

    readonly property color baseColor: theme ? theme.border : "#3a3d45"
    readonly property color liveColor: theme ? theme.accent : "#60CDFF"
    readonly property real dx: Math.max(46, Math.abs(endX - startX) * 0.5)

    // base wire
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: w.active ? w.liveColor : w.baseColor
            strokeWidth: w.active ? 2.6 : 1.8
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: w.startX
            startY: w.startY
            PathCubic {
                x: w.endX; y: w.endY
                control1X: w.startX + w.dx; control1Y: w.startY
                control2X: w.endX - w.dx;   control2Y: w.endY
            }
            Behavior on strokeColor { ColorAnimation { duration: 240 } }
        }
    }

    // animated flowing dashes
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        opacity: w.flowing ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 200 } }
        ShapePath {
            id: flow
            strokeColor: w.liveColor
            strokeWidth: 3.0
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            strokeStyle: ShapePath.DashLine
            dashPattern: [0.7, 2.3]
            dashOffset: 0
            startX: w.startX
            startY: w.startY
            PathCubic {
                x: w.endX; y: w.endY
                control1X: w.startX + w.dx; control1Y: w.startY
                control2X: w.endX - w.dx;   control2Y: w.endY
            }
        }
        NumberAnimation {
            target: flow
            property: "dashOffset"
            running: w.flowing
            from: 3; to: 0
            duration: 520
            loops: Animation.Infinite
        }
    }

    // a pip that rides the wire while flowing, for extra "data is moving" read
    Rectangle {
        width: 7; height: 7; radius: 4
        color: w.liveColor
        visible: w.flowing
        x: w.startX + (w.endX - w.startX) * w.pipT - width / 2
        y: w.startY + (w.endY - w.startY) * w.pipT - height / 2
    }
    property real pipT: 0
    NumberAnimation on pipT {
        running: w.flowing
        from: 0; to: 1
        duration: 900
        loops: Animation.Infinite
    }
}
