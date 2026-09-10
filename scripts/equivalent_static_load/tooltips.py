"""Rich HTML tooltips for the ESL GUI — every widget self-explanatory.

Qt tooltips render a rich-text subset (no LaTeX), so formulas use
``<sub>/<sup>/&middot;/&Sigma;`` markup. All texts live here, not in gui.py,
so wording stays consistent with the methodology note
(``MyLife/work/methodology-equivalent-static-loads.md``) and is testable.

Layout trick: Qt only word-wraps rich-text tooltips reliably inside a fixed
``<td width=...>`` cell, hence the table fence in :func:`tip`.
"""

from __future__ import annotations

_FORMULA_STYLE = (
    "font-family:Consolas,'Courier New',monospace; font-size:9pt; "
    "background-color:#f0f4f8; padding:6px;"
)


def tip(title: str, body: str, formula: str | None = None, footer: str | None = None) -> str:
    """Assemble a consistently formatted rich tooltip.

    Args:
        title: Bold first line — what the control is.
        body: Plain-language explanation (HTML allowed).
        formula: Optional formula line, rendered monospaced on a light box.
        footer: Optional muted practical note (defaults, consequences).
    """
    parts = [f"<p style='margin:0 0 6px 0'><b>{title}</b></p>", f"<p style='margin:0'>{body}</p>"]
    if formula:
        parts.append(
            f"<p style='margin:8px 0 0 0; {_FORMULA_STYLE}'>{formula}</p>"
        )
    if footer:
        parts.append(f"<p style='margin:8px 0 0 0; color:#5a6b7d'><i>{footer}</i></p>")
    inner = "".join(parts)
    return f"<html><body><table width='470'><tr><td>{inner}</td></tr></table></body></html>"


# --------------------------------------------------------------------- shared

F_RECONSTRUCT = (
    "&sigma;<sub>c</sub>(t*) = &Sigma;<sub>j</sub> q<sub>j</sub>(t*) &middot; "
    "&sigma;<sub>c,j</sub> &nbsp;&nbsp;(+ &sigma;<sub>c,steady</sub> if included), "
    "&nbsp;c &isin; {x, y, z, xy, yz, xz}"
)
F_EXACT_ESL = (
    "f<sub>ESL</sub> = K&middot;u(t*) = &Sigma;<sub>j</sub> &omega;<sub>j</sub><sup>2</sup> "
    "q<sub>j</sub>(t*) M&middot;&phi;<sub>j</sub>"
)
F_TIER2 = (
    "min<sub>P</sub> &Vert; W<sup>&frac12;</sup> ( &Sigma;<sub>k</sub> P<sub>k</sub> "
    "s<sub>k</sub> &minus; &sigma;<sub>dyn</sub>(t*) ) &Vert;<sup>2</sup> "
    "&nbsp;&nbsp;s.t.&nbsp; lb<sub>k</sub> &le; P<sub>k</sub> &le; ub<sub>k</sub>"
)
F_TIER1 = (
    "P = &lambda;&middot;L(t*), &nbsp;&nbsp;&lambda; = "
    "&lang;&sigma;<sub>pat</sub>, &sigma;<sub>dyn</sub>&rang;<sub>W</sub> / "
    "&lang;&sigma;<sub>pat</sub>, &sigma;<sub>pat</sub>&rang;<sub>W</sub>"
)
F_VON_MISES = (
    "&sigma;<sub>vm</sub> = &radic;( &frac12;[(&sigma;<sub>x</sub>&minus;&sigma;<sub>y</sub>)"
    "<sup>2</sup>+(&sigma;<sub>y</sub>&minus;&sigma;<sub>z</sub>)<sup>2</sup>"
    "+(&sigma;<sub>z</sub>&minus;&sigma;<sub>x</sub>)<sup>2</sup>] "
    "+ 3(&tau;<sub>xy</sub><sup>2</sup>+&tau;<sub>yz</sub><sup>2</sup>+&tau;<sub>xz</sub><sup>2</sup>) )"
)

# --------------------------------------------------------------------- header

LOAD_CONFIG = tip(
    "Load a saved configuration (JSON)",
    "Populates every page from a config file. Relative paths inside the file are "
    "resolved against the file's own folder and shown as absolute paths, so the "
    "config can be moved between machines together with its data. Referenced "
    "files are checked immediately: missing ones are listed in a warning and "
    "their fields turn <span style='color:#c0392b'><b>red</b></span>.",
    footer="The same JSON schema is used by the command-line interface — GUI and "
    "batch runs are interchangeable. Note: example_config.json is a schema "
    "template with placeholder paths; the runnable demo is Load Example.",
)

