import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"
import "components/shell"

Rectangle {
    id: root
    readonly property var shellContextRef: shellContext
    readonly property var shellLibraryBridgeRef: root.shellContextRef.shellLibraryBridge
    readonly property var shellWorkspaceBridgeRef: root.shellContextRef.shellWorkspaceBridge
    readonly property var shellInspectorBridgeRef: root.shellContextRef.shellInspectorBridge
    readonly property var addonManagerBridgeRef: root.shellContextRef.addonManagerBridge
    readonly property var themeBridgeRef: root.shellContextRef.themeBridge
    readonly property var graphThemeBridgeRef: root.shellContextRef.graphThemeBridge
    readonly property var uiIconsRef: root.shellContextRef.uiIcons
    readonly property var statusEngineRef: root.shellContextRef.statusEngine
    readonly property var statusJobsRef: root.shellContextRef.statusJobs
    readonly property var statusMetricsRef: root.shellContextRef.statusMetrics
    readonly property var statusNotificationsRef: root.shellContextRef.statusNotifications
    readonly property var helpBridgeRef: root.shellContextRef.helpBridge
    readonly property var contentFullscreenBridgeRef: root.shellContextRef.contentFullscreenBridge
    readonly property var viewerSessionBridgeRef: root.shellContextRef.viewerSessionBridge
    readonly property var viewerHostServiceRef: root.shellContextRef.viewerHostService
    readonly property var scriptEditorBridgeRef: root.shellContextRef.scriptEditorBridge
    readonly property var scriptHighlighterBridgeRef: root.shellContextRef.scriptHighlighterBridge
    readonly property var themePalette: root.themeBridgeRef.palette
    color: themePalette.app_bg
    readonly property var graphActionBridgeRef: root.shellContextRef.graphActionBridge
    readonly property var canvasStateBridgeRef: root.shellContextRef.graphCanvasStateBridge
    readonly property var canvasCommandBridgeRef: root.shellContextRef.graphCanvasCommandBridge
    readonly property var canvasViewBridgeRef: root.shellContextRef.graphCanvasViewBridge
    property string linkTargetPickMode: ""
    property string linkTargetPickOwner: ""
    property string linkTargetPickSourceWorkspaceId: ""
    property string linkTargetPickSourceNodeId: ""
    property bool addonManagerLoaderActivated: !!root.addonManagerBridgeRef
        && Boolean(root.addonManagerBridgeRef.open)
    property bool contentFullscreenLoaderActivated: !!root.contentFullscreenBridgeRef
        && Boolean(root.contentFullscreenBridgeRef.open)

    function openNodeBrowser(initialQuery, sceneX, sceneY, mode) {
        nodeBrowserOverlay.openBrowser(initialQuery, sceneX, sceneY, mode)
    }

    function clearLinkTargetPickState() {
        root.linkTargetPickMode = "";
        root.linkTargetPickOwner = "";
        root.linkTargetPickSourceWorkspaceId = "";
        root.linkTargetPickSourceNodeId = "";
        if (workspaceCenterPane)
            workspaceCenterPane.clearLinkTargetPickMode();
    }

    function cancelLinkTargetPick(abortCanvasEditor) {
        var owner = root.linkTargetPickOwner;
        var sourceWorkspaceId = root.linkTargetPickSourceWorkspaceId;
        var sourceNodeId = root.linkTargetPickSourceNodeId;
        root.clearLinkTargetPickState();
        if (owner === "canvas") {
            if (Boolean(abortCanvasEditor)) {
                workspaceCenterPane.graphCanvasRef.abortNodeLinkEditorAfterSourceLoss();
                return;
            }
            workspaceCenterPane.selectNodeForLinkSource(sourceWorkspaceId, sourceNodeId, function() {
                workspaceCenterPane.graphCanvasRef.resumeNodeLinkEditorAfterPickCancel();
            });
            return;
        }
        if (inspectorPane)
            inspectorPane.cancelLinkTargetPick();
    }

    function cancelLinkTargetPickIfSourceSelectionLost() {
        if (!root.linkTargetPickMode.length)
            return;
        var activeWorkspaceId = root.shellWorkspaceBridgeRef
            ? String(root.shellWorkspaceBridgeRef.active_workspace_id || "").trim()
            : "";
        if (activeWorkspaceId !== root.linkTargetPickSourceWorkspaceId)
            return;
        var selectedNodeId = inspectorPane ? String(inspectorPane.selectedNodeId || "").trim() : "";
        if (selectedNodeId !== root.linkTargetPickSourceNodeId)
            root.cancelLinkTargetPick(root.linkTargetPickOwner === "canvas");
    }

    function startLinkTargetPick(owner, kind, sourceWorkspaceId, sourceNodeId) {
        var normalizedOwner = String(owner || "inspector").toLowerCase();
        var normalizedKind = String(kind || "").toLowerCase();
        if (normalizedKind !== "node" && normalizedKind !== "workspace")
            return;
        var normalizedSourceNodeId = String(sourceNodeId || "").trim();
        var normalizedSourceWorkspaceId = String(sourceWorkspaceId || "").trim();
        if (normalizedOwner !== "canvas") {
            normalizedOwner = "inspector";
            normalizedSourceNodeId = inspectorPane ? String(inspectorPane.selectedNodeId || "").trim() : "";
            normalizedSourceWorkspaceId = inspectorPane
                ? String(inspectorPane.selectedNodeWorkspaceId || "").trim()
                : "";
        }
        if (!normalizedSourceWorkspaceId.length && root.shellWorkspaceBridgeRef)
            normalizedSourceWorkspaceId = String(root.shellWorkspaceBridgeRef.active_workspace_id || "").trim();
        if (!normalizedSourceNodeId.length || !normalizedSourceWorkspaceId.length) {
            root.cancelLinkTargetPick(normalizedOwner === "canvas");
            return;
        }
        root.linkTargetPickOwner = normalizedOwner;
        root.linkTargetPickMode = normalizedKind;
        root.linkTargetPickSourceWorkspaceId = normalizedSourceWorkspaceId;
        root.linkTargetPickSourceNodeId = normalizedSourceNodeId;
        workspaceCenterPane.linkTargetPickMode = normalizedKind;
        workspaceCenterPane.linkTargetPickSourceWorkspaceId = normalizedSourceWorkspaceId;
        workspaceCenterPane.linkTargetPickSourceNodeId = normalizedSourceNodeId;
    }

    function finishLinkTargetPick(kind, workspaceId, nodeId, label, subtitle) {
        var normalizedKind = String(kind || root.linkTargetPickMode || "").toLowerCase();
        var owner = root.linkTargetPickOwner;
        var sourceWorkspaceId = root.linkTargetPickSourceWorkspaceId;
        var sourceNodeId = root.linkTargetPickSourceNodeId;
        root.clearLinkTargetPickState();
        var applyTarget = function() {
            if (owner === "canvas") {
                workspaceCenterPane.graphCanvasRef.applyNodeLinkTargetPick(
                    normalizedKind,
                    String(workspaceId || ""),
                    String(nodeId || ""),
                    String(label || ""),
                    String(subtitle || "")
                );
                return;
            }
            inspectorPane.applyLinkTargetPick(
                normalizedKind,
                String(workspaceId || ""),
                String(nodeId || ""),
                String(label || ""),
                String(subtitle || "")
            );
        };
        if (normalizedKind === "node" && sourceWorkspaceId.length && sourceNodeId.length) {
            workspaceCenterPane.selectNodeForLinkSource(sourceWorkspaceId, sourceNodeId, applyTarget);
            return;
        }
        applyTarget();
    }

    Connections {
        target: root.addonManagerBridgeRef

        function onStateChanged() {
            if (root.addonManagerBridgeRef && root.addonManagerBridgeRef.open)
                root.addonManagerLoaderActivated = true;
        }
    }

    Connections {
        target: root.contentFullscreenBridgeRef

        function onContent_fullscreen_changed() {
            if (root.contentFullscreenBridgeRef && root.contentFullscreenBridgeRef.open)
                root.contentFullscreenLoaderActivated = true;
        }
    }

    Connections {
        target: root.shellLibraryBridgeRef

        function onNode_browser_requested(initialQuery, sceneX, sceneY) {
            root.openNodeBrowser(initialQuery, sceneX, sceneY, "nodes")
        }
    }

    LibraryWorkflowContextPopup {
        id: libraryWorkflowContextPopup
        anchors.fill: parent
        shellLibraryBridgeRef: root.shellLibraryBridgeRef
        themeBridgeRef: root.themeBridgeRef
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ShellRunToolbar {
            id: shellRunToolbar
            workspaceBridgeRef: root.shellWorkspaceBridgeRef
            viewBridgeRef: root.canvasViewBridgeRef
            scriptEditorBridgeRef: root.scriptEditorBridgeRef
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.canvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
        }

        RowLayout {
            id: shellWorkspaceRow
            objectName: "shellWorkspaceRow"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            NodeLibraryPane {
                id: libraryPane
                shellLibraryBridgeRef: root.shellLibraryBridgeRef
                shellWorkspaceBridgeRef: root.shellWorkspaceBridgeRef
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.canvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                graphCanvasRef: workspaceCenterPane.graphCanvasRef
                popupHostItem: root
                onWorkflowContextRequested: function(workflowId, workflowScope, positionX, positionY) {
                    libraryWorkflowContextPopup.openPopup(workflowId, workflowScope, positionX, positionY)
                }
            }

            WorkspaceCenterPane {
                id: workspaceCenterPane
                graphActionBridgeRef: root.graphActionBridgeRef
                graphCanvasStateBridgeRef: root.canvasStateBridgeRef
                graphCanvasCommandBridgeRef: root.canvasCommandBridgeRef
                workspaceBridgeRef: root.shellWorkspaceBridgeRef
                themeBridgeRef: root.themeBridgeRef
                uiIconsRef: root.uiIconsRef
                overlayHostItem: root
                onNodeCommentEditorRequested: function(_nodeId, compose) {
                    if (compose)
                        inspectorPane.beginAddCommentForSelectedNode()
                    else
                        inspectorPane.openCommentsForSelectedNode()
                }
                onLinkTargetPicked: function(kind, workspaceId, nodeId, label, subtitle) {
                    root.finishLinkTargetPick(kind, workspaceId, nodeId, label, subtitle)
                }
                onLinkTargetPickRequested: function(kind, sourceWorkspaceId, sourceNodeId) {
                    root.startLinkTargetPick("canvas", kind, sourceWorkspaceId, sourceNodeId)
                }
                onLinkTargetPickCancelled: root.cancelLinkTargetPick(false)
            }

            InspectorPane {
                id: inspectorPane
                inspectorBridgeRef: root.shellInspectorBridgeRef
                shellWorkspaceBridgeRef: root.shellWorkspaceBridgeRef
                helpBridgeRef: root.helpBridgeRef
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.canvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                onLinkTargetPickRequested: function(kind) {
                    root.startLinkTargetPick("inspector", kind, "", "")
                }
                onLinkTargetPickCancelled: root.cancelLinkTargetPick(false)
                onSelectedNodeIdChanged: root.cancelLinkTargetPickIfSourceSelectionLost()
            }
        }

        ShellStatusStrip {
            id: shellStatusStrip
            canvasStateBridgeRef: root.canvasStateBridgeRef
            statusEngineRef: root.statusEngineRef
            statusJobsRef: root.statusJobsRef
            statusMetricsRef: root.statusMetricsRef
            statusNotificationsRef: root.statusNotificationsRef
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.canvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
        }
    }

    GraphSearchOverlay {
        id: graphSearchOverlay
        shellLibraryBridgeRef: root.shellLibraryBridgeRef
        themeBridgeRef: root.themeBridgeRef
        graphCanvasStateBridgeRef: root.canvasStateBridgeRef
        uiIconsRef: root.uiIconsRef
    }

    NodeBrowserOverlay {
        id: nodeBrowserOverlay
        anchors.fill: parent
        shellLibraryBridgeRef: root.shellLibraryBridgeRef
        helpBridgeRef: root.helpBridgeRef
        themeBridgeRef: root.themeBridgeRef
        uiIconsRef: root.uiIconsRef
        graphCanvasRef: workspaceCenterPane.graphCanvasRef
        canvasCommandBridgeRef: root.canvasCommandBridgeRef
    }

    ConnectionQuickInsertOverlay {
        id: connectionQuickInsertOverlay
        shellLibraryBridgeRef: root.shellLibraryBridgeRef
        themeBridgeRef: root.themeBridgeRef
    }

    Item {
        id: addonManagerOverlayHost
        objectName: "addonManagerOverlayHost"
        x: 0
        y: shellWorkspaceRow.y
        width: root.width
        height: shellWorkspaceRow.height
        visible: root.addonManagerBridgeRef.open
        z: 70

        Rectangle {
            id: addonManagerScrim
            objectName: "addonManagerScrim"
            anchors.fill: parent
            color: Qt.alpha(themePalette.app_bg, 0.68)

            MouseArea {
                anchors.fill: parent
                enabled: parent.visible
                onClicked: root.addonManagerBridgeRef.requestClose()
            }
        }

        Loader {
            id: addonManagerPaneLoader
            objectName: "addonManagerPaneLoader"
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.topMargin: 10
            anchors.rightMargin: 12
            anchors.bottomMargin: 10
            width: Math.min(parent.width - 24, 1040)
            active: root.addonManagerLoaderActivated
            source: Qt.resolvedUrl("components/shell/AddOnManagerPane.qml")
            z: 1

            onLoaded: {
                item.requestBridge = root.addonManagerBridgeRef;
                item.workspaceBridge = root.shellWorkspaceBridgeRef;
                item.viewerHostServiceRef = root.viewerHostServiceRef;
                item.themeBridgeRef = root.themeBridgeRef;
                item.graphThemeBridgeRef = root.graphThemeBridgeRef;
                item.graphCanvasStateBridgeRef = root.canvasStateBridgeRef;
                item.uiIconsRef = root.uiIconsRef;
                Qt.callLater(function() {
                    if (addonManagerOverlayHost.visible && addonManagerPaneLoader.item)
                        addonManagerPaneLoader.item.forceActiveFocus();
                });
            }
        }
    }

    ScriptEditorOverlay {
        id: scriptOverlay
        workspaceBridgeRef: root.shellWorkspaceBridgeRef
        scriptEditorBridgeRef: root.scriptEditorBridgeRef
        scriptHighlighterBridgeRef: root.scriptHighlighterBridgeRef
        themeBridgeRef: root.themeBridgeRef
        graphCanvasStateBridgeRef: root.canvasStateBridgeRef
        uiIconsRef: root.uiIconsRef
    }

    GraphHintOverlay {
        id: graphHintOverlay
        shellLibraryBridgeRef: root.shellLibraryBridgeRef
        themeBridgeRef: root.themeBridgeRef
        graphSearchVisible: graphSearchOverlay.visible || connectionQuickInsertOverlay.visible
    }

    Loader {
        id: contentFullscreenOverlayLoader
        objectName: "contentFullscreenOverlayLoader"
        anchors.fill: parent
        active: root.contentFullscreenLoaderActivated
        source: Qt.resolvedUrl("ContentFullscreenOverlay.qml")
        z: 2000

        onLoaded: {
            item.bridgeRef = root.contentFullscreenBridgeRef;
            item.scriptEditorBridgeRef = root.scriptEditorBridgeRef;
            item.scriptHighlighterBridgeRef = root.scriptHighlighterBridgeRef;
            Qt.callLater(function() {
                if (root.contentFullscreenBridgeRef.open && contentFullscreenOverlayLoader.item)
                    contentFullscreenOverlayLoader.item.forceActiveFocus();
            });
        }
    }
}
