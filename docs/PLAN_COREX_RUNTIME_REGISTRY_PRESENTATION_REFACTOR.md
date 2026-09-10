# COREX Runtime, Registry, and Presentation Ownership Refactor

Status: `COMPLETED — T00–T26 ACCEPTED`

## Summary

This is a two-program refactor executed sequentially on local `main`:

```text
Program A — Registry and runtime ownership
T01–T12
    ↓ correctness/security/performance acceptance
T13 Program A closeout + Program B baseline
    ↓
Program B — Python presentation, native surfaces, QML, and tests
T14–T25
    ↓
T26 final closeout
```

The audit selected these current, verified concentrations:

1. `shrink:` split the 5,797-line execution client, 3,498-line protocol, and
   2,390-line headless runtime by existing owners without inventing a new
   framework.
2. `shrink:` reduce the 2,654-line `NodeRegistry` to storage, registration,
   fingerprints, and instance resolution; move validation, coercion,
   normalization, and Library queries to direct owners.
3. `delete:` remove the residual add-on coordinator, workspace controller
   facades, mixed 2,013-line `GraphCanvasPresenter`, dynamic fallback dispatch,
   and obsolete internal import barrels.
4. `shrink:` share only the proven native viewer/plot handoff state machine
   while keeping their binders and backend policies separate.
5. `shrink:` replace mirrored QML port delegates and renderer-to-renderer edge
   policy coupling without increasing per-node, per-port, or per-edge objects.
6. `move:` reown tests with production behavior and reduce shell-backed coverage
   only where collecting direct-owner or QML replacements prove equivalence.

No new dependency is permitted. Deletion is expected to exceed addition, but
there is no artificial line-count quota.

## Key Changes

### Orchestration, Git, and recovery

- The primary agent acts as orchestrator and integration owner. Implementation,
  focused verification, performance measurement, and reviews are delegated.
- Only one implementation writer may edit at a time because all agents share
  the checkout. Read-only correctness and performance reviewers may run in
  parallel after the writer stops.
- Each non-no-op task produces exactly one accepted local commit on `main`. No
  push occurs.
- The orchestrator alone stages and commits, using exact paths or hunks. Before
  each commit:
  - inspect the complete working and cached diff;
  - run `git diff --cached --check`;
  - scan staged names/content and the commit message for private study
    provenance;
  - confirm the three protected dirty paths' pre-existing content remains
    unstaged.
- The QA ledger is intentionally covered by the repository's
  `docs/specs/perf/*` ignore rule. After the same privacy review, the orchestrator
  must stage this exact neutral COREX file with
  `git add -f -- docs/specs/perf/COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR_QA_MATRIX.md`;
  ordinary staging is insufficient. No other ignored path is authorized.
- Every production commit includes its direct tests, architecture absence
  guards, file banners, owner maps, affected generated navigation, verification
  routing, and traceability updates. Later closeout tasks do not repair knowingly
  stale earlier commits.
- An accepted no-op produces no empty commit. Its evidence and reason are
  recorded in the ledger.
- T00 creates:
  - `docs/PLAN_COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR.md`;
  - `docs/specs/perf/COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR_QA_MATRIX.md`;
  - `tests/test_corex_ownership_refactor_ledger.py`.
- After any context compaction, stop before editing and reread, in order:
  1. `AGENTS.md`;
  2. the master plan;
  3. the QA/test/performance ledger;
  4. `git status --short --branch`;
  5. the last accepted commit;
  6. the next incomplete task row;
  7. active-agent state.

### Performance policy

Performance is advisory and noise-aware, never an automatic rollback trigger.

- Freeze the existing benchmark harness and report schema during both programs.
- Compare the same fixture checksum, cache/warmup state, Qt build, backend,
  display state, power state, sample count, and process topology.
- Start with three baseline and three candidate runs in counterbalanced order.
  Record individual values, median, p95, and CV or MAD.
- A movement above 5% triggers a second matched/interleaved batch and timed-path
  or counter inspection.
- A reproduced movement above 10% is recorded and explained but does not block
  or roll back automatically.
- Pause for user review only when a reproduced change exceeds 20% and has
  meaningful impact—at least 100 ms, one added interaction frame, or 20%
  CPU/RSS/throughput—or when a user-visible absolute requirement newly fails.
- Background contention, backend mismatch, an invalid fixture, a changed timed
  path, or a single outlier yields `INCONCLUSIVE`.
- Correctness, crash isolation, security, data integrity, trust-boundary
  validation, one-decoder ownership, and zero-unintended-I/O behavior remain hard
  requirements.
- No timing-only rollback occurs without user direction and causal evidence.

### Explicitly deferred

- Persistence/artifact-store decomposition.
- Engineering-scene pipeline decomposition.
- New protocol versions, schemas, transport abstractions, retry systems, or async
  frameworks.
- Deep `GraphNodeHost.qml` decomposition.
- `ContentFullscreenBridge` or `ContentFullscreenOverlay.qml` decomposition
  beyond replacing trim callbacks with the direct media service.
- QML unification of viewer and plot surfaces.
- `GraphCanvasRootApi` direct-dispatch retry or restoration of any aggregate
  graph-canvas facade.
- Edge geometry/cache redesign, renderer merge/default changes, or
  native-scenegraph implementation.
- Performance-harness restructuring.
- Verification-versus-traceability manifest restructuring.
- Global fixture rescoping, timeout weakening, pytest-qt migration, or
  replacement of `qmltestrunner`.
- Generic fake registries, dependency containers, controller hierarchies, or
  compatibility barrels.

## Public Interface Changes

### Stable external and QML contracts

The following remain unchanged:

- `.cxproj`, fragment, workflow, preferences, artifact, durable-solution, and
  schema-2 plugin formats.
- The 17-name top-level `corex` authoring API.
- The `corex-runtime` console command, arguments, output format, and exit codes.
- Worker command/event field names, defaults, validation behavior,
  catalog/plugin/add-on fingerprints, and transport bytes.
