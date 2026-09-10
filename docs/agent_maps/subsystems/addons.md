# Add-ons

## Purpose

Use this for repo-local add-on discovery, dependency-gated availability, persisted state, registry contributions, property-edit adapters, and Add-On Manager payloads.

## Start Here

- `ea_node_editor/addons/contracts.py`
- `ea_node_editor/addons/catalog.py`
- `ea_node_editor/addons/registry_contributions.py`
- `ea_node_editor/addons/state_changes.py`
- `ea_node_editor/addons/tabular_data/`
- `ea_node_editor/addons/mars/`
- `ea_node_editor/addons/mechanical/`
- `ea_node_editor/addons/mechanical/session.py`
- `ea_node_editor/addons/mechanical/owner_process.py`
- `ea_node_editor/addons/mechanical/backend.py`
- `ea_node_editor/addons/mechanical/commands.py`
- `ea_node_editor/addons/mechanical/graphics.py`
- `ea_node_editor/addons/mechanical/saving.py`
- `ea_node_editor/addons/mechanical/inspection.py`
- `ea_node_editor/addons/mechanical/runtime.py`
- `ea_node_editor/addons/mechanical/workbench.py`
- `scripts/mechanical_catalogue/generate_examples.py`
- `examples/mechanical_*.cxproj`
- `docs/MECHANICAL_CATALOGUE.md`
- `tests/mechanical_catalogue/test_examples.py`
- `ea_node_editor/ui/shell/registry_replacement.py`
- `ea_node_editor/ui/shell/presenters/addon_manager_presenter.py`
- `ea_node_editor/ui_qml/shell_addon_manager_bridge.py`

## Common Changes

