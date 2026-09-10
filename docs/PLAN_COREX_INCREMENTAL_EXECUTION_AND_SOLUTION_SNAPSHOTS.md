# COREX Incremental Execution And Solution Snapshots

Status: **COMPLETED — T01–T09 ACCEPTED**

## Summary

This plan replaces workspace-wide rerun behavior with one execution-owned solution
state and reuse system. An execution-affecting mutation expires only the changed
node and its enabled downstream dependency closure. Current nodes retain their
settled outputs, and a prepared run invokes node implementations only for nodes
whose solution record is absent, expired, invalid, ineligible, or explicitly
forced to recompute.

The immediate user-visible acceptance case is a disconnected Model Viewer branch:
after its scene and live transport are ready, changing an unrelated toggle must not
expire, rerun, close, detach, or block that viewer. The same rule applies to every
executable node; Model Viewer is the end-to-end regression, not a special case.

The implementation is a clean current-schema cutover for an unreleased product.
There will be no compatibility adapter, legacy snapshot reader, or migration for
experimental internal metadata. Node coloring, snapshot-management UI, and the
future expired-node visual treatment are explicitly deferred. This plan delivers
the authoritative backend fact that later UI work will consume.

On clean T09 closeout, this plan completes and promotes backend requirements
`REQ-EXEC-017` and `REQ-PERSIST-026`. `REQ-UI-052` remains planned because its
expired-node visuals/actions are outside this implementation.

## Key Changes

### Locked terminology

- `freshness`: one of `never`, `current`, or `expired`.
- `settlement_status`: one of the existing terminal outcomes such as `completed`,
  `empty`, `failed`, or `blocked`. Settlement status is orthogonal to freshness.
- `disposition`: how a prepared execution handled a node: `reused`,
  `recomputed`, `skipped`, or `blocked`.
- `solution_key`: the deterministic SHA-256 identity of one node solution under
  one exact executable dependency and provenance state.
- `solution_record`: validated settled outputs and identity/provenance facts for
  one `solution_key`.
- `session` residency: reusable only while its owning runtime generation remains
  valid.
- `durable` residency: validated, portable, project-managed snapshot data that may
  survive process and application restarts.
- `force_recompute`: an explicit execution request that ignores reusable records;
  it is not an implicit consequence of an unrelated graph edit.

Do not use `dirty` for solution freshness. A dirty Python Script draft remains an
authoring state and must not become a scheduler synonym.

### Architecture invariants

1. `CorexRuntime` owns preparation, solution identity, reuse decisions, solution
   records, invalidation, and the public freshness projection.
2. `ExecutionPlan` is shared execution code. It must not remain worker-private or
   be independently reimplemented in the shell.
3. `ShellRunState.cached_node_output_records_by_workspace_id` remains a bounded UI
   value projection only. It never seeds execution and is not a second freshness
   authority.
4. The worker reconstructs the shared plan and validates every reuse decision
   before installing reused outputs into `NodeExecutor.node_outputs`.
5. Graph presentation facts—position, selection, title, collapse state, colors,
   exposure, and other non-executable UI state—never enter a `solution_key`.
6. A mutation expires the changed executable roots and enabled downstream nodes.
   Disabled edges and Trigger boundaries retain their existing propagation rules.
7. Stale outputs may remain available for bounded inspection, but they cannot
   satisfy a current execution dependency, current port-flow fact, or viewer live
   transport requirement unless a matching solution record is accepted.
8. Viewer invalidation is node-scoped. Workspace-wide invalidation is reserved for
   project replacement, worker/runtime generation reset, registry replacement, or
   an explicit full reset.
9. Durable solution data lives in project-managed sidecar storage, never inline in
   `.cxproj`.
10. Persistence publishes immutable blobs before manifests and prunes unreachable
    data only after the new project/manifests are committed.
11. Credentials, secrets, callbacks, native objects, worker-local handles, Trigger
    publications, and unmaterialized temporary values never enter durable records.
12. Unknown, incomplete, corrupt, or unverifiable state fails closed to
    recomputation; it never becomes a cache hit.

### Canonical state model

Move `RootExecutionError` and `SettledPortResult` from
`ea_node_editor/execution/protocol.py` to the dependency-light
`ea_node_editor/runtime_contracts/settled_results.py`; update every caller to import
the new owner directly, with no protocol re-export.

Add immutable persistence/process-neutral contracts under
`ea_node_editor/runtime_contracts/solution_records.py`:

```text
SolutionFreshness = never | current | expired
SolutionResidency = session | durable
SolutionDisposition = reused | recomputed | skipped | blocked

NodeSolutionFact
  project_id
  workspace_id
  node_id
  freshness
  revision
  retained_record_id: str | None
  retained_solution_key: str | None
  residency: SolutionResidency | None
  expiration_reason_code
  expiration_root_node_ids
  last_disposition: SolutionDisposition | None

SolutionOutputDescriptor
  port_key
  status: value | empty
  data_type_id: declared port type
  concrete_data_type_ids: tuple[str, ...]
  data_access
  item_count
  payload_kinds: tuple[inline | artifact_ref | handle_ref | blob_ref, ...]
  payload_digest
  payload_schema_version

SolutionPayloadLocator
  kind: session | durable
  reference_id
  blob_digests

SolutionRecord
  schema_version = 1
  record_id
  project_id
  workspace_id
  node_id
  solution_key
  workflow_interface_revision
  workflow_interface_digest
  node_contract_digest
  dependency_solution_keys
  input_provenance_digest
  execution_policy_digest
  implementation_digest
  execution_environment_digest
  settlement_status
  result_digest
  reuse_eligible
  output_descriptors: tuple[SolutionOutputDescriptor, ...]
  payload_locator: SolutionPayloadLocator | None
  residency
  runtime_generation
  created_at_epoch_ms

```

Add execution-only immutable preparation contracts under
`ea_node_editor/execution/prepared_execution.py`:

```text
PreparedAction = reuse | execute
RecomputeMode = reuse_valid | force_recompute

PreparedDispatchEnvelope
  project_path
  project_id
  workspace_id
  trigger
  runtime_snapshot
  execution_backend
  target_node_ids
  clicked_trigger_node_id
  trigger_capture_node_ids
  trigger_publications
  trigger_captures
  recompute_mode
  developer_mode
  catalog_fingerprint
  catalog_revisions
  plugin_bundles
  plugin_fingerprint
  runtime_registry_fingerprint
  registry_contract_fingerprint
  addon_runtime_config

PreparedNodeDecision
  node_id
  action
  reason_code
  solution_key
  dependency_solution_keys
  accepted_record_id

AcceptedOutputPayload
  node_id
  record_id
  solution_key
  settlement_status
  result_digest
  residency
  runtime_generation: int | None
  outputs: bounded map[port_key, SettledPortResult]

PreparedExecution
  preparation_id
  dispatch_envelope: PreparedDispatchEnvelope
  solution_namespace_id
  execution_affecting_workspace_revision
  runtime_snapshot_fingerprint
  execution_plan_fingerprint
  registry_contract_fingerprint
  workflow_interface_revision
  workflow_interface_digest
  execution_environment_digest
  trigger_publication_generations: tuple[(trigger_node_id, generation), ...]
  node_decisions
  accepted_output_payloads
  recompute_node_ids
  reused_node_ids

InvalidationResult
  project_id
  workspace_id
  solution_revision
  changed_root_node_ids
  expired_node_ids
  removed_node_ids
  reason_code
```

`PreparedExecution` is frozen. Single-use consumption is stored by `CorexRuntime`
against `preparation_id`; the DTO itself never mutates.

`PreparedDispatchEnvelope` is the complete frozen input needed to construct the
eventual `StartRunCommand`; dispatch reads no mutable external request, registry,
plugin, catalog, trigger, or snapshot state. T01 proves the DTO/adapters. T03 owns
preparation storage and single-use consumption; T04 owns command construction and
worker validation.

Null/optional rules are strict:

- `never`: retained record/key/residency/last disposition are all `None`;
- `current`: retained record/key/residency are required;
- `expired`: retained record/key/residency may remain together for stale inspection
  or all be `None`; partial triples are invalid;
- `PreparedNodeDecision.solution_key` is always a SHA-256 digest;
- `accepted_record_id` is required only for `reuse` and forbidden for `execute`;
- session records/payloads require a positive runtime generation;
- durable records/payloads require `runtime_generation is None`;
- `SolutionPayloadLocator` is `None` only for a reusable outputless/empty
  settlement; a value descriptor requires a matching locator entry.

Strict semantic combinations:

| Contract/state | Required | Forbidden |
| --- | --- | --- |
| `NodeSolutionFact.never` | empty expiration roots/reason | retained triple; residency; last disposition |
| `NodeSolutionFact.current` | retained record/key/residency; last disposition `reused` or `recomputed` | expiration roots/reason |
| `NodeSolutionFact.expired` | non-empty reason and root IDs | partial retained record/key/residency triple |
| `SolutionOutputDescriptor.value` | declared type/access, non-negative item count, sorted unique concrete type IDs and payload kinds (each capped at 64), SHA-256 payload digest, positive payload schema | empty concrete/kind tuples or digest |
| `SolutionOutputDescriptor.empty` | item count `0`, empty concrete type/kind tuples, schema `0`, empty digest | concrete types or payload kinds |
| session `SolutionPayloadLocator` | `kind=session`, bounded opaque session reference ID | blob digests |
| durable `SolutionPayloadLocator` | `kind=durable`, SHA-256 record/payload reference, unique SHA-256 blob digests | runtime-local ID/generation |
| reusable `SolutionRecord` | settlement status `completed` or `empty`; locator kind equals residency | `failed`/`blocked` status; descriptor/locator mismatch |
| `PreparedNodeDecision.reuse` | accepted record ID and exactly one matching `AcceptedOutputPayload` | missing/duplicate payload; failed/blocked payload |
| `PreparedNodeDecision.execute` | no accepted record or payload | accepted payload |

For a `value` record, output descriptor port keys/statuses must match the accepted
payload output map exactly. Outputless completed and wholly empty settlements may
use `payload_locator=None` and an empty accepted output map. Property-style tests
cover every valid row and reject every cross-row combination.

Mixed DataTree carriers/types are valid observation records. Reuse is allowed only
when every concrete type/carrier in the bounded descriptor is valid for the
record's residency and integrity/generation checks; otherwise the record remains
truthfully current with `reuse_eligible=false`.

`NodeSolutionFact` is the only mutable freshness projection. `SolutionRecord`
objects are immutable after publication. Expiration changes the node fact; it does
not rewrite historical records.

`SolutionRecord.settlement_status` preserves the terminal semantic needed to replay
completed, empty, and outputless settlements. `result_digest` binds the canonical
typed output payload. `payload_locator` resolves through the execution store:

- session records point to an immutable in-memory typed-output entry owned by the
  same `SolutionStore` and runtime generation;
- durable records point to codec-validated content-addressed result blobs owned by
  the durable repository.

`PreparedNodeDecision` never embeds an unbounded payload. During preparation,
`SolutionStore.accepted_outputs(decision)` resolves the locator, verifies the
result digest, catalog contract, artifact integrity, residency, and handle/runtime
generation, then freezes the bounded typed outputs carried by the finalized
preparation's `accepted_output_payloads`. Every payload is bound to node ID, record
ID, solution key, settlement status, result digest, residency, and nullable runtime
generation. Session payloads require an exact current runtime generation; durable
payloads require `runtime_generation is None`. Queue-boundary adapters
apply the same strict DataTree/value/count/depth/byte limits as settled runtime
results; large values remain validated artifact/blob/handle references rather than
inline bytes. A missing or invalid payload becomes `execute` before
`PreparedExecution` is published, so `recompute_node_ids` is final and truthful.
Dispatch revalidation may only accept the complete immutable preparation or reject
it and require re-preparation; it never mutates an action or recompute set.

T01 establishes these queue-boundary ceilings in the shared settlement/solution
adapters; outbound payloads are reparsed under the same limits before handoff:

```text
MAX_PREPARED_NODES = 100_000
MAX_OUTPUTS_PER_NODE = 1_024
MAX_ACCEPTED_NODE_PAYLOADS_PER_PREPARATION = 100_000
MAX_ACCEPTED_PORT_RESULTS_PER_PREPARATION = 1_000_000
MAX_DATA_TREE_BRANCHES_PER_OUTPUT = 100_000
MAX_DATA_TREE_ITEMS_PER_OUTPUT = 1_000_000
MAX_ROOT_ERRORS_PER_RESULT = 64
MAX_TYPED_INLINE_BYTES = 1_048_576        # existing 1 MiB rule
MAX_REFERENCE_METADATA_BYTES = 65_536     # existing 64 KiB rule
MAX_ACCEPTED_OUTPUT_PAYLOAD_BYTES = 67_108_864  # aggregate 64 MiB
MAX_JSON_DEPTH = 32                       # existing rule
```

Count/aggregate breaches, duplicate IDs/keys, unknown fields, booleans supplied as
integers, invalid optional combinations, or oversized inline values are rejected.
During preparation, reusable nodes are considered in deterministic execution order.
If accepting another reuse would exceed the node, port-result, or aggregate-byte
budget, that node and all dependent reuse decisions become `execute` with reason
`reuse_payload_budget_exceeded` before the immutable preparation is published.
There is no command chunking in this plan.

The 64 MiB aggregate applies only to serialized `accepted_output_payloads` plus
adapter overhead. Ordinary settlement traffic retains its existing protocol
limits. A maximum-size `ImageValue` is not eligible as inline accepted output; it
must be represented by a validated artifact/blob reference. Large legitimate
values use validated artifact/blob/handle references.

### One solution store, two residencies

Add `ea_node_editor/execution/solution_store.py` as the only scheduler-facing
store. It owns session records, node facts, record selection, invalidation, and
record publication. It owns these execution-facing persistence ports; execution,
worker, compiler, and store code never import `ea_node_editor.persistence`:

```text
DurableSolutionBackend
  lookup_record(workspace_id, node_id, solution_key, catalog)
    -> DurableLookupResult
  load_payload(record, catalog)
    -> DurablePayloadResult
  stage_record(record, canonical_payload, catalog)
    -> DurableStageResult
  close() -> None

DurableSolutionBackendFactory
  open_backend(project_id, project_path, metadata_solution_store, catalog)
    -> DurableBackendOpenResult

DurableLookupResult
  record: SolutionRecord | None
  reason_code

DurablePayloadResult
  outputs: tuple[(port_key, SettledPortResult), ...] | None
  reason_code

DurableStageResult
  record: SolutionRecord | None
  reason_code

DurableBackendOpenResult
  backend: DurableSolutionBackend | None
  solution_namespace_id
  active_generation_id
  active_manifest_set_digest
  status_code
  diagnostic
```

Result combinations are strict and type-specific as defined below; no result
carries payload fields belonging to another result type. Diagnostics are sanitized
UTF-8 capped at 512 bytes and never include raw
metadata, secret values, absolute paths, or exception `repr`. `close()` is
idempotent and never deletes repository content. Malformed/corrupt repository state
crosses this port only as a deterministic result code, not a persistence exception.

`durable_bound_active` requires a backend, valid namespace, valid active generation
ID/digest pair, and empty diagnostic. Every `durable_session_only_*` status requires
`backend=None`, the runtime's valid session namespace, no active pointer, and
exactly one sanitized bounded diagnostic.
`durable_hit` requires a record/output; every other lookup/load reason forbids it.
`durable_stage_published` and `durable_stage_existing_identical` require a record;
every other stage reason forbids one.

Add `ea_node_editor/persistence/solution_repository.py` as the durable backend.
`SolutionRepository` structurally implements the execution ports. Shell and
headless composition inject the concrete factory when constructing `CorexRuntime`.
The runtime does not invoke the factory until authored project decoding succeeds
and `bind_project_solution_store()` is called. Execution imports no concrete
persistence implementation; session-only use requires no backend.

The runtime binding contract is explicit:

```text
CorexRuntime.bind_project_solution_store(
  project_id,
  project_path,
  metadata_solution_store,
) -> DurableBackendOpenResult
CorexRuntime.detach_project_solution_store(project_id, reason) -> None
```

Candidate construction and manifest-set validation complete before replacement.
Under the runtime lifecycle lock, bind atomically detaches the previous store
backend and installs the validated candidate or session-only state. Backend close,
diagnostics, and callbacks occur after store/runtime locks are released.

New/unsaved projects and missing/invalid solution metadata use session residency
only. Runtime-generation reset releases runs/preparations/session records and
loaded durable payload/negative caches while retaining the durable backend and
immutable content. Project detach/replacement clears durable indexes/caches/facts,
closes the backend, and never deletes sidecar content. Shutdown detaches/closes.
Save As keeps the source binding until T08 destination reopen succeeds.

Qt-free/headless construction uses dependency injection, not an execution-to-
persistence import inside the store/compiler/worker:

```text
CorexRuntime(
  solution_repository_factory: DurableSolutionBackendFactory | None = None,
)
```

Tests inject in-memory/faulting ports. `common/` remains a leaf and does not acquire
a generic storage framework.

#### T08 project-solution save/export port

T08 adds no persistence import to execution, no concrete solution-repository
reference to `ProjectDocumentIOService`, and no generic transaction framework.
`solution_store.py` owns frozen, slotted, persistence-neutral contracts:

