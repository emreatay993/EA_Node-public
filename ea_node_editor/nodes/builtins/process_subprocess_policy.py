from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PROCESS_STREAM_CAPTURE_CHAR_LIMIT = 262_144
PROCESS_STREAM_QUEUE_SIZE = 256
PROCESS_STDERR_ERROR_TAIL_CHAR_LIMIT = 4_096
PROCESS_OUTPUT_MODE_MEMORY = "memory"
PROCESS_OUTPUT_MODE_STORED = "stored"
PROCESS_TRANSCRIPT_SUFFIX = ".log"
PROCESS_TRANSCRIPT_SUBDIRECTORY = "generated/process_run"

ProcessOutputMode = Literal["memory", "stored"]


def normalize_args(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:  # noqa: BLE001
        pass
    return shlex.split(text, posix=False)


def normalize_env(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in value.items()}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        return {}
    if isinstance(parsed, Mapping):
        return {str(key): str(item) for key, item in parsed.items()}
    return {}


def normalize_output_mode(value: Any) -> ProcessOutputMode:
    normalized = str(value or PROCESS_OUTPUT_MODE_MEMORY).strip().lower()
    if normalized not in {PROCESS_OUTPUT_MODE_MEMORY, PROCESS_OUTPUT_MODE_STORED}:
        raise ValueError(
            "Process Run output_mode must be either "
            f"{PROCESS_OUTPUT_MODE_MEMORY!r} or {PROCESS_OUTPUT_MODE_STORED!r}."
        )
    return normalized  # type: ignore[return-value]


def _normalize_positive_float(field_name: str, value: Any, *, default: float) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = default
    if normalized <= 0:
        raise ValueError(f"Process Run {field_name} must be > 0.")
    return normalized


def _normalize_non_negative_int(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized)


@dataclass(frozen=True, slots=True)
class ProcessStreamPolicy:
    queue_size: int = PROCESS_STREAM_QUEUE_SIZE
    capture_char_limit: int = PROCESS_STREAM_CAPTURE_CHAR_LIMIT
    stderr_error_tail_char_limit: int = PROCESS_STDERR_ERROR_TAIL_CHAR_LIMIT

    def __post_init__(self) -> None:
        object.__setattr__(self, "queue_size", max(1, int(self.queue_size)))
        object.__setattr__(self, "capture_char_limit", max(1, int(self.capture_char_limit)))
        object.__setattr__(
            self,
            "stderr_error_tail_char_limit",
            max(1, int(self.stderr_error_tail_char_limit)),
        )


@dataclass(frozen=True, slots=True)
class ProcessResourceHints:
    core_hint: int = 0
    thread_hint: int = 0
    memory_mb_hint: int = 0

    @classmethod
    def from_properties(cls, properties: Mapping[str, Any]) -> "ProcessResourceHints":
        return cls(
            core_hint=_normalize_non_negative_int(properties.get("core_hint", 0)),
            thread_hint=_normalize_non_negative_int(properties.get("thread_hint", 0)),
            memory_mb_hint=_normalize_non_negative_int(properties.get("memory_mb_hint", 0)),
        )

    def to_metadata(self) -> dict[str, int]:
        return {
            "core_hint": self.core_hint,
            "thread_hint": self.thread_hint,
            "memory_mb_hint": self.memory_mb_hint,
        }


@dataclass(frozen=True, slots=True)
class ExternalSubprocessPolicy:
    command: str
    args: tuple[str, ...] = ()
    stdin_text: str = ""
    cwd: str = ""
    env_overrides: dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 60.0
    shell: bool = False
    fail_on_nonzero: bool = True
    encoding: str = "utf-8"
    output_mode: ProcessOutputMode = PROCESS_OUTPUT_MODE_MEMORY
    termination_grace_sec: float = 0.6
    stream_policy: ProcessStreamPolicy = field(default_factory=ProcessStreamPolicy)
    resource_hints: ProcessResourceHints = field(default_factory=ProcessResourceHints)

    def __post_init__(self) -> None:
        command = str(self.command).strip()
        if not command:
            raise ValueError("Process Run requires a command.")
        cwd = str(self.cwd or "").strip()
        if cwd and not Path(cwd).exists():
            raise ValueError(f"Process Run working directory does not exist: {cwd}")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "args", tuple(str(item) for item in self.args))
        object.__setattr__(self, "stdin_text", str(self.stdin_text))
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(
            self,
            "env_overrides",
            {str(key): str(item) for key, item in self.env_overrides.items()},
        )
        object.__setattr__(self, "timeout_sec", _normalize_positive_float("timeout_sec", self.timeout_sec, default=60.0))
        object.__setattr__(
            self,
            "termination_grace_sec",
            _normalize_positive_float("termination_grace_sec", self.termination_grace_sec, default=0.6),
        )
        object.__setattr__(self, "encoding", str(self.encoding or "utf-8").strip() or "utf-8")
        object.__setattr__(self, "output_mode", normalize_output_mode(self.output_mode))

    @classmethod
    def from_process_run_inputs(
        cls,
        *,
        inputs: Mapping[str, Any],
        properties: Mapping[str, Any],
    ) -> "ExternalSubprocessPolicy":
        command = str(inputs.get("command", properties.get("command", ""))).strip()
        return cls(
            command=command,
            args=tuple(normalize_args(inputs.get("args", properties.get("args", "[]")))),
            stdin_text=str(inputs.get("stdin_text", "")),
            cwd=str(properties.get("cwd", "")).strip(),
            env_overrides=normalize_env(properties.get("env", {})),
            timeout_sec=float(properties.get("timeout_sec", 60.0)),
            shell=bool(properties.get("shell", False)),
            fail_on_nonzero=bool(properties.get("fail_on_nonzero", True)),
            encoding=str(properties.get("encoding", "utf-8")).strip() or "utf-8",
            output_mode=normalize_output_mode(properties.get("output_mode", PROCESS_OUTPUT_MODE_MEMORY)),
            termination_grace_sec=float(properties.get("termination_grace_sec", 0.6)),
            stream_policy=ProcessStreamPolicy(),
            resource_hints=ProcessResourceHints.from_properties(properties),
        )

    @property
    def popen_args(self) -> str | list[str]:
        if self.shell:
            return " ".join([self.command, *self.args]).strip()
        return [self.command, *self.args]

    @property
    def popen_cwd(self) -> str | None:
        return self.cwd or None

    def build_environment(self, base_environment: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(base_environment or os.environ)
        env.update(self.env_overrides)
        return env


__all__ = [
    "ExternalSubprocessPolicy",
    "PROCESS_OUTPUT_MODE_MEMORY",
    "PROCESS_OUTPUT_MODE_STORED",
    "PROCESS_STDERR_ERROR_TAIL_CHAR_LIMIT",
    "PROCESS_STREAM_CAPTURE_CHAR_LIMIT",
    "PROCESS_STREAM_QUEUE_SIZE",
    "PROCESS_TRANSCRIPT_SUBDIRECTORY",
    "PROCESS_TRANSCRIPT_SUFFIX",
    "ProcessOutputMode",
    "ProcessResourceHints",
    "ProcessStreamPolicy",
    "normalize_args",
    "normalize_env",
    "normalize_output_mode",
]
