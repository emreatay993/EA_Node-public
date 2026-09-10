import QtQml 2.15
import "../graph/GraphActionPresentation.js" as GraphActionPresentation

QtObject {
    id: root
    property var canvasItem: null
    property var graphActionBridge: null
    property var canvasCommandBridge: null
    property var addonManagerBridge: null
    property var helpBridge: null
    property var contentFullscreenBridge: null
    property var shellLibraryBridge: null
    property var viewerSessionBridge: null

    readonly property var keyActionDescriptors: ({
        "deleteSelection": { "actionId": "delete_selection" },
        "navigateScopeParent": { "actionId": "navigate_scope_parent" },
        "navigateScopeRoot": { "actionId": "navigate_scope_root" },
        "closeCommentPeek": { "actionId": "close_comment_peek" }
    })

    readonly property var nodeDelegateActionDescriptors: ({
        "run_selected": { "actionId": "run_selected", "payload": "node" },
        "preview_selected_run": { "actionId": "preview_selected_run", "payload": "node" },
        "open_selected_run_settings": { "actionId": "open_selected_run_settings", "payload": "none" },
        "open_subnode_scope": { "actionId": "open_subnode_scope", "payload": "node" },
        "rename_node": { "actionId": "rename_node", "payload": "node", "inlineTitleEdit": true },
        "remove_node": { "actionId": "remove_node", "payload": "node", "clearEdgeSelection": true },
        "duplicate_node": { "actionId": "duplicate_node", "payload": "node" },
        "open_node_path": { "actionId": "open_node_path", "payload": "node" },
        "open_node_path_with": { "actionId": "open_node_path_with", "payload": "node" }
    })

    readonly property var edgeContextActionDescriptors: ({
        "edit_flow_edge_style": { "actionId": "edit_flow_edge_style", "payload": "edge" },
        "edit_flow_edge_label": { "actionId": "edit_flow_edge_label", "payload": "edge" },
        "reset_flow_edge_style": { "actionId": "reset_flow_edge_style", "payload": "edge" },
        "copy_flow_edge_style": { "actionId": "copy_flow_edge_style", "payload": "edge" },
        "paste_flow_edge_style": { "actionId": "paste_flow_edge_style", "payload": "edge" },
        "remove_edge": { "actionId": "remove_edge", "payload": "edge", "clearEdgeSelection": true }
    })

    readonly property var nodeContextActionDescriptors: ({
        "run_selected": { "actionId": "run_selected", "payload": "node" },
        "preview_selected_run": { "actionId": "preview_selected_run", "payload": "node" },
        "open_selected_run_settings": { "actionId": "open_selected_run_settings", "payload": "none" },
        "open_addon_manager_for_node": { "actionId": "open_addon_manager_for_node", "payload": "node", "requiresSuccess": true },
        "open_subnode_scope": { "actionId": "open_subnode_scope", "payload": "node", "requiresSuccess": true },
        "publish_custom_workflow_from_node": { "actionId": "publish_custom_workflow_from_node", "payload": "node" },
        "open_comment_peek": { "actionId": "open_comment_peek", "payload": "node", "requiresSuccess": true },
        "close_comment_peek": { "actionId": "close_comment_peek", "payload": "none", "requiresSuccess": true },
        "edit_passive_node_style": { "actionId": "edit_passive_node_style", "payload": "node" },
        "reset_passive_node_style": { "actionId": "reset_passive_node_style", "payload": "node" },
        "copy_passive_node_style": { "actionId": "copy_passive_node_style", "payload": "node" },
        "paste_passive_node_style": { "actionId": "paste_passive_node_style", "payload": "node" },
        "propagate_passive_node_style": { "actionId": "propagate_passive_node_style", "payload": "node" },
        "rename_node": {
            "actionId": "rename_node",
            "payload": "node",
            "inlineTitleEdit": true,
            "requiresSuccess": true
        },
        "show_node_help": { "actionId": "show_node_help", "payload": "node" },
        "ungroup_node": { "actionId": "ungroup_node", "payload": "node" },
        "remove_node": { "actionId": "remove_node", "payload": "node", "clearEdgeSelection": true }
    })

    readonly property var selectionContextActionDescriptors: ({
        "run_selected": { "actionId": "run_selected", "payload": "selection" },
        "preview_selected_run": { "actionId": "preview_selected_run", "payload": "selection" },
        "open_selected_run_settings": { "actionId": "open_selected_run_settings", "payload": "none" },
        "align_selection_left": { "actionId": "align_selection_left", "payload": "none" },
        "align_selection_right": { "actionId": "align_selection_right", "payload": "none" },
        "align_selection_top": { "actionId": "align_selection_top", "payload": "none" },
        "align_selection_bottom": { "actionId": "align_selection_bottom", "payload": "none" },
        "distribute_selection_horizontally": { "actionId": "distribute_selection_horizontally", "payload": "none" },
        "distribute_selection_vertically": { "actionId": "distribute_selection_vertically", "payload": "none" },
        "set_selection_same_type_width": { "actionId": "set_selection_same_type_width", "payload": "selection" },
        "set_selection_same_type_height": { "actionId": "set_selection_same_type_height", "payload": "selection" },
        "straighten_selection_connections": { "actionId": "straighten_selection_connections", "payload": "none" },
        "wrap_selection_in_group_backdrop": { "actionId": "wrap_selection_in_group_backdrop", "payload": "none" }
    })

    readonly property var folderExplorerActionDescriptors: ({
        "folder_explorer_list": { "actionId": "folder_explorer_list" },
        "folder_explorer_navigate": { "actionId": "folder_explorer_navigate" },
        "folder_explorer_refresh": { "actionId": "folder_explorer_refresh" },
        "folder_explorer_set_sort": { "actionId": "folder_explorer_set_sort" },
        "folder_explorer_set_search": { "actionId": "folder_explorer_set_search" },
        "folder_explorer_open": { "actionId": "folder_explorer_open" },
        "folder_explorer_open_with": { "actionId": "folder_explorer_open_with" },
        "folder_explorer_open_in_new_window": { "actionId": "folder_explorer_open_in_new_window" },
        "folder_explorer_new_folder": { "actionId": "folder_explorer_new_folder" },
        "folder_explorer_rename": { "actionId": "folder_explorer_rename" },
        "folder_explorer_delete": { "actionId": "folder_explorer_delete" },
        "folder_explorer_cut": { "actionId": "folder_explorer_cut" },
        "folder_explorer_copy": { "actionId": "folder_explorer_copy" },
        "folder_explorer_paste": { "actionId": "folder_explorer_paste" },
        "folder_explorer_copy_path": { "actionId": "folder_explorer_copy_path" },
        "folder_explorer_properties": { "actionId": "folder_explorer_properties" },
        "folder_explorer_send_to_corex_path_pointer": { "actionId": "folder_explorer_send_to_corex_path_pointer" }
    })

    function descriptorActionId(descriptors, key) {
        return GraphActionPresentation.descriptorActionId(descriptors, key);
    }

    function edgeContextActionId(key) {
        return descriptorActionId(root.edgeContextActionDescriptors, key);
    }

    function nodeContextActionId(key) {
        return descriptorActionId(root.nodeContextActionDescriptors, key);
    }

    function selectionContextActionId(key) {
        return descriptorActionId(root.selectionContextActionDescriptors, key);
    }

    function folderExplorerActionId(key) {
        return descriptorActionId(root.folderExplorerActionDescriptors, key);
    }

    function _graphActionBridge() {
        return root.graphActionBridge;
    }

    function triggerGraphAction(actionId, payload) {
        var bridge = root._graphActionBridge();
        if (!bridge || !bridge.trigger_graph_action)
            return false;
        return Boolean(bridge.trigger_graph_action(String(actionId || ""), payload || ({})));
    }

    function _finishInlineRename(actionId, nodeId, inlineEditStarted) {
        if (inlineEditStarted)
            return true;
        return root.triggerGraphAction(actionId, { "node_id": String(nodeId || "") });
    }

    function _canvasCommandBridge() {
        return root.canvasCommandBridge;
    }

    function requestFolderExplorerAction(actionId, payload) {
        var bridge = root._canvasCommandBridge();
        if (!bridge || !bridge.request_folder_explorer_action) {
            return {
                "success": false,
                "cancelled": false,
                "action_id": String(actionId || ""),
                "node_id": String((payload || ({})).node_id || ""),
                "path": String((payload || ({})).path || ""),
                "error": {
                    "code": "bridge_unavailable",
                    "message": "Folder explorer command bridge is not available.",
                    "operation": String(actionId || ""),
                    "path": String((payload || ({})).path || ""),
                    "target_path": ""
                }
            };
        }
        return bridge.request_folder_explorer_action(String(actionId || ""), payload || ({}));
    }

    function handleFolderExplorerAction(actionId, payload) {
        var result = root.requestFolderExplorerAction(actionId, payload || ({}));
        return Boolean(result && result.success);
    }

    function _nodePayload(nodeId) {
        if (!root.canvasItem || !root.canvasItem._sceneNodePayload)
            return null;
        return root.canvasItem._sceneNodePayload(String(nodeId || "").trim());
    }

    function _intValue(value, defaultValue) {
        var numeric = Number(value);
        return isFinite(numeric) ? Math.floor(numeric) : Number(defaultValue || 0);
    }

    function _mediaPanelSource(nodeId) {
        var facts = root.canvasItem && root.canvasItem.executionFacts
            ? root.canvasItem.executionFacts
            : null;
        var lookup = facts && facts.mediaPanelSourceLookup
            ? facts.mediaPanelSourceLookup
            : ({});
        return lookup[String(nodeId || "").trim()] || ({});
    }

    function _isReadyPdfMediaPayload(payload, nodeId) {
        var source = root._mediaPanelSource(nodeId);
        return !!payload
            && String(payload.type_id || "") === "media.panel"
            && String(source.state || "") === "ready"
            && String(source.media_kind || "") === "pdf";
    }

    function nodeReadOnly(nodeId) {
        var payload = root._nodePayload(nodeId);
        return !!payload && Boolean(payload.read_only);
    }

    function _nodeLockedState(nodeId) {
        var payload = root._nodePayload(nodeId);
        if (!payload || !payload.locked_state)
            return ({});
        return payload.locked_state;
    }

    function nodeAddonFocusId(nodeId) {
        var payload = root._nodePayload(nodeId);
        if (!payload)
            return "";
        var lockedState = root._nodeLockedState(nodeId);
        return String(lockedState.focus_addon_id || payload.addon_id || "").trim();
    }

    function addonManagerAvailable() {
        return root.addonManagerBridge && root.addonManagerBridge.requestOpen;
    }

    function canOpenAddonManagerForNode(nodeId) {
        return root.addonManagerAvailable() && root.nodeAddonFocusId(nodeId).length > 0;
    }

    function activeCommentPeekNodeId() {
        var bridge = root._canvasCommandBridge();
        if (!bridge || !bridge.active_comment_peek_node_id)
            return "";
        return String(bridge.active_comment_peek_node_id() || "").trim();
    }

    function _isCollapsedGroupBackdrop(payload) {
        return !!payload
            && String(payload.surface_family || "").trim() === "group_backdrop"
            && Boolean(payload.collapsed);
    }

    function nodeCanPeekInside(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized || root.activeCommentPeekNodeId() === normalized)
            return false;
        if (!root._isCollapsedGroupBackdrop(root._nodePayload(normalized)))
            return false;
        var bridge = root._canvasCommandBridge();
        if (bridge && bridge.can_open_comment_peek)
            return Boolean(bridge.can_open_comment_peek(normalized));
        return true;
    }

    function canShowHelpForNode(nodeId) {
        if (!root.helpBridge || !root.helpBridge.can_show_help_for_node || !root.canvasItem)
            return false;
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        return Boolean(root.helpBridge.can_show_help_for_node(normalized));
    }

    function _payloadForDescriptor(descriptor, actionId) {
        if (!descriptor)
            return null;
        var payloadKind = String(descriptor.payload || "none");
        if (payloadKind === "none")
            return ({});
        if (!root.canvasItem)
            return null;
        if (payloadKind === "edge") {
            var edgeId = String(root.canvasItem.edgeContextEdgeId || "").trim();
            return edgeId.length ? { "edge_id": edgeId } : null;
        }
        if (payloadKind === "node") {
            var nodeId = String(root.canvasItem.nodeContextNodeId || "").trim();
            if (!nodeId.length)
                return null;
            var payload = { "node_id": nodeId };
            if (descriptor.inlineTitleEdit)
                payload.inline_title_edit = true;
            return payload;
        }
        if (payloadKind === "selection") {
            if (!root.canvasItem.selectedNodeIds)
                return { "node_ids": [] };
            return { "node_ids": root.canvasItem.selectedNodeIds() || [] };
        }
        return null;
    }

    function _edgePayloadForId(edgeId) {
        var normalized = String(edgeId || "").trim();
        return normalized.length ? { "edge_id": normalized } : null;
    }

    function _edgePayload(edgeId) {
        if (!root.canvasItem || !root.canvasItem._sceneEdgePayload)
            return null;
        return root.canvasItem._sceneEdgePayload(String(edgeId || "").trim());
    }

    function edgeSupportsFlowStyle(edgeId) {
        if (root.canvasItem && root.canvasItem._edgeSupportsFlowStyle)
            return Boolean(root.canvasItem._edgeSupportsFlowStyle(edgeId));
        var payload = root._edgePayload(edgeId);
        return !!payload && String(payload.edge_family || "").toLowerCase() === "flow";
    }

    function _copyFlowEdgeStyle(edgeId) {
        var payload = root._edgePayload(edgeId) || ({});
        var source = payload.flow_style || payload.visual_style || ({});
        return root._copyEdgeStylePayload(source);
    }

    function _copyEdgeVisualStyle(edgeId) {
        var payload = root._edgePayload(edgeId) || ({});
        return root._copyEdgeStylePayload(payload.visual_style || ({}));
    }

    function _copyEdgeStylePayload(source) {
        var copy = {};
        for (var key in source) {
            if (Object.prototype.hasOwnProperty.call(source, key))
                copy[key] = source[key];
        }
        return copy;
    }

    function _sceneCommandBridge() {
        return root.canvasItem && root.canvasItem.sceneCommandBridge
            ? root.canvasItem.sceneCommandBridge
            : null;
    }

    function setFlowEdgeVisualStyle(edgeId, updates) {
        var normalized = String(edgeId || "").trim();
        if (!normalized.length || !root.edgeSupportsFlowStyle(normalized))
            return false;
        var bridge = root._sceneCommandBridge();
        if (!bridge || !bridge.set_edge_visual_style)
            return false;
        var next = root._copyFlowEdgeStyle(normalized);
        var patch = updates || ({});
        for (var key in patch) {
            if (!Object.prototype.hasOwnProperty.call(patch, key))
                continue;
            var value = patch[key];
            if (value === undefined || value === null || value === "")
                delete next[key];
            else
                next[key] = value;
        }
        var accepted = bridge.set_edge_visual_style(normalized, next);
        if (accepted === false)
            return false;
        if (root.canvasItem && root.canvasItem.requestEdgeRedraw)
            root.canvasItem.requestEdgeRedraw();
        return true;
    }

    function setEdgePathMode(edgeId, pathMode) {
        var normalized = String(edgeId || "").trim();
        if (!normalized.length)
            return false;
        var bridge = root._sceneCommandBridge();
        if (!bridge || !bridge.set_edge_visual_style)
            return false;
        var next = root._copyEdgeVisualStyle(normalized);
        var mode = GraphActionPresentation.normalizeEdgePathMode(pathMode);
        if (mode === "auto")
            delete next.path_mode;
        else
            next.path_mode = mode;
        var accepted = bridge.set_edge_visual_style(normalized, next);
        if (accepted === false)
            return false;
        if (root.canvasItem && root.canvasItem.requestEdgeRedraw)
            root.canvasItem.requestEdgeRedraw();
        return true;
    }

    function setEdgesDisplayMode(edgeIds, mode) {
        return root.canvasItem && root.canvasItem.setEdgesDisplayMode
            ? Boolean(root.canvasItem.setEdgesDisplayMode(edgeIds || [], mode))
            : false;
    }

    function jumpToEdgeEndpoint(edgeId, endpoint) {
        var normalized = String(edgeId || "").trim();
        return normalized.length > 0 && root.canvasItem && root.canvasItem.jumpToEdgeEndpoint
            ? Boolean(root.canvasItem.jumpToEdgeEndpoint(normalized, endpoint))
            : false;
    }

    function jumpToSelectedEdgeEndpoint(endpoint) {
        if (!root.canvasItem)
            return false;
        var selected = root.canvasItem._normalizeEdgeIds
            ? root.canvasItem._normalizeEdgeIds(root.canvasItem.selectedEdgeIds || [])
            : (root.canvasItem.selectedEdgeIds || []);
        return selected.length === 1
            ? root.jumpToEdgeEndpoint(selected[0], endpoint)
            : false;
    }

    function clearFlowEdgeLabel(edgeId) {
        var normalized = String(edgeId || "").trim();
        if (!normalized.length || !root.edgeSupportsFlowStyle(normalized))
            return false;
        var bridge = root._sceneCommandBridge();
        if (!bridge || !bridge.clear_edge_label)
            return false;
        var accepted = bridge.clear_edge_label(normalized);
        if (accepted === false)
            return false;
        if (root.canvasItem && root.canvasItem.requestEdgeRedraw)
            root.canvasItem.requestEdgeRedraw();
        return true;
    }

    function handleEdgeToolbarAction(actionId, edgeId) {
        var descriptor = GraphActionPresentation.descriptorForActionId(root.edgeContextActionDescriptors, actionId);
        if (!descriptor)
            return false;
        var payload = root._edgePayloadForId(edgeId);
        if (!payload)
            return false;
        var handled = root.triggerGraphAction(actionId, payload);
        if (!handled)
            return false;
        if (descriptor.clearEdgeSelection && root.canvasItem) {
            root.canvasItem.selectedEdgeIds = root.canvasItem.selectedEdgeIds.filter(function(value) {
                return value !== payload.edge_id;
            });
        }
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function handleEdgeContextAction(actionId) {
        var descriptor = GraphActionPresentation.descriptorForActionId(root.edgeContextActionDescriptors, actionId);
        var payload = root._payloadForDescriptor(descriptor, actionId);
        if (!payload)
            return false;
        root.triggerGraphAction(actionId, payload);
        if (descriptor.clearEdgeSelection && root.canvasItem) {
            root.canvasItem.selectedEdgeIds = root.canvasItem.selectedEdgeIds.filter(function(value) {
                return value !== payload.edge_id;
            });
        }
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function handleNodeContextAction(actionId) {
        var descriptor = GraphActionPresentation.descriptorForActionId(root.nodeContextActionDescriptors, actionId);
        var payload = root._payloadForDescriptor(descriptor, actionId);
        if (!descriptor || payload === null)
            return false;
        var handled = root.triggerGraphAction(actionId, payload);
        if (descriptor.requiresSuccess && !handled)
            return false;
        if (descriptor.inlineTitleEdit && root.canvasItem) {
            var renameTargetId = root.canvasItem.nodeContextNodeId;
            root.canvasItem._closeContextMenus();
            var inlineEditStarted = false;
            if (root.canvasItem.requestInlineRenameForNode)
                inlineEditStarted = Boolean(root.canvasItem.requestInlineRenameForNode(renameTargetId));
            return root._finishInlineRename(actionId, renameTargetId, inlineEditStarted);
        }
        if (descriptor.clearEdgeSelection && root.canvasItem)
            root.canvasItem.clearEdgeSelection();
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function handleSelectionContextAction(actionId) {
        var descriptor = GraphActionPresentation.descriptorForActionId(root.selectionContextActionDescriptors, actionId);
        var payload = root._payloadForDescriptor(descriptor, actionId);
        if (!descriptor || payload === null)
            return false;
        root.triggerGraphAction(actionId, payload);
        if (root.canvasItem)
            root.canvasItem._closeContextMenus();
        return true;
    }

    function handleNodeDelegateAction(nodeHost, nodeId, actionId) {
        var normalized = String(actionId || "").trim();
        if (!normalized)
            return false;
        if (normalized === "toggle_node_lock") {
            var sceneBridge = root._sceneCommandBridge();
            if (!sceneBridge || !sceneBridge.set_node_locked || !nodeHost)
                return false;
            return Boolean(sceneBridge.set_node_locked(String(nodeId || ""), !Boolean(nodeHost.authorLocked)));
        }
        if (normalized === "toggle_node_collapsed") {
            var collapseBridge = root._sceneCommandBridge();
            if (!collapseBridge || !collapseBridge.set_node_collapsed || !nodeHost)
                return false;
            return Boolean(collapseBridge.set_node_collapsed(String(nodeId || ""), !Boolean(nodeHost.isCollapsed)));
        }
        var descriptor = GraphActionPresentation.descriptorForActionId(root.nodeDelegateActionDescriptors, normalized);
        if (!descriptor) {
            if (nodeHost && nodeHost.dispatchSurfaceAction)
                return Boolean(nodeHost.dispatchSurfaceAction(normalized));
            return false;
        }
        var payload = { "node_id": String(nodeId || "") };
        if (descriptor.inlineTitleEdit)
            payload.inline_title_edit = true;
        var handled = root.triggerGraphAction(descriptor.actionId, payload);
        if (!handled)
            return false;
        if (descriptor.inlineTitleEdit) {
            var inlineEditStarted = nodeHost && nodeHost.beginInlineTitleEdit
                ? Boolean(nodeHost.beginInlineTitleEdit())
                : false;
            return root._finishInlineRename(descriptor.actionId, nodeId, inlineEditStarted);
        }
        if (descriptor.clearEdgeSelection && root.canvasItem)
            root.canvasItem.clearEdgeSelection();
        return true;
    }

    function closeCommentPeekIfActive() {
        if (root.triggerGraphAction(root.keyActionDescriptors.closeCommentPeek.actionId, ({})))
            return true;
        var bridge = root._canvasCommandBridge();
        if (!bridge || !bridge.request_close_comment_peek)
            return false;
        return Boolean(bridge.request_close_comment_peek());
    }

    function deleteSelection(edgeIds) {
        var handled = root.triggerGraphAction(
            root.keyActionDescriptors.deleteSelection.actionId,
            { "edge_ids": edgeIds || [] }
        );
        if (handled)
            return true;
        var bridge = root._canvasCommandBridge();
        if (bridge && bridge.request_delete_selected_graph_items)
            return Boolean(bridge.request_delete_selected_graph_items(edgeIds || []));
        return false;
    }

    function navigateScopeParent() {
        var handled = root.triggerGraphAction(root.keyActionDescriptors.navigateScopeParent.actionId, ({}));
        if (handled)
            return true;
        var bridge = root._canvasCommandBridge();
        return bridge && bridge.request_navigate_scope_parent
            ? Boolean(bridge.request_navigate_scope_parent())
            : false;
    }

    function navigateScopeRoot() {
        var handled = root.triggerGraphAction(root.keyActionDescriptors.navigateScopeRoot.actionId, ({}));
        if (handled)
            return true;
        var bridge = root._canvasCommandBridge();
        return bridge && bridge.request_navigate_scope_root
            ? Boolean(bridge.request_navigate_scope_root())
            : false;
    }

    function clearViewerFocus() {
        if (!root.viewerSessionBridge || !root.viewerSessionBridge.clear_viewer_focus)
            return false;
        root.viewerSessionBridge.clear_viewer_focus();
        return true;
    }

    function _showContentFullscreenHint(message) {
        var normalized = String(message || "Select one media or viewer node for fullscreen.").trim();
        if (!normalized.length)
            normalized = "Select one media or viewer node for fullscreen.";
        if (root.shellLibraryBridge && root.shellLibraryBridge.show_graph_hint) {
            root.shellLibraryBridge.show_graph_hint(normalized, 2400);
            return true;
        }
        return false;
    }

    function _selectedContentFullscreenNodeId() {
        if (!root.canvasItem || !root.canvasItem.selectedNodeIds)
            return "";
        var selected = root.canvasItem.selectedNodeIds() || [];
        if (selected.length !== 1)
            return "";
        return String(selected[0] || "").trim();
    }

    function navigateSelectedPdfPage(delta) {
        var nodeId = root._selectedContentFullscreenNodeId();
        if (!nodeId.length || root.nodeReadOnly(nodeId))
            return false;
        var payload = root._nodePayload(nodeId);
        if (!root._isReadyPdfMediaPayload(payload, nodeId))
            return false;
        var properties = payload.properties || ({});
        var sourceResolution = root._mediaPanelSource(nodeId);
        var sourcePath = String(
            sourceResolution.resolved_source_url
            || sourceResolution.source_ref
            || ""
        );
        if (!sourcePath.length || !root.canvasItem || !root.canvasItem.describeNodeSurfacePdfPreview)
            return false;
        var currentPropertyPage = root._intValue(properties.page_number, 1);
        var previewInfo = root.canvasItem.describeNodeSurfacePdfPreview(sourcePath, currentPropertyPage) || ({});
        var pageCount = root._intValue(previewInfo.page_count, 0);
        if (pageCount <= 0)
            return false;
        var currentPage = root._intValue(previewInfo.resolved_page_number, currentPropertyPage);
        currentPage = Math.max(1, Math.min(pageCount, currentPage));
        var targetPage = Math.max(1, Math.min(pageCount, currentPage + root._intValue(delta, 0)));
        if (targetPage === currentPage)
            return true;
        if (!root.canvasItem.commitNodeSurfaceProperty(nodeId, "page_number", targetPage))
            return false;
        if (root.canvasItem.forceActiveFocus)
            root.canvasItem.forceActiveFocus();
        return true;
    }

    function handleContentFullscreenShortcut() {
        var bridge = root.contentFullscreenBridge;
        if (!bridge)
            return false;
        if (Boolean(bridge.open)) {
            if (bridge.request_close)
                bridge.request_close();
            return true;
        }
        var nodeId = root._selectedContentFullscreenNodeId();
        if (!nodeId.length) {
            root._showContentFullscreenHint("Select one media or viewer node for fullscreen.");
            return true;
        }
        if (bridge.can_open_node && !bridge.can_open_node(nodeId)) {
            if (bridge.request_open_node)
                bridge.request_open_node(nodeId);
            root._showContentFullscreenHint(
                bridge.last_error || "The selected node does not support content fullscreen."
            );
            return true;
        }
        if (bridge.request_open_node && bridge.request_open_node(nodeId))
            return true;
        root._showContentFullscreenHint(
            bridge.last_error || "The selected node does not support content fullscreen."
        );
        return true;
    }
}
