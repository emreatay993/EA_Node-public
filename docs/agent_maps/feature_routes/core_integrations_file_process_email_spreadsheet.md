# Core Integrations: File, Process, Email, Spreadsheet

## Purpose
Use this for built-in integration nodes, process execution policies, file IO nodes, email nodes, spreadsheet nodes, and integration catalog metadata.

## Start Here
- `ea_node_editor/nodes/builtin_functions/integrations_file_io.py`
- `ea_node_editor/nodes/builtin_functions/filesystem.py`
- `ea_node_editor/nodes/builtin_functions/integrations_process.py`
- `ea_node_editor/nodes/builtin_functions/integrations_email.py`
- `ea_node_editor/nodes/builtin_functions/integrations_spreadsheet.py`
- `ea_node_editor/nodes/builtin_functions/__init__.py`
- `ea_node_editor/nodes/builtins/integrations_common.py`
- `ea_node_editor/nodes/builtins/integrations_file_io.py`
- `ea_node_editor/nodes/builtins/filesystem.py`
- `ea_node_editor/nodes/builtins/integrations_process.py`
- `ea_node_editor/nodes/builtins/process_subprocess_policy.py`
- `ea_node_editor/nodes/builtins/integrations_email.py`
- `ea_node_editor/nodes/builtins/integrations_spreadsheet.py`
- `ea_node_editor/nodes/bootstrap.py`
- `ea_node_editor/nodes/file_dialog_filters.py`
- `tests/test_builtin_integration_function_migration.py`
- `tests/test_filesystem_function_nodes.py`
- `tests/test_filesystem_qml_controls.py`
- `tests/test_integrations_track_f.py`
- `tests/test_process_run_node.py`

## Notes
- The reserved built-in function bundle owns File Read/Write, Image Import/Export, Process Run, Email Send, and Excel Read/Write as eight `PythonFunctionEntry` declarations. Their inert decorator source lives under `nodes/builtin_functions/`; runtime, artifact, cancellation, SMTP, CSV, and optional worker-lazy OpenPyXL behavior stays in the matching trusted `nodes/builtins/` helpers.
- Eight File System nodes are ordinary `PythonFunctionEntry` declarations in `builtin_functions/filesystem.py`; lexical and effect-safe execution remains in `builtins/filesystem.py`. They reuse the shared property-backed ports and QML slider, coded dropdown, and switch controls.
- File Read, Image Import, and Excel Read receive exact registry-owned file-content provenance for `path`; write/effect rows and public lookalikes do not. Provenance failures create execute-only preparation keys rather than cache hits.
- `io.path_pointer` and `io.folder_explorer` are the two retained trusted descriptor exceptions in this route because their passive/native surfaces do not fit ordinary function execution.
- File Read/Write and Excel Read/Write browse filters are declared in their inert path controls. Keep file-type changes in the declaration and shared filter constants, not in shell presenter conditionals.
- Process Run declares its command input mandatory with a same-key property fallback. Email Send declares SMTP host, sender, and recipient settings centrally, and requires a password only when Username is nonblank. Missing configuration waits/yellows before plugin construction; subprocess and SMTP failures remain runtime errors.
- Stored Process Run stdout/stderr form one transactional typed-artifact pair. Reruns replace seeded slots, partial registration rolls back only attempted transcripts, and cleanup failures do not mask the primary process error.
- `process_subprocess_policy.py` remains the shared process allow/deny owner after the old HPC node family is removed; SSH/SFTP uses Paramiko and does not route through this subprocess policy.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_integrations_track_f.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_process_run_node.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_builtin_integration_function_migration.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_filesystem_nodes.py tests/test_filesystem_function_nodes.py --ignore=venv -q
```

## Breadcrumbs
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [SSH/SFTP Nodes](ssh_sftp_nodes.md)

## Update Triggers
Update when integration function declarations, the two trusted file/passive exceptions, path browse filters, readiness metadata, stored process transcript transactions, runtime helpers, or integration tests change.
