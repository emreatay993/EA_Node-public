import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property string libraryContextWorkflowId: ""
    property string libraryContextWorkflowScope: ""
    readonly property bool libraryContextWorkflowReadOnly: libraryContextWorkflowScope === "bundled"
    readonly property var editableContextMenuActions: [
        { "actionId": "rename", "text": "Rename" },
        {
            "actionId": "scope",
            "text": root.libraryContextWorkflowScope === "global" ? "Make Project-Only" : "Make Global"
        },
        { "actionId": "delete", "text": "Delete", "destructive": true }
    ]
    readonly property var contextMenuActions: libraryContextWorkflowReadOnly ? [] : editableContextMenuActions
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    function openPopup(workflowId, workflowScope, positionX, positionY) {
        if (String(workflowScope || "").toLowerCase() === "bundled") {
            libraryContextPopup.close()
            return
        }
        libraryContextWorkflowId = String(workflowId || "")
        libraryContextWorkflowScope = String(workflowScope || "")
        libraryContextPopup.openAt(root, positionX, positionY)
    }

    onWidthChanged: {
        if (libraryContextPopup.visible)
            libraryContextPopup.close()
    }

    onHeightChanged: {
        if (libraryContextPopup.visible)
            libraryContextPopup.close()
    }

    ShellContextPopup {
        id: libraryContextPopup
        themeBridgeRef: root.themeBridgeRef
        minimumWidth: 188
        actions: root.contextMenuActions
        onActionTriggered: function(actionId) {
            if (actionId === "rename") {
                root.shellLibraryBridgeRef.request_rename_custom_workflow_from_library(
                    root.libraryContextWorkflowId,
                    root.libraryContextWorkflowScope
                )
            } else if (actionId === "scope") {
                var nextScope = root.libraryContextWorkflowScope === "global" ? "local" : "global"
                root.shellLibraryBridgeRef.request_set_custom_workflow_scope(root.libraryContextWorkflowId, nextScope)
            } else if (actionId === "delete") {
                root.shellLibraryBridgeRef.request_delete_custom_workflow_from_library(
                    root.libraryContextWorkflowId,
                    root.libraryContextWorkflowScope
                )
            }
        }
    }
}
