import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

Window {
    id: win
    visible: true
    width: 1180
    height: 760
    title: "Laser Pointer + Notetaking Prototype"
    color: toolbarHost.darkBackground ? "#1e1f22" : "#f7f2e8"
    palette.windowText: toolbarHost.darkBackground ? "#f2f2f2" : "#202124"
    palette.text: toolbarHost.darkBackground ? "#f2f2f2" : "#202124"
    onActiveChanged: if (!active) toolbarHost.closeLaserSubmenu()

    // ---- Tunables (locked defaults; toolbar controls remain for exploration) ----
    property int fadeDurationMs: Math.round(toolbarHost.fadeValue)
    property int idleHoldMs: Math.round(toolbarHost.idleValue)
    property real coreWidth: toolbarHost.coreValue
    property real redWidth: toolbarHost.redValue
    property real glowRadius: toolbarHost.glowValue
    property real dotRadius: toolbarHost.dotValue
    property real minDist: toolbarHost.minValue
    readonly property int maxPoints: 400
    readonly property int maxStrokes: 60
    property string laserMode: toolbarHost.lineMode ? "line" : "dot"
    property bool holdToDraw: toolbarHost.holdToDraw
    property bool fadeOnReleaseOnly: toolbarHost.fadeOnReleaseOnly
    property bool highQuality: toolbarHost.highQuality
    property bool softGlow: toolbarHost.softGlow
    readonly property color laserColor: "#ff2a2a"
    readonly property color glowColor: "#ff2a2a"
    readonly property color coreColor: "#fff2f2"
    property color panelFg: toolbarHost.darkBackground ? "#f2f2f2" : "#202124"
    readonly property bool laserActive: toolbarHost.laserActive

    // ---- Trail state: list of polylines (PathMultiline) ----
    property var strokes: []
    property bool accumulating: false
    property bool ctrlDown: false
    property bool pointerInside: false
    property real pointerX: -1000
    property real pointerY: -1000

    function isCtrl(mods) {
        return win.ctrlDown || (mods !== undefined && (mods & Qt.ControlModifier) !== 0);
    }

    function beginStroke(x, y, ctrl) {
        // Whether the previous trail has effectively faded out — read BEFORE we
        // reset opacity below, otherwise it always looks "present".
        var trailGone = trailLayer.trailOpacity <= 0.001;
        fadeAnim.stop();
        trailLayer.trailOpacity = 1.0;
        // Only discard old strokes when the previous trail is effectively gone.
        // While old lines are still visible/fading, keep them on screen and let
        // the existing idle/fade timers clean them up naturally.
        if (!ctrl && !win.accumulating && trailGone)
            win.strokes = [];
        var s = win.strokes;
        s.push([ Qt.point(x, y) ]);
        if (s.length > win.maxStrokes)
            s.shift();
        win.strokes = s.slice();
        if (ctrl)
            win.accumulating = true;
    }

    function feed(x, y) {
        fadeAnim.stop();
        trailLayer.trailOpacity = 1.0;
        if (!win.fadeOnReleaseOnly)
            idleTimer.restart();
        var s = win.strokes;
        if (s.length === 0)
            return;
        var cur = s[s.length - 1];
        if (cur.length > 0) {
            var last = cur[cur.length - 1];
            var dx = x - last.x;
            var dy = y - last.y;
            if (dx * dx + dy * dy < win.minDist * win.minDist)
                return;
        }
        cur.push(Qt.point(x, y));
        if (cur.length > win.maxPoints)
            cur.shift();
        win.strokes = s.slice();
    }

    function finishStroke(ctrl) {
        if (ctrl) {
            win.accumulating = true;
        } else {
            win.accumulating = false;
            idleTimer.restart();
        }
    }

    function onCtrlReleased() {
        win.accumulating = false;
        if (!pressArea.drawing && win.strokes.length > 0)
            idleTimer.restart();
    }

    function clearTrail() {
        win.strokes = [];
        win.accumulating = false;
        pressArea.drawing = false;
    }

    Timer {
        id: idleTimer
        interval: win.idleHoldMs
        repeat: false
        onTriggered: fadeAnim.start()
    }

    NumberAnimation {
        id: fadeAnim
        target: trailLayer
        property: "trailOpacity"
        to: 0.0
        duration: win.fadeDurationMs
        easing.type: Easing.OutCubic
        onStopped: if (trailLayer.trailOpacity === 0.0) win.clearTrail()
    }

    NotetakingBackdrop {
        id: notes
        anchors.fill: parent
        darkBackground: toolbarHost.darkBackground
    }

    LaserTrailLayer {
        id: trailLayer
        z: 10
        anchors.fill: parent
        trailOpacity: 0.0
        visible: win.laserActive || trailOpacity > 0.0
        strokes: win.strokes
        softGlow: win.softGlow
        highQuality: win.highQuality
        redWidth: win.redWidth
        coreWidth: win.coreWidth
        glowRadius: win.glowRadius
        dotRadius: win.dotRadius
        pointerX: win.pointerX
        pointerY: win.pointerY
        dotVisible: win.laserActive && win.laserMode === "dot" && win.pointerInside
        laserColor: win.laserColor
        glowColor: win.glowColor
        coreColor: win.coreColor
    }

    // ---- Input (Keys for Ctrl/Esc + MouseArea for drawing) ----
    Item {
        id: inputRoot
        z: 20
        anchors.fill: parent
        focus: true
        enabled: win.laserActive

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Control)
                win.ctrlDown = true;
        }

        Keys.onReleased: function(event) {
            if (event.key === Qt.Key_Control && !event.isAutoRepeat) {
                win.ctrlDown = false;
                win.onCtrlReleased();
            }
        }

        Keys.onEscapePressed: function(event) {
            fadeAnim.stop();
            win.clearTrail();
            trailLayer.trailOpacity = 0.0;
            event.accepted = true;
        }

        MouseArea {
            id: pressArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: win.laserMode === "dot" ? Qt.BlankCursor : Qt.CrossCursor
            property bool drawing: false

            function drawCond(buttons) {
                return win.holdToDraw ? ((buttons & Qt.LeftButton) !== 0) : true;
            }

            onEntered: function() {
                win.pointerInside = true;
            }

            onExited: function() {
                win.pointerInside = false;
                win.pointerX = -1000;
                win.pointerY = -1000;
            }

            onPressed: function(m) {
                toolbarHost.closeLaserSubmenu();
                inputRoot.forceActiveFocus();
                win.pointerInside = true;
                win.pointerX = m.x;
                win.pointerY = m.y;
                if (win.laserMode === "line" && win.holdToDraw) {
                    drawing = true;
                    win.beginStroke(m.x, m.y, win.isCtrl(m.modifiers));
                }
            }

            onPositionChanged: function(m) {
                win.pointerInside = true;
                win.pointerX = m.x;
                win.pointerY = m.y;
                if (win.laserMode !== "line")
                    return;
                if (drawCond(m.buttons)) {
                    if (!drawing) {
                        drawing = true;
                        win.beginStroke(m.x, m.y, win.isCtrl(m.modifiers));
                    } else {
                        win.feed(m.x, m.y);
                    }
                }
            }

            onReleased: function(m) {
                if (drawing) {
                    drawing = false;
                    win.finishStroke(win.isCtrl(m.modifiers));
                }
            }
        }
    }

    ToolbarHost {
        id: toolbarHost
        z: 50
        anchors.fill: parent
        onToolModeChanged: function(toolId, panelKind, shouldClearTrail) {
            if (shouldClearTrail) {
                fadeAnim.stop();
                trailLayer.trailOpacity = 0.0;
                win.clearTrail();
            }
            if (toolId === "laser")
                inputRoot.forceActiveFocus();
        }
        onLaserFocusRequested: inputRoot.forceActiveFocus()
    }
}
