import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

TextField {
    id: control
    property Item host: null
    property Item rectItem: control
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color fillColor: host ? host.inlineInputBackgroundColor : "#22242a"
    property color borderColor: host ? host.inlineInputBorderColor : "#4a4f5a"
    property color focusBorderColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color disabledTextColor: Qt.alpha(textColor, 0.58)
    property color disabledFillColor: host && typeof host.inlineRowColor !== "undefined"
        ? host.inlineRowColor
        : Qt.darker(fillColor, 1.08)
    property color disabledBorderColor: disabledTextColor
    property int controlHeight: 0
    property int controlRadius: 5
    readonly property color resolvedTextColor: enabled ? textColor : disabledTextColor
    readonly property color resolvedBackgroundColor: enabled ? fillColor : disabledFillColor
    readonly property color resolvedBorderColor: enabled
        ? (activeFocus ? focusBorderColor : borderColor)
        : disabledBorderColor
    readonly property var typography: host && host.graphSharedTypography ? host.graphSharedTypography : null
    readonly property int inlineFontPixelSize: {
        var numeric = Number(typography ? typography.inlinePropertyPixelSize : NaN);
        return isFinite(numeric) ? Math.round(numeric) : 10;
    }
    readonly property int inlineFontWeight: {
        var numeric = Number(typography ? typography.inlinePropertyFontWeight : NaN);
        return isFinite(numeric) ? Math.round(numeric) : Font.Normal;
    }
    readonly property real verticalTextPadding: {
        var fieldHeight = Number(control.height);
        var contentHeight = Number(control.contentHeight);
        if (!isFinite(fieldHeight) || fieldHeight <= 0 || !isFinite(contentHeight) || contentHeight <= 0)
            return 3;
        return Math.max(3, Math.floor((fieldHeight - contentHeight) * 0.5));
    }
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(rectItem, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)
    readonly property real textFitWidth: {
        var requiredWidth = Number(control.contentWidth)
            + Number(control.leftPadding)
            + Number(control.rightPadding);
        return isFinite(requiredWidth) && requiredWidth > 0.0
            ? Math.ceil(requiredWidth)
            : 0.0;
    }

    signal controlStarted()

    implicitHeight: controlHeight > 0 ? Math.max(20, controlHeight) : Math.max(24, contentHeight + 6)
    padding: 0
    leftPadding: 8
    rightPadding: 8
    topPadding: verticalTextPadding
    bottomPadding: verticalTextPadding
    selectByMouse: true
    activeFocusOnTab: enabled
    color: resolvedTextColor
    selectionColor: focusBorderColor
    selectedTextColor: host ? host.surfaceColor : "#1b1d22"
    font.pixelSize: inlineFontPixelSize
    font.weight: inlineFontWeight
    renderType: host ? host.nodeTextRenderType : Text.CurveRendering

    onActiveFocusChanged: {
        if (activeFocus)
            controlStarted();
    }

    background: Rectangle {
        radius: control.controlRadius
        color: control.resolvedBackgroundColor
        border.width: 1
        border.color: control.resolvedBorderColor
    }
}
