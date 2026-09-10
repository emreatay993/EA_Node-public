// Purpose: Dispatch one Media Panel to the renderer selected by its effective source.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15
import ".." as GraphShared
import "../surface_controls/SourceStorageModeUtils.js" as SourceStorageModeUtils
import "GraphMediaPanelSourceUtils.js" as GraphMediaPanelSourceUtils

GraphShared.GraphSurfaceBase {
    id: dispatcher
    objectName: "graphNodeMediaSurface"

    property bool rendererActive: false
    property string loadedRendererKey: ""

    chromeToggleAvailable: true
    readonly property string nodeId: host && host.nodeData
        ? String(host.nodeData.node_id || "")
        : ""
    readonly property var sourceLookup: host && host.executionFacts
        && host.executionFacts.mediaPanelSourceLookup
        ? host.executionFacts.mediaPanelSourceLookup
        : ({})
    readonly property var sourceResolution: nodeId.length > 0 && sourceLookup[nodeId]
        ? sourceLookup[nodeId]
        : ({
            "authority": "input",
            "input_exposed": true,
            "input_connected": false,
            "state": "waiting",
            "media_kind": "",
            "source_ref": "",
            "resolved_source_url": "",
            "preview_source_url": "",
            "message": "Media source state is unavailable."
        })
    readonly property bool inputExposed: Boolean(sourceResolution.input_exposed)
    readonly property bool inputConnected: Boolean(sourceResolution.input_connected)
    readonly property string sourceState: String(sourceResolution.state || "invalid")
    readonly property string mediaKind: String(sourceResolution.media_kind || "")
    readonly property bool sourceReady: sourceState === "ready"
        && (mediaKind === "image" || mediaKind === "pdf" || mediaKind === "video")
    readonly property string authoredSource: propValue("source")
    readonly property string sourceStorageMode: SourceStorageModeUtils.sourceModeForPath(authoredSource)
    readonly property bool sourceEditingEnabled: !inputExposed && !blocksHostInteraction
    readonly property bool canInternalizeSource: sourceEditingEnabled
        && sourceStorageMode === "external_link"
        && GraphMediaPanelSourceUtils.resolvedLocalFileSourceUrl(authoredSource).length > 0
    readonly property string effectiveLocalSourceUrl: sourceReady
        ? GraphMediaPanelSourceUtils.resolvedLocalFileSourceUrl(
            String(sourceResolution.resolved_source_url || "")
        )
        : ""
    readonly property bool openSourceAvailable: effectiveLocalSourceUrl.length > 0
    readonly property bool fileIssueActive: !inputExposed
        && authoredSource.trim().length > 0
        && (sourceState === "stale" || sourceState === "invalid")
    readonly property string placeholderMessage: String(
        sourceResolution.message
        || (inputExposed
            ? (inputConnected ? "Run the connected media source." : "Connect a Path, String, or Image value to Source.")
            : "Choose an image, PDF, or video source.")
    )
    readonly property string rendererKey: sourceReady
        ? [
            mediaKind,
            String(sourceResolution.resolved_source_url || ""),
            String(sourceResolution.preview_source_url || "")
        ].join("\u001f")
        : sourceState
    readonly property var loadedRenderer: rendererLoader.item
    readonly property bool blocksHostInteraction: loadedRenderer
        ? Boolean(loadedRenderer.blocksHostInteraction)
        : false
    readonly property var embeddedInteractiveRects: loadedRenderer
        && loadedRenderer.embeddedInteractiveRects
        ? loadedRenderer.embeddedInteractiveRects
        : []
    readonly property bool aspectRatioLocked: loadedRenderer
        ? Boolean(loadedRenderer.aspectRatioLocked)
        : false
    readonly property var modeActions: loadedRenderer
        && Array.isArray(loadedRenderer.surfaceActions)
        ? loadedRenderer.surfaceActions
        : []
    readonly property bool fullscreenAvailable: host ? Boolean(host.surfaceFullscreenAvailable) : false
    readonly property var surfaceActions: _commonActions().concat(modeActions)

    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    onRendererKeyChanged: _syncRenderer()
    Component.onCompleted: _syncRenderer()
    Component.onDestruction: release()

    Connections {
        target: host

        function onNodeOpenRequested(nodeId) {
            if (!host || !host.nodeData
                    || String(nodeId || "") !== String(host.nodeData.node_id || ""))
                return;
            dispatcher._browseProperty("", false);
        }
    }

    function release() {
        if (rendererLoader.item && rendererLoader.item.release)
            rendererLoader.item.release();
        rendererActive = false;
    }

    function _syncRenderer() {
        if (rendererLoader.item && rendererLoader.item.release)
            rendererLoader.item.release();
        rendererActive = false;
        loadedRendererKey = rendererKey;
        if (!sourceReady)
            return;
        var expectedKey = loadedRendererKey;
        Qt.callLater(function() {
            if (dispatcher.sourceReady && dispatcher.loadedRendererKey === expectedKey)
                dispatcher.rendererActive = true;
        });
    }

    function _commonActions() {
        var actions = [{
            "id": "editSource",
            "label": "Source",
            "icon": "search",
            "kind": "media",
            "enabled": sourceEditingEnabled,
            "primary": !inputExposed && authoredSource.trim().length === 0,
            "popover_layout": "source_storage",
            "popoverActions": [
                {
                    "id": "editSourceExternalLink",
                    "label": "External link",
                    "icon": "external-link",
                    "kind": "media",
                    "toolbar_text": "External",
                    "source_mode": "external_link",
                    "checked": sourceStorageMode === "external_link",
                    "enabled": sourceEditingEnabled,
                    "close_popover": true
                },
                {
                    "id": "editSourceManagedCopy",
                    "label": "Internal copy",
                    "icon": "open-session",
                    "kind": "media",
                    "toolbar_text": "Internal",
                    "source_mode": "managed_copy",
                    "checked": sourceStorageMode === "managed_copy",
                    "enabled": sourceEditingEnabled,
                    "close_popover": true
                }
            ]
        }];
        actions.push({
            "id": "openSourceMenu",
            "label": "Open",
            "icon": "external-link",
            "kind": "media",
            "enabled": openSourceAvailable,
            "popover_layout": "row",
            "popoverActions": [
                {
                    "id": "openSource",
                    "label": "Open",
                    "kind": "media",
                    "toolbar_text": "Open",
                    "close_popover": true
                },
                {
                    "id": "openSourceWith",
                    "label": "Open with...",
                    "kind": "media",
                    "toolbar_text": "Open with...",
                    "close_popover": true
                }
            ]
        });
        if (canInternalizeSource) {
            actions.push({
                "id": "internalizeSource",
                "label": "Copy into project",
                "icon": "internalize-source",
                "kind": "media",
                "enabled": true
            });
        }
        actions.push({
            "id": "toggle_source_input",
            "label": inputExposed ? "Hide Source Input" : "Show Source Input",
            "icon": "plug",
            "kind": "media",
            "enabled": true,
            "checked": inputExposed,
            "primary": false
        });
        actions.push({
            "id": "toggle_content_only",
            "label": surfaceContentOnly ? "Show chrome" : "Content only",
            "icon": surfaceContentOnly ? "node-chrome" : "content-only",
            "kind": "media",
            "enabled": !blocksHostInteraction,
            "primary": surfaceContentOnly
        });
        actions.push({
            "id": "toggle_title",
            "label": surfaceShowTitle ? "Hide title" : "Show title",
            "icon": "title-heading",
            "kind": "media",
            "enabled": !blocksHostInteraction,
            "primary": false
        });
        actions.push({
            "id": "toggle_frame",
            "label": surfaceShowFrame ? "Hide frame" : "Show frame",
            "icon": "frame-corners",
            "kind": "media",
            "enabled": !blocksHostInteraction,
            "primary": false
        });
        var fullscreenAction = host && host.surfaceFullscreenAction
            ? host.surfaceFullscreenAction(fullscreenAvailable && sourceReady && !blocksHostInteraction, false)
            : null;
        if (fullscreenAction)
            actions.push(fullscreenAction);
        if (fileIssueActive) {
            actions.push({
                "id": "repair",
                "label": "Repair",
                "icon": "plug",
                "kind": "media",
                "enabled": sourceEditingEnabled,
                "primary": true
            });
        }
        return actions;
    }

    function _canvasItem() {
        return host && host.canvasItem ? host.canvasItem : null;
    }

    function _sceneCommandBridge() {
        var canvasItem = _canvasItem();
        return canvasItem && canvasItem.sceneCommandBridge
            ? canvasItem.sceneCommandBridge
            : null;
    }

    function _commitProperty(key, value) {
        if (!host || !host.nodeData)
            return false;
        host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), key, value);
        return true;
    }

    function _commitChromeAppearance(showTitle, showFrame) {
        if (!host || !host.nodeData)
            return false;
        var canvasItem = _canvasItem();
        var values = {
            "show_title": Boolean(showTitle),
            "show_frame": Boolean(showFrame)
        };
        if (canvasItem && canvasItem.commitNodeSurfaceProperties)
            return Boolean(canvasItem.commitNodeSurfaceProperties(nodeId, values));
        _commitProperty("show_title", values.show_title);
        _commitProperty("show_frame", values.show_frame);
        return true;
    }

    function _browseProperty(sourceMode, repair) {
        if (!sourceEditingEnabled || !host || !host.browseNodePropertyPath)
            return false;
        var current = repair
            ? "ea-file-repair:" + encodeURIComponent(authoredSource)
            : authoredSource;
        var mode = SourceStorageModeUtils.normalizedSourceMode(sourceMode, sourceStorageMode);
        var selected = String(host.browseNodePropertyPath("source", current, mode) || "");
        return selected.length > 0 && selected !== authoredSource
            ? _commitProperty("source", selected)
            : false;
    }

    function _internalizeSource() {
        if (!canInternalizeSource || !host || !host.internalizeNodePropertyPath)
            return false;
        var managed = String(host.internalizeNodePropertyPath("source", authoredSource) || "");
        return managed.length > 0 && managed !== authoredSource
            ? _commitProperty("source", managed)
            : false;
    }

    function _openSource(chooser) {
        if (!openSourceAvailable || !host || !host.openLocalFileSource)
            return false;
        var result = host.openLocalFileSource(effectiveLocalSourceUrl, Boolean(chooser));
        return !!result && Boolean(result.success);
    }

    function _toggleSourceInput() {
        var bridge = _sceneCommandBridge();
        if (!bridge || !bridge.set_exposed_port || !nodeId.length)
            return false;
        bridge.set_exposed_port(nodeId, "source", !inputExposed);
        return true;
    }

    function _requestContentFullscreen() {
        if (!sourceReady || !host || !host.requestSurfaceContentFullscreen)
            return false;
        var state = loadedRenderer && loadedRenderer.fullscreenRuntimeState
            ? loadedRenderer.fullscreenRuntimeState()
            : ({});
        return Boolean(host.requestSurfaceContentFullscreen(state));
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "editSource")
            return _browseProperty("", false);
        if (normalized === "editSourceManagedCopy")
            return _browseProperty("managed_copy", false);
        if (normalized === "editSourceExternalLink")
            return _browseProperty("external_link", false);
        if (normalized === "internalizeSource")
            return _internalizeSource();
        if (normalized === "openSource")
            return _openSource(false);
        if (normalized === "openSourceWith")
            return _openSource(true);
        if (normalized === "toggle_source_input")
            return _toggleSourceInput();
        if (normalized === "toggle_content_only")
            return surfaceContentOnly
                ? _commitChromeAppearance(true, true)
                : _commitChromeAppearance(false, false);
        if (normalized === "toggle_title")
            return _commitChromeAppearance(!surfaceShowTitle, surfaceShowFrame);
        if (normalized === "toggle_frame")
            return _commitChromeAppearance(surfaceShowTitle, !surfaceShowFrame);
        if (normalized === "fullscreen")
            return _requestContentFullscreen();
        if (normalized === "repair")
            return fileIssueActive ? _browseProperty("", true) : false;
        if (loadedRenderer && loadedRenderer.dispatchSurfaceAction)
            return Boolean(loadedRenderer.dispatchSurfaceAction(normalized));
        return false;
    }

    Loader {
        id: rendererLoader
        anchors.fill: parent
        active: dispatcher.rendererActive
        sourceComponent: dispatcher.mediaKind === "image"
            ? imageRendererComponent
            : (dispatcher.mediaKind === "pdf"
                ? pdfRendererComponent
                : (dispatcher.mediaKind === "video" ? videoRendererComponent : null))
    }

    Component {
        id: imageRendererComponent
        GraphMediaImageRenderer {
            host: dispatcher.host
            sourceResolution: dispatcher.sourceResolution
        }
    }

    Component {
        id: pdfRendererComponent
        GraphMediaPdfRenderer {
            host: dispatcher.host
            sourceResolution: dispatcher.sourceResolution
        }
    }

    Component {
        id: videoRendererComponent
        GraphMediaVideoRenderer {
            host: dispatcher.host
            sourceResolution: dispatcher.sourceResolution
        }
    }

    Rectangle {
        objectName: "graphNodeMediaStatePlaceholder"
        anchors.fill: parent
        visible: !dispatcher.sourceReady
        radius: dispatcher.surfaceShowFrame
            ? (host ? Number(host.resolvedCornerRadius || 6) : 6)
            : 0
        color: dispatcher.surfaceShowFrame
            ? (host ? Qt.darker(host.surfaceColor, 1.03) : "#1b1d22")
            : "transparent"
        border.width: dispatcher.surfaceShowFrame
            ? (host ? Number(host.resolvedBorderWidth || 1) : 1)
            : 0
        border.color: host && host.isSelected
            ? host.themeSelectedOutlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a")

        Text {
            objectName: "graphNodeMediaStateMessage"
            anchors.centerIn: parent
            width: Math.min(parent.width - 32, 300)
            text: dispatcher.placeholderMessage
            color: host ? host.inlineDrivenTextColor : "#bdc5d3"
            font.pixelSize: host ? Number(host.passiveFontPixelSize || 12) : 12
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }
    }
}
