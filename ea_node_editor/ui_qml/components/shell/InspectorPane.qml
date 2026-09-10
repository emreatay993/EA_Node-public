import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common/TooltipCopy.js" as TooltipCopy

ShellCollapsibleSidePane {
    id: root
    objectName: "inspectorPane"
    tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "inspector.pane.collapse")
    property var inspectorBridgeRef: typeof shellInspectorBridge !== "undefined" ? shellInspectorBridge : null
    property var helpBridgeRef: (typeof helpBridge !== "undefined") ? helpBridge : null
    property int activeTabIndex: 0
    property string activePortDirection: "in"
    property string selectedPortKey: ""
    property string editingPortKey: ""
    property string editingPortLabel: ""
    readonly property bool hasSelectedNode: !!root.inspectorBridgeRef && root.inspectorBridgeRef.has_selected_node
    readonly property bool isPinInspector: !!root._content.selected_node_is_subnode_pin
    readonly property bool showPortSection: root.hasSelectedNode && !root.isPinInspector
    readonly property bool canManageSubnodePorts: !!root._content.selected_node_is_subnode_shell
    readonly property bool canEditPortLabels: root.hasSelectedNode && !root.isPinInspector
    readonly property string selectedNodeTitle: root._contentReady ? root._content.selected_node_title : ""
    readonly property string selectedNodeSubtitle: root._contentReady ? root._content.selected_node_subtitle : ""
    readonly property string selectedNodeId: root.inspectorBridgeRef ? root.inspectorBridgeRef.selected_node_id : ""
    readonly property string selectedNodeWorkspaceId: root.inspectorBridgeRef ? root.inspectorBridgeRef.selected_node_workspace_id : ""
    readonly property bool selectedNodeCollapsible: !!root._content.selected_node_collapsible
    readonly property bool selectedNodeCollapsed: !!root._content.selected_node_collapsed
    readonly property var selectedNodePortItems: root._contentReady ? (root._content.selected_node_port_items || []) : []
    readonly property var selectedNodeHeaderItems: root._contentReady ? (root._content.selected_node_header_items || []) : []
    readonly property var propertyPresentationLookup: root.propertiesRequested && root.graphCanvasStateBridgeRef
        && typeof root.graphCanvasStateBridgeRef.property_presentation_lookup !== "undefined"
        ? root.graphCanvasStateBridgeRef.property_presentation_lookup
        : ({})
    property var selectedNodePropertyItems: []
    readonly property var selectedNodeLinkItems: root._contentReady ? (root._content.selected_node_link_items || []) : []
    readonly property var selectedNodeCommentItems: root._contentReady ? (root._content.selected_node_comment_items || []) : []
    readonly property var selectedNodeLinkNodeOptions: root._contentReady ? (root._content.selected_node_link_node_options || []) : []
    readonly property var selectedNodeLinkWorkspaceOptions: root._contentReady ? (root._content.selected_node_link_workspace_options || []) : []
    readonly property var pinDataTypeOptions: root._contentReady ? (root._content.pin_data_type_options || []) : []
    readonly property bool propertiesRequested: visible && !paneCollapsed && activeTabIndex === 0
    property var _content: ({})
    property bool _contentReady: false
    property string _contentNodeId: ""
    property string _contentWorkspaceId: ""

    function refreshPropertyPresentation() {
        if (propertiesRequested && _contentReady)
            selectedNodePropertyItems = _propertyItemsWithPresentation(_content.selected_node_property_items || [])
    }

    function refreshContent() {
        var bridge = root.inspectorBridgeRef
        if (bridge)
            bridge.set_content_active(root.propertiesRequested)
        var nodeId = bridge ? String(bridge.selected_node_id || "") : ""
        var workspaceId = bridge ? String(bridge.selected_node_workspace_id || "") : ""
        if (nodeId !== _contentNodeId || workspaceId !== _contentWorkspaceId) {
            // Retire the old context before publishing values for another node.
            _contentReady = false
            _contentNodeId = nodeId
            _contentWorkspaceId = workspaceId
            _content = ({})
            selectedNodePropertyItems = []
        }
        if (!propertiesRequested || !nodeId.length || !bridge)
            return
        var next = {
            selected_node_title: bridge.selected_node_title,
            selected_node_subtitle: bridge.selected_node_subtitle,
            selected_node_is_subnode_pin: bridge.selected_node_is_subnode_pin,
            selected_node_is_subnode_shell: bridge.selected_node_is_subnode_shell,
            selected_node_collapsible: bridge.selected_node_collapsible,
            selected_node_collapsed: bridge.selected_node_collapsed,
            selected_node_port_items: bridge.selected_node_port_items,
            selected_node_header_items: bridge.selected_node_header_items,
            selected_node_property_items: bridge.selected_node_property_items,
            selected_node_link_items: bridge.selected_node_link_items,
            selected_node_comment_items: bridge.selected_node_comment_items,
            selected_node_link_node_options: bridge.selected_node_link_node_options,
            selected_node_link_workspace_options: bridge.selected_node_link_workspace_options
        }
        next.pin_data_type_options = next.selected_node_is_subnode_pin ? bridge.pin_data_type_options : []
        _content = next
        selectedNodePropertyItems = _propertyItemsWithPresentation(next.selected_node_property_items || [])
        _contentReady = true
    }

    onPropertiesRequestedChanged: refreshContent()
    onInspectorBridgeRefChanged: refreshContent()
    onPropertyPresentationLookupChanged: refreshPropertyPresentation()
    Component.onCompleted: refreshContent()

    readonly property var visiblePortItems: root.portItemsForDirection(activePortDirection)
    readonly property int inputPortCount: root.portItemsForDirection("in").length
    readonly property int outputPortCount: root.portItemsForDirection("out").length
    readonly property color cardBackgroundColor: root.themePalette.inspector_card_bg
    readonly property color sectionHeaderColor: root.themePalette.inspector_section_header_bg
    readonly property color selectedSurfaceColor: root.themePalette.inspector_selected_bg
    readonly property color selectedOutlineColor: root.themePalette.inspector_selected_border

    paneTitle: "PROPERTIES"
    side: "right"
    persistedPanelId: "property_pane"
    expandedWidth: 300
    contentSpacing: 0
    collapseButtonTooltip: TooltipCopy.text(tooltipCopyBridge, "inspector.pane.collapse")
    expandHandleTooltip: TooltipCopy.text(tooltipCopyBridge, "inspector.pane.expand")

    signal linkTargetPickRequested(string kind)
    signal linkTargetPickCancelled()

    function portItemsForDirection(direction) {
        var normalizedDirection = String(direction || "").toLowerCase()
        var items = root.selectedNodePortItems
        var filtered = []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (!item)
                continue
            if (String(item.direction || "").toLowerCase() !== normalizedDirection)
                continue
            filtered.push(item)
        }
        return filtered
    }

    function _propertyItemsWithPresentation(items) {
        var nodePresentations = root.propertyPresentationLookup
            && root.propertyPresentationLookup[root.selectedNodeId]
            ? root.propertyPresentationLookup[root.selectedNodeId]
            : ({})
        var resolved = []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (!item)
                continue
            var merged = ({})
            for (var itemKey in item)
                merged[itemKey] = item[itemKey]
            var presentation = nodePresentations[String(item.key || "")]
            if (presentation) {
                for (var presentationKey in presentation)
                    merged[presentationKey] = presentation[presentationKey]
            }
            resolved.push(merged)
        }
        return resolved
    }

    function hasVisiblePort(portKey) {
        var normalizedKey = String(portKey || "")
        if (!normalizedKey.length)
            return false
        for (var index = 0; index < visiblePortItems.length; ++index) {
            var item = visiblePortItems[index]
            if (String(item.key || "") === normalizedKey)
                return true
        }
        return false
    }

    function portItemByKey(portKey) {
        var normalizedKey = String(portKey || "")
        if (!normalizedKey.length)
            return null
        var items = root.selectedNodePortItems
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (!item)
                continue
            if (String(item.key || "") === normalizedKey)
                return item
        }
        return null
    }

    function syncSelectedPortSelection() {
        if (!showPortSection || visiblePortItems.length === 0) {
            selectedPortKey = ""
            editingPortKey = ""
            editingPortLabel = ""
            return
        }
        if (!hasVisiblePort(selectedPortKey))
            selectedPortKey = String(visiblePortItems[visiblePortItems.length - 1].key || "")
        if (editingPortKey.length > 0 && !hasVisiblePort(editingPortKey)) {
            editingPortKey = ""
            editingPortLabel = ""
        }
    }

    function addSubnodePort(direction) {
        var normalizedDirection = String(direction || "").toLowerCase()
        if (!root.inspectorBridgeRef)
            return
        var createdPortKey = root.inspectorBridgeRef.request_add_selected_subnode_pin(normalizedDirection)
        if (!String(createdPortKey || "").length)
            return
        activePortDirection = normalizedDirection
        selectedPortKey = String(createdPortKey)
    }

    function selectPort(portKey) {
        var normalizedKey = String(portKey || "")
        if (!normalizedKey.length)
            return
        selectedPortKey = normalizedKey
    }

    function beginPortLabelEdit(portKey) {
        var normalizedKey = String(portKey || "")
        if (!canEditPortLabels || !normalizedKey.length)
            return
        var item = portItemByKey(normalizedKey)
        if (!item)
            return
        editingPortLabel = String(item ? (item.label || item.key || "") : normalizedKey)
        selectPort(normalizedKey)
        editingPortKey = normalizedKey
    }

    function commitPortLabelEdit(portKey, label) {
        var normalizedKey = String(portKey || "")
        if (editingPortKey !== normalizedKey)
            return
        if (root.inspectorBridgeRef)
            root.inspectorBridgeRef.set_selected_port_label(normalizedKey, String(label || ""))
        editingPortKey = ""
        editingPortLabel = ""
    }

    function cancelPortLabelEdit(portKey) {
        var normalizedKey = String(portKey || "")
        if (editingPortKey === normalizedKey) {
            editingPortKey = ""
            editingPortLabel = ""
        }
    }

    function focusInspectorBackground() {
        if (editingPortKey.length > 0)
            commitPortLabelEdit(editingPortKey, editingPortLabel)
        root.forceActiveFocus()
    }

    function deleteSelectedPort() {
        var normalizedKey = String(selectedPortKey || "")
        if (!root.inspectorBridgeRef || !normalizedKey.length)
            return
        focusInspectorBackground()
        root.inspectorBridgeRef.request_remove_selected_port(normalizedKey)
    }

    function openCommentsForSelectedNode() {
        if (root.paneCollapsed)
            root.expandPane()
        root.activeTabIndex = 0
        Qt.callLater(function() {
            if (nodeCommentsSection && nodeCommentsSection.visible)
                nodeCommentsSection.markRead()
        })
    }

    function beginAddCommentForSelectedNode() {
        if (root.paneCollapsed)
            root.expandPane()
        root.activeTabIndex = 0
        Qt.callLater(function() {
            if (nodeCommentsSection && nodeCommentsSection.visible)
                nodeCommentsSection.beginNewComment("")
        })
    }

    function applyLinkTargetPick(kind, workspaceId, nodeId, label, subtitle) {
        if (root.paneCollapsed)
            root.expandPane()
        Qt.callLater(function() {
            if (nodeLinksSection && nodeLinksSection.visible)
                nodeLinksSection.applyPickedTarget(kind, workspaceId, nodeId, label, subtitle)
        })
    }

    function cancelLinkTargetPick() {
        if (nodeLinksSection)
            nodeLinksSection.clearPickMode()
    }

    onVisiblePortItemsChanged: syncSelectedPortSelection()
    onShowPortSectionChanged: syncSelectedPortSelection()

    contentData: [
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                spacing: 2

                Repeater {
                    model: [
                        { label: "Properties", index: 0 },
                        { label: "Help", index: 1 }
                    ]

                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        color: root.activeTabIndex === modelData.index
                            ? root.themePalette.tab_selected_bg
                            : root.themePalette.tab_bg
                        border.color: root.themePalette.border

                        Text {
                            anchors.centerIn: parent
                            text: modelData.label
                            color: root.activeTabIndex === modelData.index
                                ? root.themePalette.tab_selected_fg
                                : root.themePalette.tab_fg
                            font.pixelSize: 11
                            font.bold: root.activeTabIndex === modelData.index
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.activeTabIndex = modelData.index
                                if (modelData.index === 1 && root.helpBridgeRef) {
                                    root.helpBridgeRef.show_help_for_selected_node()
                                }
                            }
                        }
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.activeTabIndex

                Rectangle {
                    objectName: "inspectorContentSurface"
                    color: "transparent"

                    TapHandler {
                        enabled: root.editingPortKey.length > 0
                        acceptedButtons: Qt.LeftButton
                        onTapped: root.focusInspectorBackground()
                    }

                    ScrollView {
                        id: inspectorScroll
                        objectName: "inspectorScrollView"
                        anchors.fill: parent
                        anchors.leftMargin: 2
                        anchors.rightMargin: 2
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        TapHandler {
                            enabled: root.editingPortKey.length > 0
                            acceptedButtons: Qt.LeftButton
                            onTapped: root.focusInspectorBackground()
                        }

                        background: Rectangle {
                            color: "transparent"

                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                onTapped: root.focusInspectorBackground()
                            }
                        }

                        Column {
                            id: inspectorColumn
                            width: inspectorScroll.availableWidth
                            spacing: 10

                            InspectorSectionCard {
                                pane: root
                                objectName: "inspectorEmptyStateCard"
                                width: inspectorColumn.width
                                visible: !root.hasSelectedNode
                                title: "No Selection"
                                subtitle: "Select a node on the graph to inspect its properties and exposed ports."

                                Text {
                                    width: parent.width
                                    text: "The selected node's definition, editable fields, and port exposure controls will appear here."
                                    wrapMode: Text.WordWrap
                                    color: root.themePalette.muted_fg
                                    font.pixelSize: 11
                                }
                            }

                            InspectorNodeDefinitionSection {
                                pane: root
                                width: inspectorColumn.width
                            }

                            InspectorNodeLinksSection {
                                id: nodeLinksSection
                                pane: root
                                width: inspectorColumn.width
                                onPickTargetRequested: function(kind) {
                                    root.linkTargetPickRequested(String(kind || ""))
                                }
                                onPickTargetCancelled: root.linkTargetPickCancelled()
                            }

                            InspectorNodeCommentsSection {
                                id: nodeCommentsSection
                                pane: root
                                width: inspectorColumn.width
                            }

                            Loader {
                                id: inspectorPropertyVariantLoader
                                objectName: "inspectorPropertyVariantLoader"
                                width: inspectorColumn.width
                                height: item ? item.implicitHeight : 0
                                visible: root.hasSelectedNode
                                active: root.hasSelectedNode && root._contentReady
                                    && root._contentNodeId === root.selectedNodeId
                                    && root._contentWorkspaceId === root.selectedNodeWorkspaceId

                                property var paneRef: root
                                property var propertyItems: root.selectedNodePropertyItems

                                sourceComponent: {
                                    var variant = root.inspectorBridgeRef ? root.inspectorBridgeRef.property_pane_variant : "smart_groups"
                                    switch (String(variant || "")) {
                                        case "accordion_cards": return accordionCardsBodyComponent
                                        case "palette":         return paletteBodyComponent
                                        case "smart_groups":
                                        default:                return smartGroupsBodyComponent
                                    }
                                }

                                Component {
                                    id: smartGroupsBodyComponent
                                    InspectorSmartGroupsBody {
                                        pane: inspectorPropertyVariantLoader.paneRef
                                        propertyItems: inspectorPropertyVariantLoader.propertyItems
                                    }
                                }

                                Component {
                                    id: accordionCardsBodyComponent
                                    InspectorAccordionCardsBody {
                                        pane: inspectorPropertyVariantLoader.paneRef
                                        propertyItems: inspectorPropertyVariantLoader.propertyItems
                                    }
                                }

                                Component {
                                    id: paletteBodyComponent
                                    InspectorPaletteBody {
                                        pane: inspectorPropertyVariantLoader.paneRef
                                        propertyItems: inspectorPropertyVariantLoader.propertyItems
                                    }
                                }
                            }

                            InspectorPortManagementSection {
                                pane: root
                                width: inspectorColumn.width
                            }
                        }
                    }
                }

                HelpPane {
                    objectName: "inspectorHelpSurface"
                    helpBridgeRef: root.helpBridgeRef
                    themeBridgeRef: root.themeBridgeRef
                    hasSelectedNode: root.hasSelectedNode
                }
            }
        }
    ]

    Connections {
        target: root.helpBridgeRef
        function onHelp_visible_changed() {
            if (root.helpBridgeRef && root.helpBridgeRef.visible) {
                root.activeTabIndex = 1
                if (root.paneCollapsed)
                    root.expandPane()
            }
        }
        function onHelp_tab_requested() {
            root.activeTabIndex = 1
            if (root.paneCollapsed)
                root.expandPane()
        }
    }

    Connections {
        target: root.inspectorBridgeRef
        function onInspector_state_changed() {
            root.refreshContent()
            root.syncSelectedPortSelection()
        }
    }
}
