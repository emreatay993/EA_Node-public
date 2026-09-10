import QtQuick
import "ToolbarToolCatalog.js" as ToolCatalog

Item {
    id: root

    property string activeTool: "laser"
    property real toolbarScale: 1.0
    signal toolTriggered(string toolId, string panelKind)

    // Center X of the laser button in this item's coords, so callers can
    // anchor a popover caret under it.
    property real laserCenterX: width / 2
    property real activeToolCenterX: width / 2

    readonly property color toolbarFill: "#31598a"
    readonly property color toolbarBorder: Qt.rgba(1, 1, 1, 0.16)
    readonly property var tools: ToolCatalog.tools
    readonly property int sidePadding: Math.round(16 * toolbarScale)
    readonly property int buttonSize: Math.round(46 * toolbarScale)
    readonly property int iconSize: Math.round(24 * toolbarScale)
    implicitWidth: row.implicitWidth + sidePadding * 2
    implicitHeight: Math.round(68 * toolbarScale)

    Rectangle {
        anchors.fill: parent
        radius: Math.round(18 * root.toolbarScale)
        color: root.toolbarFill
        border.width: 1
        border.color: root.toolbarBorder

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            radius: parent.radius
            color: Qt.rgba(1, 1, 1, 0.20)
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Math.round(8 * root.toolbarScale)

        Repeater {
            model: root.tools

            delegate: Item {
                id: cell
                width: (modelData.separatorBefore === true ? Math.round(14 * root.toolbarScale) : 0) + root.buttonSize
                height: Math.round(48 * root.toolbarScale)

                readonly property bool isLaser: String(modelData.toolId || "") === "laser"

                function syncCenter() {
                    if (isLaser)
                        root.laserCenterX = cell.mapToItem(root, toolBtn.x + toolBtn.width / 2, 0).x;
                    if (root.activeTool === toolBtn.toolId)
                        root.activeToolCenterX = cell.mapToItem(root, toolBtn.x + toolBtn.width / 2, 0).x;
                }
                Component.onCompleted: syncCenter()
                onXChanged: syncCenter()
                onWidthChanged: syncCenter()
                Connections { target: row; function onXChanged() { cell.syncCenter() } }
                Connections { target: row; function onWidthChanged() { cell.syncCenter() } }
                Connections { target: root; function onActiveToolChanged() { cell.syncCenter() } }

                Rectangle {
                    visible: modelData.separatorBefore === true
                    x: 0
                    anchors.verticalCenter: parent.verticalCenter
                    width: 1
                    height: Math.round(34 * root.toolbarScale)
                    color: Qt.rgba(1, 1, 1, 0.32)
                }

                ToolbarToolButton {
                    id: toolBtn
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    toolId: String(modelData.toolId || "")
                    iconName: String(modelData.icon || "")
                    label: String(modelData.label || "")
                    active: root.activeTool === toolId
                    implemented: modelData.implemented === true
                    buttonSize: root.buttonSize
                    iconSize: root.iconSize
                    onTriggered: function(toolId) {
                        root.toolTriggered(toolId, String(modelData.panelKind || ""));
                    }
                }
            }
        }
    }
}
