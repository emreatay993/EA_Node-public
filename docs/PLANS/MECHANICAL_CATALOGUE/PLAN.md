# COREX Mechanical Catalogue — Detailed Implementation Plan

Status: **COMPLETED — T01–T18 ACCEPTED; INDEPENDENT INTEGRATION REVIEW PASSED**. Implementation resumed on 2026-09-07 and completed on 2026-09-09 against the approved 261 contract. [TASK_LEDGER.md](TASK_LEDGER.md) records the separate task commits and accepted evidence; the [final QA matrix](../../specs/perf/MECHANICAL_CATALOGUE_QA_MATRIX.md) records verification outcomes and material limitations.

Planning baseline and execution amendment: 2026-09-07. The user approved the eight-node layout, then explicitly authorized implementation, required verification using disposable fixtures and available licensed installations, and separate local task commits. After T01 found no accessible 2025 R2 installation, the user replaced that release requirement with **2026 R1 (261) as the sole initial reference and acceptance release**. The former planning-only status and 252 gate are historical; all other scope and acceptance requirements remain in force. Current execution status belongs to TASK_LEDGER.md.

Read this **entire file** and [TASK_LEDGER.md](TASK_LEDGER.md) before implementation and after **every** coordinator compaction, restart, or handoff. Follow current repository `AGENTS.md` as well. Do not reconstruct requirements from screenshots or conversation summaries alone.

## Summary

Build eight typed nodes under the exact Library category **FEA / ANSYS / Mechanical**. Use Ansys 2026 R1 (`261`) as the sole initial reference and acceptance release, with capability-checked operation on later releases. Ansys 2025 R2 (`252`) and earlier releases are outside the initial supported scope; no compatibility with them is claimed. Use PyMechanical for Mechanical operations and PyWorkbench to retain ownership of Workbench projects. Use existing COREX tables, images, data trees, handles, graph execution, and shared control widgets.

| ID | Display name | Purpose |
| --- | --- | --- |
| `mechanical.open_model` | Open Mechanical Model | Open an isolated working model from a standalone Mechanical file or Workbench project/archive. |
| `mechanical.search_tree` | Search Mechanical Tree | Query model data through eleven visible filter categories with explicit COREX background semantics; report property values and tabular-definition presence. |
| `mechanical.fea_table` | FEA Table | Extract model-definition tables, supported result/probe tables, and supported worksheets into existing COREX tables. |
| `mechanical.camera_views` | Mechanical Camera Views | Return named/current camera records, names, and readable numeric camera details. |
| `mechanical.export_image` | Export Mechanical Image | Capture selected objects in selected views, returning images and optional image files. |
| `mechanical.run_script` | Run Mechanical Script | Execute Mechanical Python once per selected analysis, or once for the whole model. |
| `mechanical.apdl_snippet` | Mechanical APDL Snippet | Create/update node-owned APDL snippets for all or selected load steps. |
| `mechanical.save_model` | Save Mechanical Model | Explicitly save standalone models, whole Workbench projects/archives, or a selected Workbench model as a standalone export. |

### Locked user decisions

1. **Every input control exposes its own typed, connectable data port.** This includes optional controls, file selectors, multiline editors, toggles, sliders, lists, and controls in collapsed sections. A wire overrides the local default through the existing COREX property-default route.
2. Collapsing a section uses existing Signal Plot behavior: individual controls/handles disappear, the group connection marker remains, and port identities/wires survive. Expanding restores each handle. Do not replace this with permanently visible compact rows.
3. Every run that requires a Mechanical operation reloads the source model. Unsaved modifications do **not** accumulate between runs. Share a model session within a run; place mutations and saving in that same run's data dependency chain.
4. The default UI mode is **Background**. Standalone files use embedded PyMechanical in a dedicated process; Workbench files use a Workbench-managed background Mechanical server. **Interactive** is optional. Embedded does not mean embedding the Mechanical GUI inside a COREX node.
5. Open standalone `.mechdat` / `.mechdb`, Workbench `.wbpj` / `.wbpz`, and the genuine standalone archive `.mechpz`. A `.mechdat` is a model export, not a complete archive of external solver files.
6. Saving is explicit through Save Mechanical Model. Native archive preservation is conditional on the applicable inclusion controls: requested inclusions must survive, intentional omissions must be reported, and an intentionally partial archive must never be described as complete.
7. **Selected Workbench model export is required and model-only.** Use native Workbench Model.Export to a run-owned `.dsdb`, followed by separate same-release standalone Open and SaveAs to `.mechdb` or `.mechdat`. This bridge never creates an archive or claims to preserve results, user files, imported files, Workbench topology, or project dependencies. Workbench projects archive natively to `.wbpz`; standalone models archive natively to `.mechpz`. See [BACKEND_DECISIONS.md](BACKEND_DECISIONS.md).
8. Image batching is every selected object × every selected view, ordered by objects then views and grouped by object. Two objects and three views produce six images.
9. Scripts run once per selected environment by default. Here an environment means a Mechanical **analysis tree object**, not a Python interpreter. A separate model-wide run-once setting is available.
10. Snippet selection means **load steps**, not arbitrary solver substeps. The Issue SOLVE control affects generated solver commands; it does not start a solve when the node runs.
11. Search **does not inspect table cells or compare complete tables**. It reports `has_tabular_data`, definition kind, and table identity/shape where available. FEA Table remains fully in scope for actual extraction; it was not deferred.
12. FEA Table includes model definitions **and** supported results/probes/worksheets. It may evaluate selected results from existing solved files by default, but must never launch a new solve implicitly.
13. Each completed implementation task gets **one separate task commit** after its required checks and review. Record its accepted hash in the single task ledger. Do not combine different completed tasks into one commit.
14. The plan must be usable by a fresh agent: exact ownership, interfaces, defaults, failure policies, tasks, evidence gates, and recovery rules are included below.
15. After a live 261 test rejected native Outline filtering in embedded mode, the user selected **COREX-owned background data filters**, with differences in difficult modes made explicit. Section 9 and BACKEND_DECISIONS.md define those meanings. Exact native Outline parity is not the acceptance target, and Search must not force an interactive session.
16. Archive inclusion is user-controlled through three Boolean ports under Save options: result/solution files, user files, and external imported files. The latter is active only for Workbench archives. COREX defaults all three to `True` to retain the prior complete-archive policy; wire values override local defaults. Inapplicable controls keep their ports but are disabled and are not passed to native APIs.

### Deliverable and evidence locations

- This file is the implementation authority; [TASK_LEDGER.md](TASK_LEDGER.md) is the sole execution status ledger.
- [REFERENCES.md](REFERENCES.md) separates documented API facts from unverified runtime behavior.
- [BACKEND_DECISIONS.md](BACKEND_DECISIONS.md) records live 261 export/camera evidence, the rejected native batch-filter route, the user's background-query choice, exact filter meanings and result-table dispatch.
- [VISUAL_BASELINE.md](VISUAL_BASELINE.md) registers the approved PNG/SVG sheets, icon references, and visual acceptance rules.
- `visuals/` contains design references, not production QML screenshots or completed node implementations.
- Future neutral live proof goes under `artifacts/verification_logs/mechanical_catalogue/`; register the final neutral QA matrix from the spec index in T18. Do not put private study provenance in tracked files.

## Key Changes

### 1. Architecture and existing owners

Use an internal trusted add-on, `ea_node_editor/addons/mechanical/`. Add-on code owns backend-specific behavior; it does not become a new general workflow engine or session framework.

| Concern | Existing owner to reuse | Planned addition or change |
| --- | --- | --- |
| Add-on discovery and installation metadata | `addons/catalog.py`, `addons/contracts.py`, `addons/registry_contributions.py` | Register one Mechanical add-on and its dependency-gated semantic contracts/function bundle. |
| Node declarations and controls | `nodes/node_specs.py`, function SDK, `nodes/builtin_functions/plot_signal.py` as a pattern | Add `addons/mechanical/function_nodes.py`; declare all controls/sections/ports as shared metadata. |
| Runtime handles and cleanup | `nodes/execution_context.py`, `execution/worker_services.py`, `execution/handle_registry.py` | A lazy Mechanical-specific run-session service using existing handle registration, resolution, leases, cancellation, and run cleanup. |
| Data-only values | `runtime_contracts/value_refs.py`, `data_types.py`, `value_codec.py` | Register bounded Mechanical object/property/camera inline contracts through the add-on manifest. |
| Tables and images | `runtime_contracts/scientific_values.py`, `scientific_codec.py`, existing `ImageValue` | Return existing `TableValue` and `ImageValue`; do not create another numerical-table transport. |
| Inspector metadata | `addons/property_edit_adapters.py` | One Mechanical metadata adapter over accepted execution snapshots. |
| Canvas metadata and refresh | `ui_qml/graph_scene_payload/factory.py`, `ui_qml/graph_scene_bridge.py` | Generalize the current Signal Plot enrichment seam once so registered metadata adapters also project canvas options. |
| Inline controls and group geometry | `ui_qml/components/graph/surface_controls/`, `GraphNodeSettingsGroupsLayer.qml`, `GraphNodePortsLayer.qml` | Reuse the existing searchable combo, list, text, textarea, path, toggle and slider widgets. No Mechanical-specific QML branch. |
| Icons | `nodes/builtins/icon_catalog.py`, `ui_qml/node_title_icon_sources.py`, `assets/node_title_icons/` | Add eight COREX-owned vector assets under the production `mechanical/` icon folder in T16. |
| Execution freshness | `execution/runtime.py::CorexRuntime._prepare_node_decisions`, `worker_runner.py::NodeExecutor` | All eight nodes use `_solution_reuse_scope="never"`; add focused same-run mutation revision checks. |

Planned add-on modules are `catalog.py`, `contracts.py`, `function_nodes.py`, `runtime.py`, `session.py`, `owner_process.py`, `backend.py`, `workbench.py`, `inspection.py`, `tables.py`, `graphics.py`, `commands.py`, `saving.py`, and `property_edit.py`. These are concrete behavior owners, not mandatory one-class wrappers. Keep closely related private functions in their owner; do not add interfaces/factories or forwarding modules with one implementation. The dedicated process protocol is private to this add-on.

Mechanical-specific types and validators live in `addons/mechanical/contracts.py` unless a type proves useful outside the add-on. Shared scientific contracts remain in their current runtime owners. Do not import Mechanical, Workbench, CLR, or add-on UI code into the graph domain. Do not import persistence codecs into runtime snapshot assembly.

### 2. Dependency and release policy

- Reuse the existing `ansys-mechanical-core>=0.12.6` dependency declaration. T01 records the exact package versions used with release 261 and establishes the supported minimum if current APIs require a newer version. Update `ansys`, `all`, and relevant packaging/install declarations together if a minimum changes.
- Add `ansys-workbench-core` for Workbench-backed sources. T01 pins the lowest tested version that provides `launch_workbench`, `run_script_string`, `start_mechanical_server`, and the necessary lifecycle operations. A missing Workbench package must not masquerade as a model-file error.
- Mechanical also directly requires `h5py>=3.16` for the narrowly qualified native state-file preservation check described in BACKEND_DECISIONS.md. Import it only inside the isolated owner when a qualifying SHA mismatch needs comparison; dependency discovery remains metadata-only.
- NumPy/pandas are needed by existing scientific table construction. Declare direct dependencies where imported; do not rely on an accidental development environment installation. Backend imports stay lazy and outside the UI process.
- Existing DPF infrastructure is available, but native model table extraction is authoritative. Do not add a DPF replacement for an existing Mechanical table merely because it is convenient. A DPF adapter is allowed only for a specifically named required family whose equivalence is demonstrated in T01/T08; it must preserve Mechanical scope, units, coordinate frame, averaging and result-set semantics.
- Discovery inspects package availability and installation metadata without launching Mechanical, checking out a solver license, opening a source file, or starting Workbench.
- Release selection uses integer code `261` and future discovered codes. The `Auto` selection chooses the newest installed code at least 261; explicit codes below 261 are rejected as unsupported. Never downgrade/open a newer database in an older release silently. A failed open reports the source, selected release and backend error.
- Initial acceptance requires the complete declared contract on 2026 R1 (261). Later releases may run only after the capability handshake succeeds; report them as capability-checked, not as having passed full release acceptance. The unavailable 252 installation is no longer a gate. Reject a missing required capability rather than guessing another API name.

### 3. Run-owned session lifecycle

1. Open constructs a session key from `(run_id, open_node_id, target_DataPath, target_iteration)`. Repeated dependent calls within that run reuse the session. Another Open node, another input item, or another run receives an independent session.
2. The source is read into a run-owned working location. Preserve the original input file/project and its accompanying files. A `.wbpj` working copy must retain project structure and resolve registered external dependencies; archive/unarchive or another vendor-supported project copy mechanism must be proved in T01. Do not copy only an internal Mechanical database out of the project.
3. Start one dedicated owner process for a standalone embedded `App`. Initialize the selected release there; import Mechanical namespaces only after initialization. All Mechanical API operations execute on that process's owning thread. Do not load CLR/embedded Mechanical into the Qt application or a shared multi-purpose COREX worker interpreter.
4. Workbench-backed runs retain a Workbench owner and its selected Model container. Open `.wbpj` with Workbench `Open`, unpack `.wbpz` with `Unarchive`, enumerate stable system IDs separately from visible labels, and connect via `start_mechanical_server` and PyMechanical. Shared Model cells map to one editing session within the run.
5. Interactive mode launches a real interactive server/editor. Do not use `App.launch_gui()` to convert the current embedded session: that helper opens a temporary copy and does not preserve the desired ownership semantics.
   Standalone `.mechpz` opening explicitly uses `Project.Unarchive(archivePath, full_target_mechdb_path, overwrite)`; ordinary Project.Open rejects archives in the 261 live probe. Open accepts the returned standalone database, not a renamed archive.
