# Plan: COREX Application-Default External Python Runtime

Status: **COMPLETED — T01–T05 ACCEPTED**

## Summary

- Objective: add one app-persistent default Python executable that COREX shell runs may use when the current project has no workflow-level Python override, while reusing the existing external Python worker and preserving the current built-in process-isolated runtime as the final fallback.
- Current repository capability: COREX already supports a project-persistent, workflow-wide external interpreter through `workflow_settings.environment.python_path`. `build_runtime_snapshot(...)` carries the project metadata into the run snapshot, `workflow_python_path_from_snapshot(...)` extracts its normalized text, `ExecutionBackendClient.start_run(...)` selects `ExternalPythonExecutionClient`, and that client launches the selected interpreter with `-m ea_node_editor.execution.stdio_worker` after a bounded import preflight for that module. Registry, catalog, plugin, and protocol agreement remain owned by the existing startup handshake after the worker launches.
- Current proof anchor: `tests/test_execution_client.py::ProcessExecutionClientTests::test_execution_backend_client_uses_workflow_python_executable_for_external_worker` executes a Python Script node through the configured project interpreter and observes its `sys.executable`. The orchestrator freshly reran this exact node after the first draft and recorded `1 passed in 6.00s`. This proves the current project-override capability only; it is not implementation or acceptance proof for the planned app default.
- Delivered capability: app preferences now own `python_runtime.default_executable`; an empty project override inherits it, while both paths blank retain the built-in process-isolated runtime.
- Runtime scope: an external interpreter hosts the complete workflow worker and therefore runs the entire workflow, not only Python Script nodes. A user-managed interpreter must import `ea_node_editor.execution.stdio_worker` and all dependencies required by nodes in that workflow; it may still fail the existing registry/catalog/protocol startup handshake when its COREX installation is incompatible.
- Security boundary: this is trusted local code execution, not a sandbox, environment manager, permission boundary, or remote-execution feature.
- Persistence boundary: the app default remains in app preferences. It must never be copied into project metadata, `RuntimeSnapshot`, `.cxproj`, node properties, graph records, or persistence migrations.
- V1 intentionally has no per-node interpreter, no plugin-level interpreter, no project-level opt-out from a configured app default, and no PATH lookup. A blank workflow override means inherit the app default; a blank app default means use the built-in runtime. To force the built-in runtime while an app default is configured, the user must clear the app default.
- T01–T05 are complete. Final acceptance recorded `194 passed, 80 subtests` in the focused owners, `3890 passed, 2 skipped` in the fast parallel lane, `224 passed` in the fast serial lane, and clean traceability, link, map, generated-index, privacy, forbidden-owner, and diff checks.

### Repository Navigation Audit Used To Write This Plan

- Route/index entries checked: `subsystems-app-preferences-settings-platform-paths`, `subsystems-execution`, `subsystems-ui-shell`, `subsystems-pyqt-dialogs-panels-theme-editor`, `feature-routes-run-controller-selected-workspace-state`, `feature-routes-graphics-settings-themes-preferences`, `feature-routes-project-session-files-managed-artifacts`, and `testing-shell-isolation-tests` in `docs/agent_route_index.md`.
- Maps consulted: `docs/agent_maps/COVERAGE.md`, `docs/agent_maps/subsystems/app_preferences_settings_platform_paths.md`, `docs/agent_maps/subsystems/execution.md`, `docs/agent_maps/subsystems/ui_shell.md`, `docs/agent_maps/subsystems/pyqt_dialogs_panels_theme_editor.md`, `docs/agent_maps/feature_routes/run_controller_selected_workspace_state.md`, `docs/agent_maps/feature_routes/graphics_settings_themes_preferences.md`, `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`, and `docs/agent_maps/testing/shell_isolation_tests.md`.
- Source candidates verified: `ea_node_editor/settings.py`, `ea_node_editor/app_preferences.py`, `ea_node_editor/common/coercions.py`, `ea_node_editor/execution/python_environment.py`, `ea_node_editor/execution/backends.py`, `ea_node_editor/execution/client.py`, `ea_node_editor/ui/dialogs/workflow_settings_dialog.py`, `ea_node_editor/ui/shell/controllers/app_preferences_controller.py`, `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`, and `ea_node_editor/ui/shell/controllers/run_controller.py`.
- Test candidates verified through source and `docs/source_test_file_index.md`: `tests/test_app_preferences.py`, `tests/test_app_preferences_import_defaults.py`, `tests/test_workflow_settings_dialog.py`, `tests/test_project_session_controller_unit.py`, `tests/test_run_controller_unit.py`, `tests/test_shell_run_controller.py`, and `tests/test_execution_client.py`.
- Broad-search note: one initial exact-anchor search included generated architecture output and was too noisy. All ownership and task decisions below were then confirmed from the bounded maps and exact source/test files above; generated, build, artifact, cache, virtual-environment, worktree-mirror, and package-metadata trees are out of scope.

### Plan Authoring Evidence

- Two independent read-only repository reviews of the first draft completed, covering current execution behavior, worker lifecycle, app/project persistence, run-controller ownership, and test seams. Their supported findings are incorporated directly into the plan below.
- After drafting, the orchestrator freshly ran `tests/test_execution_client.py::ProcessExecutionClientTests::test_execution_backend_client_uses_workflow_python_executable_for_external_worker`; it passed with `1 passed in 6.00s`.
- That test is current baseline evidence for the already-shipped project workflow override. The app-persistent default, dual-scope UI, revised selection flow, and their acceptance checks remain `PLANNED — NO IMPLEMENTATION PROOF`.

### Orchestrator Resume Contract

This subsection is mandatory operating procedure for every implementation session that uses this plan.

