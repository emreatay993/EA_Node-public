import QtQuick 2.15
import QtQml 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

QtObject {
    id: root
    property Item host: null
    property Item targetItem: null
    property bool enabled: true
    readonly property var interactiveRect: enabled
        ? SurfaceControlGeometry.rectFromItem(targetItem, host)
        : null
    readonly property var embeddedInteractiveRects: enabled
        ? SurfaceControlGeometry.rectList(interactiveRect)
        : []

    signal controlStarted()

    function beginControl() {
        if (enabled)
            controlStarted();
    }
}
