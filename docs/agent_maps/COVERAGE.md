# Agent Map Coverage

This file records the current navigation owners for live source. Historical
implementation studies are intentionally excluded.

## Layer coverage

| Source area | Primary map | Main responsibility |
| --- | --- | --- |
| `ea_node_editor/graph` | [Graph Domain](subsystems/graph_domain.md) | Graph records, invariants, mutation, transforms, and workspace state |
| `ea_node_editor/execution` | [Execution](subsystems/execution.md) | Runtime snapshots, protocol, workers, node-scoped result identity, current data-port consumption, invalidation, and workspace retirement |
| `ea_node_editor/persistence` | [Persistence](subsystems/persistence.md) | Project codecs, migrations, artifacts, and sessions |
| `ea_node_editor/nodes` | [Nodes And Built-ins](subsystems/nodes_registry_builtins.md) | Registry, contracts, built-ins, packages, and plugins |
| `ea_node_editor/addons` | [Add-ons](subsystems/addons.md) | Add-on records, dependency-gated catalogs, runtime helpers, backend contributions, and Mechanical runtime/examples/help with nullable catalogue projection |
| `ea_node_editor/common` | [Supporting Runtime Assets](subsystems/supporting_runtime_assets.md) | Dependency-light helpers shared across subsystem boundaries |
| `ea_node_editor/ui` | [UI Shell](subsystems/ui_shell.md) | Shell composition, controllers, presenters, and native hosts |
| `ea_node_editor/ui_qml` | [QML Shell And Bridges](subsystems/qml_shell_and_bridges.md) | QML components, bridges, payloads, and graph surfaces |
| `ea_node_editor/runtime_contracts` | [Supporting Runtime Assets](subsystems/supporting_runtime_assets.md) | Data types, carriers, trees, intervals, and runtime references |
| `ea_node_editor/workspace` | [Workspace And Projects](subsystems/workspace_projects_session_library.md) | Workspace navigation, project sessions, and library state |
| `ea_node_editor/custom_workflows` | [Supporting Runtime Assets](subsystems/supporting_runtime_assets.md) | Reusable workflow storage and runtime support |
| `ea_node_editor/telemetry` | [Supporting Runtime Assets](subsystems/supporting_runtime_assets.md) | Telemetry and diagnostics |

## Cross-layer feature routes

The viewer-session route owns the engineering interactor's native surface boundary, established before host attachment so OpenGL viewers can coexist with the Qt Quick graphics backend.

Panel value interpretation spans the passive surface editor/badge, data-control runtime, and project/fragment property migration. The passive surfaces map owns UI/runtime evidence; serialization migration owns the legacy flag conversion.

Shared node-toolbar Expand/Collapse and Run-options icons are owned by the floating-toolbar route and the shell icon registry.
The surface loader retains action owners for active collapsed-node toolbars; hidden body input and native viewer/plot activity remain disabled.
Ordinary active/compile-only cards fit current content even with saved custom dimensions; dedicated and passive surfaces retain manual sizing. Standard widths separate top-level port columns from settings headers and expanded controls. Graph Scene Payload owns sizing/anchor coverage and the real-canvas toggle regression.
Graphics Settings > Canvas > Nodes offers app-persistent expanded-width retention through the workspace presenter and scene-bound payload provider; ordinary card height still fits visible settings.
Settings-section size transitions use shared 180 ms width/height animations with interpolated headers and port anchors, clipped revealed controls, and presentation-only member grips during collapse. Tagged canvas geometry synchronizes connections and yields to manual resize ownership; Surface Input owns the animation regression.

