import QtQuick 2.15
import QtQuick.Window 2.15

Window {
    id: root
    objectName: "webPageDetachedWindow"
    property var payload: ({})
    property var themePalette: ({})
    property var browserStateBridge: null
    property var sourceWebPageHost: null
    property string initialUrl: ""
    property bool borrowedActive: false
    property bool standaloneMode: false
    readonly property bool standaloneHostActive: standaloneHostLoader.active
    signal detachedClosed()

    width: 1100
    height: 760
    minimumWidth: 640
    minimumHeight: 420
    title: String(payload.title || "Web page")
    visible: false

    function openWindow(nextPayload, nextUrl, nextSourceWebPageHost) {
        root._releaseBorrowedHost();
        root.payload = nextPayload || ({});
        root.initialUrl = String(nextUrl || "");
        root.sourceWebPageHost = nextSourceWebPageHost || null;
        if (root.sourceWebPageHost && root.sourceWebPageHost.attachWebEngineToDetached) {
            var nodeId = String(root.payload.node_id || "");
            if (!root.sourceWebPageHost.attachWebEngineToDetached(borrowedViewport, nodeId)) {
                root.sourceWebPageHost = null;
                root.borrowedActive = false;
                root.standaloneMode = false;
                root.visible = false;
                return false;
            }
            root.borrowedActive = true;
            root.standaloneMode = false;
        } else {
            root.borrowedActive = false;
            root.standaloneMode = true;
        }
        root.visible = true;
        root.raise();
        root.requestActivate();
        return true;
    }

    function _releaseBorrowedHost() {
        var host = root.sourceWebPageHost;
        var wasBorrowed = root.borrowedActive;
        root.borrowedActive = false;
        root.standaloneMode = false;
        root.sourceWebPageHost = null;
        if (!wasBorrowed || !host || !host.releaseDetachedWebEngine)
            return false;
        return Boolean(host.releaseDetachedWebEngine());
    }

    function _payloadForDetachedHost() {
        var source = root.payload || ({});
        var copy = {};
        for (var key in source)
            copy[key] = source[key];
        if (root.initialUrl.length > 0) {
            copy.current_location = root.initialUrl;
            copy.navigation_decision = {
                "allowed": true,
                "target_url": root.initialUrl,
                "reason": "",
                "access_profile": String(source.access_profile || "standard_browser"),
                "original_location": root.initialUrl,
                "scheme": root.initialUrl.indexOf("file:") === 0 ? "file" : "",
                "origin": root.initialUrl.indexOf("file:") === 0 ? "file://" : "",
                "is_local": root.initialUrl.indexOf("file:") === 0,
                "qwebchannel_allowed": false
            };
        }
        return copy;
    }

    onClosing: {
        root._releaseBorrowedHost();
        root.detachedClosed();
    }

    Component.onDestruction: root._releaseBorrowedHost()

    Item {
        id: borrowedViewport
        objectName: "webPageDetachedBorrowedViewport"
        anchors.fill: parent
        visible: root.borrowedActive
        clip: true
    }

    Loader {
        id: standaloneHostLoader
        objectName: "webPageDetachedStandaloneHostLoader"
        anchors.fill: parent
        active: root.visible && root.standaloneMode
        sourceComponent: Component {
            WebPageHost {
                objectName: "webPageDetachedHost"
                anchors.fill: parent
                payload: root._payloadForDetachedHost()
                themePalette: root.themePalette
                browserStateBridge: root.browserStateBridge
                surfaceMode: "detached"
            }
        }
    }
}
