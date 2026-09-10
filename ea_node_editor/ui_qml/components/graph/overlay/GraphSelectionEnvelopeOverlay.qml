import QtQuick 2.15
import "../surface_controls" as GraphSurfaceControls
import "../../common/TooltipCopy.js" as TooltipCopy

Item {
    id: root
    objectName: "graphSelectionEnvelopeOverlay"

    property var canvasItem: null
    property var viewBridge: null
    property var sceneStateBridge: null
    property var canvasActionRouter: null
    property var visibleSceneRectPayload: ({})
    property var hostResolver: null
    property var themePalette: ({})

    readonly property var selectedNodeLookup: root.sceneStateBridge
        && root.sceneStateBridge.selected_node_lookup !== undefined
        ? root.sceneStateBridge.selected_node_lookup
        : null
    readonly property bool selectedNodeLookupAuthoritative: root.sceneStateBridge
        && root.sceneStateBridge.selected_node_lookup_authoritative !== undefined
        ? Boolean(root.sceneStateBridge.selected_node_lookup_authoritative)
        : false
    readonly property var selectedNodeIds: root._selectedNodeIds()
    readonly property int selectedNodeCount: root.selectedNodeIds.length
    readonly property var selectionBounds: root._selectionBounds()
    readonly property bool hasSelectionBounds: root.selectedNodeCount >= 2
        && root._rectValid(root.selectionBounds)
    readonly property string selectionToolbarMode: root._selectionToolbarMode()
    readonly property string minimalMenuTrigger: root._minimalMenuTrigger()
    readonly property bool canAlignSelection: root.selectedNodeCount >= 2
    readonly property bool canDistributeSelection: root.selectedNodeCount >= 3
    readonly property bool canWrapSelection: root.selectedNodeCount >= 2
    readonly property bool canStraightenConnections: root._hasInternalConnection()
    readonly property real envelopePadding: 10.0
    readonly property color accentColor: root._paletteColor("accent", "#1D8CE0")
    readonly property color panelColor: root._paletteColor("panel_bg", "#20242d")
    readonly property color foregroundColor: root._paletteColor("panel_title_fg", "#f1f4fb")
    readonly property color borderColor: root._paletteColor("border", "#4b5568")

    width: root.canvasItem ? root.canvasItem.worldSize : 0
    height: root.canvasItem ? root.canvasItem.worldSize : 0
    transformOrigin: Item.TopLeft
    scale: root.viewBridge ? root.viewBridge.zoom_value : 1.0
    x: root.canvasItem
        ? root.canvasItem.width * 0.5 - ((root.viewBridge ? root.viewBridge.center_x : 0) + root.canvasItem.worldOffset) * scale
        : 0.0
    y: root.canvasItem
        ? root.canvasItem.height * 0.5 - ((root.viewBridge ? root.viewBridge.center_y : 0) + root.canvasItem.worldOffset) * scale
        : 0.0
    z: 32
    visible: root.hasSelectionBounds

    function _paletteColor(key, fallback) {
        var palette = root.themePalette || {};
        var value = palette[key];
        return value !== undefined && String(value || "").length > 0 ? value : fallback;
    }

    function _finite(value, fallback) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : Number(fallback || 0);
    }

    function _canvasStateBridge() {
        if (root.canvasItem && root.canvasItem.canvasStateBridgeRef)
            return root.canvasItem.canvasStateBridgeRef;
        return null;
    }

    function _selectionToolbarMode() {
        var bridge = root._canvasStateBridge();
        if (bridge && bridge.graphics_selection_toolbar_mode !== undefined) {
            var value = String(bridge.graphics_selection_toolbar_mode || "").toLowerCase();
            if (value === "minimal_ghost_menu" || value === "side_rail")
                return value;
        }
        return "minimal_ghost_menu";
    }

    function _minimalMenuTrigger() {
        var bridge = root._canvasStateBridge();
        if (bridge && bridge.graphics_selection_toolbar_minimal_menu_trigger !== undefined) {
            var value = String(bridge.graphics_selection_toolbar_minimal_menu_trigger || "").toLowerCase();
            if (value === "click_affordance" || value === "right_click")
                return value;
        }
        return "click_affordance";
    }

    function _selectedNodeIds() {
        var selected = [];
        var lookup = root.selectedNodeLookup;
        if (lookup && root.selectedNodeLookupAuthoritative) {
            for (var selectedId in lookup) {
                if (!Object.prototype.hasOwnProperty.call(lookup, selectedId) || !Boolean(lookup[selectedId]))
                    continue;
                var normalizedSelectedId = String(selectedId || "").trim();
                if (normalizedSelectedId.length)
                    selected.push(normalizedSelectedId);
            }
            return selected;
        }
        if (!root.canvasItem || !root.canvasItem.selectedNodeIds)
            return selected;
        var source = root.canvasItem.selectedNodeIds() || [];
        for (var i = 0; i < source.length; ++i) {
            var nodeId = String(source[i] || "").trim();
            if (nodeId.length)
                selected.push(nodeId);
        }
        return selected;
    }

    function _hostForNodeId(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized)
            return null;
        if (typeof root.hostResolver === "function")
            return root.hostResolver(normalized);
        return null;
    }

    function _fallbackNodeRect(nodeId) {
        if (!root.canvasItem || !root.canvasItem._sceneNodePayload)
            return null;
        var normalized = String(nodeId || "").trim();
        var payload = root.canvasItem._sceneNodePayload(normalized);
        if (!payload)
            return null;
        var live = root.canvasItem.liveNodeGeometry
            ? root.canvasItem.liveNodeGeometry[normalized]
            : null;
        var dragged = root.canvasItem.liveDragNodeLookup
            ? Boolean(root.canvasItem.liveDragNodeLookup[normalized])
            : false;
        var dragDx = dragged ? root._finite(root.canvasItem.liveDragDx, 0) : 0;
        var dragDy = dragged ? root._finite(root.canvasItem.liveDragDy, 0) : 0;
        var offset = root._finite(root.canvasItem.worldOffset, 0);
        return {
            "x": root._finite(live ? live.x : payload.x, 0) + offset + dragDx,
            "y": root._finite(live ? live.y : payload.y, 0) + offset + dragDy,
            "width": Math.max(1, root._finite(live ? live.width : payload.width, 1)),
            "height": Math.max(1, root._finite(live ? live.height : payload.height, 1))
        };
    }

    function _nodeRect(nodeId) {
        var host = root._hostForNodeId(nodeId);
        if (host) {
            var dragDx = host.dragTranslateX !== undefined
                ? root._finite(host.dragTranslateX, 0)
                : 0;
            var dragDy = host.dragTranslateY !== undefined
                ? root._finite(host.dragTranslateY, 0)
                : 0;
            return {
                "x": root._finite(host.x, 0) + dragDx,
                "y": root._finite(host.y, 0) + dragDy,
                "width": Math.max(1, root._finite(host.width, 1)),
                "height": Math.max(1, root._finite(host.height, 1))
            };
        }
        return root._fallbackNodeRect(nodeId);
    }

    function _selectionBounds() {
        var selected = root.selectedNodeIds || [];
        if (selected.length < 2)
            return ({ "x": 0, "y": 0, "width": 0, "height": 0 });
        var minX = Infinity;
        var minY = Infinity;
        var maxX = -Infinity;
        var maxY = -Infinity;
        var rectCount = 0;
        for (var i = 0; i < selected.length; ++i) {
            var rect = root._nodeRect(selected[i]);
            if (!root._rectValid(rect))
                continue;
            minX = Math.min(minX, rect.x);
            minY = Math.min(minY, rect.y);
            maxX = Math.max(maxX, rect.x + rect.width);
            maxY = Math.max(maxY, rect.y + rect.height);
            rectCount += 1;
        }
        if (rectCount < 2)
            return ({ "x": 0, "y": 0, "width": 0, "height": 0 });
        return {
            "x": minX,
            "y": minY,
            "width": Math.max(1, maxX - minX),
            "height": Math.max(1, maxY - minY)
        };
    }

    function _rectValid(rect) {
        return !!rect
            && isFinite(Number(rect.x))
            && isFinite(Number(rect.y))
            && isFinite(Number(rect.width))
            && isFinite(Number(rect.height))
            && Number(rect.width) > 0
            && Number(rect.height) > 0;
    }

    function _viewportLocalRect() {
        var payload = root.visibleSceneRectPayload || {};
        var offset = root.canvasItem ? root._finite(root.canvasItem.worldOffset, 0) : 0;
        return {
            "x": root._finite(payload.x, 0) + offset,
            "y": root._finite(payload.y, 0) + offset,
            "width": Math.max(1, root._finite(payload.width, root.canvasItem ? root.canvasItem.width : 1)),
            "height": Math.max(1, root._finite(payload.height, root.canvasItem ? root.canvasItem.height : 1))
        };
    }

    function _selectedNodeLookup() {
        var lookup = {};
        var selected = root.selectedNodeIds || [];
        for (var i = 0; i < selected.length; ++i) {
            var nodeId = String(selected[i] || "").trim();
            if (nodeId.length)
                lookup[nodeId] = true;
        }
        return lookup;
    }

    function _edgePayload(edgeId) {
        if (!root.canvasItem || !root.canvasItem._sceneEdgePayload)
            return null;
        return root.canvasItem._sceneEdgePayload(String(edgeId || "").trim());
    }

    function _edgeConnectsSelectedNodes(edge, selectedLookup) {
        if (!edge)
            return false;
        var sourceNodeId = String(edge.source_node_id || "").trim();
        var targetNodeId = String(edge.target_node_id || "").trim();
        return sourceNodeId.length > 0
            && targetNodeId.length > 0
            && Boolean(selectedLookup[sourceNodeId])
            && Boolean(selectedLookup[targetNodeId]);
    }

    function _hasInternalConnection() {
        if (root.selectedNodeCount < 2 || !root.canvasItem)
            return false;
        var selectedLookup = root._selectedNodeLookup();
        var selectedEdges = root.canvasItem.selectedEdgeIds || [];
        for (var selectedIndex = 0; selectedIndex < selectedEdges.length; ++selectedIndex) {
            if (root._edgeConnectsSelectedNodes(root._edgePayload(selectedEdges[selectedIndex]), selectedLookup))
                return true;
        }
        var edges = root.canvasItem.edgePayload || [];
        for (var edgeIndex = 0; edgeIndex < edges.length; ++edgeIndex) {
            if (root._edgeConnectsSelectedNodes(edges[edgeIndex], selectedLookup))
                return true;
        }
        return false;
    }

    function _actionRouter() {
        return root.canvasActionRouter
            || (root.canvasItem && root.canvasItem.canvasActionRouter ? root.canvasItem.canvasActionRouter : null);
    }

    function triggerSelectionAction(actionId, enabled) {
        if (!enabled)
            return false;
        var router = root._actionRouter();
        if (!router || !router.handleSelectionContextAction)
            return false;
        return Boolean(router.handleSelectionContextAction(String(actionId || "")));
    }

    function openSelectionMenuAt(canvasX, canvasY) {
        if (!root.canvasItem || !root.canvasItem._openSelectionContext)
            return false;
        root.canvasItem._openSelectionContext(Number(canvasX || 0), Number(canvasY || 0));
        return true;
    }

    function openSelectionMenuAtScene(sceneX, sceneY) {
        if (!root.canvasItem || !root.canvasItem._openSelectionContextAtScene || root.selectedNodeCount < 2)
            return false;
        var worldOffset = root._finite(root.canvasItem.worldOffset, 0);
        root.canvasItem._openSelectionContextAtScene(
            root._finite(sceneX, 0) - worldOffset,
            root._finite(sceneY, 0) - worldOffset
        );
        return true;
    }

    function openSelectionMenu(anchorItem) {
        if (!anchorItem || !anchorItem.mapToItem)
            return false;
        var point = anchorItem.mapToItem(
            root,
            Number(anchorItem.width || 0) + 8,
            Number(anchorItem.height || 0) * 0.5
        );
        return root.openSelectionMenuAtScene(point.x, point.y);
    }

    function _clampedAffordanceX() {
        var viewport = root._viewportLocalRect();
        var candidate = envelopeFrame.x + envelopeFrame.width - minimalAffordance.width * 0.5;
        var minX = viewport.x + 8;
        var maxX = viewport.x + viewport.width - minimalAffordance.width - 8;
        return maxX >= minX ? Math.max(minX, Math.min(maxX, candidate)) : candidate;
    }

    function _clampedAffordanceY() {
        var viewport = root._viewportLocalRect();
        var preferredInset = 8;
        var faceMinY = envelopeFrame.y + preferredInset;
        var faceMaxY = envelopeFrame.y + envelopeFrame.height - minimalAffordance.height - preferredInset;
        var candidate = faceMaxY >= faceMinY
            ? faceMinY
            : envelopeFrame.y + envelopeFrame.height * 0.5 - minimalAffordance.height * 0.5;
        var minY = viewport.y + 8;
        var maxY = viewport.y + viewport.height - minimalAffordance.height - 8;
        return maxY >= minY ? Math.max(minY, Math.min(maxY, candidate)) : candidate;
    }

    function _clampedRailX() {
        var viewport = root._viewportLocalRect();
        var candidate = envelopeFrame.x + envelopeFrame.width + 8;
        var minX = viewport.x + 8;
        var maxX = viewport.x + viewport.width - sideRailChrome.width - 8;
        return maxX >= minX ? Math.max(minX, Math.min(maxX, candidate)) : candidate;
    }

    function _clampedRailY() {
        var viewport = root._viewportLocalRect();
        var candidate = envelopeFrame.y;
        var minY = viewport.y + 8;
        var maxY = viewport.y + viewport.height - sideRailChrome.height - 8;
        return maxY >= minY ? Math.max(minY, Math.min(maxY, candidate)) : candidate;
    }

    readonly property var _sideRailActions: [
        { "id": "run_selected", "label": "Run Selected", "icon": "node-run", "glyph": "", "enabled": root.selectedNodeCount > 0 },
        { "id": "align_selection_left", "label": "Align Left", "glyph": "L", "enabled": root.canAlignSelection },
        { "id": "align_selection_right", "label": "Align Right", "glyph": "R", "enabled": root.canAlignSelection },
        { "id": "align_selection_top", "label": "Align Top", "glyph": "T", "enabled": root.canAlignSelection },
        { "id": "align_selection_bottom", "label": "Align Bottom", "glyph": "B", "enabled": root.canAlignSelection },
        { "id": "distribute_selection_horizontally", "label": "Distribute Horizontally", "glyph": "H", "enabled": root.canDistributeSelection },
        { "id": "distribute_selection_vertically", "label": "Distribute Vertically", "glyph": "V", "enabled": root.canDistributeSelection },
        { "id": "straighten_selection_connections", "label": "Straighten Connections", "glyph": "S", "enabled": root.canStraightenConnections },
        { "id": "wrap_selection_in_group_backdrop", "label": "Wrap Selection in Group", "icon": "comment", "glyph": "C", "enabled": root.canWrapSelection }
    ]

    Rectangle {
        id: envelopeFrame
        objectName: "graphSelectionEnvelopeFrame"
        visible: root.hasSelectionBounds
        x: root.selectionBounds.x - root.envelopePadding
        y: root.selectionBounds.y - root.envelopePadding
        width: root.selectionBounds.width + root.envelopePadding * 2
        height: root.selectionBounds.height + root.envelopePadding * 2
        radius: 7
        color: root.selectionToolbarMode === "side_rail"
            ? Qt.alpha(root.accentColor, 0.045)
            : Qt.alpha(root.accentColor, 0.025)
        border.width: root.selectionToolbarMode === "side_rail" ? 1.35 : 1
        border.color: Qt.alpha(root.accentColor, root.selectionToolbarMode === "side_rail" ? 0.72 : 0.38)

        MouseArea {
            id: envelopeContextMouseArea
            anchors.fill: parent
            acceptedButtons: Qt.RightButton
            hoverEnabled: false
            preventStealing: true

            function openAt(localX, localY) {
                var point = envelopeFrame.mapToItem(root, localX, localY);
                root.openSelectionMenuAtScene(point.x, point.y);
            }

            onPressed: function(mouse) {
                if (mouse.button !== Qt.RightButton) {
                    mouse.accepted = false;
                    return;
                }
                mouse.accepted = true;
            }

            onReleased: function(mouse) {
                if (mouse.button !== Qt.RightButton) {
                    mouse.accepted = false;
                    return;
                }
                envelopeContextMouseArea.openAt(mouse.x, mouse.y);
                mouse.accepted = true;
            }
        }
    }

    GraphSurfaceControls.GraphSurfaceButton {
        id: minimalAffordance
        objectName: "graphSelectionEnvelopeMinimalAffordance"
        visible: root.hasSelectionBounds
            && root.selectionToolbarMode === "minimal_ghost_menu"
            && root.minimalMenuTrigger === "click_affordance"
        x: root._clampedAffordanceX()
        y: root._clampedAffordanceY()
        width: 26
        height: 26
        iconName: "more"
        iconOnly: true
        iconSize: 14
        tooltipText: TooltipCopy.text(tooltipCopyBridge, "graph.selection.actions")
        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "graph.selection.actions")
        tooltipAnchorScale: root.scale
        tooltipScreenStablePlacement: "below"
        accentColor: root.accentColor
        foregroundColor: root.foregroundColor
        baseFillColor: Qt.alpha(root.panelColor, 0.72)
        baseBorderColor: Qt.alpha(root.borderColor, 0.68)
        hoverFillColor: Qt.alpha(root.accentColor, 0.18)
        pressedFillColor: Qt.alpha(root.accentColor, 0.28)
        chromeRadius: 8
        iconSourceResolver: function(name, size, color) {
            if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
                return "";
            return uiIcons.sourceSized(name, size, color);
        }
        onClicked: root.openSelectionMenu(minimalAffordance)
    }

    Rectangle {
        id: sideRailChrome
        objectName: "graphSelectionEnvelopeSideRail"
        visible: root.hasSelectionBounds && root.selectionToolbarMode === "side_rail"
        x: root._clampedRailX()
        y: root._clampedRailY()
        width: 34
        height: sideRailColumn.implicitHeight + 10
        radius: 8
        color: Qt.alpha(root.panelColor, 0.90)
        border.width: 1
        border.color: Qt.alpha(root.borderColor, 0.74)

        Column {
            id: sideRailColumn
            anchors.centerIn: parent
            spacing: 4

            Repeater {
                model: root._sideRailActions

                delegate: GraphSurfaceControls.GraphSurfaceButton {
                    readonly property bool actionEnabled: Boolean(modelData.enabled)
                    objectName: "graphSelectionEnvelopeAction_" + String(modelData.id || "")
                    width: 24
                    height: 24
                    text: String(modelData.icon || "").length > 0 ? "" : String(modelData.glyph || "")
                    iconName: String(modelData.icon || "")
                    iconOnly: String(modelData.icon || "").length > 0
                    iconSize: 14
                    enabled: actionEnabled
                    opacity: actionEnabled ? 1.0 : 0.46
                    tooltipText: String(modelData.label || "")
                    tooltipAnchorScale: root.scale
                    tooltipScreenStablePlacement: "left"
                    accentColor: root.accentColor
                    foregroundColor: root.foregroundColor
                    baseFillColor: "transparent"
                    baseBorderColor: "transparent"
                    hoverFillColor: Qt.alpha(root.accentColor, 0.18)
                    pressedFillColor: Qt.alpha(root.accentColor, 0.28)
                    disabledForegroundColor: Qt.alpha(root.foregroundColor, 0.48)
                    idleBorderWidth: 0
                    hoverBorderWidth: 1
                    chromeRadius: 6
                    iconSourceResolver: function(name, size, color) {
                        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
                            return "";
                        return uiIcons.sourceSized(name, size, color);
                    }
                    onClicked: root.triggerSelectionAction(modelData.id, actionEnabled)
                }
            }
        }
    }
}
