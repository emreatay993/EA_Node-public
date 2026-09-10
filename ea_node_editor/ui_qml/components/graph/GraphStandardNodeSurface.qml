import QtQuick 2.15

Item {
    id: surface
    objectName: "graphNodeStandardSurface"
    property Item host: null
    readonly property bool fullscreenAvailable: !!host && Boolean(host.surfaceFullscreenAvailable)
    readonly property var surfaceActions: {
        var action = host && host.surfaceFullscreenAction
            ? host.surfaceFullscreenAction(surface.fullscreenAvailable, false)
            : null;
        return action ? [action] : [];
    }
    readonly property var embeddedInteractiveRects: inlinePropertiesLayer.embeddedInteractiveRects
    implicitHeight: host ? host.inlineBodyHeight : 0

    GraphInlinePropertiesLayer {
        id: inlinePropertiesLayer
        anchors.fill: parent
        host: surface.host
    }

    function dispatchSurfaceAction(actionId) {
        if (String(actionId || "") === "fullscreen")
            return _requestContentFullscreen();
        return false;
    }

    function _requestContentFullscreen() {
        if (!surface.fullscreenAvailable || !host || !host.requestSurfaceContentFullscreen)
            return false;
        return Boolean(host.requestSurfaceContentFullscreen());
    }
}
