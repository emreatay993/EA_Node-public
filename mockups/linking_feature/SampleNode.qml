import QtQuick

// A COREX-style node card (header + muted body text), with hover + selected
// states. Concepts overlay their own affordances (link pill, anchor, badge) as
// siblings positioned against this node.
Rectangle {
    id: node
    property var theme
    property string title: "Node"
    property string bodyText: ""
    property bool selected: false
    readonly property bool hovered: hoverArea.containsMouse
    signal clicked()

    width: 230
    height: 116
    radius: 11
    color: theme.nodeBg
    border.width: selected ? 2 : 1
    border.color: selected ? theme.accent
                           : (hovered ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.5)
                                      : theme.border)
    Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 34
        topLeftRadius: node.radius
        topRightRadius: node.radius
        bottomLeftRadius: 0
        bottomRightRadius: 0
        color: theme.nodeHeaderBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }

        LinkGlyph {
            id: hicon
            anchors.verticalCenter: parent.verticalCenter
            x: 11
            name: "node"
            size: 16
            color: theme.mutedFg
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: hicon.right
            anchors.leftMargin: 7
            anchors.right: parent.right
            anchors.rightMargin: 10
            text: node.title
            color: theme.appFg
            font.family: theme.fontFamily
            font.pixelSize: 13
            font.bold: true
            elide: Text.ElideRight
        }
    }

    Text {
        anchors.top: header.bottom
        anchors.topMargin: 10
        anchors.left: parent.left
        anchors.leftMargin: 13
        anchors.right: parent.right
        anchors.rightMargin: 13
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        text: node.bodyText
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        lineHeight: 1.2
        verticalAlignment: Text.AlignTop
        clip: true
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: node.clicked()
    }
}
