# Mechanical Catalogue — Backend Resolution

Research and release revision: 2026-09-07. This document corrects the earlier assumption that Workbench-to-standalone export had no documented route, pins the camera route, and narrows the result-table contract. The user subsequently authorized implementation and replaced the historical 252 requirement with **2026 R1 (261) as the sole initial reference and acceptance release**. Release 252 is outside initial support; later releases remain capability-checked only. Retained probe findings below are unchanged. Neither the release amendment nor API documentation constitutes live compatibility acceptance.

## Decision summary

| Area | Selected route | Evidence status |
| --- | --- | --- |
| Selected Workbench model to standalone | Native Model.Export to `.dsdb`, then separate same-release standalone Open and SaveAs to `.mechdb` or `.mechdat`; model-only. | Basic 261 model round trip passed. Result/dependency transfer is outside this export contract. |
| Archive inclusion controls | Separate Boolean controls for result/solution files, user files and Workbench external imported files. COREX defaults all three to True; inactive format-specific controls are not consumed. | **261 native Workbench control passed** with all flags True: independent unarchive/reopen retained the real `.rst` and result-reader sets `[1, 2, 3]`. |
| Saved camera enumeration | Export model-view XML; read direct ModelView children and Name; preserve original child indices; apply each index and read numeric camera fields through public APIs. | **261 live basic check passed**: two named views, indices 0/1, numeric camera fields. Restore/rename/delete/duplicate cases remain qualification work on 261. |
| Background tree search | **User selected COREX-owned data queries** for the eleven visible categories. Do not call native Filter/Find/IsObjInTreeView. | Native 261 route rejected live. The replacement's explicit meanings and differences are fixed below; exact native Outline parity is no longer the acceptance target. |
| Native API tables | Enumerate ITable.Keys and retrieve columns through get_Item/key access; read Independents/Dependents. | Concrete interface; particular result columns are not universally available headlessly. |
| General result summary histories | Enumerate stored sets through Analysis.GetResultsData().ListTimeFreq; evaluate the configured result at each SetNumber; read its Minimum/Maximum/Average quantities. | Public Ansys example; use a configured-result adapter and preserve state. Do not claim universal TabularData history support. |
| ForceReaction histories | Accept only an unambiguous time-driven probe already `By=Time`; use DisplayTime and RetrieveResult, read XAxis/YAxis/ZAxis/Total, restore DisplayTime and verify By stayed unchanged. | Live 261 makes By read-only and exposes no ForceReaction.SetNumber. Reject other modes; never assign By or invent a fallback. |

## 1. Native archives and model-only cross-format export

Archive creation follows the source owner. Standalone Mechanical uses Project.Archive/Unarchive for `.mechpz`. Workbench uses native Archive/Unarchive for whole-project `.wbpz`. Reject `.mechpz` for a Workbench source with guidance to choose `.wbpz`; there is no alias, fallback, or `.dsdb` archive conversion.

The selected sequence is:

1. Within the isolated Workbench session, resolve the selected system's **Model container** and flush its owned editor as required by the native lifecycle.
2. Call the documented Model container `Export(FilePath=bridge_dsdb_path)`. The destination is a new run-owned `.dsdb` interchange file. This is an actual native export, **not** a copied internal project database.
3. Start a separate standalone Mechanical owner of the **same product release**, and open that exported file through the standalone Project.Open API.
4. Use standalone Project.SaveAs for `.mechdb` or `.mechdat`. Close the conversion owner after staging/verification.
5. Reopen the output and verify the selected model boundary, tree, geometry, changed loads, selections, snippets and views. Verify source integrity and report omitted results, user files, imported files, Workbench topology and project dependencies accurately. This model-only route has no archive, retained-result or dependency-transfer acceptance gate. The original Workbench owner/project remains intact; reconnect its editing client only if its lifecycle required closing it.

Workbench Model.Export is documented for `.dsdb` in the [261 Model container reference](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb2_js/ContainerName30.html). Standalone Mechanical explicitly accepts `.dsdb` in the [261 opening guide](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_Define_Analysis_Type_step.html). The standalone operations are documented in 261 as [Open](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item24511471501692523719712618616310178171248191184916825.html), [SaveAs](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item2301862269413248198541712202549813619610921712886182.html), and [Archive](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item1322132429717421118220323412032182984249342261881849.html).

