# COREX Mechanical Catalogue

The Mechanical catalogue provides eight typed nodes under **FEA > ANSYS > Mechanical**. It opens a fresh isolated working model whenever a run requires Mechanical operations, exposes data-only model observations, supports explicit mutations, and writes only through **Save Mechanical Model** or user-authored code.

Initial support and live acceptance target Ansys 2026 R1 (`261`) on Windows. Release `252` and earlier are unsupported. A later installed release is offered only after its required Mechanical or Workbench capability handshake succeeds; that is capability-checked operation, not full release certification.

## Install

Install COREX with the Mechanical dependencies in the project virtual environment:

```powershell
py -3.10 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -e ".[ansys]"
```

The minimum declared Python packages are `ansys-mechanical-core>=0.12.6`, `ansys-workbench-core>=0.14.0`, `h5py>=3.16`, `numpy>=2.0`, and `pandas>=2.3`; the Ansys installation and license are supplied separately. Add-on discovery checks package and installation metadata without launching Mechanical, opening a model, or checking out a license. **Auto** selects the newest discovered release at least `261`.

## Runnable examples

The committed examples deliberately contain blank authored Open and Save paths. Open the project, choose a source in **Open Mechanical Model > File**, and, for the mutation example, choose a separate destination in **Save Mechanical Model > File**. The blank values avoid persisting personal paths or silently overwriting a source.

| Example | Authored graph | Purpose |
| --- | --- | --- |
| [Mechanical table to Signal Plot](../examples/mechanical_table_to_signal_plot.cxproj) | Open → exact Name Search; Open + `Search.objects` → FEA Table; `FEA.tables` → Signal Plot | Extract the retained `XComponent` model definition in source units. `Search.properties` is intentionally not connected. |
| [Mechanical camera and image workflows](../examples/mechanical_camera_image_workflows.cxproj) | Open → saved Camera Views → two-object batch Export; the same Open also feeds a separate current/current preview Export → Media Panel | Keep the six-image object/view batch separate from the single-item Media Panel preview. |
| [Mechanical mutate, snippet, and save](../examples/mechanical_mutate_snippet_save.cxproj) | Open → Script → owned all-step Snippet → explicit Save | Read the current `COREX constant load`, add 100 N, inject an owned APDL snippet, then publish an explicit output. |

Regenerate the projects through the normal serializer path:

```powershell
.\venv\Scripts\python.exe .\scripts\mechanical_catalogue\generate_examples.py --output-dir .\examples
```

The generator uses fixed project, workspace, view, node, and edge IDs. It builds each current-schema document through `JsonProjectSerializer.from_document`, normalizes it with `to_persistent_document`, publishes with `save_document`, reloads with the ordinary `load` path, and verifies every surviving edge through `GraphInvariantKernel`. Initial section state comes from each current `NodeTypeSpec.default_expanded_settings_group_ids` and is preserved by the authored document.

For retained live fixtures, tests or T18 tooling may call `inject_fixture_paths(...)` from the generator after loading. That helper changes only the Open/Save properties through `ValidatedGraphMutation`; fixture paths are never committed into the examples.

### T18 live gates not claimed by these documents

- Table workflow: the retained source must yield `Time [sec] = [0, 1, 3]` and `Force [N] = [0, 100, 200]` through the registered Open → Search → FEA Table → Signal Plot composition.
- Image workflow: the new typed `Camera.views → Export.views` wire must produce two objects × three saved views in object-major order. The separate current/current Export must still produce one image accepted by Media Panel; six images are not fed to its single-item input.
- Mutation workflow: run twice from the unchanged 500 N source into distinct destinations. Each run must read the fresh value and write 600 N, never 700 N; both outputs retain the owned snippet, the source hash stays unchanged, and no implicit solve occurs. A fixed 600 N assignment would not prove freshness.

T17 proves structure, persistence, registry compatibility, and documentation without launching Ansys. T18 owns the live executions above.

## Current data and fresh Mechanical operations

Adding a consumer to a completed Image or Table does not require reopening Mechanical. Auto and Run Selected can consume the requested current data ports directly from the execution-owned SolutionStore. This also applies to data ports on a node that separately returns a live Model: unused Model handles are not transferred or revived.

