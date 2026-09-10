import QtQuick
import "CommentScenarios.js" as Scenarios

// Concept C — Sticky-Note Peek.
// A tiny rotated sticky protrudes from the node's RIGHT edge, parked above
// the grip zone by construction (never touches the corner). Hovering the node
// or the sticky unfolds it up-and-over the edge into a small note showing the
// author and the first words — the sticky IS the peek, no separate card.
Item {
    id: root
    property var theme
    property bool posed: false

    BadgeStageStrip { id: stage; anchors.fill: parent; theme: root.theme }

    component Sticky: Item {
        id: st
        property var target
        property var spec
        property bool posedOpen: false
        readonly property int total: Scenarios.commentCount(spec.comments)
        readonly property int openN: Scenarios.openCount(spec.comments)
        readonly property bool resolvedAll: total > 0 && openN === 0
        readonly property bool unread: spec.unread === true
        readonly property bool expanded: st.total > 0
                                         && (target.hovered || ma.containsMouse || posedOpen)

        readonly property real bottomY: target.y + target.height - target.gripZone - 8

        width: expanded ? 132 : 16
        height: expanded ? 72 : 16
        x: expanded ? target.x + target.width - width + 24
                    : target.x + target.width - 5
        y: bottomY - height
        z: expanded ? 60 : 40
        rotation: expanded ? -2 : -8
        transformOrigin: Item.BottomRight
        visible: st.total > 0
        Behavior on width { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on rotation { NumberAnimation { duration: 150 } }

        Rectangle {        // drop shadow
            x: 2; y: 3
            width: face.width
            height: face.height
            radius: 2
            color: Qt.rgba(0, 0, 0, theme.isDark ? 0.38 : 0.18)
        }
        Rectangle {
            id: face
            anchors.fill: parent
            radius: 2
            color: st.resolvedAll ? theme.successSoft
                 : st.unread ? theme.comment
                 : theme.commentSoft
            border.width: 1
            border.color: st.resolvedAll ? theme.success : theme.commentBorder
            Behavior on color { ColorAnimation { duration: 140 } }

            Rectangle {    // adhesive strip
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: st.expanded ? 8 : 5
                radius: 2
                color: Qt.rgba(0, 0, 0, 0.10)
            }

            CommentGlyph {
                visible: !st.expanded
                anchors.centerIn: parent
                name: st.resolvedAll ? "check" : "bubbleFilled"
                size: 9
                color: st.resolvedAll ? theme.success
                     : st.unread ? theme.onComment
                     : theme.comment
            }

            Column {
                visible: st.expanded
                anchors.fill: parent
                anchors.margins: 9
                anchors.topMargin: 12
                spacing: 3
                Row {
                    spacing: 5
                    Rectangle {
                        width: 15; height: 15; radius: 8
                        anchors.verticalCenter: parent.verticalCenter
                        color: Qt.rgba(0, 0, 0, 0.14)
                        Text {
                            anchors.centerIn: parent
                            text: theme.initials(Scenarios.firstOpenAuthor(st.spec.comments))
                            color: st.unread && !st.resolvedAll ? theme.onComment : theme.appFg
                            font.family: theme.fontFamily
                            font.pixelSize: 7
                            font.bold: true
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: st.resolvedAll ? "resolved"
                                             : Scenarios.firstOpenAuthor(st.spec.comments)
                                               + (st.openN > 1 ? "  ·  +" + (st.openN - 1) + " open" : "")
                        color: st.resolvedAll ? theme.success
                             : st.unread ? theme.onComment : theme.appFg
                        font.family: theme.fontFamily
                        font.pixelSize: 9
                        font.bold: true
                    }
                }
                Text {
                    width: parent.width
                    text: Scenarios.firstOpenBody(st.spec.comments)
                    color: st.resolvedAll ? theme.mutedFg
                         : st.unread ? theme.onComment : theme.inputFg
                    font.family: theme.fontFamily
                    font.pixelSize: 9
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    lineHeight: 1.1
                }
            }
        }
        MouseArea {
            id: ma
            anchors.fill: parent
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
        }
    }

    Repeater {
        model: 5
        delegate: Sticky {
            required property int index
            target: stage.nodeItems[index]
            spec: stage.specs[index]
            posedOpen: root.posed && index === 2
        }
    }

    // Ghost sticky on the empty node.
    Item {
        id: ghost
        readonly property var target: stage.nodeItems[0]
        width: 16; height: 16
        x: target.x + target.width - 5
        y: target.y + target.height - target.gripZone - 8 - height
        z: 40
        rotation: -8
        transformOrigin: Item.BottomRight
        visible: opacity > 0.01
        opacity: (target.hovered || ghostMa.containsMouse) ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Canvas {
            id: ghostFace
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.strokeStyle = String(ghost.tone);
                ctx.lineWidth = 1.2;
                ctx.setLineDash([3, 2]);
                ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
            }
            Component.onCompleted: requestPaint()
        }
        property color tone: theme.commentBorder
        onToneChanged: ghostFace.requestPaint()
        CommentGlyph { anchors.centerIn: parent; name: "plus"; size: 9; color: theme.comment }
        MouseArea { id: ghostMa; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Hover a node: the sticky unfolds into the note itself · parked above the grip zone, the corner stays free"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
