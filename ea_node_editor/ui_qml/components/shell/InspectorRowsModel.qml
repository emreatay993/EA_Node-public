// Purpose: Preserve inspector delegate identity while projected row values change.
// Map: docs/agent_maps/subsystems/qml_shell_and_bridges.md
// Tests: tests/test_inspector_smart_groups_variant.py, tests/qml_quick/tst_inspector_lifecycle.qml
import QtQuick 2.15

ListModel {
    id: root
    property var rows: []
    property string keyRole: "key"
    property var rowsByKey: ({})

    function synchronize() {
        var source = root.rows || []
        var keys = []
        var values = Object.create(null)
        for (var i = 0; i < source.length; ++i) {
            var row = source[i]
            var key = row ? String(row[root.keyRole] || "") : ""
            if (!key.length || values[key] !== undefined)
                continue
            keys.push(key)
            values[key] = row
        }
        root.rowsByKey = values
        for (var target = 0; target < keys.length; ++target) {
            if (target < count && get(target).rowKey === keys[target])
                continue
            var found = -1
            for (var candidate = target + 1; candidate < count; ++candidate) {
                if (get(candidate).rowKey === keys[target]) {
                    found = candidate
                    break
                }
            }
            if (found >= 0)
                move(found, target, 1)
            else
                insert(target, {rowKey: keys[target]})
        }
        if (count > keys.length)
            remove(keys.length, count - keys.length)
    }

    onRowsChanged: synchronize()
    onKeyRoleChanged: synchronize()
    Component.onCompleted: synchronize()
}