Current-result consumption does not execute or republish the producer. Changes to its relevant inputs expire downstream results as before. Missing, expired, evicted, or incompatible data requires recomputation. Explicitly requesting a Mechanical operation, a full graph run, or Force Recompute still follows the fresh-source lifecycle. An operation required by another executing branch or an ordering dependency cannot be replaced with a current-data read. Live Models and run-bound object/camera selectors remain subject to session and revision checks.

This is shared execution behavior, so future FEA nodes can use the same typed data and lifetime contracts. The UI's preview cache is never execution authority.

## Exact node and port contract

All ports below are ordinary typed `data` ports. Item, List, and Tree are explicit data-access contracts. Every listed input is exposed; a connected value overrides its local property default. Section collapse changes presentation only and preserves ports and wires.

### Open Mechanical Model (`mechanical.open_model`)

Fresh default section: `open_options` (**Open options**, expanded). `session_options` (**Session options**) starts collapsed.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `file` | In | `COREX.DataTypes.Path` / Item; accepts String | Required; blank while authoring |
| `system` | In | `COREX.DataTypes.String` / Item | `""` |
| `mode` | In | `COREX.DataTypes.String` / Item | `background` |
| `version` | In | `COREX.DataTypes.Int` / Item | `0` (Auto) |
| `working_folder` | In | `COREX.DataTypes.Path` / Item; accepts String | `""` (run-owned folder) |
| `timeout_s` | In | `COREX.DataTypes.Double` / Item | `600.0` |
| `model` | Out | `COREX.Mechanical.Model` / Item | Successful open only |
| `info` | Out | `COREX.DataTypes.TableValue` / Item | Session/system/catalogue descriptors |

Standalone inputs are `.mechdat`, `.mechdb`, and native `.mechpz`; Workbench inputs are `.wbpj` and native `.wbpz`. If a Workbench project has several distinct Model containers, an empty `system` returns discovery-only Info with `status=system_required`, no Model, and a selection warning. A sole model is selected automatically.

### Search Mechanical Tree (`mechanical.search_tree`)

Fresh default section: `search` (**Search**, expanded). `match_options` (**Match options**) starts collapsed.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `model` | In | `COREX.Mechanical.Model` / Item | Required |
| `filter` | In | `COREX.DataTypes.String` / Item | `name` |
| `query` | In | `COREX.DataTypes.String` / Item | `""` |
| `match` | In | `COREX.DataTypes.String` / Item | `contains` |
| `case_sensitive` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `include_hidden_properties` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `invert` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `objects` | Out | `COREX.Mechanical.Object` / List | Deduplicated tree order |
| `properties` | Out | `COREX.Mechanical.Property` / List | Matching/discoverable descriptors |
| `found` | Out | `COREX.DataTypes.Bool` / Item | Complete-match result |
| `details` | Out | `COREX.DataTypes.TableValue` / Item | Data-only match rows |

### FEA Table (`mechanical.fea_table`)

Fresh default section: `table_selection` (**Table selection**, expanded). `values_and_units` (**Values and units**) starts collapsed.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `model` | In | `COREX.Mechanical.Model` / Item | Required |
| `source` | In | `COREX.Mechanical.Object` / List; accepts Mechanical Property | Required, nonempty |
| `family` | In | `COREX.DataTypes.String` / Item | `auto` |
| `table` | In | `COREX.DataTypes.String` / Item | `""` |
| `component` | In | `COREX.DataTypes.String` / Item | `all` |
| `units` | In | `COREX.DataTypes.String` / Item | `source` |
| `sets` | In | `COREX.DataTypes.Int` / List | `[]` |
| `tables` | Out | `COREX.DataTypes.TableValue` / List | Full-fidelity source order |
| `definitions` | Out | `COREX.DataTypes.TableValue` / Item | Units/provenance/definition metadata |

### Mechanical Camera Views (`mechanical.camera_views`)

Fresh default section: `view_selection` (**View selection**, expanded).

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `model` | In | `COREX.Mechanical.Model` / Item | Required |
| `include` | In | `COREX.DataTypes.String` / Item | `saved_and_current` |
| `views` | Out | `COREX.Mechanical.CameraView` / List | Saved order, then current when requested |
| `names` | Out | `COREX.DataTypes.String` / List | Same order as Views |
| `details` | Out | `COREX.DataTypes.TableValue` / Item | Numeric camera fields and units |

