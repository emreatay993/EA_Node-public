import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common

Button {
    id: control
    property var pane
    property bool destructive: false
    property bool selectedStyle: false
    property bool compact: false
    property string iconName: ""
    property int iconSize: compact ? 14 : 16
    property string tooltipText: ""
    property string tooltipCategory: "general"
    property int tooltipTextFormat: Text.PlainText
    readonly property var uiIconsRef: control.pane && control.pane.uiIconsRef ? control.pane.uiIconsRef : null
    readonly property var tooltipPolicyBridge: control.pane ? control.pane.graphCanvasStateBridgeRef : null
    readonly property bool tooltipVisible: hovered
        && tooltipText.length > 0
    readonly property color fillColor: !enabled
        ? pane.themePalette.tab_bg
        : destructive
            ? (down ? pane.themePalette.inspector_danger_border
                : (hovered ? pane.themePalette.inspector_danger_border : pane.themePalette.inspector_danger_bg))
            : selectedStyle
                ? pane.themePalette.accent_strong
                : (down
                    ? pane.themePalette.hover
                    : (hovered ? pane.themePalette.hover : pane.themePalette.input_bg))
    readonly property color outlineColor: destructive
        ? pane.themePalette.inspector_danger_border
        : (selectedStyle ? pane.themePalette.accent : pane.themePalette.input_border)
    readonly property color labelColor: !enabled
        ? pane.themePalette.muted_fg
        : (destructive
            ? pane.themePalette.inspector_danger_fg
            : (selectedStyle ? pane.themePalette.panel_title_fg : pane.themePalette.tab_fg))
    readonly property string resolvedIconSource: iconName.length > 0
        && uiIconsRef
        && uiIconsRef.has(iconName)
            ? uiIconsRef.sourceSized(iconName, iconSize, String(labelColor))
            : ""

    implicitHeight: compact ? 30 : 36
    implicitWidth: Math.max(compact ? 80 : 92, contentRow.implicitWidth + (compact ? 18 : 22))
    hoverEnabled: true
    padding: 0

    Common.ManagedToolTip {
        policyBridge: control.tooltipPolicyBridge
        category: control.tooltipCategory
        active: control.tooltipVisible
        text: control.tooltipText
        textFormat: control.tooltipTextFormat
        delay: 280
    }

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: Math.max(label.implicitHeight, iconImage.visible ? iconImage.implicitHeight : 0)

        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: iconImage.visible && label.text.length > 0 ? 6 : 0

            Image {
                id: iconImage
                width: visible ? control.iconSize : 0
                height: width
                visible: control.resolvedIconSource.length > 0
                source: control.resolvedIconSource
                fillMode: Image.PreserveAspectFit
                mipmap: true
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                id: label
                text: control.text
                color: control.labelColor
                font.pixelSize: control.compact ? 10 : 12
                font.bold: true
                font.letterSpacing: control.compact ? 0.5 : 0.2
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    background: Rectangle {
        radius: control.compact ? 10 : 11
        color: control.fillColor
        border.color: control.outlineColor
        border.width: 1
    }
}
