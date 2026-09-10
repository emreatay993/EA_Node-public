# EA Node Editor Architecture Maintainability Review

Date: 2026-03-28  
Repository: `EA_Node_Editor`  
Scope: architecture quality, maintainability, understandability, refactor pressure, and cleanup priorities  
Review mode: parallel subagent analysis, local static analysis, and focused verification in the project venv

## Executive Verdict

Overall verdict: **good at the macro level, mixed at the tactical level, and now due for deliberate refactoring**.

This is not a bad codebase in the sense of lacking architecture. It clearly has one. The package layout is intentional, the worker/runtime split is real, the QML boundary has been actively improved, plugin loading is more disciplined than average, and the repository has unusually strong architecture-oriented docs and tests.

The problem is that the architecture is now paying a growing compatibility and concentration tax:

1. `ShellWindow` is still the effective center of gravity.
2. The bridge split is real, but many bridges still fall back to `ShellWindow`, which weakens ownership.
3. The graph canvas and scene stack are concentrated in a handful of very large files.
4. Core package boundaries are denser than the documentation suggests.
5. Project/session persistence flows have duplicate authorities.
6. Runtime/viewer/plugin paths still carry compatibility seams that should be retired.
7. The proof layer is strong, but some of it is brittle and one boundary contract is already drifting.

Bottom line:

- **No rewrite is needed.**
- **Important refactoring is justified now.**
- **The best payoff is in reducing host-centered compatibility surfaces, deleting duplicate authorities, and splitting the largest policy-heavy modules.**

Weighted overall score: **3.3 / 5**

Interpretation: **fundamentally good architecture with notable refactor debt**.

## Methodology

This review combined:

- Parallel subagent passes for:
  - core package boundaries
  - UI/QML and bridge ownership
  - persistence/workspace/session flows
  - execution/runtime/plugin/viewer seams
  - maintainability signals across tests, docs, and tooling
- Local static analysis:
  - package LOC distribution
  - large-file density
  - AST method counts
  - internal import fan-in/fan-out
  - targeted boundary searches
- Focused verification in the project venv:
  - `./venv/Scripts/python.exe -m pytest -q tests/test_architecture_boundaries.py tests/test_main_bootstrap.py tests/test_packaging_configuration.py`
  - Result: `17 passed in 0.22s`
  - `./venv/Scripts/python.exe -m pytest -q tests/test_dead_code_hygiene.py tests/test_run_verification.py tests/test_traceability_checker.py`
  - Result: `26 passed, 3 subtests passed in 2.07s`
  - `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/main_window_shell/bridge_qml_boundaries.py tests/main_window_shell/bridge_contracts.py -q`
  - Result: `1 failed, 33 passed, 315 subtests passed in 2.50s`
  - Failure: `tests/main_window_shell/bridge_contracts.py::MainWindowGraphCanvasBridgeTests::test_qml_context_registers_state_command_and_compat_canvas_bridges`

This was not a full green-suite certification pass, a runtime profiler session, or a user-workflow UX review.

## Architecture Scorecard

| Dimension | Score | Judgment | Key Evidence |
| --- | ---: | --- | --- |
| Layering and package cohesion | 3.2 | Real subsystem boundaries exist, but core packages are denser than ideal | `ARCHITECTURE.md:19-32`, `ea_node_editor/graph/model.py:164-262`, `ea_node_editor/nodes/types.py:443-620` |
| Dependency direction and boundary enforcement | 3.5 | Better than average and actively tested, but not fully clean | `ea_node_editor/graph/boundary_adapters.py:46-96`, `tests/test_architecture_boundaries.py:10-34` |
| UI/domain separation | 2.8 | Directionally improved, still too host-centered | `ea_node_editor/ui/shell/window.py:15-214`, `ea_node_editor/ui/shell/composition.py:58-209` |
| Scene/canvas complexity management | 2.6 | Helper extraction helped, but complexity is still concentrated | `ea_node_editor/ui_qml/graph_scene_bridge.py:54-214`, `ea_node_editor/ui_qml/graph_scene_mutation_history.py:1-120`, `ea_node_editor/ui_qml/components/GraphCanvas.qml:1-220` |
| Runtime and execution isolation | 3.6 | Worker/runtime split is real, with some legacy seams left | `ea_node_editor/execution/client.py:41-78`, `ea_node_editor/execution/runtime_snapshot.py:154-203`, `ea_node_editor/execution/worker_runtime.py:201-226` |
| Persistence and schema clarity | 3.1 | Core kernel is mostly good, shell-side orchestration is scattered | `ea_node_editor/persistence/serializer.py:29-67`, `ea_node_editor/ui/shell/controllers/project_session_services.py:329-938` |
| Extension and plugin architecture | 3.7 | Stronger than average, but too much runtime/application detail lives under `nodes` | `ea_node_editor/nodes/plugin_loader.py:43-214`, `ea_node_editor/nodes/registry.py:54-221`, `ea_node_editor/nodes/types.py:467-620` |
| Test architecture and change safety | 4.2 | Very strong safety net, but some checks are brittle and one contract has drifted | `scripts/verification_manifest.py:7-132`, `tests/test_run_verification.py:25-86`, `tests/main_window_shell/bridge_contracts.py:1470-1494` |

