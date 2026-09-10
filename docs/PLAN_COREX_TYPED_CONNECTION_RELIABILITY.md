# COREX Typed Connection Reliability - Implementation Plan

Status: `COMPLETED - T00-T06 ACCEPTED`

Task ledger: [COREX Typed Connection Reliability Task Ledger](PLANS/COREX_TYPED_CONNECTION_RELIABILITY_TASK_LEDGER.md)

## Summary

Quick Insert and final graph mutation already share the graph compatibility
predicate. The defect is that Quick Insert reduces every legal relation to a
Boolean, so exact typed matches, broad structural matches, global `Any`, and
runtime-checked matches compete as peers. Additional recurrence paths are
over-broad repo-owned metadata, omitted author types becoming `Any`, malformed
workflow/library previews becoming `Any`, and Library rows using base rather
than default-resolved dynamic ports.

This plan keeps graph legality unchanged for `assignable`, `convertible`, and
`runtime_check`, adds one structured graph result, and makes Quick Insert a
separate recommendation policy. Blank connection search shows only precise
matches; explicit search reveals legal broad/runtime fallbacks with labels.
Repo-owned authoring and projection fail closed. Unrelated catalogue generation
and type-taxonomy work are excluded.

No second registry, `allow_any` flag, compatibility shim, runtime-error wire
redesign, or insertion rollback transaction is introduced.

## Key Changes

### Structured graph compatibility

- Add `port_compatibility(source_port, target_port, *, data_types)` to
  `graph/effective_ports.py`, returning the existing
  `DataTypeCompatibility`.
- Kind mismatch returns `incompatible/port_kind_mismatch`; compatible flow
  returns `assignable/flow_kind_match` with `flow` IDs; data ports delegate to
  the data-type catalogue with the target primary and accepted types.
- Make `ports_compatible()` only the Boolean adapter over
  `port_compatibility().is_compatible`.
- Evaluate the complete target type union and return the strongest relation:
  exact assignable, parent/interface assignable, direct conversion,
  runtime-check, first unresolved, then incompatible.
- Use the structured result in the invariant kernel, static edge-warning
  projection, Quick Insert, and post-insertion auto-connect. Execution and
  solution code that needs type-only checks stays unchanged.

### Recommendation fallback metadata

Reuse `DataTypeSpec.capabilities` with the token `connection_fallback`. Mark:

- `COREX.DataTypes.Any`
- `COREX.DataTypes.Json`
- `COREX.DataTypes.GraphArray`
- `COREX.DataTypes.GraphDictionary`

A Quick Insert relation is fallback if its status is `runtime_check` or its
matched type carries `connection_fallback`, including an exact match. The
connection remains legal and is available through explicit search.

### New semantic types

Add internal `COREX.DataTypes.JsonValue`:

- abstract child of `COREX.DataTypes.Any`;
- exact JSON-domain validation for null, Boolean, integer, finite float,
  string, list, and string-keyed dictionary values;
- recursive bounded validation using existing JSON-copy/size guards;
- rejects non-finite values, non-string keys, runtime markers, unsupported
  objects, and oversized payloads.

Reparent Bool, Int, Double, String, GraphArray, GraphDictionary, Json, and
StringList beneath JsonValue. Tighten Json/StringList validators and Constant
and File Write serialization to the same strict finite JSON contract. Do not
reparent Path, Interval, images, engineering values, handles, or plot exports.

Add internal `COREX.Plot.ExportBundle`:

- concrete child of `COREX.DataTypes.Any`, family `container`, native carrier,
  persistence `never`;
- accepts exactly `static_export`, `data_export`, `static_metadata`, and
  `data_metadata`;
- the export values must be exact `RuntimeArtifactRef` objects and metadata
  must be bounded JSON dictionaries;
- rejects nested refs, missing/extra keys, arbitrary mappings, and invalid
  metadata.

Export the two internal ID constants only through existing internal type
surfaces. Keep public `corex.__all__` at exactly 17 names.

### Exact repo-owned metadata changes

Change primary types:

