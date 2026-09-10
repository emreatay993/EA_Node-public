// Purpose: Own graph-canvas Web, Timestamp, Slider, Select, and Panel editor overlays.
// Map: feature_routes/surface_input_and_inline_controls.md
// Tests: tests/qml_quick/tst_graph_canvas_surface_editor_overlays.qml

import QtQuick 2.15
import "../graph/passive" as GraphPassive
import "../web" as WebComponents

Item {
    id: root
    objectName: "webPageAddressOverlayLayer"
    property Item canvasItem: null
    property var themePalette: ({})
    property Item webPageAddressEditorHost: null
    property bool webPageAddressOverlayOpen: false
    property Item timestampEditorHost: null
    property bool timestampOverlayOpen: false
    property Item numberSliderEditorHost: null
    property bool numberSliderOverlayOpen: false
    property Item selectEditorHost: null
    property bool selectOverlayOpen: false
    property Item panelEditorHost: null
    property bool panelOverlayOpen: false
    readonly property var activeToolbarSurfaceItem: root._loadedSurfaceItem(
        root.canvasItem ? root.canvasItem.activeToolbarHost : null
    )
    readonly property bool activeToolbarAddressEditorOpen: root._surfaceAddressEditorOpen(
        root.activeToolbarSurfaceItem
    )
    readonly property bool activeToolbarTimestampEditorOpen: root._surfaceTimestampEditorOpen(
        root.activeToolbarSurfaceItem
    )
    readonly property var webPageAddressEditorSurface: root._loadedSurfaceItem(
        root.webPageAddressEditorHost
    )
    readonly property var timestampEditorSurface: root._loadedSurfaceItem(root.timestampEditorHost)
    readonly property var numberSliderEditorSurface: root._loadedSurfaceItem(
        root.numberSliderEditorHost
    )
    readonly property var selectEditorSurface: root._loadedSurfaceItem(root.selectEditorHost)
    readonly property var panelEditorSurface: root._loadedSurfaceItem(root.panelEditorHost)
    readonly property bool anyOverlayOpen: root.webPageAddressOverlayOpen
        || root.timestampOverlayOpen
        || root.numberSliderOverlayOpen
        || root.selectOverlayOpen
        || root.panelOverlayOpen

    visible: root.anyOverlayOpen
    z: 1100

    function _loadedSurfaceItem(host) {
        if (!host || host.loadedSurfaceItem === undefined || host.loadedSurfaceItem === null)
            return null;
        return host.loadedSurfaceItem;
    }

    function _surfaceAddressEditorOpen(surface) {
        return !!surface
            && surface.addressEditorOpen !== undefined
            && Boolean(surface.addressEditorOpen);
    }

    function _surfaceTimestampEditorOpen(surface) {
        return !!surface
            && surface.timestampManualEditorOpen !== undefined
            && Boolean(surface.timestampManualEditorOpen);
    }

    function _surfaceNumberSliderEditorOpen(surface) {
        return !!surface
            && surface.sliderSettingsEditorOpen !== undefined
            && Boolean(surface.sliderSettingsEditorOpen);
    }

    function _surfaceSelectEditorOpen(surface) {
        return !!surface
            && surface.selectSettingsEditorOpen !== undefined
            && Boolean(surface.selectSettingsEditorOpen);
    }

    function _surfacePanelEditorOpen(surface) {
        return !!surface
            && surface.panelEditorOpen !== undefined
            && Boolean(surface.panelEditorOpen);
    }

    function _openWebPageAddressOverlay(host, surface) {
        if (!host || !root._surfaceAddressEditorOpen(surface))
            return false;
        root.webPageAddressEditorHost = host;
        root.webPageAddressOverlayOpen = true;
        webPageAddressPopover.openWithAddress(String(surface.addressEditorText || ""));
        return true;
    }

    function _openTimestampOverlay(host, surface) {
        if (!host || !root._surfaceTimestampEditorOpen(surface))
            return false;
        root.timestampEditorHost = host;
        root.timestampOverlayOpen = true;
        timestampDateTimePopover.openWithTimestamp(
            String(surface.timestampManualEditorText || "")
        );
        return true;
    }

    function _openNumberSliderOverlay(host, surface) {
        if (!host || !root._surfaceNumberSliderEditorOpen(surface))
            return false;
        root.numberSliderEditorHost = host;
        root.numberSliderOverlayOpen = true;
        numberSliderSettingsPopover.openWithSettings(surface.sliderSettingsPayload || ({}));
        return true;
    }

    function _openSelectOverlay(host, surface) {
        if (!host || !root._surfaceSelectEditorOpen(surface))
            return false;
        root.selectEditorHost = host;
        root.selectOverlayOpen = true;
        selectSettingsPopover.openWithSettings(surface.selectSettingsPayload || ({}));
        return true;
    }

    function _openPanelOverlay(host, surface) {
        if (!host || !root._surfacePanelEditorOpen(surface))
            return false;
        root.panelEditorHost = host;
        root.panelOverlayOpen = true;
        panelEditorPopover.openWithSettings(surface.panelEditorPayload || ({}));
        return true;
    }

    function openSurfaceActionOverlayForHost(host, actionId, surface) {
        var resolvedSurface = surface || root._loadedSurfaceItem(host);
        if (String(actionId || "") === "web_page_edit_address")
            return root._openWebPageAddressOverlay(host, resolvedSurface);
        if (String(actionId || "") === "timestamp_edit_manual")
            return root._openTimestampOverlay(host, resolvedSurface);
        if (String(actionId || "") === "number_slider_edit_settings")
            return root._openNumberSliderOverlay(host, resolvedSurface);
        if (String(actionId || "") === "select_edit_settings")
            return root._openSelectOverlay(host, resolvedSurface);
        if (String(actionId || "") === "panel_edit")
            return root._openPanelOverlay(host, resolvedSurface);
        return false;
    }

    function _cancelWebPageAddressOverlay() {
        if (root.webPageAddressOverlayOpen)
            webPageAddressPopover.cancelEdit();
    }

    function _cancelTimestampOverlay() {
        if (root.timestampOverlayOpen)
            timestampDateTimePopover.cancelEdit();
    }

    function _cancelNumberSliderOverlay() {
        if (root.numberSliderOverlayOpen)
            numberSliderSettingsPopover.cancelEdit();
    }

    function _cancelSelectOverlay() {
        if (root.selectOverlayOpen)
            selectSettingsPopover.cancelEdit();
    }

    function _cancelPanelOverlay() {
        if (root.panelOverlayOpen)
            panelEditorPopover.cancelEdit();
    }

    function _clampAddressOverlayX(preferred, overlayWidth) {
        return Math.max(8, Math.min(root.width - overlayWidth - 8, preferred));
    }

    function _quickWindowAddressOverlayY(overlayHeight) {
        var preferred = Math.max(24, Math.min(72, root.height * 0.12));
        return Math.max(8, Math.min(root.height - overlayHeight - 8, preferred));
    }

    function _itemRectInOverlayLayer(item, layer) {
        if (!item || !layer)
            return {"x": 0, "y": 0, "width": 0, "height": 0};
        var width = Math.max(0, Number(item.width || 0));
        var height = Math.max(0, Number(item.height || 0));
        var p1 = item.mapToItem(layer, 0, 0);
        var p2 = item.mapToItem(layer, width, 0);
        var p3 = item.mapToItem(layer, width, height);
        var p4 = item.mapToItem(layer, 0, height);
        var minX = Math.min(p1.x, p2.x, p3.x, p4.x);
        var maxX = Math.max(p1.x, p2.x, p3.x, p4.x);
        var minY = Math.min(p1.y, p2.y, p3.y, p4.y);
        var maxY = Math.max(p1.y, p2.y, p3.y, p4.y);
        return {
            "x": minX,
            "y": minY,
            "width": Math.max(0, maxX - minX),
            "height": Math.max(0, maxY - minY)
        };
    }

    function _timestampSheetWidth() {
        return Math.min(360, Math.max(300, timestampOverlayLayer.width - 32));
    }

    function _timestampSheetX(sheetWidth) {
        var rect = root._itemRectInOverlayLayer(root.timestampEditorHost, timestampOverlayLayer);
        if (rect.width > 0)
            return root._clampAddressOverlayX(
                rect.x + rect.width * 0.5 - sheetWidth * 0.5,
                sheetWidth
            );
        return root._clampAddressOverlayX(
            timestampOverlayLayer.width * 0.5 - sheetWidth * 0.5,
            sheetWidth
        );
    }

    function _timestampSheetY(sheetHeight) {
        var host = root.timestampEditorHost;
        var layer = timestampOverlayLayer;
        if (host && layer) {
            var preferredPoint = host.mapToItem(layer, 0, -sheetHeight - 10);
            if (preferredPoint.y >= 8)
                return preferredPoint.y;
            preferredPoint = host.mapToItem(layer, 0, Number(host.height || 0) + 10);
            return Math.max(8, Math.min(layer.height - sheetHeight - 8, preferredPoint.y));
        }
        return root._quickWindowAddressOverlayY(sheetHeight);
    }

    function _numberSliderSheetWidth() {
        return Math.min(400, Math.max(320, numberSliderOverlayLayer.width - 48));
    }

    function _numberSliderSheetX(sheetWidth) {
        var rect = root._itemRectInOverlayLayer(
            root.numberSliderEditorHost,
            numberSliderOverlayLayer
        );
        if (rect.width > 0)
            return root._clampAddressOverlayX(
                rect.x + rect.width * 0.5 - sheetWidth * 0.5,
                sheetWidth
            );
        return root._clampAddressOverlayX(
            numberSliderOverlayLayer.width * 0.5 - sheetWidth * 0.5,
            sheetWidth
        );
    }

    function _numberSliderSheetY(sheetHeight) {
        var host = root.numberSliderEditorHost;
        var layer = numberSliderOverlayLayer;
        if (host && layer) {
            var preferredPoint = host.mapToItem(layer, 0, Number(host.height || 0) + 16);
            if (preferredPoint.y + sheetHeight <= layer.height - 8)
                return preferredPoint.y;
            preferredPoint = host.mapToItem(layer, 0, -sheetHeight - 16);
            return Math.max(8, Math.min(layer.height - sheetHeight - 8, preferredPoint.y));
        }
        return root._quickWindowAddressOverlayY(sheetHeight);
    }

    function _selectSheetWidth() {
        return Math.min(480, Math.max(360, selectOverlayLayer.width - 48));
    }

    function _selectSheetX(sheetWidth) {
        var rect = root._itemRectInOverlayLayer(root.selectEditorHost, selectOverlayLayer);
        if (rect.width > 0)
            return root._clampAddressOverlayX(
                rect.x + rect.width * 0.5 - sheetWidth * 0.5,
                sheetWidth
            );
        return root._clampAddressOverlayX(
            selectOverlayLayer.width * 0.5 - sheetWidth * 0.5,
            sheetWidth
        );
    }

    function _selectSheetY(sheetHeight) {
        var host = root.selectEditorHost;
        var layer = selectOverlayLayer;
        if (host && layer) {
            var preferredPoint = host.mapToItem(layer, 0, Number(host.height || 0) + 16);
            if (preferredPoint.y + sheetHeight <= layer.height - 8)
                return preferredPoint.y;
            preferredPoint = host.mapToItem(layer, 0, -sheetHeight - 16);
            return Math.max(8, Math.min(layer.height - sheetHeight - 8, preferredPoint.y));
        }
        return root._quickWindowAddressOverlayY(sheetHeight);
    }

    function _panelSheetWidth() {
        return Math.min(320, Math.max(288, panelOverlayLayer.width - 32));
    }

    function _panelSheetX(sheetWidth) {
        var rect = root._itemRectInOverlayLayer(root.panelEditorHost, panelOverlayLayer);
        if (rect.width > 0)
            return root._clampAddressOverlayX(
                rect.x + rect.width * 0.5 - sheetWidth * 0.5,
                sheetWidth
            );
        return root._clampAddressOverlayX(
            panelOverlayLayer.width * 0.5 - sheetWidth * 0.5,
            sheetWidth
        );
    }

    function _panelSheetY(sheetHeight) {
        var host = root.panelEditorHost;
        var layer = panelOverlayLayer;
        if (host && layer) {
            var preferredPoint = host.mapToItem(layer, 0, Number(host.height || 0) + 16);
            if (preferredPoint.y + sheetHeight <= layer.height - 8)
                return preferredPoint.y;
            preferredPoint = host.mapToItem(layer, 0, -sheetHeight - 16);
            return Math.max(8, Math.min(layer.height - sheetHeight - 8, preferredPoint.y));
        }
        return root._quickWindowAddressOverlayY(sheetHeight);
    }

    onActiveToolbarAddressEditorOpenChanged: {
        if (root.activeToolbarAddressEditorOpen
                && root.canvasItem
                && root.canvasItem.activeToolbarHost) {
            root._openWebPageAddressOverlay(
                root.canvasItem.activeToolbarHost,
                root.activeToolbarSurfaceItem
            );
        }
    }

    onActiveToolbarTimestampEditorOpenChanged: {
        if (root.activeToolbarTimestampEditorOpen
                && root.canvasItem
                && root.canvasItem.activeToolbarHost) {
            root._openTimestampOverlay(
                root.canvasItem.activeToolbarHost,
                root.activeToolbarSurfaceItem
            );
        }
    }

    Connections {
        target: root.webPageAddressEditorSurface

        function onAddressEditorOpenChanged() {
            var surface = root.webPageAddressEditorSurface;
            if (root._surfaceAddressEditorOpen(surface)) {
                webPageAddressPopover.openWithAddress(String(surface.addressEditorText || ""));
            } else {
                webPageAddressPopover.closeSilently();
                root.webPageAddressOverlayOpen = false;
                root.webPageAddressEditorHost = null;
            }
        }

        function onAddressEditorTextChanged() {
            var surface = root.webPageAddressEditorSurface;
            if (root._surfaceAddressEditorOpen(surface) && !webPageAddressPopover.visible)
                webPageAddressPopover.openWithAddress(String(surface.addressEditorText || ""));
        }
    }

    Connections {
        target: root.timestampEditorSurface

        function onTimestampManualEditorOpenChanged() {
            var surface = root.timestampEditorSurface;
            if (root._surfaceTimestampEditorOpen(surface)) {
                timestampDateTimePopover.openWithTimestamp(
                    String(surface.timestampManualEditorText || "")
                );
            } else {
                timestampDateTimePopover.closeSilently();
                root.timestampOverlayOpen = false;
                root.timestampEditorHost = null;
            }
        }

        function onTimestampManualEditorTextChanged() {
            var surface = root.timestampEditorSurface;
            if (root._surfaceTimestampEditorOpen(surface) && !timestampDateTimePopover.visible) {
                timestampDateTimePopover.openWithTimestamp(
                    String(surface.timestampManualEditorText || "")
                );
            }
        }
    }

    Connections {
        target: root.numberSliderEditorSurface

        function onSliderSettingsEditorOpenChanged() {
            var surface = root.numberSliderEditorSurface;
            if (root._surfaceNumberSliderEditorOpen(surface)) {
                numberSliderSettingsPopover.openWithSettings(
                    surface.sliderSettingsPayload || ({})
                );
            } else {
                numberSliderSettingsPopover.closeSilently();
                root.numberSliderOverlayOpen = false;
                root.numberSliderEditorHost = null;
            }
        }
    }

    Connections {
        target: root.selectEditorSurface

        function onSelectSettingsEditorOpenChanged() {
            var surface = root.selectEditorSurface;
            if (root._surfaceSelectEditorOpen(surface)) {
                selectSettingsPopover.openWithSettings(surface.selectSettingsPayload || ({}));
            } else {
                selectSettingsPopover.closeSilently();
                root.selectOverlayOpen = false;
                root.selectEditorHost = null;
            }
        }
    }

    Connections {
        target: root.panelEditorSurface

        function onPanelEditorOpenChanged() {
            var surface = root.panelEditorSurface;
            if (root._surfacePanelEditorOpen(surface)) {
                panelEditorPopover.openWithSettings(surface.panelEditorPayload || ({}));
            } else {
                panelEditorPopover.closeSilently();
                root.panelOverlayOpen = false;
                root.panelEditorHost = null;
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.webPageAddressOverlayOpen
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        onPressed: function(mouse) {
            mouse.accepted = true;
        }
        onReleased: function(mouse) {
            root._cancelWebPageAddressOverlay();
            mouse.accepted = true;
        }
        onCanceled: function() {
            root._cancelWebPageAddressOverlay();
        }
    }

    WebComponents.WebPageAddressPopover {
        id: webPageAddressPopover
        themePalette: root.webPageAddressEditorSurface
            ? root.webPageAddressEditorSurface.effectiveThemePalette
            : root.themePalette
        shadowStrength: root.webPageAddressEditorHost
            ? Number(root.webPageAddressEditorHost.shadowStrength || 55)
            : 55
        shadowSoftness: root.webPageAddressEditorHost
            ? Number(root.webPageAddressEditorHost.shadowSoftness || 50)
            : 50
        shadowOffset: root.webPageAddressEditorHost
            ? Number(root.webPageAddressEditorHost.shadowOffset || 4)
            : 4
        width: Math.min(520, Math.max(320, root.width - 32))
        height: implicitHeight
        z: 1
        x: root._clampAddressOverlayX(root.width * 0.5 - width * 0.5, width)
        y: root._quickWindowAddressOverlayY(height)
        onAccepted: function(location) {
            if (root.webPageAddressEditorSurface
                    && root.webPageAddressEditorSurface.acceptAddressEdit) {
                root.webPageAddressEditorSurface.acceptAddressEdit(location);
            }
        }
        onCanceled: function() {
            if (root.webPageAddressEditorSurface
                    && root.webPageAddressEditorSurface.cancelAddressEdit) {
                root.webPageAddressEditorSurface.cancelAddressEdit();
            }
        }
    }

    Item {
        id: timestampOverlayLayer
        objectName: "graphNodeTimestampOverlayLayer"
        anchors.fill: parent
        visible: root.timestampOverlayOpen
        z: 1

        MouseArea {
            anchors.fill: parent
            enabled: root.timestampOverlayOpen
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: function(mouse) {
                mouse.accepted = true;
            }
            onReleased: function(mouse) {
                root._cancelTimestampOverlay();
                mouse.accepted = true;
            }
            onCanceled: function() {
                root._cancelTimestampOverlay();
            }
        }

        GraphPassive.GraphTimestampDateTimePopover {
            id: timestampDateTimePopover
            host: root.timestampEditorHost
            themePalette: root.themePalette
            shadowStrength: root.timestampEditorHost
                ? Number(root.timestampEditorHost.shadowStrength || 55)
                : 55
            shadowSoftness: root.timestampEditorHost
                ? Number(root.timestampEditorHost.shadowSoftness || 50)
                : 50
            shadowOffset: root.timestampEditorHost
                ? Number(root.timestampEditorHost.shadowOffset || 4)
                : 4
            width: root._timestampSheetWidth()
            height: implicitHeight
            z: 1
            x: root._timestampSheetX(width)
            y: root._timestampSheetY(height)
            onAccepted: function(timestamp) {
                if (root.timestampEditorSurface
                        && root.timestampEditorSurface.acceptTimestampManualEdit) {
                    root.timestampEditorSurface.acceptTimestampManualEdit(timestamp);
                }
            }
            onCanceled: function() {
                if (root.timestampEditorSurface
                        && root.timestampEditorSurface.cancelTimestampManualEdit) {
                    root.timestampEditorSurface.cancelTimestampManualEdit();
                }
            }
        }
    }

    Item {
        id: numberSliderOverlayLayer
        objectName: "graphNumberSliderOverlayLayer"
        anchors.fill: parent
        visible: root.numberSliderOverlayOpen
        z: 1

        MouseArea {
            anchors.fill: parent
            enabled: root.numberSliderOverlayOpen
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: function(mouse) {
                mouse.accepted = true;
            }
            onReleased: function(mouse) {
                root._cancelNumberSliderOverlay();
                mouse.accepted = true;
            }
            onCanceled: function() {
                root._cancelNumberSliderOverlay();
            }
        }

        GraphPassive.GraphNumberSliderSettingsPopover {
            id: numberSliderSettingsPopover
            host: root.numberSliderEditorHost
            themePalette: root.themePalette
            shadowStrength: root.numberSliderEditorHost
                ? Number(root.numberSliderEditorHost.shadowStrength || 55)
                : 55
            shadowSoftness: root.numberSliderEditorHost
                ? Number(root.numberSliderEditorHost.shadowSoftness || 50)
                : 50
            shadowOffset: root.numberSliderEditorHost
                ? Number(root.numberSliderEditorHost.shadowOffset || 4)
                : 4
            width: root._numberSliderSheetWidth()
            height: implicitHeight
            z: 1
            x: root._numberSliderSheetX(width)
            y: root._numberSliderSheetY(height)
            onAccepted: function(payload) {
                if (root.numberSliderEditorSurface
                        && root.numberSliderEditorSurface.acceptSliderSettings) {
                    root.numberSliderEditorSurface.acceptSliderSettings(payload);
                }
            }
            onCanceled: function() {
                if (root.numberSliderEditorSurface
                        && root.numberSliderEditorSurface.cancelSliderSettings) {
                    root.numberSliderEditorSurface.cancelSliderSettings();
                }
            }
        }
    }

    Item {
        id: selectOverlayLayer
        objectName: "graphSelectOverlayLayer"
        anchors.fill: parent
        visible: root.selectOverlayOpen
        z: 1

        MouseArea {
            anchors.fill: parent
            enabled: root.selectOverlayOpen
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: function(mouse) {
                mouse.accepted = true;
            }
            onReleased: function(mouse) {
                root._cancelSelectOverlay();
                mouse.accepted = true;
            }
            onCanceled: function() {
                root._cancelSelectOverlay();
            }
        }

        GraphPassive.GraphSelectSettingsPopover {
            id: selectSettingsPopover
            host: root.selectEditorHost
            themePalette: root.themePalette
            shadowStrength: root.selectEditorHost
                ? Number(root.selectEditorHost.shadowStrength || 55)
                : 55
            shadowSoftness: root.selectEditorHost
                ? Number(root.selectEditorHost.shadowSoftness || 50)
                : 50
            shadowOffset: root.selectEditorHost
                ? Number(root.selectEditorHost.shadowOffset || 4)
                : 4
            width: root._selectSheetWidth()
            height: implicitHeight
            z: 1
            x: root._selectSheetX(width)
            y: root._selectSheetY(height)
            onAccepted: function(payload) {
                if (root.selectEditorSurface && root.selectEditorSurface.acceptSelectSettings)
                    root.selectEditorSurface.acceptSelectSettings(payload);
            }
            onCanceled: function() {
                if (root.selectEditorSurface && root.selectEditorSurface.cancelSelectSettings)
                    root.selectEditorSurface.cancelSelectSettings();
            }
        }
    }

    Item {
        id: panelOverlayLayer
        objectName: "graphPanelOverlayLayer"
        anchors.fill: parent
        visible: root.panelOverlayOpen
        z: 1

        MouseArea {
            anchors.fill: parent
            enabled: root.panelOverlayOpen
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: function(mouse) {
                mouse.accepted = true;
            }
            onReleased: function(mouse) {
                root._cancelPanelOverlay();
                mouse.accepted = true;
            }
            onCanceled: function() {
                root._cancelPanelOverlay();
            }
        }

        GraphPassive.GraphPanelEditorPopover {
            id: panelEditorPopover
            host: root.panelEditorHost
            themePalette: root.themePalette
            shadowStrength: root.panelEditorHost
                ? Number(root.panelEditorHost.shadowStrength || 55)
                : 55
            shadowSoftness: root.panelEditorHost
                ? Number(root.panelEditorHost.shadowSoftness || 50)
                : 50
            shadowOffset: root.panelEditorHost
                ? Number(root.panelEditorHost.shadowOffset || 4)
                : 4
            width: root._panelSheetWidth()
            height: implicitHeight
            z: 1
            x: root._panelSheetX(width)
            y: root._panelSheetY(height)
            onAccepted: function(payload) {
                if (root.panelEditorSurface && root.panelEditorSurface.acceptPanelSettings)
                    root.panelEditorSurface.acceptPanelSettings(payload);
            }
            onCanceled: function() {
                if (root.panelEditorSurface && root.panelEditorSurface.cancelPanelSettings)
                    root.panelEditorSurface.cancelPanelSettings();
            }
        }
    }
}
