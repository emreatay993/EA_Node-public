# Plan: COREX Change Locality and Breadcrumb Reduction

## Summary

- Updated: `2026-07-15`
- Objective: reduce time-to-owner, files opened before the first useful edit, tool-output volume, repeated verification work, and ambiguous ownership without adding runtime indirection or weakening existing performance behavior.
- Recommendation: accept the audit's change-locality goal, but do not execute its full architecture program as written. The current evidence supports a smaller sequence built around the existing map/index system, a more focused performance harness, one proven shell forwarding-chain removal, internal barrel-import cleanup, and one narrow viewer projection correction.
- The referenced Codex task does not demonstrate broad application-service duplication. It was a 32.5-minute A/B performance investigation whose product edit stayed in one QML file. Four source files were reasonably relevant, but 29 shell commands, 90 benchmark polling calls, oversized report reads, a native Qt crash, and isolated reruns grew the live prompt to about 105,000 tokens. Of the 8.79 million cumulative input tokens, 97.4% were cached replay. This makes benchmark/tooling behavior the first problem to fix for that task class.
- Independent repository evidence does confirm several narrower architecture issues: script-editor width currently crosses seven semantic hops before reaching the existing `ScriptEditorModel`; `ea_node_editor.nodes.types` has 57 internal import sites that hide seven defining modules; `ViewerSessionBridge` still writes canonical-looking phases in command paths before later applying worker projections; and committed navigation outputs contain volatile line metadata and candidate-heavy route expansion.
- Existing accepted architecture work already established graph mutation authorities, viewer host separation, and graph-scene decomposition. This plan preserves those results and does not create replacement facades over them.

### Audit verdict

| Audit finding or proposal | Verdict | Plan response |
| --- | --- | --- |
| Optimize for authority clarity and change locality, not file size | agree | Use owner-retrieval, semantic-hop, and focused-verification gates; do not split by line count. |
| `ShellWindow` and project-session forwarding cause breadcrumbing | partially agree | Remove one proven width-only chain first. Do not start a repository-wide host-injection rewrite. |
| Add a new script-editor panel service | disagree | `ScriptEditorModel` already owns width, visibility, floating state, normalization, and notifications. Reuse it. |
| Internal `nodes.types` imports obscure defining owners | agree | Migrate package-internal imports and ratchet them to zero while retaining only the required external SDK surface. |
| Graph mutation APIs need a new `GraphAuthoringPort` | disagree | Production already routes through validated/record/history owners; raw public helpers are mainly test/fixture surfaces. A new port would be another facade. |
| Guided-port work proves the need for `PortInteractionPolicy` | disagree | The cited change combined separate action, icon, and payload facts. Use it as a navigation/churn benchmark, not as justification for a new runtime owner. |
| Graph scene needs a new `GraphSceneReadModel` | not yet justified | Defer. If later evidence prioritizes this route, consolidate the existing context/cache/read-bridge owners instead of adding a fifth layer. |
| Viewer runtime, projection, and native host need clearer authority | partially agree | Keep the existing worker and host owners; narrow only canonical-versus-pending state and capture dependency lookup in `ViewerSessionBridge`. |
| Generated navigation churn and broad default results waste context | agree; highest-leverage zero-runtime item | Make the existing maps owner-first, cap default output, and remove volatile committed anchors. |
| Add a second ownership manifest and incremental SQLite index | disagree | Extend the existing agent maps, generators, and `nav.py`; do not create parallel metadata authority or cache lifecycle. |
| Mine 100-150 commits with a permanent locality analyzer | defer | Start with a small labeled corpus of real tasks. Add broader mining only if the corpus cannot distinguish the remaining problems. |
| Apply universal 2%/5% performance thresholds | disagree | Reuse route-specific harness thresholds and compare like-for-like on affected hot paths. |

## Key Changes

