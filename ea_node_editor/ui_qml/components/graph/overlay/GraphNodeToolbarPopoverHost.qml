// Purpose: Own graph-node toolbar popover state, placement, focus, and panel controls.
// Map: feature_routes/floating_toolbar_checked_states.md
// Tests: tests/qml_quick/tst_graph_node_toolbar_popover_host.qml
// Landmarks: action popover; source storage; bookmark/font/PDF panels; draft flush

import QtQuick 2.15
import QtQuick.Controls 2.15
import "../surface_controls" as GraphSurfaceControls
import "../GraphActionPresentation.js" as GraphActionPresentation
import "../../common/TooltipCopy.js" as TooltipCopy

Item {
    id: root
    objectName: "graphNodeFloatingToolbarActionPopoverBridge"

    property Item toolbar: null
    readonly property var host: root.toolbar ? root.toolbar.host : null
    readonly property var actionList: root.toolbar ? root.toolbar.actionList : []
    readonly property bool toolbarVisible: Boolean(root.toolbar && root.toolbar.visible)
    readonly property bool flipped: Boolean(root.toolbar && root.toolbar.flipped)
    readonly property real chromeWidth: root.toolbar ? Number(root.toolbar.width || 0) : 0
    readonly property real chromeHeight: root.toolbar ? Number(root.toolbar.height || 0) : 0
    readonly property real _sizeScale: root.toolbar ? Number(root.toolbar._sizeScale || 1) : 1
    readonly property real _effectiveZoom: root.toolbar ? Number(root.toolbar._effectiveZoom || 1) : 1
    readonly property int _buttonIconSize: root.toolbar ? Number(root.toolbar._buttonIconSize || 16) : 16
    readonly property color _chromeBaseFill: root.toolbar ? root.toolbar._chromeBaseFill : "#1b1d22"
    readonly property color _chromeBaseBorder: root.toolbar ? root.toolbar._chromeBaseBorder : "#3a3d45"
    readonly property color _chromeForeground: root.toolbar ? root.toolbar._chromeForeground : "#f0f4fb"
    readonly property color _buttonHoverFillColor: root.toolbar ? root.toolbar._buttonHoverFillColor : "transparent"
    readonly property color accentColor: root.toolbar ? root.toolbar.accentColor : "#4DA8DA"
    readonly property Item actionPopoverItem: actionPopover
    readonly property bool pointerHovered: actionPopoverBridgeHoverHandler.hovered || actionPopoverHoverHandler.hovered

    visible: root.toolbarVisible && root.actionPopoverVisible && root.actionPopoverActions.length > 0
    x: Math.min(0, root.actionPopoverX)
    y: root.flipped ? root.chromeHeight : root.actionPopoverY + actionPopover.height
    width: Math.max(root.chromeWidth, root.actionPopoverX + actionPopover.width) - x
    height: 6
    z: 79

    HoverHandler {
        id: actionPopoverBridgeHoverHandler
    }

    property bool actionPopoverVisible: false
    property real actionPopoverX: 0
    property real actionPopoverY: 0
    property real _lastPositionedActionPopoverImplicitWidth: -1
    property real _lastPositionedActionPopoverImplicitHeight: -1
    property real actionPopoverAnchorCenterX: 0
    property string actionPopoverOwnerId: ""
    property string actionPopoverLayout: "row"
    property var actionPopoverActions: []
    property string actionPopoverActionKind: "surface"
    property int actionPopoverFontSizeValue: 18
    property int actionPopoverFontSizeMin: 6
    property int actionPopoverFontSizeMax: 144
    property string actionPopoverFontSizeSetActionPrefix: "text_font_size_set:"
    property string actionPopoverFontSizePreviewActionPrefix: "text_font_size_preview:"
    property bool actionPopoverFontSizeDirty: false
    property int actionPopoverPageValue: 1
    property int actionPopoverPageMin: 1
    property int actionPopoverPageMax: 1
    property string actionPopoverPageSetActionPrefix: "pdf_page_set:"
    property int actionPopoverSourceStorageIndex: 0
    property string actionPopoverFilterText: ""
    readonly property int floatingToolbarPrimaryLevel: 1
    readonly property int floatingToolbarPopoverLevel: 2
    readonly property int floatingToolbarNestedPopoverLevel: 3
    readonly property int _popoverControlHeight: root._floatingToolbarControlHeight(root.floatingToolbarPopoverLevel)
    readonly property int _popoverIconSize: root._floatingToolbarIconSize(root.floatingToolbarPopoverLevel)
    readonly property int _popoverTextPixelSize: root._floatingToolbarTextPixelSize(root.floatingToolbarPopoverLevel)
    readonly property int _popoverHorizontalPadding: root._floatingToolbarHorizontalPadding(root.floatingToolbarPopoverLevel)
    readonly property int _popoverIconOnlyHorizontalPadding: root._floatingToolbarIconOnlyHorizontalPadding(root.floatingToolbarPopoverLevel)
    readonly property int _popoverVerticalPadding: root._floatingToolbarVerticalPadding(root.floatingToolbarPopoverLevel)
    readonly property int _popoverRadius: root._floatingToolbarRadius(root.floatingToolbarPopoverLevel)

    function _refreshActionPopoverActions() {
        if (!root.actionPopoverVisible)
            return false;
        var action = GraphActionPresentation.findAction(root.actionList, root.actionPopoverOwnerId);
        var popoverActions = GraphActionPresentation.childActions(action, "popoverActions");
        if (!popoverActions.length)
            return false;
        root.actionPopoverActions = popoverActions;
        root.actionPopoverActionKind = String(action && action.kind !== undefined
            ? action.kind
            : root.actionPopoverActionKind);
        root.actionPopoverSourceStorageIndex = GraphActionPresentation.checkedActionIndex(popoverActions);
        root._positionActionPopover();
        Qt.callLater(root._positionActionPopover);
        return true;
    }

    function _dispatchSourceStorageSelection(index) {
        var action = GraphActionPresentation.boundedActionAt(root.actionPopoverActions, index);
        if (!action)
            return false;
        return root._dispatchPopoverAction(action);
    }

    function _floatingToolbarDepth(level) {
        var numeric = Math.round(Number(level));
        return isFinite(numeric) && numeric > 0 ? numeric : root.floatingToolbarPrimaryLevel;
    }

    function _floatingToolbarControlHeight(level) {
        var depth = root._floatingToolbarDepth(level);
        var baseVerticalPadding = Math.max(6, Math.round(8 * root._sizeScale));
        var baseHeight = Math.max(24, Math.round(root._buttonIconSize + baseVerticalPadding));
        var step = Math.max(1, Math.round(2 * root._sizeScale));
        return Math.max(22, baseHeight - Math.max(0, depth - root.floatingToolbarPrimaryLevel) * step);
    }

    function _floatingToolbarIconSize(level) {
        var depth = root._floatingToolbarDepth(level);
        var step = Math.max(1, Math.round(2 * root._sizeScale));
        return Math.max(12, root._buttonIconSize - Math.max(0, depth - root.floatingToolbarPrimaryLevel) * step);
    }

    function _floatingToolbarTextPixelSize(level) {
        var depth = root._floatingToolbarDepth(level);
        var baseSize = Math.max(11, Math.round(13 * root._sizeScale));
        var step = Math.max(1, Math.round(1 * root._sizeScale));
        return Math.max(10, baseSize - Math.max(0, depth - root.floatingToolbarPrimaryLevel) * step);
    }

    function _floatingToolbarHorizontalPadding(level) {
        var depth = root._floatingToolbarDepth(level);
        return Math.max(5, Math.round(7 * root._sizeScale) - Math.max(0, depth - root.floatingToolbarPrimaryLevel));
    }

    function _floatingToolbarIconOnlyHorizontalPadding(level) {
        var depth = root._floatingToolbarDepth(level);
        return Math.max(4, Math.round(5 * root._sizeScale) - Math.max(0, depth - root.floatingToolbarPrimaryLevel));
    }

    function _floatingToolbarVerticalPadding(level) {
        var controlHeight = root._floatingToolbarControlHeight(level);
        var iconSize = root._floatingToolbarIconSize(level);
        return Math.max(2, Math.floor((controlHeight - iconSize) * 0.5));
    }

    function _floatingToolbarRadius(level) {
        var depth = root._floatingToolbarDepth(level);
        return Math.max(4, Math.round(6 * root._sizeScale) - Math.max(0, depth - root.floatingToolbarPrimaryLevel));
    }

    function _boundedInteger(value, minimum, maximum, fallback) {
        var minValue = Math.round(Number(minimum));
        var maxValue = Math.round(Number(maximum));
        if (!isFinite(minValue))
            minValue = 0;
        if (!isFinite(maxValue) || maxValue < minValue)
            maxValue = minValue;
        var numeric = Math.round(Number(value));
        if (!isFinite(numeric))
            numeric = Math.round(Number(fallback));
        if (!isFinite(numeric))
            numeric = minValue;
        return Math.max(minValue, Math.min(maxValue, numeric));
    }

    function _sanitizeIntegerText(value) {
        return String(value === undefined || value === null ? "" : value).replace(/[^0-9]/g, "");
    }

    function _flushActionPopoverDraft() {
        if (root.actionPopoverActionKind === "surface"
                && root.host
                && root.host.dispatchSurfaceAction)
            root.host.dispatchSurfaceAction("text_style_flush");
    }

    function _closeActionPopover(flushDraft) {
        if (Boolean(flushDraft))
            root._flushActionPopoverDraft();
        root.actionPopoverVisible = false;
        root.actionPopoverFontSizeDirty = false;
        root.actionPopoverFilterText = "";
        root._lastPositionedActionPopoverImplicitWidth = -1;
        root._lastPositionedActionPopoverImplicitHeight = -1;
    }

    function _previewFontSizeValue(value) {
        var nextSize = root._boundedInteger(
            value,
            root.actionPopoverFontSizeMin,
            root.actionPopoverFontSizeMax,
            root.actionPopoverFontSizeValue
        );
        root.actionPopoverFontSizeValue = nextSize;
        root._syncFontSizeEditor(true);
        root.actionPopoverFontSizeDirty = true;
        return root.toolbar._dispatchToolbarAction({
            "id": root.actionPopoverFontSizePreviewActionPrefix + String(nextSize),
            "kind": root.actionPopoverActionKind || "surface"
        });
    }

    function _commitFontSizeValue(value) {
        var nextSize = root._boundedInteger(
            value,
            root.actionPopoverFontSizeMin,
            root.actionPopoverFontSizeMax,
            root.actionPopoverFontSizeValue
        );
        root.actionPopoverFontSizeValue = nextSize;
        root._syncFontSizeEditor(true);
        root.actionPopoverFontSizeDirty = false;
        return root.toolbar._dispatchToolbarAction({
            "id": root.actionPopoverFontSizeSetActionPrefix + String(nextSize),
            "kind": root.actionPopoverActionKind || "surface"
        });
    }

    function _commitFontSizeText(value) {
        var cleaned = root._sanitizeIntegerText(value);
        if (cleaned.length === 0) {
            root.actionPopoverFontSizeValue = root.actionPopoverFontSizeValue;
            return false;
        }
        return root._commitFontSizeValue(Number(cleaned));
    }

    function _syncFontSizeEditor(force) {
        if (fontSizeField && (Boolean(force) || !fontSizeField.activeFocus))
            fontSizeField.text = String(root.actionPopoverFontSizeValue);
    }

    function _commitPageNumberValue(value) {
        var nextPage = root._boundedInteger(
            value,
            root.actionPopoverPageMin,
            root.actionPopoverPageMax,
            root.actionPopoverPageValue
        );
        root.actionPopoverPageValue = nextPage;
        root._syncPageNumberEditor(true);
        return root.toolbar._dispatchToolbarAction({
            "id": root.actionPopoverPageSetActionPrefix + String(nextPage),
            "kind": root.actionPopoverActionKind || "surface"
        });
    }

    function _commitPageNumberText(value) {
        var cleaned = root._sanitizeIntegerText(value);
        if (cleaned.length === 0) {
            root._syncPageNumberEditor(true);
            return false;
        }
        return root._commitPageNumberValue(Number(cleaned));
    }

    function _syncPageNumberEditor(force) {
        if (pdfPageField && (Boolean(force) || !pdfPageField.activeFocus))
            pdfPageField.text = String(root.actionPopoverPageValue);
    }

    function _positionActionPopover() {
        var popoverWidth = Math.max(1, Number(actionPopover.implicitWidth || actionPopover.width || 1));
        var popoverHeight = Math.max(1, Number(actionPopover.implicitHeight || actionPopover.height || 1));
        var edgeAllowance = 32;
        root.actionPopoverX = Math.max(
            -edgeAllowance,
            Math.min(
                root.chromeWidth - popoverWidth + edgeAllowance,
                root.actionPopoverAnchorCenterX - popoverWidth / 2
            )
        );
        root.actionPopoverY = root.flipped
            ? root.chromeHeight + 6
            : -popoverHeight - 6;
        root._lastPositionedActionPopoverImplicitWidth = popoverWidth;
        root._lastPositionedActionPopoverImplicitHeight = popoverHeight;
    }

    function _positionActionPopoverIfSizeMoved() {
        if (!root.actionPopoverVisible)
            return;
        var popoverWidth = Math.max(1, Number(actionPopover.implicitWidth || actionPopover.width || 1));
        var popoverHeight = Math.max(1, Number(actionPopover.implicitHeight || actionPopover.height || 1));
        if (root._lastPositionedActionPopoverImplicitWidth < 0
                || Math.abs(popoverWidth - root._lastPositionedActionPopoverImplicitWidth) >= 0.5
                || Math.abs(popoverHeight - root._lastPositionedActionPopoverImplicitHeight) >= 0.5) {
            root._positionActionPopover();
        }
    }

    function openActionPopover(action, anchorItem) {
        var popoverActions = GraphActionPresentation.childActions(action, "popoverActions");
        if (!popoverActions.length || !anchorItem)
            return;
        var ownerId = String(action && action.id !== undefined ? action.id : "");
        if (root.actionPopoverVisible && root.actionPopoverOwnerId === ownerId) {
            root._closeActionPopover(true);
            return;
        }
        if (root.toolbar)
            root.toolbar.runMenuVisible = false;
        root.actionPopoverOwnerId = ownerId;
        root.actionPopoverLayout = String(action && action.popover_layout !== undefined
            ? action.popover_layout
            : "row");
        root.actionPopoverActions = popoverActions;
        root.actionPopoverActionKind = String(action && action.kind !== undefined ? action.kind : "surface");
        root.actionPopoverFontSizeMin = root._boundedInteger(
            action && action.font_size_min !== undefined ? action.font_size_min : 6,
            1,
            999,
            6
        );
        root.actionPopoverFontSizeMax = root._boundedInteger(
            action && action.font_size_max !== undefined ? action.font_size_max : 144,
            root.actionPopoverFontSizeMin,
            999,
            144
        );
        root.actionPopoverFontSizeValue = root._boundedInteger(
            action && action.font_size_value !== undefined ? action.font_size_value : root.actionPopoverFontSizeValue,
            root.actionPopoverFontSizeMin,
            root.actionPopoverFontSizeMax,
            root.actionPopoverFontSizeMin
        );
        root.actionPopoverFontSizeSetActionPrefix = String(
            action && action.font_size_set_action_prefix !== undefined
                ? action.font_size_set_action_prefix
                : "text_font_size_set:"
        );
        root.actionPopoverFontSizePreviewActionPrefix = String(
            action && action.font_size_preview_action_prefix !== undefined
                ? action.font_size_preview_action_prefix
                : "text_font_size_preview:"
        );
        root.actionPopoverPageMin = root._boundedInteger(
            action && action.page_min !== undefined ? action.page_min : 1,
            1,
            99999,
            1
        );
        root.actionPopoverPageMax = root._boundedInteger(
            action && action.page_max !== undefined ? action.page_max : root.actionPopoverPageMin,
            root.actionPopoverPageMin,
            99999,
            root.actionPopoverPageMin
        );
        root.actionPopoverPageValue = root._boundedInteger(
            action && action.page_value !== undefined ? action.page_value : root.actionPopoverPageValue,
            root.actionPopoverPageMin,
            root.actionPopoverPageMax,
            root.actionPopoverPageMin
        );
        root.actionPopoverPageSetActionPrefix = String(
            action && action.page_set_action_prefix !== undefined
                ? action.page_set_action_prefix
                : "pdf_page_set:"
        );
        root.actionPopoverSourceStorageIndex = GraphActionPresentation.checkedActionIndex(popoverActions);
        root.actionPopoverFontSizeDirty = false;
        root.actionPopoverFilterText = "";
        var anchor = anchorItem.mapToItem(root.toolbar, anchorItem.width / 2, 0);
        root.actionPopoverAnchorCenterX = anchor.x;
        root.actionPopoverVisible = true;
        root._positionActionPopover();
        Qt.callLater(root._positionActionPopover);
        Qt.callLater(root._syncFontSizeEditor);
        Qt.callLater(root._syncPageNumberEditor);
        if (root.actionPopoverLayout === "font_family")
            Qt.callLater(function() {
                if (fontFamilySearchField)
                    fontFamilySearchField.forceActiveFocus();
            });
    }

    function _dispatchPopoverAction(action) {
        var dispatched = root.toolbar._dispatchToolbarAction(action);
        if (Boolean(action && action.close_popover)) {
            root._closeActionPopover(true);
        } else {
            Qt.callLater(root._refreshActionPopoverActions);
        }
        return dispatched;
    }

    onActionListChanged: root._refreshActionPopoverActions()

    Rectangle {
        id: actionPopover
        objectName: "graphNodeFloatingToolbarActionPopover"
        visible: root.toolbarVisible && root.actionPopoverVisible && root.actionPopoverActions.length > 0
        x: root.actionPopoverX - root.x
        y: root.actionPopoverY - root.y
        z: 80
        radius: 14
        antialiasing: true
        color: Qt.alpha(root._chromeBaseFill, 0.98)
        border.width: 1
        border.color: Qt.alpha(root._chromeBaseBorder, 0.72)

        readonly property real innerPadding: Math.round(6 * root._sizeScale)

        implicitWidth: actionPopoverContent.implicitWidth + innerPadding * 2
        implicitHeight: actionPopoverContent.implicitHeight + innerPadding * 2
        width: implicitWidth
        height: implicitHeight

        onImplicitWidthChanged: {
            root._positionActionPopoverIfSizeMoved();
        }
        onImplicitHeightChanged: {
            root._positionActionPopoverIfSizeMoved();
        }

        HoverHandler {
            id: actionPopoverHoverHandler
        }

        Item {
            id: actionPopoverContent
            anchors.centerIn: parent
            implicitWidth: root.actionPopoverLayout === "font_size"
                ? fontSizePopoverPanel.implicitWidth
                : (root.actionPopoverLayout === "font_family"
                    ? fontFamilyPopoverPanel.preferredWidth
                    : (root.actionPopoverLayout === "pdf_page"
                        ? pdfPagePopoverPanel.implicitWidth
                        : (root.actionPopoverLayout === "source_storage"
                            ? sourceStoragePopoverPanel.implicitWidth
                            : (root.actionPopoverLayout === "video_bookmarks"
                                ? videoBookmarksPopoverPanel.implicitWidth
                                : actionPopoverRow.implicitWidth))))
            implicitHeight: root.actionPopoverLayout === "font_size"
                ? fontSizePopoverPanel.implicitHeight
                : (root.actionPopoverLayout === "font_family"
                    ? fontFamilyPopoverPanel.preferredHeight
                    : (root.actionPopoverLayout === "pdf_page"
                        ? pdfPagePopoverPanel.implicitHeight
                        : (root.actionPopoverLayout === "source_storage"
                            ? sourceStoragePopoverPanel.implicitHeight
                            : (root.actionPopoverLayout === "video_bookmarks"
                                ? videoBookmarksPopoverPanel.implicitHeight
                                : actionPopoverRow.implicitHeight))))

            Row {
                id: actionPopoverRow
                visible: root.actionPopoverLayout !== "font_size"
                    && root.actionPopoverLayout !== "font_family"
                    && root.actionPopoverLayout !== "pdf_page"
                    && root.actionPopoverLayout !== "source_storage"
                    && root.actionPopoverLayout !== "video_bookmarks"
                anchors.centerIn: parent
                spacing: root._popoverIconOnlyHorizontalPadding

                Repeater {
                    model: root.actionPopoverLayout === "font_size"
                        || root.actionPopoverLayout === "font_family"
                        || root.actionPopoverLayout === "pdf_page"
                        || root.actionPopoverLayout === "source_storage"
                        || root.actionPopoverLayout === "video_bookmarks"
                        ? []
                        : root.actionPopoverActions

                    GraphSurfaceControls.GraphSurfaceButton {
                        id: popoverActionButton
                        objectName: "graphNodeFloatingToolbarPopoverAction_" + String(modelData.id || "")
                        host: root.host
                        text: GraphActionPresentation.actionToolbarText(modelData)
                        iconName: GraphActionPresentation.actionToolbarIcon(modelData)
                        iconOnly: GraphActionPresentation.actionIconOnly(modelData)
                        iconSize: root._popoverIconSize
                        controlHeight: root._popoverControlHeight
                        chromeRadius: root._popoverRadius
                        contentVerticalPadding: root._popoverVerticalPadding
                        iconSourceResolver: function(name, size, color) {
                            return root.toolbar._iconSource(name, size, color);
                        }
                        accentColor: root.toolbar._actionColor(modelData, "accent_color", root.accentColor)
                        foregroundColor: root.toolbar._actionColor(modelData, "foreground_color", root._chromeForeground)
                        enabled: modelData.enabled !== false
                        active: GraphActionPresentation.actionChecked(modelData)
                        contentHorizontalPadding: GraphActionPresentation.actionIconOnly(modelData)
                            ? root._popoverIconOnlyHorizontalPadding
                            : root._popoverHorizontalPadding
                        tooltipText: GraphActionPresentation.actionTooltipText(modelData)
                        tooltipCategory: "general"
                        tooltipScreenStablePositioning: true
                        tooltipAnchorScale: root._effectiveZoom
                        tooltipScreenGap: 8
                        tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                        baseFillColor: "transparent"
                        baseBorderColor: "transparent"
                        hoverFillColor: root._buttonHoverFillColor
                        hoverBorderColor: root._buttonHoverFillColor
                        activeFillColor: Qt.alpha(root.accentColor, 0.30)
                        activeBorderColor: Qt.alpha(root.accentColor, 0.82)
                        hoverBorderWidth: 1
                        focusPolicy: Qt.TabFocus
                        onControlStarted: {
                            if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                        }
                        onClicked: root._dispatchPopoverAction(modelData)
                        Keys.onReturnPressed: popoverActionButton.clicked()
                        Keys.onEnterPressed: popoverActionButton.clicked()
                    }
                }
            }

            Row {
                id: sourceStoragePopoverPanel
                objectName: "graphNodeFloatingToolbarSourceStoragePanel"
                visible: root.actionPopoverLayout === "source_storage"
                anchors.centerIn: parent
                spacing: root._popoverHorizontalPadding

                GraphSurfaceControls.GraphSurfaceComboBox {
                    id: sourceStorageCombo
                    controlHeight: root._popoverControlHeight
                    controlRadius: root._popoverRadius
                    contentLeftPadding: root._popoverHorizontalPadding
                    contentRightPadding: Math.max(20, root._popoverHorizontalPadding + 14)
                    indicatorRightMargin: root._popoverHorizontalPadding
                    popupControlHeight: root._floatingToolbarControlHeight(root.floatingToolbarNestedPopoverLevel)
                    objectName: "graphNodeFloatingToolbarSourceStorageCombo"
                    host: root.host
                    width: Math.round(112 * root._sizeScale)
                    height: root._popoverControlHeight
                    model: GraphActionPresentation.actionLabels(root.actionPopoverActions)
                    currentIndex: root.actionPopoverSourceStorageIndex
                    enabled: root.actionPopoverActions.length > 1
                    font.pixelSize: root._popoverTextPixelSize
                    font.weight: Font.DemiBold
                    fillColor: Qt.alpha(root._chromeForeground, 0.10)
                    borderColor: Qt.alpha(root._chromeForeground, 0.20)
                    focusBorderColor: root.accentColor
                    accentColor: root.accentColor
                    textColor: root._chromeForeground
                    popupFillColor: root._chromeBaseFill
                    popupBorderColor: Qt.alpha(root._chromeBaseBorder, 0.82)
                    onControlStarted: {
                        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                    }
                    onActivated: root.actionPopoverSourceStorageIndex = currentIndex
                }

                GraphSurfaceControls.GraphSurfaceButton {
                    id: sourceStorageBrowseButton
                    objectName: "graphNodeFloatingToolbarSourceBrowseButton"
                    host: root.host
                    text: "Browse"
                    iconName: "folder-open"
                    iconOnly: false
                    iconSize: root._popoverIconSize
                    controlHeight: root._popoverControlHeight
                    chromeRadius: root._popoverRadius
                    contentVerticalPadding: root._popoverVerticalPadding
                    font.pixelSize: root._popoverTextPixelSize
                    iconSourceResolver: function(name, size, color) {
                        return root.toolbar._iconSource(name, size, color);
                    }
                    accentColor: root.accentColor
                    foregroundColor: root._chromeForeground
                    enabled: GraphActionPresentation.boundedActionAt(root.actionPopoverActions, sourceStorageCombo.currentIndex) !== null
                        && GraphActionPresentation.boundedActionAt(root.actionPopoverActions, sourceStorageCombo.currentIndex).enabled !== false
                    contentHorizontalPadding: root._popoverHorizontalPadding
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.source.choose_file")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.source.choose_file")
                    tooltipScreenStablePositioning: true
                    tooltipAnchorScale: root._effectiveZoom
                    tooltipScreenGap: 8
                    tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                    baseFillColor: "transparent"
                    baseBorderColor: "transparent"
                    hoverFillColor: root._buttonHoverFillColor
                    hoverBorderColor: root._buttonHoverFillColor
                    hoverBorderWidth: 1
                    focusPolicy: Qt.TabFocus
                    onControlStarted: {
                        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                    }
                    onClicked: root._dispatchSourceStorageSelection(sourceStorageCombo.currentIndex)
                    Keys.onReturnPressed: sourceStorageBrowseButton.clicked()
                    Keys.onEnterPressed: sourceStorageBrowseButton.clicked()
                }
            }

            Item {
                id: videoBookmarksPopoverPanel
                objectName: "graphNodeFloatingToolbarVideoBookmarksPanel"
                visible: root.actionPopoverLayout === "video_bookmarks"
                anchors.centerIn: parent
                readonly property int preferredWidth: root._popoverControlHeight * 7
                    + root._popoverHorizontalPadding * 6
                readonly property int preferredHeight: root._popoverControlHeight * 7
                    + root._popoverVerticalPadding * 8
                implicitWidth: preferredWidth
                implicitHeight: Math.min(
                    preferredHeight,
                    Math.max(root._popoverControlHeight, videoBookmarkColumn.implicitHeight)
                )

                ScrollView {
                    id: videoBookmarkScroll
                    objectName: "graphNodeFloatingToolbarVideoBookmarkScroll"
                    width: videoBookmarksPopoverPanel.preferredWidth
                    height: videoBookmarksPopoverPanel.implicitHeight
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: videoBookmarkColumn.implicitHeight > height
                        ? ScrollBar.AsNeeded
                        : ScrollBar.AlwaysOff

                    Column {
                        id: videoBookmarkColumn
                        objectName: "graphNodeFloatingToolbarVideoBookmarkList"
                        width: videoBookmarkScroll.width
                        spacing: root._popoverVerticalPadding

                        Repeater {
                            model: root.actionPopoverLayout === "video_bookmarks" ? root.actionPopoverActions : []

                            Item {
                                id: videoBookmarkDelegate
                                readonly property var actionData: modelData || ({})
                                readonly property bool addRow: String(actionData.role || "") === "add"
                                readonly property bool bookmarkRow: String(actionData.role || "") === "bookmark"
                                width: videoBookmarkColumn.width
                                height: addRow
                                    ? addBookmarkButton.implicitHeight
                                    : Math.max(root._popoverControlHeight, bookmarkRowContent.implicitHeight)

                                GraphSurfaceControls.GraphSurfaceButton {
                                    id: addBookmarkButton
                                    objectName: "graphNodeFloatingToolbarPopoverAction_" + String(videoBookmarkDelegate.actionData.id || "")
                                    visible: videoBookmarkDelegate.addRow
                                    width: parent.width
                                    host: root.host
                                    text: GraphActionPresentation.actionToolbarText(videoBookmarkDelegate.actionData)
                                    iconName: GraphActionPresentation.actionToolbarIcon(videoBookmarkDelegate.actionData)
                                    iconOnly: false
                                    iconSize: root._popoverIconSize
                                    controlHeight: root._popoverControlHeight
                                    chromeRadius: root._popoverRadius
                                    contentVerticalPadding: root._popoverVerticalPadding
                                    font.pixelSize: root._popoverTextPixelSize
                                    iconSourceResolver: function(name, size, color) {
                                        return root.toolbar._iconSource(name, size, color);
                                    }
                                    accentColor: root.accentColor
                                    foregroundColor: root._chromeForeground
                                    enabled: videoBookmarkDelegate.actionData.enabled !== false
                                    contentHorizontalPadding: root._popoverHorizontalPadding
                                    tooltipText: String(videoBookmarkDelegate.actionData.label || "")
                                    tooltipCategory: "general"
                                    tooltipScreenStablePositioning: true
                                    tooltipAnchorScale: root._effectiveZoom
                                    tooltipScreenGap: 8
                                    tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                                    baseFillColor: Qt.alpha(root._chromeForeground, 0.08)
                                    baseBorderColor: Qt.alpha(root._chromeForeground, 0.12)
                                    hoverFillColor: root._buttonHoverFillColor
                                    hoverBorderColor: root._buttonHoverFillColor
                                    hoverBorderWidth: 1
                                    focusPolicy: Qt.TabFocus
                                    onControlStarted: {
                                        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                                    }
                                    onClicked: root._dispatchPopoverAction(videoBookmarkDelegate.actionData)
                                    Keys.onReturnPressed: addBookmarkButton.clicked()
                                    Keys.onEnterPressed: addBookmarkButton.clicked()
                                }

                                Row {
                                    id: bookmarkRowContent
                                    visible: videoBookmarkDelegate.bookmarkRow
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: root._popoverIconOnlyHorizontalPadding

                                    TextField {
                                        id: bookmarkLabelField
                                        objectName: "graphNodeFloatingToolbarVideoBookmarkLabel_" + String(videoBookmarkDelegate.actionData.bookmark_id || "")
                                        width: Math.max(82, videoBookmarkColumn.width
                                            - jumpBookmarkButton.width
                                            - deleteBookmarkButton.width
                                            - root._popoverIconOnlyHorizontalPadding * 2)
                                        height: root._popoverControlHeight
                                        text: String(videoBookmarkDelegate.actionData.label || "")
                                        placeholderText: String(videoBookmarkDelegate.actionData.time_text || "")
                                        color: root._chromeForeground
                                        placeholderTextColor: Qt.alpha(root._chromeForeground, 0.52)
                                        selectedTextColor: root._chromeForeground
                                        selectionColor: Qt.alpha(root.accentColor, 0.45)
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: root._popoverTextPixelSize
                                        selectByMouse: true
                                        background: Rectangle {
                                            radius: root._popoverRadius
                                            color: Qt.alpha(root._chromeForeground, 0.08)
                                            border.width: bookmarkLabelField.activeFocus ? 1 : 0
                                            border.color: Qt.alpha(root.accentColor, 0.72)
                                        }
                                        onEditingFinished: {
                                            var original = String(videoBookmarkDelegate.actionData.label || "");
                                            var updated = String(bookmarkLabelField.text || "").trim();
                                            if (updated.length > 0 && updated !== original) {
                                                root._dispatchPopoverAction({
                                                    "id": String(videoBookmarkDelegate.actionData.rename_action_prefix || "")
                                                        + encodeURIComponent(updated),
                                                    "kind": root.actionPopoverActionKind || "surface",
                                                    "close_popover": false
                                                });
                                            }
                                        }
                                        Keys.onEscapePressed: {
                                            bookmarkLabelField.text = String(videoBookmarkDelegate.actionData.label || "");
                                            bookmarkLabelField.focus = false;
                                        }
                                    }

                                    GraphSurfaceControls.GraphSurfaceButton {
                                        id: jumpBookmarkButton
                                        objectName: "graphNodeFloatingToolbarVideoBookmarkJump_" + String(videoBookmarkDelegate.actionData.bookmark_id || "")
                                        host: root.host
                                        text: "Jump"
                                        iconName: GraphActionPresentation.actionToolbarIcon(videoBookmarkDelegate.actionData)
                                        iconOnly: true
                                        iconSize: root._popoverIconSize
                                        controlHeight: root._popoverControlHeight
                                        chromeRadius: root._popoverRadius
                                        contentVerticalPadding: root._popoverVerticalPadding
                                        iconSourceResolver: function(name, size, color) {
                                            return root.toolbar._iconSource(name, size, color);
                                        }
                                        accentColor: root.accentColor
                                        foregroundColor: root._chromeForeground
                                        contentHorizontalPadding: root._popoverIconOnlyHorizontalPadding
                                            tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.bookmark_jump")
                                            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.video.bookmark_jump")
                                        tooltipScreenStablePositioning: true
                                        tooltipAnchorScale: root._effectiveZoom
                                        tooltipScreenGap: 8
                                        tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                                        baseFillColor: "transparent"
                                        baseBorderColor: "transparent"
                                        hoverFillColor: root._buttonHoverFillColor
                                        hoverBorderColor: root._buttonHoverFillColor
                                        hoverBorderWidth: 1
                                        focusPolicy: Qt.TabFocus
                                        onControlStarted: {
                                            if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                                root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                                        }
                                        onClicked: root._dispatchPopoverAction(videoBookmarkDelegate.actionData)
                                        Keys.onReturnPressed: jumpBookmarkButton.clicked()
                                        Keys.onEnterPressed: jumpBookmarkButton.clicked()
                                    }

                                    GraphSurfaceControls.GraphSurfaceButton {
                                        id: deleteBookmarkButton
                                        objectName: "graphNodeFloatingToolbarVideoBookmarkDelete_" + String(videoBookmarkDelegate.actionData.bookmark_id || "")
                                        host: root.host
                                        text: "Delete"
                                        iconName: "x"
                                        iconOnly: true
                                        iconSize: root._popoverIconSize
                                        controlHeight: root._popoverControlHeight
                                        chromeRadius: root._popoverRadius
                                        contentVerticalPadding: root._popoverVerticalPadding
                                        iconSourceResolver: function(name, size, color) {
                                            return root.toolbar._iconSource(name, size, color);
                                        }
                                        accentColor: "#D94F4F"
                                        foregroundColor: root._chromeForeground
                                        contentHorizontalPadding: root._popoverIconOnlyHorizontalPadding
                                            tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.bookmark_delete")
                                            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.video.bookmark_delete")
                                        tooltipScreenStablePositioning: true
                                        tooltipAnchorScale: root._effectiveZoom
                                        tooltipScreenGap: 8
                                        tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                                        baseFillColor: "transparent"
                                        baseBorderColor: "transparent"
                                        hoverFillColor: Qt.alpha("#D94F4F", 0.22)
                                        hoverBorderColor: Qt.alpha("#D94F4F", 0.42)
                                        hoverBorderWidth: 1
                                        focusPolicy: Qt.TabFocus
                                        onControlStarted: {
                                            if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                                root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                                        }
                                        onClicked: root._dispatchPopoverAction({
                                            "id": String(videoBookmarkDelegate.actionData.delete_action_id || ""),
                                            "kind": root.actionPopoverActionKind || "surface",
                                            "close_popover": false
                                        })
                                        Keys.onReturnPressed: deleteBookmarkButton.clicked()
                                        Keys.onEnterPressed: deleteBookmarkButton.clicked()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Row {
                id: fontSizePopoverPanel
                objectName: "graphNodeFloatingToolbarFontSizePanel"
                visible: root.actionPopoverLayout === "font_size"
                anchors.centerIn: parent
                spacing: root._popoverHorizontalPadding

                TextField {
                    id: fontSizeField
                    objectName: "graphNodeFloatingToolbarFontSizeField"
                    width: Math.round(56 * root._sizeScale)
                    height: root._popoverControlHeight
                    text: String(root.actionPopoverFontSizeValue)
                    color: root._chromeForeground
                    selectedTextColor: root._chromeForeground
                    selectionColor: Qt.alpha(root.accentColor, 0.45)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: Math.max(root._popoverTextPixelSize, root._popoverIconSize)
                    font.weight: Font.DemiBold
                    selectByMouse: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator {
                        bottom: root.actionPopoverFontSizeMin
                        top: root.actionPopoverFontSizeMax
                    }
                    background: Rectangle {
                        radius: root._popoverRadius
                        color: Qt.alpha(root._chromeForeground, 0.10)
                        border.width: fontSizeField.activeFocus ? 1 : 0
                        border.color: Qt.alpha(root.accentColor, 0.72)
                    }
                    onTextEdited: {
                        var cleaned = root._sanitizeIntegerText(fontSizeField.text);
                        if (cleaned !== fontSizeField.text) {
                            var nextCursor = Math.min(cleaned.length, fontSizeField.cursorPosition);
                            fontSizeField.text = cleaned;
                            fontSizeField.cursorPosition = nextCursor;
                        }
                    }
                    onActiveFocusChanged: {
                        if (!fontSizeField.activeFocus)
                            root._commitFontSizeText(fontSizeField.text);
                    }
                    Keys.onReturnPressed: {
                        root._commitFontSizeText(fontSizeField.text);
                        fontSizeField.selectAll();
                    }
                    Keys.onEnterPressed: {
                        root._commitFontSizeText(fontSizeField.text);
                        fontSizeField.selectAll();
                    }
                    Keys.onEscapePressed: {
                        fontSizeField.text = String(root.actionPopoverFontSizeValue);
                        fontSizeField.focus = false;
                    }
                }

                Slider {
                    id: fontSizeSlider
                    objectName: "graphNodeFloatingToolbarFontSizeSlider"
                    width: Math.round(240 * root._sizeScale)
                    height: root._popoverControlHeight
                    from: root.actionPopoverFontSizeMin
                    to: root.actionPopoverFontSizeMax
                    value: root.actionPopoverFontSizeValue
                    stepSize: 1
                    snapMode: Slider.SnapAlways
                    live: true
                    onMoved: root._previewFontSizeValue(Math.round(fontSizeSlider.value))
                    onPressedChanged: {
                        if (!fontSizeSlider.pressed && root.actionPopoverFontSizeDirty)
                            root._commitFontSizeValue(Math.round(fontSizeSlider.value));
                    }
                    background: Rectangle {
                        x: fontSizeSlider.leftPadding
                        y: fontSizeSlider.topPadding + fontSizeSlider.availableHeight / 2 - height / 2
                        width: fontSizeSlider.availableWidth
                        height: Math.max(3, root._floatingToolbarVerticalPadding(root.floatingToolbarNestedPopoverLevel))
                        radius: height / 2
                        color: Qt.alpha(root._chromeForeground, 0.30)

                        Rectangle {
                            width: fontSizeSlider.visualPosition * parent.width
                            height: parent.height
                            radius: parent.radius
                            color: Qt.alpha(root.accentColor, 0.92)
                        }
                    }
                    handle: Rectangle {
                        x: fontSizeSlider.leftPadding
                            + fontSizeSlider.visualPosition * (fontSizeSlider.availableWidth - width)
                        y: fontSizeSlider.topPadding
                            + fontSizeSlider.availableHeight / 2 - height / 2
                        width: root._popoverIconSize
                        height: width
                        radius: width / 2
                        antialiasing: true
                        color: root.accentColor
                        border.width: Math.max(1, Math.round(1 * root._sizeScale))
                        border.color: root._chromeForeground
                    }
                }

                Rectangle {
                    id: fontSizeStepper
                    objectName: "graphNodeFloatingToolbarFontSizeStepper"
                    radius: root._popoverRadius
                    color: "transparent"
                    border.width: 1
                    border.color: Qt.alpha(root._chromeForeground, 0.14)
                    implicitWidth: fontSizeStepperRow.implicitWidth + root._popoverVerticalPadding
                    implicitHeight: Math.max(root._popoverControlHeight, fontSizeStepperRow.implicitHeight)

                    Row {
                        id: fontSizeStepperRow
                        anchors.centerIn: parent
                        spacing: 0

                        Repeater {
                            model: root.actionPopoverLayout === "font_size" ? root.actionPopoverActions : []

                            GraphSurfaceControls.GraphSurfaceButton {
                                id: fontSizeStepButton
                                objectName: "graphNodeFloatingToolbarPopoverAction_" + String(modelData.id || "")
                                host: root.host
                                text: GraphActionPresentation.actionToolbarText(modelData)
                                iconName: GraphActionPresentation.actionToolbarIcon(modelData)
                                iconOnly: false
                                iconSize: root._popoverIconSize
                                controlHeight: root._popoverControlHeight
                                iconSourceResolver: function(name, size, color) {
                                    return root.toolbar._iconSource(name, size, color);
                                }
                                accentColor: root.accentColor
                                foregroundColor: root._chromeForeground
                                enabled: modelData.enabled !== false
                                chromeRadius: root._popoverRadius
                                contentHorizontalPadding: root._popoverHorizontalPadding
                                contentVerticalPadding: root._popoverVerticalPadding
                                font.pixelSize: root._popoverTextPixelSize
                                tooltipText: GraphActionPresentation.actionTooltipText(modelData)
                                tooltipCategory: "general"
                                tooltipScreenStablePositioning: true
                                tooltipAnchorScale: root._effectiveZoom
                                tooltipScreenGap: 8
                                tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                                baseFillColor: "transparent"
                                baseBorderColor: "transparent"
                                hoverFillColor: root._buttonHoverFillColor
                                hoverBorderColor: root._buttonHoverFillColor
                                hoverBorderWidth: 1
                                focusPolicy: Qt.TabFocus
                                onControlStarted: {
                                    if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                        root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                                }
                                onClicked: root._dispatchPopoverAction(modelData)
                                Keys.onReturnPressed: fontSizeStepButton.clicked()
                                Keys.onEnterPressed: fontSizeStepButton.clicked()
                            }
                        }
                    }
                }
            }

            Row {
                id: pdfPagePopoverPanel
                objectName: "graphNodeFloatingToolbarPdfPagePanel"
                visible: root.actionPopoverLayout === "pdf_page"
                anchors.centerIn: parent
                spacing: Math.round(8 * root._sizeScale)

                readonly property var previousAction: GraphActionPresentation.findAction(root.actionPopoverActions, "pdf_page_previous") || ({})
                readonly property var nextAction: GraphActionPresentation.findAction(root.actionPopoverActions, "pdf_page_next") || ({})

                GraphSurfaceControls.GraphSurfaceButton {
                    id: pdfPreviousButton
                    objectName: "graphNodeFloatingToolbarPopoverAction_pdf_page_previous"
                    host: root.host
                    text: ""
                    iconName: GraphActionPresentation.actionToolbarIcon(pdfPagePopoverPanel.previousAction)
                    iconOnly: true
                    iconSize: root._popoverIconSize
                        controlHeight: root._popoverControlHeight
                        chromeRadius: root._popoverRadius
                        contentVerticalPadding: root._popoverVerticalPadding
                    iconSourceResolver: function(name, size, color) {
                        return root.toolbar._iconSource(name, size, color);
                    }
                    accentColor: root.accentColor
                    foregroundColor: root._chromeForeground
                    enabled: root.actionPopoverPageValue > root.actionPopoverPageMin
                    contentHorizontalPadding: root._popoverIconOnlyHorizontalPadding
                    tooltipText: String(pdfPagePopoverPanel.previousAction.label || TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.previous_page_short"))
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.pdf.previous_page_short")
                    tooltipScreenStablePositioning: true
                    tooltipAnchorScale: root._effectiveZoom
                    tooltipScreenGap: 8
                    tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                    baseFillColor: "transparent"
                    baseBorderColor: "transparent"
                    hoverFillColor: root._buttonHoverFillColor
                    hoverBorderColor: root._buttonHoverFillColor
                    hoverBorderWidth: 1
                    focusPolicy: Qt.TabFocus
                    onControlStarted: {
                        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                    }
                    onClicked: root._commitPageNumberValue(root.actionPopoverPageValue - 1)
                    Keys.onReturnPressed: pdfPreviousButton.clicked()
                    Keys.onEnterPressed: pdfPreviousButton.clicked()
                }

                TextField {
                    id: pdfPageField
                    objectName: "graphNodeFloatingToolbarPdfPageField"
                    width: Math.round(58 * root._sizeScale)
                    height: root._popoverControlHeight
                    text: String(root.actionPopoverPageValue)
                    color: root._chromeForeground
                    selectedTextColor: root._chromeForeground
                    selectionColor: Qt.alpha(root.accentColor, 0.45)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: Math.max(root._popoverTextPixelSize, root._popoverIconSize)
                    font.weight: Font.DemiBold
                    selectByMouse: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator {
                        bottom: root.actionPopoverPageMin
                        top: root.actionPopoverPageMax
                    }
                    background: Rectangle {
                        radius: root._popoverRadius
                        color: Qt.alpha(root._chromeForeground, 0.10)
                        border.width: pdfPageField.activeFocus ? 1 : 0
                        border.color: Qt.alpha(root.accentColor, 0.72)
                    }
                    onTextEdited: {
                        var cleaned = root._sanitizeIntegerText(pdfPageField.text);
                        if (cleaned !== pdfPageField.text) {
                            var nextCursor = Math.min(cleaned.length, pdfPageField.cursorPosition);
                            pdfPageField.text = cleaned;
                            pdfPageField.cursorPosition = nextCursor;
                        }
                    }
                    onActiveFocusChanged: {
                        if (!pdfPageField.activeFocus)
                            root._commitPageNumberText(pdfPageField.text);
                    }
                    Keys.onReturnPressed: {
                        root._commitPageNumberText(pdfPageField.text);
                        pdfPageField.selectAll();
                    }
                    Keys.onEnterPressed: {
                        root._commitPageNumberText(pdfPageField.text);
                        pdfPageField.selectAll();
                    }
                    Keys.onEscapePressed: {
                        root._syncPageNumberEditor(true);
                        pdfPageField.focus = false;
                    }
                }

                Text {
                    objectName: "graphNodeFloatingToolbarPdfPageTotalLabel"
                    height: root._popoverControlHeight
                    text: "/ " + String(root.actionPopoverPageMax)
                    color: Qt.alpha(root._chromeForeground, 0.72)
                    font.pixelSize: root._popoverTextPixelSize
                    verticalAlignment: Text.AlignVCenter
                }

                GraphSurfaceControls.GraphSurfaceButton {
                    id: pdfNextButton
                    objectName: "graphNodeFloatingToolbarPopoverAction_pdf_page_next"
                    host: root.host
                    text: ""
                    iconName: GraphActionPresentation.actionToolbarIcon(pdfPagePopoverPanel.nextAction)
                    iconOnly: true
                    iconSize: root._popoverIconSize
                        controlHeight: root._popoverControlHeight
                        chromeRadius: root._popoverRadius
                        contentVerticalPadding: root._popoverVerticalPadding
                    iconSourceResolver: function(name, size, color) {
                        return root.toolbar._iconSource(name, size, color);
                    }
                    accentColor: root.accentColor
                    foregroundColor: root._chromeForeground
                    enabled: root.actionPopoverPageValue < root.actionPopoverPageMax
                    contentHorizontalPadding: root._popoverIconOnlyHorizontalPadding
                    tooltipText: String(pdfPagePopoverPanel.nextAction.label || TooltipCopy.text(tooltipCopyBridge, "fullscreen.pdf.next_page_short"))
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.pdf.next_page_short")
                    tooltipScreenStablePositioning: true
                    tooltipAnchorScale: root._effectiveZoom
                    tooltipScreenGap: 8
                    tooltipScreenStablePlacement: root.flipped ? "below" : "above"
                    baseFillColor: "transparent"
                    baseBorderColor: "transparent"
                    hoverFillColor: root._buttonHoverFillColor
                    hoverBorderColor: root._buttonHoverFillColor
                    hoverBorderWidth: 1
                    focusPolicy: Qt.TabFocus
                    onControlStarted: {
                        if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                            root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                    }
                    onClicked: root._commitPageNumberValue(root.actionPopoverPageValue + 1)
                    Keys.onReturnPressed: pdfNextButton.clicked()
                    Keys.onEnterPressed: pdfNextButton.clicked()
                }
            }

            Column {
                id: fontFamilyPopoverPanel
                objectName: "graphNodeFloatingToolbarFontFamilyPanel"
                visible: root.actionPopoverLayout === "font_family"
                anchors.centerIn: parent
                spacing: root._popoverVerticalPadding
                width: preferredWidth
                height: preferredHeight
                readonly property real preferredWidth: Math.round(220 * root._sizeScale)
                readonly property real preferredHeight: fontFamilySearchField.height
                    + spacing
                    + fontFamilyListFrame.height
                readonly property var filteredActions: GraphActionPresentation.filterActions(root.actionPopoverActions, root.actionPopoverFilterText)

                TextField {
                    id: fontFamilySearchField
                    objectName: "graphNodeFloatingToolbarFontFamilyField"
                    width: parent.width
                    height: root._popoverControlHeight
                    text: root.actionPopoverFilterText
                    placeholderText: "Search fonts"
                    color: root._chromeForeground
                    placeholderTextColor: Qt.alpha(root._chromeForeground, 0.58)
                    selectedTextColor: root._chromeForeground
                    selectionColor: Qt.alpha(root.accentColor, 0.45)
                    font.pixelSize: root._popoverTextPixelSize
                    selectByMouse: true
                    background: Rectangle {
                        radius: root._popoverRadius
                        color: Qt.alpha(root._chromeForeground, 0.10)
                        border.width: fontFamilySearchField.activeFocus ? 1 : 0
                        border.color: Qt.alpha(root.accentColor, 0.72)
                    }
                    onTextEdited: root.actionPopoverFilterText = fontFamilySearchField.text
                    onActiveFocusChanged: {
                        if (fontFamilySearchField.activeFocus
                                && fontFamilySearchField.text !== root.actionPopoverFilterText)
                            fontFamilySearchField.text = root.actionPopoverFilterText;
                    }
                    Keys.onDownPressed: {
                        fontFamilyList.forceActiveFocus();
                        if (fontFamilyList.currentIndex < 0 && fontFamilyPopoverPanel.filteredActions.length > 0)
                            fontFamilyList.currentIndex = 0;
                    }
                    Keys.onEscapePressed: root._closeActionPopover(true)
                    Keys.onReturnPressed: {
                        if (fontFamilyPopoverPanel.filteredActions.length > 0)
                            root._dispatchPopoverAction(fontFamilyPopoverPanel.filteredActions[0]);
                    }
                    Keys.onEnterPressed: {
                        if (fontFamilyPopoverPanel.filteredActions.length > 0)
                            root._dispatchPopoverAction(fontFamilyPopoverPanel.filteredActions[0]);
                    }
                }

                Rectangle {
                    id: fontFamilyListFrame
                    width: parent.width
                    height: preferredHeight
                    radius: root._popoverRadius
                    color: Qt.alpha(root._chromeForeground, 0.06)
                    border.width: 1
                    border.color: Qt.alpha(root._chromeForeground, 0.12)
                    readonly property real preferredHeight: Math.min(
                        fontFamilyList.contentHeight,
                        Math.round(220 * root._sizeScale)
                    )

                    ListView {
                        id: fontFamilyList
                        objectName: "graphNodeFloatingToolbarFontFamilyList"
                        anchors.fill: parent
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: fontFamilyPopoverPanel.visible ? fontFamilyPopoverPanel.filteredActions : []
                        currentIndex: GraphActionPresentation.checkedActionIndex(fontFamilyPopoverPanel.filteredActions)
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            interactive: true
                        }

                        delegate: ItemDelegate {
                            id: fontFamilyActionButton
                            objectName: "graphNodeFloatingToolbarPopoverAction_" + String(modelData.id || "")
                            width: ListView.view ? ListView.view.width : fontFamilyPopoverPanel.width
                            height: root._floatingToolbarControlHeight(root.floatingToolbarNestedPopoverLevel)
                            highlighted: ListView.isCurrentItem || GraphActionPresentation.actionChecked(modelData)

                            contentItem: Text {
                                text: String(modelData.label || "")
                                color: fontFamilyActionButton.highlighted
                                    ? root.accentColor
                                    : root._chromeForeground
                                font.pixelSize: root._floatingToolbarTextPixelSize(root.floatingToolbarNestedPopoverLevel)
                                font.family: String(modelData.font_family || "").length > 0
                                    ? String(modelData.font_family || "")
                                    : Qt.application.font.family
                                font.weight: GraphActionPresentation.actionChecked(modelData) ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }

                            background: Rectangle {
                                radius: root._floatingToolbarRadius(root.floatingToolbarNestedPopoverLevel)
                                color: fontFamilyActionButton.down
                                    ? Qt.alpha(root.accentColor, 0.26)
                                    : (fontFamilyActionButton.highlighted
                                        ? Qt.alpha(root.accentColor, 0.16)
                                        : "transparent")
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._dispatchPopoverAction(modelData)
                            }

                            onClicked: root._dispatchPopoverAction(modelData)
                            Keys.onReturnPressed: fontFamilyActionButton.clicked()
                            Keys.onEnterPressed: fontFamilyActionButton.clicked()
                        }

                        Keys.onEscapePressed: {
                            fontFamilySearchField.forceActiveFocus();
                            root._closeActionPopover(true);
                        }
                    }
                }
            }
        }
    }

}
