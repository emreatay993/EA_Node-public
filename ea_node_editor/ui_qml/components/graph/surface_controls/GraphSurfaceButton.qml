import QtQuick 2.15
import QtQuick.Controls 2.15
import "../../common" as Common
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

Button {
    id: control
    property Item host: null
    property Item rectItem: control
    property string iconName: ""
    property int iconSize: 14
    property var iconSourceResolver: null
    property string tooltipText: ""
    property bool iconOnly: false
    property bool active: false
    property bool externalHover: false
    property color accentColor: "#4DA8DA"
    property color foregroundColor: host ? host.headerTextColor : "#f0f2f5"
    property color baseFillColor: host ? Qt.alpha(host.inlineInputBackgroundColor, 0.92) : "#22242a"
    property color baseBorderColor: host ? Qt.alpha(host.inlineInputBorderColor, 0.92) : "#4a4f5a"
    property color pressedFillColor: Qt.alpha(accentColor, 0.35)
    property color hoverFillColor: Qt.alpha(accentColor, 0.22)
    property color activeFillColor: Qt.alpha(accentColor, 0.30)
    property color pressedBorderColor: Qt.alpha(accentColor, 0.95)
    property color hoverBorderColor: Qt.alpha(accentColor, 0.85)
    property color activeBorderColor: Qt.alpha(accentColor, 0.95)
    property color disabledForegroundColor: Qt.alpha(foregroundColor, 0.55)
    property real chromeRadius: 6
    property int controlHeight: 0
    property real idleBorderWidth: 1
    property real hoverBorderWidth: 1.5
    property int contentHorizontalPadding: 7
    property int contentVerticalPadding: 4
    property string tooltipCategory: "general"
    property int tooltipTextFormat: Text.PlainText
    property bool tooltipScreenStablePositioning: true
    property real tooltipAnchorScale: 0.0
    property real tooltipScreenGap: 8.0
    property string tooltipScreenStablePlacement: "above"
    readonly property var tooltipPolicyBridge: host && host.canvasItem && host.canvasItem.canvasStateBridgeRef
        ? host.canvasItem.canvasStateBridgeRef
        : null
    readonly property real resolvedTooltipAnchorScale: {
        var explicitScale = Number(tooltipAnchorScale);
        if (isFinite(explicitScale) && explicitScale > 0)
            return explicitScale;
        var bridge = host && host.canvasItem ? host.canvasItem.viewBridge : null;
        var hostZoom = bridge && bridge.zoom_value !== undefined
            ? Number(bridge.zoom_value)
            : 1.0;
        return isFinite(hostZoom) && hostZoom > 0 ? hostZoom : 1.0;
    }
    readonly property bool hoverVisualActive: hovered || externalHover
    readonly property bool stateVisualActive: active || checked
    readonly property color resolvedForegroundColor: !enabled
        ? disabledForegroundColor
        : (stateVisualActive || hoverVisualActive ? accentColor : foregroundColor)
    readonly property color resolvedFillColor: down
        ? pressedFillColor
        : (stateVisualActive ? activeFillColor : (hoverVisualActive ? hoverFillColor : baseFillColor))
    readonly property color resolvedBorderColor: down
        ? pressedBorderColor
        : (stateVisualActive ? activeBorderColor : (hoverVisualActive ? hoverBorderColor : baseBorderColor))
    readonly property real resolvedBorderWidth: stateVisualActive || hoverVisualActive ? hoverBorderWidth : idleBorderWidth
    readonly property var typography: host && host.graphSharedTypography ? host.graphSharedTypography : null
    readonly property int inlineFontPixelSize: {
        var numeric = Number(typography ? typography.inlinePropertyPixelSize : NaN);
        return isFinite(numeric) ? Math.round(numeric) : 10;
    }
    readonly property string resolvedIconSource: {
        if (typeof iconSourceResolver !== "function")
            return "";
        return String(iconSourceResolver(iconName, iconSize, String(resolvedForegroundColor)) || "");
    }
    readonly property string resolvedTooltipText: {
        if (tooltipText.length > 0)
            return tooltipText;
        if (text.length > 0)
            return text;
        if (typeof uiIcons !== "undefined" && uiIcons && iconName.length > 0)
            return String(uiIcons.label(iconName) || "");
        return "";
    }
    readonly property bool tooltipVisible: hovered
        && resolvedTooltipText.length > 0
    readonly property bool labelVisible: text.length > 0 && (!iconOnly || resolvedIconSource.length === 0)
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(rectItem, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)

    signal controlStarted()

    implicitHeight: controlHeight > 0
        ? Math.max(20, controlHeight)
        : Math.max(24, contentRow.implicitHeight + contentVerticalPadding * 2)
    implicitWidth: Math.max(
        iconOnly && resolvedIconSource.length > 0
            ? implicitHeight
            : 28,
        contentRow.implicitWidth + contentHorizontalPadding * 2
    )
    padding: 0
    font.pixelSize: inlineFontPixelSize
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    Common.ManagedToolTip {
        objectName: control.objectName.length > 0 ? control.objectName + "_tooltip" : ""
        policyBridge: control.tooltipPolicyBridge
        category: control.tooltipCategory
        active: control.tooltipVisible
        text: control.resolvedTooltipText
        textFormat: control.tooltipTextFormat
        delay: 280
        screenStablePositioning: control.tooltipScreenStablePositioning
        anchorScale: control.resolvedTooltipAnchorScale
        screenGap: control.tooltipScreenGap
        screenStablePlacement: control.tooltipScreenStablePlacement
    }

    onPressedChanged: {
        if (pressed)
            controlStarted();
    }

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight

        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: control.labelVisible && iconImage.visible ? 6 : 0

            Image {
                id: iconImage
                visible: control.resolvedIconSource.length > 0
                source: control.resolvedIconSource
                width: control.iconSize
                height: control.iconSize
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                sourceSize.width: control.iconSize
                sourceSize.height: control.iconSize
            }

            Text {
                visible: control.labelVisible
                text: control.text
                color: control.resolvedForegroundColor
                font.pixelSize: control.font.pixelSize
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
            }
        }
    }

    background: Rectangle {
        radius: control.chromeRadius
        color: control.resolvedFillColor
        border.width: control.resolvedBorderWidth
        border.color: control.resolvedBorderColor
    }
}