| Port | New type |
| --- | --- |
| `core.constant.value` | `COREX.DataTypes.JsonValue` |
| `io.file_write.data` | `COREX.DataTypes.JsonValue` |
| `fea.force.load` | `COREX.Fem.Force` |
| `plot.scatter.exports` | `COREX.Plot.ExportBundle` |
| `plot.bar.exports` | `COREX.Plot.ExportBundle` |
| `plot.histogram.exports` | `COREX.Plot.ExportBundle` |
| `plot.heatmap.exports` | `COREX.Plot.ExportBundle` |
| `plot.contour.exports` | `COREX.Plot.ExportBundle` |
| `plot.surface.exports` | `COREX.Plot.ExportBundle` |
| `plot.point_cloud.exports` | `COREX.Plot.ExportBundle` |
| `plot.streamlines.exports` | `COREX.Plot.ExportBundle` |

Remove repeated primary types from these accepted alternatives:

| Port | Accepted alternatives |
| --- | --- |
| `math.construct_interval.start` | Int |
| `math.construct_interval.end` | Int |
| `ssh_sftp.host.private_key_path` | Path |
| `core.stream_gate.gate` | Int |

Update the current repo-owned contract catalogue for the eleven primary-type
changes. The pre-cutover fixture remains byte-identical.

Add a trusted repo-owned registry audit whose exact default global-Any set is:

- `core.if.true_value`, `core.if.false_value`, `core.if.result`
- `io.process_run.stdout`, `io.process_run.stderr`
- `data.panel.input`, `data.panel.output`
- `core.trigger.input`, `core.trigger.output`
- `core.stream_gate.stream`, `core.stream_gate.output_0`,
  `core.stream_gate.output_1`
- `core.python_script.payload`, `core.python_script.result`
- `core.subnode_input.pin`, `core.subnode_output.pin`
- hidden `media.panel._surface_source`
- `mars.batch_solve.files`, `mars.run_job.files`, `mars.time_history.files`

The audit excludes public plugins. A second audit requires every repo-owned
accepted tuple to exclude its primary type.

The approved planning count of seventeen omitted the three existing MARS
filename-to-artifact maps. Implementation inspection confirmed their explicit
Any declarations and runtime `dict[str, RuntimeArtifactRef]` shape. The exact
residual audit is therefore twenty; no MARS implementation/type change is made.

### Fail-closed authoring and projection

- Public function plugins and Python Script require explicit `value_type=` on
  every `@corex.input` and `@corex.output`; omission raises a source-located
  declaration error. Deliberate broad ports use `value_type=corex.Any`.
- Update shipped defaults, tests, examples, and authoring/migration guides. Do
  not auto-rewrite user source.
- Current custom-workflow publication rejects malformed data interface ports.
  Legacy normalization retains the workflow/fragment but drops malformed
  preview ports. Accepted types stay ordered, unique, and exclude the primary.
- `projected_port_declared_data_types()` returns no types when the primary is
  missing. Library, Quick Insert, and the QML preview fallback skip that port;
  none of them substitutes `Any`.
- Build registry Library ports with
  `resolve_instance_ports(spec, {}, data_types=registry.data_types)` and derive
  data-type filter options from the projected combined rows.

### Quick Insert recommendation behavior

Always compare the eventual `output -> input` edge, including reverse drags.
Classify compatible ports as:

| Kind | Condition | Label |
| --- | --- | --- |
| `exact` | non-fallback exact assignable | Exact type |
| `assignable` | non-fallback parent/interface | Compatible type |
| `convertible` | non-fallback direct conversion | Converts automatically |
| `generic` | matched fallback-capable type | Broad data match |
| `runtime_check` | runtime-check status | Checked at runtime |
| `flow` | compatible flow | Flow |

For each node, discard hidden, unresolved, wrong-kind, and incompatible ports;
retain only equal-best ports in declaration order using the tier order exact,
assignable, convertible, flow, generic, runtime-check.

- Blank connection query shows exact/assignable/convertible/flow only.
- Nonblank query also shows generic/runtime-check rows with labels.
- Existing text rank comes first, then tier, port-count tie-break, display name,
  type ID, and only then the existing 12-row cap.
- Canvas Quick Insert remains query-required and otherwise unchanged.

Each compatible port adds `compatibility_kind`, `compatibility_label`, and
`matched_data_type`. Each node adds its best kind/label and
`compatible_port_summaries`. Existing compatible-port fields remain.

The overlay renders summaries such as `scene - Exact type` and
`data - Broad data match`; text, not color, is authoritative. It adds no Qt
property/slot or QML type logic.

