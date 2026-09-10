.pragma library
// Purpose: Shape authoritative graph-action DTOs for QML menus and toolbars.
// Map: feature_routes/graph_actions_and_context_menus.md
// Tests: tests/qml_quick/tst_graph_action_presentation.qml

function toArray(value) {
    if (Array.isArray(value))
        return value;
    if (!value || value.length === undefined)
        return [];
    var result = [];
    for (var index = 0; index < value.length; ++index)
        result.push(value[index]);
    return result;
}

function descriptorActionId(descriptors, key) {
    var descriptor = descriptors ? descriptors[key] : null;
    return descriptor ? String(descriptor.actionId || "") : "";
}

function descriptorForActionId(descriptors, actionId) {
    var normalized = String(actionId || "").trim();
    if (!normalized || !descriptors)
        return null;
    for (var key in descriptors) {
        if (!Object.prototype.hasOwnProperty.call(descriptors, key))
            continue;
        var descriptor = descriptors[key];
        if (descriptor && String(descriptor.actionId || "") === normalized)
            return descriptor;
    }
    return null;
}

function normalizeEdgePathMode(value) {
    var normalized = String(value || "").trim().toLowerCase();
    return normalized === "pipe" || normalized === "bezier" ? normalized : "auto";
}

function normalizeEdgeDisplayMode(value) {
    var normalized = String(value || "").trim().toLowerCase();
    return normalized === "faint" || normalized === "hidden" ? normalized : "default";
}

function edgePathChoices() {
    return [
        {"label": "Auto", "value": "auto"},
        {"label": "Pipe", "value": "pipe"},
        {"label": "Bezier", "value": "bezier"}
    ];
}

function edgeDisplayChoices() {
    return [
        {"label": "Default", "value": "default"},
        {"label": "Faint", "value": "faint"},
        {"label": "Hidden", "value": "hidden"}
    ];
}

function edgePathMenuActions(currentMode) {
    var current = normalizeEdgePathMode(currentMode);
    var choices = edgePathChoices();
    var actions = [];
    for (var index = 0; index < choices.length; ++index) {
        var choice = choices[index];
        actions.push({
            "actionId": "edge_path_mode:" + choice.value,
            "text": "Path: " + choice.label,
            "enabled": current !== choice.value
        });
    }
    return actions;
}

function edgeContextMenuActions(baseActions, currentMode, removeAction) {
    return toArray(baseActions)
        .concat(edgePathMenuActions(currentMode))
        .concat([removeAction || {}]);
}

function edgeDisplayMenuActions(currentMode) {
    var current = String(currentMode || "").trim().toLowerCase();
    var choices = edgeDisplayChoices();
    var actions = [];
    for (var index = 0; index < choices.length; ++index) {
        var choice = choices[index];
        actions.push({
            "actionId": "edge_display_mode:" + choice.value,
            "text": choice.label,
            "checked": current === choice.value
        });
    }
    return actions;
}

function commonEdgeDisplayMode(edgePayloads) {
    var payloads = toArray(edgePayloads);
    var current = "";
    for (var index = 0; index < payloads.length; ++index) {
        var payload = payloads[index] || {};
        var style = payload.visual_style || {};
        var mode = normalizeEdgeDisplayMode(style.display_mode);
        if (!current)
            current = mode;
        else if (current !== mode)
            return "";
    }
    return current;
}

function edgeDisplayModeLabel(value) {
    var normalized = String(value || "").trim().toLowerCase();
    if (!normalized)
        return "Mixed";
    var mode = normalizeEdgeDisplayMode(normalized);
    return mode.charAt(0).toUpperCase() + mode.slice(1);
}

