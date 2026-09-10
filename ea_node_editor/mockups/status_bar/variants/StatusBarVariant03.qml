import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/StatusMockupTheme.js" as Theme

// Route 3 — Minimal + Reveal.
// Compact (~28px), monochrome, low-distraction. Only engine state + a condensed
// notification badges show by default; hovering the metrics affordance reveals
// CPU / RAM / disk and optional FPS detail. The quietest option.
Item {
    id: root

    property string themeName: "dark"
    property var telemetry: null
    property string variantTitle: "Minimal + Reveal"

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
    readonly property int warnings: telemetry ? telemetry.warnings : 0
    readonly property int errors: telemetry ? telemetry.errors : 0

    function fpsColor() {
        if (root.fps >= 50) return root.pal.success;
        if (root.fps >= 30) return root.pal.warning;
        return root.pal.error;
    }
    function popoverMetricModel() {
        var metrics = [
            { "cap": "CPU", "val": Math.round(root.cpu) + "%", "ratio": root.cpu / 100, "kind": "load" },
            { "cap": "RAM", "val": root.ram.toFixed(1) + " / " + root.ramTotal.toFixed(1) + " GB", "ratio": root.ram / root.ramTotal, "kind": "load" },
            { "cap": "DISK", "val": "R " + root.diskRead.toFixed(1) + " / W " + root.diskWrite.toFixed(1) + " MB/s", "ratio": Math.min(1, Math.max(root.diskRead, root.diskWrite) / 200), "kind": "disk" }
        ];
        if (root.fpsEnabled)
            metrics.push({ "cap": "FPS", "val": String(Math.round(root.fps)), "ratio": Math.min(1, root.fps / 60), "kind": "fps" });
        return metrics;
    }

    Shared.MockChrome {
        anchors.fill: parent
        palette: root.pal
        title: root.variantTitle
        footprintTag: "Compact · 28 px"
        lookTag: "Monochrome · reveal on hover"
        barHeight: 28

        Rectangle {
            anchors.fill: parent
            color: root.pal.app_bg

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 1
                color: Qt.alpha(root.pal.border, 0.7)
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 12

                // ---- Engine state (dot + quiet label) -----------------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 6
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 7; height: 7; radius: 3.5
                        color: root.stateColor
                        SequentialAnimation on opacity {
                            running: root.engineState === "running"
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.35; duration: 700; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.35; to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Theme.stateLabel(root.engineState)
                        color: root.engineState === "error" ? root.pal.error : root.pal.muted_fg
                        font.pixelSize: 11
                        font.bold: root.engineState === "error"
                    }
                }

                Item { Layout.fillWidth: true }

                // ---- Notification badges (only when present) ----------------
                Row {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 6
                    Repeater {
                        model: [
                            { "dot": root.pal.warning, "value": root.warnings },
                            { "dot": root.pal.error, "value": root.errors }
                        ]
                        delegate: Row {
                            visible: modelData.value > 0
                            spacing: 4
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: modelData.dot }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.value; color: root.pal.panel_title_fg; font.pixelSize: 11; font.bold: true }
                        }
                    }
                }

                // ---- Metrics affordance (condensed; reveals popover) --------
                Item {
                    id: metricsAffordance
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredHeight: 20
                    implicitWidth: condensedRow.implicitWidth + 16
                    property bool pinned: false
                    readonly property bool revealed: metricsHover.containsMouse || pinned

                    Rectangle {
                        anchors.fill: parent
                        radius: 5
                        color: metricsAffordance.revealed ? Qt.alpha(root.pal.muted_fg, 0.14) : "transparent"
                    }
                    Row {
                        id: condensedRow
                        anchors.centerIn: parent
                        spacing: 6
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "CPU " + Math.round(root.cpu) + "%"; color: root.pal.muted_fg; font.pixelSize: 11 }
                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 3; height: 3; radius: 1.5; color: root.pal.muted_fg; opacity: 0.6 }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: "Disk R " + root.diskRead.toFixed(1); color: root.pal.muted_fg; font.pixelSize: 11 }
                        Rectangle { visible: root.fpsEnabled; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 3; radius: 1.5; color: root.pal.muted_fg; opacity: 0.6 }
                        Text { visible: root.fpsEnabled; anchors.verticalCenter: parent.verticalCenter; text: Math.round(root.fps) + " fps"; color: root.fpsColor(); font.pixelSize: 11; font.bold: true }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: metricsAffordance.revealed ? "▾" : "▸"; color: root.pal.muted_fg; font.pixelSize: 9 }
                    }
                    MouseArea {
                        id: metricsHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: metricsAffordance.pinned = !metricsAffordance.pinned
                    }

                    // Reveal popover (floats above the bar)
                    Rectangle {
                        id: popover
                        width: 260
                        height: popoverCol.implicitHeight + 20
                        y: -height - 8
                        anchors.right: parent.right
                        radius: 8
                        color: root.pal.panel_alt_bg
                        border.width: 1
                        border.color: Qt.alpha(root.pal.border, 0.95)
                        opacity: metricsAffordance.revealed ? 1 : 0
                        visible: opacity > 0.01
                        Behavior on opacity { NumberAnimation { duration: 130 } }

                        ColumnLayout {
                            id: popoverCol
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 8
                            Repeater {
                                model: root.popoverMetricModel()
                                delegate: ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.cap; color: root.pal.muted_fg; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.5 }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.val; color: root.pal.panel_title_fg; font.pixelSize: 11; font.bold: true }
                                    }
                                    Shared.MiniBar {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 4
                                        ratio: modelData.ratio
                                        trackColor: Qt.alpha(root.pal.muted_fg, 0.2)
                                        fillColor: modelData.kind === "fps" ? root.fpsColor() : Theme.metricColor(root.pal, modelData.ratio)
                                    }
                                }
                            }
                        }
                    }
                }

            }
        }
    }
}
