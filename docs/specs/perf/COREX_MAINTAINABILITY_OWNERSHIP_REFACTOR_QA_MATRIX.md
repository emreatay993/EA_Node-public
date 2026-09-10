# COREX Maintainability And Ownership Refactor QA Matrix

Status: `COMPLETED — T00–T08 ACCEPTED`

This is the single task, test-migration, performance, and review ledger for
`docs/PLAN_COREX_MAINTAINABILITY_OWNERSHIP_REFACTOR.md`.

## Locked Baseline

| Fact | Value |
| --- | --- |
| Starting branch | `main` |
| Starting commit | `5a4ae4b8` |
| Upstream at start | `origin/main` at `5a4ae4b8` |
| Publication | Local commits only; no push |
| Protected modified path | `docs/specs/INDEX.md` |
| Protected untracked path | `docs/PLAN_COREX_Physical_Simulation_Backend.md` |
| Protected untracked path | `scripts/Strain_Gage_Positioning/modular_version/strain_candidate_points.csv` |
| Performance policy | Advisory matched evidence; no timing-only rollback |

## Compaction Recovery Checklist

Before continuing after compaction, read these in order:

1. `AGENTS.md`
2. `docs/PLAN_COREX_MAINTAINABILITY_OWNERSHIP_REFACTOR.md`
3. this QA matrix
4. `git status --short --branch`
5. `git log -1 --oneline`
6. the next `IN PROGRESS` or `NOT STARTED` task row below

Do not edit until the protected dirty paths and last accepted commit are
reconciled with this ledger.

## Task Ledger

