from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class StartupImportProfileTests(unittest.TestCase):
    def _run_python(
        self,
        script: str,
        *,
        env_updates: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        if env_updates:
            env.update(env_updates)
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_app_import_is_side_effect_light_and_meets_median_gate(self) -> None:
        script = """
import json
import sys
import time

started = time.perf_counter()
import ea_node_editor.app as app
elapsed_ms = (time.perf_counter() - started) * 1000.0
forbidden = {
    "PyQt6.QtCore",
    "ea_node_editor.addons.tabular_data.loader_cache_service",
    "ea_node_editor.app_preferences",
    "ea_node_editor.ui.shell.composition",
    "ea_node_editor.ui.splash",
    "pyarrow",
}
print(json.dumps({
    "elapsed_ms": elapsed_ms,
    "loaded_forbidden": sorted(forbidden.intersection(sys.modules)),
    "has_app_stylesheet": hasattr(app, "APP_STYLESHEET"),
}))
"""
        samples: list[float] = []
        for _ in range(3):
            result = self._run_python(script)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            samples.append(float(payload["elapsed_ms"]))
            self.assertEqual(payload["loaded_forbidden"], [])
            self.assertFalse(payload["has_app_stylesheet"])

        self.assertLessEqual(statistics.median(samples), 1000.0)

    def test_project_file_owners_keep_notebook_dependencies_lazy(self) -> None:
        script = """
import json
import sys

import ea_node_editor.ui.shell.controllers.project_session_controller
import ea_node_editor.ui.shell.controllers.project_session_services_support.project_files_service
import ea_node_editor.ui.shell.host_presenter

print(json.dumps({
    "nbformat_loaded": "nbformat" in sys.modules,
    "notebook_files_loaded": "ea_node_editor.jupyter_host.notebook_files" in sys.modules,
}))
"""
        result = self._run_python(script)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "nbformat_loaded": False,
                "notebook_files_loaded": False,
            },
        )

    def test_both_qml_hosts_report_set_source_phase(self) -> None:
        script = """
import json
from ea_node_editor.ui_qml.qml_host_factory import QQuickViewContainerHost, QQuickWidgetHost

calls = []

class Target:
    def __init__(self, name):
        self.name = name

    def setSource(self, url):
        calls.append([self.name, url])

widget_host = object.__new__(QQuickWidgetHost)
widget_host.widget = Target("widget")
widget_host.set_source("widget.qml")

view_host = object.__new__(QQuickViewContainerHost)
view_host.view = Target("view")
view_host.set_source("view.qml")

print(json.dumps(calls))
"""
        result = self._run_python(
            script,
            env_updates={"EA_PROFILE_STARTUP": "1", "QT_QPA_PLATFORM": "offscreen"},
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertEqual(
            json.loads(result.stdout),
            [["widget", "widget.qml"], ["view", "view.qml"]],
        )
        self.assertEqual(result.stderr.count("[startup] qml.set_source:"), 2)


if __name__ == "__main__":
    unittest.main()