- `GraphCanvasStateBridge`, `GraphCanvasCommandBridge`, `GraphActionBridge`,
  `ViewerSessionBridge`, `ViewerControlBridge`, and `ContentFullscreenBridge` QML
  context identities and meta-object surfaces.
- All graph action IDs and payloads; `GraphCanvasActionRouter` remains the sole
  QML dispatch owner.
- `GraphCanvas.openSurfaceActionOverlayForHost(...)`.
- The five graph-surface overlay object names and live root aliases.
- `GraphNodePortsLayer` edit/context/dynamic-group properties,
  `dynamicPortGroupsApplied`, `embeddedInteractiveRects`, label-edit methods,
  and all existing input/output/dynamic-port/menu object-name families.
- Edge signals, query/redraw methods, renderer/diagnostic properties, object
  names, snapshot ordering, and Canvas-export appearance.
- `GraphNodeFloatingToolbar.openActionPopover()` and `openActionMenu()`, plus
  toolbar/context/options/popover object names.
- The complete `GraphNodeHost` signal and loaded-surface contract.
- Internal QML `id` values are not public and may change.

### Intentional internal breaks

No aliases or deprecated forwarding modules remain for these changes:

- Delete `addons.hot_apply`; add-on state preparation moves to
  `addons.state_changes`, while shell publication remains in
  `ui.shell.registry_replacement`.
- `nodes.plugin_loader` becomes public-plugin-only. Built-in and trusted add-on
  contributions move to direct owners.
- Remove `NodeRegistry.filter_nodes`, `category_paths`, and `categories`.
- Delete `execution.protocol`, `execution.client`, and
  `execution.headless_runtime`; callers import exact message, codec, transport,
  runtime, loader, or CLI owners.
- Delete `WorkspaceLibraryController`, `WorkspaceGraphEditController`,
  `GraphCanvasPresenter`, aggregate `canvas_source`, and viewer `_shell_window`
  service discovery.
- `RunController` remains the command/Auto/invalidation owner; projection and
  event intake move to direct controllers.
- Internal Python constructors and composition dependencies may break directly.

## Execution Tasks

### T00 — Establish the master plan, ledger, and baseline

- **Goal:** create the durable orchestration and no-lost-tests record before
  production edits.
- **Preconditions:** implementation begins from `main` at `db3cbc51`. If `main`
  has moved, perform a bounded re-audit of changed candidate paths and update the
  plan before editing.
- **Conservative write scope:** the master plan, QA ledger, ledger validator, and
  one exact plan-index hunk in `docs/specs/INDEX.md`.
- **Deliverables:**
  - Record starting refs and hashes for the three protected dirty paths.
  - Record affected Python node IDs, qualified QML selectors, shell targets,
    phases, isolation types, and current owners.
  - Ledger fields: program, owning task, ID kind, old ID, behavior guarded,
    production owner, phase/isolation, disposition, replacement IDs/selectors,
    assertion equivalence, collecting commit, execution result, accepted
    commit.
  - `pending_migration` is allowed for either program only while its owning task
    is `NOT STARTED` or `IN PROGRESS`. Program A rows must close at T13; Program
    B rows must close at T25.
  - Allowed dispositions: `retained`, `moved_to_owner`,
    `replaced_by_owner_test`, `replaced_by_qml_quick`,
    `retained_real_shell_lifecycle`, `redundant_existing_owner_proof`, and
    `deleted_obsolete_behavior`.
  - Capture current imports, public/meta-object snapshots,
    object/timer/provider counts, focused collection, `full --dry-run`, and
    Program A benchmark fixtures.
- **Verification:** ledger validator, focused `--collect-only -n 0`, shell
  catalog guards, traceability, links, maps, generator checks, and diff hygiene.
- **Performance:** establish commands and fixtures only; do not claim a result
  from stale retained reports.
- **Non-goals:** no production or test deletion.
- **Commit:** `Plan COREX runtime registry presentation refactor`.
- **Packetization notes:** `P00 Bootstrap`.

### T01 — Make registry replacement the sole add-on application authority

- **Goal:** delete the parallel add-on coordinator and retain one
  candidate-check-publish-persist-rollback transaction.
- **Preconditions:** T00 accepted.
- **Conservative write scope:** `addons/hot_apply.py`, new
  `addons/state_changes.py`, package exports,
  `ui/shell/registry_replacement.py`, direct add-on/registry tests, and owning
  maps.
- **Deliverables:**
  - Add pure `prepare_addon_enabled_state(...)`; it performs no store
    construction, persistence, registry build, cache invalidation, or consumer
    callback.
  - Keep `AddOnApplyResult` in the direct state-change owner.
  - `RegistryReplacementCoordinator` alone handles restart-required persistence,
    hot candidate/final builds, compatibility, admission blocking, reversible
    publication, persistence, notifications, and reverse rollback.
  - Delete the standalone coordinator, coordinator protocol, rebuild helper,
    test-only injection seam, obsolete package export, and
    `rebuild_after_addon_apply`.
  - Preserve pending-restart behavior without rebuilding runtime consumers.
- **Verification:** direct state-change tests, full registry-replacement
  success/refusal/order/rollback tests, add-on catalog tests, and one real Tabular
  disable/re-enable integration through the coordinator.
- **Performance:** preserve candidate/final build counts; compare interleaved
  hot-apply timings only after structural equality.
- **Non-goals:** no registry algorithm, package schema, or trust-check reduction.
- **Commit:** `Make registry replacement sole addon apply authority`.
- **Packetization notes:** `PA01`.

### T02 — Separate public plugin, built-in, and trusted add-on contributions

- **Goal:** make `plugin_loader.py` own public filesystem plugins only.
- **Preconditions:** T01 accepted.
- **Conservative write scope:** plugin loader/bootstrap, new node
  bundle/built-in owners, new add-on contribution owner, add-on adapter
  composition, direct tests/maps.
- **Deliverables:**
  - `nodes/function_bundle.py` owns prepared-bundle materialization and
    registry-aware fingerprint inputs, with no discovery or availability policy.
  - `nodes/builtin_catalog.py` owns the reserved built-in contribution table and
    built-in bundle.
  - `addons/registry_contributions.py` owns availability-gated, all-or-none
    trusted add-on contracts/descriptors/functions.
  - Move `register_internal_builtin_functions`, registry-aware fingerprinting,
    and trusted backend registration out of `plugin_loader.py`.
  - Update authoring and worker imports directly.
  - `addons.catalog.create_live_property_edit_adapters()` returns add-on adapters
    only; shell composition adds the core plot adapter explicitly.