This composition resolves the selected-model export choice. A basic 261 live check confirms marker-preserving standalone `.mechdb` and `.mechdat` reopening. A separate historical probe also created `.mechpz` after conversion, but that path is outside the amended Workbench-source contract and is not implementation guidance. Shared Model-cell boundaries remain 261 qualification work. Historically no 252 runtime was tested; that release is outside initial support.

Two concrete lifecycle details were established in the live check: use distinct staging project names/directories for different formats (the same-stem conversion sequence hit an own-project lock, while a distinct name passed); and use `Project.Unarchive(archivePath, projectPath, overwrite)` for `.mechpz`. Ordinary Project.Open explicitly requests Unarchive when passed an archive. The projectPath is the full target `.mechdb` path; Unarchive returns that path and opens the project.

Both selected-model outputs are model-only. Report omissions accurately. Do not call Project.Archive on the conversion owner, expose archive toggles for this branch, or investigate, copy, or reattach omitted files to manufacture a result-preserving archive.

Use the formal Workbench keyword names `ProjectPath` for Unarchive and `FailIfMissingFiles` for Archive, as specified by the command reference. Inconsistent old example spellings are not alternate APIs to try silently. A missing-dependency fixture verifies that the selected formal flag actually enforces the failure policy.

### Archive inclusion controls

The 261 Workbench `Archive` command exposes `IncludeSkippedFiles` for result/solution files (native default True), `IncludeUserFiles` (native default True), and `IncludeExternalImportedFiles` (native default False). Save exposes these as the typed COREX keys `include_results`, `include_user_files`, and `include_external_imported_files`. COREX defaults all three to True to retain the existing preservation policy while allowing local or wired overrides. `FailIfMissingFiles=True` remains mandatory publication validation and is not a user inclusion control.

Standalone `.mechpz` uses `ArchiveSettings.IncludeResultAndSolutionFiles` and `ArchiveSettings.IncludeUserFiles`, both documented with True defaults. It has no corresponding external-imported-file setting, so that port remains visible but disabled and unconsumed for standalone formats. Non-archive formats consume none of the three controls. Reports must identify every requested exclusion and must not call an intentionally partial archive complete.

The paired 261 control used the retained solved Workbench project without another solve. Native Workbench `Archive(FilePath=..., IncludeSkippedFiles=True, IncludeUserFiles=True, IncludeExternalImportedFiles=True, FailIfMissingFiles=True)` produced an archive containing the 589,824-byte `.rst`. After both source projects were made unavailable, native `Unarchive(ArchivePath=..., ProjectPath=..., Overwrite=True)` reopened it and `Analysis.GetResultsData()` returned sets `[1.0, 2.0, 3.0]`; the original source hashes remained unchanged. The earlier `.dsdb` result loss remains historical evidence supporting the model-only export label, not an archive acceptance gate.

### T14 native state-file preservation

The independently reviewed T14 diagnostic observed identical `/Session` data and the recorded HDF5 metadata in the working/staged `dp0/act.dat` files despite different whole-file hashes. It used one explicit 1.1-second diagnostic delay before native SaveAs, kept production validation unchanged, and failed that strict validation as expected. The result establishes observed logical equality with time-correlated container-metadata drift. It does not prove that only a timestamp field changed: complete raw phase files, low-level headers, free-space and link metadata were not retained. This evidence does not itself accept T14 publication.

The qualified correction is confined to the unique registered `dp0/act.dat` pair at working-to-stage SaveAs. Ordinary snapshot/schema/path/topology/inventory/flag checks run first. A logical comparison is admitted only when this pair's SHA is the sole remaining mismatch; names, display text, registration, existence, size, membership and associations stay exact. Both absent entries continue ordinary validation; unilateral or ambiguous entries fail. Identical bytes require no HDF5 schema qualification. No other file or phase receives this equivalence, and source, stage-to-verification, working-to-restoration and publication/rollback checks remain unchanged.

The comparison reads the two original paths inside the existing isolated Mechanical owner and its Save request timeout. It attests regular files, canonical paths, all reparse ancestors, stable identities and the native size/SHA before and after reading. The HDF5 signature must start at byte zero and the file creation user-block size must be zero; equal nonzero user blocks are not accepted. Both physical file size and logical Session data are bounded at 64 MiB, with 1 MiB data chunks and 64 KiB comment bounds. Read, schema, metadata, stability or capacity failures stop Save and preserve its ordinary staged recovery.

