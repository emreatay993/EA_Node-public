import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/SelectionMockupTheme.js" as Theme
import "../shared/SelectionMockupEligibility.js" as Eligibility

Rectangle {
    id: root
    objectName: "selectionToolbarVariant02"

    property string themeName: "dark"
    property string sampleState: "rich"
    property string variantTitle: "Variant 02 - Segmented Layout Bar"
    property string lastAction: "No action yet"

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
    }

    Shared.SelectionEnvelope {
        z: 20
        themePalette: root.themePalette
        nodePalette: root.nodePalette
        box: root.selectionBox
        style: "strong"
        cornerTicks: true
        halo: true
        extraPadding: 2
    }

    Rectangle {
        id: toolbar
        z: 30
        x: Math.max(18, Math.min(root.width - width - 18, root.selectionBox.x + root.selectionBox.width * 0.5 - width * 0.5))
        y: Math.max(58, root.selectionBox.y - height - 12)
        width: segmentedRow.implicitWidth + 8
        height: segmentedRow.implicitHeight + 10
        radius: 7
        color: root.nodePalette.header_bg
        border.width: 1
        border.color: root.nodePalette.card_border

        Row {
            id: segmentedRow
            anchors.centerIn: parent
            spacing: 0

            Segment {
                title: "Align"
                buttons: [
                    { "glyph": "L", "label": "Align left", "action": "align_left" },
                    { "glyph": "R", "label": "Align right", "action": "align_right" },
                    { "glyph": "T", "label": "Align top", "action": "align_top" },
                    { "glyph": "B", "label": "Align bottom", "action": "align_bottom" }
                ]
            }

            Divider {}

            Segment {
                title: "Distribute"
                buttons: [
                    { "glyph": "H", "label": "Distribute horizontally", "action": "distribute_h" },
                    { "glyph": "V", "label": "Distribute vertically", "action": "distribute_v" }
                ]
            }

            Divider {}

            Segment {
                title: "Connections"
                buttons: [
                    { "glyph": "S", "label": "Straighten connections", "action": "straighten" }
                ]
            }

            Divider {}

            Segment {
                title: "Comment"
                buttons: [
                    { "icon": "comment", "label": "Wrap in Group", "action": "wrap_comment" }
                ]
            }
        }
    }

    Rectangle {
        z: 35
        anchors.right: parent.right
        anchors.rightMargin: 22
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        width: Math.max(190, footerText.implicitWidth + 26)
        height: 30
        radius: 7
        color: Qt.alpha(root.themePalette.panel_bg, 0.92)
        border.width: 1
        border.color: Qt.alpha(root.themePalette.input_border, 0.78)

        Text {
            id: footerText
            anchors.centerIn: parent
            text: root.lastAction
            color: root.themePalette.muted_fg
            font.pixelSize: 11
        }
    }

    component Divider: Rectangle {
        width: 1
        height: 36
        color: Qt.alpha(root.nodePalette.card_border, 0.75)
    }

    component Segment: Column {
        property string title: ""
        property var buttons: []

        spacing: 4

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: title
            color: root.themePalette.muted_fg
            font.pixelSize: 9
            font.bold: true
        }

        Row {
            spacing: 0

            Repeater {
                model: buttons
                delegate: Shared.ToolbarButton {
                    buttonSize: 29
                    iconSize: 14
                    chromeRadius: 0
                    glyph: String(modelData.glyph || "")
                    iconName: String(modelData.icon || "")
                    label: String(modelData.label || "")
                    themePalette: root.themePalette
                    nodePalette: root.nodePalette
                    actionEnabled: canvas.actionEnabled(String(modelData.action || ""))
                    onTriggered: root.trigger(String(modelData.action || ""), String(modelData.label || ""))
                }
            }
        }
    }
}
