import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common" as Common

Item {
    id: root
    objectName: "nodeBrowserOverlay"

    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property var helpBridgeRef: typeof helpBridge !== "undefined" ? helpBridge : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    property var graphCanvasRef: null
    property var canvasCommandBridgeRef: null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    property string browserMode: "nodes"
    property string queryText: ""
    property string selectedCategoryKey: ""
    property var selectedCategoryPath: []
    property string directionFilter: ""
    property int selectedIndex: -1
    property bool sceneAnchorActive: false
    property real sceneAnchorX: 0
    property real sceneAnchorY: 0

    readonly property var allItems: root.shellLibraryBridgeRef
        ? root.shellLibraryBridgeRef.browser_library_items
        : []
    // Quick-insert expressions ("0<10", "0<5<10") parsed Python-side into a
    // preconfigured Number Slider payload; {} when the query is not one.
    readonly property var sliderQuickInsert: root.shellLibraryBridgeRef
            && root.shellLibraryBridgeRef.parse_number_slider_query
        ? root.shellLibraryBridgeRef.parse_number_slider_query(root.queryText)
        : ({})
    // COREX Panel shortcuts. A leading quote authors a text Panel directly;
    // the named aliases promote an empty Panel to the first result.
    readonly property var panelQuickInsert: root._panelQuickInsert(root.queryText)
    readonly property var categoryOptions: root.shellLibraryBridgeRef
        ? root.shellLibraryBridgeRef.library_category_options
        : []
    readonly property var rootCategoryOptions: root._rootCategoryOptions()
    readonly property var filteredItems: root._filteredItems()
    readonly property var groupedRows: root._groupedRows()
    readonly property var selectedItem: root.selectedIndex >= 0 && root.selectedIndex < root.filteredItems.length
        ? root.filteredItems[root.selectedIndex]
        : null
    readonly property var inputPorts: root._portsForDirection(root.selectedItem, "in")
    readonly property var outputPorts: root._portsForDirection(root.selectedItem, "out")
    readonly property var neutralPorts: root._portsForDirection(root.selectedItem, "neutral")

    visible: false
    z: 1300
    focus: visible

    function openBrowser(initialQuery, sceneX, sceneY, mode) {
        root.browserMode = String(mode || "nodes")
        root.queryText = String(initialQuery || "")
        root.selectedCategoryKey = ""
        root.selectedCategoryPath = []
        root.directionFilter = ""
        root.sceneAnchorActive = isFinite(Number(sceneX)) && isFinite(Number(sceneY))
        root.sceneAnchorX = root.sceneAnchorActive ? Number(sceneX) : 0
        root.sceneAnchorY = root.sceneAnchorActive ? Number(sceneY) : 0
        root.selectedIndex = root.filteredItems.length > 0 ? 0 : -1
        root.visible = true
        Qt.callLater(function() {
            searchField.forceActiveFocus()
            searchField.selectAll()
            nodeList.positionViewAtBeginning()
        })
    }

    function closeBrowser() {
        if (root.graphCanvasRef)
            root.graphCanvasRef.clearLibraryDropPreview()
        root.visible = false
        root.queryText = ""
        root.sceneAnchorActive = false
    }

    function _categoryMatches(item) {
        if (!root.selectedCategoryKey.length)
            return true
        var itemPath = item && item.category_path ? item.category_path : []
        if (!root.selectedCategoryPath || root.selectedCategoryPath.length > itemPath.length)
            return false
        for (var index = 0; index < root.selectedCategoryPath.length; ++index) {
            if (String(itemPath[index] || "") !== String(root.selectedCategoryPath[index] || ""))
                return false
        }
        return true
    }

    function _rootCategoryOptions() {
        var options = root.categoryOptions || []
        var result = []
        for (var index = 0; index < options.length; ++index) {
            var option = options[index]
            if (!String(option.value || "").length || Number(option.depth || 0) === 0)
                result.push(option)
        }
        return result
    }

    function _directionMatches(item) {
        if (!root.directionFilter.length)
            return true
        var ports = item && item.ports ? item.ports : []
        for (var index = 0; index < ports.length; ++index) {
            if (String(ports[index].direction || "") === root.directionFilter)
                return true
        }
        return false
    }

    function _queryMatches(item) {
        var query = root.queryText.trim().toLowerCase()
        if (!query.length)
            return true
        var parts = [
            String(item.type_id || ""),
            String(item.display_name || ""),
            String(item.category_display || ""),
            String(item.description || ""),
            (item.keywords || []).join(" ")
        ]
        var ports = item.ports || []
        for (var index = 0; index < ports.length; ++index) {
            if (root.directionFilter.length
                    && String(ports[index].direction || "") !== root.directionFilter)
                continue
            parts.push(String(ports[index].key || ""))
            parts.push(String(ports[index].label || ""))
            parts.push(String(ports[index].description || ""))
            parts.push(String(ports[index].data_type || ""))
        }
        return parts.join(" ").toLowerCase().indexOf(query) >= 0
    }

    function _filteredItems() {
        var items = root.allItems || []
        var result = []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            var source = String(item.library_source || "")
            if (root.browserMode === "nodes" && source !== "node_registry")
                continue
            if (root.browserMode === "templates" && source !== "custom_workflow")
                continue
            if (!root._categoryMatches(item) || !root._directionMatches(item) || !root._queryMatches(item))
                continue
            result.push(item)
        }
        result.sort(function(left, right) {
            var leftCategory = String(left.category_display || "").toLowerCase()
            var rightCategory = String(right.category_display || "").toLowerCase()
            if (leftCategory !== rightCategory)
                return leftCategory < rightCategory ? -1 : 1
            var leftName = String(left.display_name || left.type_id || "").toLowerCase()
            var rightName = String(right.display_name || right.type_id || "").toLowerCase()
            return leftName < rightName ? -1 : (leftName > rightName ? 1 : 0)
        })
        var booleanQuery = root.queryText.trim().toLowerCase()
        if (root.browserMode === "nodes" && (booleanQuery === "true" || booleanQuery === "false")) {
            for (var booleanIndex = 0; booleanIndex < result.length; ++booleanIndex) {
                if (String(result[booleanIndex].type_id || "") !== "data.boolean_toggle")
                    continue
                var booleanItem = Object.assign({}, result[booleanIndex])
                booleanItem.smart_insert_properties = { "value": booleanQuery === "true" }
                result.splice(booleanIndex, 1)
                result.unshift(booleanItem)
                break
            }
        }
        if (root.browserMode === "nodes" && root.sliderQuickInsert && root.sliderQuickInsert.valid) {
            var sliderQuickInsertItem = root._numberSliderQuickInsertItem(root.sliderQuickInsert)
            if (sliderQuickInsertItem)
                result.unshift(sliderQuickInsertItem)
        }
        if (root.browserMode === "nodes" && root.panelQuickInsert && root.panelQuickInsert.valid) {
            var panelQuickInsertItem = root._panelQuickInsertItem(root.panelQuickInsert)
            if (panelQuickInsertItem) {
                result = result.filter(function(item) {
                    return String(item.type_id || "") !== "data.panel"
                })
                result.unshift(panelQuickInsertItem)
            }
        }
        return result
    }

    function _panelQuickInsert(text) {
        var raw = String(text || "")
        if (raw.charAt(0) === '"')
            return { "valid": true, "authors_text": true, "value": raw.substring(1) }
        var alias = raw.trim().toLowerCase()
        if (alias === "number" || alias === "expression")
            return { "valid": true, "authors_text": false, "value": "" }
        return ({})
    }

    function _panelQuickInsertItem(parsed) {
        var items = root.allItems || []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (String(item.type_id || "") !== "data.panel")
                continue
            var copy = Object.assign({}, item)
            copy.smart_insert_properties = parsed.authors_text
                ? { "value": String(parsed.value || ""), "mode": 0 }
                : ({})
            return copy
        }
        return null
    }

    function _numberSliderQuickInsertItem(parsed) {
        var items = root.allItems || []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (String(item.type_id || "") !== "data.number_slider")
                continue
            var copy = Object.assign({}, item)
            copy.display_name = String(item.display_name || "Number Slider")
                + " (" + String(parsed.summary || "") + ")"
            copy.smart_insert_properties = {
                "value": Number(parsed.value),
                "minimum": Number(parsed.minimum),
                "maximum": Number(parsed.maximum),
                "rounding": String(parsed.rounding || "decimal"),
                "decimals": Math.round(Number(parsed.decimals) || 0)
            }
            return copy
        }
        return null
    }

    function _groupedRows() {
        var rows = []
        var category = ""
        var pair = null
        for (var index = 0; index < root.filteredItems.length; ++index) {
            var itemCategory = String(root.filteredItems[index].category_display || "Other")
            if (itemCategory !== category) {
                category = itemCategory
                rows.push({ "kind": "category", "label": category })
                pair = null
            }
            if (!pair || pair.indices.length >= 2) {
                pair = { "kind": "nodes", "indices": [] }
                rows.push(pair)
            }
            pair.indices.push(index)
        }
        return rows
    }

    function _rowIndexForSelection(selectionIndex) {
        for (var rowIndex = 0; rowIndex < root.groupedRows.length; ++rowIndex) {
            var indices = root.groupedRows[rowIndex].indices || []
            if (indices.indexOf(selectionIndex) >= 0)
                return rowIndex
        }
        return 0
    }

    function _portsForDirection(item, direction) {
        if (!item || !item.ports)
            return []
        var result = []
        for (var index = 0; index < item.ports.length; ++index) {
            if (String(item.ports[index].direction || "") === direction)
                result.push(item.ports[index])
        }
        return result
    }

    function _moveSelection(delta) {
        if (!root.filteredItems.length) {
            root.selectedIndex = -1
            return
        }
        var current = root.selectedIndex < 0 ? 0 : root.selectedIndex
        root.selectedIndex = Math.max(0, Math.min(root.filteredItems.length - 1, current + Number(delta)))
        nodeList.positionViewAtIndex(root._rowIndexForSelection(root.selectedIndex), ListView.Contain)
    }

    function _insertSelected() {
        var item = root.selectedItem
        if (!item)
            return false
        var typeId = String(item.type_id || "")
        if (!typeId.length)
            return false
        if (item.smart_insert_properties) {
            var smartProperties = item.smart_insert_properties
            if (root.sceneAnchorActive && root.canvasCommandBridgeRef
                    && root.canvasCommandBridgeRef.request_drop_node_from_library_with_properties) {
                var createdSmart = root.canvasCommandBridgeRef.request_drop_node_from_library_with_properties(
                    typeId,
                    root.sceneAnchorX,
                    root.sceneAnchorY,
                    smartProperties
                )
                if (createdSmart)
                    root.closeBrowser()
                return Boolean(createdSmart)
            }
            if (root.shellLibraryBridgeRef
                    && root.shellLibraryBridgeRef.request_add_node_from_library_with_properties) {
                root.shellLibraryBridgeRef.request_add_node_from_library_with_properties(typeId, smartProperties)
                root.closeBrowser()
                return true
            }
            return false
        }
        if (root.sceneAnchorActive && root.canvasCommandBridgeRef
                && root.canvasCommandBridgeRef.request_drop_node_from_library) {
            var created = root.canvasCommandBridgeRef.request_drop_node_from_library(
                typeId,
                root.sceneAnchorX,
                root.sceneAnchorY,
                "",
                "",
                "",
                ""
            )
            if (created)
                root.closeBrowser()
            return Boolean(created)
        }
        root.shellLibraryBridgeRef.request_add_node_from_library(typeId)
        root.closeBrowser()
        return true
    }

    function _dragPayload(item) {
        return {
            "type_id": String(item.type_id || ""),
            "display_name": String(item.display_name || ""),
            "ports": item.ports || [],
            "runtime_behavior": String(item.runtime_behavior || "active"),
            "surface_family": String(item.surface_family || "standard"),
            "surface_variant": String(item.surface_variant || ""),
            "library_source": String(item.library_source || ""),
            "workflow_id": String(item.workflow_id || ""),
            "revision": Number(item.revision || 1),
            "workflow_scope": String(item.workflow_scope || "")
        }
    }

    function _handleNavigationKey(event) {
        if (event.key === Qt.Key_Escape) {
            root.closeBrowser()
            event.accepted = true
            return true
        }
        if (event.key === Qt.Key_Up) {
            root._moveSelection(-1)
            event.accepted = true
            return true
        }
        if (event.key === Qt.Key_Down) {
            root._moveSelection(1)
            event.accepted = true
            return true
        }
        if (event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
            root._insertSelected()
            event.accepted = true
            return true
        }
        return false
    }

    onFilteredItemsChanged: {
        root.selectedIndex = root.filteredItems.length > 0 ? 0 : -1
        if (root.visible)
            nodeList.positionViewAtBeginning()
    }

    Keys.onPressed: function(event) { root._handleNavigationKey(event) }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.52)

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onClicked: root.closeBrowser()
        }
    }

    Common.DialogSurface {
        id: panel
        objectName: "nodeBrowserPanel"
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 1080)
        height: Math.min(parent.height - 48, 680)
        themePalette: root.themePalette
        title: (root.browserMode === "templates" ? "Template Browser" : "Node Browser")
            + (root.sceneAnchorActive ? "  ·  Insert at double-click position" : "  ·  Insert at viewport center")
            + "  ·  Ctrl+B"
        closeButtonVisible: true
        onCloseRequested: root.closeBrowser()

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

                Rectangle {
                    Layout.preferredWidth: 220
                    Layout.fillHeight: true
                    color: root.themePalette.panel_alt_bg
                    border.color: root.themePalette.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        Text {
                            text: "CATEGORIES"
                            color: root.themePalette.muted_fg
                            font.pixelSize: 10
                            font.bold: true
                        }

                        ListView {
                            id: categoryList
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: 2
                            model: root.rootCategoryOptions

                            delegate: Rectangle {
                                width: ListView.view.width
                                height: 30
                                radius: 4
                                color: root.selectedCategoryKey === String(modelData.value || "")
                                    ? root.themePalette.accent_strong
                                    : (categoryMouse.containsMouse ? root.themePalette.hover : "transparent")

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 8 + Math.max(0, Number(modelData.depth || 0)) * 12
                                    anchors.right: parent.right
                                    anchors.rightMargin: 6
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: String(modelData.label || "")
                                    color: root.selectedCategoryKey === String(modelData.value || "")
                                        ? root.themePalette.tab_selected_fg
                                        : root.themePalette.app_fg
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }

                                MouseArea {
                                    id: categoryMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: {
                                        root.selectedCategoryKey = String(modelData.value || "")
                                        root.selectedCategoryPath = modelData.category_path || []
                                    }
                                }
                            }
                        }

                        Text {
                            text: "PORT FILTER"
                            color: root.themePalette.muted_fg
                            font.pixelSize: 10
                            font.bold: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Repeater {
                                model: [
                                    { "label": "All", "value": "" },
                                    { "label": "Inputs", "value": "in" },
                                    { "label": "Outputs", "value": "out" }
                                ]

                                delegate: Common.DialogButton {
                                    Layout.fillWidth: true
                                    controlHeight: 30
                                    themePalette: root.themePalette
                                    text: String(modelData.label)
                                    selected: root.directionFilter === String(modelData.value)
                                    onClicked: root.directionFilter = String(modelData.value)
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 350
                    Layout.fillHeight: true
                    color: root.themePalette.panel_bg
                    border.color: root.themePalette.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        Common.DialogTextField {
                            id: searchField
                            objectName: "nodeBrowserSearchField"
                            Layout.fillWidth: true
                            controlHeight: 34
                            themePalette: root.themePalette
                            placeholderText: "Search nodes, ports, or keywords..."
                            text: root.queryText
                            Accessible.name: "Search nodes"
                            Keys.priority: Keys.BeforeItem
                            onTextChanged: root.queryText = text
                            Keys.onPressed: function(event) { root._handleNavigationKey(event) }
                        }

                        Text {
                            text: root.filteredItems.length + " result" + (root.filteredItems.length === 1 ? "" : "s")
                            color: root.themePalette.muted_fg
                            font.pixelSize: 10
                        }

                        ListView {
                            id: nodeList
                            objectName: "nodeBrowserResultList"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: 3
                            model: root.groupedRows

                            delegate: Item {
                                id: browserRow
                                required property var modelData
                                width: ListView.view.width
                                height: String(modelData.kind || "") === "category" ? 28 : 62

                                Rectangle {
                                    objectName: "nodeBrowserCategoryHeader"
                                    anchors.fill: parent
                                    visible: String(browserRow.modelData.kind || "") === "category"
                                    color: root.themePalette.panel_alt_bg

                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: String(browserRow.modelData.label || "Other")
                                        color: root.themePalette.panel_title_fg
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }

                                Row {
                                    id: nodePair
                                    anchors.fill: parent
                                    visible: String(browserRow.modelData.kind || "") === "nodes"
                                    spacing: 6

                                    Repeater {
                                        model: browserRow.modelData.indices || []

                                        delegate: Rectangle {
                                            id: nodeTile
                                            required property var modelData
                                            property int itemIndex: Number(modelData)
                                            property var itemData: root.filteredItems[itemIndex]
                                            property var dragPayload: root._dragPayload(itemData)
                                            objectName: "nodeBrowserNodeTile"
                                            width: (browserRow.width - nodePair.spacing) / 2
                                            height: browserRow.height
                                            radius: 5
                                            color: itemIndex === root.selectedIndex
                                                ? root.themePalette.accent_strong
                                                : (nodeMouse.containsMouse ? root.themePalette.hover : "transparent")
                                            border.color: itemIndex === root.selectedIndex
                                                ? root.themePalette.accent
                                                : "transparent"
                                            border.width: itemIndex === root.selectedIndex ? 1 : 0

                                            Item {
                                                id: dragProxy
                                                width: parent.width
                                                height: parent.height
                                                opacity: 0
                                            }

                                            LibraryNodeVisual {
                                                anchors.left: parent.left
                                                anchors.leftMargin: 7
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: 38
                                                height: 34
                                                libraryVisual: nodeTile.itemData
                                                    ? nodeTile.itemData.library_visual || ({})
                                                    : ({})
                                                displayName: nodeTile.itemData
                                                    ? String(nodeTile.itemData.display_name || "")
                                                    : ""
                                                uiIconsRef: root.uiIconsRef
                                                fillColor: Qt.alpha(root.themePalette.accent, 0.16)
                                                fillCompositeBaseColor: nodeTile.color
                                                strokeColor: root.themePalette.accent
                                                iconColor: root.themePalette.app_fg
                                            }

                                            Text {
                                                anchors.left: parent.left
                                                anchors.leftMargin: 51
                                                anchors.right: parent.right
                                                anchors.rightMargin: 7
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: nodeTile.itemData
                                                    ? String(nodeTile.itemData.display_name || "")
                                                    : ""
                                                color: nodeTile.itemIndex === root.selectedIndex
                                                    ? root.themePalette.tab_selected_fg
                                                    : root.themePalette.app_fg
                                                font.pixelSize: 11
                                                font.bold: nodeTile.itemIndex === root.selectedIndex
                                                elide: Text.ElideRight
                                            }

                                            MouseArea {
                                                id: nodeMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                preventStealing: true
                                                acceptedButtons: Qt.LeftButton
                                                drag.target: (pressedButtons & Qt.LeftButton) ? dragProxy : null
                                                drag.axis: Drag.XAndYAxis
                                                property real pressStartX: 0
                                                property real pressStartY: 0
                                                property bool movedState: false

                                                onPressed: {
                                                    root.selectedIndex = nodeTile.itemIndex
                                                    dragProxy.x = 0
                                                    dragProxy.y = 0
                                                    pressStartX = mouse.x
                                                    pressStartY = mouse.y
                                                    movedState = false
                                                    mouse.accepted = true
                                                }

                                                onPositionChanged: {
                                                    if (!pressed || !root.graphCanvasRef)
                                                        return
                                                    if (Math.abs(mouse.x - pressStartX) >= 3
                                                            || Math.abs(mouse.y - pressStartY) >= 3)
                                                        movedState = true
                                                    if (!movedState)
                                                        return
                                                    var point = nodeMouse.mapToItem(
                                                        root.graphCanvasRef,
                                                        mouse.x,
                                                        mouse.y
                                                    )
                                                    if (root.graphCanvasRef.isPointInCanvas(point.x, point.y))
                                                        root.graphCanvasRef.updateLibraryDropPreview(
                                                            point.x,
                                                            point.y,
                                                            nodeTile.dragPayload
                                                        )
                                                    else
                                                        root.graphCanvasRef.clearLibraryDropPreview()
                                                }

                                                onReleased: {
                                                    if (mouse.button !== Qt.LeftButton
                                                            || !movedState
                                                            || !root.graphCanvasRef)
                                                        return
                                                    var point = nodeMouse.mapToItem(
                                                        root.graphCanvasRef,
                                                        mouse.x,
                                                        mouse.y
                                                    )
                                                    if (root.graphCanvasRef.isPointInCanvas(point.x, point.y)) {
                                                        root.graphCanvasRef.performLibraryDrop(
                                                            point.x,
                                                            point.y,
                                                            nodeTile.dragPayload
                                                        )
                                                        root.closeBrowser()
                                                    } else {
                                                        root.graphCanvasRef.clearLibraryDropPreview()
                                                    }
                                                    movedState = false
                                                }

                                                onDoubleClicked: {
                                                    root.selectedIndex = nodeTile.itemIndex
                                                    root._insertSelected()
                                                }

                                                onCanceled: {
                                                    movedState = false
                                                    if (root.graphCanvasRef)
                                                        root.graphCanvasRef.clearLibraryDropPreview()
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: root.themePalette.panel_alt_bg
                    border.color: root.themePalette.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            LibraryNodeVisual {
                                Layout.preferredWidth: 78
                                Layout.preferredHeight: 64
                                libraryVisual: root.selectedItem ? root.selectedItem.library_visual || ({}) : ({})
                                displayName: root.selectedItem ? String(root.selectedItem.display_name || "") : ""
                                uiIconsRef: root.uiIconsRef
                                fillColor: Qt.alpha(root.themePalette.accent, 0.16)
                                fillCompositeBaseColor: root.themePalette.panel_alt_bg
                                strokeColor: root.themePalette.accent
                                iconColor: root.themePalette.app_fg
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3

                                Text {
                                    Layout.fillWidth: true
                                    text: root.selectedItem ? String(root.selectedItem.display_name || "") : "Select a node"
                                    color: root.themePalette.panel_title_fg
                                    font.pixelSize: 17
                                    font.bold: true
                                    elide: Text.ElideRight
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: root.selectedItem ? String(root.selectedItem.type_id || "") : ""
                                    color: root.themePalette.muted_fg
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.selectedItem ? String(root.selectedItem.description || "No description provided.") : ""
                            color: root.themePalette.app_fg
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: root.selectedItem && (root.selectedItem.keywords || []).length > 0
                            text: root.selectedItem ? "Keywords: " + (root.selectedItem.keywords || []).join(", ") : ""
                            color: root.themePalette.muted_fg
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            Column {
                                width: Math.max(0, parent.width - 12)
                                spacing: 8

                                Text {
                                    visible: root.inputPorts.length > 0
                                    text: "INPUTS"
                                    color: root.themePalette.muted_fg
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                Repeater {
                                    model: root.inputPorts
                                    delegate: Text {
                                        width: parent.width
                                        text: "• " + String(modelData.label || modelData.key || "")
                                            + "  [" + String(modelData.data_type || "COREX.DataTypes.Any") + "]"
                                            + (String(modelData.description || "").length
                                                ? " — " + String(modelData.description)
                                                : " — No description provided.")
                                        color: root.themePalette.app_fg
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                Text {
                                    visible: root.outputPorts.length > 0
                                    text: "OUTPUTS"
                                    color: root.themePalette.muted_fg
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                Repeater {
                                    model: root.outputPorts
                                    delegate: Text {
                                        width: parent.width
                                        text: "• " + String(modelData.label || modelData.key || "")
                                            + "  [" + String(modelData.data_type || "COREX.DataTypes.Any") + "]"
                                            + (String(modelData.description || "").length
                                                ? " — " + String(modelData.description)
                                                : " — No description provided.")
                                        color: root.themePalette.app_fg
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                Text {
                                    visible: root.neutralPorts.length > 0
                                    text: "PORTS"
                                    color: root.themePalette.muted_fg
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                Repeater {
                                    model: root.neutralPorts
                                    delegate: Text {
                                        width: parent.width
                                        text: "• " + String(modelData.label || modelData.key || "")
                                            + (String(modelData.description || "").length
                                                ? " — " + String(modelData.description)
                                                : " — No description provided.")
                                        color: root.themePalette.app_fg
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Common.DialogButton {
                                id: openExampleButton
                                themePalette: root.themePalette
                                text: "Open Example"
                                enabled: false

                                Common.ManagedToolTip {
                                    policyBridge: typeof graphCanvasStateBridge !== "undefined"
                                        ? graphCanvasStateBridge
                                        : null
                                    category: "general"
                                    active: openExampleButton.hovered
                                    text: "No example is available for this node."
                                }
                            }

                            Item { Layout.fillWidth: true }

                            Common.DialogButton {
                                themePalette: root.themePalette
                                text: "Show Help"
                                enabled: root.selectedItem
                                    && String(root.selectedItem.library_source || "") === "node_registry"
                                    && root.helpBridgeRef
                                onClicked: {
                                    if (root.helpBridgeRef.show_help_for_type(String(root.selectedItem.type_id || "")))
                                        root.closeBrowser()
                                }
                            }

                            Common.DialogButton {
                                themePalette: root.themePalette
                                primary: true
                                text: root.sceneAnchorActive ? "Insert Here" : "Insert"
                                enabled: root.selectedItem !== null
                                onClicked: root._insertSelected()
                            }
                        }
                    }
                }
        }
    }
}
