import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

// Throwaway showcase shell. A faux engineering pipeline you can Play or scrub;
// each node demos a candidate QML canvas feature. One ThemePalette (Theme.qml)
// is passed by reference so Dark/Light reskins everything live.
Window {
    id: win
    visible: true
    width: 1340
    height: 892
    title: "COREX — QML Feature Showcase (mockup)"
    color: pal.appBg

    Theme { id: pal; isDark: true }

    // ---------------- run state machine ----------------
    property real runProgress: 0          // 0..1 playhead over the pipeline
    property bool playing: false
    property bool paused: false           // paused at a breakpoint
    property bool breakpointArmed: true
    property bool breakpointHit: false
    property bool faultMode: false
    property string pausedNodeId: ""
    readonly property int steps: 5

    function play() {
        if (win.runProgress >= 1) reset();
        win.paused = false;
        win.playing = true;
    }
    function continueRun() { win.paused = false; win.playing = true; }
    function reset() {
        win.playing = false; win.paused = false; win.breakpointHit = false;
        win.pausedNodeId = ""; win.runProgress = 0;
    }
    function pauseAt(id) {
        var ord = ({ A: 0, B: 1, C: 2, D: 3, E: 2, F: 4 })[id];
        win.runProgress = (ord + 0.5) / win.steps;
        win.playing = false; win.paused = true; win.breakpointHit = true; win.pausedNodeId = id;
    }
    function stepOver() {
        var seq = ["B", "C", "D", "F"];
        var i = seq.indexOf(win.pausedNodeId);
        if (i < 0 || i + 1 >= seq.length) { continueRun(); return; }
        pauseAt(seq[i + 1]);
    }

    Timer {
        interval: 24; repeat: true; running: win.playing
        onTriggered: {
            var head = win.runProgress * win.steps;
            var nextP = Math.min(1, win.runProgress + 0.0055);
            var nh = nextP * win.steps;
            if (win.breakpointArmed && !win.breakpointHit && !win.faultMode && head < 1.5 && nh >= 1.5) {
                win.runProgress = 1.5 / win.steps;
                win.breakpointHit = true; win.playing = false; win.paused = true; win.pausedNodeId = "B";
                return;
            }
            if (win.faultMode && head < 1.0 && nh >= 1.0) {
                win.runProgress = 1.0 / win.steps; win.playing = false;
                return;
            }
            win.runProgress = nextP;
            if (nextP >= 1) win.playing = false;
        }
    }

    // ---------------- top bar ----------------
    Rectangle {
        id: topBar
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 58
        color: pal.toolbarBg
        Behavior on color { ColorAnimation { duration: 200 } }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pal.border }

        Row {
            anchors.left: parent.left; anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 11
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 28; height: 28; radius: 7; color: pal.accent
                Text { anchors.centerIn: parent; text: "◇"; color: pal.onAccent; font.pixelSize: 16; font.bold: true }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "COREX · QML Feature Showcase"; color: pal.appFg; font.family: pal.fontFamily; font.pixelSize: 15; font.bold: true }
                Text { text: "candidate canvas features — Play or scrub the timeline"; color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 11 }
            }
        }

        Row {
            anchors.centerIn: parent
            spacing: 8
            PillButton {
                theme: pal
                text: win.playing ? "⏸  Pause" : (win.runProgress >= 1 ? "↻  Replay" : "▶  Run")
                accentFill: true
                onClicked: win.playing ? win.playing = false : win.play()
            }
            PillButton { theme: pal; text: "Reset"; onClicked: win.reset() }
            Item { width: 6; height: 1 }
            PillButton {
                theme: pal
                text: (win.breakpointArmed ? "◉" : "○") + "  Breakpoint"
                accentFill: win.breakpointArmed
                onClicked: { win.breakpointArmed = !win.breakpointArmed; win.reset(); }
            }
            PillButton {
                theme: pal
                text: (win.faultMode ? "⚠" : "○") + "  Fault @ Filter"
                accentFill: win.faultMode
                onClicked: { win.faultMode = !win.faultMode; win.reset(); }
            }
        }

        Row {
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Text { anchors.verticalCenter: parent.verticalCenter; text: pal.isDark ? "Dark" : "Light"; color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 12 }
            Switch { anchors.verticalCenter: parent.verticalCenter; checked: pal.isDark; onToggled: pal.isDark = checked }
        }
    }

    // ---------------- canvas ----------------
    ShowcaseCanvas {
        id: stage
        anchors { left: parent.left; right: parent.right; top: topBar.bottom; bottom: bottomBar.top }
        theme: pal
        runProgress: win.runProgress
        faultMode: win.faultMode
        paused: win.paused
        pausedNodeId: win.pausedNodeId
        onContinueRequested: win.continueRun()
        onStepRequested: win.stepOver()
    }

    // ---------------- bottom: timeline scrubber + legend ----------------
    Rectangle {
        id: bottomBar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 98
        color: pal.panelBg
        Behavior on color { ColorAnimation { duration: 200 } }
        Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: pal.border }

        Text {
            id: tlLabel
            anchors.left: parent.left; anchors.leftMargin: 18
            anchors.top: parent.top; anchors.topMargin: 12
            text: "⑥  Execution timeline"
            color: pal.appFg; font.family: pal.fontFamily; font.pixelSize: 12; font.bold: true
        }
        Text {
            anchors.left: tlLabel.right; anchors.leftMargin: 10
            anchors.verticalCenter: tlLabel.verticalCenter
            text: "drag the playhead to scrub execution state"
            color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 11
        }

        Slider {
            id: scrub
            anchors.left: parent.left; anchors.leftMargin: 18
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.top: tlLabel.bottom; anchors.topMargin: 8
            height: 22
            from: 0; to: 1
            value: win.runProgress
            onMoved: win.runProgress = value
            onPressedChanged: if (pressed) win.playing = false

            background: Rectangle {
                x: scrub.leftPadding
                y: scrub.topPadding + scrub.availableHeight / 2 - height / 2
                width: scrub.availableWidth
                height: 6
                radius: 3
                color: pal.inputBg
                border.width: 1
                border.color: pal.border
                Rectangle {
                    width: scrub.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    color: pal.accent
                }
            }
            handle: Rectangle {
                x: scrub.leftPadding + scrub.visualPosition * (scrub.availableWidth - width)
                y: scrub.topPadding + scrub.availableHeight / 2 - height / 2
                width: 16; height: 16; radius: 8
                color: scrub.pressed ? Qt.lighter(pal.accent, 1.1) : pal.accent
                border.width: 2; border.color: pal.panelBg
            }
        }

        // step labels under the track
        Item {
            anchors.left: scrub.left; anchors.right: scrub.right
            anchors.top: scrub.bottom; anchors.topMargin: 2
            height: 16
            Repeater {
                model: ["Read", "Filter", "Aggregate", "Chart", "Viewer"]
                delegate: Text {
                    required property int index
                    required property string modelData
                    x: index / 4 * (parent.width - width)
                    text: modelData
                    color: (win.runProgress * 5 >= index && win.runProgress * 5 < index + 1) ? pal.accent : pal.mutedFg
                    font.family: pal.fontFamily; font.pixelSize: 10
                    font.bold: (win.runProgress * 5 >= index && win.runProgress * 5 < index + 1)
                }
            }
        }

        // state legend (feature ⑦)
        Row {
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.bottom: parent.bottom; anchors.bottomMargin: 9
            spacing: 12
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "⑦ states:"; color: pal.mutedFg
                font.family: pal.fontFamily; font.pixelSize: 10; font.bold: true
            }
            Repeater {
                model: ["idle", "queued", "running", "done", "error", "bypassed"]
                delegate: Row {
                    required property string modelData
                    spacing: 4
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 8; height: 8; radius: 4; color: pal.stateColor(modelData)
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: pal.stateLabel(modelData); color: pal.mutedFg
                        font.family: pal.fontFamily; font.pixelSize: 10
                    }
                }
            }
        }
    }
}
