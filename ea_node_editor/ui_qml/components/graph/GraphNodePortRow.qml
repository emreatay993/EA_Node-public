// Purpose: Render one shared input or output graph-node port row.
// Map: feature_routes/port_availability_and_default_values.md
// Tests: tests/qml_quick/tst_graph_node_host.qml

import QtQuick 2.15
import "../common" as Common
import "../common/TooltipPolicy.js" as TooltipPolicy
import "surface_controls" as SurfaceControls
import "surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: row
    required property Item portsLayer
    required property var modelData
    required property int index
    property string direction: "in"
    property Item defaultPropertyItem: null
    readonly property bool isInput: direction === "in"
    readonly property Item host: portsLayer ? portsLayer.host : null
    readonly property var portData: modelData || ({})
    property int rowIndex: isFinite(Number(portData && portData.layout_row))
        ? Number(portData.layout_row)
        : index
    property string propertyKey: portsLayer ? portsLayer._portKey(portData) : ""
    readonly property bool handleVisible: !isInput
        || (portData && portData.handle_visible !== undefined
            ? Boolean(portData.handle_visible)
            : true)
    readonly property bool labelOwnedBySettings: isInput
        && String(portData && portData.settings_property_key || "").length > 0
    readonly property string interactionDirection: portsLayer
        ? portsLayer._interactionDirection(portData, direction)
        : direction
    readonly property bool placeholderLockedState: portsLayer
        ? portsLayer.hostLockedPlaceholder
        : false
    readonly property bool inactiveState: portsLayer
        ? portsLayer._portInactive(portData)
        : false
    readonly property bool lockedState: placeholderLockedState
        || (!isInput && inactiveState)
    readonly property var defaultProperty: isInput && portData && portData.default_property
        ? portData.default_property
        : null
    readonly property bool defaultEditorVisible: isInput
        && !placeholderLockedState
        && defaultProperty !== null
        && portsLayer
        && portsLayer._defaultEditorSupported(defaultProperty)
    readonly property var portPoint: host
        ? host.localPortPointForPort(direction, rowIndex, portData)
        : ({"x": 0.0, "y": 0.0})
    readonly property var portLayoutPoint: host
        ? host.localPortLayoutPointForPort(direction, rowIndex, portData)
        : portPoint
    readonly property real dotDiameter: portDot.width
    readonly property real metricRowHeight: portsLayer
        ? portsLayer._resolvedPortRowHeight()
        : 18
    readonly property alias portDotItem: portDot
    readonly property alias portMouseAreaItem: portMouse
    readonly property alias labelContainerItem: labelContainer
    readonly property alias labelEditorItem: labelEditor
    readonly property alias removeButtonItem: removeButton

    objectName: isInput ? "graphNodeInputPortRow" : "graphNodeOutputPortRow"
    x: 0
    y: isInput
        ? portLayoutPoint.y - (portsLayer
            ? portsLayer._defaultEditorAnchorOffset(defaultProperty, height)
            : 0)
        : portPoint.y - height * 0.5
    width: host ? host.width : 0
    height: Math.max(
        dotDiameter,
        metricRowHeight,
        defaultEditorVisible && portsLayer
            ? portsLayer._defaultEditorHeight(defaultProperty)
            : 0
    )
    visible: handleVisible

    function currentEmbeddedInteractiveRects() {
        if (!visible)
            return [];
        var lists = [];
        if (isInput && defaultPropertyItem
                && defaultPropertyItem.visible && defaultPropertyItem.enabled) {
            var rects = defaultPropertyItem.embeddedInteractiveRects || [];
            var translated = [];
            for (var rectIndex = 0; rectIndex < rects.length; ++rectIndex) {
                var rect = rects[rectIndex];
                translated.push({
                    "x": row.x + defaultPropertyItem.x + Number(rect.x || 0),
                    "y": row.y + defaultPropertyItem.y + Number(rect.y || 0),
                    "width": Number(rect.width || 0),
                    "height": Number(rect.height || 0)
                });
            }
            lists.push(translated);
        }
        if (removeButton.visible)
            lists.push(removeButton.embeddedInteractiveRects);
        if (labelEditor.visible)
            lists.push(labelEditor.embeddedInteractiveRects);
        return SurfaceControlGeometry.combineRectLists(lists);
    }

    function refocusLabelEditor() {
        if (labelContainer.isEditing)
            labelEditor.forceActiveFocus();
    }

    function paintPadlock(canvas, padlockLocked, placeholderLocked) {
        var ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!padlockLocked || canvas.width <= 0 || canvas.height <= 0)
            return;
        var accentStrokeAlpha = padlockLocked ? 1.0 : 0.68;
        var accentFillAlpha = padlockLocked ? 0.38 : 0.18;
        var outlineAlpha = padlockLocked ? 0.92 : 0.58;
        var outlineStroke = placeholderLocked
            ? Qt.rgba(0.0, 0.0, 0.0, 0.0)
            : Qt.rgba(0.10, 0.07, 0.03, outlineAlpha);
        var accentStroke = placeholderLocked
            ? Qt.rgba(0.54, 0.58, 0.64, accentStrokeAlpha)
            : Qt.rgba(1.0, 0.82, 0.34, accentStrokeAlpha);
        var accentFill = placeholderLocked
            ? Qt.rgba(0.16, 0.18, 0.21, 1.0)
            : Qt.rgba(1.0, 0.88, 0.52, accentFillAlpha);

        function drawShackle(strokeStyle, lineWidth) {
            ctx.beginPath();
            ctx.lineWidth = lineWidth;
            ctx.strokeStyle = strokeStyle;
            ctx.arc(canvas.width * 0.5, 4.0, 2.6, Math.PI, 0, false);
            ctx.stroke();
        }

        var bodyX = Math.round((canvas.width - 8) * 0.5);
        var bodyY = 5.0;
        var bodyWidth = 8.0;
        var bodyHeight = 6.0;
        var radius = 1.8;
        function drawBody(strokeStyle, fillStyle, lineWidth) {
            ctx.beginPath();
            ctx.lineWidth = lineWidth;
            ctx.strokeStyle = strokeStyle;
            ctx.fillStyle = fillStyle;
            ctx.moveTo(bodyX + radius, bodyY);
            ctx.lineTo(bodyX + bodyWidth - radius, bodyY);
            ctx.quadraticCurveTo(bodyX + bodyWidth, bodyY, bodyX + bodyWidth, bodyY + radius);
            ctx.lineTo(bodyX + bodyWidth, bodyY + bodyHeight - radius);
            ctx.quadraticCurveTo(
                bodyX + bodyWidth,
                bodyY + bodyHeight,
                bodyX + bodyWidth - radius,
                bodyY + bodyHeight
            );
            ctx.lineTo(bodyX + radius, bodyY + bodyHeight);
            ctx.quadraticCurveTo(bodyX, bodyY + bodyHeight, bodyX, bodyY + bodyHeight - radius);
            ctx.lineTo(bodyX, bodyY + radius);
            ctx.quadraticCurveTo(bodyX, bodyY, bodyX + radius, bodyY);
            ctx.fill();
            ctx.stroke();
        }

        drawShackle(outlineStroke, 2.6);
        drawBody(outlineStroke, Qt.rgba(0.0, 0.0, 0.0, 0.0), 2.6);
        drawShackle(accentStroke, 1.2);
        drawBody(accentStroke, accentFill, 1.2);
    }

    Image {
        objectName: row.isInput ? "graphNodeInputPortNotch" : "graphNodeOutputPortNotch"
        property string propertyKey: row.propertyKey
        readonly property bool nodeFacingEdgeOnRight: row.isInput
        readonly property color notchFillColor: row.portsLayer.notchColor
        readonly property color notchStrokeColor: row.portsLayer.notchOutlineColor
        readonly property real notchStrokeWidth: row.portsLayer.notchOutlineWidth
        visible: row.portsLayer.notchedPortsEffective
        width: row.portsLayer.notchDiameter * 0.5
        height: row.portsLayer.notchDiameter
        x: row.isInput ? row.portPoint.x : row.portPoint.x - width
        y: row.isInput
            ? row.portPoint.y - row.y - height * 0.5
            : (row.height - height) * 0.5
        sourceSize: row.portsLayer.notchSourceSize
        source: row.portsLayer.notchSvgSource
        mirror: !row.isInput
        cache: true
        asynchronous: false
        smooth: true
        mipmap: false
        fillMode: Image.Stretch
        z: -1
    }

    Rectangle {
        id: portDot
        objectName: row.isInput ? "graphNodeInputPortDot" : "graphNodeOutputPortDot"
        property string propertyKey: row.propertyKey
        readonly property string interactionDirection: row.interactionDirection
        property bool inactiveState: row.inactiveState
        property bool lockedState: row.lockedState
        property bool placeholderLockedState: row.placeholderLockedState
        property bool interactionBlockedState: inactiveState || lockedState
        property bool hoveredState: !interactionBlockedState && row.host
            ? row.host.isHoveredPort(row.interactionDirection, row.portData.key)
            : false
        property bool pendingState: !interactionBlockedState && row.host
            ? row.host.isPendingPort(row.interactionDirection, row.portData.key)
            : false
        property bool dragSourceState: !interactionBlockedState && row.host
            ? row.host.isDragSourcePort(row.interactionDirection, row.portData.key)
            : false
        property bool compatibleTargetState: !interactionBlockedState && row.host
            ? row.host.isCompatibleTargetPort(row.portData)
            : false
        property bool selectedState: row.host
            ? row.host.usesCardinalNeutralFlowHandles && row.host.isSelected
            : false
        property bool attentionState: hoveredState || pendingState || dragSourceState
        property bool interactiveState: !interactionBlockedState
            && (attentionState || compatibleTargetState || selectedState)
        property bool revealState: row.portsLayer._flowEdgePortRevealActive(
            row.portData,
            attentionState || compatibleTargetState,
            selectedState
        )
        property bool connectedState: row.host ? row.host.isConnectedPort(row.portData) : false
        property color portColor: row.host ? row.host.portTypeAccentColor(row.portData) : "#7AA8FF"
        property real lockedDiameter: placeholderLockedState ? 18 : 12
        property real restDiameter: row.host && row.host.usesCardinalNeutralFlowHandles
            ? (connectedState
                ? row.host.flowchartConnectedPortDiameter
                : row.host.flowchartRestPortDiameter)
            : row.portsLayer.standardRestPortDiameter
        property real activeDiameter: row.host && row.host.usesCardinalNeutralFlowHandles
            ? (attentionState
                ? row.host.flowchartInteractivePortDiameter
                : row.host.flowchartSelectedPortDiameter)
            : 14
        property real ringDiameter: row.host && row.host.usesCardinalNeutralFlowHandles
            ? row.host.flowchartInteractiveRingDiameter
            : ((attentionState || compatibleTargetState) ? 18 : 12)
        x: row.portPoint.x - width * 0.5
        y: row.portPoint.y - row.y - height * 0.5
        width: lockedState ? lockedDiameter : (interactiveState ? activeDiameter : restDiameter)
        height: width
        radius: placeholderLockedState ? width * 0.5 : (lockedState ? 0 : width * 0.5)
        opacity: lockedState
            ? 1.0
            : (revealState
                ? (row.isInput
                    ? (inactiveState ? 0.46 : (interactionBlockedState ? 0.72 : 1.0))
                    : 1.0)
                : 0.0)
        color: placeholderLockedState
            ? "#2a2d34"
            : (lockedState
                ? "transparent"
                : (row.host && row.host.usesCardinalNeutralFlowHandles
                    ? (attentionState
                        ? row.host.portInteractiveFillColor
                        : ((selectedState || connectedState)
                            ? row.host.flowchartConnectedPortFillColor
                            : "transparent"))
                    : (attentionState
                        ? (row.host ? row.host.portInteractiveFillColor : "#FFDA6B")
                        : (row.host
                            ? row.host.portFlowFillColor(row.portData)
                            : (connectedState ? portColor : "transparent")))))
        border.width: placeholderLockedState
            ? 1.5
            : (lockedState
                ? 0
                : (row.host && row.host.usesCardinalNeutralFlowHandles
                    ? (attentionState ? 1.8 : 1.1)
                    : (interactiveState ? 2 : 1.6)))
        border.color: placeholderLockedState
            ? "#5a606c"
            : (lockedState
                ? "transparent"
                : (attentionState
                    ? (row.host ? row.host.portInteractiveBorderColor : portColor)
                    : (row.host && row.host.usesCardinalNeutralFlowHandles
                        ? (selectedState ? row.host.selectedOutlineColor : portColor)
                        : row.portsLayer._portFlowOutlineColor(row.portData))))

        Rectangle {
            objectName: row.isInput ? "graphNodeInputPortRing" : "graphNodeOutputPortRing"
            property string propertyKey: row.propertyKey
            anchors.centerIn: parent
            visible: (!row.host || !row.host.usesCardinalNeutralFlowHandles
                || portDot.attentionState || portDot.compatibleTargetState)
                && !portDot.lockedState
            width: portDot.ringDiameter
            height: portDot.ringDiameter
            radius: width * 0.5
            z: -1
            color: portDot.attentionState && row.host
                ? row.host.portInteractiveRingFillColor
                : "transparent"
            border.width: (portDot.attentionState || portDot.compatibleTargetState) ? 1 : 0
            border.color: portDot.attentionState && row.host
                ? row.host.portInteractiveRingBorderColor
                : (portDot.compatibleTargetState && row.host
                    ? row.portsLayer._portFlowOutlineColor(row.portData)
                    : "transparent")
        }

        MouseArea {
            id: portMouse
            objectName: row.isInput
                ? "graphNodeInputPortMouseArea"
                : "graphNodeOutputPortMouseArea"
            property string propertyKey: row.propertyKey
            enabled: row.host ? !row.host.surfaceInteractionLocked : false
            property real pressStartX: 0
            property real pressStartY: 0
            property bool movedState: false
            property bool hoverActive: false
            // Slight overlap hands hover from the port to its authoring controls.
            x: !row.isInput && removeButton.visible
                ? removeButton.x + removeButton.width
                    - row.portsLayer.dynamicPortHoverHandoffOverlap - portDot.x
                : -9
            y: -9
            width: removeButton.visible && row.isInput
                ? removeButton.x + row.portsLayer.dynamicPortHoverHandoffOverlap
                    - portDot.x - portMouse.x
                : parent.width + (removeButton.visible ? 9 : 18)
            height: parent.height + (row.portsLayer._dynamicPortInlineControlsVisible()
                    && row.portsLayer._dynamicPortIsGroupTerminus(row.portData)
                ? Math.max(
                    0,
                    row.portPoint.y - row.y
                        + row.portsLayer.dynamicPortControlCenterInterval
                        - row.portsLayer.dynamicPortTargetDiameter * 0.5
                        + row.portsLayer.dynamicPortHoverHandoffOverlap
                        - portDot.y - portMouse.y - parent.height
                )
                : 18)
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            hoverEnabled: true
            preventStealing: true
            cursorShape: portDot.interactionBlockedState
                ? Qt.ForbiddenCursor
                : Qt.PointingHandCursor
            property bool tooltipOnlyPortLabelActive: row.host
                ? row.host._tooltipOnlyPortLabelsActive
                : false
            property bool infoTooltipsEnabled: TooltipPolicy.categoryEnabled(
                row.portsLayer.tooltipPolicyBridge,
                "general"
            )
            property bool inactiveTooltipsEnabled: TooltipPolicy.categoryEnabled(
                row.portsLayer.tooltipPolicyBridge,
                "inactive"
            )
            property string portLabelTooltipText: row.portsLayer._portLabelText(row.portData)
            property string portHelpTooltipText: row.portsLayer._portHelpTooltipText(row.portData)
            property string inactiveTooltipText: row.portsLayer._portInactiveTooltipText(row.portData)
            property string accessiblePortText: row.portsLayer._portAccessibleText(row.portData)
            Accessible.name: accessiblePortText
            Accessible.description: accessiblePortText
            property bool effectiveHoverActive: row.isInput ? containsMouse : hoverActive
            property bool tooltipVisible: TooltipPolicy.tooltipVisible(
                row.portsLayer.tooltipPolicyBridge,
                "general",
                effectiveHoverActive && portHelpTooltipText.length > 0
            )
            property bool inactiveTooltipVisible: TooltipPolicy.tooltipVisible(
                row.portsLayer.tooltipPolicyBridge,
                "inactive",
                effectiveHoverActive
                    && (row.isInput ? portDot.inactiveState : portDot.lockedState)
                    && inactiveTooltipText.length > 0
            )
            property string activeTooltipCategory: inactiveTooltipVisible
                ? "inactive"
                : "general"

            Common.ManagedToolTip {
                policyBridge: row.portsLayer.tooltipPolicyBridge
                category: row.isInput ? portMouse.activeTooltipCategory : "general"
                active: row.isInput
                    ? (portMouse.tooltipVisible || portMouse.inactiveTooltipVisible)
                    : (portMouse.tooltipVisible && !portMouse.inactiveTooltipVisible)
                text: row.isInput && portMouse.inactiveTooltipVisible
                    ? portMouse.inactiveTooltipText
                    : portMouse.portHelpTooltipText
                textFormat: row.isInput && portMouse.inactiveTooltipVisible
                    ? Text.PlainText
                    : Text.RichText
                delay: 400
                screenStablePositioning: true
                screenStablePlacement: row.portsLayer.nodeTooltipPlacement
                anchorScale: row.portsLayer.nodeTooltipAnchorScale
                screenGap: 8
            }

            function updateHoverState(localX, localY) {
                if (row.isInput)
                    return;
                var nextHover = !(row.host && row.host._isResizeHandlePoint(localX, localY));
                if (hoverActive === nextHover)
                    return;
                hoverActive = nextHover;
                if (!row.host || !row.host.nodeData)
                    return;
                var pos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                row.host.portHoverChanged(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    pos.x,
                    pos.y,
                    nextHover
                );
            }

            onPressed: function(mouse) {
                if (!row.host || !row.host.nodeData)
                    return;
                if (mouse.button === Qt.RightButton) {
                    row.portsLayer._openPortContext(row.portData, portMouse, mouse.x, mouse.y);
                    mouse.accepted = true;
                    return;
                }
                if (mouse.button !== Qt.LeftButton || portDot.interactionBlockedState)
                    return;
                if (!row.isInput) {
                    var localPoint = portMouse.mapToItem(row.host, mouse.x, mouse.y);
                    if (row.host._isResizeHandlePoint(localPoint.x, localPoint.y)) {
                        mouse.accepted = false;
                        return;
                    }
                }
                pressStartX = mouse.x;
                pressStartY = mouse.y;
                movedState = false;
                var scenePos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                var pointerPos = row.host._pointerInCanvas(portMouse, mouse);
                row.host.portDragStarted(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    scenePos.x,
                    scenePos.y,
                    pointerPos.x,
                    pointerPos.y,
                    mouse.modifiers
                );
                mouse.accepted = true;
            }

            onPositionChanged: function(mouse) {
                if (!row.host)
                    return;
                if (!row.isInput) {
                    var localPoint = portMouse.mapToItem(row.host, mouse.x, mouse.y);
                    updateHoverState(localPoint.x, localPoint.y);
                }
                if (!row.host.nodeData || !(mouse.buttons & Qt.LeftButton)
                        || portDot.interactionBlockedState)
                    return;
                if (Math.abs(mouse.x - pressStartX) >= row.host._portDragThreshold
                        || Math.abs(mouse.y - pressStartY) >= row.host._portDragThreshold) {
                    movedState = true;
                }
                var scenePos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                var pointerPos = row.host._pointerInCanvas(portMouse, mouse);
                row.host.portDragMoved(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    scenePos.x,
                    scenePos.y,
                    pointerPos.x,
                    pointerPos.y,
                    movedState,
                    mouse.modifiers
                );
            }

            onReleased: function(mouse) {
                if (mouse.button !== Qt.LeftButton || !row.host || !row.host.nodeData)
                    return;
                if (portDot.interactionBlockedState) {
                    movedState = false;
                    return;
                }
                var scenePos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                var pointerPos = row.host._pointerInCanvas(portMouse, mouse);
                row.host.portDragFinished(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    scenePos.x,
                    scenePos.y,
                    pointerPos.x,
                    pointerPos.y,
                    movedState,
                    mouse.modifiers
                );
                if (!movedState) {
                    row.host.portClicked(
                        row.host.nodeData.node_id,
                        row.portData.key,
                        portDot.interactionDirection,
                        scenePos.x,
                        scenePos.y,
                        mouse.modifiers
                    );
                }
                movedState = false;
            }

            onCanceled: {
                if (!row.host || !row.host.nodeData)
                    return;
                row.host.portDragCanceled(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection
                );
                movedState = false;
            }

            onEntered: {
                if (!row.host || portDot.interactionBlockedState)
                    return;
                if (!row.isInput) {
                    var localPoint = portMouse.mapToItem(row.host, portMouse.mouseX, portMouse.mouseY);
                    updateHoverState(localPoint.x, localPoint.y);
                    return;
                }
                if (!row.host.nodeData)
                    return;
                var pos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                row.host.portHoverChanged(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    pos.x,
                    pos.y,
                    true
                );
            }

            onExited: {
                if (!row.host || !row.host.nodeData)
                    return;
                if (!row.isInput) {
                    if (!hoverActive)
                        return;
                    hoverActive = false;
                } else if (portDot.interactionBlockedState) {
                    return;
                }
                var pos = row.host.portScenePosForPort(row.direction, row.rowIndex, row.portData);
                row.host.portHoverChanged(
                    row.host.nodeData.node_id,
                    row.portData.key,
                    portDot.interactionDirection,
                    pos.x,
                    pos.y,
                    false
                );
            }
        }
    }

    SurfaceControls.GraphSurfaceButton {
        id: removeButton
        objectName: "graphNodeDynamicPortRemove_" + row.propertyKey
        property string propertyKey: row.propertyKey
        property color actionFillColor: "#FF5449"
        readonly property bool actionActive: hovered || activeFocus || down
        readonly property var dynamicGroup: row.portsLayer._dynamicPortGroupForPort(row.portData)
        readonly property bool revealActive: row.portsLayer._dynamicPortControlRevealActive(row.portData)
        visible: row.portsLayer._dynamicPortInlineControlsVisible()
            && row.portsLayer._dynamicPortCanRemove(row.portData)
            && (revealActive || actionActive)
        x: Number(row.portPoint.x || 0)
            + (row.isInput ? 1 : -1) * row.portsLayer.dynamicPortRemoveCenterInterval
            - width * 0.5
        anchors.verticalCenter: parent.verticalCenter
        width: row.portsLayer.dynamicPortRemoveTargetWidth
        height: row.portsLayer.dynamicPortTargetDiameter
        host: row.host
        text: ""
        foregroundColor: "#FFFFFF"
        accentColor: "#FFFFFF"
        tooltipText: "Remove " + row.direction + "put"
        focusPolicy: Qt.TabFocus
        Accessible.name: tooltipText
        background: Item {
            Rectangle {
                objectName: "graphNodeDynamicPortRemoveCircle"
                anchors.centerIn: parent
                width: removeButton.actionActive ? 14 : 6
                height: width
                radius: width * 0.5
                color: removeButton.down
                    ? Qt.darker(removeButton.actionFillColor, 1.15)
                    : (removeButton.hovered
                        ? Qt.lighter(removeButton.actionFillColor, 1.10)
                        : removeButton.actionFillColor)
                border.width: removeButton.actionActive
                    ? (removeButton.activeFocus ? 2 : 1)
                    : 0
                border.color: removeButton.activeFocus
                    ? "#FFFFFF"
                    : Qt.rgba(1.0, 1.0, 1.0, removeButton.hovered ? 0.82 : 0.34)
                Text {
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: -1
                    text: "\u2212"
                    color: "#FFFFFF"
                    font.pixelSize: 12
                    opacity: removeButton.actionActive ? 1.0 : 0.0
                }
            }
        }
        onControlStarted: {
            if (row.host && row.host.nodeData)
                row.host.surfaceControlInteractionStarted(row.host.nodeData.node_id);
        }
        onClicked: {
            if (dynamicGroup)
                row.portsLayer._removeDynamicPort(dynamicGroup.id, row.propertyKey);
        }
    }

    Item {
        id: labelContainer
        property string propertyKey: row.propertyKey
        readonly property bool isEditing: row.portsLayer.editingPortKey === row.portData.key
            && row.portsLayer.editingPortDirection === row.direction
        readonly property bool isEditable: row.portsLayer._isEditablePort(row.portData)
            && (!row.isInput || !row.inactiveState)
            && !row.portsLayer.hostLockedPlaceholder
            && (row.host ? row.host._portLabelsVisible : true)
        readonly property bool lockedState: row.lockedState
        readonly property bool labelTextVisible: row.isInput
            ? (!row.portsLayer.hostLockedPlaceholder
                && !row.defaultEditorVisible
                && (row.host ? (row.host._portLabelsVisible || lockedState) : true))
            : !isEditing
        readonly property bool standardColumnsActive: row.host
            ? row.host._usesStandardPortLabelColumns
            : false
        readonly property real inputLabelX: removeButton.visible
            ? removeButton.x + removeButton.width
            : Math.max(0, portDot.x + portDot.width + (row.host ? row.host._portLabelGap : 6))
        readonly property real outputLabelRightEdge: removeButton.visible
            ? removeButton.x
            : portDot.x - (row.host ? row.host._portLabelGap : 6)
        readonly property real rawAvailableWidth: row.isInput
            ? Math.max(0, (row.host ? row.host.width : 0) - inputLabelX - 4)
            : Math.max(0, outputLabelRightEdge - 4)
        readonly property real standardAvailableWidth: standardColumnsActive && row.host
            ? (row.isInput
                ? Math.max(
                    0,
                    Math.min(
                        row.host._standardLeftLabelWidth,
                        (row.host.width - row.host._standardPortGutter - row.host._standardCenterGap)
                            - inputLabelX
                            - row.host._standardRightLabelWidth
                    )
                )
                : Math.max(
                    0,
                    Math.min(
                        row.host._standardRightLabelWidth,
                        outputLabelRightEdge
                            - (row.host._standardPortGutter
                                + row.host._standardLeftLabelWidth
                                + row.host._standardCenterGap)
                    )
                ))
            : 0.0
        readonly property real availableWidth: standardColumnsActive
            ? standardAvailableWidth
            : rawAvailableWidth
        visible: !row.portsLayer.hostLockedPlaceholder
            && !Boolean(row.portData.settings_group_transition_only)
            && (!row.isInput || !row.labelOwnedBySettings)
            && (row.host ? (row.host._portLabelsVisible || lockedState) : true)
        anchors.verticalCenter: parent.verticalCenter
        x: row.isInput
            ? inputLabelX
            : (standardColumnsActive && row.host
                ? Math.max(0, outputLabelRightEdge - availableWidth)
                : 4)
        width: availableWidth
        height: parent.height

        Text {
            id: labelText
            objectName: row.isInput ? "graphNodeInputPortLabel" : "graphNodeOutputPortLabel"
            property string propertyKey: labelContainer.propertyKey
            property int effectiveRenderType: renderType
            property string helpTooltipCategory: "general"
            property string helpTooltipText: row.portsLayer._portHelpTooltipText(row.portData)
            property bool helpTooltipHovered: labelMouse.containsMouse
            visible: labelContainer.labelTextVisible && !labelContainer.isEditing
            anchors.verticalCenter: parent.verticalCenter
            x: row.isInput ? 0 : Math.max(0, parent.width - width)
            width: row.host
                ? row.host.portLabelWidth(implicitWidth, labelContainer.availableWidth)
                : 0
            text: row.portsLayer._portDisplayText(row.portData)
            color: row.portsLayer._portDisplayColor(row.portData)
            font.pixelSize: row.portsLayer._portDisplayPixelSize(row.portData)
            font.weight: row.portsLayer._portDisplayFontWeight(row.portData)
            horizontalAlignment: row.isInput ? Text.AlignLeft : Text.AlignRight
            elide: row.isInput ? Text.ElideRight : Text.ElideLeft
            renderType: row.host ? row.host.nodeTextRenderType : Text.CurveRendering
            opacity: row.isInput && row.inactiveState
                ? 0.52
                : (labelContainer.lockedState ? 0.58 : 1.0)

            Rectangle {
                visible: labelMouse.containsMouse && labelContainer.isEditable
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: row.host ? row.host.portLabelColor : "#d0d5de"
                opacity: 0.5
            }

            Common.ManagedToolTip {
                objectName: row.isInput
                    ? "graphNodeInputPortHelpToolTip"
                    : "graphNodeOutputPortHelpToolTip"
                policyBridge: row.portsLayer.tooltipPolicyBridge
                category: labelText.helpTooltipCategory
                active: labelMouse.containsMouse
                text: labelText.helpTooltipText
                textFormat: Text.RichText
                delay: 400
                screenStablePositioning: true
                screenStablePlacement: row.portsLayer.nodeTooltipPlacement
                anchorScale: row.portsLayer.nodeTooltipAnchorScale
                screenGap: 8
            }
        }

        MouseArea {
            id: labelMouse
            anchors.fill: labelText
            visible: labelContainer.labelTextVisible && !labelContainer.isEditing
                && !row.portsLayer.hostLockedPlaceholder
            hoverEnabled: true
            cursorShape: containsMouse && labelContainer.isEditable
                ? Qt.IBeamCursor
                : Qt.ArrowCursor
            acceptedButtons: labelContainer.isEditable ? Qt.LeftButton : Qt.NoButton
            onClicked: {
                if (labelContainer.isEditable)
                    row.portsLayer.beginPortLabelEdit(row.portData.key, row.direction);
            }
        }

        SurfaceControls.GraphSurfaceTextField {
            id: labelEditor
            objectName: row.isInput
                ? "graphNodeInputPortLabelEditor"
                : "graphNodeOutputPortLabelEditor"
            property string propertyKey: labelContainer.propertyKey
            visible: labelContainer.isEditing
            host: row.host
            x: row.isInput ? labelText.x : 0
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(1, labelContainer.availableWidth - (row.isInput ? labelText.x : 0))
            height: parent.height
            font.pixelSize: row.portsLayer._portDisplayPixelSize(row.portData)
            font.weight: row.portsLayer._portDisplayFontWeight(row.portData)
            textColor: row.portsLayer._portDisplayColor(row.portData)
            fillColor: "transparent"
            borderColor: "transparent"
            focusBorderColor: "transparent"
            topPadding: 0
            bottomPadding: 0
            leftPadding: 0
            rightPadding: 0
            horizontalAlignment: row.isInput ? TextInput.AlignLeft : TextInput.AlignRight
            verticalAlignment: TextInput.AlignVCenter

            onVisibleChanged: {
                if (visible) {
                    text = row.portData.label || row.portData.key;
                    forceActiveFocus();
                    cursorPosition = text.length;
                    deselect();
                }
            }
            onAccepted: row.portsLayer.commitPortLabelEdit(row.portData.key, text)
            onTextEdited: row.portsLayer.portLabelEditError = ""
            onActiveFocusChanged: {
                if (!activeFocus && labelContainer.isEditing)
                    row.portsLayer.commitPortLabelEdit(row.portData.key, text);
            }
            Keys.onEscapePressed: row.portsLayer.cancelPortLabelEdit()
            onControlStarted: {
                if (row.host && row.host.nodeData)
                    row.host.surfaceControlInteractionStarted(row.host.nodeData.node_id);
            }

            Common.ManagedToolTip {
                policyBridge: row.portsLayer.tooltipPolicyBridge
                category: "general"
                active: labelEditor.visible && row.portsLayer.portLabelEditError.length > 0
                text: row.portsLayer.portLabelEditError
                delay: 0
                screenStablePositioning: true
                screenStablePlacement: "below"
                anchorScale: row.portsLayer.nodeTooltipAnchorScale
                screenGap: 6
            }
        }
    }
}
