# Serialization, Migration, And Legacy Rejection

## Purpose
Use this for `.cxproj` serialization, coordinated format cutovers, legacy rejection, document fingerprints, and persistence package imports.

## Start Here
- `ea_node_editor/persistence/serializer.py`
- `ea_node_editor/persistence/project_codec.py`
- `ea_node_editor/persistence/migration.py`
- `ea_node_editor/common/payload_tools.py`
- `ea_node_editor/graph/project_state.py`
- `ea_node_editor/graph/workspace_state.py`
- `ea_node_editor/graph/record_payloads.py`
- `tests/test_serializer.py`
- `tests/test_serializer_schema_migration.py`

## Notes
- Durable node links are part of the node payload codec path. Documents without link payloads should load with `links: []`, and serializer tests should cover round-trip preservation.
- Node-link payloads stay flat: `target` remains a string, while node links emit `target_node_id` and `target_workspace_id`. Legacy node links that only contain `target` should load with `target_node_id = target` and `target_workspace_id` set to the owning workspace.
- Deprecated plot-session layout data is accepted on old documents but stripped during migration/save; do not re-add `plot_session_layout` to the current schema.
- The dataflow cutover writes `.cxproj` v5, fragment v2, `.cxwf` v2, global custom-workflow store v2, and app preferences v6. Surviving legacy data edges default enabled and derive `input_order` from serialized order; existing data ports default to Item access with no modifiers or Principal.
- T07 retains `.cxproj` schema 5: projects do not persist type definitions or port schemas. `to_persistent_document()` reconstructs the artifact store from project metadata and preflights typed `RuntimeArtifactRef` carriers plus literal `saved://`/`temp://` properties against owned entries and their exact `runtime_artifact` descriptors before Save/Save As mutation. Store-less decode preserves those literals as strings so a later save revalidates them; successful staged promotion rewrites both carriers and nested temp literals to saved strings. Final writes run the document-wide persistence guard across nested values, mapping keys, and metadata, rejecting remaining temp refs, malformed/unowned saved refs, unauthorized typed markers, live handles, raw DataTrees, bytes, and native objects without reading artifact content or materializing a runtime value.
- `metadata.solution_store` remains an opaque metadata extra to `JsonProjectCodec`; schema interpretation belongs only to the execution-injected solution repository factory. `JsonProjectSerializer.stage_document(...)` externalizes images, writes/fsyncs one same-directory canonical temp, and returns its raw bytes/digest. `commit_staged_document(...)` performs only prevalidation plus explicit `replace_current`/atomic `create_new` publication and returns strict not-published/published/publication-uncertain state; `verify_committed_document(...)` is the separate canonical-byte check, and discard is idempotent. Missing/unsupported/corrupt solution metadata still survives authored decode and falls back session-only until the next successful save writes a validated fresh pointer.
- `visual_style` is passive-node-only: current active-scene serialization omits it, schema-5 load strips it from registered active and `compile_only` nodes, and unresolved types retain it until their real type is known.
- Current `media.panel` nodes serialize their authored renderer-setting superset plus exact Source exposure. App preference v8 affects future blank creation only. Projects containing removed media identities fail through normal unknown-type validation; add no alias, migration, or authored-source fallback.
- Migration deletes known control edges, the five retired routing/status nodes, control-kind subnode pins, shell mappings, stale control-port metadata, and control-row state. Nested workflows/fragments migrate in the same pass; workflows left empty are removed and reported.
- Opening a migrated project produces one sorted report and marks the project dirty without overwriting its source before Save. A legacy file containing unresolved add-ons is rejected instead of entering a best-effort recovery path.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_serializer.py tests/test_persistence_package_imports.py -k "solution_store or solution_repository" -q
.\venv\Scripts\python.exe -m pytest tests/test_dataflow_graph_persistence.py tests/test_data_tree_ui.py --ignore=venv -q
```

## Breadcrumbs
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [Managed Artifacts And Project Data](managed_artifacts_project_data.md)
- [Plotter Nodes](plotter_nodes.md)
- [Durable Node Linking](durable_node_linking.md)

## Update Triggers
Update when project/fragment/workflow/preferences versions, final persistent-document validation, durable node link payloads, dataflow migration/reporting rules, graph serialization data ownership, unresolved-add-on rejection, or serializer tests change.

## 2026-07-11 Performance Ownership

- Serializer-owned documents use non-mutating owned mappings and one JSON encoding; external mappings keep defensive-copy behavior. Fingerprints are lowercase fixed-length SHA-256 and older values may safely mismatch once and be rewritten.
