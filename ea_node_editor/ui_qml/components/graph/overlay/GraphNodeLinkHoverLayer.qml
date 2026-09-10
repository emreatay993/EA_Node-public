import QtQuick 2.15
import QtQuick.Effects
import "../../common" as Common
import "../GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics

Item {
    id: root
    objectName: "graphNodeLinkHoverLayer"

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
    property var activeLink: null
    property string activeNodeId: ""
    property string activeLinkId: ""
    property string sourceWorkspaceId: ""
    property real activeAnchorX: 0
    property real activeAnchorY: 0
    property bool cardPointerInside: false
    property bool editorRestoreInProgress: false
    readonly property bool editorOpen: linkEditorForm.editorOpen
    readonly property bool editorSuspended: editorOpen && linkEditorForm.pickModeActive
    readonly property var inspectorBridgeRef: canvasItem ? canvasItem.shellInspectorBridgeRef : null
    readonly property var uiIconsRef: canvasItem && canvasItem.shellContextRef
        ? canvasItem.shellContextRef.uiIcons
        : null
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
    z: 35

    function token(name, fallback) {
        var palette = root.themePalette || {};
        return palette && palette[name] !== undefined ? palette[name] : fallback;
    }

    function iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, String(color));
    }

    function linksForNode(nodeData) {
        var links = nodeData ? nodeData.links : null;
        if (!links)
            return [];
        if (typeof links === "string")
            return [];
        var count = links.length !== undefined
            ? Number(links.length)
            : (links.count !== undefined ? Number(links.count) : 0);
        return isFinite(count) && count > 0 ? links : [];
    }

    function commentBadgeForNode(nodeData) {
        return nodeData && nodeData.comment_badge ? nodeData.comment_badge : ({ count: 0 });
    }

    function commentCountForNode(nodeData) {
        var badge = commentBadgeForNode(nodeData);
        return Math.max(0, Number(badge.count || 0));
    }

    function firstLink(nodeData) {
        var links = linksForNode(nodeData);
        return links.length > 0 ? links[0] : null;
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

    function editorSourceNodeData() {
        var nodeData = root.nodeDataForId(root.activeNodeId);
        if (!nodeData && canvasItem && canvasItem._sceneNodePayload)
            nodeData = canvasItem._sceneNodePayload(root.activeNodeId);
        return nodeData;
    }

    function linkForId(nodeData, linkId) {
        var normalized = String(linkId || "").trim();
        var links = root.linksForNode(nodeData);
        if (!normalized || !links.length)
            return null;
        for (var i = 0; i < links.length; i++) {
            var item = links[i] || {};
            if (String(item.id || item.link_id || "") === normalized)
                return item;
        }
        return null;
    }

    function linkIcon(kind) {
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

    function linkTypeLabel(kind) {
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

    function linkTypeColor(kind) {
        var normalized = String(kind || "url").toLowerCase();
        if (normalized === "file")
            return "#8B7CF6";
        if (normalized === "folder")
            return "#F2B84B";
        if (normalized === "workspace")
            return "#64C88A";
        if (normalized === "node")
            return "#60CDFF";
        return "#3BA9F5";
    }

    function linkGoesToGraphTarget(kind) {
        var normalized = String(kind || "url").toLowerCase();
        return normalized === "node" || normalized === "workspace";
    }

    function linkPrimaryActionLabel(kind) {
        return linkGoesToGraphTarget(kind) ? "Go To" : "Open";
    }

    function linkPrimaryActionIcon(kind) {
        return linkGoesToGraphTarget(kind) ? "navigate" : "external-link";
    }

    function finite(value, fallback) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : Number(fallback || 0);
    }

    function nodeIdForData(nodeData) {
        return String(nodeData ? nodeData.node_id || "" : "").trim();
    }

    function linkIdForData(linkData) {
        return String(linkData ? linkData.id || linkData.link_id || "" : "").trim();
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

    function showCard(nodeData, link, anchorX, anchorY) {
        if (root.editorOpen)
            return;
        root.activeNodeData = nodeData;
        root.activeLink = link;
        root.activeNodeId = root.nodeIdForData(nodeData);
        root.activeLinkId = root.linkIdForData(link);
        root.activeAnchorX = Number(anchorX || 0);
        root.activeAnchorY = Number(anchorY || 0);
        dismissTimer.stop();
    }

    function showNodeLinkCard(nodeId, linkId, anchorX, anchorY) {
        var nodeData = root.nodeDataForId(nodeId);
        var link = root.linkForId(nodeData, linkId);
        if (!nodeData || !link)
            return false;
        root.showCard(nodeData, link, anchorX, anchorY);
        return true;
    }

    function syncActiveCard() {
        if (root.editorSuspended || root.editorRestoreInProgress)
            return;
        if (root.editorOpen) {
            var editorNodeData = root.editorSourceNodeData();
            if (!editorNodeData) {
                root.abortEditor();
                return;
            }
            root.activeNodeData = editorNodeData;
            root.activeLink = null;
            root.activeLinkId = "";
            return;
        }
        if (!root.activeNodeId && !root.activeLinkId)
            return;
        var nodeData = root.nodeDataForId(root.activeNodeId);
        if (!nodeData) {
            root.forceClearCard();
            return;
        }
        var link = root.linkForId(nodeData, root.activeLinkId);
        if (!link) {
            root.forceClearCard();
            return;
        }
        root.activeNodeData = nodeData;
        root.activeLink = link;
    }

    function activeCardAnchorX() {
        if (!root.activeNodeData)
            return root.activeAnchorX;
        return root.nodeX(root.activeNodeData) + root.nodeWidth(root.activeNodeData) * 0.5;
    }

    function activeCardAnchorY() {
        if (!root.activeNodeData)
            return root.activeAnchorY;
        return root.nodeY(root.activeNodeData) + root.nodeHeight(root.activeNodeData) + 17;
    }

    function scheduleDismiss() {
        if (root.editorOpen)
            return;
        dismissTimer.restart();
    }

    function clearCard() {
        if (root.cardPointerInside || root.editorOpen)
            return;
        root.resetCardState();
    }

    function resetCardState() {
        root.editorRestoreInProgress = false;
        root.activeNodeData = null;
        root.activeLink = null;
        root.activeNodeId = "";
        root.activeLinkId = "";
        root.sourceWorkspaceId = "";
        root.activeAnchorX = 0;
        root.activeAnchorY = 0;
    }

    function forceClearCard() {
        dismissTimer.stop();
        root.cardPointerInside = false;
        if (root.editorOpen) {
            linkEditorForm.cancelEdit();
            return;
        }
        root.resetCardState();
    }

    function commandBridge() {
        if (!canvasItem)
            return null;
        return canvasItem.canvasCommandBridgeRef
            || canvasItem.canvasCommandBridge
            || canvasItem.sceneCommandBridge
            || null;
    }

    function sceneCommandBridge() {
        return canvasItem ? canvasItem.sceneCommandBridge : null;
    }

    function openActiveLink() {
        var bridge = commandBridge();
        if (!bridge || !bridge.open_node_link || !root.activeNodeData || !root.activeLink)
            return false;
        return Boolean(bridge.open_node_link(
            String(root.activeNodeData.node_id || ""),
            String(root.activeLink.id || root.activeLink.link_id || "")
        ));
    }

    function deleteActiveLink() {
        var bridge = commandBridge();
        if (!bridge || !bridge.remove_node_link || !root.activeNodeData || !root.activeLink)
            return false;
        var removed = Boolean(bridge.remove_node_link(
            String(root.activeNodeData.node_id || ""),
            String(root.activeLink.id || root.activeLink.link_id || "")
        ));
        if (removed)
            forceClearCard();
        return removed;
    }

    function requestAddLink() {
        if (!root.activeNodeData || !canvasItem || !canvasItem.requestAddNodeLinkForNode)
            return false;
        return Boolean(canvasItem.requestAddNodeLinkForNode(String(root.activeNodeData.node_id || "")));
    }

    function openEditor(nodeData, workspaceId) {
        var nodeId = root.nodeIdForData(nodeData);
        var normalizedWorkspaceId = String(workspaceId || "").trim();
        if (!nodeId.length || !normalizedWorkspaceId.length)
            return false;
        dismissTimer.stop();
        root.activeNodeData = nodeData;
        root.activeNodeId = nodeId;
        root.activeLink = null;
        root.activeLinkId = "";
        root.sourceWorkspaceId = normalizedWorkspaceId;
        root.activeAnchorX = root.nodeX(nodeData) + root.nodeWidth(nodeData) * 0.5;
        root.activeAnchorY = root.nodeY(nodeData) + root.nodeHeight(nodeData) + 17;
        linkEditorForm.beginAdd();
        return true;
    }

    function applyPickedTarget(kind, workspaceId, nodeId, label, subtitle) {
        if (!root.editorOpen)
            return false;
        var sourceNodeData = root.editorSourceNodeData();
        if (!sourceNodeData) {
            root.abortEditor();
            return false;
        }
        root.activeNodeData = sourceNodeData;
        root.editorRestoreInProgress = true;
        var applied = linkEditorForm.applyPickedTarget(kind, workspaceId, nodeId, label, subtitle);
        Qt.callLater(function() { root.editorRestoreInProgress = false; });
        return applied;
    }

    function resumeAfterPickCancel() {
        if (!root.editorOpen)
            return false;
        var sourceNodeData = root.editorSourceNodeData();
        if (!sourceNodeData) {
            root.abortEditor();
            return false;
        }
        root.activeNodeData = sourceNodeData;
        root.editorRestoreInProgress = true;
        var resumed = linkEditorForm.resumeAfterPickCancel();
        Qt.callLater(function() { root.editorRestoreInProgress = false; });
        return resumed;
    }

    function abortEditor() {
        if (!root.editorOpen)
            return false;
        linkEditorForm.cancelEdit();
        return true;
    }

    function saveEditorDraft(draft) {
        var bridge = root.commandBridge();
        if (!bridge || !bridge.upsert_node_link || !root.activeNodeId.length)
            return false;
        var storedId = bridge.upsert_node_link(
            root.activeNodeId,
            "",
            String(draft.kind || "url"),
            String(draft.title || ""),
            String(draft.target || ""),
            String(draft.subtitle || ""),
            String(draft.target_workspace_id || ""),
            String(draft.target_node_id || "")
        );
        return linkEditorForm.completeSave(storedId);
    }

    function requestEditorTargetPick(kind) {
        if (!canvasItem || !canvasItem.requestNodeLinkTargetPick)
            return false;
        var requested = Boolean(canvasItem.requestNodeLinkTargetPick(
            kind,
            root.sourceWorkspaceId,
            root.activeNodeId
        ));
        if (!requested)
            linkEditorForm.resumeAfterPickCancel();
        return requested;
    }

    function preserveEditorForWorkspaceChange(workspaceId) {
        if (root.editorSuspended || root.editorRestoreInProgress)
            return true;
        if (!root.editorOpen || !root.sourceWorkspaceId.length)
            return false;
        var currentWorkspaceId = canvasItem && canvasItem.shellWorkspaceBridgeRef
            ? String(canvasItem.shellWorkspaceBridgeRef.active_workspace_id || "").trim()
            : "";
        if (currentWorkspaceId === root.sourceWorkspaceId)
            return true;
        var normalizedWorkspaceId = String(workspaceId || "").trim();
        return normalizedWorkspaceId === root.sourceWorkspaceId;
    }

    Timer {
        id: dismissTimer
        interval: 200
        repeat: false
        onTriggered: root.clearCard()
    }

    onSceneModelChanged: root.syncActiveCard()

    Connections {
        target: root.sceneStateBridge
        ignoreUnknownSignals: true

        function onNodes_changed() {
            root.syncActiveCard();
        }

        function onScene_nodes_changed() {
            root.syncActiveCard();
        }

        function onScope_changed() {
            if (!root.editorSuspended && !root.editorRestoreInProgress)
                root.forceClearCard();
        }

        function onScene_scope_changed() {
            if (!root.editorSuspended && !root.editorRestoreInProgress)
                root.forceClearCard();
        }

        function onWorkspace_changed(workspaceId) {
            if (!root.preserveEditorForWorkspaceChange(workspaceId))
                root.forceClearCard();
        }

        function onScene_workspace_changed(workspaceId) {
            if (!root.preserveEditorForWorkspaceChange(workspaceId))
                root.forceClearCard();
        }
    }

    Repeater {
        model: root.badgeModel

        delegate: Item {
            id: badgeHost
            objectName: "graphNodeLinkBadgeHost"
            readonly property var links: root.linksForNode(modelData)
            readonly property bool hasLinks: links.length > 0
            readonly property int commentCount: root.commentCountForNode(modelData)
            readonly property bool hasCommentBadge: commentCount > 0
            readonly property real commentCountBadgeWidth: 11 + 4 + commentCountProbe.implicitWidth + 16
            readonly property real commentBadgeWidth: commentCountBadgeWidth
            readonly property real groupWidth: hasCommentBadge ? badge.width + root.badgeGap + commentBadgeWidth : badge.width
            readonly property real badgeHorizontalShift: GraphNodeSurfaceMetrics.nodeHasBottomNeutralFlowHandle(modelData)
                ? groupWidth * 0.5 + root.bottomNeutralPortClearance : 0
            readonly property real badgeX: root.nodeX(modelData) + (root.nodeWidth(modelData) - groupWidth) / 2 + badgeHorizontalShift
            readonly property real badgeY: root.nodeY(modelData) + root.nodeHeight(modelData) - badge.height / 2

            visible: hasLinks
            x: badgeX
            y: badgeY
            width: badge.width
            height: badge.height
            z: 40

            Text {
                id: commentCountProbe
                visible: false
                text: badgeHost.commentCount
                font.pixelSize: 10
                font.bold: true
            }

            Rectangle {
                id: badge
                width: badgeRow.implicitWidth + 16
                height: 18
                radius: 9
                color: badgeMouse.containsMouse ? root.token("accent", "#60CDFF") : Qt.alpha(root.token("accent", "#60CDFF"), 0.9)
                border.width: 1
                border.color: Qt.alpha(root.token("app_fg", "#ffffff"), 0.18)

                Row {
                    id: badgeRow
                    anchors.centerIn: parent
                    spacing: 4

                    Image {
                        width: 11
                        height: 11
                        source: root.iconSource("link", 11, root.token("on_accent", "#0c2230"))
                        fillMode: Image.PreserveAspectFit
                        sourceSize.width: 11
                        sourceSize.height: 11
                    }

                    Text {
                        text: badgeHost.links.length
                        color: root.token("on_accent", "#0c2230")
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                MouseArea {
                    id: badgeMouse
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: root.showCard(modelData, badgeHost.links[0], badgeHost.x + badge.width * 0.5, badgeHost.y + badge.height + 8)
                    onExited: root.scheduleDismiss()
                    onClicked: root.showCard(modelData, badgeHost.links[0], badgeHost.x + badge.width * 0.5, badgeHost.y + badge.height + 8)
                }
            }
        }
    }

    Rectangle {
        id: linkCard
        objectName: "graphNodeLinkHoverCard"
        readonly property bool active: !!root.activeNodeData
            && (!!root.activeLink || root.editorOpen)
            && !root.editorSuspended
        readonly property var viewport: root.visibleSceneRectPayload || ({})
        readonly property real viewportX: Number(viewport.x || 0) + Number(root.canvasItem ? root.canvasItem.worldOffset : 0)
        readonly property real viewportY: Number(viewport.y || 0) + Number(root.canvasItem ? root.canvasItem.worldOffset : 0)
        readonly property real viewportW: Math.max(width + 20, Number(viewport.width || root.width))
        readonly property real cardPadding: 14
        width: root.editorOpen ? 320 : Math.max(300, cardActionsRow.implicitWidth + cardPadding * 2)
        height: cardColumn.implicitHeight + 28
        radius: 12
        visible: opacity > 0.01
        opacity: active ? 1.0 : 0.0
        x: Math.max(viewportX + 10, Math.min(root.activeCardAnchorX() - width * 0.5, viewportX + viewportW - width - 10))
        y: root.activeCardAnchorY()
        z: 90
        color: root.token("panel_alt_bg", root.token("panel_bg", "#24262c"))
        border.width: 1
        border.color: root.token("border", "#3a3d45")

        RectangularShadow {
            anchors.fill: parent
            z: -1
            offset.x: 0
            offset.y: 4
            blur: 20
            spread: 0
            radius: linkCard.radius
            color: Qt.rgba(0, 0, 0, 0.45)
            cached: true
        }

        Behavior on opacity {
            NumberAnimation { duration: 130; easing.type: Easing.InOutCubic }
        }

        transform: Translate {
            y: linkCard.active ? 0 : 8
            Behavior on y {
                NumberAnimation { duration: 130; easing.type: Easing.OutCubic }
            }
        }

        Column {
            id: cardColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: linkCard.cardPadding
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
                    readonly property color typeColor: root.linkTypeColor(
                        root.editorOpen ? linkEditorForm.editingKind : (root.activeLink ? root.activeLink.kind : "url")
                    )
                    color: Qt.alpha(typeColor, 0.18)

                    Image {
                        anchors.centerIn: parent
                        width: 17
                        height: 17
                        source: root.iconSource(
                            root.linkIcon(root.editorOpen ? linkEditorForm.editingKind : (root.activeLink ? root.activeLink.kind : "url")),
                            17,
                            parent.typeColor
                        )
                        fillMode: Image.PreserveAspectFit
                        sourceSize.width: 17
                        sourceSize.height: 17
                    }
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
                        text: root.editorOpen
                            ? "Add link"
                            : (root.activeLink ? String(root.activeLink.title || root.activeLink.target || "") : "")
                        color: root.token("panel_title_fg", "#f0f4fb")
                        font.pixelSize: 13
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: root.editorOpen
                            ? (root.activeNodeData ? "on " + String(root.activeNodeData.title || "") : "")
                            : (root.activeLink
                                ? root.linkTypeLabel(root.activeLink.kind) + (String(root.activeLink.subtitle || root.activeLink.target || "").length > 0 ? " - " + String(root.activeLink.subtitle || root.activeLink.target || "") : "")
                                : "")
                        color: root.token("muted_fg", "#9aa3af")
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }

                CardIconButton {
                    id: headerCloseButton
                    objectName: "graphNodeLinkPopoverCloseButton"
                    anchors.right: parent.right
                    anchors.top: parent.top
                    iconName: "x"
                    tooltipText: "Close"
                    onClicked: root.forceClearCard()
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.token("border", "#3a3d45")
                opacity: 0.7
            }

            Common.NodeLinkEditorForm {
                id: linkEditorForm
                width: parent.width
                objectNamePrefix: "graphNodeLinkPopover"
                hideWhilePicking: true
                themePalette: root.themePalette
                selectedSurfaceColor: root.token("accent", "#60CDFF")
                cardBackgroundColor: root.token("panel_alt_bg", "#24262c")
                uiIconsRef: root.uiIconsRef
                nodeOptions: root.inspectorBridgeRef
                    ? (root.inspectorBridgeRef.selected_node_link_node_options || [])
                    : []
                workspaceOptions: root.inspectorBridgeRef
                    ? (root.inspectorBridgeRef.selected_node_link_workspace_options || [])
                    : []
                onSaveRequested: function(draft) { root.saveEditorDraft(draft); }
                onPickTargetRequested: function(kind) { root.requestEditorTargetPick(kind); }
                onEditorClosed: function(_saved) { root.resetCardState(); }
            }

            Row {
                id: cardActionsRow
                objectName: "graphNodeLinkHoverCardActions"
                width: parent.width
                spacing: 6
                visible: !root.editorOpen

                CardButton {
                    width: 78
                    text: root.linkPrimaryActionLabel(root.activeLink ? root.activeLink.kind : "url")
                    iconName: root.linkPrimaryActionIcon(root.activeLink ? root.activeLink.kind : "url")
                    accent: true
                    onClicked: root.openActiveLink()
                }

                CardButton {
                    width: 86
                    text: "Add link"
                    iconName: "plus"
                    onClicked: root.requestAddLink()
                }

                CardButton {
                    width: 86
                    text: "Delete"
                    iconName: "x"
                    danger: true
                    onClicked: root.deleteActiveLink()
                }
            }
        }

        HoverHandler {
            id: cardHoverHandler
            objectName: "graphNodeLinkHoverCardHoverHandler"
            onHoveredChanged: {
                if (!hovered) {
                    root.cardPointerInside = false;
                    root.scheduleDismiss();
                    return;
                }
                root.cardPointerInside = true;
                dismissTimer.stop();
            }
        }
    }

    component CardButton: Rectangle {
        id: control
        property string text: ""
        property string iconName: ""
        property bool accent: false
        property bool danger: false
        signal clicked()
        height: 28
        radius: 7
        color: accent
            ? root.token("accent", "#60CDFF")
            : (mouse.containsMouse
                ? (danger ? Qt.rgba(1.0, 0.23, 0.23, 0.14) : root.token("hover", "#33373f"))
                : "transparent")
        border.width: accent ? 0 : 1
        border.color: danger ? Qt.rgba(1.0, 0.23, 0.23, 0.32) : root.token("border", "#3a3d45")

        Row {
            anchors.centerIn: parent
            spacing: 5

            Image {
                width: 14
                height: 14
                source: root.iconSource(
                    control.iconName,
                    14,
                    control.accent
                        ? root.token("on_accent", "#0c2230")
                        : (control.danger && mouse.containsMouse ? "#ff7a7a" : root.token("muted_fg", "#9aa3af"))
                )
                fillMode: Image.PreserveAspectFit
                sourceSize.width: 14
                sourceSize.height: 14
            }

            Text {
                text: control.text
                color: control.accent
                    ? root.token("on_accent", "#0c2230")
                    : (control.danger && mouse.containsMouse ? "#ff7a7a" : root.token("panel_title_fg", "#f0f4fb"))
                font.pixelSize: 11
                font.bold: control.accent
            }
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
        signal clicked()
        width: 24
        height: 24
        radius: 6
        color: iconMouse.containsMouse ? root.token("hover", "#33373f") : "transparent"

        Image {
            anchors.centerIn: parent
            width: 14
            height: 14
            sourceSize.width: 14
            sourceSize.height: 14
            source: root.iconSource(iconControl.iconName, 14, root.token("muted_fg", "#9aa3af"))
            fillMode: Image.PreserveAspectFit
        }

        MouseArea {
            id: iconMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: iconControl.clicked()
        }

        Common.ManagedToolTip {
            policyBridge: root.canvasItem ? root.canvasItem.canvasStateBridgeRef : null
            category: "nodes.links.close"
            active: iconMouse.containsMouse && iconControl.tooltipText.length > 0
            text: iconControl.tooltipText
            delay: 280
            screenStablePositioning: true
            anchorScale: Math.max(0.1, root.scale)
            screenGap: 8.0
        }
    }
}
