import QtQuick 2.15

Item {
    id: surface
    objectName: "graphBareTextSurface"
    property Item host: null
    property alias textValue: richText.textValue
    property alias formatValue: richText.formatValue
    property alias fontFamilyValue: richText.fontFamilyValue
    property alias fontSizeMinimum: richText.fontSizeMinimum
    property alias fontSizeMaximum: richText.fontSizeMaximum
    property alias fontSizeValue: richText.fontSizeValue
    property alias fontWeightValue: richText.fontWeightValue
    property alias italicValue: richText.italicValue
    property alias underlineValue: richText.underlineValue
    property alias strikeoutValue: richText.strikeoutValue
    property alias resolvedFontFamily: richText.resolvedFontFamily
    property alias explicitTextColorValue: richText.explicitTextColorValue
    property alias textColorValue: richText.textColorValue
    property alias backgroundColorValue: richText.backgroundColorValue
    property alias horizontalAlignmentValue: richText.horizontalAlignmentValue
    property alias verticalAlignmentValue: richText.verticalAlignmentValue
    property alias wrapModeValue: richText.wrapModeValue
    property alias lineHeightValue: richText.lineHeightValue
    property alias letterSpacingValue: richText.letterSpacingValue
    property alias paddingValue: richText.paddingValue
    property alias opacityValue: richText.opacityValue
    property alias renderedTextRendererHighQualityActive: richText.renderedTextRendererHighQualityActive
    property alias placeholderTextRendererHighQualityActive: richText.placeholderTextRendererHighQualityActive
    property alias editorTextRendererHighQualityActive: richText.editorTextRendererHighQualityActive
    property alias surfaceActions: richText.surfaceActions
    property alias embeddedInteractiveRects: richText.embeddedInteractiveRects
    property alias styleCommitDelayMs: richText.styleCommitDelayMs
    property alias draftStyle: richText.draftStyle
    property alias editingText: richText.editingText
    readonly property real requiredHeight: {
        var minimum = host && host.surfaceMetrics
            ? Number(host.surfaceMetrics.min_height || 0)
            : 0;
        var measured = Number(richText.measuredContentHeight || 0) + 2 * Number(richText.paddingValue || 0);
        return Math.max(minimum, Math.ceil(measured));
    }
    implicitHeight: requiredHeight

    function _applyRequiredHeight() {
        if (!host || !host.nodeData || richText.textCommitPending
                || host.graphReadOnly)
            return;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return;
        var targetHeight = surface.requiredHeight;
        var live = Boolean(host._liveGeometryActive);
        var x = live ? Number(host._liveX) : Number(host.nodeData.x);
        var y = live ? Number(host._liveY) : Number(host.nodeData.y);
        var width = live ? Number(host._liveWidth) : Number(host.width);
        var currentHeight = live ? Number(host._liveHeight) : Number(host.height);
        if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(currentHeight))
            return;

        var stylePreviewActive = surface.draftStyle
            && Object.keys(surface.draftStyle).length > 0;
        if (surface.editingText || stylePreviewActive || host._resizeInteractionActive) {
            if (!live) {
                host._liveGeometryActive = true;
                host._liveX = x;
                host._liveY = y;
                host._liveWidth = width;
            }
            if (Math.abs(currentHeight - targetHeight) < 0.5)
                return;
            host._liveHeight = targetHeight;
            host.resizePreviewChanged(nodeId, x, y, width, targetHeight, true);
            return;
        }

        if (live) {
            host._liveHeight = targetHeight;
            host.resizePreviewChanged(nodeId, x, y, width, targetHeight, false);
            host.resizeFinished(nodeId, x, y, width, targetHeight);
            host._liveGeometryActive = false;
            return;
        }
        if (Math.abs(currentHeight - targetHeight) >= 0.5)
            host.resizeFinished(nodeId, x, y, width, targetHeight);
    }

    Timer {
        id: autoHeightTimer
        interval: 0
        onTriggered: surface._applyRequiredHeight()
    }

    onRequiredHeightChanged: autoHeightTimer.restart()
    onEditingTextChanged: autoHeightTimer.restart()
    onDraftStyleChanged: autoHeightTimer.restart()
    Component.onCompleted: autoHeightTimer.restart()

    Connections {
        target: richText
        function onTextCommitPendingChanged() {
            if (!richText.textCommitPending)
                autoHeightTimer.restart();
        }
    }

    Connections {
        target: surface.host
        function onWidthChanged() {
            autoHeightTimer.restart();
        }
    }

    GraphRichTextBlock {
        id: richText
        anchors.fill: parent
        host: surface.host
        contentPropertyKey: "text"
        formatPropertyKey: "format"
        stylePropertyPrefix: ""
        defaultText: "Text"
        defaultFormat: "markdown"
        placeholderValue: "Text"
        defaultFontSize: 18
        defaultHorizontalAlignment: "center"
        defaultVerticalAlignment: "middle"
        defaultWrapMode: "word"
        defaultLineHeight: 1.2
        defaultPadding: 4
    }

    function dispatchSurfaceAction(actionId) {
        return richText.dispatchSurfaceAction(actionId);
    }

    function requestInlineEditAt(localX, localY) {
        return richText.requestInlineEditAt(localX, localY);
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        return richText.commitInlineEditFromExternalInteraction(localX, localY);
    }
}
