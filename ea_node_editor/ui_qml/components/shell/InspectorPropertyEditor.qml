// Purpose: Property row presentation and exactly one active typed editor.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/main_window_shell/passive_property_editors.py, tests/qml_quick/tst_signal_selectors.qml
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common" as Common
import "../graph/surface_controls" as SurfaceControls

Column {
    id: propertyEditor
    objectName: "inspectorPropertyEditor"
    property var pane
    property var propertyItem: ({})
    readonly property string propertyKey: String(propertyItem ? propertyItem.key || "" : "")
    readonly property string editorMode: String(propertyItem ? propertyItem.editor_mode || "" : "")
    readonly property string pathDialogMode: String(propertyItem ? propertyItem.path_dialog_mode || "" : "")
    readonly property bool pathSupportsManagedCopy: !!(propertyItem && propertyItem.path_supports_managed_copy)
    readonly property bool pathSupportsExternalLink: !!(propertyItem && propertyItem.path_supports_external_link)
    readonly property string pathCurrentSourceMode: String(
        propertyItem && propertyItem.path_current_source_mode
            ? propertyItem.path_current_source_mode
            : "external_link"
    )
    readonly property bool pathSourceModeChoicesVisible: pathDialogMode !== "folder"
        && pathSupportsManagedCopy
        && pathSupportsExternalLink
    readonly property bool overriddenByInput: !!(propertyItem && propertyItem.overridden_by_input)
    readonly property bool displayValueAvailable: !propertyItem
        || typeof propertyItem.display_value_available === "undefined"
        || !!propertyItem.display_value_available
    readonly property var displayValue: propertyEditor.displayValueAvailable
        && propertyItem
        ? (propertyItem.display_value !== undefined ? propertyItem.display_value : propertyItem.value)
        : null
    readonly property bool editorEnabled: !!propertyItem
        && (typeof propertyItem.editor_enabled === "boolean"
            ? propertyItem.editor_enabled
            : !propertyEditor.overriddenByInput)
    readonly property string editorDisabledReason: String(
        propertyItem && propertyItem.editor_disabled_reason
            ? propertyItem.editor_disabled_reason
            : (propertyEditor.overriddenByInput
                ? propertyItem.override_reason || "Value supplied by connected input."
                : "")
    )
    readonly property bool searchableEnum: !!(propertyItem && propertyItem.searchable)
    readonly property bool exactSelectors: !!(propertyItem && propertyItem.exact_selectors)
    readonly property bool attentionRequired: !!(propertyItem && propertyItem.attention_required)
    readonly property string metadataStatusText: {
        if (propertyEditor.attentionRequired)
            return "Action required"
        return ""
    }
    readonly property string inputPortLabel: String(propertyItem ? propertyItem.input_port_label || "" : "")
    readonly property string propertyValueText: String(
        propertyEditor.displayValue !== undefined && propertyEditor.displayValue !== null
            ? propertyEditor.displayValue
            : (!propertyEditor.displayValueAvailable && propertyEditor.overriddenByInput
                ? "\u2014"
            : ""
            )
    )

    readonly property string effectiveEditorMode: pane && pane.isPinInspector && propertyKey === "data_type"
        ? "pin_data_type" : (editorMode === "enum" && searchableEnum ? "searchable_enum" : editorMode)
    property string _contextNodeId: ""
    property string _contextWorkspaceId: ""
    property string _contextPropertyKey: ""
    property bool _ready: false

    function currentNodeId() {
        var bridge = pane ? pane.inspectorBridgeRef : null
        return bridge && typeof bridge.selected_node_id !== "undefined" ? String(bridge.selected_node_id) : ""
    }

    function canCommit() {
        return _ready && editorEnabled && pane && pane.inspectorBridgeRef
            && _contextNodeId === currentNodeId() && _contextWorkspaceId === currentWorkspaceId()
            && _contextPropertyKey === propertyKey
    }

    function currentWorkspaceId() {
        var bridge = pane ? pane.inspectorBridgeRef : null
        return bridge && typeof bridge.selected_node_workspace_id !== "undefined"
            ? String(bridge.selected_node_workspace_id) : ""
    }

    function commitValue(key, value) {
        if (canCommit())
            propertyEditor.pane.inspectorBridgeRef.set_selected_node_property(key, value)
    }

    Component.onCompleted: {
        _contextNodeId = currentNodeId()
        _contextWorkspaceId = currentWorkspaceId()
        _contextPropertyKey = propertyKey
        _ready = true
    }
    Component.onDestruction: _ready = false

    width: parent ? parent.width : implicitWidth
    spacing: 4

    Text {
        width: parent.width
        visible: propertyEditor.editorMode !== "axis_compact"
        text: String(propertyEditor.propertyItem.label || "")
        color: propertyEditor.pane.themePalette.group_title_fg
        font.pixelSize: 10
        font.bold: true
        elide: Text.ElideRight
    }

    Text {
        width: parent.width
        visible: !propertyEditor.editorEnabled && propertyEditor.editorDisabledReason.length > 0
        objectName: "inspectorPropertyOverrideReason"
        property string propertyKey: propertyEditor.propertyKey
        text: propertyEditor.editorDisabledReason
        color: propertyEditor.pane.themePalette.muted_fg
        font.pixelSize: 10
        elide: Text.ElideRight
    }

    Text {
        width: parent.width
        visible: String(propertyEditor.propertyItem && propertyEditor.propertyItem.help_text || "").length > 0
        text: String(propertyEditor.propertyItem && propertyEditor.propertyItem.help_text || "")
        color: propertyEditor.pane.themePalette.muted_fg
        font.pixelSize: 10
        wrapMode: Text.Wrap
    }

    Rectangle {
        objectName: "inspectorPropertyStatusChip"
        property string propertyKey: propertyEditor.propertyKey
        visible: propertyEditor.metadataStatusText.length > 0
        radius: 8
        implicitWidth: propertyStatusText.implicitWidth + 12
        implicitHeight: propertyStatusText.implicitHeight + 5
        color: Qt.alpha(propertyEditor.pane.themePalette.inspector_danger_border, 0.16)
        border.width: 1
        border.color: propertyEditor.pane.themePalette.inspector_danger_border

        Text {
            id: propertyStatusText
            anchors.centerIn: parent
            text: propertyEditor.metadataStatusText
            color: propertyEditor.pane.themePalette.inspector_danger_fg
            font.pixelSize: 9
            font.bold: true
        }
    }

    Row {
        width: parent.width
        visible: propertyEditor.overriddenByInput
        spacing: 6

        Rectangle {
            objectName: "inspectorPropertyInactiveChip"
            property string propertyKey: propertyEditor.propertyKey
            radius: 8
            implicitWidth: inactiveChipText.implicitWidth + 10
            implicitHeight: inactiveChipText.implicitHeight + 4
            color: Qt.alpha(propertyEditor.pane.themePalette.accent, 0.14)
            border.width: 1
            border.color: Qt.alpha(propertyEditor.pane.themePalette.accent, 0.36)

            Text {
                id: inactiveChipText
                anchors.centerIn: parent
                text: "Inactive"
                color: propertyEditor.pane.themePalette.group_title_fg
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    Loader {
        id: editorLoader
        objectName: "inspectorTypedEditorLoader"
        width: parent.width
        height: item ? item.implicitHeight : 0
        sourceComponent: {
            switch (propertyEditor.effectiveEditorMode) {
            case "secret": return secretComponent
            case "toggle": return toggleComponent
            case "enum": return enumComponent
            case "interval_slider": return interval_sliderComponent
            case "color": return colorComponent
            case "summary": return summaryComponent
            case "axis_compact": return axis_compactComponent
            case "text": return textComponent
            case "textarea": return textareaComponent
            case "path": return pathComponent
            case "chip_list": return chip_listComponent
            case "searchable_enum":
            case "pin_data_type":
            case "editable_combo":
            case "font_family": return choiceComponent
            default: return null
            }
        }
    }

    Component {
        id: secretComponent
        Common.SecretEditor {
            objectName: "inspectorSecretEditor"
            width: parent.width
            editorEnabled: propertyEditor.editorEnabled
            hasValue: Boolean(
                propertyEditor.displayValue
                && propertyEditor.displayValue.has_value
            )
            accessibleName: String(propertyEditor.propertyItem.label || propertyEditor.propertyKey)
            textColor: propertyEditor.pane.themePalette.input_fg
            mutedTextColor: propertyEditor.pane.themePalette.muted_fg
            fieldColor: propertyEditor.pane.themePalette.input_bg
            borderColor: propertyEditor.pane.themePalette.input_border
            accentColor: propertyEditor.pane.themePalette.accent
            onReplaceRequested: function(plaintext) {
                if (propertyEditor.canCommit())
                    propertyEditor.pane.inspectorBridgeRef.set_selected_node_secret(
                        propertyEditor.propertyKey,
                        plaintext
                    )
            }
            onClearRequested: {
                if (propertyEditor.canCommit())
                    propertyEditor.pane.inspectorBridgeRef.clear_selected_node_secret(
                        propertyEditor.propertyKey
                    )
            }
        }
    }

    Component {
        id: toggleComponent
        Rectangle {
            width: parent.width
            radius: 10
            color: propertyEditor.pane.themePalette.input_bg
            border.color: propertyEditor.pane.themePalette.input_border
            border.width: 1
            implicitHeight: 38

            Row {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8

                InspectorCheckBox {
                    id: boolToggle
                    pane: propertyEditor.pane
                    enabled: propertyEditor.editorEnabled
                    checked: propertyEditor.displayValueAvailable && !!propertyEditor.displayValue
                    onToggled: {
                        if (propertyEditor.canCommit())
                            propertyEditor.commitValue(propertyEditor.propertyKey, checked)
                    }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: boolToggle.checked ? "Enabled" : "Disabled"
                    color: propertyEditor.pane.themePalette.input_fg
                    font.pixelSize: 11
                }
            }
        }
    }

    Component {
        id: enumComponent
        InspectorComboBox {
            width: parent.width
            pane: propertyEditor.pane
            enabled: propertyEditor.editorEnabled
            placeholderText: propertyEditor.displayValueAvailable ? "" : "\u2014"
            model: propertyEditor.propertyItem && propertyEditor.propertyItem.enum_values ? propertyEditor.propertyItem.enum_values : []
            currentIndex: {
                var values = propertyEditor.propertyItem && propertyEditor.propertyItem.enum_values
                    ? propertyEditor.propertyItem.enum_values
                    : []
                if (!propertyEditor.displayValueAvailable)
                    return -1
                var value = propertyEditor.propertyValueText
                var codes = propertyEditor.propertyItem.enum_codes || []
                var index = codes.length === values.length && codes.length > 0
                    ? codes.indexOf(propertyEditor.displayValue) : values.indexOf(value)
                return index >= 0 ? index : 0
            }
            onActivated: {
                var values = propertyEditor.propertyItem && propertyEditor.propertyItem.enum_values
                    ? propertyEditor.propertyItem.enum_values
                    : []
                if (!propertyEditor.canCommit() || currentIndex < 0 || currentIndex >= values.length)
                    return
                propertyEditor.commitValue(
                    propertyEditor.propertyKey,
                    (propertyEditor.propertyItem.enum_codes || []).length === values.length
                        ? propertyEditor.propertyItem.enum_codes[currentIndex] : String(values[currentIndex])
                )
            }
        }
    }

    Component {
        id: interval_sliderComponent
        SurfaceControls.GraphSurfaceIntervalSlider {
            id: intervalEditor
            objectName: "inspectorIntervalSlider"
            property string propertyKey: propertyEditor.propertyKey
            width: parent.width
            enabled: propertyEditor.editorEnabled
            from: isFinite(Number(propertyEditor.propertyItem.minimum))
                ? Number(propertyEditor.propertyItem.minimum)
                : 0
            to: isFinite(Number(propertyEditor.propertyItem.maximum))
                ? Number(propertyEditor.propertyItem.maximum)
                : 1
            stepSize: Math.max(0, Number(propertyEditor.propertyItem.step || 0))
            semanticStart: propertyEditor._intervalEndpoint("start", from)
            semanticEnd: propertyEditor._intervalEndpoint("end", to)
            displayValueAvailable: propertyEditor.displayValueAvailable
            intervalDirection: String(propertyEditor.propertyItem.interval_direction || "increasing")
            accentColor: propertyEditor.pane.themePalette.accent
            trackColor: propertyEditor.pane.themePalette.input_border
            handleFillColor: propertyEditor.pane.themePalette.input_bg
            handleBorderColor: propertyEditor.pane.themePalette.input_fg
            textColor: propertyEditor.pane.themePalette.input_fg
            disabledColor: propertyEditor.pane.themePalette.muted_fg
            onCommitRequested: function(value) {
                if (propertyEditor.editorEnabled && propertyEditor.canCommit())
                    propertyEditor.commitValue(
                        propertyEditor.propertyKey,
                        value
                    )
            }
        }
    }

    Component {
        id: colorComponent
        InspectorColorField {
            pane: propertyEditor.pane
            width: parent.width
            tooltipCategory: "general"
            enabled: propertyEditor.editorEnabled
            onCommitRequested: function(key, value) { propertyEditor.commitValue(key, value) }
            propertyKey: propertyEditor.propertyKey
            committedText: propertyEditor._displayEditorText()
        }
    }

    Component {
        id: summaryComponent
        Rectangle {
            width: parent.width
            radius: 10
            color: propertyEditor.attentionRequired
                ? Qt.alpha(propertyEditor.pane.themePalette.inspector_danger_border, 0.12)
                : Qt.alpha(propertyEditor.pane.themePalette.accent, 0.10)
            border.color: propertyEditor.attentionRequired
                ? propertyEditor.pane.themePalette.inspector_danger_border
                : Qt.alpha(propertyEditor.pane.themePalette.accent, 0.34)
            border.width: 1
            implicitHeight: summaryText.implicitHeight + 16

            Text {
                id: summaryText
                objectName: "inspectorPropertySummaryValue"
                property string propertyKey: propertyEditor.propertyKey
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                text: propertyEditor._displayEditorText()
                color: propertyEditor.pane.themePalette.input_fg
                font.pixelSize: 11
                wrapMode: Text.Wrap
            }
        }
    }

    Component {
        id: axis_compactComponent
        InspectorAxisCompactEditor {
            pane: propertyEditor.pane
            width: parent.width
            enabled: propertyEditor.editorEnabled
            onCommitRequested: function(key, value) { propertyEditor.commitValue(key, value) }
            propertyItem: propertyEditor.propertyItem
            overriddenByInput: propertyEditor.overriddenByInput
        }
    }

    Component {
        id: textComponent
        InspectorTextField {
            pane: propertyEditor.pane
            width: parent.width
            enabled: propertyEditor.editorEnabled
            text: propertyEditor._displayEditorText()
            onAccepted: {
                if (propertyEditor.canCommit())
                    propertyEditor.commitValue(propertyEditor.propertyKey, text)
            }
            onEditingFinished: {
                if (propertyEditor.canCommit())
                    propertyEditor.commitValue(propertyEditor.propertyKey, text)
            }
        }
    }

    Component {
        id: textareaComponent
        InspectorTextareaPropertyEditor { editorContext: propertyEditor }
    }

    Component {
        id: pathComponent
        InspectorPathPropertyEditor { editorContext: propertyEditor }
    }

    Component {
        id: chip_listComponent
        InspectorChipsPropertyEditor { editorContext: propertyEditor }
    }

    Component {
        id: choiceComponent
        InspectorChoicePropertyEditor { editorContext: propertyEditor }
    }

    function _intervalEndpoint(endpoint, fallback) {
        var candidate = propertyEditor.displayValueAvailable
            ? propertyEditor.displayValue
            : propertyEditor.propertyItem.value
        if (!candidate || typeof candidate !== "object")
            return fallback
        var value = Number(candidate[endpoint])
        return isFinite(value) ? value : fallback
    }

    function _displayEditorText() {
        if (!propertyEditor.displayValueAvailable && propertyEditor.overriddenByInput)
            return "\u2014"
        if (String(propertyEditor.propertyItem.type || "") === "json") {
            try {
                return JSON.stringify(propertyEditor.displayValue)
            } catch (error) {
                return ""
            }
        }
        return propertyEditor.propertyValueText
    }
}
