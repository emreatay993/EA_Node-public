from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

import pytest

from ea_node_editor.ui.shell import composition as shell_composition
from tests.graph_surface import (
    GraphSurfaceBoundaryContractTests,
    GraphSurfaceDefaultPropertyContractTests,
    GraphSurfaceFolderExplorerBridgeContractTests,
    GraphSurfaceInlineEditorContractTests,
    GraphSurfaceMediaAndScopeContractTests,
    GraphSurfaceWebBoardLoaderContractTests,
    GraphSurfaceWebPageLoaderContractTests,
)

# GraphSurfaceInputContractTests remains covered in tests.graph_surface; this entrypoint stays packet-focused.
pytestmark = pytest.mark.xdist_group("p03_graph_surface")


class _GraphSurfaceShellTestExecutionClient:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def subscribe(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def start_run(self, project_path: str, workspace_id: str, trigger=None) -> str:  # noqa: ANN001
        return ""

    def pause_run(self, run_id: str) -> None:
        return None

    def resume_run(self, run_id: str) -> None:
        return None

    def stop_run(self, run_id: str) -> None:
        return None

    def shutdown(self) -> None:
        self._callbacks.clear()


shell_composition.ProcessExecutionClient = _GraphSurfaceShellTestExecutionClient


class GraphSurfacePlotContractTests(unittest.TestCase):
    def test_plot_surface_declares_only_live_viewport_as_embedded_interactive_region(self) -> None:
        surface = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "plot"
            / "GraphPlotSurfaceBody.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("readonly property bool blocksHostInteraction: false", surface)
        self.assertIn("readonly property var embeddedInteractiveRects: surface.liveSurfaceActive", surface)
        self.assertIn("? [surface.liveSurfaceRect]", surface)
        self.assertIn(": []", surface)
        self.assertIn('objectName: "graphNodeViewerViewport"', surface)

    def test_plot_surface_toggles_host_service_without_claiming_title_or_resize_regions(self) -> None:
        surface = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "plot"
            / "GraphPlotSurfaceBody.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("set_embedded_interaction_active(currentNodeId, surface.liveSurfaceActive)", surface)
        self.assertIn("set_embedded_interaction_active(nodeId, false)", surface)
        self.assertNotIn("anchors.fill: surface", surface)
        self.assertNotIn("acceptedButtons: Qt.AllButtons", surface)


class _IsolatedGraphSurfaceShellWindowTest(unittest.TestCase):
    __test__ = False

    _TIMEOUT_SECONDS = 120

    def __init__(self, test_name: str) -> None:
        super().__init__("runTest")
        self._test_name = test_name

    def __str__(self) -> str:
        return (
            f"{self._test_name} "
            f"({GraphSurfaceMediaAndScopeContractTests.__module__}."
            f"{GraphSurfaceMediaAndScopeContractTests.__qualname__})"
        )

    def id(self) -> str:
        return (
            f"{GraphSurfaceMediaAndScopeContractTests.__module__}."
            f"{GraphSurfaceMediaAndScopeContractTests.__qualname__}.{self._test_name}"
        )

    def runTest(self) -> None:
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                f"{__name__}.GraphSurfaceMediaAndScopeContractTests.{self._test_name}",
                "-v",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self._TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            self.fail(
                f"{self.id()} failed in isolated subprocess with exit code "
                f"{result.returncode}:\n{result.stdout}"
            )


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):  # noqa: ANN001
    del tests, pattern
    suite = unittest.TestSuite()
    for test_case in (
        GraphSurfaceBoundaryContractTests,
        GraphSurfaceDefaultPropertyContractTests,
        GraphSurfaceFolderExplorerBridgeContractTests,
        GraphSurfaceInlineEditorContractTests,
        GraphSurfacePlotContractTests,
        GraphSurfaceWebBoardLoaderContractTests,
        GraphSurfaceWebPageLoaderContractTests,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))

    for test_name in loader.getTestCaseNames(GraphSurfaceMediaAndScopeContractTests):
        if test_name.startswith("test_shell_window_"):
            suite.addTest(_IsolatedGraphSurfaceShellWindowTest(test_name))
        else:
            suite.addTest(GraphSurfaceMediaAndScopeContractTests(test_name))
    return suite


__all__ = [
    "GraphSurfaceBoundaryContractTests",
    "GraphSurfaceDefaultPropertyContractTests",
    "GraphSurfaceFolderExplorerBridgeContractTests",
    "GraphSurfaceInlineEditorContractTests",
    "GraphSurfaceMediaAndScopeContractTests",
    "GraphSurfacePlotContractTests",
    "GraphSurfaceWebBoardLoaderContractTests",
    "GraphSurfaceWebPageLoaderContractTests",
]

if __name__ == "__main__":
    unittest.main()
