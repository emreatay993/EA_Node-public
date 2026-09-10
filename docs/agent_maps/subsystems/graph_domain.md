# Graph Domain, Mutation, Transforms, And Hierarchy

## Purpose
Use this for graph data structures, invariants, mutation services, transforms, hierarchy, ports, and comment geometry.

## Start Here
- `ea_node_editor/graph/model.py` for `GraphModel` and private graph record writers.
- `ea_node_editor/graph/project_state.py` for `ProjectData`.
- `ea_node_editor/graph/workspace_state.py` for `WorkspaceData`, `WorkspaceSnapshot`, and `ViewState`.
- `ea_node_editor/graph/records.py` for `NodeInstance` and `EdgeInstance`.
- `ea_node_editor/graph/record_payloads.py` for node/edge mapping codecs.
- `ea_node_editor/graph/fragment_payloads.py` for clipboard/fragment payload normalization and validation.
- `ea_node_editor/graph/invariant_kernel.py` for graph-local edge compatibility, exposed-port, capacity, and registry edge checks.
- `ea_node_editor/graph/registry_normalization.py` for project/workspace normalization against the active node registry.
- `ea_node_editor/graph/registry_compatibility.py` for read-only open-session registry replacement checks.
- `ea_node_editor/graph/property_validation.py` for saved/default property validation shared by reload safety and Python Script Apply.
- `ea_node_editor/graph/validated_mutation.py` for registry-backed node, edge, endpoint reassignment, Python Script Apply, dynamic-port insert/remove/rename, property, parent, exposed-port, and view-filter mutations.
- `ea_node_editor/graph/record_mutation_ops.py` for record-level graph edits that intentionally use private `GraphModel` record writers.
- `ea_node_editor/graph/workspace_view_ops.py` for workspace view lifecycle and camera-state mutations.
- `ea_node_editor/graph/group_backdrop_mutation_ops.py` for group-backdrop wrapping transactions.
- `ea_node_editor/graph/ids.py` for generated graph/project/workspace/view IDs.
- `ea_node_editor/graph/effective_ports.py`
- `ea_node_editor/graph/hierarchy.py`
- `ea_node_editor/graph/transforms.py`
- `ea_node_editor/graph/transform_layout_ops.py`
- `ea_node_editor/graph/transform_fragment_ops.py`
- `ea_node_editor/graph/transform_grouping_ops.py`
- `ea_node_editor/graph/group_backdrop_geometry.py`

## Do Not Start Here
- UI bridge code when the invariant belongs in graph.
- Public raw-write helpers; use graph-owned mutation paths.