### Export Mechanical Image (`mechanical.export_image`)

Fresh default section: `selection` (**Selection**, expanded). `image_options` (**Image options**) and `save_to_disk` (**Save to disk**) start collapsed.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `model` | In | `COREX.Mechanical.Model` / List | Required; exactly one per matched branch |
| `objects` | In | `COREX.Mechanical.Object` / List; accepts String | `[]` (current display) |
| `views` | In | `COREX.Mechanical.CameraView` / List; accepts String | `[]` (current camera) |
| `width` | In | `COREX.DataTypes.Int` / Item | `1600` |
| `height` | In | `COREX.DataTypes.Int` / Item | `1000` |
| `background` | In | `COREX.DataTypes.String` / Item | `white` |
| `fit_view` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `folder` | In | `COREX.DataTypes.Path` / Item; accepts String | `""` (no user-file output) |
| `file_name` | In | `COREX.DataTypes.String` / Item | `{object}_{view}.png` |
| `overwrite` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `images` | Out | `COREX.DataTypes.Image` / Tree | Object-grouped PNG values |
| `files` | Out | `COREX.DataTypes.Path` / List | Flattened object-major publication order |
| `details` | Out | `COREX.DataTypes.TableValue` / Item | Identity, DataPath, size, and file facts |

### Run Mechanical Script (`mechanical.run_script`)

Fresh default section: `script` (**Script**, expanded). `execution_options` (**Execution options**) starts collapsed. The mutator's actual model input key is `source_model`; **Model** is its visible label.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `source_model` | In | `COREX.Mechanical.Model` / Item | Required |
| `environments` | In | `COREX.Mechanical.Object` / List; accepts String | `[]` (all analyses) |
| `scope` | In | `COREX.DataTypes.String` / Item | `each_environment` |
| `code` | In | `COREX.DataTypes.String` / Item | Required, nonempty |
| `timeout_s` | In | `COREX.DataTypes.Double` / Item | `600.0` |
| `stop_on_error` | In | `COREX.DataTypes.Bool` / Item | `true` |
| `model` | Out | `COREX.Mechanical.Model` / Item | New revision after complete success |
| `report` | Out | `COREX.DataTypes.TableValue` / Item | Ordered receipts plus refreshed catalogue |

### Mechanical APDL Snippet (`mechanical.apdl_snippet`)

Fresh default section: `command_snippet` (**Command snippet**, expanded). `solver_placement` (**Solver placement**) starts collapsed. The mutator's actual model input key is `source_model`; **Model** is its visible label.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `source_model` | In | `COREX.Mechanical.Model` / Item | Required |
| `environments` | In | `COREX.Mechanical.Object` / List; accepts String | `[]` (all supported analyses) |
| `name` | In | `COREX.DataTypes.String` / Item | Required; `COREX commands` |
| `commands` | In | `COREX.DataTypes.String` / Item | Required, nonempty |
| `steps` | In | `COREX.DataTypes.String` / Item | `all` |
| `selected_steps` | In | `COREX.DataTypes.Int` / List | `[1]`; inactive for All |
| `issue_solve_command` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `model` | Out | `COREX.Mechanical.Model` / Item | New revision after complete success |
| `snippets` | Out | `COREX.Mechanical.Object` / List | Analysis order, then step order |
| `report` | Out | `COREX.DataTypes.TableValue` / Item | Mutation receipts plus refreshed catalogue |

### Save Mechanical Model (`mechanical.save_model`)

Fresh default section: `destination` (**Destination**, expanded). `save_options` (**Save options**) starts collapsed. The mutator's actual model input key is `source_model`; **Model** is its visible label.

| Port | Direction | Type / access | Required or default |
| --- | --- | --- | --- |
| `source_model` | In | `COREX.Mechanical.Model` / Item | Required |
| `file` | In | `COREX.DataTypes.Path` / Item; accepts String | Required; blank while authoring |
| `format` | In | `COREX.DataTypes.String` / Item | `auto` |
| `include_results` | In | `COREX.DataTypes.Bool` / Item | `true` |
| `include_user_files` | In | `COREX.DataTypes.Bool` / Item | `true` |
| `include_external_imported_files` | In | `COREX.DataTypes.Bool` / Item | `true` |
| `overwrite` | In | `COREX.DataTypes.Bool` / Item | `false` |
| `model` | Out | `COREX.Mechanical.Model` / Item | Fresh admissible revision after publication |
| `files` | Out | `COREX.DataTypes.Path` / List | Primary and required companions |
| `report` | Out | `COREX.DataTypes.TableValue` / Item | Publication/inclusion/recovery facts |

