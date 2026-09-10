import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQml 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry
import "SurfaceValueFormatter.js" as SurfaceValueFormatter

// Ordered Interval 1D editor. RangeSlider owns native pointer, keyboard,
// focus, and accessibility behavior; semantic Start/End ordering stays
// separate from the physical lower/upper handles.
RangeSlider {
    id: control
    property Item host: null
    property Item rectItem: control
    property real semanticStart: 0.0
    property real semanticEnd: 1.0
    property bool displayValueAvailable: true
    property string intervalDirection: "increasing"
    property string valueType: "float"
    property int continuousPrecision: 3
    property int knobDiameter: 14
    property int trackAreaHeight: 22
    property int captionGap: 2
    property bool _firstPressCommitArmed: false
    property bool _secondPressCommitArmed: false
    property bool _bindingBlocked: false
    property color accentColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color trackColor: host ? host.inlineInputBorderColor : "#4a4f5a"
    property color handleFillColor: host ? host.inlineInputBackgroundColor : "#22242a"
    property color handleBorderColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color disabledColor: host && typeof host.inlineDrivenTextColor !== "undefined"
        ? host.inlineDrivenTextColor
        : "#95a0b8"
    readonly property var typography: host && host.graphSharedTypography ? host.graphSharedTypography : null
    readonly property int captionPixelSize: {
        var numeric = Number(typography ? typography.inlinePropertyPixelSize : NaN);
        return isFinite(numeric) ? Math.round(numeric) : 10;
    }
    readonly property int captionHeight: Math.max(12, captionPixelSize + 4)
    readonly property int captionReserve: captionGap + captionHeight
    readonly property real captionRegionGap: Math.max(4, Math.round(captionPixelSize * 0.5))
    readonly property real captionHalfWidth: Math.max(1, (width - captionRegionGap) * 0.5)
    readonly property bool interactionActive: first.pressed || second.pressed || _bindingBlocked
    readonly property real fallbackValue: (Number(from) + Number(to)) * 0.5
    readonly property real physicalLowerValue: displayValueAvailable
        ? Math.min(Number(semanticStart), Number(semanticEnd))
        : fallbackValue
    readonly property real physicalUpperValue: displayValueAvailable
        ? Math.max(Number(semanticStart), Number(semanticEnd))
        : fallbackValue
    readonly property bool equalPhysicalValues: Math.abs(Number(first.value) - Number(second.value))
        <= Math.max(1e-9, Math.abs(Number(to) - Number(from)) * 1e-9)
    readonly property real equalHandleSeparation: knobDiameter * 0.28
    readonly property string leftCaptionText: displayValueAvailable
        ? SurfaceValueFormatter.format(
            first.value,
            valueType,
            stepSize,
            continuousPrecision
        )
        : "\u2014"
    readonly property string rightCaptionText: displayValueAvailable
        ? SurfaceValueFormatter.format(
            second.value,
            valueType,
            stepSize,
            continuousPrecision
        )
        : "\u2014"
    readonly property real accessibleSemanticStart: interactionActive
        ? (intervalDirection === "decreasing" ? second.value : first.value)
        : semanticStart
    readonly property real accessibleSemanticEnd: interactionActive
        ? (intervalDirection === "decreasing" ? first.value : second.value)
        : semanticEnd
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(rectItem, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)

    signal controlStarted()
    signal commitRequested(var intervalValue)

    implicitHeight: trackAreaHeight + captionReserve
    padding: 0
    bottomPadding: captionReserve
    hoverEnabled: enabled
    live: true
    snapMode: stepSize > 0 ? RangeSlider.SnapAlways : RangeSlider.NoSnap
    activeFocusOnTab: enabled
    Accessible.name: "Interval 1D"
    Accessible.description: "Start "
        + SurfaceValueFormatter.format(
            accessibleSemanticStart,
            valueType,
            stepSize,
            continuousPrecision
        )
        + ", End "
        + SurfaceValueFormatter.format(
            accessibleSemanticEnd,
            valueType,
            stepSize,
            continuousPrecision
        )
        + "."

    function _commitCurrentValues() {
        var increasing = String(control.intervalDirection || "increasing") !== "decreasing";
        control.commitRequested({
            "start": increasing ? Number(control.first.value) : Number(control.second.value),
            "end": increasing ? Number(control.second.value) : Number(control.first.value)
        });
    }

    first.onPressedChanged: {
        if (first.pressed) {
            control._firstPressCommitArmed = true;
            control._bindingBlocked = true;
            control.controlStarted();
        } else if (control._firstPressCommitArmed) {
            control._firstPressCommitArmed = false;
            control._commitCurrentValues();
            Qt.callLater(function() { control._bindingBlocked = false; });
        }
    }
    second.onPressedChanged: {
        if (second.pressed) {
            control._secondPressCommitArmed = true;
            control._bindingBlocked = true;
            control.controlStarted();
        } else if (control._secondPressCommitArmed) {
            control._secondPressCommitArmed = false;
            control._commitCurrentValues();
            Qt.callLater(function() { control._bindingBlocked = false; });
        }
    }
    first.onMoved: {
        if (!first.pressed) {
            control._bindingBlocked = true;
            control._commitCurrentValues();
            Qt.callLater(function() { control._bindingBlocked = false; });
        }
    }
    second.onMoved: {
        if (!second.pressed) {
            control._bindingBlocked = true;
            control._commitCurrentValues();
            Qt.callLater(function() { control._bindingBlocked = false; });
        }
    }

    Binding {
        target: control.first
        property: "value"
        value: control.physicalLowerValue
        when: !control.interactionActive
        restoreMode: Binding.RestoreNone
    }
    Binding {
        target: control.second
        property: "value"
        value: control.physicalUpperValue
        when: !control.interactionActive
        restoreMode: Binding.RestoreNone
    }

    background: Item {
        x: control.leftPadding
        y: control.topPadding
        width: control.availableWidth
        height: control.availableHeight

        Rectangle {
            id: intervalTrack
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: 3
            radius: height * 0.5
            color: control.enabled ? control.trackColor : Qt.alpha(control.disabledColor, 0.42)
        }

        Rectangle {
            readonly property real lowerPosition: Math.min(control.first.visualPosition, control.second.visualPosition)
            readonly property real upperPosition: Math.max(control.first.visualPosition, control.second.visualPosition)
            readonly property real equalWidth: control.equalHandleSeparation * 2.0
            x: control.equalPhysicalValues
                ? lowerPosition * parent.width - equalWidth * 0.5
                : lowerPosition * parent.width
            width: control.equalPhysicalValues
                ? equalWidth
                : Math.max(0, (upperPosition - lowerPosition) * parent.width)
            anchors.verticalCenter: intervalTrack.verticalCenter
            height: intervalTrack.height
            radius: intervalTrack.radius
            color: control.enabled ? control.accentColor : control.disabledColor
        }
    }

    first.handle: Rectangle {
        objectName: "graphSurfaceIntervalFirstHandle"
        x: Math.max(
            control.leftPadding,
            Math.min(
                control.width - control.rightPadding - width,
                control.leftPadding
                    + control.first.visualPosition * (control.availableWidth - width)
                    - (control.equalPhysicalValues ? control.equalHandleSeparation : 0)
            )
        )
        y: control.topPadding + control.availableHeight * 0.5 - height * 0.5
        width: control.knobDiameter
        height: control.knobDiameter
        radius: width * 0.5
        color: control.enabled ? control.handleFillColor : Qt.alpha(control.disabledColor, 0.28)
        border.width: 1
        border.color: control.enabled ? control.handleBorderColor : control.disabledColor
    }

    second.handle: Rectangle {
        objectName: "graphSurfaceIntervalSecondHandle"
        x: Math.max(
            control.leftPadding,
            Math.min(
                control.width - control.rightPadding - width,
                control.leftPadding
                    + control.second.visualPosition * (control.availableWidth - width)
                    + (control.equalPhysicalValues ? control.equalHandleSeparation : 0)
            )
        )
        y: control.topPadding + control.availableHeight * 0.5 - height * 0.5
        width: control.knobDiameter
        height: control.knobDiameter
        radius: width * 0.5
        color: control.enabled ? control.handleFillColor : Qt.alpha(control.disabledColor, 0.28)
        border.width: 1
        border.color: control.enabled ? control.handleBorderColor : control.disabledColor
    }

    Rectangle {
        objectName: "graphSurfaceIntervalFocusIndicator"
        anchors.fill: parent
        z: 20
        visible: control.enabled && (control.visualFocus || control.activeFocus)
        color: "transparent"
        radius: Math.max(4, control.knobDiameter * 0.35)
        border.width: 1
        border.color: control.accentColor
    }

    Text {
        id: leftCaption
        objectName: "graphSurfaceIntervalLeftCaption"
        readonly property real desiredCenter: control.first.visualPosition * control.width
        x: Math.max(
            0,
            Math.min(control.captionHalfWidth - width, desiredCenter - width * 0.5)
        )
        y: control.trackAreaHeight + control.captionGap
        width: Math.min(Math.max(1, implicitWidth), control.captionHalfWidth)
        height: control.captionHeight
        text: control.leftCaptionText
        color: control.enabled ? control.textColor : control.disabledColor
        font.pixelSize: control.captionPixelSize
        fontSizeMode: Text.Fit
        minimumPixelSize: Math.max(7, control.captionPixelSize - 3)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
    }

    Text {
        id: rightCaption
        objectName: "graphSurfaceIntervalRightCaption"
        readonly property real desiredCenter: control.second.visualPosition * control.width
        x: Math.max(
            control.captionHalfWidth + control.captionRegionGap,
            Math.min(control.width - width, desiredCenter - width * 0.5)
        )
        y: control.trackAreaHeight + control.captionGap
        width: Math.min(Math.max(1, implicitWidth), control.captionHalfWidth)
        height: control.captionHeight
        text: control.rightCaptionText
        color: control.enabled ? control.textColor : control.disabledColor
        font.pixelSize: control.captionPixelSize
        fontSizeMode: Text.Fit
        minimumPixelSize: Math.max(7, control.captionPixelSize - 3)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
    }
}