- Make `scripts/nav.py` return one compact owner capsule by default: primary owner, minimal path, focused test, verification command, and do-not-start-here paths. Keep broad candidates behind `--expand`.
- Use `Start Here` and `Do Not Start Here` sections in existing agent maps as the semantic source. Add explicit owner rows only where one route legitimately has several authorities, such as viewer worker, projection, and native host.
- Remove volatile line numbers and line counts from committed navigation data. Resolve current lines from source only when a user asks for a symbol or anchor.
- Make the graph performance harness filterable, progress-reporting, crash-tolerant, and able to compare two reports without dumping full JSON payloads.
- Route script-editor width directly from QML to the existing `ScriptEditorModel`, while keeping save/open persistence as a separate snapshot/restore path.
- Replace internal imports through `ea_node_editor.nodes.types` with imports from defining modules and add one focused architecture ratchet.
- Separate authoritative worker projection from pending command presentation inside `ViewerSessionBridge`; inject the existing capture capability instead of finding it through raw `ShellWindow` access.
- Defer graph-scene restructuring, raw graph fixture-API cleanup, port-visual extraction, and broader shell dependency changes until closeout measurements show that they remain material breadcrumb sources.

## Public Interface Changes

- Developer navigation CLI:
  - `scripts/nav.py find <query>` becomes compact and owner-first by default.
  - `scripts/nav.py find <query> --expand` retains broad discovery output.
  - Default output is limited to five paths and 4 KB.
- Performance harness CLI:
  - Add repeatable `--mutation-scenario <name>` filtering for `graph_mutations`; no option means the current full scenario set.
  - Add `--compare-to <report.json>` for a bounded metric-delta table.
  - Multi-run baselines execute in isolated child processes by default and retain completed run reports if a later child fails; an explicit diagnostic opt-out may keep in-process behavior.
  - Emit one bounded progress record after each run/scenario and document the difference between programmatic `create_edge` timing and a real pointer gesture.
- QML/runtime surface:
  - Expose existing `ScriptEditorModel.set_width(float)` as a Qt slot and call it directly from `ScriptEditorOverlay.qml` on resize release.
- Node SDK:
  - `ea_node_editor.nodes.types` remains only if the current Node SDK/plugin contract requires it. Package-internal imports from that barrel become prohibited.
- No `.cxproj` schema, graph action ID, execution protocol, viewer worker protocol, plugin descriptor, or user-visible behavior change is planned.

## Execution Tasks

### T01 Make navigation owner-first and establish the breadcrumb corpus