```text
ProjectSolutionSaveRecordExport
  record: SolutionRecord
  canonical_payload: bytes
  maximum_reuse_scope: durable
  is_current: bool

ProjectSolutionSaveSnapshot
  project_id
  source_project_path
  solution_namespace_id
  binding_revision
  registry_contract_fingerprint
  source_artifact_context_digest
  snapshot_token
  source_generation_id
  source_manifest_set_digest
  retained_owner_ids: sorted unique tuple[(workspace_id, node_id), ...]
  supplemental_records: tuple[ProjectSolutionSaveRecordExport, ...]
  required_managed_artifact_ids: sorted unique tuple[str, ...]
  estimated_copy_bytes

ProjectSolutionSaveResult
  snapshot_token
  solution_namespace_id
  candidate_generation_id
  candidate_manifest_set_digest
  previous_generation_id
  previous_manifest_set_digest
  initially_protected_generations:
    tuple[(generation_id, manifest_set_digest), ...]
  orphan_candidate_relative_paths
  orphan_scan_complete
  omitted_record_count
  estimated_copy_bytes
  staged_new_bytes
  reason_code
  diagnostic

ProjectSolutionAdoptionResult
  adopted
  reason_code
  diagnostic

ProjectSolutionCandidateResult
  prepared
  reason_code:
    project_solution_candidate_prepared |
    project_solution_candidate_snapshot_stale |
    project_solution_candidate_invalid |
    project_solution_candidate_io_error
  diagnostic

ProjectSolutionGcResult
  candidate_relative_paths
  removed_relative_paths
  has_more
  reason_code
```

`ProjectSolutionSaveRecordExport.maximum_reuse_scope` is exactly `durable`.
A session-resident export is allowed only when retained by the current
`NodeSolutionFact` and `_RecordEntry.maximum_reuse_scope == "durable"`. A durable-
resident export may be current or a T07-staged historical record. `_RecordEntry`
therefore retains `maximum_reuse_scope`; lazy-loaded durable entries set it to
`durable`.

`source_generation_id` and `source_manifest_set_digest` are both empty or both
identify the fully validated active generation of the currently bound backend.
Missing, unsupported, corrupt, or session-only source metadata produces an empty
source pointer; it is never read or migrated as cache input.

`retained_owner_ids` is the removed-owner filter and comes from the candidate
project, never artifact-owner inference. The snapshot reuses T07 bounds: at most
100,000 retained owners, 16,384 supplemental in-memory records, the existing per-
record/store payload ceilings, and candidate-generation record/4-GiB ceilings.
New GC bounds are:

```text
MAX_PROJECT_SOLUTION_ORPHAN_SCAN_ENTRIES = 100_000
MAX_PROJECT_SOLUTION_ORPHAN_CANDIDATES = 10_000
```

A capped scan returns the lexicographically first safe candidates and
`orphan_scan_complete=false`; later passes continue from current filesystem state.

`ProjectArtifactStore.project_save_context_digest()` returns 64 lowercase hex over
canonical artifact-store metadata plus normalized source project path without
value/catalog callbacks. `snapshot_token` is 64 lowercase hex:

```text
snapshot_token = SHA256(
  canonical tagged T08 snapshot payload excluding snapshot_token
)
```

The payload binds every snapshot field, complete canonical
`SolutionRecord.to_payload()` data, canonical payload size/SHA-256, maximum scope/
current flag, owners/artifact IDs, binding revision, registry contract fingerprint,
and source artifact-context digest.

`DurableSolutionBackendFactory` adds:

```text
export_project_solution_save(
  project_id,
  source_project_path,
  solution_namespace_id,
  source_generation_id,
  source_manifest_set_digest,
  retained_owner_ids,
  supplemental_records,
  binding_revision,
  registry_contract_fingerprint,
  source_artifact_context_digest,
  catalog,
  source_artifact_context,
) -> ProjectSolutionSaveSnapshot

stage_project_solution_save(
  snapshot,
  destination_project_path,
  catalog,
  destination_artifact_context,
) -> ProjectSolutionSaveResult

open_project_solution_save_candidate(
  project_id,
  destination_project_path,
  metadata_solution_store,
  expected_namespace_id,
  catalog,
  destination_artifact_context,
) -> DurableBackendOpenResult

collect_project_solution_garbage(
  project_id,
  project_path,
  active_generation_id,
  active_manifest_set_digest,
  extra_protected_generations,
  candidate_relative_paths,
  orphan_scan_complete,
  limit,
  catalog,
) -> ProjectSolutionGcResult
```

`CorexRuntime` exposes:

```text
capture_project_solution_save(
  project_id,
  source_project_path,
  retained_owner_ids,
  source_artifact_context,
) -> ProjectSolutionSaveSnapshot

stage_project_solution_save(
  snapshot,
  destination_project_path,
  destination_artifact_context,
) -> ProjectSolutionSaveResult

project_solution_save_snapshot_is_current(snapshot_token) -> bool

prepare_project_solution_adoption(
  result,
  project_id,
  destination_project_path,
  metadata_solution_store,
  destination_artifact_context,
) -> ProjectSolutionCandidateResult

adopt_project_solution_save(
  result,
  project_id,
  destination_project_path,
  metadata_solution_store,
  destination_artifact_context,
) -> ProjectSolutionAdoptionResult

cancel_project_solution_save(snapshot_token) -> None

collect_project_solution_garbage(
  result,
  *,
  protect_previous_generation,
  limit=10_000,
) -> ProjectSolutionGcResult
```

Capture briefly holds runtime lifecycle/store locks only to copy immutable
namespace, binding token, record, payload, maximum-scope, and backend-pointer facts.
Repository export, validation, artifact inspection, copying, hashing, and all other
I/O run without runtime/store locks. The runtime rechecks backend identity,
namespace, and binding revision before publishing the snapshot token.

Settlement after capture does not invalidate a snapshot; newly settled cache data
may wait for the next save. Project reset/detach, backend or namespace replacement,
registry replacement, or another binding adoption invalidates it.

Candidate backend construction/full validation occurs outside runtime/store locks.
Under the lifecycle lock adoption installs it only when the token remains current
and namespace equals the snapshot. Failure closes the candidate outside locks and
retains the source backend/session state.

`SolutionStore.install_durable_backend()` retains the normalized active generation
ID/digest pair from `DurableBackendOpenResult`; capture reads it under the store
lock. `stage_project_solution_save()` publishes the candidate generation but
retains no precommit backend. After project publication,
`prepare_project_solution_adoption()` freshly reopens the committed pointer, fully
validates generation/records/blobs/values/managed artifacts against the reopened
destination store, and retains exactly one pending candidate backend keyed by
`snapshot_token`. Failure closes it outside locks. `adopt_project_solution_save()`
performs no I/O/callbacks: under the lifecycle lock it requires exact stored-
snapshot/result/token/namespace equality and swaps the pending candidate. Cancel,
failure, reset, or replacement closes it outside locks.

Factory save reasons are exact:

```text
project_solution_save_staged
project_solution_save_snapshot_stale
project_solution_save_source_invalid
project_solution_save_destination_invalid
project_solution_save_artifact_invalid
project_solution_save_capacity_exceeded
project_solution_save_generation_invalid
project_solution_save_io_error

project_solution_adopted
project_solution_adoption_snapshot_stale
project_solution_adoption_namespace_mismatch
project_solution_adoption_candidate_invalid
project_solution_adoption_io_error

project_solution_gc_completed
project_solution_gc_partial
project_solution_gc_skipped_invalid
project_solution_gc_io_error
```

DTO rules are strict:

- `snapshot_token`, fingerprints, and artifact-context digest are exactly 64
  lowercase hex; generation IDs/digests use T07 grammar;
- project ID/namespace are nonempty, trimmed, bounded, and control-free;
  `source_project_path` is exact normalized absolute string or empty for unsaved;
- binding revision is a nonnegative exact integer and rejects Boolean;
- artifact IDs are trimmed, bounded, control-free, sorted unique; every
  supplemental owner exists in `retained_owner_ids`; session-resident export
  requires `is_current=true`;
- counts/byte sizes are nonnegative exact integers and reject booleans;
- `project_solution_save_staged` requires candidate pointer, empty diagnostic, and
  a previous pointer that is both present or both empty;
- failed save results retain token/namespace for cancellation but forbid candidate/
  previous pointers, protection/orphan paths, and nonzero counters; one sanitized
  diagnostic is required;
- adoption success is `adopted=true`, `project_solution_adopted`, empty diagnostic;
  every other reason is `false` with one sanitized diagnostic;
- candidate prepared requires `project_solution_candidate_prepared` and empty
  diagnostic; every failure is `prepared=false` with one sanitized diagnostic;
- GC `completed` requires `has_more=false`, `partial` requires `true`, and skipped-
  invalid removes nothing.

Adoption/GC failures expose no backend.

`CorexRuntime` stores the exact snapshot object. Capture, stage, candidate
preparation, and adoption recompute the token and require exact stored-snapshot
equality; copied-token altered DTOs fail stale/invalid.

`ProjectSolutionSaveSnapshot.estimated_copy_bytes` is a conservative no-write
projection using publication encoders/layout. It includes every reachable active-
generation result blob, record JSON, node manifest, and manifest set, plus worst-
case result blob/record/node-manifest/manifest-set bytes for every supplemental
record. Active generation is counted fully even when content may be reused;
supplemental records are counted before deduplication/omission/trimming.

`ProjectSolutionSaveResult.estimated_copy_bytes` equals the snapshot estimate.
`staged_new_bytes` counts only newly published raw solution bytes and must satisfy
`0 <= staged_new_bytes <= estimated_copy_bytes`; failed results carry both counters
as zero. Document free-space preflight includes this estimate. A stage result above
the estimate fails before project-file publication.

Candidate construction starts from the validated active generation, omits removed
owners, and merges T07-staged records plus current session records whose captured
maximum scope is durable. Invalid/corrupt active generation is discarded whole,
its pruning is disabled, and a fresh generation is built from validated
supplemental records. Invalid solution-only artifact/value records are omitted and
increment `omitted_record_count`. Same `(workspace, node, solution_key)` and result
retains one record; differing results omit that key. Capacity trims non-current
historical, then supplemental records deterministically, retaining newest by
`(created_at_epoch_ms, record_id)` and current supplemental records before active
historical. Even an empty selection produces a valid schema-1 generation. Only
malformed capture token/identity/namespace or inability to publish/validate even an
empty destination generation fails solution staging.

Session namespace and retention are locked:

- a project keeps one namespace for its loaded lifetime;
- valid solution metadata supplies the stored namespace;
- a saved project without solution metadata uses `project_id` as its session-only
  fallback;
- an unsaved project receives one random namespace;
- T08 persists the current namespace on first save and preserves it through Save
  As, even when it differs from `project_id`;
- maximum two session records per node (current plus newest historical);
- maximum 4,096 session records per workspace;
- maximum 536,870,912 bytes (512 MiB) of canonical session payload per workspace;
- maximum 16,384 session records across the runtime;
- maximum 2,147,483,648 bytes (2 GiB) of canonical session payload across the
  runtime;
- maximum 64 outstanding preparations and 268,435,456 bytes (256 MiB) of frozen
  preparation envelopes/payloads across the runtime;
- current fact records and active preparation/run references are pinned;
- eviction is oldest unpinned non-current first, deterministic by creation sequence
  then record ID;
- if a new record cannot fit after legal eviction, do not publish it and leave the
  node `expired` with reason `session_store_capacity_exceeded`.

Before registering preparation 65 or crossing the preparation-byte ceiling, evict
the oldest unconsumed preparation by creation sequence then preparation ID and
release every record pin and Trigger reservation it owns. Dispatch of an evicted
ID fails `preparation_evicted`. Start failure, every terminal event, generation
reset, project replacement, and shutdown release the corresponding preparation/run
context, pins, and Trigger reservations. Current records and active-run references
remain non-evictable; capacity exhaustion fails closed as above.

Every settled executable node may publish an observation `SolutionRecord` so its
fact can become `current`. `solution_reuse_scope=never` records set
`reuse_eligible=false`, are never inserted into the solution-key reuse index, and
remain subject to the same retention limits. T03 adds this field to the contract
and tests; it does not broaden any T02 classification.

`CapturedNodeSolution` stores the declared maximum `solution_reuse_scope`, not a
Boolean eligibility approximation. Record selection is deterministic:

1. validate an exact current in-memory record;
2. otherwise ask the bound durable backend for the exact workspace/node/solution
   key;
3. load and validate its payload only when preparation requests accepted outputs;
4. install the durable record/index/fact atomically only after record and payload
   pass binding, catalog, descriptor, digest, artifact, and value validation.

A lazy-load failure installs no partial record, reuse index, fact, or payload.

Publication follows the declared maximum:

- `never`: publish only the existing non-reusable observation record;
- `session`: use existing session publication;
- `durable` without a valid backend or with a durably ineligible/oversized result:
  publish a session record when ordinary session validation succeeds;
- `durable` with a valid backend/payload: construct canonical payload and a complete
  durable `SolutionRecord`, then call `stage_record`;
- durable capacity/I/O/ineligibility failure may fall back to valid session
  publication with a sanitized durable diagnostic;
- same key/same result retains the established durable record;
- same key/different result returns `durable_nondeterminism_conflict`, publishes no
  replacement at either residency, preserves the established record, and leaves
  the fact expired with `nondeterministic_solution_result`.

Forced recomputation ignores records for reuse but still consults the established
active/staged durable mapping for conflict detection. T07 reuses the existing T04
worker payload path; it adds no worker or scheduler path.

Each registered run stores per node the captured solution key and captured
`NodeSolutionFact.revision`. On settlement, under the store lock:

- reject stale preparation/run/backend generations completely;
- validate and canonically reparse completed/empty outputs with the active catalog;
- publish records only for valid completed/empty settlements;
- make a fact `current` only when its current node revision still equals the
  captured revision;
- keep it `expired` when that node was invalidated after preparation, even if an
  unrelated branch remained unchanged;
- preserve earlier records on failure, block, stop, or cancellation;
- same-key/same-result retains the established immutable record;
- same-key/different-result reports nondeterminism and leaves the fact expired.

Disposition-specific settlement handling is explicit:

- `reused`: validate against the registered decision, accepted payload, pinned
  record, event digest, generation, and node revision; publish no new record and
  set `last_disposition=reused` only if the capture remains current;
- `recomputed` completed/empty: use normal record/nondeterminism publication;
- `recomputed` failed, `skipped`, and `blocked`: publish no record and preserve
  prior retained data/freshness rules;
- late invalidation prevents both reused and recomputed events from restoring
  `current`.

User/event callbacks run only after releasing the store lock. Lock order is:
`CorexRuntime lifecycle RLock -> client registry-publication RLock -> brief
SolutionStore RLock`; client calls never occur while holding the store lock.

Adding durable storage changes a record's eligible residency, not the planner,
solution key, or scheduler authority. Do not build separate session and durable
cache frameworks.

`runtime_contracts/durable_values.py` owns one dependency-light durable value gate
consumed by `prepared_execution.py`, `solution_store.py`,
`solution_records.py`, and `solution_repository.py`:

```text
validate_durable_settled_outputs(outputs, descriptors, catalog, artifact_context)
  -> DurableRuntimeValueValidation

DurableRuntimeValueValidation
  eligible
  reason_code
  canonical_payload: bytes | None
```

It traverses exact built-in/runtime-contract types without invoking user-controlled
`repr`, iteration, callbacks, filesystem hooks, or network hooks. After exact
structural/type validation, only the trusted `artifact_context` may perform bounded,
no-follow local descriptor/content-integrity reads for a managed
`RuntimeArtifactRef`; it never invokes methods supplied by the value. It validates
the declared and every concrete catalog type for schema, assignability,
`persistence != "never"`, and `sensitivity == "normal"`.

Durable values are limited to strict JSON-native values, `DataTree`, `Interval1D`,
`TypedInlineValue`, valid sub-1-MiB `ImageValue`, and validated managed
`RuntimeArtifactRef`. Managed artifacts require managed scope plus current
descriptor, target, size, SHA-256, provenance, containment, and content integrity.
Reject staged artifacts, `RuntimeHandleRef`, `TabularDataRef`, `ArrayDataRef`,
`TabularWindowRef`, `ArraySlice2DRef`, secret/SSH markers, callbacks,
native/unknown objects, raw bytes/sets, `temp://`/`saved://`, absolute/private
paths, staging/session-temporary paths, unsupported markers, or existing count/
depth overflow. Values beyond the 1-MiB inline ceiling, including large
`ImageValue`, remain session-only; T07 adds no image/blob worker carrier.

#### Staged authority cutover

T03 builds and tests `SolutionStore`, preparation, invalidation, and event capture,
but does not route existing shell/manual/Auto/Trigger dispatch through them. A run
without a registered prepared/run context is ignored by the store and continues to
use the legacy shell projection. T04 makes prepared dispatch/reuse executable; T05
switches shell invalidation/freshness and removes the legacy authority. This is a
deliberate dormant-to-cutover sequence, not two production schedulers.

`CorexRuntime.start_run(...)` remains temporarily through T04 and is removed with
its shell call sites in T05. T03 must not claim the sole production freshness
authority before that cutover.

### Shared plan and preparation flow

Move `ExecutionPlan` from `ea_node_editor/execution/worker_runtime.py` to
`ea_node_editor/execution/execution_plan.py`. T01 moves current worker/runtime/tests
to the new owner and removes the old re-export. `CorexRuntime` begins consuming the
shared class in T03 when preparation is introduced; T01 does not add a speculative
planning call site.

Replace direct start-only dispatch with:

```text
prepared = CorexRuntime.prepare_execution(ExecutionRequest)
run_id = CorexRuntime.dispatch_prepared(prepared)
```

Preparation is side-effect free. It compiles the requested closure, calculates
solution keys in topological order, selects valid records, and returns exact
`recompute_node_ids`. Each prepared decision is only `reuse` or `execute`;
`skipped` and `blocked` are runtime outcomes that cannot be predicted before
recomputed upstream nodes settle. Dispatch consumes the preparation exactly once.

`CorexRuntime` owns an execution-affecting workspace revision that advances only
for executable graph/property changes, registry/runtime identity changes, and
solution resets—not cosmetic edits. Preparation captures this token. Dispatch is
performed under the same runtime/host lock and rejects a token mismatch, project or
workspace mismatch, registry/environment drift, or plan fingerprint change.

