import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/StatusMockupTheme.js" as Theme

// Route 4 — Semantic Ambient Bar.
// Compact (~30px), keeps the signature blue strip but makes color meaningful:
// a leading state strip + the whole bar tint shift with the dominant state
// (idle blue, running blue + animated sweep, paused amber, error red), with
// prominent notification pills. Brand identity, turned into at-a-glance feedback.
Item {
    id: root

    property string themeName: "dark"
    property var telemetry: null
    property string variantTitle: "Semantic Ambient Bar"

    readonly property var pal: Theme.shellPalette(root.themeName)
    readonly property string engineState: telemetry ? telemetry.engineState : "ready"
    readonly property string engineDetail: telemetry ? telemetry.engineDetail : "Idle"
    readonly property color stateColor: Theme.stateColor(root.pal, root.engineState)
    readonly property real cpu: telemetry ? telemetry.cpu : 0
    readonly property real ram: telemetry ? telemetry.ram : 0
    readonly property real ramTotal: telemetry ? telemetry.ramTotal : 31.8
    readonly property bool fpsEnabled: telemetry ? telemetry.fpsEnabled : true
    readonly property real fps: telemetry ? telemetry.fps : 0
    readonly property real diskRead: telemetry ? telemetry.diskRead : 0
    readonly property real diskWrite: telemetry ? telemetry.diskWrite : 0
    readonly property int jobsR: telemetry ? telemetry.jobsR : 0
    readonly property int jobsQ: telemetry ? telemetry.jobsQ : 0
    readonly property int jobsD: telemetry ? telemetry.jobsD : 0
    readonly property int jobsF: telemetry ? telemetry.jobsF : 0
    readonly property int warnings: telemetry ? telemetry.warnings : 0
    readonly property int errors: telemetry ? telemetry.errors : 0
    readonly property bool noIssues: root.warnings === 0 && root.errors === 0

    function barColor() {
        if (root.engineState === "error") return Qt.tint(root.pal.status_bg, Qt.alpha(root.pal.error, 0.58));
        if (root.engineState === "paused") return Qt.tint(root.pal.status_bg, Qt.alpha(root.pal.warning, 0.5));
        if (root.engineState === "running") return root.themeName === "light" ? root.pal.status_bg : Qt.lighter(root.pal.status_bg, 1.06);
        return root.pal.status_bg;
    }
    function metricsText() {
        var text = "CPU " + Math.round(root.cpu) + "%   RAM "
            + root.ram.toFixed(1) + "/" + root.ramTotal.toFixed(1) + " GB   Disk R "
            + root.diskRead.toFixed(1) + " W " + root.diskWrite.toFixed(1) + " MB/s";
        if (root.fpsEnabled)
            text += "   " + Math.round(root.fps) + " fps";
        return text;
    }

    Shared.MockChrome {
        anchors.fill: parent
        palette: root.pal
        title: root.variantTitle
        footprintTag: "Compact · 30 px"
        lookTag: "Keeps signature blue"
        barHeight: 30

        Rectangle {
            id: bar
            anchors.fill: parent
            color: root.barColor()
            clip: true
            Behavior on color { ColorAnimation { duration: 280 } }

            // Animated sweep while running
            Rectangle {
                width: 130
                height: parent.height
                visible: root.engineState === "running"
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: root.themeName === "light" ? Qt.rgba(0, 0, 0, 0.05) : Qt.rgba(1, 1, 1, 0.12) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                NumberAnimation on x {
                    running: root.engineState === "running"
                    from: -130; to: bar.width
                    duration: 1700
                    loops: Animation.Infinite
                }
            }

            // Leading state strip
            Rectangle {
                anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                width: 4
                color: root.stateColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                spacing: 12

                // ---- Engine label -------------------------------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 6
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 8; height: 8; radius: 4
                        color: root.stateColor
                        SequentialAnimation on opacity {
                            running: root.engineState === "running"
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.35; duration: 650; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.35; to: 1.0; duration: 650; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Theme.stateLabel(root.engineState)
                        color: root.pal.status_fg
                        font.pixelSize: 11; font.bold: true
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "· " + root.engineDetail
                        color: Qt.alpha(root.pal.status_fg, 0.75)
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 14; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.status_fg, 0.3) }

                // ---- Jobs (inline, status_fg) -------------------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 8
                    Repeater {
                        model: [
                            { "k": "R", "value": root.jobsR },
                            { "k": "Q", "value": root.jobsQ },
                            { "k": "D", "value": root.jobsD },
                            { "k": "F", "value": root.jobsF }
                        ]
                        delegate: Text {
                            text: modelData.k + ":" + modelData.value
                            color: Qt.alpha(root.pal.status_fg, modelData.value > 0 ? 1 : 0.6)
                            font.pixelSize: 11
                            font.bold: modelData.value > 0
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 14; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.status_fg, 0.3) }

                // ---- Metrics (inline, status_fg) ----------------------------
                Text {
                    Layout.alignment: Qt.AlignVCenter
                    text: root.metricsText()
                    color: Qt.alpha(root.pal.status_fg, 0.92)
                    font.pixelSize: 11
                }

                Item { Layout.fillWidth: true }

                // ---- Notification pills (prominent) -------------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 6
                    Text {
                        visible: root.noIssues
                        anchors.verticalCenter: parent.verticalCenter
                        text: "✓ No issues"
                        color: Qt.alpha(root.pal.status_fg, 0.8)
                        font.pixelSize: 10
                    }
                    Repeater {
                        model: [
                            { "label": "Warning", "bg": root.pal.warning, "value": root.warnings },
                            { "label": "Error", "bg": root.pal.error, "value": root.errors }
                        ]
                        delegate: Rectangle {
                            visible: modelData.value > 0
                            anchors.verticalCenter: parent.verticalCenter
                            width: pillRow.implicitWidth + 16
                            height: 20
                            radius: 10
                            color: modelData.bg
                            Row {
                                id: pillRow
                                anchors.centerIn: parent
                                spacing: 5
                                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.value; color: "#ffffff"; font.pixelSize: 11; font.bold: true }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.value === 1 ? modelData.label : modelData.label + "s"; color: "#ffffff"; font.pixelSize: 10 }
                            }
                        }
                    }
                }

            }
        }
    }
}
