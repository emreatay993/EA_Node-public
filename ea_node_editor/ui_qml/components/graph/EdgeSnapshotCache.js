.pragma library
.import "EdgeMath.js" as EdgeMath
.import "EdgePaintPolicy.js" as EdgePaintPolicy
.import "EdgeViewportMath.js" as EdgeViewportMath

function invalidateGeometryCache(edgeLayer) {
    edgeLayer._cachedBaseNodeMap = null;
    edgeLayer._cachedNodeMap = null;
    edgeLayer._cachedEdgeGeometries = ({});
    edgeLayer._edgeSpatialIndex = ({});
    edgeLayer._edgeSpatialIndexDirty = true;
    _bumpSpatialIndexGeneration(edgeLayer);
    edgeLayer._activeNodeGeometryDirty = false;
    edgeLayer._lastActiveGeometryNodeLookup = ({});
    edgeLayer._activeGeometryDependencyNodeLookup = ({});
    edgeLayer._lastVisibleEdgeSetKey = "";
}

function invalidateTopologyCache(edgeLayer) {
    edgeLayer._edgeById = ({});
    edgeLayer._edgeIds = [];
    edgeLayer._edgeDrawOrderById = ({});
    edgeLayer._edgeIdsByNodeId = ({});
    edgeLayer._edgeDependencyNodeIdsById = ({});
    edgeLayer._edgeTopologyCacheRevision = -1;
}

function _clearViewportSpatialQueryCache(edgeLayer) {
    edgeLayer._viewportSpatialQueryCacheKey = "";
    edgeLayer._viewportSpatialQueryCache = null;
}

function _bumpSpatialIndexGeneration(edgeLayer) {
    var generation = Number(edgeLayer._edgeSpatialIndexGeneration || 0);
    edgeLayer._edgeSpatialIndexGeneration = (isFinite(generation) ? generation : 0) + 1;
    _clearViewportSpatialQueryCache(edgeLayer);
}

function _removeSpatialIndexEntry(edgeLayer, edgeId, skipGenerationBump) {
    var index = edgeLayer._edgeSpatialIndex || null;
    if (!index || !index.valid)
        return;
    var removed = _removeSpatialEntry(index, edgeId);
    if (index.entriesById)
        delete index.entriesById[edgeId];
    if (index.edgeIds)
        _removeValue(index.edgeIds, edgeId);
    if (removed && !skipGenerationBump)
        _bumpSpatialIndexGeneration(edgeLayer);
}

function _deltaEdgeLookup(deltaPayload) {
    var lookup = {};
    var sources = [
        deltaPayload ? deltaPayload.dirty_edge_ids : [],
        deltaPayload ? deltaPayload.added_edge_ids : [],
        deltaPayload ? deltaPayload.updated_edge_ids : [],
        deltaPayload ? deltaPayload.removed_edge_ids : []
    ];
    for (var sourceIndex = 0; sourceIndex < sources.length; sourceIndex++) {
        var values = sources[sourceIndex] || [];
        for (var i = 0; i < values.length; i++) {
            var edgeId = String(values[i] || "").trim();
            if (edgeId)
                lookup[edgeId] = true;
        }
    }
    return lookup;
}

function _removedEdgeLookup(deltaPayload) {
    var lookup = {};
    var values = deltaPayload ? (deltaPayload.removed_edge_ids || []) : [];
    for (var i = 0; i < values.length; i++) {
        var edgeId = String(values[i] || "").trim();
        if (edgeId)
            lookup[edgeId] = true;
    }
    return lookup;
}

function _hasLookupValues(lookup) {
    for (var key in lookup || ({})) {
        if (Object.prototype.hasOwnProperty.call(lookup, key) && lookup[key])
            return true;
    }
    return false;
}

function _sameStringArray(left, right) {
    var leftValues = left || [];
    var rightValues = right || [];
    if (leftValues.length !== rightValues.length)
        return false;
    for (var i = 0; i < leftValues.length; i++) {
        if (String(leftValues[i] || "") !== String(rightValues[i] || ""))
            return false;
    }
    return true;
}

function _findDirtyEdges(edgeLayer, dirtyEdgeIds) {
    var foundById = {};
    var remaining = {};
    for (var dirtyIndex = 0; dirtyIndex < dirtyEdgeIds.length; dirtyIndex++)
        remaining[dirtyEdgeIds[dirtyIndex]] = true;
    var remainingCount = dirtyEdgeIds.length;
    var edgesList = edgeLayer.edges || [];
    for (var i = 0; i < edgesList.length && remainingCount > 0; i++) {
        var edge = edgesList[i];
        var edgeId = String(edge && edge.edge_id || "").trim();
        if (!edgeId || !remaining[edgeId])
            continue;
        foundById[edgeId] = {"edge": edge, "drawOrderIndex": i};
        delete remaining[edgeId];
        remainingCount -= 1;
    }
    return remainingCount === 0 ? foundById : null;
}

function _replaceEdgeTopologyEntries(edgeLayer, dirtyEdgeIds) {
    if (Number(edgeLayer._edgeTopologyCacheRevision) < 0)
        return false;
    var dirtyEdgesById = _findDirtyEdges(edgeLayer, dirtyEdgeIds);
    if (!dirtyEdgesById)
        return false;

    var edgeById = edgeLayer._edgeById || ({});
    var drawOrderById = edgeLayer._edgeDrawOrderById || ({});
    var edgeIdsByNodeId = edgeLayer._edgeIdsByNodeId || ({});
    var dependencyNodeIdsById = edgeLayer._edgeDependencyNodeIdsById || ({});
    for (var i = 0; i < dirtyEdgeIds.length; i++) {
        var edgeId = dirtyEdgeIds[i];
        var record = dirtyEdgesById[edgeId];
        var edge = record ? record.edge : null;
        if (!edge)
            return false;
        var previousNodeIds = dependencyNodeIdsById[edgeId] || [];
        var nextNodeIds = _edgeDependencyNodeIds(edge);
        if (!_sameStringArray(previousNodeIds, nextNodeIds)) {
            for (var previousIndex = 0; previousIndex < previousNodeIds.length; previousIndex++) {
                var previousNodeId = previousNodeIds[previousIndex];
                _removeValue(edgeIdsByNodeId[previousNodeId], edgeId);
            }
            for (var nextIndex = 0; nextIndex < nextNodeIds.length; nextIndex++) {
                var nextNodeId = nextNodeIds[nextIndex];
                if (!edgeIdsByNodeId[nextNodeId])
                    edgeIdsByNodeId[nextNodeId] = [];
                if (edgeIdsByNodeId[nextNodeId].indexOf(edgeId) < 0)
                    edgeIdsByNodeId[nextNodeId].push(edgeId);
            }
            dependencyNodeIdsById[edgeId] = nextNodeIds;
        }
        edgeById[edgeId] = edge;
        drawOrderById[edgeId] = record.drawOrderIndex;
    }
    edgeLayer._edgeById = edgeById;
    edgeLayer._edgeDrawOrderById = drawOrderById;
    edgeLayer._edgeIdsByNodeId = edgeIdsByNodeId;
    edgeLayer._edgeDependencyNodeIdsById = dependencyNodeIdsById;
    edgeLayer._edgeTopologyCacheRevision = Number(edgeLayer._edgeTopologyRevision || 0);
    return true;
}

function _edgeIdFromDeltaEntry(entry) {
    var payload = entry && entry.payload ? entry.payload : ({});
    return String((payload && payload.edge_id) || (entry && entry.edge_id) || "").trim();
}

function _deltaEntryLookup(entries) {
    var lookup = {};
    var source = entries || [];
    for (var i = 0; i < source.length; i++) {
        var entry = source[i] || ({});
        var edgeId = _edgeIdFromDeltaEntry(entry);
        if (!edgeId)
            continue;
        lookup[edgeId] = {
            "index": entry.index
        };
    }
    return lookup;
}

function _orderedDeltaIds(entries, fallbackIds) {
    var ids = [];
    var seen = {};
    var source = entries || [];
    for (var i = 0; i < source.length; i++) {
        var entryId = _edgeIdFromDeltaEntry(source[i] || ({}));
        if (entryId && !seen[entryId]) {
            ids.push(entryId);
            seen[entryId] = true;
        }
    }
    var fallbacks = fallbackIds || [];
    for (i = 0; i < fallbacks.length; i++) {
        var fallbackId = String(fallbacks[i] || "").trim();
        if (fallbackId && !seen[fallbackId]) {
            ids.push(fallbackId);
            seen[fallbackId] = true;
        }
    }
    return ids;
}

