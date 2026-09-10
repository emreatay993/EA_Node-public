import QtQuick

// Floating rich link preview card (Concept E hover; also the preview pane body
// in Concept B). Self-sizing; cheap layered drop shadow (no MultiEffect).
Item {
    id: card
    property var theme
    property string kind: "web"
    property string title: ""
    property string subtitle: ""
    property bool addAffordance: true
    property bool deleteAffordance: false
    signal openClicked()
    signal addClicked()
    signal deleteClicked()

    implicitWidth: 272
    implicitHeight: surface.height
    width: implicitWidth
    height: implicitHeight

    Rectangle {            // drop shadow
        x: 1; y: 5
        width: surface.width
        height: surface.height
        radius: surface.radius
        color: Qt.rgba(0, 0, 0, theme.isDark ? 0.42 : 0.16)
    }

    Rectangle {
        id: surface
        width: parent.width
        height: col.implicitHeight + 28
        radius: 12
        color: theme.panelAltBg
        border.width: 1
        border.color: theme.border

        Column {
            id: col
            x: 14; y: 14
            width: parent.width - 28
            spacing: 10

            Row {
                width: parent.width
                spacing: 10
                Rectangle {
                    id: badge
                    width: 30; height: 30; radius: 7
                    property color tint: theme.typeColor(card.kind)
                    color: Qt.rgba(tint.r, tint.g, tint.b, 0.18)
                    LinkGlyph { anchors.centerIn: parent; name: theme.typeGlyph(card.kind); size: 17; color: parent.tint }
                }
                Column {
                    width: parent.width - badge.width - 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        width: parent.width
                        text: card.title
                        color: theme.appFg
                        font.family: theme.fontFamily
                        font.pixelSize: 14
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        visible: card.subtitle.length > 0
                        text: card.subtitle
                        color: theme.mutedFg
                        font.family: theme.fontFamily
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
            }

            Row {
                spacing: 8
                Rectangle {                  // Open (accent)
                    width: openRow.implicitWidth + 22
                    height: 28
                    radius: 7
                    color: openMa.containsMouse ? theme.accentStrong : theme.accent
                    Behavior on color { ColorAnimation { duration: 110 } }
                    Row {
                        id: openRow
                        anchors.centerIn: parent
                        spacing: 6
                        LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "open"; size: 14; color: theme.onAccent }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "Open"; color: theme.onAccent; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: true}
                    }
                    MouseArea { id: openMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: card.openClicked() }
                }
                Rectangle {                  // + Add link (ghost)
                    visible: card.addAffordance
                    width: addRow.implicitWidth + 20
                    height: 28
                    radius: 7
                    color: addMa.containsMouse ? theme.hover : "transparent"
                    border.width: 1
                    border.color: theme.border
                    Row {
                        id: addRow
                        anchors.centerIn: parent
                        spacing: 5
                        LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "plus"; size: 13; color: theme.mutedFg }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "Add link"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 12 }
                }
                MouseArea { id: addMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: card.addClicked() }
            }

            Rectangle {                  // Delete link (danger ghost)
                visible: card.deleteAffordance
                width: delRow.implicitWidth + 16
                height: 28
                radius: 7
                color: delMa.containsMouse ? Qt.rgba(1, 0.23, 0.23, 0.16) : "transparent"
                border.width: 1
                border.color: delMa.containsMouse ? Qt.rgba(1, 0.23, 0.23, 0.5) : theme.border
                Row {
                    id: delRow
                    anchors.centerIn: parent
                    spacing: 5
                    LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "x"; size: 13; color: delMa.containsMouse ? "#ff7a7a" : theme.mutedFg }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Delete link"
                        color: delMa.containsMouse ? "#ff7a7a" : theme.appFg
                        font.family: theme.fontFamily
                        font.pixelSize: 12
                    }
                }
                MouseArea { id: delMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: card.deleteClicked() }
            }
        }
    }
}
}