LOAD_EXAMPLE = tip(
    "Load the runnable mockup example",
    "Loads <code>examples/mockup_inputs/mockup_config.json</code> — a tiny, "
    "internally consistent demo dataset (10 nodes, 3 modes, 2 channels) shipped "
    "with the tool. Every input format is represented by a small readable file, "
    "and the data has built-in ground truth: derive reports "
    "&lambda; (effective DLF) &asymp; 1.6 at t* = 0.004 s.",
    footer="See examples/mockup_inputs/README.md for a column-by-column "
    "explanation of every file and the cross-reference rules.",
)
SAVE_CONFIG = tip(
    "Save the current configuration (JSON)",
    "Writes everything currently entered in the GUI to a JSON file. Before every "
    "run the GUI also auto-writes <code>gui_config.json</code> into the output "
    "folder, and its SHA-256 goes into <code>run_manifest.json</code> — every "
    "run is reproducible from a hashed config.",
)
STATUS = tip(
    "Status",
    "Shows what the tool is doing. Long operations run on a worker thread, so "
    "the window stays responsive; progress messages stream into the log below.",
)
PROGRESS = tip(
    "Progress",
    "Indeterminate while a worker task (check / suggest / derive / verify) runs. "
    "Detailed timestamped progress appears in the log panel.",
)
LOG = tip(
    "Run log",
    "Timestamped progress from the engine: file loads, node/mode counts, mapping "
    "quality, per-case solve results and warnings. The same lines a command-line "
    "run would print.",
)
BACK = tip("Previous step", "Go one step back in the workflow rail.")
NEXT = tip("Next step", "Go one step forward in the workflow rail.")

STEP_RAIL = tip(
    "Workflow steps",
    "The recommended order is top to bottom: define inputs and channels, check "
    "the mapping, pick the critical instants, derive, review results, then "
    "verify with a combined nonlinear solve. You can jump freely — nothing runs "
    "until you press an action button.",
)

STEP_TIPS = [
    tip("Step 1 — Inputs", "Select the MSUP transient results (modal stress CSV + modal "
        "coordinates), the virtual-rig unit-load fields, and optional inputs "
        "(steady bias, interface load history, MARS envelope files)."),
    tip("Step 2 — Channels", "Describe each rig actuator: where it pushes, in which "
        "direction, its capacity bounds, and which unit-load case belongs to it."),
    tip("Step 3 — Region &amp; Mapping", "Set MSUP&harr;rig node-mapping tolerances, the "
        "evaluation region and weighting for the least-squares match, acceptance "
        "thresholds, and the room-temperature scaling factor."),
    tip("Step 4 — Instants", "Pick the critical time points t* the rig cases will "
        "reproduce — suggested from evidence (per-node times of maximum), or "
        "entered explicitly."),
    tip("Step 5 — Derive", "Run the ESL solve for every checked instant and write the "
        "full output folder (load tables, fields, report, APDL snippets)."),
    tip("Step 6 — Results", "Review derived channel loads and equivalence metrics per "
        "case and tier; open the output folder."),
    tip("Step 7 — Verify", "Compare the combined nonlinear rig-model solve against the "
        "target field — the Open Item C1 evidence — and get the &lambda;"
        "<sub>corr</sub> iteration if needed."),
]

# -------------------------------------------------------------- page 1 inputs

