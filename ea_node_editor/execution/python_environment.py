from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.common.coercions import normalize_path_text
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, coerce_runtime_snapshot

_PATH_DISPLAY_LIMIT = 600
_ERROR_DETAIL_LIMIT = 400


def _bounded_fragment(value: object, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else f"...{text[-(limit - 3):]}"


@dataclass(frozen=True, slots=True)
class WorkflowPythonEnvironment:
    configured: bool = False
    python_executable: str = ""
    valid: bool = True
    error: str = ""
    is_current_python: bool = False


def _path_key(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return os.path.normcase(str(resolved))


def workflow_python_path_from_snapshot(value: RuntimeSnapshot | Mapping[str, Any] | None) -> str:
    runtime_snapshot = coerce_runtime_snapshot(value)
    metadata = runtime_snapshot.metadata if runtime_snapshot is not None else {}
    if not isinstance(metadata, Mapping):
        return ""
    workflow_settings = metadata.get("workflow_settings")
    if not isinstance(workflow_settings, Mapping):
        return ""
    environment = workflow_settings.get("environment")
    if not isinstance(environment, Mapping):
        return ""
    return normalize_path_text(environment.get("python_path"))


def resolve_python_environment(
    python_executable: Any,
    *,
    current_executable: str | Path | None = None,
) -> WorkflowPythonEnvironment:
    raw_python_path = normalize_path_text(python_executable)
    if not raw_python_path:
        return WorkflowPythonEnvironment()

    try:
        normalized_candidate = Path(raw_python_path).expanduser().resolve()
        if not normalized_candidate.exists():
            error = "does not exist"
        elif not normalized_candidate.is_file():
            error = "is not a file"
        elif not os.access(normalized_candidate, os.X_OK):
            error = "is not executable"
        else:
            current = Path(current_executable or sys.executable)
            return WorkflowPythonEnvironment(
                configured=True,
                python_executable=str(normalized_candidate),
                valid=True,
                is_current_python=_path_key(normalized_candidate) == _path_key(current),
            )
    except (ValueError, RuntimeError, OSError) as exc:
        display_path = _bounded_fragment(raw_python_path, _PATH_DISPLAY_LIMIT)
        return WorkflowPythonEnvironment(
            configured=True,
            python_executable=display_path,
            valid=False,
            error=(
                f"Configured Python executable path is invalid: {display_path}. "
                f"{_bounded_fragment(exc, _ERROR_DETAIL_LIMIT)}"
            ),
        )

    display_path = _bounded_fragment(normalized_candidate, _PATH_DISPLAY_LIMIT)
    return WorkflowPythonEnvironment(
        configured=True,
        python_executable=display_path,
        valid=False,
        error=f"Configured Python executable {error}: {display_path}",
    )


__all__ = [
    "WorkflowPythonEnvironment",
    "resolve_python_environment",
    "workflow_python_path_from_snapshot",
]