Concrete execution clients expose
`execution_generation_snapshot(selection: ExecutionBackendSelection)` and one
generation-aware event subscription. The immutable snapshot includes resolved
backend, backend generation, physical/runtime generation, stable environment
digest, and `available/reason`. `ExecutionBackendClient` preserves this metadata
when forwarding events; callbacks run after releasing every client lock.
`CorexRuntime` never inspects client private fields. A cold/dead external worker
returns unavailable and produces execute-only identity; its successful handshake
publishes the exact generation/environment used by later preparation. Idle worker
death, backend replacement, executable change, registry recycle, and shutdown
notify the runtime so all affected session records/payloads are evicted.

Preparation may read/load the project, retain a candidate registry privately,
compile the snapshot, hash declared external inputs, and register an immutable
preparation. It must not call `replace_registry()` or alter client/viewer generation
during preparation. “Side-effect free” means no node execution, registry
publication, external write/effect, fact freshness change, record publication, or
viewer invalidation; it is not a promise of zero reads or zero internal registration.

Clients add a two-step caller-ID run API:

```text
reservation = ExecutionBackendClient.reserve_run(selection, workspace_id)
started = ExecutionBackendClient.start_reserved_run(reservation, command)
ExecutionBackendClient.release_run_reservation(reservation, reason)
```

Under the runtime lifecycle lock and client registry-publication lock, dispatch
first publishes/revalidates the candidate registry. It then takes the route-specific
post-publication generation snapshot and reserves the caller-owned run ID against
that exact generation. For a cold route, reservation performs/binds the handshake
generation atomically before any workflow event callback. Dispatch then atomically
consumes the preparation and registers the complete run capture in `SolutionStore`
before calling `start_reserved_run`. Synchronous settlement/terminal events
therefore always find context. Failed start releases the reservation/context/pins
and preserves prior facts/records. Tests cover registry-changing and cold
synchronous-settlement/terminal starts.

If complete reusable identity cannot be built, the node receives an execute-only
SHA-256 key over a version tag, namespace/workspace/node, preparation ID, workspace
solution revision, and deterministic failure reason. It is never inserted into the
reuse index.

Trigger generations are committed publication facts. Preparation uses the current
committed generation for ordinary Trigger dependencies and reserves `current + 1`
only for the clicked Trigger. The reservation is stored in the preparation/run
context; it commits only on a validated `trigger_published` event. Failure, stop,
cancellation, or stale generation discards the reservation without advancing the
counter.

`dispatch_prepared()` extends `StartRunCommand` with the typed prepared decisions.
The worker reconstructs `ExecutionPlan`, recalculates the decision inputs, and
rejects the command if its scheduled nodes or fingerprints disagree. Accepted
reused outputs are installed before dependent nodes run.

The worker emits no `node_started` event for reused nodes. The worker determines
the final `SolutionDisposition`: accepted reuse becomes `reused`; a successfully
executed node becomes `recomputed`; and runtime dependency outcomes may become
`skipped` or `blocked`. It emits one normal `node_settled` event with these
additive fields:

```text
disposition
decision_reason
solution_key
record_id
residency
```

The event remains the one settlement stream used by shell projections, port-flow
state, previews, run counts, diagnostics, and future freshness UI.

### Solution identity

Add `ea_node_editor/execution/solution_identity.py`. Use canonical tagged JSON
encoded as UTF-8 and SHA-256. The encoder must preserve type distinctions,
ordered DataTree paths/items, IEEE-754 special-value policy, `None`, bytes through
validated blob refs only, and deterministic map/set ordering. It must never call
user `repr`, iteration hooks, callbacks, filesystem access, or network access.

Each node `solution_key` binds:

- stable logical solution-namespace/workspace/node identity. The solution namespace
  is stored in current-schema project metadata and is preserved by Save As;
- a validated normalized workflow-interface revision and digest covering the
  execution-facing portion of `REQ-NODE-036`;
- node type ID and normalized execution contract digest;
- resolved effective input/output ports, access modes, readiness rules, and
  execution-relevant per-port modifiers;
- authored execution properties after defaults/normalization;
- enabled compiled incoming edges, endpoints, port keys, conversions, and
  `input_order`;
- execution-relevant hidden ordering/dependency links;
- ordered upstream `solution_key` values or explicit Trigger publication
  generation;
- managed/runtime artifact semantic type, schema, format, byte size, SHA-256,
  producer facts, logical/project-relative identity, and current integrity. Do not
  hash destination-root-specific store descriptors;
- plain file content SHA-256 plus the node's normalized path policy;
- directory content through a deterministic relative-path/content tree hash, or
  `session`/`never` eligibility when the node has no directory provenance codec;
- node implementation digest;
- only the data-type/conversion revisions the node actually uses;
- a stable `execution_environment_digest` covering backend, isolation mode,
  interpreter build, relevant packages/add-ons/toolchains, and result-affecting
  execution policy.

Exclude run ID, timestamps, UI state, selection, view state, trigger labels,
console settings, explanatory reason text, project absolute path, destination
artifact root, and ephemeral runtime-generation counters. Runtime generation is
validated separately for session records and live handles; it is never part of a
durable key.

The workflow-interface digest is a prerequisite, not optional wording. T02 defines
its normalized execution-facing representation and revision owner. Records without
a valid interface digest are ineligible for durable residency. T09 requirement
promotion requires the interface acceptance tests and final clean verification.

External provenance hashing is bounded by a versioned `ProvenanceHashPolicy`
included in the execution policy digest:

```text
follow_symlinks_or_reparse_points = false
max_single_file_bytes = 68_719_476_736        # 64 GiB
max_directory_total_bytes = 68_719_476_736   # 64 GiB
max_directory_entries = 100_000
max_directory_depth = 32
```

Hashing streams in bounded chunks, observes cancellation between chunks/entries,
and compares file identity/size/mtime before and after reading. A reparse point,
limit breach, cancellation, permission failure, or change during hashing yields a
deterministic non-reusable reason and an `execute` action without publishing a
solution record. Directory reuse is allowed only for nodes whose accepted
classification names this exact policy; otherwise directory inputs remain `never`.

`execution/solution_identity.py` owns one shared per-node solution-key assembler.
Both runtime preparation and worker validation call it with the namespace,
workspace revision, preparation ID, Trigger generations, environment digest,
plan/dependency keys, catalog, provenance, and execution policy. Do not duplicate
the runtime's identity assembly in worker code.

### Reuse eligibility

Extend the node execution contract with one explicit internal field:

```text
solution_reuse_scope = never | session | durable
```

Default is `never`. Every executable built-in, add-on function, trusted helper,
and public function declaration must be classified deliberately.

- `never`: external side effects, untracked environment/network state, hidden
  mutable worker state, nondeterminism, or incomplete provenance.
- `session`: deterministic within one runtime generation, including live handles
  or temporary resources that cannot be serialized safely.
- `durable`: deterministic and fully described by portable identity/provenance,
  with every output supported by a durable codec.

All public/untrusted declarations are locked to `never` for this plan. Bundle
digests and declared I/O do not prove absence of hidden environment, network,
time, randomness, or side effects. Public opt-in requires a separate accepted
trust/provenance contract and is not introduced here.

Implementation identity must be content based. Module and qualified names alone
are insufficient. Built-ins bind the packaged source/build digest; public
functions bind their existing bundle/function source digest; add-ons bind package
and implementation digests.

File/directory provenance is declared, never inferred from property names. Add an
internal `SolutionProvenanceInputSpec(property_key, kind=file|directory,
policy_revision)` tuple on `NodeTypeSpec`, but keep public/static declaration
syntax unchanged. A registry-owned typed table in
`ea_node_editor/nodes/solution_provenance.py` overlays only the accepted shipped
session readers (`engineering.cad_import`, `engineering.fe_import`, `io.file_read`,
`io.image_import`, `io.excel_read`, and `tabular.input`) during trusted registry
construction. Public/package rows never receive the overlay. Missing or mismatched
declarations make identity execute-only.

#### Locked initial classification rules

T02 must produce the exact registry-row inventory at
`docs/specs/perf/COREX_SOLUTION_REUSE_CLASSIFICATION.md` before changing any node
metadata. The implementation sub-agent may apply only an inventory accepted by the
orchestrator/reviewer. These family rules are locked:

| Executable family | Initial maximum | Required evidence |
| --- | --- | --- |
| Pure scalar/List/Tree transforms with catalog codecs | `durable` | deterministic implementation digest, normalized properties/ports, durable output codecs |
| Pure geometry/mesh/FE transforms returning portable managed artifacts | `durable` | content-addressed artifact outputs, toolchain digest, deterministic codec |
| File/directory import readers | `session` until proven durable | content/tree hash, path policy, importer/toolchain digest; no timestamp-only identity |
| CAD Import in the primary acceptance chain | `session` initially | source content hash, importer digest, session-valid prepared-scene output |
| Model Viewer and nodes producing live/native/runtime handles | `session` | matching runtime generation and handle/transport validation |
| Pure plotting/image rendering with stable artifact output | `durable` only after codec audit | input keys, renderer/package digest, content-addressed output |
| Trigger/sample-and-hold | `never` for durable; existing session semantics remain explicit | publication generation is not snapshot persistence |
| File/process/email/SSH/export/write/remote/service side effects | `never` | none; execution is the effect |
| Time/random/network/environment-dependent compute without captured provenance | `never` | may be reclassified only after explicit deterministic provenance contract |
| Public/untrusted function declarations | `never` | locked for this plan; no opt-in surface |
| Hidden mutable worker-state/optimization pairs | `never` or one coupled `session` decision | state snapshot codec and coupled invalidation proof required |
| Passive/display-only nodes | not executable | excluded from solution records |
| Unknown/unclassified executable node | `never` | fail closed |

The inventory must enumerate every current executable registry row with: type ID,
owner family, proposed scope, side-effect classification, implementation digest
source, input provenance, output codec, handle/artifact facts, reason, and proving
test. No row may inherit a broader scope merely from its category label.

T02's current retained baseline is 139 rows: 101 executable and 38 excluded
(35 passive, 3 compile-only). The conservative initial totals are:

- `durable`: 29 explicitly proven pure/portable rows;
- `session`: 27 file-reader, viewer, runtime-handle/ref, or currently non-durable
  codec rows;
- `never`: 45 rows;
- excluded: 38 non-executable rows.

Runtime-discovered public plugins remain outside the tracked row inventory and are
forced to `never`; never publish their private IDs or paths. The classification
artifact is the exact row authority and must preserve these totals unless a
reviewer reopens T02 with concrete identity/codec evidence. A non-durable input
carrier caps a row at `session` even when every output has a durable codec.

### Invalidation and Auto/manual behavior

Move executable invalidation authority out of mutable shell cache fields:

```text
CorexRuntime.invalidate_solution(
  project_id,
  workspace_id,
  runtime_snapshot,
  changed_root_node_ids,
  reason_code,
) -> InvalidationResult
```

The shared plan calculates the affected enabled downstream closure with current
Trigger boundaries. The result includes exact expired node IDs and a monotonic
workspace solution revision. `RunController` projects this result but does not
recalculate another closure.

`ExecutionPlan.affected_downstream_closure(root_node_ids)` is the only closure
owner. It validates/deduplicates roots, includes roots, traverses enabled compiled
data edges plus validated hidden-ordering pairs, includes a Trigger reached from
upstream but stops beyond it, does not traverse from a Trigger root, returns
deterministic plan/declaration order, and reports the contributing root IDs for
each affected node.

- Auto requests the affected target closure and the planner reuses any still-valid
  upstream records.
- Manual Run may continue to request all active nodes, but only `recompute`
  decisions invoke node implementations.
- Run Selected requests selected targets; current upstream dependencies are reused
  and expired/missing upstream dependencies are recomputed.
- A future Run Expired UI action may pass the exposed expired IDs. This plan
  provides the backend API but no new action or visual control.
- `force_recompute` explicitly ignores valid records within the requested closure.
- A mutation during an active run expires the affected captured keys. Late
  settlements remain historical records for their captured keys and cannot make
  the current node fact current.

Remove shell-owned scheduling mutations of `fresh_run_node_ids_by_workspace_id`
and per-record `stale` flags after all consumers use `NodeSolutionFact`. The shell
may retain settled output values for bounded display, keyed by record/solution ID,
without owning freshness.

### Viewer and live-resource scoping

Prepared viewer invalidation has one committed path:

- the execution client publishes `viewer_invalidation_committed` only after the
  participant-local parent/worker transaction commits;
- `ViewerSessionBridge.adopt_committed_invalidation(...)` is the sole partial-run
  bridge projection; `project_all_run_required()` is global-reset-only;
- worker ownership is separate `install_workspace_context(...)` plus snapshot
  validation/adoption; legacy empty-preparation direct runs alone use global
  `invalidate_workspace(...)`;
- `worker_runner.py` derives exact recomputed viewer IDs and never performs blanket
  invalidation for prepared partial/reuse-valid runs.

Filtering alone is insufficient for in-flight requests. The bridge, execution
client, and worker viewer service maintain a monotonic per-workspace/per-node viewer
invalidation epoch. Every open/update/close/materialize/query request captures the epoch;
every response carries it. Scoped invalidation increments only affected nodes,
retires their pending requests, and rejects any later response from an older epoch.
True global resets advance the workspace epoch and retire all pending requests.

Reused viewer records remain session-only while they contain live handles. Worker
reset, runtime/registry generation replacement, project replacement, backend
change, or handle-generation mismatch invalidates them globally and fails closed.

Primary acceptance scenario:

1. Branch A completes `CAD Import -> Model Viewer`.
2. Model Viewer is open/ready and has a live transport.
3. Disconnected branch B changes an unrelated toggle.
4. Invalidation returns only B and its enabled downstream closure.
5. Auto dispatch contains no recompute decision for branch A.
6. No viewer run-required projection or worker transport release occurs for A.
7. Viewer remains `phase == "open"`, `live_open_status == "ready"`, and has no
   rerun blocker before, during, and after B settles.
8. A deliberately delayed old open/materialize response cannot restore a viewer
   after a same-node invalidation epoch advances.

### Durable repository and artifact lifecycle

Use this current-schema sidecar layout:

```text
<project-stem>.data/solutions/v1/
  generations/<generation-id>/manifest-set.json
  generations/<generation-id>/nodes/<workspace-key>/<node-key>.json
  records/sha256/<first-two>/<record-digest>.json
  blobs/sha256/<first-two>/<sha256>
```

Path keys are full lowercase SHA-256 digests; untrusted logical IDs never appear in
paths:

```text
workspace_key =
  SHA256("corex-solution-workspace-key-v1\0" + UTF8(workspace_id))

node_key =
  SHA256("corex-solution-node-key-v1\0" + UTF8(node_id))
```

Generation directories, node manifests, records, and blobs are immutable after
publication. Each durable output uses the existing data-type catalog codec and a
bounded descriptor; never use pickle or assembly-qualified runtime-object
serialization.

Strict canonical JSON schema 1 is:

```text
manifest-set.json
  schema_version = 1
  generation_id: 32 lowercase hex
  solution_namespace_id: bounded string
  node_manifests: sorted unique by (workspace_key, node_key)
    workspace_key: 64 lowercase hex
    node_key: 64 lowercase hex
    relative_path: nodes/<workspace_key>/<node_key>.json
    node_manifest_digest: 64 lowercase hex

node manifest
  schema_version = 1
  solution_namespace_id: bounded string
  workspace_id: bounded logical ID
  node_id: bounded logical ID
  workspace_key: exact derived key
  node_key: exact derived key
  records: sorted unique by solution_key
    solution_key: 64 lowercase hex
    record_digest: 64 lowercase hex

record file
  exact canonical JSON from strict SolutionRecord.to_payload()

result blob
  schema_version = 1
  record_id: opaque bounded ID
  solution_key: 64 lowercase hex
  result_digest: 64 lowercase hex
  settlement_status: completed | empty
  outputs: sorted unique by port_key
    port_key: bounded port key
    result: strict SettledPortResult payload
```

`record_id` is an opaque non-control-character ID capped at 128 UTF-8 bytes. It is
never a path and need not equal a digest. `record_digest` is SHA-256 of canonical
record JSON bytes and is the filename/manifest value; it is not embedded in the
record. For T07 value records, `payload_locator.reference_id` equals the result-
blob digest and `blob_digests` contains exactly that digest. Outputless/wholly empty
records retain `payload_locator=None`; managed artifacts remain managed references
instead of duplicated solution blobs.

All JSON rejects unknown fields, duplicate keys/entries, booleans as integers,
invalid UTF-8, NaN/infinity, noncanonical bytes, and count/depth/byte overflow.

Repository ceilings are:

```text
MAX_DURABLE_JSON_DEPTH = 32
MAX_DURABLE_LOGICAL_ID_UTF8_BYTES = 4_096
MAX_DURABLE_RECORD_ID_UTF8_BYTES = 128
MAX_DURABLE_DIAGNOSTIC_UTF8_BYTES = 512

MAX_DURABLE_MANIFEST_SET_BYTES = 67_108_864
MAX_DURABLE_NODE_MANIFEST_BYTES = 1_048_576
MAX_DURABLE_RECORD_JSON_BYTES = 8_388_608
MAX_DURABLE_RESULT_BLOB_BYTES = 67_108_864

MAX_DURABLE_NODE_MANIFESTS_PER_GENERATION = 100_000
MAX_DURABLE_RECORDS_PER_NODE = 256
MAX_DURABLE_RECORDS_PER_GENERATION = 1_000_000
MAX_DURABLE_NODE_MANIFEST_BYTES_PER_GENERATION = 268_435_456
MAX_DURABLE_REFERENCED_BYTES_PER_GENERATION = 4_294_967_296
MAX_DURABLE_BLOBS_PER_RECORD = 1
```

Limits apply before decode and after canonical re-encoding. Per-node and per-
generation record ceilings both apply. The 4-GiB generation ceiling includes
referenced record JSON and result blobs; each result blob independently fits 64
MiB. Prepared durable hits still share the existing 64-MiB accepted-output
aggregate, and every inline value remains capped at 1 MiB. Capacity excess rejects
durable stage/generation publication without truncation or partial publication.

