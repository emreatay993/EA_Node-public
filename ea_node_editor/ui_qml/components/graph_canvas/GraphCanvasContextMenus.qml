import QtQuick 2.15
import "../shell" as ShellComponents
import "../common/TooltipCopy.js" as TooltipCopy
import "../graph/GraphActionPresentation.js" as GraphActionPresentation

Item {
    id: root
    objectName: "graphCanvasContextMenus"
    property Item canvasItem: null
    property var canvasActionRouter: null
    property var commandBridge: null
    property var graphActionBridge: null
    property var addonManagerBridge: null
    property var helpBridge: null
    readonly property var shellContextRef: typeof shellContext !== "undefined" ? shellContext : null
    readonly property var themeBridgeRef: root.shellContextRef ? root.shellContextRef.themeBridge : null
    readonly property var viewBridgeRef: root.canvasItem ? root.canvasItem.canvasViewBridgeRef : null
    readonly property real viewCenterX: root.viewBridgeRef ? Number(root.viewBridgeRef.center_x) : 0.0
    readonly property real viewCenterY: root.viewBridgeRef ? Number(root.viewBridgeRef.center_y) : 0.0
    readonly property real viewZoom: root.viewBridgeRef ? Number(root.viewBridgeRef.zoom_value) : 1.0
    readonly property var addonManagerBridgeRef: root.shellContextRef
        ? root.shellContextRef.addonManagerBridge
        : root.addonManagerBridge
    readonly property var helpBridgeRef: root.shellContextRef
        ? root.shellContextRef.helpBridge
        : root.helpBridge
    property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property bool anyContextMenuVisible: root.canvasItem && (
        root.canvasItem.canvasOptionsVisible
        || root.canvasItem.edgeContextVisible
        || root.canvasItem.nodeContextVisible
        || root.canvasItem.selectionContextVisible
    )

    anchors.fill: parent
    z: 900
    visible: root.anyContextMenuVisible
    enabled: root.anyContextMenuVisible

    GraphCanvasActionRouter {
        id: fallbackActionRouter
        canvasItem: root.canvasItem
        graphActionBridge: root.graphActionBridge
        canvasCommandBridge: root.commandBridge
        addonManagerBridge: root.addonManagerBridgeRef
        helpBridge: root.helpBridgeRef
    }

    GraphCanvasOptionsMenu {
        id: canvasOptionsPopup
        objectName: "graphCanvasOptionsPopup"
        canvasItem: root.canvasItem
        commandBridge: root.commandBridge
        themePalette: root.themePalette
        visible: root.canvasItem ? root.canvasItem.canvasOptionsVisible : false
        anchorX: root._resolvedContextMenuAnchorX()
        anchorY: root._resolvedContextMenuAnchorY()
        x: root.canvasItem ? canvasOptionsPopup.resolvedX : 0
        y: root.canvasItem ? canvasOptionsPopup.resolvedY : 0
    }

    function _actionRouter() {
        return root.canvasActionRouter || fallbackActionRouter;
    }

    function _nodePayload(nodeId) {
        if (!root.canvasItem || !root.canvasItem._sceneNodePayload)
            return null;
        return root.canvasItem._sceneNodePayload(nodeId);
    }

    function _isParameterSetupPoolPayload(nodePayload) {
        var typeId = nodePayload ? String(nodePayload.type_id || "").trim() : "";
        return typeId === "optimization.parameter_pool"
            || typeId === "optimization.response_pool";
    }

    function _parameterSetupLinkActions(nodePayload, editable) {
        if (!editable || !root._isParameterSetupPoolPayload(nodePayload) || !root.canvasItem)
            return [];
        var nodeId = String(root.canvasItem.nodeContextNodeId || "").trim();
        var bridge = root.canvasItem.sceneCommandBridge;
        if (!nodeId.length || !bridge
                || !bridge.parameter_setup_link_status
                || !bridge.parameter_setup_link_options)
            return [];
        var status = bridge.parameter_setup_link_status(nodeId) || ({});
        if (Boolean(status.linked)) {
            return [{
                "actionId": "node_context::unlink_parameter_setup",
                "text": "Unlink from Parameter Setup",
                "visible": true
            }];
        }
        var options = bridge.parameter_setup_link_options(nodeId) || [];
        var actions = [];
        for (var index = 0; index < options.length; ++index) {
            var option = options[index] || ({});
            var setupNodeId = String(option.setup_node_id || "").trim();
            if (!setupNodeId.length)
                continue;
            var title = String(option.title || "Parameter Setup").trim();
            actions.push({
                "actionId": "node_context::link_parameter_setup::" + setupNodeId,
                "text": options.length > 1
                    ? "Link to Parameter Setup: " + title
                    : "Link to Parameter Setup",
                "visible": true
            });
        }
        return actions;
    }

    function _nodeReadOnly(nodeId) {
        var payload = root._nodePayload(nodeId);
        return !!payload && Boolean(payload.read_only);
    }

    function _settingsGroupActions(nodePayload, enabled) {
        var groups = nodePayload && nodePayload.settings_groups
            ? nodePayload.settings_groups
            : [];
        var actions = [];
        for (var index = 0; index < groups.length; ++index) {
            var group = groups[index] || ({});
            var groupId = String(group.group_id || "").trim();
            if (!groupId.length)
                continue;
            actions.push({
                "actionId": "node_context::settings_group::" + groupId,
                "text": String(group.label || groupId),
                "checked": Boolean(group.expanded),
                "enabled": Boolean(enabled)
            });
        }
        return actions;
    }

    function _dynamicPortGroupActions(nodePayload, editable) {
        var groups = nodePayload && nodePayload.dynamic_port_groups
            ? nodePayload.dynamic_port_groups
            : [];
        var actions = [];
        for (var index = 0; index < groups.length; ++index) {
            var group = groups[index] || ({});
            var groupId = String(group.id || "").trim();
            var direction = String(group.direction || "").trim().toLowerCase();
            if (!groupId.length || (direction !== "in" && direction !== "out"))
                continue;
            actions.push({
                "actionId": "node_context::dynamic_port_add::" + groupId,
                "text": direction === "in" ? "Add Input" : "Add Output",
                "enabled": Boolean(editable) && Boolean(group.can_insert)
            });
        }
        return actions;
    }

    function _triggerGraphAction(actionId, payload) {
        var actionRouter = root._actionRouter();
        if (actionRouter && actionRouter.triggerGraphAction)
            return Boolean(actionRouter.triggerGraphAction(actionId, payload || ({})));
        if (!root.graphActionBridge || !root.graphActionBridge.trigger_graph_action)
            return false;
        return Boolean(root.graphActionBridge.trigger_graph_action(actionId, payload || ({})));
    }

    function _handleEdgeDisplayModeAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "edge_display_mode_menu") {
            if (!edgeContextPopup.activeDataWire)
                return true;
            edgeContextPopup.displayModeSubmenuOpen = !edgeContextPopup.displayModeSubmenuOpen;
            return true;
        }
        var prefix = "edge_display_mode:";
        if (normalized.indexOf(prefix) !== 0)
            return false;
        var edgeId = root.canvasItem ? String(root.canvasItem.edgeContextEdgeId || "").trim() : "";
        var edgePayload = root.canvasItem && edgeId.length
            ? root.canvasItem._sceneEdgePayload(edgeId)
            : null;
        if (!edgePayload || !Boolean(edgePayload.active_data_wire))
            return true;
        var mode = GraphActionPresentation.normalizeEdgeDisplayMode(normalized.slice(prefix.length));
        var router = root._actionRouter();
        if (edgeId.length && router && router.setEdgesDisplayMode)
            router.setEdgesDisplayMode([edgeId], mode);
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _handleEdgeNavigationAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized !== "jump_edge_start" && normalized !== "jump_edge_end")
            return false;
        var edgeId = root.canvasItem ? String(root.canvasItem.edgeContextEdgeId || "").trim() : "";
        var router = root._actionRouter();
        if (edgeId.length && router && router.jumpToEdgeEndpoint)
            router.jumpToEdgeEndpoint(edgeId, normalized === "jump_edge_end" ? "target" : "source");
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _handleEdgePathAction(actionId) {
        var text = String(actionId || "");
        var prefix = "edge_path_mode:";
        if (text.indexOf(prefix) !== 0)
            return false;
        if (!root.canvasItem)
            return true;
        var edgeId = String(root.canvasItem.edgeContextEdgeId || "").trim();
        var actionRouter = root._actionRouter();
        var mode = GraphActionPresentation.normalizeEdgePathMode(text.slice(prefix.length));
        var handled = false;
        if (actionRouter && actionRouter.setEdgePathMode)
            handled = Boolean(actionRouter.setEdgePathMode(edgeId, mode));
        if (!handled && actionRouter !== fallbackActionRouter && fallbackActionRouter.setEdgePathMode)
            handled = Boolean(fallbackActionRouter.setEdgePathMode(edgeId, mode));
        if (handled)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _handleEdgeEnableAction(actionId) {
        if (String(actionId || "") !== "toggle_edge_enabled")
            return false;
        if (root.canvasItem && root.canvasItem.toggleSelectedEdgesEnabled)
            root.canvasItem.toggleSelectedEdgesEnabled(root.canvasItem.edgeContextEdgeId);
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _nodeActionId(key) {
        var actionRouter = root._actionRouter();
        return actionRouter && actionRouter.nodeContextActionId
            ? actionRouter.nodeContextActionId(key)
            : "";
    }

    function _handleNodeEditorAction(actionId) {
        var normalized = String(actionId || "");
        var nodeId = root.canvasItem ? String(root.canvasItem.nodeContextNodeId || "").trim() : "";
        var accepted = false;
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        var setupLinkPrefix = "node_context::link_parameter_setup::";
        if (normalized === "node_context::unlink_parameter_setup") {
            if (nodeId.length && bridge && bridge.unlink_parameter_setup)
                accepted = Boolean(bridge.unlink_parameter_setup(nodeId));
        } else if (normalized.indexOf(setupLinkPrefix) === 0) {
            var setupNodeId = normalized.substring(setupLinkPrefix.length).trim();
            if (nodeId.length && setupNodeId.length && bridge && bridge.link_parameter_setup)
                accepted = Boolean(bridge.link_parameter_setup(nodeId, setupNodeId));
        } else if (normalized === "node_context::add_link") {
            if (nodeId.length && root.canvasItem.requestAddNodeLinkForNode)
                accepted = Boolean(root.canvasItem.requestAddNodeLinkForNode(nodeId));
        } else if (normalized === "node_context::add_comment") {
            var payload = nodeId.length ? root._nodePayload(nodeId) : null;
            if (payload && root.canvasItem.openNodeCommentEditor)
                accepted = Boolean(root.canvasItem.openNodeCommentEditor(payload, true));
        } else {
            return false;
        }
        if (accepted && root.canvasItem._closeContextMenus)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _handleSettingsGroupAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "node_context::settings") {
            nodeContextPopup.settingsSubmenuOpen = !nodeContextPopup.settingsSubmenuOpen;
            return true;
        }
        var prefix = "node_context::settings_group::";
        if (normalized.indexOf(prefix) !== 0)
            return false;
        var groupId = normalized.substring(prefix.length);
        var nodeId = root.canvasItem
            ? String(root.canvasItem.nodeContextNodeId || "").trim()
            : "";
        var groups = nodeContextPopup.settingsGroups;
        var expanded = false;
        for (var index = 0; index < groups.length; ++index) {
            var group = groups[index] || ({});
            if (String(group.group_id || "") === groupId) {
                expanded = Boolean(group.expanded);
                break;
            }
        }
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        if (nodeContextPopup.settingsEditable
                && nodeId.length
                && groupId.length
                && bridge
                && bridge.set_node_settings_group_expanded) {
            bridge.set_node_settings_group_expanded(nodeId, groupId, !expanded);
        }
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function _handleDynamicPortAction(actionId) {
        var normalized = String(actionId || "");
        var prefix = "node_context::dynamic_port_add::";
        if (normalized.indexOf(prefix) !== 0)
            return false;
        var groupId = normalized.substring(prefix.length);
        var nodeId = root.canvasItem
            ? String(root.canvasItem.nodeContextNodeId || "").trim()
            : "";
        var group = null;
        var groups = nodeContextPopup.dynamicPortGroups;
        for (var index = 0; index < groups.length; ++index) {
            var candidate = groups[index] || ({});
            if (String(candidate.id || "").trim() === groupId) {
                group = candidate;
                break;
            }
        }
        var bridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
        if (nodeContextPopup.dynamicPortsEditable
                && group
                && Boolean(group.can_insert)
                && nodeId.length
                && bridge
                && bridge.insert_dynamic_port) {
            var portKeys = group.port_keys || [];
            var newPortKey = String(
                bridge.insert_dynamic_port(nodeId, groupId, portKeys.length) || ""
            );
            if (newPortKey.length > 0 && root.canvasItem && root.canvasItem._closeContextMenus)
                root.canvasItem._closeContextMenus();
        }
        return true;
    }

    function _handlePanelContextAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized !== "panel_edit"
                && normalized !== "panel_copy"
                && normalized !== "panel_copy_tree")
            return false;
        if (nodeContextPopup.isPanelNode && root.canvasItem) {
            var nodeId = String(root.canvasItem.nodeContextNodeId || "").trim();
            var host = nodeId.length && root.canvasItem.hostForNodeId
                ? root.canvasItem.hostForNodeId(nodeId)
                : null;
            if (host && host.dispatchSurfaceAction)
                host.dispatchSurfaceAction(normalized);
            root.canvasItem._closeContextMenus();
        }
        return true;
    }

    function _selectionActionId(key) {
        var actionRouter = root._actionRouter();
        return actionRouter && actionRouter.selectionContextActionId
            ? actionRouter.selectionContextActionId(key)
            : "";
    }

    function _hasContextMenuSceneAnchor() {
        return root.canvasItem
            && root.canvasItem.contextMenuSceneAnchorActive
            && isFinite(Number(root.canvasItem.contextMenuSceneAnchorX))
            && isFinite(Number(root.canvasItem.contextMenuSceneAnchorY));
    }

    function _contextMenuSceneAnchorScreenX() {
        var zoom = Math.max(0.1, root.viewZoom);
        var viewportWidth = root.canvasItem ? Number(root.canvasItem.width) : 0.0;
        return viewportWidth * 0.5
            + (Number(root.canvasItem.contextMenuSceneAnchorX) - root.viewCenterX) * zoom;
    }

    function _contextMenuSceneAnchorScreenY() {
        var zoom = Math.max(0.1, root.viewZoom);
        var viewportHeight = root.canvasItem ? Number(root.canvasItem.height) : 0.0;
        return viewportHeight * 0.5
            + (Number(root.canvasItem.contextMenuSceneAnchorY) - root.viewCenterY) * zoom;
    }

    function _resolvedContextMenuAnchorX() {
        if (root._hasContextMenuSceneAnchor())
            return root._contextMenuSceneAnchorScreenX();
        return root.canvasItem ? root.canvasItem.contextMenuX : 0;
    }

    function _resolvedContextMenuAnchorY() {
        if (root._hasContextMenuSceneAnchor())
            return root._contextMenuSceneAnchorScreenY();
        return root.canvasItem ? root.canvasItem.contextMenuY : 0;
    }

    ShellComponents.ShellContextMenu {
        id: edgeContextPopup
        objectName: "graphCanvasEdgeContextPopup"
        tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
        visible: root.canvasItem ? root.canvasItem.edgeContextVisible : false
        x: root._resolvedContextMenuAnchorX()
        y: root._resolvedContextMenuAnchorY()
        minimumWidth: 198
        rowHeight: 30
        contentPadding: 4
        readonly property var edgePayload: {
            var revision = root.canvasItem ? Number(root.canvasItem.edgeTopologyRevision || 0) : 0;
            void(revision);
            return root.canvasItem
                ? root.canvasItem._liveEdgePayload(root.canvasItem.edgeContextEdgeId)
                : null;
        }
        readonly property bool isFlowEdge: edgePayload
            ? String(edgePayload.edge_family || "").toLowerCase() === "flow"
            : false
        readonly property bool activeDataWire: Boolean(edgePayload && edgePayload.active_data_wire)
        property bool displayModeSubmenuOpen: false
        onVisibleChanged: {
            if (!visible)
                displayModeSubmenuOpen = false;
        }
        actions: GraphActionPresentation.edgeContextMenuActions([
            {
                "actionId": "toggle_edge_enabled",
                "text": "Enabled",
                "checked": root.canvasItem && root.canvasItem.edgeSelectionAllEnabled
                    ? root.canvasItem.edgeSelectionAllEnabled(root.canvasItem.edgeContextEdgeId)
                    : Boolean(edgeContextPopup.edgePayload && edgeContextPopup.edgePayload.enabled !== false),
                "shortcutText": "Ctrl+E"
            },
            { "actionId": "edge_display_mode_menu", "text": "Display Mode", "shortcutText": "\u203a", "visible": edgeContextPopup.activeDataWire },
            { "actionId": "jump_edge_start", "text": "Jump to Start", "shortcutText": "Ctrl+Left" },
            { "actionId": "jump_edge_end", "text": "Jump to End", "shortcutText": "Ctrl+Right" }
        ],
            GraphActionPresentation.normalizeEdgePathMode(
                edgeContextPopup.edgePayload && edgeContextPopup.edgePayload.visual_style
                    ? edgeContextPopup.edgePayload.visual_style.path_mode
                    : "auto"
            ),
            {
                "actionId": root._actionRouter() && root._actionRouter().edgeContextActionId
                    ? root._actionRouter().edgeContextActionId("remove_edge")
                    : "",
                "text": "Remove Connection",
                "destructive": true
            }
        )
        onActionTriggered: function(actionId) {
            if (root._handleEdgeDisplayModeAction(actionId))
                return;
            if (root._handleEdgeNavigationAction(actionId))
                return;
            if (root._handleEdgeEnableAction(actionId))
                return;
            if (root._handleEdgePathAction(actionId))
                return;
            var actionRouter = root._actionRouter();
            if (actionRouter && actionRouter.handleEdgeContextAction)
                actionRouter.handleEdgeContextAction(actionId)
        }
    }

    ShellComponents.ShellContextMenu {
        id: edgeDisplayModeContextPopup
        objectName: "graphCanvasEdgeDisplayModeContextPopup"
        tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
        readonly property bool opensLeft: root.canvasItem
            && edgeContextPopup.x + edgeContextPopup.panelWidth + 6
                + edgeDisplayModeContextPopup.panelWidth > root.canvasItem.width - 4
        visible: edgeContextPopup.visible
            && edgeContextPopup.activeDataWire
            && edgeContextPopup.displayModeSubmenuOpen
        x: edgeDisplayModeContextPopup.opensLeft
            ? edgeContextPopup.x - edgeDisplayModeContextPopup.panelWidth - 6
            : edgeContextPopup.x + edgeContextPopup.panelWidth + 6
        y: edgeContextPopup.y
        minimumWidth: 150
        rowHeight: 30
        contentPadding: 4
        actions: GraphActionPresentation.edgeDisplayMenuActions(
            GraphActionPresentation.commonEdgeDisplayMode([
                edgeContextPopup.edgePayload || ({})
            ])
        )
        onActionTriggered: function(actionId) {
            root._handleEdgeDisplayModeAction(actionId);
        }
    }

    ShellComponents.ShellContextMenu {
        id: nodeContextPopup
        objectName: "graphCanvasNodeContextPopup"
        tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
        visible: root.canvasItem ? root.canvasItem.nodeContextVisible : false
        x: root._resolvedContextMenuAnchorX()
        y: root._resolvedContextMenuAnchorY()
        minimumWidth: nodeContextPopup.isReadOnlyNode ? 210 : 188
        rowHeight: 30
        contentPadding: 4
        property bool canEnterScope: root.canvasItem
            ? root.canvasItem._nodeCanEnterScope(root.canvasItem.nodeContextNodeId)
            : false
        readonly property bool isReadOnlyNode: root.canvasItem
            ? root._nodeReadOnly(root.canvasItem.nodeContextNodeId)
            : false
        readonly property bool isPassiveNode: root.canvasItem
            ? root.canvasItem._nodeSupportsPassiveStyle(root.canvasItem.nodeContextNodeId)
            : false
        readonly property bool isRunnableNode: {
            if (nodeContextPopup.isReadOnlyNode || !root.canvasItem)
                return false;
            var payload = root._nodePayload(root.canvasItem.nodeContextNodeId);
            return !!payload && String(payload.runtime_behavior || "action").toLowerCase() !== "passive";
        }
        readonly property var nodePayload: root.canvasItem
            ? root._nodePayload(root.canvasItem.nodeContextNodeId)
            : null
        readonly property var settingsGroups: nodeContextPopup.nodePayload
            && nodeContextPopup.nodePayload.settings_groups
            ? nodeContextPopup.nodePayload.settings_groups
            : []
        readonly property bool settingsEditable: !nodeContextPopup.isReadOnlyNode
            && nodeContextPopup.nodePayload
            && !Boolean(nodeContextPopup.nodePayload.locked)
        readonly property var dynamicPortGroups: nodeContextPopup.nodePayload
            && nodeContextPopup.nodePayload.dynamic_port_groups
            ? nodeContextPopup.nodePayload.dynamic_port_groups
            : []
        readonly property bool dynamicPortsEditable: {
            if (nodeContextPopup.isReadOnlyNode || !nodeContextPopup.nodePayload)
                return false;
            var lockedState = nodeContextPopup.nodePayload.locked_state || ({});
            return !Boolean(nodeContextPopup.nodePayload.locked)
                && !Boolean(lockedState.locked)
                && !Boolean(lockedState.read_only);
        }
        property bool settingsSubmenuOpen: false
        onVisibleChanged: {
            if (!visible)
                settingsSubmenuOpen = false;
        }
        readonly property bool canPeekComment: root._actionRouter().nodeCanPeekInside(root.canvasItem ? root.canvasItem.nodeContextNodeId : "")
        readonly property bool isPeekedComment: root.canvasItem
            ? root._actionRouter().activeCommentPeekNodeId() === String(root.canvasItem.nodeContextNodeId || "").trim()
            : false
        readonly property bool canOpenAddonManager: nodeContextPopup.isReadOnlyNode
            && root._actionRouter().canOpenAddonManagerForNode(root.canvasItem ? root.canvasItem.nodeContextNodeId : "")
        readonly property bool canShowHelp: {
            if (!root.canvasItem)
                return false;
            var nodeId = String(root.canvasItem.nodeContextNodeId || "").trim();
            if (!nodeId.length)
                return false;
            return Boolean(root._actionRouter().canShowHelpForNode(nodeId));
        }
        readonly property bool isViewerNode: nodeContextPopup.nodePayload
            ? String(nodeContextPopup.nodePayload.surface_family || "") === "viewer"
            : false
        readonly property bool isPanelNode: nodeContextPopup.nodePayload
            ? String(nodeContextPopup.nodePayload.type_id || "") === "data.panel"
            : false
        readonly property string viewerBackground: {
            if (!nodeContextPopup.nodePayload)
                return "theme";
            var properties = nodeContextPopup.nodePayload.properties || ({});
            return String(properties.viewer_background || "theme").toLowerCase();
        }
        function _viewerBackgroundEntry(value, label) {
            return {
                "actionId": "viewer_context::background::" + value,
                "text": (nodeContextPopup.viewerBackground === value ? "● " : "") + "Background: " + label,
                "visible": nodeContextPopup.isViewerNode && !nodeContextPopup.isReadOnlyNode
            };
        }
        actions: [
            { "actionId": "viewer_context::open_fullscreen", "text": "Open Fullscreen", "visible": nodeContextPopup.isViewerNode },
            nodeContextPopup._viewerBackgroundEntry("theme", "Theme"),
            nodeContextPopup._viewerBackgroundEntry("white", "White"),
            nodeContextPopup._viewerBackgroundEntry("black", "Black"),
            nodeContextPopup._viewerBackgroundEntry("gray", "Gray"),
            { "actionId": "panel_edit", "text": "Edit values and interpretation...", "visible": nodeContextPopup.isPanelNode && !nodeContextPopup.isReadOnlyNode },
            { "actionId": "panel_copy", "text": "Copy", "visible": nodeContextPopup.isPanelNode },
            { "actionId": "panel_copy_tree", "text": "Copy as tree", "visible": nodeContextPopup.isPanelNode },
            { "actionId": root._nodeActionId("run_selected"), "text": "Run Selected", "visible": nodeContextPopup.isRunnableNode },
            { "actionId": root._nodeActionId("preview_selected_run"), "text": "Preview Run", "visible": nodeContextPopup.isRunnableNode },
            { "actionId": root._nodeActionId("open_selected_run_settings"), "text": "Run Settings...", "visible": nodeContextPopup.isRunnableNode },
            {
                "actionId": "node_context::settings",
                "text": "Settings",
                "shortcutText": "\u203a",
                "visible": nodeContextPopup.settingsEditable
                    && nodeContextPopup.settingsGroups.length > 0
            }
        ].concat(root._dynamicPortGroupActions(
            nodeContextPopup.nodePayload,
            nodeContextPopup.dynamicPortsEditable
        )).concat(root._parameterSetupLinkActions(
            nodeContextPopup.nodePayload,
            !nodeContextPopup.isReadOnlyNode
                && !Boolean(nodeContextPopup.nodePayload && nodeContextPopup.nodePayload.locked)
        )).concat([
            { "actionId": "node_context::add_link", "text": "Add Link", "visible": !nodeContextPopup.isReadOnlyNode },
            { "actionId": "node_context::add_comment", "text": "Add Comment", "visible": !nodeContextPopup.isReadOnlyNode },
            { "actionId": root._nodeActionId("open_addon_manager_for_node"), "text": "Open Add-On Manager", "visible": nodeContextPopup.canOpenAddonManager },
            { "actionId": root._nodeActionId("open_subnode_scope"), "text": "Enter Subnode", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.canEnterScope },
            { "actionId": root._nodeActionId("publish_custom_workflow_from_node"), "text": "Add to Workflows", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.canEnterScope },
            { "actionId": root._nodeActionId("open_comment_peek"), "text": "Peek Inside", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.canPeekComment },
            { "actionId": root._nodeActionId("close_comment_peek"), "text": "Exit Peek", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPeekedComment },
            { "actionId": root._nodeActionId("edit_passive_node_style"), "text": "Edit Style...", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPassiveNode },
            { "actionId": root._nodeActionId("reset_passive_node_style"), "text": "Reset Style", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPassiveNode },
            { "actionId": root._nodeActionId("copy_passive_node_style"), "text": "Copy Style", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPassiveNode },
            { "actionId": root._nodeActionId("paste_passive_node_style"), "text": "Paste Style", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPassiveNode },
            { "actionId": root._nodeActionId("propagate_passive_node_style"), "text": "Propagate Style", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.isPassiveNode },
            { "actionId": root._nodeActionId("rename_node"), "text": "Rename Node", "visible": !nodeContextPopup.isReadOnlyNode },
            { "actionId": root._nodeActionId("show_node_help"), "text": "Help", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.canShowHelp },
            { "actionId": root._nodeActionId("ungroup_node"), "text": "Ungroup Subnode", "visible": !nodeContextPopup.isReadOnlyNode && nodeContextPopup.canEnterScope, "destructive": true },
            { "actionId": root._nodeActionId("remove_node"), "text": "Remove Node", "visible": !nodeContextPopup.isReadOnlyNode, "destructive": true }
        ])
        onActionTriggered: function(actionId) {
            if (root._handleSettingsGroupAction(actionId))
                return;
            if (root._handleDynamicPortAction(actionId))
                return;
            if (root._handlePanelContextAction(actionId))
                return;
            if (root._handleNodeEditorAction(actionId))
                return;
            if (root._handleViewerContextAction(actionId))
                return;
            var actionRouter = root._actionRouter();
            if (actionRouter && actionRouter.handleNodeContextAction)
                actionRouter.handleNodeContextAction(actionId)
        }
    }

    ShellComponents.ShellContextMenu {
        id: settingsContextPopup
        objectName: "graphCanvasNodeSettingsContextPopup"
        tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
        readonly property bool opensLeft: root.canvasItem
            && nodeContextPopup.x + nodeContextPopup.panelWidth + 6
                + settingsContextPopup.panelWidth > root.canvasItem.width - 4
        visible: nodeContextPopup.visible
            && nodeContextPopup.settingsSubmenuOpen
            && settingsContextPopup.actions.length > 0
        x: settingsContextPopup.opensLeft
            ? nodeContextPopup.x - settingsContextPopup.panelWidth - 6
            : nodeContextPopup.x + nodeContextPopup.panelWidth + 6
        y: nodeContextPopup.y
        minimumWidth: 188
        rowHeight: 30
        contentPadding: 4
        actions: root._settingsGroupActions(
            nodeContextPopup.nodePayload,
            nodeContextPopup.settingsEditable
        )
        onActionTriggered: function(actionId) {
            root._handleSettingsGroupAction(actionId);
        }
    }

    function _handleViewerContextAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized.indexOf("viewer_context::") !== 0)
            return false;
        var nodeId = root.canvasItem ? String(root.canvasItem.nodeContextNodeId || "").trim() : "";
        if (nodeId.length) {
            if (normalized === "viewer_context::open_fullscreen") {
                var fullscreenBridge = typeof contentFullscreenBridge !== "undefined" ? contentFullscreenBridge : null;
                if (fullscreenBridge && fullscreenBridge.request_open_node)
                    fullscreenBridge.request_open_node(nodeId);
            } else if (normalized.indexOf("viewer_context::background::") === 0) {
                var backgroundValue = normalized.substring("viewer_context::background::".length);
                var sceneBridge = root.canvasItem ? root.canvasItem.sceneCommandBridge : null;
                if (sceneBridge && sceneBridge.set_node_property)
                    sceneBridge.set_node_property(nodeId, "viewer_background", backgroundValue);
                // The scene-bridge path fires no shell mutation effects for
                // unselected nodes; the session sync is idempotent otherwise.
                var sessionBridge = typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge : null;
                if (sessionBridge && sessionBridge.sync_node_property_option)
                    sessionBridge.sync_node_property_option(nodeId, "viewer_background", backgroundValue);
            }
        }
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    ShellComponents.ShellContextMenu {
        id: selectionContextPopup
        objectName: "graphCanvasSelectionContextPopup"
        tooltipPolicyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
        visible: root.canvasItem ? root.canvasItem.selectionContextVisible : false
        x: selectionContextPopup._resolvedAnchorX()
        y: selectionContextPopup._resolvedAnchorY()
        minimumWidth: 242
        rowHeight: 30
        contentPadding: 4
        readonly property var selectedNodeIds: root.canvasItem && root.canvasItem.selectedNodeIds
            ? root.canvasItem.selectedNodeIds()
            : []
        readonly property int selectedNodeCount: selectionContextPopup.selectedNodeIds.length
        readonly property bool hasMultiNodeSelection: selectionContextPopup.selectedNodeCount > 1
        readonly property bool canAlignSelection: selectionContextPopup.selectedNodeCount >= 2
        readonly property bool canDistributeSelection: selectionContextPopup.selectedNodeCount >= 3
        readonly property bool canWrapSelection: selectionContextPopup.selectedNodeCount >= 2
        readonly property bool canStraightenConnections: selectionContextPopup._hasInternalConnection()
        readonly property bool canSetSameTypeWidth: selectionContextPopup._hasSameTypeBucketForDimension("width")
        readonly property bool canSetSameTypeHeight: selectionContextPopup._hasSameTypeBucketForDimension("height")
        readonly property var _viewBridge: root.canvasItem ? root.canvasItem.canvasViewBridgeRef : null
        readonly property real _viewCenterX: selectionContextPopup._viewBridge ? Number(selectionContextPopup._viewBridge.center_x) : 0.0
        readonly property real _viewCenterY: selectionContextPopup._viewBridge ? Number(selectionContextPopup._viewBridge.center_y) : 0.0
        readonly property real _viewZoom: selectionContextPopup._viewBridge ? Number(selectionContextPopup._viewBridge.zoom_value) : 1.0
        function _hasSceneAnchor() {
            return root.canvasItem
                && root.canvasItem.selectionContextSceneAnchorActive
                && isFinite(Number(root.canvasItem.selectionContextSceneAnchorX))
                && isFinite(Number(root.canvasItem.selectionContextSceneAnchorY));
        }
        function _sceneAnchorScreenX() {
            var zoom = Math.max(0.1, selectionContextPopup._viewZoom);
            var viewportWidth = root.canvasItem ? Number(root.canvasItem.width) : 0.0;
            return viewportWidth * 0.5
                + (Number(root.canvasItem.selectionContextSceneAnchorX) - selectionContextPopup._viewCenterX) * zoom;
        }
        function _sceneAnchorScreenY() {
            var zoom = Math.max(0.1, selectionContextPopup._viewZoom);
            var viewportHeight = root.canvasItem ? Number(root.canvasItem.height) : 0.0;
            return viewportHeight * 0.5
                + (Number(root.canvasItem.selectionContextSceneAnchorY) - selectionContextPopup._viewCenterY) * zoom;
        }
        function _resolvedAnchorX() {
            if (root._hasContextMenuSceneAnchor())
                return root._contextMenuSceneAnchorScreenX();
            if (selectionContextPopup._hasSceneAnchor())
                return selectionContextPopup._sceneAnchorScreenX();
            return root.canvasItem ? root.canvasItem.contextMenuX : 0;
        }
        function _resolvedAnchorY() {
            if (root._hasContextMenuSceneAnchor())
                return root._contextMenuSceneAnchorScreenY();
            if (selectionContextPopup._hasSceneAnchor())
                return selectionContextPopup._sceneAnchorScreenY();
            return root.canvasItem ? root.canvasItem.contextMenuY : 0;
        }
        function _selectedNodeLookup() {
            var lookup = {};
            var selected = selectionContextPopup.selectedNodeIds || [];
            for (var i = 0; i < selected.length; ++i) {
                var nodeId = String(selected[i] || "").trim();
                if (nodeId.length)
                    lookup[nodeId] = true;
            }
            return lookup;
        }
        function _hasSameTypeBucketForDimension(dimension) {
            if (selectionContextPopup.selectedNodeCount < 2)
                return false;
            var bucketCounts = {};
            var selected = selectionContextPopup.selectedNodeIds || [];
            for (var i = 0; i < selected.length; ++i) {
                var nodeId = String(selected[i] || "").trim();
                if (!nodeId.length)
                    continue;
                var payload = root._nodePayload(nodeId);
                if (!payload)
                    continue;
                if (String(payload.runtime_behavior || "").trim().toLowerCase() !== "passive")
                    continue;
                var typeId = String(payload.type_id || "").trim();
                if (!typeId.length)
                    continue;
                var value = Number(payload[dimension]);
                if (!isFinite(value) || value <= 0)
                    continue;
                bucketCounts[typeId] = Number(bucketCounts[typeId] || 0) + 1;
                if (bucketCounts[typeId] >= 2)
                    return true;
            }
            return false;
        }
        function _edgePayload(edgeId) {
            if (!root.canvasItem || !root.canvasItem._sceneEdgePayload)
                return null;
            return root.canvasItem._sceneEdgePayload(String(edgeId || "").trim());
        }
        function _edgeConnectsSelectedNodes(edge, selectedLookup) {
            if (!edge)
                return false;
            var sourceNodeId = String(edge.source_node_id || "").trim();
            var targetNodeId = String(edge.target_node_id || "").trim();
            return sourceNodeId.length > 0
                && targetNodeId.length > 0
                && Boolean(selectedLookup[sourceNodeId])
                && Boolean(selectedLookup[targetNodeId]);
        }
        function _hasInternalConnection() {
            if (!root.canvasItem || selectionContextPopup.selectedNodeCount < 2)
                return false;
            var selectedLookup = selectionContextPopup._selectedNodeLookup();
            var selectedEdges = root.canvasItem.selectedEdgeIds || [];
            for (var selectedIndex = 0; selectedIndex < selectedEdges.length; ++selectedIndex) {
                if (selectionContextPopup._edgeConnectsSelectedNodes(
                        selectionContextPopup._edgePayload(selectedEdges[selectedIndex]),
                        selectedLookup
                    )) {
                    return true;
                }
            }
            var edges = root.canvasItem.edgePayload || [];
            for (var edgeIndex = 0; edgeIndex < edges.length; ++edgeIndex) {
                if (selectionContextPopup._edgeConnectsSelectedNodes(edges[edgeIndex], selectedLookup))
                    return true;
            }
            return false;
        }
        actions: [
            { "actionId": root._selectionActionId("run_selected"), "text": "Run Selected", "visible": selectionContextPopup.selectedNodeCount > 0 },
            { "actionId": root._selectionActionId("preview_selected_run"), "text": "Preview Run", "visible": selectionContextPopup.selectedNodeCount > 0 },
            { "actionId": root._selectionActionId("align_selection_left"), "text": "Align Left", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canAlignSelection },
            { "actionId": root._selectionActionId("align_selection_right"), "text": "Align Right", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canAlignSelection },
            { "actionId": root._selectionActionId("align_selection_top"), "text": "Align Top", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canAlignSelection },
            { "actionId": root._selectionActionId("align_selection_bottom"), "text": "Align Bottom", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canAlignSelection },
            { "actionId": root._selectionActionId("distribute_selection_horizontally"), "text": "Distribute Horizontally", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canDistributeSelection },
            { "actionId": root._selectionActionId("distribute_selection_vertically"), "text": "Distribute Vertically", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canDistributeSelection },
            { "actionId": root._selectionActionId("set_selection_same_type_width"), "text": "Set Same Width", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canSetSameTypeWidth },
            { "actionId": root._selectionActionId("set_selection_same_type_height"), "text": "Set Same Height", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canSetSameTypeHeight },
            { "actionId": root._selectionActionId("straighten_selection_connections"), "text": "Straighten Connections", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canStraightenConnections },
            { "actionId": root._selectionActionId("wrap_selection_in_group_backdrop"), "text": "Wrap into Group", "visible": selectionContextPopup.hasMultiNodeSelection, "enabled": selectionContextPopup.canWrapSelection }
        ]
        onActionTriggered: function(actionId) {
            var actionRouter = root._actionRouter();
            if (actionRouter && actionRouter.handleSelectionContextAction)
                actionRouter.handleSelectionContextAction(actionId)
        }
    }
}
