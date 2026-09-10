import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../shell" as ShellControls
import "TabularSurfaceUtils.js" as TabularUtils
import "../../common/TooltipCopy.js" as TooltipCopy

Item {
    id: surface
    objectName: "contentFullscreenTabularSurface"
    property var payload: ({})
    property var bridgeRef: null
    property var themePalette: ({})
    property var activePreview: ({})
    property string searchText: ""
    property string filterText: ""
    property string sortColumn: ""
    property bool sortDescending: false
    property string lastCopiedText: ""
    property var lastExportResult: ({})
    property var tableViewState: ({})
    property var selectedColumns: []
    property bool windowLoading: false
    property string currentWindowRequestId: ""
    readonly property string previewState: String(activePreview.state || "")
    readonly property string previewKind: TabularUtils.previewKind(activePreview)
    readonly property bool tableMode: previewKind === "table"
    readonly property bool arrayMode: previewKind === "array"
    readonly property bool ready: previewState === "ready"
    readonly property bool exportAvailable: ready && bridgeRef && bridgeRef.export_tabular_visible_rows
    readonly property color panelColor: String(themePalette.panel_bg || "#1b1d22")
    readonly property color panelAltColor: String(themePalette.panel_alt_bg || themePalette.input_bg || "#22242a")
    readonly property color toolbarColor: String(themePalette.toolbar_bg || themePalette.tab_bg || "#2a2d34")
    readonly property color inputColor: String(themePalette.input_bg || "#22242a")
    readonly property color borderColor: String(themePalette.input_border || themePalette.border || "#3a4355")
    readonly property color chromeBorderColor: String(themePalette.border || themePalette.input_border || "#3a4355")
    readonly property color textColor: String(themePalette.panel_fg || themePalette.input_fg || "#eef3ff")
    readonly property color inputTextColor: String(themePalette.input_fg || themePalette.panel_fg || "#eef3ff")
    readonly property color titleColor: String(themePalette.panel_title_fg || themePalette.input_fg || "#eef3ff")
    readonly property color mutedColor: String(themePalette.muted_fg || "#95a0b8")
    readonly property color accentColor: String(themePalette.accent || "#2f89ff")
    readonly property color accentStrongColor: String(themePalette.accent_strong || themePalette.accent || "#2f89ff")
    readonly property color hoverColor: String(themePalette.hover || themePalette.tab_bg || "#33373f")
    readonly property color pressedColor: String(themePalette.pressed || themePalette.hover || "#2d3139")
    readonly property color scrollbarColor: String(themePalette.scrollbar_handle || themePalette.input_border || "#4d5361")
    readonly property int rowLimit: TabularUtils.rowLimit(activePreview, 50)
    readonly property int columnLimit: TabularUtils.columnLimit(activePreview, 50)
    readonly property int rowOffset: TabularUtils.rowOffset(activePreview)
    readonly property int columnOffset: TabularUtils.columnOffset(activePreview)

    function syncFromPayload() {
        activePreview = TabularUtils.previewPayload(payload);
        tableViewState = TabularUtils.tableViewState(payload);
        selectedColumns = payload && payload.tabular_selected_columns
            ? payload.tabular_selected_columns
            : (payload && payload.properties && payload.properties.tabular_selected_columns
                ? payload.properties.tabular_selected_columns
                : []);
        var columns = TabularUtils.columns(activePreview);
        if (!sortColumn.length && columns.length > 0)
            sortColumn = String(columns[0] || "");
    }

    function _requestPayload(rowOffsetValue, columnOffsetValue) {
        var request = {
            "row_offset": Math.max(0, Math.floor(Number(rowOffsetValue || 0))),
            "row_limit": Math.max(1, Math.floor(Number(rowLimit || 50))),
            "column_offset": Math.max(0, Math.floor(Number(columnOffsetValue || 0))),
            "column_limit": Math.max(1, Math.floor(Number(columnLimit || 50)))
        };
        if (searchText.trim().length > 0)
            request.search = searchText.trim();
        if (filterText.trim().length > 0)
            request.filters = {"text": filterText.trim()};
        if (tableMode && sortColumn.trim().length > 0)
            request.sort = {"column": sortColumn.trim(), "descending": sortDescending};
        return request;
    }

    function requestWindow(rowOffsetValue, columnOffsetValue) {
        if (!bridgeRef)
            return false;
        var request = _requestPayload(rowOffsetValue, columnOffsetValue);
        var response = ({});
        if (tableMode && bridgeRef.request_tabular_window)
            response = bridgeRef.request_tabular_window(request);
        else if (arrayMode && bridgeRef.request_tabular_slice_2d)
            response = bridgeRef.request_tabular_slice_2d(request);
        else if (arrayMode && bridgeRef.request_tabular_array_slice)
            response = bridgeRef.request_tabular_array_slice(request);
        else
            return false;
        if (response && typeof response === "object") {
            if (String(response.state || "") === "loading") {
                // Cold cache: keep the current rows; the resolved window
                // arrives via tabularWindowReady once the worker finishes.
                currentWindowRequestId = String(response.request_id || "");
                windowLoading = true;
                return true;
            }
            currentWindowRequestId = "";
            windowLoading = false;
            activePreview = response;
        }
        return true;
    }

    Connections {
        target: surface.bridgeRef
        ignoreUnknownSignals: true
        function onTabularWindowReady(requestId, payload) {
            if (surface.currentWindowRequestId.length === 0
                    || String(requestId || "") !== surface.currentWindowRequestId)
                return;
            surface.currentWindowRequestId = "";
            surface.windowLoading = false;
            if (payload && typeof payload === "object" && String(payload.state || "") === "ready")
                surface.activePreview = payload;
            else if (payload && typeof payload === "object" && String(payload.state || "") === "error")
                surface.activePreview = payload;
        }
    }

    function saveTableViewState(state) {
        var normalized = state && typeof state === "object" ? state : ({});
        tableViewState = normalized;
        if (bridgeRef && bridgeRef.save_tabular_table_view_state)
            return Boolean(bridgeRef.save_tabular_table_view_state(normalized));
        return false;
    }

    function saveSelectedColumns(columns) {
        var normalized = columns && columns.length !== undefined ? columns : [];
        selectedColumns = normalized;
        if (bridgeRef && bridgeRef.save_tabular_selected_columns)
            return Boolean(bridgeRef.save_tabular_selected_columns(normalized));
        return false;
    }

    function requestNextRows() {
        return requestWindow(rowOffset + rowLimit, columnOffset);
    }

    function requestPreviousRows() {
        return requestWindow(Math.max(0, rowOffset - rowLimit), columnOffset);
    }

    function requestNextColumns() {
        return requestWindow(rowOffset, columnOffset + columnLimit);
    }

    function requestPreviousColumns() {
        return requestWindow(rowOffset, Math.max(0, columnOffset - columnLimit));
    }

    function applyQuery() {
        return requestWindow(rowOffset, columnOffset);
    }

    function copySelection() {
        lastCopiedText = dataGrid.copySelection();
        return lastCopiedText;
    }

    function _copyObject(value) {
        var source = value && typeof value === "object" ? value : ({});
        var output = {};
        for (var key in source)
            output[key] = source[key];
        return output;
    }

    function _activeExportRequest() {
        var window = TabularUtils.windowPayload(activePreview);
        var request = window && window.request && typeof window.request === "object"
            ? _copyObject(window.request)
            : _requestPayload(rowOffset, columnOffset);
        return {
            "preview_kind": previewKind,
            "request": request
        };
    }

    function exportVisibleRows() {
        if (!bridgeRef || !bridgeRef.export_tabular_visible_rows || !ready)
            return false;
        var result = bridgeRef.export_tabular_visible_rows(_activeExportRequest());
        lastExportResult = result && typeof result === "object" ? result : ({});
        return Boolean(lastExportResult.ok);
    }

    onPayloadChanged: syncFromPayload()
    Component.onCompleted: syncFromPayload()

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            radius: 6
            color: surface.toolbarColor
            border.width: 1
            border.color: surface.chromeBorderColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 10
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 8
                    Layout.preferredHeight: 8
                    radius: 4
                    color: surface.ready ? surface.accentColor : surface.mutedColor
                    opacity: surface.ready ? 1.0 : 0.65
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 2

                    Text {
                        objectName: "contentFullscreenTabularSummary"
                        Layout.fillWidth: true
                        text: surface.ready
                            ? TabularUtils.visibleSummary(surface.activePreview)
                            : String(surface.activePreview.message || "Tabular preview is waiting for a bounded window.")
                        color: surface.titleColor
                        font.pixelSize: 13
                        font.bold: true
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                        Layout.fillWidth: true
                        text: surface.ready
                            ? (surface.arrayMode ? "Array slice" : "Table window")
                                + "  rows " + surface.rowOffset + "-" + (surface.rowOffset + Math.max(0, surface.rowLimit - 1))
                                + "  columns " + surface.columnOffset + "-" + (surface.columnOffset + Math.max(0, surface.columnLimit - 1))
                            : "Resolve a preview window to inspect bounded tabular data."
                        color: surface.mutedColor
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularCopyButton"
                    text: "Copy"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.copy_selection")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.copy_selection")
                    enabled: surface.ready
                    onClicked: surface.copySelection()
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularExportButton"
                    text: "Export"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.export_visible_window")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.export_visible_window")
                    enabled: surface.exportAvailable
                    onClicked: surface.exportVisibleRows()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            radius: 6
            color: Qt.alpha(surface.panelAltColor, 0.94)
            border.width: 1
            border.color: surface.borderColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 6

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularPreviousRowsButton"
                    text: "Prev rows"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.previous_row_window")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.previous_row_window")
                    enabled: surface.ready && surface.rowOffset > 0
                    onClicked: surface.requestPreviousRows()
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularNextRowsButton"
                    text: "Next rows"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.next_row_window")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.next_row_window")
                    enabled: surface.ready
                    onClicked: surface.requestNextRows()
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularPreviousColumnsButton"
                    text: "Prev cols"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.previous_column_window")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.previous_column_window")
                    enabled: surface.ready && surface.columnOffset > 0
                    onClicked: surface.requestPreviousColumns()
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularNextColumnsButton"
                    text: "Next cols"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.next_column_window")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.next_column_window")
                    enabled: surface.ready
                    onClicked: surface.requestNextColumns()
                }

                TextField {
                    id: searchField
                    objectName: "contentFullscreenTabularSearchField"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 180
                    Layout.preferredHeight: 30
                    placeholderText: "Search"
                    text: surface.searchText
                    selectByMouse: true
                    color: surface.inputTextColor
                    placeholderTextColor: surface.mutedColor
                    selectionColor: surface.accentStrongColor
                    selectedTextColor: surface.inputTextColor
                    font.pixelSize: 11
                    onTextChanged: surface.searchText = text
                    onAccepted: surface.applyQuery()
                    background: Rectangle {
                        radius: 4
                        color: surface.inputColor
                        border.width: 1
                        border.color: searchField.activeFocus ? surface.accentColor : surface.borderColor
                    }
                }

                TextField {
                    id: filterField
                    objectName: "contentFullscreenTabularFilterField"
                    Layout.preferredWidth: 160
                    Layout.preferredHeight: 30
                    placeholderText: "Filter"
                    text: surface.filterText
                    selectByMouse: true
                    color: surface.inputTextColor
                    placeholderTextColor: surface.mutedColor
                    selectionColor: surface.accentStrongColor
                    selectedTextColor: surface.inputTextColor
                    font.pixelSize: 11
                    onTextChanged: surface.filterText = text
                    onAccepted: surface.applyQuery()
                    background: Rectangle {
                        radius: 4
                        color: surface.inputColor
                        border.width: 1
                        border.color: filterField.activeFocus ? surface.accentColor : surface.borderColor
                    }
                }

                ComboBox {
                    id: sortColumnCombo
                    objectName: "contentFullscreenTabularSortColumnCombo"
                    Layout.preferredWidth: 160
                    Layout.preferredHeight: 30
                    enabled: surface.tableMode && surface.ready
                    model: TabularUtils.columns(surface.activePreview)
                    font.pixelSize: 11
                    palette.buttonText: surface.inputTextColor
                    palette.text: surface.inputTextColor
                    palette.highlight: surface.accentStrongColor
                    palette.highlightedText: surface.titleColor
                    palette.base: surface.inputColor
                    palette.window: surface.panelColor
                    onActivated: surface.sortColumn = String(currentText || "")

                    indicator: Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 9
                        anchors.verticalCenter: parent.verticalCenter
                        text: "v"
                        color: sortColumnCombo.enabled ? surface.mutedColor : Qt.alpha(surface.mutedColor, 0.55)
                        font.pixelSize: 10
                        font.bold: true
                    }

                    contentItem: Text {
                        leftPadding: 8
                        rightPadding: 24
                        text: sortColumnCombo.displayText.length > 0 ? sortColumnCombo.displayText : "Sort column"
                        color: sortColumnCombo.enabled ? surface.inputTextColor : Qt.alpha(surface.mutedColor, 0.7)
                        font: sortColumnCombo.font
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    background: Rectangle {
                        radius: 4
                        color: surface.inputColor
                        border.width: 1
                        border.color: sortColumnCombo.activeFocus ? surface.accentColor : surface.borderColor
                    }

                    delegate: ItemDelegate {
                        width: ListView.view ? ListView.view.width : sortColumnCombo.width
                        highlighted: sortColumnCombo.highlightedIndex === index
                        contentItem: Text {
                            text: String(modelData || "")
                            color: highlighted ? surface.titleColor : surface.inputTextColor
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            radius: 3
                            color: highlighted ? surface.hoverColor : "transparent"
                        }
                    }

                    popup: Popup {
                        y: sortColumnCombo.height + 4
                        width: sortColumnCombo.width
                        padding: 4
                        background: Rectangle {
                            radius: 6
                            color: surface.panelColor
                            border.width: 1
                            border.color: surface.borderColor
                        }
                        contentItem: ListView {
                            clip: true
                            implicitHeight: Math.min(contentHeight, 220)
                            model: sortColumnCombo.popup.visible ? sortColumnCombo.delegateModel : null
                            currentIndex: sortColumnCombo.highlightedIndex
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                                interactive: true
                                contentItem: Rectangle {
                                    implicitWidth: 7
                                    radius: 3
                                    color: surface.scrollbarColor
                                }
                                background: Rectangle {
                                    color: "transparent"
                                }
                            }
                        }
                    }
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularSortDirectionButton"
                    text: surface.sortDescending ? "Desc" : "Asc"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.sort_direction")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.sort_direction")
                    selectedStyle: surface.sortDescending
                    enabled: surface.tableMode && surface.ready
                    onClicked: {
                        surface.sortDescending = !surface.sortDescending;
                        surface.applyQuery();
                    }
                }

                ShellControls.ShellButton {
                    objectName: "contentFullscreenTabularApplyQueryButton"
                    text: "Apply"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "tabular.apply_query")
                    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "tabular.apply_query")
                    selectedStyle: surface.searchText.trim().length > 0 || surface.filterText.trim().length > 0
                    enabled: surface.ready
                    onClicked: surface.applyQuery()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            TabularTableViewport {
                id: dataGrid
                objectName: "contentFullscreenTabularGrid"
                Layout.fillWidth: true
                Layout.fillHeight: true
                compact: false
                preview: surface.activePreview
                tableViewState: surface.tableViewState
                selectedColumns: surface.selectedColumns
                themePalette: surface.themePalette
                objectNamePrefix: "contentFullscreenTabular"
                onTableViewStateEdited: function(state) {
                    surface.saveTableViewState(state);
                }
                onSelectedColumnsEdited: function(columns) {
                    surface.saveSelectedColumns(columns);
                }
            }

            Rectangle {
                objectName: "contentFullscreenTabularMetadataSidebar"
                Layout.preferredWidth: 250
                Layout.fillHeight: true
                radius: 6
                color: surface.panelAltColor
                border.width: 1
                border.color: surface.borderColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        radius: 4
                        color: surface.toolbarColor
                        border.width: 1
                        border.color: surface.chromeBorderColor

                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 9
                            anchors.right: parent.right
                            anchors.rightMargin: 9
                            anchors.verticalCenter: parent.verticalCenter
                            text: surface.arrayMode ? "Array Slice" : "Schema"
                            color: surface.titleColor
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        objectName: "contentFullscreenTabularArraySliceControls"
                        Layout.fillWidth: true
                        visible: surface.arrayMode
                        text: {
                            var arrayInfo = surface.activePreview.array || ({});
                            var shape = arrayInfo.shape && arrayInfo.shape.length !== undefined
                                ? arrayInfo.shape.join(" x ")
                                : "";
                            return "2D slice axes 0 and 1"
                                + (shape.length > 0 ? "\nShape " + shape : "")
                                + (arrayInfo.dtype ? "\nDtype " + arrayInfo.dtype : "");
                        }
                        color: surface.mutedColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: TabularUtils.metadataPairs(surface.activePreview, 10)
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(44, pairColumn.implicitHeight + 12)
                            radius: 4
                            color: surface.inputColor
                            border.width: 1
                            border.color: Qt.alpha(surface.borderColor, 0.72)

                            Column {
                                id: pairColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: String(modelData.label || "")
                                    color: surface.mutedColor
                                    font.pixelSize: 10
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: String(modelData.value || "")
                                    color: surface.textColor
                                    font.pixelSize: 11
                                    wrapMode: Text.WrapAnywhere
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    Item {
                        Layout.fillHeight: true
                    }
                }
            }
        }
    }
}
