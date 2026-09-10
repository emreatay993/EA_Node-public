# COREX Maintainability And Ownership Refactor

Status: `COMPLETED — T00–T08 ACCEPTED`

## Summary

This plan refactors six evidence-backed ownership and duplication problems on
the current `main` checkout:

1. Consolidate node-package schema and validation policy.
2. Reown runtime-value contracts and artifact-reference grammar.
3. Split Library, Inspector, and Quick Insert projections into direct owners.
4. Move graph cursor/style behavior to `GraphCanvasHostPresenter` and delete
   forwarding chains.
5. Normalize Tabular query behavior once while retaining optimized Python and
   Arrow evaluators.
6. Replace duplicated inline/fullscreen video logic with one playback core.

Tests move with their production owners. Residual shell-test cleanup follows
only after every removed test has a collecting equivalent. One final
integration owner updates shared maps, indexes, verification routing, and
retained evidence.

Implementation runs directly on `main`, with one commit per accepted task and
no push. The protected pre-existing dirty paths are:

- `docs/specs/INDEX.md`
- `docs/PLAN_COREX_Physical_Simulation_Backend.md`
- `scripts/Strain_Gage_Positioning/modular_version/strain_candidate_points.csv`

## Key Changes

### Orchestration and Git discipline

- The primary agent is the orchestrator and integration owner. One delegated
  implementation writer works at a time because all agents share this checkout.
- Each production task gets a focused verifier and independent read-only
  reviewer. The orchestrator alone stages and commits.
- Shared maps, generated indexes, architecture guards, and the QA ledger are
  integrated after the task writer finishes.
- Before every task, and after any context compaction, reread `AGENTS.md`, this
  plan, the QA ledger, `git status --short --branch`, and the last accepted
  commit plus next incomplete ledger row.
- Use exact-path or exact-hunk staging. Run `git diff --cached --check` and
  inspect the complete cached diff before every commit.
- Add no compatibility adapter, forwarding barrel, generic factory, dependency,
  or speculative abstraction.

### Selected audit findings

- Package validation policy is duplicated across loader, manager, and immutable
  generation verification.
- Runtime carriers, image parsing, codecs, durable validation, and shared
  artifact grammar have blurred ownership.
- Library, Inspector, and Quick Insert share a mixed owner and duplicate
  category-tree construction.
- `ShellWindow` and `ShellHostPresenter` retain graph-style/cursor forwarding
  chains.
- Tabular preview semantics are duplicated between Python-row and Arrow paths.
- Inline and fullscreen video renderers duplicate playback and state behavior.

Success requires deletion of replaced behavior and zero new dependencies; no
line-count quota is imposed.

### Explicitly deferred

- Execution-client physical file splitting.
- Registry and persistence monolith splitting.
- `GraphNodePortsLayer.qml` decomposition.
- Native viewer/plot handoff unification.
- Fullscreen overlay/bridge decomposition beyond shared video behavior.
- `GraphCanvasRootApi` direct dispatch or graph-canvas ownership redesign.
- Wholesale thin-shell replacement, QML runner replacement, global fixture
  rescoping, verification-manifest splitting, or source/test-index deletion.

## Public Interface Changes

- Current `.cxproj`, fragment, workflow, preferences, and schema-2 plugin
  packages remain readable. Their schemas and migration rules do not change.
- The 17-name top-level `corex` authoring API remains unchanged.
- Intentional internal import breaks:
  - delete add-on forwarding from `nodes.plugin_loader`; callers use
    `addons.catalog`;
  - move `AddOnState` and `AddOnRecord` to add-on ownership without aliases;
  - delete `persistence.artifact_refs`; callers use `common.artifact_refs`;
  - delete `runtime_contracts.runtime_values`; callers use defining runtime
    modules or the intentional `runtime_contracts` package surface;
  - delete `ui.shell.window_library_inspector`; callers use the new projection
    owners;
  - remove graph cursor/style methods from `ShellWindow` and
    `ShellHostPresenter`; `GraphCanvasHostPresenter` owns them.
- `GraphCanvasCommandBridge`, action IDs, QML context names, video state keys,
  Media Panel behavior, and `TabularLoaderCacheService` remain stable.
- No compatibility alias is retained for a removed internal path.

