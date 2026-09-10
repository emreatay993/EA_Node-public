import QtQuick 2.15

Rectangle {
    id: chip
    property var pane
    property string labelText: ""
    property string valueText: ""
    property real maxWidth: parent ? parent.width : metadataRow.implicitWidth

    color: "transparent"
    height: metadataRow.implicitHeight
    width: Math.min(maxWidth, metadataRow.implicitWidth)

    Row {
        id: metadataRow
        spacing: 8

        Text {
            text: chip.labelText.toUpperCase()
            anchors.verticalCenter: valuePill.verticalCenter
            color: chip.pane.themePalette.muted_fg
            font.pixelSize: 9
            font.bold: true
            font.letterSpacing: 0.6
            elide: Text.ElideRight
        }

        Rectangle {
            id: valuePill
            radius: 8
            color: chip.pane.themePalette.input_bg
            border.color: chip.pane.themePalette.input_border
            border.width: 1
            height: valueLabel.implicitHeight + 10
            width: valueLabel.implicitWidth + 18

            Text {
                id: valueLabel
                anchors.centerIn: parent
                text: chip.valueText
                color: chip.pane.themePalette.panel_title_fg
                font.pixelSize: 11
                font.bold: true
                elide: Text.ElideRight
            }
        }
    }
}
