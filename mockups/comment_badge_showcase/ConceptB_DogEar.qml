import QtQuick
import "CommentScenarios.js" as Scenarios

// Concept B — Dog-Ear Fold (the corner-tension variant).
// A folded paper corner marks "there's a note on this page". It wants the
// SAME corner as the resize grip, so the tension is resolved live: while the
// node is hovered (grip visible) the ear slides left along the bottom edge to
// cede the corner; on locked nodes the grip never appears and the ear stays
// parked. A tiny count sits beside the ear when more than one comment is
// open. Hovering the ear opens the shared peek card.
Item {
    id: root
    property var theme
    property bool posed: false

    BadgeStageStrip { id: stage; anchors.fill: parent; theme: root.theme }

    component DogEar: Item {
        id: ear
        property var target
        property var spec
        readonly property int total: Scenarios.commentCount(spec.comments)
        readonly property int openN: Scenarios.openCount(spec.comments)
        readonly property bool resolvedAll: total > 0 && openN === 0
        readonly property bool unread: spec.unread === true
        readonly property real size: 19

        width: size
        height: size
        // Parked flush in the corner; cedes it to the grip when that shows.
        x: target.x + target.width - size - 1 - (target.gripVisible ? target.gripZone + 6 : 0)
        y: target.y + target.height - size - 1
        z: 40
        visible: ear.total > 0
        Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

        Canvas {
            id: fold
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                // Fold face: corner triangle pointing at the node corner.
                ctx.beginPath();
                ctx.moveTo(0, height);
                ctx.lineTo(width, 0);
                ctx.lineTo(width, height);
                ctx.closePath();
                ctx.fillStyle = String(fold.face);
                ctx.fill();
                // Crease highlight along the hypotenuse.
                ctx.beginPath();
                ctx.moveTo(0.5, height - 0.5);
                ctx.lineTo(width - 0.5, 0.5);
                ctx.strokeStyle = String(fold.crease);
                ctx.lineWidth = 1.4;
                ctx.lineCap = "round";
                ctx.stroke();
                // Soft inner shadow line under the crease.
                ctx.beginPath();
                ctx.moveTo(3.5, height - 1);
                ctx.lineTo(width - 1, 3.5);
                ctx.strokeStyle = "rgba(0,0,0,0.28)";
                ctx.lineWidth = 1;
                ctx.stroke();
            }
            property color face: ear.resolvedAll ? theme.successSoft
                               : ear.unread ? theme.comment
                               : theme.commentSoft
            property color crease: ear.resolvedAll ? theme.success
                                 : ear.unread ? Qt.lighter(theme.comment, 1.35)
                                 : theme.commentBorder
            onFaceChanged: requestPaint()
            onCreaseChanged: requestPaint()
            Component.onCompleted: requestPaint()
        }

        // Tiny open-count beside the ear (only when it earns its ink).
        Text {
            visible: ear.openN > 1
            anchors.right: parent.left
            anchors.rightMargin: 4
            anchors.bottom: parent.bottom
            text: ear.openN
            color: ear.unread ? theme.comment : theme.mutedFg
            font.family: theme.fontFamily
            font.pixelSize: 10
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onContainsMouseChanged: {
                if (containsMouse)
                    peek.showAt(ear.spec.title, ear.spec.comments,
                                ear.x + ear.width - peek.width,
                                ear.y + ear.height + 10);
                else
                    peek.hideSoon();
            }
        }
    }

    Repeater {
        model: 5
        delegate: DogEar {
            required property int index
            target: stage.nodeItems[index]
            spec: stage.specs[index]
        }
    }

    // Ghost ear on the empty node: a faint outline fold on hover.
    Canvas {
        id: ghostEar
        readonly property var target: stage.nodeItems[0]
        width: 19; height: 19
        x: target.x + target.width - width - 1 - (target.gripVisible ? target.gripZone + 6 : 0)
        y: target.y + target.height - height - 1
        z: 40
        visible: opacity > 0.01
        opacity: (target.hovered || gearMa.containsMouse) ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            ctx.strokeStyle = String(tone);
            ctx.lineWidth = 1.2;
            ctx.setLineDash([3, 2]);
            ctx.beginPath();
            ctx.moveTo(0.5, height - 0.5);
            ctx.lineTo(width - 0.5, 0.5);
            ctx.lineTo(width - 0.5, height - 0.5);
            ctx.closePath();
            ctx.stroke();
        }
        property color tone: theme.commentBorder
        onToneChanged: requestPaint()
        Component.onCompleted: requestPaint()
        CommentGlyph {
            anchors.right: parent.left
            anchors.rightMargin: 3
            anchors.bottom: parent.bottom
            name: "plus"; size: 10; color: theme.comment
        }
        MouseArea { id: gearMa; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }

    CommentPeekCard { id: peek; theme: root.theme }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        var n = stage.nodeItems[2];   // unread node (forceHover -> ear slid aside)
        peek.showAt(stage.specs[2].title, stage.specs[2].comments,
                    n.x + n.width - peek.width,
                    n.y + n.height + 14);
    })

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Watch the third node: its grip is visible, so the ear has slid aside · the locked node keeps the ear parked in the corner"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
