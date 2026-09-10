import QtQuick 2.15
import QtQml 2.15
import "EdgeMath.js" as EdgeMath
import "EdgePaintPolicy.js" as EdgePaintPolicy
import "EdgeSnapshotCache.js" as EdgeSnapshotCache
import "EdgeViewportMath.js" as EdgeViewportMath
import "GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

Item {
    id: root
    readonly property var edgePalette: typeof graphThemeBridge !== "undefined"
        ? graphThemeBridge.edge_palette
        : ({})
    readonly property var shellPalette: typeof themeBridge !== "undefined"
        ? themeBridge.palette
        : ({})
    readonly property var portKindPalette: typeof graphThemeBridge !== "undefined"
        ? graphThemeBridge.port_kind_palette
        : ({})
    property var viewBridge: null
    property var sceneBridge: null
    property var edges: []
    property var edgeTopologyDelta: sceneBridge && sceneBridge.edge_delta_payload !== undefined
        ? (sceneBridge.edge_delta_payload || ({}))
        : ({})
    property var nodeDeltaPayload: ({})
    property var nodes: []
    property var dragNodeLookup: ({})
    property real dragDx: 0.0
    property real dragDy: 0.0
    property int dragRevision: 0
    property var liveNodeGeometry: ({})
    property bool _settingsGroupGeometryActive: false
    property var selectedNodeIds: sceneBridge ? (sceneBridge.selected_node_ids || []) : []
    property var selectedEdgeIds: []
    property var visibleSceneRectPayload: ({})
    property string previewEdgeId: ""
    property var replacementPreviewEdgeIds: []
    property var dragConnection: null
    property var outputPreviewLookup: ({})
    property string edgeCrossingStyle: "none"
    property string edgeRendererPreference: "retained_qml"
    property bool viewportInteractionActive: false
    property bool inputEnabled: true
    property bool wireSelectionModeHeld: false
    property var frameScheduler: null
    property int _redrawRequestCount: 0
    property bool _viewStateRedrawDirty: false
    property bool _scheduledRedrawDirty: false
    property var _nodePayloadDeltaById: ({})
    property real profileLastSnapshotBuildMs: 0.0
    property real profileSnapshotRefreshMs: 0.0
    property int profileSnapshotRefreshCount: 0
    property int profileTotalEdgeCount: 0
    property int profileCandidateEdgeCount: 0
    property int profileLastCandidateEdgeCount: 0
    property int profileLastVisibleEdgeCount: 0
    property int profileVisibleEdgeCount: 0
    property int profileLastVisibleEdgeSnapshotCount: 0
    property int profileLastSkippedEdgeCount: 0
    property int profileLastRefreshEdgeCount: 0
    property int profileIncidentEdgeRefreshCount: 0
    property int profileLastIncidentEdgeRefreshCount: 0
    property int profileGeometryCacheHitCount: 0
    property int profileGeometryCacheMissCount: 0
    property int profileEdgeTopologyRebuildCount: 0
    property int profileEdgeTopologyEntryUpdateCount: 0
    property real profileSpatialIndexBuildMs: 0.0
    property int profileSpatialIndexRebuildCount: 0
    property int profileSpatialIndexDirtyUpdateCount: 0
    property int profileSpatialIndexQueryCount: 0
    property int profileSpatialIndexQueryCacheHitCount: 0
    property int profileSpatialIndexQueryCacheMissCount: 0
    property int profileSpatialIndexCandidateCount: 0
    property int profileLastSpatialIndexCandidateCount: 0
    readonly property int profileRetainedModelEntryUpdateCount: edgeRetainedLayer.profileRetainedModelEntryUpdateCount
    readonly property int profileRetainedModelEntrySkipCount: edgeRetainedLayer.profileRetainedModelEntrySkipCount
    readonly property int profileFlowLabelModelSyncSkipCount: flowLabelLayer.profileFlowLabelModelSyncSkipCount
    readonly property real profileLastEdgePaintMs: root.edgeRendererKind === "retained_qml"
        ? edgeRetainedLayer.profileLastPaintMs
        : (root.edgeRendererKind === "native_scenegraph"
            ? edgeScenegraphLayer.profileLastPaintMs
            : edgeCanvasLayer.profileLastPaintMs)
    readonly property int profileEdgePaintCount: root.edgeRendererKind === "retained_qml"
        ? edgeRetainedLayer.profilePaintCount
        : (root.edgeRendererKind === "native_scenegraph"
            ? edgeScenegraphLayer.profilePaintCount
            : edgeCanvasLayer.profilePaintCount)
    readonly property string edgeRendererKind: root._activeEdgeRendererKind
    readonly property string edgeRendererRequestedKind: root._normalizeEdgeRendererKind(root.edgeRendererPreference)
    readonly property bool edgeRendererCanvasFallbackActive: root.edgeRendererKind !== root.edgeRendererRequestedKind
    readonly property string edgeRendererFallbackReason: root._edgeRendererFallbackReason
    readonly property var activeEdgePaintDiagnosticsByEdgeId: root.edgeRendererKind === "retained_qml"
        ? edgeRetainedLayer._paintDiagnosticsByEdgeId
        : edgeCanvasLayer._paintDiagnosticsByEdgeId
    property string _activeEdgeRendererKind: "canvas"
    property string _edgeRendererFallbackReason: ""
    property real viewportCullMarginPx: 96.0
    property var _cachedBaseNodeMap: null
    property var _cachedNodeMap: null
    property var _cachedEdgeGeometries: ({})
    property var _edgeById: ({})
    property var _edgeIds: []
    property var _edgeDrawOrderById: ({})
    property var _edgeIdsByNodeId: ({})
    property var _edgeDependencyNodeIdsById: ({})
    property int _edgeTopologyCacheRevision: -1
    property var _edgeSpatialIndex: ({})
    property bool _edgeSpatialIndexDirty: true
    property int _edgeSpatialIndexGeneration: 0
    property string _viewportSpatialQueryCacheKey: ""
    property var _viewportSpatialQueryCache: null
    property bool _edgeSpatialIndexIncrementalRefreshActive: false
    property var _visibleEdgeSnapshots: []
    property var _visibleEdgeSnapshotById: ({})
    property int _visibleEdgeSnapshotRevision: 0
    property string _lastVisibleEdgeSetKey: ""
    property int _edgeTopologyRevision: 0
    property int _nodeGeometryRevision: 0
    property int _activeNodeGeometryRevision: 0
    property int _viewportRevision: 0
    property int _selectionRevision: 0
    property int _crossingStyleRevision: 0
    property int _themeRevision: 0
    property bool _edgeTopologyDirty: true
    property bool _edgeTopologyDeltaDirty: false
    property var _edgeTopologyDirtyEdgeLookup: ({})
    property var _edgeTopologyRemovedEdgeLookup: ({})
    property bool _nodeGeometryDirty: true
    property bool _viewportDirty: true
    property bool _selectionDirty: true
    property bool _crossingStyleDirty: true
    property bool _themeDirty: true
    property bool _activeNodeGeometryDirty: false
    property var _lastActiveGeometryNodeLookup: ({})
    property var _activeGeometryDependencyNodeLookup: ({})
    property bool _collectingEdgeSnapshotStats: false
    property bool _structuralEdgePayloadSyncActive: false
    readonly property color selectedStrokeColor: edgePalette.selected_stroke || "#f0f4fb"
    readonly property color activeSelectedStrokeColor: "#75B4E7"
    readonly property color previewStrokeColor: edgePalette.preview_stroke || "#60CDFF"
    readonly property color validDragStrokeColor: edgePalette.valid_drag_stroke || "#60CDFF"
    readonly property color invalidDragStrokeColor: edgePalette.invalid_drag_stroke || "#d0d5de"
    readonly property color fallbackStrokeColor: portKindPalette.data || "#7AA8FF"
    readonly property color canvasBackgroundColor: shellPalette.canvas_bg || "#151821"
    readonly property color activeDefaultStrokeColor: root.neutralActiveStrokeColor(root.canvasBackgroundColor)
    readonly property color inactiveStrokeColor: shellPalette.muted_fg || "#7f8796"
    readonly property color dangerStrokeColor: "#FF543E"
    readonly property color flowDefaultStrokeColor: shellPalette.muted_fg || invalidDragStrokeColor
    readonly property color flowDefaultLabelTextColor: shellPalette.panel_title_fg || selectedStrokeColor
    readonly property color flowDefaultLabelBackgroundColor: shellPalette.panel_bg || "#1b1d22"
    readonly property color flowDefaultLabelBorderColor: shellPalette.border || "#3a3d45"
    property real flowLabelHideZoomThreshold: 0.55
    property real flowLabelSimplifyZoomThreshold: 0.85
    property real edgeCrossingGapScreenPx: 14.0
    property real edgeCrossingAnchorGuardScreenPx: 18.0
    property real edgeCrossingMergeScreenPx: 6.0
    property real edgeCrossingSampleStepScreenPx: 10.0
    signal edgeClicked(string edgeId, bool additive)
    signal edgeDoubleClicked(string edgeId)
    signal edgeContextRequested(string edgeId, real screenX, real screenY)
    function neutralActiveStrokeColor(canvasColor) {
        var color = canvasColor || root.canvasBackgroundColor;
        var luminance = Number(color.r) * 0.299
            + Number(color.g) * 0.587
            + Number(color.b) * 0.114;
        return luminance < 0.5 ? "#A7ADB2" : "#6B7277";
    }
    function requestRedraw() {
        if (root.frameScheduler && root.frameScheduler.requestEdgeRedraw) {
            root.markScheduledRedrawDirty();
            root.frameScheduler.requestEdgeRedraw();
            return false;
        }
        return root.requestImmediateRedraw();
    }
    function requestImmediateRedraw() {
        root._scheduledRedrawDirty = false;
        var startedMs = Date.now();
        root._viewStateRedrawDirty = false;
        EdgeSnapshotCache.refreshVisibleEdgeSnapshots(root, edgeCanvasLayer, flowLabelLayer);
        var snapshots = root._visibleEdgeSnapshots || [];
        var visibleEdgeCount = 0;
        for (var i = 0; i < snapshots.length; i++) {
            var snapshot = snapshots[i];
            if (!snapshot || Boolean(snapshot.culled))
                continue;
            visibleEdgeCount += 1;
        }
        root.profileLastSnapshotBuildMs = Math.max(0.0, Date.now() - startedMs);
        root.profileSnapshotRefreshMs = root.profileLastSnapshotBuildMs;
        root.profileSnapshotRefreshCount += 1;
        root.profileLastVisibleEdgeCount = visibleEdgeCount;
        root.profileVisibleEdgeCount = visibleEdgeCount;
        root.profileLastVisibleEdgeSnapshotCount = visibleEdgeCount;
        root._redrawRequestCount += 1;
        root._dispatchEdgeRenderer(snapshots);
        return true;
    }
    function _normalizeEdgeRendererKind(value) {
        var normalized = String(value || "retained_qml").trim().toLowerCase();
        if (normalized === "canvas" || normalized === "retained_qml" || normalized === "native_scenegraph")
            return normalized;
        return "retained_qml";
    }
    function _retainedFallbackReason(snapshots) {
        if (!edgeRetainedLayer.rendererSupported)
            return "retained_qml_renderer_unavailable";
        if (root.dragConnectionList().length > 0)
            return "wire_drag_preview_uses_canvas_fallback";
        if (!edgeRetainedLayer.canRenderSnapshots(snapshots))
            return "retained_qml_visible_set_requires_canvas_fallback";
        return "";
    }
    function _rendererFallbackReasonFor(requestedKind, snapshots) {
        if (requestedKind === "canvas")
            return "";
        if (requestedKind === "native_scenegraph")
            return edgeScenegraphLayer.rendererSupported
                ? ""
                : edgeScenegraphLayer.fallbackReason;
        return root._retainedFallbackReason(snapshots);
    }
    function _dispatchEdgeRenderer(snapshots) {
        var requestedKind = root.edgeRendererRequestedKind;
        var fallbackReason = root._rendererFallbackReasonFor(requestedKind, snapshots);
        var activeKind = fallbackReason ? "canvas" : requestedKind;
        root._activeEdgeRendererKind = activeKind;
        root._edgeRendererFallbackReason = fallbackReason;
        edgeCanvasLayer.visible = activeKind === "canvas";
        edgeRetainedLayer.visible = activeKind === "retained_qml";
        edgeScenegraphLayer.visible = activeKind === "native_scenegraph";
        if (activeKind === "retained_qml") {
            edgeCanvasLayer.clearCanvasPaintDiagnostics();
            edgeRetainedLayer.requestRetainedPaint();
        } else if (activeKind === "native_scenegraph") {
            edgeRetainedLayer.clearRetainedPaint();
            edgeCanvasLayer.clearCanvasPaintDiagnostics();
            edgeScenegraphLayer.requestScenegraphPaint();
        } else {
            edgeRetainedLayer.clearRetainedPaint();
            edgeCanvasLayer.requestCanvasPaint();
        }
    }
    function markEdgeTopologyDirty(deltaPayload) {
        root._edgeTopologyRevision += 1;
        if (EdgeSnapshotCache.applyTopologyDeltaCache(root, deltaPayload || root.edgeTopologyDelta))
            return;
        root._edgeTopologyDirty = true;
        root._edgeTopologyDeltaDirty = false;
        root._edgeTopologyDirtyEdgeLookup = ({});
        root._edgeTopologyRemovedEdgeLookup = ({});
        EdgeSnapshotCache.invalidateTopologyCache(root);
        EdgeSnapshotCache.invalidateGeometryCache(root);
    }
    function applyStructuralEdgePayloadDelta(edgePayload, deltaPayload) {
        root._structuralEdgePayloadSyncActive = true;
        try {
            root.edges = edgePayload || [];
        } finally {
            root._structuralEdgePayloadSyncActive = false;
        }
        root.markEdgeTopologyDirty(deltaPayload || ({}));
        root.requestRedraw();
    }
    function replaceEdgePayload(edgePayload) {
        root._structuralEdgePayloadSyncActive = true;
        try {
            root.edges = edgePayload || [];
        } finally {
            root._structuralEdgePayloadSyncActive = false;
        }
        root.markEdgeTopologyDirty({});
        root.requestRedraw();
    }
    function markNodeGeometryDirty() {
        root._nodeGeometryRevision += 1;
        root._nodeGeometryDirty = true;
        root._activeNodeGeometryDirty = false;
        EdgeSnapshotCache.invalidateGeometryCache(root);
    }
    function markActiveNodeGeometryDirty() {
        root._activeNodeGeometryRevision += 1;
        root._nodeGeometryDirty = true;
        root._activeNodeGeometryDirty = true;
        root._cachedNodeMap = null;
    }
    function markViewportDirty() {
        root._viewportRevision += 1;
        root._viewportDirty = true;
    }
    function markSelectionDirty() {
        root._selectionRevision += 1;
        root._selectionDirty = true;
    }
    function markCrossingStyleDirty() {
        root._crossingStyleRevision += 1;
        root._crossingStyleDirty = true;
    }
    function markThemeDirty() {
        root._themeRevision += 1;
        root._themeDirty = true;
    }
    function markScheduledRedrawDirty() {
        root._scheduledRedrawDirty = true;
    }
    function markViewStateRedrawDirty() {
        root.markViewportDirty();
        root._viewStateRedrawDirty = true;
        root._scheduledRedrawDirty = true;
    }
    function flushViewStateRedraw() {
        if (!root._viewStateRedrawDirty)
            return false;
        return root.requestImmediateRedraw();
    }
    function flushScheduledRedraw() {
        if (!root._viewStateRedrawDirty && !root._scheduledRedrawDirty)
            return false;
        return root.requestImmediateRedraw();
    }
    function sceneToScreenX(worldX) {
        return EdgeViewportMath.sceneXToScreen(worldX, EdgeViewportMath.viewportTransform(root));
    }
    function sceneToScreenY(worldY) {
        return EdgeViewportMath.sceneYToScreen(worldY, EdgeViewportMath.viewportTransform(root));
    }
    function _edgeAnchor(geometry, fraction) {
        return EdgeMath.edgeAnchor(geometry, fraction);
    }
    function _visibleEdgeSnapshot(edgeId) {
        return EdgeSnapshotCache.visibleEdgeSnapshot(root, edgeId);
    }
    function edgeEndpointScenePoint(edgeId, endpoint) {
        var snapshot = root._visibleEdgeSnapshot(edgeId);
        var geometry = snapshot ? snapshot.geometry : null;
        if (!geometry) {
            var edge = root._edgeData(edgeId);
            geometry = edge ? root._edgeGeometry(edge, root._nodeMap()) : null;
        }
        if (!geometry)
            return null;
        var target = String(endpoint || "source").trim().toLowerCase() === "target";
        return target
            ? ({"x": Number(geometry.tx), "y": Number(geometry.ty)})
            : ({"x": Number(geometry.sx), "y": Number(geometry.sy)});
    }

    function dragConnectionActiveDataWire(connection) {
        if (!connection)
            return false;
        if (connection.active_data_wire !== undefined)
            return Boolean(connection.active_data_wire);
        var sourceKind = String(connection.source_kind || "").trim().toLowerCase();
        var targetKind = String(connection.target_kind || "").trim().toLowerCase();
        if (sourceKind === "flow" || targetKind === "flow")
            return false;
        var nodeById = root._nodeMap();
        var endpointIds = [connection.source_node_id, connection.target_node_id];
        for (var i = 0; i < endpointIds.length; i++) {
            var node = nodeById[String(endpointIds[i] || "")];
            var behavior = String(node && node.runtime_behavior || "").trim().toLowerCase();
            if (behavior === "active" || behavior === "compile_only")
                return true;
        }
        return false;
    }
    function edgeAtScreen(screenX, screenY) {
        return EdgeSnapshotCache.edgeAtScreen(root, edgeCanvasLayer, flowLabelLayer, screenX, screenY);
    }
    function edgeIdsIntersectingScreenRect(screenX, screenY, screenWidth, screenHeight) {
        return EdgeSnapshotCache.edgeIdsIntersectingScreenRect(
            root,
            edgeCanvasLayer,
            flowLabelLayer,
            screenX,
            screenY,
            screenWidth,
            screenHeight
        );
    }
    function edgeIdsIntersectingSceneRect(sceneX, sceneY, sceneWidth, sceneHeight) {
        return EdgeSnapshotCache.edgeIdsIntersectingSceneRect(
            root,
            edgeCanvasLayer,
            flowLabelLayer,
            sceneX,
            sceneY,
            sceneWidth,
            sceneHeight
        );
    }

    function _edgeData(edgeId) {
        var normalized = String(edgeId || "");
        var cached = root._edgeById ? root._edgeById[normalized] : null;
        if (cached)
            return cached;
        var source = root.edges || [];
        for (var i = 0; i < source.length; ++i) {
            if (String(source[i] && source[i].edge_id || "") === normalized)
                return source[i];
        }
        return null;
    }

    function outputPreviewForEdge(edge) {
        if (!edge || String(edge.edge_family || "") === "flow")
            return null;
        var nodeLookup = root.outputPreviewLookup[String(edge.source_node_id || "")] || ({});
        return nodeLookup[String(edge.source_port_key || "")] || null;
    }

    function edgeValueState(edge) {
        if (!edge)
            return "never";
        if (edge.enabled === false)
            return "disabled";
        var preview = root.outputPreviewForEdge(edge);
        return String(preview && preview.state || "never");
    }

    function edgeTooltipText(edgeId) {
        var edge = root._edgeData(edgeId);
        if (!edge || EdgePaintPolicy.edgeIsFlow(edge))
            return "";
        var access = String(edge.data_access || "item").trim().toLowerCase();
        if (!Boolean(edge.active_data_wire)) {
            var accessLabel = access === "tree" ? "Tree" : (access === "list" ? "List" : "Item");
            var legacyRows = [accessLabel + " data"];
            if (edge.enabled === false)
                legacyRows.push("Disabled");
            if (Boolean(edge.data_type_warning))
                legacyRows.push("Invalid type");
            var legacyPreview = root.outputPreviewForEdge(edge);
            var legacyPreviewText = String(legacyPreview && legacyPreview.tooltip_text || "").trim();
            if (legacyPreviewText.length > 0)
                legacyRows.push(legacyPreviewText);
            return legacyRows.join("\n");
        }
        if (edge.enabled === false)
            return "Disabled";
        var result = [];
        if (Boolean(edge.data_type_warning))
            result.push("Invalid type");
        var preview = root.outputPreviewForEdge(edge);
        var previewText = String(preview && preview.tooltip_text || "").trim();
        var previewLines = previewText.length > 0 ? previewText.split(/\r?\n/) : [];
        if (previewLines.length > 0 && previewLines[0] === "Current")
            previewLines.shift();
        else if (previewLines.length > 0
                && ["Stale", "Empty", "Failed", "Pending", "Never run"].indexOf(previewLines[0]) >= 0)
            result.push(previewLines.shift());
        if (!preview)
            return result.join("\n");
        var structuredRows = preview.rows || [];
        if (access === "item") {
            for (var itemIndex = 0; itemIndex < structuredRows.length; itemIndex++) {
                if (String(structuredRows[itemIndex].kind || "") === "item") {
                    result.push(String(structuredRows[itemIndex].text || ""));
                    return result.join("\n");
                }
            }
            return result.concat(previewLines).join("\n");
        }
        var headerPrefix = access === "tree" ? "Tree:" : "List:";
        var header = "";
        for (var lineIndex = 0; lineIndex < previewLines.length; lineIndex++) {
            if (String(previewLines[lineIndex]).indexOf(headerPrefix) === 0) {
                header = String(previewLines[lineIndex]);
                break;
            }
        }
        if (header.length > 0)
            result.push(header);
        if (!structuredRows.length)
            return result.concat(previewLines.filter(function(line) { return line !== header; })).join("\n");
        var maxIndex = 0;
        for (var rowIndex = 0; rowIndex < structuredRows.length; rowIndex++) {
            if (String(structuredRows[rowIndex].kind || "") === "item")
                maxIndex = Math.max(maxIndex, Number(structuredRows[rowIndex].index || 0));
        }
        var indexWidth = String("[" + maxIndex + "]").length;
        var flatIndex = 0;
        for (rowIndex = 0; rowIndex < structuredRows.length; rowIndex++) {
            var row = structuredRows[rowIndex] || ({});
            var kind = String(row.kind || "");
            if (access === "tree" && kind === "branch") {
                result.push("{" + String(row.path || "") + "}");
                continue;
            }
            if (kind !== "item")
                continue;
            var displayIndex = access === "list" ? flatIndex++ : Number(row.index || 0);
            var indexText = "[" + displayIndex + "]";
            while (indexText.length < indexWidth)
                indexText = " " + indexText;
            result.push((access === "tree" ? "  " : "") + indexText + "  " + String(row.text || ""));
        }
        if (Boolean(preview.truncated))
            result.push("…");
        return result.join("\n");
    }

    function _rectIntersects(a, b) {
        if (!a || !b)
            return true;
        return a.left <= b.right
            && a.right >= b.left
            && a.top <= b.bottom
            && a.bottom >= b.top;
    }

    function _sceneBoundsForPoints(points) {
        if (!points || !points.length)
            return null;
        var minX = Number.POSITIVE_INFINITY;
        var minY = Number.POSITIVE_INFINITY;
        var maxX = Number.NEGATIVE_INFINITY;
        var maxY = Number.NEGATIVE_INFINITY;
        for (var i = 0; i < points.length; i++) {
            var point = points[i];
            if (!point)
                continue;
            var x = Number(point.x);
            var y = Number(point.y);
            if (!isFinite(x) || !isFinite(y))
                continue;
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
        }
        if (!isFinite(minX) || !isFinite(minY) || !isFinite(maxX) || !isFinite(maxY))
            return null;
        return {"left": minX, "top": minY, "right": maxX, "bottom": maxY};
    }

    function _nodeMap() {
        var baseById = root._baseNodeMap();
        var byId = Object.create ? Object.create(baseById) : {};
        var hasOverlay = false;
        var sceneNodes = root.nodes || [];
        var liveGeometry = root.liveNodeGeometry || {};
        for (var liveNodeId in liveGeometry) {
            if (!Object.prototype.hasOwnProperty.call(liveGeometry, liveNodeId))
                continue;
            var node = baseById[liveNodeId];
            var overlay = liveGeometry[liveNodeId];
            if (!node || !overlay || node.collapsed)
                continue;
            var merged = {};
            for (var key in node) {
                if (Object.prototype.hasOwnProperty.call(node, key))
                    merged[key] = node[key];
            }
            var liveX = Number(overlay.x);
            var liveY = Number(overlay.y);
            var liveWidth = Number(overlay.width);
            var liveHeight = Number(overlay.height);
            if (isFinite(liveX))
                merged.x = liveX;
            if (isFinite(liveY))
                merged.y = liveY;
            if (isFinite(liveWidth) && liveWidth > 0.0)
                merged.width = liveWidth;
            if (isFinite(liveHeight) && liveHeight > 0.0)
                merged.height = liveHeight;
            if (overlay.settingsGroupAnimation) {
                merged.settingsGroupLayoutHeight = overlay.settingsGroupLayoutHeight;
                merged.settingsGroupPortOffsets = overlay.settingsGroupPortOffsets;
            }
            byId[liveNodeId] = merged;
            hasOverlay = true;
        }
        if (!hasOverlay)
            return baseById;
        if (!Object.create) {
            for (var i = 0; i < sceneNodes.length; i++) {
                var sceneNode = sceneNodes[i];
                if (sceneNode && sceneNode.node_id && byId[sceneNode.node_id] === undefined)
                    byId[sceneNode.node_id] = sceneNode;
            }
        }
        return byId;
    }

    function _baseNodeMap() {
        if (root._cachedBaseNodeMap !== null)
            return root._cachedBaseNodeMap;
        var byId = {};
        var sceneNodes = root.nodes || [];
        for (var i = 0; i < sceneNodes.length; i++) {
            var node = sceneNodes[i];
            if (node && node.node_id)
                byId[node.node_id] = node;
        }
        var nodeDeltaById = root._nodePayloadDeltaById || {};
        for (var nodeId in nodeDeltaById) {
            if (Object.prototype.hasOwnProperty.call(nodeDeltaById, nodeId))
                byId[nodeId] = nodeDeltaById[nodeId];
        }
        root._cachedBaseNodeMap = byId;
        return byId;
    }

    function _portScenePoint(node, portKey) {
        if (!node || !portKey)
            return null;
        var isLockedPlaceholder = Boolean(node.read_only) && Boolean(node.unresolved);
        var ports = node.ports || [];
        var inputRow = 0;
        var outputRow = 0;
        for (var i = 0; i < ports.length; i++) {
            var port = ports[i];
            if (!port)
                continue;
            if (String(port.key || "") === String(portKey)) {
                if (isLockedPlaceholder)
                    return GraphNodeSurfaceMetrics.portScenePointForPort(node, port, 0, 0);
                var point = GraphNodeSurfaceMetrics.portScenePointForPort(
                    node, port, inputRow, outputRow, node.width,
                    node.settingsGroupLayoutHeight !== undefined ? node.settingsGroupLayoutHeight : node.height
                );
                point.y += Number(node.settingsGroupPortOffsets
                    ? node.settingsGroupPortOffsets[String(port.key)] || 0 : 0);
                return point;
            }
            var direction = GraphNodeSurfaceMetrics.portLayoutDirection(port);
            if (direction === "in")
                inputRow += 1;
            else if (direction === "out")
                outputRow += 1;
        }
        return null;
    }

    function _nodeBounds(nodeId, offsetX, offsetY, nodeById) {
        var node = nodeById[nodeId];
        if (!node)
            return null;
        var ox = Number(offsetX || 0.0);
        var oy = Number(offsetY || 0.0);
        return {
            "left": node.x + ox,
            "top": node.y + oy,
            "right": node.x + node.width + ox,
            "bottom": node.y + node.height + oy,
            "x": node.x + ox,
            "y": node.y + oy,
            "width": node.width,
            "height": node.height
        };
    }

    function _normalizedCardinalSide(side, fallback) {
        var normalized = String(side || "").trim().toLowerCase();
        if (normalized === "top" || normalized === "right" || normalized === "bottom" || normalized === "left")
            return normalized;
        return String(fallback || "").trim().toLowerCase();
    }

    function _coerceBounds(boundsPayload) {
        if (!boundsPayload)
            return null;
        var x = Number(boundsPayload.x);
        var y = Number(boundsPayload.y);
        var width = Number(boundsPayload.width);
        var height = Number(boundsPayload.height);
        if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(height) || width <= 0.0 || height <= 0.0)
            return null;
        return {
            "left": x,
            "top": y,
            "right": x + width,
            "bottom": y + height,
            "x": x,
            "y": y,
            "width": width,
            "height": height
        };
    }

    function _offsetBounds(bounds, dx, dy) {
        if (!bounds)
            return null;
        var offsetX = Number(dx);
        var offsetY = Number(dy);
        if (!isFinite(offsetX))
            offsetX = 0.0;
        if (!isFinite(offsetY))
            offsetY = 0.0;
        return {
            "left": bounds.left + offsetX,
            "top": bounds.top + offsetY,
            "right": bounds.right + offsetX,
            "bottom": bounds.bottom + offsetY,
            "x": bounds.x + offsetX,
            "y": bounds.y + offsetY,
            "width": bounds.width,
            "height": bounds.height
        };
    }

    function _overlayBounds(bounds, overlay) {
        if (!bounds)
            return null;
        if (!overlay)
            return bounds;
        var x = Number(overlay.x);
        var y = Number(overlay.y);
        var width = Number(overlay.width);
        var height = Number(overlay.height);
        var nextX = isFinite(x) ? x : bounds.x;
        var nextY = isFinite(y) ? y : bounds.y;
        var nextWidth = isFinite(width) && width > 0.0 ? width : bounds.width;
        var nextHeight = isFinite(height) && height > 0.0 ? height : bounds.height;
        return {
            "left": nextX,
            "top": nextY,
            "right": nextX + nextWidth,
            "bottom": nextY + nextHeight,
            "x": nextX,
            "y": nextY,
            "width": nextWidth,
            "height": nextHeight
        };
    }

    function _edgeAnchorBounds(edge, prefix, nodeById) {
        var anchorNodeId = String(edge && edge[prefix + "_anchor_node_id"] || "");
        var dragged = root.dragNodeLookup ? Boolean(root.dragNodeLookup[anchorNodeId]) : false;
        var offsetX = dragged ? root.dragDx : 0.0;
        var offsetY = dragged ? root.dragDy : 0.0;
        var nodeBounds = anchorNodeId ? root._nodeBounds(anchorNodeId, offsetX, offsetY, nodeById) : null;
        if (nodeBounds)
            return nodeBounds;

        var bounds = root._coerceBounds(edge ? edge[prefix + "_anchor_bounds"] : null);
        if (!bounds)
            return null;
        var overlay = root.liveNodeGeometry ? root.liveNodeGeometry[anchorNodeId] : null;
        bounds = root._overlayBounds(bounds, overlay);
        if (dragged)
            bounds = root._offsetBounds(bounds, offsetX, offsetY);
        return bounds;
    }

    function _clampToRange(value, low, high) {
        var numeric = Number(value);
        var minimum = Number(low);
        var maximum = Number(high);
        if (!isFinite(numeric))
            numeric = (minimum + maximum) * 0.5;
        if (!isFinite(minimum) || !isFinite(maximum))
            return numeric;
        if (minimum > maximum)
            return (minimum + maximum) * 0.5;
        return Math.min(maximum, Math.max(minimum, numeric));
    }

    function _perimeterPoint(bounds, side, towardPoint) {
        if (!bounds)
            return null;
        var normalizedSide = root._normalizedCardinalSide(side, "right");
        var towardX = towardPoint ? Number(towardPoint.x) : (bounds.left + bounds.right) * 0.5;
        var towardY = towardPoint ? Number(towardPoint.y) : (bounds.top + bounds.bottom) * 0.5;
        if (!isFinite(towardX))
            towardX = (bounds.left + bounds.right) * 0.5;
        if (!isFinite(towardY))
            towardY = (bounds.top + bounds.bottom) * 0.5;
        var insetX = Math.min(12.0, bounds.width * 0.5);
        var insetY = Math.min(12.0, bounds.height * 0.5);
        if (normalizedSide === "left") {
            return {"x": bounds.left, "y": root._clampToRange(towardY, bounds.top + insetY, bounds.bottom - insetY)};
        }
        if (normalizedSide === "right") {
            return {"x": bounds.right, "y": root._clampToRange(towardY, bounds.top + insetY, bounds.bottom - insetY)};
        }
        if (normalizedSide === "top") {
            return {"x": root._clampToRange(towardX, bounds.left + insetX, bounds.right - insetX), "y": bounds.top};
        }
        return {"x": root._clampToRange(towardX, bounds.left + insetX, bounds.right - insetX), "y": bounds.bottom};
    }

    function _edgeEndpointState(edge, prefix, nodeById, oppositePoint) {
        var pointX = Number(edge && edge[prefix === "source" ? "sx" : "tx"] || 0.0);
        var pointY = Number(edge && edge[prefix === "source" ? "sy" : "ty"] || 0.0);
        var anchorNodeId = String(edge && edge[prefix + "_anchor_node_id"] || edge && edge[prefix + "_node_id"] || "");
        var portKey = String(edge && edge[prefix + "_port_key"] || "");
        var fallbackSide = prefix === "source" ? "right" : "left";
        var side = root._normalizedCardinalSide(
            edge && edge[prefix + "_anchor_side"],
            root._normalizedCardinalSide(edge && edge[prefix + "_port_side"], fallbackSide)
        );
        var anchorKind = String(edge && edge[prefix + "_anchor_kind"] || "node");
        var bounds = root._edgeAnchorBounds(edge, prefix, nodeById);
        if (anchorKind === "node") {
            var anchorNode = nodeById[anchorNodeId];
            var portPoint = root._portScenePoint(anchorNode, portKey);
            if (portPoint) {
                // Drag previews keep the scene payload static, so edge anchors need the
                // transient node offset applied explicitly while the node is moving.
                var dragged = root.dragNodeLookup ? Boolean(root.dragNodeLookup[anchorNodeId]) : false;
                var offsetX = dragged ? Number(root.dragDx) : 0.0;
                var offsetY = dragged ? Number(root.dragDy) : 0.0;
                if (!isFinite(offsetX))
                    offsetX = 0.0;
                if (!isFinite(offsetY))
                    offsetY = 0.0;
                return {
                    "point": {"x": portPoint.x + offsetX, "y": portPoint.y + offsetY},
                    "bounds": bounds,
                    "side": side
                };
            }
        }
        if (bounds) {
            return {
                "point": root._perimeterPoint(bounds, side, oppositePoint),
                "bounds": bounds,
                "side": side
            };
        }
        return {"point": {"x": pointX, "y": pointY}, "bounds": bounds, "side": side};
    }

    function _routeLength(sourceX, sourceY, sourceStubX, targetX, targetY, targetStubX, routeY) {
        return Math.abs(sourceStubX - sourceX)
            + Math.abs(routeY - sourceY)
            + Math.abs(sourceStubX - targetStubX)
            + Math.abs(targetY - routeY)
            + Math.abs(targetX - targetStubX);
    }

    function _buildLegacyPipePoints(edge, sourceBounds, targetBounds, sourceX, sourceY, targetX, targetY, nodeById) {
        if (!sourceBounds && edge && edge.source_node_id)
            sourceBounds = root._nodeBounds(edge.source_node_id, 0.0, 0.0, nodeById);
        if (!targetBounds && edge && edge.target_node_id)
            targetBounds = root._nodeBounds(edge.target_node_id, 0.0, 0.0, nodeById);
        var laneBias = edge.lane_bias || 0.0;
        var stub = Math.min(72.0, Math.max(32.0, Math.max(44.0, Math.abs(targetX - sourceX) * 0.2)));
        var sourceStubX;
        var targetStubX;
        var sourceTop;
        var sourceBottom;
        var targetTop;
        var targetBottom;

        if (sourceBounds && targetBounds) {
            sourceStubX = Math.max(sourceBounds.right, sourceX) + stub;
            targetStubX = Math.min(targetBounds.left, targetX) - stub;
            sourceTop = sourceBounds.top;
            sourceBottom = sourceBounds.bottom;
            targetTop = targetBounds.top;
            targetBottom = targetBounds.bottom;
        } else {
            sourceStubX = sourceX + stub;
            targetStubX = targetX - stub;
            sourceTop = Math.min(sourceY, targetY) - 40.0;
            sourceBottom = Math.max(sourceY, targetY) + 40.0;
            targetTop = sourceTop;
            targetBottom = sourceBottom;
        }

        if (sourceStubX <= targetStubX) {
            var midX = (sourceStubX + targetStubX) * 0.5;
            sourceStubX = midX + 22.0;
            targetStubX = midX - 22.0;
        }

        var verticalClearance = 56.0 * 0.6 + Math.abs(laneBias) * 0.8;
        var topBound = Math.min(sourceTop, targetTop);
        var bottomBound = Math.max(sourceBottom, targetBottom);
        var topRouteY = topBound - verticalClearance - Math.max(0.0, laneBias);
        var bottomRouteY = bottomBound + verticalClearance + Math.max(0.0, -laneBias);
        var candidates = [{"y": topRouteY, "priority": 1}, {"y": bottomRouteY, "priority": 1}];

        var middleLow = null;
        var middleHigh = null;
        if (sourceBottom + 10.0 <= targetTop - 10.0) {
            middleLow = sourceBottom + 10.0;
            middleHigh = targetTop - 10.0;
        } else if (targetBottom + 10.0 <= sourceTop - 10.0) {
            middleLow = targetBottom + 10.0;
            middleHigh = sourceTop - 10.0;
        }

        if (middleLow !== null && middleHigh !== null && middleLow <= middleHigh) {
            var preferredMiddle = (sourceY + targetY) * 0.5 + laneBias * 0.35;
            var middleRouteY = EdgeMath.clamp(preferredMiddle, middleLow, middleHigh);
            candidates.push({"y": middleRouteY, "priority": 0});
        }

        var best = candidates[0];
        var bestLength = _routeLength(sourceX, sourceY, sourceStubX, targetX, targetY, targetStubX, best.y);
        for (var c = 1; c < candidates.length; c++) {
            var candidate = candidates[c];
            var candidateLength = _routeLength(
                sourceX,
                sourceY,
                sourceStubX,
                targetX,
                targetY,
                targetStubX,
                candidate.y
            );
            if (candidateLength < bestLength
                || (Math.abs(candidateLength - bestLength) < 0.01 && candidate.priority < best.priority)) {
                best = candidate;
                bestLength = candidateLength;
            }
        }

        return [
            {"x": sourceX, "y": sourceY},
            {"x": sourceStubX, "y": sourceY},
            {"x": sourceStubX, "y": best.y},
            {"x": targetStubX, "y": best.y},
            {"x": targetStubX, "y": targetY},
            {"x": targetX, "y": targetY}
        ];
    }

    function _buildFlowPipePoints(sourceX, sourceY, targetX, targetY, edge, sourceBounds, targetBounds, sourceSide, targetSide) {
        return EdgeMath.flowPipeRoute(
            {"x": sourceX, "y": sourceY},
            {"x": targetX, "y": targetY},
            {
                "sourceSide": String(sourceSide || edge && edge.source_anchor_side || edge && edge.source_port_side || ""),
                "targetSide": String(targetSide || edge && edge.target_anchor_side || edge && edge.target_port_side || ""),
                "sourceBounds": sourceBounds,
                "targetBounds": targetBounds,
                "laneBias": Number(edge && edge.lane_bias || 0.0)
            }
        );
    }

    function _previewIsFlow(connection) {
        if (!connection)
            return false;
        var sourceKind = String(connection.source_kind || "").trim().toLowerCase();
        var targetKind = String(connection.target_kind || "").trim().toLowerCase();
        if (sourceKind === "flow" && (!targetKind || targetKind === "flow"))
            return true;
        return !!String(connection.origin_side || "").trim()
            || !!String(connection.target_side || "").trim();
    }

    function _previewFallbackTargetSide(sourceX, sourceY, targetX, targetY) {
        var dx = Number(targetX) - Number(sourceX);
        var dy = Number(targetY) - Number(sourceY);
        if (Math.abs(dx) >= Math.abs(dy))
            return dx >= 0.0 ? "left" : "right";
        return dy >= 0.0 ? "top" : "bottom";
    }

    function _edgeGeometry(edge, nodeById) {
        var sxWorld = edge.sx;
        var syWorld = edge.sy;
        var txWorld = edge.tx;
        var tyWorld = edge.ty;
        var c1xWorld = edge.c1x;
        var c1yWorld = edge.c1y;
        var c2xWorld = edge.c2x;
        var c2yWorld = edge.c2y;
        var sourceState = root._edgeEndpointState(edge, "source", nodeById, {"x": txWorld, "y": tyWorld});
        var targetState = root._edgeEndpointState(
            edge,
            "target",
            nodeById,
            sourceState && sourceState.point ? sourceState.point : {"x": sxWorld, "y": syWorld}
        );
        sourceState = root._edgeEndpointState(
            edge,
            "source",
            nodeById,
            targetState && targetState.point ? targetState.point : {"x": txWorld, "y": tyWorld}
        );
        if (sourceState && sourceState.point) {
            c1xWorld += sourceState.point.x - sxWorld;
            c1yWorld += sourceState.point.y - syWorld;
            sxWorld = sourceState.point.x;
            syWorld = sourceState.point.y;
        }
        if (targetState && targetState.point) {
            c2xWorld += targetState.point.x - txWorld;
            c2yWorld += targetState.point.y - tyWorld;
            txWorld = targetState.point.x;
            tyWorld = targetState.point.y;
        }

        var pipePoints = edge.pipe_points || [];
        if (edge.route === "pipe") {
            var sourceBounds = sourceState ? sourceState.bounds : null;
            var targetBounds = targetState ? targetState.bounds : null;
            var sourceSide = sourceState ? sourceState.side : root._normalizedCardinalSide(edge.source_anchor_side, edge.source_port_side);
            var targetSide = targetState ? targetState.side : root._normalizedCardinalSide(edge.target_anchor_side, edge.target_port_side);
            pipePoints = EdgePaintPolicy.edgeIsFlow(edge)
                ? _buildFlowPipePoints(
                    sxWorld,
                    syWorld,
                    txWorld,
                    tyWorld,
                    edge,
                    sourceBounds,
                    targetBounds,
                    sourceSide,
                    targetSide
                )
                : _buildLegacyPipePoints(
                    edge,
                    sourceBounds,
                    targetBounds,
                    sxWorld,
                    syWorld,
                    txWorld,
                    tyWorld,
                    nodeById
                );
            var pipeHandles = EdgeMath.pipeControlHandles(pipePoints);
            c1xWorld = pipeHandles.first.x;
            c1yWorld = pipeHandles.first.y;
            c2xWorld = pipeHandles.last.x;
            c2yWorld = pipeHandles.last.y;
        }

        return {
            "sx": sxWorld,
            "sy": syWorld,
            "tx": txWorld,
            "ty": tyWorld,
            "c1x": c1xWorld,
            "c1y": c1yWorld,
            "c2x": c2xWorld,
            "c2y": c2yWorld,
            "route": edge.route,
            "pipe_points": pipePoints
        };
    }

    function _dragGeometry(connection) {
        if (!connection)
            return null;
        var sourceX = Number(connection.start_x);
        var sourceY = Number(connection.start_y);
        var targetX = Number(connection.target_x);
        var targetY = Number(connection.target_y);
        var dominantDistance = Math.max(Math.abs(targetX - sourceX), Math.abs(targetY - sourceY));
        var handle = Math.max(42.0, Math.min(170.0, dominantDistance * 0.42));
        var sourceDirection = String(connection.source_direction || "out");
        var originSide = GraphNodeSurfaceMetrics.portCardinalSide({"side": connection.origin_side});
        var targetSide = GraphNodeSurfaceMetrics.portCardinalSide({"side": connection.target_side});
        if (root._previewIsFlow(connection)) {
            var nodeById = EdgeSnapshotCache.getNodeMap(root);
            var sourceBounds = connection.source_node_id ? root._nodeBounds(connection.source_node_id, 0.0, 0.0, nodeById) : null;
            var targetBounds = connection.target_node_id ? root._nodeBounds(connection.target_node_id, 0.0, 0.0, nodeById) : null;
            var resolvedSourceSide = EdgeMath.normalizeCardinalSide(originSide, sourceDirection === "in" ? "left" : "right");
            var resolvedTargetSide = EdgeMath.normalizeCardinalSide(
                targetSide,
                root._previewFallbackTargetSide(sourceX, sourceY, targetX, targetY)
            );
            var pipePoints = EdgeMath.flowPipeRoute(
                {"x": sourceX, "y": sourceY},
                {"x": targetX, "y": targetY},
                {
                    "sourceSide": resolvedSourceSide,
                    "targetSide": resolvedTargetSide,
                    "sourceBounds": sourceBounds,
                    "targetBounds": targetBounds,
                    "laneBias": 0.0
                }
            );
            var pipeHandles = EdgeMath.pipeControlHandles(pipePoints);
            return {
                "sx": sourceX,
                "sy": sourceY,
                "tx": targetX,
                "ty": targetY,
                "c1x": pipeHandles.first.x,
                "c1y": pipeHandles.first.y,
                "c2x": pipeHandles.last.x,
                "c2y": pipeHandles.last.y,
                "route": "pipe",
                "pipe_points": pipePoints
            };
        }
        var sourceNormal = originSide
            ? GraphNodeSurfaceMetrics.flowchartAnchorNormal(originSide)
            : (sourceDirection === "in" ? {"x": -1.0, "y": 0.0} : {"x": 1.0, "y": 0.0});
        var targetNormal = targetSide
            ? GraphNodeSurfaceMetrics.flowchartAnchorNormal(targetSide)
            : (sourceDirection === "in" ? {"x": 1.0, "y": 0.0} : {"x": -1.0, "y": 0.0});
        return {
            "sx": sourceX,
            "sy": sourceY,
            "tx": targetX,
            "ty": targetY,
            "c1x": sourceX + sourceNormal.x * handle,
            "c1y": sourceY + sourceNormal.y * handle,
            "c2x": targetX + targetNormal.x * handle,
            "c2y": targetY + targetNormal.y * handle,
            "route": "bezier",
            "pipe_points": []
        };
    }
    function dragConnectionList() {
        if (!root.dragConnection)
            return [];
        if (Array.isArray(root.dragConnection))
            return root.dragConnection;
        if (Array.isArray(root.dragConnection.connections))
            return root.dragConnection.connections;
        return [root.dragConnection];
    }

    EdgeCanvasLayer {
        id: edgeCanvasLayer
        anchors.fill: parent
        edgeLayer: root
    }

    EdgeRetainedLayer {
        id: edgeRetainedLayer
        anchors.fill: parent
        edgeLayer: root
        visible: root.edgeRendererKind === "retained_qml"
    }

    EdgeScenegraphLayer {
        id: edgeScenegraphLayer
        anchors.fill: parent
        edgeLayer: root
        visible: root.edgeRendererKind === "native_scenegraph"
    }

    EdgeFlowLabelLayer {
        id: flowLabelLayer
        anchors.fill: parent
        edgeLayer: root
        canvasLayer: edgeCanvasLayer
    }

    EdgeHitTestOverlay {
        id: edgeHitTestOverlay
        anchors.fill: parent
        edgeLayer: root
        inputEnabled: root.inputEnabled
        wireSelectionModeHeld: root.wireSelectionModeHeld
        onEdgeClicked: function(edgeId, additive) {
            root.edgeClicked(edgeId, additive);
        }
        onEdgeDoubleClicked: function(edgeId) {
            root.edgeDoubleClicked(edgeId);
        }
        onEdgeContextRequested: function(edgeId, screenX, screenY) {
            root.edgeContextRequested(edgeId, screenX, screenY);
        }
    }

    onEdgesChanged: {
        if (!root._structuralEdgePayloadSyncActive) {
            markEdgeTopologyDirty({});
            requestRedraw();
        }
    }
    onNodeDeltaPayloadChanged: EdgeSnapshotCache.applyNodePayloadDelta(root, nodeDeltaPayload)
    onSelectedNodeIdsChanged: {
        markSelectionDirty();
        requestRedraw();
    }
    onReplacementPreviewEdgeIdsChanged: {
        markSelectionDirty();
        requestRedraw();
    }
    onNodesChanged: {
        root._nodePayloadDeltaById = ({});
        markNodeGeometryDirty();
        requestRedraw();
    }
    onDragRevisionChanged: { markActiveNodeGeometryDirty(); requestRedraw(); }
    onLiveNodeGeometryChanged: {
        markActiveNodeGeometryDirty();
        var animationActive = false;
        var geometry = liveNodeGeometry || ({});
        for (var nodeId in geometry) {
            if (geometry[nodeId] && geometry[nodeId].settingsGroupAnimation) {
                animationActive = true;
                break;
            }
        }
        // Canvas paint can precede deferred callbacks. Refresh the incident
        // edge snapshots now so the next paint uses this frame's socket poses.
        if (animationActive || _settingsGroupGeometryActive)
            requestImmediateRedraw();
        else
            requestRedraw();
        _settingsGroupGeometryActive = animationActive;
    }

    onVisibleSceneRectPayloadChanged: markViewportDirty()
    onSelectedEdgeIdsChanged: { markSelectionDirty(); requestRedraw(); }
    onWireSelectionModeHeldChanged: { markSelectionDirty(); requestRedraw(); }
    onPreviewEdgeIdChanged: { markSelectionDirty(); requestRedraw(); }
    onDragConnectionChanged: requestRedraw()
    onOutputPreviewLookupChanged: requestRedraw()
    onEdgePaletteChanged: { markThemeDirty(); requestRedraw(); }
    onShellPaletteChanged: { markThemeDirty(); requestRedraw(); }
    onPortKindPaletteChanged: { markThemeDirty(); requestRedraw(); }
    onEdgeCrossingStyleChanged: { markCrossingStyleDirty(); requestRedraw(); }
    onEdgeRendererPreferenceChanged: requestRedraw()
}
