import QtQuick
import "CommentScenarios.js" as Scenarios

// The shared focused stage every concept renders inside: a faux canvas grid
// and ONE ROW of five replica nodes, one per comment state (see
// CommentScenarios.js). Concepts overlay their badge design against the
// exposed node items — same badges, same states, easy side-by-side judgement.
Item {
    id: stage
    property var theme

    // Node specs by index (comments, unread, captions, ...).
    readonly property var specs: Scenarios.nodeStates
    // Node items by index, for Repeater-driven badge overlays.
    readonly property var nodeItems: [n0, n1, n2, n3, n4]

    readonly property real nodeY: 168
    function nodeX(i) { return 36 + i * 248 }

    Rectangle {
        anchors.fill: parent
        color: theme.canvasBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
    }

    Canvas {
        id: grid
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            function lines(step, col) {
                ctx.strokeStyle = col;
                ctx.lineWidth = 1;
                ctx.beginPath();
                for (var x = 0; x < width; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, height); }
                for (var y = 0; y < height; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(width, y + 0.5); }
                ctx.stroke();
            }
            lines(24, stage.theme.gridMinor);
            lines(120, stage.theme.gridMajor);
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: stage.theme; function onIsDarkChanged() { grid.requestPaint() } }
    }

    // Legend strip above the nodes.
    Row {
        x: stage.nodeX(0)
        y: 118
        spacing: 8
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 8; height: 8; radius: 4
            color: theme.comment
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Same five states in every concept — hover any unlocked node to reveal the resize grip the badge must live with; hover a badge to peek."
            color: theme.mutedFg
            font.family: theme.fontFamily
            font.pixelSize: 11
        }
    }

    BadgeMockNode {
        id: n0
        theme: stage.theme
        x: stage.nodeX(0); y: stage.nodeY
        title: stage.specs[0].title
        bodyText: stage.specs[0].body
        stateCaption: stage.specs[0].caption
        locked: stage.specs[0].locked
        forceHover: stage.specs[0].forceHover
    }
    BadgeMockNode {
        id: n1
        theme: stage.theme
        x: stage.nodeX(1); y: stage.nodeY
        title: stage.specs[1].title
        bodyText: stage.specs[1].body
        stateCaption: stage.specs[1].caption
        locked: stage.specs[1].locked
        forceHover: stage.specs[1].forceHover
    }
    BadgeMockNode {
        id: n2
        theme: stage.theme
        x: stage.nodeX(2); y: stage.nodeY
        title: stage.specs[2].title
        bodyText: stage.specs[2].body
        stateCaption: stage.specs[2].caption
        locked: stage.specs[2].locked
        forceHover: stage.specs[2].forceHover
    }
    BadgeMockNode {
        id: n3
        theme: stage.theme
        x: stage.nodeX(3); y: stage.nodeY
        title: stage.specs[3].title
        bodyText: stage.specs[3].body
        stateCaption: stage.specs[3].caption
        locked: stage.specs[3].locked
        forceHover: stage.specs[3].forceHover
    }
    BadgeMockNode {
        id: n4
        theme: stage.theme
        x: stage.nodeX(4); y: stage.nodeY
        title: stage.specs[4].title
        bodyText: stage.specs[4].body
        stateCaption: stage.specs[4].caption
        locked: stage.specs[4].locked
        forceHover: stage.specs[4].forceHover
    }
}