- [Graph Scene Payload And Projection](feature_routes/graph_scene_payload_and_projection.md)
- [Graph Canvas Input Layers](feature_routes/graph_canvas_input_layers.md)
- [Edge Routing, Labels, And Progress](feature_routes/edge_routing_labels_progress.md)
- [Surface Input And Inline Controls](feature_routes/surface_input_and_inline_controls.md)
- [Port Availability And Default Values](feature_routes/port_availability_and_default_values.md)
- [Plotter Nodes](feature_routes/plotter_nodes.md)
- [Tabular Data Add-on And Preview](feature_routes/tabular_data_addon_preview.md)
- [MARS Solver Add-on](feature_routes/mars_solver_addon.md)
- [Neutral CAD/FE Engineering Viewer](feature_routes/neutral_cad_fe_engineering_viewer.md)
- [Managed Artifacts And Project Data](feature_routes/managed_artifacts_project_data.md)
- [Project Session Files And Managed Artifacts](feature_routes/project_session_files_managed_artifacts.md)
- [Workspace Tabs, Library, And Context Menus](feature_routes/workspace_tabs_library_context_menus.md)
- [Core Integrations: File, Process, Email, Spreadsheet](feature_routes/core_integrations_file_process_email_spreadsheet.md)
- [SSH/SFTP Nodes](feature_routes/ssh_sftp_nodes.md)
- [Performance Harness And Graph Stress](feature_routes/performance_harness_graph_stress.md)
- [Retained Work-Packet QA Evidence And Spec Navigation](feature_routes/work_packet_docs_status_qa.md)

## Current ownership notes
- Shared QML surface metrics preserve projected port-row heights for both node grips and rendered wire endpoints, including Media Panel at custom graph text sizes; the edge-routing map owns this alignment regression.
- The native COREX splash background, original emblem at 115% reference size, and
  independent presentation animation are owned by `ui/splash/opening_screen.py`.
  The [splash route](feature_routes/shell_startup_qml_context_splash.md) owns startup
  contract tests and the deterministic native preview command; app handoff timing remains unchanged.
- Imported project artifacts carry Path runtime descriptors. Staging remains in `ProjectFilesService`; authored-property admission and integrity checks remain in `RuntimeArtifactService`; Panel preserves admitted carriers through its existing execution helper. The project-files, execution, surface-input, and clipboard maps cover this handoff and its real-process tests.
- Shared external canvas imports are owned by `ui/shell/controllers/canvas_import_controller.py`, with MIME/choice construction in `ui/shell/clipboard_paste_nodes.py`, the native chooser/capture in `ui/shell/`, and one graph-scene batch in `ui_qml/graph_scene_mutation/node_creation_batch.py`. The clipboard/history route covers import behaviour; the graphics route covers the shared Automatic/Ask app preference and its two controls.
- Port-row sizing reserves editor height only for a nonempty `inline_editor`; stored input defaults alone do not create extra vertical space.
- Shared header diagnostics use external warning/error circles with no title-width reservation; the header owns placement, tooltip/accessibility, and failure precedence.

- Canvas grids are one procedural GPU quad under `GraphCanvasBackground.qml` / `GraphCanvasGridShader.qml`, aligned immediately with live viewport state. Point marks retain compact logical-pixel size and background-aware contrast at high DPI. Software uses the single Canvas painter; the graph-canvas map owns rendering tests and the packaging map owns shader baking/distribution.

- Context-menu chrome and keyboard selection are shared by `ShellContextMenu.qml`; `ShellContextPopup.qml` owns overlay placement, scrolling, dismissal, and focus restoration for port, Folder Explorer, tab, and workflow popups. Native standard editor/dialog menus share the `QMenu` stylesheet rules in `ui/theme/styles.py`.