## Execution Tasks

### T00 Establish the tracked plan, ledger, and baseline

- **Goal:** Create the compaction-safe control artifacts and capture the
  pre-refactor state.
- **Preconditions:** Reconfirm `HEAD`, upstream, dirty paths, and requirements.
- **Conservative write scope:** This plan, the QA ledger, and exact additions to
  `docs/specs/INDEX.md`.
- **Deliverables:** One task table and one test-migration table in the QA ledger;
  collected affected node IDs; current focused commands and failures.
- **Verification:** `full --dry-run`, one summarized fast baseline,
  traceability, Markdown links, and diff hygiene.
- **Non-goals:** No production refactoring or performance conclusion.
- **Commit:** `Plan COREX maintainability ownership refactor`.

### T01 Consolidate node-package schema and validation policy

- **Goal:** Give schema-2 package policy one owner without weakening repeated
  trust-boundary verification.
- **Preconditions:** T00 accepted.
- **Conservative write scope:** Package schema, plugin loader/manager/generation,
  add-on contracts/catalog, direct tests, and owning maps.
- **Deliverables:**
  - Centralize manifest fields, member paths, suffixes, size limits, hash syntax,
    node inventory comparison, and canonical validation.
  - Return one internal validated-package result to loader and manager.
  - Preserve independent reads, bounds checks, hashes, and attestations at
    archive import, installed discovery, immutable generation, and worker load.
  - Remove `package_manager -> plugin_loader._prepare_package`.
  - Remove add-on forwarding functions from `plugin_loader`.
  - Move `AddOnState` and `AddOnRecord` to `addons/contracts.py`.
- **Verification:** Plugin loader, package manager, runtime agreement, worker
  loading, package IO, architecture, dead-code, and hostile-input tests; an
  independent security review.
- **Performance:** Matched discovery/import/export runs and structural proof of
  no extra directory/member pass.
- **Non-goals:** No registry split, fingerprint redesign, schema change, cached
  trust shortcut, or generic package framework.
- **Commit:** `Consolidate node package schema validation`.

### T02 Reown runtime values and artifact-reference grammar

- **Goal:** Separate distinct runtime contracts and move dependency-light
  artifact grammar out of persistence.
- **Preconditions:** T01 accepted.
- **Conservative write scope:** Common artifact grammar, runtime-contract
  modules, direct import updates, focused tests, and owning maps.
- **Deliverables:**
  - Move managed/staged artifact grammar to `common/artifact_refs.py`.
  - Split image parsing, value references, recursive codecs, and durable-value
    validation into defining modules.
  - Move only identical strict payload primitives to `common/payload_tools.py`.
  - Keep `common` independent from graph, execution, persistence, nodes, and UI.
  - Preserve intentional `runtime_contracts` package exports while deleting the
    old direct modules.
- **Verification:** Typed runtime values, solution records, protocol, serializer,
  artifact-store, architecture, import-cycle, and export tests.
- **Performance:** Matched scalar, DataTree, image, artifact, and durable-output
  codec runs plus import/copy observations.
- **Non-goals:** No carrier-format change, persistence decomposition, schema
  engine, or catalog-policy redesign.
- **Commit:** `Reown runtime value contracts`.

### T03 Split Library, Inspector, and Quick Insert projections

- **Goal:** Replace the mixed projection owner with three direct routes and one
  category-tree implementation.
- **Preconditions:** T02 accepted.
- **Conservative write scope:** New projection modules, shell presenters/state,
  direct tests, and UI-shell maps.
- **Deliverables:**
  - `library_projection.py` owns rows, filters, category options, one category
    tree, display projections, and usage ranking.
  - `inspector_projection.py` owns selected-node header, links, properties,
    ports, path/source presentation, and editor metadata.
  - `quick_insert_projection.py` owns canvas/connection matching, accepted-type
    unions, and ranking.
  - Delete `window_library_inspector.py` and update callers directly.
  - Split its tests by the same owners.
- **Verification:** New owner tests plus data-type, graph-type, property-adapter,
  media-source, sensitive-control, and viewer projection tests.
- **Performance:** Matched library rebuild and connection Quick Insert timings;
  one category-tree construction per request.
- **Non-goals:** No QML change, generic tree library, registry redesign, or
  visual behavior change.
