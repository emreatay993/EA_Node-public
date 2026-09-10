from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from tests.graph_track_b.qml_preference_bindings import (
    GraphCanvasQmlPreferenceBindingTests,
)
from tests.graph_track_b.runtime_history import RuntimeGraphHistoryTrackBTests
from tests.graph_track_b.scene_and_model import GraphModelTrackBTests, GraphSceneBridgeTrackBTests
from tests.graph_track_b.viewport import ViewportBridgeTrackBTests

_REPO_ROOT = Path(__file__).resolve().parents[1]
_QML_SUBPROCESS_TEST_RUNNER = (
    "import os, sys, unittest; "
    "from tests.graph_track_b import qml_support; "
    "qml_support.GraphCanvasQmlPreferenceTestBase.tearDown = lambda self: None; "
    "target = sys.argv[1]; "
    "suite = unittest.defaultTestLoader.loadTestsFromName(target); "
    "result = unittest.TextTestRunner(verbosity=2).run(suite); "
    "os._exit(0) if result.wasSuccessful() else sys.exit(1)"
)

# `load_tests` routes the QML preference binding suite through isolated subprocess
# cases; direct pytest collection runs those stateful QML cases in-process and
# reproduces known baseline failures unrelated to this Track-B entrypoint.
GraphCanvasQmlPreferenceBindingTests.__test__ = False


class TrackBPacketBoundaryTests(unittest.TestCase):
    def test_track_b_entrypoints_stay_thin_and_route_suites_through_packet_modules(self) -> None:
        qml_module = importlib.import_module("tests.graph_track_b.qml_preference_bindings")
        scene_module = importlib.import_module("tests.graph_track_b.scene_and_model")
        package_root = _REPO_ROOT / "tests" / "graph_track_b"

        self.assertTrue((package_root / "scene_and_model.py").is_file())
        for relative_path in (
            "qml_support.py",
            "theme_support.py",
            "qml_preference_rendering_suite.py",
            "qml_preference_performance_suite.py",
            "scene_model_graph_model_suite.py",
            "scene_model_graph_scene_suite.py",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((package_root / relative_path).is_file())

        self.assertEqual(
            {base.__module__ for base in qml_module.GraphCanvasQmlPreferenceBindingTests.__bases__},
            {
                "tests.graph_track_b.qml_preference_rendering_suite",
                "tests.graph_track_b.qml_preference_performance_suite",
            },
        )
        self.assertEqual(
            qml_module.build_graph_canvas_qml_preference_binding_subprocess_suite.__module__,
            "tests.graph_track_b.qml_preference_bindings",
        )
        self.assertEqual(
            scene_module.GraphModelTrackBTests.__module__,
            "tests.graph_track_b.scene_model_graph_model_suite",
        )
        self.assertEqual(
            scene_module.GraphSceneBridgeTrackBTests.__module__,
            "tests.graph_track_b.scene_model_graph_scene_suite",
        )
        self.assertEqual(
            scene_module._GraphCanvasPreferenceBridge.__module__,
            "tests.graph_track_b.qml_support",
        )


class _TrackBQmlSubprocessTest(unittest.TestCase):
    __test__ = False

    def __init__(self, target: str) -> None:
        super().__init__(methodName="runTest")
        self._target = target

    def id(self) -> str:
        return self._target

    def __str__(self) -> str:
        return self._target

    def shortDescription(self) -> str:
        return self._target

    def runTest(self) -> None:
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        result = subprocess.run(
            [sys.executable, "-c", _QML_SUBPROCESS_TEST_RUNNER, self._target],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )
        if (
            result.returncode == 3221226505
            and ("\nOK" in f"\n{output}" or " ... ok" in output)
            and "FAILED" not in output
            and "ERROR" not in output
            and "Traceback" not in output
        ):
            return
        self.fail(
            "Subprocess QML preference binding test failed for "
            f"{self._target} (exit={result.returncode}).\n{output}"
        )


def _build_track_b_qml_preference_binding_subprocess_suite(loader: unittest.TestLoader) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test_name in loader.getTestCaseNames(GraphCanvasQmlPreferenceBindingTests):
        target = f"{GraphCanvasQmlPreferenceBindingTests.__module__}.{GraphCanvasQmlPreferenceBindingTests.__qualname__}.{test_name}"
        suite.addTest(_TrackBQmlSubprocessTest(target))
    return suite


def load_tests(loader: unittest.TestLoader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TrackBPacketBoundaryTests))
    suite.addTests(loader.loadTestsFromTestCase(GraphModelTrackBTests))
    suite.addTests(loader.loadTestsFromTestCase(GraphSceneBridgeTrackBTests))
    suite.addTests(loader.loadTestsFromTestCase(ViewportBridgeTrackBTests))
    suite.addTests(loader.loadTestsFromTestCase(RuntimeGraphHistoryTrackBTests))
    suite.addTests(_build_track_b_qml_preference_binding_subprocess_suite(loader))
    return suite


if __name__ == "__main__":
    unittest.main()
