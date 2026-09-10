import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

ComboBox {
    id: control
    property Item host: null
    property Item rectItem: control
    property bool externalHover: false
    property bool externalPressed: false
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color fillColor: host ? host.inlineInputBackgroundColor : "#22242a"
    property color borderColor: host ? host.inlineInputBorderColor : "#4a4f5a"
    property color focusBorderColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color accentColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color popupFillColor: Qt.darker(fillColor, 1.04)
    property color popupBorderColor: borderColor
    property color hoverOverlayColor: Qt.alpha(accentColor, 0.08)
    property color activeOverlayColor: Qt.alpha(accentColor, 0.10)
    property color pressedOverlayColor: Qt.alpha(accentColor, 0.18)
    property color hoverBorderColor: Qt.alpha(accentColor, 0.82)
    property color pressedBorderColor: accentColor
    property color disabledTextColor: Qt.alpha(textColor, 0.58)
    property color disabledFillColor: host && typeof host.inlineRowColor !== "undefined"
        ? host.inlineRowColor
        : Qt.darker(fillColor, 1.08)
    property color disabledBorderColor: disabledTextColor
    property int controlHeight: 28
    property int controlRadius: 5
    property int contentLeftPadding: 8
    property int contentRightPadding: 24
    property int indicatorRightMargin: 8
    property int popupControlHeight: 0
    readonly property color resolvedTextColor: enabled ? textColor : disabledTextColor
    readonly property color resolvedBackgroundColor: enabled ? fillColor : disabledFillColor
    readonly property bool hoverVisualActive: enabled && (hovered || externalHover)
    readonly property bool pressedVisualActive: enabled && (pressed || externalPressed)
    readonly property bool activeVisualActive: enabled && (visualFocus || popup.visible)
    readonly property color resolvedStateOverlayColor: pressedVisualActive
        ? pressedOverlayColor
        : (activeVisualActive ? activeOverlayColor : (hoverVisualActive ? hoverOverlayColor : Qt.rgba(0, 0, 0, 0)))
    readonly property color resolvedBorderColor: pressedVisualActive
        ? pressedBorderColor
        : (activeVisualActive
            ? focusBorderColor
            : (hoverVisualActive ? hoverBorderColor : (enabled ? borderColor : disabledBorderColor)))
    readonly property real resolvedBorderWidth: activeVisualActive || hoverVisualActive || pressedVisualActive ? 1.5 : 1
    readonly property color resolvedIndicatorColor: enabled && (activeVisualActive || hoverVisualActive || pressedVisualActive)
        ? accentColor
        : resolvedTextColor
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
    readonly property real textFitWidth: {
        var requiredWidth = Number(displayTextMetrics.advanceWidth)
            + Number(displayLabel.leftPadding)
            + Number(displayLabel.rightPadding)
            + Number(control.leftPadding)
            + Number(control.rightPadding);
        return isFinite(requiredWidth) && requiredWidth > 0.0
            ? Math.ceil(requiredWidth)
            : 0.0;
    }
    readonly property real popupRowHeight: Math.max(
        24,
        Math.round(Math.max(
            control.popupControlHeight > 0 ? control.popupControlHeight : control.height,
            control.inlineFontPixelSize + 10
        ))
    )
    readonly property real popupWidth: Math.max(1, control.width)
    readonly property real popupMaxHeight: 160

    signal controlStarted()

    implicitHeight: Math.max(20, controlHeight)
    padding: 0
    leftPadding: contentLeftPadding
    rightPadding: contentRightPadding
    font.pixelSize: inlineFontPixelSize
    font.weight: inlineFontWeight
    hoverEnabled: true
    activeFocusOnTab: enabled

    onPressedChanged: {
        if (pressed)
            controlStarted();
    }

    TextMetrics {
        id: displayTextMetrics
        font: control.font
        text: control.displayText
    }

    contentItem: Text {
        id: displayLabel
        leftPadding: control.leftPadding
        rightPadding: control.rightPadding
        text: control.displayText
        color: control.resolvedTextColor
        font.pixelSize: control.font.pixelSize
        font.weight: control.font.weight
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
    }

    indicator: Text {
        text: "\u25BE"
        color: control.resolvedIndicatorColor
        font.pixelSize: control.font.pixelSize
        font.weight: control.font.weight
        anchors.right: parent.right
        anchors.rightMargin: control.indicatorRightMargin
        anchors.verticalCenter: parent.verticalCenter
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }

    background: Rectangle {
        radius: control.controlRadius
        color: control.resolvedBackgroundColor
        border.width: control.resolvedBorderWidth
        border.color: control.resolvedBorderColor

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.resolvedStateOverlayColor
        }

        Behavior on border.color {
            ColorAnimation { duration: 90 }
        }

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }

    delegate: ItemDelegate {
        width: ListView.view ? ListView.view.width : control.popupWidth
        height: control.popupRowHeight
        padding: 0
        leftPadding: 8
        rightPadding: 8
        topPadding: 0
        bottomPadding: 0
        hoverEnabled: true
        highlighted: control.highlightedIndex === index
        readonly property bool optionPressedVisualActive: down
        readonly property bool optionHoverVisualActive: hovered || highlighted
        contentItem: Text {
            text: modelData
            color: optionHoverVisualActive ? control.accentColor : control.resolvedTextColor
            font.pixelSize: control.font.pixelSize
            font.weight: control.font.weight
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
        }
        background: Rectangle {
            color: optionPressedVisualActive
                ? Qt.alpha(control.accentColor, 0.28)
                : (highlighted
                    ? Qt.alpha(control.accentColor, 0.20)
                    : (hovered ? Qt.alpha(control.accentColor, 0.12) : "transparent"))
            radius: control.controlRadius

            Behavior on color {
                ColorAnimation { duration: 70 }
            }
        }
    }

    popup: Popup {
        y: control.height + 2
        width: control.popupWidth
        implicitWidth: control.popupWidth
        padding: 1
        implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, control.popupMaxHeight + padding * 2)

        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, control.popupMaxHeight)
            implicitWidth: control.popupWidth
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                interactive: true
            }
        }

        background: Rectangle {
            radius: Math.max(3, control.controlRadius + 1)
            color: control.popupFillColor
            border.width: 1
            border.color: control.popupBorderColor
        }
    }
}
