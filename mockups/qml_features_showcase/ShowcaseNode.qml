import QtQuick
import QtQuick.Effects

// A COREX-style node card that demonstrates several features at once:
//  (7) traffic-light execution state (idle/ready/queued/running/done/error/...)
//  (8) bypass / mute visual
//  (9) a breakpoint marker (the watch panel itself lives in DebuggerPopover)
//      + completion glow (MultiEffect) that pulses while running / on done.
// The body is swapped by `bodyKind` (table / note / spark / chart / viewer3d).
Item {
    id: node
    property var theme
    property string title: "Node"
    property string subtitle: ""
    property string glyph: "•"
    property string bodyKind: "note"
    property var bodyProps: ({})
    property string runState: "idle"
    property bool bypass: false
    property bool hasBreakpoint: false
    property bool breakpointActive: false
    property bool celebrateOnDone: false

    signal completed()
    onRunStateChanged: if (runState === "done") node.completed()

    readonly property color stColor: theme.stateColor(runState)
    readonly property bool glowOn: (runState === "running") || (celebrateOnDone && runState === "done")
    property real glowPulse: 1.0
    SequentialAnimation on glowPulse {
        running: node.glowOn
        loops: Animation.Infinite
        NumberAnimation { from: 1.0; to: 1.05; duration: 720; easing.type: Easing.InOutSine }
        NumberAnimation { from: 1.05; to: 1.0; duration: 720; easing.type: Easing.InOutSine }
    }

    // ---- glow (behind the card) ----
    Rectangle {
        id: glowSrc
        anchors.fill: card
        radius: card.radius
        visible: false
        color: node.stColor
    }
    MultiEffect {
        source: glowSrc
        anchors.fill: glowSrc
        autoPaddingEnabled: true
        blurEnabled: true
        blur: 1.0
        blurMax: 40
        saturation: 0.2
        opacity: node.glowOn ? 0.6 : 0.0
        visible: opacity > 0.02
        scale: node.glowPulse
        Behavior on opacity { NumberAnimation { duration: 260 } }
    }

    // ---- card ----
    Rectangle {
        id: card
        anchors.fill: parent
        radius: 11
        color: node.theme.nodeBg
        opacity: node.bypass ? 0.6 : 1.0
        border.width: (node.runState === "running" || node.runState === "error" || node.runState === "done") ? 2 : 1
        border.color: (node.runState === "idle" || node.runState === "configured")
                      ? node.theme.border : node.stColor
        Behavior on border.color { ColorAnimation { duration: 220 } }
        Behavior on opacity { NumberAnimation { duration: 220 } }

        // header
        Rectangle {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 30
            topLeftRadius: card.radius
            topRightRadius: card.radius
            color: node.theme.nodeHeaderBg

            Rectangle {              // type glyph chip
                id: chip
                anchors.verticalCenter: parent.verticalCenter
                x: 9
                width: 20; height: 20; radius: 5
                color: Qt.rgba(node.stColor.r, node.stColor.g, node.stColor.b, 0.22)
                Text {
                    anchors.centerIn: parent
                    text: node.glyph
                    color: node.stColor
                    font.family: node.theme.fontFamily
                    font.pixelSize: 12
                    font.bold: true
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: chip.right
                anchors.leftMargin: 8
                anchors.right: statePill.left
                anchors.rightMargin: 6
                spacing: -1
                Text {
                    text: node.title
                    color: node.theme.appFg
                    font.family: node.theme.fontFamily
                    font.pixelSize: 13
                    font.bold: true
                    elide: Text.ElideRight
                    width: parent.width
                }
                Text {
                    text: node.subtitle
                    color: node.theme.mutedFg
                    font.family: node.theme.monoFamily
                    font.pixelSize: 9
                    elide: Text.ElideRight
                    width: parent.width
                }
            }
            // state pill (traffic light)
            Rectangle {
                id: statePill
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                anchors.rightMargin: 8
                height: 17
                width: dotRow.implicitWidth + 14
                radius: 8
                color: Qt.rgba(node.stColor.r, node.stColor.g, node.stColor.b, 0.16)
                Row {
                    id: dotRow
                    anchors.centerIn: parent
                    spacing: 5
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 7; height: 7; radius: 4
                        color: node.stColor
                        SequentialAnimation on opacity {
                            running: node.runState === "running"
                            loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.3; duration: 520 }
                            NumberAnimation { from: 0.3; to: 1; duration: 520 }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: node.theme.stateLabel(node.runState)
                        color: node.stColor
                        font.family: node.theme.fontFamily
                        font.pixelSize: 9
                        font.bold: true
                    }
                }
            }
        }

        // body
        Item {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: header.bottom
            anchors.bottom: parent.bottom
            anchors.margins: 9
            clip: true

            Loader {
                id: bodyLoader
                anchors.fill: parent
                sourceComponent: ({
                    "table": cTable, "note": cNote, "spark": cSpark,
                    "chart": cChart, "viewer3d": cViewer
                }[node.bodyKind]) || cNote
                onLoaded: {
                    item.theme = Qt.binding(function () { return node.theme; });
                    var p = node.bodyProps;
                    if (p)
                        for (var k in p)
                            item[k] = p[k];
                }
            }
            Component { id: cTable;  TablePreviewBody {} }
            Component { id: cNote;   NoteBody {} }
            Component { id: cChart;  ChartBody {} }
            Component { id: cViewer; Viewer3DBody {} }
            Component {
                id: cSpark
                Item {
                    id: sb
                    property var theme
                    Column {
                        anchors.fill: parent
                        spacing: 3
                        Row {
                            width: parent.width
                            spacing: 8
                            Text {
                                text: "mean σ_vm"
                                color: sb.theme.mutedFg
                                font.family: sb.theme.fontFamily
                                font.pixelSize: 11
                            }
                            Text {
                                text: "331 MPa ▲6%"
                                color: sb.theme.stDone
                                font.family: sb.theme.monoFamily
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                        Sparkline {
                            width: parent.width
                            height: sb.height - 22
                            theme: sb.theme
                            data: [0.18, 0.4, 0.3, 0.52, 0.46, 0.7, 0.6, 0.86, 0.78, 0.95]
                        }
                    }
                }
            }
        }

        // bypass tag
        Rectangle {
            visible: node.bypass
            anchors.centerIn: parent
            width: byTxt.implicitWidth + 18
            height: 22
            radius: 11
            color: Qt.rgba(node.theme.stBypassed.r, node.theme.stBypassed.g, node.theme.stBypassed.b, 0.9)
            Text {
                id: byTxt
                anchors.centerIn: parent
                text: "⊘  BYPASSED"
                color: "#ffffff"
                font.family: node.theme.fontFamily
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    // ---- breakpoint marker ----
    Rectangle {
        visible: node.hasBreakpoint
        x: -5; y: -5
        width: 15; height: 15; radius: 8
        color: node.theme.stError
        border.width: 2
        border.color: node.theme.nodeBg
        z: 5
        Rectangle {                  // pulsing ring when active
            visible: node.breakpointActive
            anchors.centerIn: parent
            width: parent.width; height: parent.height; radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: node.theme.stError
            SequentialAnimation on scale {
                running: node.breakpointActive
                loops: Animation.Infinite
                NumberAnimation { from: 1.0; to: 2.4; duration: 900; easing.type: Easing.OutCubic }
            }
            SequentialAnimation on opacity {
                running: node.breakpointActive
                loops: Animation.Infinite
                NumberAnimation { from: 0.9; to: 0.0; duration: 900 }
            }
        }
    }
}