1. After any context compaction or fresh-session handoff, the orchestrator must reread this entire plan and the current Task Ledger before delegating, editing, reviewing, or accepting work. It must then inspect `git status --short`, tracked diffs, direct content plus a hash for every untracked plan-owned file, recorded verification evidence from completed tasks, and live agent/task status. Prior chat summaries are hints only; the plan, ledger, checkout, and command evidence are authoritative.
2. The orchestrator must update the durable Task Ledger whenever a task changes owner or status. Every update records the task ID, one owner role, status, satisfied dependencies, exact changed paths, and evidence consisting of command plus result or reviewer finding. A verbal claim, elapsed time, or agent completion message is not proof.
3. Allowed task states are `PLANNED`, `IN_PROGRESS`, `REVIEW`, `BLOCKED`, and `COMPLETE`. A task becomes `IN_PROGRESS` only after all dependencies are `COMPLETE`, its owner and conservative write scope are recorded, and no other live writer overlaps that scope. A task becomes `COMPLETE` only after its deliverables exist, its proving checks pass, and required review findings are resolved.
4. Exploration must finish before edits begin. While any repository explorer is active, the orchestrator and all subagents remain read-only. `P00` must close with verified owners, candidates, and test routes before `T01` starts. If later evidence invalidates ownership, stop edits, return the affected task to `PLANNED` or `BLOCKED`, finish the new read-only exploration, and only then reassign work.
5. One-writer rule: one implementation owner owns `T01` through `T03` sequentially. No other agent may edit source or tests during those tasks. The documentation owner may start `T04` only after the implementation owner has stopped editing and the post-`T03` read-only review is accepted. The same independent reviewer performs `T05` and never edits tracked files.
6. A subagent may edit only when the orchestrator explicitly assigns the whole task, its exact write scope, dependencies, and proving checks, and marks that task `IN_PROGRESS` in the ledger. Exploration and review subagents are read-only. They must not opportunistically repair findings, even when the fix appears trivial.
7. To reassign ownership safely, first wait for or stop the current owner at a message boundary, confirm that it has no running edit/test command, inspect `git status --short`, tracked diffs, and direct content/hashes for untracked files in its scope, record partial deliverables and evidence, then change the ledger owner. Never let the old and new owners edit concurrently, and never split `T01` through `T03` across overlapping writers.
8. After `T03`, assign one independent read-only reviewer to cover both checklists: architecture/data boundaries, exact source-selection precedence, one-pass validation, persistence, and worker-generation reuse; then migrations, all three shell dispatch paths, lifecycle/error cases, and focused test coverage. Findings return to the single implementation owner. The same reviewer rechecks fixes before `T04` starts.
9. After `T04`, the same independent reviewer performs the `T05` final audit against the complete diff. That reviewer may run the listed commands and create only ignored test/verification artifacts; it may not modify tracked files. Any finding returns to the owner of the affected task, and final review restarts against the new diff.
10. The orchestrator owns final synthesis and ledger/status edits only. It must not mark this plan implemented, move or relabel its index entry, or claim release proof until `T05` acceptance is recorded. Plan creation alone is not feature completion.

## Key Changes

- Bump the app-preferences document from version `6` to `7` and add the normalized app-owned section:

  ```json
  {
    "python_runtime": {
      "default_executable": ""
    }
  }
  ```

- Migrate both version `5` and version `6` preference documents to version `7`. Preserve every currently recognized existing preference, retain the existing v5 removal of retired fields through current normalization, discard any forged/preexisting `python_runtime` section in either predecessor version, and initialize the new executable to blank. Versions `1` through `4` keep their current reset-to-default behavior.
- Reuse one path-text normalizer for app preferences and workflow snapshot resolution: trim surrounding whitespace, strip one matching pair of wrapping single or double quotes, and leave empty as empty. Filesystem resolution, executable checks, and COREX import verification remain runtime-start responsibilities.
- Add small `AppPreferencesController` getter/setter methods for the Python-runtime section. The setter uses copy-on-write, persists only normalized app preferences, leaves the cached document unchanged on write failure, and never touches the active project.
- Rework the existing `WorkflowSettingsDialog` Environment page into two unmistakable scopes without creating another settings dialog or framework:
  - `Application Default Python Executable`, with native Browse, `Create / Repair Managed Runtime`, and `Clear Application Default` actions.
  - `Workflow Override`, with native Browse and `Inherit Application Default` actions.
- Keep `WorkflowSettingsDialog.values()` project-only. Add a separate accessor for the app default so `DocumentIOService.show_workflow_settings_dialog()` persists the two scopes to their existing owners and cannot accidentally serialize the app default into `.cxproj`.
- Add one internal `RunController` policy helper and use it identically from `run_workflow()`, `run_selected_nodes()`, and `trigger_node()`. It returns an existing external `execution_backend` policy only when the runtime snapshot has no workflow `python_path` and the app default is non-empty.
- Refactor `ExecutionBackendClient.start_run(...)` into one text-only source-selection pass followed by exactly one filesystem validation of the final non-empty external path. Reuse `ExecutionBackendPolicy`, `ExecutionBackendClient`, `ExternalPythonExecutionClient`, the stdio protocol/worker, managed-runtime installer, bounded worker-module import preflight, startup handshake, and existing generation retirement. Add no process, version probe, compatibility probe, or protocol path.
- Update specifications, traceability, the Python Script guide, and only the ownership maps affected by the implemented behavior.

## Public Interface Changes

### App-Preference Contract

- `APP_PREFERENCES_VERSION` changes from `6` to `7`.
- `DEFAULT_APP_PREFERENCES` gains `python_runtime.default_executable`, default `""`.
- The value is app-persistent JSON and is not project data. A valid project saved while the app default is set must remain byte-for-byte free of that app default unless the user separately authored the same text as the workflow override.
- App-preference normalization accepts only a string `default_executable`. A missing/non-mapping section or `None`, list, mapping, number, boolean, or other non-string value produces blank. Valid v5/v6 migration input never imports a predecessor `python_runtime` value, even when it is a string.

### Effective Runtime Precedence

The runtime is selected once per workflow run using these exact cases:

| Case | Condition | Result |
| --- | --- | --- |
| Explicit process, trusted, or auto | API/headless caller supplies that policy | Honor it and ignore both project and app defaults. If explicit auto resolves to an external backend without a path, fail; do not fill from project or app. |
| Explicit external with path | API/headless caller supplies external policy and `python_executable` | Use that path; ignore project and app defaults. |
| Explicit external without path | API/headless caller supplies external policy without `python_executable` | Preserve the current fallback to the normalized project workflow path. If that is blank, fail; the app default never fills an explicit API/headless external policy. |
| No explicit policy, project override set | Normalized `workflow_settings.environment.python_path` is non-empty | Use the project-wide external Python path. |
| Shell run, project override blank, app default set | `python_runtime.default_executable` is non-empty | `RunController` passes the app path through the existing explicit external-backend policy. |
| No explicit/project/app path | Both stored paths are blank | Use the existing built-in process-isolated runtime. |

- Empty means empty after path-text normalization. COREX does not search `PATH`, run `python`, discover virtual environments, or choose the active terminal interpreter.
- V1 provides no project force-built-in override while an app default exists. `Inherit Application Default` is the only blank workflow state, and the built-in runtime is effective only when both app default and workflow override are blank.
- The app default is a shell default, not an implicit global added inside `ExecutionBackendClient`. API/headless callers retain their current explicit policy authority and current project-snapshot behavior.

### Environment Page Semantics

- `Application Default Python Executable` describes app scope and persists through `AppPreferencesController`.
- `Clear Application Default` clears only the app default. It does not imply that the built-in runtime is effective when a workflow override remains non-empty.
- `Workflow Override` describes project scope and persists through the existing `ProjectSessionMetadata.workflow_settings` path.
- `Inherit Application Default` clears only the workflow override.
- Both executable fields have native file-picker buttons. The picker writes the chosen executable path into its own field and performs no environment creation, package installation, or import probe.
- `Create / Repair Managed Runtime` keeps the existing explicit background action but fills the app-default field on success. It does not set the workflow override.
- Capture project metadata, revision, and document epoch before opening the dialog. Cancelling changes neither store and leaves all three exactly unchanged. On accept, persist the app preference first; only after that succeeds, update live project metadata and invoke the existing `persist_session()` path.
- `persist_session()` is best-effort and currently swallows its own write failures. V1 therefore adds no cross-store transaction, rollback, strict lifecycle-persistence API, or post-accept project-save warning. If that later best-effort write fails, the already-saved app preference and updated live project metadata may remain changed under existing session semantics.
- Help/status text must state all of the following without relying on a tooltip alone:
  - the selected external interpreter runs the entire workflow;
  - a user-managed interpreter must import `ea_node_editor.execution.stdio_worker` and can still fail the existing startup handshake when incompatible;
  - it is trusted local execution, not a sandbox;
  - app-preference changes apply to the next run and do not alter an active run;
  - the current effective choice is workflow override, app default, or built-in.