- **Commit:** `Split library inspector and quick insert projections`.

### T04 Make `GraphCanvasHostPresenter` the graph-host owner

- **Goal:** Remove the remaining graph-action forwarding cycle.
- **Preconditions:** T03 accepted.
- **Conservative write scope:** Graph-canvas presenter, shell host presenter,
  ShellWindow state, presenter contracts/composition, action tests, and maps.
- **Deliverables:**
  - Move cursor application, passive-node/flow-edge style dialogs, preset
    persistence, clipboard normalization, label editing, and mutation dispatch
    into `GraphCanvasHostPresenter`.
  - Call graph scene and project-session owners directly.
  - Delete corresponding `ShellHostPresenter` and `ShellWindow` methods.
  - Retain app-wide dialogs, theme/settings, status, and non-graph shell behavior
    in `ShellHostPresenter`.
- **Verification:** Graph-canvas presenter, graph-action, style preset/dialog,
  split-bridge, focused shell-route, and architecture tests.
- **Performance:** Matched shell-create and graph-action timing; no extra QObject,
  timer, provider, or dispatch hop.
- **Non-goals:** No canvas direct dispatch, graphics-ownership change, toolbar
  extraction, or rendering change.
- **Commit:** `Consolidate graph host action ownership`.

### T05 Decompose Tabular around one normalized query

- **Goal:** Remove duplicated preview semantics while retaining specialized fast
  evaluators and one cache owner.
- **Preconditions:** T02 and T04 accepted.
- **Conservative write scope:** Tabular cache service, source backends, preview
  query, tests, and maps.
- **Deliverables:**
  - Keep `TabularLoaderCacheService` as cache/ref/lock/eviction coordinator.
  - Move format-specific scan/read/convert behavior to `source_backends.py`.
  - Add one immutable normalized query covering columns, filters, search, sort,
    offset, and limit.
  - Evaluate it through Arrow-vectorized and bounded Python-row paths.
  - Preserve locks, cache reuse, streaming, lazy imports, PyArrow preload,
    materialization gates, zero-I/O scene rebuild, and DuckDB exclusion.
- **Verification:** Loader, performance guard, native runtime, preview provider,
  input-node, and Python/Arrow parity tests.
- **Performance:** Matched cold/warm runs on one ignored 400 MB generated project.
- **Non-goals:** No new dependency, generic slow evaluator, cache-owner move, or
  UI-thread conversion.
- **Commit:** `Normalize tabular preview queries`.

### T06 Share video playback and state behavior

- **Goal:** Replace duplicated inline/fullscreen video behavior while retaining
  distinct host responsibilities.
- **Preconditions:** T04 and T05 accepted.
- **Conservative write scope:** Video renderers, new playback core, Python video
  state normalization, fullscreen/scene callers, media tests, and maps.
- **Deliverables:**
  - `GraphMediaVideoPlaybackCore.qml` owns player/audio lifecycle, seeking, clip
    enforcement, markers, bookmarks, thumbnail priming, playback rate, time
    formatting, and canonical transient state.
  - Inline retains property persistence, node actions, capture/timestamps,
    selection/autoplay, and artifact release.
  - Fullscreen retains controls, trim calls, resume policy, and close handoff.
  - `ui/media_video_state.py` becomes the single Python normalization owner.
  - Prove only one decoder/playback owner is active in fullscreen.
- **Verification:** Media Panel, QML surface, fullscreen bridge/lifecycle, Qt
  Quick graph controls, one shell lifecycle scenario, then one GUI lane.
- **Performance:** Matched `animated_media` runs for latency, CPU, RSS, animator,
  suspension, and decoder count.
- **Non-goals:** No fullscreen-overlay breakup, bridge redesign, toolbar
  extraction, media schema change, or second browser/player.
- **Commit:** `Share video playback state and controls`.

### T07 Reown residual tests and shrink shell isolation conditionally

- **Goal:** Finish ownership migration without repeating the failed wholesale
  thin-shell rewrite.
- **Preconditions:** T01-T06 accepted and their tests co-committed.
- **Conservative write scope:** Ledger-proven residual tests, direct owner suites,
  shell catalogs when entries become unnecessary, and testing maps.
