import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Laser-pointer submenu: a popover anchored under the laser toolbar button.
// Primary choice (Dot / Line) is surfaced as big cards; everything else from
// the old controls panel lives under the "Advanced settings" disclosure.
Item {
    id: root

    // ---- Public state (consumed by Main.qml; names match the old panel) ----
    property bool lineMode: true
    property string statusText: "Laser pointer active. Drag on the notes to draw."
    property real caretX: width / 2
    property real maxHeight: 700
    property bool advancedOpen: false

    property alias fadeValue: fadeSlider.value
    property alias idleValue: idleSlider.value
    property alias minValue: minSlider.value
    property alias coreValue: coreSlider.value
    property alias redValue: redSlider.value
    property alias glowValue: glowSlider.value
    property alias dotValue: dotSlider.value
    property alias holdToDraw: holdChk.checked
    property alias fadeOnReleaseOnly: releaseChk.checked
    property alias highQuality: hqChk.checked
    property alias softGlow: softChk.checked
    property alias darkBackground: darkBg.checked

    readonly property color panelBg: "#1b1c1f"
    readonly property color fg: "#f4f5f7"
    readonly property color subFg: "#aeb6c2"
    readonly property int pad: 26
    readonly property real contentWidth: width - pad * 2

    implicitWidth: 560
    width: implicitWidth
    implicitHeight: caret.height + panel.height
    height: implicitHeight

    // ---- Styled sub-components (declared before use) ----
    component Check: CheckBox {
        focusPolicy: Qt.NoFocus
        Layout.fillWidth: true
        contentItem: Text {
            text: parent.text
            color: root.fg
            font.pixelSize: 13
            leftPadding: parent.indicator.width + 8
            verticalAlignment: Text.AlignVCenter
        }
    }

    component Row2: RowLayout {
        id: r2
        property string label: ""
        property alias from: sld.from
        property alias to: sld.to
        property alias step: sld.stepSize
        property alias value: sld.value
        spacing: 10
        Layout.fillWidth: true

        Text {
            text: r2.label
            color: root.fg
            font.pixelSize: 13
            Layout.preferredWidth: 70
        }
        Slider {
            id: sld
            Layout.fillWidth: true
            focusPolicy: Qt.NoFocus
        }
        Text {
            text: Number(sld.value).toFixed(sld.stepSize < 1 ? 1 : 0)
            color: root.fg
            font.pixelSize: 13
            Layout.preferredWidth: 38
            horizontalAlignment: Text.AlignRight
        }
    }

    // ---- Caret pointing up to the laser button ----
    Canvas {
        id: caret
        width: 32
        height: 13
        x: Math.max(14, Math.min(root.width - 14 - width, root.caretX - width / 2))
        onPaint: {
            var c = getContext("2d");
            c.clearRect(0, 0, width, height);
            c.fillStyle = root.panelBg;
            c.beginPath();
            c.moveTo(0, height);
            c.lineTo(width / 2, 0);
            c.lineTo(width, height);
            c.closePath();
            c.fill();
        }
    }

    Rectangle {
        id: panel
        anchors.top: caret.bottom
        anchors.topMargin: -1
        width: root.width
        radius: 22
        color: root.panelBg
        border.width: 1
        border.color: "#33ffffff"
        clip: true
        height: Math.min(content.implicitHeight + root.pad * 2, root.maxHeight - caret.height)
        Behavior on height { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }

        Flickable {
            id: flick
            anchors.fill: parent
            clip: true
            contentWidth: width
            contentHeight: content.implicitHeight + root.pad * 2
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            ScrollIndicator.vertical: ScrollIndicator { }

            Column {
                id: content
                x: root.pad
                y: root.pad
                width: root.contentWidth
                spacing: 18

                Text {
                    text: "Laser Pointer"
                    color: root.fg
                    font.pixelSize: 21
                    font.bold: true
                }

                Row {
                    spacing: 16

                    // ---- Dot card ----
                    Rectangle {
                        width: (root.contentWidth - 16) / 2
                        height: 150
                        radius: 16
                        color: !root.lineMode ? "#33ffffff" : (dotMA.containsMouse ? "#17ffffff" : "#0bffffff")
                        border.width: !root.lineMode ? 1.5 : 1
                        border.color: !root.lineMode ? "#85ffffff" : "#22ffffff"

                        Canvas {
                            width: 72; height: 72
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 24
                            onPaint: {
                                var c = getContext("2d");
                                c.clearRect(0, 0, width, height);
                                var cx = width / 2, cy = height / 2, R = width * 0.46;
                                var g = c.createRadialGradient(cx, cy, 0, cx, cy, R);
                                g.addColorStop(0, "#fff3ef");
                                g.addColorStop(0.22, "#ff4438");
                                g.addColorStop(0.55, "#80ff2a2a");
                                g.addColorStop(1, "#00ff2a2a");
                                c.fillStyle = g;
                                c.beginPath();
                                c.arc(cx, cy, R, 0, Math.PI * 2);
                                c.fill();
                            }
                        }
                        Text {
                            text: "Dot"
                            color: root.fg
                            font.pixelSize: 17
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 16
                        }
                        MouseArea {
                            id: dotMA
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.lineMode = false
                        }
                    }

                    // ---- Line card ----
                    Rectangle {
                        width: (root.contentWidth - 16) / 2
                        height: 150
                        radius: 16
                        color: root.lineMode ? "#33ffffff" : (lineMA.containsMouse ? "#17ffffff" : "#0bffffff")
                        border.width: root.lineMode ? 1.5 : 1
                        border.color: root.lineMode ? "#85ffffff" : "#22ffffff"

                        Canvas {
                            width: 150; height: 64
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 30
                            onPaint: {
                                var c = getContext("2d");
                                c.clearRect(0, 0, width, height);
                                c.lineCap = "round";
                                c.lineJoin = "round";
                                function curve() {
                                    c.beginPath();
                                    c.moveTo(0.14 * width, 0.66 * height);
                                    c.bezierCurveTo(0.40 * width, 0.10 * height, 0.62 * width, 0.10 * height, 0.88 * width, 0.50 * height);
                                    c.stroke();
                                }
                                c.strokeStyle = "#5cff2a2a"; c.lineWidth = 13; curve();
                                c.strokeStyle = "#ff4438"; c.lineWidth = 6; curve();
                                c.strokeStyle = "#fff3ef"; c.lineWidth = 2; curve();
                            }
                        }
                        Text {
                            text: "Line"
                            color: root.fg
                            font.pixelSize: 17
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 16
                        }
                        MouseArea {
                            id: lineMA
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.lineMode = true
                        }
                    }
                }

                // ---- Advanced settings disclosure ----
                Rectangle { width: root.contentWidth; height: 1; color: "#1fffffff" }

                Item {
                    width: root.contentWidth
                    height: 26
                    Text {
                        id: advLabel
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Advanced settings"
                        color: root.fg
                        font.pixelSize: 14
                        font.bold: true
                    }
                    ToolbarIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: advLabel.right
                        anchors.leftMargin: 6
                        iconName: "chevron"
                        size: 20
                        strokeColor: root.fg
                        rotation: root.advancedOpen ? 180 : 0
                        Behavior on rotation { NumberAnimation { duration: 130 } }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.advancedOpen = !root.advancedOpen
                    }
                }

                ColumnLayout {
                    id: advanced
                    width: root.contentWidth
                    visible: root.advancedOpen
                    spacing: 8

                    Check { id: holdChk; text: "Hold left button to draw (off = hover-follow)"; checked: true }
                    Check { id: releaseChk; text: "Fade only on release (off = fade on pause)"; checked: true }
                    Check { id: hqChk; text: "High-quality strokes (CurveRenderer)"; checked: true }
                    Check { id: softChk; text: "Soft glow (GPU blur)"; checked: true }
                    Check { id: darkBg; text: "Dark background"; checked: true }

                    Row2 { id: fadeSlider; label: "Fade ms"; from: 80; to: 1200; step: 10; value: 760 }
                    Row2 { id: idleSlider; label: "Idle ms"; from: 0; to: 500; step: 10; value: 110 }
                    Row2 { id: minSlider; label: "Min px"; from: 0; to: 8; step: 0.5; value: 0.5 }
                    Row2 { id: coreSlider; label: "Core w"; from: 0.5; to: 6; step: 0.5; value: 2.5 }
                    Row2 { id: redSlider; label: "Red w"; from: 2; to: 18; step: 0.5; value: 12 }
                    Row2 { id: glowSlider; label: "Glow"; from: 0; to: 48; step: 1; value: 23 }
                    Row2 { id: dotSlider; label: "Dot r"; from: 3; to: 22; step: 1; value: 4 }

                    Text {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        wrapMode: Text.WordWrap
                        color: root.subFg
                        font.pixelSize: 12
                        text: "Ctrl + left-drag pins multiple lines; release Ctrl to dissolve all. Esc clears."
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: "#c7d8ff"
                        font.pixelSize: 12
                        text: root.statusText
                    }
                }
            }
        }

        // top inner highlight (kept above the flickable content)
        Rectangle {
            anchors { left: parent.left; right: parent.right; top: parent.top }
            anchors.margins: 1
            height: 1
            color: "#1affffff"
        }
    }
}
