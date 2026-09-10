import QtQuick
import "ToolbarToolCatalog.js" as ToolCatalog

Rectangle {
    id: root

    property string toolId: ""
    property string panelKind: ""
    property string toolLabel: "Tool"
    property bool implemented: false
    property bool darkBackground: true
    readonly property var actions: ToolCatalog.contextActionsFor(root.panelKind)

    signal contextActionTriggered(string toolId, string actionId)

    width: Math.max(360, contentRow.implicitWidth + 32)
    height: 46
    radius: 12
    visible: root.panelKind.length > 0
    color: root.darkBackground ? "#ec24262c" : "#f7ffffff"
    border.width: 1
    border.color: root.darkBackground ? "#5531598a" : "#6631598a"

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: 8

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.toolLabel
            color: root.darkBackground ? "#e8eef7" : "#24384f"
            font.pixelSize: 12
            font.bold: true
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 24
            color: root.darkBackground ? "#4f5f76" : "#bdcad8"
        }

        Repeater {
            model: root.actions

            delegate: Rectangle {
                readonly property bool actionEnabled: modelData.enabled === true
                width: Math.max(58, actionText.implicitWidth + 18)
                height: 28
                radius: 8
                color: actionEnabled
                    ? (actionMouse.containsMouse ? "#2d6dab" : "#31598a")
                    : (root.darkBackground ? "#343944" : "#e7edf4")
                border.width: 1
                border.color: actionEnabled
                    ? "#75b7ef"
                    : (root.darkBackground ? "#4b5260" : "#c3cfda")
                opacity: actionEnabled ? 1.0 : 0.62

                Text {
                    id: actionText
                    anchors.centerIn: parent
                    text: String(modelData.label || "")
                    color: actionEnabled ? "#f8fbff" : (root.darkBackground ? "#c8d0dc" : "#5d6c7a")
                    font.pixelSize: 11
                    font.bold: actionEnabled
                }

                MouseArea {
                    id: actionMouse
                    anchors.fill: parent
                    hoverEnabled: actionEnabled
                    cursorShape: actionEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (actionEnabled) root.contextActionTriggered(root.toolId, String(modelData.actionId || ""))
                }
            }
        }
    }
}
