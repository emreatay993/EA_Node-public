.pragma library

// Throwaway sample data + helpers for the linking mockups. Pure/stateless so it
// is safe as a shared library. Nothing here touches the real app.

// Workspaces in the (faux) project.
var workspaces = [
    { kind: "workspace", title: "Research",  breadcrumb: "Project" },
    { kind: "workspace", title: "Design",    breadcrumb: "Project" },
    { kind: "workspace", title: "Tasks",      breadcrumb: "Project" }
];

// Nodes that live across the (faux) project — the searchable internal targets.
var nodes = [
    { kind: "node", title: "Research Summary", breadcrumb: "Research" },
    { kind: "node", title: "Budget Model",      breadcrumb: "Tasks" },
    { kind: "node", title: "Project Brief",     breadcrumb: "Research" },
    { kind: "node", title: "Risk Register",     breadcrumb: "Tasks" },
    { kind: "node", title: "Stakeholder Map",   breadcrumb: "Design" }
];

// Recently used external targets.
var recentFiles = [
    { kind: "file",   title: "Q3 Report.pdf",        breadcrumb: "C:\\Users\\me\\Docs" },
    { kind: "file",   title: "spec_v4.docx",          breadcrumb: "C:\\Users\\me\\Docs" },
    { kind: "folder", title: "Reference Material",    breadcrumb: "C:\\Users\\me\\Docs" },
    { kind: "web",    title: "anthropic.com",          breadcrumb: "https://anthropic.com" },
    { kind: "web",    title: "Qt for Python docs",     breadcrumb: "doc.qt.io/qtforpython" }
];

// The full mixed search index used by the omnibox / node picker.
function searchIndex() {
    var idx = [];
    var i;
    for (i = 0; i < nodes.length; i++) idx.push(nodes[i]);
    for (i = 0; i < workspaces.length; i++) idx.push(workspaces[i]);
    for (i = 0; i < recentFiles.length; i++) idx.push(recentFiles[i]);
    return idx;
}

// Sample links already attached to the "Project Brief" node (for Concept D/E).
function seedLinks() {
    return [
        { kind: "web",       title: "anthropic.com",       breadcrumb: "https://anthropic.com" },
        { kind: "node",      title: "Budget Model",         breadcrumb: "Tasks" },
        { kind: "file",      title: "Q3 Report.pdf",        breadcrumb: "C:\\Users\\me\\Docs" },
        { kind: "workspace", title: "Design",                breadcrumb: "Project" }
    ];
}

// Classify what the user typed in the omnibox into an intent.
function detectIntent(text) {
    var s = (text || "").trim();
    if (s.length === 0) return { kind: "empty", label: "" };
    if (/^(https?:\/\/|www\.)/i.test(s))
        return { kind: "web", label: s.replace(/^https?:\/\//i, ""), target: s };
    // Windows drive (C:\...), UNC (\\...), or POSIX absolute (/...)
    if (/^[a-zA-Z]:[\\/]/.test(s) || s.indexOf("\\\\") === 0 || s.charAt(0) === "/") {
        var isDir = s.charAt(s.length - 1) === "\\" || s.charAt(s.length - 1) === "/";
        return { kind: isDir ? "folder" : "file", label: s, target: s };
    }
    return { kind: "search", label: s };
}

// Live-filter the index for the search intent.
function filterIndex(query) {
    var q = (query || "").trim().toLowerCase();
    var all = searchIndex();
    if (q.length === 0) return all;
    var out = [];
    for (var i = 0; i < all.length; i++) {
        if (all[i].title.toLowerCase().indexOf(q) !== -1)
            out.push(all[i]);
    }
    return out;
}
