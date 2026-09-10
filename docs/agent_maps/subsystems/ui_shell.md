# UI Shell, Controllers, And Presenters

## Purpose
Use this for shell-backed workflows, controllers, presenters, context bridges, and high-risk shell composition edits.

## Start Here
- `ea_node_editor/ui/shell/window.py`
- `ea_node_editor/ui/shell/composition/` — one domain per module: `state.py`, `primitives.py`, `preferences.py`, `library_workspace.py`, `controllers.py`, `presenters.py`, `runtime_services.py`, `registry_replacement.py`, `bridges.py`, `graph_actions.py`, `qml_context.py`; aggregates in `services.py`, sequencing in `factory.py`, attach/startup in `bootstrap.py`, public API re-exported from `__init__.py`
- `ea_node_editor/ui/shell/registry_replacement.py`
- `ea_node_editor/ui/shell/window_actions.py`
- `ea_node_editor/ui/shell/window_state/`
- `ea_node_editor/ui/shell/context_bridges.py`
- `ea_node_editor/ui/shell/controllers/`
- `ea_node_editor/ui/shell/controllers/run_projection_controller.py`
- `ea_node_editor/ui/shell/controllers/run_event_controller.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/document_io_service.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/project_files_service.py`
- `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
- `ea_node_editor/ui/shell/controllers/plugin_authoring_controller.py`
- `ea_node_editor/ui/shell/presenters/`
- `ea_node_editor/ui/shell/presenters/graph_canvas_host_presenter.py`
- `ea_node_editor/telemetry/frame_rate.py`
- `tests/test_frame_rate_sampler.py`
- `tests/test_run_controller_unit.py`
- `tests/test_run_projection_controller.py`
- `tests/test_run_event_controller.py`
- `tests/test_registry_replacement.py`

## Do Not Start Here
- QML component files when behavior is owned by shell controllers.
- Graph domain mutation internals unless the shell operation changes graph invariants.

## Common Changes
- Route shell commands through the relevant controller, then update bridges/presenters.
- `GraphCanvasHostPresenter` is the direct graph-host owner for cursor application, passive-node/flow-edge style dialogs and project presets, the graph style clipboard, flow-edge labels, and scene mutations. Keep those methods off `ShellWindow` and `ShellHostPresenter`; the latter retains app-wide/native dialogs and import policy.
- File > New Plugin and Reload Plugins are native shell actions owned by `PluginAuthoringController`. The controller creates one fresh identity per dialog lifecycle, atomically owns a saved draft by expected content, attests the real file before calling the registry replacement coordinator, and opens the canonical plugins folder through the platform handler. It emits no library notification itself.
- `ui/shell/registry_replacement.py` owns the guarded registry transaction used by plugin reload, package import, and live add-on apply; `composition/registry_replacement.py` attaches it after runtime/controller services. The accepted order is disposable candidate + read-only graph check, guarded final recheck/activation/canonical rebuild, runtime and shell consumer publication, durable package/preference finalization, then best-effort notifications. Rollback continues across every owner and surfaces aggregate bounded failures.
- Node-package export candidates in `workspace_io_ops.py` come from registry specs plus private provenance. The shell forwards only explicit schema-2 source/asset members and metadata to `package_manager.py`; it does not pass descriptors, dependencies, or executable validation records.
- Keep shell-isolated behavior covered by shell tests instead of broad app startup checks only.
- Treat the `composition/` package and bridge installation as high-risk.
- `composition/bridges.py` constructs and attaches `GraphCanvasStateBridge` and `GraphCanvasCommandBridge` with exact per-domain owners. State receives session state/signal/size, app preferences, persisted graphics, execution/project, scene, and viewport; command receives run, scope/hint, Inspector, Library, T14 edit/drop, T15 media, graphics, host, scene, viewport, model/workspace navigation, and folder collaborators. Neither accepts `canvas_source` or a shell-window fallback.
- `composition/services.py` owns the `ShellServices` aggregate; a new shell-owned dependency enters through its domain module's dataclass + `create_*` function before it is exposed to `ShellWindow` or QML (see Recipes below).
- `composition/runtime_services.py` is the only assembly point for content fullscreen. It passes live model/registry/workspace/project providers, focused owner objects/callbacks, and one lazy per-open `WebSurfaceArtifactService` factory; `ContentFullscreenBridge` never receives `ShellWindow` or the `ShellServices` aggregate.
- The same runtime-services composition function explicitly injects every dependency used by `ViewerSessionBridge`, `ViewerControlBridge`, `ViewerHostService`, and `PlotHostService`; those classes keep their QObject parent for lifetime only and never locate services through it. Only camera capture to the later viewer host and bookmark cycling to the later viewer control remain bounded late callbacks.
- Shell-created QML image providers should be constructed in `composition/primitives.py` and registered through `shell_context_bootstrap.py` via `composition/qml_context.py`.
- Workspace view lifecycle calls route through `GraphModel.workspace_view_mutations(...)`; do not depend on the retired graph workspace mutation service factory.
- `addons/property_edit_adapters.py` composes the core Plot adapter before live add-on adapters for both Inspector and canvas. `ui/shell/property_edit_adapters.py` retains the shell-facing wrapper. Selected-node property edits and `inspector_projection.py` use that route; do not add direct add-on branches to `WorkspaceEditController` or the generic Inspector owner.
- Inspector property projection keeps the local authored `value` separate from upstream `display_value`; `overridden_by_input`, `condition_enabled`, and `editor_enabled` are presentation facts. Reuse the common interval/searchable-enum controls and existing property commit path rather than creating inspector-only validation or value-shape rules.
- Sensitive Inspector properties project only `{has_value, scope}` state. Replace, Clear, and scope reprotection route through `ShellInspectorBridge` to the graph-scene secret commands; `inspector_projection.py` must never send the persisted DPAPI envelope to QML.
- Path property browse dialogs route through `ShellInspectorPresenter` to `ShellHostPresenter`; extension filters come from `PropertySpec.file_filter` and must be forwarded as dialog metadata, not inferred from node type in shell code.
- Shell-side post-mutation aftermath such as selected-node notifications, workspace-tab refreshes, script-editor sync, runtime-history invalidation, full scene refresh after history replay, and layout graph hints routes through `MutationUiEffects`; graph-scene payload deltas remain owned by `ui_qml/graph_scene*`.
- Paste routes through `WorkspaceEditController`: graph-fragment MIME stays first, while shell-side clipboard fallback classification lives in `clipboard_paste_nodes.py`. Clipboard/media capture calls the public `ProjectSessionController.stage_node_artifact_bytes(...)` API; `ProjectFilesService` owns the synchronous write, registration, and metadata publication.
- Persisted graphics changes flow `AppPreferencesController` -> shell host state -> `ShellWorkspacePresenter.graphics_preferences_changed`; that presenter is the only persisted-graphics source for the state/command bridges and scene. Session snap/minimap and selected-run preview use their direct state/controller owners.
- `ProjectDocumentIOService.show_workflow_settings_dialog()` keeps application and project Python settings separate: it opens without normalizing the live project, persists the app default first, then updates project workflow metadata and invokes existing best-effort `persist_session()`. Cancel and app-store failure leave project/session state untouched; the best-effort later session write has no new transaction, rollback, or warning path.
- `ProjectFilesService` owns synchronous staged payload path selection through `ProjectArtifactStore`, file/byte/notebook writes, staged-entry registration, and the one metadata publication. `ProjectSessionController` is the public cross-owner API and emits one `project_meta_changed` signal only after a successful staging result. `ShellHostPresenter` owns native dialogs and import policy only; `WorkspaceEditController`, `MediaPanelActionService`, and the composition-injected Jupyter bridge call the controller directly.
- `ProjectDocumentIOService` alone owns copy-on-write Save/Save As artifact, image, solution, and canonical-project publication, verified reopen/adoption, and post-success cleanup. Staging never moves or destructively promotes payload bytes.
- `composition/controllers.py` constructs the one `CorexRuntime` with `SolutionRepositoryFactory`; execution code sees only its backend port. `ProjectDocumentIOService._install_project()` resets the runtime, then binds decoded `metadata.solution_store` before installing the replacement model. Save/Save As share one nonblocking guard, stage artifacts/solutions/images and canonical project bytes copy-on-write, reopen/verify the committed candidate, then adopt the already-prepared runtime backend and live state before releasing the guard. A postcommit failure leaves the source live binding dirty while the destination disk snapshot remains authoritative.
- `RunController._execution_backend_policy_for_runtime_snapshot(...)` injects the app-default external policy for Run, manual/automatic Run Selected, and Trigger only when the project Workflow Override is blank. It never mutates the trigger payload or runtime snapshot.
- Shell pane collapse preferences flow through `ShellWorkspacePresenter` and app preferences; keep the presenter, `ShellWorkspaceBridge`, and QML pane owners aligned.
- `ScriptEditorModel` owns interactive script-editor panel width. `ProjectDocumentIOService` snapshots the model state before manual Save/Save As conversion and restores it on project open; autosave, session, and close synchronization remain lifecycle-owned.
- File > Import COREX Project routes through `window_actions.py` and `window_state/project_session_actions.py` to `ProjectSessionController` and `ProjectDocumentIOService`. It reuses the New/Open dirty-project Discard/default-Cancel guard, installs only a validated complete/partial candidate as a pathless dirty project, and uses fixed bounded report dialogs. Save As is always a self-contained create-new/no-clobber copy for a distinct path; the former project-file-only choice is removed.
- Remaining `ShellWindow` state/action methods are normal methods defined in the `window_state/` mixin class bodies; do not recreate `window_state_helpers.py`, binding maps, `locals().update(...)` injection, module-level functions rebound through assignment blocks, host adapter classes, or `__getattr__` forwarding.
- Menubar additions belong in `window_actions.py`; PyQt-only help dialogs should route through `ShellHostPresenter` and an explicit `ShellWindow` method in `window_state/run_and_style_state.py`.
- Edit -> Interact with Locked Objects is a session-only checkable action on Ctrl+L; Connect Selected uses Ctrl+Shift+L. The action projects directly to the graph scene and is intentionally not stored in app preferences.
- The Ctrl+B Node Browser action belongs in `window_actions.py`; its cached library/help rows and learned-shortcut ranking stay in `LibraryPresenter`/`library_projection.py` and are exposed through `ShellLibraryBridge` rather than rebuilt in QML.
- `library_projection.py` owns Library filtering and category ancestors/options/tree from the same cached combined registry/custom-workflow items. `LibraryPresenter` owns one category-tree cache and no separate registry-category cache; the registry has no Library query API.
- Library type filters, pin type options, and connection Quick Insert preserve exact canonical IDs. Data inputs match their primary type plus `accepted_data_types`; reverse Quick Insert carries the originating input's accepted union in presenter state.
- Canvas view export is owned by plain `CanvasExportPresenter`: window/view-tab and `ProjectReviewDeckPresenter` call it directly for framing, viewport restore, native-overlay composition, crop extents, PNG/PPTX naming/order, output-folder dialog, and notifications/errors. `GraphCanvasHostPresenter` and QML capture APIs remain unchanged.
- Selected-node link rows/actions are projected through `ShellInspectorPresenter` and `ShellInspectorBridge`; keep inspector payload names, picker option labels/hidden IDs, cross-workspace open/focus behavior, and QML calls aligned with `InspectorNodeLinksSection.qml`.
- Selected-node comment rows/actions are projected through `ShellInspectorPresenter` and `ShellInspectorBridge`; keep payload names, composer focus, and QML calls aligned with `InspectorNodeCommentsSection.qml`.

- `RunEventController` is the sole plain-Python shell intake for runtime events. Composition retains it and connects `ShellWindow.execution_event` directly with one queued Qt connection; it filters before mutation, routes Trigger/log/terminal behavior, then directly delivers each event once to `ViewerSessionBridge.handle_viewer_execution_event(...)`. The viewer bridge does not self-register, retains its own event/epoch/request filters, and cannot interrupt completed run-state routing if its projection fails. `RunProjectionController` projects execution-owned `NodeSolutionFact` values and strict `solution_state_changed` revisions; it does not own another freshness set or closure. It is the sole shell owner of node execution sets, elapsed/warning state, accepted-output observations, port availability, failure focus, and run-control status over the shared `ShellRunState`. `RunController` remains command/Auto/Trigger/history oriented. Store-accepted output observations use `ui/support/solution_output_cache.py`, whose retained-record selector and bounded eviction are shared by shell presenters and QML projections.
- Graph history calls the renamed solution-invalidation hook. Exact expired/removed IDs clear node availability, elapsed/warning/lifecycle projections, and deleted-node caches; active-run Auto targets coalesce until the terminal outcome table permits one retry.

## Recipes

Exact touch-point lists for the most common shell additions. One domain = one
`composition/<domain>.py` module holding its dependency dataclass, its
`create_*` factory function, and only its own imports.

### Add a shell controller
1. `composition/controllers.py`: add the field to `ShellControllerDependencies`, construct it inside `create_controller_dependencies(host, state)` (the host IS the `ShellWindow`), and add the `host.<name> = self.<name>` line to `attach`.
2. Wire consumers (other controllers/presenters read it as `self._host.<name>` after attach; QML never sees controllers directly).
3. Dialogs must parent via `ea_node_editor/ui/shell/controllers/dialog_support.py` `resolve_dialog_parent(host)`.
4. Add a focused test (see `tests/test_run_controller_unit.py` for the host-stub pattern).

### Add a presenter
1. `composition/presenters.py`: field on `ShellPresenterDependencies`, construct with `<Presenter>(host, parent=host)` in `create_presenter_dependencies`, attach line.
2. If the presenter reads new window surface, extend its host protocol in `ea_node_editor/ui/shell/presenters/contracts.py` (protocols describe the `ShellWindow` surface).

### Add a QML bridge + context property
1. `composition/bridges.py`: construct the bridge in `create_context_bridge_dependencies`, add the dataclass field and attach line.
2. `composition/qml_context.py`: pass it through `_build_shell_context_bundle(...)` and add the `("contextName", ...)` tuple entry in `_build_shell_context_property_bindings`.
3. `ea_node_editor/ui_qml/shell_context_bootstrap.py`: add the matching `ShellContextBundle` field.
4. QML reads the context name; keep existing context-property names unchanged.

### Add a QML-facing window action
1. Define the method with `@pyqtSlot` in the owning `window_state/<module>.py` mixin class body; delegate to the responsible presenter/controller.
2. QML calls it on the window context object. Menubar additions still belong in `window_actions.py`.

### Add a QML-facing pyqtProperty
1. Add the module-level `_qt_<name>(self: "ShellWindow")` fget in `window_state/context_properties.py`.
2. Add one `pyqtProperty(..., fget=context_properties._qt_<name>, notify=<owning signal>)` declaration in the `ShellWindow` class body in `window.py`.
3. Make sure the owning notify signal is emitted on every change path.
## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_projection_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_event_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_project_session_controller_unit.py -k "workflow_settings" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_project_session_controller_unit.py -k "solution or bind or replacement" -q
.\venv\Scripts\python.exe -m pytest tests/test_project_file_staging.py tests/test_architecture_boundaries.py tests/test_jupyter_create_blank.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_controller_unit.py -k "application_default_python" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_registry_replacement.py tests/test_node_package_io_ops.py tests/test_main_window_shell.py -k "registry or package or addon" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_plugin_authoring_controller.py -q
```

