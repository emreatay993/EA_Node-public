# EA Node Editor Architecture Audit

Date: 2026-03-25  
Repository: `EA_Node_Editor`  
Audit scope: application architecture, graph/persistence, execution/runtime, node/plugin system, UI/QML boundary, test/tooling/docs health  
Audit mode: parallel subsystem reviews plus local static analysis and focused verification runs  

## Executive Summary

Overall verdict: **the architecture is mostly good, not bad, but it is carrying meaningful refactoring debt and should be cleaned up before it grows much further**.

This repo has a real architecture. The major subsystems are identifiable, the execution boundary is intentional, persistence is more disciplined than average, the shell/QML split is not accidental, and the project takes verification seriously. That is the good news.

The bad news is that several boundaries are eroding under compatibility baggage and concentrated hotspots:

1. `ShellWindow` still acts as a compatibility-centered god object.
2. The graph domain imports UI/QML helpers and duplicates invariants across multiple normalization paths.
3. Runtime code is clean in concept, but `execution/worker.py` has become an oversized cross-layer hub.
4. The UI/QML bridge migration is directionally correct, but it is incomplete and still carries wrapper-on-wrapper indirection.
5. Verification/docs/release tooling is strong but partially self-inconsistent, which creates maintainability risk outside the product code.

This is **not** a rewrite situation. It **is** a situation where important refactoring work is justified and should be scheduled deliberately.

## Bottom-Line Judgment

| Dimension | Assessment | Notes |
| --- | --- | --- |
| Macro decomposition | Good | Clear packages for `graph`, `persistence`, `execution`, `nodes`, `ui`, `ui_qml`, `workspace` |
| Boundary discipline | Mixed | Good intent, but compatibility seams and cross-layer imports are accumulating |
| Maintainability trend | Needs attention | Hotspot concentration is rising |
| Test posture | Good but drifting | Strong focused coverage, but several targeted runs expose contract drift |
| Docs/tooling health | Mixed | Serious verification culture, but docs and release-path truth are partially out of sync |
| Rewrite needed? | No | Core direction is sound |
| Important refactoring needed? | Yes | Several subsystems now justify structural cleanup |

## Audit Method

This audit combined:

- Parallel subsystem reviews for:
  - shell/bootstrap/application layer
  - graph domain and persistence
  - execution/runtime and plugin architecture
  - UI/QML and presentation boundary
  - repo health: tests, docs, scripts, packaging, traceability
- Local static analysis:
  - file-size hotspot review
  - import/dependency concentration review
  - import-cycle scan
- Focused verification samples in the project venv

This was **not** a full green-suite certification pass, a runtime profiler session, or a UX review with real users.

## What Is Working Well

- The repo has a real subsystem layout rather than one giant package.
- Startup/bootstrap is small and disciplined: `ea_node_editor/bootstrap.py`, `ea_node_editor/app.py`.
- Execution transport is typed and explicit: `ea_node_editor/execution/protocol.py`.
- `HandleRegistry` is a strong abstraction for worker-local non-serializable state: `ea_node_editor/execution/handle_registry.py`.
- Persistence is intentionally decomposed into serializer, codec, migration/normalization, resolver, artifact store, and session store.
- Unresolved-plugin preservation is thoughtful and better than average.
- Shell theming and graph theming are intentionally separated.
- The bridge-first QML migration is real, even if incomplete.
- The repo treats verification as a first-class concern instead of an afterthought.

## Static Signals And Hotspots

### Package size concentration

Local scan results for `ea_node_editor/`:

- `ea_node_editor/ui`: about **19.8k** lines of Python
- `ea_node_editor/ui_qml`: about **28.3k** lines across **24 Python**, **68 QML**, and **10 JS** files
- `ea_node_editor/nodes`: about **6.3k** lines
- `ea_node_editor/execution`: about **4.9k** lines
- `ea_node_editor/graph`: about **4.5k** lines

This is not automatically bad, but it does show where complexity is pooling.

### File hotspot inventory

