import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root

    property int toolbarScalePercent: 100
    property real caretX: width / 2
    signal toolbarScaleRequested(int value)

    implicitWidth: 306
    width: implicitWidth
    implicitHeight: caret.height + panel.height
    height: implicitHeight

    readonly property color panelBg: "#1b1c1f"
    readonly property color fg: "#f4f5f7"
    readonly property color subFg: "#aeb6c2"

    Canvas {
        id: caret
        width: 28
        height: 12
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
        height: 82
        radius: 16
        color: root.panelBg
        border.width: 1
        border.color: "#33ffffff"

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 1
            height: 1
            color: "#1affffff"
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            anchors.topMargin: 12
            anchors.bottomMargin: 12
            spacing: 10

            Text {
                text: "Toolbar scale"
                color: root.fg
                font.pixelSize: 13
                font.bold: true
                Layout.preferredWidth: 92
                verticalAlignment: Text.AlignVCenter
            }

            Slider {
                id: sizeSlider
                Layout.fillWidth: true
                from: 75
                to: 125
                stepSize: 5
                snapMode: Slider.SnapAlways
                focusPolicy: Qt.NoFocus
                value: root.toolbarScalePercent
                onMoved: root.toolbarScaleRequested(Math.round(value))
            }

            Text {
                text: String(Math.round(sizeSlider.value)) + "%"
                color: root.subFg
                font.pixelSize: 13
                Layout.preferredWidth: 42
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