Weighted overall: **3.3 / 5**

## Structural Strengths

### 1. The repo has real subsystem decomposition

The top-level design described in `ARCHITECTURE.md` is not fictional. The codebase does separate `ui`, `ui_qml`, `graph`, `execution`, `persistence`, `nodes`, and `workspace` into recognizable areas of responsibility (`ARCHITECTURE.md:19-32`). That is already a meaningful advantage over many desktop Python apps.

### 2. Low-level packages are mostly UI-independent

A direct search across `ea_node_editor/graph`, `ea_node_editor/persistence`, `ea_node_editor/execution`, and `ea_node_editor/nodes` found no direct `PyQt6`, `ea_node_editor.ui`, or `ea_node_editor.ui_qml` imports. The graph-domain adapter pattern is explicit instead: `GraphSceneBridge` installs UI-derived geometry and PDF policies into `graph.boundary_adapters`, and a dedicated test protects that contract (`ea_node_editor/graph/boundary_adapters.py:46-96`, `tests/test_architecture_boundaries.py:10-34`).

That is a genuine strength. It shows the team is not only documenting boundaries but also testing them.

### 3. The runtime split is real

The execution path is not just "call node code from the UI". There is a concrete `ProcessExecutionClient`, typed worker protocol, `RuntimeSnapshot`, worker runtime preparation, and worker runner orchestration (`ea_node_editor/execution/client.py:41-78`, `ea_node_editor/execution/protocol.py`, `ea_node_editor/execution/runtime_snapshot.py:171-203`, `ea_node_editor/execution/worker_runtime.py:201-226`).

That gives the codebase a solid foundation for future cleanup, because execution is already isolated conceptually.

### 4. Plugin loading and registry validation are stronger than average

`NodeRegistry` is a strong seam with centralized validation of type IDs, port definitions, property definitions, surface families, and runtime behaviors (`ea_node_editor/nodes/registry.py:54-221`). Plugin loading is descriptor-first, provenance-aware, and supports file, package, and entry-point discovery (`ea_node_editor/nodes/plugin_loader.py:43-214`).

This part of the architecture feels intentional and worth preserving.

### 5. Persistence primitives are stronger than the shell-side orchestration around them

`JsonProjectSerializer -> JsonProjectMigration -> JsonProjectCodec` is a sensible kernel (`ea_node_editor/persistence/serializer.py:29-67`, `ea_node_editor/persistence/migration.py:20-150`, `ea_node_editor/persistence/project_codec.py`). The artifact core is also structurally good: `ProjectArtifactStore` and `ProjectArtifactResolver` give file-bearing behavior a real abstraction instead of scattering path logic everywhere.

The persistence core should be kept and refined, not replaced.

### 6. Verification and documentation discipline are unusually strong

The repository has an active architecture narrative in `README.md`, `ARCHITECTURE.md`, the spec pack, and the verification manifest (`README.md:8-24`, `ARCHITECTURE.md:34-141`, `scripts/verification_manifest.py:7-132`). The focused venv verification I ran passed cleanly except for one real boundary-contract inconsistency.

That is a major asset. The codebase is not easy to change, but it is easier to change safely than many repos of this size.

## Primary Liabilities

### Finding 1: `ShellWindow` is still the effective god object

Severity: **High**  
Confidence: **High**

Evidence:

