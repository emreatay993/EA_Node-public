import QtQuick 2.15

Rectangle {
    id: card
    property var pane
    property string title: ""
    property string subtitle: ""
    default property alias bodyData: bodyColumn.data

    width: parent ? parent.width : implicitWidth
    radius: 12
    color: pane.cardBackgroundColor
    border.color: pane.themePalette.border
    border.width: 1
    clip: true
    implicitHeight: cardColumn.implicitHeight

    Column {
        id: cardColumn
        width: parent.width
        spacing: 0

        Rectangle {
            width: parent.width
            height: headerColumn.implicitHeight + 14
            color: pane.sectionHeaderColor

            Column {
                id: headerColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: subtitleLabel.visible ? 2 : 0

                Text {
                    text: card.title.toUpperCase()
                    color: pane.themePalette.group_title_fg
                    font.pixelSize: 10
                    font.bold: true
                    font.letterSpacing: 0.9
                    elide: Text.ElideRight
                }

                Text {
                    id: subtitleLabel
                    visible: card.subtitle.length > 0
                    text: card.subtitle
                    color: pane.themePalette.muted_fg
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }
        }

        Item {
            width: parent.width
            implicitHeight: bodyColumn.implicitHeight + 18

            Column {
                id: bodyColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                spacing: 8
            }
        }
    }
}
