# UI Context Scalability Refactor QA Matrix

- Updated: `2026-04-05`
- Packet set: `UI_CONTEXT_SCALABILITY_REFACTOR` (`P01` through `P09`)
- Scope: final closeout matrix for the shipped UI-context scalability refactor packet set, including the narrowed shell/presenter/graph-scene/graph-canvas/edge-rendering/viewer seams, historical context-budget artifacts, subsystem packet contracts, and packet-owned traceability/docs evidence.

## Locked Scope

- The active closeout proof lives in `docs/specs/INDEX.md`, `docs/specs/requirements/90_QA_ACCEPTANCE.md`, `docs/specs/requirements/TRACEABILITY_MATRIX.md`, `scripts/check_traceability.py`, `tests/test_traceability_checker.py`, `tests/test_markdown_hygiene.py`, `tests/test_run_verification.py`, and this matrix.
- `docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json` plus `scripts/check_context_budgets.py` remain historical/optional diagnostics from `P07`; they are not required future coding, closeout, release, or docs/proof gates.
- `docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md`, `docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md`, and the subsystem packet contract docs remain the required entry path for future UI work after `P08`.
- This closeout proof is packet-scoped: it retains the approved packet verification commands and wrap-up evidence from `P01` through `P08`, and it does not claim a broader repo-wide product rerun beyond the declared `P09` commands.
- `tests/test_run_verification.py` remains the packet-owned metadata proof that the normal developer verification surface is wired through `scripts/run_verification.py`; context-budget diagnostics are no longer part of that required surface.

## Retained Automated Verification

| Coverage Area | Packet | Command | Recorded Source |
|---|---|---|---|
| ShellWindow lifecycle-first reduction and shell runtime wiring | `P01` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_main_bootstrap.py tests/test_main_window_shell.py tests/test_shell_window_lifecycle.py tests/main_window_shell/shell_runtime_contracts.py tests/main_window_shell/bridge_contracts.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P01_shell_window_facade_collapse_WRAPUP.md` (`1e873e15c2d959a4cc4282945a774a22804e2b68`) |
| Curated presenter package split and shell search/library flows | `P02` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_main_window_shell.py tests/test_window_library_inspector.py tests/main_window_shell/bridge_contracts.py tests/main_window_shell/shell_basics_and_search.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P02_presenter_family_split_WRAPUP.md` (`0c86040158d9adf3c12fc964c257fad1889be54b`) |
| Graph-scene support package split and graph-surface bridge regressions | `P03` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_graph_scene_bridge_bind_regression.py tests/test_graph_surface_input_contract.py tests/test_passive_graph_surface_host.py tests/test_main_window_shell.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P03_graph_scene_bridge_packet_split_WRAPUP.md` (`bc0182de9e37a7c9ea55a045e05efb4e94cc0745`) |
| Graph canvas root composition and stable root-contract regressions | `P04` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py tests/test_graph_surface_input_inline.py tests/test_graph_track_b.py tests/graph_track_b/qml_preference_bindings.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P04_graph_canvas_root_packetization_WRAPUP.md` (`2a20bf1bc6c23f8cd6f6cc97f7c696c59912743b`) |
| Edge rendering, label, cache, and hit-test helper regressions | `P05` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_flow_edge_labels.py tests/test_flowchart_visual_polish.py tests/test_graphics_settings_preferences.py tests/test_graph_track_b.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P05_edge_renderer_packet_split_WRAPUP.md` (`77cdcf091891e817228db7852147bdb0eaa54ff3`) |
| Viewer-session isolation and viewer surface contract regressions | `P06` | `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/test_execution_viewer_service.py tests/test_viewer_session_bridge.py tests/test_viewer_host_service.py tests/test_viewer_surface_contract.py tests/test_viewer_surface_host.py tests/test_engineering_viewer_node.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P06_viewer_surface_isolation_WRAPUP.md` (`3769e0fc9eea2392a7756c874fb6fafd6a5d802c`) |
| Context-budget hotspot checker | `P07` | `./venv/Scripts/python.exe scripts/check_context_budgets.py` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P07_context_budget_guardrails_WRAPUP.md` (`5537558c7d64539e51084455a6d0f44643373871`) |
| Context-budget verification metadata and targeted guardrail tests | `P07` | `./venv/Scripts/python.exe -m pytest tests/test_context_budget_guardrails.py tests/test_run_verification.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P07_context_budget_guardrails_WRAPUP.md` (`5537558c7d64539e51084455a6d0f44643373871`) |
| Subsystem packet docs markdown structure and registration proof | `P08` | `./venv/Scripts/python.exe -m pytest tests/test_markdown_hygiene.py --ignore=venv -q` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P08_subsystem_packet_docs_WRAPUP.md` (`956cdc7f7d726c040aefbb0f5d81f581f4ba2fd4`) |
| Subsystem packet docs local link integrity | `P08` | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | PASS in `docs/specs/work_packets/ui_context_scalability_refactor/P08_subsystem_packet_docs_WRAPUP.md` (`956cdc7f7d726c040aefbb0f5d81f581f4ba2fd4`) |

## Final Closeout Commands

| Coverage Area | Command | Expected Coverage |
|---|---|---|
| Traceability, markdown hygiene, and verification metadata closeout proof | `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_run_verification.py --ignore=venv -q` | Revalidates the packet-owned QA matrix tokens, canonical spec-index registration, markdown discovery, and inherited `P07` verification metadata on the P09 closeout surface |
| Traceability gate | `./venv/Scripts/python.exe scripts/check_traceability.py` | Confirms the refreshed closeout docs, requirement rows, traceability entries, retained QA matrix, historical context-budget artifact notes, and subsystem packet contract references stay aligned |
| Markdown link gate | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Confirms the canonical docs surfaces and retained UI packet docs resolve to existing local markdown targets and headings |

## 2026-04-05 Execution Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_run_verification.py --ignore=venv -q` | PASS | Packet-owned traceability, markdown-hygiene, and verification-metadata tests passed on the closeout surface (`55 passed, 6 subtests passed in 3.81s`) |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | The refreshed QA matrix, spec index, QA acceptance requirements, traceability rows, and inherited guardrail references stayed aligned (`TRACEABILITY CHECK PASS`) |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | PASS | Canonical docs surfaces and retained UI packet docs resolved to existing local markdown targets and headings (`MARKDOWN LINK CHECK PASS`) |