- `ea_node_editor/ui/shell/window.py` is about 1725 LOC.
- Local AST analysis counted **329 methods** on `ShellWindow`.
- The file imports execution, graph, persistence, theming, dialogs, presenters, bridges, and workspace concerns directly (`ea_node_editor/ui/shell/window.py:15-114`).
- The composition root still attaches a very large dependency surface directly onto the host (`ea_node_editor/ui/shell/composition.py:76-209`, `ea_node_editor/ui/shell/composition.py:306-342`).

Why it matters:

- A facade is fine.
- A facade with this much surface area becomes the place where every new feature can "just land".
- Even when methods are delegations, the host still becomes the mental center of the app.

What this means architecturally:

- The repo has made progress from one giant constructor toward a composition root.
- It has **not** yet moved the true ownership center away from the host.

Recommended direction:

1. Treat `ShellWindow` as lifecycle and Qt ownership only.
2. Stop adding new application commands directly to `ShellWindow`.
3. Move behavior behind explicit services or presenters with narrow source interfaces.
4. Shrink the host API release by release instead of adding new compatibility methods.

### Finding 2: The bridge split is real, but weakened by host fallback and compatibility wrappers

Severity: **High**  
Confidence: **High**

Evidence:

- `ShellLibraryBridge`, `ShellWorkspaceBridge`, and `ShellInspectorBridge` all resolve their source by trying a presenter first and then falling back to the full host (`ea_node_editor/ui_qml/shell_library_bridge.py:87-93`, `ea_node_editor/ui_qml/shell_workspace_bridge.py:64-70`, `ea_node_editor/ui_qml/shell_inspector_bridge.py:53-59`).
- `GraphCanvasStateBridge` derives `_canvas_source` from `graph_canvas_presenter`, but still keeps the host attached and uses source indirection instead of a strict interface (`ea_node_editor/ui_qml/graph_canvas_state_bridge.py:48-71`).
- `GraphCanvasCommandBridge` routes many commands through source chains that can end at `ShellWindow` (`ea_node_editor/ui_qml/graph_canvas_command_bridge.py:37-50`).
- `GraphCanvasBridge` still exists as a compatibility wrapper over the state and command bridges (`ea_node_editor/ui_qml/graph_canvas_bridge.py:31-116`).

Why it matters:

- The bridge split is only partially authoritative if bridges still say "use presenter if available, otherwise the whole host".
- That makes ownership dynamic and less legible.
- New contributors still need to understand `ShellWindow` to understand many bridge behaviors.

Recommended direction:

1. Replace host fallback with explicit interface injection.
2. Make each bridge depend on exactly one source contract.
3. Keep `GraphCanvasBridge` as host-only compatibility if needed, but stop treating it as part of the primary architecture.

### Finding 3: The graph-canvas boundary contract has already drifted across code, docs, and tests

Severity: **High**  
Confidence: **High**

Evidence:

- `ARCHITECTURE.md` says `ShellWindow.graph_canvas_bridge` remains a host-side compatibility wrapper and packet-owned QML should use the focused state and command bridges instead (`ARCHITECTURE.md:56-66`, `ARCHITECTURE.md:117-125`).
- `shell_context_property_bindings()` registers `shellLibraryBridge`, `shellWorkspaceBridge`, `shellInspectorBridge`, `graphCanvasStateBridge`, and `graphCanvasCommandBridge`, but **does not** register `graphCanvasBridge` as a QML context property (`ea_node_editor/ui_qml/shell_context_bootstrap.py:46-66`).
- The focused verification run reproduced a failing test that still expects `graphCanvasBridge` in the QML context: `tests/main_window_shell/bridge_contracts.py:1470-1494`.

Why it matters:

- This is not just a failing test.
- It is proof that the intended contract is no longer single-source-of-truth.

Recommended direction:

1. Decide one policy explicitly.
2. My recommendation: keep `graphCanvasBridge` as a host-only compatibility alias and do not register it into packet-owned QML.
3. Update tests and docs to that single policy.

### Finding 4: The canvas and scene layer are too concentrated

Severity: **High**  
Confidence: **High**

Evidence:

- `ea_node_editor/ui_qml/components/GraphCanvas.qml`: about 930 LOC
- `ea_node_editor/ui_qml/graph_scene_bridge.py`: local AST count **116 methods**
- `ea_node_editor/ui_qml/graph_scene_mutation_history.py`: about 1197 LOC
- `ea_node_editor/ui_qml/graph_surface_metrics.py`: about 1368 LOC
- `ea_node_editor/ui_qml/edge_routing.py`: about 1223 LOC
- `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml`: about 1334 LOC