function _removeExistingValue(values, value) {
    if (!values)
        return false;
    var removed = false;
    for (var i = values.length - 1; i >= 0; i--) {
        if (values[i] === value) {
            values.splice(i, 1);
            removed = true;
        }
    }
    return removed;
}

function _removeEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, edgeId) {
    var previousNodeIds = dependencyNodeIdsById[edgeId] || [];
    for (var i = 0; i < previousNodeIds.length; i++) {
        var previousNodeId = previousNodeIds[i];
        _removeValue(edgeIdsByNodeId[previousNodeId], edgeId);
        if (edgeIdsByNodeId[previousNodeId] && !edgeIdsByNodeId[previousNodeId].length)
            delete edgeIdsByNodeId[previousNodeId];
    }
    delete dependencyNodeIdsById[edgeId];
}

function _addEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, edgeId, edge) {
    var nextNodeIds = _edgeDependencyNodeIds(edge);
    dependencyNodeIdsById[edgeId] = nextNodeIds;
    for (var i = 0; i < nextNodeIds.length; i++) {
        var nodeId = nextNodeIds[i];
        if (!edgeIdsByNodeId[nodeId])
            edgeIdsByNodeId[nodeId] = [];
        if (edgeIdsByNodeId[nodeId].indexOf(edgeId) < 0)
            edgeIdsByNodeId[nodeId].push(edgeId);
    }
}

function _insertEdgeId(edgeIds, edgeId, indexValue) {
    if (edgeIds.indexOf(edgeId) >= 0)
        return false;
    var targetIndex = Number(indexValue);
    if (!isFinite(targetIndex))
        targetIndex = edgeIds.length;
    targetIndex = Math.max(0, Math.min(Math.round(targetIndex), edgeIds.length));
    edgeIds.splice(targetIndex, 0, edgeId);
    return true;
}

function _drawOrderForInsertedEdge(edgeIds, drawOrderById, edgeId, fallbackIndex) {
    var edgeIndex = edgeIds.indexOf(edgeId);
    if (edgeIndex < 0)
        return fallbackIndex;
    var left = Number.NaN;
    for (var leftIndex = edgeIndex - 1; leftIndex >= 0; leftIndex--) {
        left = Number(drawOrderById[edgeIds[leftIndex]]);
        if (isFinite(left))
            break;
    }
    var right = Number.NaN;
    for (var rightIndex = edgeIndex + 1; rightIndex < edgeIds.length; rightIndex++) {
        right = Number(drawOrderById[edgeIds[rightIndex]]);
        if (isFinite(right))
            break;
    }
    if (isFinite(left) && isFinite(right) && left < right)
        return left + ((right - left) / 2.0);
    if (isFinite(left))
        return left + 1.0;
    if (isFinite(right))
        return right - 1.0;
    return fallbackIndex;
}

function _applyStructuralEdgeTopologyEntries(edgeLayer, deltaPayload, dirtyEdgeIds, addedLookup, removedLookup) {
    if (Number(edgeLayer._edgeTopologyCacheRevision) < 0)
        return false;
    var edgeById = edgeLayer._edgeById || null;
    var edgeIds = edgeLayer._edgeIds || null;
    var drawOrderById = edgeLayer._edgeDrawOrderById || null;
    var edgeIdsByNodeId = edgeLayer._edgeIdsByNodeId || null;
    var dependencyNodeIdsById = edgeLayer._edgeDependencyNodeIdsById || null;
    if (!edgeById || !edgeIds || !drawOrderById || !edgeIdsByNodeId || !dependencyNodeIdsById)
        return false;

    var addedEntryLookup = _deltaEntryLookup(deltaPayload ? deltaPayload.added_edges : []);
    var addedEdgeIds = _orderedDeltaIds(deltaPayload ? deltaPayload.added_edges : [], deltaPayload ? (deltaPayload.added_edge_ids || []) : []);
    var removedEdgeIds = _orderedDeltaIds([], deltaPayload ? (deltaPayload.removed_edge_ids || []) : []);
    var nonRemovedDirtyEdgeIds = [];
    for (var dirtyIndex = 0; dirtyIndex < dirtyEdgeIds.length; dirtyIndex++) {
        var dirtyEdgeId = dirtyEdgeIds[dirtyIndex];
        if (!removedLookup[dirtyEdgeId])
            nonRemovedDirtyEdgeIds.push(dirtyEdgeId);
    }
    var dirtyEdgesById = nonRemovedDirtyEdgeIds.length
        ? _findDirtyEdges(edgeLayer, nonRemovedDirtyEdgeIds)
        : ({});
    if (!dirtyEdgesById)
        return false;

    var nextEdgeIds = edgeIds.slice(0);
    for (var removeIndex = 0; removeIndex < removedEdgeIds.length; removeIndex++) {
        var removedEdgeId = removedEdgeIds[removeIndex];
        if (!edgeById[removedEdgeId])
            return false;
        if (!_removeExistingValue(nextEdgeIds, removedEdgeId))
            return false;
        _removeEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, removedEdgeId);
        delete edgeById[removedEdgeId];
        delete drawOrderById[removedEdgeId];
    }

    for (var updateIndex = 0; updateIndex < nonRemovedDirtyEdgeIds.length; updateIndex++) {
        var updatedEdgeId = nonRemovedDirtyEdgeIds[updateIndex];
        if (addedLookup[updatedEdgeId])
            continue;
        var updatedRecord = dirtyEdgesById[updatedEdgeId];
        if (!updatedRecord || !updatedRecord.edge || !edgeById[updatedEdgeId])
            return false;
        _removeEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, updatedEdgeId);
        _addEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, updatedEdgeId, updatedRecord.edge);
        edgeById[updatedEdgeId] = updatedRecord.edge;
        drawOrderById[updatedEdgeId] = updatedRecord.drawOrderIndex;
    }

    for (var addIndex = 0; addIndex < addedEdgeIds.length; addIndex++) {
        var addedEdgeId = addedEdgeIds[addIndex];
        var addedRecord = dirtyEdgesById[addedEdgeId];
        if (!addedRecord || !addedRecord.edge || edgeById[addedEdgeId])
            return false;
        var addedEntry = addedEntryLookup[addedEdgeId] || ({});
        var insertionIndex = Number(addedEntry.index);
        if (!isFinite(insertionIndex))
            insertionIndex = addedRecord.drawOrderIndex;
        if (!_insertEdgeId(nextEdgeIds, addedEdgeId, insertionIndex))
            return false;
        edgeById[addedEdgeId] = addedRecord.edge;
        _addEdgeTopologyMembership(edgeIdsByNodeId, dependencyNodeIdsById, addedEdgeId, addedRecord.edge);
    }

    for (addIndex = 0; addIndex < addedEdgeIds.length; addIndex++) {
        addedEdgeId = addedEdgeIds[addIndex];
        addedRecord = dirtyEdgesById[addedEdgeId];
        drawOrderById[addedEdgeId] = _drawOrderForInsertedEdge(
            nextEdgeIds,
            drawOrderById,
            addedEdgeId,
            addedRecord ? addedRecord.drawOrderIndex : nextEdgeIds.indexOf(addedEdgeId)
        );
    }

    var expectedCountAfter = Number(deltaPayload ? deltaPayload.edge_count_after : Number.NaN);
    if (isFinite(expectedCountAfter) && nextEdgeIds.length !== Math.max(0, Math.round(expectedCountAfter)))
        return false;
    var edgeListLength = (edgeLayer.edges || []).length;
    if (nextEdgeIds.length !== edgeListLength)
        return false;
    edgeLayer._edgeIds = nextEdgeIds;
    edgeLayer._edgeById = edgeById;
    edgeLayer._edgeDrawOrderById = drawOrderById;
    edgeLayer._edgeIdsByNodeId = edgeIdsByNodeId;
    edgeLayer._edgeDependencyNodeIdsById = dependencyNodeIdsById;
    edgeLayer._edgeTopologyCacheRevision = Number(edgeLayer._edgeTopologyRevision || 0);
    edgeLayer.profileTotalEdgeCount = nextEdgeIds.length;
    return true;
}