| File | Size | Why it matters |
| --- | ---: | --- |
| `ea_node_editor/ui/shell/window.py` | 1725 lines | Main shell compatibility hub; still the de facto god object |
| `ea_node_editor/ui_qml/components/GraphCanvas.qml` | 1432 lines | Canvas composition plus compatibility fallbacks plus behavior plumbing |
| `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml` | 790 lines | Node chrome, hit-testing, style resolution, and surface-contract behavior all mixed |
| `ea_node_editor/ui_qml/graph_surface_metrics.py` | 1338 lines | Large geometry/metrics policy surface |
| `ea_node_editor/ui_qml/edge_routing.py` | 1165 lines | Geometry/routing logic; also pulled into other layers |
| `ea_node_editor/ui_qml/graph_scene_mutation_history.py` | 1125 lines | Scene edits, history, clipboard, geometry mixed together |
| `ea_node_editor/ui_qml/graph_scene_bridge.py` | 872 lines | Scene bridge still owns too many responsibilities |
| `ea_node_editor/graph/transforms.py` | 1265 lines | Layout, fragment ops, grouping, custom workflow snapshotting all mixed |
| `ea_node_editor/execution/worker.py` | 901 lines | Worker transport, orchestration, execution lifecycle, artifact handling mixed |
| `ea_node_editor/ui/shell/controllers/project_session_controller.py` | 903 lines | Project/session/files/artifact/session-recovery responsibilities bundled |

### Import-cycle and boundary signals

Local dependency scanning found two especially important patterns:

- A large strongly connected component linking `graph.model`, `graph.mutation_service`, `graph.normalization`, `graph.transforms`, `ui_qml.edge_routing`, and `ui_qml.graph_surface_metrics`.
  - This is a concrete warning that graph-domain logic and UI geometry logic are no longer cleanly separated.
- Another large strongly connected component linking `ui.shell.window`, `ui.shell.composition`, presenters, and multiple `ui_qml` bridge wrappers.
  - This matches the qualitative finding that the shell/QML migration exists, but old dependency direction still leaks through compatibility shims.

## Focused Verification Snapshot

These were targeted samples, not a full-suite pass.

### Green samples

- `venv/Scripts/python.exe -m pytest tests/test_run_verification.py tests/test_traceability_checker.py tests/test_packaging_configuration.py tests/test_dead_code_hygiene.py -q`
  - Result: `24 passed, 3 subtests passed`
- `venv/Scripts/python.exe scripts/check_traceability.py`
  - Result: `TRACEABILITY CHECK PASS`
  - Result: `8 passed`

### Drift signals from targeted failures

- `venv/Scripts/python.exe -m pytest tests/test_dead_code_hygiene.py tests/test_main_bootstrap.py tests/test_registry_validation.py -q --ignore=venv`
  - Result: `1 failed, 31 passed`
  - Failure: `tests/test_registry_validation.py:536`
  - Interpretation: node catalog / expectations drift

- `venv/Scripts/python.exe -m pytest tests/test_main_bootstrap.py tests/test_project_session_controller_unit.py tests/test_workspace_library_controller_unit.py tests/test_workspace_manager.py -q`
  - Result: `1 failed, 56 passed`
  - Failure: `tests/test_workspace_library_controller_unit.py:290`
  - Interpretation: controller contract drift, specifically a stub signature mismatch after API evolution

- `QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_serializer.py tests/test_serializer_schema_migration.py tests/test_project_artifact_store.py tests/test_project_artifact_resolution.py -q`
  - Result: `1 failed, 40 passed`
  - Failure: `tests/test_serializer_schema_migration.py:113`
  - Interpretation: normalization / migration / contract drift in persistence rules

These failures do **not** indicate architectural collapse. They do indicate that policy and compatibility surfaces are drifting in ways the architecture should be absorbing more cleanly.

## Highest-Priority Findings

## 1. Shell/Application Architecture Has Good Intent But Too Much Surface Area Still Lives In The Host

### Why this matters

The shell layer is meant to have a composition root, focused controllers, focused presenters, and focused QML bridges. That direction is correct. The problem is that the old center of gravity, `ShellWindow`, still owns or re-exports too much of the application.

### Evidence

- `ea_node_editor/ui/shell/window.py:141`
  - `ShellWindow` remains the main compatibility and orchestration surface.
- `ea_node_editor/ui/shell/composition.py:214-260`
  - `build_composition()` mutates the host while building dependencies, and bootstrap then re-attaches them.
- `ea_node_editor/ui/shell/controllers/project_session_controller.py:37-45`
  - Host protocol is broad.
- `ea_node_editor/ui/shell/controllers/project_session_controller.py:62`
  - `ProjectSessionController` owns too many concerns.
