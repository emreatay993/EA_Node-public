import QtQuick 2.15
import QtQuick.Effects
import "../common" as Common
import "surface_controls" as SurfaceControls
import "surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "GraphNodeHostHitTesting.js" as GraphNodeHostHitTesting

Item {
    id: root
    objectName: "graphNodeHeaderLayer"
    property Item host: null
    property bool isEditing: false
    readonly property bool sharedHeaderTitleEditable: host ? host.sharedHeaderTitleEditable : false
    readonly property bool headerTitleVisible: host
        ? ((!host.isFlowchartSurface || host.isCollapsed)
            && !host.isCompactPillSurface
            && (!host.chromeToggleCapableSurface || host.nodeChromeTitleVisible))
        : true
    readonly property bool isGroupBackdropNode: host
        ? String(host.surfaceFamily || "") === "group_backdrop"
        : false
    // Flowchart shapes retain their fixed compact collapsed geometry; every
    // other card grows to show its full header title.
    readonly property bool collapsedTitleFitsWidth: host
        ? !host.isFlowchartSurface
        : false
    readonly property bool groupTitleIconVisible: host
        ? root.isGroupBackdropNode && host.isCollapsed
        : false
    readonly property bool lockedPlaceholderActive: host ? Boolean(host.lockedPlaceholderActive) : false
    readonly property var tooltipPolicyBridge: root.host && root.host.canvasItem && root.host.canvasItem.canvasStateBridgeRef
        ? root.host.canvasItem.canvasStateBridgeRef
        : null
    readonly property string nodeTooltipPlacement: root.host && root.host.floatingToolbarFlipped ? "above" : "below"
    readonly property real nodeTooltipAnchorScale: root.host
        ? Math.max(0.1, Number(root.host.floatingToolbarZoom || 1.0))
        : 1.0
    readonly property var tooltipThemePalette: typeof themeBridge !== "undefined" && themeBridge
        ? themeBridge.palette
        : ({})
    readonly property string nodeHelpMutedColor: String(root.tooltipThemePalette.muted_fg || "#95a0b8")
    readonly property string nodeHelpDividerColor: String(root.tooltipThemePalette.border || "#3a3d45")
    readonly property string nodeHelpText: root._nodeHelpTooltipText()
    readonly property bool warningBadgeVisible: root.host
        ? root.host.isDiagnosticWarningNode && !root.host.isFailedNode
        : false
    readonly property var warningDiagnosticRows: root.host && root.host.nodeDiagnostic
        ? (root.host.nodeDiagnostic.rows || [])
        : []
    readonly property int warningDiagnosticCount: root.warningDiagnosticRows.length
    readonly property string warningDiagnosticTitle: root.warningDiagnosticCount + " warning"
        + (root.warningDiagnosticCount === 1 ? "" : "s")
    readonly property bool primaryGroupBackdropTitleSuppressedByInputOverlay: root.isGroupBackdropNode
        && !!root.host
        && String(root.host.surfaceVariant || "") !== "group_backdrop_input_overlay"
        && !!root.host.canvasItem
        && Boolean(root.host.isSelected)
    readonly property int groupTitleIconSize: root.graphSharedTypography
        ? root.graphSharedTypography.nodeTitleIconPixelSize
        : 10
    readonly property int groupTitleIconSpacing: 6
    readonly property int lockedTitleIconSize: root.nodeTitleIconSize
    readonly property int lockedTitleIconSpacing: 8
    readonly property real _titleBandHeight: root.host ? Math.max(0, Number(root.host._titleHeight)) : 0
    readonly property int nodeTitleIconSize: root.graphSharedTypography
        ? root.graphSharedTypography.nodeTitleIconPixelSize
        : 10
    readonly property int nodeTitleIconRenderSize: Math.max(
        0,
        Math.floor(Math.min(root.nodeTitleIconSize, root._titleBandHeight))
    )
    readonly property int groupTitleIconRenderSize: Math.max(
        0,
        Math.floor(Math.min(root.groupTitleIconSize, root._titleBandHeight))
    )
    readonly property bool lockedTitleIconVisible: root.lockedPlaceholderActive && root.headerTitleVisible
    readonly property int lockedTitleIconRenderSize: Math.max(
        0,
        Math.floor(Math.min(root.lockedTitleIconSize, root._titleBandHeight))
    )
    readonly property int nodeTitleIconSpacing: 6
    readonly property real _groupTitleIconReserveWidth: root.groupTitleIconVisible
        && root.groupTitleIconRenderSize > 0
        ? root.groupTitleIconRenderSize + root.groupTitleIconSpacing
        : 0
    readonly property real _lockedTitleIconReserveWidth: root.lockedTitleIconVisible
        && root.lockedTitleIconRenderSize > 0
        ? root.lockedTitleIconRenderSize + root.lockedTitleIconSpacing
        : 0
    readonly property string nodeTitleIconSource: root.host && root.host.nodeData
        ? String(root.host.nodeData.icon_source || "")
        : ""
    readonly property bool nodeTitleIconThemeAware: root.host
        && root.host.nodeData
        && Boolean(root.host.nodeData.icon_theme_aware)
    readonly property color nodeTitleIconThemeColor: root.host
        ? root.host.headerTextColor
        : "#f0f4fb"
    readonly property bool passiveTitleIconOptIn: root.host
        && root.host.nodeData
        && Boolean(root.host.nodeData.show_title_icon)
    readonly property bool nodeTitleIconEligible: root.headerTitleVisible
        && !!root.host
        && !root.isGroupBackdropNode
        && (!root.host.isPassiveNode || root.passiveTitleIconOptIn)
        && root.nodeTitleIconSource.length > 0
    readonly property bool nodeTitleIconVisible: root.nodeTitleIconEligible
        && root.nodeTitleIconRenderSize > 0
    readonly property real _nodeTitleIconReserveWidth: root.nodeTitleIconEligible
        && root.nodeTitleIconRenderSize > 0
        ? root.nodeTitleIconRenderSize + root.nodeTitleIconSpacing
        : 0
    readonly property real _titleLeadingIconReserveWidth: root.lockedTitleIconVisible
        ? root._lockedTitleIconReserveWidth
        : (root.groupTitleIconVisible
            ? root._groupTitleIconReserveWidth
            : root._nodeTitleIconReserveWidth)
    readonly property real _headerBadgeReserveWidth: root.lockedPlaceholderActive ? 64 : 0
    readonly property real diagnosticBadgeSize: Math.max(
        16, (root.graphSharedTypography ? root.graphSharedTypography.badgePixelSize : 9) + 6
    )
    readonly property string currentTitle: root.host && root.host.nodeData
        ? String(root.host.nodeData.title || root.host.nodeData.display_name || "")
        : ""
    readonly property var graphSharedTypography: root.host ? root.host.graphSharedTypography : null
    readonly property int titlePixelSize: root.graphSharedTypography
        ? root.graphSharedTypography.nodeTitlePixelSize
        : 12
    readonly property int titleFontWeight: root.graphSharedTypography
        ? root.graphSharedTypography.nodeTitleFontWeight
        : Font.Bold
    readonly property string displayTitle: {
        var title = String(root.currentTitle || "");
        if (root.isGroupBackdropNode && !title.trim().length)
            return root.host && root.host.isSelected ? "Double click to edit title" : "";
        return title;
    }
    readonly property real collapsedTitleRequiredWidth: {
        if (!root.host || !root.host.isCollapsed || !root.collapsedTitleFitsWidth || !root.headerTitleVisible)
            return 0.0;
        var textWidth = Math.ceil(root._collapsedMeasuredTitleTextWidth());
        return Math.max(
            0.0,
            Number(root.host._titleLeftMargin)
                + Number(root.host._titleRightMargin)
                + Number(root._headerBadgeReserveWidth)
                + Number(root._titleLeadingIconReserveWidth)
                + textWidth
                + 4.0
        );
    }
    readonly property string groupTitleIconSource: root.groupTitleIconVisible
        ? uiIcons.sourceSized("comment", root.groupTitleIconSize, String(root.host ? root.host.headerTextColor : "#f0f4fb"))
        : ""
    readonly property string lockedTitleIconSource: root.lockedTitleIconVisible
        ? uiIcons.sourceSized("lock", root.lockedTitleIconSize, String(root.host ? root.host.headerTextColor : "#b0b7c3"))
        : ""
    readonly property real _titleEditorLeftPadding: root.host && root.host._titleCentered
        ? (root._titleLeadingIconReserveWidth * 0.5)
        : root._titleLeadingIconReserveWidth
    readonly property real _titleEditorRightPadding: root.host && root.host._titleCentered
        ? (root._titleLeadingIconReserveWidth * 0.5)
        : 0
    readonly property var embeddedInteractiveRects: titleEditorInteractionRegion.embeddedInteractiveRects
    z: 3

    function _collapsedMeasuredTitleTextWidth() {
        var advanceWidth = Number(collapsedTitleMetrics.advanceWidth);
        var measuredWidth = Number(collapsedTitleMetrics.width);
        return Math.max(
            0.0,
            isFinite(advanceWidth) ? advanceWidth : 0.0,
            isFinite(measuredWidth) ? measuredWidth : 0.0
        );
    }

    function _centeredTitleTextDisplayStart() {
        if (!(root.host && root.host._titleCentered))
            return Number(titleText ? titleText.x : 0);
        var availableWidth = Math.max(0, Number(titleText ? titleText.width : 0));
        var displayWidth = Math.min(availableWidth, Math.max(0, Number(titleText ? titleText.contentWidth : 0)));
        return Number(titleText ? titleText.x : 0) + Math.max(0, (availableWidth - displayWidth) * 0.5);
    }

    function _titleLeadingIconX(iconWidth, spacing) {
        if (!(root.host && root.host._titleCentered))
            return 0;
        return Math.max(
            0,
            root._centeredTitleTextDisplayStart() - Math.max(0, Number(iconWidth)) - Math.max(0, Number(spacing))
        );
    }

    function _escapeNodeHelpHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;");
    }

    function _nodeHelpTooltipText() {
        if (!root.host || !root.host.nodeData)
            return "";
        var node = root.host.nodeData;
        var title = String(node.display_name || node.title || "").trim();
        var categoryPath = node.category_path || [];
        var description = String(node.help_text || "").trim();
        var keywords = node.keywords || [];
        var html = title.length > 0 ? "<b>" + root._escapeNodeHelpHtml(title) + "</b>" : "";
        if (categoryPath.length > 0)
            html += "<br><font color=\"" + root._escapeNodeHelpHtml(root.nodeHelpMutedColor) + "\">"
                + root._escapeNodeHelpHtml(Array.prototype.join.call(categoryPath, ", "))
                + "</font>";
        if (description.length > 0)
            html += "<br>" + root._escapeNodeHelpHtml(description).replace(/\r?\n/g, "<br>");
        if (keywords.length > 0)
            html += "<br><br>Keywords: "
                + root._escapeNodeHelpHtml(Array.prototype.join.call(keywords, ", "))
                + ".";
        var runCountLookup = root.host.executionFacts
            && root.host.executionFacts.nodeRunCountLookup
            ? root.host.executionFacts.nodeRunCountLookup
            : ({});
        var runCount = Math.max(0, Math.round(Number(runCountLookup[String(node.node_id || "")] || 0)));
        if (runCount > 0)
            html += "<hr color=\"" + root._escapeNodeHelpHtml(root.nodeHelpDividerColor) + "\">"
                + "This node ran " + runCount + " time(s).";
        return html;
    }

    function _beginTitleEdit() {
        if (!root.sharedHeaderTitleEditable || !root.headerTitleVisible || root.isEditing || !root.host || !root.host.nodeData)
            return false;
        root.isEditing = true;
        root.host.surfaceControlInteractionStarted(String(root.host.nodeData.node_id || ""));
        return true;
    }

    function requestTitleEditAt(localX, localY) {
        if (!root.sharedHeaderTitleEditable || !root.headerTitleVisible || root.isEditing)
            return false;
        if (!GraphNodeHostHitTesting.pointInRect(localX, localY, titleHitRegion.interactiveRect))
            return false;
        return root._beginTitleEdit();
    }

    function requestScopeOpenAt(localX, localY) {
        return false;
    }

    function cancelTitleEdit() {
        if (!root.isEditing)
            return;
        root.isEditing = false;
        titleEditor.text = root.currentTitle;
    }

    function commitTitleEdit(text) {
        if (!root.isEditing)
            return;
        var normalized = String(text || "").trim();
        var current = String(root.currentTitle || "").trim();
        root.isEditing = false;
        if (!normalized.length || normalized === current) {
            titleEditor.text = root.currentTitle;
            return;
        }
        titleEditor.text = normalized;
        if (root.host && root.host.nodeData)
            root.host.inlinePropertyCommitted(String(root.host.nodeData.node_id || ""), "title", normalized);
    }

    function commitTitleEditFromExternalInteraction(localX, localY) {
        if (!root.isEditing)
            return false;
        if (GraphNodeHostHitTesting.pointInRect(localX, localY, titleEditorInteractionRegion.interactiveRect))
            return false;
        root.commitTitleEdit(titleEditor.text);
        return true;
    }

    onCurrentTitleChanged: {
        if (!root.isEditing && titleEditor.text !== root.currentTitle)
            titleEditor.text = root.currentTitle;
    }

    onSharedHeaderTitleEditableChanged: {
        if (!root.sharedHeaderTitleEditable && root.isEditing)
            root.cancelTitleEdit();
    }

    onHeaderTitleVisibleChanged: {
        if (!root.headerTitleVisible && root.isEditing)
            root.cancelTitleEdit();
    }

    Loader {
        id: lockedAccentStripeLoader
        active: root.lockedPlaceholderActive && !!root.host
        x: 2
        y: root.host ? Number(root.host.surfaceMetrics.header_top_margin) : 0
        width: 4
        height: root.host ? Number(root.host.surfaceMetrics.header_height) : 0
        z: 2
        sourceComponent: Component {
            Canvas {
                objectName: "graphNodeLockedAccentStripe"
                antialiasing: false

                onPaint: {
                    var ctx = getContext("2d");
                    ctx.clearRect(0, 0, width, height);
                    if (width <= 0 || height <= 0)
                        return;
                    var dashHeight = 4;
                    var gapHeight = 3;
                    ctx.fillStyle = root.host
                        ? String(root.host.lockedPlaceholderAccentDashColor)
                        : "#6b7280";
                    for (var y = 0; y < height; y += dashHeight + gapHeight)
                        ctx.fillRect(0, y, width, Math.min(dashHeight, height - y));
                }

                Component.onCompleted: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
            }
        }
    }

    TextMetrics {
        id: collapsedTitleMetrics
        text: root.displayTitle
        font.pixelSize: root.titlePixelSize
        font.weight: root.titleFontWeight
    }

    Item {
        id: titleDisplay
        objectName: "graphNodeTitleDisplay"
        visible: root.headerTitleVisible
        anchors.left: parent.left
        anchors.leftMargin: root.host ? root.host._titleLeftMargin : 0
        anchors.right: parent.right
        anchors.rightMargin: root.host ? root.host._titleRightMargin + root._headerBadgeReserveWidth : 0
        y: root.host ? root.host._titleTop : 0
        height: root.host ? root.host._titleHeight : 0

        Image {
            id: nodeTitleIcon
            objectName: "graphNodeTitleIcon"
            readonly property bool themeAware: root.nodeTitleIconThemeAware
            readonly property color themeAwareColor: root.nodeTitleIconThemeColor
            visible: root.nodeTitleIconVisible
            source: root.nodeTitleIconSource
            x: root._titleLeadingIconX(width, root.nodeTitleIconSpacing)
            y: Math.round((titleDisplay.height - height) * 0.5)
            width: root.nodeTitleIconRenderSize
            height: root.nodeTitleIconRenderSize
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            sourceSize.width: root.nodeTitleIconRenderSize
            sourceSize.height: root.nodeTitleIconRenderSize
            layer.enabled: themeAware
            layer.effect: MultiEffect {
                colorization: nodeTitleIcon.themeAware ? 1.0 : 0.0
                colorizationColor: nodeTitleIcon.themeAwareColor
            }
        }

        Image {
            id: groupTitleIcon
            objectName: "graphNodeGroupTitleIcon"
            visible: root.groupTitleIconVisible
                && root.groupTitleIconRenderSize > 0
                && root.groupTitleIconSource.length > 0
            source: root.groupTitleIconSource
            x: root._titleLeadingIconX(width, root.groupTitleIconSpacing)
            y: Math.round((titleDisplay.height - height) * 0.5)
            width: root.groupTitleIconRenderSize
            height: root.groupTitleIconRenderSize
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            sourceSize.width: root.groupTitleIconRenderSize
            sourceSize.height: root.groupTitleIconRenderSize
        }

        Image {
            id: lockedTitleIcon
            objectName: "graphNodeLockedTitleIcon"
            visible: root.lockedTitleIconVisible
                && root.lockedTitleIconRenderSize > 0
                && root.lockedTitleIconSource.length > 0
            source: root.lockedTitleIconSource
            x: root._titleLeadingIconX(width, root.lockedTitleIconSpacing)
            y: Math.round((titleDisplay.height - height) * 0.5)
            width: root.lockedTitleIconRenderSize
            height: root.lockedTitleIconRenderSize
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            sourceSize.width: root.lockedTitleIconRenderSize
            sourceSize.height: root.lockedTitleIconRenderSize
        }

        Text {
            id: titleText
            objectName: "graphNodeTitle"
            visible: !(root.headerTitleVisible && root.isEditing)
                && !root.primaryGroupBackdropTitleSuppressedByInputOverlay
            property int effectiveRenderType: renderType
            x: root._titleLeadingIconReserveWidth > 0
                ? (root.host && root.host._titleCentered
                    ? root._titleLeadingIconReserveWidth * 0.5
                    : root._titleLeadingIconReserveWidth)
                : 0
            width: Math.max(0, titleDisplay.width - x)
            height: titleDisplay.height
            text: root.displayTitle
            color: root.host ? root.host.headerTextColor : "#f0f4fb"
            font.pixelSize: root.titlePixelSize
            font.weight: root.titleFontWeight
            horizontalAlignment: root.host && root.host._titleCentered ? Text.AlignHCenter : Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            renderType: root.host ? root.host.nodeTextRenderType : Text.CurveRendering

            HoverHandler {
                id: titleHelpHover
                enabled: root.nodeHelpText.length > 0 && titleText.visible
            }

            Common.ManagedToolTip {
                objectName: "graphNodeHelpToolTip"
                policyBridge: root.tooltipPolicyBridge
                category: "general"
                active: titleHelpHover.hovered
                text: root.nodeHelpText
                textFormat: Text.RichText
                delay: 400
                screenStablePositioning: true
                screenStablePlacement: root.nodeTooltipPlacement
                anchorScale: root.nodeTooltipAnchorScale
                screenGap: 8
            }
        }
    }

    SurfaceControls.GraphSurfaceInteractiveRegion {
        id: titleHitRegion
        host: root.host
        targetItem: titleDisplay
        enabled: root.sharedHeaderTitleEditable && titleDisplay.visible
    }

    SurfaceControls.GraphSurfaceTextField {
        id: titleEditor
        objectName: "graphNodeTitleEditor"
        visible: root.headerTitleVisible && root.isEditing
        host: root.host
        x: titleDisplay.x
        y: titleDisplay.y
        width: titleDisplay.width
        height: titleDisplay.height
        text: root.currentTitle
        font.pixelSize: titleText.font.pixelSize
        font.weight: titleText.font.weight
        textColor: root.host ? root.host.headerTextColor : "#f0f4fb"
        fillColor: "transparent"
        borderColor: "transparent"
        focusBorderColor: "transparent"
        topPadding: 0
        bottomPadding: 0
        leftPadding: root._titleEditorLeftPadding
        rightPadding: root._titleEditorRightPadding
        horizontalAlignment: root.host && root.host._titleCentered
            ? TextInput.AlignHCenter
            : TextInput.AlignLeft
        verticalAlignment: TextInput.AlignVCenter

        onVisibleChanged: {
            if (visible) {
                text = root.currentTitle;
                forceActiveFocus();
                cursorPosition = text.length;
                deselect();
            }
        }

        onAccepted: {
            root.commitTitleEdit(text);
        }

        onActiveFocusChanged: {
            if (!activeFocus && root.isEditing)
                root.commitTitleEdit(text);
        }

        Keys.onEscapePressed: function(event) {
            root.cancelTitleEdit();
            event.accepted = true;
        }
    }

    SurfaceControls.GraphSurfaceInteractiveRegion {
        id: titleEditorInteractionRegion
        host: root.host
        targetItem: titleEditor
        enabled: root.sharedHeaderTitleEditable && titleEditor.visible
    }

    Rectangle {
        id: warningBadge
        objectName: "graphNodeWarningBadge"
        visible: root.warningBadgeVisible
        anchors.right: parent.right
        anchors.rightMargin: 8
        y: -height * 0.5
        width: root.diagnosticBadgeSize
        height: width
        radius: width * 0.5
        color: root.host ? root.host.warningOutlineColor : "#E8A838"
        border.width: 1
        border.color: root.host ? root.host.warningOutlineColor : "#E8A838"
        Accessible.name: root.warningDiagnosticTitle

        Text {
            objectName: "graphNodeWarningBadgeText"
            anchors.centerIn: parent
            text: "!"
            color: "#FFFFFF"
            font.pixelSize: root.graphSharedTypography ? root.graphSharedTypography.badgePixelSize : 9
            font.weight: root.graphSharedTypography ? root.graphSharedTypography.badgeFontWeight : Font.Bold
            renderType: root.host ? root.host.nodeTextRenderType : Text.CurveRendering
        }

        HoverHandler {
            id: warningBadgeHover
        }

        Common.ManagedToolTip {
            id: warningToolTip
            objectName: "graphNodeWarningToolTip"
            policyBridge: root.tooltipPolicyBridge
            category: "warning"
            active: warningBadgeHover.hovered
            text: root.host
                ? String(root.host.nodeDiagnostic.tooltip_text || root.warningDiagnosticTitle || "")
                : ""
            delay: 240
            screenStablePositioning: true
            screenStablePlacement: root.nodeTooltipPlacement
            anchorScale: root.nodeTooltipAnchorScale
            screenGap: 8
            Accessible.name: text

            contentItem: Item {
                implicitWidth: 360
                implicitHeight: warningToolTipTable.implicitHeight

                Column {
                    id: warningToolTipTable
                    objectName: "graphNodeWarningToolTipTable"
                    width: parent.width
                    spacing: 0

                    Text {
                        objectName: "graphNodeWarningToolTipHeader"
                        width: parent.width
                        bottomPadding: 10
                        text: root.warningDiagnosticTitle
                        color: warningToolTip.resolvedTextColor
                        font.family: warningToolTip.font.family
                        font.pixelSize: warningToolTip.font.pixelSize
                        font.weight: Font.Bold
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        objectName: "graphNodeWarningToolTipHeaderDivider"
                        width: parent.width
                        height: 1
                        color: root.nodeHelpDividerColor
                    }

                    Repeater {
                        model: root.warningDiagnosticRows

                        delegate: Item {
                            id: warningRow
                            objectName: "graphNodeWarningToolTipRow" + index
                            required property int index
                            required property var modelData
                            width: 360
                            height: Math.max(40, warningMessage.implicitHeight + 16)

                            Text {
                                objectName: "graphNodeWarningToolTipIndex" + warningRow.index
                                x: 0
                                y: 8
                                width: 32
                                text: String(warningRow.index)
                                color: warningToolTip.resolvedTextColor
                                font: warningToolTip.font
                                horizontalAlignment: Text.AlignHCenter
                            }

                            Rectangle {
                                x: 38
                                width: 1
                                height: parent.height
                                color: root.nodeHelpDividerColor
                            }

                            Text {
                                id: warningMessage
                                objectName: "graphNodeWarningToolTipMessage" + warningRow.index
                                x: 50
                                y: 8
                                width: parent.width - x
                                text: String(warningRow.modelData.message || "")
                                color: warningToolTip.resolvedTextColor
                                font: warningToolTip.font
                                wrapMode: Text.WordWrap
                            }

                            Rectangle {
                                visible: warningRow.index + 1 < root.warningDiagnosticCount
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 1
                                color: root.nodeHelpDividerColor
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: failureBadge
        objectName: "graphNodeFailureBadge"
        visible: root.host ? root.host.isFailedNode : false
        anchors.right: parent.right
        anchors.rightMargin: 8
        y: -height * 0.5
        width: root.diagnosticBadgeSize
        height: width
        radius: width * 0.5
        color: root.host ? root.host.failureBadgeFillColor : "#421617"
        border.color: root.host ? root.host.failureBadgeBorderColor : "#FF8C74"
        Accessible.name: "Execution halted"

        Text {
            id: failureBadgeText
            objectName: "graphNodeFailureBadgeText"
            anchors.centerIn: parent
            text: "!"
            color: root.host ? root.host.failureBadgeTextColor : "#FFE5DE"
            font.pixelSize: root.graphSharedTypography ? root.graphSharedTypography.badgePixelSize : 9
            font.weight: root.graphSharedTypography ? root.graphSharedTypography.badgeFontWeight : Font.Bold
            renderType: root.host ? root.host.nodeTextRenderType : Text.CurveRendering
        }

        HoverHandler { id: failureBadgeHover }

        Common.ManagedToolTip {
            objectName: "graphNodeFailureToolTip"
            policyBridge: root.tooltipPolicyBridge
            category: "general"
            active: failureBadgeHover.hovered
            text: "Execution halted"
            delay: 240
            screenStablePositioning: true
            screenStablePlacement: root.nodeTooltipPlacement
            anchorScale: root.nodeTooltipAnchorScale
            screenGap: 8
        }
    }

    Rectangle {
        id: lockedBadge
        objectName: "graphNodeLockedChip"
        visible: root.lockedPlaceholderActive
        anchors.right: parent.right
        anchors.rightMargin: 8
        y: root.host ? root.host._titleTop + Math.max(0, (root.host._titleHeight - height) * 0.5) : 0
        width: Math.ceil(lockedBadgeText.implicitWidth) + 12
        height: 18
        radius: 3
        color: root.host ? root.host.lockedPlaceholderChipColor : "#3a3d45"
        border.width: 0

        Text {
            id: lockedBadgeText
            objectName: "graphNodeLockedChipText"
            anchors.centerIn: parent
            text: "LOCKED"
            color: root.host ? root.host.lockedPlaceholderChipTextColor : "#d0d5de"
            font.pixelSize: root.graphSharedTypography ? root.graphSharedTypography.badgePixelSize : 9
            font.weight: root.graphSharedTypography ? root.graphSharedTypography.badgeFontWeight : Font.Bold
            font.letterSpacing: 0.6
            renderType: root.host ? root.host.nodeTextRenderType : Text.CurveRendering
        }
    }
}
