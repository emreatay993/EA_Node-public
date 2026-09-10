import QtQuick 2.15

Item {
    id: root
    objectName: "webPageStatusPane"
    property var themePalette: ({})
    property string state: ""
    property string title: "Web page"
    property string message: ""
    property string detail: ""
    property string actionText: ""

    Rectangle {
        anchors.fill: parent
        radius: 6
        color: root.themePalette.input_bg || "#151821"
        border.width: 1
        border.color: root.state === "policy_denied"
            ? (root.themePalette.error || "#d94f4f")
            : (root.themePalette.input_border || root.themePalette.border || "#3a4355")
    }

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 36, 560)
        spacing: 8

        Text {
            objectName: "webPageStatusTitle"
            width: parent.width
            text: root.title
            color: root.themePalette.panel_title_fg || "#eef3ff"
            font.pixelSize: 14
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }

        Text {
            objectName: "webPageStatusMessage"
            width: parent.width
            text: root.message
            visible: text.length > 0
            color: root.state === "policy_denied"
                ? (root.themePalette.error || "#d94f4f")
                : (root.themePalette.muted_fg || "#95a0b8")
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Text {
            objectName: "webPageStatusDetail"
            width: parent.width
            text: root.detail
            visible: text.length > 0
            color: root.themePalette.muted_fg || "#95a0b8"
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Text {
            objectName: "webPageStatusActionText"
            width: parent.width
            text: root.actionText
            visible: text.length > 0
            color: root.themePalette.accent || "#5da9ff"
            font.pixelSize: 11
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }
}
