import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common" as Common
import "../common/TooltipCopy.js" as TooltipCopy

ShellCollapsibleSidePane {
    id: root
    objectName: "libraryPane"
    tooltipCategory: "general"
    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property var graphCanvasRef
    property var popupHostItem
    property var collapsedCategories: ({})
    readonly property string passiveLibraryDisplayMode: root.shellLibraryBridgeRef
        ? String(root.shellLibraryBridgeRef.passive_node_library_display_mode || "text")
        : "text"
    signal workflowContextRequested(string workflowId, string workflowScope, real positionX, real positionY)

    paneTitle: "NODE LIBRARY"
    side: "left"
    persistedPanelId: "node_library"
    expandedWidth: 260
    collapseButtonTooltip: TooltipCopy.text(tooltipCopyBridge, "shell.node_library.collapse")
    expandHandleTooltip: TooltipCopy.text(tooltipCopyBridge, "shell.node_library.expand")

    function categoryKeyForRow(row) {
        if (!row)
            return ""
        return String(row.category_key || "")
    }

    function depthForRow(row) {
        if (!row || row.depth === undefined || row.depth === null)
            return 0
        var depth = Number(row.depth)
        if (!isFinite(depth) || depth < 0)
            return 0
        return Math.floor(depth)
    }

    function rowIndentForRow(row) {
        var baseIndent = 8 + (depthForRow(row) * 14)
        if (row && row.kind !== "category")
            return baseIndent + 10
        return baseIndent
    }

    function dragPayloadForItem(item) {
        if (!item)
            return null
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

    function visualKindForItem(item) {
        var visual = item ? item.library_visual : null
        return String(visual ? visual.kind || "none" : "none")
    }

    function hasPassiveVisual(item) {
        var runtimeBehavior = String(item ? item.runtime_behavior || "" : "").toLowerCase()
        return runtimeBehavior === "passive" && visualKindForItem(item) !== "none"
    }

    function gridColumnsForWidth(widthValue, indentValue) {
        var available = Math.max(72, Number(widthValue) - Number(indentValue || 0) - 14)
        return Math.max(1, Math.floor(available / 64))
    }

    function primaryDataPort(item, direction) {
        var ports = item && item.ports ? item.ports : []
        for (var index = 0; index < ports.length; ++index) {
            var port = ports[index]
            if (String(port.direction || "") === direction && String(port.kind || "") === "data")
                return port
        }
        return null
    }

    function compactDescription(description) {
        var normalized = String(description || "").replace(/\s+/g, " ").trim()
        if (!normalized.length)
            return ""
        var sentenceEnd = normalized.search(/[.!?](\s|$)/)
        var compact = sentenceEnd >= 0 ? normalized.slice(0, sentenceEnd + 1) : normalized
        if (compact.length > 200)
            compact = compact.slice(0, 197).trim() + "..."
        return compact
    }

    function libraryItemTooltip(item) {
        if (!item)
            return ""
        var lines = [String(item.display_name || "")]
        var description = root.compactDescription(item.description)
        if (description.length)
            lines.push(description)
        var directions = ["in", "out"]
        var copyKeys = ["nodes.library.tooltip.input", "nodes.library.tooltip.output"]
        for (var index = 0; index < directions.length; ++index) {
            var port = primaryDataPort(item, directions[index])
            if (!port)
                continue
            var portName = String(port.label || port.key || "")
            var dataType = String(port.data_type || "")
            var portSummary = portName
            if (dataType.length)
                portSummary += " · " + dataType
            lines.push(TooltipCopy.text(tooltipCopyBridge, copyKeys[index]) + " " + portSummary)
        }
        return lines.join("\n")
    }

    function isCategoryCollapsed(categoryKey) {
        var normalizedCategoryKey = String(categoryKey || "")
        if (!normalizedCategoryKey.length)
            return true
        var value = collapsedCategories[normalizedCategoryKey]
        if (value === undefined)
            return true
        return !!value
    }

    function setCategoryCollapsed(categoryKey, collapsed) {
        var normalizedCategoryKey = String(categoryKey || "")
        if (!normalizedCategoryKey.length)
            return
        var nextMap = {}
        for (var key in collapsedCategories)
            nextMap[key] = collapsedCategories[key]
        nextMap[normalizedCategoryKey] = !!collapsed
        collapsedCategories = nextMap
    }

    function ancestorsExpanded(ancestorCategoryKeys) {
        if (!ancestorCategoryKeys || ancestorCategoryKeys.length === undefined)
            return true
        for (var index = 0; index < ancestorCategoryKeys.length; ++index) {
            var categoryKey = String(ancestorCategoryKeys[index] || "")
            if (categoryKey.length && isCategoryCollapsed(categoryKey))
                return false
        }
        return true
    }

    function isRowHiddenByAncestors(row) {
        if (!row)
            return true
        return !ancestorsExpanded(row.ancestor_category_keys || [])
    }

    function ensureCollapsedDefaults(rows) {
        if (!rows || rows.length === undefined)
            return
        var nextMap = {}
        for (var key in collapsedCategories)
            nextMap[key] = collapsedCategories[key]
        var changed = false
        for (var index = 0; index < rows.length; ++index) {
            var row = rows[index]
            if (!row || row.kind !== "category")
                continue
            var categoryKey = categoryKeyForRow(row)
            if (!categoryKey.length || nextMap[categoryKey] !== undefined)
                continue
            nextMap[categoryKey] = true
            changed = true
        }
        if (changed)
            collapsedCategories = nextMap
    }

    function resetCollapsedState() {
        collapsedCategories = ({})
        ensureCollapsedDefaults(libraryListView.model)
    }

    contentData: [
        TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "Search nodes..."
            color: root.themePalette.input_fg
            placeholderTextColor: root.themePalette.muted_fg
            background: Rectangle {
                color: root.themePalette.input_bg
                border.color: root.themePalette.input_border
                radius: 3
            }
            onTextChanged: root.shellLibraryBridgeRef.set_library_query(text)
        },

        ListView {
            id: libraryListView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.shellLibraryBridgeRef.display_node_library_items
            spacing: 0
            Component.onCompleted: root.ensureCollapsedDefaults(model)
            onModelChanged: root.ensureCollapsedDefaults(model)

            delegate: Rectangle {
                id: libraryRow
                objectName: "nodeLibraryRow"
                property bool isCategory: modelData.kind === "category"
                property bool isIconGrid: modelData.kind === "passive_icon_grid"
                property bool isCustomWorkflow: !isCategory && String(modelData.library_source || "") === "custom_workflow"
                property string workflowScope: String(modelData.workflow_scope || "")
                property string rowCategoryKey: root.categoryKeyForRow(modelData)
                property string rowTypeId: isCategory || isIconGrid ? "" : String(modelData.type_id || "")
                property int rowDepth: root.depthForRow(modelData)
                property real rowIndent: root.rowIndentForRow(modelData)
                property bool hiddenByAncestors: root.isRowHiddenByAncestors(modelData)
                property bool showPassiveInlineVisual: !isCategory
                    && !isIconGrid
                    && root.passiveLibraryDisplayMode === "text_icon"
                    && root.hasPassiveVisual(modelData)
                property var gridItems: isIconGrid && modelData.items ? modelData.items : []
                property int gridColumns: isIconGrid
                    ? root.gridColumnsForWidth(width, rowIndent)
                    : 1
                property int gridRows: isIconGrid
                    ? Math.max(1, Math.ceil(gridItems.length / Math.max(1, gridColumns)))
                    : 1
                property var dragPayload: isCategory || isIconGrid ? null : root.dragPayloadForItem(modelData)
                width: ListView.view.width
                height: hiddenByAncestors ? 0 : (
                    isCategory
                        ? 32
                        : (isIconGrid ? (gridRows * 68 + 10) : (showPassiveInlineVisual ? 36 : 28))
                )
                color: hiddenByAncestors ? "transparent"
                    : (mouseArea.containsMouse ? root.themePalette.hover : "transparent")
                radius: 4
                visible: !hiddenByAncestors

                Common.ManagedToolTip {
                    policyBridge: root.graphCanvasStateBridgeRef
                    category: root.tooltipCategory
                    active: mouseArea.containsMouse && !libraryRow.isCategory
                    text: root.libraryItemTooltip(modelData)
                    maximumTextWidth: 320
                    delay: 350
                }

                Item {
                    id: dragProxy
                    width: parent.width
                    height: parent.height
                    x: 0
                    y: 0
                    opacity: 0
                    Drag.active: !libraryRow.isCategory && !libraryRow.isIconGrid && mouseArea.drag.active
                    Drag.source: libraryRow
                    Drag.keys: ["ea-node-library"]
                    Drag.supportedActions: Qt.CopyAction
                    Drag.hotSpot.x: mouseArea.mouseX
                    Drag.hotSpot.y: mouseArea.mouseY
                    Drag.mimeData: libraryRow.dragPayload
                        ? {
                            "application/x-ea-node-library":
                                JSON.stringify(libraryRow.dragPayload)
                        }
                        : ({})
                }

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: libraryRow.rowIndent
                    spacing: 6
                    visible: !libraryRow.isIconGrid

                    Rectangle {
                        width: isCategory ? 0 : 8
                        height: isCategory ? 0 : 8
                        radius: 4
                        visible: !isCategory && !libraryRow.showPassiveInlineVisual
                        border.color: root.themePalette.accent
                        border.width: libraryRow.isCustomWorkflow && libraryRow.workflowScope === "local" ? 1.5 : 0
                        color: libraryRow.isCustomWorkflow && libraryRow.workflowScope === "local"
                            ? "transparent"
                            : root.themePalette.accent
                    }

                    LibraryNodeVisual {
                        width: libraryRow.showPassiveInlineVisual ? 28 : 0
                        height: libraryRow.showPassiveInlineVisual ? 22 : 0
                        visible: libraryRow.showPassiveInlineVisual
                        libraryVisual: modelData.library_visual || ({})
                        displayName: String(modelData.display_name || "")
                        uiIconsRef: root.uiIconsRef
                        fillColor: Qt.alpha(root.themePalette.accent, 0.18)
                        fillCompositeBaseColor: mouseArea.containsMouse
                            ? root.themePalette.hover
                            : root.themePalette.panel_alt_bg
                        strokeColor: root.themePalette.accent
                        iconColor: root.themePalette.app_fg
                        strokeWidth: 1.1
                    }

                    Text {
                        text: isCategory
                            ? ((root.isCategoryCollapsed(libraryRow.rowCategoryKey) ? "▸ " : "▾ ") + modelData.label)
                            : modelData.display_name
                        color: isCategory ? root.themePalette.group_title_fg : root.themePalette.app_fg
                        font.pixelSize: isCategory ? 12 : 11
                        font.bold: isCategory
                    }
                }

                Flow {
                    id: passiveIconGrid
                    objectName: "nodeLibraryPassiveIconGrid"
                    visible: libraryRow.isIconGrid
                    anchors.left: parent.left
                    anchors.leftMargin: libraryRow.rowIndent
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.top: parent.top
                    anchors.topMargin: 5
                    spacing: 6

                    Repeater {
                        model: libraryRow.gridItems

                        delegate: Rectangle {
                            id: libraryTile
                            objectName: "nodeLibraryGridTile"
                            property var tilePayload: root.dragPayloadForItem(modelData)
                            width: 58
                            height: 62
                            radius: 5
                            color: tileMouseArea.containsMouse ? root.themePalette.hover : "transparent"
                            border.color: tileMouseArea.containsMouse ? root.themePalette.accent : "transparent"
                            border.width: tileMouseArea.containsMouse ? 1 : 0

                            Common.ManagedToolTip {
                                policyBridge: root.graphCanvasStateBridgeRef
                                category: root.tooltipCategory
                                active: tileMouseArea.containsMouse
                                text: root.libraryItemTooltip(modelData)
                                maximumTextWidth: 320
                                delay: 350
                            }

                            Item {
                                id: tileDragProxy
                                width: parent.width
                                height: parent.height
                                x: 0
                                y: 0
                                opacity: 0
                                Drag.active: tileMouseArea.drag.active
                                Drag.source: libraryTile
                                Drag.keys: ["ea-node-library"]
                                Drag.supportedActions: Qt.CopyAction
                                Drag.hotSpot.x: tileMouseArea.mouseX
                                Drag.hotSpot.y: tileMouseArea.mouseY
                                Drag.mimeData: libraryTile.tilePayload
                                    ? {
                                        "application/x-ea-node-library":
                                            JSON.stringify(libraryTile.tilePayload)
                                    }
                                    : ({})
                            }

                            LibraryNodeVisual {
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: 6
                                width: 44
                                height: 32
                                libraryVisual: modelData.library_visual || ({})
                                displayName: String(modelData.display_name || "")
                                uiIconsRef: root.uiIconsRef
                                fillColor: Qt.alpha(root.themePalette.accent, 0.15)
                                fillCompositeBaseColor: tileMouseArea.containsMouse
                                    ? root.themePalette.hover
                                    : root.themePalette.panel_alt_bg
                                strokeColor: root.themePalette.accent
                                iconColor: root.themePalette.app_fg
                                strokeWidth: 1.2
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 4
                                text: String(modelData.display_name || "")
                                color: root.themePalette.app_fg
                                font.pixelSize: 9
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                                maximumLineCount: 1
                            }

                            MouseArea {
                                id: tileMouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                preventStealing: true
                                acceptedButtons: Qt.LeftButton
                                drag.target: (pressedButtons & Qt.LeftButton) ? tileDragProxy : null
                                drag.axis: Drag.XAndYAxis
                                property real pressStartX: 0
                                property real pressStartY: 0
                                property bool movedState: false

                                onPressed: {
                                    if (mouse.button !== Qt.LeftButton)
                                        return
                                    tileDragProxy.x = 0
                                    tileDragProxy.y = 0
                                    root.graphCanvasRef.clearLibraryDropPreview()
                                    pressStartX = mouse.x
                                    pressStartY = mouse.y
                                    movedState = false
                                    mouse.accepted = true
                                }

                                onPositionChanged: {
                                    if (!pressed)
                                        return
                                    if (Math.abs(mouse.x - pressStartX) >= 2 || Math.abs(mouse.y - pressStartY) >= 2)
                                        movedState = true
                                    if (!movedState)
                                        return
                                    var canvasPoint = tileMouseArea.mapToItem(root.graphCanvasRef, mouse.x, mouse.y)
                                    if (root.graphCanvasRef.isPointInCanvas(canvasPoint.x, canvasPoint.y))
                                        root.graphCanvasRef.updateLibraryDropPreview(canvasPoint.x, canvasPoint.y, libraryTile.tilePayload)
                                    else
                                        root.graphCanvasRef.clearLibraryDropPreview()
                                }

                                onReleased: {
                                    if (mouse.button !== Qt.LeftButton)
                                        return
                                    if (movedState) {
                                        var canvasPoint = tileMouseArea.mapToItem(root.graphCanvasRef, mouse.x, mouse.y)
                                        if (root.graphCanvasRef.isPointInCanvas(canvasPoint.x, canvasPoint.y))
                                            root.graphCanvasRef.performLibraryDrop(canvasPoint.x, canvasPoint.y, libraryTile.tilePayload)
                                        else
                                            root.graphCanvasRef.clearLibraryDropPreview()
                                        Qt.callLater(function() {
                                            tileDragProxy.x = 0
                                            tileDragProxy.y = 0
                                        })
                                        movedState = false
                                        return
                                    }
                                    root.shellLibraryBridgeRef.request_add_node_from_library(modelData.type_id)
                                }

                                onCanceled: {
                                    movedState = false
                                    root.graphCanvasRef.clearLibraryDropPreview()
                                    Qt.callLater(function() {
                                        tileDragProxy.x = 0
                                        tileDragProxy.y = 0
                                    })
                                }
                            }
                        }
                    }
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    enabled: !libraryRow.isIconGrid
                    hoverEnabled: true
                    preventStealing: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    drag.target: (isCategory || !(pressedButtons & Qt.LeftButton)) ? null : dragProxy
                    drag.axis: Drag.XAndYAxis
                    property real pressStartX: 0
                    property real pressStartY: 0
                    property bool movedState: false

                    onPressed: {
                        if (mouse.button === Qt.RightButton) {
                            if (libraryRow.isCustomWorkflow) {
                                var popupHost = root.popupHostItem ? root.popupHostItem : root
                                var pointInHost = libraryRow.mapToItem(popupHost, mouse.x, mouse.y)
                                root.workflowContextRequested(
                                    String(modelData.workflow_id || ""),
                                    libraryRow.workflowScope,
                                    pointInHost.x,
                                    pointInHost.y
                                )
                            }
                            mouse.accepted = true
                            return
                        }
                        if (mouse.button !== Qt.LeftButton)
                            return
                        dragProxy.x = 0
                        dragProxy.y = 0
                        root.graphCanvasRef.clearLibraryDropPreview()
                        pressStartX = mouse.x
                        pressStartY = mouse.y
                        movedState = false
                        mouse.accepted = true
                    }

                    onPositionChanged: {
                        if (!pressed)
                            return
                        if (Math.abs(mouse.x - pressStartX) >= 2 || Math.abs(mouse.y - pressStartY) >= 2)
                            movedState = true
                        if (!movedState || isCategory)
                            return
                        var canvasPoint = mouseArea.mapToItem(root.graphCanvasRef, mouse.x, mouse.y)
                        if (root.graphCanvasRef.isPointInCanvas(canvasPoint.x, canvasPoint.y))
                            root.graphCanvasRef.updateLibraryDropPreview(canvasPoint.x, canvasPoint.y, libraryRow.dragPayload)
                        else
                            root.graphCanvasRef.clearLibraryDropPreview()
                    }

                    onReleased: {
                        if (mouse.button !== Qt.LeftButton)
                            return
                        if (movedState) {
                            if (!isCategory) {
                                var canvasPoint = mouseArea.mapToItem(root.graphCanvasRef, mouse.x, mouse.y)
                                if (root.graphCanvasRef.isPointInCanvas(canvasPoint.x, canvasPoint.y))
                                    root.graphCanvasRef.performLibraryDrop(canvasPoint.x, canvasPoint.y, libraryRow.dragPayload)
                                else
                                    root.graphCanvasRef.clearLibraryDropPreview()
                            } else {
                                root.graphCanvasRef.clearLibraryDropPreview()
                            }
                            Qt.callLater(function() {
                                dragProxy.x = 0
                                dragProxy.y = 0
                            })
                            movedState = false
                            return
                        }
                        if (isCategory) {
                            root.setCategoryCollapsed(
                                libraryRow.rowCategoryKey,
                                !root.isCategoryCollapsed(libraryRow.rowCategoryKey)
                            )
                        } else {
                            root.shellLibraryBridgeRef.request_add_node_from_library(modelData.type_id)
                        }
                    }

                    onCanceled: {
                        movedState = false
                        root.graphCanvasRef.clearLibraryDropPreview()
                        Qt.callLater(function() {
                            dragProxy.x = 0
                            dragProxy.y = 0
                        })
                    }
                }
            }
        }
    ]

    Connections {
        target: root.shellLibraryBridgeRef
        function onLibraryPaneResetRequested() {
            root.resetCollapsedState()
        }
    }
}
