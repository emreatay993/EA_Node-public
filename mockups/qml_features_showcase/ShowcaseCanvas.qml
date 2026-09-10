import QtQuick
import QtQuick.Particles

// The node-editor stage: grid, animated wires, the six demo nodes, a particle
// system for completion bursts, and the breakpoint debugger popover. Driven by
// `runProgress` (0..1) so the whole scene animates from the timeline scrubber.
Item {
    id: cv
    property var theme
    property real runProgress: 0
    property bool faultMode: false
    property bool paused: false
    property string pausedNodeId: ""
    signal continueRequested()
    signal stepRequested()

    readonly property int steps: 5

    // ---- pipeline model ----
    property var nodes: [
        { id: "A", order: 0, x: 60,  y: 206, w: 212, h: 152, title: "Excel Read",    sub: "io.excel_read",   glyph: "E", body: "table",    tag: "② Inline data preview" },
        { id: "B", order: 1, x: 322, y: 214, w: 196, h: 140, title: "Filter Rows",   sub: "data.filter",     glyph: "F", body: "note",     tag: "⑨ Breakpoint + watch", breakpoint: true,
          bodyProps: { expr: "σ_vm > S_y", lines: [["rows in","1,024"],["rows out","318"]] } },
        { id: "C", order: 2, x: 566, y: 120, w: 214, h: 132, title: "Aggregate",     sub: "data.aggregate",  glyph: "Σ", body: "spark",    tag: "③ In-node sparkline" },
        { id: "E", order: 2, x: 566, y: 332, w: 214, h: 116, title: "Normalize",     sub: "data.formula",    glyph: "z", body: "note",     tag: "⑧ Bypass / mute", bypass: true,
          bodyProps: { expr: "z = (x−μ)/σ", lines: [["status","skipped"]], dim: true } },
        { id: "D", order: 3, x: 830, y: 96,  w: 250, h: 184, title: "Trend Chart",   sub: "plot.chart",      glyph: "▤", body: "chart",    tag: "④ Live chart · Qt Graphs" },
        { id: "F", order: 4, x: 830, y: 330, w: 250, h: 198, title: "Model Viewer", sub: "model.viewer",      glyph: "◳", body: "viewer3d", tag: "⑤ 3D preview node", celebrate: true }
    ]
    property var edges: [
        { from: "A", to: "B" }, { from: "B", to: "C" }, { from: "B", to: "E" },
        { from: "C", to: "D" }, { from: "D", to: "F" }, { from: "E", to: "F" }
    ]

    function find(id) {
        for (var i = 0; i < nodes.length; i++)
            if (nodes[i].id === id)
                return nodes[i];
        return null;
    }
    function nodeState(order, bypassed) {
        if (bypassed)
            return "bypassed";
        var head = runProgress * steps;
        if (faultMode) {
            if (order === 1 && head >= 1) return "error";
            if (order > 1 && head >= 1)   return "blocked";
        }
        if (head >= order + 1) return "done";
        if (head >= order)     return "running";
        if (head >= order - 0.4) return "queued";
        return runProgress > 0 ? "configured" : "idle";
    }
    function watchFor(id) {
        var m = {
            A: [["sheet", "\"Results\""], ["rows", "1,024"]],
            B: [["rows_in", "1,024"], ["predicate", "σ>S_y"], ["rows_out", "318"]],
            C: [["groups", "12"], ["agg", "mean"]],
            D: [["series", "2"], ["x_max", "5"]],
            F: [["mesh", "18,402 nd"], ["result", "σ_vm"]]
        };
        return m[id] !== undefined ? m[id] : [];
    }
    function burstAt(x, y) {
        burstEmitter.x = x;
        burstEmitter.y = y;
        burstEmitter.burst(24);
    }

    // ---- background ----
    Rectangle {
        anchors.fill: parent
        color: cv.theme.canvasBg
        Behavior on color { ColorAnimation { duration: 200 } }
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
            lines(26, cv.theme.gridMinor);
            lines(130, cv.theme.gridMajor);
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: cv.theme; function onIsDarkChanged() { grid.requestPaint(); } }
    }

    // ---- wires (below nodes) ----
    Repeater {
        model: cv.edges
        delegate: FlowWire {
            required property var modelData
            anchors.fill: parent
            theme: cv.theme
            readonly property var fromN: cv.find(modelData.from)
            readonly property var toN: cv.find(modelData.to)
            readonly property string tState: cv.nodeState(toN.order, toN.bypass === true)
            startX: fromN.x + fromN.w
            startY: fromN.y + fromN.h / 2
            endX: toN.x
            endY: toN.y + toN.h / 2
            flowing: tState === "running"
            active: tState === "done"
        }
    }

    // ---- nodes ----
    Repeater {
        model: cv.nodes
        delegate: Item {
            required property var modelData
            x: modelData.x
            y: modelData.y
            width: modelData.w
            height: modelData.h

            ShowcaseNode {
                anchors.fill: parent
                theme: cv.theme
                title: modelData.title
                subtitle: modelData.sub
                glyph: modelData.glyph
                bodyKind: modelData.body
                bodyProps: modelData.bodyProps !== undefined ? modelData.bodyProps : ({})
                bypass: modelData.bypass === true
                hasBreakpoint: modelData.breakpoint === true
                celebrateOnDone: modelData.celebrate === true
                runState: cv.nodeState(modelData.order, modelData.bypass === true)
                breakpointActive: cv.paused && cv.pausedNodeId === modelData.id
                onCompleted: cv.burstAt(modelData.x + modelData.w / 2, modelData.y + modelData.h / 2)
            }

            // feature tag pill under the node
            Rectangle {
                anchors.top: parent.bottom
                anchors.topMargin: 7
                anchors.horizontalCenter: parent.horizontalCenter
                width: tagTxt.implicitWidth + 16
                height: 18
                radius: 9
                color: Qt.rgba(cv.theme.accent.r, cv.theme.accent.g, cv.theme.accent.b, 0.12)
                border.width: 1
                border.color: Qt.rgba(cv.theme.accent.r, cv.theme.accent.g, cv.theme.accent.b, 0.3)
                Text {
                    id: tagTxt
                    anchors.centerIn: parent
                    text: modelData.tag
                    color: cv.theme.accent
                    font.family: cv.theme.fontFamily
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
    }

    // ---- particle bursts on completion (above nodes) ----
    ParticleSystem {
        id: psys
        anchors.fill: parent
        ItemParticle {
            delegate: Rectangle {
                width: 6; height: 6; radius: 3
                color: cv.theme.accent
            }
        }
        Emitter {
            id: burstEmitter
            emitRate: 0
            lifeSpan: 850
            lifeSpanVariation: 250
            size: 7
            sizeVariation: 4
            velocity: AngleDirection { angle: 0; angleVariation: 180; magnitude: 70; magnitudeVariation: 45 }
            acceleration: PointDirection { y: 60 }
        }
    }

    // ---- breakpoint debugger popover (top overlay) ----
    DebuggerPopover {
        id: dbg
        property var pn: cv.paused ? cv.find(cv.pausedNodeId) : null
        visible: cv.paused && pn !== null
        theme: cv.theme
        nodeTitle: pn ? (pn.title + "  ·  " + pn.sub) : ""
        watch: pn ? cv.watchFor(pn.id) : []
        x: pn ? Math.min(pn.x + pn.w + 18, cv.width - width - 12) : 0
        y: pn ? Math.min(pn.y, cv.height - height - 12) : 0
        z: 50
        onContinueClicked: cv.continueRequested()
        onStepClicked: cv.stepRequested()
    }
}
