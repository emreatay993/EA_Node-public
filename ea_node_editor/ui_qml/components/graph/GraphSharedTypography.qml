import QtQuick 2.15
import QtQml 2.15

QtObject {
    id: root
    objectName: "graphSharedTypography"
    readonly property int _graphLabelPixelSizeMax: 50
    readonly property int _graphNodeIconPixelSizeMax: 50
    property int graphLabelPixelSize: 10
    property int graphNodeIconPixelSize: root.graphLabelPixelSize

    readonly property int _basePixelSize: _normalizePixelSize(root.graphLabelPixelSize, root._graphLabelPixelSizeMax)

    readonly property int nodeTitlePixelSize: root._basePixelSize + 2
    readonly property int nodeTitleIconPixelSize: _normalizePixelSize(
        root.graphNodeIconPixelSize,
        root._graphNodeIconPixelSizeMax
    )
    readonly property int portLabelPixelSize: root._basePixelSize
    readonly property int elapsedFooterPixelSize: root._basePixelSize
    readonly property int inlinePropertyPixelSize: root._basePixelSize
    readonly property int inlineRowSpacing: 4
    readonly property int inlineRowHeight: Math.max(24, root.inlinePropertyPixelSize + 16)
    readonly property int inlineStackedRowHeight: root.inlineRowHeight * 2 + root.inlineRowSpacing
    readonly property int inlineSliderRowHeight: root.inlineRowHeight * 2
        + root.inlinePropertyPixelSize + root.inlineRowSpacing
    readonly property real inlineLabelAnchorOffset: root.inlineRowHeight * 0.5
    readonly property int inlineTextareaRowHeight: Math.max(96, root.inlineRowHeight * 4)
    readonly property int inlineTextareaFieldHeight: Math.max(74, root.inlineTextareaRowHeight - 30)
    readonly property int badgePixelSize: Math.max(9, root._basePixelSize - 1)
    readonly property int badgeIconPixelSize: Math.max(8, root._basePixelSize + 1)
    readonly property int edgeLabelPixelSize: root._basePixelSize + 1
    readonly property int edgePillPixelSize: root._basePixelSize + 2

    readonly property int nodeTitleFontWeight: Font.Bold
    readonly property int portLabelFontWeight: Font.Normal
    readonly property int inlinePropertyFontWeight: Font.Normal
    readonly property int badgeFontWeight: Font.Bold
    readonly property int edgeLabelFontWeight: Font.Medium
    readonly property int edgePillFontWeight: Font.DemiBold

    function _normalizePixelSize(value, maxValue) {
        var numeric = Math.round(Number(value));
        if (!isFinite(numeric))
            numeric = 10;
        return Math.max(8, Math.min(maxValue, numeric));
    }
}