- **Verification:** public plugin discovery/generation, add-on contribution,
  worker generation, package manager, built-in infrastructure, architecture,
  and hostile-input suites.
- **Performance:** identical bundle bytes/digests, type-ID order, function refs,
  plugin/full-registry fingerprints, traversal/member-read counts, and
  availability-call counts.
- **Non-goals:** no generic provider interface, execution of public source,
  cached trust shortcut, or package-format change.
- **Commit:** `Separate plugin and addon registry contributions`.
- **Packetization notes:** `PA02`.

### T03 — Extract node property coercion and specification validation

- **Goal:** remove structural validation from `NodeRegistry` without changing
  registration order or atomicity.
- **Preconditions:** T02 accepted.
- **Conservative write scope:** `nodes/registry.py`, new
  `nodes/property_coercion.py`, `nodes/instance_resolution.py`, and
  `nodes/spec_validation.py`, direct resolution callers, validation tests,
  architecture maps.
- **Deliverables:**
  - `coerce_property_value(...)` becomes the dependency-light primitive used by
    validation and later normalization.
  - `validate_node_spec(spec, *, data_types)` receives the exact catalog being
    validated.
  - Registration validates against the staged catalog after new
    families/types/conversions are installed.
  - Owner replacement revalidates all surviving and new entries before atomic
    commit.
  - Public plugin pre-materialization validation remains independent from
    registry-boundary validation.
  - `instance_resolution.py` directly owns port validation, instance-spec
    resolution, dynamic-group resolution, and resolved ports without importing
    registry or specification validation; all callers import it directly.
  - Dynamic and resolved instance specs use the same extracted validator.
  - Keep catalog storage, registration rollback, freeze, fingerprints, and
    registry-aware spec resolution in `NodeRegistry`; pure instance-resolution
    mechanics belong only to `instance_resolution.py`.
- **Verification:** exact accepted/rejected corpus, deterministic validation
  order, exception type/message parity, atomic registration/owner replacement,
  plugin runtime agreement, and architecture tests.
- **Performance:** matched full-registry construction and validator-call counts;
  no extra catalog traversal.
- **Non-goals:** no normalization move, data-type redesign, or validation memo
  redesign.
- **Commit:** `Extract node specification validation`.
- **Packetization notes:** `PA03`.

### T04 — Extract node property normalization policy

- **Goal:** remove built-in-specific normalization from the registry while
  retaining the registry's spec-aware API.
- **Preconditions:** T03 accepted.
- **Conservative write scope:** `nodes/registry.py`, new
  `nodes/property_normalization.py`, and direct normalization tests/maps.
- **Deliverables:**
  - Reuse `property_coercion.py`; do not duplicate coercion.
  - Move generic defaults/coercion orchestration, dynamic-property-backed port
    handling, Select, Number Slider, and Web Viewer normalization.
  - Retain `NodeRegistry.default_properties`, `normalize_property_value`, and
    `normalize_properties` as intentional spec/catalog-aware APIs.
  - Remove built-in-specific type branches from `registry.py`.
- **Verification:** exact output hashes and deep-copy isolation for scalar,
  interval/tree carriers, dynamic ports, Select, slider, and Web state.
- **Performance:** one base-spec lookup, one instance resolution, one property
  traversal, and no added deep copy or validation pass.
- **Non-goals:** no generic callback framework or workflow redesign.
- **Commit:** `Extract node property normalization policy`.
- **Packetization notes:** `PA04`.

### T05 — Move residual registry Library queries to the existing UI owner

- **Goal:** finish the T03 projection work by deleting the remaining
  registry-owned UI query methods.
- **Preconditions:** T03–T04 accepted.
- **Conservative write scope:** `nodes/registry.py`, existing
  `ui/shell/library_projection.py`, `ShellLibraryPresenter`,
  registry-filter/Library tests, maps.
- **Deliverables:**
  - Delete production-dead `NodeRegistry.filter_nodes`.
  - Derive categories from the same projected registry/custom-workflow items
    already cached by Library projection.
  - Delete `NodeRegistry.category_paths`, `categories`, and the presenter's
    separate registry-category cache.
  - Move filter/taxonomy tests to the Library owner; do not create a replacement
    registry filter API.
- **Verification:** identical ordering, accepted-type unions, hidden-port
  behavior, category ancestors/options/tree, query matching, Engineering taxonomy,
  and custom-workflow categories.
- **Performance:** one category tree per cached request; matched Library and
  Quick Insert query timings.
- **Non-goals:** no new projection module or registry search engine.
- **Commit:** `Move node library queries to presentation ownership`.
- **Packetization notes:** `PA05`.

### T07 — Split typed execution protocol ownership

- **Goal:** delete the protocol catch-all while preserving byte-identical
  transport behavior.
- **Preconditions:** T01–T05 committed; the current registry/add-on baseline
  passes.
- **Conservative write scope:** `execution/protocol.py`, runtime DTO parsing,
  direct production imports, split protocol tests, execution/viewer maps.
- **Deliverables:**
  - `transport_fields.py`: strict scalar/list decoding.
  - `registry_agreement.py`: catalog/plugin/add-on normalization, fingerprints,
    and mismatch diagnostics.
  - `run_messages.py`: run commands/events.
  - `viewer_messages.py`: viewer commands/events and invalidation epochs.
  - `protocol_codec.py`: unions and handwritten dict adapters.
  - Delete `protocol.py` and package compatibility reexports.
  - Keep prepared-execution imports local inside encode/decode methods to avoid
    a cycle with `run_messages.py`.
  - Settlement normalization imports directly from its runtime-contract owner.
- **Verification:** protocol, viewer protocol, prepared execution, worker
  protocol/worker, plugin agreement/loading, artifact/solution records,
  architecture, and deleted-path tests.
