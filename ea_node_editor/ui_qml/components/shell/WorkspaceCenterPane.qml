import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import ".." as Components
import "../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: root
    property var workspaceBridgeRef: typeof shellWorkspaceBridge !== "undefined" ? shellWorkspaceBridge : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphActionBridgeRef
    property var graphCanvasStateBridgeRef
    property var graphCanvasCommandBridgeRef
    property var overlayHostItem
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    property alias graphCanvasRef: graphCanvas
    property string linkTargetPickMode: ""
    property string linkTargetPickSourceWorkspaceId: ""
    property string linkTargetPickSourceNodeId: ""
    signal nodeCommentEditorRequested(string nodeId, bool compose)
    signal linkTargetPickRequested(string kind, string sourceWorkspaceId, string sourceNodeId)
    signal linkTargetPicked(string kind, string workspaceId, string nodeId, string label, string subtitle)
    signal linkTargetPickCancelled()

    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property string tabStripDensityPreset: String(root.workspaceBridgeRef.graphics_tab_strip_density || "compact")
    readonly property bool compactTabStripDensity: root.tabStripDensityPreset === "compact"

    Layout.fillWidth: true
    Layout.fillHeight: true
    color: themePalette.panel_bg
    border.color: themePalette.border

    function clearLinkTargetPickMode() {
        root.linkTargetPickMode = "";
        root.linkTargetPickSourceWorkspaceId = "";
        root.linkTargetPickSourceNodeId = "";
    }

    function selectNodeForLinkSource(workspaceId, nodeId, callback) {
        var normalizedWorkspaceId = String(workspaceId || "").trim();
        var normalizedNodeId = String(nodeId || "").trim();
        if (!normalizedWorkspaceId.length || !normalizedNodeId.length)
            return;
        if (root.workspaceBridgeRef
                && normalizedWorkspaceId !== String(root.workspaceBridgeRef.active_workspace_id || ""))
            root.workspaceBridgeRef.activate_workspace(normalizedWorkspaceId);
        Qt.callLater(function() {
            if (graphCanvas.sceneCommandBridge && graphCanvas.sceneCommandBridge.select_node)
                graphCanvas.sceneCommandBridge.select_node(normalizedNodeId, false);
            if (callback)
                Qt.callLater(callback);
        });
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.compactTabStripDensity ? 34 : 44
            color: root.themePalette.toolbar_bg
            border.color: root.themePalette.border

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Item {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                    implicitHeight: viewControlsStrip.implicitHeight

                    ShellLabeledTabStrip {
                        id: viewControlsStrip
                        objectName: "viewControlsStrip"
                        themeBridgeRef: root.themeBridgeRef
                        graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                        uiIconsRef: root.uiIconsRef
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(0, parent.width)
                        densityPreset: root.tabStripDensityPreset
                        titleText: "VIEWS"
                        model: root.workspaceBridgeRef.active_view_items
                        minTabWidth: 56
                        tabHorizontalPadding: 20
                        contextMenuActions: [
                            { "actionId": "export", "text": "Export View..." },
                            { "actionId": "export_all", "text": "Export All Views..." },
                            { "actionId": "rename", "text": "Rename View" },
                            { "actionId": "delete", "text": "Delete View", "destructive": true }
                        ]
                        createButtonText: "New View"
                        isTabActive: function(itemData) {
                            return !!itemData.active
                        }
                        onTabActivated: function(itemData) {
                            root.workspaceBridgeRef.request_switch_view(itemData.view_id)
                        }
                        onTabMoveRequested: function(fromIndex, toIndex, _itemData) {
                            root.workspaceBridgeRef.request_move_view_tab(fromIndex, toIndex)
                        }
                        onContextMenuActionRequested: function(actionId, itemData) {
                            if (actionId === "export") {
                                root.workspaceBridgeRef.request_export_view(String(itemData.view_id || ""))
                                return
                            }
                            if (actionId === "export_all") {
                                root.workspaceBridgeRef.request_export_all_views()
                                return
                            }
                            if (actionId === "rename") {
                                root.workspaceBridgeRef.request_rename_view(String(itemData.view_id || ""))
                                return
                            }
                            if (actionId === "delete")
                                root.workspaceBridgeRef.request_close_view(String(itemData.view_id || ""))
                        }
                        onCreateActivated: root.workspaceBridgeRef.request_create_view()
                    }
                }
            }
        }

        Components.GraphCanvas {
            id: graphCanvas
            Layout.fillWidth: true
            Layout.fillHeight: true
            graphActionBridge: root.graphActionBridgeRef
            canvasStateBridge: root.graphCanvasStateBridgeRef
            canvasCommandBridge: root.graphCanvasCommandBridgeRef
            overlayHostItem: root.overlayHostItem
            nodeLinkTargetPickActive: root.linkTargetPickMode === "node"
            nodeLinkTargetPickCancelActive: root.linkTargetPickMode.length > 0
            nodeLinkTargetPickWorkspaceId: root.workspaceBridgeRef
                ? String(root.workspaceBridgeRef.active_workspace_id || "")
                : ""
            onNodeCommentEditorRequested: function(nodeId, compose) {
                root.nodeCommentEditorRequested(String(nodeId || ""), Boolean(compose))
            }
            onNodeLinkTargetPickRequested: function(kind, sourceWorkspaceId, sourceNodeId) {
                root.linkTargetPickRequested(
                    String(kind || ""),
                    String(sourceWorkspaceId || ""),
                    String(sourceNodeId || "")
                )
            }
            onNodeLinkTargetPicked: function(workspaceId, nodeId, label, subtitle) {
                root.linkTargetPicked(
                    "node",
                    String(workspaceId || ""),
                    String(nodeId || ""),
                    String(label || ""),
                    String(subtitle || "")
                )
                root.clearLinkTargetPickMode()
            }
            onNodeLinkTargetPickCancelled: function() {
                root.linkTargetPickCancelled()
                root.clearLinkTargetPickMode()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.compactTabStripDensity ? 36 : 48
            color: root.themePalette.toolbar_bg
            border.color: root.themePalette.border

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                    ShellLabeledTabStrip {
                        id: workspaceControlsStrip
                        objectName: "workspaceControlsStrip"
                        themeBridgeRef: root.themeBridgeRef
                        graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                        uiIconsRef: root.uiIconsRef
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignVCenter
                    densityPreset: root.tabStripDensityPreset
                    titleText: "WORKSPACES"
                    model: root.workspaceBridgeRef.workspace_tabs
                    minTabWidth: 132
                    maxTabWidth: model && model.length > 3 && tabsViewportWidth > 0
                        ? Math.max(effectiveMinTabWidth, Math.floor(tabsViewportWidth))
                        : 0
                    tabHorizontalPadding: 24
                    contextMenuActions: [
                        { "actionId": "rename", "text": "Rename Workspace" },
                        { "actionId": "delete", "text": "Delete Workspace", "destructive": true }
                    ]
                    createButtonText: "New Workspace"
                    isTabActive: function(itemData) {
                        return itemData.workspace_id === root.workspaceBridgeRef.active_workspace_id
                    }
                    onTabActivated: function(itemData) {
                        if (root.linkTargetPickMode === "workspace") {
                            var pickedWorkspaceId = String(itemData.workspace_id || "")
                            var pickedLabel = String(itemData.label || itemData.title || pickedWorkspaceId)
                            root.linkTargetPicked("workspace", pickedWorkspaceId, "", pickedLabel, "Workspace")
                            root.clearLinkTargetPickMode()
                            return
                        }
                        if (root.linkTargetPickMode === "node") {
                            root.workspaceBridgeRef.activate_workspace(itemData.workspace_id)
                            return
                        }
                        root.workspaceBridgeRef.activate_workspace(itemData.workspace_id)
                    }
                    onTabMoveRequested: function(fromIndex, toIndex, _itemData) {
                        root.workspaceBridgeRef.request_move_workspace_tab(fromIndex, toIndex)
                    }
                    onContextMenuActionRequested: function(actionId, itemData) {
                        if (actionId === "rename") {
                            root.workspaceBridgeRef.request_rename_workspace_by_id(String(itemData.workspace_id || ""))
                            return
                        }
                        if (actionId === "delete")
                            root.workspaceBridgeRef.request_close_workspace_by_id(String(itemData.workspace_id || ""))
                    }
                    onCreateActivated: root.workspaceBridgeRef.request_create_workspace()
                }
            }
        }

        Rectangle {
            id: consolePane
            objectName: "workspaceConsolePane"
            property bool paneCollapsed: false
            property real defaultExpandedHeight: 170
            property real minimumExpandedHeight: 128
            property real maximumExpandedHeight: Math.max(
                defaultExpandedHeight,
                Math.min(
                    520,
                    Math.max(minimumExpandedHeight, root.height > 0 ? root.height - 180 : 520)
                )
            )
            property real expandedHeight: defaultExpandedHeight
            property int collapsedHeight: 30
            property real animatedPaneHeight: paneCollapsed ? collapsedHeight : expandedHeight
            property real expandedContentOpacity: paneCollapsed ? 0 : 1
            property bool resizeDragActive: false
            property bool panePersistenceRestoring: false

            onMaximumExpandedHeightChanged: {
                if (expandedHeight > maximumExpandedHeight)
                    setExpandedHeight(maximumExpandedHeight)
            }

            onMinimumExpandedHeightChanged: {
                if (expandedHeight < minimumExpandedHeight)
                    setExpandedHeight(minimumExpandedHeight)
            }

            function refreshAncestorLayouts() {
                var candidate = consolePane.parent
                while (candidate) {
                    if (candidate.forceLayout)
                        candidate.forceLayout()
                    candidate = candidate.parent
                }
            }

            function persistedPaneCollapsedValue() {
                if (!root.workspaceBridgeRef)
                    return consolePane.paneCollapsed
                var collapsedMap = root.workspaceBridgeRef.shell_panel_collapsed || ({})
                if (collapsedMap.output_panel === undefined)
                    return consolePane.paneCollapsed
                return Boolean(collapsedMap.output_panel)
            }

            function persistPaneCollapsed() {
                if (consolePane.panePersistenceRestoring)
                    return
                if (!root.workspaceBridgeRef || !root.workspaceBridgeRef.set_shell_panel_collapsed)
                    return
                root.workspaceBridgeRef.set_shell_panel_collapsed("output_panel", consolePane.paneCollapsed)
            }

            function setPaneCollapsed(collapsed, persist) {
                consolePane.paneCollapsed = Boolean(collapsed)
                if (persist !== false)
                    consolePane.persistPaneCollapsed()
                Qt.callLater(consolePane.refreshAncestorLayouts)
            }

            function restorePersistedPaneCollapsed() {
                if (!root.workspaceBridgeRef)
                    return
                consolePane.panePersistenceRestoring = true
                consolePane.setPaneCollapsed(consolePane.persistedPaneCollapsedValue(), false)
                consolePane.panePersistenceRestoring = false
            }

            function collapsePane() {
                consolePane.setPaneCollapsed(true, true)
            }

            function expandPane() {
                consolePane.setPaneCollapsed(false, true)
            }

            function togglePane() {
                consolePane.setPaneCollapsed(!consolePane.paneCollapsed, true)
            }

            function clampExpandedHeight(value) {
                return Math.max(
                    consolePane.minimumExpandedHeight,
                    Math.min(consolePane.maximumExpandedHeight, value)
                )
            }

            function setExpandedHeight(value) {
                consolePane.expandedHeight = consolePane.clampExpandedHeight(value)
                Qt.callLater(consolePane.refreshAncestorLayouts)
            }

            Component.onCompleted: consolePane.restorePersistedPaneCollapsed()

            Connections {
                target: root.workspaceBridgeRef
                function onGraphics_preferences_changed() {
                    consolePane.restorePersistedPaneCollapsed()
                }
            }

            function consoleChannelLabel(channelIndex) {
                if (channelIndex === 0)
                    return "Output"
                if (channelIndex === 1)
                    return "Warnings"
                return "Errors"
            }

            function consoleChannelCount(channelIndex) {
                if (channelIndex === 1)
                    return Number(root.workspaceBridgeRef.warning_count_value || 0)
                if (channelIndex === 2)
                    return Number(root.workspaceBridgeRef.error_count_value || 0)
                return 0
            }

            function consoleChannelObjectName(channelIndex) {
                if (channelIndex === 0)
                    return "workspaceConsoleOutputTab"
                if (channelIndex === 1)
                    return "workspaceConsoleWarningsTab"
                return "workspaceConsoleErrorsTab"
            }

            function consoleSeverityColor(channelIndex) {
                if (channelIndex === 1)
                    return root.themePalette.inspector_smart_modified_fg || "#E6D28D"
                if (channelIndex === 2)
                    return root.themePalette.inspector_danger_fg || "#F7A1A1"
                return root.themePalette.accent || "#60CDFF"
            }

            Layout.fillWidth: true
            Layout.preferredHeight: consolePane.animatedPaneHeight
            Layout.minimumHeight: consolePane.paneCollapsed
                ? consolePane.collapsedHeight
                : consolePane.minimumExpandedHeight
            Layout.maximumHeight: consolePane.paneCollapsed
                ? consolePane.collapsedHeight
                : consolePane.maximumExpandedHeight
            color: root.themePalette.panel_bg
            border.color: root.themePalette.border
            clip: true

            Behavior on animatedPaneHeight {
                enabled: !consolePane.resizeDragActive
                NumberAnimation {
                    duration: 220
                    easing.type: Easing.InOutCubic
                }
            }

            Behavior on expandedContentOpacity {
                NumberAnimation {
                    duration: 150
                    easing.type: Easing.OutCubic
                }
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    color: root.themePalette.toolbar_bg

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        spacing: 8

                        Row {
                            id: consoleChannelTabs
                            objectName: "workspaceConsoleSeverityTabs"
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredHeight: 30
                            height: 30
                            spacing: 2

                            Repeater {
                                model: 3

                                Item {
                                    id: consoleChannelTab
                                    property int channelIndex: index
                                    objectName: consolePane.consoleChannelObjectName(channelIndex)
                                    property bool active: consoleTabs.currentIndex === channelIndex
                                    property int badgeValue: consolePane.consoleChannelCount(channelIndex)
                                    readonly property color severityColor: consolePane.consoleSeverityColor(channelIndex)
                                    readonly property bool countBadgeVisible: channelIndex > 0

                                    width: Math.max(
                                        channelIndex === 0 ? 82 : 112,
                                        Math.ceil(
                                            tabLabelMetrics.advanceWidth
                                                + (countBadgeVisible ? badgeTextMetrics.advanceWidth + 38 : 28)
                                        )
                                    )
                                    height: 30

                                    TextMetrics {
                                        id: tabLabelMetrics
                                        text: consolePane.consoleChannelLabel(consoleChannelTab.channelIndex)
                                        font.pixelSize: 11
                                        font.bold: consoleChannelTab.active
                                    }

                                    TextMetrics {
                                        id: badgeTextMetrics
                                        text: String(consoleChannelTab.badgeValue)
                                        font.pixelSize: 10
                                        font.bold: true
                                    }

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        anchors.topMargin: 4
                                        anchors.bottomMargin: 3
                                        radius: 3
                                        color: consoleChannelTab.active
                                            ? root.themePalette.tab_selected_bg
                                            : (consoleChannelMouseArea.containsMouse ? root.themePalette.hover : "transparent")
                                        border.width: 1
                                        border.color: consoleChannelTab.active
                                            ? root.themePalette.input_border
                                            : "transparent"
                                    }

                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 6

                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: consolePane.consoleChannelLabel(consoleChannelTab.channelIndex)
                                            color: consoleChannelTab.active
                                                ? root.themePalette.tab_selected_fg
                                                : root.themePalette.tab_fg
                                            font.pixelSize: 11
                                            font.bold: consoleChannelTab.active
                                        }

                                        Rectangle {
                                            objectName: consoleChannelTab.channelIndex === 1
                                                ? "workspaceConsoleWarningsBadge"
                                                : (consoleChannelTab.channelIndex === 2
                                                    ? "workspaceConsoleErrorsBadge"
                                                    : "")
                                            visible: consoleChannelTab.countBadgeVisible
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Math.max(18, badgeText.implicitWidth + 10)
                                            height: 16
                                            radius: 8
                                            color: consoleChannelTab.badgeValue > 0
                                                ? Qt.alpha(consoleChannelTab.severityColor, 0.18)
                                                : root.themePalette.tab_bg
                                            border.width: 1
                                            border.color: consoleChannelTab.badgeValue > 0
                                                ? Qt.alpha(consoleChannelTab.severityColor, 0.85)
                                                : root.themePalette.border

                                            Text {
                                                id: badgeText
                                                anchors.centerIn: parent
                                                text: String(consoleChannelTab.badgeValue)
                                                color: consoleChannelTab.badgeValue > 0
                                                    ? consoleChannelTab.severityColor
                                                    : root.themePalette.muted_fg
                                                font.pixelSize: 10
                                                font.bold: true
                                            }
                                        }
                                    }

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.leftMargin: 5
                                        anchors.rightMargin: 5
                                        anchors.bottom: parent.bottom
                                        height: 2
                                        radius: 1
                                        color: consoleChannelTab.active
                                            ? consoleChannelTab.severityColor
                                            : "transparent"
                                    }

                                    MouseArea {
                                        id: consoleChannelMouseArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: consoleTabs.currentIndex = consoleChannelTab.channelIndex
                                    }
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                        ShellButton {
                            themeBridgeRef: root.themeBridgeRef
                            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                            uiIconsRef: root.uiIconsRef
                            objectName: "workspaceConsoleClearButton"
                            text: "Clear"
                            onClicked: root.workspaceBridgeRef.clear_all()
                        }
                        ShellButton {
                            themeBridgeRef: root.themeBridgeRef
                            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                            uiIconsRef: root.uiIconsRef
                            objectName: "workspaceConsoleCollapseButton"
                            readonly property string tooltipKey: consolePane.paneCollapsed
                                ? "shell.workspace_console.expand_output_panel"
                                : "shell.workspace_console.collapse_output_panel"
                            iconName: consolePane.paneCollapsed ? "chevron-up" : "chevron-down"
                            iconSize: 14
                            implicitWidth: 26
                            implicitHeight: 24
                            tooltipText: TooltipCopy.text(tooltipCopyBridge, tooltipKey)
                            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, tooltipKey)
                            onClicked: consolePane.togglePane()
                        }
                    }
                }

                StackLayout {
                    id: consoleTabs
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 0
                    visible: consolePane.expandedContentOpacity > 0.01
                    opacity: consolePane.expandedContentOpacity
                    enabled: consolePane.expandedContentOpacity > 0.99

                    ScrollView {
                        id: outputScroll
                        objectName: "workspaceConsoleOutputScrollView"
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        readonly property real scrollContentY: contentItem ? contentItem.contentY : 0
                        readonly property real scrollContentHeight: contentItem ? contentItem.contentHeight : 0
                        readonly property real scrollViewportHeight: availableHeight

                        function scrollToBottom() {
                            if (!contentItem)
                                return
                            contentItem.contentY = Math.max(0, contentItem.contentHeight - availableHeight)
                        }

                        TextArea {
                            objectName: "workspaceConsoleOutputTextArea"
                            width: Math.max(outputScroll.availableWidth, contentWidth + leftPadding + rightPadding)
                            height: Math.max(outputScroll.availableHeight, contentHeight + topPadding + bottomPadding)
                            readOnly: true
                            text: root.workspaceBridgeRef.output_text
                            color: root.themePalette.app_fg
                            font.family: "Consolas"
                            font.pixelSize: 12
                            wrapMode: TextArea.NoWrap
                            background: Rectangle { color: root.themePalette.console_bg }
                            selectByMouse: true
                            persistentSelection: true
                            leftPadding: 8
                            rightPadding: 8
                            topPadding: 6
                            bottomPadding: 6
                        }
                    }
                    ScrollView {
                        id: warningsScroll
                        objectName: "workspaceConsoleWarningsScrollView"
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        readonly property real scrollContentY: contentItem ? contentItem.contentY : 0
                        readonly property real scrollContentHeight: contentItem ? contentItem.contentHeight : 0
                        readonly property real scrollViewportHeight: availableHeight

                        function scrollToBottom() {
                            if (!contentItem)
                                return
                            contentItem.contentY = Math.max(0, contentItem.contentHeight - availableHeight)
                        }

                        TextArea {
                            objectName: "workspaceConsoleWarningsTextArea"
                            width: Math.max(warningsScroll.availableWidth, contentWidth + leftPadding + rightPadding)
                            height: Math.max(warningsScroll.availableHeight, contentHeight + topPadding + bottomPadding)
                            readOnly: true
                            text: root.workspaceBridgeRef.warnings_text
                            color: "#E6D28D"
                            font.family: "Consolas"
                            font.pixelSize: 12
                            wrapMode: TextArea.NoWrap
                            background: Rectangle { color: root.themePalette.console_bg }
                            selectByMouse: true
                            persistentSelection: true
                            leftPadding: 8
                            rightPadding: 8
                            topPadding: 6
                            bottomPadding: 6
                        }
                    }
                    ScrollView {
                        id: errorsScroll
                        objectName: "workspaceConsoleErrorsScrollView"
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        readonly property real scrollContentY: contentItem ? contentItem.contentY : 0
                        readonly property real scrollContentHeight: contentItem ? contentItem.contentHeight : 0
                        readonly property real scrollViewportHeight: availableHeight

                        function scrollToBottom() {
                            if (!contentItem)
                                return
                            contentItem.contentY = Math.max(0, contentItem.contentHeight - availableHeight)
                        }

                        TextArea {
                            objectName: "workspaceConsoleErrorsTextArea"
                            width: Math.max(errorsScroll.availableWidth, contentWidth + leftPadding + rightPadding)
                            height: Math.max(errorsScroll.availableHeight, contentHeight + topPadding + bottomPadding)
                            readOnly: true
                            text: root.workspaceBridgeRef.errors_text
                            color: "#F7A1A1"
                            font.family: "Consolas"
                            font.pixelSize: 12
                            wrapMode: TextArea.NoWrap
                            background: Rectangle { color: root.themePalette.console_bg }
                            selectByMouse: true
                            persistentSelection: true
                            leftPadding: 8
                            rightPadding: 8
                            topPadding: 6
                            bottomPadding: 6
                        }
                    }
                }
            }

            Rectangle {
                id: workspaceConsoleResizeHandle
                objectName: "workspaceConsoleResizeHandle"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 6
                z: 20
                visible: !consolePane.paneCollapsed
                color: workspaceConsoleResizeMouseArea.containsMouse || consolePane.resizeDragActive
                    ? Qt.alpha(root.themePalette.accent || "#60CDFF", 0.45)
                    : "transparent"

                MouseArea {
                    id: workspaceConsoleResizeMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.SplitVCursor
                    preventStealing: true
                    property real pressSceneY: 0
                    property real pressExpandedHeight: 0

                    onPressed: function(mouse) {
                        var scenePoint = mapToItem(null, mouse.x, mouse.y)
                        pressSceneY = scenePoint.y
                        pressExpandedHeight = consolePane.expandedHeight
                        consolePane.resizeDragActive = true
                        mouse.accepted = true
                    }

                    onPositionChanged: function(mouse) {
                        if (!pressed)
                            return
                        var scenePoint = mapToItem(null, mouse.x, mouse.y)
                        consolePane.setExpandedHeight(
                            pressExpandedHeight - (scenePoint.y - pressSceneY)
                        )
                    }

                    onReleased: consolePane.resizeDragActive = false
                    onCanceled: consolePane.resizeDragActive = false
                }
            }
        }
    }
}