TITLE = tip(
    "Run title",
    "Free text identifying this derivation. Appears in the report header "
    "(<code>esl_report.md</code>) and the run manifest.",
)
UNITS = tip(
    "Unit system (assumed, never validated)",
    "The tool performs <b>no unit conversion</b> — every input file must already "
    "be consistent with what you state here: modal stress CSV and unit-load "
    "fields in the same stress unit, load history and channel bounds in the same "
    "force unit, coordinates in the same length unit. The declared units are "
    "echoed into every output header for traceability.",
    footer="Typical Ansys export set: N, N·mm, MPa, mm.",
)
MODAL_STRESS = tip(
    "Modal stress CSV (required)",
    "Per-mode nodal stress tensors from the modal solution — the <b>same file "
    "MARS uses</b>. Expected columns: <code>NodeID, X, Y, Z, sx_Mode1, sy_Mode1, "
    "sz_Mode1, sxy_Mode1, syz_Mode1, sxz_Mode1, sx_Mode2, …</code> "
    "Column matching is case-insensitive contains-match; duplicate NodeIDs keep "
    "the last row (MARS parity). X, Y, Z are needed for mesh mapping. The mode "
    "count must equal the modal-coordinates file — a mismatch is a hard error "
    "because it means a different modal basis.",
    formula="target at instant: " + F_RECONSTRUCT,
)
MCF = tip(
    "Modal coordinates — .mcf or NASTRAN .pch (required)",
    "The generalized-coordinate histories q<sub>j</sub>(t) of the MSUP transient "
    "(e.g. Ansys MCFOPT output). <code>.mcf</code>: header "
    "<code>Number of Modes: N</code> + a <code>Time … Coordinates</code> table; "
    "wrapped continuation lines are handled (parser shared with "
    "mcf_dpf_section_resultants). <code>.pch</code>: SOL 112 punch with "
    "<code>$DISPLACEMENTS (SOLUTION SET)</code> sections.",
    footer="Requested instants are snapped to this file's time grid.",
)
MODAL_FORCES = tip(
    "Modal element-nodal forces CSV (optional — Route A)",
    "Per-mode element nodal forces/moments (<code>enfox_Mode1 … enmoz_ModeN</code> "
    "columns) on interface node sets. Used by the <code>resultants</code> "
    "command to reconstruct the <b>dynamic interface resultants</b> at t* — the "
    "amplified loads the casing feels at its boundaries:",
    formula="F = &Sigma; f<sub>i</sub>, &nbsp;&nbsp;M<sub>ref</sub> = &Sigma; m<sub>i</sub> "
    "+ &Sigma; (r<sub>i</sub> &minus; r<sub>ref</sub>) &times; f<sub>i</sub>",
    footer="For resultants over the whole time history straight from the modal "
    ".rst, use the sibling tool mcf_dpf_section_resultants.",
)
STEADY = tip(
    "Steady / bias stress field (optional)",
    "A static prestress field (pressure, thermal, bolt preload) with columns "
    "<code>NodeID, sx … sxz</code>. Only added to the target when the checkbox "
    "below is ticked.",
)
INCLUDE_BIAS = tip(
    "Steady-bias double-counting rule (methodology §7)",
    "The rig applies internal pressure <b>physically</b> as its own load. If the "
    "ESL target also contained the pressure prestress, the casing would be "
    "loaded twice for the same effect — a non-traceable over-test. Keep this "
    "<b>OFF</b> (default) so the target is the transient-only field; turn it on "
    "only if the rig will NOT apply the corresponding steady load.",
    formula=F_RECONSTRUCT,
)
UNIT_LAYOUT = tip(
    "Unit-load field source",
    "<b>wide</b> — one CSV holding all channels as column groups "
    "<code>sx_&lt;case_label&gt; … sxz_&lt;case_label&gt;</code> (same export "
    "style as the modal stress CSV, so existing extraction scripts work "
    "unchanged).<br><b>rst</b> — read nodal-averaged stress per result set "
    "directly from the rig-model result file via ansys-dpf-core (one static "
    "result set per channel; a numeric case_label selects that set id, "
    "otherwise sets are taken in channel order).",
)
UNIT_CSV = tip(
    "Unit-load fields CSV (wide layout)",
    "Stress fields of the virtual rig model, one linear static solve per "
    "channel, all on the <b>same node set</b>. Columns: <code>NodeID, X, Y, Z</code> "
    "+ per channel <code>sx_&lt;case_label&gt; … sxz_&lt;case_label&gt;</code>. "
    "Values are the <i>as-solved</i> stresses; the tool normalizes to a "
    "per-unit-force influence field:",
    formula="s<sub>k</sub> = &sigma;<sub>as-solved,k</sub> / unit_load<sub>k</sub> "
    "&nbsp;&nbsp;&rArr;&nbsp;&nbsp; &sigma;<sub>static</sub>(P) = "
    "&Sigma;<sub>k</sub> P<sub>k</sub> s<sub>k</sub>",
    footer="Run the unit solves at any convenient magnitude (e.g. 1 kN) — enter "
    "that magnitude as the channel's unit_load.",
)
UNIT_RST = tip(
    "Unit-load fields .rst (DPF layout)",
    "Rig-model result file containing one static result set per channel. "
    "Requires ansys-dpf-core in this environment. Stress is read nodal-averaged; "
    "node coordinates come from the mesh for mapping.",
)
HISTORY = tip(
    "Interface load history (optional — Tier-1 pattern)",
    "Canonical wide CSV: a <code>Time</code> column plus one named column per "
    "load channel. Provides the instantaneous load pattern L(t*) for the "
    "pattern-scaled route; each rig channel picks its column via "
    "<i>interface_channel</i> on the Channels page. If the history grid differs "
    "from the .mcf grid, L(t*) is linearly interpolated (flagged in the report).",
    formula=F_TIER1,
    footer="Convert the whole-engine team's heterogeneous format into this CSV "
    "once — that conversion is deliberately outside the tool for traceability.",
)
MARS_MAX = tip(
    "MARS envelope — max_von_mises.csv (optional)",
    "Per-node peak von Mises over the transient (<code>NodeID, X, Y, Z, "
    "value</code>), produced by a MARS batch solve. Together with the "
    "time-of-max file it drives evidence-based instant suggestion: the "
    "times-of-max of the top-VM hotspot population are clustered, one candidate "
    "instant per cluster.",
)
MARS_TIME = tip(
    "MARS envelope — time_of_max_von_mises.csv (optional)",
    "Per-node time at which each node reaches its peak von Mises. Consumed "
    "together with max_von_mises.csv for instant suggestion. If either file is "
    "missing, the tool self-computes the region envelope trace instead (slower, "
    "same idea).",
)

# ------------------------------------------------------------ page 2 channels

