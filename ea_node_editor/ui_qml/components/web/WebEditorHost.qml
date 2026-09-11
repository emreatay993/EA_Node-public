import QtQuick 2.15
import QtQuick.Controls 2.15

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
    readonly property bool rendererStopped: !!root.webEngineItem && Boolean(root.webEngineItem.rendererStopped)

    clip: true

    onShouldLoadWebEngineChanged: Qt.callLater(root._syncWebEngineItem)
    onAssetUrlChanged: Qt.callLater(root._syncWebEngineItem)
    onWebSurfaceBridgeChanged: {
        root._destroyWebEngineItem();
        Qt.callLater(root._syncWebEngineItem);
    }
    onVisibleChanged: {
        if (visible) {
            Qt.callLater(root._syncWebEngineItem);
        } else {
            root._destroyWebEngineItem();
        }
    }

    Component.onCompleted: Qt.callLater(root._syncWebEngineItem)
    Component.onDestruction: root._destroyWebEngineItem()

    Connections {
        target: root.webSurfaceBridge
        function onCloseRequested() { root.requestClosePreviewExport(); }
    }

    function _requestHostAction(action) {
        if (!root.webEngineItem || !root.webEngineItem.runJavaScript || root.rendererStopped) {
            if (root.webSurfaceBridge)
                root._hostMissing(root.webSurfaceBridge, action);
            return false;
        }
        var bridge = root.webSurfaceBridge;
        root.webEngineItem.runJavaScript(
            "(function() { var host = window.corexExcalidrawHost; if (!host || !host."
                + action + ") return false; host." + action + "(); return true; })();",
            function(started) {
                if (!started && bridge && bridge === root.webSurfaceBridge)
                    root._hostMissing(bridge, action);
            }
        );
        return true;
    }

    function requestClosePreviewExport() { return root._requestHostAction("requestClose"); }
    function retryPreview() { return root._requestHostAction("retryPreview"); }

    function _hostMissing(bridge, action) {
        if (action === "requestClose" || action === "closeWithoutPreview")
            bridge.recover_unstarted_editor("close");
        else if (action === "reloadEditor")
            bridge.recover_unstarted_editor("reload");
        else
            bridge.host_unavailable("The editor is still loading or its connection failed. Reopen it to retry.");
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
            "    property bool rendererStopped: false",
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
            "        onRenderProcessTerminated: function(status, exitCode) {",
            "            webRoot.rendererStopped = true;",
            "            if (webRoot.bridgeObject) webRoot.bridgeObject.editor_stopped();",
            "        }",
            "    }",
            "}"
        ].join("\n");
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

            Button {
                objectName: "contentFullscreenWebEditorRetryButton"
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Retry preview"
                visible: root.bridgeErrorText.length > 0
                onClicked: root.retryPreview()
            }

            Button {
                objectName: "contentFullscreenWebEditorCloseWithoutPreviewButton"
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.rendererStopped ? "Close with saved drawing" : "Save drawing and close without preview"
                visible: root.bridgeErrorText.length > 0
                onClicked: root._requestHostAction("closeWithoutPreview")
            }

            Button {
                objectName: "contentFullscreenWebEditorReloadButton"
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.rendererStopped ? "Reopen saved drawing" : "Save drawing and reload editor"
                visible: root.statusMessage.length > 0 && root.webSurfaceBridge !== null
                onClicked: root._requestHostAction("reloadEditor")
            }

        }
    }
}
