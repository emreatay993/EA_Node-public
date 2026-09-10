import QtQuick 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph_canvas" as GraphCanvas

TestCase {
    id: testCase
    name: "GraphCanvasSurfaceEditorOverlays"
    width: 1200
    height: 900
    visible: true
    when: windowShown
    property var tooltipCopyBridge: null
    property var themePalette: ({
        "accent": "#60cdff",
        "border": "#3a3d45",
        "button_bg": "#2d3139",
        "button_fg": "#f0f4fb",
        "group_title_fg": "#d0d5de",
        "input_bg": "#24262c",
        "input_border": "#4a4f5a",
        "input_fg": "#f0f2f5",
        "muted_fg": "#95a0b8",
        "panel_bg": "#1b1d22",
        "panel_title_fg": "#f0f4fb"
    })

    Component {
        id: probeComponent

        Item {
            id: probe
            width: 1200
            height: 900
            property alias overlay: overlays
            property alias canvasStub: canvasStub
            property alias webHost: webHost
            property alias timestampHost: timestampHost
            property alias sliderHost: sliderHost
            property alias selectHost: selectHost
            property alias panelHost: panelHost
            property alias webSurface: webSurface
            property alias timestampSurface: timestampSurface
            property alias sliderSurface: sliderSurface
            property alias selectSurface: selectSurface
            property alias panelSurface: panelSurface

            QtObject {
                id: webSurface
                property bool addressEditorOpen: false
                property string addressEditorText: "https://initial.test"
                property var effectiveThemePalette: testCase.themePalette
                property var calls: []
                function acceptAddressEdit(value) {
                    calls = calls.concat([["accept", String(value)]])
                    addressEditorOpen = false
                }
                function cancelAddressEdit() {
                    calls = calls.concat([["cancel"]])
                    addressEditorOpen = false
                }
            }

            QtObject {
                id: timestampSurface
                property bool timestampManualEditorOpen: false
                property string timestampManualEditorText: "2026-09-02T10:20:30"
                property var calls: []
                function acceptTimestampManualEdit(value) {
                    calls = calls.concat([["accept", String(value)]])
                    timestampManualEditorOpen = false
                }
                function cancelTimestampManualEdit() {
                    calls = calls.concat([["cancel"]])
                    timestampManualEditorOpen = false
                }
            }

            QtObject {
                id: sliderSurface
                property bool sliderSettingsEditorOpen: false
                property var sliderSettingsPayload: ({
                    "title": "Gain",
                    "rounding": "decimal",
                    "decimals": 2,
                    "minimum": 0,
                    "value": 5,
                    "maximum": 10
                })
                property var calls: []
                function acceptSliderSettings(value) {
                    calls = calls.concat([["accept", value]])
                    sliderSettingsEditorOpen = false
                }
                function cancelSliderSettings() {
                    calls = calls.concat([["cancel"]])
                    sliderSettingsEditorOpen = false
                }
            }

            QtObject {
                id: selectSurface
                property bool selectSettingsEditorOpen: false
                property var selectSettingsPayload: ({
                    "selected_index": 0,
                    "options": [
                        {"name": "A", "value": "a"},
                        {"name": "B", "value": "b"}
                    ]
                })
                property var calls: []
                function acceptSelectSettings(value) {
                    calls = calls.concat([["accept", value]])
                    selectSettingsEditorOpen = false
                }
                function cancelSelectSettings() {
                    calls = calls.concat([["cancel"]])
                    selectSettingsEditorOpen = false
                }
            }

            QtObject {
                id: panelSurface
                property bool panelEditorOpen: false
                property var panelEditorPayload: ({
                    "value": "Panel text",
                    "mode": 0,
                    "font_size": 12,
                    "alignment": 2,
                    "auto_resize": true,
                    "parse_numbers": false
                })
                property var calls: []
                function acceptPanelSettings(value) {
                    calls = calls.concat([["accept", value]])
                    panelEditorOpen = false
                }
                function cancelPanelSettings() {
                    calls = calls.concat([["cancel"]])
                    panelEditorOpen = false
                }
            }

            Item {
                id: webHost
                x: 100
                y: 140
                width: 240
                height: 120
                property var loadedSurfaceItem: webSurface
                property int shadowStrength: 60
                property int shadowSoftness: 52
                property int shadowOffset: 5
            }

            Item {
                id: timestampHost
                x: 390
                y: 540
                width: 220
                height: 120
                property var loadedSurfaceItem: timestampSurface
                property int shadowStrength: 60
                property int shadowSoftness: 52
                property int shadowOffset: 5
            }

            Item {
                id: sliderHost
                x: 670
                y: 160
                width: 220
                height: 120
                property var loadedSurfaceItem: sliderSurface
                property int shadowStrength: 60
                property int shadowSoftness: 52
                property int shadowOffset: 5
            }

            Item {
                id: selectHost
                x: 760
                y: 560
                width: 220
                height: 120
                property var loadedSurfaceItem: selectSurface
                property int shadowStrength: 60
                property int shadowSoftness: 52
                property int shadowOffset: 5
            }

            Item {
                id: panelHost
                x: 150
                y: 560
                width: 220
                height: 120
                property var loadedSurfaceItem: panelSurface
                property int shadowStrength: 60
                property int shadowSoftness: 52
                property int shadowOffset: 5
                property color inlineInputTextColor: "#f0f2f5"
                property color inlineInputBackgroundColor: "#24262c"
                property color inlineInputBorderColor: "#4a4f5a"
                property color selectedOutlineColor: "#60cdff"
                property color surfaceColor: "#1b1d22"
                property int nodeTextRenderType: Text.CurveRendering
                property var graphSharedTypography: null
            }

            Item {
                id: canvasStub
                property Item activeToolbarHost: null
            }

            GraphCanvas.GraphCanvasSurfaceEditorOverlays {
                id: overlays
                anchors.fill: parent
                canvasItem: canvasStub
                themePalette: testCase.themePalette
            }
        }
    }

    function createProbe() {
        var probe = createTemporaryObject(probeComponent, testCase)
        verify(probe !== null)
        return probe
    }

    function findNamed(item, name) {
        if (!item)
            return null
        if (String(item.objectName || "") === name)
            return item
        var children = item.children || []
        for (var index = 0; index < children.length; ++index) {
            var found = findNamed(children[index], name)
            if (found)
                return found
        }
        return null
    }

    function assertPositioned(layer, popover) {
        verify(popover.x >= 8)
        verify(popover.y >= 8)
        verify(popover.x + popover.width <= layer.width - 8 + 0.01)
        verify(popover.y + popover.height <= layer.height - 8 + 0.01)
    }

    function closeSurface(surface, openProperty) {
        surface[openProperty] = false
        wait(0)
    }

    function test_component_replaces_web_root_and_contains_other_exact_layers() {
        var probe = createProbe()
        compare(probe.overlay.objectName, "webPageAddressOverlayLayer")
        var names = [
            "graphNodeTimestampOverlayLayer",
            "graphNumberSliderOverlayLayer",
            "graphSelectOverlayLayer",
            "graphPanelOverlayLayer"
        ]
        for (var index = 0; index < names.length; ++index) {
            var layer = findNamed(probe.overlay, names[index])
            verify(layer !== null)
            compare(layer.parent, probe.overlay)
        }
    }

    function test_open_focus_position_and_surface_identity_for_all_editors() {
        var probe = createProbe()
        var overlay = probe.overlay

        probe.webSurface.addressEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(
            probe.webHost,
            "web_page_edit_address",
            probe.webSurface
        ))
        compare(overlay.webPageAddressEditorHost, probe.webHost)
        verify(overlay.webPageAddressOverlayOpen)
        var webPopover = findNamed(overlay, "webPageAddressPopover")
        var webField = findNamed(overlay, "webPageAddressPopoverField")
        tryVerify(function() { return webField.activeFocus })
        assertPositioned(overlay, webPopover)
        closeSurface(probe.webSurface, "addressEditorOpen")

        probe.timestampSurface.timestampManualEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(
            probe.timestampHost,
            "timestamp_edit_manual",
            probe.timestampSurface
        ))
        compare(overlay.timestampEditorHost, probe.timestampHost)
        verify(overlay.timestampOverlayOpen)
        var timestampLayer = findNamed(overlay, "graphNodeTimestampOverlayLayer")
        var timestampPopover = findNamed(overlay, "graphNodeTimestampDateTimePopover")
        var hourField = findNamed(overlay, "graphNodeTimestampHourField")
        tryVerify(function() { return hourField.activeFocus })
        assertPositioned(timestampLayer, timestampPopover)
        closeSurface(probe.timestampSurface, "timestampManualEditorOpen")

        probe.sliderSurface.sliderSettingsEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(
            probe.sliderHost,
            "number_slider_edit_settings",
            probe.sliderSurface
        ))
        compare(overlay.numberSliderEditorHost, probe.sliderHost)
        verify(overlay.numberSliderOverlayOpen)
        var sliderLayer = findNamed(overlay, "graphNumberSliderOverlayLayer")
        var sliderPopover = findNamed(overlay, "graphNumberSliderSettingsPopover")
        var sliderField = findNamed(overlay, "graphNumberSliderSettingsNameField")
        tryVerify(function() { return sliderField.activeFocus })
        assertPositioned(sliderLayer, sliderPopover)
        closeSurface(probe.sliderSurface, "sliderSettingsEditorOpen")

        probe.selectSurface.selectSettingsEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(
            probe.selectHost,
            "select_edit_settings",
            probe.selectSurface
        ))
        compare(overlay.selectEditorHost, probe.selectHost)
        verify(overlay.selectOverlayOpen)
        var selectLayer = findNamed(overlay, "graphSelectOverlayLayer")
        var selectPopover = findNamed(overlay, "graphSelectSettingsPopover")
        tryVerify(function() { return selectPopover.activeFocus })
        assertPositioned(selectLayer, selectPopover)
        closeSurface(probe.selectSurface, "selectSettingsEditorOpen")

        probe.panelSurface.panelEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(
            probe.panelHost,
            "panel_edit",
            probe.panelSurface
        ))
        compare(overlay.panelEditorHost, probe.panelHost)
        verify(overlay.panelOverlayOpen)
        var panelLayer = findNamed(overlay, "graphPanelOverlayLayer")
        var panelPopover = findNamed(overlay, "graphPanelEditorPopover")
        var panelField = findNamed(overlay, "graphPanelEditorValueField")
        tryVerify(function() { return panelField.activeFocus })
        assertPositioned(panelLayer, panelPopover)
    }

    function test_accept_callbacks_commit_and_close_each_surface() {
        var probe = createProbe()
        var overlay = probe.overlay

        probe.webSurface.addressEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(probe.webHost, "web_page_edit_address"))
        findNamed(overlay, "webPageAddressPopover").accepted("https://accepted.test")
        tryCompare(probe.webSurface, "addressEditorOpen", false)
        compare(probe.webSurface.calls[0][0], "accept")
        compare(probe.webSurface.calls[0][1], "https://accepted.test")

        probe.timestampSurface.timestampManualEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(probe.timestampHost, "timestamp_edit_manual"))
        findNamed(overlay, "graphNodeTimestampDateTimePopover").accepted("2026-09-03T01:02:03")
        tryCompare(probe.timestampSurface, "timestampManualEditorOpen", false)
        compare(probe.timestampSurface.calls[0][0], "accept")

        probe.sliderSurface.sliderSettingsEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(probe.sliderHost, "number_slider_edit_settings"))
        findNamed(overlay, "graphNumberSliderSettingsPopover").accepted({"value": 7})
        tryCompare(probe.sliderSurface, "sliderSettingsEditorOpen", false)
        compare(probe.sliderSurface.calls[0][0], "accept")

        probe.selectSurface.selectSettingsEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(probe.selectHost, "select_edit_settings"))
        findNamed(overlay, "graphSelectSettingsPopover").accepted({"selected_index": 1})
        tryCompare(probe.selectSurface, "selectSettingsEditorOpen", false)
        compare(probe.selectSurface.calls[0][0], "accept")

        probe.panelSurface.panelEditorOpen = true
        verify(overlay.openSurfaceActionOverlayForHost(probe.panelHost, "panel_edit"))
        findNamed(overlay, "graphPanelEditorPopover").accepted({"value": "Accepted"})
        tryCompare(probe.panelSurface, "panelEditorOpen", false)
        compare(probe.panelSurface.calls[0][0], "accept")
    }

    function test_outside_click_cancels_and_clears_each_host() {
        var probe = createProbe()
        var overlay = probe.overlay
        var cases = [
            [probe.webHost, probe.webSurface, "web_page_edit_address", overlay, "addressEditorOpen", "webPageAddressEditorHost"],
            [probe.timestampHost, probe.timestampSurface, "timestamp_edit_manual", findNamed(overlay, "graphNodeTimestampOverlayLayer"), "timestampManualEditorOpen", "timestampEditorHost"],
            [probe.sliderHost, probe.sliderSurface, "number_slider_edit_settings", findNamed(overlay, "graphNumberSliderOverlayLayer"), "sliderSettingsEditorOpen", "numberSliderEditorHost"],
            [probe.selectHost, probe.selectSurface, "select_edit_settings", findNamed(overlay, "graphSelectOverlayLayer"), "selectSettingsEditorOpen", "selectEditorHost"],
            [probe.panelHost, probe.panelSurface, "panel_edit", findNamed(overlay, "graphPanelOverlayLayer"), "panelEditorOpen", "panelEditorHost"]
        ]
        for (var index = 0; index < cases.length; ++index) {
            var row = cases[index]
            row[1][row[4]] = true
            verify(overlay.openSurfaceActionOverlayForHost(row[0], row[2], row[1]))
            mouseClick(row[3], 2, 2, Qt.LeftButton)
            tryCompare(row[1], row[4], false)
            compare(row[1].calls[row[1].calls.length - 1][0], "cancel")
            compare(overlay[row[5]], null)
        }
    }

    function test_active_toolbar_reopens_web_and_timestamp_and_unknown_action_is_rejected() {
        var probe = createProbe()
        var overlay = probe.overlay
        verify(!overlay.openSurfaceActionOverlayForHost(probe.webHost, "unknown_action"))

        probe.webSurface.addressEditorOpen = true
        probe.canvasStub.activeToolbarHost = probe.webHost
        tryCompare(overlay, "webPageAddressEditorHost", probe.webHost)
        probe.webSurface.addressEditorOpen = false
        tryCompare(overlay, "webPageAddressEditorHost", null)

        probe.timestampSurface.timestampManualEditorOpen = true
        probe.canvasStub.activeToolbarHost = probe.timestampHost
        tryCompare(overlay, "timestampEditorHost", probe.timestampHost)
        probe.timestampSurface.timestampManualEditorOpen = false
        tryCompare(overlay, "timestampEditorHost", null)
    }
}
