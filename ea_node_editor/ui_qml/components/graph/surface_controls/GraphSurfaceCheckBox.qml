import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

CheckBox {
    id: control
    property Item host: null
    property Item rectItem: control
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color fillColor: host ? host.inlineInputBackgroundColor : "#22242a"
    property color borderColor: host ? host.inlineInputBorderColor : "#4a4f5a"
    property color accentColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color indicatorCheckColor: host ? host.surfaceColor : "#1b1d22"
    property real switchTrackWidth: 28
    property real switchTrackHeight: 14
    property color disabledTextColor: Qt.alpha(textColor, 0.58)
    readonly property color resolvedTextColor: enabled ? textColor : disabledTextColor
    readonly property color resolvedIndicatorFillColor: enabled
        ? (checked ? accentColor : fillColor)
        : (host && typeof host.inlineRowColor !== "undefined"
            ? host.inlineRowColor
            : Qt.darker(fillColor, 1.08))
    readonly property color resolvedIndicatorBorderColor: enabled
        ? (checked ? accentColor : borderColor)
        : disabledTextColor
    readonly property var typography: host && host.graphSharedTypography ? host.graphSharedTypography : null
    readonly property int inlineFontPixelSize: {
        var numeric = Number(typography ? typography.inlinePropertyPixelSize : NaN);
        return isFinite(numeric) ? Math.round(numeric) : 10;
    }
    readonly property int inlineFontWeight: {
        var numeric = Number(typography ? typography.inlinePropertyFontWeight : NaN);
        return isFinite(numeric) ? Math.round(numeric) : Font.Normal;
    }
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(rectItem, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)

    signal controlStarted()

    spacing: 6
    padding: 0
    font.pixelSize: inlineFontPixelSize
    font.weight: inlineFontWeight
    hoverEnabled: true
    activeFocusOnTab: enabled

    onPressedChanged: {
        if (pressed)
            controlStarted();
    }

    // Pill toggle switch: track keeps the checked\u2192accent fill/border
    // semantics exported via resolvedIndicator*Color (pinned by
    // tests/test_graph_surface_input_controls.py), knob slides left/right.
    indicator: Rectangle {
        implicitWidth: control.switchTrackWidth
        implicitHeight: control.switchTrackHeight
        radius: height * 0.5
        color: control.resolvedIndicatorFillColor
        border.width: 1
        border.color: control.resolvedIndicatorBorderColor
        anchors.verticalCenter: parent.verticalCenter

        Rectangle {
            width: Math.max(0, parent.height - 4)
            height: width
            radius: width * 0.5
            anchors.verticalCenter: parent.verticalCenter
            x: control.checked ? parent.width - width - 2 : 2
            color: !control.enabled
                ? control.disabledTextColor
                : (control.checked
                ? control.indicatorCheckColor
                : Qt.alpha(control.textColor, 0.75))

            Behavior on x {
                NumberAnimation {
                    duration: 110
                    easing.type: Easing.OutCubic
                }
            }
        }
    }

    contentItem: Text {
        text: control.text
        color: control.resolvedTextColor
        font.pixelSize: control.font.pixelSize
        font.weight: control.font.weight
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
    }
}
