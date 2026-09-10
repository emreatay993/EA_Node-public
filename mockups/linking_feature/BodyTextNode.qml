import QtQuick

// SampleNode variant whose body is a selectable, rich-text TextEdit. This is the
// linchpin for span-as-source: text can be selected (Concept A/D) and already
// linked spans render as accent-underlined <a> markup (Concept E).
Rectangle {
    id: node
    property var theme
    property string title: "Project Brief"
    property string bodyHtml: ""
    property bool selected: false
    readonly property bool hovered: hoverArea.containsMouse || linkHover.hovered
    property alias textEdit: body
    readonly property bool hasSelection: body.selectionStart !== body.selectionEnd
    signal clicked()
    signal selectionChanged(string text)
    signal linkHovered(string href)

    width: 320
    height: 190
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
            name: "document"
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
        // clicking the header selects the node (the body is reserved for text selection)
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: node.clicked()
        }
    }

    // Node hover tracker for the non-body region (NoButton — never steals press).
    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }

    TextEdit {
        id: body
        anchors.top: header.bottom
        anchors.topMargin: 9
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        readOnly: true
        selectByMouse: true
        persistentSelection: true
        wrapMode: TextEdit.WordWrap
        textFormat: TextEdit.RichText
        color: theme.appFg
        selectionColor: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.35)
        selectedTextColor: theme.appFg
        font.family: theme.fontFamily
        font.pixelSize: 13
        text: node.bodyHtml
        onSelectedTextChanged: node.selectionChanged(selectedText)

        // Link-hover detection via a passive HoverHandler — it never grabs the
        // press, so mouse text-selection (Concept A/D) is fully preserved while
        // we read TextEdit.linkAt() at the hover position (Concept E).
        property string curLink: ""
        function updateLink() {
            var l = linkHover.hovered
                ? body.linkAt(linkHover.point.position.x, linkHover.point.position.y) : "";
            if (l !== curLink) { curLink = l; node.linkHovered(l); }
        }
        HoverHandler {
            id: linkHover
            cursorShape: body.curLink !== "" ? Qt.PointingHandCursor : Qt.IBeamCursor
            onPointChanged: body.updateLink()
            onHoveredChanged: body.updateLink()
        }
    }
}
