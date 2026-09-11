# Preserve Types Through Forwarding Nodes

## Summary

Implement the approved type-forwarding plan in the current checkout. Signal Plot
through Panel or Trigger must offer the same recommendations as its Image output,
while connecting the chosen node to the port actually dragged. Inherited output
types also drive port descriptions and graph connection checks. An upstream edit
and any newly incompatible downstream wire removals form one undoable edit.

## Key Changes

- Explicitly declare Panel output from input, Trigger output from input, and every
  Stream Gate output from stream. Gate selection never determines output type.
- Resolve forwarding chains and existing subnode mappings in one graph-owned,
  memoized resolver using declarations and topology, without execution or caches
  of runtime values. Mixed source types require every member to be accepted.
- Keep input acceptance, inferred output type sets, and runtime carrier validation
  separate. Recompute on topology, enable/disable, semantic property/dynamic-port,
  registry, and history changes.
- Extend existing downstream pruning and retain existing invalid-type visuals;
  do not introduce a separate persisted invalid-wire model.

## Public Interface Changes

- Add `PortSpec.type_from_input`, default empty, and the equivalent public output
  decorator argument. Initially allow Any data outputs referencing Any data inputs
  with matching access structure; reject invalid references and relationships.
- Preserve inferred source sets separately from target accepted alternatives.
- Include forwarding metadata and inferred contracts in relevant identities.
- Keep inferred contracts transient; no project-file schema migration.

## Execution Tasks

### T01 - Declare and resolve forwarding

- Goal: define and implement the reusable declaration and graph inference seam.
- Preconditions: verified current checkout and preserved baseline dirty work.
- Conservative write scope: node specs, instance/declaration parsers, registry
  fingerprints, Panel/Trigger/Stream Gate declarations, graph type resolver and
  compatibility helpers, associated focused tests and generated node catalog.
- Deliverables: validated static/dynamic forwarding and immutable resolved source
  sets, including chains, fan-in, disabled inputs, cycles and subnode mappings.
- Verification: declaration, registry, core node, type resolver and catalog tests.
- Non-goals: UI adoption, runtime carrier changes, broader value inference.
- Packetization notes: none; one implementation owner and independent review.

### T02 - Integrate graph and runtime checks

- Goal: make graph edits, persistence normalization, compilation and identities
  consistently use the shared inferred contracts.
- Preconditions: accepted T01 interfaces and focused tests.
- Conservative write scope: graph invariant/mutation/normalization/fragment paths,
  compiler, execution plan/identity, associated graph/runtime/persistence tests.
- Deliverables: downstream pruning in the initiating history action; transient
  inferred execution facts and correct cache/reuse invalidation.
- Verification: edits, Shift fan-in, enable/disable, Undo/Redo, save/reopen,
  compilation, conversion, Trigger retention and solution identity regressions.
- Non-goals: replacing declared runtime Any contracts or changing Trigger timing.
- Packetization notes: none; one implementation owner and independent review.

### T03 - Integrate recommendations and presentation

- Goal: use the same contracts for recommendations, descriptions and drag feedback.
- Preconditions: accepted T02 behavior.
- Conservative write scope: Quick Insert/presenter/drop-connect, graph scene
  projections, drag compatibility and targeted cache refresh, associated tests.
- Deliverables: identical direct/forwarded suggestions and ranking; original drag
  anchor retained; choices revalidated against current topology; downstream refresh.
- Verification: focused projection/drop-connect, mixed type tiers, stale choices,
  payload updates and real QML render/interaction regression.
- Non-goals: UI redesign, unrelated node behavior or relaxed runtime validation.
- Packetization notes: none; one implementation owner and independent review.

### T04 - Acceptance and documentation

- Goal: prove the complete workflow and publish accurate repository guidance.
- Preconditions: T01-T03 accepted and integration risks reviewed.
- Conservative write scope: focused integration tests, affected authoring/spec/map
  documentation, generated route/catalog artifacts, and fixes justified by checks.
- Deliverables: final verification and review evidence recorded once in this plan.
- Verification: focused suites, targeted QML rendering, fast summarized integration
  lane, traceability, Markdown links, agent maps and relevant hygiene checks.
- Non-goals during implementation: publication, packet generation or unrelated cleanup.
- Packetization notes: none.

## Work Packet Conversion Map

None. Execute these task slices directly with one active implementation writer.

## Test Plan

- Direct Signal Plot, Signal Plot -> Trigger, and Signal Plot -> Panel -> Trigger
  must return identical rows/order/labels, including Export Image and Media Panel.
- A chosen result connects to the dragged output, preserving Trigger behavior.
- Integer plus Decimal admits inputs supporting both; Image plus Number excludes
  single-type inputs. Broad/runtime matches remain search-only.
- Disconnected forwarding and unresolved generic producers preserve prior behavior.
- Edits, Shift fan-in, enable/disable, dynamic ports and history refresh the chain;
  pruned wires and the source change restore together in one Undo.
- Runtime uses declared Any for carrier validation/conversion. A retained old
  Trigger value must not pass an image consumer merely because current topology
  infers Image. Type changes invalidate consumer identity even if Trigger has not
  published a new generation.