## Breadcrumbs
- [Graph Actions And Context Menus](../feature_routes/graph_actions_and_context_menus.md)
- [Project Session, Project Files, And Managed Artifacts](../feature_routes/project_session_files_managed_artifacts.md)
- [Run Controller And Selected Workspace State](../feature_routes/run_controller_selected_workspace_state.md)
- [Durable Node Linking](../feature_routes/durable_node_linking.md)
- [SSH/SFTP Nodes](../feature_routes/ssh_sftp_nodes.md)


## 2026-06-10 Shell Composition Package + Host Adapter Retirement

- `composition.py` is now the `composition/` package described in Start Here; the public API (`create_shell_window`, `build_shell_window_composition`, `bootstrap_shell_window`, `ShellWindowComposition`, `ShellServices`, `ShellWindowDependencyFactory`, the dependency dataclasses, `AddonManagerBridge`) is unchanged and re-exported from the package `__init__`.
- `_ShellWindowAdapterBase` and the eight per-consumer host adapter classes are deleted. Controllers and presenters receive the `ShellWindow` directly; `resolve_dialog_parent` resolves the window as the QWidget dialog parent. **Do not recreate host adapter classes or `__getattr__` forwarding.**
- `window_state/` mixins are normal classes: new state/action methods are defined in the mixin class body (with `@pyqtSlot` where QML-facing); there are no module-level mixin functions, assignment blocks, or function-name `__all__` bookkeeping.
- The QML-facing graph-action `request_*` slots live in `ShellWindowWorkspaceGraphActionsMixin` and still dispatch through `graph_action_controller.trigger(GraphActionId...)`; `window.py` keeps signals, class constants, `pyqtProperty` declarations, `__init__`, and lifecycle only.

