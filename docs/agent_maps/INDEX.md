# Agent Map Atlas

This atlas is an advisory lookup layer for agents and maintainers, not a requirements or ownership authority. Use it to compress broad discovery and attach owner, boundary, and focused-test context to source evidence.

## Agent Quick-Start

1. **Lead with exact evidence for narrow tasks** — search a known file, symbol, UI label, error, setting, or test with bounded `rg`; inspect the first useful hits instead of asking the fuzzy router to rediscover them.
2. **Use navigation for ambiguity** — `./venv/Scripts/python.exe scripts/nav.py find <term>` returns a compact advisory owner/test capsule for broad or cross-layer work. Exact alias/title/component matches are labeled exact; other results explicitly say no owner is yet confirmed. Use `route`, `qml`, or `source` when the index family is already known.
3. **Verify, then open one map** — confirm the candidate against source before choosing an owner or insertion point. Use `nav.py source <path>` to attach map/test context to a discovered file and `nav.py line <path> <symbol-or-heading>` for its current line. Open only the relevant map when its boundaries or guard rails matter.

Indexes are generated — regenerate with `scripts/generate_agent_route_index.py`, then validate with `scripts/check_agent_maps.py` after any map edit.

**Shared helpers:** dependency-light utilities used by 2+ subsystems live in `ea_node_editor/common/` (`protocols.py`, `coercions.py`, `payload_tools.py`, `path_safety.py`, `artifact_refs.py`) — check there before adding a subsystem-local copy.

## Maintenance Contract

- [Maintenance Rules](MAINTENANCE.md)
- [Coverage Matrix](COVERAGE.md)
- [Generated Agent Route Index](../agent_route_index.md)

Before broad exploration, open the coverage matrix and the most relevant subsystem or route page. After changing feature routing, architecture ownership, public contracts, verification ownership, or common insertion points, update the affected map and coverage row in the same change.

## Subsystem Maps

- [Startup, Bootstrap, And App Lifecycle](subsystems/startup_and_bootstrap.md)
- [App Preferences, Settings, And Platform Paths](subsystems/app_preferences_settings_platform_paths.md)
- [UI Shell, Controllers, And Presenters](subsystems/ui_shell.md)
- [PyQt Dialogs, Theme, And Editor Support](subsystems/pyqt_dialogs_panels_theme_editor.md)
- [QML Shell And Bridge Layer](subsystems/qml_shell_and_bridges.md)
- [Graph Canvas Rendering, Input, And Viewport](subsystems/graph_canvas.md)
- [Graph Domain, Mutation, Transforms, And Hierarchy](subsystems/graph_domain.md)
- [Persistence, Documents, Artifacts, And Migrations](subsystems/persistence.md)
- [Execution Snapshot, Client, Worker, And Protocol](subsystems/execution.md)
- [Nodes, Registry, Built-ins, And Plugin Loading](subsystems/nodes_registry_builtins.md)
- [Add-ons](subsystems/addons.md)
- [Workspace, Projects, Session, And Library](subsystems/workspace_projects_session_library.md)
- [Web Assets, Web Host, Chromium, And Excalidraw](subsystems/web_assets_host_chromium_excalidraw.md)
- [Viewer Surfaces, Native Overlays, And Fullscreen](subsystems/viewer_surfaces.md)
- [Passive, Media, And Tabular Surfaces](subsystems/passive_media_tabular_surfaces.md)
- [Assets, Icons, Title Icons, And Theme Assets](subsystems/assets_icons_theme.md)
- [Telemetry, Help, Benchmarks, Custom Workflows, And Runtime Contracts](subsystems/supporting_runtime_assets.md)
- [Packaging And Generated Assets](subsystems/packaging_generated_assets.md)
- [Verification, Testing, And Docs Hygiene](subsystems/verification_testing_docs_hygiene.md)

## Testing Maps

- [Verification Runner](testing/verification_runner.md)
- [QML And Graph Surface Tests](testing/qml_and_graph_surface_tests.md)
- [Shell Isolation Tests](testing/shell_isolation_tests.md)
- [Docs, Traceability, And Hygiene Tests](testing/docs_traceability_hygiene.md)

