import QtQuick 2.15

Item {
    id: root
    objectName: "graphNodeGradientFill"
    property color startColor: "transparent"
    property color endColor: "transparent"
    property string direction: "south"
    property real cornerRadius: 0
    readonly property string normalizedDirection: {
        var value = String(root.direction || "").toLowerCase();
        if (value === "north" || value === "east" || value === "south" || value === "west" || value === "radial")
            return value;
        return "south";
    }
    readonly property bool radial: root.normalizedDirection === "radial"
    readonly property bool horizontal: root.normalizedDirection === "east" || root.normalizedDirection === "west"
    readonly property color firstStopColor: root.normalizedDirection === "north" || root.normalizedDirection === "west"
        ? root.endColor
        : root.startColor
    readonly property color lastStopColor: root.normalizedDirection === "north" || root.normalizedDirection === "west"
        ? root.startColor
        : root.endColor
    onStartColorChanged: radialCanvas.requestPaint()
    onEndColorChanged: radialCanvas.requestPaint()
    onDirectionChanged: radialCanvas.requestPaint()
    onCornerRadiusChanged: radialCanvas.requestPaint()

    Rectangle {
        anchors.fill: parent
        visible: !root.radial
        radius: root.cornerRadius
        color: "transparent"
        gradient: Gradient {
            orientation: root.horizontal ? Gradient.Horizontal : Gradient.Vertical
            GradientStop { position: 0.0; color: root.firstStopColor }
            GradientStop { position: 1.0; color: root.lastStopColor }
        }
    }

    Canvas {
        id: radialCanvas
        anchors.fill: parent
        visible: root.radial
        antialiasing: true
        renderTarget: Canvas.FramebufferObject
        renderStrategy: Canvas.Cooperative

        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            if (width <= 0 || height <= 0)
                return;

            var radius = Math.max(0, Math.min(root.cornerRadius, Math.min(width, height) / 2));
            ctx.beginPath();
            ctx.moveTo(radius, 0);
            ctx.lineTo(width - radius, 0);
            ctx.quadraticCurveTo(width, 0, width, radius);
            ctx.lineTo(width, height - radius);
            ctx.quadraticCurveTo(width, height, width - radius, height);
            ctx.lineTo(radius, height);
            ctx.quadraticCurveTo(0, height, 0, height - radius);
            ctx.lineTo(0, radius);
            ctx.quadraticCurveTo(0, 0, radius, 0);
            ctx.closePath();
            ctx.clip();

            var centerX = width / 2;
            var centerY = height / 2;
            var gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(width, height) / 2);
            gradient.addColorStop(0, String(root.startColor));
            gradient.addColorStop(1, String(root.endColor));
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, width, height);
        }

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        Component.onCompleted: requestPaint()
    }
}
