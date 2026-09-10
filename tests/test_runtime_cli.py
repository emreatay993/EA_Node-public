# Purpose: Direct corex-runtime parser, output, and exit-code tests.
# Map: subsystems/execution.md

from __future__ import annotations

import json
import subprocess
import sys

from ea_node_editor.execution import runtime_cli
from ea_node_editor.execution.runtime_requests import ExecutionResult


def test_runtime_cli_module_help() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ea_node_editor.execution.runtime_cli", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert "usage: corex-runtime" in completed.stdout


class _CliRuntime:
    status = "completed"
    failure: Exception | None = None

    def run(self, request, *, timeout=None, on_event=None):  # noqa: ANN001, ANN201
        del request, timeout
        if self.failure is not None:
            raise self.failure
        if on_event is not None:
            on_event(
                {
                    "type": "log",
                    "run_id": "run_cli",
                    "workspace_id": "ws_cli",
                    "message": "hello",
                }
            )
        return ExecutionResult(
            run_id="run_cli",
            workspace_id="ws_cli",
            status=self.status,  # type: ignore[arg-type]
            terminal_event={
                "type": "run_completed" if self.status == "completed" else "run_failed"
            },
        )

    def shutdown(self) -> None:
        return None


def test_runtime_cli_json_output_and_success_exit(monkeypatch, capsys) -> None:  # noqa: ANN001
    _CliRuntime.status = "completed"
    _CliRuntime.failure = None
    monkeypatch.setattr(runtime_cli, "CorexRuntime", _CliRuntime)

    exit_code = runtime_cli.main(
        ["run", "project.cxproj", "--workspace", "ws_cli", "--format", "json"]
    )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert exit_code == 0
    assert [record["record"] for record in records] == ["event", "result"]
    assert records[-1]["result"]["status"] == "completed"


def test_runtime_cli_failed_and_exception_exit_codes(monkeypatch, capsys) -> None:  # noqa: ANN001
    monkeypatch.setattr(runtime_cli, "CorexRuntime", _CliRuntime)
    _CliRuntime.status = "failed"
    _CliRuntime.failure = None
    assert runtime_cli.main(["run", "project.cxproj", "--format", "text"]) == 1
    assert "result status=failed" in capsys.readouterr().out

    _CliRuntime.failure = ValueError("cli failure")
    assert runtime_cli.main(["run", "project.cxproj", "--format", "json"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "cli failure",
        "record": "error",
    }
