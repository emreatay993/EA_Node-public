# Project Session, Project Files, And Node Files


## Start Here
- `ea_node_editor/ui/shell/controllers/project_session_controller.py`
- `ea_node_editor/ui/shell/controllers/project_session_services.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
- `ea_node_editor/ui/dialogs/project_files_dialog.py`
- `ea_node_editor/ui/shell/host_presenter.py`
- `ea_node_editor/persistence/artifact_store.py`
- `ea_node_editor/persistence/artifact_resolution.py`
- `ea_node_editor/workspace/`
- `tests/test_project_session_controller_unit.py`
- `tests/test_project_file_staging.py`

## Notes
- `ProjectFilesService` registers imported file/byte/notebook payloads through the existing Path artifact registration helper, including runtime schema, format, size, and digest descriptors. Authored node properties remain exact `temp://` / `saved://` references. `RuntimeArtifactService.materialize_authored_properties` is the explicit execution boundary for registered canonical staged refs; runtime outputs and raw path resolution retain their strict typed-carrier rules. `tests/test_canvas_import_runtime.py` proves real process execution before save, after reopen, and after Save As, including negative integrity cases.
- Startup session restore keeps the active project empty instead of reopening the saved `last_session.json` project path; `ProjectSessionLifecycleService.restore_session()` still keeps that path in Recent Projects and uses it only as an autosave comparison/recovery baseline.
- Project Save/Save As calls `ProjectArtifactStore.stage_project_save(...)`. Legacy `nodes/<node-folder>/...` metadata is rewritten into workspace-scoped candidate metadata while bytes are copied to immutable destination targets; production saves never mutate or move source payloads in place.
- `ProjectDocumentIOService.save_project(...)` and `save_project_as(...)` share one non-reentrant guard and capture both a document fingerprint/epoch token and an execution-owned solution snapshot token. Persistent preflight validates typed artifact refs before copy-on-write artifact, solution, image, and canonical project staging; immediately before commit and adoption the tokens and destination identities are rechecked.
- Workspace rename updates the readable workspace folder prefix through `WorkspaceNavigationController.rename_workspace_by_id(...)` and `ProjectArtifactStore.rename_workspace_artifact_folder(...)`; the hash suffix remains stable.
- Staged artifact resolution honors an explicit session `staging_root` before falling back to a saved project sidecar, and staged `slot` metadata is preserved in the managed candidate metadata.
- Media, tabular, and web-page local HTML import paths use `ShellHostPresenter` only for native dialogs and source-import policy. It delegates selected-file staging to `ProjectSessionController`, whose `ProjectFilesService` writes and registers the staged `temp://` payload; the final persistent-document candidate rewrites only referenced refs to `saved://` values.
- Candidate-only `rewrite_project_artifact_refs(...)` converts nested temp literals and typed artifact carriers to saved strings while retaining descriptors. `.cxproj` is the sole commit point: bound Save uses replace-current, first Save/distinct Save As uses atomic create-new, and publication state is recorded before separate committed-byte verification.
- Postcommit verification reconstructs the destination store, compares exact ID/path/kind/size/SHA facts for document refs union solution-only artifact IDs, and freshly opens/fully validates the committed solution generation. The final source-token recheck follows all I/O; runtime adoption and live properties/metadata/path changes are then no-I/O.
- A published or publication-uncertain postcommit verification/adoption failure is `committed_not_adopted`: destination disk data may already be authoritative, but source live metadata/properties/path/binding/dirty/autosave state remain. Cleanup is bounded and best effort only after successful adoption, with previous/new protection on the first pass and retry entries retained on exception/partial work.
- Clipboard/media payloads from `WorkspaceEditController` and composition-injected `MediaPanelActionService` call `ProjectSessionController.stage_node_artifact_bytes(...)` directly. The composition-injected Jupyter bridge calls `create_blank_notebook_artifact(...)` directly. Each resulting node stores a `temp://` ref; Save/Save As rewrites only candidate-document refs during copy-on-write publication.
- Project review deck export must enumerate evidence from project refs and artifact-store metadata, not by raw sidecar folder scanning. `ea_node_editor/ui/project_review_deck.py` builds the reusable slide plan from referenced `saved://` / `temp://` entries, then verifies resolved paths before image/PDF evidence is embedded.
- `examples/project_review_deck_airworthiness/rotor_llp_review_showcase.cxproj` is the committed Project Review Deck showcase for ref-first managed evidence, Media Panel PDF-mode authored-page rendering, web-preview artifacts, explicit invalid/stale media warnings, and optional PowerPoint template export.
- `ProjectSessionLifecycleService.persist_session(project_doc)` honors caller-supplied runtime documents, snapshots them with `ProjectDocumentSnapshot.from_owned_document(...)`, and keeps the recent-session payload metadata-only; Save/Save As should keep using their normal persistent-document write path.
- Workflow Settings reads the app-default Python executable separately from project `workflow_settings`. Cancel changes neither store. Accepted changes persist the app preference first; app-store failure leaves live project/session state untouched. After success, `ProjectDocumentIOService` updates project metadata and invokes existing best-effort `persist_session()` once. That lifecycle method may swallow its store failure, so this path adds no cross-store transaction, rollback, strict persistence variant, or post-accept warning. Persistent-project tests use distinct app/workflow sentinels to prove the app path never enters `to_persistent_document()` output.
- Autosave ticks sync active view and script-editor metadata, compare the runtime-only project document epoch, and skip `serializer.to_document(...)` plus `SessionAutosaveStore.autosave_if_changed(...)` when the epoch and last fingerprint are unchanged.
- Manual Save and Save As snapshot the current `ScriptEditorModel` state immediately before persistent document conversion. Project open restores through the existing script-editor panel adapter; autosave, session, and close synchronization stay on `ProjectSessionLifecycleService._sync_session_state()`.
- Artifact-store, workflow, passive-style preset, and script-editor metadata writers should call `ProjectData.replace_metadata(...)` so the autosave epoch changes without hashing full project metadata on idle ticks.
- `ProjectFilesService` owns synchronous staged payload target creation, file/byte/notebook write, staged-entry registration, and in-memory artifact-store metadata publication. Its public controller wrappers emit `project_meta_changed` exactly once after a successful staging result; there is no private setter alias. `ShellHostPresenter` retains only dialogs and source-import policy.
- `ProjectDocumentIOService` retains guarded copy-on-write Save/Save As staging, canonical `.cxproj` publication, raw reopen/verification, no-I/O adoption, and post-success cleanup. Do not reintroduce destructive staged-payload promotion.
- A fullscreen Web editor creates one existing `WebSurfaceArtifactService` per open from composition-supplied node identity and the authoritative current store. Artifact publication uses the public controller boundary only, advances metadata once, and performs no Save/Save As, serializer, or project-file publication.
- Project install/open/new flows reset `ViewerHostService` before `ViewerSessionBridge.project_loaded(...)` reseeds project viewer projections; this clears native overlay bindings, cached previews, and viewer view state before fixed `(workspace_id, node_id)` viewer keys are reused.
- The same install seam calls `CorexRuntime.reset_project_session(project_id, project_path)`, then `bind_project_solution_store(project_id, project_path, metadata.solution_store)`, before model replacement. Valid metadata supplies the stored namespace and committed generation; saved metadata-absent projects use `project_id`, while unsaved projects keep one random session namespace. Invalid cache state is one sanitized session-only fallback and never blocks authored install. Replacement clears records/payloads/preparations/runs, closes the old backend without deleting sidecar content, and publishes the existing removal notifications.
## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_project_file_staging.py tests/test_project_session_controller_unit.py tests/test_project_artifact_store.py tests/test_jupyter_create_blank.py tests/test_architecture_boundaries.py --ignore=venv -q
```

## Breadcrumbs
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [Workspace-Scoped Node Files And Data](managed_artifacts_project_data.md)


## 2026-07-11 Performance Ownership

- Empty or fully workspace-scoped stores skip artifact-owner/migration scans. Autosave consumes owned non-mutating mappings, one JSON encoding, and SHA-256 fingerprints; mixed legacy stores retain migration behavior.
