import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../common" as Common

// Settings sheet for the Number Slider pill: custom name, integer/decimal
// rounding, decimal places, and the minimum/value/maximum range. Anchored and
// opened by GraphCanvasRootLayers (same overlay contract as the timestamp
// popover); Accept emits one payload that the surface commits atomically.
FocusScope {
    id: root
    objectName: "graphNumberSliderSettingsPopover"

    property Item host: null
    property var themePalette: ({})
    property real shadowStrength: 55
    property real shadowSoftness: 50
    property real shadowOffset: 4

    property var _originalSettings: ({})
    property string roundingDraft: "decimal"

    readonly property var embeddedInteractiveRects: []
    readonly property color panelTextColor: root.themePalette.panel_title_fg || "#eef3ff"
    readonly property color mutedTextColor: root.themePalette.muted_fg || "#95a0b8"

    signal accepted(var payload)
    signal canceled()

    visible: false
    implicitWidth: 400
    implicitHeight: dialogSurface.implicitHeight
    activeFocusOnTab: true

    function _numberOrFallback(text, fallback) {
        var numeric = Number(String(text === undefined || text === null ? "" : text).trim());
        return isFinite(numeric) ? numeric : Number(fallback);
    }

    function openWithSettings(settings) {
        var normalized = settings && typeof settings === "object" ? settings : {};
        root._originalSettings = normalized;
        customNameField.text = String(normalized.title || "");
        root.roundingDraft = String(normalized.rounding || "decimal") === "integer" ? "integer" : "decimal";
        decimalsField.text = String(Math.max(0, Math.min(6, Math.round(Number(normalized.decimals) || 0))));
        minimumField.text = String(Number(normalized.minimum) || 0);
        valueField.text = String(Number(normalized.value) || 0);
        maximumField.text = String(Number(normalized.maximum) || 0);
        root.visible = true;
        Qt.callLater(function() {
            customNameField.forceActiveFocus();
            customNameField.selectAll();
        });
    }

    function acceptEdit() {
        var original = root._originalSettings || {};
        root.visible = false;
        root.accepted({
            "title": String(customNameField.text || "").trim() || String(original.title || ""),
            "rounding": root.roundingDraft,
            "decimals": Math.round(root._numberOrFallback(decimalsField.text, original.decimals)),
            "minimum": root._numberOrFallback(minimumField.text, original.minimum),
            "value": root._numberOrFallback(valueField.text, original.value),
            "maximum": root._numberOrFallback(maximumField.text, original.maximum)
        });
    }

    function cancelEdit() {
        root.visible = false;
        root.canceled();
    }

    function closeSilently() {
        root.visible = false;
    }

    Keys.onEscapePressed: root.cancelEdit()
    Keys.onReturnPressed: root.acceptEdit()
    Keys.onEnterPressed: root.acceptEdit()

    Common.DialogSurface {
        id: dialogSurface
        anchors.fill: parent
        themePalette: root.themePalette
        closeButtonVisible: true
        onCloseRequested: root.cancelEdit()

        ColumnLayout {
            id: contentColumn
            Layout.fillWidth: true
            Layout.margins: 24
            spacing: 18

            Common.DialogTextField {
                id: customNameField
                objectName: "graphNumberSliderSettingsNameField"
                Layout.fillWidth: true
                controlHeight: 44
                themePalette: root.themePalette
                placeholderText: "Custom name..."
                Accessible.name: "Custom name"
                onAccepted: root.acceptEdit()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Text {
                    Layout.fillWidth: true
                    text: "Rounding"
                    color: root.mutedTextColor
                    font.pixelSize: 11
                }

                RowLayout {
                    Layout.preferredWidth: 160
                    spacing: 0

                    Common.DialogButton {
                        id: integerRoundingButton
                        objectName: "graphNumberSliderSettingsIntegerButton"
                        Layout.fillWidth: true
                        controlHeight: 44
                        themePalette: root.themePalette
                        text: "ℤ"
                        selected: root.roundingDraft === "integer"
                        Accessible.name: "Integer rounding"
                        onClicked: root.roundingDraft = "integer"
                    }

                    Common.DialogButton {
                        id: decimalRoundingButton
                        objectName: "graphNumberSliderSettingsDecimalButton"
                        Layout.fillWidth: true
                        controlHeight: 44
                        themePalette: root.themePalette
                        text: "ℚ"
                        selected: root.roundingDraft === "decimal"
                        Accessible.name: "Decimal rounding"
                        onClicked: root.roundingDraft = "decimal"
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                opacity: root.roundingDraft === "decimal" ? 1.0 : 0.45

                Text {
                    Layout.fillWidth: true
                    text: "Digits"
                    color: root.mutedTextColor
                    font.pixelSize: 11
                }

                Common.DialogTextField {
                    id: decimalsField
                    objectName: "graphNumberSliderSettingsDecimalsField"
                    Layout.preferredWidth: 160
                    controlHeight: 44
                    themePalette: root.themePalette
                    enabled: root.roundingDraft === "decimal"
                    horizontalAlignment: TextInput.AlignRight
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 0; top: 6 }
                    Accessible.name: "Digits"
                    onAccepted: root.acceptEdit()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: "Minimum"
                    color: root.mutedTextColor
                    font.pixelSize: 11
                }

                Common.DialogTextField {
                    id: minimumField
                    objectName: "graphNumberSliderSettingsMinimumField"
                    Layout.preferredWidth: 160
                    controlHeight: 44
                    themePalette: root.themePalette
                    horizontalAlignment: TextInput.AlignRight
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    Accessible.name: "Minimum"
                    onAccepted: root.acceptEdit()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: "Value"
                    color: root.mutedTextColor
                    font.pixelSize: 11
                }

                Common.DialogTextField {
                    id: valueField
                    objectName: "graphNumberSliderSettingsValueField"
                    Layout.preferredWidth: 160
                    controlHeight: 44
                    themePalette: root.themePalette
                    horizontalAlignment: TextInput.AlignRight
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    Accessible.name: "Value"
                    onAccepted: root.acceptEdit()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: "Maximum"
                    color: root.mutedTextColor
                    font.pixelSize: 11
                }

                Common.DialogTextField {
                    id: maximumField
                    objectName: "graphNumberSliderSettingsMaximumField"
                    Layout.preferredWidth: 160
                    controlHeight: 44
                    themePalette: root.themePalette
                    horizontalAlignment: TextInput.AlignRight
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    Accessible.name: "Maximum"
                    onAccepted: root.acceptEdit()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Item { Layout.fillWidth: true }

                Common.DialogButton {
                    id: cancelButton
                    objectName: "graphNumberSliderSettingsCancelButton"
                    Layout.preferredWidth: 140
                    controlHeight: 44
                    themePalette: root.themePalette
                    text: "Cancel"
                    onClicked: root.cancelEdit()
                }

                Common.DialogButton {
                    id: acceptButton
                    objectName: "graphNumberSliderSettingsAcceptButton"
                    Layout.preferredWidth: 140
                    controlHeight: 44
                    themePalette: root.themePalette
                    text: "OK"
                    primary: true
                    onClicked: root.acceptEdit()
                }
            }
        }
    }
}
