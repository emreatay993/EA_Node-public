import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../common" as Common

FocusScope {
    id: root
    objectName: "graphSelectSettingsPopover"

    property Item host: null
    property var themePalette: ({})
    property real shadowStrength: 55
    property real shadowSoftness: 50
    property real shadowOffset: 4
    property int selectedIndexDraft: 0
    property int selectionRevision: 0

    readonly property var embeddedInteractiveRects: []
    readonly property color panelTextColor: root.themePalette.panel_title_fg || "#eef3ff"
    readonly property color mutedTextColor: root.themePalette.muted_fg || "#95a0b8"
    readonly property int checkedCount: {
        root.selectionRevision;
        return _checkedCount();
    }
    readonly property int singleCheckedIndex: {
        root.selectionRevision;
        return _singleCheckedIndex();
    }

    signal accepted(var payload)
    signal canceled()

    visible: false
    implicitWidth: 480
    implicitHeight: dialogSurface.implicitHeight
    activeFocusOnTab: true

    ListModel {
        id: optionModel
    }

    function _checkedCount() {
        var count = 0;
        for (var index = 0; index < optionModel.count; ++index) {
            if (optionModel.get(index).checked)
                ++count;
        }
        return count;
    }

    function _singleCheckedIndex() {
        var found = -1;
        for (var index = 0; index < optionModel.count; ++index) {
            if (!optionModel.get(index).checked)
                continue;
            if (found >= 0)
                return -1;
            found = index;
        }
        return found;
    }

    function _clampSelectedIndex(index) {
        return optionModel.count > 0
            ? Math.max(0, Math.min(optionModel.count - 1, Math.round(Number(index) || 0)))
            : 0;
    }

    function _setAllChecked(checked) {
        for (var index = 0; index < optionModel.count; ++index)
            optionModel.setProperty(index, "checked", Boolean(checked));
        ++root.selectionRevision;
    }

    function openWithSettings(settings) {
        var normalized = settings && typeof settings === "object" ? settings : {};
        var rows = normalized.options;
        optionModel.clear();
        if (rows && rows.length !== undefined) {
            for (var index = 0; index < rows.length; ++index) {
                var row = rows[index] || ({});
                optionModel.append({
                    "name": String(row.name === undefined || row.name === null ? "" : row.name),
                    "value": String(row.value === undefined || row.value === null ? "" : row.value),
                    "checked": false
                });
            }
        }
        if (optionModel.count === 0) {
            optionModel.append({"name": "Option A", "value": "0", "checked": false});
            optionModel.append({"name": "Option B", "value": "1", "checked": false});
        }
        root.selectedIndexDraft = root._clampSelectedIndex(normalized.selected_index);
        ++root.selectionRevision;
        root.visible = true;
        root.forceActiveFocus();
    }

    function addOption() {
        var ordinal = optionModel.count;
        var suffix = ordinal < 26 ? String.fromCharCode(65 + ordinal) : String(ordinal + 1);
        optionModel.append({"name": "Option " + suffix, "value": "", "checked": false});
        ++root.selectionRevision;
    }

    function deleteCheckedOptions() {
        var count = root.checkedCount;
        if (count <= 0 || count >= optionModel.count)
            return false;
        var oldSelected = root._clampSelectedIndex(root.selectedIndexDraft);
        var selectedWasDeleted = Boolean(optionModel.get(oldSelected).checked);
        var removedBefore = 0;
        for (var before = 0; before < oldSelected; ++before) {
            if (optionModel.get(before).checked)
                ++removedBefore;
        }
        for (var index = optionModel.count - 1; index >= 0; --index) {
            if (optionModel.get(index).checked)
                optionModel.remove(index);
        }
        root.selectedIndexDraft = selectedWasDeleted
            ? Math.min(oldSelected - removedBefore, optionModel.count - 1)
            : oldSelected - removedBefore;
        root.selectedIndexDraft = root._clampSelectedIndex(root.selectedIndexDraft);
        ++root.selectionRevision;
        return true;
    }

    function moveCheckedOption(offset) {
        var sourceIndex = root.singleCheckedIndex;
        var targetIndex = sourceIndex + Number(offset);
        if (sourceIndex < 0 || targetIndex < 0 || targetIndex >= optionModel.count)
            return false;
        var selected = root._clampSelectedIndex(root.selectedIndexDraft);
        optionModel.move(sourceIndex, targetIndex, 1);
        if (selected === sourceIndex) {
            selected = targetIndex;
        } else if (targetIndex < sourceIndex && selected >= targetIndex && selected < sourceIndex) {
            ++selected;
        } else if (targetIndex > sourceIndex && selected > sourceIndex && selected <= targetIndex) {
            --selected;
        }
        root.selectedIndexDraft = selected;
        ++root.selectionRevision;
        return true;
    }

    function acceptEdit() {
        var rows = [];
        for (var index = 0; index < optionModel.count; ++index) {
            var row = optionModel.get(index);
            rows.push({"name": String(row.name || ""), "value": String(row.value || "")});
        }
        root.visible = false;
        root.accepted({
            "options": rows,
            "selected_index": root._clampSelectedIndex(root.selectedIndexDraft)
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
        title: "Select settings"
        closeButtonVisible: true
        onCloseRequested: root.cancelEdit()

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 20
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 286
                radius: 6
                color: root.themePalette.panel_bg || "#1b1f2a"
                border.width: 1
                border.color: root.themePalette.border || "#3a3d45"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        Layout.leftMargin: 8
                        Layout.rightMargin: 8
                        spacing: 8

                        CheckBox {
                            id: headerCheck
                            objectName: "graphSelectSettingsHeaderCheck"
                            Layout.preferredWidth: 30
                            tristate: true
                            checkState: root.checkedCount === 0
                                ? Qt.Unchecked
                                : (root.checkedCount === optionModel.count ? Qt.Checked : Qt.PartiallyChecked)
                            nextCheckState: function() {
                                return headerCheck.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked;
                            }
                            Accessible.name: "Select all options"
                            onClicked: root._setAllChecked(headerCheck.checkState === Qt.Checked)
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Name"
                            color: root.panelTextColor
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }

                        Text {
                            Layout.preferredWidth: 160
                            text: "Value"
                            color: root.panelTextColor
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.themePalette.border || "#3a3d45"
                    }

                    ListView {
                        id: optionList
                        objectName: "graphSelectSettingsOptionList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: optionModel
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 48
                            color: index === root.selectedIndexDraft
                                ? Qt.alpha(root.themePalette.accent || "#60cdff", 0.10)
                                : "transparent"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                CheckBox {
                                    objectName: "graphSelectSettingsRowCheck_" + index
                                    Layout.preferredWidth: 30
                                    checked: Boolean(model.checked)
                                    Accessible.name: "Select option " + (index + 1)
                                    onClicked: {
                                        optionModel.setProperty(index, "checked", checked);
                                        ++root.selectionRevision;
                                    }
                                }

                                Common.DialogTextField {
                                    objectName: "graphSelectSettingsNameField_" + index
                                    Layout.fillWidth: true
                                    controlHeight: 36
                                    themePalette: root.themePalette
                                    text: String(model.name || "")
                                    placeholderText: "Enter name"
                                    Accessible.name: "Option name " + (index + 1)
                                    onTextChanged: optionModel.setProperty(index, "name", text)
                                }

                                Common.DialogTextField {
                                    objectName: "graphSelectSettingsValueField_" + index
                                    Layout.preferredWidth: 160
                                    controlHeight: 36
                                    themePalette: root.themePalette
                                    text: String(model.value || "")
                                    placeholderText: "Enter value"
                                    Accessible.name: "Option value " + (index + 1)
                                    onTextChanged: optionModel.setProperty(index, "value", text)
                                }
                            }
                        }

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: root.themePalette.border || "#3a3d45"
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 46
                        Layout.leftMargin: 8
                        Layout.rightMargin: 8
                        spacing: 6

                        Common.DialogButton {
                            objectName: "graphSelectSettingsAddButton"
                            Layout.preferredWidth: 38
                            controlHeight: 34
                            themePalette: root.themePalette
                            text: "+"
                            Accessible.name: "Add option"
                            onClicked: root.addOption()
                        }

                        Common.DialogButton {
                            objectName: "graphSelectSettingsDeleteButton"
                            Layout.preferredWidth: 38
                            controlHeight: 34
                            themePalette: root.themePalette
                            text: "×"
                            enabled: root.checkedCount > 0 && root.checkedCount < optionModel.count
                            Accessible.name: "Delete selected options"
                            onClicked: root.deleteCheckedOptions()
                        }

                        Item { Layout.fillWidth: true }

                        Common.DialogButton {
                            objectName: "graphSelectSettingsMoveUpButton"
                            Layout.preferredWidth: 38
                            controlHeight: 34
                            themePalette: root.themePalette
                            text: "↑"
                            enabled: root.singleCheckedIndex > 0
                            Accessible.name: "Move selected option up"
                            onClicked: root.moveCheckedOption(-1)
                        }

                        Common.DialogButton {
                            objectName: "graphSelectSettingsMoveDownButton"
                            Layout.preferredWidth: 38
                            controlHeight: 34
                            themePalette: root.themePalette
                            text: "↓"
                            enabled: root.singleCheckedIndex >= 0
                                && root.singleCheckedIndex < optionModel.count - 1
                            Accessible.name: "Move selected option down"
                            onClicked: root.moveCheckedOption(1)
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Item { Layout.fillWidth: true }

                Common.DialogButton {
                    objectName: "graphSelectSettingsCancelButton"
                    Layout.preferredWidth: 120
                    controlHeight: 42
                    themePalette: root.themePalette
                    text: "Cancel"
                    onClicked: root.cancelEdit()
                }

                Common.DialogButton {
                    objectName: "graphSelectSettingsAcceptButton"
                    Layout.preferredWidth: 120
                    controlHeight: 42
                    themePalette: root.themePalette
                    text: "OK"
                    primary: true
                    onClicked: root.acceptEdit()
                }
            }
        }
    }
}
