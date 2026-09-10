import QtQuick
import QtQuick.Shapes
import QtQuick.Controls.Basic

// Concept C — Drag-from-Anchor Connector.
// Each node has a link anchor; press-drag draws a live curve. Drop on another
// node → node link; on a workspace tab → workspace link; on empty space → a
// small URL/File/Folder chooser. External links dock as satellite chips.
Item {
    id: root
    property var theme
    property bool posed: false

    // drag state
    property bool dragging: false
    property var srcNode: null
    property point startPt: Qt.point(0, 0)
    property point curPt: Qt.point(0, 0)
    property var hoverNode: null
    property var hoverWs: null
    property rect hoverWsRect: Qt.rect(0, 0, 0, 0)
    property point pendingDrop: Qt.point(0, 0)

    FauxCanvas { id: canvas; anchors.fill: parent; theme: root.theme }

    // per-node satellite link stores
    ListModel { id: researchSat }
    ListModel { id: budgetSat }
    ListModel { id: briefSat }
    function satFor(node) {
        if (node === canvas.research) return researchSat;
        if (node === canvas.budget) return budgetSat;
        return briefSat;
    }

    // ---- drag helpers ----
    function nodeAt(p) {
        var ns = [canvas.research, canvas.budget, canvas.brief];
        for (var i = 0; i < ns.length; i++) {
            var n = ns[i];
            if (n !== srcNode && p.x >= n.x && p.x <= n.x + n.width && p.y >= n.y && p.y <= n.y + n.height)
                return n;
        }
        return null;
    }
    function tabChildAt(p) {
        var local = canvas.tabStrip.mapFromItem(root, p.x, p.y);
        return canvas.tabStrip.childAt(local.x, local.y);
    }
    function setNodeHighlight(node) {
        canvas.research.selected = (node === canvas.research);
        canvas.budget.selected = (node === canvas.budget);
        canvas.brief.selected = (node === canvas.brief);
    }
    function beginDrag(node, p) {
        srcNode = node;
        startPt = Qt.point(node.x + node.width + 3, node.y + node.height / 2);
        curPt = p;
        dragging = true;
    }
    function updateDrag(p) {
        curPt = p;
        hoverNode = nodeAt(p);
        setNodeHighlight(hoverNode);
        var child = tabChildAt(p);
        if (child && child.modelData !== undefined) {
            hoverWs = child.modelData;
            var tl = child.mapToItem(root, 0, 0);
            hoverWsRect = Qt.rect(tl.x, tl.y, child.width, child.height);
        } else {
            hoverWs = null;
        }
    }
    function endDrag(p) {
        if (hoverNode) {
            satFor(srcNode).append({ kind: "node", label: hoverNode.title });
        } else if (hoverWs) {
            satFor(srcNode).append({ kind: "workspace", label: hoverWs.title });
        } else {
            pendingDrop = p;
            chooser.x = Math.max(10, Math.min(p.x, root.width - chooser.width - 10));
            chooser.y = Math.max(10, Math.min(p.y, root.height - 150));
            chooser.open();
        }
        dragging = false;
        hoverNode = null;
        hoverWs = null;
        setNodeHighlight(null);
    }

    // ---- live connector ----
    Shape {
        anchors.fill: parent
        visible: root.dragging
        z: 25
        ShapePath {
            strokeColor: theme.accent
            strokeWidth: 2.5
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: root.startPt.x
            startY: root.startPt.y
            PathCubic {
                x: root.curPt.x
                y: root.curPt.y
                control1X: root.startPt.x + 80
                control1Y: root.startPt.y
                control2X: root.curPt.x - 80
                control2Y: root.curPt.y
            }
        }
    }
    Rectangle { // drag end dot
        visible: root.dragging
        z: 26
        width: 12; height: 12; radius: 6
        x: root.curPt.x - 6; y: root.curPt.y - 6
        color: theme.accent
        border.width: 2; border.color: theme.canvasBg
    }

    // ---- workspace drop highlight ----
    Rectangle {
        visible: root.dragging && root.hoverWs !== null
        z: 24
        x: root.hoverWsRect.x - 2; y: root.hoverWsRect.y - 2
        width: root.hoverWsRect.width + 4; height: root.hoverWsRect.height + 4
        radius: 9
        color: "transparent"
        border.width: 2; border.color: theme.accent
    }

    // ---- anchors on each node ----
    Repeater {
        model: [canvas.research, canvas.budget, canvas.brief]
        delegate: Item {
            id: anchor
            required property var modelData
            readonly property var node: modelData
            width: 20; height: 20
            x: node ? node.x + node.width - 7 : 0
            y: node ? node.y + node.height / 2 - height / 2 : 0
            z: 30
            Rectangle {
                anchors.centerIn: parent
                width: aMa.containsMouse || (root.dragging && root.srcNode === anchor.node) ? 18 : 14
                height: width
                radius: width / 2
                color: theme.accent
                border.width: 2
                border.color: theme.canvasBg
                Behavior on width { NumberAnimation { duration: 90 } }
                LinkGlyph { anchors.centerIn: parent; name: "chain"; size: parent.width - 6; color: theme.onAccent }
            }
            MouseArea {
                id: aMa
                anchors.fill: parent
                anchors.margins: -6
                hoverEnabled: true
                cursorShape: Qt.CrossCursor
                preventStealing: true
                onPressed: (m) => root.beginDrag(anchor.node, mapToItem(root, m.x, m.y))
                onPositionChanged: (m) => { if (root.dragging) root.updateDrag(mapToItem(root, m.x, m.y)); }
                onReleased: (m) => { if (root.dragging) root.endDrag(mapToItem(root, m.x, m.y)); }
            }
        }
    }

    // ---- satellite chips ----
    component SatStack: Column {
        property var node
        property var linkModel
        x: node ? node.x + node.width + 16 : 0
        y: node ? node.y + 2 : 0
        spacing: 5
        z: 20
        Repeater {
            model: parent.linkModel
            delegate: Item {
                required property int index
                required property string kind
                required property string label
                width: sc.width; height: sc.height
                LinkChip { id: sc; theme: root.theme; kind: parent.kind; label: parent.label; removable: true; onRemoveClicked: parent.parent.linkModel.remove(index) }
            }
        }
    }
    SatStack { node: canvas.research; linkModel: researchSat }
    SatStack { node: canvas.budget;   linkModel: budgetSat }
    SatStack { node: canvas.brief;    linkModel: briefSat }

    // ---- empty-drop chooser ----
    Popup {
        id: chooser
        width: 220
        padding: 6
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: theme.panelAltBg; radius: 10; border.width: 1; border.color: theme.border }
        contentItem: Column {
            spacing: 2
            Text { text: "Link to…"; color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11; leftPadding: 8; topPadding: 4; bottomPadding: 4 }
            Repeater {
                model: [
                    { kind: "web", label: "Web URL", sample: "example.com" },
                    { kind: "file", label: "File…", sample: "document.pdf" },
                    { kind: "folder", label: "Folder…", sample: "Project Folder" }
                ]
                delegate: Rectangle {
                    id: chDel
                    required property var modelData
                    readonly property color tint: theme.typeColor(chDel.modelData.kind)
                    width: 208; height: 38; radius: 7
                    color: chMa.containsMouse ? theme.hover : "transparent"
                    Row {
                        anchors.left: parent.left; anchors.leftMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 9
                        Rectangle {
                            width: 26; height: 26; radius: 6
                            anchors.verticalCenter: parent.verticalCenter
                            color: Qt.rgba(chDel.tint.r, chDel.tint.g, chDel.tint.b, 0.18)
                            LinkGlyph { anchors.centerIn: parent; name: theme.typeGlyph(chDel.modelData.kind); size: 15; color: chDel.tint }
                        }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: chDel.modelData.label; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 13 }
                    }
                    MouseArea {
                        id: chMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.satFor(root.srcNode).append({ kind: chDel.modelData.kind, label: chDel.modelData.sample });
                            chooser.close();
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        researchSat.append({ kind: "workspace", label: "Design" });
        root.beginDrag(canvas.research, Qt.point(canvas.budget.x + 24, canvas.budget.y + 34));
        root.updateDrag(Qt.point(canvas.budget.x + 24, canvas.budget.y + 34));
    })

    Text {
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Drag from a node's blue anchor onto another node, a workspace tab, or empty space"
        color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11; opacity: 0.8
    }
}
