import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common
import "../common/TooltipPolicy.js" as TooltipPolicy
import "../graph_canvas/CanvasBackgroundStyle.js" as CanvasBackgroundStyle
import "GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics
import "surface_controls" as SurfaceControls
import "surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    objectName: "graphNodePortsLayer"
    property Item host: null
    property string editingPortKey: ""
    property string editingPortDirection: ""
    property string portLabelEditError: ""
    property var contextPortData: null
    readonly property string contextNodeId: root.host && root.host.nodeData
        ? String(root.host.nodeData.node_id || "").trim()
        : ""
    readonly property var graphSharedTypography: root.host ? root.host.graphSharedTypography : null
    readonly property var tooltipPolicyBridge: root.host && root.host.canvasItem && root.host.canvasItem.canvasStateBridgeRef
        ? root.host.canvasItem.canvasStateBridgeRef
        : null
    readonly property var tooltipThemePalette: typeof themeBridge !== "undefined" && themeBridge
        ? themeBridge.palette
        : ({})
    readonly property string portHelpMutedColor: String(root.tooltipThemePalette.muted_fg || "#95a0b8")
    readonly property string portHelpDividerColor: String(root.tooltipThemePalette.border || "#3a3d45")
    readonly property string nodeTooltipPlacement: root.host && root.host.floatingToolbarFlipped ? "above" : "below"
    readonly property real nodeTooltipAnchorScale: root.host
        ? Math.max(0.1, Number(root.host.floatingToolbarZoom || 1.0))
        : 1.0
    readonly property bool hostLockedPlaceholder: root.host ? Boolean(root.host.lockedPlaceholderActive) : false
    readonly property real standardRestPortDiameter: 10
    readonly property real standardActivePortDiameter: 14
    readonly property real dynamicPortControlCenterInterval:
        GraphNodeSurfaceMetrics.DYNAMIC_PORT_HANDLE_CENTER_INTERVAL
    readonly property real dynamicPortTargetDiameter:
        GraphNodeSurfaceMetrics.DYNAMIC_PORT_HANDLE_TARGET_RADIUS * 2
    readonly property real dynamicPortRemoveCenterInterval:
        GraphNodeSurfaceMetrics.DYNAMIC_PORT_REMOVE_CENTER_INTERVAL
    readonly property real dynamicPortRemoveTargetWidth:
        GraphNodeSurfaceMetrics.DYNAMIC_PORT_REMOVE_TARGET_WIDTH
    readonly property real dynamicPortHoverHandoffOverlap: 2
    readonly property real notchDiameter: 18
    // Fixed 6x raster for zoom/HiDPI; keep the shared image cache independent of zoom.
    readonly property size notchSourceSize: Qt.size(54, 108)
    readonly property bool notchedPortsEffective: root.host ? Boolean(root.host._notchedPortsEffective) : false
    readonly property color notchOutlineColor: root.host ? root.host._effectiveChromeOutlineColor : "transparent"
    readonly property real notchOutlineWidth: root.host ? root.host._effectiveChromeBorderWidth : 0
    readonly property color notchColor: CanvasBackgroundStyle.fillColor(
        root.host && root.host.prefs ? root.host.prefs.canvasBackgroundVariant : "theme",
        typeof themeBridge !== "undefined" && themeBridge ? themeBridge.palette : ({})
    )
    readonly property url notchSvgSource: root._notchSvgSource()
    readonly property var settingsGroups: root.host ? root.host.settingsGroups : []
    readonly property real settingsBandYOffset: root.host && root.host.nodeData
        ? GraphNodeSurfaceMetrics.settingsBandYOffset(
            root.host.nodeData,
            root.host.settingsGroupLayoutHeight
        )
        : 0.0
    readonly property color settingsGroupPortColor: root.host
        ? ((root.host.portStatePalette || ({})).valid || "#67D487")
        : "#67D487"
    readonly property var _visibleInputPorts: {
        if (!root.host)
            return [];
        var list = root.host.inputPorts || [];
        if (root.hostLockedPlaceholder && list.length > 1)
            return [list[0]];
        return list;
    }
    readonly property var _visibleOutputPorts: {
        if (!root.host)
            return [];
        var list = root.host.outputPorts || [];
        if (root.hostLockedPlaceholder && list.length > 1)
            return [list[0]];
        return list;
    }
    property var dynamicPortGroups: []
    property int dynamicPortGroupModelRevision: 0
    property int _dynamicPortGroupSyncGeneration: 0
    property bool _dynamicPortGroupSyncScheduled: false
    property string _dynamicPortGroupFallbackNodeId: ""
    property var _dynamicPortGroupFallbackGroups: null
    signal dynamicPortGroupsApplied(string nodeId, int revision)
    readonly property real _interactiveRectGeometryKey: {
        var total = inputPortsRepeater.count;
        for (var index = 0; index < inputPortsRepeater.count; ++index) {
            var row = inputPortsRepeater.itemAt(index);
            if (!row)
                continue;
            total += row.x + row.y + row.width + row.height + (row.visible ? 1 : 0);
            var rects = row.currentEmbeddedInteractiveRects();
            for (var rectIndex = 0; rectIndex < rects.length; ++rectIndex) {
                var rect = rects[rectIndex];
                total += Number(rect.x || 0) + Number(rect.y || 0)
                    + Number(rect.width || 0) + Number(rect.height || 0);
            }
        }
        for (var outputIndex = 0; outputIndex < outputPortsRepeater.count; ++outputIndex) {
            var outputRow = outputPortsRepeater.itemAt(outputIndex);
            if (!outputRow)
                continue;
            total += outputRow.x + outputRow.y + outputRow.width + outputRow.height
                + (outputRow.visible ? 1 : 0);
            var outputRects = outputRow.currentEmbeddedInteractiveRects();
            for (var outputRectIndex = 0; outputRectIndex < outputRects.length; ++outputRectIndex) {
                var outputRect = outputRects[outputRectIndex];
                total += Number(outputRect.x || 0) + Number(outputRect.y || 0)
                    + Number(outputRect.width || 0) + Number(outputRect.height || 0);
            }
        }
        for (var groupIndex = 0; groupIndex < dynamicPortGroupRepeater.count; ++groupIndex) {
            var groupControl = dynamicPortGroupRepeater.itemAt(groupIndex);
            if (!groupControl)
                continue;
            total += groupControl.x + groupControl.y + groupControl.width + groupControl.height
                + (groupControl.visible ? 1 : 0);
        }
        return total;
    }
    readonly property var embeddedInteractiveRects: {
        var _geometryKey = root._interactiveRectGeometryKey;
        var lists = [];
        for (var index = 0; index < inputPortsRepeater.count; ++index) {
            var row = inputPortsRepeater.itemAt(index);
            if (row)
                lists.push(row.currentEmbeddedInteractiveRects());
        }
        for (var outputIndex = 0; outputIndex < outputPortsRepeater.count; ++outputIndex) {
            var outputRow = outputPortsRepeater.itemAt(outputIndex);
            if (outputRow)
                lists.push(outputRow.currentEmbeddedInteractiveRects());
        }
        for (var groupIndex = 0; groupIndex < dynamicPortGroupRepeater.count; ++groupIndex) {
            var groupControl = dynamicPortGroupRepeater.itemAt(groupIndex);
            if (groupControl && groupControl.visible)
                lists.push(groupControl.embeddedInteractiveRects);
        }
        return SurfaceControlGeometry.combineRectLists(lists);
    }
    z: 5

    onHostChanged: root._scheduleDynamicPortGroupSync()
    onContextNodeIdChanged: {
        root.dynamicPortGroups = [];
        root._dynamicPortGroupFallbackNodeId = "";
        root._dynamicPortGroupFallbackGroups = null;
        root._scheduleDynamicPortGroupSync();
    }
    Component.onCompleted: root._scheduleDynamicPortGroupSync()

    Connections {
        target: root.host
        ignoreUnknownSignals: true

        function onNodeDataChanged() {
            root._scheduleDynamicPortGroupSync();
        }
    }

    Connections {
        target: root.host && root.host.canvasItem
            ? root.host.canvasItem.sceneStateBridge
            : null
        ignoreUnknownSignals: true

        function onNodes_changed() {
            root._retainDynamicPortGroupsFromSceneDelta();
            root._scheduleDynamicPortGroupSync();
        }

        function onScene_nodes_changed() {
            root._retainDynamicPortGroupsFromSceneDelta();
            root._scheduleDynamicPortGroupSync();
        }
    }

    function _copyDynamicPortGroups(groups) {
        var copiedGroups = [];
        var sourceGroups = groups || [];
        for (var groupIndex = 0; groupIndex < sourceGroups.length; ++groupIndex) {
            var sourceGroup = sourceGroups[groupIndex] || ({});
            var copiedGroup = {};
            for (var fieldName in sourceGroup)
                copiedGroup[fieldName] = sourceGroup[fieldName];
            var portKeys = [];
            var sourcePortKeys = sourceGroup.port_keys || [];
            for (var portIndex = 0; portIndex < sourcePortKeys.length; ++portIndex)
                portKeys.push(sourcePortKeys[portIndex]);
            copiedGroup.port_keys = portKeys;
            var removablePortKeys = [];
            var sourceRemovablePortKeys = sourceGroup.removable_port_keys || [];
            for (var removableIndex = 0; removableIndex < sourceRemovablePortKeys.length; ++removableIndex)
                removablePortKeys.push(sourceRemovablePortKeys[removableIndex]);
            copiedGroup.removable_port_keys = removablePortKeys;
            copiedGroups.push(copiedGroup);
        }
        return copiedGroups;
    }

    function _payloadHasDynamicPortGroups(payload) {
        return Boolean(payload)
            && payload.dynamic_port_groups !== undefined
            && payload.dynamic_port_groups !== null
            && payload.dynamic_port_groups.length !== undefined;
    }

    function _scheduleDynamicPortGroupSync() {
        root._dynamicPortGroupSyncGeneration += 1;
        if (root._dynamicPortGroupSyncScheduled)
            return;
        root._dynamicPortGroupSyncScheduled = true;
        Qt.callLater(function() {
            if (!root._dynamicPortGroupSyncScheduled)
                return;
            root._dynamicPortGroupSyncScheduled = false;
            var scheduledGeneration = root._dynamicPortGroupSyncGeneration;
            var scheduledNodeId = root.contextNodeId;
            root._applyScheduledDynamicPortGroupSync(
                scheduledNodeId,
                scheduledGeneration
            );
        });
    }

    function _retainDynamicPortGroupsFromSceneDelta() {
        var sceneStateBridge = root.host && root.host.canvasItem
            ? root.host.canvasItem.sceneStateBridge
            : null;
        var deltaPayload = sceneStateBridge
            && sceneStateBridge.node_delta_payload !== undefined
            ? sceneStateBridge.node_delta_payload
            : ({});
        var nodePayloads = deltaPayload && deltaPayload.nodes
            ? deltaPayload.nodes
            : [];
        var nodeId = root.contextNodeId;
        for (var nodeIndex = 0; nodeIndex < nodePayloads.length; ++nodeIndex) {
            var nodePayload = nodePayloads[nodeIndex] || ({});
            if (String(nodePayload.node_id || "") === nodeId
                    && root._payloadHasDynamicPortGroups(nodePayload)) {
                root._dynamicPortGroupFallbackNodeId = nodeId;
                root._dynamicPortGroupFallbackGroups = root._copyDynamicPortGroups(
                    nodePayload.dynamic_port_groups
                );
                return;
            }
        }
    }

    function _applyScheduledDynamicPortGroupSync(nodeId, generation) {
        if (generation !== root._dynamicPortGroupSyncGeneration
                || nodeId !== root.contextNodeId)
            return;
        var hostPayload = root.host && root.host.nodeData
            ? root.host.nodeData
            : null;
        var groups = null;
        if (hostPayload
                && String(hostPayload.node_id || "") === nodeId
                && root._payloadHasDynamicPortGroups(hostPayload)) {
            groups = hostPayload.dynamic_port_groups;
        } else if (root._dynamicPortGroupFallbackNodeId === nodeId
                && root._dynamicPortGroupFallbackGroups !== null) {
            groups = root._dynamicPortGroupFallbackGroups;
        }
        if (groups === null)
            return;
        root.dynamicPortGroups = root._copyDynamicPortGroups(groups);
        root.dynamicPortGroupModelRevision += 1;
        root.dynamicPortGroupsApplied(
            nodeId,
            root.dynamicPortGroupModelRevision
        );
        if (root._dynamicPortGroupFallbackNodeId === nodeId) {
            root._dynamicPortGroupFallbackNodeId = "";
            root._dynamicPortGroupFallbackGroups = null;
        }
    }

    function _colorChannel(value) {
        return Math.max(0, Math.min(255, Math.round(Number(value) * 255)));
    }

    function _svgOpacity(value) {
        return Math.max(0.0, Math.min(1.0, Number(value))).toFixed(4);
    }

    function _svgNumber(value) {
        return Number(value).toFixed(3).replace(/\.?0+$/, "");
    }

    function _svgColor(value) {
        return "rgb(" + root._colorChannel(value.r)
            + "," + root._colorChannel(value.g)
            + "," + root._colorChannel(value.b) + ")";
    }

    function _notchSvgSource() {
        var strokeWidth = Math.max(0.0, Number(root.notchOutlineWidth));
        var halfStroke = strokeWidth * 0.5;
        var radius = Math.max(0.0, 9.0 - halfStroke);
        var bottom = 18.0 - halfStroke;
        var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="9" height="18" viewBox="0 0 9 18">'
            + '<path d="M0 0 A9 9 0 0 1 0 18 Z" fill="' + root._svgColor(root.notchColor)
            + '" fill-opacity="' + root._svgOpacity(root.notchColor.a) + '"/>';
        if (strokeWidth > 0.0) {
            svg += '<path d="M' + root._svgNumber(halfStroke) + ' ' + root._svgNumber(halfStroke)
                + ' A' + root._svgNumber(radius) + ' ' + root._svgNumber(radius)
                + ' 0 0 1 ' + root._svgNumber(halfStroke) + ' ' + root._svgNumber(bottom)
                + '" fill="none" stroke="' + root._svgColor(root.notchOutlineColor)
                + '" stroke-opacity="' + root._svgOpacity(root.notchOutlineColor.a)
                + '" stroke-width="' + root._svgNumber(strokeWidth) + '" stroke-linecap="round"/>';
        }
        svg += '</svg>';
        return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    }

    function _portFlowOutlineColor(portData) {
        if (!root.host)
            return root.settingsGroupPortColor;
        var groupId = String(portData && portData.settings_group_id || "").trim();
        var state = String(root.host.resolvedPortFlowState(portData));
        if (groupId.length > 0
                && state !== "waiting"
                && state !== "idle"
                && state !== "invalid"
                && state !== "invalid_muted") {
            return root.settingsGroupPortColor;
        }
        return root.host.portFlowOutlineColor(portData);
    }

    function _dynamicPortGroupById(groupId) {
        var normalizedId = String(groupId || "").trim();
        for (var index = 0; index < root.dynamicPortGroups.length; ++index) {
            var group = root.dynamicPortGroups[index] || ({});
            if (String(group.id || "").trim() === normalizedId)
                return group;
        }
        return null;
    }

    function _dynamicPortGroupForPort(portData) {
        var portKey = root._portKey(portData);
        var direction = root._interactionDirection(portData, "");
        if (!portKey.length || (direction !== "in" && direction !== "out"))
            return null;
        for (var index = 0; index < root.dynamicPortGroups.length; ++index) {
            var group = root.dynamicPortGroups[index] || ({});
            if (String(group.direction || "").trim().toLowerCase() !== direction)
                continue;
            var keys = group.port_keys || [];
            for (var keyIndex = 0; keyIndex < keys.length; ++keyIndex) {
                if (String(keys[keyIndex] || "") === portKey)
                    return group;
            }
        }
        return null;
    }

    function _dynamicPortOrdinal(group, portKey) {
        var keys = group && group.port_keys ? group.port_keys : [];
        var normalizedKey = String(portKey || "");
        for (var index = 0; index < keys.length; ++index) {
            if (String(keys[index] || "") === normalizedKey)
                return index;
        }
        return -1;
    }

    function _dynamicPortCanRemove(portData) {
        var group = root._dynamicPortGroupForPort(portData);
        var removable = group && group.removable_port_keys ? group.removable_port_keys : [];
        var portKey = root._portKey(portData);
        for (var index = 0; index < removable.length; ++index) {
            if (String(removable[index] || "") === portKey)
                return true;
        }
        return false;
    }

    function _dynamicPortAuthoringAllowed() {
        if (!root.contextNodeId.length || !root.host || !root.host.nodeData || root.host.graphReadOnly)
            return false;
        var lockedState = root.host.nodeData.locked_state || ({});
        return !Boolean(root.host.nodeData.locked)
            && !Boolean(lockedState.locked)
            && !Boolean(lockedState.read_only);
    }

    function _dynamicPortInlineControlsVisible() {
        return root._dynamicPortAuthoringAllowed()
            && root.host
            && !Boolean(root.host.nodeData.collapsed)
            && Number(root.host.floatingToolbarZoom || 1.0) >= 0.95;
    }

    function _dynamicPortControlRevealActive(portData) {
        if (!root._dynamicPortInlineControlsVisible() || !root.host)
            return false;
        var direction = root._interactionDirection(portData, "");
        var portKey = root._portKey(portData);
        var repeater = direction === "in" ? inputPortsRepeater : outputPortsRepeater;
        for (var index = 0; index < repeater.count; ++index) {
            var row = repeater.itemAt(index);
            if (!row || String(row.propertyKey || "") !== portKey)
                continue;
            if (row.portMouseAreaItem && row.portMouseAreaItem.containsMouse)
                return true;
            break;
        }
        return root.host.isHoveredPort(direction, portKey);
    }

    function _dynamicPortIsGroupTerminus(portData) {
        var group = root._dynamicPortGroupForPort(portData);
        var keys = group && group.port_keys ? group.port_keys : [];
        return keys.length > 0
            && String(keys[keys.length - 1] || "") === root._portKey(portData);
    }

    function _anyDynamicPortControlRevealActive() {
        var repeaters = [inputPortsRepeater, outputPortsRepeater];
        for (var repeaterIndex = 0; repeaterIndex < repeaters.length; ++repeaterIndex) {
            var repeater = repeaters[repeaterIndex];
            for (var index = 0; index < repeater.count; ++index) {
                var row = repeater.itemAt(index);
                if (row && root._dynamicPortControlRevealActive(row.portData))
                    return true;
            }
        }
        return false;
    }

    function _dynamicGroupControlRevealActive(group) {
        if (!root._dynamicPortInlineControlsVisible() || !root.host)
            return false;
        var keys = group && group.port_keys ? group.port_keys : [];
        if (keys.length === 0)
            return Boolean(root.host.hoveredPort)
                || root._anyDynamicPortControlRevealActive()
                || Boolean(root.host.hoverActive);
        return root._dynamicPortControlRevealActive({
            "direction": String(group.direction || "").trim().toLowerCase(),
            "key": String(keys[keys.length - 1] || "")
        });
    }

    function _isEditablePort(portData) {
        var group = root._dynamicPortGroupForPort(portData);
        if (!group)
            return true;
        return root._dynamicPortAuthoringAllowed()
            && String(group.rename_mode || "none").trim().toLowerCase() !== "none";
    }

    function _directionPorts(direction) {
        return String(direction || "").trim().toLowerCase() === "in"
            ? root._visibleInputPorts
            : root._visibleOutputPorts;
    }

    function _dynamicGroupTerminusPoint(group) {
        if (!root.host)
            return ({"x": 0.0, "y": 0.0});
        var direction = String(group && group.direction || "").trim().toLowerCase();
        var ports = root._directionPorts(direction);
        var keys = group && group.port_keys ? group.port_keys : [];
        for (var keyIndex = keys.length - 1; keyIndex >= 0; --keyIndex) {
            var key = String(keys[keyIndex] || "");
            for (var portIndex = ports.length - 1; portIndex >= 0; --portIndex) {
                var port = ports[portIndex];
                if (root._portKey(port) === key) {
                    var lastPoint = root.host.localPortPointForPort(
                        direction,
                        portIndex,
                        port
                    );
                    return {
                        "x": Number(lastPoint.x || 0),
                        "y": Number(lastPoint.y || 0) + root.dynamicPortControlCenterInterval
                    };
                }
            }
        }
        return root.host.localPortPoint(direction, ports.length);
    }

    function _insertDynamicPort(groupId, ordinal) {
        var group = root._dynamicPortGroupById(groupId);
        if (!group || !Boolean(group.can_insert) || !root._dynamicPortAuthoringAllowed())
            return "";
        var bridge = root.host.canvasItem ? root.host.canvasItem.sceneCommandBridge : null;
        if (!bridge || !bridge.insert_dynamic_port)
            return "";
        return String(
            bridge.insert_dynamic_port(
                root.contextNodeId,
                String(group.id || ""),
                Number(ordinal)
            ) || ""
        );
    }

    function _removeDynamicPort(groupId, portKey) {
        var group = root._dynamicPortGroupById(groupId);
        var portData = {"key": String(portKey || ""), "direction": group ? group.direction : ""};
        if (!group || !root._dynamicPortCanRemove(portData) || !root._dynamicPortAuthoringAllowed())
            return ({});
        var bridge = root.host.canvasItem ? root.host.canvasItem.sceneCommandBridge : null;
        if (!bridge || !bridge.remove_dynamic_port)
            return ({});
        return bridge.remove_dynamic_port(
            root.contextNodeId,
            String(group.id || ""),
            String(portKey || "")
        ) || ({});
    }

    function _renameDynamicPort(groupId, portKey, value) {
        var group = root._dynamicPortGroupById(groupId);
        if (!group
                || String(group.rename_mode || "none").trim().toLowerCase() === "none"
                || !root._dynamicPortAuthoringAllowed()) {
            return ({});
        }
        var bridge = root.host.canvasItem ? root.host.canvasItem.sceneCommandBridge : null;
        if (!bridge || !bridge.rename_dynamic_port)
            return ({});
        return bridge.rename_dynamic_port(
            root.contextNodeId,
            String(group.id || ""),
            String(portKey || ""),
            String(value || "")
        ) || ({});
    }

    function _defaultEditorSupported(propertyData) {
        var editor = String(propertyData && propertyData.inline_editor || "").trim().toLowerCase();
        return editor === "slider"
            || editor === "interval_slider"
            || editor === "toggle"
            || editor === "text"
            || editor === "number"
            || editor === "enum"
            || editor === "path"
            || editor === "color"
            || editor === "textarea"
            || editor === "list"
            || editor === "interval_fields";
    }

    function _defaultEditorHeight(propertyData) {
        var editor = String(propertyData && propertyData.inline_editor || "").trim().toLowerCase();
        var baseHeight = root.host ? root.host._inlineRowHeight : 26;
        var spacing = root.host ? root.host._inlineRowSpacing : 4;
        var pixelSize = Number(root.graphSharedTypography ? root.graphSharedTypography.inlinePropertyPixelSize : 10);
        if (editor === "textarea")
            return root.host ? root.host._inlineTextareaRowHeight : 104;
        if (editor === "list") {
            var listValue = propertyData && propertyData.display_value !== undefined
                ? propertyData.display_value
                : (propertyData ? propertyData.value : []);
            return SurfaceControlGeometry.listEditorRowHeight(listValue, baseHeight);
        }
        if (editor === "interval_fields")
            return root.host ? root.host._inlineStackedRowHeight : baseHeight * 2 + spacing;
        if (editor === "slider" || editor === "interval_slider")
            return root.host ? root.host._inlineSliderRowHeight : baseHeight * 2 + pixelSize + spacing;
        if (editor === "text" || editor === "number" || editor === "enum")
            return root.host ? root.host._inlineStackedRowHeight : baseHeight * 2 + spacing;
        return baseHeight;
    }

    function _defaultEditorAnchorOffset(propertyData, rowHeight) {
        var editor = String(propertyData && propertyData.inline_editor || "").trim().toLowerCase();
        if (editor === "slider"
                || editor === "interval_slider"
                || editor === "text"
                || editor === "number"
                || editor === "enum"
                || editor === "textarea"
                || editor === "list"
                || editor === "interval_fields") {
            var baseHeight = root.host ? root.host._inlineRowHeight : 26;
            return root.host ? root.host._inlineLabelAnchorOffset : baseHeight * 0.5;
        }
        return Math.max(0.0, Number(rowHeight) * 0.5);
    }

    function _isFlowEdgePort(portData) {
        var kind = String(portData && portData.kind || "").trim().toLowerCase();
        return kind === "flow";
    }

    function _isDataPort(portData) {
        return String(portData && portData.kind || "").trim().toLowerCase() === "data";
    }

    function _flowEdgePortRevealActive(portData, attentionState, selectedState) {
        if (!(root.host && root.host.usesCardinalNeutralFlowHandles))
            return true;
        if (!root._isFlowEdgePort(portData))
            return true;
        return Boolean(attentionState)
            || Boolean(selectedState)
            || (root.host ? Boolean(root.host.hoverActive) : false);
    }

    function _interactionDirection(portData, fallbackDirection) {
        var direction = String(portData && portData.direction || "").trim().toLowerCase();
        if (direction === "in" || direction === "out" || direction === "neutral")
            return direction;
        return String(fallbackDirection || "").trim().toLowerCase();
    }

    function _portLabelText(portData) {
        return String(portData && (portData.label || portData.key) || "");
    }

    function _dataAccessLabel(portData) {
        var access = String(portData && portData.data_access || "item").trim().toLowerCase();
        if (access === "list")
            return "List";
        if (access === "tree")
            return "Tree";
        return "Item";
    }

    function _portModifiers(portData) {
        var source = portData && portData.modifiers ? portData.modifiers : [];
        var result = [];
        for (var i = 0; i < source.length; ++i) {
            var modifier = String(source[i] || "").trim().toLowerCase();
            if (modifier.length && result.indexOf(modifier) < 0)
                result.push(modifier);
        }
        return result;
    }

    function _modifierChecked(modifier) {
        return root._portModifiers(root.contextPortData).indexOf(String(modifier || "").toLowerCase()) >= 0;
    }

    function _modifierSummary(portData) {
        if (!root._isDataPort(portData))
            return "";
        var names = root._portModifiers(portData);
        if (!names.length)
            return "";
        return names.map(function(name) {
            return name.charAt(0).toUpperCase() + name.slice(1);
        }).join(", ");
    }

    function _structureIndicatorText(portData) {
        if (!root._isDataPort(portData))
            return "";
        var glyphs = {"graft": "G", "flatten": "F", "simplify": "S", "reverse": "R", "clean": "C"};
        var active = root._portModifiers(portData).map(function(name) { return glyphs[name] || ""; })
            .filter(function(glyph) { return glyph.length > 0; });
        if (Boolean(portData && portData.principal_eligible && portData.principal)
                && String(portData.direction || "") === "in") {
            active.push("P");
        }
        return active.length ? " [" + active.join(" ") + "]" : "";
    }

    function _openPortContext(portData, sourceItem, localX, localY) {
        if (!root._isDataPort(portData) || !sourceItem)
            return;
        root.contextPortData = portData;
        portContextMenu.openAt(sourceItem, localX, localY);
    }

    function _togglePortModifier(modifier) {
        if (!root._isDataPort(root.contextPortData)
                || !root.contextNodeId.length || !root.host || root.host.graphReadOnly)
            return false;
        var bridge = root.host.canvasItem ? root.host.canvasItem.sceneCommandBridge : null;
        if (!bridge || !bridge.set_port_modifiers)
            return false;
        var normalized = String(modifier || "").trim().toLowerCase();
        var next = root._portModifiers(root.contextPortData);
        var index = next.indexOf(normalized);
        if (index >= 0)
            next.splice(index, 1);
        else
            next.push(normalized);
        return Boolean(bridge.set_port_modifiers(root.contextNodeId, String(root.contextPortData.key || ""), next));
    }

    function _togglePrincipal() {
        if (!root._isDataPort(root.contextPortData)
                || !root.contextPortData.principal_eligible
                || String(root.contextPortData.direction || "") !== "in"
                || !root.contextNodeId.length || !root.host || root.host.graphReadOnly)
            return false;
        var bridge = root.host.canvasItem ? root.host.canvasItem.sceneCommandBridge : null;
        if (!bridge || !bridge.set_principal_input_port)
            return false;
        var nextPortKey = Boolean(root.contextPortData.principal)
            ? ""
            : String(root.contextPortData.key || "");
        return Boolean(bridge.set_principal_input_port(root.contextNodeId, nextPortKey));
    }

    function _portStatusText(portData) {
        var direction = String(portData && portData.direction || "");
        var state = root.host ? String(root.host.resolvedPortFlowState(portData) || "") : "";
        if (direction === "out")
            return state === "flowing" ? "Available" : "No current output";
        if (state === "invalid")
            return "Invalid connection";
        if (state === "invalid_muted")
            return "Invalid inactive connection";
        if (portData && portData.connected)
            return "Connected";
        if (state === "default")
            return "Set";
        if (state === "waiting")
            return "Empty";
        return "";
    }

    function _portAvailabilityReason(portData) {
        return String(portData && portData.availability_reason || "").trim();
    }

    function _portInactiveReason(portData) {
        return String(portData && portData.inactive_reason || "").trim();
    }

    function _portInactiveTooltipText(portData) {
        var availabilityReason = root._portAvailabilityReason(portData);
        return availabilityReason.length > 0
            ? availabilityReason
            : root._portInactiveReason(portData);
    }

    function _portAccessibleText(portData) {
        var parts = [];
        var label = root._portLabelText(portData).trim();
        var direction = String(portData && portData.direction || "").trim().toLowerCase();
        var typeLabel = String(
            portData && (portData.data_type_label || portData.data_type) || ""
        ).trim();
        var familyLabel = String(portData && portData.data_type_family_label || "").trim();
        if (label.length > 0)
            parts.push(label);
        if (direction === "in")
            parts.push("Input");
        else if (direction === "out")
            parts.push("Output");
        if (typeLabel.length > 0 && typeLabel.toLowerCase() !== "flow")
            parts.push("Type " + typeLabel);
        if (familyLabel.length > 0)
            parts.push("Family " + familyLabel);
        if (root._isDataPort(portData))
            parts.push("Access " + root._dataAccessLabel(portData));
        var acceptedLabels = portData && portData.accepted_data_type_labels
            ? portData.accepted_data_type_labels
            : [];
        if (acceptedLabels.length > 0)
            parts.push("Accepts " + acceptedLabels.join(", "));
        var availabilityReason = root._portAvailabilityReason(portData);
        if (availabilityReason.length > 0)
            parts.push("Availability " + availabilityReason);
        var inactiveReason = root._portInactiveReason(portData);
        if (inactiveReason.length > 0 && inactiveReason !== availabilityReason)
            parts.push("Inactive " + inactiveReason);
        return parts.join(", ");
    }

    function _portValuePreview(portData) {
        if (!root.host || !root.host.nodeData || !root.host.executionFacts || !portData)
            return null;
        if (String(portData.direction || "") !== "out" || String(portData.kind || "") !== "data")
            return null;
        var lookup = root.host.executionFacts.portValuePreviewLookup || ({});
        var nodeLookup = lookup[String(root.host.nodeData.node_id || "")] || ({});
        return nodeLookup[String(portData.key || "")] || null;
    }

    function _escapePortHelpHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;");
    }

    function _portHelpTooltipText(portData) {
        var title = root._portLabelText(portData).trim();
        var helpText = String(portData && portData.help_text || "").trim();
        var dataType = String(
            portData && (portData.data_type_label || portData.data_type) || ""
        ).trim();
        var familyLabel = String(portData && portData.data_type_family_label || "").trim();
        var direction = String(portData && portData.direction || "").trim();
        if (direction === "neutral")
            return "";
        var statusText = root._portStatusText(portData);
        var metadata = [];
        if (direction.length > 0)
            metadata.push(direction === "in" ? "Input" : (direction === "out" ? "Output" : "Neutral"));
        if (dataType.length > 0 && dataType.toLowerCase() !== "flow")
            metadata.push(dataType);
        if (familyLabel.length > 0)
            metadata.push("Family: " + familyLabel);
        if (String(portData && portData.kind || "") === "data")
            metadata.push(root._dataAccessLabel(portData));
        var acceptedLabels = portData && portData.accepted_data_type_labels
            ? portData.accepted_data_type_labels
            : [];
        if (acceptedLabels.length > 0)
            metadata.push("Accepts: " + acceptedLabels.join(", "));
        var modifierSummary = root._modifierSummary(portData);
        if (modifierSummary.length > 0)
            metadata.push("Modifiers: " + modifierSummary);
        if (portData && portData.principal_eligible && portData.principal)
            metadata.push("Principal input");
        var html = title.length > 0 ? "<b>" + root._escapePortHelpHtml(title) + "</b>" : "";
        if (metadata.length > 0)
            html += "<br><font color=\"" + root._escapePortHelpHtml(root.portHelpMutedColor) + "\">"
                + root._escapePortHelpHtml(metadata.join(", ")) + "</font>";
        if (helpText.length > 0)
            html += "<br>" + root._escapePortHelpHtml(helpText).replace(/\r?\n/g, "<br>");
        var footer = [];
        if (statusText.length > 0)
            footer.push(statusText);
        var preview = root._portValuePreview(portData);
        var previewText = String(preview && preview.tooltip_text || "").trim();
        if (previewText.length > 0)
            footer.push(previewText);
        var availabilityReason = root._portAvailabilityReason(portData);
        if (availabilityReason.length > 0)
            footer.push("Availability: " + availabilityReason);
        var inactiveReason = root._portInactiveReason(portData);
        if (inactiveReason.length > 0 && inactiveReason !== availabilityReason)
            footer.push("Inactive: " + inactiveReason);
        if (footer.length > 0)
            html += "<hr color=\"" + root._escapePortHelpHtml(root.portHelpDividerColor) + "\">"
                + root._escapePortHelpHtml(footer.join("\n")).replace(/\r?\n/g, "<br>");
        return html;
    }

    function _portDisplayText(portData) {
        var label = root._portLabelText(portData);
        if (!root._isDataPort(portData))
            return label;
        return label + root._structureIndicatorText(portData);
    }

    function _portDisplayColor(portData) {
        return root.host ? root.host.portLabelColor : "#d0d5de";
    }

    function _portDisplayPixelSize(portData) {
        return root.graphSharedTypography ? root.graphSharedTypography.portLabelPixelSize : 10;
    }

    function _portDisplayFontWeight(portData) {
        return root.graphSharedTypography ? root.graphSharedTypography.portLabelFontWeight : Font.Normal;
    }

    function _portInactive(portData) {
        return !!(portData && portData.inactive);
    }

    function _portKey(portData) {
        return String(portData && portData.key || "");
    }

    function _resolvedPortRowHeight() {
        var numeric = Number(root.host && root.host.surfaceMetrics ? root.host.surfaceMetrics.port_height : NaN);
        if (!isFinite(numeric) || numeric <= 0.0)
            return 18.0;
        return Math.max(18.0, numeric);
    }

    function beginPortLabelEdit(portKey, direction) {
        root.portLabelEditError = "";
        root.editingPortKey = portKey;
        root.editingPortDirection = direction;
    }

    function cancelPortLabelEdit() {
        root.portLabelEditError = "";
        root.editingPortKey = "";
        root.editingPortDirection = "";
    }

    function _refocusPortLabelEditor() {
        var repeaters = root.editingPortDirection === "in"
            ? inputPortsRepeater
            : outputPortsRepeater;
        for (var index = 0; index < repeaters.count; ++index) {
            var row = repeaters.itemAt(index);
            if (row && row.refocusLabelEditor
                    && String(row.propertyKey || "") === root.editingPortKey) {
                row.refocusLabelEditor();
                return;
            }
        }
    }

    function commitPortLabelEdit(portKey, label) {
        if (root.editingPortKey !== portKey)
            return false;
        if (!root.host || !root.host.nodeData)
            return false;
        var nodeId = root.host.nodeData.node_id;
        var direction = root.editingPortDirection;
        var portData = null;
        var ports = root._directionPorts(direction);
        for (var index = 0; index < ports.length; ++index) {
            if (root._portKey(ports[index]) === String(portKey || "")) {
                portData = ports[index];
                break;
            }
        }
        var group = root._dynamicPortGroupForPort(portData);
        if (group) {
            var result = root._renameDynamicPort(group.id, portKey, label);
            var error = result && result.error ? result.error : null;
            var message = String(error && error.message || "").trim();
            if (message.length > 0) {
                root.portLabelEditError = message;
                Qt.callLater(root._refocusPortLabelEditor);
                return false;
            }
            root.cancelPortLabelEdit();
            return true;
        }
        root.cancelPortLabelEdit();
        var hostRef = root.host;
        Qt.callLater(function() {
            if (hostRef)
                hostRef.portLabelCommitted(nodeId, portKey, label);
        });
        return true;
    }
    visible: root.host && root.host.nodeData ? !root.host.nodeData.collapsed : false

    Repeater {
        model: root.settingsGroups

        delegate: Item {
            id: settingsGroupAggregate
            property var groupData: modelData || ({})
            property string groupId: String(groupData.group_id || "")
            readonly property var anchor: groupData.aggregate_anchor || null
            readonly property int connectedCount: anchor ? Number(anchor.connected_count || 0) : 0
            readonly property real animationYOffset: root.host
                ? Number(root.host.settingsGroupOffsets[groupId] || 0) : 0
            visible: Boolean(anchor) && !Boolean(groupData.expanded)
            width: root.width
            height: root.height

            Image {
                objectName: "graphNodeSettingsGroupAggregateNotch"
                property string groupId: settingsGroupAggregate.groupId
                readonly property bool nodeFacingEdgeOnRight: true
                readonly property color notchFillColor: root.notchColor
                readonly property color notchStrokeColor: root.notchOutlineColor
                readonly property real notchStrokeWidth: root.notchOutlineWidth
                visible: root.notchedPortsEffective
                width: root.notchDiameter * 0.5
                height: root.notchDiameter
                x: settingsGroupAggregate.anchor ? Number(settingsGroupAggregate.anchor.x || 0) : 0
                y: settingsGroupAggregate.anchor
                    ? Number(settingsGroupAggregate.anchor.y || 0)
                        + root.settingsBandYOffset + settingsGroupAggregate.animationYOffset - height * 0.5
                    : 0
                sourceSize: root.notchSourceSize
                source: root.notchSvgSource
                cache: true
                asynchronous: false
                smooth: true
                mipmap: false
                fillMode: Image.Stretch
                z: -1
            }

            Rectangle {
                objectName: "graphNodeSettingsGroupAggregateSocket"
                property string groupId: settingsGroupAggregate.groupId
                property int connectedCount: settingsGroupAggregate.connectedCount
                x: settingsGroupAggregate.anchor
                    ? Number(settingsGroupAggregate.anchor.x || 0) - width * 0.5
                    : 0
                y: settingsGroupAggregate.anchor
                    ? Number(settingsGroupAggregate.anchor.y || 0)
                        + root.settingsBandYOffset + settingsGroupAggregate.animationYOffset - height * 0.5
                    : 0
                width: root.standardRestPortDiameter
                height: width
                radius: width * 0.5
                color: connectedCount > 0
                    ? root.settingsGroupPortColor
                    : (root.host ? root.host.themeSurfaceColor : "transparent")
                border.width: 1.6
                border.color: root.settingsGroupPortColor
            }
        }
    }

    Repeater {
        id: inputPortsRepeater
        model: root._visibleInputPorts

        delegate: GraphNodePortRow {
            id: inputPortRow
            portsLayer: root
            direction: "in"
            defaultPropertyItem: defaultPropertyLayer

            Rectangle {
                objectName: "graphNodeInputPortInactiveSlash"
                property string propertyKey: inputPortRow.propertyKey
                parent: inputPortRow.portDotItem
                visible: inputPortRow.portDotItem.inactiveState
                    && inputPortRow.portDotItem.width > 0
                    && inputPortRow.portDotItem.height > 0
                anchors.centerIn: parent
                width: Math.max(6, inputPortRow.portDotItem.width + 1)
                height: 1.6
                radius: height * 0.5
                rotation: -35
                color: root.host ? root.host.outlineColor : "#95a0b8"
                opacity: 0.9
            }

            Canvas {
                id: inputLockGlyph
                objectName: "graphNodeInputPortPadlock"
                property string propertyKey: inputPortRow.propertyKey
                readonly property bool lockedState: inputPortRow.labelContainerItem.lockedState
                readonly property bool placeholderLockedState: root.hostLockedPlaceholder
                parent: lockedState
                    ? inputPortRow.portDotItem
                    : inputPortRow.labelContainerItem
                visible: lockedState
                x: lockedState ? Math.round((parent.width - width) * 0.5) : 0
                y: Math.round((parent.height - height) * 0.5)
                width: 10
                height: 12
                implicitHeight: height
                antialiasing: true
                opacity: lockedState ? 0.96 : 0.42
                z: 2

                onPaint: inputPortRow.paintPadlock(
                    inputLockGlyph,
                    lockedState,
                    placeholderLockedState
                )
                Component.onCompleted: requestPaint()
                onVisibleChanged: requestPaint()
                onLockedStateChanged: requestPaint()
                onPlaceholderLockedStateChanged: requestPaint()
            }

            GraphInlinePropertiesLayer {
                id: defaultPropertyLayer
                objectName: "graphNodeInputDefaultProperty"
                property string propertyKey: inputPortRow.propertyKey
                x: 0
                y: 0
                width: root.host ? root.host.width : 0
                height: root.host && root.host.settingsGroupAnimationRunning
                    ? Math.min(inputPortRow.height, Math.max(0,
                        root.host.settingsGroupContentBottom(String(inputPortRow.portData.settings_group_id || ""))
                            - inputPortRow.y))
                    : inputPortRow.height
                clip: Boolean(root.host && root.host.settingsGroupAnimationRunning)
                visible: inputPortRow.defaultEditorVisible
                enabled: root.host ? !root.host.surfaceInteractionLocked
                    && !root.host.settingsGroupAnimationRunning : false
                host: root.host
                modelOverride: inputPortRow.defaultEditorVisible
                    ? [inputPortRow.defaultProperty]
                    : []
                contentHeightOverride: inputPortRow.height
                contentTopOverride: 0
                z: 4
            }
        }
    }

    Repeater {
        id: outputPortsRepeater
        model: root._visibleOutputPorts

        delegate: GraphNodePortRow {
            id: outputPortRow
            portsLayer: root
            direction: "out"

            Common.ManagedToolTip {
                parent: outputPortRow.portMouseAreaItem
                policyBridge: root.tooltipPolicyBridge
                category: "inactive"
                active: outputPortRow.portMouseAreaItem.inactiveTooltipVisible
                text: outputPortRow.portMouseAreaItem.inactiveTooltipText
                delay: 240
                screenStablePositioning: true
                screenStablePlacement: root.nodeTooltipPlacement
                anchorScale: root.nodeTooltipAnchorScale
                screenGap: 8
            }

            Loader {
                id: outputLockGlyphLoader
                active: outputPortRow.portDotItem.lockedState
                parent: outputPortRow.portDotItem
                x: Math.round((parent.width - 10) * 0.5)
                y: Math.round((parent.height - 12) * 0.5)
                width: 10
                height: 12
                z: 2
                sourceComponent: Component {
                    Canvas {
                        id: outputLockGlyph
                        objectName: "graphNodeOutputPortPadlock"
                        property string propertyKey: outputPortRow.propertyKey
                        property bool placeholderLockedState: root.hostLockedPlaceholder
                        antialiasing: true
                        opacity: 0.96

                        onPaint: outputPortRow.paintPadlock(
                            outputLockGlyph,
                            true,
                            placeholderLockedState
                        )
                        Component.onCompleted: requestPaint()
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        onPlaceholderLockedStateChanged: requestPaint()
                    }
                }
            }
        }
    }

    Repeater {
        id: dynamicPortGroupRepeater
        model: root.dynamicPortGroups

        delegate: SurfaceControls.GraphSurfaceButton {
            id: dynamicPortAddButton
            objectName: "graphNodeDynamicPortAdd_" + String(modelData && modelData.id || "")
            property string groupId: String(modelData && modelData.id || "")
            property string direction: String(modelData && modelData.direction || "").trim().toLowerCase()
            readonly property var terminusPoint: root._dynamicGroupTerminusPoint(modelData)
            readonly property var portKeys: modelData && modelData.port_keys ? modelData.port_keys : []
            readonly property bool actionActive: hovered || activeFocus || down
            readonly property bool revealActive: root._dynamicGroupControlRevealActive(modelData)
            visible: root._dynamicPortInlineControlsVisible()
                && Boolean(modelData && modelData.can_insert)
                && (direction === "in" || direction === "out")
                && groupId.length > 0
                && (revealActive || actionActive)
            x: Number(terminusPoint.x || 0) - width * 0.5
            y: Number(terminusPoint.y || 0) - height * 0.5
            width: root.dynamicPortTargetDiameter
            height: width
            host: root.host
            property color actionFillColor: "#55D65B"
            text: ""
            foregroundColor: "#FFFFFF"
            accentColor: "#FFFFFF"
            tooltipText: direction === "in" ? "Add input" : "Add output"
            focusPolicy: Qt.TabFocus
            Accessible.name: tooltipText
            background: Item {
                Rectangle {
                    objectName: "graphNodeDynamicPortAddCircle"
                    anchors.centerIn: parent
                    width: dynamicPortAddButton.actionActive ? 14 : 6
                    height: width
                    radius: width * 0.5
                    color: dynamicPortAddButton.down
                        ? Qt.darker(dynamicPortAddButton.actionFillColor, 1.15)
                        : (dynamicPortAddButton.hovered
                            ? Qt.lighter(dynamicPortAddButton.actionFillColor, 1.10)
                            : dynamicPortAddButton.actionFillColor)
                    border.width: dynamicPortAddButton.actionActive
                        ? (dynamicPortAddButton.activeFocus ? 2 : 1)
                        : 0
                    border.color: dynamicPortAddButton.activeFocus
                        ? "#FFFFFF"
                        : Qt.rgba(
                            1.0,
                            1.0,
                            1.0,
                            dynamicPortAddButton.hovered ? 0.82 : 0.34
                        )
                    Text {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -1
                        text: "+"
                        color: "#FFFFFF"
                        font.pixelSize: 12
                        opacity: dynamicPortAddButton.actionActive ? 1.0 : 0.0
                    }
                }
            }
            onControlStarted: {
                if (root.host && root.host.nodeData)
                    root.host.surfaceControlInteractionStarted(root.host.nodeData.node_id);
            }
            onClicked: root._insertDynamicPort(groupId, portKeys.length)
        }
    }

    GraphNodePortContextMenu {
        id: portContextMenu
        portsLayer: root
    }
}
