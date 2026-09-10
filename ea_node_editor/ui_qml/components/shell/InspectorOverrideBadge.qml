import QtQuick 2.15

Rectangle {
    id: badge
    property var pane
    property string label: "Driven"

    readonly property color accentColor: pane ? pane.themePalette.accent : "#60CDFF"

    radius: 8
    color: Qt.alpha(accentColor, 0.14)
    border.color: Qt.alpha(accentColor, 0.36)
    border.width: 1

    implicitHeight: badgeRow.implicitHeight + 4
    implicitWidth: badgeRow.implicitWidth + 12
    height: implicitHeight
    width: implicitWidth

    Row {
        id: badgeRow
        anchors.centerIn: parent
        spacing: 4

        Rectangle {
            width: 6
            height: 6
            radius: 3
            color: badge.accentColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: badge.label.toUpperCase()
            color: badge.accentColor
            font.pixelSize: 9
            font.bold: true
            font.letterSpacing: 0.4
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
