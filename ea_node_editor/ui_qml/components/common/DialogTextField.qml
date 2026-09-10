import QtQuick 2.15
import QtQuick.Controls 2.15
import "contrast_utils.js" as ContrastUtils

TextField {
    id: control

    property var themePalette: ({})
    property real controlHeight: 36

    implicitWidth: 160
    implicitHeight: Math.max(28, control.controlHeight)
    leftPadding: 10
    rightPadding: 10
    selectByMouse: true
    verticalAlignment: TextInput.AlignVCenter
    color: control.enabled
        ? ContrastUtils.inputForeground(control.themePalette)
        : Qt.alpha(ContrastUtils.inputForeground(control.themePalette), 0.58)
    placeholderTextColor: control.themePalette.muted_fg || "#95a0b8"
    selectionColor: ContrastUtils.inputSelectionBackground(control.themePalette)
    selectedTextColor: ContrastUtils.inputSelectedForeground(control.themePalette)
    font.pixelSize: 12

    background: Rectangle {
        radius: 6
        color: control.themePalette.input_bg || "#22242a"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus
            ? (control.themePalette.accent || "#2F89FF")
            : (control.themePalette.input_border || control.themePalette.border || "#4a4f5a")
    }
}
