import QtQuick 2.15
import QtQuick.Controls 2.15

Button {
    id: control

    property var themePalette: ({})
    property bool primary: false
    property bool selected: false
    property real controlHeight: 36

    readonly property color accentColor: control.themePalette.accent || "#2F89FF"
    readonly property color primaryFillColor: control.themePalette.accent_strong || control.accentColor
    readonly property color foregroundColor: !control.enabled
        ? Qt.alpha(control.themePalette.muted_fg || "#95a0b8", 0.58)
        : (control.selected
            ? (control.themePalette.tab_selected_fg || control.themePalette.panel_title_fg || "#ffffff")
            : (control.themePalette.input_fg || control.themePalette.panel_title_fg || "#eef3ff"))
    readonly property color fillColor: !control.enabled
        ? Qt.alpha(control.themePalette.input_bg || control.themePalette.panel_bg || "#22242a", 0.72)
        : (control.down
            ? (control.themePalette.pressed || "#2d3139")
            : (control.selected
                ? control.primaryFillColor
                : (control.hovered
                    ? (control.themePalette.hover || "#33373f")
                    : (control.themePalette.input_bg || control.themePalette.panel_bg || "#22242a"))))
    readonly property color outlineColor: control.activeFocus || control.primary || control.selected
        ? control.accentColor
        : (control.themePalette.input_border || control.themePalette.border || "#4a4f5a")

    implicitWidth: Math.max(80, label.implicitWidth + 28)
    implicitHeight: Math.max(28, control.controlHeight)
    hoverEnabled: control.enabled
    padding: 0

    contentItem: Text {
        id: label
        text: control.text
        color: control.foregroundColor
        font.pixelSize: 12
        font.weight: control.primary || control.selected ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 6
        color: control.fillColor
        border.width: control.activeFocus || control.primary || control.selected ? 2 : 1
        border.color: control.outlineColor
    }
}