- Shell projection ownership is direct: `library_projection.py` owns Library rows, filters, category ancestors/options/tree, custom-workflow discoverability, and display projections from one cached combined item source; `inspector_projection.py` owns selected-node projection; `quick_insert_projection.py` owns canvas/connection search and ranking. `LibraryPresenter` caches one category tree, has no registry-category cache, and projects grouped/display rows lazily; `NodeRegistry` has no Library query API.
- Inspector selection performance is owned by the QML Shell map: detail snapshots and runtime-schema projection follow visible Properties demand, stable keyed rows retain drafts, groups initialize on first expansion, and each property creates only its effective editor. The Performance route owns composed-shell selection-to-render measurements.
- `GraphCanvasHostPresenter` directly owns graph cursor application, passive-node/flow-edge style dialogs and presets, style clipboard operations, flow-edge labels, and their scene mutations. `ShellHostPresenter` retains app-wide/native dialog and import policy only; `ShellWindow` has no graph cursor/style facade slots.
- Workspace shell ownership is direct: `WorkspaceSelectionContext`, `WorkspaceNavigationController`, `WorkspaceEditController`, `WorkspaceDropConnectController`, `WorkflowLibraryController`, and `WorkspacePackageIOController` are composed explicitly. One shared `MutationUiEffects` is injected into edit/drop, while `GraphActionController` calls concrete owners without string dispatch or umbrella fallbacks.
- Tabular ownership is split without a second service: `loader_cache_service.py` coordinates refs, records, cache lifecycle, locks, and eviction; `source_backends.py` owns format IO/conversion; `preview_query.py` owns one normalized query and the optimized Arrow plus bounded Python evaluators.
- Media Panel action ownership is direct: `ui/shell/media_panel_action_service.py` is the sole QObject for crop, frame capture, timestamp annotation, trim replace/copy, artifact staging, and trim worker/QThread lifecycle. `ui/media_video_state.py` still owns Python normalization and `GraphMediaVideoPlaybackCore.qml` still owns per-renderer playback/seek/clip/bookmark/primer behavior; no singleton player or fullscreen lifecycle redesign was introduced.
- Incremental execution freshness, invalidation closure, settlement acceptance, and reset notifications are execution-owned. Shell/QML retain only bounded record-ID-selected presentation caches, exact node cleanup, and the transport-only current/expired projection.
- Shell execution ownership is direct: `RunEventController` is the sole runtime-event intake; `RunController` owns commands, preview, dispatch, Auto, Trigger, pause/resume/stop, and history invalidation; `RunProjectionController` alone owns node execution sets, elapsed/warning state, accepted-output observations, solution facts, port availability, failure focus, run-control status, and their signals over the one shared `ShellRunState`.
- Durable solution selection/publication and project-save snapshot/adoption tokens remain execution-owned through strict backend/factory ports. Persistence implements immutable schema-1 generation merge/validation plus bounded exact-candidate GC. `ProjectDocumentIOService` alone coordinates guarded copy-on-write artifacts, images, solution candidate, canonical `.cxproj` publication, raw reopen, no-I/O runtime/live adoption, and post-success cleanup.
- `ProjectFilesService` owns synchronous staged payload target/path creation, writes, entry registration, and artifact-store metadata publication. `ProjectSessionController` is the public staging facade and emits one success signal; `ShellHostPresenter` owns dialogs and import policy only. Clipboard/media and Jupyter create through the controller, while `ProjectDocumentIOService` retains copy-on-write Save/Save As publication, adoption, and cleanup.
- Viewer invalidation epochs are participant-local transport safety facts: prepared runs stage process/trusted/external snapshots plus an independent high-level/Bridge projection, worker preflight uses only the selected concrete view, and concrete responses translate to projection epochs only after local validation. Context installation is separate from validation/adoption; the Bridge has one committed partial-run adoption path, and global reset/legacy-direct paths remain explicit. Commit uses high-level active then child state-before-viewer locking, callback-free pinned delivery, all-or-none apply, and an irreversible gate-clearing finalizer. Failure remains byte-identical; only a state-free selected service may baseline-align its selected concrete workspace epoch. Project and generation replacement remain workspace-global.
- Tabular's seven executable declarations are owned by `addons/tabular_data/function_nodes.py`; its Path inline editor is disabled, retaining the port and inspector/surface source selection. Dependency gating and bundle publication stay under the add-on catalog, while refs, preview, property editing, native preload, and execution helpers remain in their existing Tabular owners.
- MARS's three executable declarations are owned by `addons/mars/function_nodes.py`; its catalog owns dependency gating, package provenance, and bundle publication while `nodes.py` and `runtime.py` retain job construction, JSONL execution, cancellation, and artifact publication.
- Mechanical's dependency-gated semantic values remain in `addons/mechanical/contracts.py`; `runtime.py` and `inspection.py` own Open, accepted discovery, and eleven-mode data-only Search execution, `tables.py` owns full-fidelity definition/result/probe/worksheet extraction, `graphics.py` owns saved/current cameras plus deterministic viewport image batches and rollback-protected optional PNG publication, `commands.py` owns scoped scripts plus deterministic marker-owned APDL snippets with verified rollback, and `saving.py`/`workbench.py` own standalone and whole-Workbench native save staging, documented native semantic snapshots, reconnect identity, and primary/companion publication rollback. `function_nodes.py` and `property_edit.py` own the eight nodes' shared grouped control metadata, fresh primary-group defaults, and contextual editor conditions; central Mechanical title-icon masks remain gated by trusted repo add-on provenance. Its run/workspace service and dedicated bounded owner process keep native imports out of the shell and shared execution worker. Native working copies use source-family APIs; structured native Open/Script/Snippet/Save data crosses a bounded UTF-8 owned-file plus ASCII hash-receipt boundary before existing owner spools/runtime codecs.
- Mechanical's neutral example/documentation owner is `scripts/mechanical_catalogue/generate_examples.py` plus `docs/MECHANICAL_CATALOGUE.md`. The generator publishes three fixed-ID blank-path projects through the current registry and normal serializer, while `tests/mechanical_catalogue/test_examples.py` protects exact ports/groups/edges and validated fixture-path injection. Live execution of those compositions remains the separate T18 acceptance boundary.
- Signal Plot declaration/execution is owned by `nodes/builtin_functions/plot_signal.py`,
  normalization/rendering by `execution/signal_plot_inputs.py` and `execution/signal_plot_renderer.py`,
  metadata-only selectors by `nodes/builtins/plot/signal_schema.py`, and navigation by the plotter route.
