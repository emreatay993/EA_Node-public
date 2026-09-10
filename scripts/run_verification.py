#!/usr/bin/env python3
"""Run split verification phases for the COREX Node Editor repo."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

try:
    import verification_manifest as manifest
except ModuleNotFoundError:
    import scripts.verification_manifest as manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_VENV_PYTHON = REPO_ROOT / "venv" / "Scripts" / "python.exe"
DEFAULT_SUMMARY_LOG_DIR = REPO_ROOT / "artifacts" / "verification_logs"
_MODULE_AVAILABLE_PROBE = (
    "import importlib, sys; "
    "importlib.import_module(sys.argv[1])"
)
_PYTEST_STARTUP_PROBE_ARGS = (
    "-m",
    "pytest",
    "--collect-only",
    "-q",
    "tests/test_run_verification.py",
    "--ignore=venv",
)
_MISSING_MODULE_PATTERN = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_PIP_CHECK_MISSING_REQUIREMENT_PATTERN = re.compile(
    r"^(?P<dist>[A-Za-z0-9_.-]+)\s+\S+\s+requires\s+(?P<requirement>.+), which is not installed\.$"
)
_PIP_CHECK_INCOMPATIBLE_REQUIREMENT_PATTERN = re.compile(
    r"^(?P<dist>[A-Za-z0-9_.-]+)\s+\S+\s+has requirement\s+"
    r"(?P<requirement>.+), but you have .+\.$"
)
_PYTEST_CORE_DISTS = frozenset({"pytest", "pytest-xdist"})
_PYTEST_STACK_REPAIR_PACKAGES = {
    "_pytest": "pytest",
    "pytest": "pytest",
    "colorama": "colorama",
    "coverage": "coverage[toml]",
    "execnet": "execnet>=2.1",
    "exceptiongroup": "exceptiongroup",
    "iniconfig": "iniconfig",
    "packaging": "packaging",
    "pluggy": "pluggy",
    "pygments": "pygments",
    "tomli": "tomli",
    "typing_extensions": "typing-extensions",
}
_PYQT_QT_VERSION_PROBE = (
    "from PyQt6.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)"
)
_QML_QUICK_SETUP_HINT = (
    "Install a matching Qt Quick Test SDK and set QT_ROOT to the Qt installation root."
)


@dataclass(frozen=True)
class CommandSpec:
    """One concrete verification command."""

    phase: str
    argv: tuple[str, ...]
    display_argv: tuple[str, ...]
    env: dict[str, str]
    notice: str | None = None


def local_venv_python_exists() -> bool:
    try:
        return LOCAL_VENV_PYTHON.exists()
    except OSError:
        return False


def current_python_matches_project_venv() -> bool:
    return Path(sys.executable).as_posix().lower().endswith("/venv/scripts/python.exe")


def resolve_python() -> tuple[str, str]:
    if local_venv_python_exists():
        return str(LOCAL_VENV_PYTHON), manifest.LOCAL_VENV_PYTHON_DISPLAY
    if current_python_matches_project_venv():
        return sys.executable, manifest.LOCAL_VENV_PYTHON_DISPLAY
    return sys.executable, sys.executable


def _qmltestrunner_name() -> str:
    return "qmltestrunner.exe" if os.name == "nt" else "qmltestrunner"


def resolve_qmltestrunner() -> Path:
    executable_name = _qmltestrunner_name()
    qt_root = os.environ.get("QT_ROOT")
    if qt_root:
        runner = Path(qt_root) / "bin" / executable_name
        if runner.is_file():
            return runner
        raise RuntimeError(
            f"QT_ROOT does not contain {runner}. {_QML_QUICK_SETUP_HINT}"
        )

    resolved = shutil.which(executable_name)
    if resolved is None and executable_name != "qmltestrunner":
        resolved = shutil.which("qmltestrunner")
    if resolved is None:
        raise RuntimeError(
            f"{executable_name} was not found on PATH. {_QML_QUICK_SETUP_HINT}"
        )
    return Path(resolved)


def resolve_qtpaths(qmltestrunner: Path) -> Path:
    names = (
        ("qtpaths6.exe", "qtpaths.exe")
        if os.name == "nt"
        else ("qtpaths6", "qtpaths")
    )
    for name in names:
        candidate = qmltestrunner.parent / name
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        f"Neither {names[0]} nor {names[1]} exists beside {qmltestrunner}. "
        f"{_QML_QUICK_SETUP_HINT}"
    )


def probe_command_output(argv: Sequence[str], description: str) -> str:
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Failed to launch {description}: {exc}. {_QML_QUICK_SETUP_HINT}"
        ) from exc
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    ).strip()
    if completed.returncode != 0 or not output:
        detail = output or "no version output"
        raise RuntimeError(
            f"Failed to query {description}: {detail}. {_QML_QUICK_SETUP_HINT}"
        )
    return output


def qt_major_minor(version_output: str, description: str) -> tuple[int, int]:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.\d+)?(?!\d)", version_output)
    if match is None:
        raise RuntimeError(
            f"Could not parse the {description} Qt version from {version_output!r}. "
            f"{_QML_QUICK_SETUP_HINT}"
        )
    return int(match.group(1)), int(match.group(2))


def validate_qmltestrunner_version(qmltestrunner: Path, python_exec: str) -> None:
    qtpaths = resolve_qtpaths(qmltestrunner)
    sdk_version = probe_command_output([str(qtpaths), "--qt-version"], "Qt SDK version")
    pyqt_version = probe_command_output(
        [python_exec, "-c", _PYQT_QT_VERSION_PROBE],
        "PyQt Qt version",
    )
    if qt_major_minor(sdk_version, "Qt SDK") != qt_major_minor(pyqt_version, "PyQt"):
        raise RuntimeError(
            "Qt Quick Test and PyQt must use the same Qt major/minor version; "
            f"found SDK {sdk_version!r} and PyQt {pyqt_version!r}. "
            f"{_QML_QUICK_SETUP_HINT}"
        )


def resolve_qml_quick_runner(
    python_exec: str, *, dry_run: bool
) -> tuple[str, str | None]:
    try:
        runner = resolve_qmltestrunner()
        validate_qmltestrunner_version(runner, python_exec)
        return str(runner), None
    except RuntimeError as exc:
        if not dry_run:
            raise
        return _qmltestrunner_name(), f"{exc} Real gui/full execution requires it."


def python_module_available(python_exec: str, module_name: str) -> bool:
    completed = subprocess.run(
        [python_exec, "-c", _MODULE_AVAILABLE_PROBE, module_name],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode == 0


def pytest_xdist_available(python_exec: str) -> bool:
    return python_module_available(python_exec, "xdist.newhooks")


def probe_pytest_startup(python_exec: str) -> tuple[bool, str]:
    completed = subprocess.run(
        [python_exec, *_PYTEST_STARTUP_PROBE_ARGS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True, ""

    return (
        False,
        "\n".join(
            part.strip()
            for part in (completed.stderr, completed.stdout)
            if part and part.strip()
        ).strip(),
    )


def missing_module_from_output(failure_output: str) -> str | None:
    match = _MISSING_MODULE_PATTERN.search(failure_output)
    return None if match is None else match.group(1)


def pytest_related_unmet_requirements(
    python_exec: str, *, include_plugins: bool = True
) -> tuple[str, ...]:
    completed = subprocess.run(
        [python_exec, "-m", "pip", "--disable-pip-version-check", "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return ()

    requirements: list[str] = []
    lines = [
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    ]
    for output in lines:
        for line in output.splitlines():
            stripped = line.strip()
            match = _PIP_CHECK_MISSING_REQUIREMENT_PATTERN.match(stripped)
            if match is None:
                match = _PIP_CHECK_INCOMPATIBLE_REQUIREMENT_PATTERN.match(stripped)
            if match is None:
                continue
            dist_name = match.group("dist").lower()
            is_relevant = (
                dist_name.startswith("pytest")
                if include_plugins
                else dist_name in _PYTEST_CORE_DISTS
            )
            if not is_relevant:
                continue
            requirement = match.group("requirement").strip()
            if requirement not in requirements:
                requirements.append(requirement)
    return tuple(requirements)


def install_python_packages(python_exec: str, *packages: str) -> int:
    completed = subprocess.run(
        [
            python_exec,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *packages,
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode


def ensure_pytest_stack_ready(python_exec: str) -> bool:
    attempted_repairs: set[str] = set()
    repaired = False
    max_attempts = len(_PYTEST_STACK_REPAIR_PACKAGES) + 1

    for _ in range(max_attempts):
        core_unmet_requirements = tuple(
            requirement
            for requirement in pytest_related_unmet_requirements(
                python_exec, include_plugins=False
            )
            if requirement not in attempted_repairs
        )
        if core_unmet_requirements:
            print(
                "NOTE: pip check found broken core pytest requirements in the project "
                "venv. Installing "
                + ", ".join(f"'{requirement}'" for requirement in core_unmet_requirements)
                + " and retrying."
            )
            install_return_code = install_python_packages(python_exec, *core_unmet_requirements)
            if install_return_code != 0:
                raise RuntimeError(
                    "Automatic pytest-stack repair failed while installing core pip-check "
                    f"requirements (exit code {install_return_code})."
                )
            attempted_repairs.update(core_unmet_requirements)
            repaired = True
            continue

        startup_ok, failure_output = probe_pytest_startup(python_exec)
        if startup_ok:
            return repaired

        missing_module = missing_module_from_output(failure_output)
        package_name = None if missing_module is None else _PYTEST_STACK_REPAIR_PACKAGES.get(
            missing_module
        )
        if package_name is not None and package_name not in attempted_repairs:
            print(
                "NOTE: pytest startup failed because "
                f"'{missing_module}' is missing in the project venv. "
                f"Installing '{package_name}' and retrying."
            )
            install_return_code = install_python_packages(python_exec, package_name)
            if install_return_code != 0:
                raise RuntimeError(
                    f"Automatic pytest-stack repair failed while installing '{package_name}' "
                    f"(exit code {install_return_code})."
                )
            attempted_repairs.add(package_name)
            repaired = True
            continue

        unmet_requirements = tuple(
            requirement
            for requirement in pytest_related_unmet_requirements(
                python_exec, include_plugins=True
            )
            if requirement not in attempted_repairs
        )
        if unmet_requirements:
            print(
                "NOTE: pip check found broken pytest-related requirements in the project "
                "venv. Installing "
                + ", ".join(f"'{requirement}'" for requirement in unmet_requirements)
                + " and retrying."
            )
            install_return_code = install_python_packages(python_exec, *unmet_requirements)
            if install_return_code != 0:
                raise RuntimeError(
                    "Automatic pytest-stack repair failed while installing pip-check "
                    f"requirements (exit code {install_return_code})."
                )
            attempted_repairs.update(unmet_requirements)
            repaired = True
            continue

        raise RuntimeError(
            "pytest is not startup-ready in the project venv after the automatic repair "
            "attempt.\n"
            f"{failure_output}"
        )

    raise RuntimeError("pytest remains unavailable in the project venv after repair attempts.")


def resolve_max_parallel_workers() -> int:
    if importlib.util.find_spec("psutil") is not None:
        import psutil

        resolved = psutil.cpu_count(logical=True)
        if resolved is not None:
            return resolved
    return os.cpu_count() or 1


def resolve_gui_parallel_workers(max_parallel_workers: int) -> int:
    return max(1, min(max_parallel_workers, manifest.MAX_GUI_PARALLEL_WORKERS))


def build_pytest_command(
    *,
    phase: str,
    marker_expression: str,
    faulthandler_timeout_seconds: int | None,
    python_exec: str,
    python_display: str,
    use_xdist: bool,
    worker_count: int,
    target_args: Sequence[str] = (),
    deselect_args: Sequence[str] = (),
    notice: str | None = None,
) -> CommandSpec:
    argv = [python_exec, "-m", "pytest"]
    display_argv = [python_display, "-m", "pytest"]
    if use_xdist:
        argv.extend(["-n", str(worker_count), "--dist", "load"])
        display_argv.extend(["-n", str(worker_count), "--dist", "load"])
    timeout_args = manifest.pytest_faulthandler_timeout_args(faulthandler_timeout_seconds)
    argv.extend(timeout_args)
    display_argv.extend(timeout_args)
    argv.extend(["-m", marker_expression])
    display_argv.extend(["-m", marker_expression])
    for ignore_arg in manifest.worktree_pytest_ignore_args():
        argv.append(ignore_arg)
        display_argv.append(ignore_arg)
    for ignore_arg in manifest.non_shell_pytest_ignore_args():
        argv.append(ignore_arg)
        display_argv.append(ignore_arg)
    argv.extend(deselect_args)
    display_argv.extend(deselect_args)
    argv.extend(target_args)
    display_argv.extend(target_args)
    return CommandSpec(
        phase=phase,
        argv=tuple(argv),
        display_argv=tuple(display_argv),
        env=manifest.OFFSCREEN_ENV,
        notice=notice,
    )


def build_shell_isolation_phase_command(
    *,
    python_exec: str,
    python_display: str,
    use_xdist: bool,
    worker_count: int,
    notice: str | None = None,
) -> CommandSpec:
    phase_args = manifest.shell_isolation_phase_pytest_args(
        worker_count if use_xdist else None
    )
    argv = [python_exec, *phase_args]
    display_argv = [python_display, *phase_args]
    return CommandSpec(
        phase=manifest.SHELL_ISOLATION_SPEC.phase,
        argv=tuple(argv),
        display_argv=tuple(display_argv),
        env=manifest.OFFSCREEN_ENV,
        notice=notice,
    )


def build_context_budget_command(
    *,
    python_exec: str,
    python_display: str,
) -> CommandSpec:
    return CommandSpec(
        phase=manifest.CONTEXT_BUDGET_PHASE,
        argv=(python_exec, manifest.CHECK_CONTEXT_BUDGETS_SCRIPT),
        display_argv=(python_display, manifest.CHECK_CONTEXT_BUDGETS_SCRIPT),
        env={},
    )


def build_qml_quick_command(runner: str, notice: str | None = None) -> CommandSpec:
    argv = (runner, *manifest.QML_QUICK_ARGS)
    return CommandSpec(
        phase=manifest.QML_QUICK_PHASE,
        argv=argv,
        display_argv=argv,
        env=manifest.QML_QUICK_ENV,
        notice=notice,
    )


def build_commands(
    mode: str,
    *,
    dry_run: bool = False,
    qml_quick_runner: tuple[str, str | None] | None = None,
) -> list[CommandSpec]:
    python_exec, python_display = resolve_python()
    xdist_available = pytest_xdist_available(python_exec)
    worker_count = resolve_max_parallel_workers()
    notices = {
        "fast": "pytest-xdist is unavailable; falling back to serial pytest for fast mode.",
        "gui": "pytest-xdist is unavailable; falling back to serial pytest for gui mode.",
        manifest.SHELL_ISOLATION_PHASE_KEY: (
            "pytest-xdist is unavailable; falling back to serial pytest for the shell-isolation phase."
        ),
    }

    commands_by_key: dict[str, CommandSpec] = {}
    for phase_key in manifest.RUN_VERIFICATION_MODE_SEQUENCE[mode]:
        if phase_key == manifest.QML_QUICK_PHASE_KEY:
            runner, notice = qml_quick_runner or resolve_qml_quick_runner(
                python_exec,
                dry_run=dry_run,
            )
            commands_by_key[phase_key] = build_qml_quick_command(runner, notice)
            continue
        if phase_key == manifest.CONTEXT_BUDGET_PHASE_KEY:
            commands_by_key[phase_key] = build_context_budget_command(
                python_exec=python_exec,
                python_display=python_display,
            )
            continue
        if phase_key == manifest.SHELL_ISOLATION_PHASE_KEY:
            shell_worker_cap = manifest.verification_suite_spec(phase_key).worker_cap
            shell_worker_count = (
                min(worker_count, shell_worker_cap)
                if shell_worker_cap is not None
                else worker_count
            )
            commands_by_key[phase_key] = build_shell_isolation_phase_command(
                python_exec=python_exec,
                python_display=python_display,
                use_xdist=xdist_available,
                worker_count=shell_worker_count,
                notice=None if xdist_available else notices[phase_key],
            )
            continue

        phase_spec = manifest.PYTEST_PHASE_SPECS_BY_MODE[phase_key]
        phase_worker_count = worker_count
        if phase_key == "gui":
            phase_worker_count = resolve_gui_parallel_workers(worker_count)
        target_args: tuple[str, ...] = ()
        deselect_args: tuple[str, ...] = ()
        if phase_key == manifest.FAST_SUITE_KEY:
            deselect_args = manifest.fast_serial_pytest_deselect_args()
        elif phase_key == manifest.FAST_SERIAL_SUITE_KEY:
            target_args = manifest.fast_serial_pytest_targets()
        elif phase_key == manifest.GUI_SUITE_KEY:
            deselect_args = manifest.gui_serial_pytest_deselect_args()
        elif phase_key == manifest.GUI_SERIAL_SUITE_KEY:
            target_args = manifest.gui_serial_pytest_targets()
        commands_by_key[phase_key] = build_pytest_command(
            phase=phase_spec.phase,
            marker_expression=phase_spec.marker_expression,
            faulthandler_timeout_seconds=phase_spec.faulthandler_timeout_seconds,
            python_exec=python_exec,
            python_display=python_display,
            use_xdist=xdist_available and phase_spec.uses_xdist,
            worker_count=phase_worker_count,
            target_args=target_args,
            deselect_args=deselect_args,
            notice=None if xdist_available else notices.get(phase_key),
        )

    return [commands_by_key[phase_key] for phase_key in manifest.RUN_VERIFICATION_MODE_SEQUENCE[mode]]


def format_command(command: CommandSpec) -> str:
    if os.name == "nt":
        env_prefix = " ".join(
            f"$env:{name}={_powershell_quote(value)};" for name, value in sorted(command.env.items())
        )
        display_argv = tuple(_powershell_display_arg(part) for part in command.display_argv)
        argv = " ".join(_powershell_quote(part) for part in display_argv)
        if env_prefix:
            return f"{env_prefix} & {argv}"
        return f"& {argv}"

    env_prefix = " ".join(
        f"{name}={shlex.quote(value)}" for name, value in sorted(command.env.items())
    )
    argv = " ".join(shlex.quote(part) for part in command.display_argv)
    if env_prefix:
        return f"{env_prefix} {argv}"
    return argv


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell_display_arg(value: str) -> str:
    if value.startswith("./"):
        return ".\\" + value[2:].replace("/", "\\")
    return value


def run_command(command: CommandSpec) -> int:
    env = os.environ.copy()
    env.update(command.env)
    completed = subprocess.run(command.argv, cwd=REPO_ROOT, env=env, check=False)
    return completed.returncode


def _safe_log_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return stem.strip("._") or "phase"


def _relative_display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _tail_lines(path: Path, max_lines: int) -> tuple[str, ...]:
    if max_lines <= 0:
        return ()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return (f"<failed to read log tail: {exc}>",)
    return tuple(lines[-max_lines:])


def run_command_summarized(
    command: CommandSpec,
    *,
    log_path: Path,
    failure_tail_lines: int,
) -> int:
    reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure_stdout):
        reconfigure_stdout(errors="replace")
    env = os.environ.copy()
    env.update(command.env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        completed = subprocess.run(
            command.argv,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    display_path = _relative_display_path(log_path)
    if completed.returncode == 0:
        print(f"PASS: {command.phase} output captured at {display_path}")
        return 0

    print(
        f"FAIL: {command.phase} exited {completed.returncode}; "
        f"output captured at {display_path}"
    )
    tail = _tail_lines(log_path, failure_tail_lines)
    if tail:
        print(f"--- last {len(tail)} log line(s) ---")
        for line in tail:
            print(line)
        print("--- end log tail ---")
    return completed.returncode


def create_summary_log_dir(base_dir: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_dir / run_id


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=manifest.MODE_NAMES,
        help="verification phase selection",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the concrete commands without executing them",
    )
    parser.add_argument(
        "--summarize-output",
        action="store_true",
        help=(
            "capture each phase's stdout/stderr to artifacts and print only a "
            "bounded summary; failing phases include a log tail"
        ),
    )
    parser.add_argument(
        "--summary-log-dir",
        type=Path,
        default=DEFAULT_SUMMARY_LOG_DIR,
        help="base directory for --summarize-output logs",
    )
    parser.add_argument(
        "--failure-tail-lines",
        type=int,
        default=80,
        help="number of captured log lines to print for a failing summarized phase",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    python_exec, _python_display = resolve_python()
    qml_quick_runner = None
    if manifest.QML_QUICK_PHASE_KEY in manifest.RUN_VERIFICATION_MODE_SEQUENCE[args.mode]:
        try:
            qml_quick_runner = resolve_qml_quick_runner(
                python_exec,
                dry_run=args.dry_run,
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    if not args.dry_run:
        try:
            ensure_pytest_stack_ready(python_exec)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    commands = build_commands(
        args.mode,
        dry_run=args.dry_run,
        qml_quick_runner=qml_quick_runner,
    )
    summary_log_dir = (
        create_summary_log_dir(args.summary_log_dir) if args.summarize_output else None
    )
    for index, command in enumerate(commands, start=1):
        print(f"[{command.phase}]")
        if command.notice:
            print(f"NOTE: {command.notice}")
        print(format_command(command))
        if args.dry_run:
            continue
        if summary_log_dir is None:
            return_code = run_command(command)
        else:
            log_path = summary_log_dir / f"{index:02d}_{_safe_log_stem(command.phase)}.log"
            return_code = run_command_summarized(
                command,
                log_path=log_path,
                failure_tail_lines=max(0, args.failure_tail_lines),
            )
        if return_code != 0:
            return return_code
    if args.dry_run:
        print("Dry run only; no commands executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