- `addons/contracts.py` owns `AddOnState` and `AddOnRecord`; `addons/catalog.py` owns dependency-gated construction and lookup.
- `addons/registry_contributions.py` atomically contributes add-on semantic types, descriptors, and static function bundles. Conflicts reject the complete contribution.
- `addons/state_changes.py` only prepares normalized requested state. `RegistryReplacementCoordinator` owns compatibility checks, registry/service publication, persistence, notification, and rollback.
- The repo catalog contains Tabular Data, MARS, and Mechanical. Mechanical contributes dependency-gated semantic contracts and the real `mechanical.open_model`, `mechanical.search_tree`, `mechanical.fea_table`, `mechanical.camera_views`, `mechanical.export_image`, `mechanical.run_script`, `mechanical.apdl_snippet`, and `mechanical.save_model` declarations.
- Tabular owns seven function declarations, property editing, native preload, compact refs, preview/query behavior, and one shared loader cache service.
- Mechanical property editing resolves immutable accepted Info/Report catalogue tables through each Model locator. It normalizes nullable pandas scalars to Python None before indexing, including unknown omission counts. It caches detached descriptor choices by catalogue identity/revision and never opens a source or resolves the live handle while projecting selectors.
- Mechanical's eight declarations expose 52 typed inputs and 22 outputs through the shared named-settings-group controls. Each declaration expands its primary group on fresh creation and leaves advanced groups collapsed. `tests/mechanical_catalogue/test_controls.py` owns the exact section/order/default/condition inventory; `test_visuals.py` owns production GraphCanvas interactions and font/theme/scale captures without launching Ansys.
- `scripts/mechanical_catalogue/generate_examples.py` owns the three fixed-ID blank-path Mechanical `.cxproj` workflows and derives fresh section expansion from the current registry before normal serializer publication/reload. `docs/MECHANICAL_CATALOGUE.md` owns the user/developer contract; `tests/mechanical_catalogue/test_examples.py` pins its registry-exact ports/groups and each example's invariant-compatible edges without launching Ansys.
- Selected Workbench `.mechdb`/`.mechdat` model-only exports flush and reconnect the source owner around native Model-container Export. A short-lived separate same-release `MechanicalOwnerProcess` alone opens the private `.dsdb`, SaveAs/reopens the standalone stage, verifies tree/geometry/load/selection/snippet/view snapshots, and closes before publication; archive controls remain unconsumed and the returned Model remains Workbench-owned.
- MARS owns three function declarations plus managed-package/toolchain/artifact metadata and JSONL subprocess execution.
- Mechanical contracts and run ownership are isolated in `addons/mechanical/`: `contracts.py` owns transient Model handles and bounded inline/table values, while `session.py` and `owner_process.py` own workspace-identified run sessions, source copies, revision admission, and a dedicated bounded subprocess protocol. On Windows the owner is assigned to a kill-on-close Job Object before backend imports, so worker death cannot orphan the owned process tree.
- Mechanical working copies use native Open/SaveAs or source-family Archive/Unarchive routes; Workbench projects retain their dependency structure. Save uses native standalone or whole-Workbench APIs, verifies a native reopen, restores the admitted working database/project, and publishes the primary plus required companion through one identity-checked rollback transaction. Selectable Mechanical systems are identified from documented `system.Components` membership; Model-less systems are omitted from Model choices but remain present in whole-project system/component/file snapshots. Workbench Save closes only the selected Model container, captures the flushed working project before Save-As, compares documented native file/component/model/design-point semantic snapshots across working/stage/verify/restore boundaries, trusts the native archive flags for their undisclosed skipped-result classification, discards old proxies, reconnects the selected/shared Model, and advances both revision and connection generation. Native 261 qualification establishes that `GetProjectDirectory()` reports the project file's containing directory while `GetUserFilesDirectory()` reports the companion's `user_files` child; inventory therefore keeps the exact primary, companion-relative logical paths, and exact registered external locations as separate identities. When native Unarchive rebases a requested registered external into the verification companion, only its location is normalized and its full name/display/association/existence/size/hash/registration identity stays exact. Native structured data from Open, Script, Snippet, standalone Save, and Workbench inventory/snapshots uses lossless UTF-8 owned files with bounded ASCII size/hash receipts before the existing owner spool/scientific codecs. Run Script preflights Object/Text analysis selectors, executes in native tree order with cleaned injected context, advances the admitted model revision on every attempt, and returns a fresh Report locator only after every invocation succeeds. APDL Snippet defaults to supported Static Structural analyses, preflights all phases/steps/native setters/ownership collisions, and creates or updates deterministic marker-owned command objects with bounded verified rollback.
- Mechanical Search re-reads the admitted current model through the owner process, applies eleven COREX data predicates without native Outline filter calls or table-cell reads, and transfers typed Object/Property lists plus Details through the hashed `mechanical-search-v1` runtime-value spool. FEA Table separately reads actual Field/Variable values, bolt-pretension step states, native ITable columns, configured-result summaries, qualified PlotData/ForceReaction data, and mesh/layered worksheet rows, then publishes immutable scientific tables and Definitions through the same bounded codec contract. Camera Views reads saved names/original indices from direct exported `ModelView` children and returns typed snapshots. Export Image validates complete object/view selections before capture, preserves exact graphics and accepted result-addressing state, returns object-grouped `ImageValue` trees, and optionally publishes one rollback-protected no-clobber PNG batch. Restoration failures retire the native session.
- The Mechanical owner launcher uses module execution in source/dev and the statically allowlisted `--private-mechanical-owner` bootstrap role when frozen.
- Workbench preservation remains byte-strict except for the sole working-to-stage SHA mismatch of the unique registered `dp0/act.dat` pair. `ea_node_editor/addons/mechanical/workbench.py` checks its closed HDF5 Session schema and full logical data/metadata using lazy h5py inside the existing timed owner; byte-zero signature, zero user block, exact native file attestation and bounded reads are mandatory. Unknown schemas fail; archive verification and restore remain byte-strict. `tests/mechanical_catalogue/test_workbench_save.py` owns the real HDF5/adversarial cases, and `ea_node_editor/addons/mechanical/catalog.py` declares the direct dependency without importing it during discovery.
- Repo-owned declarations require authored node keywords and descriptions for every declared port; `tests/test_repo_owned_node_documentation.py` covers the exact 147-row catalog.
- Public plugin loading imports no add-on backend types. Add-on package IDs and apply policy remain private registry facts.

## Focused Verification

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_addon_catalog.py tests/test_addon_state_changes.py tests/test_registry_replacement.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_tabular_function_migration.py tests/test_tabular_addon_catalog.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_mars_function_migration.py tests/test_mars_nodes.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_session_lifecycle.py tests/mechanical_catalogue/test_owner_protocol.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_open_model.py tests/mechanical_catalogue/test_catalogue.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_search_tree.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_definition_tables.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_result_tables.py tests/mechanical_catalogue/test_worksheet_tables.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_camera_views.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_image_export.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_scripts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_snippets.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_standalone_save.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_workbench_save.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_workbench_model_export.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_controls.py tests/mechanical_catalogue/test_visuals.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/mechanical_catalogue/test_examples.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_repo_owned_node_documentation.py --ignore=venv -q
```

## Breadcrumbs

- [Add-on Manager](../feature_routes/addon_manager.md)
- [Tabular Data Add-on And Preview](../feature_routes/tabular_data_addon_preview.md)
- [MARS Solver Add-on](../feature_routes/mars_solver_addon.md)

## Update Triggers

Update when add-on discovery, dependencies, semantic-type/function contributions, persisted state, property edit adapters, Mechanical session ownership/examples/help, Tabular/MARS metadata, or Add-On Manager behavior changes.