Why it matters:

- The repo's most interaction-heavy layer is also the most size-concentrated.
- That raises change cost even when architecture is directionally correct.
- Large presentation modules often force maintainers to understand geometry, interaction, performance policy, and compatibility behavior at the same time.

Important nuance:

- The helper extraction is real. `GraphSceneBridge` delegates to `GraphSceneMutationHistory`, `GraphScenePayloadBuilder`, and `GraphSceneScopeSelection` (`ea_node_editor/ui_qml/graph_scene_bridge.py:19-25`, `ea_node_editor/ui_qml/graph_scene_bridge.py:54-214`).
- The problem is that the extracted helpers are also large, so complexity has been redistributed more than reduced.

Recommended direction:

1. Split by responsibility, not by arbitrary line count:
   - graph-scene mutation operations
   - payload/materialization
   - geometry/routing
   - performance policy
   - host-bridge adaptation
2. Reduce the amount of command logic that can be routed back to the host from inside the canvas bridges.

### Finding 5: Core package boundaries are denser than the docs imply

Severity: **High**  
Confidence: **High**

Evidence:

- `WorkspaceData` and `WorkspaceSnapshot` carry `WorkspacePersistenceState` directly inside the graph model (`ea_node_editor/graph/model.py:164-205`, `ea_node_editor/graph/model.py:211-262`).
- `graph/file_issue_state.py` is artifact-resolution and repair-mode logic living under `graph` (`ea_node_editor/graph/file_issue_state.py:7-175`).
- The graph write path is split across raw `GraphModel` CRUD, `WorkspaceMutationService`, `GraphInvariantKernel`, `ValidatedGraphMutation`, and normalization helpers (`ea_node_editor/graph/model.py:353-419`, `ea_node_editor/graph/normalization.py:215-922`).
- `nodes/types.py` combines spec definitions, execution context, runtime references, and plugin descriptors in one high-fan-in file (`ea_node_editor/nodes/types.py:443-620`).

Import-density signals from local analysis:

- Highest fan-in:
  - `ea_node_editor.nodes.types`: 51
  - `ea_node_editor.graph.model`: 33
  - `ea_node_editor.ui.shell.window`: 26
- Highest fan-out:
  - `ea_node_editor.ui.shell.window`: 42
  - `ea_node_editor.ui.shell.composition`: 28
  - `ea_node_editor.nodes.bootstrap`: 14
  - `ea_node_editor.ui.shell.controllers.project_session_services`: 14
  - `ea_node_editor.ui_qml.graph_scene_mutation_history`: 14

Why it matters:

- The architecture is not a flat soup.
- It is, however, denser than a clean one-way stack.
- Dense packages are harder to refactor because changes in one place tend to pull multiple layers with them.

Recommended direction:

1. Move persistence overlays and file-issue logic out of `graph` or formalize them as explicit adapters.
2. Collapse the graph mutation path into one authoritative service boundary.
3. Split `nodes/types.py` into `node_specs`, `execution_context`, and `runtime_refs`.

### Finding 6: Project/session/document orchestration has duplicate active authorities

Severity: **High**  
Confidence: **High**

Evidence:

- `ProjectSessionController` constructs `ProjectFilesService`, `ProjectSessionLifecycleService`, and `ProjectDocumentIOService` (`ea_node_editor/ui/shell/controllers/project_session_controller.py:27-36`).
- The same controller still contains active `save_project`, `save_project_as`, `open_project_path`, and autosave-recovery prompt logic (`ea_node_editor/ui/shell/controllers/project_session_controller.py:237-466`).
- `ProjectDocumentIOService` in `project_session_services.py` contains another active implementation of the same save/open flows (`ea_node_editor/ui/shell/controllers/project_session_services.py:740-937`).
- `project_session_services.py` is about 938 LOC and mixes project files, session lifecycle, document IO, save-as artifact rewriting, and script editor persistence (`ea_node_editor/ui/shell/controllers/project_session_services.py:329-938`).

Why it matters:

- This is more than file size.
- It is duplicate authority, which is one of the fastest ways to make a codebase confusing and bug-prone.

Recommended direction:

1. Make `ProjectSessionController` a true facade.
2. Keep only one active implementation for save/open/recover/project-files flows.
3. Split `project_session_services.py` into focused modules:
   - `project_files_service.py`
   - `project_session_lifecycle.py`
   - `project_document_io.py`
   - optionally `project_metadata_service.py`

