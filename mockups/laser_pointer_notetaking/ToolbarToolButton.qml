import QtQuick

Item {
    id: root

    property string toolId: ""
    property string iconName: ""
    property string label: ""
    property bool active: false
    property bool implemented: false
    property int buttonSize: 46
    property int iconSize: 24
    signal triggered(string toolId)

    width: root.buttonSize
    height: root.buttonSize
    opacity: root.implemented || root.active ? 1.0 : 0.58

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: root.active
            ? "#e7edf6"
            : (hoverArea.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent")
        border.width: root.active || hoverArea.containsMouse ? 1 : 0
        border.color: root.active ? "#f8fbff" : Qt.rgba(1, 1, 1, 0.28)
    }

    ToolbarIcon {
        anchors.centerIn: parent
        iconName: root.iconName
        size: root.iconSize
        strokeColor: root.active ? "#244a78" : "#f7fbff"
        accentColor: root.active && root.toolId === "laser" ? "#ff3030"
            : root.active && root.toolId === "eraser" ? "#a8daf0"
            : root.active ? "#244a78" : "#f7fbff"
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.triggered(root.toolId)
    }
}