6. Every owner request includes request ID, run/session identity, expected model revision, operation name, and bounded data-only arguments. Commands are allowlisted backend operations; the explicitly authored Script and APDL text are the only general user-code fields. Never construct executable Python by interpolating object names, filenames, or selector strings; pass/encode them as data.
7. Register a Model-state wrapper through existing runtime handles. Its immutable metadata identifies the run/session/revision and its accepted catalogue output locator. The underlying process/session lives in the run service. Do not mutate registered handle metadata and do not give borrowed object references independent process ownership.
8. Background sessions close at terminal run cleanup after all dependent nodes finish. Add an explicit `MechanicalSessionService.cleanup_run(run_id)` invocation to `WorkerServices.cleanup_run` on every terminal path; ordinary handle lease release is insufficient because accepted outputs may hold independent solution-resource leases. Service cleanup closes owned processes, marks session admission terminal and clears API objects even if immutable observational wrapper metadata remains leased. Failed/cancelled runs close every process they own with bounded cleanup in both modes. A successful Interactive window is inspection-only after its run and may remain until the next graph-run start in the **same workspace**, workspace close, application shutdown, or explicit owned-session retirement. Before any next graph run in that workspace, close all of that workspace's retained interactive inspection instances, even when the new run omits Open; a run in workspace B does not close retained instances owned by workspace A. The new run opens a fresh source where applicable. Carry workspace identity in the run/session lifecycle metadata needed to enforce this rule. Retained handles are expired and cannot be admitted to any later run. Display the fresh-run and workspace-scoped inspection behavior in Open's help text.
9. Do not kill unrelated Ansys/Workbench processes. Retain exact owned process IDs and transport/session identities. Cancellation first requests cooperative stop; after five seconds, terminate only this run's owned owner/process tree and mark the operation failed. Default open/operation timeout is 600 seconds; user controls may override within declared bounds.
10. Completed source-derived snapshots and images may remain visible after cleanup. They are observations from the completed run, not usable live model handles. A partial downstream consumer may read current detached data ports without executing Open. If it requires a live Model or run-bound selector, its Open dependency must be recomputed; an expired Model input cannot reconnect implicitly.
11. The source changes only through an explicitly requested Save destination/overwrite operation or explicitly authored user code that itself saves. Temporary working saves needed by Workbench archive/export are internal to the isolated working project. A fresh run always uses the currently saved source bytes, including an explicitly overwritten source if the user chose that destination.

No cross-run in-memory session cache, ambient singleton, automatic reconnect to a user-launched session, remote host selector, active global pool, ownership keyed only by Open-node identity, or hidden source overwrite is in scope.

### 4. Mutations, ordering, and result freshness

- All eight nodes retain `never` computation reuse for requested operations. The user-approved current-result refinement allows implicit dependencies in partial consumer runs to provide already-current detached data ports without executing those operations. Explicit operations, full runs, Force Recompute, changed inputs, and required executing/ordering dependencies retain fresh execution. Process reuse and consumption of a completed data snapshot are separate concepts.
- A Model-state wrapper has an expected revision. Reads must match the session's current revision. Successful Script/Snippet mutation advances the revision and returns a new wrapper of the same public Model type. Previous wrappers and backend-bound selection snapshots become stale.
- A mutation reserves the session, checks cancellation/revision, executes serially, and invalidates inspection caches after **every attempted mutation**, including partial failure. Do not return a success Model output after a partial mutation failure. The next run is the recovery path from the original source.
- Users order model changes by wiring `Open.Model -> Script.Model -> Snippet.Model -> Save.Model` and by connecting readers to the correct resulting Model output. Two sibling mutators from one revision cannot both proceed: the second receives a stale-model error. Do not infer ordering from canvas position or silently sequence ambiguous branches.
- FEA Table result evaluation and image capture may temporarily change result display/graphics state. Save and restore those presentation settings in `finally`. For a configured result initially `By=Time` with inactive `SetNumber=0`, if the public setter rejects restoring zero, restore `By`, `DisplayTime`, and `CalculateTimeHistory` exactly, retain only the resulting valid positive SetNumber, and report the before/after inactive drift. Every other restoration failure taints the session and fails the node. Tree-active objects and graphics restoration remain exact and independent. If a future native interactive search route changes outline filters, it must capture/restore the exact prior query/mode/inversion and changed active/expanded state too; clearing a prior filter is insufficient.
- Save may close/reopen a Workbench editor. It returns a fresh admissible Model-state wrapper, updates the session revision/connection generation and publishes a refreshed catalogue. Never retain old CLR proxy objects across the reconnect.
- Reuse the existing invalidation authority when marking already displayed sibling observations stale after a mutation. Do not directly edit solution-store internals or fabricate UI state. Tests must distinguish next-run recomputation (already provided) from same-run stale-reference rejection (new add-on responsibility).

### 5. Metadata and autocomplete without backend calls while typing

The existing Model handle's metadata is bounded and immutable; it must not contain the complete Mechanical tree. Use the existing **Info** and **Report** table outputs for accepted, data-only discovery snapshots instead of adding a new visible catalogue port.

- `Open.Info` contains typed table rows for session information, Workbench systems, object identities, visible property descriptors, available table descriptors, and saved/current view descriptors. Operational summary rows come first. It contains metadata, never raw solver arrays or table-cell data.
- Script, Snippet and Save use the same discovery row schema in `Report`, after their operation receipt rows, whenever they return a new Model revision. The new immutable Model-handle metadata contains the exact catalogue locator: `catalogue_id` (a new UUID for this emitted snapshot), `producer_node_id`, `producer_port` (`info` or `report`), `producer_path` (integer DataPath), `producer_iteration`, `run_id`, `session_id`, and `model_revision`. These are identity facts, not mutable metadata.
- The Mechanical property adapter resolves that sibling accepted output using `PropertyEditAdapterContext.current_output_provider`; it never resolves a live runtime handle in the UI. The provider returns a whole output DataTree: inspect the named `producer_path` branch and find exactly one TableValue whose session-summary row matches **all** locator identity fields. Do not assume the first output item or revision 0 identifies the correct model. `producer_iteration` is checked against the table summary, not treated as an unconditional list index, because omitted outputs can change output-item positions. Zero matches means unavailable/evicted metadata; multiple matches or inconsistent fields mean invalid metadata. Preserve the user's draft/selection, show the unavailable state and do not fall back to another model's table. This survives a Model value passing through a Panel/Select node because the locator travels with the immutable Model metadata.
- Build one detached search/options index per accepted catalogue table identity/revision. Read the already accepted immutable descriptor columns once; do not repeatedly materialize tables on paint or every keystroke. Shared NumPy/scientific readers may inspect accepted descriptor buffers; no file reader, script execution, Mechanical call or Workbench call is allowed in projection.
- Use a bounded catalogue of up to 100,000 descriptor rows and 64 MiB encoded content, below existing scientific transport limits. Put `catalogue_complete`, omitted row count when known, and `model_revision` in the session summary row. An incomplete suggestion catalogue produces a visible informational message; it does not narrow the actual backend Search operation. Search traverses the full selected model during execution, with cancellation. Never silently call partial suggestions complete search results.
- Suggestions rank exact match, prefix match, then substring match, preserving stable source order within a tier. Filter locally as the user types. Limit the popup to 50 visible suggestions, with normal scroll/filter behavior. The displayed label may include the full tree path to disambiguate duplicate names; the stored code is a stable selector, not its decorated label.
- Preserve keyboard focus, uncommitted drafts, exact string/int selector identity, unknown authored selectors, and connected-input read-only presentation using the existing Signal Plot/shared controls behavior. Missing metadata shows an empty editable selector with an explanatory placeholder; it must not launch a model just to fill the dropdown.
- The first run with no selected Workbench system lists systems when more than one distinct model exists. Return a **discovery-only accepted result**: publish `Info` with `status=system_required`, omit the Model output, emit a normal warning requesting selection, and close this discovery session. Open's metadata adapter reads its own accepted Info table in this state. Downstream required Model inputs remain waiting; there is no successful live model. Do not rely on an unimplemented diagnostic payload/provider. The ordinary next run uses the selected system. A single distinct model is selected automatically.
- The shared canvas metadata hook takes the same adapter context and item schema as the existing inspector path. Migrate Signal Plot onto that hook so the new path is genuinely shared. Keep backend policy in the add-on, dispatch in existing graph bridges, and control rendering in existing QML widgets.

The common Info/Report table schema is fixed here so producers and adapters do not design independent formats. Columns occur in the following groups, in the listed order; every table has all columns. Empty strings mean a non-applicable text field, null means a non-applicable nullable scalar. No nested Python objects are stored in cells.

| Columns | Scientific column kind | Rules |
| --- | --- | --- |
| `schema_version`, `model_revision`, `producer_iteration` | Integer | Required in every row; schema is 1. |
| `record_kind`, `catalogue_id`, `producer_node_id`, `producer_port`, `producer_path`, `run_id`, `session_id`, `document_id`, `source_key` | Text | Required identity fields in every row; `producer_path` is the canonical JSON spelling of the integer path array, decoded/validated as data. |
| `system_key`, `system_label`, `selector_code` | Text | Stable identity codes separate from labels; system rows exist even in discovery-only results. |
| `object_id`, `parent_id`, `analysis_id` | Nullable integer | Native IDs; no zero-as-missing convention. |
| `object_path`, `display_name`, `api_type`, `property_key`, `property_caption`, `display_value`, `definition_kind` | Text | Display/identity metadata; no table-cell values. |
| `scalar_value` | Nullable float | Finite scalar quantity magnitude where available. |
| `has_tabular_data` | Nullable Boolean | Explicit true/false for property descriptors; null for unrelated row kinds. |
| `unit`, `quantity_name`, `formula`, `table_key`, `table_family` | Text | Definition metadata, not evaluated samples. |
| `row_count`, `column_count`, `view_index`, `omitted_rows` | Nullable integer | Nonnegative when known; never fabricate counts for inaccessible tables. |
| `view_key`, `view_name`, `status`, `message` | Text | View identity or operation/summary diagnostics. |
| `catalogue_complete` | Nullable Boolean | Required on the session summary row; null on non-summary rows. |
| `relation_kind`, `relation_role`, `related_label`, `raw_source_id`, `scope_kind`, `relation_status`, `activation_state` | Text | Appended relation fields for the selected background-query contract. |
| `related_object_id`, `scope_count` | Nullable integer | Explicit relation target/count; do not infer missing or historical counts. |
| `body_hidden` | Nullable Boolean | Readable Body.Hidden flag, not effective associated-object visibility. |

`record_kind` is exactly one of `session`, `system`, `object`, `property`, `table`, `view`, `operation`, `relation`. Relation subjects use the existing object_id/path; kinds are `coordinate_system`, `source_model`, `body_visibility`, `environment`, `scope`; statuses are `available`, `not_applicable`, `unavailable`. Other row kinds leave the relation fields empty/null. There is exactly one session-summary row for the catalogue. All identity fields must agree across rows. Operation rows precede descriptor rows after the summary; duplicate catalogue IDs or malformed rows invalidate picker use. Selector codes are versioned JSON data strings containing kind, document/system identity, canonical object path and native ID where applicable; parse with the standard JSON library and validate the exact schema, never `eval`. The UI checks locator identity before indexing any descriptor rows. This metadata table and any built index remain transient and must not be serialized into authored `.cxproj` properties.

## Public Interface Changes

### 6. Types and transport

All data ports remain ordinary COREX `data` ports. Do not reintroduce execution/completed/failed ports or an `Any` escape hatch. User-facing type names are concise; fully qualified IDs and validators are internal.

| Semantic type | Carrier | Required content and validation |
| --- | --- | --- |
| `COREX.Mechanical.Model` | `RuntimeHandleRef` | Run-owned Model-state wrapper; immutable workspace, run and session identity, selected source/system, expected revision, release code, backend mode and accepted catalogue locator. Validate handle generation and service membership before use. |
| `COREX.Mechanical.Object` | `TypedInlineValue` | Schema 1; session/run/document identity, revision, ObjectId, parent ID, canonical tree path, visible name, API type/category and analysis identity where applicable. |
| `COREX.Mechanical.Property` | `TypedInlineValue` | Schema 1; owning object identity plus exact property key, caption, definition kind, display text, scalar magnitude/unit or formula metadata, `has_tabular_data`, available table descriptors. No table cells. |
| `COREX.Mechanical.CameraView` | `TypedInlineValue` | Schema 1; session/document/revision, kind (`current` or `saved`), name/index identity, focal point, up/view vectors, scene dimensions and their length unit; only documented/probed fields. |
| Existing COREX Table | `TableValue` | Numeric or mixed scalar columns and stable column order. Units/provenance are described below. Existing byte/shape/codec limits remain enforced. |
| Existing COREX Image | `ImageValue` | Validated PNG bytes; no raw QImage, viewport handle, path-shaped image substitute, or executable payload. |
| Existing Text / Boolean / Integer / Path | Existing built-in carriers | Exact explicit scalar/list/tree declarations; paths use the runtime path resolver and existing artifact admission when applicable. |

