import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/StatusMockupTheme.js" as Theme

// Route 1 — Segmented Pill Cluster.
// Compact (~32px), blends into the app chrome. Every group becomes a rounded
// chip; engine state is a color-coded pill. Hairline dividers, pulsing run dot.
// The "safe modernization".
Item {
    id: root

    property string themeName: "dark"
    property var telemetry: null
    property string variantTitle: "Segmented Pill Cluster"

    readonly property var pal: Theme.shellPalette(root.themeName)
    readonly property string engineState: telemetry ? telemetry.engineState : "ready"
    readonly property color stateColor: Theme.stateColor(root.pal, root.engineState)
    readonly property real cpu: telemetry ? telemetry.cpu : 0
    readonly property real ram: telemetry ? telemetry.ram : 0
    readonly property real ramTotal: telemetry ? telemetry.ramTotal : 31.8
    readonly property bool fpsEnabled: telemetry ? telemetry.fpsEnabled : true
    readonly property real fps: telemetry ? telemetry.fps : 0
    readonly property real diskRead: telemetry ? telemetry.diskRead : 0
    readonly property real diskWrite: telemetry ? telemetry.diskWrite : 0
    readonly property int warnings: telemetry ? telemetry.warnings : 0
    readonly property int errors: telemetry ? telemetry.errors : 0

    function fpsColor() {
        if (root.fps >= 50) return root.pal.success;
        if (root.fps >= 30) return root.pal.warning;
        return root.pal.error;
    }
    function jobsModel() {
        return [
            { "dot": root.pal.accent, "value": telemetry ? telemetry.jobsR : 0 },
            { "dot": root.pal.muted_fg, "value": telemetry ? telemetry.jobsQ : 0 },
            { "dot": root.pal.success, "value": telemetry ? telemetry.jobsD : 0 },
            { "dot": root.pal.error, "value": telemetry ? telemetry.jobsF : 0 }
        ];
    }
    function metricModel() {
        var metrics = ["cpu", "ram", "disk"];
        if (root.fpsEnabled)
            metrics.push("fps");
        return metrics;
    }

    Shared.MockChrome {
        anchors.fill: parent
        palette: root.pal
        title: root.variantTitle
        footprintTag: "Compact · 32 px"
        lookTag: "Blends into chrome"
        barHeight: 32

        Rectangle {
            anchors.fill: parent
            color: root.pal.toolbar_bg

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 1
                color: Qt.alpha(root.pal.border, 0.9)
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.topMargin: 1
                spacing: 7

                // ---- Engine state pill --------------------------------------
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredHeight: 22
                    implicitWidth: engineRow.implicitWidth + 18
                    radius: 11
                    color: Qt.alpha(root.stateColor, 0.16)
                    border.width: 1
                    border.color: Qt.alpha(root.stateColor, 0.55)
                    Row {
                        id: engineRow
                        anchors.centerIn: parent
                        spacing: 6
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 8; height: 8; radius: 4
                            color: root.stateColor
                            SequentialAnimation on opacity {
                                running: root.engineState === "running"
                                loops: Animation.Infinite
                                NumberAnimation { from: 1.0; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                NumberAnimation { from: 0.3; to: 1.0; duration: 650; easing.type: Easing.InOutSine }
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: Theme.stateLabel(root.engineState)
                            color: root.pal.panel_title_fg
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 16; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.border, 0.8) }

                // ---- Jobs chip ----------------------------------------------
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredHeight: 22
                    implicitWidth: jobsRow.implicitWidth + 16
                    radius: 6
                    color: Qt.alpha(root.pal.panel_bg, 0.55)
                    Row {
                        id: jobsRow
                        anchors.centerIn: parent
                        spacing: 9
                        Repeater {
                            model: root.jobsModel()
                            delegate: Row {
                                spacing: 4
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7; height: 7; radius: 3.5
                                    color: modelData.dot
                                    opacity: modelData.value > 0 ? 1 : 0.4
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.value
                                    color: modelData.value > 0 ? root.pal.panel_title_fg : root.pal.muted_fg
                                    font.pixelSize: 11
                                    font.bold: modelData.value > 0
                                }
                            }
                        }
                    }
                }

                // ---- Metric chips (CPU / RAM / Disk / optional FPS) ---------
                Repeater {
                    model: root.metricModel()
                    delegate: Rectangle {
                        id: metricChip
                        readonly property bool hasBar: modelData === "cpu" || modelData === "ram"
                        readonly property real ratio: modelData === "cpu" ? root.cpu / 100 : (modelData === "ram" ? root.ram / root.ramTotal : 0)
                        readonly property string captionText: modelData === "cpu" ? "CPU" : (modelData === "ram" ? "RAM" : (modelData === "disk" ? "DISK" : "FPS"))
                        readonly property string valueText: modelData === "cpu"
                            ? Math.round(root.cpu) + "%"
                            : (modelData === "ram"
                                ? root.ram.toFixed(1) + " / " + root.ramTotal.toFixed(1) + " GB"
                                : (modelData === "disk"
                                    ? "R " + root.diskRead.toFixed(1) + " W " + root.diskWrite.toFixed(1)
                                    : String(Math.round(root.fps))))
                        readonly property color valueColor: modelData === "fps" ? root.fpsColor() : root.pal.panel_title_fg
                        Layout.alignment: Qt.AlignVCenter
                        Layout.preferredHeight: 22
                        implicitWidth: chipRow.implicitWidth + 16
                        radius: 6
                        color: Qt.alpha(root.pal.panel_bg, 0.55)
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 6
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: captionText
                                color: root.pal.muted_fg
                                font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.5
                            }
                            Shared.MiniBar {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: metricChip.hasBar
                                width: metricChip.hasBar ? 30 : 0
                                height: 5
                                ratio: metricChip.ratio
                                trackColor: Qt.alpha(root.pal.muted_fg, 0.22)
                                fillColor: Theme.metricColor(root.pal, metricChip.ratio)
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: valueText
                                color: valueColor
                                font.pixelSize: 11; font.bold: true
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 16; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root.pal.border, 0.8) }

                // ---- Notifications ------------------------------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 10
                    Repeater {
                        model: [
                            { "dot": root.pal.warning, "value": root.warnings },
                            { "dot": root.pal.error, "value": root.errors }
                        ]
                        delegate: Row {
                            spacing: 5
                            opacity: modelData.value > 0 ? 1 : 0.5
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 8; height: 8; radius: 4
                                color: modelData.value > 0 ? modelData.dot : "transparent"
                                border.width: modelData.value > 0 ? 0 : 1
                                border.color: root.pal.muted_fg
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.value
                                color: modelData.value > 0 ? root.pal.panel_title_fg : root.pal.muted_fg
                                font.pixelSize: 11
                                font.bold: modelData.value > 0
                            }
                        }
                    }
                }
            }
        }
    }
}