### Finding 7: Runtime, viewer, and plugin layers still carry compatibility debt

Severity: **High**  
Confidence: **Medium-High**

Evidence:

- The shell builds a registry at startup (`ea_node_editor/ui/shell/composition.py:306-342`), and the worker rebuilds a fresh registry during runtime preparation (`ea_node_editor/execution/worker_runtime.py:201-226`).
- `RuntimeSnapshot` is the intended execution boundary, but protocol/client/runtime code still keeps the legacy `project_doc` compatibility path alive (`ea_node_editor/execution/runtime_snapshot.py:154-203`, `ea_node_editor/execution/client.py:239-250`).
- `ViewerSessionService` is worker-side and already engineering-transport-aware (`ea_node_editor/execution/viewer_session_service.py`).
- `ViewerSessionBridge` keeps a separate UI-side viewer session state machine (`ea_node_editor/ui_qml/viewer_session_bridge.py:21-213`).
- `AsyncNodePlugin` claims thread-pool execution in docs, but worker execution is still `asyncio.run(...)` inline (`ea_node_editor/nodes/types.py:594-603`, `ea_node_editor/execution/worker_runner.py:377-383`).

Why it matters:

- Runtime/editor separation exists conceptually.
- The remaining compatibility seams still force cross-cutting awareness between authoring, runtime, and viewer flows.

Recommended direction:

1. Freeze registry construction into a manifest or descriptor set reused by both shell and worker.
2. Retire `project_doc` from normal execution paths.
3. Split viewer session logic into generic session core plus backend-specific strategies.
4. Align the async-node contract with actual behavior.

### Finding 8: The verification layer is strong, but brittle

Severity: **Medium**  
Confidence: **High**

Evidence:

- `tests/test_architecture_boundaries.py` checks exact source import strings (`tests/test_architecture_boundaries.py:10-34`).
- `tests/test_dead_code_hygiene.py` checks exact helper names and text snippets (`tests/test_dead_code_hygiene.py:21-49`).
- `scripts/verification_manifest.py` encodes "fresh-process shell isolation" as a truth of the repo (`scripts/verification_manifest.py:7-14`).
- A direct search found no inline `TODO` / `FIXME` / `HACK` markers across source, tests, scripts, docs, `README.md`, or `ARCHITECTURE.md`, which is clean but also means debt is documented away from the code.

Why it matters:

- The repo is very safe against accidental drift.
- It is not always cheap to refactor because some proof checks are token-based rather than behavior-based.

Recommended direction:

1. Replace some exact-string checks with AST or parsed-manifest checks.
2. Decide whether shell isolation is a temporary bug or an architectural constraint, then encode that more cleanly.
3. Keep architecture verification, but make it less fragile.

## Detailed Domain Review

### UI/QML shell and presentation

Strengths:

- `MainShell.qml` is a relatively clean composition root and uses focused context bridges rather than broad host globals (`ea_node_editor/ui_qml/MainShell.qml:7-78`).
- The composition root is explicit. `ui/shell/composition.py` divides state, primitives, controllers, presenters, context bridges, and timers (`ea_node_editor/ui/shell/composition.py:58-258`).
- Scene decomposition is real, not only documented (`ea_node_editor/ui_qml/graph_scene_bridge.py:19-25`).

Weaknesses:

- The host still owns too much surface.
- Focused bridges often remain thin adapters over presenter-or-host fallback.
- `GraphCanvas.qml`, `GraphSceneBridge`, and their helper modules still carry too much concentrated knowledge.
- `ViewerSessionBridge` is doing more than a passive UI bridge should.

Assessment:

- The UI architecture is directionally good.
- It is the biggest current maintainability hotspot.

### Graph/domain and mutation path

Strengths:

- `GraphModel` is still the canonical mutable project graph.
- Boundary adapters are a good corrective move.
- Passive authoring on the same graph is coherent in concept.

Weaknesses:

- `WorkspaceData` now embeds persistence concerns.
- `file_issue_state` is really artifact/persistence logic in the graph package.
- Mutation and normalization responsibilities are spread across too many overlapping APIs.
- `graph/transforms.py` has become a broad utility bucket for layout, fragment operations, grouping, and subnode behavior.

Assessment:

- The domain model still makes sense.
- The surrounding policy surface is too broad and no longer obviously layered.

### Persistence, workspace, session, and artifacts

