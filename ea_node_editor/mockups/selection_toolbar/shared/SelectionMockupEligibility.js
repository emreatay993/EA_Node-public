.pragma library

var ALIGN_ACTIONS = ["align_left", "align_right", "align_top", "align_bottom"];
var DISTRIBUTE_ACTIONS = ["distribute_h", "distribute_v"];

function stateLabel(sampleState) {
    var state = String(sampleState || "");
    if (state === "two_nodes")
        return "2 nodes";
    if (state === "one_node")
        return "1 node";
    if (state === "mixed")
        return "mixed / ineligible";
    return "3 nodes + internal edge";
}

function selectedNodeIds(sampleState) {
    var state = String(sampleState || "");
    if (state === "two_nodes")
        return ["source", "process"];
    if (state === "one_node")
        return ["process"];
    if (state === "mixed")
        return ["source", "note", "locked"];
    return ["source", "process", "output"];
}

function selectedCount(sampleState) {
    return selectedNodeIds(sampleState).length;
}

function hasInternalConnection(sampleState) {
    var state = String(sampleState || "");
    return state === "rich" || state === "two_nodes" || state === "";
}

function isMixedIneligible(sampleState) {
    return String(sampleState || "") === "mixed";
}

function actionEnabled(actionId, sampleState) {
    if (isMixedIneligible(sampleState))
        return false;
    var count = selectedCount(sampleState);
    var action = String(actionId || "");
    if (ALIGN_ACTIONS.indexOf(action) >= 0)
        return count >= 2;
    if (DISTRIBUTE_ACTIONS.indexOf(action) >= 0)
        return count >= 3;
    if (action === "straighten")
        return count >= 2 && hasInternalConnection(sampleState);
    if (action === "wrap_comment")
        return count >= 2;
    if (action === "more" || action === "focus")
        return count > 0;
    return false;
}

function actionSummary(sampleState) {
    var enabled = [];
    var actions = [
        ["align_left", "Align"],
        ["distribute_h", "Distribute"],
        ["straighten", "Straighten"],
        ["wrap_comment", "Wrap"]
    ];
    for (var i = 0; i < actions.length; i++) {
        if (actionEnabled(actions[i][0], sampleState))
            enabled.push(actions[i][1]);
    }
    return enabled.length ? enabled.join(", ") : "No eligible actions";
}
