import QtQuick 2.15
import "GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics
import "surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    objectName: "graphNodeSettingsGroupsLayer"
    property Item host: null
    readonly property var settingsGroups: host ? host.settingsGroups : []
    readonly property var settingsBand: host ? host.settingsBand : ({})
    readonly property real bandYOffset: host && host.nodeData
        ? GraphNodeSurfaceMetrics.settingsBandYOffset(host.nodeData, host.settingsGroupLayoutHeight)
        : 0.0
    readonly property bool interactionLocked: host ? Boolean(host.surfaceInteractionLocked) : true
    readonly property bool contentInteractionLocked: interactionLocked
        || Boolean(host && host.settingsGroupAnimationRunning)
    signal expansionRequested(string nodeId, string groupId, bool expanded)

    readonly property real _interactiveRectGeometryKey: {
        var total = groupRepeater.count;
        for (var index = 0; index < groupRepeater.count; index++) {
            var groupItem = groupRepeater.itemAt(index);
            if (groupItem)
                total += Number(groupItem.interactiveGeometryKey || 0);
        }
        return total;
    }
    readonly property var embeddedInteractiveRects: {
        var _geometryKey = root._interactiveRectGeometryKey;
        var lists = [];
        for (var index = 0; index < groupRepeater.count; index++) {
            var groupItem = groupRepeater.itemAt(index);
            if (groupItem)
                lists.push(groupItem.currentInteractiveRects());
        }
        return SurfaceControlGeometry.combineRectLists(lists);
    }

    visible: settingsGroups.length > 0
        && host
        && host.nodeData
        && !Boolean(host.nodeData.collapsed)
    z: 4
    clip: Boolean(host && host.settingsGroupAnimationRunning)

    Repeater {
        id: groupRepeater
        model: root.settingsGroups

        delegate: Item {
            id: groupItem
            property var groupData: modelData || ({})
            property var headerData: groupData.header || ({
                "x": 0,
                "y": Number(groupData.header_y || 0),
                "width": root.width,
                "height": Number(groupData.header_height || 0)
            })
            readonly property bool expanded: Boolean(groupData.expanded)
            readonly property real animationYOffset: root.host
                ? Number(root.host.settingsGroupOffsets[String(groupData.group_id)] || 0)
                : 0
            readonly property real interactiveGeometryKey: {
                var total = headerRow.x + headerRow.y + headerRow.width + headerRow.height;
                total += headerRow.visible && headerMouse.enabled ? 1 : 0;
                for (var index = 0; index < itemRepeater.count; index++) {
                    var item = itemRepeater.itemAt(index);
                    if (item)
                        total += Number(item.interactiveGeometryKey || 0);
                }
                return total;
            }

            width: root.width
            height: root.host && root.host.settingsGroupAnimationRunning
                ? root.host.settingsGroupContentBottom(String(groupData.group_id)) : root.height
            clip: Boolean(root.host && root.host.settingsGroupAnimationRunning)

            function currentInteractiveRects() {
                var lists = [];
                if (headerRow.visible && headerMouse.enabled) {
                    lists.push(SurfaceControlGeometry.rectList({
                        "x": headerRow.x,
                        "y": headerRow.y,
                        "width": headerRow.width,
                        "height": headerRow.height
                    }));
                }
                for (var index = 0; index < itemRepeater.count; index++) {
                    var item = itemRepeater.itemAt(index);
                    if (item)
                        lists.push(item.currentInteractiveRects());
                }
                return SurfaceControlGeometry.combineRectLists(lists);
            }

            function requestExpansion() {
                if (!root.host || !root.host.nodeData || !headerRow.groupId.length)
                    return;
                root.expansionRequested(
                    String(root.host.nodeData.node_id || ""),
                    headerRow.groupId,
                    !groupItem.expanded
                );
            }

            Item {
                id: headerRow
                objectName: "graphNodeSettingsGroupHeader"
                property string groupId: String(groupItem.groupData.group_id || "")
                x: Number(groupItem.headerData.x || 0)
                y: Number(groupItem.headerData.y || 0) + root.bandYOffset + groupItem.animationYOffset
                width: {
                    if (root.host && root.host.settingsGroupAnimationRunning)
                        return Math.max(0, groupItem.width - x);
                    var numeric = Number(groupItem.headerData.width);
                    return isFinite(numeric) && numeric > 0 ? numeric : groupItem.width;
                }
                height: Math.max(0, Number(groupItem.headerData.height || 0))
                Accessible.name: String(groupItem.groupData.label || groupItem.groupData.group_id || "Settings")
                Accessible.description: groupItem.expanded
                    ? "Expanded settings group."
                    : "Collapsed settings group."

                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.width: headerMouse.activeFocus ? 1 : 0
                    border.color: root.host ? root.host.selectedOutlineColor : "#60CDFF"
                    radius: 3
                }

                Text {
                    id: groupLabel
                    objectName: "graphNodeSettingsGroupLabel"
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(groupItem.groupData.label || groupItem.groupData.group_id || "")
                    color: root.interactionLocked
                        ? (root.host ? root.host.inlineDrivenTextColor : "#95a0b8")
                        : (root.host ? root.host.inlineLabelColor : "#d0d5de")
                    font.pixelSize: root.host ? root.host.effectiveGraphLabelPixelSize : 10
                    font.weight: Font.Medium
                    renderType: root.host ? root.host.nodeTextRenderType : Text.QtRendering
                }

                Rectangle {
                    objectName: "graphNodeSettingsGroupDivider"
                    anchors.left: groupLabel.right
                    anchors.leftMargin: 8
                    anchors.right: chevron.left
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    height: 1
                    color: root.host ? root.host.inlineDrivenTextColor : "#95a0b8"
                    opacity: 0.38
                }

                Rectangle {
                    id: chevron
                    objectName: "graphNodeSettingsGroupChevron"
                    readonly property bool expandedState: groupItem.expanded
                    readonly property string direction: expandedState ? "down" : "right"
                    readonly property color decorationColor: root.host
                        ? root.host.inlineDrivenTextColor
                        : "#95a0b8"
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 12
                    height: width
                    radius: width * 0.5
                    color: expandedState ? decorationColor : "transparent"
                    border.width: expandedState ? 0 : 1.2
                    border.color: decorationColor

                    Canvas {
                        objectName: "graphNodeSettingsGroupChevronGlyph"
                        anchors.centerIn: parent
                        width: 7
                        height: 7
                        antialiasing: true
                        readonly property bool expandedState: chevron.expandedState
                        readonly property color strokeColor: expandedState
                            ? "#FFFFFF"
                            : chevron.decorationColor

                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.clearRect(0, 0, width, height);
                            ctx.beginPath();
                            if (expandedState) {
                                ctx.moveTo(1.0, 2.25);
                                ctx.lineTo(3.5, 4.75);
                                ctx.lineTo(6.0, 2.25);
                            } else {
                                ctx.moveTo(2.25, 1.0);
                                ctx.lineTo(4.75, 3.5);
                                ctx.lineTo(2.25, 6.0);
                            }
                            ctx.fillStyle = "transparent";
                            ctx.strokeStyle = strokeColor;
                            ctx.lineWidth = 1.5;
                            ctx.lineCap = "round";
                            ctx.lineJoin = "round";
                            ctx.stroke();
                        }

                        onExpandedStateChanged: requestPaint()
                        onStrokeColorChanged: requestPaint()
                        Component.onCompleted: requestPaint()
                    }
                }

                MouseArea {
                    id: headerMouse
                    objectName: "graphNodeSettingsGroupToggleArea"
                    anchors.fill: parent
                    enabled: !root.interactionLocked
                    acceptedButtons: Qt.LeftButton
                    hoverEnabled: enabled
                    activeFocusOnTab: enabled
                    preventStealing: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    Accessible.name: headerRow.Accessible.name
                    Accessible.description: headerRow.Accessible.description
                    Accessible.role: Accessible.Button
                    onPressed: function(mouse) {
                        if (root.host && root.host.nodeData)
                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                        mouse.accepted = true;
                    }
                    onClicked: function(mouse) {
                        groupItem.requestExpansion();
                        mouse.accepted = true;
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return
                                || event.key === Qt.Key_Enter
                                || event.key === Qt.Key_Space) {
                            groupItem.requestExpansion();
                            event.accepted = true;
                        }
                    }
                }
            }

            Repeater {
                id: itemRepeater
                model: groupItem.groupData.items || []

                delegate: Item {
                    id: settingsItem
                    property var itemData: modelData || ({})
                    readonly property bool ownsPropertyLabel: Boolean(itemData.property)
                    readonly property real interactiveGeometryKey: {
                        var total = x + y + width + height + (visible ? 1 : 0);
                        if (!propertyLayer.visible)
                            return total;
                        var rects = propertyLayer.embeddedInteractiveRects || [];
                        for (var index = 0; index < rects.length; index++) {
                            var rect = rects[index];
                            total += Number(rect.x || 0) + Number(rect.y || 0)
                                + Number(rect.width || 0) + Number(rect.height || 0);
                        }
                        return total;
                    }
                    x: 0
                    y: Number(itemData.y || 0) + root.bandYOffset + groupItem.animationYOffset
                    width: groupItem.width
                    height: Math.max(0, Number(itemData.height || 0))
                    visible: groupItem.expanded && Boolean(itemData.visible)

                    function currentInteractiveRects() {
                        if (!visible || !propertyLayer.visible || root.contentInteractionLocked)
                            return [];
                        var rects = propertyLayer.embeddedInteractiveRects || [];
                        var translated = [];
                        for (var index = 0; index < rects.length; index++) {
                            var rect = rects[index];
                            translated.push({
                                "x": settingsItem.x + propertyLayer.x + Number(rect.x || 0),
                                "y": settingsItem.y + propertyLayer.y + Number(rect.y || 0),
                                "width": Number(rect.width || 0),
                                "height": Number(rect.height || 0)
                            });
                        }
                        return translated;
                    }

                    GraphInlinePropertiesLayer {
                        id: propertyLayer
                        objectName: "graphNodeSettingsGroupInlineProperty"
                        anchors.fill: parent
                        enabled: !root.contentInteractionLocked
                        host: root.host
                        modelOverride: settingsItem.ownsPropertyLabel ? [settingsItem.itemData.property] : []
                        contentHeightOverride: settingsItem.height
                        contentTopOverride: 0
                    }
                }
            }
        }
    }
}