- Immutable scientific ArrayValue/TableValue/SeriesValue contracts and the bounded codec live in
  `runtime_contracts/scientific_values.py` and `scientific_codec.py`; native script/plugin boundaries
  preserve isolation without copying for each built-in reader. T04 pipeline/budget proof is owned by
  `tests/test_signal_plot_scientific_integration.py` and `scripts/benchmark_signal_plot.py`.
- Scientific process/external worker transport follows the existing manifest-owned
  `fast.serial.pytest` route; native Signal Plot integration remains in its focused/fast route.
- Declarative node controls are shared metadata-to-QML behavior owned by the
  node registry, graph-scene projection, and shared graph controls. Rendered
  list/group/control geometry belongs to Surface Input; payload and settings-band
  calculation belongs to Graph Scene Payload.
- Active-data wire behavior is owned jointly by graph mutation/history, graph-scene projection, graph-canvas input and action routing, pure `EdgePaintPolicy.js`, and the retained/canvas edge renderers; `EdgeMath.js` owns shared anchors, while passive-only and `flow` edges remain under their existing routes.
- Canvas surface-editor overlays are directly owned by `GraphCanvasSurfaceEditorOverlays.qml`; RootLayers exposes ten live host/open aliases and one dispatch method without duplicating Web Address, Timestamp, Number Slider, Select, or Panel state.
- Standard input/output port rows are directly shared by `GraphNodePortRow.qml`, and `GraphNodePortContextMenu.qml` owns the access/modifier/Principal/dynamic action descriptors and dispatch in a shared `ShellContextPopup`. `GraphNodePortsLayer.qml` retains models, dynamic scheduling/mutations, notch cache with a fixed 54 x 108 raster shared by ordinary and grouped ports, aggregate rectangles, context/edit state, menu anchor/opening, add controls, and the minimal direction-only children without adding per-port/menu objects or loaders. Dynamic add/remove handles share 9 px notch-corner centers, 6/14 px resting/active sizes, direction-only remove tooltips, port-hover reveal with a recoverable empty-group fallback, and a 2 px hover-handoff overlap with their owning port regions.
- Action presentation is pure and QML-owned by `GraphActionPresentation.js`; seven files across the original six canvas/menu/toolbar/host presentation surfaces use it for lookup, normalization, field shaping, menu/popover extraction, and stable ordering after the node-toolbar popover extraction. `GraphCanvasActionRouter.qml` remains the sole dispatch owner, including the shared native-dialog fallback when a node has no inline title editor, and Python/QML feature owners retain policy/lifecycle decisions.
- Node-toolbar popover state, placement, focus, hover bridge, dirty-draft flush, and source-storage/bookmark/font/PDF panel callbacks are directly owned by `GraphNodeToolbarPopoverHost.qml`. Its root replaces the former inline bridge Item; `GraphNodeFloatingToolbar.qml` retains chrome/anchor/grace, primary buttons, run menu, live aliases, and thin public delegation without adding always-live objects.
- Graph-canvas QML composition is direct: `GraphCanvasStateBridge` reads persisted graphics, session state/signal/size, app preferences, execution/project, scene, and viewport from exact owners; `GraphCanvasCommandBridge` receives exact run, scope/hint, Inspector, Library, T14 edit/drop, T15 media, graphics, host, scene, and viewport owners. Neither bridge has `canvas_source` or a shell-window fallback. Plain `CanvasExportPresenter` owns export outside the QML bridge. Bridge identities, context names, and meta-object bytes remain unchanged.
- Content-fullscreen and viewer/plot composition are direct: shell composition supplies live providers/callbacks to `ContentFullscreenBridge`, `ViewerSessionBridge`, `ViewerControlBridge`, `ViewerHostService`, and `PlotHostService`; ProjectSession owns artifact-store metadata publication. The four viewer/plot owners retain dynamic replacement visibility and exactly two bounded construction-cycle callbacks, with no `ShellWindow` locator, policy facade, compatibility alias, dependency bag, or QML API change.
- Native cached-preview demotion uses two distinct plain `NativePresentationHandoff` instances, one per viewer/plot host. Shared pending/serial/render-gate/timeout/queue mechanics live there; host-specific capture/completion, widgets, binders, windows, policy, and overlay geometry remain separate.
- `MainWindowShellTestBase` owns shared full-shell QML traversal and Inspector lookup; image/PDF subclasses own QML reference retention. T25 collects windowless bridge/frame/mutation policy through direct wrappers and routes the isolated lifecycle wrapper only through manifest child targets; `SharedMainWindowShellTestBase` reuse remains bounded by those child processes.
- Exact feature-map citations own QML components when present; the broader QML
  or graph-canvas subsystem remains the fallback only when no feature map cites
  that exact component path.