The closed schema has an attribute-free root and exactly one hard-linked, unaliased `/Session` dataset: rank-one unsigned 8-bit data, chunks `(262144,)`, no filters, no virtual/external storage, and exactly one `UsedSize` attribute of shape `(1,)` and unsigned 64-bit type matching the Session length. Dataset time tracking and nonzero recorded creation-time evidence are required; reopened version-one headers can otherwise expose the default tracking flag even when no times were recorded. Complete data, type/space/max-extent, attribute, comment, link and file/root/dataset creation-property comparisons use HDF5 APIs. Unknown objects, attributes, layouts and aliases are rejected. The opaque Session data is never decoded or rewritten, and no timestamp offsets are masked.

`h5py>=3.16` is a direct Mechanical dependency, already used by the existing scientific packages. Its import occurs only for this comparison, outside UI discovery. No new process, private operation, timer, serializer framework or database-copy route is introduced. Independently reviewed T14 evidence now includes successful registered no-external publication with the logical branch exercised, followed by an ordinary registered independent reopen with retained results/user files and the same selected tree. Only the Save qualification used the explicit 1.1-second timing seam; the exact reviewed source was restored afterward. The missing-dependency Archive gate is separately accepted. TASK_LEDGER.md remains the authority for final task acceptance.

Archive exclusions are native file/reference-identity policy, not removal of every identical byte sequence. The final fixture already had unregistered internal `fixture.step` and `x.step` files; both stayed intact while the active registered external `x.step` was not imported/rebased. A basename-only harness assertion therefore failed after successful publication; its aggregate remains failed. The separate ordinary reopen passed. An older retained native archive omits the registered `x.step` member while retaining the pre-existing `fixture.step` with identical STEP bytes; its earlier Save aggregate remains failed on the superseded strict state-file SHA gate. Neither observation proves absence of all copies of the source bytes.

The final consolidated receipt and read-only validator are retained under `artifacts/verification_logs/mechanical_catalogue/T14/`. They link successful subruns without rewriting failed aggregates. No-results/no-user evidence proves omission and reopenability; their resume hid a newly created STEP rather than the original archive source, so original-path independence relies solely on the separately accepted all-enabled cohort. The first successful `.wbpj` producer was overwritten before exact bytes were retained; its recorded hash and raw/output evidence remain, but exact source replayability is not claimed. No additional solve was used.

## 2. Camera names and numeric data

Use ModelViewManager.ExportModelViews to a run-owned XML file. Parse direct root children tagged `ModelView`, require their `Name` attribute, and retain each child's original enumeration index. Store records in a list so duplicate names survive. Validate the parsed view count against NumberOfViews. This exact name/index discovery approach appears in an [Ansys developer forum answer](https://discuss.ansys.com/discussion/4537/act-python-or-js-how-to-get-the-view-objects-managed-views-and-get-their-names).

Do not infer undocumented numeric XML fields. Preserve the current camera and active objects, apply each saved view by its index, and read public Camera fields: FocalPoint.Location and Unit, ViewVector, UpVector, SceneHeight and SceneWidth. Scene dimensions are quantities, not assumed model-unit floats. Restore the original state in `finally`.

The [261 saved-view guide](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_script/mech_apis_graphics_manage_views.html) documents count/export/apply operations. Qualification on 261 must cover zero views, several views, duplicate/renamed/deleted entries, index validity, malformed XML and restoration. Unknown XML shape is an explicit error; it is not silently converted into an empty saved-view list.

## 3. Background search design selected by the user

The 261 stubs expose `Tree.IsObjInTreeView(IDataModelObject) -> bool`, but the reference does not define its filtering semantics. The 261 live probe has now ruled out the proposed embedded Filter/membership route; do not repeat it as if still untested or use its all-false return values as empty-search evidence.

| UI mode | Native Filter keyword |
| --- | --- |
| Name | `name` |
| Tag | `tag` |
| Type | `type` |
| State | `state` / `filterState`, according to the actual visible state choice |
| Coordinate System | `coordinateSystem` |
| Model | `model` |
| Graphics | `visibility` |
| Environment | `environment` |
| Scoping | `scoping` |
| Property Name | `propertyName` |
| Property Value | `propertyValue` |

