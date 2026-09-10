import QtQuick 2.15
import QtQuick.Controls 2.15
import ".." as GraphShared

// Editable Panel. The shared host owns chrome, ports, shadow,
// selection, and resizing; this surface only renders the text/tree content.
GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphPanelSurface"

    readonly property string nodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string panelValue: propString("value", "")
    readonly property int panelMode: Math.round(propNumber("mode", 0)) === 1 ? 1 : 0
    readonly property int panelFontSize: Math.max(8, Math.min(72, Math.round(propNumber("font_size", 12))))
    readonly property int panelAlignment: Math.max(0, Math.min(2, Math.round(propNumber("alignment", 2))))
    readonly property bool panelAutoResize: propBool("auto_resize", true)
    readonly property string panelInterpretation: propString("interpretation", "text")
    readonly property string interpretationLabel: inputConnected ? "Input"
        : panelInterpretation === "number" ? "Number"
        : panelInterpretation === "auto" ? "Auto" : "Text"
    readonly property real panelFontPixelSize: Math.round(surface.panelFontSize * 4 / 3)
    readonly property bool panelEditable: !!host && !host.graphReadOnly
        && !host.authorLocked && !host.surfaceInteractionLocked
    readonly property bool inputConnected: _inputConnected()
    readonly property bool structuredMode: inputConnected || panelMode === 1
    readonly property var runtimeRows: _runtimeRows()
    readonly property var displayRows: inputConnected
        ? runtimeRows
        : (panelMode === 1 ? _authoredRows(panelValue) : [])
    readonly property int displayRowCount: displayRows.length
    readonly property bool placeholderVisible: structuredMode
        ? displayRows.length === 0
        : panelValue.length === 0
    readonly property string placeholderText: "Double click to edit..."
    readonly property var panelEditorPayload: ({
        "value": surface.panelValue,
        "mode": surface.panelMode,
        "font_size": surface.panelFontSize,
        "alignment": surface.panelAlignment,
        "auto_resize": surface.panelAutoResize,
        "interpretation": surface.panelInterpretation,
        "input_connected": surface.inputConnected
    })

    property bool panelEditorOpen: false
    property bool autoFitPending: false

    readonly property var embeddedInteractiveRects: []
    readonly property var surfaceActions: [
        {
            "id": "panel_font_increase",
            "label": "Increase font size",
            "description": "Make the text a bit bigger.",
            "icon": "text-increase",
            "kind": "surface",
            "enabled": surface.panelEditable && surface.panelFontSize < 72,
            "primary": true,
            "separator_after": false
        },
        {
            "id": "panel_font_decrease",
            "label": "Decrease font size",
            "description": "Make the text a bit smaller.",
            "icon": "text-decrease",
            "kind": "surface",
            "enabled": surface.panelEditable && surface.panelFontSize > 8,
            "primary": true,
            "separator_after": true
        },
        {
            "id": "panel_align_left",
            "label": "Align left",
            "description": "Align the content with the left margin.",
            "icon": "format-align-left",
            "kind": "surface",
            "enabled": surface.panelEditable,
            "checked": surface.panelAlignment === 0,
            "primary": true
        },
        {
            "id": "panel_align_right",
            "label": "Align right",
            "description": "Align the content with the right margin.",
            "icon": "format-align-right",
            "kind": "surface",
            "enabled": surface.panelEditable,
            "checked": surface.panelAlignment === 1,
            "primary": true,
            "separator_after": true
        },
        {
            "id": "panel_fit_width",
            "label": "Fit width",
            "description": "Adjust the node to fit the text without line breaks.",
            "icon": "fit-width",
            "kind": "surface",
            "enabled": surface.panelEditable,
            "primary": true
        },
        {
            "id": "panel_fit_height",
            "label": "Fit height",
            "description": "Adjust the node to fit the content without a scrollbar.",
            "icon": "fit-height",
            "kind": "surface",
            "enabled": surface.panelEditable,
            "primary": true
        }
    ]

    function _inputConnected() {
        var ports = surface.host && surface.host.inputPorts ? surface.host.inputPorts : [];
        for (var index = 0; index < ports.length; ++index) {
            var port = ports[index] || ({});
            if (String(port.key || "") === "input")
                return Boolean(port.connected);
        }
        return false;
    }

    function _runtimeRows() {
        if (!surface.host || !surface.host.executionFacts || !surface.nodeId.length)
            return [];
        var lookup = surface.host.executionFacts.portValuePreviewLookup || ({});
        var nodePreview = lookup[surface.nodeId] || ({});
        var outputPreview = nodePreview.output || ({});
        var sourceRows = outputPreview.rows || [];
        var bridge = surface.host.canvasItem ? surface.host.canvasItem.canvasStateBridge : null;
        if (bridge && bridge.panel_display_rows) {
            try {
                var completeRows = bridge.panel_display_rows(surface.nodeId) || [];
                if (completeRows.length > 0
                        || String(outputPreview.state || "") === "current"
                        || String(outputPreview.state || "") === "empty")
                    sourceRows = completeRows;
            } catch (error) {
                sourceRows = outputPreview.rows || [];
            }
        }
        var rows = [];
        for (var index = 0; index < sourceRows.length; ++index) {
            var row = sourceRows[index] || ({});
            var kind = String(row.kind || "");
            if (kind === "branch") {
                rows.push({"kind": "branch", "path": String(row.path || "")});
            } else if (kind === "item") {
                var rowIndex = Math.round(Number(row.index));
                rows.push({
                    "kind": "item",
                    "path": String(row.path || ""),
                    "index": isFinite(rowIndex) ? rowIndex : 0,
                    "text": String(row.text === undefined || row.text === null ? "" : row.text)
                });
            }
        }
        return rows;
    }

    function _authoredRows(value) {
        var text = String(value || "");
        if (!text.length)
            return [];
        var lines = text.split(/\r?\n/);
        var rows = [];
        var path = "0";
        var itemIndex = 0;
        var branchStarted = false;
        for (var index = 0; index < lines.length; ++index) {
            var line = String(lines[index]);
            var trimmed = line.trim();
            if (trimmed.charAt(0) === "*") {
                path = trimmed.substring(1).trim() || "0";
                itemIndex = 0;
                rows.push({"kind": "branch", "path": path});
                branchStarted = true;
            } else {
                if (!branchStarted) {
                    rows.push({"kind": "branch", "path": path});
                    branchStarted = true;
                }
                rows.push({"kind": "item", "path": path, "index": itemIndex,
                    "text": surface.panelInterpretation === "text" ? line : trimmed});
                ++itemIndex;
            }
        }
        return rows;
    }

    function _resolvedTextAlignment() {
        if (surface.panelAlignment === 0)
            return Text.AlignLeft;
        if (surface.panelAlignment === 1)
            return Text.AlignRight;
        return Text.AlignHCenter;
    }

    function requestInlineEditAt(_localX, _localY) {
        return surface.host && surface.host.dispatchSurfaceAction
            ? surface.host.dispatchSurfaceAction("panel_edit")
            : false;
    }

    function _commitProperty(key, value) {
        if (!surface.host || !surface.nodeId.length || surface.host.graphReadOnly)
            return false;
        surface.host.inlinePropertyCommitted(surface.nodeId, String(key || ""), value);
        return true;
    }

    function _copyPanelText(asTree) {
        if (!surface.host || !surface.nodeId.length)
            return false;
        var copied = "";
        if (!surface.inputConnected) {
            copied = surface._authoredCopyText(Boolean(asTree));
        } else {
            var canvasItem = surface.host.canvasItem;
            var bridge = canvasItem ? canvasItem.canvasStateBridge : null;
            if (!bridge || !bridge.panel_copy_text)
                return false;
            try {
                copied = bridge.panel_copy_text(surface.nodeId, Boolean(asTree));
            } catch (error) {
                return false;
            }
        }
        clipboardBuffer.text = String(copied === undefined || copied === null ? "" : copied);
        clipboardBuffer.selectAll();
        clipboardBuffer.copy();
        clipboardBuffer.deselect();
        clipboardBuffer.text = "";
        return true;
    }

    function _authoredCopyText(asTree) {
        if (surface.panelMode !== 1)
            return surface.panelValue;
        var rows = surface._authoredRows(surface.panelValue);
        var lines = [];
        for (var index = 0; index < rows.length; ++index) {
            var row = rows[index] || ({});
            if (String(row.kind || "") === "branch") {
                if (asTree)
                    lines.push("* " + String(row.path || ""));
            } else {
                lines.push(String(row.text === undefined ? "" : row.text));
            }
        }
        return lines.join("\n");
    }

    function _requiredContentWidth() {
        if (!surface.structuredMode)
            return Math.max(surface._minimumWidth(), Number(unwrappedTextMeasure.implicitWidth || 0) + 18);
        var characterWidth = surface.panelFontPixelSize * 0.62;
        var maximum = surface._minimumWidth();
        for (var index = 0; index < surface.displayRows.length; ++index) {
            var row = surface.displayRows[index] || ({});
            if (String(row.kind || "") === "branch") {
                maximum = Math.max(maximum, String(row.path || "").length * characterWidth + 18);
            } else {
                maximum = Math.max(
                    maximum,
                    String(row.index === undefined ? "" : row.index).length * characterWidth
                        + String(row.text || "").length * characterWidth + 58
                );
            }
        }
        return Math.ceil(maximum);
    }

    function _requiredContentHeight() {
        if (!surface.structuredMode)
            return Math.max(surface._minimumHeight(), Number(unwrappedTextMeasure.implicitHeight || 0) + 18);
        var required = 16 + interpretationHeader.height;
        for (var index = 0; index < surface.displayRows.length; ++index) {
            var row = surface.displayRows[index] || ({});
            required += String(row.kind || "") === "branch"
                ? surface.panelFontPixelSize + 14
                : surface.panelFontPixelSize + 12;
        }
        return Math.max(surface._minimumHeight(), Math.ceil(required));
    }

    function _minimumWidth() {
        return Math.max(0, Number(surface.host && surface.host.surfaceMetrics
            ? surface.host.surfaceMetrics.min_width : 0));
    }

    function _minimumHeight() {
        return Math.max(0, Number(surface.host && surface.host.surfaceMetrics
            ? surface.host.surfaceMetrics.min_height : 0));
    }

    function _resizeTo(targetWidth, targetHeight) {
        if (!surface.host || !surface.host.nodeData || !surface.nodeId.length
                || surface.host.graphReadOnly || surface.host.surfaceInteractionLocked)
            return false;
        var width = Math.max(surface._minimumWidth(), Math.min(2400, Math.ceil(Number(targetWidth) || surface.host.width)));
        var height = Math.max(surface._minimumHeight(), Math.min(1600, Math.ceil(Number(targetHeight) || surface.host.height)));
        if (Math.abs(width - Number(surface.host.width || 0)) < 0.5
                && Math.abs(height - Number(surface.host.height || 0)) < 0.5)
            return true;
        var x = Number(surface.host.nodeData.x);
        var y = Number(surface.host.nodeData.y);
        if (!isFinite(x))
            x = Number(surface.host.x) || 0;
        if (!isFinite(y))
            y = Number(surface.host.y) || 0;
        surface.host.resizeFinished(surface.nodeId, x, y, width, height);
        return true;
    }

    function _fitWidth() {
        return surface._resizeTo(surface._requiredContentWidth(), surface.host ? surface.host.height : height);
    }

    function _fitHeight() {
        return surface._resizeTo(surface.host ? surface.host.width : width, surface._requiredContentHeight());
    }

    function _fitBoth() {
        return surface._resizeTo(surface._requiredContentWidth(), surface._requiredContentHeight());
    }

    function _scheduleAutoFit() {
        if (!surface.panelAutoResize || surface.autoFitPending
                || (!surface.inputConnected && surface.panelValue.length === 0))
            return;
        surface.autoFitPending = true;
        Qt.callLater(function() {
            surface.autoFitPending = false;
            surface._fitBoth();
        });
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        if (normalized === "panel_edit") {
            if (!surface.panelEditable)
                return false;
            surface.panelEditorOpen = true;
            return true;
        }
        if (normalized === "panel_font_increase")
            return surface._commitProperty("font_size", Math.min(72, surface.panelFontSize + 1));
        if (normalized === "panel_font_decrease")
            return surface._commitProperty("font_size", Math.max(8, surface.panelFontSize - 1));
        if (normalized === "panel_align_left")
            return surface._commitProperty("alignment", surface.panelAlignment === 0 ? 2 : 0);
        if (normalized === "panel_align_right")
            return surface._commitProperty("alignment", surface.panelAlignment === 1 ? 2 : 1);
        if (normalized === "panel_fit_width")
            return surface._fitWidth();
        if (normalized === "panel_fit_height")
            return surface._fitHeight();
        if (normalized === "panel_copy")
            return surface._copyPanelText(false);
        if (normalized === "panel_copy_tree")
            return surface._copyPanelText(true);
        return false;
    }

    function acceptPanelSettings(payload) {
        surface.panelEditorOpen = false;
        if (!surface.panelEditable || !surface.host.canvasItem || !surface.nodeId.length)
            return false;
        var canvasItem = surface.host.canvasItem;
        if (!canvasItem.commitNodeSurfaceProperties)
            return false;
        var source = payload || ({});
        var updates = {
            "value": String(source.value === undefined ? surface.panelValue : source.value),
            "mode": Math.round(Number(source.mode)) === 1 ? 1 : 0,
            "font_size": Math.max(8, Math.min(72, Math.round(Number(
                source.font_size === undefined ? surface.panelFontSize : source.font_size
            )))),
            "alignment": Math.max(0, Math.min(2, Math.round(Number(
                source.alignment === undefined ? surface.panelAlignment : source.alignment
            )))),
            "auto_resize": source.auto_resize === undefined
                ? surface.panelAutoResize
                : Boolean(source.auto_resize),
            "interpretation": source.interpretation === undefined
                ? surface.panelInterpretation
                : String(source.interpretation)
        };
        var applied = Boolean(canvasItem.commitNodeSurfaceProperties(surface.nodeId, updates));
        if (applied && updates.auto_resize)
            Qt.callLater(function() { surface._fitBoth(); });
        return applied;
    }

    function cancelPanelSettings() {
        surface.panelEditorOpen = false;
    }

    onPanelValueChanged: surface._scheduleAutoFit()
    onPanelModeChanged: surface._scheduleAutoFit()
    onPanelFontSizeChanged: surface._scheduleAutoFit()
    onDisplayRowsChanged: {
        if (surface.inputConnected)
            surface._scheduleAutoFit();
    }
    Component.onCompleted: {
        if (surface.panelValue.length > 0 || surface.inputConnected)
            surface._scheduleAutoFit();
    }

    Item {
        id: panelBody
        objectName: "graphPanelBody"
        anchors.fill: parent

        Item {
            id: interpretationHeader
            objectName: "graphPanelInterpretationHeader"
            anchors.top: parent.top
            width: parent.width
            height: visible ? 34 : 0
            visible: surface.structuredMode

            Rectangle {
                objectName: "graphPanelInterpretationBadge"
                anchors.centerIn: parent
                width: badgeLabel.implicitWidth + 16
                height: 22
                radius: 11
                color: surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.08) : "#20333d"
                border.color: surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.16) : "#46555e"
                border.width: 1

                Text {
                    id: badgeLabel
                    anchors.centerIn: parent
                    text: surface.interpretationLabel
                    color: surface.host ? surface.host.inlineInputTextColor : "#f0f2f5"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
                }
            }
        }

        Text {
            id: textContent
            objectName: "graphPanelTextContent"
            anchors.fill: parent
            anchors.margins: 9
            visible: !surface.structuredMode
            text: surface.placeholderVisible ? surface.placeholderText : surface.panelValue
            color: surface.placeholderVisible
                ? (surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.56) : "#8f96a3")
                : (surface.host ? surface.host.inlineInputTextColor : "#f0f2f5")
            font.pointSize: surface.panelFontSize
            horizontalAlignment: surface._resolvedTextAlignment()
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap
            renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
        }

        ListView {
            id: dataList
            objectName: "graphPanelDataList"
            anchors.fill: parent
            anchors.topMargin: interpretationHeader.height
            visible: surface.structuredMode && surface.displayRows.length > 0
            clip: true
            model: surface.displayRows
            interactive: false
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
                required property var modelData
                required property int index
                readonly property bool branchRow: String(modelData.kind || "") === "branch"
                width: ListView.view.width
                height: branchRow ? surface.panelFontPixelSize + 14 : surface.panelFontPixelSize + 12
                color: branchRow
                    ? (surface.host ? Qt.alpha(surface.host.outlineColor, 0.22) : "#30343c")
                    : (Number(modelData.index || 0) % 2 === 0
                        ? "transparent"
                        : (surface.host ? Qt.alpha(surface.host.headerTextColor, 0.035) : "#08000000"))

                Text {
                    objectName: "graphPanelBranchPath"
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    visible: parent.branchRow
                    text: String(parent.modelData.path || "")
                    color: surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.72) : "#aab1bd"
                    font.pointSize: surface.panelFontSize
                    font.family: "Consolas"
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
                }

                Rectangle {
                    id: itemIndexLabel
                    objectName: "graphPanelIndexColumn"
                    width: 38
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    visible: !parent.branchRow
                    color: surface.host ? Qt.alpha(surface.host.outlineColor, 0.10) : "#10000000"

                    Text {
                        objectName: "graphPanelItemIndex"
                        anchors.fill: parent
                        text: String(parent.parent.modelData.index === undefined
                            ? ""
                            : parent.parent.modelData.index)
                        color: surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.58) : "#8f96a3"
                        font.pointSize: surface.panelFontSize
                        font.family: "Consolas"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
                    }
                }

                Text {
                    objectName: "graphPanelItemValue"
                    anchors.left: itemIndexLabel.right
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 12
                    anchors.rightMargin: 10
                    visible: !parent.branchRow
                    text: String(parent.modelData.text === undefined ? "" : parent.modelData.text)
                    color: surface.host ? surface.host.inlineInputTextColor : "#f0f2f5"
                    font.pointSize: surface.panelFontSize
                    font.family: "Consolas"
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
                }
            }

            ScrollBar.vertical: ScrollBar {
                objectName: "graphPanelVerticalScrollBar"
                policy: ScrollBar.AsNeeded
            }

        }

        MouseArea {
            anchors.fill: dataList
            visible: dataList.visible
            acceptedButtons: Qt.NoButton
            propagateComposedEvents: true

            onWheel: function(wheel) {
                var deltaY = wheel.angleDelta && Number(wheel.angleDelta.y) !== 0
                    ? Number(wheel.angleDelta.y)
                    : Number(wheel.pixelDelta.y);
                var step = (-deltaY / 120.0) * (surface.panelFontPixelSize + 12);
                var minimumY = Number(dataList.originY);
                var maximumY = minimumY + Math.max(0, dataList.contentHeight - dataList.height);
                dataList.contentY = Math.max(minimumY, Math.min(maximumY, dataList.contentY + step));
                wheel.accepted = true;
            }
        }

        Text {
            objectName: "graphPanelStructuredPlaceholder"
            anchors.fill: parent
            anchors.topMargin: interpretationHeader.height
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            visible: surface.structuredMode && surface.displayRows.length === 0
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            clip: true
            text: surface.placeholderText
            color: surface.host ? Qt.alpha(surface.host.inlineInputTextColor, 0.56) : "#8f96a3"
            font.pointSize: surface.panelFontSize
            renderType: surface.host ? surface.host.nodeTextRenderType : Text.CurveRendering
        }
    }

    Text {
        id: unwrappedTextMeasure
        visible: false
        text: surface.panelValue.length > 0 ? surface.panelValue : surface.placeholderText
        font.pointSize: surface.panelFontSize
        wrapMode: Text.NoWrap
    }

    // Keep the native clipboard path local to QML; no application clipboard
    // service is introduced for this node.
    TextArea {
        id: clipboardBuffer
        objectName: "graphPanelClipboardBuffer"
        x: -10000
        y: -10000
        width: 1
        height: 1
        opacity: 0
        readOnly: true
        selectByMouse: false
    }

}
