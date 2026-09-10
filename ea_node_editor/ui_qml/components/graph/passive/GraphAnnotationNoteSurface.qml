import QtQuick 2.15
import ".." as GraphShared

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeAnnotationSurface"
    readonly property string annotationVariant: host ? String(host.surfaceVariant || "") : ""
    readonly property color noteFillColor: _noteFillColor()
    readonly property color noteBorderColor: host && host.isSelected
        ? host.selectedOutlineColor
        : (host && host.hasPassiveBorderOverride
            ? host.outlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.08) : "#4a4f5a"))
    readonly property color primaryTextColor: host ? host.inlineInputTextColor : "#f0f2f5"
    readonly property color secondaryTextColor: host ? host.inlineDrivenTextColor : "#bdc5d3"
    readonly property color labelTextColor: host ? host.inlineLabelColor : "#d0d5de"
    readonly property string editableBodyKey: annotationVariant === "section_header" ? "subtitle" : "body"
    readonly property real bodyFontSize: host ? Number(host.passiveFontPixelSize || 12) : 12
    readonly property real labelFontSize: Math.max(9, bodyFontSize - 2)
    readonly property int bodyLineCount: annotationVariant === "section_header"
        ? 2
        : (annotationVariant === "sticky_note" ? 5 : 4)
    readonly property var embeddedInteractiveRects: richBody.embeddedInteractiveRects
    readonly property var surfaceActions: richBody.surfaceActions
    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    function _noteFillColor() {
        if (host && host.hasPassiveFillOverride)
            return host.surfaceColor;
        if (annotationVariant === "section_header")
            return Qt.alpha(host ? host.surfaceColor : "#2a2b30", 0.22);
        if (annotationVariant === "callout")
            return Qt.darker(host ? host.inlineRowColor : "#24262c", 1.04);
        return Qt.lighter(host ? host.inlineRowColor : "#24262c", 1.08);
    }

    function requestInlineEditAt(localX, localY) {
        return richBody.requestInlineEditAt(localX, localY);
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        return richBody.commitInlineEditFromExternalInteraction(localX, localY);
    }

    function dispatchSurfaceAction(actionId) {
        return richBody.dispatchSurfaceAction(actionId);
    }

    Rectangle {
        anchors.fill: parent
        radius: annotationVariant === "section_header"
            ? Math.max(4, host ? Number(host.resolvedCornerRadius || 6) - 2 : 4)
            : (host ? Number(host.resolvedCornerRadius || 6) : 6)
        color: surface.noteFillColor
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: surface.noteBorderColor
    }

    Rectangle {
        visible: annotationVariant === "sticky_note"
        width: 18
        height: 18
        anchors.top: parent.top
        anchors.right: parent.right
        color: Qt.darker(surface.noteFillColor, 1.12)
        border.width: 1
        border.color: surface.noteBorderColor
        transform: Rotation {
            angle: 45
            origin.x: 0
            origin.y: 0
        }
    }

    Rectangle {
        visible: annotationVariant === "callout"
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 6
        color: host ? host.scopeBadgeColor : "#1D8CE0"
    }

    Rectangle {
        visible: annotationVariant === "section_header"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 3
        color: host ? host.scopeBadgeColor : "#1D8CE0"
    }

    Item {
        id: bodyBounds
        anchors.left: parent.left
        anchors.leftMargin: host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14
        anchors.right: parent.right
        anchors.rightMargin: host ? Number(host.surfaceMetrics.body_right_margin || 14) : 14
        anchors.top: parent.top
        anchors.topMargin: host ? Number(host.surfaceMetrics.body_top || 42) : 42
        anchors.bottom: parent.bottom
        anchors.bottomMargin: host ? Number(host.surfaceMetrics.body_bottom_margin || 12) : 12
        clip: true

        Column {
            anchors.fill: parent
            spacing: annotationVariant === "section_header" ? 6 : 8

            Row {
                id: calloutHeaderRow
                visible: annotationVariant === "callout"
                width: parent.width
                spacing: 8

                Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    color: Qt.alpha(host ? host.scopeBadgeColor : "#1D8CE0", 0.22)
                    border.width: 1
                    border.color: host ? host.scopeBadgeColor : "#1D8CE0"

                    Text {
                        anchors.centerIn: parent
                        text: "!"
                        color: host ? host.scopeBadgeTextColor : "#f2f4f8"
                        font.pixelSize: Math.max(11, surface.bodyFontSize - 1)
                        font.bold: true
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }
                }

                Text {
                    text: "CALLOUT"
                    color: surface.labelTextColor
                    font.pixelSize: surface.labelFontSize
                    font.bold: true
                    opacity: 0.86
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }
            }

            GraphRichTextBlock {
                id: richBody
                objectName: "graphNodeAnnotationRichTextBlock"
                width: parent.width
                height: Math.max(
                    surface.bodyFontSize + 12,
                    bodyBounds.height - (calloutHeaderRow.visible ? calloutHeaderRow.height + parent.spacing : 0)
                )
                host: surface.host
                contentPropertyKey: surface.editableBodyKey
                formatPropertyKey: surface.editableBodyKey + "_format"
                stylePropertyPrefix: surface.editableBodyKey + "_"
                defaultText: ""
                defaultFormat: "plain"
                placeholderValue: surface.annotationVariant === "section_header" ? "Subtitle" : "Body"
                defaultFontSize: surface.bodyFontSize
                defaultFontBold: host ? Boolean(host.passiveFontBold) : false
                defaultTextColor: surface.annotationVariant === "section_header"
                    ? surface.secondaryTextColor
                    : surface.primaryTextColor
                defaultHorizontalAlignment: "left"
                defaultVerticalAlignment: surface.annotationVariant === "section_header" ? "middle" : "top"
                defaultLineHeight: 1.0
                defaultPadding: 0
                maximumLineCount: surface.bodyLineCount
                elideMode: Text.ElideRight
                renderedTextObjectName: surface.annotationVariant === "section_header"
                    ? "graphNodeAnnotationSubtitleText"
                    : "graphNodeAnnotationBodyText"
                editorWrapperObjectName: "graphNodeAnnotationBodyEditor"
                editorObjectName: surface.annotationVariant === "section_header"
                    ? "graphNodeAnnotationSubtitleEditorField"
                    : "graphNodeAnnotationBodyEditorField"
            }
        }
    }
}
