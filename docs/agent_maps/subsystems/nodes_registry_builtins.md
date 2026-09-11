# Nodes, Registry, Built-ins, And Plugin Loading

## Purpose
Use this for node definitions, registry validation, built-in node families, data-type contracts, packages, and plugin loading.

## Lookup Aliases
- `node registry builtins`

## Start Here
- `corex/__init__.py`
- `ea_node_editor/nodes/bootstrap.py`
- `ea_node_editor/nodes/registry.py`
- `ea_node_editor/nodes/node_specs.py`
- `ea_node_editor/nodes/core_data_types.py`
- `ea_node_editor/nodes/spec_validation.py`
- `ea_node_editor/nodes/property_coercion.py`
- `ea_node_editor/nodes/property_normalization.py`
- `ea_node_editor/nodes/instance_resolution.py`
- `ea_node_editor/nodes/declaration_engine.py`
- `ea_node_editor/nodes/function_plugin.py`
- `ea_node_editor/nodes/function_bundle.py`
- `ea_node_editor/nodes/builtin_catalog.py`
- `ea_node_editor/nodes/plugin_declaration.py`
- `ea_node_editor/nodes/package_schema.py`
- `ea_node_editor/nodes/plugin_generation.py`
- `ea_node_editor/nodes/python_script_declaration.py`
- `ea_node_editor/nodes/execution_context.py`
- `ea_node_editor/nodes/plugin_contracts.py`
- `ea_node_editor/nodes/plugin_loader.py`
- `ea_node_editor/nodes/package_manager.py`
- `ea_node_editor/nodes/plugin_authoring.py`
- `ea_node_editor/common/path_safety.py`
- `ea_node_editor/nodes/builtin_functions/`
- `ea_node_editor/nodes/builtins/`
- `ea_node_editor/runtime_contracts/data_types.py`
- `docs/PLAN_COREX_NOVICE_PLUGIN_SDK.md`
- `docs/PLUGIN_AUTHORING_GUIDE.md`
- `docs/PLUGIN_MIGRATION_GUIDE.md`
- `docs/examples/signal_plot_function_plugin.py`
- `docs/examples/strain_conditioner_plugin.py`
- `docs/specs/requirements/COREX_NOVICE_PLUGIN_SDK_MIGRATION_INVENTORY.md`
- `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`
- `docs/specs/perf/COREX_SOLUTION_REUSE_CLASSIFICATION.md`

