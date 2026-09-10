import QtQuick 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph/GraphActionPresentation.js" as Presentation

TestCase {
    name: "GraphActionPresentation"

    function ids(actions) {
        var result = []
        for (var index = 0; index < actions.length; ++index)
            result.push(String(actions[index].id || actions[index].actionId || ""))
        return result
    }

    function test_descriptor_lookup_is_stable_and_null_safe() {
        var descriptors = {
            "run": {"actionId": "run_selected", "payload": "node"},
            "remove": {"actionId": "remove_node", "payload": "node"}
        }
        compare(Presentation.descriptorActionId(descriptors, "run"), "run_selected")
        compare(Presentation.descriptorActionId(descriptors, "missing"), "")
        compare(Presentation.descriptorForActionId(descriptors, "remove_node").payload, "node")
        compare(Presentation.descriptorForActionId(descriptors, "missing"), null)
    }

    function test_edge_normalization_and_choices_are_exact() {
        compare(JSON.stringify(["", " PIPE ", "bezier", "curve"].map(
            Presentation.normalizeEdgePathMode
        )), JSON.stringify(["auto", "pipe", "bezier", "auto"]))
        compare(JSON.stringify(["", " FAINT ", "hidden", "ghost"].map(
            Presentation.normalizeEdgeDisplayMode
        )), JSON.stringify(["default", "faint", "hidden", "default"]))
        compare(JSON.stringify(Presentation.edgePathChoices()), JSON.stringify([
            {"label": "Auto", "value": "auto"},
            {"label": "Pipe", "value": "pipe"},
            {"label": "Bezier", "value": "bezier"}
        ]))
        compare(JSON.stringify(Presentation.edgeDisplayChoices()), JSON.stringify([
            {"label": "Default", "value": "default"},
            {"label": "Faint", "value": "faint"},
            {"label": "Hidden", "value": "hidden"}
        ]))
    }

    function test_edge_menu_models_preserve_order_and_state() {
        var paths = Presentation.edgePathMenuActions("pipe")
        compare(ids(paths).join(","), "edge_path_mode:auto,edge_path_mode:pipe,edge_path_mode:bezier")
        compare(JSON.stringify(paths.map(function(item) { return item.enabled })), JSON.stringify([
            true, false, true
        ]))
        var displays = Presentation.edgeDisplayMenuActions("faint")
        compare(ids(displays).join(","), "edge_display_mode:default,edge_display_mode:faint,edge_display_mode:hidden")
        compare(JSON.stringify(displays.map(function(item) { return item.checked })), JSON.stringify([
            false, true, false
        ]))
        compare(Presentation.commonEdgeDisplayMode([]), "")
        compare(Presentation.edgeDisplayModeLabel(""), "Mixed")
        compare(Presentation.commonEdgeDisplayMode([
            {"visual_style": {"display_mode": "faint"}},
            {"visual_style": {"display_mode": "hidden"}}
        ]), "")
    }

    function test_edge_toolbar_model_uses_resolved_facts_only() {
        var actions = Presentation.edgeToolbarActions({
            "edgePayload": {"enabled": false},
            "activeDataWire": true,
            "flowEdgeActive": true,
            "displayMode": "faint",
            "hasLabel": false
        })
        compare(ids(actions).join(","), [
            "toggle_edge_enabled", "remove_edge", "path_mode", "frame_edge",
            "display_mode", "edge_color", "clear_flow_edge_label",
            "edit_flow_edge_label", "stroke_pattern", "arrow_head",
            "edit_flow_edge_style"
        ].join(","))
        compare(actions[0].label, "Enable connection")
        verify(!actions[0].checked)
        compare(actions[4].label, "Display mode: Faint")
        verify(!actions[6].enabled)

        var emptyFactsActions = Presentation.edgeToolbarActions({})
        compare(ids(emptyFactsActions).join(","), "toggle_edge_enabled,remove_edge,path_mode,frame_edge")
        compare(emptyFactsActions[0].label, "Disable connection")
        verify(!emptyFactsActions[0].checked)
    }

    function test_used_action_field_helpers_and_child_extraction_preserve_presentation() {
        var action = {
            "id": "font_family",
            "label": "Font family",
            "description": "Choose font",
            "toolbar_text": "Segoe UI",
            "enabled": false,
            "checked": true,
            "menuActions": [{"id": "child"}]
        }
        compare(Presentation.actionToolbarText(action), "Segoe UI")
        compare(Presentation.actionTooltipText(action), "Font family\nChoose font")
        compare(Presentation.actionToolbarIcon(action), "")
        verify(!Presentation.actionIconOnly(action))
        verify(Presentation.actionChecked(action))
        compare(Presentation.childActions(action, "menuActions")[0].id, "child")

        var fontSizeAction = {"label": "Text size", "toolbar_text": "24"}
        compare(Presentation.actionToolbarText(fontSizeAction), "24")
        compare(Presentation.actionToolbarIcon(fontSizeAction), "")
        verify(!Presentation.actionIconOnly(fontSizeAction))

        var pdfAction = {"label": "Navigate", "icon": "navigate"}
        compare(Presentation.actionToolbarText(pdfAction), "Navigate")
        compare(Presentation.actionToolbarIcon(pdfAction), "navigate")
        verify(Presentation.actionIconOnly(pdfAction))
    }

    function test_order_filter_checked_and_menu_projection_are_stable() {
        var actions = [
            {"id": "rename", "label": "Rename", "kind": "common"},
            {"id": "align", "label": "Align left", "kind": "surface"},
            {"id": "alpha", "label": "Alpha", "kind": "surface", "checked": true}
        ]
        compare(ids(Presentation.orderNodeToolbarActions(actions, false)).join(","), "rename,align,alpha")
        compare(ids(Presentation.orderNodeToolbarActions(actions, true)).join(","), "align,alpha,rename")
        compare(ids(Presentation.filterActions(actions, "alpha")).join(","), "alpha")
        compare(Presentation.checkedActionIndex(actions), 2)
        compare(Presentation.boundedActionAt(actions, 99).id, "alpha")
        compare(JSON.stringify(Presentation.menuModel([
            {"id": "run", "label": "Run", "enabled": false, "destructive": true}
        ])), JSON.stringify([
            {"actionId": "run", "text": "Run", "enabled": false, "visible": true, "destructive": true}
        ]))
    }

    function test_node_builders_preserve_normal_path_and_lock_orders() {
        var context = Presentation.nodeContextActions({
            "canEnterScope": true,
            "pathPointer": {"enabled": true, "isFolder": true}
        })
        compare(ids(context).join(","), "open_subnode_scope,open_node_path_menu")
        var pathChildren = Presentation.childActions(context[1], "popoverActions")
        compare(ids(pathChildren).join(","), "open_node_path,open_node_path_with")
        verify(!pathChildren[1].enabled)

        var common = Presentation.nodeCommonActions({
            "runnable": true,
            "graphReadOnly": false,
            "lockEligible": true,
            "authorLocked": false,
            "collapsible": true,
            "collapsed": false
        })
        compare(ids(common).join(","), "frame_node,run_selected,toggle_node_lock,toggle_node_collapsed,rename_node,duplicate_node,remove_node")
        compare(ids(Presentation.childActions(common[1], "menuActions")).join(","), "preview_selected_run,open_selected_run_settings")
        compare(common[1].menu_icon, "settings")
        compare(common[1].icon, "node-run")
        compare(common[3].label, "Collapse")
        compare(common[3].icon, "node-collapse")

        var collapsed = Presentation.nodeCommonActions({
            "runnable": false,
            "graphReadOnly": false,
            "lockEligible": false,
            "authorLocked": false,
            "collapsible": true,
            "collapsed": true
        })
        compare(ids(collapsed).join(","), "frame_node,toggle_node_collapsed,rename_node,duplicate_node,remove_node")
        compare(collapsed[1].label, "Expand")
        compare(collapsed[1].icon, "node-expand")
        var locked = Presentation.nodeCommonActions({
            "runnable": false,
            "graphReadOnly": false,
            "lockEligible": true,
            "authorLocked": true
        })
        compare(ids(locked).join(","), "frame_node,toggle_node_lock")
    }

    function test_available_actions_preserve_panel_and_author_lock_rules() {
        var context = [{"id": "context"}]
        var surface = [{"id": "surface"}]
        var common = [{"id": "common"}]
        compare(ids(Presentation.nodeAvailableActions({
            "contextActions": context,
            "surfaceActions": surface,
            "commonActions": common,
            "panelSurface": false,
            "authorLocked": false
        })).join(","), "context,surface,common")
        compare(ids(Presentation.nodeAvailableActions({
            "contextActions": context,
            "surfaceActions": surface,
            "commonActions": common,
            "panelSurface": true,
            "authorLocked": false
        })).join(","), "surface")
        compare(ids(Presentation.nodeAvailableActions({
            "contextActions": context,
            "surfaceActions": surface,
            "commonActions": common,
            "panelSurface": false,
            "authorLocked": true
        })).join(","), "common")
    }
}