- Cover cycles, long chains, subnodes and instance-dependent declarations without
  repeated per-candidate graph traversal or executing source code for inference.
- Run narrow proving checks first, then the final owning suites and
  `run_verification.py --mode fast --summarize-output`, targeted QML rendering,
  documentation/map checks and independent review.

## Assumptions

- Only explicit forwarding relationships inherit types; arbitrary scripts do not.
- Unconnected authored Panel values keep their existing declared behavior.
- Structural graph checks and actual runtime carrier validation remain authoritative.
- Publication requires separate authorization. Preserve unrelated dirty files throughout.

## Progress

The implementation was checked against its pre-change baseline. Local comparison
evidence remains in the ignored verification artifacts. Task staging excludes
unrelated pre-existing modifications, including the mixed-content specs index.

| Task | Status | Owner | Accepted evidence | Next action |
| --- | --- | --- | --- | --- |
| T01 | Accepted | t01_forwarding; t01_review | 357 tests + 107 subtests; catalog, Ruff and diff checks; independent review clean | Complete |
| T02 | Accepted | t02_graph_runtime; t02_review | 264 tests + 82 subtests; 5 scene/history checks; final runtime 87 + 5; Ruff/diff clean; independent review clean | Complete |
| T03 | Accepted | t03_ui; t03_review | Final UI 10 passed; owning 79 + 23 subtests; 24-test subset including existing QML drag; rendered artifact inspected; independent review clean | Complete |
| T04 | Accepted with baseline verification exceptions | t04_closeout; integration_review; Coordinator | Rewire fix reviewed; 220 serial tests passed; docs/maps/hygiene passed; broad-main exceptions classified below | Complete |

### Final integration

- `graph/type_forwarding.py` owns `GraphTypeResolver`,
  `ResolvedSourceContract(type_ids, has_unresolved_sources)`,
  `PortTypeCompatibility(members)`, and `source_port_compatibility`. Declared ports
  and ordinary scalar catalog compatibility remain separate from inferred sets.
- Quick Insert refreshes live endpoint facts and preserves selected item/port
  identity, coordinates and the actual drag anchor. Popup model/workspace/scope
  guards prevent retargeting across navigation or reload. Real controller tests
  prove both image recommendations create an edge from Trigger output and undo
  the insertion in one action.
- Scene publication compares fresh topology/source contracts with cached state,
  publishing downstream type changes and every pruned edge together. QML tracks
  graph revision separately from the Python endpoint snapshot's catalog
  generation, refreshing same-workspace gestures without weakening cancellation.
- Runtime ports remain Any. Forwarded conversions validate actual source and
  target carriers, follow the catalog-selected conversion and its failure rules,
  and fingerprint selected per-member converter revisions. Retained Trigger
  values cannot bypass these checks.
- `graph/edge_rewire.py` owns `PreparedEdgeRewire`, exposed through
  `ValidatedGraphMutation.prepare_rewire_edges` and shared by preview and fresh
  commit validation. Topology overlays resolve only queried source ancestors.
  The fix matched the original gate in 952 cases and passed graph/history/QML
  regressions. Independent probes use one full resolver and preserve candidate
  lists: 101 nodes improved from 0.296 to 0.0286 s; 201 nodes from 1.279 to 0.0555 s.
- Coordinator and reviewer inspected the readable QML artifact at
  `artifacts/type_forwarding/forwarding-image-drag.png`. The test-only font setup
  is isolated to the QML probe subprocess.

## Final Outcome

Implementation and independent source review are complete. Authoring guides,
requirements, traceability, ownership maps and generated navigation are updated.
These results record implementation acceptance before separately authorized
publication. Unrelated pre-existing work remains outside the feature change.

| Final check | Result |
| --- | --- |
| Hygiene/authoring | 171 tests and 115 subtests passed |
| Feature-related stale-test repairs | 12 tests and 4 subtests passed |
| Post-correction documentation/map hygiene | 29 tests and 82 subtests passed |
| Changed Python Ruff, traceability, Markdown links, maps, generated index freshness, diff | Passed |
| Broad fast main | 5123 passed, 8 failed, 4 skipped; 511.01 s |
| Required fast serial, unchanged manifest command | 220 passed; 107.00 s |
| Isolated Signal Plot visual rerun | 1 passed; 25.55 s |

The broad main run was not fully green. Three failures were stale tests repaired
for the new source-contract fixture and validated removal authority; focused
reruns passed, and all private/raw-model writer prohibitions remain intact.
Four static assertion/subtest failures are pre-existing: fullscreen constructor
expectations, two InspectorPane link-option snippets, and tooltip-category
expectations. Isolated reproduction and baseline file/method comparisons were
independently verified. The eighth failure was a Signal Plot visual cleanup
timeout under 12 workers; its isolated rerun passed, but the concurrency timeout
is not proven fixed. No production code changed after the broad main run, so it
was not repeated merely to reproduce those baseline failures.

Logs and baseline evidence are under
`artifacts/verification_logs/20260911_232602/`: `01_fast.pytest.log`,
`02_baseline_static_failures.log`, `03_fast.serial.pytest.log`, and
`04_baseline_evidence.log`. Feature integration is accepted with these explicit
verification exceptions; no forwarding-source finding remains open.
