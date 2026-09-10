import QtQuick 2.15
import "../common" as Common

FocusScope {
    id: root
    property var actions: []
    property var tooltipPolicyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property int minimumWidth: 182
    property int rowHeight: 30
    property int contentPadding: 4
    property int cornerRadius: 8
    property alias color: menuPanel.color
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property int shadowDepth: 12
    property int currentIndex: -1
    readonly property var visibleActions: {
        var resolved = []
        var source = root.actions || []
        for (var i = 0; i < source.length; ++i) {
            var action = source[i]
            if (!action || action.visible === false)
                continue
            resolved.push(action)
        }
        return resolved
    }
    readonly property int separatorCount: Math.max(0, root.visibleActions.length - 1)
    readonly property int panelWidth: {
        var widest = root.minimumWidth
        for (var i = 0; i < root.visibleActions.length; ++i) {
            var action = root.visibleActions[i]
            var shortcut = String(action.shortcutText || "")
            widest = Math.max(widest, labelMetrics.advanceWidth(String(action.text || "")) + 40
                + (shortcut.length ? shortcutMetrics.advanceWidth(shortcut) + 20 : 0)
                + root.contentPadding * 2)
        }
        return Math.ceil(widest)
    }
    readonly property int panelHeight: (root.contentPadding * 2)
        + (root.visibleActions.length * root.rowHeight)
        + root.separatorCount

    signal actionTriggered(string actionId)
    signal dismissRequested()

    function selectNext(step) {
        var count = root.visibleActions.length
        for (var offset = 1; offset <= count; ++offset) {
            var next = (root.currentIndex + step * offset + count) % count
            if (root.visibleActions[next].enabled !== false) {
                root.currentIndex = next
                return
            }
        }
        root.currentIndex = -1
    }

    function activateCurrent() {
        var action = root.visibleActions[root.currentIndex]
        if (action && action.enabled !== false)
            root.actionTriggered(String(action.actionId || ""))
    }

    onVisibleActionsChanged: currentIndex = -1
    onVisibleChanged: currentIndex = -1
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Down) {
            root.selectNext(1)
        } else if (event.key === Qt.Key_Up) {
            if (root.currentIndex < 0)
                root.currentIndex = 0
            root.selectNext(-1)
        } else if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
            root.currentIndex = event.key === Qt.Key_Home ? -1 : 0
            root.selectNext(event.key === Qt.Key_Home ? 1 : -1)
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.activateCurrent()
        } else if (event.key === Qt.Key_Escape) {
            root.dismissRequested()
        } else {
            event.accepted = false
            return
        }
        event.accepted = true
    }
    Accessible.role: Accessible.PopupMenu

    FontMetrics { id: labelMetrics; font.pixelSize: 12; font.bold: true }
    FontMetrics { id: shortcutMetrics; font.pixelSize: 10 }

    implicitWidth: root.panelWidth
    implicitHeight: root.panelHeight + root.shadowDepth
    width: implicitWidth
    height: implicitHeight

    Rectangle {
        visible: root.visibleActions.length > 0
        x: 0
        y: 10
        width: root.width
        height: root.panelHeight
        radius: root.cornerRadius + 2
        color: Qt.alpha("#000000", 0.10)
    }

    Rectangle {
        visible: root.visibleActions.length > 0
        x: 0
        y: 4
        width: root.width
        height: root.panelHeight
        radius: root.cornerRadius + 1
        color: Qt.alpha("#000000", 0.06)
    }

    Rectangle {
        id: menuPanel
        visible: root.visibleActions.length > 0
        x: 0
        y: 0
        width: root.width
        height: root.panelHeight
        radius: root.cornerRadius
        color: root.themePalette.panel_bg
        border.width: 1
        border.color: Qt.alpha(root.themePalette.input_border, 0.92)

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            radius: parent.radius
            color: Qt.alpha("#ffffff", 0.35)
        }

        Column {
            id: contentColumn
            anchors.fill: parent
            anchors.margins: root.contentPadding
            spacing: 0

            Repeater {
                model: root.visibleActions

                delegate: Item {
                    id: actionRow
                    objectName: String(modelData && modelData.objectName || "")
                    readonly property bool destructive: !!(modelData && modelData.destructive)
                    readonly property bool actionEnabled: !(modelData && modelData.enabled === false)
                    readonly property bool checked: !!(modelData && modelData.checked)
                    readonly property string text: String(modelData && modelData.text !== undefined ? modelData.text : "")
                    readonly property bool highlighted: actionEnabled && root.currentIndex === index
                    readonly property string actionId: String(modelData && modelData.actionId !== undefined ? modelData.actionId : "")
                    readonly property string actionTooltipText: String(modelData && modelData.tooltipText !== undefined ? modelData.tooltipText : "")
                    readonly property string actionTooltipCategory: String(modelData && modelData.tooltipCategory !== undefined ? modelData.tooltipCategory : "general")
                    implicitWidth: actionLabel.implicitWidth + 40
                        + (shortcutLabel.text.length ? shortcutLabel.implicitWidth + 20 : 0)
                    width: contentColumn.width
                    height: root.rowHeight + (index < root.visibleActions.length - 1 ? 1 : 0)
                    enabled: actionEnabled
                    Accessible.role: Accessible.MenuItem
                    Accessible.name: text
                    Accessible.checkable: !!(modelData && modelData.checkable)
                    Accessible.checked: checked
                    Accessible.onPressAction: {
                        root.currentIndex = index
                        root.activateCurrent()
                    }

                    Rectangle {
                        id: actionBackground
                        width: parent.width
                        height: root.rowHeight
                        radius: 6
                        color: actionRow.highlighted
                            ? (destructive
                                ? Qt.alpha(root.themePalette.inspector_danger_border, 0.16)
                                : Qt.alpha(root.themePalette.accent, 0.12))
                            : "transparent"
                    }

                    Rectangle {
                        visible: actionRow.highlighted
                        x: 8
                        y: 7
                        width: 3
                        height: root.rowHeight - 14
                        radius: 2
                        color: destructive
                            ? root.themePalette.inspector_danger_border
                            : root.themePalette.accent
                    }

                    Text {
                        id: actionCheck
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.verticalCenter: actionBackground.verticalCenter
                        text: actionRow.checked ? "\u2713" : ""
                        color: root.themePalette.accent
                        font.pixelSize: 13
                        font.bold: true
                    }

                    Text {
                        id: actionLabel
                        anchors.left: parent.left
                        anchors.leftMargin: 28
                        anchors.right: parent.right
                        anchors.rightMargin: shortcutLabel.text.length ? shortcutLabel.implicitWidth + 24 : 12
                        anchors.verticalCenter: actionBackground.verticalCenter
                        text: actionRow.text
                        color: !actionEnabled
                            ? Qt.alpha(root.themePalette.panel_title_fg, 0.46)
                            : destructive
                            ? root.themePalette.inspector_danger_fg
                            : root.themePalette.panel_title_fg
                        font.pixelSize: 12
                        font.bold: actionRow.highlighted
                        elide: Text.ElideRight
                    }

                    Text {
                        id: shortcutLabel
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: actionBackground.verticalCenter
                        text: String(modelData && modelData.shortcutText || "")
                        color: Qt.alpha(root.themePalette.panel_title_fg, 0.56)
                        font.pixelSize: 10
                    }

                    Rectangle {
                        visible: index < root.visibleActions.length - 1
                        x: 10
                        y: root.rowHeight
                        width: parent.width - 20
                        height: 1
                        color: Qt.alpha(root.themePalette.border, 0.55)
                    }

                    MouseArea {
                        id: actionMouseArea
                        anchors.fill: actionBackground
                        hoverEnabled: actionEnabled
                        cursorShape: actionEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onPositionChanged: root.currentIndex = index
                        onEntered: root.currentIndex = index
                        onExited: {
                            if (root.currentIndex === index)
                                root.currentIndex = -1
                        }
                        onClicked: function(mouse) {
                            root.currentIndex = index
                            root.activateCurrent()
                            mouse.accepted = true
                        }
                    }

                    Common.ManagedToolTip {
                        policyBridge: root.tooltipPolicyBridge
                        category: parent.actionTooltipCategory
                        active: actionEnabled && actionMouseArea.containsMouse
                        text: parent.actionTooltipText
                        delay: 400
                    }
                }
            }
        }
    }
}
