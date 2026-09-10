import QtQuick 2.15
import QtQuick.Controls 2.15
import ".." as GraphShared
import "../../common" as Common
import "../surface_controls" as SurfaceControls

// Pill-shaped Number Slider surface: [name][slider][value readout] in a single
// row with the output port dot centered on the right edge. The host chrome
// draws the pill body itself (resolvedCornerRadius is height/2 for this
// variant), which keeps the shared shadow, state-aware border, and port-notch
// rendering; this surface only draws the row content on top. The standard
// header stays suppressed via the isNumberSliderSurface gates.
GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNumberSliderSurface"

    readonly property string nodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string nodeTitle: host && host.nodeData ? String(host.nodeData.title || "") : ""
    readonly property string roundingMode: propString("rounding", "decimal")
    readonly property bool integerRounding: roundingMode === "integer"
    readonly property int decimalPlaces: Math.max(0, Math.min(6, Math.round(propNumber("decimals", 2))))
    readonly property real minimumValue: propNumber("minimum", 0)
    readonly property real maximumValue: propNumber("maximum", 10)
    readonly property real currentValue: propNumber("value", 5)
    readonly property real pillRadius: height * 0.5
    readonly property real portGutterReserve: host
        ? Math.max(10.0, Number(host.surfaceMetrics.body_right_margin || 0.0))
        : 10.0
    readonly property color pillBorderColor: host ? host.outlineColor : "#4a4f5a"
    readonly property color nameSectionColor: Qt.alpha(pillBorderColor, 0.12)
    readonly property color dividerColor: Qt.alpha(pillBorderColor, 0.55)
    readonly property color nameTextColor: host ? host.headerTextColor : "#f0f2f5"
    readonly property color valueTextColor: host ? host.inlineInputTextColor : "#f0f2f5"

    // Settings-popover contract; GraphCanvasRootLayers watches the open flag
    // and anchors GraphNumberSliderSettingsPopover next to this node.
    property bool sliderSettingsEditorOpen: false
    readonly property var sliderSettingsPayload: ({
        "title": surface.nodeTitle,
        "rounding": surface.roundingMode,
        "decimals": surface.decimalPlaces,
        "minimum": surface.minimumValue,
        "value": surface.currentValue,
        "maximum": surface.maximumValue
    })

    readonly property var embeddedInteractiveRects: []
        .concat(sliderControl.embeddedInteractiveRects || [])
        .concat(valueDoubleClickTarget.embeddedInteractiveRects || [])
    readonly property var surfaceActions: []
    implicitHeight: host ? Number(host.surfaceMetrics.default_height || 0) : 0

    function _formatValue(value) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = 0;
        if (surface.integerRounding)
            return String(Math.round(numeric));
        return numeric.toFixed(surface.decimalPlaces);
    }

    function dispatchSurfaceAction(actionId) {
        if (String(actionId || "") === "number_slider_edit_settings") {
            surface.sliderSettingsEditorOpen = true;
            return true;
        }
        return false;
    }

    function acceptSliderSettings(payload) {
        surface.sliderSettingsEditorOpen = false;
        if (!surface.host || !surface.host.canvasItem || !surface.nodeId.length)
            return false;
        var canvasItem = surface.host.canvasItem;
        if (!canvasItem.commitNodeSurfaceProperties)
            return false;
        return Boolean(canvasItem.commitNodeSurfaceProperties(surface.nodeId, payload || ({})));
    }

    function cancelSliderSettings() {
        surface.sliderSettingsEditorOpen = false;
    }

    // Name section: one translucent fill extends past a clipped right edge,
    // keeping the left edge rounded without double-painting the tint.
    Item {
        id: nameSection
        objectName: "graphNumberSliderNameSection"
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.topMargin: 1
        anchors.bottomMargin: 1
        anchors.leftMargin: 1
        width: Math.max(nameLabel.implicitWidth + 26.0, 82.0)

        Item {
            id: nameSectionFillClip
            objectName: "graphNumberSliderNameSectionFillClip"
            anchors.fill: parent
            clip: true

            Rectangle {
                objectName: "graphNumberSliderNameSectionFill"
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
            objectName: "graphNumberSliderNameLabel"
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
                objectName: "graphNumberSliderHelpToolTip"
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

    SurfaceControls.GraphSurfaceSlider {
        id: sliderControl
        objectName: "graphNumberSliderControl"
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: nameDivider.right
        anchors.right: valueLabel.left
        anchors.leftMargin: 12.0
        anchors.rightMargin: 10.0
        knobDiameter: 21
        host: surface.host
        enabled: !!surface.host && !surface.host.graphReadOnly
        from: surface.minimumValue
        to: Math.max(surface.maximumValue, surface.minimumValue + 1e-9)
        stepSize: surface.integerRounding ? 1 : Math.pow(10, -surface.decimalPlaces)
        snapMode: Slider.SnapAlways
        onControlStarted: {
            if (surface.host && surface.nodeId.length)
                surface.host.surfaceControlInteractionStarted(surface.nodeId);
        }
        onCommitRequested: function(value) {
            if (!surface.host || !surface.nodeId.length)
                return;
            surface.host.inlinePropertyCommitted(
                surface.nodeId,
                "value",
                surface.integerRounding ? Math.round(value) : Number(value)
            );
        }
    }

    // An interactive Slider permanently breaks a declarative value binding on
    // first drag; this keeps payload updates flowing back in whenever the user
    // is not dragging.
    Binding {
        target: sliderControl
        property: "value"
        value: surface.currentValue
        when: !sliderControl.pressed
        restoreMode: Binding.RestoreNone
    }

    Text {
        id: valueLabel
        objectName: "graphNumberSliderValueLabel"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: surface.portGutterReserve + 6.0
        width: Math.max(34.0, implicitWidth)
        horizontalAlignment: Text.AlignRight
        text: surface._formatValue(sliderControl.pressed ? sliderControl.value : surface.currentValue)
        color: surface.valueTextColor
        font.pixelSize: host && host.graphSharedTypography
            ? host.graphSharedTypography.inlinePropertyPixelSize + 1
            : 11
        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
    }

    // Double-click on the value readout opens the settings popover (custom
    // name, rounding, decimals, min/value/max). The knob itself must keep its
    // press events for dragging, so the readout is the double-click target.
    SurfaceControls.GraphSurfaceDoubleClickTarget {
        id: valueDoubleClickTarget
        objectName: "graphNumberSliderValueDoubleClickTarget"
        host: surface.host
        targetItem: valueLabel
        enabled: !!surface.host && !surface.host.graphReadOnly
        cursorShape: Qt.PointingHandCursor
        onDoubleClicked: {
            if (surface.host)
                surface.host.dispatchSurfaceAction("number_slider_edit_settings");
        }
    }
}
