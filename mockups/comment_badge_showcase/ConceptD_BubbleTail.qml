import QtQuick
import "CommentScenarios.js" as Scenarios

// Concept D — Bubble Tail (the zero-conflict variant).
// A miniature chat bubble floats fully OUTSIDE the node, diagonally off the
// lower-right corner, with a small tail pointing back at it — the resize-grip
// corner is never touched. Unread comments announce themselves with a one-
// shot pulse + halo (frozen under --shot poses). Hovering opens the shared
// peek card; the empty node grows a ghost add-bubble on hover.
Item {
    id: root
    property var theme
    property bool posed: false

    BadgeStageStrip { id: stage; anchors.fill: parent; theme: root.theme }

    component TailBubble: Item {
        id: bub
        property var target
        property var spec
        readonly property int total: Scenarios.commentCount(spec.comments)
        readonly property int openN: Scenarios.openCount(spec.comments)
        readonly property bool resolvedAll: total > 0 && openN === 0
        readonly property bool unread: spec.unread === true

        width: 26
        height: 22
        x: target.x + target.width + 7
        y: target.y + target.height + 4
        z: 40
        visible: bub.total > 0

        readonly property color fillColor: bub.resolvedAll ? theme.successSoft
                                         : bub.unread ? theme.comment
                                         : theme.commentSoft
        readonly property color edgeColor: bub.resolvedAll ? theme.success
                                         : bub.unread ? Qt.rgba(1, 1, 1, theme.isDark ? 0.22 : 0.0)
                                         : theme.commentBorder
        readonly property color fgColor: bub.resolvedAll ? theme.success
                                       : bub.unread ? theme.onComment
                                       : theme.comment

        // Expanding halo behind the bubble (one-shot unread announcement).
        Rectangle {
            id: halo
            anchors.centerIn: body
            width: body.width
            height: body.height
            radius: body.radius
            color: "transparent"
            border.width: 2
            border.color: theme.comment
            opacity: 0
        }

        Item {
            id: body
            anchors.fill: parent
            readonly property real radius: 8

            Rectangle {    // tail pointing back at the node corner
                width: 9; height: 9
                x: -2
                y: -2
                rotation: 45
                color: bub.fillColor
                border.width: 1
                border.color: bub.edgeColor
                Behavior on color { ColorAnimation { duration: 140 } }
            }
            Rectangle {    // bubble body
                anchors.fill: parent
                radius: body.radius
                color: bub.fillColor
                border.width: 1
                border.color: bub.edgeColor
                Behavior on color { ColorAnimation { duration: 140 } }
                Row {
                    anchors.centerIn: parent
                    spacing: 3
                    CommentGlyph {
                        visible: bub.resolvedAll
                        anchors.verticalCenter: parent.verticalCenter
                        name: "check"; size: 10; color: bub.fgColor
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: bub.total
                        color: bub.fgColor
                        font.family: theme.fontFamily
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }
        }

        SequentialAnimation {
            id: pulse
            running: bub.unread && bub.visible && !root.posed
            loops: 2
            ParallelAnimation {
                SequentialAnimation {
                    NumberAnimation { target: body; property: "scale"; from: 1.0; to: 1.18; duration: 220; easing.type: Easing.OutCubic }
                    NumberAnimation { target: body; property: "scale"; to: 1.0; duration: 260; easing.type: Easing.OutBack }
                }
                SequentialAnimation {
                    PropertyAction { target: halo; property: "scale"; value: 1.0 }
                    PropertyAction { target: halo; property: "opacity"; value: 0.55 }
                    ParallelAnimation {
                        NumberAnimation { target: halo; property: "scale"; to: 2.1; duration: 480; easing.type: Easing.OutCubic }
                        NumberAnimation { target: halo; property: "opacity"; to: 0; duration: 480 }
                    }
                }
            }
            PauseAnimation { duration: 900 }
        }

        MouseArea {
            anchors.fill: parent
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onContainsMouseChanged: {
                if (containsMouse)
                    peek.showAt(bub.spec.title, bub.spec.comments,
                                bub.x + bub.width - peek.width,
                                bub.y + bub.height + 8);
                else
                    peek.hideSoon();
            }
        }
    }

    Repeater {
        model: 5
        delegate: TailBubble {
            required property int index
            target: stage.nodeItems[index]
            spec: stage.specs[index]
        }
    }

    // Ghost add-bubble on the empty node.
    Item {
        id: ghost
        readonly property var target: stage.nodeItems[0]
        width: 26; height: 22
        x: target.x + target.width + 7
        y: target.y + target.height + 4
        z: 40
        visible: opacity > 0.01
        opacity: (target.hovered || ghostMa.containsMouse) ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Rectangle {
            width: 9; height: 9
            x: -2; y: -2
            rotation: 45
            color: "transparent"
            border.width: 1
            border.color: theme.commentBorder
        }
        Rectangle {
            anchors.fill: parent
            radius: 8
            color: "transparent"
            border.width: 1
            border.color: theme.commentBorder
            CommentGlyph { anchors.centerIn: parent; name: "plus"; size: 11; color: theme.comment }
        }
        MouseArea { id: ghostMa; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    CommentPeekCard { id: peek; theme: root.theme }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        var n = stage.nodeItems[2];   // unread node
        peek.showAt(stage.specs[2].title, stage.specs[2].comments,
                    n.x + n.width + 33 - peek.width,
                    n.y + n.height + 34);
    })

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "The bubble floats outside the silhouette — grip corner untouched · unread bubbles pulse twice on load"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
