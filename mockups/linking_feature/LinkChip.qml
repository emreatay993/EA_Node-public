import QtQuick

// A small colored pill representing a link, tinted by link type. Used as an
// attached link on a node corner (Concept A/C) and inline for span links.
Rectangle {
    id: chip
    property var theme
    property string kind: "web"
    property string label: "example.com"
    property bool removable: false
    readonly property bool hovered: chipMouse.containsMouse
    readonly property color tint: theme.typeColor(kind)
    signal clicked()
    signal removeClicked()

    implicitHeight: 24
    implicitWidth: row.implicitWidth + 18
    height: implicitHeight
    width: implicitWidth
    radius: height / 2
    color: Qt.rgba(tint.r, tint.g, tint.b, hovered ? 0.32 : 0.18)
    border.width: 1
    border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.55)
    Behavior on color { ColorAnimation { duration: 120 } }

    // Declared BEFORE the row so the row's nested remove-MouseArea wins on top;
    // clicks elsewhere fall through to this.
    MouseArea {
        id: chipMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.clicked()
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 5
        LinkGlyph {
            anchors.verticalCenter: parent.verticalCenter
            name: theme.typeGlyph(chip.kind)
            size: 13
            color: chip.tint
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: chip.label
            color: theme.appFg
            font.family: theme.fontFamily
            font.pixelSize: 12
        }
        LinkGlyph {
            anchors.verticalCenter: parent.verticalCenter
            visible: chip.removable
            name: "x"
            size: 11
            color: theme.mutedFg
            MouseArea {
                anchors.fill: parent
                anchors.margins: -3
                cursorShape: Qt.PointingHandCursor
                onClicked: chip.removeClicked()
            }
        }
    }
}