function applyTopologyDeltaCache(edgeLayer, deltaPayload) {
    var dirtyLookup = _deltaEdgeLookup(deltaPayload || ({}));
    var dirtyEdgeIds = _lookupKeys(dirtyLookup);
    if (!dirtyEdgeIds.length)
        return false;

    var removedLookup = _removedEdgeLookup(deltaPayload || ({}));
    var addedLookup = _lookupFromIds(deltaPayload ? (deltaPayload.added_edge_ids || []) : []);
    var structuralDelta = _hasLookupValues(addedLookup) || _hasLookupValues(removedLookup);
    var appliedTopologyDelta = structuralDelta
        ? _applyStructuralEdgeTopologyEntries(edgeLayer, deltaPayload || ({}), dirtyEdgeIds, addedLookup, removedLookup)
        : _replaceEdgeTopologyEntries(edgeLayer, dirtyEdgeIds);
    if (!appliedTopologyDelta)
        invalidateTopologyCache(edgeLayer);
    else
        edgeLayer.profileEdgeTopologyEntryUpdateCount += dirtyEdgeIds.length;
    edgeLayer._edgeTopologyDirty = false;
    edgeLayer._edgeTopologyDeltaDirty = true;
    edgeLayer._edgeTopologyDirtyEdgeLookup = dirtyLookup;
    edgeLayer._edgeTopologyRemovedEdgeLookup = removedLookup;
    if (structuralDelta)
        edgeLayer._lastVisibleEdgeSetKey = "";

    for (var i = 0; i < dirtyEdgeIds.length; i++) {
        var edgeId = dirtyEdgeIds[i];
        delete edgeLayer._cachedEdgeGeometries[edgeId];
        delete edgeLayer._visibleEdgeSnapshotById[edgeId];
        _removeSpatialIndexEntry(edgeLayer, edgeId);
    }
    edgeLayer._visibleEdgeSnapshots = (edgeLayer._visibleEdgeSnapshots || []).filter(function(snapshot) {
        return snapshot && !removedLookup[String(snapshot.edgeId || "")];
    });
    return true;
}

function getNodeMap(edgeLayer) {
    if (edgeLayer._cachedNodeMap !== null)
        return edgeLayer._cachedNodeMap;
    edgeLayer._cachedNodeMap = edgeLayer._nodeMap();
    return edgeLayer._cachedNodeMap;
}

function applyNodePayloadDelta(edgeLayer, deltaPayload) {
    if (!deltaPayload || String(deltaPayload.kind || "") !== "node_delta")
        return false;
    var addedNodeIds = deltaPayload.added_node_ids || [];
    if ((deltaPayload.removed_node_ids || []).length > 0)
        return false;
    var payloads = deltaPayload.nodes || [];
    if (addedNodeIds.length > 0) {
        var addedLookup = {};
        for (var addedIndex = 0; addedIndex < addedNodeIds.length; addedIndex++) {
            var addedNodeId = String(addedNodeIds[addedIndex] || "").trim();
            if (!addedNodeId || addedLookup[addedNodeId])
                return false;
            addedLookup[addedNodeId] = true;
        }
        var seenPayloadLookup = {};
        var payloadGroups = [payloads, deltaPayload.backdrop_nodes || []];
        var payloadCount = 0;
        for (var groupIndex = 0; groupIndex < payloadGroups.length; groupIndex++) {
            var group = payloadGroups[groupIndex];
            for (var payloadIndex = 0; payloadIndex < group.length; payloadIndex++) {
                var deltaPayloadNodeId = String(group[payloadIndex] && group[payloadIndex].node_id || "").trim();
                if (!deltaPayloadNodeId || !addedLookup[deltaPayloadNodeId] || seenPayloadLookup[deltaPayloadNodeId])
                    return false;
                seenPayloadLookup[deltaPayloadNodeId] = true;
                payloadCount += 1;
            }
        }
        if (payloadCount !== addedNodeIds.length)
            return false;
    }
    var next = {};
    var current = edgeLayer._nodePayloadDeltaById || {};
    for (var existingId in current) {
        if (Object.prototype.hasOwnProperty.call(current, existingId))
            next[existingId] = current[existingId];
    }
    for (var i = 0; i < payloads.length; i++) {
        var payload = payloads[i];
        var nodeId = String(payload && payload.node_id || "").trim();
        if (!nodeId)
            return false;
        if (addedNodeIds.length > 0 && current[nodeId] !== undefined)
            return false;
        next[nodeId] = payload;
    }
    edgeLayer._nodePayloadDeltaById = next;
    edgeLayer._cachedBaseNodeMap = null;
    edgeLayer._cachedNodeMap = null;
    return true;
}

function _appendUnique(values, value) {
    var normalized = String(value || "").trim();
    if (!normalized || values.indexOf(normalized) >= 0)
        return;
    values.push(normalized);
}

function _edgeDependencyNodeIds(edge) {
    var ids = [];
    _appendUnique(ids, edge ? edge.source_node_id : "");
    _appendUnique(ids, edge ? edge.target_node_id : "");
    _appendUnique(ids, edge ? edge.source_anchor_node_id : "");
    _appendUnique(ids, edge ? edge.target_anchor_node_id : "");
    return ids;
}

function ensureEdgeTopology(edgeLayer, edgesList) {
    var revision = Number(edgeLayer._edgeTopologyRevision);
    if (!isFinite(revision))
        revision = 0;
    if (Number(edgeLayer._edgeTopologyCacheRevision) === revision
            && edgeLayer._edgeById
            && edgeLayer._edgeIds
            && edgeLayer._edgeIdsByNodeId)
        return;

    var edgeById = {};
    var edgeIds = [];
    var drawOrderById = {};
    var edgeIdsByNodeId = {};
    var dependencyNodeIdsById = {};
    var source = edgesList || [];
    for (var i = 0; i < source.length; i++) {
        var edge = source[i];
        if (!edge || !edge.edge_id)
            continue;
        var edgeId = String(edge.edge_id);
        edgeById[edgeId] = edge;
        edgeIds.push(edgeId);
        drawOrderById[edgeId] = i;
        var nodeIds = _edgeDependencyNodeIds(edge);
        dependencyNodeIdsById[edgeId] = nodeIds;
        for (var nodeIndex = 0; nodeIndex < nodeIds.length; nodeIndex++) {
            var nodeId = nodeIds[nodeIndex];
            if (!edgeIdsByNodeId[nodeId])
                edgeIdsByNodeId[nodeId] = [];
            edgeIdsByNodeId[nodeId].push(edgeId);
        }
    }
    edgeLayer._edgeById = edgeById;
    edgeLayer._edgeIds = edgeIds;
    edgeLayer._edgeDrawOrderById = drawOrderById;
    edgeLayer._edgeIdsByNodeId = edgeIdsByNodeId;
    edgeLayer._edgeDependencyNodeIdsById = dependencyNodeIdsById;
    edgeLayer._edgeTopologyCacheRevision = revision;
    edgeLayer.profileTotalEdgeCount = edgeIds.length;
    edgeLayer.profileEdgeTopologyRebuildCount += 1;
}

function _edgeGeometryDependencyKey(edgeLayer, edge) {
    var edgeId = String(edge && edge.edge_id || "");
    var nodeIds = (edgeLayer._edgeDependencyNodeIdsById || ({}))[edgeId] || _edgeDependencyNodeIds(edge);
    var activeLookup = edgeLayer._activeGeometryDependencyNodeLookup || ({});
    var parts = [
        "edge", edgeId,
        "topology", String(edgeLayer._edgeTopologyRevision || 0),
        "nodes", String(edgeLayer._nodeGeometryRevision || 0)
    ];
    for (var i = 0; i < nodeIds.length; i++) {
        var nodeId = nodeIds[i];
        if (activeLookup[nodeId])
            parts.push("active", nodeId, String(edgeLayer._activeNodeGeometryRevision || 0));
    }
    return parts.join("|");
}

function getCachedEdgeGeometryRecord(edgeLayer, edge, nodeById) {
    var edgeId = edge.edge_id;
    var cached = edgeLayer._cachedEdgeGeometries[edgeId];
    var dependencyKey = _edgeGeometryDependencyKey(edgeLayer, edge);
    if (cached !== undefined && cached.key === dependencyKey) {
        cached.spatialIndexEntryDirty = false;
        if (edgeLayer._collectingEdgeSnapshotStats)
            edgeLayer.profileGeometryCacheHitCount += 1;
        return cached;
    }
    var geometry = edgeLayer._edgeGeometry(edge, nodeById);
    var record = {
        "key": dependencyKey,
        "geometry": geometry,
        "bounds": geometrySceneBounds(edgeLayer, geometry),
        "spatialIndexEntryDirty": false
    };
    edgeLayer._cachedEdgeGeometries[edgeId] = record;
    if (edgeLayer._edgeSpatialIndexIncrementalRefreshActive
            && edgeLayer._edgeSpatialIndex
            && edgeLayer._edgeSpatialIndex.valid
            && !edgeLayer._edgeSpatialIndexDirty) {
        record.spatialIndexEntryDirty = true;
    } else {
        edgeLayer._edgeSpatialIndexDirty = true;
    }
    if (edgeLayer._collectingEdgeSnapshotStats)
        edgeLayer.profileGeometryCacheMissCount += 1;
    return record;
}

