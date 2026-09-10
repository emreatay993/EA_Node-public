from __future__ import annotations

import gc
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PyQt6.QtCore import QEvent, QUrl

from ea_node_editor.graph.file_issue_state import encode_file_repair_request
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from tests.conftest import ShellTestEnvironment
from tests.graph_surface_pointer_regression import (
    QML_POINTER_REGRESSION_HELPERS,
    graph_surface_pointer_audit_failures,
    run_qml_probe,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

def _flush_qt_events(app) -> None:  # noqa: ANN001
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

def _destroy_shell_window(window, app) -> None:  # noqa: ANN001
    if window is None:
        return
    for timer_name in ("metrics_timer", "graph_hint_timer", "autosave_timer"):
        timer = getattr(window, timer_name, None)
        if timer is not None:
            timer.stop()
    window.close()
    quick_widget = getattr(window, "quick_widget", None)
    if quick_widget is not None:
        window.takeCentralWidget()
        quick_widget.setSource(QUrl())
        quick_widget.hide()
        quick_widget.deleteLater()
        window.quick_widget = None
    window.deleteLater()
    _flush_qt_events(app)
    gc.collect()

class _RenderQualityPayloadPlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()

class PassiveGraphSurfaceHostTestBase(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        self._run_qml_probe_with_retry(label, body)

    def _run_qml_probe_once(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            import importlib.util
            import os
            import sys
            import types
            from pathlib import Path

            os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

            from PyQt6.QtCore import QEvent, QObject, QMetaObject, Qt, QUrl, pyqtProperty, pyqtSlot
            from PyQt6.QtGui import QKeyEvent
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtQuick import QQuickItem
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui.media_preview_provider import (
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider,
            )

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())

            repo_root = Path.cwd()
            components_dir = repo_root / "ea_node_editor" / "ui_qml" / "components"
            graph_canvas_qml_path = components_dir / "GraphCanvas.qml"
            graph_node_host_qml_path = components_dir / "graph" / "GraphNodeHost.qml"
            node_card_qml_path = components_dir / "graph" / "NodeCard.qml"

            def ensure_namespace(package_name, package_dir):
                if package_name in sys.modules:
                    return
                package = types.ModuleType(package_name)
                package.__path__ = [str(repo_root / package_dir)]
                sys.modules[package_name] = package

            def load_module(module_name, relative_path):
                if module_name in sys.modules:
                    return sys.modules[module_name]
                module_path = repo_root / relative_path
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                assert spec is not None and spec.loader is not None
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                return module

            def load_package(package_name, relative_dir):
                if package_name in sys.modules:
                    return sys.modules[package_name]
                package_dir = repo_root / relative_dir
                spec = importlib.util.spec_from_file_location(
                    package_name,
                    package_dir / "__init__.py",
                    submodule_search_locations=[str(package_dir)],
                )
                package = importlib.util.module_from_spec(spec)
                assert spec is not None and spec.loader is not None
                sys.modules[package_name] = package
                spec.loader.exec_module(package)
                return package

            ensure_namespace("ea_node_editor.graph", Path("ea_node_editor/graph"))
            ensure_namespace("ea_node_editor.ui_qml", Path("ea_node_editor/ui_qml"))

            GraphModel = load_module(
                "ea_node_editor.graph.model",
                Path("ea_node_editor/graph/model.py"),
            ).GraphModel
            GraphSceneBridge = load_module(
                "ea_node_editor.ui_qml.graph_scene_bridge",
                Path("ea_node_editor/ui_qml/graph_scene_bridge.py"),
            ).GraphSceneBridge
            GraphCanvasStateBridge = load_package(
                "ea_node_editor.ui_qml.graph_canvas_state",
                Path("ea_node_editor/ui_qml/graph_canvas_state"),
            ).GraphCanvasStateBridge
            GraphCanvasCommandBridge = load_package(
                "ea_node_editor.ui_qml.graph_canvas_command",
                Path("ea_node_editor/ui_qml/graph_canvas_command"),
            ).GraphCanvasCommandBridge
            ViewportBridge = load_module(
                "ea_node_editor.ui_qml.viewport_bridge",
                Path("ea_node_editor/ui_qml/viewport_bridge.py"),
            ).ViewportBridge
            load_module(
                "ea_node_editor.ui_qml.tabular_preview_table_model",
                Path("ea_node_editor/ui_qml/tabular_preview_table_model.py"),
            ).register_qml_types()

            from ea_node_editor.nodes.bootstrap import build_default_registry
            from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values

            class ThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "app_bg": "#151821",
                        "border": "#3a4355",
                        "canvas_bg": "#151821",
                        "canvas_major_grid": "#2f3644",
                        "canvas_minor_grid": "#222833",
                        "group_title_fg": "#d5dbea",
                        "hover": "#33405c",
                        "input_bg": "#18202d",
                        "input_border": "#465066",
                        "input_fg": "#eef3ff",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_fg": "#eef3ff",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class GraphThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def node_palette(self):
                    return {
                        "card_bg": "#1f2431",
                        "card_border": "#414a5d",
                        "card_selected_border": "#5da9ff",
                        "header_bg": "#252c3c",
                        "header_fg": "#eef3ff",
                        "inline_driven_fg": "#aeb8ce",
                        "inline_input_bg": "#18202d",
                        "inline_input_border": "#465066",
                        "inline_input_fg": "#eef3ff",
                        "inline_label_fg": "#d5dbea",
                        "inline_row_bg": "#202635",
                        "inline_row_border": "#3a4355",
                        "port_interactive_border": "#8ca0c7",
                        "port_interactive_fill": "#101521",
                        "port_interactive_ring_border": "#7fb2ff",
                        "port_interactive_ring_fill": "#1a2233",
                        "port_label_fg": "#d5dbea",
                        "scope_badge_bg": "#1f3657",
                        "scope_badge_border": "#4c7bc0",
                        "scope_badge_fg": "#eef3ff",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def port_kind_palette(self):
                    return {
                        "data": "#7AA8FF",
                        "flow": "#67D487",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def edge_palette(self):
                    return {
                        "invalid_drag_stroke": "#D94F4F",
                        "preview_stroke": "#95a0b8",
                        "selected_stroke": "#5da9ff",
                        "valid_drag_stroke": "#67D487",
                    }

            class ShellContextStub(QObject):
                def __init__(self, theme_bridge, graph_theme_bridge):
                    super().__init__()
                    self._theme_bridge = theme_bridge
                    self._graph_theme_bridge = graph_theme_bridge
                    self._addon_manager_bridge = None

                @pyqtProperty(QObject, constant=True)
                def themeBridge(self):
                    return self._theme_bridge

                @pyqtProperty(QObject, constant=True)
                def graphThemeBridge(self):
                    return self._graph_theme_bridge

                @pyqtProperty(QObject, constant=True)
                def addonManagerBridge(self):
                    return self._addon_manager_bridge

            theme_bridge = ThemeBridgeStub()
            graph_theme_bridge = GraphThemeBridgeStub()
            shell_context = ShellContextStub(theme_bridge, graph_theme_bridge)
            engine.rootContext().setContextProperty("themeBridge", theme_bridge)
            engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
            engine.rootContext().setContextProperty("shellContext", shell_context)

            class CanvasShellSource:
                def __init__(self, values=None):
                    for key, value in dict(values or {}).items():
                        setattr(self, str(key), value)

            def _graph_canvas_initial_properties(path, initial_properties):
                normalized = dict(initial_properties)
                if path != graph_canvas_qml_path:
                    return normalized, []
                if "canvasStateBridge" in normalized or "canvasCommandBridge" in normalized:
                    refs = [
                        normalized.get("canvasStateBridge"),
                        normalized.get("canvasCommandBridge"),
                    ]
                    return normalized, [ref for ref in refs if ref is not None]

                scene_bridge = normalized.pop("sceneBridge", None)
                view_bridge = normalized.pop("viewBridge", None)
                shell_source = normalized.pop("mainWindowBridge", None)
                if isinstance(shell_source, dict):
                    shell_source = CanvasShellSource(shell_source)

                state_bridge = GraphCanvasStateBridge(
                    session_state=shell_source,
                    snap_to_grid_changed_signal=getattr(shell_source, "snap_to_grid_changed", None),
                    snap_grid_size=float(getattr(shell_source, "snap_grid_size", 20.0)),
                    app_preferences_source=shell_source,
                    graphics_source=shell_source,
                    scene_bridge=scene_bridge,
                    view_bridge=view_bridge,
                )
                command_bridge = GraphCanvasCommandBridge(
                    search_scope_controller=shell_source,
                    app_preferences_source=shell_source,
                    run_controller=shell_source,
                    inspector_source=shell_source,
                    library_source=shell_source,
                    workspace_edit_controller=shell_source,
                    workspace_drop_connect_controller=shell_source,
                    scene_bridge=scene_bridge,
                    view_bridge=view_bridge,
                )
                normalized["canvasStateBridge"] = state_bridge
                normalized["canvasCommandBridge"] = command_bridge
                refs = [state_bridge, command_bridge]
                if shell_source is not None:
                    refs.append(shell_source)
                return normalized, refs

            def create_component(path, initial_properties):
                initial_properties, persistent_refs = _graph_canvas_initial_properties(path, initial_properties)
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load {path.name}:\\n{errors}")
                if hasattr(component, "createWithInitialProperties"):
                    obj = component.createWithInitialProperties(initial_properties)
                else:
                    obj = component.create()
                    for key, value in initial_properties.items():
                        obj.setProperty(key, value)
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate {path.name}:\\n{errors}")
                if persistent_refs:
                    setattr(obj, "_graph_canvas_refs", persistent_refs)
                app.processEvents()
                return obj

            class PassiveSurfaceCanvasItem(QQuickItem):
                def __init__(self):
                    super().__init__()
                    self.requested_crop_node_id = ""
                    self.last_committed_node_id = ""
                    self.last_committed_properties = None

                @pyqtSlot(str, result=bool)
                def requestNodeSurfaceCropEdit(self, node_id):
                    self.requested_crop_node_id = str(node_id)
                    return True

                @pyqtSlot(str, result=bool)
                def consumePendingNodeSurfaceAction(self, _node_id):
                    return False

                @pyqtSlot(str, "QVariantMap", result=bool)
                def commitNodeSurfaceProperties(self, node_id, properties):
                    self.last_committed_node_id = str(node_id)
                    self.last_committed_properties = dict(properties or {})
                    return True

                @pyqtSlot(str, str, "QVariant", result=bool)
                def commitNodeSurfaceProperty(self, node_id, key, value):
                    self.last_committed_node_id = str(node_id)
                    self.last_committed_properties = {str(key): value}
                    return True

                @pyqtSlot(int, result=bool)
                def setNodeSurfaceCursorShape(self, _cursor_shape):
                    return True

                @pyqtSlot(result=bool)
                def clearNodeSurfaceCursorShape(self):
                    return True

                @pyqtSlot(str, "QVariant", result="QVariantMap")
                def describeNodeSurfacePdfPreview(self, _source, _page_number):
                    return {}

            def create_surface_canvas_item():
                return PassiveSurfaceCanvasItem()

            def node_payload(surface_family="standard", surface_variant=""):
                return {
                    "node_id": "node_surface_host_test",
                    "type_id": "core.logger",
                    "title": "Logger",
                    "x": 120.0,
                    "y": 120.0,
                    "width": 210.0,
                    "height": 88.0,
                    "accent": "#2F89FF",
                    "collapsed": False,
                    "selected": False,
                    "runtime_behavior": "active",
                    "surface_family": surface_family,
                    "surface_variant": surface_variant,
                    "surface_spec": surface_spec_payload_for_values(
                        type_id="core.logger",
                        family=surface_family,
                        variant=surface_variant,
                    ),
                    "surface_metrics": {
                        "default_width": 210.0,
                        "default_height": 88.0,
                        "min_width": 120.0,
                        "min_height": 50.0,
                        "collapsed_width": 130.0,
                        "collapsed_height": 36.0,
                        "header_height": 24.0,
                        "header_top_margin": 4.0,
                        "body_top": 30.0,
                        "body_height": 30.0,
                        "port_top": 60.0,
                        "port_height": 18.0,
                        "port_center_offset": 6.0,
                        "port_side_margin": 8.0,
                        "port_dot_radius": 5.0,
                        "resize_handle_size": 16.0,
                    },
                    "visual_style": {},
                    "can_enter_scope": False,
                    "ports": [
                        {
                            "key": "payload",
                            "label": "Payload",
                            "direction": "in",
                            "kind": "data",
                            "data_type": "any",
                            "connected": False,
                        },
                        {
                            "key": "result",
                            "label": "Result",
                            "direction": "out",
                            "kind": "data",
                            "data_type": "any",
                            "connected": False,
                        },
                    ],
                    "inline_properties": [
                        {
                            "key": "message",
                            "label": "Message",
                            "inline_editor": "text",
                            "value": "log message",
                            "overridden_by_input": False,
                            "input_port_label": "message",
                        }
                    ],
                }

            def flowchart_payload(
                variant,
                *,
                title="Decision",
                display_name="Decision",
                collapsed=False,
                properties=None,
                visual_style=None,
            ):
                payload = node_payload(surface_family="flowchart", surface_variant=variant)
                payload["runtime_behavior"] = "passive"
                payload["type_id"] = f"passive.flowchart.{variant}"
                payload["title"] = title
                payload["display_name"] = display_name
                payload["collapsed"] = collapsed
                payload["properties"] = {
                    "title": title,
                    "body": "Review the decision criteria and route accordingly.",
                }
                if properties:
                    payload["properties"].update(properties)
                payload["visual_style"] = {}
                if visual_style:
                    payload["visual_style"].update(visual_style)
                payload["width"] = 236.0
                payload["height"] = 128.0
                payload["ports"] = [
                    {
                        "key": "top",
                        "label": "top",
                        "direction": "neutral",
                        "kind": "flow",
                        "data_type": "flow",
                        "exposed": True,
                        "connected": False,
                    },
                    {
                        "key": "right",
                        "label": "right",
                        "direction": "neutral",
                        "kind": "flow",
                        "data_type": "flow",
                        "exposed": True,
                        "connected": False,
                    },
                    {
                        "key": "bottom",
                        "label": "bottom",
                        "direction": "neutral",
                        "kind": "flow",
                        "data_type": "flow",
                        "exposed": True,
                        "connected": False,
                    },
                    {
                        "key": "left",
                        "label": "left",
                        "direction": "neutral",
                        "kind": "flow",
                        "data_type": "flow",
                        "exposed": True,
                        "connected": False,
                    },
                ]
                payload["inline_properties"] = []
                return payload
            """,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def _run_qml_probe_with_retry(self, label: str, body: str, *, retries: int = 4) -> None:
        for attempt in range(max(1, int(retries))):
            try:
                self._run_qml_probe_once(label, body)
                return
            except AssertionError as exc:
                if "exit code 3221226505" not in str(exc) or attempt + 1 >= retries:
                    raise

class GraphSurfaceInputContractTestBase(unittest.TestCase):
    def _run_qml_probe(self, label: str, body: str) -> None:
        self._run_qml_probe_with_retry(label, body)

    def _run_qml_probe_once(self, label: str, body: str) -> None:
        run_qml_probe(
            self,
            label,
            """
            import os
            from pathlib import Path

            os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

            from PyQt6.QtCore import QObject, QUrl, pyqtProperty
            from PyQt6.QtQml import QQmlComponent, QQmlEngine
            from PyQt6.QtWidgets import QApplication

            from ea_node_editor.ui.media_preview_provider import (
                LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
                LocalMediaPreviewImageProvider,
            )
            from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
            from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
            from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values

            class ThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def palette(self):
                    return {
                        "accent": "#2F89FF",
                        "border": "#3a4355",
                        "canvas_bg": "#151821",
                        "canvas_major_grid": "#2f3644",
                        "canvas_minor_grid": "#222833",
                        "group_title_fg": "#d5dbea",
                        "hover": "#33405c",
                        "muted_fg": "#95a0b8",
                        "panel_bg": "#1b1f2a",
                        "panel_title_fg": "#eef3ff",
                        "pressed": "#22304a",
                        "toolbar_bg": "#202635",
                    }

            class GraphThemeBridgeStub(QObject):
                @pyqtProperty("QVariantMap", constant=True)
                def node_palette(self):
                    return {
                        "card_bg": "#1f2431",
                        "card_border": "#414a5d",
                        "card_selected_border": "#5da9ff",
                        "header_bg": "#252c3c",
                        "header_fg": "#eef3ff",
                        "inline_driven_fg": "#aeb8ce",
                        "inline_input_bg": "#18202d",
                        "inline_input_border": "#465066",
                        "inline_input_fg": "#eef3ff",
                        "inline_label_fg": "#d5dbea",
                        "inline_row_bg": "#202635",
                        "inline_row_border": "#3a4355",
                        "port_interactive_border": "#8ca0c7",
                        "port_interactive_fill": "#101521",
                        "port_interactive_ring_border": "#7fb2ff",
                        "port_interactive_ring_fill": "#1a2233",
                        "port_label_fg": "#d5dbea",
                        "scope_badge_bg": "#1f3657",
                        "scope_badge_border": "#4c7bc0",
                        "scope_badge_fg": "#eef3ff",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def port_kind_palette(self):
                    return {
                        "data": "#7AA8FF",
                        "flow": "#67D487",
                    }

                @pyqtProperty("QVariantMap", constant=True)
                def edge_palette(self):
                    return {
                        "invalid_drag_stroke": "#D94F4F",
                        "preview_stroke": "#95a0b8",
                        "selected_stroke": "#5da9ff",
                        "valid_drag_stroke": "#67D487",
                    }

            app = QApplication.instance() or QApplication([])
            engine = QQmlEngine()
            engine.addImageProvider(LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider())
            class ShellContextStub(QObject):
                def __init__(self, theme_bridge, graph_theme_bridge):
                    super().__init__()
                    self._theme_bridge = theme_bridge
                    self._graph_theme_bridge = graph_theme_bridge
                    self._addon_manager_bridge = None

                @pyqtProperty(QObject, constant=True)
                def themeBridge(self):
                    return self._theme_bridge

                @pyqtProperty(QObject, constant=True)
                def graphThemeBridge(self):
                    return self._graph_theme_bridge

                @pyqtProperty(QObject, constant=True)
                def addonManagerBridge(self):
                    return self._addon_manager_bridge

            theme_bridge = ThemeBridgeStub()
            graph_theme_bridge = GraphThemeBridgeStub()
            shell_context = ShellContextStub(theme_bridge, graph_theme_bridge)
            engine.rootContext().setContextProperty("themeBridge", theme_bridge)
            engine.rootContext().setContextProperty("graphThemeBridge", graph_theme_bridge)
            engine.rootContext().setContextProperty("shellContext", shell_context)

            repo_root = Path.cwd()
            components_dir = repo_root / "ea_node_editor" / "ui_qml" / "components"
            graph_canvas_qml_path = components_dir / "GraphCanvas.qml"
            graph_node_host_qml_path = components_dir / "graph" / "GraphNodeHost.qml"

            def create_component(path, initial_properties):
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load {path.name}:\\n{errors}")
                if hasattr(component, "createWithInitialProperties"):
                    obj = component.createWithInitialProperties(initial_properties)
                else:
                    obj = component.create()
                    for key, value in initial_properties.items():
                        obj.setProperty(key, value)
                if obj is None:
                    errors = "\\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate {path.name}:\\n{errors}")
                app.processEvents()
                return obj

            def build_canvas_bridges(*, shell_bridge=None, scene_bridge=None, view_bridge=None):
                state_bridge = GraphCanvasStateBridge(
                    session_state=shell_bridge,
                    snap_to_grid_changed_signal=getattr(shell_bridge, "snap_to_grid_changed", None),
                    snap_grid_size=float(getattr(shell_bridge, "snap_grid_size", 20.0)),
                    app_preferences_source=shell_bridge,
                    graphics_source=shell_bridge,
                    scene_bridge=scene_bridge,
                    view_bridge=view_bridge,
                )
                command_bridge = GraphCanvasCommandBridge(
                    search_scope_controller=shell_bridge,
                    app_preferences_source=shell_bridge,
                    run_controller=shell_bridge,
                    inspector_source=shell_bridge,
                    library_source=shell_bridge,
                    workspace_edit_controller=shell_bridge,
                    workspace_drop_connect_controller=shell_bridge,
                    scene_bridge=scene_bridge,
                    view_bridge=view_bridge,
                )
                return state_bridge, command_bridge

            def node_payload(surface_family="standard", surface_variant=""):
                return {
                    "node_id": "node_surface_contract_test",
                    "type_id": "core.logger",
                    "title": "Logger",
                    "x": 120.0,
                    "y": 120.0,
                    "width": 210.0,
                    "height": 88.0,
                    "accent": "#2F89FF",
                    "collapsed": False,
                    "selected": False,
                    "runtime_behavior": "active",
                    "surface_family": surface_family,
                    "surface_variant": surface_variant,
                    "surface_spec": surface_spec_payload_for_values(
                        type_id="core.logger",
                        family=surface_family,
                        variant=surface_variant,
                    ),
                    "surface_metrics": {
                        "default_width": 210.0,
                        "default_height": 88.0,
                        "min_width": 120.0,
                        "min_height": 50.0,
                        "collapsed_width": 130.0,
                        "collapsed_height": 36.0,
                        "header_height": 24.0,
                        "header_top_margin": 4.0,
                        "body_left_margin": 8.0,
                        "body_right_margin": 8.0,
                        "body_top": 30.0,
                        "body_height": 30.0,
                        "port_top": 60.0,
                        "port_height": 18.0,
                        "port_center_offset": 6.0,
                        "port_side_margin": 8.0,
                        "port_dot_radius": 5.0,
                        "resize_handle_size": 16.0,
                    },
                    "visual_style": {},
                    "can_enter_scope": False,
                    "ports": [
                        {
                            "key": "payload",
                            "label": "Payload",
                            "direction": "in",
                            "kind": "data",
                            "data_type": "any",
                            "connected": False,
                        },
                        {
                            "key": "result",
                            "label": "Result",
                            "direction": "out",
                            "kind": "data",
                            "data_type": "any",
                            "connected": False,
                        },
                    ],
                    "inline_properties": [
                        {
                            "key": "message",
                            "label": "Message",
                            "inline_editor": "text",
                            "value": "log message",
                            "overridden_by_input": False,
                            "input_port_label": "message",
                        }
                    ],
                }
            """,
            QML_POINTER_REGRESSION_HELPERS,
            body,
        )

    def _run_qml_probe_with_retry(self, label: str, body: str, *, retries: int = 4) -> None:
        for attempt in range(max(1, int(retries))):
            try:
                self._run_qml_probe_once(label, body)
                return
            except AssertionError as exc:
                if "exit code 3221226505" not in str(exc) or attempt + 1 >= retries:
                    raise

    def _expand_graph_surface_scan_paths(self, paths: list[Path]) -> list[Path]:
        expanded: list[Path] = []
        for path in paths:
            if path.is_dir():
                expanded.extend(sorted(path.rglob("*.qml")))
            else:
                expanded.append(path)
        return expanded

    def _search_graph_surface_pattern(self, pattern: str, paths: list[Path]) -> list[str]:
        compiled = re.compile(pattern)
        matches: list[str] = []
        for path in self._expand_graph_surface_scan_paths(paths):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if compiled.search(line):
                    matches.append(f"{path.relative_to(_REPO_ROOT)}:{line_number}:{line.strip()}")
        return matches

    def _graph_surface_pointer_audit_failures_with_fallback(self) -> list[str]:
        try:
            return graph_surface_pointer_audit_failures()
        except PermissionError as exc:
            if "Access is denied" not in str(exc):
                raise

        graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
        passive_dir = graph_dir / "passive"
        surface_files = [
            graph_dir / "GraphInlinePropertiesLayer.qml",
            graph_dir / "GraphStandardNodeSurface.qml",
            *sorted(passive_dir.glob("*Surface.qml")),
        ]
        failures: list[str] = []

        hover_proxy_matches = self._search_graph_surface_pattern(
            r"hoverActionHitRect|graphNodeSurfaceHoverActionButton",
            [graph_dir, passive_dir],
        )
        if hover_proxy_matches:
            failures.append(
                "Removed hover-proxy compatibility shims reappeared:\n"
                + "\n".join(hover_proxy_matches)
            )

        tap_handler_matches = self._search_graph_surface_pattern(r"\bTapHandler\s*\{", surface_files)
        if tap_handler_matches:
            failures.append(
                "Unexpected TapHandler usage in graph-surface QML:\n"
                + "\n".join(tap_handler_matches)
            )

        unexpected_mouse_areas: list[str] = []
        for path in surface_files:
            matches = self._search_graph_surface_pattern(r"\bMouseArea\s*\{", [path])
            if not matches:
                continue
            if path.name == "GraphMediaPanelSurface.qml":
                if len(matches) != 1:
                    unexpected_mouse_areas.append(
                        f"{path.relative_to(_REPO_ROOT)}: expected exactly one crop-handle MouseArea, found {len(matches)}"
                    )
                text = path.read_text(encoding="utf-8")
                if 'objectName: "graphNodeMediaCropHandleMouseArea"' not in text:
                    unexpected_mouse_areas.append(
                        f"{path.relative_to(_REPO_ROOT)}: allowed crop-handle MouseArea objectName is missing"
                    )
                if "targetItem: handleMouseArea" not in text:
                    unexpected_mouse_areas.append(
                        f"{path.relative_to(_REPO_ROOT)}: crop-handle MouseArea is no longer tied to GraphSurfaceInteractiveRegion"
                    )
                continue
            if path.name == "GraphNativeExplorerSurface.qml":
                if len(matches) != 2:
                    unexpected_mouse_areas.append(
                        f"{path.relative_to(_REPO_ROOT)}: expected exactly two registered folder-explorer MouseAreas, found {len(matches)}"
                    )
                text = path.read_text(encoding="utf-8")
                required_snippets = {
                    'objectName: "graphFolderExplorerRowMouseArea"': "row MouseArea objectName is missing",
                    'objectName: "graphFolderExplorerHeaderMouseArea"': "header MouseArea objectName is missing",
                    "targetItem: rowMouseArea": "row MouseArea is no longer tied to GraphSurfaceInteractiveRegion",
                    "targetItem: headerMouseArea": "header MouseArea is no longer tied to GraphSurfaceInteractiveRegion",
                }
                for snippet, message in required_snippets.items():
                    if snippet not in text:
                        unexpected_mouse_areas.append(
                            f"{path.relative_to(_REPO_ROOT)}: {message}"
                        )
                continue
            unexpected_mouse_areas.extend(matches)

        if unexpected_mouse_areas:
            failures.append(
                "Unexpected raw MouseArea usage in graph-surface QML:\n"
                + "\n".join(unexpected_mouse_areas)
            )

        return failures

__all__ = [
    "GraphModel",
    "GraphScenePayloadBuilder",
    "GraphSurfaceInputContractTestBase",
    "NodeRegistry",
    "NodeResult",
    "NodeTypeSpec",
    "PassiveGraphSurfaceHostTestBase",
    "Path",
    "ProjectArtifactStore",
    "QEvent",
    "QML_POINTER_REGRESSION_HELPERS",
    "QUrl",
    "ShellTestEnvironment",
    "build_default_registry",
    "encode_file_repair_request",
    "format_managed_artifact_ref",
    "graph_surface_pointer_audit_failures",
    "patch",
    "pytest",
    "run_qml_probe",
    "unittest",
    "_REPO_ROOT",
    "_RenderQualityPayloadPlugin",
    "_destroy_shell_window",
    "_flush_qt_events",
]
