import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/StatusMockupTheme.js" as Theme

// Route 2 — Live Telemetry HUD.
// Taller (~46px), blends into chrome with neon accent. CPU/RAM are animated
// sparklines, FPS is a radial gauge; all colored by green->amber->red
// thresholds. Game-engine / DAW feel; best showcases the performance identity.
Item {
    id: root

    property string themeName: "dark"
    property var telemetry: null
    property string variantTitle: "Live Telemetry HUD"

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
    readonly property var cpuHistory: telemetry ? telemetry.cpuHistory : []
    readonly property var ramHistory: telemetry ? telemetry.ramHistory : []
    readonly property var diskReadHistory: telemetry ? telemetry.diskReadHistory : []
    readonly property int jobsR: telemetry ? telemetry.jobsR : 0
    readonly property int jobsQ: telemetry ? telemetry.jobsQ : 0
    readonly property int jobsD: telemetry ? telemetry.jobsD : 0
    readonly property int jobsF: telemetry ? telemetry.jobsF : 0
    readonly property int warnings: telemetry ? telemetry.warnings : 0
    readonly property int errors: telemetry ? telemetry.errors : 0

    Connections {
        target: root.telemetry
        function onFpsChanged() { gaugeCanvas.requestPaint() }
    }

    function fpsColor() {
        if (root.fps >= 50) return root.pal.success;
        if (root.fps >= 30) return root.pal.warning;
        return root.pal.error;
    }

    Shared.MockChrome {
        anchors.fill: parent
        palette: root.pal
        title: root.variantTitle
        footprintTag: "Taller · 46 px"
        lookTag: "Blends into chrome"
        barHeight: 46

        Rectangle {
            anchors.fill: parent
            color: root.pal.panel_bg

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 1
                color: Qt.alpha(root.stateColor, 0.5)
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 16

                // ---- Engine block (accent bar + 2 lines) --------------------
                RowLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 8
                    Rectangle {
                        Layout.preferredWidth: 3
                        Layout.preferredHeight: 30
                        radius: 1.5
                        color: root.stateColor
                    }
                    ColumnLayout {
                        spacing: 1
                        RowLayout {
                            spacing: 6
                            Rectangle {
                                Layout.alignment: Qt.AlignVCenter
                                width: 7; height: 7; radius: 3.5
                                color: root.stateColor
                                SequentialAnimation on opacity {
                                    running: root.engineState === "running"
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 650; easing.type: Easing.InOutSine }
                                }
                            }
                            Text {
                                text: Theme.stateLabel(root.engineState).toUpperCase()
                                color: root.pal.panel_title_fg
                                font.pixelSize: 11; font.bold: true; font.letterSpacing: 0.8
                            }
                        }
                        Text {
                            text: root.engineDetail
                            color: root.pal.muted_fg
                            font.pixelSize: 9
                            elide: Text.ElideRight
                            Layout.maximumWidth: 150
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.border, 0.8) }

                // ---- Jobs block ---------------------------------------------
                ColumnLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 2
                    Text { text: "JOBS"; color: root.pal.muted_fg; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { "label": "R", "dot": root.pal.accent, "value": root.jobsR },
                                { "label": "Q", "dot": root.pal.muted_fg, "value": root.jobsQ },
                                { "label": "D", "dot": root.pal.success, "value": root.jobsD },
                                { "label": "F", "dot": root.pal.error, "value": root.jobsF }
                            ]
                            delegate: Row {
                                spacing: 3
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: modelData.dot; opacity: modelData.value > 0 ? 1 : 0.4 }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.value; color: modelData.value > 0 ? root.pal.panel_title_fg : root.pal.muted_fg; font.pixelSize: 12; font.bold: modelData.value > 0 }
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // ---- CPU sparkline module -----------------------------------
                Item {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 92
                    Layout.preferredHeight: 36
                    Text { anchors.left: parent.left; anchors.top: parent.top; text: "CPU"; color: root.pal.muted_fg; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Text { anchors.right: parent.right; anchors.top: parent.top; text: Math.round(root.cpu) + "%"; color: Theme.metricColor(root.pal, root.cpu / 100); font.pixelSize: 12; font.bold: true }
                    Shared.Sparkline {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 16
                        values: root.cpuHistory
                        maxValue: 100
                        strokeColor: Theme.metricColor(root.pal, root.cpu / 100)
                        fillColor: Qt.alpha(Theme.metricColor(root.pal, root.cpu / 100), 0.16)
                    }
                }

                // ---- RAM sparkline module -----------------------------------
                Item {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 116
                    Layout.preferredHeight: 36
                    Text { anchors.left: parent.left; anchors.top: parent.top; text: "RAM"; color: root.pal.muted_fg; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Text { anchors.right: parent.right; anchors.top: parent.top; text: root.ram.toFixed(1) + " GB"; color: Theme.metricColor(root.pal, root.ram / root.ramTotal); font.pixelSize: 12; font.bold: true }
                    Shared.Sparkline {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 16
                        values: root.ramHistory
                        maxValue: root.ramTotal
                        strokeColor: Theme.metricColor(root.pal, root.ram / root.ramTotal)
                        fillColor: Qt.alpha(Theme.metricColor(root.pal, root.ram / root.ramTotal), 0.16)
                    }
                }

                // ---- Disk read/write module --------------------------------
                Item {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 116
                    Layout.preferredHeight: 36
                    Text { anchors.left: parent.left; anchors.top: parent.top; text: "DISK"; color: root.pal.muted_fg; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Text { anchors.right: parent.right; anchors.top: parent.top; text: "R " + root.diskRead.toFixed(1) + " / W " + root.diskWrite.toFixed(1); color: root.pal.panel_title_fg; font.pixelSize: 10; font.bold: true }
                    Shared.Sparkline {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: 16
                        values: root.diskReadHistory
                        maxValue: Math.max(10, root.diskRead * 1.3)
                        strokeColor: root.pal.accent
                        fillColor: Qt.alpha(root.pal.accent, 0.16)
                    }
                }

                // ---- Optional FPS radial gauge -----------------------------
                Item {
                    visible: root.fpsEnabled
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: root.fpsEnabled ? 40 : 0
                    Layout.preferredHeight: 40
                    Canvas {
                        id: gaugeCanvas
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.reset();
                            ctx.clearRect(0, 0, width, height);
                            var cx = width / 2, cy = height / 2, r = width / 2 - 4;
                            var start = Math.PI * 0.75, sweep = Math.PI * 1.5;
                            ctx.lineWidth = 4; ctx.lineCap = "round";
                            ctx.beginPath();
                            ctx.arc(cx, cy, r, start, start + sweep);
                            ctx.strokeStyle = Qt.alpha(root.pal.muted_fg, 0.22);
                            ctx.stroke();
                            var ratio = Math.max(0, Math.min(1, root.fps / 60));
                            ctx.beginPath();
                            ctx.arc(cx, cy, r, start, start + sweep * ratio);
                            ctx.strokeStyle = root.fpsColor();
                            ctx.stroke();
                        }
                        Component.onCompleted: if (root.fpsEnabled) requestPaint()
                    }
                    Column {
                        anchors.centerIn: parent
                        spacing: -2
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Math.round(root.fps); color: root.pal.panel_title_fg; font.pixelSize: 13; font.bold: true }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "FPS"; color: root.pal.muted_fg; font.pixelSize: 7; font.bold: true; font.letterSpacing: 0.5 }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.border, 0.8) }

                // ---- Notifications ------------------------------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 6
                    Repeater {
                        model: [
                            { "dot": root.pal.warning, "value": root.warnings },
                            { "dot": root.pal.error, "value": root.errors }
                        ]
                        delegate: Rectangle {
                            width: notifRow.implicitWidth + 14
                            height: 22
                            radius: 11
                            color: modelData.value > 0 ? Qt.alpha(modelData.dot, 0.18) : "transparent"
                            border.width: 1
                            border.color: modelData.value > 0 ? Qt.alpha(modelData.dot, 0.55) : Qt.alpha(root.pal.muted_fg, 0.4)
                            Row {
                                id: notifRow
                                anchors.centerIn: parent
                                spacing: 4
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5; color: modelData.value > 0 ? modelData.dot : "transparent"; border.width: modelData.value > 0 ? 0 : 1; border.color: root.pal.muted_fg }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.value; color: modelData.value > 0 ? root.pal.panel_title_fg : root.pal.muted_fg; font.pixelSize: 11; font.bold: modelData.value > 0 }
                            }
                        }
                    }
                }
            }
        }
    }
}
