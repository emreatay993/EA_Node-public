import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common/TooltipCopy.js" as TooltipCopy

Column {
    id: root
    property var pane
    signal commitRequested(string key, var value)
    property var propertyItem: ({})
    property bool overriddenByInput: false
    readonly property string propertyKey: String(propertyItem ? propertyItem.key || "" : "")
    readonly property string axisLabel: String(propertyItem ? propertyItem.label || "" : "")
    readonly property var fields: propertyItem && propertyItem.fields ? propertyItem.fields : []
    readonly property bool logScale: _fieldBool("log")
    readonly property bool hasManualAxis: _fieldText("min").length > 0
        || _fieldText("max").length > 0
        || logScale

    width: parent ? parent.width : implicitWidth
    spacing: 0

    function _fieldByRole(role) {
        for (var index = 0; index < fields.length; ++index) {
            var field = fields[index] || {}
            if (String(field.role || "") === role)
                return field
        }
        return null
    }

    function _fieldKey(role) {
        var field = _fieldByRole(role)
        return field ? String(field.key || "") : ""
    }

    function _fieldText(role) {
        var field = _fieldByRole(role)
        if (!field || field.value === undefined || field.value === null)
            return ""
        return String(field.value)
    }

    function _fieldBool(role) {
        var field = _fieldByRole(role)
        if (!field)
            return false
        if (typeof field.value === "boolean")
            return field.value
        return String(field.value || "").toLowerCase() === "true"
    }

    function _fieldPlaceholder(role) {
        var field = _fieldByRole(role)
        return field ? String(field.placeholder_text || "") : ""
    }

    function _commitField(role, value) {
        var key = _fieldKey(role)
        if (!key.length || !root.pane || !root.pane.inspectorBridgeRef)
            return
        root.commitRequested(key, value)
    }

    function resetAxis() {
        _commitField("min", "")
        _commitField("max", "")
        _commitField("log", false)
    }

    RowLayout {
        id: axisRow
        objectName: "inspectorAxisCompactEditor"
        property string propertyKey: root.propertyKey
        width: root.width
        spacing: 6

        Text {
            Layout.preferredWidth: 42
            Layout.minimumWidth: 36
            Layout.alignment: Qt.AlignVCenter
            text: root.axisLabel.length ? root.axisLabel : "Axis"
            color: root.pane.themePalette.group_title_fg
            font.pixelSize: 11
            font.bold: true
            elide: Text.ElideRight
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 58
            spacing: 3

            Text {
                text: "Min"
                color: root.pane.themePalette.muted_fg
                font.pixelSize: 10
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            InspectorTextField {
                id: minEditor
                pane: root.pane
                objectName: "inspectorAxisCompactMinEditor"
                property string propertyKey: root._fieldKey("min")
                Layout.fillWidth: true
                enabled: !root.overriddenByInput
                text: root._fieldText("min")
                placeholderText: root._fieldPlaceholder("min")
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                onAccepted: root._commitField("min", text)
                onEditingFinished: root._commitField("min", text)
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 58
            spacing: 3

            Text {
                text: "Max"
                color: root.pane.themePalette.muted_fg
                font.pixelSize: 10
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            InspectorTextField {
                id: maxEditor
                pane: root.pane
                objectName: "inspectorAxisCompactMaxEditor"
                property string propertyKey: root._fieldKey("max")
                Layout.fillWidth: true
                enabled: !root.overriddenByInput
                text: root._fieldText("max")
                placeholderText: root._fieldPlaceholder("max")
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                onAccepted: root._commitField("max", text)
                onEditingFinished: root._commitField("max", text)
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 82
            Layout.minimumWidth: 74
            Layout.maximumWidth: 92
            spacing: 3

            Text {
                text: "Scale"
                color: root.pane.themePalette.muted_fg
                font.pixelSize: 10
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Rectangle {
                id: scaleToggle
                objectName: "inspectorAxisCompactLogToggle"
                property string propertyKey: root._fieldKey("log")
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                radius: 9
                color: root.pane.themePalette.input_bg
                border.color: root.logScale ? root.pane.themePalette.accent : root.pane.themePalette.input_border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 3
                    spacing: 2

                    Repeater {
                        model: [
                            {"label": "Lin", "value": false},
                            {"label": "Log", "value": true}
                        ]

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 7
                            color: root.logScale === !!modelData.value
                                ? root.pane.themePalette.accent
                                : "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: String(modelData.label || "")
                                color: root.logScale === !!modelData.value
                                    ? root.pane.themePalette.panel_bg
                                    : root.pane.themePalette.input_fg
                                font.pixelSize: 10
                                font.bold: root.logScale === !!modelData.value
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: !root.overriddenByInput
                                hoverEnabled: true
                                onClicked: root._commitField("log", !!modelData.value)
                            }
                        }
                    }
                }
            }
        }

        InspectorButton {
            pane: root.pane
            objectName: "inspectorAxisCompactResetButton"
            property string propertyKey: root.propertyKey
            Layout.preferredWidth: 34
            Layout.minimumWidth: 34
            Layout.maximumWidth: 34
            Layout.preferredHeight: 34
            Layout.alignment: Qt.AlignBottom
            compact: true
            text: ""
            iconName: "rotate-clockwise"
            iconSize: 14
            tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.axis.reset")
            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.axis.reset")
            enabled: !root.overriddenByInput && root.hasManualAxis
            onClicked: root.resetAxis()
        }
    }
}
