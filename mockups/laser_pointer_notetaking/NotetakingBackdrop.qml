import QtQuick

Item {
    id: root

    property bool darkBackground: true

    Rectangle {
        anchors.fill: parent
        color: root.darkBackground ? "#1e1f22" : "#f7f2e8"
    }

    Canvas {
        anchors.fill: parent
        opacity: root.darkBackground ? 0.42 : 0.72
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            ctx.strokeStyle = root.darkBackground ? "rgba(255,255,255,0.055)" : "rgba(49,89,138,0.12)";
            ctx.lineWidth = 1;
            for (var x = 0; x < width; x += 32) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
                ctx.stroke();
            }
            for (var y = 0; y < height; y += 32) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
                ctx.stroke();
            }
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
    }

}