- **Deliverables:**
  - Pure QML behavior moves to QuickTest; presenter/service behavior moves to
    direct Python tests; bridge projections use explicit sources.
  - Real shell tests retain composition, context identity, native parenting,
    mount/reset, timer cancellation, and deterministic teardown only.
  - Source-text assertions are removed only after executable or AST replacement.
  - Shell-isolation entries are removed only after collecting replacements pass.
- **Verification:** Before/after collection inventories, every ledger replacement,
  shell-isolation phase checks, `full --dry-run`, and repeated lifecycle runs.
- **Non-goals:** No QML runner rewrite, timeout reduction, global fixture change,
  verification-manifest split, source/test-index deletion, or forced catalog
  elimination.
- **Commit:** `Reown residual shell tests` only when real changes remain;
  otherwise record an accepted no-op.

### T08 Integrate, review, and close out

- **Goal:** Produce a reviewed, navigable, correctness-green commit series with
  honest performance evidence.
- **Preconditions:** T01-T07 accepted or explicitly recorded no-op.
- **Conservative write scope:** Plan/QA status, affected maps/banners, generated
  navigation, changed verification routing, and final guards.
- **Deliverables:**
  - Update maps and coverage; regenerate affected indexes.
  - Finalize task, test, performance, review, and commit evidence.
  - Mark this plan completed and retain the QA matrix in the spec index.
  - Run independent ownership, correctness/security, and performance reviews.
- **Verification:** Task-focused suites, map/traceability/link checks, generator
  checks, one summarized full verification, diff hygiene, and staged privacy
  audit.
- **Acceptance:** No new correctness, security, data-loss, collection, or trust
  failure. Noisy performance evidence may be `INCONCLUSIVE` but not mislabeled.
- **Non-goals:** No push, release build, installer, or unrelated cleanup.
- **Commit:** `Close COREX maintainability ownership refactor`.

## Work Packet Conversion Map

These are delegation labels only; do not create packet manifests.

1. `P00 Bootstrap` -> T00
2. `P01 Node Package Policy` -> T01
3. `P02 Runtime Contract Ownership` -> T02
4. `P03 Shell Projection Ownership` -> T03
5. `P04 Graph Host Ownership` -> T04
6. `P05 Tabular Ownership` -> T05
7. `P06 Shared Video Playback` -> T06
8. `P07 Residual Test Ownership` -> T07
9. `P08 Integration And Closeout` -> T08

Each task uses one implementation writer followed by one independent reviewer.
The final three reviews may run in parallel only after all writers stop.

## Test Plan

### No-lost-tests policy

- Every removed or renamed node ID has exactly one ledger disposition and a
  collecting replacement before deletion.
- Replacement tests preserve success, failure, cancellation, no-op, signal,
  persistence, cleanup, and rejection assertions.
- Parametrization keeps each original case independently identifiable.
- Native or QML crashes never count as passing.
- Tests move with production ownership; test-only movement is not progress.

### Performance policy

Performance is advisory, not an automatic rollback gate.

- Use three matched baseline and three matched candidate runs with the same
  fixture, cache state, Qt host/backend, display state, and sample count.
- A change above 5% triggers a second matched/interleaved batch and timed-path
  investigation.
- A reproduced change above 10% is recorded but does not automatically block or
  roll back the task.
- A reproduced change above 20% plus at least 100 ms added latency, one added
  interaction frame, or 20% CPU/RSS/throughput degradation pauses for user
  review.
- A newly failed user-visible absolute requirement also pauses for review.
- Background noise, invalid fixtures, backend mismatch, missing artifacts, or a
  changed timed path yields `INCONCLUSIVE`.
- Correctness, security, data integrity, one-decoder behavior, zero-I/O guards,
  and trust-boundary verification remain hard gates.
- No timing-only rollback occurs without user direction.

## Assumptions

- Work runs directly on `main`; each accepted task is committed separately and
  nothing is pushed.
- Protected dirty files remain untouched and unstaged.
- Public import break permission applies only to the listed obsolete internal
  paths; project and plugin formats remain readable.
- No third-party dependency is added.
- Current source and requirements override disconnected older history.
- Work stops after compaction until this plan, the QA ledger, `AGENTS.md`, and
  current Git state are reread.
