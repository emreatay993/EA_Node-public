from __future__ import annotations

import ast
import importlib
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from scripts import verification_manifest as manifest
from tests.shell_isolation_runtime import format_child_output
from tests.shell_isolation_runtime import list_target_ids
from tests.shell_isolation_runtime import load_target_registry
from tests.shell_isolation_runtime import resolve_target
from tests.shell_isolation_runtime import run_shell_isolation_target
from tests.shell_isolation_runtime import ShellIsolationTargetTimeout
from tests.shell_isolation_runtime import shell_lifecycle_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_T25_TARGET_IDS = {
    "main_window__drop_connect_and_workflow_io__connection_constraints_and_library_drop",
    "main_window__drop_connect_and_workflow_io__connection_drag_and_cycle",
    "main_window__drop_connect_and_workflow_io__nested_category_startup",
    "main_window__drop_connect_and_workflow_io__project_and_selection",
    "main_window__drop_connect_and_workflow_io__quick_insert_and_workflow_mutations",
    "main_window__drop_connect_and_workflow_io__workflow_round_trip_and_install",
    "main_window__drop_connect_and_workflow_io__workflow_updates_and_nested_drop",
    "main_window__edit_clipboard_history__clipboard_artifacts_and_backdrops",
    "main_window__edit_clipboard_history__clipboard_history_and_undo",
    "main_window__edit_clipboard_history__graph_edits_and_clipboard_basics",
    "main_window__lifecycle__composition_context_provider_action_identity",
    "main_window__lifecycle__fullscreen_media_handoff",
    "main_window__lifecycle__native_parenting",
    "main_window__lifecycle__project_reset_timer_cancellation",
    "main_window__lifecycle__repeated_mount_close_teardown",
    "main_window__lifecycle__viewer_reparent_restore",
    "main_window__passive_image_nodes__crop_interactions",
    "main_window__passive_image_nodes__editors_and_storage",
    "main_window__passive_pdf_nodes__editors_and_storage",
    "main_window__passive_pdf_nodes__toolbar_and_page_resolution",
    "main_window__passive_property_editors",
    "main_window__passive_style_context_menus",
    "main_window__shell_basics_and_search__graph_search",
    "main_window__shell_basics_and_search__menus_and_settings",
    "main_window__shell_basics_and_search__node_browser_and_tabs",
    "main_window__shell_basics_and_search__preferences_and_dialogs",
    "main_window__shell_basics_and_search__qml_canvas_and_preferences",
    "main_window__shell_basics_and_search__typography_labels_and_bridges",
    "main_window__shell_basics_and_search__workspace_actions",
    "main_window__view_library_inspector__graph_and_library",
    "main_window__view_library_inspector__panes_and_console",
    "main_window__view_library_inspector__ports_payloads_and_viewport",
    "main_window__view_library_inspector__subnodes_and_inspector",
    "main_window__view_library_inspector__views_and_workspaces",
    "project_session__test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc",
    "project_session__test_open_project_rejects_saved_node_when_startup_preferences_disable_addon",
    "project_session__test_recovery_prompt_accept_loads_newer_autosave",
    "project_session__test_recovery_prompt_is_deferred_until_main_window_is_visible",
    "project_session__test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave",
    "project_session__test_restore_session_handles_corrupted_session_and_autosave_files",
    "project_session__test_session_restore_recovers_workspace_order_active_workspace_and_view_camera",
    "script_editor__test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor",
    "script_editor__test_numeric_overflow_draft_stays_dirty_and_leaves_graph_unchanged",
    "script_editor__test_script_apply_failure_draft_survives_panel_reopen",
    "script_editor__test_script_apply_failure_keeps_draft_dirty",
    "script_editor__test_script_draft_survives_same_node_property_refresh",
    "script_editor__test_script_editor_binds_to_selected_python_script_node",
    "script_editor__test_script_editor_exposes_cursor_diagnostics_and_dirty_state",
    "script_editor__test_script_editor_state_persists_in_metadata",
    "script_editor__test_set_script_editor_panel_visible_focuses_editor_for_script_node",
}
_REEXPORTED_SHELL_SOURCE_PATHS = {
    "tests/main_window_shell/bridge_contracts.py",
    "tests/main_window_shell/bridge_contracts_library_and_inspector.py",
    "tests/main_window_shell/bridge_qml_boundaries.py",
    "tests/main_window_shell/bridge_contracts_workspace_and_console.py",
    "tests/main_window_shell/bridge_support.py",
    "tests/main_window_shell/mutation_ui_effects.py",
}
_REEXPORTED_TEST_CLASSES_BY_PATH = {
    "tests/main_window_shell/bridge_contracts.py": (
        "SharedUiSupportBoundaryTests",
        "ShellInspectorBridgeTests",
        "ShellLibraryBridgeTests",
        "ShellWorkspaceBridgeTests",
    ),
}
_LOCAL_EXCLUDED_TEST_CLASSES_BY_PATH = {
    "tests/main_window_shell/bridge_qml_boundaries.py": (
        "ShellAddOnManagerQmlBoundaryTests",
    ),
    "tests/main_window_shell/shell_runtime_contracts.py": (
        "MainWindowShellContentFullscreenStaticContractsTests",
    ),
    "tests/test_main_window_shell.py": (
        "MainWindowBridgeContractPacketBoundaryTests",
        "MainWindowGraphTypographyBridgeTests",
        "MainWindowPyQtGraphActionRouteTests",
        "NodeBrowserQmlBoundaryTests",
        "PresenterPackageBoundaryTests",
        "ShellWindowStateFacadeBoundaryTests",
    ),
}
_LOCAL_EXCLUDED_TEST_METHODS_BY_OWNER = {
    ("tests/test_shell_run_controller.py", "ShellRunControllerTests"): (
        "test_disconnected_toggle_auto_run_preserves_current_viewer_until_separate_same_node_invalidation",
        "test_failed_dispatch_leaves_viewer_host_and_epochs_untouched",
        "test_fatal_run_failed_event_invalidates_viewer_sessions_as_worker_reset",
        "test_graph_typography_host_chrome_shell_events_apply_shared_roles_and_preserve_elapsed_footer_semantics",
        "test_node_execution_visualization_failure_priority_overrides_completed_chrome",
        "test_node_execution_visualization_shell_events_drive_graph_node_chrome_states",
        "test_node_settled_failure_hides_elapsed_timer_for_failed_running_node",
        "test_node_settled_artifact_ref_payload_keeps_run_ui_running",
        "test_warning_node_settled_event_marks_golden_chrome_and_logs_without_failure_focus",
        "test_persistent_node_elapsed_footer_failure_priority_hides_failed_running_live_timer",
        "test_persistent_node_elapsed_footer_shell_events_render_live_then_cached_until_invalidation",
        "test_selected_workspace_toolbar_buttons_follow_run_owner_state_and_warning_path",
        "test_shell_context_bridge_explicit_sources_wrap_shell_window_with_focused_sources",
        "test_viewer_session_bridge_context_property_exists_and_rerun_invalidates_current_workspace",
        "test_successful_dispatch_invalidates_exact_viewers_without_host_reset",
    ),
}
_LOCAL_RETIRED_TEST_METHODS_BY_OWNER = {
    ("tests/test_shell_run_controller.py", "ShellRunControllerTests"): (
        "test_shell_context_bridge_fallbacks_wrap_shell_window_with_focused_sources",
    ),
}