## Built-in Contract Families
- Core values and media contracts: `core_values.py` and `core_media.py`; ordinary converted execution source lives as inert strings under `builtin_functions/`.
- Geometry and spatial contracts/helpers: `geometry_contracts.py`, `geometry_primitives.py`, and `spatial_values.py`; ordinary execution declarations live in `builtin_functions/{spatial.py,engineering_geometry.py}`.
- Engineering contracts/helpers: `mesh_contracts.py`, `fem_contracts.py`, `engineering_imports.py`, `engineering_viewer.py`, and `voxel_contracts.py`; ordinary declarations live in `builtin_functions/{engineering_fem.py,engineering_imports.py,engineering_viewer.py}`.
- Support contracts/helpers: `tree_path.py`, `units.py`, `viewer_viewport.py`, `security_contracts.py`, `reporting.py`, `rich_value_nodes.py`, and `ai_ml_contracts.py`; their converted declarations live in the matching `builtin_functions/` modules.
- Signal Plot declaration/execution is owned by inert `builtin_functions/plot_signal.py`; rendering remains in `execution/signal_plot_renderer.py` and emits `COREX.DataTypes.Image`.
- `core_data_types.py` registers concrete scientific ArrayValue/TableValue/SeriesValue IDs. `builtins/core.py` and `function_plugin.py` adapt immutable runtime values to isolated native NumPy/pandas inputs and snapshot native outputs. These are item values, independent of outer Item/List/Tree access.
- `ea_node_editor/nodes/builtins/plot/signal_schema.py` owns metadata-only scientific column suggestions; its shared property adapter preserves exact string/int selectors and uses the ordinary enum/list QML controls.
- Public function plugins use the dependency-free top-level `corex` decorators and static `plugin_declaration.py` discovery. Both public plugins and Python Script require explicit `value_type=` on every input/output decorator; missing types fail at their source location, and deliberate broad ports use `corex.Any`. Python Script keeps its one-`run` signature while sharing only the bounded literal/control engine.
- `PortSpec.type_from_input` and public/Python Script `@corex.output(..., type_from_input="input")` declare an Any data output following an Any input with the same access structure. `instance_resolution.py` validates static and resolved relationships; parsers retain source-located errors, and registry fingerprints include the declaration. Panel, Trigger, and all Stream Gate outputs opt in; Stream Gate follows Stream, never its Gate selector. Graph inference belongs to `graph/type_forwarding.py`, separate from declared input/runtime contracts.
- Core metadata narrows Constant/File Write data to JsonValue, Force output to Force, and eight generic plot exports to Plot Export Bundle. `tests/test_corex_contract_catalog.py` pins exactly 20 intentional repo-owned Any endpoints across primary and accepted declarations, including three MARS artifact maps, and rejects primary-type repetition in accepted alternatives. `tests/repo_owned_catalog_fixture.py` loads the exact current catalog.
- `corex.__all__` is the exact 17-name public SDK. `ea_node_editor.nodes` exports
  no authoring helpers, `nodes/types.py` is deleted, and `nodes/decorators.py`,
  `NodePlugin`, `PluginDescriptor`, `node_type`, and `PLUGIN_BACKENDS` remain
  trusted implementation details only. The loader discovers public code only
  from explicitly configured loose/schema-2 paths through static parsing; it has
  no entry-point, class-probe, executable-manifest, or descriptor-discovery path.
- `function_bundle.py` owns shared in-memory preparation/materialization and registry-aware fingerprint inputs without filesystem discovery, add-on availability policy, reserved-owner decisions, or registry publication. `plugin_loader.py` owns public loose/schema-2 filesystem discovery and public function publication.
- `builtin_catalog.py` owns the 17-entry built-in contract contribution table, the two explicit `replace_owner` exceptions, trusted descriptors, reserved declaration permission, `None` provenance, and trusted registration for the internal owner `corex:builtin:functions`. GUI bootstrap registers exactly 76 `PythonFunctionEntry` records: 68 historical built-in conversions plus eight post-baseline native File System functions, while workers independently attest and lazily execute them. The migration inventory still includes ten converted add-on functions and separately tracks the eight native functions. The remaining 53 built-ins are its exact trusted exceptions, including Python Script, Trigger, Stream Gate, subnodes, three FEM pool/setup nodes, passive/custom surfaces, active Media Panel, and generated private families.
- The complete private boundary is the 53 trusted exceptions and two shipped
  add-on catalogs. Public authors never use those
  descriptor/backend records.
