.pragma library
.import "GraphNodeSurfaceMetricContract.js" as SurfaceMetricContract

function _contract() {
    return SurfaceMetricContract.contract();
}

function _contractSection(key) {
    var value = _contract()[key];
    return value && typeof value === "object" ? value : {};
}

function _contractNumber(source, key) {
    var value = source ? Number(source[key]) : NaN;
    return isFinite(value) ? value : NaN;
}

function _metricNumber(source, key, fallback) {
    var value = source ? Number(source[key]) : NaN;
    if (!isFinite(value))
        value = fallback;
    return isFinite(value) ? value : 0.0;
}

function _metricBool(source, key, fallback) {
    if (!source || source[key] === undefined)
        return Boolean(fallback);
    return Boolean(source[key]);
}

function _inlineContract() {
    return _contractSection("inline");
}

function _standardContract() {
    return _contractSection("standard");
}

function _passiveContract() {
    return _contractSection("passive");
}

function _flowchartContract() {
    return _contractSection("flowchart");
}

function _planningContract() {
    return _contractSection("planning");
}

function _annotationContract() {
    return _contractSection("annotation");
}

function _groupBackdropContract() {
    return _contractSection("group_backdrop");
}

function _mediaContract() {
    return _contractSection("media");
}

var VIEWER_DEFAULT_WIDTH = 340.0;
var VIEWER_MIN_WIDTH = 320.0;
var VIEWER_DEFAULT_BODY_HEIGHT = 176.0;
var VIEWER_MIN_BODY_HEIGHT = 148.0;
var VIEWER_BODY_LEFT_MARGIN = 14.0;
var VIEWER_BODY_RIGHT_MARGIN = 14.0;
var VIEWER_BODY_BOTTOM_PADDING = 12.0;
var VIEWER_TITLE_RIGHT_MARGIN = 42.0;
var GRAPH_LABEL_PIXEL_SIZE_DEFAULT = 10;
var GRAPH_LABEL_PIXEL_SIZE_MIN = 8;
var GRAPH_LABEL_PIXEL_SIZE_MAX = 50;
var DYNAMIC_PORT_HANDLE_TARGET_RADIUS = 7.0;
var DYNAMIC_PORT_HANDLE_REST_RADIUS = 3.0;
var DYNAMIC_PORT_REMOVE_TARGET_WIDTH = 14.0;
var DYNAMIC_PORT_REMOVE_CENTER_INTERVAL = 9.0;
var DYNAMIC_PORT_HANDLE_BOTTOM_INSET = 4.0;
var DYNAMIC_PORT_HANDLE_CENTER_INTERVAL = 9.0;

function _variantLayouts(section) {
    var layouts = section ? section.variants : null;
    return layouts && typeof layouts === "object" ? layouts : {};
}

function _normalizedVariant(value, layouts, fallback) {
    var variant = String(value || "").trim().toLowerCase();
    return layouts && layouts[variant] !== undefined ? variant : fallback;
}

function inlineBodyHeight(node) {
    var inlineProperties = node && node.inline_properties ? node.inline_properties : [];
    var count = inlineProperties.length;
    if (count <= 0)
        return 0.0;
    var inlineContract = _inlineContract();
    var rowHeight = _contractNumber(inlineContract, "row_height");
    var textareaRowHeight = _contractNumber(inlineContract, "textarea_row_height");
    var rowSpacing = _contractNumber(inlineContract, "row_spacing");
    var sectionPadding = _contractNumber(inlineContract, "section_padding");
    var totalRowHeight = 0.0;
    for (var i = 0; i < inlineProperties.length; i++) {
        var propertyItem = inlineProperties[i];
        totalRowHeight += String(propertyItem && propertyItem.inline_editor || "").toLowerCase() === "textarea"
            ? textareaRowHeight
            : rowHeight;
    }
    return sectionPadding + totalRowHeight + Math.max(0, count - 1) * rowSpacing;
}

function settingsBandHeight(node) {
    var band = node && node.settings_band && typeof node.settings_band === "object"
        ? node.settings_band
        : null;
    var value = band ? Number(band.height) : 0.0;
    return isFinite(value) ? Math.max(0.0, value) : 0.0;
}

function settingsBandYOffset(node, heightOverride) {
    var band = node && node.settings_band && typeof node.settings_band === "object"
        ? node.settings_band
        : null;
    var bandTop = band ? Number(band.top) : NaN;
    var bandHeight = settingsBandHeight(node);
    if (!isFinite(bandTop) || bandHeight <= 0.0)
        return 0.0;
    var persistedHeight = bandTop + bandHeight;
    var activeHeight = _resolvedDimension(
        heightOverride !== undefined ? heightOverride : node && node.height,
        persistedHeight
    );
    return activeHeight - persistedHeight;
}

function _surfaceContentHeight(node, heightOverride, fallback) {
    return Math.max(
        0.0,
        _resolvedDimension(
            heightOverride !== undefined ? heightOverride : node && node.height,
            fallback
        ) - settingsBandHeight(node)
    );
}

function _visiblePortCounts(node) {
    var presentation = node && node.port_presentation ? node.port_presentation : null;
    var totalRows = presentation ? Number(presentation.total_row_count) : NaN;
    if (isFinite(totalRows) && totalRows >= 0) {
        return {
            "inputCount": totalRows,
            "outputCount": totalRows,
            "portCount": totalRows
        };
    }
    var ports = node && node.ports ? node.ports : [];
    var inputCount = 0;
    var outputCount = 0;
    for (var i = 0; i < ports.length; i++) {
        var port = ports[i];
        if (!port || port.exposed === false || port.handle_visible === false)
            continue;
        if (String(port.direction || "") === "in")
            inputCount += 1;
        else if (String(port.direction || "") === "out")
            outputCount += 1;
    }
    return {
        "inputCount": inputCount,
        "outputCount": outputCount,
        "portCount": Math.max(inputCount, outputCount)
    };
}

function _flowchartVariantLayout(variant) {
    var contract = _flowchartContract();
    var layouts = _variantLayouts(contract);
    var normalized = _normalizedVariant(variant, layouts, "process");
    var layout = layouts[normalized];
    return layout && typeof layout === "object" ? layout : {};
}

function flowchartBodyTextPlacement(variant) {
    var layout = _flowchartVariantLayout(variant);
    var value = String(layout && layout.body_text_placement || "").trim().toLowerCase();
    if (value === "below_shape" || value === "front_face" || value === "above_tail"
        || value === "cube_front_face")
        return value;
    return "center";
}

function _planningVariantLayout(variant) {
    var contract = _planningContract();
    var layouts = _variantLayouts(contract);
    var normalized = _normalizedVariant(variant, layouts, "task_card");
    var layout = layouts[normalized];
    return layout && typeof layout === "object" ? layout : {};
}

function _annotationVariantLayout(variant) {
    var contract = _annotationContract();
    var layouts = _variantLayouts(contract);
    var normalized = _normalizedVariant(variant, layouts, "sticky_note");
    var layout = layouts[normalized];
    return layout && typeof layout === "object" ? layout : {};
}

function _groupBackdropVariantLayout(variant) {
    var contract = _groupBackdropContract();
    var layouts = _variantLayouts(contract);
    var normalized = _normalizedVariant(variant, layouts, "group_backdrop");
    var layout = layouts[normalized];
    return layout && typeof layout === "object" ? layout : {};
}

function _mediaVariantLayout(variant) {
    var contract = _mediaContract();
    var layouts = _variantLayouts(contract);
    var normalized = _normalizedVariant(variant, layouts, "media_panel");
    var layout = layouts[normalized];
    return layout && typeof layout === "object" ? layout : {};
}

