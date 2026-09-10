from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.shell.tooltip_policy import (
    TOOLTIP_CATEGORY_NAMES,
    default_tooltip_category_preferences,
    tooltip_category_effectively_visible,
)
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from tests.graph_track_b import (
    qml_preference_performance_suite as _performance_suite,
    qml_preference_rendering_suite as _rendering_suite,
)
from tests.graph_track_b.qml_support import build_graph_canvas_qml_preference_subprocess_suite

_GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH = (
    _rendering_suite._GRAPH_CANVAS_QML_PATH.parent / "graph_canvas" / "GraphCanvasPreferenceFacts.qml"
)
_GRAPH_SHARED_TYPOGRAPHY_QML_PATH = _rendering_suite._NODE_CARD_QML_PATH.parent / "GraphSharedTypography.qml"


def _qml_error_text(errors) -> str:  # noqa: ANN001
    return "\n".join(error.toString() for error in errors)


def _qml_variant_map(value) -> dict[str, object]:  # noqa: ANN001
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return dict(value)


class _GraphCanvasTypographyPreferenceBridge(_rendering_suite.QObject):
    graphics_preferences_changed = _rendering_suite.pyqtSignal()
    snap_to_grid_changed = _rendering_suite.pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._graphics_show_grid = True
        self._graphics_grid_style = "lines"
        self._graphics_show_minimap = True
        self._graphics_minimap_expanded = True
        self._graphics_show_port_labels = True
        self._graphics_notched_ports = True
        self._graphics_tooltip_categories = default_tooltip_category_preferences()
        self._graphics_edge_crossing_style = "none"
        self._graphics_node_shadow = True
        self._graphics_node_elapsed_time_unit = "seconds"
        self._graphics_node_elapsed_time_visibility = "always"
        self._graphics_node_floating_toolbar_opens_on_hover = False
        self._graphics_shadow_strength = 70
        self._graphics_shadow_softness = 50
        self._graphics_shadow_offset = 4
        self._graphics_lightweight_canvas = False
        self._graphics_plot_default_backend_per_type = dict(
            DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"]
        )
        self._graphics_graph_label_pixel_size = 10
        self._graphics_graph_node_icon_pixel_size_override: int | None = None
        self._graphics_expand_collision_avoidance = dict(
            DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"]
        )

    @property
    def graphics_show_grid(self) -> bool:
        return bool(self._graphics_show_grid)

    @property
    def graphics_grid_style(self) -> str:
        return str(self._graphics_grid_style)

    @property
    def graphics_show_minimap(self) -> bool:
        return bool(self._graphics_show_minimap)

    @property
    def graphics_minimap_expanded(self) -> bool:
        return bool(self._graphics_minimap_expanded)

    @property
    def graphics_show_port_labels(self) -> bool:
        return bool(self._graphics_show_port_labels)

    @property
    def graphics_notched_ports(self) -> bool:
        return bool(self._graphics_notched_ports)

    @property
    def graphics_show_tooltips(self) -> bool:
        return bool(self._graphics_tooltip_categories["general"])

    @property
    def graphics_tooltip_categories(self) -> dict[str, bool]:
        return dict(self._graphics_tooltip_categories)

    @property
    def graphics_tooltip_category_visibility(self) -> dict[str, bool]:
        return {
            category: tooltip_category_effectively_visible(
                category,
                tooltip_categories=self._graphics_tooltip_categories,
            )
            for category in TOOLTIP_CATEGORY_NAMES
        }

    def tooltip_category_enabled(self, category: str) -> bool:
        return tooltip_category_effectively_visible(
            category,
            tooltip_categories=self._graphics_tooltip_categories,
        )

    @property
    def graphics_edge_crossing_style(self) -> str:
        return str(self._graphics_edge_crossing_style)

    @property
    def graphics_node_shadow(self) -> bool:
        return bool(self._graphics_node_shadow)

    @property
    def graphics_node_elapsed_time_unit(self) -> str:
        return str(self._graphics_node_elapsed_time_unit)

    @property
    def graphics_node_elapsed_time_visibility(self) -> str:
        return str(self._graphics_node_elapsed_time_visibility)

    @property
    def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
        return bool(self._graphics_node_floating_toolbar_opens_on_hover)

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
    def graphics_lightweight_canvas(self) -> bool:
        return bool(self._graphics_lightweight_canvas)

    @property
    def graphics_plot_default_backend_per_type(self) -> dict[str, str]:
        return dict(self._graphics_plot_default_backend_per_type)

    @property
    def graphics_graph_label_pixel_size(self) -> int:
        return int(self._graphics_graph_label_pixel_size)

    @property
    def graphics_graph_node_icon_pixel_size_override(self) -> int | None:
        return self._graphics_graph_node_icon_pixel_size_override

    @property
    def graphics_node_title_icon_pixel_size(self) -> int:
        override = self._graphics_graph_node_icon_pixel_size_override
        return int(self._graphics_graph_label_pixel_size if override is None else override)

    @property
    def graphics_expand_collision_avoidance(self) -> dict[str, object]:
        return dict(self._graphics_expand_collision_avoidance)

    def set_graphics_graph_label_pixel_size_value(self, value: int) -> None:
        normalized = max(8, min(int(value), 50))
        if self._graphics_graph_label_pixel_size == normalized:
            return
        self._graphics_graph_label_pixel_size = normalized
        self.graphics_preferences_changed.emit()

    def set_plot_preferences_value(
        self,
        *,
        lightweight_canvas: bool,
        plot_default_backend_per_type: dict[str, str] | None = None,
    ) -> None:
        defaults = (
            dict(plot_default_backend_per_type)
            if plot_default_backend_per_type is not None
            else dict(self._graphics_plot_default_backend_per_type)
        )
        changed = (
            self._graphics_lightweight_canvas != bool(lightweight_canvas)
            or self._graphics_plot_default_backend_per_type != defaults
        )
        if not changed:
            return
        self._graphics_lightweight_canvas = bool(lightweight_canvas)
        self._graphics_plot_default_backend_per_type = defaults
        self.graphics_preferences_changed.emit()

    def set_general_tooltips_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_tooltip_categories["general"] == normalized:
            return
        self._graphics_tooltip_categories["general"] = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_tooltip_category_value(self, category: str, value: bool) -> None:
        if category not in self._graphics_tooltip_categories:
            return
        normalized = bool(value)
        if self._graphics_tooltip_categories[category] == normalized:
            return
        self._graphics_tooltip_categories[category] = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_graph_node_icon_pixel_size_override_value(self, value: int | None) -> None:
        normalized = None if value is None else max(8, min(int(value), 50))
        if self._graphics_graph_node_icon_pixel_size_override == normalized:
            return
        self._graphics_graph_node_icon_pixel_size_override = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_elapsed_time_unit_value(self, value: str) -> None:
        normalized = str(value or "seconds").strip().lower()
        if normalized not in {"seconds", "milliseconds"}:
            normalized = "seconds"
        if self._graphics_node_elapsed_time_unit == normalized:
            return
        self._graphics_node_elapsed_time_unit = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_elapsed_time_visibility_value(self, value: str) -> None:
        normalized = str(value or "always").strip().lower()
        if normalized not in {"off", "during_run", "always"}:
            normalized = "always"
        if self._graphics_node_elapsed_time_visibility == normalized:
            return
        self._graphics_node_elapsed_time_visibility = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_notched_ports_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_notched_ports == normalized:
            return
        self._graphics_notched_ports = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_node_floating_toolbar_opens_on_hover_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_node_floating_toolbar_opens_on_hover == normalized:
            return
        self._graphics_node_floating_toolbar_opens_on_hover = normalized
        self.graphics_preferences_changed.emit()

    def set_graphics_expand_collision_avoidance_value(self, value: dict[str, object]) -> None:
        normalized = dict(value)
        if self._graphics_expand_collision_avoidance == normalized:
            return
        self._graphics_expand_collision_avoidance = normalized
        self.graphics_preferences_changed.emit()


