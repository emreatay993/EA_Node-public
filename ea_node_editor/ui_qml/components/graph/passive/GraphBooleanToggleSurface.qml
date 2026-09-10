import QtQuick 2.15
import ".." as GraphShared
import "../../common" as Common
import "../surface_controls" as SurfaceControls

// Compact Boolean source: [name][toggle] with one output centered on the
// right edge. Shared host chrome owns the pill, shadow, border, and port notch.
GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphBooleanToggleSurface"

    readonly property string nodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string nodeTitle: host && host.nodeData ? String(host.nodeData.title || "") : ""
    readonly property bool currentValue: propBool("value", false)
    readonly property real pillRadius: height * 0.5
    readonly property real portGutterReserve: host
        ? Math.max(10.0, Number(host.surfaceMetrics.body_right_margin || 0.0))
        : 10.0
    readonly property color pillBorderColor: host ? host.outlineColor : "#4a4f5a"
    readonly property color nameSectionColor: Qt.alpha(pillBorderColor, 0.12)
    readonly property color dividerColor: Qt.alpha(pillBorderColor, 0.55)
    readonly property color nameTextColor: host ? host.headerTextColor : "#f0f2f5"
    readonly property var embeddedInteractiveRects: toggleControl.embeddedInteractiveRects || []
    readonly property var surfaceActions: []
    implicitHeight: host ? Number(host.surfaceMetrics.default_height || 0) : 0

    Item {
        id: nameSection
        objectName: "graphBooleanToggleNameSection"
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.topMargin: 1
        anchors.bottomMargin: 1
        anchors.leftMargin: 1
        width: Math.max(nameLabel.implicitWidth + 26.0, 82.0)

        Item {
            id: nameSectionFillClip
            objectName: "graphBooleanToggleNameSectionFillClip"
            anchors.fill: parent
            clip: true

            Rectangle {
                objectName: "graphBooleanToggleNameSectionFill"
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                width: parent.width + Math.max(0.0, surface.pillRadius - 1.0)
                radius: Math.max(0.0, surface.pillRadius - 1.0)
                color: surface.nameSectionColor
                antialiasing: true
            }
        }

        Text {
            id: nameLabel
            objectName: "graphBooleanToggleNameLabel"
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 16.0
            anchors.rightMargin: 8.0
            text: surface.nodeTitle
            elide: Text.ElideNone
            color: surface.nameTextColor
            font.pixelSize: host && host.graphSharedTypography
                ? host.graphSharedTypography.nodeTitlePixelSize
                : 12
            font.weight: host && host.graphSharedTypography
                ? host.graphSharedTypography.nodeTitleFontWeight
                : Font.Bold
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering

            HoverHandler {
                id: nameHelpHover
                enabled: !!surface.host && surface.host.nodeHelpTooltipText.length > 0
            }

            Common.ManagedToolTip {
                objectName: "graphBooleanToggleHelpToolTip"
                policyBridge: surface.host ? surface.host.nodeHelpTooltipPolicyBridge : null
                category: "general"
                active: nameHelpHover.hovered
                text: surface.host ? surface.host.nodeHelpTooltipText : ""
                textFormat: Text.RichText
                delay: 400
                screenStablePositioning: true
                screenStablePlacement: surface.host ? surface.host.nodeHelpTooltipPlacement : "below"
                anchorScale: surface.host ? surface.host.nodeHelpTooltipAnchorScale : 1.0
                screenGap: 8
            }
        }
    }

    Rectangle {
        id: nameDivider
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: nameSection.right
        width: 1
        color: surface.dividerColor
    }

    SurfaceControls.GraphSurfaceCheckBox {
        id: toggleControl
        objectName: "graphBooleanToggleControl"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: surface.portGutterReserve + 8.0
        width: 64.0
        height: 24.0
        switchTrackWidth: 40.0
        switchTrackHeight: 20.0
        host: surface.host
        enabled: !!surface.host && !surface.host.graphReadOnly
        checked: surface.currentValue
        text: checked ? "On" : ""
        Accessible.name: "Boolean value"
        onControlStarted: {
            if (surface.host && surface.nodeId.length)
                surface.host.surfaceControlInteractionStarted(surface.nodeId);
        }
        onClicked: {
            if (surface.host && surface.nodeId.length)
                surface.host.inlinePropertyCommitted(surface.nodeId, "value", checked);
        }
    }
}