- `ea_node_editor/ui/shell/controllers/workspace_library_controller.py:18-144`
  - Capability wrappers mostly bounce through the same façade.
- `ea_node_editor/ui/shell/presenters.py:640-820`
  - `ShellWorkspacePresenter` exposes state but also drives application behavior and applies preferences.

### Architectural judgment

This is **not** a missing-architecture problem. It is a **half-finished migration problem**. The composition split exists, but much of the responsibility never fully moved out of the host façade.

### Refactor priority

High.

### Recommended direction

- Shrink `ShellWindow` into a true host shell:
  - lifecycle
  - final Qt ownership
  - show/close integration
  - no broad business façade behavior
- Make `build_shell_window_composition()` pure data construction.
- Split `ProjectSessionController` into narrower services:
  - project document IO
  - session/autosave recovery
  - project files / managed artifacts coordination
- Replace capability-loop indirection in `WorkspaceLibraryController` with direct narrow dependency injection.
- Move modal prompting behind abstractions instead of calling dialogs directly from controllers.

## 2. The Graph Domain Is No Longer Cleanly Separated From UI Geometry And Preview Policy

### Why this matters

The graph layer should define domain state and mutation rules. It should not depend directly on UI preview providers or QML geometry utilities.

### Evidence

- `ea_node_editor/graph/mutation_service.py:24-25`
  - imports `ea_node_editor.ui.pdf_preview_provider.clamp_pdf_page_number`
  - imports `ea_node_editor.ui_qml.edge_routing.node_size`
- `ea_node_editor/graph/mutation_service.py:342`
  - uses `node_size(...)` in mutation-time geometry decisions
- `ea_node_editor/graph/mutation_service.py:430`
  - uses `clamp_pdf_page_number(...)` during mutation/property normalization

### Architectural judgment

This is the clearest boundary violation in the repo. It makes the graph layer depend on presentation logic and preview semantics, which increases coupling and contributes directly to import cycles.

### Refactor priority

High.

### Recommended direction

- Introduce injected adapters or application-layer services for:
  - node geometry measurement
  - PDF page-number normalization
- Keep the graph package responsible for mutation rules, not for acquiring UI-derived geometry or preview-derived metadata.

## 3. Invariant And Normalization Policy Is Split Across Too Many Paths

### Why this matters

A graph/persistence system can have multiple callers, but it should not have multiple policy copies. Right now the repo has overlapping graph-admission and normalization logic spread across edit-time validation, fragment normalization, load-time normalization, migration normalization, and codec behavior.

### Evidence

- `ea_node_editor/graph/normalization.py:224`
- `ea_node_editor/graph/normalization.py:590`
- `ea_node_editor/graph/normalization.py:660`
- `ea_node_editor/persistence/migration.py:195`
- `ea_node_editor/persistence/project_codec.py:243`
- `ea_node_editor/graph/transforms.py:544`
- Failing focused persistence test:
  - `tests/test_serializer_schema_migration.py:113`

### Architectural judgment

This is not a single bug. It is a structural drift problem. The more places policy is copied, the more likely the repo is to produce “mostly works, but edge cases disagree” behavior.

### Refactor priority

High.

### Recommended direction

- Create a single invariant engine for:
  - registry node resolution
  - exposed port normalization
  - edge validation / acceptance
  - fragment node normalization
  - fragment edge normalization
- Make load-time, edit-time, runtime, migration, and fragment callers share that policy instead of re-encoding variants.

## 4. Execution Architecture Is Conceptually Strong But Now Bottlenecked By Hotspots

### Why this matters

The runtime pipeline is actually one of the better parts of the repo conceptually:

- authoring graph
- runtime snapshot
- compiled runtime workspace
- typed worker command/event protocol
- worker execution

The problems are implementation concentration and compatibility residue, not missing concepts.

### Evidence

- `ea_node_editor/execution/runtime_snapshot.py:19-156`
- `ea_node_editor/execution/compiler.py:12-407`
- `ea_node_editor/execution/protocol.py`
- `ea_node_editor/execution/handle_registry.py:37-176`
- `ea_node_editor/execution/worker.py`

### Key sub-findings

- `execution/worker.py` mixes:
  - command parsing
  - run control
  - event publishing
  - execution planning
  - artifact path service
  - node execution
  - workflow orchestration

