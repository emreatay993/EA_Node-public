.pragma library

var tools = [
    { "toolId": "select", "icon": "select", "label": "Select", "panelKind": "selection", "implemented": false },
    // Opens a floating writing-tools toolbar (Pen, Pencil, Highlighter, ...).
    { "toolId": "pen", "icon": "pen", "label": "Writing Tools", "panelKind": "writingTools", "implemented": false },
    // Opens a floating eraser-options toolbar (type, sizes, eraser settings).
    { "toolId": "eraser", "icon": "eraser", "label": "Eraser", "panelKind": "erase", "implemented": false },
    { "toolId": "text", "icon": "text", "label": "Text", "panelKind": "text", "implemented": false },
    { "toolId": "sticker", "icon": "sticker", "label": "Sticker", "panelKind": "stickers", "implemented": false },
    { "toolId": "image", "icon": "image", "label": "Image", "panelKind": "media", "implemented": false },
    { "toolId": "shapes", "icon": "shapes", "label": "Shapes", "panelKind": "shapes", "implemented": false },
    { "toolId": "note", "icon": "note", "label": "Note", "panelKind": "note", "implemented": false },
    { "toolId": "laser", "icon": "laser", "label": "Laser pointer", "panelKind": "laser", "implemented": true, "separatorBefore": true },
    { "toolId": "more", "icon": "chevron", "label": "More", "panelKind": "more", "implemented": false }
];

var contextActions = {
    "selection": [
        { "actionId": "select_lasso", "label": "Lasso", "enabled": false },
        { "actionId": "select_box", "label": "Box select", "enabled": false }
    ],
    "writingTools": [
        { "actionId": "writing_black", "label": "Black", "enabled": false },
        { "actionId": "writing_red", "label": "Red", "enabled": false },
        { "actionId": "writing_width", "label": "Width", "enabled": false }
    ],
    "text": [
        { "actionId": "text_size", "label": "Size", "enabled": false },
        { "actionId": "text_color", "label": "Color", "enabled": false }
    ],
    "stickers": [
        { "actionId": "sticker_recent", "label": "Recent", "enabled": false },
        { "actionId": "sticker_reactions", "label": "Reactions", "enabled": false }
    ],
    "media": [
        { "actionId": "image_file", "label": "File", "enabled": false },
        { "actionId": "image_clipboard", "label": "Clipboard", "enabled": false }
    ],
    "shapes": [
        { "actionId": "shape_rect", "label": "Rect", "enabled": false },
        { "actionId": "shape_circle", "label": "Circle", "enabled": false },
        { "actionId": "shape_arrow", "label": "Arrow", "enabled": false }
    ],
    "note": [
        { "actionId": "note_sticky", "label": "Sticky", "enabled": false },
        { "actionId": "note_comment", "label": "Comment", "enabled": false }
    ],
    "laser": [
        { "actionId": "laser_line", "label": "Line", "enabled": true },
        { "actionId": "laser_dot", "label": "Dot", "enabled": true },
        { "actionId": "laser_clear", "label": "Clear", "enabled": true }
    ],
    "more": [
        { "actionId": "more_tools", "label": "More tools", "enabled": false }
    ]
};

function labelFor(toolId) {
    var id = String(toolId || "");
    for (var i = 0; i < tools.length; i++) {
        if (tools[i].toolId === id)
            return tools[i].label;
    }
    return "Tool";
}

function contextActionsFor(panelKind) {
    var key = String(panelKind || "");
    return contextActions[key] || [];
}

function contextActionLabel(actionId) {
    var id = String(actionId || "");
    var panelKeys = Object.keys(contextActions);
    for (var i = 0; i < panelKeys.length; i++) {
        var actions = contextActions[panelKeys[i]];
        for (var j = 0; j < actions.length; j++) {
            if (actions[j].actionId === id)
                return actions[j].label;
        }
    }
    return "Action";
}
