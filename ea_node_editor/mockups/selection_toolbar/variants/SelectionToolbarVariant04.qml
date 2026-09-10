import QtQuick 2.15
import "../shared" as Shared
import "../shared/SelectionMockupTheme.js" as Theme
import "../shared/SelectionMockupEligibility.js" as Eligibility

Rectangle {
    id: root
    objectName: "selectionToolbarVariant04"

    property string themeName: "dark"
    property string sampleState: "rich"
    property string variantTitle: "Variant 04 - Minimal Ghost + Menu"
    property string lastAction: "Menu open"

    readonly property var themePalette: Theme.shellPalette(root.themeName)
    readonly property var nodePalette: Theme.nodePalette(root.themeName)
    readonly property var edgePalette: Theme.edgePalette(root.themeName)
    readonly property var selectionBox: canvas.screenSelectionBox(0)
    readonly property var menuActions: [
        { "actionId": "align_left", "text": "Align Left", "glyph": "L", "enabled": canvas.actionEnabled("align_left") },
        { "actionId": "align_right", "text": "Align Right", "glyph": "R", "enabled": canvas.actionEnabled("align_right") },
        { "actionId": "align_top", "text": "Align Top", "glyph": "T", "enabled": canvas.actionEnabled("align_top") },
        { "actionId": "align_bottom", "text": "Align Bottom", "glyph": "B", "enabled": canvas.actionEnabled("align_bottom") },
        { "actionId": "distribute_h", "text": "Distribute Horizontally", "glyph": "H", "enabled": canvas.actionEnabled("distribute_h"), "separatorBefore": true },
        { "actionId": "distribute_v", "text": "Distribute Vertically", "glyph": "V", "enabled": canvas.actionEnabled("distribute_v") },
        { "actionId": "straighten", "text": "Straighten Connections", "glyph": "S", "enabled": canvas.actionEnabled("straighten"), "separatorBefore": true },
        { "actionId": "wrap_comment", "text": "Wrap in Group", "glyph": "C", "shortcut": "C", "enabled": canvas.actionEnabled("wrap_comment"), "separatorBefore": true }
    ]

    function trigger(actionId) {
        for (var i = 0; i < root.menuActions.length; i++) {
            if (root.menuActions[i].actionId === actionId) {
                root.lastAction = root.menuActions[i].text;
                return;
            }
        }
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
        style: "ghost"
        extraPadding: 0
    }

    Rectangle {
        id: affordance
        z: 35
        x: Math.max(18, Math.min(root.width - width - 18, root.selectionBox.x + root.selectionBox.width - width + 4))
        y: Math.max(58, root.selectionBox.y - height * 0.5)
        width: 36
        height: 36
        radius: 18
        color: Qt.alpha(root.nodePalette.header_bg, 0.72)
        border.width: 1
        border.color: Qt.alpha(root.nodePalette.card_selected_border, 0.55)

        Shared.ToolbarButton {
            anchors.centerIn: parent
            buttonSize: 28
            iconSize: 15
            iconName: "more"
            label: "Selection actions"
            themePalette: root.themePalette
            nodePalette: root.nodePalette
            actionEnabled: canvas.actionEnabled("more")
            active: true
        }
    }

    Shared.MockupContextMenu {
        id: menu
        z: 34
        x: Math.max(18, Math.min(root.width - width - 18, affordance.x + affordance.width + 10))
        y: Math.max(58, Math.min(root.height - height - 22, affordance.y - 8))
        themePalette: root.themePalette
        actions: root.menuActions
        minimumWidth: 314
        showGlyphs: false
        onActionTriggered: root.trigger(actionId)
    }

    Rectangle {
        z: 36
        anchors.right: parent.right
        anchors.rightMargin: 22
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        width: Math.max(162, actionText.implicitWidth + 26)
        height: 30
        radius: 7
        color: Qt.alpha(root.themePalette.panel_bg, 0.92)
        border.width: 1
        border.color: Qt.alpha(root.themePalette.input_border, 0.78)

        Text {
            id: actionText
            anchors.centerIn: parent
            text: root.lastAction
            color: root.themePalette.muted_fg
            font.pixelSize: 11
        }
    }
}