Strengths:

- Serializer, codec, migration/normalization, overlay handling, and artifact storage are a solid base.
- Workspace ownership normalization is clean and useful (`ea_node_editor/workspace/ownership.py`).
- Artifact storage and resolution are real abstractions, not just path helpers.

Weaknesses:

- Project/session orchestration is duplicated and scattered.
- `project.metadata` is used as a typeless integration bus for UI state, workflow settings, custom workflows, artifact store metadata, and workspace order.
- `SessionAutosaveStore.persist_session()` stores a full `project_doc` inside the recent session payload (`ea_node_editor/persistence/session_store.py:77-93`), which duplicates large state with autosave.
- `WorkspaceManager` is helpful but still mostly fronts private `GraphModel` methods (`ea_node_editor/workspace/manager.py:39-77`).

Assessment:

- The persistence kernel is mostly good.
- The shell-side session and project-IO layer is where maintainability is weakest.

### Execution, runtime, plugins, and viewer flows

Strengths:

- The worker process split is real.
- The runtime snapshot idea is strong.
- Plugin provenance and registry validation are strong.

Weaknesses:

- Registry discovery is duplicated between startup and worker runtime preparation.
- `RuntimeSnapshot` is still diluted by `project_doc` compatibility.
- Viewer session responsibilities are split across worker and UI in a way that still feels transitional.
- `nodes/types.py` is too broad to be a stable SDK surface forever.

Assessment:

- This area is not broken.
- It is carrying debt that should be paid down before it becomes the next growth bottleneck.

### Tests, docs, and governance

Strengths:

- The repo is unusually disciplined for a desktop app.
- Verification commands and doc anchors are centralized in `scripts/verification_manifest.py`.
- Architecture and traceability checks are real, not aspirational.

Weaknesses:

- The proof layer itself is complicated.
- Some tests are token-based rather than behavior-based.
- Shell lifecycle testing still requires dedicated process isolation.
- One documented architecture contract has already drifted in the test suite.

Assessment:

- The verification culture is an asset.
- It now deserves its own cleanup pass to stay maintainable.

## Drift Between Documented and Implemented Architecture

### 1. `ShellWindow` is not yet "thin" in practice

`ARCHITECTURE.md` says `ShellWindow` is a thin facade that delegates to controllers and bridge helpers (`ARCHITECTURE.md:41-43`, `ARCHITECTURE.md:108-110`). That is true directionally, but not yet true operationally. The host still imports broadly and carries 329 methods.

Conclusion: **documented intent is ahead of implementation here**.

### 2. The focused-bridge migration is real, but the implementation still carries host fallback

`ARCHITECTURE.md` correctly describes `shellLibraryBridge`, `shellWorkspaceBridge`, `shellInspectorBridge`, `graphCanvasStateBridge`, and `graphCanvasCommandBridge` as the primary context surface (`ARCHITECTURE.md:54-66`). The code does implement that, but several bridges still resolve their source through presenter-or-host fallback.

Conclusion: **the migration is real, but ownership is not fully locked down**.

### 3. The `graphCanvasBridge` compatibility story is inconsistent across docs, code, and tests

`ARCHITECTURE.md` says `GraphCanvasBridge` remains a compatibility seam and new QML ownership should use the focused bridges (`ARCHITECTURE.md:63`, `ARCHITECTURE.md:119-121`). The code matches that: `graphCanvasBridge` is not registered into QML context properties (`ea_node_editor/ui_qml/shell_context_bootstrap.py:46-66`). But one remaining test still expects it there (`tests/main_window_shell/bridge_contracts.py:1470-1494`).

Conclusion: **this is the clearest current architecture-doc/test drift**.

### 4. `RuntimeSnapshot` is authoritative in intent, but not yet exclusive in implementation

The docs say run flows now build and submit `RuntimeSnapshot` payloads, while compatibility adapters remain narrow (`ARCHITECTURE.md:113`, `ARCHITECTURE.md:117-120`). The code mostly matches, but the legacy `project_doc` path still exists in runtime snapshot coercion and protocol handling (`ea_node_editor/execution/runtime_snapshot.py:154-203`, `ea_node_editor/execution/client.py:239-250`).

Conclusion: **the runtime boundary is improved, not fully closed**.

### 5. The README structure is broadly right but no longer a full mental map