Inline snapshots contain only JSON-safe exact-schema data. Enforce the existing 1 MiB inline-payload and 64 KiB handle-metadata limits; the catalogue is a scientific table, not handle metadata. Reject unknown fields/schema versions, invalid identities, non-finite camera numbers, invalid vector lengths, negative revisions, cross-session references and expired generations. Property snapshots may indicate unreadable/unsupported values explicitly; do not invent a value or coerce a free DOF to zero.

Keep the model domain independent of the neutral FE/CAD scene domain. `COREX.Mechanical.Model` is not `COREX.Engineering.Scene`: a live authored Mechanical tree cannot be sent to Model Viewer as a neutral mesh automatically. Exported images can connect to existing Image/Media Panel; extracted tables connect directly to Signal Plot or table tools.

### 7. Common port/control rules

- All control rows below have `port=True`, `exposed=True`, a non-empty label/description, exact type, access mode and local default. Optional absence is distinct from an empty connected result.
- Abbreviations in the tables: **I** = Item access, **L** = List access per branch, **T** = whole DataTree access. `Object | Text` and `CameraView | Text` are explicit accepted-type unions, never an untyped port.
- Data-tree matching of ordinary scalar/control inputs follows COREX's existing principal/matching rules. Batch-consuming nodes use their explicit List/Tree adapters below so object/view combinations do not accidentally depend on repeat-last item matching.
- Disabled controls retain their port identity and authored value. A disabled conditional input is not consumed. An upstream connected value displays read-only in the local editor. Collapse changes geometry only, not topology or persistence.
- List selectors use real list values and the shared list editor/chips. Text such as `Isometric, Front` in a preview illustrates two selections; do **not** implement an implicit comma-splitting parser for names that may themselves contain commas.
- Object text selectors accept a canonical path or a unique visible name. If a visible name matches multiple objects, fail with disambiguating paths. Selection codes emitted by pickers contain stable source/system/path identity; validation verifies they still identify the intended object in this run. Do not choose the first duplicate silently.
- Version, mode, filter and other dropdowns store explicit codes; their visible English labels are presentation. Do not persist a localized enum label as an API enum identifier.
- Optional file outputs default to no path. There is no automatic write into the user's source directory. Persist authored values in normal node properties; app installation preferences remain app-wide.

### 8. Open Mechanical Model

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `file` / File | Path; I | Required; Open options. Accept `.mechdat`, `.mechdb`, `.mechpz`, `.wbpj`, `.wbpz`. |
| In | `system` / Model / system | Text; I | Empty = sole distinct model; otherwise require explicit selection; Open options. Only relevant to Workbench sources. |
| In | `mode` / Mode | Text enum; I | `background`; labels Background, Interactive; Open options. |
| In | `version` / Version | Integer; I | `0` = Auto; Open options. Other choices are discovered release codes >=261. |
| In | `working_folder` / Working folder | Path; I | Empty = run-owned working directory; Session options, collapsed. Never use an existing nonempty directory as disposable scratch. |
| In | `timeout_s` / Timeout (s) | Number; I | 600; finite range 1–86400; Session options, collapsed. |
| Out | `model` / Model | Mechanical Model; I | Only on successful open and selected model admission. |
| Out | `info` / Info | Table; I | Operation summary and accepted discovery descriptors from section 5. |

Open once per input item/path in the run. If a list of source files reaches the Item input, existing item iteration creates independent run sessions. Do not share a mutable session solely because two Open nodes use the same file. Validate source existence/type and destination ownership before launching. User-selected interactive mode may consume UI resources; background helpers remain hidden.

For a failed version/license/open/system-selection operation, return a clear node diagnostic and clean up partially started resources. Include available releases/systems when known. Do not quietly import geometry/results in place of opening the authored model.

### 9. Search Mechanical Tree

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. |
| In | `filter` / Filter | Text enum; I | `name`; Search. Exact visible mode list below. |
| In | `query` / Query | Text; I | Empty; Search; editable searchable selector. |
| In | `match` / Match | Text enum; I | `contains`; options Contains / Exact; Match options, collapsed. |
| In | `case_sensitive` / Case sensitive | Boolean; I | False; Match options. |
| In | `include_hidden_properties` / Include hidden properties | Boolean; I | False; Match options. Applies to property discovery, not changing tree suppression. |
| In | `invert` / Invert results | Boolean; I | False; Match options. |
| Out | `objects` / Objects | Mechanical Object; L | Deduplicated matching objects in original tree traversal order. |
| Out | `properties` / Properties | Mechanical Property; L | Matching descriptors; object-only searches include the selected objects' discoverable property descriptors within bounded output limits. |
| Out | `found` / Found | Boolean; I | True iff the complete search has at least one matching object/property. |
| Out | `details` / Details | Table; I | One row per match with object path, property caption/value, units, definition kind, tabular flag and any unreadable-property diagnostic. |

The eleven visible filter labels remain **Name, Tag, Type, State, Coordinate System, Model, Graphics, Environment, Scoping, Property Name, Property Value**. The user selected COREX-owned background queries after native Outline filtering failed in embedded 261. The Query editor uses the following explicit definitions; these are neither eleven name-substring aliases nor claims of native Outline parity.

| Filter | Required background query |
| --- | --- |
| Name | Displayed object Name; multiple terms ANDed. |
| Tag | Directly assigned ObjectTags names, with no inherited-tag inference. |
| Type | Actual DataModelObjectCategory/API type labels; do not guess native UI supergroup membership from names. |
| State | Explicit ObjectState and readable Suppressed flag. Map visible Not licensed to LicenseConflict and Underdefined to UnderDefined; keep other real enum labels. |
| Coordinate System | Direct documented coordinate bindings (CoordinateSystem, or type-aware probe selection/orientation). Show Explicit assignment; None/missing never implies Global. Documented Solution binding is distinct from Global/Unspecified/Unavailable. |
| Model | Current opened document/system identity or exact recorded ImportableObjectSourceId. Show Source ID when no trusted human label exists; do not infer assembly-cell labels. |
| Graphics | Body.Hidden flag only: Shown bodies / Hidden bodies. No indirect load/result association or effective viewport visibility inference. |
| Environment | Owning analysis; for shared/global objects only a tested native per-analysis activation relation establishes additional membership. Ancestry alone is not universal. |
| Scoping | Current explicit scope kind/reference/count from documented typed fields, preserving primary/source/target roles. Confirmed no scope field is an available `no_explicit_scope` classification; a readable empty selection is `empty_explicit_scope`; failed getters/unclassified types are unavailable. Do not provide historical Partial/lost-scoping detection. |
| Property Name | Visible Caption, retaining API key; hidden properties only when enabled. |
| Property Value | Scalar/enum StringValue, formula text or Tabular data summary, never table cells. |

Use the type-aware relation adapters and availability/error rules fixed in BACKEND_DECISIONS.md section 3. If data necessary to decide the selected query is unavailable for an applicable object, fail with `mechanical.search_incomplete`, not a falsely complete list or Found=False. Inversion never turns Unknown into a match. Reject unsupported Partial/lost-scoping text with an explanatory diagnostic instead of interpreting it as empty/UnderDefined. These differences appear in contextual Query labels/tooltips and Details metadata; no extra control or layout change is required.

Use `VisibleProperties`, `Caption`, and **`StringValue`** to obtain the displayed property label and selected dropdown text. Retain internal property identity separately. Constant quantities expose magnitude/unit and the displayed text; expressions retain their formula text and declared unit. Search does not numerically evaluate arbitrary formulas. A tabular definition contributes the display summary `Tabular data`, `definition_kind=tabular`, `has_tabular_data=True`, and available table names/shapes; it contributes **no cell contents**. Searching Property Value for `Tabular data` therefore finds definitions without reading their cells. A normal scalar property remains searchable by its visible text such as `500 N` or `Bonded`.

Plain-text matching uses Unicode-aware `casefold()` unless Case sensitive is enabled. Exact compares the entire query with the entire displayed text; it never tokenizes Name into words. Contains normally compares the whole query as a substring. Preserve interior whitespace for Exact, ordinary Contains, and bare Property Value operands; only Name + Contains splits the unquoted query on Unicode whitespace, discards empty terms, and requires every term as a substring in any order. Name receives no phrase/quote language; quotes there are literal text, and otherwise its nonempty query text remains unchanged. An empty or whitespace-only unquoted query means no restriction within the selected search universe.

Property Value alone may use `Property Name = Property Value`. Split on the first `=` outside double-quoted operands; later equals signs are value content, as in `Comment = "Load = 100 N"`. Each quoted operand must be one complete JSON-style string token, with standard JSON escapes including `\"` and `\\`; trim syntactic whitespace outside it while preserving decoded quoted content exactly. Bare operands retain interior whitespace, literal backslashes and apostrophes; trim only their syntactic edge whitespace. When an outside `=` is present, the property caption must be nonempty. An explicitly empty value is valid and matches only an available empty displayed value in both Exact and Contains modes; it never invokes unrestricted-search semantics. Without an outside `=`, Property Value is a single value query and has no caption restriction. Malformed or unmatched quotes/escapes are validation errors. Opaque source IDs and accepted picker identity codes are validated and resolved before this grammar, remain exact identities, and are never reinterpreted as plain text. Do not add regex, numerical tolerance matching, hidden unit conversion, table-content search, multiple clauses, or another query language. Nonempty categorical queries apply only to eligible readable records. Inversion complements available applicable predicates within that scope.

No matches returns empty lists, an empty Details table and `Found=False`. Mechanical's presentation behavior that may show the full tree on no match must not be copied into an existence-query result.

**261 live finding and resulting architecture:** Tree.AllObjects and DataModel.GetObjectsByName worked on a saved/reopened 16-object model; Tree.Find explicitly rejected batch enumeration, Tree.Filter raised a null-reference exception, and IsObjInTreeView returned false for every object. Search therefore enumerates/read-snapshots model data in the backend and applies pure COREX predicates under the contract above. Never call the rejected native filter/membership methods for this node, even in Interactive mode; both modes expose the same COREX query meanings. Search leaves Outline filters, active objects and expanded state untouched. T01 validates the selected predicates/metadata adapters and does not repeat the rejected native candidate.

### 10. FEA Table

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. |
| In | `source` / Source | Mechanical Object or Property; L | Required, nonempty. Connect Search outputs or another typed selector. |
| In | `family` / Family | Text enum; I | `auto`; Table selection. Options Auto, Model definition, Result history / summary, Spatial samples, Supported worksheet. |
| In | `table` / Table / property | Text; I | Empty = sole applicable table; if several exist, require selection; Table selection. |
| In | `component` / Component | Text; I | `all`; Table selection. Discover actual components from accepted descriptors. |
| In | `units` / Units | Text enum; I | `source`; Values and units, collapsed. Options Preserve source units / SI. |
| In | `sets` / Rows / sets | Integer list; L | Empty = all available stored sets; Values and units. For model-definition/worksheet tables, no set restriction; the control remains present but inactive. |
| Out | `tables` / Tables | Table; L | One immutable TableValue per selected source/table, in source order. |
| Out | `definitions` / Definitions | Table; I | One row per output column, keyed by table ordinal, carrying units, source, set, location and definition metadata. |

Use explicit adapters, in this order:

1. **Model definitions:** documented Mechanical `Field.Inputs`, `Field.Output` and `Variable` metadata/values. Include constant, ramp/tabular, formula-backed definitions, vector components and bolt-pretension step states. Preserve original row order, duplicate independent values, free/locked states, formulas and units. Do not fabricate an independent time column for a scalar constant; a one-row scalar table is valid.
2. **Result histories and solution summaries:** use actual API-native `Result.TabularData` / `Solution.TabularData` columns when they exist, but do not assume they expose every GUI history. `ITable` is a column mapping: enumerate Keys, retrieve by key/get_Item, and record Independents/Dependents; it is not IDataTable and has no assumed Columns/GetColumnValues API. For a configured result's Minimum/Maximum/Average history, obtain stored time/frequency sets from `analysis.GetResultsData().ListTimeFreq`, select each result set through By=ResultSet and SetNumber, evaluate that selected result, and read its summary quantities. Capture/restore By, DisplayTime, CalculateTimeHistory and SetNumber in `finally`. The sole exception is an initial `By=Time`/inactive `SetNumber=0` whose public setter rejects zero: restore the three active addressing settings exactly, retain a valid positive SetNumber, and report the inactive drift in Definitions.notes and normal diagnostics. All other drift is fatal. Native modal Frequency is a separately supported ITable column. Never call Solve, scrape the GUI, or evaluate every result in the project merely to extract one history.
3. **Spatial samples:** `Result.PlotData` is a separate table for the evaluated result set. Keep node/element identity, location, component and set information. Do not label spatial rows as a time history.
4. **Force-reaction probe:** a specifically tested native `RetrieveResult` adapter for X, Y, Z and Total, preserving scope and coordinate-system semantics. The 261 ForceReaction stubs expose By and DisplayTime but not SetNumber, and live 261 makes By read-only. Accept only probes already `By=Time` in time-driven analyses with unambiguous stored times. Never assign By; set DisplayTime, call RetrieveResult, restore DisplayTime, and verify By stayed unchanged. Reject every other addressing mode explicitly. Repeated/ambiguous times or unsupported analysis modes are explicit unsupported-adapter errors, not merged rows. Other probes/result-set addressing require a separately proved adapter; do not infer from an identical class suffix or invent ForceReaction.SetNumber.
5. **Worksheets:** initially the mesh-control worksheet (row activation and named selection) and layered-section worksheet (material, thickness, angle), using their documented row APIs. Return mixed scalar tables with stable references rendered as readable names/IDs; do not coerce those columns into floats.

