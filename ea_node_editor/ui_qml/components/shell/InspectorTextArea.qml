import QtQuick 2.15
import QtQuick.Controls 2.15

TextArea {
    id: control
    property var pane
    implicitHeight: 118
    padding: 8
    selectByMouse: true
    wrapMode: TextEdit.Wrap
    color: pane.themePalette.input_fg
    selectionColor: pane.selectedSurfaceColor
    selectedTextColor: pane.themePalette.panel_title_fg

    background: Rectangle {
        radius: 10
        color: control.pane.themePalette.input_bg
        border.color: control.activeFocus ? control.pane.themePalette.accent : control.pane.themePalette.input_border
        border.width: 1
    }
}
