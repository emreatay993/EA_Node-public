// Purpose: Typed list editing without scalar Repeater expansion.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/main_window_shell/passive_property_editors.py, tests/qml_quick/tst_signal_selectors.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Column {
    required property var editorContext
    width: parent.width
    id: chipListContainer
    objectName: "inspectorChipListContainer"
    spacing: 6
    readonly property var chipValues: {
        var value = editorContext.exactSelectors
            ? (editorContext.displayValueAvailable ? editorContext.displayValue : null)
            : editorContext.propertyItem.value
        return Array.isArray(value) ? value : []
    }

    Flow {
        width: parent.width
        spacing: 6
        visible: chipListContainer.chipValues.length > 0

        Repeater {
            model: chipListContainer.chipValues

            Rectangle {
                property int chipIndex: index
                radius: 8
                color: Qt.alpha(editorContext.pane.themePalette.accent, 0.14)
                border.width: 1
                border.color: Qt.alpha(editorContext.pane.themePalette.accent, 0.36)
                implicitWidth: chipRow.implicitWidth + 10
                implicitHeight: chipRow.implicitHeight + 6

                Row {
                    id: chipRow
                    anchors.centerIn: parent
                    spacing: 4

                    Text {
                        text: editorContext.exactSelectors
                            ? chipListEditor.labelForValue(modelData) : String(modelData || "")
                        color: editorContext.pane.themePalette.input_fg
                        font.pixelSize: 10
                    }

                    InspectorButton {
                        pane: editorContext.pane
                        compact: true
                        text: "x"
                        enabled: editorContext.editorEnabled
                        onClicked: {
                            if (!editorContext.canCommit())
                                return
                            var values = []
                            for (var row = 0; row < chipListContainer.chipValues.length; ++row) {
                                if (row !== chipIndex)
                                    values.push(editorContext.exactSelectors ? chipListContainer.chipValues[row] : String(chipListContainer.chipValues[row] || ""))
                            }
                            editorContext.commitValue(
                                editorContext.propertyKey,
                                values
                            )
                        }
                    }
                }
            }
        }
    }

    InspectorEditableComboBox {
        id: chipListEditor
        objectName: "inspectorChipListEditor"
        property string propertyKey: editorContext.propertyKey
        pane: editorContext.pane
        width: parent.width
        enabled: editorContext.editorEnabled
        placeholderText: String(
            editorContext.propertyItem && editorContext.propertyItem.placeholder_text
                ? editorContext.propertyItem.placeholder_text
                : "Add value"
        )
        model: editorContext.propertyItem && editorContext.propertyItem.enum_values
            ? editorContext.propertyItem.enum_values
            : []
        selectedValue: ""
        optionCodes: editorContext.propertyItem.enum_codes || []
        exactSelectors: editorContext.exactSelectors

        function commitChip(value) {
            if (!editorContext.canCommit())
                return
            var text = editorContext.exactSelectors ? value : String(value || "").trim()
            if (text === "")
                return
            var values = []
            var normalized = editorContext.exactSelectors ? text : text.toLowerCase()
            var seen = false
            for (var index = 0; index < chipListContainer.chipValues.length; ++index) {
                var existing = editorContext.exactSelectors ? chipListContainer.chipValues[index] : String(chipListContainer.chipValues[index] || "")
                values.push(existing)
                if ((editorContext.exactSelectors ? existing : existing.toLowerCase()) === normalized)
                    seen = true
            }
            if (!seen)
                values.push(text)
            editorContext.commitValue(
                editorContext.propertyKey,
                values
            )
            editText = ""
        }

        onValueActivated: function(value) {
            commitChip(value)
        }
        onAccepted: commitChip(valueForText(editText))
    }
}