- **Performance:** same dictionaries, field order, validation failures, one
  serialization construction, allocation/copy counts, and matched round trips.
- **Non-goals:** no reflection codec, field/schema change, or trust-check
  consolidation.
- **Commit:** `Split execution protocol ownership`.
- **Packetization notes:** `PA07`.

### T08 — Split concrete execution transports and backend routing

- **Goal:** delete the 5,797-line client module by moving existing owners, not
  redesigning them.
- **Preconditions:** T07 accepted.
- **Conservative write scope:** `execution/client.py`, new direct client modules,
  app/runtime imports, split client tests, maps/routing.
- **Deliverables:**
  - `client_common.py`: existing proven shared behavior only.
  - `process_client.py`, `external_python_client.py`, `trusted_client.py`:
    unchanged transport lifecycles.
  - `backend_client.py`: backend selection, generation/viewer routing,
    invalidation commit.
  - `client_generation.py`: generation snapshots/reservations/leases.
  - Delete `client.py` and compatibility reexports.
  - Preserve `RegistryReplacementCoordinator` and `CorexRuntime` publication
    guard/replace calls exactly.
- **Verification:** five client-owner suites, worker, viewer protocol/service,
  plugin agreement/loading, external-Python routing, timeout/death/recovery,
  registry replacement, and architecture.
- **Performance:** cold start, warm reuse, dispatch, viewer command, retirement;
  unchanged process/thread/queue/listener counts and lock order.
- **Non-goals:** no new client interface, adapter, queue, retry, lock, or async
  framework.
- **Commit:** `Split execution client transports`.
- **Packetization notes:** `PA08`.

### T09 — Separate durable solution contracts from session state

- **Goal:** let persistence depend on explicit execution ports rather than
  `SolutionStore`.
- **Preconditions:** T07–T08 accepted.
- **Conservative write scope:** `solution_store.py`, new `solution_backend.py`
  and `project_solution.py`, repository imports, solution tests/maps.
- **Deliverables:**
  - Move durable backend/factory ports and result DTOs to
    `solution_backend.py`.
  - Move save snapshot/result/candidate/adoption/GC value contracts and token
    calculation to `project_solution.py`.
  - Keep all facts, records, preparations, settlement acceptance, locks, leases,
    eviction, and binding installation in the single `SolutionStore`.
  - Persistence imports only the two explicit boundary modules.
- **Verification:** solution store/session, repository, records, Save/Save As,
  durable/project-solution runtime subsets, architecture, and import-cycle tests.
- **Performance:** unchanged hash/JSON/file passes, lock counts/order,
  registration/consume, invalidation, settlement, selection, and eviction.
- **Non-goals:** no `ProjectSolutionCoordinator`, store sharding, schema, GC, or
  eviction redesign.
- **Commit:** `Split solution contracts from session state`.
- **Packetization notes:** `PA09`.

### T10 — Split `CorexRuntime`, project loading, requests, and CLI ownership

- **Goal:** delete `headless_runtime.py` while retaining one runtime lifecycle
  owner.
- **Preconditions:** T07–T09 accepted.
- **Conservative write scope:** headless runtime, new
  request/loader/runtime/CLI modules, bootstrap and shell composition imports,
  runtime tests, traceability/maps.
- **Deliverables:**
  - `runtime_requests.py`: request/result/load/cancellation records.
  - `project_loader.py`: the composition-level persistence-loading dependency.
  - `runtime.py`: `CorexRuntime`, registry publication, prepare/dispatch, event
    enrichment, solution lifecycle, and viewer forwarding.
  - `runtime_cli.py`: parser, text/JSON output, and `main`.
  - Delete `headless_runtime.py` and update imports directly.
  - Point `bootstrap.headless_main` to the new CLI owner.
  - Preserve project-solution capture/stage/reopen/adopt/bind/reset/GC inside
    `CorexRuntime` and preserve lifecycle → client-publication → store lock
    order.
- **Verification:** runtime request/core/loader/CLI suites, run script,
  bootstrap, registry replacement, plugin agreement, project save/session,
  packaging configuration, architecture, and deleted-path tests.
- **Performance:** import/startup, project load, prepare, dispatch, and
  synchronous run with identical plan/key/output hashes.
- **Non-goals:** no runtime state-bag, callback bundle, lifecycle split, or
  execution semantic change.
- **Commit:** `Split Corex runtime API and CLI ownership`.
- **Packetization notes:** `PA10`.

### T11 — Extract shell run-state projection

- **Goal:** make `RunController` command-oriented and give UI execution state one
  owner.
- **Preconditions:** T10 accepted.
- **Conservative write scope:** run controller/state/composition, new projection
  controller, direct tests/maps.
- **Deliverables:**
  - `RunProjectionController` solely owns node execution sets, elapsed/warning
    state, accepted-output cache, solution facts, port availability, failure
    focus, and related signals.
  - Publish cached outputs only from a runtime-enriched settlement carrying the
    retained record accepted by `SolutionStore`.
  - `RunController` retains Manual/Selected/Trigger/Auto commands, preview,
    dirty-script Apply, dispatch policy, pause/resume/stop, and history
    invalidation.
  - Retain one `ShellRunState`; add no forwarding facade.
- **Verification:** projection, remaining run-controller, port
  flow/availability, output cache, elapsed/warning/solution facts, project
  reset/open, and bootstrap tests.
- **Performance:** matched 10k state updates, exact signal counts, cache writes,
  dict copies, and zero additional QObject/timer.
- **Non-goals:** no QML property, cache, run-semantic, or state-schema change.
- **Commit:** `Extract shell run state projection`.
- **Packetization notes:** `PA11`.

### T12 — Make one controller the shell execution-event intake

- **Goal:** remove event forwarding and leave one queued route from runtime to
  shell state.
- **Preconditions:** T11 accepted.
- **Conservative write scope:** new event controller, run
  controller/composition, ShellWindow forwarding mixins, shell/viewer tests,
  maps/routing.
