import QtQuick

// Feature (9): node-level debugger overlay. When the run pauses at a breakpoint,
// this card shows the paused node's watched port values + Continue / Step Over —
// the visual debugging COREX lacks today (it only has global pause/resume).
Rectangle {
    id: pop
    property var theme
    property string nodeTitle: ""
    property var watch: []          // array of [port, value]
    signal continueClicked()
    signal stepClicked()

    width: 232
    height: head.height + watchCol.height + btnRow.height + 34
    radius: 10
    color: theme.panelAltBg
    border.width: 1
    border.color: theme.accent
    opacity: 0
    scale: 0.96
    states: State {
        name: "shown"
        when: pop.visible
        PropertyChanges { target: pop; opacity: 1; scale: 1 }
    }
    transitions: Transition {
        NumberAnimation { properties: "opacity,scale"; duration: 160; easing.type: Easing.OutCubic }
    }

    // soft shadow-ish backdrop
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        radius: parent.radius + 1
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(pop.theme.accent.r, pop.theme.accent.g, pop.theme.accent.b, 0.25)
        z: -1
    }

    Column {
        id: head
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 11
        spacing: 1
        Row {
            spacing: 6
            Text {
                text: "⏸"
                color: pop.theme.accent
                font.pixelSize: 13
            }
            Text {
                text: "Paused at breakpoint"
                color: pop.theme.appFg
                font.family: pop.theme.fontFamily
                font.pixelSize: 12
                font.bold: true
            }
        }
        Text {
            text: pop.nodeTitle
            color: pop.theme.mutedFg
            font.family: pop.theme.fontFamily
            font.pixelSize: 10
        }
    }

    Column {
        id: watchCol
        anchors.top: head.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 8
        anchors.leftMargin: 11
        anchors.rightMargin: 11
        spacing: 3

        Text {
            text: "WATCH"
            color: pop.theme.mutedFg
            font.family: pop.theme.fontFamily
            font.pixelSize: 9
            font.bold: true
        }
        Repeater {
            model: pop.watch
            delegate: Rectangle {
                required property var modelData
                width: watchCol.width
                height: 19
                radius: 4
                color: pop.theme.inputBg
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData[0]
                    color: pop.theme.mutedFg
                    font.family: pop.theme.monoFamily
                    font.pixelSize: 10
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData[1]
                    color: pop.theme.accent
                    font.family: pop.theme.monoFamily
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
    }

    Row {
        id: btnRow
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 11
        spacing: 7
        PillButton {
            theme: pop.theme
            text: "Step over"
            onClicked: pop.stepClicked()
        }
        PillButton {
            theme: pop.theme
            text: "Continue ▶"
            accentFill: true
            onClicked: pop.continueClicked()
        }
    }
}
