import QtQuick
import QtQuick.Effects

Item {
    id: root
    objectName: "writingToolsFloatingToolbar"

    property real toolbarScale: 1.0
    property string selectedDrawingTool: "pen"
    property int selectedWidthIndex: 1
    property string selectedColor: "#0a84ff"
    property bool colorPanelOpen: false
    property bool customPickerOpen: false
    property bool eyedropperSampling: false
    // Which control opened the colour panel: "add" (dashed + button) or "dot"
    // (the selected swatch on the toolbar). Lets only the actual trigger show its
    // active highlight, so opening the panel from a colour dot does not light up
    // the "+" add button.
    property string colorPanelSource: ""
    property real maxColorPanelHeight: 10000
    // Toolbar colour slots: a stable, ordered list shown on the toolbar. Exactly
    // one slot is selected at a time (it carries the chevron). Selecting a slot
    // never reshuffles the list; picking in the flyout edits the selected slot in
    // place; the "+" swatch in the flyout appends a new slot.
    property var toolbarColors: []
    property int selectedColorIndex: 0
    property var _slotCache: ({})
    property bool _reconciling: false

    // ---- Pen options popover state (single source of truth; the popover
    // binds down and signals up). Per-variant settings are dedicated scalars
    // so each pen style keeps its own values and every change notifies. ----
    property bool penPopoverOpen: false
    property string penVariant: "fountain"        // "fountain" | "ball" | "brush"
    property real penFountainSharpness: 1.0       // 5 detents, 0..1; 1 = "Sharp"
    property real penFountainPressure: 1.0        // 5 detents, 0..1; 1 = "Max"
    property real penFountainStabilization: 0.0   // continuous 0..1
    property real penBallStabilization: 0.0
    property real penBrushPressure: 0.75
    property real penBrushStabilization: 0.0
    property bool penDrawAndHold: true
    property bool penScribbleToErase: true
    property bool penEraseShapesHighlighter: true
    property bool penCircleToLasso: true
    // Window width (set by ToolbarHost) so the popover can clamp against the
    // window edges; the pen-button centre is synced by the pen delegate.
    property real hostWidth: 100000
    property real penButtonCenterX: Math.round(14 * toolbarScale) + Math.round(74 * toolbarScale) / 2
    readonly property string penToolbarIcon: penVariant === "ball" ? "pen_ball"
                                           : penVariant === "brush" ? "pen_brush" : "pen"

    // Custom-picker HSV working state. selectedColor stays the public source of
    // truth; these mirror it (H/S/V in 0..1) so the field ring and hue handle
    // can be positioned, and so dragging one dial preserves the other two.
    property real hsvH: 0.58
    property real hsvS: 0.70
    property real hsvV: 0.59
    property bool _applyingHsv: false

    signal optionChanged(string summary)

    onSelectedColorChanged: {
        if (!root._applyingHsv)
            root.syncHsvFromColor();
        if (root.colorPanelSource !== "add")
            root.reconcileSelectedSlot();
    }
    Component.onCompleted: root.initColorSlots()

    readonly property color shellBg: "#202023"
    readonly property color shellBorder: "#22ffffff"
    readonly property color selectedBg: "#2fa8be"
    readonly property color pressedBg: "#2b2b2f"
    readonly property color hoverBg: "#2c2c30"
    readonly property color fg: "#f5f5f7"
    readonly property color mutedFg: "#b8b8b8"
    readonly property color selectedGlyph: "#16181a"
    readonly property var drawingTools: [
        { "toolId": "pen", "icon": "pen", "label": "Pen", "accent": "#0a84ff", "defaultColor": "#000000", "colors": [ "#000000", "#0a84ff", "#ffffff" ], "widths": [ 2, 5, 8 ] },
        { "toolId": "pencil", "icon": "pencil", "label": "Pencil", "accent": "#caa46a", "defaultColor": "#6b6b6b", "colors": [ "#6b6b6b", "#9a9a9a", "#c9c9c9" ], "widths": [ 2, 4, 6 ] },
        { "toolId": "highlighter", "icon": "highlighter", "label": "Highlighter", "accent": "#9abe46", "defaultColor": "#9abe46", "colors": [ "#9abe46", "#b01236", "#0a8a3f", "#15a3b8" ], "widths": [ 10, 16, 24 ] },
        { "toolId": "tape", "icon": "tape", "label": "Tape", "accent": "#ff5e68", "defaultColor": "#ff5e68", "colors": [ "#ff5e68", "#ff9f42", "#ffd22b" ], "widths": [ 8, 12, 16 ] },
        { "toolId": "shapes", "icon": "shapes", "label": "Draw Shape", "accent": "#0a84ff", "defaultColor": "#000000", "colors": [ "#000000", "#0a84ff", "#ffffff" ], "widths": [ 2, 5, 8 ] }
    ]
    readonly property var swatchGrid: [
        "#000000", "#737373", "#a5a5a5", "#d8d8d8", "#ffffff",
        "#ff1717", "#84229b", "#ff5558", "#ff8c8f", "#ff9828",
        "#0a84ff", "#0f5d9f", "#08a061", "#77c936", "#fbff7d"
    ]
    readonly property string activeToolLabel: labelFor(root.selectedDrawingTool)
    readonly property var activeWidths: widthsFor(root.selectedDrawingTool)
    readonly property int toolbarHeight: Math.round(76 * toolbarScale)
    readonly property int rowHeight: Math.round(58 * toolbarScale)
    readonly property int iconSize: Math.round(27 * toolbarScale)
    readonly property int selectedIconSize: Math.round(29 * toolbarScale)
    readonly property int colorDotSize: Math.round(38 * toolbarScale)
    readonly property int controlCellHeight: Math.round(58 * toolbarScale)
    readonly property real colorPanelScale: Math.max(0.68, Math.min(1.0, root.iconSize / 27))
    readonly property int colorPanelPad: Math.round(26 * colorPanelScale)
    readonly property int colorTitleSize: Math.round(24 * colorPanelScale)
    readonly property int colorGridTop: Math.round(78 * colorPanelScale)
    readonly property int colorSwatchCell: Math.round(42 * colorPanelScale)
    readonly property int colorSwatchDot: Math.round(32 * colorPanelScale)
    readonly property int colorSwatchGapX: Math.round(26 * colorPanelScale)
    readonly property int colorSwatchGapY: Math.round(13 * colorPanelScale)
    readonly property int colorWheelSize: Math.round(32 * colorPanelScale)
    readonly property int simpleColorPanelWidth: colorPanelPad * 2 + colorSwatchCell * 5 + colorSwatchGapX * 4
    readonly property int simpleColorPanelIdealHeight: colorGridTop
        + colorSwatchCell * 3
        + colorSwatchGapY * 2
        + Math.round(12 * colorPanelScale)
        + colorWheelSize
        + colorPanelPad
    readonly property int customColorPanelWidth: Math.round(500 * colorPanelScale)
    // Custom-picker vertical layout (scaled). The panel height is the sum of the
    // stacked rows so the field, hue strip and hex/commit row never collide.
    readonly property int colorFieldTop: Math.round(112 * colorPanelScale)
    readonly property int colorFieldHeight: Math.round(258 * colorPanelScale)
    readonly property int hueStripGap: Math.round(30 * colorPanelScale)
    readonly property int hueStripHeight: Math.round(18 * colorPanelScale)
    readonly property int hueStripInset: Math.round(46 * colorPanelScale)
    readonly property int colorHexGap: Math.round(30 * colorPanelScale)
    readonly property int colorHexHeight: Math.round(66 * colorPanelScale)
    readonly property int colorRowInset: Math.round(44 * colorPanelScale)
    readonly property int colorSelectorRing: Math.round(34 * colorPanelScale)
    readonly property int customColorPanelIdealHeight: colorFieldTop + colorFieldHeight
        + hueStripGap + hueStripHeight + colorHexGap + colorHexHeight
        + Math.round(38 * colorPanelScale)

    implicitWidth: toolbarRow.implicitWidth + Math.round(28 * root.toolbarScale)
    width: implicitWidth
    height: penPopover.visible ? penPopover.y + penPopover.height
          : colorPanel.visible ? colorPanel.y + colorPanel.height
          : toolbarShell.height

    function toolData(toolId) {
        var id = String(toolId || "");
        for (var i = 0; i < root.drawingTools.length; i++) {
            if (root.drawingTools[i].toolId === id)
                return root.drawingTools[i];
        }
        return root.drawingTools[0];
    }

    function labelFor(toolId) {
        return String(toolData(toolId).label || "Tool");
    }

    function widthsFor(toolId) {
        return toolData(toolId).widths || [ 2, 5, 8 ];
    }

    function baseColorsFor(toolId) {
        return toolData(toolId).colors || [ "#000000", "#0a84ff", "#ffffff" ];
    }

    function normalizeColor(value) {
        return String(value || "").toLowerCase();
    }

    function colorAlreadySeen(list, value) {
        var needle = normalizeColor(value);
        for (var i = 0; i < list.length; i++) {
            if (normalizeColor(list[i]) === needle)
                return true;
        }
        return false;
    }

    function defaultIndexFor(toolId) {
        var data = toolData(toolId);
        var cols = data.colors || [];
        var def = normalizeColor(data.defaultColor);
        for (var i = 0; i < cols.length; i++) {
            if (normalizeColor(cols[i]) === def)
                return i;
        }
        return 0;
    }

    // Perceived luminance test so the chevron can flip to a dark tint on light
    // swatches (white, pale yellow, …) and stay light on dark ones.
    function isLightColor(value) {
        var s = String(value || "").replace("#", "");
        if (s.length === 3)
            s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
        var r = parseInt(s.substr(0, 2), 16);
        var g = parseInt(s.substr(2, 2), 16);
        var b = parseInt(s.substr(4, 2), 16);
        if (isNaN(r) || isNaN(g) || isNaN(b))
            return false;
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62;
    }

    function initColorSlots() {
        var t = root.selectedDrawingTool;
        root.toolbarColors = baseColorsFor(t).slice();
        root.selectedColorIndex = defaultIndexFor(t);
        root.selectedColor = String(root.toolbarColors[root.selectedColorIndex] || "#0a84ff");
        root.syncHsvFromColor();
    }

    function saveColorSlots() {
        var cache = root._slotCache || {};
        cache[root.selectedDrawingTool] = {
            "colors": (root.toolbarColors || []).slice(),
            "index": root.selectedColorIndex
        };
        root._slotCache = cache;
    }

    function loadColorSlotsForTool(toolId) {
        var cached = (root._slotCache || {})[toolId];
        if (cached && cached.colors && cached.colors.length) {
            root.toolbarColors = cached.colors.slice();
            root.selectedColorIndex = Math.max(0, Math.min(cached.colors.length - 1, cached.index || 0));
        } else {
            root.toolbarColors = baseColorsFor(toolId).slice();
            root.selectedColorIndex = defaultIndexFor(toolId);
        }
        root.selectedColor = String(root.toolbarColors[root.selectedColorIndex] || "#0a84ff");
    }

    // Select an existing toolbar slot in place (no reshuffle to the front).
    function chooseColorSlot(index) {
        var list = root.toolbarColors || [];
        if (!list.length)
            return;
        var i = Math.max(0, Math.min(list.length - 1, index));
        root.selectedColorIndex = i;
        root.selectedColor = String(list[i] || root.selectedColor);
        emitOptionSummary();
    }

    // Edit the currently selected slot in place (swatch / field / hue picks).
    function editActiveColor(colorValue) {
        var v = String(colorValue || root.selectedColor);
        var list = (root.toolbarColors || []).slice();
        var i = root.selectedColorIndex;
        if (i >= 0 && i < list.length) {
            list[i] = v;
        } else {
            list.push(v);
            i = list.length - 1;
            root.selectedColorIndex = i;
        }
        root.toolbarColors = list;
        root.selectedColor = v;
    }

    // The "+" swatch in the picker: always pin the current colour as a NEW
    // toolbar slot and select it. (Picking a swatch / dragging the picker edits
    // the selected slot in place; only this "+" grows the palette - so it must
    // append unconditionally, even if the colour duplicates an existing slot.)
    function addColorSlot(colorValue) {
        var v = String(colorValue || root.selectedColor);
        var list = (root.toolbarColors || []).slice();
        list.push(v);
        root.toolbarColors = list;
        root.selectedColorIndex = list.length - 1;
        root.selectedColor = v;
        emitOptionSummary();
    }

    // Right-click a toolbar slot to remove it. Refuse if it would drop the
    // palette below three colours so the toolbar always keeps a usable minimum.
    function removeColorSlot(index) {
        var list = (root.toolbarColors || []).slice();
        if (list.length <= 3)
            return;
        var i = Math.max(0, Math.min(list.length - 1, index));
        list.splice(i, 1);
        var sel = root.selectedColorIndex;
        if (sel === i)
            sel = Math.min(i, list.length - 1);   // removed the selected slot
        else if (sel > i)
            sel = sel - 1;                         // selection shifted left
        root.toolbarColors = list;
        root.selectedColorIndex = sel;
        root.selectedColor = String(list[sel] || root.selectedColor);
        emitOptionSummary();
    }

    // Keep the selected slot consistent with selectedColor, even when it is set
    // externally: match an existing slot, otherwise write the colour into the
    // active slot so exactly one slot always carries the selection (and chevron).
    function reconcileSelectedSlot() {
        if (root._reconciling)
            return;
        var list = root.toolbarColors || [];
        if (!list.length)
            return;
        var cur = normalizeColor(root.selectedColor);
        var idx = root.selectedColorIndex;
        if (idx >= 0 && idx < list.length && normalizeColor(list[idx]) === cur)
            return;
        for (var i = 0; i < list.length; i++) {
            if (normalizeColor(list[i]) === cur) {
                root.selectedColorIndex = i;
                return;
            }
        }
        root._reconciling = true;
        var copy = list.slice();
        var j = Math.max(0, Math.min(copy.length - 1, idx));
        copy[j] = root.selectedColor;
        root.toolbarColors = copy;
        root.selectedColorIndex = j;
        root._reconciling = false;
    }

    function chooseDrawingTool(toolId) {
        var data = toolData(toolId);
        var nextTool = String(data.toolId || "pen");
        if (nextTool !== root.selectedDrawingTool)
            saveColorSlots();
        root.selectedDrawingTool = nextTool;
        root.selectedWidthIndex = 1;
        loadColorSlotsForTool(nextTool);
        closeColorPanel();
        root.penPopoverOpen = false;
        emitOptionSummary();
    }

    function chooseWidth(index) {
        root.selectedWidthIndex = Math.max(0, Math.min(2, index));
        emitOptionSummary();
    }

    function chooseColor(colorValue) {
        if (root.colorPanelSource === "add") {
            addColorSlot(colorValue);
            closeColorPanel();
            return;
        }
        editActiveColor(colorValue);
        emitOptionSummary();
    }

    function toggleColorPanel(customMode, source) {
        root.penPopoverOpen = false;
        var src = source || "add";
        if (root.colorPanelOpen && root.customPickerOpen === customMode) {
            closeColorPanel();
            return;
        }
        root.customPickerOpen = customMode;
        root.colorPanelOpen = true;
        root.colorPanelSource = src;
        root.eyedropperSampling = false;
    }

    function closeColorPanel() {
        if (root.colorPanelSource === "add") {
            var list = root.toolbarColors || [];
            root.selectedColor = String(list[root.selectedColorIndex] || root.selectedColor);
        }
        root.colorPanelOpen = false;
        root.customPickerOpen = false;
        root.colorPanelSource = "";
        root.eyedropperSampling = false;
    }

    function activateEyedropper() {
        if (!root.customPickerOpen)
            return;
        root.eyedropperSampling = !root.eyedropperSampling;
        root.optionChanged(root.eyedropperSampling
            ? "Eyedropper sample mode active"
            : "Eyedropper sample mode cancelled");
    }

    function sampleWithEyedropper(h, s, v) {
        root.eyedropperSampling = false;
        root.setHsv(h, s, v);
        root.optionChanged("Eyedropper picked " + root.selectedColor);
    }

    function penVariantLabel(v) {
        return v === "ball" ? "Ball Pen" : v === "brush" ? "Brush Pen" : "Fountain Pen";
    }

    function togglePenPopover() {
        if (root.penPopoverOpen) {
            root.penPopoverOpen = false;
            return;
        }
        closeColorPanel();
        root.penPopoverOpen = true;
        root.optionChanged(penVariantLabel(root.penVariant) + " options opened");
    }

    function closePenPopover() {
        root.penPopoverOpen = false;
    }

    function openPenGesturesPage() {
        penPopover.currentPage = 1;
    }

    function setPenVariant(v) {
        root.penVariant = String(v);
        root.optionChanged("Pen style: " + penVariantLabel(root.penVariant));
    }

    function setPenSlider(key, value, summaryText) {
        root[key] = value;
        root.optionChanged(String(summaryText));
    }

    function setPenToggle(key, on, label) {
        root[key] = on;
        root.optionChanged(String(label) + (on ? " on" : " off"));
    }

    function hueColorAt(t) {
        var h = Math.max(0, Math.min(1, t)) * 6;
        var c = 255;
        var x = Math.round(c * (1 - Math.abs((h % 2) - 1)));
        var r = 0, g = 0, b = 0;
        if (h < 1) { r = c; g = x; }
        else if (h < 2) { r = x; g = c; }
        else if (h < 3) { g = c; b = x; }
        else if (h < 4) { g = x; b = c; }
        else if (h < 5) { r = x; b = c; }
        else { r = c; b = x; }
        function hex(v) {
            var s = Math.max(0, Math.min(255, v)).toString(16);
            return s.length === 1 ? "0" + s : s;
        }
        return "#" + hex(r) + hex(g) + hex(b);
    }

    function emitOptionSummary() {
        var width = root.activeWidths[root.selectedWidthIndex] || 0;
        root.optionChanged(root.activeToolLabel + " preview: width " + width + ", color " + root.selectedColor);
    }

    function clamp01(t) {
        return Math.max(0, Math.min(1, t));
    }

    // "#rrggbb" -> [h, s, v] in 0..1. Hue is preserved (kept at the current
    // working value) for greys, where it is otherwise undefined.
    function rgbToHsv(value) {
        var s = String(value || "").replace("#", "");
        if (s.length === 3)
            s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
        var r = parseInt(s.substr(0, 2), 16) / 255;
        var g = parseInt(s.substr(2, 2), 16) / 255;
        var b = parseInt(s.substr(4, 2), 16) / 255;
        if (isNaN(r) || isNaN(g) || isNaN(b))
            return [ root.hsvH, root.hsvS, root.hsvV ];
        var mx = Math.max(r, g, b);
        var mn = Math.min(r, g, b);
        var d = mx - mn;
        var h = root.hsvH;
        if (d > 0.0001) {
            if (mx === r) h = (((g - b) / d) % 6 + 6) % 6;
            else if (mx === g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h /= 6;
        }
        return [ h, mx <= 0 ? 0 : d / mx, mx ];
    }

    function hsvToHex(h, s, v) {
        h = clamp01(h); s = clamp01(s); v = clamp01(v);
        var i = Math.floor(h * 6);
        var f = h * 6 - i;
        var p = v * (1 - s);
        var q = v * (1 - f * s);
        var t = v * (1 - (1 - f) * s);
        var r, g, b;
        switch (i % 6) {
        case 0: r = v; g = t; b = p; break;
        case 1: r = q; g = v; b = p; break;
        case 2: r = p; g = v; b = t; break;
        case 3: r = p; g = q; b = v; break;
        case 4: r = t; g = p; b = v; break;
        default: r = v; g = p; b = q; break;
        }
        function hx(x) {
            var n = Math.round(clamp01(x) * 255).toString(16);
            return n.length < 2 ? "0" + n : n;
        }
        return "#" + hx(r) + hx(g) + hx(b);
    }

    function syncHsvFromColor() {
        var hsv = rgbToHsv(root.selectedColor);
        root.hsvH = hsv[0];
        root.hsvS = hsv[1];
        root.hsvV = hsv[2];
    }

    // Set one or more HSV channels and push the result back to selectedColor
    // without clobbering the other channels (the _applyingHsv guard stops the
    // onSelectedColorChanged handler from re-deriving and rounding them away).
    function setHsv(h, s, v) {
        root.hsvH = clamp01(h);
        root.hsvS = clamp01(s);
        root.hsvV = clamp01(v);
        root._applyingHsv = true;
        var colorValue = hsvToHex(root.hsvH, root.hsvS, root.hsvV);
        if (root.colorPanelSource === "add")
            root.selectedColor = colorValue;
        else
            editActiveColor(colorValue);
        root._applyingHsv = false;
        emitOptionSummary();
    }

    component WritingToolGlyph: Canvas {
        id: glyph
        property string iconName: "pen"
        property color strokeColor: "#ffffff"
        property color accentColor: "#0a84ff"
        property color bgColor: "#202023"   // backdrop, used to knock out idle line-art overlaps
        property bool selected: false

        width: 42
        height: 42
        antialiasing: true

        onIconNameChanged: requestPaint()
        onStrokeColorChanged: requestPaint()
        onAccentColorChanged: requestPaint()
        onBgColorChanged: requestPaint()
        onSelectedChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()

        function roundedRect(ctx, x, y, w, h, r) {
            ctx.beginPath();
            ctx.moveTo(x + r, y);
            ctx.lineTo(x + w - r, y);
            ctx.quadraticCurveTo(x + w, y, x + w, y + r);
            ctx.lineTo(x + w, y + h - r);
            ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
            ctx.lineTo(x + r, y + h);
            ctx.quadraticCurveTo(x, y + h, x, y + h - r);
            ctx.lineTo(x, y + r);
            ctx.quadraticCurveTo(x, y, x + r, y);
        }

        function poly(ctx, points, fill) {
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (var i = 1; i < points.length; i++)
                ctx.lineTo(points[i][0], points[i][1]);
            ctx.closePath();
            if (fill)
                ctx.fill();
            else
                ctx.stroke();
        }

        onPaint: {
            var ctx = getContext("2d");
            var s = Math.min(width, height);
            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.translate((width - s) / 2, (height - s) / 2);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.strokeStyle = glyph.strokeColor;
            ctx.fillStyle = glyph.strokeColor;
            ctx.lineWidth = s * 0.072;

            var sel = glyph.selected;
            var outline = sel ? "#1b1b1f" : glyph.strokeColor;
            var ink = glyph.accentColor;  // selected drawing colour → the tool's "ink" parts

            if (glyph.iconName === "pen") {
                // Custom pen-tool nib geometry, normalized to the icon bbox.
                // Screen-space:
                // a flag "wing" (ink) behind a white metal nib with a bold dark
                // outline + dark spike tip, a dark-ringed breather hole whose
                // centre is the ink colour, and an ink swoosh below.
                var ow = s * 0.05;
                var penOutline = sel ? "#15151a" : glyph.strokeColor;
                ctx.lineJoin = "round";
                ctx.lineCap = "round";
                ctx.strokeStyle = penOutline;
                ctx.lineWidth = ow;

                // flag wing (ink), behind the nib
                ctx.beginPath();
                ctx.moveTo(0.573 * s, 0.093 * s);
                ctx.lineTo(0.885 * s, 0.403 * s);
                ctx.lineTo(0.718 * s, 0.443 * s);
                ctx.lineTo(0.524 * s, 0.249 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = ink; ctx.fill(); }
                ctx.stroke();

                // dark spike tip
                ctx.beginPath();
                ctx.moveTo(0.098 * s, 0.887 * s);
                ctx.lineTo(0.221 * s, 0.687 * s);
                ctx.lineTo(0.298 * s, 0.742 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#15151a"; ctx.fill(); }
                ctx.stroke();

                // nib body (white metal)
                ctx.beginPath();
                ctx.moveTo(0.298 * s, 0.405 * s);
                ctx.lineTo(0.487 * s, 0.324 * s);
                ctx.lineTo(0.645 * s, 0.487 * s);
                ctx.lineTo(0.553 * s, 0.671 * s);
                ctx.lineTo(0.298 * s, 0.742 * s);
                ctx.lineTo(0.221 * s, 0.687 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#eceef0"; ctx.fill(); }
                ctx.stroke();

                // slit from the breather toward the tip
                ctx.lineWidth = ow * 0.85;
                ctx.beginPath();
                ctx.moveTo(0.405 * s, 0.575 * s);
                ctx.lineTo(0.250 * s, 0.712 * s);
                ctx.stroke();

                // breather hole: dark ring + ink centre
                ctx.lineWidth = ow;
                ctx.beginPath();
                ctx.arc(0.430 * s, 0.537 * s, 0.052 * s, 0, Math.PI * 2);
                if (sel) { ctx.fillStyle = "#15151a"; ctx.fill(); }
                ctx.stroke();
                if (sel) {
                    ctx.beginPath();
                    ctx.arc(0.430 * s, 0.537 * s, 0.026 * s, 0, Math.PI * 2);
                    ctx.fillStyle = ink;
                    ctx.fill();
                }

                // ink swoosh below the nib
                ctx.strokeStyle = sel ? ink : glyph.strokeColor;
                ctx.lineWidth = sel ? s * 0.135 : s * 0.06;
                ctx.beginPath();
                ctx.moveTo(0.410 * s, 0.820 * s);
                ctx.quadraticCurveTo(0.650 * s, 0.885 * s, 0.900 * s, 0.835 * s);
                ctx.stroke();
            } else if (glyph.iconName === "pen_ball") {
                // Ball Pen style of the pen tool: same 45deg tilt family as the
                // pencil — dark barrel with a clicker nub, white metal cone and
                // an ink-filled ball point, plus the shared ink swoosh.
                ctx.save();
                ctx.translate(0.46 * s, 0.42 * s);
                ctx.rotate(Math.PI / 4);
                ctx.strokeStyle = sel ? "#15151a" : glyph.strokeColor;
                ctx.lineWidth = s * 0.062;

                var bHalf = 0.115 * s;
                var bBack = -0.40 * s;
                var bCollar = 0.10 * s;
                var bTipTop = 0.30 * s;
                var bTip = 0.40 * s;
                var bR = 0.045 * s;

                // clicker nub on the back end
                glyph.roundedRect(ctx, -0.045 * s, bBack - 0.075 * s, 0.09 * s, 0.09 * s, 0.02 * s);
                if (sel) { ctx.fillStyle = "#15151a"; ctx.fill(); }
                ctx.stroke();

                // barrel: rounded back, straight sides down to the collar
                ctx.beginPath();
                ctx.moveTo(-bHalf, bBack + bR);
                ctx.quadraticCurveTo(-bHalf, bBack, -bHalf + bR, bBack);
                ctx.lineTo(bHalf - bR, bBack);
                ctx.quadraticCurveTo(bHalf, bBack, bHalf, bBack + bR);
                ctx.lineTo(bHalf, bCollar);
                ctx.lineTo(-bHalf, bCollar);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#3f4148"; ctx.fill(); }
                ctx.stroke();

                // white metal cone narrowing toward the point
                ctx.beginPath();
                ctx.moveTo(-bHalf, bCollar);
                ctx.lineTo(bHalf, bCollar);
                ctx.lineTo(0.042 * s, bTipTop);
                ctx.lineTo(-0.042 * s, bTipTop);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#eceef0"; ctx.fill(); }
                ctx.stroke();

                // ball point: ink-filled tip
                ctx.beginPath();
                ctx.moveTo(-0.042 * s, bTipTop);
                ctx.lineTo(0.042 * s, bTipTop);
                ctx.lineTo(0, bTip);
                ctx.closePath();
                if (sel) { ctx.fillStyle = ink; ctx.fill(); }
                ctx.stroke();
                ctx.restore();

                // shared ink swoosh underline
                ctx.strokeStyle = sel ? ink : glyph.strokeColor;
                ctx.lineWidth = sel ? s * 0.135 : s * 0.06;
                ctx.beginPath();
                ctx.moveTo(0.410 * s, 0.820 * s);
                ctx.quadraticCurveTo(0.650 * s, 0.885 * s, 0.900 * s, 0.835 * s);
                ctx.stroke();
            } else if (glyph.iconName === "pen_brush") {
                // Brush Pen style of the pen tool: cream handle, metal ferrule
                // and an ink bristle head tapering to a point, plus the swoosh.
                ctx.save();
                ctx.translate(0.46 * s, 0.42 * s);
                ctx.rotate(Math.PI / 4);
                ctx.strokeStyle = sel ? "#15151a" : glyph.strokeColor;
                ctx.lineWidth = s * 0.062;

                var hHalf = 0.082 * s;
                var hBack = -0.46 * s;
                var hEnd = -0.12 * s;     // handle -> ferrule
                var fEnd = 0.005 * s;     // ferrule -> bristles
                var hR = 0.04 * s;

                // handle (cream)
                ctx.beginPath();
                ctx.moveTo(-hHalf, hBack + hR);
                ctx.quadraticCurveTo(-hHalf, hBack, -hHalf + hR, hBack);
                ctx.lineTo(hHalf - hR, hBack);
                ctx.quadraticCurveTo(hHalf, hBack, hHalf, hBack + hR);
                ctx.lineTo(hHalf, hEnd);
                ctx.lineTo(-hHalf, hEnd);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#e8d9a8"; ctx.fill(); }
                ctx.stroke();

                // ferrule (metal band, slightly wider than the handle)
                ctx.beginPath();
                ctx.moveTo(-0.095 * s, hEnd);
                ctx.lineTo(0.095 * s, hEnd);
                ctx.lineTo(0.085 * s, fEnd);
                ctx.lineTo(-0.085 * s, fEnd);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#b9bdc4"; ctx.fill(); }
                ctx.stroke();

                // bristle head: swells out then tapers to a point
                ctx.beginPath();
                ctx.moveTo(-0.085 * s, fEnd);
                ctx.quadraticCurveTo(-0.150 * s, 0.115 * s, 0, 0.42 * s);
                ctx.quadraticCurveTo(0.150 * s, 0.115 * s, 0.085 * s, fEnd);
                ctx.closePath();
                if (sel) { ctx.fillStyle = ink; ctx.fill(); }
                ctx.stroke();
                ctx.restore();

                // shared ink swoosh underline
                ctx.strokeStyle = sel ? ink : glyph.strokeColor;
                ctx.lineWidth = sel ? s * 0.135 : s * 0.06;
                ctx.beginPath();
                ctx.moveTo(0.410 * s, 0.820 * s);
                ctx.quadraticCurveTo(0.650 * s, 0.885 * s, 0.900 * s, 0.835 * s);
                ctx.stroke();
            } else if (glyph.iconName === "pencil") {
                // Custom sharpened hex pencil, tip at lower-left: a grey barrel
                // carrying two facet
                // ridge lines under a bold black outline, a pale-wood sharpened
                // cone, and a grey graphite point. Colours are fixed (a pencil
                // reads as a pencil regardless of the selected ink).
                ctx.save();
                ctx.translate(0.50 * s, 0.50 * s);
                ctx.rotate(Math.PI / 4);
                ctx.strokeStyle = outline;

                var pHalf = 0.142 * s;
                var pBack = -0.43 * s;     // flat back end (upper-right)
                var pCollar = 0.085 * s;   // barrel -> raw-wood boundary (tooth roots)
                var pTip = 0.45 * s;       // sharpened point
                var pFacet = 0.052 * s;    // ridge-line offset from the axis
                var pNotch = 0.062 * s;    // how far the paint teeth bite toward the tip
                var pR = 0.042 * s;        // back-end corner radius

                // sharpened wood cone (drawn first; the barrel laps over its top)
                ctx.lineWidth = s * 0.062;
                ctx.beginPath();
                ctx.moveTo(-pHalf, pCollar - 0.02 * s);
                ctx.lineTo(pHalf, pCollar - 0.02 * s);
                ctx.lineTo(0, pTip);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#eae6a2"; ctx.fill(); }
                ctx.stroke();

                // grey barrel: rounded back, then a zig-zag "freshly sharpened"
                // collar with paint teeth biting toward the tip at the ridges
                ctx.beginPath();
                ctx.moveTo(-pHalf, pBack + pR);
                ctx.quadraticCurveTo(-pHalf, pBack, -pHalf + pR, pBack);
                ctx.lineTo(pHalf - pR, pBack);
                ctx.quadraticCurveTo(pHalf, pBack, pHalf, pBack + pR);
                ctx.lineTo(pHalf, pCollar);
                ctx.lineTo(pFacet, pCollar + pNotch);
                ctx.lineTo(0, pCollar);
                ctx.lineTo(-pFacet, pCollar + pNotch);
                ctx.lineTo(-pHalf, pCollar);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#70727a"; ctx.fill(); }
                ctx.stroke();

                // grey graphite point at the very tip
                ctx.beginPath();
                ctx.moveTo(-0.062 * s, 0.335 * s);
                ctx.lineTo(0.062 * s, 0.335 * s);
                ctx.lineTo(0, pTip);
                ctx.closePath();
                if (sel) { ctx.fillStyle = "#595b61"; ctx.fill(); }
                ctx.stroke();

                // two hexagonal facet ridge lines running down to the paint teeth
                ctx.lineWidth = s * 0.042;
                ctx.beginPath();
                ctx.moveTo(-pFacet, pBack + 0.06 * s);
                ctx.lineTo(-pFacet, pCollar + pNotch);
                ctx.moveTo(pFacet, pBack + 0.06 * s);
                ctx.lineTo(pFacet, pCollar + pNotch);
                ctx.stroke();
                ctx.restore();
            } else if (glyph.iconName === "highlighter") {
                // Custom illustrated chisel highlighter: a green ink barrel
                // (back of the pen), a
                // grey holder over its front, a green felt nib at the lower-left,
                // and a green swipe beneath — all under bold outlines. The
                // ink-coloured parts (barrel/nib/swipe) track the selected
                // colour; the holder stays grey. Selected renders in full
                // colour; idle knocks the overlaps out to clean white line-art.
                var hlBg = glyph.bgColor;
                var hlInk = sel ? ink : hlBg;           // barrel / nib / swipe
                var hlHolder = sel ? "#5b757b" : hlBg;  // grey grip
                ctx.lineWidth = s * 0.062;
                ctx.strokeStyle = outline;

                // barrel — green parallelogram (back of the pen); its lower-left
                // edge is the division line shared with the grey holder
                ctx.beginPath();
                ctx.moveTo(0.482 * s, 0.094 * s);
                ctx.lineTo(0.852 * s, 0.560 * s);
                ctx.lineTo(0.658 * s, 0.728 * s);
                ctx.lineTo(0.326 * s, 0.363 * s);
                ctx.closePath();
                ctx.fillStyle = hlInk; ctx.fill(); ctx.stroke();

                // holder — grey grip riding over the barrel's front
                ctx.beginPath();
                ctx.moveTo(0.312 * s, 0.361 * s);
                ctx.lineTo(0.648 * s, 0.689 * s);
                ctx.lineTo(0.404 * s, 0.792 * s);
                ctx.lineTo(0.212 * s, 0.592 * s);
                ctx.closePath();
                ctx.fillStyle = hlHolder; ctx.fill(); ctx.stroke();

                // felt nib — green wedge poking out the lower-left
                ctx.beginPath();
                ctx.moveTo(0.180 * s, 0.703 * s);
                ctx.lineTo(0.302 * s, 0.803 * s);
                ctx.lineTo(0.118 * s, 0.844 * s);
                ctx.lineTo(0.080 * s, 0.811 * s);
                ctx.closePath();
                ctx.fillStyle = hlInk; ctx.fill(); ctx.stroke();

                // green swipe laid down beneath the tip (selected only)
                if (sel) {
                    ctx.strokeStyle = ink;
                    ctx.lineCap = "round";
                    ctx.lineWidth = s * 0.072;
                    ctx.beginPath();
                    ctx.moveTo(0.526 * s, 0.875 * s);
                    ctx.lineTo(0.920 * s, 0.875 * s);
                    ctx.stroke();
                }
            } else if (glyph.iconName === "tape") {
                // Slanted tape slab; red with a hatch texture when active.
                ctx.save();
                ctx.translate(0.50 * s, 0.52 * s);
                ctx.rotate(-Math.PI * 0.17);
                ctx.strokeStyle = outline;
                ctx.lineWidth = s * 0.072;
                if (sel) {
                    glyph.roundedRect(ctx, -0.33 * s, -0.15 * s, 0.66 * s, 0.30 * s, 0.06 * s);
                    ctx.fillStyle = ink;
                    ctx.fill();
                    ctx.save();
                    ctx.clip();
                    ctx.globalAlpha = 0.20;
                    ctx.strokeStyle = "#ffffff";
                    ctx.lineWidth = s * 0.028;
                    for (var tx = -0.5; tx <= 0.42; tx += 0.085) {
                        ctx.beginPath();
                        ctx.moveTo(tx * s, -0.22 * s);
                        ctx.lineTo((tx + 0.17) * s, 0.22 * s);
                        ctx.stroke();
                    }
                    ctx.restore();
                }
                glyph.roundedRect(ctx, -0.33 * s, -0.15 * s, 0.66 * s, 0.30 * s, 0.06 * s);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(0.15 * s, -0.15 * s);
                ctx.lineTo(0.15 * s, 0.15 * s);
                ctx.stroke();
                ctx.restore();
            } else if (glyph.iconName === "shapes") {
                // Overlapping circle / square / triangle — stays colourful in
                // both states with a thin dark outline.
                ctx.lineWidth = s * 0.05;
                ctx.strokeStyle = "#2a2a30";
                ctx.fillStyle = "#ecc93c";
                ctx.beginPath();
                ctx.arc(0.34 * s, 0.63 * s, 0.165 * s, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = "#a9a6c2";
                glyph.roundedRect(ctx, 0.45 * s, 0.15 * s, 0.27 * s, 0.27 * s, 0.05 * s);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = "#c4565a";
                ctx.beginPath();
                ctx.moveTo(0.56 * s, 0.66 * s);
                ctx.lineTo(0.85 * s, 0.52 * s);
                ctx.lineTo(0.85 * s, 0.82 * s);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
            } else if (glyph.iconName === "eyedropper") {
                ctx.save();
                ctx.translate(0.53 * s, 0.48 * s);
                ctx.rotate(-Math.PI * 0.25);
                ctx.strokeStyle = glyph.strokeColor;
                ctx.lineWidth = s * 0.075;
                ctx.beginPath();
                ctx.moveTo(-0.05 * s, -0.30 * s);
                ctx.lineTo(0.28 * s, -0.30 * s);
                ctx.lineTo(0.28 * s, -0.16 * s);
                ctx.lineTo(0.08 * s, 0.04 * s);
                ctx.lineTo(0.08 * s, 0.32 * s);
                ctx.lineTo(-0.08 * s, 0.32 * s);
                ctx.lineTo(-0.08 * s, 0.04 * s);
                ctx.lineTo(-0.28 * s, -0.16 * s);
                ctx.lineTo(-0.28 * s, -0.30 * s);
                ctx.closePath();
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(-0.18 * s, 0.18 * s);
                ctx.lineTo(-0.36 * s, 0.36 * s);
                ctx.stroke();
                ctx.restore();
            }

            ctx.restore();
        }
    }

    component DrawingToolButton: Item {
        id: toolButton
        property string toolId: "pen"
        property string iconName: "pen"
        property string label: "Tool"
        property color accentColor: "#0a84ff"
        property bool selected: false
        signal clicked()

        width: selected ? Math.round(74 * root.toolbarScale) : Math.round(52 * root.toolbarScale)
        height: root.controlCellHeight

        Rectangle {
            anchors.fill: parent
            radius: Math.round(18 * root.toolbarScale)
            color: toolButton.selected ? root.selectedBg : (toolButtonMouse.containsMouse ? root.hoverBg : "transparent")
        }

        // Idle (unselected) glyph: prefer a vectorised SVG traced from the
        // benchmark via scripts/vectorize.py --preset glyph; fall back to the
        // hand-drawn Canvas glyph when no SVG exists for this tool.
        Image {
            id: idleGlyph
            anchors.centerIn: parent
            width: root.iconSize
            height: root.iconSize
            sourceSize.width: 160
            sourceSize.height: 160
            fillMode: Image.PreserveAspectFit
            smooth: true
            antialiasing: true
            // pen_ball / pen_brush are Canvas-only (no SVGs traced for them).
            source: toolButton.iconName.indexOf("pen_") === 0
                ? "" : Qt.resolvedUrl("glyphs/" + toolButton.iconName + "_idle.svg")
            visible: !toolButton.selected && status === Image.Ready
        }

        // Selected ink: the recolourable accent silhouette, drawn UNDER the base
        // and tinted live to the selected drawing colour. pen/highlighter/tape tint
        // their saturated accent; pencil tints its grey body+tip (ink split by a
        // luminance band, see scripts/extract_button_glyph.py --ink-luma). Hidden
        // for shapes (no ink SVG -> fixed colours).
        Image {
            id: selectedInk
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: toolButton.selected ? -Math.round(6 * root.toolbarScale) : 0
            width: root.selectedIconSize
            height: root.selectedIconSize
            sourceSize.width: 168
            sourceSize.height: 168
            fillMode: Image.PreserveAspectFit
            source: toolButton.iconName.indexOf("pen_") === 0
                ? "" : Qt.resolvedUrl("glyphs/" + toolButton.iconName + "_selected_ink.svg")
            visible: false
        }
        MultiEffect {
            anchors.fill: selectedInk
            source: selectedInk
            colorization: 1.0
            colorizationColor: root.selectedColor
            visible: toolButton.selected && selectedInk.status === Image.Ready
        }

        // Selected base: fixed structural colours (outline, nib, holder, wood),
        // on top of the tinted ink. Falls back to Canvas if no SVG for this tool.
        Image {
            id: selectedGlyph
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: toolButton.selected ? -Math.round(6 * root.toolbarScale) : 0
            width: root.selectedIconSize
            height: root.selectedIconSize
            sourceSize.width: 168
            sourceSize.height: 168
            fillMode: Image.PreserveAspectFit
            smooth: true
            antialiasing: true
            source: toolButton.iconName.indexOf("pen_") === 0
                ? "" : Qt.resolvedUrl("glyphs/" + toolButton.iconName + "_selected.svg")
            visible: toolButton.selected && status === Image.Ready
        }

        WritingToolGlyph {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: toolButton.selected ? -Math.round(6 * root.toolbarScale) : 0
            width: toolButton.selected ? root.selectedIconSize : root.iconSize
            height: width
            iconName: toolButton.iconName
            selected: toolButton.selected
            strokeColor: toolButton.selected ? root.selectedGlyph : root.fg
            accentColor: toolButton.selected ? root.selectedColor : root.fg
            visible: toolButton.selected ? selectedGlyph.status !== Image.Ready
                                         : idleGlyph.status !== Image.Ready
        }

        ToolbarIcon {
            visible: toolButton.selected
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: Math.round(7 * root.toolbarScale)
            iconName: "chevron"
            size: Math.max(10, Math.round(root.iconSize * 0.45))
            strokeColor: root.selectedGlyph
        }

        MouseArea {
            id: toolButtonMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: toolButton.clicked()
        }
    }

    component WidthButton: Item {
        id: widthButton
        property int optionIndex: 0
        property real previewHeight: 4
        property bool selected: false
        property bool roundDot: false
        signal clicked()

        width: Math.round(56 * root.toolbarScale)
        height: root.controlCellHeight

        Rectangle {
            anchors.centerIn: parent
            width: Math.round(50 * root.toolbarScale)
            height: width
            radius: Math.round(17 * root.toolbarScale)
            color: widthButton.selected ? root.pressedBg : (widthMouse.containsMouse ? root.hoverBg : "transparent")
        }

        Rectangle {
            visible: !widthButton.roundDot
            anchors.centerIn: parent
            width: Math.round(36 * root.toolbarScale)
            height: Math.max(2, Math.round(widthButton.previewHeight * root.toolbarScale))
            radius: Math.max(1, height / 2)
            color: root.fg
            opacity: 0.98
        }

        Rectangle {
            visible: widthButton.roundDot
            anchors.centerIn: parent
            width: Math.max(Math.round(8 * root.toolbarScale), Math.min(Math.round(24 * root.toolbarScale), Math.round(widthButton.previewHeight * root.toolbarScale)))
            height: width
            radius: width / 2
            color: root.fg
            opacity: 0.98
        }

        MouseArea {
            id: widthMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: widthButton.clicked()
        }
    }

    component ColorDot: Item {
        id: colorDot
        property string colorValue: "#ffffff"
        property bool selected: false
        property int dotSize: root.colorDotSize
        property bool removable: false
        signal clicked()
        signal rightClicked()

        width: dotSize + (selected ? Math.round(18 * root.toolbarScale) : Math.round(8 * root.toolbarScale))
        height: root.controlCellHeight

        Rectangle {
            anchors.centerIn: parent
            width: colorDot.selected ? Math.round(54 * root.toolbarScale) : colorDot.dotSize
            height: width
            radius: width / 2
            color: colorDot.selected ? root.pressedBg : "transparent"
        }

        Rectangle {
            anchors.centerIn: parent
            width: colorDot.dotSize
            height: width
            radius: width / 2
            color: colorDot.colorValue
            border.width: normalizeColor(colorDot.colorValue) === "#ffffff" ? 1 : 0
            border.color: "#cfcfcf"
        }

        ToolbarIcon {
            visible: colorDot.selected
            anchors.centerIn: parent
            iconName: "chevron"
            size: 20
            strokeColor: root.isLightColor(colorDot.colorValue) ? "#3c3f45" : "#f8f8f8"
        }

        // Hover hint that this slot can be removed with a right-click.
        Rectangle {
            visible: colorDot.removable && dotMouse.containsMouse
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -Math.round(colorDot.dotSize / 2) - Math.round(2 * root.toolbarScale)
            width: Math.round(16 * root.toolbarScale)
            height: width
            radius: width / 2
            color: "#d23b3b"
            border.width: 1
            border.color: "#16181a"
            Rectangle {
                anchors.centerIn: parent
                width: Math.round(8 * root.toolbarScale)
                height: Math.max(1, Math.round(2 * root.toolbarScale))
                radius: height / 2
                color: "#ffffff"
            }
        }

        MouseArea {
            id: dotMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: function(mouse) {
                if (mouse.button === Qt.RightButton)
                    colorDot.rightClicked();
                else
                    colorDot.clicked();
            }
        }
    }

    component AddColorButton: Item {
        id: addButton
        signal clicked()

        width: Math.round(58 * root.toolbarScale)
        height: root.controlCellHeight

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: addMouse.containsMouse || (root.colorPanelOpen && root.colorPanelSource === "add")
                ? root.pressedBg : "transparent"
        }

        Canvas {
            id: addGlyph
            anchors.centerIn: parent
            width: Math.round(38 * root.toolbarScale)
            height: width
            // Hand-drawn to match icons/benchmark/add_color_slot.png: a dashed
            // ring of 6 segments (one hidden behind the badge) with a filled "+"
            // badge sitting up-and-right on the ring. Proportions (badge at 45deg,
            // 0.94*R out, radius 0.556*R, 6 dashes at 60deg pitch / ~33deg arc)
            // were measured from the reference, then drawn as vectors so it stays
            // crisp at any toolbar scale.
            property color glyphColor: root.fg
            onGlyphColorChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d");
                var W = width, H = height;
                ctx.clearRect(0, 0, W, H);
                ctx.save();

                var cx = W * 0.5, cy = H * 0.5;
                var R = W * 0.40;                 // ring radius
                var ring = Math.max(1.5, W * 0.075);
                var badgeR = R * 0.556;           // badge outer radius
                var ba = -Math.PI / 4;            // badge centre at 45deg up-right
                var bx = cx + Math.cos(ba) * R;
                var by = cy + Math.sin(ba) * R;

                // Dashed ring: 6 arcs at 60deg pitch, ~33deg drawn / ~27deg gap,
                // centred so one gap faces the badge (so the badge reads as
                // replacing that segment, like the reference).
                ctx.strokeStyle = addGlyph.glyphColor;
                ctx.lineWidth = ring;
                ctx.lineCap = "round";
                var dash = 33 * Math.PI / 180;
                for (var k = 0; k < 6; k++) {
                    var mid = ba + (k + 1) * (Math.PI / 3);   // step around from badge
                    ctx.beginPath();
                    ctx.arc(cx, cy, R, mid - dash / 2, mid + dash / 2);
                    ctx.stroke();
                }

                // Badge disc (knock a ring-width gap out from under it so the
                // dashes never bleed into the badge edge).
                ctx.fillStyle = root.shellBg;
                ctx.beginPath();
                ctx.arc(bx, by, badgeR + ring * 0.6, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = addGlyph.glyphColor;
                ctx.beginPath();
                ctx.arc(bx, by, badgeR, 0, Math.PI * 2);
                ctx.fill();

                // "+" knockout inside the badge.
                ctx.strokeStyle = root.shellBg;
                ctx.lineWidth = Math.max(1.4, badgeR * 0.30);
                ctx.lineCap = "round";
                var arm = badgeR * 0.52;
                ctx.beginPath();
                ctx.moveTo(bx - arm, by);
                ctx.lineTo(bx + arm, by);
                ctx.moveTo(bx, by - arm);
                ctx.lineTo(bx, by + arm);
                ctx.stroke();

                ctx.restore();
            }
        }

        MouseArea {
            id: addMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: addButton.clicked()
        }
    }

    component PickedColorButton: Item {
        id: pickedButton
        property string colorValue: "#000000"
        readonly property real s: root.colorPanelScale
        signal clicked()

        width: Math.round(76 * s)
        height: Math.round(70 * s)

        Rectangle {
            anchors.centerIn: parent
            width: Math.round(58 * pickedButton.s)
            height: width
            radius: width / 2
            color: pickedButton.colorValue
            border.width: normalizeColor(pickedButton.colorValue) === "#ffffff" ? 1 : 0
            border.color: "#cfcfcf"
        }

        Rectangle {
            width: Math.round(26 * pickedButton.s)
            height: width
            radius: width / 2
            x: parent.width - width - Math.round(2 * pickedButton.s)
            y: Math.round(2 * pickedButton.s)
            color: "#0a84ff"
            Text {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: -1
                text: "+"
                color: root.fg
                font.pixelSize: Math.round(22 * pickedButton.s)
                font.bold: true
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pickedButton.clicked()
        }
    }

    component EyedropperButton: Item {
        id: pickerButton
        objectName: "writingToolsEyedropperButton"
        property bool active: false
        readonly property real s: root.colorPanelScale
        signal clicked()

        width: Math.round(42 * s)
        height: width

        Rectangle {
            anchors.fill: parent
            radius: Math.round(10 * pickerButton.s)
            color: pickerButton.active ? root.pressedBg
                : (pickerMouse.containsMouse ? root.hoverBg : "transparent")
            border.width: pickerButton.active ? 1 : 0
            border.color: "#55ffffff"
        }

        Image {
            id: pickerIcon
            objectName: "writingToolsEyedropperIcon"
            anchors.centerIn: parent
            width: Math.round(28 * pickerButton.s)
            height: width
            sourceSize.width: 24
            sourceSize.height: 24
            fillMode: Image.PreserveAspectFit
            smooth: true
            antialiasing: true
            visible: false
            source: Qt.resolvedUrl("glyphs/color_picker.svg")
        }

        MultiEffect {
            anchors.fill: pickerIcon
            source: pickerIcon
            colorization: 1.0
            colorizationColor: pickerButton.active || pickerMouse.containsMouse ? root.fg : root.mutedFg
            visible: pickerIcon.status === Image.Ready
        }

        MouseArea {
            id: pickerMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pickerButton.clicked()
        }
    }

    Rectangle {
        id: toolbarShell
        width: root.width
        height: root.toolbarHeight
        radius: height / 2
        color: root.shellBg
        border.width: 1
        border.color: root.shellBorder

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: parent.radius
            anchors.rightMargin: parent.radius
            height: 1
            color: "#22ffffff"
        }

        Flickable {
            id: toolbarFlick
            anchors.fill: parent
            anchors.leftMargin: Math.round(14 * root.toolbarScale)
            anchors.rightMargin: Math.round(14 * root.toolbarScale)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            contentWidth: toolbarRow.implicitWidth
            contentHeight: height
            interactive: contentWidth > width

            Row {
                id: toolbarRow
                y: (toolbarFlick.height - height) / 2
                height: root.rowHeight
                spacing: Math.round(8 * root.toolbarScale)

                Repeater {
                    model: root.drawingTools

                    DrawingToolButton {
                        id: toolDelegate
                        toolId: String(modelData.toolId || "")
                        iconName: toolId === "pen" ? root.penToolbarIcon : String(modelData.icon || "")
                        label: String(modelData.label || "")
                        accentColor: String(modelData.accent || root.selectedColor)
                        selected: root.selectedDrawingTool === toolId
                        onClicked: {
                            if (toolId === "pen" && root.selectedDrawingTool === "pen")
                                root.togglePenPopover();   // re-click on the active pen opens its options
                            else
                                root.chooseDrawingTool(toolId);
                        }

                        // Keep the pen-options caret glued to the pen button:
                        // mapToItem is imperative, so re-sync on every geometry
                        // input, including horizontal scrolling of the row.
                        readonly property bool isPen: String(modelData.toolId || "") === "pen"
                        function syncCenter() {
                            if (isPen)
                                root.penButtonCenterX = toolDelegate.mapToItem(root, toolDelegate.width / 2, 0).x;
                        }
                        Component.onCompleted: syncCenter()
                        onXChanged: syncCenter()
                        onWidthChanged: syncCenter()
                        Connections {
                            target: toolbarFlick
                            function onContentXChanged() { toolDelegate.syncCenter(); }
                        }
                    }
                }

                Rectangle {
                    width: 1
                    height: Math.round(38 * root.toolbarScale)
                    anchors.verticalCenter: parent.verticalCenter
                    color: "#23ffffff"
                }

                Repeater {
                    model: 3

                    WidthButton {
                        optionIndex: index
                        previewHeight: root.activeWidths[index]
                        selected: root.selectedWidthIndex === index
                        roundDot: root.selectedDrawingTool === "highlighter"
                        onClicked: root.chooseWidth(index)
                    }
                }

                Repeater {
                    model: root.toolbarColors

                    ColorDot {
                        colorValue: String(modelData || "#ffffff")
                        selected: index === root.selectedColorIndex
                        dotSize: root.colorDotSize
                        removable: (root.toolbarColors || []).length > 3
                        onClicked: {
                            if (index === root.selectedColorIndex)
                                root.toggleColorPanel(false, "dot");
                            else
                                root.chooseColorSlot(index);
                        }
                        onRightClicked: root.removeColorSlot(index)
                    }
                }

                AddColorButton {
                    id: addColorButton
                    onClicked: root.toggleColorPanel(false, "add")
                }
            }
        }
    }

    Rectangle {
        id: colorPanel
        objectName: "writingToolsColorPopover"
        visible: root.colorPanelOpen
        width: root.customPickerOpen ? root.customColorPanelWidth : root.simpleColorPanelWidth
        height: Math.min(
            root.customPickerOpen ? root.customColorPanelIdealHeight : root.simpleColorPanelIdealHeight,
            Math.max(180, root.maxColorPanelHeight - y)
        )
        x: Math.max(0, Math.min(root.width - width, root.width - width - 16))
        y: toolbarShell.height + Math.round(14 * root.toolbarScale)
        radius: Math.round(16 * root.toolbarScale)
        color: root.shellBg
        border.width: 1
        border.color: "#22ffffff"
        clip: true

        Canvas {
            id: colorPanelCaret
            width: 36
            height: 18
            x: Math.max(16, Math.min(colorPanel.width - width - 16, colorPanel.width - 94))
            y: -height + 1
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.fillStyle = root.shellBg;
                ctx.beginPath();
                ctx.moveTo(0, height);
                ctx.lineTo(width / 2, 0);
                ctx.lineTo(width, height);
                ctx.closePath();
                ctx.fill();
            }
        }

        Text {
            id: colorTitle
            x: root.colorPanelPad
            y: root.colorPanelPad
            text: root.activeToolLabel + " Color"
            color: root.fg
            font.pixelSize: root.colorTitleSize
            font.bold: true
        }

        EyedropperButton {
            visible: root.customPickerOpen
            anchors.right: parent.right
            anchors.rightMargin: root.colorPanelPad
            anchors.verticalCenter: colorTitle.verticalCenter
            active: root.eyedropperSampling
            onClicked: root.activateEyedropper()
        }

        Grid {
            visible: !root.customPickerOpen
            x: root.colorPanelPad
            y: root.colorGridTop
            columns: 5
            rows: 3
            rowSpacing: root.colorSwatchGapY
            columnSpacing: root.colorSwatchGapX

            Repeater {
                model: root.swatchGrid

                delegate: Item {
                    width: root.colorSwatchCell
                    height: root.colorSwatchCell
                    readonly property bool swatchSelected: normalizeColor(modelData) === normalizeColor(root.selectedColor)
                    Rectangle {
                        visible: parent.swatchSelected
                        anchors.centerIn: parent
                        width: root.colorSwatchCell
                        height: root.colorSwatchCell
                        radius: width / 2
                        color: "#2c292a"
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: root.colorSwatchDot
                        height: width
                        radius: width / 2
                        color: String(modelData || "#ffffff")
                        border.width: normalizeColor(modelData) === "#ffffff" ? 1 : 0
                        border.color: "#cfcfcf"
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.chooseColor(String(modelData || "#000000"))
                    }
                }
            }
        }

        Canvas {
            id: colorWheel
            visible: !root.customPickerOpen
            x: root.colorPanelPad + Math.round(5 * root.colorPanelScale)
            y: root.colorGridTop + root.colorSwatchCell * 3 + root.colorSwatchGapY * 2 + Math.round(12 * root.colorPanelScale)
            width: root.colorWheelSize
            height: root.colorWheelSize
            onPaint: {
                var ctx = getContext("2d");
                var cx = width / 2;
                var cy = height / 2;
                var r = Math.min(width, height) / 2 - 2;
                ctx.clearRect(0, 0, width, height);
                for (var i = 0; i < 360; i += 6) {
                    ctx.beginPath();
                    ctx.moveTo(cx, cy);
                    ctx.arc(cx, cy, r, i * Math.PI / 180, (i + 8) * Math.PI / 180);
                    ctx.closePath();
                    ctx.fillStyle = root.hueColorAt(i / 360);
                    ctx.fill();
                }
                var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
                grad.addColorStop(0, "#ffffffff");
                grad.addColorStop(1, "#00ffffff");
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = "#99ffffff";
                ctx.lineWidth = 2;
                ctx.stroke();
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                // Expand the simple panel into the custom picker, keeping whatever
                // opened it (dot / add) as the source so the "+" highlight is
                // unaffected by switching modes.
                onClicked: root.toggleColorPanel(true, root.colorPanelSource || "dot")
            }
        }

        Item {
            id: customPicker
            visible: root.customPickerOpen
            anchors.fill: parent

            // ---- Saturation / value field: white -> pure hue, fading to black ----
            Rectangle {
                id: colorField
                x: 0
                width: parent.width
                y: root.colorFieldTop
                height: root.colorFieldHeight
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "#ffffff" }
                    GradientStop { position: 1.0; color: root.hueColorAt(root.hsvH) }
                }

                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#00000000" }
                        GradientStop { position: 1.0; color: "#ff000000" }
                    }
                }

                // Selector ring at (saturation, 1 - value).
                Rectangle {
                    width: root.colorSelectorRing
                    height: width
                    radius: width / 2
                    x: root.clamp01(root.hsvS) * parent.width - width / 2
                    y: (1 - root.clamp01(root.hsvV)) * parent.height - height / 2
                    color: "transparent"
                    border.width: Math.max(2, Math.round(3 * root.colorPanelScale))
                    border.color: root.fg
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.CrossCursor
                    function pick(mx, my) {
                        var nextS = mx / Math.max(1, width);
                        var nextV = 1 - my / Math.max(1, height);
                        if (root.eyedropperSampling) {
                            root.sampleWithEyedropper(root.hsvH, nextS, nextV);
                            return;
                        }
                        root.setHsv(root.hsvH, nextS, nextV);
                    }
                    onPressed: function(mouse) { pick(mouse.x, mouse.y); }
                    onPositionChanged: function(mouse) { pick(mouse.x, mouse.y); }
                }
            }

            // ---- Hue strip ----
            Canvas {
                id: hueStrip
                x: root.hueStripInset
                width: parent.width - root.hueStripInset * 2
                y: colorField.y + colorField.height + root.hueStripGap
                height: root.hueStripHeight
                onPaint: {
                    var ctx = getContext("2d");
                    ctx.clearRect(0, 0, width, height);
                    var g = ctx.createLinearGradient(0, 0, width, 0);
                    g.addColorStop(0.00, "#ff0000");
                    g.addColorStop(0.16, "#ffff00");
                    g.addColorStop(0.32, "#00ff00");
                    g.addColorStop(0.48, "#00ffff");
                    g.addColorStop(0.64, "#0000ff");
                    g.addColorStop(0.80, "#ff00ff");
                    g.addColorStop(1.00, "#ff0000");
                    ctx.fillStyle = g;
                    ctx.beginPath();
                    ctx.moveTo(height / 2, 0);
                    ctx.lineTo(width - height / 2, 0);
                    ctx.quadraticCurveTo(width, 0, width, height / 2);
                    ctx.quadraticCurveTo(width, height, width - height / 2, height);
                    ctx.lineTo(height / 2, height);
                    ctx.quadraticCurveTo(0, height, 0, height / 2);
                    ctx.quadraticCurveTo(0, 0, height / 2, 0);
                    ctx.fill();
                }

                // Hue handle at the current hue.
                Rectangle {
                    width: Math.round(18 * root.colorPanelScale)
                    height: Math.round(34 * root.colorPanelScale)
                    radius: Math.round(5 * root.colorPanelScale)
                    x: root.clamp01(root.hsvH) * parent.width - width / 2
                    y: (parent.height - height) / 2
                    color: "#f8f8f8"
                    border.width: 1
                    border.color: "#999999"
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    function pick(mx) { root.setHsv(mx / Math.max(1, width), root.hsvS, root.hsvV); }
                    onPressed: function(mouse) { pick(mouse.x); }
                    onPositionChanged: function(mouse) { pick(mouse.x); }
                }
            }

            // ---- Hex value + commit swatch ----
            Rectangle {
                id: hexField
                x: root.colorRowInset
                y: hueStrip.y + hueStrip.height + root.colorHexGap
                width: parent.width - root.colorRowInset * 2 - pickedColorButton.width
                    - Math.round(18 * root.colorPanelScale)
                height: root.colorHexHeight
                radius: Math.round(12 * root.colorPanelScale)
                color: root.pressedBg
                border.width: 1
                border.color: "#3affffff"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: Math.round(30 * root.colorPanelScale)
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.selectedColor.toUpperCase()
                    color: root.fg
                    font.pixelSize: Math.round(27 * root.colorPanelScale)
                }
            }

            PickedColorButton {
                id: pickedColorButton
                anchors.right: parent.right
                anchors.rightMargin: root.colorRowInset
                anchors.verticalCenter: hexField.verticalCenter
                colorValue: root.selectedColor
                onClicked: root.chooseColor(root.selectedColor)
            }
        }
    }

    PenOptionsPopover {
        id: penPopover
        objectName: "writingToolsPenPopover"
        visible: root.penPopoverOpen
        popScale: root.colorPanelScale
        y: toolbarShell.height + Math.round(14 * root.toolbarScale)
        anchorCenterX: root.penButtonCenterX
        minX: -root.x + 12
        maxX: root.hostWidth - root.x - 12
        maxHeight: Math.max(240, root.maxColorPanelHeight - y)
        variant: root.penVariant
        fountainSharpness: root.penFountainSharpness
        fountainPressure: root.penFountainPressure
        fountainStabilization: root.penFountainStabilization
        ballStabilization: root.penBallStabilization
        brushPressure: root.penBrushPressure
        brushStabilization: root.penBrushStabilization
        drawAndHold: root.penDrawAndHold
        scribbleToErase: root.penScribbleToErase
        eraseShapesHighlighter: root.penEraseShapesHighlighter
        circleToLasso: root.penCircleToLasso
        onVariantSelected: function(v) { root.setPenVariant(v); }
        onSliderChanged: function(key, value, summaryText) { root.setPenSlider(key, value, summaryText); }
        onToggleChanged: function(key, on, label) { root.setPenToggle(key, on, label); }
    }
}