### Runtime Validation And Errors

- Storage performs text normalization only. Dialog acceptance must not spawn Python, probe packages, install dependencies, create a virtual environment, or mutate the active execution client.
- `ExecutionBackendClient.start_run(...)` first obtains normalized workflow path text, selects/fills the policy under the cases above, and then performs exactly one filesystem validation of the final non-empty external executable. Project selection must not call a validating workflow resolver and then validate the same path again.
- For a new or switched interpreter, the existing bounded preflight proves only `import ea_node_editor.execution.stdio_worker`; it runs before `_prepare_start_run(...)`. A same-path live-worker reuse skips that import probe and does not restart or advance the generation.
- Registry, catalog, plugin, and protocol agreement remains in the existing startup handshake after worker launch. This plan adds no version/protocol/compatibility probe and no protocol field. Managed-runtime preparation retains its stronger pinned-package installation and verification.
- Invalid text, filesystem validation failure, or worker-module import failure returns no run ID and emits an actionable bounded protocol error before any new stdio worker starts. Error cases include missing path, directory instead of file, non-executable file, launch failure, import-check timeout, and inability to import `ea_node_editor.execution.stdio_worker`.
- An invalid or import-incompatible replacement path launches no new worker and leaves any existing external worker and generation unchanged; `_process` is not required to be absent. A valid switch advances the generation only after existing live-viewer replacement guards allow it.
- A later `subprocess.Popen(...)` failure occurs after path/import preflight and run reservation. It must release the reserved run, install/accept no new physical or catalog generation, and emit a bounded actionable launch error. On cold start no worker remains. During a switch, existing behavior may already have retired the prior worker before `Popen`, so v1 does not promise preservation or add process rollback; the next valid run must start cleanly without an active-run or half-generation residue.
- Import failure tells the user that the environment must import the COREX stdio worker and points to `Create / Repair Managed Runtime`; it must not trigger automatic installation. A later startup-handshake mismatch uses the existing bounded mismatch behavior.
- The existing external worker is selected for the whole `StartRunCommand`. Python Script nodes can observe the selected `sys.executable`, but no node receives an interpreter field or can select another runtime.

### Explicit Non-Interfaces

- No new process protocol, worker executable, worker command/event field, runtime snapshot field, execution backend ID, environment manager, package installer, dependency, settings framework, or dialog.
- No graph, node, port, property, plugin, decorator, package, project-schema, or `.cxproj` migration change.
- No per-node, per-plugin, per-package, per-workspace, or temporary run-only interpreter selector.
- No remote execution, isolation claim, sandbox, environment discovery, PATH fallback, dependency solver, or automatic compatibility repair.

## Execution Tasks

### Task Ledger

The ledger records the completed implementation and acceptance evidence under the Orchestrator Resume Contract.

| ID | Status | Owner role | Dependencies | Conservative write scope | Deliverables | Proving check / acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| `P00` | `COMPLETE` | Orchestrator + `/root/corex_external_python_explorer` | none | This plan and read-only repository inspection only | Owners, dirty paths, shared-normalizer gap, exact test anchors, and no-overlap assignment reconfirmed | Explorer inspected plan hash `475632A7CF3E4C5882A4864DD9C5BE83436B1CF573DE80547007DC450FAD01DC`; unrelated plan hash `F1709CD27CDD97141E354AB0644B3602F8EA43EBEFBB294B0C5FA4578C6788F2` unchanged; no source/test drift |
| `T01` | `COMPLETE` | `/root/external_python_implementation_owner` | `P00` complete | Preference constants/normalization/controller plus focused tests only | App preferences v7, locked v5/v6 migration, string-only normalization, copy-on-write getter/setter | `56 passed, 24 subtests passed`; workflow resolver `1 passed, 50 deselected`; scoped `git diff --check` passed |
| `T02` | `COMPLETE` | `/root/external_python_implementation_owner` | `T01` complete | Existing Workflow Settings dialog, tooltip data, document IO/host protocol owners, focused tests | Dual-scope UI, native pickers, clear/inherit actions, exact cancel/app-write-failure state, app-first accepted write order | Offscreen dialog/project suite `27 passed`; persistent-document sentinel included; scoped `git diff --check` passed |
| `T03` | `COMPLETE` | Implementation `/root/external_python_implementation_owner`; review `/root/external_python_plan_review_execution` | `T02` complete | Python path text/validation, existing execution backend client, run controller, focused tests | Exact selection, single validation, worker reuse/switch/failure behavior implemented and independently accepted | Re-review `PASS` with no findings; targeted reviewer gate `2 passed, 14 subtests`; all recorded implementation gates passed |
| `T04` | `COMPLETE` | `/root/external_python_plan_writer` | `T03` review accepted | Requirements, traceability, Python Script guide, affected maps/coverage, generated route/source-test indexes | Requirements now distinguish app-default non-leakage from the intentional project Workflow Override | Correction touched only `50_EXECUTION_ENGINE.md`; traceability, links, diff check passed; targeted docs tests `110 passed, 15 subtests` |
| `T05` | `COMPLETE` | `/root/external_python_plan_review_execution`; orchestrator closeout | Corrected `T04` complete | No tracked writes by reviewer; ignored verification artifacts only | Final diff, focused regression, fast integration, lifecycle/limitation, privacy, and forbidden-owner acceptance passed | Focused `194 passed, 80 subtests`; fast parallel `3890 passed, 2 skipped, 18 warnings`; fast serial `224 passed`; final reviewer `PASS` with no findings |

### P00 Bootstrap And Exploration Gate

- Goal: establish a clean, current, and non-overlapping implementation start from this plan without changing source, tests, or product documentation.
- Preconditions: this plan exists and is registered under `Active Implementation Plans — No Implementation Proof`; no implementation claim has been made.
- Conservative write scope: this plan's Task Ledger only. All repository discovery is read-only.
- Deliverables:
  - Re-read this entire plan and ledger.
  - Run `git status --short` and classify every existing change by owner. The external-runtime plan and Physical Simulation plan are currently untracked, so do not treat `git diff` as evidence of their content. Preserve the unrelated Physical Simulation plan exactly.
  - Read the external-runtime plan directly and record its SHA-256. Record the Physical Simulation plan SHA-256 before implementation and verify it remains unchanged at each ownership handoff.
  - Reconfirm the route-index/map candidates named in the navigation audit before broader search.
  - Reopen the exact candidate source/test paths and verify that the named symbols still own the behavior.
  - Search for any newly added executable-path normalizer before editing `ea_node_editor/common/coercions.py`; reuse the current equivalent if one now exists.
  - Record the single implementation owner for `T01` through `T03`, the documentation owner for `T04`, and one independent read-only reviewer for both the post-`T03` checklist and `T05`. Confirm no live writer overlaps their scopes.
  - Identify the exact test node IDs that will prove the new cases so verification commands can become narrower if the tests are split during implementation.
