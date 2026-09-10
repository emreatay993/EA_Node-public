import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../graph/passive/GraphMediaPanelSourceUtils.js" as SourceUtils
import "../graph/surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "../graph/surface_controls/SourceStorageModeUtils.js" as SourceStorageModeUtils

Item {
    id: root
    objectName: root.surfaceMode === "graph" ? "graphNodeWebPageHost" : "webPageHost"
    property var payload: ({})
    property Item host: null
    property var themePalette: ({})
    property var browserStateBridge: null
    property var graphBrowserStateSink: null
    property string surfaceMode: host ? "graph" : "fullscreen"
    property var webEngineItem: null
    property string currentUrl: ""
    property string addressText: ""
    property string documentTitle: ""
    property string policyDeniedText: ""
    property string webEngineCreationError: ""
    property string webEngineLoadError: ""
    property string webEngineDiagnosticText: ""
    property string detachedWindowError: ""
    property var detachedWindow: null
    property var _externalWebEngineOriginalParent: null
    property string _externalWebEngineBorrowMode: ""
    readonly property bool webEngineBorrowedExternally: root._externalWebEngineBorrowMode.length > 0
    readonly property bool webEngineBorrowedForFullscreen: root._externalWebEngineBorrowMode === "fullscreen"
    readonly property bool webEngineBorrowedForDetached: root._externalWebEngineBorrowMode === "detached"
    property bool loading: false
    property int loadProgress: 0
    property bool canGoBack: false
    property bool canGoForward: false
    property real zoomFactor: 1.0
    property string displayMode: "fit_width"
    property bool addressEditorOpen: false
    property string addressEditorText: ""
    property bool canvasExportFallbackActive: false
    property bool _applyingPayload: false
    property int _fitZoomRetryCount: 0
    readonly property int _fitZoomMaxRetries: 3
    readonly property var nodeData: host && host.nodeData ? host.nodeData : ({})
    readonly property string nodeId: _nodeId()
    readonly property var activePayload: _activePayload()
    readonly property string sourceStorageMode: SourceStorageModeUtils.sourceModeForPath(activePayload.start_location || "")
    readonly property var effectiveThemePalette: _effectiveThemePalette()
    readonly property bool graphSurface: root.surfaceMode === "graph"
    readonly property bool webEngineAvailable: Boolean(activePayload.webengine_available)
    readonly property bool liveBrowserAllowed: !root.graphSurface || root.webEngineAvailable
    readonly property bool autoFitZoomActive: root.displayMode === "fit_width" || root.displayMode === "fit_page"
    readonly property bool graphInlineNativeFitWidthActive: root.graphSurface && root.displayMode === "fit_width"
    readonly property string statusState: _statusState()
    readonly property bool statusVisible: root.statusState.length > 0
    readonly property var nodeProperties: root.nodeData && root.nodeData.properties ? root.nodeData.properties : ({})
    readonly property var previewRef: root._previewRef()
    readonly property string previewSourceRef: root._previewSourceRef(root.previewRef)
    readonly property string previewImageSource: root.previewSourceRef.length > 0
        ? SourceUtils.previewSourceUrl(root.previewSourceRef)
        : ""
    readonly property bool chromeTitleVisible: !root.graphSurface || root._boolValue("show_title", true)
    readonly property bool chromeFrameVisible: !root.graphSurface || root._boolValue("show_frame", true)
    readonly property bool chromeContentOnlyActive: root.graphSurface
        && !root.chromeTitleVisible
        && !root.chromeFrameVisible
    readonly property real contentMargin: root.graphSurface
        ? (root.chromeFrameVisible ? 6 : 0)
        : 10
    readonly property bool shouldLoadWebEngine: (root.visible || root.webEngineBorrowedExternally)
        && root.liveBrowserAllowed
        && root.webEngineAvailable
        && root.currentUrl.length > 0
        && root.policyDeniedText.length === 0
        && root.webEngineCreationError.length === 0
    readonly property bool fullscreenAvailable: host ? Boolean(host.surfaceFullscreenAvailable) : false
    readonly property var surfaceActions: {
        if (!root.host || !root.graphSurface)
            return [];
        var actions = [
            {
                "id": "web_page_back",
                "label": "Back",
                "icon": "browser-back",
                "kind": "web_page",
                "enabled": root.canGoBack,
                "primary": false
            },
            {
                "id": "web_page_forward",
                "label": "Forward",
                "icon": "browser-forward",
                "kind": "web_page",
                "enabled": root.canGoForward,
                "primary": false
            },
            {
                "id": "web_page_reload_stop",
                "label": root.loading ? "Stop" : "Reload",
                "icon": root.loading ? "browser-stop" : "browser-reload",
                "kind": "web_page",
                "enabled": root.currentUrl.length > 0,
                "primary": false
            },
            {
                "id": "web_page_edit_address",
                "label": "Address",
                "icon": "world-www",
                "kind": "web_page",
                "enabled": true,
                "primary": false
            },
            {
                "id": "web_page_local_html",
                "label": "Local HTML",
                "icon": "file-type-html",
                "kind": "surface",
                "enabled": true,
                "primary": String(root.activePayload.start_location || "").trim().length === 0,
                "popover_layout": "source_storage",
                "popoverActions": [
                    {
                        "id": "web_page_local_html_external",
                        "label": "External link",
                        "icon": "external-link",
                        "kind": "surface",
                        "toolbar_text": "External",
                        "source_mode": "external_link",
                        "checked": root.sourceStorageMode === "external_link",
                        "enabled": true,
                        "close_popover": true
                    },
                    {
                        "id": "web_page_local_html_managed",
                        "label": "Internal copy",
                        "icon": "open-session",
                        "kind": "surface",
                        "toolbar_text": "Internal",
                        "source_mode": "managed_copy",
                        "checked": root.sourceStorageMode === "managed_copy",
                        "enabled": true,
                        "close_popover": true
                    }
                ]
            },
            {
                "id": "web_page_display_mode",
                "label": "Display mode",
                "icon": "zoom-fit",
                "kind": "surface",
                "enabled": true,
                "primary": false,
                "popoverActions": [
                    {
                        "id": "web_page_display_responsive",
                        "label": "Responsive",
                        "toolbar_text": "Responsive",
                        "kind": "surface",
                        "checked": root.displayMode === "responsive",
                        "enabled": true,
                        "close_popover": true
                    },
                    {
                        "id": "web_page_display_fit_width",
                        "label": "Fit width",
                        "toolbar_text": "Fit width",
                        "kind": "surface",
                        "checked": root.displayMode === "fit_width",
                        "enabled": true,
                        "close_popover": true
                    },
                    {
                        "id": "web_page_display_fit_page",
                        "label": "Fit page",
                        "toolbar_text": "Fit page",
                        "kind": "surface",
                        "checked": root.displayMode === "fit_page",
                        "enabled": true,
                        "close_popover": true
                    }
                ]
            }
        ];
        actions.push({
            "id": "toggle_content_only",
            "label": root.chromeContentOnlyActive ? "Show chrome" : "Content only",
            "icon": root.chromeContentOnlyActive ? "node-chrome" : "content-only",
            "kind": "surface",
            "enabled": true,
            "primary": root.chromeContentOnlyActive
        });
        actions.push({
            "id": "toggle_title",
            "label": root.chromeTitleVisible ? "Hide title" : "Show title",
            "icon": "title-heading",
            "kind": "surface",
            "enabled": true,
            "primary": false
        });
        actions.push({
            "id": "toggle_frame",
            "label": root.chromeFrameVisible ? "Hide frame" : "Show frame",
            "icon": "frame-corners",
            "kind": "surface",
            "enabled": true,
            "primary": false
        });
        var fullscreenAction = root.host.surfaceFullscreenAction
            ? root.host.surfaceFullscreenAction(root.fullscreenAvailable, false)
            : null;
        if (fullscreenAction)
            actions.push(fullscreenAction);
        actions.push({
            "id": "web_page_detach",
            "label": "Detach",
            "icon": "browser-detach",
            "kind": "web_page",
            "enabled": root.currentUrl.length > 0 || String(root.activePayload.start_location || "").trim().length > 0,
            "primary": false
        });
        return actions;
    }
    readonly property bool blocksHostInteraction: false
    readonly property var embeddedInteractiveRects: {
        if (!root.host || !root.graphSurface)
            return SurfaceControlGeometry.combineRectLists([]);
        // Reference geometry so the binding recomputes on resize/move/layout
        // (mapToItem is not a reactive dependency on its own).
        var _vw = viewportFrame.width;
        var _vh = viewportFrame.height;
        var _rw = root.width;
        var _rh = root.height;
        var lists = [];
        if (root.shouldLoadWebEngine) {
            var viewportRect = SurfaceControlGeometry.rectFromItem(viewportFrame, root.host);
            if (viewportRect)
                lists.push([viewportRect]);
        }
        return SurfaceControlGeometry.combineRectLists(lists);
    }
    signal fullscreenRequested()
    signal detachedRequested()

    clip: true

    onActivePayloadChanged: {
        Qt.callLater(root._applyPayload);
        Qt.callLater(root._syncWebEngineItem);
    }
    onVisibleChanged: {
        if (visible) {
            Qt.callLater(root._applyPayload);
            Qt.callLater(root._syncWebEngineItem);
        } else {
            root.cancelAddressEdit();
            root.flushBrowserState();
            if (!root.webEngineBorrowedExternally && !root._parkWebEngineItemForWorkspaceSwitch())
                root._destroyWebEngineItem();
        }
    }
    onShouldLoadWebEngineChanged: Qt.callLater(root._syncWebEngineItem)
    onCurrentUrlChanged: {
        root.addressText = root.currentUrl;
        root._scheduleBrowserStatePersist();
        Qt.callLater(root._syncWebEngineItem);
    }
    onDocumentTitleChanged: root._scheduleBrowserStatePersist()
    onZoomFactorChanged: {
        if (root.webEngineItem)
            root.webEngineItem.pageZoom = root.zoomFactor;
        root._scheduleBrowserStatePersist();
    }
    onDisplayModeChanged: root._handleDisplayModeChanged()
    onEffectiveThemePaletteChanged: {
        if (root.webEngineItem)
            root.webEngineItem.pageBackgroundColor = root._webEngineBackgroundColor();
    }

    Component.onCompleted: {
        root._applyPayload();
        Qt.callLater(root._syncWebEngineItem);
    }
    Component.onDestruction: {
        root.flushBrowserState();
        if (root.detachedWindow)
            root.detachedWindow.destroy();
        if (!root._parkWebEngineItemForWorkspaceSwitch())
            root._destroyWebEngineItem();
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "web_page_back") {
            root.goBack();
            return true;
        }
        if (normalized === "web_page_forward") {
            root.goForward();
            return true;
        }
        if (normalized === "web_page_reload_stop") {
            root.reloadOrStop();
            return true;
        }
        if (normalized === "web_page_edit_address")
            return root._openAddressEditor();
        if (normalized === "web_page_local_html_external")
            return root._chooseLocalHtmlSource("external_link");
        if (normalized === "web_page_local_html_managed")
            return root._chooseLocalHtmlSource("managed_copy");
        if (normalized === "web_page_display_responsive")
            return root._setDisplayMode("responsive");
        if (normalized === "web_page_display_fit_width")
            return root._setDisplayMode("fit_width");
        if (normalized === "web_page_display_fit_page")
            return root._setDisplayMode("fit_page");
        if (normalized === "toggle_content_only") {
            return root.chromeContentOnlyActive
                ? root._commitChromeAppearance(true, true)
                : root._commitChromeAppearance(false, false);
        }
        if (normalized === "toggle_title")
            return root._commitChromeAppearance(!root.chromeTitleVisible, root.chromeFrameVisible);
        if (normalized === "toggle_frame")
            return root._commitChromeAppearance(root.chromeTitleVisible, !root.chromeFrameVisible);
        if (normalized === "web_page_detach")
            return root._requestDetached();
        if (normalized === "fullscreen")
            return root._requestFullscreen();
        return false;
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        if (!root.addressEditorOpen)
            return false;
        root.cancelAddressEdit();
        return true;
    }

    function navigateTo(location) {
        var navigationLocation = root._navigationLocation(location);
        var decision = root._decideNavigation(navigationLocation);
        root.addressText = String(location || "").trim();
        root.documentTitle = "";
        root.webEngineLoadError = "";
        root.webEngineDiagnosticText = "";
        if (!Boolean(decision.allowed)) {
            root.policyDeniedText = String(decision.reason || "Navigation is not allowed.");
            root.currentUrl = "";
            root._destroyWebEngineItem();
            return false;
        }
        root.policyDeniedText = "";
        root.currentUrl = String(decision.target_url || "");
        return root.currentUrl.length > 0;
    }

    function _beginInlineInteraction() {
        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
    }

    function _commitNodeProperty(key, value) {
        if (root.host && root.host.nodeData && root.host.inlinePropertyCommitted)
            root.host.inlinePropertyCommitted(String(root.host.nodeData.node_id || ""), key, value);
    }

    function _commitChromeAppearance(showTitle, showFrame) {
        root._beginInlineInteraction();
        root._commitNodeProperty("show_title", Boolean(showTitle));
        root._commitNodeProperty("show_frame", Boolean(showFrame));
        return true;
    }

    function _rawValue(key, fallback) {
        var value = root.nodeProperties[key];
        return value === undefined || value === null ? fallback : value;
    }

    function _boolValue(key, fallback) {
        var value = root._rawValue(key, fallback);
        if (typeof value === "boolean")
            return value;
        if (typeof value === "string") {
            var normalized = value.trim().toLowerCase();
            if (normalized === "true" || normalized === "1" || normalized === "yes")
                return true;
            if (normalized === "false" || normalized === "0" || normalized === "no")
                return false;
        }
        return Boolean(value);
    }

    function _chooseLocalHtmlSource(sourceMode) {
        if (!root.graphSurface || !root.host || !root.host.browseNodePropertyPath)
            return false;
        var normalizedSourceMode = SourceStorageModeUtils.normalizedSourceMode(sourceMode, root.sourceStorageMode);
        var currentPath = String(root.activePayload.start_location || root._addressPopoverSourceText() || "").trim();
        root._beginInlineInteraction();
        var selectedPath = String(root.host.browseNodePropertyPath("start_location", currentPath, normalizedSourceMode) || "").trim();
        if (!selectedPath.length || selectedPath === currentPath)
            return false;
        root.cancelAddressEdit();
        root._applyingPayload = true;
        root.navigateTo(selectedPath);
        root._applyingPayload = false;
        root._commitNodeProperty("browser_state", {});
        root._commitNodeProperty("start_location", selectedPath);
        return true;
    }

    function _setDisplayMode(mode) {
        var normalized = root._displayMode(mode);
        root.displayMode = normalized;
        if (root.graphSurface)
            root._commitNodeProperty("display_mode", normalized);
        root._handleDisplayModeChanged();
        return true;
    }

    function goBack() {
        if (root.webEngineItem && root.webEngineItem.goBack)
            root.webEngineItem.goBack();
    }

    function goForward() {
        if (root.webEngineItem && root.webEngineItem.goForward)
            root.webEngineItem.goForward();
    }

    function reloadOrStop() {
        if (!root.webEngineItem)
            return;
        if (root.loading && root.webEngineItem.stop)
            root.webEngineItem.stop();
        else if (root.webEngineItem.reload)
            root.webEngineItem.reload();
    }

    function goHome() {
        var home = String(root.activePayload.start_location || "").trim();
        if (home.length)
            root.navigateTo(home);
    }

    function _addressPopoverSourceText() {
        if (root.addressText.length > 0)
            return root.addressText;
        if (root.currentUrl.length > 0)
            return root.currentUrl;
        return String(root.activePayload.start_location || "").trim();
    }

    function _openAddressEditor() {
        if (!root.graphSurface)
            return false;
        root.addressEditorText = root._addressPopoverSourceText();
        root.addressEditorOpen = true;
        return true;
    }

    function acceptAddressEdit(location) {
        root.addressEditorOpen = false;
        var navigated = root.navigateTo(location);
        if (navigated)
            root.flushBrowserState();
        return navigated;
    }

    function cancelAddressEdit() {
        root.addressEditorOpen = false;
    }

    function zoomIn() {
        root._beginManualZoom();
        root.zoomFactor = Math.min(3.0, Math.round((root.zoomFactor + 0.1) * 10.0) / 10.0);
    }

    function zoomOut() {
        root._beginManualZoom();
        root.zoomFactor = Math.max(0.25, Math.round((root.zoomFactor - 0.1) * 10.0) / 10.0);
    }

    function zoomReset() {
        root._beginManualZoom();
        root.zoomFactor = 1.0;
    }

    function _beginManualZoom() {
        if (root.autoFitZoomActive)
            root.displayMode = "responsive";
    }

    function _requestFullscreen() {
        if (host && host.requestSurfaceContentFullscreen)
            return Boolean(host.requestSurfaceContentFullscreen());
        root.fullscreenRequested();
        return true;
    }

    function _hasBorrowableWebEngineForExternalPresentation(nodeId) {
        var requestedNodeId = String(nodeId || "").trim();
        return root.graphSurface
            && root.nodeId.length > 0
            && (!requestedNodeId.length || requestedNodeId === root.nodeId)
            && root.webEngineItem
            && !root.webEngineBorrowedExternally
            && root.shouldLoadWebEngine
            && root.policyDeniedText.length === 0
            && root.webEngineCreationError.length === 0;
    }

    function _attachWebEngineToExternalPresentation(target, nodeId, mode) {
        var normalizedMode = String(mode || "").trim();
        if (!target || !normalizedMode.length || !root._hasBorrowableWebEngineForExternalPresentation(nodeId))
            return false;
        var item = root.webEngineItem;
        var originalParent = item.parent || webViewport;
        try {
            item.parent = target;
            item.visible = true;
            item.anchors.fill = target;
        } catch (error) {
            try {
                item.parent = originalParent;
                item.visible = true;
                item.anchors.fill = originalParent;
            } catch (restoreError) {
            }
            return false;
        }
        root._externalWebEngineOriginalParent = originalParent;
        root._externalWebEngineBorrowMode = normalizedMode;
        root._scheduleFitZoom(true);
        return true;
    }

    function _releaseExternalWebEngine(mode) {
        var normalizedMode = String(mode || "").trim();
        if (!root.webEngineBorrowedExternally)
            return false;
        if (normalizedMode.length > 0 && root._externalWebEngineBorrowMode !== normalizedMode)
            return false;
        var restoreParent = root._externalWebEngineOriginalParent || webViewport;
        if (root.webEngineItem) {
            root.webEngineItem.parent = restoreParent;
            root.webEngineItem.visible = true;
            root.webEngineItem.anchors.fill = restoreParent;
        }
        root._externalWebEngineBorrowMode = "";
        root._externalWebEngineOriginalParent = null;
        root._scheduleFitZoom(true);
        if (!root.visible)
            Qt.callLater(root._syncWebEngineItem);
        return true;
    }

    function hasBorrowableWebEngineForFullscreen(nodeId) {
        return root._hasBorrowableWebEngineForExternalPresentation(nodeId);
    }

    function attachWebEngineToFullscreen(target, nodeId) {
        return root._attachWebEngineToExternalPresentation(target, nodeId, "fullscreen");
    }

    function releaseFullscreenWebEngine() {
        return root._releaseExternalWebEngine("fullscreen");
    }

    function hasBorrowableWebEngineForDetached(nodeId) {
        return root._hasBorrowableWebEngineForExternalPresentation(nodeId);
    }

    function attachWebEngineToDetached(target, nodeId) {
        return root._attachWebEngineToExternalPresentation(target, nodeId, "detached");
    }

    function releaseDetachedWebEngine() {
        return root._releaseExternalWebEngine("detached");
    }

    function prepareForCanvasExport() {
        if (!root.graphSurface)
            return {"ready": true, "node_id": root.nodeId, "fallback_active": false};
        root._syncWebEngineItem();
        root.canvasExportFallbackActive = root._shouldUseCanvasExportFallback();
        return {
            "ready": root.canvasExportReady(),
            "node_id": root.nodeId,
            "fallback_active": root.canvasExportFallbackActive,
            "has_preview_ref": root.previewSourceRef.length > 0,
            "loading": root.loading,
            "load_progress": root.loadProgress
        };
    }

    function finishCanvasExport() {
        root.canvasExportFallbackActive = false;
    }

    function canvasExportReady() {
        if (!root.graphSurface)
            return true;
        if (root.statusVisible)
            return root.previewImageSource.length > 0;
        if (!root.shouldLoadWebEngine)
            return true;
        var progress = Math.max(0, Math.min(100, Number(root.loadProgress || 0)));
        if (!root.webEngineItem || root.loading || progress < 100)
            return root.previewImageSource.length > 0;
        return true;
    }

    function _shouldUseCanvasExportFallback() {
        if (!root.graphSurface || root.previewImageSource.length <= 0)
            return false;
        if (root.statusVisible)
            return true;
        if (!root.shouldLoadWebEngine)
            return false;
        var progress = Math.max(0, Math.min(100, Number(root.loadProgress || 0)));
        return !root.webEngineItem || root.loading || progress < 100;
    }

    function _webPageRetentionStore() {
        if (root.host && root.host.canvasItem && root.host.canvasItem.webPageRetentionStore)
            return root.host.canvasItem.webPageRetentionStore;
        return null;
    }

    function _retentionWorkspaceId() {
        return String(
            root.activePayload.workspace_id
            || (root.nodeData ? root.nodeData.workspace_id : "")
            || ""
        ).trim();
    }

    function _retentionKey() {
        var store = root._webPageRetentionStore();
        if (!store || !store.keyFor)
            return "";
        return store.keyFor(root._retentionWorkspaceId(), root.nodeId);
    }

    function _previewRef() {
        return root._normalizedPreviewRef(
            root.activePayload.preview_ref
            || (root.activePayload.properties && root.activePayload.properties.preview_ref)
            || root.nodeProperties.preview_ref
            || ({})
        );
    }

    function _normalizedPreviewRef(value) {
        if (value === undefined || value === null)
            return ({});
        if (typeof value === "string") {
            var text = value.trim();
            if (!text.length)
                return ({});
            try {
                var parsed = JSON.parse(text);
                return parsed && typeof parsed === "object" ? parsed : {"artifact_ref": text};
            } catch (error) {
                return {"artifact_ref": text};
            }
        }
        return typeof value === "object" ? value : ({});
    }

    function _previewSourceRef(ref) {
        var data = ref && typeof ref === "object" ? ref : ({});
        var candidates = [
            data.uri,
            data.artifact_ref,
            data.preview_ref,
            data.ref,
            data.artifact_id,
            data.path
        ];
        for (var index = 0; index < candidates.length; index++) {
            var value = String(candidates[index] || "").trim();
            if (value.length > 0)
                return value;
        }
        return "";
    }

    function _handleWebEngineNavigationRequested(url) {
        if (!root.webEngineItem)
            return;
        root.webEngineItem.navigationAllowed = root._requestNavigationFromPage(url);
    }

    function _connectWebEngineItemSignals(item) {
        if (!item)
            return;
        try { item.loadStatusChanged.connect(root._handleWebEngineLoadStatus); } catch (error) {}
        try { item.documentTitleReported.connect(root._handleWebEngineTitleChanged); } catch (error) {}
        try { item.webEngineDiagnostic.connect(root._handleWebEngineDiagnostic); } catch (error) {}
        try { item.pageFullscreenRequested.connect(root._handleWebEnginePageFullscreen); } catch (error) {}
        try { item.contentMetricsReady.connect(root._applyFitZoomForMetrics); } catch (error) {}
        try { item.navigationRequestedByPage.connect(root._handleWebEngineNavigationRequested); } catch (error) {}
    }

    function _disconnectWebEngineItemSignals(item) {
        if (!item)
            return;
        try { item.loadStatusChanged.disconnect(root._handleWebEngineLoadStatus); } catch (error) {}
        try { item.documentTitleReported.disconnect(root._handleWebEngineTitleChanged); } catch (error) {}
        try { item.webEngineDiagnostic.disconnect(root._handleWebEngineDiagnostic); } catch (error) {}
        try { item.pageFullscreenRequested.disconnect(root._handleWebEnginePageFullscreen); } catch (error) {}
        try { item.contentMetricsReady.disconnect(root._applyFitZoomForMetrics); } catch (error) {}
        try { item.navigationRequestedByPage.disconnect(root._handleWebEngineNavigationRequested); } catch (error) {}
    }

    function _parkWebEngineItemForWorkspaceSwitch() {
        if (!root.graphSurface || !root.webEngineItem)
            return false;
        if (root.webEngineBorrowedExternally)
            root._releaseExternalWebEngine(root._externalWebEngineBorrowMode);
        var store = root._webPageRetentionStore();
        if (!store || !store.shouldParkForWorkspaceSwitch || !store.shouldParkForWorkspaceSwitch())
            return false;
        var key = root._retentionKey();
        if (!key.length || !root.currentUrl.length)
            return false;
        var item = root.webEngineItem;
        root._disconnectWebEngineItemSignals(item);
        if (!store.parkPage(key, item, {
                "workspace_id": root._retentionWorkspaceId(),
                "node_id": root.nodeId,
                "current_url": root.currentUrl
            })) {
            root._connectWebEngineItemSignals(item);
            return false;
        }
        root.webEngineItem = null;
        root._externalWebEngineBorrowMode = "";
        root._externalWebEngineOriginalParent = null;
        root.loading = false;
        root.canGoBack = false;
        root.canGoForward = false;
        return true;
    }

    function _claimRetainedWebEngineItem() {
        if (!root.graphSurface)
            return false;
        var store = root._webPageRetentionStore();
        if (!store || !store.claimPage)
            return false;
        var key = root._retentionKey();
        if (!key.length)
            return false;
        var item = store.claimPage(key, root.currentUrl, webViewport, true);
        if (!item)
            return false;
        root.webEngineItem = item;
        root._connectWebEngineItemSignals(root.webEngineItem);
        root._externalWebEngineBorrowMode = "";
        root._externalWebEngineOriginalParent = null;
        var retainedUrl = String(root.webEngineItem.pageUrl || "").trim();
        if (retainedUrl.length > 0 && retainedUrl !== root.currentUrl) {
            root.currentUrl = retainedUrl;
            root.addressText = retainedUrl;
        }
        return true;
    }

    function _requestDetached() {
        if (!root.currentUrl.length && !String(root.activePayload.start_location || "").trim().length)
            return false;
        var liveGraphSourceHost = root.graphSurface && root.webEngineItem ? root : null;
        if (!root.detachedWindow) {
            var component = Qt.createComponent(Qt.resolvedUrl("WebPageDetachedWindow.qml"));
            if (component.status === Component.Error) {
                root.detachedWindowError = component.errorString();
                return false;
            }
            root.detachedWindow = component.createObject(root, {
                "payload": root.activePayload,
                "themePalette": root.effectiveThemePalette,
                "browserStateBridge": root.browserStateBridge
            });
            if (!root.detachedWindow) {
                root.detachedWindowError = "Detached web page window could not be created.";
                return false;
            }
        }
        if (!root.detachedWindow.openWindow(root.activePayload, root.currentUrl, liveGraphSourceHost)) {
            root.detachedWindowError = "Detached web page window could not attach to the live page.";
            return false;
        }
        root.detachedWindowError = "";
        root.detachedRequested();
        return true;
    }

    function _activePayload() {
        if (root.payload && typeof root.payload === "object" && Object.keys(root.payload).length > 0)
            return root.payload;
        if (root.nodeData && root.nodeData.web_page_payload && typeof root.nodeData.web_page_payload === "object")
            return root.nodeData.web_page_payload;
        return ({});
    }

    function _nodeId() {
        var payloadNodeId = String(root.activePayload.node_id || "").trim();
        if (payloadNodeId.length > 0)
            return payloadNodeId;
        return String(root.nodeData && root.nodeData.node_id ? root.nodeData.node_id : "").trim();
    }

    function _applyPayload() {
        var nextPayload = root.activePayload || ({});
        root._applyingPayload = true;
        root.webEngineCreationError = "";
        root.webEngineLoadError = "";
        root.webEngineDiagnosticText = "";
        root.detachedWindowError = "";
        root.loading = false;
        root.loadProgress = 0;
        root.displayMode = root._displayModeFromPayload(nextPayload);
        root.zoomFactor = root.autoFitZoomActive ? 1.0 : root._zoomFromPayload(nextPayload);
        root.documentTitle = root._documentTitleFromPayload(nextPayload);

        var location = String(nextPayload.current_location || "").trim();
        if (!location.length && nextPayload.browser_state && typeof nextPayload.browser_state === "object") {
            location = String(
                nextPayload.browser_state.current_url
                || nextPayload.browser_state.current_location
                || nextPayload.browser_state.url
                || ""
            ).trim();
        }
        if (!location.length)
            location = String(nextPayload.start_location || "").trim();

        var navigationLocation = String(nextPayload.navigation_location || "").trim();
        if (!navigationLocation.length)
            navigationLocation = root._navigationLocation(location);

        var decision = nextPayload.navigation_decision && typeof nextPayload.navigation_decision === "object"
            ? nextPayload.navigation_decision
            : ({});
        if (!Boolean(decision.allowed)
                && navigationLocation.length > 0
                && navigationLocation !== location) {
            decision = root._decideNavigation(navigationLocation);
        }
        if (Boolean(decision.allowed)) {
            root.policyDeniedText = "";
            root.currentUrl = String(decision.target_url || location || "").trim();
            root.addressText = root.currentUrl;
            root._finishApplyPayload();
            return;
        }
        if (location.length > 0 && String(decision.reason || "").length === 0) {
            root.navigateTo(location);
            root._finishApplyPayload();
            return;
        }
        root.currentUrl = "";
        root.addressText = location;
        root.policyDeniedText = location.length > 0
            ? String(decision.reason || "Navigation is not allowed.")
            : "";
        root._finishApplyPayload();
    }

    function _finishApplyPayload() {
        root._applyingPayload = false;
        if (root.autoFitZoomActive)
            Qt.callLater(root._scheduleFitZoomReset);
    }

    function _effectiveThemePalette() {
        if (root.themePalette && typeof root.themePalette === "object" && Object.keys(root.themePalette).length > 0)
            return root.themePalette;
        if (root.host)
            return root._hostThemePalette();
        if (typeof themeBridge !== "undefined" && themeBridge && themeBridge.palette)
            return themeBridge.palette;
        return ({});
    }

    function _hostThemePalette() {
        return {
            "panel_bg": String(root.host.surfaceColor || "#1f2431"),
            "panel_fg": String(root.host.inlineInputTextColor || root.host.headerTextColor || "#eef3ff"),
            "panel_title_fg": String(root.host.headerTextColor || "#eef3ff"),
            "toolbar_bg": String(root.host.headerColor || root.host.surfaceColor || "#202635"),
            "border": String(root.host.outlineColor || "#3a4355"),
            "input_bg": String(root.host.inlineInputBackgroundColor || root.host.surfaceColor || "#151821"),
            "input_border": String(root.host.inlineInputBorderColor || root.host.outlineColor || "#3a4355"),
            "input_fg": String(root.host.inlineInputTextColor || root.host.headerTextColor || "#eef3ff"),
            "muted_fg": String(root.host.inlineDrivenTextColor || root.host.portLabelColor || "#95a0b8"),
            "accent": String(root.host.selectedOutlineColor || "#5da9ff"),
            "hover": String(root.host.inlineRowColor || "#33405c"),
            "pressed": String(root.host.inlineInputBorderColor || "#22304a"),
            "error": "#d94f4f"
        };
    }

    function _persistBrowserStateEnabled() {
        if (root.activePayload.persist_browser_state === undefined || root.activePayload.persist_browser_state === null)
            return true;
        var text = String(root.activePayload.persist_browser_state).trim().toLowerCase();
        return !(text === "0" || text === "false" || text === "no" || text === "off");
    }

    function _browserStateCanPersist() {
        if (root.graphSurface)
            return Boolean(root.graphBrowserStateSink);
        return Boolean(root.browserStateBridge && root.browserStateBridge.save_web_page_browser_state);
    }

    function _scheduleBrowserStatePersist() {
        if (root._applyingPayload || !root._persistBrowserStateEnabled())
            return;
        if (!root._browserStateCanPersist())
            return;
        if (!root.currentUrl.length)
            return;
        browserStatePersistTimer.restart();
    }

    function flushBrowserState() {
        browserStatePersistTimer.stop();
        return root._persistBrowserState();
    }

    function _persistBrowserState() {
        if (!root._persistBrowserStateEnabled())
            return false;
        if (!root.currentUrl.length)
            return false;
        var state = {
            "current_url": root._browserStateCurrentUrl(),
            "zoom_factor": root.zoomFactor
        };
        if (root.documentTitle.length > 0)
            state["page_title"] = root.documentTitle;
        if (root.graphSurface) {
            if (!root.graphBrowserStateSink)
                return false;
            try {
                return Boolean(root.graphBrowserStateSink.persistWebPageBrowserState(state));
            } catch (error) {
                return false;
            }
        }
        if (!root.browserStateBridge || !root.browserStateBridge.save_web_page_browser_state)
            return false;
        return Boolean(root.browserStateBridge.save_web_page_browser_state(state));
    }

    function _webEngineBackgroundColor() {
        return String(
            root.effectiveThemePalette.input_bg
            || root.effectiveThemePalette.panel_bg
            || "#ffffff"
        );
    }

    function _zoomFromPayload(nextPayload) {
        var value = Number(nextPayload.zoom_factor);
        if (!isFinite(value) && nextPayload.browser_state && typeof nextPayload.browser_state === "object")
            value = Number(nextPayload.browser_state.zoom_factor || nextPayload.browser_state.zoom || NaN);
        if (!isFinite(value) || value <= 0.0)
            value = 1.0;
        return Math.max(0.25, Math.min(3.0, value));
    }

    function _displayMode(value) {
        var normalized = String(value || "fit_width").trim().toLowerCase();
        if (normalized === "fit_width" || normalized === "fit_page")
            return normalized;
        if (normalized === "responsive")
            return normalized;
        return "fit_width";
    }

    function _displayModeFromPayload(nextPayload) {
        return root._displayMode(nextPayload.display_mode
            || (nextPayload.properties && nextPayload.properties.display_mode)
            || "fit_width");
    }

    function _displayDocumentTitle(value) {
        return String(value || "").replace(/\s+/g, " ").trim();
    }

    function _documentTitleFromPayload(nextPayload) {
        var state = nextPayload.browser_state && typeof nextPayload.browser_state === "object"
            ? nextPayload.browser_state
            : ({});
        return root._displayDocumentTitle(nextPayload.page_title || state.page_title || "");
    }

    function _handleWebEngineTitleChanged(title) {
        var normalized = root._displayDocumentTitle(title);
        if (root.documentTitle !== normalized)
            root.documentTitle = normalized;
    }

    function _handleDisplayModeChanged() {
        if (root.autoFitZoomActive) {
            if (Math.abs(root.zoomFactor - 1.0) > 0.001)
                root.zoomFactor = 1.0;
            root._scheduleFitZoom(true);
            Qt.callLater(root._scheduleFitZoomFollowUp);
            return;
        }
        var payloadZoom = root._zoomFromPayload(root.activePayload || ({}));
        if (Math.abs(root.zoomFactor - payloadZoom) > 0.001)
            root.zoomFactor = payloadZoom;
    }

    function _scheduleFitZoomReset() {
        root._scheduleFitZoom(true);
    }

    function _scheduleFitZoomFollowUp() {
        root._scheduleFitZoom(false);
    }

    function _graphResizeActive() {
        if (!root.graphSurface || !root.host)
            return false;
        try {
            return Boolean(root.host._resizeInteractionActive);
        } catch (error) {
            return false;
        }
    }

    function _scheduleFitZoomAfterResize() {
        fitZoomAfterResizeTimer.restart();
    }

    function _scheduleFitZoom(resetRetry, deferForResize) {
        if (Boolean(resetRetry))
            root._fitZoomRetryCount = 0;
        if (Boolean(deferForResize) && root._graphResizeActive()) {
            root._scheduleFitZoomAfterResize();
            return;
        }
        if (!root.autoFitZoomActive || !root.webEngineItem || root.statusVisible)
            return;
        fitZoomTimer.restart();
    }

    function _retryFitZoom() {
        if (!root.autoFitZoomActive || !root.webEngineItem || root.statusVisible)
            return;
        if (root._graphResizeActive()) {
            root._scheduleFitZoomAfterResize();
            return;
        }
        if (root._fitZoomRetryCount >= root._fitZoomMaxRetries)
            return;
        root._fitZoomRetryCount += 1;
        fitZoomTimer.restart();
    }

    function _requestFitZoomMetrics() {
        if (root._applyGraphInlineNativeFitWidthZoom())
            return;
        if (!root.autoFitZoomActive || !root.webEngineItem || !root.webEngineItem.requestContentMetrics)
            return;
        if (root._graphResizeActive()) {
            root._scheduleFitZoomAfterResize();
            return;
        }
        root.webEngineItem.requestContentMetrics();
    }

    function _applyGraphInlineNativeFitWidthZoom() {
        if (!root.graphInlineNativeFitWidthActive)
            return false;
        if (Math.abs(root.zoomFactor - 1.0) > 0.005)
            root.zoomFactor = 1.0;
        return true;
    }

    function _applyFitZoomForMetrics(contentWidth, contentHeight) {
        if (!root.autoFitZoomActive)
            return;
        if (root._applyGraphInlineNativeFitWidthZoom())
            return;
        if (root._graphResizeActive()) {
            root._scheduleFitZoomAfterResize();
            return;
        }
        var resolvedContentWidth = Number(contentWidth || 0);
        var resolvedContentHeight = Number(contentHeight || 0);
        var viewportWidth = Math.max(1.0, Number(webViewport.width || 0));
        var viewportHeight = Math.max(1.0, Number(webViewport.height || 0));
        if (!isFinite(resolvedContentWidth) || resolvedContentWidth <= 0.0) {
            root._retryFitZoom();
            return;
        }
        var nextZoom = viewportWidth / resolvedContentWidth;
        if (root.displayMode === "fit_page"
                && isFinite(resolvedContentHeight)
                && resolvedContentHeight > 0.0) {
            nextZoom = Math.min(nextZoom, viewportHeight / resolvedContentHeight);
        }
        if (!isFinite(nextZoom) || nextZoom <= 0.0) {
            root._retryFitZoom();
            return;
        }
        nextZoom = Math.max(0.25, Math.min(3.0, Math.round(nextZoom * 100.0) / 100.0));
        if (Math.abs(root.zoomFactor - nextZoom) > 0.005)
            root.zoomFactor = nextZoom;
        root._retryFitZoom();
    }

    function _statusState() {
        if (root.policyDeniedText.length > 0)
            return "policy_denied";
        if (root.detachedWindowError.length > 0)
            return "detach_error";
        if (root.graphSurface && root.webEngineBorrowedForDetached)
            return "detached";
        if (!root.webEngineAvailable)
            return "webengine_unavailable";
        if (root.webEngineCreationError.length > 0 || root.webEngineLoadError.length > 0)
            return "load_error";
        if (!root.currentUrl.length)
            return "empty";
        return "";
    }

    function _statusTitle() {
        if (root.statusState === "policy_denied")
            return "Navigation blocked";
        if (root.statusState === "detach_error")
            return "Detach failed";
        if (root.statusState === "detached")
            return "Web page detached";
        if (root.statusState === "webengine_unavailable")
            return "WebEngine unavailable";
        if (root.statusState === "load_error")
            return "Page load failed";
        return "Web page";
    }

    function _statusMessage() {
        if (root.statusState === "policy_denied")
            return root.policyDeniedText;
        if (root.statusState === "detach_error")
            return root.detachedWindowError;
        if (root.statusState === "detached")
            return "Close the detached window to return this live page to the canvas.";
        if (root.statusState === "webengine_unavailable")
            return root._webEngineUnavailableText();
        if (root.statusState === "load_error")
            return root.webEngineCreationError.length > 0 ? root.webEngineCreationError : root.webEngineLoadError;
        if (root.statusState === "empty")
            return "Enter a URL or local HTML path to load a page.";
        return "";
    }

    function _statusDetail() {
        if (root.currentUrl.length > 0)
            return root.currentUrl;
        if (root.addressText.length > 0)
            return root.addressText;
        return String(root.activePayload.start_location || "");
    }

    function _statusActionText() {
        if (root.statusState === "webengine_unavailable"
                && String(root.activePayload.webengine_reason || "").toLowerCase().indexOf("offscreen") >= 0)
            return "Set COREX_ENABLE_OFFSCREEN_WEBENGINE=1 only for an explicit live WebEngine smoke.";
        return "";
    }

    function _webEngineUnavailableText() {
        if (root.webEngineAvailable)
            return "";
        var reason = String(root.activePayload.webengine_reason || "").trim();
        return reason.length > 0
            ? "Qt WebEngine is unavailable: " + reason
            : "Qt WebEngine is unavailable.";
    }

    Timer {
        id: browserStatePersistTimer
        interval: 150
        repeat: false
        onTriggered: root._persistBrowserState()
    }

    Timer {
        id: fitZoomTimer
        interval: 60
        repeat: false
        onTriggered: root._requestFitZoomMetrics()
    }

    Timer {
        id: fitZoomAfterResizeTimer
        interval: 180
        repeat: false
        onTriggered: root._scheduleFitZoom(true, true)
    }

    function _decideNavigation(location) {
        var text = String(location || "").trim();
        if (!text.length)
            return root._navigationDecision(false, text, "", "", "", false, "Web navigation location must not be empty.");
        var target = root._normalizeLocation(text);
        if (!target.ok)
            return root._navigationDecision(false, text, "", "", "", false, target.reason);
        return root._navigationDecision(true, text, target.url, target.scheme, target.origin, target.isLocal, "");
    }

    function _normalizeLocation(location) {
        var text = String(location || "").trim();
        var lower = text.toLowerCase();
        if (lower.indexOf("file://") === 0)
            return {"ok": true, "url": text, "scheme": "file", "origin": "file://", "isLocal": true};
        if (/^[A-Za-z]:[\\/]/.test(text) || text.indexOf("\\\\") === 0 || text.indexOf("/") === 0 || text.indexOf("./") === 0 || text.indexOf("../") === 0)
            return {"ok": true, "url": root._fileUrlFromPath(text), "scheme": "file", "origin": "file://", "isLocal": true};
        if (text.indexOf("://") < 0) {
            if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(text))
                return {"ok": false, "reason": "Unsupported web navigation scheme: " + text.split(":", 1)[0].toLowerCase()};
            text = "https://" + text;
            lower = text.toLowerCase();
        }
        var match = /^(https?):\/\/([^\/?#]+)(.*)$/.exec(text);
        if (!match)
            return {"ok": false, "reason": "Web navigation location must be a URL or filesystem path."};
        var scheme = match[1].toLowerCase();
        var host = match[2].toLowerCase();
        if (!host.length)
            return {"ok": false, "reason": scheme.toUpperCase() + " navigation requires a host."};
        return {"ok": true, "url": scheme + "://" + host + match[3], "scheme": scheme, "origin": scheme + "://" + host, "isLocal": false};
    }

    function _fileUrlFromPath(pathText) {
        var path = String(pathText || "").trim().replace(/\\/g, "/");
        if (!path.length)
            return "";
        if (path.toLowerCase().indexOf("file://") === 0)
            return path;
        if (path.indexOf("//") === 0)
            return "file:" + encodeURI(path);
        if (/^[A-Za-z]:\//.test(path))
            return "file:///" + encodeURI(path);
        if (path.indexOf("/") === 0)
            return "file://" + encodeURI(path);
        return Qt.resolvedUrl(path).toString();
    }

    function _navigationDecision(allowed, original, target, scheme, origin, isLocal, reason) {
        return {
            "allowed": Boolean(allowed),
            "target_url": String(target || ""),
            "reason": String(reason || ""),
            "original_location": String(original || ""),
            "scheme": String(scheme || ""),
            "origin": String(origin || ""),
            "is_local": Boolean(isLocal),
            "qwebchannel_allowed": false
        };
    }

    function _isProjectArtifactRef(location) {
        return /^(saved|temp):\/\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(String(location || "").trim());
    }

    function _resolvedProjectFileUrl(location) {
        var text = String(location || "").trim();
        if (!root._isProjectArtifactRef(text))
            return "";
        var payloadLocation = String(root.activePayload.current_location || "").trim();
        var payloadNavigationLocation = String(root.activePayload.navigation_location || "").trim();
        if (payloadLocation === text && payloadNavigationLocation.length > 0 && payloadNavigationLocation !== text)
            return payloadNavigationLocation;
        var decision = root.activePayload.navigation_decision && typeof root.activePayload.navigation_decision === "object"
            ? root.activePayload.navigation_decision
            : ({});
        var targetUrl = String(decision.target_url || "").trim();
        if (payloadLocation === text && targetUrl.length > 0 && targetUrl !== text)
            return targetUrl;
        if (root.host && root.host.resolveLocalFileSourceUrl)
            return String(root.host.resolveLocalFileSourceUrl(text) || "").trim();
        return "";
    }

    function _navigationLocation(location) {
        var text = String(location || "").trim();
        var resolved = root._resolvedProjectFileUrl(text);
        return resolved.length > 0 ? resolved : text;
    }

    function _browserStateCurrentUrl() {
        var startLocation = String(root.activePayload.start_location || "").trim();
        if (root._isProjectArtifactRef(startLocation)) {
            var resolved = root._navigationLocation(startLocation);
            if (resolved.length > 0 && resolved === root.currentUrl)
                return startLocation;
        }
        return root.currentUrl;
    }

    function _requestNavigationFromPage(url) {
        var decision = root._decideNavigation(url);
        if (!Boolean(decision.allowed)) {
            root.policyDeniedText = String(decision.reason || "Navigation is not allowed.");
            return false;
        }
        root.policyDeniedText = "";
        root.currentUrl = String(decision.target_url || "");
        root.addressText = root.currentUrl;
        return true;
    }

    function _syncWebEngineItem() {
        if (!root.shouldLoadWebEngine) {
            if (!root._parkWebEngineItemForWorkspaceSwitch())
                root._destroyWebEngineItem();
            return;
        }
        if (root.webEngineItem) {
            root.webEngineItem.pageZoom = root.zoomFactor;
            root.webEngineItem.pageBackgroundColor = root._webEngineBackgroundColor();
            if (root.webEngineItem.documentTitle !== undefined)
                root._handleWebEngineTitleChanged(root.webEngineItem.documentTitle);
            if (String(root.webEngineItem.pageUrl || "") !== root.currentUrl)
                root.webEngineItem.pageUrl = root.currentUrl;
            root._scheduleFitZoom(true);
            return;
        }
        if (root._claimRetainedWebEngineItem()) {
            root._syncWebEngineItem();
            return;
        }
        try {
            root.webEngineCreationError = "";
            root.webEngineLoadError = "";
            root.webEngineItem = Qt.createQmlObject(
                root._webEngineComponentQml(),
                webViewport,
                "genericWebPageHostDynamic"
            );
            root._connectWebEngineItemSignals(root.webEngineItem);
            root.webEngineItem.pageZoom = root.zoomFactor;
            root.webEngineItem.pageBackgroundColor = root._webEngineBackgroundColor();
            root._handleWebEngineTitleChanged(root.webEngineItem.documentTitle || "");
            root.webEngineItem.pageUrl = root.currentUrl;
            root._scheduleFitZoom(true);
        } catch (error) {
            root._destroyWebEngineItem();
            root.webEngineCreationError = "Web page could not be loaded: " + String(error);
        }
    }

    function _handleWebEngineDiagnostic(category, message, url) {
        var normalizedCategory = String(category || "webengine");
        var normalizedMessage = String(message || "").trim();
        var normalizedUrl = String(url || "").trim();
        if (!normalizedMessage.length)
            return;
        root.webEngineDiagnosticText = normalizedCategory + ": " + normalizedMessage
            + (normalizedUrl.length ? " [" + normalizedUrl + "]" : "");
        console.warn("WebPageHost " + root.webEngineDiagnosticText);
        if (normalizedCategory === "load" || normalizedCategory === "render_process")
            root.webEngineLoadError = normalizedMessage;
    }

    function _handleWebEnginePageFullscreen(toggleOn, origin) {
        root.webEngineDiagnosticText = Boolean(toggleOn)
            ? "fullscreen: " + String(origin || root.currentUrl || "")
            : "";
        if (Boolean(toggleOn) && root.graphSurface)
            root._requestFullscreen();
    }

    function _destroyWebEngineItem() {
        if (!root.webEngineItem)
            return;
        root._externalWebEngineBorrowMode = "";
        root._externalWebEngineOriginalParent = null;
        root._disconnectWebEngineItemSignals(root.webEngineItem);
        root.webEngineItem.destroy();
        root.webEngineItem = null;
        root.loading = false;
        root.canGoBack = false;
        root.canGoForward = false;
    }

    function _handleWebEngineLoadStatus(status, errorText, url, progress, isLoading) {
        root.loading = Boolean(isLoading);
        root.loadProgress = Math.max(0, Math.min(100, Number(progress || 0)));
        if (String(url || "").length > 0 && String(url) !== "about:blank") {
            if (String(url) !== root.currentUrl)
                root.documentTitle = "";
            root.currentUrl = String(url);
            root.addressText = root.currentUrl;
        }
        root.webEngineLoadError = String(errorText || "");
        if (root.webEngineItem) {
            root.canGoBack = Boolean(root.webEngineItem.pageCanGoBack);
            root.canGoForward = Boolean(root.webEngineItem.pageCanGoForward);
        }
        if (!root.loading)
            root._scheduleFitZoom(true);
    }

    function _webEngineComponentQml() {
        return [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "Item {",
            "    id: webRoot",
            "    objectName: \"webPageHostDynamicRoot\"",
            "    anchors.fill: parent",
            "    property string pageUrl: \"\"",
            "    property real pageZoom: 1.0",
            "    property color pageBackgroundColor: \"#ffffff\"",
            "    property bool navigationAllowed: true",
            "    property bool retainedPaused: false",
            "    readonly property string documentTitle: pageView.title",
            "    readonly property bool pageCanGoBack: pageView.canGoBack",
            "    readonly property bool pageCanGoForward: pageView.canGoForward",
            "    signal loadStatusChanged(int status, string errorText, string url, int progress, bool loading)",
            "    signal documentTitleReported(string title)",
            "    signal navigationRequestedByPage(string url)",
            "    signal webEngineDiagnostic(string category, string message, string url)",
            "    signal pageFullscreenRequested(bool toggleOn, string origin)",
            "    signal contentMetricsReady(real contentWidth, real contentHeight)",
            "    function goBack() { pageView.goBack(); }",
            "    function goForward() { pageView.goForward(); }",
            "    function reload() { pageView.reload(); }",
            "    function stop() { pageView.stop(); }",
            "    function setPageRetained(retained) {",
            "        retainedPaused = Boolean(retained);",
            "        pageView.audioMuted = retainedPaused;",
            "        try {",
            "            pageView.lifecycleState = retainedPaused ? WebEngineView.Frozen : WebEngineView.Active;",
            "        } catch (error) {",
            "        }",
            "    }",
            "    function reportDocumentTitle() { webRoot.documentTitleReported(String(pageView.title || \"\")); }",
            "    function requestContentMetrics() {",
            "        try {",
            "            pageView.runJavaScript(\"(function(){var d=document.documentElement||{};var b=document.body||{};var v=window.visualViewport||{};function n(x){x=Number(x||0);return isFinite(x)?x:0;}return {width:Math.max(n(d.scrollWidth),n(b.scrollWidth),n(d.offsetWidth),n(b.offsetWidth),n(d.clientWidth),n(b.clientWidth),n(window.innerWidth),n(v.width)),height:Math.max(n(d.scrollHeight),n(b.scrollHeight),n(d.offsetHeight),n(b.offsetHeight),n(d.clientHeight),n(b.clientHeight),n(window.innerHeight),n(v.height))};})()\", function(result) {",
            "                var data = result || {};",
            "                webRoot.contentMetricsReady(Number(data.width || 0), Number(data.height || 0));",
            "            });",
            "        } catch (error) {",
            "            webRoot.contentMetricsReady(0, 0);",
            "        }",
            "    }",
            "    onPageZoomChanged: pageView.zoomFactor = pageZoom",
            "    onPageUrlChanged: {",
            "        if (pageUrl.length > 0 && pageView.url.toString() !== pageUrl)",
            "            pageView.url = pageUrl;",
            "    }",
            "    function _chromeLikeUserAgent(defaultUserAgent) {",
            "        var tokens = String(defaultUserAgent || \"\").split(\" \");",
            "        var kept = [];",
            "        for (var index = 0; index < tokens.length; ++index) {",
            "            var token = String(tokens[index] || \"\");",
            "            if (token.length > 0 && token.indexOf(\"QtWebEngine/\") !== 0)",
            "                kept.push(token);",
            "        }",
            "        var normalized = kept.join(\" \").trim();",
            "        if (normalized.indexOf(\"Chrome/\") >= 0 && normalized.indexOf(\"Safari/537.36\") >= 0)",
            "            return normalized;",
            "        return \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36\";",
            "    }",
            "    function _chromeVersionFromUserAgent(userAgent) {",
            "        var match = /Chrome\\/([0-9.]+)/.exec(String(userAgent || \"\"));",
            "        return match && match.length > 1 ? String(match[1]) : \"140.0.0.0\";",
            "    }",
            "    function _applyChromeLikeClientHints(profile) {",
            "        if (!profile || !profile.clientHints)",
            "            return;",
            "        var version = webRoot._chromeVersionFromUserAgent(profile.httpUserAgent);",
            "        profile.clientHints.isAllClientHintsEnabled = true;",
            "        profile.clientHints.platform = \"Windows\";",
            "        profile.clientHints.arch = \"x86\";",
            "        profile.clientHints.bitness = \"64\";",
            "        profile.clientHints.mobile = false;",
            "        profile.clientHints.model = \"\";",
            "        profile.clientHints.fullVersion = version;",
            "        profile.clientHints.fullVersionList = {",
            "            \"Google Chrome\": version,",
            "            \"Chromium\": version,",
            "            \"Not=A?Brand\": \"24.0.0.0\"",
            "        };",
            "    }",
            "    WebEngineProfile {",
            "        id: pageViewerProfile",
            "        objectName: \"webPageHostWebEngineProfile\"",
            "        storageName: \"corex_web_page_viewer\"",
            "        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies",
            "        Component.onCompleted: {",
            "            httpUserAgent = webRoot._chromeLikeUserAgent(httpUserAgent);",
            "            webRoot._applyChromeLikeClientHints(pageViewerProfile);",
            "        }",
            "    }",
            "    WebEngineView {",
            "        id: pageView",
            "        objectName: \"webPageHostWebEngineView\"",
            "        anchors.fill: parent",
            "        profile: pageViewerProfile",
            "        url: \"about:blank\"",
            "        backgroundColor: webRoot.pageBackgroundColor",
            "        zoomFactor: webRoot.pageZoom",
            "        settings.fullScreenSupportEnabled: true",
            "        settings.playbackRequiresUserGesture: false",
            "        settings.localStorageEnabled: true",
            "        settings.webGLEnabled: true",
            "        onFullScreenRequested: function(request) {",
            "            webRoot.pageFullscreenRequested(Boolean(request.toggleOn), String(request.origin || \"\"));",
            "            request.accept();",
            "        }",
            "        onNewWindowRequested: function(request) {",
            "            request.openIn(pageView);",
            "        }",
            "        onPermissionRequested: function(permission) {",
            "            webRoot.webEngineDiagnostic(\"permission\", \"Denied \" + String(permission.permissionType || \"permission\") + \" request\", String(permission.origin || pageView.url || \"\"));",
            "            permission.deny();",
            "        }",
            "        onNavigationRequested: function(request) {",
            "            if (!request.isMainFrame) {",
            "                request.action = WebEngineNavigationRequest.AcceptRequest;",
            "                return;",
            "            }",
            "            webRoot.navigationAllowed = true;",
            "            webRoot.navigationRequestedByPage(String(request.url || \"\"));",
            "            request.action = webRoot.navigationAllowed",
            "                ? WebEngineNavigationRequest.AcceptRequest",
            "                : WebEngineNavigationRequest.IgnoreRequest;",
            "        }",
            "        onLoadingChanged: function(loadRequest) {",
            "            webRoot.loadStatusChanged(",
            "                Number(loadRequest.status || 0),",
            "                String(loadRequest.errorString || \"\"),",
            "                String(loadRequest.url || pageView.url || \"\"),",
            "                Number(pageView.loadProgress || 0),",
            "                Boolean(pageView.loading)",
            "            );",
            "            webRoot.reportDocumentTitle();",
            "            if (String(loadRequest.errorString || \"\").length > 0)",
            "                webRoot.webEngineDiagnostic(\"load\", String(loadRequest.errorString || \"\"), String(loadRequest.url || pageView.url || \"\"));",
            "        }",
            "        onLoadProgressChanged: {",
            "            webRoot.loadStatusChanged(0, \"\", String(pageView.url || \"\"), Number(loadProgress || 0), Boolean(pageView.loading));",
            "            webRoot.reportDocumentTitle();",
            "        }",
            "        onTitleChanged: webRoot.reportDocumentTitle()",
            "        onUrlChanged: {",
            "            var nextUrl = pageView.url.toString();",
            "            if (nextUrl.length > 0)",
            "                webRoot.loadStatusChanged(0, \"\", nextUrl, Number(pageView.loadProgress || 0), Boolean(pageView.loading));",
            "            webRoot.reportDocumentTitle();",
            "        }",
            "        onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {",
            "            webRoot.webEngineDiagnostic(\"console\", String(message || \"\") + \" (line \" + Number(lineNumber || 0) + \")\", String(sourceID || pageView.url || \"\"));",
            "        }",
            "        onRenderProcessTerminated: function(terminationStatus, exitCode) {",
            "            webRoot.webEngineDiagnostic(\"render_process\", \"Render process terminated: \" + String(terminationStatus) + \" (exit \" + Number(exitCode || 0) + \")\", String(pageView.url || \"\"));",
            "        }",
            "    }",
            "}"
        ].join("\n");
    }

    Component {
        id: toolbarComponent

        WebPageToolbar {
            objectName: "webPageToolbar"
            themePalette: root.effectiveThemePalette
            compact: root.graphSurface
            detachedVisible: root.surfaceMode !== "detached"
            addressText: root.addressText
            loading: root.loading
            canGoBack: root.canGoBack
            canGoForward: root.canGoForward
            zoomPercent: Math.round(root.zoomFactor * 100)
            onNavigateRequested: root.navigateTo(location)
            onBackRequested: root.goBack()
            onForwardRequested: root.goForward()
            onReloadStopRequested: root.reloadOrStop()
            onHomeRequested: root.goHome()
            onZoomInRequested: root.zoomIn()
            onZoomOutRequested: root.zoomOut()
            onZoomResetRequested: root.zoomReset()
            onFullscreenRequested: root._requestFullscreen()
            onDetachedRequested: root._requestDetached()
        }
    }

    Rectangle {
        visible: !root.graphSurface || root.chromeFrameVisible
        anchors.fill: parent
        radius: 6
        color: root.effectiveThemePalette.panel_bg || "#1f2431"
        border.width: 1
        border.color: root.effectiveThemePalette.border || "#3a4355"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.contentMargin
        spacing: root.contentMargin > 0 ? 8 : 0

        Loader {
            id: toolbarLoader
            objectName: "webPageToolbarLoader"
            Layout.fillWidth: true
            Layout.preferredHeight: active && item ? item.implicitHeight : 0
            active: !root.graphSurface
            visible: active
            sourceComponent: root.graphSurface ? null : toolbarComponent
        }

        Rectangle {
            id: viewportFrame
            objectName: "webPageViewportFrame"
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 6
            color: root.effectiveThemePalette.input_bg || "#151821"
            border.width: 1
            border.color: root.effectiveThemePalette.input_border || root.effectiveThemePalette.border || "#3a4355"
            clip: true

            Item {
                id: webViewport
                objectName: "webPageViewport"
                anchors.fill: parent
                anchors.margins: 1
                visible: root.shouldLoadWebEngine
                onWidthChanged: root._scheduleFitZoom(true, true)
                onHeightChanged: root._scheduleFitZoom(true, true)
            }

            WebPageStatusPane {
                id: statusPane
                objectName: root.graphSurface ? "graphNodeWebPageStatusPane" : "contentFullscreenWebPageStatusPane"
                anchors.fill: parent
                visible: root.statusVisible
                themePalette: root.effectiveThemePalette
                state: root.statusState
                title: root._statusTitle()
                message: root._statusMessage()
                detail: root._statusDetail()
                actionText: root._statusActionText()
            }

            Image {
                id: canvasExportPreviewImage
                objectName: "webPageCanvasExportPreviewImage"
                anchors.fill: parent
                anchors.margins: 1
                visible: root.canvasExportFallbackActive && root.previewImageSource.length > 0
                source: visible ? root.previewImageSource : ""
                fillMode: Image.PreserveAspectFit
                smooth: true
                asynchronous: false
                cache: false
            }
        }

        Text {
            id: documentTitleLabel
            objectName: "webPageDocumentTitleLabel"
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? implicitHeight : 0
            visible: root.documentTitle.length > 0
            text: root.documentTitle
            color: root.effectiveThemePalette.muted_fg || root.effectiveThemePalette.panel_fg || "#95a0b8"
            opacity: root.graphSurface ? 0.56 : 0.62
            font.pixelSize: root.graphSurface ? 12 : 13
            elide: Text.ElideRight
            maximumLineCount: 1
            wrapMode: Text.NoWrap
            verticalAlignment: Text.AlignVCenter
        }
    }

}
