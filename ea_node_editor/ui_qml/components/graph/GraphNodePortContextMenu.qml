// Purpose: Own the standard graph-port access, modifier, and dynamic-action menu.
// Map: feature_routes/port_availability_and_default_values.md
// Tests: tests/qml_quick/tst_graph_node_port_context_menu.qml

import QtQuick 2.15
import "../shell" as Shell

Shell.ShellContextPopup {
    id: menu
    required property Item portsLayer
    readonly property var dynamicGroup: portsLayer._dynamicPortGroupForPort(portsLayer.contextPortData)
    objectName: "graphNodePortContextMenu"

    actions: {
        var layer = menu.portsLayer
        var port = layer.contextPortData
        var editable = !(layer.host && layer.host.graphReadOnly)
        var dataPort = layer._isDataPort(port)
        var group = menu.dynamicGroup
        var dynamicEditable = layer._dynamicPortAuthoringAllowed()
        var items = [{
            objectName: "graphNodePortAccessMetadata", actionId: "access",
            text: "Access: " + layer._dataAccessLabel(port), visible: dataPort, enabled: false
        }]
        var modifiers = ["Graft", "Flatten", "Simplify", "Reverse", "Clean"]
        for (var i = 0; i < modifiers.length; ++i) {
            var modifier = modifiers[i].toLowerCase()
            items.push({
                objectName: "graphNodePortModifier" + modifiers[i], actionId: modifier,
                text: modifiers[i], visible: dataPort, enabled: editable,
                checkable: true, checked: layer._modifierChecked(modifier)
            })
        }
        return items.concat([
            {
                objectName: "graphNodePortPrincipal", actionId: "principal", text: "Principal",
                visible: Boolean(port && port.principal_eligible), enabled: editable,
                checkable: true, checked: Boolean(port && port.principal)
            },
            {
                objectName: "graphNodeDynamicPortInsertBefore", actionId: "insert_before", text: "Insert Before",
                visible: group !== null && Boolean(group.can_insert), enabled: dynamicEditable
            },
            {
                objectName: "graphNodeDynamicPortInsertAfter", actionId: "insert_after", text: "Insert After",
                visible: group !== null && Boolean(group.can_insert), enabled: dynamicEditable
            },
            {
                objectName: "graphNodeDynamicPortRename", actionId: "rename", text: "Rename",
                visible: group !== null && String(group.rename_mode || "none").trim().toLowerCase() !== "none",
                enabled: dynamicEditable
            },
            {
                objectName: "graphNodeDynamicPortRemove", actionId: "remove", text: "Remove",
                visible: group !== null && layer._dynamicPortCanRemove(port), enabled: dynamicEditable
            }
        ])
    }

    onActionTriggered: function(actionId) {
        var layer = menu.portsLayer
        if (["graft", "flatten", "simplify", "reverse", "clean"].indexOf(actionId) >= 0) {
            layer._togglePortModifier(actionId)
        } else if (actionId === "principal") {
            layer._togglePrincipal()
        } else if (menu.dynamicGroup !== null) {
            var group = menu.dynamicGroup
            var key = layer._portKey(layer.contextPortData)
            if (actionId === "insert_before" || actionId === "insert_after") {
                var ordinal = layer._dynamicPortOrdinal(group, key)
                if (ordinal >= 0)
                    layer._insertDynamicPort(group.id, ordinal + (actionId === "insert_after" ? 1 : 0))
            } else if (actionId === "rename") {
                layer.beginPortLabelEdit(key, String(group.direction || ""))
            } else if (actionId === "remove") {
                layer._removeDynamicPort(group.id, key)
            }
        }
    }
}
