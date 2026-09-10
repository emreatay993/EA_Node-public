# Shell Isolation Tests

## Purpose
Use this for shell-backed workflows that need process isolation, shell target catalogs, and main-window shell test routing.

## Start Here
- `tests/test_shell_isolation_phase.py`
- `tests/shell_isolation_runtime.py`
- `tests/main_window_shell/`
- `tests/test_shell_window_lifecycle_isolated.py`
- `tests/shell_window_lifecycle_support.py`
- `scripts/verification_manifest.py`

## Common Changes
- Add shell-backed targets to manifest-owned shell isolation catalogs.
- T25 owns an exact retained target-ID set without a target-count assertion: six lifecycle groups, one visible-recovery lifecycle scenario, and 42 other integration targets (28 main-window plus 14 script/project targets). Direct bridge, frame-rate, mutation-effect, run-event, and recent-project tests collect outside shell isolation; real composition/context, native parenting, repeated mount/close, project reset/timer cancellation, fullscreen/media handoff, viewer reparent/restore, and deterministic teardown remain grouped in serial child commands.
- Keep catalog IDs unique and pairwise disjoint. Every pytest child command includes `-n 0`; the outer full shell-isolation phase remains capped at four workers and each target keeps the manifest-owned 360-second hard child timeout.
- `MainWindowShellTestBase` owns shared full-shell QML traversal and Inspector lookup. Image and PDF subclasses retain ownership of their QML reference lists and teardown.
- PDF tests use `SharedMainWindowShellTestBase` to own shell reuse within each existing isolated child; the two manifest-owned child processes remain the process-isolation boundaries that scope that reuse.
- Keep catalog-owned Media Panel and graph-host targets free of nested subprocess proxy classes and `load_tests` wrappers.
- Graph cursor/style mutation behavior belongs in `tests/test_graph_canvas_host_presenter.py` and `tests/test_passive_style_presets.py`; shell-isolated passive-style coverage retains only the real QML graph-action route/render smoke.
- Keep shell-isolated direct `unittest` commands as focused manual reruns only.
- Prefer `run_verification.py --mode full` for release confidence when shell-backed behavior changes.
- For shell composition changes, keep `tests/test_main_bootstrap.py`, `tests/test_main_window_shell.py`, and `tests/test_shell_window_lifecycle_isolated.py` aligned with the direct `ShellWindow()` and `create_shell_window()` paths. `tests/test_shell_window_lifecycle.py` is the windowless policy wrapper.
- Selected-node inspector link action contracts live in `tests/main_window_shell/`; add shell-isolation catalog entries only if future link tests require isolated shell startup.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_shell_isolation_phase.py --ignore=venv -q
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run
```

## Update Triggers
Update when shell target catalogs, shell runtime helpers, or shell-backed test ownership changes.

## 2026-05-31 Shell Services Bundle Update

- P02 service-bundle coverage lives in `tests/test_main_bootstrap.py`, the lifecycle identity target, and the direct `tests/main_window_shell/test_bridge_contracts.py` / `test_qml_shell_roots.py` modules. These tests assert `window.shell_services`, stable QML context registration, and direct/factory shell lifecycle behavior.

## 2026-05-31 Shell Facade Retirement Update

- P03 coverage in `tests/test_main_bootstrap.py` and `tests/test_main_window_shell.py` asserts that `window_state_helpers.py`, `SHELL_WINDOW_FACADE_BINDINGS`, `WINDOW_STATE_FACADE_BINDINGS`, and `locals().update(...)` class mutation stay retired.

## 2026-06-10 Shell Composition Package Update

- `tests/test_main_window_shell.py` and `tests/test_graph_action_contracts.py` now pin the QML graph-action `request_*` slots to the `window_state.workspace_graph_actions` mixin class body (controller dispatch unchanged), and `tests/test_main_bootstrap.py` asserts controllers/presenters receive the `ShellWindow` directly with no host-adapter layer.
- The shared shell harness (`tests/main_window_shell/base.py`, `tests/shell_window_lifecycle_support.py`) patches `ea_node_editor.ui.shell.composition.controllers._create_shell_execution_client`; bootstrap-internal patch targets live on `ea_node_editor.ui.shell.composition.bootstrap`.

## 2026-05-31 Mutation UI Effects Update

- `tests/test_mutation_ui_effects.py` collects the existing direct mutation-effect checks without constructing a shell.
