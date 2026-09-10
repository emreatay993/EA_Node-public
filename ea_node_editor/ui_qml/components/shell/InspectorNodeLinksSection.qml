import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common
import "../common/TooltipCopy.js" as TooltipCopy

InspectorSectionCard {
    id: section

    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    property alias editorOpen: linkEditorForm.editorOpen
    property alias editingId: linkEditorForm.editingId
    property alias editingKind: linkEditorForm.editingKind
    property alias editingTitle: linkEditorForm.editingTitle
    property alias editingTarget: linkEditorForm.editingTarget
    property alias editingSubtitle: linkEditorForm.editingSubtitle
    property alias editingTargetWorkspaceId: linkEditorForm.editingTargetWorkspaceId
    property alias editingTargetNodeId: linkEditorForm.editingTargetNodeId
    property alias pickModeActive: linkEditorForm.pickModeActive
    readonly property bool editingNodeTarget: linkEditorForm.editingNodeTarget
    readonly property bool editingWorkspaceTarget: linkEditorForm.editingWorkspaceTarget
    readonly property bool editingStructuredTarget: linkEditorForm.editingStructuredTarget
    readonly property int linkCount: pane ? pane.selectedNodeLinkItems.length : 0

    signal pickTargetRequested(string kind)
    signal pickTargetCancelled()

    objectName: "inspectorNodeLinksCard"
    width: parent ? parent.width : implicitWidth
    visible: pane && pane.hasSelectedNode
    title: "Links"
    subtitle: linkCount === 1 ? "1 linked target" : linkCount + " linked targets"

    function token(name, fallback) {
        var palette = pane ? pane.themePalette : ({});
        return palette && palette[name] !== undefined ? palette[name] : fallback;
    }

    function iconSource(name, size, color) {
        if (!uiIconsRef || !uiIconsRef.has(name))
            return "";
        return uiIconsRef.sourceSized(name, size, String(color));
    }

    function kindLabel(kind) {
        var normalized = String(kind || "url").toLowerCase();
        if (normalized === "file")
            return "File";
        if (normalized === "folder")
            return "Folder";
        if (normalized === "workspace")
            return "Workspace";
        if (normalized === "node")
            return "Node";
        return "Web";
    }

    function kindIcon(kind) {
        var normalized = String(kind || "url").toLowerCase();
        if (normalized === "file")
            return "file-text";
        if (normalized === "folder")
            return "folder";
        if (normalized === "workspace")
            return "layout-dashboard";
        if (normalized === "node")
            return "hierarchy-2";
        return "world-www";
    }

    function applyPickedTarget(kind, workspaceId, nodeId, label, subtitle) {
        return linkEditorForm.applyPickedTarget(kind, workspaceId, nodeId, label, subtitle);
    }

    function cancelTargetPick() {
        return linkEditorForm.resumeAfterPickCancel();
    }

    function clearPickMode() {
        return cancelTargetPick();
    }

    function beginAdd() {
        linkEditorForm.beginAdd();
    }

    function beginEdit(item) {
        linkEditorForm.beginEdit(item);
    }

    function cancelEdit() {
        linkEditorForm.cancelEdit();
    }

    function saveEdit() {
        return linkEditorForm.requestSave();
    }

    Text {
        width: parent.width
        visible: section.linkCount === 0 && !section.editorOpen
        text: "No links on the selected node."
        color: section.token("muted_fg", "#9aa3af")
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    Column {
        objectName: "inspectorNodeLinksList"
        width: parent.width
        spacing: 4

        Repeater {
            model: section.pane ? section.pane.selectedNodeLinkItems : []

            delegate: Rectangle {
                id: row
                objectName: "inspectorNodeLinkRow_" + String(modelData.id || "")
                width: parent ? parent.width : 0
                height: 56
                radius: 8
                color: rowMouse.containsMouse ? section.token("hover", "#33373f") : "transparent"

                readonly property color typeColor: modelData.type_color || section.token("accent", "#60CDFF")

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    spacing: 8

                    Rectangle {
                        width: 32
                        height: 32
                        radius: 7
                        anchors.verticalCenter: parent.verticalCenter
                        color: Qt.alpha(row.typeColor, 0.18)

                        Image {
                            anchors.centerIn: parent
                            source: section.iconSource(String(modelData.icon || section.kindIcon(modelData.kind)), 17, row.typeColor)
                            width: 17
                            height: 17
                            fillMode: Image.PreserveAspectFit
                            sourceSize.width: 17
                            sourceSize.height: 17
                        }
                    }

                    Column {
                        width: Math.max(20, parent.width - 32 - 8 - actionRow.width - 8)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Text {
                            width: parent.width
                            text: String(modelData.title || "")
                            color: section.token("panel_title_fg", "#f0f4fb")
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }

                        Text {
                            width: parent.width
                            text: String(modelData.type_label || section.kindLabel(modelData.kind))
                                + (String(modelData.breadcrumb || "").length > 0 ? " - " + String(modelData.breadcrumb || "") : "")
                            color: section.token("muted_fg", "#9aa3af")
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }

                    Row {
                        id: actionRow
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        opacity: rowMouse.containsMouse ? 1.0 : 0.72

                        LinkActionButton {
                            objectName: "inspectorNodeLinkMoveUpButton_" + String(modelData.id || "")
                            iconName: "chevron-up"
                            enabled: Boolean(modelData.can_move_up)
                            onClicked: section.pane.inspectorBridgeRef.move_selected_node_link(String(modelData.id || ""), -1)
                        }

                        LinkActionButton {
                            objectName: "inspectorNodeLinkMoveDownButton_" + String(modelData.id || "")
                            iconName: "chevron-down"
                            enabled: Boolean(modelData.can_move_down)
                            onClicked: section.pane.inspectorBridgeRef.move_selected_node_link(String(modelData.id || ""), 1)
                        }

                        LinkActionButton {
                            objectName: "inspectorNodeLinkOpenButton_" + String(modelData.id || "")
                            iconName: "external-link"
                            onClicked: section.pane.inspectorBridgeRef.open_selected_node_link(String(modelData.id || ""))
                        }

                        LinkActionButton {
                            objectName: "inspectorNodeLinkEditButton_" + String(modelData.id || "")
                            iconName: "edit"
                            onClicked: section.beginEdit(modelData)
                        }

                        LinkActionButton {
                            objectName: "inspectorNodeLinkRemoveButton_" + String(modelData.id || "")
                            iconName: "x"
                            danger: true
                            onClicked: section.pane.inspectorBridgeRef.remove_selected_node_link(String(modelData.id || ""))
                        }
                    }
                }

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.NoButton
                }
            }
        }
    }

    Common.NodeLinkEditorForm {
        id: linkEditorForm
        width: parent.width
        objectNamePrefix: "inspectorNodeLink"
        themePalette: section.pane ? section.pane.themePalette : ({})
        selectedSurfaceColor: section.pane ? section.pane.selectedSurfaceColor : section.token("accent", "#60CDFF")
        cardBackgroundColor: section.pane ? section.pane.cardBackgroundColor : section.token("panel_alt_bg", "#24262c")
        uiIconsRef: section.uiIconsRef
        nodeOptions: section.pane ? section.pane.selectedNodeLinkNodeOptions : []
        workspaceOptions: section.pane ? section.pane.selectedNodeLinkWorkspaceOptions : []

        onSaveRequested: function(draft) {
            if (!section.pane || !section.pane.inspectorBridgeRef)
                return;
            var storedId = section.pane.inspectorBridgeRef.upsert_selected_node_link(
                String(draft.id || ""),
                String(draft.kind || "url"),
                String(draft.title || ""),
                String(draft.target || ""),
                String(draft.subtitle || ""),
                String(draft.target_workspace_id || ""),
                String(draft.target_node_id || "")
            );
            linkEditorForm.completeSave(storedId);
        }

        onPickTargetRequested: function(kind) { section.pickTargetRequested(kind); }
        onPickTargetCancelled: section.pickTargetCancelled()
    }

    InspectorButton {
        pane: section.pane
        objectName: "inspectorAddLinkButton"
        width: parent.width
        visible: !section.editorOpen
        iconName: "plus"
        text: "Add link"
        tooltipText: TooltipCopy.text(tooltipCopyBridge, "inspector.node_links.add")
        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.node_links.add")
        onClicked: section.beginAdd()
    }

    component LinkActionButton: Rectangle {
        id: action
        property string iconName: ""
        property bool danger: false
        signal clicked()
        width: 26
        height: 26
        radius: 6
        opacity: enabled ? 1.0 : 0.35
        color: mouse.containsMouse
            ? (danger ? Qt.rgba(1.0, 0.23, 0.23, 0.14) : section.token("pressed", "#2d3139"))
            : "transparent"

        Image {
            anchors.centerIn: parent
            source: section.iconSource(
                action.iconName,
                15,
                action.danger && mouse.containsMouse ? "#ff7a7a" : section.token("muted_fg", "#9aa3af")
            )
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

}
