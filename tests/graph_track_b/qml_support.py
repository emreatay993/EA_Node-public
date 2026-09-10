from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PyQt6.QtCore import QPoint, QObject, QMetaObject, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.decorators import in_port, node_type, out_port
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from tests.graph_track_b.theme_support import GraphThemeBridge, ThemeBridge
from tests.qt_wait import wait_for_condition_or_raise

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBPROCESS_TEST_RUNNER = (
    'import sys, unittest; '
    'target = sys.argv[1]; '
    'suite = unittest.defaultTestLoader.loadTestsFromName(target); '
    'result = unittest.TextTestRunner(verbosity=2).run(suite); '
    'sys.exit(0 if result.wasSuccessful() else 1)'
)
_GRAPH_CANVAS_QML_PATH = (
    Path(__file__).resolve().parents[2] / 'ea_node_editor' / 'ui_qml' / 'components' / 'GraphCanvas.qml'
)
_NODE_CARD_QML_PATH = (
    Path(__file__).resolve().parents[2]
    / 'ea_node_editor'
    / 'ui_qml'
    / 'components'
    / 'graph'
    / 'NodeCard.qml'
)
_EDGE_LAYER_QML_PATH = _GRAPH_CANVAS_QML_PATH.parent / 'graph' / 'EdgeLayer.qml'


def _qml_error_text(errors) -> str:  # noqa: ANN001
    return "\n".join(error.toString() for error in errors)


def _named_child_items(root: QObject, object_name: str) -> list[QObject]:
    matches: list[QObject] = []

    def _walk(item: QObject | None) -> None:
        if item is None:
            return
        if item.objectName() == object_name:
            matches.append(item)
        child_items = getattr(item, 'childItems', None)
        if callable(child_items):
            for child in child_items():
                _walk(child)

    _walk(root)
    return matches




@node_type(
    type_id="tests.edge_crossing_pipe_probe_node",
    display_name="Edge Crossing Pipe Probe",
    category="Tests",
    icon="branch",
    ports=(
        in_port("flow_in", kind="flow"),
        out_port("flow_out", kind="flow"),
    ),
    properties=(),
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="sticky_note",
)
class _EdgeCrossingPipeProbeNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})

def _build_edge_crossing_pipe_registry() -> NodeRegistry:
    registry = build_default_registry()
    registry.register(_EdgeCrossingPipeProbeNode)
    return registry


class _GraphCanvasPreferenceBridge(QObject):
    graphics_preferences_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._graphics_show_grid = True
        self._graphics_grid_style = "lines"
        self._graphics_show_minimap = True
        self._graphics_show_canvas_options_button = True
        self._graphics_show_port_labels = True
        self._graphics_node_elapsed_time_unit = "seconds"
        self._graphics_node_elapsed_time_visibility = "always"
        self._graphics_node_floating_toolbar_opens_on_hover = False

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_grid(self) -> bool:
        return bool(self._graphics_show_grid)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_grid_style(self) -> str:
        return str(self._graphics_grid_style)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_minimap(self) -> bool:
        return bool(self._graphics_show_minimap)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_canvas_options_button(self) -> bool:
        return bool(self._graphics_show_canvas_options_button)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_port_labels(self) -> bool:
        return bool(self._graphics_show_port_labels)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_node_elapsed_time_unit(self) -> str:
        return str(self._graphics_node_elapsed_time_unit)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_node_elapsed_time_visibility(self) -> str:
        return str(self._graphics_node_elapsed_time_visibility)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
        return bool(self._graphics_node_floating_toolbar_opens_on_hover)

    def set_graphics_show_grid_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_show_grid == normalized:
            return
        self._graphics_show_grid = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_grid_style_value(self, value: str) -> None:
        normalized = str(value or "lines").strip().lower()
        if normalized not in {"lines", "points"}:
            normalized = "lines"
        if self._graphics_grid_style == normalized:
            return
        self._graphics_grid_style = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_show_minimap_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_show_minimap == normalized:
            return
        self._graphics_show_minimap = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_show_canvas_options_button_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_show_canvas_options_button == normalized:
            return
        self._graphics_show_canvas_options_button = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_show_port_labels_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_show_port_labels == normalized:
            return
        self._graphics_show_port_labels = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_elapsed_time_unit_value(self, value: str) -> None:
        normalized = str(value or "seconds").strip().lower()
        if normalized not in {"seconds", "milliseconds"}:
            normalized = "seconds"
        if self._graphics_node_elapsed_time_unit == normalized:
            return
        self._graphics_node_elapsed_time_unit = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_elapsed_time_unit(self, value: str) -> None:
        self.set_graphics_node_elapsed_time_unit_value(value)

    def set_graphics_node_elapsed_time_visibility_value(self, value: str) -> None:
        normalized = str(value or "always").strip().lower()
        if normalized not in {"off", "during_run", "always"}:
            normalized = "always"
        if self._graphics_node_elapsed_time_visibility == normalized:
            return
        self._graphics_node_elapsed_time_visibility = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_elapsed_time_visibility(self, value: str) -> None:
        self.set_graphics_node_elapsed_time_visibility_value(value)

