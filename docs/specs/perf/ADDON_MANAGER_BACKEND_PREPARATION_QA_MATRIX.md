# Add-On Manager Backend Preparation QA Matrix

- Updated: `2026-09-07`
- Scope: current generic add-on catalog/state model, Add-On Manager shell surface, unavailable-node projection, and retained Tabular Data and MARS add-ons.

## Locked Scope

- `Add-On Manager` remains the top-level menubar entry and Variant 4 inspector-style right drawer.
- Missing add-on nodes remain visible as locked Mockup B placeholders with read-only graph structure.
- Add-on state changes rebuild the candidate registry and publish only after graph compatibility and consumer updates succeed; failures roll back.
- The repo catalog contains Tabular Data and MARS. Marketplace, update, install, and restart actions remain outside this contract.

## Current Automated Verification

| Coverage Area | Requirement Anchors | Command | Status |
|---|---|---|---|
| Catalog, state model, and retained add-ons | `REQ-INT-011`, `REQ-QA-040` | `.\venv\Scripts\python.exe -m pytest tests/test_addon_catalog.py tests/test_addon_state_changes.py tests/test_tabular_addon_catalog.py tests/test_mars_nodes.py --ignore=venv -q` | `FAIL` |
| Registry replacement and rollback | `REQ-PERSIST-023`, `REQ-QA-040` | `.\venv\Scripts\python.exe -m pytest tests/test_registry_replacement.py tests/test_addon_manager_install.py --ignore=venv -q` | `PASS` |
| Missing-node persistence and locked surface | `REQ-UI-042`, `REQ-PERSIST-023` | `.\venv\Scripts\python.exe -m pytest tests/test_serializer.py tests/test_registry_validation.py tests/test_graph_surface_input_contract.py tests/test_passive_graph_surface_host.py --ignore=venv -q` | `PASS` |
| Manager shell projection | `REQ-UI-041`, `REQ-INT-011` | `.\venv\Scripts\python.exe -m pytest tests/test_main_window_shell.py tests/main_window_shell/shell_basics_and_search.py tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q` | `FAIL` |

The catalog lane currently fails because `tests/test_tabular_addon_catalog.py` still expects the removed property-edit adapter. The shell lane passes 338 tests and 1,544 subtests but retains three unrelated ownership/interaction assertion failures in quick insert, Content Fullscreen, and shell window-state coverage. This matrix does not relabel either lane as passing evidence.

## Final Closeout Commands

| Command | Purpose |
|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | Structural traceability and Markdown regression for the current add-on matrix. |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | Semantic proof audit for current requirements, commands, statuses, and result rows. |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Local Markdown-link audit. |

## 2026-09-07 Execution Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | `PASS` | Current generic add-on proof structure and Markdown checks passed. |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | `PASS` | Current semantic proof audit passed. |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | `PASS` | Current local Markdown links resolved. |

## Manual Desktop Checks

1. Open and close the manager drawer with the scrim and `Esc`; verify selected add-on focus is retained.
2. Toggle a retained available add-on and verify the Library and manager detail refresh without disturbing the open workspace.
3. Open a project with an unavailable add-on node and verify the locked placeholder preserves saved values and edges.

## Residual Risks

- Marketplace/discovery flows and true in-session unload for restart-required add-ons remain out of scope.
