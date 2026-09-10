import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common

ToolButton {
    id: control
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    readonly property var themePalette: control.themeBridgeRef ? control.themeBridgeRef.palette : ({})
    property string tooltipText: text
    property string tooltipCategory: "general"
    property int tooltipTextFormat: Text.PlainText
    readonly property bool tooltipVisible: hovered
        && tooltipText.length > 0
    property bool accentOutline: false
    property int buttonHeight: 30
    property int labelFontPixelSize: 11
    property int iconCircleSize: 18
    property int iconBarLong: Math.max(8, control.iconCircleSize - 8)
    property int iconBarShort: 2
    property int cornerRadius: 9
    property int contentSpacing: 8
    property int minimumButtonWidth: 108
    property int contentHorizontalPadding: 10
    readonly property bool lightTheme: String(control.themePalette.icon_variant || "light") === "dark"

    function white(alpha) {
        return Qt.rgba(1, 1, 1, alpha)
    }

    implicitHeight: control.buttonHeight
    implicitWidth: Math.max(
        control.minimumButtonWidth,
        contentRow.implicitWidth + (control.contentHorizontalPadding * 2)
    )
    padding: 0
    hoverEnabled: true

    Common.ManagedToolTip {
        policyBridge: control.graphCanvasStateBridgeRef
        category: control.tooltipCategory
        active: control.tooltipVisible
        text: control.tooltipText
        textFormat: control.tooltipTextFormat
        delay: 300
    }

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight

        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: control.contentSpacing

            Rectangle {
                width: control.iconCircleSize
                height: control.iconCircleSize
                radius: control.iconCircleSize / 2
                color: Qt.alpha(control.themePalette.accent, control.accentOutline ? 0.12 : 0.10)
                border.width: 1
                border.color: control.themePalette.accent

                Rectangle {
                    anchors.centerIn: parent
                    width: control.iconBarLong
                    height: control.iconBarShort
                    radius: 1
                    color: control.themePalette.accent
                }

                Rectangle {
                    anchors.centerIn: parent
                    width: control.iconBarShort
                    height: control.iconBarLong
                    radius: 1
                    color: control.themePalette.accent
                }
            }

            Text {
                text: control.text
                color: control.accentOutline
                    ? control.themePalette.accent
                    : control.themePalette.muted_fg
                font.pixelSize: control.labelFontPixelSize
                font.bold: control.accentOutline
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    background: Rectangle {
        radius: control.cornerRadius
        border.width: 1
        border.color: control.down
            ? control.themePalette.accent
            : ((control.hovered || control.accentOutline)
                ? control.themePalette.accent
                : (control.lightTheme
                    ? Qt.rgba(0.16, 0.25, 0.34, 0.14)
                    : control.white(0.10)))
        color: control.down
            ? control.themePalette.pressed
            : (control.hovered
                ? (control.lightTheme ? control.white(0.16) : control.white(0.035))
                : "transparent")
    }
}
