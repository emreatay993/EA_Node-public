import QtQuick 2.15
import ".." as GraphShared

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeGroupBackdropSurface"
    readonly property bool inputOverlayMode: host
        ? String(host.surfaceVariant || "") === "group_backdrop_input_overlay"
        : false
    readonly property bool backdropVisible: !surface.inputOverlayMode
    readonly property color backdropFillColor: _backdropFillColor()
    readonly property color backdropGlassTopColor: host
        ? Qt.alpha(Qt.lighter(host.surfaceColor, host.hasPassiveFillOverride ? 1.12 : 1.22), host.hasPassiveFillOverride ? 0.26 : 0.2)
        : Qt.rgba(0.21, 0.24, 0.29, 0.2)
    readonly property color backdropGlassBottomColor: host
        ? Qt.alpha(Qt.darker(host.surfaceColor, host.hasPassiveFillOverride ? 1.04 : 1.08), host.hasPassiveFillOverride ? 0.34 : 0.26)
        : Qt.rgba(0.12, 0.14, 0.18, 0.26)
    readonly property color backdropBorderColor: host && host.isSelected
        ? host.selectedOutlineColor
        : (host
            ? Qt.alpha(host.outlineColor, host.hasPassiveBorderOverride ? 0.96 : 0.8)
            : "#4a4f5a")
    readonly property color backdropInnerBorderColor: host
        ? Qt.rgba(1.0, 1.0, 1.0, host.isSelected ? 0.18 : 0.11)
        : Qt.rgba(1.0, 1.0, 1.0, 0.11)
    readonly property color accentColor: host
        ? Qt.alpha(host.scopeBadgeColor, host.isSelected ? 0.28 : 0.18)
        : "#4d9fff"
    readonly property color sheenTopColor: host
        ? Qt.rgba(1.0, 1.0, 1.0, host.isSelected ? 0.18 : 0.12)
        : Qt.rgba(1.0, 1.0, 1.0, 0.12)
    readonly property color sheenBottomColor: Qt.rgba(1.0, 1.0, 1.0, 0.0)
    readonly property color lowerTintColor: host
        ? Qt.alpha(host.scopeBadgeColor, host.isSelected ? 0.14 : 0.08)
        : Qt.rgba(0.3, 0.62, 1.0, 0.08)
    function _backdropFillColor() {
        var base = host ? host.surfaceColor : "#1b1d22";
        if (host && host.hasPassiveFillOverride)
            return Qt.alpha(base, 0.34);
        return Qt.alpha(Qt.lighter(base, 1.1), 0.22);
    }

    Rectangle {
        visible: surface.backdropVisible
        anchors.fill: parent
        radius: host ? Math.max(8, Number(host.resolvedCornerRadius || 10) + 2) : 10
        color: "transparent"
        gradient: Gradient {
            GradientStop { position: 0.0; color: surface.backdropGlassTopColor }
            GradientStop { position: 0.32; color: surface.backdropFillColor }
            GradientStop { position: 1.0; color: surface.backdropGlassBottomColor }
        }
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: surface.backdropBorderColor
    }

    Rectangle {
        visible: surface.backdropVisible
        anchors.fill: parent
        anchors.margins: 1
        radius: host ? Math.max(7, Number(host.resolvedCornerRadius || 10) + 1) : 9
        color: "transparent"
        border.width: 1
        border.color: surface.backdropInnerBorderColor
    }

    Rectangle {
        visible: surface.backdropVisible
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: Math.max(56, parent.height * 0.46)
        radius: host ? Math.max(8, Number(host.resolvedCornerRadius || 10) + 2) : 10
        color: "transparent"
        gradient: Gradient {
            GradientStop { position: 0.0; color: surface.sheenTopColor }
            GradientStop { position: 1.0; color: surface.sheenBottomColor }
        }
    }

    Rectangle {
        visible: surface.backdropVisible
        anchors.fill: parent
        radius: host ? Math.max(8, Number(host.resolvedCornerRadius || 10) + 2) : 10
        color: "transparent"
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0.0, 0.0, 0.0, 0.0) }
            GradientStop { position: 1.0; color: surface.lowerTintColor }
        }
    }

    Rectangle {
        visible: surface.backdropVisible
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: Math.max(
            32,
            host ? Number(host.surfaceMetrics.title_top || 14) + Number(host.surfaceMetrics.title_height || 24) + 14 : 40
        )
        color: surface.accentColor
        opacity: 0.7
    }

}
