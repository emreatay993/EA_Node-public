# Architecture Followup Refactor QA Matrix

- Updated: `2026-04-03`
- Packet set: `ARCHITECTURE_FOLLOWUP_REFACTOR` (`P01` through `P08`; `P00` remains the retained bootstrap baseline)
- Scope: final closeout matrix for the retained architecture-followup refactor verification evidence, canonical spec-pack registration, and packet-owned docs or traceability gates.

## Locked Scope

- This closeout republishes retained packet evidence from `P01` through `P07` plus the exact `P08` doc-refresh verification commands; it does not introduce a new packet-external aggregate runner or a new broad token-audit layer.
- The canonical closeout surfaces for this packet set are `ARCHITECTURE.md`, `docs/specs/INDEX.md`, `docs/specs/requirements/90_QA_ACCEPTANCE.md`, `docs/specs/requirements/TRACEABILITY_MATRIX.md`, `scripts/check_traceability.py`, `tests/test_architecture_boundaries.py`, `tests/test_markdown_hygiene.py`, `tests/test_traceability_checker.py`, and this matrix.
- The retained packet wrap-ups under `docs/specs/work_packets/architecture_followup_refactor/` remain the source of record for packet-local implementation detail, accepted packet SHAs, and the desktop/manual checks that were already captured earlier in the sequence.
- `docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md` remains the broader release or Windows follow-up matrix from the earlier closeout; this matrix closes only the architecture-followup packet set.

## Retained Automated Verification

| Coverage Area | Packet | Command | Recorded Source |
|---|---|---|---|
| Shell composition root collapse and focused shell bootstrap | `P01` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_main_bootstrap.py tests/test_main_window_shell.py tests/main_window_shell/bridge_contracts.py tests/main_window_shell/shell_runtime_contracts.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P01_shell_composition_root_collapse_WRAPUP.md` (`c80c68cf5232ca9dd6cee5141cfd94e9bed264cc`) |
| Focused shell controller seams for project/session, run, and workspace flows | `P02` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_workspace_library_controller_unit.py tests/test_project_session_controller_unit.py tests/test_shell_project_session_controller.py tests/test_shell_run_controller.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P02_shell_controller_surface_narrowing_WRAPUP.md` (`aa5cafce899c6f007e630099bc9b28fa4d1c0709`) |
| Packet-owned QML bridge cleanup and focused shell or canvas bindings | `P03` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/main_window_shell/bridge_contracts.py tests/main_window_shell/bridge_qml_boundaries.py tests/test_graph_surface_input_contract.py tests/test_main_window_shell.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P03_qml_bridge_cleanup_finalization_WRAPUP.md` (`31e06aa96225e01ec75074598409aeab3b162850`) |
| Graph persistence overlay removal from packet-owned graph models | `P04` | `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_project_file_issues.py tests/test_serializer.py tests/test_serializer_schema_migration.py tests/test_workspace_manager.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P04_graph_persistence_sidecar_removal_WRAPUP.md` (`254b5cee91e16c429c1c797e462241b20420f655`) |
| Runtime snapshot direct builder without serializer round-trip on the normal run path | `P05` | `./venv/Scripts/python.exe -m pytest tests/test_execution_client.py tests/test_execution_worker.py tests/test_execution_artifact_refs.py tests/test_passive_runtime_wiring.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P05_runtime_snapshot_direct_builder_WRAPUP.md` (`85db500970842b4e2df3d2acc1232ac17f27d5bf`) |
| Graph authoring boundary collapse onto the mutation-service command path | `P06` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_graph_scene_bridge_bind_regression.py tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py tests/test_graph_surface_input_inline.py tests/test_passive_graph_surface_host.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P06_graph_authoring_boundary_collapse_WRAPUP.md` (`3c2ed4cd5d7de2aea7261349a8c48714c39fdb8a`) |
| Viewer session authority on the execution-side service and bridge projection | `P07` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_execution_viewer_service.py tests/test_execution_viewer_protocol.py tests/test_execution_worker.py tests/test_viewer_session_bridge.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P07_viewer_session_single_authority_WRAPUP.md` (`b439978de84dfc48e07bcd85be78715115313133`) |
| Viewer host, surface, and binder consumers of the normalized session model | `P07` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_viewer_host_service.py tests/test_viewer_surface_contract.py tests/test_viewer_surface_host.py tests/test_engineering_viewer_widget_binder.py --ignore=venv -q` | PASS in `docs/specs/work_packets/architecture_followup_refactor/P07_viewer_session_single_authority_WRAPUP.md` (`b439978de84dfc48e07bcd85be78715115313133`) |

## Final Closeout Commands

| Coverage Area | Command | Expected Coverage |
|---|---|---|
| Packet-owned architecture, traceability, and markdown-hygiene regression anchors | `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | Revalidates the final architecture-followup closeout anchors in `ARCHITECTURE.md`, the packet-owned traceability checker contracts, and the spec-pack markdown registration surface |
| Traceability gate | `./venv/Scripts/python.exe scripts/check_traceability.py` | Confirms the canonical spec-pack docs, requirement anchors, traceability rows, and this matrix stay aligned without widening the proof surface |
| Markdown link gate | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Confirms the spec index, requirement docs, QA matrix, and wrap-up references resolve to valid local Markdown targets |

## 2026-04-03 Execution Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q` | PASS | Packet-owned closeout regressions passed in the project venv after the final spec-pack, architecture, and QA-matrix refresh |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | Review-gate proof audit passed after the canonical closeout docs, requirements, spec index, and traceability rows were updated for the architecture-followup packet set |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | PASS | Local Markdown links for the packet-owned closeout surfaces resolved to existing targets and valid heading anchors |

## Remaining Manual Desktop Checks

1. Re-run the on-screen shell or canvas smoke checks retained in `docs/specs/work_packets/architecture_followup_refactor/P03_qml_bridge_cleanup_finalization_WRAPUP.md` if a release candidate needs confirmation that the focused bridge-only QML path still behaves correctly on a live desktop session.
2. Re-run the normal workflow execution smoke checks retained in `docs/specs/work_packets/architecture_followup_refactor/P05_runtime_snapshot_direct_builder_WRAPUP.md` if a release candidate needs confirmation that runtime preparation still behaves correctly without the serializer round-trip on a real project run.
3. Re-run the viewer reopen or rerun checks retained in `docs/specs/work_packets/architecture_followup_refactor/P07_viewer_session_single_authority_WRAPUP.md` when validating a native desktop environment, because viewer live/proxy transitions remain the most environment-sensitive surface in this packet set.

## Residual Risks

- This closeout evidence is intentionally assembled from retained `P01` through `P07` packet verification plus the exact `P08` doc-refresh commands; it does not claim a new broad aggregate rerun outside the packet spec.
- `P08` itself is a docs and verification closeout packet, so it does not add fresh interactive desktop execution evidence beyond the earlier packet-owned manual directives retained above.
- `scripts/verification_manifest.py` still points at the earlier maintainability closeout matrix as the shared branch-wide closeout baseline outside this packet's write scope; this matrix is registered from the canonical spec pack and packet-owned docs instead of replacing that shared manifest contract.
