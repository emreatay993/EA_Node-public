from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ea_node_editor.benchmarks.tabular.adapters import available_format_adapters
from ea_node_editor.benchmarks.tabular.contracts import BenchmarkConfig
from ea_node_editor.benchmarks.tabular.runner import config_from_args, parse_args, run_benchmark_matrix


def _modules_available(*module_names: str) -> bool:
    return all(importlib.util.find_spec(module_name) is not None for module_name in module_names)


class TabularBenchmarkCliTests(unittest.TestCase):
    def test_default_headless_matrix_completes_without_failures_or_skips(self) -> None:
        if not _modules_available("numpy", "pandas", "polars", "pyarrow", "duckdb"):
            self.skipTest("Default tabular stack is not installed.")

        with tempfile.TemporaryDirectory() as temp_dir:
            args = parse_args(["--headless", "--out", temp_dir])
            config = config_from_args(args)
            results, paths = run_benchmark_matrix(config)

            self.assertTrue(results)
            self.assertEqual([result.error for result in results if not result.success], [])
            report = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["failure_count"], 0)
            self.assertEqual(report["summary"]["skipped_count"], 0)

    def test_parse_args_builds_decision_benchmark_config(self) -> None:
        args = parse_args(
            [
                "--headless",
                "--out",
                "artifacts/example",
                "--sizes",
                "small,medium",
                "--formats",
                "csv,parquet",
                "--backends",
                "pandas,duckdb",
                "--operations",
                "write,read,preview",
                "--reuse-datasets",
            ]
        )
        config = config_from_args(args)

        self.assertTrue(config.headless)
        self.assertEqual(config.output_dir, Path("artifacts/example"))
        self.assertEqual(config.sizes, ("small", "medium"))
        self.assertEqual(config.formats, ("csv", "parquet"))
        self.assertEqual(config.backends, ("pandas", "duckdb"))
        self.assertEqual(config.operations, ("write", "read", "preview"))
        self.assertTrue(config.reuse_datasets)

    def test_large_dataset_requires_explicit_allow_large(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = BenchmarkConfig(
                output_dir=Path(temp_dir),
                sizes=("large",),
                profiles=("mixed_table",),
                formats=("csv",),
                backends=("pandas",),
                operations=("write",),
                allow_large=False,
            )

            with self.assertRaisesRegex(ValueError, "--allow-large"):
                run_benchmark_matrix(config)

    def test_unsupported_format_profile_pairs_are_skipped_not_failed(self) -> None:
        if not _modules_available("numpy", "pandas"):
            self.skipTest("NumPy/pandas are not installed.")

        with tempfile.TemporaryDirectory() as temp_dir:
            config = BenchmarkConfig(
                output_dir=Path(temp_dir),
                sizes=("small",),
                profiles=("mixed_table",),
                formats=("npy",),
                backends=("numpy",),
                operations=("write", "read"),
            )
            results, paths = run_benchmark_matrix(config)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].skipped)
            self.assertFalse(results[0].success)
            report = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["failure_count"], 0)
            self.assertEqual(report["summary"]["skipped_count"], 1)

    def test_npy_headless_smoke_writes_reports_without_dataframe_stack(self) -> None:
        if not _modules_available("numpy"):
            self.skipTest("NumPy is not installed.")

        with tempfile.TemporaryDirectory() as temp_dir:
            config = BenchmarkConfig(
                output_dir=Path(temp_dir),
                sizes=("small",),
                profiles=("dense_numeric",),
                formats=("npy",),
                backends=("numpy",),
                operations=("write", "read", "schema", "preview"),
            )
            results, paths = run_benchmark_matrix(config)

            self.assertTrue(results)
            self.assertTrue(all(result.success for result in results))
            self.assertTrue(paths["json"].is_file())
            self.assertTrue(paths["markdown"].is_file())
            self.assertTrue(paths["csv"].is_file())
            report = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(report["kind"], "tabular_backend_format_benchmark")
            self.assertIn("packages", report["environment"])
            self.assertIn("rss_peak_bytes", report["results"][0])
            self.assertIn("rss_peak_delta_bytes", report["results"][0])
            csv_text = paths["csv"].read_text(encoding="utf-8")
            self.assertIn("rss_peak_bytes", csv_text.splitlines()[0])


