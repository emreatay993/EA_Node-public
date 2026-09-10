// Purpose: Host the shared context menu above clipped/scaled content with keyboard and focus handling.
// Map: subsystems/qml_shell_and_bridges.md
// Tests: tests/qml_quick/tst_shell_context_popup.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Popup {
    id: popup
    property alias actions: menu.actions
    property alias themeBridgeRef: menu.themeBridgeRef
    property alias tooltipPolicyBridge: menu.tooltipPolicyBridge
    property alias minimumWidth: menu.minimumWidth
    readonly property alias menuContent: menu
    property Item previousFocusItem: null
    signal actionTriggered(string actionId)

    parent: Overlay.overlay
    modal: false
    focus: true
    padding: 0
    margins: 4
    z: 1000
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    implicitWidth: menu.implicitWidth
    implicitHeight: menu.implicitHeight
    width: Math.min(implicitWidth, parent && parent.Window.window ? Math.max(1, parent.Window.window.width - 8) : implicitWidth)
    height: Math.min(implicitHeight, parent && parent.Window.window ? Math.max(1, parent.Window.window.height - 8) : implicitHeight)
    background: Item {}

    function openAt(sourceItem, localX, localY) {
        var point = sourceItem.mapToItem(popup.parent, localX, localY)
        popup.open()
        var window = popup.parent.Window.window
        popup.x = Math.max(margins, Math.min(point.x, window.width - width - margins))
        popup.y = Math.max(margins, Math.min(point.y, window.height - height - margins))
    }

    onAboutToShow: {
        var window = parent.Window.window
        previousFocusItem = window.activeFocusItem
        menu.currentIndex = -1
        viewport.contentY = 0
    }
    onOpened: menu.forceActiveFocus(Qt.PopupFocusReason)
    onClosed: {
        if (previousFocusItem && previousFocusItem.visible && previousFocusItem.enabled)
            previousFocusItem.forceActiveFocus(Qt.PopupFocusReason)
        previousFocusItem = null
    }

    contentItem: Flickable {
        id: viewport
        contentWidth: width
        contentHeight: menu.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ShellContextMenu {
            id: menu
            width: viewport.width
            onDismissRequested: popup.close()
            onActionTriggered: function(actionId) {
                // Close first so actions opening an editor keep the new editor's focus.
                popup.close()
                popup.actionTriggered(actionId)
            }
            onCurrentIndexChanged: {
                if (currentIndex < 0)
                    return
                var top = contentPadding + currentIndex * (rowHeight + 1)
                var bottom = top + rowHeight
                viewport.contentY = Math.max(0, Math.min(
                    Math.max(0, viewport.contentHeight - viewport.height),
                    top < viewport.contentY ? top : Math.max(viewport.contentY, bottom - viewport.height)
                ))
            }
        }
    }
}