- Verification:

  ```powershell
  git status --short
  Get-Content -Raw .\docs\PLAN_COREX_EXTERNAL_PYTHON_RUNTIME.md
  Get-FileHash -Algorithm SHA256 .\docs\PLAN_COREX_EXTERNAL_PYTHON_RUNTIME.md
  Get-FileHash -Algorithm SHA256 .\docs\PLAN_COREX_Physical_Simulation_Backend.md
  git diff -- docs/specs/INDEX.md
  rg -n "python_path|resolve_workflow_python_environment|ExternalPythonExecutionClient|WorkflowSettingsDialog|execution_backend" ea_node_editor tests --glob "*.py"
  ```

  The final search must be bounded further if its first results fan out; generated, cache, build, artifact, virtual-environment, worktree-mirror, and package-metadata trees remain excluded.
- Non-goals: code edits, tests, package builds, work-packet manifest generation, or parallel implementation.
- Packetization notes: becomes `P00 Bootstrap`. It is a coordination gate, not an implementation packet. If external packet manifests are later requested, this plan remains the source of task scope and the packet set links back here.

### T01 Add The App-Preference Contract, Migration, And Controller API

- Goal: persist one normalized app-wide default Python executable without changing project persistence or runtime selection yet.
- Preconditions: `P00` is `COMPLETE`; the same implementation owner is assigned through `T03`; no other source/test writer is live.
- Conservative write scope:
  - `ea_node_editor/settings.py`
  - `ea_node_editor/common/coercions.py`
  - `ea_node_editor/app_preferences.py`
  - `ea_node_editor/execution/python_environment.py`
  - `ea_node_editor/ui/shell/controllers/app_preferences_controller.py`
  - `tests/test_app_preferences.py`
  - `tests/test_app_preferences_import_defaults.py`
  - The Task Ledger evidence cells for `T01`
- Deliverables:
  - Change `APP_PREFERENCES_VERSION` from `6` to `7`.
  - Add `DEFAULT_PYTHON_RUNTIME_SETTINGS = {"default_executable": ""}` and include it under `DEFAULT_APP_PREFERENCES["python_runtime"]`.
  - Promote the existing whitespace/wrapping-quote behavior into one dependency-light helper in `ea_node_editor/common/coercions.py`, then use it from both app-preference normalization and `workflow_python_path_from_snapshot(...)`. This helper is text-only: it does not touch the filesystem.
  - Add `normalize_python_runtime_settings(payload)` to `ea_node_editor/app_preferences.py`. It returns a fresh mapping with only `default_executable`, accepts only strings, maps every non-string value to blank, and never performs filesystem or import checks.
  - Update `normalize_app_preferences_document(...)` so versions `5` and `6` migrate to `7`, discard any predecessor `python_runtime` section, and force the migrated default executable to blank. Versions `1` through `4` keep current default-reset behavior, unknown/future versions still fail closed to current defaults, and all other recognized existing sections remain preserved.
  - Update `AppPreferencesStore.load_document()` so loading a valid v5 or v6 document persists the normalized v7 document once. Do not add chained migration objects or a migration registry for two simple predecessor versions.
  - Add `AppPreferencesController.python_runtime_settings()`, `default_python_executable()`, and `set_default_python_executable(value)`. The setter deep-copies the cached document, normalizes and persists the candidate, replaces the cache only after successful storage, and returns the normalized stored string. A store exception leaves the cached document byte-for-byte equivalent to its prior value.
  - Add tests for blank defaults, string quote/whitespace normalization, every non-string value mapping to blank, v5-to-v7 and v6-to-v7 migration with forged predecessor values discarded, persistence-on-load for both predecessor versions, preservation of recognized sibling preferences, rejection/reset of pre-v5 and future documents, controller round-trip, and failed-store cache preservation.
  - Add a regression assertion that app-preference persistence does not import or mutate project metadata and does not change `SCHEMA_VERSION`.
- Verification:

  ```powershell
  .\venv\Scripts\python.exe -m pytest tests/test_app_preferences.py tests/test_app_preferences_import_defaults.py --ignore=venv -q
  .\venv\Scripts\python.exe -m pytest tests/test_execution_client.py -k "workflow_python_environment_resolver" --ignore=venv -q
  git diff --check -- ea_node_editor/settings.py ea_node_editor/common/coercions.py ea_node_editor/app_preferences.py ea_node_editor/execution/python_environment.py ea_node_editor/ui/shell/controllers/app_preferences_controller.py tests/test_app_preferences.py tests/test_app_preferences_import_defaults.py
  ```
- Non-goals: dialog changes, dispatch changes, filesystem validation during preference writes, subprocess/import probing, `.cxproj` schema changes, compatibility support for preference versions `1` through `4`, or a general migration framework.
- Packetization notes: becomes `P01 Preference Contract And Migration`. Keep it owned by the same writer as `P02` and `P03`; do not split the shared normalizer or controller API into a second packet.

### T02 Make Workflow Settings Explicitly Dual-Scope