The completed no-solve check created a static analysis and two named selections, saved and reopened its own `.mechdb`, and refreshed the tree. There were 16 objects. DataModel.GetObjectsByName returned the expected marker ID, while Tree.Find reported that its enumerator is unavailable in batch mode. Tree.Filter raised a null-reference exception for empty, matching and nonmatching queries. IsObjInTreeView returned false for all 16 objects in all three cases. The session closed successfully. An earlier unsaved-model check showed the same Filter failure, so this was not resolved by saving/reopening or Tree.Refresh.

The ordinary data API therefore supports inventory/name/property queries, but native Outline membership is not a valid embedded match engine. Four exact-native mappings remain unestablished: implicit coordinate associations (None can mean Solution coordinates), assembly source-model identity from importable source IDs, complete direct/indirect object-to-visible-body association, and historical partial/lost scoping. Environment also needs global/shared boundary-condition activation, not only ancestry. Declared fields such as AttachedRefs and ImportableObjectSourceId have insufficiently documented semantics to claim a universal substitute.

After reviewing the failed native route, the user selected **Background data filters: build COREX-owned model queries and review differences in the difficult filter modes**. The eleven visible category names remain. Their contract is the explicit data-query table below, not an undocumented attempt to recreate native Outline internals. This resolves the backend direction; no hidden GUI launch or native filter call is needed for Search.

| Category | COREX background definition | Public data and boundary |
| --- | --- | --- |
| Name | Match the object's displayed Name; multiple terms are ANDed. | Tree.AllObjects inventory and Name; no Tree.Find. |
| Tag | Match the object's directly assigned tag names. | ObjectTags / documented tag labels; no inherited-tag inference. |
| Type | Match actual DataModelObjectCategory or API type labels. | Current object category/type; show available type labels. Native UI supergroups are not guessed from names. |
| State | Match explicit ObjectState labels and the readable Suppressed flag. | Use real enum names; Not licensed is the displayed alias for LicenseConflict, Underdefined for UnderDefined. A missing/unreadable state is Unknown, not healthy. |
| Coordinate System | Match directly reported coordinate-system bindings by name/ID, or an explicit binding label such as Solution. | Type-aware adapters for documented CoordinateSystem fields and probe CoordinateSystemSelection/Orientation. Missing/None is never assumed Global. This does not include every implicit native association. |
| Model | Match the current opened document/system, or an object's recorded ImportableObjectSourceId. | Current source identity comes from Open; imported IDs are exact opaque values, shown as Source ID when no trusted label exists. Do not guess an assembly cell label from an ID. |
| Graphics | Match Body.Hidden directly: shown-body or hidden-body records. | Applies to Body records with a readable Hidden flag. It does not pull in loads/results through inferred geometry links or represent viewport occlusion. |
| Environment | Match an explicit owning analysis; include shared/global objects only when their per-analysis activation API establishes membership. | Analysis ancestry for owned objects; documented GetActivationStatusForAnalysis and native GlobalObjectState for supported shared-object adapters. Unavailable activation is Unknown, not inferred from a name. |
| Scoping | Match current explicit scope kind, referenced selection/object, or empty explicit scope. | Typed Location/SourceLocation/TargetLocation and documented object-scoping fields; preserve source/target roles. Partial/lost-history detection is not provided because current IDs/counts cannot establish lost original references. |
| Property Name | Match visible property Caption and preserve its API key. | VisibleProperties by default; optional hidden Properties. |
| Property Value | Match scalar/enum display text, formula text, or the summary Tabular data. | StringValue plus Field definition metadata; no cells, formula execution or whole-table comparison. |

### Query and availability rules

