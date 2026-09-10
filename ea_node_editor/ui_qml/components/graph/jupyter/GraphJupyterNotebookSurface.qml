import QtQuick 2.15

// Dedicated surface for the code.jupyter_notebook node. It asks the global
// jupyterServerBridge to start the project-scoped Jupyter server (off the UI
// thread) and, on serverReady, hosts the tokened single-document URL in a
// dynamically created WebEngineView. When Jupyter / WebEngine is unavailable or
// no notebook is selected it degrades to a status pane (no WebEngineView), the
// same discipline WebPageHost uses.
Item {
    id: root
    objectName: "graphJupyterNotebookSurface"

    property Item host: null
    property var themePalette: ({})

    readonly property var nodeData: host && host.nodeData ? host.nodeData : ({})
    readonly property var payload: (nodeData && nodeData.jupyter_notebook_payload
        && typeof nodeData.jupyter_notebook_payload === "object")
        ? nodeData.jupyter_notebook_payload : ({})
    readonly property string nodeId: String((payload.node_id
        || (nodeData ? nodeData.node_id : "")) || "")
    readonly property string notebookRef: String(payload.notebook_ref || "")
    readonly property string frontend: String(payload.frontend || "notebook")
    readonly property bool jupyterAvailable: Boolean(payload.jupyter_available)
    readonly property bool webengineAvailable: Boolean(payload.webengine_available)

    readonly property var jupyterServerBridgeRef:
        (typeof jupyterServerBridge !== "undefined" && jupyterServerBridge) ? jupyterServerBridge : null

    // idle | jupyter_unavailable | webengine_unavailable | no_notebook | server_starting | error | ready
    property string statusState: "idle"
    property string statusMessage: ""
    property string currentUrl: ""
    property string requestedRef: ""
    property var webEngineItem: null
    property var _externalWebEngineOriginalParent: null
    property string _externalWebEngineBorrowMode: ""
    readonly property bool webEngineBorrowedExternally: root._externalWebEngineBorrowMode.length > 0
    readonly property bool fullscreenBorrowable: root._hasBorrowableWebEngineForExternalPresentation(root.nodeId)
    readonly property bool fullscreenAvailable: host ? Boolean(host.surfaceFullscreenAvailable) : false
    readonly property var surfaceActions: {
        var action = root.host && root.host.surfaceFullscreenAction
            ? root.host.surfaceFullscreenAction(root.fullscreenAvailable && root.fullscreenBorrowable, false)
            : null
        return action ? [action] : []
    }

    function _palette(key, fallback) {
        return (themePalette && themePalette[key]) ? themePalette[key] : fallback
    }

    function _resolveState() {
        if (!jupyterAvailable) {
            _setStatus("jupyter_unavailable",
                "Jupyter is not installed.\nInstall it with:  pip install corex-node-editor[jupyter]")
            return
        }
        if (!webengineAvailable) {
            _setStatus("webengine_unavailable", "Qt WebEngine is unavailable in this build.")
            return
        }
        if (notebookRef.length === 0) {
            _setStatus("no_notebook",
                "No notebook selected.\nChoose or create a .ipynb in the inspector.")
            return
        }
        if (statusState === "ready" && requestedRef === notebookRef)
            return
        _requestServer()
    }

    function _setStatus(state, message) {
        statusState = state
        statusMessage = message
    }

    function _requestServer() {
        if (!jupyterServerBridgeRef || nodeId.length === 0) {
            _setStatus("error", "The Jupyter bridge is unavailable.")
            return
        }
        requestedRef = notebookRef
        _setStatus("server_starting", "Starting the Jupyter server…")
        jupyterServerBridgeRef.ensureServer(nodeId, notebookRef, frontend)
    }

    function _createBlankNotebook() {
        if (!jupyterServerBridgeRef || nodeId.length === 0) {
            _setStatus("error", "The Jupyter bridge is unavailable.")
            return
        }
        _setStatus("server_starting", "Creating a new notebook…")
        jupyterServerBridgeRef.createBlankNotebook(nodeId, String(payload.kernel_name || ""))
    }

    function _hostNotebook(url) {
        currentUrl = String(url || "")
        statusState = "ready"
        statusMessage = ""
        if (webEngineItem) {
            webEngineItem.url = currentUrl
            return
        }
        webEngineItem = _createWebEngineView(currentUrl)
    }

    function _createWebEngineView(url) {
        var qml = [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "WebEngineView {",
            "    objectName: \"jupyterNotebookWebEngineView\"",
            "    anchors.fill: parent",
            "    profile: WebEngineProfile {",
            "        objectName: \"jupyterNotebookWebEngineProfile\"",
            "        storageName: \"corex_jupyter\"",
            "        offTheRecord: false",
            "        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies",
            "    }",
            "    settings.localStorageEnabled: true",
            "    settings.javascriptCanAccessClipboard: true",
            "    settings.javascriptCanPaste: true",
            "    settings.fullScreenSupportEnabled: true",
            "}"
        ].join("\n");
        try {
            var view = Qt.createQmlObject(qml, viewport, "jupyterNotebookWebEngineView");
            view.url = url;
            return view;
        } catch (err) {
            _setStatus("error", "Failed to create the notebook view: " + err);
            return null;
        }
    }

    function dispatchSurfaceAction(actionId) {
        if (String(actionId || "") === "fullscreen")
            return root._requestFullscreen()
        return false
    }

    function _requestFullscreen() {
        if (!root.fullscreenBorrowable || !host || !host.requestSurfaceContentFullscreen)
            return false
        return Boolean(host.requestSurfaceContentFullscreen())
    }

    function _hasBorrowableWebEngineForExternalPresentation(nodeId) {
        var requestedNodeId = String(nodeId || "").trim()
        return root.nodeId.length > 0
            && (!requestedNodeId.length || requestedNodeId === root.nodeId)
            && root.webEngineItem
            && !root.webEngineBorrowedExternally
            && root.statusState === "ready"
            && root.currentUrl.length > 0
            && root.jupyterAvailable
            && root.webengineAvailable
    }

    function _attachWebEngineToExternalPresentation(target, nodeId, mode) {
        var normalizedMode = String(mode || "").trim()
        if (!target || !normalizedMode.length || !root._hasBorrowableWebEngineForExternalPresentation(nodeId))
            return false
        var item = root.webEngineItem
        var originalParent = item.parent || viewport
        try {
            item.parent = target
            item.visible = true
            item.anchors.fill = target
        } catch (error) {
            try {
                item.parent = originalParent
                item.visible = true
                item.anchors.fill = originalParent
            } catch (restoreError) {
            }
            return false
        }
        root._externalWebEngineOriginalParent = originalParent
        root._externalWebEngineBorrowMode = normalizedMode
        return true
    }

    function _releaseExternalWebEngine(mode) {
        var normalizedMode = String(mode || "").trim()
        if (!root.webEngineBorrowedExternally)
            return false
        if (normalizedMode.length > 0 && root._externalWebEngineBorrowMode !== normalizedMode)
            return false
        var restoreParent = root._externalWebEngineOriginalParent || viewport
        if (root.webEngineItem) {
            root.webEngineItem.parent = restoreParent
            root.webEngineItem.visible = true
            root.webEngineItem.anchors.fill = restoreParent
        }
        root._externalWebEngineBorrowMode = ""
        root._externalWebEngineOriginalParent = null
        return true
    }

    function hasBorrowableWebEngineForFullscreen(nodeId) {
        return root._hasBorrowableWebEngineForExternalPresentation(nodeId)
    }

    function attachWebEngineToFullscreen(target, nodeId) {
        return root._attachWebEngineToExternalPresentation(target, nodeId, "fullscreen")
    }

    function releaseFullscreenWebEngine() {
        return root._releaseExternalWebEngine("fullscreen")
    }

    Connections {
        target: root.jupyterServerBridgeRef
        ignoreUnknownSignals: true
        function onServerReady(nodeId, url) {
            if (String(nodeId) === root.nodeId)
                root._hostNotebook(String(url))
        }
        function onServerFailed(nodeId, reason) {
            if (String(nodeId) === root.nodeId)
                root._setStatus("error", String(reason || "Failed to start the Jupyter server."))
        }
        function onNotebookRefAssigned(nodeId, ref) {
            if (String(nodeId) === root.nodeId && root.host && root.host.inlinePropertyCommitted)
                root.host.inlinePropertyCommitted(root.nodeId, "notebook_ref", String(ref))
        }
    }

    onNotebookRefChanged: _resolveState()
    onJupyterAvailableChanged: _resolveState()
    onWebengineAvailableChanged: _resolveState()
    Component.onCompleted: _resolveState()
    Component.onDestruction: root.releaseFullscreenWebEngine()

    Item {
        id: viewport
        anchors.fill: parent
        visible: root.statusState === "ready"
    }

    Rectangle {
        objectName: "jupyterNotebookStatusPane"
        anchors.fill: parent
        visible: root.statusState !== "ready"
        radius: 6
        color: root._palette("panel_bg", "#1f2431")
        border.color: root._palette("border", "#3a4355")
        border.width: 1

        Column {
            anchors.centerIn: parent
            width: parent.width - 32
            spacing: 8

            Text {
                objectName: "jupyterNotebookStatusTitle"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.statusState === "server_starting" ? "Jupyter Notebook" : "Jupyter Notebook"
                color: root._palette("panel_title_fg", "#eef3ff")
                font.pixelSize: 13
                font.bold: true
            }

            Text {
                objectName: "jupyterNotebookStatusMessage"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: root.statusMessage
                color: root.statusState === "error"
                    ? root._palette("error", "#d94f4f")
                    : root._palette("muted_fg", "#95a0b8")
                font.pixelSize: 11
            }

            Rectangle {
                objectName: "jupyterNotebookCreateButton"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.statusState === "no_notebook"
                width: createLabel.implicitWidth + 28
                height: 28
                radius: 6
                color: createButtonArea.containsMouse
                    ? root._palette("accent", "#2c3346")
                    : root._palette("input_bg", "#262c3b")
                border.color: root._palette("input_border", "#3a4355")
                border.width: 1

                Text {
                    id: createLabel
                    anchors.centerIn: parent
                    text: "＋  New notebook"
                    color: root._palette("panel_title_fg", "#eef3ff")
                    font.pixelSize: 11
                }

                MouseArea {
                    id: createButtonArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root._createBlankNotebook()
                }
            }
        }
    }
}