function _resolvedDimension(value, fallback) {
    var numeric = Number(value);
    if (!(numeric > 0.0))
        numeric = fallback;
    return isFinite(numeric) ? numeric : 0.0;
}

function _normalizedGraphLabelPixelSize(value) {
    var numeric = Math.round(Number(value));
    if (!isFinite(numeric))
        numeric = GRAPH_LABEL_PIXEL_SIZE_DEFAULT;
    return Math.max(GRAPH_LABEL_PIXEL_SIZE_MIN, Math.min(GRAPH_LABEL_PIXEL_SIZE_MAX, numeric));
}

// Projected port_height is authoritative for both cards and edge endpoints.
// This font-based row height is only a fallback for unprojected preview nodes;
// edge callers do not carry the card's graphLabelPixelSize override.
function _viewerPortRowHeight(graphLabelPixelSize) {
    var standard = _standardContract();
    return Math.max(
        _contractNumber(standard, "port_height"),
        _normalizedGraphLabelPixelSize(graphLabelPixelSize) + 8
    );
}

function _layoutReservesBodyMetrics(layout, bodyRegionLayout) {
    return bodyRegionLayout
        || Math.max(0.0, Number(layout.min_body_width) || 0.0) > 0.0
        || Math.max(0.0, Number(layout.min_body_height) || 0.0) > 0.0
        || Math.max(0.0, Number(layout.preferred_body_height) || 0.0) > 0.0;
}

// Fixed pill geometry for compact Data > Control surfaces; fallbacks mirror
// NUMBER_SLIDER_* constants in ea_node_editor/nodes/builtins/data_control.py
// and TRIGGER_* constants in ea_node_editor/nodes/builtins/core.py.
var BOOLEAN_TOGGLE_SURFACE_VARIANT = "boolean_toggle";
var NUMBER_SLIDER_SURFACE_VARIANT = "number_slider";
var PANEL_SURFACE_VARIANT = "panel";
var SELECT_SURFACE_VARIANT = "select";
var TRIGGER_SURFACE_VARIANT = "trigger";
var NUMBER_SLIDER_PILL_HEIGHT = 40.0;
var NUMBER_SLIDER_DEFAULT_WIDTH = 280.0;
var NUMBER_SLIDER_MIN_WIDTH = 220.0;
var TRIGGER_DEFAULT_WIDTH = 160.0;
var TRIGGER_MIN_WIDTH = 120.0;
var NUMBER_SLIDER_BODY_SIDE_MARGIN = 10.0;
var PANEL_DEFAULT_WIDTH = 280.0;
var PANEL_DEFAULT_HEIGHT = 180.0;
var PANEL_MIN_WIDTH = 120.0;
var PANEL_MIN_HEIGHT = 40.0;
var PANEL_BODY_SIDE_MARGIN = 12.0;
var PANEL_PORT_CENTER_OFFSET = 20.0;

function isNumberSliderSurface(node) {
    return String(node && node.surface_family || "standard") === "standard"
        && String(node && node.surface_variant || "") === NUMBER_SLIDER_SURFACE_VARIANT;
}

function isBooleanToggleSurface(node) {
    return String(node && node.surface_family || "standard") === "standard"
        && String(node && node.surface_variant || "") === BOOLEAN_TOGGLE_SURFACE_VARIANT;
}

function isPanelSurface(node) {
    return String(node && node.surface_family || "standard") === "standard"
        && String(node && node.surface_variant || "") === PANEL_SURFACE_VARIANT;
}

function isSelectSurface(node) {
    return String(node && node.surface_family || "standard") === "standard"
        && String(node && node.surface_variant || "") === SELECT_SURFACE_VARIANT;
}

function isTriggerSurface(node) {
    return String(node && node.surface_family || "standard") === "standard"
        && String(node && node.surface_variant || "") === TRIGGER_SURFACE_VARIANT;
}

function isCompactPillSurface(node) {
    return isNumberSliderSurface(node) || isBooleanToggleSurface(node)
        || isSelectSurface(node) || isTriggerSurface(node);
}

