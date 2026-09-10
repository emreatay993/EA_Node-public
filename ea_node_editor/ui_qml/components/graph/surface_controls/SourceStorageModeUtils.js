.pragma library

var EXTERNAL_LINK_MODE = "external_link";
var MANAGED_COPY_MODE = "managed_copy";

function isProjectArtifactRef(value) {
    return /^(?:saved|temp):\/\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(String(value || "").trim());
}

function sourceModeForPath(value) {
    return isProjectArtifactRef(value) ? MANAGED_COPY_MODE : EXTERNAL_LINK_MODE;
}

function normalizedSourceMode(value, fallback) {
    var normalized = String(value || "").trim().toLowerCase();
    if (normalized === MANAGED_COPY_MODE || normalized === EXTERNAL_LINK_MODE)
        return normalized;
    return String(fallback || EXTERNAL_LINK_MODE).trim().toLowerCase() || EXTERNAL_LINK_MODE;
}