- Goal: let users view and change the app default and project override in the existing Environment page while persisting each value only to its current owner.
- Preconditions: `T01` is `COMPLETE`; `AppPreferencesController.default_python_executable()` and `.set_default_python_executable(...)` are available; the implementation owner remains unchanged.
- Conservative write scope:
  - `ea_node_editor/ui/dialogs/workflow_settings_dialog.py`
  - `ea_node_editor/ui/tooltips/settings.json`
  - `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
  - `ea_node_editor/ui/shell/controllers/project_session_services_support/shared.py`
  - `tests/test_workflow_settings_dialog.py`
  - `tests/test_project_session_controller_unit.py` only if its existing document-service seam is the narrowest non-shell test owner
  - The Task Ledger evidence cells for `T02`
- Deliverables:
  - Extend `WorkflowSettingsDialog.__init__(...)` with the current application-default executable as a separate input. Do not insert app preferences into `initial_settings`, whose contract remains project workflow settings.
  - Replace the ambiguous single executable row with two labeled rows and separate line edits:
    - `Application Default Python Executable`
    - `Workflow Override`
  - Add native `QFileDialog.getOpenFileName(...)` Browse actions beside both fields. A selected path updates only its associated field; cancel leaves the field unchanged.
  - Retain the current managed-runtime background worker. On success, `_managed_runtime_finished(...)` writes `result.python_executable` only to the application-default field. On failure, both fields remain unchanged and the bounded error remains visible.
  - Keep `Create / Repair Managed Runtime` under app scope. Relabel/rewire the clear actions so `Clear Application Default` clears only the application default and `Inherit Application Default` clears only the workflow override. Visible help states that built-in is effective only when both fields are blank.
  - Keep `values()` returning exactly the project-owned `DEFAULT_WORKFLOW_SETTINGS` shape, with the workflow field serialized at `environment.python_path`. Add `application_default_python_executable()` as a separate normalized accessor.
  - Update `_refresh_managed_runtime_status(...)`, inline labels, and `ea_node_editor/ui/tooltips/settings.json` so the current effective choice and the whole-workflow/compatible-runtime/trusted-local/next-run semantics are visible. Tooltips supplement rather than replace visible help.
  - Keep `_set_runtime_controls_enabled(...)` correct for both Browse buttons and both clear actions while managed-runtime preparation is active.
  - Update `DocumentIOService.show_workflow_settings_dialog()` to read the current app default from `self._host.app_preferences_controller`, pass it separately to the dialog, and persist the dialog's app accessor through the controller only after the dialog is accepted. Keep project settings on `ProjectSessionMetadata.with_workflow_settings(dialog.values())`.
  - Before constructing the dialog, capture a deep copy of `project.metadata`, `project.project_document_revision`, and `project.document_epoch()`. Remove/defer the current pre-dialog `self._host.model.project.replace_metadata(session_metadata.to_mapping())`.
  - Opening and cancelling the dialog must leave the captured metadata/revision/epoch exactly unchanged and must persist neither app preferences nor session state.
  - On accept, persist the normalized app preference first through `AppPreferencesController.set_default_python_executable(...)`. If that store write fails, leave project metadata, project revision/epoch, and session persistence untouched; report the bounded app-preference failure from `ProjectDocumentIOService` with its existing `QMessageBox.warning(...)` pattern because the accepted dialog is already closed.
  - After app persistence succeeds, apply `ProjectSessionMetadata.with_workflow_settings(dialog.values()).to_mapping()` to the live project and invoke the existing `persist_session()` exactly once.
  - Treat `persist_session()` according to its existing best-effort contract: it currently swallows lifecycle-store failures, so this caller cannot detect a later write failure. Do not add a strict persistence variant, post-accept warning, state restoration, or cross-store transaction. The app preference and live project metadata may remain changed even when the best-effort session snapshot was not written.
  - Add tests for initial projection, both native picker success/cancel paths, exact clear-button semantics, managed-runtime success targeting app scope, managed-runtime failure preserving both fields, project-only `values()`, app-only accessor, tooltip/category behavior, app-first accepted call order, accepted live metadata update plus one `persist_session()` invocation, app-store failure leaving project/session untouched, and cancel persistence to neither store with unchanged metadata/revision/epoch.
  - Prove leakage through `JsonProjectSerializer.to_persistent_document(...)` or an actual temporary serializer save. Use a unique app-path sentinel and a distinct authored workflow-override sentinel; assert the encoded persistent project contains the workflow sentinel and never contains the app sentinel. `to_document()` alone is not acceptance evidence.
  - Assert that changing either field does not start, stop, recycle, or validate an execution worker during dialog acceptance.
- Verification:

  ```powershell
  $env:QT_QPA_PLATFORM = "offscreen"
  .\venv\Scripts\python.exe -m pytest tests/test_workflow_settings_dialog.py tests/test_project_session_controller_unit.py --ignore=venv -q
  Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
  git diff --check -- ea_node_editor/ui/dialogs/workflow_settings_dialog.py ea_node_editor/ui/tooltips/settings.json ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py ea_node_editor/ui/shell/controllers/project_session_services_support/shared.py tests/test_workflow_settings_dialog.py tests/test_project_session_controller_unit.py
  ```
- Non-goals: a separate Application Settings dialog, QML settings UI, environment browsing/discovery, automatic package installation on accept, a cross-store transaction or rollback framework, a strict replacement for best-effort `persist_session()`, a post-accept project-save warning, changing Working Directory semantics, changing plugin selection, applying settings to an active run, or persisting the app default in project/session metadata.
- Packetization notes: becomes `P02 Dual-Scope Environment UI`. Keep the native dialog and document-service persistence in one packet because their separation is the regression boundary that prevents app state from leaking into `.cxproj`.

### T03 Apply The App Default At Shell Dispatch With Exact Precedence

- Goal: use the app default for every shell run only when the project override is empty, while preserving explicit API/headless policies, current project override behavior, and built-in fallback.
- Preconditions: `T02` is `COMPLETE`; the same implementation owner is still active; no reviewer or docs writer is editing.
- Conservative write scope:
  - `ea_node_editor/execution/python_environment.py`
  - `ea_node_editor/execution/client.py`
  - `ea_node_editor/ui/shell/controllers/run_controller.py`
  - `tests/test_execution_client.py`
  - `tests/test_run_controller_unit.py`
  - `tests/test_shell_run_controller.py` only when a shell-backed assertion is necessary beyond the unit-owned controller seam
  - The Task Ledger evidence cells for `T03`
- Deliverables:
  - Keep `workflow_python_path_from_snapshot(...)` as the text-only project source reader. Add one generic final-path resolver in `ea_node_editor/execution/python_environment.py` that accepts already selected executable text and returns the existing environment result shape after `Path.expanduser()`, best-effort resolution, existence, file, executable, and current-interpreter comparison checks.
  - Stop using `resolve_workflow_python_environment(...)` as a validating selection step. If no production caller remains after the client/tests are updated, remove it and its export instead of retaining an unused compatibility alias. The repository is unreleased.
  - Refactor `ExecutionBackendClient.start_run(...)` into this exact order:
    1. Read normalized workflow Python text once with `workflow_python_path_from_snapshot(runtime_snapshot)`; do no filesystem work.
    2. Determine whether the caller supplied an explicit policy and coerce/select it under the public cases above.
    3. Explicit process, trusted, and auto never consult project or app defaults. Explicit external with a path uses its own path. Explicit external without a path fills only from non-empty workflow text and otherwise fails. With no explicit policy, non-empty workflow text creates the current workflow external policy; blank text leaves the normal process selection unless the shell already supplied an app-default policy.
    4. After the final backend/path is known, validate the final non-empty external path exactly once with the generic resolver and replace the selection with its normalized resolved path. Emit one actionable protocol error and return `""` on failure.
    5. Call the selected backend client. Do not add a second project resolver, PATH fallback, app lookup, or protocol field.
  - Refactor `ExternalPythonExecutionClient.start_run(...)` under its existing start lock so worker-module preflight precedes `_prepare_start_run(...)` only for a new/switched path. A live worker on the same normalized path skips the import probe, process restart, and generation advance.
  - Keep `_verify_runtime_available(...)` as the bounded check for `import ea_node_editor.execution.stdio_worker`, not a runtime-version or protocol-compatibility check. For every new process or switched path, execute that import preflight before `_prepare_start_run(...)`; narrow/remove `_verified_python_executables` caching so it cannot suppress the probe for a new process or a switch back to a previously used path. Only reuse of a currently live same-path worker skips the probe. Then make `_ensure_process(...)` perform only the guarded process transition without repeating the import probe. Preserve the existing post-launch registry/catalog/plugin/protocol handshake.
  - Before a switched-path preflight, preserve the existing live-viewer replacement refusal. Missing, invalid, or worker-module import-incompatible replacement configuration starts no new worker, reserves no run, and leaves the prior live external worker plus physical/catalog generation unchanged. `_process` may remain non-`None`.
  - Preserve valid path switching: after validation/preflight and `_prepare_start_run(...)`, the existing guarded transition may replace the worker, install the new process, and advance generation. Recheck viewer/process state under the same lock so a race cannot bypass the refusal or launch an un-preflighted replacement.
  - Handle `subprocess.Popen(...)` failure after preflight/reservation by releasing the reserved run, leaving no active run/start-pending state, and installing/accepting no new physical or catalog generation. Emit one bounded actionable launch error. For a switched path, allow that the prior worker may already be retired; add no worker rollback framework. A subsequent valid run must create and accept a clean generation.
  - Add one internal `RunController` helper, named `_execution_backend_policy_for_runtime_snapshot(...)`, with exactly this behavior:
    - if `workflow_python_path_from_snapshot(runtime_snapshot)` is non-empty, return `None` so the existing client-owned project override remains authoritative;
    - else read `self._host.app_preferences_controller.default_python_executable()`;
    - if blank, return `None` so the existing built-in process-isolated selection remains authoritative;
    - otherwise return the existing policy mapping with `requested_backend=EXTERNAL_SUBPROCESS_BACKEND`, `allow_external_subprocess=True`, the app `python_executable`, and stable reason `application_default_python_executable`.
  - Pass that helper's result as the existing `execution_backend=` keyword in `run_workflow()`, `run_selected_nodes()`, and `trigger_node()`. Do not modify the trigger mapping, workflow settings, runtime snapshot, project metadata, protocol DTOs, or client constructor.
  - Preserve exact explicit API/headless semantics: process/trusted/auto ignores project and app; external with its own path uses it; external without a path falls back only to the project workflow path; app default never fills an explicit API/headless policy.
  - Add focused tests for the complete truth table:
    - explicit process, trusted, and auto ignore a non-empty project override and any app value;
    - explicit external with its own path ignores project and app values;
    - explicit external without a path uses a non-empty project workflow path and fails when that path is blank, without app fallback;
    - non-empty project override beats a configured app default;
    - empty project plus configured app default produces the exact external policy;
    - empty project plus empty app default leaves `execution_backend=None` and selects the built-in process client;
    - quotes/whitespace normalize consistently;
    - no value triggers PATH lookup;
    - the final external path receives exactly one filesystem validation;
    - same-path live-worker reuse performs no import re-probe, restart, or generation change;
    - a dead same-path worker is a new process and therefore reruns the import preflight before reservation;
    - a missing app-default or replacement executable launches no new worker and leaves any existing worker/generation unchanged;
    - a replacement interpreter that cannot import the stdio worker fails before `_prepare_start_run(...)`, performs no automatic repair, and leaves the existing worker/generation unchanged;
    - a valid different path switches worker and advances generation after preflight;
    - a different path is refused while existing viewer requests or sessions make replacement unsafe, with the current worker/generation unchanged;
    - cold-start `subprocess.Popen` failure releases the reserved run, creates no active worker or accepted/half generation, emits the bounded error, and permits a later valid run;
    - switched-path `subprocess.Popen` failure releases the reserved run and installs/accepts no new generation; the test explicitly allows the prior worker to have been retired, then proves a later valid run recovers cleanly;
    - existing catalog/registry/protocol handshake-mismatch tests remain passing after launch; no new compatibility probe substitutes for them;
    - the selected app-default interpreter runs a workflow containing a Python Script node and that node observes the configured `sys.executable`;
    - Run, manual Run Selected, automatic Run Selected, and Trigger all call the same helper and pass the same policy for the same snapshot/preferences.
  - Assert that one external backend selection covers all nodes in the run and that no per-node interpreter field appears in snapshot, protocol, graph, or node payloads.
- Verification:

  ```powershell
  .\venv\Scripts\python.exe -m pytest tests/test_execution_client.py -k "workflow_python or external_python or application_default_python" --ignore=venv -q
  .\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py -k "python_runtime or application_default or run_workflow or run_selected or trigger_node" --ignore=venv -q
  .\venv\Scripts\python.exe -m pytest tests/test_shell_run_controller.py -k "application_default_python" --ignore=venv -q
  git diff --check -- ea_node_editor/execution/python_environment.py ea_node_editor/execution/client.py ea_node_editor/ui/shell/controllers/run_controller.py tests/test_execution_client.py tests/test_run_controller_unit.py tests/test_shell_run_controller.py
  ```

  If no shell-backed test is added, omit the third pytest command and record the reason in the ledger; the run-controller unit suite must still cover all dispatch methods.
- Non-goals: new execution backend classes, new worker/protocol DTOs, a new version/protocol/compatibility probe, rollback/revival of a prior worker after switched-path `Popen` failure, app-default lookup in headless runtime, project opt-out, per-node selection, environment/package management, or PATH fallback.
- Packetization notes: becomes `P03 Shell Dispatch Precedence`. The existing client validation and three shell entry points belong together because splitting them permits a stored path to route differently depending on the action.

### T04 Align Requirements, User Guidance, Traceability, And Agent Maps

- Goal: document the implemented contract and its limitations without claiming evidence not produced by `T01` through `T03`.
- Preconditions: `T03` focused checks pass; the single independent read-only architecture/QA review is accepted; the implementation owner has stopped editing; the documentation owner is the only writer.
- Conservative write scope:
  - `docs/specs/requirements/50_EXECUTION_ENGINE.md`
  - `docs/specs/requirements/20_UI_UX.md`
  - `docs/specs/requirements/TRACEABILITY_MATRIX.md`
  - `docs/PYTHON_SCRIPT_GUIDE.md`
  - `docs/agent_maps/subsystems/app_preferences_settings_platform_paths.md`
  - `docs/agent_maps/subsystems/execution.md`
  - `docs/agent_maps/subsystems/ui_shell.md`
  - `docs/agent_maps/subsystems/pyqt_dialogs_panels_theme_editor.md`
  - `docs/agent_maps/feature_routes/run_controller_selected_workspace_state.md`
  - `docs/agent_maps/feature_routes/project_session_files_managed_artifacts.md`
  - `docs/agent_maps/feature_routes/graphics_settings_themes_preferences.md`
  - `docs/agent_maps/COVERAGE.md` when the changed ownership rows require it
  - Generated `docs/agent_route_index.md` and `docs/agent_route_index.json`
  - Generated `docs/source_test_file_index.md`
  - This plan's ledger/status and `docs/specs/INDEX.md` only as required by truthful status registration
- Deliverables:
  - Add `REQ-EXEC-029` and `AC-REQ-EXEC-029-01` for exact explicit/project/app/built-in selection cases, whole-workflow external execution, one final filesystem validation, worker-module preflight before run reservation for new/switched paths, same-path reuse, safe generation switching, existing startup handshake, no PATH fallback, and no project/runtime-snapshot leakage.
  - Add `REQ-UI-066` and `AC-REQ-UI-066-01` for the dual-scope Environment page, native pickers, managed-runtime/app-default targeting, `Clear Application Default`/`Inherit Application Default`, visible import/handshake/trust help, next-run application, exact cancel/app-store-failure behavior, app-first accepted ordering, and the existing best-effort session-persistence limitation.
  - Add implementation and acceptance rows to `TRACEABILITY_MATRIX.md` only for evidence actually produced. Point to exact source/test files; do not cite this plan as implementation proof.
  - Add a concise `Choose the workflow Python runtime` section to `docs/PYTHON_SCRIPT_GUIDE.md` that documents the exact selection-case table, states that the interpreter runs the entire workflow, distinguishes the bounded worker-module import preflight from the existing post-launch handshake, explains both clear actions and app-first accepted ordering, marks trusted local execution as non-sandboxed, and calls out the best-effort session limitation plus the v1 lack of project opt-out/per-node selection/PATH fallback.
  - Update the affected subsystem and feature-route maps plus `COVERAGE.md` where required with the app-preference v7 key, dual-scope dialog ownership, best-effort project-session behavior, shell policy injection, final-path validation, worker reuse/switch behavior, and focused test commands. Do not add a new feature-route map for this small cross-layer extension.
  - Use only COREX or neutral terminology in tracked files, paths, generated outputs, status text, requirement wording, and test names. Include no vendor-study names, study URLs or provenance, installed-product paths or versions, screenshots, hashes, proprietary identifiers, or comparative labels/wording.
  - Regenerate `docs/agent_route_index.md` and `.json` with the repository script; do not hand-edit generated outputs.
  - Regenerate `docs/source_test_file_index.md` with its repository script because focused test contents changed; do not hand-edit it.
  - Keep the plan and index labeled `PLANNED — NO IMPLEMENTATION PROOF` until implementation and acceptance evidence actually exists. A later truthful status update may occur only under the Orchestrator Resume Contract.
- Verification:

  ```powershell
  .\venv\Scripts\python.exe .\scripts\generate_source_test_file_index.py
  .\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py
  .\venv\Scripts\python.exe .\scripts\generate_source_test_file_index.py --check
  .\venv\Scripts\python.exe .\scripts\check_traceability.py
  .\venv\Scripts\python.exe .\scripts\check_markdown_links.py
  .\venv\Scripts\python.exe .\scripts\check_agent_maps.py
  .\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_agent_route_index.py tests/test_source_test_file_index.py tests/test_python_script_guide_example.py --ignore=venv -q
  git diff --check -- docs
  ```
- Non-goals: adding a new architecture diagram, adding a retained QA matrix before acceptance evidence exists, rewriting unrelated guide sections, changing requirement IDs outside `REQ-EXEC-029`/`REQ-UI-066`, or hand-editing generated route indexes.
- Packetization notes: becomes `P04 Requirements And Guidance`. It starts only after the source freeze and post-implementation reviews so documentation describes actual symbols and tests rather than planned names.

### T05 Run Independent Final Audit And Acceptance

- Goal: independently prove the complete feature, its negative boundaries, and documentation consistency before any completion claim.
- Preconditions: `T04` is ready for review; all writers have stopped; the same independent read-only reviewer who accepted `T03` is assigned the final audit.
- Conservative write scope: no tracked files. The reviewer may produce only ignored pytest caches and `artifacts/verification_logs/` output from the repository-owned runner. The orchestrator alone may update this plan's ledger/status after review.
- Deliverables:
  - Review the full diff and map every changed line to `T01` through `T04`; flag unrelated churn.
  - Confirm `python_runtime.default_executable` exists only in app-preference/controller/dialog/run-policy/docs/tests owners and never in project persistence, graph/node schemas, runtime snapshot DTOs, worker protocol DTOs, or plugin declarations.
  - Confirm no new dependency, worker, protocol field, backend ID, process launcher, settings framework, environment manager, package installer, or per-node selector exists.
  - Confirm the exact selection cases through tests and source: explicit process/trusted/auto ignores defaults; explicit external uses its path or only the existing project fallback when pathless; implicit project override; shell app default; built-in only when both stored fields are blank.
  - Confirm `run_workflow()`, `run_selected_nodes()` including automatic dispatch, and `trigger_node()` call the same policy helper.
  - Confirm version `5` and `6` migrate to `7` with any predecessor `python_runtime` discarded, non-string executable values normalize blank, pre-v5 behavior is unchanged, failed controller storage preserves cache, and app-default changes do not enter `.cxproj`.
  - Confirm source selection is text-only until the final external path receives exactly one filesystem validation.
  - Confirm same-path reuse does not probe/restart/advance; invalid or worker-module import-incompatible replacement launches no new worker and preserves the current worker/generation; valid switching advances generation; and live-viewer switching remains refused. Confirm startup-handshake mismatch behavior remains post-launch.
  - Confirm cold-start and switched-path `subprocess.Popen` failures release the reserved run, install/accept no new or half generation, emit bounded actionable errors, and permit the next valid run to recover. Do not require a previously running worker to survive a failed switched-path launch.
  - Confirm the dialog exposes native pickers, `Clear Application Default`, `Inherit Application Default`, app-targeted managed-runtime action, visible whole-workflow/import/handshake/trust/next-run help, exact cancel/app-store-failure no-op semantics for project/session state, app-first accepted ordering, and no invented guarantee beyond best-effort `persist_session()`.
  - Confirm persistent-document sentinel evidence includes an authored workflow override and excludes the app-default sentinel.
  - Confirm all intended limitations are documented: whole-workflow scope, trusted local execution, worker-module import requirement plus possible startup-handshake rejection, no PATH fallback, no per-node selector, and no project opt-out from a configured app default.
  - Confirm every tracked change uses only COREX or neutral terminology and contains no vendor-study names, study URLs/provenance, installed-product paths/versions, screenshots, hashes, proprietary identifiers, or comparative labels/wording.
  - Run the focused commands once against the final diff, then the `fast` integration gate because this crosses app preferences, shell, execution, tests, specs, and maps.
- Verification:

  ```powershell
  git status --short
  git diff --check
  git diff -- ea_node_editor tests docs
  Get-Content -Raw .\docs\PLAN_COREX_EXTERNAL_PYTHON_RUNTIME.md
  Get-FileHash -Algorithm SHA256 .\docs\PLAN_COREX_EXTERNAL_PYTHON_RUNTIME.md
  Get-FileHash -Algorithm SHA256 .\docs\PLAN_COREX_Physical_Simulation_Backend.md
  .\venv\Scripts\python.exe -m pytest tests/test_app_preferences.py tests/test_app_preferences_import_defaults.py tests/test_workflow_settings_dialog.py tests/test_project_session_controller_unit.py tests/test_run_controller_unit.py tests/test_execution_client.py --ignore=venv -q
  .\venv\Scripts\python.exe .\scripts\check_traceability.py
  .\venv\Scripts\python.exe .\scripts\check_markdown_links.py
  .\venv\Scripts\python.exe .\scripts\check_agent_maps.py
  .\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output
  rg -n "python_runtime|default_executable" ea_node_editor tests docs --glob "*.py" --glob "*.md" --glob "*.json"
  rg -n "default_executable" ea_node_editor\persistence ea_node_editor\graph ea_node_editor\nodes ea_node_editor\execution\protocol.py ea_node_editor\execution\runtime_snapshot.py
  ```

  The final `rg` over forbidden owners must return no hits. If it returns a test fixture documenting absence, inspect it manually and record why it is not a production contract before acceptance.
- Non-goals: fixing findings directly as reviewer, package/installer release proof, remote execution, or expanding v1 limitations.
- Packetization notes: becomes `P05 Independent Acceptance`. Review findings reopen the owning packet; the reviewer rechecks the resulting diff. The orchestrator records final evidence only after every reopened task returns to `COMPLETE`.

## Work Packet Conversion Map

1. `P00 Bootstrap`: derive a packet ledger/prompts only if explicitly requested, classify the dirty checkout, reconfirm owners/tests, assign the one implementation writer, and close all exploration before edits.
2. `P01 Preference Contract And Migration`: derived from `T01`; app preferences v7, v5/v6 migration, shared path-text normalization, controller accessor/setter, and focused preference tests.
3. `P02 Dual-Scope Environment UI`: derived from `T02`; existing dialog, native pickers, managed-runtime targeting, split persistence, and dialog/document-service tests.
4. `P03 Shell Dispatch Precedence`: derived from `T03`; one text-selection/final-validation flow, one shell policy helper, all three dispatch paths, reuse/switch/error/handshake tests, then one independent read-only architecture/QA review.
5. `P04 Requirements And Guidance`: derived from `T04`; requirements/acceptance criteria, traceability, Python Script guide, affected maps, and regenerated route index after the source/review freeze.
6. `P05 Independent Acceptance`: derived from `T05`; the same independent reviewer repeats the audit against the complete diff, runs focused regression/docs/fast checks, and returns evidence for orchestrator closeout.

Packet conversion rules:

- Do not create packet manifests, packet-only indexes, wrap-ups, or intermediate commits unless the user explicitly requests packetization or the repository's active release process requires them.
- Keep `P01` through `P03` with one implementation owner even if they become separate packets. The packet boundary controls verification and review; it does not authorize concurrent writers.
- `P04` cannot start from planned symbol names. It starts only from the accepted `P03` diff so docs cite actual owners and test names.
- `P05` is read-only. Any edit reopens the owning earlier packet and invalidates the prior final-review result.

## Test Plan

### Preference And Migration Contract

- Default v7 document contains exactly `python_runtime.default_executable = ""`.
- Path text trims whitespace and one matching quote pair; only strings are accepted, and every non-string executable value defaults blank.
- Valid v5 and v6 documents migrate and persist once as v7 while preserving recognized sibling sections, discarding any predecessor `python_runtime`, and forcing the new default blank.
- Pre-v5, unknown kind, malformed version, and future version behavior remains unchanged.
- Controller copy-on-write get/set round-trips and a failed store write leaves its cached document unchanged.

### Dual-Scope Dialog And Persistence

- Both fields initialize from separate owners and round-trip separately.
- Browse success changes the target field; Browse cancel changes neither.
- Managed-runtime success fills only app default; failure preserves both fields.
- `Clear Application Default` clears app default only; `Inherit Application Default` clears workflow override only; built-in is effective only when both are blank.
- `values()` contains only project workflow settings; the app accessor contains only the app default.
- Cancel persists neither store and leaves project metadata, `project_document_revision`, and `document_epoch()` exactly unchanged.
- Accept persists app preference first. App-store failure leaves project/session state unchanged. After success, live project metadata updates and existing best-effort `persist_session()` is invoked once.
- V1 does not detect or warn on a later lifecycle-store failure swallowed by `persist_session()`, and does not restore either already-applied store. Tests pin this limitation rather than inventing cross-store atomicity.
- `to_persistent_document()` or an actual temporary save includes a distinct authored workflow-override sentinel while excluding the unique app-default sentinel.
- No accept path launches Python, imports packages, installs dependencies, creates a venv, or changes an active run.

### Runtime Selection And Validation

- Selection-case tests cover explicit process/trusted/auto, explicit external with/without path, implicit project override, shell app default, and built-in fallback.
- Explicit process/trusted/auto ignores project/app; explicit external uses its own path or only the existing project fallback when pathless; app never fills an explicit API/headless external policy.
- An implicit project override is never replaced by app policy; shell app policy is injected only when project override is empty.
- Run, Run Selected, automatic Run Selected, and Trigger use identical selection logic.
- Source selection is text-only, and the final non-empty external executable receives exactly one filesystem validation.
- Missing/directory/non-executable paths fail before any new worker creation while preserving an existing worker/generation.
- Same-path live-worker reuse skips import preflight/restart/generation advance. New/switched paths run the worker-module import preflight before run reservation; invalid/import-incompatible replacement preserves the existing worker, valid switching advances generation, and live-viewer switching remains refused.
- Post-preflight `subprocess.Popen` failure releases the reserved run and accepts no new physical/catalog generation. Cold start leaves no worker; switched-path failure may leave the prior worker retired. Both cases emit a bounded error and the next valid run recovers without active-run or half-generation residue.
- Import-check timeout or launch failure emits an actionable protocol error with no automatic repair. Registry/catalog/protocol incompatibility remains an existing post-launch handshake failure, not a new preflight claim.
- An app-default interpreter that passes existing startup executes the full workflow; a Python Script node observes that interpreter's resolved `sys.executable`.
- Empty settings do not consult PATH or the terminal environment.

### Negative Architecture Checks

- No app default in project documents, runtime snapshots, graph/node/property schemas, protocol DTOs, plugin contracts, or worker payload fields.
- No new backend/client/worker/protocol/settings framework/dependency.
- No per-node or plugin-level interpreter.
- No environment discovery or installer side effect outside the explicit managed-runtime button.

### Documentation And Integration

- Requirements, acceptance criteria, traceability, guide, and maps describe the exact shipped implementation and limitations.
- Generated route index is regenerated, not hand-edited.
- Traceability, Markdown links, agent maps, guide example, focused tests, and `run_verification.py --mode fast --summarize-output` pass against the final diff.
- Windows package/installer build is not required for this local settings/dispatch extension unless implementation changes packaged runtime contents or the final reviewer finds packaging impact. If that happens, reopen scope rather than silently adding a release claim.

## Assumptions

- The existing project workflow Python override, external stdio worker, execution backend policy, managed runtime, and runtime import check remain the correct production seams.
- The selected external interpreter is installed on the local PC and trusted by the user. A user-managed interpreter must import `ea_node_editor.execution.stdio_worker`; passing that bounded preflight does not guarantee the later registry/catalog/plugin/protocol startup handshake will accept it.
- One interpreter hosts one complete workflow run. Python Script is an observable proving node, not a special routing target.
- App-preference changes apply on the next dispatch. They do not mutate the active run snapshot or hot-swap a live worker.
- Empty project override always means inherit. V1 has no project-only force-built-in state while a non-empty app default exists.
- Empty app default always means built-in process-isolated runtime. No PATH or environment discovery is permitted.
- App preferences v7 is the only persistence version change. `SCHEMA_VERSION` and `.cxproj` migrations remain unchanged.
- Existing `ExternalPythonExecutionClient` generation replacement and viewer-safety rules remain authoritative when the next run chooses a different interpreter.
- If `subprocess.Popen(...)` fails during a path switch, the prior external worker may already be retired. V1 requires clean run/generation release and next-run recovery, not restoration of that prior process.
- `ProjectSessionLifecycleService.persist_session()` remains best-effort and may swallow a session-store failure. After an accepted dialog, the app preference and live project metadata may remain changed even if the session snapshot was not written; v1 intentionally adds no strict persistence path, cross-store transaction, rollback, or post-accept warning.
- No new dependency is required.