class TabularFormatAdapterSmokeTests(unittest.TestCase):
    FORMAT_CASES = {
        "csv": ("mixed_table", "pandas", ("numpy", "pandas")),
        "tsv": ("mixed_table", "pandas", ("numpy", "pandas")),
        "txt": ("mixed_table", "pandas", ("numpy", "pandas")),
        "fixed_width_txt": ("mixed_table", "pandas", ("numpy", "pandas")),
        "jsonl": ("mixed_table", "pandas", ("numpy", "pandas")),
        "npy": ("dense_numeric", "numpy", ("numpy",)),
        "npz": ("dense_numeric", "numpy", ("numpy",)),
        "parquet": ("mixed_table", "pandas", ("numpy", "pandas", "pyarrow")),
        "feather": ("mixed_table", "pandas", ("numpy", "pandas", "pyarrow")),
        "hdf5": ("dense_numeric", "numpy", ("numpy", "h5py")),
        "xlsx": ("excel_like", "pandas", ("numpy", "pandas", "openpyxl")),
        "orc": ("dense_numeric", "arrow", ("numpy", "pandas", "pyarrow")),
    }

    def test_each_installed_format_adapter_handles_tiny_fixture(self) -> None:
        tested = 0
        for format_id, (profile, backend, modules) in self.FORMAT_CASES.items():
            with self.subTest(format_id=format_id):
                if not _modules_available(*modules):
                    continue
                with tempfile.TemporaryDirectory() as temp_dir:
                    config = BenchmarkConfig(
                        output_dir=Path(temp_dir),
                        sizes=("small",),
                        profiles=(profile,),
                        formats=(format_id,),
                        backends=(backend,),
                        operations=("write", "read", "schema", "preview"),
                        preview_rows=5,
                    )
                    results, _paths = run_benchmark_matrix(config)

                failures = [result.error for result in results if not result.success]
                self.assertEqual(failures, [])
                tested += 1
        self.assertGreater(tested, 0)

    def test_registry_exposes_planned_format_ids(self) -> None:
        adapters = available_format_adapters()

        self.assertEqual(
            set(adapters),
            {
                "csv",
                "tsv",
                "txt",
                "fixed_width_txt",
                "jsonl",
                "npy",
                "npz",
                "parquet",
                "feather",
                "hdf5",
                "xlsx",
                "orc",
            },
        )


class TabularWorkbenchGuiTests(unittest.TestCase):
    def test_qml_workbench_declares_results_and_preview_tables(self) -> None:
        import ea_node_editor.benchmarks.tabular.gui as gui

        self.assertIn("ApplicationWindow", gui._QML)
        self.assertGreaterEqual(gui._QML.count("TableView"), 2)
        self.assertIn("tabularController.resultsModel", gui._QML)
        self.assertIn("tabularController.previewModel", gui._QML)
        self.assertIn("runBenchmark", gui._QML)
        self.assertIn("BusyIndicator", gui._QML)
        self.assertGreaterEqual(gui._QML.count("HorizontalHeaderView"), 2)
        self.assertIn("Backend Decision", gui._QML)
        self.assertIn("Array Paths", gui._QML)
        self.assertIn("Format Smoke", gui._QML)
        self.assertIn("tabularController.setResultFilter", gui._QML)
        self.assertIn("No results yet", gui._QML)
        row = gui._result_row(
            {
                "dataset": {"profile": "mixed_table", "size": "small"},
                "format_id": "csv",
                "backend_id": "pandas",
                "operation": "read",
                "success": True,
                "skipped": False,
                "elapsed_ms": 1.0,
                "throughput_mb_s": 2.0,
                "rss_peak_delta_bytes": 3 * 1024 * 1024,
                "rss_delta_bytes": 1024 * 1024,
                "file_size_bytes": 1024**3,
                "error": "",
            }
        )
        self.assertEqual(row["peak_rss_mb"], "3.0")
        self.assertEqual(row["file_gib"], "1.000")

    @unittest.skipUnless(_modules_available("PyQt6"), "PyQt6 is not installed.")
    def test_qml_workbench_loads_offscreen_without_event_loop(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from ea_node_editor.benchmarks.tabular.gui import run_gui

        args = SimpleNamespace(
            out="artifacts/tabular_gui_test",
            sizes="small",
            profiles="mixed_table",
            formats="csv",
            backends="pandas",
            operations="write,read",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot_path = Path(temp_dir) / "workbench.png"
            self.assertEqual(run_gui(args, start_event_loop=False, screenshot_path=screenshot_path), 0)
            self.assertTrue(screenshot_path.is_file())

    @unittest.skipUnless(_modules_available("PyQt6", "numpy"), "PyQt6/NumPy are not installed.")
    def test_qml_workbench_auto_run_completes_tiny_benchmark(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from ea_node_editor.benchmarks.tabular.gui import run_gui

        with tempfile.TemporaryDirectory() as temp_dir:
            args = SimpleNamespace(
                out=temp_dir,
                sizes="small",
                profiles="dense_numeric",
                formats="npy",
                backends="numpy",
                operations="write,read,schema,preview",
            )

            self.assertEqual(
                run_gui(args, auto_run=True, quit_on_complete=True, quit_timeout_ms=20_000),
                0,
            )