- Goal: make one normal lookup identify the likely owner and proving test without opening several maps or inventories.
- Preconditions: current `scripts/nav.py`, agent route index, and map tests pass. The original map-first authority model is superseded by the evidence-first, advisory-navigation policy in `AGENTS.md` and `docs/agent_maps/INDEX.md`.
- Conservative write scope: `scripts/nav.py`, `scripts/generate_agent_route_index.py`, `tests/test_nav_cli.py`, `tests/test_agent_route_index.py`, one small corpus fixture under `tests/fixtures/`, and only the agent maps needed to express missing `Start Here` or `Do Not Start Here` facts.
- Deliverables:
  - Add a labeled corpus of ten recent tasks, including notched-port A/B work, script-editor width, viewer settings expansion, fullscreen toolbar click, graph scene projection, viewer session ownership, and representative node/runtime lookups.
  - Record expected primary owner, up to two legitimate secondary owners, focused test, and paths that should not be returned first.
  - Require all meaningful query tokens for a strong route match; return one primary route unless confidence is tied.
  - Build the default owner capsule from existing map sections and cap it at five paths and 4 KB.
  - Add `--expand` for the current candidate-heavy output.
  - Add exact aliases/anchors for `stress_1200_nodes`, port rendering/notched ports, script-editor panel state, viewer session, and benchmark report fields where the corpus proves they are missing.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_nav_cli.py tests/test_agent_route_index.py --ignore=venv -q`
  - Corpus gate: at least 8/10 top-1 owner and 10/10 top-3, with every default response at most five paths and 4 KB.
  - `./venv/Scripts/python.exe scripts/check_agent_maps.py`
- Non-goals: new SQLite index, second ownership manifest, runtime source refactor, repository-wide commit mining, or semantic code analysis beyond the existing generators.
- Packetization notes: likely `P01 Owner-First Navigation`; can land independently after `P00 Bootstrap` and should precede ownership-changing runtime tasks.

### T02 Make focused performance proof cheap and recoverable

- Goal: prevent long A/B tasks from running irrelevant scenarios, repeatedly polling quiet children, losing completed runs, or loading huge report payloads into context.
- Preconditions: current `tests/test_track_h_perf_harness.py` passes; preserve existing report fields and route-specific acceptance semantics.
- Conservative write scope: `ea_node_editor/ui/perf/performance_harness.py`, `tests/test_track_h_perf_harness.py`, `docs/agent_maps/feature_routes/performance_harness_graph_stress.md`, and generated route metadata only if its source map changes.
- Deliverables:
  - Filter `_MUTATION_BENCHMARK_SCENARIOS` through repeatable `--mutation-scenario` values while keeping the full set as the no-option default.
  - Run `--baseline-runs > 1` as isolated child runs, write each completed run atomically, and aggregate only after children finish.
  - Retain partial results and an explicit failed-run record when a child exits nonzero or crashes in native Qt.
  - Emit bounded flushed progress after each scenario/run so a parent can wait on meaningful output instead of blind polling.
  - Add `--compare-to` with a fixed, small table for selected load, pan/zoom, drag, mutation, and RSS metrics; never recursively print `baseline_series` or full sample arrays by default.
  - Record the `create_edge` measurement limitation in the report and route map. A real pointer-gesture benchmark is a separate feature only if a future task needs it.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_track_h_perf_harness.py --ignore=venv -q`
  - Parser/runner test proves selecting `create_edge` produces no samples for the other six mutation scenarios.
  - Simulated child-failure test proves earlier run files remain readable and the aggregate reports the failed run.
  - Comparison-output test proves default stdout remains below 4 KB and excludes raw sample arrays.
  - One minimal offscreen smoke with one sample; the 1,200-node display-attached lane is reserved for a real performance-affecting implementation.
- Non-goals: changing production graph rendering, adding a generic benchmark framework, adding a database, or replacing existing route-specific performance gates.
- Packetization notes: likely `P02 Focused Performance Harness`; independent of `T01` and safe to land early because it changes developer tooling only.

### T03 Remove volatile committed navigation anchors

