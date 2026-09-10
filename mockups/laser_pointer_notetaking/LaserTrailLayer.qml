import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: root

    property var strokes: []
    property bool softGlow: true
    property bool highQuality: true
    property real redWidth: 12
    property real coreWidth: 2.5
    property real glowRadius: 23
    property real dotRadius: 4
    property real pointerX: -1000
    property real pointerY: -1000
    property bool dotVisible: false
    property color laserColor: "#ff2a2a"
    property color glowColor: "#ff2a2a"
    property color coreColor: "#fff2f2"
    property real trailOpacity: 1.0

    Shape {
        id: glowShape
        anchors.fill: parent
        z: -1
        opacity: root.trailOpacity
        visible: root.softGlow
        antialiasing: true
        preferredRendererType: root.highQuality ? Shape.CurveRenderer : Shape.GeometryRenderer
        layer.enabled: root.softGlow
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 48; autoPaddingEnabled: true }

        ShapePath {
            strokeColor: root.glowColor
            strokeWidth: root.redWidth * 1.3
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathMultiline { paths: root.softGlow ? root.strokes : [] }
        }
    }

    Shape {
        id: lineShape
        anchors.fill: parent
        opacity: root.trailOpacity
        antialiasing: true
        preferredRendererType: root.highQuality ? Shape.CurveRenderer : Shape.GeometryRenderer

        ShapePath {
            strokeColor: Qt.rgba(1.0, 0.16, 0.16, 0.22)
            strokeWidth: root.glowRadius
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathMultiline { paths: root.strokes }
        }

        ShapePath {
            strokeColor: root.laserColor
            strokeWidth: root.redWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathMultiline { paths: root.strokes }
        }

        ShapePath {
            strokeColor: root.coreColor
            strokeWidth: root.coreWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathMultiline { paths: root.strokes }
        }
    }

    Canvas {
        id: dot
        property real cx: root.pointerX
        property real cy: root.pointerY
        width: Math.ceil(root.dotRadius * 5)
        height: width
        x: cx - width / 2
        y: cy - height / 2
        antialiasing: true
        visible: root.dotVisible
        onWidthChanged: requestPaint()
        onVisibleChanged: requestPaint()
        Component.onCompleted: requestPaint()

        Connections {
            target: root
            function onDotRadiusChanged() { dot.requestPaint(); }
        }

        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            var c = width / 2;
            var r = root.dotRadius;
            var g = ctx.createRadialGradient(c, c, 0, c, c, r * 2.2);
            g.addColorStop(0.00, "rgba(255,120,120,1.0)");
            g.addColorStop(0.30, "rgba(255,40,40,0.95)");
            g.addColorStop(1.00, "rgba(255,40,40,0.0)");
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(c, c, r * 2.2, 0, 2 * Math.PI);
            ctx.fill();
        }
    }
}