Safe immutable I/O validates containment and every existing component for symlink/
junction/reparse state before and after directory creation, read, write, publish,
and prune. Reads compare file identity, size, and metadata before/after. Stage with
an unpredictable `mkstemp` file in the destination directory, canonical bytes, and
flush/fsync. Publish immutable blob, record, node-manifest, and manifest-set targets
with an atomic no-clobber operation. If the final target already exists, verify its
raw bytes and digest and reuse it; otherwise atomically install the completed same-
directory temporary file only if the target remains absent. A race that creates the
target is resolved by validating the winner and discarding the temporary file.
Never call a replacing/overwriting primitive on an immutable content-addressed
target. T08 may atomically publish `.cxproj`; only `replace_current` may replace an
existing target. Publication order is result
blob, record, node manifests, then `manifest-set.json`; a valid manifest set marks
a complete generation.

The `.cxproj` document is the sole commit point. Current-schema project metadata
contains only:

```text
solution_store
  schema_version = 1
  solution_namespace_id
  active_generation_id
  active_manifest_set_digest
```

The manifest-set digest covers every node-manifest path/digest in the generation.
T07 binds only an already committed pointer, lazily loads it, stages immutable
content, builds/validates candidate generations, enumerates reachability, and
provides safe prune primitives tested in isolation. T07 does not mutate metadata,
write/replace `.cxproj`, report Save/Save As success, switch a Save As binding, or
invoke lifecycle pruning.

T08 alone coordinates one guarded copy-on-write project transaction.

`ProjectDocumentIOService` owns one non-reentrant, nonblocking save guard shared by
Save and Save As. A second Save/Save As returns `save_in_progress`; New/Open/import
replacement is rejected while the guard is active. Ordinary authoring edits remain
unlocked during I/O.

After view/script-editor synchronization, capture:

```text
ProjectSaveToken
  save_id
  project_object_identity
  project_id
  normalized_source_path
  project_document_epoch
  persistent_document_fingerprint
  solution_snapshot_token
```

Immediately before project-file publication, recheck object identity, project ID,
source path, document epoch, an independently rebuilt persistent-document
fingerprint, and runtime solution token. A mismatch returns `save_source_changed`
without commit/clean-state mutation. Repeat after disk commit before candidate
adoption; mismatch becomes `save_committed_not_adopted_source_changed`.

The exact transaction is:

1. Resolve mode: first Save is `create_new`; normal Save at the bound path is
   `replace_current`; distinct Save As is self-contained `create_new`.
2. Capture/export the project-solution snapshot and finish `ProjectSaveToken`.
3. Preflight current project/final persistent document, source artifact integrity,
   image markers, destination parent/target/sidecar policy, containment/reparse
   state, and conservative free space including `snapshot.estimated_copy_bytes`.
4. Build candidate metadata/property rewrites without changing live metadata,
   properties, path, dirty flags, runtime binding, Recent Projects, or autosave.
5. Stage project artifacts copy-on-write using document references union
   `snapshot.required_managed_artifact_ids`. Legacy workspace-path migration is
   metadata rewrite plus copy, never a source move. Referenced staged data is
   copied to a managed target; source staged/unreferenced data remains until after
   commit. Reuse an existing managed target only after exact content-integrity
   equality; differing content gets a deterministic full-SHA-256-suffixed target.
   Immutable targets are never overwritten/deleted.
6. Stage/build/validate the destination solution generation against the completed
   destination artifact context. This publishes immutable candidate content and
   returns `ProjectSolutionSaveResult` only; it does not open or retain a backend.
   The sole retained candidate is created by the fresh postcommit
   `prepare_project_solution_adoption()` reopen.
7. Write artifact metadata and the exact four-field `metadata.solution_store`
   pointer only into the candidate. Rewrite `temp://` only there; live values stay
   unchanged.
8. Stage image blobs copy-on-write. Reuse an existing digest target only when
   bounded raw bytes match; differing bytes return `save_image_digest_conflict`.
   No image is pruned before commit.
9. Validate the final candidate, encode canonical bytes, write an unpredictable
   same-directory `.cxproj` temporary, flush, and fsync.
10. Recheck source token, destination identities/reparse state, and free-space
    floor.
11. Publish `.cxproj`, immediately record `ProjectDocumentPublicationResult`, and
    set committed state before any verification. `replace_current` uses `os.replace`;
    `create_new` uses atomic create-if-absent and never a replacing primitive.
12. For published/uncertain, call `verify_committed_document()`, decode/hydrate the
    current serializer output, verify project ID/schema/pointer/no staged/temp refs/
    every image, and reconstruct the destination artifact store.
13. Build postcommit artifact verification set as reopened document managed refs
    union `solution_snapshot.required_managed_artifact_ids`. Require exact equality
    with `artifact_stage.expected_integrity_facts`; each fact verifies ID, selected
    destination relative path, file/directory kind, size, SHA-256, containment,
    non-reparse state, and current content integrity.
14. Call `CorexRuntime.prepare_project_solution_adoption(...)` to freshly reopen the
    committed pointer and fully validate generation/records/blobs/values/managed
    artifacts against the reopened destination store; retain the pending candidate.
15. Perform the second document-token check after all reopen/artifact/image/solution
    I/O. No blocking I/O, nested event loop, or callback may occur between this
    check, backend swap, and live adoption. On mismatch, close/cancel the pending
    candidate and retain source binding/state.
16. `adopt_project_solution_save(...)` performs only token/snapshot/namespace/result
    equality checks and the in-memory backend swap.
17. Apply the precomputed no-I/O live adoption block: properties, metadata, artifact-
    store object, path, timestamp, clean flags, adopted runtime-document fingerprint,
    and autosave snapshot replacement facts.
18. After success only, run bounded best-effort artifact/image/solution cleanup.
    The first pass protects previous/new generation ID+manifest-digest pairs and
    reachability; a later successful save or same-process deferred retry may use
    active-only protection.

The save guard may span filesystem work; no runtime/store lock does. Core adoption
and bounded cleanup finish before the guard releases. Only then may session
persistence, tab/recent notifications, metadata signals, dialogs, error
presentation, or user callbacks run. Backend close and diagnostics also occur
outside runtime/store locks.

`create_new` uses the repository's existing same-directory no-clobber semantics:
completed/fsynced temp, create-only install, racing target untouched, then installed-
byte verification. It never falls back to `os.replace`.

Destination policy is exact:

- Parent already exists, is a real directory, and has no reparse component.
- Normal Save target equals the case-normalized current path and is a regular,
  non-reparse file. Its sibling sidecar is an existing safe real directory or a
  safe create target.
- First Save/distinct Save As require neither target `.cxproj` nor sibling
  `<stem>.data` existed at initial preflight; target remains absent until create-new
  publication.
- Destination is outside source sidecar/staging/candidate-managed roots.
- Required free bytes conservatively sum candidate project/artifact/image/solution
  bytes plus `SAVE_FREE_SPACE_RESERVE_BYTES = 16_777_216`.
- Target, parent, sidecar identity, and referenced paths are rechecked before commit.

`ProjectArtifactStore.stage_project_save(...)` replaces production Save/Save As use
of `migrate_workspace_artifact_folders()` and `commit_referenced_artifacts()`. It
returns frozen candidate metadata/ref replacements, previous/new reachability,
promoted staged IDs, safe cleanup candidates, and byte estimate. It performs no
source move/delete or immutable overwrite.

```text
ProjectArtifactIntegrityFact
  artifact_id
  relative_path
  kind: file | directory
  size_bytes
  sha256

ProjectArtifactSaveStage
  ...
  expected_integrity_facts:
    sorted unique tuple[ProjectArtifactIntegrityFact, ...]
```

Facts cover document-managed plus solution-required IDs after destination path
selection/copying.

`image_blobs.stage_project_images(...)` returns the prepared marker document plus
previous/new digest reachability and cleanup candidates. `_write_blob()` never
replaces a digest target.

Artifact and image cleanup use the same 100,000-entry scan and 10,000-candidate
ceilings as solution GC. Artifact cleanup considers only exact paths from validated
previous/candidate metadata. Image cleanup considers only exact
`[0-9a-f]{64}.png` children under the validated image root. No save cleanup performs
broad recursive deletion.

```text
ProjectArtifactGcResult
  candidate_relative_paths
  removed_relative_paths
  remaining_relative_paths
  has_more

ProjectImageGcResult
  candidate_digests
  removed_digests
  remaining_digests
  has_more
```

Tuples are sorted/unique/bounded; removed and remaining are disjoint candidate
subsets. `has_more=true` when remaining is nonempty or scan/batch is incomplete.
Deferred candidates are never popped before collection: success-empty removes the
entry, partial/protected/locked replaces it with remaining work, and exception
retains the original tuple. New candidates merge before first attempt. Failed or
committed-not-adopted transaction candidates remain for later same-target save.

When `orphan_scan_complete=false`, solution GC performs a new bounded scan of
current filesystem state after validating active/extra protected generation ID+
digest pairs. It merges/deduplicates supplied/new candidates and selects a bounded
batch. `has_more` stays true for incomplete scan, unselected/partial candidates, or
I/O failure with unresolved work. The runtime save context remains until a complete
scan returns `has_more=false`.

`serializer.py` owns publication state explicitly:

```text
ProjectDocumentPublicationState =
  not_published | published | publication_uncertain

ProjectDocumentPublicationResult
  state: ProjectDocumentPublicationState
  reason_code:
    project_document_not_published |
    project_document_published |
    project_document_publication_uncertain

  committed = state != not_published

stage_document(path, document, commit_mode) -> StagedProjectDocument
commit_staged_document(stage) -> ProjectDocumentPublicationResult
verify_committed_document(stage) -> None
discard_staged_document(stage) -> None
```

`commit_mode` is `replace_current | create_new`. `StagedProjectDocument` owns its
temporary path, canonical-byte SHA-256, prepared image-marker document, prior/new
image digests, and image cleanup candidates. Document I/O no longer calls
`save_document()` as the project transaction.

`commit_staged_document()` validates the temporary before the atomic operation but
performs no post-publication verification. It captures exact pre-attempt target
identity, executes replace-current/create-only, and catches every post-attempt
exception. Classification is conservative:

- create-new target still absent after failure -> `not_published`;
- replace-current target provably retains exact prior identity/bytes ->
  `not_published`;
- target appeared, identity changed, or canonical bytes are installed ->
  `published`;
- target cannot be read or proven unchanged -> `publication_uncertain`.

Published/uncertain are committed. Document I/O assigns committed state immediately
from the result before `verify_committed_document()`. A not-published result maps to
commit failed or create-new destination exists; any later exception is committed-
not-adopted. `verify_committed_document()` requires exact canonical bytes/SHA-256.
`save_document()` uses the same publish/result/verify order and performs no cleanup
when committed verification fails.

Each publication state requires its identically named reason code; cross-pairs are
invalid. `committed` is exactly false for `not_published` and true for `published`
or `publication_uncertain`.

No artifact/image/solution rollback occurs after a `published` or
`publication_uncertain` atomic attempt. After verified publication, the candidate
disk project is authoritative and self-contained. After an uncertain attempt whose
verification fails, disk may contain the prior or candidate complete atomic file;
the window retains source binding/live metadata/properties/path/dirty state/Recent
Projects/autosave state, performs no pruning, and reports
`committed_not_adopted`. For normal Save, the retained live path is already the
attempted target but stays dirty until later successful adoption.

Crash semantics:

- before the atomic publication attempt: prior commit is authoritative;
- after verified publication: the new project is authoritative and complete;
- after a publication-uncertain attempt but before verification: disk may contain
  the prior or candidate atomic file; treat the operation as committed for no-
  rollback/no-prune purposes, retain live source state, and let normal restart
  validation determine which complete file is present;
- GC failure: save succeeds and safe orphans remain.

First Save persists the runtime namespace, including the random unsaved namespace,
and writes a valid generation even when empty. Normal Save preserves namespace and
merges active generation/new durable-eligible records. Save As preserves logical
project/workspace/node/artifact IDs, namespace, solution keys/result identities,
and image digests; only destination-local descriptors outside keys change.

Solution export excludes session/live handles, callbacks/native objects,
credentials/secrets/protected values, Trigger session publications, private/
absolute/staging paths, raw `temp://`, and values rejected by T07. External authored
links remain external and are outside the self-contained guarantee. Unsupported/
corrupt prior solution metadata stays opaque until save and is never cache input;
the committed candidate replaces it with a fresh schema-1 pointer from validated
records.

`document_io_service.py` adds internal:

```text
ProjectSaveResult
  status: cancelled | saved | failed | committed_not_adopted
  reason_code
  target_path
```

Reason codes are locked:

```text
save_cancelled
save_succeeded
save_in_progress
save_destination_invalid
save_destination_exists
save_destination_sidecar_exists
save_destination_unsafe
save_destination_overlaps_source
save_destination_space_insufficient
save_source_changed
save_document_invalid
save_artifact_stage_failed
save_solution_stage_failed
save_image_digest_conflict
save_project_stage_failed
save_project_commit_failed
save_committed_not_adopted_source_changed
save_committed_not_adopted_reopen_failed
save_committed_not_adopted_verification_failed
save_committed_not_adopted_binding_failed
```

Failure matrix:

| Injection | Required outcome |
| --- | --- |
| Reentrant Save/Save As | `failed/save_in_progress`; no mutation |
| Prompt/path/document/source preflight | cancelled/failed; zero writes |
| Artifact/image staging | prior commits valid; COW orphans allowed |
| Solution export/build/validation | prior commits valid; immutable orphans allowed |
| `.cxproj` temp write/fsync | prior commit valid; temp removed |
| Precommit source-token drift | `failed/save_source_changed`; no commit |
| Normal replace failure with target proven exactly unchanged | `failed/save_project_commit_failed`; prior `.cxproj` authoritative |
| Atomic helper installs then raises, target changes, or outcome cannot be proven unchanged | publication is `published` or `publication_uncertain`; committed flag set immediately; later failure is `committed_not_adopted` |
| Create-new race | `failed/save_destination_exists`; racing target untouched |
| Crash after verified publication | candidate disk project authoritative/complete |
| Crash after publication-uncertain attempt before verification | disk contains either prior or candidate complete atomic file; no live adoption or pruning |
| Reopen/artifact/image/solution failure | `committed_not_adopted`; source live state/binding retained; no prune |
| Candidate bind/token/namespace failure | same; candidate closed |
| Postcommit source-token drift | `save_committed_not_adopted_source_changed` |
| Recent/autosave/session/signal failure | core save succeeds; bounded notification only |
| GC scan/delete failure | save succeeds; candidates retained |

Autosave continues serializing the runtime document only. It never stages sidecars,
builds generations, or writes a candidate pointer. Live metadata stays unchanged
until adoption, so autosave during staging retains the last committed pointer and
precommit fingerprint catches authored changes. Successful adoption discards the
prior autosave snapshot and seeds the adopted fingerprint. `committed_not_adopted`
changes no autosave fingerprint/recovery snapshot/recent path/source path/live
pointer/dirty flag. `session_lifecycle_service.py` requires no production edit.

Forced recomputation under an existing `solution_key` calculates the canonical
`result_digest` before publication. An identical digest retains the existing
immutable record (updating only mutable node fact/history projections). A different
digest is a nondeterminism conflict: report it, quarantine no new current record,
and never overwrite the established record.

Existing project-schema migration remains unchanged. There is no migration or
compatibility reader for nested `metadata.solution_store`. Absent metadata opens
authored data session-only with `durable_session_only_metadata_absent`. Present
metadata must contain exactly `schema_version`, `solution_namespace_id`,
`active_generation_id`, and `active_manifest_set_digest`. Malformed fields,
unknown schema, invalid pointer grammar, missing/corrupt manifest, unsafe path, or
I/O failure preserve the authored graph and original metadata, install no durable
record/fact/index, and open session-only with at most one sanitized 512-byte
regeneration diagnostic per project install.

Deterministic repository reasons are locked:

```text
bind:
  durable_bound_active
  durable_session_only_metadata_absent
  durable_session_only_factory_unavailable
  durable_session_only_metadata_invalid
  durable_session_only_schema_unsupported
  durable_session_only_pointer_invalid
  durable_session_only_manifest_missing
  durable_session_only_manifest_oversized
  durable_session_only_manifest_invalid
  durable_session_only_manifest_digest_mismatch
  durable_session_only_path_unsafe
  durable_session_only_reparse_rejected
  durable_session_only_io_error

lookup/load:
  durable_hit
  durable_not_bound
  durable_key_absent
  durable_node_manifest_missing
  durable_node_manifest_oversized
  durable_node_manifest_invalid
  durable_node_manifest_digest_mismatch
  durable_record_missing
  durable_record_oversized
  durable_record_invalid
  durable_record_digest_mismatch
  durable_record_binding_mismatch
  durable_payload_missing
  durable_payload_oversized
  durable_payload_invalid
  durable_payload_digest_mismatch
  durable_payload_binding_mismatch
  durable_value_ineligible
  durable_artifact_invalid
  durable_path_unsafe
  durable_reparse_rejected
  durable_io_error

stage/generation:
  durable_stage_published
  durable_stage_existing_identical
  durable_stage_ineligible
  durable_stage_capacity_exceeded
  durable_stage_path_unsafe
  durable_stage_reparse_rejected
  durable_stage_write_failed
  durable_nondeterminism_conflict
  durable_generation_built
  durable_generation_valid
  durable_generation_capacity_exceeded
  durable_generation_invalid
  durable_generation_digest_mismatch
  durable_generation_write_failed
```

Prepared decisions continue mapping unbound/absent key to `no_reusable_record` and
located-invalid record/payload/artifact to `accepted_output_invalid`, while bounded
diagnostics retain the durable reason. Nondeterminism retains the existing
`nondeterministic_solution_result` fact/event behavior.

### Relationship to explicit value internalization

Solution snapshots remain a derived performance cache. They do not sever graph
dependencies and do not become authored node properties.

Explicit value internalization/data-container behavior is a separate future
feature. If implemented later, input ports—not the solution store—should own the
authored captured-value reference, wire attachment should clear that authored
capture, and undo/redo should cover the graph mutation. This plan does not add
container nodes or internalization commands.

