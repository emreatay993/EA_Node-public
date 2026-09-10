import QtQuick

// A COREX-style node card replica with the two production details the badge
// designs must coexist with: the bottom-right RESIZE GRIP (16px box, three
// diagonal lines at 3.5px offsets, stroke 1.2 — GraphNodeResizeHandle.qml
// geometry), shown on hover of unlocked nodes, and the LOCKED header pill
// (18px / radius 9 / 9px bold — GraphNodeHeaderLayer.qml grammar). Concepts
// overlay their badges as siblings positioned against this node.
Rectangle {
    id: node
    property var theme
    property string title: "Node"
    property string bodyText: ""
    property string stateCaption: ""
    property bool locked: false
    property bool selected: false
    // Poses the hover look without a real cursor (grip visible in screenshots).
    property bool forceHover: false
    readonly property bool hovered: hoverArea.containsMouse || forceHover
    readonly property bool gripVisible: hovered && !locked
    // Corner real estate claimed by the resize grip (badge designs dodge it).
    readonly property real gripZone: 16

    width: 215
    height: 118
    radius: 11
    color: theme.nodeBg
    border.width: selected ? 2 : 1
    border.color: selected ? theme.accent
                           : (hovered ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.5)
                                      : theme.border)
    Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: 160 } }

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 30
        topLeftRadius: node.radius
        topRightRadius: node.radius
        bottomLeftRadius: 0
        bottomRightRadius: 0
        color: theme.nodeHeaderBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 11
            anchors.right: lockedPill.visible ? lockedPill.left : parent.right
            anchors.rightMargin: 8
            text: node.title
            color: theme.appFg
            font.family: theme.fontFamily
            font.pixelSize: 13
            font.bold: true
            elide: Text.ElideRight
        }

        // LOCKED pill — production header-badge grammar.
        Rectangle {
            id: lockedPill
            visible: node.locked
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: lockedText.implicitWidth + 14
            height: 18
            radius: 9
            color: "transparent"
            border.width: 1
            border.color: theme.mutedFg
            Text {
                id: lockedText
                anchors.centerIn: parent
                text: "LOCKED"
                color: theme.mutedFg
                font.family: theme.fontFamily
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 0.6
            }
        }
    }

    Text {
        anchors.top: header.bottom
        anchors.topMargin: 9
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        text: node.bodyText
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        lineHeight: 1.2
        verticalAlignment: Text.AlignTop
        clip: true
    }

    // Resize grip replica (GraphNodeResizeHandle.qml visuals; no drag).
    Canvas {
        id: grip
        width: node.gripZone
        height: node.gripZone
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: node.gripVisible
        z: 6
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            ctx.strokeStyle = String(gripColor);
            ctx.lineWidth = 1.2;
            ctx.lineCap = "round";
            for (var i = 1; i <= 3; i++) {
                var off = i * 3.5;
                ctx.beginPath();
                ctx.moveTo(width - off, height - 1);
                ctx.lineTo(width - 1, height - off);
                ctx.stroke();
            }
        }
        property color gripColor: Qt.rgba(theme.mutedFg.r, theme.mutedFg.g, theme.mutedFg.b, 0.9)
        onGripColorChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        Component.onCompleted: requestPaint()
    }

    // Caption chip under the card so each state is self-describing in shots.
    Text {
        visible: node.stateCaption.length > 0
        anchors.top: parent.bottom
        anchors.topMargin: 40   // clear of badges that hang below the bottom edge
        anchors.horizontalCenter: parent.horizontalCenter
        width: node.width + 16
        horizontalAlignment: Text.AlignHCenter
        text: node.stateCaption
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 10
        wrapMode: Text.WordWrap
        opacity: 0.85
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
    }
}
