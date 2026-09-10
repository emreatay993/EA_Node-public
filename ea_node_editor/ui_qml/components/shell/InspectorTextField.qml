import QtQuick 2.15
import QtQuick.Controls 2.15

TextField {
    id: control
    property var pane
    implicitHeight: 34
    padding: 8
    selectByMouse: true
    color: pane.themePalette.input_fg
    selectionColor: pane.selectedSurfaceColor
    selectedTextColor: pane.themePalette.panel_title_fg

    background: Rectangle {
        radius: 9
        color: control.pane.themePalette.input_bg
        border.color: control.activeFocus ? control.pane.themePalette.accent : control.pane.themePalette.input_border
        border.width: 1
    }
}
