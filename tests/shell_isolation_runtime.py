"""Shared runtime for shell-isolated verification targets."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

try:
    import verification_manifest as manifest
except ModuleNotFoundError:
    import scripts.verification_manifest as manifest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_SESSION_SCENARIO_ARG = "--scenario"
_PROJECT_SESSION_SCENARIO_MODULE = "tests.test_shell_project_session_controller"


class ShellIsolationTargetTimeout(RuntimeError):
    """Raised when one shell-isolated child exceeds its target hard limit."""


def _stable_target_id(prefix: str, value: str) -> str:
    normalized = value.replace("\\", "/")
    return f"{prefix}::{normalized}"


def _normalized_env_overrides(
    extra_env: Mapping[str, str] | None,
) -> tuple[tuple[str, str], ...]:
    if not extra_env:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in extra_env.items()))


def build_unittest_module_command(module_name: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "unittest", module_name)


def build_unittest_target_command(dotted_target: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "unittest", dotted_target)


def build_unittest_target_list_command(
    dotted_targets: Sequence[str],
) -> tuple[str, ...]:
    if not dotted_targets:
        raise ValueError("unittest_target_list requires at least one dotted target.")
    return (sys.executable, "-m", "unittest", *dotted_targets)


def build_pytest_nodeid_command(nodeid: str) -> tuple[str, ...]:
    pytest_args = manifest.shell_isolation_target_pytest_args(nodeid)
    return (sys.executable, *pytest_args[:2], "-n", "0", *pytest_args[2:])


def build_pytest_nodeid_list_command(nodeids: Sequence[str]) -> tuple[str, ...]:
    if not nodeids:
        raise ValueError("pytest_nodeid_list requires at least one nodeid.")
    pytest_args = manifest.shell_isolation_target_pytest_args(*nodeids)
    return (sys.executable, *pytest_args[:2], "-n", "0", *pytest_args[2:])


def build_project_session_scenario_command(scenario_name: str) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        _PROJECT_SESSION_SCENARIO_MODULE,
        _PROJECT_SESSION_SCENARIO_ARG,
        scenario_name,
    )


@dataclass(frozen=True, slots=True)
class ShellIsolationTarget:
    """Shell-isolated child-process target definition."""

    target_id: str
    command: tuple[str, ...]
    extra_env: tuple[tuple[str, str], ...] = ()

    @classmethod
    def unittest_module(
        cls,
        module_name: str,
        *,
        target_id: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id or _stable_target_id("unittest-module", module_name),
            command=build_unittest_module_command(module_name),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @classmethod
    def unittest_target(
        cls,
        dotted_target: str,
        *,
        target_id: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id or _stable_target_id("unittest-target", dotted_target),
            command=build_unittest_target_command(dotted_target),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @classmethod
    def unittest_target_list(
        cls,
        target_id: str,
        dotted_targets: Sequence[str],
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id,
            command=build_unittest_target_list_command(dotted_targets),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @classmethod
    def pytest_nodeid(
        cls,
        nodeid: str,
        *,
        target_id: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id or _stable_target_id("pytest-nodeid", nodeid),
            command=build_pytest_nodeid_command(nodeid),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @classmethod
    def pytest_nodeid_list(
        cls,
        target_id: str,
        nodeids: Sequence[str],
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id,
            command=build_pytest_nodeid_list_command(nodeids),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @classmethod
    def project_session_scenario(
        cls,
        scenario_name: str,
        *,
        target_id: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> "ShellIsolationTarget":
        return cls(
            target_id=target_id
            or _stable_target_id("project-session-scenario", scenario_name),
            command=build_project_session_scenario_command(scenario_name),
            extra_env=_normalized_env_overrides(extra_env),
        )

    @property
    def env_overrides(self) -> dict[str, str]:
        return dict(self.extra_env)


def load_target_registry() -> dict[str, ShellIsolationTarget]:
    registry: dict[str, ShellIsolationTarget] = {}
    for catalog_spec in manifest.SHELL_ISOLATION_CATALOG_SPECS:
        catalog_module = importlib.import_module(catalog_spec.module_name)
        targets = getattr(catalog_module, "TARGETS", ())
        for target in targets:
            if not isinstance(target, ShellIsolationTarget):
                raise TypeError(
                    f"{catalog_spec.module_name}.TARGETS must contain ShellIsolationTarget instances; "
                    f"got {type(target).__name__}."
                )
            if not target.target_id.startswith(catalog_spec.target_id_prefixes):
                expected_prefixes = ", ".join(catalog_spec.target_id_prefixes)
                raise ValueError(
                    f"{catalog_spec.module_name} target_id {target.target_id!r} must start with one "
                    f"of: {expected_prefixes}."
                )
            if target.target_id in registry:
                raise ValueError(
                    f"Duplicate shell isolation target_id {target.target_id!r} "
                    f"found while loading {catalog_spec.module_name}."
                )
            registry[target.target_id] = target
    return registry


def list_target_ids() -> tuple[str, ...]:
    return tuple(sorted(load_target_registry()))


def shell_lifecycle_contract() -> dict[str, str]:
    return {
        "truth": manifest.SHELL_LIFECYCLE_TRUTH,
        "shared_window_scope": manifest.SHELL_LIFECYCLE_SHARED_WINDOW_SCOPE,
        "lifecycle_test_path": manifest.SHELL_WINDOW_LIFECYCLE_TEST_PATH,
    }


def resolve_target(target_id: str) -> ShellIsolationTarget:
    registry = load_target_registry()
    try:
        return registry[target_id]
    except KeyError as exc:
        available = ", ".join(sorted(registry)) or "<none>"
        raise KeyError(
            f"Unknown shell isolation target_id {target_id!r}. Available targets: {available}"
        ) from exc


def run_shell_isolation_target(
    target: ShellIsolationTarget,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(target.env_overrides)
    env.update(manifest.OFFSCREEN_ENV)
    env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    timeout_seconds = manifest.SHELL_ISOLATION_SPEC.target_timeout_seconds
    started_at = time.monotonic()
    try:
        return subprocess.run(
            target.command,
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_seconds = time.monotonic() - started_at
        raise ShellIsolationTargetTimeout(
            "Shell isolation child process timed out "
            f"for {target.target_id} after {elapsed_seconds:.2f}s "
            f"(hard limit={timeout_seconds}s).\n"
            f"Command: {' '.join(target.command)}\n"
            f"{format_child_streams(exc.stdout, exc.stderr)}"
        ) from exc


def _normalize_child_stream(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value or "").strip()


def format_child_streams(
    stdout_value: str | bytes | None,
    stderr_value: str | bytes | None,
) -> str:
    stdout = _normalize_child_stream(stdout_value)
    stderr = _normalize_child_stream(stderr_value)
    return "\n".join(
        (
            "stdout:",
            stdout or "<empty>",
            "stderr:",
            stderr or "<empty>",
        )
    )


def format_child_output(completed: subprocess.CompletedProcess[str]) -> str:
    return format_child_streams(completed.stdout, completed.stderr)
