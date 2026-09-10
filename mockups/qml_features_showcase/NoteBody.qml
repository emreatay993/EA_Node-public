import QtQuick

// A simple compute-node body: a monospace "expression" line plus a couple of
// key/value rows. Used for the Filter node (predicate) and the bypassed
// Normalize node.
Item {
    id: b
    property var theme
    property string expr: ""
    property var lines: []          // array of [key, value]
    property bool dim: false

    Column {
        anchors.fill: parent
        spacing: 7

        Rectangle {
            visible: b.expr.length > 0
            width: parent.width
            height: 24
            radius: 5
            color: b.theme.inputBg
            border.width: 1
            border.color: b.theme.border
            Text {
                anchors.fill: parent
                anchors.leftMargin: 8
                verticalAlignment: Text.AlignVCenter
                text: b.expr
                color: b.dim ? b.theme.mutedFg : b.theme.accent
                font.family: b.theme.monoFamily
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }

        Repeater {
            model: b.lines
            delegate: Row {
                required property var modelData
                width: b.width
                spacing: 6
                Text {
                    width: b.width * 0.46
                    text: modelData[0]
                    color: b.theme.mutedFg
                    font.family: b.theme.fontFamily
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
                Text {
                    text: modelData[1]
                    color: b.dim ? b.theme.mutedFg : b.theme.appFg
                    font.family: b.theme.monoFamily
                    font.pixelSize: 11
                    font.bold: true
                }
            }
        }
    }
}
