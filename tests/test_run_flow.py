from ea_node_editor.ui.shell.run_flow import selected_workspace_run_control_state


def test_selected_workspace_run_control_state_is_idle_without_an_active_run() -> None:
    state = selected_workspace_run_control_state(
        selected_workspace_id="workspace_a",
        active_run_id="",
        active_run_workspace_id="",
        engine_state="ready",
    )

    assert state.selected_workspace_owns_active_run is False
    assert state.can_run_active_workspace is True
    assert state.can_pause_active_workspace is False
    assert state.can_stop_active_workspace is False
    assert state.pause_label == "Pause"


def test_selected_workspace_run_control_state_marks_owner_running_state() -> None:
    state = selected_workspace_run_control_state(
        selected_workspace_id="workspace_a",
        active_run_id="run_1",
        active_run_workspace_id="workspace_a",
        engine_state="running",
    )

    assert state.selected_workspace_owns_active_run is True
    assert state.can_run_active_workspace is False
    assert state.can_pause_active_workspace is True
    assert state.can_stop_active_workspace is True
    assert state.pause_label == "Pause"


def test_selected_workspace_run_control_state_marks_owner_paused_state() -> None:
    state = selected_workspace_run_control_state(
        selected_workspace_id="workspace_a",
        active_run_id="run_1",
        active_run_workspace_id="workspace_a",
        engine_state="paused",
    )

    assert state.selected_workspace_owns_active_run is True
    assert state.can_run_active_workspace is False
    assert state.can_pause_active_workspace is True
    assert state.can_stop_active_workspace is True
    assert state.pause_label == "Resume"


def test_selected_workspace_run_control_state_keeps_run_enabled_for_non_owner() -> None:
    state = selected_workspace_run_control_state(
        selected_workspace_id="workspace_b",
        active_run_id="run_1",
        active_run_workspace_id="workspace_a",
        engine_state="running",
    )

    assert state.selected_workspace_owns_active_run is False
    assert state.can_run_active_workspace is True
    assert state.can_pause_active_workspace is False
    assert state.can_stop_active_workspace is False
    assert state.pause_label == "Pause"


def test_selected_workspace_run_control_state_does_not_leak_resume_for_non_owner() -> None:
    state = selected_workspace_run_control_state(
        selected_workspace_id="workspace_b",
        active_run_id="run_1",
        active_run_workspace_id="workspace_a",
        engine_state="paused",
    )

    assert state.selected_workspace_owns_active_run is False
    assert state.can_run_active_workspace is True
    assert state.can_pause_active_workspace is False
    assert state.can_stop_active_workspace is False
    assert state.pause_label == "Pause"