## Search meanings and grammar

Search uses eleven COREX-owned background filters. It never calls native Outline Filter/Find/membership APIs, never changes the Outline, and does not claim native filter parity.

| Filter code | Visible meaning and boundary |
| --- | --- |
| `name` | Displayed object Name. Only Name + Contains splits unquoted Unicode whitespace and ANDs every term in any order. |
| `tag` | Direct ObjectTags names only; no inherited tags. |
| `type` | Actual data-model category/API type labels; no guessed UI supergroups. |
| `state` | Explicit ObjectState and readable Suppressed flag. `LicenseConflict` displays as Not licensed and `UnderDefined` as Underdefined. |
| `coordinate_system` | Direct documented bindings and type-aware probe orientation/selection. Missing does not mean Global; documented Solution is distinct. |
| `model` | Current document/system identity or exact opaque `ImportableObjectSourceId`; no guessed assembly-cell label. |
| `graphics` | Readable Body.Hidden only: Shown bodies or Hidden bodies. It does not infer viewport occlusion or associated loads/results. |
| `environment` | Owning analysis plus only tested per-analysis activation for shared/global objects; ancestry alone is not universal. |
| `scoping` | Current explicit scope kind/reference/count with primary/source/target roles. Empty explicit scope differs from confirmed No explicit scope. Historical Partial/lost scoping is unsupported. |
| `property_name` | Visible Caption with the API key retained; hidden properties are optional. |
| `property_value` | Scalar/enum StringValue, formula text, or the literal summary `Tabular data`; never table cells. |

Case-insensitive matching uses Unicode `casefold()`. Exact compares the complete query and displayed text. Ordinary Contains treats the query as one substring; Name + Contains is the only whitespace-tokenized mode. Quotes in Name are literal. An empty or whitespace-only unquoted query removes the restriction within the chosen universe.

Property Value may use one optional `Property Name = Property Value` pair. Split only on the first `=` outside quoted operands, so `Comment = "Load = 100 N"` is valid. A quoted operand is one complete JSON string token and supports JSON escapes such as `\"` and `\\`; outer syntax whitespace is discarded while decoded content is preserved. Bare operands preserve interior whitespace, backslashes, and apostrophes. A pair requires a nonempty caption. An explicitly empty value matches only an available empty displayed value in both match modes. Malformed quotes/escapes fail. There is no regex, numeric tolerance, unit conversion, multi-clause language, formula execution, or table-cell search. Typed picker identities are validated before this grammar and remain exact opaque identities.

If applicable data needed for the selected predicate is unavailable, Search fails with `mechanical.search_incomplete`; inversion never converts Unknown into a match. A genuine complete no-match returns empty outputs and `found=false`.

## Tables, units, and result state

FEA Table supports these explicit families:

1. Model definitions from Field Inputs/Output and Variable metadata: one-value native definitions use `DefinitionType.Discrete`, not a `Constant` enum. Constants, ramps/tabular definitions, formulas and samples, vector components, free/locked states, and bolt-pretension step states preserve native order and units. A scalar constant does not acquire an invented time column.
2. Native ITable columns through Keys and key/item access, including qualified modal Mode/Frequency data.
3. Configured-result Minimum/Maximum/Average histories over stored result sets.
4. PlotData spatial samples with entity/location/component/set identity.
5. The qualified time-driven ForceReaction adapter with X/Y/Z/Total values.
6. Mesh-control and layered-section worksheets through their documented row APIs.

`units=source` preserves native units. `units=si` converts only actual quantity columns with native Ansys quantity facilities, including affine temperatures. Identifiers, states, and formulas are not converted. Tables are immutable `TableValue` objects; Signal Plot may reduce rendering points but cannot mutate or truncate the extracted source.

