import QtQuick 2.15
import QtQuick.Controls 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/shell" as Shell

TestCase {
    id: tests
    name: "InspectorLifecycle"
    width: 700
    height: 700
    visible: true
    when: windowShown

    Component {
        id: harnessComponent
        Item {
            id: harness
            width: 640
            height: 640
            property string layout: "row"
            property string nodeId: "first"
            property string workspaceId: "workspace"
            property var commits: []
            property var items: [{key: "value", label: "Value", group: "Properties", type: "str",
                value: "saved", editor_mode: "textarea", editor_enabled: true}]
            property var themePalette: ({input_bg: "#222222", input_fg: "#ffffff", input_border: "#555555",
                accent: "#5599ee", panel_title_fg: "#ffffff", group_title_fg: "#ffffff", muted_fg: "#888888",
                inspector_danger_fg: "#ff6666", inspector_danger_border: "#ff4444",
                panel_bg: "#222222", border: "#555555", toolbar_bg: "#333333",
                inspector_selected_bg: "#335577", accent_strong: "#5599ee",
                button_bg: "#333333", button_hover_bg: "#444444", button_fg: "#ffffff",
                button_border: "#555555", button_hover_border: "#666666",
                inspector_section_header_bg: "#333333", group_header_bg: "#333333"})
            property bool isPinInspector: false
            property var pinDataTypeOptions: []
            property var graphCanvasStateBridgeRef: null
            property var inspectorBridgeRef: bridge
            property var uiIconsRef: null
            property color cardBackgroundColor: "#222222"
            property color selectedSurfaceColor: "#335577"
            property alias body: bodyLoader.item
            QtObject {
                id: bridge
                property string selected_node_id: harness.nodeId
                property string selected_node_workspace_id: harness.workspaceId
                function set_selected_node_property(key, value) {
                    harness.commits = harness.commits.concat([{key: key, value: value}])
                }
            }
            Loader {
                id: bodyLoader
                width: 320
                sourceComponent: harness.layout === "smart_groups" ? smart
                    : harness.layout === "accordion_cards" ? accordion
                    : harness.layout === "palette" ? palette : row
            }
            Component { id: row; Shell.InspectorPropertyEditor { pane: harness; propertyItem: harness.items[0] } }
            Component { id: smart; Shell.InspectorSmartGroupsBody { pane: harness; propertyItems: harness.items } }
            Component { id: accordion; Shell.InspectorAccordionCardsBody { pane: harness; propertyItems: harness.items } }
            Component { id: palette; Shell.InspectorPaletteBody { pane: harness; propertyItems: harness.items } }
            Button { objectName: "blurTarget"; x: 400; y: 500; text: "Other control" }
        }
    }

    function makeHarness(layout, items) {
        var props = {layout: layout || "row"}
        if (items)
            props.items = items
        var root = createTemporaryObject(harnessComponent, tests, props)
        verify(root !== null)
        wait(0)
        return root
    }

    function countItems(item) {
        var count = 1
        var children = item.children || []
        for (var i = 0; i < children.length; ++i)
            count += countItems(children[i])
        return count
    }

    function openGroup(root, open) {
        if (root.layout === "smart_groups")
            root.body.expandedMap = {"static:Properties": open}
        else if (root.layout === "accordion_cards")
            root.body.expandedMap = {Properties: open}
        wait(0)
    }

    function test_numeric_scalar_does_not_create_chip_or_font_controls() {
        var root = makeHarness("row", [{key: "width", label: "Width", value: 100000,
            editor_mode: "text", editor_enabled: true}])
        verify(findChild(root, "inspectorTypedEditorLoader").item !== null)
        compare(findChild(root, "inspectorChipListContainer"), null)
        compare(findChild(root, "inspectorFontFamilyEditor"), null)
        verify(countItems(root) < 100, "A scalar row must have bounded visual work")
    }

    function test_chip_editor_rejects_scalar_repeater_counts() {
        var root = makeHarness("row", [{key: "values", label: "Values", value: 100000,
            editor_mode: "chip_list", editor_enabled: true}])
        compare(findChild(root, "inspectorChipListContainer").chipValues.length, 0)
        verify(countItems(root) < 150)
    }

    function test_context_replacement_blocks_old_blur_commits_data() {
        return [{tag: "node", field: "nodeId"}, {tag: "workspace", field: "workspaceId"}]
    }

    function test_context_replacement_blocks_old_blur_commits(data) {
        var root = makeHarness("row", [{key: "value", value: "saved", editor_mode: "editable_combo",
            editor_enabled: true, enum_values: []}])
        var control = findChild(root, "inspectorEditableComboEditor")
        mouseClick(control, 20, control.height / 2)
        control.editText = "uncommitted"
        root[data.field] = "second"
        mouseClick(findChild(root, "blurTarget"))
        compare(root.commits.length, 0)
    }

    function test_groups_and_value_refresh_preserve_draft_identity_data() {
        return [{tag: "smart", layout: "smart_groups"}, {tag: "accordion", layout: "accordion_cards"},
            {tag: "palette", layout: "palette"}]
    }

    function test_groups_and_value_refresh_preserve_draft_identity(data) {
        var root = makeHarness(data.layout)
        if (data.layout !== "palette")
            compare(findChild(root, "inspectorTextareaEditor"), null)
        openGroup(root, true)
        var editor = findChild(root, "inspectorTextareaEditor")
        verify(editor !== null)
        editor.forceActiveFocus()
        editor.text = "dirty draft"
        root.items = [Object.assign({}, root.items[0], {value: "external update"})]
        wait(0)
        compare(findChild(root, "inspectorTextareaEditor"), editor)
        compare(editor.text, "dirty draft")
        openGroup(root, false)
        openGroup(root, true)
        compare(findChild(root, "inspectorTextareaEditor"), editor)
        compare(editor.text, "dirty draft")
        compare(root.commits.length, 0)
        var apply = findChild(root, "inspectorTextareaApplyButton")
        verify(apply.visible && apply.enabled)
        apply.click()
        compare(root.commits[root.commits.length - 1].value, "dirty draft")
    }
}