| Task | Status | Writer | Conservative write scope | Focused evidence | Performance evidence | Independent review | Accepted commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T00 Plan and baseline | `ACCEPTED` | Orchestrator | Plan, this ledger, exact spec-index additions | Full dry-run, traceability, links, diff hygiene, and 582-test affected inventory passed; `qmltestrunner.exe` unavailable | Fast baseline: 4,543 passed, 2 skipped, 18 existing warnings; logs under `artifacts/verification_logs/20260901_042328/` | Two delegated read-only baseline verifiers returned no findings | `bc4233f6` |
| T01 Package policy | `ACCEPTED` | `t01_package_writer` | Nodes package schema, add-on contracts, direct tests/maps | Final focused acceptance: 235 tests and 90 subtests passed; Ruff, compile, maps, traceability, links, and diff hygiene passed | Discovery/import/export medians changed `3.030/8.717/7.220 ms` to `2.483/8.333/6.621 ms`; no added traversal and deterministic bytes retained | `t01_package_reviewer`: initial two P1/two P2/one P3 findings fixed; re-review `CLEAR` | `fa3b8ff9` |
| T02 Runtime contracts | `ACCEPTED` | `t02_runtime_writer` | Common artifact grammar, defining runtime modules, direct imports/tests/maps | Final combined acceptance: 646 tests and 209 subtests passed with one existing PyArrow warning; Ruff, compile, maps, traceability, links, and diff hygiene passed | Exact payload hashes, round trips, copy guards, and allocation peaks unchanged; confirmed micro-regressions of `+2.66 us` ImageValue and `+0.73 us` durable decode are advisory | `t02_runtime_reviewer`: residual barrels and missing exact owner/export guards fixed; source/test re-review `CLEAR` | `e402f973` |
| T03 UI projections | `ACCEPTED` | `t03_projection_writer` | Library, Inspector, Quick Insert, direct tests/maps | Final combined run: 309 tests and 77 subtests passed; one unrelated workspace-tab shell timeout under xdist passed immediately in exact serial rerun; Ruff, compile, maps, traceability, links, diagrams, and diff hygiene passed | Exact output counts/order/hashes retained; display and Quick Insert neutral; shared grouped/display projection materially faster | `t03_projection_reviewer`: dependency inversion fixed; source/test re-review `CLEAR` | `0dc09780` |
| T04 Graph host owner | `ACCEPTED` | `t04_graph_host_writer` | Graph host presenter, shell forwarders, direct tests/maps | Final serial owner/style/bridge/architecture acceptance: 119 tests and 120 subtests passed; writer graph-surface gate 138 passed; Ruff, compile, maps, traceability, links, and diff hygiene passed | Shell create `-2.1%`; cursor `-8.1%`; reset-edge host `-21.3%`; full action `-4.9%`; object/timer/provider counts unchanged | `t04_graph_host_reviewer`: production/tests `CLEAR`; docs/maps integrated by orchestrator | `24994bae` |
| T05 Tabular query | `ACCEPTED` | `t05_tabular_writer` | Tabular coordinator, source backends, normalized query/evaluators, direct tests/maps | Final integrated acceptance: 191 tests and 75 subtests passed; closeout missing/null/non-finite/mixed-sort/collision/PyArrow-24 suite 70 passed; Ruff, compile, maps, traceability, links, and diff hygiene passed | 409.6 MiB fixture/cache/output hashes, scan/conversion counts, caps/totals unchanged; timing inconclusive; offscreen shell harness inconclusive | `t05_tabular_reviewer` and final correctness reviewer: parity, coverage, min-version, and collision findings fixed; re-review `CLEAR` | `57d4b84d`; review fix `73a92161` |
| T06 Video playback | `ACCEPTED` | `t06_video_writer` | Shared QML playback core, Python state owner, inline/fullscreen callers, direct tests/maps | Final product/media run: 181 tests and 75 subtests passed with one existing PyArrow warning; QML navigation 5 tests/171 subtests passed; Ruff, compile, maps, traceability, links, shell isolation, and diff hygiene passed | Real-MP4 comparable ready/position/unload/reload timings within `0.35 ms`; source leasing/resume correctness improved; GIF harness unrelated/inconclusive; CPU/RSS incomparable because HEAD did not decode | `t06_video_reviewer`: two decoded-media P1s, warning suppression, and dead hook fixed; re-review `CLEAR` | `dcdfd5b4` |
| T07 Residual tests | `ACCEPTED` | `t07_test_writer` | One graph-host preset test plus canonical style normalization imports | Standalone import passed; final owner/dialog/architecture/serializer acceptance 131 tests and 97 subtests passed; seven catalog guards and full dry-run passed; Ruff, compile, and diff hygiene passed | Product runtime unaffected; one unnecessary `ShellWindow` test construction removed | `t07_test_reviewer`: weakened final A/B payload assertion fixed; re-review `CLEAR` | `88cb140b` |
| T08 Closeout | `ACCEPTED` | Orchestrator | Final correctness fix, live docs, QA status, guard, independent reviews, final gates | Full verification passed all seven phases; maps, traceability, links, generated indexes, Ruff, compile, and diff hygiene passed | Consolidated advisory review: acceptable with caveats; no pause threshold or rollback condition met | Architecture and correctness reviews `CLEAR`; performance review `ACCEPTABLE WITH CAVEATS` | This closeout commit |

## Test Migration Ledger

Allowed dispositions are `retained`, `moved_to_owner`,
`replaced_by_owner_test`, `replaced_by_qml_quicktest`, `merged_equivalent`, and
`deleted_redundant`.

