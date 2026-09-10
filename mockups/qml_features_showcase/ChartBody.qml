import QtQuick
import QtGraphs

// Feature (4): a live in-node chart rendered with Qt Graphs (the modern,
// non-deprecated charting module — installed as PyQt6-Graphs). GraphsView does
// NOT auto-range, so axes are set explicitly. Wrapped in an Item so the palette
// `theme` property doesn't collide with GraphsView's own `theme`.
Item {
    id: b
    property var theme

    GraphsView {
        id: gv
        anchors.fill: parent
        anchors.margins: 4

        theme: GraphsTheme {
            colorScheme: (b.theme && b.theme.isDark) ? GraphsTheme.ColorScheme.Dark
                                                     : GraphsTheme.ColorScheme.Light
            seriesColors: [
                b.theme ? b.theme.accent : "#60CDFF",
                b.theme ? b.theme.stDone : "#46c98b"
            ]
            backgroundVisible: false
        }

        axisX: ValueAxis { min: 0; max: 5; subTickCount: 0; labelDecimals: 0 }
        axisY: ValueAxis { min: 0; max: 10; subTickCount: 0; labelDecimals: 0 }

        BarSeries {
            BarSet { values: [1.6, 3.2, 2.6, 4.2, 3.5, 5.1] }
        }
        LineSeries {
            width: 2.5
            XYPoint { x: 0; y: 2.2 }
            XYPoint { x: 1; y: 4.6 }
            XYPoint { x: 2; y: 3.9 }
            XYPoint { x: 3; y: 7.1 }
            XYPoint { x: 4; y: 6.4 }
            XYPoint { x: 5; y: 9.2 }
        }
    }
}
