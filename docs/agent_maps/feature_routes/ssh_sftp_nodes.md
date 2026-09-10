# SSH/SFTP Nodes

## Purpose
Use this for the six built-in Control > SSH/SFTP nodes, protected credentials, Paramiko execution and transfer behavior, and the shared sensitive-property authoring path.

## Lookup Aliases
- `SSH SFTP`
- `SecretData`
- `SshSftpHostData`
- `DPAPI secret`
- `known_hosts`
- `Paramiko`

## Start Here
- `ea_node_editor/nodes/builtin_functions/integrations_ssh_sftp.py`
- `ea_node_editor/nodes/builtins/integrations_ssh_sftp.py`
- `ea_node_editor/nodes/builtins/ssh_sftp_values.py`
- `ea_node_editor/nodes/builtins/ssh_sftp_runtime.py`
- `ea_node_editor/nodes/builtin_functions/__init__.py`
- `ea_node_editor/nodes/bootstrap.py`
- `ea_node_editor/common/protected_values.py`
- `ea_node_editor/runtime_contracts/value_codec.py`
- `ea_node_editor/nodes/node_specs.py`
- `ea_node_editor/nodes/registry.py`
- `ea_node_editor/ui_qml/components/common/SecretEditor.qml`
- `ea_node_editor/ui_qml/graph_scene_mutation/selection_and_scope_ops.py`
- `tests/test_ssh_sftp_node_contracts.py`
- `tests/test_ssh_sftp_runtime.py`
- `tests/test_protected_values.py`
- `tests/test_sensitive_property_controls.py`

## Do Not Start Here
- COREX's `HPC` keywords: they are search metadata on connector nodes, not active COREX HPC nodes.
- `ea_node_editor/nodes/builtins/process_subprocess_policy.py`: it remains owned by the core process-integration route.
- Persistence migrations when adding a current SSH/SFTP node; the only retained HPC identifier is the historical `hpc.on_status` migration tombstone.

## Common Changes
- Keep the family fixed at Secret, SSH/SFTP Host, Run SSH Command, Run SSH Script, SFTP Upload, and SFTP Download. All six are inert declarations in `nodes/builtin_functions/integrations_ssh_sftp.py`, registered in the reserved bundle as `PythonFunctionEntry` records; port order, labels, types, access, descriptions, properties, category, and keywords stay there.
- D042 records exactly two production types under `corex.ssh_sftp`: `SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SecretData` and `SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SshSftpHostData`. Both are native opaque tagged values, use `persistence="never"`, and are `transport_ready` in the crosswalk. Their Paramiko-free contracts live in `integrations_ssh_sftp.py`, tagged value construction/validation lives in `ssh_sftp_values.py`, and `bootstrap.py` registers those contracts before the reserved function bundle without SSH node descriptors.
- `protected_values.py` owns DPAPI CurrentUser/LocalMachine envelopes. Plaintext enters only the dedicated replace command, is protected before graph mutation/history, and is never projected into QML. Non-Windows protection/decryption fails closed.
- `PropertySpec.sensitive`, `sensitive_scope_key`, and the `secret` editor kind are generic metadata. Scene and Inspector payloads expose only redacted public state; both UIs reuse `SecretEditor.qml` and the graph-owned replace/clear/reprotect mutation path.
- Secret and SSH Host runtime markers are unavailable in previews before any key or value is stringified, including nested containers and hostile non-string keys. Panel display rows and Copy/Copy as tree reuse the same callback-free projection; ciphertext, address, username, key path, and marker details never enter QML or clipboard text.
- Runtime `secret_data` and `ssh_sftp_host_data` values are immutable-by-convention tagged mappings, not live sessions. `runtime_contracts/value_codec.py` preserves these opaque mappings through worker serialization; operation functions import `ssh_sftp_runtime.py` only when executed, and that lazy runtime decrypts credentials only while creating a fresh Paramiko client.
- Connections load system OpenSSH known-hosts and reject unknown or changed host keys. Command/script execution uses bounded capture, cancellation callbacks, and warnings for nonzero exits; script staging uses a unique protected remote directory with cleanup.
- Public runtime failures use fixed path-free messages for local path probes, credential decode, known-host loading, client/agent setup, connect/transport failures, and cleanup. Cause/context chaining is suppressed so Paramiko, DPAPI, filesystem, host, user, and key-path details do not escape; client/SFTP close remains best-effort and does not replace the primary failure.
- Upload/download reuse one SFTP session per node execution, recurse through directory contents, skip symlinks with warnings, contain local targets, and commit files atomically. Multiple sources require a directory destination.
- `ssh_sftp.secret` persists only the DPAPI envelope in ordinary node properties. Current project and fragment formats need no new schema; preserve the existing `hpc.on_status` tombstone only for immediate-predecessor migration.
- Paramiko is a required base dependency and is collected for every Windows package profile with its metadata and license notice. SSH/SFTP title icons live under `ea_node_editor/assets/node_title_icons/ssh_sftp/`; the former HPC icon directory is retired.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_ssh_sftp_node_contracts.py::test_ssh_sftp_runtime_type_contracts_and_process_transport_are_exact --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_ssh_sftp_node_contracts.py tests/test_ssh_sftp_runtime.py tests/test_protected_values.py tests/test_sensitive_property_controls.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_builtin_integration_function_migration.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py tests/test_dataflow_graph_persistence.py tests/test_repo_owned_node_documentation.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_node_title_icon_assets.py tests/test_packaging_configuration.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_catalog_generator.py::test_current_unsupported_addin_source_node_policy_is_exact --ignore=venv -q
```


For the shared QML editor, run the repository Qt Quick Test phase or target `tests/qml_quick/tst_secret_editor.qml` with `qmltestrunner`.

## Breadcrumbs
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [Surface Input And Inline Controls](surface_input_and_inline_controls.md)
- [QML Bridge Wiring](qml_bridge_wiring.md)
- [Packaging And Generated Assets](../subsystems/packaging_generated_assets.md)
- [Node Title Icons And Theme Sources](node_title_icons_theme_sources.md)
- [Core Integrations: File, Process, Email, Spreadsheet](core_integrations_file_process_email_spreadsheet.md)

## Update Triggers
Update when SSH/SFTP function declarations, Paramiko-free contracts/tagged values, lazy Paramiko connection/command/script/transfer behavior, protected-value envelopes, fixed public error/redaction behavior, sensitive-property projection or commands, retained HPC migration handling, dependencies, packaging, icons, or focused tests change.
