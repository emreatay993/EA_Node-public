// Purpose: Explicit-Apply text drafts.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/main_window_shell/passive_property_editors.py, tests/qml_quick/tst_signal_selectors.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Column {
    required property var editorContext
    id: textareaEditorGroup
    width: parent.width
    spacing: 6
    property string propertyKey: editorContext.propertyKey
    property string committedText: editorContext._displayEditorText()
    property string draftText: committedText
    property bool draftDirty: draftText !== committedText

    function syncDraftToCommitted() {
        draftText = committedText
        if (textareaEditor.text !== committedText)
            textareaEditor.text = committedText
    }

    function commitDraft() {
        if (!editorContext.canCommit())
            return
        editorContext.commitValue(propertyKey, draftText)
    }

    onCommittedTextChanged: {
        if (!textareaEditor.activeFocus || !draftDirty)
            syncDraftToCommitted()
    }

    InspectorTextArea {
        id: textareaEditor
        pane: editorContext.pane
        objectName: "inspectorTextareaEditor"
        property string propertyKey: textareaEditorGroup.propertyKey
        width: parent.width
        enabled: editorContext.editorEnabled
        text: textareaEditorGroup.draftText
        onTextChanged: {
            if (textareaEditorGroup.draftText !== text)
                textareaEditorGroup.draftText = text
        }
        Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                    && (event.modifiers & Qt.ControlModifier)) {
                textareaEditorGroup.commitDraft()
                event.accepted = true
            } else if (event.key === Qt.Key_Escape) {
                textareaEditorGroup.syncDraftToCommitted()
                event.accepted = true
            }
        }
    }

    RowLayout {
        width: parent.width
        spacing: 6

        InspectorButton {
            pane: editorContext.pane
            objectName: "inspectorTextareaApplyButton"
            property string propertyKey: textareaEditorGroup.propertyKey
            compact: true
            enabled: editorContext.editorEnabled && textareaEditorGroup.draftDirty
            text: "Apply"
            onClicked: textareaEditorGroup.commitDraft()
        }

        InspectorButton {
            pane: editorContext.pane
            objectName: "inspectorTextareaResetButton"
            property string propertyKey: textareaEditorGroup.propertyKey
            compact: true
            enabled: editorContext.editorEnabled && textareaEditorGroup.draftDirty
            text: "Reset"
            onClicked: textareaEditorGroup.syncDraftToCommitted()
        }

        Text {
            Layout.fillWidth: true
            verticalAlignment: Text.AlignVCenter
            text: textareaEditorGroup.draftDirty
                ? "Ctrl+Enter to commit"
                : "Committed"
            color: editorContext.pane.themePalette.muted_fg
            font.pixelSize: 10
            elide: Text.ElideRight
        }
    }
}
