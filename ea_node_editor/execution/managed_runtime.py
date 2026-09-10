# Purpose: Prepare and verify COREX's managed Python runtime from local package records.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_managed_runtime.py

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea_node_editor.settings import user_data_dir

MANAGED_RUNTIME_DIRNAME = "runtimes"
DEFAULT_MANAGED_RUNTIME_NAME = "default"
RUNTIME_BUNDLE_DIRNAME = "runtime"
RUNTIME_MANIFEST_FILENAME = "runtime_manifest.json"
RUNTIME_MANIFEST_SCHEMA_VERSION = 2
COREX_RUNTIME_PACKAGE_ID = "corex"
MARS_RUNTIME_PACKAGE_ID = "mars"
ADDON_RUNTIME_PYTHON_ENV = "COREX_ADDON_RUNTIME_PYTHON"
RUNTIME_PACKAGE_NAME = "corex-node-editor"
RUNTIME_WHEEL_GLOB = "corex_node_editor-*.whl"
RUNTIME_INSTALL_EXTRAS = ("all",)
RUNTIME_IMPORT_CHECK = "import corex\nimport ea_node_editor.execution.stdio_worker"
RUNTIME_VERSION_CHECK = (
    "from importlib.metadata import PackageNotFoundError, version\n"
    "import sys\n"
    "name, expected = sys.argv[1:3]\n"
    "try:\n"
    "    actual = version(name)\n"
    "except PackageNotFoundError:\n"
    "    raise SystemExit(f'Package is not installed: {name}')\n"
    "if expected and actual != expected:\n"
    "    raise SystemExit(f'Expected {name} {expected}, found {actual}')\n"
    "print(actual)\n"
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _report_progress(callback: Callable[[str], None] | None, message: str) -> None:
    normalized = str(message or "").strip()
    if callback is None or not normalized:
        return
    try:
        callback(normalized)
    except Exception:  # noqa: BLE001
        return


@dataclass(frozen=True, slots=True)
class ManagedRuntimePaths:
    runtime_root: Path
    venv_dir: Path
    python_executable: Path
    runtime_bundle_dir: Path
    runtime_manifest_path: Path


@dataclass(frozen=True, slots=True)
class ManagedRuntimeStatus:
    runtime_root: str = ""
    python_executable: str = ""
    runtime_bundle_dir: str = ""
    runtime_manifest_path: str = ""
    wheel_path: str = ""
    exists: bool = False
    verified: bool = False
    error: str = ""


@dataclass(frozen=True, slots=True)
class ManagedRuntimePackageSpec:
    package_id: str
    distribution: str
    version: str
    install_target: Path
    extras: tuple[str, ...] = ()
    console_scripts: tuple[str, ...] = ()
    source_kind: str = "wheel"
    editable: bool = False


@dataclass(frozen=True, slots=True)
class ManagedRuntimeInstallResult:
    success: bool = False
    python_executable: str = ""
    bootstrap_python: str = ""
    status: ManagedRuntimeStatus = ManagedRuntimeStatus()
    steps: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class SystemPython:
    command: tuple[str, ...]
    executable: str


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _default_runtime_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / RUNTIME_BUNDLE_DIRNAME
    return Path(__file__).resolve().parents[2] / RUNTIME_BUNDLE_DIRNAME


def resolve_managed_runtime_paths(
    *,
    runtime_name: str = DEFAULT_MANAGED_RUNTIME_NAME,
    data_dir: str | Path | None = None,
    runtime_bundle_dir: str | Path | None = None,
) -> ManagedRuntimePaths:
    normalized_name = str(runtime_name or DEFAULT_MANAGED_RUNTIME_NAME).strip()
    if not normalized_name:
        normalized_name = DEFAULT_MANAGED_RUNTIME_NAME
    base_data_dir = Path(data_dir) if data_dir is not None else user_data_dir()
    runtime_root = base_data_dir / MANAGED_RUNTIME_DIRNAME / normalized_name
    bundle_dir = (
        Path(runtime_bundle_dir)
        if runtime_bundle_dir is not None
        else _default_runtime_bundle_dir()
    )
    return ManagedRuntimePaths(
        runtime_root=runtime_root,
        venv_dir=runtime_root,
        python_executable=_venv_python_path(runtime_root),
        runtime_bundle_dir=bundle_dir,
        runtime_manifest_path=bundle_dir / RUNTIME_MANIFEST_FILENAME,
    )


def resolve_addon_runtime_paths(
    *,
    runtime_name: str = DEFAULT_MANAGED_RUNTIME_NAME,
    data_dir: str | Path | None = None,
    runtime_bundle_dir: str | Path | None = None,
) -> ManagedRuntimePaths:
    """Use COREX's active Python for source add-ons and the managed venv when frozen."""

    inherited_python = os.environ.get(ADDON_RUNTIME_PYTHON_ENV, "").strip()
    if inherited_python:
        python_executable = Path(inherited_python).resolve()
        runtime_root = python_executable.parent.parent
        bundle_dir = (
            Path(runtime_bundle_dir)
            if runtime_bundle_dir is not None
            else _default_runtime_bundle_dir()
        )
        return ManagedRuntimePaths(
            runtime_root=runtime_root,
            venv_dir=runtime_root,
            python_executable=python_executable,
            runtime_bundle_dir=bundle_dir,
            runtime_manifest_path=bundle_dir / RUNTIME_MANIFEST_FILENAME,
        )
    if getattr(sys, "frozen", False):
        return resolve_managed_runtime_paths(
            runtime_name=runtime_name,
            data_dir=data_dir,
            runtime_bundle_dir=runtime_bundle_dir,
        )
    bundle_dir = (
        Path(runtime_bundle_dir)
        if runtime_bundle_dir is not None
        else _default_runtime_bundle_dir()
    )
    runtime_root = Path(sys.prefix).resolve()
    return ManagedRuntimePaths(
        runtime_root=runtime_root,
        venv_dir=runtime_root,
        python_executable=Path(sys.executable).resolve(),
        runtime_bundle_dir=bundle_dir,
        runtime_manifest_path=bundle_dir / RUNTIME_MANIFEST_FILENAME,
    )


def _run_command(
    command: Sequence[str | Path],
    *,
    runner: CommandRunner | None,
    timeout: float | None,
    progress_callback: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    normalized = [str(part) for part in command]
    if runner is not None:
        result = runner(
            normalized,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if progress_callback is not None:
            for line in (result.stdout or result.stderr or "").splitlines():
                _report_progress(progress_callback, line)
        return result
    if progress_callback is None:
        return subprocess.run(
            normalized,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    process = subprocess.Popen(
        normalized,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output: list[str] = []

    def read_output() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            output.append(line)
            _report_progress(progress_callback, line)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        reader.join(timeout=1.0)
        raise
    reader.join()
    return subprocess.CompletedProcess(
        normalized,
        returncode,
        stdout="".join(output),
        stderr="",
    )


def _format_command_failure(command: Sequence[str | Path], result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "").strip()
    suffix = f": {output[-1200:]}" if output else ""
    return f"Command failed with exit code {result.returncode}: {' '.join(str(part) for part in command)}{suffix}"


def _successful_system_python_from_command(
    command: Sequence[str],
    *,
    runner: CommandRunner | None,
    timeout: float,
) -> SystemPython | None:
    probe = (
        "import sys\n"
        "if sys.version_info < (3, 10):\n"
        "    raise SystemExit('Python 3.10 or newer is required')\n"
        "print(sys.executable)\n"
    )
    full_command = [*command, "-c", probe]
    try:
        result = _run_command(full_command, runner=runner, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    executable = (result.stdout or "").strip().splitlines()[0:1]
    if not executable:
        return None
    return SystemPython(command=tuple(command), executable=executable[0])


def detect_system_python(
    *,
    runner: CommandRunner | None = None,
    timeout: float = 10.0,
) -> SystemPython | None:
    for command in (("py", "-3.10"), ("py", "-3"), ("python",)):
        detected = _successful_system_python_from_command(
            command,
            runner=runner,
            timeout=timeout,
        )
        if detected is not None:
            return detected
    return None


def _load_runtime_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"COREX runtime manifest was not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"COREX runtime manifest is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"COREX runtime manifest must be a JSON object: {path}")
    return payload


def _manifest_string_list(value: Any, *, field: str, package_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(
            f"Runtime package '{package_id}' field '{field}' must be a JSON array."
        )
    normalized = tuple(str(item).strip() for item in value if str(item).strip())
    if len(normalized) != len(value):
        raise RuntimeError(
            f"Runtime package '{package_id}' field '{field}' contains an empty value."
        )
    return normalized


def _resolve_bundled_wheel(paths: ManagedRuntimePaths, package_id: str, value: Any) -> Path:
    wheel_name = str(value or "").strip()
    wheel_path = Path(wheel_name)
    if not wheel_name or wheel_path.is_absolute() or wheel_path.name != wheel_name:
        raise RuntimeError(
            f"Runtime package '{package_id}' wheel must be a file name inside "
            f"{paths.runtime_bundle_dir}."
        )
    bundle_dir = paths.runtime_bundle_dir.resolve()
    candidate = (bundle_dir / wheel_path).resolve()
    if candidate.parent != bundle_dir:
        raise RuntimeError(
            f"Runtime package '{package_id}' wheel escapes {paths.runtime_bundle_dir}."
        )
    if not candidate.is_file():
        raise RuntimeError(f"Runtime package '{package_id}' wheel was not found: {candidate}")
    return candidate


def _resolve_source_target(
    paths: ManagedRuntimePaths,
    package_id: str,
    value: Any,
    *,
    allow_source_targets: bool,
) -> Path:
    if not allow_source_targets:
        raise RuntimeError(
            f"Runtime package '{package_id}' cannot use a source target in a bundled build."
        )
    source_value = str(value or "").strip()
    if not source_value:
        raise RuntimeError(f"Runtime package '{package_id}' source target is empty.")
    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = paths.runtime_bundle_dir / source_path
    source_path = source_path.resolve()
    if not source_path.is_dir():
        raise RuntimeError(
            f"Runtime package '{package_id}' source directory was not found: {source_path}"
        )
    return source_path


def _runtime_packages_from_manifest(
    paths: ManagedRuntimePaths,
    package_ids: Sequence[str] = (),
    *,
    allow_source_targets: bool | None = None,
) -> tuple[ManagedRuntimePackageSpec, ...]:
    manifest = _load_runtime_manifest(paths.runtime_manifest_path)
    if manifest.get("schema_version") != RUNTIME_MANIFEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"COREX runtime manifest schema_version must be {RUNTIME_MANIFEST_SCHEMA_VERSION}: "
            f"{paths.runtime_manifest_path}"
        )
    packages = manifest.get("packages")
    if not isinstance(packages, Mapping) or not packages:
        raise RuntimeError("COREX runtime manifest field 'packages' must be a JSON object.")
    if COREX_RUNTIME_PACKAGE_ID not in packages:
        raise RuntimeError("COREX runtime manifest does not define package 'corex'.")

    requested_ids = tuple(dict.fromkeys(str(item).strip() for item in package_ids))
    if any(not package_id for package_id in requested_ids):
        raise RuntimeError("Managed runtime package ids must not be empty.")
    unknown = [package_id for package_id in requested_ids if package_id not in packages]
    if unknown:
        raise RuntimeError(f"Unknown managed runtime package id: {unknown[0]}")

    selected_ids: list[str] = [COREX_RUNTIME_PACKAGE_ID]
    for package_id, payload in packages.items():
        if not isinstance(package_id, str) or not package_id.strip():
            raise RuntimeError("COREX runtime manifest contains an invalid package id.")
        if not isinstance(payload, Mapping):
            raise RuntimeError(f"Runtime package '{package_id}' must be a JSON object.")
        required = payload.get("required", False)
        if not isinstance(required, bool):
            raise RuntimeError(f"Runtime package '{package_id}' field 'required' must be boolean.")
        if required and package_id not in selected_ids:
            selected_ids.append(package_id)
    for package_id in requested_ids:
        if package_id not in selected_ids:
            selected_ids.append(package_id)

    source_targets_allowed = (
        not bool(getattr(sys, "frozen", False))
        if allow_source_targets is None
        else allow_source_targets
    )
    specs: list[ManagedRuntimePackageSpec] = []
    for package_id in selected_ids:
        payload = packages[package_id]
        distribution = str(payload.get("distribution", "") or "").strip()
        if not distribution:
            raise RuntimeError(
                f"Runtime package '{package_id}' field 'distribution' is required."
            )
        version = str(payload.get("version", "") or "").strip()
        if not version:
            raise RuntimeError(f"Runtime package '{package_id}' field 'version' is required.")
        has_wheel = "wheel" in payload
        has_source = "source" in payload
        if has_wheel == has_source:
            raise RuntimeError(
                f"Runtime package '{package_id}' must define exactly one of 'wheel' or 'source'."
            )
        if has_wheel:
            install_target = _resolve_bundled_wheel(paths, package_id, payload["wheel"])
            source_kind = "wheel"
        else:
            install_target = _resolve_source_target(
                paths,
                package_id,
                payload["source"],
                allow_source_targets=source_targets_allowed,
            )
            source_kind = "source"
        extras = _manifest_string_list(
            payload.get("extras", []), field="extras", package_id=package_id
        )
        console_scripts = _manifest_string_list(
            payload.get("console_scripts", []),
            field="console_scripts",
            package_id=package_id,
        )
        if any(Path(name).name != name for name in console_scripts):
            raise RuntimeError(
                f"Runtime package '{package_id}' contains an invalid console script name."
            )
        editable = payload.get("editable", False)
        if not isinstance(editable, bool):
            raise RuntimeError(
                f"Runtime package '{package_id}' field 'editable' must be boolean."
            )
        if editable and source_kind != "source":
            raise RuntimeError(
                f"Runtime package '{package_id}' can only be editable when using a source target."
            )
        specs.append(
            ManagedRuntimePackageSpec(
                package_id=package_id,
                distribution=distribution,
                version=version,
                install_target=install_target,
                extras=extras,
                console_scripts=console_scripts,
                source_kind=source_kind,
                editable=editable,
            )
        )
    return tuple(specs)


def _runtime_install_target(package: ManagedRuntimePackageSpec) -> str:
    if not package.extras:
        return str(package.install_target)
    return f"{package.install_target}[{','.join(package.extras)}]"


def _runtime_install_command(
    python_executable: Path,
    package: ManagedRuntimePackageSpec,
    *,
    no_deps: bool = False,
) -> list[str | Path]:
    command: list[str | Path] = [
        python_executable,
        "-m",
        "pip",
        "install",
        "--progress-bar",
        "off",
        "--upgrade",
    ]
    if no_deps:
        command.append("--no-deps")
    if package.editable:
        command.append("--editable")
    command.append(_runtime_install_target(package))
    return command


def resolve_managed_console_script(
    script_name: str,
    *,
    paths: ManagedRuntimePaths | None = None,
    python_executable: str | Path | None = None,
) -> Path:
    normalized_name = str(script_name or "").strip()
    if (
        not normalized_name
        or normalized_name in {".", ".."}
        or Path(normalized_name).name != normalized_name
    ):
        raise ValueError("Managed console script name must be a file name.")
    runtime_paths = paths or resolve_managed_runtime_paths()
    candidate_python = (
        Path(python_executable)
        if python_executable is not None
        else runtime_paths.python_executable
    )
    executable_name = normalized_name
    if os.name == "nt" and not executable_name.lower().endswith(".exe"):
        executable_name += ".exe"
    elif os.name != "nt" and executable_name.lower().endswith(".exe"):
        executable_name = executable_name[:-4]
    return candidate_python.parent / executable_name


def verify_managed_runtime(
    python_executable: str | Path | None = None,
    *,
    paths: ManagedRuntimePaths | None = None,
    runner: CommandRunner | None = None,
    timeout: float = 10.0,
    package_ids: Sequence[str] = (),
) -> ManagedRuntimeStatus:
    runtime_paths = paths or resolve_managed_runtime_paths()
    candidate = Path(python_executable) if python_executable is not None else runtime_paths.python_executable
    try:
        packages = _runtime_packages_from_manifest(runtime_paths, package_ids)
    except RuntimeError as exc:
        return ManagedRuntimeStatus(
            runtime_root=str(runtime_paths.runtime_root),
            python_executable=str(candidate),
            runtime_bundle_dir=str(runtime_paths.runtime_bundle_dir),
            runtime_manifest_path=str(runtime_paths.runtime_manifest_path),
            exists=candidate.exists(),
            verified=False,
            error=str(exc),
        )

    base_status = {
        "runtime_root": str(runtime_paths.runtime_root),
        "python_executable": str(candidate),
        "runtime_bundle_dir": str(runtime_paths.runtime_bundle_dir),
        "runtime_manifest_path": str(runtime_paths.runtime_manifest_path),
        "wheel_path": str(packages[0].install_target),
        "exists": candidate.exists(),
    }
    if not candidate.exists():
        return ManagedRuntimeStatus(
            **base_status,
            verified=False,
            error=f"Managed COREX runtime Python was not found: {candidate}",
        )
    try:
        result = _run_command(
            [candidate, "-c", RUNTIME_IMPORT_CHECK],
            runner=runner,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ManagedRuntimeStatus(
            **base_status,
            verified=False,
            error="Managed COREX runtime verification timed out.",
        )
    except OSError as exc:
        return ManagedRuntimeStatus(
            **base_status,
            verified=False,
            error=f"Failed to launch managed COREX runtime Python: {exc}",
        )
    if result.returncode != 0:
        return ManagedRuntimeStatus(
            **base_status,
            verified=False,
            error=_format_command_failure([candidate, "-c", RUNTIME_IMPORT_CHECK], result),
        )
    for package in packages:
        command = [candidate, "-c", RUNTIME_VERSION_CHECK, package.distribution, package.version]
        try:
            result = _run_command(command, runner=runner, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ManagedRuntimeStatus(
                **base_status,
                verified=False,
                error=f"Managed runtime package verification timed out: {package.package_id}",
            )
        except OSError as exc:
            return ManagedRuntimeStatus(
                **base_status,
                verified=False,
                error=f"Failed to verify managed runtime package '{package.package_id}': {exc}",
            )
        if result.returncode != 0:
            return ManagedRuntimeStatus(
                **base_status,
                verified=False,
                error=_format_command_failure(command, result),
            )
        for script_name in package.console_scripts:
            script_path = resolve_managed_console_script(
                script_name,
                paths=runtime_paths,
                python_executable=candidate,
            )
            if not script_path.is_file():
                return ManagedRuntimeStatus(
                    **base_status,
                    verified=False,
                    error=(
                        f"Managed runtime console script '{script_name}' was not found: "
                        f"{script_path}"
                    ),
                )
    return ManagedRuntimeStatus(**base_status, verified=True)


def _failed_install_result(
    message: str,
    *,
    paths: ManagedRuntimePaths,
    steps: Sequence[str],
    bootstrap_python: str = "",
) -> ManagedRuntimeInstallResult:
    status = ManagedRuntimeStatus(
        runtime_root=str(paths.runtime_root),
        python_executable=str(paths.python_executable),
        runtime_bundle_dir=str(paths.runtime_bundle_dir),
        runtime_manifest_path=str(paths.runtime_manifest_path),
        exists=paths.python_executable.exists(),
        verified=False,
        error=message,
    )
    return ManagedRuntimeInstallResult(
        success=False,
        python_executable="",
        bootstrap_python=bootstrap_python,
        status=status,
        steps=tuple(steps),
        error=message,
    )


def prepare_managed_runtime(
    *,
    runtime_name: str = DEFAULT_MANAGED_RUNTIME_NAME,
    data_dir: str | Path | None = None,
    runtime_bundle_dir: str | Path | None = None,
    runner: CommandRunner | None = None,
    timeout: float | None = None,
    package_ids: Sequence[str] = (),
    progress_callback: Callable[[str], None] | None = None,
) -> ManagedRuntimeInstallResult:
    paths = resolve_managed_runtime_paths(
        runtime_name=runtime_name,
        data_dir=data_dir,
        runtime_bundle_dir=runtime_bundle_dir,
    )
    steps: list[str] = []

    try:
        packages = _runtime_packages_from_manifest(paths, package_ids)
    except RuntimeError as exc:
        return _failed_install_result(str(exc), paths=paths, steps=steps)

    _report_progress(progress_callback, "Finding Python 3.10 or newer...")
    system_python = detect_system_python(runner=runner)
    if system_python is None:
        return _failed_install_result(
            "Could not find Python 3.10 or newer with the Windows py launcher or python on PATH.",
            paths=paths,
            steps=steps,
        )

    bootstrap_python = system_python.executable
    try:
        paths.venv_dir.parent.mkdir(parents=True, exist_ok=True)
        create_venv_command = [*system_python.command, "-m", "venv", paths.venv_dir]
        steps.append("create_venv")
        _report_progress(progress_callback, "Creating the managed COREX runtime...")
        create_venv = _run_command(
            create_venv_command,
            runner=runner,
            timeout=timeout,
            progress_callback=progress_callback,
        )
        if create_venv.returncode != 0:
            return _failed_install_result(
                _format_command_failure(create_venv_command, create_venv),
                paths=paths,
                steps=steps,
                bootstrap_python=bootstrap_python,
            )

        if not paths.python_executable.exists():
            return _failed_install_result(
                f"Managed COREX runtime Python was not created: {paths.python_executable}",
                paths=paths,
                steps=steps,
                bootstrap_python=bootstrap_python,
            )

        pip_upgrade_command = [
            paths.python_executable,
            "-m",
            "pip",
            "install",
            "--progress-bar",
            "off",
            "--upgrade",
            "pip",
        ]
        steps.append("upgrade_pip")
        _report_progress(progress_callback, "Upgrading pip...")
        pip_upgrade = _run_command(
            pip_upgrade_command,
            runner=runner,
            timeout=timeout,
            progress_callback=progress_callback,
        )
        if pip_upgrade.returncode != 0:
            return _failed_install_result(
                _format_command_failure(pip_upgrade_command, pip_upgrade),
                paths=paths,
                steps=steps,
                bootstrap_python=bootstrap_python,
            )

        for package in packages:
            install_command = _runtime_install_command(
                paths.python_executable,
                package,
                no_deps=package.package_id == MARS_RUNTIME_PACKAGE_ID,
            )
            step = (
                "install_corex_runtime"
                if package.package_id == COREX_RUNTIME_PACKAGE_ID
                else f"install_runtime_package:{package.package_id}"
            )
            steps.append(step)
            package_name = (
                "COREX and its dependencies"
                if package.package_id == COREX_RUNTIME_PACKAGE_ID
                else package.distribution
            )
            _report_progress(progress_callback, f"Installing {package_name}...")
            install_result = _run_command(
                install_command,
                runner=runner,
                timeout=timeout,
                progress_callback=progress_callback,
            )
            if install_result.returncode != 0:
                return _failed_install_result(
                    _format_command_failure(install_command, install_result),
                    paths=paths,
                    steps=steps,
                    bootstrap_python=bootstrap_python,
                )

        steps.append("verify_runtime")
        _report_progress(progress_callback, "Verifying the managed runtime...")
        status = verify_managed_runtime(
            paths.python_executable,
            paths=paths,
            runner=runner,
            package_ids=package_ids,
        )
        if not status.verified:
            return ManagedRuntimeInstallResult(
                success=False,
                python_executable="",
                bootstrap_python=bootstrap_python,
                status=status,
                steps=tuple(steps),
                error=status.error,
            )
        return ManagedRuntimeInstallResult(
            success=True,
            python_executable=str(paths.python_executable),
            bootstrap_python=bootstrap_python,
            status=status,
            steps=tuple(steps),
            error="",
        )
    except subprocess.TimeoutExpired:
        return _failed_install_result(
            "Preparing the managed COREX runtime timed out.",
            paths=paths,
            steps=steps,
            bootstrap_python=bootstrap_python,
        )
    except OSError as exc:
        return _failed_install_result(
            f"Preparing the managed COREX runtime failed: {exc}",
            paths=paths,
            steps=steps,
            bootstrap_python=bootstrap_python,
        )


def prepare_addon_runtime(
    *,
    runtime_name: str = DEFAULT_MANAGED_RUNTIME_NAME,
    data_dir: str | Path | None = None,
    runtime_bundle_dir: str | Path | None = None,
    runner: CommandRunner | None = None,
    timeout: float | None = None,
    package_ids: Sequence[str] = (),
    progress_callback: Callable[[str], None] | None = None,
) -> ManagedRuntimeInstallResult:
    """Install add-ons into the selected source or frozen COREX Python environment."""

    if getattr(sys, "frozen", False):
        return prepare_managed_runtime(
            runtime_name=runtime_name,
            data_dir=data_dir,
            runtime_bundle_dir=runtime_bundle_dir,
            runner=runner,
            timeout=timeout,
            package_ids=package_ids,
            progress_callback=progress_callback,
        )

    paths = resolve_addon_runtime_paths(
        runtime_name=runtime_name,
        data_dir=data_dir,
        runtime_bundle_dir=runtime_bundle_dir,
    )
    steps: list[str] = []
    bootstrap_python = str(paths.python_executable)
    try:
        packages = tuple(
            package
            for package in _runtime_packages_from_manifest(paths, package_ids)
            if package.package_id != COREX_RUNTIME_PACKAGE_ID
        )
    except RuntimeError as exc:
        return _failed_install_result(
            str(exc),
            paths=paths,
            steps=steps,
            bootstrap_python=bootstrap_python,
        )

    try:
        _report_progress(
            progress_callback,
            f"Using COREX Python environment: {paths.python_executable}",
        )
        for package in packages:
            install_command = _runtime_install_command(
                paths.python_executable,
                package,
                no_deps=package.package_id == MARS_RUNTIME_PACKAGE_ID,
            )
            steps.append(f"install_runtime_package:{package.package_id}")
            _report_progress(
                progress_callback,
                f"Installing {package.distribution} into {paths.python_executable}...",
            )
            install_result = _run_command(
                install_command,
                runner=runner,
                timeout=timeout,
                progress_callback=progress_callback,
            )
            if install_result.returncode != 0:
                return _failed_install_result(
                    _format_command_failure(install_command, install_result),
                    paths=paths,
                    steps=steps,
                    bootstrap_python=bootstrap_python,
                )

        steps.append("verify_runtime")
        _report_progress(progress_callback, "Verifying the COREX Python environment...")
        status = verify_managed_runtime(
            paths.python_executable,
            paths=paths,
            runner=runner,
            package_ids=package_ids,
        )
        if not status.verified:
            return ManagedRuntimeInstallResult(
                success=False,
                bootstrap_python=bootstrap_python,
                status=status,
                steps=tuple(steps),
                error=status.error,
            )
        return ManagedRuntimeInstallResult(
            success=True,
            python_executable=str(paths.python_executable),
            bootstrap_python=bootstrap_python,
            status=status,
            steps=tuple(steps),
        )
    except subprocess.TimeoutExpired:
        return _failed_install_result(
            "Preparing the COREX Python environment timed out.",
            paths=paths,
            steps=steps,
            bootstrap_python=bootstrap_python,
        )
    except OSError as exc:
        return _failed_install_result(
            f"Preparing the COREX Python environment failed: {exc}",
            paths=paths,
            steps=steps,
            bootstrap_python=bootstrap_python,
        )


__all__ = [
    "ADDON_RUNTIME_PYTHON_ENV",
    "DEFAULT_MANAGED_RUNTIME_NAME",
    "COREX_RUNTIME_PACKAGE_ID",
    "MANAGED_RUNTIME_DIRNAME",
    "ManagedRuntimeInstallResult",
    "ManagedRuntimePaths",
    "ManagedRuntimePackageSpec",
    "ManagedRuntimeStatus",
    "MARS_RUNTIME_PACKAGE_ID",
    "RUNTIME_BUNDLE_DIRNAME",
    "RUNTIME_IMPORT_CHECK",
    "RUNTIME_INSTALL_EXTRAS",
    "RUNTIME_MANIFEST_FILENAME",
    "RUNTIME_MANIFEST_SCHEMA_VERSION",
    "RUNTIME_PACKAGE_NAME",
    "RUNTIME_VERSION_CHECK",
    "SystemPython",
    "detect_system_python",
    "prepare_addon_runtime",
    "prepare_managed_runtime",
    "resolve_addon_runtime_paths",
    "resolve_managed_runtime_paths",
    "resolve_managed_console_script",
    "verify_managed_runtime",
]