`README.md` documents the major structure and recent architecture highlights well (`README.md:8-24`, `README.md:44-180`). It does not fully expose newer helper/service modules such as `project_session_services.py`, `context_bridges.py`, and the more layered QML bridge split. This is a mild drift, not a critical one.

Conclusion: **documentation quality is good, but the architecture has evolved beyond the simplified tree**.

## Refactor Priorities

### Immediate priorities

1. **Resolve the `graphCanvasBridge` contract drift**
   - Choose one policy for QML registration.
   - Update docs and tests to match.
   - This is a low-cost, high-clarity cleanup.

2. **Freeze `ShellWindow` growth**
   - Stop adding new host commands.
   - Require new bridge and presenter behavior to depend on explicit interfaces.
   - Treat current host methods as compatibility-only.

3. **Delete the duplicate project/session save-open implementations**
   - Keep one active authority for save, save-as, open, recover, and project-files flows.
   - Split `project_session_services.py`.

4. **Retire `project_doc` from normal execution paths**
   - Keep `RuntimeSnapshot` as the authoritative run payload.
   - Move compatibility to a narrow migration edge or remove it entirely.

### Medium-term priorities

5. **Split the highest-pressure modules**
   - `ea_node_editor/ui/shell/window.py`
   - `ea_node_editor/ui_qml/components/GraphCanvas.qml`
   - `ea_node_editor/ui_qml/graph_scene_mutation_history.py`
   - `ea_node_editor/ui_qml/graph_surface_metrics.py`
   - `ea_node_editor/ui_qml/edge_routing.py`
   - `ea_node_editor/graph/transforms.py`
   - `ea_node_editor/nodes/types.py`
   - `ea_node_editor/ui/shell/controllers/project_session_services.py`

6. **Narrow core package responsibilities**
   - Move file-issue and repair logic out of `graph`.
   - Reconsider whether persistence overlay state belongs on `WorkspaceData`.
   - Split `nodes/types.py` into smaller contracts.

7. **Make runtime and viewer seams explicit**
   - Freeze registry construction across shell and worker.
   - Split viewer session core from backend-specific logic.
   - Align async-node docs with actual execution semantics.

### Later priorities

8. **Simplify the proof layer**
   - Replace some token-based tests with AST or manifest-backed checks.
   - Reduce the cost of legitimate refactors.

9. **Decide what shell isolation means**
   - Either fix repeated `ShellWindow()` lifecycle so the workaround disappears,
   - or make the isolation boundary a clearly formalized constraint instead of a scattered workaround.

## Suggested Target Architecture Direction

### Host layer

- `ShellWindow` owns Qt lifecycle, root widget ownership, top-level windowing, and final signal wiring.
- It should not be the broad application-command API.

### Application-service layer

- Project/session service
- Workspace authoring service
- Run/viewer service
- Artifact coordination service
- Custom workflow repository

These should own policy. Bridges and presenters should consume them through narrow contracts.

### Presentation bridge layer

- Each bridge depends on one explicit source contract.
- No presenter-or-host fallback.
- `GraphCanvasBridge` stays compatibility-only until removed.

### Graph core

- Graph model
- Mutation service
- Invariant kernel
- Layout/fragment/subnode operations split into separate modules

Persistence overlays, file repair, and artifact concerns should sit outside or behind explicit adapters.

### Runtime

- `execution` should consume runtime DTOs and runtime context only.
- Authoring-to-runtime conversion should happen before the runtime package where possible.
- Viewer session should have a generic core and backend-specific implementations.

## Hotspot Appendix

### Source package distribution

Local scan of `ea_node_editor`:

| Package | Files | LOC |
| --- | ---: | ---: |
| `ui_qml` | 108 | 28,295 |
| `ui` | 66 | 20,281 |
| `nodes` | 30 | 6,510 |
| `execution` | 21 | 5,238 |
| `graph` | 12 | 4,766 |
| `persistence` | 10 | 2,310 |

Total scanned under `ea_node_editor`: **265 files**, **68,885 LOC**

Total scanned under `tests`: **126 files**, **46,060 LOC**

### Large-file density

| Area | Files >= 400 LOC | Files >= 800 LOC | Files >= 1200 LOC |
| --- | ---: | ---: | ---: |
| `ea_node_editor` | 60 | 15 | 7 |
| `tests` | 38 | 11 | 5 |

### Biggest source hotspots

