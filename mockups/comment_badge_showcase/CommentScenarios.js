.pragma library

// Shared node-state fixture: every concept renders the SAME five nodes so the
// badge designs can be compared state-for-state. Comment shape (author/time/
// body/resolved/pinned) matches the in-package node_comments mockup.
//
// States, left to right on the stage:
//   empty    - no comments; demonstrates the hover ghost "add" affordance
//   single   - one open comment, already read (resting look)
//   unread   - 3 comments / 2 open, unread accent + pulse; forceHover so the
//              resize grip is visible statically (grip-coexistence demo)
//   resolved - every comment resolved (muted / success tone)
//   long     - one long open comment (elision test); locked, so the LOCKED
//              header pill shows and the resize grip stays hidden
var nodeStates = [
    {
        key: "empty",
        title: "Tabular Data Input",
        type: "data.table",
        body: "Reads the mission-point CSV and exposes a preview table.",
        unread: false,
        locked: false,
        forceHover: false,
        caption: "no comments · hover node for add affordance",
        comments: []
    },
    {
        key: "single",
        title: "Python Script",
        type: "core.python",
        body: "Normalises channel names before the resample step.",
        unread: false,
        locked: false,
        forceHover: false,
        caption: "1 open comment · read",
        comments: [
            {
                author: "Emre",
                time: "10:11",
                body: "Call out the pandas import path before the run button is used.",
                resolved: false,
                pinned: false
            }
        ]
    },
    {
        key: "unread",
        title: "Scatter Plot",
        type: "viz.scatter",
        body: "Cross-plots blade temperature against shaft speed.",
        unread: true,
        locked: false,
        forceHover: true,
        caption: "3 comments · 2 open · unread (node hovered: grip visible)",
        comments: [
            {
                author: "Nora",
                time: "10:18",
                body: "The warning row should stay visible after reconnecting the input.",
                resolved: false,
                pinned: true
            },
            {
                author: "Maya",
                time: "10:24",
                body: "Axis units disagree with the solver output — needs a scale factor.",
                resolved: false,
                pinned: false
            },
            {
                author: "Emre",
                time: "09:52",
                body: "Legend overlaps the last series.",
                resolved: true,
                pinned: false
            }
        ]
    },
    {
        key: "resolved",
        title: "Export Report",
        type: "io.report",
        body: "Writes the run summary deck to the shared drive.",
        unread: false,
        locked: false,
        forceHover: false,
        caption: "2 comments · all resolved",
        comments: [
            {
                author: "Maya",
                time: "08:40",
                body: "Use the 16:9 template for the appendix pages.",
                resolved: true,
                pinned: false
            },
            {
                author: "Emre",
                time: "08:55",
                body: "Done — template swapped and margins fixed.",
                resolved: true,
                pinned: false
            }
        ]
    },
    {
        key: "long",
        title: "Solver Sweep",
        type: "solve.sweep",
        body: "Runs the speed sweep across the mission envelope.",
        unread: false,
        locked: true,
        forceHover: false,
        caption: "1 open comment · long body · node LOCKED (no grip)",
        comments: [
            {
                author: "Emre",
                time: "11:03",
                body: "Sweep range is hard-coded to 0.8–1.2× nominal speed; parameterise it "
                    + "from the mission profile node and document the damping assumption for "
                    + "the LP turbine stage before this goes to certification.",
                resolved: false,
                pinned: false
            }
        ]
    }
];

function commentCount(comments) {
    return comments ? comments.length : 0;
}

function openCount(comments) {
    var n = 0;
    for (var i = 0; i < (comments ? comments.length : 0); i++) {
        if (!comments[i].resolved)
            n += 1;
    }
    return n;
}

function firstOpenBody(comments) {
    for (var i = 0; i < (comments ? comments.length : 0); i++) {
        if (!comments[i].resolved)
            return comments[i].body;
    }
    return comments && comments.length ? comments[0].body : "";
}

function firstOpenAuthor(comments) {
    for (var i = 0; i < (comments ? comments.length : 0); i++) {
        if (!comments[i].resolved)
            return comments[i].author;
    }
    return comments && comments.length ? comments[0].author : "";
}
