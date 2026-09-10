import QtQuick 2.15
import QtQml 2.15

Item {
    id: root
    property Item canvasItem: null
    property var sceneStateBridge: null
    property var viewStateBridge: null
    property var sceneState: null
    property var interactionState: null
    property var viewportController: null
    property var edgeLayerItem: null
    property var frameScheduler: null
    visible: false
    width: 0
    height: 0

    function requestEdgeRedraw() {
        if (root.frameScheduler && root.frameScheduler.requestEdgeRedraw) {
            root.frameScheduler.requestEdgeRedraw();
            return;
        }
        if (root.edgeLayerItem && root.edgeLayerItem.requestRedraw)
            root.edgeLayerItem.requestRedraw();
    }

    function _clearTransientSceneState() {
        if (root.sceneState) {
            if (root.sceneState.clearLiveDragOffset)
                root.sceneState.clearLiveDragOffset();
            if (root.sceneState.clearLiveNodeGeometry)
                root.sceneState.clearLiveNodeGeometry();
            else if (root.sceneState.liveNodeGeometry && Object.keys(root.sceneState.liveNodeGeometry).length > 0)
                root.sceneState.liveNodeGeometry = ({});
        }
        if (root.interactionState && root.interactionState._clearWireDragState)
            root.interactionState._clearWireDragState();
        if (root.interactionState && root.interactionState.clearLibraryDropPreview)
            root.interactionState.clearLibraryDropPreview();
    }

    function handleSceneMutation() {
        root._clearTransientSceneState();
        if (root.sceneState && root.sceneState.syncEdgePayload)
            root.sceneState.syncEdgePayload();
    }

    function handleNodeOnlySceneMutation() {
        root._clearTransientSceneState();
    }

    function resetCanvasSceneState() {
        if (root.sceneState) {
            if (root.sceneState.clearLiveDragOffset)
                root.sceneState.clearLiveDragOffset();
            root.sceneState.liveNodeGeometry = ({});
            if (root.sceneState.syncEdgePayload)
                root.sceneState.syncEdgePayload();
        }
        if (root.interactionState && root.interactionState.resetSceneBridgeState)
            root.interactionState.resetSceneBridgeState();
    }

    Connections {
        target: root.sceneStateBridge
        ignoreUnknownSignals: true

        function onScene_edges_changed() {
            root.handleSceneMutation();
        }

        function onScene_nodes_changed() {
            root.handleNodeOnlySceneMutation();
        }

        function onEdges_changed() {
            root.handleSceneMutation();
        }

        function onNodes_changed() {
            root.handleNodeOnlySceneMutation();
        }

        function onScene_workspace_changed() {
            root.resetCanvasSceneState();
        }
    }

    Connections {
        target: root.viewStateBridge
        ignoreUnknownSignals: true

        function onView_state_changed() {
            if (root.viewportController && root.viewportController.requestViewStateRedraw)
                root.viewportController.requestViewStateRedraw();
        }
    }
}