Automatic evaluation is a locked default, not an automatic solver launch. Missing/unsolved results fail with a clear message identifying the required solved source. Unsupported worksheets or table kinds fail explicitly and name the unsupported source; no GUI Tabular Data pane scraping or silent empty success.

Use the existing immutable TableValue with numeric buffers wherever values are numeric. Source units remain default. Numeric column headings include readable units, for example `Time [s]`, `Force [N]`, `Displacement [mm]`; Definitions retains the original column key, label, quantity dimension and exact unit separately. SI conversion uses Ansys quantity/unit facilities for actual quantity columns, including affine temperature conversion; identifiers, states and formulas are never converted. Do not add a second scientific table type or convert all values into display strings.

Definitions columns are `table_index`, `column_index`, `column_key`, `column_label`, `unit`, `quantity_name`, `definition_kind`, `formula`, `object_path`, `property_key`, `result_set`, `location`, `coordinate_system`, and `notes`. Absent fields are null/empty according to the typed column schema, not invented defaults. A table can have several independent variables; retain them all. Formula samples returned by the API must be described as samples, distinct from the formula. Do not add a user-controlled formula resampling engine in v1.

Extraction is full fidelity up to existing scientific transport limits. No implicit decimation, row truncation, resampling, interpolation, sorting or averaging. On a limit violation fail with the exact table/size and recommend narrower source/set/component selection. Plot decimation remains owned by Signal Plot and must not change the extracted table.

### 11. Mechanical Camera Views

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. |
| In | `include` / Include | Text enum; I | `saved_and_current`; View selection. Options Saved views + current view / Saved views / Current view. |
| Out | `views` / Views | Mechanical CameraView; L | Saved order followed by one current view when requested. |
| Out | `names` / Names | Text; L | Labels in the same order as Views; current uses the reserved visible label Current view. |
| Out | `details` / Details | Table; I | One row per view with name/kind, focal point, view/up vectors, scene dimensions, length unit and source identity. |

Use `Graphics.Camera` for the current snapshot and `Graphics.ModelViewManager` for saved views. The selected enumeration route is ExportModelViews to a run-owned XML file, then standard-library parsing of direct root children tagged `ModelView` with a required `Name` attribute. Preserve each child's original enumeration index and store records as a list so duplicate names survive. Require the parsed count to agree with NumberOfViews. Apply each index and read numeric camera fields through public Camera properties rather than decoding undocumented numeric XML fields. FocalPoint supplies Location/Unit and scene dimensions are quantities. This route is supported by a public Ansys example and the 261 release guide; T01 verifies structure/index/restoration behavior, not an unspecified search for another getter. Never execute exported camera commands or silently drop unnamed/unknown view structures.

If obtaining saved camera parameters temporarily applies views, snapshot the current camera/active objects first and restore them afterward. Duplicate saved names must carry stable indices; text-only selection of an ambiguous duplicate is an error. A model with no saved views still provides the current view. An unavailable camera field is null plus an availability note; do not invent a perspective flag or camera position from incomplete vectors.

### 12. Export Mechanical Image

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; L | Required; exactly one Model per matched branch. Graft multiple Model items into separate branches before connecting. |
| In | `objects` / Objects | Mechanical Object or Text; L | Empty = current active display; Selection. Searchable list selector. |
| In | `views` / Views | Mechanical CameraView or Text; L | Empty = current camera; Selection. Searchable list selector. |
| In | `width` / Width (px) | Integer; I | 1600; Image options, collapsed; 64–8192. |
| In | `height` / Height (px) | Integer; I | 1000; Image options; 64–8192. Combined size <=33,554,432 pixels. |
| In | `background` / Background | Text enum; I | `white`; White / Model background; Image options. |
| In | `fit_view` / Fit view | Boolean; I | False; Image options. If True explicitly fit after applying the selected camera. |
| In | `folder` / Folder | Path; I | Empty = return images without user-file export; Save to disk, collapsed. |
| In | `file_name` / File name | Text; I | `{object}_{view}.png`; Save to disk. Only documented object/view/index tokens, no arbitrary expression evaluation. |
| In | `overwrite` / Overwrite | Boolean; I | False; Save to disk. |
| Out | `images` / Images | Image; T | Object-grouped image tree as specified below. |
| Out | `files` / Files | Path; L | Written files in the same flattened object-major order; empty if Folder is absent. |
| Out | `details` / Details | Table; I | Object/view identities, DataPath, image ordinal, dimensions and file path when written. |

Within each matched input branch, require exactly one Model and consume the complete Objects and Views lists. Reject multiple Model items in one branch before any capture, with guidance to use the existing Graft modifier. For incoming branch path `p`, executor invocation ordinal `j` (`ctx.target_iteration`), and object ordinal `i`, create image branch `p + (j, i)`; its items are views in selected order. The explicit invocation component prevents equal output branches merging separate parameter/model invocations. Empty optional Objects or Views denotes one current-display/current-camera choice. Explicit multiple connections merge through normal COREX data-tree admission; do not invent graft/flatten modifiers inside the node. Generic port modifiers remain available to users. Image counts and Details paths must match exactly. Enforce a maximum of 256 captures per invocation; report the requested count before doing any capture when exceeded.

Capture transaction: validate every selector and output path first; snapshot camera/active object/visibility state; activate the selected object; evaluate an existing selected result when necessary without solving; apply the final requested view; optionally Fit only when explicitly enabled; apply export settings; call the documented viewport `ExportImage`; validate/read PNG into ImageValue; restore graphics state in `finally`. The output is the graphics viewport, not the Mechanical Outline/window chrome.

Mechanical may require a temporary file to export an image. That file is run-owned and is distinct from optional user-file export. Reuse the existing image/artifact service for authored output publication. Preflight sanitized, collision-free filenames; reject tokens that escape the chosen folder, duplicate destinations and existing files when Overwrite is false. Stage all requested images before publication; do not leave a deceptively complete partial batch on failure. Use one batch manifest/Details table, not per-attempt log ledgers.

### 13. Run Mechanical Script

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. |
| In | `environments` / Environments | Mechanical Object or Text; L | Empty = all supported analyses; required only for an explicit nonempty authored selection. |
| In | `scope` / Scope | Text enum; I | `each_environment`; Each selected environment / Model once; Script. |
| In | `code` / Code | Text; I | Empty; multiline editor; required nonempty to execute. |
| In | `timeout_s` / Timeout (s) | Number; I | 600; range 1–86400; Execution options, collapsed. |
| In | `stop_on_error` / Stop on error | Boolean; I | True; Execution options. |
| Out | `model` / Model | Mechanical Model; I | New revision only after successful completion. |
| Out | `report` / Report | Table; I | Per-environment operation receipts followed by the refreshed discovery descriptors. |

Provide `ExtAPI`, `DataModel`, `Model`, `analyses` and, in per-environment mode, `analysis`. For Model once, execute exactly once and set `analysis=None`; `analyses` is the ordered selected/all-analysis collection. In per-environment mode execute once for each selected analysis in tree order. A passed object must be an analysis of this model; do not reinterpret result objects or Python runtime environments as analyses.

Use the internal Mechanical scripting engine qualified on 261: embedded `app.execute_script` or server `run_python_script`, with an IronPython-compatible authored script contract. The release change does not expand this contract to CPython-only authored features. A code editor language selector and arbitrary external Python interpreter routing are out of scope.

Set the documented context for each invocation and clean up injected variables afterward. Capture bounded stdout/result text and errors with environment identity. Code is intentionally user-authored automation and may explicitly solve/save if the user writes those commands; the built-in node must not add such operations. Explain this distinction in node help instead of pretending arbitrary scripts are read-only.

If Stop on error is false, attempt remaining selected environments, collect receipts, then fail the node if any invocation failed. Diagnostics carry the partial report; no success Model output is emitted. On timeout, cancellation or transport loss, treat state as uncertain and retire the run session. No automatic retry of mutating code.

### 14. Mechanical APDL Snippet

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. |
| In | `environments` / Environments | Mechanical Object or Text; L | Empty = all supported analyses; Command snippet. |
| In | `name` / Name | Text; I | `COREX commands`; nonempty; Command snippet. |
| In | `commands` / Commands | Text; I | Empty; required nonempty; APDL multiline editor. |
| In | `steps` / Steps | Text enum; I | `all`; All load steps / Selected load steps; Solver placement, collapsed. |
| In | `selected_steps` / Selected load steps | Integer; L | `[1]`; active only for selected mode; positive, unique, within each target analysis. |
| In | `issue_solve_command` / Issue SOLVE command | Boolean; I | False; Solver placement. |
| Out | `model` / Model | Mechanical Model; I | New revision on successful mutation. |
| Out | `snippets` / Snippets | Mechanical Object; L | Created/updated snippets in analysis, then step order. |
| Out | `report` / Report | Table; I | Per-target change receipts plus refreshed discovery descriptors. |

Use `analysis.AddCommandSnippet()`, `snippet.Input`, `StepSelectionMode`, `StepNumber`, and `IssueSolveCommand`, with release-/analysis-specific enum values established in T01. Do not label a load step as a substep. If selected steps cannot be represented by one native snippet, create one owned snippet per selected step; use deterministic names such as `COREX commands — Step 1`. All mode uses the native all-step setting, not one duplicated snippet per solver substep.

Preflight every target/step/analysis capability before modifying any tree. Only update snippets owned by this workflow node: mark generated APDL with a deterministic comment containing a neutral COREX owner token based on workflow-node ID, analysis identity and step selection. Retain the exact user command text after that marker. A same-name unowned snippet is a collision: fail with its path and ask the user to rename the new snippet; never overwrite it. Re-executing against an explicitly saved output containing this node's marker updates that owned snippet instead of appending duplicates.

For API failures after partial changes, attempt to restore the captured input/settings of updated snippets and remove only newly created owned snippets. If restoration cannot be verified, taint the session and fail. Never delete unrelated snippets. Running this node injects source; it does not solve. The toggle controls generated input, and explicit SOLVE commands within user APDL remain user-authored commands.

### 15. Save Mechanical Model

| Direction | Key / label | Type; access | Default / section / behavior |
| --- | --- | --- | --- |
| In | `model` / Model | Mechanical Model; I | Required. Must be wired after intended mutations. |
| In | `file` / File | Path; I | Required, no implicit source overwrite; Destination. |
| In | `format` / Format | Text enum; I | `auto` = infer from explicit destination extension; Destination. Choices below. |
| In | `include_results` / Include result files | Boolean; I | True; Save options, collapsed. Only active for archive formats that support it. |
| In | `include_user_files` / Include user files | Boolean; I | True; Save options. Only active for `.mechpz` and `.wbpz`. |
| In | `include_external_imported_files` / Include external imported files | Boolean; I | True; Save options. Only active for whole Workbench `.wbpz` archives. |
| In | `overwrite` / Overwrite existing | Boolean; I | False; Save options. |
| Out | `model` / Model | Mechanical Model; I | Refreshed valid Model revision after any required reconnect. |
| Out | `files` / Files | Path; L | Published primary file and required accompanying project directory/assets. |
| Out | `report` / Report | Table; I | Format, source/destination identity, inclusion policy, publication outcome, and refreshed discovery descriptors. |

Format codes are `auto`, `mechdb`, `mechdat`, `mechpz`, `wbpj`, `wbpz`. Explicit format and filename extension must agree. Standalone sources support `.mechdb`, `.mechdat`, and native `.mechpz`. Workbench sources support native `.wbpj`/`.wbpz` plus separate model-only selected exports to `.mechdb`/`.mechdat`. Reject `.mechpz` for a Workbench source with guidance to choose `.wbpz`; never silently route it through `.dsdb`, alias one source family as another, or create a fake archive.

**Standalone:** use supported standalone Project save/export/archive APIs. A `.mechdat` intentionally omits external solver files and is labeled Model export in help; `.mechpz` is the archive option. Map Include result files and Include user files to the two documented `ArchiveSettings` Boolean properties. Include external imported files is disabled for standalone formats and is not consumed. Inactive controls remain visible as ports and are not passed to inapplicable formats. Report every omission; an intentionally partial archive is never labeled complete.