function edgeToolbarActions(facts) {
    var source = facts || {};
    var payload = source.edgePayload || {};
    var actions = [
        {
            "id": "toggle_edge_enabled",
            "label": payload.enabled === false ? "Enable connection" : "Disable connection",
            "icon": "check",
            "checked": Boolean(source.edgePayload) && payload.enabled !== false
        },
        {"id": "remove_edge", "label": "Remove", "icon": "delete", "destructive": true},
        {"id": "path_mode", "label": "Path mode", "icon": "path-style", "popover": "path_mode"},
        {"id": "frame_edge", "label": "Zoom to selection", "icon": "zoom-fit"}
    ];
    if (Boolean(source.activeDataWire)) {
        actions.push({
            "id": "display_mode",
            "label": "Display mode: " + edgeDisplayModeLabel(source.displayMode),
            "icon": "palette",
            "popover": "display_mode"
        });
    }
    if (Boolean(source.flowEdgeActive)) {
        actions.push(
            {"id": "edge_color", "label": "Set color", "icon": "palette", "popover": "color"},
            {"id": "clear_flow_edge_label", "label": "Remove label", "icon": "label-off", "enabled": Boolean(source.hasLabel)},
            {"id": "edit_flow_edge_label", "label": "Edit label", "icon": "edit"},
            {"id": "stroke_pattern", "label": "Line pattern", "icon": "path-style", "popover": "pattern"},
            {"id": "arrow_head", "label": "Arrow style", "icon": "arrow-right", "popover": "arrow"},
            {"id": "edit_flow_edge_style", "label": "More settings", "icon": "more"}
        );
    }
    return actions;
}

function nodeContextActions(facts) {
    var source = facts || {};
    var actions = [];
    if (Boolean(source.canEnterScope)) {
        actions.push({
            "id": "open_subnode_scope", "label": "Enter Subnode", "icon": "door-enter",
            "kind": "scope", "enabled": true, "primary": false
        });
    }
    var pathPointer = source.pathPointer || null;
    if (pathPointer) {
        actions.push({
            "id": "open_node_path_menu", "label": "Open", "icon": "external-link",
            "kind": "context", "enabled": Boolean(pathPointer.enabled), "primary": false,
            "popover_layout": "row",
            "popoverActions": [
                {"id": "open_node_path", "label": "Open", "kind": "context", "toolbar_text": "Open", "close_popover": true},
                {"id": "open_node_path_with", "label": "Open with...", "kind": "context", "toolbar_text": "Open with...", "close_popover": true, "enabled": !Boolean(pathPointer.isFolder)}
            ]
        });
    }
    return actions;
}

function nodeCommonActions(facts) {
    var source = facts || {};
    var actions = [
        {"id": "frame_node", "label": "Zoom to node", "icon": "zoom-fit", "kind": "common", "enabled": true, "primary": false}
    ];
    if (Boolean(source.runnable)) {
        actions.push({
            "id": "run_selected", "label": "Run", "icon": "node-run", "kind": "common",
            "enabled": true, "primary": true,
            "menu_icon": "settings",
            "menuActions": [
                {"id": "preview_selected_run", "label": "Preview Run"},
                {"id": "open_selected_run_settings", "label": "Run Settings..."}
            ]
        });
    }
    if (Boolean(source.graphReadOnly)) {
        if (Boolean(source.lockedPlaceholderActive)) {
            actions.push({
                "id": "open_addon_manager_for_node", "label": "Load...", "icon": "open-session",
                "kind": "common", "enabled": Boolean(source.lockedPlaceholderManagerAvailable),
                "primary": true
            });
        }
        return actions;
    }
    if (Boolean(source.lockEligible)) {
        actions.push({
            "id": "toggle_node_lock", "label": Boolean(source.authorLocked) ? "Unlock" : "Lock",
            "icon": "lock", "kind": "common", "checked": Boolean(source.authorLocked),
            "enabled": true, "primary": false
        });
    }
    if (Boolean(source.authorLocked))
        return actions;
    if (Boolean(source.collapsible)) {
        var collapsed = Boolean(source.collapsed);
        actions.push({
            "id": "toggle_node_collapsed", "label": collapsed ? "Expand" : "Collapse",
            "icon": collapsed ? "node-expand" : "node-collapse",
            "kind": "common", "enabled": true, "primary": false
        });
    }
    actions.push(
        {"id": "rename_node", "label": "Rename", "icon": "edit", "kind": "common", "enabled": true, "primary": false},
        {"id": "duplicate_node", "label": "Duplicate", "icon": "duplicate", "kind": "common", "enabled": true, "primary": false},
        {"id": "remove_node", "label": "Delete", "icon": "delete", "kind": "common", "enabled": true, "primary": false, "destructive": true}
    );
    return actions;
}

