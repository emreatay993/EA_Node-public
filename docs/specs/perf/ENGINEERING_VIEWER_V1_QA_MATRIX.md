# COREX Neutral CAD/FE Model Viewer V1 QA Matrix

- Status: `PARTIAL`
- Requirements: `REQ-UI-050`, `REQ-NODE-035`, `REQ-EXEC-016`,
  `REQ-INT-017`, `REQ-PERF-015`, and `REQ-QA-050`.

## Automated evidence

| Area | Evidence | Result |
| --- | --- | --- |
| Scene/schema/cache | `tests/test_engineering_import_nodes.py` | PASS |
| CAD/query/export | `tests/test_engineering_viewer_backend.py` | PASS |
| Native binding | `tests/test_engineering_viewer_widget_binder.py` | PASS |
| Session transport | `tests/test_viewer_session_bridge.py` | PASS |
| Shared controls | `tests/test_viewer_control_bridge.py`, `tests/test_content_fullscreen_bridge.py` | PASS |
| Same-widget lifecycle | `tests/test_viewer_host_service.py` | PASS |
| Packaging contracts | `tests/test_packaging_configuration.py` | PASS |

## Current behavior

- One focus-owned viewer widget moves between inline, fullscreen, and detached
  presentations while retaining camera, selection, and display state.
- Runtime capability facts gate CAD and FE selection filters.
- Shaded, wireframe, hidden-line, topology-edge, mesh-edge, and source-color
  display modes remain independently selectable when supported.
- Fit, isolate/restore, standard views, projection, orientation aids, camera
  bookmarks, screenshot export, and detach/redock use shared controls.
- Unsupported capabilities stay disabled with an explicit explanation.

## Open release gates

- Representative tracked fixtures for every advertised CAD and FE format.
- Display-attached picking, lighting, orientation-widget, and reparenting checks.
- Lazy field/time materialization and large-model memory evidence.
- Clean packaged startup and neutral fixture smoke.

## Verification

```powershell
.\venv\Scripts\python.exe -m pytest -n 0 tests/test_engineering_import_nodes.py tests/test_engineering_viewer_backend.py tests/test_engineering_viewer_widget_binder.py tests/test_engineering_viewer_node.py -q
.\venv\Scripts\python.exe -m pytest -n 0 tests/test_viewer_control_bridge.py tests/test_content_fullscreen_bridge.py tests/test_viewer_host_service.py tests/test_viewer_surface_contract.py -q
.\venv\Scripts\python.exe -m pytest -n 0 tests/test_packaging_configuration.py tests/test_engineering_viewer_performance.py -q
```

The matrix remains `PARTIAL` until every open release gate has current
display-attached or tracked-fixture evidence.