## 2026-05-31 Mutation UI Effects Update

- `composition/library_workspace.py` constructs one `MutationUiEffects` and injects it into both `WorkspaceEditController` and `WorkspaceDropConnectController`. `WorkspaceSelectionContext`, `WorkspaceNavigationController`, `WorkflowLibraryController`, and `WorkspacePackageIOController` are exposed directly; no workspace umbrella/edit facade is attached to `ShellWindow`.
- Packet-owned graph edit paths now call explicit per-action effect methods instead of repeating selected-node notification, workspace-tab refresh, script-editor sync, history invalidation, scene refresh, and graph-hint clusters inline.

## 2026-05-31 Shell Services Bundle Update

- `ShellWindowComposition` now exposes one `services: ShellServices` field. The services bundle groups state, primitives, preferences/theme/status, workspace/library, controllers, presenters, runtime services, context bridges, graph actions, and QML context bindings.
- `ShellWindow.shell_services` is the stable shell-owned seam for future shell cleanup. Runtime and bridge objects still keep their existing QML context names; QML context internals are read from `shell_services.qml_context` rather than host-attached private fields.

## 2026-05-31 Shell Facade Retirement Update

- `window_state_helpers.py` has been deleted. `ShellWindow` imports the focused `window_state` modules directly and inherits their explicit mixin classes instead of mutating the class body from aggregate facade binding dictionaries.
- `WINDOW_STATE_FACADE_BINDINGS` and `SHELL_WINDOW_FACADE_BINDINGS` are retired. New shell host methods should be owned directly by `ShellWindow` or routed through the responsible controller, presenter, or bridge.

