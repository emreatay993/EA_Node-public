# MARS Solver Add-on

## Purpose
Use this for the `mars.corex` add-on, managed MARS installation, guided MARS nodes, JSONL process execution, and MARS result artifacts.

## Start Here
- `ea_node_editor/addons/mars/catalog.py`
- `ea_node_editor/addons/mars/function_nodes.py`
- `ea_node_editor/addons/mars/nodes.py`
- `ea_node_editor/addons/mars/runtime.py`
- `ea_node_editor/addons/mars/icons/mars_icon_64.png`
- `ea_node_editor/execution/managed_runtime.py`
- `runtime/runtime_manifest.json`
- `ea_node_editor/ui_qml/shell_addon_manager_bridge.py`
- `docs/MARS_ADDON.md`

## Contracts
- COREX owns static declarations, add-on registration, installation, scratch paths, subprocess lifecycle, and artifact registration.
- MARS owns the `mars-modal-response-solver` wheel, `MARSBatch`, schema-v1 jobs, JSONL events/results, and numerical execution.
- Desktop and worker processes do not import `mars_solver`; generated functions delegate to COREX-owned helpers that launch the absolute console script beside the selected COREX Python.
- Source COREX installs only editable MARS with `--no-deps` into `sys.executable`; it does not create a venv, upgrade pip, reinstall COREX, or touch the retained AppData runtime.
- Frozen COREX keeps the app-managed AppData venv, installs contained COREX and MARS wheels, and applies `--no-deps` only to MARS.
- Workflow Settings keeps its separate `prepare_managed_runtime()` behavior; MARS installation routes through `prepare_addon_runtime()`.
- External workflow workers inherit the desktop-selected add-on Python path, so a configured Workflow Settings interpreter does not redirect MARSBatch lookup.
- Managed package setup has no default five-minute ceiling; pip output is streamed through the Add-On Manager bridge so long installs remain visibly active.
- The three MARS function declarations use the add-on-owned `icons/mars_icon_64.png`; registry entries retain package provenance for this asset while worker function references remain immutable-generation backed.
- `mars.batch_solve`, `mars.time_history`, and `mars.run_job` are one lazy `mars.corex` function bundle. Disabled or dependency-unavailable states publish no entries or bundle, while manager discovery reads the three declared IDs without loading source.
- Guided MARS file inputs use explicit same-key property fallbacks; Batch Solve requires Modal Coordinates and conditionally requires fatigue `A` and `m` only when Damage output is enabled. Run Job's job path uses the same override rule. Missing prerequisites wait with warnings before `MARSBatch` is resolved or launched; invalid supplied values, nonexistent paths, protocol errors, and solver failures stay fatal.
- Published MARS results are typed `COREX.DataTypes.Path` artifact refs. File suffixes provide lowercase formats, the results directory uses explicit `mars_results`, and carrier/store metadata is bounded labels/counts only; the artifact store owns path resolution while the contained result manifest owns the complete file inventory.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_mars_function_migration.py tests/test_mars_nodes.py tests/test_registry_replacement.py tests/test_managed_runtime.py tests/test_addon_manager_install.py tests/test_packaging_configuration.py --ignore=venv -q
```

## Breadcrumbs
- [Add-ons](../subsystems/addons.md)
- [Add-on Manager](addon_manager.md)
- [Core Integrations: File, Process, Email, Spreadsheet](core_integrations_file_process_email_spreadsheet.md)
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)

## Update Triggers
Update when MARS node ports/properties/readiness rules/icons, managed package manifests, MARSBatch protocol handling, Add-On Manager installation, result artifact mapping, or packaged wheel behavior changes.
