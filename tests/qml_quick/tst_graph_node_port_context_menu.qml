import QtQuick 2.15
import QtQuick.Controls 2.15
import QtTest 1.3
import "../../ea_node_editor/ui_qml/components/graph" as Graph

TestCase {
    id: testCase
    name: "GraphNodePortContextMenu"
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

    QtObject {
        id: sceneBridgeStub
        property var modifierCalls: []
        property var principalCalls: []
        property var insertCalls: []
        property var removeCalls: []

        function set_port_modifiers(nodeId, portKey, modifiers) {
            modifierCalls.push([String(nodeId), String(portKey), modifiers.slice()])
            return true
        }

        function set_principal_input_port(nodeId, portKey) {
            principalCalls.push([String(nodeId), String(portKey)])
            return true
        }

        function insert_dynamic_port(nodeId, groupId, ordinal) {
            insertCalls.push([String(nodeId), String(groupId), Number(ordinal)])
            return "inserted"
        }

        function remove_dynamic_port(nodeId, groupId, portKey) {
            removeCalls.push([String(nodeId), String(groupId), String(portKey)])
            return {"port_key": String(portKey)}
        }
    }

    QtObject {
        id: canvasItem
        property var sceneCommandBridge: sceneBridgeStub
    }

    Item {
        id: host
        property bool graphReadOnly: false
        property real floatingToolbarZoom: 1.0
        property var canvasItem: canvasItem
        property var inputPorts: []
        property var outputPorts: []
        property var settingsGroups: []
        property int nodeTextRenderType: Text.CurveRendering
        property var nodeData: ({
            "node_id": "node_menu_test",
            "collapsed": false,
            "locked": false,
            "locked_state": {},
            "dynamic_port_groups": []
        })

        function localPortPoint(direction, rowIndex) {
            return {"x": direction === "in" ? 0 : width, "y": 40 + rowIndex * 18}
        }

        function localPortPointForPort(direction, rowIndex, portData) {
            return localPortPoint(direction, rowIndex)
        }
    }

    Graph.GraphNodePortsLayer {
        id: portsLayer
        width: 360
        height: 260
        host: host
    }

    Graph.GraphNodePortContextMenu {
        id: menu
        portsLayer: portsLayer
    }

    function appendNamedObjects(item, matches) {
        if (!item)
            return
        if (String(item.objectName || "").length > 0)
            matches.push(item)
        var children = item.children || []
        for (var index = 0; index < children.length; ++index)
            appendNamedObjects(children[index], matches)
    }

    function namedMenuItems() {
        var items = []
        appendNamedObjects(menu.contentItem, items)
        return items.filter(function(item) {
            var name = String(item.objectName || "")
            return name.indexOf("graphNodePort") === 0
                || name.indexOf("graphNodeDynamicPort") === 0
        })
    }

    function itemByName(name) {
        var items = namedMenuItems()
        for (var index = 0; index < items.length; ++index) {
            if (String(items[index].objectName) === name)
                return items[index]
        }
        return null
    }

    function clickAction(name) {
        menu.openAt(testCase, 24, 36)
        tryCompare(menu, "opened", true)
        waitForRendering(menu.menuContent)
        var item = itemByName(name)
        verify(item !== null, name)
        mouseClick(item, item.width / 2, 15)
        tryCompare(menu, "visible", false)
    }

    function dynamicGroup() {
        return {
            "id": "inputs",
            "direction": "in",
            "port_keys": ["a", "b"],
            "can_insert": true,
            "removable_port_keys": ["a", "b"],
            "rename_mode": "label"
        }
    }

    function inputPort(key, modifiers, principal) {
        return {
            "key": key,
            "label": key.toUpperCase(),
            "direction": "in",
            "kind": "data",
            "data_access": "item",
            "modifiers": modifiers || [],
            "principal_eligible": true,
            "principal": Boolean(principal)
        }
    }

    function init() {
        menu.close()
        host.graphReadOnly = false
        sceneBridgeStub.modifierCalls = []
        sceneBridgeStub.principalCalls = []
        sceneBridgeStub.insertCalls = []
        sceneBridgeStub.removeCalls = []
        portsLayer.dynamicPortGroups = [dynamicGroup()]
        portsLayer.contextPortData = inputPort("a", ["graft", "clean"], false)
        wait(0)
    }

    function cleanup() {
        menu.close()
        wait(0)
    }

    function test_root_order_checks_and_open_close_stay_exact() {
        compare(menu.objectName, "graphNodePortContextMenu")
        verify(!menu.modal)
        menu.openAt(testCase, 24, 36)
        tryVerify(function() { return menu.visible && menu.opened })
        waitForRendering(menu.menuContent)
        compare(menu.x, 24)
        verify(menu.y >= 4)
        verify(menu.y + menu.height <= menu.parent.height - 4)
        var names = [menu.objectName]
        var items = namedMenuItems()
        for (var index = 0; index < items.length; ++index)
            names.push(String(items[index].objectName))
        compare(names.join(","), [
            "graphNodePortContextMenu",
            "graphNodePortAccessMetadata",
            "graphNodePortModifierGraft",
            "graphNodePortModifierFlatten",
            "graphNodePortModifierSimplify",
            "graphNodePortModifierReverse",
            "graphNodePortModifierClean",
            "graphNodePortPrincipal",
            "graphNodeDynamicPortInsertBefore",
            "graphNodeDynamicPortInsertAfter",
            "graphNodeDynamicPortRename",
            "graphNodeDynamicPortRemove"
        ].join(","))
        compare(itemByName("graphNodePortAccessMetadata").text, "Access: Item")
        verify(itemByName("graphNodePortModifierGraft").checked)
        verify(!itemByName("graphNodePortModifierFlatten").checked)
        verify(!itemByName("graphNodePortModifierSimplify").checked)
        verify(!itemByName("graphNodePortModifierReverse").checked)
        verify(itemByName("graphNodePortModifierClean").checked)
        verify(!itemByName("graphNodePortPrincipal").checked)
        menu.close()
        tryVerify(function() { return !menu.visible && !menu.opened })
    }

    function test_modifier_principal_and_dynamic_items_call_the_layer_owner() {
        clickAction("graphNodePortModifierFlatten")
        compare(sceneBridgeStub.modifierCalls.length, 1)
        compare(JSON.stringify(sceneBridgeStub.modifierCalls[0]), JSON.stringify([
            "node_menu_test",
            "a",
            ["graft", "clean", "flatten"]
        ]))

        clickAction("graphNodePortPrincipal")
        compare(sceneBridgeStub.principalCalls.length, 1)
        compare(JSON.stringify(sceneBridgeStub.principalCalls[0]), JSON.stringify([
            "node_menu_test",
            "a"
        ]))

        clickAction("graphNodeDynamicPortInsertBefore")
        clickAction("graphNodeDynamicPortInsertAfter")
        compare(JSON.stringify(sceneBridgeStub.insertCalls), JSON.stringify([
            ["node_menu_test", "inputs", 0],
            ["node_menu_test", "inputs", 1]
        ]))
        clickAction("graphNodeDynamicPortRename")
        compare(portsLayer.editingPortKey, "a")
        compare(portsLayer.editingPortDirection, "in")
        portsLayer.cancelPortLabelEdit()
        clickAction("graphNodeDynamicPortRemove")
        compare(JSON.stringify(sceneBridgeStub.removeCalls), JSON.stringify([
            ["node_menu_test", "inputs", "a"]
        ]))
    }

    function test_data_visibility_and_read_only_guards_stay_exact() {
        host.graphReadOnly = true
        wait(0)
        for (var name of [
            "graphNodePortModifierGraft",
            "graphNodePortModifierFlatten",
            "graphNodePortModifierSimplify",
            "graphNodePortModifierReverse",
            "graphNodePortModifierClean",
            "graphNodePortPrincipal",
            "graphNodeDynamicPortInsertBefore",
            "graphNodeDynamicPortInsertAfter",
            "graphNodeDynamicPortRename",
            "graphNodeDynamicPortRemove"
        ]) {
            verify(!itemByName(name).enabled, name)
        }

        portsLayer.contextPortData = {
            "key": "top",
            "direction": "neutral",
            "kind": "flow",
            "principal_eligible": false
        }
        wait(0)
        for (var hiddenName of [
            "graphNodePortAccessMetadata",
            "graphNodePortModifierGraft",
            "graphNodePortModifierFlatten",
            "graphNodePortModifierSimplify",
            "graphNodePortModifierReverse",
            "graphNodePortModifierClean",
            "graphNodePortPrincipal",
            "graphNodeDynamicPortInsertBefore",
            "graphNodeDynamicPortInsertAfter",
            "graphNodeDynamicPortRename",
            "graphNodeDynamicPortRemove"
        ]) {
            compare(itemByName(hiddenName), null, hiddenName)
        }
    }
}
