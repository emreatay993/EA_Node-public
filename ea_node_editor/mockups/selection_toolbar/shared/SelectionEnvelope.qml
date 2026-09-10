import QtQuick 2.15

Item {
    id: root

    property var themePalette: ({})
    property var nodePalette: ({})
    property var box: ({ "x": 0, "y": 0, "width": 0, "height": 0 })
    property string style: "subtle"
    property bool cornerTicks: false
    property bool halo: false
    property real extraPadding: 0

    readonly property color accentColor: nodePalette.card_selected_border || themePalette.accent || "#60CDFF"
    readonly property real resolvedX: Number(box.x || 0) - extraPadding
    readonly property real resolvedY: Number(box.y || 0) - extraPadding
    readonly property real resolvedWidth: Math.max(0, Number(box.width || 0) + extraPadding * 2)
    readonly property real resolvedHeight: Math.max(0, Number(box.height || 0) + extraPadding * 2)

    x: root.resolvedX
    y: root.resolvedY
    width: root.resolvedWidth
    height: root.resolvedHeight
    visible: root.resolvedWidth > 0 && root.resolvedHeight > 0

    Rectangle {
        anchors.fill: parent
        radius: root.style === "halo" ? 18 : 10
        color: root.halo ? Qt.alpha(root.accentColor, 0.08) : "transparent"
        border.width: root.style === "strong" ? 2 : 1.4
        border.color: root.style === "ghost"
            ? Qt.alpha(root.accentColor, 0.34)
            : Qt.alpha(root.accentColor, root.style === "strong" ? 0.95 : 0.66)
    }

    Rectangle {
        visible: root.halo
        anchors.fill: parent
        anchors.margins: -8
        radius: 22
        color: "transparent"
        border.width: 1
        border.color: Qt.alpha(root.accentColor, 0.22)
    }

    Repeater {
        visible: root.cornerTicks
        model: [
            { "x": -1, "y": -1, "h": true },
            { "x": -1, "y": -1, "h": false },
            { "x": root.width - 19, "y": -1, "h": true },
            { "x": root.width - 1, "y": -1, "h": false },
            { "x": -1, "y": root.height - 1, "h": true },
            { "x": -1, "y": root.height - 19, "h": false },
            { "x": root.width - 19, "y": root.height - 1, "h": true },
            { "x": root.width - 1, "y": root.height - 19, "h": false }
        ]
        delegate: Rectangle {
            x: modelData.x
            y: modelData.y
            width: modelData.h ? 20 : 2
            height: modelData.h ? 2 : 20
            radius: 1
            color: root.accentColor
        }
    }
}
