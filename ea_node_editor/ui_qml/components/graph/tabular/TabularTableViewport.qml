import QtQuick 2.15
import QtQuick.Controls 2.15
import EA.NodeEditor 1.0

Item {
    id: viewport
    objectName: "tabularTableViewport"

    property var preview: ({})
    property var tableViewState: ({})
    property bool compact: false
    property var themePalette: ({})
    property Item host: null
    property string objectNamePrefix: "tabular"
    property int selectedRow: -1
    property int selectedColumn: -1
    property var selectedColumns: []
    property bool _applyingStoredWidths: false

    readonly property int rowCount: tableModel.row_count
    readonly property int columnCount: tableModel.column_count
    readonly property int rowHeight: compact ? 20 : 26
    readonly property int headerHeight: compact ? 22 : 28
    readonly property int rowHeaderWidth: compact ? 38 : 56
    readonly property color panelColor: host ? Qt.darker(host.inlineInputBackgroundColor, 1.02) : String(themePalette.input_bg || themePalette.panel_bg || "#22242a")
    readonly property color borderColor: host ? host.inlineInputBorderColor : String(themePalette.input_border || themePalette.border || "#3a4355")
    readonly property color textColor: host ? host.inlineInputTextColor : String(themePalette.input_fg || themePalette.panel_fg || "#eef3ff")
    readonly property color mutedTextColor: host ? host.inlineDrivenTextColor : String(themePalette.muted_fg || "#95a0b8")
    readonly property color accentColor: host ? host.selectedOutlineColor : String(themePalette.accent || "#2f89ff")
    readonly property color headerFillColor: host ? Qt.alpha(borderColor, 0.28) : String(themePalette.toolbar_bg || themePalette.tab_bg || "#2a2d34")
    readonly property color rowFillColor: host ? Qt.alpha(panelColor, 0.94) : String(themePalette.input_bg || themePalette.panel_alt_bg || "#22242a")
    readonly property color alternateRowFillColor: host ? Qt.alpha(borderColor, 0.13) : String(themePalette.panel_alt_bg || themePalette.hover || "#24262c")
    readonly property color gridLineColor: host ? Qt.alpha(borderColor, 0.82) : String(themePalette.input_border || themePalette.border || "#3a4355")
    readonly property color selectedColor: Qt.alpha(accentColor, host ? 0.32 : 0.20)
    readonly property color selectedBorderColor: Qt.alpha(accentColor, host ? 0.92 : 0.80)
    readonly property color scrollbarHandleColor: String(themePalette.scrollbar_handle || themePalette.input_border || "#4d5361")

    signal cellSelected(int row, int column, string text)
    signal tableViewStateEdited(var state)
    signal selectedColumnsEdited(var columns)

    function _objectValue(value) {
        return value && typeof value === "object" ? value : ({});
    }

    function _clampColumnWidth(widthValue) {
        var numeric = Math.round(Number(widthValue || 0));
        if (!isFinite(numeric))
            numeric = compact ? 72 : 104;
        return Math.max(48, Math.min(480, numeric));
    }

    function _storedColumnWidths() {
        return _objectValue(_objectValue(tableViewState).column_widths);
    }

    function _storedColumnWidth(column) {
        var key = tableModel.column_key(column);
        var widths = _storedColumnWidths();
        if (!key || widths[key] === undefined)
            return -1;
        return _clampColumnWidth(widths[key]);
    }

    function _selectedColumnList() {
        var raw = selectedColumns && selectedColumns.length !== undefined ? selectedColumns : [];
        var result = [];
        for (var index = 0; index < raw.length; index++) {
            var normalized = String(raw[index] || "").trim();
            if (normalized.length > 0 && result.indexOf(normalized) < 0)
                result.push(normalized);
        }
        return result;
    }

    function isSelectedColumn(column) {
        var label = String(tableModel.column_label(column) || "").trim();
        return label.length > 0 && _selectedColumnList().indexOf(label) >= 0;
    }

    function toggleSelectedColumn(column) {
        if (column < 0 || column >= columnCount)
            return false;
        var label = String(tableModel.column_label(column) || "").trim();
        if (!label.length)
            return false;
        var next = _selectedColumnList();
        var index = next.indexOf(label);
        if (index >= 0)
            next.splice(index, 1);
        else
            next.push(label);
        selectedColumns = next;
        selectedColumnsEdited(next);
        return true;
    }

    function defaultColumnWidth(column) {
        var stored = _storedColumnWidth(column);
        if (stored > 0)
            return stored;
        var label = tableModel.column_label(column);
        return _clampColumnWidth((compact ? 62 : 96) + Math.min(140, String(label || "").length * 7));
    }

    function resolvedColumnWidth(column) {
        if (tableView && tableView.explicitColumnWidth) {
            var explicit = tableView.explicitColumnWidth(column);
            if (explicit >= 0)
                return _clampColumnWidth(explicit);
        }
        return defaultColumnWidth(column);
    }

    function applyStoredColumnWidths() {
        if (!tableView)
            return;
        _applyingStoredWidths = true;
        for (var column = 0; column < columnCount; column++) {
            var widthValue = _storedColumnWidth(column);
            if (widthValue > 0)
                tableView.setColumnWidth(column, widthValue);
        }
        tableView.forceLayout();
        Qt.callLater(function() { viewport._applyingStoredWidths = false; });
    }

    function captureColumnWidths() {
        if (_applyingStoredWidths || !tableView)
            return;
        var widths = {};
        var changed = false;
        var existing = _storedColumnWidths();
        for (var existingKey in existing) {
            if (Object.prototype.hasOwnProperty.call(existing, existingKey))
                widths[existingKey] = existing[existingKey];
        }
        for (var column = 0; column < columnCount; column++) {
            var explicit = tableView.explicitColumnWidth(column);
            if (explicit < 0)
                continue;
            var key = tableModel.column_key(column);
            if (!key)
                continue;
            var widthValue = _clampColumnWidth(explicit);
            if (widths[key] !== widthValue) {
                widths[key] = widthValue;
                changed = true;
            }
        }
        if (changed)
            tableViewStateEdited({"version": 1, "column_widths": widths});
    }

    function autofitColumn(column) {
        if (!tableView || column < 0 || column >= columnCount)
            return false;
        var widthValue = tableModel.autofit_width(column);
        tableView.setColumnWidth(column, _clampColumnWidth(widthValue));
        tableView.forceLayout();
        captureColumnWidths();
        return true;
    }

    function selectCell(row, column) {
        selectedRow = row;
        selectedColumn = column;
        cellSelected(row, column, tableModel.cell_text(row, column));
    }

    function copySelection() {
        if (selectedRow >= 0 && selectedColumn >= 0)
            return tableModel.cell_text(selectedRow, selectedColumn);
        var lines = [];
        var headers = [];
        for (var column = 0; column < columnCount; column++)
            headers.push(tableModel.column_label(column));
        if (headers.length > 0)
            lines.push(headers.join("\t"));
        for (var row = 0; row < rowCount; row++) {
            var values = [];
            for (var valueColumn = 0; valueColumn < columnCount; valueColumn++)
                values.push(tableModel.cell_text(row, valueColumn));
            lines.push(values.join("\t"));
        }
        return lines.join("\n");
    }

    onPreviewChanged: Qt.callLater(applyStoredColumnWidths)
    onTableViewStateChanged: Qt.callLater(applyStoredColumnWidths)

    TabularPreviewTableModel {
        id: tableModel
        preview: viewport.preview
        onPreviewChanged: Qt.callLater(viewport.applyStoredColumnWidths)
    }

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: viewport.panelColor
        border.width: 1
        border.color: viewport.borderColor
    }

    Rectangle {
        id: cornerHeader
        objectName: viewport.objectNamePrefix + "CornerHeader"
        x: 1
        y: 1
        width: viewport.rowHeaderWidth
        height: viewport.headerHeight
        color: viewport.headerFillColor
        border.width: 1
        border.color: viewport.gridLineColor
        clip: true

        Text {
            anchors.centerIn: parent
            text: "#"
            color: viewport.mutedTextColor
            font.pixelSize: viewport.compact ? 9 : 11
        }
    }

    HorizontalHeaderView {
        id: horizontalHeader
        objectName: viewport.objectNamePrefix + "HorizontalHeaderView"
        anchors.left: cornerHeader.right
        anchors.top: parent.top
        anchors.topMargin: 1
        anchors.right: parent.right
        anchors.rightMargin: 1
        height: viewport.headerHeight
        syncView: tableView
        clip: true
        resizableColumns: true

        delegate: Rectangle {
            required property int column
            required property var display
            implicitWidth: viewport.resolvedColumnWidth(column)
            implicitHeight: viewport.headerHeight
            readonly property bool selected: viewport.isSelectedColumn(column)
            color: selected ? viewport.selectedColor : viewport.headerFillColor
            border.width: 1
            border.color: selected ? viewport.selectedBorderColor : viewport.gridLineColor
            clip: true

            Text {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 8
                text: String(display || "")
                color: viewport.textColor
                font.pixelSize: viewport.compact ? 9 : 11
                font.bold: true
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }

            MouseArea {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                anchors.rightMargin: 8
                acceptedButtons: Qt.LeftButton
                onClicked: viewport.toggleSelectedColumn(column)
            }

            MouseArea {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                width: 8
                cursorShape: Qt.SplitHCursor
                acceptedButtons: Qt.LeftButton
                property real _pressX: 0
                property real _pressWidth: 0
                onPressed: function(mouse) {
                    _pressX = mouse.x;
                    _pressWidth = viewport.resolvedColumnWidth(column);
                }
                onPositionChanged: function(mouse) {
                    if (!pressed)
                        return;
                    tableView.setColumnWidth(column, viewport._clampColumnWidth(_pressWidth + mouse.x - _pressX));
                    tableView.forceLayout();
                }
                onReleased: viewport.captureColumnWidths()
                onDoubleClicked: viewport.autofitColumn(column)
            }
        }
    }

    VerticalHeaderView {
        id: verticalHeader
        objectName: viewport.objectNamePrefix + "VerticalHeaderView"
        anchors.left: parent.left
        anchors.leftMargin: 1
        anchors.top: cornerHeader.bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 1
        width: viewport.rowHeaderWidth
        syncView: tableView
        clip: true
        resizableRows: false

        delegate: Rectangle {
            required property int row
            required property var display
            implicitWidth: viewport.rowHeaderWidth
            implicitHeight: viewport.rowHeight
            color: viewport.headerFillColor
            border.width: 1
            border.color: viewport.gridLineColor
            clip: true

            Text {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                text: String(display || row)
                color: viewport.mutedTextColor
                font.pixelSize: viewport.compact ? 9 : 10
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }
    }

    TableView {
        id: tableView
        objectName: viewport.objectNamePrefix + "TableView"
        anchors.left: verticalHeader.right
        anchors.top: horizontalHeader.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 1
        anchors.bottomMargin: 1
        clip: true
        reuseItems: true
        model: tableModel
        columnSpacing: 0
        rowSpacing: 0
        resizableColumns: true
        resizableRows: false
        rowHeightProvider: function(_row) { return viewport.rowHeight; }
        columnWidthProvider: function(column) { return viewport.resolvedColumnWidth(column); }

        delegate: Rectangle {
            required property int row
            required property int column
            required property var display
            implicitWidth: viewport.resolvedColumnWidth(column)
            implicitHeight: viewport.rowHeight
            readonly property bool selected: viewport.selectedRow === row && viewport.selectedColumn === column
            color: selected ? viewport.selectedColor : (row % 2 === 0 ? viewport.rowFillColor : viewport.alternateRowFillColor)
            border.width: 1
            border.color: selected ? viewport.selectedBorderColor : viewport.gridLineColor
            clip: true

            Text {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                text: String(display || "")
                color: viewport.textColor
                font.pixelSize: viewport.compact ? 9 : 11
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }

            TapHandler {
                onTapped: viewport.selectCell(row, column)
            }
        }

        ScrollBar.horizontal: ScrollBar {
            id: horizontalScrollBar
            policy: ScrollBar.AsNeeded
            interactive: true
            contentItem: Rectangle {
                implicitHeight: 7
                radius: 3
                color: horizontalScrollBar.pressed ? viewport.accentColor : viewport.scrollbarHandleColor
                opacity: horizontalScrollBar.size < 1.0 ? (horizontalScrollBar.hovered || horizontalScrollBar.pressed ? 0.95 : 0.72) : 0.0
            }
            background: Rectangle {
                color: "transparent"
            }
        }
        ScrollBar.vertical: ScrollBar {
            id: verticalScrollBar
            policy: ScrollBar.AsNeeded
            interactive: true
            contentItem: Rectangle {
                implicitWidth: 7
                radius: 3
                color: verticalScrollBar.pressed ? viewport.accentColor : viewport.scrollbarHandleColor
                opacity: verticalScrollBar.size < 1.0 ? (verticalScrollBar.hovered || verticalScrollBar.pressed ? 0.95 : 0.72) : 0.0
            }
            background: Rectangle {
                color: "transparent"
            }
        }
    }

    Text {
        objectName: viewport.objectNamePrefix + "EmptyGridLabel"
        anchors.centerIn: parent
        width: Math.min(parent.width - 28, 320)
        visible: viewport.rowCount <= 0 || viewport.columnCount <= 0
        text: "No cells in this bounded preview window."
        color: viewport.mutedTextColor
        font.pixelSize: viewport.compact ? 10 : 12
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }

    Component.onCompleted: Qt.callLater(applyStoredColumnWidths)
}
