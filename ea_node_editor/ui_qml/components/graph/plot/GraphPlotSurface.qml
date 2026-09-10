import QtQuick 2.15

Item {
    id: root
    property Item host: null
    property var _impl: null
    readonly property bool proxySurfaceActive: _impl ? Boolean(_impl.proxySurfaceActive) : false
    readonly property bool liveSurfaceActive: _impl ? Boolean(_impl.liveSurfaceActive) : false
    readonly property bool blocksHostInteraction: _impl ? Boolean(_impl.blocksHostInteraction) : false
    readonly property var embeddedInteractiveRects: _impl && _impl.embeddedInteractiveRects !== undefined && _impl.embeddedInteractiveRects !== null ? _impl.embeddedInteractiveRects : []
    readonly property var surfaceActions: _impl && _impl.surfaceActions !== undefined && _impl.surfaceActions !== null ? _impl.surfaceActions : []
    implicitHeight: _impl ? Number(_impl.implicitHeight || 0) : 0

    function triggerHoverAction() { if (_impl && _impl.triggerHoverAction) _impl.triggerHoverAction(); }
    function dispatchSurfaceAction(actionId) {
        if (_impl && _impl.dispatchSurfaceAction)
            return Boolean(_impl.dispatchSurfaceAction(actionId));
        return false;
    }
    function requestInlineEditAt(_localX, _localY) { return false; }
    function commitInlineEditFromExternalInteraction(_localX, _localY) { return false; }

    Loader {
        id: bodyLoader
        anchors.fill: parent
        source: Qt.resolvedUrl("GraphPlotSurfaceBody.qml")
        onLoaded: {
            if (item) {
                item.host = Qt.binding(function() { return root.host; });
                root._impl = item;
            }
        }
    }
}