def _target_params():
    target_ids = list_target_ids()
    if target_ids:
        return [pytest.param(target_id, id=target_id) for target_id in target_ids]
    return [
        pytest.param(
            "",
            id="no-targets",
            marks=pytest.mark.skip(
                reason="Shell isolation target catalogs are empty in P01."
            ),
        )
    ]


def _parse_module(relative_path: str) -> ast.Module:
    path = REPO_ROOT / relative_path
    return ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)


def _public_test_classes(relative_path: str) -> tuple[str, ...]:
    if relative_path in _REEXPORTED_TEST_CLASSES_BY_PATH:
        return tuple(sorted(_REEXPORTED_TEST_CLASSES_BY_PATH[relative_path]))
    tree = _parse_module(relative_path)
    names = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
        and node.name.endswith("Tests")
    ]
    return tuple(sorted(names))


def _test_methods(relative_path: str, class_name: str) -> tuple[str, ...]:
    tree = _parse_module(relative_path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple(
                sorted(
                    item.name
                    for item in node.body
                    if isinstance(item, ast.FunctionDef)
                    and item.name.startswith("test_")
                )
            )
    raise AssertionError(f"Missing test class {class_name!r} in {relative_path}.")


def _test_functions(relative_path: str) -> tuple[str, ...]:
    tree = _parse_module(relative_path)
    return tuple(
        sorted(
            {
                node.name
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
            }
            | {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
                if (alias.asname or alias.name).startswith("test_")
            }
        )
    )


def _discovered_shell_sources() -> set[str]:
    discovered: set[str] = set()
    main_window_dir = REPO_ROOT / "tests" / "main_window_shell"
    for path in sorted(main_window_dir.glob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        if relative_path.endswith(("__init__.py", "base.py")):
            continue
        if relative_path in _REEXPORTED_SHELL_SOURCE_PATHS:
            continue
        if _public_test_classes(relative_path):
            discovered.add(relative_path)
    for relative_path in (
        "tests/test_main_window_shell.py",
        "tests/test_script_editor_dock.py",
        "tests/test_shell_run_controller.py",
        "tests/test_shell_project_session_controller.py",
        manifest.SHELL_WINDOW_LIFECYCLE_TEST_PATH,
    ):
        if _public_test_classes(relative_path) or _test_functions(relative_path):
            discovered.add(relative_path)
    return discovered


def _dotted_module_to_path(module_name: str) -> str:
    return f"{module_name.replace('.', '/')}.py"


def _pytest_target_nodeids(
    command: tuple[str, ...], ignore_count: int
) -> tuple[str, ...]:
    args_start = 3
    if command[args_start : args_start + 2] == ("-n", "0"):
        args_start += 2
    return command[args_start + ignore_count : -1]


def _target_index():
    registry = load_target_registry()
    ignore_count = len(manifest.worktree_pytest_ignore_args())
    module_targets: set[str] = set()
    pytest_class_targets: dict[str, set[str]] = defaultdict(set)
    pytest_function_targets: dict[str, set[str]] = defaultdict(set)
    unittest_method_targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    scenario_targets: dict[tuple[str, str], set[str]] = defaultdict(set)

    for target in registry.values():
        command = target.command
        if command[:3] == (sys.executable, "-m", "unittest"):
            for dotted_target in command[3:]:
                parts = dotted_target.split(".")
                if parts[-1].startswith("test_"):
                    source_path = _dotted_module_to_path(".".join(parts[:-2]))
                    unittest_method_targets[(source_path, parts[-2])].add(parts[-1])
                else:
                    module_targets.add(_dotted_module_to_path(dotted_target))
            continue

        if (
            len(command) == 5
            and command[:3]
            == (sys.executable, "-m", "tests.test_shell_project_session_controller")
            and command[3] == "--scenario"
        ):
            scenario_targets[
                (
                    "tests/test_shell_project_session_controller.py",
                    "ShellProjectSessionControllerTests",
                )
            ].add(command[4])
            continue

        if command[0] != sys.executable or command[1:3] != ("-m", "pytest"):
            continue
        nodeids = _pytest_target_nodeids(command, ignore_count)
        for nodeid in nodeids:
            parts = nodeid.replace("\\", "/").split("::")
            if len(parts) == 2 and parts[1].startswith("test_"):
                pytest_function_targets[parts[0]].add(parts[1])
            elif len(parts) >= 2:
                pytest_class_targets[parts[0]].add(parts[1])

    return (
        module_targets,
        pytest_class_targets,
        pytest_function_targets,
        unittest_method_targets,
        scenario_targets,
    )


def _assert_ownership_rule(
    spec: manifest.ShellIsolationOwnershipSpec,
    *,
    module_targets: set[str],
    pytest_class_targets: dict[str, set[str]],
    pytest_function_targets: dict[str, set[str]],
    unittest_method_targets: dict[tuple[str, str], set[str]],
    scenario_targets: dict[tuple[str, str], set[str]],
) -> None:
    if spec.coverage_kind == "module_target":
        if spec.source_path in module_targets:
            return
        for class_name in _public_test_classes(spec.source_path):
            assert set(
                _test_methods(spec.source_path, class_name)
            ) <= unittest_method_targets.get(
                (spec.source_path, class_name),
                set(),
            )
        return

    if spec.coverage_kind == "class_targets":
        discovered = set(_public_test_classes(spec.source_path))
        expected = (
            {name for name in spec.covered_names if not name.startswith("_")}
            | set(spec.excluded_names)
            | set(_LOCAL_EXCLUDED_TEST_CLASSES_BY_PATH.get(spec.source_path, ()))
        )
        assert discovered == expected
        assert set(spec.covered_names) <= pytest_class_targets.get(
            spec.source_path, set()
        )
        return

    if spec.coverage_kind == "method_targets":
        assert spec.owner_name is not None
        discovered = set(_test_methods(spec.source_path, spec.owner_name))
        expected = (
            set(spec.covered_names)
            | set(spec.excluded_names)
            | set(
                _LOCAL_EXCLUDED_TEST_METHODS_BY_OWNER.get(
                    (spec.source_path, spec.owner_name), ()
                )
            )
        )
        expected -= set(
            _LOCAL_RETIRED_TEST_METHODS_BY_OWNER.get(
                (spec.source_path, spec.owner_name), ()
            )
        )
        assert discovered == expected
        assert set(spec.covered_names) <= unittest_method_targets.get(
            (spec.source_path, spec.owner_name),
            set(),
        )
        return

    if spec.coverage_kind == "scenario_targets":
        assert spec.owner_name is not None
        discovered = set(_test_methods(spec.source_path, spec.owner_name))
        expected = set(spec.covered_names) | set(spec.excluded_names)
        assert discovered == expected
        assert set(spec.covered_names) <= scenario_targets.get(
            (spec.source_path, spec.owner_name),
            set(),
        )
        return

    if spec.coverage_kind == "function_targets":
        discovered = set(_test_functions(spec.source_path))
        expected = set(spec.covered_names) | set(spec.excluded_names)
        assert discovered == expected
        assert set(spec.covered_names) <= pytest_function_targets.get(
            spec.source_path,
            set(),
        )
        return

    raise AssertionError(f"Unknown shell-isolation coverage kind: {spec.coverage_kind}")


def test_shell_isolation_target_catalogs_follow_manifest_owned_prefixes() -> None:
    registry = load_target_registry()

    assert registry
    assert set(registry) == _EXPECTED_T25_TARGET_IDS
    allowed_prefixes = manifest.shell_isolation_target_id_prefixes()
    for target_id in registry:
        assert target_id.startswith(allowed_prefixes)

    seen: set[str] = set()
    for spec in manifest.SHELL_ISOLATION_CATALOG_SPECS:
        target_ids = {
            target.target_id
            for target in getattr(importlib.import_module(spec.module_name), "TARGETS")
        }
        assert seen.isdisjoint(target_ids)
        seen.update(target_ids)
    assert seen == set(registry)


def test_real_shell_lifecycle_is_isolated_from_fast_and_gui_collection() -> None:
    lifecycle_path = manifest.SHELL_WINDOW_LIFECYCLE_TEST_PATH

    assert lifecycle_path in manifest.SHELL_BACKED_TEST_PATHS
    assert lifecycle_path in manifest.NON_SHELL_PYTEST_IGNORES
    assert lifecycle_path not in manifest.GUI_TEST_PATHS
    assert (
        "tests/test_shell_window_lifecycle.py" not in manifest.SHELL_BACKED_TEST_PATHS
    )


def test_shell_isolation_pytest_targets_use_manifest_owned_pytest_args() -> None:
    registry = load_target_registry()
    ignore_count = len(manifest.worktree_pytest_ignore_args())
    pytest_targets = [
        (target_id, target)
        for target_id, target in registry.items()
        if target.command[0] == sys.executable
        and target.command[1:3] == ("-m", "pytest")
    ]

    assert pytest_targets
    for target_id, target in pytest_targets:
        nodeids = _pytest_target_nodeids(target.command, ignore_count)
        pytest_args = manifest.shell_isolation_target_pytest_args(*nodeids)
        expected = (sys.executable, *pytest_args[:2], "-n", "0", *pytest_args[2:])
        assert target.command == expected


def test_shell_isolation_catalog_ownership_rules_cover_current_shell_surfaces() -> None:
    discovered = _discovered_shell_sources()
    owned = set(manifest.shell_isolation_ownership_specs_by_path())

    assert discovered == owned


def test_shell_isolation_suite_is_first_class_manifest_registry_member() -> None:
    suite_spec = manifest.verification_suite_spec(manifest.SHELL_ISOLATION_PHASE_KEY)

    assert suite_spec.shell_isolation
    assert suite_spec.worker_cap == manifest.MAX_SHELL_ISOLATION_PARALLEL_WORKERS
    assert manifest.SHELL_ISOLATION_SPEC.phase == suite_spec.phase
    assert manifest.SHELL_ISOLATION_SPEC.test_path in manifest.suite_test_paths(
        manifest.SHELL_ISOLATION_PHASE_KEY
    )
    assert (
        manifest.SHELL_ISOLATION_SPEC.shell_module_paths
        == manifest.suite_test_paths(manifest.SHELL_SUITE_KEY)
    )


def test_shell_isolation_catalogs_cover_manifest_owned_shell_surfaces() -> None:
    (
        module_targets,
        pytest_class_targets,
        pytest_function_targets,
        unittest_method_targets,
        scenario_targets,
    ) = _target_index()

    for spec in manifest.SHELL_ISOLATION_OWNERSHIP_SPECS:
        _assert_ownership_rule(
            spec,
            module_targets=module_targets,
            pytest_class_targets=pytest_class_targets,
            pytest_function_targets=pytest_function_targets,
            unittest_method_targets=unittest_method_targets,
            scenario_targets=scenario_targets,
        )


def test_shell_target_groups_are_complete_and_disjoint() -> None:
    registry = load_target_registry()
    expected_split_target_ids = {
        "main_window__edit_clipboard_history__graph_edits_and_clipboard_basics",
        "main_window__edit_clipboard_history__clipboard_artifacts_and_backdrops",
        "main_window__edit_clipboard_history__clipboard_history_and_undo",
        "main_window__drop_connect_and_workflow_io__project_and_selection",
        "main_window__drop_connect_and_workflow_io__connection_drag_and_cycle",
        "main_window__drop_connect_and_workflow_io__connection_constraints_and_library_drop",
        "main_window__drop_connect_and_workflow_io__quick_insert_and_workflow_mutations",
        "main_window__drop_connect_and_workflow_io__workflow_round_trip_and_install",
        "main_window__drop_connect_and_workflow_io__nested_category_startup",
        "main_window__drop_connect_and_workflow_io__workflow_updates_and_nested_drop",
        "main_window__shell_basics_and_search__menus_and_settings",
        "main_window__shell_basics_and_search__preferences_and_dialogs",
        "main_window__shell_basics_and_search__typography_labels_and_bridges",
        "main_window__shell_basics_and_search__node_browser_and_tabs",
        "main_window__shell_basics_and_search__qml_canvas_and_preferences",
        "main_window__shell_basics_and_search__workspace_actions",
        "main_window__shell_basics_and_search__graph_search",
        "main_window__lifecycle__composition_context_provider_action_identity",
        "main_window__lifecycle__fullscreen_media_handoff",
        "main_window__lifecycle__native_parenting",
        "main_window__lifecycle__project_reset_timer_cancellation",
        "main_window__lifecycle__repeated_mount_close_teardown",
        "main_window__lifecycle__viewer_reparent_restore",
        "main_window__passive_image_nodes__editors_and_storage",
        "main_window__passive_image_nodes__crop_interactions",
        "main_window__passive_pdf_nodes__editors_and_storage",
        "main_window__passive_pdf_nodes__toolbar_and_page_resolution",
        "main_window__view_library_inspector__panes_and_console",
        "main_window__view_library_inspector__graph_and_library",
        "main_window__view_library_inspector__subnodes_and_inspector",
        "main_window__view_library_inspector__ports_payloads_and_viewport",
        "main_window__view_library_inspector__views_and_workspaces",
    }
    split_prefixes = (
        "main_window__edit_clipboard_history__",
        "main_window__drop_connect_and_workflow_io__",
        "main_window__shell_basics_and_search__",
        "main_window__lifecycle__",
        "main_window__passive_image_nodes__",
        "main_window__passive_pdf_nodes__",
        "main_window__view_library_inspector__",
    )
    assert {
        target_id for target_id in registry if target_id.startswith(split_prefixes)
    } == expected_split_target_ids
    expected_unittest_methods = {
        (
            "tests/main_window_shell/edit_clipboard_history.py",
            "MainWindowShellEditClipboardHistoryTests",
        ): set(
            _test_methods(
                "tests/main_window_shell/edit_clipboard_history.py",
                "MainWindowShellEditClipboardHistoryTests",
            )
        ),
        (
            "tests/main_window_shell/drop_connect_and_workflow_io.py",
            "MainWindowShellDropConnectAndWorkflowIOTests",
        ): set(
            _test_methods(
                "tests/main_window_shell/drop_connect_and_workflow_io.py",
                "MainWindowShellDropConnectAndWorkflowIOTests",
            )
        ),
        (
            "tests/main_window_shell/shell_basics_and_search.py",
            "MainWindowShellBasicsAndSearchTests",
        ): set(
            _test_methods(
                "tests/main_window_shell/shell_basics_and_search.py",
                "MainWindowShellBasicsAndSearchTests",
            )
        ),
        (
            "tests/main_window_shell/view_library_inspector.py",
            "MainWindowShellViewLibraryInspectorTests",
        ): set(
            _test_methods(
                "tests/main_window_shell/view_library_inspector.py",
                "MainWindowShellViewLibraryInspectorTests",
            )
        ),
    }
    expected_pytest_nodeids: set[str] = set()
    for source_path, class_name in (
        (
            "tests/main_window_shell/passive_image_nodes.py",
            "MainWindowShellPassiveImageNodesTests",
        ),
        (
            "tests/main_window_shell/passive_pdf_nodes.py",
            "MainWindowShellPassivePdfNodesTests",
        ),
    ):
        expected_pytest_nodeids.update(
            f"{source_path}::{class_name}::{method_name}"
            for method_name in _test_methods(source_path, class_name)
        )
    actual_unittest_methods = defaultdict(list)
    actual_pytest_nodeids = []
    ignore_count = len(manifest.worktree_pytest_ignore_args())

    for target in registry.values():
        command = target.command
        if command[:3] == (sys.executable, "-m", "unittest"):
            for dotted_target in command[3:]:
                parts = dotted_target.split(".")
                if not parts[-1].startswith("test_"):
                    continue
                owner = (_dotted_module_to_path(".".join(parts[:-2])), parts[-2])
                if owner in expected_unittest_methods:
                    actual_unittest_methods[owner].append(parts[-1])
            continue
        if command[0] == sys.executable and command[1:3] == ("-m", "pytest"):
            actual_pytest_nodeids.extend(
                nodeid
                for nodeid in _pytest_target_nodeids(command, ignore_count)
                if nodeid in expected_pytest_nodeids
            )

    for owner, expected in expected_unittest_methods.items():
        actual = actual_unittest_methods[owner]
        assert len(actual) == len(set(actual)) == len(expected)
        assert set(actual) == expected
    assert (
        len(actual_pytest_nodeids)
        == len(set(actual_pytest_nodeids))
        == len(expected_pytest_nodeids)
    )
    assert set(actual_pytest_nodeids) == expected_pytest_nodeids


def test_shell_lifecycle_contract_registers_isolated_regression() -> None:
    contract = shell_lifecycle_contract()
    lifecycle_test_path = Path(contract["lifecycle_test_path"])

    assert contract["truth"]
    assert contract["shared_window_scope"]
    assert lifecycle_test_path.is_file()
    assert lifecycle_test_path.as_posix() in manifest.SHELL_BACKED_TEST_PATHS
    assert lifecycle_test_path.as_posix() not in manifest.GUI_TEST_PATHS


@pytest.mark.parametrize(
    "target_id",
    _target_params(),
)
def test_shell_isolation_target(target_id: str) -> None:
    target = resolve_target(target_id)
    try:
        completed = run_shell_isolation_target(target)
    except ShellIsolationTargetTimeout as exc:
        pytest.fail(str(exc), pytrace=False)
    if completed.returncode == 0:
        return
    pytest.fail(
        "Shell isolation child process failed "
        f"for {target_id} (exit={completed.returncode}).\n"
        f"Command: {' '.join(target.command)}\n"
        f"{format_child_output(completed)}",
        pytrace=False,
    )
