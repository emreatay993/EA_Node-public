import QtQuick 2.15
import "../../../ui_qml/components/graph/surface_controls" as SurfaceControls

Item {
    id: root

    property var themePalette: ({})
    property var nodePalette: ({})
    property string iconName: ""
    property string glyph: ""
    property string label: ""
    property bool actionEnabled: true
    property bool active: false
    property bool floatingChrome: true
    property int buttonSize: 28
    property int iconSize: 15
    property real chromeRadius: 999
    property color accentColor: themePalette.accent || "#60CDFF"

    signal triggered()

    width: root.buttonSize
    height: root.buttonSize

    Item {
        id: hostStub
        property color headerTextColor: root.themePalette.panel_title_fg || "#f0f4fb"
        property color inlineInputBackgroundColor: root.themePalette.toolbar_bg || "#2a2b30"
        property color inlineInputBorderColor: root.themePalette.input_border || "#4a4f5a"
        property var graphSharedTypography: null
        property int nodeTextRenderType: Text.CurveRendering
        property var canvasItem: null
    }

    SurfaceControls.GraphSurfaceButton {
        id: button
        anchors.fill: parent
        host: hostStub
        text: root.iconName.length ? "" : root.glyph
        iconName: root.iconName
        iconOnly: root.iconName.length > 0
        iconSize: root.iconSize
        tooltipText: root.label
        active: root.active
        enabled: root.actionEnabled
        accentColor: root.accentColor
        foregroundColor: root.themePalette.panel_title_fg || "#f0f4fb"
        baseFillColor: root.floatingChrome ? "transparent" : Qt.alpha(root.themePalette.toolbar_bg || "#2a2b30", 0.96)
        baseBorderColor: root.floatingChrome ? "transparent" : Qt.alpha(root.themePalette.input_border || "#4a4f5a", 0.92)
        hoverFillColor: Qt.alpha(root.accentColor, 0.18)
        hoverBorderColor: Qt.alpha(root.accentColor, 0.18)
        pressedFillColor: Qt.alpha(root.accentColor, 0.30)
        pressedBorderColor: Qt.alpha(root.accentColor, 0.80)
        activeFillColor: Qt.alpha(root.accentColor, 0.24)
        activeBorderColor: Qt.alpha(root.accentColor, 0.70)
        idleBorderWidth: root.floatingChrome ? 0 : 1
        hoverBorderWidth: 1
        disabledForegroundColor: Qt.alpha(root.themePalette.muted_fg || "#8d98aa", 0.58)
        chromeRadius: root.chromeRadius
        contentHorizontalPadding: root.floatingChrome ? 7 : 4
        contentVerticalPadding: root.floatingChrome ? 7 : 3
        iconSourceResolver: function(name, size, color) {
            if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
                return "";
            return uiIcons.sourceSized(name, size, color);
        }
        onClicked: root.triggered()
    }
}
