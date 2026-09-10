# Workspace-Scoped Node Files And Data

## Purpose
Use this for workspace-scoped node project files, saved/temporary artifact refs, runtime artifact integrity, transactional staged cleanup, artifact cache metadata, and project data repair.

## Start Here
- `ea_node_editor/common/artifact_refs.py`
- `ea_node_editor/persistence/artifact_store.py`
- `ea_node_editor/persistence/artifact_resolution.py`
- `ea_node_editor/persistence/solution_repository.py`
- `ea_node_editor/persistence/project_codec.py`
- `ea_node_editor/persistence/file_issues.py`
- `ea_node_editor/ui/shell/controllers/project_session_controller.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/project_files_service.py`
- `ea_node_editor/ui/shell/host_presenter.py`
- `ea_node_editor/ui/dialogs/project_files_dialog.py`
- `tests/test_project_artifact_store.py`
- `tests/test_project_artifact_resolution.py`
- `tests/test_project_file_staging.py`

## Notes
- `common/artifact_refs.py` owns only normalized `saved://` and `temp://` syntax. Persistence and execution retain independent ownership of store metadata, integrity, publication, runtime carriers, and durable eligibility.
- The OS sidecar layout is `<project>.data/workspaces/<Workspace [hash]>/nodes/<Node [hash]>/{in,out,tmp}/...`; the workspace hash is stable from `workspace_id`, while the readable prefix follows workspace renames.
- `ProjectArtifactStore.migrate_workspace_artifact_folders(...)` remains for explicit legacy/non-save callers. Production Save/Save As uses `stage_project_save(...)`: legacy metadata is rewritten in the candidate and registered payloads are copied to verified immutable workspace-scoped targets without moving source bytes.
- Raw clipboard/media imports are node-first staged artifacts: `WorkspaceEditController` and composition-injected `MediaPanelActionService` call the public project-session controller, while `ProjectFilesService` writes under the node temp input path, registers MIME/size/hash metadata, and returns the `temp://` ref. The normal copy-on-write save candidate rewrites referenced refs to `saved://`; it never destructively promotes source bytes.
- Project review deck evidence discovery is ref-first: include only referenced managed/staged artifact entries, resolve paths through `ProjectArtifactStore`/`ProjectArtifactResolver`, and treat stale sidecar files or unsupported extensions as warnings instead of slides.
- Artifact-store metadata writes flow through `ProjectData.replace_metadata(...)`: `ProjectFilesService` performs one successful staging publication and `ProjectSessionController` emits its one public success signal. Shell presenters retain dialog/import policy rather than metadata writes; the existing fullscreen Web service continues to use the controller callback supplied by composition.
- Runtime artifact resolution validates catalog identity, active-store descriptor/target ownership, and current file or directory integrity under the trusted store root.
- `ProjectArtifactStore.inspect_durable_artifact(...)` is the callback-free durable inspection route: it accepts only an exact managed runtime ref, compares the owned entry and descriptor fields directly, then runs bounded no-follow content integrity. It never invokes catalog validators or methods on the value.
- Durable solution output may retain a managed `RuntimeArtifactRef` only when the shared runtime-value gate reuses that same trusted resolution/content-integrity path. Staged refs, raw `saved://`/`temp://` strings, private paths, handles, and invalid descriptor/content bindings remain session-only and write no durable result bytes.
- Durable solution files share the project-owned sidecar root under `solutions/v1` but do not enter artifact-store metadata. Project save unions authored document refs with solution-only managed artifact IDs, stages those artifacts first, then validates the candidate solution generation against the completed destination store.
- A typed persisted artifact property accepts either a `RuntimeArtifactRef` carrier or a literal `saved://`/`temp://` string only when the owned managed/staged store entry has the exact `runtime_artifact` descriptor and its concrete type is catalog-compatible with the property's `persistence_data_type_id`. `to_persistent_document()` performs this metadata-only preflight before Save/Save As mutation. Candidate staging converts referenced temp refs to saved refs; source staged and unreferenced bytes remain untouched until after project commit.
- Staged replacement and `discard_staged_entries(...)` / `discard_staged_paths(...)` prevalidate the whole batch before mutation or deletion. Reject absolute hints, traversal, symlink/reparse/special targets, managed paths, and tracked overlaps; safe file/directory/missing targets preserve the unsaved staging root.
- Cleanup remains best effort after prevalidation: a locked file can leave untracked residue, and a same-user post-`lstat` path-swap window remains. Closing that window requires Windows handle-relative deletion rather than path-based removal.
## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_project_artifact_store.py tests/test_project_file_staging.py tests/test_typed_runtime_values.py tests/test_architecture_boundaries.py --ignore=venv -q
```

## Breadcrumbs
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [Project Session, Project Files, And Node Files](project_session_files_managed_artifacts.md)

## Update Triggers
Update when artifact refs/integrity, typed persisted-artifact descriptor ownership, staged replacement/discard safety, node-owned files, project files dialog, project review deck evidence discovery, temporary artifacts, or artifact tests change.

## 2026-07-11 Performance Ownership

- `ProjectArtifactStore` early exits only when the store is empty or completely workspace-scoped. Any mixed legacy ownership continues through the existing lookup and migration path.
