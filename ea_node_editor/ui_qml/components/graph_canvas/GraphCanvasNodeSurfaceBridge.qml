import QtQuick 2.15

Item {
    id: root
    property var canvasItem: null
    visible: false
    width: 0
    height: 0

    GraphCanvasSurfaceInteractionHost {
        id: hostInteraction
        canvasItem: root.canvasItem
    }

    function _sceneSelectionBridge() {
        return hostInteraction.sceneSelectionBridge();
    }

    function _pendingActionBridge() {
        return hostInteraction.pendingActionBridge();
    }

    function _propertyBridge() {
        return hostInteraction.propertyBridge();
    }

    function _cursorBridge() {
        return hostInteraction.cursorBridge();
    }

    function _pdfPreviewBridge() {
        return hostInteraction.pdfPreviewBridge();
    }

    function _imagePreviewBridge() {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (bridge && bridge.describe_image_preview)
            return bridge;
        return null;
    }

    function _mailPreviewBridge() {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (bridge && bridge.describe_mail_preview)
            return bridge;
        return null;
    }

    function _tabularPreviewBridge() {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (bridge && bridge.describe_tabular_preview)
            return bridge;
        return null;
    }

    function _folderExplorerActionRouter() {
        if (!root.canvasItem || !root.canvasItem.canvasActionRouter)
            return null;
        return root.canvasItem.canvasActionRouter;
    }

    function _folderExplorerActionId(command) {
        var router = root._folderExplorerActionRouter();
        var normalized = String(command || "").trim();
        if (!router || !router.folderExplorerActionId)
            return normalized;
        var routed = String(router.folderExplorerActionId(normalized) || "").trim();
        return routed.length ? routed : normalized;
    }

    function _sceneNodePayload(nodeId) {
        if (!root.canvasItem || !root.canvasItem._sceneNodePayload)
            return null;
        return root.canvasItem._sceneNodePayload(String(nodeId || "").trim());
    }

    function _nodeReadOnly(nodeId) {
        var payload = root._sceneNodePayload(nodeId);
        return !!payload && Boolean(payload.read_only);
    }

    function requestOpenSubnodeScope(nodeId) {
        if (!root.canvasItem)
            return false;
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        if (root._nodeReadOnly(normalized))
            return false;
        var actionRouter = root.canvasItem.canvasActionRouter;
        var opened = actionRouter && actionRouter.triggerGraphAction
            ? actionRouter.triggerGraphAction("open_subnode_scope", { "node_id": normalized })
            : false;
        if (!opened) {
            var bridge = root.canvasItem.canvasCommandBridgeRef;
            opened = bridge && bridge.request_open_subnode_scope
                ? bridge.request_open_subnode_scope(normalized)
                : false;
        }
        if (!opened)
            return false;
        hostInteraction.clearCanvasSelectionState();
        return true;
    }

    function prepareNodeSurfaceControlInteraction(nodeId) {
        if (!root.canvasItem)
            return false;
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        hostInteraction.resetSurfaceInteractionState();
        return true;
    }

    function commitNodeSurfaceProperty(nodeId, key, value) {
        if (!root.canvasItem)
            return false;
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedKey = String(key || "").trim();
        if (!normalizedNodeId || !normalizedKey)
            return false;
        if (root._nodeReadOnly(normalizedNodeId))
            return false;
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        var bridge = root.canvasItem.sceneCommandBridge;
        if (!bridge || !bridge.set_node_property)
            return false;
        bridge.set_node_property(normalizedNodeId, normalizedKey, value);
        return true;
    }

    function commitNodePortLabel(nodeId, portKey, label) {
        if (!root.canvasItem)
            return false;
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedPortKey = String(portKey || "").trim();
        if (!normalizedNodeId || !normalizedPortKey)
            return false;
        if (root._nodeReadOnly(normalizedNodeId))
            return false;
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        var bridge = root.canvasItem.sceneCommandBridge;
        if (!bridge || !bridge.set_node_port_label)
            return false;
        bridge.set_node_port_label(normalizedNodeId, normalizedPortKey, String(label || ""));
        return true;
    }

    function requestNodeSurfaceCropEdit(nodeId) {
        if (!root.canvasItem)
            return false;
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        if (root._nodeReadOnly(normalized))
            return false;
        var selectionBridge = root._sceneSelectionBridge();
        var needsSelection = hostInteraction.selectedNodeIds().indexOf(normalized) < 0;
        if (needsSelection) {
            var pendingBridge = root._pendingActionBridge();
            if (!selectionBridge || !pendingBridge)
                return false;
            hostInteraction.resetSurfaceInteractionState();
            pendingBridge.set_pending_surface_action(normalized);
            selectionBridge.select_node(normalized, false);
            return false;
        }
        root.prepareNodeSurfaceControlInteraction(normalized);
        return true;
    }

    function consumePendingNodeSurfaceAction(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        var bridge = root._pendingActionBridge();
        if (!bridge)
            return false;
        return Boolean(bridge.consume_pending_surface_action(normalized));
    }

    function commitNodeSurfaceProperties(nodeId, properties) {
        if (!root.canvasItem)
            return false;
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        if (root._nodeReadOnly(normalized))
            return false;
        root.prepareNodeSurfaceControlInteraction(normalized);
        var bridge = root._propertyBridge();
        if (bridge)
            return Boolean(bridge.set_node_properties(normalized, properties || ({})));
        bridge = root.canvasItem.sceneCommandBridge;
        if (!bridge || !bridge.set_node_property)
            return false;
        var changed = false;
        var payload = properties || ({});
        for (var key in payload) {
            if (!Object.prototype.hasOwnProperty.call(payload, key))
                continue;
            bridge.set_node_property(normalized, key, payload[key]);
            changed = true;
        }
        return changed;
    }

    function setNodeSurfaceCursorShape(cursorShape) {
        var bridge = root._cursorBridge();
        if (!bridge)
            return false;
        bridge.set_graph_cursor_shape(cursorShape);
        return true;
    }

    function clearNodeSurfaceCursorShape() {
        var bridge = root._cursorBridge();
        if (!bridge)
            return false;
        bridge.clear_graph_cursor_shape();
        return true;
    }

    function describeNodeSurfacePdfPreview(source, pageNumber) {
        var bridge = root._pdfPreviewBridge();
        if (!bridge)
            return ({});
        return bridge.describe_pdf_preview(String(source || ""), pageNumber);
    }

    function describeNodeSurfaceImagePreview(source) {
        var bridge = root._imagePreviewBridge();
        if (!bridge)
            return ({});
        return bridge.describe_image_preview(String(source || ""));
    }

    function describeNodeSurfaceMailPreview(source) {
        var bridge = root._mailPreviewBridge();
        if (!bridge)
            return ({});
        return bridge.describe_mail_preview(String(source || ""));
    }

    function resolveNodeSurfaceLocalFileSource(source) {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (!bridge || !bridge.resolve_local_file_source_url)
            return "";
        return String(bridge.resolve_local_file_source_url(String(source || "")) || "");
    }

    function openNodeSurfaceLocalFileSource(source, chooser) {
        var bridge = root.canvasItem ? root.canvasItem.canvasCommandBridgeRef : null;
        if (!bridge || !bridge.open_local_file_source)
            return ({"success": false, "error": {"code": "bridge_unavailable"}});
        return bridge.open_local_file_source(String(source || ""), Boolean(chooser));
    }

    function describeNodeSurfaceTabularPreview(properties, request) {
        var bridge = root._tabularPreviewBridge();
        if (bridge && bridge.describe_tabular_preview)
            return bridge.describe_tabular_preview(properties || ({}), request || ({}));
        var sourcePath = "";
        if (properties && properties.path !== undefined && properties.path !== null)
            sourcePath = String(properties.path || "");
        return {
            "state": sourcePath.trim().length > 0 ? "placeholder" : "placeholder",
            "message": sourcePath.trim().length > 0
                ? "Open fullscreen to resolve a bounded tabular preview window."
                : "Choose a tabular data file to preview it here.",
            "content_kind": "tabular",
            "preview_kind": "",
            "source": {"path": sourcePath},
            "selector": {},
            "limits": {
                "inline_row_limit": 50,
                "inline_column_limit": 50
            }
        };
    }

    function requestFolderExplorerAction(nodeId, command, payload) {
        var router = root._folderExplorerActionRouter();
        var normalizedNodeId = String(nodeId || "").trim();
        if (!normalizedNodeId || !router || !router.requestFolderExplorerAction) {
            return {
                "success": false,
                "cancelled": false,
                "action_id": root._folderExplorerActionId(command),
                "node_id": normalizedNodeId,
                "path": String((payload || ({})).path || ""),
                "error": {
                    "code": "bridge_unavailable",
                    "message": "Folder explorer action router is not available.",
                    "operation": root._folderExplorerActionId(command),
                    "path": String((payload || ({})).path || ""),
                    "target_path": ""
                }
            };
        }
        if (root._nodeReadOnly(normalizedNodeId)) {
            return {
                "success": false,
                "cancelled": false,
                "action_id": root._folderExplorerActionId(command),
                "node_id": normalizedNodeId,
                "path": String((payload || ({})).path || ""),
                "error": {
                    "code": "read_only",
                    "message": "Folder explorer node is read-only.",
                    "operation": root._folderExplorerActionId(command),
                    "path": String((payload || ({})).path || ""),
                    "target_path": ""
                }
            };
        }
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        var requestPayload = {};
        var incoming = payload || ({});
        for (var key in incoming) {
            if (Object.prototype.hasOwnProperty.call(incoming, key))
                requestPayload[key] = incoming[key];
        }
        requestPayload.node_id = normalizedNodeId;
        return router.requestFolderExplorerAction(root._folderExplorerActionId(command), requestPayload);
    }

    function createFolderExplorerPathPointer(nodeId, path, sceneX, sceneY) {
        return root.requestFolderExplorerAction(
            nodeId,
            "folder_explorer_send_to_corex_path_pointer",
            {
                "path": String(path || ""),
                "scene_x": Number(sceneX || 0),
                "scene_y": Number(sceneY || 0)
            }
        );
    }

    function openFolderExplorerInNewWindow(nodeId, path, sceneX, sceneY) {
        return root.requestFolderExplorerAction(
            nodeId,
            "folder_explorer_open_in_new_window",
            {
                "path": String(path || ""),
                "scene_x": Number(sceneX || 0),
                "scene_y": Number(sceneY || 0)
            }
        );
    }

    function folderExplorerDragPayload(path, isFolder) {
        var normalizedPath = String(path || "").trim();
        if (!normalizedPath)
            return ({});
        return {
            "action_id": root._folderExplorerActionId("folder_explorer_send_to_corex_path_pointer"),
            "type_id": "io.path_pointer",
            "properties": {
                "path": normalizedPath,
                "mode": Boolean(isFolder) ? "folder" : "file"
            }
        };
    }

    function browseNodePropertyPath(nodeId, key, currentPath) {
        if (!root.canvasItem)
            return "";
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedKey = String(key || "").trim();
        var sourceMode = arguments.length > 3 ? String(arguments[3] || "").trim() : "";
        var bridge = root.canvasItem.canvasCommandBridgeRef;
        if (!normalizedNodeId || !normalizedKey || !bridge || !bridge.browse_node_property_path)
            return "";
        if (root._nodeReadOnly(normalizedNodeId))
            return "";
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        if (sourceMode.length > 0) {
            return String(bridge.browse_node_property_path(
                normalizedNodeId,
                normalizedKey,
                String(currentPath || ""),
                sourceMode
            ) || "");
        }
        return String(bridge.browse_node_property_path(
            normalizedNodeId,
            normalizedKey,
            String(currentPath || "")
        ) || "");
    }

    function internalizeNodePropertyPath(nodeId, key, currentPath) {
        if (!root.canvasItem)
            return "";
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedKey = String(key || "").trim();
        var bridge = root.canvasItem.canvasCommandBridgeRef;
        if (!normalizedNodeId || !normalizedKey || !bridge || !bridge.internalize_node_property_path)
            return "";
        if (root._nodeReadOnly(normalizedNodeId))
            return "";
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        return String(bridge.internalize_node_property_path(
            normalizedNodeId,
            normalizedKey,
            String(currentPath || "")
        ) || "");
    }

    function pickNodePropertyColor(nodeId, key, currentValue) {
        if (!root.canvasItem)
            return "";
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedKey = String(key || "").trim();
        var bridge = root.canvasItem.canvasCommandBridgeRef;
        if (!normalizedNodeId || !normalizedKey || !bridge || !bridge.pick_node_property_color)
            return "";
        if (root._nodeReadOnly(normalizedNodeId))
            return "";
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        return String(bridge.pick_node_property_color(
            normalizedNodeId,
            normalizedKey,
            String(currentValue || "")
        ) || "");
    }
}
