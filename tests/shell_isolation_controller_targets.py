"""Controller/session shell isolation targets."""

from __future__ import annotations

from functools import lru_cache

_SCRIPT_EDITOR_TEST_CLASS = "tests.test_script_editor_dock.ScriptEditorDockTests"


@lru_cache(maxsize=1)
def _build_targets():
    from tests.shell_isolation_runtime import ShellIsolationTarget

    return (
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor",
            target_id="script_editor__test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_editor_binds_to_selected_python_script_node",
            target_id="script_editor__test_script_editor_binds_to_selected_python_script_node",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_editor_state_persists_in_metadata",
            target_id="script_editor__test_script_editor_state_persists_in_metadata",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_editor_exposes_cursor_diagnostics_and_dirty_state",
            target_id="script_editor__test_script_editor_exposes_cursor_diagnostics_and_dirty_state",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_set_script_editor_panel_visible_focuses_editor_for_script_node",
            target_id="script_editor__test_set_script_editor_panel_visible_focuses_editor_for_script_node",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_apply_failure_keeps_draft_dirty",
            target_id="script_editor__test_script_apply_failure_keeps_draft_dirty",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_numeric_overflow_draft_stays_dirty_and_leaves_graph_unchanged",
            target_id="script_editor__test_numeric_overflow_draft_stays_dirty_and_leaves_graph_unchanged",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_apply_failure_draft_survives_panel_reopen",
            target_id="script_editor__test_script_apply_failure_draft_survives_panel_reopen",
        ),
        ShellIsolationTarget.unittest_target(
            f"{_SCRIPT_EDITOR_TEST_CLASS}.test_script_draft_survives_same_node_property_refresh",
            target_id="script_editor__test_script_draft_survives_same_node_property_refresh",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_session_restore_recovers_workspace_order_active_workspace_and_view_camera",
            target_id="project_session__test_session_restore_recovers_workspace_order_active_workspace_and_view_camera",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_open_project_rejects_saved_node_when_startup_preferences_disable_addon",
            target_id="project_session__test_open_project_rejects_saved_node_when_startup_preferences_disable_addon",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc",
            target_id="project_session__test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_recovery_prompt_accept_loads_newer_autosave",
            target_id="project_session__test_recovery_prompt_accept_loads_newer_autosave",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave",
            target_id="project_session__test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_restore_session_handles_corrupted_session_and_autosave_files",
            target_id="project_session__test_restore_session_handles_corrupted_session_and_autosave_files",
        ),
        ShellIsolationTarget.project_session_scenario(
            "test_recovery_prompt_is_deferred_until_main_window_is_visible",
            target_id="project_session__test_recovery_prompt_is_deferred_until_main_window_is_visible",
        ),
    )


def __getattr__(name: str):
    if name == "TARGETS":
        return _build_targets()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