function getCachedEdgeGeometry(edgeLayer, edge, nodeById) {
    var record = getCachedEdgeGeometryRecord(edgeLayer, edge, nodeById);
    return record ? record.geometry : null;
}

function expandedVisibleSceneBounds(edgeLayer) {
    var payload = edgeLayer.visibleSceneRectPayload;
    if ((!payload || payload.width === undefined || payload.height === undefined) && edgeLayer.viewBridge)
        payload = edgeLayer.viewBridge.visible_scene_rect_payload;
    if (!payload)
        return null;
    var x = Number(payload.x);
    var y = Number(payload.y);
    var width = Number(payload.width);
    var height = Number(payload.height);
    if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(height) || width <= 0.0 || height <= 0.0)
        return null;
    var viewportTransform = EdgeViewportMath.viewportTransform(edgeLayer);
    var sceneMargin = EdgeViewportMath.screenMarginToScene(edgeLayer.viewportCullMarginPx, viewportTransform);
    return {
        "left": x - sceneMargin,
        "top": y - sceneMargin,
        "right": x + width + sceneMargin,
        "bottom": y + height + sceneMargin
    };
}

function geometrySceneBounds(edgeLayer, geometry) {
    if (!geometry)
        return null;
    if (geometry.route === "pipe")
        return edgeLayer._sceneBoundsForPoints(geometry.pipe_points || []);
    return edgeLayer._sceneBoundsForPoints([
        {"x": geometry.sx, "y": geometry.sy},
        {"x": geometry.c1x, "y": geometry.c1y},
        {"x": geometry.c2x, "y": geometry.c2y},
        {"x": geometry.tx, "y": geometry.ty}
    ]);
}

function edgeCullState(edgeLayer, edge, nodeById, viewportBounds) {
    var record = getCachedEdgeGeometryRecord(edgeLayer, edge, nodeById);
    var geometry = record ? record.geometry : null;
    var sceneBounds = record ? record.bounds : geometrySceneBounds(edgeLayer, geometry);
    var visibleBounds = viewportBounds || expandedVisibleSceneBounds(edgeLayer);
    var culled = sceneBounds && visibleBounds ? !edgeLayer._rectIntersects(sceneBounds, visibleBounds) : false;
    return {"culled": culled, "geometry": culled ? null : geometry, "record": record};
}

function _allEdgeIds(edgeLayer) {
    return edgeLayer._edgeIds || [];
}

function _spatialCellSize(edgeLayer) {
    var margin = Number(edgeLayer.viewportCullMarginPx);
    if (!isFinite(margin) || margin <= 0.0)
        margin = 96.0;
    return Math.max(256.0, margin * 4.0);
}

function _cellRange(bounds, cellSize) {
    if (!bounds)
        return null;
    var left = Number(bounds.left);
    var right = Number(bounds.right);
    var top = Number(bounds.top);
    var bottom = Number(bounds.bottom);
    if (!isFinite(left) || !isFinite(right) || !isFinite(top) || !isFinite(bottom))
        return null;
    return {
        "minX": Math.floor(left / cellSize),
        "maxX": Math.floor(right / cellSize),
        "minY": Math.floor(top / cellSize),
        "maxY": Math.floor(bottom / cellSize)
    };
}

function _cellKey(x, y) {
    return String(x) + ":" + String(y);
}

function _insertSpatialEntry(index, edgeId, bounds, cellSize) {
    var cells = index.cells || {};
    var unboundedEdgeLookup = index.unboundedEdgeLookup || {};
    var cellKeys = [];
    var range = _cellRange(bounds, cellSize);
    if (!range) {
        unboundedEdgeLookup[edgeId] = true;
        return {"cellKeys": cellKeys, "unbounded": true};
    }
    var spanX = range.maxX - range.minX + 1;
    var spanY = range.maxY - range.minY + 1;
    if (spanX * spanY > 256) {
        unboundedEdgeLookup[edgeId] = true;
        return {"cellKeys": cellKeys, "unbounded": true};
    }
    for (var cellX = range.minX; cellX <= range.maxX; cellX++) {
        for (var cellY = range.minY; cellY <= range.maxY; cellY++) {
            var key = _cellKey(cellX, cellY);
            if (!cells[key])
                cells[key] = [];
            cells[key].push(edgeId);
            cellKeys.push(key);
        }
    }
    return {"cellKeys": cellKeys, "unbounded": false};
}

function _removeValue(values, value) {
    if (!values)
        return;
    for (var i = values.length - 1; i >= 0; i--) {
        if (values[i] === value)
            values.splice(i, 1);
    }
}

function _removeSpatialEntry(index, edgeId) {
    if (!index || !index.entriesById)
        return false;
    var existing = index.entriesById[edgeId];
    if (!existing)
        return false;
    var cells = index.cells || {};
    var cellKeys = existing.cellKeys || [];
    for (var i = 0; i < cellKeys.length; i++) {
        var key = cellKeys[i];
        var bucket = cells[key] || [];
        _removeValue(bucket, edgeId);
        if (!bucket.length)
            delete cells[key];
    }
    if (index.unboundedEdgeLookup)
        delete index.unboundedEdgeLookup[edgeId];
    return true;
}

function _updateSpatialIndexEntry(edgeLayer, edge, drawOrderIndex, record) {
    var index = edgeLayer._edgeSpatialIndex || null;
    if (!index || !index.valid || !edge || !edge.edge_id || !record)
        return;
    var edgeId = String(edge.edge_id);
    if (!index.cells)
        index.cells = {};
    if (!index.entriesById)
        index.entriesById = {};
    if (!index.edgeIds)
        index.edgeIds = [];
    if (!index.unboundedEdgeLookup)
        index.unboundedEdgeLookup = {};

    _removeSpatialEntry(index, edgeId);
    if (index.edgeIds.indexOf(edgeId) < 0)
        index.edgeIds.push(edgeId);

    var cellSize = Number(index.cellSize);
    if (!isFinite(cellSize) || cellSize <= 0.0)
        cellSize = _spatialCellSize(edgeLayer);
    var inserted = _insertSpatialEntry(index, edgeId, record.bounds || null, cellSize);
    index.entriesById[edgeId] = {
        "edge": edge,
        "drawOrderIndex": drawOrderIndex,
        "bounds": record.bounds || null,
        "cellKeys": inserted.cellKeys || [],
        "unbounded": Boolean(inserted.unbounded)
    };
    record.spatialIndexEntryDirty = false;
    edgeLayer.profileSpatialIndexDirtyUpdateCount += 1;
    _bumpSpatialIndexGeneration(edgeLayer);
}

function ensureSpatialIndex(edgeLayer, edgesList, nodeById) {
    ensureEdgeTopology(edgeLayer, edgesList);
    var existing = edgeLayer._edgeSpatialIndex || null;
    if (existing && existing.valid && !edgeLayer._edgeSpatialIndexDirty)
        return existing;

    var startedMs = Date.now();
    var cellSize = _spatialCellSize(edgeLayer);
    var cells = {};
    var entriesById = {};
    var unboundedEdgeLookup = {};
    var edgeIds = _allEdgeIds(edgeLayer).slice(0);
    var edgeById = edgeLayer._edgeById || ({});
    var drawOrderById = edgeLayer._edgeDrawOrderById || ({});
    var index = {
        "valid": true,
        "cellSize": cellSize,
        "cells": cells,
        "entriesById": entriesById,
        "edgeIds": edgeIds,
        "unboundedEdgeLookup": unboundedEdgeLookup
    };

    for (var i = 0; i < edgeIds.length; i++) {
        var edgeId = edgeIds[i];
        var edge = edgeById[edgeId];
        if (!edge || !edge.edge_id)
            continue;
        var record = getCachedEdgeGeometryRecord(edgeLayer, edge, nodeById);
        var inserted = _insertSpatialEntry(index, edgeId, record ? record.bounds : null, cellSize);
        entriesById[edgeId] = {
            "edge": edge,
            "drawOrderIndex": drawOrderById[edgeId] !== undefined ? drawOrderById[edgeId] : i,
            "bounds": record ? record.bounds : null,
            "cellKeys": inserted.cellKeys || [],
            "unbounded": Boolean(inserted.unbounded)
        };
    }
    edgeLayer._edgeSpatialIndex = index;
    edgeLayer._edgeSpatialIndexDirty = false;
    _bumpSpatialIndexGeneration(edgeLayer);
    edgeLayer.profileSpatialIndexBuildMs = Math.max(0.0, Date.now() - startedMs);
    edgeLayer.profileSpatialIndexRebuildCount += 1;
    return index;
}

