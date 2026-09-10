import QtQuick 2.15
import "GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics
import "GraphActionPresentation.js" as GraphActionPresentation

Item {
    id: card
    objectName: "graphNodeCard"
    property var nodeData: null
    readonly property string nodeId: String(nodeData ? nodeData.node_id || "" : "").trim()
    readonly property bool hasNodeIdentity: nodeId.length > 0
    property real worldOffset: 0
    property Item canvasItem: null
    property var frameScheduler: null
    property var renderActivationSceneRectPayload: ({})
    property var visibleSceneRectPayload: ({})
    property string contextTargetNodeId: ""
    property var hoveredPort: null
    property var previewPort: null
    property var pendingPort: null
    property var dragSourcePort: null
    property real liveDragDx: 0
    property real liveDragDy: 0
    property bool showShadow: false
    property int shadowStrength: 70
    property int shadowSoftness: 50
    property int shadowOffset: 4
    property bool viewportInteractionCacheActive: false
    property bool snapshotReuseActive: false
    property bool showPortLabelsPreference: true
    property bool portLayerActive: true
    property bool edgeHitPassthroughEnabled: false
    property int graphLabelPixelSize: 10
    property string surfaceVariantOverride: ""
    readonly property var graphBrowserStateSink: card

    QtObject {
        id: webPageBrowserStateSink
        // Persists web-page browser state ({current_url, zoom_factor}) for a
        // canvas web node directly through the scene command bridge. Does NOT
        // use commitNodeSurfaceProperty: that force-selects the node, which
        // would hijack selection on every navigate/zoom while browsing.
        function browserStatePersistenceEnabled() {
            var value = undefined;
            if (card.nodeData && card.nodeData.properties && typeof card.nodeData.properties === "object")
                value = card.nodeData.properties.persist_browser_state;
            if ((value === undefined || value === null) && card.nodeData && card.nodeData.web_page_payload && typeof card.nodeData.web_page_payload === "object")
                value = card.nodeData.web_page_payload.persist_browser_state;
            if (value === undefined || value === null)
                return true;
            var text = String(value).trim().toLowerCase();
            return !(text === "0" || text === "false" || text === "no" || text === "off");
        }

        function persistWebPageBrowserState(state) {
            if (!card.canvasItem || !card.nodeData || card.graphReadOnly)
                return false;
            var nodeId = String(card.nodeData.node_id || "");
            if (!nodeId.length)
                return false;
            if (!browserStatePersistenceEnabled())
                return false;
            var payload = state || ({});
            var currentUrl = String(payload.current_url || "").trim();
            if (!currentUrl.length)
                return false;
            var zoom = Number(payload.zoom_factor);
            if (!isFinite(zoom) || zoom <= 0.0)
                zoom = 1.0;
            zoom = Math.max(0.25, Math.min(3.0, zoom));
            var bridge = card.canvasItem.sceneCommandBridge;
            if (!bridge)
                return false;
            var browserState = {
                "current_url": currentUrl,
                "zoom_factor": zoom
            };
            try {
                if (bridge.set_node_properties)
                    return Boolean(bridge.set_node_properties(nodeId, {"browser_state": browserState}));
            } catch (error) {
                // Fall back to older command bridges that only expose the
                // single-property slot.
            }
            try {
                bridge.set_node_property(nodeId, "browser_state", browserState);
                return true;
            } catch (error) {
                return false;
            }
        }
    }

    function persistWebPageBrowserState(state) {
        return webPageBrowserStateSink.persistWebPageBrowserState(state);
    }
    readonly property int effectiveGraphLabelPixelSize: {
        var numeric = NaN;
        if (card.prefs)
            numeric = Number(card.prefs.graphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = Number(card.graphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = 10;
        return Math.max(8, Math.min(18, Math.round(numeric)));
    }
    readonly property int effectiveNodeTitleIconPixelSize: {
        var numeric = NaN;
        if (card.prefs)
            numeric = Number(card.prefs.nodeTitleIconPixelSize);
        if (!isFinite(numeric))
            numeric = Number(card.effectiveGraphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = Number(card.graphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = 10;
        return Math.max(8, Math.min(50, Math.round(numeric)));
    }

    GraphNodeHostTheme {
        id: themeState
        host: card
    }

    GraphSharedTypography {
        id: sharedTypographyState
        graphLabelPixelSize: card.effectiveGraphLabelPixelSize
        graphNodeIconPixelSize: card.effectiveNodeTitleIconPixelSize
    }

    GraphNodeHostLayout {
        id: chromeLayout
        host: card
    }

    GraphNodeHostRenderQuality {
        id: renderQualityState
        host: card
    }

    GraphNodeHostSceneAccess {
        id: sceneAccess
        host: card
    }

    GraphNodeHostInteractionState {
        id: interactionState
        host: card
        surfaceLoader: surfaceLoader
        headerLayer: headerLayer
        settingsGroupsLayer: settingsGroupsLayer
        portsLayer: portsLayer
    }

    readonly property var shellContextRef: typeof shellContext !== "undefined" ? shellContext : null
    readonly property var graphThemeBridgeRef: shellContextRef ? shellContextRef.graphThemeBridge : null
    readonly property var addonManagerBridgeRef: shellContextRef && shellContextRef.addonManagerBridge
        ? shellContextRef.addonManagerBridge
        : null
    readonly property var nodePalette: graphThemeBridgeRef
        ? graphThemeBridgeRef.node_palette
        : ({})
    readonly property var portKindPalette: graphThemeBridgeRef
        ? graphThemeBridgeRef.port_kind_palette
        : ({})
    readonly property var portStatePalette: graphThemeBridgeRef
        ? graphThemeBridgeRef.port_state_palette
        : ({})
    readonly property var selectedNodeLookup: {
        var bridge = canvasItem ? canvasItem.sceneBridge : null;
        return bridge ? bridge.selected_node_lookup : ({});
    }
    // Shared facts objects passed by reference from the canvas. Children and
    // overlays read host.executionFacts.<fact> / host.prefs.<fact> directly;
    // this host stays closed for new canvas-level fact pass-throughs (see
    // tests/test_qml_drill_budget.py).
    readonly property var executionFacts: canvasItem ? canvasItem.executionFacts : null
    readonly property var prefs: canvasItem ? canvasItem.prefs : null
    readonly property string nodeHelpTooltipText: headerLayer.nodeHelpText
    readonly property var nodeHelpTooltipPolicyBridge: headerLayer.tooltipPolicyBridge
    readonly property string nodeHelpTooltipPlacement: headerLayer.nodeTooltipPlacement
    readonly property real nodeHelpTooltipAnchorScale: headerLayer.nodeTooltipAnchorScale
    readonly property bool isSelected: !!nodeData
        && Boolean(selectedNodeLookup[String(nodeData.node_id || "")])
    readonly property bool isFailedNode: !!nodeData && !!executionFacts
        && Boolean(executionFacts.failedNodeLookup[String(nodeData.node_id || "")])
    readonly property bool isRunningNode: !!nodeData && !!executionFacts
        && Boolean(executionFacts.runningNodeLookup[String(nodeData.node_id || "")])
    readonly property bool isCompletedNode: !!nodeData && !!executionFacts
        && Boolean(executionFacts.completedNodeLookup[String(nodeData.node_id || "")])
    readonly property bool isWarningNode: !!nodeData && !!executionFacts
        && Boolean(executionFacts.warningNodeLookup[String(nodeData.node_id || "")])
    readonly property var nodeDiagnostic: !!nodeData && !!executionFacts
        && typeof executionFacts.nodeDiagnosticLookup !== "undefined"
        ? (executionFacts.nodeDiagnosticLookup[String(nodeData.node_id || "")] || ({}))
        : ({})
    readonly property bool isDiagnosticWarningNode: String(nodeDiagnostic.severity || "") === "warning"
    readonly property bool isWarningChromeNode: isWarningNode || isDiagnosticWarningNode
    readonly property bool isFreshRunNode: !!nodeData && !!executionFacts
        && Boolean(executionFacts.freshRunNodeLookup[String(nodeData.node_id || "")])
    readonly property string selectedRunPreviewTone: !!nodeData && !!executionFacts
        ? String(executionFacts.selectedRunPreviewNodeLookup[String(nodeData.node_id || "")] || "")
        : ""
    readonly property bool isSelectedRunPreviewNode: selectedRunPreviewTone.length > 0
    readonly property string executionNodeId: !!nodeData ? String(nodeData.node_id || "") : ""
    readonly property int executionStateRevision: executionFacts ? Number(executionFacts.nodeExecutionRevision || 0) : 0
    readonly property double runningNodeStartedAtMs: {
        var lookup = card.executionFacts ? card.executionFacts.runningNodeStartedAtMsLookup : ({});
        var numeric = card._lookupExecutionTimingValue(lookup, false);
        return isFinite(numeric) ? numeric : 0.0;
    }
    readonly property bool hasCachedExecutionElapsedMs: isFinite(
        card._lookupExecutionTimingValue(
            card.executionFacts ? card.executionFacts.nodeElapsedMsLookup : ({}),
            true
        )
    )
    readonly property double cachedExecutionElapsedMs: {
        var lookup = card.executionFacts ? card.executionFacts.nodeElapsedMsLookup : ({});
        var numeric = card._lookupExecutionTimingValue(lookup, true);
        return isFinite(numeric) ? numeric : 0.0;
    }
    readonly property string nodeElapsedTimeVisibility: card.prefs
        ? String(card.prefs.nodeElapsedTimeVisibility || "always")
        : "always"
    // ponytail: fixed primitive list; move this policy to node metadata if exclusions multiply.
    readonly property bool elapsedTimeSuppressedForNode: ["data.boolean_toggle", "data.number_slider", "data.select", "core.trigger", "core.constant"].indexOf(
        String(card.nodeData ? card.nodeData.type_id || "" : "")
    ) >= 0
    readonly property bool liveExecutionElapsedVisible: !card.elapsedTimeSuppressedForNode
        && card.nodeElapsedTimeVisibility !== "off"
        && !card.isFailedNode
        && card.isRunningNode
        && card.runningNodeStartedAtMs > 0.0
    readonly property bool cachedExecutionElapsedVisible: !card.elapsedTimeSuppressedForNode
        && card.nodeElapsedTimeVisibility === "always"
        && !card.isFailedNode
        && !card.isRunningNode
        && card.hasCachedExecutionElapsedMs
    readonly property var surfaceSpec: _surfaceSpecFromNodeData()
    readonly property var surfaceInputCapabilities: _surfaceContractObject(surfaceSpec.input_capabilities)
    readonly property var surfaceFullscreen: _surfaceContractObject(surfaceSpec.fullscreen)
    readonly property bool surfaceFullscreenSupported: Boolean(surfaceFullscreen.supported)
    readonly property bool surfaceFullscreenRequiresBridge: surfaceFullscreen.requires_bridge === undefined
        ? true
        : Boolean(surfaceFullscreen.requires_bridge)
    readonly property var surfaceFullscreenBridgeRef: typeof contentFullscreenBridge !== "undefined" && contentFullscreenBridge
        ? contentFullscreenBridge
        : null
    readonly property bool surfaceFullscreenAvailable: surfaceFullscreenSupported
        && !!nodeData
        && String(nodeData.node_id || "").length > 0
        && (!surfaceFullscreenRequiresBridge || surfaceFullscreenBridgeRef)
    readonly property string surfaceFamily: String(surfaceSpec.family || "standard")
    readonly property string surfaceVariant: String(surfaceVariantOverride || surfaceSpec.variant || (nodeData ? nodeData.surface_variant || "" : ""))
    readonly property var surfaceMetadata: _surfaceContractObject(surfaceSpec.metadata)
    readonly property string surfaceIdentityKey: [
        nodeData ? String(nodeData.node_id || "") : "",
        surfaceFamily,
        surfaceVariant,
        String(surfaceSpec && surfaceSpec.component_key ? surfaceSpec.component_key : "standard"),
        String(surfaceSpec && surfaceSpec.qml_component ? surfaceSpec.qml_component : "GraphStandardNodeSurface.qml"),
        lockedPlaceholderActive ? "locked" : "surface"
    ].join("|")
    readonly property bool isBareTextAnnotationSurface: isPassiveNode
        && surfaceFamily === "annotation"
        && surfaceVariant === "text"
        && String(surfaceSpec && surfaceSpec.component_key ? surfaceSpec.component_key : "") === "annotation_text"
    readonly property bool panelLikeSurface: Boolean(surfaceMetadata.panel_like)
    readonly property bool suppressRunAction: Boolean(surfaceMetadata.suppress_run_action)
    readonly property bool chromeToggleCapableSurface: (surfaceFamily === "media"
            && (surfaceVariant === "media_panel" || surfaceVariant === "mail_panel"))
        || (surfaceFamily === "web" && surfaceVariant === "page_viewer")
    readonly property var nodeProperties: nodeData && nodeData.properties ? nodeData.properties : ({})
    readonly property bool nodeChromeTitleVisible: !chromeToggleCapableSurface || card._nodePropertyBool("show_title", true)
    readonly property bool nodeChromeFrameVisible: !chromeToggleCapableSurface || card._nodePropertyBool("show_frame", true)
    readonly property bool nodeChromeContentOnlyActive: chromeToggleCapableSurface
        && !nodeChromeTitleVisible
        && !nodeChromeFrameVisible
    readonly property var renderQuality: renderQualityState.renderQuality
    // Most nodes only negotiate reduced/proxy quality during snapshot reuse.
    // Heavy proxy-capable media/viewer surfaces also demote during transient
    // max-performance viewport interaction because the world cache alone does
    // not avoid their bitmap resampling cost.
    readonly property bool reducedQualityRequested: renderQualityState.reducedQualityRequested
    readonly property string requestedQualityTier: renderQualityState.requestedQualityTier
    readonly property bool proxySurfaceCapable: renderQualityState.proxySurfaceCapable
    readonly property bool proxySurfaceRequested: renderQualityState.proxySurfaceRequested
    readonly property string resolvedQualityTier: renderQualityState.resolvedQualityTier
    readonly property var surfaceQualityContext: renderQualityState.surfaceQualityContext
    readonly property bool isFlowchartSurface: surfaceFamily === "flowchart"
    readonly property bool isNumberSliderSurface: surfaceFamily === "standard"
        && surfaceVariant === "number_slider"
    readonly property bool isBooleanToggleSurface: surfaceFamily === "standard"
        && surfaceVariant === "boolean_toggle"
    readonly property bool isSelectSurface: surfaceFamily === "standard"
        && surfaceVariant === "select"
    readonly property bool isPanelSurface: surfaceFamily === "standard"
        && surfaceVariant === "panel"
    readonly property bool isTriggerSurface: surfaceFamily === "standard"
        && surfaceVariant === "trigger"
    readonly property bool isCompactPillSurface: isNumberSliderSurface || isBooleanToggleSurface
        || isSelectSurface || isTriggerSurface
    readonly property bool usesCardinalNeutralFlowHandles: !!nodeData
        && GraphNodeSurfaceMetrics.nodeUsesCardinalNeutralFlowHandles(nodeData)
    readonly property string runtimeBehavior: String(nodeData && nodeData.runtime_behavior || "").toLowerCase()
    readonly property bool isActiveWireNode: runtimeBehavior === "active" || runtimeBehavior === "compile_only"
    readonly property bool isPassiveNode: runtimeBehavior === "passive"
    readonly property bool lockEligible: !!nodeData && String(nodeData.type_id || "").indexOf("passive.") === 0
    readonly property bool authorLocked: lockEligible && Boolean(nodeData.locked)
    readonly property bool lockedInteractionEnabled: !!canvasItem && Boolean(canvasItem.interactWithLockedObjects)
    readonly property var passiveStyle: themeState.passiveStyle
    readonly property string _passiveFillOverride: themeState.passiveFillOverride
    readonly property string _passiveBorderOverride: themeState.passiveBorderOverride
    readonly property string _passiveTextOverride: themeState.passiveTextOverride
    readonly property bool hasPassiveFillOverride: themeState.hasPassiveFillOverride
    readonly property bool hasPassiveBorderOverride: themeState.hasPassiveBorderOverride
    readonly property bool hasPassiveTextOverride: themeState.hasPassiveTextOverride
    readonly property color themeSurfaceColor: themeState.themeSurfaceColor
    readonly property color themeOutlineColor: themeState.themeOutlineColor
    readonly property color themeSelectedOutlineColor: themeState.themeSelectedOutlineColor
    readonly property color themeHeaderTextColor: themeState.themeHeaderTextColor
    readonly property color themeScopeBadgeColor: themeState.themeScopeBadgeColor
    readonly property color themeScopeBadgeBorderColor: themeState.themeScopeBadgeBorderColor
    readonly property color themeScopeBadgeTextColor: themeState.themeScopeBadgeTextColor
    readonly property color themeInlineRowColor: themeState.themeInlineRowColor
    readonly property color themeInlineRowBorderColor: themeState.themeInlineRowBorderColor
    readonly property color themeInlineLabelColor: themeState.themeInlineLabelColor
    readonly property color themeInlineInputTextColor: themeState.themeInlineInputTextColor
    readonly property color themeInlineInputBackgroundColor: themeState.themeInlineInputBackgroundColor
    readonly property color themeInlineInputBorderColor: themeState.themeInlineInputBorderColor
    readonly property color themeInlineDrivenTextColor: themeState.themeInlineDrivenTextColor
    readonly property color themePortLabelColor: themeState.themePortLabelColor
    readonly property color flowchartDefaultFillColor: themeState.flowchartDefaultFillColor
    readonly property color flowchartDefaultOutlineColor: themeState.flowchartDefaultOutlineColor
    readonly property color flowchartDefaultTextColor: themeState.flowchartDefaultTextColor
    // readonly property color surfaceColor: themeState.surfaceColor
    readonly property color surfaceColor: card.lockedPlaceholderActive
        ? card.lockedPlaceholderSurfaceColor
        : themeState.surfaceColor
    readonly property color outlineColor: card.lockedPlaceholderActive
        ? card.lockedPlaceholderOutlineColor
        : themeState.outlineColor
    readonly property string semanticChromeState: themeState.activeSemanticState
    readonly property color selectedOutlineColor: themeState.selectedOutlineColor
    readonly property color selectedGlowColor: themeState.selectedGlowColor
    readonly property bool bodyGradientActive: themeState.bodyGradientActive
    readonly property color bodyGradientStartColor: themeState.bodyGradientStartColor
    readonly property color bodyGradientEndColor: themeState.bodyGradientEndColor
    readonly property string bodyGradientDirection: themeState.bodyGradientDirection
    readonly property color headerTextColor: card.lockedPlaceholderActive
        ? card.lockedPlaceholderHeaderTextColor
        : themeState.headerTextColor
    readonly property color scopeBadgeColor: themeState.scopeBadgeColor
    readonly property color scopeBadgeBorderColor: themeState.scopeBadgeBorderColor
    readonly property color scopeBadgeTextColor: themeState.scopeBadgeTextColor
    readonly property color inlineRowColor: themeState.inlineRowColor
    readonly property color inlineRowBorderColor: themeState.inlineRowBorderColor
    readonly property color inlineLabelColor: themeState.inlineLabelColor
    readonly property color inlineInputTextColor: themeState.inlineInputTextColor
    readonly property color inlineInputBackgroundColor: themeState.inlineInputBackgroundColor
    readonly property color inlineInputBorderColor: themeState.inlineInputBorderColor
    readonly property color inlineDrivenTextColor: themeState.inlineDrivenTextColor
    readonly property color portLabelColor: card.lockedPlaceholderActive
        ? card.lockedPlaceholderLabelColor
        : themeState.portLabelColor
    readonly property color portInteractiveFillColor: themeState.portInteractiveFillColor
    readonly property color portInteractiveBorderColor: themeState.portInteractiveBorderColor
    readonly property color portInteractiveRingFillColor: themeState.portInteractiveRingFillColor
    readonly property color portInteractiveRingBorderColor: themeState.portInteractiveRingBorderColor
    readonly property color flowchartConnectedPortFillColor: themeState.flowchartConnectedPortFillColor
    readonly property color failureOutlineColor: themeState.failureOutlineColor
    readonly property color failureBadgeFillColor: themeState.failureBadgeFillColor
    readonly property color failureBadgeBorderColor: themeState.failureBadgeBorderColor
    readonly property color failureBadgeTextColor: themeState.failureBadgeTextColor
    readonly property color runningOutlineColor: themeState.runningOutlineColor
    readonly property color warningOutlineColor: themeState.warningOutlineColor
    readonly property color completedOutlineColor: themeState.completedOutlineColor
    readonly property color runningElapsedFooterColor: themeState.runningElapsedFooterColor
    readonly property color warningElapsedFooterColor: themeState.warningElapsedFooterColor
    readonly property color completedElapsedFooterColor: themeState.completedElapsedFooterColor
    readonly property real runningElapsedFooterOpacity: themeState.runningElapsedFooterOpacity
    readonly property real warningElapsedFooterOpacity: themeState.warningElapsedFooterOpacity
    readonly property real completedElapsedFooterOpacity: themeState.completedElapsedFooterOpacity
    readonly property real flowchartRestPortDiameter: themeState.flowchartRestPortDiameter
    readonly property real flowchartConnectedPortDiameter: themeState.flowchartConnectedPortDiameter
    readonly property real flowchartSelectedPortDiameter: themeState.flowchartSelectedPortDiameter
    readonly property real flowchartInteractivePortDiameter: themeState.flowchartInteractivePortDiameter
    readonly property real flowchartInteractiveRingDiameter: themeState.flowchartInteractiveRingDiameter
    readonly property real passiveBorderWidth: themeState.passiveBorderWidth
    readonly property real passiveCornerRadius: themeState.passiveCornerRadius
    readonly property real passiveFontPixelSize: themeState.passiveFontPixelSize
    readonly property int passiveFontWeight: themeState.passiveFontWeight
    readonly property bool passiveFontBold: themeState.passiveFontBold
    readonly property var graphSharedTypography: sharedTypographyState
    readonly property var surfaceMetrics: GraphNodeSurfaceMetrics.surfaceMetrics(
        nodeData,
        card._liveGeometryActive ? card._liveWidth : (card.nodeData ? card.nodeData.width : undefined),
        card._liveGeometryActive ? card._liveHeight : (card.nodeData ? card.nodeData.height : undefined),
        card.effectiveGraphLabelPixelSize
    )
    readonly property bool graphReadOnly: !!nodeData && Boolean(nodeData.read_only)
    readonly property var commentBadgePayload: nodeData && nodeData.comment_badge ? nodeData.comment_badge : ({})
    readonly property int commentCount: Math.max(0, Number(nodeData ? nodeData.comment_count || commentBadgePayload.count || 0 : 0))
    readonly property int linkCount: Math.max(0, Number(nodeData ? nodeData.link_count || 0 : 0))
    readonly property var nodeLockedState: nodeData && nodeData.locked_state ? nodeData.locked_state : ({})
    readonly property bool pathPointerDropTarget: !!nodeData
        && String(nodeData.type_id || "") === "io.path_pointer"
    readonly property bool pathPointerDropWritable: pathPointerDropTarget
        && !graphReadOnly
        && !Boolean(nodeLockedState.locked || nodeLockedState.read_only)
    property var pathPointerDropData: ({
        "path": "",
        "isFolder": false,
        "preferFileDrop": false,
        "itemCount": 0
    })
    readonly property bool pathPointerDropValid: pathPointerDropWritable
        && String(pathPointerDropData.path || "").trim().length > 0
        && Number(pathPointerDropData.itemCount || 0) === 1
    readonly property bool lockedPlaceholderActive: graphReadOnly && !!nodeData && Boolean(nodeData.unresolved)
    readonly property var lockedStatePayload: lockedPlaceholderActive && nodeData && nodeData.locked_state
        ? nodeData.locked_state
        : ({})
    readonly property string lockedPlaceholderReason: String(lockedStatePayload.reason || "")
    readonly property string lockedPlaceholderLabel: String(lockedStatePayload.label || "Requires add-on")
    readonly property string lockedPlaceholderSummary: String(
        lockedStatePayload.summary
        || (nodeData ? nodeData.unavailable_reason || "" : "")
    )
    readonly property string lockedPlaceholderFocusAddonId: String(
        lockedStatePayload.focus_addon_id
        || (nodeData ? nodeData.addon_id || "" : "")
    )
    readonly property string lockedPlaceholderAddonName: String(
        (nodeData ? nodeData.addon_display_name || "" : "")
        || lockedPlaceholderFocusAddonId
    )
    readonly property string lockedPlaceholderAddonVersion: String(nodeData ? nodeData.addon_version || "" : "")
    readonly property string lockedPlaceholderPackageText: {
        var addonName = String(card.lockedPlaceholderAddonName || "");
        var addonVersion = String(card.lockedPlaceholderAddonVersion || "");
        if (!addonVersion.length)
            return addonName;
        if (!addonName.length)
            return "v" + addonVersion;
        return addonName + " v" + addonVersion;
    }
    readonly property bool lockedPlaceholderManagerAvailable: addonManagerBridgeRef
        && addonManagerBridgeRef.requestOpen
        && card.lockedPlaceholderFocusAddonId.length > 0
    readonly property color lockedPlaceholderSurfaceColor: "#1b1d22"
    readonly property color lockedPlaceholderOutlineColor: "#3a3d45"
    readonly property color lockedPlaceholderHeaderTextColor: "#b0b7c3"
    readonly property color lockedPlaceholderLabelColor: "#8a93a3"
    readonly property color lockedPlaceholderAccentDashColor: "#6b7280"
    readonly property color lockedPlaceholderRibbonFillColor: "#1a1c21"
    readonly property color lockedPlaceholderRibbonBorderColor: "#4a4f5a"
    readonly property color lockedPlaceholderPackageTextColor: "#d0d5de"
    readonly property color lockedPlaceholderChipColor: "#3a3d45"
    readonly property color lockedPlaceholderChipTextColor: "#d0d5de"
    readonly property color lockedPlaceholderLinkColor: "#60cdff"
    readonly property bool surfaceInteractionLocked: card.graphReadOnly
        || card.authorLocked
        || Boolean(surfaceLoader.blocksHostInteraction)
    readonly property var surfaceLayout: _surfaceContractObject(surfaceSpec.layout)
    readonly property var viewerSurfaceContract: surfaceLoader.viewerSurfaceContract
    readonly property rect viewerBodyRect: surfaceLoader.viewerBodyRect
    readonly property rect viewerProxySurfaceRect: surfaceLoader.viewerProxySurfaceRect
    readonly property rect viewerLiveSurfaceRect: surfaceLoader.viewerLiveSurfaceRect
    readonly property var viewerBridgeBinding: surfaceLoader.viewerBridgeBinding
    readonly property var viewerInteractiveRects: surfaceLoader.viewerInteractiveRects
    readonly property rect lockedPlaceholderActionRect: surfaceLoader.lockedPlaceholderActionRect
    readonly property bool isCollapsed: !!nodeData && !!nodeData.collapsed
    readonly property color color: card._useHostChrome ? card.surfaceColor : "transparent"
    readonly property real radius: card._useHostChrome ? card.resolvedCornerRadius : 0

    signal nodeClicked(string nodeId, bool additive)
    signal nodeOpenRequested(string nodeId)
    signal nodeContextRequested(string nodeId, real localX, real localY)
    signal dragOffsetChanged(string nodeId, real dx, real dy)
    signal dragFinished(string nodeId, real finalX, real finalY, bool moved)
    signal dragCanceled(string nodeId)
    signal resizePreviewChanged(string nodeId, real newX, real newY, real newWidth, real newHeight, bool active)
    signal resizeFinished(string nodeId, real newX, real newY, real newWidth, real newHeight)
    signal inlineTextFitRequested()
    signal portClicked(string nodeId, string portKey, string direction, real sceneX, real sceneY, int modifiers)
    signal portDragStarted(
        string nodeId,
        string portKey,
        string direction,
        real sceneX,
        real sceneY,
        real screenX,
        real screenY,
        int modifiers
    )
    signal portDragMoved(
        string nodeId,
        string portKey,
        string direction,
        real sceneX,
        real sceneY,
        real screenX,
        real screenY,
        bool dragActive,
        int modifiers
    )
    signal portDragFinished(
        string nodeId,
        string portKey,
        string direction,
        real sceneX,
        real sceneY,
        real screenX,
        real screenY,
        bool dragActive,
        int modifiers
    )
    signal portDragCanceled(string nodeId, string portKey, string direction)
    signal surfaceControlInteractionStarted(string nodeId)
    signal inlinePropertyCommitted(string nodeId, string key, var value)
    signal sensitivePropertyReplaceRequested(string nodeId, string key, string plaintext)
    signal sensitivePropertyClearRequested(string nodeId, string key)
    signal portLabelCommitted(string nodeId, string portKey, string label)
    signal portHoverChanged(
        string nodeId,
        string portKey,
        string direction,
        real sceneX,
        real sceneY,
        bool hovered
    )
    signal nodeCommentEditorRequested(string nodeId, bool compose)
    signal nodeActionRequested(string nodeId, string actionId, var payload)
    signal settingsGroupExpansionRequested(string nodeId, string groupId, bool expanded)
    signal triggerNodeRequested(string nodeId)

    // Type-specific action list published by the loaded surface (viewer, media, ...).
    // Each entry is { id, label, icon, kind, enabled, primary, checked }.
    // checked is persistent toggle state; primary remains action emphasis.
    property var surfaceActions: Array.isArray(surfaceLoader.surfaceActions) ? surfaceLoader.surfaceActions : []
    readonly property var loadedSurfaceItem: surfaceLoader.loadedSurfaceItem

    property bool _liveGeometryActive: false
    property real _liveX: 0
    property real _liveY: 0
    property real _liveWidth: 0
    property real _liveHeight: 0
    property bool settingsGroupAnimationsEnabled: true
    property bool _settingsGroupAnimationArmed: false
    property real _settingsGroupStartWidth: 0
    property real _settingsGroupStartHeight: 0
    property var _settingsGroupStartHeaders: ({})
    property var _settingsGroupStartPorts: ({})
    property var _settingsGroupStartVisiblePorts: ({})
    readonly property int settingsGroupAnimationDuration: 180
    readonly property bool settingsGroupAnimationRunning: settingsGroupHeightAnimation.running
        || settingsGroupWidthAnimation.running
    readonly property real settingsGroupLayoutHeight: settingsGroupAnimationRunning
        && nodeData
        ? Number(nodeData.height)
        : Number(height)
    readonly property real _settingsGroupAnimationRemaining: {
        if (!settingsGroupAnimationRunning || !nodeData)
            return 0;
        var heightDelta = Number(nodeData.height) - _settingsGroupStartHeight;
        var widthDelta = Number(nodeData.width) - _settingsGroupStartWidth;
        var remaining = Math.abs(heightDelta) > 0.01
            ? (Number(nodeData.height) - height) / heightDelta
            : (Math.abs(widthDelta) > 0.01 ? (Number(nodeData.width) - width) / widthDelta : 0);
        return Math.max(0, Math.min(1, remaining));
    }
    readonly property var settingsGroupOffsets: {
        var offsets = {};
        for (var i = 0; i < settingsGroups.length; ++i) {
            var group = settingsGroups[i];
            var start = _settingsGroupStartHeaders[String(group.group_id)];
            if (start !== undefined)
                offsets[String(group.group_id)] = (start - Number(group.header.y)) * _settingsGroupAnimationRemaining;
        }
        return offsets;
    }
    readonly property var settingsGroupPortOffsets: {
        var offsets = {};
        if (!settingsGroupAnimationRunning || !nodeData)
            return offsets;
        var ports = nodeData.ports || [];
        var inputRow = 0;
        var outputRow = 0;
        for (var i = 0; i < ports.length; ++i) {
            var port = ports[i];
            var start = _settingsGroupStartPorts[String(port.key)];
            var target = GraphNodeSurfaceMetrics.localPortPointForPort(
                nodeData, port, inputRow, outputRow, width, settingsGroupLayoutHeight, effectiveGraphLabelPixelSize);
            if (start !== undefined)
                offsets[String(port.key)] = (start - target.y) * _settingsGroupAnimationRemaining;
            if (GraphNodeSurfaceMetrics.portLayoutDirection(port) === "in")
                inputRow += 1;
            else
                outputRow += 1;
        }
        return offsets;
    }

    function settingsGroupContentBottom(groupId) {
        for (var i = 0; i < settingsGroups.length - 1; ++i) {
            if (String(settingsGroups[i].group_id) === String(groupId)) {
                var next = settingsGroups[i + 1];
                return Math.min(height, Number(next.header.y)
                    + Number(settingsGroupOffsets[String(next.group_id)] || 0));
            }
        }
        return height;
    }
    readonly property bool _bodyRegionSurface: String(surfaceLayout.content_region || "host") === "body"

    function _emptyPathPointerDropData() {
        return {"path": "", "isFolder": false, "preferFileDrop": false, "itemCount": 0};
    }

    function beginSettingsGroupAnimation() {
        var headers = {};
        var ports = {};
        var visiblePorts = {};
        var currentPorts = inputPorts.concat(outputPorts);
        for (var visibleIndex = 0; visibleIndex < currentPorts.length; ++visibleIndex)
            visiblePorts[String(currentPorts[visibleIndex].key)] = true;
        for (var i = 0; i < settingsGroups.length; ++i) {
            var group = settingsGroups[i];
            headers[String(group.group_id)] = Number(group.header.y)
                + Number(settingsGroupOffsets[String(group.group_id)] || 0);
        }
        var nodePorts = nodeData ? nodeData.ports || [] : [];
        var inputRow = 0;
        var outputRow = 0;
        for (var portIndex = 0; portIndex < nodePorts.length; ++portIndex) {
            var port = nodePorts[portIndex];
            var direction = GraphNodeSurfaceMetrics.portLayoutDirection(port);
            ports[String(port.key)] = sceneAccess.localPortPointForPort(
                direction, direction === "in" ? inputRow++ : outputRow++, port).y;
        }
        _settingsGroupStartHeaders = headers;
        _settingsGroupStartPorts = ports;
        _settingsGroupStartVisiblePorts = visiblePorts;
        _settingsGroupStartWidth = width;
        _settingsGroupStartHeight = height;
        _settingsGroupAnimationArmed = Boolean(settingsGroupAnimationsEnabled);
        // Only this request's model update may start a transition. Disabling
        // a Behavior leaves its current animation running, but later edits snap.
        Qt.callLater(function() { card._settingsGroupAnimationArmed = false; });
    }

    function cancelSettingsGroupAnimation() {
        _settingsGroupAnimationArmed = false;
        // Reapply the bound targets through the disabled Behaviors so an active
        // transition also stops when lightweight mode or a resize takes over.
        width = Qt.binding(function() { return card._resolvedNodeWidth; });
        height = Qt.binding(function() { return card._resolvedNodeHeight; });
    }

    function _finishSettingsGroupAnimation() {
        if (!settingsGroupAnimationRunning)
            _settingsGroupAnimationArmed = false;
    }

    onSettingsGroupAnimationsEnabledChanged: {
        if (!settingsGroupAnimationsEnabled)
            cancelSettingsGroupAnimation();
    }
    on_LiveGeometryActiveChanged: {
        if (_liveGeometryActive)
            cancelSettingsGroupAnimation();
    }

    function _updatePathPointerDropData(eventObj) {
        var canvas = card.canvasItem;
        card.pathPointerDropData = canvas && canvas._pathPointerDataFromDropEvent
            ? canvas._pathPointerDataFromDropEvent(eventObj)
            : card._emptyPathPointerDropData();
        if (canvas && canvas.clearLibraryDropPreview)
            canvas.clearLibraryDropPreview();
        if (eventObj && eventObj.accept)
            eventObj.accept(card.pathPointerDropValid ? Qt.CopyAction : Qt.IgnoreAction);
    }

    function _clearPathPointerDropPreview() {
        var canvas = card.canvasItem;
        if (canvas && canvas.clearLibraryDropPreview)
            canvas.clearLibraryDropPreview();
    }

    function _finishPathPointerDrop(eventObj) {
        card._updatePathPointerDropData(eventObj);
        var canvas = card.canvasItem;
        if (card.pathPointerDropValid && canvas && canvas.performPathPointerNodeDrop) {
            canvas.performPathPointerNodeDrop(
                card.nodeId,
                card.pathPointerDropData.path,
                Boolean(card.pathPointerDropData.isFolder)
            );
        }
        card.pathPointerDropData = card._emptyPathPointerDropData();
    }
    readonly property real _bodyRegionMinimumNodeWidth: {
        if (!card._bodyRegionSurface)
            return 0.0;
        var bodyWidth = Number(surfaceLoader.minimumBodyWidth);
        if (!isFinite(bodyWidth) || bodyWidth <= 0.0)
            return 0.0;
        var left = Math.max(0.0, Number(surfaceMetrics.body_left_margin || 0.0));
        var right = Math.max(0.0, Number(surfaceMetrics.body_right_margin || 0.0));
        return left + bodyWidth + right;
    }
    readonly property real _bodyRegionMinimumNodeHeight: {
        if (!card._bodyRegionSurface)
            return 0.0;
        var bodyHeight = Number(surfaceLoader.minimumBodyHeight);
        if (!isFinite(bodyHeight) || bodyHeight <= 0.0)
            return 0.0;
        var chromeHeight = Math.max(
            0.0,
            Number(surfaceMetrics.default_height || 0.0) - Number(surfaceMetrics.body_height || 0.0)
        );
        return chromeHeight + bodyHeight;
    }
    readonly property real _minNodeWidth: Math.max(Number(surfaceMetrics.min_width), card._bodyRegionMinimumNodeWidth)
    readonly property real _minNodeHeight: Math.max(Number(surfaceMetrics.min_height), card._bodyRegionMinimumNodeHeight)
    readonly property bool _viewerSurfaceHeightClamped: card.surfaceFamily === "viewer"
    property real _measuredCollapsedTitleRequiredWidth: 0.0
    readonly property real lockedPlaceholderCompactHeight: {
        var bodyTop = Number(surfaceMetrics.body_top) || 30;
        var bodyPad = 8;
        var ribbonH = 38;
        var loadRowH = 14;
        var gap = 6;
        var bottomPad = Number(surfaceMetrics.body_bottom_margin || surfaceMetrics.bottom_padding) || 8;
        return bodyTop + bodyPad + ribbonH + gap + loadRowH + bodyPad + bottomPad;
    }
    readonly property real _resolvedNodeHeight: {
        if (card.lockedPlaceholderActive)
            return card.lockedPlaceholderCompactHeight;
        if (card.isCollapsed) {
            var collapsed = Number(surfaceMetrics.collapsed_height);
            if (!isFinite(collapsed) || collapsed <= 0.0)
                collapsed = card.nodeData ? Number(card.nodeData.height) : Number(surfaceMetrics.default_height);
            if (!isFinite(collapsed) || collapsed <= 0.0)
                collapsed = Number(surfaceMetrics.default_height);
            return Math.max(0.0, collapsed);
        }
        var numeric = card._liveGeometryActive
            ? Number(card._liveHeight)
            : (card.nodeData ? Number(card.nodeData.height) : Number(surfaceMetrics.default_height));
        if (!isFinite(numeric) || numeric <= 0.0)
            numeric = Number(surfaceMetrics.default_height);
        return Math.max(card._minNodeHeight, numeric);
    }
    readonly property real _resolvedNodeWidth: {
        if (card.isCollapsed) {
            var collapsed = Number(surfaceMetrics.collapsed_width);
            if (!isFinite(collapsed) || collapsed <= 0.0)
                collapsed = card.nodeData ? Number(card.nodeData.width) : Number(surfaceMetrics.default_width);
            if (!isFinite(collapsed) || collapsed <= 0.0)
                collapsed = Number(surfaceMetrics.default_width);
            // The header layer reports a required width only for families whose
            // collapsed chip should fit the full header title (standard + group
            // backdrop); other families leave this at 0 and keep their fixed size.
            var titleWidth = Number(card._measuredCollapsedTitleRequiredWidth);
            if (isFinite(titleWidth) && titleWidth > 0.0)
                collapsed = Math.max(collapsed, titleWidth);
            return Math.max(0.0, collapsed);
        }
        var numeric = card._liveGeometryActive
            ? Number(card._liveWidth)
            : (card.nodeData ? Number(card.nodeData.width) : Number(surfaceMetrics.default_width));
        if (!isFinite(numeric) || numeric <= 0.0)
            numeric = Number(surfaceMetrics.default_width);
        return Math.max(card._minNodeWidth, numeric);
    }
    readonly property real _resizeHandleSize: Number(surfaceMetrics.resize_handle_size)
    readonly property real _resizeHandleHitSize: {
        var size = Number(card._resizeHandleSize);
        if (!isFinite(size) || size <= 0.0)
            return 10.0;
        return Math.max(6.0, Math.min(size, 10.0));
    }

    readonly property real _inlineRowHeight: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineRowHeight : NaN);
        return isFinite(numeric) ? numeric : 26;
    }
    readonly property real _inlineStackedRowHeight: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineStackedRowHeight : NaN);
        return isFinite(numeric) ? numeric : card._inlineRowHeight * 2 + card._inlineRowSpacing;
    }
    readonly property real _inlineSliderRowHeight: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineSliderRowHeight : NaN);
        var pixelSize = Number(card.graphSharedTypography ? card.graphSharedTypography.inlinePropertyPixelSize : 10);
        return isFinite(numeric)
            ? numeric
            : card._inlineRowHeight * 2 + pixelSize + card._inlineRowSpacing;
    }
    readonly property real _inlineLabelAnchorOffset: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineLabelAnchorOffset : NaN);
        return isFinite(numeric) ? numeric : card._inlineRowHeight * 0.5;
    }
    readonly property real _inlineTextareaRowHeight: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineTextareaRowHeight : NaN);
        return isFinite(numeric) ? numeric : 104;
    }
    readonly property real _inlineRowSpacing: {
        var numeric = Number(card.graphSharedTypography ? card.graphSharedTypography.inlineRowSpacing : NaN);
        return isFinite(numeric) ? numeric : 4;
    }
    readonly property var inlineProperties: {
        if (!card.nodeData || !card.nodeData.inline_properties)
            return [];
        return card.nodeData.inline_properties;
    }
    readonly property real inlineBodyHeight: Number(surfaceMetrics.body_height)
    readonly property var settingsGroups: card.nodeData && card.nodeData.settings_groups
        ? card.nodeData.settings_groups
        : []
    readonly property var settingsBand: card.nodeData && card.nodeData.settings_band
        ? card.nodeData.settings_band
        : ({})
    readonly property real settingsBandHeight: {
        var numeric = Number(card.settingsBand.height);
        return isFinite(numeric) ? Math.max(0.0, numeric) : 0.0;
    }
    readonly property real _portDragThreshold: 2
    readonly property bool canEnterScope: !!card.nodeData
        && !!card.nodeData.can_enter_scope
        && !card.graphReadOnly
        && !card.authorLocked
    readonly property bool sharedHeaderTitleEditable: !!card.nodeData && !card.graphReadOnly && !card.authorLocked
    readonly property bool flowchartTitleEditable: card.isFlowchartSurface && card.sharedHeaderTitleEditable
    readonly property bool _useHostChrome: chromeLayout.useHostChrome
    readonly property real _titleTop: chromeLayout.titleTop
    readonly property real _titleHeight: chromeLayout.titleHeight
    readonly property real _titleLeftMargin: chromeLayout.titleLeftMargin
    readonly property real _titleRightMargin: chromeLayout.titleRightMargin
    readonly property bool _titleCentered: chromeLayout.titleCentered
    readonly property bool _portLabelsSuppressedBySurfaceRule: chromeLayout.portLabelsSuppressedBySurfaceRule
    readonly property bool _standardExpandedNonPassiveNode: chromeLayout.standardExpandedNonPassiveNode
    // Consume the scene-owned width contract for visible standard-node labels.
    readonly property real _standardLeftLabelMetricWidth: chromeLayout.standardLeftLabelMetricWidth
    readonly property real _standardRightLabelMetricWidth: chromeLayout.standardRightLabelMetricWidth
    readonly property real _standardPortGutterMetric: chromeLayout.standardPortGutterMetric
    readonly property real _standardCenterGapMetric: chromeLayout.standardCenterGapMetric
    readonly property real _standardPortLabelMinMetricWidth: chromeLayout.standardPortLabelMinMetricWidth
    readonly property bool _standardPortLabelMetricsReady: chromeLayout.standardPortLabelMetricsReady
    readonly property bool _usesStandardPortLabelColumns: chromeLayout.usesStandardPortLabelColumns
    readonly property int _standardVisibleLabelColumnCount: chromeLayout.standardVisibleLabelColumnCount
    readonly property real _standardExtraLabelWidthPerColumn: chromeLayout.standardExtraLabelWidthPerColumn
    readonly property real _standardLeftLabelWidth: chromeLayout.standardLeftLabelWidth
    readonly property real _standardRightLabelWidth: chromeLayout.standardRightLabelWidth
    readonly property real _standardPortGutter: chromeLayout.standardPortGutter
    readonly property real _standardCenterGap: chromeLayout.standardCenterGap
    readonly property real _portLabelGap: chromeLayout.portLabelGap
    readonly property real _portLabelMaxWidth: chromeLayout.portLabelMaxWidth
    readonly property bool _tooltipOnlyPortLabelsActive: chromeLayout.tooltipOnlyPortLabelsActive
    readonly property bool _portLabelsVisible: chromeLayout.portLabelsVisible
    readonly property bool _notchedPortsEffective: chromeLayout.notchedPortsEffective
    readonly property color _effectiveChromeOutlineColor: chromeBackground.effectiveOutlineColor
    readonly property real _effectiveChromeBorderWidth: chromeBackground.effectiveBorderWidth
    readonly property bool _surfaceOwnsShadow: chromeLayout.surfaceOwnsShadow
    readonly property bool _backgroundShadowVisible: chromeLayout.backgroundShadowVisible
    readonly property bool _surfaceShadowVisible: chromeLayout.surfaceShadowVisible
    readonly property bool _shadowVisible: chromeLayout.shadowVisible
    readonly property int nodeTextRenderType: chromeLayout.nodeTextRenderType

    // Keep old member grips visible while their wires converge onto the
    // collapsed aggregate. The transient rows own no editors or labels.
    readonly property var _settingsGroupPortPresentation: {
        if (!settingsGroupAnimationRunning || !nodeData)
            return nodeData;
        var ports = (nodeData.ports || []).map(function(port) {
            if (port.handle_visible !== false || !_settingsGroupStartVisiblePorts[String(port.key)])
                return port;
            return Object.assign({}, port, {
                "handle_visible": true, "settings_group_transition_only": true,
                "default_property": null
            });
        });
        return Object.assign({}, nodeData, {"ports": ports});
    }
    readonly property var inputPorts: {
        if (!card.portLayerActive)
            return [];
        return GraphNodeSurfaceMetrics.visiblePortsForDirection(card._settingsGroupPortPresentation, "in");
    }
    readonly property var outputPorts: {
        if (!card.portLayerActive)
            return [];
        return GraphNodeSurfaceMetrics.visiblePortsForDirection(card._settingsGroupPortPresentation, "out");
    }
    readonly property real resolvedBorderWidth: themeState.resolvedBorderWidth
    readonly property real resolvedCornerRadius: themeState.resolvedCornerRadius
    readonly property bool chromeCacheActive: chromeLayout.chromeCacheActive
    readonly property bool shadowCacheActive: chromeLayout.shadowCacheActive
    readonly property bool surfaceShadowCacheActive: chromeLayout.surfaceShadowCacheActive
    readonly property bool chromeShadowCacheActive: chromeLayout.chromeShadowCacheActive
    readonly property string chromeShadowCacheKey: [
        chromeLayout.chromeShadowCacheKey,
        card.semanticChromeState,
        String(card.surfaceColor),
        String(card.outlineColor),
        String(card.bodyGradientEndColor)
    ].join("|")
    readonly property string surfaceShadowCacheKey: chromeLayout.surfaceShadowCacheKey

    function localPortPoint(direction, rowIndex) {
        return sceneAccess.localPortPoint(direction, rowIndex);
    }

    function localPortPointForPort(direction, rowIndex, portData) {
        return sceneAccess.localPortPointForPort(direction, rowIndex, portData);
    }

    function localPortLayoutPointForPort(direction, rowIndex, portData) {
        return sceneAccess._localPortPoint(direction, rowIndex, portData, true);
    }

    function portScenePos(direction, rowIndex) {
        return sceneAccess.portScenePos(direction, rowIndex);
    }

    function portScenePosForPort(direction, rowIndex, portData) {
        return sceneAccess.portScenePosForPort(direction, rowIndex, portData);
    }

    function portLabelWidth(labelImplicitWidth, availableWidth) {
        var implicitValue = Number(labelImplicitWidth);
        if (!isFinite(implicitValue) || implicitValue < 0.0)
            implicitValue = 0.0;
        var maxWidth = Math.max(0.0, Number(card._portLabelMaxWidth));
        var clampedAvailable = Math.max(0.0, Number(availableWidth));
        return Math.max(0.0, Math.min(implicitValue, maxWidth, clampedAvailable));
    }

    function basePortColor(portKind) {
        var palette = card.portKindPalette || {};
        if (portKind === "flow")
            return card.usesCardinalNeutralFlowHandles
                ? Qt.alpha(card.outlineColor, 0.72)
                : (card.isPassiveNode ? card.scopeBadgeColor : "#60CDFF");
        return palette.data || "#7AA8FF";
    }

    function portTypeAccentColor(portData) {
        var kind = String(portData && portData.kind || "").trim().toLowerCase();
        if (kind !== "data")
            return card.basePortColor(kind);
        var palette = card.portKindPalette || {};
        var fallbackColor = palette.data || "#7AA8FF";
        var colorToken = String(portData && portData.data_type_color_token || "").trim();
        if (colorToken.length > 0
                && card.graphThemeBridgeRef
                && card.graphThemeBridgeRef.resolve_data_type_color) {
            var resolved = String(
                card.graphThemeBridgeRef.resolve_data_type_color(colorToken) || ""
            ).trim();
            if (resolved.length > 0)
                return resolved;
        }
        return fallbackColor;
    }

    // Grip flow-state rendering: the topology fallback rides in nodeData;
    // retained execution outputs refine it through the shared facts object.
    // Hollow grips get an opaque card-colored interior so the card border
    // does not draw a line through the ring of edge-centered grips.
    function resolvedPortFlowState(portData) {
        var nodeId = String(card.nodeData && card.nodeData.node_id || "");
        var portKey = String(portData && portData.key || "");
        var lookup = card.executionFacts && card.executionFacts.portFlowStateLookup
            ? card.executionFacts.portFlowStateLookup
            : ({});
        var nodeStates = lookup[nodeId] || ({});
        return String(nodeStates[portKey] || (portData && portData.flow_state) || "");
    }

    function portFlowFillColor(portData) {
        var palette = card.portStatePalette || {};
        var state = card.resolvedPortFlowState(portData);
        if (state === "flowing")
            return palette.valid || "#67D487";
        if (state === "invalid")
            return card.isActiveWireNode && String(portData && portData.direction || "").toLowerCase() === "in"
                ? "#FF543E"
                : (palette.invalid_fill || "#D94F4F");
        if (state === "invalid_muted")
            return palette.invalid_muted_fill || "#f4f6f9";
        if (state === "default" || state === "waiting" || state === "idle")
            return card.isPassiveNode ? card.surfaceColor : card.themeSurfaceColor;
        return "transparent";
    }

    function portFlowOutlineColor(portData) {
        var palette = card.portStatePalette || {};
        var state = card.resolvedPortFlowState(portData);
        if (state === "waiting")
            return palette.waiting_outline || "#E8A838";
        if (state === "idle")
            return palette.idle_outline || "#6b7280";
        if (state === "invalid" || state === "invalid_muted")
            return state === "invalid"
                && card.isActiveWireNode
                && String(portData && portData.direction || "").toLowerCase() === "in"
                ? "#FF543E"
                : (palette.invalid_border || "#FF8C74");
        if (String(portData && portData.data_type_color_token || "").trim().length > 0)
            return card.portTypeAccentColor(portData);
        return palette.valid || "#67D487";
    }

    function isHoveredPort(direction, portKey) {
        var hovered = !!card.hoveredPort
            && card.hoveredPort.node_id === card.nodeData.node_id
            && card.hoveredPort.port_key === portKey
            && card.hoveredPort.direction === direction;
        if (hovered)
            return true;
        return !!card.previewPort
            && card.previewPort.node_id === card.nodeData.node_id
            && card.previewPort.port_key === portKey
            && card.previewPort.direction === direction;
    }

    function isConnectedPort(portData) {
        return !!portData && !!portData.connected;
    }

    function _compatibleEndpointKey(nodeId, portKey) {
        var normalizedNodeId = String(nodeId || "");
        var normalizedPortKey = String(portKey || "");
        return "$" + normalizedNodeId.length + ":" + normalizedNodeId
            + ":" + normalizedPortKey.length + ":" + normalizedPortKey;
    }

    function isCompatibleTargetPort(portData) {
        if (!card.nodeData || !portData || !card.canvasItem)
            return false;
        var state = card.canvasItem.wireDragState;
        if (!state || !state.active || !state.compatibility_snapshot_valid)
            return false;
        if (Boolean(portData.blocks_new_connections) || Boolean(portData.inactive))
            return false;
        var generation = String(portData.catalog_generation || "");
        if (!generation
                || generation !== String(state.compatibility_catalog_generation || "")) {
            return false;
        }
        var lookup = state.compatible_endpoint_lookup || ({});
        return Boolean(
            lookup[
                _compatibleEndpointKey(
                    String(card.nodeData.node_id || ""),
                    String(portData.key || "")
                )
            ]
        );
    }

    function isPendingPort(direction, portKey) {
        return !!card.nodeData
            && !!card.pendingPort
            && card.pendingPort.node_id === card.nodeData.node_id
            && card.pendingPort.port_key === portKey
            && card.pendingPort.direction === direction;
    }

    function isDragSourcePort(direction, portKey) {
        return !!card.nodeData
            && !!card.dragSourcePort
            && card.dragSourcePort.node_id === card.nodeData.node_id
            && card.dragSourcePort.port_key === portKey
            && card.dragSourcePort.direction === direction;
    }

    function inlineEditorText(propertyData) {
        if (!propertyData)
            return "";
        var value = propertyData.value;
        if (value === undefined || value === null)
            return "";
        return String(value);
    }

    function applyInlineTextFitWidth(requiredWidth) {
        if (!card.nodeData || card.isCollapsed || card.surfaceInteractionLocked)
            return false;
        var targetWidth = Math.ceil(Number(requiredWidth));
        var currentWidth = Number(card.width);
        if (!isFinite(targetWidth) || targetWidth <= 0.0
                || !isFinite(currentWidth) || targetWidth <= currentWidth + 0.01)
            return false;

        var finalX = card._liveGeometryActive ? Number(card._liveX) : Number(card.nodeData.x);
        var finalY = card._liveGeometryActive ? Number(card._liveY) : Number(card.nodeData.y);
        var finalHeight = card._liveGeometryActive ? Number(card._liveHeight) : Number(card.height);
        if (!isFinite(finalX) || !isFinite(finalY) || !isFinite(finalHeight) || finalHeight <= 0.0)
            return false;

        if (card._liveGeometryActive) {
            card._liveWidth = targetWidth;
            card.resizePreviewChanged(
                String(card.nodeData.node_id || ""),
                finalX,
                finalY,
                targetWidth,
                finalHeight,
                false
            );
        }
        card.resizeFinished(
            String(card.nodeData.node_id || ""),
            finalX,
            finalY,
            targetWidth,
            finalHeight
        );
        card._liveGeometryActive = false;
        return true;
    }

    function browseNodePropertyPath(key, currentPath) {
        if (arguments.length > 2)
            return sceneAccess.browseNodePropertyPath(key, currentPath, arguments[2]);
        return sceneAccess.browseNodePropertyPath(key, currentPath);
    }

    function internalizeNodePropertyPath(key, currentPath) {
        return sceneAccess.internalizeNodePropertyPath(key, currentPath);
    }

    function pickNodePropertyColor(key, currentValue) {
        return sceneAccess.pickNodePropertyColor(key, currentValue);
    }

    function resolveLocalFileSourceUrl(source) {
        return sceneAccess.resolveLocalFileSourceUrl(source);
    }

    function describeImagePreview(source) {
        return sceneAccess.describeImagePreview(source);
    }

    function describeMailPreview(source) {
        return sceneAccess.describeMailPreview(source);
    }

    function openLocalFileSource(source, chooser) {
        return sceneAccess.openLocalFileSource(source, chooser);
    }

    function _styleString(value) {
        if (value === undefined || value === null)
            return "";
        return String(value).trim();
    }

    function _nodePropertyBool(key, fallback) {
        var properties = card.nodeProperties || {};
        var value = properties[String(key || "")];
        if (value === undefined || value === null)
            return Boolean(fallback);
        if (typeof value === "boolean")
            return value;
        if (typeof value === "string") {
            var normalized = value.trim().toLowerCase();
            if (normalized === "true")
                return true;
            if (normalized === "false")
                return false;
        }
        return Boolean(value);
    }

    function _surfaceSpecFromNodeData() {
        if (card.nodeData
                && card.nodeData.surface_spec !== null
                && typeof card.nodeData.surface_spec === "object")
            return card.nodeData.surface_spec;
        return ({});
    }

    function _surfaceContractObject(value) {
        if (!value || typeof value !== "object")
            return ({});
        return value;
    }

    function surfaceFullscreenAction(enabled, primary) {
        if (!card.surfaceFullscreenSupported)
            return null;
        return {
            "id": String(card.surfaceFullscreen.action_id || "fullscreen"),
            "label": String(card.surfaceFullscreen.action_label || "Fullscreen"),
            "icon": String(card.surfaceFullscreen.action_icon || "fullscreen"),
            "kind": String(card.surfaceFullscreen.action_kind || "surface"),
            "enabled": Boolean(enabled) && card.surfaceFullscreenAvailable,
            "primary": Boolean(primary)
        };
    }

    function requestSurfaceContentFullscreen(runtimeState) {
        if (!card.surfaceFullscreenAvailable || !card.surfaceFullscreenBridgeRef || !card.nodeData)
            return false;
        var nodeId = String(card.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        if (card.surfaceFullscreenBridgeRef.request_toggle_for_node_with_state)
            return Boolean(card.surfaceFullscreenBridgeRef.request_toggle_for_node_with_state(nodeId, runtimeState || ({})));
        if (card.surfaceFullscreenBridgeRef.request_toggle_for_node)
            return Boolean(card.surfaceFullscreenBridgeRef.request_toggle_for_node(nodeId));
        if (card.surfaceFullscreenBridgeRef.request_open_node)
            return Boolean(card.surfaceFullscreenBridgeRef.request_open_node(nodeId));
        return false;
    }

    function _styleNumber(value, fallback, allowZero) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            return fallback;
        if (allowZero ? numeric < 0.0 : numeric <= 0.0)
            return fallback;
        return numeric;
    }

    function _normalizedRenderQuality(renderQualityLike) {
        return renderQualityState.normalizedRenderQuality(renderQualityLike);
    }

    function _normalizedQualityTierList(value) {
        return renderQualityState.normalizedQualityTierList(value);
    }

    function _supportsRenderQualityTier(tier) {
        return renderQualityState.supportsRenderQualityTier(tier);
    }

    function _pointerInCanvas(mouseArea, mouse) {
        return interactionState.pointerInCanvas(mouseArea, mouse);
    }

    function _isResizeHandlePoint(localX, localY) {
        return card.isPassiveNode && interactionState.isResizeHandlePoint(localX, localY);
    }

    function _pointInRect(localX, localY, rectLike) {
        return interactionState.pointInRect(localX, localY, rectLike);
    }

    function _pointInEmbeddedInteractiveRect(localX, localY) {
        return interactionState.pointInEmbeddedInteractiveRect(localX, localY);
    }

    function _surfaceClaimsBodyInteractionAt(localX, localY) {
        return interactionState.surfaceClaimsBodyInteractionAt(localX, localY);
    }

    function requestInlineTitleEditAt(localX, localY) {
        return interactionState.requestInlineTitleEditAt(localX, localY);
    }

    function beginInlineTitleEdit() {
        if (headerLayer._beginTitleEdit())
            return true;
        return surfaceLoader.beginInlineTitleEdit();
    }

    function requestScopeOpenAt(localX, localY) {
        return interactionState.requestScopeOpenAt(localX, localY);
    }

    function commitInlineTitleEditAt(localX, localY) {
        return interactionState.commitInlineTitleEditAt(localX, localY);
    }

    function currentViewportZoom() {
        return sceneAccess.currentViewportZoom();
    }

    function _normalizedSceneRectPayload(rectLike) {
        return sceneAccess.normalizedSceneRectPayload(rectLike);
    }

    function _nodeSceneRect() {
        return sceneAccess.nodeSceneRect();
    }

    function _sceneRectsIntersect(firstRectLike, secondRectLike) {
        return sceneAccess.sceneRectsIntersect(firstRectLike, secondRectLike);
    }

    function _lookupExecutionTimingValue(lookupLike, allowZero) {
        if (!card.executionNodeId.length)
            return NaN;
        var lookup = lookupLike || {};
        var value = lookup[card.executionNodeId];
        if (value === undefined || value === null)
            return NaN;
        var numeric = Number(value);
        if (!isFinite(numeric))
            return NaN;
        if (allowZero ? numeric < 0.0 : numeric <= 0.0)
            return NaN;
        return numeric;
    }

    function formatExecutionElapsed(elapsedMilliseconds) {
        var elapsedMs = Math.max(0.0, Number(elapsedMilliseconds));
        if (!isFinite(elapsedMs))
            elapsedMs = 0.0;
        var elapsedUnit = card.executionFacts ? card.executionFacts.nodeElapsedTimeUnit : "seconds";
        if (elapsedUnit === "milliseconds")
            return Math.round(elapsedMs) + "ms";
        var elapsedSeconds = elapsedMs / 1000.0;
        if (!isFinite(elapsedSeconds))
            elapsedSeconds = 0.0;
        if (elapsedSeconds < 60.0)
            return elapsedSeconds.toFixed(1) + "s";
        var minutes = Math.floor(elapsedSeconds / 60.0);
        var seconds = Math.floor(elapsedSeconds % 60.0);
        return minutes + "m " + (seconds < 10 ? "0" : "") + seconds + "s";
    }

    function updateSharedElapsed(nowMs) {
        elapsedTimerLabel._updateElapsed(nowMs);
    }

    function commentToken(name, fallback) {
        var surface = Qt.color(String(card.themeSurfaceColor || "#1b1d22"));
        var dark = (0.2126 * surface.r + 0.7152 * surface.g + 0.0722 * surface.b) < 0.5;
        if (name === "comment")
            return dark ? "#F2B84B" : "#D58E1E";
        if (name === "commentBorder")
            return dark ? "#765f2b" : "#E3B660";
        return fallback;
    }

    function lockedPlaceholderActionContains(localX, localY) {
        if (!card.lockedPlaceholderActive || !card.lockedPlaceholderManagerAvailable)
            return false;
        return card._pointInRect(localX, localY, card.lockedPlaceholderActionRect);
    }

    function requestLockedPlaceholderManager() {
        if (!card.lockedPlaceholderManagerAvailable)
            return false;
        card.addonManagerBridgeRef.requestOpen(card.lockedPlaceholderFocusAddonId);
        return true;
    }

    HoverHandler {
        id: cardHoverHandler
    }

    readonly property bool _hostHoverActive: cardHoverHandler.hovered || hostGestureLayer.containsMouse
    readonly property bool _resizeHandleContainsMouse: topLeftResizeHandle.containsMouse
        || topRightResizeHandle.containsMouse
        || bottomLeftResizeHandle.containsMouse
        || bottomRightResizeHandle.containsMouse
    readonly property bool _resizeInteractionActive: topLeftResizeHandle.dragActive
        || topRightResizeHandle.dragActive
        || bottomLeftResizeHandle.dragActive
        || bottomRightResizeHandle.dragActive
    readonly property bool _hoveredPortOnNode: !!card.nodeData
        && !!card.hoveredPort
        && card.hoveredPort.node_id === card.nodeData.node_id
    readonly property bool _previewPortOnNode: !!card.nodeData
        && !!card.previewPort
        && card.previewPort.node_id === card.nodeData.node_id
    readonly property bool _pendingPortOnNode: !!card.nodeData
        && !!card.pendingPort
        && card.pendingPort.node_id === card.nodeData.node_id
    readonly property bool _dragSourcePortOnNode: !!card.nodeData
        && !!card.dragSourcePort
        && card.dragSourcePort.node_id === card.nodeData.node_id
    readonly property bool _contextTargetActive: !!card.nodeData
        && String(card.contextTargetNodeId || "") === String(card.nodeData.node_id || "")
    readonly property bool _dragPreviewActive: Math.abs(Number(card.liveDragDx)) >= 0.01
        || Math.abs(Number(card.liveDragDy)) >= 0.01
    readonly property bool hoverActive: card._hostHoverActive
        || card._resizeHandleContainsMouse
        || card._resizeInteractionActive
    readonly property bool runnableNode: !!card.nodeData
        && !card.graphReadOnly
        && !card.suppressRunAction
        && String(card.nodeData.runtime_behavior || "action").toLowerCase() !== "passive"

    // --- Floating toolbar contract (T01) -------------------------------------
    // Accent color used by the floating toolbar for primary-action tint and hover
    // border. Tracks the node's per-node theme via its selected outline color.
    readonly property color nodeThemeColor: card.selectedOutlineColor

    // Eligibility and lifecycle stay host-owned; the pure module only shapes
    // already-resolved presentation facts.
    readonly property var contextNodeActions: GraphActionPresentation.nodeContextActions({
        "canEnterScope": card.canEnterScope,
        "pathPointer": card.nodeData
            && String(card.nodeData.type_id || "") === "io.path_pointer"
            ? {
                "enabled": String((card.nodeData.properties || {}).path || "").trim().length > 0,
                "isFolder": String((card.nodeData.properties || {}).mode || "") === "folder"
            }
            : null
    })
    readonly property var commonNodeActions: GraphActionPresentation.nodeCommonActions({
        "runnable": card.runnableNode,
        "graphReadOnly": card.graphReadOnly,
        "lockedPlaceholderActive": card.lockedPlaceholderActive,
        "lockedPlaceholderManagerAvailable": card.lockedPlaceholderManagerAvailable,
        "lockEligible": card.lockEligible,
        "authorLocked": card.authorLocked,
        "collapsible": card.nodeData ? Boolean(card.nodeData.collapsible) : false,
        "collapsed": card.isCollapsed
    })
    readonly property var availableActions: GraphActionPresentation.nodeAvailableActions({
        "contextActions": card.contextNodeActions,
        "surfaceActions": card.surfaceActions,
        "commonActions": card.commonNodeActions,
        "panelSurface": card.isPanelSurface,
        "authorLocked": card.authorLocked
    })

    // Drag translate exposed for sibling overlays (floating toolbar) that need to
    // follow the node during multi-selection drag, where non-anchor nodes stay
    // pinned to nodeData.x/y and move via the Translate transform below.
    readonly property real dragTranslateX: Number(card.liveDragDx || 0)
    readonly property real dragTranslateY: Number(card.liveDragDy || 0)

    readonly property bool hostDragActive: hostGestureLayer.dragActive
        || Number(card.liveDragDx || 0) !== 0
        || Number(card.liveDragDy || 0) !== 0

    // Set by the overlay toolbar while the cursor is inside its chrome (or the
    // gap bridging it to the node), so the toolbar stays open while the user
    // reaches for a button.
    property bool toolbarPointerInside: false
    // Published by the overlay toolbar so node tooltips can use the opposite side.
    property bool floatingToolbarFlipped: false
    property real floatingToolbarZoom: 1.0

    // Singleton-selection or opt-in hover trigger. Keep the 120 ms grace period
    // so the cursor can enter a hover-opened toolbar without collapsing it.
    readonly property bool nodeFloatingToolbarOpensOnHover: card.prefs
        && card.prefs.nodeFloatingToolbarOpensOnHover !== undefined
        ? Boolean(card.prefs.nodeFloatingToolbarOpensOnHover)
        : false
    readonly property bool isIndividuallySelected: card.isSelected
        && Object.keys(card.selectedNodeLookup || ({})).length === 1
    readonly property bool toolbarActiveSource: card.isIndividuallySelected
        || (card.hoverActive && card.nodeFloatingToolbarOpensOnHover)
        || card.toolbarPointerInside
    property bool toolbarActive: false
    function _claimToolbarHost() {
        if (!card.canvasItem || card.canvasItem.activeToolbarHost === undefined)
            return;
        card.canvasItem.activeToolbarHost = card;
    }
    function _releaseToolbarHost() {
        if (!card.canvasItem || card.canvasItem.activeToolbarHost === undefined)
            return;
        if (card.canvasItem.activeToolbarHost === card)
            card.canvasItem.activeToolbarHost = null;
    }
    function _syncToolbarActive() {
        if (card.toolbarActiveSource) {
            if (card.frameScheduler && card.frameScheduler.cancelToolbarGrace)
                card.frameScheduler.cancelToolbarGrace(card);
            card.toolbarActive = true;
            card._claimToolbarHost();
        } else if (card.toolbarActive) {
            if (card.frameScheduler && card.frameScheduler.scheduleToolbarGrace)
                card.frameScheduler.scheduleToolbarGrace(card);
            else
                card.toolbarActive = false;
        }
    }
    function finishToolbarGrace() {
        if (!card.toolbarActiveSource)
            card.toolbarActive = false;
    }
    onToolbarActiveSourceChanged: card._syncToolbarActive()
    onHoverActiveChanged: {
        if (card.hoverActive && card.toolbarActive)
            card._claimToolbarHost();
    }
    Component.onCompleted: card._syncToolbarActive()
    onToolbarActiveChanged: {
        if (card.toolbarActive)
            card._claimToolbarHost();
        else
            card._releaseToolbarHost();
    }
    onAuthorLockedChanged: {
        if (!card.authorLocked || card.lockedInteractionEnabled)
            return;
        card.toolbarPointerInside = false;
        card.toolbarActive = false;
        card._releaseToolbarHost();
    }
    Component.onDestruction: {
        card._releaseToolbarHost();
        if (card.frameScheduler && card.frameScheduler.unregisterHost)
            card.frameScheduler.unregisterHost(card);
    }

    function dispatchNodeAction(actionId, payload) {
        if (!card.nodeData)
            return;
        var normalized = String(actionId || "");
        if (normalized === "frame_node") {
            card.frameNodeInView();
            return;
        }
        if (normalized === "open_addon_manager_for_node") {
            card.requestLockedPlaceholderManager();
            return;
        }
        if (card.graphReadOnly || (card.authorLocked && normalized !== "toggle_node_lock"))
            return;
        card.nodeActionRequested(String(card.nodeData.node_id || ""), normalized, payload || null);
    }

    function frameNodeInView() {
        if (!card.canvasItem || !card.canvasItem.frameSceneRectPayload)
            return false;
        var bounds = card._nodeSceneRect();
        if (!bounds)
            return false;
        return Boolean(card.canvasItem.frameSceneRectPayload(bounds, 80.0));
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        var nonMutatingPanelAction = normalized === "panel_copy"
            || normalized === "panel_copy_tree";
        if ((card.graphReadOnly || card.authorLocked) && !nonMutatingPanelAction)
            return false;
        if (!surfaceLoader || !surfaceLoader.dispatchSurfaceAction)
            return false;
        var handled = Boolean(surfaceLoader.dispatchSurfaceAction(normalized));
        if (handled
                && card.canvasItem
                && card.canvasItem.openSurfaceActionOverlayForHost) {
            card.canvasItem.openSurfaceActionOverlayForHost(card, normalized, card.loadedSurfaceItem);
        }
        return handled;
    }
    // -------------------------------------------------------------------------

    readonly property bool _forceRenderActive: card.isSelected
        || card.isFailedNode
        || card.isRunningNode
        || card.isWarningChromeNode
        || card.isCompletedNode
        || card.isFreshRunNode
        || card.hoverActive
        || card._hoveredPortOnNode
        || card._previewPortOnNode
        || card._pendingPortOnNode
        || card._dragSourcePortOnNode
        || card._contextTargetActive
        || interactionState.inlineEditingActive
        || hostGestureLayer.dragActive
        || hostGestureLayer.pointerInteractionActive
        || card._dragPreviewActive
        || card._liveGeometryActive
        || card._resizeInteractionActive
    readonly property bool inVisibleViewport: card._sceneRectsIntersect(
        card._nodeSceneRect(),
        card.visibleSceneRectPayload
    )
    readonly property bool renderActive: card._forceRenderActive
        || card._sceneRectsIntersect(card._nodeSceneRect(), card.renderActivationSceneRectPayload)
    readonly property bool _resizeHandlesVisible: !!card.nodeData
        && (card.isPassiveNode || card.panelLikeSurface)
        && !card.isCollapsed
        && !card.surfaceInteractionLocked
        && (card._hostHoverActive || card._resizeInteractionActive)

    visible: card.hasNodeIdentity
    enabled: card.hasNodeIdentity && (!card.authorLocked || card.lockedInteractionEnabled)

    z: card.authorLocked
        ? 10
        : (card.isFailedNode
        ? 32
        : (card.isRunningNode
            ? 31
            : ((card.isWarningChromeNode || card.isCompletedNode)
                ? 30
                : (card.isFreshRunNode
                    ? 29
                    : (card.isSelected ? 28 : 20)))))
    x: (card._liveGeometryActive ? card._liveX : (card.nodeData ? card.nodeData.x : 0.0)) + card.worldOffset
    y: (card._liveGeometryActive ? card._liveY : (card.nodeData ? card.nodeData.y : 0.0)) + card.worldOffset
    transform: Translate {
        x: card.liveDragDx
        y: card.liveDragDy
    }
    width: card._resolvedNodeWidth
    height: card._resolvedNodeHeight

    Behavior on width {
        enabled: card._settingsGroupAnimationArmed
            && card.settingsGroupAnimationsEnabled
            && !card._liveGeometryActive
            && !card.isCollapsed
        NumberAnimation {
            id: settingsGroupWidthAnimation
            duration: card.settingsGroupAnimationDuration
            easing.type: Easing.InOutCubic
            onRunningChanged: {
                if (!running)
                    Qt.callLater(card._finishSettingsGroupAnimation);
            }
        }
    }

    Behavior on height {
        enabled: card._settingsGroupAnimationArmed
            && card.settingsGroupAnimationsEnabled
            && !card._liveGeometryActive
            && !card.isCollapsed
        NumberAnimation {
            id: settingsGroupHeightAnimation
            duration: card.settingsGroupAnimationDuration
            easing.type: Easing.InOutCubic
            onRunningChanged: {
                if (!running)
                    Qt.callLater(card._finishSettingsGroupAnimation);
            }
        }
    }

    GraphNodeChromeBackground {
        id: chromeBackground
        anchors.fill: parent
        host: card
    }

    Rectangle {
        id: elapsedTimerBadge
        objectName: "graphNodeElapsedTimerBadge"
        visible: elapsedTimerLabel.visible
        anchors.centerIn: elapsedTimerLabel
        width: Math.max(0.0, elapsedTimerLabel.width + 12)
        height: Math.max(0.0, elapsedTimerLabel.height + 4)
        radius: Math.max(6, height * 0.22)
        color: Qt.alpha(card.surfaceColor, 1.0)
        border.width: 1
        border.color: Qt.alpha(elapsedTimerLabel.color, elapsedTimerLabel.liveElapsedActive ? 0.45 : 0.34)
        z: 3
        antialiasing: true
    }

    Text {
        id: elapsedTimerLabel
        objectName: "graphNodeElapsedTimer"
        visible: liveElapsedActive || cachedElapsedActive
        anchors.top: parent.bottom
        anchors.topMargin: 4
        anchors.horizontalCenter: parent.horizontalCenter
        z: 4
        font.pixelSize: card.graphSharedTypography ? card.graphSharedTypography.elapsedFooterPixelSize : 10
        font.bold: true
        color: liveElapsedActive
            ? card.runningElapsedFooterColor
            : (card.isWarningChromeNode ? card.warningElapsedFooterColor : card.completedElapsedFooterColor)
        opacity: liveElapsedActive
            ? card.runningElapsedFooterOpacity
            : (card.isWarningChromeNode ? card.warningElapsedFooterOpacity : card.completedElapsedFooterOpacity)
        renderType: card.nodeTextRenderType
        text: card.formatExecutionElapsed(liveElapsedActive ? elapsedMilliseconds : cachedElapsedMilliseconds)

        property bool liveElapsedActive: card.liveExecutionElapsedVisible
        property bool cachedElapsedActive: card.cachedExecutionElapsedVisible
        property double elapsedMilliseconds: 0.0
        property double startedAtMs: card.runningNodeStartedAtMs
        property double cachedElapsedMilliseconds: card.cachedExecutionElapsedMs

        function _updateElapsed(nowMs) {
            if (!liveElapsedActive || startedAtMs <= 0.0) {
                elapsedMilliseconds = 0.0;
                return;
            }
            var resolvedNowMs = Number(nowMs);
            if (!isFinite(resolvedNowMs))
                resolvedNowMs = Date.now();
            elapsedMilliseconds = Math.max(0.0, resolvedNowMs - startedAtMs);
        }

        function _syncElapsedState() {
            if (!liveElapsedActive) {
                elapsedMilliseconds = 0.0;
                return;
            }
            _updateElapsed(Date.now());
        }

        onLiveElapsedActiveChanged: {
            _syncElapsedState();
            if (card.frameScheduler && card.frameScheduler.registerElapsedHost)
                card.frameScheduler.registerElapsedHost(card, liveElapsedActive);
        }
        onStartedAtMsChanged: _syncElapsedState()
        Component.onCompleted: {
            _syncElapsedState();
            if (card.frameScheduler && card.frameScheduler.registerElapsedHost)
                card.frameScheduler.registerElapsedHost(card, liveElapsedActive);
        }
    }

    // Keep body interactions below the loaded surface so local surface controls can own pointer input.
    GraphNodeHostGestureLayer {
        id: hostGestureLayer
        anchors.fill: parent
        host: card
    }

    Item {
        id: surfaceLayer
        z: 2
        anchors.fill: parent
        visible: card.nodeData ? !card.nodeData.collapsed : false

        GraphNodeSurfaceLoader {
            id: surfaceLoader
            anchors.fill: parent
            anchors.bottomMargin: card.settingsBandHeight
            host: card
            nodeData: card.nodeData
            surfaceSpec: card.surfaceSpec
            surfaceFamily: card.surfaceFamily
            surfaceVariant: card.surfaceVariant
        }
    }

    GraphNodeHeaderLayer {
        id: headerLayer
        anchors.fill: parent
        host: card
        onCollapsedTitleRequiredWidthChanged: card._measuredCollapsedTitleRequiredWidth = collapsedTitleRequiredWidth
        Component.onCompleted: card._measuredCollapsedTitleRequiredWidth = collapsedTitleRequiredWidth
    }

    Item {
        objectName: "graphNodePortsAnimationClip"
        z: 5
        x: -16
        width: card.width + 32
        height: card.height
        clip: card.settingsGroupAnimationRunning

        GraphNodePortsLayer {
            id: portsLayer
            x: 16
            width: card.width
            height: card.height
            host: card
        }
    }

    GraphNodeSettingsGroupsLayer {
        id: settingsGroupsLayer
        anchors.fill: parent
        host: card
        onExpansionRequested: function(nodeId, groupId, expanded) {
            card.settingsGroupExpansionRequested(nodeId, groupId, expanded);
        }
    }

    DropArea {
        id: pathPointerDropArea
        objectName: "graphNodePathPointerDropArea"
        anchors.fill: parent
        z: 5
        enabled: card.pathPointerDropTarget
        keys: ["text/uri-list", "text/plain", "application/x-corex-path-pointer"]

        onEntered: function(drag) { card._updatePathPointerDropData(drag); }
        onPositionChanged: function(drag) { card._updatePathPointerDropData(drag); }
        onExited: {
            card.pathPointerDropData = card._emptyPathPointerDropData();
            card._clearPathPointerDropPreview();
        }
        onDropped: function(drop) { card._finishPathPointerDrop(drop); }
    }

    Rectangle {
        id: pathPointerDropFeedback
        objectName: "graphNodePathPointerDropFeedback"
        anchors.fill: parent
        z: 5
        visible: pathPointerDropArea.containsDrag && card.pathPointerDropValid
        enabled: false
        color: "transparent"
        radius: card.resolvedCornerRadius
        border.width: 2
        border.color: card.selectedOutlineColor

        Rectangle {
            anchors.centerIn: parent
            width: pathPointerDropLabel.implicitWidth + 16
            height: pathPointerDropLabel.implicitHeight + 8
            radius: 4
            color: card.surfaceColor
            border.width: 1
            border.color: card.selectedOutlineColor

            Text {
                id: pathPointerDropLabel
                anchors.centerIn: parent
                text: "Replace path"
                color: card.headerTextColor
                font.pixelSize: 11
                font.bold: true
                renderType: card.nodeTextRenderType
            }
        }
    }

    MouseArea {
        id: lockedNodeOverlay
        objectName: "graphNodeLockedOverlay"
        visible: !!card.nodeData
            && (card.graphReadOnly || (card.authorLocked && card.lockedInteractionEnabled))
        enabled: visible
        anchors.fill: parent
        z: 6
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: true
        preventStealing: true
        cursorShape: card.graphReadOnly && card.lockedPlaceholderActionContains(mouseX, mouseY)
            ? Qt.PointingHandCursor
            : Qt.ArrowCursor

        onPressed: function(mouse) {
            if (!card.nodeData)
                return;
            if (mouse.button === Qt.RightButton && card.graphReadOnly) {
                card.nodeContextRequested(card.nodeData.node_id, mouse.x, mouse.y);
                mouse.accepted = true;
                return;
            }
            mouse.accepted = true;
        }

        onClicked: function(mouse) {
            if (!card.nodeData || mouse.button !== Qt.LeftButton)
                return;
            var additive = Boolean((mouse.modifiers & Qt.ControlModifier) || (mouse.modifiers & Qt.ShiftModifier));
            card.nodeClicked(card.nodeData.node_id, additive);
            if (card.graphReadOnly && card.lockedPlaceholderActionContains(mouse.x, mouse.y))
                card.requestLockedPlaceholderManager();
            mouse.accepted = true;
        }

        onDoubleClicked: function(mouse) {
            if (mouse.button !== Qt.LeftButton)
                return;
            if (card.graphReadOnly && card.lockedPlaceholderActionContains(mouse.x, mouse.y))
                card.requestLockedPlaceholderManager();
            mouse.accepted = true;
        }
    }

    GraphNodeResizeHandle {
        id: topLeftResizeHandle
        host: card
        cornerRole: "topLeft"
    }

    GraphNodeResizeHandle {
        id: topRightResizeHandle
        host: card
        cornerRole: "topRight"
        onFitDisplayedTextRequested: card.inlineTextFitRequested()
    }

    GraphNodeResizeHandle {
        id: bottomLeftResizeHandle
        host: card
        cornerRole: "bottomLeft"
    }

    GraphNodeResizeHandle {
        id: bottomRightResizeHandle
        host: card
        cornerRole: "bottomRight"
        onFitDisplayedTextRequested: card.inlineTextFitRequested()
    }
}