For a valid connection context with zero blank results, keep the overlay open
and show `No direct type matches. Type to search broader compatible nodes.` A
nonblank miss shows `No matching compatible nodes.` Only an invalid origin
context prevents opening.

### Selection and load behavior

- Pass the displayed compatible port keys into the existing drop controller.
- After creation, resolve actual effective ports, restrict candidates to those
  keys, recompute structured compatibility, use the existing equal-choice
  prompt, and leave the invariant kernel as final gate.
- Ordinary Library drops continue using every graph-legal port.
- Do not add rollback. An unsupported stale-key case retains the existing
  unconnected-node behavior; tests must prove default-resolved rows reconnect
  in the supported stable-registry flow.
- Keep existing project normalization: newly invalid edges are removed in
  memory, the workspace becomes dirty, and source files are untouched until
  save. Add controls for valid JsonValue, Force-to-ILoad, and intentional Any
  edges.
- Do not add runtime port identity or runtime-red wire behavior.

## Public Interface Changes

- Public and Python Script input/output decorators require `value_type=`.
- Intentional broad declarations use `corex.Any` explicitly.
- Internal IDs: `COREX.DataTypes.JsonValue`, `COREX.Plot.ExportBundle`.
- Internal graph API: `port_compatibility(...)`.
- Internal Library/drop signatures carry default-resolved ports and displayed
  candidate keys.
- Quick Insert rows gain compatibility classification/summary fields.
- No public `corex` export, project schema, workflow schema, package schema,
  wire protocol, or Qt property version changes.

## Execution Tasks

### T00 Canonical plan, ledger, and baseline

- Goal: persist this plan and the mandatory resume ledger.
- Preconditions: implementation authorization.
- Conservative write scope: this plan, its ledger, and only its index line.
- Deliverables: baseline, decisions, task states, owner/evidence fields, resume
  protocol, and protected dirty-path record.
- Verification: Markdown links and `git diff --check`.
- Non-goals: production code.
- Packetization notes: `P00 Bootstrap`.

### T01 Compatibility and semantic types

- Goal: structured compatibility, strongest accepted-union choice, JsonValue,
  Plot Export Bundle, and fallback capabilities.
- Preconditions: T00 accepted.
- Conservative write scope: runtime type catalogue/core registration,
  effective-port/invariant/static-warning owners, focused tests.
- Deliverables: exact contracts above with unchanged graph legality.
- Verification: data-type, core-value, graph-enforcement, route-payload tests.
- Non-goals: declarations and Quick Insert UI.
- Packetization notes: `P01 Contract Foundation`.

### T02 Repo-owned metadata and explicit authoring

- Goal: correct eleven primary types, four accepted tuples, and require explicit
  public/Python Script types.
- Preconditions: T01 accepted.
- Conservative write scope: affected built-ins/functions, declaration parsers,
  current repo-owned catalogue, exact conformance tests.
- Deliverables: metadata changes, exact Any inventory, zero repeated primary.
- Verification: plugin/Python Script, core, integration, FEM, generic plot,
  interval, SSH, overlay, registry-conformance tests.
- Non-goals: unrelated declaration/generation changes or public aliases.
- Packetization notes: `P02 Metadata and Authoring`.

### T03 Projection integrity

- Goal: remove missing-type fallbacks and align Library/default dynamic ports.
- Preconditions: T01-T02 accepted.
- Conservative write scope: custom-workflow codec, Library projection/presenter,
  QML Library-preview fallback, focused tests.
- Deliverables: malformed-port omission, default-resolved rows and filters.
- Verification: workflow, Library, default Python Script/Stream Gate, and
  graph-scene preview tests.
- Non-goals: Quick Insert ranking or workflow migration.
- Packetization notes: `P03 Projection Integrity`.

### T04 Typed Quick Insert

- Goal: tiered/query-gated suggestions, labels, empty state, and selected-key
  auto-connect revalidation.
- Preconditions: T01-T03 accepted.
- Conservative write scope: Quick Insert projection, Library presenter,
  drop-connect controller, overlay QML, focused tests.
- Deliverables: exact behavior/payload above, both drag directions, unchanged
  flow/canvas behavior.
- Verification: Quick Insert, drop controller, graph-surface, isolated shell.
- Non-goals: graph legality, runtime-red wires, rollback.
- Packetization notes: `P04 Typed Quick Insert`.

### T05 Persistence, specifications, guides, and maps