| Task | Old node ID | Behavior | Current owner | Disposition | Replacement node ID | Proving command | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | `tests/test_plugin_loader.py::test_addon_registration_lookup_requires_canonical_addon_id` | Canonical add-on ID lookup | Add-on catalog | `moved_to_owner` | `tests/test_addon_catalog.py::test_addon_registration_lookup_requires_canonical_addon_id` | `.\venv\Scripts\python.exe -m pytest tests/test_addon_catalog.py -q` | `PASS` |
| T01 | `tests/test_plugin_loader.py::test_discover_addon_records_reports_generic_manifest_and_state` | Add-on manifest/state projection | Add-on catalog | `moved_to_owner` | `tests/test_addon_catalog.py::test_discover_addon_records_reports_generic_manifest_and_state` | `.\venv\Scripts\python.exe -m pytest tests/test_addon_catalog.py -q` | `PASS` |
| T01 | `tests/test_plugin_loader.py::test_plugin_loader_addon_record_discovery_delegates_to_addon_catalog` | Forwarding-only loader alias | Removed forwarding path | `deleted_redundant` | Add-on owner tests above plus architecture absence guard | T01 focused package/add-on/architecture suite | `PASS` |
| T02 | All affected runtime/artifact/worker test node IDs | Runtime carrier, codec, durable, and artifact grammar behavior | Defining runtime/common owners | `retained` | Same node IDs with direct defining-module imports; exact owner/export/union absence guards added | T02 focused runtime, persistence, worker, UI caller, and architecture suites | `PASS` |
| T02 | `tests/test_architecture_boundaries.py::GraphArchitectureBoundaryTests::test_execution_value_codec_is_contract_compatibility_export` | Execution compatibility-codec export | Removed compatibility barrel | `replaced_by_owner_test` | `tests/test_architecture_boundaries.py::GraphArchitectureBoundaryTests::test_runtime_value_contracts_have_direct_owners_and_common_stays_leaf` | T02 architecture boundary suite | `PASS` |
| T03 | 29 node IDs from `tests/test_window_library_inspector.py` | Library/Inspector/Quick Insert projection | Three defining projection owners | `moved_to_owner` | 30 replacement node IDs across `test_library_projection.py`, `test_inspector_projection.py`, and `test_quick_insert_projection.py`; one combined test split in two | `.\venv\Scripts\python.exe -m pytest tests/test_library_projection.py tests/test_inspector_projection.py tests/test_quick_insert_projection.py -q` | `PASS` |
| T04 | `tests/main_window_shell/passive_style_context_menus.py::MainWindowShellPassiveStyleContextMenuTests::test_passive_node_style_slots_apply_copy_paste_and_reset_only_for_passive_nodes` | Passive style edit/copy/paste/reset | Graph host presenter | `replaced_by_owner_test` | `tests/test_graph_canvas_host_presenter.py::test_graph_canvas_host_presenter_edits_styles_through_exact_scene_owner`; `::test_graph_canvas_host_presenter_owns_passive_style_clipboard_and_mutations`; retained real-shell graph-action smoke | T04 focused owner/shell suites | `PASS` |
| T04 | `tests/main_window_shell/passive_style_context_menus.py::MainWindowShellPassiveStyleContextMenuTests::test_passive_node_propagate_style_slot_applies_to_workspace_passive_nodes` | Passive style propagation | Graph host presenter | `replaced_by_owner_test` | `tests/test_graph_canvas_host_presenter.py::test_graph_canvas_host_presenter_owns_passive_style_clipboard_and_mutations` | T04 focused owner suite | `PASS` |
| T04 | `tests/main_window_shell/passive_style_context_menus.py::MainWindowShellPassiveStyleContextMenuTests::test_flow_edge_style_slots_apply_copy_paste_reset_and_label_only_for_flow_edges` | Flow style/label/clipboard | Graph host presenter | `replaced_by_owner_test` | `tests/test_graph_canvas_host_presenter.py::test_graph_canvas_host_presenter_owns_flow_style_label_and_clipboard`; `::test_graph_canvas_host_presenter_edits_styles_through_exact_scene_owner` | T04 focused owner suite | `PASS` |
| T04 | `tests/test_main_window_shell.py::MainWindowShellHostFacadeDelegationTests::test_host_slots_delegate_nontrivial_host_logic_to_shell_host_presenter` | Mixed ShellHost/graph-host forwarding | Split app-wide and graph owners | `replaced_by_owner_test` | `::test_host_slot_delegates_app_dialog_to_shell_host_presenter`; `tests/test_graph_canvas_host_presenter.py::test_graph_canvas_host_presenter_applies_cursor_to_widget_and_quick_window`; direct style tests | T04 focused owner/shell suites | `PASS` |
| T04 | `tests/test_passive_style_presets.py::ShellPassiveStylePresetProjectScopeTests::test_shell_uses_current_project_preset_library_when_projects_switch` | Project-local style presets | Graph host presenter | `moved_to_owner` | `tests/test_passive_style_presets.py::GraphCanvasHostPresenterPassiveStylePresetProjectScopeTests::test_graph_host_presenter_uses_current_project_preset_library_when_projects_switch` | `.\venv\Scripts\python.exe -m pytest tests/test_passive_style_presets.py -q` | `PASS` |
| T04 | `tests/main_window_shell/passive_style_context_menus.py::MainWindowShellPassiveStyleContextMenuTests::test_passive_node_style_slots_apply_copy_paste_and_reset_only_for_passive_nodes` QML route portion | Real QML dispatch | Shell integration | `merged_equivalent` | `tests/main_window_shell/passive_style_context_menus.py::MainWindowShellPassiveStyleContextMenuTests::test_graph_action_bridge_routes_style_to_graph_canvas_host_presenter` | T04 real-shell route suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_sorts_text_source_by_numeric_column_both_directions` | Python sort semantics | Preview query owner | `merged_equivalent` | `tests/test_tabular_preview_query.py::test_python_preview_query_cases[descending-sort]` plus sort parity cases | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_applies_free_text_filter_and_search` | Filter/search semantics | Preview query owner | `merged_equivalent` | `test_python_preview_query_cases[filter]`; `[search]`; Arrow/Python parity nodes | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_applies_row_and_column_window_after_sort` | Sort-before-row/column window and total columns | Preview query owner | `replaced_by_owner_test` | `tests/test_tabular_preview_query.py::test_native_parquet_preview_sorts_before_row_and_column_window`; `[offset-limit]` | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_supports_multi_key_sort_and_numeric_filter` | Multi-sort/numeric filter | Preview query owner | `merged_equivalent` | `test_preview_window_arrow_and_python_match_for_query_case[multi-sort]`; `[numeric-filter]` | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_reports_scan_truncation_for_source_direct` | 200k Python cap/truncated totals | Preview query owner | `replaced_by_owner_test` | `test_preview_window_source_direct_reports_bounded_total_and_truncation`; `test_preview_window_source_direct_publishes_truncation_metadata` | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_arrow_query_matches_python_scan` | Arrow/Python common query behavior | Preview query owner | `replaced_by_owner_test` | 14 independently parametrized `test_preview_window_arrow_and_python_match_for_query_case[...]` nodes plus no-value parity nodes | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_arrow_query_matches_python_scan_for_numeric_strings` | Numeric-string typing/filter/sort | Preview query owner | `replaced_by_owner_test` | `test_preview_window_arrow_matches_numeric_string_filter_and_sort`; `test_managed_and_source_direct_queries_preserve_deliberate_source_typing` | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_arrow_query_cache_skips_full_table_read_when_too_large` | Query-table cache column reads | Preview query/cache owners | `moved_to_owner` | `tests/test_tabular_preview_query.py::test_preview_window_arrow_query_cache_reads_only_needed_columns` | T05 query suite | `PASS` |
| T05 | `tests/test_tabular_loaders.py::test_preview_window_parquet_lane_or_reports_dependency` | Native Parquet preview | Source backend/query owners | `replaced_by_owner_test` | `tests/test_tabular_preview_query.py::test_native_parquet_preview_sorts_before_row_and_column_window` | T05 query suite | `PASS` |
| T06 | Existing media/fullscreen/trim/bridge/shell node IDs | Inline/fullscreen video playback and state handoff | Shared playback core plus distinct hosts | `retained` | Same node IDs with stronger source-lease, warning, renderer, fullscreen, and normalization assertions | T06 focused media/fullscreen/bridge/shell suites | `PASS` |
| T06 | New owner coverage | Canonical Python video state | `ui/media_video_state.py` | `replaced_by_owner_test` | `tests/test_media_video_state.py::{test_video_state_normalizes_malformed_values_and_aliases,test_video_bookmarks_drop_duplicates_sort_and_cap,test_video_properties_share_state_normalization_without_transient_playing}` | `.\venv\Scripts\python.exe -m pytest tests/test_media_video_state.py -q` | `PASS` |
| T06 | Real decoded-media lifecycle gap | LoadedMedia initialization, autoplay, primer, paused handoff, source lease, parallel node, reopen, rename | Shared QML core/hosts | `replaced_by_owner_test` | Mounted real-MP4 lifecycle node in `tests/test_media_panel_qml_surface.py` using `tests/fixtures/media/video-playback.mp4` | Exact mounted node | `PASS` |
| T07 | `tests/test_passive_style_presets.py::GraphCanvasHostPresenterPassiveStylePresetProjectScopeTests::test_graph_host_presenter_uses_current_project_preset_library_when_projects_switch` | Same-presenter Project A/B style-preset isolation | Direct graph host presenter | `moved_to_owner` | `tests/test_graph_canvas_host_presenter.py::test_graph_canvas_host_presenter_uses_current_project_presets_after_model_switch` | Exact node plus focused presenter/preset/dialog suites | `PASS` |
| T07 | Residual T01-T06 shell catalog audit | Unique QML route, integration, native/lifecycle, storage, fullscreen, and project-open behaviors | Existing shell owners | `retained` | Same 51 shell-isolation targets; no catalog or manifest change | Seven catalog guards and `full --dry-run` | `PASS` |