CHANNELS_TABLE = tip(
    "Rig load channels",
    "One row per actuator/piston = one unit static solve in the virtual rig "
    "model = one column s<sub>k</sub> of the influence library. The solver "
    "finds channel loads P so the static field matches the dynamic target:",
    formula=F_TIER2,
    footer="Hover each column header for its exact meaning. Positive load = "
    "push along the stated direction vector.",
)
ADD_CHANNEL = tip(
    "Add channel",
    "Appends a channel row with defaults (unit_load 1000, free name/label). "
    "Blank bounds mean unbounded (&plusmn;&infin;); a push-only actuator should "
    "get bounds 0 … capacity.",
)
REMOVE_CHANNEL = tip("Remove selected", "Deletes the selected channel rows.")

CHANNEL_COLUMN_TIPS = {
    "name": tip(
        "Channel name",
        "Unique identifier used in load tables, reports and pattern CSVs "
        "(e.g. <code>P1_fwd_vert</code>).",
    ),
    "case_label": tip(
        "Unit-field case label",
        "Selects this channel's unit stress field: in the <b>wide CSV</b> it "
        "matches the column suffix (<code>sx_&lt;case_label&gt;</code> …); in "
        "the <b>.rst</b> layout a numeric label selects that result set id, "
        "otherwise sets are taken in channel order.",
    ),
    "unit_load": tip(
        "Unit-solve load magnitude",
        "The force magnitude the unit static solve was actually run at. The "
        "supplied field is divided by this to get the per-unit influence field.",
        formula="s<sub>k</sub> = &sigma;<sub>as-solved</sub> / unit_load",
        footer="Solving at realistic magnitude (e.g. 1000 N) and normalizing "
        "here is numerically cleaner than a literal 1 N solve.",
    ),
    "point_x": tip("Application point X", "Actuator contact point, global CS, length units. "
                   "Documentation + load-table traceability; the stress response comes from "
                   "the unit field itself."),
    "point_y": tip("Application point Y", "Actuator contact point, global CS."),
    "point_z": tip("Application point Z", "Actuator contact point, global CS."),
    "dir_x": tip(
        "Direction X (unit vector)",
        "Load direction in the <b>global CS</b>. Must be a unit vector "
        "(checked on run). A solved load P &gt; 0 means force P·d&#770; — i.e. "
        "<b>push along this direction</b>. Never flip the sign here to fix a "
        "mismatch; fix the unit solve or the bounds instead.",
        formula="F = P &middot; (d<sub>x</sub>, d<sub>y</sub>, d<sub>z</sub>), "
        "&nbsp;|d| = 1",
    ),
    "dir_y": tip("Direction Y (unit vector)", "See Direction X — component of the unit "
                 "direction vector in the global CS."),
    "dir_z": tip("Direction Z (unit vector)", "See Direction X — component of the unit "
                 "direction vector in the global CS."),
    "lower_bound": tip(
        "Lower load bound",
        "Minimum admissible channel load (force units). <b>Push-only actuator: "
        "0</b>. Blank = &minus;&infin;. Enforced exactly by the bounded solver; "
        "a solution pinned at a bound is flagged <i>at bound</i> in the results "
        "(meaning the unconstrained optimum wanted more than the hardware "
        "allows).",
    ),
    "upper_bound": tip(
        "Upper load bound",
        "Actuator capacity (force units). Blank = +&infin;. Get the real "
        "capacity from the rig subcontractor's datasheet — open item ESL-3 in "
        "the methodology note.",
    ),
    "interface_channel": tip(
        "Load-history column (Tier-1 pattern)",
        "Name of this channel's column in the interface load-history CSV. "
        "Defines the pattern entry L<sub>k</sub>(t*) for the pattern-scaled "
        "route. Leave blank if this channel has no counterpart in the history "
        "(then Tier 1 needs a pattern CSV instead).",
    ),
    "apdl_node": tip(
        "APDL pilot node (verification)",
        "Node id in the <b>rig model</b> where the verification snippet applies "
        "this channel's force (<code>F,node,FX/FY/FZ,…</code> in "
        "<code>verify_forces_tier*.inp</code>). Typically the remote-point "
        "pilot node of the actuator contact. Blank &rarr; the snippet emits a "
        "comment instead of a command.",
    ),
    "gang": tip(
        "Gang group",
        "Channels sharing one hydraulic circuit / controller get the same gang "
        "name and are solved as <b>one unknown</b> r: each member carries "
        "P<sub>k</sub> = ratio<sub>k</sub>·r. Bounds of all members are "
        "intersected through their ratios (negative ratios allowed). Blank = "
        "independent channel.",
    ),
    "gang_ratio": tip(
        "Gang ratio",
        "This channel's fixed multiplier within its gang group: "
        "P<sub>k</sub> = ratio<sub>k</sub>·r. Sign encodes opposed actuators "
        "on one circuit.",
    ),
    "notes": tip("Notes", "Free text carried verbatim into esl_loads.csv "
                 "(hardware ids, datasheet refs, …)."),
}

# ------------------------------------------------------ page 3 region/mapping

