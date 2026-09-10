import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: portSection

    property var pane
    property bool open: false

    objectName: "inspectorPortManagementCard"
    width: parent ? parent.width : implicitWidth
    visible: pane.showPortSection
    radius: 12
    color: pane.cardBackgroundColor
    border.color: pane.themePalette.border
    border.width: 1
    clip: true
    implicitHeight: cardColumn.implicitHeight
    height: implicitHeight

    Column {
        id: cardColumn
        width: parent.width
        spacing: 0

        InspectorSmartGroupHeader {
            objectName: "inspectorPortManagementHeader"
            pane: portSection.pane
            width: cardColumn.width
            label: "Port Management"
            open: portSection.open
            uppercase: true
            showCount: false
            onToggleRequested: portSection.open = !portSection.open
        }

        Column {
            id: cardBody
            objectName: "inspectorPortManagementBody"
            width: cardColumn.width
            visible: portSection.open
            spacing: 8
            topPadding: portSection.open ? 12 : 0
            bottomPadding: portSection.open ? 12 : 0
            leftPadding: 12
            rightPadding: 12

            readonly property real contentWidth: width - leftPadding - rightPadding

            InspectorButton {
                pane: portSection.pane
                objectName: "inspectorDeletePortButton"
                width: cardBody.contentWidth
                visible: portSection.pane.canManageSubnodePorts
                destructive: true
                enabled: portSection.pane.selectedPortKey.length > 0
                text: "Delete"
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.ports.delete_selected")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.ports.delete_selected")
                onClicked: portSection.pane.deleteSelectedPort()
            }

            Rectangle {
                objectName: "inspectorPortTabs"
                width: cardBody.contentWidth
                height: 44
                radius: 11
                color: portSection.pane.themePalette.input_bg
                border.color: portSection.pane.themePalette.input_border
                border.width: 1

                Row {
                    anchors.fill: parent
                    anchors.margins: 3
                    spacing: 4

                    InspectorSegmentButton {
                        pane: portSection.pane
                        objectName: "inspectorInputsTab"
                        width: (parent.width - 4) / 2
                        height: parent.height
                        text: "INPUTS (" + portSection.pane.inputPortCount + ")"
                        selectedStyle: portSection.pane.activePortDirection === "in"
                        onClicked: portSection.pane.activePortDirection = "in"
                    }

                    InspectorSegmentButton {
                        pane: portSection.pane
                        objectName: "inspectorOutputsTab"
                        width: (parent.width - 4) / 2
                        height: parent.height
                        text: "OUTPUTS (" + portSection.pane.outputPortCount + ")"
                        selectedStyle: portSection.pane.activePortDirection === "out"
                        onClicked: portSection.pane.activePortDirection = "out"
                    }
                }
            }

            Text {
                width: cardBody.contentWidth
                visible: portSection.pane.visiblePortItems.length === 0
                wrapMode: Text.WordWrap
                text: portSection.pane.activePortDirection === "in"
                    ? "No input ports are available for the current node."
                    : "No output ports are available for the current node."
                color: portSection.pane.themePalette.muted_fg
                font.pixelSize: 10
            }

            Column {
                objectName: "inspectorPortList"
                width: cardBody.contentWidth
                spacing: 4

                Repeater {
                    model: portSection.pane.visiblePortItems

                    delegate: InspectorPortRow {
                        pane: portSection.pane
                        width: parent ? parent.width : portSection.width
                        portItem: modelData
                    }
                }
            }

            InspectorButton {
                pane: portSection.pane
                objectName: "inspectorAddPortButton"
                width: cardBody.contentWidth
                visible: portSection.pane.canManageSubnodePorts
                text: portSection.pane.activePortDirection === "in" ? "+ Input" : "+ Output"
                tooltipText: portSection.pane.activePortDirection === "in"
                    ? "Add an input port to the selected subnode"
                    : "Add an output port to the selected subnode"
                tooltipCategory: "tutorial"
                onClicked: portSection.pane.addSubnodePort(portSection.pane.activePortDirection)
            }
        }
    }
}