- Goal: stop non-semantic source edits from producing large generated diffs and consuming review/context budget.
- Preconditions: `T01` proves compact lookup can operate from stable symbols and map sections without committed line numbers.
- Conservative write scope: `scripts/generate_qml_navigation_index.py`, `scripts/generate_source_test_file_index.py`, `scripts/generate_agent_route_index.py`, `scripts/nav.py`, their generated outputs under `docs/`, and `tests/test_qml_navigation_index.py`, `tests/test_source_test_file_index.py`, and `tests/test_agent_route_index.py`.
- Deliverables:
  - Remove committed line numbers and line-count fields for QML IDs, properties, signals, functions, bindings, handlers, connections, references, map headings, and source/test inventory entries.
  - Keep stable file, symbol, relationship, owner, and heading names.
  - Resolve a requested current line on demand by scanning the selected source/map file; do not persist a local SQLite cache.
  - Regenerate committed indexes once in the new stable format.
  - Add invariance tests showing that prepending comments/blank lines and changing non-symbol QML text leave committed navigation data byte-identical.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_qml_navigation_index.py tests/test_source_test_file_index.py tests/test_agent_route_index.py tests/test_nav_cli.py --ignore=venv -q`
  - `./venv/Scripts/python.exe scripts/generate_qml_navigation_index.py --check`
  - `./venv/Scripts/python.exe scripts/generate_source_test_file_index.py --check`
  - `./venv/Scripts/python.exe scripts/generate_agent_route_index.py --check`
  - `./venv/Scripts/python.exe scripts/check_agent_maps.py`
- Non-goals: untracking all navigation artifacts, changing map ownership, adding runtime code generation, or introducing another cache/index authority.
- Packetization notes: likely `P03 Stable Navigation Artifacts`; depends on `P01` and should land before runtime tasks that update maps.

### T04 Remove the script-editor width forwarding chain

- Goal: reduce the interactive width path from seven semantic hops to `ScriptEditorOverlay.qml -> ScriptEditorModel.set_width`, while preserving project/session persistence.
- Preconditions: `T01`/`T03` are landed; current script-editor and project-session focused tests pass.
- Conservative write scope: `ea_node_editor/ui_qml/script_editor_model.py`, `ea_node_editor/ui_qml/components/shell/ScriptEditorOverlay.qml`, `ea_node_editor/ui_qml/shell_workspace_bridge.py`, `ea_node_editor/ui/shell/presenters/workspace_presenter.py`, `ea_node_editor/ui/shell/controllers/project_session_controller.py`, `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`, focused tests, and affected maps.
- Deliverables:
  - Mark existing `ScriptEditorModel.set_width` as `@pyqtSlot(float)`.
  - Keep drag updates local in QML and call the model only on resize release.
  - Remove only width forwarding from the bridge, presenter, controller, and document I/O service.
  - Keep the existing restore adapter because open/restore still needs a model setter.
  - Snapshot current script-editor state before manual save/save-as document conversion; keep autosave/session/close synchronization on the existing lifecycle path.
  - Update the shell/QML/project-session maps to name `ScriptEditorModel` as the interactive owner and document I/O as snapshot/restore only.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_script_editor_dock.py tests/test_project_session_controller_unit.py tests/test_project_save_as_flow.py --ignore=venv -q`
  - Static test proves removed width symbols do not remain on forwarding surfaces.
  - QML test proves one Python call occurs on release rather than per drag frame.
- Non-goals: visibility/focus behavior, a new panel service, a dependency dataclass, a command bus, a broad `ShellWindow` constructor migration, or a repository-wide host AST rule.
- Packetization notes: likely `P04 Script Editor Width Locality`; one complete vertical pilot. Visibility/focus is a separate future slice only if measured as another offender.

### T05 Retire package-internal `nodes.types` imports