COORD_TOL = tip(
    "Coordinate tolerance (ID join)",
    "When MSUP and rig-model nodes match by NodeID, their coordinates are "
    "cross-checked; a node pair further apart than this distance (length units) "
    "is <b>dropped from the evaluation set</b> and counted in the mapping "
    "report. Catches same-numbering-different-geometry mistakes.",
    footer="Default 0.1 mm — tighten for fine meshes.",
)
KDTREE_DIST = tip(
    "KD-tree max distance (fallback matching)",
    "If too few nodes match by ID (renumbered meshes), each MSUP node is "
    "matched to its <b>nearest rig-model node</b> instead; pairs further apart "
    "than this radius are rejected. Large RMS in the mapping report with this "
    "fallback usually means wrong model pair or wrong length units.",
)
MIN_ID_FRAC = tip(
    "Minimum ID-match fraction",
    "If at least this fraction of MSUP nodes finds the same NodeID in the rig "
    "model, the ID join is trusted; below it, the KD-tree coordinate fallback "
    "runs. 0.9 default.",
)
CHECK_BUTTON = tip(
    "Pre-flight check (no solve)",
    "Loads every configured input, verifies the modal basis (mode count of the "
    "stress CSV vs the coordinates file), builds the node mapping, and reports "
    "its quality — cheap insurance before a long derive. Nothing is solved and "
    "only <code>gui_config.json</code> is written.",
)
MAPPING_LABEL = tip(
    "Mapping quality",
    "<b>id_join</b> = same NodeIDs in both models (best). "
    "<b>kdtree_fallback</b> = matched by nearest coordinates. RMS/max are "
    "match-distance statistics; <b>unmatched</b> nodes are excluded from "
    "matching and metrics. Poor mapping invalidates any derived load — fix "
    "meshes or tolerances first.",
)
REGION_MODE = tip(
    "Evaluation region &Omega;",
    "The node set on which the least-squares match and all metrics are "
    "computed. <b>top_vm_percent</b> — the hottest X% of mapped nodes by target "
    "von Mises (default; focuses the match where margin is consumed). "
    "<b>node_list_csv</b> — explicit NodeID list (e.g. a named selection "
    "export). <b>bbox</b> — axis-aligned box in model coordinates. "
    "<b>all</b> — every mapped node.",
    formula="min<sub>P</sub> &Vert;W<sup>&frac12;</sup>(&sigma;<sub>static</sub>(P) "
    "&minus; &sigma;<sub>dyn</sub>(t*))&Vert;<sup>2</sup> over &Omega;",
)
REGION_VALUE = tip(
    "Top-VM percent",
    "Only for region mode <i>top_vm_percent</i>: the percentage of mapped nodes "
    "kept, ranked by target von Mises at the instant. 5% default. 100% = whole "
    "mapped mesh.",
)
REGION_NODES = tip(
    "Region node list CSV",
    "Only for region mode <i>node_list_csv</i>: a CSV whose <code>NodeID</code> "
    "column (or first column) lists the evaluation nodes — e.g. exported from a "
    "Mechanical named selection.",
)
BBOX = tip(
    "Bounding box",
    "Only for region mode <i>bbox</i>: six comma-separated values "
    "<code>xmin, ymin, zmin, xmax, ymax, zmax</code> in model coordinates "
    "(length units). Nodes inside the box form the evaluation region.",
)
WEIGHTING = tip(
    "Node weighting",
    "<b>vm</b> — weight each node by its normalized target von Mises to a "
    "power: hotspots dominate the match while the field character is kept "
    "(recommended). <b>uniform</b> — every region node counts equally. The "
    "per-node weight is applied to all six tensor components of that node.",
    formula="w<sub>i</sub> = (&sigma;<sub>vm,i</sub> / &sigma;<sub>vm,max</sub>)"
    "<sup>p</sup>",
)
VM_EXP = tip(
    "VM weight exponent p",
    "Sharpness of the von-Mises weighting: p = 0 &equiv; uniform, p = 1 linear "
    "(default), p = 2 strongly hotspot-focused. Higher p improves the peak "
    "match at the cost of the surrounding field.",
)
TIKHONOV = tip(
    "Tikhonov regularization &alpha; (default 0 = OFF)",
    "Adds a penalty &alpha;&middot;&Vert;scaled P&Vert;&sup2; that damps wild "
    "load trade-offs between <b>nearly collinear unit fields</b> (adjacent "
    "pistons). It is deliberately OFF by default: regularization biases loads "
    "low, which is an <b>under-test risk</b> in a certification context. "
    "Consider a small &alpha; (10<sup>&minus;6</sup>…10<sup>&minus;3</sup>) "
    "only when the condition number warns and physical bounds don't already "
    "settle the trade-off; the report records &alpha; and the load-norm/residual "
    "pair so the choice stays defensible.",
    formula="min &Vert;W<sup>&frac12;</sup>(A&middot;P &minus; b)&Vert;<sup>2</sup> "
    "+ &alpha;&Vert;D&middot;P&Vert;<sup>2</sup>, &nbsp;D = diag(&Vert;col&Vert;)",
)
UNDER_TEST_TOL = tip(
    "Under-test tolerance",
    "A node counts as <b>under-tested</b> when the ESL field falls short of the "
    "dynamic target by more than this fraction (and the node is above the VM "
    "floor). Under-tested nodes are listed per case; across the selected case "
    "set the union must be empty or justified (methodology §5/§9).",
    formula="&sigma;<sub>vm,ESL</sub> &lt; &sigma;<sub>vm,dyn</sub>&middot;"
    "(1 &minus; tol)",
)
VM_FLOOR = tip(
    "VM floor fraction",
    "Nodes below this fraction of the region's peak target von Mises are "
    "ignored by the under-test check — low-stress nodes cannot meaningfully be "
    "'under-tested'. 0.10 default.",
    formula="check only nodes with &sigma;<sub>vm,dyn</sub> &ge; floor &middot; "
    "max(&sigma;<sub>vm,dyn</sub>)",
)
MIN_PEAK_RATIO = tip(
    "Minimum peak ratio (acceptance)",
    "Accept a case only if the ESL reproduces at least this fraction of the "
    "dynamic peak at the critical node. 1.0 = full reproduction; values "
    "&gt; 1.0 demand deliberate over-test.",
    formula="&sigma;<sub>vm,ESL</sub>(crit) / &sigma;<sub>vm,dyn</sub>(crit) "
    "&ge; min_peak_ratio",
    footer="Thresholds are proposals until agreed with the compliance-"
    "verification engineers (open item ESL-2).",
)
RT_FACTOR = tip(
    "RT &rarr; operating-temperature factor (reported table only)",
    "The room-temperature rig cannot reproduce operating-temperature material "
    "behaviour, so loads are scaled by a factor derived from material property "
    "ratios (Young's modulus / strength, room vs operating temperature; max "
    "over the mesh — the project's documented method). It multiplies the "
    "<b>reported load table only</b> (column <i>magnitude_rt_scaled</i>) and "
    "never enters the ESL math, keeping dynamic-equivalence and temperature "
    "correction separately traceable.",
)
RT_NOTE = tip(
    "Scaling basis note (traceability rule)",
    "State <b>what the factor scales</b> (load / pressure / strain / stress) "
    "and its property-ratio basis. Copied verbatim into the report — the "
    "project's traceability rule for any applied factor.",
)

