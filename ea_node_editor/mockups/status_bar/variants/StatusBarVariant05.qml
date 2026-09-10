import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/StatusMockupTheme.js" as Theme

// Route 5 — Floating Control Dock.
// Taller slot (~60px), keeps blue as an elevated accent-glass module: a detached,
// rounded, shadowed dock that floats above the window edge with separated metric
// cards. Most distinct from a full-width strip.
Item {
    id: root

    property string themeName: "dark"
    property var telemetry: null
    property string variantTitle: "Floating Control Dock"

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
    readonly property int jobsR: telemetry ? telemetry.jobsR : 0
    readonly property int jobsQ: telemetry ? telemetry.jobsQ : 0
    readonly property int jobsD: telemetry ? telemetry.jobsD : 0
    readonly property int jobsF: telemetry ? telemetry.jobsF : 0
    readonly property int warnings: telemetry ? telemetry.warnings : 0
    readonly property int errors: telemetry ? telemetry.errors : 0

    function fpsColor() {
        if (root.fps >= 50) return root.pal.success;
        if (root.fps >= 30) return root.pal.warning;
        return root.pal.error;
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
        footprintTag: "Taller · floating 44 px"
        lookTag: "Keeps blue · elevated glass"
        barHeight: 60

        // The slot is transparent; the dock floats inside it with margins.
        Item {
            anchors.fill: parent

            // ---- Soft shadow (stacked translucent layers) -------------------
            Rectangle {
                anchors.fill: dock
                anchors.topMargin: 5
                anchors.leftMargin: -1
                anchors.rightMargin: -1
                radius: dock.radius + 2
                color: Qt.rgba(0, 0, 0, root.themeName === "light" ? 0.10 : 0.28)
            }
            Rectangle {
                anchors.fill: dock
                anchors.topMargin: 2
                radius: dock.radius + 1
                color: Qt.rgba(0, 0, 0, root.themeName === "light" ? 0.06 : 0.18)
            }

            // ---- The floating dock -----------------------------------------
            Rectangle {
                id: dock
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.bottomMargin: 9
                height: 44
                radius: 13
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.lighter(root.pal.status_bg, root.themeName === "light" ? 1.02 : 1.10) }
                    GradientStop { position: 1.0; color: root.pal.status_bg }
                }
                border.width: 1
                border.color: Qt.alpha(root.pal.accent, root.themeName === "light" ? 0.5 : 0.45)

                // Top highlight line for the "glass" feel
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.leftMargin: dock.radius; anchors.rightMargin: dock.radius
                    height: 1
                    color: Qt.alpha(root.pal.status_fg, 0.18)
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 7

                    // ---- Engine state card ----------------------------------
                    Rectangle {
                        Layout.alignment: Qt.AlignVCenter
                        Layout.preferredHeight: 30
                        implicitWidth: engineRow.implicitWidth + 18
                        radius: 8
                        color: Qt.alpha(root.pal.status_fg, 0.12)
                        Row {
                            id: engineRow
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 9; height: 9; radius: 4.5
                                color: root.stateColor
                                SequentialAnimation on opacity {
                                    running: root.engineState === "running"
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1.0; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.3; to: 1.0; duration: 650; easing.type: Easing.InOutSine }
                                }
                            }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: Theme.stateLabel(root.engineState); color: root.pal.status_fg; font.pixelSize: 11; font.bold: true }
                        }
                    }

                    // ---- Jobs card ------------------------------------------
                    Rectangle {
                        Layout.alignment: Qt.AlignVCenter
                        Layout.preferredHeight: 30
                        implicitWidth: jobsCol.implicitWidth + 18
                        radius: 8
                        color: Qt.alpha(root.pal.status_fg, 0.12)
                        Column {
                            id: jobsCol
                            anchors.centerIn: parent
                            spacing: 0
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "JOBS"; color: Qt.alpha(root.pal.status_fg, 0.7); font.pixelSize: 7; font.bold: true; font.letterSpacing: 1 }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "R" + root.jobsR + " Q" + root.jobsQ + " D" + root.jobsD + " F" + root.jobsF
                                color: root.pal.status_fg; font.pixelSize: 11; font.bold: true
                            }
                        }
                    }

                    // ---- Metric cards (CPU / RAM / Disk / optional FPS) -----
                    Repeater {
                        model: root.metricModel()
                        delegate: Rectangle {
                            readonly property string captionText: modelData === "cpu" ? "CPU" : (modelData === "ram" ? "RAM" : (modelData === "disk" ? "DISK" : "FPS"))
                            readonly property string valueText: modelData === "cpu"
                                ? Math.round(root.cpu) + "%"
                                : (modelData === "ram"
                                    ? root.ram.toFixed(1) + " / " + root.ramTotal.toFixed(1) + " GB"
                                    : (modelData === "disk"
                                        ? "R " + root.diskRead.toFixed(1) + " W " + root.diskWrite.toFixed(1)
                                        : String(Math.round(root.fps))))
                            readonly property color valueColor: modelData === "fps" ? root.fpsColor() : root.pal.status_fg
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredHeight: 30
                            implicitWidth: cardCol.implicitWidth + 18
                            radius: 8
                            color: Qt.alpha(root.pal.status_fg, 0.12)
                            Column {
                                id: cardCol
                                anchors.centerIn: parent
                                spacing: 0
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: captionText; color: Qt.alpha(root.pal.status_fg, 0.7); font.pixelSize: 7; font.bold: true; font.letterSpacing: 1 }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: valueText; color: valueColor; font.pixelSize: 11; font.bold: true }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    // ---- Notification badges --------------------------------
                    Row {
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 5
                        Repeater {
                            model: [
                                { "bg": root.pal.warning, "value": root.warnings },
                                { "bg": root.pal.error, "value": root.errors }
                            ]
                            delegate: Rectangle {
                                visible: modelData.value > 0
                                anchors.verticalCenter: parent.verticalCenter
                                width: 24; height: 24; radius: 12
                                color: modelData.bg
                                Text { anchors.centerIn: parent; text: modelData.value; color: "#ffffff"; font.pixelSize: 12; font.bold: true }
                            }
                        }
                    }

                }
            }
        }
    }
}
