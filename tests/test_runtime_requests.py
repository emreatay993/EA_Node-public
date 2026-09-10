# Purpose: Direct runtime request/result value-contract tests.
# Map: subsystems/execution.md

from __future__ import annotations

from ea_node_editor.execution.backends import ExecutionBackendPolicy
from ea_node_editor.execution.runtime_requests import ExecutionRequest, ExecutionResult


def test_execution_request_detaches_trigger_and_honors_explicit_fields() -> None:
    nested = {"values": [1]}
    request = ExecutionRequest(
        trigger={
            "nested": nested,
            "runtime_snapshot": {"legacy": True},
            "execution_backend": "legacy",
        },
        runtime_snapshot={"current": True},
        execution_backend=ExecutionBackendPolicy(),
    )

    trigger, snapshot, backend = request.trigger_without_runtime_snapshot()

    assert trigger == {"nested": {"values": [1]}}
    assert snapshot == {"current": True}
    assert isinstance(backend, ExecutionBackendPolicy)
    nested["values"].append(2)
    assert trigger == {"nested": {"values": [1]}}


def test_execution_result_to_dict_detaches_nested_event_payloads() -> None:
    terminal = {"type": "run_completed", "nested": {"value": 1}}
    event = {"type": "log", "items": ["one"]}
    result = ExecutionResult(
        run_id="run_1",
        workspace_id="ws_1",
        status="completed",
        events=(event,),
        terminal_event=terminal,
    )

    payload = result.to_dict()
    event["items"].append("two")
    terminal["nested"]["value"] = 2

    assert payload["events"] == [{"type": "log", "items": ["one"]}]
    assert payload["terminal_event"] == {
        "type": "run_completed",
        "nested": {"value": 1},
    }
