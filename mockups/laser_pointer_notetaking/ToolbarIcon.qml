import QtQuick

Canvas {
    id: root

    property string iconName: "select"
    property int size: 36
    property color strokeColor: "#ffffff"
    property color accentColor: "#ffffff"

    width: root.size
    height: root.size
    antialiasing: true

    onIconNameChanged: requestPaint()
    onStrokeColorChanged: requestPaint()
    onAccentColorChanged: requestPaint()
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
        var c = root.strokeColor;
        var a = root.accentColor;
        ctx.clearRect(0, 0, width, height);
        ctx.save();
        ctx.translate((width - s) / 2, (height - s) / 2);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = c;
        ctx.fillStyle = c;

        // Line weights are tuned for the production 36px size and scaled up
        // proportionally so the glyphs keep their weight at any render size.
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
            if (close)
                ctx.closePath();
            if (fill)
                ctx.fill();
            else
                ctx.stroke();
        }

        function circle(x, y, r, fill) {
            ctx.beginPath();
            ctx.arc(x * s, y * s, r * s, 0, Math.PI * 2);
            if (fill)
                ctx.fill();
            else
                ctx.stroke();
        }

        // Four-point sparkle (concave diamond) centred at cx,cy.
        function star4(cx, cy, R, r) {
            var d = r * 0.7071;
            poly([
                [cx, cy - R], [cx + d, cy - d], [cx + R, cy], [cx + d, cy + d],
                [cx, cy + R], [cx - d, cy + d], [cx - R, cy], [cx - d, cy - d]
            ], true, true);
        }

        if (iconName === "select") {
            // Marching-ants rounded square (clean butt-cap dashes)...
            ctx.lineWidth = W(2.2);
            ctx.lineCap = "butt";
            ctx.setLineDash([W(2.7), W(2.5)]);
            roundedRect(ctx, 0.13 * s, 0.13 * s, 0.62 * s, 0.62 * s, 0.12 * s);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.lineCap = "round";
            // ...with a solid pointer arrow tucked into the bottom-right corner.
            var ax = 0.50, ay = 0.48, aw = 0.40;
            function A(ux, uy) { return [ax + ux * aw, ay + uy * aw]; }
            poly([A(0, 0), A(0, 0.74), A(0.205, 0.56), A(0.33, 0.85),
                  A(0.45, 0.80), A(0.32, 0.52), A(0.56, 0.52)], true, true);
        } else if (iconName === "pen") {
            // Marker tilted along the NE-SW diagonal, nib at lower-left.
            ctx.save();
            ctx.translate(0.52 * s, 0.46 * s);
            ctx.rotate(Math.PI / 4);
            ctx.lineWidth = W(2.5);
            // barrel
            roundedRect(ctx, -0.13 * s, -0.34 * s, 0.26 * s, 0.42 * s, 0.10 * s);
            ctx.stroke();
            // end cap + grip band
            ctx.beginPath(); ctx.moveTo(-0.13 * s, -0.20 * s); ctx.lineTo(0.13 * s, -0.20 * s); ctx.stroke();
            // nib
            ctx.beginPath();
            ctx.moveTo(-0.13 * s, 0.08 * s);
            ctx.lineTo(0.13 * s, 0.08 * s);
            ctx.lineTo(0, 0.33 * s);
            ctx.closePath();
            ctx.stroke();
            ctx.restore();
            // little writing squiggle trailing from the nib
            ctx.lineWidth = W(2.0);
            ctx.beginPath();
            ctx.moveTo(0.16 * s, 0.85 * s);
            ctx.quadraticCurveTo(0.23 * s, 0.75 * s, 0.30 * s, 0.83 * s);
            ctx.quadraticCurveTo(0.37 * s, 0.91 * s, 0.44 * s, 0.82 * s);
            ctx.stroke();
        } else if (iconName === "eraser") {
            // Angled rubber block with a tip band; when an accent colour is
            // provided (active state) the tip fills light blue like the
            // floating eraser toolbar's glyphs.
            ctx.save();
            ctx.translate(0.50 * s, 0.54 * s);
            ctx.rotate(-Math.PI * 0.17);
            ctx.lineWidth = W(2.6);
            if (!Qt.colorEqual(a, c)) {
                ctx.fillStyle = a;
                ctx.beginPath();
                ctx.moveTo(0.05 * s, -0.17 * s);
                ctx.lineTo(0.23 * s, -0.17 * s);
                ctx.quadraticCurveTo(0.30 * s, -0.17 * s, 0.30 * s, -0.10 * s);
                ctx.lineTo(0.30 * s, 0.08 * s);
                ctx.quadraticCurveTo(0.30 * s, 0.15 * s, 0.23 * s, 0.15 * s);
                ctx.lineTo(0.05 * s, 0.15 * s);
                ctx.closePath();
                ctx.fill();
            }
            roundedRect(ctx, -0.30 * s, -0.17 * s, 0.60 * s, 0.32 * s, 0.07 * s);
            ctx.stroke();
            ctx.beginPath(); ctx.moveTo(0.05 * s, -0.17 * s); ctx.lineTo(0.05 * s, 0.15 * s); ctx.stroke();
            ctx.restore();
        } else if (iconName === "text") {
            // "T" in a rounded badge with little frame tabs on the sides.
            ctx.lineWidth = W(2.4);
            roundedRect(ctx, 0.18 * s, 0.22 * s, 0.64 * s, 0.56 * s, 0.12 * s);
            ctx.stroke();
            ctx.lineWidth = W(2.2);
            line(0.13, 0.50, 0.18, 0.50);
            line(0.82, 0.50, 0.87, 0.50);
            ctx.fillStyle = c;
            ctx.font = "bold " + Math.round(s * 0.42) + "px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("T", 0.50 * s, 0.52 * s);
        } else if (iconName === "sticker") {
            // Smiley sticker with a peeled corner.
            ctx.lineWidth = W(2.5);
            circle(0.50, 0.48, 0.32, false);
            circle(0.40, 0.42, 0.038, true);
            circle(0.60, 0.42, 0.038, true);
            ctx.beginPath();
            ctx.arc(0.50 * s, 0.50 * s, 0.16 * s, 0.18 * Math.PI, 0.82 * Math.PI);
            ctx.stroke();
            // peeled corner curl, bottom-right
            ctx.lineWidth = W(2.2);
            ctx.beginPath();
            ctx.moveTo(0.70 * s, 0.74 * s);
            ctx.quadraticCurveTo(0.84 * s, 0.74 * s, 0.82 * s, 0.60 * s);
            ctx.stroke();
        } else if (iconName === "image") {
            // Photo frame with a sun and a mountain ridge.
            ctx.lineWidth = W(2.5);
            roundedRect(ctx, 0.17 * s, 0.21 * s, 0.66 * s, 0.58 * s, 0.11 * s);
            ctx.stroke();
            circle(0.36, 0.39, 0.066, false);
            ctx.lineWidth = W(2.5);
            poly([[0.21, 0.74], [0.40, 0.51], [0.52, 0.63], [0.64, 0.46], [0.81, 0.72]], false, false);
        } else if (iconName === "shapes") {
            // Triangle + rounded square with a swap cycle between them.
            ctx.lineWidth = W(2.4);
            poly([[0.28, 0.12], [0.14, 0.39], [0.42, 0.39]], true, false);
            roundedRect(ctx, 0.56 * s, 0.58 * s, 0.28 * s, 0.28 * s, 0.06 * s);
            ctx.stroke();
            // upper swap arrow: triangle -> square
            ctx.lineWidth = W(2.2);
            ctx.beginPath();
            ctx.moveTo(0.46 * s, 0.24 * s);
            ctx.quadraticCurveTo(0.76 * s, 0.28 * s, 0.71 * s, 0.54 * s);
            ctx.stroke();
            poly([[0.64, 0.49], [0.71, 0.57], [0.78, 0.49]], false, false);
            // lower swap arrow: square -> triangle
            ctx.beginPath();
            ctx.moveTo(0.52 * s, 0.73 * s);
            ctx.quadraticCurveTo(0.24 * s, 0.69 * s, 0.28 * s, 0.45 * s);
            ctx.stroke();
            poly([[0.21, 0.50], [0.28, 0.42], [0.35, 0.50]], false, false);
        } else if (iconName === "note") {
            // Sticky note with a curled (folded) bottom-right corner.
            ctx.lineWidth = W(2.5);
            var f = 0.20;
            ctx.beginPath();
            ctx.moveTo(0.24 * s, 0.20 * s);
            ctx.lineTo(0.76 * s, 0.20 * s);
            ctx.lineTo(0.76 * s, (0.80 - f) * s);
            ctx.lineTo((0.76 - f) * s, 0.80 * s);
            ctx.lineTo(0.24 * s, 0.80 * s);
            ctx.closePath();
            ctx.stroke();
            // the fold
            ctx.beginPath();
            ctx.moveTo(0.76 * s, (0.80 - f) * s);
            ctx.lineTo((0.76 - f) * s, (0.80 - f) * s);
            ctx.lineTo((0.76 - f) * s, 0.80 * s);
            ctx.stroke();
            // text lines
            ctx.lineWidth = W(2.0);
            line(0.33, 0.39, 0.67, 0.39);
            line(0.33, 0.51, 0.60, 0.51);
        } else if (iconName === "laser") {
            // Laser pointer: body, red beam to a glowing dot, magic sparkles.
            ctx.save();
            ctx.translate(0.33 * s, 0.67 * s);
            ctx.rotate(-Math.PI / 4);
            ctx.lineWidth = W(2.4);
            ctx.strokeStyle = c;
            roundedRect(ctx, -0.20 * s, -0.075 * s, 0.40 * s, 0.15 * s, 0.055 * s);
            ctx.stroke();
            // grip band toward the back
            ctx.beginPath(); ctx.moveTo(-0.06 * s, -0.075 * s); ctx.lineTo(-0.06 * s, 0.075 * s); ctx.stroke();
            ctx.restore();
            // red beam from the emitter to the dot
            ctx.strokeStyle = a;
            ctx.lineWidth = W(3.0);
            line(0.55, 0.45, 0.71, 0.29);
            ctx.fillStyle = a;
            circle(0.73, 0.27, 0.05, true);
            // white magic sparkles near the dot
            ctx.fillStyle = c;
            star4(0.85, 0.17, 0.10, 0.026);
            star4(0.93, 0.32, 0.05, 0.014);
        } else if (iconName === "chevron") {
            ctx.lineWidth = W(3.0);
            line(0.30, 0.42, 0.50, 0.62);
            line(0.50, 0.62, 0.70, 0.42);
        }

        ctx.restore();
    }
}
