import QtQuick 2.15

Item {
    id: root
    objectName: "graphCanvasInputLayers"
    property Item canvasItem: null
    property var canvasActionRouter: null
    property var graphActionBridge: null
    property var canvasCommandBridge: null
    property var sceneCommandBridge: null
    property var viewStateBridge: null
    property var viewCommandBridge: null
    readonly property var shellContextRef: typeof shellContext !== "undefined" ? shellContext : null
    readonly property var contentFullscreenBridgeRef: root.shellContextRef
        ? root.shellContextRef.contentFullscreenBridge
        : null
    readonly property var viewerSessionBridgeRef: root.shellContextRef
        ? root.shellContextRef.viewerSessionBridge
        : null
    readonly property var shellLibraryBridgeRef: root.shellContextRef
        ? root.shellContextRef.shellLibraryBridge
        : null
    property var themePalette: ({})
    property real boxZoomDragThreshold: 4
    property real boxZoomPaddingPx: 24
    property bool wireSelectionModeHeld: false

    function _frameScheduler() {
        return root.canvasItem && root.canvasItem.frameSchedulerRef
            ? root.canvasItem.frameSchedulerRef
            : null;
    }

    function _wheelDeltaY(eventObj) {
        if (!eventObj)
            return 0.0;
        if (root.canvasItem && root.canvasItem._wheelDeltaY)
            return Number(root.canvasItem._wheelDeltaY(eventObj));
        var delta = 0.0;
        if (eventObj.angleDelta && Number(eventObj.angleDelta.y) !== 0)
            delta = Number(eventObj.angleDelta.y);
        else if (eventObj.pixelDelta && Number(eventObj.pixelDelta.y) !== 0)
            delta = Number(eventObj.pixelDelta.y) * 0.5;
        if (eventObj.inverted)
            delta = -delta;
        return delta;
    }

    function _plainKeyEvent(eventObj) {
        if (!eventObj)
            return false;
        return (eventObj.modifiers & (
            Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier
        )) === 0;
    }

    function _flushFrameScheduler() {
        var scheduler = root._frameScheduler();
        if (scheduler && scheduler.flushPendingRedraws)
            scheduler.flushPendingRedraws();
    }

    function _optionalPortFilterBridge() {
        if (root.canvasItem && root.canvasItem.sceneBridge && root.canvasItem.sceneBridge.set_hide_optional_ports)
            return root.canvasItem.sceneBridge;
        if (root.sceneCommandBridge && root.sceneCommandBridge.set_hide_optional_ports)
            return root.sceneCommandBridge;
        return null;
    }

    function _toggleHideOptionalPorts() {
        var bridge = root._optionalPortFilterBridge();
        if (!bridge || !root.canvasItem || !bridge.set_hide_optional_ports)
            return false;
        return Boolean(bridge.set_hide_optional_ports(!Boolean(root.canvasItem.prefs && root.canvasItem.prefs.hideOptionalPorts)));
    }

    function _closeCommentPeekIfActive() {
        if (root.canvasActionRouter && root.canvasActionRouter.closeCommentPeekIfActive)
            return Boolean(root.canvasActionRouter.closeCommentPeekIfActive());
        if (root._triggerGraphAction("close_comment_peek", ({})))
            return true;
        if (!root.canvasCommandBridge || !root.canvasCommandBridge.request_close_comment_peek)
            return false;
        return Boolean(root.canvasCommandBridge.request_close_comment_peek());
    }

    function _triggerGraphAction(actionId, payload) {
        if (root.canvasActionRouter && root.canvasActionRouter.triggerGraphAction)
            return Boolean(root.canvasActionRouter.triggerGraphAction(actionId, payload || ({})));
        if (!root.graphActionBridge || !root.graphActionBridge.trigger_graph_action)
            return false;
        return Boolean(root.graphActionBridge.trigger_graph_action(String(actionId || ""), payload || ({})));
    }

    function _handleContentFullscreenShortcut() {
        return root.canvasActionRouter && root.canvasActionRouter.handleContentFullscreenShortcut
            ? Boolean(root.canvasActionRouter.handleContentFullscreenShortcut())
            : false;
    }

    function _handleHidePortChord(buttons, changedButton) {
        var normalizedButtons = Number(buttons || 0);
        if (!(normalizedButtons & Qt.MiddleButton))
            return false;
        if (changedButton === Qt.RightButton)
            return root._toggleHideOptionalPorts();
        if (changedButton === Qt.MiddleButton) {
            if (normalizedButtons & Qt.RightButton)
                return root._toggleHideOptionalPorts();
        }
        return false;
    }

    Keys.onDeletePressed: function(event) {
        if (root.canvasItem) {
            var edgeIds = root.canvasItem.selectedEdgeIds || [];
            var deleted = root.canvasActionRouter && root.canvasActionRouter.deleteSelection
                ? Boolean(root.canvasActionRouter.deleteSelection(edgeIds))
                : root._triggerGraphAction("delete_selection", { "edge_ids": edgeIds });
            if (!deleted && root.canvasCommandBridge && root.canvasCommandBridge.request_delete_selected_graph_items) {
                root.canvasCommandBridge.request_delete_selected_graph_items(edgeIds);
            }
        }
        if (root.canvasItem) {
            root.canvasItem.selectedEdgeIds = [];
            root.canvasItem.clearPendingConnection();
            root.canvasItem._closeContextMenus();
        }
        event.accepted = true;
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_W
                && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) {
            root.wireSelectionModeHeld = true;
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_F11) {
            if (root._handleContentFullscreenShortcut())
                event.accepted = true;
            return;
        }
        if (!root.canvasItem)
            return;
        if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_E) {
            if (root.canvasItem.toggleSelectedEdgesEnabled)
                root.canvasItem.toggleSelectedEdgesEnabled("");
            event.accepted = true;
            return;
        }
        if ((event.modifiers & Qt.ControlModifier)
                && !(event.modifiers & (Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier))
                && (event.key === Qt.Key_Left || event.key === Qt.Key_Right)) {
            var endpoint = event.key === Qt.Key_Right ? "target" : "source";
            var jumpedToEndpoint = root.canvasActionRouter
                && root.canvasActionRouter.jumpToSelectedEdgeEndpoint
                ? Boolean(root.canvasActionRouter.jumpToSelectedEdgeEndpoint(endpoint))
                : false;
            if (jumpedToEndpoint) {
                event.accepted = true;
                return;
            }
            event.accepted = false;
        }
        if ((event.key === Qt.Key_Left || event.key === Qt.Key_Right) && root._plainKeyEvent(event)) {
            var navigatedPdfPage = root.canvasActionRouter && root.canvasActionRouter.navigateSelectedPdfPage
                ? Boolean(root.canvasActionRouter.navigateSelectedPdfPage(event.key === Qt.Key_Right ? 1 : -1))
                : false;
            if (navigatedPdfPage) {
                event.accepted = true;
                return;
            }
        }
        if ((event.modifiers & Qt.AltModifier) && event.key === Qt.Key_Left) {
            var navigatedParent = root.canvasActionRouter && root.canvasActionRouter.navigateScopeParent
                ? Boolean(root.canvasActionRouter.navigateScopeParent())
                : root._triggerGraphAction("navigate_scope_parent", ({}));
            if (!navigatedParent
                    && !(root.canvasActionRouter && root.canvasActionRouter.navigateScopeParent)
                    && root.canvasCommandBridge
                    && root.canvasCommandBridge.request_navigate_scope_parent) {
                navigatedParent = root.canvasCommandBridge.request_navigate_scope_parent();
            }
            if (navigatedParent) {
                root.canvasItem.clearEdgeSelection();
                root.canvasItem.clearPendingConnection();
                root.canvasItem._closeContextMenus();
            }
            event.accepted = true;
            return;
        }
        if ((event.modifiers & Qt.AltModifier) && event.key === Qt.Key_Home) {
            var navigatedRoot = root.canvasActionRouter && root.canvasActionRouter.navigateScopeRoot
                ? Boolean(root.canvasActionRouter.navigateScopeRoot())
                : root._triggerGraphAction("navigate_scope_root", ({}));
            if (!navigatedRoot
                    && !(root.canvasActionRouter && root.canvasActionRouter.navigateScopeRoot)
                    && root.canvasCommandBridge
                    && root.canvasCommandBridge.request_navigate_scope_root) {
                navigatedRoot = root.canvasCommandBridge.request_navigate_scope_root();
            }
            if (navigatedRoot) {
                root.canvasItem.clearEdgeSelection();
                root.canvasItem.clearPendingConnection();
                root.canvasItem._closeContextMenus();
            }
            event.accepted = true;
        }
    }

    Keys.onReleased: function(event) {
        if (event.key !== Qt.Key_W)
            return;
        root.wireSelectionModeHeld = false;
        event.accepted = true;
    }

    Keys.onEscapePressed: function(event) {
        if (!root.canvasItem)
            return;
        var handled = false;
        if (root.canvasItem.cancelNodeLinkTargetPick && root.canvasItem.cancelNodeLinkTargetPick())
            handled = true;
        if (root.canvasItem.cancelWireDrag())
            handled = true;
        if (root.canvasItem.pendingConnectionPort) {
            root.canvasItem.clearPendingConnection();
            handled = true;
        }
        if (
            root.canvasItem.edgeContextVisible
            || root.canvasItem.nodeContextVisible
            || root.canvasItem.selectionContextVisible
            || root.canvasItem.canvasOptionsVisible
        ) {
            root.canvasItem._closeContextMenus();
            handled = true;
        }
        if (root._closeCommentPeekIfActive())
            handled = true;
        if (handled)
            event.accepted = true;
    }

    MouseArea {
        id: marqueeArea
        objectName: "graphCanvasMarqueeArea"
        anchors.fill: parent
        z: -9
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: false
        property bool selecting: false
        property bool additive: false
        property string marqueeMode: ""
        property real startX: 0
        property real startY: 0
        property real currentX: 0
        property real currentY: 0
        property var edgeSelectionBaseline: []

        function resetGestureState() {
            selecting = false;
            additive = false;
            marqueeMode = "";
            edgeSelectionBaseline = [];
        }

        function updateEdgeSelection() {
            if (!root.canvasItem || marqueeMode !== "edge_selection")
                return;
            var left = Math.min(startX, currentX);
            var top = Math.min(startY, currentY);
            var width = Math.abs(currentX - startX);
            var height = Math.abs(currentY - startY);
            var intersected = root.canvasItem.edgeIdsIntersectingScreenRect
                ? root.canvasItem.edgeIdsIntersectingScreenRect(left, top, width, height)
                : [];
            root.canvasItem.setEdgeSelection(
                additive ? edgeSelectionBaseline.concat(intersected || []) : intersected,
                false
            );
        }

        onPressed: function(mouse) {
            if (!root.canvasItem)
                return;
            root.canvasItem.forceActiveFocus();
            if (
                (mouse.button === Qt.LeftButton || mouse.button === Qt.RightButton)
                && root._closeCommentPeekIfActive()
            ) {
                resetGestureState();
                mouse.accepted = true;
                return;
            }
            if (root._handleHidePortChord(mouse.buttons, mouse.button)) {
                resetGestureState();
                panArea.cancelPanningForChord();
                mouse.accepted = true;
                return;
            }
            startX = mouse.x;
            startY = mouse.y;
            currentX = mouse.x;
            currentY = mouse.y;
            if (mouse.button === Qt.LeftButton) {
                root.canvasItem._closeContextMenus();
                root.canvasItem.clearPendingConnection();
                selecting = true;
                marqueeMode = root.wireSelectionModeHeld ? "edge_selection" : "selection";
                additive = marqueeMode === "edge_selection"
                    ? Boolean(mouse.modifiers & Qt.ShiftModifier)
                    : Boolean((mouse.modifiers & Qt.ControlModifier) || (mouse.modifiers & Qt.ShiftModifier));
                edgeSelectionBaseline = additive
                    ? root.canvasItem._normalizeEdgeIds(root.canvasItem.selectedEdgeIds || [])
                    : [];
                if (marqueeMode === "edge_selection" && !additive) {
                    if (root.sceneCommandBridge && root.sceneCommandBridge.clear_selection)
                        root.sceneCommandBridge.clear_selection();
                    root.canvasItem.setEdgeSelection([], false);
                }
                return;
            }
            if (mouse.button === Qt.RightButton) {
                root.canvasItem._closeContextMenus();
                root.canvasItem.clearPendingConnection();
                selecting = true;
                marqueeMode = "zoom";
                additive = false;
            }
        }

        onPositionChanged: function(mouse) {
            if (!selecting)
                return;
            currentX = mouse.x;
            currentY = mouse.y;
            if (marqueeMode === "edge_selection")
                updateEdgeSelection();
            if (
                marqueeMode === "zoom"
                && root.canvasItem
                && (Math.abs(currentX - startX) >= 2 || Math.abs(currentY - startY) >= 2)
            ) {
                if (!root.canvasItem.viewportInteractionHeld)
                    root.canvasItem.beginViewportInteraction();
                root.canvasItem.noteViewportInteraction();
            }
        }

        onReleased: function(mouse) {
            var zoomGestureActive = marqueeMode === "zoom";
            if (!selecting) {
                resetGestureState();
                return;
            }
            currentX = mouse.x;
            currentY = mouse.y;
            var dx = Math.abs(currentX - startX);
            var dy = Math.abs(currentY - startY);
            if (marqueeMode === "edge_selection" && root.canvasItem) {
                if (dx >= 4 || dy >= 4)
                    updateEdgeSelection();
            } else if (marqueeMode === "selection" && root.sceneCommandBridge && root.canvasItem) {
                if (dx >= 4 || dy >= 4) {
                    root.sceneCommandBridge.select_nodes_in_rect(
                        root.canvasItem.screenToSceneX(startX),
                        root.canvasItem.screenToSceneY(startY),
                        root.canvasItem.screenToSceneX(currentX),
                        root.canvasItem.screenToSceneY(currentY),
                        additive
                    );
                    if (!additive)
                        root.canvasItem.clearEdgeSelection();
                } else if (!additive) {
                    root.sceneCommandBridge.clear_selection();
                    root.canvasItem.clearEdgeSelection();
                }
            } else if (zoomGestureActive && root.canvasItem) {
                var openContextMenu = dx < root.boxZoomDragThreshold
                    && dy < root.boxZoomDragThreshold;
                if (openContextMenu && root.canvasItem.selectedNodeIds().length > 1) {
                    if (root.canvasItem.interactionActive)
                        root.canvasItem.finishViewportInteractionSoon();
                    root.canvasItem._openSelectionContextAtScene(
                        root.canvasItem.screenToSceneX(currentX),
                        root.canvasItem.screenToSceneY(currentY)
                    );
                } else if (openContextMenu) {
                    if (root.canvasItem.interactionActive)
                        root.canvasItem.finishViewportInteractionSoon();
                    root.canvasItem._openCanvasOptionsAtScene(
                        root.canvasItem.screenToSceneX(currentX),
                        root.canvasItem.screenToSceneY(currentY)
                    );
                } else {
                    root.canvasItem.noteViewportInteraction();
                    if (dx >= root.boxZoomDragThreshold && dy >= root.boxZoomDragThreshold) {
                        root.canvasItem.frameScreenRect(
                            startX,
                            startY,
                            currentX,
                            currentY,
                            root.boxZoomPaddingPx
                        );
                    }
                    root.canvasItem.finishViewportInteractionSoon();
                }
            }
            resetGestureState();
        }

        onCanceled: {
            var zoomGestureActive = marqueeMode === "zoom";
            resetGestureState();
            if (zoomGestureActive && root.canvasItem)
                root.canvasItem.finishViewportInteractionSoon();
        }

        onDoubleClicked: function(mouse) {
            resetGestureState();
            if (mouse.button !== Qt.LeftButton)
                return;
            if (!root.canvasItem)
                return;
            if (!root.canvasCommandBridge || !root.canvasCommandBridge.request_open_canvas_quick_insert)
                return;
            var sceneX = root.canvasItem.screenToSceneX(mouse.x);
            var sceneY = root.canvasItem.screenToSceneY(mouse.y);
            var overlayHost = root.canvasItem.overlayHostItem || root.canvasItem;
            var overlayPoint = root.canvasItem.mapToItem(overlayHost, mouse.x, mouse.y);
            root.canvasCommandBridge.request_open_canvas_quick_insert(
                sceneX, sceneY, overlayPoint.x, overlayPoint.y
            );
            mouse.accepted = true;
        }

        onWheel: function(wheel) {
            if (!root.canvasItem)
                return;
            var scheduler = root._frameScheduler();
            if (
                scheduler
                && scheduler.queueWheelZoom
                && root.viewCommandBridge
                && scheduler.queueWheelZoom(
                    root.canvasItem,
                    root.viewCommandBridge,
                    root._wheelDeltaY(wheel),
                    Number(wheel.x),
                    Number(wheel.y)
                )
            ) {
                wheel.accepted = true;
                return;
            }
            if (root.canvasItem.applyWheelZoom(wheel))
                wheel.accepted = true;
        }
    }

    Rectangle {
        objectName: "graphCanvasMarqueeRect"
        parent: root.canvasItem
        visible: marqueeArea.selecting
            && (Math.abs(marqueeArea.currentX - marqueeArea.startX) >= 2
                || Math.abs(marqueeArea.currentY - marqueeArea.startY) >= 2)
        z: 60
        x: Math.min(marqueeArea.startX, marqueeArea.currentX)
        y: Math.min(marqueeArea.startY, marqueeArea.currentY)
        width: Math.abs(marqueeArea.currentX - marqueeArea.startX)
        height: Math.abs(marqueeArea.currentY - marqueeArea.startY)
        color: marqueeArea.marqueeMode === "zoom"
            ? Qt.alpha(root.themePalette.accent, 0.12)
            : (marqueeArea.marqueeMode === "edge_selection"
                ? Qt.rgba(0.27, 0.72, 0.82, 0.16)
                : Qt.alpha(root.themePalette.accent, 0.2))
        border.width: marqueeArea.marqueeMode === "edge_selection" ? 0 : 1
        border.color: root.themePalette.accent

        Canvas {
            anchors.fill: parent
            visible: marqueeArea.marqueeMode === "edge_selection"
            onVisibleChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                if (!visible || width < 1 || height < 1)
                    return;
                ctx.strokeStyle = "#45B8D2";
                ctx.lineWidth = 1;
                ctx.setLineDash([1, 3]);
                ctx.strokeRect(0.5, 0.5, Math.max(0, width - 1), Math.max(0, height - 1));
            }
        }
    }

    MouseArea {
        id: panArea
        objectName: "graphCanvasPanArea"
        anchors.fill: parent
        z: -10
        acceptedButtons: Qt.MiddleButton
        hoverEnabled: false
        property bool panning: false
        property real lastX: 0
        property real lastY: 0

        function cancelPanningForChord() {
            if (!panning)
                return;
            panning = false;
            if (root.canvasItem)
                root.canvasItem.finishViewportInteractionSoon();
        }

        onPressed: {
            if (root._handleHidePortChord(mouse.buttons, mouse.button)) {
                marqueeArea.resetGestureState();
                panning = false;
                mouse.accepted = true;
                return;
            }
            if (!root.viewStateBridge || !root.viewCommandBridge || !root.viewCommandBridge.pan_by)
                return;
            panning = true;
            lastX = mouse.x;
            lastY = mouse.y;
            if (root.canvasItem)
                root.canvasItem.beginViewportInteraction();
        }

        onPositionChanged: {
            if (!panning || !root.viewStateBridge || !root.viewCommandBridge || !root.viewCommandBridge.pan_by)
                return;
            if (root.canvasItem)
                root.canvasItem.noteViewportInteraction();
            var dx = (mouse.x - lastX) / Math.max(0.1, root.viewStateBridge.zoom_value);
            var dy = (mouse.y - lastY) / Math.max(0.1, root.viewStateBridge.zoom_value);
            var scheduler = root._frameScheduler();
            if (!scheduler || !scheduler.queuePanBy || !scheduler.queuePanBy(root.viewCommandBridge, -dx, -dy))
                root.viewCommandBridge.pan_by(-dx, -dy);
            lastX = mouse.x;
            lastY = mouse.y;
        }

        onReleased: {
            panning = false;
            if (root.canvasItem)
                root.canvasItem.finishViewportInteractionSoon();
        }

        onCanceled: {
            panning = false;
            if (root.canvasItem)
                root.canvasItem.finishViewportInteractionSoon();
        }
    }
}