- `RuntimeSnapshot` is declared frozen but node code mutates its metadata:
  - `ea_node_editor/execution/runtime_snapshot.py:19`
  - `ea_node_editor/nodes/output_artifacts.py:109-115`
  - `tests/test_process_run_node.py:96-156`

- Legacy `project_doc` compatibility still leaks through:
  - `ea_node_editor/execution/runtime_snapshot.py:107-156`
  - `ea_node_editor/execution/protocol.py:423-431`
  - `ea_node_editor/execution/worker.py:665-687`

- `ExecutionContext` exposes `worker_services: Any`, which acts like a service locator:
  - `ea_node_editor/nodes/types.py:454-512`

### Architectural judgment

The runtime architecture is **good but overloaded**. It needs decomposition, not reinvention.

### Refactor priority

High.

### Recommended direction

- Split `execution/worker.py` into focused modules:
  - command loop
  - run control
  - node executor
  - workflow runner
  - execution plan
- Separate immutable run input from mutable execution scratch state.
- Collapse `project_doc` compatibility into a single edge adapter.
- Replace broad `worker_services` escape hatches with explicit typed capabilities.

## 6. The UI/QML Architecture Is Directionally Good, But The Bridge Migration Is Incomplete

### Why this matters

The repo has already done valuable work to move away from raw `mainWindow`/scene globals and toward focused bridges. That direction should be finished rather than abandoned.

### Evidence

- Good direction:
  - `ea_node_editor/ui_qml/shell_context_bootstrap.py`
  - `ea_node_editor/ui_qml/MainShell.qml`
  - `ea_node_editor/ui/theme/*`
  - `ea_node_editor/ui/graph_theme/*`

- Incomplete migration:
  - `ea_node_editor/ui_qml/components/GraphCanvas.qml:11-63`
    - still carries `mainWindowBridge`, `sceneBridge`, `viewBridge`, and `graphCanvasBridge` fallbacks
  - `ea_node_editor/ui_qml/shell_context_bootstrap.py:129-133`
    - still registers deferred compatibility surfaces such as `consoleBridge`, `workspaceTabsBridge`
  - `ea_node_editor/ui/shell/composition.py:417-450`
    - duplicates bridge creation that also exists in `ui_qml/shell_context_bootstrap.py:39-80`
  - `ea_node_editor/ui_qml/graph_canvas_bridge.py`
  - `ea_node_editor/ui_qml/graph_canvas_command_bridge.py`
    - still chain behavior back through `shell_window` / `graph_canvas_presenter`

- Scene-layer ownership remains mixed:
  - `ea_node_editor/ui_qml/graph_scene_bridge.py:21-24`
    - imports shell runtime clipboard/history helpers
  - `ea_node_editor/ui_qml/graph_scene_mutation_history.py:29-47`
    - mixes scene edits, clipboard normalization, history semantics, geometry helpers

### Architectural judgment

The UI/QML architecture is **good under load, but not cleanly finished**. The cost right now is compatibility indirection and oversized orchestration files.

### Refactor priority

High.

### Recommended direction

- Finish the bridge migration:
  - make `graphCanvasStateBridge` and `graphCanvasCommandBridge` authoritative
  - retire `graphCanvasBridge`, `mainWindowBridge`, `sceneBridge`, `viewBridge` from packet-owned QML
  - migrate remaining compatibility consumers such as `ea_node_editor/ui/perf/performance_harness.py:786-800` before removing old canvas globals
- Shrink `GraphCanvas.qml` into a true composition root
- Split `GraphNodeHost.qml` so theme/chrome, hit-testing, and surface-contract behavior are no longer carried by one node wrapper
- Split scene responsibilities:
  - payload building
  - selection/scope behavior
  - mutation/history
  - clipboard
- Split geometry policy out of current monoliths:
  - `ui_qml/graph_surface_metrics.py`
  - `ui_qml/edge_routing.py`
- Move hard-coded dialog styling back onto shared theme-aware helpers:
  - `ea_node_editor/ui/dialogs/graph_theme_editor_dialog.py:83-94`
  - `ea_node_editor/ui/dialogs/graph_theme_editor_dialog.py:247-267`

## 7. Persistence Is Pragmatic, But Recovery/Overlay State Has Leaked Into The Live Domain Model

### Why this matters

