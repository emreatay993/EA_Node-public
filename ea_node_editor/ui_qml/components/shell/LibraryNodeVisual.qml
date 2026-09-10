import QtQuick 2.15
import "../graph/passive" as GraphPassiveComponents

Item {
    id: root
    objectName: "nodeLibraryVisual"
    property var libraryVisual: ({})
    property string displayName: ""
    property var uiIconsRef: null
    property color fillColor: "#20242c"
    property color fillCompositeBaseColor: "#ffffff"
    property color strokeColor: "#7f8da3"
    property color iconColor: "#d8deea"
    property real strokeWidth: 1.2

    readonly property string visualKind: String(libraryVisual ? libraryVisual.kind || "none" : "none")
    readonly property string iconName: String(libraryVisual ? libraryVisual.icon || "" : "")
    readonly property real flowchartAspectRatio: {
        var ratio = Number(libraryVisual ? libraryVisual.aspect_ratio || 0 : 0)
        if (!isFinite(ratio) || ratio <= 0)
            return 1.0
        return ratio
    }
    readonly property real fittedFlowchartWidth: {
        if (root.width <= 0 || root.height <= 0)
            return 0
        return Math.min(root.width, root.height * root.flowchartAspectRatio)
    }
    readonly property real fittedFlowchartHeight: {
        if (root.width <= 0 || root.height <= 0)
            return 0
        return Math.min(root.height, root.width / root.flowchartAspectRatio)
    }
    readonly property color effectiveFlowchartFillColor: root._opaqueCompositeColor(
        root.fillColor,
        root.fillCompositeBaseColor
    )
    readonly property string iconSource: visualKind === "catalog_icon" && iconName.length > 0 && uiIconsRef
        ? uiIconsRef.sourceSized(iconName, Math.max(12, Math.floor(Math.min(width, height) * 0.62)), String(iconColor))
        : ""

    function _opaqueCompositeColor(foreground, background) {
        var alpha = Math.max(0.0, Math.min(1.0, foreground.a))
        return Qt.rgba(
            foreground.r * alpha + background.r * (1.0 - alpha),
            foreground.g * alpha + background.g * (1.0 - alpha),
            foreground.b * alpha + background.b * (1.0 - alpha),
            1.0
        )
    }

    function fallbackText() {
        var trimmed = String(displayName || "").trim()
        if (!trimmed.length)
            return ""
        var parts = trimmed.split(/\s+/)
        if (parts.length > 1)
            return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
        return trimmed.substring(0, Math.min(2, trimmed.length)).toUpperCase()
    }

    GraphPassiveComponents.FlowchartShapeCanvas {
        anchors.centerIn: parent
        width: root.fittedFlowchartWidth
        height: root.fittedFlowchartHeight
        visible: root.visualKind === "flowchart_shape"
        variant: String(root.libraryVisual ? root.libraryVisual.shape_id || root.libraryVisual.surface_variant || "" : "")
        showPreviewContent: true
        fillColor: root.effectiveFlowchartFillColor
        strokeColor: root.strokeColor
        strokeWidth: root.strokeWidth
    }

    Image {
        anchors.centerIn: parent
        width: Math.max(12, Math.floor(Math.min(parent.width, parent.height) * 0.62))
        height: width
        visible: root.visualKind === "catalog_icon" && source.toString().length > 0
        source: root.iconSource
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.max(22, Math.min(parent.width, parent.height) * 0.72)
        height: width
        radius: 5
        visible: root.visualKind === "catalog_icon" && root.iconSource.length === 0
        color: Qt.alpha(root.fillColor, 0.74)
        border.color: root.strokeColor
        border.width: Math.max(1, root.strokeWidth)

        Text {
            anchors.centerIn: parent
            text: root.fallbackText()
            color: root.iconColor
            font.pixelSize: 9
            font.bold: true
        }
    }
}
