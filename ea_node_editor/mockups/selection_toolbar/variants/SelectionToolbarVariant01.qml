import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../shared" as Shared
import "../shared/SelectionMockupTheme.js" as Theme
import "../shared/SelectionMockupEligibility.js" as Eligibility

Rectangle {
    id: root
    objectName: "selectionToolbarVariant01"

    property string themeName: "dark"
    property string sampleState: "rich"
    property string variantTitle: "Variant 01 - Compact Top Pill"
    property string lastAction: "Compact actions"

    readonly property var themePalette: Theme.shellPalette(root.themeName)
    readonly property var nodePalette: Theme.nodePalette(root.themeName)
    readonly property var edgePalette: Theme.edgePalette(root.themeName)
    readonly property real selectionLeft: canvas.worldX + canvas.selectionBox.x
    readonly property real selectionTop: canvas.worldY + canvas.selectionBox.y
    readonly property real selectionWidth: canvas.selectionBox.width

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
        box: canvas.screenSelectionBox(0)
        style: "subtle"
        extraPadding: 0
    }

    Rectangle {
        id: toolbar
        z: 30
        x: Math.max(18, Math.min(root.width - width - 18, root.selectionLeft + root.selectionWidth * 0.5 - width * 0.5))
        y: Math.max(58, root.selectionTop - height - 6)
        width: pillRow.implicitWidth + 6
        height: 36
        radius: 999
        color: Qt.alpha(root.nodePalette.header_bg, 0.96)
        border.width: 1
        border.color: Qt.alpha(root.nodePalette.card_border, 0.55)

        Row {
            id: pillRow
            anchors.centerIn: parent
            spacing: 2

            Shared.ToolbarButton {
                buttonSize: 29
                chromeRadius: 999
                glyph: "A"
                label: "Align selection"
                themePalette: root.themePalette
                nodePalette: root.nodePalette
                actionEnabled: canvas.actionEnabled("align_left")
                onTriggered: root.trigger("align_left", "Align group")
            }
            Shared.ToolbarButton {
                buttonSize: 29
                chromeRadius: 999
                glyph: "D"
                label: "Distribute selection"
                themePalette: root.themePalette
                nodePalette: root.nodePalette
                actionEnabled: canvas.actionEnabled("distribute_h")
                onTriggered: root.trigger("distribute_h", "Distribute group")
            }
            Shared.ToolbarButton {
                buttonSize: 29
                chromeRadius: 999
                glyph: "S"
                label: "Straighten connections"
                themePalette: root.themePalette
                nodePalette: root.nodePalette
                actionEnabled: canvas.actionEnabled("straighten")
                onTriggered: root.trigger("straighten", "Straighten connections")
            }
            Shared.ToolbarButton {
                buttonSize: 29
                chromeRadius: 999
                iconName: "comment"
                label: "Wrap in Group"
                themePalette: root.themePalette
                nodePalette: root.nodePalette
                actionEnabled: canvas.actionEnabled("wrap_comment")
                onTriggered: root.trigger("wrap_comment", "Wrap in Group")
            }
            Shared.ToolbarButton {
                buttonSize: 29
                chromeRadius: 999
                iconName: "more"
                label: "More selection actions"
                themePalette: root.themePalette
                nodePalette: root.nodePalette
                actionEnabled: canvas.actionEnabled("more")
                onTriggered: root.trigger("more", "Open action menu")
            }
        }
    }

    Rectangle {
        z: 35
        anchors.right: parent.right
        anchors.rightMargin: 22
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        width: Math.max(166, actionText.implicitWidth + 26)
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