The unresolved-plugin and authored-override story is thoughtful, but it currently lives directly on `WorkspaceData`, which makes the live model carry persistence-envelope responsibilities.

### Evidence

- `ea_node_editor/graph/model.py:211-240`
  - `WorkspaceData.persistence_state` plus unresolved/authored override accessors
- `ea_node_editor/graph/model.py:164-205`
  - `WorkspaceSnapshot` also carries persistence state
- `ea_node_editor/persistence/project_codec.py:125-180`
  - runtime-vs-authored document flavor is subtle
- `ea_node_editor/persistence/project_codec.py:239`
  - unresolved preservation path is meaningful but hidden

### Architectural judgment

This is a reasonable compatibility design, but it is becoming too implicit. It makes “what is the domain model?” less obvious than it should be.

### Refactor priority

Medium-high.

### Recommended direction

- Wrap persistence overlays in a clearly named persistence envelope instead of letting them feel like ordinary domain fields.
- Make runtime and persistent document flavors explicit:
  - separate codec classes
  - or explicit `DocumentFlavor.RUNTIME` / `DocumentFlavor.AUTHORED`

## 8. Plugin And Output-Artifact APIs Need Finishing Passes

### Why this matters

This area is not structurally broken, but it still contains too many “temporary but still public” seams.

### Evidence

- Multiple registration modes remain:
  - `ea_node_editor/nodes/plugin_loader.py:27-40`
  - `ea_node_editor/nodes/registry.py:54-62`
  - `ea_node_editor/nodes/bootstrap.py:40-75`
- Package manager still imports private loader internals:
  - `ea_node_editor/nodes/package_manager.py:295-305`
- Artifact output code touches private persistence internals:
  - `ea_node_editor/nodes/output_artifacts.py:109-115`
  - `ea_node_editor/nodes/builtins/integrations_process.py:71-92`

### Architectural judgment

The repo invented cleaner abstractions here, but did not fully migrate to them. That is classic refactoring debt.

### Refactor priority

Medium-high.

### Recommended direction

- Finish descriptor-first plugin registration for built-ins.
- Expose a public package-discovery API so `package_manager` stops importing private helpers.
- Add a supported public artifact-output API on `ProjectArtifactStore`.
- Stop mutating `_state` and calling private cleanup helpers from node code.

## 9. Verification, Docs, And Release Tooling Are Serious But Partially Self-Inconsistent

### Why this matters

This repo is unusually serious about verification and proof documents. That is a strength. The problem is that the proof layer is now large enough that it can report green while important semantic drift still exists.

### Evidence

- Strong verification architecture:
  - `scripts/run_verification.py`
  - `scripts/verification_manifest.py`
  - `scripts/check_traceability.py`

- Release-path drift:
  - `scripts/build_windows_package.ps1:27-30`
  - `scripts/build_windows_installer.ps1:124-129`
  - `scripts/sign_release_artifacts.ps1:7-9`
  - `scripts/sign_release_artifacts.ps1:28-39`

- Docs drift:
  - `docs/specs/INDEX.md:28-29`
    - links to missing packet files
  - `docs/PACKAGING_WINDOWS.md:31-36`
  - `docs/PACKAGING_WINDOWS.md:91-98`
    - documentation no longer matches packaging profile layout

- Test collection coupled to script-layer manifest:
  - `tests/conftest.py:16-17`

### Architectural judgment

The repo is **well-instrumented but partially self-inconsistent**. This is not a code architecture failure, but it is a maintainability and release-safety issue.

### Refactor priority

Medium-high.

### Recommended direction

- Create a single source of truth for release layout.
- Split proof/traceability metadata into smaller declarative pieces.
- Add semantic repo-health checks:
  - markdown link validation
  - packaging-path consistency tests
  - docs drift checks
- Separate canonical docs from archived process history.

## Subsystem-by-Subsystem Assessment

## Shell / Bootstrap

Status: **Good direction, important cleanup needed**

Keep:

- `ea_node_editor/bootstrap.py`
- `ea_node_editor/app.py`
- `ea_node_editor/app_preferences.py`
- bridge-first shell/QML direction

Refactor:

- `ea_node_editor/ui/shell/window.py`
- `ea_node_editor/ui/shell/composition.py`
- `ea_node_editor/ui/shell/controllers/project_session_controller.py`
- `ea_node_editor/ui/shell/controllers/workspace_library_controller.py`
- `ea_node_editor/ui/shell/presenters.py`