- Goal: make each internal import land directly on the defining node/runtime contract module.
- Preconditions: confirm the current Node SDK/plugin contract still requires the external `nodes.types` surface; if it does not, deletion is preferred over compatibility retention.
- Conservative write scope: import statements under `ea_node_editor/**` that currently reference `ea_node_editor.nodes.types`, `ea_node_editor/nodes/types.py`, `tests/test_architecture_boundaries.py`, and directly affected import/registry/viewer tests. No behavior body changes are allowed in this task.
- Deliverables:
  - Replace all 57 current internal barrel imports with imports from `node_specs`, `execution_context`, `category_paths`, `plugin_contracts`, `runtime_refs`, or `viewer_runtime_contracts`.
  - Keep `nodes.types` as external-only re-exports only when required by the public SDK contract.
  - Add one AST rule rejecting `ea_node_editor.nodes.types` imports inside `ea_node_editor/**`, with an empty whitelist unless a concrete generated/bootstrap exception is proven.
  - Update the nodes map with the direct-import rule.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_registry_validation.py tests/test_execution_viewer_service.py tests/test_plugin_loader.py --ignore=venv -q`
  - Import smoke for `ea_node_editor.graph`, `ea_node_editor.execution`, `ea_node_editor.nodes`, and `ea_node_editor.ui_qml.graph_scene_bridge`.
  - Static count is zero internal barrel imports.
- Non-goals: renaming defining modules, changing contract shapes, preserving unrequired pre-release aliases, or adding a general barrel-detection framework.
- Packetization notes: likely `P05 Direct Node Contract Imports`; mechanical cross-subsystem packet with import-only production edits. It can run independently after `P03` but should avoid overlapping `P06` viewer imports.

### T06 Narrow viewer projection authority

- Goal: ensure canonical viewer phase/options/transport/playback state comes only from the execution-owned session model while keeping local pending-command presentation responsive.
- Preconditions: `T05` is landed to avoid import overlap; current viewer service/bridge/host tests pass; capture and pending-state semantics are stated in tests before code movement.
- Conservative write scope: `ea_node_editor/ui_qml/viewer_session_bridge.py`, `ea_node_editor/ui/shell/composition/runtime_services.py`, focused viewer tests, and the viewer route/subsystem maps. `ViewerHostService`, `ViewerControlBridge`, and `ContentFullscreenBridge` may only receive call-site adjustments required by dependency injection, not responsibility rewrites.
- Deliverables:
  - Keep the authoritative worker projection separate from a small pending-command/display record.
  - Remove direct canonical `phase` writes from `open`, `close`, update, and dispatch-failure command paths; those paths may update pending command/error presentation only.
  - Normalize canonical state through the existing execution-owned model/coercion path once.
  - Inject the existing camera/preview capture callable at composition instead of resolving `shell_window.viewer_host_service` with `getattr`.
  - Preserve stable QObject identity, lazy widget allocation, one renderer per workspace/node, current event batching, and fullscreen/detached/inline priority.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_execution_viewer_service.py tests/test_execution_viewer_protocol.py tests/test_viewer_session_bridge.py tests/test_viewer_control_bridge.py tests/test_viewer_host_service.py --ignore=venv -q`
  - `./venv/Scripts/python.exe -m pytest tests/test_engineering_viewer_performance.py --ignore=venv -q`
  - Static gate: no command-dispatch assignment to canonical phase fields and no raw shell lookup for capture.
  - Run the existing display-attached engineering-viewer benchmark only if payload allocation, event batching, widget lifecycle, or live projection timing changes; use its current route-specific thresholds rather than new global percentages.
- Non-goals: a new `ViewerSessionReadModel` facade, worker protocol changes, host-service rewrite, fullscreen redesign, renderer replacement, or extra payload copies.
- Packetization notes: likely `P06 Viewer Pending/Authoritative State`; keep isolated because this is the only runtime-sensitive task in the program.

### T07 Remeasure and close out without automatic scope expansion

- Goal: prove that lookup/context and locality improved, retain compact evidence, and decide explicitly whether any deferred graph work deserves a separate plan.
- Preconditions: `T01` through `T06` are complete or each skipped task has a recorded reason and unchanged baseline.
- Conservative write scope: the ten-task corpus/results, affected agent maps and coverage rows, `docs/specs/perf/COREX_CHANGE_LOCALITY_QA_MATRIX.md`, `docs/specs/INDEX.md` for closeout registration, and existing verification metadata only when the workflow actually changed.
- Deliverables:
  - Record before/after top-1/top-3 owner accuracy, default output bytes, paths returned, and retrieval calls needed before opening the primary owner.
  - Record performance-harness selected-scenario behavior, progress volume, partial-result recovery, and comparison-output bytes.
  - Record script-editor semantic-hop reduction, zero internal barrel imports, and viewer canonical-state ownership checks.
  - Use active-context/tool-output measurements, not cumulative cached-token totals, when replaying representative tasks.
  - Decide `proceed` or `defer` for graph-scene consolidation. Proceed only if a real replay still requires more than five production files because the same state/policy fact is duplicated, or the primary owner misses top-3 after `T01`/`T03`.
  - If the gate triggers, write a new focused plan that consolidates existing graph context/cache/read owners. Do not implement it inside this closeout task.