# ------------------------------------------------------------ page 4 instants

INSTANTS_PANEL_HINT = tip(
    "Why instants?",
    "Secondary vibrations are oscillatory: every node peaks at its own time, so "
    "<b>no single static case envelopes the whole casing</b>. Each rig case "
    "reproduces the stress state at one chosen instant t*. Per the project "
    "decision, the two blade-out rig cases are two instants of the <b>same "
    "event</b> — the governing peak, plus a second instant at which a "
    "<b>different casing region</b> reaches its critical state.",
)
INSTANTS_MODE = tip(
    "Instant selection mode",
    "<b>auto</b> — suggest candidates from evidence (recommended): cluster the "
    "per-node times-of-max of the hotspot population (MARS envelope files), or "
    "self-compute the region envelope trace when those files are absent. "
    "<b>explicit</b> — type the times yourself.",
)
EXPLICIT_TIMES = tip(
    "Explicit times [s]",
    "Comma-separated instants, e.g. <code>0.0123, 0.0456</code>. Each is "
    "snapped to the nearest sample of the modal-coordinates time grid (the "
    "snapped value is reported and used).",
)
N_SUGGESTIONS = tip(
    "Number of suggestions",
    "Upper limit on auto-suggested candidates. The governing global peak is "
    "always first; remaining slots go to hotspot clusters ranked by VM-weighted "
    "importance.",
)
QUADRATURE = tip(
    "Quadrature companion",
    "Adds a candidate a quarter period after the governing peak. For a "
    "narrowband (single-frequency-dominated) response the stress pattern there "
    "is shifted ~90&deg; — locations that were near zero at t* are near their "
    "extreme. f&#8320; is estimated from the FFT of the dominant modal "
    "coordinate around t*.",
    formula="t<sub>q</sub> = t* + 1 / (4&middot;f&#8320;)",
)
HOTSPOT_PCT = tip(
    "Hotspot top percent (MARS-envelope mode)",
    "The share of nodes — ranked by MARS peak von Mises — whose times-of-max "
    "are clustered into candidate instants. 2% default keeps the analysis on "
    "the locations that matter.",
)
CLUSTER_DT = tip(
    "Cluster window dt [s]",
    "Hotspot times-of-max closer together than this window merge into one "
    "candidate (their VM-weighted representative time). Set it near the "
    "dominant response period to avoid splitting one physical event into "
    "several candidates.",
)
SUGGEST_BUTTON = tip(
    "Suggest instants from evidence",
    "Runs the suggestion analysis on a worker thread and fills the table. "
    "Uses the MARS envelope files when both are configured; otherwise "
    "reconstructs the region VM(t) envelope from the modal inputs and picks "
    "its prominent peaks.",
)
INSTANTS_TABLE = tip(
    "Candidate instants",
    "<b>Checked rows become the derive cases.</b> Aim for the governing peak "
    "plus instants whose <i>driver nodes</i> lie in different regions — that is "
    "exactly the two-rig-case policy. Add rows via explicit times if a wanted "
    "instant is missing.",
)
INSTANTS_HEADER_TIPS = {
    "use": tip("Use", "Checked instants are derived as cases when you press "
               "<i>Derive ESL load sets</i> (unchecked rows are kept for reference)."),
    "time [s]": tip("Instant t* [s]", "Snapped to the modal-coordinates time grid."),
    "reason": tip(
        "Why this instant was suggested",
        "<b>global_vm_max</b> — the governing peak (Case 1). "
        "<b>hotspot_cluster</b> — a cluster of nodes peaking together at another "
        "time (candidate for the second, different-region case). "
        "<b>envelope_peak</b> — a prominent peak of the self-computed region "
        "envelope. <b>quadrature_of_…</b> — quarter-period companion. "
        "<b>explicit</b> — typed by you.",
    ),
    "driver node": tip(
        "Driver node",
        "The node whose peak defines this instant. Compare driver locations "
        "across rows: instants driven by nodes in <b>different regions</b> are "
        "the right pair for the two blade-out cases.",
    ),
    "VM at driver": tip("Von Mises at driver", "Target von Mises at the driver node at "
                        "this instant (stress units). NaN for quadrature companions — their "
                        "value lies in the shifted pattern, not the driver amplitude."),
    "cluster": tip("Cluster size", "Number of hotspot nodes whose times-of-max merged "
                   "into this candidate (MARS-envelope mode)."),
}

