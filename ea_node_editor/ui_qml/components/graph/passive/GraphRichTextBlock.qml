import QtQuick 2.15
import ".." as GraphShared
import QtQuick.Controls 2.15
import "../../common/FontFamilyOptions.js" as FontFamilyOptions
import "../surface_controls" as SurfaceControls
import "../GraphNodeHostHitTesting.js" as GraphNodeHostHitTesting

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphRichTextBlock"
    property string contentPropertyKey: "text"
    property string formatPropertyKey: contentPropertyKey === "text" ? "format" : contentPropertyKey + "_format"
    property string stylePropertyPrefix: contentPropertyKey === "text" ? "" : contentPropertyKey + "_"
    property string defaultText: "Text"
    property string defaultFormat: "markdown"
    property string placeholderValue: "Text"
    property real defaultFontSize: 18
    property bool defaultFontBold: false
    property string defaultTextColor: ""
    property string defaultHorizontalAlignment: "center"
    property string defaultVerticalAlignment: "middle"
    property string defaultWrapMode: "word"
    property real defaultLineHeight: 1.2
    property real defaultLetterSpacing: 0.0
    property int defaultPadding: 4
    property real defaultOpacity: 1.0
    property int maximumLineCount: 0
    property int elideMode: Text.ElideNone
    property bool editModeAlwaysVisible: false
    property bool useDefaultTextWhenBlank: false
    property bool localPointerTargetEnabled: true
    property string renderedTextObjectName: "graphBareTextRenderedText"
    property string placeholderTextObjectName: "graphBareTextPlaceholderText"
    property string editorWrapperObjectName: ""
    property string editorObjectName: "graphBareTextEditor"
    property string editorLayoutProbeObjectName: "graphBareTextEditorLayoutProbe"
    readonly property bool usesPrefixedStyle: stylePropertyPrefix.length > 0
    readonly property bool editorVisible: editingText || editModeAlwaysVisible
    readonly property string textValue: _contentTextValue()
    readonly property string formatValue: _choiceProperty("format", ["markdown", "plain"], defaultFormat)
    readonly property string fontFamilyValue: _stringProperty("font_family", "").trim()
    readonly property int fontSizeMinimum: 6
    readonly property int fontSizeMaximum: 144
    readonly property int fontSizeValue: _intProperty("font_size", defaultFontSize, fontSizeMinimum, fontSizeMaximum)
    readonly property string fontWeightValue: _choiceProperty(
        "font_weight",
        ["normal", "medium", "demibold", "bold", "black"],
        defaultFontBold ? "bold" : "normal"
    )
    readonly property bool italicValue: _boolProperty("italic", false)
    readonly property bool underlineValue: _boolProperty("underline", false)
    readonly property bool strikeoutValue: _boolProperty("strikeout", false)
    readonly property string resolvedFontFamily: fontFamilyValue.length > 0
        ? fontFamilyValue
        : Qt.application.font.family
    readonly property string explicitTextColorValue: _colorProperty("text_color", "")
    readonly property string textColorValue: explicitTextColorValue.length > 0
        ? explicitTextColorValue
        : (defaultTextColor.length > 0 ? defaultTextColor : _autoTextColorForCanvas())
    readonly property string backgroundColorValue: _colorProperty("background_color", "")
    readonly property string horizontalAlignmentValue: _choiceProperty(
        "horizontal_alignment",
        ["left", "center", "right", "justify"],
        defaultHorizontalAlignment
    )
    readonly property string verticalAlignmentValue: _choiceProperty(
        "vertical_alignment",
        ["top", "middle", "bottom"],
        defaultVerticalAlignment
    )
    readonly property string wrapModeValue: _choiceProperty("wrap_mode", ["word", "anywhere", "none"], defaultWrapMode)
    readonly property real lineHeightValue: _numberProperty("line_height", defaultLineHeight, 0.5, 4.0)
    readonly property real letterSpacingValue: _numberProperty("letter_spacing", defaultLetterSpacing, -10.0, 20.0)
    readonly property int paddingValue: _intProperty("padding", defaultPadding, 0, 64)
    readonly property real opacityValue: _intProperty("opacity", Math.round(defaultOpacity * 100), 0, 100) / 100.0
    readonly property int highQualityTextRenderType: host ? host.nodeTextRenderType : Text.CurveRendering
    readonly property int editorTextRenderType: host ? host.nodeTextRenderType : TextEdit.CurveRendering
    readonly property int highQualityTextRenderQuality: Text.NormalRenderTypeQuality
    readonly property int resolvedFontWeight: _fontWeight()
    readonly property int resolvedTextWrapMode: _textWrapMode()
    readonly property int resolvedEditorWrapMode: _editorWrapMode()
    readonly property int resolvedHorizontalAlignment: _horizontalAlignment()
    readonly property int resolvedVerticalAlignment: _verticalAlignment()
    readonly property bool renderedTextRendererHighQualityActive: renderedText.renderType === highQualityTextRenderType
        && renderedText.renderTypeQuality === highQualityTextRenderQuality
    readonly property bool placeholderTextRendererHighQualityActive: placeholderText.renderType === highQualityTextRenderType
        && placeholderText.renderTypeQuality === highQualityTextRenderQuality
    readonly property bool editorTextRendererHighQualityActive: textEditor.renderType === editorTextRenderType
    readonly property bool textCommitPending: surface._focusInitialized
        && !surface.editorVisible
        && textEditor.text !== surface.textValue
    readonly property real measuredContentHeight: surface.editorVisible || surface.textCommitPending
        ? Number(editorLayoutProbe.contentHeight || 0)
        : Number(renderedText.contentHeight || 0)
    readonly property bool isBoldWeight: fontWeightValue === "bold" || fontWeightValue === "black"
        || fontWeightValue === "demibold"
    readonly property bool bulletListActive: _allTextLinesUseListMode("bullet")
    readonly property bool numberedListActive: _allTextLinesUseListMode("numbered")
    readonly property bool displayLinkPointerTargetEnabled: surface.localPointerTargetEnabled
        && !surface.editorVisible
        && surface.formatValue === "markdown"
        && surface.textValue.indexOf("corex-link:") >= 0
    readonly property var textAnnotationStyleKeys: [
        "font_family",
        "font_size",
        "font_weight",
        "italic",
        "underline",
        "strikeout",
        "text_color",
        "background_color",
        "horizontal_alignment",
        "vertical_alignment",
        "wrap_mode",
        "line_height",
        "letter_spacing",
        "padding",
        "opacity"
    ]
    readonly property var surfaceActions: _surfaceActions()
    readonly property var embeddedInteractiveRects: textEditor.visible
        ? editorInteractionRegion.embeddedInteractiveRects
        : (surface.displayLinkPointerTargetEnabled ? displayDoubleClickTarget.embeddedInteractiveRects : [])
    readonly property int styleCommitDelayMs: 70
    property var draftStyle: ({})
    property var _pendingStyleCommits: ({})
    property bool editingText: false
    property bool _blurCommitEnabled: false
    property bool _focusInitialized: false
    property string _hoveredCorexLinkId: ""
    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    onNodePropertiesChanged: surface._dropResolvedDraftProperties()

    Component.onDestruction: surface._flushDraftCommits()

    Component.onCompleted: {
        if (surface.editModeAlwaysVisible)
            textEditor.text = surface.textValue;
    }

    onTextValueChanged: {
        if (surface.editModeAlwaysVisible && !textEditor.activeFocus)
            textEditor.text = surface.textValue;
    }

    Timer {
        id: styleCommitTimer
        interval: surface.styleCommitDelayMs
        repeat: false
        onTriggered: surface._flushDraftCommits()
    }

    function _storedProperty(key) {
        var actualKey = surface._actualPropertyKey(key);
        var value = nodeProperties && nodeProperties[actualKey] !== undefined ? nodeProperties[actualKey] : undefined;
        return surface._inheritedStyleValue(key, value) ? undefined : value;
    }

    function _actualPropertyKey(key) {
        var normalized = String(key || "");
        if (normalized === "text")
            return String(surface.contentPropertyKey || "text");
        if (normalized === "format")
            return String(surface.formatPropertyKey || "format");
        if (surface.stylePropertyPrefix.length > 0)
            return String(surface.stylePropertyPrefix) + normalized;
        return normalized;
    }

    function _inheritedStyleValue(key, value) {
        if (!surface.usesPrefixedStyle)
            return value === undefined || value === null;
        if (value === undefined || value === null)
            return true;
        var normalizedKey = String(key || "");
        if (normalizedKey === "font_size")
            return Number(value) <= 0;
        if (normalizedKey === "line_height")
            return Number(value) <= 0;
        if (normalizedKey === "letter_spacing")
            return Number(value) <= -999;
        if (normalizedKey === "padding")
            return Number(value) < 0;
        if (normalizedKey === "opacity")
            return Number(value) < 0;
        if (normalizedKey === "font_weight"
                || normalizedKey === "horizontal_alignment"
                || normalizedKey === "vertical_alignment"
                || normalizedKey === "wrap_mode")
            return String(value || "").trim().length === 0;
        return false;
    }

    function _draftHasProperty(key) {
        var draft = surface.draftStyle || {};
        return draft[key] !== undefined;
    }

    function _rawProperty(key) {
        if (surface._draftHasProperty(key))
            return surface.draftStyle[key];
        return surface._storedProperty(key);
    }

    function _stringProperty(key, fallback) {
        var value = surface._rawProperty(key);
        if (value === undefined || value === null)
            return String(fallback || "");
        return String(value);
    }

    function _contentTextValue() {
        var value = surface._stringProperty("text", surface.defaultText);
        if (surface.useDefaultTextWhenBlank && value.trim().length === 0)
            return String(surface.defaultText || "");
        return value;
    }

    function _choiceProperty(key, choices, fallback) {
        var value = surface._stringProperty(key, fallback).trim().toLowerCase();
        for (var i = 0; i < choices.length; i++) {
            if (value === choices[i])
                return value;
        }
        return fallback;
    }

    function _boolProperty(key, fallback) {
        var value = surface._rawProperty(key);
        if (typeof value === "boolean")
            return value;
        var text = String(value === undefined || value === null ? "" : value).trim().toLowerCase();
        if (text === "true" || text === "1" || text === "yes" || text === "on")
            return true;
        if (text === "false" || text === "0" || text === "no" || text === "off")
            return false;
        return Boolean(fallback);
    }

    function _numberProperty(key, fallback, minimum, maximum) {
        var numeric = Number(surface._rawProperty(key));
        if (!isFinite(numeric))
            numeric = Number(fallback);
        if (!isFinite(numeric))
            numeric = 0;
        return Math.max(Number(minimum), Math.min(numeric, Number(maximum)));
    }

    function _intProperty(key, fallback, minimum, maximum) {
        return Math.round(surface._numberProperty(key, fallback, minimum, maximum));
    }

    function _colorProperty(key, fallback) {
        var value = surface._stringProperty(key, "").trim();
        return /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(value) ? value.toUpperCase() : String(fallback || "");
    }

    function _themePaletteValue(key, fallback) {
        var canvas = host && host.canvasItem ? host.canvasItem : null;
        var palette = canvas && canvas.themePalette ? canvas.themePalette : null;
        if (palette && palette[key] !== undefined)
            return String(palette[key] || fallback || "");
        return String(fallback || "");
    }

    function _canvasBackgroundColor() {
        var canvas = host && host.canvasItem ? host.canvasItem : null;
        var variant = canvas && canvas.canvasBackgroundVariant !== undefined
            ? String(canvas.canvasBackgroundVariant || "theme").trim().toLowerCase()
            : "theme";
        if (variant === "dark")
            return "#1D1F24";
        if (variant === "light")
            return "#F3F5F8";
        if (variant === "white")
            return "#FFFFFF";
        return surface._themePaletteValue("canvas_bg", "#1D1F24");
    }

    function _hexChannels(value) {
        var text = String(value || "").trim();
        if (/^#[0-9a-fA-F]{6}$/.test(text)) {
            return {
                "r": parseInt(text.substr(1, 2), 16),
                "g": parseInt(text.substr(3, 2), 16),
                "b": parseInt(text.substr(5, 2), 16)
            };
        }
        if (/^#[0-9a-fA-F]{8}$/.test(text)) {
            return {
                "r": parseInt(text.substr(3, 2), 16),
                "g": parseInt(text.substr(5, 2), 16),
                "b": parseInt(text.substr(7, 2), 16)
            };
        }
        return null;
    }

    function _linearChannel(value) {
        var channel = Math.max(0, Math.min(255, Number(value))) / 255.0;
        return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    }

    function _relativeLuminance(colorValue) {
        var channels = surface._hexChannels(colorValue);
        if (!channels)
            return 0.0;
        return 0.2126 * surface._linearChannel(channels.r)
            + 0.7152 * surface._linearChannel(channels.g)
            + 0.0722 * surface._linearChannel(channels.b);
    }

    function _autoTextColorForCanvas() {
        return surface._relativeLuminance(surface._canvasBackgroundColor()) > 0.55
            ? "#000000"
            : "#FFFFFF";
    }

    function _fontWeight() {
        if (surface.fontWeightValue === "black")
            return Font.Black;
        if (surface.fontWeightValue === "bold")
            return Font.Bold;
        if (surface.fontWeightValue === "demibold")
            return Font.DemiBold;
        if (surface.fontWeightValue === "medium")
            return Font.Medium;
        return Font.Normal;
    }

    function _horizontalAlignment() {
        if (surface.horizontalAlignmentValue === "center")
            return Text.AlignHCenter;
        if (surface.horizontalAlignmentValue === "right")
            return Text.AlignRight;
        if (surface.horizontalAlignmentValue === "justify")
            return Text.AlignJustify;
        return Text.AlignLeft;
    }

    function _verticalAlignment() {
        if (surface.verticalAlignmentValue === "middle")
            return Text.AlignVCenter;
        if (surface.verticalAlignmentValue === "bottom")
            return Text.AlignBottom;
        return Text.AlignTop;
    }

    function _textWrapMode() {
        if (surface.wrapModeValue === "none")
            return Text.NoWrap;
        if (surface.wrapModeValue === "anywhere")
            return Text.WrapAnywhere;
        return Text.WordWrap;
    }

    function _editorWrapMode() {
        if (surface.wrapModeValue === "none")
            return TextEdit.NoWrap;
        if (surface.wrapModeValue === "anywhere")
            return TextEdit.WrapAnywhere;
        return TextEdit.Wrap;
    }

    function _editorVerticalPadding() {
        var freeHeight = Math.max(0, textBounds.height - editorLayoutProbe.contentHeight);
        if (surface.verticalAlignmentValue === "middle")
            return Math.round(freeHeight / 2);
        if (surface.verticalAlignmentValue === "bottom")
            return Math.round(freeHeight);
        return 0;
    }

    function _beginInteraction() {
        if (host && host.nodeData)
            host.surfaceControlInteractionStarted(String(host.nodeData.node_id || ""));
    }

    function _commitProperty(key, value) {
        if (!host || !host.nodeData)
            return false;
        host.inlinePropertyCommitted(
            String(host.nodeData.node_id || ""),
            surface._actualPropertyKey(key),
            value
        );
        return true;
    }

    function _copyObject(value) {
        var source = value || {};
        var copy = {};
        for (var key in source)
            copy[key] = source[key];
        return copy;
    }

    function _setDraftProperty(key, value) {
        var normalizedKey = String(key || "");
        if (!normalizedKey.length)
            return false;
        if (surface._draftHasProperty(normalizedKey)
                && String(surface.draftStyle[normalizedKey]) === String(value))
            return true;
        var nextDraft = surface._copyObject(surface.draftStyle);
        nextDraft[normalizedKey] = value;
        surface.draftStyle = nextDraft;
        return true;
    }

    function _dropResolvedDraftProperties() {
        var draft = surface.draftStyle || {};
        var pending = surface._pendingStyleCommits || {};
        var nextDraft = {};
        var nextPending = {};
        var changed = false;
        for (var key in draft) {
            if (String(surface._storedProperty(key)) === String(draft[key])) {
                changed = true;
                continue;
            }
            nextDraft[key] = draft[key];
        }
        for (var pendingKey in pending) {
            if (String(surface._storedProperty(pendingKey)) === String(pending[pendingKey])) {
                changed = true;
                continue;
            }
            nextPending[pendingKey] = pending[pendingKey];
        }
        if (changed) {
            surface.draftStyle = nextDraft;
            surface._pendingStyleCommits = nextPending;
        }
    }

    function _queueStyleCommit(key, value, flushNow) {
        var normalizedKey = String(key || "");
        if (!normalizedKey.length)
            return false;
        var nextPending = surface._copyObject(surface._pendingStyleCommits);
        if (String(surface._storedProperty(normalizedKey)) === String(value))
            delete nextPending[normalizedKey];
        else
            nextPending[normalizedKey] = value;
        surface._pendingStyleCommits = nextPending;
        if (flushNow)
            return surface._flushDraftCommits();
        styleCommitTimer.restart();
        return true;
    }

    function _flushDraftCommits() {
        styleCommitTimer.stop();
        var pending = surface._pendingStyleCommits || {};
        surface._pendingStyleCommits = ({});
        var committed = false;
        for (var key in pending) {
            var value = pending[key];
            if (String(surface._storedProperty(key)) === String(value))
                continue;
            committed = surface._commitProperty(key, value) || committed;
        }
        return committed;
    }

    function _setStylePropertyIfChanged(key, value, flushNow) {
        if (String(surface._rawProperty(key)) === String(value)) {
            if (flushNow)
                surface._flushDraftCommits();
            return true;
        }
        surface._setDraftProperty(key, value);
        return surface._queueStyleCommit(key, value, Boolean(flushNow));
    }

    function _beginTextEdit() {
        if (surface.editModeAlwaysVisible) {
            surface._beginInteraction();
            textEditor.forceActiveFocus();
            return true;
        }
        if (surface.editingText)
            return true;
        if (!host || !host.nodeData)
            return false;
        surface.editingText = true;
        surface._blurCommitEnabled = false;
        surface._focusInitialized = false;
        surface._beginInteraction();
        textEditor.text = surface.textValue;
        Qt.callLater(function() {
            textEditor.forceActiveFocus();
            textEditor.cursorPosition = textEditor.length;
            textEditor.deselect();
            Qt.callLater(function() {
                surface._blurCommitEnabled = surface.editingText && textEditor.activeFocus;
            });
        });
        return true;
    }

    function _commitText(value) {
        if (!surface.editorVisible)
            return false;
        var nextValue = String(value === undefined || value === null ? "" : value);
        surface._blurCommitEnabled = false;
        if (!surface.editModeAlwaysVisible)
            surface.editingText = false;
        if (nextValue !== surface.textValue)
            surface._commitProperty("text", nextValue);
        if (surface.editModeAlwaysVisible)
            textEditor.text = nextValue;
        return true;
    }

    function _cancelTextEdit() {
        surface._blurCommitEnabled = false;
        if (!surface.editModeAlwaysVisible)
            surface.editingText = false;
        textEditor.text = surface.textValue;
    }

    function _setFontSize(delta) {
        var nextSize = Math.max(
            surface.fontSizeMinimum,
            Math.min(surface.fontSizeMaximum, surface.fontSizeValue + Number(delta || 0))
        );
        return surface._setStylePropertyIfChanged("font_size", nextSize, true);
    }

    function _setFontSizeAbsolute(value, flushNow) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            return false;
        var nextSize = Math.max(
            surface.fontSizeMinimum,
            Math.min(surface.fontSizeMaximum, Math.round(numeric))
        );
        return surface._setStylePropertyIfChanged("font_size", nextSize, flushNow !== false);
    }

    function _setFontFamily(value) {
        var text = String(value === undefined || value === null ? "" : value).trim();
        var family = FontFamilyOptions.canonicalFamily(text);
        if (!family.length && text.length > 0
                && text.toLowerCase() !== FontFamilyOptions.DEFAULT_FONT_FAMILY_LABEL.toLowerCase())
            return false;
        return surface._setStylePropertyIfChanged("font_family", family, false);
    }

    function _toggleBold() {
        return surface._setStylePropertyIfChanged("font_weight", surface.isBoldWeight ? "normal" : "bold", false);
    }

    function _toggleBoolProperty(key, currentValue) {
        return surface._setStylePropertyIfChanged(key, !Boolean(currentValue), false);
    }

    function _cycleWrapMode() {
        var nextValue = "word";
        if (surface.wrapModeValue === "word")
            nextValue = "anywhere";
        else if (surface.wrapModeValue === "anywhere")
            nextValue = "none";
        return surface._setStylePropertyIfChanged("wrap_mode", nextValue, false);
    }

    function _setWrapMode(value) {
        return surface._setStylePropertyIfChanged("wrap_mode", String(value || "word"), false);
    }

    function _splitLines(value) {
        return String(value === undefined || value === null ? "" : value).split(/\r\n|\n|\r/);
    }

    function _leadingWhitespace(value) {
        var text = String(value || "");
        var trimmed = text.replace(/^\s+/, "");
        return text.substring(0, text.length - trimmed.length);
    }

    function _listModeForLine(line) {
        var trimmed = String(line || "").replace(/^\s+/, "");
        if (/^[-+*]\s+/.test(trimmed))
            return "bullet";
        if (/^\d+[.)]\s+/.test(trimmed))
            return "numbered";
        return "";
    }

    function _stripListMarker(line) {
        var text = String(line || "");
        var indent = surface._leadingWhitespace(text);
        var trimmed = text.substring(indent.length);
        return indent + trimmed.replace(/^[-+*]\s+/, "").replace(/^\d+[.)]\s+/, "");
    }

    function _allTextLinesUseListMode(mode) {
        var lines = surface._splitLines(surface.textValue);
        var nonBlankCount = 0;
        for (var i = 0; i < lines.length; i++) {
            if (String(lines[i] || "").trim().length === 0)
                continue;
            nonBlankCount += 1;
            if (surface._listModeForLine(lines[i]) !== mode)
                return false;
        }
        return nonBlankCount > 0;
    }

    function _toggleListMode(mode) {
        if (!host || !host.nodeData)
            return false;
        var normalizedMode = String(mode || "") === "numbered" ? "numbered" : "bullet";
        var sourceText = surface.editorVisible ? textEditor.text : surface.textValue;
        var lines = surface._splitLines(sourceText);
        var removeExisting = true;
        var nonBlankCount = 0;
        for (var i = 0; i < lines.length; i++) {
            if (String(lines[i] || "").trim().length === 0)
                continue;
            nonBlankCount += 1;
            if (surface._listModeForLine(lines[i]) !== normalizedMode)
                removeExisting = false;
        }
        if (nonBlankCount === 0)
            return false;

        var nextLines = [];
        var orderedIndex = 1;
        for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
            var line = String(lines[lineIndex] || "");
            if (line.trim().length === 0) {
                nextLines.push(line);
                continue;
            }
            var stripped = surface._stripListMarker(line);
            if (removeExisting) {
                nextLines.push(stripped);
                continue;
            }
            var indent = surface._leadingWhitespace(stripped);
            var content = stripped.substring(indent.length);
            if (normalizedMode === "numbered") {
                nextLines.push(indent + String(orderedIndex) + ". " + content);
                orderedIndex += 1;
            } else {
                nextLines.push(indent + "- " + content);
            }
        }

        var nextText = nextLines.join("\n");
        if (nextText === String(sourceText || "") && surface.formatValue === "markdown")
            return true;
        surface._setDraftProperty("text", nextText);
        if (surface.editorVisible)
            textEditor.text = nextText;
        var committed = false;
        if (surface.formatValue !== "markdown") {
            surface._setDraftProperty("format", "markdown");
            committed = surface._commitProperty("format", "markdown") || committed;
        }
        if (nextText !== String(sourceText || ""))
            committed = surface._commitProperty("text", nextText) || committed;
        return committed;
    }

    function _alignmentIcon() {
        if (surface.horizontalAlignmentValue === "center")
            return "format-align-center";
        if (surface.horizontalAlignmentValue === "right")
            return "format-align-right";
        if (surface.horizontalAlignmentValue === "justify")
            return "format-align-justify";
        return "format-align-left";
    }

    function _alignmentLabel() {
        if (surface.horizontalAlignmentValue === "center")
            return "Align center";
        if (surface.horizontalAlignmentValue === "right")
            return "Align right";
        if (surface.horizontalAlignmentValue === "justify")
            return "Justify";
        return "Align left";
    }

    function _wrapLabel() {
        if (surface.wrapModeValue === "anywhere")
            return "Wrap anywhere";
        if (surface.wrapModeValue === "none")
            return "No wrapping";
        return "Wrap words";
    }

    function _canvasCommandBridge() {
        if (!host || !host.canvasItem)
            return null;
        return host.canvasItem.canvasCommandBridgeRef
            || host.canvasItem.canvasCommandBridge
            || null;
    }

    function _corexLinkIdFromHref(href) {
        var text = String(href || "").trim();
        var prefix = "corex-link:";
        if (text.indexOf(prefix) !== 0)
            return "";
        return text.substring(prefix.length).trim();
    }

    function _nodeId() {
        if (!host || !host.nodeData)
            return "";
        return String(host.nodeData.node_id || "").trim();
    }

    function _linkHrefAt(x, y) {
        if (!renderedText.visible || surface.formatValue !== "markdown" || !renderedText.linkAt)
            return "";
        return String(renderedText.linkAt(x, y) || "");
    }

    function _showCorexLinkHoverCard(linkId, x, y) {
        var nodeId = surface._nodeId();
        if (!nodeId || !linkId || !host || !host.parent || !host.canvasItem || !host.canvasItem.showNodeLinkHoverCard)
            return false;
        var point = textBounds.mapToItem(host.parent, x, y + 18);
        return Boolean(host.canvasItem.showNodeLinkHoverCard(nodeId, linkId, point.x, point.y));
    }

    function _scheduleCorexLinkHoverDismiss() {
        if (host && host.canvasItem && host.canvasItem.scheduleNodeLinkHoverDismiss)
            host.canvasItem.scheduleNodeLinkHoverDismiss();
    }

    function _updateCorexLinkHover(x, y) {
        var linkId = surface._corexLinkIdFromHref(surface._linkHrefAt(x, y));
        surface._hoveredCorexLinkId = linkId;
        if (linkId.length > 0)
            surface._showCorexLinkHoverCard(linkId, x, y);
        else
            surface._scheduleCorexLinkHoverDismiss();
    }

    function _openCorexLinkAt(x, y) {
        return surface._openCorexLink(surface._corexLinkIdFromHref(surface._linkHrefAt(x, y)));
    }

    function _openCorexLink(linkId) {
        var nodeId = surface._nodeId();
        var bridge = surface._canvasCommandBridge();
        if (!nodeId || !linkId || !bridge || !bridge.open_node_link)
            return false;
        return Boolean(bridge.open_node_link(nodeId, linkId));
    }

    function _canvasStateBridge() {
        if (!host || !host.canvasItem)
            return null;
        return host.canvasItem.canvasStateBridgeRef
            || host.canvasItem.canvasStateBridge
            || null;
    }

    function _recordRecentTextColor(color) {
        var bridge = surface._canvasCommandBridge();
        if (bridge && bridge.record_recent_text_color)
            bridge.record_recent_text_color(String(color || ""));
    }

    function _pickTextColor() {
        if (!host || !host.nodeData)
            return false;
        var bridge = surface._canvasCommandBridge();
        if (!bridge || !bridge.pick_node_property_color)
            return false;
        var color = String(
            bridge.pick_node_property_color(
                String(host.nodeData.node_id || ""),
                "text_color",
                surface.textColorValue
            ) || ""
        ).trim();
        if (!color.length)
            return false;
        surface._recordRecentTextColor(color);
        return surface._setStylePropertyIfChanged("text_color", color, false);
    }

    function _textAnnotationStylePayload() {
        return {
            "font_family": surface.fontFamilyValue,
            "font_size": surface.fontSizeValue,
            "font_weight": surface.fontWeightValue,
            "italic": surface.italicValue,
            "underline": surface.underlineValue,
            "strikeout": surface.strikeoutValue,
            "text_color": surface.explicitTextColorValue,
            "background_color": surface.backgroundColorValue,
            "horizontal_alignment": surface.horizontalAlignmentValue,
            "vertical_alignment": surface.verticalAlignmentValue,
            "wrap_mode": surface.wrapModeValue,
            "line_height": surface.lineHeightValue,
            "letter_spacing": surface.letterSpacingValue,
            "padding": surface.paddingValue,
            "opacity": Math.round(surface.opacityValue * 100)
        };
    }

    function _copyTextAnnotationStyle() {
        var bridge = surface._canvasCommandBridge();
        if (!bridge || !bridge.copy_text_annotation_style)
            return false;
        return Boolean(bridge.copy_text_annotation_style(surface._textAnnotationStylePayload()));
    }

    function _pasteTextAnnotationStyle() {
        var bridge = surface._canvasCommandBridge();
        if (!bridge || !bridge.paste_text_annotation_style)
            return false;
        var style = bridge.paste_text_annotation_style() || ({});
        return surface._applyTextAnnotationStyle(style);
    }

    function _applyTextAnnotationStyle(style) {
        if (!style || typeof style !== "object")
            return false;
        var changedPayload = {};
        var visibleChanged = false;
        var hasStyleValue = false;
        for (var i = 0; i < surface.textAnnotationStyleKeys.length; i++) {
            var key = surface.textAnnotationStyleKeys[i];
            if (style[key] === undefined)
                continue;
            hasStyleValue = true;
            var value = style[key];
            if (String(surface._rawProperty(key)) !== String(value)) {
                surface._setDraftProperty(key, value);
                visibleChanged = true;
            }
            if (String(surface._storedProperty(key)) !== String(value))
                changedPayload[key] = value;
        }
        if (!hasStyleValue)
            return false;
        if (!visibleChanged && Object.keys(changedPayload).length === 0)
            return true;
        if (Object.keys(changedPayload).length === 0)
            return true;
        return surface._commitTextAnnotationStylePayload(changedPayload);
    }

    function _commitTextAnnotationStylePayload(payload) {
        if (!host || !host.nodeData)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        surface._beginInteraction();
        var actualPayload = {};
        for (var payloadKey in payload) {
            if (!Object.prototype.hasOwnProperty.call(payload, payloadKey))
                continue;
            actualPayload[surface._actualPropertyKey(payloadKey)] = payload[payloadKey];
        }
        if (host.canvasItem && host.canvasItem.commitNodeSurfaceProperties) {
            if (host.canvasItem.commitNodeSurfaceProperties(nodeId, actualPayload || ({})))
                return true;
        }
        var committed = false;
        for (var key in payload) {
            if (!Object.prototype.hasOwnProperty.call(payload, key))
                continue;
            committed = surface._commitProperty(key, payload[key]) || committed;
        }
        return committed;
    }

    function _recentTextColors() {
        var bridge = surface._canvasStateBridge();
        var colors = bridge && bridge.graphics_recent_text_colors !== undefined
            ? bridge.graphics_recent_text_colors
            : [];
        if (!colors || colors.length === undefined)
            return [];
        var normalized = [];
        for (var i = 0; i < colors.length; i++) {
            var color = surface._colorLiteral(colors[i]);
            if (color.length > 0)
                normalized.push(color);
        }
        return normalized;
    }

    function _colorLiteral(value) {
        var text = String(value || "").trim();
        return /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(text) ? text.toUpperCase() : "";
    }

    function _fontFamilyToolbarText() {
        var label = FontFamilyOptions.displayName(surface.fontFamilyValue);
        return label.length > 14 ? label.substring(0, 13) + "..." : label;
    }

    function _fontFamilyActions() {
        var actions = [
            {
                "id": "text_font_family_clear",
                "label": FontFamilyOptions.DEFAULT_FONT_FAMILY_LABEL,
                "toolbar_text": FontFamilyOptions.DEFAULT_FONT_FAMILY_LABEL,
                "font_family": "",
                "kind": "surface",
                "checked": surface.fontFamilyValue.length === 0,
                "close_popover": true
            }
        ];
        var families = FontFamilyOptions.fontFamilies();
        for (var index = 0; index < families.length; index++) {
            var family = families[index];
            actions.push({
                "id": "text_font_family_set:" + FontFamilyOptions.encodeFamily(family),
                "label": family,
                "toolbar_text": family,
                "font_family": family,
                "kind": "surface",
                "checked": family === surface.fontFamilyValue,
                "close_popover": true
            });
        }
        return actions;
    }

    function _surfaceActions() {
        var styleActive = surface.isBoldWeight
            || surface.italicValue
            || surface.underlineValue
            || surface.strikeoutValue;
        var colorActions = [
            {
                "id": "text_pick_color",
                "label": "Pick text color",
                "icon": "color-picker",
                "kind": "surface",
                "foreground_color": surface.textColorValue,
                "accent_color": surface.textColorValue
            }
        ];
        var colors = surface._recentTextColors();
        for (var i = 0; i < Math.min(colors.length, 12); i++) {
            colorActions.push({
                "id": "text_color_recent:" + colors[i],
                "label": colors[i],
                "icon": "circle-filled",
                "kind": "surface",
                "foreground_color": colors[i],
                "accent_color": colors[i],
                "close_popover": true
            });
        }
        var actions = [
            {
                "id": "text_font_size_group",
                "label": "Text size",
                "kind": "surface",
                "toolbar_text": String(surface.fontSizeValue),
                "popover_layout": "font_size",
                "font_size_value": surface.fontSizeValue,
                "font_size_min": surface.fontSizeMinimum,
                "font_size_max": surface.fontSizeMaximum,
                "font_size_set_action_prefix": "text_font_size_set:",
                "font_size_preview_action_prefix": "text_font_size_preview:",
                "popoverActions": [
                    {
                        "id": "text_font_size_decrease",
                        "label": "Smaller",
                        "kind": "surface",
                        "role": "decrease",
                        "toolbar_text": "-"
                    },
                    {
                        "id": "text_font_size_increase",
                        "label": "Larger",
                        "kind": "surface",
                        "role": "increase",
                        "toolbar_text": "+"
                    }
                ]
            },
            {
                "id": "text_font_family_group",
                "label": "Font family",
                "kind": "surface",
                "toolbar_text": surface._fontFamilyToolbarText(),
                "popover_layout": "font_family",
                "popoverActions": surface._fontFamilyActions()
            },
            {
                "id": "text_style_group",
                "label": "Text style",
                "kind": "surface",
                "icon": "format-bold-italic",
                "checked": styleActive,
                "popover_layout": "row",
                "popoverActions": [
                    {
                        "id": "text_toggle_bold",
                        "label": "Bold",
                        "icon": "format-bold",
                        "kind": "surface",
                        "checked": surface.isBoldWeight
                    },
                    {
                        "id": "text_toggle_italic",
                        "label": "Italic",
                        "icon": "format-italic",
                        "kind": "surface",
                        "checked": surface.italicValue
                    },
                    {
                        "id": "text_toggle_underline",
                        "label": "Underline",
                        "icon": "format-underline",
                        "kind": "surface",
                        "checked": surface.underlineValue
                    },
                    {
                        "id": "text_toggle_strikeout",
                        "label": "Strikeout",
                        "icon": "format-strikethrough",
                        "kind": "surface",
                        "checked": surface.strikeoutValue
                    },
                    {
                        "id": "text_toggle_bullet_list",
                        "label": "Bulleted list",
                        "icon": "format-list-bulleted",
                        "kind": "surface",
                        "checked": surface.bulletListActive
                    },
                    {
                        "id": "text_toggle_numbered_list",
                        "label": "Numbered list",
                        "icon": "format-list-numbered",
                        "kind": "surface",
                        "checked": surface.numberedListActive
                    }
                ]
            },
            {
                "id": "text_alignment_group",
                "label": surface._alignmentLabel(),
                "icon": surface._alignmentIcon(),
                "kind": "surface",
                "popover_layout": "row",
                "popoverActions": [
                    {
                        "id": "text_align_left",
                        "label": "Align left",
                        "icon": "format-align-left",
                        "kind": "surface",
                        "checked": surface.horizontalAlignmentValue === "left",
                        "close_popover": true
                    },
                    {
                        "id": "text_align_center",
                        "label": "Align center",
                        "icon": "format-align-center",
                        "kind": "surface",
                        "checked": surface.horizontalAlignmentValue === "center",
                        "close_popover": true
                    },
                    {
                        "id": "text_align_right",
                        "label": "Align right",
                        "icon": "format-align-right",
                        "kind": "surface",
                        "checked": surface.horizontalAlignmentValue === "right",
                        "close_popover": true
                    },
                    {
                        "id": "text_align_justify",
                        "label": "Justify",
                        "icon": "format-align-justify",
                        "kind": "surface",
                        "checked": surface.horizontalAlignmentValue === "justify",
                        "close_popover": true
                    }
                ]
            },
            {
                "id": "text_wrap_group",
                "label": surface._wrapLabel(),
                "icon": "text-wrap",
                "kind": "surface",
                "checked": surface.wrapModeValue !== "none",
                "popover_layout": "row",
                "popoverActions": [
                    {
                        "id": "text_wrap_word",
                        "label": "Words",
                        "icon": "text-wrap",
                        "kind": "surface",
                        "checked": surface.wrapModeValue === "word",
                        "close_popover": true
                    },
                    {
                        "id": "text_wrap_anywhere",
                        "label": "Anywhere",
                        "icon": "text-wrap",
                        "kind": "surface",
                        "checked": surface.wrapModeValue === "anywhere",
                        "close_popover": true
                    },
                    {
                        "id": "text_wrap_none",
                        "label": "No wrap",
                        "icon": "text-wrap",
                        "kind": "surface",
                        "checked": surface.wrapModeValue === "none",
                        "close_popover": true
                    }
                ]
            },
            {
                "id": "text_color_group",
                "label": "Text color",
                "icon": "color-picker",
                "kind": "surface",
                "foreground_color": surface.textColorValue,
                "accent_color": surface.textColorValue,
                "popover_layout": "swatches",
                "popoverActions": colorActions
            },
            {
                "id": "text_copy_style",
                "label": "Copy text style",
                "icon": "copy-text-style",
                "kind": "surface"
            },
            {
                "id": "text_paste_style",
                "label": "Paste text style",
                "icon": "paste-text-style",
                "kind": "surface"
            }
        ];
        return actions;
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "text_font_size_decrease")
            return surface._setFontSize(-1);
        if (normalized === "text_font_size_increase")
            return surface._setFontSize(1);
        if (normalized.indexOf("text_font_size_set:") === 0)
            return surface._setFontSizeAbsolute(normalized.substring("text_font_size_set:".length));
        if (normalized.indexOf("text_font_size_preview:") === 0)
            return surface._setFontSizeAbsolute(normalized.substring("text_font_size_preview:".length), false);
        if (normalized === "text_font_family_clear")
            return surface._setFontFamily("");
        if (normalized.indexOf("text_font_family_set:") === 0)
            return surface._setFontFamily(
                FontFamilyOptions.decodeFamily(normalized.substring("text_font_family_set:".length))
            );
        if (normalized === "text_style_flush")
            return surface._flushDraftCommits();
        if (normalized === "text_toggle_bold")
            return surface._toggleBold();
        if (normalized === "text_toggle_italic")
            return surface._toggleBoolProperty("italic", surface.italicValue);
        if (normalized === "text_toggle_underline")
            return surface._toggleBoolProperty("underline", surface.underlineValue);
        if (normalized === "text_toggle_strikeout")
            return surface._toggleBoolProperty("strikeout", surface.strikeoutValue);
        if (normalized === "text_toggle_bullet_list")
            return surface._toggleListMode("bullet");
        if (normalized === "text_toggle_numbered_list")
            return surface._toggleListMode("numbered");
        if (normalized === "text_align_left")
            return surface._setStylePropertyIfChanged("horizontal_alignment", "left", false);
        if (normalized === "text_align_center")
            return surface._setStylePropertyIfChanged("horizontal_alignment", "center", false);
        if (normalized === "text_align_right")
            return surface._setStylePropertyIfChanged("horizontal_alignment", "right", false);
        if (normalized === "text_align_justify")
            return surface._setStylePropertyIfChanged("horizontal_alignment", "justify", false);
        if (normalized === "text_cycle_wrap")
            return surface._cycleWrapMode();
        if (normalized === "text_wrap_word")
            return surface._setWrapMode("word");
        if (normalized === "text_wrap_anywhere")
            return surface._setWrapMode("anywhere");
        if (normalized === "text_wrap_none")
            return surface._setWrapMode("none");
        if (normalized === "text_pick_color")
            return surface._pickTextColor();
        if (normalized.indexOf("text_color_recent:") === 0) {
            var color = surface._colorLiteral(normalized.substring("text_color_recent:".length));
            if (!color.length)
                return false;
            surface._recordRecentTextColor(color);
            return surface._setStylePropertyIfChanged("text_color", color, false);
        }
        if (normalized === "text_copy_style")
            return surface._copyTextAnnotationStyle();
        if (normalized === "text_paste_style")
            return surface._pasteTextAnnotationStyle();
        return false;
    }

    function requestInlineEditAt(localX, localY) {
        if (surface.editorVisible)
            return GraphNodeHostHitTesting.pointInRect(localX, localY, editorInteractionRegion.interactiveRect);
        if (GraphNodeHostHitTesting.pointInRect(localX, localY, displayInteractionRegion.interactiveRect))
            return surface._beginTextEdit();
        return false;
    }

    function commitInlineEditFromExternalInteraction(localX, localY) {
        if (!surface.editorVisible)
            return false;
        if (GraphNodeHostHitTesting.pointInRect(localX, localY, editorInteractionRegion.interactiveRect))
            return false;
        surface._commitText(textEditor.text);
        return true;
    }

    Item {
        id: editorCompatibilityObject
        objectName: surface.editorWrapperObjectName
        visible: surface.editorVisible
        property string committedText: surface.textValue
        property alias draftText: textEditor.text
        property string propertyKey: surface.contentPropertyKey
        property var embeddedInteractiveRects: editorInteractionRegion.embeddedInteractiveRects
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: Math.max(0, surface.paddingValue - 1)
        radius: 3
        visible: surface.backgroundColorValue.length > 0
        color: visible ? Qt.alpha(surface.backgroundColorValue, surface.opacityValue) : "transparent"
        border.width: 0
    }

    Item {
        id: textBounds
        anchors.fill: parent
        anchors.margins: surface.paddingValue
        clip: true

        Text {
            id: renderedText
            objectName: surface.renderedTextObjectName
            property int effectiveRenderType: renderType
            anchors.fill: parent
            enabled: false
            visible: !surface.editorVisible && surface.textValue.length > 0
            text: surface.textValue
            textFormat: surface.formatValue === "markdown" ? Text.MarkdownText : Text.PlainText
            color: surface.textColorValue
            opacity: surface.opacityValue
            font.family: surface.resolvedFontFamily
            font.pixelSize: surface.fontSizeValue
            font.weight: surface.resolvedFontWeight
            font.italic: surface.italicValue
            font.underline: surface.underlineValue
            font.strikeout: surface.strikeoutValue
            font.letterSpacing: surface.letterSpacingValue
            antialiasing: true
            wrapMode: surface.resolvedTextWrapMode
            horizontalAlignment: surface.resolvedHorizontalAlignment
            verticalAlignment: surface.resolvedVerticalAlignment
            lineHeightMode: Text.ProportionalHeight
            lineHeight: surface.lineHeightValue
            maximumLineCount: surface.maximumLineCount > 0 ? surface.maximumLineCount : 2147483647
            elide: surface.elideMode
            renderType: surface.highQualityTextRenderType
            renderTypeQuality: surface.highQualityTextRenderQuality
        }

        Text {
            id: placeholderText
            objectName: surface.placeholderTextObjectName
            anchors.fill: parent
            enabled: false
            visible: !surface.editorVisible && surface.textValue.length === 0
                && host && (host.isSelected || host.hoverActive)
            text: surface.placeholderValue
            color: host ? Qt.alpha(host.inlineDrivenTextColor, 0.62) : "#8D98A8"
            font.family: surface.resolvedFontFamily
            font.pixelSize: surface.fontSizeValue
            font.italic: true
            antialiasing: true
            wrapMode: Text.WordWrap
            horizontalAlignment: surface.resolvedHorizontalAlignment
            verticalAlignment: surface.resolvedVerticalAlignment
            renderType: surface.highQualityTextRenderType
            renderTypeQuality: surface.highQualityTextRenderQuality
        }

        Text {
            id: editorLayoutProbe
            objectName: surface.editorLayoutProbeObjectName
            visible: false
            width: textBounds.width
            text: textEditor.text
            textFormat: Text.PlainText
            font.family: surface.resolvedFontFamily
            font.pixelSize: surface.fontSizeValue
            font.weight: surface.resolvedFontWeight
            font.italic: surface.italicValue
            font.underline: surface.underlineValue
            font.strikeout: surface.strikeoutValue
            font.letterSpacing: surface.letterSpacingValue
            wrapMode: surface.resolvedTextWrapMode
            lineHeightMode: Text.ProportionalHeight
            lineHeight: surface.lineHeightValue
        }

        TextArea {
            id: textEditor
            objectName: surface.editorObjectName
            property string propertyKey: surface.contentPropertyKey
            anchors.fill: parent
            visible: surface.editorVisible
            textFormat: TextEdit.PlainText
            wrapMode: surface.resolvedEditorWrapMode
            selectByMouse: true
            persistentSelection: true
            color: surface.textColorValue
            selectionColor: host ? Qt.alpha(host.selectedOutlineColor, 0.28) : "#6040CDFF"
            selectedTextColor: host ? host.surfaceColor : "#1b1d22"
            horizontalAlignment: surface.resolvedHorizontalAlignment
            font.family: surface.resolvedFontFamily
            font.pixelSize: surface.fontSizeValue
            font.weight: surface.resolvedFontWeight
            font.italic: surface.italicValue
            font.underline: surface.underlineValue
            font.strikeout: surface.strikeoutValue
            font.letterSpacing: surface.letterSpacingValue
            antialiasing: true
            leftPadding: 0
            rightPadding: 0
            topPadding: surface._editorVerticalPadding()
            bottomPadding: 0
            renderType: surface.editorTextRenderType
            background: Item {}

            onActiveFocusChanged: {
                if (activeFocus) {
                    surface._focusInitialized = true;
                    surface._beginInteraction();
                    if (surface.editModeAlwaysVisible)
                        surface._blurCommitEnabled = true;
                    return;
                }
                if (!surface.editorVisible || !surface._focusInitialized || !surface._blurCommitEnabled)
                    return;
                surface._commitText(text);
            }

            Keys.onPressed: function(event) {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        && (event.modifiers & Qt.ControlModifier)) {
                    surface._commitText(text);
                    event.accepted = true;
                } else if (event.key === Qt.Key_Escape) {
                    surface._cancelTextEdit();
                    event.accepted = true;
                }
            }
        }
    }

    SurfaceControls.GraphSurfaceInteractiveRegion {
        id: displayInteractionRegion
        host: surface.host
        targetItem: textBounds
        enabled: surface.localPointerTargetEnabled && !surface.editorVisible
    }

    SurfaceControls.GraphSurfaceInteractiveRegion {
        id: editorInteractionRegion
        host: surface.host
        targetItem: textEditor
        enabled: surface.editorVisible
    }

    SurfaceControls.GraphSurfaceDoubleClickTarget {
        id: displayDoubleClickTarget
        host: surface.host
        targetItem: textBounds
        enabled: surface.displayLinkPointerTargetEnabled
        hoverEnabled: surface.formatValue === "markdown"
        cursorShape: surface._hoveredCorexLinkId.length > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    Connections {
        target: displayDoubleClickTarget

        function onSingleClicked(localX, localY) {
            var linkId = surface._corexLinkIdFromHref(surface._linkHrefAt(localX, localY));
            if (linkId.length > 0 && surface._openCorexLink(linkId))
                return;
            if (surface.host && surface.host.nodeData)
                surface.host.nodeClicked(String(surface.host.nodeData.node_id || ""), false);
        }

        function onDoubleClicked(localX, localY) {
            if (surface._corexLinkIdFromHref(surface._linkHrefAt(localX, localY)).length > 0)
                return;
            surface._beginTextEdit();
        }

        function onHoverMoved(localX, localY) {
            surface._updateCorexLinkHover(localX, localY);
        }

        function onHoverExited() {
            surface._hoveredCorexLinkId = "";
            surface._scheduleCorexLinkHoverDismiss();
        }
    }
}
