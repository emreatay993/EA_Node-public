import QtQuick 2.15
import ".." as GraphShared
import "../../common" as Common
import "../surface_controls" as SurfaceControls

// Compact Trigger gate: a single centered click button inside the shared pill
// chrome; the blocked input enters on the left edge and the held output leaves
// on the right. Shared host chrome owns the pill, shadow, border, and port
// notches. The click routes through host.triggerNodeRequested to the
// RunController capture/publication path.
GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphTriggerSurface"

    readonly property string nodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string nodeTitle: host && host.nodeData ? String(host.nodeData.title || "") : ""
    // The button label follows the node rename (benchmark hint) and falls back
    // to the type name for untitled nodes.
    readonly property string buttonLabel: nodeTitle.length > 0 ? nodeTitle : "Trigger"
    readonly property real portGutterReserve: host
        ? Math.max(10.0, Number(host.surfaceMetrics.body_right_margin || 0.0))
        : 10.0
    readonly property var embeddedInteractiveRects: triggerButton.embeddedInteractiveRects || []
    readonly property var surfaceActions: []
    implicitHeight: host ? Number(host.surfaceMetrics.default_height || 0) : 0

    SurfaceControls.GraphSurfaceButton {
        id: triggerButton
        objectName: "graphTriggerNodeControl"
        anchors.centerIn: parent
        width: Math.max(68.0, implicitWidth)
        controlHeight: 24
        host: surface.host
        enabled: !!surface.host && !surface.host.graphReadOnly
        text: surface.buttonLabel
        accentColor: surface.host ? surface.host.selectedOutlineColor : "#4DA8DA"
        tooltipText: surface.host ? surface.host.nodeHelpTooltipText : ""
        tooltipTextFormat: Text.RichText
        tooltipScreenStablePlacement: surface.host ? surface.host.nodeHelpTooltipPlacement : "below"
        tooltipAnchorScale: surface.host ? surface.host.nodeHelpTooltipAnchorScale : 0.0
        onClicked: {
            if (surface.host && surface.nodeId.length)
                surface.host.triggerNodeRequested(surface.nodeId);
        }
    }

    // Node-help tooltip for the pill body outside the button; the button's
    // built-in tooltip carries the same text, so exactly one is active.
    HoverHandler {
        id: pillHelpHover
        enabled: !!surface.host && surface.host.nodeHelpTooltipText.length > 0
    }

    Common.ManagedToolTip {
        objectName: "graphTriggerHelpToolTip"
        policyBridge: surface.host ? surface.host.nodeHelpTooltipPolicyBridge : null
        category: "general"
        active: pillHelpHover.hovered && !triggerButton.hovered
        text: surface.host ? surface.host.nodeHelpTooltipText : ""
        textFormat: Text.RichText
        delay: 400
        screenStablePositioning: true
        screenStablePlacement: surface.host ? surface.host.nodeHelpTooltipPlacement : "below"
        anchorScale: surface.host ? surface.host.nodeHelpTooltipAnchorScale : 1.0
        screenGap: 8
    }
}
