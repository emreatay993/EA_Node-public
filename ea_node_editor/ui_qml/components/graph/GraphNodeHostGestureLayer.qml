import QtQuick 2.15

Item {
    id: root
    objectName: "graphNodeHostGestureLayer"
    property Item host: null
    readonly property bool dragActive: nodeDragArea.manualDragActive
    readonly property bool containsMouse: nodeDragArea.containsMouse
    readonly property bool pointerInteractionActive: nodeDragArea.pressed || nodeDragArea.manualDragActive
    z: 1.5

    MouseArea {
        id: nodeDragArea
        objectName: "graphNodeDragArea"
        anchors.fill: parent
        enabled: root.host ? !root.host.surfaceInteractionLocked : false
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: true
        cursorShape: root.host && root.host.surfaceInteractionLocked
            ? Qt.ArrowCursor
            : (manualDragActive ? Qt.ClosedHandCursor : (hostDragCursorSuppressed ? Qt.ArrowCursor : Qt.OpenHandCursor))
        drag.target: null
        drag.axis: Drag.XAndYAxis
        propagateComposedEvents: true
        property bool dragMoved: false
        property bool manualDragActive: false
        property bool suppressNextClick: false
        property real pressPointerX: 0.0
        property real pressPointerY: 0.0
        property real lastDragDx: 0.0
        property real lastDragDy: 0.0
        property bool edgePressHandled: false
        readonly property bool edgeHoverActive: containsMouse && _edgeAtLocalPosition(mouseX, mouseY).length > 0
        readonly property bool surfaceClaimHoverActive: containsMouse
            && !!root.host
            && !!root.host._surfaceClaimsBodyInteractionAt
            && root.host._surfaceClaimsBodyInteractionAt(mouseX, mouseY)
        readonly property bool hostDragCursorSuppressed: edgeHoverActive || surfaceClaimHoverActive

        function _resetDragMotionState() {
            dragMoved = false;
            manualDragActive = false;
            lastDragDx = 0.0;
            lastDragDy = 0.0;
        }

        function _dragThreshold() {
            var threshold = Number(drag.threshold);
            return isFinite(threshold) && threshold > 0.0 ? threshold : 4.0;
        }

        function _pointerPoint(mouse) {
            var coordinateItem = root.host ? root.host.parent : null;
            if (coordinateItem && nodeDragArea.mapToItem) {
                var mapped = nodeDragArea.mapToItem(coordinateItem, mouse.x, mouse.y);
                return {"x": Number(mapped.x), "y": Number(mapped.y)};
            }
            return {"x": Number(mouse.x), "y": Number(mouse.y)};
        }

        function _pointerInCanvasAt(localX, localY) {
            if (!root.host || !root.host.edgeHitPassthroughEnabled || !root.host.canvasItem)
                return null;
            if (root.host._pointerInCanvas)
                return root.host._pointerInCanvas(nodeDragArea, {"x": localX, "y": localY});
            if (nodeDragArea.mapToItem)
                return nodeDragArea.mapToItem(root.host.canvasItem, localX, localY);
            return {"x": Number(localX), "y": Number(localY)};
        }

        function _edgeAtLocalPosition(localX, localY) {
            if (!root.host || !root.host.edgeHitPassthroughEnabled || !root.host.canvasItem)
                return "";
            if (!root.host.canvasItem.edgeAtScreen)
                return "";
            var pointerPos = _pointerInCanvasAt(localX, localY);
            if (!pointerPos)
                return "";
            return String(root.host.canvasItem.edgeAtScreen(pointerPos.x, pointerPos.y) || "");
        }

        function _handleEdgePress(mouse) {
            if (!mouse || (mouse.button !== Qt.LeftButton && mouse.button !== Qt.RightButton))
                return false;
            if (!root.host || !root.host.canvasItem || !root.host.canvasItem.handleEdgePressAtScreen)
                return false;
            var pointerPos = _pointerInCanvasAt(mouse.x, mouse.y);
            if (!pointerPos)
                return false;
            return Boolean(root.host.canvasItem.handleEdgePressAtScreen(
                pointerPos.x,
                pointerPos.y,
                mouse.button,
                mouse.modifiers
            ));
        }

        function _emitDragOffset(mouse, force) {
            var pointerPoint = _pointerPoint(mouse);
            var dx = Number(pointerPoint.x) - pressPointerX;
            var dy = Number(pointerPoint.y) - pressPointerY;
            if (!isFinite(dx))
                dx = 0.0;
            if (!isFinite(dy))
                dy = 0.0;
            if (!force && !dragMoved && Math.max(Math.abs(dx), Math.abs(dy)) < _dragThreshold())
                return false;
            dragMoved = true;
            manualDragActive = true;
            lastDragDx = dx;
            lastDragDy = dy;
            root.host.dragOffsetChanged(root.host.nodeData.node_id, dx, dy);
            return true;
        }

        onPressed: function(mouse) {
            if (!root.host || !root.host.nodeData)
                return;
            _resetDragMotionState();
            suppressNextClick = false;
            edgePressHandled = false;
            if (root.host.commitInlineTitleEditAt)
                root.host.commitInlineTitleEditAt(mouse.x, mouse.y);
            if (root.host._surfaceClaimsBodyInteractionAt(mouse.x, mouse.y)) {
                mouse.accepted = true;
                return;
            }
            if (_handleEdgePress(mouse)) {
                edgePressHandled = true;
                suppressNextClick = true;
                mouse.accepted = true;
                return;
            }
            if (mouse.button === Qt.RightButton) {
                root.host.nodeContextRequested(root.host.nodeData.node_id, mouse.x, mouse.y);
                mouse.accepted = true;
                return;
            }
            if (mouse.button !== Qt.LeftButton)
                return;
            var pointerPoint = _pointerPoint(mouse);
            pressPointerX = Number(pointerPoint.x);
            pressPointerY = Number(pointerPoint.y);
        }

        onClicked: function(mouse) {
            if (!root.host || !root.host.nodeData || mouse.button !== Qt.LeftButton)
                return;
            if (suppressNextClick) {
                suppressNextClick = false;
                mouse.accepted = true;
                return;
            }
            if (root.host._surfaceClaimsBodyInteractionAt(mouse.x, mouse.y)) {
                mouse.accepted = true;
                return;
            }
            var additive = Boolean((mouse.modifiers & Qt.ControlModifier) || (mouse.modifiers & Qt.ShiftModifier));
            root.host.nodeClicked(root.host.nodeData.node_id, additive);
        }

        onDoubleClicked: function(mouse) {
            if (!root.host || !root.host.nodeData || mouse.button !== Qt.LeftButton)
                return;
            if (root.host._surfaceClaimsBodyInteractionAt(mouse.x, mouse.y)) {
                mouse.accepted = true;
                return;
            }
            if (root.host.requestInlineTitleEditAt && root.host.requestInlineTitleEditAt(mouse.x, mouse.y)) {
                mouse.accepted = true;
                return;
            }
            root.host.nodeOpenRequested(root.host.nodeData.node_id);
        }

        onPositionChanged: {
            if (!root.host || !root.host.nodeData || !pressed)
                return;
            if (edgePressHandled)
                return;
            if ((pressedButtons & Qt.LeftButton) === 0)
                return;
            _emitDragOffset(mouse, false);
        }

        onReleased: function(mouse) {
            if (!root.host || !root.host.nodeData)
                return;
            if (edgePressHandled) {
                edgePressHandled = false;
                suppressNextClick = true;
                _resetDragMotionState();
                mouse.accepted = true;
                return;
            }
            if (mouse.button !== Qt.LeftButton)
                return;
            var moved = dragMoved;
            if (!moved && root.host._surfaceClaimsBodyInteractionAt(mouse.x, mouse.y)) {
                _resetDragMotionState();
                mouse.accepted = true;
                return;
            }
            if (moved)
                _emitDragOffset(mouse, true);
            var baseX = Number(root.host.nodeData.x);
            var baseY = Number(root.host.nodeData.y);
            if (!isFinite(baseX))
                baseX = 0.0;
            if (!isFinite(baseY))
                baseY = 0.0;
            root.host.dragFinished(
                root.host.nodeData.node_id,
                baseX + (moved ? lastDragDx : 0.0),
                baseY + (moved ? lastDragDy : 0.0),
                moved
            );
            suppressNextClick = moved;
            _resetDragMotionState();
        }

        onCanceled: {
            if (!root.host || !root.host.nodeData)
                return;
            edgePressHandled = false;
            root.host.dragCanceled(root.host.nodeData.node_id);
            suppressNextClick = false;
            _resetDragMotionState();
        }
    }
}