## Graph / Persistence / Custom Workflows

Status: **Mostly good, but boundary cleanup is now important**

Keep:

- simple core model in `ea_node_editor/graph/model.py`
- additive artifact-ref strategy
- unresolved-plugin preservation behavior
- deterministic serializer ordering

Refactor:

- remove UI/QML imports from `graph/mutation_service.py`
- centralize invariant logic
- split `graph/transforms.py`
- validate imported custom workflow fragments
- make migration/document-flavor contracts explicit

## Execution / Nodes / Plugins

Status: **Conceptually strong, implementation hotspots need decomposition**

Keep:

- compile/runtime split
- typed protocol
- handle registry
- worker services composition

Refactor:

- split `execution/worker.py`
- make `RuntimeSnapshot` semantics honest
- remove lingering `project_doc` compatibility from core runtime path
- finish descriptor-first/plugin-loader cleanup
- clean up artifact output API boundaries

## UI / QML / Theme / Dialogs

Status: **Directionally good, bridge migration incomplete**

Keep:

- shell-owned overlays in `MainShell.qml`
- bridge-first boundary direction
- shell-theme vs graph-theme split

Refactor:

- finish bridge migration
- shrink `GraphCanvas.qml`
- split `graph_scene_bridge.py` and `graph_scene_mutation_history.py`
- split geometry policy in `graph_surface_metrics.py` and `edge_routing.py`
- clean up large dialogs after canvas/bridge work

## Docs / Scripts / Packaging / Verification

Status: **Strong culture, but single-source-of-truth drift is real**

Keep:

- verification modes and shell-isolation discipline
- packaging configuration tests

Refactor:

- release layout truth
- proof metadata layering
- semantic documentation validation
- canonical-vs-archival doc separation

## Recommended Refactoring Roadmap

## Phase 1: Highest-Leverage Boundary Repairs

Schedule first.

1. Remove UI/QML dependencies from `graph/mutation_service.py`.
2. Centralize graph/persistence invariant logic into one engine.
3. Make `RuntimeSnapshot` semantics explicit and honest.
4. Fix release-path truth across packaging, installer, signing, and docs.
5. Finish the bridge migration so packet-owned QML depends only on authoritative focused bridges.

Expected payoff:

- lower cross-layer coupling
- clearer runtime/persistence contracts
- less architectural drift
- immediate maintainability gain without broad rewrites

## Phase 2: Decompose The Largest Hotspots

Schedule next.

1. Split `ui/shell/window.py` and narrow its role.
2. Split `ProjectSessionController`.
3. Split `execution/worker.py`.
5. Split `GraphCanvas.qml`, `graph_scene_bridge.py`, `graph_scene_mutation_history.py`, and geometry modules.
6. Split `graph/transforms.py`.

Expected payoff:

- smaller change surfaces
- better local reasoning
- easier testing
- reduced regression risk

## Phase 3: Add Architectural Guardrails

Schedule after the first decomposition steps land.

1. Add import-boundary tests:
   - graph may not import UI/QML
   - built-in node modules may not import execution protocol directly without explicit allowance
2. Add compatibility-debt guardrails:
   - ban reintroduction of old QML context globals
   - architecture-pressure tests for façade size or slot/property budgets
3. Add tooling guardrails:
   - markdown link checker
   - packaging/signing path consistency tests
   - canonical docs drift tests
4. Finish descriptor-only built-in registration and public artifact-output APIs.

## What Should Be Preserved

Refactoring should **preserve**, not erase, the strongest patterns already present:

- small bootstrap/app startup chain
- focused app-preferences normalization
- typed execution protocol
- handle registry design
- additive artifact-reference strategy
- unresolved-plugin round-trip guarantees
- shell-theme vs graph-theme separation
- bridge-first QML direction
- serious verification culture

## Final Verdict

The repo **does not require an architectural rewrite**.

It **does require important refactoring and cleanup** in a few concentrated places:

1. shell host / compatibility façade
2. graph-domain boundary discipline and invariant centralization
3. execution worker decomposition
4. UI/QML bridge completion and scene/canvas hotspot reduction
5. release/docs/proof single-source-of-truth cleanup

If those areas are addressed deliberately, maintainability and understandability should improve substantially without changing the overall architectural direction of the project.
