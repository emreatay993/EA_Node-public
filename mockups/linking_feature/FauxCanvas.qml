import QtQuick
import "LinkData.js" as LinkData

// The shared faux node-editor stage every concept renders inside: a 2-level
// grid, a workspace tab strip, and three sample nodes (two plain + one
// selectable body-text node). Concepts decorate the exposed nodes/tabs.
Item {
    id: stage
    property var theme
    property alias research: nResearch
    property alias budget: nBudget
    property alias brief: nBrief
    property alias tabStrip: wsRow
    property int currentWorkspace: 0
    signal nodeClicked(var node)
    signal emptyClicked(real x, real y)

    // The pre-linked span in the brief recolours with the theme accent.
    readonly property string briefHtml:
        "<span style='line-height:150%'>This brief consolidates the "
        + "<a href='node:Budget%20Model' style='color:" + theme.accent + "; text-decoration:underline'>budget model</a>"
        + " and the latest research findings. See the reference deck for background, "
        + "and keep assets in the shared project folder.</span>"

    Rectangle {
        anchors.fill: parent
        color: theme.canvasBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
    }

    // empty-space click catcher (sits below the nodes / tabs)
    MouseArea {
        anchors.fill: parent
        onClicked: (m) => stage.emptyClicked(m.x, m.y)
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

    // workspace tab strip
    Row {
        id: wsRow
        x: 18; y: 14
        spacing: 6
        Repeater {
            model: LinkData.workspaces
            delegate: Rectangle {
                id: wtab
                required property int index
                required property var modelData
                readonly property bool active: index === stage.currentWorkspace
                height: 30
                width: wlabel.implicitWidth + 44
                radius: 7
                color: active ? theme.panelAltBg : (wma.containsMouse ? theme.hover : "transparent")
                border.width: 1
                border.color: active ? theme.border : "transparent"
                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    LinkGlyph {
                        anchors.verticalCenter: parent.verticalCenter
                        name: "workspace"; size: 14
                        color: wtab.active ? theme.accent : theme.mutedFg
                    }
                    Text {
                        id: wlabel
                        anchors.verticalCenter: parent.verticalCenter
                        text: wtab.modelData.title
                        color: theme.appFg
                        font.family: theme.fontFamily
                        font.pixelSize: 13
                        font.bold: wtab.active
                    }
                }
                Rectangle {
                    visible: wtab.active
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 18
                    height: 2; radius: 1
                    color: theme.accent
                }
                MouseArea {
                    id: wma
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: stage.currentWorkspace = wtab.index
                }
            }
        }
    }

    SampleNode {
        id: nResearch
        theme: stage.theme
        x: 70; y: 96
        title: "Research Summary"
        bodyText: "Key findings from the Q3 user interviews and the competitive scan."
        onClicked: stage.nodeClicked(nResearch)
    }
    SampleNode {
        id: nBudget
        theme: stage.theme
        x: 430; y: 96
        title: "Budget Model"
        bodyText: "Cost projections and the headcount ramp for the next two quarters."
        onClicked: stage.nodeClicked(nBudget)
    }
    BodyTextNode {
        id: nBrief
        theme: stage.theme
        x: 210; y: 288
        title: "Project Brief"
        bodyHtml: stage.briefHtml
        onClicked: stage.nodeClicked(nBrief)
    }
}
