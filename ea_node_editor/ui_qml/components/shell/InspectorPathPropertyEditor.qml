// Purpose: Path editing, source storage and native browsing.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/main_window_shell/passive_property_editors.py, tests/qml_quick/tst_signal_selectors.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Column {
    id: pathBody
    required property var editorContext
    width: parent.width
    spacing: 6

    RowLayout {
        width: parent.width
        spacing: 6

        InspectorTextField {
            id: pathEditor
            pane: editorContext.pane
            objectName: "inspectorPathEditor"
            property string propertyKey: editorContext.propertyKey
            property string pathDialogMode: editorContext.pathDialogMode
            Layout.fillWidth: true
            enabled: editorContext.editorEnabled
            text: editorContext._displayEditorText()
            onAccepted: {
                if (editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, text)
            }
            onEditingFinished: {
                if (editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, text)
            }
        }

        InspectorButton {
            pane: editorContext.pane
            objectName: "inspectorPathBrowseButton"
            property string propertyKey: editorContext.propertyKey
            property string pathDialogMode: editorContext.pathDialogMode
            compact: true
            enabled: editorContext.editorEnabled
            text: "Browse"
            iconName: "folder-open"
            onClicked: {
                pathBody._browseAndCommitPath(
                    pathEditor.text,
                    pathBody._selectedPathSourceMode()
                )
            }
        }
    }

    RowLayout {
        width: parent.width
        spacing: 6
        visible: editorContext.pathSourceModeChoicesVisible

        Text {
            Layout.alignment: Qt.AlignVCenter
            text: "Source storage"
            color: editorContext.pane.themePalette.muted_fg
            font.pixelSize: 10
            elide: Text.ElideRight
        }

        InspectorComboBox {
            id: sourceStorageCombo
            pane: editorContext.pane
            objectName: "inspectorPathSourceStorageComboBox"
            property string propertyKey: editorContext.propertyKey
            Layout.fillWidth: true
            enabled: editorContext.editorEnabled
            model: ["External", "Internal"]
            currentIndex: 0
        }
    }

    Rectangle {
        width: parent.width
        visible: !!(editorContext.propertyItem && editorContext.propertyItem.file_issue_active)
        radius: 8
        color: Qt.alpha(editorContext.pane.themePalette.accent, 0.12)
        border.width: 1
        border.color: Qt.alpha(editorContext.pane.themePalette.accent, 0.48)
        implicitHeight: issueColumn.implicitHeight + 12

        Column {
            id: issueColumn
            anchors.fill: parent
            anchors.margins: 6
            spacing: 6

            Text {
                width: parent.width
                text: String(editorContext.propertyItem && editorContext.propertyItem.file_issue_message || "")
                color: editorContext.pane.themePalette.input_fg
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }

            InspectorButton {
                pane: editorContext.pane
                objectName: "inspectorPathRepairButton"
                property string propertyKey: editorContext.propertyKey
                compact: true
                text: "Repair file..."
                onClicked: {
                    if (!editorContext.canCommit())
                        return
                    var repairedPath = editorContext.pane.inspectorBridgeRef.browse_selected_node_property_path(
                        editorContext.propertyKey,
                        String(editorContext.propertyItem && editorContext.propertyItem.file_issue_request || "")
                    )
                    if (!editorContext.canCommit() || !String(repairedPath || "").length)
                        return
                    pathEditor.text = String(repairedPath)
                    editorContext.commitValue(editorContext.propertyKey, pathEditor.text)
                }
            }
        }
    }
    function _selectedPathSourceMode() {
        if (!editorContext.pathSourceModeChoicesVisible)
            return ""
        return sourceStorageCombo.currentIndex === 1 ? "managed_copy" : "external_link"
    }

    function _pathSourceModeIndex(sourceMode) {
        return String(sourceMode || "").trim().toLowerCase() === "managed_copy" ? 1 : 0
    }

    function _syncSourceStorageCombo() {
        sourceStorageCombo.currentIndex = pathBody._pathSourceModeIndex(editorContext.pathCurrentSourceMode)
    }

    function _browseAndCommitPath(currentPath, sourceMode) {
        if (!editorContext.canCommit())
            return
        var normalizedSourceMode = String(sourceMode || "").trim()
        var selectedPath = normalizedSourceMode.length > 0
            ? editorContext.pane.inspectorBridgeRef.browse_selected_node_property_path(
                editorContext.propertyKey,
                currentPath,
                normalizedSourceMode
            )
            : editorContext.pane.inspectorBridgeRef.browse_selected_node_property_path(
                editorContext.propertyKey,
                currentPath
            )
        if (!editorContext.canCommit() || !String(selectedPath || "").length)
            return
        pathEditor.text = String(selectedPath)
        editorContext.commitValue(editorContext.propertyKey, pathEditor.text)
    }

    Connections {
        target: editorContext
        function onPathCurrentSourceModeChanged() { pathBody._syncSourceStorageCombo() }
        function onPathSourceModeChoicesVisibleChanged() { pathBody._syncSourceStorageCombo() }
    }

    Component.onCompleted: _syncSourceStorageCombo()

}
