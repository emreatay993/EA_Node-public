import QtQuick
import "CommentScenarios.js" as Scenarios

// Concept E — Dot → Expanding Chip (the dense-graph variant).
// At rest each commented node carries only a 7px LED dot embedded in its
// bottom edge, inset LEFT of the 16px grip zone. Hovering the node expands
// the dot leftward into an 18px chip: count + first-line preview, still
// ending clear of the grip. Hovering the chip opens the shared peek card.
Item {
    id: root
    property var theme
    property bool posed: false

    BadgeStageStrip { id: stage; anchors.fill: parent; theme: root.theme }

    component DotChip: Item {
        id: dc
        property var target
        property var spec
        readonly property int total: Scenarios.commentCount(spec.comments)
        readonly property int openN: Scenarios.openCount(spec.comments)
        readonly property bool resolvedAll: total > 0 && openN === 0
        readonly property bool unread: spec.unread === true
        readonly property bool expanded: dc.total > 0 && (target.hovered || ma.containsMouse)

        // Right end stays fixed, clear of the grip zone; the chip grows left.
        readonly property real rightEnd: target.x + target.width - target.gripZone - 10

        width: expanded ? 172 : 7
        height: expanded ? 18 : 7
        x: rightEnd - width
        y: target.y + target.height - height / 2
        z: 40
        visible: dc.total > 0
        Behavior on width { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        readonly property color fillColor: dc.resolvedAll ? theme.successSoft
                                         : dc.unread ? theme.comment
                                         : theme.commentSoft
        readonly property color edgeColor: dc.resolvedAll ? theme.success
                                         : dc.unread ? Qt.rgba(1, 1, 1, theme.isDark ? 0.22 : 0.0)
                                         : theme.commentBorder
        readonly property color fgColor: dc.resolvedAll ? theme.success
                                       : dc.unread ? theme.onComment
                                       : theme.comment

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: dc.fillColor
            border.width: 1
            border.color: dc.edgeColor
            clip: true
            Behavior on color { ColorAnimation { duration: 140 } }

            Row {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 8
                spacing: 5
                opacity: dc.expanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }

                CommentGlyph {
                    anchors.verticalCenter: parent.verticalCenter
                    name: dc.resolvedAll ? "check" : "bubbleFilled"
                    size: 10
                    color: dc.fgColor
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: dc.total
                    color: dc.fgColor
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    font.bold: true
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "·"
                    color: dc.fgColor
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    opacity: 0.7
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 104   // remaining chip interior; clip on the pill catches the rest
                    text: dc.resolvedAll ? "all resolved" : Scenarios.firstOpenBody(dc.spec.comments)
                    color: dc.resolvedAll ? theme.success
                         : dc.unread ? theme.onComment : theme.inputFg
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }
        }

        MouseArea {
            id: ma
            anchors.fill: parent
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onContainsMouseChanged: {
                if (containsMouse)
                    peek.showAt(dc.spec.title, dc.spec.comments,
                                dc.rightEnd - peek.width,
                                dc.target.y + dc.target.height + 14);
                else
                    peek.hideSoon();
            }
        }
    }

    Repeater {
        model: 5
        delegate: DotChip {
            required property int index
            target: stage.nodeItems[index]
            spec: stage.specs[index]
        }
    }

    // Empty node: hollow dot on hover; expands into a ghost "+ add" chip.
    Item {
        id: ghost
        readonly property var target: stage.nodeItems[0]
        readonly property bool expanded: ghostMa.containsMouse
        readonly property real rightEnd: target.x + target.width - target.gripZone - 10
        width: expanded ? 112 : 7
        height: expanded ? 18 : 7
        x: rightEnd - width
        y: target.y + target.height - height / 2
        z: 40
        visible: opacity > 0.01
        opacity: (target.hovered || ghostMa.containsMouse) ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on width { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: "transparent"
            border.width: 1
            border.color: theme.commentBorder
            clip: true
            Row {
                anchors.centerIn: parent
                spacing: 4
                opacity: ghost.expanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                CommentGlyph { anchors.verticalCenter: parent.verticalCenter; name: "plus"; size: 10; color: theme.comment }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Add comment"
                    color: theme.comment
                    font.family: theme.fontFamily
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
        MouseArea { id: ghostMa; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    CommentPeekCard { id: peek; theme: root.theme }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        var n = stage.nodeItems[2];   // unread node (forceHover -> chip expanded)
        peek.showAt(stage.specs[2].title, stage.specs[2].comments,
                    n.x + n.width - n.gripZone - 10 - peek.width,
                    n.y + n.height + 16);
    })

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Quiet at rest: just a dot in the edge · hover a node to expand the chip, hover the chip to peek"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
