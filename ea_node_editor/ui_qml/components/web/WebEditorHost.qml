import QtQuick 2.15

Item {
    id: root
    objectName: "webEditorHost"
    property var payload: ({})
    property var webSurfaceBridge: null
    property var themePalette: ({})
    readonly property string assetUrl: String(payload.asset_url || "")
    readonly property string assetErrorText: String(payload.asset_error || "")
    readonly property bool webEngineAvailable: Boolean(payload.webengine_available)
    readonly property string webEngineUnavailableText: {
        if (webEngineAvailable)
            return "";
        var reason = String(payload.webengine_reason || "").trim();
        return reason.length > 0 ? "Qt WebEngine is unavailable: " + reason : "Qt WebEngine is unavailable.";
    }
    readonly property string bridgeErrorText: webSurfaceBridge && webSurfaceBridge.last_error
        ? String(webSurfaceBridge.last_error || "")
        : ""
    readonly property string statusMessage: {
        if (bridgeErrorText.length > 0)
            return bridgeErrorText;
        if (assetErrorText.length > 0)
            return "Web editor asset is unavailable: " + assetErrorText;
        if (webEngineLoadError.length > 0)
            return webEngineLoadError;
        if (webEngineUnavailableText.length > 0)
            return webEngineUnavailableText;
        if (!assetUrl.length)
            return "Web editor asset URL is unavailable.";
        return "";
    }
    readonly property bool shouldLoadWebEngine: visible
        && webEngineAvailable
        && assetUrl.length > 0
        && assetErrorText.length === 0
        && root.webSurfaceBridge !== null
        && root.webSurfaceBridge !== undefined
    property string webEngineLoadError: ""
    property var webEngineItem: null
    property var pendingSceneState: null
    signal closePreviewExportResult(var result)

    clip: true

    onShouldLoadWebEngineChanged: Qt.callLater(root._syncWebEngineItem)
    onAssetUrlChanged: Qt.callLater(root._syncWebEngineItem)
    onWebSurfaceBridgeChanged: {
        if (root.webEngineItem)
            root.webEngineItem.bridgeObject = root.webSurfaceBridge;
        Qt.callLater(root._syncWebEngineItem);
    }
    onVisibleChanged: {
        if (visible) {
            Qt.callLater(root._syncWebEngineItem);
        } else {
            saveDebounceTimer.stop();
            root.pendingSceneState = null;
            root._destroyWebEngineItem();
        }
    }

    Component.onCompleted: Qt.callLater(root._syncWebEngineItem)
    Component.onDestruction: root._destroyWebEngineItem()

    function requestSceneSave(sceneState) {
        root.pendingSceneState = sceneState;
        saveDebounceTimer.restart();
        return true;
    }

    function flushSceneSave() {
        if (!root.webSurfaceBridge || !root.webSurfaceBridge.save_state)
            return false;
        var sceneState = root.pendingSceneState;
        if (sceneState === null || sceneState === undefined)
            return true;
        root.pendingSceneState = null;
        return Boolean(root.webSurfaceBridge.save_state(sceneState));
    }

    function requestClosePreviewExport() {
        saveDebounceTimer.stop();
        root.flushSceneSave();
        if (!root.webEngineItem || !root.webEngineItem.runJavaScript)
            return false;
        root.webEngineItem.runJavaScript(
            root._closePreviewExportScript(),
            function(result) { root._handleClosePreviewScriptResult(result); }
        );
        return true;
    }

    function _handleClosePreviewScriptResult(result) {
        var text = String(result || "");
        if (text === "__corex_pending_close_preview__") {
            closePreviewPollTimer.attempts = 0;
            closePreviewPollTimer.restart();
            return;
        }
        if (!text.length || text === "true" || text === "false")
            return;
        try {
            root.closePreviewExportResult(JSON.parse(text));
        } catch (error) {
            root.closePreviewExportResult({"ok": false, "error": String(error)});
        }
    }

    function _pollClosePreviewResult() {
        if (!root.webEngineItem || !root.webEngineItem.runJavaScript) {
            closePreviewPollTimer.stop();
            root.closePreviewExportResult({"ok": false, "error": "Preview export is unavailable."});
            return;
        }
        closePreviewPollTimer.attempts += 1;
        root.webEngineItem.runJavaScript(
            "(function() { return window.corexClosePreviewResult || ''; })();",
            function(result) {
                var text = String(result || "");
                if (text.length > 0) {
                    closePreviewPollTimer.stop();
                    root._handleClosePreviewScriptResult(text);
                    return;
                }
                if (closePreviewPollTimer.attempts >= 75) {
                    closePreviewPollTimer.stop();
                    root.closePreviewExportResult({"ok": false, "error": "Preview export timed out."});
                }
            }
        );
    }

    function _closePreviewExportScript() {
        return [
            "(function() {",
            "  var host = window.corexExcalidrawHost || {};",
            "  var exportPreview = host.requestPreviewExport || host.exportPreview || window.corexExcalidrawExportPreview;",
            "  function fallbackResult(message) {",
            "    var sceneState = typeof host.getSceneState === 'function' ? host.getSceneState() : null;",
            "    return JSON.stringify({ok: false, error: message, scene_state: sceneState});",
            "  }",
            "  window.corexClosePreviewResult = '';",
            "  if (typeof exportPreview !== 'function')",
            "    return fallbackResult('Preview export is unavailable.');",
            "  Promise.resolve()",
            "    .then(function() {",
            "      return typeof host.flushSave === 'function' ? host.flushSave() : true;",
            "    })",
            "    .then(function() {",
            "      return exportPreview({reason: 'fullscreen_close'});",
            "    })",
            "    .then(function(result) {",
            "      window.corexClosePreviewResult = JSON.stringify(result || {});",
            "    })",
            "    .catch(function(error) {",
            "      window.corexClosePreviewResult = fallbackResult(error && error.message ? error.message : String(error));",
            "    });",
            "  return '__corex_pending_close_preview__';",
            "})();"
        ].join("\n");
    }

    function _syncWebEngineItem() {
        if (!root.shouldLoadWebEngine) {
            root._destroyWebEngineItem();
            return;
        }
        if (root.webEngineItem) {
            root.webEngineItem.bridgeObject = root.webSurfaceBridge;
            if (String(root.webEngineItem.pageUrl || "") !== root.assetUrl)
                root.webEngineItem.pageUrl = root.assetUrl;
            return;
        }
        try {
            root.webEngineLoadError = "";
            root.webEngineItem = Qt.createQmlObject(
                root._webEngineComponentQml(),
                webViewport,
                "contentFullscreenWebEditorDynamic"
            );
            root.webEngineItem.bridgeObject = root.webSurfaceBridge;
            root.webEngineItem.pageUrl = root.assetUrl;
        } catch (error) {
            root._destroyWebEngineItem();
            root.webEngineLoadError = "Web editor could not be loaded: " + String(error);
        }
    }

    function _destroyWebEngineItem() {
        if (!root.webEngineItem)
            return;
        root.webEngineItem.destroy();
        root.webEngineItem = null;
    }

    function _webEngineComponentQml() {
        return [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "import QtWebChannel",
            "Item {",
            "    id: webRoot",
            "    objectName: \"contentFullscreenWebEditorDynamicRoot\"",
            "    anchors.fill: parent",
            "    property var bridgeObject: null",
            "    property var registeredBridgeObject: null",
            "    property string pageUrl: \"\"",
            "    function runJavaScript(script) {",
            "        if (arguments.length > 1 && arguments[1])",
            "            editorView.runJavaScript(script, arguments[1]);",
            "        else",
            "            editorView.runJavaScript(script);",
            "    }",
            "    function syncBridgeRegistration() {",
            "        if (!bridgeObject) {",
            "            registeredBridgeObject = null;",
            "            return;",
            "        }",
            "        if (registeredBridgeObject === bridgeObject)",
            "            return;",
            "        editorChannel.registerObjects({\"webSurfaceBridge\": bridgeObject});",
            "        registeredBridgeObject = bridgeObject;",
            "    }",
            "    Component.onCompleted: syncBridgeRegistration()",
            "    onBridgeObjectChanged: {",
            "        syncBridgeRegistration();",
            "        if (bridgeObject && pageUrl.length > 0 && editorView.url.toString() !== pageUrl)",
            "            editorView.url = pageUrl;",
            "    }",
            "    onPageUrlChanged: {",
            "        if (bridgeObject && pageUrl.length > 0 && editorView.url.toString() !== pageUrl)",
            "            editorView.url = pageUrl;",
            "    }",
            "    WebChannel {",
            "        id: editorChannel",
            "        registeredObjects: []",
            "    }",
            "    WebEngineView {",
            "        id: editorView",
            "        objectName: \"contentFullscreenWebEngineView\"",
            "        anchors.fill: parent",
            "        url: \"\"",
            "        webChannel: editorChannel",
            "    }",
            "}"
        ].join("\n");
    }

    Timer {
        id: saveDebounceTimer
        interval: 250
        repeat: false
        onTriggered: root.flushSceneSave()
    }

    Timer {
        id: closePreviewPollTimer
        property int attempts: 0
        interval: 100
        repeat: true
        onTriggered: root._pollClosePreviewResult()
    }

    Rectangle {
        anchors.fill: parent
        radius: 6
        color: root.themePalette.input_bg || "#151821"
        border.width: 1
        border.color: root.themePalette.input_border || root.themePalette.border || "#3a4355"
    }

    Item {
        id: webViewport
        objectName: "contentFullscreenWebEditorViewport"
        anchors.fill: parent
        anchors.margins: 1
        clip: true
    }

    Rectangle {
        id: fallbackPanel
        objectName: "contentFullscreenWebEditorFallback"
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 560)
        height: Math.min(parent.height - 48, Math.max(124, fallbackColumn.implicitHeight + 32))
        radius: 6
        visible: root.statusMessage.length > 0
        color: root.themePalette.panel_bg || "#1f2431"
        border.width: 1
        border.color: root.bridgeErrorText.length > 0
            ? (root.themePalette.error || "#d94f4f")
            : (root.themePalette.border || "#3a4355")

        Column {
            id: fallbackColumn
            anchors.centerIn: parent
            width: parent.width - 32
            spacing: 8

            Text {
                objectName: "contentFullscreenWebEditorFallbackTitle"
                width: parent.width
                text: String(root.payload.title || "Web editor")
                color: root.themePalette.panel_title_fg || "#eef3ff"
                font.pixelSize: 15
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }

            Text {
                objectName: "contentFullscreenWebEditorErrorText"
                width: parent.width
                text: root.statusMessage
                color: root.bridgeErrorText.length > 0
                    ? (root.themePalette.error || "#d94f4f")
                    : (root.themePalette.muted_fg || "#95a0b8")
                font.pixelSize: 12
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }
}