| File | Approx LOC | Why it matters |
| --- | ---: | --- |
| `ea_node_editor/ui/perf/performance_harness.py` | 1902 | Dev/perf tooling concentration |
| `ea_node_editor/ui/shell/window.py` | 1725 | Effective host god object |
| `ea_node_editor/ui_qml/graph_surface_metrics.py` | 1368 | Geometry and surface policy concentration |
| `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml` | 1334 | Large rendering/presentation surface |
| `ea_node_editor/ui/shell/presenters.py` | 1308 | Presentation policy concentration |
| `ea_node_editor/ui_qml/edge_routing.py` | 1223 | Geometry/routing hotspot |
| `ea_node_editor/graph/transforms.py` | 1216 | Too many domain operations in one module |
| `ea_node_editor/ui_qml/graph_scene_mutation_history.py` | 1197 | Scene edit/history concentration |
| `ea_node_editor/ui_qml/graph_scene_bridge.py` | 792 | Large public scene contract |
| `ea_node_editor/persistence/artifact_store.py` | 765 | Cohesive but sizeable policy module |

### Biggest test hotspots

| File | Approx LOC | Signal |
| --- | ---: | --- |
| `tests/test_passive_graph_surface_host.py` | 3336 | Large GUI contract surface |
| `tests/test_graph_surface_input_contract.py` | 2083 | Broad interaction contract coverage |
| `tests/graph_track_b/scene_and_model.py` | 1787 | Large integrated scene tests |
| `tests/main_window_shell/bridge_contracts.py` | 1755 | Boundary contract coverage, now drifting |
| `tests/test_execution_worker.py` | 1447 | Large runtime behavior surface |

### Method-count hotspots from local AST analysis

| Class | Method Count | File |
| --- | ---: | --- |
| `ShellWindow` | 329 | `ea_node_editor/ui/shell/window.py` |
| `GraphSceneBridge` | 116 | `ea_node_editor/ui_qml/graph_scene_bridge.py` |
| `GraphCanvasBridge` | 78 | `ea_node_editor/ui_qml/graph_canvas_bridge.py` |
| `ProjectSessionController` | 48 | `ea_node_editor/ui/shell/controllers/project_session_controller.py` |
| `ShellWorkspacePresenter` | 29 | `ea_node_editor/ui/shell/presenters.py` |

### Internal import centrality

Highest fan-in:

| Module | Fan-in |
| --- | ---: |
| `ea_node_editor.nodes.types` | 51 |
| `ea_node_editor.graph.model` | 33 |
| `ea_node_editor.ui.shell.window` | 26 |
| `ea_node_editor.settings` | 22 |
| `ea_node_editor.graph.effective_ports` | 17 |

Highest fan-out:

| Module | Fan-out |
| --- | ---: |
| `ea_node_editor.ui.shell.window` | 42 |
| `ea_node_editor.ui.shell.composition` | 28 |
| `ea_node_editor.nodes.bootstrap` | 14 |
| `ea_node_editor.ui.shell.controllers.project_session_services` | 14 |
| `ea_node_editor.ui_qml.graph_scene_mutation_history` | 14 |

### Verification summary

| Command | Result | Takeaway |
| --- | --- | --- |
| `./venv/Scripts/python.exe -m pytest -q tests/test_architecture_boundaries.py tests/test_main_bootstrap.py tests/test_packaging_configuration.py` | `17 passed` | bootstrap and architecture boundary basics are healthy |
| `./venv/Scripts/python.exe -m pytest -q tests/test_dead_code_hygiene.py tests/test_run_verification.py tests/test_traceability_checker.py` | `26 passed, 3 subtests passed` | meta-verification and traceability checks are active and currently green |
| `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/main_window_shell/bridge_qml_boundaries.py tests/main_window_shell/bridge_contracts.py -q` | `1 failed, 33 passed, 315 subtests passed` | code and one bridge-contract test disagree about the `graphCanvasBridge` QML contract |

## Final Judgment

The repository is **architecturally good enough to keep building on**, but **not clean enough to safely absorb unlimited feature growth without cleanup**.

The right response is not a rewrite. The right response is a focused refactor program aimed at:

1. shrinking host-centered compatibility surfaces,
2. deleting duplicate authorities,
3. splitting the largest concentrated modules,
4. tightening the remaining bridge contracts, and
5. retiring legacy execution compatibility seams.

If that work is done soon, the existing architecture can scale. If it is postponed for too long, maintainability will degrade faster than the current test and doc discipline can compensate for.
