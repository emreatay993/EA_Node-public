# UI Context Scalability Follow-Up Review

- Date: `2026-04-05`
- Scope: remaining context sinks after `UI_CONTEXT_SCALABILITY_REFACTOR`
- Baseline branch: `main`

## Repo-Owned Size Snapshot

- Excluding `venv/`, `.claude/`, build artifacts, and other generated directories, repo-owned source totals about `69,287` lines across `321` files.
- Repo-owned tests total about `48,753` lines across `133` files.
- Average source file size is about `216` lines.
- Average test file size is about `367` lines.
- The biggest remaining context sinks are a mix of test umbrellas and source helper umbrellas, not one category alone.

## Current Hotspots

### Tests

- `tests/test_passive_graph_surface_host.py` (`3178` lines)
- `tests/test_graph_surface_input_contract.py` (`1950` lines)
- `tests/main_window_shell/bridge_contracts.py` (`1794` lines)
- `tests/graph_track_b/qml_preference_bindings.py` (`1648` lines)
- `tests/graph_track_b/scene_and_model.py` (`1549` lines)

### Source

- `ea_node_editor/ui/shell/window_state_helpers.py` (`1297` lines)
- `ea_node_editor/ui_qml/graph_surface_metrics.py` (`1255` lines)
- `ea_node_editor/ui_qml/edge_routing.py` (`1199` lines)
- `ea_node_editor/ui_qml/graph_scene_mutation_history.py` (`1089` lines)
- `ea_node_editor/ui/shell/controllers/project_session_services.py` (`931` lines)

## Follow-Up Findings

- The existing `UI_CONTEXT_SCALABILITY_REFACTOR` packet set successfully narrowed earlier shell, graph-canvas, edge-layer, and viewer entry surfaces, but its guardrails only cover that first hotspot catalog.
- The remaining large files are now mostly second-order seams: shell helper surfaces, graph geometry helpers, graph-scene mutation helpers, and the large regression suites that still prove those seams.
- Future UI features will keep consuming oversized context unless both source and regression ownership are packetized and machine-guarded.
- The follow-up should preserve current public entrypoints and regression entrypoints as thin facades or aggregators so existing commands and docs stay stable while implementation detail moves behind smaller packet-owned modules.

## Follow-Up Packet Intent

1. Extend guardrails and wire them into normal verification.
2. Split the remaining shell and project-session helper umbrellas.
3. Split graph geometry and routing helper umbrellas.
4. Split graph-scene mutation history helpers.
5. Packetize the main-window bridge regression suite.
6. Packetize the graph-surface regression suite.
7. Packetize the Track-B regression suite.
8. Update the canonical UI packet docs so future work must name both a source owner and a regression owner.
9. Publish the closeout QA and traceability baseline for the follow-up packet set.

## Expected Outcome

- Routine UI feature work should normally touch one source packet plus one regression packet.
- The legacy top-level files stay import-compatible and command-compatible, but they stop being the only place engineers have to read.
- The canonical guardrail and packet docs stay in the existing `ui_context_scalability_refactor` documentation home instead of creating a second competing entrypoint.
