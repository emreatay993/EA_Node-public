# Startup, Bootstrap, And App Lifecycle

## Purpose
Use this for launch path, app lifetime, splash handoff, and startup authority changes.

## Start Here
- `ea_node_editor/bootstrap.py`
- `ea_node_editor/app.py`
- `ea_node_editor/execution/runtime_cli.py`
- `ea_node_editor/ui/shell/composition/` (`bootstrap.py` owns `create_shell_window` and the attach/startup sequence; `factory.py` sequences the per-domain dependency modules)
- `ea_node_editor/ui/shell/window.py`
- `ea_node_editor/ui/splash/opening_screen.py`

## Do Not Start Here
- Root launch scripts unless a task explicitly targets packaging or legacy launch behavior.
- Generated architecture diagrams; regenerate them from documented scripts instead.

## Common Changes
- Preserve `python -m ea_node_editor.bootstrap` as the source/dev launch route.
- Frozen startup recognizes only the private Mechanical owner-child role before Qt/application imports; source owners continue to use the owner module directly.
- Keep startup authority in `bootstrap` and `app`, with shell composition in `ui/shell`.
- Startup still calls session restore during shell bootstrap, but restore should leave the active project empty instead of reopening the last saved project.
- For splash behavior, route through `ui/splash/opening_screen.py` and app handoff code; the splash should keep normal desktop z-order and not force itself above unrelated windows.
- For shell dependency changes, keep `ShellWindowComposition` as the startup contract and use `ShellServices` as the attached dependency aggregate.
- Shell composition creates one `CorexRuntime` with the persistence-owned durable repository factory injected through the execution-owned port. Project install/new/open resets and binds that same store; no shell or persistence cache becomes another scheduler authority.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_main_bootstrap.py tests/test_shell_window_lifecycle.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_shell_isolation_phase.py -k "main_window__lifecycle" --ignore=venv -q -n 0
.\venv\Scripts\python.exe -m pytest tests/test_runtime.py -k "project_solution" -q
.\venv\Scripts\python.exe -m pytest tests/test_runtime_cli.py tests/test_run_script.py -q
```

## Breadcrumbs
- [Shell Startup, QML Context, And Splash](../feature_routes/shell_startup_qml_context_splash.md)
- [UI Shell, Controllers, And Presenters](ui_shell.md)

## Update Triggers
Update this map when launch entry points, app lifetime, splash handoff, shell composition, or bootstrap tests change.

## 2026-05-31 Shell Services Bundle Update

- Bootstrap tests now assert that `ShellWindowComposition` carries `services: ShellServices` and that bootstrap attaches that single services reference before shell startup.

## 2026-06-10 Shell Composition Package Update

- Shell composition is the `ea_node_editor/ui/shell/composition/` package; `ShellWindowComposition` remains the startup contract and `ShellServices` the attached dependency aggregate, re-exported unchanged from the package `__init__`.
- Bootstrap-attach behavior is pinned by `tests/test_main_bootstrap.py` and the isolated lifecycle targets backed by `tests/shell_window_lifecycle_support.py`; the latter patches `composition.controllers._create_shell_execution_client`.

## 2026-06-10 Empty Startup Project Update

- `_run_shell_startup_sequence()` still routes through `host._restore_session()`, but `ProjectSessionLifecycleService.restore_session()` no longer installs the saved `last_session.json` project path on startup. The saved path remains available through Recent Projects and as the comparison baseline for autosave recovery.

## 2026-07-11 Performance Ownership

- `ea_node_editor/app.py` owns side-effect-light imports, explicit pre-QML PyArrow preload, and QML `setSource()` timing. Its packaged function-plugin smoke also invokes the default execution-owned COREX build digest, proving the frozen-executable authority is available before worker use. Process-wall and shell-create timings are separate evidence; do not use one as the other's relative baseline.
