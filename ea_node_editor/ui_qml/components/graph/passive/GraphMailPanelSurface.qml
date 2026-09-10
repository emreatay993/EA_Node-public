import QtQuick 2.15
import ".." as GraphShared
import QtQuick.Controls 2.15
import "../surface_controls/SourceStorageModeUtils.js" as SourceStorageModeUtils
import "GraphMediaPanelSourceUtils.js" as GraphMediaPanelSourceUtils

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeMailSurface"
    chromeToggleAvailable: true

    readonly property string sourcePath: propValue("source_path")
    readonly property string sourceStorageMode: SourceStorageModeUtils.sourceModeForPath(sourcePath)
    readonly property bool canInternalizeSource: sourceStorageMode === "external_link"
        && GraphMediaPanelSourceUtils.resolvedLocalFileSourceUrl(sourcePath).length > 0
    readonly property string previewUrl: String(mailPreviewInfo.preview_url || "")
    readonly property string previewState: String(mailPreviewInfo.state || (sourcePath.trim().length ? "placeholder" : "placeholder"))
    readonly property string previewMessage: String(mailPreviewInfo.message || "")
    readonly property var previewMetadata: mailPreviewInfo.metadata || ({})
    readonly property var attachments: mailPreviewInfo.attachments || []
    readonly property string attachmentSummary: String(mailPreviewInfo.attachment_summary || "No attachments")
    readonly property bool readyPreview: previewState === "ready" && previewUrl.length > 0
    readonly property bool fileIssueActive: sourcePath.trim().length > 0
        && (previewState === "error" || previewState === "unavailable")
    readonly property string fileIssueMessage: fileIssueActive
        ? (previewMessage.length ? previewMessage : "The mail source is missing or cannot be previewed.")
        : ""
    readonly property bool blocksHostInteraction: false
    readonly property bool fullscreenAvailable: host ? Boolean(host.surfaceFullscreenAvailable) : false
    readonly property color panelFillColor: host && host.hasPassiveFillOverride
        ? host.surfaceColor
        : Qt.darker(host ? host.surfaceColor : "#1b1d22", 1.03)
    readonly property color panelBorderColor: host && host.isSelected
        ? host.themeSelectedOutlineColor
        : (host && host.hasPassiveBorderOverride
            ? host.outlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a"))
    readonly property color viewportFillColor: host
        ? Qt.darker(host.inlineInputBackgroundColor, 1.02)
        : "#202228"
    readonly property color hintTextColor: host ? host.inlineDrivenTextColor : "#bdc5d3"
    readonly property color captionTextColor: host ? host.inlineInputTextColor : "#f0f2f5"
    readonly property real contentInset: host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14
    readonly property real contentLeftMargin: surfaceShowFrame ? (host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14) : 0
    readonly property real contentRightMargin: surfaceShowFrame ? (host ? Number(host.surfaceMetrics.body_right_margin || 14) : 14) : 0
    readonly property real contentTopMargin: {
        if (!host)
            return surfaceShowTitle ? 44 : (surfaceShowFrame ? contentInset : 0);
        if (!surfaceShowTitle)
            return surfaceShowFrame ? contentInset : 0;
        return Number(host.surfaceMetrics.body_top || 44);
    }
    readonly property real contentBottomMargin: surfaceShowFrame ? (host ? Number(host.surfaceMetrics.body_bottom_margin || 12) : 12) : 0
    readonly property var embeddedInteractiveRects: []
    readonly property var surfaceActions: {
        var actions = [
            {
                "id": "editSource",
                "label": "Source",
                "icon": "search",
                "kind": "media",
                "enabled": true,
                "primary": sourcePath.trim().length === 0,
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
                        "enabled": true,
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
                        "enabled": true,
                        "close_popover": true
                    }
                ]
            },
            {
                "id": "openSourceMenu",
                "label": "Open",
                "icon": "external-link",
                "kind": "media",
                "enabled": sourcePath.trim().length > 0,
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
            }
        ];
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
            "id": "toggle_content_only",
            "label": surfaceContentOnly ? "Show chrome" : "Content only",
            "icon": surfaceContentOnly ? "node-chrome" : "content-only",
            "kind": "media",
            "enabled": true,
            "popover_layout": "row",
            "popoverActions": [
                {
                    "id": "toggle_title",
                    "label": surfaceShowTitle ? "Hide title" : "Show title",
                    "kind": "media",
                    "toolbar_text": surfaceShowTitle ? "Hide title" : "Show title",
                    "checked": surfaceShowTitle,
                    "close_popover": true
                },
                {
                    "id": "toggle_frame",
                    "label": surfaceShowFrame ? "Hide frame" : "Show frame",
                    "kind": "media",
                    "toolbar_text": surfaceShowFrame ? "Hide frame" : "Show frame",
                    "checked": surfaceShowFrame,
                    "close_popover": true
                }
            ]
        });
        var fullscreenAction = host && host.surfaceFullscreenAction
            ? host.surfaceFullscreenAction(fullscreenAvailable && readyPreview, false)
            : null;
        if (fullscreenAction)
            actions.push(fullscreenAction);
        if (fileIssueActive) {
            actions.push({
                "id": "repair",
                "label": "Repair file...",
                "icon": "folder-open",
                "kind": "media",
                "enabled": true
            });
        }
        return actions;
    }

    property var mailPreviewInfo: ({})
    property string _mailPreviewSignature: ""
    property bool _mailPreviewRefreshQueued: false
    property var webEngineView: null
    property string webEngineDiagnostic: ""

    Component.onCompleted: {
        _refreshMailPreviewInfo();
        _syncWebEnginePreview();
    }
    Component.onDestruction: _destroyWebEngineView()
    onSourcePathChanged: _queueMailPreviewRefresh()
    onPreviewUrlChanged: _syncWebEnginePreview()
    onReadyPreviewChanged: _syncWebEnginePreview()

    function _beginInlineInteraction() {
        if (host && host.nodeData)
            host.surfaceControlInteractionStarted(String(host.nodeData.node_id || ""));
    }

    function _commitInlineProperty(key, value) {
        if (host && host.nodeData)
            host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), key, value);
    }

    function _commitSurfaceProperties(values) {
        if (!host || !host.nodeData)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var payload = values || ({});
        var canvasItem = host.canvasItem || null;
        if (canvasItem && canvasItem.commitNodeSurfaceProperties) {
            if (canvasItem.commitNodeSurfaceProperties(nodeId, payload))
                return true;
        }
        var changed = false;
        for (var key in payload) {
            if (!Object.prototype.hasOwnProperty.call(payload, key))
                continue;
            _commitInlineProperty(key, payload[key]);
            changed = true;
        }
        return changed;
    }

    function _browseInlinePropertyPath(key, currentPath, sourceMode) {
        if (!host || !host.browseNodePropertyPath)
            return "";
        var normalizedSourceMode = String(sourceMode || "").trim();
        if (normalizedSourceMode.length > 0)
            return String(host.browseNodePropertyPath(key, currentPath, normalizedSourceMode) || "");
        return String(host.browseNodePropertyPath(key, currentPath) || "");
    }

    function _editSource(sourceMode) {
        var selectedPath = _browseInlinePropertyPath(
            "source_path",
            sourcePath,
            SourceStorageModeUtils.normalizedSourceMode(sourceMode, sourceStorageMode)
        );
        if (!selectedPath.length || selectedPath === sourcePath)
            return false;
        _commitInlineProperty("source_path", selectedPath);
        return true;
    }

    function _internalizeSource() {
        if (!canInternalizeSource || !host || !host.internalizeNodePropertyPath)
            return false;
        var managedPath = String(host.internalizeNodePropertyPath("source_path", sourcePath) || "");
        if (!managedPath.length || managedPath === sourcePath)
            return false;
        _commitInlineProperty("source_path", managedPath);
        return true;
    }

    function _openSource(chooser) {
        if (!host || !host.openLocalFileSource)
            return false;
        var result = host.openLocalFileSource(sourcePath, Boolean(chooser));
        return !!result && Boolean(result.success);
    }

    function _requestContentFullscreen() {
        if (!fullscreenAvailable || !readyPreview || !host || !host.requestSurfaceContentFullscreen)
            return false;
        return Boolean(host.requestSurfaceContentFullscreen());
    }

    function _repairRequestValue(currentPath) {
        return "ea-file-repair:" + encodeURIComponent(String(currentPath || ""));
    }

    function repairFile() {
        var repairedPath = _browseInlinePropertyPath("source_path", _repairRequestValue(sourcePath));
        if (!repairedPath.length)
            return;
        _commitInlineProperty("source_path", repairedPath);
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        _beginInlineInteraction();
        if (normalized === "editSource")
            return _editSource();
        if (normalized === "editSourceManagedCopy")
            return _editSource("managed_copy");
        if (normalized === "editSourceExternalLink")
            return _editSource("external_link");
        if (normalized === "internalizeSource")
            return _internalizeSource();
        if (normalized === "openSource")
            return _openSource(false);
        if (normalized === "openSourceWith")
            return _openSource(true);
        if (normalized === "fullscreen")
            return _requestContentFullscreen();
        if (normalized === "toggle_content_only") {
            return surfaceContentOnly
                ? _commitChromeAppearance(true, true)
                : _commitChromeAppearance(false, false);
        }
        if (normalized === "toggle_title")
            return _commitChromeAppearance(!surfaceShowTitle, surfaceShowFrame);
        if (normalized === "toggle_frame")
            return _commitChromeAppearance(surfaceShowTitle, !surfaceShowFrame);
        if (normalized === "repair") {
            repairFile();
            return true;
        }
        return false;
    }

    function _commitChromeAppearance(showTitle, showFrame) {
        return _commitSurfaceProperties({
            "show_title": Boolean(showTitle),
            "show_frame": Boolean(showFrame)
        });
    }

    function _mailPreviewInfoSignature(info) {
        if (!info)
            return "";
        try {
            return JSON.stringify({
                "state": info.state || "",
                "preview_url": info.preview_url || "",
                "message": info.message || "",
                "file_stamp_token": info.file_stamp_token || "",
                "attachment_summary": info.attachment_summary || ""
            });
        } catch (error) {
            return String(info);
        }
    }

    function _applyMailPreviewInfo(value) {
        var info = value || ({});
        var signature = _mailPreviewInfoSignature(info);
        if (signature === _mailPreviewSignature)
            return false;
        _mailPreviewSignature = signature;
        mailPreviewInfo = info;
        return true;
    }

    function _queueMailPreviewRefresh() {
        if (_mailPreviewRefreshQueued)
            return;
        _mailPreviewRefreshQueued = true;
        Qt.callLater(function() {
            surface._mailPreviewRefreshQueued = false;
            surface._refreshMailPreviewInfo();
        });
    }

    function _refreshMailPreviewInfo() {
        if (!host || !host.describeMailPreview) {
            _applyMailPreviewInfo(({
                "state": sourcePath.trim().length ? "placeholder" : "placeholder",
                "message": sourcePath.trim().length
                    ? "Mail preview bridge is unavailable."
                    : "Choose a local mail file to preview it here."
            }));
            return false;
        }
        var changed = _applyMailPreviewInfo(host.describeMailPreview(sourcePath));
        _syncWebEnginePreview();
        return changed;
    }

    function _destroyWebEngineView() {
        if (!webEngineView)
            return;
        webEngineView.destroy();
        webEngineView = null;
    }

    function _syncWebEnginePreview() {
        if (!readyPreview) {
            _destroyWebEngineView();
            return;
        }
        if (!webEngineView)
            webEngineView = _createWebEngineView();
        if (webEngineView)
            webEngineView.url = previewUrl;
    }

    function _createWebEngineView() {
        var qml = [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "WebEngineView {",
            "    objectName: \"graphNodeMailWebEngineView\"",
            "    anchors.fill: parent",
            "    enabled: false",
            "    focus: false",
            "    activeFocusOnTab: false",
            "    url: \"about:blank\"",
            "    profile: WebEngineProfile {",
            "        objectName: \"graphNodeMailWebEngineProfile\"",
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
            webEngineDiagnostic = "";
            return Qt.createQmlObject(qml, webEngineLayer, "GraphMailPanelWebEngineView");
        } catch (error) {
            webEngineDiagnostic = String(error || "");
            return null;
        }
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        color: surfaceShowFrame ? surface.panelFillColor : "transparent"
        border.width: surfaceShowFrame ? 1 : 0
        border.color: surface.panelBorderColor
        radius: surfaceShowFrame ? 8 : 0

        Rectangle {
            id: viewport
            objectName: "graphNodeMailViewport"
            x: surface.contentLeftMargin
            y: surface.contentTopMargin
            width: Math.max(0, parent.width - surface.contentLeftMargin - surface.contentRightMargin)
            height: Math.max(0, parent.height - surface.contentTopMargin - surface.contentBottomMargin)
            color: surface.viewportFillColor
            border.width: surfaceShowFrame ? 1 : 0
            border.color: Qt.alpha(surface.panelBorderColor, 0.70)
            radius: surfaceShowFrame ? 6 : 0
            clip: true

            Item {
                id: webEngineLayer
                objectName: "graphNodeMailWebEngineLayer"
                anchors.fill: parent
                visible: surface.webEngineView !== null
            }

            Column {
                id: fallbackLayer
                objectName: "graphNodeMailFallbackPanel"
                visible: surface.webEngineView === null
                anchors.centerIn: parent
                width: Math.min(parent.width - 28, 300)
                spacing: 8

                Text {
                    objectName: "graphNodeMailFallbackTitle"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: surface.previewMetadata.subject || "Mail preview"
                    color: surface.captionTextColor
                    font.pixelSize: 13
                    font.bold: true
                    elide: Text.ElideRight
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }

                Text {
                    objectName: "graphNodeMailFallbackMessage"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: surface.previewMessage.length
                        ? surface.previewMessage
                        : "Choose a local mail file to preview it here."
                    color: surface.hintTextColor
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }

                Text {
                    objectName: "graphNodeMailAttachmentSummary"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: surface.attachmentSummary
                    color: surface.hintTextColor
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }
            }
        }
    }
}
