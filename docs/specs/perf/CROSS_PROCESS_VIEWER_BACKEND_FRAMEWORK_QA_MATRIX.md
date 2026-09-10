# Cross-Process Viewer Backend Framework QA Matrix

- Updated: `2026-09-07`
- Scope: current generic execution-side viewer contract, engineering scene transport, shell host/binder framework, rerun-required reopen projection, and documentation traceability.

## Locked Scope

- The worker owns prepared scenes and the UI owns native widgets; raw PyVista, VTK, OCP, and other native scene objects do not cross the worker/UI boundary.
- Execution publishes `backend_id`, typed `transport`, `transport_revision`, and explicit live-open status or blocker fields through `ViewerSessionService`.
- The shell hosts `model.viewer` through `ViewerHostService`, `ViewerWidgetBinderRegistry`, and the engineering viewer binder.
- Saved projects retain projection-safe summary state only. Reopen or reset remains blocked until rerun recreates live transport.

## Current Automated Verification

| Coverage Area | Requirement Anchors | Command | Status |
|---|---|---|---|
| Queue-safe protocol and viewer service | `REQ-ARCH-016`, `REQ-EXEC-013` | `.\venv\Scripts\python.exe -m pytest tests/test_execution_viewer_protocol.py tests/test_execution_viewer_service.py tests/test_process_client.py --ignore=venv -q` | `NOT RUN` |
| Engineering backend and binder | `REQ-ARCH-016`, `REQ-UI-032` | `.\venv\Scripts\python.exe -m pytest tests/test_engineering_viewer_backend.py tests/test_engineering_viewer_node.py tests/test_engineering_viewer_widget_binder.py --ignore=venv -q` | `NOT RUN` |
| Shell host, bridge, and surface projection | `REQ-UI-032`, `REQ-NODE-026` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_viewer_host_service.py tests/test_viewer_session_bridge.py tests/test_viewer_surface_contract.py tests/test_viewer_surface_host.py --ignore=venv -q` | `NOT RUN` |
| Project reopen and rerun intent | `REQ-PERSIST-020`, `REQ-QA-023` | `.\venv\Scripts\python.exe -m pytest tests/test_project_session_controller_unit.py tests/test_shell_project_session_controller.py tests/test_shell_run_controller.py --ignore=venv -q` | `NOT RUN` |

## Manual Desktop Checks

1. Run a `model.viewer` workspace, activate its inline native viewer, and verify fullscreen/detached transitions reuse the same widget.
2. Save and reopen the project without rerunning; verify projection-safe summary state remains and live open reports rerun required.
3. Rerun and verify the blocker clears, a new transport revision is adopted, and no stale widget remains attached.

## Residual Risks

- Real PyVista/VTK widget behavior, native compositor timing, and large-scene cleanup still require display-attached release validation.