function _recordSpatialIndexQuery(edgeLayer, candidateCount) {
    edgeLayer.profileSpatialIndexQueryCount += 1;
    edgeLayer.profileSpatialIndexCandidateCount += candidateCount;
    edgeLayer.profileLastSpatialIndexCandidateCount = candidateCount;
}

function _lookupFromIds(ids) {
    var lookup = {};
    var source = ids || [];
    for (var i = 0; i < source.length; i++)
        lookup[source[i]] = true;
    return lookup;
}

function _querySpatialIndex(edgeLayer, bounds) {
    var index = edgeLayer._edgeSpatialIndex || null;
    if (!bounds || !index || !index.valid) {
        var fallbackIds = _allEdgeIds(edgeLayer);
        _recordSpatialIndexQuery(edgeLayer, fallbackIds.length);
        var fallbackLookup = _lookupFromIds(fallbackIds);
        return {"ids": fallbackIds, "lookup": fallbackLookup, "usedIndex": false};
    }

    var range = _cellRange(bounds, Number(index.cellSize));
    if (!range) {
        var fallbackIds = _allEdgeIds(edgeLayer);
        _recordSpatialIndexQuery(edgeLayer, fallbackIds.length);
        var fallbackLookup = _lookupFromIds(fallbackIds);
        return {"ids": fallbackIds, "lookup": fallbackLookup, "usedIndex": false};
    }

    var candidateLookup = {};
    for (var cellX = range.minX; cellX <= range.maxX; cellX++) {
        for (var cellY = range.minY; cellY <= range.maxY; cellY++) {
            var bucket = index.cells[_cellKey(cellX, cellY)] || [];
            for (var i = 0; i < bucket.length; i++)
                candidateLookup[bucket[i]] = true;
        }
    }
    var unbounded = index.unboundedEdgeLookup || ({});
    for (var unboundedEdgeId in unbounded) {
        if (Object.prototype.hasOwnProperty.call(unbounded, unboundedEdgeId))
            candidateLookup[unboundedEdgeId] = true;
    }

    var ordered = [];
    var orderedIds = index.edgeIds || [];
    for (var orderedIndex = 0; orderedIndex < orderedIds.length; orderedIndex++) {
        var edgeId = orderedIds[orderedIndex];
        if (candidateLookup[edgeId])
            ordered.push(edgeId);
    }
    _recordSpatialIndexQuery(edgeLayer, ordered.length);
    return {"ids": ordered, "lookup": candidateLookup, "usedIndex": true};
}

function _queryViewportSpatialCandidates(edgeLayer, bounds) {
    var index = edgeLayer._edgeSpatialIndex || null;
    if (!bounds || !index || !index.valid)
        return _querySpatialIndex(edgeLayer, bounds);
    var range = _cellRange(bounds, Number(index.cellSize));
    if (!range)
        return _querySpatialIndex(edgeLayer, bounds);
    var generation = Number(edgeLayer._edgeSpatialIndexGeneration || 0);
    var key = String(range.minX) + ":" + String(range.maxX)
        + ":" + String(range.minY) + ":" + String(range.maxY)
        + ":" + String(isFinite(generation) ? generation : 0);
    if (edgeLayer._viewportSpatialQueryCacheKey === key && edgeLayer._viewportSpatialQueryCache) {
        var cached = edgeLayer._viewportSpatialQueryCache;
        edgeLayer.profileSpatialIndexQueryCacheHitCount += 1;
        edgeLayer.profileSpatialIndexCandidateCount += (cached.ids || []).length;
        edgeLayer.profileLastSpatialIndexCandidateCount = (cached.ids || []).length;
        return cached;
    }
    edgeLayer.profileSpatialIndexQueryCacheMissCount += 1;
    var result = _querySpatialIndex(edgeLayer, bounds);
    if (result && result.usedIndex) {
        edgeLayer._viewportSpatialQueryCacheKey = key;
        edgeLayer._viewportSpatialQueryCache = result;
    }
    return result;
}

function _previousVisibleEdgeLookup(edgeLayer) {
    var lookup = {};
    var snapshots = edgeLayer._visibleEdgeSnapshots || [];
    for (var i = 0; i < snapshots.length; i++) {
        var snapshot = snapshots[i];
        if (snapshot && !snapshot.culled && snapshot.edgeId)
            lookup[String(snapshot.edgeId)] = true;
    }
    return lookup;
}

function _addLookupValue(lookup, value) {
    var normalized = String(value || "").trim();
    if (normalized)
        lookup[normalized] = true;
}

function _addLookupKeys(target, source) {
    for (var key in source || ({})) {
        if (Object.prototype.hasOwnProperty.call(source, key))
            target[key] = true;
    }
}

function _addLookupValues(target, values) {
    var source = values || [];
    for (var i = 0; i < source.length; i++)
        _addLookupValue(target, source[i]);
}

function _lookupSize(lookup) {
    var count = 0;
    for (var key in lookup || ({})) {
        if (Object.prototype.hasOwnProperty.call(lookup, key))
            count += 1;
    }
    return count;
}

function _currentActiveNodeLookup(edgeLayer) {
    var lookup = {};
    var dragNodeLookup = edgeLayer.dragNodeLookup || ({});
    for (var dragNodeId in dragNodeLookup) {
        if (Object.prototype.hasOwnProperty.call(dragNodeLookup, dragNodeId))
            _addLookupValue(lookup, dragNodeId);
    }
    var liveNodeGeometry = edgeLayer.liveNodeGeometry || ({});
    for (var liveNodeId in liveNodeGeometry) {
        if (Object.prototype.hasOwnProperty.call(liveNodeGeometry, liveNodeId))
            _addLookupValue(lookup, liveNodeId);
    }
    var dragConnections = edgeLayer.dragConnectionList ? edgeLayer.dragConnectionList() : [];
    for (var dragIndex = 0; dragIndex < dragConnections.length; dragIndex++) {
        var dragConnection = dragConnections[dragIndex];
        _addLookupValue(lookup, dragConnection.source_node_id);
        _addLookupValue(lookup, dragConnection.target_node_id);
        _addLookupValue(lookup, dragConnection.source_anchor_node_id);
        _addLookupValue(lookup, dragConnection.target_anchor_node_id);
    }
    return lookup;
}

function _incidentEdgeLookup(edgeLayer, nodeLookup) {
    var lookup = {};
    if (!_lookupSize(nodeLookup))
        return lookup;
    var edgeIdsByNodeId = edgeLayer._edgeIdsByNodeId || ({});
    for (var nodeId in nodeLookup) {
        if (!Object.prototype.hasOwnProperty.call(nodeLookup, nodeId) || !nodeLookup[nodeId])
            continue;
        var edgeIds = edgeIdsByNodeId[nodeId] || [];
        for (var i = 0; i < edgeIds.length; i++)
            lookup[edgeIds[i]] = true;
    }
    return lookup;
}

function _dragConnectionSceneBounds(edgeLayer) {
    if (!edgeLayer.dragConnection || !edgeLayer._dragGeometry)
        return null;
    var connections = edgeLayer.dragConnectionList ? edgeLayer.dragConnectionList() : [edgeLayer.dragConnection];
    var bounds = null;
    for (var i = 0; i < connections.length; i++) {
        var current = geometrySceneBounds(edgeLayer, edgeLayer._dragGeometry(connections[i]));
        if (!current)
            continue;
        bounds = bounds
            ? {
                "left": Math.min(bounds.left, current.left),
                "top": Math.min(bounds.top, current.top),
                "right": Math.max(bounds.right, current.right),
                "bottom": Math.max(bounds.bottom, current.bottom)
            }
            : current;
    }
    return bounds;
}

function _dirtyState(edgeLayer) {
    return {
        "topology": Boolean(edgeLayer._edgeTopologyDirty),
        "topologyDelta": Boolean(edgeLayer._edgeTopologyDeltaDirty),
        "nodeGeometry": Boolean(edgeLayer._nodeGeometryDirty),
        "viewport": Boolean(edgeLayer._viewportDirty),
        "selection": Boolean(edgeLayer._selectionDirty),
        "crossingStyle": Boolean(edgeLayer._crossingStyleDirty),
        "theme": Boolean(edgeLayer._themeDirty)
    };
}

