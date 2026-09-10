import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common/TooltipCopy.js" as TooltipCopy

InspectorSectionCard {
    id: definitionSection

    objectName: "inspectorNodeDefinitionCard"
    width: parent ? parent.width : implicitWidth
    visible: pane.hasSelectedNode
    title: "Node Definition"

    RowLayout {
        width: parent.width
        spacing: 8

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: definitionSection.pane.selectedNodeTitle
                color: definitionSection.pane.themePalette.panel_title_fg
                font.pixelSize: 18
                font.bold: true
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: definitionSection.pane.selectedNodeSubtitle
                wrapMode: Text.WordWrap
                color: definitionSection.pane.themePalette.muted_fg
                font.pixelSize: 11
            }
        }

        InspectorButton {
            pane: definitionSection.pane
            objectName: "inspectorCollapseButton"
            visible: definitionSection.pane.selectedNodeCollapsible
            compact: true
            selectedStyle: definitionSection.pane.selectedNodeCollapsed
            text: definitionSection.pane.selectedNodeCollapsed ? "EXPAND" : "COLLAPSE"
            tooltipText: definitionSection.pane.selectedNodeCollapsed
                ? "Expand the selected node body"
                : "Collapse the selected node body"
            tooltipCategory: "general"
            onClicked: {
                if (!definitionSection.pane.inspectorBridgeRef)
                    return
                definitionSection.pane.inspectorBridgeRef.set_selected_node_collapsed(
                    !definitionSection.pane.selectedNodeCollapsed
                )
            }
        }

        InspectorButton {
            pane: definitionSection.pane
            objectName: "inspectorUngroupButton"
            visible: definitionSection.pane.canManageSubnodePorts
            compact: true
            destructive: true
            text: "UNGROUP"
            tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.node_definition.ungroup")
            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.node_definition.ungroup")
            onClicked: {
                if (!definitionSection.pane.inspectorBridgeRef)
                    return
                definitionSection.pane.inspectorBridgeRef.request_ungroup_selected_nodes()
            }
        }
    }

    Flow {
        id: metadataFlow
        width: parent.width
        spacing: 6
        visible: definitionSection.pane.selectedNodeHeaderItems.length > 0

        Repeater {
            model: definitionSection.pane.selectedNodeHeaderItems

            delegate: InspectorMetadataChip {
                pane: definitionSection.pane
                maxWidth: metadataFlow.width
                labelText: String(modelData.label || "")
                valueText: String(modelData.value || "")
            }
        }
    }

    Rectangle {
        objectName: "inspectorPinHintBanner"
        width: parent.width
        visible: definitionSection.pane.isPinInspector
        radius: 10
        color: definitionSection.pane.selectedSurfaceColor
        border.color: definitionSection.pane.selectedOutlineColor
        border.width: 1
        implicitHeight: pinHintText.implicitHeight + 14

        Text {
            id: pinHintText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            text: "Pin ports are configured through Label, Kind, and Data Type."
            wrapMode: Text.WordWrap
            color: definitionSection.pane.themePalette.panel_title_fg
            font.pixelSize: 10
            font.bold: true
        }
    }

}
