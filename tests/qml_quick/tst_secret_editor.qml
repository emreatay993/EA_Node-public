import QtQuick 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/common" as Common

TestCase {
    id: testCase
    name: "SecretEditor"
    width: 640
    height: 180
    visible: true
    when: windowShown

    Item {
        id: stage
        anchors.fill: parent
    }

    Component {
        id: editorComponent
        Common.SecretEditor {
            width: 560
            height: implicitHeight
            hasValue: true
            accessibleName: "Value"
        }
    }

    SignalSpy {
        id: replaceSpy
        signalName: "replaceRequested"
    }

    SignalSpy {
        id: clearSpy
        signalName: "clearRequested"
    }

    function test_existing_secret_is_never_prefilled_and_replace_is_masked() {
        var editor = createTemporaryObject(editorComponent, stage)
        verify(editor !== null)
        replaceSpy.target = editor
        clearSpy.target = editor
        var field = findChild(editor, "secretEditorField")
        var replaceButton = findChild(editor, "secretEditorReplaceButton")
        verify(field !== null)
        verify(replaceButton !== null)
        compare(field.text, "")
        compare(field.echoMode, TextInput.Password)

        field.text = "new plaintext"
        mouseClick(replaceButton, replaceButton.width / 2, replaceButton.height / 2)
        compare(replaceSpy.count, 1)
        compare(replaceSpy.signalArguments[0][0], "new plaintext")
        compare(field.text, "")
    }

    function test_clear_is_explicit_and_requires_a_stored_value() {
        var editor = createTemporaryObject(editorComponent, stage)
        verify(editor !== null)
        replaceSpy.target = editor
        clearSpy.target = editor
        var clearButton = findChild(editor, "secretEditorClearButton")
        verify(clearButton !== null)
        verify(clearButton.enabled)
        mouseClick(clearButton, clearButton.width / 2, clearButton.height / 2)
        compare(clearSpy.count, 1)

        editor.hasValue = false
        wait(0)
        verify(!clearButton.enabled)
    }
}
