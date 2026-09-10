from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from io import BytesIO, TextIOWrapper
from pathlib import Path
from subprocess import CompletedProcess, run
from tempfile import TemporaryDirectory
from unittest.mock import call
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_VERIFICATION_PATH = REPO_ROOT / "scripts" / "run_verification.py"
VERIFICATION_MANIFEST_PATH = REPO_ROOT / "scripts" / "verification_manifest.py"
CONFTEST_PATH = REPO_ROOT / "tests" / "conftest.py"
SHELL_ISOLATION_RUNTIME_PATH = REPO_ROOT / "tests" / "shell_isolation_runtime.py"
UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX_PATH = (
    REPO_ROOT / "docs" / "specs" / "perf" / "UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_CLOSEOUT_PYTEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py "
    "tests/test_run_verification.py --ignore=venv -q"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_module("verification_manifest_under_test", VERIFICATION_MANIFEST_PATH)
        cls.runner = load_module("run_verification_under_test", RUN_VERIFICATION_PATH)
        cls.packet_conftest = load_module("packet_conftest_under_test", CONFTEST_PATH)
        cls.shell_runtime = load_module(
            "shell_isolation_runtime_under_test",
            SHELL_ISOLATION_RUNTIME_PATH,
        )

    def assert_pytest_phase_command(
        self,
        command,
        *,
        phase_spec,
        worker_count: int | None,
        use_xdist: bool,
        target_args: tuple[str, ...] = (),
        deselect_args: tuple[str, ...] = (),
    ) -> None:
        expected = [
            "./venv/Scripts/python.exe",
            "-m",
            "pytest",
        ]
        if use_xdist:
            expected.extend(["-n", str(worker_count), "--dist", "load"])
        expected.extend(
            self.manifest.pytest_faulthandler_timeout_args(
                phase_spec.faulthandler_timeout_seconds
            )
        )
        expected.extend(["-m", phase_spec.marker_expression])
        expected.extend(self.manifest.worktree_pytest_ignore_args())
        expected.extend(self.manifest.non_shell_pytest_ignore_args())
        expected.extend(deselect_args)
        expected.extend(target_args)
        self.assertEqual(phase_spec.phase, command.phase)
        self.assertEqual(tuple(expected), command.display_argv)
        self.assertEqual({"QT_QPA_PLATFORM": "offscreen"}, command.env)

    def assert_context_budget_command(self, command) -> None:
        expected = (
            "./venv/Scripts/python.exe",
            self.manifest.CHECK_CONTEXT_BUDGETS_SCRIPT,
        )
        self.assertEqual(self.manifest.CONTEXT_BUDGET_PHASE, command.phase)
        self.assertEqual(expected, command.display_argv)
        self.assertEqual({}, command.env)

    def assert_qml_quick_command(self, command) -> None:
        expected_args = (
            "-input",
            "tests/qml_quick",
            "-eventdelay",
            "0",
            "-keydelay",
            "0",
            "-mousedelay",
            "0",
            "-o",
            "-,txt",
        )
        expected_env = {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_CONTROLS_STYLE": "Basic",
        }
        expected = ("C:/Qt/bin/qmltestrunner.exe", *expected_args)
        self.assertEqual(expected_args, self.manifest.QML_QUICK_ARGS)
        self.assertEqual(expected_env, self.manifest.QML_QUICK_ENV)
        self.assertEqual(self.manifest.QML_QUICK_PHASE, command.phase)
        self.assertEqual(expected, command.display_argv)
        self.assertEqual(expected_env, command.env)

    def assert_shell_isolation_command(
        self,
        command,
        *,
        worker_count: int | None,
        use_xdist: bool,
    ) -> None:
        expected = [
            "./venv/Scripts/python.exe",
            *self.manifest.shell_isolation_phase_pytest_args(
                worker_count if use_xdist else None
            ),
        ]
        self.assertEqual(self.manifest.SHELL_ISOLATION_SPEC.phase, command.phase)
        self.assertEqual(tuple(expected), command.display_argv)

    def test_full_mode_enables_xdist_for_fast_gui_and_shell_when_available(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "pytest_xdist_available", return_value=True),
            patch.object(self.runner, "resolve_max_parallel_workers", return_value=12),
        ):
            commands = self.runner.build_commands(
                "full",
                qml_quick_runner=("C:/Qt/bin/qmltestrunner.exe", None),
            )

        self.assertEqual(
            [
                "fast.pytest",
                "fast.serial.pytest",
                "gui.qml_quick",
                "gui.pytest",
                "gui.serial.pytest",
                "slow.pytest",
                "full.shell_isolation.pytest",
            ],
            [command.phase for command in commands],
        )

        (
            fast_command,
            fast_serial_command,
            qml_quick_command,
            gui_command,
            gui_serial_command,
            slow_command,
            shell_command,
        ) = commands
        self.assert_pytest_phase_command(
            fast_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE["fast"],
            worker_count=12,
            use_xdist=True,
            deselect_args=self.manifest.fast_serial_pytest_deselect_args(),
        )
        self.assert_pytest_phase_command(
            fast_serial_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE[self.manifest.FAST_SERIAL_SUITE_KEY],
            worker_count=None,
            use_xdist=False,
            target_args=self.manifest.fast_serial_pytest_targets(),
        )
        self.assert_qml_quick_command(qml_quick_command)
        self.assert_pytest_phase_command(
            gui_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE["gui"],
            worker_count=self.manifest.MAX_GUI_PARALLEL_WORKERS,
            use_xdist=True,
            deselect_args=self.manifest.gui_serial_pytest_deselect_args(),
        )
        self.assert_pytest_phase_command(
            gui_serial_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE[
                self.manifest.GUI_SERIAL_SUITE_KEY
            ],
            worker_count=None,
            use_xdist=False,
            target_args=self.manifest.gui_serial_pytest_targets(),
        )
        self.assert_pytest_phase_command(
            slow_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE["slow"],
            worker_count=None,
            use_xdist=False,
        )
        self.assert_shell_isolation_command(
            shell_command,
            worker_count=self.manifest.MAX_SHELL_ISOLATION_PARALLEL_WORKERS,
            use_xdist=True,
        )

    def test_fast_mode_runs_pytest_without_context_budget_gate(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "pytest_xdist_available", return_value=True),
            patch.object(self.runner, "resolve_max_parallel_workers", return_value=8),
        ):
            commands = self.runner.build_commands("fast")

        self.assertEqual(
            [
                self.manifest.PYTEST_PHASE_SPECS_BY_MODE["fast"].phase,
                self.manifest.PYTEST_PHASE_SPECS_BY_MODE[self.manifest.FAST_SERIAL_SUITE_KEY].phase,
            ],
            [command.phase for command in commands],
        )
        fast_command, fast_serial_command = commands
        self.assert_pytest_phase_command(
            fast_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE["fast"],
            worker_count=8,
            use_xdist=True,
            deselect_args=self.manifest.fast_serial_pytest_deselect_args(),
        )
        self.assert_pytest_phase_command(
            fast_serial_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE[self.manifest.FAST_SERIAL_SUITE_KEY],
            worker_count=None,
            use_xdist=False,
            target_args=self.manifest.fast_serial_pytest_targets(),
        )

    def test_gui_parallel_worker_count_is_capped_for_qml_heavy_phase(self) -> None:
        self.assertEqual(1, self.runner.resolve_gui_parallel_workers(1))
        self.assertEqual(4, self.runner.resolve_gui_parallel_workers(4))
        self.assertEqual(self.manifest.MAX_GUI_PARALLEL_WORKERS, self.runner.resolve_gui_parallel_workers(6))
        self.assertEqual(self.manifest.MAX_GUI_PARALLEL_WORKERS, self.runner.resolve_gui_parallel_workers(12))

    def test_gui_mode_falls_back_to_serial_with_notice_when_xdist_is_unavailable(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "pytest_xdist_available", return_value=False),
            patch.object(self.runner, "resolve_max_parallel_workers", return_value=12),
        ):
            commands = self.runner.build_commands(
                "gui",
                qml_quick_runner=("C:/Qt/bin/qmltestrunner.exe", None),
            )

        self.assertEqual(
            ["gui.qml_quick", "gui.pytest", "gui.serial.pytest"],
            [command.phase for command in commands],
        )
        qml_quick_command, gui_command, gui_serial_command = commands
        self.assert_qml_quick_command(qml_quick_command)
        self.assert_pytest_phase_command(
            gui_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE["gui"],
            worker_count=None,
            use_xdist=False,
            deselect_args=self.manifest.gui_serial_pytest_deselect_args(),
        )
        self.assertEqual(
            "pytest-xdist is unavailable; falling back to serial pytest for gui mode.",
            gui_command.notice,
        )
        self.assert_pytest_phase_command(
            gui_serial_command,
            phase_spec=self.manifest.PYTEST_PHASE_SPECS_BY_MODE[
                self.manifest.GUI_SERIAL_SUITE_KEY
            ],
            worker_count=None,
            use_xdist=False,
            target_args=self.manifest.gui_serial_pytest_targets(),
        )

    def test_gui_serial_target_and_deselection_contract_is_exact(self) -> None:
        expected_targets = (
            (
                "tests/test_docx_rendering_comparison.py::"
                "test_docx_rendering_comparison_single_renderer_smoke"
            ),
            "tests/test_viewer_surface_contract.py",
            "tests/test_flow_edge_labels.py",
        )
        self.assertEqual(expected_targets, self.manifest.GUI_SERIAL_PYTEST_TARGETS)
        self.assertEqual(expected_targets, self.manifest.gui_serial_pytest_targets())
        self.assertEqual(
            tuple(f"--deselect={target}" for target in expected_targets),
            self.manifest.gui_serial_pytest_deselect_args(),
        )

    def test_gui_serial_manifest_targets_collect(self) -> None:
        completed = run(
            (
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-n",
                "0",
                *self.manifest.GUI_SERIAL_PYTEST_TARGETS,
            ),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={
                key: value
                for key, value in os.environ.items()
                if key.upper() not in {"PYTHONHOME", "PYTHONPATH"}
            },
        )

        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )

    def test_fast_serial_target_and_deselection_contract_is_exact(self) -> None:
        expected_targets = (
            "tests/test_plugin_loader.py::test_bootstrap_import_keeps_builtin_and_public_plugin_routes_lazy",
            (
                "tests/test_external_python_client.py::ExternalPythonSelectionTests::"
                "test_execution_backend_client_uses_application_default_python_policy_for_external_worker"
            ),
            (
                "tests/test_external_python_client.py::ExternalPythonSelectionTests::"
                "test_execution_backend_client_uses_workflow_python_executable_for_external_worker"
            ),
            (
                "tests/test_backend_client.py::BackendSelectionIntegrationTests::"
                "test_headless_runtime_loads_project_selects_workspace_and_runs_without_qapplication"
            ),
            "tests/test_runtime_cli.py::test_runtime_cli_module_help",
            "tests/test_process_client.py::ProcessClientTests",
            "tests/test_scientific_worker_transport.py",
            (
                "tests/test_managed_runtime.py::ManagedRuntimeTests::"
                "test_run_command_streams_output_before_process_finishes"
            ),
            "tests/test_mars_function_migration.py::test_t14_all_three_functions_execute_through_worker_runtime",
            (
                "tests/test_process_run_node.py::ProcessRunNodeTests::"
                "test_stop_run_cancels_active_process_node"
            ),
            "tests/test_mcf_dpf_section_resultants_gui.py",
            "tests/test_jupyter_server_manager.py::JupyterServerManagerIntegrationTests",
            "tests/test_project_file_issues.py",
            (
                "tests/test_workspace_edit_controller.py::"
                "WorkspaceEditControllerCoreTests::"
                "test_paste_nodes_from_clipboard_is_noop_when_clipboard_is_missing"
            ),
        )
        self.assertEqual(expected_targets, self.manifest.FAST_SERIAL_PYTEST_TARGETS)
        self.assertEqual(expected_targets, self.manifest.fast_serial_pytest_targets())
        self.assertEqual(
            tuple(f"--deselect={target}" for target in expected_targets),
            self.manifest.fast_serial_pytest_deselect_args(),
        )

    def test_fast_serial_manifest_targets_collect(self) -> None:
        completed = run(
            (
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-n",
                "0",
                *self.manifest.FAST_SERIAL_PYTEST_TARGETS,
            ),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={
                key: value
                for key, value in os.environ.items()
                if key.upper() not in {"PYTHONHOME", "PYTHONPATH"}
            },
        )

        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )

    def test_fast_and_slow_modes_never_resolve_qml_quick_runner(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "pytest_xdist_available", return_value=True),
            patch.object(self.runner, "resolve_max_parallel_workers", return_value=4),
            patch.object(self.runner, "resolve_qml_quick_runner") as quick_mock,
        ):
            self.runner.build_commands("fast")
            self.runner.build_commands("slow")

        quick_mock.assert_not_called()

    def test_resolve_qmltestrunner_prefers_qt_root_over_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            runner_path = Path(temp_dir) / "bin" / self.runner._qmltestrunner_name()
            runner_path.parent.mkdir()
            runner_path.touch()
            with (
                patch.dict(self.runner.os.environ, {"QT_ROOT": temp_dir}, clear=True),
                patch.object(self.runner.shutil, "which") as which_mock,
            ):
                resolved = self.runner.resolve_qmltestrunner()

        self.assertEqual(runner_path, resolved)
        which_mock.assert_not_called()

    def test_invalid_explicit_qt_root_does_not_fall_back_to_path(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            patch.dict(self.runner.os.environ, {"QT_ROOT": temp_dir}, clear=True),
            patch.object(
                self.runner.shutil,
                "which",
                return_value="C:/other/Qt/bin/qmltestrunner.exe",
            ) as which_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "QT_ROOT does not contain"):
                self.runner.resolve_qmltestrunner()

        which_mock.assert_not_called()

    def test_resolve_qmltestrunner_uses_path_without_qt_root(self) -> None:
        expected = "C:/Qt/bin/qmltestrunner.exe"
        with (
            patch.dict(self.runner.os.environ, {}, clear=True),
            patch.object(self.runner.shutil, "which", return_value=expected),
        ):
            resolved = self.runner.resolve_qmltestrunner()

        self.assertEqual(Path(expected), resolved)

    def test_qmltestrunner_version_accepts_patch_only_drift(self) -> None:
        runner = Path("C:/Qt/bin/qmltestrunner.exe")
        with (
            patch.object(
                self.runner,
                "resolve_qtpaths",
                return_value=Path("C:/Qt/bin/qtpaths6.exe"),
            ),
            patch.object(
                self.runner,
                "probe_command_output",
                side_effect=["6.11.1", "6.11.0"],
            ),
        ):
            self.runner.validate_qmltestrunner_version(runner, "python.exe")

    def test_qmltestrunner_version_rejects_major_minor_mismatch(self) -> None:
        runner = Path("C:/Qt/bin/qmltestrunner.exe")
        with (
            patch.object(
                self.runner,
                "resolve_qtpaths",
                return_value=Path("C:/Qt/bin/qtpaths6.exe"),
            ),
            patch.object(
                self.runner,
                "probe_command_output",
                side_effect=["6.10.2", "6.11.0"],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "same Qt major/minor"):
                self.runner.validate_qmltestrunner_version(runner, "python.exe")

    def test_resolve_qtpaths_requires_sibling_sdk_probe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            runner = Path(temp_dir) / self.runner._qmltestrunner_name()
            runner.touch()
            qtpaths_names = (
                ("qtpaths6.exe", "qtpaths.exe")
                if self.runner.os.name == "nt"
                else ("qtpaths6", "qtpaths")
            )
            with self.assertRaisesRegex(
                RuntimeError,
                f"Neither {qtpaths_names[0]} nor {qtpaths_names[1]}",
            ):
                self.runner.resolve_qtpaths(runner)

    def test_resolve_qtpaths_prefers_qtpaths6(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suffix = ".exe" if self.runner.os.name == "nt" else ""
            runner = Path(temp_dir) / self.runner._qmltestrunner_name()
            qtpaths6 = runner.with_name(f"qtpaths6{suffix}")
            runner.with_name(f"qtpaths{suffix}").touch()
            qtpaths6.touch()

            resolved = self.runner.resolve_qtpaths(runner)

        self.assertEqual(qtpaths6, resolved)

    def test_resolve_qtpaths_falls_back_to_qtpaths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suffix = ".exe" if self.runner.os.name == "nt" else ""
            runner = Path(temp_dir) / self.runner._qmltestrunner_name()
            qtpaths = runner.with_name(f"qtpaths{suffix}")
            qtpaths.touch()

            resolved = self.runner.resolve_qtpaths(runner)

        self.assertEqual(qtpaths, resolved)

    def test_version_probe_launch_error_becomes_dry_run_notice(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_qmltestrunner",
                return_value=Path("C:/Qt/bin/qmltestrunner.exe"),
            ),
            patch.object(
                self.runner,
                "resolve_qtpaths",
                return_value=Path("C:/Qt/bin/qtpaths6.exe"),
            ),
            patch.object(
                self.runner.subprocess,
                "run",
                side_effect=OSError("cannot launch qtpaths"),
            ),
        ):
            runner, notice = self.runner.resolve_qml_quick_runner(
                "python.exe",
                dry_run=True,
            )

        self.assertEqual(self.runner._qmltestrunner_name(), runner)
        self.assertIn("Failed to launch Qt SDK version", notice)
        self.assertIn("cannot launch qtpaths", notice)

    def test_qml_quick_dry_run_uses_placeholder_when_sdk_is_missing(self) -> None:
        with patch.object(
            self.runner,
            "resolve_qmltestrunner",
            side_effect=RuntimeError("missing Qt SDK"),
        ):
            runner, notice = self.runner.resolve_qml_quick_runner(
                "python.exe",
                dry_run=True,
            )

        self.assertEqual(self.runner._qmltestrunner_name(), runner)
        self.assertIn("missing Qt SDK", notice)
        self.assertIn("Real gui/full execution requires it", notice)

    def test_main_gui_dry_run_prints_missing_sdk_placeholder_and_notice(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("python.exe", "python.exe"),
            ),
            patch.object(
                self.runner,
                "resolve_qmltestrunner",
                side_effect=RuntimeError("missing Qt SDK"),
            ),
            patch.object(self.runner, "pytest_xdist_available", return_value=False),
            patch.object(self.runner, "resolve_max_parallel_workers", return_value=2),
            patch("builtins.print") as print_mock,
        ):
            return_code = self.runner.main(["--mode", "gui", "--dry-run"])

        rendered = "\n".join(
            " ".join(str(value) for value in call_args.args)
            for call_args in print_mock.call_args_list
        )
        self.assertEqual(0, return_code)
        self.assertIn("[gui.qml_quick]", rendered)
        self.assertIn("NOTE: missing Qt SDK", rendered)
        self.assertIn(self.runner._qmltestrunner_name(), rendered)
        self.assertIn("Dry run only; no commands executed.", rendered)

    def test_main_preflights_qml_quick_before_pytest_repair(self) -> None:
        call_order: list[str] = []
        command = self.runner.CommandSpec(
            phase=self.manifest.QML_QUICK_PHASE,
            argv=("qmltestrunner.exe",),
            display_argv=("qmltestrunner.exe",),
            env=self.manifest.QML_QUICK_ENV,
        )

        def resolve_quick(*_args, **_kwargs):
            call_order.append("qml")
            return "qmltestrunner.exe", None

        def ensure_pytest(*_args, **_kwargs):
            call_order.append("pytest")
            return False

        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("python.exe", "python.exe"),
            ),
            patch.object(self.runner, "resolve_qml_quick_runner", side_effect=resolve_quick),
            patch.object(self.runner, "ensure_pytest_stack_ready", side_effect=ensure_pytest),
            patch.object(self.runner, "build_commands", return_value=[command]),
            patch.object(self.runner, "run_command", return_value=0),
        ):
            return_code = self.runner.main(["--mode", "gui"])

        self.assertEqual(0, return_code)
        self.assertEqual(["qml", "pytest"], call_order)

    def test_main_fails_qml_preflight_before_pytest_repair(self) -> None:
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("python.exe", "python.exe"),
            ),
            patch.object(
                self.runner,
                "resolve_qml_quick_runner",
                side_effect=RuntimeError("Qt version mismatch"),
            ),
            patch.object(self.runner, "ensure_pytest_stack_ready") as ensure_mock,
            patch.object(self.runner.sys, "stderr"),
        ):
            return_code = self.runner.main(["--mode", "gui"])

        self.assertEqual(1, return_code)
        ensure_mock.assert_not_called()

    def test_ensure_pytest_stack_ready_repairs_missing_direct_dependencies(self) -> None:
        with (
            patch.object(
                self.runner,
                "probe_pytest_startup",
                side_effect=[
                    (False, "No module named 'iniconfig'"),
                    (False, "No module named 'exceptiongroup'"),
                    (True, ""),
                ],
            ),
            patch.object(self.runner, "pytest_related_unmet_requirements", return_value=()),
            patch.object(self.runner, "install_python_packages", return_value=0) as install_mock,
            patch("builtins.print") as print_mock,
        ):
            repaired = self.runner.ensure_pytest_stack_ready("./venv/Scripts/python.exe")

        self.assertTrue(repaired)
        self.assertEqual(
            [
                call("./venv/Scripts/python.exe", "iniconfig"),
                call("./venv/Scripts/python.exe", "exceptiongroup"),
            ],
            install_mock.call_args_list,
        )
        self.assertEqual(2, print_mock.call_count)

    def test_ensure_pytest_stack_ready_raises_when_repairable_module_is_not_identified(self) -> None:
        with (
            patch.object(
                self.runner,
                "probe_pytest_startup",
                return_value=(False, "pytest startup exploded"),
            ),
            patch.object(self.runner, "pytest_related_unmet_requirements", return_value=()),
        ):
            with self.assertRaisesRegex(RuntimeError, "pytest is not startup-ready"):
                self.runner.ensure_pytest_stack_ready("./venv/Scripts/python.exe")

    def test_ensure_pytest_stack_ready_repairs_core_pip_check_gaps_before_startup(self) -> None:
        with (
            patch.object(
                self.runner,
                "probe_pytest_startup",
                return_value=(True, ""),
            ),
            patch.object(
                self.runner,
                "pytest_related_unmet_requirements",
                side_effect=[
                    ("colorama",),
                    (),
                ],
            ),
            patch.object(self.runner, "install_python_packages", return_value=0) as install_mock,
            patch("builtins.print") as print_mock,
        ):
            repaired = self.runner.ensure_pytest_stack_ready("./venv/Scripts/python.exe")

        self.assertTrue(repaired)
        install_mock.assert_called_once_with("./venv/Scripts/python.exe", "colorama")
        self.assertEqual(1, print_mock.call_count)

    def test_ensure_pytest_stack_ready_uses_pip_check_for_pytest_plugin_requirements(self) -> None:
        with (
            patch.object(
                self.runner,
                "probe_pytest_startup",
                side_effect=[
                    (False, "plugin import crashed"),
                    (True, ""),
                ],
            ),
            patch.object(
                self.runner,
                "pytest_related_unmet_requirements",
                side_effect=[
                    (),
                    ("execnet>=2.1", "coverage[toml]>=7.10.6"),
                    (),
                ],
            ),
            patch.object(self.runner, "install_python_packages", return_value=0) as install_mock,
            patch("builtins.print") as print_mock,
        ):
            repaired = self.runner.ensure_pytest_stack_ready("./venv/Scripts/python.exe")

        self.assertTrue(repaired)
        install_mock.assert_called_once_with(
            "./venv/Scripts/python.exe",
            "execnet>=2.1",
            "coverage[toml]>=7.10.6",
        )
        self.assertEqual(1, print_mock.call_count)

    def test_main_repairs_pytest_stack_before_running_commands(self) -> None:
        command = self.runner.CommandSpec(
            phase="fast.pytest",
            argv=("python", "-m", "pytest"),
            display_argv=("./venv/Scripts/python.exe", "-m", "pytest"),
            env={},
        )
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "ensure_pytest_stack_ready", return_value=True) as ensure_mock,
            patch.object(self.runner, "build_commands", return_value=[command]),
            patch.object(self.runner, "run_command", return_value=0) as run_mock,
        ):
            return_code = self.runner.main(["--mode", "fast"])

        self.assertEqual(0, return_code)
        ensure_mock.assert_called_once_with("./venv/Scripts/python.exe")
        run_mock.assert_called_once_with(command)

    def test_main_summarized_output_routes_phase_to_log_file(self) -> None:
        command = self.runner.CommandSpec(
            phase="fast.pytest",
            argv=("python", "-m", "pytest"),
            display_argv=("./venv/Scripts/python.exe", "-m", "pytest"),
            env={},
        )
        summary_dir = REPO_ROOT / "artifacts" / "verification_logs" / "unit-test-run"
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "ensure_pytest_stack_ready", return_value=True),
            patch.object(self.runner, "build_commands", return_value=[command]),
            patch.object(self.runner, "create_summary_log_dir", return_value=summary_dir),
            patch.object(self.runner, "run_command") as stream_mock,
            patch.object(self.runner, "run_command_summarized", return_value=0) as summary_mock,
        ):
            return_code = self.runner.main(
                [
                    "--mode",
                    "fast",
                    "--summarize-output",
                    "--failure-tail-lines",
                    "12",
                ]
            )

        self.assertEqual(0, return_code)
        stream_mock.assert_not_called()
        summary_mock.assert_called_once_with(
            command,
            log_path=summary_dir / "01_fast.pytest.log",
            failure_tail_lines=12,
        )

    def test_summarized_failure_tail_replaces_unencodable_console_text(self) -> None:
        command = self.runner.CommandSpec(
            phase="fast.pytest",
            argv=("python", "-m", "pytest"),
            display_argv=("./venv/Scripts/python.exe", "-m", "pytest"),
            env={},
        )
        encoded_output = BytesIO()
        console = TextIOWrapper(encoded_output, encoding="cp1252", errors="strict")

        with (
            TemporaryDirectory() as temp_dir,
            patch.object(
                self.runner.subprocess,
                "run",
                return_value=CompletedProcess(command.argv, returncode=1),
            ),
            patch.object(self.runner, "_tail_lines", return_value=("unencodable \ufffd tail",)),
            patch.object(self.runner.sys, "stdout", console),
        ):
            return_code = self.runner.run_command_summarized(
                command,
                log_path=Path(temp_dir) / "fast.pytest.log",
                failure_tail_lines=1,
            )
            console.flush()

        self.assertEqual(1, return_code)
        rendered = encoded_output.getvalue().decode("cp1252")
        self.assertIn("unencodable ? tail", rendered)
        self.assertIn("--- end log tail ---", rendered)

    def test_main_skips_pytest_stack_repair_on_dry_run(self) -> None:
        command = self.runner.CommandSpec(
            phase="fast.pytest",
            argv=("python", "-m", "pytest"),
            display_argv=("./venv/Scripts/python.exe", "-m", "pytest"),
            env={},
        )
        with (
            patch.object(
                self.runner,
                "resolve_python",
                return_value=("./venv/Scripts/python.exe", "./venv/Scripts/python.exe"),
            ),
            patch.object(self.runner, "ensure_pytest_stack_ready") as ensure_mock,
            patch.object(self.runner, "build_commands", return_value=[command]),
            patch.object(self.runner, "run_command") as run_mock,
        ):
            return_code = self.runner.main(["--mode", "fast", "--dry-run"])

        self.assertEqual(0, return_code)
        ensure_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_resolve_python_falls_back_to_current_venv_when_worktree_helper_is_inaccessible(self) -> None:
        with (
            patch.object(self.runner, "local_venv_python_exists", return_value=False),
            patch.object(self.runner, "current_python_matches_project_venv", return_value=True),
            patch.object(self.runner.sys, "executable", "C:/real/project/venv/Scripts/python.exe"),
        ):
            python_exec, python_display = self.runner.resolve_python()

        self.assertEqual("C:/real/project/venv/Scripts/python.exe", python_exec)
        self.assertEqual("./venv/Scripts/python.exe", python_display)

    def test_shell_isolation_runtime_uses_manifest_owned_pytest_child_args(self) -> None:
        nodeid = "tests/main_window_shell/passive_image_nodes.py::MainWindowShellPassiveImageNodesTests"
        pytest_args = self.manifest.shell_isolation_target_pytest_args(nodeid)
        expected = (
            sys.executable,
            *pytest_args[:2],
            "-n",
            "0",
            *pytest_args[2:],
        )
        self.assertEqual(expected, self.shell_runtime.build_pytest_nodeid_command(nodeid))

    def test_shell_isolation_runtime_serializes_pytest_nodeid_lists(self) -> None:
        nodeids = (
            "tests/main_window_shell/bridge_contracts.py::ShellLibraryBridgeTests",
            "tests/main_window_shell/bridge_contracts.py::ShellInspectorBridgeTests",
        )
        pytest_args = self.manifest.shell_isolation_target_pytest_args(*nodeids)
        expected = (
            sys.executable,
            *pytest_args[:2],
            "-n",
            "0",
            *pytest_args[2:],
        )
        self.assertEqual(expected, self.shell_runtime.build_pytest_nodeid_list_command(nodeids))

    def test_shell_isolation_runtime_uses_manifest_owned_target_timeout(self) -> None:
        target = self.shell_runtime.ShellIsolationTarget(
            target_id="test-timeout-owner",
            command=(sys.executable, "-c", "pass"),
        )
        completed = CompletedProcess(target.command, returncode=0, stdout="", stderr="")

        with patch.object(
            self.shell_runtime.subprocess,
            "run",
            return_value=completed,
        ) as run_mock:
            self.assertIs(completed, self.shell_runtime.run_shell_isolation_target(target))

        self.assertEqual(
            self.manifest.SHELL_ISOLATION_TARGET_TIMEOUT_SECONDS,
            run_mock.call_args.kwargs["timeout"],
        )
        self.assertEqual(360, run_mock.call_args.kwargs["timeout"])

    def test_shell_isolation_runtime_reports_timeout_with_normalized_partial_output(self) -> None:
        target = self.shell_runtime.ShellIsolationTarget(
            target_id="test-timeout-report",
            command=(sys.executable, "-c", "pass"),
        )
        timeout = self.shell_runtime.subprocess.TimeoutExpired(
            target.command,
            self.manifest.SHELL_ISOLATION_TARGET_TIMEOUT_SECONDS,
            output=b"partial stdout\r\n",
            stderr="partial stderr\r\n",
        )

        with (
            patch.object(self.shell_runtime.subprocess, "run", side_effect=timeout),
            patch.object(self.shell_runtime.time, "monotonic", side_effect=(10.0, 371.25)),
            self.assertRaises(self.shell_runtime.ShellIsolationTargetTimeout) as raised,
        ):
            self.shell_runtime.run_shell_isolation_target(target)

        message = str(raised.exception)
        self.assertIn("test-timeout-report", message)
        self.assertIn("after 361.25s", message)
        self.assertIn("hard limit=360s", message)
        self.assertIn(f"Command: {sys.executable} -c pass", message)
        self.assertIn("stdout:\npartial stdout\nstderr:\npartial stderr", message)
        self.assertNotIn("\\r", message)
        self.assertNotIn("b'partial stdout", message)

    def test_manual_shell_wrappers_delegate_to_timeout_runtime(self) -> None:
        for relative_path in (
            "tests/test_script_editor_dock.py",
            "tests/test_shell_run_controller.py",
            "tests/test_shell_project_session_controller.py",
            "tests/test_graph_theme_shell.py",
        ):
            source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn("run_shell_isolation_target(target)", source)
                self.assertNotIn("subprocess.run(", source)

    def test_shell_isolation_runtime_uses_manifest_owned_target_catalogs(self) -> None:
        self.assertEqual(
            self.manifest.shell_isolation_target_catalog_module_names(),
            tuple(spec.module_name for spec in self.manifest.SHELL_ISOLATION_CATALOG_SPECS),
        )

    def test_shell_isolation_target_catalog_specs_own_target_prefixes(self) -> None:
        self.assertEqual(
            ("main_window__", "script_editor__", "run_controller__", "project_session__"),
            self.manifest.shell_isolation_target_id_prefixes(),
        )

    def test_pytest_marker_catalogs_follow_verification_manifest(self) -> None:
        self.assertEqual(frozenset(self.manifest.GUI_TEST_PATHS), self.packet_conftest._GUI_TEST_PATHS)
        self.assertEqual(
            frozenset(self.manifest.SLOW_TEST_PATHS),
            self.packet_conftest._SLOW_TEST_PATHS,
        )
        self.assertEqual(
            self.manifest.pytest_marker_path_sets(),
            self.packet_conftest._MARKER_TEST_PATHS_BY_NAME,
        )

    def test_verification_suite_registry_feeds_paths_modes_and_shell_isolation(self) -> None:
        suite_keys = {spec.key for spec in self.manifest.VERIFICATION_SUITE_SPECS}
        registered_paths = [
            path_spec.path for path_spec in self.manifest.VERIFICATION_TEST_PATH_SPECS
        ]
        path_suite_keys = {
            suite_key
            for path_spec in self.manifest.VERIFICATION_TEST_PATH_SPECS
            for suite_key in path_spec.suites
        }
        phase_suite_keys = tuple(
            spec.key
            for spec in self.manifest.VERIFICATION_SUITE_SPECS
            if spec.phase is not None and spec.marker_expression is not None
        )

        self.assertLessEqual(path_suite_keys, suite_keys)
        self.assertEqual(len(registered_paths), len(set(registered_paths)))
        self.assertEqual(
            self.manifest.suite_test_paths(self.manifest.SHELL_SUITE_KEY),
            self.manifest.SHELL_BACKED_TEST_PATHS,
        )
        self.assertEqual(
            self.manifest.non_shell_pytest_ignore_paths(),
            self.manifest.NON_SHELL_PYTEST_IGNORES,
        )
        self.assertEqual(
            phase_suite_keys,
            tuple(spec.mode for spec in self.manifest.PYTEST_PHASE_SPECS),
        )
        self.assertEqual(
            (
                self.manifest.FAST_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
                self.manifest.FAST_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
                self.manifest.GUI_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
                self.manifest.GUI_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
                self.manifest.SLOW_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
            ),
            tuple(
                spec.faulthandler_timeout_seconds
                for spec in self.manifest.PYTEST_PHASE_SPECS
            ),
        )
        self.assertEqual(
            (self.manifest.SHELL_ISOLATION_SPEC.test_path,),
            self.manifest.suite_test_paths(self.manifest.SHELL_ISOLATION_PHASE_KEY),
        )
        self.assertEqual(
            self.manifest.SHELL_ISOLATION_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
            self.manifest.SHELL_ISOLATION_SPEC.faulthandler_timeout_seconds,
        )
        self.assertEqual(
            self.manifest.SHELL_ISOLATION_TARGET_TIMEOUT_SECONDS,
            self.manifest.SHELL_ISOLATION_SPEC.target_timeout_seconds,
        )
        self.assertEqual(330, self.manifest.SHELL_ISOLATION_SPEC.faulthandler_timeout_seconds)
        self.assertEqual(360, self.manifest.SHELL_ISOLATION_SPEC.target_timeout_seconds)
        self.assertEqual(
            self.manifest.MAX_SHELL_ISOLATION_PARALLEL_WORKERS,
            self.manifest.verification_suite_spec(
                self.manifest.SHELL_ISOLATION_PHASE_KEY
            ).worker_cap,
        )
        self.assertGreater(
            self.manifest.SHELL_ISOLATION_SPEC.target_timeout_seconds,
            self.manifest.SHELL_ISOLATION_SPEC.faulthandler_timeout_seconds,
        )
        self.assertTrue(
            self.manifest.verification_suite_spec(
                self.manifest.SHELL_ISOLATION_PHASE_KEY
            ).shell_isolation
        )

    def test_context_budget_guardrail_metadata_matches_packet_contract(self) -> None:
        self.assertEqual(
            "scripts/check_context_budgets.py",
            self.manifest.CHECK_CONTEXT_BUDGETS_SCRIPT,
        )
        self.assertEqual(
            "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
            self.manifest.CONTEXT_BUDGET_RULES_PATH,
        )
        self.assertEqual(
            "tests/test_context_budget_guardrails.py",
            self.manifest.CONTEXT_BUDGET_GUARDRAILS_TEST,
        )
        self.assertEqual(
            "./venv/Scripts/python.exe scripts/check_context_budgets.py",
            self.manifest.CONTEXT_BUDGET_CHECK_COMMAND,
        )
        self.assertEqual("context_budgets", self.manifest.CONTEXT_BUDGET_PHASE_KEY)
        self.assertEqual("fast.context_budgets", self.manifest.CONTEXT_BUDGET_PHASE)
        self.assertEqual(
            (
                "./venv/Scripts/python.exe scripts/check_context_budgets.py",
                "./venv/Scripts/python.exe -m pytest tests/test_context_budget_guardrails.py "
                "tests/test_run_verification.py --ignore=venv -q",
            ),
            self.manifest.P07_CONTEXT_BUDGET_VERIFICATION_COMMANDS,
        )
        self.assertEqual(
            "./venv/Scripts/python.exe scripts/check_context_budgets.py",
            self.manifest.P07_CONTEXT_BUDGET_REVIEW_GATE_COMMAND,
        )
        self.assertEqual(
            (
                "scripts/check_context_budgets.py",
                "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
                "tests/test_context_budget_guardrails.py",
            ),
            self.manifest.P07_CONTEXT_BUDGET_ARTIFACTS,
        )
        self.assertEqual(
            "./venv/Scripts/python.exe -m pytest tests/test_context_budget_guardrails.py "
            "tests/test_run_verification.py --ignore=venv -q",
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_PYTEST_COMMAND,
        )
        self.assertEqual(
            "./venv/Scripts/python.exe scripts/run_verification.py --mode fast --dry-run",
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_FAST_DRY_RUN_COMMAND,
        )
        self.assertEqual(
            (
                "./venv/Scripts/python.exe scripts/check_context_budgets.py",
                "./venv/Scripts/python.exe -m pytest tests/test_context_budget_guardrails.py "
                "tests/test_run_verification.py --ignore=venv -q",
                "./venv/Scripts/python.exe scripts/run_verification.py --mode fast --dry-run",
            ),
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_VERIFICATION_COMMANDS,
        )
        self.assertEqual(
            "./venv/Scripts/python.exe scripts/check_context_budgets.py",
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_REVIEW_GATE_COMMAND,
        )
        self.assertEqual(
            (
                "scripts/check_context_budgets.py",
                "scripts/run_verification.py",
                "scripts/verification_manifest.py",
                "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
                "tests/test_context_budget_guardrails.py",
                "tests/test_run_verification.py",
            ),
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_ARTIFACTS,
        )

    def test_followup_closeout_matrix_records_guardrail_and_closeout_commands(self) -> None:
        text = UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX_PATH.read_text(encoding="utf-8-sig")

        for token in (
            self.manifest.CONTEXT_BUDGET_RULES_PATH,
            self.manifest.CONTEXT_BUDGET_CHECK_COMMAND,
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_PYTEST_COMMAND,
            self.manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_FAST_DRY_RUN_COMMAND,
            UI_CONTEXT_SCALABILITY_FOLLOWUP_CLOSEOUT_PYTEST_COMMAND,
            UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND,
            UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND,
            "UI_CONTEXT_SCALABILITY_FOLLOWUP_STATUS.md",
            "P08_canonical_ui_test_packet_docs_WRAPUP.md",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