- `TrustedFactoryEntry` and `PythonFunctionEntry` are the mutually exclusive private registry implementations. Public function entries store only `PythonFunctionRef`; process workers re-hash the immutable generation and use `PythonFunctionAdapter` without exposing a callable to GUI discovery.
- `spec_validation.py` purely validates node, property/default, readiness, group, source-metadata, and data-type-reference structure against the explicit catalog it receives. `instance_resolution.py` directly owns port validation, instance-spec resolution, dynamic-group resolution, and resolved ports without importing registry or specification validation; graph, execution, UI, registry, and tests import it directly. `property_coercion.py` is the dependency-light scalar/carrier coercion primitive shared by validation, resolution, and normalization. `property_normalization.py` owns the generic default/coercion traversal, dynamic backing-property rewrite, and Select/Number Slider/Web policy. `registry.py` retains entry/catalog storage, staged catalog composition, atomic owner replacement/rollback, freeze/fingerprints, registry-aware `resolve_spec`, and the three intentional catalog-aware property API entry points; every staged surviving and new entry is revalidated before commit.
- `NodeTypeSpec.solution_reuse_scope` is the internal fail-closed `never|session|durable` maximum. Every normal/untrusted function registration is locked to `never` regardless of type-ID prefix; broader scopes enter only through the attested internal built-in or shipped Tabular package construction paths. Every trusted factory remains `never`. The locked classification artifact is the row authority; the effective catalog fixture layers it after the frozen 133-row fixture instead of editing that fixture.
- `nodes/solution_provenance.py` is the registry-owned typed overlay for the six accepted shipped session readers. It adds exact `path` file provenance only for the trusted built-in/tabular owners; declarations, public packages, and trusted factories cannot supply or imitate this metadata.
- `NodeRegistry.execution_environment_facts()` projects deterministic active add-on, plugin-bundle, toolchain, and Python-package requirements for the concrete execution-route handshake; it contains no mutable source/install paths.
- `package_schema.py` is the single pure policy owner for schema-2 fields, member paths, sizes, hashes, node inventory, icon declarations, and canonical manifest bytes. Discovery, archive import, installed-directory activation, immutable-generation reads, and workers still perform their own bounded reads and digest checks at each trust boundary.
- Public loose files and installed schema-2 directories are parsed without import, checked for bundled imports, and copied byte-for-byte into `runtime/plugin_generations/<bundle-digest>/`; registry fingerprints exclude author/install paths. Worker registry construction reparses only the verified generation and never the mutable discovery roots.
- `build_plugin_candidate_registry(...)` builds fail-closed candidates into a caller-owned disposable generation root; one staged schema-2 package may replace only the installed package with the same exact name. Candidate and canonical registries must have the same full `NodeRegistry.contract_fingerprint()` before publication.
- `NodeRegistry` owns entry/spec/catalog storage and resolution, not presentation queries. Library filtering, category ancestors/options/tree, and custom-workflow discoverability live only in the existing UI Library projection/presenter owner; do not recreate `filter_nodes`, `category_paths`, or `categories`.
- `.cxpkg` import/export accepts schema 2 only. `package_manager.py` applies the shared static directory/declaration checks, exact source/asset hashes, Windows-safe paths and documented size/member limits; the 128-file ceiling includes `node_package.json`, and filesystem members must be singly linked regular files. ZIP exports use canonical manifest JSON, sorted members, fixed timestamps, and stored bytes for deterministic output. `PackageInstallTransaction` separates stage, reversible activation, commit, and retryable rollback; unresolved cleanup/restore work is exposed only as bounded issue codes.
- Package node icons must name declared `.svg`/`.png`/`.jpg`/`.jpeg` assets. Function entries expose private provenance rooted at the immutable validated generation, so title-icon projection never reopens mutable installed assets. Loose files cannot claim custom assets.
- `plugin_authoring.py` owns one-time readable/random identities, novice templates, non-executing temporary validation, structured summaries, direct-child no-clobber saves, expected-content overwrites, and attested saved-draft reads. It has no watcher, installer, environment selection, or legacy descriptor path.
- Python Script decorators resolve one applied source into ordinary ports,
  properties, and settings groups through the registry's instance-spec path.
  Its input/output dynamic groups reference those resolved plain ports and use
  the trusted `property_editor` callback to edit source spans and input parameters.
  They never normalize source into JSON name lists; default-backed controls stay static.
- `NodeTypeSpec.default_expanded_settings_group_ids` declares fresh type-creation defaults in settings-group declaration order. Normal scene creation applies them once; persisted, pasted, duplicated, and loaded `expanded_settings_group_ids` remain authored state and are not replaced by defaults.
- Model Viewer reuses the existing dynamic input group with an exact trusted
  function-spec overlay. Ordered scene IDs and per-ID styles are ordinary hidden
  properties; the function adapter reads resolved inputs from ExecutionContext.
  Only the two approved Model Viewer callbacks receive deterministic private
  function fingerprint serialization; public plugin callback rejection remains.

