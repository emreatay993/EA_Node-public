.pragma library

function relativeLabel(isoString) {
    var text = String(isoString || "").trim();
    if (!text.length)
        return "";
    var stamp = new Date(text);
    if (isNaN(stamp.getTime()))
        return "";
    var deltaSec = Math.floor((Date.now() - stamp.getTime()) / 1000);
    if (deltaSec < 45)
        return "just now";
    if (deltaSec < 3600)
        return Math.max(1, Math.round(deltaSec / 60)) + "m ago";
    if (deltaSec < 86400)
        return Math.floor(deltaSec / 3600) + "h ago";
    if (deltaSec < 604800)
        return Math.floor(deltaSec / 86400) + "d ago";
    return Qt.formatDate(stamp, "MMM d, yyyy");
}

function initials(author) {
    var words = String(author || "").trim().split(/\s+/).filter(function(word) { return word.length > 0; });
    if (!words.length)
        return "?";
    var first = words[0].charAt(0);
    var last = words.length > 1 ? words[words.length - 1].charAt(0) : "";
    return (first + last).toUpperCase();
}
