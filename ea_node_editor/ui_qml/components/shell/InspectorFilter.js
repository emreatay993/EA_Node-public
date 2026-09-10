.pragma library

function makePropMatcher(query, scope) {
    var q = (query === undefined || query === null ? "" : String(query)).trim().toLowerCase()
    if (q.length === 0)
        return function () { return true }

    function nameText(prop) {
        if (!prop)
            return ""
        var label = prop.label === undefined || prop.label === null ? "" : String(prop.label)
        var key = prop.key === undefined || prop.key === null ? "" : String(prop.key)
        return (label + " " + key).toLowerCase()
    }

    function valueText(prop) {
        if (!prop)
            return ""
        var v = prop.value
        if (v === undefined || v === null)
            return ""
        if (typeof v === "boolean")
            return v ? "enabled true on" : "disabled false off"
        return String(v).toLowerCase()
    }

    if (scope === "name")
        return function (prop) { return nameText(prop).indexOf(q) >= 0 }
    if (scope === "value")
        return function (prop) { return valueText(prop).indexOf(q) >= 0 }
    return function (prop) {
        return nameText(prop).indexOf(q) >= 0 || valueText(prop).indexOf(q) >= 0
    }
}

function groupPropertyItems(items) {
    var result = []
    var index = {}
    var list = items || []
    for (var i = 0; i < list.length; ++i) {
        var item = list[i]
        if (!item)
            continue
        var groupName = item.group === undefined || item.group === null ? "" : String(item.group)
        if (groupName.length === 0)
            groupName = "Properties"
        if (index[groupName] === undefined) {
            index[groupName] = result.length
            result.push({ name: groupName, items: [] })
        }
        result[index[groupName]].items.push(item)
    }
    return result
}

function smartGroups(items) {
    var list = items || []
    var modified = []
    var driven = []
    var required = []
    for (var i = 0; i < list.length; ++i) {
        var item = list[i]
        if (!item)
            continue
        if (item.dirty)
            modified.push(item)
        if (item.driven_by || item.overridden_by_input)
            driven.push(item)
        if (item.required)
            required.push(item)
    }
    var result = []
    if (modified.length > 0)
        result.push({ kind: "modified", label: "Modified", accent: "edge_warning", items: modified })
    if (driven.length > 0)
        result.push({ kind: "driven", label: "Driven", accent: "accent", items: driven })
    if (required.length > 0)
        result.push({ kind: "required", label: "Required", accent: "run_failed", items: required })
    return result
}