## Remaining Manual Desktop Checks

1. Shell and presenter smoke: rerun the native desktop checks from `docs/specs/work_packets/ui_context_scalability_refactor/P01_shell_window_facade_collapse_WRAPUP.md` and `docs/specs/work_packets/ui_context_scalability_refactor/P02_presenter_family_split_WRAPUP.md` to confirm launch, search, workspace, library, and presenter-driven shell flows still behave on a display-attached Windows session.
2. Graph editing smoke: rerun the native desktop checks from `docs/specs/work_packets/ui_context_scalability_refactor/P03_graph_scene_bridge_packet_split_WRAPUP.md`, `docs/specs/work_packets/ui_context_scalability_refactor/P04_graph_canvas_root_packetization_WRAPUP.md`, and `docs/specs/work_packets/ui_context_scalability_refactor/P05_edge_renderer_packet_split_WRAPUP.md` to confirm graph editing, inline controls, flow-edge rendering, and graph-surface interactions still behave through the narrowed UI seams.
3. Viewer smoke: rerun the native desktop checks from `docs/specs/work_packets/ui_context_scalability_refactor/P06_viewer_surface_isolation_WRAPUP.md` to confirm viewer projection, binder adoption, and rerun-required desktop behavior still work on a real Windows desktop session.
4. Packet-doc entry-path smoke: open `docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md` and `docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md`. Expected result: the docs still provide the future-work entry path; `./venv/Scripts/python.exe scripts/check_context_budgets.py` may be run only as an optional legacy diagnostic when explicitly requested.

## Residual Risks

- This closeout thread retains the approved `P01` through `P08` evidence and reruns only the packet-owned traceability/markdown proof required by `P09`; it does not repeat the broader offscreen regression suites from the earlier packets.
- The manual Windows desktop checks inherited from the earlier packet wrap-ups were not rerun in this docs closeout thread, so real-display validation for shell, graph, and viewer interaction remains a separate release-candidate task.
- Context-budget artifacts are retained for historical diagnostics only. Future UI work still needs to keep `SUBSYSTEM_PACKET_INDEX.md`, `FEATURE_PACKET_TEMPLATE.md`, and the subsystem packet docs synchronized as entry points evolve, but it does not need to satisfy or update context budgets unless explicitly requested.