- Verification:
  - Rerun every task-owned focused command once after the last related task.
  - `./venv/Scripts/python.exe scripts/check_traceability.py`
  - `./venv/Scripts/python.exe scripts/check_markdown_links.py`
  - `./venv/Scripts/python.exe scripts/check_agent_maps.py`
  - Because the completed program crosses shared tooling and several routes, run `./venv/Scripts/python.exe scripts/run_verification.py --mode fast --summarize-output` once at final closeout, not after each task.
- Non-goals: implementing deferred graph work, creating a permanent commit-mining service, adding dashboards, enforcing production-file counts as a universal quality metric, or rerunning unrelated GUI/slow/full suites.
- Packetization notes: likely `P07 Measurement Closeout`; must remain evidence/docs only. Any triggered graph work becomes a separately approved plan/packet set.

## Work Packet Conversion Map

1. `P00 Bootstrap`: create only the manifest, ledger, prompts, index registration, and packet tracking files if this plan is explicitly converted into work packets.
2. `P01 Owner-First Navigation`: derived from `T01`.
3. `P02 Focused Performance Harness`: derived from `T02`; may run in parallel with `P01` after bootstrap because it has no overlapping production scope.
4. `P03 Stable Navigation Artifacts`: derived from `T03`; depends on `P01`.
5. `P04 Script Editor Width Locality`: derived from `T04`; depends on `P03` so its map updates use the stable format.
6. `P05 Direct Node Contract Imports`: derived from `T05`; can start after `P03` and should finish before viewer work.
7. `P06 Viewer Pending/Authoritative State`: derived from `T06`; depends on `P05` to avoid import conflicts.
8. `P07 Measurement Closeout`: derived from `T07`; depends on all accepted implementation packets.

## Test Plan

- Navigation loop: corpus-driven top-1/top-3 tests, output-size cap, `--expand` compatibility, exact alias coverage, and current-line on-demand resolution.
- Generated artifacts: generator unit tests, three generator `--check` commands, comment/blank-line invariance, and agent-map path validation.
- Performance tooling: parser/filter tests, isolated-run aggregation, simulated native-child failure with retained partial evidence, bounded progress, safe report comparison, and one minimal offscreen smoke.
- Script editor: model/QML width behavior, release-only call frequency, manual save/save-as snapshot, and open/restore regression coverage.
- Node contracts: AST import ratchet, registry/plugin tests, viewer/execution imports, and focused package import smoke; no runtime performance run.
- Viewer: execution service/protocol, bridge/control/host tests, existing engineering-viewer performance test, and conditional display-attached benchmark only when a hot-path behavior changes.
- Closeout: one targeted test pass per task, one final cross-route `fast --summarize-output` run, traceability/link/map checks, and corpus replay. Do not repeat the same broad command at task and program closeout.

## Assumptions

- Existing agent maps remain the single semantic navigation authority. Generated indexes are derived lookup artifacts, not competing ownership manifests.
- The ten-task corpus is sufficient for the first iteration. Expand it only when a new failure mode cannot be represented by the existing sample.
- The referenced notched-port task is evidence for performance-harness and lookup/process improvements, not proof of broad application-service duplication.
- `ScriptEditorModel` remains the script-editor presentation-state owner; project/session services own persistence snapshots and lifecycle, not interactive width commands.
- `nodes.types` is retained only to the extent required by the current public Node SDK/plugin contract. COREX's pre-release compatibility policy otherwise favors deletion.
- Cross-process viewer architecture legitimately has worker, UI projection, and native host authorities. The goal is one-way canonical state flow, not one class for all responsibilities.
- Tooling/index/import tasks have no production hot-path performance effect. Runtime tasks must preserve item counts, stable QObjects, direct calls, lazy allocation, batching, and existing route-specific performance gates.
- Existing unrelated worktree changes are preserved. This plan does not authorize editing or cleaning the active graph-port work from the referenced task.
