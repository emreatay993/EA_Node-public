import QtQuick 2.15
import QtQuick.Controls 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/shell" as Shell
import "../../ea_node_editor/ui_qml/components/graph/surface_controls" as Surface

TestCase {
    id: tests
    name: "SignalSelectors"
    width: 700
    height: 500
    visible: true
    when: windowShown
    property var uiIcons: icons
    property var themeBridge: theme
    QtObject {
        id: icons
        function has(name) { return false; }
        function sourceSized(name, size, color) { return ""; }
        function label(name) { return name; }
    }
    QtObject { id: theme; property var palette: ({}) }

    Component {
        id: harnessComponent
        Item {
            id: harness
            width: 680
            height: 450
            property var commits: []
            property var inlineCommits: []
            property var item: ({"key": "x_column", "label": "X column", "type": "json", "value": 0,
                "display_value": 0, "display_value_available": true, "editor_enabled": true,
                "editor_mode": "editable_combo", "exact_selectors": true, "enum_values": [], "enum_codes": []})
            property var themePalette: ({"input_bg": "#222222", "input_fg": "#ffffff", "input_border": "#555555",
                "accent": "#5599ee", "panel_title_fg": "#ffffff", "group_title_fg": "#ffffff", "muted_fg": "#888888",
                "inspector_danger_fg": "#ff6666", "inspector_danger_border": "#ff4444"})
            property color selectedSurfaceColor: "#335577"
            property color cardBackgroundColor: "#222222"
            property bool isPinInspector: false
            property var pinDataTypeOptions: []
            property var inspectorBridgeRef: bridge
            property alias inlineControl: inlineControl
            property alias listControl: listControl
            QtObject {
                id: bridge
                function set_selected_node_property(key, value) {
                    harness.commits = harness.commits.concat([{"key": key, "value": value}]);
                }
            }
            Shell.InspectorPropertyEditor {
                id: inspector
                width: 280
                pane: harness
                propertyItem: harness.item
            }
            Surface.GraphSurfaceSearchableComboBox {
                id: inlineControl
                x: 320
                y: 25
                width: 280
                height: 32
                exactSelectors: true
                selectedValue: 0
                onValueActivated: function(value) {
                    harness.inlineCommits = harness.inlineCommits.concat([value]);
                }
            }
            Surface.GraphSurfaceListEditor {
                id: listControl
                x: 320
                y: 90
                width: 280
                height: 180
                exactSelectors: true
                values: [0, " Exact ", 1]
                enumValues: ["Column 1", " Exact ", "Column 2"]
                enumCodes: [0, " Exact ", 1]
            }
            Button { objectName: "blurTarget"; x: 10; y: 370; text: "Other control" }
        }
    }

    function makeHarness() {
        var result = createTemporaryObject(harnessComponent, tests);
        verify(result !== null);
        wait(0);
        return result;
    }

    function test_inspector_position_survives_enter_blur_and_schema_expiry() {
        var root = makeHarness();
        var selector = findChild(root, "inspectorEditableComboEditor");
        compare(selector.editText, "Column 1");
        mouseClick(selector, 20, selector.height / 2);
        keyClick(Qt.Key_Return);
        compare(root.commits[root.commits.length - 1].value, 0);
        mouseClick(findChild(root, "blurTarget"));
        compare(root.commits[root.commits.length - 1].value, 0);
        root.item = Object.assign({}, root.item, {"enum_values": ["time"], "enum_codes": [0]});
        compare(selector.editText, "time");
        mouseClick(selector, 20, selector.height / 2);
        root.item = Object.assign({}, root.item, {"enum_values": [], "enum_codes": []});
        mouseClick(findChild(root, "blurTarget"));
        compare(root.commits[root.commits.length - 1].value, 0);
    }

    function test_authored_exact_names_survive_focused_schema_refresh() {
        var root = makeHarness();
        var selector = findChild(root, "inspectorEditableComboEditor");
        mouseClick(selector, 20, selector.height / 2);
        selector.editText = " Column 1 ";
        root.item = Object.assign({}, root.item, {"enum_values": ["Column 1"], "enum_codes": [0]});
        keyClick(Qt.Key_Return);
        compare(root.commits[root.commits.length - 1].value, " Column 1 ");
    }

    function test_inline_position_and_typed_names_remain_distinct() {
        var root = makeHarness();
        var selector = root.inlineControl;
        compare(selector.editText, "Column 1");
        mouseClick(selector, 20, selector.height / 2);
        keyClick(Qt.Key_Return);
        compare(root.inlineCommits[0], 0);
        selector.editText = "Column 2";
        keyClick(Qt.Key_Return);
        compare(root.inlineCommits[1], "Column 2");
        selector.model = ["Column 1", "Column 2"];
        selector.optionCodes = [0, 1];
        selector.editText = "Column 2";
        wait(0);
        mouseClick(selector, 20, selector.height / 2);
        keyClick(Qt.Key_Down);
        wait(0);
        keyClick(Qt.Key_Return);
        compare(root.inlineCommits[root.inlineCommits.length - 1], 1);
        var values = root.listControl.snapshot();
        compare(values[0], 0);
        compare(typeof values[0], "number");
        compare(values[1], " Exact ");
        compare(values[2], 1);
    }

    function test_connected_y_uses_display_values_and_disables_edits() {
        var root = makeHarness();
        root.item = {"key": "y_columns", "label": "Y columns", "type": "json", "value": ["authored"],
            "display_value": null, "display_value_available": false, "editor_enabled": false,
            "overridden_by_input": true, "editor_mode": "chip_list", "exact_selectors": true};
        var chips = findChild(root, "inspectorChipListContainer");
        compare(chips.chipValues.length, 0);
        verify(!findChild(root, "inspectorChipListEditor").enabled);
        root.item = Object.assign({}, root.item, {"display_value_available": true, "display_value": [0, "Current"]});
        compare(chips.chipValues[0], 0);
        compare(chips.chipValues[1], "Current");
    }

    function test_shared_filter_ranks_unicode_and_caps_after_filtering() {
        var root = makeHarness();
        var values = [];
        for (var index = 0; index < 80; ++index)
            values.push("Result " + String(index));
        values.push("RÉSULTAT exact");
        root.item = Object.assign({}, root.item, {"enum_values": values, "enum_codes": values});
        var inspector = findChild(root, "inspectorEditableComboEditor");
        inspector.editText = "résultat";
        compare(inspector.filteredOptions.length, 1);
        compare(inspector.filteredOptions[0].value, "RÉSULTAT exact");
        inspector.editText = "result";
        compare(inspector.filteredOptions.length, 50);

        root.inlineControl.model = values;
        root.inlineControl.optionCodes = values;
        root.inlineControl.editText = "résultat";
        compare(root.inlineControl.filteredOptions.length, 1);
        root.inlineControl.editText = "result";
        compare(root.inlineControl.filteredOptions.length, 50);
    }
}
