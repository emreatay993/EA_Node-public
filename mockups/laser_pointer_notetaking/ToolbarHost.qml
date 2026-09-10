import QtQuick
import "ToolbarToolCatalog.js" as ToolCatalog

Item {
    id: root

    property string activeTool: "laser"
    property string activePanelKind: "laser"
    readonly property bool laserActive: activeTool === "laser"
    property string statusText: "Laser pointer active. Drag on the notes to draw."
    property int toolbarScalePercent: 100
    readonly property real toolbarScale: toolbarScalePercent / 100.0

    property alias fadeValue: controls.fadeValue
    property alias idleValue: controls.idleValue
    property alias minValue: controls.minValue
    property alias coreValue: controls.coreValue
    property alias redValue: controls.redValue
    property alias glowValue: controls.glowValue
    property alias dotValue: controls.dotValue
    property alias lineMode: controls.lineMode
    property alias holdToDraw: controls.holdToDraw
    property alias fadeOnReleaseOnly: controls.fadeOnReleaseOnly
    property alias highQuality: controls.highQuality
    property alias softGlow: controls.softGlow
    property alias darkBackground: controls.darkBackground

    property real settingsAnchorX: -1
    property string toolBeforeToolbarSettings: "laser"
    property string panelBeforeToolbarSettings: "laser"

    signal toolModeChanged(string toolId, string panelKind, bool shouldClearTrail)
    signal laserFocusRequested()

    function toolLabel(toolId) {
        return ToolCatalog.labelFor(toolId);
    }

    function closeLaserSubmenu() {
        if (root.activePanelKind === "laser")
            root.activePanelKind = "";
    }

    function activateTool(toolId, panelKind) {
        var id = String(toolId || "");
        var panel = String(panelKind || "");
        if (id === "more") {
            if (root.activePanelKind === "more") {
                root.closeToolbarSettings();
                return;
            }
            root.toolBeforeToolbarSettings = root.activeTool;
            root.panelBeforeToolbarSettings = root.activePanelKind;
            root.activeTool = id;
            root.activePanelKind = panel;
            root.statusText = "Toolbar settings active.";
            root.toolModeChanged(id, panel, false);
            return;
        }

        root.activeTool = id;
        root.activePanelKind = panel;
        if (id === "laser") {
            root.statusText = "Laser pointer active. Drag on the notes to draw.";
            root.laserFocusRequested();
            root.toolModeChanged(id, panel, false);
            return;
        }
        if (panel === "writingTools") {
            root.statusText = "Writing Tools active. Pick a drawing preset in the floating toolbar.";
            root.toolModeChanged(id, panel, true);
            return;
        }
        if (panel === "erase") {
            root.statusText = "Eraser active. Pick eraser type and size in the floating toolbar.";
            root.toolModeChanged(id, panel, true);
            return;
        }
        root.statusText = root.toolLabel(id) + " toolbar slot is present; laser is the only wired tool.";
        root.toolModeChanged(id, panel, true);
    }

    function closeToolbarSettings() {
        if (root.activePanelKind !== "more")
            return;
        var id = String(root.toolBeforeToolbarSettings || "laser");
        var panel = String(root.panelBeforeToolbarSettings || "laser");
        root.activeTool = id;
        root.activePanelKind = panel;
        if (id === "laser") {
            root.statusText = "Laser pointer active. Drag on the notes to draw.";
            root.laserFocusRequested();
        } else if (panel === "writingTools") {
            root.statusText = "Writing Tools active. Pick a drawing preset in the floating toolbar.";
        } else if (panel === "erase") {
            root.statusText = "Eraser active. Pick eraser type and size in the floating toolbar.";
        } else if (panel.length > 0) {
            root.statusText = root.toolLabel(id) + " toolbar slot is present; laser is the only wired tool.";
        }
        root.toolModeChanged(id, panel, false);
    }

    // Reproducible states for --shot captures: --pen-popover opens the pen
    // options flyout (optionally preset to a style), --pen-gestures lands on
    // its second page.
    Component.onCompleted: {
        var args = Qt.application.arguments;
        if (args.indexOf("--pen-popover") === -1 && args.indexOf("--pen-gestures") === -1)
            return;
        root.activateTool("pen", "writingTools");
        if (args.indexOf("--pen-variant-ball") !== -1)
            writingToolsToolbar.setPenVariant("ball");
        else if (args.indexOf("--pen-variant-brush") !== -1)
            writingToolsToolbar.setPenVariant("brush");
        writingToolsToolbar.togglePenPopover();
        if (args.indexOf("--pen-gestures") !== -1)
            writingToolsToolbar.openPenGesturesPage();
    }

    LaserPointerToolbar {
        id: toolBar
        z: 2
        anchors.top: parent.top
        anchors.topMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 56, implicitWidth)
        height: implicitHeight
        activeTool: root.activeTool
        toolbarScale: root.toolbarScale
        onToolTriggered: function(toolId, panelKind) {
            root.activateTool(toolId, panelKind);
        }
    }

    MouseArea {
        id: toolbarSettingsDismissArea
        z: 1
        anchors.fill: parent
        visible: root.activePanelKind === "more"
        acceptedButtons: Qt.LeftButton
        onClicked: root.closeToolbarSettings()
    }

    Item {
        id: toolbarSettingsKeyTrap
        z: 1
        anchors.fill: parent
        visible: root.activePanelKind === "more"
        focus: visible
        onVisibleChanged: if (visible) forceActiveFocus()
        Keys.onEscapePressed: function(event) {
            root.closeToolbarSettings();
            event.accepted = true;
        }
    }

    MouseArea {
        id: penPopoverDismissArea
        z: 1
        anchors.fill: parent
        visible: root.activePanelKind === "writingTools" && writingToolsToolbar.penPopoverOpen
        acceptedButtons: Qt.LeftButton
        onClicked: writingToolsToolbar.closePenPopover()
    }

    Item {
        id: penPopoverKeyTrap
        z: 1
        anchors.fill: parent
        visible: penPopoverDismissArea.visible
        focus: visible
        onVisibleChanged: if (visible) forceActiveFocus()
        Keys.onEscapePressed: function(event) {
            writingToolsToolbar.closePenPopover();
            event.accepted = true;
        }
    }

    MouseArea {
        id: colorPanelDismissArea
        z: 1
        anchors.fill: parent
        visible: root.activePanelKind === "writingTools" && writingToolsToolbar.colorPanelOpen
        acceptedButtons: Qt.LeftButton
        onClicked: writingToolsToolbar.closeColorPanel()
    }

    Item {
        id: colorPanelKeyTrap
        z: 1
        anchors.fill: parent
        visible: colorPanelDismissArea.visible
        focus: visible
        onVisibleChanged: if (visible) forceActiveFocus()
        Keys.onEscapePressed: function(event) {
            writingToolsToolbar.closeColorPanel();
            event.accepted = true;
        }
    }

    WritingToolsFloatingToolbar {
        id: writingToolsToolbar
        z: 5
        property real placementHalfWidth: 0
        width: Math.min(root.width - 36, implicitWidth)
        visible: root.activePanelKind === "writingTools"
        toolbarScale: root.toolbarScale
        maxColorPanelHeight: root.height - y - 12
        hostWidth: root.width
        readonly property real anchorX: toolBar.x + toolBar.activeToolCenterX
        x: Math.max(18, Math.min(root.width - width - 18, anchorX - placementHalfWidth))
        y: toolBar.y + toolBar.height + 10
        onVisibleChanged: {
            if (visible) {
                placementHalfWidth = width / 2;
            } else {
                writingToolsToolbar.closePenPopover();
                writingToolsToolbar.closeColorPanel();
            }
        }
        onOptionChanged: function(summary) {
            root.statusText = summary + " (prototype UI only).";
        }
    }

    EraserFloatingToolbar {
        id: eraserToolbar
        z: 5
        visible: root.activePanelKind === "erase"
        toolbarScale: root.toolbarScale
        readonly property real anchorX: toolBar.x + toolBar.activeToolCenterX
        x: Math.max(18, Math.min(root.width - width - 18, anchorX - width / 2))
        y: toolBar.y + toolBar.height + 10
        viewportLeft: 12 - x
        viewportRight: root.width - 12 - x
        onOptionChanged: function(summary) {
            root.statusText = summary + " (prototype UI only).";
        }
    }

    ToolContextPanel {
        id: contextPanel
        z: 3
        anchors.top: toolBar.bottom
        anchors.topMargin: 10
        anchors.horizontalCenter: toolBar.horizontalCenter
        visible: root.activeTool !== "laser"
            && root.activePanelKind.length > 0
            && root.activePanelKind !== "writingTools"
            && root.activePanelKind !== "erase"
            && root.activePanelKind !== "more"
        toolId: root.activeTool
        panelKind: root.activePanelKind
        toolLabel: root.toolLabel(root.activeTool)
        darkBackground: root.darkBackground
        onContextActionTriggered: function(toolId, actionId) {
            root.statusText = root.toolLabel(toolId) + ": " + ToolCatalog.contextActionLabel(actionId);
        }
    }

    ToolbarSettingsPanel {
        id: toolbarSettingsPanel
        z: 4
        visible: root.activePanelKind === "more"
        toolbarScalePercent: root.toolbarScalePercent
        readonly property real liveAnchorX: toolBar.x + toolBar.activeToolCenterX
        readonly property real anchorX: root.settingsAnchorX >= 0 ? root.settingsAnchorX : liveAnchorX
        x: Math.max(12, Math.min(root.width - width - 12, anchorX - width / 2))
        y: toolBar.y + toolBar.height + 8
        caretX: anchorX - x
        onVisibleChanged: {
            if (visible) {
                root.settingsAnchorX = liveAnchorX;
                Qt.callLater(function() {
                    if (toolbarSettingsPanel.visible)
                        root.settingsAnchorX = toolbarSettingsPanel.liveAnchorX;
                });
            } else {
                root.settingsAnchorX = -1;
            }
        }
        onToolbarScaleRequested: function(value) {
            root.toolbarScalePercent = Math.max(75, Math.min(125, Math.round(value)));
        }
    }

    LaserSubmenu {
        id: controls
        z: 6
        width: 560
        visible: root.activeTool === "laser" && root.activePanelKind === "laser"
        readonly property real anchorX: toolBar.x + toolBar.laserCenterX
        x: Math.max(12, Math.min(root.width - width - 12, anchorX - width / 2))
        y: toolBar.y + toolBar.height + 8
        caretX: anchorX - x
        maxHeight: root.height - y - 16
        statusText: root.statusText
    }
}
