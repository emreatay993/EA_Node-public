import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common
import "surface_controls" as SurfaceControls
import "surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    objectName: "graphInlinePropertiesLayer"
    property Item host: null
    property var modelOverride: null
    property real contentHeightOverride: NaN
    property real contentTopOverride: NaN
    readonly property var graphSharedTypography: root.host ? root.host.graphSharedTypography : null
    readonly property var inlineProperties: modelOverride !== null
        ? modelOverride
        : (host ? host.inlineProperties : [])
    property bool _inlineDelegatesReady: false
    readonly property real _inlineLabelMinWidth: 78
    readonly property real _inlineLabelMaxWidth: 320
    readonly property real _inlineToggleControlReserveWidth: 32
    readonly property real _textareaRowHeight: {
        var numeric = Number(root.graphSharedTypography ? root.graphSharedTypography.inlineTextareaRowHeight : NaN);
        return isFinite(numeric) ? numeric : 104;
    }
    readonly property real _interactiveRectGeometryKey: {
        if (!root._inlineDelegatesReady)
            return 0;
        var total = inlinePropertyRepeater.count;
        total += inlineControlsColumn.x + inlineControlsColumn.y
            + inlineControlsColumn.width + inlineControlsColumn.height;
        for (var index = 0; index < inlinePropertyRepeater.count; index++) {
            var row = inlinePropertyRepeater.itemAt(index);
            if (!row)
                continue;
            total += row.x + row.y + row.width + row.height + (row.visible ? 1 : 0);
            var rectList = row.currentInteractiveRectList();
            for (var rectIndex = 0; rectIndex < rectList.length; rectIndex++) {
                var rect = rectList[rectIndex];
                total += Number(rect.x || 0) + Number(rect.y || 0)
                    + Number(rect.width || 0) + Number(rect.height || 0);
            }
        }
        return total;
    }
    readonly property var embeddedInteractiveRects: {
        if (!root._inlineDelegatesReady)
            return [];
        var _geometryKey = root._interactiveRectGeometryKey;
        return root._embeddedInteractiveRects();
    }
    readonly property real requiredTextFitNodeWidth: root._inlineDelegatesReady
        ? root._requiredTextFitNodeWidth()
        : 0.0

    implicitHeight: isFinite(contentHeightOverride)
        ? Math.max(0, contentHeightOverride)
        : (host ? host.inlineBodyHeight : 0)
    visible: inlineProperties.length > 0

    function _beginInteraction() {
        if (host && host.nodeData)
            host.surfaceControlInteractionStarted(String(host.nodeData.node_id || ""));
    }

    function _commitInlineProperty(key, value) {
        if (host && host.nodeData)
            host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), key, value);
    }

    function _presentationFor(staticData) {
        if (!staticData || !host || !host.nodeData || !host.executionFacts)
            return staticData || ({});
        var lookup = host.executionFacts.propertyPresentationLookup || ({});
        var nodeLookup = lookup[String(host.nodeData.node_id || "")] || ({});
        return nodeLookup[String(staticData.key || "")] || staticData;
    }

    function _editorKind(propertyData) {
        return String(propertyData && propertyData.inline_editor || "").trim().toLowerCase();
    }

    function _isStackedEditor(propertyData) {
        var editor = root._editorKind(propertyData);
        return editor === "text" || editor === "number" || editor === "enum"
            || editor === "slider" || editor === "interval_slider"
            || editor === "interval_fields" || editor === "list"
            || editor === "secret";
    }

    function _editorEnabled(propertyData) {
        if (!propertyData)
            return false;
        if (propertyData.editor_enabled !== undefined)
            return Boolean(propertyData.editor_enabled);
        return !Boolean(propertyData.overridden_by_input);
    }

    function _displayValueAvailable(propertyData) {
        if (!propertyData)
            return false;
        if (propertyData.display_value_available !== undefined)
            return Boolean(propertyData.display_value_available);
        return true;
    }

    function _displayValue(propertyData) {
        if (!propertyData)
            return null;
        if (propertyData.display_value !== undefined)
            return propertyData.display_value;
        return propertyData.value;
    }

    function _displayText(propertyData) {
        if (!root._displayValueAvailable(propertyData))
            return "\u2014";
        var value = root._displayValue(propertyData);
        return value === undefined || value === null ? "" : String(value);
    }

    function _rowHeightFor(propertyData) {
        if (isFinite(root.contentHeightOverride))
            return Math.max(0, root.contentHeightOverride);
        var editor = root._editorKind(propertyData);
        if (editor === "textarea")
            return host ? host._inlineTextareaRowHeight : root._textareaRowHeight;
        if (editor === "slider" || editor === "interval_slider")
            return host ? host._inlineSliderRowHeight : 66;
        if (editor === "list")
            return 142;
        if (editor === "interval_fields")
            return host ? host._inlineStackedRowHeight : 56;
        if (editor === "text" || editor === "number" || editor === "enum"
                || editor === "secret")
            return host ? host._inlineStackedRowHeight : 56;
        return host ? host._inlineRowHeight : 26;
    }

    function _number(value, fallback) {
        var numeric = Number(value);
        return isFinite(numeric) ? numeric : fallback;
    }

    function _rowOffsetForIndex(rowIndex) {
        var offset = 0.0;
        var count = Math.min(Math.max(0, rowIndex), inlineProperties.length);
        for (var index = 0; index < count; index++) {
            offset += root._rowHeightFor(root._presentationFor(inlineProperties[index]));
            offset += host ? host._inlineRowSpacing : 4;
        }
        return offset;
    }

    function _statusChipVariant(propertyData) {
        return String(propertyData && propertyData.status_chip_variant || "").trim().toLowerCase();
    }

    function _statusChipFillColor(propertyData) {
        return root._statusChipVariant(propertyData) === "stored"
            ? (host ? Qt.alpha(host.scopeBadgeColor, 0.92) : "#1D8CE0")
            : (host ? Qt.alpha(host.inlineRowBorderColor, 0.72) : "#4a4f5a");
    }

    function _statusChipBorderColor(propertyData) {
        return root._statusChipVariant(propertyData) === "stored"
            ? (host ? Qt.alpha(host.scopeBadgeBorderColor, 0.96) : "#60CDFF")
            : (host ? Qt.alpha(host.inlineLabelColor, 0.78) : "#bdc5d3");
    }

    function _statusChipTextColor(propertyData) {
        return root._statusChipVariant(propertyData) === "stored"
            ? (host ? host.scopeBadgeTextColor : "#f2f4f8")
            : (host ? host.inlineLabelColor : "#d0d5de");
    }

    function _isPathPointerPathProperty(propertyData) {
        return Boolean(host && host.nodeData
            && String(host.nodeData.type_id || "") === "io.path_pointer"
            && String(propertyData && propertyData.key || "") === "path");
    }

    function _pathPointerShowFullPath() {
        return Boolean(host && host.nodeData && host.nodeData.properties
            && host.nodeData.properties.show_full_path);
    }

    function _embeddedInteractiveRects() {
        if (!root._inlineDelegatesReady || !host || inlinePropertyRepeater.count <= 0)
            return [];
        var rectLists = [];
        for (var index = 0; index < inlinePropertyRepeater.count; index++) {
            var row = inlinePropertyRepeater.itemAt(index);
            if (!row || !row.visible)
                continue;
            var rectList = row.currentInteractiveRectList();
            if (rectList && rectList.length > 0)
                rectLists.push(rectList);
        }
        return SurfaceControlGeometry.combineRectLists(rectLists);
    }

    function _requiredTextFitNodeWidth() {
        if (!root._inlineDelegatesReady)
            return 0.0;
        var requiredWidth = 0.0;
        for (var index = 0; index < inlinePropertyRepeater.count; index++) {
            var row = inlinePropertyRepeater.itemAt(index);
            if (!row || !row.visible)
                continue;
            var rowWidth = Number(row.currentTextFitNodeWidth());
            if (isFinite(rowWidth) && rowWidth > requiredWidth)
                requiredWidth = rowWidth;
        }
        return requiredWidth;
    }

    Connections {
        target: root.host
        ignoreUnknownSignals: true

        function onInlineTextFitRequested() {
            if (!root.visible || !root.host || root.host.isCollapsed)
                return;
            var requiredWidth = Number(root._requiredTextFitNodeWidth());
            if (isFinite(requiredWidth) && requiredWidth > 0.0
                    && root.host.applyInlineTextFitWidth)
                root.host.applyInlineTextFitWidth(requiredWidth);
        }
    }

    onInlinePropertiesChanged: {
        root._inlineDelegatesReady = false;
        inlineDelegateSettleTimer.restart();
    }
    Component.onCompleted: inlineDelegateSettleTimer.restart()

    Timer {
        id: inlineDelegateSettleTimer
        interval: 0
        repeat: false
        onTriggered: root._inlineDelegatesReady = true
    }

    Item {
        id: inlineControlsColumn
        property real spacing: host ? host._inlineRowSpacing : 4
        anchors.left: parent.left
        anchors.leftMargin: host ? Number(host.surfaceMetrics.body_left_margin || 8) : 8
        anchors.right: parent.right
        anchors.rightMargin: host ? Number(host.surfaceMetrics.body_right_margin || 8) : 8
        anchors.top: parent.top
        anchors.topMargin: isFinite(root.contentTopOverride)
            ? root.contentTopOverride
            : (host ? Number(host.surfaceMetrics.body_top || 30) : 30)
        visible: inlineProperties.length > 0

        Repeater {
            id: inlinePropertyRepeater
            model: inlineProperties

            delegate: Rectangle {
                id: inlineRow
                objectName: "graphNodeInlinePropertyRow"
                readonly property var propertyData: root._presentationFor(modelData)
                property string propertyKey: String(propertyData.key || "")
                readonly property string editorKind: root._editorKind(propertyData)
                readonly property bool editorEnabled: root._editorEnabled(propertyData)
                readonly property bool displayValueAvailable: root._displayValueAvailable(propertyData)
                readonly property bool stackedEditor: root._isStackedEditor(propertyData)
                readonly property real baseRowHeight: host ? host._inlineRowHeight : 26
                readonly property string disabledReason: String(propertyData.editor_disabled_reason || "")
                readonly property real editorTextFitWidth: {
                    if (editorKind === "enum")
                        return propertyData.searchable
                            ? Number(searchableEnumEditor.textFitWidth)
                            : Number(enumEditor.textFitWidth);
                    if (editorKind === "text" || editorKind === "number")
                        return Number(valueEditor.textFitWidth);
                    if (editorKind === "path")
                        return Number(pathEditor.textFitWidth);
                    if (editorKind === "color")
                        return Number(colorEditor.textFitWidth);
                    return 0.0;
                }

                width: inlineControlsColumn.width
                height: root._rowHeightFor(propertyData)
                y: root._rowOffsetForIndex(index)
                color: "transparent"
                border.width: 0
                Accessible.name: String(propertyData.label || propertyData.key || "Property")
                Accessible.description: disabledReason

                function currentInteractiveRectList() {
                    if (!inlineRow.editorEnabled)
                        return [];
                    var editorX = Number(inlineControlsColumn.x) + Number(editorArea.x);
                    var editorY = Number(inlineControlsColumn.y)
                        + root._rowOffsetForIndex(index) + Number(editorArea.y);
                    var editorWidth = Number(editorArea.width);
                    var editorHeight = Number(editorArea.height);
                    if (inlineRow.editorKind === "toggle") {
                        editorX += Math.max(0, editorWidth - Number(toggleEditor.width));
                        editorY += Math.max(0, (editorHeight - Number(toggleEditor.height)) * 0.5);
                        editorWidth = Number(toggleEditor.width);
                        editorHeight = Number(toggleEditor.height);
                    }
                    return SurfaceControlGeometry.rectList({
                        "x": editorX,
                        "y": editorY,
                        "width": editorWidth,
                        "height": editorHeight
                    });
                }

                function currentTextFitNodeWidth() {
                    var editorWidth = Number(inlineRow.editorTextFitWidth);
                    if (!isFinite(editorWidth) || editorWidth <= 0.0)
                        return 0.0;
                    var labelWidth = Math.min(
                        root._inlineLabelMaxWidth,
                        Math.max(root._inlineLabelMinWidth, Number(inlineLabel.implicitWidth) + 4.0)
                    );
                    var outerMargins = Number(inlineControlsColumn.x)
                        + Math.max(0.0, Number(root.width)
                            - Number(inlineControlsColumn.x)
                            - Number(inlineControlsColumn.width));
                    if (!isFinite(outerMargins) || outerMargins < 0.0)
                        outerMargins = 16.0;
                    var statusWidth = statusChip.visible ? Number(statusChip.width) + 6.0 : 0.0;
                    var contentWidth = inlineRow.stackedEditor
                        ? Math.max(labelWidth + statusWidth, editorWidth)
                        : labelWidth + 6.0 + statusWidth + editorWidth;
                    return Math.ceil(outerMargins + 12.0 + contentWidth);
                }

                HoverHandler {
                    id: disabledReasonHover
                    enabled: inlineRow.disabledReason.length > 0
                }

                Common.ManagedToolTip {
                    objectName: "graphNodeInlineDisabledReasonToolTip"
                    property string propertyKey: String(inlineRow.propertyData.key || "")
                    policyBridge: root.host ? root.host.nodeHelpTooltipPolicyBridge : null
                    category: "inactive"
                    active: disabledReasonHover.hovered && inlineRow.disabledReason.length > 0
                    text: inlineRow.disabledReason
                    textFormat: Text.PlainText
                    delay: 400
                    screenStablePositioning: true
                    screenStablePlacement: root.host ? root.host.nodeHelpTooltipPlacement : "above"
                    anchorScale: root.host ? root.host.nodeHelpTooltipAnchorScale : 1.0
                    screenGap: 8
                }

                Text {
                    id: inlineLabel
                    objectName: "graphNodeInlinePropertyLabel"
                    property string propertyKey: String(inlineRow.propertyData.key || "")
                    x: 6
                    y: 0
                    width: inlineRow.stackedEditor
                        ? Math.max(0, statusChip.x - x - 6)
                        : Math.min(
                            root._inlineLabelMaxWidth,
                            Math.max(root._inlineLabelMinWidth, implicitWidth + 4)
                        )
                    height: inlineRow.stackedEditor ? inlineRow.baseRowHeight : inlineRow.height
                    text: String(inlineRow.propertyData.label || inlineRow.propertyData.key || "")
                    color: inlineRow.editorEnabled
                        ? (host ? host.inlineLabelColor : "#d0d5de")
                        : (host ? host.inlineDrivenTextColor : "#95a0b8")
                    font.pixelSize: root.graphSharedTypography
                        ? root.graphSharedTypography.inlinePropertyPixelSize
                        : 10
                    font.weight: root.graphSharedTypography
                        ? root.graphSharedTypography.inlinePropertyFontWeight
                        : Font.Normal
                    elide: Text.ElideRight
                    verticalAlignment: inlineRow.editorKind === "textarea"
                        ? Text.AlignTop
                        : Text.AlignVCenter
                    renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                }

                Rectangle {
                    id: statusChip
                    objectName: "graphNodeInlineStatusChip"
                    property string propertyKey: String(inlineRow.propertyData.key || "")
                    visible: String(inlineRow.propertyData.status_chip_text || "").length > 0
                    anchors.right: parent.right
                    anchors.rightMargin: 6
                    y: Math.max(0, (inlineRow.baseRowHeight - height) * 0.5)
                    radius: height * 0.5
                    height: Math.max(18, statusChipLabel.implicitHeight + 4)
                    width: statusChipLabel.implicitWidth + 12
                    color: root._statusChipFillColor(inlineRow.propertyData)
                    border.color: root._statusChipBorderColor(inlineRow.propertyData)

                    Text {
                        id: statusChipLabel
                        objectName: "graphNodeInlineStatusChipLabel"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.centerIn: parent
                        text: String(inlineRow.propertyData.status_chip_text || "")
                        color: root._statusChipTextColor(inlineRow.propertyData)
                        font.pixelSize: root.graphSharedTypography
                            ? root.graphSharedTypography.badgePixelSize
                            : 9
                        font.weight: root.graphSharedTypography
                            ? root.graphSharedTypography.badgeFontWeight
                            : Font.Bold
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }
                }

                Item {
                    id: editorArea
                    x: inlineRow.stackedEditor
                        ? 6
                        : Math.min(inlineRow.width - 12, inlineLabel.x + inlineLabel.width + 6)
                    y: inlineRow.stackedEditor ? inlineRow.baseRowHeight : 0
                    width: inlineRow.stackedEditor
                        ? Math.max(0, inlineRow.width - 12)
                        : Math.max(0, inlineRow.width - x - 6)
                    height: inlineRow.stackedEditor
                        ? Math.max(0, inlineRow.height - y)
                        : inlineRow.height

                    SurfaceControls.GraphSurfaceCheckBox {
                        id: toggleEditor
                        objectName: "graphNodeInlineToggleEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "toggle" && inlineRow.displayValueAvailable
                        enabled: inlineRow.editorEnabled
                        checked: Boolean(root._displayValue(inlineRow.propertyData))
                        host: root.host
                        text: ""
                        Accessible.name: inlineLabel.text
                        Accessible.description: inlineRow.disabledReason
                        onControlStarted: root._beginInteraction()
                        onClicked: root._commitInlineProperty(inlineRow.propertyData.key, checked)
                    }

                    SurfaceControls.GraphSurfaceComboBox {
                        id: enumEditor
                        objectName: "graphNodeInlineEnumEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "enum"
                            && !Boolean(inlineRow.propertyData.searchable)
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        model: inlineRow.propertyData.enum_values || []
                        currentIndex: {
                            if (!inlineRow.displayValueAvailable)
                                return -1;
                            var codes = inlineRow.propertyData.enum_codes || [];
                            if (codes.length > 0)
                                return codes.indexOf(root._displayValue(inlineRow.propertyData));
                            var values = inlineRow.propertyData.enum_values || [];
                            return values.indexOf(root._displayText(inlineRow.propertyData));
                        }
                        displayText: inlineRow.displayValueAvailable
                            ? (currentIndex >= 0 ? String(model[currentIndex]) : root._displayText(inlineRow.propertyData))
                            : "\u2014"
                        Accessible.name: inlineLabel.text
                        Accessible.description: inlineRow.disabledReason
                        onControlStarted: root._beginInteraction()
                        onActivated: function(selectedIndex) {
                            var values = inlineRow.propertyData.enum_values || [];
                            if (selectedIndex < 0 || selectedIndex >= values.length)
                                return;
                            var codes = inlineRow.propertyData.enum_codes || [];
                            root._commitInlineProperty(
                                inlineRow.propertyData.key,
                                codes.length === values.length
                                    ? codes[selectedIndex]
                                    : String(values[selectedIndex])
                            );
                        }
                    }

                    SurfaceControls.GraphSurfaceIntervalFields {
                        id: intervalFieldsEditor
                        objectName: "graphNodeInlineIntervalFieldsEditor"
                        anchors.fill: parent
                        visible: inlineRow.editorKind === "interval_fields"
                        propertyKey: String(inlineRow.propertyData.key || "")
                        editorEnabled: inlineRow.editorEnabled
                        host: root.host
                        value: root._displayValue(inlineRow.propertyData)
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    SurfaceControls.GraphSurfaceListEditor {
                        id: listEditor
                        objectName: "graphNodeInlineListEditor"
                        anchors.fill: parent
                        visible: inlineRow.editorKind === "list"
                        propertyKey: String(inlineRow.propertyData.key || "")
                        editorEnabled: inlineRow.editorEnabled
                        host: root.host
                        values: root._displayValue(inlineRow.propertyData) || []
                        itemType: String(inlineRow.propertyData.list_item_type || "str")
                        enumValues: inlineRow.propertyData.list_item_enum_values || []
                        enumCodes: inlineRow.propertyData.list_item_enum_codes || []
                        exactSelectors: Boolean(inlineRow.propertyData.exact_selectors)
                        minimum: inlineRow.propertyData.list_item_minimum
                        maximum: inlineRow.propertyData.list_item_maximum
                        stepSize: Number(inlineRow.propertyData.list_item_step || 0)
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    SurfaceControls.GraphSurfaceSearchableComboBox {
                        id: searchableEnumEditor
                        objectName: "graphNodeInlineSearchableEnumEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "enum"
                            && Boolean(inlineRow.propertyData.searchable)
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        model: inlineRow.propertyData.enum_values || []
                        optionCodes: inlineRow.propertyData.enum_codes || []
                        exactSelectors: Boolean(inlineRow.propertyData.exact_selectors)
                        selectedValue: inlineRow.displayValueAvailable
                            ? root._displayValue(inlineRow.propertyData)
                            : ""
                        placeholderText: "\u2014"
                        Accessible.name: inlineLabel.text
                        Accessible.description: inlineRow.disabledReason
                        onControlStarted: root._beginInteraction()
                        onValueActivated: function(value) {
                            var values = inlineRow.propertyData.enum_values || [];
                            if (!Boolean(inlineRow.propertyData.exact_selectors) && values.indexOf(value) < 0)
                                return;
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    SurfaceControls.GraphSurfaceSlider {
                        id: sliderEditor
                        objectName: "graphNodeInlineSliderEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "slider"
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        from: Number(inlineRow.propertyData.minimum)
                        to: Number(inlineRow.propertyData.maximum)
                        stepSize: Number(inlineRow.propertyData.step) > 0
                            ? Number(inlineRow.propertyData.step)
                            : (String(inlineRow.propertyData.type) === "int" ? 1 : 0)
                        valueType: String(inlineRow.propertyData.type || "float")
                        displayValueAvailable: inlineRow.displayValueAvailable
                        showRangeCaptions: true
                        Accessible.name: inlineLabel.text
                        Accessible.description: inlineRow.disabledReason.length > 0
                            ? inlineRow.disabledReason
                            : "Minimum " + minimumCaptionText
                                + ", current " + currentCaptionText
                                + ", maximum " + maximumCaptionText + "."
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            if (!inlineRow.editorEnabled)
                                return;
                            root._commitInlineProperty(
                                inlineRow.propertyData.key,
                                String(inlineRow.propertyData.type) === "int" ? Math.round(value) : value
                            );
                        }
                    }

                    Binding {
                        target: sliderEditor
                        property: "value"
                        value: inlineRow.displayValueAvailable
                            ? Number(root._displayValue(inlineRow.propertyData))
                            : (Number(sliderEditor.from) + Number(sliderEditor.to)) * 0.5
                        when: sliderEditor.visible && !sliderEditor.interactionActive
                        restoreMode: Binding.RestoreNone
                    }

                    SurfaceControls.GraphSurfaceIntervalSlider {
                        id: intervalEditor
                        objectName: "graphNodeInlineIntervalSliderEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "interval_slider"
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        from: Number(inlineRow.propertyData.minimum)
                        to: Number(inlineRow.propertyData.maximum)
                        stepSize: Math.max(0, Number(inlineRow.propertyData.step) || 0)
                        semanticStart: {
                            var value = root._displayValue(inlineRow.propertyData);
                            return value && value.start !== undefined ? Number(value.start) : Number(from);
                        }
                        semanticEnd: {
                            var value = root._displayValue(inlineRow.propertyData);
                            return value && value.end !== undefined ? Number(value.end) : Number(to);
                        }
                        displayValueAvailable: inlineRow.displayValueAvailable
                        intervalDirection: String(
                            inlineRow.propertyData.interval_direction || "increasing"
                        )
                        valueType: "float"
                        Accessible.name: inlineLabel.text
                        Accessible.description: {
                            var value = root._displayValue(inlineRow.propertyData);
                            var semantic = value && value.start !== undefined && value.end !== undefined
                                ? "Start " + String(value.start) + ", End " + String(value.end) + "."
                                : "Start and End unavailable.";
                            return inlineRow.disabledReason.length > 0
                                ? semantic + " " + inlineRow.disabledReason
                                : semantic;
                        }
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(intervalValue) {
                            if (!inlineRow.editorEnabled)
                                return;
                            root._commitInlineProperty(inlineRow.propertyData.key, intervalValue);
                        }
                    }

                    SurfaceControls.GraphSurfaceTextField {
                        id: valueEditor
                        objectName: "graphNodeInlineValueEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: inlineRow.editorKind === "text" || inlineRow.editorKind === "number"
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        text: root._displayText(inlineRow.propertyData)
                        Accessible.name: inlineLabel.text
                        Accessible.description: inlineRow.disabledReason
                        onControlStarted: root._beginInteraction()
                        onAccepted: root._commitInlineProperty(inlineRow.propertyData.key, text)
                        onEditingFinished: root._commitInlineProperty(inlineRow.propertyData.key, text)
                    }

                    SurfaceControls.GraphSurfacePathEditor {
                        id: pathEditor
                        visible: inlineRow.editorKind === "path"
                        anchors.fill: parent
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        propertyKey: String(inlineRow.propertyData.key || "")
                        committedText: root._displayText(inlineRow.propertyData)
                        shortenDisplayPathWhenInactive: root._isPathPointerPathProperty(inlineRow.propertyData)
                            && !root._pathPointerShowFullPath()
                        fieldObjectName: "graphNodeInlinePathEditor"
                        browseButtonObjectName: "graphNodeInlinePathBrowseButton"
                        browsePathResolver: function(currentPath) {
                            return host && host.browseNodePropertyPath
                                ? host.browseNodePropertyPath(inlineRow.propertyData.key, currentPath)
                                : "";
                        }
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    SurfaceControls.GraphSurfaceColorEditor {
                        id: colorEditor
                        visible: inlineRow.editorKind === "color"
                        anchors.fill: parent
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        propertyKey: String(inlineRow.propertyData.key || "")
                        committedText: root._displayText(inlineRow.propertyData)
                        fieldObjectName: "graphNodeInlineColorEditor"
                        pickButtonObjectName: "graphNodeInlineColorPickerButton"
                        colorResolver: function(currentValue) {
                            return host && host.pickNodePropertyColor
                                ? host.pickNodePropertyColor(inlineRow.propertyData.key, currentValue)
                                : "";
                        }
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    SurfaceControls.GraphSurfaceTextareaEditor {
                        id: textareaEditor
                        visible: inlineRow.editorKind === "textarea"
                        anchors.fill: parent
                        enabled: inlineRow.editorEnabled
                        host: root.host
                        propertyKey: String(inlineRow.propertyData.key || "")
                        committedText: root._displayText(inlineRow.propertyData)
                        fieldObjectName: "graphNodeInlineTextareaEditor"
                        onControlStarted: root._beginInteraction()
                        onCommitRequested: function(value) {
                            root._commitInlineProperty(inlineRow.propertyData.key, value);
                        }
                    }

                    Common.SecretEditor {
                        id: secretEditor
                        objectName: "graphNodeInlineSecretEditor"
                        property string propertyKey: String(inlineRow.propertyData.key || "")
                        anchors.fill: parent
                        visible: inlineRow.editorKind === "secret"
                        editorEnabled: inlineRow.editorEnabled
                        hasValue: Boolean(
                            root._displayValue(inlineRow.propertyData)
                            && root._displayValue(inlineRow.propertyData).has_value
                        )
                        accessibleName: inlineLabel.text
                        textColor: host ? host.inlineLabelColor : "#d0d5de"
                        mutedTextColor: host ? host.inlineDrivenTextColor : "#95a0b8"
                        fieldColor: host ? host.inlineRowColor : "#24262c"
                        borderColor: host ? host.inlineRowBorderColor : "#515968"
                        accentColor: host ? host.scopeBadgeColor : "#2f8cff"
                        onReplaceRequested: function(plaintext) {
                            root._beginInteraction()
                            if (host && host.nodeData)
                                host.sensitivePropertyReplaceRequested(
                                    String(host.nodeData.node_id || ""),
                                    inlineRow.propertyData.key,
                                    plaintext
                                )
                        }
                        onClearRequested: {
                            root._beginInteraction()
                            if (host && host.nodeData)
                                host.sensitivePropertyClearRequested(
                                    String(host.nodeData.node_id || ""),
                                    inlineRow.propertyData.key
                                )
                        }
                    }

                    Text {
                        objectName: "graphNodeInlineUnavailablePlaceholder"
                        anchors.centerIn: parent
                        visible: !inlineRow.displayValueAvailable
                            && inlineRow.editorKind === "toggle"
                        text: "\u2014"
                        color: host ? host.inlineDrivenTextColor : "#95a0b8"
                        font.pixelSize: root.graphSharedTypography
                            ? root.graphSharedTypography.inlinePropertyPixelSize
                            : 10
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }
                }
            }
        }
    }
}
