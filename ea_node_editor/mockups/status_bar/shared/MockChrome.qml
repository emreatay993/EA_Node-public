import QtQuick 2.15

// Shared framing for every status-bar route: a titled card containing a small
// "application window" (faint node-graph content) with a bottom overlay slot
// where each design docks its bar. Identical framing across all five panels so
// the comparison isolates the bar design itself.
Rectangle {
    id: chrome

    property var palette: ({})
    property string title: "Variant"
    property string footprintTag: ""
    property string lookTag: ""
    property real barHeight: 28
    // Status-bar markup is declared as children and reparented into the slot.
    default property alias barContent: barSlot.data

    readonly property var pal: chrome.palette

    color: pal.panel_alt_bg || "#24262c"
    radius: 10
    border.width: 1
    border.color: Qt.alpha(pal.border || "#3a3d45", 0.85)
    clip: true

    // ---- Header: title + footprint/look tags -------------------------------
    Item {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        height: 46

        Text {
            id: titleText
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: chrome.title
            color: pal.panel_title_fg || "#f0f4fb"
            font.pixelSize: 14
            font.bold: true
            elide: Text.ElideRight
            width: Math.min(implicitWidth, parent.width - tagRow.width - 14)
        }

        Row {
            id: tagRow
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Repeater {
                model: [chrome.footprintTag, chrome.lookTag].filter(function (t) { return t && t.length > 0; })
                delegate: Rectangle {
                    height: 20
                    width: tagLabel.implicitWidth + 16
                    radius: 10
                    color: Qt.alpha(pal.toolbar_bg || "#2a2b30", 0.9)
                    border.width: 1
                    border.color: Qt.alpha(pal.border || "#3a3d45", 0.8)
                    Text {
                        id: tagLabel
                        anchors.centerIn: parent
                        text: modelData
                        color: pal.muted_fg || "#d0d5de"
                        font.pixelSize: 10
                    }
                }
            }
        }
    }

    // ---- Mock application window --------------------------------------------
    Rectangle {
        id: windowMock
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.bottomMargin: 14
        radius: 8
        clip: true
        color: pal.canvas_bg || "#1d1f24"
        border.width: 1
        border.color: Qt.alpha(pal.border || "#3a3d45", 0.7)

        // Faint dotted grid to suggest the node canvas.
        Canvas {
            anchors.fill: parent
            opacity: 0.6
            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                ctx.clearRect(0, 0, width, height);
                ctx.fillStyle = pal.canvas_minor_grid || "#2b2f38";
                var gap = 22;
                for (var y = gap; y < height; y += gap) {
                    for (var x = gap; x < width; x += gap) {
                        ctx.beginPath();
                        ctx.arc(x, y, 1.0, 0, Math.PI * 2);
                        ctx.fill();
                    }
                }
            }
            Component.onCompleted: requestPaint()
        }

        // A couple of muted node cards + a connector, purely contextual.
        Rectangle {
            x: 38; y: 30; width: 116; height: 56; radius: 7
            color: Qt.alpha(pal.panel_bg || "#1b1d22", 0.95)
            border.width: 1
            border.color: Qt.alpha(pal.accent || "#60CDFF", 0.45)
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 18; radius: 7
                color: Qt.alpha(pal.accent || "#60CDFF", 0.22)
            }
        }
        Rectangle {
            x: 214; y: 92; width: 116; height: 56; radius: 7
            color: Qt.alpha(pal.panel_bg || "#1b1d22", 0.95)
            border.width: 1
            border.color: Qt.alpha(pal.border || "#3a3d45", 0.9)
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 18; radius: 7
                color: Qt.alpha(pal.muted_fg || "#d0d5de", 0.14)
            }
        }
        Canvas {
            anchors.fill: parent
            opacity: 0.7
            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                ctx.strokeStyle = pal.accent || "#60CDFF";
                ctx.lineWidth = 1.6;
                ctx.beginPath();
                ctx.moveTo(154, 58);
                ctx.bezierCurveTo(190, 58, 178, 120, 214, 120);
                ctx.stroke();
            }
            Component.onCompleted: requestPaint()
        }

        // ---- Bottom overlay slot: each design docks its bar here ------------
        Item {
            id: barSlot
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: chrome.barHeight
            z: 10
        }
    }
}