## Public Interface Changes

### Headless runtime

- Add `CorexRuntime.prepare_execution(request) -> PreparedExecution`.
- Add `CorexRuntime.dispatch_prepared(prepared) -> str`.
- Add `CorexRuntime.invalidate_solution(...) -> InvalidationResult`.
- Keep `CorexRuntime.start(request: ExecutionRequest) -> str` as the only
  convenience entrypoint; it is exactly prepare followed by dispatch.
- Remove `CorexRuntime.start_run(project_path, workspace_id, ...)` and update every
  call site to construct `ExecutionRequest`; do not keep an alias. This removal
  occurs in T05 after T04 makes prepared dispatch executable.
- Add `bind_project_solution_store(...)` and
  `detach_project_solution_store(project_id, reason)` with the lifecycle semantics
  defined above.
- Extend `ExecutionRequest` with `recompute_mode: RecomputeMode = "reuse_valid"`.
- Add read-only solution-state queries:
  - `solution_facts(project_id, workspace_id) -> tuple[NodeSolutionFact, ...]`;
    unknown project/workspace returns an empty tuple;
  - `expired_node_ids(project_id, workspace_id) -> tuple[str, ...]`; unknown
    project/workspace returns an empty tuple, sorted by execution-plan order;
  - `solution_record(record_id) -> SolutionRecord | None`; unknown ID returns
    `None`.
- `InvalidationResult` has the exact fields listed in Canonical state model; an
  unknown project/workspace or malformed root raises `ValueError` before mutation.
- Add runtime-local strict `solution_state_changed` events after locks are released:
  `{project_id, workspace_id, solution_revision, expired_node_ids,
  removed_node_ids, reason_code}`. Adapters bound counts/types and reject unknown or
  malformed fields. This notifies shell/QML of registry/generation/project resets
  without creating another settlement stream.
- Add `ExecutionBackendClient.execution_generation_snapshot()` and a
  generation-aware subscription used by `CorexRuntime`; forwarded events retain
  backend/generation/environment metadata.

### Worker protocol

- Extend `StartRunCommand` with immutable `reuse|execute` prepared decisions,
  `accepted_output_payloads`, and these non-duplicated preparation facts:
  `preparation_id`, `solution_namespace_id`, execution-affecting workspace revision,
  dispatch runtime generation, runtime-snapshot/plan/workflow-interface/environment
  digests, Trigger publication generations, node decisions, and accepted payloads.
- Empty `preparation_id` is the explicit legacy shell form and requires every
  prepared-only field to be empty/default. Non-empty ID requires the complete
  prepared field set. Session payload generation equals the command generation;
  durable payloads have no runtime generation.
- Add run-carried viewer invalidation synchronization:
  `viewer_invalidation_node_ids: tuple[str, ...] | None`,
  `viewer_workspace_invalidation_epoch`, and sorted unique
  `viewer_node_invalidation_epochs`. Prepared runs carry the exact execute-viewer
  filter; legacy runs carry `None`. Client and worker validate the same None/empty/
  exact semantics and epoch snapshot before service cleanup.
- Add `RunPreflightAcceptedEvent` with run ID, preparation ID, viewer reservation
  ID, and viewer epoch-snapshot digest. It is the first run-scoped event and the
  client commit boundary; preflight failure emits no acceptance event.
- Add `CommitRunPreflightCommand` and `CancelRunPreflightCommand`, each bound to the
  run/reservation/snapshot digest. The worker executes viewer cleanup/node work only
  after a matching commit; cancel/timeout before commit leaves service state
  unchanged.
- Extend `NodeSettledEvent` with disposition, reason, solution key, record ID, and
  residency.
- Settlement combinations are strict:
  - `reused`: completed/empty with record ID and residency;
  - `recomputed`: completed/empty/failed without record ID/residency;
  - `skipped`: empty without record ID/residency;
  - `blocked`: blocked without record ID/residency;
  - legacy: empty solution key, reason `legacy_direct_run`, no record/residency.
- Do not add a second settlement event family.

### Node execution contracts

- Add `solution_reuse_scope` to the internal node execution specification.
- Add internal `SolutionProvenanceInputSpec` declarations for accepted file and
  directory readers.
- Add a content-based `implementation_digest` contract.
- Reject missing/invalid declarations at registry validation for nodes opting into
  `session` or `durable` reuse.
- Add `SolutionRecord.reuse_eligible`; `never` rows publish observation records
  with `false` but never enter the reuse index.

### Viewer invalidation

- Add optional exact `node_ids` filters to bridge/service workspace invalidators.
- `None` means a true workspace-wide reset; an empty set means invalidate none.
- Add `workspace_invalidation_epoch` and `node_invalidation_epoch` to every viewer
  command/event—including close—and pending-request registry; older-epoch commands
  and responses are ignored before any signal/state mutation. Newer epochs may
  synchronize a recycled worker through scoped cleanup.
- Add explicit forwarding APIs:
  - `CorexRuntime.query_viewer_session(workspace_id, node_id, session_id, *,
    run_id="", backend_id="", query_type, payload=None, options=None) -> str`;
  - `ExecutionBackendClient.query_viewer_session(...) -> str` with the same
    signature; unresolved owner returns `""`;
  - `CorexRuntime.invalidate_viewer_requests(workspace_id: str,
    node_ids: Iterable[str] | None) -> int`;
  - `ExecutionBackendClient.invalidate_viewer_requests(...) -> int` with the same
    signature. The count is unique pending request IDs retired; routing/session map
    cleanup is not double-counted. String/bytes `node_ids` raises `TypeError`,
    `None` is global, and empty returns `0` with no epoch/state change.
- Add internal typed reservation APIs on `ExecutionBackendClient`:
  `reserve_viewer_invalidation(...) -> ViewerInvalidationReservation`,
  `commit_viewer_invalidation(reservation)`, and
  `cancel_viewer_invalidation(reservation)`. Reservations are single-use and bound
  to route/workspace/filter/generation. The committed snapshot is delivered once by
  `viewer_invalidation_committed`; there is no retained per-run query API.

### Future UI transport, without styling

- Add `ExecutionStateProps.node_solution_freshness_lookup`.
- Add `GraphCanvasExecutionFacts.nodeSolutionFreshnessLookup`.
- Values are `current` or `expired`; a missing node ID means `never`.
- Do not add node colors, badges, stripes, tooltips, animations, or actions.

### Removed internal contracts

- Remove shell scheduling authority from `fresh_run_node_ids_by_workspace_id`.
- Remove mutable per-output-record `stale`/`stale_reason` as the freshness source.
- Remove blanket viewer invalidation on every rerun.
- Remove worker-private `ExecutionPlan` ownership.
- Remove duplicate direct-run call paths that bypass `CorexRuntime` preparation.

## Execution Tasks

### T01 Define solution contracts and move the shared execution plan

- Goal: Establish one dependency-light solution contract and one shared
  `ExecutionPlan` used by preparation and worker validation.
- Preconditions: Current `main`; approved plan; implementation sub-agent has read
  the execution subsystem and requirements `REQ-EXEC-015`/`017`.
- Conservative write scope:
  - `ea_node_editor/runtime_contracts/settled_results.py` (new)
  - `ea_node_editor/runtime_contracts/solution_records.py` (new)
  - `ea_node_editor/runtime_contracts/__init__.py`
  - `ea_node_editor/execution/prepared_execution.py` (new)
  - `ea_node_editor/execution/execution_plan.py` (new)
  - `ea_node_editor/execution/protocol.py`
  - `ea_node_editor/execution/worker_runtime.py`
  - `ea_node_editor/execution/worker_runner.py`
  - exact settlement import consumers identified by the accepted T01 explorer
  - `tests/test_solution_records.py` (new)
  - `tests/test_execution_plan.py` (new)
  - `tests/test_execution_worker.py`
  - `tests/test_execution_protocol.py`
  - `tests/test_architecture_boundaries.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/supporting_runtime_assets.md`
  - regenerated `docs/agent_route_index.md`, `docs/agent_route_index.json`, and
    `docs/source_test_file_index.md`
- Deliverables:
  - enums/DTOs listed in Canonical state model;
  - shared settlement ownership moved without a compatibility re-export;
  - structural ownership proof confirms the settlement classes are defined only in
    `runtime_contracts/settled_results.py`, are unavailable from
    `execution.protocol`, and no live source/test imports them from the old owner;
  - strict `to_payload`/`from_payload` adapters with the approved
    count/depth/byte/null/type limits;
  - `ExecutionPlan` moved without behavior drift;
  - deterministic versioned canonical-JSON plan fingerprint over workspace ID,
    effective targets/Trigger mode, scheduled IDs/order, execution-relevant ports,
    enabled edge endpoints/input order, and validated hidden-ordering pairs;
  - fingerprint excludes titles, coordinates, collapse/style/labels,
    selection/view state, and disabled edges;
  - current Trigger, disabled-edge, hidden-ordering, dynamic-port, and target
    behavior preserved.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_records.py tests/test_execution_plan.py -q`
  - `./venv/Scripts/python.exe -m pytest tests/test_execution_protocol.py -q`
  - `./venv/Scripts/python.exe -m pytest tests/test_dataflow_execution_runtime.py -q`
  - `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py::GraphArchitectureBoundaryTests::test_runtime_contracts_do_not_import_execution_implementation -q`
  - focused import-smoke coverage for `ui/support/port_flow_state.py`,
    `ui_qml/graph_canvas_state/execution_state_props.py`, shell run state/controller,
    and protocol/client/worker consumers after the ownership move;
  - existing worker-runtime target/ordering selectors;
  - generate source/test and agent-route indexes, then run
    `./venv/Scripts/python.exe ./scripts/check_agent_maps.py`;
  - `git diff --check`.
- Non-goals: reuse decisions, persistence, viewer changes, QML facts.
- Packetization notes: `P01`; mandatory foundation. One pre-implementation explorer,
  one implementation sub-agent, and one separate reviewer are required.

### T02 Implement canonical solution identity and reuse eligibility

- Goal: Compute fail-closed `solution_key` values and classify every executable
  node's maximum reuse residency.
- Preconditions: T01 accepted.
- Conservative write scope:
  - `ea_node_editor/execution/solution_identity.py` (new)
  - `ea_node_editor/execution/execution_plan.py`
  - `ea_node_editor/nodes/registry.py`
  - `ea_node_editor/nodes/node_specs.py`
  - `ea_node_editor/nodes/decorators.py`
  - `ea_node_editor/nodes/plugin_declaration.py`
  - `ea_node_editor/nodes/builtins/icon_catalog.py`
  - `ea_node_editor/nodes/builtin_functions/core_value.py`
  - `ea_node_editor/nodes/builtin_functions/data_control.py`
  - `ea_node_editor/nodes/builtin_functions/engineering_fem.py`
  - `ea_node_editor/nodes/builtin_functions/engineering_geometry.py`
  - `ea_node_editor/nodes/builtin_functions/engineering_imports.py`
  - `ea_node_editor/nodes/builtin_functions/engineering_viewer.py`
  - `ea_node_editor/nodes/builtin_functions/integrations_file_io.py`
  - `ea_node_editor/nodes/builtin_functions/integrations_spreadsheet.py`
  - `ea_node_editor/nodes/builtin_functions/plot_signal.py`
  - `ea_node_editor/nodes/builtin_functions/reporting.py`
  - `ea_node_editor/nodes/builtin_functions/rich_values.py`
  - `ea_node_editor/nodes/builtin_functions/spatial.py`
  - `ea_node_editor/nodes/builtin_functions/unit_math.py`
  - `ea_node_editor/nodes/builtin_functions/viewer_viewport.py`
  - `ea_node_editor/addons/tabular_data/function_nodes.py`
  - `ea_node_editor/common/payload_tools.py` only if existing canonical helpers are
    insufficient and can remain dependency-light
  - `docs/specs/perf/COREX_SOLUTION_REUSE_CLASSIFICATION.md` (new)
  - `.gitignore` exact negation for
    `docs/specs/perf/COREX_SOLUTION_REUSE_CLASSIFICATION.md` only
  - `tests/repo_owned_catalog_fixture.py`
  - `tests/test_solution_identity.py` (new)
  - `tests/test_registry_validation.py`
  - `tests/test_decorator_sdk.py`
  - `tests/test_plugin_declaration.py`
  - `tests/test_builtin_function_infrastructure.py`
  - `tests/test_corex_contract_catalog.py`
  - relevant built-in/integration/tabular migration tests
  - `docs/agent_maps/subsystems/nodes_registry_builtins.md`
  - `docs/agent_maps/subsystems/execution.md`
  - regenerated route/source indexes
- Deliverables:
  - callback-free canonical tagged encoder;
  - executable node projection excluding UI-only fields;
  - normalized execution-facing workflow-interface revision/digest required by
    durable identity;
  - public/untrusted rows hard-locked to `never`;
  - trusted factories hard-locked to `never` in T02 until content/toolchain
    identity is available;
  - one cached COREX build digest and one normalized execution-environment digest;
  - read-only `ExecutionPlan.hidden_ordering_pairs` accessor for identity without a
    private-field dependency;
  - upstream/artifact/file/toolchain/backend/implementation identity;
  - `solution_reuse_scope` and content-based implementation digest validation;
  - explicit fail-closed reason codes for ineligible nodes;
  - accepted classification inventory for every executable registry row, including
    the CAD Import/Model Viewer chain.
- Verification:
  - same executable inputs produce the same key across process restarts;
  - UI-only edits do not change a key;
  - execution property, edge enable/order, port modifier, file content, artifact
    digest, implementation, catalog revision, backend, or toolchain changes do;
  - hostile values invoke no callbacks/I/O;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_identity.py tests/test_registry_validation.py tests/test_decorator_sdk.py -q`.
- Non-goals: storing outputs, running reused results, durable files.
- Packetization notes: `P02`; split the node-classification inventory into a
  read-only classification-drafter/reviewer gate before metadata implementation,
  exactly as recorded in the ledger. No metadata edit starts before
  `CLASSIFICATION_ACCEPTED`.

### T03 Add the execution-owned session solution store

- Goal: Add the execution-owned session solution store, preparation, invalidation,
  and generation-safe settlement capture as a dormant production path; sole shell
  freshness/scheduling authority switches only in T05.
- Preconditions: T01-T02 accepted.
- Conservative write scope:
  - `ea_node_editor/execution/solution_store.py` (new)
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/execution/client.py`
  - `ea_node_editor/execution/execution_plan.py`
  - `ea_node_editor/execution/solution_identity.py`
  - `ea_node_editor/runtime_contracts/solution_records.py`
  - `ea_node_editor/nodes/node_specs.py`
  - `ea_node_editor/nodes/registry.py`
  - `ea_node_editor/nodes/bootstrap.py` only if trusted-overlay installation cannot
    remain inside registry construction
  - `ea_node_editor/nodes/solution_provenance.py` (new)
  - `ea_node_editor/ui/shell/composition/controllers.py`
  - `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
  - `tests/test_solution_store_session.py` (new)
  - `tests/test_headless_runtime.py` (new)
  - `tests/test_solution_records.py`
  - `tests/test_execution_client.py`
  - `tests/test_execution_plan.py`
  - `tests/test_solution_identity.py`
  - `tests/test_plugin_runtime_agreement.py`
  - `tests/test_registry_replacement.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `tests/test_registry_validation.py`
  - `tests/test_architecture_boundaries.py`
  - `tests/test_project_session_controller_unit.py`
  - `tests/test_shell_project_session_controller.py`
  - focused reader tests identified by the accepted T03 exploration
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/startup_and_bootstrap.md`
  - `docs/agent_maps/subsystems/supporting_runtime_assets.md`
  - `docs/agent_maps/subsystems/nodes_registry_builtins.md`
  - `docs/agent_maps/subsystems/persistence.md`
  - `docs/agent_maps/subsystems/ui_shell.md`
  - `docs/agent_maps/subsystems/addons.md`
  - `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`
  - `docs/agent_maps/feature_routes/neutral_cad_fe_engineering_viewer.md`
  - `docs/agent_maps/feature_routes/core_integrations_file_process_email_spreadsheet.md`
  - `docs/agent_maps/feature_routes/tabular_data_addon_preview.md`
  - regenerated route/source indexes
- Deliverables:
  - in-memory record backend;
  - immutable in-memory typed-output payload lookup with result digests;
  - `reuse_eligible` observation records for `never` rows without reuse indexing;
  - node facts and monotonic workspace solution revision;
  - saved-project namespace equals `project_id`; stable in-memory namespace for
    unsaved projects;
  - deterministic per-workspace/runtime/preparation retention ceilings, eviction,
    and pin/reservation cleanup on every terminal/reset/replacement/shutdown path;
  - route-specific generation-aware client snapshot/event API and environment
    identity, including cold unavailable behavior;
  - caller-ID run reservation and atomic preparation-consume/run-context registration
    before client start;
  - registry-owned trusted file/directory provenance overlay for accepted session
    readers;
  - bounded heterogeneous concrete output type/carrier descriptors;
  - shared `ExecutionPlan.affected_downstream_closure()` with contributing roots;
  - record publication only after validated terminal settlement;
  - affected-closure invalidation through shared `ExecutionPlan`;
  - execution-affecting workspace revision captured by preparation/dispatch;
  - late-settlement protection by captured solution key/revision;
  - execute-only keys for identity failures;
  - Trigger publication generation reservation/commit/discard;
  - runtime-generation eviction for handle-bearing/session-only records;
  - `prepare_execution()` and single-use `dispatch_prepared()` API;
  - T03 dispatch supports all-`execute` preparations only and rejects any `reuse`
    action with `prepared_reuse_not_supported_until_t04`;
  - existing `start()`/`start_run()` and shell dispatch remain unchanged until
    T04/T05;
  - project replacement/new/open clears the previous session store without adding
    durable binding.