- **Deliverables:**
  - `RunEventController.handle_execution_event` owns typed event routing,
    active-run rejection, logs, Trigger settlement, viewer invalidation
    adoption, fatal reset, and terminal transitions.
  - Composition creates exactly one `Qt.QueuedConnection` from
    `host.execution_event` to the controller.
  - Retain the controller in `ShellControllerDependencies`; it catches/logs its
    own exceptions.
  - Remove ShellWindow event wrappers, second subscriptions, timers, and
    `Qt.callLater` hops.
  - Preserve event order: generation callback → runtime store
    acceptance/enrichment → runtime event stream → Qt queued signal → event
    controller.
  - Only successful completion drains Auto; failure/stop/protocol/infrastructure
    outcomes clear it.
- **Verification:** event controller, run controller/projection, shell run,
  viewer session/host/service, bootstrap/composition, shell-isolation routing,
  and stale/foreign event cases.
- **Performance:** exactly one decode, signal subscription, event-loop hop,
  cache publication, and matched event-to-projection latency.
- **Non-goals:** no viewer, QML, Auto, or execution semantic redesign.
- **Commit:** `Split shell execution event ownership`.
- **Packetization notes:** `PA12`.

### T13 — Close Program A and lock Program B's baseline

- **Goal:** accept Program A independently, then baseline Program B against its
  resulting `HEAD`.
- **Preconditions:** T01–T12 individually accepted with no stale routing or
  ledger rows.
- **Conservative write scope:** plan/ledger status, retained QA evidence, exact
  spec-index status hunk, and corrections required by final reviews.
- **Deliverables:**
  - Program A ledger rows accepted; Program B rows remain pending.
  - Independent architecture/ownership, correctness/security/no-lost-tests, and
    performance-causality reviews return no pending findings.
  - Explicit absence scan for every deleted Program A module/import.
  - Run the Program A closeout boundary once.
  - Record Program B's final run-owner names and prove pre-A event/projection
    symbols are absent.
  - Capture post-A Python/QML bridge surfaces, action routes, object names,
    QObject/timer/provider counts, native identities, and Program B benchmark
    fixtures.
- **Verification:** exact closeout commands in the Test Plan.
- **Performance:** report supportive, regressed, or inconclusive evidence without
  timing-only rollback.
- **Non-goals:** no Program B production change.
- **Commit:** `Close COREX runtime and registry ownership stage`.
- **Packetization notes:** `PA13 Gate`.

### T14 — Make workspace graph actions direct-owned

- **Goal:** delete the remaining workspace/action forwarding maze.
- **Preconditions:** T13 accepted.
- **Conservative write scope:** workspace controllers, graph-action
  controller/composition, direct tests/maps.
- **Deliverables:**
  - Promote `WorkspaceSelectionContext`.
  - Promote/rename `WorkspaceEditOps` to `WorkspaceEditController`; it absorbs
    selection/workspace lookup, clipboard signature/count, node-change
    aftermath, and non-forwarding edit behavior.
  - Promote `WorkspaceDropConnectOps` to `WorkspaceDropConnectController` with
    explicit active-workspace, workflow-resolver, and connection-picker
    callbacks.
  - Construct one `MutationUiEffects` instance and inject it into both.
  - Use existing direct navigation, workflow, and package-IO controllers.
  - Make `GraphActionController` use explicit typed calls, including Program A's
    run owner.
  - Delete `WorkspaceLibraryController`, `WorkspaceGraphEditController`, host
    attributes, protocols, generic `getattr` dispatch, and fallback owners.
- **Verification:** direct workspace owner suites, graph-action contracts,
  transforms/layout, clipboard/history, drop/connect, package/workflow IO, and
  shell composition.
- **Performance:** exact mutation/history payloads, dispatch depth, and matched
  action/drop/layout timings.
- **Non-goals:** no graph-host presenter, run semantic, or QML action-ID change.
- **Commit:** `Make workspace graph actions direct owned`.
- **Packetization notes:** `PB01`.

### T15 — Give Media Panel actions one direct service

- **Goal:** move crop/frame/timestamp/trim behavior out of the mixed canvas
  presenter.
- **Preconditions:** T14 accepted.
- **Conservative write scope:** graph canvas presenter media sections, new
  `MediaPanelActionService`, command bridge media ops, fullscreen trim callback
  wiring, media tests/maps.
- **Deliverables:**
  - One QObject service owns crop, frame creation, timestamp annotation, trim
    replace/copy, worker/thread lifecycle, artifact staging, and result
    normalization.
  - Inject scene mutation, direct workspace edit/drop owners,
    model/workspace/project providers, project-session staging, run-state/project
    path providers, and notification/error callbacks.
  - `ContentFullscreenBridge` changes only its trim callbacks.
  - Preserve `media_panel_source.py`, `media_video_state.py`, playback core, and
    one-decoder behavior.
- **Verification:** new service suite, video trim, media QML surface, passive
  image/media creation preferences, staging, mounted MP4 lifecycle,
  cancellation, and cleanup.
- **Performance:** same QThread/worker/decoder counts, artifact bytes/refs, and
  matched submission/completion overhead.
- **Non-goals:** no media schema, QML, playback, or fullscreen lifecycle
  redesign.
- **Commit:** `Own Media Panel actions directly`.
- **Packetization notes:** `PB02`.

### T16 — Extract canvas export and delete `GraphCanvasPresenter`

- **Goal:** remove the remaining mixed canvas aggregate without changing QML
  APIs.
- **Preconditions:** T14–T15 accepted.
- **Conservative write scope:** graph canvas presenter, new
  `CanvasExportPresenter`, bridge constructor/composition wiring,
  export/media/direct-owner tests/maps.
- **Deliverables:**
  - Plain-Python `CanvasExportPresenter` owns capture framing, native-overlay
    composition, PNG/PPTX export, restoration, dialogs, and errors.
  - Split state/command bridge inputs by domain: canvas session state,
    preferences, Program A run owner, scope/hints, Inspector, Library/Quick
    Insert, workspace edit/drop, media actions, and canvas host.
  - `trigger_node` routes to Program A's command owner.
  - Delete `GraphCanvasPresenter`, `canvas_source`, shell-window fallback
    parameters/accessors, and replacement aggregates.
  - Keep bridge identities, parents, context names, properties, slots, signals,
    and graph-surface snapshot unchanged.
