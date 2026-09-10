import QtQuick 2.15

Rectangle {
    id: toggle
    property var pane
    property string scope: "name"
    property bool compact: false

    signal selectRequested(string nextScope)

    readonly property int buttonPaddingH: compact ? 7 : 9
    readonly property int buttonPaddingV: compact ? 3 : 4
    readonly property int buttonFontSize: compact ? 10 : 11

    radius: 5
    color: pane ? pane.themePalette.input_bg : "#22242a"
    border.color: pane ? pane.themePalette.border : "#3a3d45"
    border.width: 1
    clip: true

    implicitHeight: toggleRow.implicitHeight
    implicitWidth: toggleRow.implicitWidth
    height: implicitHeight
    width: implicitWidth

    Row {
        id: toggleRow
        anchors.fill: parent
        spacing: 0

        Repeater {
            model: [
                { id: "name", label: "Name" },
                { id: "value", label: "Value" }
            ]

            delegate: Rectangle {
                id: segment
                readonly property bool isActive: toggle.scope === modelData.id
                readonly property bool isFirst: index === 0

                width: segmentLabel.implicitWidth + toggle.buttonPaddingH * 2
                height: segmentLabel.implicitHeight + toggle.buttonPaddingV * 2

                color: isActive
                    ? (toggle.pane ? toggle.pane.themePalette.inspector_selected_bg : "#2f4a66")
                    : "transparent"

                Rectangle {
                    visible: segment.isFirst
                    width: 1
                    height: parent.height
                    anchors.right: parent.right
                    color: toggle.pane ? toggle.pane.themePalette.border : "#3a3d45"
                }

                Text {
                    id: segmentLabel
                    anchors.centerIn: parent
                    text: String(modelData.label).toUpperCase()
                    font.pixelSize: toggle.buttonFontSize
                    font.bold: segment.isActive
                    font.letterSpacing: 0.3
                    color: segment.isActive
                        ? (toggle.pane ? toggle.pane.themePalette.panel_title_fg : "#f0f4fb")
                        : (toggle.pane ? toggle.pane.themePalette.muted_fg : "#d0d5de")
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (toggle.scope !== modelData.id)
                            toggle.selectRequested(modelData.id)
                    }
                }
            }
        }
    }
}
