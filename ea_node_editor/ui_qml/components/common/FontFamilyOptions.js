.pragma library

var DEFAULT_FONT_FAMILY_LABEL = "Default";

function _trimmed(value) {
    return String(value === undefined || value === null ? "" : value).trim();
}

function fontFamilies() {
    var source = [];
    try {
        source = Qt.fontFamilies();
    } catch (error) {
        source = [];
    }
    if (!source || source.length === undefined || source.length === 0) {
        source = [
            Qt.application.font.family,
            "Arial",
            "Segoe UI",
            "Calibri",
            "Times New Roman",
            "Courier New",
            "Georgia",
            "Verdana"
        ];
    }
    var seen = {};
    var families = [];
    for (var index = 0; index < source.length; index++) {
        var family = _trimmed(source[index]);
        if (!family.length)
            continue;
        var key = family.toLowerCase();
        if (seen[key])
            continue;
        seen[key] = true;
        families.push(family);
    }
    families.sort(function(left, right) {
        return left.localeCompare(right);
    });
    return families;
}

function withDefault() {
    return [DEFAULT_FONT_FAMILY_LABEL].concat(fontFamilies());
}

function displayName(value) {
    var family = _trimmed(value);
    return family.length > 0 ? family : DEFAULT_FONT_FAMILY_LABEL;
}

function valueFromDisplay(value) {
    var text = _trimmed(value);
    return text.toLowerCase() === DEFAULT_FONT_FAMILY_LABEL.toLowerCase() ? "" : text;
}

function canonicalFamily(value) {
    var requested = valueFromDisplay(value);
    if (!requested.length)
        return "";
    var requestedKey = requested.toLowerCase();
    var families = fontFamilies();
    for (var index = 0; index < families.length; index++) {
        if (families[index].toLowerCase() === requestedKey)
            return families[index];
    }
    return "";
}

function encodeFamily(value) {
    return encodeURIComponent(_trimmed(value));
}

function decodeFamily(value) {
    try {
        return decodeURIComponent(String(value || ""));
    } catch (error) {
        return "";
    }
}