function _canUseViewportOnlyRefresh(edgeLayer, dirty) {
    return dirty.viewport
        && !dirty.topology
        && !dirty.nodeGeometry
        && !dirty.selection
        && !dirty.crossingStyle
        && !dirty.theme
        && (edgeLayer._visibleEdgeSnapshots || []).length > 0
        && edgeLayer._visibleEdgeSnapshotById;
}

function _isSelected(edgeLayer, edgeId) {
    return (edgeLayer.selectedEdgeIds || []).indexOf(edgeId) >= 0;
}

function _displayMode(edge) {
    if (!edge || !Boolean(edge.active_data_wire))
        return "default";
    var mode = String((edge.visual_style || {}).display_mode || "default").trim().toLowerCase();
    return mode === "faint" || mode === "hidden" ? mode : "default";
}

function _isSelectedNode(edgeLayer, nodeId) {
    return (edgeLayer.selectedNodeIds || []).indexOf(String(nodeId || "")) >= 0;
}

function _cloneObjectArray(values) {
    var source = values || [];
    var cloned = [];
    for (var i = 0; i < source.length; i++) {
        var entry = source[i];
        if (!entry || typeof entry !== "object") {
            cloned.push(entry);
            continue;
        }
        var copy = {};
        for (var key in entry) {
            if (Object.prototype.hasOwnProperty.call(entry, key))
                copy[key] = entry[key];
        }
        cloned.push(copy);
    }
    return cloned;
}

function _buildSnapshotForEdge(
    edgeLayer,
    canvasLayer,
    labelLayer,
    edge,
    nodeById,
    viewportBounds,
    revision,
    drawOrderIndex,
    previousSnapshotById,
    preserveCrossingMetadata,
    pendingSpatialIndexUpdates
) {
    var edgeId = String(edge.edge_id);
    var cullState = edgeCullState(edgeLayer, edge, nodeById, viewportBounds);
    if (cullState && cullState.record && cullState.record.spatialIndexEntryDirty) {
        pendingSpatialIndexUpdates.push({
            "edge": edge,
            "drawOrderIndex": drawOrderIndex,
            "record": cullState.record
        });
    }
    var geometry = cullState && !cullState.culled ? cullState.geometry : null;
    var labelMode = labelLayer.flowLabelMode(edge);
    var selected = _isSelected(edgeLayer, edgeId);
    var previewed = Boolean(edgeLayer.previewEdgeId && edgeLayer.previewEdgeId === edgeId);
    var replacementPreviewed = (edgeLayer.replacementPreviewEdgeIds || []).indexOf(edgeId) >= 0;
    var activeDataWire = Boolean(edge.active_data_wire);
    var displayMode = _displayMode(edge);
    var sourceNodeSelected = activeDataWire
        && edge.source_active_node !== false
        && _isSelectedNode(edgeLayer, edge.source_node_id);
    var targetNodeSelected = activeDataWire
        && edge.target_active_node !== false
        && _isSelectedNode(edgeLayer, edge.target_node_id);
    var previousSnapshot = previousSnapshotById[edgeId];
    var preserveCurrentCrossingMetadata = preserveCrossingMetadata
        && !selected
        && !previewed
        && !replacementPreviewed
        && previousSnapshot
        && !previousSnapshot.culled
        && previousSnapshot.geometry;
    var preserveLabelAnchor = previousSnapshot
        && previousSnapshot.geometry === geometry
        && previousSnapshot.labelAnchorScene;
    return {
        "revision": revision,
        "edgeId": edgeId,
        "edgeData": edge,
        "culled": cullState ? Boolean(cullState.culled) : false,
        "geometry": geometry,
        "selected": selected,
        "previewed": previewed,
        "replacementPreviewed": replacementPreviewed,
        "activeDataWire": activeDataWire,
        "displayMode": displayMode,
        "hiddenUnrevealed": activeDataWire
            && displayMode === "hidden"
            && !Boolean(edgeLayer.wireSelectionModeHeld)
            && !selected
            && !previewed
            && !replacementPreviewed,
        "sourceNodeSelected": sourceNodeSelected,
        "targetNodeSelected": targetNodeSelected,
        "flowEdge": EdgePaintPolicy.edgeIsFlow(edge),
        "labelText": labelLayer.edgeLabelText(edge),
        "labelMode": labelMode,
        "drawOrderIndex": drawOrderIndex,
        "crossingBreaks": preserveCurrentCrossingMetadata
            ? _cloneObjectArray(previousSnapshot.crossingBreaks)
            : [],
        "crossingSamplePoints": preserveCurrentCrossingMetadata
            ? _cloneObjectArray(previousSnapshot.crossingSamplePoints)
            : [],
        "labelAnchorScene": labelMode !== "hidden" && geometry
            ? (preserveLabelAnchor
                ? previousSnapshot.labelAnchorScene
                : labelLayer.flowLabelAnchorScene(geometry))
            : null
    };
}

function _visibleEdgeSetKey(snapshots, wireSelectionModeHeld) {
    var visible = [];
    for (var i = 0; i < snapshots.length; i++) {
        var snapshot = snapshots[i];
        if (snapshot && !snapshot.culled && snapshot.edgeId)
            visible.push(String(snapshot.edgeId));
    }
    visible.sort();
    return (wireSelectionModeHeld ? "w|" : "p|") + visible.join("|");
}

function _lookupKeys(lookup) {
    var keys = [];
    for (var key in lookup || ({})) {
        if (Object.prototype.hasOwnProperty.call(lookup, key) && lookup[key])
            keys.push(key);
    }
    return keys;
}

function _orderedLookupKeys(edgeLayer, lookup) {
    var keys = _lookupKeys(lookup);
    var drawOrderById = edgeLayer._edgeDrawOrderById || ({});
    keys.sort(function(a, b) {
        var left = Number(drawOrderById[a]);
        var right = Number(drawOrderById[b]);
        if (!isFinite(left))
            left = 9007199254740991;
        if (!isFinite(right))
            right = 9007199254740991;
        if (left === right)
            return String(a) < String(b) ? -1 : (String(a) > String(b) ? 1 : 0);
        return left - right;
    });
    return keys;
}

