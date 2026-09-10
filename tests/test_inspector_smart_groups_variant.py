from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal
from PyQt6.QtQml import QJSEngine, QQmlComponent, QQmlEngine
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.icon_registry import UiIconRegistryBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHELL_COMPONENTS_DIR = (
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "shell"
)
_INSPECTOR_FILTER_JS_PATH = _SHELL_COMPONENTS_DIR / "InspectorFilter.js"
_SMART_GROUPS_BODY_QML_PATH = _SHELL_COMPONENTS_DIR / "InspectorSmartGroupsBody.qml"


def _load_filter_engine() -> QJSEngine:
    source = _INSPECTOR_FILTER_JS_PATH.read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(".pragma")
    )
    engine = QJSEngine()
    result = engine.evaluate(stripped)
    if result.isError():
        raise RuntimeError(f"InspectorFilter.js failed to load: {result.toString()}")
    return engine


def _evaluate_helper(engine: QJSEngine, fn_name: str, items: list[dict]) -> object:
    payload = json.dumps(items)
    expression = f"JSON.stringify({fn_name}({payload}))"
    result = engine.evaluate(expression)
    if result.isError():
        raise RuntimeError(f"{fn_name} failed: {result.toString()}")
    return json.loads(result.toString())


class InspectorSmartGroupsJsHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._engine = _load_filter_engine()

    def test_smart_groups_surface_dirty_driven_and_required_sections(self) -> None:
        items = [
            {"key": "a", "label": "A", "dirty": True},
            {"key": "b", "label": "B", "driven_by": "port.in"},
            {"key": "c", "label": "C", "overridden_by_input": True},
            {"key": "d", "label": "D", "required": True},
            {"key": "e", "label": "E"},
        ]

        sections = _evaluate_helper(self._engine, "smartGroups", items)

        kinds = [section["kind"] for section in sections]
        self.assertEqual(kinds, ["modified", "driven", "required"])
        driven_keys = [prop["key"] for prop in sections[1]["items"]]
        self.assertEqual(set(driven_keys), {"b", "c"})
        accents = {section["kind"]: section["accent"] for section in sections}
        self.assertEqual(
            accents,
            {"modified": "edge_warning", "driven": "accent", "required": "run_failed"},
        )

    def test_smart_groups_omits_empty_sections(self) -> None:
        items = [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}]
        sections = _evaluate_helper(self._engine, "smartGroups", items)
        self.assertEqual(sections, [])

    def test_group_property_items_preserves_first_seen_order_and_defaults(self) -> None:
        items = [
            {"key": "a", "group": "Source"},
            {"key": "b", "group": ""},
            {"key": "c", "group": "Source"},
            {"key": "d"},
        ]

        groups = _evaluate_helper(self._engine, "groupPropertyItems", items)

        self.assertEqual([group["name"] for group in groups], ["Source", "Properties"])
        props_by_group = {group["name"]: [prop["key"] for prop in group["items"]] for group in groups}
        self.assertEqual(props_by_group["Source"], ["a", "c"])
        self.assertEqual(props_by_group["Properties"], ["b", "d"])


