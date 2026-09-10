import QtQuick

// Small themed pill button (no Controls styling fight). Used in the top bar
// and the debugger popover.
Rectangle {
    id: btn
    property var theme
    property string text: ""
    property bool accentFill: false
    property bool enabledX: true
    signal clicked()

    implicitHeight: 30
    implicitWidth: label.implicitWidth + 26
    radius: 7
    opacity: enabledX ? 1 : 0.45
    color: accentFill
           ? (ma.pressed ? Qt.darker(theme.accent, 1.15) : (ma.containsMouse ? Qt.lighter(theme.accent, 1.08) : theme.accent))
           : (ma.pressed ? theme.pressed : (ma.containsMouse ? theme.hover : theme.panelAltBg))
    border.width: 1
    border.color: accentFill ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.0) : theme.border
    Behavior on color { ColorAnimation { duration: 110 } }

    Text {
        id: label
        anchors.centerIn: parent
        text: btn.text
        color: btn.accentFill ? btn.theme.onAccent : btn.theme.appFg
        font.family: btn.theme.fontFamily
        font.pixelSize: 12
        font.bold: btn.accentFill
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        enabled: btn.enabledX
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
