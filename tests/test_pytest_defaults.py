from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from ea_node_editor import pytest_defaults
from scripts import verification_manifest as manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


class PytestDefaultsTests(unittest.TestCase):
    def test_empty_invocation_uses_fast_slice_parallel_defaults(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=(),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertTrue(decision.enable_xdist)
        self.assertEqual("not gui and not slow", decision.markexpr)
        self.assertEqual(
            tuple(
                dict.fromkeys(
                    (
                        *manifest.non_shell_pytest_ignore_paths(),
                        *manifest.fast_serial_pytest_paths(),
                    )
                )
            ),
            decision.ignored_paths,
        )

    def test_tests_directory_invocation_uses_fast_slice_parallel_defaults(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertTrue(decision.enable_xdist)
        self.assertEqual("not gui and not slow", decision.markexpr)

    def test_focused_non_gui_file_enables_parallelism_without_rewriting_markexpr(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests/test_icon_registry.py",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertTrue(decision.enable_xdist)
        self.assertIsNone(decision.markexpr)
        self.assertEqual((), decision.ignored_paths)

    def test_nodeid_target_is_normalized_to_its_test_file(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests/test_icon_registry.py::test_icon_map_contains_expected_entries",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertTrue(decision.enable_xdist)
        self.assertEqual(
            ("tests/test_icon_registry.py",),
            pytest_defaults.selected_test_paths(
                ("tests/test_icon_registry.py::test_icon_map_contains_expected_entries",),
                REPO_ROOT,
            ),
        )

    def test_gui_targets_stay_off_the_default_parallel_path(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests/test_viewer_surface_host.py",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertFalse(decision.enable_xdist)

    def test_slow_targets_stay_off_the_default_parallel_path(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests/test_track_h_perf_harness.py",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertFalse(decision.enable_xdist)

    def test_fast_serial_targets_stay_off_the_default_parallel_path(self) -> None:
        targets = (
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

        for target in targets:
            with self.subTest(target=target):
                decision = pytest_defaults.decide_default_parallelism(
                    args=(target,),
                    rootdir=REPO_ROOT,
                    markexpr="",
                )
                self.assertFalse(decision.enable_xdist)

    def test_shell_isolation_phase_uses_the_default_parallel_path(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=("tests/test_shell_isolation_phase.py",),
            rootdir=REPO_ROOT,
            markexpr="",
        )

        self.assertTrue(decision.enable_xdist)

    def test_heavy_parallelism_paths_follow_verification_registry(self) -> None:
        self.assertEqual(
            set(manifest.heavy_parallelism_test_paths()),
            pytest_defaults._heavy_parallelism_paths(),
        )
        self.assertNotIn(
            manifest.SHELL_ISOLATION_SPEC.test_path,
            manifest.heavy_parallelism_test_paths(),
        )

    def test_explicit_marker_expression_disables_automatic_defaults(self) -> None:
        decision = pytest_defaults.decide_default_parallelism(
            args=(),
            rootdir=REPO_ROOT,
            markexpr="gui",
        )

        self.assertFalse(decision.enable_xdist)

    def test_worker_count_prefers_physical_core_count(self) -> None:
        with patch("ea_node_editor.pytest_defaults.psutil.cpu_count", side_effect=[4, 8]):
            self.assertEqual(4, pytest_defaults.resolve_default_worker_count())

    def test_worker_count_falls_back_to_logical_when_physical_count_is_missing(self) -> None:
        with patch("ea_node_editor.pytest_defaults.psutil.cpu_count", side_effect=[None, 8]):
            self.assertEqual(8, pytest_defaults.resolve_default_worker_count())


if __name__ == "__main__":
    unittest.main()
