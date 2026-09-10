import QtQuick 2.15
import QtQuick.Controls 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/shell" as Shell
import "../../ea_node_editor/ui_qml/components/graph/passive" as Passive

TestCase {
    id: testCase
    name: "ShellContextPopup"
    width: 640
    height: 480
    visible: true
    when: windowShown

    QtObject {
        id: themeBridge
        property var palette: ({panel_bg: "#1b1d22", panel_title_fg: "#f0f4fb",
            input_border: "#3a3d45", border: "#3a3d45", accent: "#60cdff",
            inspector_danger_border: "#ff5449", inspector_danger_fg: "#ff5449"})
    }
    TextField { id: editor; y: 430; width: 200; text: "Restore focus here" }
    Item {
        id: scaledSource
        x: 20; y: 30; width: 200; height: 100
        clip: true
        scale: 0.5
        transformOrigin: Item.TopLeft
        Shell.ShellContextPopup { id: popup }
    }
    Shell.ShellContextMenu { id: referenceMenu; visible: false }
    SignalSpy { id: actionSpy; target: popup; signalName: "actionTriggered" }

    Item {
        id: explorerHost
        visible: false
        x: 10; y: 20; width: 580; height: 380
        property bool graphReadOnly: false
        property int nodeTextRenderType: Text.QtRendering
        property var nodeData: ({node_id: "explorer", properties: {}})
        property var canvasItem: explorerCanvas
        Passive.GraphNativeExplorerSurface { id: explorer; anchors.fill: parent; host: explorerHost }
    }
    Item {
        id: explorerCanvas
        property var canvasActionRouter: router
        function screenToSceneX(x) { return x * 2 }
        function screenToSceneY(y) { return y * 2 }
    }
    QtObject {
        id: router
        property var calls: []
        function requestFolderExplorerAction(command, payload) {
            calls.push({command: command, payload: payload})
            return {success: true, listing: {entries: []}}
        }
    }

    function init() {
        actionSpy.clear()
        popup.actions = [
            {actionId: "metadata", text: "Information", enabled: false},
            {actionId: "hidden", text: "Hidden", visible: false},
            {actionId: "checked", text: "Checked action", checked: true, checkable: true},
            {actionId: "copy", text: "Copy a longer descriptive menu label", shortcutText: "Ctrl+C"}
        ]
        editor.forceActiveFocus()
        router.calls = []
        explorerHost.graphReadOnly = false
    }
    function cleanup() {
        popup.close()
        findChild(explorer, "graphFolderExplorerRowContextMenu").close()
        explorerHost.visible = false
        wait(0)
    }
    function openPopup(source, x, y) {
        popup.openAt(source, x, y)
        tryCompare(popup, "opened", true)
        waitForRendering(popup.menuContent)
    }

    function test_keyboard_palette_and_focus() {
        openPopup(testCase, 24, 36)
        compare(popup.menuContent.rowHeight, 30)
        compare(popup.menuContent.contentPadding, 4)
        compare(popup.menuContent.color, referenceMenu.color)
        compare(popup.menuContent.visibleActions.length, 3)
        keyClick(Qt.Key_Down)
        compare(popup.menuContent.currentIndex, 1)
        keyClick(Qt.Key_Return)
        compare(actionSpy.count, 1)
        compare(actionSpy.signalArguments[0][0], "checked")
        tryCompare(popup, "visible", false)
        verify(editor.activeFocus)

        var darkPalette = themeBridge.palette
        themeBridge.palette = {panel_bg: "#ffffff", panel_title_fg: "#18202b",
            input_border: "#cbd5e1", border: "#cbd5e1", accent: "#005fb8",
            inspector_danger_border: "#c42b1c", inspector_danger_fg: "#c42b1c"}
        openPopup(testCase, 24, 36)
        compare(popup.menuContent.color, referenceMenu.color)
        compare(popup.menuContent.color, "#ffffff")
        keyClick(Qt.Key_End)
        compare(popup.menuContent.currentIndex, 2)
        keyClick(Qt.Key_Home)
        compare(popup.menuContent.currentIndex, 1)
        keyClick(Qt.Key_Up)
        compare(popup.menuContent.currentIndex, 2)
        keyClick(Qt.Key_Escape)
        tryCompare(popup, "visible", false)
        verify(editor.activeFocus)
        themeBridge.palette = darkPalette
    }

    function test_scaled_clipped_source_edges_and_long_menu() {
        openPopup(scaledSource, 40, 20)
        compare(popup.x, 40)
        compare(popup.y, 40)
        compare(popup.menuContent.scale, 1)
        verify(popup.width > scaledSource.width)
        mouseClick(testCase, 620, 460)
        tryCompare(popup, "visible", false)
        var actions = []
        for (var i = 0; i < 30; ++i)
            actions.push({actionId: String(i), text: "Action " + i})
        popup.actions = actions
        openPopup(testCase, 635, 475)
        verify(popup.x >= 4 && popup.x + popup.width <= width - 4)
        verify(popup.y >= 4 && popup.y + popup.height <= height - 4)
        keyClick(Qt.Key_End)
        compare(popup.menuContent.currentIndex, 29)
        verify(popup.contentItem.contentY > 0)
        keyClick(Qt.Key_Space)
        compare(actionSpy.signalArguments[0][0], "29")
        tryCompare(popup, "visible", false)
    }

    function test_folder_explorer_data() {
        return [
            {tag: "file", folder: false, parentRow: false, action: "open_with"},
            {tag: "folder", folder: true, parentRow: false, action: "open_in_new_window"},
            {tag: "parent", folder: true, parentRow: true, action: "copy_path"}
        ]
    }
    function test_folder_explorer(data) {
        explorerHost.visible = true
        explorer._applyListing({directory_path: "C:/test", parent_path: data.parentRow ? "C:/" : "",
            entries: data.parentRow ? [] : [{name: "entry", absolute_path: "C:/test/entry", is_folder: data.folder}]})
        waitForRendering(explorer)
        var row = findChild(explorer, "graphFolderExplorerRowMouseArea")
        verify(row !== null)
        mouseClick(row, 60, row.height / 2, Qt.RightButton)
        var menu = findChild(explorer, "graphFolderExplorerRowContextMenu")
        tryCompare(menu, "opened", true)
        waitForRendering(menu.menuContent)
        compare(menu.menuContent.color, referenceMenu.color)
        var ids = menu.menuContent.visibleActions.map(function(action) { return action.actionId })
        compare(ids.indexOf("open_with") >= 0, !data.folder && !data.parentRow)
        compare(ids.indexOf("open_in_new_window") >= 0, data.folder || data.parentRow)
        compare(ids.indexOf("send_to_corex_path_pointer") >= 0, !data.parentRow)
        menu.menuContent.currentIndex = ids.indexOf(data.action)
        keyClick(Qt.Key_Return)
        tryCompare(menu, "visible", false)
        compare(router.calls.length, 1)
        compare(router.calls[0].command, "folder_explorer_" + data.action)
        compare(router.calls[0].payload.path, data.parentRow ? "C:/" : "C:/test/entry")
    }
}
