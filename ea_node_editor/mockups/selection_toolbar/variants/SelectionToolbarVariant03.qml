import QtQuick 2.15
import "../shared" as Shared
import "../shared/SelectionMockupTheme.js" as Theme
import "../shared/SelectionMockupEligibility.js" as Eligibility

Rectangle {
    id: root
    objectName: "selectionToolbarVariant03"

    property string themeName: "dark"
    property string sampleState: "rich"
    property string variantTitle: "Variant 03 - Side Rail"
    property string lastAction: "Eligibility rail"

    readonly property var themePalette: Theme.shellPalette(root.themeName)
    readonly property var nodePalette: Theme.nodePalette(root.themeName)
    readonly property var edgePalette: Theme.edgePalette(root.themeName)
    readonly property var selectionBox: canvas.screenSelectionBox(0)

    function trigger(actionId, label) {
        if (canvas.actionEnabled(actionId))
            root.lastAction = label;
    }

    color: root.themePalette.panel_alt_bg
    radius: 8
    border.width: 1
    border.color: Qt.alpha(root.themePalette.border, 0.8)
    clip: true

    Text {
        id: title
        x: 18
        y: 14
        text: root.variantTitle
        color: root.themePalette.panel_title_fg
        font.pixelSize: 15
        font.bold: true
    }

    Text {
        anchors.left: title.right
        anchors.leftMargin: 12
        anchors.verticalCenter: title.verticalCenter
        text: Eligibility.actionSummary(root.sampleState)
        color: root.themePalette.muted_fg
        font.pixelSize: 11
    }

    Shared.SelectionMockupCanvas {
        id: canvas
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 48
        themePalette: root.themePalette
        nodePalette: root.nodePalette
        edgePalette: root.edgePalette
        sampleState: root.sampleState
        dimIneligible: true
    }

    Shared.SelectionEnvelope {
        z: 20
        themePalette: root.themePalette
        nodePalette: root.nodePalette
        box: root.selectionBox
        style: "subtle"
        cornerTicks: true
        extraPadding: 1
    }

    Rectangle {
        id: rail
        z: 30
        x: Math.max(18, Math.min(root.width - width - 18, root.selectionBox.x + root.selectionBox.width + 12))
        y: Math.max(58, Math.min(root.height - height - 22, root.selectionBox.y + 4))
        width: 42
        height: railColumn.implicitHeight + 8
        radius: 7
        color: Qt.alpha(root.nodePalette.header_bg, 0.96)
        border.width: 1
        border.color: Qt.alpha(root.nodePalette.card_border, 0.74)

        Column {
            id: railColumn
            anchors.centerIn: parent
            spacing: 2

            Repeater {
                model: [
                    { "glyph": "L", "label": "Align left", "action": "align_left" },
                    { "glyph": "R", "label": "Align right", "action": "align_right" },
                    { "glyph": "H", "label": "Distribute horizontally", "action": "distribute_h" },
                    { "glyph": "V", "label": "Distribute vertically", "action": "distribute_v" },
                    { "glyph": "S", "label": "Straighten connections", "action": "straighten" },
                    { "icon": "comment", "label": "Wrap in Group", "action": "wrap_comment" },
                    { "icon": "focus", "label": "Focus selection", "action": "focus" }
                ]

                delegate: Item {
                    width: 32
                    height: 30

                    Shared.ToolbarButton {
                        anchors.fill: parent
                        buttonSize: 30
                        iconSize: 15
                        chromeRadius: 6
                        glyph: String(modelData.glyph || "")
                        iconName: String(modelData.icon || "")
                        label: String(modelData.label || "")
                        themePalette: root.themePalette
                        nodePalette: root.nodePalette
                        actionEnabled: canvas.actionEnabled(String(modelData.action || ""))
                        onTriggered: root.trigger(String(modelData.action || ""), String(modelData.label || ""))
                    }

                    Rectangle {
                        visible: !canvas.actionEnabled(String(modelData.action || ""))
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        width: 6
                        height: 6
                        radius: 3
                        color: root.themePalette.inspector_danger_border || "#b96a72"
                    }
                }
            }
        }
    }

    Rectangle {
        z: 35
        x: Math.max(18, Math.min(root.width - width - 18, rail.x - width - 10))
        y: rail.y
        width: Math.max(158, statusText.implicitWidth + 24)
        height: 30
        radius: 7
        color: Qt.alpha(root.themePalette.panel_bg, 0.92)
        border.width: 1
        border.color: Qt.alpha(root.themePalette.input_border, 0.78)

        Text {
            id: statusText
            anchors.centerIn: parent
            text: root.lastAction
            color: root.themePalette.muted_fg
            font.pixelSize: 11
        }
    }
}