class _GraphCanvasRenderingPreferenceBridge(_GraphCanvasPreferenceBridge):
    def __init__(self) -> None:
        super().__init__()
        self._graphics_edge_crossing_style = "none"
        self._graphics_node_shadow = True
        self._graphics_shadow_strength = 70
        self._graphics_shadow_softness = 50
        self._graphics_shadow_offset = 4

    @property
    def graphics_node_shadow(self) -> bool:
        return bool(self._graphics_node_shadow)

    @property
    def graphics_shadow_strength(self) -> int:
        return int(self._graphics_shadow_strength)

    @property
    def graphics_shadow_softness(self) -> int:
        return int(self._graphics_shadow_softness)

    @property
    def graphics_shadow_offset(self) -> int:
        return int(self._graphics_shadow_offset)

    @property
    def graphics_edge_crossing_style(self) -> str:
        return str(self._graphics_edge_crossing_style)

    def set_graphics_shadow_softness_value(self, value: int) -> None:
        normalized = int(value)
        if self._graphics_shadow_softness == normalized:
            return
        self._graphics_shadow_softness = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_edge_crossing_style_value(self, value: str) -> None:
        normalized = str(value or "none").strip().lower()
        if normalized not in {"none", "gap_break"}:
            normalized = "none"
        if self._graphics_edge_crossing_style == normalized:
            return
        self._graphics_edge_crossing_style = normalized
        self.graphics_preferences_changed.emit()


class _GraphCanvasSessionBridge(QObject):
    snap_to_grid_changed = pyqtSignal()
    snap_grid_size = 20.0

    def __init__(self, graphics_source: _GraphCanvasPreferenceBridge) -> None:
        super().__init__()
        self._graphics_source = graphics_source
        self.graphics_minimap_expanded = True
        self.selected_run_preview_before_run = False
        self.snap_to_grid_enabled = False
        self.minimap_update_history: list[bool] = []

    def set_graphics_minimap_expanded_value(self, value: bool) -> None:
        self.set_graphics_minimap_expanded(value)

    def set_snap_to_grid_enabled_value(self, value: bool) -> None:
        self.set_snap_to_grid_enabled(value)

    def set_snap_to_grid_enabled(self, value: bool) -> None:
        normalized = bool(value)
        if self.snap_to_grid_enabled == normalized:
            return
        self.snap_to_grid_enabled = normalized
        self.snap_to_grid_changed.emit()

    @pyqtSlot(bool)
    def set_graphics_minimap_expanded(self, expanded: bool) -> None:
        normalized = bool(expanded)
        self.minimap_update_history.append(normalized)
        if self.graphics_minimap_expanded == normalized:
            return
        self.graphics_minimap_expanded = normalized
        self._graphics_source.graphics_preferences_changed.emit()

    def set_selected_run_preview_before_run(self, enabled: bool) -> None:
        normalized = bool(enabled)
        if self.selected_run_preview_before_run == normalized:
            return
        self.selected_run_preview_before_run = normalized
        self._graphics_source.graphics_preferences_changed.emit()

class _GraphCanvasShellContext(QObject):
    def __init__(self, theme_bridge: ThemeBridge, graph_theme_bridge: GraphThemeBridge) -> None:
        super().__init__()
        self._theme_bridge = theme_bridge
        self._graph_theme_bridge = graph_theme_bridge

    @pyqtProperty(QObject, constant=True)
    def themeBridge(self) -> QObject:
        return self._theme_bridge

    @pyqtProperty(QObject, constant=True)
    def graphThemeBridge(self) -> QObject:
        return self._graph_theme_bridge


