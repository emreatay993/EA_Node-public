import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common
import "GraphCanvasLogic.js" as GraphCanvasLogic
import "../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: root
    objectName: "graphCanvasMinimapOverlayRoot"
    property Item canvasItem: null
    property var sceneStateBridge: null
    property var viewStateBridge: null
    property var viewCommandBridge: null
    readonly property var themePalette: themeBridge.palette
    property int tooltipTextFormat: Text.PlainText
    property string tooltipCategory: TooltipCopy.category(tooltipCopyBridge, root.toggleTooltipKey)
    readonly property string toggleTooltipKey: root.isExpanded ? "graph.minimap.collapse" : "graph.minimap.expand"
    readonly property var tooltipPolicyBridge: root.sceneStateBridge
        ? root.sceneStateBridge
        : (root.canvasItem && root.canvasItem.canvasStateBridgeRef
            ? root.canvasItem.canvasStateBridgeRef
            : null)
    readonly property bool isExpanded: root.canvasItem ? root.canvasItem.minimapExpanded : false
    readonly property bool minimapContentVisible: root.isExpanded
    readonly property color chromeColor: Qt.alpha(themePalette.panel_bg, 0.64)
    readonly property color chromeBorderColor: themePalette.border
    readonly property color titleColor: themePalette.group_title_fg
    readonly property color toggleHoverColor: themePalette.hover
    readonly property color togglePressedColor: themePalette.pressed
    readonly property color toggleBorderColor: themePalette.border
    readonly property color toggleCollapsedColor: themePalette.toolbar_bg
    readonly property color toggleIconColor: themePalette.panel_title_fg
    readonly property color viewportBackdropColor: Qt.alpha(themePalette.canvas_bg, 0.72)
    readonly property color viewportBackdropBorderColor: themePalette.border
    readonly property color minimapNodeSelectedColor: Qt.alpha(themePalette.accent, 0.28)
    readonly property color minimapNodeColor: Qt.alpha(themePalette.border, 0.45)
    readonly property color minimapNodeSelectedBorderColor: themePalette.accent
    readonly property color minimapNodeBorderColor: themePalette.muted_fg
    readonly property color viewportRectFillColor: Qt.alpha(themePalette.accent, 0.18)
    readonly property color viewportRectBorderColor: themePalette.accent
    readonly property var selectedNodeLookup: root.sceneStateBridge ? root.sceneStateBridge.selected_node_lookup : ({})
    property int profileMinimapStaticUpdateCount: 0
    property real profileLastMinimapStaticUpdateMs: 0.0
    property int profileMinimapViewportUpdateCount: 0
    property real profileLastMinimapViewportUpdateMs: 0.0
    property int profileMinimapStaticNodeCount: 0
    property int profileMinimapNodeDelegateCreateCount: 0

    z: 140
    visible: root.canvasItem ? root.canvasItem.minimapVisible : true
    enabled: visible
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    anchors.rightMargin: 12
    anchors.bottomMargin: 12
    width: root.canvasItem && root.isExpanded
        ? root.canvasItem.minimapExpandedWidth
        : (root.canvasItem ? root.canvasItem.minimapCollapsedWidth : 28)
    height: root.canvasItem && root.isExpanded
        ? root.canvasItem.minimapExpandedHeight
        : (root.canvasItem ? root.canvasItem.minimapCollapsedHeight : 28)
    radius: 6
    color: root.chromeColor
    border.width: 1
    border.color: root.isExpanded ? root.chromeBorderColor : (minimapToggleMouse.containsMouse || minimapToggleMouse.pressed ? root.chromeBorderColor : "transparent")
    clip: true

    Behavior on width {
        NumberAnimation { duration: 200; easing.type: Easing.InOutCubic }
    }
    Behavior on height {
        NumberAnimation { duration: 200; easing.type: Easing.InOutCubic }
    }
    Behavior on border.color {
        ColorAnimation { duration: 120 }
    }

    // Expanded header: label + collapse toggle
    Text {
        visible: root.isExpanded
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.top: parent.top
        anchors.topMargin: 6
        text: "MINIMAP"
        color: root.titleColor
        font.pixelSize: 9
        font.bold: true
    }

    // Toggle button — ghost icon-only style.
    // Collapsed: fills the entire root and shows "expand" chevron.
    // Expanded: small button in top-right shows "collapse" chevron.
    Rectangle {
        id: minimapToggle
        objectName: "graphCanvasMinimapToggle"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: root.isExpanded ? 3 : 0
        anchors.rightMargin: root.isExpanded ? 3 : 0
        width: root.isExpanded ? 22 : parent.width
        height: root.isExpanded ? 22 : parent.height
        radius: root.isExpanded ? 4 : root.radius
        color: minimapToggleMouse.pressed
            ? root.togglePressedColor
            : (minimapToggleMouse.containsMouse ? root.toggleHoverColor : root.toggleCollapsedColor)
        border.width: (minimapToggleMouse.containsMouse || minimapToggleMouse.pressed) ? 1 : 0
        border.color: root.toggleBorderColor

        Image {
            anchors.centerIn: parent
            source: root.isExpanded
                ? uiIcons.sourceSized("chevron-down", 12, String(root.toggleIconColor))
                : uiIcons.sourceSized("chevron-up", 14, String(root.toggleIconColor))
            width: root.isExpanded ? 12 : 14
            height: root.isExpanded ? 12 : 14
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        Common.ManagedToolTip {
            policyBridge: root.tooltipPolicyBridge
            category: root.tooltipCategory
            active: minimapToggleMouse.containsMouse
            text: TooltipCopy.text(tooltipCopyBridge, root.toggleTooltipKey)
            textFormat: root.tooltipTextFormat
            delay: 400
        }

        MouseArea {
            id: minimapToggleMouse
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            hoverEnabled: true
            preventStealing: true
            onClicked: {
                if (!root.canvasItem)
                    return;
                root.canvasItem.forceActiveFocus();
                root.canvasItem.toggleMinimapExpanded();
                mouse.accepted = true;
            }
        }
    }

    Item {
        id: minimapViewport
        objectName: "graphCanvasMinimapViewport"
        visible: root.minimapContentVisible
        x: 4
        y: 24
        width: Math.max(
            1.0,
            root.canvasItem
                ? root.canvasItem.minimapExpandedWidth - 8.0
                : parent.width - 8.0
        )
        height: Math.max(
            1.0,
            root.canvasItem
                ? root.canvasItem.minimapExpandedHeight - 28.0
                : parent.height - 28.0
        )
        property real contentPadding: 7
        readonly property var sceneRectPayload: _normalizeRectPayload(
            root.sceneStateBridge
                ? root.sceneStateBridge.workspace_scene_bounds_payload
                : null,
            -1600.0,
            -900.0,
            3200.0,
            1800.0
        )
        readonly property var visibleRectPayload: _normalizeRectPayload(
            root.viewStateBridge
                ? (root.viewStateBridge.visible_scene_rect_payload_cached !== undefined
                    ? root.viewStateBridge.visible_scene_rect_payload_cached
                    : root.viewStateBridge.visible_scene_rect_payload)
                : null,
            sceneRectPayload.x,
            sceneRectPayload.y,
            sceneRectPayload.width,
            sceneRectPayload.height
        )
        readonly property real contentScale: {
            var availableWidth = Math.max(1.0, width - contentPadding * 2.0);
            var availableHeight = Math.max(1.0, height - contentPadding * 2.0);
            return Math.min(
                availableWidth / sceneRectPayload.width,
                availableHeight / sceneRectPayload.height
            );
        }
        readonly property real contentWidth: sceneRectPayload.width * contentScale
        readonly property real contentHeight: sceneRectPayload.height * contentScale
        readonly property real contentOffsetX: (width - contentWidth) * 0.5
        readonly property real contentOffsetY: (height - contentHeight) * 0.5
        readonly property real minimumNodeExtentScene: 2.0 / Math.max(1e-6, contentScale)
        readonly property string nodeGeometryCacheKey: [
            Number(sceneRectPayload.x).toFixed(3),
            Number(sceneRectPayload.y).toFixed(3),
            Number(sceneRectPayload.width).toFixed(3),
            Number(sceneRectPayload.height).toFixed(3),
            Number(contentScale).toFixed(6),
            Number(contentOffsetX).toFixed(3),
            Number(contentOffsetY).toFixed(3)
        ].join("|")
        property int _nodeDelegateCreationCount: 0
        property string _lastStaticCacheKey: ""
        readonly property var minimapNodesModel: root.sceneStateBridge
            ? root.sceneStateBridge.minimap_nodes_model
            : []

        function _minimapNodesModel() {
            return minimapNodesModel || [];
        }

        function _minimapNodeCount() {
            var model = _minimapNodesModel();
            if (!model || model.length === undefined)
                return 0;
            return Number(model.length || 0);
        }

        function _currentStaticCacheKey() {
            return [
                nodeGeometryCacheKey,
                _minimapNodeCount()
            ].join("|");
        }

        function refreshStaticCache(forceRefresh) {
            var startedMs = Date.now();
            var force = Boolean(forceRefresh);
            var nodeCount = _minimapNodeCount();
            var cacheKey = _currentStaticCacheKey();
            root.profileMinimapStaticNodeCount = nodeCount;
            if (!force && cacheKey === _lastStaticCacheKey)
                return false;

            _lastStaticCacheKey = cacheKey;
            root.profileMinimapStaticUpdateCount += 1;
            root.profileLastMinimapStaticUpdateMs = Math.max(0.0, Date.now() - startedMs);
            return true;
        }

        function recordViewportUpdate(startedMs) {
            root.profileMinimapViewportUpdateCount += 1;
            root.profileLastMinimapViewportUpdateMs = Math.max(0.0, Date.now() - Number(startedMs || Date.now()));
        }

        onNodeGeometryCacheKeyChanged: refreshStaticCache()
        onVisibleChanged: {
            if (visible)
                refreshStaticCache();
        }
        Component.onCompleted: refreshStaticCache()

        function _normalizeRectPayload(payload, fallbackX, fallbackY, fallbackWidth, fallbackHeight) {
            return GraphCanvasLogic.normalizeRectPayload(
                payload,
                fallbackX,
                fallbackY,
                fallbackWidth,
                fallbackHeight
            );
        }

        function sceneToMinimapX(sceneX) {
            return contentOffsetX + (Number(sceneX) - sceneRectPayload.x) * contentScale;
        }

        function sceneToMinimapY(sceneY) {
            return contentOffsetY + (Number(sceneY) - sceneRectPayload.y) * contentScale;
        }

        function minimapToSceneX(minimapX) {
            return sceneRectPayload.x + (Number(minimapX) - contentOffsetX) / Math.max(1e-6, contentScale);
        }

        function minimapToSceneY(minimapY) {
            return sceneRectPayload.y + (Number(minimapY) - contentOffsetY) / Math.max(1e-6, contentScale);
        }

        Rectangle {
            anchors.fill: parent
            radius: 2
            color: root.viewportBackdropColor
            border.width: 1
            border.color: root.viewportBackdropBorderColor
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            onPressed: {
                if (!root.canvasItem)
                    return;
                root.canvasItem.forceActiveFocus();
                root.canvasItem._closeContextMenus();
            }
            onClicked: {
                if (!root.viewCommandBridge)
                    return;
                root.viewCommandBridge.center_on_scene_point(
                    minimapViewport.minimapToSceneX(mouse.x),
                    minimapViewport.minimapToSceneY(mouse.y)
                );
                mouse.accepted = true;
            }
        }

        Item {
            id: minimapNodeContent
            objectName: "graphCanvasMinimapNodeContent"
            x: minimapViewport.contentOffsetX
            y: minimapViewport.contentOffsetY
            width: minimapViewport.sceneRectPayload.width
            height: minimapViewport.sceneRectPayload.height
            scale: minimapViewport.contentScale
            transformOrigin: Item.TopLeft

            Repeater {
                id: minimapNodeRepeater
                model: minimapViewport.minimapNodesModel
                delegate: Rectangle {
                    Component.onCompleted: {
                        minimapViewport._nodeDelegateCreationCount += 1;
                        root.profileMinimapNodeDelegateCreateCount += 1;
                    }
                    readonly property bool selectedState: Boolean(
                        root.selectedNodeLookup[String(modelData.node_id || "")]
                    )
                    readonly property real sceneWidthValue: {
                        var value = Number(modelData.width);
                        return isFinite(value) && value > 0.0
                            ? value
                            : minimapViewport.minimumNodeExtentScene;
                    }
                    readonly property real sceneHeightValue: {
                        var value = Number(modelData.height);
                        return isFinite(value) && value > 0.0
                            ? value
                            : minimapViewport.minimumNodeExtentScene;
                    }
                    x: Number(modelData.x) - minimapViewport.sceneRectPayload.x
                    y: Number(modelData.y) - minimapViewport.sceneRectPayload.y
                    width: Math.max(minimapViewport.minimumNodeExtentScene, sceneWidthValue)
                    height: Math.max(minimapViewport.minimumNodeExtentScene, sceneHeightValue)
                    color: selectedState ? root.minimapNodeSelectedColor : root.minimapNodeColor
                    border.width: (selectedState ? 1.2 : 1.0) / Math.max(1e-6, minimapViewport.contentScale)
                    border.color: selectedState
                        ? root.minimapNodeSelectedBorderColor
                        : root.minimapNodeBorderColor
                    radius: 1.0 / Math.max(1e-6, minimapViewport.contentScale)
                }
            }
        }

        Rectangle {
            id: minimapViewportRect
            objectName: "graphCanvasMinimapViewportRect"
            property int _geometryUpdateCount: 0
            readonly property string geometryKey: [
                Number(x).toFixed(3),
                Number(y).toFixed(3),
                Number(width).toFixed(3),
                Number(height).toFixed(3)
            ].join("|")
            function recordGeometryUpdate() {
                var startedMs = Date.now();
                _geometryUpdateCount += 1;
                minimapViewport.recordViewportUpdate(startedMs);
            }
            property real contentWidth: minimapViewport.contentWidth
            property real contentHeight: minimapViewport.contentHeight
            width: Math.max(10, Math.min(contentWidth, minimapViewport.visibleRectPayload.width * minimapViewport.contentScale))
            height: Math.max(10, Math.min(contentHeight, minimapViewport.visibleRectPayload.height * minimapViewport.contentScale))
            x: {
                var raw = minimapViewport.sceneToMinimapX(minimapViewport.visibleRectPayload.x);
                var minX = minimapViewport.contentOffsetX;
                return Math.max(minX, Math.min(raw, minX + contentWidth - width));
            }
            y: {
                var raw = minimapViewport.sceneToMinimapY(minimapViewport.visibleRectPayload.y);
                var minY = minimapViewport.contentOffsetY;
                return Math.max(minY, Math.min(raw, minY + contentHeight - height));
            }
            color: root.viewportRectFillColor
            border.width: 1
            border.color: root.viewportRectBorderColor
            radius: 2
            onXChanged: recordGeometryUpdate()
            onYChanged: recordGeometryUpdate()
            onWidthChanged: recordGeometryUpdate()
            onHeightChanged: recordGeometryUpdate()

            MouseArea {
                id: minimapViewportDragArea
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                cursorShape: Qt.SizeAllCursor
                preventStealing: true
                onPressed: {
                    if (!root.canvasItem)
                        return;
                    root.canvasItem.forceActiveFocus();
                    root.canvasItem._closeContextMenus();
                    if (root.viewCommandBridge) {
                        root.viewCommandBridge.center_on_scene_point(
                            minimapViewport.minimapToSceneX(minimapViewportRect.x + mouse.x),
                            minimapViewport.minimapToSceneY(minimapViewportRect.y + mouse.y)
                        );
                    }
                    mouse.accepted = true;
                }
                onPositionChanged: {
                    if (!pressed || !root.viewCommandBridge)
                        return;
                    root.viewCommandBridge.center_on_scene_point(
                        minimapViewport.minimapToSceneX(minimapViewportRect.x + mouse.x),
                        minimapViewport.minimapToSceneY(minimapViewportRect.y + mouse.y)
                    );
                    mouse.accepted = true;
                }
            }
        }
    }
}