**Whole Workbench project/archive:** retain the isolated Workbench project, flush/close the owned Mechanical editor with the vendor container lifecycle, native Save to a staging project destination, and Archive when requested. For `.wbpz`, map Include result files to `IncludeSkippedFiles`, Include user files to `IncludeUserFiles`, and Include external imported files to `IncludeExternalImportedFiles`. Native 261 defaults the first two to True and external imported files to False; COREX deliberately defaults all three controls to True for safer preservation while allowing a wire or local toggle to exclude them. Use `ArchivePath` and the formal `ProjectPath` Unarchive argument, plus `FailIfMissingFiles=True` for publication validation. Inclusion choices do not weaken missing-file failure. After publication reconnect/reacquire the selected model when needed and invalidate old selection snapshots.

**Workbench selected-model export:** export the selected Model container with `model.Export(FilePath=bridge_dsdb_path)` into a new run-owned `.dsdb`, open it in a **separate same-release standalone owner**, then use Project.SaveAs for `.mechdb` or `.mechdat` only. Close the conversion owner after verification and retain the Workbench project. Label outputs model-only and report omitted results, user/imported/external files and Workbench project data accurately. Archive inclusion controls are inactive and unconsumed here. Never call Project.Archive in this branch, offer `.mechpz` for a Workbench source, copy an internal database, rename a file, reattach omitted files, or investigate a result-preserving `.dsdb` archive route.

**Publication:** validate destinations and source identity before writing; capture destination-exists checks again at publish time. Create a complete staging output first. Single files publish by same-volume atomic replacement where available. `.wbpj` output is a file-plus-directory transaction: use a staging sibling directory, a bounded backup/restore transaction for explicit overwrite, and rollback on publication failure. Never report success before the primary file and required companions are complete. Do not overwrite an independently open/locked source project. Preserve staged recovery output if rollback cannot complete and report exact paths; do not auto-delete the only surviving user data.

Use distinct staging project names/directories for different conversion formats. The 261 same-stem `.mechdb`→`.mechdat` sequence encountered an own-project lock; a distinct-name `.mechdat` conversion succeeded. Preflight associated project directories/locks as well as the primary filename; do not infer that changing only the extension creates an independent save target.

A source path may be overwritten only when it is explicitly chosen as Destination and Overwrite is true. That changes the source for later runs by the user's explicit save action. Default fresh-run behavior still applies.

Workbench Save first validates ordinary native inventory, topology, archive policy, verification and restoration. Only a sole remaining working-to-stage SHA mismatch for the unique registered companion `dp0/act.dat` pair may use the closed-schema HDF5 logical comparison in [BACKEND_DECISIONS.md](BACKEND_DECISIONS.md). Every other file field stays exact, including size and associations. Byte-identical files retain ordinary byte proof; two absent entries need no HDF5 inspection, while unilateral or ambiguous membership fails. Stage-to-verification and working-to-restoration remain byte-strict. The accepted diagnostic supports observed logical equality with container-metadata drift, not a claim that only timestamp bytes changed.

### 16. Diagnostics, resource limits, and UI defaults

Use normal COREX node diagnostics, progress, cancellation and warnings; do not add flow/error ports. Stable error codes are `mechanical.missing_dependency`, `mechanical.release_unsupported`, `mechanical.open_failed`, `mechanical.system_required`, `mechanical.selector_ambiguous`, `mechanical.selector_missing`, `mechanical.stale_reference`, `mechanical.cross_session_reference`, `mechanical.table_unsupported`, `mechanical.results_missing`, `mechanical.capacity_exceeded`, `mechanical.operation_failed`, `mechanical.operation_timeout`, `mechanical.restore_failed`, `mechanical.save_failed`, and `mechanical.capability_unproved`. Messages name the operation, model/system, object/property or output path when useful; they do not dump entire source files, large tables or secrets.

The selected background Search also uses `mechanical.search_incomplete` when unavailable data prevents a complete match decision. Do not convert that failure into Found=False or an apparently complete partial object list.

Default guards: 600-second open/script timeout, 64–8192 image dimensions with a 32-megapixel ceiling, 256 image captures per invocation, existing scientific 256 MiB per-value / 512 MiB per-codec-operation limits, 1 MiB inline descriptors, 64 KiB handle metadata, and the catalogue bounds in section 5. Keep long user code/expressions out of metadata fields; emit bounded diagnostics with a private log path for full operation details. These are documented v1 limits, not silent truncation policies.

All section names/order follow the visual baseline. Open options, Search, Table selection, View selection, Selection, Script, Command snippet, and Destination are initially expanded. Session options, Match options, Values and units, Image options, Save to disk, Execution options, Solver placement and Save options are initially collapsed. Persist expansion through the existing generic node state. No per-node geometry constants, timers, custom hover exceptions, or duplicated port/editor rows.

## Execution Tasks

### 17. Execution, review, commit, and recovery protocol

Implementation is authorized and uses large-plan execution. One coordinator owns this full plan, dependencies and the single ledger. Use one fresh implementation worker per task and one fresh independent reviewer for each substantial task. Retain the implementation worker through fixes for its task, then retire it. Default to one writer in the shared checkout; parallel read-only research is permitted only for concrete independent questions. Do not create new app tasks, model tiers, a work-packet manifest set, or additional progress ledgers automatically.

Start a fresh Sol (`gpt-5.6-sol`) T01 implementation worker in the new session; reuse the existing files and retained evidence, but do not resume or address an old agent ID. Use fresh Sol workers for subsequent implementation and intermediate independent reviews, preserving the selected reasoning setting unless the user changes it. Use Astra (`gpt-6-astra`) for the final T18 independent integration review. Keep detailed implementation and verification with the task owners so the coordinator retains only compact acceptance evidence and decisions. This model routing changes none of the independent-review, acceptance, dependency or separate-commit requirements below.

T11 routing exception approved by the user: use GPT-6 Astra at xhigh only for the worker-startup/workspace-retirement fix blocking production integration. Pause the Sol writer during that bounded handoff, retain independent Sol review, then return the remaining implementation to Sol. All other task routing remains unchanged.

T14 routing exception approved by the user: use a fresh GPT-6 Astra worker at xhigh for the remaining challenging T14 implementation through completion. The Sol writer stops before write ownership transfers; retain independent Sol review. T15–T17 return to Sol implementation, and T18 still requires a fresh independent Astra integration reviewer.

Every task below must follow this exact completion sequence:

1. Re-read its full contract sections and predecessor evidence; verify `git rev-parse --show-toplevel`, current branch and dirty status. Use an implementation branch under `codex/` unless the user directs another branch. Preserve concurrent work; do not reset the repository or stage everything.
2. Assign one bounded owner/write scope. Implement only that task, updating source banners and affected agent maps when ownership changes. New helpers require a search of existing owners and `ea_node_editor/common/` first.
3. Run the smallest failing/proving check first, then the task's specified acceptance checks once. Keep full logs under the neutral task artifact directory and return a bounded summary. Do not repeat a passed task suite at every later step unless a new change touches that contract.
4. Obtain the independent review specified below against the actual task diff and its recorded baseline. Resolve actionable findings with the same implementation worker. A worker's self-review is not independent approval.
5. Update this task's ledger status and evidence. Inspect staged filenames, staged content, generated artifacts and the proposed commit message for unrelated changes and private study provenance. Stage exact paths/hunks only.
6. **Create a separate commit for this task.** The task's commit includes its implementation, tests, relevant documentation/maps and its ledger acceptance record. Never combine Txx and Tyy just to reduce the commit count. Never mark a task accepted before its required checks/review pass. Never commit a knowingly failing task as complete.
7. Record the resulting hash in the coordinator's ledger and report. The next substantive task commit may carry the previous task's exact-hash ledger update. A commit cannot contain its own hash: the final task's committed ledger row records its unique exact commit subject as the resolvable reference, and the final report supplies the actual SHA. Do not create a metadata-only commit or amend a task repeatedly to chase a self-referential hash.
8. Move to the next task only after its dependencies are accepted. Publishing/pushing is not part of the present authorization and requires a later user request. A task-specific implementation commit is required by this plan; a planning-only commit has not been requested now.

The ledger uses `NOT_STARTED`, `IN_PROGRESS`, `IN_REVIEW`, `BLOCKED`, and `ACCEPTED`. For a block, name the concrete unavailable API/environment/evidence, the task it blocks and the next action. Do not silently narrow scope to remove a block. Maintain one concise final outcome per task; no per-attempt documents or extra metadata-only commits.

**Recovery after any compaction/restart:** read all of this PLAN.md, all of TASK_LEDGER.md, current AGENTS.md, Git status/diff, the accepted task commit list and active workers. Resolve the first incomplete task and its next action. Reuse accepted evidence. Do not restart completed probes, reread the whole private corpus, or recreate already accepted tasks. If actual Git state disagrees with the ledger, reconcile exact commits/files before editing and preserve unrelated work.

### T01 — Validate the selected backend routes and background queries

- **Goal:** qualify the fixed COREX background-query contract and selected native export/camera/table routes. BACKEND_DECISIONS.md records the user's search decision, successful small conversion/camera checks and rejected native filter candidate; reuse them. This is validation of explicit designs, not an unresolved choice of backend architecture. Planning probes are not full implementation-task acceptance.
- **Preconditions:** explicit implementation authorization received; licensed accessible 2026 R1 (261) Mechanical and Workbench; project venv/package prerequisites; no user production files used as disposable fixtures. If the required 261 environment is unavailable, mark T01 blocked and identify the missing prerequisite. Release 252 is outside initial support and is not an acceptance gate.
- **Conservative write scope:** `scripts/mechanical_catalogue/probe_capabilities.py`, `scripts/mechanical_catalogue/build_probe_fixtures.py`, `tests/mechanical_catalogue/test_probe_contract.py`, neutral generated fixture recipes under `tests/fixtures/mechanical_catalogue/`, and a neutral capability evidence document under `docs/specs/perf/`. Live databases/images/logs go under `artifacts/verification_logs/mechanical_catalogue/T01/`. No production add-on/runtime/QML implementation yet.
- **Deliverables:** first reconcile the existing probe validators, fixture recipes and proof schema with the amended source-family archive scope; the retired Workbench-to-standalone result-complete archive gate must neither block nor pass T01. Complete the linked Workbench and solved Mechanical fixture coverage already specified, reusing retained evidence and the single retained 261 solve. Record source checksums, versions, exact APIs/enums, schemas and restoration. Prove native `.wbpz` and `.mechpz` separately; qualify `.dsdb` only for model-only `.mechdb`/`.mechdat` export.
- **Required probe order:** first amend existing validators, recipes and schema to the source-family matrix. Then (A) finish uncovered query cases, including a live positive imported source-ID case; never call Filter/Find/IsObjInTreeView. (B) qualify model-only `.dsdb` conversion boundaries and `.mechdb`/`.mechdat` reopening, with no archive/result-transfer gate. (C) extend the passed view check to restoration and duplicate/rename/delete cases. (D) exercise actual supported ITable, configured-result, ForceReaction and worksheet extraction from existing results without Solve. (E) cover native `.mechpz`/`.wbpz` toggles, disabled controls, missing dependencies, remaining formats, lifecycle, cleanup, source integrity, images and snippet placement. Use 261 and retained evidence; run only uncovered fixture families. The resumption prompt permits additional solves only for a concrete uncovered fixture need. One genuinely standalone modal solve was authorized because the retained solved source was Workbench-owned and could not qualify native standalone result archives. Reuse both retained solves; do not repeat them.
- **Hard acceptance gates:** verify the selected conversion round trip and requested data completeness on **2026 R1 (261)**; establish the explicit COREX query results/availability rules (not native Outline parity); verify camera parsing/index/state restoration and declared table families with no automatic solve. Pin exact working syntax/schema for later tasks. If a declared contract fails, stop before T02 and report that concrete failure. Do not convert a documented endpoint into assumed end-to-end proof, invent fallback APIs, change user scope or copy internal databases as substitute evidence.
- **Verification:** validate the probe result schema with the focused test, execute the 261 probe against the two bounded fixtures, and independently review the API evidence. Compare original source hashes before/after and reopen outputs with the vendor-supported API. For native archives, verify each requested inclusion and each intentional exclusion under the enabled flags, retained results where requested, `FailIfMissingFiles=True`, and accurate non-complete reporting for partial archives. For model-only selected Workbench exports, verify the selected tree/model boundary, geometry, loads, selections, snippets, views, source integrity, and accurate omission reporting; do not impose a result/dependency-transfer gate. Inspect generated `ds.dat` for snippet phase/step behavior without launching unnecessary additional solves. Run one heavy Ansys process cohort at a time.
- **Non-goals:** full solver benchmarking, a Cartesian matrix of every analysis type, unrelated installed-product inspection, production user models, implementing node features, accepting GUI-only behavior as a headless API.
- **Packetization notes:** P01 only; its result is the exact API contract input to T03/T05–T15. Do not merge it with implementation work.
- **Dedicated commit:** `T01 Validate Mechanical catalogue backend routes`. Independent API/evidence review required.

### T02 — Register bounded Mechanical value contracts

