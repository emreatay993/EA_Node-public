import QtQuick 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph/overlay" as GraphOverlay

TestCase {
    id: testCase
    name: "GraphNodeToolbarPopoverHost"
    width: 800
    height: 600
    visible: true
    when: windowShown

    property var tooltipCopyBridge: null
    property var createdObjects: []

    Component {
        id: popoverProbeComponent

        Item {
            id: probe
            width: 640
            height: 480
            property alias toolbar: toolbarOwner
            property alias owner: popoverHost
            property alias anchorItem: popoverAnchor
            property var events: []
            property int videoBookmarkAddCount: 0

            function recordAction(actionId) {
                var normalized = String(actionId || "")
                probe.events = probe.events.concat([normalized])
                if (normalized === "videoBookmarkAdd") {
                    probe.videoBookmarkAddCount += 1
                    probe.useVideoBookmarkActionProbe()
                }
                return true
            }

            function useRowActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "text_style_group",
                    "label": "Text style",
                    "kind": "surface",
                    "popoverActions": [
                        {"id": "text_toggle_bold", "label": "Bold", "kind": "surface"},
                        {"id": "text_toggle_underline", "label": "Underline", "kind": "surface"}
                    ]
                }]
            }

            function useFontSizeActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "text_font_size_group",
                    "label": "Text size",
                    "toolbar_text": "24",
                    "kind": "surface",
                    "enabled": true,
                    "popover_layout": "font_size",
                    "font_size_value": 24,
                    "font_size_min": 6,
                    "font_size_max": 144,
                    "font_size_set_action_prefix": "text_font_size_set:",
                    "font_size_preview_action_prefix": "text_font_size_preview:",
                    "popoverActions": [
                        {"id": "text_font_size_decrease", "label": "Smaller", "kind": "surface", "role": "decrease", "toolbar_text": "-"},
                        {"id": "text_font_size_increase", "label": "Larger", "kind": "surface", "role": "increase", "toolbar_text": "+"}
                    ]
                }]
            }

            function usePdfPageActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "pdf_page_navigation",
                    "label": "Navigate",
                    "icon": "navigate",
                    "kind": "media",
                    "enabled": true,
                    "popover_layout": "pdf_page",
                    "page_value": 2,
                    "page_min": 1,
                    "page_max": 5,
                    "page_set_action_prefix": "pdf_page_set:",
                    "popoverActions": [
                        {"id": "pdf_page_previous", "label": "Previous page", "icon": "navigate-previous", "kind": "media", "enabled": true},
                        {"id": "pdf_page_next", "label": "Next page", "icon": "navigate-next", "kind": "media", "enabled": true}
                    ]
                }]
            }

            function useSourceStorageActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "editSource",
                    "label": "Source",
                    "kind": "media",
                    "enabled": true,
                    "popover_layout": "source_storage",
                    "popoverActions": [
                        {"id": "editSourceExternalLink", "label": "External link", "toolbar_text": "External", "kind": "media", "enabled": true, "checked": true, "close_popover": true},
                        {"id": "editSourceManagedCopy", "label": "Internal copy", "toolbar_text": "Internal", "kind": "media", "enabled": true, "close_popover": true}
                    ]
                }]
            }

            function useFontFamilyActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "text_font_family_group",
                    "label": "Font family",
                    "toolbar_text": "Segoe UI",
                    "kind": "surface",
                    "enabled": true,
                    "popover_layout": "font_family",
                    "popoverActions": [
                        {"id": "text_font_family_clear", "label": "Default", "toolbar_text": "Default", "font_family": "", "kind": "surface", "checked": false, "close_popover": true},
                        {"id": "text_font_family_set:Arial", "label": "Arial", "toolbar_text": "Arial", "font_family": "Arial", "kind": "surface", "checked": false, "close_popover": true},
                        {"id": "text_font_family_set:Georgia", "label": "Georgia", "toolbar_text": "Georgia", "font_family": "Georgia", "kind": "surface", "checked": false, "close_popover": true},
                        {"id": "text_font_family_set:Segoe%20UI", "label": "Segoe UI", "toolbar_text": "Segoe UI", "font_family": "Segoe UI", "kind": "surface", "checked": true, "close_popover": true}
                    ]
                }]
            }

            function videoBookmarkActions() {
                var actions = [{
                    "id": "videoBookmarkAdd",
                    "label": "Add 0:13",
                    "icon": "video-bookmark-add",
                    "kind": "media",
                    "role": "add",
                    "enabled": true,
                    "close_popover": false
                }]
                for (var index = 0; index < probe.videoBookmarkAddCount; ++index) {
                    var bookmarkId = "bookmark-" + String(index + 1)
                    actions.push({
                        "id": "videoBookmarkJump:" + bookmarkId,
                        "label": "Bookmark " + String(index + 1),
                        "icon": "video-bookmark-jump",
                        "kind": "media",
                        "role": "bookmark",
                        "bookmark_id": bookmarkId,
                        "time_text": "0:" + String(13 + index),
                        "rename_action_prefix": "videoBookmarkRename:" + bookmarkId + ":",
                        "delete_action_id": "videoBookmarkDelete:" + bookmarkId,
                        "enabled": true,
                        "close_popover": false
                    })
                }
                return actions
            }

            function useVideoBookmarkActionProbe() {
                toolbarOwner.actionList = [{
                    "id": "bookmarks",
                    "label": "Bookmarks",
                    "kind": "media",
                    "enabled": true,
                    "popover_layout": "video_bookmarks",
                    "popoverActions": probe.videoBookmarkActions()
                }]
            }

            Item {
                id: surfaceHost
                property var nodeData: ({"node_id": "probe_node"})
                property int nodeTextRenderType: Text.QtRendering

                function dispatchSurfaceAction(actionId) {
                    return probe.recordAction(actionId)
                }

                function surfaceControlInteractionStarted(nodeId) {
                }
            }

            Item {
                id: toolbarOwner
                x: 180
                y: 220
                width: 240
                height: 36
                property var host: surfaceHost
                property var actionList: []
                property bool flipped: false
                property bool runMenuVisible: false
                property real _sizeScale: 1
                property real _effectiveZoom: 1
                property int _buttonIconSize: 16
                property color _chromeBaseFill: "#1b1d22"
                property color _chromeBaseBorder: "#3a3d45"
                property color _chromeForeground: "#f0f4fb"
                property color _buttonHoverFillColor: "#334455"
                property color accentColor: "#4da8da"

                function _iconSource(name, size, color) {
                    return ""
                }

                function _actionColor(action, key, fallback) {
                    return fallback
                }

                function _dispatchToolbarAction(action) {
                    return probe.recordAction(action ? action.id : "")
                }

                Item {
                    id: popoverAnchor
                    x: 80
                    width: 32
                    height: parent.height
                }

                GraphOverlay.GraphNodeToolbarPopoverHost {
                    id: popoverHost
                    toolbar: toolbarOwner
                }
            }
        }
    }

    function init() {
        createdObjects = []
    }

    function cleanup() {
        for (var index = 0; index < createdObjects.length; ++index)
            createdObjects[index].destroy()
        createdObjects = []
    }

    function createProbe() {
        var probe = popoverProbeComponent.createObject(testCase)
        verify(probe !== null)
        createdObjects.push(probe)
        wait(0)
        return probe
    }

    function openFirstAction(probe) {
        probe.owner.openActionPopover(probe.toolbar.actionList[0], probe.anchorItem)
        wait(0)
        tryCompare(probe.owner.actionPopoverItem, "visible", true, 1000)
    }

    function test_direct_root_owns_popover_panels_and_toolbar_coordinates() {
        var probe = createProbe()
        probe.useRowActionProbe()
        openFirstAction(probe)

        compare(probe.owner.objectName, "graphNodeFloatingToolbarActionPopoverBridge")
        compare(probe.owner.actionPopoverItem.objectName, "graphNodeFloatingToolbarActionPopover")
        compare(probe.owner.actionPopoverItem.parent, probe.owner)
        compare(findChild(probe, "graphNodeFloatingToolbarSourceStoragePanel").parent.parent, probe.owner.actionPopoverItem)
        verify(findChild(probe, "graphNodeFloatingToolbarVideoBookmarksPanel") !== null)
        verify(findChild(probe, "graphNodeFloatingToolbarFontSizePanel") !== null)
        verify(findChild(probe, "graphNodeFloatingToolbarPdfPagePanel") !== null)
        verify(findChild(probe, "graphNodeFloatingToolbarFontFamilyPanel") !== null)
        verify(!probe.owner.pointerHovered)

        var mapped = probe.owner.actionPopoverItem.mapToItem(probe.toolbar, 0, 0)
        compare(Math.round(mapped.x), Math.round(probe.owner.actionPopoverX))
        compare(Math.round(mapped.y), Math.round(probe.owner.actionPopoverY))
        compare(probe.owner.actionPopoverLayout, "row")

        mouseMove(
            probe.owner.actionPopoverItem,
            probe.owner.actionPopoverItem.width / 2,
            probe.owner.actionPopoverItem.height / 2
        )
        tryCompare(probe.owner, "pointerHovered", true, 1000)
        mouseMove(probe, 2, 2)
        tryCompare(probe.owner, "pointerHovered", false, 1000)

        probe.owner.openActionPopover(probe.toolbar.actionList[0], probe.anchorItem)
        tryCompare(probe.owner.actionPopoverItem, "visible", false, 1000)
        compare(probe.events[probe.events.length - 1], "text_style_flush")
    }

    function test_video_bookmarks_refresh_after_repeated_adds() {
        var probe = createProbe()
        probe.useVideoBookmarkActionProbe()
        openFirstAction(probe)
        compare(probe.owner.actionPopoverLayout, "video_bookmarks")
        compare(probe.owner.actionPopoverActions.length, 1)

        findChild(probe, "graphNodeFloatingToolbarPopoverAction_videoBookmarkAdd").clicked()
        tryCompare(probe.owner.actionPopoverActions, "length", 2, 1000)
        compare(probe.events[0], "videoBookmarkAdd")
        verify(probe.owner.actionPopoverItem.visible)
        compare(findChild(probe, "graphNodeFloatingToolbarVideoBookmarkTime"), null)
        var labelField = findChild(probe, "graphNodeFloatingToolbarVideoBookmarkLabel_bookmark-1")
        compare(labelField.placeholderText, "0:13")
        compare(findChild(probe, "graphNodeFloatingToolbarVideoBookmarkJump_bookmark-1").iconName, "video-bookmark-jump")

        findChild(probe, "graphNodeFloatingToolbarPopoverAction_videoBookmarkAdd").clicked()
        tryCompare(probe.owner.actionPopoverActions, "length", 3, 1000)
        compare(JSON.stringify(probe.events), JSON.stringify(["videoBookmarkAdd", "videoBookmarkAdd"]))
        compare(probe.owner.actionPopoverActions[0].role, "add")
        compare(probe.owner.actionPopoverActions[1].role, "bookmark")
        compare(probe.owner.actionPopoverActions[2].role, "bookmark")
    }

    function test_font_size_panel_preserves_preview_commit_flush_and_bounds() {
        var probe = createProbe()
        probe.useFontSizeActionProbe()
        openFirstAction(probe)
        compare(probe.owner.actionPopoverLayout, "font_size")

        var panel = findChild(probe, "graphNodeFloatingToolbarFontSizePanel")
        var field = findChild(probe, "graphNodeFloatingToolbarFontSizeField")
        var slider = findChild(probe, "graphNodeFloatingToolbarFontSizeSlider")
        var stepper = findChild(probe, "graphNodeFloatingToolbarFontSizeStepper")
        verify(panel.visible)
        verify(stepper.visible)
        compare(field.text, "24")
        compare(slider.from, 6)
        compare(slider.to, 144)
        compare(slider.stepSize, 1)

        probe.owner._previewFontSizeValue(48)
        probe.owner._previewFontSizeValue(52)
        compare(JSON.stringify(probe.events), JSON.stringify([
            "text_font_size_preview:48",
            "text_font_size_preview:52"
        ]))
        compare(field.text, "52")
        probe.owner._commitFontSizeValue(52)
        compare(probe.events[probe.events.length - 1], "text_font_size_set:52")

        probe.events = []
        probe.owner._previewFontSizeValue(48)
        probe.owner._closeActionPopover(true)
        compare(JSON.stringify(probe.events), JSON.stringify([
            "text_font_size_preview:48",
            "text_style_flush"
        ]))

        probe.owner.openActionPopover(probe.toolbar.actionList[0], probe.anchorItem)
        tryCompare(probe.owner.actionPopoverItem, "visible", true, 1000)
        field.forceActiveFocus()
        keyClick(Qt.Key_A, Qt.ControlModifier)
        keyClick(Qt.Key_A)
        keyClick(Qt.Key_Exclam)
        keyClick(Qt.Key_9)
        compare(field.text, "9")
        keyClick(Qt.Key_Return)
        compare(probe.events[probe.events.length - 1], "text_font_size_set:9")

        field.text = "999"
        field.forceActiveFocus()
        keyClick(Qt.Key_Return)
        compare(probe.events[probe.events.length - 1], "text_font_size_set:144")
        compare(field.text, "144")
        findChild(probe, "graphNodeFloatingToolbarPopoverAction_text_font_size_increase").clicked()
        compare(probe.events[probe.events.length - 1], "text_font_size_increase")
    }

    function test_pdf_page_panel_preserves_field_and_navigation_callbacks() {
        var probe = createProbe()
        probe.usePdfPageActionProbe()
        openFirstAction(probe)
        compare(probe.owner.actionPopoverLayout, "pdf_page")

        var field = findChild(probe, "graphNodeFloatingToolbarPdfPageField")
        var panel = findChild(probe, "graphNodeFloatingToolbarPdfPagePanel")
        var total = findChild(probe, "graphNodeFloatingToolbarPdfPageTotalLabel")
        var previousButton = findChild(probe, "graphNodeFloatingToolbarPopoverAction_pdf_page_previous")
        var nextButton = findChild(probe, "graphNodeFloatingToolbarPopoverAction_pdf_page_next")
        verify(panel.visible)
        compare(field.text, "2")
        compare(total.text, "/ 5")
        compare(previousButton.iconName, "navigate-previous")
        compare(nextButton.iconName, "navigate-next")
        verify(previousButton.enabled)
        verify(nextButton.enabled)

        field.text = "4"
        field.forceActiveFocus()
        keyClick(Qt.Key_Return)
        compare(probe.events[probe.events.length - 1], "pdf_page_set:4")
        nextButton.clicked()
        compare(probe.events[probe.events.length - 1], "pdf_page_set:5")
        compare(field.text, "5")
        verify(!nextButton.enabled)
        previousButton.clicked()
        compare(probe.events[probe.events.length - 1], "pdf_page_set:4")
        compare(field.text, "4")
    }

    function test_source_storage_panel_preserves_default_and_dispatch() {
        var probe = createProbe()
        probe.useSourceStorageActionProbe()
        openFirstAction(probe)
        compare(probe.owner.actionPopoverLayout, "source_storage")

        var panel = findChild(probe, "graphNodeFloatingToolbarSourceStoragePanel")
        var combo = findChild(probe, "graphNodeFloatingToolbarSourceStorageCombo")
        var browseButton = findChild(probe, "graphNodeFloatingToolbarSourceBrowseButton")
        verify(panel.visible)
        compare(combo.currentText, "External")
        compare(Math.round(combo.height), probe.owner._popoverControlHeight)
        compare(Math.round(combo.controlHeight), probe.owner._popoverControlHeight)
        compare(Math.round(browseButton.height), probe.owner._popoverControlHeight)
        combo.currentIndex = 1
        browseButton.clicked()
        compare(JSON.stringify(probe.events), JSON.stringify(["editSourceManagedCopy"]))
        tryCompare(probe.owner.actionPopoverItem, "visible", false, 1000)
    }

    function test_font_family_panel_preserves_focus_filter_and_dispatch() {
        var probe = createProbe()
        probe.useFontFamilyActionProbe()
        openFirstAction(probe)
        compare(probe.owner.actionPopoverLayout, "font_family")

        var field = findChild(probe, "graphNodeFloatingToolbarFontFamilyField")
        verify(findChild(probe, "graphNodeFloatingToolbarFontFamilyPanel").visible)
        verify(findChild(probe, "graphNodeFloatingToolbarFontFamilyList").visible)
        tryCompare(field, "activeFocus", true, 1000)
        compare(field.placeholderText, "Search fonts")
        tryVerify(function() {
            return findChild(probe, "graphNodeFloatingToolbarPopoverAction_text_font_family_set:Segoe%20UI") !== null
        }, 1000)

        probe.owner.actionPopoverFilterText = "geo"
        tryVerify(function() {
            return findChild(probe, "graphNodeFloatingToolbarPopoverAction_text_font_family_set:Georgia") !== null
        }, 1000)
        findChild(probe, "graphNodeFloatingToolbarPopoverAction_text_font_family_set:Georgia").clicked()
        compare(JSON.stringify(probe.events), JSON.stringify([
            "text_font_family_set:Georgia",
            "text_style_flush"
        ]))
        tryCompare(probe.owner.actionPopoverItem, "visible", false, 1000)

        probe.owner.openActionPopover(probe.toolbar.actionList[0], probe.anchorItem)
        tryCompare(probe.owner.actionPopoverItem, "visible", true, 1000)
        findChild(probe, "graphNodeFloatingToolbarPopoverAction_text_font_family_clear").clicked()
        compare(probe.events[probe.events.length - 2], "text_font_family_clear")
        compare(probe.events[probe.events.length - 1], "text_style_flush")
    }
}