- Verification:
  - current/expired/never transitions;
  - disconnected branches retain current records;
  - changed/downstream closure expires exactly once;
  - Trigger/disabled-edge/hidden-ordering closure and contributing-root matrix;
  - failure/cancel leaves prior record expired and intact;
  - stale late completion cannot restore current;
  - unrelated-branch invalidation does not reject a valid settlement;
  - prepared execution rejects reuse after graph/registry/runtime revision drift;
  - prepare alone does not publish/replace registry generation or alter viewer
    ownership;
  - synchronous settlement/terminal during start sees registered context; failed
    start releases reservation/context/pins;
  - generation replacement evicts all session records/payloads and expires facts;
  - per-workspace and runtime-global record/byte/preparation capacity and eviction;
  - namespace, observation-record, mixed carrier/type descriptor, execute-only key,
    Trigger reservation, and project-replacement tests;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_store_session.py tests/test_headless_runtime.py tests/test_execution_plan.py tests/test_solution_identity.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_execution_client.py tests/test_plugin_runtime_agreement.py tests/test_registry_replacement.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_architecture_boundaries.py tests/test_registry_validation.py tests/test_solution_records.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_project_session_controller_unit.py tests/test_shell_project_session_controller.py -q`;
  - focused engineering/file/spreadsheet/tabular reader suites named by the T03
    explorer.
- Non-goals: worker reuse/output injection, shell/Auto freshness cutover, removal of
  `start_run`, viewer invalidation, durable repository.
- Packetization notes: `P03`; do not merge with T04 because store invariants must be
  reviewed before process-boundary reuse.

### T04 Validate and execute prepared reuse decisions in the worker

- Goal: Prevent unchanged eligible nodes from invoking their implementation while
  preserving the existing settlement stream.
- Preconditions: T01-T03 accepted.
- Conservative write scope:
  - `ea_node_editor/execution/protocol.py`
  - `ea_node_editor/execution/client.py`
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/execution/prepared_execution.py`
  - `ea_node_editor/execution/solution_identity.py`
  - `ea_node_editor/execution/solution_store.py`
  - `ea_node_editor/execution/worker_runner.py`
  - `ea_node_editor/execution/worker_runtime.py`
  - `tests/test_execution_protocol.py`
  - `tests/test_execution_client.py`
  - `tests/test_headless_runtime.py`
  - `tests/test_solution_records.py`
  - `tests/test_solution_identity.py`
  - `tests/test_solution_store_session.py`
  - `tests/test_plugin_runtime_agreement.py`
  - `tests/test_registry_replacement.py`
  - `tests/test_execution_worker.py`
  - `tests/test_dataflow_execution_runtime.py`
  - `docs/agent_maps/subsystems/execution.md`
- Deliverables:
  - prepared decisions encoded on `StartRunCommand`;
  - strictly bounded accepted-output payloads round-trip through protocol adapters
    with node/record/key/status/digest binding;
  - worker reconstruction and plan/solution-key validation;
  - exact scheduled-node/order decision parity and shared per-node key/dependency
    reconstruction;
  - session/durable payload lookup resolves settlement status and typed outputs;
  - reused outputs installed into `NodeExecutor` in `worker_runner.py` before
    dependent execution;
  - reused nodes emit `node_settled` without `node_started`;
  - reused nodes install outputs/add `executed` exactly once in plan order, with
    cancellation polling and preserved ordered fan-in;
  - recomputed settlements publish new immutable records through `CorexRuntime`;
  - force-recompute path;
  - `CorexRuntime.start(ExecutionRequest)` becomes exactly prepare plus executable
    prepared dispatch; legacy `start_run` remains only for shell until T05;
  - `CorexRuntime.run(ExecutionRequest)` subscribes then uses the same
    prepare/dispatch path;
  - `CorexRuntime.start_run(...)` calls a renamed legacy `_start_legacy(...)` path;
    shell/RunController remain untouched in T04;
  - failed/blocked/corrupt/generation-incompatible records rejected.
- Verification:
  - second unchanged Run invokes zero node implementations for reusable nodes;
  - Run Selected reuses current upstream nodes and runs only expired/missing nodes;
  - a diamond graph reuses shared upstream once and preserves input order;
  - outputless completed/empty eligible nodes may reuse;
  - failed/blocked results never reuse;
  - handle generation and artifact integrity fail closed;
  - worker validates every prepared fingerprint, decision/key/dependency tuple,
    payload binding/digest, actual output port/catalog item, artifact, and trusted
    live handle before installing any reused output;
  - any mismatch rejects the whole run, never downgrades reuse to execute;
  - malformed, oversized, mismatched-node/record/key/status/digest/residency/runtime-
    generation accepted-output payloads are rejected before worker output
    installation;
  - protocol dict round-trip preserves valid reused EMPTY/value results and refs;
  - reused settlement events preserve residency; durable payloads reject a runtime
    generation and session payloads reject a missing/stale generation;
  - identical forced recomputation retains the established same-key record;
  - divergent forced recomputation reports nondeterminism and does not overwrite;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_records.py tests/test_solution_identity.py tests/test_solution_store_session.py tests/test_headless_runtime.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_execution_protocol.py tests/test_execution_client.py tests/test_execution_worker.py tests/test_dataflow_execution_runtime.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_plugin_runtime_agreement.py tests/test_registry_replacement.py -q`;
  - `./venv/Scripts/python.exe ./scripts/check_agent_maps.py`;
  - explicit proof that `CorexRuntime.start()` uses executable prepared dispatch,
    while legacy `start_run()` remains shell-only until T05;
  - exact headless proof that `CorexRuntime.run()` subscribes before preparation,
    dispatches the prepared command, captures terminal events, and cannot bypass
    reuse.
- Non-goals: shell/QML behavior, viewer invalidation, durable persistence.
- Packetization notes: `P04`; implementation and reviewer sub-agents must be
  different because this is the trust boundary.

### T05 Cut graph invalidation and Auto/manual scheduling over to CorexRuntime

- Goal: Remove shell cache as freshness/scheduling authority and expose generic
  node freshness for future UI.
- Preconditions: T03-T04 accepted.
- Conservative write scope:
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/execution/solution_store.py`
  - `ea_node_editor/execution/prepared_execution.py`
  - `ea_node_editor/ui/shell/runtime_history.py`
  - `ea_node_editor/ui/shell/controllers/run_controller.py`
  - `ea_node_editor/ui/shell/state.py`
  - `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
  - `ea_node_editor/ui/shell/controllers/workspace_edit_controller.py`
  - `ea_node_editor/ui/shell/window_state/run_and_style_state.py`
  - `ea_node_editor/ui/graph_interactions.py`
  - `ea_node_editor/ui_qml/graph_scene/context.py`
  - `ea_node_editor/ui/support/solution_output_cache.py` (new)
  - `ea_node_editor/ui/support/port_flow_state.py`
  - `ea_node_editor/ui/media_panel_source.py`
  - `ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py`
  - `ea_node_editor/ui_qml/graph_canvas_state/protocols.py`
  - `ea_node_editor/ui_qml/graph_canvas_state_bridge.py`
  - `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml`
  - `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
  - `ea_node_editor/ui_qml/graph_scene/command_bridge.py`
  - `ea_node_editor/ui/shell/presenters/canvas_export_presenter.py`
  - `ea_node_editor/ui/project_review_deck.py`
  - `ea_node_editor/ui/shell/presenters/project_review_deck_presenter.py`
  - `tests/test_run_controller_unit.py`
  - `tests/test_shell_run_controller.py`
  - `tests/test_port_flow_state.py`
  - `tests/test_media_panel_source_resolution.py`
  - `tests/test_data_type_ui_projection.py`
  - `tests/test_graph_scene_presentation_facts.py`
  - `tests/test_content_fullscreen_bridge.py`
  - `tests/test_project_review_deck.py`
  - `tests/test_port_availability.py`
  - `tests/main_window_shell/bridge_support.py`
  - `tests/main_window_shell/view_library_inspector.py`
  - `tests/main_window_shell/bridge_qml_boundaries.py`
  - `tests/main_window_shell/mutation_ui_effects.py`
  - `tests/graph_track_b/qml_preference_rendering_suite.py`
  - `tests/test_headless_runtime.py`
  - `tests/test_execution_client.py`
  - `tests/test_plugin_runtime_agreement.py`
  - `tests/test_registry_replacement.py`
  - `tests/test_solution_store_session.py`
  - `tests/test_solution_records.py`
  - `docs/agent_maps/feature_routes/run_controller_selected_workspace_state.md`
  - `docs/agent_maps/feature_routes/node_execution_visualization.md`
  - `docs/agent_maps/feature_routes/clipboard_undo_redo_mutation_history.md`
  - `docs/agent_maps/feature_routes/media_image_video_pdf_refocus.md`
  - `docs/agent_maps/feature_routes/persistent_node_elapsed_times.md`
  - `docs/agent_maps/feature_routes/port_availability_and_default_values.md`
  - `docs/agent_maps/feature_routes/qml_bridge_wiring.md`
  - `docs/agent_maps/feature_routes/port_availability_and_default_values.md`
  - `docs/agent_maps/feature_routes/graph_scene_payload_and_projection.md`
  - `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`
  - `docs/agent_maps/feature_routes/tabular_data_addon_preview.md`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/ui_shell.md`
  - `docs/agent_maps/subsystems/graph_canvas.md`
  - `docs/agent_maps/subsystems/qml_shell_and_bridges.md`
  - `docs/agent_maps/testing/qml_and_graph_surface_tests.md`
  - regenerated QML/source/route indexes
- Deliverables:
  - rename the history execution classifier/hook away from persistent-elapsed
    terminology, with no compatibility alias;
  - one before/after/registry-aware classifier: cosmetic/passive-only changes do
    not advance execution revision; currently present active roots invalidate;
    removed-only executable changes advance with an empty root tuple; changed edge
    old/new targets are considered;
  - invalidation synchronizes store facts against current full-plan node IDs:
    deleted facts, current pins, and reuse indexes are removed; a session tombstone
    revision remains so undo/re-add cannot accept an old settlement;
    `InvalidationResult.removed_node_ids` drives presentation-cache cleanup;
  - remove `_AUTO_RUN_ACTION_TYPES` and duplicate Auto closure helpers;
  - history hook calls `CorexRuntime.invalidate_solution()` with normalized roots;
  - Auto uses returned affected targets;
  - Manual, Selected, Auto, and Trigger build one `ExecutionRequest` and dispatch
    through prepare/dispatch; remove `CorexRuntime.start_run()` and `_start_legacy()`;
  - Manual targets all active nodes, Selected explicit targets, Auto exact expired
    targets, Trigger retains clicked/capture fields;
  - active-run edits union pending expired targets and schedule one terminal rerun;
    Manual-to-Auto toolbar transition still requests full active-workflow evaluation;
  - pending outcome table:
    - successful `run_completed` drains exactly one unioned Auto target set when
      Auto remains enabled and the workspace is still active;
    - `run_failed`, `run_stopped`, cancellation, fatal/infrastructure/protocol
      failure clear pending targets and never auto-retry;
    - workspace switch/project replacement and Auto-to-Manual/Pause clear pending
      targets for that workspace;
    - Manual, Selected, and Trigger requests during an active run retain the
      existing reject/warn behavior and are not queued;
    - explicit Run/Run Selected that consumes Apply suppresses its duplicate Auto
      invalidation/rerun;
  - `node_solution_freshness_lookup` projects current/expired; absence means never;
  - runtime-local solution-state events notify RunController/QML after registry,
    generation, project, and explicit resets;
  - `SolutionStore.handle_event()` returns an explicit acceptance result with
    accepted record ID, solution key, result digest, and disposition only when that
    exact event became/reused the retained record; rejected/late/nondeterministic/
    capacity/failed events receive no record ID and can never stamp old retained IDs
    onto new outputs;
  - every accepted cached shell event is stamped from that acceptance result with
    record ID, solution key, disposition, typed outputs, and timestamp;
  - lock/event flow is exactly:
    `generation callback -> CorexRuntime store handling/enrichment ->
    ExecutionEventStream -> ShellWindow.execution_event ->
    RunController.handle_execution_event -> commit_node_execution_state_change ->
    node_execution_state_changed -> GraphCanvasStateBridge
    node_execution_state_changed/port_flow_state_changed -> ExecutionStateProps/QML`;
    enriched `node_settled` publishes only after store fact/record update;
    `solution_state_changed` is non-run-scoped;
  - shared retained-record selector chooses only the event matching
    `NodeSolutionFact.retained_record_id`; expired retained records remain
    inspectable/stale, expired-without-record and never expose no cached value;
  - port flow, viewer state, property presentation, Panel, Media, fullscreen, graph commands,
    graph presenter, and Project Review Deck use that selector;
  - exact node-level availability clearing uses invalidation results and prepared
    recompute IDs; late/rejected settlements cannot republish availability;
  - remove mutation-time workspace-wide availability clears from
    `graph_interactions.py` and `workspace_edit_controller.py`; keep workspace clears only
    for true project/workspace replacement;
  - old mutable shell freshness fields/flags and duplicate closure logic removed;
  - keep `fresh_run_node_lookup` only as a derived current-only compatibility fact
    for unchanged visuals, not mutable authority;
  - add generic `GraphCanvasExecutionFacts.nodeSolutionFreshnessLookup` transport
    only; no styling consumer;
  - UI cache bound: maximum two records per node, 4,096 records and 512 MiB
    canonical payload per workspace; retained fact record pinned, oldest unpinned
    evicted deterministically; oversized/unfit payload becomes metadata-only and
    unavailable to previews rather than misrepresented;
  - runtime-global UI cache bound: maximum 16,384 records and 2 GiB canonical
    payload across workspaces; evict oldest unpinned cross-workspace entry by
    observed sequence, workspace ID, node ID, record ID; active retained records are
    pinned and capacity failure degrades the new entry to metadata-only;
  - preserve monotonic session-only run counts in a separate counter instead of
    deriving them from bounded cache length;
  - failed `start_reserved_run` restores pre-dispatch facts; a run that actually
    started and later failed/stopped/cancelled remains expired;
  - `solution_state_changed` payload includes project ID, workspace ID, monotonic
    solution revision, separate expired and removed node IDs, and reason;
    RunController rejects a mismatched project or non-increasing revision;
  - authoring dirty state remains separate.
- Verification:
  - cosmetic edits do not expire solutions;
  - property/node/edge changes expire exact roots/downstream with disabled-edge and
    Trigger boundaries;
  - deleted isolated executable advances revision without invalid roots;
  - active-run edits coalesce one pending Auto rerun;
  - late/rejected/nondeterministic/capacity settlements cannot become current,
    republish availability, or replace retained previews;
  - expired retained output stays inspectable but produces no flowing grip/Panel/
    media renderer; current retained output does;
  - registry/runtime resets notify freshness projection immediately;
  - failed start restores prior current fact; started-run failure remains expired;
  - `CorexRuntime.start_run` and `_start_legacy` are absent;
  - cache count/byte/record eviction and monotonic run-count tests;
  - no node styling changes appear;
  - `./venv/Scripts/python.exe -m pytest tests/test_run_controller_unit.py tests/test_shell_run_controller.py tests/test_port_flow_state.py tests/test_port_availability.py tests/test_media_panel_source_resolution.py tests/test_data_type_ui_projection.py tests/test_graph_scene_presentation_facts.py tests/test_content_fullscreen_bridge.py tests/test_project_review_deck.py tests/main_window_shell/bridge_support.py tests/main_window_shell/view_library_inspector.py tests/main_window_shell/bridge_qml_boundaries.py tests/main_window_shell/mutation_ui_effects.py tests/graph_track_b/qml_preference_rendering_suite.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_store_session.py tests/test_headless_runtime.py tests/test_execution_client.py tests/test_plugin_runtime_agreement.py tests/test_registry_replacement.py -q`;
  - `./venv/Scripts/python.exe ./scripts/generate_source_test_file_index.py`;
  - `./venv/Scripts/python.exe ./scripts/generate_qml_navigation_index.py`;
  - `./venv/Scripts/python.exe ./scripts/generate_agent_route_index.py`;
  - `./venv/Scripts/python.exe ./scripts/check_agent_maps.py`;
  - `git diff --check`.
- Non-goals: expired-node coloring, Run Expired action, inspector, persistence;
  committed viewer bridge/service/host invalidation, transport release, and epochs
  remain T06. T05 preserves existing viewer behavior while adapting dispatch only.
- Packetization notes: `P05`; QML change is transport-only and stays in the same
  packet because it consumes the new single authority.

### T06 Scope viewer and live-resource invalidation to recomputed nodes

- Goal: Keep unaffected Model Viewer sessions/transports ready during unrelated
  partial runs.
- Preconditions: T03-T05 accepted; exact prepared recompute set available.
- Conservative write scope:
  - `ea_node_editor/ui/shell/controllers/run_controller.py`
  - `ea_node_editor/ui_qml/viewer_session_bridge.py`
  - `ea_node_editor/execution/protocol.py`
  - `ea_node_editor/execution/prepared_execution.py`
  - `ea_node_editor/execution/worker_protocol.py`
  - `ea_node_editor/execution/client.py`
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/execution/viewer_session_service.py`
  - `ea_node_editor/execution/worker_runner.py`
  - `ea_node_editor/nodes/viewer_runtime_contracts.py`
  - `tests/test_shell_run_controller.py`
  - `tests/test_viewer_session_bridge.py`
  - `tests/test_execution_viewer_service.py`
  - `tests/test_viewer_host_service.py`
  - `tests/test_execution_client.py`
  - `tests/test_execution_protocol.py`
  - `tests/test_solution_store_session.py`
  - `tests/test_run_verification.py`
  - `tests/test_execution_viewer_protocol.py`
  - `tests/test_execution_worker.py`
  - `tests/test_headless_runtime.py`
  - `tests/test_ssh_sftp_runtime.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/viewer_surfaces.md`
  - `docs/agent_maps/feature_routes/run_controller_selected_workspace_state.md`
  - `docs/agent_maps/feature_routes/viewer_session_overlay_fullscreen.md`
  - `docs/agent_maps/testing/qml_and_graph_surface_tests.md`
  - `docs/agent_maps/COVERAGE.md`
  - regenerated source/test and route indexes
