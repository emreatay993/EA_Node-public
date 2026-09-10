import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common

Item {
    id: root
    property Item edgeLayer: null
    property bool inputEnabled: true
    property bool wireSelectionModeHeld: false
    property string hoveredEdgeId: ""
    property real hoverX: 0.0
    property real hoverY: 0.0
    readonly property string hoveredEdgeTooltipText: root.edgeLayer && root.edgeLayer.edgeTooltipText
        ? root.edgeLayer.edgeTooltipText(root.hoveredEdgeId)
        : ""

    onWireSelectionModeHeldChanged: {
        if (root.wireSelectionModeHeld)
            root.hoveredEdgeId = "";
    }

    signal edgeClicked(string edgeId, bool additive)
    signal edgeDoubleClicked(string edgeId)
    signal edgeContextRequested(string edgeId, real screenX, real screenY)

    MouseArea {
        id: edgeHitMouse
        anchors.fill: parent
        enabled: root.inputEnabled && !root.wireSelectionModeHeld
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        propagateComposedEvents: true

        onPositionChanged: function(mouse) {
            root.hoverX = mouse.x;
            root.hoverY = mouse.y;
            root.hoveredEdgeId = root.edgeLayer && root.edgeLayer.edgeAtScreen
                ? root.edgeLayer.edgeAtScreen(mouse.x, mouse.y)
                : "";
        }

        onExited: root.hoveredEdgeId = ""

        onPressed: function(mouse) {
            var edgeId = root.edgeLayer && root.edgeLayer.edgeAtScreen ? root.edgeLayer.edgeAtScreen(mouse.x, mouse.y) : "";
            if (!edgeId) {
                mouse.accepted = false;
                return;
            }
            var additive = Boolean((mouse.modifiers & Qt.ControlModifier) || (mouse.modifiers & Qt.ShiftModifier));
            if (mouse.button === Qt.LeftButton)
                root.edgeClicked(edgeId, additive);
            else if (mouse.button === Qt.RightButton)
                root.edgeContextRequested(edgeId, mouse.x, mouse.y);
            mouse.accepted = true;
        }

        onDoubleClicked: function(mouse) {
            if (mouse.button !== Qt.LeftButton) {
                mouse.accepted = false;
                return;
            }
            var edgeId = root.edgeLayer && root.edgeLayer.edgeAtScreen ? root.edgeLayer.edgeAtScreen(mouse.x, mouse.y) : "";
            if (!edgeId) {
                mouse.accepted = false;
                return;
            }
            root.edgeDoubleClicked(edgeId);
            mouse.accepted = true;
        }
    }

    Item {
        id: edgePreviewAnchor
        x: root.hoverX
        y: root.hoverY
        width: 1
        height: 1

        Common.ManagedToolTip {
            objectName: "graphEdgeValuePreviewToolTip"
            popupType: Popup.Item
            policyBridge: root.edgeLayer ? root.edgeLayer.sceneBridge : null
            category: "general"
            active: root.hoveredEdgeId.length > 0
            text: root.hoveredEdgeTooltipText
            delay: 400
            maximumTextWidth: 360
            font.family: "monospace"
            font.pixelSize: 12
            screenStablePositioning: true
            screenStablePlacement: "below"
            screenGap: 6
        }
    }
}
