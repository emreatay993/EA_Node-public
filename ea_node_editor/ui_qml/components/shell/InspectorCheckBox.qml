import QtQuick 2.15
import QtQuick.Controls 2.15

CheckBox {
    id: control
    property var pane
    hoverEnabled: true
    spacing: 8
    padding: 0

    indicator: Rectangle {
        implicitWidth: 16
        implicitHeight: 16
        radius: 4
        color: control.checked ? control.pane.themePalette.accent : control.pane.themePalette.input_bg
        border.color: control.checked ? control.pane.themePalette.accent : control.pane.themePalette.input_border
        border.width: 1

        Text {
            anchors.centerIn: parent
            text: control.checked ? "✓" : ""
            color: control.checked ? control.pane.themePalette.panel_bg : "transparent"
            font.pixelSize: 10
            font.bold: true
        }
    }

    contentItem: Text {
        text: control.text
        visible: text.length > 0
        leftPadding: control.indicator.width + control.spacing
        color: control.pane.themePalette.input_fg
        font.pixelSize: 11
        verticalAlignment: Text.AlignVCenter
    }
}
