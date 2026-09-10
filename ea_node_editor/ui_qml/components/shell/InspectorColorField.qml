import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common" as Common

Item {
    id: root
    property var pane
    signal commitRequested(string key, var value)
    property string propertyKey: ""
    property string committedText: ""
    property string tooltipCategory: "general"
    property int tooltipTextFormat: Text.PlainText
    readonly property string text: colorField.text
    readonly property var tooltipPolicyBridge: root.pane ? root.pane.graphCanvasStateBridgeRef : null

    implicitWidth: editorRow.implicitWidth
    implicitHeight: editorRow.implicitHeight

    function _normalizedText(value) {
        return String(value || "").trim();
    }

    function _hasValidColor(value) {
        return /^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(root._normalizedText(value));
    }

    function _swatchFillColor(value) {
        return root._hasValidColor(value)
            ? root._normalizedText(value)
            : "transparent";
    }

    function _swatchBorderColor() {
        return pickButton.hovered
            ? root.pane.themePalette.accent
            : root.pane.themePalette.input_border;
    }

    function syncTextToCommitted() {
        if (colorField.text !== committedText)
            colorField.text = committedText;
    }

    function commitText(value) {
        if (root.pane.inspectorBridgeRef)
            root.commitRequested(root.propertyKey, String(value || ""));
    }

    function pickColor() {
        if (!root.pane.inspectorBridgeRef)
            return;
        var selectedColor = root.pane.inspectorBridgeRef.pick_selected_node_property_color(
            root.propertyKey,
            colorField.text
        );
        if (!String(selectedColor || "").length)
            return;
        if (colorField.text !== String(selectedColor))
            colorField.text = String(selectedColor);
        commitText(colorField.text);
    }

    onCommittedTextChanged: {
        if (!colorField.activeFocus)
            syncTextToCommitted();
    }

    Component.onCompleted: syncTextToCommitted()

    RowLayout {
        id: editorRow
        anchors.fill: parent
        spacing: 6

        Button {
            id: pickButton
            objectName: "inspectorColorPickerButton"
            property string propertyKey: root.propertyKey
            Layout.preferredWidth: 34
            Layout.minimumWidth: 34
            Layout.maximumWidth: 34
            Layout.preferredHeight: 34
            Layout.minimumHeight: 34
            Layout.maximumHeight: 34
            enabled: root.enabled
            hoverEnabled: true
            focusPolicy: Qt.NoFocus

            onClicked: root.pickColor()

            Common.ManagedToolTip {
                policyBridge: root.tooltipPolicyBridge
                category: root.tooltipCategory
                active: pickButton.hovered
                text: "Pick color"
                textFormat: root.tooltipTextFormat
                delay: 280
            }

            contentItem: Item {
                implicitWidth: 0
                implicitHeight: 0
            }

            background: Rectangle {
                radius: 9
                color: root._swatchFillColor(colorField.text)
                border.width: 1
                border.color: root._swatchBorderColor()

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 5
                    radius: 5
                    color: root._hasValidColor(colorField.text)
                        ? root._swatchFillColor(colorField.text)
                        : Qt.alpha(root.pane.themePalette.tab_bg, 0.75)
                    border.width: root._hasValidColor(colorField.text) ? 0 : 1
                    border.color: root.pane.themePalette.input_border
                }
            }
        }

        InspectorTextField {
            id: colorField
            pane: root.pane
            objectName: "inspectorColorEditor"
            property string propertyKey: root.propertyKey
            Layout.fillWidth: true
            enabled: root.enabled
            onAccepted: root.commitText(text)
            onEditingFinished: root.commitText(text)
        }
    }
}
