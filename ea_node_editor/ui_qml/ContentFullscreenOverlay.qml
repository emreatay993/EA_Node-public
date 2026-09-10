import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Pdf 6.0
import "components/shell"
import "components/web" as WebComponents
import "components/graph/tabular" as TabularComponents
import "components/graph/viewer" as ViewerComponents
import "components/graph/passive" as PassiveComponents
import "components/graph/passive/GraphMediaPanelGeometry.js" as GraphMediaPanelGeometry
import "components/common/TooltipCopy.js" as TooltipCopy

FocusScope {
    id: root
    objectName: "contentFullscreenOverlay"
    property var bridgeRef: null
    property var scriptEditorBridgeRef: null
    property var scriptHighlighterBridgeRef: null
    readonly property var themePalette: themeBridge.palette
    readonly property bool bridgeOpen: !!root.bridgeRef && Boolean(root.bridgeRef.open)
    readonly property string activeNodeId: root.bridgeRef ? String(root.bridgeRef.node_id || "") : ""
    readonly property string contentKind: root.bridgeRef ? String(root.bridgeRef.content_kind || "") : ""
    property bool scriptGuideVisible: false
    readonly property string titleText: root.bridgeRef ? String(root.bridgeRef.title || "") : ""
    readonly property var mediaPayload: root.bridgeRef && root.bridgeRef.media_payload ? root.bridgeRef.media_payload : ({})
    readonly property var viewerPayload: root.bridgeRef && root.bridgeRef.viewer_payload ? root.bridgeRef.viewer_payload : ({})
    readonly property var webEditorPayload: root.bridgeRef && root.bridgeRef.web_editor_payload ? root.bridgeRef.web_editor_payload : ({})
    readonly property var webPagePayload: root.bridgeRef && root.bridgeRef.web_page_payload ? root.bridgeRef.web_page_payload : ({})
    readonly property var plotPayload: root.bridgeRef && root.bridgeRef.plot_payload ? root.bridgeRef.plot_payload : ({})
    readonly property var plotOptions: root._plotOptions()
    readonly property bool plotHoverReadout: root._plotOptionBool("hover_readout", false)
    readonly property bool plotVerticalGuide: root._plotOptionBool("vertical_guide", false)
    readonly property bool plotCrosshair: root._plotOptionBool("crosshair", false)
    readonly property string plotThemeOption: root._plotThemeOption()
    readonly property var viewerSessionBridgeRef: typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge : null
    readonly property var viewerControlBridgeRef: typeof viewerControlBridge !== "undefined" ? viewerControlBridge : null
    readonly property var viewerHostServiceRef: typeof viewerHostService !== "undefined" ? viewerHostService : null
    readonly property var graphCanvasCommandBridgeRef: typeof graphCanvasCommandBridge !== "undefined" ? graphCanvasCommandBridge : null
    readonly property var viewerLiveSessionState: {
        if (!root.viewerSessionBridgeRef
                || root.contentKind !== "viewer"
                || root.activeNodeId.length === 0)
            return ({});
        var projectionSeed = root.viewerSessionBridgeRef.sessions_model;
        void(projectionSeed);
        if (!root.viewerSessionBridgeRef.session_state)
            return ({});
        return root.viewerSessionBridgeRef.session_state(root.activeNodeId);
    }
    readonly property var tabularPayload: root.bridgeRef && root.bridgeRef.tabular_payload ? root.bridgeRef.tabular_payload : ({})
    readonly property var surfaceSpec: _activeSurfaceSpec()
    readonly property var inputCapabilities: surfaceSpec && surfaceSpec.input_capabilities
        ? surfaceSpec.input_capabilities
        : ({})
    readonly property var webSurfaceBridge: root.bridgeRef && root.bridgeRef.web_surface_bridge ? root.bridgeRef.web_surface_bridge : null
    readonly property bool mediaContentActive: root.contentKind === "media"
    readonly property string mediaState: root.mediaContentActive
        ? String(root.mediaPayload.source_state || "invalid")
        : ""
    readonly property bool mediaReady: root.bridgeOpen
        && root.mediaContentActive
        && root.mediaState === "ready"
    readonly property string mediaKind: root.mediaContentActive
        ? String(root.mediaPayload.media_kind || "")
        : ""
    readonly property bool mediaImageActive: root.mediaReady && root.mediaKind === "image"
    readonly property bool mediaPdfActive: root.mediaReady && root.mediaKind === "pdf"
    readonly property bool mediaVideoActive: root.mediaReady && root.mediaKind === "video"
    readonly property string mediaStateMessage: String(
        root.mediaPayload.source_message
        || root.mediaPayload.preview_message
        || "Media preview is unavailable."
    )
    readonly property string previewSourceUrl: String(root.mediaPayload.preview_url || "")
    readonly property string pdfSourceUrl: root.mediaPdfActive
        ? String(root.mediaPayload.resolved_source_url || "")
        : ""
    readonly property string imageResolvedSourceUrl: root.mediaImageActive
        ? String(root.mediaPayload.resolved_source_url || "")
        : ""
    readonly property bool mediaImageAnimationSupported: root.mediaImageActive
        && Boolean(root.mediaPayload.is_animated)
        && Boolean(root.mediaPayload.animation_supported)
    readonly property var mediaAnimatedImageItem: mediaAnimatedImageLoader.item
    readonly property string mailPreviewMessage: String(root.mediaPayload.preview_message
        || (root.mediaPayload.mail_preview ? root.mediaPayload.mail_preview.message : "")
        || "Mail preview is unavailable.")
    readonly property string mailAttachmentSummary: String(root.mediaPayload.attachment_summary || "No attachments")
    readonly property string mailZoomLabel: Math.round(root.mailZoomFactor * 100) + "%"
    readonly property int sourcePixelWidth: Math.max(0, Number(root.mediaPayload.source_pixel_width || 0))
    readonly property int sourcePixelHeight: Math.max(0, Number(root.mediaPayload.source_pixel_height || 0))
    readonly property var pdfDocumentHandle: pdfViewerLoader.item ? pdfViewerLoader.item.pdfDocument : null
    readonly property var pdfMultiPageViewHandle: pdfViewerLoader.item ? pdfViewerLoader.item.pdfMultiPageView : null
    readonly property bool pdfDocumentReady: !!root.pdfDocumentHandle
        && root.pdfDocumentHandle.status === PdfDocument.Ready
    readonly property bool pdfDocumentLoading: !!root.pdfDocumentHandle
        && root.pdfDocumentHandle.status === PdfDocument.Loading
    readonly property bool pdfViewVisible: !!root.pdfMultiPageViewHandle
        && Boolean(root.pdfMultiPageViewHandle.visible)
    readonly property real pdfRenderScale: root.pdfMultiPageViewHandle
        ? root._clampPdfRenderScale(Number(root.pdfMultiPageViewHandle.renderScale || 1.0))
        : 1.0
    readonly property string pdfZoomLabel: Math.round(root.pdfRenderScale * 100) + "%"
    readonly property int pdfPayloadPageCount: root._intValue(
        root.mediaPayload.page_count || (root.mediaPayload.pdf_preview ? root.mediaPayload.pdf_preview.page_count : 0),
        0
    )
    readonly property int pdfPageCount: root.mediaKind === "pdf" && root.pdfDocumentReady
        ? Math.max(0, Number(root.pdfDocumentHandle.pageCount || 0))
        : root.pdfPayloadPageCount
    readonly property int pdfResolvedPageNumber: root._intValue(
        root.mediaPayload.resolved_page_number || (
            root.mediaPayload.pdf_preview ? root.mediaPayload.pdf_preview.resolved_page_number : root.mediaPayload.page_number
        ),
        1
    )
    readonly property int pdfCurrentPageNumber: {
        if (root.mediaKind === "pdf"
                && root.pdfMultiPageViewHandle
                && Number(root.pdfMultiPageViewHandle.currentPage) >= 0)
            return root._boundedPdfPage(Number(root.pdfMultiPageViewHandle.currentPage) + 1);
        return root._boundedPdfPage(root.pdfResolvedPageNumber);
    }
    readonly property int pdfSearchResultCount: root._pdfSearchResultCount()
    readonly property string pdfSearchStatusText: root._pdfSearchStatusText()
    readonly property var mediaCrop: root._normalizedMediaCrop()
    readonly property rect mediaImageSourceClipRect: root._sourceClipRect()
    readonly property int mediaImageRotationDegrees: root._normalizedImageRotationDegrees(root.mediaPayload.rotation_degrees)
    readonly property bool mediaImageMirrorHorizontal: root._boolValue(root.mediaPayload.mirror_horizontal, false)
    readonly property bool mediaImageMirrorVertical: root._boolValue(root.mediaPayload.mirror_vertical, false)
    readonly property bool mediaImageRotationSwapsAxes: (Math.floor(mediaImageRotationDegrees / 90) % 2) !== 0
    readonly property real mediaImageSourceClipWidth: Math.max(0, Number(root.mediaImageSourceClipRect.width || 0))
    readonly property real mediaImageSourceClipHeight: Math.max(0, Number(root.mediaImageSourceClipRect.height || 0))
    readonly property real mediaImageTransformedSourceWidth: root.mediaImageRotationSwapsAxes
        ? root.mediaImageSourceClipHeight
        : root.mediaImageSourceClipWidth
    readonly property real mediaImageTransformedSourceHeight: root.mediaImageRotationSwapsAxes
        ? root.mediaImageSourceClipWidth
        : root.mediaImageSourceClipHeight
    readonly property var mediaImageDisplayRect: root._mediaImageDisplayRect(
        mediaViewport ? mediaViewport.width : 0,
        mediaViewport ? mediaViewport.height : 0
    )
    readonly property real mediaImageDisplayScale: {
        if (!(root.mediaImageTransformedSourceWidth > 0) || !(root.mediaImageTransformedSourceHeight > 0))
            return 0.0;
        if (root.effectiveDisplayMode === "actual")
            return 1.0;
        return Number(root.mediaImageDisplayRect.width || 0) / root.mediaImageTransformedSourceWidth;
    }
    readonly property real mediaImageCropFrameWidth: root.mediaImageSourceClipWidth * root.mediaImageDisplayScale
    readonly property real mediaImageCropFrameHeight: root.mediaImageSourceClipHeight * root.mediaImageDisplayScale
    readonly property real mediaImageFullFrameWidth: root.sourcePixelWidth > 0
        ? root.sourcePixelWidth * root.mediaImageDisplayScale
        : 0
    readonly property real mediaImageFullFrameHeight: root.sourcePixelHeight > 0
        ? root.sourcePixelHeight * root.mediaImageDisplayScale
        : 0
    readonly property real mediaImageOffsetX: -Number(root.mediaCrop.x || 0) * root.mediaImageFullFrameWidth
    readonly property real mediaImageOffsetY: -Number(root.mediaCrop.y || 0) * root.mediaImageFullFrameHeight
    readonly property string payloadFitMode: root._normalizedPayloadFitMode()
    readonly property string effectiveDisplayMode: root.localDisplayMode.length > 0
        ? root.localDisplayMode
        : root._displayModeFromPayload()
    property string localDisplayMode: ""
    property bool webEditorClosePending: false
    property bool pdfViewerReleased: false
    property bool pdfSearchOpen: false
    property string pdfSearchText: ""
    property string pdfFitMode: "custom"
    property bool pdfApplyingFitMode: false
    property var mailWebEngineView: null
    property string mailWebEngineDiagnostic: ""
    property real mailZoomFactor: 1.0
    property string mailFitMode: "actual"
    property var borrowedWebPageHost: null
    property bool webPageBorrowedActive: false
    property bool webPageBorrowSyncPending: true

    visible: root.bridgeOpen
    enabled: visible
    focus: visible
    activeFocusOnTab: visible
    z: 2000

    onVisibleChanged: {
        if (visible) {
            root._scheduleBorrowedWebPageHostSync();
            Qt.callLater(function() {
                if (root.visible)
                    root.forceActiveFocus();
            });
        } else {
            root._releaseBorrowedWebPageHost();
            root._destroyMailWebEngineView();
            root._resetMailReaderControls();
            root.webPageBorrowSyncPending = false;
            root.localDisplayMode = "";
            root.webEditorClosePending = false;
            root._resetPdfReaderControls();
            webEditorCloseTimeout.stop();
        }
    }

    onActiveNodeIdChanged: {
        root._releaseBorrowedWebPageHost();
        root._destroyMailWebEngineView();
        root._resetMailReaderControls();
        root.localDisplayMode = "";
        root._resetPdfReaderControls();
        root._scheduleBorrowedWebPageHostSync();
        root._syncMailWebEnginePreview();
    }
    onContentKindChanged: {
        root._releaseBorrowedWebPageHost();
        root._destroyMailWebEngineView();
        root._resetMailReaderControls();
        root._scheduleBorrowedWebPageHostSync();
        root._syncMailWebEnginePreview();
    }
    onBridgeOpenChanged: {
        root.pdfViewerReleased = false;
        if (!root.bridgeOpen) {
            root._releaseBorrowedWebPageHost();
            root._destroyMailWebEngineView();
            root._resetMailReaderControls();
            root.webPageBorrowSyncPending = false;
            root.webEditorClosePending = false;
            root._resetPdfReaderControls();
            webEditorCloseTimeout.stop();
        } else {
            root._scheduleBorrowedWebPageHostSync();
            root._syncMailWebEnginePreview();
        }
        root._syncPdfDocumentSource();
    }

    onPreviewSourceUrlChanged: root._syncMailWebEnginePreview()
    onMailZoomFactorChanged: root._syncMailWebEngineZoom()

    Component.onCompleted: {
        root._scheduleBorrowedWebPageHostSync();
        root._syncMailWebEnginePreview();
    }

    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
        if (root.mediaPdfActive) {
            if (event.key === Qt.Key_Escape
                    && root.pdfSearchOpen
                    && pdfSearchField
                    && pdfSearchField.activeFocus) {
                root._closePdfSearch();
                event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_F && root._controlOnlyKeyEvent(event)) {
                root._openPdfSearch();
                event.accepted = true;
                return;
            }
            if ((event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
                    && root._controlKeyEvent(event)) {
                if (root._requestPdfZoom(1.15))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Minus && root._controlOnlyKeyEvent(event)) {
                if (root._requestPdfZoom(1 / 1.15))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_0 && root._controlOnlyKeyEvent(event)) {
                if (root._applyPdfFitMode("actual", true))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_R
                    && (root._plainKeyEvent(event) || root._shiftOnlyKeyEvent(event))
                    && !root._pdfTextFieldFocused()) {
                if (root._rotatePdfPages((event.modifiers & Qt.ShiftModifier) !== 0 ? -90 : 90))
                    event.accepted = true;
                return;
            }
            if (!root._pdfTextFieldFocused() && root._plainKeyEvent(event)) {
                if (event.key === Qt.Key_Left || event.key === Qt.Key_PageUp) {
                    if (root._requestPdfPageDelta(-1))
                        event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_Right || event.key === Qt.Key_PageDown) {
                    if (root._requestPdfPageDelta(1))
                        event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_Home) {
                    if (root._requestPdfPageNumber(1))
                        event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_End) {
                    if (root._requestPdfPageNumber(root.pdfPageCount))
                        event.accepted = true;
                    return;
                }
            }
        }
        if (root.contentKind === "mail") {
            if ((event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
                    && root._controlKeyEvent(event)) {
                if (root._requestMailZoom(1.15))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Minus && root._controlOnlyKeyEvent(event)) {
                if (root._requestMailZoom(1 / 1.15))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_0 && root._controlOnlyKeyEvent(event)) {
                if (root._applyMailFitMode("actual", true))
                    event.accepted = true;
                return;
            }
        }
        if (root.contentKind === "viewer" && root._plainKeyEvent(event)) {
            if (event.key === Qt.Key_Space) {
                if (viewerQuickControls.togglePlayback())
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Left) {
                if (viewerQuickControls.stepBack())
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Right) {
                if (viewerQuickControls.stepForward())
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Home) {
                if (viewerQuickControls.cameraFit())
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_R) {
                if (viewerQuickControls.applyStandardView("iso"))
                    event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_PageUp || event.key === Qt.Key_PageDown) {
                if (viewerQuickControls.cycleSavedView(event.key === Qt.Key_PageUp ? -1 : 1))
                    event.accepted = true;
                return;
            }
        }
        if (event.key === Qt.Key_Escape || event.key === Qt.Key_F11) {
            root.requestClose();
            event.accepted = true;
            return;
        }
    }

    onMediaKindChanged: {
        root.pdfViewerReleased = false;
        root._resetPdfReaderControls();
        root._syncPdfDocumentSource();
    }
    onMediaStateChanged: {
        root.pdfViewerReleased = !root.mediaReady;
        root._resetPdfReaderControls();
        root._syncPdfDocumentSource();
    }
    onPdfSourceUrlChanged: {
        _resetPdfReaderControls();
        _syncPdfDocumentSource();
        Qt.callLater(function() { root._syncPdfViewToResolvedPage(); });
    }
    onPdfResolvedPageNumberChanged: {
        _syncPdfPageField(false);
        _syncPdfViewToResolvedPage();
    }
    onPdfPageCountChanged: {
        _syncPdfPageField(false);
        _syncPdfViewToResolvedPage();
    }
    onPdfCurrentPageNumberChanged: _syncPdfPageField(false)

    function requestClose() {
        if (!root.bridgeRef)
            return;
        if (root.contentKind === "web_editor") {
            root._requestWebEditorClose();
            return;
        }
        if (root._usesBorrowedWebEngine()) {
            var activeWebPageHost = root._activeWebPageHost();
            if (root.contentKind === "web_page" && activeWebPageHost && activeWebPageHost.flushBrowserState)
                activeWebPageHost.flushBrowserState();
            root._releaseBorrowedWebPageHost();
        }
        if (root.mediaVideoActive
                && videoFullscreenLoader.item
                && videoFullscreenLoader.item.requestCloseWithState) {
            videoFullscreenLoader.item.requestCloseWithState();
            return;
        }
        if (root.mediaPdfActive)
            root._releasePdfViewer();
        if (root.bridgeRef.request_close)
            root.bridgeRef.request_close();
    }

    function _activeWebPageHost() {
        if (root.webPageBorrowedActive && root.borrowedWebPageHost)
            return root.borrowedWebPageHost;
        return webPageHost;
    }

    function _liveWebPageHost() {
        if (!root.activeNodeId.length)
            return null;
        var searchRoot = root._topLevelItem();
        if (!searchRoot)
            return null;
        return root._findLiveWebPageHost(searchRoot, root.activeNodeId, 0);
    }

    function _topLevelItem() {
        var item = root;
        while (item && item.parent)
            item = item.parent;
        return item;
    }

    function _findLiveWebPageHost(item, nodeId, depth) {
        if (!item || depth > 80)
            return null;
        var itemNodeId = "";
        try {
            itemNodeId = String(item.nodeId || "").trim();
        } catch (error) {
            itemNodeId = "";
        }
        var objectName = String(item.objectName || "");
        if ((objectName === "graphNodeWebPageHost" || objectName === "graphJupyterNotebookSurface")
                && itemNodeId === String(nodeId || "").trim()
                && item.hasBorrowableWebEngineForFullscreen)
            return item;
        var children = item.children || [];
        for (var index = 0; index < children.length; ++index) {
            var result = root._findLiveWebPageHost(children[index], nodeId, depth + 1);
            if (result)
                return result;
        }
        return null;
    }

    function _usesBorrowedWebEngine() {
        return root.contentKind === "web_page" || root.contentKind === "jupyter_notebook";
    }

    function _scheduleBorrowedWebPageHostSync() {
        if (root.visible && root._usesBorrowedWebEngine() && !root.webPageBorrowedActive)
            root.webPageBorrowSyncPending = true;
        Qt.callLater(root._syncBorrowedWebPageHost);
    }

    function _syncBorrowedWebPageHost() {
        if (!root.visible || !root._usesBorrowedWebEngine()) {
            root.webPageBorrowSyncPending = false;
            root._releaseBorrowedWebPageHost();
            return;
        }
        var candidate = root._liveWebPageHost();
        if (root.webPageBorrowedActive && root.borrowedWebPageHost === candidate) {
            root.webPageBorrowSyncPending = false;
            return;
        }
        root._releaseBorrowedWebPageHost();
        if (candidate && candidate.attachWebEngineToFullscreen
                && candidate.attachWebEngineToFullscreen(webPageBorrowedViewport, root.activeNodeId)) {
            root.borrowedWebPageHost = candidate;
            root.webPageBorrowedActive = true;
            root.webPageBorrowSyncPending = false;
            return;
        }
        root.webPageBorrowSyncPending = false;
    }

    function _releaseBorrowedWebPageHost() {
        var host = root.borrowedWebPageHost;
        var wasActive = root.webPageBorrowedActive;
        root.borrowedWebPageHost = null;
        root.webPageBorrowedActive = false;
        if (!wasActive || !host || !host.releaseFullscreenWebEngine)
            return false;
        return Boolean(host.releaseFullscreenWebEngine());
    }

    function _requestWebEditorClose() {
        if (root.webEditorClosePending)
            return;
        root.webEditorClosePending = true;
        webEditorCloseTimeout.restart();
        if (!webEditorHost.requestClosePreviewExport())
            root._finishWebEditorClose({"ok": false, "error": "Preview export is unavailable."});
    }

    function _finishWebEditorClose(previewResult) {
        if (!root.webEditorClosePending && root.bridgeOpen)
            return;
        root.webEditorClosePending = false;
        webEditorCloseTimeout.stop();
        if (root.bridgeRef && root.bridgeRef.finish_web_editor_close) {
            root.bridgeRef.finish_web_editor_close(previewResult || ({}));
            return;
        }
        if (root.bridgeRef && root.bridgeRef.request_close)
            root.bridgeRef.request_close();
    }

    function _normalizedPayloadFitMode() {
        var value = String(root.mediaPayload.fit_mode || "contain").trim().toLowerCase();
        if (value === "cover" || value === "original")
            return value;
        return "contain";
    }

    function _intValue(value, defaultValue) {
        var numeric = Number(value);
        return isFinite(numeric) ? Math.floor(numeric) : Number(defaultValue || 0);
    }

    function _boolValue(value, defaultValue) {
        if (value === undefined || value === null)
            return Boolean(defaultValue);
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

    function _plotOptions() {
        var properties = root.plotPayload.properties || ({});
        return properties.plot_options || ({});
    }

    function _plotOptionBool(key, defaultValue) {
        return root._boolValue(root.plotOptions[key], defaultValue);
    }

    function _plotThemeOption() {
        var normalized = String(root.plotOptions.plot_theme || "system").trim().toLowerCase();
        if (normalized === "auto")
            normalized = "system";
        if (normalized === "dark" || normalized === "light" || normalized === "system")
            return normalized;
        return "system";
    }

    function _setPlotOption(key, value) {
        if (root.bridgeRef && root.bridgeRef.set_active_plot_option)
            return root.bridgeRef.set_active_plot_option(key, value);
        return false;
    }

    function _normalizedImageRotationDegrees(value) {
        var degrees = Number(value);
        if (!isFinite(degrees))
            return 0;
        degrees = Math.round(degrees);
        degrees = ((degrees % 360) + 360) % 360;
        return degrees % 90 === 0 ? degrees : 0;
    }

    function _mediaImageDisplayRect(containerWidth, containerHeight) {
        var fitMode = "contain";
        if (root.effectiveDisplayMode === "fill")
            fitMode = "cover";
        else if (root.effectiveDisplayMode === "actual")
            fitMode = "original";
        return GraphMediaPanelGeometry.fitRect(
            containerWidth,
            containerHeight,
            root.mediaImageTransformedSourceWidth,
            root.mediaImageTransformedSourceHeight,
            fitMode
        );
    }

    function _plainKeyEvent(eventObj) {
        if (!eventObj)
            return false;
        return (eventObj.modifiers & (
            Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier
        )) === 0;
    }

    function _controlKeyEvent(eventObj) {
        if (!eventObj)
            return false;
        return (eventObj.modifiers & Qt.ControlModifier) !== 0
            && (eventObj.modifiers & (Qt.AltModifier | Qt.MetaModifier)) === 0;
    }

    function _controlOnlyKeyEvent(eventObj) {
        if (!root._controlKeyEvent(eventObj))
            return false;
        return (eventObj.modifiers & Qt.ShiftModifier) === 0;
    }

    function _shiftOnlyKeyEvent(eventObj) {
        if (!eventObj)
            return false;
        return (eventObj.modifiers & Qt.ShiftModifier) !== 0
            && (eventObj.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) === 0;
    }

    function _pdfTextFieldFocused() {
        return (pdfPageField && pdfPageField.activeFocus)
            || (pdfSearchField && pdfSearchField.activeFocus);
    }

    function _resetPdfReaderControls() {
        root.pdfSearchOpen = false;
        root.pdfSearchText = "";
        root.pdfFitMode = "custom";
        root.pdfApplyingFitMode = false;
    }

    function _pdfReaderReady() {
        return root.mediaPdfActive
            && root.pdfDocumentReady
            && !!root.pdfMultiPageViewHandle;
    }

    function _clampPdfRenderScale(value) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = 1.0;
        if (numeric < 0.1)
            numeric = 0.1;
        if (numeric > 10.0)
            numeric = 10.0;
        return numeric;
    }

    function _setPdfRenderScale(value) {
        if (!root._pdfReaderReady())
            return false;
        root.pdfMultiPageViewHandle.renderScale = root._clampPdfRenderScale(value);
        root.pdfFitMode = "custom";
        return true;
    }

    function _requestPdfZoom(factor) {
        if (!root._pdfReaderReady())
            return false;
        var normalizedFactor = Number(factor);
        if (!isFinite(normalizedFactor) || normalizedFactor <= 0)
            return false;
        return root._setPdfRenderScale(root.pdfRenderScale * normalizedFactor);
    }

    function _pdfViewportWidth() {
        if (root.pdfMultiPageViewHandle && Number(root.pdfMultiPageViewHandle.width) > 0)
            return Math.max(1, Number(root.pdfMultiPageViewHandle.width));
        if (pdfViewerLoader && Number(pdfViewerLoader.width) > 0)
            return Math.max(1, Number(pdfViewerLoader.width));
        return 1;
    }

    function _pdfViewportHeight() {
        if (root.pdfMultiPageViewHandle && Number(root.pdfMultiPageViewHandle.height) > 0)
            return Math.max(1, Number(root.pdfMultiPageViewHandle.height));
        if (pdfViewerLoader && Number(pdfViewerLoader.height) > 0)
            return Math.max(1, Number(pdfViewerLoader.height));
        return 1;
    }

    function _applyPdfFitMode(mode, remember) {
        if (!root._pdfReaderReady())
            return false;
        var normalizedMode = String(mode || "custom").trim().toLowerCase();
        var shouldRemember = remember === undefined ? true : Boolean(remember);
        root.pdfApplyingFitMode = true;
        try {
            if (normalizedMode === "page") {
                root.pdfMultiPageViewHandle.scaleToPage(root._pdfViewportWidth(), root._pdfViewportHeight());
            } else if (normalizedMode === "width") {
                root.pdfMultiPageViewHandle.scaleToWidth(root._pdfViewportWidth(), root._pdfViewportHeight());
            } else if (normalizedMode === "actual") {
                root.pdfMultiPageViewHandle.resetScale();
            } else {
                normalizedMode = "custom";
            }
            root.pdfMultiPageViewHandle.renderScale = root._clampPdfRenderScale(root.pdfMultiPageViewHandle.renderScale);
        } finally {
            root.pdfApplyingFitMode = false;
        }
        if (shouldRemember || normalizedMode !== "custom")
            root.pdfFitMode = normalizedMode;
        return true;
    }

    function _schedulePdfFitRefresh() {
        if (root.pdfFitMode !== "page" && root.pdfFitMode !== "width")
            return;
        Qt.callLater(function() {
            if (root.pdfFitMode === "page" || root.pdfFitMode === "width")
                root._applyPdfFitMode(root.pdfFitMode, false);
        });
    }

    function _rotatePdfPages(deltaDegrees) {
        if (!root._pdfReaderReady())
            return false;
        var currentRotation = Number(root.pdfMultiPageViewHandle.pageRotation || 0);
        var nextRotation = (currentRotation + Number(deltaDegrees || 0)) % 360;
        if (nextRotation < 0)
            nextRotation += 360;
        root.pdfMultiPageViewHandle.pageRotation = nextRotation;
        root._schedulePdfFitRefresh();
        return true;
    }

    function _openPdfSearch() {
        if (!root.mediaPdfActive)
            return false;
        root.pdfSearchOpen = true;
        Qt.callLater(function() {
            if (root.visible && pdfSearchField) {
                pdfSearchField.forceActiveFocus();
                pdfSearchField.selectAll();
            }
        });
        return true;
    }

    function _closePdfSearch() {
        root.pdfSearchOpen = false;
        Qt.callLater(function() {
            if (root.visible)
                root.forceActiveFocus();
        });
        return true;
    }

    function _clearPdfSearch() {
        root.pdfSearchText = "";
        root.pdfSearchOpen = false;
        Qt.callLater(function() {
            if (root.visible)
                root.forceActiveFocus();
        });
        return true;
    }

    function _requestPdfSearchStep(delta) {
        if (!root._pdfReaderReady() || root.pdfSearchText.trim().length === 0)
            return false;
        if (Number(delta || 0) < 0)
            root.pdfMultiPageViewHandle.searchBack();
        else
            root.pdfMultiPageViewHandle.searchForward();
        return true;
    }

    function _pdfSearchResultCount() {
        var view = root.pdfMultiPageViewHandle;
        var model = view ? view.searchModel : null;
        if (!model || model.count === undefined)
            return -1;
        var count = Number(model.count);
        return isFinite(count) ? Math.max(0, Math.floor(count)) : -1;
    }

    function _pdfSearchStatusText() {
        if (!root.mediaPdfActive || root.pdfSearchText.trim().length === 0)
            return "";
        var count = root.pdfSearchResultCount;
        if (count < 0)
            return "Search active";
        if (count === 0)
            return "No matches";
        var view = root.pdfMultiPageViewHandle;
        var current = view && view.searchModel ? Number(view.searchModel.currentResult) : -1;
        if (isFinite(current) && current >= 0 && current < count)
            return String(Math.floor(current) + 1) + " / " + String(count);
        return String(count) + " matches";
    }

    function _requestPdfPageDelta(delta) {
        if (!root.mediaPdfActive)
            return false;
        if (root.pdfPageCount > 0 && root.pdfDocumentReady) {
            var normalizedDelta = root._intValue(delta, 0);
            var targetPage = root._boundedPdfPage(root.pdfCurrentPageNumber + normalizedDelta);
            return root._goToPdfViewerPage(targetPage);
        }
        if (!root.bridgeRef || !root.bridgeRef.request_pdf_page_delta)
            return false;
        return Boolean(root.bridgeRef.request_pdf_page_delta(delta));
    }

    function _wheelDeltaY(wheel) {
        if (!wheel)
            return 0;
        var delta = 0;
        if (wheel.angleDelta && wheel.angleDelta.y !== undefined && Number(wheel.angleDelta.y) !== 0)
            delta = Number(wheel.angleDelta.y);
        else if (wheel.pixelDelta && wheel.pixelDelta.y !== undefined && Number(wheel.pixelDelta.y) !== 0)
            delta = Number(wheel.pixelDelta.y);
        if (wheel.inverted)
            delta = -delta;
        return delta;
    }

    function _requestPdfPageDeltaFromWheel(wheel) {
        if (!root.mediaPdfActive || (pdfPageField && pdfPageField.activeFocus))
            return false;
        var deltaY = root._wheelDeltaY(wheel);
        if (Math.abs(deltaY) < 0.001)
            return false;
        return root._requestPdfPageDelta(deltaY < 0 ? 1 : -1);
    }

    function _requestPdfPageNumber(pageNumber) {
        if (!root.mediaPdfActive)
            return false;
        if (root.pdfPageCount > 0 && root.pdfDocumentReady)
            return root._goToPdfViewerPage(pageNumber);
        if (!root.bridgeRef || !root.bridgeRef.request_pdf_page_number)
            return false;
        return Boolean(root.bridgeRef.request_pdf_page_number(pageNumber));
    }

    function _goToPdfViewerPage(pageNumber) {
        var pageCount = Math.max(0, root.pdfPageCount);
        var view = root.pdfMultiPageViewHandle;
        if (pageCount <= 0 || !view)
            return false;
        var targetPage = root._boundedPdfPage(pageNumber);
        if (Number(view.currentPage) === targetPage - 1) {
            root._syncPdfPageField(false);
            return true;
        }
        view.goToPage(targetPage - 1);
        root._syncPdfPageField(true);
        return true;
    }

    function _syncPdfViewToResolvedPage() {
        if (root.mediaKind !== "pdf" || !root.pdfDocumentReady || root.pdfPageCount <= 0)
            return;
        root._goToPdfViewerPage(root.pdfResolvedPageNumber);
    }

    function _syncPdfDocumentSource() {
        var document = root.pdfDocumentHandle;
        if (!document)
            return;
        var nextSource = root.bridgeOpen && root.mediaKind === "pdf" && root.pdfSourceUrl.length > 0
            ? root.pdfSourceUrl
            : "";
        if (nextSource.length === 0) {
            root._releasePdfViewer();
            return;
        }
        if (String(document.source || "") === nextSource)
            return;
        document.source = nextSource;
    }

    function _releasePdfViewer() {
        root.pdfViewerReleased = true;
    }

    function _sanitizeIntegerText(value) {
        return String(value === undefined || value === null ? "" : value).replace(/[^0-9]/g, "");
    }

    function _boundedPdfPage(value) {
        var maxPage = Math.max(1, root.pdfPageCount);
        var numeric = root._intValue(value, root.pdfResolvedPageNumber);
        if (numeric < 1)
            numeric = 1;
        if (numeric > maxPage)
            numeric = maxPage;
        return numeric;
    }

    function _commitPdfPageText(value) {
        var cleaned = root._sanitizeIntegerText(value);
        if (cleaned.length === 0) {
            root._syncPdfPageField(true);
            return false;
        }
        var targetPage = root._boundedPdfPage(Number(cleaned));
        if (root._requestPdfPageNumber(targetPage)) {
            if (pdfPageField)
                pdfPageField.text = String(targetPage);
            return true;
        }
        root._syncPdfPageField(true);
        return false;
    }

    function _syncPdfPageField(force) {
        if (pdfPageField && (Boolean(force) || !pdfPageField.activeFocus))
            pdfPageField.text = String(root._boundedPdfPage(root.pdfCurrentPageNumber));
    }

    function _activeSurfaceSpec() {
        if ((root.contentKind === "media" || root.contentKind === "mail")
                && root.mediaPayload.surface_spec)
            return root.mediaPayload.surface_spec;
        if (root.contentKind === "viewer" && root.viewerPayload.surface_spec)
            return root.viewerPayload.surface_spec;
        if (root.contentKind === "web_editor" && root.webEditorPayload.surface_spec)
            return root.webEditorPayload.surface_spec;
        if (root.contentKind === "web_page" && root.webPagePayload.surface_spec)
            return root.webPagePayload.surface_spec;
        if (root.contentKind === "plot" && root.plotPayload.surface_spec)
            return root.plotPayload.surface_spec;
        if (root.contentKind === "tabular" && root.tabularPayload.surface_spec)
            return root.tabularPayload.surface_spec;
        return ({});
    }

    function _destroyMailWebEngineView() {
        if (!root.mailWebEngineView)
            return;
        root.mailWebEngineView.destroy();
        root.mailWebEngineView = null;
    }

    function _resetMailReaderControls() {
        root.mailZoomFactor = 1.0;
        root.mailFitMode = "actual";
    }

    function _syncMailWebEnginePreview() {
        if (!root.bridgeOpen || root.contentKind !== "mail" || root.previewSourceUrl.length === 0) {
            root._destroyMailWebEngineView();
            return;
        }
        if (!root.mailWebEngineView)
            root.mailWebEngineView = root._createMailWebEngineView();
        if (root.mailWebEngineView) {
            root._syncMailWebEngineZoom();
            root.mailWebEngineView.url = root.previewSourceUrl;
            root._scheduleMailFitRefresh();
        }
    }

    function _mailReaderReady() {
        return root.contentKind === "mail" && !!root.mailWebEngineView;
    }

    function _clampMailZoomFactor(value) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = 1.0;
        if (numeric < 0.25)
            numeric = 0.25;
        if (numeric > 3.0)
            numeric = 3.0;
        return numeric;
    }

    function _setMailZoomFactor(value, fitMode) {
        if (!root._mailReaderReady())
            return false;
        root.mailZoomFactor = root._clampMailZoomFactor(value);
        root.mailFitMode = String(fitMode || "custom");
        root._syncMailWebEngineZoom();
        return true;
    }

    function _syncMailWebEngineZoom() {
        var view = root.mailWebEngineView;
        if (!view)
            return false;
        try {
            if (view.pageZoom !== undefined) {
                view.pageZoom = root.mailZoomFactor;
                return true;
            }
        } catch (error) {
        }
        try {
            view.zoomFactor = root.mailZoomFactor;
            return true;
        } catch (fallbackError) {
            return false;
        }
    }

    function _requestMailZoom(factor) {
        if (!root._mailReaderReady())
            return false;
        var normalizedFactor = Number(factor);
        if (!isFinite(normalizedFactor) || normalizedFactor <= 0)
            return false;
        return root._setMailZoomFactor(root.mailZoomFactor * normalizedFactor, "custom");
    }

    function _mailViewportWidth() {
        if (mailViewport && Number(mailViewport.width) > 0)
            return Math.max(1, Number(mailViewport.width));
        return 1;
    }

    function _mailViewportHeight() {
        if (mailViewport && Number(mailViewport.height) > 0)
            return Math.max(1, Number(mailViewport.height));
        return 1;
    }

    function _applyMailFitMode(mode, remember) {
        if (!root._mailReaderReady())
            return false;
        var normalizedMode = String(mode || "custom").trim().toLowerCase();
        if (normalizedMode === "actual")
            return root._setMailZoomFactor(1.0, "actual");
        if (normalizedMode !== "page" && normalizedMode !== "width")
            normalizedMode = "custom";
        root.mailFitMode = normalizedMode;
        root._requestMailContentMetrics();
        return true;
    }

    function _requestMailContentMetrics() {
        if (root.mailFitMode !== "page" && root.mailFitMode !== "width")
            return;
        var view = root.mailWebEngineView;
        if (!view || !view.requestContentMetrics)
            return;
        view.requestContentMetrics();
    }

    function _scheduleMailFitRefresh() {
        if (root.mailFitMode !== "page" && root.mailFitMode !== "width")
            return;
        Qt.callLater(function() {
            root._requestMailContentMetrics();
        });
    }

    function _applyMailFitZoomForMetrics(contentWidth, contentHeight) {
        if (root.mailFitMode !== "page" && root.mailFitMode !== "width")
            return;
        var resolvedContentWidth = Number(contentWidth || 0);
        var resolvedContentHeight = Number(contentHeight || 0);
        if (!isFinite(resolvedContentWidth) || resolvedContentWidth <= 0.0)
            return;
        var nextZoom = root._mailViewportWidth() / resolvedContentWidth;
        if (root.mailFitMode === "page"
                && isFinite(resolvedContentHeight)
                && resolvedContentHeight > 0.0)
            nextZoom = Math.min(nextZoom, root._mailViewportHeight() / resolvedContentHeight);
        if (!isFinite(nextZoom) || nextZoom <= 0.0)
            return;
        root.mailZoomFactor = root._clampMailZoomFactor(Math.round(nextZoom * 100.0) / 100.0);
        root._syncMailWebEngineZoom();
    }

    function _createMailWebEngineView() {
        var qml = [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "WebEngineView {",
            "    objectName: \"contentFullscreenMailWebEngineView\"",
            "    signal contentMetricsReady(real contentWidth, real contentHeight)",
            "    property real pageZoom: 1.0",
            "    anchors.fill: parent",
            "    url: \"about:blank\"",
            "    function requestContentMetrics() {",
            "        try {",
            "            runJavaScript(\"(function(){var d=document.documentElement||{};var b=document.body||{};var v=window.visualViewport||{};function n(x){x=Number(x||0);return isFinite(x)?x:0;}return {width:Math.max(n(d.scrollWidth),n(b.scrollWidth),n(d.offsetWidth),n(b.offsetWidth),n(d.clientWidth),n(b.clientWidth),n(window.innerWidth),n(v.width)),height:Math.max(n(d.scrollHeight),n(b.scrollHeight),n(d.offsetHeight),n(b.offsetHeight),n(d.clientHeight),n(b.clientHeight),n(window.innerHeight),n(v.height))};})()\", function(result) {",
            "                var data = result || {};",
            "                contentMetricsReady(Number(data.width || 0), Number(data.height || 0));",
            "            });",
            "        } catch (error) {",
            "            contentMetricsReady(0, 0);",
            "        }",
            "    }",
            "    onPageZoomChanged: zoomFactor = pageZoom",
            "    onLoadingChanged: requestContentMetrics()",
            "    profile: WebEngineProfile {",
            "        objectName: \"contentFullscreenMailWebEngineProfile\"",
            "        offTheRecord: true",
            "        httpCacheType: WebEngineProfile.NoCache",
            "        persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies",
            "    }",
            "    settings.javascriptEnabled: false",
            "    settings.pluginsEnabled: false",
            "    settings.localContentCanAccessRemoteUrls: true",
            "    settings.localContentCanAccessFileUrls: true",
            "    settings.errorPageEnabled: false",
            "}"
        ].join("\n");
        try {
            root.mailWebEngineDiagnostic = "";
            var view = Qt.createQmlObject(qml, mailWebEngineLayer, "ContentFullscreenMailWebEngineView");
            if (view && view.contentMetricsReady)
                view.contentMetricsReady.connect(root._applyMailFitZoomForMetrics);
            return view;
        } catch (error) {
            root.mailWebEngineDiagnostic = String(error || "");
            return null;
        }
    }

    function _displayModeFromPayload() {
        if (root.payloadFitMode === "cover")
            return "fill";
        if (root.payloadFitMode === "original")
            return "actual";
        return "fit";
    }

    function _normalizedMediaCrop() {
        var crop = root.mediaPayload.crop || ({});
        return GraphMediaPanelGeometry.normalizedCropRect(
            Number(crop.x || 0.0),
            Number(crop.y || 0.0),
            Number(crop.width || 1.0),
            Number(crop.height || 1.0)
        );
    }

    function _sourceClipRect() {
        if (root.mediaKind === "pdf")
            return Qt.rect(0, 0, 0, 0);
        if (!(root.sourcePixelWidth > 0) || !(root.sourcePixelHeight > 0))
            return Qt.rect(0, 0, 0, 0);
        return GraphMediaPanelGeometry.sourceClipRectFromNormalized(
            root.mediaCrop,
            root.sourcePixelWidth,
            root.sourcePixelHeight
        );
    }

    function _viewerStatusText() {
        if (root.contentKind === "plot") {
            var plotSurface = root.plotPayload.plot_surface || ({});
            var plotType = String(plotSurface.plot_type || root.plotPayload.surface_variant || "plot");
            if (Boolean(plotSurface.embedded_rendering_suppressed))
                return plotType + " live fullscreen";
            return plotType + " live surface";
        }
        var phase = String(root.viewerPayload.phase || "closed");
        var cacheState = String(root.viewerPayload.cache_state || "");
        var liveMode = String(root.viewerPayload.live_mode || "");
        var details = [];
        if (phase.length > 0)
            details.push("Session " + phase);
        if (cacheState.length > 0)
            details.push("Cache " + cacheState);
        if (liveMode.length > 0)
            details.push("Mode " + liveMode);
        return details.length > 0
            ? details.join("  |  ")
            : "Viewer surface is waiting for live retargeting.";
    }

    Connections {
        target: root.webSurfaceBridge
        enabled: root.webEditorClosePending

        function onPreviewExportFinished(result) {
            root._finishWebEditorClose(result || ({}));
        }
    }

    Connections {
        target: root.graphCanvasCommandBridgeRef

        function onManagedArtifactRenameReleaseRequested(nodeId) {
            if (!root.mediaVideoActive)
                return;
            if (String(nodeId || "") !== root.activeNodeId)
                return;
            root.requestClose();
        }
    }

    Timer {
        id: webEditorCloseTimeout
        interval: 10000
        repeat: false
        onTriggered: root._finishWebEditorClose({"ok": false, "error": "Preview export timed out."})
    }

    Rectangle {
        anchors.fill: parent
        color: root.themePalette.app_bg
    }

    MouseArea {
        id: interactionBlocker
        objectName: "contentFullscreenInteractionBlocker"
        anchors.fill: parent
        z: 1
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        preventStealing: true
        onPressed: function(mouse) { mouse.accepted = true; }
        onReleased: function(mouse) { mouse.accepted = true; }
        onWheel: function(wheel) {
            root._requestPdfPageDeltaFromWheel(wheel);
            wheel.accepted = true;
        }
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12
        z: 2

        Rectangle {
            id: topBar
            objectName: "contentFullscreenTopBar"
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            radius: 6
            color: root.themePalette.toolbar_bg
            border.width: 1
            border.color: root.themePalette.border

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 8
                spacing: 8

                Text {
                    id: titleLabel
                    objectName: "contentFullscreenTitleText"
                    Layout.fillWidth: true
                    text: root.titleText.length > 0 ? root.titleText : "Fullscreen content"
                    color: root.themePalette.panel_title_fg
                    font.pixelSize: 14
                    font.bold: true
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }

                Text {
                    id: shortcutHint
                    objectName: "contentFullscreenShortcutHint"
                    text: root.mediaPdfActive
                        ? "Ctrl+F  Ctrl+Plus/Minus  Esc"
                        : (root.contentKind === "mail"
                            ? "Ctrl+Plus/Minus  Esc"
                            : "Esc / F11")
                    color: root.themePalette.muted_fg
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                }

                ShellButton {
                    id: closeButton
                    objectName: "contentFullscreenCloseButton"
                    text: "Close"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.close")
                    onClicked: root.requestClose()
                }
            }
        }

        Rectangle {
            id: contentFrame
            objectName: "contentFullscreenContentFrame"
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 8
            color: Qt.darker(root.themePalette.panel_bg, 1.08)
            border.width: 1
            border.color: root.themePalette.border
            clip: true

            ColumnLayout {
                id: mediaLayout
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                visible: root.mediaReady
                    && (root.mediaKind === "image" || root.mediaKind === "pdf")

                ColumnLayout {
                    id: mediaToolbar
                    objectName: "contentFullscreenMediaToolbar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.mediaKind === "pdf"
                        ? (root.pdfSearchOpen ? 64 : 28)
                        : 28
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        spacing: 6

                        Text {
                            objectName: "contentFullscreenMediaSummary"
                            Layout.fillWidth: true
                            text: root.mediaKind === "pdf"
                                ? "PDF page " + root.pdfCurrentPageNumber + " / " + Math.max(1, root.pdfPageCount)
                                : (root.sourcePixelWidth > 0 && root.sourcePixelHeight > 0
                                    ? root.sourcePixelWidth + " x " + root.sourcePixelHeight
                                    : "Image preview")
                            color: root.themePalette.muted_fg
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        RowLayout {
                            id: pdfNavigationControls
                            objectName: "contentFullscreenPdfNavigationControls"
                            visible: root.mediaKind === "pdf"
                            Layout.preferredHeight: 24
                            spacing: 6

                            ShellButton {
                                objectName: "contentFullscreenPdfPreviousButton"
                                text: ""
                                iconName: "navigate-previous"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.previous_page")
                                enabled: root.pdfPageCount > 0 && root.pdfCurrentPageNumber > 1
                                onClicked: root._requestPdfPageDelta(-1)
                            }

                            TextField {
                                id: pdfPageField
                                objectName: "contentFullscreenPdfPageField"
                                Layout.preferredWidth: 54
                                Layout.preferredHeight: 24
                                text: String(root._boundedPdfPage(root.pdfCurrentPageNumber))
                                color: root.themePalette.input_fg
                                selectedTextColor: root.themePalette.input_fg
                                selectionColor: Qt.alpha(root.themePalette.accent, 0.45)
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: 12
                                font.bold: true
                                selectByMouse: true
                                inputMethodHints: Qt.ImhDigitsOnly
                                enabled: root.pdfPageCount > 0
                                validator: IntValidator {
                                    bottom: 1
                                    top: Math.max(1, root.pdfPageCount)
                                }
                                background: Rectangle {
                                    radius: 3
                                    color: root.themePalette.input_bg
                                    border.width: pdfPageField.activeFocus ? 1 : 0
                                    border.color: root.themePalette.accent
                                }
                                onTextEdited: {
                                    var cleaned = root._sanitizeIntegerText(pdfPageField.text);
                                    if (cleaned !== pdfPageField.text) {
                                        var nextCursor = Math.min(cleaned.length, pdfPageField.cursorPosition);
                                        pdfPageField.text = cleaned;
                                        pdfPageField.cursorPosition = nextCursor;
                                    }
                                }
                                onActiveFocusChanged: {
                                    if (!pdfPageField.activeFocus)
                                        root._commitPdfPageText(pdfPageField.text);
                                }
                                Keys.onReturnPressed: {
                                    root._commitPdfPageText(pdfPageField.text);
                                    pdfPageField.selectAll();
                                }
                                Keys.onEnterPressed: {
                                    root._commitPdfPageText(pdfPageField.text);
                                    pdfPageField.selectAll();
                                }
                            }

                            Text {
                                objectName: "contentFullscreenPdfPageTotalLabel"
                                Layout.preferredHeight: 24
                                text: "/ " + Math.max(1, root.pdfPageCount)
                                color: root.themePalette.muted_fg
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfNextButton"
                                text: ""
                                iconName: "navigate-next"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.next_page")
                                enabled: root.pdfPageCount > 0 && root.pdfCurrentPageNumber < root.pdfPageCount
                                onClicked: root._requestPdfPageDelta(1)
                            }
                        }

                        RowLayout {
                            id: pdfReaderControls
                            objectName: "contentFullscreenPdfReaderControls"
                            visible: root.mediaKind === "pdf"
                            Layout.preferredHeight: 24
                            spacing: 6

                            ShellButton {
                                objectName: "contentFullscreenPdfSearchButton"
                                text: ""
                                iconName: "search"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.find")
                                selectedStyle: root.pdfSearchOpen
                                enabled: root.pdfDocumentReady
                                onClicked: root.pdfSearchOpen ? root._closePdfSearch() : root._openPdfSearch()
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfZoomOutButton"
                                text: ""
                                iconName: "zoom-out"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.zoom_out")
                                enabled: root.pdfDocumentReady && root.pdfRenderScale > 0.101
                                onClicked: root._requestPdfZoom(1 / 1.15)
                            }

                            Text {
                                objectName: "contentFullscreenPdfZoomLabel"
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 24
                                text: root.pdfZoomLabel
                                color: root.themePalette.muted_fg
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfZoomInButton"
                                text: ""
                                iconName: "zoom-in"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.zoom_in")
                                enabled: root.pdfDocumentReady && root.pdfRenderScale < 9.999
                                onClicked: root._requestPdfZoom(1.15)
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfFitPageButton"
                                text: "Page"
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.fit_page")
                                selectedStyle: root.pdfFitMode === "page"
                                enabled: root.pdfDocumentReady
                                onClicked: root._applyPdfFitMode("page", true)
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfFitWidthButton"
                                text: "Width"
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.fit_width")
                                selectedStyle: root.pdfFitMode === "width"
                                enabled: root.pdfDocumentReady
                                onClicked: root._applyPdfFitMode("width", true)
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfActualSizeButton"
                                text: "100%"
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.actual_size")
                                selectedStyle: root.pdfFitMode === "actual"
                                enabled: root.pdfDocumentReady
                                onClicked: root._applyPdfFitMode("actual", true)
                            }

                            ShellButton {
                                objectName: "contentFullscreenPdfRotateClockwiseButton"
                                text: ""
                                iconName: "rotate-clockwise"
                                iconSize: 16
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.rotate_clockwise")
                                enabled: root.pdfDocumentReady
                                onClicked: root._rotatePdfPages(90)
                            }
                        }

                        ShellButton {
                            objectName: "contentFullscreenDisplayModeFitButton"
                            visible: root.mediaKind !== "pdf"
                            text: "Fit"
                            selectedStyle: root.effectiveDisplayMode === "fit"
                            onClicked: root.localDisplayMode = "fit"
                        }

                        ShellButton {
                            objectName: "contentFullscreenDisplayModeFillButton"
                            visible: root.mediaKind !== "pdf"
                            text: "Fill"
                            selectedStyle: root.effectiveDisplayMode === "fill"
                            onClicked: root.localDisplayMode = "fill"
                        }

                        ShellButton {
                            objectName: "contentFullscreenDisplayModeActualButton"
                            visible: root.mediaKind !== "pdf"
                            text: "100%"
                            selectedStyle: root.effectiveDisplayMode === "actual"
                            onClicked: root.localDisplayMode = "actual"
                        }
                    }

                    RowLayout {
                        id: pdfSearchControls
                        objectName: "contentFullscreenPdfSearchControls"
                        visible: root.mediaKind === "pdf" && root.pdfSearchOpen
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        spacing: 6

                        TextField {
                            id: pdfSearchField
                            objectName: "contentFullscreenPdfSearchField"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 180
                            Layout.preferredHeight: 28
                            placeholderText: "Find in PDF"
                            text: root.pdfSearchText
                            color: root.themePalette.input_fg
                            placeholderTextColor: root.themePalette.muted_fg
                            selectedTextColor: root.themePalette.input_fg
                            selectionColor: Qt.alpha(root.themePalette.accent, 0.45)
                            font.pixelSize: 12
                            selectByMouse: true
                            enabled: root.pdfDocumentReady
                            background: Rectangle {
                                radius: 4
                                color: root.themePalette.input_bg
                                border.width: 1
                                border.color: pdfSearchField.activeFocus
                                    ? root.themePalette.accent
                                    : root.themePalette.input_border
                            }
                            onTextEdited: root.pdfSearchText = text
                            Keys.onPressed: function(event) {
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    root._requestPdfSearchStep((event.modifiers & Qt.ShiftModifier) !== 0 ? -1 : 1);
                                    event.accepted = true;
                                } else if (event.key === Qt.Key_Escape) {
                                    root._closePdfSearch();
                                    event.accepted = true;
                                }
                            }
                        }

                        Text {
                            objectName: "contentFullscreenPdfSearchStatus"
                            Layout.preferredWidth: 96
                            Layout.preferredHeight: 28
                            text: root.pdfSearchStatusText
                            color: root.themePalette.muted_fg
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        ShellButton {
                            objectName: "contentFullscreenPdfSearchPreviousButton"
                            text: ""
                            iconName: "navigate-previous"
                            iconSize: 16
                            tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.search_previous")
                            enabled: root.pdfDocumentReady && root.pdfSearchText.trim().length > 0
                            onClicked: root._requestPdfSearchStep(-1)
                        }

                        ShellButton {
                            objectName: "contentFullscreenPdfSearchNextButton"
                            text: ""
                            iconName: "navigate-next"
                            iconSize: 16
                            tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.search_next")
                            enabled: root.pdfDocumentReady && root.pdfSearchText.trim().length > 0
                            onClicked: root._requestPdfSearchStep(1)
                        }

                        ShellButton {
                            objectName: "contentFullscreenPdfSearchClearButton"
                            text: "Clear"
                            tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.search_clear")
                            enabled: root.pdfSearchText.length > 0
                            onClicked: root._clearPdfSearch()
                        }
                    }
                }

                Rectangle {
                    id: mediaViewport
                    objectName: "contentFullscreenMediaViewport"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 6
                    color: root.themePalette.input_bg
                    border.width: 1
                    border.color: root.themePalette.input_border
                    clip: true

                    Loader {
                        id: pdfViewerLoader
                        objectName: "contentFullscreenPdfViewerLoader"
                        anchors.fill: parent
                        anchors.margins: 8
                        active: root.bridgeOpen
                            && root.mediaPdfActive
                            && root.pdfSourceUrl.length > 0
                            && !root.pdfViewerReleased
                        sourceComponent: Component {
                            Item {
                                property alias pdfDocument: pdfDocument
                                property alias pdfMultiPageView: pdfMultiPageView

                                anchors.fill: parent

                                PdfDocument {
                                    id: pdfDocument
                                    objectName: "contentFullscreenPdfDocument"
                                    source: root.pdfSourceUrl
                                    onStatusChanged: {
                                        if (status === PdfDocument.Ready)
                                            Qt.callLater(function() { root._syncPdfViewToResolvedPage(); });
                                    }
                                    onPageCountChanged: Qt.callLater(function() { root._syncPdfViewToResolvedPage(); })
                                }

                                PdfMultiPageView {
                                    id: pdfMultiPageView
                                    objectName: "contentFullscreenPdfMultiPageView"
                                    anchors.fill: parent
                                    visible: pdfDocument.status === PdfDocument.Ready
                                        && pdfDocument.pageCount > 0
                                    document: pdfDocument
                                    searchString: root.pdfSearchText
                                    clip: true
                                    onCurrentPageChanged: root._syncPdfPageField(false)
                                    onRenderScaleChanged: {
                                        if (!root.pdfApplyingFitMode)
                                            root.pdfFitMode = "custom";
                                    }
                                    onWidthChanged: root._schedulePdfFitRefresh()
                                    onHeightChanged: root._schedulePdfFitRefresh()
                                }
                            }
                        }
                    }

                    Item {
                        id: mediaImageViewport
                        objectName: "contentFullscreenMediaImageViewport"
                        x: Number(root.mediaImageDisplayRect.x || 0)
                        y: Number(root.mediaImageDisplayRect.y || 0)
                        width: Math.max(0, Number(root.mediaImageDisplayRect.width || 0))
                        height: Math.max(0, Number(root.mediaImageDisplayRect.height || 0))
                        visible: root.mediaImageActive
                            && (root.mediaImageAnimationSupported
                                ? root.imageResolvedSourceUrl.length > 0
                                : root.previewSourceUrl.length > 0)
                        clip: true

                        Item {
                            id: mediaImageTransformFrame
                            objectName: "contentFullscreenMediaImageTransformFrame"
                            x: (parent.width - width) * 0.5
                            y: (parent.height - height) * 0.5
                            width: Math.max(0, Number(root.mediaImageCropFrameWidth || 0))
                            height: Math.max(0, Number(root.mediaImageCropFrameHeight || 0))
                            rotation: root.mediaImageRotationDegrees
                            transformOrigin: Item.Center

                            Item {
                                id: mediaImageMirrorFrame
                                objectName: "contentFullscreenMediaImageMirrorFrame"
                                anchors.fill: parent
                                transform: Scale {
                                    origin.x: mediaImageMirrorFrame.width * 0.5
                                    origin.y: mediaImageMirrorFrame.height * 0.5
                                    xScale: root.mediaImageMirrorHorizontal ? -1 : 1
                                    yScale: root.mediaImageMirrorVertical ? -1 : 1
                                }

                                Image {
                                    id: mediaImage
                                    objectName: "contentFullscreenMediaImage"
                                    x: Number(root.mediaImageOffsetX || 0)
                                    y: Number(root.mediaImageOffsetY || 0)
                                    width: Math.max(0, Number(root.mediaImageFullFrameWidth || 0))
                                    height: Math.max(0, Number(root.mediaImageFullFrameHeight || 0))
                                    asynchronous: false
                                    cache: true
                                    mipmap: true
                                    smooth: true
                                    source: root.mediaImageActive && !root.mediaImageAnimationSupported
                                        ? root.previewSourceUrl
                                        : ""
                                    sourceSize.width: 0
                                    sourceSize.height: 0
                                    fillMode: Image.Stretch
                                    visible: source.toString().length > 0
                                }

                                Loader {
                                    id: mediaAnimatedImageLoader
                                    objectName: "contentFullscreenMediaAnimatedImageLoader"
                                    anchors.fill: parent
                                    active: root.mediaImageAnimationSupported

                                    sourceComponent: AnimatedImage {
                                        objectName: "contentFullscreenMediaAnimatedImage"
                                        x: Number(root.mediaImageOffsetX || 0)
                                        y: Number(root.mediaImageOffsetY || 0)
                                        width: Math.max(0, Number(root.mediaImageFullFrameWidth || 0))
                                        height: Math.max(0, Number(root.mediaImageFullFrameHeight || 0))
                                        asynchronous: true
                                        cache: false
                                        mipmap: true
                                        smooth: true
                                        autoTransform: true
                                        source: root.imageResolvedSourceUrl
                                        playing: source.toString().length > 0
                                        fillMode: Image.Stretch
                                        visible: source.toString().length > 0
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        objectName: "contentFullscreenMediaPlaceholder"
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 48, 420)
                        visible: root.mediaKind === "pdf"
                            ? !root.pdfViewVisible
                            : (root.mediaImageAnimationSupported
                                ? (!root.mediaAnimatedImageItem
                                    || !root.mediaAnimatedImageItem.visible
                                    || root.mediaAnimatedImageItem.status === Image.Error)
                                : (!mediaImage.visible || mediaImage.status === Image.Error))
                        text: root.mediaKind === "pdf"
                            ? String(root.mediaPayload.pdf_preview && root.mediaPayload.pdf_preview.message
                                ? root.mediaPayload.pdf_preview.message
                                : (root.pdfDocumentLoading
                                    ? "Loading PDF..."
                                    : "PDF preview is unavailable."))
                            : String(root.mediaPayload.preview_message || "Image preview is unavailable.")
                        color: root.themePalette.muted_fg
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }

            }

            ColumnLayout {
                id: mailLayout
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "mail"
                spacing: 10

                RowLayout {
                    id: mailReaderControls
                    objectName: "contentFullscreenMailReaderControls"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    spacing: 6

                    Text {
                        objectName: "contentFullscreenMailSummary"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        text: root.mailAttachmentSummary
                        color: root.themePalette.muted_fg
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }

                    ShellButton {
                        objectName: "contentFullscreenMailZoomOutButton"
                        text: ""
                        iconName: "zoom-out"
                        iconSize: 16
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.mail.zoom_out")
                        enabled: root.mailWebEngineView !== null && root.mailZoomFactor > 0.251
                        onClicked: root._requestMailZoom(1 / 1.15)
                    }

                    Text {
                        objectName: "contentFullscreenMailZoomLabel"
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 24
                        text: root.mailZoomLabel
                        color: root.themePalette.muted_fg
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    ShellButton {
                        objectName: "contentFullscreenMailZoomInButton"
                        text: ""
                        iconName: "zoom-in"
                        iconSize: 16
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.mail.zoom_in")
                        enabled: root.mailWebEngineView !== null && root.mailZoomFactor < 2.999
                        onClicked: root._requestMailZoom(1.15)
                    }

                    ShellButton {
                        objectName: "contentFullscreenMailFitPageButton"
                        text: "Page"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.mail.fit_message")
                        selectedStyle: root.mailFitMode === "page"
                        enabled: root.mailWebEngineView !== null
                        onClicked: root._applyMailFitMode("page", true)
                    }

                    ShellButton {
                        objectName: "contentFullscreenMailFitWidthButton"
                        text: "Width"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.mail.fit_width")
                        selectedStyle: root.mailFitMode === "width"
                        enabled: root.mailWebEngineView !== null
                        onClicked: root._applyMailFitMode("width", true)
                    }

                    ShellButton {
                        objectName: "contentFullscreenMailActualSizeButton"
                        text: "100%"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.mail.actual_size")
                        selectedStyle: root.mailFitMode === "actual"
                        enabled: root.mailWebEngineView !== null
                        onClicked: root._applyMailFitMode("actual", true)
                    }
                }

                Rectangle {
                    id: mailViewport
                    objectName: "contentFullscreenMailViewport"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 6
                    color: root.themePalette.input_bg
                    border.width: 1
                    border.color: root.themePalette.input_border
                    clip: true
                    onWidthChanged: root._scheduleMailFitRefresh()
                    onHeightChanged: root._scheduleMailFitRefresh()

                    Item {
                        id: mailWebEngineLayer
                        objectName: "contentFullscreenMailWebEngineLayer"
                        anchors.fill: parent
                        visible: root.mailWebEngineView !== null
                    }

                    Text {
                        objectName: "contentFullscreenMailPlaceholder"
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 48, 420)
                        visible: root.mailWebEngineView === null
                        text: root.mailWebEngineDiagnostic.length > 0
                            ? root.mailWebEngineDiagnostic
                            : root.mailPreviewMessage
                        color: root.themePalette.muted_fg
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Loader {
                id: videoFullscreenLoader
                objectName: "contentFullscreenVideoSurfaceLoader"
                anchors.fill: parent
                anchors.margins: 12
                active: root.mediaVideoActive
                sourceComponent: PassiveComponents.GraphMediaVideoFullscreenRenderer {
                    payload: root.mediaPayload
                    bridgeRef: root.bridgeRef
                    themePalette: root.themePalette
                }
            }

            Text {
                objectName: "contentFullscreenMediaStatePlaceholder"
                anchors.centerIn: parent
                width: Math.min(parent.width - 64, 520)
                visible: root.mediaContentActive && !root.mediaReady
                text: root.mediaStateMessage
                color: root.themePalette.muted_fg
                font.pixelSize: 13
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            ColumnLayout {
                id: viewerLayout
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "viewer" || root.contentKind === "plot"
                spacing: root.contentKind === "viewer" ? 0 : 8

                RowLayout {
                    id: plotQuickControls
                    objectName: "contentFullscreenPlotQuickControls"
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.preferredHeight: root.contentKind === "plot" ? 28 : 0
                    visible: root.contentKind === "plot"
                    spacing: 6

                    ShellButton {
                        objectName: "contentFullscreenPlotHoverReadoutButton"
                        text: "Hover"
                        iconName: "search"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.plot.hover_readout")
                        selectedStyle: root.plotHoverReadout
                        Layout.preferredWidth: 78
                        onClicked: root._setPlotOption("hover_readout", !root.plotHoverReadout)
                    }

                    ShellButton {
                        objectName: "contentFullscreenPlotVerticalGuideButton"
                        text: "Guide"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.plot.vertical_guide")
                        selectedStyle: root.plotVerticalGuide
                        Layout.preferredWidth: 74
                        onClicked: root._setPlotOption("vertical_guide", !root.plotVerticalGuide)
                    }

                    ShellButton {
                        objectName: "contentFullscreenPlotCrosshairButton"
                        text: "Cross"
                        iconName: "focus"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.plot.crosshair")
                        selectedStyle: root.plotCrosshair
                        Layout.preferredWidth: 74
                        onClicked: root._setPlotOption("crosshair", !root.plotCrosshair)
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    ComboBox {
                        id: plotThemeCombo
                        objectName: "contentFullscreenPlotThemeCombo"
                        Layout.preferredWidth: 112
                        Layout.preferredHeight: 24
                        model: ["system", "dark", "light"]
                        currentIndex: Math.max(0, ["system", "dark", "light"].indexOf(root.plotThemeOption))
                        font.pixelSize: 11
                        palette.buttonText: root.themePalette.tab_fg
                        palette.text: root.themePalette.tab_fg
                        palette.highlight: root.themePalette.accent
                        palette.highlightedText: root.themePalette.tab_selected_fg
                        palette.base: root.themePalette.input_bg
                        palette.window: root.themePalette.panel_bg
                        onActivated: function(index) {
                            root._setPlotOption("plot_theme", ["system", "dark", "light"][index]);
                        }
                    }
                }

                ViewerComponents.ViewerSelectionControls {
                    id: viewerSelectionControls
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.preferredHeight: implicitHeight
                    themePalette: root.themePalette
                    nodeId: root.activeNodeId
                    fullscreenBridgeRef: root.bridgeRef
                    sessionBridgeRef: root.viewerSessionBridgeRef
                    controlBridgeRef: root.viewerControlBridgeRef
                    hostServiceRef: root.viewerHostServiceRef
                    sessionState: root.viewerLiveSessionState
                    presentationVisible: root.contentKind === "viewer"
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    Rectangle {
                        id: viewerViewport
                        objectName: "contentFullscreenViewerViewport"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 6
                        color: root.themePalette.input_bg
                        border.width: 1
                        border.color: root.themePalette.accent

                        Column {
                            anchors.centerIn: parent
                            width: Math.min(parent.width - 48, 520)
                            spacing: 10

                            Text {
                                objectName: "contentFullscreenViewerPlaceholderTitle"
                                width: parent.width
                                text: root.contentKind === "plot"
                                    ? String(root.plotPayload.title || root.titleText || "Plot")
                                    : String(root.viewerPayload.title || root.titleText || "Viewer")
                                color: root.themePalette.panel_title_fg
                                font.pixelSize: 15
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }

                            Text {
                                objectName: "contentFullscreenViewerStatusText"
                                width: parent.width
                                text: root._viewerStatusText()
                                color: root.themePalette.muted_fg
                                font.pixelSize: 12
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                objectName: "contentFullscreenViewerRetargetHint"
                                width: parent.width
                                text: root.contentKind === "plot"
                                    ? "Live plot retargeting will attach here."
                                    : "Live viewer retargeting will attach here."
                                color: root.themePalette.muted_fg
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    ViewerComponents.ViewerSidePanel {
                        id: viewerSidePanel
                        visible: root.contentKind === "viewer"
                        Layout.fillHeight: true
                        Layout.preferredWidth: implicitWidth
                        themePalette: root.themePalette
                        nodeId: root.activeNodeId
                        bridgeRef: root.viewerControlBridgeRef
                        fullscreenBridgeRef: root.bridgeRef
                        hostServiceRef: root.viewerHostServiceRef
                        sessionState: root.viewerLiveSessionState
                    }
                }

                ViewerComponents.ViewerQuickControls {
                    id: viewerQuickControls
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.preferredHeight: root.contentKind === "viewer" ? 54 : 0
                    visible: root.contentKind === "viewer"
                    themePalette: root.themePalette
                    nodeId: root.activeNodeId
                    fullscreenBridgeRef: root.bridgeRef
                    sessionBridgeRef: root.viewerSessionBridgeRef
                    controlBridgeRef: root.viewerControlBridgeRef
                    hostServiceRef: root.viewerHostServiceRef
                    sessionState: root.viewerLiveSessionState
                }
            }

            WebComponents.WebEditorHost {
                id: webEditorHost
                objectName: "contentFullscreenWebEditorHost"
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "web_editor"
                payload: root.webEditorPayload
                webSurfaceBridge: root.webSurfaceBridge
                themePalette: root.themePalette
                onClosePreviewExportResult: function(result) {
                    root._finishWebEditorClose(result || ({}));
                }
            }

            Item {
                id: scriptEditorWorkspace
                objectName: "contentFullscreenScriptEditorWorkspace"
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "script_editor"

                RowLayout {
                    anchors.fill: parent
                    spacing: 8

                    ScriptCodeEditorPane {
                        id: scriptEditorPane
                        objectName: "contentFullscreenScriptEditorPane"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        scriptEditorBridgeRef: root.scriptEditorBridgeRef
                        scriptHighlighterBridgeRef: root.scriptHighlighterBridgeRef
                        themeBridgeRef: themeBridge
                        graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                        uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
                        guideButtonVisible: true
                        guideButtonSelected: root.scriptGuideVisible
                        onGuideRequested: root.scriptGuideVisible = !root.scriptGuideVisible
                    }

                    PythonScriptGuidePane {
                        id: pythonScriptGuidePane
                        objectName: "contentFullscreenPythonScriptGuidePane"
                        visible: root.scriptGuideVisible
                        Layout.preferredWidth: Math.max(300, Math.min(440, scriptEditorWorkspace.width * 0.38))
                        Layout.fillHeight: true
                        themeBridgeRef: themeBridge
                        graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                        uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
                        onCloseRequested: root.scriptGuideVisible = false
                    }
                }
            }

            Item {
                id: webPageBorrowedViewport
                objectName: "contentFullscreenBorrowedWebPageViewport"
                anchors.fill: parent
                anchors.margins: 12
                visible: root._usesBorrowedWebEngine() && root.webPageBorrowedActive
                clip: true
            }

            Rectangle {
                objectName: "contentFullscreenJupyterPlaceholder"
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "jupyter_notebook"
                    && !root.webPageBorrowedActive
                    && !root.webPageBorrowSyncPending
                radius: 6
                color: root.themePalette.input_bg
                border.width: 1
                border.color: root.themePalette.input_border

                Text {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 48, 420)
                    text: "Jupyter notebook view is not ready for fullscreen."
                    color: root.themePalette.muted_fg
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }

            WebComponents.WebPageHost {
                id: webPageHost
                objectName: "contentFullscreenWebPageHost"
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "web_page"
                    && !root.webPageBorrowedActive
                    && !root.webPageBorrowSyncPending
                payload: root.webPagePayload
                themePalette: root.themePalette
                browserStateBridge: root.bridgeRef
                surfaceMode: "fullscreen"
                onFullscreenRequested: root.requestClose()
            }

            TabularComponents.TabularFullscreenSurface {
                id: tabularFullscreenSurface
                objectName: "contentFullscreenTabularSurface"
                anchors.fill: parent
                anchors.margins: 12
                visible: root.contentKind === "tabular"
                payload: root.tabularPayload
                bridgeRef: root.bridgeRef
                themePalette: root.themePalette
            }
        }
    }
}
