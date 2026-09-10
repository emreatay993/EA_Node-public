from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import graph_surface_pointer_regression as probe_runner


class GraphSurfaceProbeRunnerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        probe_runner._stop_qml_probe_worker()

    def test_worker_reuse_and_probe_state_reset(self) -> None:
        probe_runner._stop_qml_probe_worker()
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = Path(temp_dir) / "app-baseline.json"
            probe_runner.run_qml_probe(
                self,
                "dirty-state",
                f"""
                import json
                import os
                import tempfile
                from pathlib import Path
                from PyQt6.QtCore import Qt
                from PyQt6.QtQuick import QQuickWindow
                from PyQt6.QtWidgets import QApplication, QWidget

                leaked_global = True
                os.environ["COREX_QML_PROBE_LEAK"] = "yes"
                os.chdir(tempfile.gettempdir())
                app = QApplication.instance()
                Path({str(baseline_path)!r}).write_text(
                    json.dumps({{
                        "application_name": app.applicationName(),
                        "style_sheet": app.styleSheet(),
                    }}),
                    encoding="utf-8",
                )
                app.setQuitOnLastWindowClosed(False)
                app.setApplicationName("dirty probe application")
                app.setStyleSheet("QWidget {{ color: magenta; }}")
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                leaked_widget = QWidget()
                leaked_widget.show()
                leaked_quick_window = QQuickWindow()
                leaked_quick_window.show()
                """,
            )
            first_process = probe_runner._worker_process

            probe_runner.run_qml_probe(
                self,
                "clean-state",
                f"""
                import json
                import os
                from pathlib import Path
                from PyQt6.QtWidgets import QApplication

                baseline = json.loads(Path({str(baseline_path)!r}).read_text(encoding="utf-8"))
                assert "leaked_global" not in globals()
                assert Path.cwd() == Path({str(probe_runner._REPO_ROOT)!r})
                assert "COREX_QML_PROBE_LEAK" not in os.environ
                app = QApplication.instance()
                assert app.quitOnLastWindowClosed()
                assert app.applicationName() == baseline["application_name"]
                assert app.styleSheet() == baseline["style_sheet"]
                assert QApplication.overrideCursor() is None
                assert QApplication.topLevelWidgets() == []
                assert QApplication.topLevelWindows() == []
                """,
            )
            self.assertIs(probe_runner._worker_process, first_process)

    def test_assertion_diagnostics_discard_worker_and_log(self) -> None:
        probe_runner.run_qml_probe(self, "before-assertion", "assert True")
        log_path = Path(probe_runner._worker_log_path)

        with self.assertRaises(AssertionError) as raised:
            probe_runner.run_qml_probe(
                self,
                "diagnostic",
                """
                import os

                print("printed before failure")
                os.write(2, b"native descriptor marker\\n")
                raise AssertionError("diagnostic marker")
                """,
            )

        message = str(raised.exception)
        self.assertIn("diagnostic probe failed with exit code 1", message)
        self.assertIn("printed before failure", message)
        self.assertIn("native descriptor marker", message)
        self.assertIn("AssertionError: diagnostic marker", message)
        self.assertFalse(log_path.exists())

    def test_dead_worker_restarts_and_stop_deletes_native_log(self) -> None:
        probe_runner.run_qml_probe(self, "before-death", "assert True")
        dead_process = probe_runner._worker_process
        dead_log_path = Path(probe_runner._worker_log_path)

        with self.assertRaisesRegex(AssertionError, "dead probe failed with exit code 23"):
            probe_runner.run_qml_probe(self, "dead", "import os; os._exit(23)")
        self.assertFalse(dead_log_path.exists())

        probe_runner.run_qml_probe(self, "after-death", "assert True")
        self.assertIsNot(probe_runner._worker_process, dead_process)
        live_log_path = Path(probe_runner._worker_log_path)
        self.assertTrue(live_log_path.exists())
        probe_runner._stop_qml_probe_worker()
        probe_runner._stop_qml_probe_worker()
        self.assertFalse(live_log_path.exists())

    def test_cleanup_death_accepts_completed_probe_then_restarts(self) -> None:
        probe_runner.run_qml_probe(self, "before-cleanup-death", "assert True")
        dead_process = probe_runner._worker_process
        dead_log_path = Path(probe_runner._worker_log_path)

        probe_runner.run_qml_probe(
            self,
            "cleanup-death",
            """
            import os
            from tests import graph_surface_pointer_regression as worker_module

            def die_during_cleanup(*_args, **_kwargs):
                os._exit(23)

            worker_module._restore_probe_baseline = die_during_cleanup
            """,
        )

        self.assertIsNone(probe_runner._worker_process)
        self.assertFalse(dead_log_path.exists())
        probe_runner.run_qml_probe(self, "after-cleanup-death", "assert True")
        self.assertIsNot(probe_runner._worker_process, dead_process)

    def test_bootstrap_timeout_reports_state_and_discards_worker(self) -> None:
        probe_runner._stop_qml_probe_worker()
        monotonic_values = iter((100.0, 160.25))

        with (
            mock.patch.object(
                probe_runner.time,
                "monotonic",
                side_effect=lambda: next(monotonic_values, 160.25),
            ),
            mock.patch.object(probe_runner, "_next_worker_message", side_effect=TimeoutError),
            self.assertRaises(AssertionError) as raised,
        ):
            probe_runner.run_qml_probe(self, "bootstrap-timeout", "assert True")

        message = str(raised.exception)
        self.assertIn("bootstrap-timeout probe timed out after 60s (elapsed=60.250s)", message)
        self.assertIn("request=bootstrap state=starting", message)
        self.assertRegex(message, r"native log path: .+corex-qml-probe-.+\.log")
        self.assertIn("native log:", message)
        self.assertIsNone(probe_runner._worker_process)

    def test_request_timeout_reports_state_and_restarts_worker(self) -> None:
        probe_runner.run_qml_probe(self, "before-timeout", "assert True")
        timed_out_process = probe_runner._worker_process
        timed_out_log_path = Path(probe_runner._worker_log_path)
        monotonic_values = iter((100.0, 100.35))

        with (
            mock.patch.object(probe_runner, "_QML_PROBE_TIMEOUT_SECONDS", 0.2),
            mock.patch.object(
                probe_runner.time,
                "monotonic",
                side_effect=lambda: next(monotonic_values, 100.35),
            ),
            mock.patch.object(probe_runner, "_worker_log_contents", return_value="timeout native marker"),
            self.assertRaises(AssertionError) as raised,
        ):
            probe_runner.run_qml_probe(
                self,
                "request-timeout",
                "assert True",
            )

        message = str(raised.exception)
        self.assertIn("request-timeout probe timed out after 0.2s (elapsed=0.350s)", message)
        self.assertRegex(message, r"request=\d+ state=sent")
        self.assertIn(f"native log path: {timed_out_log_path}", message)
        self.assertIn("native log:\ntimeout native marker", message)
        self.assertIsNone(probe_runner._worker_process)
        self.assertFalse(timed_out_log_path.exists())

        probe_runner.run_qml_probe(self, "after-timeout", "assert True")
        self.assertIsNot(probe_runner._worker_process, timed_out_process)

    def test_discard_bounds_pending_windows_termination_without_kill(self) -> None:
        probe_runner._stop_qml_probe_worker()

        class PendingWindowsProcess:
            pid = 123

            def __init__(self) -> None:
                self.alive = True
                self.joins = []
                self.terminate_calls = 0
                self.kill_calls = 0

            def is_alive(self) -> bool:
                return self.alive

            def join(self, timeout=None) -> None:
                self.joins.append(timeout)
                if timeout is None:
                    self.alive = False

            def terminate(self) -> None:
                self.terminate_calls += 1
                error = PermissionError("termination already pending")
                error.winerror = 5
                raise error

            def kill(self) -> None:
                self.kill_calls += 1

        class FakeConnection:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        process = PendingWindowsProcess()
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "pending-worker.log"
            log_path.write_text("native output", encoding="utf-8")
            with (
                mock.patch.object(probe_runner.os, "name", "nt"),
                mock.patch.object(probe_runner, "_worker_process", process),
                mock.patch.object(probe_runner, "_worker_connection", connection),
                mock.patch.object(probe_runner, "_worker_log_path", log_path),
                mock.patch.object(probe_runner, "_worker_owner_pid", probe_runner.os.getpid()),
            ):
                probe_runner._discard_qml_probe_worker()

            self.assertEqual(process.joins, [2.0, 5.0])
            self.assertEqual(process.terminate_calls, 1)
            self.assertEqual(process.kill_calls, 0)
            self.assertTrue(connection.closed)
            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