function _compactPillSurfaceMetrics(node, source) {
    var standard = _standardContract();
    var pillHeight = _metricNumber(source, "default_height", NUMBER_SLIDER_PILL_HEIGHT);
    var fallbackDefaultWidth = isTriggerSurface(node) ? TRIGGER_DEFAULT_WIDTH : NUMBER_SLIDER_DEFAULT_WIDTH;
    var fallbackMinWidth = isTriggerSurface(node) ? TRIGGER_MIN_WIDTH : NUMBER_SLIDER_MIN_WIDTH;
    return {
        "default_width": _metricNumber(source, "default_width", fallbackDefaultWidth),
        "default_height": pillHeight,
        "min_width": _metricNumber(source, "min_width", fallbackMinWidth),
        "min_height": _metricNumber(source, "min_height", pillHeight),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(standard, "collapsed_width")),
        "collapsed_height": _metricNumber(source, "collapsed_height", _contractNumber(standard, "collapsed_height")),
        "header_height": _metricNumber(source, "header_height", 0.0),
        "header_top_margin": _metricNumber(source, "header_top_margin", 0.0),
        "body_top": _metricNumber(source, "body_top", 0.0),
        "body_height": _metricNumber(source, "body_height", pillHeight),
        "port_top": _metricNumber(source, "port_top", 0.0),
        "port_height": _metricNumber(source, "port_height", pillHeight),
        "port_center_offset": _metricNumber(source, "port_center_offset", pillHeight * 0.5),
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(standard, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(standard, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(standard, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", 0.0),
        "title_height": _metricNumber(source, "title_height", 0.0),
        "title_left_margin": _metricNumber(source, "title_left_margin", 0.0),
        "title_right_margin": _metricNumber(source, "title_right_margin", 0.0),
        "title_centered": false,
        "body_left_margin": _metricNumber(source, "body_left_margin", NUMBER_SLIDER_BODY_SIDE_MARGIN),
        "body_right_margin": _metricNumber(source, "body_right_margin", NUMBER_SLIDER_BODY_SIDE_MARGIN),
        "body_bottom_margin": _metricNumber(source, "body_bottom_margin", 0.0),
        "standard_title_full_width": _metricNumber(source, "standard_title_full_width", 0.0),
        "standard_left_label_width": _metricNumber(source, "standard_left_label_width", 0.0),
        "standard_right_label_width": _metricNumber(source, "standard_right_label_width", 0.0),
        "standard_port_gutter": _metricNumber(source, "standard_port_gutter", 0.0),
        "standard_center_gap": _metricNumber(source, "standard_center_gap", 0.0),
        "standard_port_label_min_width": _metricNumber(source, "standard_port_label_min_width", 0.0),
        "use_host_chrome": _metricBool(source, "use_host_chrome", true),
        "use_host_shadow": _metricBool(source, "use_host_shadow", true)
    };
}

function _panelSurfaceMetrics(node, source, heightOverride) {
    var standard = _standardContract();
    var activeHeight = _surfaceContentHeight(
        node,
        heightOverride,
        _metricNumber(source, "default_height", PANEL_DEFAULT_HEIGHT)
    );
    return {
        "default_width": _metricNumber(source, "default_width", PANEL_DEFAULT_WIDTH),
        "default_height": _metricNumber(source, "default_height", PANEL_DEFAULT_HEIGHT),
        "min_width": _metricNumber(source, "min_width", PANEL_MIN_WIDTH),
        "min_height": _metricNumber(source, "min_height", PANEL_MIN_HEIGHT),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(standard, "collapsed_width")),
        "collapsed_height": _metricNumber(source, "collapsed_height", _contractNumber(standard, "collapsed_height")),
        "header_height": 0.0,
        "header_top_margin": 0.0,
        "body_top": 0.0,
        "body_height": activeHeight,
        "port_top": 0.0,
        "port_height": 0.0,
        "port_center_offset": PANEL_PORT_CENTER_OFFSET,
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(standard, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(standard, "port_dot_radius")),
        "resize_handle_size": _metricNumber(source, "resize_handle_size", _contractNumber(standard, "resize_handle_size")),
        "title_top": 0.0,
        "title_height": 0.0,
        "title_left_margin": 0.0,
        "title_right_margin": 0.0,
        "title_centered": false,
        "body_left_margin": PANEL_BODY_SIDE_MARGIN,
        "body_right_margin": PANEL_BODY_SIDE_MARGIN,
        "body_bottom_margin": 0.0,
        "standard_title_full_width": _contractNumber(standard, "standard_title_full_width"),
        "standard_left_label_width": 0.0,
        "standard_right_label_width": 0.0,
        "standard_port_gutter": _contractNumber(standard, "standard_port_gutter"),
        "standard_center_gap": _contractNumber(standard, "standard_center_gap"),
        "standard_port_label_min_width": 0.0,
        "use_host_chrome": true,
        "use_host_shadow": true
    };
}

function _standardSurfaceMetrics(node, source, graphLabelPixelSize, heightOverride) {
    var standard = _standardContract();
    var surfaceSpec = node && node.surface_spec && typeof node.surface_spec === "object" ? node.surface_spec : {};
    var layout = surfaceSpec.layout && typeof surfaceSpec.layout === "object" ? surfaceSpec.layout : {};
    var bodyRegionLayout = String(layout.content_region || "host") === "body";
    var bodyLayoutMetrics = _layoutReservesBodyMetrics(layout, bodyRegionLayout);
    var portCount = _visiblePortCounts(node).portCount;
    var headerHeight = _contractNumber(standard, "header_height");
    var inlineHeight = inlineBodyHeight(node);
    var portHeight = _metricNumber(
        source, "port_height",
        _viewerPortRowHeight(graphLabelPixelSize)
    );
    var portCenterOffset = Math.max(
        _metricNumber(source, "port_center_offset", _contractNumber(standard, "port_center_offset")),
        portHeight * 0.5
    );
    var bottomPadding = _dynamicPortBottomPadding(
        node,
        portCount,
        portHeight,
        portCenterOffset,
        _contractNumber(standard, "bottom_padding")
    );
    var bodyTop = _contractNumber(standard, "body_top");
    var resolvedBodyTop = _metricNumber(source, "body_top", bodyTop);
    var bodyHeight = bodyLayoutMetrics
        ? inlineHeight
        : _metricNumber(source, "body_height", inlineHeight);
    if (bodyLayoutMetrics) {
        bodyHeight = Math.max(
            bodyHeight,
            Math.max(0.0, Number(layout.min_body_height) || 0.0),
            Math.max(0.0, Number(layout.preferred_body_height) || 0.0)
        );
    }
    var defaultBodyHeight = bodyHeight;
    if (bodyRegionLayout) {
        var activeHeight = _surfaceContentHeight(
            node,
            heightOverride,
            0.0
        );
        if (activeHeight > 0.0) {
            bodyHeight = Math.max(
                bodyHeight,
                activeHeight - resolvedBodyTop - portCount * portHeight - bottomPadding
            );
        }
    }
    var bodyLayoutMinWidth = bodyLayoutMetrics
        ? _contractNumber(standard, "body_left_margin")
            + Math.max(0.0, Number(layout.min_body_width) || 0.0)
            + _contractNumber(standard, "body_right_margin")
        : 0.0;
    var contentHeight = resolvedBodyTop + defaultBodyHeight + portCount * portHeight + bottomPadding;
    return {
        "default_width": Math.max(
            _metricNumber(source, "default_width", _contractNumber(standard, "default_width")),
            _metricNumber(source, "min_width", _contractNumber(standard, "min_width")),
            bodyLayoutMinWidth
        ),
        "default_height": Math.max(
            _metricNumber(
                source,
                "default_height",
                contentHeight
            ),
            contentHeight
        ),
        "min_width": Math.max(
            _metricNumber(source, "min_width", _contractNumber(standard, "min_width")),
            bodyLayoutMinWidth
        ),
        "min_height": Math.max(
            _metricNumber(source, "min_height", _contractNumber(standard, "min_height")),
            contentHeight
        ),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(standard, "collapsed_width")),
        "collapsed_height": _metricNumber(source, "collapsed_height", _contractNumber(standard, "collapsed_height")),
        "header_height": _metricNumber(source, "header_height", headerHeight),
        "header_top_margin": _metricNumber(source, "header_top_margin", _contractNumber(standard, "header_top_margin")),
        "body_top": resolvedBodyTop,
        "body_height": bodyHeight,
        "port_top": Math.max(
            bodyRegionLayout ? resolvedBodyTop + bodyHeight : _metricNumber(source, "port_top", resolvedBodyTop + bodyHeight),
            resolvedBodyTop + bodyHeight
        ),
        "port_height": portHeight,
        "port_center_offset": portCenterOffset,
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(standard, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(standard, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(standard, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", _contractNumber(standard, "header_top_margin")),
        "title_height": _metricNumber(source, "title_height", headerHeight),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(standard, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(
            source,
            "title_right_margin",
            _contractNumber(standard, "title_right_margin")
        ),
        "title_centered": _metricBool(source, "title_centered", false),
        "body_left_margin": _metricNumber(
            source,
            "body_left_margin",
            _contractNumber(standard, "body_left_margin")
        ),
        "body_right_margin": _metricNumber(
            source,
            "body_right_margin",
            _contractNumber(standard, "body_right_margin")
        ),
        "body_bottom_margin": _metricNumber(source, "body_bottom_margin", bottomPadding),
        "standard_title_full_width": _metricNumber(
            source,
            "standard_title_full_width",
            _contractNumber(standard, "standard_title_full_width")
        ),
        "standard_left_label_width": _metricNumber(
            source,
            "standard_left_label_width",
            _contractNumber(standard, "standard_left_label_width")
        ),
        "standard_right_label_width": _metricNumber(
            source,
            "standard_right_label_width",
            _contractNumber(standard, "standard_right_label_width")
        ),
        "standard_port_gutter": _metricNumber(
            source,
            "standard_port_gutter",
            _contractNumber(standard, "standard_port_gutter")
        ),
        "standard_center_gap": _metricNumber(
            source,
            "standard_center_gap",
            _contractNumber(standard, "standard_center_gap")
        ),
        "standard_port_label_min_width": _metricNumber(
            source,
            "standard_port_label_min_width",
            _contractNumber(standard, "standard_port_label_min_width")
        ),
        "use_host_chrome": _metricBool(source, "use_host_chrome", Boolean(standard.use_host_chrome)),
        "use_host_shadow": _metricBool(source, "use_host_shadow", standard.use_host_shadow !== false)
    };
}

function _dynamicPortBottomPadding(node, portCount, portHeight, portCenterOffset, basePadding) {
    var groups = node && node.dynamic_port_groups ? node.dynamic_port_groups : [];
    if (groups.length <= 0)
        return basePadding;
    var bottommostAddCenter = NaN;
    for (var groupIndex = 0; groupIndex < groups.length; ++groupIndex) {
        var group = groups[groupIndex] || {};
        var direction = String(group.direction || "").trim().toLowerCase();
        if (direction !== "in" && direction !== "out")
            continue;
        var groupKeys = group.port_keys || [];
        var groupKeyLookup = {};
        for (var keyIndex = 0; keyIndex < groupKeys.length; ++keyIndex)
            groupKeyLookup[String(groupKeys[keyIndex] || "")] = true;
        var directionPorts = visiblePortsForDirection(node, direction);
        var lastGroupRow = NaN;
        for (var portIndex = 0; portIndex < directionPorts.length; ++portIndex) {
            var port = directionPorts[portIndex] || {};
            if (!groupKeyLookup[String(port.key || "")])
                continue;
            var layoutRow = Number(port.layout_row);
            lastGroupRow = isFinite(layoutRow) && layoutRow >= 0
                ? layoutRow
                : portIndex;
        }
        var addCenter = isFinite(lastGroupRow)
            ? portCenterOffset
                + lastGroupRow * portHeight
                + DYNAMIC_PORT_HANDLE_CENTER_INTERVAL
            : portCenterOffset + directionPorts.length * portHeight;
        bottommostAddCenter = isFinite(bottommostAddCenter)
            ? Math.max(bottommostAddCenter, addCenter)
            : addCenter;
    }
    if (!isFinite(bottommostAddCenter))
        return basePadding;
    return Math.max(
        basePadding,
        bottommostAddCenter
            // Hover targets may overflow the chrome; only the resting dot sizes it.
            + DYNAMIC_PORT_HANDLE_REST_RADIUS
            + DYNAMIC_PORT_HANDLE_BOTTOM_INSET
            - portCount * portHeight
    );
}

function _flowchartSurfaceMetrics(node, source, heightOverride) {
    var contract = _flowchartContract();
    var layout = _flowchartVariantLayout(node && node.surface_variant);
    var portCount = _visiblePortCounts(node).portCount;
    var bodyHeight = _metricNumber(source, "body_height", inlineBodyHeight(node));
    var titleHeight = _contractNumber(contract, "title_height");
    var portHeight = _contractNumber(contract, "port_height");
    var inlineGap = _contractNumber(contract, "inline_gap");
    var defaultPortSectionTop = _contractNumber(contract, "port_section_top");
    var basePortSectionTop = bodyHeight > 0.0
        ? _contractNumber(layout, "title_top") + titleHeight + inlineGap + bodyHeight + inlineGap
        : defaultPortSectionTop;
    var defaultHeight = Math.max(
        _contractNumber(layout, "min_height"),
        basePortSectionTop + portCount * portHeight + _contractNumber(layout, "body_bottom_margin")
    );
    var defaultWidth = _contractNumber(layout, "default_width");
    var minWidth = _contractNumber(layout, "min_width");
    if (Boolean(layout.square)) {
        defaultWidth = Math.max(defaultWidth, defaultHeight);
        minWidth = Math.max(minWidth, _contractNumber(layout, "min_height"));
    }
    defaultHeight = _metricNumber(source, "default_height", defaultHeight);
    defaultWidth = _metricNumber(source, "default_width", defaultWidth);
    minWidth = _metricNumber(source, "min_width", minWidth);
    var contentMinHeight = basePortSectionTop + portCount * portHeight + _contractNumber(layout, "body_bottom_margin");
    var minHeight = Math.max(
        _metricNumber(source, "min_height", _contractNumber(layout, "min_height")),
        contentMinHeight
    );
    var activeHeight = _surfaceContentHeight(
        node,
        settingsBandHeight(node) > 0.0 ? heightOverride : undefined,
        defaultHeight
    );
    var titleTop = bodyHeight > 0.0
        ? _contractNumber(layout, "title_top")
        : Math.max(12.0, (activeHeight - titleHeight) * 0.5);
    titleTop = _metricNumber(source, "title_top", titleTop);
    var bodyTop = _metricNumber(source, "body_top", titleTop + titleHeight + inlineGap);
    var portSectionTop = bodyHeight > 0.0
        ? bodyTop + bodyHeight + inlineGap
        : defaultPortSectionTop;
    var availablePortHeight = Math.max(
        portCount * portHeight,
        activeHeight - portSectionTop - _contractNumber(layout, "body_bottom_margin")
    );
    return {
        "default_width": defaultWidth,
        "default_height": defaultHeight,
        "min_width": minWidth,
        "min_height": minHeight,
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(contract, "collapsed_width")),
        "collapsed_height": _metricNumber(source, "collapsed_height", _contractNumber(contract, "collapsed_height")),
        "header_height": _metricNumber(source, "header_height", 0.0),
        "header_top_margin": _metricNumber(source, "header_top_margin", 0.0),
        "body_top": bodyTop,
        "body_height": bodyHeight,
        "port_top": _metricNumber(
            source,
            "port_top",
            portSectionTop + Math.max(0.0, (availablePortHeight - portCount * portHeight) * 0.5)
        ),
        "port_height": _metricNumber(source, "port_height", portHeight),
        "port_center_offset": _metricNumber(
            source,
            "port_center_offset",
            _contractNumber(contract, "port_center_offset")
        ),
        "port_side_margin": _metricNumber(source, "port_side_margin", 0.0),
        "port_dot_radius": _metricNumber(
            source,
            "port_dot_radius",
            _contractNumber(contract, "port_dot_radius")
        ),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(contract, "resize_handle_size")
        ),
        "title_top": titleTop,
        "title_height": _metricNumber(source, "title_height", titleHeight),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(layout, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(
            source,
            "title_right_margin",
            _contractNumber(layout, "title_right_margin")
        ),
        "title_centered": _metricBool(source, "title_centered", true),
        "body_left_margin": _metricNumber(
            source,
            "body_left_margin",
            _contractNumber(layout, "body_left_margin")
        ),
        "body_right_margin": _metricNumber(
            source,
            "body_right_margin",
            _contractNumber(layout, "body_right_margin")
        ),
        "body_bottom_margin": _metricNumber(
            source,
            "body_bottom_margin",
            _contractNumber(layout, "body_bottom_margin")
        ),
        "use_host_chrome": _metricBool(source, "use_host_chrome", false),
        "use_host_shadow": _metricBool(source, "use_host_shadow", true)
    };
}

function _passivePanelSurfaceMetrics(node, source, layout, heightOverride) {
    var passive = _passiveContract();
    var activeHeight = _surfaceContentHeight(
        node,
        settingsBandHeight(node) > 0.0 ? heightOverride : undefined,
        _contractNumber(layout, "default_height")
    );
    var bodyTop = _metricNumber(source, "body_top", _contractNumber(layout, "body_top"));
    var bodyBottomMargin = _metricNumber(source, "body_bottom_margin", _contractNumber(layout, "body_bottom_margin"));
    var bodyHeight = _metricNumber(
        source,
        "body_height",
        Math.max(_contractNumber(layout, "body_height"), activeHeight - bodyTop - bodyBottomMargin)
    );
    return {
        "default_width": _metricNumber(source, "default_width", _contractNumber(layout, "default_width")),
        "default_height": _metricNumber(source, "default_height", _contractNumber(layout, "default_height")),
        "min_width": _metricNumber(source, "min_width", _contractNumber(layout, "min_width")),
        "min_height": _metricNumber(source, "min_height", _contractNumber(layout, "min_height")),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(_standardContract(), "collapsed_width")),
        "collapsed_height": _metricNumber(
            source,
            "collapsed_height",
            _contractNumber(_standardContract(), "collapsed_height")
        ),
        "header_height": _metricNumber(source, "header_height", 0.0),
        "header_top_margin": _metricNumber(source, "header_top_margin", 0.0),
        "body_top": bodyTop,
        "body_height": bodyHeight,
        "port_top": _metricNumber(source, "port_top", activeHeight - bodyBottomMargin),
        "port_height": _metricNumber(source, "port_height", 0.0),
        "port_center_offset": _metricNumber(source, "port_center_offset", 0.0),
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(passive, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(passive, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(passive, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", _contractNumber(layout, "title_top")),
        "title_height": _metricNumber(source, "title_height", _contractNumber(layout, "title_height")),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(layout, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(
            source,
            "title_right_margin",
            _contractNumber(layout, "title_right_margin")
        ),
        "title_centered": _metricBool(source, "title_centered", Boolean(layout.title_centered)),
        "body_left_margin": _metricNumber(
            source,
            "body_left_margin",
            _contractNumber(layout, "body_left_margin")
        ),
        "body_right_margin": _metricNumber(
            source,
            "body_right_margin",
            _contractNumber(layout, "body_right_margin")
        ),
        "body_bottom_margin": bodyBottomMargin,
        "use_host_chrome": _metricBool(
            source,
            "use_host_chrome",
            layout && layout.use_host_chrome !== undefined ? Boolean(layout.use_host_chrome) : true
        ),
        "use_host_shadow": _metricBool(
            source,
            "use_host_shadow",
            layout && layout.use_host_shadow !== undefined ? Boolean(layout.use_host_shadow) : true
        )
    };
}

function _groupBackdropSurfaceMetrics(node, source, graphLabelPixelSize, heightOverride) {
    var layout = _groupBackdropVariantLayout(node && node.surface_variant);
    var passive = _passiveContract();
    var activeHeight = _surfaceContentHeight(
        node,
        settingsBandHeight(node) > 0.0 ? heightOverride : undefined,
        _contractNumber(layout, "default_height")
    );
    var bodyTop = _metricNumber(source, "body_top", _contractNumber(layout, "body_top"));
    var bodyBottomMargin = _metricNumber(source, "body_bottom_margin", _contractNumber(layout, "body_bottom_margin"));
    var bodyHeight = _metricNumber(
        source,
        "body_height",
        Math.max(0.0, activeHeight - bodyTop - bodyBottomMargin)
    );
    return {
        "default_width": _metricNumber(source, "default_width", _contractNumber(layout, "default_width")),
        "default_height": _metricNumber(source, "default_height", _contractNumber(layout, "default_height")),
        "min_width": _metricNumber(source, "min_width", _contractNumber(layout, "min_width")),
        "min_height": _metricNumber(source, "min_height", _contractNumber(layout, "min_height")),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(_standardContract(), "collapsed_width")),
        "collapsed_height": _metricNumber(
            source,
            "collapsed_height",
            _contractNumber(_standardContract(), "collapsed_height")
        ),
        "header_height": _metricNumber(source, "header_height", 0.0),
        "header_top_margin": _metricNumber(source, "header_top_margin", 0.0),
        "body_top": bodyTop,
        "body_height": bodyHeight,
        "port_top": _metricNumber(source, "port_top", activeHeight - bodyBottomMargin),
        "port_height": _metricNumber(source, "port_height", 0.0),
        "port_center_offset": _metricNumber(source, "port_center_offset", 0.0),
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(passive, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(passive, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(passive, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", _contractNumber(layout, "title_top")),
        "title_height": _metricNumber(source, "title_height", _contractNumber(layout, "title_height")),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(layout, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(
            source,
            "title_right_margin",
            _contractNumber(layout, "title_right_margin")
        ),
        "title_centered": _metricBool(source, "title_centered", Boolean(layout.title_centered)),
        "body_left_margin": _metricNumber(
            source,
            "body_left_margin",
            _contractNumber(layout, "body_left_margin")
        ),
        "body_right_margin": _metricNumber(
            source,
            "body_right_margin",
            _contractNumber(layout, "body_right_margin")
        ),
        "body_bottom_margin": bodyBottomMargin,
        "use_host_chrome": _metricBool(
            source,
            "use_host_chrome",
            layout && layout.use_host_chrome !== undefined ? Boolean(layout.use_host_chrome) : true
        ),
        "use_host_shadow": _metricBool(
            source,
            "use_host_shadow",
            layout && layout.use_host_shadow !== undefined ? Boolean(layout.use_host_shadow) : true
        )
    };
}

function _mediaSurfaceMetrics(node, source, heightOverride, graphLabelPixelSize) {
    var layout = _mediaVariantLayout(node && node.surface_variant);
    var passive = _passiveContract();
    var portCount = _visiblePortCounts(node).portCount;
    var portHeight = _metricNumber(source, "port_height", _viewerPortRowHeight(graphLabelPixelSize));
    var defaultBodyHeight = Math.max(
        _contractNumber(layout, "min_body_height"),
        _contractNumber(layout, "default_height")
            - _contractNumber(layout, "body_top")
            - _contractNumber(layout, "body_bottom_margin")
    );
    var bodyTop = _metricNumber(source, "body_top", _contractNumber(layout, "body_top"));
    var bodyBottomMargin = _metricNumber(source, "body_bottom_margin", _contractNumber(layout, "body_bottom_margin"));
    var defaultHeight = Math.max(
        _metricNumber(source, "default_height", 0.0),
        bodyTop + defaultBodyHeight + portCount * portHeight + bodyBottomMargin
    );
    var minHeight = Math.max(
        _metricNumber(source, "min_height", 0.0),
        bodyTop
            + _contractNumber(layout, "min_body_height")
            + portCount * portHeight
            + bodyBottomMargin
    );
    var activeHeight = _surfaceContentHeight(
        node,
        settingsBandHeight(node) > 0.0 ? heightOverride : undefined,
        defaultHeight
    );
    var bodyHeight = Math.max(
        _contractNumber(layout, "min_body_height"),
        activeHeight - bodyTop - portCount * portHeight - bodyBottomMargin
    );
    return {
        "default_width": _metricNumber(source, "default_width", _contractNumber(layout, "default_width")),
        "default_height": defaultHeight,
        "min_width": _metricNumber(source, "min_width", _contractNumber(layout, "min_width")),
        "min_height": minHeight,
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(_standardContract(), "collapsed_width")),
        "collapsed_height": _metricNumber(
            source,
            "collapsed_height",
            _contractNumber(_standardContract(), "collapsed_height")
        ),
        "header_height": _metricNumber(source, "header_height", 0.0),
        "header_top_margin": _metricNumber(source, "header_top_margin", 0.0),
        "body_top": bodyTop,
        "body_height": bodyHeight,
        "port_top": bodyTop + bodyHeight,
        "port_height": portHeight,
        "port_center_offset": Math.max(
            _metricNumber(source, "port_center_offset", 0.0),
            portHeight * 0.5
        ),
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(passive, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(passive, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(passive, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", _contractNumber(layout, "title_top")),
        "title_height": _metricNumber(source, "title_height", _contractNumber(layout, "title_height")),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(layout, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(
            source,
            "title_right_margin",
            _contractNumber(layout, "title_right_margin")
        ),
        "title_centered": _metricBool(source, "title_centered", Boolean(layout.title_centered)),
        "body_left_margin": _metricNumber(
            source,
            "body_left_margin",
            _contractNumber(layout, "body_left_margin")
        ),
        "body_right_margin": _metricNumber(
            source,
            "body_right_margin",
            _contractNumber(layout, "body_right_margin")
        ),
        "body_bottom_margin": bodyBottomMargin,
        "use_host_chrome": _metricBool(source, "use_host_chrome", true),
        "use_host_shadow": _metricBool(source, "use_host_shadow", true)
    };
}

function _viewerSurfaceMetrics(node, source, _widthOverride, heightOverride, graphLabelPixelSize) {
    var standard = _standardContract();
    var portCount = _visiblePortCounts(node).portCount;
    var headerHeight = _contractNumber(standard, "header_height");
    var bodyTop = _contractNumber(standard, "body_top");
    var resolvedBodyTop = _metricNumber(source, "body_top", bodyTop);
    var portHeight = _metricNumber(
        source, "port_height",
        _viewerPortRowHeight(graphLabelPixelSize)
    );
    var inlineHeight = inlineBodyHeight(node);
    var defaultBodyHeight = Math.max(VIEWER_DEFAULT_BODY_HEIGHT, inlineHeight);
    var minBodyHeight = Math.max(VIEWER_MIN_BODY_HEIGHT, inlineHeight);
    var bottomPadding = _dynamicPortBottomPadding(
        node, portCount, portHeight,
        _metricNumber(source, "port_center_offset", _contractNumber(standard, "port_center_offset")),
        VIEWER_BODY_BOTTOM_PADDING
    );
    var defaultHeight = resolvedBodyTop + defaultBodyHeight + portCount * portHeight + bottomPadding;
    var minHeight = resolvedBodyTop + minBodyHeight + portCount * portHeight + bottomPadding;
    var resolvedDefaultHeight = Math.max(
        _metricNumber(source, "default_height", defaultHeight),
        defaultHeight
    );
    var activeHeight = _surfaceContentHeight(
        node,
        heightOverride,
        resolvedDefaultHeight
    );
    var bodyBottomMargin = Math.max(_metricNumber(source, "body_bottom_margin", bottomPadding), bottomPadding);
    var bodyHeight = Math.max(
        minBodyHeight,
        activeHeight - resolvedBodyTop - portCount * portHeight - bodyBottomMargin
    );
    return {
        "default_width": _metricNumber(source, "default_width", VIEWER_DEFAULT_WIDTH),
        "default_height": resolvedDefaultHeight,
        "min_width": _metricNumber(source, "min_width", VIEWER_MIN_WIDTH),
        "min_height": Math.max(
            _metricNumber(source, "min_height", minHeight),
            minHeight
        ),
        "collapsed_width": _metricNumber(source, "collapsed_width", _contractNumber(standard, "collapsed_width")),
        "collapsed_height": _metricNumber(source, "collapsed_height", _contractNumber(standard, "collapsed_height")),
        "header_height": _metricNumber(source, "header_height", headerHeight),
        "header_top_margin": _metricNumber(source, "header_top_margin", _contractNumber(standard, "header_top_margin")),
        "body_top": resolvedBodyTop,
        "body_height": bodyHeight,
        "port_top": resolvedBodyTop + bodyHeight,
        "port_height": portHeight,
        "port_center_offset": _metricNumber(
            source,
            "port_center_offset",
            _contractNumber(standard, "port_center_offset")
        ),
        "port_side_margin": _metricNumber(source, "port_side_margin", _contractNumber(standard, "port_side_margin")),
        "port_dot_radius": _metricNumber(source, "port_dot_radius", _contractNumber(standard, "port_dot_radius")),
        "resize_handle_size": _metricNumber(
            source,
            "resize_handle_size",
            _contractNumber(standard, "resize_handle_size")
        ),
        "title_top": _metricNumber(source, "title_top", _contractNumber(standard, "header_top_margin")),
        "title_height": _metricNumber(source, "title_height", headerHeight),
        "title_left_margin": _metricNumber(
            source,
            "title_left_margin",
            _contractNumber(standard, "title_left_margin")
        ),
        "title_right_margin": _metricNumber(source, "title_right_margin", VIEWER_TITLE_RIGHT_MARGIN),
        "title_centered": _metricBool(source, "title_centered", false),
        "body_left_margin": _metricNumber(source, "body_left_margin", VIEWER_BODY_LEFT_MARGIN),
        "body_right_margin": _metricNumber(source, "body_right_margin", VIEWER_BODY_RIGHT_MARGIN),
        "body_bottom_margin": bodyBottomMargin,
        "use_host_chrome": _metricBool(source, "use_host_chrome", Boolean(standard.use_host_chrome)),
        "use_host_shadow": _metricBool(source, "use_host_shadow", standard.use_host_shadow !== false),
        "standard_title_full_width": _metricNumber(
            source,
            "standard_title_full_width",
            _contractNumber(standard, "standard_title_full_width")
        ),
        "standard_left_label_width": _metricNumber(
            source,
            "standard_left_label_width",
            _contractNumber(standard, "standard_left_label_width")
        ),
        "standard_right_label_width": _metricNumber(
            source,
            "standard_right_label_width",
            _contractNumber(standard, "standard_right_label_width")
        ),
        "standard_port_gutter": _metricNumber(
            source,
            "standard_port_gutter",
            _contractNumber(standard, "standard_port_gutter")
        ),
        "standard_center_gap": _metricNumber(
            source,
            "standard_center_gap",
            _contractNumber(standard, "standard_center_gap")
        ),
        "standard_port_label_min_width": _metricNumber(
            source,
            "standard_port_label_min_width",
            _contractNumber(standard, "standard_port_label_min_width")
        )
    };
}

function surfaceMetrics(node, widthOverride, heightOverride, graphLabelPixelSize) {
    var source = node && node.surface_metrics ? node.surface_metrics : null;
    var family = String(node && node.surface_family || "standard");
    if (isCompactPillSurface(node))
        return _compactPillSurfaceMetrics(node, source);
    if (isPanelSurface(node))
        return _panelSurfaceMetrics(node, source, heightOverride);
    if (family === "flowchart")
        return _flowchartSurfaceMetrics(node, source, heightOverride);
    if (family === "planning")
        return _passivePanelSurfaceMetrics(
            node,
            source,
            _planningVariantLayout(node && node.surface_variant),
            heightOverride
        );
    if (family === "annotation")
        return _passivePanelSurfaceMetrics(
            node,
            source,
            _annotationVariantLayout(node && node.surface_variant),
            heightOverride
        );
    if (family === "group_backdrop")
        return _groupBackdropSurfaceMetrics(node, source, graphLabelPixelSize, heightOverride);
    if (family === "media")
        return _mediaSurfaceMetrics(node, source, heightOverride, graphLabelPixelSize);
    if (family === "viewer")
        return _viewerSurfaceMetrics(node, source, widthOverride, heightOverride, graphLabelPixelSize);
    return _standardSurfaceMetrics(node, source, graphLabelPixelSize, heightOverride);
}

function _normalizedFlowchartVariant(value) {
    return _normalizedVariant(value, _variantLayouts(_flowchartContract()), "process");
}

function _flowchartBounds(width, height) {
    if (!(width > 0.0) || !(height > 0.0)) {
        var safeWidth = Math.max(1.0, Number(width) || 0.0);
        var safeHeight = Math.max(1.0, Number(height) || 0.0);
        return {
            "left": 0.0,
            "top": 0.0,
            "right": Math.max(0.0, Number(width) || 0.0),
            "bottom": Math.max(0.0, Number(height) || 0.0),
            "widthValue": safeWidth,
            "heightValue": safeHeight,
            "centerX": Math.max(0.0, Number(width) || 0.0) * 0.5,
            "centerY": Math.max(0.0, Number(height) || 0.0) * 0.5
        };
    }
    var inset = 0.5;
    var left = inset;
    var top = inset;
    var right = Math.max(left + 1.0, width - inset);
    var bottom = Math.max(top + 1.0, height - inset);
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "widthValue": Math.max(1.0, right - left),
        "heightValue": Math.max(1.0, bottom - top),
        "centerX": (left + right) * 0.5,
        "centerY": (top + bottom) * 0.5
    };
}

function _rectAnchorPoint(width, height, side) {
    var normalizedSide = String(side || "").trim().toLowerCase();
    var bounds = _flowchartBounds(width, height);
    if (normalizedSide === "top")
        return {"x": bounds.centerX, "y": bounds.top};
    if (normalizedSide === "right")
        return {"x": bounds.right, "y": bounds.centerY};
    if (normalizedSide === "bottom")
        return {"x": bounds.centerX, "y": bounds.bottom};
    return {"x": bounds.left, "y": bounds.centerY};
}

function _cubicBezierCoordinate(p0, p1, p2, p3, t) {
    var omt = 1.0 - t;
    return omt * omt * omt * p0
        + 3.0 * omt * omt * t * p1
        + 3.0 * omt * t * t * p2
        + t * t * t * p3;
}

function _solveMonotonicBezierT(target, p0, p1, p2, p3) {
    var increasing = p3 >= p0;
    var low = 0.0;
    var high = 1.0;
    for (var i = 0; i < 32; i++) {
        var mid = (low + high) * 0.5;
        var value = _cubicBezierCoordinate(p0, p1, p2, p3, mid);
        if ((value < target) === increasing)
            low = mid;
        else
            high = mid;
    }
    return (low + high) * 0.5;
}

function _documentBottomAnchor(bounds) {
    var waveDepth = Math.min(bounds.heightValue * 0.11, 11.5);
    var waveBase = bounds.bottom - waveDepth * 0.58;
    var waveCrest = bounds.bottom - waveDepth * 1.08;
    var waveTrough = bounds.bottom - waveDepth * 0.12;
    var middleX = bounds.left + bounds.widthValue * 0.52;
    var targetX = bounds.centerX;
    var p0x;
    var p1x;
    var p2x;
    var p3x;
    var p0y;
    var p1y;
    var p2y;
    var p3y;

    if (targetX >= middleX) {
        p0x = bounds.right;
        p1x = bounds.right - bounds.widthValue * 0.17;
        p2x = bounds.left + bounds.widthValue * 0.7;
        p3x = middleX;
        p0y = waveBase;
        p1y = waveTrough;
        p2y = waveTrough;
        p3y = waveBase - waveDepth * 0.34;
    } else {
        p0x = middleX;
        p1x = bounds.left + bounds.widthValue * 0.33;
        p2x = bounds.left + bounds.widthValue * 0.14;
        p3x = bounds.left;
        p0y = waveBase - waveDepth * 0.34;
        p1y = waveCrest;
        p2y = waveCrest;
        p3y = waveBase;
    }

    var t = _solveMonotonicBezierT(targetX, p0x, p1x, p2x, p3x);
    return {
        "x": targetX,
        "y": _cubicBezierCoordinate(p0y, p1y, p2y, p3y, t)
    };
}

function flowchartAnchorPoint(variant, width, height, side) {
    var normalizedSide = String(side || "").trim().toLowerCase();
    var bounds = _flowchartBounds(width, height);
    if (normalizedSide !== "top" && normalizedSide !== "right"
        && normalizedSide !== "bottom" && normalizedSide !== "left") {
        return {"x": bounds.centerX, "y": bounds.centerY};
    }

    var normalizedVariant = _normalizedFlowchartVariant(variant);
    if (normalizedVariant === "start" || normalizedVariant === "end" || normalizedVariant === "process"
        || normalizedVariant === "predefined_process" || normalizedVariant === "decision"
        || normalizedVariant === "connector") {
        if (normalizedSide === "top")
            return {"x": bounds.centerX, "y": bounds.top};
        if (normalizedSide === "right")
            return {"x": bounds.right, "y": bounds.centerY};
        if (normalizedSide === "bottom")
            return {"x": bounds.centerX, "y": bounds.bottom};
        return {"x": bounds.left, "y": bounds.centerY};
    }

    if (normalizedVariant === "input_output") {
        var slant = Math.min(bounds.widthValue * 0.13, bounds.heightValue * 0.26);
        if (normalizedSide === "top")
            return {"x": bounds.centerX, "y": bounds.top};
        if (normalizedSide === "right")
            return {"x": bounds.right - slant * 0.5, "y": bounds.centerY};
        if (normalizedSide === "bottom")
            return {"x": bounds.centerX, "y": bounds.bottom};
        return {"x": bounds.left + slant * 0.5, "y": bounds.centerY};
    }

    if (normalizedVariant === "database") {
        if (normalizedSide === "top")
            return {"x": bounds.centerX, "y": bounds.top};
        if (normalizedSide === "right")
            return {"x": bounds.right, "y": bounds.centerY};
        if (normalizedSide === "bottom")
            return {"x": bounds.centerX, "y": bounds.bottom};
        return {"x": bounds.left, "y": bounds.centerY};
    }

    if (normalizedVariant === "document") {
        if (normalizedSide === "top")
            return {"x": bounds.centerX, "y": bounds.top};
        if (normalizedSide === "right")
            return {"x": bounds.right, "y": bounds.centerY};
        if (normalizedSide === "bottom")
            return _documentBottomAnchor(bounds);
        return {"x": bounds.left, "y": bounds.centerY};
    }

    if (normalizedSide === "top")
        return {"x": bounds.centerX, "y": bounds.top};
    if (normalizedSide === "right")
        return {"x": bounds.right, "y": bounds.centerY};
    if (normalizedSide === "bottom")
        return {"x": bounds.centerX, "y": bounds.bottom};
    return {"x": bounds.left, "y": bounds.centerY};
}

function flowchartAnchorNormal(side) {
    var normalizedSide = String(side || "").trim().toLowerCase();
    if (normalizedSide === "top")
        return {"x": 0.0, "y": -1.0};
    if (normalizedSide === "right")
        return {"x": 1.0, "y": 0.0};
    if (normalizedSide === "bottom")
        return {"x": 0.0, "y": 1.0};
    if (normalizedSide === "left")
        return {"x": -1.0, "y": 0.0};
    return {"x": 0.0, "y": 0.0};
}

function flowchartAnchorTangent(side) {
    var normalizedSide = String(side || "").trim().toLowerCase();
    if (normalizedSide === "top" || normalizedSide === "bottom")
        return {"x": 1.0, "y": 0.0};
    if (normalizedSide === "left" || normalizedSide === "right")
        return {"x": 0.0, "y": 1.0};
    return {"x": 0.0, "y": 0.0};
}

function portCardinalSide(port) {
    var side = String(port && (port.side !== undefined ? port.side : port.key) || "").trim().toLowerCase();
    if (side === "top" || side === "right" || side === "bottom" || side === "left")
        return side;
    return "";
}

function portLayoutDirection(port) {
    var rawDirection = String(port && port.direction || "").trim().toLowerCase();
    var side = portCardinalSide(port);
    if (rawDirection === "neutral" && side)
        return (side === "top" || side === "left") ? "in" : "out";
    return rawDirection;
}

function nodeUsesCardinalNeutralFlowHandles(node) {
    var ports = node && node.ports ? node.ports : [];
    for (var i = 0; i < ports.length; i++) {
        var port = ports[i];
        if (!port || port.exposed === false || port.handle_visible === false)
            continue;
        if (String(port.direction || "").trim().toLowerCase() !== "neutral")
            continue;
        if (String(port.kind || "").trim().toLowerCase() !== "flow")
            continue;
        if (String(port.data_type || "").trim().toLowerCase() !== "flow")
            continue;
        if (portCardinalSide(port))
            return true;
    }
    return false;
}

function nodeHasBottomNeutralFlowHandle(node) {
    var ports = node && node.ports ? node.ports : [];
    for (var i = 0; i < ports.length; i++) {
        var port = ports[i];
        if (!port || port.exposed === false || port.handle_visible === false)
            continue;
        if (String(port.direction || "").trim().toLowerCase() !== "neutral"
                || String(port.kind || "").trim().toLowerCase() !== "flow"
                || String(port.data_type || "").trim().toLowerCase() !== "flow")
            continue;
        if (portCardinalSide(port) === "bottom")
            return true;
    }
    return false;
}

function visiblePortsForDirection(node, direction) {
    var ports = node && node.ports ? node.ports : [];
    var normalizedDirection = String(direction || "").trim().toLowerCase();
    var output = [];
    for (var i = 0; i < ports.length; i++) {
        var port = ports[i];
        if (!port || port.exposed === false || port.handle_visible === false)
            continue;
        if (portLayoutDirection(port) !== normalizedDirection)
            continue;
        output.push(port);
    }
    if (String(node && node.surface_family || "standard") !== "flowchart")
        return output;

    var sideOrder = normalizedDirection === "in"
        ? {"top": 0, "left": 1}
        : {"right": 0, "bottom": 1};
    output.sort(function(a, b) {
        var aSide = portCardinalSide(a);
        var bSide = portCardinalSide(b);
        var aOrder = sideOrder[aSide];
        var bOrder = sideOrder[bSide];
        if (aOrder === undefined)
            aOrder = 99;
        if (bOrder === undefined)
            bOrder = 99;
        if (aOrder !== bOrder)
            return aOrder - bOrder;
        return String(a && a.key || "").localeCompare(String(b && b.key || ""));
    });
    return output;
}

function _flowchartHorizontalBounds(variant, width, height, localY) {
    if (!(width > 0.0) || !(height > 0.0))
        return {"left": 0.0, "right": Math.max(0.0, width)};
    var yValue = Math.max(0.0, Math.min(height, localY));
    if (variant === "start" || variant === "end") {
        var radius = Math.min(width * 0.5, height * 0.5);
        var cy = height * 0.5;
        var dy = Math.max(-radius, Math.min(radius, yValue - cy));
        var dx = Math.sqrt(Math.max(0.0, radius * radius - dy * dy));
        var left = radius - dx;
        return {"left": left, "right": width - left};
    }
    if (variant === "decision") {
        var leftDecision = Math.abs((height * 0.5) - yValue) * width / height;
        return {"left": leftDecision, "right": width - leftDecision};
    }
    if (variant === "connector") {
        var rx = width * 0.5;
        var ry = height * 0.5;
        var cyConnector = height * 0.5;
        var dyConnector = Math.max(-ry, Math.min(ry, yValue - cyConnector));
        if (!(ry > 0.0))
            return {"left": 0.0, "right": width};
        var factor = Math.sqrt(Math.max(0.0, 1.0 - (dyConnector * dyConnector) / (ry * ry)));
        var dxConnector = rx * factor;
        return {"left": rx - dxConnector, "right": rx + dxConnector};
    }
    if (variant === "input_output") {
        var slant = Math.min(width * 0.13, height * 0.26);
        var leftIo = Math.max(0.0, slant * (1.0 - (yValue / height)));
        return {"left": leftIo, "right": width - leftIo};
    }
    return {"left": 0.0, "right": width};
}

function localPortPointForPort(node, port, inputRow, outputRow, widthOverride, heightOverride, graphLabelPixelSize) {
    if (!node || !port)
        return {"x": 0.0, "y": 0.0};
    var direction = portLayoutDirection(port);
    if (node.collapsed) {
        var collapsedMetrics = surfaceMetrics(node, widthOverride, heightOverride, graphLabelPixelSize);
        var collapsedWidth = _resolvedDimension(
            widthOverride !== undefined ? widthOverride : node.width,
            collapsedMetrics.default_width
        );
        return {
            "x": direction === "in" ? 0.0 : collapsedWidth,
            "y": collapsedMetrics.collapsed_height * 0.5
        };
    }

    var presentationAnchor = port.presentation_anchor;
    var presentationX = presentationAnchor ? Number(presentationAnchor.x) : NaN;
    var presentationY = presentationAnchor ? Number(presentationAnchor.y) : NaN;
    if (isFinite(presentationX) && isFinite(presentationY))
        return {
            "x": presentationX,
            "y": presentationY + settingsBandYOffset(node, heightOverride)
        };

    var metrics = surfaceMetrics(node, widthOverride, heightOverride, graphLabelPixelSize);
    var widthValue = _resolvedDimension(widthOverride !== undefined ? widthOverride : node.width, metrics.default_width);
    var heightValue = _surfaceContentHeight(node, heightOverride, metrics.default_height);

    var side = portCardinalSide(port);
    if (side) {
        if (String(node.surface_family || "standard") === "flowchart")
            return flowchartAnchorPoint(node.surface_variant, widthValue, heightValue, side);
        return _rectAnchorPoint(widthValue, heightValue, side);
    }

    var explicitLayoutRow = Number(port.layout_row);
    var rowIndex = isFinite(explicitLayoutRow)
        ? explicitLayoutRow
        : (direction === "in" ? Number(inputRow) : Number(outputRow));
    if (!isFinite(rowIndex))
        rowIndex = 0;
    var localY = metrics.port_top + metrics.port_center_offset + metrics.port_height * rowIndex;
    if (String(node.surface_family || "standard") === "flowchart") {
        var bounds = _flowchartHorizontalBounds(
            _normalizedFlowchartVariant(node.surface_variant),
            widthValue,
            heightValue,
            localY
        );
        return {
            "x": direction === "in" ? bounds.left : bounds.right,
            "y": localY
        };
    }
    return {
        "x": direction === "in" ? 0.0 : widthValue,
        "y": localY
    };
}

function localPortPoint(node, direction, rowIndex, widthOverride, heightOverride, graphLabelPixelSize) {
    if (!node)
        return {"x": 0.0, "y": 0.0};
    var visiblePorts = visiblePortsForDirection(node, direction);
    var resolvedRow = Number(rowIndex);
    if (!isFinite(resolvedRow))
        resolvedRow = 0;
    if (resolvedRow >= 0 && resolvedRow < visiblePorts.length) {
        var rowPort = visiblePorts[resolvedRow];
        if (portCardinalSide(rowPort))
            return localPortPointForPort(
                node,
                rowPort,
                resolvedRow,
                resolvedRow,
                widthOverride,
                heightOverride,
                graphLabelPixelSize
            );
    }
    var metrics = surfaceMetrics(node, widthOverride, heightOverride, graphLabelPixelSize);
    var widthValue = _resolvedDimension(widthOverride !== undefined ? widthOverride : node.width, metrics.default_width);
    var heightValue = _surfaceContentHeight(node, heightOverride, metrics.default_height);
    if (node.collapsed) {
        return {
            "x": String(direction || "") === "in" ? 0.0 : widthValue,
            "y": metrics.collapsed_height * 0.5
        };
    }
    var localY = metrics.port_top + metrics.port_center_offset + metrics.port_height * Number(rowIndex);
    if (String(node.surface_family || "standard") === "flowchart") {
        var bounds = _flowchartHorizontalBounds(
            _normalizedFlowchartVariant(node.surface_variant),
            widthValue,
            heightValue,
            localY
        );
        return {
            "x": String(direction || "") === "in" ? bounds.left : bounds.right,
            "y": localY
        };
    }
    return {
        "x": String(direction || "") === "in" ? 0.0 : widthValue,
        "y": localY
    };
}

function portScenePoint(node, direction, rowIndex, widthOverride, heightOverride, graphLabelPixelSize) {
    if (!node)
        return {"x": 0.0, "y": 0.0};
    var localPoint = localPortPoint(
        node,
        direction,
        rowIndex,
        widthOverride,
        heightOverride,
        graphLabelPixelSize
    );
    return {
        "x": Number(node.x || 0.0) + localPoint.x,
        "y": Number(node.y || 0.0) + localPoint.y
    };
}

function portScenePointForPort(node, port, inputRow, outputRow, widthOverride, heightOverride, graphLabelPixelSize) {
    if (!node || !port)
        return {"x": 0.0, "y": 0.0};
    var localPoint = localPortPointForPort(
        node,
        port,
        inputRow,
        outputRow,
        widthOverride,
        heightOverride,
        graphLabelPixelSize
    );
    return {
        "x": Number(node.x || 0.0) + localPoint.x,
        "y": Number(node.y || 0.0) + localPoint.y
    };
}
