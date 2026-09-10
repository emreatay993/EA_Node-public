# Persistence, Documents, Artifacts, And Migrations

## Purpose
Use this for `.cxproj` documents, serializers, migrations, workspace-scoped project files, artifact stores, and session persistence.

## Start Here
- `ea_node_editor/persistence/serializer.py`
- `ea_node_editor/persistence/project_codec.py`
- `ea_node_editor/persistence/migration.py`
- `ea_node_editor/common/artifact_refs.py`
- `ea_node_editor/persistence/artifact_store.py`
- `ea_node_editor/persistence/artifact_resolution.py`
- `ea_node_editor/persistence/solution_repository.py`
- `ea_node_editor/execution/solution_backend.py`
- `ea_node_editor/execution/project_solution.py`
- `ea_node_editor/persistence/session_store.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`

## Boundaries
- Keep document conversion and legacy-envelope handling in persistence.
- Keep runtime snapshot and worker code independent of persistence internals.
- Route workspace-scoped `in`/`out`/`tmp` files through the artifact store and resolution helpers.
- Keep `saved://`/`temp://` parsing in the dependency-light common owner; persistence owns store metadata, resolution, publication, and cleanup rather than the reference grammar.
- Persistent `ImageValue` properties externalize to immutable content-addressed PNG sidecars only at save time; an existing digest target is reused only after exact-byte verification and is never replaced.
- Save and Save As use `ProjectArtifactStore.stage_project_save(...)`, `stage_project_images(...)`, and `JsonProjectSerializer.stage_document(...)` copy-on-write paths. Source/staged bytes and committed immutable targets are not moved, deleted, or overwritten before `.cxproj` publication; no product-specific importer owns a special promotion path.
- Keep protected properties encrypted and reject unresolved add-ons before final writes.
- Persist Python Script source and authored decorator settings as ordinary node
  properties; resolve the declaration from source instead of storing a second manifest.
- Persist `media.panel` authored properties and exact per-instance Source exposure through the normal node document path. The removed pre-cutover media identities are unknown types with no alias or migration; current project/fragment/history paths preserve serialized exposure without consulting app preferences.
- `solution_repository.py` is the persistence-only concrete implementation of `execution/solution_backend.py` and `execution/project_solution.py`; it never imports `SolutionStore` or session algorithms. Its schema-1 sidecar is `<project-stem>.data/solutions/v1`: bind reads only the committed manifest set, lookup reads one node manifest and record, and payload resolution structurally decodes one result blob without catalog callbacks before the execution-owned durable gate checks types. Logical IDs are full tagged SHA-256 path keys; immutable no-clobber writes publish blob, record, node manifest, then manifest set. Build, validate, reachability, and active-prune protection share one aggregate-bound generation inspector.
- `SolutionRepositoryFactory` implements the execution-owned project-save ports: conservatively estimate the complete active generation plus worst-case supplemental blobs/records/manifests, merge validated active data with captured durable-maximum records, filter removed owners, validate destination artifacts, and build a complete candidate while accounting every newly published solution byte. The fresh postcommit open returns the only retained backend candidate. Bounded GC merges exact candidates with a new filesystem scan when the prior scan was incomplete and protects generation ID/digest pairs after adoption.
- Project install/new/open resets the execution runtime and then binds the decoded `metadata.solution_store` pointer before replacing the graph model. Missing, malformed, unsupported, corrupt, or unsafe cache metadata preserves authored data and installs one session-only result; persistence never becomes a scheduler owner.

## Focused Tests
- `tests/test_serializer.py`
- `tests/test_serializer_schema_migration.py`
- `tests/test_project_save_as_flow.py`
- `tests/test_project_artifact_store.py`
- `tests/test_project_session_controller_unit.py`
- `tests/test_solution_repository.py`
- `tests/test_solution_backend.py`
- `tests/test_project_solution.py`
- `tests/test_media_panel_creation_preferences.py`
- `tests/serializer/round_trip_cases.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_solution_backend.py tests/test_project_solution.py tests/test_solution_repository.py tests/test_serializer.py tests/test_project_artifact_store.py -q
```
