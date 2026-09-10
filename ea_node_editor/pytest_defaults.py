"""Safe default pytest parallelism for local developer runs.

This plugin keeps direct ``pytest`` invocations fast by default while avoiding
the Qt/QML-heavy, slow, and shell-isolation slices that have higher memory and
process-isolation requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

try:
    import psutil
except ImportError:  # pragma: no cover - project dev env ships psutil
    psutil = None

try:
    from scripts import verification_manifest as _manifest
except ModuleNotFoundError:  # pragma: no cover - repo-local tests always have it
    _manifest = None


_FAST_MARKEXPR = "not gui and not slow"


@dataclass(frozen=True)
class DefaultParallelismDecision:
    """One scheduling decision for the current pytest invocation."""

    enable_xdist: bool
    markexpr: str | None = None
    ignored_paths: tuple[str, ...] = ()


def _manifest_available() -> bool:
    return _manifest is not None


def _normalize_cli_target(arg: str, rootdir: Path) -> str | None:
    if not arg or arg.startswith("-"):
        return None

    raw_path = arg.split("::", 1)[0]
    if not raw_path:
        return None

    path = Path(raw_path)
    if not path.is_absolute():
        path = rootdir / path

    try:
        relative = path.resolve(strict=False).relative_to(rootdir.resolve())
    except ValueError:
        if path.is_absolute():
            return None
        relative = Path(raw_path)

    return relative.as_posix()


def selected_test_paths(args: tuple[str, ...], rootdir: Path) -> tuple[str, ...]:
    """Return normalized test paths from explicit CLI targets."""

    selected: list[str] = []
    for arg in args:
        normalized = _normalize_cli_target(arg, rootdir)
        if normalized is not None:
            selected.append(normalized)
    return tuple(selected)


def _is_broad_selection(selected_paths: tuple[str, ...]) -> bool:
    if not selected_paths:
        return True
    return any(not path.endswith(".py") for path in selected_paths)


def _heavy_parallelism_paths() -> set[str]:
    if _manifest is None:
        return set()
    return set(_manifest.heavy_parallelism_test_paths())


def _broad_ignored_paths() -> tuple[str, ...]:
    if _manifest is None:
        return ()
    return tuple(
        dict.fromkeys(
            (
                *_manifest.non_shell_pytest_ignore_paths(),
                *_manifest.fast_serial_pytest_paths(),
            )
        )
    )


def decide_default_parallelism(
    *,
    args: tuple[str, ...],
    rootdir: Path,
    markexpr: str,
) -> DefaultParallelismDecision:
    """Return the safe default scheduling policy for this invocation."""

    if not _manifest_available() or markexpr.strip():
        return DefaultParallelismDecision(enable_xdist=False)

    selected_paths = selected_test_paths(args, rootdir)
    if _is_broad_selection(selected_paths):
        return DefaultParallelismDecision(
            enable_xdist=True,
            markexpr=_FAST_MARKEXPR,
            ignored_paths=_broad_ignored_paths(),
        )

    heavy_paths = _heavy_parallelism_paths()
    if any(path in heavy_paths for path in selected_paths):
        return DefaultParallelismDecision(enable_xdist=False)

    return DefaultParallelismDecision(enable_xdist=True)


def resolve_default_worker_count() -> int:
    """Resolve a conservative worker count for automatic parallel runs."""

    if psutil is None:  # pragma: no cover - project dev env ships psutil
        resolved = os.cpu_count()
    else:
        resolved = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True)

    return max(1, int(resolved or 1))


def _user_requested_parallelism(config: pytest.Config) -> bool:
    numprocesses = getattr(config.option, "numprocesses", None)
    tx = tuple(getattr(config.option, "tx", ()) or ())
    dist = getattr(config.option, "dist", "no")
    distload = bool(getattr(config.option, "distload", False))
    return numprocesses is not None or bool(tx) or dist != "no" or distload


def _should_skip_default_parallelism(config: pytest.Config) -> bool:
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return True
    if not config.pluginmanager.hasplugin("xdist"):
        return True
    if _user_requested_parallelism(config):
        return True
    if config.getoption("usepdb", False):
        return True
    if config.getoption("collectonly"):
        return True
    return False


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> None:
    """Enable safe xdist defaults for plain pytest invocations."""

    if _should_skip_default_parallelism(config):
        return

    rootdir = getattr(config, "rootpath", Path.cwd())
    decision = decide_default_parallelism(
        args=tuple(config.args),
        rootdir=Path(rootdir),
        markexpr=getattr(config.option, "markexpr", "") or "",
    )
    if not decision.enable_xdist:
        return

    if decision.markexpr and not config.option.markexpr:
        config.option.markexpr = decision.markexpr

    ignored = list(getattr(config.option, "ignore", ()) or ())
    for path in decision.ignored_paths:
        if path not in ignored:
            ignored.append(path)
    config.option.ignore = ignored

    worker_count = resolve_default_worker_count()
    config.option.numprocesses = worker_count
    config.option.dist = "load"
    config.option.tx = ["popen"] * worker_count