# -------------------------------------------------------------- page 5 derive

TIER = tip(
    "Derivation route (tier)",
    "<b>1 — pattern-scaled (stress-matched DLF)</b>: keep the physical load "
    "pattern L(t*) and scale it by one factor &lambda;, reported as the "
    "<b>effective dynamic amplification factor</b> — the certification-friendly "
    "narrative.<br><b>2 — constrained least squares</b>: let every channel vary "
    "freely within its bounds for the best achievable field match.<br>"
    "<b>both</b> (recommended): derive and report the two side by side; Tier 1 "
    "is exactly Tier 2 restricted to one degree of freedom, so their residuals "
    "are directly comparable.",
    formula=F_TIER1 + "<br>" + F_TIER2,
    footer="Why not just apply L(t*) statically? Because it omits the inertia "
    "and damping forces: " + F_EXACT_ESL,
)
PATTERN_CSV = tip(
    "Tier-1 pattern CSV (optional override)",
    "Two columns <code>channel, value</code> — one row per rig channel. "
    "Overrides the pattern from the load history. Typical use: paste the "
    "interface resultants at t* (Route A / mcf_dpf_section_resultants output) "
    "as the pattern — then &lambda; &asymp; 1 is expected, a strong "
    "cross-check between the two routes.",
)
OUTDIR = tip(
    "Output folder",
    "Absolute path; created if missing. Receives <code>gui_config.json</code>, "
    "<code>run_manifest.json</code> (SHA-256 of every input — the traceability "
    "anchor), <code>esl_report.md</code>, <code>instants_used.csv</code>, "
    "<code>mapping_report.json</code>, and one <code>case_t…</code> folder per "
    "instant with load tables, fields and APDL snippets.",
)
DERIVE_BUTTON = tip(
    "Derive ESL load sets",
    "Full chain on a worker thread: load inputs &rarr; map meshes &rarr; "
    "reconstruct the tensor target at each checked instant &rarr; bounded "
    "weighted least-squares solve per tier &rarr; equivalence metrics &rarr; "
    "write all outputs. The window stays responsive; progress streams to the "
    "log. Results open automatically on the next page.",
    formula="target: " + F_RECONSTRUCT,
)

# ------------------------------------------------------------- page 6 results