function nodeAvailableActions(facts) {
    var source = facts || {};
    var context = toArray(source.contextActions);
    var surface = toArray(source.surfaceActions);
    var common = toArray(source.commonActions);
    if (Boolean(source.panelSurface))
        return surface;
    if (Boolean(source.authorLocked))
        return common;
    return context.concat(surface).concat(common);
}

function findAction(actions, actionId) {
    var values = toArray(actions);
    var normalized = String(actionId || "");
    for (var index = 0; index < values.length; ++index) {
        var action = values[index] || {};
        if (String(action.id || action.actionId || "") === normalized)
            return action;
    }
    return null;
}

function actionChecked(action) {
    return Boolean((action || {}).checked);
}

function actionToolbarText(action) {
    var item = action || {};
    var toolbarText = String(item.toolbar_text !== undefined ? item.toolbar_text : "");
    return toolbarText.length ? toolbarText : String(item.label || "");
}

function actionTooltipText(action) {
    var item = action || {};
    var label = String(item.label || "");
    var description = String(item.description || "");
    return description.length ? label + "\n" + description : label;
}

function actionToolbarIcon(action) {
    var item = action || {};
    var toolbarText = String(item.toolbar_text !== undefined ? item.toolbar_text : "");
    if (toolbarText.length && !String(item.icon || "").length)
        return "";
    return String(item.icon || "");
}

function actionIconOnly(action) {
    var item = action || {};
    return !String(item.toolbar_text !== undefined ? item.toolbar_text : "").length;
}

function actionLabels(actions) {
    var values = toArray(actions);
    var labels = [];
    for (var index = 0; index < values.length; ++index)
        labels.push(actionToolbarText(values[index]));
    return labels;
}

function boundedActionAt(actions, index) {
    var values = toArray(actions);
    if (!values.length)
        return null;
    var bounded = Math.max(0, Math.min(values.length - 1, Math.round(Number(index || 0))));
    return values[bounded] || null;
}

function childActions(action, fieldName) {
    var item = action || {};
    return toArray(item[String(fieldName || "")]);
}

function orderNodeToolbarActions(actions, groupBySurfaceFamily) {
    var values = toArray(actions);
    if (!groupBySurfaceFamily)
        return values;
    var surface = [];
    var common = [];
    for (var index = 0; index < values.length; ++index) {
        var item = values[index] || {};
        if (String(item.kind || "") === "common")
            common.push(item);
        else
            surface.push(item);
    }
    return surface.concat(common);
}

function filterActions(actions, query) {
    var values = toArray(actions);
    var filter = String(query || "").trim().toLowerCase();
    if (!filter)
        return values;
    var exact = [];
    var prefix = [];
    var contains = [];
    for (var index = 0; index < values.length; ++index) {
        var action = values[index] || {};
        var label = String(action.label || action.toolbar_text || "").toLowerCase();
        if (label === filter)
            exact.push(action);
        else if (label.indexOf(filter) === 0)
            prefix.push(action);
        else if (label.indexOf(filter) >= 0)
            contains.push(action);
    }
    return exact.concat(prefix, contains);
}

function checkedActionIndex(actions) {
    var values = toArray(actions);
    for (var index = 0; index < values.length; ++index) {
        if (Boolean((values[index] || {}).checked))
            return index;
    }
    return values.length ? 0 : -1;
}

function menuModel(actions) {
    var values = toArray(actions);
    var result = [];
    for (var index = 0; index < values.length; ++index) {
        var item = values[index] || {};
        result.push({
            "actionId": String(item.actionId || item.id || ""),
            "text": String(item.text || item.label || ""),
            "enabled": item.enabled !== false,
            "visible": item.visible !== false,
            "destructive": Boolean(item.destructive)
        });
    }
    return result;
}
