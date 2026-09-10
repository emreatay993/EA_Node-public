.pragma library

function numberValue(value, fallback) {
    var numeric = Number(value);
    return isFinite(numeric) ? numeric : (fallback === undefined ? 0 : fallback);
}

function positiveInt(value, fallback) {
    var numeric = Math.floor(numberValue(value, fallback));
    if (numeric <= 0)
        return Math.max(1, Math.floor(numberValue(fallback, 1)));
    return numeric;
}

function nonNegativeInt(value, fallback) {
    var numeric = Math.floor(numberValue(value, fallback));
    return numeric >= 0 ? numeric : Math.max(0, Math.floor(numberValue(fallback, 0)));
}

function objectValue(value) {
    return value && typeof value === "object" ? value : ({});
}

function stringValue(value, fallback) {
    if (value === undefined || value === null)
        return fallback === undefined ? "" : String(fallback);
    return String(value);
}

function arrayValue(value) {
    return value && value.length !== undefined ? value : [];
}

function previewPayload(payload) {
    var normalized = objectValue(payload);
    return objectValue(normalized.preview ? normalized.preview : normalized);
}

function tableViewState(payload) {
    var normalized = objectValue(payload);
    var directState = objectValue(normalized.tabular_table_view_state);
    if (directState.column_widths !== undefined)
        return directState;
    return objectValue(objectValue(normalized.properties).tabular_table_view_state);
}

function previewKind(preview) {
    return stringValue(objectValue(preview).preview_kind, "");
}

function windowPayload(preview) {
    var normalized = objectValue(preview);
    if (previewKind(normalized) === "array")
        return objectValue(normalized.slice_2d);
    return objectValue(normalized.window);
}

function tableColumns(preview) {
    var window = windowPayload(preview);
    return arrayValue(window.columns);
}

function arrayColumns(preview) {
    var slice = windowPayload(preview);
    var values = arrayValue(slice.values);
    var width = 0;
    if (values.length > 0 && values[0] && values[0].length !== undefined)
        width = values[0].length;
    var columns = [];
    var offset = nonNegativeInt(slice.column_offset, 0);
    for (var index = 0; index < width; index++)
        columns.push("C" + (offset + index));
    return columns;
}

function columns(preview) {
    return previewKind(preview) === "array" ? arrayColumns(preview) : tableColumns(preview);
}

function rows(preview) {
    var window = windowPayload(preview);
    if (previewKind(preview) === "array")
        return arrayValue(window.values);
    return arrayValue(window.rows);
}

function totalRows(preview) {
    var normalized = objectValue(preview);
    var window = windowPayload(normalized);
    if (previewKind(normalized) === "array") {
        var shape = arrayValue(window.shape && window.shape.length !== undefined ? window.shape : objectValue(normalized.array).shape);
        return shape.length > 0 ? nonNegativeInt(shape[0], rows(normalized).length) : rows(normalized).length;
    }
    return nonNegativeInt(window.total_rows, rows(normalized).length);
}

function totalColumns(preview) {
    var normalized = objectValue(preview);
    var window = windowPayload(normalized);
    if (previewKind(normalized) === "array") {
        var shape = arrayValue(window.shape && window.shape.length !== undefined ? window.shape : objectValue(normalized.array).shape);
        return shape.length > 1 ? nonNegativeInt(shape[1], columns(normalized).length) : columns(normalized).length;
    }
    return nonNegativeInt(window.total_columns, columns(normalized).length);
}

function rowOffset(preview) {
    return nonNegativeInt(windowPayload(preview).row_offset, 0);
}

function columnOffset(preview) {
    return nonNegativeInt(windowPayload(preview).column_offset, 0);
}

function rowLimit(preview, fallback) {
    var request = objectValue(windowPayload(preview).request);
    return positiveInt(request.row_limit, fallback === undefined ? 50 : fallback);
}

function columnLimit(preview, fallback) {
    var request = objectValue(windowPayload(preview).request);
    return positiveInt(request.column_limit, fallback === undefined ? 50 : fallback);
}

function cellText(preview, row, column) {
    var normalizedRows = rows(preview);
    var rowValue = normalizedRows[row];
    if (rowValue === undefined || rowValue === null)
        return "";
    if (previewKind(preview) === "array") {
        if (!rowValue || rowValue.length === undefined)
            return "";
        return stringValue(rowValue[column], "");
    }
    var columnName = columns(preview)[column];
    if (columnName === undefined || columnName === null)
        return "";
    return stringValue(objectValue(rowValue)[String(columnName)], "");
}

function selectorLabel(preview) {
    var selector = objectValue(objectValue(preview).selector);
    var selected = stringValue(selector.selected_object, "").trim();
    if (selected.length > 0)
        return "Selected " + selected;
    if (selector.requires_selection)
        return "Selection required";
    return "Single object";
}

function selectorObjects(preview) {
    return arrayValue(objectValue(objectValue(preview).selector).objects);
}

function selectorObjectIds(preview) {
    var objects = selectorObjects(preview);
    var values = [];
    var seen = {};
    for (var index = 0; index < objects.length; index++) {
        var item = objectValue(objects[index]);
        var value = stringValue(item.object_id || item.display_name, "").trim();
        var key = value.toLowerCase();
        if (!value.length || seen[key])
            continue;
        seen[key] = true;
        values.push(value);
    }
    return values;
}