Selected existing results may be evaluated, but FEA Table never calls Solve. Missing/unsolved data fails. Configured-result state is restored in `finally`; only an initial `By=Time`, inactive `SetNumber=0` may retain a valid positive SetNumber when native 261 rejects restoring zero, and that drift is reported. ForceReaction must already be `By=Time`; its `By` is read-only in live 261, DisplayTime is restored, and ambiguous/repeated times or other addressing modes are rejected. Camera, active-object, and graphics restoration remain exact; other restoration failures retire the session.

Search's `has_tabular_data` and `Tabular data` value are presence metadata only. Connect `Search.objects` or `Search.properties` to FEA Table for cell/sample extraction.

## Cameras, images, and data trees

Camera Views exports saved-view XML to run-owned storage, parses direct `ModelView` names in native order, retains original indices so duplicate names remain distinct, applies each index, and reads public numeric camera fields. Current view uses the reserved visible label **Current view**. Text selection of an ambiguous duplicate fails.

Image export consumes complete object and view Lists inside each matched branch. For incoming path `p`, executor invocation `j`, and object ordinal `i`, output Images uses branch `p + (j, i)` and places selected views in order. Flattened Files and Details remain object-major. Empty Objects means the current active display; empty Views means the current camera. Exactly one Model is allowed per matched branch—use the existing Graft modifier for multiple models.

The capture transaction validates all selectors and output paths before capture, restores camera/active/visibility/result state in `finally`, stages all PNGs before optional publication, and rejects path escape, duplicate destinations, and existing files when Overwrite is false. `fit_view=false` preserves the requested view; fitting occurs only when explicitly enabled. Media Panel accepts one image item, so use a separate current/current preview rather than connecting a six-image tree directly.

## Scripts, snippets, revisions, and ordering

Run Script supplies `ExtAPI`, `DataModel`, `Model`, ordered `analyses`, and `analysis` for each selected environment. `each_environment` runs once per analysis in tree order; `model_once` runs once with `analysis=None`. Authored code is IronPython-compatible. It may explicitly solve or save if the user writes that operation, but the node adds neither. With Stop on error disabled, later environments are attempted and reported, but any failure still fails the node and emits no success Model. Timeout, cancellation, or transport loss retires the uncertain session and never retries mutating code.

The example script reads `XComponent.Output` strictly, requires native `Discrete`, reads exactly one current sample in N, and assigns current + 100 N. It does not catch broad exceptions and does not hard-code 600 N.

APDL Snippet targets load steps, not solver substeps. All uses the native all-step mode; Selected creates one owned snippet per selected step when needed. COREX prepends a deterministic ownership marker based on workflow node, analysis, and step identity and preserves the authored command body exactly. A same-name unowned snippet is a collision and remains untouched. A saved rerun updates only matching owned snippets. `issue_solve_command` controls generated solver input; running the node never launches a solve.

Every attempted mutation invalidates the prior model revision. Order changes only with data dependencies: `Open.model → Script.source_model → Snippet.source_model → Save.source_model`. Canvas position does not order execution. Two sibling mutators cannot consume the same revision; one becomes stale.

## Explicit save and publication

Format codes are `auto`, `mechdb`, `mechdat`, `mechpz`, `wbpj`, and `wbpz`; explicit format and extension must agree.

| Source | Destination | Contract |
| --- | --- | --- |
| Standalone | `.mechdb`, `.mechdat` | Native save/export. `.mechdat` is a model export and omits external solver files. Archive controls are inactive. |
| Standalone | `.mechpz` | Native Mechanical archive. `include_results` and `include_user_files` apply; external imported files is disabled/unconsumed. |
| Workbench | `.wbpj` | Native whole-project save with companion assets. Archive controls are inactive. |
| Workbench | `.wbpz` | Native whole-project archive. Results/solution, user files, and external imported files are independent inclusion choices; `FailIfMissingFiles=True` remains mandatory. |
| Selected Workbench Model | `.mechdb`, `.mechdat` | Native Model.Export to a run-owned `.dsdb`, then separate same-release standalone Open/SaveAs/reopen. This is model-only, never an archive. |

Workbench-to-`.mechpz` is rejected with guidance to use `.wbpz`. The selected-model export omits results, user/imported/external files, Workbench systems/topology/shared links, design points, and project dependencies; the Report names those omissions. It does not expose archive toggles or manufacture missing files.

