import QtQuick 2.15
import QtQml 2.15
import QtQuick.Window 2.15
import "graph_canvas" as GraphCanvasComponents
import "graph_canvas/GraphCanvasRootApi.js" as GraphCanvasRootApi
Item {
    id: root
    objectName: "graphCanvas"
    signal nodeCommentEditorRequested(string nodeId, bool compose)
    signal nodeLinkTargetPickRequested(string kind, string sourceWorkspaceId, string sourceNodeId)
    signal nodeLinkTargetPicked(string workspaceId, string nodeId, string label, string subtitle)
    signal nodeLinkTargetPickCancelled()
    signal canvasBasePngExportFinished(var result)

    property var graphActionBridge: null
    property var canvasStateBridge: null
    property var canvasCommandBridge: null
    property var canvasViewBridge: null
    readonly property var shellContextRef: typeof shellContext !== "undefined" ? shellContext : null
    readonly property var shellWorkspaceBridgeRef: root.shellContextRef ? root.shellContextRef.shellWorkspaceBridge : null
    readonly property var shellInspectorBridgeRef: root.shellContextRef ? root.shellContextRef.shellInspectorBridge : null
    readonly property var _canvasViewportBridge: root.canvasViewBridge
        || (root.canvasStateBridge && root.canvasStateBridge.viewport_bridge
            ? root.canvasStateBridge.viewport_bridge
            : (root.canvasCommandBridge && root.canvasCommandBridge.viewport_bridge
                ? root.canvasCommandBridge.viewport_bridge
                : null))
    readonly property var graphActionBridgeRef: root.graphActionBridge || null
    readonly property var canvasStateBridgeRef: root.canvasStateBridge || null
    readonly property var canvasCommandBridgeRef: root.canvasCommandBridge || null
    readonly property var canvasViewBridgeRef: root._canvasViewportBridge
    readonly property var sceneStateBridge: root.canvasStateBridgeRef
    readonly property var sceneCommandBridge: root.canvasCommandBridgeRef
    readonly property var sceneBridge: root.canvasStateBridgeRef
    readonly property var viewBridge: root.canvasViewBridgeRef
    readonly property bool interactWithLockedObjects: root.sceneStateBridge
        && root.sceneStateBridge.interact_with_locked_objects !== undefined
        ? Boolean(root.sceneStateBridge.interact_with_locked_objects)
        : false

    function _validSceneRectPayload(payload) {
        return payload
            && isFinite(Number(payload.width))
            && isFinite(Number(payload.height))
            && Number(payload.width) > 0
            && Number(payload.height) > 0;
    }
    function _nodeRenderActivationPaddingPxForExtent(extent) {
        var resolvedExtent = Number(extent);
        if (!isFinite(resolvedExtent) || resolvedExtent < 0.0)
            resolvedExtent = 0.0;
        return Math.min(640.0, Math.max(240.0, resolvedExtent * 0.5));
    }
    function _nodeRenderActivationSceneRectPayload() {
        if (root.canvasViewBridgeRef
                && root.canvasViewBridgeRef.node_render_activation_scene_rect_payload !== undefined
                && root._validSceneRectPayload(root.canvasViewBridgeRef.node_render_activation_scene_rect_payload)) {
            return root.canvasViewBridgeRef.node_render_activation_scene_rect_payload;
        }
        return viewportController
            ? viewportController.inflateSceneRectPayload(
                root.visibleSceneRectPayload,
                viewportController.scenePaddingForViewportPixels(
                    root._nodeRenderActivationPaddingPxForExtent(root.width)
                ),
                viewportController.scenePaddingForViewportPixels(
                    root._nodeRenderActivationPaddingPxForExtent(root.height)
                )
            )
            : ({});
    }
    readonly property var themeBridgeRef: root.shellContextRef
        ? root.shellContextRef.themeBridge
        : (typeof themeBridge !== "undefined" ? themeBridge : null)
    readonly property var graphThemeBridgeRef: root.shellContextRef
        ? root.shellContextRef.graphThemeBridge
        : null
    readonly property var addonManagerBridgeRef: root.shellContextRef
        ? root.shellContextRef.addonManagerBridge
        : null
    readonly property var helpBridgeRef: root.shellContextRef
        ? root.shellContextRef.helpBridge
        : null
    readonly property var contentFullscreenBridgeRef: root.shellContextRef
        ? root.shellContextRef.contentFullscreenBridge
        : null
    readonly property var shellLibraryBridgeRef: root.shellContextRef
        ? root.shellContextRef.shellLibraryBridge
        : null
    readonly property var viewerSessionBridgeRef: root.shellContextRef
        ? root.shellContextRef.viewerSessionBridge
        : (typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge : null)
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property var graphNodePalette: root.graphThemeBridgeRef ? root.graphThemeBridgeRef.node_palette : ({})
    readonly property var canvasActionRouter: actionRouter
    readonly property var webPageRetentionStore: rootLayers.webPageRetentionStore
    readonly property var frameSchedulerRef: frameScheduler
    readonly property var nodeCommentPalette: rootLayers.nodeCommentPalette
    property var overlayHostItem: null
    property bool nodeLinkTargetPickActive: false
    property bool nodeLinkTargetPickCancelActive: nodeLinkTargetPickActive
    property string nodeLinkTargetPickWorkspaceId: ""
    property Item activeToolbarHost: null
    property var edgePayload: []
    readonly property var visibleSceneRectPayload: root.canvasViewBridgeRef
        ? (root.canvasViewBridgeRef.visible_scene_rect_payload_cached !== undefined
            ? root.canvasViewBridgeRef.visible_scene_rect_payload_cached
            : root.canvasViewBridgeRef.visible_scene_rect_payload)
        : ({})
    // Execution/preference projections below source from the shared Facts
    // objects. They remain on the canvas root because focused
    // QML suites probe them via canvas.property("..."); new facts must NOT
    // grow this list - consumers read the facts objects directly.
    readonly property var failedNodeLookup: executionFactsObject.failedNodeLookup
    readonly property string failedNodeTitle: executionFactsObject.failedNodeTitle
    readonly property var runningNodeLookup: executionFactsObject.runningNodeLookup
    readonly property var completedNodeLookup: executionFactsObject.completedNodeLookup
    readonly property var warningNodeLookup: executionFactsObject.warningNodeLookup
    readonly property bool hideOptionalPorts: preferenceFactsObject.hideOptionalPorts
    readonly property var runningNodeStartedAtMsLookup: executionFactsObject.runningNodeStartedAtMsLookup
    readonly property var nodeElapsedMsLookup: executionFactsObject.nodeElapsedMsLookup
    readonly property string nodeElapsedTimeUnit: executionFactsObject.nodeElapsedTimeUnit
    readonly property var freshRunNodeLookup: executionFactsObject.freshRunNodeLookup
    readonly property int nodeExecutionRevision: executionFactsObject.nodeExecutionRevision
    readonly property int edgeTopologyRevision: rootLayers.edgeLayerItem
        ? Number(rootLayers.edgeLayerItem._edgeTopologyRevision || 0)
        : 0
    readonly property var canvasViewportController: viewportController
    readonly property var canvasSceneLifecycle: sceneLifecycle
    readonly property var nodeRenderActivationSceneRectPayload: root._nodeRenderActivationSceneRectPayload()
    property bool minimapExpanded: preferenceFactsObject.minimapExpanded
    readonly property bool showGrid: preferenceFactsObject.showGrid
    readonly property string canvasBackgroundVariant: preferenceFactsObject.canvasBackgroundVariant
    readonly property bool minimapVisible: preferenceFactsObject.minimapVisible
    readonly property bool showCanvasOptionsButton: preferenceFactsObject.showCanvasOptionsButton
    readonly property bool showPortLabels: preferenceFactsObject.showPortLabels
    readonly property string edgeCrossingStyle: preferenceFactsObject.edgeCrossingStyle
    readonly property int shadowStrength: preferenceFactsObject.shadowStrength
    readonly property int shadowSoftness: preferenceFactsObject.shadowSoftness
    readonly property int shadowOffset: preferenceFactsObject.shadowOffset
    readonly property bool viewportInteractionWorldCacheActive: interactionState.interactionActive
    readonly property bool nativeOverlaySuppressionActive: interactionState.interactionActive
        || (sceneState.liveDragNodeIds && sceneState.liveDragNodeIds.length > 0)
        || (sceneState.liveNodeGeometry && Object.keys(sceneState.liveNodeGeometry).length > 0)
        || Boolean(interactionState.wireDragState && interactionState.wireDragState.active)
    property real profileOverlaySyncMs: 0.0
    readonly property int interactionIdleDelayMs: 2000
    readonly property int transientRecoveryDelayMs: 150
    readonly property real wireDragThreshold: 2
    readonly property real boxZoomDragThreshold: 4
    readonly property real boxZoomPaddingPx: 24
    readonly property real worldSize: 12000
    readonly property real worldOffset: root.worldSize / 2
    readonly property real minimapExpandedWidth: 238
    readonly property real minimapExpandedHeight: 162
    readonly property real minimapCollapsedWidth: 28
    readonly property real minimapCollapsedHeight: 28
    readonly property string gridStyle: preferenceFactsObject.gridStyle
    readonly property var folderExplorerColumnWidths: root.canvasStateBridgeRef
        && root.canvasStateBridgeRef.graphics_folder_explorer_column_widths !== undefined
        ? root.canvasStateBridgeRef.graphics_folder_explorer_column_widths
        : ({})
    readonly property var lockedNodeStatusSummary: root.sceneStateBridge
        && root.sceneStateBridge.locked_node_status_summary !== undefined
        ? root.sceneStateBridge.locked_node_status_summary
        : ({})
    readonly property int lockedNodeCount: Math.max(0, Number(lockedNodeStatusSummary.lockedNodeCount || 0))
    readonly property int missingAddonCount: Math.max(0, Number(lockedNodeStatusSummary.missingAddonCount || 0))
    readonly property string lockedNodeStatusFocusAddonId: String(lockedNodeStatusSummary.focusAddonId || "")
    readonly property bool lockedNodeStatusVisible: lockedNodeCount > 0
    readonly property bool lockedNodeStatusActionVisible: false
    readonly property string lockedNodeStatusText: {
        if (root.lockedNodeCount <= 0)
            return "";
        var lockedNodeText = root.lockedNodeCount === 1
            ? "1 locked node"
            : root.lockedNodeCount + " locked nodes";
        if (root.missingAddonCount <= 0)
            return lockedNodeText;
        var missingAddonText = root.missingAddonCount === 1
            ? "1 add-on missing"
            : root.missingAddonCount + " add-ons missing";
        return lockedNodeText + ", " + missingAddonText;
    }
    readonly property color lockedNodeStatusMutedTextColor: typeof themeBridge !== "undefined"
        && themeBridge
        && themeBridge.palette
        && themeBridge.palette.muted_fg
        ? themeBridge.palette.muted_fg
        : "#95a0b8"
    readonly property color lockedNodeStatusActionColor: typeof themeBridge !== "undefined"
        && themeBridge
        && themeBridge.palette
        && themeBridge.palette.accent
        ? themeBridge.palette.accent
        : "#2F89FF"
    readonly property var executionFacts: executionFactsObject
    readonly property var prefs: preferenceFactsObject
    GraphCanvasComponents.GraphCanvasExecutionFacts {
        id: executionFactsObject
        stateBridge: root.canvasStateBridgeRef
    }
    GraphCanvasComponents.GraphCanvasPreferenceFacts {
        id: preferenceFactsObject
        stateBridge: root.canvasStateBridgeRef
    }
    GraphCanvasComponents.GraphCanvasActionRouter {
        id: actionRouter
        canvasItem: root
        graphActionBridge: root.graphActionBridgeRef
        canvasCommandBridge: root.canvasCommandBridgeRef
        addonManagerBridge: root.addonManagerBridgeRef
        helpBridge: root.helpBridgeRef
        contentFullscreenBridge: root.contentFullscreenBridgeRef
        shellLibraryBridge: root.shellLibraryBridgeRef
        viewerSessionBridge: root.viewerSessionBridgeRef
    }
    GraphCanvasComponents.GraphCanvasInteractionState {
        id: interactionState
        canvasItem: root
        shellBridge: root.canvasCommandBridgeRef
        sceneBridge: root.sceneStateBridge
        edgeLayerItem: rootLayers.edgeLayerItem
        interactionIdleTimer: interactionIdleTimer
        interactionIdleDelayMs: root.transientRecoveryDelayMs
        wireDragThreshold: root.wireDragThreshold
    }
    GraphCanvasComponents.GraphCanvasSceneState {
        id: sceneState
        canvasItem: root
        edgeLayerItem: rootLayers.edgeLayerItem
    }

    GraphCanvasComponents.GraphCanvasFrameScheduler {
        id: frameScheduler
        backgroundLayer: rootLayers.backgroundLayerItem
        edgeLayer: rootLayers.edgeLayerItem
    }

    GraphCanvasComponents.GraphCanvasNodeSurfaceBridge {
        id: nodeSurfaceBridge
        canvasItem: root
    }

    GraphCanvasComponents.GraphCanvasViewportController {
        id: viewportController
        canvasItem: root
        shellCommandBridge: root.canvasCommandBridgeRef
        viewStateBridge: root.viewBridge
        viewCommandBridge: root.viewBridge
        interactionState: interactionState
        backgroundLayer: rootLayers.backgroundLayerItem
        edgeLayer: rootLayers.edgeLayerItem
        frameScheduler: frameScheduler
    }

    GraphCanvasComponents.GraphCanvasSceneLifecycle {
        id: sceneLifecycle
        canvasItem: root
        sceneStateBridge: root.sceneStateBridge
        viewStateBridge: root.viewBridge
        sceneState: sceneState
        interactionState: interactionState
        viewportController: viewportController
        edgeLayerItem: rootLayers.edgeLayerItem
        frameScheduler: frameScheduler
    }

    property alias hoveredPort: interactionState.hoveredPort
    property alias dropPreviewPort: interactionState.dropPreviewPort
    property alias dropPreviewEdgeId: interactionState.dropPreviewEdgeId
    property alias dropPreviewNodePayload: interactionState.dropPreviewNodePayload
    property alias dropPreviewScreenX: interactionState.dropPreviewScreenX
    property alias dropPreviewScreenY: interactionState.dropPreviewScreenY
    property alias pendingConnectionPort: interactionState.pendingConnectionPort
    property alias wireDragState: interactionState.wireDragState
    property alias wireDropCandidate: interactionState.wireDropCandidate
    property alias edgeContextVisible: interactionState.edgeContextVisible
    property alias nodeContextVisible: interactionState.nodeContextVisible
    property alias selectionContextVisible: interactionState.selectionContextVisible
    property alias canvasOptionsVisible: interactionState.canvasOptionsVisible
    property alias edgeContextEdgeId: interactionState.edgeContextEdgeId
    property alias nodeContextNodeId: interactionState.nodeContextNodeId
    property alias contextMenuX: interactionState.contextMenuX
    property alias contextMenuY: interactionState.contextMenuY
    property alias contextMenuSceneAnchorActive: interactionState.contextMenuSceneAnchorActive
    property alias contextMenuSceneAnchorX: interactionState.contextMenuSceneAnchorX
    property alias contextMenuSceneAnchorY: interactionState.contextMenuSceneAnchorY
    property alias selectionContextSceneAnchorActive: interactionState.selectionContextSceneAnchorActive
    property alias selectionContextSceneAnchorX: interactionState.selectionContextSceneAnchorX
    property alias selectionContextSceneAnchorY: interactionState.selectionContextSceneAnchorY
    property alias interactionActive: interactionState.interactionActive
    property alias viewportInteractionHeld: interactionState.viewportInteractionHeld
    property alias liveDragAnchorNodeId: sceneState.liveDragAnchorNodeId
    property alias liveDragNodeIds: sceneState.liveDragNodeIds
    property alias liveDragNodeLookup: sceneState.liveDragNodeLookup
    property alias liveDragDx: sceneState.liveDragDx
    property alias liveDragDy: sceneState.liveDragDy
    property alias liveDragRevision: sceneState.liveDragRevision
    property alias liveNodeGeometry: sceneState.liveNodeGeometry
    property alias profileLiveDragOffsetUpdateCount: sceneState.profileLiveDragOffsetUpdateCount
    property alias profileLiveDragMembershipFreezeCount: sceneState.profileLiveDragMembershipFreezeCount
    property alias selectedEdgeIds: sceneState.selectedEdgeIds
    property alias wireSelectionModeHeld: inputLayers.wireSelectionModeHeld
    onLiveDragRevisionChanged: root.applyLiveDragOffsetToHosts()
    onActiveFocusChanged: {
        if (!activeFocus)
            root.wireSelectionModeHeld = false;
    }

    focus: true
    activeFocusOnTab: true
    Keys.forwardTo: [inputLayers]
    clip: true

    Timer {
        id: interactionIdleTimer
        interval: root.transientRecoveryDelayMs
        repeat: false
        onTriggered: {
            if (!interactionState.viewportInteractionHeld)
                interactionState.endViewportInteraction();
        }
    }

    Connections {
        target: root.Window.window
        ignoreUnknownSignals: true

        function onActiveChanged() {
            var window = root.Window.window;
            if (!window || !window.active)
                root.wireSelectionModeHeld = false;
        }
    }

    function toggleMinimapExpanded() { GraphCanvasRootApi.invoke(viewportController, "toggleMinimapExpanded"); }
    function beginViewportInteraction() { GraphCanvasRootApi.invoke(viewportController, "beginViewportInteraction"); }
    function finishViewportInteractionSoon() { GraphCanvasRootApi.invoke(viewportController, "finishViewportInteractionSoon"); }
    function noteViewportInteraction() { GraphCanvasRootApi.invoke(viewportController, "noteViewportInteraction"); }
    function screenToSceneX(screenX) { return GraphCanvasRootApi.invoke(viewportController, "screenToSceneX", [screenX], 0.0); }
    function screenToSceneY(screenY) { return GraphCanvasRootApi.invoke(viewportController, "screenToSceneY", [screenY], 0.0); }
    function _wheelDeltaY(eventObj) { return GraphCanvasRootApi.invoke(viewportController, "wheelDeltaY", [eventObj], 0.0); }
    function shouldUseViewportInteractionQualityForWheelZoom() { return GraphCanvasRootApi.invoke(viewportController, "shouldUseViewportInteractionQualityForWheelZoom", [], false); }
    function applyWheelZoom(eventObj) { return GraphCanvasRootApi.invoke(viewportController, "applyWheelZoom", [eventObj], false); }
    function sceneToScreenX(sceneX) { return GraphCanvasRootApi.invoke(viewportController, "sceneToScreenX", [sceneX], 0.0); }
    function sceneToScreenY(sceneY) { return GraphCanvasRootApi.invoke(viewportController, "sceneToScreenY", [sceneY], 0.0); }
    function _normalizedSceneRectPayload(rectLike) { return GraphCanvasRootApi.invoke(viewportController, "normalizedSceneRectPayload", [rectLike], null); }
    function _scenePaddingForViewportPixels(paddingPx) { return GraphCanvasRootApi.invoke(viewportController, "scenePaddingForViewportPixels", [paddingPx], 0.0); }
    function _inflateSceneRectPayload(rectLike, horizontalPadding, verticalPadding) { return GraphCanvasRootApi.invoke(viewportController, "inflateSceneRectPayload", [rectLike, horizontalPadding, verticalPadding], ({})); }
    function frameScreenRect(screenX1, screenY1, screenX2, screenY2, paddingPx) { return GraphCanvasRootApi.invoke(viewportController, "frameScreenRect", [screenX1, screenY1, screenX2, screenY2, paddingPx], false); }
    function frameSceneRectPayload(rectLike, paddingPx) { return GraphCanvasRootApi.invoke(viewportController, "frameSceneRectPayload", [rectLike, paddingPx], false); }
    function snapToGridEnabled() { return GraphCanvasRootApi.snapToGridEnabled(root.canvasStateBridgeRef); }
    function snapGridSize() { return GraphCanvasRootApi.snapGridSize(root.canvasStateBridgeRef); }
    function snapToGridValue(value) { return GraphCanvasRootApi.snapToGridValue(root.canvasStateBridgeRef, value); }
    function setFolderExplorerColumnWidths(widths) { return GraphCanvasRootApi.invoke(root.canvasCommandBridgeRef, "set_folder_explorer_column_widths", [widths || ({})], false); }
    function snappedDragDelta(nodeId, rawDx, rawDy) { return GraphCanvasRootApi.snappedDragDelta(sceneState, root.canvasStateBridgeRef, nodeId, rawDx, rawDy); }
    function _normalizeEdgeIds(values) { return GraphCanvasRootApi.invoke(sceneState, "normalizeEdgeIds", [values], []); }
    function _availableEdgeIdSet() { return GraphCanvasRootApi.invoke(sceneState, "availableEdgeIdSet", [], ({})); }
    function pruneSelectedEdges() { GraphCanvasRootApi.invoke(sceneState, "pruneSelectedEdges"); }
    function clearEdgeSelection() { GraphCanvasRootApi.invoke(sceneState, "clearEdgeSelection"); }
    function toggleEdgeSelection(edgeId) { GraphCanvasRootApi.invoke(sceneState, "toggleEdgeSelection", [edgeId]); }
    function setExclusiveEdgeSelection(edgeId) { GraphCanvasRootApi.invoke(sceneState, "setExclusiveEdgeSelection", [edgeId]); }
    function setEdgeSelection(edgeIds, additive) { GraphCanvasRootApi.invoke(sceneState, "setEdgeSelection", [edgeIds, additive]); }
    function edgeAtScreen(screenX, screenY) {
        var edgeLayer = rootLayers.edgeLayerItem;
        return edgeLayer && edgeLayer.edgeAtScreen ? edgeLayer.edgeAtScreen(screenX, screenY) : "";
    }
    function handleEdgePressAtScreen(screenX, screenY, button, modifiers) {
        var edgeId = root.edgeAtScreen(screenX, screenY);
        if (!edgeId)
            return false;
        root.forceActiveFocus();
        if (root.clearViewerFocus)
            root.clearViewerFocus();
        root._closeContextMenus();
        root.clearPendingConnection();
        if (button === Qt.LeftButton) {
            var additive = Boolean((modifiers & Qt.ControlModifier) || (modifiers & Qt.ShiftModifier));
            if (additive)
                root.toggleEdgeSelection(edgeId);
            else
                root.setExclusiveEdgeSelection(edgeId);
            return true;
        }
        if (button === Qt.RightButton) {
            root._openEdgeContext(edgeId, screenX, screenY);
            return true;
        }
        return false;
    }
    function _sceneNodePayload(nodeId) { return GraphCanvasRootApi.invoke(sceneState, "sceneNodePayload", [nodeId], null); }
    function _sceneBackdropNodesModel() { return GraphCanvasRootApi.invoke(sceneState, "sceneBackdropNodesModel", [], []); }
    function _sceneAllNodesModel() { return GraphCanvasRootApi.invoke(sceneState, "sceneAllNodesModel", [], []); }
    function _sceneEdgePayload(edgeId) { return GraphCanvasRootApi.invoke(sceneState, "sceneEdgePayload", [edgeId], null); }
    function _liveEdgePayload(edgeId) {
        var edgeLayer = rootLayers.edgeLayerItem;
        var livePayload = edgeLayer && edgeLayer._edgeData ? edgeLayer._edgeData(edgeId) : null;
        return livePayload || root._sceneEdgePayload(edgeId);
    }
    function edgeIdsForEnableToggle(preferredEdgeId) {
        var preferred = String(preferredEdgeId || "").trim();
        var selected = root._normalizeEdgeIds(root.selectedEdgeIds || []);
        var liveSelected = [];
        for (var i = 0; i < selected.length; ++i) {
            if (root._liveEdgePayload(selected[i]))
                liveSelected.push(selected[i]);
        }
        if (preferred.length && !root._liveEdgePayload(preferred))
            return [];
        if (preferred.length && liveSelected.indexOf(preferred) < 0)
            return [preferred];
        return liveSelected;
    }
    function edgeSelectionAllEnabled(preferredEdgeId) {
        var revision = root.edgeTopologyRevision;
        void(revision);
        var edgeIds = root.edgeIdsForEnableToggle(preferredEdgeId);
        if (!edgeIds.length)
            return false;
        for (var i = 0; i < edgeIds.length; ++i) {
            var payload = root._liveEdgePayload(edgeIds[i]);
            if (!payload || payload.enabled === false)
                return false;
        }
        return true;
    }
    function toggleSelectedEdgesEnabled(preferredEdgeId) {
        var edgeIds = root.edgeIdsForEnableToggle(preferredEdgeId);
        if (!edgeIds.length || !root.sceneCommandBridge || !root.sceneCommandBridge.set_edges_enabled)
            return false;
        return Boolean(root.sceneCommandBridge.set_edges_enabled(
            edgeIds,
            !root.edgeSelectionAllEnabled(preferredEdgeId)
        ));
    }
    function setEdgesDisplayMode(edgeIds, mode) {
        var normalized = root._normalizeEdgeIds(edgeIds || []);
        if (!normalized.length || !root.sceneCommandBridge || !root.sceneCommandBridge.set_edges_display_mode)
            return false;
        return Boolean(root.sceneCommandBridge.set_edges_display_mode(normalized, String(mode || "default")));
    }
    function edgeIdsIntersectingScreenRect(screenX, screenY, screenWidth, screenHeight) {
        var edgeLayer = rootLayers.edgeLayerItem;
        return edgeLayer && edgeLayer.edgeIdsIntersectingScreenRect
            ? edgeLayer.edgeIdsIntersectingScreenRect(screenX, screenY, screenWidth, screenHeight)
            : [];
    }
    function edgeEndpointScenePoint(edgeId, endpoint) {
        var edgeLayer = rootLayers.edgeLayerItem;
        return edgeLayer && edgeLayer.edgeEndpointScenePoint
            ? edgeLayer.edgeEndpointScenePoint(edgeId, endpoint)
            : null;
    }
    function jumpToEdgeEndpoint(edgeId, endpoint) {
        var point = root.edgeEndpointScenePoint(edgeId, endpoint);
        if (!point || !root.viewBridge || !root.viewBridge.center_on_scene_point)
            return false;
        root.viewBridge.center_on_scene_point(Number(point.x), Number(point.y));
        return true;
    }
    function _nodeSupportsPassiveStyle(nodeId) { return GraphCanvasRootApi.invoke(sceneState, "nodeSupportsPassiveStyle", [nodeId], false); }
    function _edgeSupportsFlowStyle(edgeId) { return GraphCanvasRootApi.invoke(sceneState, "edgeSupportsFlowStyle", [edgeId], false); }
    function _nodeCanEnterScope(nodeId) { return GraphCanvasRootApi.invoke(sceneState, "nodeCanEnterScope", [nodeId], false); }
    function requestOpenSubnodeScope(nodeId) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "requestOpenSubnodeScope", [nodeId], false); }
    function _nodeSurfaceSelectionBridge() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "_sceneSelectionBridge", [], null); }
    function _nodeSurfacePendingActionBridge() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "_pendingActionBridge", [], null); }
    function _nodeSurfacePropertyBridge() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "_propertyBridge", [], null); }
    function _nodeSurfaceCursorBridge() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "_cursorBridge", [], null); }
    function _nodeSurfacePdfPreviewBridge() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "_pdfPreviewBridge", [], null); }
    function prepareNodeSurfaceControlInteraction(nodeId) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "prepareNodeSurfaceControlInteraction", [nodeId], false); }
    function commitNodeSurfaceProperty(nodeId, key, value) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "commitNodeSurfaceProperty", [nodeId, key, value], false); }
    function commitNodePortLabel(nodeId, portKey, label) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "commitNodePortLabel", [nodeId, portKey, label], false); }
    function requestNodeSurfaceCropEdit(nodeId) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "requestNodeSurfaceCropEdit", [nodeId], false); }
    function consumePendingNodeSurfaceAction(nodeId) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "consumePendingNodeSurfaceAction", [nodeId], false); }
    function commitNodeSurfaceProperties(nodeId, properties) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "commitNodeSurfaceProperties", [nodeId, properties], false); }
    function setNodeSurfaceCursorShape(cursorShape) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "setNodeSurfaceCursorShape", [cursorShape], false); }
    function clearNodeSurfaceCursorShape() { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "clearNodeSurfaceCursorShape", [], false); }
    function describeNodeSurfacePdfPreview(source, pageNumber) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "describeNodeSurfacePdfPreview", [source, pageNumber], ({})); }
    function describeNodeSurfaceImagePreview(source) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "describeNodeSurfaceImagePreview", [source], ({})); }
    function describeNodeSurfaceMailPreview(source) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "describeNodeSurfaceMailPreview", [source], ({})); }
    function resolveNodeSurfaceLocalFileSource(source) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "resolveNodeSurfaceLocalFileSource", [source], ""); }
    function openNodeSurfaceLocalFileSource(source, chooser) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "openNodeSurfaceLocalFileSource", [source, Boolean(chooser)], ({})); }
    function describeNodeSurfaceTabularPreview(properties, request) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "describeNodeSurfaceTabularPreview", [properties, request], ({})); }
    function browseNodePropertyPath(nodeId, key, currentPath) {
        var args = [nodeId, key, currentPath];
        if (arguments.length > 3)
            args.push(arguments[3]);
        return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "browseNodePropertyPath", args, "");
    }
    function internalizeNodePropertyPath(nodeId, key, currentPath) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "internalizeNodePropertyPath", [nodeId, key, currentPath], ""); }
    function pickNodePropertyColor(nodeId, key, currentValue) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "pickNodePropertyColor", [nodeId, key, currentValue], ""); }
    function selectedNodeIds() { return GraphCanvasRootApi.invoke(sceneState, "selectedNodeIds", [], []); }
    function _appendUniqueDragNodeId(nodeIds, seenNodeIds, nodeId) { GraphCanvasRootApi.invoke(sceneState, "_appendUniqueDragNodeId", [nodeIds, seenNodeIds, nodeId]); }
    function _payloadNodeIdList(payload, key) { return GraphCanvasRootApi.invoke(sceneState, "_payloadNodeIdList", [payload, key], []); }
    function _isGroupBackdropPayload(payload) { return GraphCanvasRootApi.invoke(sceneState, "isGroupBackdropPayload", [payload], false); }
    function _appendBackdropDragDescendants(nodeIds, seenNodeIds, backdropNodeId) { GraphCanvasRootApi.invoke(sceneState, "_appendBackdropDragDescendants", [nodeIds, seenNodeIds, backdropNodeId]); }
    function _appendBackdropAwareDragNodeIds(nodeIds, seenNodeIds, nodeId) { GraphCanvasRootApi.invoke(sceneState, "_appendBackdropAwareDragNodeIds", [nodeIds, seenNodeIds, nodeId]); }
    function dragNodeIdsForAnchor(nodeId) { return GraphCanvasRootApi.invoke(sceneState, "dragNodeIdsForAnchor", [nodeId], []); }
    function activeDragNodeIds(nodeId) { return GraphCanvasRootApi.invoke(sceneState, "activeDragNodeIds", [nodeId], []); }
    function setLiveDragOffset(nodeId, dx, dy) { GraphCanvasRootApi.invoke(sceneState, "setLiveDragOffset", [nodeId, dx, dy]); }
    function clearLiveDragOffset() { GraphCanvasRootApi.invoke(sceneState, "clearLiveDragOffset"); }
    function setLiveNodeGeometry(nodeId, x, y, width, height, active) { GraphCanvasRootApi.invoke(sceneState, "setLiveNodeGeometry", [nodeId, x, y, width, height, active]); }
    function clearLiveNodeGeometry() { GraphCanvasRootApi.invoke(sceneState, "clearLiveNodeGeometry"); }
    function _dropTargetInput(sourceDrag, candidate) { return GraphCanvasRootApi.invoke(interactionState, "_dropTargetInput", [sourceDrag, candidate], null); }
    function _isExactDuplicate(sourceDrag, candidate, edge) { return GraphCanvasRootApi.invoke(interactionState, "_isExactDuplicate", [sourceDrag, candidate, edge], false); }
    function _portKind(nodeId, portKey) { return GraphCanvasRootApi.invoke(interactionState, "_portKind", [nodeId, portKey], ""); }
    function _portDataType(nodeId, portKey) { return GraphCanvasRootApi.invoke(interactionState, "_portDataType", [nodeId, portKey], "COREX.DataTypes.Any"); }
    function _arePortKindsCompatible(sourceKind, targetKind) { return GraphCanvasRootApi.invoke(interactionState, "_arePortKindsCompatible", [sourceKind, targetKind], false); }
    function _isDropAllowed(sourceDrag, candidate) { return GraphCanvasRootApi.invoke(interactionState, "_isDropAllowed", [sourceDrag, candidate], false); }
    function _nearestDropCandidateForWireDrag(screenX, screenY, sourceDrag, thresholdOverride, includeInvalid) { return GraphCanvasRootApi.invoke(interactionState, "_nearestDropCandidateForWireDrag", [screenX, screenY, sourceDrag, thresholdOverride, includeInvalid], null); }
    function _areDataTypesCompatible(sourceType, targetType) { return GraphCanvasRootApi.invoke(interactionState, "_areDataTypesCompatible", [sourceType, targetType], false); }
    function _portsCompatibleForAuto(sourcePort, targetPort) { return GraphCanvasRootApi.invoke(interactionState, "_portsCompatibleForAuto", [sourcePort, targetPort], false); }
    function _libraryPorts(payload) { return GraphCanvasRootApi.invoke(interactionState, "_libraryPorts", [payload], []); }
    function _scenePortData(nodeId, portKey) { return GraphCanvasRootApi.invoke(interactionState, "_scenePortData", [nodeId, portKey], null); }
    function _scenePortPoint(node, port, inputRow, outputRow) { return GraphCanvasRootApi.invoke(interactionState, "_scenePortPoint", [node, port, inputRow, outputRow], ({})); }
    function _hasCompatiblePortForTarget(targetPort, nodePorts) { return GraphCanvasRootApi.invoke(interactionState, "_hasCompatiblePortForTarget", [targetPort, nodePorts], false); }
    function _portDropTargetAtScreen(screenX, screenY, payload) { return GraphCanvasRootApi.invoke(interactionState, "_portDropTargetAtScreen", [screenX, screenY, payload], null); }
    function _edgeSupportsDrop(edgeId, payload) { return GraphCanvasRootApi.invoke(interactionState, "_edgeSupportsDrop", [edgeId, payload], false); }
    function _computeLibraryDropTarget(screenX, screenY, payload) { return GraphCanvasRootApi.invoke(interactionState, "_computeLibraryDropTarget", [screenX, screenY, payload], ({})); }
    function _previewNodeMetrics(payload) { return GraphCanvasRootApi.invoke(interactionState, "_previewNodeMetrics", [payload], ({})); }
    function previewNodeMetrics() { return GraphCanvasRootApi.invoke(interactionState, "previewNodeMetrics", [], ({})); }
    function _previewVisiblePorts(payload, direction) { return GraphCanvasRootApi.invoke(interactionState, "_previewVisiblePorts", [payload, direction], []); }
    function previewInputPorts() { return GraphCanvasRootApi.invoke(interactionState, "previewInputPorts", [], []); }
    function previewOutputPorts() { return GraphCanvasRootApi.invoke(interactionState, "previewOutputPorts", [], []); }
    function previewPortColor(kind) { return GraphCanvasRootApi.invoke(interactionState, "previewPortColor", [kind], "transparent"); }
    function previewNodeScreenWidth() { return GraphCanvasRootApi.invoke(interactionState, "previewNodeScreenWidth", [], 0.0); }
    function previewNodeScreenHeight() { return GraphCanvasRootApi.invoke(interactionState, "previewNodeScreenHeight", [], 0.0); }
    function previewPortLabelsVisible() { return GraphCanvasRootApi.invoke(interactionState, "previewPortLabelsVisible", [], false); }
    function clearLibraryDropPreview() { GraphCanvasRootApi.invoke(interactionState, "clearLibraryDropPreview"); }
    function updateLibraryDropPreview(screenX, screenY, payload) { GraphCanvasRootApi.invoke(interactionState, "updateLibraryDropPreview", [screenX, screenY, payload]); }
    function isPointInCanvas(screenX, screenY) { return GraphCanvasRootApi.isPointInCanvas(root, screenX, screenY); }
    function performLibraryDrop(screenX, screenY, payload) { GraphCanvasRootApi.invoke(interactionState, "performLibraryDrop", [screenX, screenY, payload]); }
    function folderExplorerDragPayload(path, isFolder) { return GraphCanvasRootApi.invoke(nodeSurfaceBridge, "folderExplorerDragPayload", [path, isFolder], ({})); }
    function _pathPointerPayload(path, isFolder) {
        return folderExplorerDragPayload(path, isFolder);
    }
    function _pathPointerDataFromDragSource(sourceItem) {
        if (!sourceItem)
            return {"path": "", "isFolder": false, "preferFileDrop": false, "itemCount": 0};
        var payload = sourceItem.dragPayload || null;
        var pointerPath = String(payload && payload.properties ? payload.properties.path || "" : "").trim();
        var pointerMode = String(payload && payload.properties ? payload.properties.mode || "" : "").trim();
        if (!pointerPath.length)
            return {"path": "", "isFolder": false, "preferFileDrop": false, "itemCount": 0};
        return {"path": pointerPath, "isFolder": pointerMode === "folder", "preferFileDrop": false, "itemCount": 1};
    }
    function _pathPointerDataFromDropEvent(eventObj) {
        if (!eventObj)
            return {"path": "", "isFolder": false, "preferFileDrop": false, "itemCount": 0};
        var sourcePointerData = _pathPointerDataFromDragSource(eventObj.source);
        if (sourcePointerData.path.length)
            return sourcePointerData;
        if (eventObj.getDataAsString) {
            var pointerData = String(eventObj.getDataAsString("application/x-corex-path-pointer") || "").trim();
            if (pointerData.length > 0) {
                try {
                    var payload = JSON.parse(pointerData);
                    var pointerPath = String(payload && payload.properties ? payload.properties.path || "" : "").trim();
                    var pointerMode = String(payload && payload.properties ? payload.properties.mode || "" : "").trim();
                    if (pointerPath.length > 0)
                        return {"path": pointerPath, "isFolder": pointerMode === "folder", "preferFileDrop": false, "itemCount": 1};
                } catch (error) {
                }
            }
        }
        if (eventObj.urls && eventObj.urls.length > 0)
            return {"path": String(eventObj.urls[0] || ""), "isFolder": false, "preferFileDrop": true, "itemCount": eventObj.urls.length};
        if (eventObj.getDataAsString) {
            var uriList = String(eventObj.getDataAsString("text/uri-list") || "").trim();
            if (uriList.length > 0) {
                var uriItems = uriList.split(/\r?\n/).filter(function(item) {
                    var normalized = String(item || "").trim();
                    return normalized.length > 0 && normalized.charAt(0) !== "#";
                });
                if (uriItems.length > 0)
                    return {"path": uriItems[0], "isFolder": false, "preferFileDrop": true, "itemCount": uriItems.length};
            }
        }
        if (eventObj.text !== undefined && String(eventObj.text || "").trim().length > 0)
            return {"path": String(eventObj.text || "").trim(), "isFolder": false, "preferFileDrop": true, "itemCount": 1};
        if (eventObj.getDataAsString) {
            var plainText = String(eventObj.getDataAsString("text/plain") || "").trim();
            if (plainText.length > 0)
                return {"path": plainText, "isFolder": false, "preferFileDrop": true, "itemCount": 1};
        }
        return {"path": "", "isFolder": false, "preferFileDrop": false, "itemCount": 0};
    }
    function _pathFromDropEvent(eventObj) {
        return String(_pathPointerDataFromDropEvent(eventObj).path || "");
    }
    function updatePathPointerDropPreview(screenX, screenY, path, isFolder) {
        // The import controller chooses the representation after release.
        // Keep Folder Explorer feedback neutral, just like external drops.
        root.clearLibraryDropPreview();
    }
    function performPathPointerDrop(screenX, screenY, path, isFolder) {
        var targetHost = root._pathPointerDropHostAt(screenX, screenY);
        if (targetHost)
            return root.performPathPointerNodeDrop(targetHost.nodeId, path, isFolder);
        var bridge = root.canvasCommandBridgeRef;
        root.clearLibraryDropPreview();
        if (!bridge || !bridge.request_canvas_import_local_path || !String(path || "").length)
            return false;
        return bridge.request_canvas_import_local_path(String(path), Boolean(isFolder),
            root.screenToSceneX(screenX), root.screenToSceneY(screenY));
    }
    function _acceptExternalCanvasDrop(eventObj) {
        // Internal library/node drags keep their existing gesture owner.
        return !eventObj.source || root._pathPointerDataFromDragSource(eventObj.source).path.length > 0;
    }
    function performExternalCanvasDrop(drop) {
        var bridge = root.canvasCommandBridgeRef;
        root.clearLibraryDropPreview();
        if (!bridge || !bridge.request_canvas_import_drop)
            return false;
        var pointer = root._pathPointerDataFromDragSource(drop.source);
        if (pointer.path.length)
            return root.performPathPointerDrop(drop.x, drop.y, pointer.path, pointer.isFolder);
        var urls = [];
        for (var i = 0; drop.urls && i < drop.urls.length; i++)
            urls.push(String(drop.urls[i]));
        var text = drop.text !== undefined ? String(drop.text || "") : "";
        var html = drop.html !== undefined ? String(drop.html || "") : "";
        return bridge.request_canvas_import_drop(urls, text, html,
            root.screenToSceneX(drop.x), root.screenToSceneY(drop.y));
    }
    function _pathPointerDropHostAt(screenX, screenY) {
        var hosts = rootLayers && rootLayers._allVisibleNodeHosts
            ? rootLayers._allVisibleNodeHosts()
            : [];
        var match = null;
        for (var i = 0; i < hosts.length; i++) {
            var host = hosts[i];
            if (!host || !host.visible || !host.pathPointerDropTarget)
                continue;
            var localPoint = host.mapFromItem(root, Number(screenX), Number(screenY));
            if (localPoint.x < 0 || localPoint.y < 0 || localPoint.x > host.width || localPoint.y > host.height)
                continue;
            if (!match || Number(host.z) >= Number(match.z))
                match = host;
        }
        return match;
    }
    function performPathPointerNodeDrop(nodeId, path, isFolder) {
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedPath = String(path || "").trim();
        var host = root.hostForNodeId(normalizedNodeId);
        var bridge = root.canvasCommandBridgeRef;
        root.clearLibraryDropPreview();
        if (!normalizedNodeId.length || !normalizedPath.length || !host || !host.pathPointerDropWritable)
            return false;
        if (!bridge || !bridge.request_update_path_pointer_node)
            return false;
        root._closeContextMenus();
        root.clearPendingConnection();
        root.prepareNodeSurfaceControlInteraction(normalizedNodeId);
        var updated = Boolean(bridge.request_update_path_pointer_node(
            normalizedNodeId,
            normalizedPath,
            Boolean(isFolder)
        ));
        root.clearEdgeSelection();
        root.forceActiveFocus();
        return updated;
    }
    function _samePort(a, b) { return GraphCanvasRootApi.invoke(interactionState, "_samePort", [a, b], false); }
    function clearPendingConnection() { GraphCanvasRootApi.invoke(interactionState, "clearPendingConnection"); }
    function _wireDragSourceData(state) { return GraphCanvasRootApi.invoke(interactionState, "_wireDragSourceData", [state], null); }
    function wireDragSourcePort() { return GraphCanvasRootApi.invoke(interactionState, "wireDragSourcePort", [], null); }
    function wireDragPreviewConnection() { return GraphCanvasRootApi.invoke(interactionState, "wireDragPreviewConnection", [], null); }
    function _updateWireDropCandidate(screenX, screenY, state) { GraphCanvasRootApi.invoke(interactionState, "_updateWireDropCandidate", [screenX, screenY, state]); }
    function _clearWireDragState() { GraphCanvasRootApi.invoke(interactionState, "_clearWireDragState"); }
    function beginPortWireDrag(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers) { GraphCanvasRootApi.invoke(interactionState, "beginPortWireDrag", [nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers]); }
    function updatePortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) { GraphCanvasRootApi.invoke(interactionState, "updatePortWireDrag", [nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers]); }
    function finishPortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) { GraphCanvasRootApi.invoke(interactionState, "finishPortWireDrag", [nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers]); }
    function cancelWireDrag() { return GraphCanvasRootApi.invoke(interactionState, "cancelWireDrag", [], false); }
    function handlePortClick(nodeId, portKey, direction, sceneX, sceneY, modifiers) { GraphCanvasRootApi.invoke(interactionState, "handlePortClick", [nodeId, portKey, direction, sceneX, sceneY, modifiers]); }
    function _syncEdgePayload() { GraphCanvasRootApi.invoke(sceneState, "syncEdgePayload"); }
    function requestEdgeRedraw() { GraphCanvasRootApi.invoke(sceneLifecycle, "requestEdgeRedraw"); }
    function requestViewStateRedraw() { GraphCanvasRootApi.invoke(viewportController, "requestViewStateRedraw"); }
    function flushViewStateRedraw() { GraphCanvasRootApi.invoke(viewportController, "flushViewStateRedraw"); }
    function forceExactVisibleSceneModels() { return rootLayers.forceExactVisibleSceneModels(); }
    function _closeContextMenus() { GraphCanvasRootApi.invoke(interactionState, "_closeContextMenus"); }
    function _clampMenuPosition(x, y, menuWidth, menuHeight) { return GraphCanvasRootApi.clampMenuPosition(root, x, y, menuWidth, menuHeight); }
    function _openEdgeContext(edgeId, x, y) { GraphCanvasRootApi.invoke(interactionState, "_openEdgeContext", [edgeId, x, y]); }
    function _openNodeContext(nodeId, x, y) { GraphCanvasRootApi.invoke(interactionState, "_openNodeContext", [nodeId, x, y]); }
    function _openSelectionContext(x, y) { GraphCanvasRootApi.invoke(interactionState, "_openSelectionContext", [x, y]); }
    function _openSelectionContextAtScene(sceneX, sceneY) { GraphCanvasRootApi.invoke(interactionState, "_openSelectionContextAtScene", [sceneX, sceneY]); }
    function _openCanvasOptions(x, y) { GraphCanvasRootApi.invoke(interactionState, "_openCanvasOptions", [x, y]); }
    function _openCanvasOptionsAtScene(sceneX, sceneY) { GraphCanvasRootApi.invoke(interactionState, "_openCanvasOptionsAtScene", [sceneX, sceneY]); }
    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
    }
    function requestOpenLockedNodeStatusAction() {
        if (!root.lockedNodeStatusActionVisible)
            return false;
        return true;
    }

    function clearViewerFocus() { return GraphCanvasRootApi.invoke(actionRouter, "clearViewerFocus", [], false); }

    function applyLiveDragOffsetToHosts() {
        return rootLayers.applyLiveDragOffsetToHosts();
    }

    function applyLiveDragOffsetToHost(host) {
        return rootLayers.applyLiveDragOffsetToHost(host);
    }

    function openSurfaceActionOverlayForHost(host, actionId, surface) {
        return rootLayers.openSurfaceActionOverlayForHost(host, actionId, surface);
    }

    function exportCanvasBasePng(request) {
        rootLayers.exportCanvasBasePng(request || {}, function(result) {
            root.canvasBasePngExportFinished(result || {});
        });
    }

    GraphCanvasComponents.GraphCanvasRootLayers {
        id: rootLayers
        canvasItem: root
        sceneStateBridge: root.sceneStateBridge
        viewStateBridge: root.viewBridge
        viewCommandBridge: root.viewBridge
        canvasActionRouter: root.canvasActionRouter
        themePalette: root.themePalette
        graphNodePalette: root.graphNodePalette
    }

    Binding {
        target: rootLayers.edgeLayerItem
        property: "frameScheduler"
        value: frameScheduler
        restoreMode: Binding.RestoreNone
    }

    Item {
        id: osPathDropLayer
        objectName: "graphCanvasOsPathDropLayer"
        anchors.fill: parent
        z: -5

        DropArea {
            id: osPathDropArea
            objectName: "graphCanvasOsPathDropArea"
            anchors.fill: parent
            keys: ["text/uri-list", "text/plain", "text/html", "image/*", "video/*",
                "application/pdf", "application/x-qt-image", "application/x-corex-path-pointer"]

            onEntered: function(drag) {
                drag.accepted = root._acceptExternalCanvasDrop(drag);
                if (drag.accepted)
                    drag.accept(Qt.CopyAction);
            }

            onPositionChanged: function(drag) {
                drag.accepted = root._acceptExternalCanvasDrop(drag);
                if (drag.accepted)
                    drag.accept(Qt.CopyAction);
            }

            onExited: root.clearLibraryDropPreview()

            onDropped: function(drop) {
                if (!root._acceptExternalCanvasDrop(drop))
                    return;
                if (root.performExternalCanvasDrop(drop))
                    drop.accept(Qt.CopyAction);
            }
        }
    }

    Item {
        id: lockedNodeStatusRibbon
        objectName: "graphCanvasLockedNodeStatusRibbon"
        visible: root.lockedNodeStatusVisible
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 12
        height: 28
        z: 7

        Rectangle {
            id: lockedNodeStatusPill
            objectName: "graphCanvasLockedNodeStatusPill"
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.ceil(lockedNodeStatusTextItem.implicitWidth) + 20
            height: 24
            radius: 4
            color: "#151b26"
            opacity: 0.84
            border.width: 1
            border.color: "#2d3442"

            Text {
                id: lockedNodeStatusTextItem
                objectName: "graphCanvasLockedNodeStatusText"
                anchors.centerIn: parent
                text: root.lockedNodeStatusText
                color: root.lockedNodeStatusMutedTextColor
                font.pixelSize: 11
                font.weight: Font.Medium
                renderType: Text.CurveRendering
            }
        }

        Rectangle {
            id: lockedNodeStatusAction
            objectName: "graphCanvasLockedNodeStatusAction"
            visible: root.lockedNodeStatusActionVisible
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Math.ceil(lockedNodeStatusActionText.implicitWidth) + 22
            height: 24
            radius: 4
            color: root.lockedNodeStatusActionColor
            border.width: 1
            border.color: Qt.lighter(root.lockedNodeStatusActionColor, 1.12)

            Text {
                id: lockedNodeStatusActionText
                objectName: "graphCanvasLockedNodeStatusActionText"
                anchors.centerIn: parent
                text: "Load missing add-ons"
                color: "#f7fbff"
                font.pixelSize: 11
                font.weight: Font.DemiBold
                renderType: Text.CurveRendering
            }

            MouseArea {
                objectName: "graphCanvasLockedNodeStatusActionMouseArea"
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.requestOpenLockedNodeStatusAction()
            }
        }
    }

    Item {
        id: canvasOptionsGearButton
        objectName: "graphCanvasOptionsGearButton"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 8
        anchors.rightMargin: 8
        width: 36
        height: 36
        visible: root.showCanvasOptionsButton
        enabled: root.showCanvasOptionsButton
        z: 860

        readonly property bool hovered: canvasOptionsGearMouseArea.containsMouse
        readonly property color accentColor: root.themePalette && root.themePalette.accent !== undefined
            ? root.themePalette.accent
            : "#60CDFF"
        readonly property color panelColor: root.themePalette && root.themePalette.panel_bg !== undefined
            ? root.themePalette.panel_bg
            : "#1b1d22"
        readonly property color borderColor: root.themePalette && root.themePalette.input_border !== undefined
            ? root.themePalette.input_border
            : "#4a4f5a"
        readonly property color iconColor: root.canvasOptionsVisible || hovered
            ? accentColor
            : (root.themePalette && root.themePalette.panel_title_fg !== undefined
                ? root.themePalette.panel_title_fg
                : "#f0f4fb")

        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 4
            anchors.leftMargin: 1
            radius: width / 2
            color: Qt.alpha("#000000", 0.18)
        }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: canvasOptionsGearButton.panelColor
            border.width: 1
            border.color: root.canvasOptionsVisible || canvasOptionsGearButton.hovered
                ? Qt.alpha(canvasOptionsGearButton.accentColor, 0.78)
                : Qt.alpha(canvasOptionsGearButton.borderColor, 0.92)
        }

        Image {
            anchors.centerIn: parent
            width: 19
            height: 19
            sourceSize.width: 19
            sourceSize.height: 19
            source: root._iconSource("settings", 19, String(canvasOptionsGearButton.iconColor))
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        MouseArea {
            id: canvasOptionsGearMouseArea
            objectName: "graphCanvasOptionsGearMouseArea"
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.forceActiveFocus();
                if (root.canvasOptionsVisible) {
                    root._closeContextMenus();
                    return;
                }
                var menuWidth = 252;
                var localX = canvasOptionsGearButton.x + canvasOptionsGearButton.width - menuWidth;
                var localY = canvasOptionsGearButton.y + canvasOptionsGearButton.height + 8;
                root._openCanvasOptions(localX, localY);
            }
        }
    }

    function hostForNodeId(nodeId) {
        return rootLayers.hostForNodeId(nodeId);
    }

    function requestInlineRenameForNode(nodeId) {
        var host = rootLayers.hostForNodeId(nodeId);
        if (host && host.beginInlineTitleEdit)
            return host.beginInlineTitleEdit();
        return false;
    }

    function requestAddNodeLinkForNode(nodeId) {
        var normalizedNodeId = String(nodeId || "").trim();
        if (!normalizedNodeId.length)
            return false;
        if (root.sceneCommandBridge && root.sceneCommandBridge.select_node)
            root.sceneCommandBridge.select_node(normalizedNodeId, false);
        var nodeData = root._sceneNodePayload(normalizedNodeId);
        if (!nodeData)
            return false;
        var workspaceId = root.shellWorkspaceBridgeRef
            ? String(root.shellWorkspaceBridgeRef.active_workspace_id || "")
            : "";
        return root.openNodeLinkEditor(nodeData, workspaceId);
    }

    function requestNodeCommentEditorForNode(nodeId, compose) {
        var normalizedNodeId = String(nodeId || "").trim();
        if (!normalizedNodeId.length)
            return false;
        if (root.sceneCommandBridge && root.sceneCommandBridge.select_node)
            root.sceneCommandBridge.select_node(normalizedNodeId, false);
        root.nodeCommentEditorRequested(normalizedNodeId, Boolean(compose));
        return true;
    }

    function openNodeCommentEditor(nodeData, compose) {
        return rootLayers.openNodeCommentEditor(nodeData, compose);
    }

    function openNodeLinkEditor(nodeData, workspaceId) {
        return rootLayers.openNodeLinkEditor(nodeData, workspaceId);
    }

    function requestNodeLinkTargetPick(kind, sourceWorkspaceId, sourceNodeId) {
        var normalizedKind = String(kind || "").toLowerCase();
        var normalizedWorkspaceId = String(sourceWorkspaceId || "").trim();
        var normalizedNodeId = String(sourceNodeId || "").trim();
        if ((normalizedKind !== "node" && normalizedKind !== "workspace")
                || !normalizedWorkspaceId.length || !normalizedNodeId.length)
            return false;
        root.nodeLinkTargetPickRequested(normalizedKind, normalizedWorkspaceId, normalizedNodeId);
        return true;
    }

    function applyNodeLinkTargetPick(kind, workspaceId, nodeId, label, subtitle) {
        return rootLayers.applyNodeLinkTargetPick(kind, workspaceId, nodeId, label, subtitle);
    }

    function resumeNodeLinkEditorAfterPickCancel() {
        return rootLayers.resumeNodeLinkEditorAfterPickCancel();
    }

    function abortNodeLinkEditorAfterSourceLoss() {
        return rootLayers.abortNodeLinkEditorAfterSourceLoss();
    }

    function completeNodeLinkTargetPick(nodeId) {
        if (!root.nodeLinkTargetPickActive)
            return false;
        var normalizedNodeId = String(nodeId || "").trim();
        if (!normalizedNodeId.length)
            return false;
        var payload = root._sceneNodePayload(normalizedNodeId);
        var label = payload ? String(payload.title || payload.display_name || normalizedNodeId) : normalizedNodeId;
        var subtitleParts = [];
        if (payload && String(payload.display_name || "").trim().length)
            subtitleParts.push(String(payload.display_name || "").trim());
        if (payload && String(payload.type_id || "").trim().length)
            subtitleParts.push(String(payload.type_id || "").trim());
        root.nodeLinkTargetPicked(
            String(root.nodeLinkTargetPickWorkspaceId || ""),
            normalizedNodeId,
            label,
            subtitleParts.join(" - ")
        );
        return true;
    }

    function cancelNodeLinkTargetPick() {
        if (!root.nodeLinkTargetPickCancelActive)
            return false;
        root.nodeLinkTargetPickCancelled();
        return true;
    }

    function showNodeLinkHoverCard(nodeId, linkId, sceneX, sceneY) {
        return rootLayers.showNodeLinkHoverCard(nodeId, linkId, sceneX, sceneY);
    }

    function scheduleNodeLinkHoverDismiss() {
        rootLayers.scheduleNodeLinkHoverDismiss();
    }

    GraphCanvasComponents.GraphCanvasInputLayers {
        id: inputLayers
        objectName: "graphCanvasInputLayers"
        anchors.fill: parent
        canvasItem: root
        canvasActionRouter: root.canvasActionRouter
        graphActionBridge: root.graphActionBridgeRef
        canvasCommandBridge: root.canvasCommandBridgeRef
        sceneCommandBridge: root.sceneCommandBridge
        viewStateBridge: root.viewBridge
        viewCommandBridge: root.viewBridge
        z: -1
        themePalette: root.themePalette
        boxZoomDragThreshold: root.boxZoomDragThreshold
        boxZoomPaddingPx: root.boxZoomPaddingPx
    }

    GraphCanvasComponents.GraphCanvasContextMenus {
        id: contextMenus
        objectName: "graphCanvasContextMenus"
        canvasItem: root
        canvasActionRouter: root.canvasActionRouter
        commandBridge: root.canvasCommandBridgeRef
        graphActionBridge: root.graphActionBridgeRef
        themePalette: root.themePalette
    }

    function _resetCanvasSceneState() {
        rootLayers.clearRetainedWebPages();
        GraphCanvasRootApi.invoke(sceneLifecycle, "resetCanvasSceneState");
    }

    onCanvasStateBridgeChanged: root._resetCanvasSceneState()
    onCanvasCommandBridgeChanged: root._resetCanvasSceneState()
    onCanvasViewBridgeChanged: {
        root._resetCanvasSceneState()
        viewportController.scheduleViewportSizeUpdate()
    }
    onSceneBridgeChanged: root._resetCanvasSceneState()
    onWidthChanged: viewportController.scheduleViewportSizeUpdate()
    onHeightChanged: viewportController.scheduleViewportSizeUpdate()

    Component.onCompleted: viewportController.scheduleViewportSizeUpdate()

    Component.onDestruction: {
        interactionIdleTimer.stop();
        interactionState.releaseHostReferences();
    }
}
