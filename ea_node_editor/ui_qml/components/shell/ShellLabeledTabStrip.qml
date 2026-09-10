import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQml.Models 2.15
import "../common/TooltipCopy.js" as TooltipCopy

RowLayout {
    id: root
    property string titleText: ""
    property var model: []
    property var isTabActive: null
    property string densityPreset: "compact"
    property string tabLabelKey: "label"
    property int minTabWidth: 56
    property int maxTabWidth: 0
    property int tabHorizontalPadding: 24
    property int createButtonMinimumWidth: 108
    property int createButtonHorizontalPadding: 10
    property var contextMenuActions: []
    property string createButtonText: ""
    property bool createButtonAccentOutline: false
    property var contextMenuItemData: null
    property var tabSlots: []
    property int testWheelHorizontalDelta: 0
    property int testWheelVerticalDelta: 0
    property bool testWheelShiftHeld: false
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property bool compactDensity: String(root.densityPreset).toLowerCase() === "compact"
    readonly property int titleFontSize: root.compactDensity ? 8 : 10
    readonly property real titleLetterSpacing: root.compactDensity ? 0.9 : 1.1
    readonly property int cardVerticalPadding: root.compactDensity ? 1 : 5
    readonly property int cardHorizontalPadding: root.compactDensity ? 3 : 6
    readonly property int cardRadius: root.compactDensity ? 9 : 12
    readonly property int cardSpacing: root.compactDensity ? 3 : 5
    readonly property int tabHeight: root.compactDensity ? 22 : 28
    readonly property int tabRadius: root.compactDensity ? 7 : 9
    readonly property int tabFontSize: root.compactDensity ? 10 : 12
    readonly property int effectiveMinTabWidth: root.compactDensity
        ? Math.max(42, Math.round(root.minTabWidth * 0.82))
        : root.minTabWidth
    readonly property int effectiveTabHorizontalPadding: root.compactDensity
        ? Math.max(12, root.tabHorizontalPadding - 4)
        : root.tabHorizontalPadding
    readonly property int createButtonHeight: root.compactDensity ? 24 : 30
    readonly property int createButtonFontSize: root.compactDensity ? 9 : 11
    readonly property int createButtonIconSize: root.compactDensity ? 14 : 18
    readonly property int effectiveCreateButtonMinimumWidth: root.compactDensity
        ? Math.max(88, root.createButtonMinimumWidth - 18)
        : root.createButtonMinimumWidth
    readonly property int effectiveCreateButtonHorizontalPadding: root.compactDensity
        ? Math.max(8, root.createButtonHorizontalPadding - 2)
        : root.createButtonHorizontalPadding
    readonly property int overflowButtonSize: root.compactDensity ? 24 : 28
    readonly property real tabsViewportWidth: Math.max(0, Number(tabsViewport.width) || 0)
    readonly property real tabsContentWidth: Math.max(0, Number(tabsViewport.contentWidth) || 0)
    readonly property real tabsContentX: Math.max(0, Number(tabsViewport.contentX) || 0)
    readonly property real tabsMaxContentX: Math.max(0, root.tabsContentWidth - root.tabsViewportWidth)
    readonly property bool tabsOverflowActive: root.tabsMaxContentX > 0.5
    readonly property bool tabsAtStart: !root.tabsOverflowActive || root.tabsContentX <= 0.5
    readonly property bool tabsAtEnd: !root.tabsOverflowActive || root.tabsContentX >= root.tabsMaxContentX - 0.5
    readonly property int effectiveMaxTabWidth: root.maxTabWidth > 0
        ? Math.max(root.effectiveMinTabWidth, root.maxTabWidth)
        : 32767
    readonly property bool lightTheme: String(root.themePalette.icon_variant || "light") === "dark"

    signal tabActivated(var itemData)
    signal tabMoveRequested(int fromIndex, int toIndex, var itemData)
    signal contextMenuActionRequested(string actionId, var itemData)
    signal createActivated()

    readonly property bool canReorderTabs: root.model && root.model.length !== undefined && root.model.length > 1

    function tabLabelForItem(itemData) {
        if (itemData && itemData[root.tabLabelKey] !== undefined)
            return String(itemData[root.tabLabelKey])
        return ""
    }

    function white(alpha) {
        return Qt.rgba(1, 1, 1, alpha)
    }

    function black(alpha) {
        return Qt.rgba(0, 0, 0, alpha)
    }

    function glassTrackBorderColor() {
        return root.lightTheme
            ? Qt.rgba(0.16, 0.25, 0.34, 0.16)
            : root.white(0.105)
    }

    function glassTabFill(active, dragging, hovered) {
        if (active)
            return root.lightTheme ? root.white(0.54) : root.white(0.075)
        if (dragging)
            return root.lightTheme ? root.white(0.22) : root.white(0.045)
        return hovered ? (root.lightTheme ? root.white(0.16) : root.white(0.035)) : "transparent"
    }

    function glassTabBorderColor(active, dragging, hovered) {
        if (active) {
            return root.lightTheme
                ? Qt.rgba(0.12, 0.42, 0.68, 0.46)
                : Qt.rgba(0.74, 0.90, 1.0, 0.50)
        }
        if (dragging)
            return root.lightTheme ? Qt.rgba(0.22, 0.32, 0.42, 0.22) : root.white(0.16)
        return root.lightTheme
            ? (hovered ? Qt.rgba(0.18, 0.28, 0.38, 0.18) : "transparent")
            : (hovered ? root.white(0.14) : "transparent")
    }

    function glassHighlightOpacity(active, dragging, hovered) {
        if (active)
            return root.lightTheme ? 0.12 : 0.10
        if (dragging || hovered)
            return root.lightTheme ? 0.08 : 0.06
        return 0.0
    }

    function orderedTabSlots() {
        var slots = []
        for (var index = 0; index < root.tabSlots.length; index += 1) {
            var child = root.tabSlots[index]
            if (!child || child.width <= 0 || !child.visible)
                continue
            slots.push(child)
        }
        slots.sort(function(a, b) { return a.x - b.x })
        return slots
    }

    function reorderTargetIndexForCenterX(slots, centerX) {
        var targetIndex = slots.length - 1
        for (var slotIndex = 0; slotIndex < slots.length; slotIndex += 1) {
            var midpoint = slots[slotIndex].x + (slots[slotIndex].width / 2)
            if (centerX <= midpoint) {
                targetIndex = slotIndex
                break
            }
        }
        return targetIndex
    }

    function updateTabReorderTarget(tabButton) {
        if (!root.canReorderTabs || !tabButton || !tabsList.contentItem)
            return
        var slots = root.orderedTabSlots()
        if (!slots.length)
            return
        var centerPoint = tabButton.mapToItem(tabsList.contentItem, tabButton.width / 2, tabButton.height / 2)
        var targetIndex = root.reorderTargetIndexForCenterX(slots, centerPoint.x)
        if (targetIndex < 0 || targetIndex === tabButton.visualIndex)
            return
        visualModel.items.move(tabButton.visualIndex, targetIndex)
    }

    function setTabSlotRegistration(slot, registered) {
        if (!slot)
            return
        var nextSlots = []
        var exists = false
        for (var index = 0; index < root.tabSlots.length; index += 1) {
            var current = root.tabSlots[index]
            if (!current)
                continue
            if (current === slot) {
                exists = true
                if (!registered)
                    continue
            }
            nextSlots.push(current)
        }
        if (registered && !exists)
            nextSlots.push(slot)
        root.tabSlots = nextSlots
    }

    function registerTabSlot(slot) {
        root.setTabSlotRegistration(slot, true)
        root.scheduleActiveTabReveal()
    }

    function unregisterTabSlot(slot) {
        root.setTabSlotRegistration(slot, false)
        root.scheduleActiveTabReveal()
    }

    function dragMinimumXForSlot(slot) {
        if (!slot || slot.draggingInOverlay)
            return 0
        return -slot.x
    }

    function dragMaximumXForSlot(slot) {
        if (!slot)
            return 0
        var maxOffset = dragOverlay.width - slot.buttonWidth
        if (slot.draggingInOverlay)
            return Math.max(0, maxOffset)
        return Math.max(0, maxOffset - slot.x)
    }

    function resetDraggedTabPosition(tabButton) {
        if (!tabButton)
            return
        tabButton.x = 0
        tabButton.y = 0
    }

    function finalizeTabDrag(tabButton) {
        if (!tabButton)
            return
        var didReorder = tabButton.dragStartIndex >= 0 && tabButton.dragStartIndex !== tabButton.visualIndex
        tabButton.suppressClick = didReorder || tabButton.dragging
        var fromIndex = tabButton.dragStartIndex
        var toIndex = tabButton.visualIndex
        tabButton.dragStartIndex = -1
        if (fromIndex >= 0 && fromIndex !== toIndex)
            root.tabMoveRequested(fromIndex, toIndex, tabButton.itemData)
        root.scheduleActiveTabReveal()
    }

    function openContextMenu(itemData, positionX, positionY) {
        var actions = root.contextMenuActions || []
        if (!actions.length)
            return
        root.contextMenuItemData = itemData
        contextActionPopup.openAt(root, positionX, positionY)
    }

    function clampTabsContentX(value) {
        return Math.max(0, Math.min(root.tabsMaxContentX, Number(value) || 0))
    }

    function setTabsContentX(value) {
        var nextValue = root.tabsOverflowActive ? root.clampTabsContentX(value) : 0
        if (Math.abs(nextValue - tabsViewport.contentX) < 0.5)
            return false
        tabsViewport.contentX = nextValue
        return true
    }

    function scrollTabsBy(delta) {
        return root.setTabsContentX(tabsViewport.contentX + (Number(delta) || 0))
    }

    function scrollTabsTowardStart() {
        var distance = Math.max(48, Math.round(root.tabsViewportWidth * 0.72))
        return root.scrollTabsBy(-distance)
    }

    function scrollTabsTowardEnd() {
        var distance = Math.max(48, Math.round(root.tabsViewportWidth * 0.72))
        return root.scrollTabsBy(distance)
    }

    function activeTabSlot() {
        if (typeof root.isTabActive !== "function")
            return null
        var slots = root.orderedTabSlots()
        for (var index = 0; index < slots.length; index += 1) {
            var slot = slots[index]
            if (root.isTabActive(slot.itemData))
                return slot
        }
        return null
    }

    function ensureTabSlotVisible(slot) {
        if (!slot)
            return false
        if (!root.tabsOverflowActive)
            return root.setTabsContentX(0)
        var slotLeft = Number(slot.x) || 0
        var slotRight = slotLeft + (Number(slot.width) || 0)
        var viewportLeft = tabsViewport.contentX
        var viewportRight = viewportLeft + root.tabsViewportWidth
        if (slotRight - slotLeft > root.tabsViewportWidth)
            return root.setTabsContentX(slotLeft)
        if (slotLeft < viewportLeft)
            return root.setTabsContentX(slotLeft)
        if (slotRight > viewportRight)
            return root.setTabsContentX(slotRight - root.tabsViewportWidth)
        return false
    }

    function ensureActiveTabVisible() {
        if (!root.tabsOverflowActive)
            return root.setTabsContentX(0)
        return root.ensureTabSlotVisible(root.activeTabSlot())
    }

    function scheduleActiveTabReveal() {
        activeTabRevealTimer.restart()
    }

    function wheelAxisDelta(wheel, axisName) {
        if (!wheel)
            return 0.0
        var delta = 0.0
        if (wheel.angleDelta && wheel.angleDelta[axisName] !== undefined && Number(wheel.angleDelta[axisName]) !== 0)
            delta = Number(wheel.angleDelta[axisName])
        else if (wheel.pixelDelta && wheel.pixelDelta[axisName] !== undefined && Number(wheel.pixelDelta[axisName]) !== 0)
            delta = Number(wheel.pixelDelta[axisName]) * 0.5
        if (wheel.inverted)
            delta = -delta
        return delta
    }

    function scrollStepFromWheelDelta(delta) {
        var step = (-Number(delta) / 120.0) * 40.0
        if (Math.abs(step) < 1.0)
            step = delta > 0 ? -24.0 : 24.0
        return step
    }

    function applyWheelScroll(wheel) {
        if (!root.tabsOverflowActive)
            return false
        var deltaX = root.wheelAxisDelta(wheel, "x")
        var deltaY = root.wheelAxisDelta(wheel, "y")
        var modifiers = Number(wheel && wheel.modifiers) || 0
        var hasHorizontalDelta = Math.abs(deltaX) >= 0.001
        var shiftHeld = (modifiers & Qt.ShiftModifier) === Qt.ShiftModifier
        if (!hasHorizontalDelta && !shiftHeld)
            return false
        var sourceDelta = hasHorizontalDelta ? deltaX : deltaY
        if (Math.abs(sourceDelta) < 0.001)
            return false
        return root.scrollTabsBy(root.scrollStepFromWheelDelta(sourceDelta))
    }

    function applyConfiguredTestWheelScroll() {
        return root.applyWheelScroll({
            "angleDelta": {
                "x": Number(root.testWheelHorizontalDelta) || 0,
                "y": Number(root.testWheelVerticalDelta) || 0
            },
            "modifiers": root.testWheelShiftHeld ? Qt.ShiftModifier : Qt.NoModifier,
            "inverted": false
        })
    }

    implicitWidth: titleLabel.implicitWidth + spacing + stripCard.implicitWidth
    implicitHeight: Math.max(titleLabel.implicitHeight, stripCard.implicitHeight)
    spacing: root.compactDensity ? 8 : 10

    onModelChanged: root.scheduleActiveTabReveal()

    onWidthChanged: {
        if (contextActionPopup.visible)
            contextActionPopup.close()
        root.scheduleActiveTabReveal()
    }

    onHeightChanged: {
        if (contextActionPopup.visible)
            contextActionPopup.close()
        root.scheduleActiveTabReveal()
    }

    Component.onCompleted: root.scheduleActiveTabReveal()

    Timer {
        id: activeTabRevealTimer
        interval: 0
        repeat: false
        onTriggered: root.ensureActiveTabVisible()
    }

    Text {
        id: titleLabel
        Layout.alignment: Qt.AlignVCenter
        text: root.titleText
        color: root.themePalette.muted_fg
        font.pixelSize: root.titleFontSize
        font.bold: true
        font.letterSpacing: root.titleLetterSpacing
    }

    Rectangle {
        id: stripCard
        Layout.alignment: Qt.AlignVCenter
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        implicitWidth: stripChromeRow.implicitWidth + (root.cardHorizontalPadding * 2)
        implicitHeight: stripChromeRow.implicitHeight + (root.cardVerticalPadding * 2)
        radius: (root.tabHeight / 2) + 4
        color: "transparent"
        border.width: 1
        border.color: root.glassTrackBorderColor()

        RowLayout {
            id: stripChromeRow
            anchors.fill: parent
            anchors.leftMargin: root.cardHorizontalPadding
            anchors.rightMargin: root.cardHorizontalPadding
            anchors.topMargin: root.cardVerticalPadding
            anchors.bottomMargin: root.cardVerticalPadding
            spacing: root.cardSpacing

            ShellButton {
                id: scrollBackwardButton
                objectName: "tabStripScrollBackwardButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: root.tabsOverflowActive ? root.overflowButtonSize : 0
                Layout.maximumWidth: root.tabsOverflowActive ? root.overflowButtonSize : 0
                Layout.minimumWidth: 0
                Layout.preferredHeight: root.tabHeight
                visible: root.tabsOverflowActive
                enabled: root.tabsOverflowActive && !root.tabsAtStart
                text: ""
                iconName: "chevrons-left"
                iconSize: root.compactDensity ? 14 : 16
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "shell.tab_strip.scroll_left")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "shell.tab_strip.scroll_left")
                onClicked: root.scrollTabsTowardStart()
            }

            Item {
                id: tabsViewportHost
                objectName: "tabStripViewportHost"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: tabsList.implicitWidth
                implicitHeight: root.tabHeight

                Flickable {
                    id: tabsViewport
                    objectName: "tabStripViewport"
                    anchors.fill: parent
                    contentWidth: tabsList.width
                    contentHeight: tabsList.height
                    interactive: false
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.HorizontalFlick
                    onWidthChanged: root.scheduleActiveTabReveal()
                    onContentWidthChanged: root.scheduleActiveTabReveal()

                    ListView {
                        id: tabsList
                        objectName: "tabStripListView"
                        orientation: ListView.Horizontal
                        interactive: false
                        spacing: root.cardSpacing
                        clip: false
                        implicitWidth: contentWidth
                        implicitHeight: root.tabHeight
                        width: contentWidth
                        height: root.tabHeight
                        model: visualModel
                        displaced: Transition {
                            NumberAnimation {
                                properties: "x,y"
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                        moveDisplaced: Transition {
                            NumberAnimation {
                                properties: "x,y"
                                duration: 180
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.NoButton
                        hoverEnabled: true
                        propagateComposedEvents: true
                        onWheel: function(wheel) {
                            if (root.applyWheelScroll(wheel))
                                wheel.accepted = true
                        }
                    }
                }

                Item {
                    id: dragOverlay
                    objectName: "tabStripDragOverlay"
                    anchors.fill: tabsViewport
                    z: 100
                }
            }

            ShellButton {
                id: scrollForwardButton
                objectName: "tabStripScrollForwardButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: root.tabsOverflowActive ? root.overflowButtonSize : 0
                Layout.maximumWidth: root.tabsOverflowActive ? root.overflowButtonSize : 0
                Layout.minimumWidth: 0
                Layout.preferredHeight: root.tabHeight
                visible: root.tabsOverflowActive
                enabled: root.tabsOverflowActive && !root.tabsAtEnd
                text: ""
                iconName: "chevrons-right"
                iconSize: root.compactDensity ? 14 : 16
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "shell.tab_strip.scroll_right")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "shell.tab_strip.scroll_right")
                onClicked: root.scrollTabsTowardEnd()
            }

            ShellCreateButton {
                id: createButton
                objectName: "tabStripCreateButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                Layout.alignment: Qt.AlignVCenter
                text: root.createButtonText
                tooltipCategory: "tutorial"
                accentOutline: root.createButtonAccentOutline
                buttonHeight: root.createButtonHeight
                labelFontPixelSize: root.createButtonFontSize
                iconCircleSize: root.createButtonIconSize
                minimumButtonWidth: root.effectiveCreateButtonMinimumWidth
                contentHorizontalPadding: root.effectiveCreateButtonHorizontalPadding
                contentSpacing: root.compactDensity ? 6 : 8
                cornerRadius: root.tabRadius
                onClicked: root.createActivated()
            }

            DelegateModel {
                id: visualModel
                model: root.model || []
                delegate: Item {
                    id: tabSlot
                    property int visualIndex: DelegateModel.itemsIndex
                    property var itemData: modelData
                    readonly property string itemLabel: root.tabLabelForItem(itemData)
                    readonly property bool itemActive: typeof root.isTabActive === "function"
                        ? !!root.isTabActive(itemData)
                        : false
                    readonly property int buttonWidth: Math.max(
                        1,
                        Math.min(
                            root.effectiveMaxTabWidth,
                            Math.max(
                                root.effectiveMinTabWidth,
                                Math.ceil(
                                    Math.max(
                                        tabLabelMetrics.advanceWidth,
                                        activeTabLabelMetrics.advanceWidth
                                    ) + root.effectiveTabHorizontalPadding
                                )
                            )
                        )
                    )
                    readonly property bool draggingInOverlay: tabButton.parent === dragOverlay
                    readonly property real dragMinimumX: root.dragMinimumXForSlot(tabSlot)
                    readonly property real dragMaximumX: root.dragMaximumXForSlot(tabSlot)
                    width: buttonWidth
                    height: root.tabHeight
                    Component.onCompleted: root.registerTabSlot(tabSlot)
                    Component.onDestruction: root.unregisterTabSlot(tabSlot)

                    TextMetrics {
                        id: tabLabelMetrics
                        text: tabSlot.itemLabel
                        font.pixelSize: root.tabFontSize
                        font.bold: false
                    }

                    TextMetrics {
                        id: activeTabLabelMetrics
                        text: tabSlot.itemLabel
                        font.pixelSize: root.tabFontSize
                        font.bold: true
                    }

                    Rectangle {
                        id: tabButton
                        width: tabSlot.buttonWidth
                        height: root.tabHeight
                        property int dragStartIndex: -1
                        property bool suppressClick: false
                        property int visualIndex: tabSlot.visualIndex
                        property var itemData: tabSlot.itemData
                        property bool active: tabSlot.itemActive
                        property bool dragging: dragArea.drag.active
                        radius: height / 2
                        color: root.glassTabFill(active, dragging, dragArea.containsMouse)
                        gradient: glassGradient
                        border.width: 1
                        border.color: root.glassTabBorderColor(active, dragging, dragArea.containsMouse)
                        z: dragging ? 200 : 0
                        scale: dragging ? 1.02 : 1.0
                        opacity: dragging ? 0.98 : 1.0
                        onXChanged: {
                            if (tabButton.dragging)
                                root.updateTabReorderTarget(tabButton)
                        }
                        onDraggingChanged: {
                            if (!tabButton.dragging)
                                root.resetDraggedTabPosition(tabButton)
                        }
                        onActiveChanged: root.scheduleActiveTabReveal()

                        Behavior on scale {
                            NumberAnimation {
                                duration: 120
                                easing.type: Easing.OutCubic
                            }
                        }

                        states: State {
                            when: tabButton.dragging
                            ParentChange {
                                target: tabButton
                                parent: dragOverlay
                            }
                            PropertyChanges {
                                target: tabButton
                                width: tabSlot.buttonWidth
                                height: root.tabHeight
                            }
                        }

                        Gradient {
                            id: glassGradient
                            GradientStop {
                                position: 0.0
                                color: tabButton.active
                                    ? (root.lightTheme ? Qt.rgba(1, 1, 1, 0.78) : root.white(0.16))
                                    : ((dragArea.containsMouse || tabButton.dragging)
                                        ? (root.lightTheme ? root.white(0.18) : root.white(0.055))
                                        : "transparent")
                            }
                            GradientStop {
                                position: 0.18
                                color: tabButton.active
                                    ? (root.lightTheme ? Qt.rgba(0.98, 0.99, 1.0, 0.68) : root.white(0.13))
                                    : ((dragArea.containsMouse || tabButton.dragging)
                                        ? (root.lightTheme ? root.white(0.14) : root.white(0.045))
                                        : "transparent")
                            }
                            GradientStop {
                                position: 0.42
                                color: tabButton.active
                                    ? (root.lightTheme ? Qt.rgba(0.94, 0.96, 0.98, 0.52) : root.white(0.095))
                                    : ((dragArea.containsMouse || tabButton.dragging)
                                        ? (root.lightTheme ? root.white(0.09) : root.white(0.030))
                                        : "transparent")
                            }
                            GradientStop {
                                position: 0.72
                                color: tabButton.active
                                    ? (root.lightTheme ? Qt.rgba(0.84, 0.88, 0.92, 0.34) : root.white(0.045))
                                    : ((dragArea.containsMouse || tabButton.dragging)
                                        ? (root.lightTheme ? Qt.rgba(0.82, 0.86, 0.90, 0.055) : root.black(0.015))
                                        : "transparent")
                            }
                            GradientStop {
                                position: 1.0
                                color: tabButton.active
                                    ? (root.lightTheme ? Qt.rgba(0.72, 0.78, 0.84, 0.18) : root.black(0.050))
                                    : ((dragArea.containsMouse || tabButton.dragging)
                                        ? (root.lightTheme ? Qt.rgba(0.72, 0.78, 0.84, 0.030) : root.black(0.018))
                                        : "transparent")
                            }
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: 2
                            anchors.rightMargin: 2
                            anchors.topMargin: 1
                            height: Math.max(1, Math.floor(parent.height / 2))
                            radius: parent.radius
                            color: root.white(
                                root.glassHighlightOpacity(
                                    tabButton.active,
                                    tabButton.dragging,
                                    dragArea.containsMouse
                                )
                            )
                            visible: root.glassHighlightOpacity(
                                tabButton.active,
                                tabButton.dragging,
                                dragArea.containsMouse
                            ) > 0
                        }

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: root.compactDensity ? 6 : 8
                            anchors.rightMargin: root.compactDensity ? 6 : 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: tabSlot.itemLabel
                            color: tabButton.active
                                ? root.themePalette.tab_selected_fg
                                : root.themePalette.tab_fg
                            font.pixelSize: root.tabFontSize
                            font.bold: tabButton.active
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }

                        MouseArea {
                            id: dragArea
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            cursorShape: root.canReorderTabs
                                ? (dragArea.drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor)
                                : Qt.PointingHandCursor
                            drag.target: root.canReorderTabs ? tabButton : null
                            drag.axis: Drag.XAxis
                            drag.minimumX: tabSlot.dragMinimumX
                            drag.maximumX: tabSlot.dragMaximumX
                            onPressed: function(mouse) {
                                if (mouse.button === Qt.LeftButton) {
                                    tabButton.dragStartIndex = tabButton.visualIndex
                                    tabButton.suppressClick = false
                                }
                            }
                            onReleased: function(mouse) {
                                if (mouse.button !== Qt.LeftButton)
                                    return
                                root.finalizeTabDrag(tabButton)
                            }
                            onCanceled: {
                                tabButton.dragStartIndex = -1
                                tabButton.suppressClick = false
                                root.scheduleActiveTabReveal()
                            }
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.LeftButton) {
                                    if (tabButton.suppressClick) {
                                        tabButton.suppressClick = false
                                        return
                                    }
                                    root.tabActivated(tabButton.itemData)
                                    return
                                }
                                if (mouse.button === Qt.RightButton) {
                                    var popupPosition = tabButton.mapToItem(root, mouse.x, mouse.y)
                                    root.openContextMenu(tabButton.itemData, popupPosition.x, popupPosition.y)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    ShellContextPopup {
        id: contextActionPopup
        themeBridgeRef: root.themeBridgeRef
        minimumWidth: 188
        actions: root.contextMenuActions
        onActionTriggered: function(actionId) {
            root.contextMenuActionRequested(actionId, root.contextMenuItemData)
        }
    }
}