Save validates the destination and source identity, writes and verifies a complete staging output, then publishes. `.wbpj` is a file-plus-directory transaction. Overwrite uses identity-checked backup/restore; if rollback cannot complete, the only surviving recovery output is retained and its exact path is reported. No success is reported before primary and required companions are complete. Source overwrite occurs only when the user explicitly selects the source as destination and enables Overwrite.

The qualified Workbench state comparison is narrowly limited to the unique registered `dp0/act.dat` pair when its working-to-stage SHA is the sole mismatch after ordinary checks. The closed HDF5 schema and complete logical Session data/metadata must match; all other files and all stage-verification/restoration phases remain byte-strict. This proves qualified logical equality, not timestamp-only byte changes.

## Sessions, errors, and limits

Background standalone work runs in a dedicated owner process; Workbench retains its project owner and selected Model server. Each run reloads a run-owned copy of the saved source. Model handles and selectors are bound to run, session, document, revision, generation, and workspace identity; stale, cross-session, or expired values fail before native dereference. Completed tables/images remain viewable observations, not reconnectable live handles.

A successful Interactive window may remain inspection-only after completion. Any next graph run in the same workspace retires every retained Interactive owner before dispatch, even if that run has no Open node. A run in another workspace does not close it. Workspace close, application shutdown, or explicit retirement also closes it. Background success and every failed/cancelled run close their owned processes; unrelated Ansys processes are never killed.

Stable diagnostics include `mechanical.missing_dependency`, `mechanical.release_unsupported`, `mechanical.open_failed`, `mechanical.system_required`, `mechanical.selector_ambiguous`, `mechanical.selector_missing`, `mechanical.stale_reference`, `mechanical.cross_session_reference`, `mechanical.table_unsupported`, `mechanical.results_missing`, `mechanical.search_incomplete`, `mechanical.capacity_exceeded`, `mechanical.operation_failed`, `mechanical.operation_timeout`, `mechanical.restore_failed`, `mechanical.save_failed`, and `mechanical.capability_unproved`.

Declared v1 limits are failures, never silent truncation:

- Open and Script timeout default 600 seconds; accepted range is 1–86,400 seconds.
- Image width/height are each 64–8,192 pixels, with at most 33,554,432 pixels and 256 captures per invocation.
- Script accepts at most 256 analyses; Snippet accepts at most 256 analyses and 256 command objects per invocation.
- Scientific transport allows 256 MiB per value and 512 MiB per codec operation.
- Inline descriptors/selectors allow 1 MiB; Model-handle metadata allows 64 KiB; the private owner control request/response envelope allows 1 MiB.
- An accepted discovery catalogue allows 100,000 rows and 64 MiB encoded content; the selector popup shows at most 50 ranked options. An incomplete suggestion catalogue is labeled incomplete and never limits execution Search.
- The qualified `act.dat` logical comparison allows at most 64 MiB physical/logical state, reads in 1 MiB chunks, and bounds HDF5 comments at 64 KiB.

Cancellation first requests cooperative stop; after five seconds COREX may terminate only that run's recorded owner process tree. Large table/image operations report the requested source, dimensions, or counts with `mechanical.capacity_exceeded`.

## Developer verification and evidence boundary

The registry and documentation contract is checked without Ansys:

```powershell
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_examples.py tests/mechanical_catalogue/test_catalogue.py tests/test_corex_contract_catalog.py tests/test_repo_owned_node_documentation.py -q -n 0
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
```

T17 also closes one runnable-source integration omission from the accepted T16 metadata change: the dependency-free `corex.node` identity decorator now admits the already validated `_default_expanded_settings_group_ids` field. No other private field was admitted, and decorator identity behavior is unchanged. The exact direct-source regression is `tests/mechanical_catalogue/test_catalogue.py::test_registered_function_forwards_unconnected_properties_as_settings`; the complete six-test catalogue lane also exercises worker-registry loading.

The [T01 capability qualification](specs/perf/MECHANICAL_CATALOGUE_CAPABILITY_PROOF.md) records bounded 261 native evidence. The [implementation plan](PLANS/MECHANICAL_CATALOGUE/PLAN.md) and [task ledger](PLANS/MECHANICAL_CATALOGUE/TASK_LEDGER.md) separate accepted task evidence from remaining T18 live integration. These examples and this guide contain neutral COREX material only.