## Feature Routes

- [Graph Canvas Feature Recipes](feature_routes/graph_canvas_feature_recipes.md)
- [Graph Actions And Context Menus](feature_routes/graph_actions_and_context_menus.md)
- [QML Bridge Wiring](feature_routes/qml_bridge_wiring.md)
- [Graph Scene Payload And Projection](feature_routes/graph_scene_payload_and_projection.md)
- [Durable Node Linking](feature_routes/durable_node_linking.md)
- [Graph Canvas Input Layers](feature_routes/graph_canvas_input_layers.md)
- [Surface Input And Inline Controls](feature_routes/surface_input_and_inline_controls.md)
- [Passive Surface Loading And Contracts](feature_routes/passive_surface_loading_contracts.md)
- [Group Backdrops, Peek, And Membership](feature_routes/group_backdrops_peek_membership.md)
- [Floating Toolbar And Checked States](feature_routes/floating_toolbar_checked_states.md)
- [Edge Routing, Labels, And Progress](feature_routes/edge_routing_labels_progress.md)
- [Node Title Icons And Theme Sources](feature_routes/node_title_icons_theme_sources.md)
- [Shared Graph Typography](feature_routes/shared_graph_typography.md)
- [Port Availability And Default Values](feature_routes/port_availability_and_default_values.md)
- [Node Execution Visualization](feature_routes/node_execution_visualization.md)
- [Persistent Node Elapsed Times](feature_routes/persistent_node_elapsed_times.md)
- [Nested Node Categories, Subnodes, And Grouping](feature_routes/nested_node_categories_subnodes_grouping.md)
- [Workspace Tabs And Library Context Menus](feature_routes/workspace_tabs_library_context_menus.md)
- [Project Session, Project Files, And Node Files](feature_routes/project_session_files_managed_artifacts.md)
- [Workflow Library And Drop Connect](feature_routes/workflow_library_drop_connect.md)
- [Run Controller And Selected Workspace State](feature_routes/run_controller_selected_workspace_state.md)
- [Shell Startup, QML Context, And Splash](feature_routes/shell_startup_qml_context_splash.md)
- [Viewer Session, Native Overlay, And Fullscreen](feature_routes/viewer_session_overlay_fullscreen.md)
- [Neutral CAD/FE Engineering Viewer](feature_routes/neutral_cad_fe_engineering_viewer.md)
- [Media, Image, Video, PDF, And Mail Nodes](feature_routes/media_image_video_pdf_refocus.md)
- [Web Viewer And Chromium Website Node](feature_routes/web_viewer_chromium_node.md)
- [Excalidraw Web Host And Real Editor](feature_routes/excalidraw_web_host_real_editor.md)
- [Tabular Data Add-on And Preview](feature_routes/tabular_data_addon_preview.md)
- [Plotter Nodes](feature_routes/plotter_nodes.md)
- [Add-on Manager](feature_routes/addon_manager.md)
- [MARS Solver Add-on](feature_routes/mars_solver_addon.md)
- [Core Integrations: File, Process, Email, Spreadsheet](feature_routes/core_integrations_file_process_email_spreadsheet.md)
- [SSH/SFTP Nodes](feature_routes/ssh_sftp_nodes.md)
- [Clipboard, Undo, Redo, And Mutation History](feature_routes/clipboard_undo_redo_mutation_history.md)
- [Graphics Settings, Themes, And Preferences](feature_routes/graphics_settings_themes_preferences.md)
- [Tooltips And Tooltip Tiers](feature_routes/tooltips_and_tiers.md)
- [Performance Harness And Graph Stress](feature_routes/performance_harness_graph_stress.md)
- [Workspace-Scoped Node Files And Data](feature_routes/managed_artifacts_project_data.md)
- [Serialization, Migration, And Legacy Rejection](feature_routes/serialization_migration_legacy_rejection.md)
- [Retained Work-Packet QA Evidence And Spec Navigation](feature_routes/work_packet_docs_status_qa.md)