function buildVisibleEdgeSnapshots(edgeLayer, canvasLayer, labelLayer, revision) {
    var drawSnapshots = [];
    var edgesList = edgeLayer.edges || [];
    ensureEdgeTopology(edgeLayer, edgesList);
    var edgeById = edgeLayer._edgeById || ({});
    var edgeIds = _allEdgeIds(edgeLayer);
    var drawOrderById = edgeLayer._edgeDrawOrderById || ({});
    var nodeById = getNodeMap(edgeLayer);
    var viewportBounds = expandedVisibleSceneBounds(edgeLayer);
    var viewportTransform = EdgeViewportMath.viewportTransform(edgeLayer);
    var previousSnapshotById = edgeLayer._visibleEdgeSnapshotById || ({});
    var previousVisibleLookup = _previousVisibleEdgeLookup(edgeLayer);
    var dirty = _dirtyState(edgeLayer);
    var viewportOnlyRefresh = _canUseViewportOnlyRefresh(edgeLayer, dirty);
    var activeNodeRefresh = dirty.nodeGeometry
        && Boolean(edgeLayer._activeNodeGeometryDirty)
        && !dirty.topology;
    var reuseCrossingMetadata = Boolean(
        canvasLayer
        && canvasLayer.shouldReuseCrossingMetadata
        && canvasLayer.shouldReuseCrossingMetadata()
        && !dirty.topology
        && !dirty.nodeGeometry
        && !dirty.crossingStyle
    );

    edgeLayer.profileTotalEdgeCount = edgeIds.length;
    var currentActiveNodeLookup = _currentActiveNodeLookup(edgeLayer);
    var activeNodeLookup = {};
    _addLookupKeys(activeNodeLookup, currentActiveNodeLookup);
    _addLookupKeys(activeNodeLookup, edgeLayer._lastActiveGeometryNodeLookup || ({}));
    edgeLayer._activeGeometryDependencyNodeLookup = currentActiveNodeLookup;
    ensureSpatialIndex(edgeLayer, edgesList, nodeById);
    var incidentActiveEdgeLookup = _incidentEdgeLookup(edgeLayer, activeNodeLookup);
    var activeIncidentOnlyRefresh = activeNodeRefresh
        && !dirty.viewport
        && !dirty.selection
        && !dirty.crossingStyle
        && !dirty.theme;
    var topologyDeltaOnlyRefresh = dirty.topologyDelta
        && !dirty.nodeGeometry
        && !dirty.viewport
        && !dirty.selection
        && !dirty.crossingStyle
        && !dirty.theme;
    var candidateQuery = viewportBounds
        ? _queryViewportSpatialCandidates(edgeLayer, viewportBounds)
        : _querySpatialIndex(edgeLayer, null);
    var paintLookup = {};
    _addLookupValues(paintLookup, candidateQuery.ids || []);
    _addLookupKeys(paintLookup, previousVisibleLookup);
    _addLookupValues(paintLookup, edgeLayer.selectedEdgeIds || []);
    _addLookupValue(paintLookup, edgeLayer.previewEdgeId);
    _addLookupValues(paintLookup, edgeLayer.replacementPreviewEdgeIds || []);
    _addLookupKeys(paintLookup, incidentActiveEdgeLookup);
    if (dirty.topologyDelta)
        _addLookupKeys(paintLookup, edgeLayer._edgeTopologyDirtyEdgeLookup || ({}));

    var dragConnectionBounds = _dragConnectionSceneBounds(edgeLayer);
    if (dragConnectionBounds) {
        var dragConnectionQuery = _querySpatialIndex(edgeLayer, dragConnectionBounds);
        _addLookupValues(paintLookup, dragConnectionQuery.ids || []);
    }

    var refreshLookup = {};
    var refreshAll = dirty.topology || (dirty.nodeGeometry && !activeNodeRefresh);
    var snapshotById = refreshAll ? ({}) : previousSnapshotById;
    if (!refreshAll) {
        if (activeIncidentOnlyRefresh) {
            _addLookupKeys(refreshLookup, incidentActiveEdgeLookup);
        } else if (topologyDeltaOnlyRefresh) {
            _addLookupKeys(refreshLookup, edgeLayer._edgeTopologyDirtyEdgeLookup || ({}));
        } else {
            if (dirty.topologyDelta)
                _addLookupKeys(refreshLookup, edgeLayer._edgeTopologyDirtyEdgeLookup || ({}));
            _addLookupKeys(refreshLookup, paintLookup);
            _addLookupKeys(refreshLookup, previousVisibleLookup);
        }
    }

    var refreshIds = refreshAll ? edgeIds : _orderedLookupKeys(edgeLayer, refreshLookup);
    edgeLayer.profileLastRefreshEdgeCount = refreshIds.length;
    edgeLayer.profileLastIncidentEdgeRefreshCount = activeIncidentOnlyRefresh
        ? _lookupSize(incidentActiveEdgeLookup)
        : 0;
    if (activeIncidentOnlyRefresh)
        edgeLayer.profileIncidentEdgeRefreshCount += 1;
    edgeLayer._edgeSpatialIndexIncrementalRefreshActive = true;
    var pendingSpatialIndexUpdates = [];
    for (var i = 0; i < refreshIds.length; i++) {
        var edgeId = refreshIds[i];
        var edge = edgeById[edgeId];
        if (!edge)
            continue;
        var snapshot = _buildSnapshotForEdge(
            edgeLayer,
            canvasLayer,
            labelLayer,
            edge,
            nodeById,
            viewportBounds,
            revision,
            drawOrderById[edgeId] !== undefined ? drawOrderById[edgeId] : i,
            previousSnapshotById,
            reuseCrossingMetadata,
            pendingSpatialIndexUpdates
        );
        snapshotById[edgeId] = snapshot;
    }
    for (var updateIndex = 0; updateIndex < pendingSpatialIndexUpdates.length; updateIndex++) {
        var update = pendingSpatialIndexUpdates[updateIndex];
        _updateSpatialIndexEntry(edgeLayer, update.edge, update.drawOrderIndex, update.record);
    }
    edgeLayer._edgeSpatialIndexIncrementalRefreshActive = false;

    var paintIds = _orderedLookupKeys(edgeLayer, paintLookup);
    for (i = 0; i < paintIds.length; i++) {
        var paintEdgeId = paintIds[i];
        var paintSnapshot = snapshotById[paintEdgeId];
        if (paintSnapshot && !paintSnapshot.culled && paintSnapshot.geometry)
            drawSnapshots.push(paintSnapshot);
    }
    if (viewportOnlyRefresh) {
        for (i = 0; i < drawSnapshots.length; i++) {
            var snapshot = drawSnapshots[i];
            if (snapshot)
                snapshot.revision = revision;
        }
    }

    var visibleSetKey = _visibleEdgeSetKey(drawSnapshots, edgeLayer.wireSelectionModeHeld);
    var visibleSetChanged = visibleSetKey !== edgeLayer._lastVisibleEdgeSetKey;
    var canPreserveCrossings = reuseCrossingMetadata && !visibleSetChanged;
    if (canPreserveCrossings && canvasLayer.orderSnapshotsForDraw)
        drawSnapshots = canvasLayer.orderSnapshotsForDraw(drawSnapshots, true);
    else
        drawSnapshots = canvasLayer.applyCrossingMetadata(drawSnapshots, viewportTransform);

    edgeLayer._lastVisibleEdgeSetKey = _visibleEdgeSetKey(drawSnapshots, edgeLayer.wireSelectionModeHeld);
    var visibleCount = 0;
    for (i = 0; i < drawSnapshots.length; i++) {
        if (drawSnapshots[i] && !drawSnapshots[i].culled)
            visibleCount += 1;
    }
    var candidateEdgeCount = Math.min(edgeLayer.profileTotalEdgeCount, _lookupSize(paintLookup));
    edgeLayer.profileCandidateEdgeCount = candidateEdgeCount;
    edgeLayer.profileLastCandidateEdgeCount = edgeLayer.profileCandidateEdgeCount;
    edgeLayer.profileLastSkippedEdgeCount = Math.max(
        0,
        edgeLayer.profileTotalEdgeCount - edgeLayer.profileCandidateEdgeCount
    );
    edgeLayer.profileVisibleEdgeCount = visibleCount;
    edgeLayer.profileLastVisibleEdgeSnapshotCount = visibleCount;
    edgeLayer.profileLastVisibleEdgeCount = visibleCount;
    edgeLayer._lastActiveGeometryNodeLookup = currentActiveNodeLookup;
    edgeLayer._activeNodeGeometryDirty = false;
    return {"snapshots": drawSnapshots, "snapshotById": snapshotById};
}

function refreshVisibleEdgeSnapshots(edgeLayer, canvasLayer, labelLayer) {
    edgeLayer.profileSpatialIndexBuildMs = 0.0;
    edgeLayer.profileSpatialIndexDirtyUpdateCount = 0;
    edgeLayer.profileSpatialIndexQueryCount = 0;
    edgeLayer.profileSpatialIndexQueryCacheHitCount = 0;
    edgeLayer.profileSpatialIndexQueryCacheMissCount = 0;
    edgeLayer.profileSpatialIndexCandidateCount = 0;
    edgeLayer.profileLastSpatialIndexCandidateCount = 0;
    var nextRevision = edgeLayer._visibleEdgeSnapshotRevision + 1;
    edgeLayer._collectingEdgeSnapshotStats = true;
    edgeLayer.profileGeometryCacheHitCount = 0;
    edgeLayer.profileGeometryCacheMissCount = 0;
    var model = buildVisibleEdgeSnapshots(edgeLayer, canvasLayer, labelLayer, nextRevision);
    edgeLayer._collectingEdgeSnapshotStats = false;
    edgeLayer._visibleEdgeSnapshots = model.snapshots;
    edgeLayer._visibleEdgeSnapshotById = model.snapshotById;
    edgeLayer._visibleEdgeSnapshotRevision = nextRevision;
    edgeLayer._edgeTopologyDirty = false;
    edgeLayer._edgeTopologyDeltaDirty = false;
    edgeLayer._edgeTopologyDirtyEdgeLookup = ({});
    edgeLayer._edgeTopologyRemovedEdgeLookup = ({});
    edgeLayer._nodeGeometryDirty = false;
    edgeLayer._viewportDirty = false;
    edgeLayer._selectionDirty = false;
    edgeLayer._crossingStyleDirty = false;
    edgeLayer._themeDirty = false;
}

function visibleEdgeSnapshot(edgeLayer, edgeId) {
    var normalized = String(edgeId || "");
    if (!normalized)
        return null;
    return edgeLayer._visibleEdgeSnapshotById[normalized] || null;
}

function _edgeDistanceAtScreen(geometry, screenX, screenY, viewportTransform) {
    if (!geometry)
        return Number.POSITIVE_INFINITY;
    var sceneX = EdgeViewportMath.screenToSceneX(screenX, viewportTransform);
    var sceneY = EdgeViewportMath.screenToSceneY(screenY, viewportTransform);
    if (geometry.route === "pipe")
        return EdgeMath.distancePolyline(sceneX, sceneY, geometry.pipe_points || []);
    return EdgeMath.distanceBezier(
        sceneX,
        sceneY,
        geometry.sx,
        geometry.sy,
        geometry.c1x,
        geometry.c1y,
        geometry.c2x,
        geometry.c2y,
        geometry.tx,
        geometry.ty,
        28
    );
}

