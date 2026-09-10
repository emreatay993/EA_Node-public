import QtQuick 2.15
import QtQuick.Controls 2.15
import "../surface_controls" as GraphSurfaceControls
import "../GraphActionPresentation.js" as GraphActionPresentation
import "../../shell" as ShellComponents
import "../surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "toolbar_positioning.js" as ToolbarPositioning
import "../../common/contrast_utils.js" as ContrastUtils
import "../../common/TooltipCopy.js" as TooltipCopy

Item {
    id: root
    objectName: "graphNodeFloatingToolbar"

    property Item host: null
    property var canvasItem: null
    property var viewBridge: null
    property var visibleSceneRectPayload: ({})

    readonly property bool hostValid: !!root.host
    readonly property var hostNodeData: root.hostValid ? root.host.nodeData : null
    readonly property bool toolbarActive: root.hostValid && Boolean(root.host.toolbarActive)
    readonly property var toolbarMetrics: {
        if (!root.hostValid)
            return ({});
        var metrics = root.host.surfaceMetrics || {};
        return metrics.floating_toolbar ? metrics.floating_toolbar : ({});
    }
    readonly property var actionList: {
        if (!root.hostValid)
            return [];
        var actions = root.host.availableActions;
        return Array.isArray(actions) ? actions : [];
    }
    // compact_pill / minimal_ghost group surface-specific buttons on the left
    // and common (rename/duplicate/delete/...) buttons on the right so the two
    // families read as distinct groups separated by a thin divider. Other styles
    // keep the source order.
    readonly property bool _groupBySurfaceFamily:
        root.style === "compact_pill" || root.style === "minimal_ghost"
    readonly property var _orderedActions: GraphActionPresentation.orderNodeToolbarActions(
        root.actionList,
        root._groupBySurfaceFamily
    )
    readonly property color _requestedAccentColor: root.hostValid ? root.host.nodeThemeColor : "#4DA8DA"
    readonly property color _shellAccentColor: (typeof themeBridge !== "undefined"
            && themeBridge
            && themeBridge.palette
            && themeBridge.palette.accent)
        ? themeBridge.palette.accent
        : "#1D8CE0"
    // Chrome colors track the host's theme / shell palette so the toolbar
    // follows both graph-theme switches (dark/light) and per-node passive
    // overrides (shell colors) instead of staying hardcoded-dark.
    readonly property color _chromeBaseFill: root.hostValid ? root.host.surfaceColor : "#1b1d22"
    readonly property color _chromeBaseBorder: root.hostValid ? root.host.outlineColor : "#3a3d45"
    readonly property color _rawHeaderText: root.hostValid ? root.host.headerTextColor : "#f0f4fb"
    // Ghost icons float on the shell's canvas_bg but headerTextColor comes from the graph theme â€” some pairs drop below WCAG 3:1, so fall back to shell app_fg.
    readonly property string _canvasBg: (typeof themeBridge !== "undefined" && themeBridge && themeBridge.palette) ? String(themeBridge.palette.canvas_bg || "") : ""
    readonly property color _shellFallbackFg: (typeof themeBridge !== "undefined" && themeBridge && themeBridge.palette && themeBridge.palette.app_fg) ? themeBridge.palette.app_fg : "#f0f4fb"
    readonly property color _chromeForeground: {
        if (!root.hostValid || root.style !== "minimal_ghost")
            return root._rawHeaderText;
        return ContrastUtils.pickReadableForeground(root._rawHeaderText, root._shellFallbackFg, root._canvasBg, 3.0);
    }
    readonly property color accentColor: root._readableActionAccentColor()

    function _canvasStateBridge() {
        if (root.canvasItem) {
            if (root.canvasItem.canvasStateBridgeRef)
                return root.canvasItem.canvasStateBridgeRef;
        }
        return null;
    }

    function _readableActionAccentColor() {
        var background = root.style === "minimal_ghost" && root._canvasBg.length > 0
            ? root._canvasBg
            : String(root._chromeFillColor);
        var candidates = [
            String(root._requestedAccentColor),
            String(root._shellAccentColor),
            String(root._chromeForeground)
        ];
        for (var i = 0; i < candidates.length; i++) {
            var candidate = candidates[i];
            if (!ContrastUtils.parseColor(candidate))
                continue;
            if (ContrastUtils.contrastRatio(candidate, background) >= 1.8)
                return candidate;
        }
        return String(root._shellAccentColor);
    }

    function _actionColor(action, key, fallback) {
        var value = String(action && action[key] !== undefined ? action[key] : "").trim();
        if (value.length > 0 && ContrastUtils.parseColor(value))
            return value;
        return fallback;
    }

    function _dispatchToolbarAction(action) {
        if (!root.host)
            return false;
        var actionId = String(action && action.id !== undefined ? action.id : "");
        if (!actionId.length)
            return false;
        // `kind` is the routing discriminator, not the boolean result of the
        // dispatch. A surface action that is handled but produces no state
        // change (e.g. the colour picker is cancelled, or an already-applied
        // value is re-selected) returns false. That must not fall through to a
        // node action: the node router finds no descriptor for a surface action
        // id and re-routes it straight back to dispatchSurfaceAction, which
        // re-triggers the action and re-opens the colour dialog.
        var actionKind = String(action && action.kind || "");
        if ((actionKind === "surface" || actionKind === "media") && root.host.dispatchSurfaceAction)
            return Boolean(root.host.dispatchSurfaceAction(actionId));
        root.host.dispatchNodeAction(actionId, null);
        return true;
    }

    readonly property string style: {
        var bridge = root._canvasStateBridge();
        if (bridge && bridge.graphics_floating_toolbar_style !== undefined) {
            var value = String(bridge.graphics_floating_toolbar_style || "").toLowerCase();
            if (value === "compact_pill" || value === "segmented_bar" || value === "minimal_ghost")
                return value;
        }
        return "compact_pill";
    }

    readonly property string size: {
        var bridge = root._canvasStateBridge();
        if (bridge && bridge.graphics_floating_toolbar_size !== undefined) {
            var value = String(bridge.graphics_floating_toolbar_size || "").toLowerCase();
            if (value === "small" || value === "medium" || value === "large")
                return value;
        }
        return "small";
    }

    readonly property real _sizeScale: {
        if (root.size === "large") return 1.5;
        if (root.size === "medium") return 1.25;
        return 1.0;
    }

    readonly property bool _hasChrome: root.style !== "minimal_ghost"
    readonly property real _chromeRadius: {
        if (root.style === "compact_pill") return 999;
        if (root.style === "segmented_bar") return 7;
        return 0;
    }
    readonly property color _chromeFillColor: {
        if (root.style === "compact_pill")
            return Qt.rgba(root._chromeBaseFill.r, root._chromeBaseFill.g, root._chromeBaseFill.b, 0.96);
        if (root.style === "segmented_bar") return root._chromeBaseFill;
        return "transparent";
    }
    readonly property color _chromeBorderColor: {
        if (root.style === "compact_pill") return Qt.alpha(root._chromeBaseBorder, 0.55);
        if (root.style === "segmented_bar") return root._chromeBaseBorder;
        return "transparent";
    }
    readonly property real _chromeBorderWidth: root._hasChrome ? 1 : 0
    readonly property real _chromeInternalPadding: {
        var base;
        if (root.style === "compact_pill") base = 3;
        else if (root.style === "segmented_bar") base = 0;
        else base = 2;
        return base * root._sizeScale;
    }
    readonly property real _chromeButtonGap: {
        var base;
        if (root.style === "compact_pill") base = 2;
        else if (root.style === "segmented_bar") base = 0;
        else base = 2;
        return base * root._sizeScale;
    }
    readonly property bool _chromeClip: root.style === "segmented_bar"
    readonly property real _buttonChromeRadius: {
        if (root.style === "compact_pill") return 999;
        if (root.style === "segmented_bar") return 0;
        return 5;
    }
    readonly property int _buttonHPadding: {
        var base;
        if (root.style === "compact_pill") base = 7;
        else if (root.style === "segmented_bar") base = 12;
        else base = 6;
        return Math.round(base * root._sizeScale);
    }
    readonly property int _buttonVPadding: {
        var base;
        if (root.style === "compact_pill") base = 7;
        else if (root.style === "segmented_bar") base = 6;
        else base = 6;
        return Math.round(base * root._sizeScale);
    }
    readonly property int _buttonIconSize: {
        var base;
        if (root.style === "compact_pill") base = 15;
        else if (root.style === "segmented_bar") base = 14;
        else base = 14;
        return Math.round(base * root._sizeScale);
    }
    readonly property color _buttonHoverFillColor: {
        if (root.style === "minimal_ghost") return Qt.alpha(root._chromeForeground, 0.10);
        return Qt.alpha(root.accentColor, 0.18);
    }
    readonly property color _segmentedDividerColor: Qt.alpha(root._chromeBaseBorder, 0.75)
    readonly property color _minimalSeparatorColor: Qt.alpha(root._chromeForeground, 0.18)
    readonly property color _caretFillColor: root._hasChrome ? root._chromeFillColor : Qt.alpha(root.accentColor, 0.55)
    readonly property color _caretBorderColor: root._hasChrome ? root._chromeBorderColor : Qt.alpha(root.accentColor, 0.55)

    readonly property real gapFromNode: Number(toolbarMetrics.gap_from_node || 6)
    readonly property real safetyMargin: Number(toolbarMetrics.safety_margin || 8)
    readonly property real hysteresis: Number(toolbarMetrics.hysteresis || 8)
    readonly property int animationDuration: Number(toolbarMetrics.animation_duration_ms || 180)
    readonly property real toolbarHeightMetric: Number(toolbarMetrics.toolbar_height || 32)
    readonly property real _rawZoom: Number(
        root.viewBridge && root.viewBridge.zoom_value !== undefined
            ? root.viewBridge.zoom_value
            : 1.0
    )
    readonly property real _effectiveZoom: isFinite(root._rawZoom)
        ? Math.max(0.1, root._rawZoom)
        : 1.0

    readonly property var embeddedInteractiveRects: root.visible
        ? SurfaceControlGeometry.combineRectLists([
            SurfaceControlGeometry.rectList(SurfaceControlGeometry.rectFromItem(chromeContainer, root.host)),
            SurfaceControlGeometry.rectList(SurfaceControlGeometry.rectFromItem(actionPopoverHost.actionPopoverItem, root.host))
        ])
        : []
    readonly property rect toolbarRect: Qt.rect(root.x, root.y, root.width, root.height)

    property bool flipped: false
    Binding {
        target: root.host
        property: "floatingToolbarFlipped"
        value: root.flipped
        when: root.hostValid
    }
    Binding {
        target: root.host
        property: "floatingToolbarZoom"
        value: root._effectiveZoom
        when: root.hostValid
    }
    property bool runMenuVisible: false
    property real runMenuX: 0
    property real runMenuY: 0
    property var runMenuActions: []
    property alias actionPopoverVisible: actionPopoverHost.actionPopoverVisible
    property alias actionPopoverX: actionPopoverHost.actionPopoverX
    property alias actionPopoverY: actionPopoverHost.actionPopoverY
    property alias actionPopoverAnchorCenterX: actionPopoverHost.actionPopoverAnchorCenterX
    property alias actionPopoverOwnerId: actionPopoverHost.actionPopoverOwnerId
    property alias actionPopoverLayout: actionPopoverHost.actionPopoverLayout
    property alias actionPopoverActions: actionPopoverHost.actionPopoverActions
    property alias actionPopoverActionKind: actionPopoverHost.actionPopoverActionKind
    property alias actionPopoverFontSizeValue: actionPopoverHost.actionPopoverFontSizeValue
    property alias actionPopoverFontSizeMin: actionPopoverHost.actionPopoverFontSizeMin
    property alias actionPopoverFontSizeMax: actionPopoverHost.actionPopoverFontSizeMax
    property alias actionPopoverFontSizeSetActionPrefix: actionPopoverHost.actionPopoverFontSizeSetActionPrefix
    property alias actionPopoverFontSizePreviewActionPrefix: actionPopoverHost.actionPopoverFontSizePreviewActionPrefix
    property alias actionPopoverFontSizeDirty: actionPopoverHost.actionPopoverFontSizeDirty
    property alias actionPopoverPageValue: actionPopoverHost.actionPopoverPageValue
    property alias actionPopoverPageMin: actionPopoverHost.actionPopoverPageMin
    property alias actionPopoverPageMax: actionPopoverHost.actionPopoverPageMax
    property alias actionPopoverPageSetActionPrefix: actionPopoverHost.actionPopoverPageSetActionPrefix
    property alias actionPopoverSourceStorageIndex: actionPopoverHost.actionPopoverSourceStorageIndex
    property alias actionPopoverFilterText: actionPopoverHost.actionPopoverFilterText
    readonly property int floatingToolbarPrimaryLevel: actionPopoverHost.floatingToolbarPrimaryLevel
    readonly property int floatingToolbarPopoverLevel: actionPopoverHost.floatingToolbarPopoverLevel
    readonly property int floatingToolbarNestedPopoverLevel: actionPopoverHost.floatingToolbarNestedPopoverLevel
    readonly property int _popoverControlHeight: actionPopoverHost._popoverControlHeight
    readonly property int _popoverIconSize: actionPopoverHost._popoverIconSize
    readonly property int _popoverTextPixelSize: actionPopoverHost._popoverTextPixelSize
    readonly property int _popoverHorizontalPadding: actionPopoverHost._popoverHorizontalPadding
    readonly property int _popoverIconOnlyHorizontalPadding: actionPopoverHost._popoverIconOnlyHorizontalPadding
    readonly property int _popoverVerticalPadding: actionPopoverHost._popoverVerticalPadding
    readonly property int _popoverRadius: actionPopoverHost._popoverRadius

    readonly property var nodeLocalRect: {
        if (!root.hostValid || !root.hostNodeData)
            return ({ x: 0, y: 0, width: 0, height: 0 });
        // host.x already folds in worldOffset plus the active drag (drag.target
        // mutates host.x directly during a drag). liveDragDx/Dy contribute the
        // multi-selection translate applied to non-anchor nodes via transform.
        var dragDx = root.host.dragTranslateX !== undefined
            ? Number(root.host.dragTranslateX || 0)
            : 0.0;
        var dragDy = root.host.dragTranslateY !== undefined
            ? Number(root.host.dragTranslateY || 0)
            : 0.0;
        return {
            x: Number(root.host.x || 0) + dragDx,
            y: Number(root.host.y || 0) + dragDy,
            width: Number(root.host.width || 0),
            height: Number(root.host.height || 0)
        };
    }
    readonly property var viewportLocalRect: {
        var payload = root.visibleSceneRectPayload || {};
        var offset = root.hostValid ? Number(root.host.worldOffset || 0) : 0;
        return {
            x: Number(payload.x || 0) + offset,
            y: Number(payload.y || 0) + offset,
            width: Number(payload.width || 0),
            height: Number(payload.height || 0)
        };
    }
    readonly property size toolbarSize: Qt.size(
        Math.max(1, chromeContainer.implicitWidth),
        Math.max(1, chromeContainer.implicitHeight)
    )
    readonly property var anchor: ToolbarPositioning.computeAnchor(
        root.nodeLocalRect,
        { width: root.toolbarSize.width, height: root.toolbarSize.height },
        root.viewportLocalRect,
        {
            gap_from_node: root.gapFromNode,
            safety_margin: root.safetyMargin,
            hysteresis: root.hysteresis
        },
        root.flipped
    )

    // `anchor` reads root.flipped for hysteresis, and used to write root.flipped
    // straight back here — since onAnchorChanged runs synchronously inside the
    // anchor property's own assignment, that write re-entered the still-settling
    // anchor binding and tripped QML's binding-loop detector. Deferring the sync
    // via Qt.callLater lets the assignment finish before flipped is updated;
    // repeated calls with the same function reference coalesce into one.
    onAnchorChanged: Qt.callLater(root._syncFlippedFromAnchor)

    function _syncFlippedFromAnchor() {
        if (Boolean(root.anchor.flipped) !== root.flipped)
            root.flipped = Boolean(root.anchor.flipped);
    }

    readonly property bool _nodeDragActive: root.hostValid && Boolean(root.host.hostDragActive)

    visible: root.toolbarActive && root.actionList.length > 0 && !root._nodeDragActive
    x: Number(root.anchor.x)
    y: Number(root.anchor.y)
    width: chromeContainer.implicitWidth
    height: chromeContainer.implicitHeight
    opacity: root.visible ? 1.0 : 0.0
    z: 40
    activeFocusOnTab: root.visible

    Behavior on opacity {
        NumberAnimation {
            duration: root.animationDuration
            easing.type: Easing.InOutCubic
        }
    }

    transform: Translate {
        id: slideTransform
        y: root.visible ? 0 : (root.flipped ? -root.gapFromNode : root.gapFromNode)
        Behavior on y {
            NumberAnimation {
                duration: root.animationDuration
                easing.type: Easing.OutCubic
            }
        }
    }

    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
    }

    function _closeActionPopover(flushDraft) {
        actionPopoverHost._closeActionPopover(flushDraft);
    }

    function _previewFontSizeValue(value) {
        return actionPopoverHost._previewFontSizeValue(value);
    }

    function _commitFontSizeValue(value) {
        return actionPopoverHost._commitFontSizeValue(value);
    }

    function openActionPopover(action, anchorItem) {
        actionPopoverHost.openActionPopover(action, anchorItem);
    }

    function openActionMenu(action, anchorItem) {
        root.runMenuActions = GraphActionPresentation.childActions(action, "menuActions");
        if (!root.runMenuActions.length || !anchorItem)
            return;
        root._closeActionPopover(true);
        var anchor = anchorItem.mapToItem(root, 0, root.flipped ? anchorItem.height + 4 : -4);
        root.runMenuX = anchor.x - 4;
        var estimatedHeight = 18 + root.runMenuActions.length * 35;
        root.runMenuY = root.flipped ? anchor.y : anchor.y - estimatedHeight;
        root.runMenuVisible = true;
    }

    // Propagate hover state back to the host so toolbarActiveSource stays true
    // while the cursor is on the chrome or in the gap bridging it to the node.
    // The gap bridge widens the effective hover target across the visible gap
    // so slow cursor movement does not race the 120 ms grace timer.
    readonly property bool pointerOnToolbar: chromeHoverHandler.hovered
        || bridgeHoverHandler.hovered
        || actionPopoverHost.pointerHovered
        || runMenuHoverHandler.hovered
        || runMenuBridgeHoverHandler.hovered
    onPointerOnToolbarChanged: {
        if (root.hostValid)
            root.host.toolbarPointerInside = root.pointerOnToolbar;
    }
    onHostChanged: {
        if (_previousHost && _previousHost.toolbarPointerInside !== undefined)
            _previousHost.toolbarPointerInside = false;
        _previousHost = root.host;
        if (root.hostValid)
            root.host.toolbarPointerInside = root.pointerOnToolbar;
        root.runMenuVisible = false;
        root._closeActionPopover(false);
    }
    property Item _previousHost: null

    HoverHandler {
        id: chromeHoverHandler
    }

    Item {
        id: hoverBridge
        objectName: "graphNodeFloatingToolbarHoverBridge"
        width: chromeContainer.width
        height: Math.max(1, root.gapFromNode)
        x: 0
        y: root.flipped ? -height : chromeContainer.height

        HoverHandler {
            id: bridgeHoverHandler
        }
    }

    readonly property real _ownerCenterX: {
        if (!root.hostValid)
            return chromeContainer.width / 2;
        var rect = root.nodeLocalRect;
        return rect.x + rect.width / 2 - root.x;
    }

    Rectangle {
        id: ownershipCaret
        objectName: "graphNodeFloatingToolbarCaret"
        visible: root._hasChrome
        z: -1
        width: 9
        height: 9
        rotation: 45
        antialiasing: true
        color: root._caretFillColor
        border.width: 1
        border.color: root._caretBorderColor

        readonly property real caretEdgeMargin: 6
        readonly property real clampedCenterX: Math.max(
            caretEdgeMargin + width / 2,
            Math.min(
                chromeContainer.width - caretEdgeMargin - width / 2,
                root._ownerCenterX
            )
        )
        x: clampedCenterX - width / 2
        y: root.flipped
            ? -height / 2 - 0.5
            : chromeContainer.height - height / 2 + 0.5
    }

    Image {
        id: ownershipChevron
        objectName: "graphNodeFloatingToolbarChevron"
        visible: !root._hasChrome
        z: -1
        width: 24
        height: 24
        smooth: true
        antialiasing: true
        source: root._iconSource(
            root.flipped ? "chevron-down" : "chevron-up",
            24,
            root._chromeForeground
        )
        sourceSize: Qt.size(24, 24)

        readonly property real clampedCenterX: Math.max(
            width / 2,
            Math.min(
                chromeContainer.width - width / 2,
                root._ownerCenterX
            )
        )
        x: clampedCenterX - width / 2
        y: root.flipped ? -height + 8 : chromeContainer.height - 9
    }

    Rectangle {
        id: chromeContainer
        objectName: "graphNodeFloatingToolbarChrome"
        radius: root._chromeRadius
        color: root._chromeFillColor
        border.width: root._chromeBorderWidth
        border.color: root._chromeBorderColor
        clip: root._chromeClip

        implicitWidth: buttonRow.implicitWidth + root._chromeInternalPadding * 2
        implicitHeight: Math.max(root.toolbarHeightMetric, buttonRow.implicitHeight + root._chromeInternalPadding * 2)

        Row {
            id: buttonRow
            anchors.centerIn: parent
            spacing: root._chromeButtonGap

            Repeater {
                id: buttonRepeater
                model: root._orderedActions

                Row {
                    id: buttonCell
                    spacing: 0
                    height: actionButton.implicitHeight

                    readonly property bool _isFirst: index === 0
                    readonly property bool _isLast: index === buttonRepeater.count - 1
                    readonly property bool _isDestructive: Boolean(modelData.destructive)
                    readonly property bool _isCommon: String((modelData || {}).kind || "") === "common"
                    readonly property var _menuActions: GraphActionPresentation.childActions(modelData, "menuActions")
                    readonly property bool _hasMenu: buttonCell._menuActions.length > 0
                    readonly property var _popoverActions: GraphActionPresentation.childActions(modelData, "popoverActions")
                    readonly property bool _hasPopover: buttonCell._popoverActions.length > 0
                    readonly property bool _startsCommonGroup: {
                        if (!root._groupBySurfaceFamily || !buttonCell._isCommon || buttonCell._isFirst)
                            return false;
                        var prev = root._orderedActions[index - 1] || {};
                        return String(prev.kind || "") !== "common";
                    }
                    readonly property bool _showLeadingSeparator:
                        buttonCell._startsCommonGroup
                        || Boolean((modelData || {}).separator_before)
                        || (index > 0 && Boolean((root._orderedActions[index - 1] || {}).separator_after))
                        || (root.style === "minimal_ghost" && buttonCell._isDestructive && !buttonCell._isFirst)

                    Item {
                        id: leadingSeparatorSlot
                        visible: buttonCell._showLeadingSeparator
                        width: visible ? 9 : 0
                        height: buttonCell.height
                        Rectangle {
                            anchors.centerIn: parent
                            width: 1
                            height: parent.height - 8
                            color: root._minimalSeparatorColor
                        }
                    }

                    GraphSurfaceControls.GraphSurfaceButton {
                        id: actionButton
                        objectName: "graphNodeFloatingToolbarAction_" + String(modelData.id || "")
                        host: root.host
                        text: GraphActionPresentation.actionToolbarText(modelData)
                        iconName: GraphActionPresentation.actionToolbarIcon(modelData)
                        iconOnly: GraphActionPresentation.actionIconOnly(modelData)
                        iconSize: root._buttonIconSize
                        iconSourceResolver: function(name, size, color) {
                            return root._iconSource(name, size, color);
                        }
                        accentColor: buttonCell._isDestructive
                            ? "#D94F4F"
                            : root._actionColor(modelData, "accent_color", root.accentColor)
                        foregroundColor: root._actionColor(modelData, "foreground_color", root._chromeForeground)
                        enabled: modelData.enabled !== false
                        active: GraphActionPresentation.actionChecked(modelData)
                        chromeRadius: root._buttonChromeRadius
                        contentHorizontalPadding: root._buttonHPadding
                        contentVerticalPadding: root._buttonVPadding
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
                            // A live viewer can republish this model when focus clears.
                            // Let fullscreen dispatch prepare the surface after the click
                            // so the pressed delegate survives through mouse release.
                            if (String(modelData.id || "") === "fullscreen")
                                return;
                            if (root.host && root.host.nodeData && root.host.surfaceControlInteractionStarted)
                                root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
                        }
                        onClicked: {
                            if (!root.host)
                                return;
                            root.runMenuVisible = false;
                            if (buttonCell._hasPopover)
                                root.openActionPopover(modelData, actionButton);
                            else
                                root._dispatchToolbarAction(modelData);
                        }
                        Keys.onReturnPressed: actionButton.clicked()
                        Keys.onEnterPressed: actionButton.clicked()
                    }

                    GraphSurfaceControls.GraphSurfaceButton {
                        id: actionMenuButton
                        objectName: "graphNodeFloatingToolbarActionMenu_" + String(modelData.id || "")
                        visible: buttonCell._hasMenu
                        host: root.host
                        text: String(modelData.label || "") + " menu"
                        iconName: String(modelData.menu_icon || "chevron-down")
                        iconOnly: true
                        iconSize: modelData.menu_icon ? root._buttonIconSize : Math.max(10, root._buttonIconSize - 3)
                        iconSourceResolver: function(name, size, color) {
                            return root._iconSource(name, size, color);
                        }
                        foregroundColor: root._chromeForeground
                        accentColor: root.accentColor
                        enabled: modelData.enabled !== false
                        chromeRadius: root._buttonChromeRadius
                        contentHorizontalPadding: Math.max(4, Math.round(root._buttonHPadding * 0.55))
                        contentVerticalPadding: root._buttonVPadding
                        tooltipText: String(modelData.label || "") + TooltipCopy.text(tooltipCopyBridge, "fullscreen.toolbar.options_suffix")
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "fullscreen.toolbar.options_suffix")
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
                        onClicked: root.openActionMenu(modelData, actionMenuButton)
                        Keys.onReturnPressed: actionMenuButton.clicked()
                        Keys.onEnterPressed: actionMenuButton.clicked()
                    }

                    Rectangle {
                        id: trailingDivider
                        visible: root.style === "segmented_bar" && !buttonCell._isLast
                        width: visible ? 1 : 0
                        height: buttonCell.height
                        color: root._segmentedDividerColor
                    }
                }
            }
        }
    }

    GraphNodeToolbarPopoverHost {
        id: actionPopoverHost
        toolbar: root
    }
    // Bridges the gap between the toolbar chrome and the run menu so the cursor
    // never falls through to a node beneath the overlay (e.g. a group backdrop)
    // while reaching for a menu item. Without it the backdrop claims the active
    // toolbar host mid-gap, switching the toolbar's host and closing the menu.
    Item {
        id: runMenuBridge
        objectName: "graphNodeFloatingToolbarRunMenuBridge"
        visible: actionDropdown.visible
        x: Math.min(0, actionDropdown.x)
        width: Math.max(chromeContainer.width, actionDropdown.x + actionDropdown.width) - x
        y: root.flipped
            ? chromeContainer.height
            : (actionDropdown.y + actionDropdown.panelHeight)
        height: root.flipped
            ? Math.max(0, actionDropdown.y - chromeContainer.height)
            : Math.max(0, -(actionDropdown.y + actionDropdown.panelHeight))
        z: 79

        HoverHandler {
            id: runMenuBridgeHoverHandler
        }
    }

    ShellComponents.ShellContextMenu {
        id: actionDropdown
        objectName: "graphNodeFloatingToolbarRunMenu"
        visible: root.visible && root.runMenuVisible && root.runMenuActions.length > 0
        x: root.runMenuX
        y: root.runMenuY
        z: 80
        minimumWidth: 196

        HoverHandler {
            id: runMenuHoverHandler
        }
        actions: GraphActionPresentation.menuModel(root.runMenuActions)
        onActionTriggered: function(actionId) {
            root.runMenuVisible = false;
            if (root.host)
                root.host.dispatchNodeAction(String(actionId || ""), null);
        }
    }
}