CASE_COMBO = tip(
    "Case",
    "One derived case per checked instant; the id encodes the time "
    "(<code>t0p001200</code> = t* = 0.0012 s). Select to inspect its loads and "
    "metrics.",
)
RESULT_TIER_COMBO = tip(
    "Tier",
    "Switch between the pattern-scaled (1) and constrained-LS (2) results of "
    "this case. Comparing their residuals shows how much fidelity the simple "
    "one-factor narrative gives away.",
)
METRICS_LABEL = tip(
    "Equivalence metrics",
    "<b>&lambda;</b> — effective dynamic amplification factor (Tier 1 only): "
    "how much the instantaneous load pattern must be amplified for the static "
    "field to match the dynamic one. "
    "<b>peak ratio</b> — &sigma;<sub>vm,ESL</sub>/&sigma;<sub>vm,dyn</sub> at "
    "the critical node; acceptance requires &ge; the configured minimum. "
    "<b>R&sup2;</b> — weighted goodness of fit on the tensor components (the "
    "quantity the solver minimizes). "
    "<b>Pearson(VM)</b> — shape correlation of the von Mises fields; a "
    "<i>negative</i> value almost always means a sign or channel-mapping error. "
    "<b>under-test</b> — count of nodes failing the deficit tolerance. "
    "<b>cond</b> — condition number of the design matrix; &#9888; above the "
    "threshold means nearly collinear unit fields (see Tikhonov tooltip).",
)
LOADS_TABLE = tip(
    "Derived channel loads",
    "The static loads to apply on the rig (and in the verification solve). "
    "Positive = push along the channel's direction vector. Columns are "
    "explained in their headers.",
)
LOADS_HEADER_TIPS = {
    "channel": tip("Channel", "Rig channel name from the Channels page."),
    "magnitude": tip(
        "Load magnitude",
        "Solved channel load in force units, at the analysis (operating) "
        "condition — before any room-temperature scaling.",
    ),
    "RT-scaled": tip(
        "RT-scaled magnitude",
        "Magnitude &times; the RT&rarr;operating factor from the Region page — "
        "the value the room-temperature rig should actually apply. Equal to "
        "<i>magnitude</i> when the factor is 1.0.",
    ),
    "at bound": tip(
        "At bound",
        "'yes' = this channel is pinned at its lower/upper bound: the "
        "unconstrained optimum wanted a load outside the actuator's range, so "
        "the residual is non-zero. Consider more capacity or another channel "
        "layout if a critical channel saturates.",
    ),
    "pattern value": tip(
        "Pattern value L<sub>k</sub>(t*)",
        "Tier 1 only: this channel's entry in the instantaneous load pattern. "
        "magnitude = &lambda; &middot; pattern value.",
    ),
    "unconstrained": tip(
        "Unconstrained diagnostic",
        "Plain least-squares solution ignoring bounds and regularization "
        "(SVD-backed lstsq — same diagnostic the load-reconstruction tool "
        "records). A large gap to <i>magnitude</i> shows how strongly bounds "
        "or &alpha; shaped the answer.",
    ),
}
HOTSPOTS_TABLE = tip(
    "Hotspot comparison",
    "The region's highest-stressed nodes (by dynamic target), dynamic vs ESL "
    "side by side. Ratio &lt; 1 means locally under-tested; check the "
    "under_test_nodes.csv and the residual field for the full picture.",
)
HOTSPOTS_HEADER_TIPS = {
    "NodeID": tip("NodeID", "Node number (MSUP model numbering)."),
    "vm_dyn": tip("Dynamic von Mises", "Target: reconstructed transient stress at "
                  "this node at t*.", formula=F_VON_MISES),
    "vm_esl": tip("ESL von Mises", "Achieved: static field of the derived loads at "
                  "this node."),
    "ratio": tip("Ratio", "vm_esl / vm_dyn — 1.0 is a perfect local match; &lt; 1 "
                 "under-tests, &gt; 1 over-tests this node."),
    "signed_vm_dyn": tip(
        "Signed VM (dynamic)",
        "Von Mises with the sign of the trace (&sigma;<sub>x</sub>+&sigma;"
        "<sub>y</sub>+&sigma;<sub>z</sub>) — distinguishes tension-like from "
        "compression-like states, which plain von Mises hides.",
    ),
    "signed_vm_esl": tip("Signed VM (ESL)", "Same signed measure for the achieved "
                         "static field — compare signs to catch matches that agree in "
                         "magnitude but not in sense."),
}
OPEN_FOLDER = tip(
    "Open output folder",
    "Opens the derive output folder in Explorer: report, manifest, per-case "
    "CSVs (fields are contour-ready with NodeID/X/Y/Z), APDL snippets.",
)

# -------------------------------------------------------------- page 7 verify

VERIFY_CASE = tip(
    "Case to verify",
    "The derived case whose stored target the solved field is compared "
    "against.",
)
SOLVED_ROW = tip(
    "Solved field CSV",
    "Nodal stress export of the <b>combined verification solve</b>: apply the "
    "derived loads (use <code>verify_forces_tier*.inp</code>) in the virtual "
    "rig model with real contacts and pressure ON, solve once, export "
    "<code>NodeID [, X, Y, Z], sx … sxz</code>. Nodes are joined to the target "
    "by NodeID.",
)
VERIFY_BUTTON = tip(
    "Verify against target — the Open Item C1 evidence",
    "The derived loads came from <b>linear</b> unit fields; the real rig model "
    "has nonlinear bolted contacts and a pressurized state. This comparison "
    "shows whether the combined nonlinear solve still reproduces the target "
    "(combined-solve &asymp; superposed prediction — exactly the C1 check). "
    "Acceptance: peak ratio &ge; minimum and zero under-test nodes. If the "
    "critical stress drifted, apply the recommended correction and re-verify:",
    formula="&lambda;<sub>corr</sub> = &sigma;<sub>vm,dyn</sub>(crit) / "
    "&sigma;<sub>vm,solved</sub>(crit)",
    footer="The corrected table esl_loads_corrected.csv is written next to the "
    "case outputs. If divergence stays large, regenerate the unit fields as "
    "linear perturbation solves about the pressurized preloaded state "
    "(methodology §8, open item ESL-4).",
)
