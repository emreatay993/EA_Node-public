# COREX Novice Function Plugin SDK QA Matrix

- Updated: `2026-09-07`
- Plan: `docs/PLAN_COREX_NOVICE_PLUGIN_SDK.md`
- Release status: pre-release; removal-closeout gates below must be rerun before making a new acceptance claim.

## Locked Scope

Public source is parsed statically, copied into immutable content-addressed generations, and imported only by an attested process worker. Deterministic schema-2 packages and guarded registry replacement are in scope. Compatibility aliases, schema-1 public packages, dependency installation, file watchers, per-plugin interpreters, and a plugin-selectable external runner remain absent.

Custom Workflows remain copied graph snapshots, and Python Script keeps its persisted source property. No public plugin source path, bytes, digest, package manifest, generation record, or callable identity enters project persistence.

## Current Inventory

| Claim | Exact value | Proof owner |
| --- | ---: | --- |
| Public API | 17 public `corex` exports | `corex.__all__`, `tests/test_architecture_boundaries.py` |
| Migration inventory | 139 classified type IDs | `docs/specs/requirements/COREX_NOVICE_PLUGIN_SDK_MIGRATION_INVENTORY.md`, `tests/test_corex_contract_catalog.py` |
| Function conversion | 78 converted type IDs | 76 reserved built-in function entries plus 7 Tabular and 3 MARS entries |
| Trusted boundary | 53 trusted internal exceptions | migration inventory and `tests/test_remaining_builtin_function_migration.py` |
| Current catalog | 139 repo-owned rows | `tests/fixtures/node_catalog/current_repo_owned_catalog.json` |
| Model Viewer default | `surface_with_edges` | `tests/test_corex_contract_catalog.py` |

The exact public export order is `node`, `input`, `output`, `text`, `text_area`, `number`, `switch`, `dropdown`, `slider`, `color`, `path`, `interval`, `list`, `Any`, `Image`, `Color`, `Interval`.

## Public Documentation And Examples

| Artifact | Current role |
| --- | --- |
| `docs/PLUGIN_AUTHORING_GUIDE.md` | Novice loose-file tutorial, exact decorators/signature/settings/outputs/warnings, schema-2 package and reload workflow. |
| `docs/PLUGIN_MIGRATION_GUIDE.md` | Clean-break migration from class/descriptor plugins and explicit unsupported schema-1 message. |
| `docs/PYTHON_SCRIPT_GUIDE.md` | Distinguishes persisted workflow-local Python Script from reusable plugins. |
| `docs/examples/signal_plot_function_plugin.py` | Public function-only Signal Plot example. |
| `docs/examples/strain_conditioner_plugin.py` | Public function-only Strain Conditioner example. |

## Focused Closeout Results

| Command | Result |
| --- | --- |
| `.\venv\Scripts\python.exe -m pytest tests/test_novice_plugin_sdk_docs.py tests/test_repo_owned_node_documentation.py tests/test_corex_contract_catalog.py tests/test_node_title_icon_assets.py tests/test_builtin_function_migration.py tests/test_remaining_builtin_function_migration.py tests/test_architecture_boundaries.py tests/test_dead_code_hygiene.py --ignore=venv -q` | `NOT RUN` |
| `.\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_agent_route_index.py tests/test_source_test_file_index.py tests/test_qml_navigation_index.py --ignore=venv -q` | `NOT RUN` |

## Pending Acceptance Gates

| Gate | Command / Review | Result |
| --- | --- | --- |
| Full summarized verification | `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --summarize-output` | `PENDING / NOT RUN` |
| Clean base Windows package | `.\scripts\build_windows_package.ps1 -PackageProfile base -Clean` | `PENDING / NOT RUN` |
| Independent final diff/evidence review | Independent read-only review after generated outputs and acceptance commands | `PENDING / NOT RUN` |

## Residual Boundaries

- The bundled COREX runtime is the only plugin execution environment. A plugin-selectable external runner, per-plugin interpreter, dependency installer, watcher, marketplace, and generated typing surface remain unimplemented.
- The existing workflow-level external Python setting remains separate and unchanged.
