// Purpose: Lazy enum, typed selector, pin datatype and font editors.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/main_window_shell/passive_property_editors.py, tests/qml_quick/tst_signal_selectors.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common/FontFamilyOptions.js" as FontFamilyOptions

Loader {
    id: choices
    required property var editorContext
    height: item ? item.implicitHeight : 0
    sourceComponent: {
        switch (editorContext.effectiveEditorMode) {
        case "searchable_enum": return choice8
        case "pin_data_type": return choice10
        case "editable_combo": return choice11
        case "font_family": return choice12
        default: return null
        }
    }

    Component {
        id: choice8
        InspectorEditableComboBox {
            id: searchableEnumEditor
            pane: editorContext.pane
            objectName: "inspectorSearchableEnumEditor"
            property string propertyKey: editorContext.propertyKey
            width: parent.width
            enabled: editorContext.editorEnabled
            model: editorContext.propertyItem && editorContext.propertyItem.enum_values
                ? editorContext.propertyItem.enum_values
                : []
            selectedValue: editorContext.propertyValueText

            function commitDeclaredValue(value) {
                var candidate = String(value || "")
                var values = editorContext.propertyItem && editorContext.propertyItem.enum_values
                    ? editorContext.propertyItem.enum_values
                    : []
                for (var index = 0; index < values.length; ++index) {
                    if (String(values[index]) !== candidate)
                        continue
                    if (editorContext.canCommit())
                        editorContext.commitValue(
                            editorContext.propertyKey,
                            candidate
                        )
                    return
                }
                editText = editorContext.propertyValueText
            }

            onValueActivated: function(value) { commitDeclaredValue(value) }
            onAccepted: commitDeclaredValue(editText)
            onActiveFocusChanged: {
                if (!activeFocus)
                    editText = editorContext.propertyValueText
            }
        }
    }

    Component {
        id: choice10
        InspectorEditableComboBox {
            id: pinDataTypeEditor
            pane: editorContext.pane
            width: parent.width
            enabled: editorContext.editorEnabled
            model: editorContext.pane.pinDataTypeOptions
            selectedValue: String(editorContext.propertyItem && editorContext.propertyItem.value || "").toLowerCase()
            onValueActivated: function(value) {
                if (!editorContext.canCommit())
                    return
                editorContext.commitValue(
                    editorContext.propertyKey,
                    String(value || "")
                )
            }
            onAccepted: {
                if (editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, editText)
            }
            onActiveFocusChanged: {
                if (!activeFocus && editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, editText)
            }
            Component.onCompleted: editText = editorContext.propertyValueText
            onVisibleChanged: {
                if (visible && !activeFocus)
                    editText = editorContext.propertyValueText
            }
        }
    }

    Component {
        id: choice11
        InspectorEditableComboBox {
            id: editableComboEditor
            objectName: "inspectorEditableComboEditor"
            property string propertyKey: editorContext.propertyKey
            pane: editorContext.pane
            width: parent.width
            enabled: editorContext.editorEnabled
            placeholderText: String(
                editorContext.propertyItem && editorContext.propertyItem.placeholder_text
                    ? editorContext.propertyItem.placeholder_text
                    : ""
            )
            model: editorContext.propertyItem && editorContext.propertyItem.enum_values
                ? editorContext.propertyItem.enum_values
                : []
            optionCodes: editorContext.propertyItem.enum_codes || []
            exactSelectors: editorContext.exactSelectors
            selectedValue: editorContext.exactSelectors ? editorContext.displayValue : editorContext.propertyValueText
            onValueActivated: function(value) {
                if (!editorContext.canCommit())
                    return
                editorContext.commitValue(
                    editorContext.propertyKey,
                    editorContext.exactSelectors ? value : String(value || "")
                )
            }
            onAccepted: {
                if (editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, valueForText(editText))
            }
            onActiveFocusChanged: {
                if (!activeFocus && !popupInteractionActive && editorContext.canCommit())
                    editorContext.commitValue(editorContext.propertyKey, valueForText(editText))
            }
            Component.onCompleted: _syncSelectionFromValue()
            onVisibleChanged: {
                if (visible && !activeFocus)
                    _syncSelectionFromValue()
            }
        }
    }

    Component {
        id: choice12
        InspectorEditableComboBox {
            id: fontFamilyEditor
            pane: editorContext.pane
            objectName: "inspectorFontFamilyEditor"
            property string propertyKey: editorContext.propertyKey
            width: parent.width
            enabled: editorContext.editorEnabled
            placeholderText: "Search fonts"
            model: FontFamilyOptions.withDefault()
            selectedValue: FontFamilyOptions.displayName(editorContext.propertyValueText)
            previewValueAsFontFamily: true
            defaultFontFamilyLabel: FontFamilyOptions.DEFAULT_FONT_FAMILY_LABEL

            function commitDisplayValue(value) {
                if (!editorContext.canCommit())
                    return
                var display = String(value || "").trim()
                if (!display.length) {
                    editText = selectedValue
                    return
                }
                var family = FontFamilyOptions.canonicalFamily(display)
                if (!family.length && display.toLowerCase() !== FontFamilyOptions.DEFAULT_FONT_FAMILY_LABEL.toLowerCase()) {
                    editText = selectedValue
                    return
                }
                editorContext.commitValue(
                    editorContext.propertyKey,
                    family
                )
                editText = FontFamilyOptions.displayName(family)
            }

            onValueActivated: function(value) {
                commitDisplayValue(value)
            }
            onAccepted: commitDisplayValue(editText)
            onActiveFocusChanged: {
                if (!activeFocus)
                    commitDisplayValue(editText)
            }
            Component.onCompleted: editText = selectedValue
            onVisibleChanged: {
                if (visible && !activeFocus)
                    editText = selectedValue
            }
        }
    }
}
