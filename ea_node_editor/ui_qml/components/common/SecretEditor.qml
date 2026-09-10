// Purpose: Provide the shared masked Replace/Clear editor for protected properties.
// Map: feature_routes/ssh_sftp_nodes.md
// Tests: tests/qml_quick/tst_secret_editor.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FocusScope {
    id: root
    property bool hasValue: false
    property bool editorEnabled: true
    property string accessibleName: "Secret"
    property color textColor: "#f2f4f8"
    property color mutedTextColor: "#9ca7b8"
    property color fieldColor: "#1d2026"
    property color borderColor: "#515968"
    property color accentColor: "#2f8cff"
    signal replaceRequested(string plaintext)
    signal clearRequested()

    implicitHeight: editorRow.implicitHeight

    function clearDraft() {
        secretField.clear()
    }

    RowLayout {
        id: editorRow
        anchors.fill: parent
        spacing: 6

        Text {
            objectName: "secretEditorStateLabel"
            Layout.alignment: Qt.AlignVCenter
            text: root.hasValue ? "Set" : "Not set"
            color: root.hasValue ? root.textColor : root.mutedTextColor
            font.pixelSize: 10
            Accessible.name: root.accessibleName + " state"
        }

        TextField {
            id: secretField
            objectName: "secretEditorField"
            Layout.fillWidth: true
            enabled: root.editorEnabled
            echoMode: TextInput.Password
            placeholderText: root.hasValue ? "New secret" : "Secret"
            selectByMouse: true
            color: root.textColor
            placeholderTextColor: root.mutedTextColor
            Accessible.name: root.accessibleName
            Accessible.description: "Masked secret value. Existing values are never displayed."
            background: Rectangle {
                radius: 5
                color: root.fieldColor
                border.width: secretField.activeFocus ? 2 : 1
                border.color: secretField.activeFocus ? root.accentColor : root.borderColor
            }
            Keys.onEscapePressed: root.clearDraft()
        }

        Button {
            objectName: "secretEditorReplaceButton"
            enabled: root.editorEnabled && secretField.text.length > 0
            text: root.hasValue ? "Replace" : "Set"
            Accessible.name: text + " " + root.accessibleName
            onClicked: {
                root.replaceRequested(secretField.text)
                root.clearDraft()
            }
        }

        Button {
            objectName: "secretEditorClearButton"
            enabled: root.editorEnabled && root.hasValue
            text: "Clear"
            Accessible.name: "Clear " + root.accessibleName
            onClicked: {
                root.clearRequested()
                root.clearDraft()
            }
        }
    }
}
