import QtQuick 2.15
import QtQuick.Effects
import "../../../ui_qml/components/graph_canvas" as GraphCanvasComponents
import "SelectionMockupEligibility.js" as Eligibility

Item {
    id: root

    property var themePalette: ({})
    property var nodePalette: ({})
    property var edgePalette: ({})
    property string sampleState: "rich"
    property bool showStateBadge: true
    property bool dimIneligible: false
    readonly property real minorGridStep: 20.0
    readonly property real majorGridStep: 100.0

    readonly property var nodes: [
        { "id": "source", "title": "Inputs", "subtitle": "CSV + parameters", "x": 96, "y": 132, "w": 158, "h": 92, "accent": "#22B455", "ports": 2 },
        { "id": "process", "title": "Normalize", "subtitle": "clean signal", "x": 330, "y": 112, "w": 176, "h": 104, "accent": "#2F89FF", "ports": 3 },
        { "id": "output", "title": "Report", "subtitle": "plots + table", "x": 580, "y": 154, "w": 160, "h": 96, "accent": "#B35BD1", "ports": 2 },
        { "id": "note", "title": "Design Note", "subtitle": "Group", "x": 210, "y": 308, "w": 206, "h": 74, "accent": "#D88C32", "ports": 0 },
        { "id": "locked", "title": "Locked Add-on", "subtitle": "not editable", "x": 540, "y": 314, "w": 164, "h": 82, "accent": "#C75050", "ports": 1, "locked": true }
    ]
    readonly property var selectedIds: Eligibility.selectedNodeIds(root.sampleState)
    readonly property var selectionBox: root._selectionBox(root.selectedIds)
    readonly property real worldX: scene.x
    readonly property real worldY: scene.y
    readonly property real worldWidth: scene.width
    readonly property real worldHeight: scene.height

    signal stateBadgeClicked()

    function _nodeById(nodeId) {
        for (var i = 0; i < root.nodes.length; i++) {
            if (root.nodes[i].id === nodeId)
                return root.nodes[i];
        }
        return null;
    }

    function _selectionBox(nodeIds) {
        var ids = nodeIds || [];
        var left = 0;
        var top = 0;
        var right = 0;
        var bottom = 0;
        var hasBounds = false;
        for (var i = 0; i < ids.length; i++) {
            var node = root._nodeById(ids[i]);
            if (!node)
                continue;
            if (!hasBounds) {
                left = node.x;
                top = node.y;
                right = node.x + node.w;
                bottom = node.y + node.h;
                hasBounds = true;
            } else {
                left = Math.min(left, node.x);
                top = Math.min(top, node.y);
                right = Math.max(right, node.x + node.w);
                bottom = Math.max(bottom, node.y + node.h);
            }
        }
        if (!hasBounds)
            return { "x": 0, "y": 0, "width": 0, "height": 0 };
        return { "x": left - 18, "y": top - 18, "width": right - left + 36, "height": bottom - top + 36 };
    }

    function screenSelectionBox(extra) {
        var pad = Number(extra || 0);
        return {
            "x": root.worldX + root.selectionBox.x - pad,
            "y": root.worldY + root.selectionBox.y - pad,
            "width": root.selectionBox.width + pad * 2,
            "height": root.selectionBox.height + pad * 2
        };
    }

    function isSelected(nodeId) {
        return root.selectedIds.indexOf(String(nodeId || "")) >= 0;
    }

    function actionEnabled(actionId) {
        return Eligibility.actionEnabled(actionId, root.sampleState);
    }

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: root.themePalette.canvas_bg || "#1d1f24"
        border.width: 1
        border.color: Qt.alpha(root.themePalette.border || "#3a3d45", 0.7)
        clip: true

        GraphCanvasComponents.GraphCanvasGridShader {
            id: gridCanvas
            anchors.fill: parent
            gridStyle: "lines"
            minorGridColor: root.themePalette.canvas_minor_grid || "#2b2f38"
            majorGridColor: root.themePalette.canvas_major_grid || "#323746"
            minorStep: root.minorGridStep
            majorStep: root.majorGridStep
            minorOffset: Qt.vector2d(0, 0)
            majorOffset: Qt.vector2d(0, 0)
        }

        Item {
            id: scene
            width: 820
            height: 470
            anchors.centerIn: parent

            Canvas {
                id: edgeCanvas
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d");
                    ctx.reset();
                    ctx.lineCap = "round";
                    ctx.lineJoin = "round";

                    function edge(fromX, fromY, toX, toY, selected) {
                        ctx.strokeStyle = selected
                            ? (root.edgePalette.preview_stroke || root.themePalette.accent || "#60CDFF")
                            : Qt.alpha(root.themePalette.muted_fg || "#8d98aa", 0.46);
                        ctx.lineWidth = selected ? 3.0 : 2.0;
                        ctx.beginPath();
                        ctx.moveTo(fromX, fromY);
                        ctx.bezierCurveTo(fromX + 78, fromY, toX - 78, toY, toX, toY);
                        ctx.stroke();
                    }

                    edge(254, 177, 330, 164, root.isSelected("source") && root.isSelected("process"));
                    edge(506, 164, 580, 202, root.isSelected("process") && root.isSelected("output"));
                    edge(416, 345, 540, 356, root.isSelected("note") && root.isSelected("locked"));
                }
            }

            Rectangle {
                x: 74
                y: 82
                width: 468
                height: 204
                radius: 16
                color: Qt.alpha(root.themePalette.accent || "#60CDFF", 0.05)
                border.width: 1
                border.color: Qt.alpha(root.themePalette.accent || "#60CDFF", 0.18)
            }

            Repeater {
                model: root.nodes
                delegate: Item {
                    id: nodeCard
                    x: modelData.x
                    y: modelData.y
                    width: modelData.w
                    height: modelData.h
                    opacity: root.dimIneligible && root.isSelected(modelData.id) && !root.actionEnabled("focus") ? 0.62 : 1.0

                    RectangularShadow {
                        anchors.fill: cardChrome
                        offset.x: 0
                        offset.y: 4
                        blur: 20
                        spread: 0.32
                        radius: cardChrome.radius
                        color: Qt.rgba(0, 0, 0, root.themePalette.app_bg === "#1f1f1f" ? 0.42 : 0.18)
                    }

                    Rectangle {
                        id: cardChrome
                        anchors.fill: parent
                        radius: 6
                        color: root.nodePalette.card_bg || "#1b1d22"
                        border.width: root.isSelected(modelData.id) ? 2 : 1
                        border.color: root.isSelected(modelData.id)
                            ? (root.nodePalette.card_selected_border || root.themePalette.accent || "#60CDFF")
                            : (root.nodePalette.card_border || root.themePalette.border || "#3a3d45")

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 30
                            radius: 6
                            color: root.nodePalette.header_bg || root.themePalette.toolbar_bg || "#2a2b30"
                        }

                        Rectangle {
                            x: 0
                            y: 24
                            width: parent.width
                            height: 10
                            color: root.nodePalette.header_bg || root.themePalette.toolbar_bg || "#2a2b30"
                        }

                        Rectangle {
                            x: 0
                            y: 0
                            width: 5
                            height: parent.height
                            radius: 3
                            color: modelData.accent
                        }

                        Text {
                            x: 14
                            y: 8
                            text: modelData.title
                            color: root.nodePalette.header_fg || root.themePalette.panel_title_fg || "#f0f4fb"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        Text {
                            x: 14
                            y: 43
                            width: parent.width - 28
                            text: modelData.subtitle
                            color: root.nodePalette.inline_label_fg || root.themePalette.muted_fg || "#d0d5de"
                            font.pixelSize: 10
                            elide: Text.ElideRight
                        }

                        Rectangle {
                            visible: (modelData.ports || 0) > 1
                            x: 14
                            y: parent.height - 25
                            width: parent.width - 28
                            height: 18
                            radius: 4
                            color: root.nodePalette.inline_row_bg || "#24262c"
                            border.width: 1
                            border.color: Qt.alpha(root.nodePalette.inline_row_border || "#4a4f5a", 0.82)
                        }

                        Repeater {
                            model: modelData.ports || 0
                            delegate: Rectangle {
                                x: index % 2 === 0 ? -4 : cardChrome.width - 4
                                y: 46 + index * 14
                                width: root.isSelected(modelData.id) ? 8 : 7
                                height: width
                                radius: width / 2
                                color: root.nodePalette.port_interactive_fill || "#FFDA6B"
                                border.width: 1
                                border.color: root.nodePalette.port_interactive_border || "#FFE48B"
                            }
                        }

                        Rectangle {
                            visible: Boolean(modelData.locked)
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.top: parent.top
                            anchors.topMargin: 7
                            width: 42
                            height: 15
                            radius: 4
                            color: Qt.alpha(root.themePalette.inspector_danger_border || "#b96a72", 0.18)
                            border.width: 1
                            border.color: root.themePalette.inspector_danger_border || "#b96a72"

                            Text {
                                anchors.centerIn: parent
                                text: "lock"
                                color: root.themePalette.inspector_danger_fg || "#f1b0b7"
                                font.pixelSize: 9
                                font.bold: true
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: root.showStateBadge
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.top: parent.top
            anchors.topMargin: 14
            width: Math.max(210, stateLabel.implicitWidth + 26)
            height: 28
            radius: 7
            color: Qt.alpha(root.themePalette.panel_bg || "#1b1d22", 0.92)
            border.width: 1
            border.color: Qt.alpha(root.themePalette.input_border || "#4a4f5a", 0.8)

            Text {
                id: stateLabel
                anchors.centerIn: parent
                text: Eligibility.stateLabel(root.sampleState)
                color: root.themePalette.panel_title_fg || "#f0f4fb"
                font.pixelSize: 11
                font.bold: true
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.stateBadgeClicked()
            }
        }
    }

    onSampleStateChanged: {
        edgeCanvas.requestPaint();
    }
    onEdgePaletteChanged: edgeCanvas.requestPaint()
}
