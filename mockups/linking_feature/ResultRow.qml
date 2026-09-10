import QtQuick

// One row in a search/list result (omnibox results, dialog lists, node picker).
Rectangle {
    id: rrow
    property var theme
    property string kind: "node"
    property string title: ""
    property string breadcrumb: ""
    property bool current: false
    readonly property bool hovered: rmouse.containsMouse
    readonly property color tint: theme.typeColor(kind)
    signal clicked()
    signal activated()

    implicitHeight: 42
    radius: 7
    color: current ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16)
                   : (hovered ? theme.hover : "transparent")
    Behavior on color { ColorAnimation { duration: 90 } }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        spacing: 11

        Rectangle {
            width: 28; height: 28; radius: 6
            anchors.verticalCenter: parent.verticalCenter
            color: Qt.rgba(rrow.tint.r, rrow.tint.g, rrow.tint.b, 0.18)
            LinkGlyph { anchors.centerIn: parent; name: theme.typeGlyph(rrow.kind); size: 15; color: rrow.tint }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 1
            Text {
                text: rrow.title
                color: theme.appFg
                font.family: theme.fontFamily
                font.pixelSize: 13
            }
            Text {
                visible: rrow.breadcrumb.length > 0
                text: theme.typeLabel(rrow.kind) + "  ·  " + rrow.breadcrumb
                color: theme.mutedFg
                font.family: theme.fontFamily
                font.pixelSize: 11
            }
        }
    }

    MouseArea {
        id: rmouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: rrow.clicked()
        onDoubleClicked: rrow.activated()
    }
}
