# Purpose: Parse corex-runtime arguments and emit stable text/JSON records and exit codes.
# Map: subsystems/execution.md
# Tests: tests/test_runtime_cli.py
# Landmarks: main; _build_arg_parser; _emit_cli_record
"""Qt-free Corex runtime API and CLI entry point."""

from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any

from ea_node_editor.execution.backends import (
    PROCESS_ISOLATED_BACKEND,
    TRUSTED_IN_PROCESS_BACKEND,
    ExecutionBackendPolicy,
)
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest


def _format_text_event(event: Mapping[str, Any]) -> str:
    parts = [
        f"type={event.get('type', '')}",
        f"run_id={event.get('run_id', '')}",
        f"workspace_id={event.get('workspace_id', '')}",
    ]
    node_id = str(event.get("node_id", ""))
    if node_id:
        parts.append(f"node_id={node_id}")
    message = str(event.get("message", "") or event.get("error", ""))
    if message:
        parts.append(f"message={message}")
    return "event " + " ".join(parts)


def _emit_cli_record(record: Mapping[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(copy.deepcopy(dict(record)), sort_keys=True, ensure_ascii=True)
        )
        return
    record_type = str(record.get("record", ""))
    if record_type == "event":
        print(_format_text_event(dict(record.get("event", {}))))
    elif record_type == "result":
        result = dict(record.get("result", {}))
        print(
            "result "
            f"status={result.get('status', '')} "
            f"run_id={result.get('run_id', '')} "
            f"workspace_id={result.get('workspace_id', '')}"
        )
    else:
        print("error " + str(record.get("error", "")))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corex-runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run a Corex workspace without Qt.")
    run_parser.add_argument("project", help="Path to the .cxproj project.")
    run_parser.add_argument(
        "--workspace",
        "-w",
        default="",
        help="Workspace id to run. Defaults to the project's active workspace.",
    )
    run_parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format for streamed events and the final result.",
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Maximum seconds to wait before requesting cancellation.",
    )
    run_parser.add_argument(
        "--execution-backend",
        choices=(PROCESS_ISOLATED_BACKEND, TRUSTED_IN_PROCESS_BACKEND),
        default=PROCESS_ISOLATED_BACKEND,
        help="Execution backend. Process isolation remains the default.",
    )
    run_parser.add_argument(
        "--trust-in-process",
        action="store_true",
        help="Required opt-in when --execution-backend=trusted_in_process.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.command != "run":
        return 2

    runtime = CorexRuntime()
    try:
        result = runtime.run(
            ExecutionRequest(
                project_path=args.project,
                workspace_id=args.workspace,
                trigger={"kind": "headless_cli"},
                execution_backend=ExecutionBackendPolicy(
                    requested_backend=args.execution_backend,
                    allow_trusted_in_process=bool(args.trust_in_process),
                    reason="headless_cli",
                ),
            ),
            timeout=args.timeout,
            on_event=lambda event: _emit_cli_record(
                {"record": "event", "event": event},
                output_format=args.format,
            ),
        )
        _emit_cli_record(
            {"record": "result", "result": result.to_dict()},
            output_format=args.format,
        )
        return 0 if result.status == "completed" else 1
    except Exception as exc:  # noqa: BLE001
        _emit_cli_record(
            {"record": "error", "error": str(exc)},
            output_format=getattr(args, "format", "json"),
        )
        return 2
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
