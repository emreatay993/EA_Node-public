import QtQuick 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    property Item host: null
    property Item targetItem: null
    property bool hoverEnabled: false
    property int cursorShape: Qt.ArrowCursor
    readonly property var interactiveRect: enabled
        ? SurfaceControlGeometry.rectFromItem(targetItem, host)
        : null
    readonly property var localInteractiveRect: enabled
        ? SurfaceControlGeometry.rectFromItem(targetItem, root.parent)
        : null
    readonly property var embeddedInteractiveRects: enabled
        ? SurfaceControlGeometry.rectList(interactiveRect)
        : []

    signal singleClicked(real localX, real localY)
    signal doubleClicked(real localX, real localY)
    signal hoverMoved(real localX, real localY)
    signal hoverExited()

    x: localInteractiveRect ? localInteractiveRect.x : 0
    y: localInteractiveRect ? localInteractiveRect.y : 0
    width: localInteractiveRect ? localInteractiveRect.width : 0
    height: localInteractiveRect ? localInteractiveRect.height : 0
    visible: enabled && localInteractiveRect !== null

    MouseArea {
        anchors.fill: parent
        enabled: root.enabled
        acceptedButtons: Qt.LeftButton
        hoverEnabled: root.hoverEnabled
        cursorShape: root.cursorShape
        propagateComposedEvents: false

        onPositionChanged: function(mouse) {
            root.hoverMoved(mouse.x, mouse.y);
        }

        onExited: {
            root.hoverExited();
        }

        onClicked: function(mouse) {
            root.singleClicked(mouse.x, mouse.y);
        }

        onDoubleClicked: function(mouse) {
            root.doubleClicked(mouse.x, mouse.y);
            mouse.accepted = true;
        }
    }
}
