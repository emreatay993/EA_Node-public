# Nested Node Categories QA Matrix

- Updated: `2026-09-07`
- Scope: current path-backed node categories, descendant filtering, nested Engineering taxonomy, QML presentation, and external-plugin authoring.

## Locked Scope

- `category_path: tuple[str, ...]` is authoritative; paths contain `1..10` non-empty trimmed segments.
- `category` remains read-only display text. Grouping, filtering, sorting, and collapse state use normalized paths and `category_key`.
- The display-only separator is ` > ` and must not be parsed back into a path.
- Descendant filters include retained nested families such as `Engineering > Import` and `Engineering > Viewer`.
- Category metadata is not persisted on node instances, so no `.cxproj` migration is required.

## Current Automated Verification

| Coverage Area | Requirement Anchors | Command | Status |
|---|---|---|---|
| SDK normalization and validation | `REQ-NODE-003` | `.\venv\Scripts\python.exe -m pytest tests/test_decorator_sdk.py tests/test_registry_validation.py -k nested_category_sdk --ignore=venv -q` | `NOT RUN` |
| Descendant filtering and retained taxonomy | `REQ-NODE-003`, `REQ-UI-006` | `.\venv\Scripts\python.exe -m pytest tests/test_library_projection.py tests/test_graph_theme_shell.py -k nested_category_library --ignore=venv -q` | `NOT RUN` |
| QML category presentation and drop behavior | `REQ-UI-006` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/main_window_shell/drop_connect_and_workflow_io.py tests/main_window_shell/bridge_qml_boundaries.py -k nested_category --ignore=venv -q` | `NOT RUN` |

## Manual Desktop Checks

1. Expand `Engineering`, then `Import` and `Viewer`; verify indentation, collapse state, and draggable node rows.
2. Filter by the `Engineering` category and verify both descendants remain visible.
3. Confirm custom workflows remain under `Custom Workflows`.

## Residual Risks

- Native Windows visual spacing and drag/drop feel still require a display-attached release smoke.