function _hiddenEndpointHitAtScreen(geometry, screenX, screenY, viewportTransform, threshold) {
    var sceneX = EdgeViewportMath.screenToSceneX(screenX, viewportTransform);
    var sceneY = EdgeViewportMath.screenToSceneY(screenY, viewportTransform);
    var sceneStep = EdgeViewportMath.screenLengthToScene(4.0, viewportTransform);
    var endpointSpan = EdgeViewportMath.screenLengthToScene(26.0, viewportTransform);
    var metrics = EdgeMath.polylineMetrics(EdgeMath.sampleGeometryPolyline(geometry, sceneStep));
    for (var i = 0; i < (metrics.segments || []).length; i++) {
        var segment = metrics.segments[i];
        if (segment.startDistance > endpointSpan
                && segment.endDistance < metrics.totalLength - endpointSpan) {
            continue;
        }
        if (EdgeMath.distanceSegment(
                sceneX,
                sceneY,
                segment.a.x,
                segment.a.y,
                segment.b.x,
                segment.b.y
            ) <= threshold) {
            return true;
        }
    }
    return false;
}

function edgeAtScreen(edgeLayer, canvasLayer, labelLayer, screenX, screenY) {
    var snapshots = edgeLayer._visibleEdgeSnapshots || [];
    var snapshotById = edgeLayer._visibleEdgeSnapshotById || ({});
    if ((!snapshots.length || !_lookupSize(snapshotById)) && (edgeLayer.edges || []).length) {
        refreshVisibleEdgeSnapshots(edgeLayer, canvasLayer, labelLayer);
        snapshots = edgeLayer._visibleEdgeSnapshots || [];
        snapshotById = edgeLayer._visibleEdgeSnapshotById || ({});
    }
    if (!_lookupSize(snapshotById))
        return "";
    ensureSpatialIndex(edgeLayer, edgeLayer.edges || [], getNodeMap(edgeLayer));
    var viewportTransform = EdgeViewportMath.viewportTransform(edgeLayer);
    var threshold = EdgeViewportMath.screenLengthToScene(8.0, viewportTransform);
    var sceneX = EdgeViewportMath.screenToSceneX(screenX, viewportTransform);
    var sceneY = EdgeViewportMath.screenToSceneY(screenY, viewportTransform);
    var hitQuery = _querySpatialIndex(
        edgeLayer,
        {
            "left": sceneX - threshold,
            "top": sceneY - threshold,
            "right": sceneX + threshold,
            "bottom": sceneY + threshold
        }
    );
    var hitSnapshots = [];
    var hitIds = hitQuery.ids || [];
    for (var hitIndex = 0; hitIndex < hitIds.length; hitIndex++) {
        var hitSnapshot = snapshotById[hitIds[hitIndex]];
        if (hitSnapshot)
            hitSnapshots.push(hitSnapshot);
    }
    hitSnapshots.sort(function(a, b) {
        return Number(a.drawOrderIndex || 0) - Number(b.drawOrderIndex || 0);
    });
    var bestId = "";
    var bestDistance = Number.POSITIVE_INFINITY;
    for (var i = hitSnapshots.length - 1; i >= 0; i--) {
        var snapshot = hitSnapshots[i];
        if (!snapshot || snapshot.culled || !snapshot.geometry)
            continue;
        if (snapshot.hiddenUnrevealed) {
            if (_hiddenEndpointHitAtScreen(
                    snapshot.geometry,
                    screenX,
                    screenY,
                    viewportTransform,
                    threshold
                )) {
                return snapshot.edgeId;
            }
            continue;
        }
        var distance = _edgeDistanceAtScreen(snapshot.geometry, screenX, screenY, viewportTransform);
        if (distance < bestDistance && distance <= threshold) {
            bestDistance = distance;
            bestId = snapshot.edgeId;
        }
    }
    return bestId;
}

function _normalizedRect(x, y, width, height) {
    var left = Number(x);
    var top = Number(y);
    var right = left + Number(width);
    var bottom = top + Number(height);
    if (![left, top, right, bottom].every(isFinite))
        return null;
    return {
        "left": Math.min(left, right),
        "top": Math.min(top, bottom),
        "right": Math.max(left, right),
        "bottom": Math.max(top, bottom)
    };
}

function _pointInRect(point, rect) {
    return point && rect
        && Number(point.x) >= rect.left && Number(point.x) <= rect.right
        && Number(point.y) >= rect.top && Number(point.y) <= rect.bottom;
}

function _segmentIntersectsRect(a, b, rect) {
    if (_pointInRect(a, rect) || _pointInRect(b, rect))
        return true;
    if (!EdgeMath.rectsIntersect({
        "left": Math.min(Number(a.x), Number(b.x)),
        "top": Math.min(Number(a.y), Number(b.y)),
        "right": Math.max(Number(a.x), Number(b.x)),
        "bottom": Math.max(Number(a.y), Number(b.y))
    }, rect)) {
        return false;
    }
    var topLeft = {"x": rect.left, "y": rect.top};
    var topRight = {"x": rect.right, "y": rect.top};
    var bottomRight = {"x": rect.right, "y": rect.bottom};
    var bottomLeft = {"x": rect.left, "y": rect.bottom};
    return Boolean(
        EdgeMath.segmentIntersection(a, b, topLeft, topRight)
        || EdgeMath.segmentIntersection(a, b, topRight, bottomRight)
        || EdgeMath.segmentIntersection(a, b, bottomRight, bottomLeft)
        || EdgeMath.segmentIntersection(a, b, bottomLeft, topLeft)
    );
}

function _geometryIntersectsRect(geometry, rect, sceneStep) {
    var points = EdgeMath.sampleGeometryPolyline(geometry, sceneStep);
    for (var i = 0; i < points.length; i++) {
        if (_pointInRect(points[i], rect))
            return true;
        if (i > 0 && _segmentIntersectsRect(points[i - 1], points[i], rect))
            return true;
    }
    return false;
}

function edgeIdsIntersectingSceneRect(edgeLayer, canvasLayer, labelLayer, x, y, width, height) {
    var rect = _normalizedRect(x, y, width, height);
    if (!rect)
        return [];
    if (!(edgeLayer._visibleEdgeSnapshots || []).length && (edgeLayer.edges || []).length)
        refreshVisibleEdgeSnapshots(edgeLayer, canvasLayer, labelLayer);
    ensureSpatialIndex(edgeLayer, edgeLayer.edges || [], getNodeMap(edgeLayer));
    var candidateIds = (_querySpatialIndex(edgeLayer, rect).ids || []).slice(0);
    var snapshotById = edgeLayer._visibleEdgeSnapshotById || ({});
    var nodeById = getNodeMap(edgeLayer);
    var step = EdgeViewportMath.screenLengthToScene(6.0, EdgeViewportMath.viewportTransform(edgeLayer));
    var hits = [];
    for (var i = 0; i < candidateIds.length; i++) {
        var edgeId = candidateIds[i];
        var snapshot = snapshotById[edgeId];
        var geometry = snapshot && snapshot.geometry;
        if (!geometry) {
            var edge = (edgeLayer._edgeById || {})[edgeId];
            var record = edge ? getCachedEdgeGeometryRecord(edgeLayer, edge, nodeById) : null;
            geometry = record ? record.geometry : null;
        }
        if (geometry && _geometryIntersectsRect(geometry, rect, step))
            hits.push(edgeId);
    }
    return hits;
}

function edgeIdsIntersectingScreenRect(edgeLayer, canvasLayer, labelLayer, x, y, width, height) {
    var screenRect = _normalizedRect(x, y, width, height);
    if (!screenRect)
        return [];
    var viewport = EdgeViewportMath.viewportTransform(edgeLayer);
    var sceneLeft = EdgeViewportMath.screenToSceneX(screenRect.left, viewport);
    var sceneTop = EdgeViewportMath.screenToSceneY(screenRect.top, viewport);
    var sceneRight = EdgeViewportMath.screenToSceneX(screenRect.right, viewport);
    var sceneBottom = EdgeViewportMath.screenToSceneY(screenRect.bottom, viewport);
    return edgeIdsIntersectingSceneRect(
        edgeLayer,
        canvasLayer,
        labelLayer,
        sceneLeft,
        sceneTop,
        sceneRight - sceneLeft,
        sceneBottom - sceneTop
    );
}