- **Verification:** canvas export, project review, split bridges, command modules,
  surface snapshot/meta-object, media, and focused shell context identity.
- **Performance:** deterministic capture hashes/geometry, shell
  QObject/timer/provider counts, and separate action versus export timings.
- **Non-goals:** no `GraphCanvasHostPresenter`, QML root, graph mutation, or run
  redesign.
- **Commit:** `Retire the mixed graph canvas presenter`.
- **Packetization notes:** `PB03`.

### T17 — Inject viewer and plot dependencies explicitly

- **Goal:** remove residual ShellWindow service location while preserving host
  identities.
- **Preconditions:** T16 accepted.
- **Conservative write scope:** runtime service composition and the four
  viewer/session/control/plot classes, direct tests/maps.
- **Deliverables:**
  - `ViewerSessionBridge`: execution-event signal/client and active/workspace
    providers.
  - `ViewerControlBridge`: active/scene/workspace/model/registry providers,
    preferences, save callback, and direct viewer-host reference.
  - `ViewerHostService`: QML-engine, save, and camera-bookmark-cycle providers.
  - `PlotHostService`: active-workspace provider.
  - Preserve dynamic model/registry providers and fail-closed scene/manager
    workspace mismatch.
  - Use only the two genuine bounded late callbacks for session-camera-to-host
    and host-page-navigation-to-control cycles.
  - Remove `_shell_window` and service discovery from the four classes;
    `parent=host` remains allowed for lifecycle ownership.
- **Verification:** viewer session/control/host, plot host, fullscreen lifecycle,
  registry replacement, architecture, bootstrap, and shell runtime contracts.
- **Performance:** stable QObject/timer/provider/signal counts and zero eager
  binder/pool creation.
- **Non-goals:** no presentation-state extraction or rendering change yet.
- **Commit:** `Inject viewer runtime owners explicitly`.
- **Packetization notes:** `PB04`.

### T18 — Share the native viewer/plot presentation handoff

- **Goal:** remove exact duplicate transition mechanics without merging the two
  host services.
- **Preconditions:** T17 accepted.
- **Conservative write scope:** new `NativePresentationHandoff`, viewer/plot
  hosts, direct lifecycle tests/maps.
- **Deliverables:**
  - One handoff instance per host; never a singleton.
  - Own pending preview-source records, serial validation, render-gate
    connection, timeout, cancel/flush/shutdown, and queued completion.
  - Host-specific preview capture and completion remain callbacks.
  - Preserve expected-source matching, one `afterRendering` connection, no host
    mutation inside render callbacks, stale-serial rejection, and idle
    disconnect.
  - Keep detached windows, binders, viewer controls, plot requests/backends, and
    main reconciliation loops distinct.
  - After acceptance, perform the required Python/native-to-QML convergence gate
    and capture a new QML/object/performance baseline for T19–T24.
- **Verification:** new handoff suite, viewer/plot hosts, overlay manager,
  detached/fullscreen tests, viewer surface, widget identity, and
  engineering-viewer performance checks.
- **Performance:** widget/binder creation, overlay count, preview revision,
  render connections, demotion completions, pan/drag/reparent timing.
- **Non-goals:** no generic native-surface framework, pool, parking container,
  or QML viewer/plot unification.
- **Commit:** `Share native presentation handoff`.
- **Packetization notes:** `PB05 Gate`.

### T19 — Separate renderer-neutral graph-edge paint policy

- **Goal:** stop retained rendering from depending on Canvas implementation
  methods.
- **Preconditions:** T18's post-Python/QML baseline recorded.
- **Conservative write scope:** edge Canvas/retained layers, new pure JS policy,
  existing edge math, focused tests/maps.
- **Deliverables:**
  - `EdgePaintPolicy.js` owns pure stroke/dash/marker/display/drag-preview paint
    state.
  - Move `edgeAnchor()` to `EdgeMath.js`.
  - Canvas and retained renderers call direct pure owners; no
    renderer-to-renderer reference remains.
  - Preserve `EdgeScenegraphLayer.qml` as the unsupported placeholder with its
    current fallback reason, object name, counters, selection, and Canvas
    fallback.
  - Add zero Items, QObjects, timers, Loaders, per-frame arrays, snapshot passes,
    or per-edge allocations.
- **Verification:** spatial index, flow labels, active-wire,
  display/preference rendering, hit tests, Track-H counters, and Canvas-export
  appearance.
- **Performance:** snapshot order/hash, geometry/cache and retained update/skip
  counters, paint counts, create-edge, load/pan/drag.
- **Non-goals:** no renderer merge/default, geometry/cache redesign, or native
  scenegraph implementation.
- **Commit:** `Separate graph edge paint policy`.
- **Packetization notes:** `PB06`.

### T20 — Extract graph-surface editor overlays

- **Goal:** remove five parallel overlay state/placement/cancel flows from root
  layers.
- **Preconditions:** T19 accepted and T16 export owner stable.
- **Conservative write scope:** `GraphCanvasRootLayers.qml`, new
  `GraphCanvasSurfaceEditorOverlays.qml`, direct QML/integration tests/maps.
- **Deliverables:**
  - The new component owns Web Address, Timestamp, Number Slider, Select, and
    Panel overlay state, positioning, Connections, outside-click cancellation,
    commit, and cancel.
  - Its root replaces `webPageAddressOverlayLayer` and contains the other four
    moved Items.
  - Root layers retain live aliases and one delegation method; no duplicated
    state.
  - Net always-live Item/timer count must not increase.
- **Verification:** direct QuickTests for open/switch/cancel/commit, Web bridge,
  P03 input contract, slider/select/panel, passive-host overlays, and
  Canvas-export exclusion.
- **Performance:** object/timer counts, first-open identity/focus, and no
  additional loader/event pass.
- **Non-goals:** no generic overlay registry or unrelated root-layer
  decomposition.
- **Commit:** `Extract graph surface editor overlays`.
- **Packetization notes:** `PB07`.

### T21 — Replace mirrored input/output port delegates