### T03 Exact Node-ID Migration

All rows use disposition `moved_to_owner`; the final combined case has two
replacement node IDs.

| Old node ID under `tests/test_window_library_inspector.py` | Replacement node ID |
| --- | --- |
| `WindowLibraryInspectorUsageRankingTests::test_recent_usage_ranks_by_frequency_then_recency_and_ignores_unavailable_items` | `tests/test_library_projection.py::LibraryProjectionUsageRankingTests::test_recent_usage_ranks_by_frequency_then_recency_and_ignores_unavailable_items` |
| `WindowLibraryInspectorQuickInsertTests::test_canvas_quick_insert_blank_query_returns_no_results` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_canvas_quick_insert_blank_query_returns_no_results` |
| `WindowLibraryInspectorQuickInsertTests::test_canvas_quick_insert_non_empty_query_returns_matches` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_canvas_quick_insert_non_empty_query_returns_matches` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_blank_query_keeps_compatible_matches` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_blank_query_keeps_compatible_matches` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_filters_data_ports_by_type` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_filters_data_ports_by_type` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_treats_primary_and_accepted_types_as_union` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_treats_primary_and_accepted_types_as_union` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_excludes_hidden_ports_in_both_directions` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_excludes_hidden_ports_in_both_directions` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_retains_runtime_check_matches_in_both_directions` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_retains_runtime_check_matches_in_both_directions` |
| `WindowLibraryInspectorQuickInsertTests::test_connection_quick_insert_neutral_flow_source_returns_flowchart_nodes` | `tests/test_quick_insert_projection.py::QuickInsertProjectionTests::test_connection_quick_insert_neutral_flow_source_returns_flowchart_nodes` |
| `WindowLibraryInspectorQuickInsertTests::test_registry_library_items_keep_declared_data_port_order` | `tests/test_library_projection.py::LibraryProjectionRegistryTests::test_registry_library_items_keep_declared_data_port_order` |
| `WindowLibraryInspectorQuickInsertTests::test_registry_browser_payload_projects_help_metadata_and_real_port_labels` | `tests/test_library_projection.py::LibraryProjectionRegistryTests::test_registry_browser_payload_projects_help_metadata_and_real_port_labels` |
| `WindowLibraryInspectorFolderExplorerTests::test_folder_explorer_is_discoverable_in_input_output_library_group` | `tests/test_library_projection.py::LibraryProjectionFolderExplorerTests::test_folder_explorer_is_discoverable_in_input_output_library_group` |
| `WindowLibraryInspectorFolderExplorerTests::test_folder_explorer_current_path_property_is_folder_path_editor_payload` | `tests/test_inspector_projection.py::InspectorProjectionFolderExplorerTests::test_folder_explorer_current_path_property_is_folder_path_editor_payload` |
| `WindowLibraryInspectorNodeLinkTests::test_selected_node_link_items_preserve_order_and_resolve_target_metadata` | `tests/test_inspector_projection.py::InspectorProjectionNodeLinkTests::test_selected_node_link_items_preserve_order_and_resolve_target_metadata` |
| `WindowLibraryInspectorTabularDataInputTests::test_tabular_data_input_library_item_is_availability_gated` | `tests/test_library_projection.py::LibraryProjectionTabularDataInputTests::test_tabular_data_input_library_item_is_availability_gated` |
| `WindowLibraryInspectorTabularDataInputTests::test_tabular_data_input_property_items_use_file_path_and_semantic_groups` | `tests/test_inspector_projection.py::InspectorProjectionTabularDataInputTests::test_tabular_data_input_property_items_use_file_path_and_semantic_groups` |
| `WindowLibraryInspectorTabularDataInputTests::test_tabular_selection_items_come_from_property_edit_adapter` | `tests/test_inspector_projection.py::InspectorProjectionTabularDataInputTests::test_tabular_selection_items_come_from_property_edit_adapter` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_registry_items_nested_category_library_payload_projects_path_metadata` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_registry_items_nested_category_library_payload_projects_path_metadata` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_grouped_rows_nested_category_library_payload_flattens_trie_with_metadata` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_grouped_rows_nested_category_library_payload_flattens_trie_with_metadata` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_display_rows_icon_mode_groups_passive_flowchart_visuals_into_tile_rows` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_display_rows_icon_mode_groups_passive_flowchart_visuals_into_tile_rows` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_flowchart_multi_document_library_visual_uses_metric_contract_aspect_ratio` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_flowchart_multi_document_library_visual_uses_metric_contract_aspect_ratio` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_filters_and_options_nested_category_library_payload_are_path_backed` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_filters_and_options_nested_category_library_payload_are_path_backed` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_custom_workflows_nested_category_library_payload_use_single_segment_path` | `tests/test_library_projection.py::LibraryProjectionNestedCategoryPayloadTests::test_custom_workflows_nested_category_library_payload_use_single_segment_path` |
| `WindowLibraryInspectorNestedCategoryLibraryPayloadTests::test_quick_insert_and_header_nested_category_library_payload_show_full_paths` | `tests/test_quick_insert_projection.py::QuickInsertProjectionCategoryTests::test_quick_insert_nested_category_library_payload_shows_full_path`; `tests/test_inspector_projection.py::InspectorProjectionHeaderTests::test_header_nested_category_library_payload_shows_full_path` |
| `WindowLibraryInspectorPropertyGroupTests::test_interval_editor_input_keeps_declared_endpoint_order` | `tests/test_inspector_projection.py::InspectorProjectionPropertyGroupTests::test_interval_editor_input_keeps_declared_endpoint_order` |
| `WindowLibraryInspectorPropertyGroupTests::test_property_items_reuse_interval_and_condition_presentation` | `tests/test_inspector_projection.py::InspectorProjectionPropertyGroupTests::test_property_items_reuse_interval_and_condition_presentation` |
| `WindowLibraryInspectorPropertyGroupTests::test_property_items_emit_group_with_fallback_when_unset` | `tests/test_inspector_projection.py::InspectorProjectionPropertyGroupTests::test_property_items_emit_group_with_fallback_when_unset` |
| `WindowLibraryInspectorPropertyGroupTests::test_property_items_flag_dirty_when_value_differs_from_default` | `tests/test_inspector_projection.py::InspectorProjectionPropertyGroupTests::test_property_items_flag_dirty_when_value_differs_from_default` |
| `WindowLibraryInspectorPropertyGroupTests::test_web_page_viewer_start_location_uses_source_storage_picker` | `tests/test_inspector_projection.py::InspectorProjectionPropertyGroupTests::test_web_page_viewer_start_location_uses_source_storage_picker` |

## Performance Evidence

| Task | Metric and fixture | Baseline | Candidate | Repeat / attribution | Verdict |
| --- | --- | --- | --- | --- | --- |
| T01 | Four-member schema-2 fixture; discovery/import/export | `3.030 / 8.717 / 7.220 ms` medians | `2.483 / 8.333 / 6.621 ms` medians | Same 3 warmups + 7 measured runs; filesystem and ZIP call counts did not increase; all archive hashes identical; raw run output not retained | `SUPPORTIVE; NO DETECTED REGRESSION` |
| T02 | Fresh import; scalar/DataTree/Image/artifact codecs; durable validate/to/from | `47.011 ms`; `28.291/135.737/51.217/130.216 us`; `19.209/3.988/10.420 us` | `47.184 ms`; `28.392/134.710/53.877/132.308 us`; `19.184/3.939/11.152 us` | Second matched batch confirmed only Image `+5.2%` (`+2.66 us`) and durable decode `+7.0%` (`+0.73 us`); hashes, copies, allocations identical | `ADVISORY MICRO-REGRESSION`; below material threshold |
| T03 | Default 933-spec registry; display/grouped projection and Quick Insert | Exact counts/order hashes pinned; display ~25-29 ms, paired projection ~49-54 ms, Quick Insert ~1.8/27 ms | Second interleaved batch: display text `-1.43%`; icon supportive/variable; paired text/icon `-52.31%/-47.04%`; Quick Insert within `+0.97%/+0.22%` | Live display-only path builds one tree and zero grouped rows; later grouped read reuses the tree; no payload/hash drift | `NEUTRAL-TO-BETTER` |
| T04 | Offscreen shell create; cursor and reset-edge action paths | `727.949 ms`; cursor `1426.923 ns`; host reset `291.733 ns`; full action `3042.979 ns` | `712.441 ms`; cursor `1311.855 ns`; host reset `229.580 ns`; full action `2894.418 ns` | Same 3 shell runs and 3x100k micro-path batches; 156 QObjects, 3 timers, 1 graph host, 1 shell host, 5 image providers unchanged; raw run output not retained | `SUPPORTIVE; NO DETECTED REGRESSION` |
| T05 | Deterministic 429,484,247-byte/3.8M-row fixture; managed cold/warm and source-direct queries | Original baseline timing JSON used a mismatched key/zero-match queries; retained `ad0b23...` Parquet cache is 115,861,026 bytes, SHA-256 `C0E00798...20E8A` | Candidate retains identical cache bytes, scan/conversion counts, row counts/totals/truncation and output hashes; source-direct comparable deltas remain below material thresholds without a second valid batch | UI-thread guard retained; baseline/candidate timing queries are not a matched pair; real-shell offscreen runs stalled before checkpoint and were not repeated | `STRUCTURAL I/O/CORRECTNESS PASS; TIMING INCONCLUSIVE` |
| T06 | Synthetic 5 s H.264 fixture SHA-256 `8E57FAE7...F6F9B4`; HEAD/candidate renderer-only QQuickWindow offscreen/software runs | Ready `12.564 ms`, position `10.591`, paused stability `10.351`, unload `10.527`, reload `22.734`; HEAD resume failed within 1 s | Ready `12.911 ms`, position `10.943`, paused `10.664`, unload `10.522`, reload `22.387`; retained/recreated resume works | Three interleaved runs; comparable timing within `0.36 ms`; candidate same-node source unload and different-node playback proven; CPU/RSS incomparable because HEAD stayed idle | `SUPPORTIVE NO-REGRESSION` for renderer lifecycle; display-attached/full-app CPU/RSS `INCONCLUSIVE`; GIF harness unrelated |

## T00 Baseline Evidence

| Command / evidence | Result |
| --- | --- |
| `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run` | `PASS`; command graph rendered, with `qmltestrunner.exe` reported unavailable in this environment |
| Affected Python suites, serial `--collect-only` | `PASS`; 582 tests collected across 27 modules, no collection errors |
| `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output` | `PASS`; parallel 4,318 passed/2 skipped, serial 225 passed, 18 existing warnings |
| `.\venv\Scripts\python.exe .\scripts\check_traceability.py` | `PASS` |
| `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` | `PASS` |
| `git diff --check` | `PASS` |
| Protected-path hash audit | `PASS`; all three pre-existing dirty paths retained their starting hashes |

## Review Ledger

| Review | Scope | Reviewer | Findings | Resolution | Verdict |
| --- | --- | --- | --- | --- | --- |
| Per-task reviews | T01 | `t01_package_reviewer` | Numeric loose-plugin generation rejection; delayed cumulative-byte checks; stale add-on test ownership; missing maps; dead imports | Production/test findings fixed by original writer; maps integrated by orchestrator | `CLEAR` |
| Per-task reviews | T02 | `t02_runtime_reviewer` | Stale docs; `value_refs` forwarding tabular/array carriers; obsolete execution codec; missing exact export/union guards | Source/test findings fixed by original writer; docs/maps integrated by orchestrator | `CLEAR` |
| Per-task reviews | T03 | `t03_projection_reviewer` | Live docs named deleted owner; Library depended on Quick Insert for projected-port parsing | Helper moved to Library; dependency/absence guards added; docs/maps integrated by orchestrator | `CLEAR` |
| Per-task reviews | T04 | `t04_graph_host_reviewer` | Stale route/map/ledger ownership only | Direct graph-host ownership documented; shell test responsibility narrowed; generated navigation refreshed | `CLEAR` |
| Per-task reviews | T05 | `t05_tabular_reviewer` | Missing/null Arrow/Python drift; missing native-Parquet/window coverage; looped non-independent cases; faulty perf probe key/query values | Explicit no-value policy, parametrized parity, native Parquet test, corrected ignored probe and matched 400 MB evidence | `CLEAR` |
| Per-task reviews | T06 | `t06_video_reviewer` | Missed LoadedMedia initialization; nonzero paused primer drift; suppressed fullscreen warnings; dead hook; GIF perf misattribution | Deferred readiness, restored primer guard/warnings, removed hook, added synthetic MP4 lifecycle proof and real-video matched evidence | `CLEAR` |
| Per-task reviews | T07 | `t07_test_reviewer` | Moved direct test initially weakened final Project A/B payload equality | Exact full-list A/B assertions restored; import-cycle and canonical normalizer changes rechecked | `CLEAR` |
| Architecture/ownership closeout | Whole series | `t08_architecture_review` | Four live owner descriptions stale; T01 forwarder absence guard missing | Live docs corrected; explicit loader-forwarder absence assertions added | `CLEAR` |
| Correctness/security/no-lost-tests closeout | Whole series | `t08_correctness_review` | T05 mixed/null/non-finite parity, PyArrow-24, key collision; T02 ledger omission | Query semantics/compatibility/collision tests fixed; explicit T02 migration row added | `CLEAR` |
| Performance-evidence closeout | Whole series | `t08_performance_review` | T05 mismatched timing pair; T06 rounding/scope; supportive-only raw evidence | Verdicts and caveats corrected without speedup claims | `ACCEPTABLE WITH CAVEATS` |
| Architecture/ownership closeout | Whole series | Pending | Pending | Pending | Pending |
| Correctness/security/no-lost-tests closeout | Whole series | Pending | Pending | Pending | Pending |
| Performance-evidence closeout | Whole series | Pending | Pending | Pending | Pending |

## Final Acceptance

| Gate | Command / evidence | Result |
| --- | --- | --- |
| Focused task suites | Recorded per task above | `PASS` |
| Agent maps | `.\venv\Scripts\python.exe .\scripts\check_agent_maps.py` | `PASS` |
| Traceability | `.\venv\Scripts\python.exe .\scripts\check_traceability.py` | `PASS` |
| Markdown links | `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` | `PASS` |
| Full fast | `artifacts/verification_logs/20260901_111824/01_fast.pytest.log` | `PASS` — 4,375 passed, 2 skipped, 24 warnings |
| Full fast serial | `artifacts/verification_logs/20260901_111824/02_fast.serial.pytest.log` | `PASS` — 225 passed |
| Full Qt Quick | `artifacts/verification_logs/20260901_111824/03_gui.qml_quick_explicit.log` | `PASS` — 70 passed |
| Full GUI | `artifacts/verification_logs/20260901_111824/04_gui.pytest.log` | `PASS` — 589 passed, 1 skipped, 2 warnings |
| Full GUI serial | `artifacts/verification_logs/20260901_111824/05_gui.serial.pytest.log` | `PASS` — 39 passed, 1 skipped |
| Full slow | `artifacts/verification_logs/20260901_111824/06_slow.pytest.log` | `PASS` — 56 passed |
| Full shell isolation | `artifacts/verification_logs/20260901_111824/07_full.shell_isolation.pytest.log` | `PASS` — 58 passed; unchanged 51-target catalog |
| Diff hygiene | `git diff --check` and cached-diff audit | `PASS` |
| Publication | Local commit series only; no push | `PASS` |
