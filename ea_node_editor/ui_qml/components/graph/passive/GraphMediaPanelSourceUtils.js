.pragma library

function isWindowsDrivePath(value) {
    return /^[A-Za-z]:[\\/]/.test(value);
}

function isAbsolutePosixPath(value) {
    return value.length > 0 && value.charAt(0) === "/";
}

function isUncPath(value) {
    return /^[/\\]{2}[^/\\]/.test(value);
}

function isProjectArtifactRef(value) {
    return /^(?:saved|temp):\/\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value);
}

function normalizedFileUrlFromRemainder(remainder) {
    var normalized = String(remainder || "").replace(/\\/g, "/");
    if (!normalized.length)
        return "";
    if (normalized.indexOf("///") === 0)
        return "file://" + encodeURI(normalized.substring(2));
    if (normalized.indexOf("//") === 0)
        return "file://" + encodeURI(normalized.substring(2));
    if (isWindowsDrivePath(normalized))
        return "file:///" + encodeURI(normalized);
    if (isUncPath(normalized))
        return "file:" + encodeURI(normalized);
    if (isAbsolutePosixPath(normalized))
        return "file://" + encodeURI(normalized);
    return "";
}

function resolvedLocalSourceUrl(rawValue) {
    var trimmed = String(rawValue || "").trim();
    if (!trimmed.length)
        return "";
    if (isProjectArtifactRef(trimmed))
        return trimmed;
    var normalized = trimmed.replace(/\\/g, "/");
    var lower = normalized.toLowerCase();
    if (lower.indexOf("file:") === 0)
        return normalizedFileUrlFromRemainder(normalized.substring(5));
    if (isWindowsDrivePath(trimmed))
        return "file:///" + encodeURI(trimmed.replace(/\\/g, "/"));
    if (isUncPath(trimmed))
        return "file:" + encodeURI(trimmed.replace(/\\/g, "/"));
    if (isAbsolutePosixPath(trimmed))
        return "file://" + encodeURI(trimmed);
    return "";
}

function resolvedLocalFileSourceUrl(rawValue) {
    var trimmed = String(rawValue || "").trim();
    if (!trimmed.length)
        return "";
    var normalized = trimmed.replace(/\\/g, "/");
    var lower = normalized.toLowerCase();
    if (lower.indexOf("file:") === 0)
        return normalizedFileUrlFromRemainder(normalized.substring(5));
    if (isWindowsDrivePath(trimmed))
        return "file:///" + encodeURI(trimmed.replace(/\\/g, "/"));
    if (isUncPath(trimmed))
        return "file:" + encodeURI(trimmed.replace(/\\/g, "/"));
    if (isAbsolutePosixPath(trimmed))
        return "file://" + encodeURI(trimmed);
    return "";
}

function previewSourceUrl(localSourceUrl) {
    var normalized = String(localSourceUrl || "").trim();
    if (!normalized.length)
        return "";
    return "image://local-media-preview/preview?source=" + encodeURIComponent(normalized);
}
