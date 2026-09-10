import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common/CommentFormat.js" as CommentFormat
import "../common/TooltipCopy.js" as TooltipCopy

InspectorSectionCard {
    id: section

    property bool composerOpen: false
    property string editingId: ""
    property string editingParentId: ""
    property string editingNodeId: ""
    property string draftText: ""
    readonly property var comments: pane ? (pane.selectedNodeCommentItems || []) : []
    readonly property int commentCount: comments.length
    readonly property int openCount: {
        var count = 0;
        for (var i = 0; i < comments.length; ++i) {
            if (!comments[i] || comments[i].resolved !== true)
                count += 1;
        }
        return count;
    }

    objectName: "inspectorNodeCommentsCard"
    width: parent ? parent.width : implicitWidth
    visible: pane && pane.hasSelectedNode
    title: "Comments"
    subtitle: commentCount === 0
        ? "No comments"
        : (openCount > 0 ? openCount + " open / " + commentCount + " total" : "All resolved")

    function token(name, fallback) {
        var palette = pane ? pane.themePalette : ({});
        if (palette && palette[name] !== undefined)
            return palette[name];
        var camelName = String(name || "").replace(/_([a-z])/g, function(match, letter) { return letter.toUpperCase(); });
        return palette && palette[camelName] !== undefined ? palette[camelName] : fallback;
    }

    function commentById(commentId) {
        var normalized = String(commentId || "").trim();
        for (var i = 0; i < comments.length; ++i) {
            var item = comments[i];
            if (item && String(item.id || item.comment_id || "") === normalized)
                return item;
        }
        return null;
    }

    function beginNewComment(parentId) {
        markRead();
        composerOpen = true;
        editingId = "";
        editingParentId = String(parentId || "");
        editingNodeId = pane ? String(pane.selectedNodeId || "") : "";
        draftText = "";
        Qt.callLater(function() { bodyEditor.forceActiveFocus(); });
    }

    function editComment(commentId) {
        var item = commentById(commentId);
        if (!item)
            return;
        composerOpen = true;
        editingId = String(item.id || item.comment_id || "");
        editingParentId = String(item.parent_id || "");
        editingNodeId = pane ? String(pane.selectedNodeId || "") : "";
        draftText = String(item.body || "");
        Qt.callLater(function() { bodyEditor.forceActiveFocus(); });
    }

    function cancelEdit() {
        composerOpen = false;
        editingId = "";
        editingParentId = "";
        editingNodeId = "";
        draftText = "";
    }

    function markRead() {
        if (pane && pane.inspectorBridgeRef)
            pane.inspectorBridgeRef.mark_selected_node_comments_read();
    }

    function saveEdit() {
        if (!pane || !pane.inspectorBridgeRef)
            return;
        if (editingNodeId.length > 0 && editingNodeId !== String(pane.selectedNodeId || "")) {
            cancelEdit();
            return;
        }
        var body = String(draftText || "").trim();
        if (!body.length)
            return;
        var existing = commentById(editingId) || {};
        var storedId = pane.inspectorBridgeRef.upsert_selected_node_comment(
            editingId,
            body,
            editingParentId,
            Boolean(existing.resolved),
            existing.unread !== false,
            Boolean(existing.pinned)
        );
        if (String(storedId || "").length)
            cancelEdit();
    }

    onCommentsChanged: {
        if (composerOpen && editingNodeId.length > 0 && pane && editingNodeId !== String(pane.selectedNodeId || ""))
            cancelEdit();
    }

    Text {
        visible: commentCount === 0 && !composerOpen
        width: parent.width
        text: "No comments on the selected node."
        color: token("muted_fg", "#9aa3af")
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    Repeater {
        model: section.comments

        delegate: Item {
            id: row
            required property var modelData
            readonly property string commentId: String(modelData.id || modelData.comment_id || "")
            readonly property bool resolved: modelData.resolved === true
            readonly property bool pinned: modelData.pinned === true
            readonly property bool isReply: String(modelData.parent_id || "").length > 0
            width: parent.width
            implicitHeight: rowColumn.implicitHeight + 8
            opacity: resolved ? 0.68 : 1

            HoverHandler { id: rowHover }

            Column {
                id: rowColumn
                x: row.isReply ? 16 : 0
                width: parent.width - x
                spacing: 5

                Item {
                    id: metaRow
                    width: parent.width
                    height: 18

                    Text {
                        id: metaTime
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: CommentFormat.relativeLabel(row.modelData.created_at)
                        color: token("muted_fg", "#9aa3af")
                        font.pixelSize: 10
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Rectangle {
                            width: 18
                            height: 18
                            radius: 9
                            anchors.verticalCenter: parent.verticalCenter
                            color: Qt.alpha("#F2B84B", 0.14)
                            border.width: 1
                            border.color: Qt.alpha("#F2B84B", 0.4)

                            Text {
                                anchors.centerIn: parent
                                text: CommentFormat.initials(row.modelData.author)
                                color: "#F2B84B"
                                font.pixelSize: 8
                                font.bold: true
                            }
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(24, Math.min(implicitWidth,
                                metaRow.width - statusChip.width - metaTime.width - 42))
                            text: String(row.modelData.author || "You")
                            color: token("panel_title_fg", "#f0f4fb")
                            font.pixelSize: 11
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Rectangle {
                            id: statusChip
                            readonly property color chipFg: row.resolved ? "#64C88A" : "#F2B84B"
                            anchors.verticalCenter: parent.verticalCenter
                            height: 15
                            radius: 7.5
                            width: chipLabel.implicitWidth + 12
                            color: Qt.alpha(chipFg, 0.14)
                            border.width: 1
                            border.color: Qt.alpha(chipFg, 0.45)

                            Text {
                                id: chipLabel
                                anchors.centerIn: parent
                                text: row.pinned ? "Pinned" : (row.resolved ? "Resolved" : "Open")
                                color: statusChip.chipFg
                                font.pixelSize: 9
                                font.bold: true
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: String(row.modelData.body || "")
                    color: token("tab_fg", "#dce3ee")
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }

                Flow {
                    width: parent.width
                    spacing: 4
                    opacity: rowHover.hovered ? 1.0 : 0.4
                    Behavior on opacity { NumberAnimation { duration: 120 } }

                    InspectorButton {
                        pane: section.pane
                        compact: true
                        width: 32
                        text: ""
                        iconName: "reply"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.reply")
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.reply")
                        onClicked: section.beginNewComment(row.commentId)
                    }

                    InspectorButton {
                        pane: section.pane
                        compact: true
                        width: 32
                        text: ""
                        iconName: "edit"
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.edit_comment")
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.edit_comment")
                        onClicked: section.editComment(row.commentId)
                    }

                    InspectorButton {
                        pane: section.pane
                        compact: true
                        width: 32
                        text: ""
                        iconName: row.pinned ? "pin-off" : "pin"
                        tooltipText: row.pinned
                            ? TooltipCopy.text(tooltipCopyBridge, "nodes.comments.unpin")
                            : TooltipCopy.text(tooltipCopyBridge, "nodes.comments.pin")
                        tooltipCategory: row.pinned
                            ? TooltipCopy.category(tooltipCopyBridge, "nodes.comments.unpin")
                            : TooltipCopy.category(tooltipCopyBridge, "nodes.comments.pin")
                        onClicked: section.pane.inspectorBridgeRef.set_selected_node_comment_pinned(row.commentId, !row.pinned)
                    }

                    InspectorButton {
                        pane: section.pane
                        compact: true
                        width: 32
                        text: ""
                        iconName: row.resolved ? "rotate-clockwise" : "check"
                        tooltipText: row.resolved
                            ? TooltipCopy.text(tooltipCopyBridge, "nodes.comments.reopen")
                            : TooltipCopy.text(tooltipCopyBridge, "nodes.comments.resolve")
                        tooltipCategory: row.resolved
                            ? TooltipCopy.category(tooltipCopyBridge, "nodes.comments.reopen")
                            : TooltipCopy.category(tooltipCopyBridge, "nodes.comments.resolve")
                        onClicked: section.pane.inspectorBridgeRef.set_selected_node_comment_resolved(row.commentId, !row.resolved)
                    }

                    InspectorButton {
                        pane: section.pane
                        compact: true
                        width: 32
                        text: ""
                        iconName: "delete"
                        destructive: true
                        tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.delete_comment")
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.delete_comment")
                        onClicked: section.pane.inspectorBridgeRef.remove_selected_node_comment(row.commentId)
                    }
                }
            }
        }
    }

    Rectangle {
        visible: composerOpen
        width: parent.width
        height: composerColumn.implicitHeight + 14
        radius: 8
        color: token("input_bg", "#24262c")
        border.width: 1
        border.color: token("input_border", "#4a4f5a")

        Column {
            id: composerColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 7
            spacing: 7

            TextArea {
                id: bodyEditor
                objectName: "inspectorNodeCommentBodyEditor"
                width: parent.width
                height: 76
                text: section.draftText
                placeholderText: section.editingParentId.length > 0 ? "Reply..." : "Comment..."
                wrapMode: TextArea.Wrap
                color: token("input_fg", "#f0f2f5")
                placeholderTextColor: token("muted_fg", "#9aa3af")
                font.pixelSize: 12
                selectByMouse: true
                onTextChanged: section.draftText = text
                background: Rectangle {
                    radius: 6
                    color: token("panel_bg", "#1b1d22")
                    border.color: token("input_border", "#4a4f5a")
                    border.width: 1
                }
            }

            Row {
                width: parent.width
                spacing: 6

                InspectorButton {
                    pane: section.pane
                    compact: true
                    width: 76
                    text: section.editingId.length > 0 ? "Save" : "Post"
                    iconName: "send"
                    onClicked: section.saveEdit()
                }

                InspectorButton {
                    pane: section.pane
                    compact: true
                    width: 74
                    text: "Cancel"
                    onClicked: section.cancelEdit()
                }
            }
        }
    }

    Row {
        visible: !composerOpen
        width: parent.width
        spacing: 6

        InspectorButton {
            objectName: "inspectorAddCommentButton"
            pane: section.pane
            width: openCount > 0 ? (parent.width - parent.spacing) / 2 : parent.width
            text: "Add comment"
            iconName: "plus"
            onClicked: section.beginNewComment("")
        }

        InspectorButton {
            visible: openCount > 0
            pane: section.pane
            width: (parent.width - parent.spacing) / 2
            text: "Resolve all"
            iconName: "check"
            onClicked: section.pane.inspectorBridgeRef.resolve_all_selected_node_comments()
        }
    }
}