- Decorator-driven Python Script declarations are owned jointly by the node
  registry/parser, graph-owned atomic Apply, worker revalidation, and generic persistence.
  Shared canvas handles edit that source through dynamic-port mutations; canvas
  commands and workspace editing own dirty-draft protection and clean-editor refresh.
- Deterministic `.cxpkg` schema-2 archive IO, static package validation, and
  immutable function-package asset provenance are owned by the Nodes map;
  title-icon projection remains owned by the icon and graph-scene routes.
- Open-session registry reload safety is shared by the graph compatibility checker,
  nodes candidate/package transaction, execution identity/admission guard, and the
  shell registry replacement coordinator; it is not a legacy compatibility layer.
- Mechanical selected-model export keeps Workbench ownership and publication in the existing Save route, while a short-lived separate same-release Mechanical owner process alone opens the private `.dsdb` and validates the standalone `.mechdb`/`.mechdat` stage. Mechanical Workbench save validates the qualified HDF5 state pair only after all ordinary checks leave its working-to-stage SHA as the sole mismatch. This closed-schema comparison stays in `addons/mechanical/workbench.py` and the existing owner timeout; all other phases/files keep exact-byte validation.
- Add-on state preparation is pure and add-on-owned in `addons/state_changes.py`;
  the shell registry replacement coordinator is the sole candidate, publication,
  persistence, notification, and reverse-rollback authority.
