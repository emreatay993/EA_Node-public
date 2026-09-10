import QtQuick 2.15
import QtQuick.Controls 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph" as Graph
import "../../ea_node_editor/ui_qml/components/graph/GraphActionPresentation.js" as Presentation
import "../../ea_node_editor/ui_qml/components/graph/surface_controls" as Controls
import "../../ea_node_editor/ui_qml/components/graph/overlay" as GraphOverlay
import "../../ea_node_editor/ui_qml/components/common" as Common

TestCase {
    id: testCase
    name: "GraphSurfaceControls"
    width: 800
    height: 600
    visible: true
    when: windowShown
    property var tooltipCopyBridge: null
    property var uiIcons: uiIconsStub
    property var themeBridge: themeBridgeStub
    property var themePalette: ({
        "accent": "#1d8ce0",
        "border": "#3a3d45",
        "input_border": "#4a4f5a",
        "inspector_danger_border": "#d94f4f",
        "inspector_danger_fg": "#ffb0b0",
        "panel_bg": "#20242d",
        "panel_title_fg": "#f1f4fb"
    })

    QtObject {
        id: uiIconsStub

        function has(name) {
            return false
        }

        function sourceSized(name, size, color) {
            return ""
        }

        function label(name) {
            return String(name || "")
        }
    }

    QtObject {
        id: themeBridgeStub
        property var palette: testCase.themePalette
    }

    Item {
        id: stage
        anchors.fill: parent
        visible: true
    }

    Component {
        id: probeComponent

        Item {
            id: root
            width: 240
            height: 500

            property alias probeHost: hostItem
            property alias probeRegion: region
            property alias probeButton: button
            property alias probeField: field
            property alias probeCombo: combo
            property alias probeSearchableCombo: searchableCombo
            property alias probeCheck: check
            property alias probeSlider: slider
            property alias probeInterval: intervalSlider
            property alias probeInlineHost: inlineHost
            property alias probeInlineLayer: inlineLayer
            property alias inlineProperties: inlineHost.inlineProperties
            property int regionStarts: 0
            property int buttonStarts: 0
            property int fieldStarts: 0
            property int comboStarts: 0
            property int searchableStarts: 0
            property var searchableCommits: []
            property int checkStarts: 0
            property int sliderStarts: 0
            property int intervalStarts: 0
            property var sliderCommits: []
            property var intervalCommits: []

            Item {
                id: hostItem
                x: 10
                y: 8
                width: 200
                height: 174
                property int graphFontSize: 15
                property int graphFontWeight: Font.DemiBold
                property var graphSharedTypography: ({
                    "inlinePropertyPixelSize": graphFontSize,
                    "inlinePropertyFontWeight": graphFontWeight,
                    "badgePixelSize": Math.max(9, graphFontSize - 1),
                    "badgeFontWeight": Font.Bold
                })
                property color inlineInputBackgroundColor: "#223344"
                property color inlineInputBorderColor: "#556677"
                property color inlineInputTextColor: "#ddeeff"
                property color selectedOutlineColor: "#66ccff"
                property color headerTextColor: "#f7f7f0"
                property color surfaceColor: "#111111"
                property int nodeTextRenderType: Text.QtRendering

                Item {
                    x: 12
                    y: 18
                    width: 180
                    height: 80

                    Rectangle {
                        id: targetRect
                        x: 5
                        y: 7
                        width: 40
                        height: 18
                        color: "transparent"
                    }

                    Controls.GraphSurfaceInteractiveRegion {
                        id: region
                        host: hostItem
                        targetItem: targetRect
                        onControlStarted: root.regionStarts += 1
                    }

                    Controls.GraphSurfaceButton {
                        id: button
                        host: hostItem
                        x: 50
                        y: 10
                        width: 56
                        height: 24
                        text: "Run"
                        onControlStarted: root.buttonStarts += 1
                    }

                    Controls.GraphSurfaceTextField {
                        id: field
                        host: hostItem
                        x: 10
                        y: 38
                        width: 110
                        height: 24
                        text: "hello"
                        onControlStarted: root.fieldStarts += 1
                    }

                    Controls.GraphSurfaceComboBox {
                        id: combo
                        host: hostItem
                        x: 128
                        y: 38
                        width: 60
                        height: 24
                        model: ["one", "two"]
                        currentIndex: 1
                        onControlStarted: root.comboStarts += 1
                    }

                    Controls.GraphSurfaceSearchableComboBox {
                        id: searchableCombo
                        host: hostItem
                        x: 10
                        y: 66
                        width: 178
                        height: 24
                        model: ["Alpha", "Beta", "Gamma"]
                        selectedValue: "Beta"
                        placeholderText: "Pick item"
                        onControlStarted: root.searchableStarts += 1
                        onValueActivated: function(value) {
                            root.searchableCommits = root.searchableCommits.concat([value])
                        }
                    }

                    Controls.GraphSurfaceCheckBox {
                        id: check
                        host: hostItem
                        x: 128
                        y: 10
                        width: 44
                        height: 20
                        checked: true
                        text: ""
                        onControlStarted: root.checkStarts += 1
                    }

                    Controls.GraphSurfaceSlider {
                        id: slider
                        host: hostItem
                        x: 10
                        y: 92
                        width: 178
                        height: 40
                        from: 0
                        to: 10
                        stepSize: 1
                        value: 3
                        valueType: "int"
                        showRangeCaptions: true
                        onControlStarted: root.sliderStarts += 1
                        onCommitRequested: function(value) {
                            root.sliderCommits = root.sliderCommits.concat([Number(value)])
                        }
                    }

                    Controls.GraphSurfaceIntervalSlider {
                        id: intervalSlider
                        host: hostItem
                        x: 10
                        y: 132
                        width: 178
                        height: 40
                        from: 0
                        to: 10
                        stepSize: 1
                        semanticStart: 2
                        semanticEnd: 8
                        onControlStarted: root.intervalStarts += 1
                        onCommitRequested: function(value) {
                            root.intervalCommits = root.intervalCommits.concat([value])
                        }
                    }
                }
            }

            Item {
                id: inlineHost
                y: 190
                width: 220
                height: 286
                property var inlineProperties: []
                property var nodeData: ({"node_id": "probe_node"})
                property var executionFacts: ({"propertyPresentationLookup": ({})})
                property int graphFontSize: 10
                property var graphSharedTypography: ({
                    "inlinePropertyPixelSize": graphFontSize,
                    "inlinePropertyFontWeight": Font.Normal,
                    "badgePixelSize": Math.max(9, graphFontSize - 1),
                    "badgeFontWeight": Font.Bold
                })
                property int inlineBodyHeight: 286
                property color inlineRowColor: "#24262c"
                property color inlineRowBorderColor: "#4a4f5a"
                property color inlineLabelColor: "#d0d5de"
                property color inlineDrivenTextColor: "#bdc5d3"
                property color inlineInputBackgroundColor: "#223344"
                property color inlineInputBorderColor: "#556677"
                property color inlineInputTextColor: "#ddeeff"
                property color selectedOutlineColor: "#66ccff"
                property color headerTextColor: "#f7f7f0"
                property color surfaceColor: "#111111"
                property int nodeTextRenderType: Text.QtRendering
                property int _inlineRowSpacing: 4
                property int _inlineRowHeight: Math.max(24, graphFontSize + 16)
                property int _inlineStackedRowHeight: _inlineRowHeight * 2 + _inlineRowSpacing
                property int _inlineSliderRowHeight: _inlineRowHeight * 2
                    + graphFontSize + _inlineRowSpacing
                property real _inlineLabelAnchorOffset: _inlineRowHeight * 0.5
                property int _inlineTextareaRowHeight: Math.max(96, _inlineRowHeight * 4)
                property var nodeHelpTooltipPolicyBridge: null
                property string nodeHelpTooltipPlacement: "above"
                property real nodeHelpTooltipAnchorScale: 1.0
                property var surfaceMetrics: ({
                    "body_left_margin": 8,
                    "body_right_margin": 8,
                    "body_top": 30
                })

                signal surfaceControlInteractionStarted(string nodeId)
                signal inlinePropertyCommitted(string nodeId, string key, var value)

                function inlineEditorText(modelData) {
                    return String(modelData.value === undefined || modelData.value === null ? "" : modelData.value)
                }

                Graph.GraphInlinePropertiesLayer {
                    id: inlineLayer
                    anchors.fill: parent
                    host: inlineHost
                }
            }
        }
    }

    Component {
        id: fitProbeComponent

        Item {
            id: fitRoot
            width: 220
            height: 160
            property alias fitTextField: fitTextField
            property alias fitComboBox: fitComboBox
            property alias fitPathEditor: fitPathEditor
            property alias fitColorEditor: fitColorEditor
            property var graphSharedTypography: ({
                "inlinePropertyPixelSize": 15,
                "inlinePropertyFontWeight": Font.Normal
            })
            property color inlineInputBackgroundColor: "#223344"
            property color inlineInputBorderColor: "#556677"
            property color inlineInputTextColor: "#ddeeff"
            property color selectedOutlineColor: "#66ccff"
            property color headerTextColor: "#f7f7f0"
            property color surfaceColor: "#111111"
            property int nodeTextRenderType: Text.QtRendering

            Controls.GraphSurfaceTextField {
                id: fitTextField
                host: fitRoot
                width: 100
                text: "A very long text value that cannot fit in the current field"
            }

            Controls.GraphSurfaceComboBox {
                id: fitComboBox
                host: fitRoot
                y: 32
                width: 100
                model: ["A very long currently selected enum value"]
                currentIndex: 0
            }

            Controls.GraphSurfacePathEditor {
                id: fitPathEditor
                host: fitRoot
                y: 64
                width: 100
                committedText: "C:/short/folder/" + "deep_directory/".repeat(90) + "result.rst"
                shortenDisplayPathWhenInactive: true
            }

            Controls.GraphSurfaceColorEditor {
                id: fitColorEditor
                host: fitRoot
                y: 96
                width: 100
                committedText: "#AABBCCDD"
            }
        }
    }

    Component {
        id: floatingToolbarProbeComponent

        Item {
            id: floatingRoot
            width: 640
            height: 480
            objectName: "floatingToolbarProbeRoot"

            Item {
                id: floatingViewBridge
                objectName: "floatingToolbarProbeViewBridge"
                property real zoom_value: 1.0
                property real center_x: 0.0
                property real center_y: 0.0
            }

            Item {
                id: floatingHost
                objectName: "floatingToolbarProbeHost"
                x: 200
                y: 180
                width: 200
                height: 80

                property var nodeData: ({"node_id": "probe_node"})
                property var surfaceMetrics: ({
                    "floating_toolbar": {
                        "toolbar_height": 32,
                        "button_size": 24,
                        "button_gap": 4,
                        "internal_padding": 4,
                        "gap_from_node": 6,
                        "safety_margin": 8,
                        "hysteresis": 8,
                        "animation_duration_ms": 0
                    }
                })
                property var availableActions: ([
                    {"id": "frame_node", "label": "Zoom to node", "icon": "zoom-fit", "kind": "common", "enabled": true, "primary": false},
                    {"id": "rename", "label": "Rename", "icon": "edit", "kind": "common", "enabled": true, "primary": false},
                    {"id": "duplicate", "label": "Duplicate", "icon": "duplicate", "kind": "common", "enabled": true, "primary": false},
                    {"id": "delete", "label": "Delete", "icon": "delete", "kind": "common", "enabled": true, "primary": false, "destructive": true}
                ])
                property bool toolbarActive: true
                property bool floatingToolbarFlipped: false
                property real floatingToolbarZoom: 1.0
                property bool showNodeTooltip: false
                property bool toolbarPointerInside: false
                property color nodeThemeColor: "#5da9ff"
                property color surfaceColor: "#1b1d22"
                property color outlineColor: "#3a3d45"
                property real worldOffset: 0
                property bool _liveGeometryActive: false
                property real _liveX: 0
                property real _liveY: 0
                property color inlineInputBackgroundColor: "#22242a"
                property color inlineInputBorderColor: "#4a4f5a"
                property color headerTextColor: "#eef3ff"
                property var graphSharedTypography: ({"inlinePropertyPixelSize": 12})
                property int nodeTextRenderType: Text.QtRendering
                property var canvasItem: null
                property bool rebuildViewerActionsOnControlStart: false
                property bool surfaceActionHandledResult: true

                signal surfaceControlInteractionStarted(string nodeId)
                signal nodeActionRequested(string nodeId, string actionId, var payload)
                signal surfaceActionRequested(string actionId)

                onSurfaceControlInteractionStarted: {
                    if (floatingHost.rebuildViewerActionsOnControlStart)
                        floatingHost._setViewerFullscreenActions(false)
                }

                function dispatchNodeAction(actionId, payload) {
                    floatingHost.nodeActionRequested(
                        String(floatingHost.nodeData && floatingHost.nodeData.node_id || ""),
                        String(actionId || ""),
                        payload || null
                    )
                }

                function dispatchSurfaceAction(actionId) {
                    if (String(actionId || "") === "fullscreen" && floatingHost.rebuildViewerActionsOnControlStart)
                        floatingHost.surfaceControlInteractionStarted(String(floatingHost.nodeData.node_id || ""))
                    floatingHost.surfaceActionRequested(String(actionId || ""))
                    return floatingHost.surfaceActionHandledResult
                }

                function useWebStyleActionProbe() {
                    floatingHost.availableActions = [
                        {"id": "web_page_back", "label": "Back", "icon": "browser-back", "kind": "web_page", "enabled": false, "primary": false},
                        {"id": "web_page_forward", "label": "Forward", "icon": "browser-forward", "kind": "web_page", "enabled": false, "primary": false},
                        {"id": "web_page_reload_stop", "label": "Reload", "icon": "browser-reload", "kind": "web_page", "enabled": true, "primary": false},
                        {"id": "web_page_edit_address", "label": "Address", "icon": "search", "kind": "web_page", "enabled": true, "primary": false},
                        {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "web_page", "enabled": true, "primary": false},
                        {"id": "web_page_detach", "label": "Detach", "icon": "browser-detach", "kind": "web_page", "enabled": true, "primary": false},
                        {"id": "frame_node", "label": "Zoom to node", "icon": "zoom-fit", "kind": "common", "enabled": true, "primary": false},
                        {"id": "rename_node", "label": "Rename", "icon": "edit", "kind": "common", "enabled": true, "primary": false},
                        {"id": "duplicate_node", "label": "Duplicate", "icon": "duplicate", "kind": "common", "enabled": true, "primary": false},
                        {"id": "remove_node", "label": "Delete", "icon": "delete", "kind": "common", "enabled": true, "primary": false, "destructive": true}
                    ]
                }

                function useToggleActionProbe() {
                    floatingHost.availableActions = [
                        {"id": "loop", "label": "Disable loop", "icon": "keep-live", "kind": "media", "enabled": true, "primary": true, "checked": true},
                        {"id": "fit", "label": "Fill video", "icon": "frame", "kind": "media", "enabled": true, "primary": false, "checked": false},
                        {"id": "source", "label": "Source", "icon": "search", "kind": "media", "enabled": true, "primary": true}
                    ]
                }

                function useSurfaceActionProbe() {
                    floatingHost.availableActions = [
                        {"id": "text_toggle_bold", "label": "Bold", "icon": "format-bold", "kind": "surface", "enabled": true, "checked": true},
                        {"id": "text_copy_style", "label": "Copy text style", "icon": "copy-text-style", "kind": "surface", "enabled": true},
                        {"id": "text_paste_style", "label": "Paste text style", "icon": "paste-text-style", "kind": "surface", "enabled": true},
                        {"id": "rename_node", "label": "Rename", "icon": "edit", "kind": "common", "enabled": true}
                    ]
                }

                function _setViewerFullscreenActions(cameraEnabled) {
                    floatingHost.availableActions = [
                        {"id": "camera", "label": "Camera", "icon": "focus", "kind": "viewer", "enabled": Boolean(cameraEnabled)},
                        {"id": "fullscreen", "label": "Fullscreen", "icon": "fullscreen", "kind": "surface", "enabled": true}
                    ]
                }

                function useViewerFullscreenActionProbe() {
                    floatingHost._setViewerFullscreenActions(true)
                }

                function useGroupedSurfaceActionProbe() {
                    floatingHost.availableActions = [
                        {
                            "id": "text_style_group",
                            "label": "Text style",
                            "icon": "format-bold-italic",
                            "kind": "surface",
                            "enabled": true,
                            "checked": true,
                            "popoverActions": [
                                {"id": "text_toggle_bold", "label": "Bold", "icon": "format-bold", "kind": "surface", "enabled": true, "checked": true},
                                {"id": "text_toggle_underline", "label": "Underline", "icon": "format-underline", "kind": "surface", "enabled": true}
                            ]
                        },
                        {"id": "rename_node", "label": "Rename", "icon": "edit", "kind": "common", "enabled": true}
                    ]
                }

                function useRunMenuActionProbe() {
                    floatingHost.availableActions = [Presentation.findAction(
                        Presentation.nodeCommonActions({"runnable": true}), "run_selected"
                    )]
                }

                Common.ManagedToolTip {
                    objectName: "floatingToolbarProbeNodeToolTip"
                    active: floatingHost.showNodeTooltip
                    text: "Node help"
                    delay: 0
                    screenStablePositioning: true
                    screenStablePlacement: floatingHost.floatingToolbarFlipped ? "above" : "below"
                    anchorScale: floatingHost.floatingToolbarZoom
                    screenGap: 8
                }
            }

            GraphOverlay.GraphNodeFloatingToolbar {
                id: floatingToolbar
                objectName: "floatingToolbarProbeToolbar"
                host: floatingHost
                viewBridge: floatingViewBridge
                visibleSceneRectPayload: ({"x": 0, "y": 0, "width": 640, "height": 480})
            }

            function previewFontSize(value) {
                return floatingToolbar._previewFontSizeValue(value)
            }

            function commitFontSize(value) {
                return floatingToolbar._commitFontSizeValue(value)
            }

            function closeActionPopover(flushDraft) {
                floatingToolbar._closeActionPopover(flushDraft)
            }
        }
    }

    Component {
        id: selectionEnvelopeProbeComponent

        Item {
            id: selectionRoot
            width: 640
            height: 480
            objectName: "selectionEnvelopeProbeRoot"

            Item {
                id: selectionViewBridge
                objectName: "selectionEnvelopeProbeViewBridge"
                property real zoom_value: 1.0
                property real center_x: 320.0
                property real center_y: 240.0
            }

            Item {
                id: selectionCanvasStateBridge
                objectName: "selectionEnvelopeProbeCanvasStateBridge"
                property string graphics_selection_toolbar_mode: "minimal_ghost_menu"
                property string graphics_selection_toolbar_minimal_menu_trigger: "click_affordance"
            }

            Item {
                id: selectionSceneBridge
                objectName: "selectionEnvelopeProbeSceneBridge"
                property var selected_node_lookup: ({"node-a": true, "node-b": true, "node-c": true})
                property bool selected_node_lookup_authoritative: true
            }

            Item {
                id: selectionCanvas
                objectName: "selectionEnvelopeProbeCanvasItem"
                width: 640
                height: 480
                property real worldSize: 1000
                property real worldOffset: 0
                property var canvasStateBridgeRef: selectionCanvasStateBridge
                property var liveNodeGeometry: ({})
                property var liveDragNodeLookup: ({})
                property real liveDragDx: 0
                property real liveDragDy: 0
                property var selectedEdgeIds: []
                property var edgePayload: ([
                    {"edge_id": "edge-ab", "source_node_id": "node-a", "target_node_id": "node-b"},
                    {"edge_id": "edge-bx", "source_node_id": "node-b", "target_node_id": "node-x"}
                ])
                property int openedSelectionMenus: 0
                property real lastMenuX: -1
                property real lastMenuY: -1

                function selectedNodeIds() {
                    var selected = []
                    var lookup = selectionSceneBridge.selected_node_lookup || {}
                    for (var nodeId in lookup) {
                        if (Object.prototype.hasOwnProperty.call(lookup, nodeId) && lookup[nodeId])
                            selected.push(String(nodeId))
                    }
                    return selected
                }

                function _sceneNodePayload(nodeId) {
                    var payloads = {
                        "node-a": {"node_id": "node-a", "x": 120, "y": 100, "width": 100, "height": 60},
                        "node-b": {"node_id": "node-b", "x": 300, "y": 140, "width": 120, "height": 70},
                        "node-c": {"node_id": "node-c", "x": 210, "y": 260, "width": 90, "height": 70}
                    }
                    return payloads[String(nodeId || "")] || null
                }

                function _sceneEdgePayload(edgeId) {
                    for (var index = 0; index < edgePayload.length; ++index) {
                        if (String(edgePayload[index].edge_id || "") === String(edgeId || ""))
                            return edgePayload[index]
                    }
                    return null
                }

                function _openSelectionContext(x, y) {
                    openedSelectionMenus += 1
                    lastMenuX = Number(x)
                    lastMenuY = Number(y)
                }

                function _openSelectionContextAtScene(sceneX, sceneY) {
                    _openSelectionContext(sceneX, sceneY)
                }

                function forceActiveFocus() {}
            }

            Item {
                id: selectionActionRouter
                objectName: "selectionEnvelopeProbeActionRouter"
                property var triggeredActions: []

                function handleSelectionContextAction(actionId) {
                    triggeredActions = triggeredActions.concat([String(actionId || "")])
                    return true
                }
            }

            Item {
                id: selectionHostA
                objectName: "selectionEnvelopeProbeHostA"
                x: 120
                y: 100
                width: 100
                height: 60
                property real dragTranslateX: 0
                property real dragTranslateY: 0
            }

            Item {
                id: selectionHostB
                objectName: "selectionEnvelopeProbeHostB"
                x: 300
                y: 140
                width: 120
                height: 70
                property real dragTranslateX: 0
                property real dragTranslateY: 0
            }

            Item {
                id: selectionHostC
                objectName: "selectionEnvelopeProbeHostC"
                x: 210
                y: 260
                width: 90
                height: 70
                property real dragTranslateX: 0
                property real dragTranslateY: 0
            }

            function hostForNodeId(nodeId) {
                if (nodeId === "node-a")
                    return selectionHostA
                if (nodeId === "node-b")
                    return selectionHostB
                if (nodeId === "node-c")
                    return selectionHostC
                return null
            }

            GraphOverlay.GraphSelectionEnvelopeOverlay {
                id: selectionOverlay
                objectName: "selectionEnvelopeProbeOverlay"
                canvasItem: selectionCanvas
                viewBridge: selectionViewBridge
                sceneStateBridge: selectionSceneBridge
                canvasActionRouter: selectionActionRouter
                visibleSceneRectPayload: ({"x": 0, "y": 0, "width": 640, "height": 480})
                hostResolver: selectionRoot.hostForNodeId
                themePalette: ({
                    "accent": "#1d8ce0",
                    "panel_bg": "#20242d",
                    "panel_title_fg": "#f1f4fb",
                    "border": "#4b5568"
                })
            }
        }
    }

    function createProbe(properties) {
        return createTemporaryObject(probeComponent, stage, properties || {})
    }

    function test_inline_column_selection_commits_canonical_position() {
        var root = createProbe();
        root.inlineProperties = [{"key": "x_column", "label": "X column", "type": "json", "value": 0,
            "display_value": 0, "display_value_available": true, "inline_editor": "enum", "searchable": true,
            "exact_selectors": true, "enum_values": ["Column 1", "Column 2"], "enum_codes": [0, 1], "editor_enabled": true}];
        var commits = [];
        root.probeInlineHost.inlinePropertyCommitted.connect(function(node, key, value) { commits.push(value); });
        wait(0);
        var selector = findChild(root.probeInlineLayer, "graphNodeInlineSearchableEnumEditor");
        verify(selector !== null);
        compare(selector.selectedValue, 0);
        mouseClick(selector, 20, selector.height / 2);
        selector.editText = "Column 2";
        keyClick(Qt.Key_Down);
        wait(0);
        keyClick(Qt.Key_Return);
        compare(commits[commits.length - 1], 1);
    }

    function near(actual, expected) {
        return Math.abs(Number(actual) - Number(expected)) < 0.5
    }

    function colorName(value) {
        return String(value).toLowerCase()
    }

    function coreInlineProperties() {
        return [
            {
                "key": "enabled",
                "label": "Enabled",
                "inline_editor": "toggle",
                "value": true,
                "overridden_by_input": false,
                "input_port_label": "enabled"
            },
            {
                "key": "mode",
                "label": "Mode",
                "inline_editor": "enum",
                "value": "two",
                "enum_values": ["one", "two", "three"],
                "overridden_by_input": false,
                "input_port_label": "mode"
            },
            {
                "key": "message",
                "label": "Message",
                "inline_editor": "text",
                "value": "hello",
                "overridden_by_input": false,
                "input_port_label": "message"
            },
            {
                "key": "count",
                "label": "Count",
                "inline_editor": "number",
                "value": 7,
                "overridden_by_input": false,
                "input_port_label": "count"
            }
        ]
    }

    function test_interactive_region_maps_host_space_rect_and_emits_control_start() {
        var root = createProbe()
        verify(root !== null)
        root.probeRegion.beginControl()
        compare(root.probeRegion.embeddedInteractiveRects.length, 1)
        var rect = root.probeRegion.embeddedInteractiveRects[0]
        verify(near(rect.x, 17))
        verify(near(rect.y, 25))
        verify(near(rect.width, 40))
        verify(near(rect.height, 18))
        compare(root.regionStarts, 1)
    }

    function test_button_and_text_field_publish_rects_and_host_styling() {
        var root = createProbe()
        verify(root !== null)
        var button = root.probeButton
        var field = root.probeField

        compare(button.embeddedInteractiveRects.length, 1)
        verify(near(button.embeddedInteractiveRects[0].x, 62))
        verify(near(button.embeddedInteractiveRects[0].y, 28))
        compare(colorName(button.resolvedForegroundColor), "#f7f7f0")
        compare(button.font.pixelSize, 15)

        compare(field.embeddedInteractiveRects.length, 1)
        verify(near(field.embeddedInteractiveRects[0].x, 22))
        verify(near(field.embeddedInteractiveRects[0].y, 56))
        compare(colorName(field.resolvedBackgroundColor), "#223344")
        compare(colorName(field.resolvedBorderColor), "#556677")
        compare(field.font.pixelSize, 15)
        compare(field.font.weight, Font.DemiBold)

        mouseClick(button, button.width * 0.5, button.height * 0.5)
        field.forceActiveFocus()
        tryCompare(root, "buttonStarts", 1)
        tryCompare(root, "fieldStarts", 1)
        compare(colorName(field.resolvedBorderColor), "#66ccff")

        root.probeHost.graphFontSize = 17
        tryCompare(button.font, "pixelSize", 17)
        tryCompare(field.font, "pixelSize", 17)
    }

    function test_slider_commits_on_release_only_and_publishes_contracts() {
        var root = createProbe()
        verify(root !== null)
        var slider = root.probeSlider
        compare(slider.embeddedInteractiveRects.length, 1)
        verify(Math.abs(slider.value - 3) < 0.001)
        compare(slider.minimumCaptionText, "0")
        compare(slider.currentCaptionText, "3")
        compare(slider.maximumCaptionText, "10")
        var focusIndicator = findChild(slider, "graphSurfaceSliderFocusIndicator")
        verify(focusIndicator !== null)
        verify(!focusIndicator.visible)

        mousePress(slider, slider.width * 0.3, slider.availableHeight * 0.5)
        tryCompare(root, "sliderStarts", 1)
        compare(root.sliderCommits.length, 0)

        mouseMove(slider, slider.width * 0.9, slider.availableHeight * 0.5)
        compare(root.sliderCommits.length, 0)
        verify(Number(slider.currentCaptionText) > 3)

        mouseRelease(slider, slider.width * 0.9, slider.availableHeight * 0.5)
        tryCompare(root.sliderCommits, "length", 1)
        verify(root.sliderCommits[0] > 3)

        slider.forceActiveFocus()
        tryCompare(focusIndicator, "visible", true)
        compare(colorName(focusIndicator.border.color), "#66ccff")
        keyClick(Qt.Key_Right)
        tryCompare(root.sliderCommits, "length", 2)

        slider.valueType = "float"
        slider.stepSize = 0.001
        slider.value = 1.2
        compare(slider.currentCaptionText, "1.200")
        slider.stepSize = 0
        compare(slider.currentCaptionText, "1.200")
        slider.enabled = false
        tryCompare(focusIndicator, "visible", false)
    }

    function test_interval_slider_preserves_semantic_direction_and_separates_equal_handles() {
        var root = createProbe()
        verify(root !== null)
        var interval = root.probeInterval
        compare(interval.embeddedInteractiveRects.length, 1)
        tryCompare(interval.first, "value", 2)
        tryCompare(interval.second, "value", 8)
        compare(interval.leftCaptionText, "2")
        compare(interval.rightCaptionText, "8")

        var initialFirstHandle = findChild(interval, "graphSurfaceIntervalFirstHandle")
        verify(initialFirstHandle !== null)
        mousePress(
            interval,
            initialFirstHandle.x + initialFirstHandle.width * 0.5,
            initialFirstHandle.y + initialFirstHandle.height * 0.5
        )
        tryCompare(root, "intervalStarts", 1)
        compare(root.intervalCommits.length, 0)
        mouseMove(interval, interval.width * 0.4, interval.availableHeight * 0.5)
        compare(root.intervalCommits.length, 0)
        var draggedFirstValue = Number(interval.first.value)
        var draggedSecondValue = Number(interval.second.value)
        verify(draggedFirstValue > 2)
        compare(Number(interval.leftCaptionText), draggedFirstValue)
        compare(Number(interval.rightCaptionText), draggedSecondValue)

        interval.semanticStart = 1
        interval.semanticEnd = 9
        wait(1)
        compare(Number(interval.first.value), draggedFirstValue)
        compare(Number(interval.second.value), draggedSecondValue)
        compare(Number(interval.leftCaptionText), draggedFirstValue)
        compare(Number(interval.rightCaptionText), draggedSecondValue)

        mouseRelease(interval, interval.width * 0.4, interval.availableHeight * 0.5)
        tryCompare(root.intervalCommits, "length", 1)
        tryCompare(interval.first, "value", 1)
        tryCompare(interval.second, "value", 9)

        root.intervalCommits = []
        interval.forceActiveFocus()
        var focusIndicator = findChild(interval, "graphSurfaceIntervalFocusIndicator")
        verify(focusIndicator !== null)
        tryCompare(focusIndicator, "visible", true)
        compare(colorName(focusIndicator.border.color), "#66ccff")
        keyClick(Qt.Key_Right)
        tryCompare(root.intervalCommits, "length", 1)

        root.intervalCommits = []
        interval.intervalDirection = "decreasing"
        interval.first.value = 3
        interval.second.value = 7
        interval._commitCurrentValues()
        tryCompare(root.intervalCommits, "length", 1)
        compare(Number(root.intervalCommits[0].start), 7)
        compare(Number(root.intervalCommits[0].end), 3)

        root.probeHost.graphFontSize = 24
        interval.from = 0
        interval.to = 1000000
        interval.stepSize = 0.000001
        interval.semanticStart = 123456.789
        interval.semanticEnd = 123456.789
        tryCompare(interval.first, "value", 123456.789)
        tryCompare(interval.second, "value", 123456.789)
        tryCompare(interval, "captionPixelSize", 24)
        verify(interval.equalPhysicalValues)
        var firstHandle = findChild(interval, "graphSurfaceIntervalFirstHandle")
        var secondHandle = findChild(interval, "graphSurfaceIntervalSecondHandle")
        var leftCaption = findChild(interval, "graphSurfaceIntervalLeftCaption")
        var rightCaption = findChild(interval, "graphSurfaceIntervalRightCaption")
        verify(firstHandle !== null)
        verify(secondHandle !== null)
        verify(leftCaption !== null)
        verify(rightCaption !== null)
        verify(Number(secondHandle.x) > Number(firstHandle.x))
        verify(Number(leftCaption.width) <= Number(interval.captionHalfWidth) + 0.5)
        verify(Number(rightCaption.width) <= Number(interval.captionHalfWidth) + 0.5)
        verify(
            Number(leftCaption.x) + Number(leftCaption.width)
                <= Number(interval.width) * 0.5 - Number(interval.captionRegionGap) * 0.5 + 0.5
        )
        verify(
            Number(rightCaption.x)
                >= Number(interval.width) * 0.5 + Number(interval.captionRegionGap) * 0.5 - 0.5
        )
        verify(
            Number(rightCaption.x) - Number(leftCaption.x) - Number(leftCaption.width)
                >= Number(interval.captionRegionGap) - 0.5
        )
        interval.enabled = false
        tryCompare(focusIndicator, "visible", false)
    }

    function test_combo_box_and_check_box_emit_control_start_and_keep_surface_contracts() {
        var root = createProbe()
        verify(root !== null)
        var combo = root.probeCombo
        var check = root.probeCheck

        compare(colorName(combo.resolvedTextColor), "#ddeeff")
        compare(colorName(combo.resolvedBackgroundColor), "#223344")
        compare(colorName(check.resolvedIndicatorBorderColor), "#66ccff")
        compare(combo.font.pixelSize, 15)
        compare(combo.font.weight, Font.DemiBold)
        compare(check.font.pixelSize, 15)
        compare(check.switchTrackWidth, 28)
        compare(check.switchTrackHeight, 14)
        compare(combo.embeddedInteractiveRects.length, 1)
        compare(check.embeddedInteractiveRects.length, 1)
        verify(combo.popupRowHeight >= 24 && combo.popupRowHeight <= 30)
        verify(near(combo.popupWidth, combo.width))
        verify(!combo.hoverVisualActive)
        verify(!combo.pressedVisualActive)
        verify(!combo.activeVisualActive)

        mouseClick(combo, combo.width * 0.5, combo.height * 0.5)
        mouseClick(check, check.width * 0.5, check.height * 0.5)
        tryCompare(root, "comboStarts", 1)
        tryCompare(root, "checkStarts", 1)

        root.probeHost.graphFontSize = 17
        tryCompare(combo.font, "pixelSize", 17)
        tryCompare(check.font, "pixelSize", 17)
    }

    function test_searchable_combo_filters_options_and_publishes_surface_rect() {
        var root = createProbe()
        verify(root !== null)
        var searchable = root.probeSearchableCombo

        tryCompare(searchable, "editText", "Beta")
        compare(colorName(searchable.resolvedTextColor), "#ddeeff")
        compare(colorName(searchable.resolvedBackgroundColor), "#223344")
        compare(searchable.embeddedInteractiveRects.length, 1)
        verify(searchable.popupRowHeight >= 24 && searchable.popupRowHeight <= 30)
        verify(near(searchable.popupWidth, searchable.width))
        verify(!searchable.hoverVisualActive)
        verify(!searchable.pressedVisualActive)

        searchable.editText = "ta"
        tryCompare(searchable.filteredOptions, "length", 1)
        compare(String(searchable.filteredOptions[0].value), "Beta")

        searchable.model = ["Scalpel", "Alpine", "Alp", "Alpha"]
        searchable.editText = "alp"
        tryCompare(searchable.filteredOptions, "length", 4)
        compare(String(searchable.filteredOptions[0].value), "Alp")
        compare(String(searchable.filteredOptions[1].value), "Alpine")
        compare(String(searchable.filteredOptions[2].value), "Alpha")
        compare(String(searchable.filteredOptions[3].value), "Scalpel")

        mouseClick(searchable, searchable.width * 0.5, searchable.height * 0.5)
        tryCompare(root, "searchableStarts", 1)
        searchable.editText = "alp"
        keyClick(Qt.Key_Return)
        tryCompare(root.searchableCommits, "length", 1)
        compare(String(root.searchableCommits[0]), "Alp")
        searchable.editText = "no declared option"
        keyClick(Qt.Key_Return)
        compare(root.searchableCommits.length, 1)
        root.probeHost.graphFontSize = 17
        tryCompare(searchable, "inlineFontPixelSize", 17)
    }

    function test_dropdown_controls_publish_hover_and_press_visual_state() {
        var root = createProbe()
        verify(root !== null)
        var combo = root.probeCombo
        var searchable = root.probeSearchableCombo

        combo.externalHover = true
        tryCompare(combo, "hoverVisualActive", true)
        verify(combo.resolvedBorderWidth > 1)
        combo.externalPressed = true
        tryCompare(combo, "pressedVisualActive", true)
        combo.externalPressed = false

        searchable.externalHover = true
        tryCompare(searchable, "hoverVisualActive", true)
        verify(searchable.resolvedBorderWidth > 1)
        searchable.externalPressed = true
        tryCompare(searchable, "pressedVisualActive", true)
        searchable.externalPressed = false
    }

    function test_inline_properties_layer_publishes_control_scoped_rects_for_core_editors() {
        var root = createProbe({"inlineProperties": coreInlineProperties()})
        verify(root !== null)
        var layer = root.probeInlineLayer
        tryVerify(function() { return layer.embeddedInteractiveRects.length === 4 })

        var baseHeight = Number(root.probeInlineHost._inlineRowHeight)
        var stackedHeight = Number(root.probeInlineHost._inlineStackedRowHeight)
        var spacing = Number(root.probeInlineHost._inlineRowSpacing)
        var bodyTop = Number(root.probeInlineHost.surfaceMetrics.body_top)
        var expectedY = [
            bodyTop + (baseHeight - Number(layer.embeddedInteractiveRects[0].height)) * 0.5,
            bodyTop + baseHeight + spacing + baseHeight,
            bodyTop + baseHeight + spacing + stackedHeight + spacing + baseHeight,
            bodyTop + baseHeight + spacing + stackedHeight + spacing
                + stackedHeight + spacing + baseHeight
        ]
        for (var index = 0; index < layer.embeddedInteractiveRects.length; ++index) {
            var rect = layer.embeddedInteractiveRects[index]
            verify(Number(rect.x) >= 14)
            if (index === 0)
                verify(Number(rect.width) < 40)
            else
                verify(Number(rect.width) > 180)
            verify(near(Number(rect.y), expectedY[index]))
        }
    }

    function test_inline_layer_uses_dynamic_upstream_display_and_condition_state() {
        var root = createProbe({
            "inlineProperties": [{
                "key": "message",
                "label": "Message",
                "type": "str",
                "inline_editor": "text",
                "value": "saved local",
                "display_value": "saved local",
                "display_value_available": true,
                "editor_enabled": true,
                "overridden_by_input": false
            }]
        })
        verify(root !== null)
        var host = root.probeInlineHost
        var layer = root.probeInlineLayer
        tryVerify(function() { return layer.embeddedInteractiveRects.length === 1 })
        var editor = findChild(layer, "graphNodeInlineValueEditor")
        verify(editor !== null)
        compare(editor.text, "saved local")

        host.executionFacts = {
            "propertyPresentationLookup": {
                "probe_node": {
                    "message": {
                        "key": "message",
                        "label": "Message",
                        "type": "str",
                        "inline_editor": "text",
                        "value": "saved local",
                        "display_value": "upstream value",
                        "display_value_available": true,
                        "overridden_by_input": true,
                        "condition_enabled": true,
                        "editor_enabled": false,
                        "editor_disabled_reason": "Value supplied by connected input."
                    }
                }
            }
        }
        tryCompare(editor, "text", "upstream value")
        compare(editor.enabled, false)
        tryVerify(function() { return layer.embeddedInteractiveRects.length === 0 })

        host.executionFacts = {
            "propertyPresentationLookup": {
                "probe_node": {
                    "message": {
                        "key": "message",
                        "label": "Message",
                        "type": "str",
                        "inline_editor": "text",
                        "value": "saved local",
                        "display_value_available": false,
                        "overridden_by_input": true,
                        "condition_enabled": true,
                        "editor_enabled": false,
                        "editor_disabled_reason": "Value supplied by connected input."
                    }
                }
            }
        }
        tryCompare(editor, "text", "\u2014")
    }

    function test_inline_stacked_controls_follow_enlarged_typography_without_clipping() {
        var root = createProbe({
            "inlineProperties": [
                {
                    "key": "message",
                    "label": "Message",
                    "type": "str",
                    "inline_editor": "text",
                    "value": "saved local",
                    "editor_enabled": true
                },
                {
                    "key": "count",
                    "label": "Count",
                    "type": "int",
                    "inline_editor": "slider",
                    "value": 3,
                    "minimum": 0,
                    "maximum": 10,
                    "step": 1,
                    "editor_enabled": true
                },
                {
                    "key": "bound",
                    "label": "Bound",
                    "type": "interval_1d",
                    "inline_editor": "interval_slider",
                    "value": {"start": 2, "end": 8},
                    "minimum": 0,
                    "maximum": 10,
                    "step": 1,
                    "interval_direction": "increasing",
                    "editor_enabled": true
                }
            ]
        })
        verify(root !== null)
        var host = root.probeInlineHost
        var layer = root.probeInlineLayer
        var field = findChild(layer, "graphNodeInlineValueEditor")
        var slider = findChild(layer, "graphNodeInlineSliderEditor")
        var interval = findChild(layer, "graphNodeInlineIntervalSliderEditor")
        verify(field !== null)
        verify(slider !== null)
        verify(interval !== null)

        host.graphFontSize = 17
        tryCompare(field, "inlineFontPixelSize", 17)
        tryCompare(slider, "captionPixelSize", 17)
        tryCompare(interval, "captionPixelSize", 17)
        verify(field.height >= field.contentHeight)
        verify(slider.height >= slider.implicitHeight)
        verify(interval.height >= interval.implicitHeight)
        tryVerify(function() { return layer.embeddedInteractiveRects.length === 3 })
    }

    function test_single_line_surface_controls_publish_uncapped_display_text_fit_widths() {
        var root = createTemporaryObject(fitProbeComponent, stage)
        verify(root !== null)
        tryVerify(function() { return root.fitTextField.textFitWidth > 0 })
        verify(root.fitTextField.textFitWidth > root.fitTextField.width)
        verify(root.fitComboBox.textFitWidth > root.fitComboBox.width)
        verify(root.fitColorEditor.textFitWidth > root.fitColorEditor.width)

        var shortenedWidth = root.fitPathEditor.textFitWidth
        root.fitPathEditor.shortenDisplayPathWhenInactive = false
        tryVerify(function() { return root.fitPathEditor.textFitWidth > shortenedWidth })
        verify(root.fitPathEditor.textFitWidth > 1400)
    }

    function test_inline_properties_layer_fits_widest_eligible_row_and_excludes_multiline_controls() {
        var root = createProbe({
            "inlineProperties": [
                {
                    "key": "message",
                    "label": "Message",
                    "inline_editor": "text",
                    "value": "A very long displayed text value ".repeat(12),
                    "overridden_by_input": false
                },
                {
                    "key": "count",
                    "label": "Count",
                    "inline_editor": "number",
                    "value": 12345678901234567890,
                    "overridden_by_input": false
                },
                {
                    "key": "mode",
                    "label": "Mode",
                    "inline_editor": "enum",
                    "value": "A long selected enum value",
                    "enum_values": ["A long selected enum value"],
                    "overridden_by_input": false
                },
                {
                    "key": "color",
                    "label": "Color",
                    "inline_editor": "color",
                    "value": "#AABBCCDD",
                    "overridden_by_input": false
                }
            ]
        })
        verify(root !== null)
        var host = root.probeInlineHost
        var layer = root.probeInlineLayer
        tryVerify(function() { return layer.requiredTextFitNodeWidth > host.width })

        host.inlineProperties = [
            {
                "key": "enabled",
                "label": "Enabled",
                "inline_editor": "toggle",
                "value": true,
                "overridden_by_input": false
            },
            {
                "key": "notes",
                "label": "Notes",
                "inline_editor": "textarea",
                "value": "Wrapped multiline content",
                "overridden_by_input": false
            }
        ]
        tryVerify(function() {
            return layer._inlineDelegatesReady && layer.requiredTextFitNodeWidth === 0
        })

        host.inlineProperties = [
            {
                "key": "message",
                "label": "Message",
                "inline_editor": "text",
                "value": "Visible disabled value",
                "overridden_by_input": true,
                "input_port_label": "a very long upstream input label"
            }
        ]
        tryVerify(function() { return layer.requiredTextFitNodeWidth > 0 })
    }

    function createFloatingToolbarProbe() {
        var root = createTemporaryObject(floatingToolbarProbeComponent, stage)
        verify(root !== null)
        tryVerify(function() {
            var toolbar = findChild(root, "floatingToolbarProbeToolbar")
            return toolbar !== null && toolbar.visible
        }, 1000)
        return root
    }

    function createSelectionEnvelopeProbe() {
        var root = createTemporaryObject(selectionEnvelopeProbeComponent, stage)
        verify(root !== null)
        tryVerify(function() {
            return findChild(root, "selectionEnvelopeProbeOverlay") !== null
        }, 1000)
        return root
    }

    function test_floating_toolbar_action_model_ignores_position_only_changes() {
        var probe = createFloatingToolbarProbe()
        var toolbar = findChild(probe, "floatingToolbarProbeToolbar")
        var host = findChild(probe, "floatingToolbarProbeHost")
        var view = findChild(probe, "floatingToolbarProbeViewBridge")
        var rebuildCount = 0
        toolbar._orderedActionsChanged.connect(function() {
            rebuildCount += 1
        })

        view.zoom_value = 0.75
        view.center_x += 40
        view.center_y -= 25
        host.worldOffset += 18
        wait(0)
        compare(rebuildCount, 0)

        host.availableActions = host.availableActions.concat([
            {"id": "new_action", "label": "New", "kind": "common", "enabled": true}
        ])
        tryVerify(function() { return rebuildCount === 1 })
        compare(toolbar._orderedActions.length, 5)
    }

    function clickItem(item, button) {
        verify(item !== null)
        mouseClick(
            item,
            Math.max(1, item.width * 0.5),
            Math.max(1, item.height * 0.5),
            button === undefined ? Qt.LeftButton : button
        )
        wait(0)
    }

    function test_floating_toolbar_publishes_rect_and_dispatches_each_action_exactly_once() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        verify(toolbar.width > 0)
        verify(toolbar.height > 0)
        verify(toolbar.toolbarRect.width > 0)
        verify(toolbar.toolbarRect.height > 0)
        compare(toolbar.embeddedInteractiveRects.length, 1)
        verify(toolbar.embeddedInteractiveRects[0].width > 0)

        var events = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            events.push([String(nodeId), String(actionId)])
        })
        var actionIds = ["frame_node", "rename", "duplicate", "delete"]
        for (var index = 0; index < actionIds.length; ++index)
            clickItem(findChild(root, "graphNodeFloatingToolbarAction_" + actionIds[index]))
        compare(JSON.stringify(events), JSON.stringify([
            ["probe_node", "frame_node"],
            ["probe_node", "rename"],
            ["probe_node", "duplicate"],
            ["probe_node", "delete"]
        ]))
    }

    function test_floating_toolbar_grouped_surface_popover_dispatches_surface_actions() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        host.useGroupedSurfaceActionProbe()
        wait(0)
        var nodeEvents = []
        var surfaceEvents = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            nodeEvents.push([String(nodeId), String(actionId)])
        })
        host.surfaceActionRequested.connect(function(actionId) {
            surfaceEvents.push(String(actionId))
        })

        var groupButton = findChild(root, "graphNodeFloatingToolbarAction_text_style_group")
        compare(groupButton.iconName, "format-bold-italic")
        verify(groupButton.iconOnly)
        groupButton.clicked()
        tryCompare(findChild(root, "graphNodeFloatingToolbarActionPopover"), "visible", true, 1000)
        compare(toolbar.embeddedInteractiveRects.length, 2)
        findChild(root, "graphNodeFloatingToolbarPopoverAction_text_toggle_underline").clicked()
        compare(JSON.stringify(surfaceEvents), JSON.stringify(["text_toggle_underline"]))
        compare(nodeEvents.length, 0)
    }

    function test_floating_toolbar_routes_surface_kind_actions_to_surface_dispatch() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        host.useSurfaceActionProbe()
        wait(0)
        var nodeEvents = []
        var surfaceEvents = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            nodeEvents.push([String(nodeId), String(actionId)])
        })
        host.surfaceActionRequested.connect(function(actionId) {
            surfaceEvents.push(String(actionId))
        })

        findChild(root, "graphNodeFloatingToolbarAction_text_toggle_bold").clicked()
        compare(findChild(root, "graphNodeFloatingToolbarAction_text_copy_style").iconName, "copy-text-style")
        var pasteButton = findChild(root, "graphNodeFloatingToolbarAction_text_paste_style")
        compare(pasteButton.iconName, "paste-text-style")
        pasteButton.clicked()
        findChild(root, "graphNodeFloatingToolbarAction_rename_node").clicked()
        compare(JSON.stringify(surfaceEvents), JSON.stringify([
            "text_toggle_bold",
            "text_paste_style"
        ]))
        compare(JSON.stringify(nodeEvents), JSON.stringify([["probe_node", "rename_node"]]))
    }

    function test_floating_toolbar_fullscreen_click_survives_viewer_action_refresh() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        host.useViewerFullscreenActionProbe()
        host.rebuildViewerActionsOnControlStart = true
        var events = []
        host.surfaceActionRequested.connect(function(actionId) {
            events.push(String(actionId))
        })
        var button = findChild(root, "graphNodeFloatingToolbarAction_fullscreen")
        mousePress(button, button.width * 0.5, button.height * 0.5)
        wait(0)
        mouseRelease(button, button.width * 0.5, button.height * 0.5)
        compare(JSON.stringify(events), JSON.stringify(["fullscreen"]))
    }

    function test_floating_toolbar_does_not_fall_back_to_node_dispatch_when_surface_action_unhandled() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        host.useSurfaceActionProbe()
        host.surfaceActionHandledResult = false
        wait(0)
        var nodeEvents = []
        var surfaceEvents = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            nodeEvents.push([String(nodeId), String(actionId)])
        })
        host.surfaceActionRequested.connect(function(actionId) {
            surfaceEvents.push(String(actionId))
        })
        findChild(root, "graphNodeFloatingToolbarAction_text_toggle_bold").clicked()
        compare(JSON.stringify(surfaceEvents), JSON.stringify(["text_toggle_bold"]))
        compare(nodeEvents.length, 0)
    }

    function test_floating_toolbar_tooltips_stay_clear_of_scaled_toolbar_hit_area() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        findChild(root, "floatingToolbarProbeViewBridge").zoom_value = 0.45
        var button = findChild(root, "graphNodeFloatingToolbarAction_rename")
        var tooltip = findChild(button, "graphNodeFloatingToolbarAction_rename_tooltip")
        var nodeTooltip = findChild(root, "floatingToolbarProbeNodeToolTip")
        host.showNodeTooltip = true
        mouseMove(button, button.width * 0.5, button.height * 0.5)
        wait(360)
        tryVerify(function() {
            return button.tooltipVisible && tooltip.visible && nodeTooltip.visible
        }, 1000)
        verify(button.tooltipScreenStablePositioning)
        verify(Math.abs(button.tooltipAnchorScale - 0.45) < 0.01)
        compare(button.tooltipScreenStablePlacement, "above")
        verify(!host.floatingToolbarFlipped)
        verify(Math.abs(host.floatingToolbarZoom - 0.45) < 0.01)
        compare(nodeTooltip.screenStablePlacement, "below")

        var nodeScale = host.floatingToolbarZoom
        var nodeGap = nodeTooltip.screenGap
        verify(nodeTooltip.y * nodeScale >= host.height * nodeScale + nodeGap - 0.75)
        var clearsToolbar = function() {
            var tooltipTop = nodeTooltip.y
            var tooltipBottom = tooltipTop + nodeTooltip.height
            var toolbarTop = toolbar.y
            var toolbarBottom = toolbarTop + toolbar.height
            return tooltipBottom <= toolbarTop + 0.75 || tooltipTop >= toolbarBottom - 0.75
        }
        verify(clearsToolbar())
        verify(
            (tooltip.y + tooltip.height) * button.tooltipAnchorScale
                <= -button.tooltipScreenGap + 0.75
        )

        host.y = 5
        tryCompare(toolbar, "flipped", true, 1000)
        tryCompare(host, "floatingToolbarFlipped", true, 1000)
        compare(nodeTooltip.screenStablePlacement, "above")
        verify(clearsToolbar())
    }

    function test_floating_toolbar_renders_checked_action_state_without_disabling_button() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        host.useToggleActionProbe()
        var loopButton = findChild(root, "graphNodeFloatingToolbarAction_loop")
        var fitButton = findChild(root, "graphNodeFloatingToolbarAction_fit")
        var sourceButton = findChild(root, "graphNodeFloatingToolbarAction_source")
        verify(loopButton.enabled)
        verify(loopButton.active)
        verify(!fitButton.active)
        verify(!sourceButton.active)
        verify(loopButton.resolvedFillColor.a > fitButton.resolvedFillColor.a)
        verify(loopButton.resolvedBorderColor.a > fitButton.resolvedBorderColor.a)
        compare(String(loopButton.resolvedForegroundColor).toLowerCase(), "#5da9ff")
    }

    function test_floating_toolbar_run_action_exposes_selected_run_menu() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        host.useRunMenuActionProbe()
        wait(0)
        var events = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            events.push([String(nodeId), String(actionId)])
        })
        findChild(root, "graphNodeFloatingToolbarAction_run_selected").clicked()
        compare(JSON.stringify(events), JSON.stringify([["probe_node", "run_selected"]]))
        var optionsButton = findChild(root, "graphNodeFloatingToolbarActionMenu_run_selected")
        compare(optionsButton.iconName, "settings")
        optionsButton.clicked()
        var menu = findChild(root, "graphNodeFloatingToolbarRunMenu")
        tryCompare(menu, "visible", true, 1000)
        compare(menu.visibleActions.length, 2)
        compare(menu.visibleActions[0].actionId, "preview_selected_run")
        compare(menu.visibleActions[1].actionId, "open_selected_run_settings")

        var chrome = findChild(root, "graphNodeFloatingToolbarChrome")
        var bridge = findChild(root, "graphNodeFloatingToolbarRunMenuBridge")
        verify(bridge.visible)
        var intervals = [
            [Math.min(chrome.y, chrome.y + chrome.height), Math.max(chrome.y, chrome.y + chrome.height)],
            [Math.min(bridge.y, bridge.y + bridge.height), Math.max(bridge.y, bridge.y + bridge.height)],
            [Math.min(menu.y, menu.y + menu.panelHeight), Math.max(menu.y, menu.y + menu.panelHeight)]
        ]
        intervals.sort(function(left, right) { return left[0] - right[0] })
        for (var index = 0; index + 1 < intervals.length; ++index)
            verify(intervals[index + 1][0] <= intervals[index][1] + 1)
    }

    function test_floating_toolbar_buttons_support_keyboard_tab_and_enter() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var events = []
        host.nodeActionRequested.connect(function(nodeId, actionId, payload) {
            events.push([String(nodeId), String(actionId)])
        })
        var firstButton = findChild(root, "graphNodeFloatingToolbarAction_rename")
        firstButton.forceActiveFocus()
        tryCompare(firstButton, "activeFocus", true, 1000)
        keyClick(Qt.Key_Return)
        compare(JSON.stringify(events), JSON.stringify([["probe_node", "rename"]]))
        var secondButton = findChild(root, "graphNodeFloatingToolbarAction_duplicate")
        secondButton.forceActiveFocus()
        tryCompare(secondButton, "activeFocus", true, 1000)
        keyClick(Qt.Key_Enter)
        compare(JSON.stringify(events), JSON.stringify([
            ["probe_node", "rename"],
            ["probe_node", "duplicate"]
        ]))
    }

    function test_floating_toolbar_visibility_tracks_host_toolbar_active_flag() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        verify(host.toolbarActive)
        verify(toolbar.visible)
        host.toolbarActive = false
        tryCompare(toolbar, "visible", false, 1000)
        host.toolbarActive = true
        tryCompare(toolbar, "visible", true, 1000)
        host.availableActions = []
        tryCompare(toolbar, "visible", false, 1000)
    }

    function test_floating_toolbar_uses_readable_shell_accent_for_web_style_actions() {
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        host.nodeData = {"node_id": "probe_node"}
        host.nodeThemeColor = "#ffffff"
        host.surfaceColor = "#e8f0f7"
        host.outlineColor = "#c3d4e2"
        host.headerTextColor = "#1b2733"
        host.useWebStyleActionProbe()
        var expectedAccent = String(toolbar._shellAccentColor).toLowerCase()
        compare(String(toolbar.accentColor).toLowerCase(), expectedAccent)
        var actionIds = [
            "web_page_back",
            "web_page_forward",
            "web_page_reload_stop",
            "web_page_edit_address",
            "fullscreen",
            "web_page_detach",
            "frame_node",
            "rename_node",
            "duplicate_node"
        ]
        for (var index = 0; index < actionIds.length; ++index) {
            var button = findChild(root, "graphNodeFloatingToolbarAction_" + actionIds[index])
            compare(String(button.accentColor).toLowerCase(), expectedAccent)
            verify(button.hoverFillColor.a > 0)
            compare(String(button.hoverBorderColor).toLowerCase(), String(button.hoverFillColor).toLowerCase())
        }
        compare(
            String(findChild(root, "graphNodeFloatingToolbarAction_remove_node").accentColor).toLowerCase(),
            "#d94f4f"
        )
    }

    function test_floating_toolbar_anchor_flip_does_not_trigger_binding_loop() {
        failOnWarning(/Binding loop detected/)
        var root = createFloatingToolbarProbe()
        var host = findChild(root, "floatingToolbarProbeHost")
        var toolbar = findChild(root, "floatingToolbarProbeToolbar")
        host.y = 5
        tryCompare(toolbar, "flipped", true, 1000)
    }

    function test_selection_envelope_defaults_to_minimal_affordance_and_tracks_bounds() {
        var root = createSelectionEnvelopeProbe()
        var overlay = findChild(root, "selectionEnvelopeProbeOverlay")
        var frame = findChild(root, "graphSelectionEnvelopeFrame")
        var affordance = findChild(root, "graphSelectionEnvelopeMinimalAffordance")
        var sideRail = findChild(root, "graphSelectionEnvelopeSideRail")
        tryCompare(overlay, "visible", true, 1000)
        compare(overlay.selectionToolbarMode, "minimal_ghost_menu")
        compare(overlay.minimalMenuTrigger, "click_affordance")
        verify(affordance.visible)
        verify(!sideRail.visible)
        compare(overlay.selectionBounds.x, 120)
        compare(overlay.selectionBounds.y, 100)
        compare(overlay.selectionBounds.width, 300)
        compare(overlay.selectionBounds.height, 230)
        verify(Math.abs(affordance.x - (frame.x + frame.width - affordance.width * 0.5)) < 0.01)
        verify(Math.abs(affordance.y - (frame.y + 8)) < 0.01)
        verify(affordance.y >= frame.y)
        verify(affordance.y + affordance.height <= frame.y + frame.height)

        findChild(root, "selectionEnvelopeProbeHostB").dragTranslateX = 30
        tryVerify(function() {
            return overlay.selectionBounds.width === 330
        }, 1000)
    }

    function test_selection_envelope_minimal_tooltip_stays_clear_of_affordance() {
        var root = createSelectionEnvelopeProbe()
        findChild(root, "selectionEnvelopeProbeViewBridge").zoom_value = 0.55
        var affordance = findChild(root, "graphSelectionEnvelopeMinimalAffordance")
        var tooltip = findChild(affordance, "graphSelectionEnvelopeMinimalAffordance_tooltip")
        mouseMove(affordance, affordance.width * 0.5, affordance.height * 0.5)
        wait(360)
        tryVerify(function() {
            return affordance.tooltipVisible && tooltip.visible
        }, 1000)
        verify(affordance.tooltipScreenStablePositioning)
        compare(affordance.tooltipScreenStablePlacement, "below")
        verify(Math.abs(affordance.tooltipAnchorScale - 0.55) < 0.01)
        verify(
            tooltip.y * affordance.tooltipAnchorScale
                >= affordance.height * affordance.tooltipAnchorScale
                    + affordance.tooltipScreenGap - 0.75
        )
    }

    function test_selection_envelope_click_affordance_and_right_click_trigger_menu() {
        var root = createSelectionEnvelopeProbe()
        var canvas = findChild(root, "selectionEnvelopeProbeCanvasItem")
        var state = findChild(root, "selectionEnvelopeProbeCanvasStateBridge")
        var affordance = findChild(root, "graphSelectionEnvelopeMinimalAffordance")
        var frame = findChild(root, "graphSelectionEnvelopeFrame")
        clickItem(affordance)
        compare(canvas.openedSelectionMenus, 1)
        state.graphics_selection_toolbar_minimal_menu_trigger = "right_click"
        tryCompare(affordance, "visible", false, 1000)
        clickItem(frame, Qt.RightButton)
        compare(canvas.openedSelectionMenus, 2)
    }

    function test_selection_envelope_side_rail_dispatches_enabled_actions_only() {
        var root = createSelectionEnvelopeProbe()
        var state = findChild(root, "selectionEnvelopeProbeCanvasStateBridge")
        var scene = findChild(root, "selectionEnvelopeProbeSceneBridge")
        var router = findChild(root, "selectionEnvelopeProbeActionRouter")
        state.graphics_selection_toolbar_mode = "side_rail"
        scene.selected_node_lookup = {"node-a": true, "node-b": true}
        var affordance = findChild(root, "graphSelectionEnvelopeMinimalAffordance")
        var sideRail = findChild(root, "graphSelectionEnvelopeSideRail")
        var align = findChild(root, "graphSelectionEnvelopeAction_align_selection_left")
        var distribute = findChild(root, "graphSelectionEnvelopeAction_distribute_selection_horizontally")
        var straighten = findChild(root, "graphSelectionEnvelopeAction_straighten_selection_connections")
        tryCompare(sideRail, "visible", true, 1000)
        verify(!affordance.visible)
        verify(align.enabled)
        verify(!distribute.enabled)
        verify(straighten.enabled)
        verify(align.tooltipScreenStablePositioning)
        verify(align.tooltipScreenGap >= 8)
        compare(align.tooltipScreenStablePlacement, "left")
        verify(Math.abs(align.tooltipAnchorScale - 1) < 0.01)
        distribute.clicked()
        align.clicked()
        compare(JSON.stringify(router.triggeredActions), JSON.stringify(["align_selection_left"]))
    }

    function test_selection_envelope_hides_edge_only_and_disables_straighten_without_internal_edge() {
        var root = createSelectionEnvelopeProbe()
        var overlay = findChild(root, "selectionEnvelopeProbeOverlay")
        var canvas = findChild(root, "selectionEnvelopeProbeCanvasItem")
        var scene = findChild(root, "selectionEnvelopeProbeSceneBridge")
        var state = findChild(root, "selectionEnvelopeProbeCanvasStateBridge")
        scene.selected_node_lookup = {}
        canvas.selectedEdgeIds = ["edge-ab"]
        tryCompare(overlay, "visible", false, 1000)
        state.graphics_selection_toolbar_mode = "side_rail"
        scene.selected_node_lookup = {"node-a": true, "node-c": true}
        canvas.selectedEdgeIds = ["edge-bx"]
        tryCompare(overlay, "visible", true, 1000)
        verify(!overlay.canStraightenConnections)
        verify(!findChild(root, "graphSelectionEnvelopeAction_straighten_selection_connections").enabled)
    }
}