- Goal: lock load behavior and publish navigable neutral COREX contracts.
- Preconditions: T01-T04 accepted.
- Conservative write scope: normalization/serializer tests, guides/examples,
  requirement/traceability docs, affected maps/indexes, plan/ledger.
- Deliverables: load regressions; `REQ-UI-067`, `REQ-GRAPH-023`,
  `REQ-QA-056`; amended `REQ-NODE-050`; migration guidance; map/index updates.
- Verification: persistence/docs tests, traceability, links, maps, indexes.
- Non-goals: QA matrix and schema migration.
- Packetization notes: `P05 Compatibility and Documentation`.

### T06 Independent acceptance

- Goal: independently prove completeness, scope, and recurrence prevention.
- Preconditions: T01-T05 implemented and writer idle.
- Conservative write scope: reviewers read-only; fixes return to the original
  writer; orchestrator updates ledger/plan status only after acceptance.
- Deliverables: whole-diff review, focused/fast evidence, desktop smoke,
  accepted ledger.
- Verification: commands below.
- Non-goals: publication or unrelated cleanup.
- Packetization notes: `P06 Independent Acceptance`.

## Work Packet Conversion Map

No packet manifests are created unless separately requested. If later needed,
P00-P06 map one-to-one to T00-T06. Implementation tasks are serial; final
read-only static review and verification may run concurrently after the writer
stops.

## Test Plan

Focused contract and metadata lane:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_data_type_catalog.py tests/test_core_value_types.py tests/test_graph_type_enforcement.py tests/test_registry_validation.py tests/test_corex_type_conformance.py tests/test_fem_contracts.py tests/test_plot_node_contracts.py tests/test_integrations_track_f.py --ignore=venv -q
```

Focused authoring/projection lane:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_plugin_declaration.py tests/test_python_script_declaration.py tests/test_library_projection.py tests/test_quick_insert_projection.py tests/test_workspace_drop_connect_controller.py --ignore=venv -q
```

Focused QML/shell lane:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/graph_surface/pointer_and_modal_suite.py tests/main_window_shell/drop_connect_and_workflow_io.py -k "quick_insert or wire_drag or connection_quick_insert" --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

Documentation/navigation and final shared-infrastructure gate:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output
```

Run Ruff on changed Python files and `git diff --check`. Do not run unrelated
catalogue generation or targeted suites.

Mandatory desktop smoke uses
`.\venv\Scripts\python.exe -m ea_node_editor.bootstrap` and proves:

1. Geometry Group blank Quick Insert shows the precise Model Viewer match and
   omits broad rows from the reported screenshot.
2. Searching a broad pass-through reveals it with `Broad data match` and
   inserts the correctly oriented edge.
3. Reverse drag from Model Viewer Scene shows precise geometry producers.
4. Python Script Any output leaves a blank, open searchable overlay and reveals
   a searched typed consumer as `Checked at runtime`.
5. Keyboard, mouse, focus, Escape, Enter, and overlay placement still work.

Completion cannot be claimed without the desktop smoke or an explicit record
that display-attached acceptance remains outstanding.

## Assumptions

- Blank Quick Insert hides broad/runtime matches; explicit search reveals them.
- Repo-owned/public authoring fails closed. Unrelated metadata, generation,
  catalogues, fixtures, deletion, and type expansion are excluded.
- Assignable, convertible, and runtime-check relations remain graph-legal.
- No runtime-wire coloring or insertion rollback is added.
- Current project normalization may prune newly invalid edges in memory and
  mark the workspace dirty; it never writes the file until save.
- COREX is unreleased, so omitted `value_type` receives no compatibility shim.
- The plan and ledger are the only new orchestration artifacts.
- No commit or push occurs without a separate explicit request.

## Orchestration and resume rule

The root agent remains orchestrator. One implementation subagent owns T01-T05
serially. The orchestrator inspects each diff/evidence before advancing. After
T05, one independent read-only reviewer and one verification subagent may run
in parallel. Findings return to the original writer.

After any context compaction, handoff, or long pause, stop and fully reread the
latest user request, this entire plan, the entire ledger, and `AGENTS.md`; then
check repository root, branch, HEAD, status, active diff/staged diff, task-owned
untracked files, recorded test evidence, and live agent status. State the
current task, dependencies, next owner, and next proving check before resuming.