- These are deliberate, documented definitions, not claims of identical native Outline results. T06 must test these definitions. Do not use a native UI count as the sole expected value for the four differing categories.
- Query dropdown labels make the distinctions visible: Coordinate System says `Explicit assignment`; Model says `Current document` or `Source ID: ...` when no source label is established; Graphics offers `Shown bodies` / `Hidden bodies`; Scoping offers current `Geometry`, `Mesh nodes`, `Mesh elements`, `Named selection`, `Referenced object`, `Empty explicit scope`, and `No explicit scope` as supported by observed records.
- Keep the existing Filter/Query controls and section layout. Use contextual placeholders/tooltips and Details metadata, not additional control ports or a new backend selector.
- Empty Query means no restriction within the selected search universe. For a nonempty category query, only applicable/readable records can match. Distinguish `available`, `not_applicable`, and `unavailable`; an unavailable getter produces a diagnostic/count. If metadata required to decide that query is unavailable for an applicable object, fail with `mechanical.search_incomplete` rather than emit a falsely complete list or Found=False. Unreadable unrelated descriptive fields may remain diagnostic rows without invalidating a Name/Type match. Inversion negates only available applicable predicates, so unavailable data does not become a positive match.
- Coordinate adapters report the property/API key and explicit relation role. For documented probe None=Solution cases, emit Solution; for other unassigned/unsupported cases emit Unspecified/Unavailable. Never infer missing Global or Fiber associations. A user seeking all textual mentions of a coordinate name can use Property Value separately.
- Model source IDs are compared as opaque exact identities. Human names may be used only when supplied by trusted model/system metadata. Locally created objects without an import source still belong to the current opened document; absence of an imported ID is not evidence that another source cell owns the object.
- Graphics does not classify non-body objects as visible/hidden. Parent-group hiding, suppression and effective display are not silently folded into the Hidden flag; users can additionally query State. This is a body-flag query, not the native associated-object visibility filter.
- Scope adapters preserve explicit primary/source/target/other documented roles. A readable empty selection is `scope_kind=empty_explicit_scope`. Confirmed absence of a scoping field on a supported object is an **available** classification, `scope_kind=no_explicit_scope`, so the offered No explicit scope query can match it and inversion is well defined. Do not mark this confirmed absence not_applicable. A failed getter or an unclassified extension type remains unavailable and produces search_incomplete when needed. Unsupported Partial/lost-scoping text is rejected with a clear explanation; it is not treated as an empty result or mapped to UnderDefined.
- Environment membership for a global/shared boundary condition must use a tested adapter for the native activation API. If that API is missing for an object/release, record unavailable shared membership; do not claim ancestor-only traversal covers it. Record the native activation state and use only the explicitly active state for matching.
- Plain-text matching uses Unicode-aware `casefold()` unless Case sensitive is enabled. Exact compares the whole query with the whole displayed text and never tokenizes Name. Contains uses the whole query as one substring except Name + Contains, which splits an unquoted query on Unicode whitespace, discards empty terms and requires every term in any order. Preserve interior whitespace for Exact, ordinary Contains and bare Property Value operands; only Name + Contains tokenizes whitespace. Quotes in Name are literal, and otherwise nonempty Name/other plain-text queries remain unchanged. Empty or whitespace-only unquoted text keeps the existing unrestricted meaning.
- Property Value alone accepts optional `Property Name = Property Value` syntax. Split only the first `=` outside double-quoted operands; subsequent equals signs belong to the value. A quoted operand must be the entire operand and use standard JSON string escapes; trim only syntactic outer whitespace and preserve its decoded content. Bare operands retain interior whitespace, literal backslashes and apostrophes; trim only syntactic edge whitespace. When an outside `=` is present, reject an empty property caption. An explicitly empty value matches only an available empty display value in both Exact and Contains modes and never means unrestricted search. Without an outside `=`, Property Value has no caption restriction. Reject malformed/unmatched quotes or escapes. Examples are `Comment = "Load = 100 N"` and `Comment = "Bolt \"A\""`. This is one optional pair, not a clause/query language.
- Validate and resolve accepted picker identity codes before plain-text parsing. They remain opaque exact IDs; the text grammar never reinterprets them.

### Metadata schema addition

Add `relation` to Info/Report record_kind. A relation row uses the existing object_id/path as its subject and these appended columns: `relation_kind`, `relation_role`, `related_label`, `raw_source_id`, `scope_kind`, `relation_status`, `activation_state` (Text); `related_object_id`, `scope_count` (nullable Integer); `body_hidden` (nullable Boolean). Other row kinds carry empty/null values for these fields. Allowed relation kinds are `coordinate_system`, `source_model`, `body_visibility`, `environment`, and `scope`; statuses are `available`, `not_applicable`, `unavailable`. No nested live objects or raw selection arrays enter the UI metadata table. Existing catalogue size/identity/revision limits still apply.

The [261 native filter guide](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_filter_tree.html) documents the differences described above. The selected data-query implementation does not change Outline filter, active-object or expansion state, so no native filter restoration is part of this route. If native interactive filtering is separately added later, it must first establish exact snapshot/restoration; it is outside this selected backend design.

## 4. Table API correction

`ITable` is a labeled column mapping, not the newer IDataTable interface. Read Keys in the API's advertised order and fetch each column through key/get_Item access; record Independents and Dependents membership. Do not invent Columns/GetColumnValues on ITable. The interface alone does not guarantee that every GUI result-table column exists in background mode.

