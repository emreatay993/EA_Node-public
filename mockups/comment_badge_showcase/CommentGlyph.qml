import QtQuick

// Throwaway mockup glyph atlas. Canvas-drawn, recolourable, crisp at any size
// and DPI-safe under QT_SCALE_FACTOR=2. Cloned from the linking mockup's
// LinkGlyph.qml engine: 0..1 normalised coords, k = size/36 weight scaling,
// repaint on every relevant property change. The "bubble" silhouette mirrors
// the production shell icon (ea_node_editor/.../shell/icons/comment.svg) so
// the mock family matches the app's comment glyph.
Canvas {
    id: g

    property string name: "bubble"
    property int size: 18
    property color color: "#e8e8e8"

    width: g.size
    height: g.size
    antialiasing: true

    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
    onSizeChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Component.onCompleted: requestPaint()

    // Speech-bubble outline traced from comment.svg (24-unit viewBox, /24):
    // rounded body, bottom-left tail dipping to (0.125, 0.875).
    function bubblePath(ctx, s) {
        ctx.beginPath();
        ctx.moveTo(0.25 * s, 0.7917 * s);
        ctx.lineTo(0.125 * s, 0.875 * s);
        ctx.lineTo(0.125 * s, 0.3333 * s);
        ctx.quadraticCurveTo(0.125 * s, 0.1667 * s, 0.2917 * s, 0.1667 * s);
        ctx.lineTo(0.7083 * s, 0.1667 * s);
        ctx.quadraticCurveTo(0.875 * s, 0.1667 * s, 0.875 * s, 0.3333 * s);
        ctx.lineTo(0.875 * s, 0.5833 * s);
        ctx.quadraticCurveTo(0.875 * s, 0.75 * s, 0.7083 * s, 0.75 * s);
        ctx.lineTo(0.375 * s, 0.75 * s);
        ctx.closePath();
    }

    onPaint: {
        var ctx = getContext("2d");
        var s = Math.min(width, height);
        ctx.clearRect(0, 0, width, height);
        ctx.save();
        ctx.translate((width - s) / 2, (height - s) / 2);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = g.color;
        ctx.fillStyle = g.color;

        var k = s / 36;
        function W(px) { return px * k; }
        function line(x1, y1, x2, y2) {
            ctx.beginPath();
            ctx.moveTo(x1 * s, y1 * s);
            ctx.lineTo(x2 * s, y2 * s);
            ctx.stroke();
        }
        function circle(x, y, r, fill) {
            ctx.beginPath();
            ctx.arc(x * s, y * s, r * s, 0, Math.PI * 2);
            if (fill) ctx.fill(); else ctx.stroke();
        }

        if (g.name === "bubble") {
            ctx.lineWidth = W(2.4);
            bubblePath(ctx, s);
            ctx.stroke();
            // text rules
            ctx.lineWidth = W(1.9);
            line(0.2917, 0.375, 0.7083, 0.375);
            line(0.2917, 0.5417, 0.5417, 0.5417);
        } else if (g.name === "bubbleFilled") {
            // Solid silhouette for tiny sizes where strokes get muddy.
            bubblePath(ctx, s);
            ctx.fill();
        } else if (g.name === "check") {
            ctx.lineWidth = W(3.0);
            ctx.beginPath();
            ctx.moveTo(0.26 * s, 0.52 * s);
            ctx.lineTo(0.43 * s, 0.70 * s);
            ctx.lineTo(0.76 * s, 0.32 * s);
            ctx.stroke();
        } else if (g.name === "plus") {
            ctx.lineWidth = W(2.6);
            line(0.50, 0.24, 0.50, 0.76);
            line(0.24, 0.50, 0.76, 0.50);
        } else if (g.name === "x") {
            ctx.lineWidth = W(2.4);
            line(0.29, 0.29, 0.71, 0.71);
            line(0.71, 0.29, 0.29, 0.71);
        } else if (g.name === "pin") {
            // Pushpin: filled head + stem.
            ctx.lineWidth = W(2.4);
            circle(0.5, 0.40, 0.15, true);
            line(0.5, 0.56, 0.5, 0.80);
        }

        ctx.restore();
    }
}