- **Goal:** give one row component both port directions without adding per-port
  objects.
- **Preconditions:** T20 accepted.
- **Conservative write scope:** `GraphNodePortsLayer.qml`, new
  `GraphNodePortRow.qml`, port tests/maps.
- **Deliverables:**
  - The component root directly replaces each existing input/output delegate
    `Item`.
  - The component derives side, notch mirroring, label alignment,
    default-property capability, and resize-hover behavior from direction.
  - Row owns shared geometry, grip/notch/ring/dot, gestures/context routing,
    dynamic remove, label/edit, general tooltip/accessibility, flow state,
    padlock painting, and interactive-rectangle behavior.
  - Input instances retain only the inactive slash, always-live padlock Canvas,
    and `GraphInlinePropertiesLayer` default child. Output instances retain only
    the separate inactive tooltip and existing padlock Loader/Component/Canvas.
  - Root retains models, dynamic-group scheduling, notch cache, aggregate
    interactive rectangles, context state, and add-button repeater.
  - No extra per-port Connection, Binding, Loader, timer, wrapper, edge scan, or
    catalog scan.
- **Verification:** node-host/control QuickTests, data-tree UI, default values,
  port-flow/data-type projection, label editing, drag/click/hover, compatibility
  rings, dynamic remove, and accessibility.
- **Performance:** identical geometry/object names, delegate/QQuickItem count,
  notch-cache behavior, port-heavy load/drag.
- **Non-goals:** no port payload, mutation, or dynamic-group scheduling redesign.
- **Commit:** `Share graph node port row`.
- **Packetization notes:** `PB08`.

### T22 — Extract the graph-port context menu

- **Goal:** remove menu policy/markup from the ports root without a menu
  framework.
- **Preconditions:** T21 accepted.
- **Conservative write scope:** ports layer, new
  `GraphNodePortContextMenu.qml`, direct menu/mutation/history tests/maps.
- **Deliverables:**
  - Root `Menu` replaces the current `portContextMenu` directly.
  - Preserve every object name, modifier order/check state, Principal
    exclusivity, dynamic insert/rename/remove, and read-only guards.
  - Menu calls existing ports-layer mutation methods through an explicit owner.
  - After acceptance, run the second QML convergence checkpoint before
    action/popover work.
- **Verification:** port menu QuickTests plus scene mutation/history/persistence
  and dynamic/read-only cases.
- **Performance:** unchanged menu/object counts and port delegate counts.
- **Non-goals:** no generic action/menu system.
- **Commit:** `Own graph port context menu`.
- **Packetization notes:** `PB09 Gate`.

### T23 — Centralize graph-action presentation

- **Goal:** remove repeated QML action normalization and descriptor shaping
  while keeping dispatch direct.
- **Preconditions:** T14–T22 accepted and the second QML checkpoint passes.
- **Conservative write scope:** new pure `GraphActionPresentation.js`, router
  consumers, context/options/edge/node toolbar tests/maps.
- **Deliverables:**
  - Shape already-authoritative action DTOs: lookup, edge path/display
    normalization, checked/enabled/label/icon fields, menu/popover models, and
    ordering.
  - `GraphCanvasActionRouter` remains the sole dispatch owner.
  - Do not decide graph mutation, media action availability, fullscreen
    lifecycle, viewer/plot readiness, or native state.
  - Recompute models only when authoritative actions or popover state change,
    never during positioning frames.
  - Add zero QML objects, timers, loaders, or per-frame arrays.
- **Verification:** action inventory/payload equality, graph-action contracts,
  active-wire/flow-edge actions, context/options, passive/media/viewer/plot
  actions, split bridges, snapshots, and checked states.
- **Performance:** action-model rebuild count and toolbar/context first-open
  diagnostics.
- **Non-goals:** no action-policy move from Python owners and no router redesign.
- **Commit:** `Centralize graph action presentation`.
- **Packetization notes:** `PB10`.

### T24 — Extract graph-node toolbar popovers

- **Goal:** separate large popover markup from toolbar chrome without wrapping
  it.
- **Preconditions:** T23 accepted.
- **Conservative write scope:** node floating toolbar, new
  `GraphNodeToolbarPopoverHost.qml`, focused QuickTests/maps.
- **Deliverables:**
  - New root replaces `graphNodeFloatingToolbarActionPopoverBridge`.
  - Move source-storage, bookmark, font-size, PDF-page, font-family, and existing
    action popovers without duplicate panels.
  - Toolbar retains anchor geometry, chrome, hover grace, primary actions, run
    menu, and public open methods.
  - Preserve object names, focus/keyboard behavior, positioning,
    dirty-draft flush, and nested callbacks.
- **Verification:** toolbar/popover QuickTests, media/PDF/font/source action
  suites, context/options, and graph-action snapshots.
- **Performance:** unchanged always-live object/timer count and diagnostic
  first-open latency.
- **Non-goals:** no toolbar visual redesign or new popover framework.
- **Commit:** `Extract graph node toolbar popovers`.
- **Packetization notes:** `PB11`.

### T25 — Reown residual shell tests and align actual verification routes

- **Goal:** finish test ownership against the final Program A/B architecture
  while retaining genuine lifecycle/native isolation.
- **Preconditions:** T14–T24 production tests have already moved and collect in
  their owning commits.
- **Conservative write scope:** remaining shell tests, direct-owner suites, QML
  QuickTests, shell catalog/guards, and only the verification routing actually
  changed.
- **Deliverables:**
  - Reinventory every remaining shell test against final owners; the inventory
    is broad, but deletion is allowed only with exact collecting proof.
  - Move pure QML positives to qualified QuickTest selectors and Python behavior
    to direct controllers/services/presenters.
  - Retain real shell coverage for composition,
    context/provider/action identity, native parenting, repeated mount/close,
    project reset, timer cancellation, fullscreen/media handoff, viewer
    reparent/restore, and deterministic teardown.
  - Preserve one crash-isolated child and hard timeout per retained lifecycle
    target, bounded outer workers, and serial execution inside each child.
  - Shrink the catalog only as justified by the ledger; there is no required
    target count.
  - Replace the literal “51 targets” assertion with unique/disjoint
    registration, one owner/ledger row per target, serial command construction,
    no unregistered shell lifecycle tests, and no accidental fast/GUI
    collection.
  - Update `verification_manifest.py` only for actual path/catalog changes;
    retain Qt Quick before Python GUI and canonical phase semantics.
  - Harden the shared `hover_host_local_point` helper so it always forces an
    outside-to-target pointer transition, then prove both sibling test orders in
    the existing persistent probe process. Do not solve this by isolating every
    test/process.
  - If no residual test or route change is justified, record an accepted no-op
    rather than manufacture one.
