import QtQuick 2.15

Item {
    id: root
    property Item host: null
    property var _impl: null
    readonly property bool proxySurfaceActive: _impl ? Boolean(_impl.proxySurfaceActive) : false
    readonly property bool liveSurfaceActive: _impl ? Boolean(_impl.liveSurfaceActive) : false
    readonly property bool blocksHostInteraction: _impl ? Boolean(_impl.blocksHostInteraction) : false
    readonly property var embeddedInteractiveRects: _impl && _impl.embeddedInteractiveRects !== undefined && _impl.embeddedInteractiveRects !== null ? _impl.embeddedInteractiveRects : []
    readonly property var viewerInteractiveRects: _impl && _impl.viewerInteractiveRects !== undefined && _impl.viewerInteractiveRects !== null ? _impl.viewerInteractiveRects : []
    readonly property var viewerBridgeBinding: _impl && _impl.viewerBridgeBinding !== undefined && _impl.viewerBridgeBinding !== null ? _impl.viewerBridgeBinding : ({})
    readonly property var viewerSurfaceContract: _impl && _impl.viewerSurfaceContract !== undefined && _impl.viewerSurfaceContract !== null ? _impl.viewerSurfaceContract : (host && host.nodeData && host.nodeData.viewer_surface ? host.nodeData.viewer_surface : ({}))
    readonly property var surfaceActions: _impl && _impl.surfaceActions !== undefined && _impl.surfaceActions !== null ? _impl.surfaceActions : []
    implicitHeight: _impl ? Number(_impl.implicitHeight || 0) : 0

    function dispatchSurfaceAction(actionId) {
        if (_impl && _impl.dispatchSurfaceAction)
            return Boolean(_impl.dispatchSurfaceAction(actionId));
        return false;
    }
    function requestInlineEditAt(localX, localY) { return _impl && _impl.requestInlineEditAt ? Boolean(_impl.requestInlineEditAt(localX, localY)) : false; }
    function commitInlineEditFromExternalInteraction(localX, localY) { return _impl && _impl.commitInlineEditFromExternalInteraction ? Boolean(_impl.commitInlineEditFromExternalInteraction(localX, localY)) : false; }

    Loader {
        id: bodyLoader
        anchors.fill: parent
        source: Qt.resolvedUrl("GraphViewerSurfaceBody.qml")
        onLoaded: {
            if (item) {
                item.host = Qt.binding(function() { return root.host; });
                root._impl = item;
            }
        }
    }
}
