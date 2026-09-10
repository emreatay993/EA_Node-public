import QtQuick

// Throwaway mockup glyph atlas. Canvas-drawn, recolourable, crisp at any size
// and DPI-safe under QT_SCALE_FACTOR=2. Cloned from the laser mockup's
// ToolbarIcon.qml engine: 0..1 normalised coords, k = size/36 weight scaling,
// repaint on every relevant property change.
Canvas {
    id: g

    property string name: "chain"
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

    function roundedRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
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
        function poly(pts, close, fill) {
            ctx.beginPath();
            ctx.moveTo(pts[0][0] * s, pts[0][1] * s);
            for (var i = 1; i < pts.length; i++)
                ctx.lineTo(pts[i][0] * s, pts[i][1] * s);
            if (close) ctx.closePath();
            if (fill) ctx.fill(); else ctx.stroke();
        }
        function circle(x, y, r, fill) {
            ctx.beginPath();
            ctx.arc(x * s, y * s, r * s, 0, Math.PI * 2);
            if (fill) ctx.fill(); else ctx.stroke();
        }

        if (g.name === "chain" || g.name === "link") {
            // Two interlocking rounded capsules along the NE-SW diagonal.
            ctx.lineWidth = W(2.6);
            function capsule(cx, cy) {
                ctx.save();
                ctx.translate(cx * s, cy * s);
                ctx.rotate(-Math.PI / 4);
                roundedRect(ctx, -0.17 * s, -0.085 * s, 0.34 * s, 0.17 * s, 0.085 * s);
                ctx.stroke();
                ctx.restore();
            }
            capsule(0.38, 0.62);
            capsule(0.62, 0.38);
        } else if (g.name === "globe") {
            ctx.lineWidth = W(2.2);
            var R = 0.33;
            circle(0.5, 0.5, R, false);
            // meridian (a vertical lens drawn as two quadratics)
            ctx.beginPath();
            ctx.moveTo(0.5 * s, (0.5 - R) * s);
            ctx.quadraticCurveTo((0.5 - R * 0.62) * s, 0.5 * s, 0.5 * s, (0.5 + R) * s);
            ctx.moveTo(0.5 * s, (0.5 - R) * s);
            ctx.quadraticCurveTo((0.5 + R * 0.62) * s, 0.5 * s, 0.5 * s, (0.5 + R) * s);
            ctx.stroke();
            // parallels (chords)
            line(0.22, 0.40, 0.78, 0.40);
            line(0.17, 0.50, 0.83, 0.50);
            line(0.22, 0.60, 0.78, 0.60);
        } else if (g.name === "document") {
            ctx.lineWidth = W(2.4);
            var f = 0.16;
            ctx.beginPath();
            ctx.moveTo(0.28 * s, 0.16 * s);
            ctx.lineTo((0.72 - f) * s, 0.16 * s);
            ctx.lineTo(0.72 * s, (0.16 + f) * s);
            ctx.lineTo(0.72 * s, 0.84 * s);
            ctx.lineTo(0.28 * s, 0.84 * s);
            ctx.closePath();
            ctx.stroke();
            // dog-ear fold
            ctx.beginPath();
            ctx.moveTo((0.72 - f) * s, 0.16 * s);
            ctx.lineTo((0.72 - f) * s, (0.16 + f) * s);
            ctx.lineTo(0.72 * s, (0.16 + f) * s);
            ctx.stroke();
            // text lines
            ctx.lineWidth = W(1.8);
            line(0.36, 0.44, 0.64, 0.44);
            line(0.36, 0.56, 0.64, 0.56);
            line(0.36, 0.68, 0.56, 0.68);
        } else if (g.name === "folder") {
            ctx.lineWidth = W(2.4);
            ctx.beginPath();
            ctx.moveTo(0.16 * s, 0.30 * s);
            ctx.lineTo(0.40 * s, 0.30 * s);
            ctx.lineTo(0.46 * s, 0.38 * s);
            ctx.lineTo(0.84 * s, 0.38 * s);
            ctx.lineTo(0.84 * s, 0.74 * s);
            ctx.lineTo(0.16 * s, 0.74 * s);
            ctx.closePath();
            ctx.stroke();
        } else if (g.name === "workspace") {
            ctx.lineWidth = W(2.2);
            roundedRect(ctx, 0.20 * s, 0.24 * s, 0.42 * s, 0.40 * s, 0.06 * s); ctx.stroke();
            roundedRect(ctx, 0.36 * s, 0.38 * s, 0.42 * s, 0.40 * s, 0.06 * s); ctx.stroke();
        } else if (g.name === "node") {
            ctx.lineWidth = W(2.4);
            roundedRect(ctx, 0.20 * s, 0.26 * s, 0.60 * s, 0.48 * s, 0.08 * s); ctx.stroke();
            line(0.20, 0.40, 0.80, 0.40);
        } else if (g.name === "plus") {
            ctx.lineWidth = W(2.6);
            line(0.50, 0.24, 0.50, 0.76);
            line(0.24, 0.50, 0.76, 0.50);
        } else if (g.name === "x") {
            ctx.lineWidth = W(2.4);
            line(0.29, 0.29, 0.71, 0.71);
            line(0.71, 0.29, 0.29, 0.71);
        } else if (g.name === "chevron") {
            ctx.lineWidth = W(3.0);
            line(0.30, 0.42, 0.50, 0.62);
            line(0.50, 0.62, 0.70, 0.42);
        } else if (g.name === "chevronRight") {
            ctx.lineWidth = W(2.6);
            line(0.42, 0.30, 0.62, 0.50);
            line(0.62, 0.50, 0.42, 0.70);
        } else if (g.name === "open") {
            // box with arrow leaving the top-right (open externally)
            ctx.lineWidth = W(2.4);
            ctx.beginPath();
            ctx.moveTo(0.54 * s, 0.24 * s);
            ctx.lineTo(0.24 * s, 0.24 * s);
            ctx.lineTo(0.24 * s, 0.76 * s);
            ctx.lineTo(0.76 * s, 0.76 * s);
            ctx.lineTo(0.76 * s, 0.46 * s);
            ctx.stroke();
            line(0.48, 0.52, 0.80, 0.20);
            poly([[0.60, 0.20], [0.80, 0.20], [0.80, 0.40]], false, false);
        } else if (g.name === "edit") {
            // pencil along the NE-SW diagonal
            ctx.save();
            ctx.translate(0.5 * s, 0.5 * s);
            ctx.rotate(Math.PI / 4);
            ctx.lineWidth = W(2.4);
            roundedRect(ctx, -0.085 * s, -0.34 * s, 0.17 * s, 0.46 * s, 0.04 * s);
            ctx.stroke();
            line(-0.085, -0.18, 0.085, -0.18);
            ctx.beginPath();
            ctx.moveTo(-0.085 * s, 0.12 * s);
            ctx.lineTo(0.085 * s, 0.12 * s);
            ctx.lineTo(0, 0.30 * s);
            ctx.closePath();
            ctx.stroke();
            ctx.restore();
        } else if (g.name === "search") {
            ctx.lineWidth = W(2.4);
            circle(0.44, 0.44, 0.22, false);
            line(0.60, 0.60, 0.79, 0.79);
        }

        ctx.restore();
    }
}
