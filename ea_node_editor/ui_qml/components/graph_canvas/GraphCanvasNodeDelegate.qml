import QtQuick 2.15
import "../graph" as GraphComponents
import "GraphCanvasLogic.js" as GraphCanvasLogic

GraphComponents.GraphNodeHost {
    id: nodeCard
    property bool backdropInputOverlay: false
    property string _settingsGroupGeometryNodeId: ""
    readonly property bool _groupBackdropNode: canvasItem ? canvasItem._isGroupBackdropPayload(modelData) : false

    objectName: nodeCard.backdropInputOverlay ? "graphGroupBackdropInputCard" : "graphNodeCard"
    nodeData: modelData
    worldOffset: canvasItem ? canvasItem.worldOffset : 0.0
    frameScheduler: canvasItem ? canvasItem.frameSchedulerRef : null
    hoveredPort: canvasItem ? canvasItem.hoveredPort : null
    previewPort: canvasItem ? canvasItem.dropPreviewPort : null
    pendingPort: canvasItem ? canvasItem.pendingConnectionPort : null
    dragSourcePort: canvasItem ? canvasItem.wireDragSourcePort() : null
    liveDragDx: 0.0
    liveDragDy: 0.0
    showShadow: !nodeCard._groupBackdropNode
        && !nodeCard.backdropInputOverlay
        && (prefs ? prefs.nodeShadowEnabled : false)
    shadowStrength: Number(prefs ? prefs.shadowStrength : 70)
    shadowSoftness: Number(prefs ? prefs.shadowSoftness : 50)
    shadowOffset: Number(prefs ? prefs.shadowOffset : 4)
    viewportInteractionCacheActive: canvasItem ? canvasItem.viewportInteractionWorldCacheActive : false
    edgeHitPassthroughEnabled: nodeCard.backdropInputOverlay
    renderActivationSceneRectPayload: canvasItem ? canvasItem.nodeRenderActivationSceneRectPayload : ({})
    visibleSceneRectPayload: canvasItem ? canvasItem.visibleSceneRectPayload : ({})
    contextTargetNodeId: canvasItem ? canvasItem.nodeContextNodeId : ""
    showPortLabelsPreference: prefs ? prefs.showPortLabels : true
    portLayerActive: !nodeCard._groupBackdropNode || nodeCard.backdropInputOverlay
    surfaceVariantOverride: nodeCard.backdropInputOverlay ? "group_backdrop_input_overlay" : ""
    opacity: nodeCard.backdropInputOverlay
        ? (nodeCard.renderActive ? 1.0 : 0.001)
        : 1.0
    settingsGroupAnimationsEnabled: !(canvasItem
        && canvasItem.canvasStateBridgeRef
        && Boolean(canvasItem.canvasStateBridgeRef.graphics_lightweight_canvas))

    function _syncSettingsGroupGeometry(active) {
        var geometryNodeId = active ? nodeId : _settingsGroupGeometryNodeId;
        if (!active)
            _settingsGroupGeometryNodeId = "";
        if (!canvasItem || !geometryNodeId.length)
            return;
        var current = canvasItem.liveNodeGeometry || ({});
        var existing = current[geometryNodeId];
        // A resize preview owns its geometry and cancels the settings transition.
        if (existing && !existing.settingsGroupAnimation)
            return;
        if (!active && !existing)
            return;
        var next = Object.assign({}, current);
        if (active) {
            _settingsGroupGeometryNodeId = geometryNodeId;
            next[geometryNodeId] = {
                "x": Number(nodeData.x), "y": Number(nodeData.y),
                "width": width, "height": height,
                "settingsGroupAnimation": true,
                "settingsGroupLayoutHeight": settingsGroupLayoutHeight,
                "settingsGroupPortOffsets": settingsGroupPortOffsets
            };
        } else {
            delete next[geometryNodeId];
        }
        canvasItem.liveNodeGeometry = next;
    }

    onWidthChanged: _syncSettingsGroupGeometry(settingsGroupAnimationRunning)
    onHeightChanged: _syncSettingsGroupGeometry(settingsGroupAnimationRunning)
    onSettingsGroupPortOffsetsChanged: _syncSettingsGroupGeometry(settingsGroupAnimationRunning)
    onSettingsGroupAnimationRunningChanged: _syncSettingsGroupGeometry(settingsGroupAnimationRunning)
    onNodeIdChanged: {
        _syncSettingsGroupGeometry(false);
        cancelSettingsGroupAnimation();
    }
    Component.onDestruction: _syncSettingsGroupGeometry(false)

    function _graphActionBridge() {
        return canvasItem ? canvasItem.graphActionBridgeRef : null;
    }

    function _canvasActionRouter() {
        return canvasItem ? canvasItem.canvasActionRouter : null;
    }

    function _findFrameScheduler(item) {
        if (!item)
            return null;
        if (item.objectName === "graphCanvasFrameScheduler")
            return item;
        var children = item.children || [];
        for (var i = 0; i < children.length; i++) {
            var match = nodeCard._findFrameScheduler(children[i]);
            if (match)
                return match;
        }
        return null;
    }

    function _frameScheduler() {
        return canvasItem ? nodeCard._findFrameScheduler(canvasItem) : null;
    }

    function _flushFrameScheduler() {
        var scheduler = nodeCard._frameScheduler();
        if (scheduler && scheduler.flushPendingRedraws)
            scheduler.flushPendingRedraws();
    }

    function _triggerGraphAction(actionId, nodeId, inlineTitleEdit) {
        var actionRouter = nodeCard._canvasActionRouter();
        if (actionRouter && actionRouter.triggerGraphAction) {
            var routedPayload = { "node_id": String(nodeId || "") };
            if (inlineTitleEdit)
                routedPayload.inline_title_edit = true;
            return Boolean(actionRouter.triggerGraphAction(actionId, routedPayload));
        }
        var graphActionBridge = nodeCard._graphActionBridge();
        if (!graphActionBridge || !graphActionBridge.trigger_graph_action)
            return false;
        var payload = { "node_id": String(nodeId || "") };
        if (inlineTitleEdit)
            payload.inline_title_edit = true;
        return Boolean(graphActionBridge.trigger_graph_action(actionId, payload));
    }

    // Backdrop nodes render in two stacked layers (main + input overlay), each a
    // separate GraphNodeHost instance. The resize handle updates only its own
    // host's _liveGeometry* properties, so the sibling instance would stay at the
    // committed model size until release. Mirroring the central liveNodeGeometry
    // map into every delegate keeps both instances in sync during the drag.
    Connections {
        target: nodeCard.canvasItem
        enabled: !!nodeCard.canvasItem && !!nodeCard.nodeData
        function onLiveNodeGeometryChanged() {
            if (!nodeCard.canvasItem || !nodeCard.nodeData)
                return;
            var map = nodeCard.canvasItem.liveNodeGeometry || ({});
            var entry = map[String(nodeCard.nodeData.node_id || "")];
            if (entry && entry.settingsGroupAnimation)
                return;
            if (entry) {
                nodeCard._liveX = Number(entry.x);
                nodeCard._liveY = Number(entry.y);
                nodeCard._liveWidth = Number(entry.width);
                nodeCard._liveHeight = Number(entry.height);
                nodeCard._liveGeometryActive = true;
            } else if (nodeCard._liveGeometryActive) {
                nodeCard._liveGeometryActive = false;
            }
        }
    }

    onNodeClicked: function(nodeId, additive) {
        if (!canvasItem)
            return;
        if (canvasItem.completeNodeLinkTargetPick && canvasItem.completeNodeLinkTargetPick(nodeId))
            return;
        var bridge = canvasItem.sceneCommandBridge;
        canvasItem.forceActiveFocus();
        canvasItem._closeContextMenus();
        canvasItem.clearPendingConnection();
        if (!bridge || !bridge.select_node)
            return;
        if (!additive)
            canvasItem.clearEdgeSelection();
        bridge.select_node(nodeId, additive);
    }
    onNodeContextRequested: function(nodeId, localX, localY) {
        if (!canvasItem)
            return;
        var point = nodeCard.mapToItem(canvasItem, localX, localY);
        canvasItem._openNodeContext(nodeId, point.x, point.y);
    }
    onNodeOpenRequested: function(nodeId) {
        if (canvasItem)
            nodeCard._triggerGraphAction("open_subnode_scope", nodeId);
    }
    onDragOffsetChanged: function(nodeId, dx, dy) {
        if (!canvasItem)
            return;
        canvasItem.setLiveDragOffset(nodeId, Number(dx), Number(dy));
    }
    onDragFinished: function(nodeId, finalX, finalY, _moved) {
        if (!canvasItem)
            return;
        var bridge = canvasItem.sceneCommandBridge;
        var dragNodeIds = canvasItem.activeDragNodeIds(nodeId);
        if (dragNodeIds.length === 0)
            dragNodeIds = canvasItem.dragNodeIdsForAnchor(nodeId);
        var anchorPayload = canvasItem._sceneNodePayload(nodeId);
        var anchorX = anchorPayload ? Number(anchorPayload.x) : Number(finalX);
        var anchorY = anchorPayload ? Number(anchorPayload.y) : Number(finalY);
        if (!isFinite(anchorX))
            anchorX = Number(finalX);
        if (!isFinite(anchorY))
            anchorY = Number(finalY);
        var rawDeltaX = Number(finalX) - anchorX;
        var rawDeltaY = Number(finalY) - anchorY;
        var snappedDelta = canvasItem.snappedDragDelta(nodeId, rawDeltaX, rawDeltaY);
        var deltaX = Number(snappedDelta.dx);
        var deltaY = Number(snappedDelta.dy);
        if (!isFinite(deltaX))
            deltaX = 0.0;
        if (!isFinite(deltaY))
            deltaY = 0.0;
        var finalSnappedX = anchorX + deltaX;
        var finalSnappedY = anchorY + deltaY;
        var movedByCommit = Math.abs(deltaX) >= 0.01 || Math.abs(deltaY) >= 0.01;

        canvasItem.clearLiveDragOffset();
        if (!bridge)
            return;
        if (!movedByCommit)
            return;
        if (dragNodeIds.length > 1) {
            movedByCommit = bridge.move_nodes_by_delta ? bridge.move_nodes_by_delta(dragNodeIds, deltaX, deltaY) : false;
            if (movedByCommit)
                canvasItem.clearEdgeSelection();
            nodeCard._flushFrameScheduler();
            return;
        }

        if (bridge.move_node)
            bridge.move_node(nodeId, finalSnappedX, finalSnappedY);
        if (movedByCommit && bridge.select_node) {
            canvasItem.clearEdgeSelection();
            bridge.select_node(nodeId, false);
        }
        // Retained edge delegates read the scalar drag facts through live bindings, so the
        // clear above already snapped them back to the pre-drag payload geometry.
        // The corrected snapshot otherwise waits on the frame scheduler's flush
        // timer, letting one frame paint the edge at its old position. Flushing
        // in the same call stack as the move commit closes that window.
        nodeCard._flushFrameScheduler();
    }
    onDragCanceled: function(_nodeId) {
        if (canvasItem)
            canvasItem.clearLiveDragOffset();
    }
    onResizePreviewChanged: function(nodeId, newX, newY, newWidth, newHeight, active) {
        if (canvasItem)
            canvasItem.setLiveNodeGeometry(nodeId, newX, newY, newWidth, newHeight, active);
    }
    onResizeFinished: function(nodeId, newX, newY, newWidth, newHeight) {
        if (!canvasItem)
            return;
        var bridge = canvasItem.sceneCommandBridge;
        canvasItem.setLiveNodeGeometry(nodeId, newX, newY, newWidth, newHeight, false);
        if (!bridge)
            return;
        if (bridge.set_node_geometry) {
            bridge.set_node_geometry(nodeId, newX, newY, newWidth, newHeight);
            return;
        }
        if (bridge.move_node)
            bridge.move_node(nodeId, newX, newY);
        if (bridge.resize_node)
            bridge.resize_node(nodeId, newWidth, newHeight);
    }
    onPortClicked: function(nodeId, portKey, direction, sceneX, sceneY, modifiers) {
        if (canvasItem)
            canvasItem.handlePortClick(nodeId, portKey, direction, sceneX, sceneY, modifiers);
    }
    onPortDragStarted: function(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers) {
        if (canvasItem)
            canvasItem.beginPortWireDrag(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers);
    }
    onPortDragMoved: function(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, dragActive, modifiers) {
        if (!canvasItem)
            return;
        var scheduler = nodeCard._frameScheduler();
        if (
            scheduler
            && scheduler.queueWireDragUpdate
            && scheduler.queueWireDragUpdate(
                canvasItem,
                nodeId,
                portKey,
                direction,
                sceneX,
                sceneY,
                screenX,
                screenY,
                dragActive,
                modifiers
            )
        ) {
            return;
        }
        canvasItem.updatePortWireDrag(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, dragActive, modifiers);
    }
    onPortDragFinished: function(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, dragActive, modifiers) {
        if (canvasItem) {
            nodeCard._flushFrameScheduler();
            canvasItem.finishPortWireDrag(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, dragActive, modifiers);
        }
    }
    onPortDragCanceled: function(_nodeId, _portKey, _direction) {
        if (canvasItem) {
            var scheduler = nodeCard._frameScheduler();
            if (scheduler && scheduler.cancelWireDragUpdate)
                scheduler.cancelWireDragUpdate(canvasItem);
            canvasItem.cancelWireDrag();
        }
    }
    onPortHoverChanged: function(nodeId, portKey, direction, sceneX, sceneY, hovered) {
        if (!canvasItem || (canvasItem.wireDragState && canvasItem.wireDragState.active))
            return;
        if (hovered) {
            var hoveredPortData = canvasItem._scenePortData(nodeId, portKey);
            var hoveredDirection = String(
                hoveredPortData && hoveredPortData.direction !== undefined
                    ? hoveredPortData.direction
                    : direction
            ).trim().toLowerCase();
            var hoveredSide = GraphCanvasLogic.normalizedPortSide(
                hoveredPortData && hoveredPortData.side !== undefined
                    ? hoveredPortData.side
                    : portKey
            );
            var nextHoveredPort = {
                "node_id": nodeId,
                "port_key": portKey,
                "direction": hoveredDirection,
                "kind": hoveredPortData ? String(hoveredPortData.kind || "") : "",
                "data_type": hoveredPortData ? String(hoveredPortData.data_type || "") : "",
                "allow_multiple_connections": hoveredPortData ? Boolean(hoveredPortData.allow_multiple_connections) : false,
                "scene_x": sceneX,
                "scene_y": sceneY,
                "valid_drop": false
            };
            if (hoveredSide)
                nextHoveredPort.side = hoveredSide;
            if (canvasItem._samePort && canvasItem._samePort(canvasItem.hoveredPort, nextHoveredPort))
                return;
            canvasItem.hoveredPort = nextHoveredPort;
            if (canvasItem.requestEdgeRedraw)
                canvasItem.requestEdgeRedraw();
        } else if (
            canvasItem.hoveredPort
            && canvasItem.hoveredPort.node_id === nodeId
            && canvasItem.hoveredPort.port_key === portKey
        ) {
            canvasItem.hoveredPort = null;
            if (canvasItem.requestEdgeRedraw)
                canvasItem.requestEdgeRedraw();
        }
    }
    onSurfaceControlInteractionStarted: function(nodeId) {
        if (canvasItem)
            canvasItem.prepareNodeSurfaceControlInteraction(nodeId);
    }
    onInlinePropertyCommitted: function(nodeId, key, value) {
        if (canvasItem && canvasItem.commitNodeSurfaceProperty(nodeId, key, value))
            canvasItem.forceActiveFocus();
    }
    onSensitivePropertyReplaceRequested: function(nodeId, key, plaintext) {
        var bridge = canvasItem ? canvasItem.sceneCommandBridge : null;
        if (bridge && bridge.set_node_secret
                && bridge.set_node_secret(nodeId, key, plaintext))
            canvasItem.forceActiveFocus();
    }
    onSensitivePropertyClearRequested: function(nodeId, key) {
        var bridge = canvasItem ? canvasItem.sceneCommandBridge : null;
        if (bridge && bridge.clear_node_secret
                && bridge.clear_node_secret(nodeId, key))
            canvasItem.forceActiveFocus();
    }
    onSettingsGroupExpansionRequested: function(nodeId, groupId, expanded) {
        if (!canvasItem || nodeCard.surfaceInteractionLocked)
            return;
        var bridge = canvasItem.sceneCommandBridge;
        if (!bridge || !bridge.set_node_settings_group_expanded)
            return;
        nodeCard.beginSettingsGroupAnimation();
        if (bridge.set_node_settings_group_expanded(nodeId, groupId, expanded)) {
            // Scene mutation clears transient geometry, including a retoggle's
            // still-running preview. Restore it before the next painted frame.
            nodeCard._syncSettingsGroupGeometry(nodeCard.settingsGroupAnimationRunning);
            canvasItem.forceActiveFocus();
            return;
        }
        nodeCard.cancelSettingsGroupAnimation();
    }
    onPortLabelCommitted: function(nodeId, portKey, label) {
        if (canvasItem && canvasItem.commitNodePortLabel(nodeId, portKey, label))
            canvasItem.forceActiveFocus();
    }
    onNodeCommentEditorRequested: function(_nodeId, compose) {
        if (canvasItem && canvasItem.openNodeCommentEditor)
            canvasItem.openNodeCommentEditor(nodeCard.nodeData, compose);
    }
    onTriggerNodeRequested: function(nodeId) {
        if (!canvasItem)
            return;
        var bridge = canvasItem.canvasCommandBridgeRef;
        if (bridge && bridge.trigger_node)
            bridge.trigger_node(nodeId);
    }
    onNodeActionRequested: function(nodeId, actionId, payload) {
        if (!canvasItem)
            return;
        var normalized = String(actionId || "").trim();
        if (!normalized)
            return;
        var actionRouter = nodeCard._canvasActionRouter();
        if (actionRouter && actionRouter.handleNodeDelegateAction)
            return actionRouter.handleNodeDelegateAction(nodeCard, nodeId, normalized);
        if (nodeCard.dispatchSurfaceAction)
            nodeCard.dispatchSurfaceAction(normalized);
    }
}
