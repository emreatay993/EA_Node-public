import QtQuick

// Feature (2): generalized inline data preview — a node showing its output rows
// as a compact table right in the body (today only the tabular-input node does
// this; this generalizes it to any data-producing node).
Item {
    id: b
    property var theme
    property var headers: ["Load case", "σ_vm [MPa]", "Margin"]
    property var rows: [
        ["LC-001", "312.4", "+0.18"],
        ["LC-002", "288.1", "+0.27"],
        ["LC-003", "401.7", "-0.05"],
        ["LC-004", "356.9", "+0.04"]
    ]
    readonly property var colW: [0.40, 0.34, 0.26]

    Column {
        anchors.fill: parent
        spacing: 0

        // header
        Row {
            width: parent.width
            height: 22
            Repeater {
                model: b.headers
                delegate: Rectangle {
                    id: hcell
                    required property int index
                    required property var modelData
                    width: b.width * b.colW[index]
                    height: 22
                    color: b.theme.nodeHeaderBg
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 7
                        verticalAlignment: Text.AlignVCenter
                        text: hcell.modelData
                        color: b.theme.mutedFg
                        font.family: b.theme.fontFamily
                        font.pixelSize: 10
                        font.bold: true
                        elide: Text.ElideRight
                    }
                }
            }
        }

        // data rows
        Repeater {
            model: b.rows
            delegate: Row {
                id: rrow
                required property int index
                required property var modelData
                width: b.width
                height: 21
                Repeater {
                    model: rrow.modelData
                    delegate: Rectangle {
                        id: ccell
                        required property int index
                        required property var modelData
                        width: b.width * b.colW[index]
                        height: 21
                        color: (rrow.index % 2 === 0)
                               ? "transparent"
                               : Qt.rgba(b.theme.mutedFg.r, b.theme.mutedFg.g, b.theme.mutedFg.b, 0.06)
                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 7
                            verticalAlignment: Text.AlignVCenter
                            text: ccell.modelData
                            color: (ccell.index === 2 && String(ccell.modelData).indexOf("-") === 0)
                                   ? b.theme.stError
                                   : b.theme.appFg
                            font.family: ccell.index === 0 ? b.theme.fontFamily : b.theme.monoFamily
                            font.pixelSize: 10
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    // dimensions badge
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: dimsTxt.implicitWidth + 12
        height: 16
        radius: 8
        color: Qt.rgba(b.theme.accent.r, b.theme.accent.g, b.theme.accent.b, 0.16)
        Text {
            id: dimsTxt
            anchors.centerIn: parent
            text: "1,024 × 3"
            color: b.theme.accent
            font.family: b.theme.fontFamily
            font.pixelSize: 9
            font.bold: true
        }
    }
}