function cacheLabel(payload) {
    var properties = objectValue(objectValue(payload).properties);
    var cachePolicy = stringValue(properties.cache_policy, "").trim();
    if (!cachePolicy.length)
        cachePolicy = "app_managed_parquet";
    return "Cache " + cachePolicy.replace(/_/g, " ");
}

function sourceLabel(preview) {
    var source = objectValue(objectValue(preview).source);
    var resolved = stringValue(source.resolved_path, "").trim();
    if (resolved.length > 0)
        return resolved;
    return stringValue(source.path, "").trim();
}

function statusText(payload) {
    var preview = previewPayload(payload);
    var state = stringValue(preview.state, "");
    var kind = previewKind(preview);
    var parts = [];
    if (state.length > 0)
        parts.push(state);
    if (kind.length > 0)
        parts.push(kind);
    parts.push(selectorLabel(preview));
    parts.push(cacheLabel(payload));
    return parts.join("  |  ");
}

function metadataPairs(preview, limit) {
    var metadata = objectValue(objectValue(preview).metadata);
    var ref = objectValue(objectValue(preview).ref);
    var source = objectValue(objectValue(preview).source);
    var pairs = [];
    function pushPair(label, value) {
        var text = stringValue(value, "").trim();
        if (text.length > 0)
            pairs.push({"label": label, "value": text});
    }
    pushPair("Source", sourceLabel(preview));
    pushPair("Format", source.format_id || metadata.format_id || ref.format_id);
    pushPair("Rows", totalRows(preview));
    pushPair("Columns", totalColumns(preview));
    pushPair("Resolver", ref.resolver_id);
    pushPair("Object", ref.object_id || objectValue(preview).array && objectValue(preview).array.object_id);
    pushPair("Dtype", objectValue(preview).array ? objectValue(preview).array.dtype : "");
    var shape = arrayValue(objectValue(preview).array ? objectValue(preview).array.shape : []);
    if (shape.length > 0)
        pushPair("Shape", shape.join(" x "));
    var capped = [];
    var maxPairs = positiveInt(limit, 8);
    for (var index = 0; index < pairs.length && index < maxPairs; index++)
        capped.push(pairs[index]);
    return capped;
}

function visibleSummary(preview) {
    var rowsVisible = rows(preview).length;
    var columnsVisible = columns(preview).length;
    var firstRow = rowOffset(preview);
    var firstColumn = columnOffset(preview);
    return rowsVisible + " rows from " + firstRow + ", "
        + columnsVisible + " columns from " + firstColumn;
}

function formatCount(value) {
    var numeric = Math.max(0, nonNegativeInt(value, 0));
    if (numeric >= 1000000) {
        var millions = numeric / 1000000;
        return (numeric >= 10000000 ? millions.toFixed(0) : millions.toFixed(1)).replace(/\.0$/, "") + "M";
    }
    if (numeric >= 1000) {
        var thousands = numeric / 1000;
        return (numeric >= 10000 ? thousands.toFixed(0) : thousands.toFixed(1)).replace(/\.0$/, "") + "K";
    }
    return String(numeric);
}

function fileNameFromPath(path) {
    var trimmed = stringValue(path, "").trim();
    if (trimmed.length === 0)
        return "";
    var slashSplit = trimmed.split(/[\\/]/);
    return slashSplit[slashSplit.length - 1];
}

function nodeStatus(payload, sourcePath) {
    var preview = previewPayload(payload);
    var rawState = stringValue(preview.state, "").trim();
    var hasPath = stringValue(sourcePath, "").trim().length > 0;
    switch (rawState) {
        case "ready":
            return {"label": "Ready", "tone": "ok"};
        case "loading":
            return {"label": "Loading", "tone": "info"};
        case "error":
            return {"label": "Error", "tone": "error"};
        case "warning":
            return {"label": "Warning", "tone": "warn"};
        case "":
        case "placeholder":
            return hasPath
                ? {"label": "Pending preview", "tone": "warn"}
                : {"label": "", "tone": "muted"};
        default:
            return {"label": rawState.replace(/_/g, " "), "tone": "muted"};
    }
}

function nodeDetail(payload, sourcePath) {
    var preview = previewPayload(payload);
    var fileName = fileNameFromPath(sourcePath);
    if (stringValue(preview.state, "") === "ready") {
        var rowText = formatCount(totalRows(preview));
        var columnText = formatCount(totalColumns(preview));
        var summary = rowText + " rows  ×  " + columnText + " cols";
        return fileName.length > 0 ? fileName + "  ·  " + summary : summary;
    }
    if (fileName.length > 0)
        return fileName;
    return "";
}

function nodeEmptyHeadline(payload, sourcePath) {
    var preview = previewPayload(payload);
    var rawState = stringValue(preview.state, "");
    var hasPath = stringValue(sourcePath, "").trim().length > 0;
    if (rawState === "error")
        return "Preview failed";
    if (rawState === "warning")
        return "Preview unavailable";
    if (rawState === "loading")
        return "Loading preview…";
    if (!hasPath)
        return "No file connected";
    return "Preview not yet resolved";
}

function nodeEmptyDescription(payload, sourcePath) {
    var preview = previewPayload(payload);
    var message = stringValue(preview.message, "").trim();
    if (message.length > 0
        && message.indexOf("Open fullscreen to resolve") < 0
        && message.indexOf("Choose a tabular data file") < 0)
        return message;
    var hasPath = stringValue(sourcePath, "").trim().length > 0;
    return hasPath
        ? "Open fullscreen to load a bounded preview window from this dataset."
        : "Drive the Path port from a file source, or open fullscreen to pick one.";
}
