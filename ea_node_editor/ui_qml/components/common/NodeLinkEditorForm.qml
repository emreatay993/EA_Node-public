import QtQuick 2.15
import QtQuick.Controls 2.15

FocusScope {
    id: form

    property var themePalette: ({})
    property var uiIconsRef: null
    property color selectedSurfaceColor: token("inspector_selected_bg", token("accent", "#60CDFF"))
    property color cardBackgroundColor: token("inspector_card_bg", token("panel_alt_bg", "#24262c"))
    property var nodeOptions: []
    property var workspaceOptions: []
    property string objectNamePrefix: "nodeLink"
    property bool hideWhilePicking: false

    property bool editorOpen: false
    property string editingId: ""
    property string editingKind: "url"
    property string editingTitle: ""
    property string editingTarget: ""
    property string editingSubtitle: ""
    property string editingTargetWorkspaceId: ""
    property string editingTargetNodeId: ""
    property bool pickModeActive: false

    readonly property bool editingNodeTarget: String(editingKind || "").toLowerCase() === "node"
    readonly property bool editingWorkspaceTarget: String(editingKind || "").toLowerCase() === "workspace"
    readonly property bool editingStructuredTarget: editingNodeTarget || editingWorkspaceTarget
    readonly property var linkKindOptions: [
        { label: "Web", value: "url" },
        { label: "File", value: "file" },
        { label: "Folder", value: "folder" },
        { label: "Workspace", value: "workspace" },
        { label: "Node", value: "node" }
    ]
    readonly property var linkKindLabels: ["Web", "File", "Folder", "Workspace", "Node"]

    signal saveRequested(var draft)
    signal pickTargetRequested(string kind)
    signal pickTargetCancelled()
    signal editorClosed(bool saved)

    objectName: objectNamePrefix + "EditorForm"
    visible: editorOpen && (!pickModeActive || !hideWhilePicking)
    implicitHeight: editorSurface.implicitHeight
    height: visible ? implicitHeight : 0

    function token(name, fallback) {
        var palette = form.themePalette || {};
        return palette && palette[name] !== undefined ? palette[name] : fallback;
    }

    function iconSource(name, size, color) {
        if (!uiIconsRef || !uiIconsRef.has(name))
            return "";
        return uiIconsRef.sourceSized(name, size, String(color));
    }

    function linkKindIndex(kind) {
        var normalized = String(kind || "url").toLowerCase();
        for (var index = 0; index < linkKindOptions.length; ++index) {
            if (String(linkKindOptions[index].value) === normalized)
                return index;
        }
        return 0;
    }

    function _targetOptions() {
        if (editingNodeTarget)
            return nodeOptions || [];
        if (editingWorkspaceTarget)
            return workspaceOptions || [];
        return [];
    }

    function currentTarget() {
        if (editingNodeTarget)
            return String(editingTargetNodeId || editingTarget || "").trim();
        if (editingWorkspaceTarget)
            return String(editingTargetWorkspaceId || editingTarget || "").trim();
        return String(editingTarget || "").trim();
    }

    function _findOption(kind, workspaceId, nodeId) {
        var options = kind === "node" ? (nodeOptions || []) : (workspaceOptions || []);
        var normalizedWorkspaceId = String(workspaceId || "").trim();
        var normalizedNodeId = String(nodeId || "").trim();
        for (var index = 0; index < options.length; ++index) {
            var option = options[index];
            if (!option)
                continue;
            if (kind === "node") {
                if (String(option.target_node_id || option.target || "").trim() === normalizedNodeId
                        && String(option.target_workspace_id || "").trim() === normalizedWorkspaceId)
                    return option;
            } else if (String(option.target_workspace_id || option.target || "").trim() === normalizedWorkspaceId) {
                return option;
            }
        }
        return null;
    }

    function _setEditingKind(kind, resetTarget) {
        var normalized = String(kind || "url").toLowerCase();
        if (editingKind === normalized)
            return;
        editingKind = normalized;
        if (pickModeActive)
            cancelTargetPick();
        if (resetTarget) {
            editingTarget = "";
            editingTargetWorkspaceId = "";
            editingTargetNodeId = "";
            editingSubtitle = "";
        }
    }

    function selectTargetOption(option) {
        if (!option)
            return;
        if (editingNodeTarget) {
            editingTargetNodeId = String(option.target_node_id || option.target || "").trim();
            editingTargetWorkspaceId = String(option.target_workspace_id || "").trim();
            editingTarget = editingTargetNodeId;
        } else if (editingWorkspaceTarget) {
            editingTargetWorkspaceId = String(option.target_workspace_id || option.target || "").trim();
            editingTargetNodeId = "";
            editingTarget = editingTargetWorkspaceId;
        }
        var label = String(option.label || option.title || "").trim();
        var subtitle = String(option.subtitle || "").trim();
        if (!String(editingTitle || "").trim().length && label.length)
            editingTitle = label;
        if (!String(editingSubtitle || "").trim().length && subtitle.length)
            editingSubtitle = subtitle;
    }

    function applyPickedTarget(kind, workspaceId, nodeId, label, subtitle) {
        var normalizedKind = String(kind || "").toLowerCase();
        if (normalizedKind !== "node" && normalizedKind !== "workspace")
            return false;
        if (!editorOpen)
            editorOpen = true;
        editingKind = normalizedKind;
        var option = _findOption(normalizedKind, workspaceId, normalizedKind === "node" ? nodeId : "");
        if (!option) {
            option = {
                "kind": normalizedKind,
                "target": normalizedKind === "node" ? String(nodeId || "") : String(workspaceId || ""),
                "target_node_id": String(nodeId || ""),
                "target_workspace_id": String(workspaceId || ""),
                "label": String(label || ""),
                "title": String(label || ""),
                "subtitle": String(subtitle || "")
            };
        }
        selectTargetOption(option);
        pickModeActive = false;
        Qt.callLater(function() { linkTargetPicker.focusSearch(); });
        return true;
    }

    function requestPickTarget() {
        if (!editingStructuredTarget)
            return false;
        pickModeActive = true;
        pickTargetRequested(editingKind);
        return true;
    }

    function cancelTargetPick() {
        if (!pickModeActive)
            return false;
        pickModeActive = false;
        pickTargetCancelled();
        Qt.callLater(function() { linkTargetPicker.focusSearch(); });
        return true;
    }

    function resumeAfterPickCancel() {
        if (!pickModeActive)
            return false;
        pickModeActive = false;
        Qt.callLater(function() { linkTargetPicker.focusSearch(); });
        return true;
    }

    function beginAdd() {
        editingId = "";
        editingKind = "url";
        editingTitle = "";
        editingTarget = "";
        editingSubtitle = "";
        editingTargetWorkspaceId = "";
        editingTargetNodeId = "";
        pickModeActive = false;
        editorOpen = true;
        Qt.callLater(function() {
            titleField.forceActiveFocus();
            titleField.selectAll();
        });
    }

    function beginEdit(item) {
        var source = item || {};
        editingId = String(source.id || "");
        editingKind = String(source.kind || "url");
        editingTitle = String(source.title || "");
        editingTarget = String(source.target || "");
        editingSubtitle = String(source.subtitle || "");
        editingTargetWorkspaceId = String(source.target_workspace_id || "");
        editingTargetNodeId = String(source.target_node_id || "");
        if (editingKind === "node" && !editingTargetNodeId.length)
            editingTargetNodeId = editingTarget;
        if (editingKind === "workspace" && !editingTargetWorkspaceId.length)
            editingTargetWorkspaceId = editingTarget;
        pickModeActive = false;
        editorOpen = true;
        Qt.callLater(function() {
            titleField.forceActiveFocus();
            titleField.selectAll();
        });
    }

    function _resetEditor() {
        editorOpen = false;
        pickModeActive = false;
        editingId = "";
        editingKind = "url";
        editingTitle = "";
        editingTarget = "";
        editingSubtitle = "";
        editingTargetWorkspaceId = "";
        editingTargetNodeId = "";
    }

    function cancelEdit() {
        if (pickModeActive)
            pickTargetCancelled();
        _resetEditor();
        editorClosed(false);
    }

    function requestSave() {
        var target = currentTarget();
        if (!target.length)
            return false;
        saveRequested({
            "id": editingId,
            "kind": editingKind,
            "title": editingTitle,
            "target": target,
            "subtitle": editingSubtitle,
            "target_workspace_id": editingNodeTarget ? editingTargetWorkspaceId : "",
            "target_node_id": editingNodeTarget ? editingTargetNodeId : ""
        });
        return true;
    }

    function completeSave(storedId) {
        if (!String(storedId || "").length)
            return false;
        _resetEditor();
        editorClosed(true);
        return true;
    }

    Rectangle {
        id: editorSurface
        width: parent.width
        radius: 9
        color: form.token("input_bg", "#24262c")
        border.color: form.token("border", "#3a3d45")
        border.width: 1
        implicitHeight: editorColumn.implicitHeight + 20

        Column {
            id: editorColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 8

            StyledComboBox {
                width: parent.width
                model: form.linkKindLabels
                currentIndex: form.linkKindIndex(form.editingKind)
                onActivated: function(index) {
                    form._setEditingKind(String(form.linkKindOptions[index].value || "url"), true);
                }
            }

            DialogTextField {
                id: titleField
                objectName: form.objectNamePrefix + "TitleField"
                width: parent.width
                themePalette: form.themePalette
                controlHeight: 34
                text: form.editingTitle
                placeholderText: "Title"
                onTextChanged: form.editingTitle = text
            }

            Row {
                width: parent.width
                spacing: 6
                visible: form.editingStructuredTarget

                LinkTargetPicker {
                    id: linkTargetPicker
                    width: parent.width - pickButton.width - parent.spacing
                    options: form._targetOptions()
                    selectedTarget: form.currentTarget()
                    selectedWorkspaceId: form.editingTargetWorkspaceId
                    placeholderText: form.editingNodeTarget ? "Search nodes..." : "Choose workspace..."
                    onOptionPicked: function(option) { form.selectTargetOption(option); }
                }

                IconActionButton {
                    id: pickButton
                    objectName: form.objectNamePrefix + "PickTargetButton"
                    iconName: "focus"
                    width: 34
                    height: 34
                    onClicked: form.requestPickTarget()
                }
            }

            DialogTextField {
                width: parent.width
                themePalette: form.themePalette
                controlHeight: 34
                visible: !form.editingStructuredTarget
                text: form.editingTarget
                placeholderText: "URL or path"
                onTextChanged: form.editingTarget = text
            }

            DialogTextField {
                width: parent.width
                themePalette: form.themePalette
                controlHeight: 34
                text: form.editingSubtitle
                placeholderText: "Subtitle"
                onTextChanged: form.editingSubtitle = text
            }

            Row {
                width: parent.width
                spacing: 6

                DialogButton {
                    objectName: form.objectNamePrefix + "SaveButton"
                    text: "Save"
                    width: (parent.width - 6) / 2
                    themePalette: form.themePalette
                    controlHeight: 36
                    enabled: form.currentTarget().length > 0
                    onClicked: form.requestSave()
                }

                DialogButton {
                    objectName: form.objectNamePrefix + "CancelButton"
                    text: "Cancel"
                    width: (parent.width - 6) / 2
                    themePalette: form.themePalette
                    controlHeight: 36
                    onClicked: form.cancelEdit()
                }
            }
        }
    }

    component StyledComboBox: ComboBox {
        id: combo
        readonly property real popupMaxHeight: 240
        implicitHeight: 34
        leftPadding: 8
        rightPadding: 30
        hoverEnabled: true
        font.pixelSize: 11
        palette.buttonText: form.token("input_fg", "#f0f2f5")
        palette.text: form.token("input_fg", "#f0f2f5")
        palette.highlight: form.selectedSurfaceColor
        palette.highlightedText: form.token("panel_title_fg", "#f0f4fb")
        palette.base: form.token("input_bg", "#24262c")
        palette.window: form.cardBackgroundColor

        indicator: Text {
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: "\u25BE"
            color: form.token("muted_fg", "#9aa3af")
            font.pixelSize: 11
            font.bold: true
        }

        contentItem: Text {
            text: combo.displayText
            color: form.token("input_fg", "#f0f2f5")
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: 10
            color: form.token("input_bg", "#24262c")
            border.color: combo.activeFocus
                ? form.token("accent", "#60CDFF")
                : form.token("input_border", "#3a3d45")
            border.width: 1
        }

        delegate: ItemDelegate {
            width: ListView.view ? ListView.view.width : combo.width
            highlighted: combo.highlightedIndex === index
            contentItem: Text {
                text: modelData
                color: highlighted
                    ? form.token("panel_title_fg", "#f0f4fb")
                    : form.token("input_fg", "#f0f2f5")
                font.pixelSize: 11
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: highlighted ? form.selectedSurfaceColor : "transparent"
                radius: 7
            }
        }

        popup: Popup {
            y: combo.height + 4
            width: combo.width
            padding: 4
            background: Rectangle {
                radius: 9
                color: form.cardBackgroundColor
                border.color: form.token("input_border", "#3a3d45")
                border.width: 1
            }
            contentItem: ListView {
                clip: true
                implicitHeight: Math.min(contentHeight, combo.popupMaxHeight)
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; interactive: true }
            }
        }
    }

    component IconActionButton: Rectangle {
        id: action
        property string iconName: ""
        signal clicked()
        radius: 6
        opacity: enabled ? 1.0 : 0.35
        color: mouse.containsMouse ? form.token("pressed", "#2d3139") : "transparent"

        Image {
            anchors.centerIn: parent
            source: form.iconSource(action.iconName, 15, form.token("muted_fg", "#9aa3af"))
            width: 15
            height: 15
            fillMode: Image.PreserveAspectFit
            sourceSize.width: 15
            sourceSize.height: 15
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: action.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: {
                if (action.enabled)
                    action.clicked();
            }
        }
    }

    component LinkTargetPicker: FocusScope {
        id: picker
        property var options: []
        property string selectedTarget: ""
        property string selectedWorkspaceId: ""
        property string placeholderText: ""
        property bool suppressTextHandling: false
        readonly property var filteredOptions: picker._filteredOptions()
        signal optionPicked(var option)
        implicitHeight: pickerColumn.implicitHeight

        function focusSearch() {
            searchField.forceActiveFocus();
            searchField.selectAll();
        }

        function _optionMatches(option) {
            var query = String(searchField.text || "").trim().toLowerCase();
            if (!query.length)
                return true;
            var haystack = [
                option ? option.label : "",
                option ? option.title : "",
                option ? option.subtitle : "",
                option ? option.workspace_name : "",
                option ? option.display_name : "",
                option ? option.instance_label : ""
            ].join(" ").toLowerCase();
            return haystack.indexOf(query) >= 0;
        }

        function _filteredOptions() {
            var source = picker.options || [];
            var results = [];
            for (var index = 0; index < source.length; ++index) {
                var option = source[index];
                if (option && picker._optionMatches(option))
                    results.push(option);
            }
            return results.slice(0, 8);
        }

        function _currentOption() {
            var source = picker.options || [];
            for (var index = 0; index < source.length; ++index) {
                var option = source[index];
                if (!option)
                    continue;
                var key = String(option.target_node_id || option.target_workspace_id || option.target || "").trim();
                var workspaceId = String(option.target_workspace_id || "").trim();
                if (key === String(picker.selectedTarget || "").trim()
                        && (!picker.selectedWorkspaceId.length || !workspaceId.length || workspaceId === picker.selectedWorkspaceId))
                    return option;
            }
            return null;
        }

        function _setSearchText(value) {
            picker.suppressTextHandling = true;
            searchField.text = String(value || "");
            picker.suppressTextHandling = false;
        }

        function _syncTextToSelection() {
            if (searchField.activeFocus)
                return;
            var option = picker._currentOption();
            picker._setSearchText(option ? String(option.label || option.title || "") : "");
        }

        function _commitOption(option) {
            if (!option)
                return;
            picker.optionPicked(option);
            picker._setSearchText(String(option.label || option.title || ""));
            picker.focusSearch();
        }

        Component.onCompleted: picker._syncTextToSelection()
        onSelectedTargetChanged: picker._syncTextToSelection()
        onSelectedWorkspaceIdChanged: picker._syncTextToSelection()
        onOptionsChanged: picker._syncTextToSelection()

        Column {
            id: pickerColumn
            width: parent.width
            spacing: 4

            Rectangle {
                width: parent.width
                height: 34
                radius: 9
                color: form.token("input_bg", "#24262c")
                border.color: picker.activeFocus
                    ? form.token("accent", "#60CDFF")
                    : form.token("input_border", "#3a3d45")
                border.width: 1

                TextField {
                    id: searchField
                    objectName: form.objectNamePrefix + "TargetSearchField"
                    anchors.fill: parent
                    leftPadding: 8
                    rightPadding: 30
                    topPadding: 8
                    bottomPadding: 8
                    selectByMouse: true
                    color: form.token("input_fg", "#f0f2f5")
                    selectionColor: form.selectedSurfaceColor
                    selectedTextColor: form.token("panel_title_fg", "#f0f4fb")
                    placeholderText: picker.placeholderText
                    placeholderTextColor: form.token("muted_fg", "#6f7782")
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                    background: null

                    onActiveFocusChanged: {
                        if (activeFocus)
                            selectAll();
                        else
                            picker._syncTextToSelection();
                    }
                    onAccepted: {
                        if (picker.filteredOptions.length > 0)
                            picker._commitOption(picker.filteredOptions[0]);
                    }
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: searchField.activeFocus ? "\u25B2" : "\u25BE"
                    color: form.token("muted_fg", "#6f7782")
                    font.pixelSize: 10
                }
            }

            Column {
                width: parent.width
                spacing: 3
                visible: searchField.activeFocus

                Repeater {
                    model: picker.filteredOptions
                    delegate: Rectangle {
                        id: optionRow
                        required property var modelData
                        width: parent.width
                        height: 44
                        radius: 7
                        color: optionMouse.containsMouse
                            ? form.token("hover", "#33373f")
                            : form.token("input_bg", "#24262c")
                        border.color: form.token("border", "#3a3d45")
                        border.width: 1

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 2
                            Text {
                                width: parent.width
                                text: String(optionRow.modelData.label || optionRow.modelData.title || "")
                                color: form.token("panel_title_fg", "#f0f4fb")
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                text: String(optionRow.modelData.subtitle || "")
                                color: form.token("muted_fg", "#9aa3af")
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            id: optionMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: picker._commitOption(optionRow.modelData)
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: picker.filteredOptions.length === 0
                    text: "No matching targets"
                    color: form.token("muted_fg", "#9aa3af")
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