class _StubPane(QObject):
    """Minimal stand-in for ShellInspectorPane used purely by the smart groups body.

    Only the attributes read by the body / its nested editors are exposed; calling
    into the real inspector bridge is avoided since this test targets layout only.
    """

    changed = pyqtSignal()

    def __init__(
        self,
        palette: dict,
        ui_icons: QObject | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = dict(palette)
        self._ui_icons = ui_icons

    @pyqtProperty("QVariantMap", notify=changed)
    def themePalette(self):  # type: ignore[override]
        return self._palette

    @pyqtProperty(bool, notify=changed)
    def isPinInspector(self) -> bool:
        return False

    @pyqtProperty("QVariantList", notify=changed)
    def pinDataTypeOptions(self):
        return []

    @pyqtProperty(QObject, notify=changed)
    def inspectorBridgeRef(self):
        return None

    @pyqtProperty(QObject, notify=changed)
    def graphCanvasStateBridgeRef(self):
        return None

    @pyqtProperty(QObject, notify=changed)
    def uiIconsRef(self):
        return self._ui_icons

    @pyqtProperty(str, notify=changed)
    def selectedSurfaceColor(self) -> str:
        return "#3B82F6"


class InspectorSmartGroupsBodyQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        cls._app = QApplication.instance() or QApplication([])

    def _walk(self, item):
        yield item
        child_items = getattr(item, "childItems", None)
        if not callable(child_items):
            return
        for child in child_items():
            yield from self._walk(child)

    def _find_by_name(self, root, object_name: str):
        for node in self._walk(root):
            if node.objectName() == object_name:
                return node
        return None

    def _find_all_by_name(self, root, object_name: str):
        return [node for node in self._walk(root) if node.objectName() == object_name]

    def _load_component(self, initial_property_items: list[dict]):
        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_dark")
        ui_icons = UiIconRegistryBridge()
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("uiIcons", ui_icons)
        engine.addImportPath(str(_SHELL_COMPONENTS_DIR.parent))

        pane = _StubPane(palette=theme_bridge.palette, ui_icons=ui_icons)

        component = QQmlComponent(engine, QUrl.fromLocalFile(str(_SMART_GROUPS_BODY_QML_PATH)))
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(f"Failed to load InspectorSmartGroupsBody.qml:\n{errors}")
        initial_properties = {
            "pane": pane,
            "propertyItems": list(initial_property_items),
        }
        obj = component.createWithInitialProperties(initial_properties)
        if obj is None:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(f"Failed to instantiate InspectorSmartGroupsBody.qml:\n{errors}")
        self._app.processEvents()
        return obj, engine, pane, theme_bridge, ui_icons

    def test_runtime_schema_refresh_preserves_focused_draft_and_selection_changes_immediately(self) -> None:
        from types import SimpleNamespace
        import numpy as np
        from PyQt6.QtCore import QPoint, QPointF, Qt
        from PyQt6.QtQuick import QQuickItem, QQuickWindow
        from PyQt6.QtTest import QTest
        from ea_node_editor.graph.model import GraphModel
        from ea_node_editor.nodes.bootstrap import build_default_registry
        from ea_node_editor.runtime_contracts import DataTree, SettledPortResult
        from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value
        from ea_node_editor.ui.shell.presenters.inspector_presenter import ShellInspectorPresenter

        class Host(QObject):
            selected_node_changed = pyqtSignal()
            workspace_state_changed = pyqtSignal()
            node_execution_state_changed = pyqtSignal()

        host = Host()
        host.registry = build_default_registry()
        host.model = GraphModel()
        workspace = host.model.active_workspace
        source = host.model.add_node(workspace.workspace_id, "core.python_script", "Source", 0., 0.)
        node = host.model.add_node(workspace.workspace_id, "plot.signal", "Signal", 200., 0.)
        host.model.add_edge(workspace.workspace_id, source.node_id, "result", node.node_id, "values")
        selected = [node]
        host.workspace_selection_context = SimpleNamespace(selected_node_context=lambda: (selected[0], host.registry.get_spec(selected[0].type_id)))
        host.workspace_manager = SimpleNamespace(active_workspace_id=lambda: workspace.workspace_id)
        host._SUBNODE_PIN_TYPE_IDS = set()
        host.project_path = ""
        record = {"record_id": "current", "outputs_available": True, "outputs": {}}
        fact = SimpleNamespace(retained_record_id="current", freshness=SimpleNamespace(value="current"))
        host.run_state = SimpleNamespace(node_solution_facts_by_workspace_id={workspace.workspace_id: {source.node_id: fact}}, cached_node_output_records_by_workspace_id={workspace.workspace_id: {source.node_id: {"current": record}}})

        def set_width(width):
            record["outputs"]["result"] = SettledPortResult(status="value", value=DataTree.from_item(snapshot_scientific_value(np.ones((3, width)))))

        set_width(2)
        presenter = ShellInspectorPresenter(host)

        def items():
            return [dict(item, group_default_open=True) for item in presenter.selected_node_property_items if item["key"] == "x_column"]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items())
        window = QQuickWindow()
        window.resize(440, 500)
        blur_target = QQuickItem(window.contentItem())
        body.setParentItem(window.contentItem())
        body.setWidth(420)
        refreshes = []

        def refresh():
            refreshes.append(True)
            body.setProperty("propertyItems", items())

        presenter.inspector_state_changed.connect(refresh)
        try:
            window.show()
            window.requestActivate()
            QTest.qWait(30)
            self._app.processEvents()
            selector = next(item for item in self._find_all_by_name(body, "inspectorEditableComboEditor") if item.isVisible())
            point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2))
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y())))
            selector.setProperty("editText", "unfinished exact name")
            self.assertTrue(selector.property("activeFocus"))
            set_width(4)
            host.node_execution_state_changed.emit()
            self._app.processEvents()
            self.assertTrue(presenter._runtime_schema_pending)
            self.assertEqual(refreshes, [])
            self.assertEqual(selector.property("editText"), "unfinished exact name")
            self.assertTrue(selector.property("activeFocus"))
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(435, 490))
            blur_target.forceActiveFocus()
            QTest.qWait(10)
            self._app.processEvents()
            self.assertEqual(len(refreshes), 1)
            self.assertEqual(items()[0]["enum_codes"], [0, 1, 2, 3])
            host.node_execution_state_changed.emit()
            self.assertEqual(len(refreshes), 1)
            selector = next(item for item in self._find_all_by_name(body, "inspectorEditableComboEditor") if item.isVisible())
            point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2))
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y())))
            set_width(5)
            host.node_execution_state_changed.emit()
            self.assertTrue(presenter._runtime_schema_pending)
            host.model.add_edge(workspace.workspace_id, source.node_id, "result", node.node_id, "x_column")
            host.workspace_state_changed.emit()
            self.assertFalse(presenter._runtime_schema_pending)
            self.assertFalse(items()[0]["editor_enabled"])
            presenter._runtime_schema_pending = True
            selected[0] = source
            host.selected_node_changed.emit()
            self.assertFalse(presenter._runtime_schema_pending)
            self.assertEqual(body.property("propertyItems"), [])
        finally:
            presenter.shutdown()
            window.close()
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_component_loads_and_exposes_static_groups(self) -> None:
        items = [
            {"key": "source_path", "label": "Source Path", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "comment", "label": "Comment", "group": "", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorStaticGroupHeader_Source"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorStaticGroupHeader_Properties"))
            self.assertIsNone(self._find_by_name(body, "inspectorSmartGroupHeader_modified"))
            self.assertIsNone(self._find_by_name(body, "inspectorSmartGroupHeader_driven"))
            self.assertIsNone(self._find_by_name(body, "inspectorSmartGroupHeader_required"))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_declared_interval_and_searchable_enum_editors_load_disabled(self) -> None:
        items = [
            {
                "key": "result_bound",
                "label": "Result bound",
                "type": "interval_1d",
                "editor_mode": "interval_slider",
                "value": {"start": 8.0, "end": 2.0},
                "display_value": {"start": 8.0, "end": 2.0},
                "display_value_available": True,
                "minimum": 0.0,
                "maximum": 10.0,
                "step": 0.5,
                "interval_direction": "decreasing",
                "condition_enabled": False,
                "editor_enabled": False,
                "editor_disabled_reason": "Available when Mode is Manual.",
            },
            {
                "key": "color_map",
                "label": "Color map",
                "editor_mode": "enum",
                "value": "Rainbow",
                "display_value": "Rainbow",
                "display_value_available": True,
                "enum_values": ["Rainbow", "Viridis"],
                "searchable": True,
                "editor_enabled": False,
                "editor_disabled_reason": "Available when Mode is Manual.",
            },
        ]
        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.toggleGroup("static", "Properties")
            self._app.processEvents()
            interval = self._find_by_name(body, "inspectorIntervalSlider")
            searchable = self._find_by_name(body, "inspectorSearchableEnumEditor")

            self.assertIsNotNone(interval)
            self.assertFalse(bool(interval.property("enabled")))
            self.assertAlmostEqual(float(interval.property("semanticStart")), 8.0)
            self.assertAlmostEqual(float(interval.property("semanticEnd")), 2.0)
            self.assertIsNotNone(searchable)
            self.assertFalse(bool(searchable.property("enabled")))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_smart_group_headers_appear_when_flagged_items_present(self) -> None:
        items = [
            {"key": "a", "label": "A", "group": "Source", "editor_mode": "text", "value": "", "dirty": True},
            {"key": "b", "label": "B", "group": "Source", "editor_mode": "text", "value": "", "overridden_by_input": True},
            {"key": "c", "label": "C", "group": "Post", "editor_mode": "text", "value": "", "required": True},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorSmartGroupHeader_modified"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorSmartGroupHeader_driven"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorSmartGroupHeader_required"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorStaticGroupHeader_Source"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorStaticGroupHeader_Post"))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_property_groups_start_collapsed_and_toggle_open(self) -> None:
        items = [
            {"key": "a", "label": "A", "group": "Source", "editor_mode": "text", "value": "", "dirty": True},
            {"key": "b", "label": "B", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            smart_body = self._find_by_name(body, "inspectorSmartGroupBody_modified")
            static_body = self._find_by_name(body, "inspectorStaticGroupBody_Source")
            self.assertIsNotNone(smart_body)
            self.assertIsNotNone(static_body)
            self.assertFalse(smart_body.property("visible"))
            self.assertFalse(static_body.property("visible"))

            body.toggleGroup("modified", "Modified")
            body.toggleGroup("static", "Source")
            self._app.processEvents()
            self.assertTrue(smart_body.property("visible"))
            self.assertTrue(static_body.property("visible"))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_property_group_can_request_initial_open_without_overriding_user_toggle(self) -> None:
        items = [
            {
                "key": "setup",
                "label": "Workflow",
                "group": "Setup",
                "editor_mode": "summary",
                "value": "Choose result file",
                "group_default_open": True,
            }
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            static_body = self._find_by_name(body, "inspectorStaticGroupBody_Setup")
            self.assertIsNotNone(static_body)
            self.assertTrue(static_body.property("visible"))

            body.setProperty(
                "propertyItems",
                [
                    {
                        "key": "setup",
                        "label": "Workflow",
                        "group": "Setup",
                        "editor_mode": "summary",
                        "value": "Ready",
                        "group_default_open": False,
                    }
                ],
            )
            self._app.processEvents()
            static_body = self._find_by_name(body, "inspectorStaticGroupBody_Setup")
            self.assertIsNotNone(static_body)
            self.assertTrue(static_body.property("visible"))

            body.toggleGroup("static", "Setup")
            self._app.processEvents()
            static_body = self._find_by_name(body, "inspectorStaticGroupBody_Setup")
            self.assertIsNotNone(static_body)
            self.assertFalse(static_body.property("visible"))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_filter_bar_is_present_at_top_of_body(self) -> None:
        items = [{"key": "a", "label": "A", "group": "Source", "editor_mode": "text", "value": ""}]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorSmartGroupsFilterBar"))
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_summary_property_editor_renders_read_only_preview(self) -> None:
        items = [
            {
                "key": "array_slice_2d_summary",
                "label": "Preview",
                "group": "Selection",
                "editor_mode": "summary",
                "value": "Rows 1-50, Columns A-AX",
                "attention_required": True,
            }
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.toggleGroup("static", "Selection")
            self._app.processEvents()

            summary = self._find_by_name(body, "inspectorPropertySummaryValue")
            self.assertIsNotNone(summary)
            self.assertEqual(summary.property("propertyKey"), "array_slice_2d_summary")
            status = self._find_by_name(body, "inspectorPropertyStatusChip")
            self.assertIsNotNone(status)
            self.assertEqual(status.property("propertyKey"), "array_slice_2d_summary")
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()

    def test_axis_compact_property_editor_renders_axis_controls(self) -> None:
        items = [
            {
                "key": "plot_axis_x",
                "label": "X Axis",
                "group": "Axes",
                "editor_mode": "axis_compact",
                "value": {"axis": "x", "min": 0, "max": 10, "log": False},
                "help_text": "Auto range unless Min or Max is set.",
                "fields": [
                    {
                        "key": "axis_limit_x_min",
                        "role": "min",
                        "label": "Min",
                        "type": "float",
                        "editor_mode": "text",
                        "value": 0,
                        "placeholder_text": "Auto",
                        "reset_value": "",
                    },
                    {
                        "key": "axis_limit_x_max",
                        "role": "max",
                        "label": "Max",
                        "type": "float",
                        "editor_mode": "text",
                        "value": 10,
                        "placeholder_text": "Auto",
                        "reset_value": "",
                    },
                    {
                        "key": "log_scale_x",
                        "role": "log",
                        "label": "Scale",
                        "type": "bool",
                        "editor_mode": "toggle",
                        "value": False,
                        "reset_value": False,
                    },
                ],
            },
            {
                "key": "plot_axis_y",
                "label": "Y Axis",
                "group": "Axes",
                "editor_mode": "axis_compact",
                "value": {"axis": "y", "min": "", "max": "", "log": True},
                "fields": [
                    {
                        "key": "axis_limit_y_min",
                        "role": "min",
                        "label": "Min",
                        "type": "float",
                        "editor_mode": "text",
                        "value": "",
                        "placeholder_text": "Auto",
                        "reset_value": "",
                    },
                    {
                        "key": "axis_limit_y_max",
                        "role": "max",
                        "label": "Max",
                        "type": "float",
                        "editor_mode": "text",
                        "value": "",
                        "placeholder_text": "Auto",
                        "reset_value": "",
                    },
                    {
                        "key": "log_scale_y",
                        "role": "log",
                        "label": "Scale",
                        "type": "bool",
                        "editor_mode": "toggle",
                        "value": True,
                        "reset_value": False,
                    },
                ],
            },
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.toggleGroup("static", "Axes")
            self._app.processEvents()

            axis_rows = self._find_all_by_name(body, "inspectorAxisCompactEditor")
            self.assertEqual({row.property("propertyKey") for row in axis_rows}, {"plot_axis_x", "plot_axis_y"})
            min_editors = self._find_all_by_name(body, "inspectorAxisCompactMinEditor")
            max_editors = self._find_all_by_name(body, "inspectorAxisCompactMaxEditor")
            scale_toggles = self._find_all_by_name(body, "inspectorAxisCompactLogToggle")
            reset_buttons = self._find_all_by_name(body, "inspectorAxisCompactResetButton")
            self.assertEqual({editor.property("propertyKey") for editor in min_editors}, {"axis_limit_x_min", "axis_limit_y_min"})
            self.assertEqual({editor.property("propertyKey") for editor in max_editors}, {"axis_limit_x_max", "axis_limit_y_max"})
            self.assertEqual({toggle.property("propertyKey") for toggle in scale_toggles}, {"log_scale_x", "log_scale_y"})
            self.assertEqual({button.property("propertyKey") for button in reset_buttons}, {"plot_axis_x", "plot_axis_y"})
        finally:
            body.deleteLater()
            engine.deleteLater()
            pane.deleteLater()
            theme_bridge.deleteLater()
            ui_icons.deleteLater()
            self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
