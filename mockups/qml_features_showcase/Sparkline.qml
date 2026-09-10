import QtQuick
import QtQuick.Shapes

// Feature (3): in-node sparkline drawn with QtQuick.Shapes (zero extra deps).
// A filled area + stroked polyline built from a normalized (0..1) data array.
Item {
    id: sp
    property var theme
    property var data: [0.20, 0.45, 0.32, 0.6, 0.5, 0.78, 0.62, 0.9]
    property color lineColor: theme ? theme.accent : "#60CDFF"
    property bool area: true

    function _linePts() {
        var n = data.length;
        if (n < 2 || width <= 0 || height <= 0)
            return [];
        var pts = [];
        var pad = 2;
        var h = height - pad * 2;
        for (var i = 0; i < n; i++)
            pts.push(Qt.point(i / (n - 1) * width, pad + (1 - data[i]) * h));
        return pts;
    }
    function _areaPts() {
        var p = _linePts();
        if (p.length === 0)
            return [];
        var out = [Qt.point(0, height)];
        for (var i = 0; i < p.length; i++)
            out.push(p[i]);
        out.push(Qt.point(width, height));
        return out;
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: "transparent"
            fillColor: sp.area ? Qt.rgba(sp.lineColor.r, sp.lineColor.g, sp.lineColor.b, 0.16) : "transparent"
            PathPolyline { path: sp._areaPts() }
        }
        ShapePath {
            strokeColor: sp.lineColor
            strokeWidth: 2
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathPolyline { path: sp._linePts() }
        }
    }
}
