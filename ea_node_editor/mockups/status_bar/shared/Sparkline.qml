import QtQuick 2.15

// Lightweight pure-QML sparkline: filled area + top line, driven by a numeric
// `values` array normalized against `maxValue`. Used by the telemetry-forward
// design routes. No external dependencies so the mockups stay self-contained.
Canvas {
    id: spark

    property var values: []
    property real maxValue: 100
    property color strokeColor: "#60CDFF"
    property color fillColor: "transparent"
    property real strokeWidth: 1.6
    property real baselinePadding: 2

    onValuesChanged: requestPaint()
    onMaxValueChanged: requestPaint()
    onStrokeColorChanged: requestPaint()
    onFillColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d");
        ctx.reset();
        ctx.clearRect(0, 0, width, height);

        var data = spark.values;
        var n = data ? data.length : 0;
        if (n < 2 || width <= 0 || height <= 0)
            return;

        var top = spark.baselinePadding;
        var usable = Math.max(1, height - spark.baselinePadding * 2);
        var denom = spark.maxValue > 0 ? spark.maxValue : 1;
        var stepX = width / (n - 1);

        function px(i) { return i * stepX; }
        function py(v) {
            var ratio = Math.max(0, Math.min(1, Number(v) / denom));
            return top + (1 - ratio) * usable;
        }

        // Filled area (optional)
        if (Qt.colorEqual(spark.fillColor, "transparent") === false) {
            ctx.beginPath();
            ctx.moveTo(0, height);
            for (var i = 0; i < n; i++)
                ctx.lineTo(px(i), py(data[i]));
            ctx.lineTo(width, height);
            ctx.closePath();
            ctx.fillStyle = spark.fillColor;
            ctx.fill();
        }

        // Top line
        ctx.beginPath();
        ctx.moveTo(0, py(data[0]));
        for (var j = 1; j < n; j++)
            ctx.lineTo(px(j), py(data[j]));
        ctx.lineWidth = spark.strokeWidth;
        ctx.strokeStyle = spark.strokeColor;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
    }
}