- **Goal:** establish model-state, object, property, camera and discovery table contracts before backend or UI adoption.
- **Preconditions:** T01 accepted; exact schema/release capability records available.
- **Conservative write scope:** new `addons/mechanical/contracts.py` and minimal package files; add-on contract registration in `addons/registry_contributions.py` / existing manifest owners only as required; focused `tests/mechanical_catalogue/test_contracts.py`. Touch runtime contract core only if a genuinely missing carrier hook is demonstrated; do not add a new scientific table codec.
- **Deliverables:** the four semantic types in section 6; exact-schema validators; stable selector encode/decode; discovery/receipt/Definitions table builders; model metadata catalogue locator; object/property/camera identity rules; field-presence/nullable policies; explicit source-unit labels; immutable snapshot construction. Validators remain usable without Ansys/CLR packages.
- **Verification:** malformed fields/schema/type/size, non-finite camera values, invalid paths/revisions, duplicate/ambiguous selector identities, wrong model/system, same-name objects, free DOF/null preservation, scientific table round trip, and reference metadata bounds. Run `tests/test_typed_runtime_values.py`, `tests/test_scientific_worker_transport.py` and the focused new contracts module when the relevant hooks are changed.
- **Non-goals:** live sessions, a second TableValue, automatic neutral-scene conversion, dynamic imports selected by payload text, large catalogue data inside handles.
- **Packetization notes:** P02; consumed by every later node. Keep transient model/object types durable-ineligible.
- **Dedicated commit:** `T02 Add Mechanical runtime value contracts`. Independent boundary review required.

### T03 — Add fresh-run session ownership and process isolation

- **Goal:** own Mechanical/Workbench resources within the existing run lifecycle and make stale or cross-session use impossible.
- **Preconditions:** T01–T02 accepted.
- **Conservative write scope:** `addons/mechanical/session.py`, `owner_process.py`, `backend.py`, minimal `workbench.py` transport ownership, and narrow lifecycle hooks in `execution/worker_services.py` / `nodes/execution_context.py`; `tests/mechanical_catalogue/test_session_lifecycle.py`, `test_owner_protocol.py` and directly affected existing handle tests.
- **Deliverables:** dedicated owner process/thread; private bounded data-only request protocol with request IDs/timeouts/cancellation; workspace-identified run-owned session map; immutable revision wrappers; serialized operation guard; owned-process shutdown; source/work-directory separation; explicit cleanup independent of outstanding observational handle leases; no cross-run model reuse. Successful Interactive instances may remain inspection-only until the next graph-run start in their workspace or workspace/application shutdown; Background and every failed/cancelled run always close. Use the existing codec for scientific values and existing handle registry for admission, not pickle of arbitrary live objects.
- **Verification:** two dependencies share one run session; two Open nodes do not; second run starts from source; expired/wrong-run handles fail; partial launch cleanup; cancel/timeout/transport crash; only owned PIDs close; background success and every failure/cancellation release the backend; retained solution-output leases do not keep background Ansys alive. Prove that any next run in workspace A retires all A-owned retained Interactive instances even if it omits Open, then reopens fresh where applicable; a run in workspace B leaves A's retained windows alone; workspace close/application shutdown retires the applicable retained instances; no active global pool or ownership keyed only by Open exists. Run focused new tests plus `tests/test_execution_handle_registry.py`, `tests/test_handle_registry_leases.py`, and the exact changed runtime cleanup tests.
- **Non-goals:** a global pool, reconnecting to arbitrary user sessions, parallel API calls on one model, a general-purpose RPC framework, persistent unsaved state between graph runs.
- **Packetization notes:** P03; do not expose Open until this lifecycle is accepted.
- **Dedicated commit:** `T03 Own Mechanical sessions within execution runs`. Independent lifecycle/error-path review required.

### T04 — Share accepted-metadata selectors between canvas and inspector

- **Goal:** support Mechanical autocomplete through the existing shared controls without backend calls during UI editing.
- **Preconditions:** T02 accepted; T03 available for runtime metadata test doubles. This task uses synthetic accepted snapshots, so it does not need live Mechanical.
- **Conservative write scope:** `addons/property_edit_adapters.py`, `addons/mechanical/property_edit.py`, `ui_qml/graph_scene_payload/factory.py`, `ui_qml/graph_scene_bridge.py`, existing Signal Plot metadata owner and focused selector tests; QML changes only in shared controls when an actual contract gap is proved.
- **Deliverables:** one shared registered enrichment/refresh path used by both Signal Plot and Mechanical; full catalogue locator resolution; cached detached descriptor indexes; exact/prefix/substring filtering; typed codes separate from labels; empty/partial/stale metadata states; preserved editor drafts and read-only wired values; empty catalogue does not trigger backend discovery.
- **Verification:** instrument every model API/file-loader/script callback to fail if invoked during a keystroke/projection; assert no calls. Check duplicate labels, Unicode/case, unknown authored paths, 50-option popup limit, incomplete catalogue notice, multiple models emitted by one Open node, catalogue rev replacement, upstream Model routed through Panel/Select, deferred focused-editor refresh, keyboard navigation and Inspector/canvas parity. Run `tests/qml_quick/tst_signal_selectors.qml` through the repo's existing focused QML route and the relevant Python selector/inspector tests.
- **Non-goals:** Mechanical-specific QML, a new combo widget, a generic app-wide search service, source I/O to fill selectors, dropping existing Signal Plot behavior.
- **Packetization notes:** P04; shared UI adoption is kept separate from node backend work.
- **Dedicated commit:** `T04 Share metadata-driven node selectors`. Independent shared-UI review required.

### T05 — Implement Open Mechanical Model and discovery

- **Goal:** open supported standalone and Workbench sources with the fresh-run lifecycle and publish the first Model/Info outputs.
- **Preconditions:** T01–T04 accepted; supported copy/open/unarchive/system-selection APIs fixed by T01.
- **Conservative write scope:** `addons/mechanical/catalog.py`, `function_nodes.py`, `runtime.py`, `inspection.py`, `workbench.py`, add-on discovery/install declarations, relevant `pyproject.toml` optional dependency groups, and `tests/mechanical_catalogue/test_open_model.py` / `test_catalogue.py`. Update the exact repo-owned node catalog fixture and owning maps as this declaration becomes available.
- **Deliverables:** the complete section 8 node contract; file-aware Background/Interactive launch; release discovery/Auto selection; a working project per run; source and dependencies unchanged; system selector keyed by stable identity; shared Model-cell deduplication; bounded complete/partial Info schema; dependency-gated add-on availability without startup imports of Ansys.
- **Verification:** each accepted input format, each launch mode on the two 261 fixtures, single/multiple/shared Workbench model choices, missing file/package/release/license, rejection of explicit releases below 261, source hash unchanged, invalid working folder, two source items from one Open node, and fresh input after a previous mutating run. Verify the actual production registration rather than only a declaration fixture. Run the focused node tests and `tests/test_addon_catalog.py` / `tests/test_addon_registry_contributions.py` for changed registration seams.
- **Non-goals:** importing CDB/RST as an authored Mechanical project, opening a GUI inside the graph card, silent source saves, user installation of a missing Ansys release.
- **Packetization notes:** P05; only implemented declarations are added to the bundle. Do not publish fake successful placeholders for remaining nodes.
- **Dedicated commit:** `T05 Add Mechanical model opening and discovery`. Independent backend/registration review required.

### T06 — Implement complete outline and property search

- **Goal:** implement all eleven COREX background data-query categories in section 9, with explicit differences from native Outline filtering and readable property labels/values.
- **Preconditions:** T05 accepted and T01's selected query metadata/predicate contracts validated.
- **Conservative write scope:** `addons/mechanical/inspection.py`, `function_nodes.py`, `property_edit.py`, and `tests/mechanical_catalogue/test_search_tree.py`; exact node catalog fixture/maps.
- **Deliverables:** model-data snapshot/relation adapters, pure predicates, per-mode suggestions/contextual difference labels, Name multi-term behavior, explicit current-state/scoping/visibility/provenance matching, scalar/formula/enum metadata, `has_tabular_data`, typed snapshots/Details, true complete no-match Found=False and search_incomplete on required unreadable data. No native Outline mutation or table-cell reading.
- **Verification:** all eleven declared categories with positive/negative/not-applicable/unavailable cases; missing CS is not Global; opaque source IDs are not guessed cell labels; body flags do not pull in loads; shared environment membership is not ancestor-only; partial/lost scoping is explicitly unsupported; current scope roles/counts preserved; No explicit scope positively matches confirmed absence and its inversion excludes it, while empty explicit scope remains distinct and failed getters fail; duplicate labels; visible enum aliases; inversion never matches unknown; presence detection never reads cells; cancellation/stale references. Pin Exact whole-query behavior, casefold/case-sensitive behavior, Name + Contains Unicode-whitespace AND terms in any order, Name quotes as literal text, empty/whitespace-only unrestricted behavior, and Property Value `Comment = "Load = 100 N"` plus literal quotes via `Comment = "Bolt \"A\""`; reject an empty caption when the pair delimiter is present and malformed JSON-style quoted operands, make an explicitly empty pair value match only an available empty display in both Match modes, preserve bare interior whitespace/backslashes/apostrophes, and prove only the first outside `=` delimits. Prove typed picker identities bypass the text grammar unchanged. Instrument native Filter/Find/IsObjInTreeView and table-cell APIs to fail if called. Compare with the COREX contract, not native UI counts for deliberately differing modes.
- **Non-goals:** exact native Outline parity, inherited/implicit-association inference, historical lost-scoping reconstruction, cell/full-table search, formula execution, regex or UI-state changes.
- **Packetization notes:** P06; independent read path, required by later source selectors.
- **Dedicated commit:** `T06 Add Mechanical tree and property search`. Independent semantic review required.

### T07 — Extract model-definition tables into COREX values

- **Goal:** establish FEA Table's shared extraction/metadata/output behavior using model definitions first.
- **Preconditions:** T06 accepted; table contract from T02 and Field/Variable probe evidence from T01.
- **Conservative write scope:** `addons/mechanical/tables.py`, `function_nodes.py`, `property_edit.py`, and `tests/mechanical_catalogue/test_definition_tables.py`; node catalog fixture/maps and a direct Signal Plot integration fixture.
- **Deliverables:** section 10 port/control declaration and definition adapter; component selection; constant/tabular/formula/vector/bolt-pretension states; exact full-fidelity immutable tables; unit-bearing headings and Definitions metadata; source/SI unit policy; capacity errors; direct plot compatibility.
- **Verification:** scalar constant without invented time; multiple independent variables; duplicate rows/times preserved; nonuniform times; vector components; formulas versus API samples; free/locked states; numeric units and affine temperature conversion; missing component; mixed text state columns; table limit rejection; direct TableValue→Signal Plot integration with unchanged source data. Run the new focused module and relevant existing scientific/Signal Plot tests once.
- **Non-goals:** formula resampling controls, result histories, GUI table copying, converting identifiers to floats, silent decimation or a second numerical table carrier.
- **Packetization notes:** P07; node family reports only its currently supported adapters until T08 completes. Do not label the whole catalogue release accepted here.
- **Dedicated commit:** `T07 Extract Mechanical definition tables`. Independent data/units review required.

### T08 — Add result, probe, and worksheet adapters

- **Goal:** complete the first-release FEA Table families selected by the user.
- **Preconditions:** T07 accepted and T01 native ITable/PlotData/probe/worksheet evidence available.
- **Conservative write scope:** `addons/mechanical/tables.py` and a small family module only if needed for readability; focused `tests/mechanical_catalogue/test_result_tables.py`, `test_worksheet_tables.py`; minimal declaration/metadata refinements.
- **Deliverables:** actual API-native ITable columns (including supported modal Frequency), configured-result Minimum/Maximum/Average histories from explicit stored-set evaluation, separate PlotData spatial samples, a time-driven native ForceReaction adapter with ambiguous-time rejection, mesh-control/layered-section worksheets, selected-result evaluation from existing solved data, and state restoration. Do not assume every GUI history exists under TabularData or ForceReaction has SetNumber. If T01 proved a required DPF adapter, implement only that family with its equivalence test; otherwise add no DPF execution dependency.
- **Verification:** selected/all stored sets; history versus spatial row identity; correct scope/coordinate system/components/units; no Solve call; missing/stale solved data; result evaluation restoration after success/error/cancel; probe totals and coordinate frame; textual worksheet columns; row counts/column order; adapter rejection for unsupported probes/worksheets; full table output to Signal Plot. Enforce the approved section 10 boundaries: ForceReaction must already be By=Time, never assign By, restore DisplayTime and reject other modes; only the initial By=Time/SetNumber=0 case with native zero rejection may retain and report a valid changed SetNumber after exact By/DisplayTime/CalculateTimeHistory restoration, while every other restoration failure remains fatal. Do not compare a DPF sum to a Mechanical probe without matching its complete reduction semantics.
- **Non-goals:** a generic adapter for every ACT extension table, GUI scraping, automatically solving or remeshing, extending solver capabilities.
- **Packetization notes:** P08; keep separate from T07 because result evaluation has different state/restoration and numerical evidence.
- **Dedicated commit:** `T08 Extract Mechanical result and worksheet tables`. Independent numerical/state-restoration review required.