## Common Changes
- Preserve graph independence from UI and persistence implementation details.
- Registry replacement uses `check_registry_compatibility(...)` as a read-only reload-safety gate; it must never call destructive registry normalization. It checks every open workspace, effective port, incident edge, saved/default property, persistence/sensitivity field, and candidate-catalog carrier while preserving project/workspace revisions and dirty state.
- Import graph state from the focused owner modules instead of using `ea_node_editor.graph.model` as a catch-all; `graph/model.py` owns `GraphModel` only.
- Import graph normalization behavior from the focused owner modules; the retired `graph/normalization.py` path is not an internal compatibility surface.
- Use focused graph mutation modules and private model record writers consistently; `WorkspaceMutationService` is retired.
- Parent topology is a graph-domain invariant. Use `hierarchy.py` parent helpers through validated mutation, private record writers, workspace sanitization, and fragment insertion so self-parents, missing parents, and parent cycles do not enter workspace state.
- `EdgeInstance.enabled` and `input_order` are durable graph state. Normal data drops validate first and atomically replace every edge at the target input; Shift-drop appends in persisted order; exact duplicates are no-ops. Disabled edges stay connected, selectable, ordered, serialized, and undoable while contributing no dependency or value.
- Endpoint rewiring is graph-owned and atomic in `ValidatedGraphMutation.rewire_edges`: move or disconnect an ordered existing-edge batch while preserving each moved edge's identity, state, metadata, and unaffected ordering. A copy is accepted only for one selected edge and creates one new edge while preserving the original. `request_rewire_edges(...)` owns the one-step history boundary; replacement/append does not compose public remove-plus-add calls.
- Active input defaults are spec-declared and stored only in `NodeInstance.properties`; graph records carry no active-port lock or second default state. `ViewState.hide_optional_ports` remains view-local, while `hide_locked_ports` is retired.
- `NodeRegistry.data_types.compatibility(...)` is the single semantic data-port authority. `effective_ports.port_compatibility(...)` returns its structured result plus kind/flow reasons; `ports_compatible(...)` is only the Boolean adapter. The full target primary/accepted union chooses exact assignment, parent/interface assignment, direct conversion, runtime check, first unresolved, then incompatible, retaining declaration-order ties. Data edges still accept `assignable`, `convertible`, and `runtime_check`; they reject `incompatible` and `unresolved`. The graph never performs conversion. Flow ports bypass semantic typing after the structural kind check. Derived subnode/grouping ports preserve the union and exact type-ID casing.
- Current-registry load normalization prunes newly incompatible edges in memory and marks the workspace dirty without writing the source file. `tests/serializer/round_trip_cases.py` proves Geometry Group-to-File Write pruning while JsonValue-to-File Write, Force-to-ILoad, and intentional Any edges remain; explicit save alone updates disk.
- Registry-backed add, endpoint rewire, edge re-enable, dynamic-output edits, semantic property changes, and fragment insertion preflight resolved catalog IDs before writing. `GraphInteractions.rewire_edges(...)` also runs port-availability preflight for every proposed new connection before it reaches graph mutation. Fragment preflight covers every resolved data port, including edge-free dynamic ports; flow ports are not catalog-validated as data. Bulk edge-enable preflights the whole requested batch against a temporary edge view before changing records or history. Failed mutations leave graph state, fan-in order, revision, and history unchanged. Semantic port changes prune only newly invalid incident edges; registry normalization and registry-backed compilation prune incompatible or unresolved edges.
- `NodeInstance.port_modifiers` stores sparse per-port Graft/Flatten/Simplify/Reverse/Clean state and `principal_input_port_id` stores one mutually exclusive eligible input. Route these, edge Enable, and generic dynamic-port insert/remove/rename through validated record mutation/history. Dynamic mutations alone write ordered backing properties: they preflight node-owned resolvers and key callbacks, preserve unchanged stable keys and state, and prune removed, structurally renamed, or incompatible keys with incident wires and sparse per-port state. Direct backing-property writes are rejected; label rename preserves the stable key and wires.
- `ValidatedGraphMutation.apply_python_script(...)` owns one candidate-first Apply action for `core.python_script`. Resolve the source before writing, then reconcile ordinary settings, resolved ports, per-port state, wires, and `expanded_settings_group_ids` together. A failed parse or validation leaves the existing applied node untouched; one successful Apply is one undo/redo entry.
- Source-backed dynamic groups preflight their property editor against the candidate resolved spec. Python Script handle edits commit through the same atomic Apply action; generic backing-property writes remain restricted to validated dynamic mutations.
- `NodeInstance.expanded_settings_group_ids` stores ordered per-node expansion state for spec-declared named settings groups. Registry normalization removes unknown IDs and restores declaration order; node mappings and graph fragments preserve the tuple. Presentation moves grouped input anchors without changing their real port identities or edges.
- `NodeInstance.locked` is graph-owned authored state for `passive.*` canvas objects. Record mutation/history owns changes; node mappings and graph fragments preserve it. It is separate from the removed active-port lock state and the missing-add-on `locked_state` payload.
- `NodeInstance.visual_style` is passive-only authored state. Validated insertion and fragment paste clear it for registered active and `compile_only` types; unresolved types retain it so unavailable nodes can round-trip until their real type is known.
- Node links are ordered durable node records. Use graph-owned upsert/remove/move mutation operations so ordering, history replay, persistence, and node payload projection stay aligned. Node links keep string `target` while carrying explicit `target_workspace_id` and `target_node_id` for cross-workspace jumps.
- Optimization Parameter/Response Setup-to-Pool relationships are exact semantic roles on those same persisted node links. They remain ordinary graph state and mutation/history records; runtime ordering is a downstream execution projection, not a second graph relationship store.
- `WorkspaceData.mutation_revision` is runtime-only state for history snapshot memoing. Bump it from graph/view mutation boundaries and snapshot restore paths; keep it out of `WorkspaceSnapshot` equality and persistence documents.
- `ProjectData.project_document_revision` is runtime-only state for autosave document-epoch gating. Bump it for project metadata, workspace order, active-workspace, and workspace create/duplicate/close changes; combine it with each workspace's document epoch part instead of reusing run-state epochs.
- `RegistryValidationPassMemo` is scoped to one registry-validation pass. Use it from prune/validation loops to reuse resolved node views, effective-port lookups, and edge tuples; invalidate the edge tuple immediately when a prune pass removes an edge.
- Keep transform and hierarchy tests focused before running broader UI gates.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_transform_layout_ops.py tests/test_workspace_manager.py tests/test_port_availability.py tests/test_default_port_values.py tests/test_group_backdrop_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m unittest tests.graph_track_b.scene_model_graph_model_suite -q
.\venv\Scripts\python.exe -m pytest tests/test_dataflow_graph_persistence.py tests/test_data_tree_ui.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_type_enforcement.py tests/test_data_type_catalog.py tests/test_registry_validation.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_registry_compatibility.py tests/test_python_script_declaration.py --ignore=venv -q
```

## Breadcrumbs
- [Nested Node Categories, Subnodes, And Grouping](../feature_routes/nested_node_categories_subnodes_grouping.md)
- [Group Backdrops, Peek, And Membership](../feature_routes/group_backdrops_peek_membership.md)
- [Clipboard, Undo, Redo, And Mutation History](../feature_routes/clipboard_undo_redo_mutation_history.md)
- [Plotter Nodes](../feature_routes/plotter_nodes.md)
- [Durable Node Linking](../feature_routes/durable_node_linking.md)

## Update Triggers
Update when domain invariants, ordered/enabled edge state, data-port modifiers or Principal, dynamic-port declarations/resolution/mutations, registry normalization, validated mutation, record mutation ops, durable or semantic node link records, workspace view mutation ops, fragment payloads, mutation boundaries, hierarchy rules, transforms, effective-port logic, graph state module ownership, or project data ownership changes.

## 2026-07-11 Performance Ownership

- Registry normalization owns one invocation-scoped `GraphInvariantKernel` and `RegistryValidationPassMemo`; prune-time edge removal invalidates the memo immediately. `tests/test_registry_validation.py` owns reuse and invalidation parity.