- Deliverables:
  - delete blanket viewer preflight/reset/rollback helpers and manual-run flag;
    prepared dispatch reserves invalidation for `prepared.recompute_node_ids` but
    does not project it until worker preflight acceptance; failed dispatch/preflight
    invalidates nothing;
  - registry publication is idempotent by exact registry contract fingerprint:
    concrete execution clients and `ExecutionBackendClient` compare the requested
    fingerprint with their currently published/pinned fingerprint before every
    active-run, viewer-request, viewer-session, or high-level route replacement
    guard. An exact match returns `False` with no retirement, generation/epoch
    change, route cleanup, registry-owner replacement, or callback; only a differing
    fingerprint enters replaceability guards and replacement. The real
    `CorexRuntime.dispatch_prepared()` path continues publishing the registry, so
    same-registry reruns with live viewer routes reach prepared dispatch;
  - exact optional node filters on UI/worker viewer invalidators with one contract:
    `None` advances workspace epoch once and invalidates all; normalized empty is a
    strict invalidation no-op; non-empty deduplicates and affects exact nodes only;
    string-as-iterable filters reject. Worker context installation occurs separately
    through `install_workspace_context`; after committed empty adoption,
    invalidation, cleanup, signal, and transport mutation are skipped, with only the
    fresh-worker service baseline exception defined below;
  - partial run invalidates only recomputed viewers;
  - every viewer command/response carries nonnegative workspace/node epochs.
    Concrete clients and worker services validate transport-local epochs; the high-
    level client and Bridge validate projection-local epochs. After validating the
    emitting client, generation, request, and route against the concrete snapshot,
    the high-level client translates the event to its projection snapshot before
    callbacks; unvalidated or stale events are never translated;
  - scoped invalidation advances only affected node epochs, retires their pending
    requests/session/provisional/generation/owner maps, and preserves unaffected
    projections byte-for-byte;
  - `ViewerInvalidationReservation` carries immutable participant-local snapshots
    for process, trusted, external, and high-level projection state. It does not
    derive workspace or node epochs from a cross-participant maximum:
    - `None`: each participant advances its own workspace epoch exactly once and
      performs workspace-global cleanup;
    - normalized empty: every concrete/high-level target equals that participant's
      captured local epoch, node epochs are empty, and its plan is byte-identical;
    - non-empty: every participant retains its local workspace epoch, advances only
      the named nodes from that participant's local node epochs, and cleans only
      those nodes;
  - the reservation derives two identity-bound views without adding participant
    data to the worker wire contract: the existing `StartRunCommand`/preflight/
    commit fields carry the selected concrete participant's worker-service snapshot
    and digest; `viewer_invalidation_committed` carries the high-level/Bridge
    projection snapshot and its independently computed digest. The reservation
    retains all participant snapshots for parent prevalidation and all-or-nothing
    apply;
  - only the selected worker service may reconcile a participant difference. Equal
    selected-service epochs are a no-op. A lower service workspace epoch may
    baseline-adopt the selected concrete participant's already-committed epoch only
    when the selected worker/service generation is entirely fresh under the existing
    no-session/context/owner/lease/transport/buffer rule. Other concrete clients and
    the high-level client never advance or clean state merely to match another
    participant. Higher service epochs or non-fresh mismatches reject;
  - after final worker ensure/recycle, `CorexRuntime` derives the trusted viewer
    filter and creates the staged reservation. `StartRunCommand` carries only the
    selected worker-service view; reservation creation changes no visible counter,
    route, session, or projection;
  - worker preflight validates the prepared run and a non-mutating service cleanup/
    baseline plan, then emits identity/digest-bound `run_preflight_accepted` as the
    first run-scoped event and waits at most 30 seconds for
    `CommitRunPreflightCommand`. No viewer/node/run response precedes acceptance;
    failure does not adopt service state;
  - on matching preflight acceptance, encode the commit command before acquiring
    transaction locks. The sole commit order is: high-level
    `_viewer_invalidation_lock`; high-level `_active_lock`; then, in process/trusted/
    external order, each child `_state_lock` followed immediately by that child's
    `_viewer_request_lock`; finally the selected delivery transport/queue lock or
    already-pinned queue handle. Response ingress retains its existing child state-
    before-viewer order and high-level active-before-child-state order;
  - while those locks are held, read the selected generation directly from the
    already-held state lock, prevalidate every participant-local snapshot, and build
    immutable replacement plans. Commit delivery uses the pre-encoded payload and
    pinned transport/queue state and must not reacquire a child state/viewer lock.
    Successful delivery applies only precomputed non-throwing map replacements
    before releasing locks;
  - no callback, signal, protocol-error publication, generation callback, or
    buffered-event dispatch runs while any transaction lock is held. Delivery
    errors are recorded under lock and published only after release. Generation
    retirement/reset paths that need the same state follow the same order or wait
    until the transaction seal is released;
  - a `False` delivery result or exception cancels the parent/worker reservation and
    buffered responses after lock release, publishes no
    `viewer_invalidation_committed`, and leaves all visible concrete/high-level
    client, Bridge, and worker-service state byte-identical;
  - successful delivery and participant apply create an irreversible local commit
    finalizer before the generic selected-generation event path runs. The finalizer
    is not subject to ordinary child-generation or viewer-response filtering;
  - under the transaction seal, the finalizer chooses exactly one outcome: publish
    one `viewer_invalidation_committed` event carrying the projection snapshot; or,
    if same-turn generation retirement has already superseded that snapshot,
    synchronously complete the existing workspace-global retirement/reset adoption
    instead;
  - outside all locks, dispatch the chosen event/adoption exactly once. In a
    `finally` path, clear `_viewer_commit_publication_pending` and either drain still-
    current buffered events after Bridge adoption or discard them after global
    retirement. Callback failure, terminal events, later generation drift, reset,
    or shutdown cannot bypass gate cleanup;
  - later generation drift may globally retire the already-published snapshot, but
    may not suppress the commit finalizer. No state is permitted in which child/
    service commit succeeded while Bridge received neither the exact commit adoption
    nor the superseding global retirement;
  - the worker adopts the already-validated service cleanup/baseline plan only after
    receiving the exact commit command, then emits `run_started` and executes. Post-
    delivery service/run failure is a started-run failure and retains committed
    invalidation. Timeout, cancel, wrong identity/digest, terminal/reset, and
    shutdown discard uncommitted plans and buffers; no committed per-run snapshot
    registry is retained;
  - process/external clients ensure/recycle/handshake the worker before capturing
    the command epoch snapshot, so first post-restart viewer commands cannot use a
    retired epoch;
  - global project/load/reset paths advance/retire epochs before projection
    replacement; project load covers the union of old/incoming workspace IDs;
  - query success/failure signals move after epoch and workspace/node validation;
  - delayed close cannot close a replacement session;
  - reuse preserves session handles and transport;
  - worker derives viewer invalidation filter only from trusted prepared
    `EXECUTE` decisions whose resolved node spec has `surface_family == "viewer"`;
    remove unconditional `invalidate_existing=True`. Legacy commands with empty
    `preparation_id` pass `node_ids=None` and retain workspace-wide invalidation;
  - affected service records release transport, owner scope, handles/leases, strip
    stale refs, and become rerun-required; unaffected records/transport revisions
    remain identical; reused viewer open is idempotent;
  - add missing headless query and viewer-request invalidation delegation;
  - catch-all worker failure responses preserve both epoch fields;
  - high-level retired-request counts deduplicate request IDs across child backends;
    every generation-retirement and fatal-generation path, including trusted-worker
    fatal successor cleanup, removes matching session IDs, session generations, and
    session-node indices together;
  - update synthetic SSH `NodeExecutor` fixtures for accepted prepared-decision state;
    real-process reuse tests use load-tolerant bounded waits and deterministic
    stale-run cleanup without weakening assertions;
  - true reset/project/registry/runtime/backend replacement remains global;
  - no Model Viewer-specific branch in generic scheduling.
- Verification:
  - primary eight-step acceptance scenario in Viewer and live-resource scoping;
  - real, non-stub `CorexRuntime.dispatch_prepared()` with an active viewer route
    and the same registry reaches `run_preflight_accepted` and dispatch; a differing
    fingerprint remains rejected without partial retirement;
  - stale state injected independently into process, trusted, external, and high-
    level participants before commit rejects before delivery and leaves every
    participant unchanged; success commits all participants once;
  - `CommitRunPreflightCommand` delivery returning `False` and raising for each
    selected backend emits no commit event, causes no Bridge/service adoption, and
    leaves visible epochs, pending requests, routes, sessions, indices, owners,
    leases, and transports byte-identical;
  - with the selected concrete workspace epoch ahead of its recycled selected
    service, an empty-filter run baseline-adopts only that selected-client epoch and
    reaches dispatch. Equal selected concrete/service epochs are byte-identical; any
    selected-generation session, route, pending request, context, node epoch, owner,
    lease, transport, or buffered command makes the mismatch reject without
    mutation; high-level/Bridge projection state remains unchanged;
  - heterogeneous empty-filter matrix for each selected backend: process/trusted/
    external/high-level epochs differ and a non-selected backend owns a live
    session, route, pending request, and transport. Commit leaves every concrete/
    high-level map and Bridge byte-identical, retires zero requests, and only a
    qualifying fresh selected service baseline-adopts its selected-client epoch;
  - worker preflight/commit digest uses the selected concrete snapshot while the
    commit event digest uses the high-level projection snapshot;
  - a heterogeneous empty run followed by non-empty viewer recomputation retires
    only that viewer; the unrelated backend route survives, and both its response
    and the recomputed viewer response pass concrete validation and high-level
    projection translation;
  - `None` from heterogeneous participant epochs advances each participant's local
    workspace epoch once and remains truly global;
  - deterministic barrier proof holds response ingress at child state-before-viewer
    while commit begins; both threads complete and commit never acquires viewer-
    before-state;
  - process/trusted/external delivery helpers do not reacquire already-held state/
    viewer locks and invoke no callback while locked;
  - generation advancement immediately after successful delivery/apply yields
    exactly one commit adoption or one synchronous global retirement, coherent
    Bridge state, an empty pending gate, and no buffered-event leak. A raising
    subscriber and buffered `run_started`/terminal variants still clear the gate in
    `finally`; events drain only after adoption or are discarded by retirement;
  - trusted fatal-generation cleanup removes matching session-node entries together
    with session IDs and generations;
  - failed-start/cancelled viewer reservation leaves client/bridge/service epochs,
    pending requests, sessions, and transports byte-identical;
  - preflight-accepted acknowledgment is first, identity-bound, and commits exactly
    once; preflight failure yields no commit event or visible cleanup;
  - missing parent commit acknowledgment times out/cancels byte-identically; wrong
    reservation/digest rejects; post-ack service cleanup failure is reported as a
    started-run failure with committed invalidation retained;
  - synchronous reserved viewer responses buffer until successful commit and never
    escape after cancellation;
  - first post-recycle run commits the selected concrete/service and high-level/
    Bridge participant-local snapshots with no double increment;
  - terminal/reset/shutdown clear every unacknowledged reservation/buffer; no
    per-run committed snapshot registry leaks;
  - two viewers in one workspace, recompute one, retain one;
  - empty filter invalidates none; `None` invalidates all. Empty filters refresh
    runtime context; equal selected concrete/service epochs remain byte-identical,
    while a qualifying fresh recycled selected service may adopt only the selected
    concrete participant's already-committed workspace-epoch baseline. High-level/
    Bridge projection epochs remain unchanged;
  - legacy direct viewer run/failure/skip uses global invalidation and retires old
    transport/leases;
  - same-branch upstream change expires/recomputes viewer and requires a new live
    transport;
  - worker reset invalidates all session-only handles;
  - delayed pre-invalidation open/update/materialize/query/close responses cannot
    emit completion, mutate ownership, close replacements, or restore ready state;
  - process/external/trusted pending-request registries and provisional routes
    validate their participant-local transport epochs; high-level callbacks receive
    projection-local epochs only after validated translation;
  - direct empty-request-ID service calls use current epochs without node edits;
  - explicit query/invalidate delegation signatures, unresolved query owner, string
    rejection, and retired-request count tests;
  - all 17 `test_connection_failure_error_is_fixed_and_sensitive_text_free` SSH
    parameter cases pass with initialized prepared-decision fixture state;
  - `test_real_process_second_run_reuses_without_node_started` and
    `test_selected_and_diamond_reuse_preserve_plan_order` pass under the full fast
    xdist lane using load-tolerant bounded timeouts and deterministic cleanup;
  - `./venv/Scripts/python.exe -m pytest tests/test_shell_run_controller.py tests/test_viewer_session_bridge.py tests/test_execution_viewer_service.py tests/test_viewer_host_service.py tests/test_execution_client.py tests/test_execution_protocol.py tests/test_execution_viewer_protocol.py tests/test_execution_worker.py tests/test_headless_runtime.py tests/test_solution_store_session.py tests/test_run_verification.py -q`;
  - scope audit proves the diff from foundation `63e9786f` is a subset of the
    expanded T06 scope plus the two declared unrelated/prohibited baseline paths;
  - regenerate source/test and route indexes, run `check_agent_maps.py`, then
    `run_verification.py --mode fast --summarize-output` and `git diff --check`.
- Non-goals: viewer QML styling or a persistent live native handle.
- Packetization notes: `P06`; primary UX acceptance packet.

### T07 Implement the durable solution repository and codecs

- Goal: Persist eligible solution records/results atomically in project-managed
  sidecar storage using the same store/record model as session reuse.
- Preconditions: T01-T04 accepted; durable eligibility and implementation identity
  gates from T02 complete.
- Conservative write scope:
  - `ea_node_editor/execution/solution_store.py`
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/execution/prepared_execution.py`
  - `ea_node_editor/persistence/solution_repository.py` (new)
  - `ea_node_editor/persistence/artifact_store.py`
  - `ea_node_editor/runtime_contracts/durable_values.py`
  - `ea_node_editor/runtime_contracts/solution_records.py`
  - `ea_node_editor/ui/shell/composition/controllers.py`
  - `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
  - `tests/test_solution_repository.py` (new)
  - `tests/test_solution_store_session.py`
  - `tests/test_headless_runtime.py`
  - `tests/test_solution_records.py`
  - `tests/test_typed_runtime_values.py`
  - `tests/test_project_artifact_store.py`
  - `tests/test_project_session_controller_unit.py`
  - `tests/test_serializer.py`
  - `tests/test_architecture_boundaries.py`
  - `tests/test_persistence_package_imports.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/persistence.md`
  - `docs/agent_maps/subsystems/supporting_runtime_assets.md`
  - `docs/agent_maps/subsystems/ui_shell.md`
  - `docs/agent_maps/subsystems/startup_and_bootstrap.md`
  - `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`
  - `docs/agent_maps/feature_routes/managed_artifacts_project_data.md`
  - `docs/agent_maps/feature_routes/serialization_migration_legacy_rejection.md`
  - `docs/agent_maps/COVERAGE.md`
  - regenerated source/test and agent-route indexes
- Deliverables:
  - execution-owned durable backend/factory ports and persistence-owned concrete
    repository with no reverse import;
  - captured maximum reuse scope, conditional durable/session publication, forced-
    recompute conflict lookup, and runtime-reset versus project-detach semantics;
  - centralized durable runtime-value gate covering every declared/concrete catalog
    type, sensitivity, carrier, artifact, path, and inline ceiling;
  - exact schema-1 manifest-set/node-manifest/record/result-blob layouts, full
    logical-ID path keys, bounds, deterministic reasons, and immutable I/O rules;
  - bind reads only `manifest-set.json`; lookup reads only the requested node
    manifest/record; payload loads only for accepted-output resolution;
  - candidate generation build/validation plus reachability/safe-prune primitives;
  - saved open/replacement binds an already committed pointer; absent/corrupt/
    unknown solution metadata opens authored data session-only with one sanitized
    regeneration diagnostic and no cache state;
  - restart reuse for strict portable values and validated managed artifacts;
  - current integrity verification and deterministic recompute fallback;
  - same-key/same-result retention and ordinary/forced same-key/different-result
    nondeterminism without overwrite or session fallback;
  - no `.cxproj` mutation, Save/Save As success/binding switch, or lifecycle prune
    until T08.