class GraphCanvasQmlPreferenceBindingTests(
    _rendering_suite.GraphCanvasQmlPreferenceRenderingTests,
    _performance_suite.GraphCanvasQmlPreferencePerformanceTests,
):
    """Stable regression entrypoint for packetized Track-B QML preference coverage."""

    __test__ = True

    def _load_qml_component(self, path) -> _rendering_suite.QQmlComponent:
        component = _rendering_suite.QQmlComponent(self.engine, _rendering_suite.QUrl.fromLocalFile(str(path)))
        if component.status() != _rendering_suite.QQmlComponent.Status.Ready:
            errors = _qml_error_text(component.errors())
            self.fail(f"Failed to load {path.name}:\n{errors}")
        return component

    def _create_component(self, path, initial_properties: dict[str, object]) -> _rendering_suite.QObject:
        component = self._load_qml_component(path)
        if hasattr(component, "createWithInitialProperties"):
            instance = component.createWithInitialProperties(initial_properties)
        else:
            instance = component.create()
            if instance is not None:
                for key, value in initial_properties.items():
                    instance.setProperty(key, value)
        if instance is None:
            errors = _qml_error_text(component.errors())
            self.fail(f"Failed to instantiate {path.name}:\n{errors}")
        self.app.processEvents()
        return instance

    def test_canvas_options_gear_position_and_visibility_follow_graphics_preference(self) -> None:
        gear_items = _rendering_suite._named_child_items(
            self.canvas,
            "graphCanvasOptionsGearButton",
        )
        self.assertEqual(len(gear_items), 1)
        gear = gear_items[0]
        expected_x = (
            float(self.canvas.property("width")) - float(gear.property("width")) - 8.0
        )

        _rendering_suite.wait_for_condition_or_raise(
            lambda: abs(float(gear.property("x")) - expected_x) <= 0.5
            and abs(float(gear.property("y")) - 8.0) <= 0.5,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for the canvas options gear to use the corner margin.",
        )
        self.assertTrue(bool(self.canvas.property("showCanvasOptionsButton")))
        self.assertTrue(bool(gear.property("visible")))
        self.assertTrue(bool(gear.property("enabled")))

        self.bridge.set_graphics_show_canvas_options_button_value(False)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: not bool(self.canvas.property("showCanvasOptionsButton"))
            and not bool(gear.property("visible"))
            and not bool(gear.property("enabled")),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for the canvas options gear to hide.",
        )

        self.bridge.set_graphics_show_canvas_options_button_value(True)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(self.canvas.property("showCanvasOptionsButton"))
            and bool(gear.property("visible"))
            and bool(gear.property("enabled")),
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for the canvas options gear to show again.",
        )

    def test_notched_ports_fact_defaults_on_and_follows_preference_source(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        facts = self._create_component(
            _GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH,
            {"stateBridge": state_bridge},
        )

        try:
            self.assertTrue(bool(facts.property("notchedPortsEnabled")))
            preference_bridge.set_graphics_notched_ports_value(False)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: not bool(facts.property("notchedPortsEnabled")),
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for the notched ports fact to update.",
            )
        finally:
            facts.deleteLater()
            state_bridge.deleteLater()
            preference_bridge.deleteLater()
            self.app.processEvents()

    def test_expand_collision_avoidance_bridge_projection_follows_preference_source(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        seen = {"count": 0}
        state_bridge.graphics_preferences_changed.connect(lambda: seen.__setitem__("count", seen["count"] + 1))

        try:
            self.assertEqual(
                state_bridge.graphics_expand_collision_avoidance,
                DEFAULT_GRAPHICS_SETTINGS["interaction"]["expand_collision_avoidance"],
            )

            updated = {
                "enabled": False,
                "strategy": "nearest",
                "scope": "all_movable",
                "radius_mode": "unbounded",
                "local_radius_preset": "large",
                "gap_preset": "tight",
                "animate": False,
            }
            preference_bridge.set_graphics_expand_collision_avoidance_value(updated)
            self.app.processEvents()

            self.assertEqual(state_bridge.graphics_expand_collision_avoidance, updated)
            self.assertEqual(seen["count"], 1)
        finally:
            state_bridge.deleteLater()
            preference_bridge.deleteLater()
            self.app.processEvents()

    def test_plot_preference_bridge_projection_follows_preference_source(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        seen = {"count": 0}
        state_bridge.graphics_preferences_changed.connect(lambda: seen.__setitem__("count", seen["count"] + 1))

        try:
            self.assertFalse(state_bridge.graphics_lightweight_canvas)
            self.assertEqual(
                state_bridge.graphics_plot_default_backend_per_type,
                DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"],
            )

            preference_bridge.set_plot_preferences_value(
                lightweight_canvas=True,
                plot_default_backend_per_type={
                    "line": "matplotlib",
                    "point_cloud": "matplotlib",
                    "future": "matplotlib",
                },
            )
            self.app.processEvents()

            self.assertTrue(state_bridge.graphics_lightweight_canvas)
            self.assertEqual(
                state_bridge.graphics_plot_default_backend_per_type,
                DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"],
            )
            self.assertEqual(seen["count"], 1)
        finally:
            state_bridge.deleteLater()
            preference_bridge.deleteLater()
            self.app.processEvents()

    def _assert_persistent_node_elapsed_footer_rendering(self) -> None:
        node_id = "node_execution_visualization"
        node_payload = {
            "node_id": node_id,
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 140.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "surface_family": "standard",
            "surface_variant": "",
            "ports": [
                {
                    "key": "message",
                    "label": "Message",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
                {
                    "key": "result",
                    "label": "Result",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "str",
                    "connected": False,
                },
            ],
            "inline_properties": [],
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
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            },
        }

        class CanvasStateBridgeStub(_rendering_suite.QObject):
            graphics_preferences_changed = _rendering_suite.pyqtSignal()
            scene_nodes_changed = _rendering_suite.pyqtSignal()
            failure_highlight_changed = _rendering_suite.pyqtSignal()
            node_execution_state_changed = _rendering_suite.pyqtSignal()

            def __init__(
                self,
                preference_bridge: _rendering_suite._GraphCanvasPreferenceBridge,
                canvas_source: object,
                view_bridge: _rendering_suite.ViewportBridge,
            ) -> None:
                super().__init__()
                self._preference_bridge = preference_bridge
                self._canvas_source = canvas_source
                self._view_bridge = view_bridge
                self._nodes_model = [dict(node_payload)]
                self._running_node_lookup: dict[str, bool] = {}
                self._completed_node_lookup: dict[str, bool] = {}
                self._failed_node_lookup: dict[str, bool] = {}
                self._running_node_started_at_ms_lookup: dict[str, float] = {}
                self._node_elapsed_ms_lookup: dict[str, float] = {}
                self._node_execution_revision = 0
                self._preference_bridge.graphics_preferences_changed.connect(self.graphics_preferences_changed.emit)

            @_rendering_suite.pyqtProperty(_rendering_suite.QObject, constant=True)
            def viewport_bridge(self) -> _rendering_suite.ViewportBridge:
                return self._view_bridge

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._canvas_source.graphics_minimap_expanded)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_grid(self) -> bool:
                return bool(self._preference_bridge.graphics_show_grid)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_grid_style(self) -> str:
                return str(self._preference_bridge.graphics_grid_style)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_edge_crossing_style(self) -> str:
                return str(self._preference_bridge.graphics_edge_crossing_style)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_minimap(self) -> bool:
                return bool(self._preference_bridge.graphics_show_minimap)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_port_labels(self) -> bool:
                return bool(self._preference_bridge.graphics_show_port_labels)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_node_elapsed_time_unit(self) -> str:
                return str(self._preference_bridge.graphics_node_elapsed_time_unit)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_node_elapsed_time_visibility(self) -> str:
                return str(self._preference_bridge.graphics_node_elapsed_time_visibility)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
                return bool(
                    self._preference_bridge.graphics_node_floating_toolbar_opens_on_hover
                )

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_shadow(self) -> bool:
                return True

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_strength(self) -> int:
                return 70

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_softness(self) -> int:
                return 50

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_offset(self) -> int:
                return 4

            @_rendering_suite.pyqtProperty("QVariantList", notify=scene_nodes_changed)
            def nodes_model(self) -> list[dict[str, object]]:
                return list(self._nodes_model)

            @_rendering_suite.pyqtProperty("QVariantList", constant=True)
            def backdrop_nodes_model(self) -> list[dict[str, object]]:
                return []

            @_rendering_suite.pyqtProperty("QVariantList", constant=True)
            def edges_model(self) -> list[dict[str, object]]:
                return []

            @_rendering_suite.pyqtProperty("QVariantMap", constant=True)
            def selected_node_lookup(self) -> dict[str, bool]:
                return {}

            @_rendering_suite.pyqtProperty("QVariantMap", constant=True)
            def workspace_scene_bounds_payload(self) -> dict[str, float]:
                return {}

            @_rendering_suite.pyqtProperty("QVariantMap", notify=failure_highlight_changed)
            def failed_node_lookup(self) -> dict[str, bool]:
                return dict(self._failed_node_lookup)

            @_rendering_suite.pyqtProperty(str, notify=failure_highlight_changed)
            def failed_node_title(self) -> str:
                return "Logger" if self._failed_node_lookup else ""

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_lookup(self) -> dict[str, bool]:
                return dict(self._running_node_lookup)

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def completed_node_lookup(self) -> dict[str, bool]:
                return dict(self._completed_node_lookup)

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_started_at_ms_lookup(self) -> dict[str, float]:
                return dict(self._running_node_started_at_ms_lookup)

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def node_elapsed_ms_lookup(self) -> dict[str, float]:
                return dict(self._node_elapsed_ms_lookup)

            @_rendering_suite.pyqtProperty(int, notify=node_execution_state_changed)
            def node_execution_revision(self) -> int:
                return int(self._node_execution_revision)

            def set_running_node_state(self, tracked_node_id: str, started_at_ms: float) -> None:
                self._running_node_lookup = {str(tracked_node_id): True}
                self._completed_node_lookup = {}
                self._running_node_started_at_ms_lookup = {str(tracked_node_id): float(started_at_ms)}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def set_completed_node_state(self, tracked_node_id: str, elapsed_ms: float) -> None:
                self._running_node_lookup = {}
                self._completed_node_lookup = {str(tracked_node_id): True}
                self._running_node_started_at_ms_lookup = {}
                self._node_elapsed_ms_lookup = {str(tracked_node_id): float(elapsed_ms)}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def clear_terminal_execution_state(self) -> None:
                self._running_node_lookup = {}
                self._completed_node_lookup = {}
                self._running_node_started_at_ms_lookup = {}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def clear_cached_elapsed(self) -> None:
                self._node_elapsed_ms_lookup = {}
                self._node_execution_revision += 1
                self.node_execution_state_changed.emit()

            def set_failed_node_state(self, tracked_node_id: str) -> None:
                self._failed_node_lookup = {str(tracked_node_id): True}
                self.failure_highlight_changed.emit()

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = CanvasStateBridgeStub(
            self.bridge,
            self.canvas_source,
            self.view,
        )
        canvas_command_bridge = _rendering_suite.GraphCanvasCommandBridge(
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
        self.addCleanup(self.app.processEvents)
        self.addCleanup(canvas_command_bridge.deleteLater)
        self.addCleanup(canvas_state_bridge.deleteLater)
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        _rendering_suite.wait_for_condition_or_raise(
            lambda: len(_rendering_suite._named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas execution-visualization node host to appear.",
        )
        node_card = _rendering_suite._named_child_items(self.canvas, "graphNodeCard")[0]
        background_layer = node_card.findChild(_rendering_suite.QObject, "graphNodeChromeBackgroundLayer")
        elapsed_timer = node_card.findChild(_rendering_suite.QObject, "graphNodeElapsedTimer")
        self.assertIsNotNone(background_layer)
        self.assertIsNotNone(elapsed_timer)
        if background_layer is None or elapsed_timer is None:
            self.fail("Expected graph canvas execution chrome items to exist")
        for removed_name in (
            "graphNodeFailureHalo",
            "graphNodeFailurePulseHalo",
            "graphNodeRunningHalo",
            "graphNodeRunningPulseHalo",
            "graphNodeCompletedFlashHalo",
            "graphNodeSelectedRunPreviewHalo",
            "graphNodeRunFreshHalo",
        ):
            self.assertIsNone(node_card.findChild(_rendering_suite.QObject, removed_name))

        self.assertEqual(str(background_layer.property("effectiveBorderState")), "idle")
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(self.canvas.property("completedNodeLookup")), {})
        self.assertFalse(bool(elapsed_timer.property("visible")))

        idle_key = str(background_layer.property("cacheKey") or "")
        started_at_ms = (time.time() * 1000.0) - 2100.0
        completed_elapsed_ms = 3487.0

        canvas_state_bridge.set_running_node_state(node_id, started_at_ms)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and str(background_layer.property("effectiveBorderState")) == "idle"
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("liveElapsedActive"))
            and abs(float(elapsed_timer.property("startedAtMs")) - started_at_ms) < 16.0
            and float(elapsed_timer.property("elapsedMilliseconds")) >= 1700.0,
            timeout_ms=500,
            app=self.app,
            timeout_message="Timed out waiting for lookup-backed live elapsed footer rendering on graph canvas host.",
        )

        self.assertTrue(bool(node_card.property("renderActive")))
        self.assertEqual(int(node_card.property("z")), 31)
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {node_id: True})
        self.assertEqual(self.canvas.property("runningNodeStartedAtMsLookup"), {node_id: started_at_ms})
        self.assertEqual(
            _rendering_suite._color_name(background_layer.property("effectiveOutlineColor")),
            _rendering_suite._color_name(node_card.property("outlineColor")),
        )

        running_key = str(background_layer.property("cacheKey") or "")
        self.assertEqual(running_key, idle_key)

        canvas_state_bridge.set_completed_node_state(node_id, completed_elapsed_ms)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(node_card.property("isCompletedNode"))
            and not bool(node_card.property("isRunningNode"))
            and str(background_layer.property("effectiveBorderState")) == "idle"
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive"))
            and str(elapsed_timer.property("text") or "") == "3.5s",
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer rendering on graph canvas host.",
        )

        self.assertEqual(int(node_card.property("z")), 30)
        self.assertEqual(dict(self.canvas.property("runningNodeLookup")), {})
        self.assertEqual(dict(self.canvas.property("completedNodeLookup")), {node_id: True})
        self.assertEqual(self.canvas.property("nodeElapsedMsLookup"), {node_id: completed_elapsed_ms})
        self.assertFalse(bool(elapsed_timer.property("liveElapsedActive")))
        self.assertAlmostEqual(float(elapsed_timer.property("cachedElapsedMilliseconds")), completed_elapsed_ms, places=2)
        self.assertEqual(
            _rendering_suite._color_name(elapsed_timer.property("color")),
            _rendering_suite._color_name(node_card.property("completedElapsedFooterColor")),
        )
        self.assertAlmostEqual(
            float(elapsed_timer.property("opacity")),
            float(node_card.property("completedElapsedFooterOpacity")),
            places=2,
        )
        self.bridge.set_graphics_node_elapsed_time_unit_value("milliseconds")
        _rendering_suite.wait_for_condition_or_raise(
            lambda: str(elapsed_timer.property("text") or "") == "3487ms",
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for millisecond elapsed footer rendering on graph canvas host.",
        )
        self.assertEqual(str(self.canvas.property("nodeElapsedTimeUnit")), "milliseconds")

        self.bridge.set_graphics_node_elapsed_time_visibility_value("during_run")
        _rendering_suite.wait_for_condition_or_raise(
            lambda: not bool(elapsed_timer.property("visible"))
            and not bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for During run mode to hide completed elapsed footer.",
        )
        self.bridge.set_graphics_node_elapsed_time_visibility_value("always")
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for Always mode to restore completed elapsed footer.",
        )

        completed_key = str(background_layer.property("cacheKey") or "")
        self.assertEqual(completed_key, running_key)

        canvas_state_bridge.clear_terminal_execution_state()
        _rendering_suite.wait_for_condition_or_raise(
            lambda: not bool(node_card.property("isCompletedNode"))
            and not bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer persistence after terminal cleanup.",
        )

        canvas_state_bridge.clear_cached_elapsed()
        _rendering_suite.wait_for_condition_or_raise(
            lambda: not bool(elapsed_timer.property("visible"))
            and not bool(elapsed_timer.property("cachedElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for cached elapsed footer invalidation on graph canvas host.",
        )

        self.bridge.set_graphics_node_elapsed_time_visibility_value("off")
        canvas_state_bridge.set_running_node_state(node_id, (time.time() * 1000.0) - 1600.0)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and not bool(elapsed_timer.property("visible")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for Off mode to hide live elapsed footer.",
        )
        self.bridge.set_graphics_node_elapsed_time_visibility_value("during_run")
        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(node_card.property("isRunningNode"))
            and bool(elapsed_timer.property("visible"))
            and bool(elapsed_timer.property("liveElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for live elapsed footer to restore before failure-priority check.",
        )

        canvas_state_bridge.set_failed_node_state(node_id)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: str(background_layer.property("effectiveBorderState")) == "failed"
            and not bool(elapsed_timer.property("visible")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for failure priority to hide the elapsed footer.",
        )

        self.assertEqual(dict(self.canvas.property("failedNodeLookup")), {node_id: True})
        self.assertEqual(
            _rendering_suite._color_name(background_layer.property("effectiveOutlineColor")),
            _rendering_suite._color_name(node_card.property("failureOutlineColor")),
        )
        self.assertFalse(bool(elapsed_timer.property("liveElapsedActive")))
        self.assertFalse(bool(elapsed_timer.property("cachedElapsedActive")))
        self.assertIn("|error|", str(background_layer.property("cacheKey") or ""))

    def test_graph_typography_qml_contract_graph_typography_inline_edge_root_bindings_and_shared_roles_follow_preference_projection(
        self,
    ) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        root_bindings = self._create_component(
            _GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH,
            {"stateBridge": state_bridge},
        )
        typography = self._create_component(
            _GRAPH_SHARED_TYPOGRAPHY_QML_PATH,
            {"graphLabelPixelSize": int(root_bindings.property("graphLabelPixelSize"))},
        )

        try:
            self.assertEqual(int(root_bindings.property("graphLabelPixelSize")), 10)
            self.assertFalse(bool(root_bindings.property("nodeFloatingToolbarOpensOnHover")))
            expected_defaults = {
                "nodeTitlePixelSize": 12,
                "portLabelPixelSize": 10,
                "elapsedFooterPixelSize": 10,
                "inlinePropertyPixelSize": 10,
                "badgePixelSize": 9,
                "badgeIconPixelSize": 11,
                "edgeLabelPixelSize": 11,
                "edgePillPixelSize": 12,
                "nodeTitleFontWeight": 700,
                "portLabelFontWeight": 400,
                "inlinePropertyFontWeight": 400,
                "badgeFontWeight": 700,
                "edgeLabelFontWeight": 500,
                "edgePillFontWeight": 600,
            }
            for property_name, expected_value in expected_defaults.items():
                with self.subTest(property_name=property_name, expected_value=expected_value):
                    self.assertEqual(int(typography.property(property_name)), expected_value)

            preference_bridge.set_graphics_graph_label_pixel_size_value(16)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: int(root_bindings.property("graphLabelPixelSize")) == 16,
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for GraphCanvasPreferenceFacts to project graph label pixel size.",
            )
            typography.setProperty("graphLabelPixelSize", int(root_bindings.property("graphLabelPixelSize")))
            self.app.processEvents()

            preference_bridge.set_graphics_node_floating_toolbar_opens_on_hover_value(True)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: bool(root_bindings.property("nodeFloatingToolbarOpensOnHover")),
                timeout_ms=200,
                app=self.app,
                timeout_message=(
                    "Timed out waiting for GraphCanvasPreferenceFacts to project "
                    "node floating toolbar hover behavior."
                ),
            )

            expected_updated_sizes = {
                "nodeTitlePixelSize": 18,
                "portLabelPixelSize": 16,
                "elapsedFooterPixelSize": 16,
                "inlinePropertyPixelSize": 16,
                "badgePixelSize": 15,
                "badgeIconPixelSize": 17,
                "edgeLabelPixelSize": 17,
                "edgePillPixelSize": 18,
            }
            for property_name, expected_value in expected_updated_sizes.items():
                with self.subTest(property_name=property_name, expected_value=expected_value):
                    self.assertEqual(int(typography.property(property_name)), expected_value)
        finally:
            typography.deleteLater()
            root_bindings.deleteLater()
            self.app.processEvents()

    def test_graph_typography_dialog_qml_bindings_follow_bridge_projection(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        root_bindings = self._create_component(
            _GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH,
            {"stateBridge": state_bridge},
        )
        typography = self._create_component(
            _GRAPH_SHARED_TYPOGRAPHY_QML_PATH,
            {"graphLabelPixelSize": int(root_bindings.property("graphLabelPixelSize"))},
        )

        try:
            self.assertEqual(int(root_bindings.property("graphLabelPixelSize")), 10)
            self.assertEqual(int(typography.property("graphLabelPixelSize")), 10)
            self.assertEqual(int(typography.property("nodeTitlePixelSize")), 12)

            preference_bridge.set_graphics_graph_label_pixel_size_value(16)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: int(root_bindings.property("graphLabelPixelSize")) == 16,
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for dialog-owned typography preference projection to reach root bindings.",
            )
            typography.setProperty("graphLabelPixelSize", int(root_bindings.property("graphLabelPixelSize")))
            self.app.processEvents()

            self.assertEqual(int(typography.property("graphLabelPixelSize")), 16)
            self.assertEqual(int(typography.property("portLabelPixelSize")), 16)
            self.assertEqual(int(typography.property("nodeTitlePixelSize")), 18)
        finally:
            typography.deleteLater()
            root_bindings.deleteLater()
            self.app.processEvents()

    def test_graph_tooltip_qml_bindings_follow_bridge_projection(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        root_bindings = self._create_component(
            _GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH,
            {"stateBridge": state_bridge},
        )

        try:
            expected_visibility = {
                "general": True,
                "tutorial": True,
                "advanced": False,
                "warning": True,
                "inactive": True,
                "critical": True,
            }
            self.assertTrue(bool(state_bridge.graphics_show_tooltips))
            self.assertEqual(state_bridge.graphics_tooltip_category_visibility, expected_visibility)
            self.assertEqual(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility")), expected_visibility)
            self.assertTrue(state_bridge.tooltip_category_enabled("critical"))
            self.assertTrue(bool(root_bindings.property("showTooltips")))

            preference_bridge.set_general_tooltips_value(False)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: (
                    not bool(root_bindings.property("showTooltips"))
                    and not bool(
                        _qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["general"]
                    )
                ),
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for GraphCanvasPreferenceFacts to project tooltip visibility policy.",
            )

            self.assertFalse(bool(state_bridge.graphics_show_tooltips))
            self.assertFalse(state_bridge.tooltip_category_enabled("general"))
            self.assertTrue(state_bridge.tooltip_category_enabled("tutorial"))
            self.assertTrue(state_bridge.tooltip_category_enabled("warning"))
            self.assertTrue(state_bridge.tooltip_category_enabled("critical"))
            self.assertFalse(bool(root_bindings.property("showTooltips")))
            self.assertTrue(bool(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["tutorial"]))
            self.assertTrue(bool(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["warning"]))
            self.assertTrue(bool(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["critical"]))

            preference_bridge.set_graphics_tooltip_category_value("tutorial", False)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: (
                    not bool(state_bridge.tooltip_category_enabled("tutorial"))
                    and not bool(
                        _qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["tutorial"]
                    )
                ),
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for tutorial tooltip category projection to update.",
            )
            self.assertFalse(state_bridge.tooltip_category_enabled("tutorial"))
            self.assertFalse(bool(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["tutorial"]))

            preference_bridge.set_graphics_tooltip_category_value("warning", False)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: (
                    not bool(state_bridge.tooltip_category_enabled("warning"))
                    and not bool(
                        _qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["warning"]
                    )
                ),
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for tooltip category projection to update.",
            )
            self.assertFalse(state_bridge.tooltip_category_enabled("warning"))
            self.assertFalse(bool(_qml_variant_map(root_bindings.property("tooltipCategoryVisibility"))["warning"]))
        finally:
            root_bindings.deleteLater()
            self.app.processEvents()

    def test_graph_node_icon_size_qml_bindings_project_effective_size_without_text_role_drift(self) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        state_bridge = GraphCanvasStateBridge(
            session_state=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            snap_to_grid_changed_signal=getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_to_grid_changed", None),  # type: ignore[arg-type]
            snap_grid_size=float(getattr(_rendering_suite._GraphCanvasSessionBridge(preference_bridge), "snap_grid_size", 20.0)),  # type: ignore[arg-type]
            app_preferences_source=_rendering_suite._GraphCanvasSessionBridge(preference_bridge),  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        root_bindings = self._create_component(
            _GRAPH_CANVAS_PREFERENCE_FACTS_QML_PATH,
            {"stateBridge": state_bridge},
        )
        typography = self._create_component(
            _GRAPH_SHARED_TYPOGRAPHY_QML_PATH,
            {
                "graphLabelPixelSize": int(root_bindings.property("graphLabelPixelSize")),
                "graphNodeIconPixelSize": int(root_bindings.property("nodeTitleIconPixelSize")),
            },
        )

        try:
            self.assertEqual(int(root_bindings.property("graphLabelPixelSize")), 10)
            self.assertIsNone(root_bindings.property("graphNodeIconPixelSizeOverride"))
            self.assertEqual(int(root_bindings.property("nodeTitleIconPixelSize")), 10)
            self.assertEqual(int(typography.property("nodeTitleIconPixelSize")), 10)
            self.assertEqual(int(typography.property("nodeTitlePixelSize")), 12)

            preference_bridge.set_graphics_graph_label_pixel_size_value(16)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: int(root_bindings.property("nodeTitleIconPixelSize")) == 16,
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for automatic node title icon size to follow graph label size.",
            )
            typography.setProperty("graphLabelPixelSize", int(root_bindings.property("graphLabelPixelSize")))
            typography.setProperty("graphNodeIconPixelSize", int(root_bindings.property("nodeTitleIconPixelSize")))
            self.app.processEvents()

            self.assertEqual(int(typography.property("nodeTitleIconPixelSize")), 16)
            self.assertEqual(int(typography.property("nodeTitlePixelSize")), 18)

            preference_bridge.set_graphics_graph_node_icon_pixel_size_override_value(12)
            _rendering_suite.wait_for_condition_or_raise(
                lambda: int(root_bindings.property("nodeTitleIconPixelSize")) == 12
                and int(root_bindings.property("graphNodeIconPixelSizeOverride")) == 12,
                timeout_ms=200,
                app=self.app,
                timeout_message="Timed out waiting for explicit node title icon size override projection.",
            )
            typography.setProperty("graphNodeIconPixelSize", int(root_bindings.property("nodeTitleIconPixelSize")))
            self.app.processEvents()

            self.assertEqual(int(typography.property("nodeTitleIconPixelSize")), 12)
            self.assertEqual(int(typography.property("nodeTitlePixelSize")), 18)
            self.assertEqual(int(typography.property("portLabelPixelSize")), 16)
        finally:
            typography.deleteLater()
            root_bindings.deleteLater()
            self.app.processEvents()

    def test_graph_typography_qml_contract_scene_refresh_updates_standard_metrics_and_edge_geometry(
        self,
    ) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        scene = GraphSceneBridge(preference_bridge)
        scene.bind_graphics_preferences_source(preference_bridge)
        graph_theme_bridge = GraphThemeBridge(preference_bridge, theme_id="graph_stitch_dark")
        scene.bind_graph_theme_bridge(graph_theme_bridge)
        self.addCleanup(self.app.processEvents)
        self.addCleanup(preference_bridge.deleteLater)
        self.addCleanup(graph_theme_bridge.deleteLater)
        self.addCleanup(scene.deleteLater)
        model = GraphModel()
        registry = build_default_registry()
        workspace_id = model.active_workspace.workspace_id
        scene.set_workspace(model, registry, workspace_id)

        source_id = scene.add_node_from_type("core.constant", 40.0, 60.0)
        target_id = scene.add_node_from_type("core.python_script", 460.0, 80.0)
        edge_id = scene.add_edge(source_id, "value", target_id, "payload")
        scene.set_node_port_label(source_id, "value", "Dispatch Result Token")
        scene.refresh_workspace_from_model(workspace_id)

        baseline_nodes = {item["node_id"]: item for item in scene.nodes_model}
        baseline_edges = {item["edge_id"]: item for item in scene.edges_model}
        baseline_source_payload = baseline_nodes[source_id]
        baseline_edge_payload = baseline_edges[edge_id]

        seen = {"nodes": 0, "edges": 0}
        scene.nodes_changed.connect(lambda: seen.__setitem__("nodes", seen["nodes"] + 1))
        scene.edges_changed.connect(lambda: seen.__setitem__("edges", seen["edges"] + 1))

        preference_bridge.set_graphics_graph_label_pixel_size_value(16)
        scene.refresh_workspace_from_model(workspace_id)

        updated_nodes = {item["node_id"]: item for item in scene.nodes_model}
        updated_edges = {item["edge_id"]: item for item in scene.edges_model}
        updated_source_payload = updated_nodes[source_id]
        updated_edge_payload = updated_edges[edge_id]

        self.assertGreaterEqual(seen["nodes"], 1)
        self.assertGreaterEqual(seen["edges"], 1)
        self.assertGreater(
            float(updated_source_payload["surface_metrics"]["standard_title_full_width"]),
            float(baseline_source_payload["surface_metrics"]["standard_title_full_width"]),
        )
        self.assertGreater(
            float(updated_source_payload["surface_metrics"]["standard_port_label_min_width"]),
            float(baseline_source_payload["surface_metrics"]["standard_port_label_min_width"]),
        )
        self.assertGreater(float(updated_source_payload["width"]), float(baseline_source_payload["width"]))
        self.assertGreater(
            float(updated_edge_payload["source_anchor_bounds"]["width"]),
            float(baseline_edge_payload["source_anchor_bounds"]["width"]),
        )
        self.assertGreater(float(updated_edge_payload["sx"]), float(baseline_edge_payload["sx"]))

    def test_graph_typography_host_chrome_canvas_bindings_update_standard_title_ports_and_elapsed_footer(
        self,
    ) -> None:
        preference_bridge = _GraphCanvasTypographyPreferenceBridge()
        node_id = "node_typography_host_chrome"
        started_at_ms = (time.time() * 1000.0) - 2100.0
        node_payload = {
            "node_id": node_id,
            "type_id": "core.logger",
            "title": "Logger",
            "x": 120.0,
            "y": 140.0,
            "width": 210.0,
            "height": 88.0,
            "accent": "#2F89FF",
            "collapsed": False,
            "selected": False,
            "can_enter_scope": False,
            "surface_family": "standard",
            "surface_variant": "",
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
                    "data_type": "str",
                    "connected": False,
                },
            ],
            "inline_properties": [],
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
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            },
        }

        class CanvasStateBridgeStub(_rendering_suite.QObject):
            graphics_preferences_changed = _rendering_suite.pyqtSignal()
            scene_nodes_changed = _rendering_suite.pyqtSignal()
            failure_highlight_changed = _rendering_suite.pyqtSignal()
            node_execution_state_changed = _rendering_suite.pyqtSignal()

            def __init__(
                self,
                preference_bridge: _GraphCanvasTypographyPreferenceBridge,
                view_bridge: _rendering_suite.ViewportBridge,
            ) -> None:
                super().__init__()
                self._preference_bridge = preference_bridge
                self._view_bridge = view_bridge
                self._preference_bridge.graphics_preferences_changed.connect(self.graphics_preferences_changed.emit)

            @_rendering_suite.pyqtProperty(_rendering_suite.QObject, constant=True)
            def viewport_bridge(self) -> _rendering_suite.ViewportBridge:
                return self._view_bridge

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_minimap_expanded(self) -> bool:
                return bool(self._preference_bridge.graphics_minimap_expanded)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_grid(self) -> bool:
                return bool(self._preference_bridge.graphics_show_grid)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_grid_style(self) -> str:
                return str(self._preference_bridge.graphics_grid_style)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_edge_crossing_style(self) -> str:
                return str(self._preference_bridge.graphics_edge_crossing_style)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_minimap(self) -> bool:
                return bool(self._preference_bridge.graphics_show_minimap)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_show_port_labels(self) -> bool:
                return bool(self._preference_bridge.graphics_show_port_labels)

            @_rendering_suite.pyqtProperty(str, notify=graphics_preferences_changed)
            def graphics_node_elapsed_time_unit(self) -> str:
                return str(self._preference_bridge.graphics_node_elapsed_time_unit)

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_floating_toolbar_opens_on_hover(self) -> bool:
                return bool(
                    self._preference_bridge.graphics_node_floating_toolbar_opens_on_hover
                )

            @_rendering_suite.pyqtProperty(bool, notify=graphics_preferences_changed)
            def graphics_node_shadow(self) -> bool:
                return True

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_strength(self) -> int:
                return 70

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_softness(self) -> int:
                return 50

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_shadow_offset(self) -> int:
                return 4

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_graph_label_pixel_size(self) -> int:
                return int(self._preference_bridge.graphics_graph_label_pixel_size)

            @_rendering_suite.pyqtProperty("QVariant", notify=graphics_preferences_changed)
            def graphics_graph_node_icon_pixel_size_override(self) -> int | None:
                return self._preference_bridge.graphics_graph_node_icon_pixel_size_override

            @_rendering_suite.pyqtProperty(int, notify=graphics_preferences_changed)
            def graphics_node_title_icon_pixel_size(self) -> int:
                return int(self._preference_bridge.graphics_node_title_icon_pixel_size)

            @_rendering_suite.pyqtProperty("QVariantList", notify=scene_nodes_changed)
            def nodes_model(self) -> list[dict[str, object]]:
                return [dict(node_payload)]

            @_rendering_suite.pyqtProperty("QVariantList", constant=True)
            def backdrop_nodes_model(self) -> list[dict[str, object]]:
                return []

            @_rendering_suite.pyqtProperty("QVariantList", constant=True)
            def edges_model(self) -> list[dict[str, object]]:
                return []

            @_rendering_suite.pyqtProperty("QVariantMap", constant=True)
            def selected_node_lookup(self) -> dict[str, bool]:
                return {}

            @_rendering_suite.pyqtProperty("QVariantMap", constant=True)
            def workspace_scene_bounds_payload(self) -> dict[str, float]:
                return {}

            @_rendering_suite.pyqtProperty("QVariantMap", notify=failure_highlight_changed)
            def failed_node_lookup(self) -> dict[str, bool]:
                return {}

            @_rendering_suite.pyqtProperty(str, notify=failure_highlight_changed)
            def failed_node_title(self) -> str:
                return ""

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_lookup(self) -> dict[str, bool]:
                return {node_id: True}

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def completed_node_lookup(self) -> dict[str, bool]:
                return {}

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def running_node_started_at_ms_lookup(self) -> dict[str, float]:
                return {node_id: started_at_ms}

            @_rendering_suite.pyqtProperty("QVariantMap", notify=node_execution_state_changed)
            def node_elapsed_ms_lookup(self) -> dict[str, float]:
                return {}

            @_rendering_suite.pyqtProperty(int, notify=node_execution_state_changed)
            def node_execution_revision(self) -> int:
                return 1

        self.canvas.deleteLater()
        self.app.processEvents()

        canvas_state_bridge = CanvasStateBridgeStub(preference_bridge, self.view)
        canvas_command_bridge = _rendering_suite.GraphCanvasCommandBridge(
            search_scope_controller=self.canvas_source,  # type: ignore[arg-type]
            app_preferences_source=self.canvas_source,  # type: ignore[arg-type]
            run_controller=self.canvas_source,  # type: ignore[arg-type]
            inspector_source=self.canvas_source,  # type: ignore[arg-type]
            library_source=self.canvas_source,  # type: ignore[arg-type]
            workspace_edit_controller=self.canvas_source,  # type: ignore[arg-type]
            workspace_drop_connect_controller=self.canvas_source,  # type: ignore[arg-type]
            graphics_source=preference_bridge,  # type: ignore[arg-type]
            view_bridge=self.view,
        )
        self.addCleanup(self.app.processEvents)
        self.addCleanup(preference_bridge.deleteLater)
        self.addCleanup(canvas_command_bridge.deleteLater)
        self.addCleanup(canvas_state_bridge.deleteLater)
        self.canvas = self._create_canvas(
            {
                "canvasStateBridge": canvas_state_bridge,
                "canvasCommandBridge": canvas_command_bridge,
                "width": 1280.0,
                "height": 720.0,
            }
        )

        _rendering_suite.wait_for_condition_or_raise(
            lambda: len(_rendering_suite._named_child_items(self.canvas, "graphNodeCard")) == 1,
            timeout_ms=200,
            app=self.app,
            timeout_message="Timed out waiting for graph canvas typography host to appear.",
        )
        node_card = _rendering_suite._named_child_items(self.canvas, "graphNodeCard")[0]
        typography = node_card.findChild(_rendering_suite.QObject, "graphSharedTypography")
        title = node_card.findChild(_rendering_suite.QObject, "graphNodeTitle")
        elapsed_timer = node_card.findChild(_rendering_suite.QObject, "graphNodeElapsedTimer")
        elapsed_timer_badge = node_card.findChild(_rendering_suite.QObject, "graphNodeElapsedTimerBadge")
        input_labels = _rendering_suite._named_child_items(node_card, "graphNodeInputPortLabel")
        output_labels = _rendering_suite._named_child_items(node_card, "graphNodeOutputPortLabel")
        data_input_label = next(
            item for item in input_labels if str(item.property("text") or "") == "Payload"
        )
        result_output_label = next(
            item for item in output_labels if str(item.property("text") or "") == "Result"
        )

        self.assertIsNotNone(typography)
        self.assertIsNotNone(title)
        self.assertIsNotNone(elapsed_timer)
        self.assertIsNotNone(elapsed_timer_badge)
        if typography is None or title is None or elapsed_timer is None or elapsed_timer_badge is None:
            self.fail("Expected graph canvas typography host chrome items to exist")

        _rendering_suite.wait_for_condition_or_raise(
            lambda: bool(elapsed_timer.property("visible")) and bool(elapsed_timer.property("liveElapsedActive")),
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for live elapsed footer to appear on the typography host.",
        )

        self.assertEqual(int(typography.property("nodeTitlePixelSize")), 12)
        self.assertEqual(title.property("font").pixelSize(), 12)
        self.assertEqual(title.property("font").weight(), int(typography.property("nodeTitleFontWeight")))
        self.assertEqual(data_input_label.property("font").pixelSize(), 10)
        self.assertEqual(data_input_label.property("font").weight(), int(typography.property("portLabelFontWeight")))
        self.assertEqual(result_output_label.property("font").pixelSize(), 10)
        self.assertEqual(result_output_label.property("font").weight(), int(typography.property("portLabelFontWeight")))
        self.assertEqual(elapsed_timer.property("font").pixelSize(), 10)
        elapsed_badge_color = elapsed_timer_badge.property("color")
        node_fill_color = node_card.property("surfaceColor")
        self.assertAlmostEqual(elapsed_badge_color.alphaF(), 1.0)
        self.assertEqual(elapsed_badge_color.rgb(), node_fill_color.rgb())

        preference_bridge.set_graphics_graph_label_pixel_size_value(16)
        _rendering_suite.wait_for_condition_or_raise(
            lambda: int(typography.property("nodeTitlePixelSize")) == 18
            and title.property("font").pixelSize() == 18
            and data_input_label.property("font").pixelSize() == 16
            and result_output_label.property("font").pixelSize() == 16
            and elapsed_timer.property("font").pixelSize() == 16,
            timeout_ms=300,
            app=self.app,
            timeout_message="Timed out waiting for graph typography preference updates to reach host chrome.",
        )

        self.assertEqual(title.property("font").weight(), int(typography.property("nodeTitleFontWeight")))
        self.assertEqual(data_input_label.property("font").weight(), int(typography.property("portLabelFontWeight")))
        self.assertEqual(result_output_label.property("font").weight(), int(typography.property("portLabelFontWeight")))

    def test_node_execution_visualization_graph_canvas_host_chrome_follows_bridge_state_priority(self) -> None:
        self._assert_persistent_node_elapsed_footer_rendering()

    def test_persistent_node_elapsed_footer_graph_canvas_host_renders_live_and_cached_timing_states(self) -> None:
        self._assert_persistent_node_elapsed_footer_rendering()


def build_graph_canvas_qml_preference_binding_subprocess_suite(
    loader: unittest.TestLoader,
) -> unittest.TestSuite:
    return build_graph_canvas_qml_preference_subprocess_suite(
        loader,
        GraphCanvasQmlPreferenceBindingTests,
    )


def load_tests(loader: unittest.TestLoader, _tests, _pattern):  # noqa: ANN001
    return build_graph_canvas_qml_preference_binding_subprocess_suite(loader)


__all__ = [
    "GraphCanvasQmlPreferenceBindingTests",
    "build_graph_canvas_qml_preference_binding_subprocess_suite",
]


if __name__ == "__main__":
    unittest.main()