class GraphCanvasQmlPreferenceTestBase(unittest.TestCase):
    __test__ = False

    def _create_canvas(self, initial_properties: dict[str, object]) -> QObject:
        if hasattr(self.component, "createWithInitialProperties"):
            canvas = self.component.createWithInitialProperties(initial_properties)
        else:
            canvas = self.component.create()
            for key, value in initial_properties.items():
                canvas.setProperty(key, value)
        if canvas is None:
            errors = _qml_error_text(self.component.errors())
            self.fail(f"Failed to instantiate GraphCanvas.qml:\n{errors}")
        self.app.processEvents()
        return canvas

    def _create_edge_layer(self, initial_properties: dict[str, object] | None = None) -> QObject:
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(_EDGE_LAYER_QML_PATH)))
        if component.status() != QQmlComponent.Status.Ready:
            errors = _qml_error_text(component.errors())
            self.fail(f"Failed to load EdgeLayer.qml:\n{errors}")

        properties = {"width": 1280.0, "height": 720.0}
        if initial_properties:
            properties.update(initial_properties)

        if hasattr(component, "createWithInitialProperties"):
            edge_layer = component.createWithInitialProperties(properties)
        else:
            edge_layer = component.create()
            if edge_layer is not None:
                for key, value in properties.items():
                    edge_layer.setProperty(key, value)
        if edge_layer is None:
            errors = _qml_error_text(component.errors())
            self.fail(f"Failed to instantiate EdgeLayer.qml:\n{errors}")
        self.app.processEvents()
        return edge_layer

    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.engine = QQmlEngine()
        self.theme_bridge = ThemeBridge(theme_id="stitch_dark")
        self.graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_dark")
        self.shell_context = _GraphCanvasShellContext(self.theme_bridge, self.graph_theme_bridge)
        self.engine.rootContext().setContextProperty("themeBridge", self.theme_bridge)
        self.engine.rootContext().setContextProperty("graphThemeBridge", self.graph_theme_bridge)
        self.engine.rootContext().setContextProperty("shellContext", self.shell_context)
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(_GRAPH_CANVAS_QML_PATH)))
        if self.component.status() != QQmlComponent.Status.Ready:
            errors = _qml_error_text(self.component.errors())
            self.fail(f"Failed to load GraphCanvas.qml:\n{errors}")
        self.bridge = _GraphCanvasRenderingPreferenceBridge()
        self.canvas_source = _GraphCanvasSessionBridge(self.bridge)
        self.view = ViewportBridge()
        self.view.set_viewport_size(1280.0, 720.0)
        self.canvas_state_bridge = GraphCanvasStateBridge(
            session_state=self.canvas_source,  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(self.canvas_source, "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(self.canvas_source, "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.canvas_command_bridge = GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=self.bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": self.canvas_state_bridge,
                "canvasCommandBridge": self.canvas_command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

    def tearDown(self) -> None:
        if self.canvas is not None:
            self.canvas.deleteLater()
        self.app.processEvents()
        self.engine.deleteLater()
        self.app.processEvents()

class _SubprocessGraphCanvasQmlPreferenceBindingTest(unittest.TestCase):
        __test__ = False

        def __init__(self, target: str) -> None:
            super().__init__(methodName='runTest')
            self._target = target

        def id(self) -> str:
            return self._target

        def __str__(self) -> str:
            return self._target

        def shortDescription(self) -> str:
            return self._target

        def runTest(self) -> None:
            env = os.environ.copy()
            env.setdefault('QT_QPA_PLATFORM', 'offscreen')
            result = subprocess.run(
                [sys.executable, '-c', _SUBPROCESS_TEST_RUNNER, self._target],
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
            self.fail(
                'Subprocess QML preference binding test failed for '
                f'{self._target} (exit={result.returncode}).\n{output}'
            )


def build_graph_canvas_qml_preference_subprocess_suite(
    loader: unittest.TestLoader,
    case_type: type[unittest.TestCase],
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test_name in loader.getTestCaseNames(case_type):
        target = f"{case_type.__module__}.{case_type.__qualname__}.{test_name}"
        suite.addTest(_SubprocessGraphCanvasQmlPreferenceBindingTest(target))
    return suite


__all__ = [
    "GraphCanvasCommandBridge",
    "GraphCanvasQmlPreferenceTestBase",
    "GraphCanvasStateBridge",
    "GraphModel",
    "GraphSceneBridge",
    "GraphThemeBridge",
    "NodeRegistry",
    "NodeResult",
    "QApplication",
    "QMetaObject",
    "QObject",
    "QPoint",
    "QQmlComponent",
    "QQmlEngine",
    "QQuickWindow",
    "QTest",
    "Qt",
    "QUrl",
    "ThemeBridge",
    "ViewportBridge",
    "_EDGE_LAYER_QML_PATH",
    "_GRAPH_CANVAS_QML_PATH",
    "_NODE_CARD_QML_PATH",
    "_GraphCanvasRenderingPreferenceBridge",
    "_GraphCanvasPreferenceBridge",
    "_GraphCanvasSessionBridge",
    "_build_edge_crossing_pipe_registry",
    "_named_child_items",
    "build_graph_canvas_qml_preference_subprocess_suite",
    "pyqtProperty",
    "pyqtSignal",
    "pyqtSlot",
    "wait_for_condition_or_raise",
]
