import QtQuick 2.15
import QtQuick.Controls 2.15
import "../surface_controls" as SurfaceControls
import "../../shell" as Shell

Item {
    id: root
    objectName: "graphNativeExplorerSurface"
    property Item host: null
    property var listing: ({})
    property bool loading: false
    property bool completed: false
    property string errorText: ""
    property string selectedPath: ""
    // Right-click context-menu state, captured from the row at popup time.
    property string _menuPath: ""
    property bool _menuIsFolder: false
    property bool _menuIsParent: false
    property real _menuSceneX: 0
    property real _menuSceneY: 0
    readonly property string currentPath: _propertyString("current_path")
    readonly property string displayPath: String(listing && listing.directory_path ? listing.directory_path : currentPath)
    readonly property string sortKey: String(listing && listing.sort_key ? listing.sort_key : "name")
    readonly property bool reverse: Boolean(listing && listing.reverse)
    readonly property real panelLeft: Math.max(6.0, Number(host && host.surfaceMetrics ? host.surfaceMetrics.body_left_margin || 8.0 : 8.0))
    readonly property real panelRight: Math.max(6.0, Number(host && host.surfaceMetrics ? host.surfaceMetrics.body_right_margin || 8.0 : 8.0))
    readonly property real panelTop: Math.max(30.0, Number(host && host.surfaceMetrics ? host.surfaceMetrics.body_top || 30.0 : 30.0))
    readonly property real panelBottom: Math.max(48.0, Number(host && host.surfaceMetrics ? host.surfaceMetrics.body_bottom_margin || 8.0 : 8.0))
    readonly property var embeddedInteractiveRects: [
        {
            "x": explorerPanel.x,
            "y": explorerPanel.y,
            "width": explorerPanel.width,
            "height": explorerPanel.height
        }
    ]
    readonly property var surfaceActions: []
    readonly property bool blocksHostInteraction: false
    readonly property var overlayViewportRect: Qt.rect(
        explorerPanel.x,
        explorerPanel.y,
        explorerPanel.width,
        explorerPanel.height
    )
    readonly property var overlayContentRect: overlayViewportRect
    readonly property var overlaySourceClipRect: Qt.rect(0, 0, explorerPanel.width, explorerPanel.height)
    readonly property string overlayPreviewKind: "native_explorer"
    readonly property bool overlayPreviewVisible: explorerPanel.visible
    readonly property var persistedColumnWidths: {
        var canvas = root._canvasItem();
        if (!canvas)
            return ({});
        if (canvas.folderExplorerColumnWidths !== undefined)
            return canvas.folderExplorerColumnWidths || ({});
        if (canvas.canvasStateBridgeRef
                && canvas.canvasStateBridgeRef.graphics_folder_explorer_column_widths !== undefined) {
            return canvas.canvasStateBridgeRef.graphics_folder_explorer_column_widths || ({});
        }
        return ({});
    }

    implicitHeight: Math.max(260.0, height)
    clip: true

    ListModel {
        id: entryModel
    }

    Shell.ShellContextPopup {
        id: rowContextMenu
        objectName: "graphFolderExplorerRowContextMenu"
        actions: [
            {
                objectName: "graphFolderExplorerRowOpenItem", actionId: "open", text: "Open",
                enabled: root._menuPath.length > 0
            },
            {
                objectName: "graphFolderExplorerRowOpenWithItem", actionId: "open_with", text: "Open with...",
                visible: root._menuPath.length > 0 && !root._menuIsFolder && !root._menuIsParent
            },
            {
                objectName: "graphFolderExplorerRowCopyPathItem", actionId: "copy_path", text: "Copy Path",
                enabled: root._menuPath.length > 0
            },
            {
                objectName: "graphFolderExplorerRowOpenNewWindowItem", actionId: "open_in_new_window",
                text: "Open in New Classic Explorer",
                visible: root._menuPath.length > 0 && (root._menuIsFolder || root._menuIsParent)
            },
            {
                objectName: "graphFolderExplorerRowSendToCorexItem", actionId: "send_to_corex_path_pointer",
                text: "Send to COREX as Path Pointer", visible: root._menuPath.length > 0 && !root._menuIsParent
            },
            {
                objectName: "graphFolderExplorerRowPropertiesItem", actionId: "properties", text: "Properties",
                enabled: root._menuPath.length > 0
            }
        ]
        onActionTriggered: function(actionId) {
            if (actionId === "open")
                root.openPath(root._menuPath)
            else if (actionId === "open_with")
                root.openPathWith(root._menuPath)
            else if (actionId === "copy_path")
                root._runMenuAction("folder_explorer_copy_path", root._menuPath, false)
            else if (actionId === "open_in_new_window")
                root._createNodeFromMenu("folder_explorer_open_in_new_window", root._menuPath)
            else if (actionId === "send_to_corex_path_pointer")
                root._createNodeFromMenu("folder_explorer_send_to_corex_path_pointer", root._menuPath)
            else if (actionId === "properties")
                root._runMenuAction("folder_explorer_properties", root._menuPath, true)
        }
    }

    function _propertyString(key) {
        if (!host || !host.nodeData)
            return "";
        var properties = host.nodeData.properties || ({});
        return String(properties[key] || host.nodeData[key] || "");
    }

    function _nodeId() {
        return host && host.nodeData ? String(host.nodeData.node_id || "").trim() : "";
    }

    function _canvasItem() {
        return host && host.canvasItem ? host.canvasItem : null;
    }

    function _actionRouter() {
        var canvas = root._canvasItem();
        return canvas && canvas.canvasActionRouter ? canvas.canvasActionRouter : null;
    }

    function _folderExplorerActionId(command) {
        var normalized = String(command || "").trim();
        var router = root._actionRouter();
        if (!router || !router.folderExplorerActionId)
            return normalized;
        var actionId = String(router.folderExplorerActionId(normalized) || "").trim();
        return actionId.length ? actionId : normalized;
    }

    function _prepareInteraction() {
        var canvas = root._canvasItem();
        var nodeId = root._nodeId();
        if (canvas && canvas.prepareNodeSurfaceControlInteraction && nodeId.length)
            canvas.prepareNodeSurfaceControlInteraction(nodeId);
    }

    function _errorPayload(command, code, message, path) {
        return {
            "success": false,
            "cancelled": false,
            "action_id": root._folderExplorerActionId(command),
            "node_id": root._nodeId(),
            "path": String(path || ""),
            "error": {
                "code": String(code || "error"),
                "message": String(message || ""),
                "operation": root._folderExplorerActionId(command),
                "path": String(path || ""),
                "target_path": ""
            }
        };
    }

    function _requestAction(command, payload, interactive) {
        var router = root._actionRouter();
        var nodeId = root._nodeId();
        var incoming = payload || ({});
        if (!router || !router.requestFolderExplorerAction || !nodeId.length) {
            return root._errorPayload(
                command,
                "bridge_unavailable",
                "Folder explorer command bridge is not available.",
                incoming.path || root.displayPath
            );
        }
        if (interactive && host && Boolean(host.graphReadOnly)) {
            return root._errorPayload(
                command,
                "read_only",
                "Folder explorer node is read-only.",
                incoming.path || root.displayPath
            );
        }
        if (interactive)
            root._prepareInteraction();

        var requestPayload = {};
        for (var key in incoming) {
            if (Object.prototype.hasOwnProperty.call(incoming, key))
                requestPayload[key] = incoming[key];
        }
        requestPayload.node_id = nodeId;
        return router.requestFolderExplorerAction(root._folderExplorerActionId(command), requestPayload);
    }

    function refresh(interactive) {
        var path = root.displayPath.length ? root.displayPath : root.currentPath;
        root.loading = true;
        var result = root._requestAction(
            "folder_explorer_list",
            {
                "path": path,
                "sort_key": root.sortKey,
                "reverse": root.reverse
            },
            Boolean(interactive)
        );
        root.loading = false;
        root._applyResult(result);
        return result && Boolean(result.success);
    }

    function navigateTo(path) {
        var targetPath = String(path || "").trim();
        if (!targetPath.length)
            return false;
        root.loading = true;
        var result = root._requestAction(
            "folder_explorer_navigate",
            {
                "path": targetPath,
                "sort_key": root.sortKey,
                "reverse": root.reverse
            },
            true
        );
        root.loading = false;
        root._applyResult(result);
        return result && Boolean(result.success);
    }

    function openPath(path) {
        var targetPath = String(path || "").trim();
        if (!targetPath.length)
            return false;
        var result = root._requestAction("folder_explorer_open", {"path": targetPath}, true);
        if (!result || !Boolean(result.success))
            root._setErrorFromResult(result);
        return result && Boolean(result.success);
    }

    function openPathWith(path) {
        var targetPath = String(path || "").trim();
        if (!targetPath.length)
            return false;
        var result = root._requestAction("folder_explorer_open_with", {"path": targetPath}, true);
        if (!result || !Boolean(result.success))
            root._setErrorFromResult(result);
        return result && Boolean(result.success);
    }

    function _runMenuAction(command, path, interactive) {
        var targetPath = String(path || "").trim();
        if (!targetPath.length)
            return false;
        var result = root._requestAction(command, {"path": targetPath}, Boolean(interactive));
        if (!result || !Boolean(result.success))
            root._setErrorFromResult(result);
        return result && Boolean(result.success);
    }

    function _createNodeFromMenu(command, path) {
        var targetPath = String(path || "").trim();
        if (!targetPath.length)
            return false;
        var result = root._requestAction(
            command,
            {
                "path": targetPath,
                "scene_x": root._menuSceneX,
                "scene_y": root._menuSceneY
            },
            true
        );
        if (!result || !Boolean(result.success))
            root._setErrorFromResult(result);
        return result && Boolean(result.success);
    }

    function _openRowContextMenu(mouseArea, mouse, rowItem) {
        root._menuPath = String(rowItem.rowPath || "");
        root._menuIsFolder = Boolean(rowItem.rowFolder);
        root._menuIsParent = Boolean(rowItem.rowParent);
        var canvas = root._canvasItem();
        var canvasPoint = root._canvasPointFromMouse(mouseArea, mouse);
        root._menuSceneX = canvas && canvas.screenToSceneX ? Number(canvas.screenToSceneX(canvasPoint.x)) : 0;
        root._menuSceneY = canvas && canvas.screenToSceneY ? Number(canvas.screenToSceneY(canvasPoint.y)) : 0;
        rowContextMenu.openAt(mouseArea, mouse.x, mouse.y);
    }

    function setSort(sortKey) {
        var key = String(sortKey || "name");
        var nextReverse = root.sortKey === key ? !root.reverse : false;
        root.loading = true;
        var result = root._requestAction(
            "folder_explorer_set_sort",
            {
                "path": root.displayPath,
                "sort_key": key,
                "reverse": nextReverse
            },
            false
        );
        root.loading = false;
        root._applyResult(result);
        return result && Boolean(result.success);
    }

    function _applyResult(result) {
        if (!result || !Boolean(result.success)) {
            root._setErrorFromResult(result);
            return;
        }
        root._applyListing(result.listing || ({}));
    }

    function _setErrorFromResult(result) {
        var error = result && result.error ? result.error : ({});
        root.errorText = String(error.message || "Folder explorer action failed.");
    }

    function _applyListing(nextListing) {
        root.errorText = "";
        root.selectedPath = "";
        root.listing = nextListing || ({});
        entryModel.clear();

        var parentPath = String(root.listing.parent_path || "");
        if (parentPath.length) {
            entryModel.append({
                "name": "..",
                "absolute_path": parentPath,
                "is_folder": true,
                "is_parent": true,
                "modified_text": "",
                "type_label": "Parent folder",
                "display_size": ""
            });
        }

        var entries = root.listing.entries || [];
        for (var index = 0; index < entries.length; ++index) {
            var entry = entries[index] || ({});
            entryModel.append({
                "name": String(entry.name || ""),
                "absolute_path": String(entry.absolute_path || ""),
                "is_folder": Boolean(entry.is_folder),
                "is_parent": false,
                "modified_text": root._formatModified(entry.modified_timestamp),
                "type_label": String(entry.type_label || (entry.is_folder ? "File folder" : "")),
                "display_size": String(entry.display_size || "")
            });
        }
    }

    function _formatModified(timestamp) {
        var numeric = Number(timestamp);
        if (!isFinite(numeric) || numeric <= 0)
            return "";
        return new Date(numeric * 1000).toLocaleString();
    }

    function _sortMarker(key) {
        if (root.sortKey !== key)
            return "";
        return root.reverse ? " v" : " ^";
    }

    function _dragPayload(path, isFolder) {
        var canvas = root._canvasItem();
        if (canvas && canvas.folderExplorerDragPayload)
            return canvas.folderExplorerDragPayload(path, isFolder);
        return {
            "action_id": root._folderExplorerActionId("folder_explorer_send_to_corex_path_pointer"),
            "type_id": "io.path_pointer",
            "properties": {
                "path": String(path || ""),
                "mode": Boolean(isFolder) ? "folder" : "file"
            }
        };
    }

    function _persistColumnWidths(widths) {
        var canvas = root._canvasItem();
        if (!canvas)
            return false;
        var payload = widths || ({});
        if (canvas.setFolderExplorerColumnWidths)
            return Boolean(canvas.setFolderExplorerColumnWidths(payload));
        var commandBridge = canvas.canvasCommandBridgeRef || canvas.canvasCommandBridge || null;
        if (commandBridge && commandBridge.set_folder_explorer_column_widths) {
            commandBridge.set_folder_explorer_column_widths(payload);
            return true;
        }
        return false;
    }

    function _canvasPointFromMouse(mouseArea, mouse) {
        var canvas = root._canvasItem();
        if (!canvas || !mouseArea || !mouse)
            return Qt.point(0, 0);
        return mouseArea.mapToItem(canvas, mouse.x, mouse.y);
    }

    function _clearPathPointerDropPreview() {
        var canvas = root._canvasItem();
        if (canvas && canvas.clearLibraryDropPreview)
            canvas.clearLibraryDropPreview();
    }

    function _updatePathPointerDropPreview(mouseArea, mouse, path, isFolder) {
        var canvas = root._canvasItem();
        var normalizedPath = String(path || "").trim();
        if (!canvas || !normalizedPath.length) {
            root._clearPathPointerDropPreview();
            return;
        }
        var canvasPoint = root._canvasPointFromMouse(mouseArea, mouse);
        if (canvas.isPointInCanvas && !canvas.isPointInCanvas(canvasPoint.x, canvasPoint.y)) {
            root._clearPathPointerDropPreview();
            return;
        }
        if (canvas.updatePathPointerDropPreview)
            canvas.updatePathPointerDropPreview(canvasPoint.x, canvasPoint.y, normalizedPath, Boolean(isFolder));
    }

    function _performPathPointerDrop(mouseArea, mouse, path, isFolder) {
        var canvas = root._canvasItem();
        var normalizedPath = String(path || "").trim();
        if (!canvas || !normalizedPath.length) {
            root._clearPathPointerDropPreview();
            return false;
        }
        var canvasPoint = root._canvasPointFromMouse(mouseArea, mouse);
        if (canvas.isPointInCanvas && !canvas.isPointInCanvas(canvasPoint.x, canvasPoint.y)) {
            root._clearPathPointerDropPreview();
            return false;
        }
        if (canvas.performPathPointerDrop)
            return Boolean(canvas.performPathPointerDrop(canvasPoint.x, canvasPoint.y, normalizedPath, Boolean(isFolder)));
        root._clearPathPointerDropPreview();
        return false;
    }

    onCurrentPathChanged: {
        if (completed && currentPath.length && currentPath !== displayPath)
            refresh(false);
    }

    Component.onCompleted: {
        completed = true;
        refresh(false);
    }

    onPersistedColumnWidthsChanged: {
        if (explorerPanel.columnLayoutReady && !explorerPanel.columnResizeActive)
            explorerPanel.applyPersistedColumnWidths();
    }

    Rectangle {
        id: explorerPanel
        objectName: "graphNodeViewerViewport"
        x: root.panelLeft
        y: root.panelTop
        width: Math.max(0.0, root.width - root.panelLeft - root.panelRight)
        height: Math.max(0.0, root.height - root.panelTop - root.panelBottom)
        color: "#ffffff"
        border.width: 1
        border.color: "#cbd5e1"
        radius: 2
        clip: true

        readonly property bool compactColumns: width < 450
        readonly property real minNameColumnWidth: 96
        readonly property real minModifiedColumnWidth: 110
        readonly property real minTypeColumnWidth: 70
        readonly property real minSizeColumnWidth: 56
        readonly property real maxColumnWidth: 1200
        property real nameColumnWidth: minNameColumnWidth
        property real modifiedColumnWidth: compactColumns ? 124 : 150
        property real typeColumnPreferredWidth: 130
        property real sizeColumnPreferredWidth: 76
        readonly property real typeColumnWidth: compactColumns ? 0 : typeColumnPreferredWidth
        readonly property real sizeColumnWidth: compactColumns ? 0 : sizeColumnPreferredWidth
        property bool columnLayoutReady: false
        property bool columnResizeActive: false
        property bool columnResizeChanged: false
        property real resizeStartNameColumnWidth: minNameColumnWidth
        property real resizeStartModifiedColumnWidth: 150
        property real resizeStartTypeColumnWidth: 130
        property real resizeStartSizeColumnWidth: 76

        function _columnMinimum(columnKey) {
            if (columnKey === "name")
                return minNameColumnWidth;
            if (columnKey === "modified")
                return minModifiedColumnWidth;
            if (columnKey === "type")
                return minTypeColumnWidth;
            if (columnKey === "size")
                return minSizeColumnWidth;
            return 48;
        }

        function _clampedColumnWidth(columnKey, value) {
            var numeric = Number(value);
            if (!isFinite(numeric))
                numeric = _columnMinimum(columnKey);
            return Math.max(_columnMinimum(columnKey), Math.min(maxColumnWidth, numeric));
        }

        function _storedColumnWidth(widths, columnKey, fallback) {
            if (!widths || widths[columnKey] === undefined)
                return _clampedColumnWidth(columnKey, fallback);
            return _clampedColumnWidth(columnKey, widths[columnKey]);
        }

        function _visibleColumnKeys() {
            return compactColumns ? ["name", "modified"] : ["name", "modified", "type", "size"];
        }

        function _columnWidth(columnKey) {
            if (columnKey === "name")
                return nameColumnWidth;
            if (columnKey === "modified")
                return modifiedColumnWidth;
            if (columnKey === "type")
                return typeColumnPreferredWidth;
            if (columnKey === "size")
                return sizeColumnPreferredWidth;
            return 0;
        }

        function _setColumnWidth(columnKey, value) {
            var clamped = _clampedColumnWidth(columnKey, value);
            if (columnKey === "name")
                nameColumnWidth = clamped;
            else if (columnKey === "modified")
                modifiedColumnWidth = clamped;
            else if (columnKey === "type")
                typeColumnPreferredWidth = clamped;
            else if (columnKey === "size")
                sizeColumnPreferredWidth = clamped;
        }

        function _visibleColumnTotal() {
            var keys = _visibleColumnKeys();
            var total = 0;
            for (var index = 0; index < keys.length; ++index)
                total += _columnWidth(keys[index]);
            return total;
        }

        function _fitVisibleColumnsToPanel() {
            if (width <= 0)
                return;

            var keys = _visibleColumnKeys();
            var minimumTotal = 0;
            for (var index = 0; index < keys.length; ++index) {
                var key = keys[index];
                minimumTotal += _columnMinimum(key);
                _setColumnWidth(key, _columnWidth(key));
            }

            var targetWidth = Math.max(minimumTotal, width);
            var total = _visibleColumnTotal();
            if (total < targetWidth) {
                nameColumnWidth = Math.max(minNameColumnWidth, nameColumnWidth + targetWidth - total);
                return;
            }

            var excess = total - targetWidth;
            for (var shrinkIndex = 0; shrinkIndex < keys.length && excess > 0.01; ++shrinkIndex) {
                var shrinkKey = keys[shrinkIndex];
                var current = _columnWidth(shrinkKey);
                var available = Math.max(0, current - _columnMinimum(shrinkKey));
                var applied = Math.min(available, excess);
                _setColumnWidth(shrinkKey, current - applied);
                excess -= applied;
            }
        }

        function applyPersistedColumnWidths() {
            var widths = root.persistedColumnWidths || ({});
            var modifiedFallback = compactColumns ? 124 : 150;
            modifiedColumnWidth = _storedColumnWidth(widths, "modified", modifiedFallback);
            typeColumnPreferredWidth = _storedColumnWidth(widths, "type", 130);
            sizeColumnPreferredWidth = _storedColumnWidth(widths, "size", 76);
            var nameFallback = Math.max(
                minNameColumnWidth,
                width - modifiedColumnWidth - (compactColumns ? 0 : typeColumnPreferredWidth)
                    - (compactColumns ? 0 : sizeColumnPreferredWidth)
            );
            nameColumnWidth = _storedColumnWidth(widths, "name", nameFallback);
            columnLayoutReady = true;
            _fitVisibleColumnsToPanel();
        }

        function _rightColumnForBoundary(columnKey) {
            if (columnKey === "name")
                return "modified";
            if (columnKey === "modified" && !compactColumns)
                return "type";
            if (columnKey === "type" && !compactColumns)
                return "size";
            return "";
        }

        function _resizeStartWidth(columnKey) {
            if (columnKey === "name")
                return resizeStartNameColumnWidth;
            if (columnKey === "modified")
                return resizeStartModifiedColumnWidth;
            if (columnKey === "type")
                return resizeStartTypeColumnWidth;
            if (columnKey === "size")
                return resizeStartSizeColumnWidth;
            return 0;
        }

        function beginColumnResize(columnKey) {
            if (!_rightColumnForBoundary(columnKey).length)
                return false;
            columnResizeActive = true;
            columnResizeChanged = false;
            resizeStartNameColumnWidth = nameColumnWidth;
            resizeStartModifiedColumnWidth = modifiedColumnWidth;
            resizeStartTypeColumnWidth = typeColumnPreferredWidth;
            resizeStartSizeColumnWidth = sizeColumnPreferredWidth;
            return true;
        }

        function resizeColumnBoundary(columnKey, deltaX) {
            if (!columnResizeActive)
                return false;
            var rightKey = _rightColumnForBoundary(columnKey);
            if (!rightKey.length)
                return false;

            var leftStart = _resizeStartWidth(columnKey);
            var rightStart = _resizeStartWidth(rightKey);
            var total = leftStart + rightStart;
            var leftMinimum = _columnMinimum(columnKey);
            var rightMinimum = _columnMinimum(rightKey);
            var nextLeft = Math.max(leftMinimum, Math.min(leftStart + deltaX, total - rightMinimum));
            var nextRight = total - nextLeft;

            _setColumnWidth(columnKey, nextLeft);
            _setColumnWidth(rightKey, nextRight);
            columnResizeChanged = columnResizeChanged || Math.abs(nextLeft - leftStart) >= 0.5;
            _fitVisibleColumnsToPanel();
            return true;
        }

        function columnWidthsPayload() {
            return {
                "name": Math.round(nameColumnWidth),
                "modified": Math.round(modifiedColumnWidth),
                "type": Math.round(typeColumnPreferredWidth),
                "size": Math.round(sizeColumnPreferredWidth)
            };
        }

        function finishColumnResize() {
            if (!columnResizeActive)
                return false;
            var shouldPersist = columnResizeChanged;
            columnResizeActive = false;
            columnResizeChanged = false;
            if (shouldPersist)
                root._persistColumnWidths(columnWidthsPayload());
            return shouldPersist;
        }

        onWidthChanged: {
            if (columnLayoutReady && !columnResizeActive)
                _fitVisibleColumnsToPanel();
        }

        onCompactColumnsChanged: {
            if (columnLayoutReady && !columnResizeActive)
                _fitVisibleColumnsToPanel();
        }

        Component.onCompleted: applyPersistedColumnWidths()

        Rectangle {
            id: pathBar
            objectName: "graphFolderExplorerPathBar"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 31
            color: "#f7f9fc"
            border.width: 0

            Rectangle {
                id: homeIcon
                anchors.left: parent.left
                anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                width: 16
                height: 16
                color: "transparent"

                Canvas {
                    anchors.fill: parent
                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.clearRect(0, 0, width, height);
                        ctx.fillStyle = "#d46b08";
                        ctx.beginPath();
                        ctx.moveTo(2, 8);
                        ctx.lineTo(8, 2);
                        ctx.lineTo(14, 8);
                        ctx.closePath();
                        ctx.fill();
                        ctx.fillStyle = "#f59f00";
                        ctx.fillRect(4, 8, 8, 6);
                    }
                }
            }

            Text {
                id: pathText
                objectName: "graphFolderExplorerPathText"
                anchors.left: homeIcon.right
                anchors.leftMargin: 8
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: root.displayPath.length ? root.displayPath : "Home"
                color: "#1f2937"
                font.pixelSize: 12
                elide: Text.ElideMiddle
                verticalAlignment: Text.AlignVCenter
                renderType: host ? host.nodeTextRenderType : Text.CurveRendering
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: "#dbe3ed"
            }
        }

        Rectangle {
            id: headerRow
            objectName: "graphFolderExplorerHeaderRow"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: pathBar.bottom
            height: 27
            color: "#f1f5f9"

            Row {
                anchors.fill: parent

                HeaderCell {
                    width: explorerPanel.nameColumnWidth
                    columnKey: "name"
                    resizable: true
                    label: "Name" + root._sortMarker("name")
                    textRenderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    onClicked: root.setSort("name")
                    onResizeStarted: function(columnKey) { explorerPanel.beginColumnResize(columnKey); }
                    onResizeDragged: function(columnKey, deltaX) { explorerPanel.resizeColumnBoundary(columnKey, deltaX); }
                    onResizeFinished: function(changed) { explorerPanel.finishColumnResize(); }
                }
                HeaderCell {
                    width: explorerPanel.modifiedColumnWidth
                    columnKey: "modified"
                    resizable: !explorerPanel.compactColumns
                    label: "Date modified" + root._sortMarker("modified")
                    textRenderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    onClicked: root.setSort("modified")
                    onResizeStarted: function(columnKey) { explorerPanel.beginColumnResize(columnKey); }
                    onResizeDragged: function(columnKey, deltaX) { explorerPanel.resizeColumnBoundary(columnKey, deltaX); }
                    onResizeFinished: function(changed) { explorerPanel.finishColumnResize(); }
                }
                HeaderCell {
                    width: explorerPanel.typeColumnWidth
                    visible: width > 0
                    columnKey: "type"
                    resizable: !explorerPanel.compactColumns
                    label: "Type" + root._sortMarker("type")
                    textRenderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    onClicked: root.setSort("type")
                    onResizeStarted: function(columnKey) { explorerPanel.beginColumnResize(columnKey); }
                    onResizeDragged: function(columnKey, deltaX) { explorerPanel.resizeColumnBoundary(columnKey, deltaX); }
                    onResizeFinished: function(changed) { explorerPanel.finishColumnResize(); }
                }
                HeaderCell {
                    width: explorerPanel.sizeColumnWidth
                    visible: width > 0
                    columnKey: "size"
                    resizable: false
                    label: "Size" + root._sortMarker("size")
                    textRenderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    onClicked: root.setSort("size")
                }
            }
        }

        ListView {
            id: entryList
            objectName: "graphFolderExplorerEntriesView"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: headerRow.bottom
            anchors.bottom: parent.bottom
            clip: true
            model: entryModel
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                id: rowRoot
                objectName: is_parent ? "graphFolderExplorerParentRow" : "graphFolderExplorerEntryRow"
                property string rowName: String(name || "")
                property string rowPath: String(absolute_path || "")
                property bool rowFolder: Boolean(is_folder)
                property bool rowParent: Boolean(is_parent)
                property var dragPayload: rowParent ? ({}) : root._dragPayload(rowPath, rowFolder)
                width: ListView.view ? ListView.view.width : explorerPanel.width
                height: 26
                color: root.selectedPath === rowPath
                    ? "#dbeafe"
                    : (rowMouseArea.containsMouse ? "#eef6ff" : "#ffffff")
                border.width: 0

                Item {
                    id: dragProxy
                    width: rowRoot.width
                    height: rowRoot.height
                    opacity: 0
                    Drag.active: !rowRoot.rowParent && rowMouseArea.drag.active && rowRoot.rowPath.length > 0
                    Drag.source: rowRoot
                    Drag.keys: ["application/x-corex-path-pointer", "text/plain"]
                    Drag.supportedActions: Qt.CopyAction
                    Drag.hotSpot.x: rowMouseArea.mouseX
                    Drag.hotSpot.y: rowMouseArea.mouseY
                    Drag.mimeData: rowRoot.dragPayload && rowRoot.dragPayload.type_id
                        ? {
                            "application/x-corex-path-pointer": JSON.stringify(rowRoot.dragPayload),
                            "text/plain": rowRoot.rowPath
                        }
                        : ({})
                }

                Row {
                    anchors.fill: parent

                    Item {
                        objectName: "graphFolderExplorerNameColumn"
                        width: explorerPanel.nameColumnWidth
                        height: parent.height

                        Item {
                            id: rowIcon
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: 19
                            height: 17

                            Canvas {
                                anchors.fill: parent
                                onPaint: {
                                    var ctx = getContext("2d");
                                    ctx.clearRect(0, 0, width, height);
                                    if (rowRoot.rowParent) {
                                        ctx.fillStyle = "#111827";
                                        ctx.beginPath();
                                        ctx.moveTo(9.5, 2.5);
                                        ctx.lineTo(16, 10);
                                        ctx.lineTo(12, 10);
                                        ctx.lineTo(12, 15);
                                        ctx.lineTo(7, 15);
                                        ctx.lineTo(7, 10);
                                        ctx.lineTo(3, 10);
                                        ctx.closePath();
                                        ctx.fill();
                                        return;
                                    }
                                    if (rowRoot.rowFolder) {
                                        ctx.fillStyle = "#e6a400";
                                        ctx.fillRect(2, 4, 7, 4);
                                        ctx.fillStyle = "#f8c95a";
                                        ctx.fillRect(1, 7, 17, 9);
                                        ctx.strokeStyle = "#d69a00";
                                        ctx.strokeRect(1.5, 7.5, 16, 8);
                                        return;
                                    }
                                    ctx.fillStyle = "#f8fafc";
                                    ctx.fillRect(4, 1, 11, 15);
                                    ctx.strokeStyle = "#94a3b8";
                                    ctx.strokeRect(4.5, 1.5, 10, 14);
                                    ctx.fillStyle = "#dbeafe";
                                    ctx.fillRect(6, 11, 7, 1);
                                    ctx.fillRect(6, 13, 7, 1);
                                }
                            }
                        }

                        Text {
                            anchors.left: rowIcon.right
                            anchors.leftMargin: 6
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: rowRoot.rowName
                            color: "#0f172a"
                            font.pixelSize: 12
                            elide: Text.ElideMiddle
                            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                        }
                    }

                    Text {
                        objectName: "graphFolderExplorerModifiedColumn"
                        width: explorerPanel.modifiedColumnWidth
                        height: parent.height
                        text: String(modified_text || "")
                        color: "#111827"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }

                    Text {
                        objectName: "graphFolderExplorerTypeColumn"
                        width: explorerPanel.typeColumnWidth
                        height: parent.height
                        visible: width > 0
                        text: String(type_label || "")
                        color: "#111827"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }

                    Text {
                        objectName: "graphFolderExplorerSizeColumn"
                        width: explorerPanel.sizeColumnWidth
                        height: parent.height
                        visible: width > 0
                        text: rowRoot.rowFolder ? "" : String(display_size || "")
                        color: "#111827"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignRight
                        verticalAlignment: Text.AlignVCenter
                        renderType: host ? host.nodeTextRenderType : Text.CurveRendering
                    }
                }

                MouseArea {
                    id: rowMouseArea
                    objectName: "graphFolderExplorerRowMouseArea"
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    preventStealing: true
                    drag.target: (!rowRoot.rowParent && (pressedButtons & Qt.LeftButton)) ? dragProxy : null
                    drag.axis: Drag.XAndYAxis
                    property real pressStartX: 0
                    property real pressStartY: 0
                    property bool movedState: false

                    onPressed: function(mouse) {
                        root.selectedPath = rowRoot.rowPath;
                        if (mouse.button === Qt.LeftButton) {
                            dragProxy.x = 0;
                            dragProxy.y = 0;
                            rowMouseArea.pressStartX = mouse.x;
                            rowMouseArea.pressStartY = mouse.y;
                            rowMouseArea.movedState = false;
                            root._clearPathPointerDropPreview();
                        } else if (mouse.button === Qt.RightButton) {
                            root._openRowContextMenu(rowMouseArea, mouse, rowRoot);
                        }
                        mouse.accepted = true;
                    }

                    onPositionChanged: function(mouse) {
                        if (!(pressedButtons & Qt.LeftButton))
                            return;
                        if (Math.abs(mouse.x - rowMouseArea.pressStartX) >= 2
                                || Math.abs(mouse.y - rowMouseArea.pressStartY) >= 2) {
                            rowMouseArea.movedState = true;
                        }
                        if (!rowMouseArea.movedState || rowRoot.rowParent)
                            return;
                        root._updatePathPointerDropPreview(rowMouseArea, mouse, rowRoot.rowPath, rowRoot.rowFolder);
                    }

                    onDoubleClicked: function(mouse) {
                        if (mouse.button !== Qt.LeftButton)
                            return;
                        mouse.accepted = true;
                        if (rowRoot.rowParent || rowRoot.rowFolder)
                            root.navigateTo(rowRoot.rowPath);
                        else
                            root.openPath(rowRoot.rowPath);
                    }

                    onReleased: function(mouse) {
                        if (mouse.button === Qt.LeftButton) {
                            if (rowMouseArea.movedState && !rowRoot.rowParent)
                                root._performPathPointerDrop(rowMouseArea, mouse, rowRoot.rowPath, rowRoot.rowFolder);
                            else
                                root._clearPathPointerDropPreview();
                        }
                        dragProxy.x = 0;
                        dragProxy.y = 0;
                    }

                    onCanceled: {
                        rowMouseArea.movedState = false;
                        root._clearPathPointerDropPreview();
                        dragProxy.x = 0;
                        dragProxy.y = 0;
                    }
                }

                SurfaceControls.GraphSurfaceInteractiveRegion {
                    id: rowMouseAreaInteractiveRegion
                    host: root.host
                    targetItem: rowMouseArea
                    enabled: rowRoot.visible
                }
            }
        }

        Text {
            objectName: "graphFolderExplorerEmptyText"
            anchors.centerIn: entryList
            width: Math.max(100, entryList.width - 24)
            visible: !root.loading && !root.errorText.length && entryModel.count === 0
            text: "This folder is empty"
            color: "#64748b"
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }

        Text {
            objectName: "graphFolderExplorerErrorText"
            anchors.centerIn: entryList
            width: Math.max(120, entryList.width - 24)
            visible: root.errorText.length > 0
            text: root.errorText
            color: "#b91c1c"
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering
        }
    }

    component HeaderCell: Rectangle {
        signal clicked()
        signal resizeStarted(string columnKey)
        signal resizeDragged(string columnKey, real deltaX)
        signal resizeFinished(bool changed)
        property string label: ""
        property string columnKey: ""
        property bool resizable: false
        property int textRenderType: Text.CurveRendering
        property real resizeEdgeWidth: 8
        objectName: "graphFolderExplorerHeaderCell_" + columnKey
        height: parent ? parent.height : 27
        color: headerMouseArea.containsMouse ? (headerMouseArea.onResizeEdge ? "#dce6f1" : "#e2e8f0") : "#f1f5f9"
        border.width: 0

        function _isOnResizeEdge(localX) {
            return resizable && visible && width > 0 && localX >= Math.max(0, width - resizeEdgeWidth);
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: "#334155"
            font.pixelSize: 12
            font.bold: true
            elide: Text.ElideRight
            renderType: parent.textRenderType
        }

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: "#dbe3ed"
        }

        MouseArea {
            id: headerMouseArea
            objectName: "graphFolderExplorerHeaderMouseArea"
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            cursorShape: onResizeEdge ? Qt.SplitHCursor : Qt.ArrowCursor
            property bool resizing: false
            property bool resized: false
            property bool suppressClick: false
            property real resizeStartGlobalX: 0
            readonly property bool onResizeEdge: parent._isOnResizeEdge(mouseX)

            onPressed: function(mouse) {
                if (parent._isOnResizeEdge(mouse.x)) {
                    resizing = true;
                    resized = false;
                    suppressClick = true;
                    resizeStartGlobalX = parent.mapToGlobal(mouse.x, mouse.y).x;
                    parent.resizeStarted(parent.columnKey);
                    mouse.accepted = true;
                    return;
                }
                suppressClick = false;
                mouse.accepted = true;
            }

            onPositionChanged: function(mouse) {
                if (!resizing)
                    return;
                var globalPoint = parent.mapToGlobal(mouse.x, mouse.y);
                var deltaX = globalPoint.x - resizeStartGlobalX;
                if (Math.abs(deltaX) >= 0.5)
                    resized = true;
                parent.resizeDragged(parent.columnKey, deltaX);
                mouse.accepted = true;
            }

            onReleased: function(mouse) {
                if (!resizing)
                    return;
                var didResize = resized;
                resizing = false;
                resized = false;
                parent.resizeFinished(didResize);
                mouse.accepted = true;
            }

            onCanceled: {
                if (!resizing)
                    return;
                var didResize = resized;
                resizing = false;
                resized = false;
                parent.resizeFinished(didResize);
            }

            onClicked: function(mouse) {
                if (suppressClick) {
                    suppressClick = false;
                    mouse.accepted = true;
                    return;
                }
                parent.clicked();
            }
        }

        SurfaceControls.GraphSurfaceInteractiveRegion {
            id: headerMouseAreaInteractiveRegion
            host: root.host
            targetItem: headerMouseArea
            enabled: parent.visible
        }
    }
}
