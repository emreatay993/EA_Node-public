import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Effects
import "../../common" as Common
import "../../common/CommentFormat.js" as CommentFormat
import "../../common/TooltipCopy.js" as TooltipCopy
import "../GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

Item {
    id: root
    objectName: "graphNodeCommentPopoverLayer"

    property var canvasItem: null
    property var viewBridge: null
    property var sceneStateBridge: null
    property var sceneModel: []
    property var badgeModel: []
    property var visibleSceneRectPayload: ({})
    property var hostResolver: null
    property var themePalette: ({})
    property var liveNodeGeometry: canvasItem ? canvasItem.liveNodeGeometry : ({})

    property var activeNodeData: null
    property string activeNodeId: ""
    property bool editorOpen: false
    property bool cardPointerInside: false
    property string editingId: ""
    property string editingParentId: ""
    property string draftText: ""
    readonly property real badgeGap: 6
    readonly property real bottomNeutralPortClearance: 12

    width: canvasItem ? canvasItem.worldSize : 0
    height: canvasItem ? canvasItem.worldSize : 0
    transformOrigin: Item.TopLeft
    scale: viewBridge ? viewBridge.zoom_value : 1.0
    x: canvasItem
        ? canvasItem.width * 0.5 - ((viewBridge ? viewBridge.center_x : 0) + canvasItem.worldOffset) * scale
        : 0.0
    y: canvasItem
        ? canvasItem.height * 0.5 - ((viewBridge ? viewBridge.center_y : 0) + canvasItem.worldOffset) * scale
        : 0.0
    z: root.activeNodeData || root.editorOpen ? 38 : 34

    function token(name, fallback) {
        var palette = root.themePalette || {};
        return palette && palette[name] !== undefined ? palette[name] : fallback;
    }

    function iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, String(color));
    }

    function finite(value, fallback) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : Number(fallback || 0);
    }

    function commandBridge() {
        if (!canvasItem)
            return null;
        return canvasItem.canvasCommandBridgeRef
            || canvasItem.canvasCommandBridge
            || canvasItem.sceneCommandBridge
            || null;
    }

    function nodeIdForData(nodeData) {
        return String(nodeData ? nodeData.node_id || "" : "").trim();
    }

    function nodeDataForId(nodeId) {
        var normalized = String(nodeId || "").trim();
        var model = root.sceneModel || [];
        if (!normalized)
            return null;
        var count = model.length !== undefined
            ? Number(model.length)
            : (model.count !== undefined ? Number(model.count) : 0);
        if (!isFinite(count) || count <= 0)
            return null;
        for (var i = 0; i < count; i++) {
            var item = model[i];
            if (!item && model.get)
                item = model.get(i);
            if (item && String(item.node_id || "") === normalized)
                return item;
        }
        return null;
    }

    function commentsForNode(nodeData) {
        var comments = nodeData ? nodeData.comments : null;
        if (!comments || typeof comments === "string")
            return [];
        var count = comments.length !== undefined
            ? Number(comments.length)
            : (comments.count !== undefined ? Number(comments.count) : 0);
        return isFinite(count) && count > 0 ? comments : [];
    }

    function linksForNode(nodeData) {
        var links = nodeData ? nodeData.links : null;
        if (!links || typeof links === "string")
            return [];
        var count = links.length !== undefined
            ? Number(links.length)
            : (links.count !== undefined ? Number(links.count) : 0);
        return isFinite(count) && count > 0 ? links : [];
    }

    function badgeForNode(nodeData) {
        return nodeData && nodeData.comment_badge ? nodeData.comment_badge : ({ count: 0, open_count: 0 });
    }

    function commentForId(commentId) {
        var normalized = String(commentId || "").trim();
        var comments = commentsForNode(root.activeNodeData);
        for (var i = 0; i < comments.length; ++i) {
            var item = comments[i];
            if (item && String(item.id || item.comment_id || "") === normalized)
                return item;
        }
        return null;
    }

    function hostForNode(nodeData) {
        var nodeId = nodeIdForData(nodeData);
        if (!nodeId || !hostResolver)
            return null;
        return hostResolver(nodeId);
    }

    function dragDxForNode(nodeData) {
        var nodeId = nodeIdForData(nodeData);
        if (!nodeId)
            return 0;
        if (!canvasItem || !canvasItem.liveDragNodeLookup || !canvasItem.liveDragNodeLookup[nodeId])
            return 0;
        return finite(canvasItem.liveDragDx, 0);
    }

    function dragDyForNode(nodeData) {
        var nodeId = nodeIdForData(nodeData);
        if (!nodeId)
            return 0;
        if (!canvasItem || !canvasItem.liveDragNodeLookup || !canvasItem.liveDragNodeLookup[nodeId])
            return 0;
        return finite(canvasItem.liveDragDy, 0);
    }

    function liveGeometryForNode(nodeData) {
        var nodeId = nodeIdForData(nodeData);
        if (!nodeId || !liveNodeGeometry)
            return null;
        return liveNodeGeometry[nodeId] || null;
    }

    function nodeX(nodeData) {
        var host = hostForNode(nodeData);
        if (host)
            return finite(host.x, 0) + finite(host.dragTranslateX, 0);
        var live = liveGeometryForNode(nodeData);
        return finite(live ? live.x : (nodeData && nodeData.x !== undefined ? nodeData.x : 0), 0)
            + finite(canvasItem ? canvasItem.worldOffset : 0, 0)
            + dragDxForNode(nodeData);
    }

    function nodeY(nodeData) {
        var host = hostForNode(nodeData);
        if (host)
            return finite(host.y, 0) + finite(host.dragTranslateY, 0);
        var live = liveGeometryForNode(nodeData);
        return finite(live ? live.y : (nodeData && nodeData.y !== undefined ? nodeData.y : 0), 0)
            + finite(canvasItem ? canvasItem.worldOffset : 0, 0)
            + dragDyForNode(nodeData);
    }

    function nodeWidth(nodeData) {
        var host = hostForNode(nodeData);
        if (host)
            return finite(host.width, 0);
        var live = liveGeometryForNode(nodeData);
        return finite(live ? live.width : (nodeData && nodeData.width !== undefined ? nodeData.width : 0), 0);
    }

    function nodeHeight(nodeData) {
        var host = hostForNode(nodeData);
        if (host)
            return finite(host.height, 0);
        var live = liveGeometryForNode(nodeData);
        return finite(live ? live.height : (nodeData && nodeData.height !== undefined ? nodeData.height : 0), 0);
    }

    function nodeEditable(nodeData) {
        if (!nodeData || Boolean(nodeData.read_only) || Boolean(nodeData.collapsed))
            return false;
        var locked = nodeData.locked_state || {};
        return !Boolean(locked.locked || locked.read_only);
    }

    function showPeek(nodeData, anchorX, anchorY) {
        root.activeNodeData = nodeData;
        root.activeNodeId = root.nodeIdForData(nodeData);
        root.editorOpen = false;
        root.editingId = "";
        root.editingParentId = "";
        root.draftText = "";
        dismissTimer.stop();
    }

    function openEditor(nodeData, compose, parentId, editId) {
        root.activeNodeData = nodeData;
        root.activeNodeId = root.nodeIdForData(nodeData);
        root.editorOpen = true;
        dismissTimer.stop();
        if (compose || String(editId || "").length || String(parentId || "").length)
            root.beginCompose(parentId || "", editId || "");
        else
            root.clearCompose();
        var bridge = commandBridge();
        if (bridge && bridge.mark_node_comments_read)
            bridge.mark_node_comments_read(root.activeNodeId);
    }

    function requestInspectorEditor(nodeData, compose) {
        var nodeId = root.nodeIdForData(nodeData);
        if (!nodeId || !canvasItem || !canvasItem.requestNodeCommentEditorForNode)
            return false;
        forceClearCard();
        return Boolean(canvasItem.requestNodeCommentEditorForNode(nodeId, Boolean(compose)));
    }

    function activeEditable() {
        return root.nodeEditable(root.activeNodeData);
    }

    function handleBadgeClick(nodeData, compose) {
        var prefs = canvasItem ? canvasItem.prefs : null;
        var target = prefs ? String(prefs.nodeCommentEditorDefault || "canvas_popover") : "canvas_popover";
        if (target === "inspector" && root.nodeEditable(nodeData))
            return requestInspectorEditor(nodeData, compose);
        openEditor(nodeData, compose, "", "");
        return true;
    }

    function beginCompose(parentId, editId) {
        if (!root.activeEditable())
            return;
        root.editingParentId = String(parentId || "");
        root.editingId = String(editId || "");
        var existing = commentForId(root.editingId);
        root.draftText = existing ? String(existing.body || "") : "";
        Qt.callLater(function() { commentEditor.forceActiveFocus(); });
    }

    function clearCompose() {
        root.editingId = "";
        root.editingParentId = "";
        root.draftText = "";
    }

    function saveComment() {
        var bridge = commandBridge();
        var body = String(root.draftText || "").trim();
        if (!root.activeEditable() || !bridge || !bridge.upsert_node_comment || !root.activeNodeId || !body.length)
            return false;
        var existing = commentForId(root.editingId) || {};
        var storedId = bridge.upsert_node_comment(
            root.activeNodeId,
            root.editingId,
            body,
            "",
            root.editingParentId,
            Boolean(existing.resolved),
            existing.unread !== false,
            Boolean(existing.pinned)
        );
        if (String(storedId || "").length) {
            clearCompose();
            return true;
        }
        return false;
    }

    function setResolved(commentId, resolved) {
        var bridge = commandBridge();
        return root.activeEditable() && bridge && bridge.set_node_comment_resolved
            ? Boolean(bridge.set_node_comment_resolved(root.activeNodeId, commentId, Boolean(resolved)))
            : false;
    }

    function setPinned(commentId, pinned) {
        var bridge = commandBridge();
        return root.activeEditable() && bridge && bridge.set_node_comment_pinned
            ? Boolean(bridge.set_node_comment_pinned(root.activeNodeId, commentId, Boolean(pinned)))
            : false;
    }

    function removeComment(commentId) {
        var bridge = commandBridge();
        return root.activeEditable() && bridge && bridge.remove_node_comment
            ? Boolean(bridge.remove_node_comment(root.activeNodeId, commentId))
            : false;
    }

    function resolveAll() {
        var bridge = commandBridge();
        return root.activeEditable() && bridge && bridge.resolve_all_node_comments
            ? Boolean(bridge.resolve_all_node_comments(root.activeNodeId))
            : false;
    }

    function syncActiveCard() {
        if (!root.activeNodeId)
            return;
        var nodeData = root.nodeDataForId(root.activeNodeId);
        if (!nodeData) {
            root.forceClearCard();
            return;
        }
        root.activeNodeData = nodeData;
    }

    function scheduleDismiss() {
        dismissTimer.restart();
    }

    function clearCard() {
        if (root.cardPointerInside || root.editorOpen)
            return;
        root.forceClearCard();
    }

    function forceClearCard() {
        dismissTimer.stop();
        root.cardPointerInside = false;
        root.activeNodeData = null;
        root.activeNodeId = "";
        root.editorOpen = false;
        root.clearCompose();
    }

    Timer {
        id: dismissTimer
        interval: 200
        repeat: false
        onTriggered: root.clearCard()
    }

    onSceneModelChanged: {
        root.syncActiveCard();
    }

    Connections {
        target: root.sceneStateBridge
        ignoreUnknownSignals: true

        function onNodes_changed() { root.syncActiveCard(); }
        function onScene_nodes_changed() { root.syncActiveCard(); }
        function onScope_changed() { root.forceClearCard(); }
        function onScene_scope_changed() { root.forceClearCard(); }
        function onWorkspace_changed(workspaceId) { root.forceClearCard(); }
        function onScene_workspace_changed(workspaceId) { root.forceClearCard(); }
    }

    Repeater {
        model: root.badgeModel

        delegate: Item {
            id: badgeHost
            objectName: "graphNodeCommentBadgeHost"
            readonly property var badge: root.badgeForNode(modelData)
            readonly property int count: Math.max(0, Number(badge.count || 0))
            readonly property int openCount: Math.max(0, Number(badge.open_count || 0))
            readonly property bool resolvedAll: count > 0 && openCount === 0
            readonly property bool unread: badge.unread === true
            readonly property int linkCount: root.linksForNode(modelData).length
            readonly property bool hasLinkBadge: linkCount > 0
            readonly property real linkBadgeWidth: 11 + 4 + linkCountProbe.implicitWidth + 16
            readonly property real ownBadgeWidth: pill.width
            readonly property real groupWidth: hasLinkBadge ? linkBadgeWidth + root.badgeGap + ownBadgeWidth : ownBadgeWidth
            readonly property real badgeHorizontalShift: GraphNodeSurfaceMetrics.nodeHasBottomNeutralFlowHandle(modelData)
                ? groupWidth * 0.5 + root.bottomNeutralPortClearance : 0
            readonly property real badgeX: root.nodeX(modelData) + (root.nodeWidth(modelData) - groupWidth) / 2
                + (hasLinkBadge ? linkBadgeWidth + root.badgeGap : 0)
                + badgeHorizontalShift
            readonly property real badgeY: root.nodeY(modelData) + root.nodeHeight(modelData) - height / 2

            visible: count > 0
            x: badgeX
            y: badgeY
            width: ownBadgeWidth
            height: 18
            z: 40

            Text {
                id: linkCountProbe
                visible: false
                text: badgeHost.linkCount
                font.pixelSize: 10
                font.bold: true
            }

            Rectangle {
                id: pill
                visible: badgeHost.count > 0
                width: pillRow.implicitWidth + 16
                height: 18
                radius: 9
                color: badgeHost.resolvedAll ? root.token("successSoft", "#20372a")
                    : badgeHost.unread ? root.token("comment", "#F2B84B")
                    : root.token("commentSoft", "#3c321f")
                border.width: 1
                border.color: badgeHost.resolvedAll ? root.token("success", "#64C88A")
                    : badgeHost.unread ? Qt.rgba(1, 1, 1, root.token("isDark", true) ? 0.25 : 0.0)
                    : root.token("commentBorder", "#765f2b")

                readonly property color fg: badgeHost.resolvedAll ? root.token("success", "#64C88A")
                    : badgeHost.unread ? root.token("onComment", "#241a08")
                    : root.token("comment", "#F2B84B")

                Row {
                    id: pillRow
                    anchors.centerIn: parent
                    spacing: 4

                    CommentGlyph {
                        anchors.verticalCenter: parent.verticalCenter
                        name: badgeHost.resolvedAll ? "check" : "bubbleFilled"
                        size: 11
                        color: pill.fg
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: badgeHost.count
                        color: pill.fg
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: root.showPeek(modelData, badgeHost.x + pill.width * 0.5, badgeHost.y + pill.height + 8)
                    onExited: root.scheduleDismiss()
                    onClicked: root.handleBadgeClick(modelData, false)
                }
            }

        }
    }

    Rectangle {
        id: card
        objectName: "graphNodeCommentPopover"
        readonly property bool active: !!root.activeNodeData
        readonly property var comments: root.commentsForNode(root.activeNodeData)
        readonly property var badge: root.badgeForNode(root.activeNodeData)
        readonly property int openCount: Math.max(0, Number(badge.open_count || 0))
        readonly property var viewport: root.visibleSceneRectPayload || ({})
        readonly property real viewportX: Number(viewport.x || 0) + Number(root.canvasItem ? root.canvasItem.worldOffset : 0)
        readonly property real viewportY: Number(viewport.y || 0) + Number(root.canvasItem ? root.canvasItem.worldOffset : 0)
        readonly property real viewportW: Math.max(width + 20, Number(viewport.width || root.width))
        width: 300
        height: cardColumn.implicitHeight + 28
        radius: 12
        visible: active
        opacity: active ? 1 : 0
        x: Math.max(viewportX + 10, Math.min(root.nodeX(root.activeNodeData) + root.nodeWidth(root.activeNodeData) - width - 26, viewportX + viewportW - width - 10))
        y: root.nodeY(root.activeNodeData) + root.nodeHeight(root.activeNodeData) + 12
        z: 100
        color: root.token("panelAltBg", "#24262c")
        border.width: 1
        border.color: root.token("border", "#3a3d45")

        Behavior on opacity { NumberAnimation { duration: 130 } }

        RectangularShadow {
            anchors.fill: parent
            z: -1
            offset.x: 0
            offset.y: 4
            blur: 20
            spread: 0
            radius: card.radius
            color: Qt.rgba(0, 0, 0, root.token("isDark", true) ? 0.45 : 0.20)
            cached: true
        }

        Column {
            id: cardColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 14
            spacing: 10

            Item {
                width: parent.width
                height: 32

                Rectangle {
                    id: headerChip
                    width: 30
                    height: 30
                    radius: 7
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.token("commentSoft", "#3c321f")
                    border.width: 1
                    border.color: root.token("commentBorder", "#765f2b")
                    CommentGlyph { anchors.centerIn: parent; name: "bubble"; size: 17; color: root.token("comment", "#F2B84B") }
                }

                Column {
                    anchors.left: headerChip.right
                    anchors.leftMargin: 10
                    anchors.right: headerCloseButton.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        width: parent.width
                        text: card.openCount > 0 ? "Comments · " + card.openCount + " open" : "Comments · all resolved"
                        color: root.token("appFg", "#e8e8e8")
                        font.pixelSize: 13
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: root.activeNodeData ? "on " + String(root.activeNodeData.title || "") : ""
                        color: root.token("mutedFg", "#9aa3af")
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }

                CardIconButton {
                    id: headerCloseButton
                    objectName: "graphNodeCommentPopoverCloseButton"
                    anchors.right: parent.right
                    anchors.top: parent.top
                    iconName: "x"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.close")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.close")
                    onClicked: root.forceClearCard()
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.token("border", "#3a3d45")
                opacity: 0.7
            }

            Repeater {
                model: root.editorOpen ? card.comments : (root.badgeForNode(root.activeNodeData).preview_comments || [])

                delegate: Column {
                    id: commentRow
                    required property var modelData
                    readonly property string commentId: String(modelData.id || modelData.comment_id || "")
                    readonly property bool resolved: modelData.resolved === true
                    readonly property bool pinned: modelData.pinned === true
                    width: cardColumn.width
                    spacing: 4
                    opacity: resolved ? 0.58 : 1

                    HoverHandler { id: commentHover }

                    Item {
                        id: commentMeta
                        width: parent.width
                        height: 20

                        Text {
                            id: commentTime
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: CommentFormat.relativeLabel(commentRow.modelData.created_at)
                            color: root.token("mutedFg", "#9aa3af")
                            font.pixelSize: 10
                        }

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            Rectangle {
                                width: 20
                                height: 20
                                radius: 10
                                anchors.verticalCenter: parent.verticalCenter
                                color: root.token("commentSoft", "#3c321f")
                                border.width: 1
                                border.color: root.token("commentBorder", "#765f2b")

                                Text {
                                    anchors.centerIn: parent
                                    text: CommentFormat.initials(commentRow.modelData.author)
                                    color: root.token("comment", "#F2B84B")
                                    font.pixelSize: 9
                                    font.bold: true
                                }
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(24, Math.min(implicitWidth,
                                    commentMeta.width - commentStatusChip.width - commentTime.width - 54))
                                text: String(commentRow.modelData.author || "You")
                                color: root.token("appFg", "#e8e8e8")
                                font.pixelSize: 12
                                font.bold: true
                                elide: Text.ElideRight
                            }

                            StatusChip {
                                id: commentStatusChip
                                anchors.verticalCenter: parent.verticalCenter
                                label: commentRow.pinned ? "Pinned" : (commentRow.resolved ? "Resolved" : "Open")
                                fg: commentRow.resolved ? root.token("success", "#64C88A") : root.token("comment", "#F2B84B")
                            }
                        }
                    }

                    Text {
                        x: 28
                        width: parent.width - 28
                        text: String(modelData.body || "")
                        color: resolved ? root.token("mutedFg", "#9aa3af") : root.token("inputFg", "#f0f2f5")
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        maximumLineCount: root.editorOpen ? 1000 : 2
                        elide: root.editorOpen ? Text.ElideNone : Text.ElideRight
                    }

                    Row {
                        x: 26
                        visible: root.editorOpen && root.activeEditable()
                        spacing: 2
                        opacity: commentHover.hovered ? 1.0 : 0.35
                        Behavior on opacity { NumberAnimation { duration: 120 } }

                        CardIconButton { iconName: "reply"; tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.reply"); tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.reply"); onClicked: root.beginCompose(commentId, "") }
                        CardIconButton { iconName: "edit"; tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.edit"); tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.edit"); onClicked: root.beginCompose("", commentId) }
                        CardIconButton { iconName: pinned ? "pin-off" : "pin"; tooltipText: pinned ? TooltipCopy.text(tooltipCopyBridge, "nodes.comments.unpin") : TooltipCopy.text(tooltipCopyBridge, "nodes.comments.pin"); tooltipCategory: pinned ? TooltipCopy.category(tooltipCopyBridge, "nodes.comments.unpin") : TooltipCopy.category(tooltipCopyBridge, "nodes.comments.pin"); onClicked: root.setPinned(commentId, !pinned) }
                        CardIconButton { iconName: resolved ? "rotate-clockwise" : "check"; tooltipText: resolved ? TooltipCopy.text(tooltipCopyBridge, "nodes.comments.reopen") : TooltipCopy.text(tooltipCopyBridge, "nodes.comments.resolve"); tooltipCategory: resolved ? TooltipCopy.category(tooltipCopyBridge, "nodes.comments.reopen") : TooltipCopy.category(tooltipCopyBridge, "nodes.comments.resolve"); onClicked: root.setResolved(commentId, !resolved) }
                        CardIconButton { iconName: "delete"; danger: true; tooltipText: TooltipCopy.text(tooltipCopyBridge, "nodes.comments.delete"); tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "nodes.comments.delete"); onClicked: root.removeComment(commentId) }
                    }
                }
            }

            TextArea {
                id: commentEditor
                visible: root.editorOpen && root.activeEditable()
                width: parent.width
                height: 76
                text: root.draftText
                placeholderText: root.editingParentId.length > 0 ? "Reply..." : "Comment..."
                wrapMode: TextArea.Wrap
                color: root.token("inputFg", "#f0f2f5")
                placeholderTextColor: root.token("mutedFg", "#9aa3af")
                font.pixelSize: 12
                selectByMouse: true
                onTextChanged: root.draftText = text
                background: Rectangle {
                    radius: 6
                    color: root.token("inputBg", "#22242a")
                    border.color: root.token("inputBorder", "#4a4f5a")
                    border.width: 1
                }
            }

            Row {
                spacing: 8
                visible: root.editorOpen
                CardButton { visible: root.activeEditable(); width: 60; text: root.editingId.length > 0 ? "Save" : "Post"; accent: true; onClicked: root.saveComment() }
                CardButton { visible: root.activeEditable(); width: 62; text: "New"; onClicked: root.beginCompose("", "") }
                CardButton { width: 76; text: "Resolve all"; visible: card.openCount > 0; onClicked: root.resolveAll() }
            }
        }

        HoverHandler {
            onHoveredChanged: {
                root.cardPointerInside = hovered;
                if (hovered)
                    dismissTimer.stop();
                else
                    root.scheduleDismiss();
            }
        }
    }

    component CardButton: Rectangle {
        id: control
        property string text: ""
        property bool accent: false
        property bool danger: false
        signal clicked()
        height: 26
        radius: 7
        color: accent
            ? root.token("comment", "#F2B84B")
            : (mouse.containsMouse ? root.token("hover", "#33373f") : "transparent")
        border.width: accent ? 0 : 1
        border.color: danger ? root.token("danger", "#ff7a7a") : root.token("border", "#3a3d45")

        Text {
            anchors.centerIn: parent
            text: control.text
            color: control.accent ? root.token("onComment", "#241a08") : (control.danger ? root.token("danger", "#ff7a7a") : root.token("appFg", "#e8e8e8"))
            font.pixelSize: 11
            font.bold: control.accent
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: control.clicked()
        }
    }

    component CardIconButton: Rectangle {
        id: iconControl
        property string iconName: ""
        property string tooltipText: ""
        property string tooltipCategory: "general"
        property bool danger: false
        signal clicked()
        width: 24
        height: 24
        radius: 6
        color: iconMouse.containsMouse ? root.token("hover", "#33373f") : "transparent"

        readonly property color glyphColor: danger
            ? root.token("danger", "#ff7a7a")
            : (iconMouse.containsMouse ? root.token("appFg", "#e8e8e8") : root.token("mutedFg", "#9aa3af"))

        Image {
            anchors.centerIn: parent
            width: 14
            height: 14
            sourceSize.width: 14
            sourceSize.height: 14
            source: root.iconSource(iconControl.iconName, 14, iconControl.glyphColor)
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        MouseArea {
            id: iconMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: iconControl.clicked()
        }

        Common.ManagedToolTip {
            policyBridge: root.canvasItem && root.canvasItem.canvasStateBridgeRef
                ? root.canvasItem.canvasStateBridgeRef
                : null
            category: iconControl.tooltipCategory
            active: iconMouse.containsMouse && iconControl.tooltipText.length > 0
            text: iconControl.tooltipText
            delay: 280
            screenStablePositioning: true
            anchorScale: Math.max(0.1, root.scale)
            screenGap: 8.0
        }
    }

    component StatusChip: Rectangle {
        id: chipControl
        property string label: ""
        property color fg: root.token("comment", "#F2B84B")
        height: 16
        radius: 8
        width: chipText.implicitWidth + 12
        color: Qt.alpha(fg, 0.14)
        border.width: 1
        border.color: Qt.alpha(fg, 0.45)

        Text {
            id: chipText
            anchors.centerIn: parent
            text: chipControl.label
            color: chipControl.fg
            font.pixelSize: 9
            font.bold: true
        }
    }

    component CommentGlyph: Canvas {
        id: g
        property string name: "bubble"
        property int size: 18
        property color color: "#e8e8e8"

        width: g.size
        height: g.size
        antialiasing: true

        onNameChanged: requestPaint()
        onColorChanged: requestPaint()
        onSizeChanged: requestPaint()
        Component.onCompleted: requestPaint()

        function bubblePath(ctx, s) {
            ctx.beginPath();
            ctx.moveTo(0.25 * s, 0.7917 * s);
            ctx.lineTo(0.125 * s, 0.875 * s);
            ctx.lineTo(0.125 * s, 0.3333 * s);
            ctx.quadraticCurveTo(0.125 * s, 0.1667 * s, 0.2917 * s, 0.1667 * s);
            ctx.lineTo(0.7083 * s, 0.1667 * s);
            ctx.quadraticCurveTo(0.875 * s, 0.1667 * s, 0.875 * s, 0.3333 * s);
            ctx.lineTo(0.875 * s, 0.5833 * s);
            ctx.quadraticCurveTo(0.875 * s, 0.75 * s, 0.7083 * s, 0.75 * s);
            ctx.lineTo(0.375 * s, 0.75 * s);
            ctx.closePath();
        }

        onPaint: {
            var ctx = getContext("2d");
            var s = Math.min(width, height);
            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.translate((width - s) / 2, (height - s) / 2);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.strokeStyle = g.color;
            ctx.fillStyle = g.color;
            var k = s / 36;
            function W(px) { return px * k; }
            function line(x1, y1, x2, y2) {
                ctx.beginPath();
                ctx.moveTo(x1 * s, y1 * s);
                ctx.lineTo(x2 * s, y2 * s);
                ctx.stroke();
            }
            if (g.name === "bubble") {
                ctx.lineWidth = W(2.4);
                bubblePath(ctx, s);
                ctx.stroke();
                ctx.lineWidth = W(1.9);
                line(0.2917, 0.375, 0.7083, 0.375);
                line(0.2917, 0.5417, 0.5417, 0.5417);
            } else if (g.name === "bubbleFilled") {
                bubblePath(ctx, s);
                ctx.fill();
            } else if (g.name === "check") {
                ctx.lineWidth = W(3.0);
                ctx.beginPath();
                ctx.moveTo(0.26 * s, 0.52 * s);
                ctx.lineTo(0.43 * s, 0.70 * s);
                ctx.lineTo(0.76 * s, 0.32 * s);
                ctx.stroke();
            } else if (g.name === "plus") {
                ctx.lineWidth = W(2.6);
                line(0.50, 0.24, 0.50, 0.76);
                line(0.24, 0.50, 0.76, 0.50);
            }
            ctx.restore();
        }
    }
}