- **Verification:** ledger validator, before/after collection, authoritative QML
  runner, shell catalog guards, `tests/test_shell_isolation_phase.py -n 0`,
  `full --dry-run`, and affected direct-owner suites.
- **Performance:** compare old and replacement test cohorts; product timing
  remains advisory and unchanged by test-only work.
- **Non-goals:** no runner replacement, fixture rescope, timeout reduction,
  in-process collapse of crash boundaries, per-test process isolation, generic
  fake hierarchy, or wholesale source-assertion deletion.
- **Commit:** `Reown remaining shell tests` when non-no-op.
- **Packetization notes:** `PB12`.

### T26 — Integrate, review, and close the full refactor

- **Goal:** finish with a navigable, bisectable, correctness-green local commit
  series and honest performance evidence.
- **Preconditions:** T01–T25 accepted or explicitly recorded no-op.
- **Conservative write scope:** plan/ledger status, retained QA evidence, exact
  spec-index status hunk, and corrections from final independent reviews.
- **Deliverables:**
  - Every ledger row has an accepted program-scoped disposition.
  - No deleted module, facade, aggregate source, fallback owner,
    `_shell_window` lookup, renderer-to-renderer reference, or compatibility
    alias remains.
  - All maps, banners, coverage rows, traceability, focused commands, and
    generated indexes point at current owners.
  - Independent architecture/ownership, correctness/security/no-lost-tests, and
    performance-causality reviewers return no pending findings.
  - Report every local task commit, `main`'s ahead count, protected dirty paths,
    full verification result, and performance verdicts. Do not push.
- **Verification:** the exact final boundary below.
- **Performance:** report narrow regressions and inconclusive evidence without
  rewriting thresholds or rolling back automatically.
- **Non-goals:** no release build, installer, push, or unrelated cleanup.
- **Commit:** `Close COREX runtime registry presentation refactor`.
- **Packetization notes:** `PB13 Closeout`.

## Work Packet Conversion Map

These are delegation labels only; do not create packet manifests.

- `P00` → T00.
- `PA01`–`PA12` → T01–T12, one implementation writer and one independent
  reviewer each.
- `PA13` → T13 Program A acceptance and Program B baseline.
- `PB01`–`PB11` → T14–T24.
- `PB12` → T25 residual test ownership.
- `PB13` → T26 final reviews and closeout.

No packet may start before its predecessor is accepted. A writer may not
overlap another writer. Review findings return to the owning writer before the
orchestrator stages the task.

## Test Plan

### No-lost-tests policy

- Every removed Python node ID, qualified QML selector, and shell target appears
  exactly once in the ledger.
- Replacement IDs must collect before deletion; QML selectors must execute under
  `qmltestrunner`, not a Python wrapper.
- Parametrized replacements use stable unique IDs.
- Many-to-one replacements record assertion equivalence separately for every old
  case.
- Success, failure, cancellation, stale-event rejection, no-op, signals,
  persistence, cleanup, and security rejection remain independently proven.
- Native/QML crashes never count as skips or passes.
- Program A closeout accepts only Program A rows; Program B rows may remain
  explicitly pending until T25.

### Per-task verification

- Run the smallest owner suite first.
- Run route/map/traceability/verification-manifest checks in the same task
  whenever paths or ownership change.
- Run `full --dry-run` for tasks that rename/delete test modules or verification
  targets.
- Regenerate and check source/test, route, and QML indexes in the same commit
  when their inputs change.
- Do not run the broad full suite after every task.

### Authoritative QML command

After the final QML-changing task and after T25 if it adds/moves QuickTests:

```powershell
$runner = Join-Path $env:QT_ROOT "bin\qmltestrunner.exe"
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& $runner -input tests/qml_quick -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
```

### Program closeout boundary

Run once at T13 and once at T26, using the project venv:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_corex_ownership_refactor_ledger.py --ignore=venv -q -n 0
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py --check
.\venv\Scripts\python.exe .\scripts\generate_source_test_file_index.py --check
.\venv\Scripts\python.exe .\scripts\generate_qml_navigation_index.py --check
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --summarize-output
git diff --check
git diff --cached --check
```

Only generator checks whose inputs changed are mandatory, though both programs
are expected to change maps and test ownership. The summarized full run supplies
the broad fast, GUI, Qt Quick, slow, and isolated-shell acceptance; do not
redundantly rerun each broad lane separately.

## Assumptions

- Both programs are authorized sequentially. Program B starts automatically
  only after Program A's correctness/security closeout passes.
- Implementation is directly on local `main`, one accepted commit per non-no-op
  task, with no push.
- Starting truth is `db3cbc51`. If the checkout drifts, re-audit affected owners
  and update the plan/ledger before editing.
- The pre-existing changes in `docs/specs/INDEX.md`,
  `docs/PLAN_COREX_Physical_Simulation_Backend.md`, and
  `scripts/Strain_Gage_Positioning/modular_version/strain_candidate_points.csv`
  remain user-owned and unstaged. Only exact new plan/status hunks may be staged
  from the modified index.
- Obsolete internal imports may break directly; public formats, SDK, CLI, QML
  context/meta-object surfaces, action IDs, and wire semantics remain stable.
- No third-party dependency is added.
- If an exact residual edge is absent when its task starts, record an accepted
  no-op and do not manufacture an abstraction.
- Current source/tests and focused commit history override stale architecture
  descriptions.
- Performance follows the advisory 5%/10%/20%-plus-material-impact policy, with
  no timing-only rollback.