## Boundaries
- Register built-ins through `build_builtin_registry()`; do not mutate catalog internals.
- Keep `corex/` dependency-free and normalize its static declarations into the existing registry/presentation model; do not import public plugin source in GUI discovery.
- Keep public function entries non-constructible through `NodeRegistry.create()` so trusted in-process execution cannot acquire their callable.
- Keep generation pruning explicit and protect both active and externally referenced digests; never overwrite a mismatched existing digest directory.
- Keep package archives free of compatibility fields, dependency installers, descriptor overrides, nested Python packages, and executable validation hooks. Schema-1 rejection uses the migration pointer in `SCHEMA_1_UNSUPPORTED_MESSAGE`.
- Preserve the exact 147-row repo-owned catalog in `tests/fixtures/node_catalog/current_repo_owned_catalog.json`. The Model Viewer representation default is `surface_with_edges`, and the earlier migration inventory tracks 78 conversions, eight native functions, and 53 internal exceptions.
- Keep canonical data-type IDs under the `COREX.*` namespace.
- Keep source-product provenance, import adapters, comparison studies, and installed-product evidence outside the tracked repository.
- Add no compatibility alias for removed internal contracts unless an active public format requires it.

## Focused Tests
- `tests/test_registry_validation.py`
- `tests/test_spec_validation.py`
- `tests/test_property_coercion.py`
- `tests/test_property_normalization.py`
- `tests/test_plugin_declaration.py`
- `tests/test_function_plugin.py`
- `tests/test_plugin_loader.py`
- `tests/test_function_bundle.py`
- `tests/test_addon_catalog.py`
- `tests/test_plugin_worker_loading.py`
- `tests/test_package_manager.py`
- `tests/test_node_package_io_ops.py`
- `tests/test_plugin_authoring.py`
- `tests/test_builtin_function_infrastructure.py`
- `tests/test_builtin_function_migration.py`
- `tests/test_remaining_builtin_function_migration.py`
- `tests/test_corex_contract_catalog.py`
- `tests/test_solution_identity.py`
- `tests/test_solution_store_session.py`
- `tests/test_corex_type_conformance.py`
- `tests/test_type_forwarding_declarations.py`
- `tests/test_type_forwarding.py`
- `tests/test_core_value_types.py`
- `tests/test_spatial_values.py`
- `tests/test_geometry_contracts.py`
- `tests/test_mesh_contracts.py`
- `tests/test_fem_contracts.py`
- `tests/test_signal_plot_renderer.py`
- `tests/test_python_script_declaration.py`
- `tests/test_dead_code_hygiene.py`
- `tests/test_architecture_boundaries.py`
- `tests/test_packaging_configuration.py`
- `tests/test_novice_plugin_sdk_docs.py`
- `tests/repo_owned_catalog_fixture.py`
- `tests/fixtures/node_catalog/current_repo_owned_catalog.json`
- `tests/test_repo_owned_node_documentation.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_plugin_declaration.py tests/test_function_plugin.py tests/test_function_bundle.py tests/test_property_coercion.py tests/test_property_normalization.py tests/test_spec_validation.py tests/test_registry_validation.py tests/test_plugin_loader.py tests/test_package_manager.py tests/test_addon_catalog.py tests/test_corex_contract_catalog.py tests/test_corex_type_conformance.py tests/test_python_script_declaration.py -q
.\venv\Scripts\python.exe -m pytest tests/test_plugin_authoring.py tests/test_plugin_authoring_controller.py tests/test_plugin_authoring_dialog.py -q
.\venv\Scripts\python.exe -m pytest tests/test_builtin_function_infrastructure.py tests/test_builtin_function_migration.py tests/test_remaining_builtin_function_migration.py tests/test_corex_contract_catalog.py tests/test_core_unit_nodes.py tests/test_spatial_values.py -q
.\venv\Scripts\python.exe -m pytest tests/test_novice_plugin_sdk_docs.py tests/test_repo_owned_node_documentation.py -q
```
