import QtQuick
import "CommentScenarios.js" as Scenarios

// Concept A — Count Pill.
// A pill in the production header-badge grammar (18px / radius 9 / 9-10px
// bold) straddles the node's BOTTOM edge, half in / half out, and keeps
// `gripZone + 10` px clear of the corner so the resize grip is never covered.
// Amber solid while unread, amber-soft while read, success-muted when every
// comment is resolved. The empty node grows a dashed ghost "+ Add" pill on
// hover. Hovering a pill opens the shared peek card.
Item {
    id: root
    property var theme
    property bool posed: false

    BadgeStageStrip { id: stage; anchors.fill: parent; theme: root.theme }

    // ---- pill badge ----
    component PillBadge: Item {
        id: badge
        property var target
        property var spec
        readonly property int total: Scenarios.commentCount(spec.comments)
        readonly property int openN: Scenarios.openCount(spec.comments)
        readonly property bool resolvedAll: total > 0 && openN === 0
        readonly property bool unread: spec.unread === true

        width: pill.width
        height: pill.height
        x: target.x + target.width - width - target.gripZone - 10
        y: target.y + target.height - height / 2
        z: 40
        visible: badge.total > 0

        Rectangle {
            id: pill
            width: pillRow.implicitWidth + 16
            height: 18
            radius: 9
            color: badge.resolvedAll ? theme.successSoft
                 : badge.unread ? theme.comment
                 : theme.commentSoft
            border.width: 1
            border.color: badge.resolvedAll ? theme.success
                        : badge.unread ? Qt.rgba(1, 1, 1, theme.isDark ? 0.25 : 0.0)
                        : theme.commentBorder
            Behavior on color { ColorAnimation { duration: 140 } }

            readonly property color fg: badge.resolvedAll ? theme.success
                                      : badge.unread ? theme.onComment
                                      : theme.comment
            Row {
                id: pillRow
                anchors.centerIn: parent
                spacing: 4
                CommentGlyph {
                    anchors.verticalCenter: parent.verticalCenter
                    name: badge.resolvedAll ? "check" : "bubbleFilled"
                    size: 11
                    color: pill.fg
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: badge.total
                    color: pill.fg
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    font.bold: true
                }
            }
            MouseArea {
                anchors.fill: parent
                anchors.margins: -4
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onContainsMouseChanged: {
                    if (containsMouse)
                        peek.showAt(badge.spec.title, badge.spec.comments,
                                    badge.x + badge.width - peek.width,
                                    badge.y + badge.height + 8);
                    else
                        peek.hideSoon();
                }
            }
        }
    }

    Repeater {
        model: 5
        delegate: PillBadge {
            required property int index
            target: stage.nodeItems[index]
            spec: stage.specs[index]
        }
    }

    // ---- ghost "add" pill on the empty node (hover affordance) ----
    Item {
        id: ghost
        readonly property var target: stage.nodeItems[0]
        width: ghostPill.width
        height: 18
        x: target.x + target.width - width - target.gripZone - 10
        y: target.y + target.height - height / 2
        z: 40
        visible: opacity > 0.01
        opacity: (target.hovered || gma.containsMouse) ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }

        Canvas {
            id: ghostPill
            width: ghostRow.implicitWidth + 16
            height: 18
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.strokeStyle = String(dashColor);
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(9, 0.5);
                ctx.lineTo(width - 9, 0.5);
                ctx.arc(width - 9, 9, 8.5, -Math.PI / 2, Math.PI / 2);
                ctx.lineTo(9, 17.5);
                ctx.arc(9, 9, 8.5, Math.PI / 2, Math.PI * 1.5);
                ctx.stroke();
            }
            property color dashColor: theme.commentBorder
            onDashColorChanged: requestPaint()
            Component.onCompleted: requestPaint()

            Row {
                id: ghostRow
                anchors.centerIn: parent
                spacing: 4
                CommentGlyph { anchors.verticalCenter: parent.verticalCenter; name: "plus"; size: 10; color: theme.comment }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Add"
                    color: theme.comment
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
        MouseArea { id: gma; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    CommentPeekCard { id: peek; theme: root.theme }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        var n = stage.nodeItems[2];   // unread node
        peek.showAt(stage.specs[2].title, stage.specs[2].comments,
                    n.x + n.width - peek.width - n.gripZone - 10,
                    n.y + n.height + 18);
    })

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Hover a pill to peek · hover the first node for the ghost add · pills stop " + stage.nodeItems[0].gripZone + "px short of the grip corner"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