## 2026-05-29 status strip execution navigation update

- Shell status-strip items can request execution-node focus through `StatusItemModel.requestAction(...)`; composition wires engine, jobs, and notifications through the existing shell host rather than a new bridge.
- Metrics text includes disk read/write throughput and can hide FPS when the telemetry source chooses not to publish it.

## 2026-05-29 status bar layout preference update

- Graphics Settings now owns a persisted `graphics.shell.status_bar_layout` choice with `option_1` as the default segmented status strip and `option_2` as the telemetry HUD status strip.
- `ShellStatusStrip.qml` renders both visual layouts from the same status models, graphics mode bridge, and execution-node click routing.

## 2026-05-29 FPS telemetry preference update

- Graphics Settings owns `graphics.shell.show_fps_telemetry`, defaulting on, to control whether status metrics publish FPS text.
- Status-bar layouts keep hiding FPS by omission: when the metrics text has no `FPS:` token, Option 1 has no FPS chip and Option 2 has no FPS gauge.

## 2026-05-29 status bar sparkline history correction

- Option 2 status-bar CPU, RAM, and disk sparklines are real rolling histories retained by `ShellStatusStrip.qml`; they are not decorative generated waves.

## 2026-07-11 Performance Ownership

- Shell composition creates stable bridge/service facades eagerly but defers tabular, Jupyter, plot, viewer/binder, and disabled folder-explorer internals. Add-On Manager/fullscreen retained loaders are QML-shell owned, not presenter-owned.
- Theme/tooltip and library/inspector projections cache only against their existing theme, policy, registry, or workflow revisions; no generic cache layer was introduced.
