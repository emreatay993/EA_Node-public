import QtQuick 2.15

Item {
    id: root
    objectName: "graphCanvasEdgeScenegraphLayer"
    property Item edgeLayer: null
    readonly property bool rendererSupported: false
    property real profileLastPaintMs: 0.0
    property int profilePaintCount: 0
    readonly property string fallbackReason: "native_scenegraph_renderer_unavailable"

    function requestScenegraphPaint() {
        root.profileLastPaintMs = 0.0;
        root.profilePaintCount += 1;
    }
}
