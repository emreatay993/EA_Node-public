# Add-on Manager

## Purpose
Use this for add-on catalog metadata, add-on manager shell/QML payloads, dependency display, managed-package installation, and add-on tab behavior.

## Start Here
- `ea_node_editor/addons/contracts.py`
- `ea_node_editor/addons/catalog.py`
- `ea_node_editor/addons/registry_contributions.py`
- `ea_node_editor/addons/state_changes.py`
- `ea_node_editor/ui/shell/controllers/addon_manager_controller.py`
- `ea_node_editor/ui/shell/presenters/addon_manager_presenter.py`
- `ea_node_editor/ui/shell/registry_replacement.py`
- `ea_node_editor/ui/shell/presenters/_addon_manager_payloads.py`
- `ea_node_editor/ui_qml/shell_addon_manager_bridge.py`
- `ea_node_editor/ui_qml/components/shell/AddOnManagerPane.qml`
- `ea_node_editor/execution/managed_runtime.py`
- `tests/main_window_shell/bridge_qml_boundaries.py`
- `tests/test_addon_catalog.py`

## Contracts
- Add-on state and presentation records are add-on-owned. The shell presenter reads them from `addons.catalog`; `nodes.plugin_loader` has no add-on catalog forwarding surface.
- Trusted registry contributions are add-on-owned in `addons.registry_contributions`; public plugin discovery never imports add-on backend contracts.
- Managed package setup has no default five-minute ceiling. The runtime command runner streams its latest phase/output line through the install worker and bridge to `AddOnManagerPane.qml`.
- Add-on setup reports the exact selected COREX Python path. Source runs use the active interpreter; frozen runs use the app-managed AppData interpreter.
- Keep progress transient and bridge-owned: QML displays only the latest line while installation is active, and thread cleanup clears it.
- `addons/state_changes.py` prepares state without I/O or runtime work. `RegistryReplacementCoordinator` alone builds and checks a fresh registry, then holds the shared runtime admission guard through final contract verification, non-normalizing runtime/scene/shell publication, preference persistence, and complete reverse rollback. Notifications occur only after durable success; workers receive the accepted bounded add-on configuration rather than default preferences.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_managed_runtime.py tests/test_addon_catalog.py tests/test_addon_state_changes.py tests/test_addon_manager_install.py tests/test_plugin_loader.py tests/test_registry_replacement.py tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q
```

## Breadcrumbs
- [Add-ons](../subsystems/addons.md)
- [Tabular Data Add-on And Preview](tabular_data_addon_preview.md)
- [MARS Solver Add-on](mars_solver_addon.md)

## Update Triggers
Update when add-on catalog records, dependency/install metadata, asynchronous install behavior, add-on manager payloads, or add-on manager tests change.

## 2026-07-11 Performance Ownership

- `AddOnManagerPane` is a retained URL-backed loader: first open creates it, later opens reuse the same object. Preserve object name, geometry, z-order, focus, and close behavior.
