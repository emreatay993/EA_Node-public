import QtQuick 2.15

// Small rounded utilization bar (0..1) with an animated fill. Shared atom used
// by the chip-based and ambient design routes for CPU / RAM.
Rectangle {
    id: bar
    property real ratio: 0
    property color trackColor: "#33373f"
    property color fillColor: "#67D487"

    radius: height / 2
    color: trackColor

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.max(0, Math.min(1, bar.ratio)) * parent.width
        radius: parent.radius
        color: bar.fillColor
        Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 240 } }
    }
}