### T09 — Extract named and current camera views

- **Goal:** implement section 11 with data-only, Panel-readable camera outputs.
- **Preconditions:** T05/T06 accepted; T01 view enumeration/schema proof accepted.
- **Conservative write scope:** `addons/mechanical/graphics.py`, camera declaration/selector metadata, and `tests/mechanical_catalogue/test_camera_views.py`; catalog fixture/maps.
- **Deliverables:** saved/current/all selection, direct ModelView XML Name/original-index parser, NumberOfViews count validation, apply-index/public-Camera snapshots, Details table, duplicate-name resolution, original-camera restoration. Do not implement a speculative view getter or numeric XML field decoder.
- **Verification:** no saved views; two named views; Unicode/comma/duplicate names; stable name/index mapping; current view units/vectors/scene dimensions; unsupported/malformed exported schema; restore after enumeration failure; Panel displays meaningful values instead of an object repr; stale/cross-session snapshots reject.
- **Non-goals:** exporting Python camera commands, inventing a `GetViewNames` API, changing view definitions, a new 3D viewer, DPF camera reconstruction.
- **Packetization notes:** P09; interface precedes image batching.
- **Dedicated commit:** `T09 Add Mechanical camera view extraction`. Independent schema/restoration review required.

### T10 — Capture images and deterministic object/view batches

- **Goal:** implement section 12 including images as values and optional safe file export.
- **Preconditions:** T08–T09 accepted for result evaluation and camera semantics.
- **Conservative write scope:** `addons/mechanical/graphics.py`, relevant declaration/selector metadata, existing artifact helpers only where a reusable gap is proven, and `tests/mechanical_catalogue/test_image_export.py`.
- **Deliverables:** validated object/view selectors; object-major Cartesian captures; exact DataTree path mapping; explicit fit/background/size settings; full graphics restore; validated ImageValue output; staged optional PNG publication and matching Files/Details.
- **Verification:** one object/current view, two×three=6 captures, input branches preserved, rejection of two Model items in one branch before capture, distinct output paths for grafted multi-model branches and separate invocation ordinals, names containing commas as real list items, named view not overwritten by Fit=False, result object activated before final view, missing/ambiguous selectors preflight before any export, pixel/count limits, path escape/name collisions, overwrite policy, batch failure cleanup/rollback and restore failure. Inspect actual images from 261 rather than only checking file existence. Connect image output to Media Panel and file output to Path tools.
- **Non-goals:** screenshots of Outline/application chrome, animation/video export, hidden Cartesian product from generic item matching, implicit file writes when Folder is empty.
- **Packetization notes:** P10; no separate image-library dependency.
- **Dedicated commit:** `T10 Add Mechanical viewport image batches`. Independent graphics/dataflow/file-publication review required.

### T11 — Run Mechanical scripts with explicit analysis scope

- **Goal:** implement the immediate user-code node and model revision behavior in section 13.
- **Preconditions:** T03–T06 accepted; fresh-run model/session and discovery paths stable.
- **Conservative write scope:** `addons/mechanical/commands.py`, `function_nodes.py`, model revision service functions and `tests/mechanical_catalogue/test_scripts.py`; narrow runtime invalidation integration only when needed to mark obsolete observations stale.
- **Deliverables:** per-environment and model-once execution; explicit injected context; IronPython-compatible engine route; bounded stdout/receipt reports; Stop on error behavior; no implicit solve/save; revision advancement/inspection invalidation after any attempted mutation; stale sibling Model error and refreshed Report catalogue.
- **Verification:** two analyses cause exactly two executions; Model once causes one; typed and text selection; scripts operate on correct analysis; default code not executed during edits/suggestions; failure in first/second environment; continue-and-report mode still fails overall; timeout/cancel prevents auto retry; original file remains unchanged; mutation→table→Signal Plot recomputes; two sibling mutators cannot both consume one revision; fresh next run returns to original source.
- **Non-goals:** CPython version selector, arbitrary external interpreter selection, silent error swallowing, transactional guarantees for arbitrary user Python, automatic re-execution after uncertain transport failure.
- **Packetization notes:** P11; retain implementation worker through the mutation/invalidation review.
- **Dedicated commit:** `T11 Add scoped Mechanical script execution`. Independent mutation/runtime review required.

### T12 — Inject node-owned APDL snippets by load step

- **Goal:** implement section 14 with clear ownership and load-step semantics.
- **Preconditions:** T11 accepted; T01 exact per-analysis snippet settings/phase evidence available.
- **Conservative write scope:** `addons/mechanical/commands.py`, snippet declaration/metadata, and `tests/mechanical_catalogue/test_snippets.py`.
- **Deliverables:** all/selected analysis scoping; all/selected load steps; one snippet per selected step where necessary; Issue SOLVE setting; deterministic neutral ownership marker; safe owned update; unowned collision errors; preflight and bounded rollback; model revision/Report/Snippets outputs.
- **Verification:** two analyses; all steps; selected `[1,3]`; out-of-range step preflight; unsupported analysis phase; owner marker match/mismatch; same-name unowned snippet unchanged; rerun from saved output updates owned snippets; exact user APDL body preserved; restoration on partial failure; generated `ds.dat` placement and IssueSolveCommand behavior. No solver launch merely to prove injection; use the T01 fixture's supported generation route.
- **Non-goals:** individual solver substep injection, a Solve node, deleting existing command objects, replacing arbitrary same-name snippets.
- **Packetization notes:** P12; separate from arbitrary Python because ownership/idempotency can be guaranteed here.
- **Dedicated commit:** `T12 Add load-step Mechanical command snippets`. Independent solver-placement/data-loss review required.

### T13 — Save standalone Mechanical outputs explicitly

- **Goal:** implement Save's standalone branch and reusable publication transaction.
- **Preconditions:** T11–T12 accepted; T01 standalone formats/archive semantics proved.
- **Conservative write scope:** `addons/mechanical/saving.py`, save declaration/metadata, narrow reuse of existing path/publication helpers, and `tests/mechanical_catalogue/test_standalone_save.py`; catalog fixture/maps.
- **Deliverables:** required destination, format/extension validation, `.mechdb` / `.mechdat` / `.mechpz`, typed result/user-file archive controls, preservation of files requested by enabled archive controls, overwrite false by default, staged output, rollback/recovery reporting, Files/Report/refreshed Model outputs.
- **Verification:** each supported format reopens; command changes survive; result and user-file inclusion/exclusion is honored for `.mechpz`; the external-imported-file control remains present but disabled and unconsumed; source hash unchanged unless explicitly targeted; explicit overwrite succeeds only after complete staging; failure does not destroy existing destination; extension conflict; locked destination; disk-full/injected write failure; source overwrite updates next-run source only by explicit choice.
- **Non-goals:** hidden autosave, calling standalone Project APIs on Workbench-backed models, pretending `.mechdat` includes solver files, cross-family conversion.
- **Packetization notes:** P13; Save declaration may expose only accepted backend formats until T14–T15 finish.
- **Dedicated commit:** `T13 Add explicit standalone Mechanical saving`. Independent publication/data-loss review required.

### T14 — Save whole Workbench projects and archives

- **Goal:** implement the native Workbench save/archive branch without severing project ownership.
- **Preconditions:** T13 accepted and T01 exact native Workbench lifecycle/archive keyword contract proved.
- **Conservative write scope:** `addons/mechanical/workbench.py`, `saving.py`, save metadata and `tests/mechanical_catalogue/test_workbench_save.py`.
- **Deliverables:** flush/close only the owned Mechanical editor; native Save/Archive; separate typed result, user-file and external-imported-file controls with safe True defaults; project file-plus-directory staging/publication; rollback; reconnect/reacquire selected/shared Model; new revision and refreshed catalogue.
- **Verification:** linked multi-system fixture; shared Model remains shared; with all three toggles enabled, registered external geometry/import data, user files and retained result files are present after independent reopen; each exclusion is honored separately; missing external dependency still fails with `FailIfMissingFiles=True`; destination `.wbpj` plus companions consistent; archive reopens without original external location; save failure/rollback; changed generation rejects old references; original source project and all unrelated systems stay unchanged in isolated runs.
- **Non-goals:** reimporting an archive as a substitute for Unarchive, dropping design-point/system structure, using `download_project_archive()` without explicit dependency inclusion, implicit save of the user's source before staging.
- **Packetization notes:** P14; independent from selected-model export because the preservation contracts differ.
- **Dedicated commit:** `T14 Preserve Workbench projects during explicit save`. Independent Workbench lifecycle/publication review required.

### T15 — Export a selected Workbench model to standalone

- **Goal:** deliver the required model-only selected Workbench export through native `.dsdb` export and separate standalone conversion.
- **Preconditions:** T01 model-only export route accepted for 261; T14 accepted.
- **Conservative write scope:** the proved export adapter in `addons/mechanical/saving.py` / `workbench.py`, format metadata, and `tests/mechanical_catalogue/test_workbench_model_export.py`. No undocumented GUI automation or internal-file extraction helper.
- **Deliverables:** native selected Model-container `.dsdb` export; separate same-release standalone conversion owner; verified `.mechdb` and `.mechdat` SaveAs outputs; accurate model-only omission report; safe publication; original Workbench project retained; refreshed wrapper after lifecycle transitions.
- **Verification:** select each of two distinct Mechanical models and reopen both model-only formats; confirm correct selected-model geometry/tree/loads/snippets and accurate omissions; confirm Workbench topology/shared links/design-point data are not rewritten; verify source hashes and rollback. Reject `.mechpz` with guidance to choose native `.wbpz`. Use retained T01 fixtures on 261.
- **Non-goals:** archive creation, result/dependency/user-file preservation, invented APIs, unsupported `.dsdb` extensions, exporting every system, or reconstructing a Workbench project.
- **Packetization notes:** P15 only. Any inability to honor the proved contract requires user-visible scope reconsideration, not an internal workaround.
- **Dedicated commit:** `T15 Export selected Workbench models to standalone`. Independent compatibility and project-preservation review required.

### T16 — Finalize shared controls, all ports, and eight icons

- **Goal:** achieve the approved visual baseline through shared production QML and final node metadata.
- **Preconditions:** T05–T15 accepted; all final controls/types/capabilities available.
- **Conservative write scope:** `addons/mechanical/function_nodes.py`, `property_edit.py`, `assets/node_title_icons/mechanical/`, `nodes/builtins/icon_catalog.py`, focused shared geometry/metadata files only if a real generic defect remains, and `tests/mechanical_catalogue/test_controls.py` / `test_visuals.py` plus existing icon/QML tests.
- **Deliverables:** each control row has exactly one exposed typed port, shared local-default/connected override behavior, keyboard/multiline/list/dropdown interaction, correct enabled conditions, all group headers/aggregate ports, persisted expansion, eight professional COREX-owned SVG icons, tooltips describing fresh-run/solve/table/save behavior. Promote icon motifs from the plan references into theme-aware production assets using the existing icon source pipeline.
- **Verification:** inventory asserts a port for every control, including the three Save archive inclusion toggles; production-path physical clicks expand/collapse every section and preserve wire identity; two connections to a collapsed group reappear at distinct anchors; control editor input does not drag the node; wired values disable local edits; autocomplete has no backend calls; disabled/inapplicable archive, step and system controls keep their ports and are not consumed; actual QML renders for all eight nodes at graph fonts 10 and 16, light/dark themes, and 100/150% display scale where available; compare with saved references for order, grouping, port presence and icon identity. Icons must remain readable at 16/24/32 pixels. Run focused icon tests and the practical graph-surface gate documented below.
- **Non-goals:** per-node geometry patches, custom Mechanical widgets, a different node theme, copying vendor icons, treating mocked SVG sheets as proof of real QML interactions.
- **Packetization notes:** P16; if the implementation requires a material port/control layout change, show the revised render to the user before acceptance.
- **Dedicated commit:** `T16 Finalize Mechanical node controls and icons`. Fresh independent visual/shared-control review required.

### T17 — Add runnable examples and complete user/developer documentation

- **Goal:** make the full catalogue discoverable and usable through concrete workflows and clear contracts.
- **Preconditions:** T16 accepted.
- **Conservative write scope:** neutral example `.cxproj` generation/fixtures under `examples/` / `scripts/mechanical_catalogue/`, `docs/MECHANICAL_CATALOGUE.md`, relevant requirement/traceability entries, owning agent maps/COVERAGE, generated route index when citations change, and documentation/contract tests.
- **Deliverables:** three original workflows: (1) Open→Search→FEA Table→Signal Plot; (2) Open→Camera Views→Select/Export Image→Media Panel with two×three batch; (3) Open→Script→Snippet→Save with fresh-run behavior. Use source file inputs as configurable paths, not committed personal paths. Document installation/release matrix, typed connection examples, all eleven filters, tabular-presence versus extraction, units, supported table adapters, result evaluation versus solve, explicit Save formats, ownership/ordering, capacity/cancellation errors and unsupported APIs. Link actual final proof locations from the spec index.
- **Verification:** reopen each example through normal `.cxproj` loading; execute with the two original live fixtures in the integration gate, not another independent solve campaign; validate graph connections without Ansys installed; docs link/traceability/map checks; assert advertised node IDs/types/ports exactly match registry. No hard-coded machine secrets, personal file paths or private study identifiers.
- **Non-goals:** a comparison document, an additional general Ansys node family, a Solve node, remote sessions, republishing proprietary examples, adding unused compatibility bridges.
- **Packetization notes:** P17; real examples/help are substantive deliverables, not a ledger-only closeout.
- **Dedicated commit:** `T17 Document Mechanical workflows and examples`. Independent handoff/documentation review required.

