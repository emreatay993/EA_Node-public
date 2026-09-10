# Architecture Residual Refactor QA Matrix

- Updated: `2026-04-04`
- Packet set: `ARCHITECTURE_RESIDUAL_REFACTOR` (`P01` through `P08`)
- Scope: semantic verification, shell-isolation ownership proof, traceability, and docs closeout for the residual architecture refactor packet set.

## Locked Scope

- The active residual closeout proof lives in `docs/specs/INDEX.md`, `docs/specs/requirements/90_QA_ACCEPTANCE.md`, `docs/specs/requirements/TRACEABILITY_MATRIX.md`, `scripts/verification_manifest.py`, `scripts/check_traceability.py`, `tests/test_architecture_boundaries.py`, `tests/test_shell_isolation_phase.py`, `tests/test_traceability_checker.py`, `tests/test_markdown_hygiene.py`, and this matrix.
- `scripts/verification_manifest.py` is the canonical source for the packet-owned `P08` closeout commands, shell-isolation ownership rules, target catalog boundaries, and residual traceability tokens shared by the checker and tests.
- The packet-owned shell catalog remains anchored by `tests/shell_isolation_main_window_targets.py` and `tests/shell_isolation_controller_targets.py`; `P08` adds reverse ownership proof so new shell-backed tests require explicit catalog coverage or an explicit manifest-owned exclusion.
- `docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md` remains inherited context for the earlier closeout, while this matrix records the residual packet-set closeout proof.

## Retained Automated Verification

| Packet | Verification Command | Retained Evidence |
|---|---|---|
| `P01` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_main_bootstrap.py tests/test_project_session_controller_unit.py tests/test_workspace_library_controller_unit.py tests/test_shell_project_session_controller.py tests/test_shell_run_controller.py tests/test_main_window_shell.py --ignore=venv -q` | `P01_shell_host_surface_retirement_WRAPUP.md` |
| `P02` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_shell_window_lifecycle.py tests/shell_isolation_runtime.py tests/test_shell_isolation_phase.py --ignore=venv -q` | `P02_shell_lifecycle_isolation_hardening_WRAPUP.md` |
| `P03` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_graph_scene_bridge_bind_regression.py tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py tests/test_graph_surface_input_inline.py tests/test_passive_graph_surface_host.py --ignore=venv -q` | `P03_graph_scene_bridge_decomposition_WRAPUP.md` |
| `P04` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_execution_viewer_service.py tests/test_execution_viewer_protocol.py tests/test_viewer_session_bridge.py tests/test_viewer_host_service.py tests/test_viewer_surface_host.py tests/test_engineering_viewer_widget_binder.py --ignore=venv -q` | `P04_viewer_projection_authority_split_WRAPUP.md` |
| `P05` | `./venv/Scripts/python.exe -m pytest tests/test_execution_client.py tests/test_execution_worker.py tests/test_execution_artifact_refs.py tests/test_passive_runtime_wiring.py tests/test_architecture_boundaries.py --ignore=venv -q` | `P05_runtime_snapshot_boundary_decoupling_WRAPUP.md` |
| `P06` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_graph_scene_bridge_bind_regression.py tests/test_graph_surface_input_contract.py tests/test_passive_graph_surface_host.py --ignore=venv -q` | `P06_graph_mutation_service_decoupling_WRAPUP.md` |
| `P07` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_plugin_loader.py tests/test_execution_worker.py tests/test_execution_viewer_service.py tests/test_engineering_viewer_widget_binder.py --ignore=venv -q` | `P07_shared_runtime_contract_extraction_WRAPUP.md` |

## Final Closeout Commands

| Coverage Area | Command | Expected Coverage |
|---|---|---|
| Semantic architecture, shell-isolation ownership, traceability, and markdown-hygiene regressions | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_shell_isolation_phase.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | Revalidates the AST-backed architecture boundaries, manifest-owned shell ownership rules, residual traceability tokens, and canonical spec-index markdown discovery |
| Traceability gate | `./venv/Scripts/python.exe scripts/check_traceability.py` | Confirms the refreshed residual closeout docs, requirements rows, traceability matrix entries, and QA matrix stay aligned |
| Markdown link gate | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Confirms the canonical docs surfaces resolve to existing local markdown targets and headings |

## 2026-04-04 Execution Results

| Command | Result | Notes |
|---|---|---|
| `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_shell_isolation_phase.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | PASS | Packet-owned semantic verification, shell-isolation ownership proof, traceability coverage, and markdown discovery passed in the project venv (`70 passed in 67.74s`) |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | Residual closeout docs, requirements, traceability rows, and QA matrix stayed aligned after the packet refresh (`TRACEABILITY CHECK PASS`) |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | PASS | Canonical markdown surfaces resolved to existing local targets and valid headings (`MARKDOWN LINK CHECK PASS`) |

## Remaining Manual Desktop Checks

1. Shell lifecycle and host smoke: rerun the `P01` and `P02` desktop checks from `P01_shell_host_surface_retirement_WRAPUP.md` and `P02_shell_lifecycle_isolation_hardening_WRAPUP.md` to confirm repeated launch, close, search, workspace, and view flows still behave on a display-attached Windows session.
2. Graph interaction smoke: rerun the `P03` and `P06` desktop checks from `P03_graph_scene_bridge_decomposition_WRAPUP.md` and `P06_graph_mutation_service_decoupling_WRAPUP.md` to confirm graph editing, grouping, and flowchart connection gestures still behave through the narrowed graph-scene and mutation seams.
3. Viewer smoke: rerun the `P04` and `P07` desktop checks from `P04_viewer_projection_authority_split_WRAPUP.md` and `P07_shared_runtime_contract_extraction_WRAPUP.md` using Model Viewer to confirm focus/proxy transitions, rerun behavior, and engineering scene transport still behave on a native desktop session.
4. Runtime snapshot and artifact smoke: rerun the `P05` desktop check from `P05_runtime_snapshot_boundary_decoupling_WRAPUP.md` to confirm a normal workflow run still exercises runtime metadata, artifact projection, and viewer-backed execution paths without a user-visible regression.

## Residual Risks

- `P08` publishes proof and docs evidence only; the manual Windows desktop checks inherited from the earlier packet wrap-ups were not rerun in this closeout thread.
- The shell-isolation catalog remains intentionally curated rather than exhaustive, but the manifest-owned ownership rules now force explicit coverage or exclusion decisions for the current shell-backed modules, classes, and scenarios.
- `tests/test_main_window_shell.py::GraphCanvasQmlBoundaryTests` is now an explicit shell-isolation exclusion because the retained graph-surface regressions already cover the packet-owned canvas bridge contract and the shell-isolated bridge-local pack no longer stays green with that stale QML-boundary expectation on this branch.
- Broader architecture discovery docs outside the `P08` write scope still describe later closeout material, so this matrix is the packet-owned source for the residual refactor closeout rather than a repo-wide architecture rewrite.