The [Ansys headless-table discussion](https://discuss.ansys.com/discussion/3129/how-to-access-tabular-data-values-in-mechanical-scripting-without-the-gui-open) gives a configured-result approach: obtain available time/frequency sets from the result reader, select each stored set, evaluate that result, and read its summary quantities. The [earlier table discussion](https://discuss.ansys.com/discussion/255/how-to-access-tabular-data-using-act) distinguishes a working modal Frequency column from general tabular support. These are limitations to test on 261, not evidence that no modern result table can work.

Pin the FEA Table dispatch as follows:

- Field/Variable definitions: direct authored input/output values, units and formula metadata, unchanged from the plan.
- API-native tables: return columns that the actual ITable exposes, including modal Frequency when supported. Unsupported/missing columns are diagnosed; no GUI pane scraping.
- Result summary history: configured result object, stored set ordinal, CalculateTimeHistory disabled only for the bounded evaluation loop, and native Minimum/Maximum/Average reads. Restore By, DisplayTime and CalculateTimeHistory exactly. Restore SetNumber too except for the proved initial `By=Time`/inactive `SetNumber=0` case where the public setter rejects zero; there retain only a valid positive SetNumber and report the before/after inactive drift. Every other restoration failure is fatal. Evaluate only the selected result and never solve.
- ForceReaction: use its documented native RetrieveResult and axis/total quantities only when the probe is already `By=Time` and stored times are unambiguous. Do not assign the read-only By property. Set and restore DisplayTime, verify By stayed unchanged, and reject all other addressing modes. Repeated/ambiguous stored times or unsupported analysis modes receive an explicit unsupported-adapter error; do not merge rows or pretend an absent SetNumber property exists.
- PlotData: remains spatial result data for one evaluated set, not a result history.
- Mesh/layered-section worksheets: retain their explicit row APIs and mixed scalar columns.

DPF remains an optional specifically validated path for a required result family. Do not reinterpret arbitrary reaction probes through an unmatched nodal-force sum or silently change a Mechanical result's averaging/scoping semantics.

## 5. Historical planning-machine availability and retained test status

At the initial planning-probe snapshot, the project venv reported PyMechanical 0.12.12, Mechanical stubs 0.1.12 and DPF 0.16.1; PyWorkbench was absent then. Environment variables advertised v261 and v232, not v252. These statements are dated historical evidence, not the current environment inventory. Later T01 work installed and used PyWorkbench 0.14.0 and retained one solved 261 fixture, as recorded in the capability proof and task ledger; do not infer current availability without a fresh check.

For that initial planning-probe snapshot, the user explicitly authorized Ansys 2026 R1. No existing user project was opened or modified, no solve was run, and no node implementation or task commit was made. Workbench used native RunWB2 for the disposable export because PyWorkbench was absent at that time. Every embedded planning probe reported successful close; all planning-probe commands and the Workbench job exited. Subsequent T01 evidence is governed by the capability proof and ledger.

Retained evidence under `artifacts/verification_logs/mechanical_catalogue/planning_backend/`:

| Report | Result and limit |
| --- | --- |
| `tree_membership_261.json` | Initial unsaved-model Filter failure; no user input file. |
| `tree_membership_reopened_261.json` | Runtime version 261; saved/reopened fixture; 16-object negative membership test; data-name lookup works; native Find/Filter route rejected. |
| `workbench_export_261.json` | Native Workbench Model.Export created the `.dsdb` interchange; owned editor closed. |
| `conversion_camera_261.json` | Marker preserved in `.mechdb`; archive created; two XML-named views applied and public numeric fields read; interchange source hash unchanged. Same-stem `.mechdat` sequence hit a project lock. |
| `conversion_distinct_paths_261.json` | Distinct-name `.mechdat` SaveAs/reopen preserved marker; ordinary Open of `.mechpz` explicitly rejected in favor of Unarchive. |
| `archive_unarchive_261.json` | Explicit Project.Unarchive opened the archive at the requested `.mechdb` destination and preserved marker. |

The initial rows above retain the small planning-probe history. The completed T01 evidence additionally qualifies result-file completeness, nonempty geometry, shared Model-cell export boundaries, selected data-query adapters and full camera restoration on 261. The user removed the historical 252 gate and approved the two narrow result-state policies above. TASK_LEDGER.md owns current task acceptance and commit status.
