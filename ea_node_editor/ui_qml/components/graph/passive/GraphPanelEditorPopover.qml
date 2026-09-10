import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../common" as Common
import "../surface_controls" as SurfaceControls

// Draft-only Panel editor. Cancel discards every draft; OK emits one complete
// property payload for the surface to commit atomically.
FocusScope {
    id: root
    objectName: "graphPanelEditorPopover"

    property Item host: null
    property var themePalette: ({})
    property real shadowStrength: 55
    property real shadowSoftness: 50
    property real shadowOffset: 4
    property var _originalSettings: ({})
    property int modeDraft: 0
    property bool autoResizeDraft: true

    readonly property var embeddedInteractiveRects: []
    readonly property color panelTextColor: root.themePalette.panel_title_fg || "#eef3ff"
    readonly property color mutedTextColor: root.themePalette.muted_fg || "#95a0b8"
    readonly property var tooltipPolicyBridge: root.host
        && root.host.canvasItem
        && typeof root.host.canvasItem.canvasStateBridgeRef !== "undefined"
        ? root.host.canvasItem.canvasStateBridgeRef
        : null

    signal accepted(var payload)
    signal canceled()

    visible: false
    implicitWidth: 320
    implicitHeight: dialogSurface.implicitHeight
    activeFocusOnTab: true

    function openWithSettings(settings) {
        var normalized = settings && typeof settings === "object" ? settings : {};
        root._originalSettings = normalized;
        root.modeDraft = Math.round(Number(normalized.mode)) === 1 ? 1 : 0;
        root.autoResizeDraft = normalized.auto_resize === undefined
            ? true
            : Boolean(normalized.auto_resize);
        valueEditor.text = String(normalized.value === undefined || normalized.value === null
            ? ""
            : normalized.value);
        root.visible = true;
        Qt.callLater(function() {
            valueEditor.forceActiveFocus();
            valueEditor.cursorPosition = valueEditor.length;
        });
    }

    function acceptEdit() {
        var original = root._originalSettings || {};
        root.visible = false;
        root.accepted({
            "value": String(valueEditor.text || ""),
            "mode": root.modeDraft,
            "font_size": original.font_size === undefined ? 12 : original.font_size,
            "alignment": original.alignment === undefined ? 2 : original.alignment,
            "auto_resize": root.autoResizeDraft,
            "parse_numbers": original.parse_numbers === undefined
                ? false
                : Boolean(original.parse_numbers)
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

    Common.DialogSurface {
        id: dialogSurface
        anchors.fill: parent
        themePalette: root.themePalette
        title: ""
        closeButtonVisible: true
        onCloseRequested: root.cancelEdit()

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 16
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: "Mode"
                    color: root.mutedTextColor
                    font.pixelSize: 14
                }

                RowLayout {
                    Layout.preferredWidth: 96
                    spacing: 0

                    ToolButton {
                        id: textModeButton
                        objectName: "graphPanelEditorTextModeButton"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        hoverEnabled: true
                        checkable: true
                        checked: root.modeDraft === 0
                        Accessible.name: "Text mode"
                        onClicked: root.modeDraft = 0

                        contentItem: Image {
                            source: typeof uiIcons !== "undefined" && uiIcons
                                ? uiIcons.sourceSized("file-text", 18, String(root.panelTextColor))
                                : ""
                            sourceSize.width: 18
                            sourceSize.height: 18
                            fillMode: Image.PreserveAspectFit
                        }
                        background: Rectangle {
                            radius: 5
                            color: parent.checked
                                ? (root.themePalette.accent || "#15a9df")
                                : (root.themePalette.input_bg || "#ffffff")
                            border.width: 1
                            border.color: root.themePalette.input_border || "#8c939d"
                        }
                        Common.ManagedToolTip {
                            policyBridge: root.tooltipPolicyBridge
                            category: "general"
                            active: textModeButton.hovered
                            text: "Text mode\nThe whole content is interpreted as one text value."
                            delay: 280
                        }
                    }

                    ToolButton {
                        id: dataModeButton
                        objectName: "graphPanelEditorDataModeButton"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        hoverEnabled: true
                        checkable: true
                        checked: root.modeDraft === 1
                        Accessible.name: "Data mode"
                        onClicked: root.modeDraft = 1


                        contentItem: Image {
                            source: typeof uiIcons !== "undefined" && uiIcons
                                ? uiIcons.sourceSized("format-list-bulleted", 18, String(root.panelTextColor))
                                : ""
                            sourceSize.width: 18
                            sourceSize.height: 18
                            fillMode: Image.PreserveAspectFit
                        }
                        background: Rectangle {
                            radius: 5
                            color: parent.checked
                                ? (root.themePalette.accent || "#15a9df")
                                : (root.themePalette.input_bg || "#ffffff")
                            border.width: 1
                            border.color: root.themePalette.input_border || "#8c939d"
                        }
                        Common.ManagedToolTip {
                            policyBridge: root.tooltipPolicyBridge
                            category: "general"
                            active: dataModeButton.hovered
                            text: "Data mode\nEach line is interpreted as one item of a list.\nStart a line with an asterisk followed by a path description (for example * 0;1) to start a new branch. All following lines will be placed on that branch until another branch is defined."
                            delay: 280
                        }
                    }
                }
            }

            SurfaceControls.GraphSurfaceTextArea {
                id: valueEditor
                objectName: "graphPanelEditorValueField"
                Layout.fillWidth: true
                Layout.preferredHeight: 146
                host: root.host
                font.family: "Consolas"
                font.pointSize: 12
                placeholderText: root.modeDraft === 1
                    ? "One item per line; use * 0;1 to start a branch"
                    : "Enter text"
                Accessible.name: "Panel value"
                Keys.priority: Keys.BeforeItem
                Keys.onReturnPressed: function(event) {
                    if ((event.modifiers & Qt.ShiftModifier) !== 0) {
                        event.accepted = false;
                        return;
                    }
                    root.acceptEdit();
                    event.accepted = true;
                }
                Keys.onEnterPressed: function(event) {
                    if ((event.modifiers & Qt.ShiftModifier) !== 0) {
                        event.accepted = false;
                        return;
                    }
                    root.acceptEdit();
                    event.accepted = true;
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Use Shift+Enter for line breaks"
                color: root.mutedTextColor
                font.pixelSize: 11
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                CheckBox {
                    id: autoResizeCheck
                    objectName: "graphPanelEditorAutoResizeCheck"
                    Layout.preferredWidth: 105
                    text: "Auto-resize"
                    checked: root.autoResizeDraft
                    Accessible.name: "Auto-resize"
                    onToggled: root.autoResizeDraft = checked

                    indicator: Rectangle {
                        implicitWidth: 18
                        implicitHeight: 18
                        radius: 3
                        color: autoResizeCheck.checked
                            ? (root.themePalette.accent || "#15a9df")
                            : (root.themePalette.input_bg || "#ffffff")
                        border.width: 1
                        border.color: autoResizeCheck.checked
                            ? color
                            : (root.themePalette.input_border || "#8c939d")

                        Text {
                            anchors.centerIn: parent
                            visible: autoResizeCheck.checked
                            text: "✓"
                            color: "white"
                            font.pixelSize: 13
                            font.weight: Font.Bold
                        }
                    }

                    contentItem: Text {
                        text: autoResizeCheck.text
                        color: root.panelTextColor
                        font.pixelSize: 12
                        leftPadding: autoResizeCheck.indicator.width + 6
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Item { Layout.fillWidth: true }

                Common.DialogButton {
                    objectName: "graphPanelEditorCancelButton"
                    Layout.preferredWidth: 76
                    controlHeight: 36
                    themePalette: root.themePalette
                    text: "Cancel"
                    onClicked: root.cancelEdit()
                }

                Common.DialogButton {
                    objectName: "graphPanelEditorAcceptButton"
                    Layout.preferredWidth: 76
                    controlHeight: 36
                    themePalette: root.themePalette
                    text: "OK"
                    primary: true
                    onClicked: root.acceptEdit()
                }
            }
        }
    }
}
