.pragma library

function toEditorText(item) {
    if (!item)
        return ""
    if (item.type === "json") {
        try {
            return JSON.stringify(item.value)
        } catch (error) {
            return ""
        }
    }
    if (item.value === undefined || item.value === null)
        return ""
    return String(item.value)
}

function comboOptionValue(model, index) {
    if (!model || index < 0 || index >= model.length)
        return ""
    var entry = model[index]
    if (!entry || entry.value === undefined || entry.value === null)
        return ""
    return String(entry.value)
}

function lineNumbersText(lineCount) {
    var count = Math.max(1, Number(lineCount) || 1)
    var lines = ""
    for (var i = 1; i <= count; i++) {
        lines += i
        if (i < count)
            lines += "\n"
    }
    return lines
}
