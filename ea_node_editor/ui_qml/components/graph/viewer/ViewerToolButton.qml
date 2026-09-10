import QtQuick 2.15
import QtQuick.Controls 2.15
import "../../shell"
import "../../common" as Common

Item {
    id: root

    property var themePalette: typeof themeBridge !== "undefined" ? themeBridge.palette : ({})
    property string iconName: ""
    property string accessibleName: ""
    property string tooltipText: ""
    property string tooltipCategory: "general"
    property bool actionEnabled: true
    property bool selectedStyle: false
    property bool checkable: false
    property int iconSize: 20
    property int buttonWidth: 32
    property int buttonHeight: 34
    property int cornerRadius: 3
    signal clicked()

    implicitWidth: buttonWidth
    implicitHeight: buttonHeight
    opacity: actionEnabled ? 1.0 : 0.48

    HoverHandler {
        id: hoverHandler
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    }

    Common.ManagedToolTip {
        policyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
        category: root.tooltipCategory
        active: hoverHandler.hovered && root.tooltipText.length > 0
        text: root.tooltipText
        delay: 300
    }

    ShellButton {
        id: button
        anchors.fill: parent
        enabled: root.actionEnabled
        activeFocusOnTab: root.actionEnabled
        text: ""
        iconName: root.iconName
        iconSize: root.iconSize
        selectedStyle: root.selectedStyle
        tooltipText: ""
        tooltipCategory: root.tooltipCategory
        Accessible.name: root.accessibleName.length > 0 ? root.accessibleName : root.tooltipText
        Accessible.description: root.tooltipText
        Accessible.checkable: root.checkable
        Accessible.checked: root.selectedStyle
        onClicked: root.clicked()

        background: Rectangle {
            radius: root.cornerRadius
            border.width: 1
            border.color: !button.enabled
                ? Qt.alpha(root.themePalette.input_border || "#3d4652", 0.72)
                : root.selectedStyle
                ? (root.themePalette.accent || "#2d9bf0")
                : button.down
                ? (root.themePalette.input_border || "#3d4652")
                : (root.themePalette.border || "#3d4652")
            color: !button.enabled
                ? Qt.alpha(root.themePalette.tab_bg || "#252b33", 0.62)
                : root.selectedStyle
                ? (root.themePalette.accent_strong || root.themePalette.accent || "#187fc4")
                : button.down
                ? (root.themePalette.pressed || "#313a45")
                : button.hovered
                ? (root.themePalette.hover || "#2c3540")
                : (root.themePalette.tab_bg || "#252b33")
        }
    }
}
