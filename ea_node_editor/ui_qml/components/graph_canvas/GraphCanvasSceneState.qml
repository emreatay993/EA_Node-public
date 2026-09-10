import QtQml 2.15
import "GraphCanvasLogic.js" as GraphCanvasLogic

QtObject {
    id: root
    property var canvasItem: null
    property var edgeLayerItem: null
    property var selectedEdgeIds: []
    property string liveDragAnchorNodeId: ""
    property var liveDragNodeIds: []
    property var liveDragNodeLookup: ({})
    property real liveDragDx: 0.0
    property real liveDragDy: 0.0
    property int liveDragRevision: 0
    property int profileLiveDragOffsetUpdateCount: 0
    property int profileLiveDragMembershipFreezeCount: 0
    property var liveNodeGeometry: ({})
    property int _lastAppliedEdgeDeltaSequence: 0

    function _findFrameScheduler(item) {
        if (!item)
            return null;
        if (item.objectName === "graphCanvasFrameScheduler")
            return item;
        var children = item.children || [];
        for (var i = 0; i < children.length; i++) {
            var match = root._findFrameScheduler(children[i]);
            if (match)
                return match;
        }
        return null;
    }

    function _frameScheduler() {
        if (root.edgeLayerItem && root.edgeLayerItem.frameScheduler)
            return root.edgeLayerItem.frameScheduler;
        return root.canvasItem ? root._findFrameScheduler(root.canvasItem) : null;
    }

    function _requestEdgeRedraw() {
        var scheduler = root._frameScheduler();
        if (scheduler && scheduler.requestEdgeRedraw) {
            scheduler.requestEdgeRedraw();
            return;
        }
        if (root.edgeLayerItem && root.edgeLayerItem.requestRedraw)
            root.edgeLayerItem.requestRedraw();
    }

    function normalizeEdgeIds(values) {
        return GraphCanvasLogic.normalizeEdgeIds(values);
    }

    function availableEdgeIdSet() {
        return GraphCanvasLogic.availableEdgeIdSet(root.canvasItem ? root.canvasItem.edgePayload : []);
    }

    function pruneSelectedEdges() {
        root.selectedEdgeIds = GraphCanvasLogic.pruneSelectedEdgeIds(root.selectedEdgeIds, root.availableEdgeIdSet());
    }

    function clearEdgeSelection() {
        if (!root.selectedEdgeIds.length)
            return;
        root.selectedEdgeIds = [];
    }

    function toggleEdgeSelection(edgeId) {
        var next = root.normalizeEdgeIds(root.selectedEdgeIds);
        var index = next.indexOf(edgeId);
        if (index >= 0)
            next.splice(index, 1);
        else
            next.push(edgeId);
        root.selectedEdgeIds = next;
    }

    function setExclusiveEdgeSelection(edgeId) {
        root.selectedEdgeIds = edgeId ? [edgeId] : [];
    }

    function setEdgeSelection(edgeIds, additive) {
        var next = additive ? root.normalizeEdgeIds(root.selectedEdgeIds) : [];
        var additions = root.normalizeEdgeIds(edgeIds);
        for (var i = 0; i < additions.length; ++i) {
            if (next.indexOf(additions[i]) < 0)
                next.push(additions[i]);
        }
        root.selectedEdgeIds = next;
    }

    function sceneBackdropNodesModel() {
        var stateBridge = root.sceneStateBridge();
        if (stateBridge && stateBridge.backdrop_nodes_model !== undefined)
            return stateBridge.backdrop_nodes_model || [];
        return [];
    }

    function sceneStateBridge() {
        if (!root.canvasItem)
            return null;
        if (root.canvasItem.sceneStateBridge !== undefined)
            return root.canvasItem.sceneStateBridge;
        if (root.canvasItem._canvasSceneStateBridgeRef !== undefined)
            return root.canvasItem._canvasSceneStateBridgeRef;
        return null;
    }

    function _bridgeModel(name) {
        var stateBridge = root.sceneStateBridge();
        if (stateBridge && stateBridge[name] !== undefined)
            return stateBridge[name] || [];
        return [];
    }

    function visibleSceneNodesModel() {
        return root._bridgeModel("visible_nodes_payloads");
    }

    function visibleSceneBackdropNodesModel() {
        return root._bridgeModel("visible_backdrop_nodes_payloads");
    }

    function sceneAllNodesModel() {
        var stateBridge = root.sceneStateBridge();
        var nodes = stateBridge
            ? stateBridge.nodes_model
            : [];
        var backdrops = root.sceneBackdropNodesModel();
        if (!backdrops.length)
            return nodes;
        return nodes.concat(backdrops);
    }

    function _findNodePayloadInModel(nodes, nodeId) {
        var source = nodes || [];
        for (var i = 0; i < source.length; i++) {
            var node = source[i];
            if (node && node.node_id === nodeId)
                return node;
        }
        return null;
    }

    function sceneNodePayload(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return null;
        var stateBridge = root.sceneStateBridge();
        var visiblePayload = null;
        if (stateBridge && stateBridge.visible_scene_node_payload)
            visiblePayload = stateBridge.visible_scene_node_payload(normalized);
        if (!visiblePayload || !visiblePayload.node_id) {
            visiblePayload = root._findNodePayloadInModel(root.visibleSceneNodesModel(), normalized)
                || root._findNodePayloadInModel(root.visibleSceneBackdropNodesModel(), normalized);
        }
        if (visiblePayload)
            return visiblePayload;
        var nodes = root.sceneAllNodesModel();
        return root._findNodePayloadInModel(nodes, normalized);
    }

    function sceneEdgePayload(edgeId) {
        var normalized = String(edgeId || "").trim();
        if (!normalized)
            return null;
        var edges = root.canvasItem ? (root.canvasItem.edgePayload || []) : [];
        for (var i = 0; i < edges.length; i++) {
            var edge = edges[i];
            if (edge && edge.edge_id === normalized)
                return edge;
        }
        return null;
    }

    function _edgePayloadId(payload) {
        return String(payload && payload.edge_id || "").trim();
    }

    function _edgePayloadIdsAreUnique(edges) {
        var seen = {};
        var source = edges || [];
        for (var i = 0; i < source.length; i++) {
            var edgeId = root._edgePayloadId(source[i]);
            if (!edgeId || seen[edgeId])
                return false;
            seen[edgeId] = true;
        }
        return true;
    }

    function _findEdgePayloadIndex(edges, edgeId, startIndex) {
        var normalized = String(edgeId || "");
        var source = edges || [];
        for (var i = Math.max(0, Number(startIndex || 0)); i < source.length; i++) {
            if (root._edgePayloadId(source[i]) === normalized)
                return i;
        }
        return -1;
    }

    function _edgeDeltaEntries(entries) {
        var normalized = [];
        var source = entries || [];
        for (var i = 0; i < source.length; i++) {
            var entry = source[i] || ({});
            var payload = entry.payload || ({});
            var edgeId = root._edgePayloadId(payload) || String(entry.edge_id || "").trim();
            if (!edgeId)
                return null;
            normalized.push({
                "edgeId": edgeId,
                "index": entry.index,
                "payload": payload
            });
        }
        normalized.sort(function(left, right) {
            var leftIndex = Number(left.index);
            var rightIndex = Number(right.index);
            var leftHasIndex = isFinite(leftIndex);
            var rightHasIndex = isFinite(rightIndex);
            if (leftHasIndex && rightHasIndex)
                return leftIndex - rightIndex;
            if (leftHasIndex)
                return -1;
            if (rightHasIndex)
                return 1;
            return 0;
        });
        return normalized;
    }

    function _normalizedRemovedEdgeIds(values) {
        var normalized = [];
        var seen = {};
        var source = values || [];
        for (var i = 0; i < source.length; i++) {
            var edgeId = String(source[i] || "").trim();
            if (!edgeId || seen[edgeId])
                continue;
            normalized.push(edgeId);
            seen[edgeId] = true;
        }
        return normalized;
    }

    function _hasStructuralEdgePayloadDelta(deltaPayload) {
        var payload = deltaPayload || ({});
        return Boolean(
            (payload.added_edges && payload.added_edges.length)
            || (payload.updated_edges && payload.updated_edges.length)
            || (payload.removed_edge_ids && payload.removed_edge_ids.length)
        );
    }

    function _edgeDeltaExpectedCountBefore(deltaPayload, addedEntries, removedEdgeIds) {
        var afterCount = Number(deltaPayload.edge_count_after);
        if (!isFinite(afterCount) || afterCount < 0)
            return -1;
        return Math.max(0, Math.round(afterCount) - addedEntries.length + removedEdgeIds.length);
    }

    function _validateEdgeDeltaPayload(deltaPayload) {
        if (!deltaPayload || typeof deltaPayload !== "object")
            return false;
        if (deltaPayload.schema !== "graph_scene_edge_structural_delta" || Number(deltaPayload.version) !== 1)
            return false;
        if (Boolean(deltaPayload.requires_full_refresh))
            return false;
        var sequence = Number(deltaPayload.sequence || 0);
        if (!isFinite(sequence) || sequence <= 0)
            return false;
        if (!root._hasStructuralEdgePayloadDelta(deltaPayload))
            return false;
        return true;
    }

    function _commitEdgePayloadInPlace(currentEdges, nextEdges) {
        currentEdges.splice(0, currentEdges.length);
        for (var i = 0; i < nextEdges.length; i++)
            currentEdges.push(nextEdges[i]);
    }

    function _applyEdgeLayerStructuralPayloadDelta(edgePayload, deltaPayload) {
        if (!root.edgeLayerItem)
            return;
        root.edgeLayerItem.applyStructuralEdgePayloadDelta(edgePayload || [], deltaPayload || ({}));
    }

    function _replaceEdgeLayerPayload(edgePayload) {
        if (!root.edgeLayerItem)
            return;
        root.edgeLayerItem.replaceEdgePayload(edgePayload || []);
    }

    function _applyEdgePayloadDelta(deltaPayload) {
        if (!root.canvasItem || !root.edgeLayerItem)
            return false;
        if (!root._validateEdgeDeltaPayload(deltaPayload))
            return false;
        var sequence = Number(deltaPayload.sequence || 0);
        if (sequence === root._lastAppliedEdgeDeltaSequence)
            return true;
        if (root._lastAppliedEdgeDeltaSequence > 0 && sequence !== root._lastAppliedEdgeDeltaSequence + 1)
            return false;
        var currentEdges = root.canvasItem.edgePayload || [];
        if (!currentEdges.splice || !root._edgePayloadIdsAreUnique(currentEdges))
            return false;
        var addedEntries = root._edgeDeltaEntries(deltaPayload.added_edges);
        var updatedEntries = root._edgeDeltaEntries(deltaPayload.updated_edges);
        var removedEdgeIds = root._normalizedRemovedEdgeIds(deltaPayload.removed_edge_ids);
        if (addedEntries === null || updatedEntries === null)
            return false;
        var expectedCountBefore = root._edgeDeltaExpectedCountBefore(deltaPayload, addedEntries, removedEdgeIds);
        if (expectedCountBefore >= 0 && currentEdges.length !== expectedCountBefore)
            return false;

        var workingEdges = currentEdges.slice(0);
        for (var removeIndex = 0; removeIndex < removedEdgeIds.length; removeIndex++) {
            var removedIndex = root._findEdgePayloadIndex(workingEdges, removedEdgeIds[removeIndex], 0);
            if (removedIndex < 0)
                return false;
            workingEdges.splice(removedIndex, 1);
        }

        for (var updateIndex = 0; updateIndex < updatedEntries.length; updateIndex++) {
            var updatedEntry = updatedEntries[updateIndex];
            var existingUpdateIndex = root._findEdgePayloadIndex(workingEdges, updatedEntry.edgeId, 0);
            if (existingUpdateIndex < 0)
                return false;
            workingEdges[existingUpdateIndex] = updatedEntry.payload;
        }

        for (var addIndex = 0; addIndex < addedEntries.length; addIndex++) {
            var addedEntry = addedEntries[addIndex];
            var existingIndex = root._findEdgePayloadIndex(workingEdges, addedEntry.edgeId, 0);
            if (existingIndex >= 0) {
                return false;
            }
            var targetIndex = Number(addedEntry.index);
            if (!isFinite(targetIndex))
                targetIndex = workingEdges.length;
            targetIndex = Math.max(0, Math.min(Math.round(targetIndex), workingEdges.length));
            workingEdges.splice(targetIndex, 0, addedEntry.payload);
        }

        if (!root._edgePayloadIdsAreUnique(workingEdges))
            return false;
        var expectedCountAfter = Number(deltaPayload.edge_count_after);
        if (isFinite(expectedCountAfter) && workingEdges.length !== Math.max(0, Math.round(expectedCountAfter)))
            return false;

        root._commitEdgePayloadInPlace(currentEdges, workingEdges);
        root._applyEdgeLayerStructuralPayloadDelta(currentEdges, deltaPayload || ({}));
        root._lastAppliedEdgeDeltaSequence = sequence;
        return true;
    }

    function nodeSupportsPassiveStyle(nodeId) {
        var payload = root.sceneNodePayload(nodeId);
        if (!payload)
            return false;
        if (String(payload.runtime_behavior || "").toLowerCase() !== "passive")
            return false;
        return !(String(payload.surface_family || "").toLowerCase() === "annotation"
            && String(payload.surface_variant || "").toLowerCase() === "text");
    }

    function edgeSupportsFlowStyle(edgeId) {
        var payload = root.sceneEdgePayload(edgeId);
        if (!payload)
            return false;
        return String(payload.edge_family || "").toLowerCase() === "flow";
    }

    function nodeCanEnterScope(nodeId) {
        var payload = root.sceneNodePayload(nodeId);
        if (!payload)
            return false;
        if (payload.can_enter_scope !== undefined)
            return Boolean(payload.can_enter_scope);
        return String(payload.type_id || "") === "core.subnode";
    }

    function selectedNodeIds() {
        var bridge = root.sceneStateBridge();
        var selectedLookup = null;
        if (bridge && typeof bridge.selected_node_lookup !== "undefined")
            selectedLookup = bridge.selected_node_lookup || ({});
        var selected = [];
        if (bridge && typeof bridge.selected_node_ids !== "undefined") {
            var orderedSelected = bridge.selected_node_ids || [];
            for (var orderedIndex = 0; orderedIndex < orderedSelected.length; ++orderedIndex) {
                var orderedNodeId = String(orderedSelected[orderedIndex] || "").trim();
                if (!orderedNodeId.length)
                    continue;
                if (selectedLookup !== null
                        && Boolean(bridge.selected_node_lookup_authoritative)
                        && !Boolean(selectedLookup[orderedNodeId]))
                    continue;
                selected.push(orderedNodeId);
            }
            if (selected.length)
                return selected;
        }
        if (selectedLookup !== null && Boolean(bridge.selected_node_lookup_authoritative)) {
            for (var selectedId in selectedLookup) {
                if (Object.prototype.hasOwnProperty.call(selectedLookup, selectedId) && Boolean(selectedLookup[selectedId])) {
                    var normalizedSelectedId = String(selectedId || "").trim();
                    if (normalizedSelectedId.length)
                        selected.push(normalizedSelectedId);
                }
            }
            return selected;
        }
        var nodes = root.sceneAllNodesModel();
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            var nodeId = node ? String(node.node_id || "").trim() : "";
            if (!nodeId)
                continue;
            if (node.selected)
                selected.push(nodeId);
        }
        return selected;
    }

    function _appendUniqueDragNodeId(nodeIds, seenNodeIds, nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized || Boolean(seenNodeIds[normalized]))
            return;
        seenNodeIds[normalized] = true;
        nodeIds.push(normalized);
    }

    function _payloadNodeIdList(payload, key) {
        if (!payload || payload[key] === undefined || payload[key] === null)
            return [];
        if (payload[key].length === undefined)
            return [payload[key]];
        return payload[key];
    }

    function isGroupBackdropPayload(payload) {
        return !!payload && String(payload.surface_family || "").trim() === "group_backdrop";
    }

    function _nodeVisiblePorts(payload) {
        if (!payload)
            return [];
        var ports = payload.ports || [];
        var visiblePorts = [];
        for (var i = 0; i < ports.length; i++) {
            var port = ports[i];
            if (port && port.exposed !== false)
                visiblePorts.push(port);
        }
        return visiblePorts;
    }

    function _nodeHasConnectedVisiblePort(payload) {
        var ports = root._nodeVisiblePorts(payload);
        for (var i = 0; i < ports.length; i++) {
            var port = ports[i];
            if (!port)
                continue;
            if (Boolean(port.connected) || Number(port.connection_count || 0) > 0)
                return true;
        }
        return false;
    }

    function nodeCanAffectEdgeGeometry(nodeId) {
        var payload = root.sceneNodePayload(nodeId);
        if (!payload)
            return true;
        if (root.isGroupBackdropPayload(payload))
            return root._nodeHasConnectedVisiblePort(payload);
        return root._nodeVisiblePorts(payload).length > 0;
    }

    function _appendBackdropDragDescendants(nodeIds, seenNodeIds, backdropNodeId) {
        var payload = root.sceneNodePayload(backdropNodeId);
        if (!root.isGroupBackdropPayload(payload))
            return;

        var memberNodeIds = root._payloadNodeIdList(payload, "member_node_ids");
        for (var i = 0; i < memberNodeIds.length; i++)
            root._appendUniqueDragNodeId(nodeIds, seenNodeIds, memberNodeIds[i]);

        var memberBackdropIds = root._payloadNodeIdList(payload, "member_backdrop_ids");
        for (var j = 0; j < memberBackdropIds.length; j++)
            root._appendUniqueDragNodeId(nodeIds, seenNodeIds, memberBackdropIds[j]);
        for (var k = 0; k < memberBackdropIds.length; k++)
            root._appendBackdropDragDescendants(nodeIds, seenNodeIds, memberBackdropIds[k]);
    }

    function _appendBackdropAwareDragNodeIds(nodeIds, seenNodeIds, nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return;
        root._appendUniqueDragNodeId(nodeIds, seenNodeIds, normalized);
        root._appendBackdropDragDescendants(nodeIds, seenNodeIds, normalized);
    }

    function dragNodeIdsForAnchor(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return [];
        var selected = root.selectedNodeIds();
        var baseNodeIds = [];
        if (selected.length > 1 && selected.indexOf(normalized) >= 0) {
            baseNodeIds.push(normalized);
            for (var i = 0; i < selected.length; i++) {
                if (selected[i] !== normalized)
                    baseNodeIds.push(selected[i]);
            }
        } else {
            baseNodeIds.push(normalized);
        }

        var ordered = [];
        var seenNodeIds = {};
        for (var index = 0; index < baseNodeIds.length; index++)
            root._appendBackdropAwareDragNodeIds(ordered, seenNodeIds, baseNodeIds[index]);
        return ordered;
    }

    function _shouldRequestRedraw(requestRedraw) {
        return requestRedraw === undefined || Boolean(requestRedraw);
    }

    function _freezeLiveDragMembership(anchorNodeId) {
        var normalizedAnchor = String(anchorNodeId || "").trim();
        if (!normalizedAnchor)
            return false;
        if (root.liveDragAnchorNodeId === normalizedAnchor && root.liveDragNodeIds.length > 0)
            return true;
        var nodeIds = root.dragNodeIdsForAnchor(normalizedAnchor);
        var lookup = {};
        for (var i = 0; i < nodeIds.length; i++)
            lookup[String(nodeIds[i])] = true;
        root.liveDragAnchorNodeId = normalizedAnchor;
        root.liveDragNodeIds = nodeIds;
        root.liveDragNodeLookup = lookup;
        root.profileLiveDragMembershipFreezeCount += 1;
        return true;
    }

    function _applyLiveDragOffset(dx, dy, requestRedraw) {
        root.liveDragDx = Math.abs(dx) >= 0.01 ? dx : 0.0;
        root.liveDragDy = Math.abs(dy) >= 0.01 ? dy : 0.0;
        root.liveDragRevision += 1;
        root.profileLiveDragOffsetUpdateCount += 1;
        if (root._shouldRequestRedraw(requestRedraw))
            root._requestEdgeRedraw();
        return true;
    }

    function applyLiveDragOffsetNow(dx, dy, requestRedraw) {
        return root._applyLiveDragOffset(dx, dy, requestRedraw);
    }

    function setLiveDragOffset(anchorNodeId, dx, dy) {
        if (!root._freezeLiveDragMembership(anchorNodeId))
            return;
        var scheduler = root._frameScheduler();
        if (scheduler && scheduler.queueLiveDragOffset && scheduler.queueLiveDragOffset(root, dx, dy))
            return;
        root._applyLiveDragOffset(dx, dy, true);
    }

    function activeDragNodeIds(anchorNodeId) {
        return root.liveDragAnchorNodeId === String(anchorNodeId || "").trim()
            ? root.liveDragNodeIds.slice(0)
            : [];
    }

    function clearLiveDragOffset() {
        var scheduler = root._frameScheduler();
        var hasPendingLiveDragOffset = scheduler
            && scheduler.hasPendingLiveDragOffset
            && scheduler.hasPendingLiveDragOffset(root);
        if (hasPendingLiveDragOffset && scheduler.flushPendingRedraws)
            scheduler.flushPendingRedraws();
        if (scheduler && scheduler.cancelLiveDragOffset)
            scheduler.cancelLiveDragOffset(root);
        if (!root.liveDragAnchorNodeId && root.liveDragNodeIds.length === 0)
            return;
        root.liveDragAnchorNodeId = "";
        root.liveDragNodeIds = [];
        root.liveDragNodeLookup = ({});
        root.liveDragDx = 0.0;
        root.liveDragDy = 0.0;
        root.liveDragRevision += 1;
        root.profileLiveDragOffsetUpdateCount += 1;
        root._requestEdgeRedraw();
    }

    function _applyLiveNodeGeometry(nodeId, x, y, width, height, active, requestRedraw) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return false;
        var redrawEdges = root.nodeCanAffectEdgeGeometry(normalized);
        var next = {};
        var source = root.liveNodeGeometry || {};
        for (var key in source) {
            if (Object.prototype.hasOwnProperty.call(source, key))
                next[key] = source[key];
        }
        if (active) {
            next[normalized] = {
                "x": Number(x),
                "y": Number(y),
                "width": Math.max(1.0, Number(width)),
                "height": Math.max(1.0, Number(height))
            };
        } else {
            delete next[normalized];
        }
        root.liveNodeGeometry = next;
        if (redrawEdges && root._shouldRequestRedraw(requestRedraw))
            root._requestEdgeRedraw();
        return redrawEdges;
    }

    function applyLiveNodeGeometryNow(nodeId, x, y, width, height, active, requestRedraw) {
        return root._applyLiveNodeGeometry(nodeId, x, y, width, height, active, requestRedraw);
    }

    function setLiveNodeGeometry(nodeId, x, y, width, height, active) {
        var scheduler = root._frameScheduler();
        if (
            scheduler
            && scheduler.queueLiveNodeGeometry
            && scheduler.queueLiveNodeGeometry(root, nodeId, x, y, width, height, active)
        ) {
            root._applyLiveNodeGeometry(nodeId, x, y, width, height, active, false);
            return;
        }
        root._applyLiveNodeGeometry(nodeId, x, y, width, height, active, true);
    }

    function clearLiveNodeGeometry() {
        var scheduler = root._frameScheduler();
        var hasPendingLiveNodeGeometry = scheduler
            && scheduler.hasPendingLiveNodeGeometry
            && scheduler.hasPendingLiveNodeGeometry(root);
        if (hasPendingLiveNodeGeometry && scheduler.flushPendingRedraws)
            scheduler.flushPendingRedraws();
        if (scheduler && scheduler.cancelLiveNodeGeometry)
            scheduler.cancelLiveNodeGeometry(root);
        if (!root.liveNodeGeometry || Object.keys(root.liveNodeGeometry).length === 0)
            return;
        root.liveNodeGeometry = ({});
        root._requestEdgeRedraw();
    }

    function syncEdgePayload() {
        if (!root.canvasItem)
            return;
        var stateBridge = root.sceneStateBridge();
        var deltaPayload = stateBridge && stateBridge.edge_delta_payload !== undefined
            ? (stateBridge.edge_delta_payload || ({}))
            : ({});
        if (!root._applyEdgePayloadDelta(deltaPayload)) {
            var nextEdges = stateBridge
                ? (stateBridge.edges_model || [])
                : [];
            root.canvasItem.edgePayload = nextEdges;
            var sequence = Number(deltaPayload.sequence || 0);
            root._lastAppliedEdgeDeltaSequence = isFinite(sequence) && sequence > 0
                ? sequence
                : 0;
            root._replaceEdgeLayerPayload(nextEdges);
        }
        root.pruneSelectedEdges();
        root._requestEdgeRedraw();
    }
}