- Verification:
  - every schema field/order/type and each repository limit at `N` and `N+1`;
  - full SHA-256 path-key collision/binding, containment, link/junction/reparse,
    replace-scan-restore, truncation, mutation-during-read, digest, canonical-byte,
    and unknown-field rejection;
  - lazy-load read-count/order proof and no partial cache installation on failure;
  - repository-built restart generation with manually supplied committed descriptor,
    without a `.cxproj` write;
  - absent/corrupt/unknown solution metadata preserves authored data session-only
    with one sanitized diagnostic;
  - all 29 maximum-durable rows remain conditional on actual output eligibility;
  - every excluded carrier/sensitivity/path/artifact case and large `ImageValue`
    stays session-only without durable bytes;
  - stage I/O/capacity failure falls back safely to session;
  - nondeterminism, generation-reset binding preservation, project-detach close/no-
    delete, and T07/T08 non-overlap tests;
  - execution imports no persistence implementation; `common` remains a leaf; no
    duplicate scheduler/store framework;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_repository.py tests/test_solution_records.py tests/test_typed_runtime_values.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_store_session.py tests/test_headless_runtime.py -k "durable or solution_repository or project_solution" -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_project_artifact_store.py tests/test_project_session_controller_unit.py -k "solution or reachability or bind or replacement" -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_serializer.py tests/test_architecture_boundaries.py tests/test_persistence_package_imports.py -k "solution_store or solution_repository or persistence_neutral" -q`;
  - acceptance runs all ten scoped test modules together, regenerates source/test
    and agent-route indexes, runs `check_agent_maps.py`, then `git diff --check`;
  - no broad fast/full lane unless implementation escapes this boundary.
- Non-goals: remote/global cache, cross-project deduplication, migration, Save/Save
  As orchestration, `.cxproj` replacement, lifecycle pruning, QML.
- Packetization notes: `P07`; execution timing and worktree use defer entirely to
  the current orchestration baseline in the ledger.

### T08 Integrate copy-on-write Save, Save As, reopen, adoption, and garbage collection

- Goal: Commit one self-contained project snapshot without moving, deleting, or
  overwriting source/committed sidecar content before the project-file commit.
- Preconditions: T07 accepted; reviewed T08 transaction and self-contained create-
  new no-clobber policy authorized.
- Conservative write scope:
  - `ea_node_editor/ui/shell/controllers/project_session_controller.py`
  - `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
  - `ea_node_editor/execution/solution_store.py`
  - `ea_node_editor/execution/headless_runtime.py`
  - `ea_node_editor/persistence/solution_repository.py`
  - `ea_node_editor/persistence/artifact_store.py`
  - `ea_node_editor/persistence/image_blobs.py`
  - `ea_node_editor/persistence/serializer.py`
  - delete `ea_node_editor/ui/dialogs/project_save_as_dialog.py`
  - `tests/test_project_save_as_flow.py`
  - `tests/test_project_artifact_store.py`
  - `tests/test_serializer.py`
  - `tests/test_solution_repository.py`
  - `tests/test_solution_store_session.py`
  - `tests/test_headless_runtime.py`
  - `tests/test_project_session_controller_unit.py`
  - `tests/test_image_value.py`
  - `tests/test_architecture_boundaries.py`
  - `tests/test_shell_project_session_controller.py`
  - `tests/test_tabular_project_managed_data.py`
  - `tests/test_solution_records.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/persistence.md`
  - `docs/agent_maps/subsystems/ui_shell.md`
  - `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`
  - `docs/agent_maps/feature_routes/managed_artifacts_project_data.md`
  - `docs/agent_maps/feature_routes/serialization_migration_legacy_rejection.md`
  - `docs/agent_maps/COVERAGE.md`
  - regenerated source/test and agent-route indexes
- Explicitly unnecessary production scope:
  - `session_lifecycle_service.py`
  - `project_files_service.py`
  - QML, composition, migration, project schema, runtime-value/solution-record
    schemas, requirements/traceability/release docs, and `docs/specs/INDEX.md`
- Deliverables:
  - non-reentrant save guard and document/solution snapshot tokens;
  - copy-on-write artifact migration/promotion and immutable image publication;
  - execution-owned solution save/export DTOs and factory port;
  - active-generation merge, durable-maximum session export, removed-owner filter,
    destination artifact validation, and fresh empty generation;
  - self-contained create-new first Save/Save As with atomic no-clobber publication;
  - normal-save atomic replacement only at the currently bound path;
  - raw reopen plus complete pointer/artifact/image/generation verification;
  - expected-namespace/token candidate adoption preserving source on failure;
  - exact saved versus committed-not-adopted outcomes;
  - bounded previous+new-protected GC followed by later active-only retries;
  - remove the Save As `Project file only` choice;
  - retain legacy destructive artifact helpers only for explicit non-save callers;
    no production Save/Save As path may call them.
- Verification:
  - first Save preserves random unsaved namespace and reuses eligible records after
    restart;
  - normal Save merges active generation and new records;
  - source-removal Save As fixture includes managed/staged artifacts, `ImageValue`,
    ordinary durable value, and durable managed-artifact solution; after deleting
    source `.cxproj`/`.data`, fresh runtime resolves/hydrates destination, binds the
    generation, and reuses without `node_started`;
  - removed owners do not enter the candidate; session records export only when
    current and captured maximum scope was durable;
  - every failure-matrix stage asserts exact source/destination/live state;
  - destination `.cxproj`/sibling `.data` and create-new race no-clobber tests;
  - source mutation/autosave/project replacement and solution-binding drift tests;
  - identical image/managed targets reuse; differing immutable image bytes reject,
    and artifact bytes use the full-digest-suffixed target without overwrite;
  - immediate GC protects previous/new reachability; later active-only pass deletes
    only validated candidates; GC failure never changes save success;
  - architecture proof: Document I/O imports no concrete solution repository and
    execution imports no persistence implementation;
  - publication-state shapes, publish-then-raise modes, postcommit artifact union/
    exact integrity mismatch, fresh solution reopen, deterministic altered-snapshot
    rejection, strict snapshot fields, complete byte estimate, retryable GC, and
    affected shell/Tabular/solution-record caller compatibility;
  - `./venv/Scripts/python.exe -m pytest tests/test_project_save_as_flow.py tests/test_project_artifact_store.py tests/test_serializer.py tests/test_solution_repository.py -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_solution_store_session.py tests/test_headless_runtime.py -k "project_solution_save or durable_save or binding" -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_project_session_controller_unit.py -k "save or reopen or bind or autosave or recovery" -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_image_value.py tests/test_architecture_boundaries.py -k "save or sidecar or solution or no_clobber or prune" -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_shell_project_session_controller.py tests/test_tabular_project_managed_data.py tests/test_solution_records.py -q`;
  - regenerate source/test and agent-route indexes, run `check_agent_maps.py`, then
    `git diff --check`.
- Non-goals: overwrite of a different existing project, project-file-only Save As,
  compatibility migration, cloud/global cache, requirements/traceability updates,
  broad fast/full verification, or unrelated lifecycle cleanup.
- Packetization notes: `P08`; implementation starts after revised whole-plan hash
  is independently accepted. User authorization is already recorded in the ledger.

### T09 Closeout, independent review, documentation, and acceptance

- Goal: Prove the clean cutover, remove obsolete paths, and register only accepted
  requirement evidence.
- Preconditions: T01-T08 accepted; existing unrelated `docs/specs/INDEX.md` owner
  hunk remains unstaged and the T09 addition is staged separately.
- Conservative write scope:
  - `ea_node_editor/execution/viewer_session_service.py`
  - `ea_node_editor/ui_qml/viewer_session_bridge.py`
  - `ea_node_editor/ui/shell/controllers/run_controller.py`
  - `tests/test_viewer_session_bridge.py`
  - `tests/test_execution_viewer_service.py`
  - `tests/test_viewer_host_service.py`
  - `tests/test_shell_run_controller.py`
  - `tests/test_run_controller_unit.py`
  - `tests/test_data_tree_ui.py`
  - `tests/test_corex_contract_catalog.py`
  - `tests/test_traceability_checker.py`
  - `tests/test_markdown_hygiene.py`
  - `tests/repo_owned_catalog_fixture.py`
  - `tests/fixtures/node_catalog/current_repo_owned_catalog.json`
  - `docs/specs/requirements/20_UI_UX.md`
  - `docs/specs/requirements/50_EXECUTION_ENGINE.md`
  - `docs/specs/requirements/60_PERSISTENCE.md`
  - `docs/specs/requirements/90_QA_ACCEPTANCE.md`
  - `docs/specs/requirements/TRACEABILITY_MATRIX.md`
  - `docs/specs/INDEX.md` (T09 hunks only)
  - `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`
  - `scripts/verification_manifest.py`
  - `scripts/check_traceability.py`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/nodes_registry_builtins.md`
  - `docs/agent_maps/subsystems/viewer_surfaces.md`
  - `docs/agent_maps/feature_routes/run_controller_selected_workspace_state.md`
  - `docs/agent_maps/feature_routes/viewer_session_overlay_fullscreen.md`
  - `docs/agent_maps/testing/docs_traceability_hygiene.md`
  - `docs/agent_maps/COVERAGE.md`
  - regenerated `docs/agent_route_index.md` and `docs/agent_route_index.json`
  - `docs/PLAN_COREX_INCREMENTAL_EXECUTION_AND_SOLUTION_SNAPSHOTS.md`
  - `docs/PLANS/COREX_INCREMENTAL_EXECUTION_TASK_LEDGER.md`
- Deliverables:
  - remove the three dead workspace/all-session bridge compatibility invalidators;
    RunController global fallback calls `project_all_run_required` directly;
  - remove the dead service API that combined context installation and invalidation;
    retain explicit `install_workspace_context`, validation/adoption, and legacy-
    only direct `invalidate_workspace` ownership;
  - remove obsolete raw cache `stale/stale_reason` test setup/assertions without
    deleting the fact-derived presentation projection;
  - zero duplicate scheduler/freshness authorities;
  - zero blanket partial-run viewer invalidators;
  - zero references to the four removed APIs across production, tests, maps, and
    this plan;
  - one direct `ShellRunControllerTests` acceptance with graph
    `engineering.cad_import.scene -> model.viewer.scene` plus disconnected
    `data.boolean_toggle`; seed a fixed current/open/ready bridge viewer and real
    worker-service session, toggle only through history/Auto, and apply the same
    empty committed snapshot to both bridge/service. First assert exact target, no
    viewer `node_started`/release, current fact, and byte-identical session/
    transport/summary/preview through completion; then separately perform same-node
    invalidation and prove delayed old-epoch response rejection;
  - current-contract catalogue at
    `tests/fixtures/node_catalog/current_repo_owned_catalog.json`, applied
    after structural overlay and before reuse classification, with exact schema:

    ```text
    schema_version = 1
    frozen_sha256 = 3CF91390E9E4C606B571ED3C907D7BF35647165F5358328F8FE9C18BF15C618F
    property_default_patches
      model.viewer
        representation
          expected_default = surface
          replacement_default = surface_with_edges
    ```

    These are the only top-level/nested keys and sole patch. Reject extra keys,
    drift, duplicates, unknown target, or out-of-enum replacement; frozen fixture
    SHA and classification SHA stay unchanged;
  - stale effective-catalog failures close with frozen=`surface` and effective/live
    `surface_with_edges` proof;
  - promote `REQ-EXEC-017` from planned only at final closeout after clean fast
    verification and all three independent reviews;
  - promote `REQ-PERSIST-026` at that same final closeout with exact wording:
    immutable record identity/
    integrity is durable, while mutable freshness/invalidation is reconstructed
    against current graph/runtime and never persisted as durable truth;
  - keep `REQ-UI-052` exactly planned/unimplemented;
  - correct `REQ-UI-029`, `REQ-PERSIST-017`, and `REQ-PERSIST-018` plus acceptance
    criteria: normal Save replaces only the bound `.cxproj`; Save As is self-
    contained create-new/no-clobber; live path/binding changes only after committed
    reopen/adoption; cleanup is bounded/post-adoption; remove deleted dialog/copy-
    choice references;
  - update `SYN-OPP-0002` to partial: backend/persistence accepted, UX planned;
  - update capability-status manifest/checker/test ownership counts, add normal
    traceability/proof rows for promoted requirements, update `REQ-QA-055` and
    retained novice-SDK QA proof for the new overlay, without relabeling historical
    full/package evidence;
  - independent architecture, security/data-integrity, and UX-acceptance reviews;
  - only after clean fast and all three reviews, mark this plan
    `COMPLETED — T01–T09 ACCEPTED`, register it under Completed Implementation
    Plans, promote the two requirements, and rerun exact traceability/Markdown checks.
- Verification:
  - `./venv/Scripts/python.exe -m pytest tests/test_viewer_session_bridge.py tests/test_execution_viewer_service.py tests/test_viewer_host_service.py tests/test_shell_run_controller.py tests/test_run_controller_unit.py --ignore=venv -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_novice_plugin_sdk_docs.py tests/test_repo_owned_node_documentation.py tests/test_corex_contract_catalog.py tests/test_node_title_icon_assets.py tests/test_builtin_function_migration.py tests/test_remaining_builtin_function_migration.py tests/test_architecture_boundaries.py tests/test_dead_code_hygiene.py --ignore=venv -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_agent_route_index.py --ignore=venv -q`;
  - `./venv/Scripts/python.exe -m pytest tests/test_data_tree_ui.py::test_open_project_shows_migration_report_after_finalization_without_overwriting_source -q`;
  - regenerate only agent route indexes; source/test paths and QML components do not
    change;
  - `./venv/Scripts/python.exe ./scripts/check_agent_maps.py`;
  - `./venv/Scripts/python.exe ./scripts/check_traceability.py`;
  - `./venv/Scripts/python.exe ./scripts/check_markdown_links.py`;
  - `./venv/Scripts/python.exe ./scripts/run_verification.py --mode fast --summarize-output`;
  - every focused/check/map/traceability/Markdown/fast command exits zero; declared
    skips are allowed, failing-test waivers are not;
  - optional display-attached acceptance uses
    `examples/engineering_viewer/engineering_viewer_capabilities.cxproj`; record
    `NOT RUN` when display/GPU state is unstable because automation remains required.
- Non-goals: UI coloring, new snapshot controls, persistence/save redesign,
  overwrite policy changes, frozen catalogue edits, startup/full/package lanes,
  unrelated cleanup, or the untracked Physical Simulation plan.
- Packetization notes: `P09`; reviewers must be separate from all implementation
  owners. Any reviewer finding reopens the owning task, not a new catch-all patch.

## Work Packet Conversion Map

1. `P00 Bootstrap`: create external packet manifests/prompts only after plan
   approval; copy task IDs and ledger gates verbatim; no production edits.
2. `P01 Solution Contracts And Shared Plan`: T01.
3. `P02 Canonical Identity And Eligibility`: T02.
4. `P03 Session Solution Store`: T03.
5. `P04 Worker Reuse Cutover`: T04.
6. `P05 Shell Invalidation And Freshness Projection`: T05.
7. `P06 Scoped Viewer Invalidation`: T06.
8. `P07 Durable Solution Repository`: T07.
9. `P08 Save And Save-As Transactions`: T08.
10. `P09 Closeout And Independent Acceptance`: T09.

Assignment, resume, evidence, worktree, implementation, and review gates are owned
only by `docs/PLANS/COREX_INCREMENTAL_EXECUTION_TASK_LEDGER.md`.

## Test Plan

### Required semantic matrix

- never-run node -> `never`.
- valid settlement -> `current`.
- execution-affecting node/property/edge change -> exact root/downstream
  `expired`.
- cosmetic graph edit -> no freshness change.
- disabled edge and Trigger boundary -> no propagation past boundary.
- mutation during run -> late old-key settlement cannot restore current.
- second identical Run -> reused dispositions, zero implementation calls.
- Run Selected -> reuse current upstream, recompute expired/missing upstream, do
  not run siblings.
- Auto -> only affected target closure requested; current upstream reused.
- force recompute -> valid record ignored intentionally.
- force recompute with identical outputs -> established record retained; divergent
  outputs -> nondeterminism conflict without overwrite.
- empty/outputless eligible settlement -> reusable.
- failed/blocked/cancelled/infrastructure-lost settlement -> not reusable.
- file/artifact/implementation/toolchain/backend/catalog change -> key miss and
  recompute.
- UI-only change -> key remains stable.
- stale output remains bounded/inspectable but cannot become current flow.
- worker/runtime/registry generation replacement -> session handles expire.
- durable restart -> supported records lazily restore.
- durable restart uses stable environment/interface identity, never ephemeral
  runtime-generation counters.
- corrupt or unsupported durable state -> recompute with deterministic reason.
- precommit Save/Save As failure -> previous committed project/artifact set remains
  authoritative;
- postpublication verification/adoption failure -> verified publication makes the
  candidate disk project authoritative; publication-uncertain failure may leave
  either prior or candidate complete atomic file; in both cases live source
  state/binding remains dirty and unadopted with no pruning;
- Save As preserves logical solution identity while rewriting destination storage
  descriptors outside solution keys.
- crash before/after `.cxproj` publication resolves to one complete
  generation, never a mixed manifest set.

### Primary UX regression

Automate the disconnected Model Viewer acceptance scenario from Key Changes. The
test must assert all of the following, not merely absence of a QML label:

- unrelated branch is the only recompute target;
- viewer node freshness remains `current`;
- viewer node receives no `node_started` event;
- viewer bridge receives no run-required projection;
- worker viewer service releases no transport/owner scope for that node;
- session stays open/ready with the same transport revision;
- last cached preview/live presentation remains available throughout.
- delayed old-epoch viewer responses are discarded and cannot revive invalidated
  state.

### Data integrity and security matrix

- canonical encoder rejects hostile/custom values without callbacks;
- manifests are size/depth/count bounded;
- all logical IDs are validated and path-keyed;
- path escape, symlink/reparse, hash mismatch, truncation, and unknown schema fail
  closed;
- secret/protected/runtime-handle/native/callback/private-path values cannot become
  durable;
- immutable record conflict reports nondeterminism;
- cleanup never deletes content reachable from the previous or newly committed
  manifest set.

### Broad acceptance boundary

Run focused suites during each task. T09 stops at one clean summarized fast
verifier. Any later release-confidence, full, startup, package, or installer lane is
a separate scope.

## Assumptions

- COREX remains unreleased; internal APIs and experimental metadata may break.
- Existing architecture boundaries may be changed when the replacement ownership
  is cleaner and more intuitive; update all callers, boundary tests, and agent maps
  in the same accepted task instead of adding adapters.
- No migration or compatibility reader is required.
- The existing `.cxproj` current schema remains the project document; durable
  results live in its `.data` sidecar.
- Session reuse is delivered before durability because live handles and the primary
  Model Viewer acceptance depend on runtime-generation-local state.
- Durable eligibility remains fail closed until normalized execution identity,
  implementation digest, provenance, and output codecs are complete.
- Trigger publication/sample-and-hold remains session-only and is not a durable
  solution dependency unless a later requirement defines it.
- Nodes with side effects or untracked external state default to `never` reuse.
- Worker queues/stdin are treated as private OS-owned parent/child channels. T04
  validates structure, identity, catalog, resources, and generation; authenticated
  command envelopes/MACs are a separate security scope.
- Node coloring, expired stripes, snapshot settings UI, inspector, clear/recompute
  actions, and provenance explanations are later UI work under `REQ-UI-052`.
- Explicit value internalization/data-container nodes are a separate authored-data
  feature and are not part of solution snapshot caching.
- Orchestration mechanics are governed exclusively by
  `docs/PLANS/COREX_INCREMENTAL_EXECUTION_TASK_LEDGER.md`.