- Novice plugin authoring is shared by the nodes-owned static/save backend, native
  PyQt dialog/editor, and shell controller/File actions; reload still routes only
  through the guarded registry replacement coordinator.
- The reserved built-in bundle owns exactly 76 inert function declarations under
  `nodes/builtin_functions/`; trusted helpers and data contracts remain under
  `nodes/builtins/`, and the original migration inventory pins 53 trusted
  exceptions across its 139-row catalog baseline; the current catalog has 147 rows.
- Public filesystem discovery is nodes-owned in `plugin_loader.py`; shared
  function materialization/fingerprinting lives in `function_bundle.py`, built-in
  contributions in `builtin_catalog.py`, and trusted backend contributions in
  `addons/registry_contributions.py` without forwarding aliases.
- Node specification structure is validated purely by `nodes/spec_validation.py`
  against an explicit staged/live `DataTypeCatalog`; port and instance/dynamic
  resolution lives directly in `nodes/instance_resolution.py`, and dependency-light
  property coercion lives in `nodes/property_coercion.py`. Generic property
  normalization lives in `nodes/property_normalization.py`.
  `NodeRegistry` retains storage, atomic staged composition/revalidation/rollback,
  fingerprints, registry-aware `resolve_spec`, and the three catalog-aware
  normalization API entry points without built-in-specific policy.
- Public node authoring is now only the 17-name top-level `corex` function SDK.
  `ea_node_editor.nodes` is internal, its former `types.py` barrel is removed,
  and trusted descriptor decorators remain owned by the Nodes map for the exact
  internal/add-on boundary only.
- Public plugin guidance is `docs/PLUGIN_AUTHORING_GUIDE.md` plus the Signal
  Plot and strain examples under `docs/examples/`; migration failures route to
  `docs/PLUGIN_MIGRATION_GUIDE.md`. The old Signal Plot declaration is retained
  only as an internal visual fixture under `tests/fixtures/node_controls/`.
- The exact current catalog is `tests/fixtures/node_catalog/current_repo_owned_catalog.json`;
  `tests/repo_owned_catalog_fixture.py` loads its 147 rows for catalog, migration,
  solution-reuse, and documentation checks. Closeout evidence lives in
  `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`.
- Core integrations contribute eight reserved function entries plus the trusted
  Path Pointer and Folder Explorer exceptions. SSH/SFTP contributes six reserved
  function entries, Paramiko-free value contracts, and a worker-lazy Paramiko runtime.
- Data-control, engineering import/viewer, geometry, spatial, mesh, FEM, AI,
  security, reporting, rich-value, and viewport execution declarations are in the
  reserved function bundle; their trusted contracts, services, size resolvers,
  session/handle ownership, and neutral COREX identifiers remain with the existing
  helper modules.
- Retired import and placeholder surfaces are absent from current ownership.
- Typed connection reliability keeps relation authority in `runtime_contracts/data_types.py` plus `graph/effective_ports.py`, recommendation tiers in `ui/shell/quick_insert_projection.py`, default-port Library/filter projection in `ui/shell/library_projection.py`, and restrictive post-insertion endpoint checks in `workspace_drop_connect_controller.py`. Public/Python Script input/output types are explicit; malformed workflow/Library/QML previews never become Any. The trusted repo-owned primary/accepted Any audit is exactly 20 endpoints, with existing MARS artifact maps retained.

## Hygiene

- Model Viewer dynamic inputs reuse graph-owned port mutations and generic QML
  authoring controls. Trusted node registration owns the scene-group metadata;
  engineering execution owns v2 ordered layers and source leases; the binder and
  viewer bridges own per-ID appearance, selection, visibility, and queries.
  Viewer Python/QML geometry reserves the resting dynamic-add dot; label widths
  include removable controls, and hover targets can extend beyond the chrome.

- Update the owning map when source/test ownership moves.
- Regenerate `docs/agent_route_index.*` and
  `docs/source_test_file_index.md` after path changes.
- Run `scripts/check_agent_maps.py` after every map edit.
