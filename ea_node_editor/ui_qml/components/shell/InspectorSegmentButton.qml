import QtQuick 2.15
import QtQuick.Controls 2.15

Button {
    id: control
    property var pane
    property bool selectedStyle: false
    readonly property color fillColor: selectedStyle
        ? pane.selectedSurfaceColor
        : (down ? pane.themePalette.hover : (hovered ? pane.themePalette.hover : "transparent"))
    readonly property color outlineColor: selectedStyle ? pane.selectedOutlineColor : "transparent"
    readonly property color labelColor: selectedStyle ? pane.themePalette.panel_title_fg : pane.themePalette.muted_fg

    implicitHeight: 38
    hoverEnabled: true
    padding: 0

    contentItem: Text {
        text: control.text
        color: control.labelColor
        font.pixelSize: 11
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 9
        color: control.fillColor
        border.color: control.outlineColor
        border.width: 1
    }
}
