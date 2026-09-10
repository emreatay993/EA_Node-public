from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest import mock

from ea_node_editor.execution.managed_runtime import (
    ADDON_RUNTIME_PYTHON_ENV,
    RUNTIME_IMPORT_CHECK,
    RUNTIME_VERSION_CHECK,
    _run_command,
    detect_system_python,
    prepare_addon_runtime,
    prepare_managed_runtime,
    resolve_addon_runtime_paths,
    resolve_managed_console_script,
    resolve_managed_runtime_paths,
    verify_managed_runtime,
)


def _completed(command: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def _venv_python_for_test(prefix: Path) -> Path:
    return prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _write_manifest(bundle_dir: Path, packages: dict[str, dict[str, object]]) -> None:
    (bundle_dir / "runtime_manifest.json").write_text(
        json.dumps({"schema_version": 2, "packages": packages}),
        encoding="utf-8",
    )


def _package(
    distribution: str,
    version: str,
    *,
    wheel: str | None = None,
    source: str | None = None,
    extras: tuple[str, ...] = (),
    console_scripts: tuple[str, ...] = (),
    required: bool = False,
    editable: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "distribution": distribution,
        "version": version,
        "extras": list(extras),
        "console_scripts": list(console_scripts),
        "required": required,
        "editable": editable,
    }
    if wheel is not None:
        payload["wheel"] = wheel
    if source is not None:
        payload["source"] = source
    return payload


class ManagedRuntimeTests(unittest.TestCase):
    def test_runtime_import_check_includes_public_sdk_and_worker_entrypoint(self) -> None:
        self.assertEqual(
            RUNTIME_IMPORT_CHECK,
            "import corex\nimport ea_node_editor.execution.stdio_worker",
        )

    def test_resolve_managed_runtime_paths_uses_app_data_runtime_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = resolve_managed_runtime_paths(data_dir=temp_dir)

            self.assertEqual(paths.runtime_root, Path(temp_dir) / "runtimes" / "default")
            self.assertEqual(paths.venv_dir, paths.runtime_root)
            if os.name == "nt":
                self.assertEqual(
                    paths.python_executable,
                    paths.runtime_root / "Scripts" / "python.exe",
                )
            else:
                self.assertEqual(
                    paths.python_executable,
                    paths.runtime_root / "bin" / "python",
                )

    def test_resolve_addon_runtime_paths_uses_active_python_for_source_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "corex-venv"
            python = _venv_python_for_test(prefix)
            bundle_dir = Path(temp_dir) / "bundle"
            with (
                mock.patch.object(sys, "frozen", False, create=True),
                mock.patch.object(sys, "prefix", str(prefix)),
                mock.patch.object(sys, "executable", str(python)),
            ):
                source_paths = resolve_addon_runtime_paths(
                    data_dir=Path(temp_dir) / "ignored-app-data",
                    runtime_bundle_dir=bundle_dir,
                )

            self.assertEqual(source_paths.runtime_root, prefix.resolve())
            self.assertEqual(source_paths.python_executable, python.resolve())
            self.assertEqual(source_paths.runtime_bundle_dir, bundle_dir)

            with mock.patch.object(sys, "frozen", True, create=True):
                frozen_paths = resolve_addon_runtime_paths(
                    data_dir=Path(temp_dir) / "app-data",
                    runtime_bundle_dir=bundle_dir,
                )
            self.assertEqual(
                frozen_paths.runtime_root,
                Path(temp_dir) / "app-data" / "runtimes" / "default",
            )

    def test_prepare_addon_runtime_keeps_frozen_managed_environment_flow(self) -> None:
        expected = object()
        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch(
                "ea_node_editor.execution.managed_runtime.prepare_managed_runtime",
                return_value=expected,
            ) as prepare_managed,
        ):
            result = prepare_addon_runtime(
                runtime_name="frozen",
                data_dir="app-data",
                runtime_bundle_dir="bundle",
                package_ids=("mars",),
            )

        self.assertIs(result, expected)
        prepare_managed.assert_called_once_with(
            runtime_name="frozen",
            data_dir="app-data",
            runtime_bundle_dir="bundle",
            runner=None,
            timeout=None,
            package_ids=("mars",),
            progress_callback=None,
        )

    def test_resolve_addon_runtime_paths_honors_desktop_path_in_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "desktop-addon-venv"
            python = _venv_python_for_test(prefix)
            with (
                mock.patch.dict(os.environ, {ADDON_RUNTIME_PYTHON_ENV: str(python)}),
                mock.patch.object(sys, "frozen", False, create=True),
                mock.patch.object(sys, "prefix", str(Path(temp_dir) / "worker-venv")),
                mock.patch.object(
                    sys,
                    "executable",
                    str(_venv_python_for_test(Path(temp_dir) / "worker-venv")),
                ),
            ):
                paths = resolve_addon_runtime_paths()

            self.assertEqual(paths.runtime_root, prefix.resolve())
            self.assertEqual(paths.python_executable, python.resolve())

    def test_detect_system_python_tries_py310_py3_then_python(self) -> None:
        calls: list[list[str]] = []

        def runner(command: list[str], **_kwargs):
            calls.append(command)
            if command[:2] == ["py", "-3.10"]:
                return _completed(command, returncode=1, stderr="missing")
            if command[:2] == ["py", "-3"]:
                return _completed(command, stdout=f"{sys.executable}\n")
            self.fail("python fallback should not be called after py -3 succeeds")

        detected = detect_system_python(runner=runner)

        self.assertIsNotNone(detected)
        if detected is None:
            self.fail("expected system Python detection")
        self.assertEqual(detected.command, ("py", "-3"))
        self.assertEqual(detected.executable, sys.executable)
        self.assertEqual(calls[0][:2], ["py", "-3.10"])
        self.assertEqual(calls[1][:2], ["py", "-3"])

    def test_run_command_streams_output_before_process_finishes(self) -> None:
        first_line_seen = Event()
        progress: list[str] = []
        results: list[subprocess.CompletedProcess[str]] = []
        errors: list[Exception] = []

        def report(line: str) -> None:
            progress.append(line)
            if line == "first":
                first_line_seen.set()

        def run() -> None:
            try:
                results.append(
                    _run_command(
                        [
                            sys.executable,
                            "-c",
                            (
                                "import time; print('first', flush=True); "
                                "time.sleep(0.5); print('second', flush=True)"
                            ),
                        ],
                        runner=None,
                        timeout=5.0,
                        progress_callback=report,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread = Thread(target=run)
        thread.start()

        self.assertTrue(first_line_seen.wait(3.0))
        self.assertTrue(thread.is_alive())
        thread.join(5.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].returncode, 0)
        self.assertEqual(progress, ["first", "second"])

    def test_prepare_managed_runtime_builds_venv_installs_all_extra_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            bundle_dir = Path(temp_dir) / "bundle"
            bundle_dir.mkdir()
            wheel_path = bundle_dir / "corex_node_editor-0.1.0-py3-none-any.whl"
            wheel_path.write_text("fake wheel", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        wheel=wheel_path.name,
                        extras=("all",),
                        required=True,
                    ),
                    "mars": _package(
                        "mars-modal-response-solver",
                        "1.0.0",
                        wheel="not-required-for-corex-only.whl",
                    ),
                },
            )
            paths = resolve_managed_runtime_paths(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
            )
            calls: list[list[str]] = []
            command_timeouts: list[tuple[list[str], float | None]] = []
            progress: list[str] = []

            def runner(command: list[str], **kwargs):
                calls.append(command)
                command_timeouts.append((command, kwargs["timeout"]))
                if command[:2] == ["py", "-3.10"] and "-c" in command:
                    return _completed(command, stdout=f"{sys.executable}\n")
                if command[:2] == ["py", "-3.10"] and command[-3:-1] == ["-m", "venv"]:
                    paths.python_executable.parent.mkdir(parents=True, exist_ok=True)
                    paths.python_executable.write_text("", encoding="utf-8")
                    return _completed(command)
                if command[:4] == [str(paths.python_executable), "-m", "pip", "install"]:
                    return _completed(command, stdout="Downloading corex...\n")
                if command == [str(paths.python_executable), "-c", RUNTIME_IMPORT_CHECK]:
                    return _completed(command)
                if command[:3] == [str(paths.python_executable), "-c", RUNTIME_VERSION_CHECK]:
                    return _completed(command, stdout="0.1.0\n")
                self.fail(f"unexpected command: {command!r}")

            result = prepare_managed_runtime(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
                runner=runner,
                progress_callback=progress.append,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.python_executable, str(paths.python_executable))
            self.assertEqual(
                result.steps,
                ("create_venv", "upgrade_pip", "install_corex_runtime", "verify_runtime"),
            )
            self.assertIn(
                f"{wheel_path}[all]",
                calls[-3],
            )
            setup_timeouts = [
                timeout
                for command, timeout in command_timeouts
                if "venv" in command or command[:4] == [
                    str(paths.python_executable),
                    "-m",
                    "pip",
                    "install",
                ]
            ]
            self.assertTrue(setup_timeouts)
            self.assertTrue(all(timeout is None for timeout in setup_timeouts))
            self.assertIn("Installing COREX and its dependencies...", progress)
            self.assertIn("Downloading corex...", progress)

    def test_prepare_managed_runtime_installs_requested_local_package_without_pypi_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            bundle_dir = Path(temp_dir) / "bundle"
            bundle_dir.mkdir()
            corex_wheel = bundle_dir / "corex_node_editor-0.1.0-py3-none-any.whl"
            mars_wheel = bundle_dir / "mars_solver-1.2.3-py3-none-any.whl"
            corex_wheel.write_text("fake corex wheel", encoding="utf-8")
            mars_wheel.write_text("fake mars wheel", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        wheel=corex_wheel.name,
                        extras=("all",),
                        required=True,
                    ),
                    "mars": _package(
                        "mars-solver",
                        "1.2.3",
                        wheel=mars_wheel.name,
                        console_scripts=("MARSBatch.exe",),
                    ),
                },
            )
            paths = resolve_managed_runtime_paths(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
            )
            calls: list[list[str]] = []

            def runner(command: list[str], **_kwargs):
                calls.append(command)
                if command[:2] == ["py", "-3.10"] and "-c" in command:
                    return _completed(command, stdout=f"{sys.executable}\n")
                if command[:2] == ["py", "-3.10"] and command[-3:-1] == ["-m", "venv"]:
                    paths.python_executable.parent.mkdir(parents=True, exist_ok=True)
                    paths.python_executable.write_text("", encoding="utf-8")
                    return _completed(command)
                if command[:4] == [str(paths.python_executable), "-m", "pip", "install"]:
                    if str(mars_wheel) in command[-1]:
                        resolve_managed_console_script(
                            "MARSBatch.exe", paths=paths
                        ).write_text("", encoding="utf-8")
                    return _completed(command)
                if command == [str(paths.python_executable), "-c", RUNTIME_IMPORT_CHECK]:
                    return _completed(command)
                if command[:3] == [str(paths.python_executable), "-c", RUNTIME_VERSION_CHECK]:
                    return _completed(command, stdout=f"{command[-1]}\n")
                self.fail(f"unexpected command: {command!r}")

            result = prepare_managed_runtime(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
                runner=runner,
                package_ids=("mars",),
            )

            self.assertTrue(result.success, result.error)
            self.assertEqual(
                result.steps,
                (
                    "create_venv",
                    "upgrade_pip",
                    "install_corex_runtime",
                    "install_runtime_package:mars",
                    "verify_runtime",
                ),
            )
            install_targets = [
                command[-1]
                for command in calls
                if command[:4] == [str(paths.python_executable), "-m", "pip", "install"]
                and "--upgrade" in command
                and command[-1] != "pip"
            ]
            self.assertIn(f"{corex_wheel}[all]", install_targets)
            self.assertIn(str(mars_wheel), install_targets)
            self.assertNotIn("mars-solver", install_targets)
            install_commands = [
                command
                for command in calls
                if command[:4] == [str(paths.python_executable), "-m", "pip", "install"]
                and command[-1] != "pip"
            ]
            corex_install = next(command for command in install_commands if str(corex_wheel) in command[-1])
            mars_install = next(command for command in install_commands if command[-1] == str(mars_wheel))
            self.assertNotIn("--no-deps", corex_install)
            self.assertIn("--no-deps", mars_install)

    def test_prepare_addon_runtime_installs_only_editable_mars_without_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_dir = root / "bundle"
            corex_source = root / "corex-source"
            mars_source = root / "mars-source"
            prefix = root / "corex-venv"
            python = _venv_python_for_test(prefix)
            ignored_data = root / "ignored-app-data"
            bundle_dir.mkdir()
            corex_source.mkdir()
            mars_source.mkdir()
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        source=str(corex_source),
                        extras=("all",),
                        required=True,
                        editable=True,
                    ),
                    "mars": _package(
                        "mars-modal-response-solver",
                        "1.0.0",
                        source=str(mars_source),
                        console_scripts=("MARSBatch",),
                        editable=True,
                    ),
                },
            )
            calls: list[list[str]] = []
            progress: list[str] = []

            def runner(command: list[str], **_kwargs):
                calls.append(command)
                if command[:4] == [str(python.resolve()), "-m", "pip", "install"]:
                    resolve_managed_console_script(
                        "MARSBatch",
                        python_executable=python.resolve(),
                    ).write_text("", encoding="utf-8")
                    return _completed(command)
                if command == [str(python.resolve()), "-c", RUNTIME_IMPORT_CHECK]:
                    return _completed(command)
                if command[:3] == [str(python.resolve()), "-c", RUNTIME_VERSION_CHECK]:
                    return _completed(command, stdout=f"{command[-1]}\n")
                self.fail(f"unexpected command: {command!r}")

            with (
                mock.patch.object(sys, "frozen", False, create=True),
                mock.patch.object(sys, "prefix", str(prefix)),
                mock.patch.object(sys, "executable", str(python)),
            ):
                result = prepare_addon_runtime(
                    data_dir=ignored_data,
                    runtime_bundle_dir=bundle_dir,
                    runner=runner,
                    package_ids=("mars",),
                    progress_callback=progress.append,
                )

            self.assertTrue(result.success, result.error)
            self.assertEqual(
                result.steps,
                ("install_runtime_package:mars", "verify_runtime"),
            )
            pip_commands = [command for command in calls if command[1:4] == ["-m", "pip", "install"]]
            self.assertEqual(len(pip_commands), 1)
            self.assertIn("--editable", pip_commands[0])
            self.assertIn("--no-deps", pip_commands[0])
            self.assertLess(
                pip_commands[0].index("--no-deps"),
                pip_commands[0].index("--editable"),
            )
            self.assertEqual(pip_commands[0][-1], str(mars_source.resolve()))
            self.assertNotIn(str(corex_source.resolve()), pip_commands[0])
            self.assertFalse(ignored_data.exists())
            self.assertIn(f"Using COREX Python environment: {python.resolve()}", progress)
            self.assertIn(
                f"Installing mars-modal-response-solver into {python.resolve()}...",
                progress,
            )

    def test_prepare_managed_runtime_accepts_source_target_only_outside_frozen_builds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            bundle_dir = Path(temp_dir) / "bundle"
            source_dir = Path(temp_dir) / "corex-source"
            bundle_dir.mkdir()
            source_dir.mkdir()
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        source="../corex-source",
                        extras=("all",),
                        required=True,
                        editable=True,
                    )
                },
            )
            paths = resolve_managed_runtime_paths(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
            )
            calls: list[list[str]] = []

            def runner(command: list[str], **_kwargs):
                calls.append(command)
                if command[:2] == ["py", "-3.10"] and "-c" in command:
                    return _completed(command, stdout=f"{sys.executable}\n")
                if command[:2] == ["py", "-3.10"] and command[-3:-1] == ["-m", "venv"]:
                    paths.python_executable.parent.mkdir(parents=True, exist_ok=True)
                    paths.python_executable.write_text("", encoding="utf-8")
                    return _completed(command)
                if command[:4] == [str(paths.python_executable), "-m", "pip", "install"]:
                    return _completed(command)
                if command == [str(paths.python_executable), "-c", RUNTIME_IMPORT_CHECK]:
                    return _completed(command)
                if command[:3] == [str(paths.python_executable), "-c", RUNTIME_VERSION_CHECK]:
                    return _completed(command, stdout="0.1.0\n")
                self.fail(f"unexpected command: {command!r}")

            source_result = prepare_managed_runtime(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
                runner=runner,
            )

            self.assertTrue(source_result.success, source_result.error)
            self.assertTrue(any(command[-1] == f"{source_dir}[all]" for command in calls))
            self.assertTrue(
                any("--editable" in command and command[-1] == f"{source_dir}[all]" for command in calls)
            )
            call_count = len(calls)

            with mock.patch.object(sys, "frozen", True, create=True):
                result = prepare_managed_runtime(
                    data_dir=Path(temp_dir) / "frozen-data",
                    runtime_bundle_dir=bundle_dir,
                    runner=runner,
                )

            self.assertFalse(result.success)
            self.assertIn("cannot use a source target", result.error)
            self.assertEqual(len(calls), call_count)

    def test_runtime_manifest_rejects_wheel_outside_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_dir = Path(temp_dir) / "bundle"
            bundle_dir.mkdir()
            (Path(temp_dir) / "outside.whl").write_text("fake", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        wheel="../outside.whl",
                        required=True,
                    )
                },
            )

            result = prepare_managed_runtime(runtime_bundle_dir=bundle_dir)

            self.assertFalse(result.success)
            self.assertIn("must be a file name inside", result.error)

    def test_resolve_managed_console_script_uses_managed_venv_scripts_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = resolve_managed_runtime_paths(data_dir=temp_dir)

            resolved = resolve_managed_console_script("MARSBatch.exe", paths=paths)

            expected_name = "MARSBatch.exe" if os.name == "nt" else "MARSBatch"
            self.assertEqual(resolved, paths.python_executable.parent / expected_name)

    def test_verify_managed_runtime_checks_declared_version_and_console_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_dir = Path(temp_dir) / "bundle"
            bundle_dir.mkdir()
            corex_wheel = bundle_dir / "corex.whl"
            mars_wheel = bundle_dir / "mars.whl"
            corex_wheel.write_text("fake", encoding="utf-8")
            mars_wheel.write_text("fake", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor", "0.1.0", wheel=corex_wheel.name, required=True
                    ),
                    "mars": _package(
                        "mars-modal-response-solver",
                        "1.0.0",
                        wheel=mars_wheel.name,
                        console_scripts=("MARSBatch",),
                    ),
                },
            )
            paths = resolve_managed_runtime_paths(
                data_dir=Path(temp_dir) / "data",
                runtime_bundle_dir=bundle_dir,
            )
            paths.python_executable.parent.mkdir(parents=True)
            paths.python_executable.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def runner(command: list[str], **_kwargs):
                calls.append(command)
                return _completed(command)

            status = verify_managed_runtime(
                paths=paths,
                runner=runner,
                package_ids=("mars",),
            )

            self.assertFalse(status.verified)
            self.assertIn("console script 'MARSBatch' was not found", status.error)
            version_commands = [
                command for command in calls if command[2] == RUNTIME_VERSION_CHECK
            ]
            self.assertEqual(
                [command[-2:] for command in version_commands],
                [
                    ["corex-node-editor", "0.1.0"],
                    ["mars-modal-response-solver", "1.0.0"],
                ],
            )

    def test_verify_managed_runtime_reports_missing_python_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            bundle_dir = Path(temp_dir) / "bundle"
            bundle_dir.mkdir()
            wheel_path = bundle_dir / "corex_node_editor-0.1.0-py3-none-any.whl"
            wheel_path.write_text("fake wheel", encoding="utf-8")
            _write_manifest(
                bundle_dir,
                {
                    "corex": _package(
                        "corex-node-editor",
                        "0.1.0",
                        wheel=wheel_path.name,
                        extras=("all",),
                        required=True,
                    )
                },
            )
            paths = resolve_managed_runtime_paths(
                data_dir=data_dir,
                runtime_bundle_dir=bundle_dir,
            )

            status = verify_managed_runtime(paths=paths)

            self.assertFalse(status.verified)
            self.assertFalse(status.exists)
            self.assertIn("was not found", status.error)


if __name__ == "__main__":
    unittest.main()
