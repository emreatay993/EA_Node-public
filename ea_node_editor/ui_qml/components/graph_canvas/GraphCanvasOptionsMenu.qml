import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common
import "../graph/GraphActionPresentation.js" as GraphActionPresentation

Item {
    id: root
    property Item canvasItem: null
    property var commandBridge: null
    property var themePalette: ({})
    property real anchorX: 0
    property real anchorY: 0
    readonly property var shellContextRef: typeof shellContext !== "undefined" ? shellContext : null
    readonly property var themeBridgeRef: root.shellContextRef
        ? root.shellContextRef.themeBridge
        : (typeof themeBridge !== "undefined" ? themeBridge : null)

    readonly property int panelW: 252
    readonly property int submenuW: 170
    readonly property int rowH: 30
    readonly property int contentPad: 4
    readonly property int shadowDepth: 12
    readonly property int menuGap: 6
    readonly property int viewportPadding: 4
    property string activeSubmenu: ""
    readonly property bool hasActiveSubmenu: root.activeSubmenu.length > 0
    readonly property bool submenuOpensLeft: root.hasActiveSubmenu
        && root.canvasItem
        && root.anchorX + root.panelW + root.menuGap + root.submenuW > root.canvasItem.width - root.viewportPadding
    readonly property real resolvedX: root.submenuOpensLeft
        ? Math.max(root.viewportPadding, root.anchorX - root.menuGap - root.submenuW)
        : root.anchorX
    readonly property real availablePanelHeight: root.canvasItem
        ? Math.max(0, root.canvasItem.height - root.viewportPadding * 2 - root.shadowDepth)
        : mainColumn.implicitHeight + root.contentPad * 2
    readonly property real resolvedY: root.canvasItem
        ? Math.max(root.viewportPadding,
                   Math.min(root.anchorY, root.canvasItem.height - root.height - root.viewportPadding))
        : root.anchorY
    readonly property real mainPanelOffsetX: root.submenuOpensLeft ? root.submenuW + root.menuGap : 0
    readonly property real submenuOffsetX: root.submenuOpensLeft ? 0 : root.panelW + root.menuGap

    readonly property color panelBg: _token("panel_bg", "#1b1d22")
    readonly property color borderColor: _token("input_border", _token("border", "#3a3d45"))
    readonly property color titleFg: _token("panel_title_fg", "#f0f4fb")
    readonly property color mutedFg: _token("muted_fg", "#d0d5de")
    readonly property color accentColor: _token("accent", "#60CDFF")
    readonly property color sectionFg: _token("group_title_fg", "#bdc5d3")
    readonly property var canvasPrefs: root.canvasItem ? root.canvasItem.prefs : null
    readonly property var canvasExecutionFacts: root.canvasItem ? root.canvasItem.executionFacts : null
    readonly property var selectedWireEdgeIds: root._selectedActiveWireEdgeIds()
    readonly property string selectedWireDisplayModeValue: root._selectedWireDisplayModeValue()
    readonly property string selectedWireDisplayModeLabel:
        GraphActionPresentation.edgeDisplayModeLabel(root.selectedWireDisplayModeValue)
    readonly property bool showGrid: root.canvasPrefs ? Boolean(root.canvasPrefs.showGrid) : true
    readonly property bool snapToGrid: root.canvasItem ? Boolean(root.canvasItem.snapToGridEnabled()) : false
    readonly property bool nodeShadows: root.canvasPrefs ? Boolean(root.canvasPrefs.nodeShadowEnabled) : true
    readonly property bool selectedRunPreviewBeforeRun: root.canvasExecutionFacts
        ? Boolean(root.canvasExecutionFacts.selectedRunPreviewBeforeRun)
        : true
    readonly property bool graphsFollowShell: root.canvasPrefs ? Boolean(root.canvasPrefs.graphsFollowShellTheme) : true
    readonly property string gridStyleValue: root.canvasPrefs ? String(root.canvasPrefs.gridStyle || "lines") : "lines"
    readonly property string activeShellThemeId: root.themeBridgeRef
        ? String(root.themeBridgeRef.theme_id || "stitch_dark")
        : (root.canvasPrefs ? String(root.canvasPrefs.activeThemeId || "stitch_dark") : "stitch_dark")
    readonly property string canvasBackgroundVariant: root.canvasPrefs
        ? String(root.canvasPrefs.canvasBackgroundVariant || "theme").toLowerCase().trim()
        : "theme"
    readonly property string canvasColorValue: {
        if (root.canvasBackgroundVariant === "white")
            return root.canvasBackgroundVariant;
        if (root.canvasBackgroundVariant === "dark")
            return "dark";
        return root.activeShellThemeId === "stitch_light" ? "light" : "dark";
    }
    readonly property string canvasColorLabel: {
        if (root.canvasColorValue === "white")
            return "White";
        return "Dark";
    }
    readonly property string gridStyleLabel: root.gridStyleValue === "points" ? "Points" : "Lines"
    readonly property string canvasImportModeValue: root.canvasPrefs
        ? root.canvasPrefs.canvasImportMode : "automatic"
    readonly property string canvasImportModeLabel: root.canvasImportModeValue === "ask"
        ? "Ask every time" : "Automatic"
    readonly property string nodeElapsedTimeUnitValue: {
        // executionFacts.nodeElapsedTimeUnit is already normalized (single
        // normalization point); only the milliseconds/seconds collapse stays.
        var value = root.canvasExecutionFacts ? root.canvasExecutionFacts.nodeElapsedTimeUnit : "seconds";
        return value === "milliseconds" ? "milliseconds" : "seconds";
    }
    readonly property string nodeElapsedTimeUnitLabel: root.nodeElapsedTimeUnitValue === "milliseconds"
        ? "Milliseconds"
        : "Seconds"
    readonly property string nodeElapsedTimeVisibilityValue: {
        var value = root.canvasPrefs ? String(root.canvasPrefs.nodeElapsedTimeVisibility || "always") : "always";
        return value === "off" || value === "during_run" ? value : "always";
    }
    readonly property string nodeElapsedTimeVisibilityLabel: root.nodeElapsedTimeVisibilityValue === "off"
        ? "Off"
        : (root.nodeElapsedTimeVisibilityValue === "during_run" ? "During run" : "Always")
    readonly property string nodeCommentEditorDefaultValue: {
        var value = root.canvasPrefs ? String(root.canvasPrefs.nodeCommentEditorDefault || "canvas_popover") : "canvas_popover";
        return value === "inspector" ? "inspector" : "canvas_popover";
    }
    readonly property string nodeCommentEditorDefaultLabel: root.nodeCommentEditorDefaultValue === "inspector"
        ? "Inspector"
        : "Canvas popover"
    readonly property string shellThemeLabel: root.activeShellThemeId === "stitch_light" ? "Light" : "Dark"
    readonly property var tooltipPolicyBridge: root.canvasItem && root.canvasItem.canvasStateBridgeRef
        ? root.canvasItem.canvasStateBridgeRef
        : null
    width: root.panelW + (root.hasActiveSubmenu ? root.menuGap + root.submenuW : 0)
    height: Math.max(mainPanel.height, activeSubmenuHeight())

    onVisibleChanged: {
        if (mainScroll.contentItem)
            mainScroll.contentItem.contentY = 0;
        if (!visible)
            root.activeSubmenu = "";
    }
    onSelectedWireEdgeIdsChanged: {
        if (!root.selectedWireEdgeIds.length && root.activeSubmenu === "selectedWireDisplayMode")
            root.activeSubmenu = "";
    }

    function _token(name, fallback) {
        return root.themePalette && root.themePalette[name] !== undefined
            ? root.themePalette[name]
            : fallback;
    }

    function activeSubmenuHeight() {
        if (canvasImportSubmenuLoader.active && canvasImportSubmenuLoader.item)
            return canvasImportSubmenuLoader.item.height;
        if (canvasSubmenuLoader.active && canvasSubmenuLoader.item)
            return canvasSubmenuLoader.item.height;
        if (gridSubmenuLoader.active && gridSubmenuLoader.item)
            return gridSubmenuLoader.item.height;
        if (elapsedTimeVisibilitySubmenuLoader.active && elapsedTimeVisibilitySubmenuLoader.item)
            return elapsedTimeVisibilitySubmenuLoader.item.height;
        if (elapsedTimeUnitSubmenuLoader.active && elapsedTimeUnitSubmenuLoader.item)
            return elapsedTimeUnitSubmenuLoader.item.height;
        if (commentEditorSubmenuLoader.active && commentEditorSubmenuLoader.item)
            return commentEditorSubmenuLoader.item.height;
        if (shellSubmenuLoader.active && shellSubmenuLoader.item)
            return shellSubmenuLoader.item.height;
        if (selectedWireDisplayModeSubmenuLoader.active && selectedWireDisplayModeSubmenuLoader.item)
            return selectedWireDisplayModeSubmenuLoader.item.height;
        return 0;
    }

    function _selectedActiveWireEdgeIds() {
        var selected = root.canvasItem && root.canvasItem._normalizeEdgeIds
            ? root.canvasItem._normalizeEdgeIds(root.canvasItem.selectedEdgeIds || [])
            : [];
        var active = [];
        for (var i = 0; i < selected.length; ++i) {
            var payload = root.canvasItem && root.canvasItem._sceneEdgePayload
                ? root.canvasItem._sceneEdgePayload(selected[i])
                : null;
            if (payload && Boolean(payload.active_data_wire))
                active.push(selected[i]);
        }
        return active;
    }

    function _selectedWireDisplayModeValue() {
        var payloads = [];
        for (var i = 0; i < root.selectedWireEdgeIds.length; ++i) {
            var payload = root.canvasItem && root.canvasItem._sceneEdgePayload
                ? root.canvasItem._sceneEdgePayload(root.selectedWireEdgeIds[i])
                : null;
            if (payload)
                payloads.push(payload);
        }
        return GraphActionPresentation.commonEdgeDisplayMode(payloads);
    }

    function setSelectedWiresDisplayMode(mode) {
        if (!root.canvasItem || !root.canvasItem.setEdgesDisplayMode || !root.selectedWireEdgeIds.length)
            return false;
        return Boolean(root.canvasItem.setEdgesDisplayMode(root.selectedWireEdgeIds, mode));
    }

    function closeMenu() {
        if (root.canvasItem && root.canvasItem._closeContextMenus)
            root.canvasItem._closeContextMenus();
        else
            root.visible = false;
    }

    function setShowGrid(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_show_grid)
            root.commandBridge.set_graphics_show_grid(Boolean(value));
    }

    function setGridStyle(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_grid_style)
            root.commandBridge.set_graphics_grid_style(String(value || "lines"));
    }

    function setSnapToGrid(value) {
        if (root.commandBridge && root.commandBridge.set_snap_to_grid_enabled)
            root.commandBridge.set_snap_to_grid_enabled(Boolean(value));
    }

    function setCanvasImportMode(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_canvas_import_mode)
            root.commandBridge.set_graphics_canvas_import_mode(value);
    }

    function setNodeShadows(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_node_shadow)
            root.commandBridge.set_graphics_node_shadow(Boolean(value));
    }

    function setSelectedRunPreviewBeforeRun(value) {
        if (root.commandBridge && root.commandBridge.set_selected_run_preview_before_run)
            root.commandBridge.set_selected_run_preview_before_run(Boolean(value));
    }

    function setNodeElapsedTimeUnit(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_node_elapsed_time_unit)
            root.commandBridge.set_graphics_node_elapsed_time_unit(String(value || "seconds"));
    }

    function setNodeElapsedTimeVisibility(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_node_elapsed_time_visibility)
            root.commandBridge.set_graphics_node_elapsed_time_visibility(String(value || "always"));
    }

    function setNodeCommentEditorDefault(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_node_comment_editor_default)
            root.commandBridge.set_graphics_node_comment_editor_default(String(value || "canvas_popover"));
    }

    function setShellTheme(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_shell_theme)
            root.commandBridge.set_graphics_shell_theme(String(value || "stitch_dark"));
    }

    function setGraphsFollowShell(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_graph_follow_shell_theme)
            root.commandBridge.set_graphics_graph_follow_shell_theme(Boolean(value));
    }

    function setCanvasBackgroundVariant(value) {
        if (root.commandBridge && root.commandBridge.set_graphics_canvas_background_variant)
            root.commandBridge.set_graphics_canvas_background_variant(String(value || "theme"));
    }

    function openGraphicsSettings() {
        if (root.commandBridge && root.commandBridge.request_open_graphics_settings)
            root.commandBridge.request_open_graphics_settings();
        root.closeMenu();
    }

    MenuPanel {
        id: mainPanel
        x: root.mainPanelOffsetX
        panelWidth: root.panelW
        panelHeight: Math.min(mainColumn.implicitHeight + root.contentPad * 2,
                              root.availablePanelHeight)

        ScrollView {
            id: mainScroll
            objectName: "canvasOptionsMainScroll"
            x: root.contentPad
            y: root.contentPad
            width: mainPanel.panelWidth - root.contentPad * 2
            height: Math.max(0, mainPanel.panelHeight - root.contentPad * 2)
            contentWidth: availableWidth
            contentHeight: mainColumn.implicitHeight
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            Column {
                id: mainColumn
                width: parent.width
                spacing: 0

                SectionHeader {
                    label: "SELECTED WIRES"
                    visible: root.selectedWireEdgeIds.length > 0
                    height: visible ? 22 : 0
                }
                SubmenuRow {
                    label: "Selected Wires Display Mode"
                    value: root.selectedWireDisplayModeLabel
                    visible: root.selectedWireEdgeIds.length > 0
                    height: visible ? root.rowH : 0
                    isOpen: root.activeSubmenu === "selectedWireDisplayMode"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "selectedWireDisplayMode"
                        ? ""
                        : "selectedWireDisplayMode"
                }
                Divider {
                    visible: root.selectedWireEdgeIds.length > 0
                    height: visible ? 1 : 0
                }

                SectionHeader { label: "BACKGROUND" }
                SubmenuRow {
                    label: "Canvas color"
                    value: root.canvasColorLabel
                    isOpen: root.activeSubmenu === "canvas"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "canvas" ? "" : "canvas"
                }

                Divider {}

                SectionHeader { label: "GRID" }
                ToggleRow {
                    label: "Show grid"
                    checked: root.showGrid
                    onToggled: root.setShowGrid(!root.showGrid)
                }
                SubmenuRow {
                    label: "Grid style"
                    value: root.gridStyleLabel
                    dim: !root.showGrid
                    isOpen: root.activeSubmenu === "grid"
                    onClicked: {
                        if (!root.showGrid)
                            return;
                        root.activeSubmenu = root.activeSubmenu === "grid" ? "" : "grid";
                    }
                }
                ToggleRow {
                    label: "Snap to grid"
                    checked: root.snapToGrid
                    dim: !root.showGrid
                    onToggled: {
                        if (root.showGrid)
                            root.setSnapToGrid(!root.snapToGrid);
                    }
                }

                Divider {}

                SectionHeader { label: "NODES" }
                SubmenuRow {
                    label: "Elapsed time"
                    value: root.nodeElapsedTimeVisibilityLabel
                    isOpen: root.activeSubmenu === "elapsedTimeVisibility"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "elapsedTimeVisibility" ? "" : "elapsedTimeVisibility"
                }
                SubmenuRow {
                    label: "Elapsed unit"
                    value: root.nodeElapsedTimeUnitLabel
                    isOpen: root.activeSubmenu === "elapsedTimeUnit"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "elapsedTimeUnit" ? "" : "elapsedTimeUnit"
                }
                SubmenuRow {
                    label: "Comments"
                    value: root.nodeCommentEditorDefaultLabel
                    isOpen: root.activeSubmenu === "commentEditor"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "commentEditor" ? "" : "commentEditor"
                }

                Divider {}

                SectionHeader { label: "RUN" }
                ToggleRow {
                    label: "Preview before run"
                    checked: root.selectedRunPreviewBeforeRun
                    onToggled: root.setSelectedRunPreviewBeforeRun(!root.selectedRunPreviewBeforeRun)
                }

                Divider {}

                SectionHeader { label: "INTERACTION" }
                SubmenuRow {
                    objectName: "canvasOptionsPasteAndDropRow"
                    label: "Paste and drop"
                    value: root.canvasImportModeLabel
                    tooltipText: "Choose node types automatically, or ask how to add each pasted or dropped item."
                    isOpen: root.activeSubmenu === "canvasImport"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "canvasImport" ? "" : "canvasImport"
                }

                Divider {}

                SectionHeader { label: "EFFECTS" }
                ToggleRow {
                    label: "Node shadows"
                    checked: root.nodeShadows
                    onToggled: root.setNodeShadows(!root.nodeShadows)
                }

                Divider {}

                SectionHeader { label: "THEME" }
                SubmenuRow {
                    label: "Shell theme"
                    value: root.shellThemeLabel
                    isOpen: root.activeSubmenu === "shell"
                    onClicked: root.activeSubmenu = root.activeSubmenu === "shell" ? "" : "shell"
                }
                ToggleRow {
                    label: "Graphs follow shell"
                    checked: root.graphsFollowShell
                    onToggled: root.setGraphsFollowShell(!root.graphsFollowShell)
                }

                Divider {}

                ActionRow {
                    objectName: "canvasOptionsOpenGraphicsSettingsRow"
                    label: "Open full Graphics Settings..."
                    onClicked: root.openGraphicsSettings()
                }
            }
        }
    }

    Loader {
        id: canvasImportSubmenuLoader
        active: root.activeSubmenu === "canvasImport"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            objectName: "canvasOptionsPasteAndDropSubmenu"
            title: "Paste and drop"
            options: [
                { "label": "Automatic", "value": "automatic" },
                { "label": "Ask every time", "value": "ask" }
            ]
            currentValue: root.canvasImportModeValue
            onPicked: function(value) {
                root.setCanvasImportMode(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: selectedWireDisplayModeSubmenuLoader
        active: root.activeSubmenu === "selectedWireDisplayMode"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Selected Wires Display Mode"
            options: GraphActionPresentation.edgeDisplayChoices()
            currentValue: root.selectedWireDisplayModeValue
            onPicked: function(value) {
                root.setSelectedWiresDisplayMode(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: canvasSubmenuLoader
        active: root.activeSubmenu === "canvas"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Canvas color"
            options: [
                { "label": "Dark", "value": "dark" },
                { "label": "White", "value": "white" }
            ]
            currentValue: root.canvasColorValue
            onPicked: function(value) {
                root.setCanvasBackgroundVariant(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: gridSubmenuLoader
        active: root.activeSubmenu === "grid"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Grid style"
            options: [
                { "label": "Lines", "value": "lines" },
                { "label": "Points", "value": "points" }
            ]
            currentValue: root.gridStyleValue
            onPicked: function(value) {
                root.setGridStyle(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: elapsedTimeVisibilitySubmenuLoader
        active: root.activeSubmenu === "elapsedTimeVisibility"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Elapsed time"
            options: [
                { "label": "Off", "value": "off" },
                { "label": "During run", "value": "during_run" },
                { "label": "Always", "value": "always" }
            ]
            currentValue: root.nodeElapsedTimeVisibilityValue
            onPicked: function(value) {
                root.setNodeElapsedTimeVisibility(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: elapsedTimeUnitSubmenuLoader
        active: root.activeSubmenu === "elapsedTimeUnit"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Elapsed unit"
            options: [
                { "label": "Seconds", "value": "seconds" },
                { "label": "Milliseconds", "value": "milliseconds" }
            ]
            currentValue: root.nodeElapsedTimeUnitValue
            onPicked: function(value) {
                root.setNodeElapsedTimeUnit(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: commentEditorSubmenuLoader
        active: root.activeSubmenu === "commentEditor"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Comments"
            options: [
                { "label": "Canvas popover", "value": "canvas_popover" },
                { "label": "Inspector", "value": "inspector" }
            ]
            currentValue: root.nodeCommentEditorDefaultValue
            onPicked: function(value) {
                root.setNodeCommentEditorDefault(value);
                root.activeSubmenu = "";
            }
        }
    }

    Loader {
        id: shellSubmenuLoader
        active: root.activeSubmenu === "shell"
        x: root.submenuOffsetX
        y: 0
        sourceComponent: SubmenuPanel {
            title: "Shell theme"
            options: [
                { "label": "Dark", "value": "stitch_dark" },
                { "label": "Light", "value": "stitch_light" }
            ]
            currentValue: root.activeShellThemeId
            onPicked: function(value) {
                root.setShellTheme(value);
                root.activeSubmenu = "";
            }
        }
    }

    component MenuPanel: Item {
        property int panelWidth: 252
        property int panelHeight: 120

        width: panelWidth
        height: panelHeight + root.shadowDepth

        Rectangle {
            x: 0
            y: 10
            width: parent.panelWidth
            height: parent.panelHeight
            radius: 10
            color: Qt.alpha("#000000", 0.10)
        }

        Rectangle {
            x: 0
            y: 4
            width: parent.panelWidth
            height: parent.panelHeight
            radius: 9
            color: Qt.alpha("#000000", 0.06)
        }

        Rectangle {
            width: parent.panelWidth
            height: parent.panelHeight
            radius: 8
            color: root.panelBg
            border.width: 1
            border.color: Qt.alpha(root.borderColor, 0.92)

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                radius: parent.radius
                color: Qt.alpha("#ffffff", 0.35)
            }
        }
    }

    component SectionHeader: Item {
        property string label: ""
        width: parent ? parent.width : root.panelW - (root.contentPad * 2)
        height: 22

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: root.sectionFg
            font.pixelSize: 9
            font.bold: true
            font.letterSpacing: 1.2
            renderType: Text.CurveRendering
        }
    }

    component Divider: Rectangle {
        width: (parent ? parent.width : root.panelW - (root.contentPad * 2)) - 18
        x: 9
        height: 1
        color: Qt.alpha(root._token("border", "#3a3d45"), 0.55)
    }

    component ToggleRow: Item {
        property string label: ""
        property bool checked: false
        property bool dim: false
        property string tooltipText: ""
        property string tooltipCategory: "general"
        signal toggled()

        width: parent ? parent.width : root.panelW - (root.contentPad * 2)
        height: root.rowH
        opacity: dim ? 0.45 : 1.0

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 6
            color: toggleMouseArea.containsMouse && !parent.dim
                ? Qt.alpha(root.accentColor, 0.12)
                : "transparent"
        }

        Rectangle {
            visible: toggleMouseArea.containsMouse && !parent.dim
            x: 8
            y: 7
            width: 3
            height: root.rowH - 14
            radius: 2
            color: root.accentColor
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            width: 14
            text: parent.checked ? "\u2713" : ""
            color: root.accentColor
            font.pixelSize: 12
            font.bold: true
            renderType: Text.CurveRendering
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 34
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: root.titleFg
            font.pixelSize: 12
            font.bold: toggleMouseArea.containsMouse && !parent.dim
            elide: Text.ElideRight
            renderType: Text.CurveRendering
        }

        MouseArea {
            id: toggleMouseArea
            anchors.fill: parent
            hoverEnabled: true
            enabled: !parent.dim
            cursorShape: parent.dim ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: parent.toggled()
        }

        Common.ManagedToolTip {
            policyBridge: root.tooltipPolicyBridge
            category: parent.tooltipCategory
            active: toggleMouseArea.containsMouse && !parent.dim
            text: parent.tooltipText
            delay: 400
        }
    }

    component SubmenuRow: Item {
        property string label: ""
        property string value: ""
        property bool dim: false
        property bool isOpen: false
        property string tooltipText: ""
        property string tooltipCategory: "general"
        signal clicked()

        width: parent ? parent.width : root.panelW - (root.contentPad * 2)
        height: root.rowH
        opacity: dim ? 0.45 : 1.0

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 6
            color: (submenuMouseArea.containsMouse && !parent.dim) || parent.isOpen
                ? Qt.alpha(root.accentColor, 0.12)
                : "transparent"
        }

        Rectangle {
            visible: (submenuMouseArea.containsMouse && !parent.dim) || parent.isOpen
            x: 8
            y: 7
            width: 3
            height: root.rowH - 14
            radius: 2
            color: root.accentColor
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: root.titleFg
            font.pixelSize: 12
            font.bold: submenuMouseArea.containsMouse && !parent.dim
            elide: Text.ElideRight
            renderType: Text.CurveRendering
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Text {
                text: parent.parent.value
                color: root.mutedFg
                font.pixelSize: 11
                renderType: Text.CurveRendering
            }

            Text {
                text: "\u203a"
                color: root.mutedFg
                font.pixelSize: 14
                font.bold: true
                renderType: Text.CurveRendering
            }
        }

        MouseArea {
            id: submenuMouseArea
            anchors.fill: parent
            hoverEnabled: true
            enabled: !parent.dim
            cursorShape: parent.dim ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: parent.clicked()
        }

        Common.ManagedToolTip {
            policyBridge: root.tooltipPolicyBridge
            category: parent.tooltipCategory
            active: submenuMouseArea.containsMouse && !parent.dim
            text: parent.tooltipText
            delay: 400
        }
    }

    component ActionRow: Item {
        property string label: ""
        signal clicked()

        width: parent ? parent.width : root.panelW - (root.contentPad * 2)
        height: root.rowH

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 6
            color: actionMouseArea.containsMouse ? Qt.alpha(root.accentColor, 0.12) : "transparent"
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: root.accentColor
            font.pixelSize: 12
            font.italic: true
            font.bold: actionMouseArea.containsMouse
            elide: Text.ElideRight
            renderType: Text.CurveRendering
        }

        MouseArea {
            id: actionMouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }

    component SubmenuPanel: Item {
        id: submenuRoot
        property string title: ""
        property var options: []
        property string currentValue: ""
        signal picked(string value)

        width: submenuPanel.width
        height: submenuPanel.height

        MenuPanel {
            id: submenuPanel
            panelWidth: root.submenuW
            panelHeight: Math.min(submenuColumn.implicitHeight + root.contentPad * 2,
                                  root.availablePanelHeight)

            ScrollView {
                id: submenuScroll
                objectName: "canvasOptionsSubmenuScroll"
                x: root.contentPad
                y: root.contentPad
                width: submenuPanel.panelWidth - root.contentPad * 2
                height: Math.max(0, submenuPanel.panelHeight - root.contentPad * 2)
                contentWidth: availableWidth
                contentHeight: submenuColumn.implicitHeight
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical.policy: ScrollBar.AsNeeded

                Column {
                    id: submenuColumn
                    width: parent.width
                    spacing: 0

                    SectionHeader { label: submenuRoot.title.toUpperCase() }

                    Repeater {
                        model: submenuRoot.options

                        delegate: Item {
                            readonly property string optionLabel: String(modelData && modelData.label !== undefined ? modelData.label : "")
                            readonly property string optionValue: String(modelData && modelData.value !== undefined ? modelData.value : optionLabel)
                            readonly property bool isActive: optionValue === submenuRoot.currentValue

                            width: submenuColumn.width
                            height: root.rowH

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 2
                                radius: 6
                                color: submenuOptionMouseArea.containsMouse || parent.isActive
                                    ? Qt.alpha(root.accentColor, 0.14)
                                    : "transparent"
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 18
                                anchors.verticalCenter: parent.verticalCenter
                                width: 14
                                text: parent.isActive ? "\u2713" : ""
                                color: root.accentColor
                                font.pixelSize: 12
                                font.bold: true
                                renderType: Text.CurveRendering
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 34
                                anchors.right: parent.right
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: parent.optionLabel
                                color: root.titleFg
                                font.pixelSize: 12
                                font.bold: submenuOptionMouseArea.containsMouse || parent.isActive
                                elide: Text.ElideRight
                                renderType: Text.CurveRendering
                            }

                            MouseArea {
                                id: submenuOptionMouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: submenuRoot.picked(parent.optionValue)
                            }
                        }
                    }
                }
            }
        }
    }
}