### T18 — Integrate, verify 2026 R1, and publish the QA record

- **Goal:** accept the complete catalogue against the locked scope and produce one durable QA result.
- **Preconditions:** T01–T17 accepted as separate commits, with no unresolved required capability or visual-review gate.
- **Conservative write scope:** final neutral QA matrix `docs/specs/perf/MECHANICAL_CATALOGUE_QA_MATRIX.md`, spec-index proof link, final necessary integration test/manifest fixes, and this ledger. Fixes belong to their real owner and must receive focused rechecks; do not hide broad feature changes in a documentation-only diff.
- **Deliverables:** exact product/package/runtime versions; all required input/output formats including cross-export; one evidence row per requirement/test scenario; end-to-end fresh-run/mutation/table/image/save proof; accepted visual comparisons; process cleanup/resource observations; final task commit references; honest failure/block status if anything fails. Do not describe implementation as accepted when only code is complete.
- **Verification:** run the owning Mechanical suite once; execute the three workflows against release 261 using retained fixtures; verify no leaked owned background process, no source mutation, required complete project dependencies and data/units consistency; run `scripts/run_verification.py --mode fast --summarize-output` once for the shared runtime/metadata/catalog integration; docs/traceability/map/icon checks as relevant. Use a single small interactive opening/capture check on 261, not a full Cartesian process matrix. Broad `full` or packaging builds are not required unless changes genuinely reach shell-wide composition or the user requests release packaging.
- **Non-goals:** presenting model-only cross-export as an archive or dependency-preserving output, replacing failed primary evidence with unrelated passing tests, exhaustive fresh-process stress matrices, automatic commit squashing/pushing, declaring newer untested Ansys releases fully certified.
- **Packetization notes:** P18; one fresh integration reviewer validates actual commits/diffs and final evidence. A substantive final QA report belongs in this task commit; avoid a separate metadata-only commit.
- **Dedicated commit:** `T18 Verify the complete Mechanical catalogue`. Independent integration review required before acceptance.

## Work Packet Conversion Map

No external packet set is requested now. If the user later requests packetization, use the exact task boundaries below; do not generate packet manifests merely to execute this plan.

| Packet | Task | Dependencies | Acceptance boundary |
| --- | --- | --- | --- |
| P00 | Bootstrap only | Implementation authorization | Read full plan/ledger/AGENTS and verify working root; no separate metadata-only task commit. |
| P01 | T01 | P00 | Exact 261 API evidence; blocking gate. |
| P02 | T02 | T01 | Data contracts and registry boundary. |
| P03 | T03 | T01–T02 | Fresh-run resource ownership. |
| P04 | T04 | T02–T03 | Shared metadata controls. |
| P05 | T05 | T01–T04 | Real Open node and discovery. |
| P06 | T06 | T05 | Eleven-mode search. |
| P07 | T07 | T06 | Definition tables and numerical transport. |
| P08 | T08 | T07 | Results/probes/worksheets. |
| P09 | T09 | T05–T06 | Camera identity and restoration. |
| P10 | T10 | T08–T09 | Image batch/value/publication. |
| P11 | T11 | T03–T06 | Script mutation scope. |
| P12 | T12 | T11 | Owned load-step snippets. |
| P13 | T13 | T11–T12 | Standalone publication. |
| P14 | T14 | T13 | Workbench preservation. |
| P15 | T15 | T01, T14 | Required standalone export from Workbench. |
| P16 | T16 | T05–T15 | Final UI/icon/port parity. |
| P17 | T17 | T16 | Runnable examples and docs. |
| P18 | T18 | T01–T17 | Complete integration and final QA. |

No two tasks are merged into one commit, even if a worker handles closely related review fixes. The serial order above is the default. A coordinator may investigate disjoint future tasks read-only while a worker implements the current task, but must not start a writer that depends on unaccepted interfaces.

## Test Plan

### 18. Test layers and commands

All commands below use the project venv. Newly named test/probe files are **planned deliverables**, not claims that they already exist.

1. Pure contracts, selectors, data-tree mapping, state guards and publication transactions run without Ansys installed. Use existing pytest/unittest infrastructure; no new test framework.
2. Owner-protocol/lifecycle tests use a deterministic fake subprocess for normal failure/cancellation cases. At least one focused real COREX process-worker test proves handle/scientific/image transport and terminal cleanup; mocks alone are insufficient.
3. Live compatibility evidence uses 261 and one heavy process cohort at a time with the two retained original fixture recipes. Record product/package versions and fixture fingerprints. Reuse generated fixtures and accepted data; avoid repeated small solves at each task when the saved result suffices.
4. UI tests use the actual registered node, GraphSceneBridge, production command/state facade and shared QML. Physical window-coordinate clicks, real connected defaults and layout animation settlement are required for expansion/port checks.
5. Integration checks cover full graph execution, fresh next run, stale references, source integrity and explicit save publication. A passing Python helper does not prove its production registration/bridge route.

Typical focused command after a task's new module exists:

```powershell
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_contracts.py -q
```

Task-specific modules replace `test_contracts.py` as described in T01–T18; do not run the whole suite at every task. The final Mechanical suite is:

```powershell
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue -q
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output
```

For the final shared graph-surface adoption gate, when practical:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m unittest tests.test_graph_surface_input_contract tests.test_graph_surface_input_inline tests.test_passive_graph_surface_host tests.test_passive_image_nodes -v
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Use `try/finally` or an equivalent isolated process when scripting environment cleanup so a failed check cannot leave QT_QPA_PLATFORM changed. Offscreen renders are regression evidence; retain at least one display-attached production interaction/capture cohort for final visual acceptance.

After changing documentation/spec registration/ownership references:

```powershell
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
```

Regenerate `scripts/generate_agent_route_index.py` when agent-map citations change, then recheck maps. The link checker normally targets canonical docs; explicitly audit this plan package's Markdown files with its existing `audit_markdown_file` function as part of planning/closeout, too.

### 19. Mandatory end-to-end scenarios

| Scenario | Required result |
| --- | --- |
| Two consecutive graph runs with a script adding 100 N | Each starts from the saved source, so changes do not accumulate across unsaved runs. |
| Interactive retention across workspaces | Any next run in workspace A retires all A-owned retained inspection windows before execution, even without Open; a run in workspace B does not close A's windows; workspace/application shutdown closes the applicable retained owners. |
| Same source in two Open nodes | Independent working models; changing one does not alter the other. |
| Open→Script→FEA Table→Signal Plot | Post-script values are extracted/plotted in the same run; previous result records cannot be reused. |
| Two sibling mutators from one Model revision | One revision cannot be consumed by both; ambiguous/stale operation fails, requiring explicit chaining. |
| Read selector from an older run/model/system | Reject before any backend dereference; no silent rebind to a same-name object. |
| Search Property Value for a visible enum / quantity / formula | Match displayed text/metadata, preserving property identity and units. |
| Search Property Value for Tabular data | Return matching objects/properties and `has_tabular_data`; no table-cell API access. |
| Search plain-text grammar | Exact is whole-query; Name + Contains ANDs Unicode-whitespace terms; the optional Property Value name/value pair accepts JSON-style quoted operands and only the first outside `=` delimits. Malformed syntax fails and typed identity codes bypass text parsing. |
| No search matches | Found=False, empty outputs, no fallback to all tree objects. |
| Background category differences | Explicit CS is not inferred Global; imported source IDs remain opaque; Graphics matches body flags only; Scoping reports current scope and rejects historical Partial detection. |
| Required search metadata unreadable | search_incomplete failure; inversion does not turn unknown into a positive match. |
| FEA Table model curve→Signal Plot | Numeric columns usable directly; units/row order retained; plot reduction does not mutate source data. |
| FEA Table history versus PlotData | Histories use stored result sets; spatial samples retain location/entity identity. |
| FEA Table existing solved result needs evaluation | Evaluate selected result only; do not start Solve or change its persistent display settings. |
| Two objects × three named views | Six images grouped into two branches, in deterministic object/view order. |
| Export image with Fit=False | Preserve the requested named camera; no unconditional SetFit. |
| Script per two environments / Model once | Exactly two executions / exactly one execution, with correct provided context. |
| Snippet all steps / selected 1 and 3 | Correct native step placement and owned snippets; Issue SOLVE does not solve immediately. |
| Save Workbench archive with external geometry and retained result | With all three inclusion toggles enabled, reopen independently of the original paths with required structure/dependencies intact; verify each explicit exclusion separately. |
| Export selected Workbench model to standalone | Supported route on 261; selected model reopens; other Workbench systems remain intact. |
| Save failure after staging with existing destination | Destination survives or verified rollback/recovery paths are reported; no false success. |
| Collapsed section with two connected inputs | One group marker, two preserved wire identities; expansion restores separate ports/editors. |
| Every declared editable control | Exactly one exposed typed input port, including inactive and advanced controls. |
| Typing into any selector | Zero Mechanical/Workbench/source-loader/script calls; only accepted metadata is consulted. |
| Cancel/crash/terminal run cleanup with retained output leases | No owned background Ansys process leaks; stale observational handles cannot reopen a session. |

### 20. Acceptance and limitations

The catalogue is accepted only when T01–T18 are accepted, every task has its separate commit, the complete API/format scope works on 2026 R1 (261), required visual interactions pass, and the QA record identifies evidence rather than merely listing intended tests. If implementation is finished but a release/environment/API acceptance gate fails, use `IMPLEMENTATION COMPLETE — ACCEPTANCE BLOCKED/FAILED` and name the gate; do not call the feature complete.

The plan does not certify future product releases, arbitrary ACT extensions, every probe/worksheet in Mechanical, an untested DPF equivalent, or a source file's numerical engineering validity. It does require the exact adapter families, filters, formats, ports and UI behavior listed here. New adapter families can be added later as explicit tasks without changing existing value/metadata semantics.

## Assumptions

### 21. Explicit implementation defaults

- Windows is the first supported host. The catalogue is local; remote Mechanical/Workbench services are outside v1.
- The user supplies/licenses Ansys. Implementation verification on disposable fixtures and available licensed 261 installations is authorized; connecting to a user-owned live session is outside scope. The initial planning phase performed no installation or license acquisition.
- Backend choices are fixed: source-family native archives (`.mechpz` standalone, `.wbpz` Workbench), model-only selected Workbench export through `.dsdb` to `.mechdb`/`.mechdat`, exported view names/indices, explicit table dispatch, and COREX-owned background queries. T01 qualifies the amended contracts on 261; small probes are evidence, not task acceptance.
- Native table extraction remains authoritative. DPF is an optional narrowly proved implementation aid, not a prerequisite for the entire catalogue and not a substitute for authored-tree information.
- Fresh-run source reload is the final user choice and overrides any earlier discussion of keeping unsaved models open between runs.
- Tabular-presence search is the final user choice and overrides earlier discussions of cell/whole-table searching. FEA Table extraction remains included.
- The saved drawings are an approved **layout baseline**; exact port types/default behavior in this plan incorporate later clarified decisions. In particular Version is an integer code with a visible label, Rows/sets is a list of stored-set IDs, and displayed multi-selection text represents list items. Do not implement untyped Text ports just because a mockup uses a readable label.
- Archive inclusion is explicit user policy. Save exposes Boolean ports for result/solution files, user files and Workbench external imported files, all defaulting to True. Disabled/inapplicable controls keep their ports and are not consumed. Reports identify exclusions, and intentionally partial archives are not described as complete.
- For Image export all-object/all-view combinations are fixed behavior, so the earlier draft Batch mode selector is removed. No pairing preference remains unresolved.
- Only original neutral fixtures/examples and official public API citations belong in tracked docs/tests. Keep private research, screenshots, study product names/namespaces/hashes and proprietary source workflows out of commits and public documentation.

### 22. Planning baseline and concurrent work

At planning time the working tree already contained unrelated modifications to `docs/specs/INDEX.md`, `scripts/Strain_Gage_Positioning/modular_version/run.py`, and `tests/fixtures/graph_canvas_surface_snapshot.json`, plus an untracked physical-simulation plan and strain candidate CSV. This is a preservation warning, not authority to stage, discard or alter those files. This planning task adds only its own spec-index link to the existing index changes.

Future implementers must re-read live Git status instead of assuming this inventory is current. Initial package saving involved no application implementation, dependency installation, Ansys launch, solver run, commit or push. The later user-authorized backend refinement ran small disposable 261 Mechanical/Workbench probes without solving or opening existing user models; their results and limits are in BACKEND_DECISIONS.md. The initial T01 prerequisite check then found no accessible 252 installation. The user's subsequent release amendment replaces that historical gate with 261; it does not accept any implementation task or erase the retained evidence. Read the ledger for current implementation and commit status.
