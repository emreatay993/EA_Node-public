from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import Q_ARG, QObject, QMetaObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox

from ea_node_editor.nodes.node_specs import (
    NodeTypeSpec,
    PortSpec,
    PropertyConditionSpec,
    PropertySpec,
)
from ea_node_editor.persistence.project_codec import JsonProjectCodec
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    INTERVAL_1D_DATA_TYPE,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    JSON_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
    Interval1D,
)
from ea_node_editor.ui.theme.tokens import STITCH_DARK_V1
from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.qt_wait import wait_for_condition_or_raise
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtQml import QJSValue
from PyQt6.QtTest import QTest

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.runtime_contracts import DataTree


def _color_name(value: object) -> str:
    return QColor(value).name(QColor.NameFormat.HexRgb)


class MainWindowShellViewLibraryInspectorTests(SharedMainWindowShellTestBase):
    def _walk_items(self, item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from self._walk_items(child)

    def _pane_child_item(self, pane: QObject, object_name: str) -> QQuickItem:
        self.assertIsInstance(pane, QQuickItem)
        for item in self._walk_items(pane):
            if item.objectName() == object_name:
                return item
        self.fail(f"Could not find {object_name!r} under pane {pane.objectName()!r}.")

    def _item_widget_point(self, item: QQuickItem, x: float, y: float) -> QPoint:
        item_window = item.window()
        self.assertIsNotNone(item_window)
        scene_point = item.mapToScene(QPointF(x, y))
        global_point = item_window.mapToGlobal(
            QPoint(round(scene_point.x()), round(scene_point.y()))
        )
        return self.window.quick_widget.mapFromGlobal(global_point)

    def _move_mouse_to_shell_center(self) -> None:
        QTest.mouseMove(
            self.window.quick_widget,
            QPoint(
                self.window.quick_widget.width() // 2,
                self.window.quick_widget.height() // 2,
            ),
        )
        self.app.processEvents()

    def _inspector_object(self, name: str) -> QObject:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        item = root_object.findChild(QObject, name)
        self.assertIsNotNone(item)
        return item

    def _inspector_property_object(self, object_name: str, property_key: str) -> QQuickItem:
        item = self._find_inspector_property_object(object_name, property_key)
        if item is not None:
            return item
        self.fail(f"Could not find {object_name!r} for property {property_key!r}.")

    def _find_inspector_property_object(self, object_name: str, property_key: str) -> QQuickItem | None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        for item in self._walk_items(root_object):
            if item.objectName() != object_name:
                continue
            if str(item.property("propertyKey")) != property_key:
                continue
            if not bool(item.property("visible")):
                continue
            return item
        return None

    @staticmethod
    def _variant_value(value):  # noqa: ANN001
        if isinstance(value, QJSValue):
            return value.toVariant()
        return value

    def _library_item(self, type_id: str) -> dict[str, object]:
        return next(
            item
            for item in self.window.filtered_node_library_items
            if item.get("type_id") == type_id
        )

    def _strip_child(self, strip: QObject, object_name: str) -> QObject:
        child = strip.findChild(QObject, object_name)
        self.assertIsNotNone(child)
        return child

    def _tab_strip_slots(self, strip: QObject) -> list[QQuickItem]:
        slots = strip.property("tabSlots")
        if isinstance(slots, QJSValue):
            slots = slots.toVariant()
        return sorted(
            [slot for slot in (slots or []) if isinstance(slot, QQuickItem)],
            key=lambda slot: float(slot.property("x")),
        )

    def _active_tab_slot(self, strip: QObject) -> QQuickItem:
        for slot in self._tab_strip_slots(strip):
            for child in slot.children():
                if isinstance(child, QQuickItem) and bool(child.property("active")):
                    return slot
        self.fail(f"Expected an active tab slot under strip {strip.objectName()!r}.")

    def _tab_slot_fully_visible(self, strip: QObject, slot: QQuickItem) -> bool:
        viewport_width = float(strip.property("tabsViewportWidth"))
        content_x = float(strip.property("tabsContentX"))
        slot_left = float(slot.property("x")) - content_x
        slot_right = slot_left + float(slot.property("width"))
        return slot_left >= -0.5 and slot_right <= viewport_width + 0.5

    def _scene_node_payload(self, node_id: str) -> dict[str, object]:
        return next(
            node
            for node in self.window.scene.nodes_model
            if node.get("node_id") == node_id
        )

    def _screen_point_for_port(self, node_id: str, port_key: str) -> tuple[float, float]:
        graph_canvas = self._graph_canvas_item()
        node_payload = self._scene_node_payload(node_id)
        port_payload = next(
            port
            for port in node_payload.get("ports", [])
            if port.get("key") == port_key
        )
        point = self._variant_value(graph_canvas._scenePortPoint(node_payload, port_payload, 0, 0))
        screen_x = float(graph_canvas.sceneToScreenX(point["x"]))
        screen_y = float(graph_canvas.sceneToScreenY(point["y"]))
        return screen_x, screen_y

    def _register_interval_inspector_fixture(self) -> tuple[str, str]:
        type_id = "tests.inspector_interval"
        source_type_id = "tests.inspector_interval_source"
        spec = NodeTypeSpec(
            type_id=type_id,
            display_name="Inspector Interval",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "result_bound",
                    "in",
                    "data",
                    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
                    required=False,
                    uses_property_default=True,
                ),
            ),
            properties=(
                PropertySpec(
                    key="mode",
                    type="enum",
                    default="Manual",
                    label="Mode",
                    enum_values=("None", "Manual"),
                    inline_editor="enum",
                ),
                PropertySpec(
                    key="color_map",
                    type="enum",
                    default="Alpha",
                    label="Color map",
                    enum_values=("Alpha", "Alphabet", "Palpha"),
                    inline_editor="enum",
                    searchable=True,
                ),
                PropertySpec(
                    key="result_bound",
                    type=INTERVAL_1D_DATA_TYPE,
                    default=Interval1D(2.0, 8.0),
                    label="Result bound",
                    minimum=0.0,
                    maximum=10.0,
                    step=0.5,
                    inline_editor="interval_slider",
                    interval_direction="increasing",
                    enabled_when=PropertyConditionSpec("mode", ("Manual",)),
                ),
            ),
        )
        self.window.registry.register_descriptor(spec, lambda: SimpleNamespace())
        self.window.registry.register_descriptor(
            NodeTypeSpec(
                type_id=source_type_id,
                display_name="Inspector Interval Source",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec(
                        "result",
                        "out",
                        "data",
                        INTERVAL_1D_GRAPH_DATA_TYPE_ID,
                    ),
                ),
                properties=(),
            ),
            lambda: SimpleNamespace(),
        )
        return type_id, source_type_id

    def test_qml_inspector_interval_commit_is_typed_single_undo_and_round_trips(self) -> None:
        type_id, source_type_id = self._register_interval_inspector_fixture()
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type(type_id, x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.window.shell_inspector_presenter.set_property_pane_variant("smart_groups")
        self.app.processEvents()

        inspector_pane = self._inspector_object("inspectorPane")
        smart_groups_body = self._pane_child_item(inspector_pane, "inspectorSmartGroupsBody")
        smart_groups_body.setProperty("expandedMap", {"static:Properties": True})
        wait_for_condition_or_raise(
            lambda: self._find_inspector_property_object(
                "inspectorIntervalSlider", "result_bound"
            )
            is not None,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for the Inspector Interval 1D editor.",
        )

        def interval_editor() -> QQuickItem:
            return self._inspector_property_object(
                "inspectorIntervalSlider", "result_bound"
            )

        current_interval_editor = interval_editor()
        def searchable_editor() -> QQuickItem:
            return self._inspector_property_object(
                "inspectorSearchableEnumEditor", "color_map"
            )

        def interval_has_state(
            *, enabled: bool, display_available: bool, start: float, end: float
        ) -> bool:
            editor = self._find_inspector_property_object(
                "inspectorIntervalSlider", "result_bound"
            )
            return (
                editor is not None
                and bool(editor.property("enabled")) is enabled
                and bool(editor.property("displayValueAvailable")) is display_available
                and float(editor.property("semanticStart")) == start
                and float(editor.property("semanticEnd")) == end
            )

        current_searchable_editor = searchable_editor()
        self.assertTrue(bool(current_interval_editor.property("enabled")))
        self.assertTrue(bool(current_searchable_editor.property("enabled")))
        self.assertAlmostEqual(float(current_interval_editor.property("semanticStart")), 2.0)
        self.assertAlmostEqual(float(current_interval_editor.property("semanticEnd")), 8.0)

        self.window.set_selected_node_property("mode", "None")
        wait_for_condition_or_raise(
            lambda: not bool(interval_editor().property("enabled")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Interval editor stayed enabled after its condition became false.",
        )
        self.window.set_selected_node_property("mode", "Manual")
        wait_for_condition_or_raise(
            lambda: bool(interval_editor().property("enabled")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Interval editor did not re-enable when its condition became true.",
        )

        workspace = self.window.model.project.workspaces[workspace_id]
        before_search_undo_depth = self.window.runtime_history.undo_depth(workspace_id)
        searchable_point = self._item_widget_point(
            searchable_editor(),
            float(searchable_editor().property("width")) * 0.4,
            float(searchable_editor().property("height")) * 0.5,
        )
        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            searchable_point,
        )
        QTest.keyClick(
            self.window.quick_widget,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClicks(self.window.quick_widget, "ALPHA")
        self.assertEqual(
            [
                str(option["value"])
                for option in self._variant_value(
                    searchable_editor().property("filteredOptions")
                )
            ],
            ["Alpha", "Alphabet", "Palpha"],
        )
        text_field = next(
            item
            for item in self._walk_items(searchable_editor())
            if item.metaObject().className().startswith("TextField")
        )
        text_field.forceActiveFocus()
        QTest.keyClick(
            self.window.quick_widget,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClicks(self.window.quick_widget, "Alphabet")
        self.assertEqual(searchable_editor().property("editText"), "Alphabet")
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
        wait_for_condition_or_raise(
            lambda: workspace.nodes[node_id].properties["color_map"] == "Alphabet",
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Inspector searchable enum Enter path did not commit its declared value.",
        )
        self.assertEqual(
            self.window.runtime_history.undo_depth(workspace_id),
            before_search_undo_depth + 1,
        )
        wait_for_condition_or_raise(
            lambda: self._find_inspector_property_object(
                "inspectorSearchableEnumEditor", "color_map"
            )
            is not None,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Inspector searchable enum did not reload after its declared commit.",
        )
        text_field = next(
            item
            for item in self._walk_items(searchable_editor())
            if item.metaObject().className().startswith("TextField")
        )
        text_field.forceActiveFocus()
        QTest.keyClick(
            self.window.quick_widget,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClicks(self.window.quick_widget, "Not declared")
        self.assertEqual(searchable_editor().property("editText"), "Not declared")
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(workspace.nodes[node_id].properties["color_map"], "Alphabet")
        self.assertEqual(
            self.window.runtime_history.undo_depth(workspace_id),
            before_search_undo_depth + 1,
        )

        before_undo_depth = self.window.runtime_history.undo_depth(workspace_id)
        QMetaObject.invokeMethod(
            interval_editor(),
            "commitRequested",
            Qt.ConnectionType.DirectConnection,
            Q_ARG("QVariant", {"start": 3.0, "end": 7.0}),
        )
        wait_for_condition_or_raise(
            lambda: workspace.nodes[node_id].properties["result_bound"]
            == Interval1D(3.0, 7.0),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Inspector interval commit did not reach the selected node.",
        )
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), before_undo_depth + 1)

        document = JsonProjectCodec().to_persistent_document(self.window.model.project)
        restored = JsonProjectCodec().from_document(json.loads(json.dumps(document)))
        self.assertEqual(
            restored.workspaces[workspace_id].nodes[node_id].properties["result_bound"],
            Interval1D(3.0, 7.0),
        )

        source_id = self.window.scene.add_node_from_type(source_type_id, x=-180.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.window.set_selected_node_property("result_bound", Interval1D(8.0, 2.0))
        edge_id = self.window.scene.add_edge(source_id, "result", node_id, "result_bound")
        self.window.run_state.cached_node_output_records_by_workspace_id.setdefault(workspace_id, {})[
            source_id
        ] = {
            "settled": {
                "record_id": "settled",
                "observed_at_epoch_ms": 1.0,
                "outputs": {
                    "result": SettledPortResult(
                        status="value",
                        value=DataTree.from_item(Interval1D(3.0, 7.0)),
                    ),
                },
            }
        }
        self.window.run_state.node_solution_facts_by_workspace_id.setdefault(
            workspace_id, {}
        )[source_id] = NodeSolutionFact(
            project_id=self.window.model.project.project_id,
            workspace_id=workspace_id,
            node_id=source_id,
            freshness=SolutionFreshness.CURRENT,
            revision=1,
            retained_record_id="settled",
            retained_solution_key="a" * 64,
            residency=SolutionResidency.SESSION,
            last_disposition=SolutionDisposition.RECOMPUTED,
        )
        self.window.graph_canvas_state_bridge.port_flow_state_changed.emit()
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: interval_has_state(
                enabled=False, display_available=True, start=3.0, end=7.0
            ),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Inspector did not show the settled upstream interval as a disabled override.",
        )
        self.assertEqual(workspace.nodes[node_id].properties["result_bound"], Interval1D(8.0, 2.0))

        self.assertTrue(self.window.scene.set_edge_enabled(edge_id, False))
        wait_for_condition_or_raise(
            lambda: interval_has_state(
                enabled=True, display_available=True, start=8.0, end=2.0
            ),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Inspector did not restore its authored interval after disabling the edge.",
        )
        self.assertEqual(workspace.nodes[node_id].properties["result_bound"], Interval1D(8.0, 2.0))

    def test_qml_side_panes_share_collapsible_shell_behavior(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        library_pane = root_object.findChild(QObject, "libraryPane")
        inspector_pane = root_object.findChild(QObject, "inspectorPane")

        self.assertIsNotNone(library_pane)
        self.assertIsNotNone(inspector_pane)

        for pane in (library_pane, inspector_pane):
            self.assertFalse(bool(pane.property("paneCollapsed")))
            QMetaObject.invokeMethod(pane, "collapsePane")
            wait_for_condition_or_raise(
                lambda pane=pane: float(pane.property("width")) <= 1.0,
                timeout_ms=2500,
                poll_interval_ms=20,
                app=self.app,
                timeout_message=lambda pane=pane: (
                    f"Pane width did not satisfy predicate within 2500ms: {pane.property('width')}"
                ),
            )
            self.assertTrue(bool(pane.property("paneCollapsed")))
            self.assertLessEqual(float(pane.property("width")), 1.0)

            QMetaObject.invokeMethod(pane, "expandPane")
            wait_for_condition_or_raise(
                lambda pane=pane: float(pane.property("width")) > 200.0,
                timeout_ms=2500,
                poll_interval_ms=20,
                app=self.app,
                timeout_message=lambda pane=pane: (
                    f"Pane width did not satisfy predicate within 2500ms: {pane.property('width')}"
                ),
            )
            self.assertFalse(bool(pane.property("paneCollapsed")))
            self.assertGreater(float(pane.property("width")), 200.0)

    def test_qml_workspace_console_pane_collapses_and_expands(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        console_pane = root_object.findChild(QObject, "workspaceConsolePane")

        self.assertIsNotNone(console_pane)
        self.assertFalse(bool(console_pane.property("paneCollapsed")))
        self.assertGreater(float(console_pane.property("height")), 150.0)

        QMetaObject.invokeMethod(console_pane, "collapsePane")
        wait_for_condition_or_raise(
            lambda: float(console_pane.property("height")) <= 32.0,
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message=lambda: (
                "Console pane height did not collapse within 2500ms: "
                f"{console_pane.property('height')}"
            ),
        )
        self.assertTrue(bool(console_pane.property("paneCollapsed")))

        QMetaObject.invokeMethod(console_pane, "expandPane")
        wait_for_condition_or_raise(
            lambda: float(console_pane.property("height")) > 150.0,
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message=lambda: (
                "Console pane height did not expand within 2500ms: "
                f"{console_pane.property('height')}"
            ),
        )
        self.assertFalse(bool(console_pane.property("paneCollapsed")))

    def test_qml_shell_pane_collapse_state_persists_across_window_restart(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        library_pane = root_object.findChild(QObject, "libraryPane")
        inspector_pane = root_object.findChild(QObject, "inspectorPane")
        console_pane = root_object.findChild(QObject, "workspaceConsolePane")

        self.assertIsNotNone(library_pane)
        self.assertIsNotNone(inspector_pane)
        self.assertIsNotNone(console_pane)

        for pane in (library_pane, inspector_pane, console_pane):
            QMetaObject.invokeMethod(pane, "collapsePane")

        expected = {
            "node_library": True,
            "property_pane": True,
            "output_panel": True,
        }

        wait_for_condition_or_raise(
            lambda: (
                self._app_preferences_path.exists()
                and json.loads(self._app_preferences_path.read_text(encoding="utf-8"))[
                    "graphics"
                ]["shell"]["panel_collapsed"]
                == expected
            ),
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Shell pane collapse preferences were not persisted.",
        )

        self._reopen_shared_window()
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        library_pane = root_object.findChild(QObject, "libraryPane")
        inspector_pane = root_object.findChild(QObject, "inspectorPane")
        console_pane = root_object.findChild(QObject, "workspaceConsolePane")

        self.assertIsNotNone(library_pane)
        self.assertIsNotNone(inspector_pane)
        self.assertIsNotNone(console_pane)

        wait_for_condition_or_raise(
            lambda: (
                bool(library_pane.property("paneCollapsed"))
                and bool(inspector_pane.property("paneCollapsed"))
                and bool(console_pane.property("paneCollapsed"))
                and float(library_pane.property("width")) <= 1.0
                and float(inspector_pane.property("width")) <= 1.0
                and float(console_pane.property("height")) <= 32.0
            ),
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Shell pane collapse preferences were not restored.",
        )

        self.assertLessEqual(float(library_pane.property("width")), 1.0)
        self.assertLessEqual(float(inspector_pane.property("width")), 1.0)
        self.assertLessEqual(float(console_pane.property("height")), 32.0)

    def test_qml_workspace_console_scrolls_and_resizes_vertically(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        console_pane = root_object.findChild(QObject, "workspaceConsolePane")
        self.assertIsNotNone(console_pane)

        output_scroll = self._pane_child_item(console_pane, "workspaceConsoleOutputScrollView")
        output_text_area = self._pane_child_item(console_pane, "workspaceConsoleOutputTextArea")
        resize_handle = self._pane_child_item(console_pane, "workspaceConsoleResizeHandle")

        for index in range(80):
            self.window.console_panel.append_log(
                "info",
                f"Scrollable console line {index:02d} with enough text to keep the output body realistic.",
            )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: (
                float(output_scroll.property("scrollContentHeight"))
                > float(output_scroll.property("scrollViewportHeight")) + 80.0
                and int(output_text_area.property("lineCount")) >= 80
            ),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Console output did not overflow the scroll viewport.",
        )

        self.assertAlmostEqual(float(output_scroll.property("scrollContentY")), 0.0, delta=1.0)
        QMetaObject.invokeMethod(output_scroll, "scrollToBottom")
        wait_for_condition_or_raise(
            lambda: float(output_scroll.property("scrollContentY")) > 40.0,
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Console output scroll view did not scroll vertically.",
        )

        initial_height = float(console_pane.property("height"))
        start_point = self._item_widget_point(
            resize_handle,
            float(resize_handle.width()) * 0.5,
            float(resize_handle.height()) * 0.5,
        )
        end_point = QPoint(start_point.x(), start_point.y() - 80)
        QTest.mousePress(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_point,
        )
        QTest.mouseMove(self.window.quick_widget, end_point)
        QTest.mouseRelease(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_point,
        )

        wait_for_condition_or_raise(
            lambda: float(console_pane.property("height")) > initial_height + 40.0,
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message=lambda: (
                "Console pane did not grow after dragging the vertical resize handle: "
                f"{console_pane.property('height')} from {initial_height}"
            ),
        )

    def test_qml_workspace_console_severity_tabs_switch_channels_and_clear_counts(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        console_pane = root_object.findChild(QObject, "workspaceConsolePane")
        self.assertIsNotNone(console_pane)

        self.window.console_panel.append_log("error", "Severity tab error")
        self.window.console_panel.append_log("warning", "Severity tab warning")
        self.app.processEvents()

        output_tab = self._pane_child_item(console_pane, "workspaceConsoleOutputTab")
        errors_tab = self._pane_child_item(console_pane, "workspaceConsoleErrorsTab")
        warnings_tab = self._pane_child_item(console_pane, "workspaceConsoleWarningsTab")
        clear_button = self._pane_child_item(console_pane, "workspaceConsoleClearButton")

        wait_for_condition_or_raise(
            lambda: (
                int(errors_tab.property("badgeValue")) == 1
                and int(warnings_tab.property("badgeValue")) == 1
            ),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Console severity badges did not reflect appended warning/error counts.",
        )
        self.assertTrue(bool(output_tab.property("active")))
        self.assertFalse(bool(errors_tab.property("active")))
        self.assertFalse(bool(warnings_tab.property("active")))

        warnings_point = self._item_widget_point(
            warnings_tab,
            float(warnings_tab.width()) * 0.5,
            float(warnings_tab.height()) * 0.5,
        )
        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            warnings_point,
        )
        wait_for_condition_or_raise(
            lambda: bool(warnings_tab.property("active")),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Warnings console tab did not become active after click.",
        )

        errors_point = self._item_widget_point(
            errors_tab,
            float(errors_tab.width()) * 0.5,
            float(errors_tab.height()) * 0.5,
        )
        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            errors_point,
        )
        wait_for_condition_or_raise(
            lambda: bool(errors_tab.property("active")),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Errors console tab did not become active after click.",
        )

        clear_point = self._item_widget_point(
            clear_button,
            float(clear_button.width()) * 0.5,
            float(clear_button.height()) * 0.5,
        )
        QTest.mouseClick(
            self.window.quick_widget,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            clear_point,
        )
        wait_for_condition_or_raise(
            lambda: (
                self.window.console_panel.error_count == 0
                and self.window.console_panel.warning_count == 0
                and int(errors_tab.property("badgeValue")) == 0
                and int(warnings_tab.property("badgeValue")) == 0
            ),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Console Clear did not reset severity badge counts.",
        )

    def test_qml_collapsed_side_pane_handles_reveal_only_on_edge_hover(self) -> None:
        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        library_pane = root_object.findChild(QObject, "libraryPane")
        inspector_pane = root_object.findChild(QObject, "inspectorPane")

        self.assertIsNotNone(library_pane)
        self.assertIsNotNone(inspector_pane)

        for pane in (library_pane, inspector_pane):
            self._move_mouse_to_shell_center()
            QMetaObject.invokeMethod(pane, "collapsePane")
            wait_for_condition_or_raise(
                lambda pane=pane: float(pane.property("width")) <= 1.0,
                timeout_ms=2500,
                poll_interval_ms=20,
                app=self.app,
                timeout_message=lambda pane=pane: (
                    f"Pane width did not satisfy predicate within 2500ms: {pane.property('width')}"
                ),
            )

            handle = self._pane_child_item(pane, "collapsedSidePaneHandle")
            reveal_zone = self._pane_child_item(pane, "collapsedSidePaneRevealZone")
            edge_point = self._item_widget_point(
                reveal_zone,
                max(1.0, float(reveal_zone.width()) * 0.5),
                float(reveal_zone.height()) * 0.5,
            )

            wait_for_condition_or_raise(
                lambda pane=pane, handle=handle: (
                    not bool(pane.property("collapsedHandleRevealed"))
                    and float(handle.property("opacity")) < 0.05
                ),
                timeout_ms=600,
                poll_interval_ms=20,
                app=self.app,
                timeout_message="Collapsed side pane handle did not start hidden.",
            )

            QTest.mouseMove(self.window.quick_widget, edge_point)
            wait_for_condition_or_raise(
                lambda pane=pane, handle=handle: (
                    bool(pane.property("collapsedHandleRevealed"))
                    and float(handle.property("opacity")) > 0.8
                ),
                timeout_ms=800,
                poll_interval_ms=20,
                app=self.app,
                timeout_message="Collapsed side pane handle did not reveal near the edge.",
            )

            self._move_mouse_to_shell_center()
            wait_for_condition_or_raise(
                lambda pane=pane, handle=handle: (
                    not bool(pane.property("collapsedHandleRevealed"))
                    and float(handle.property("opacity")) < 0.1
                ),
                timeout_ms=800,
                poll_interval_ms=20,
                app=self.app,
                timeout_message="Collapsed side pane handle stayed visible away from the edge.",
            )

            QTest.mouseMove(self.window.quick_widget, edge_point)
            wait_for_condition_or_raise(
                lambda pane=pane, handle=handle: (
                    bool(pane.property("collapsedHandleRevealed"))
                    and float(handle.property("opacity")) > 0.8
                ),
                timeout_ms=800,
                poll_interval_ms=20,
                app=self.app,
                timeout_message="Collapsed side pane handle did not reveal before expanding.",
            )
            handle_point = self._item_widget_point(
                handle,
                float(handle.width()) * 0.5,
                float(handle.height()) * 0.5,
            )
            QTest.mouseClick(
                self.window.quick_widget,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                handle_point,
            )
            wait_for_condition_or_raise(
                lambda pane=pane: (
                    not bool(pane.property("paneCollapsed"))
                    and float(pane.property("width")) > 200.0
                ),
                timeout_ms=2500,
                poll_interval_ms=20,
                app=self.app,
                timeout_message=lambda pane=pane: (
                    f"Pane did not expand from hover-revealed handle: {pane.property('width')}"
                ),
            )

    def test_qml_rect_selection_supports_replace_and_additive_modes(self) -> None:
        node_a = self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        node_b = self.window.scene.add_node_from_type("core.logger", x=360.0, y=30.0)
        self.app.processEvents()

        self.window.scene.select_nodes_in_rect(0.0, 0.0, 280.0, 180.0)
        self.app.processEvents()
        selected_after_replace = set(self.window.scene.selected_node_lookup)
        self.assertEqual(selected_after_replace, {node_a})

        self.window.scene.select_nodes_in_rect(300.0, 0.0, 700.0, 220.0, True)
        self.app.processEvents()
        selected_after_additive = set(self.window.scene.selected_node_lookup)
        self.assertEqual(selected_after_additive, {node_a, node_b})

    def test_qml_parallel_edges_between_same_nodes_use_distinct_lanes(self) -> None:
        source_id = self.window.scene.add_node_from_type("core.constant", x=40.0, y=40.0)
        target_id = self.window.scene.add_node_from_type("core.if", x=320.0, y=60.0)
        self.window.scene.set_node_collapsed(source_id, True)
        self.window.scene.set_node_collapsed(target_id, True)
        self.app.processEvents()

        edge_a = self.window.scene.add_edge(source_id, "value", target_id, "condition")
        edge_b = self.window.scene.add_edge(source_id, "as_text", target_id, "true_value")
        self.app.processEvents()

        edges_by_id = {item["edge_id"]: item for item in self.window.scene.edges_model}
        self.assertIn(edge_a, edges_by_id)
        self.assertIn(edge_b, edges_by_id)
        c1_gap = abs(edges_by_id[edge_a]["c1y"] - edges_by_id[edge_b]["c1y"])
        c2_gap = abs(edges_by_id[edge_a]["c2y"] - edges_by_id[edge_b]["c2y"])
        self.assertGreater(c1_gap, 8.0)
        self.assertGreater(c2_gap, 8.0)

    def test_qml_backward_edge_routes_outside_connected_node_bounds(self) -> None:
        source_id = self.window.scene.add_node_from_type("core.constant", x=360.0, y=80.0)
        target_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=220.0)
        self.app.processEvents()

        self.window.scene.add_edge(source_id, "as_text", target_id, "message")
        self.app.processEvents()

        nodes_by_id = {item["node_id"]: item for item in self.window.scene.nodes_model}
        source_node = nodes_by_id[source_id]
        target_node = nodes_by_id[target_id]
        edge = self.window.scene.edges_model[0]

        source_right = source_node["x"] + source_node["width"]
        target_left = target_node["x"]
        source_top = source_node["y"]
        source_bottom = source_node["y"] + source_node["height"]
        target_top = target_node["y"]
        target_bottom = target_node["y"] + target_node["height"]

        self.assertGreater(edge["c1x"], source_right)
        self.assertLess(edge["c2x"], target_left)
        self.assertEqual(edge["route"], "pipe")

        pipe_points = edge["pipe_points"]
        self.assertGreaterEqual(len(pipe_points), 4)
        self.assertAlmostEqual(pipe_points[0]["x"], edge["sx"], places=4)
        self.assertAlmostEqual(pipe_points[0]["y"], edge["sy"], places=4)
        self.assertAlmostEqual(pipe_points[-1]["x"], edge["tx"], places=4)
        self.assertAlmostEqual(pipe_points[-1]["y"], edge["ty"], places=4)
        self.assertGreater(pipe_points[1]["x"], source_right)
        self.assertLess(pipe_points[-2]["x"], target_left)
        for index in range(1, len(pipe_points)):
            start = pipe_points[index - 1]
            end = pipe_points[index]
            self.assertTrue(
                abs(start["x"] - end["x"]) < 0.001 or abs(start["y"] - end["y"]) < 0.001,
                msg=f"segment {index - 1}->{index} is not orthogonal: {start} -> {end}",
            )
        horizontal_lanes = [
            start["y"]
            for index, start in enumerate(pipe_points[:-1])
            if abs(start["y"] - pipe_points[index + 1]["y"]) < 0.001
        ]
        self.assertTrue(
            any(source_bottom < y < target_top for y in horizontal_lanes),
            msg=f"expected a routing lane between nodes, got {pipe_points}",
        )

    def test_qml_library_filter_slots_apply_category_direction_and_type(self) -> None:
        self.window.set_library_query("")
        self.window.set_library_category("Input / Output")
        self.window.set_library_direction("in")
        self.window.set_library_data_type(PATH_DATA_TYPE_ID)
        self.app.processEvents()

        type_ids = {item["type_id"] for item in self.window.filtered_node_library_items}
        self.assertIn("io.file_read", type_ids)
        self.assertIn("io.file_write", type_ids)
        self.assertIn("io.excel_read", type_ids)
        self.assertIn("io.excel_write", type_ids)
        self.assertNotIn("core.logger", type_ids)

    def test_qml_graph_canvas_library_drop_on_flowchart_port_autoconnects_neutral_side(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        target_id = self.window.scene.add_node_from_type("passive.flowchart.process", x=80.0, y=120.0)
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        graph_canvas = self._graph_canvas_item()
        payload = self._library_item("passive.flowchart.process")
        screen_x, screen_y = self._screen_point_for_port(target_id, "right")
        self.assertTrue(graph_canvas.isPointInCanvas(screen_x + 6.0, screen_y))
        graph_canvas.updateLibraryDropPreview(screen_x + 6.0, screen_y, payload)
        self.app.processEvents()

        preview = self._variant_value(graph_canvas.property("dropPreviewPort"))
        self.assertEqual(
            preview,
            {
                "node_id": target_id,
                "port_key": "right",
                "direction": "neutral",
            },
        )

        graph_canvas.performLibraryDrop(screen_x + 6.0, screen_y, payload)
        self.app.processEvents()

        self.assertEqual(len(workspace.edges), 1)
        (new_node_id,) = set(workspace.nodes).difference(before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, target_id)
        self.assertEqual(edge.source_port_key, "right")
        self.assertEqual(edge.target_node_id, new_node_id)
        self.assertEqual(edge.target_port_key, "left")

    def test_qml_library_drop_replaces_occupied_data_input_but_keeps_flow_capacity(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        original_source_id = self.window.scene.add_node_from_type(
            "core.constant", x=360.0, y=40.0
        )
        target_id = self.window.scene.add_node_from_type("core.if", x=80.0, y=40.0)
        original_edge_id = self.window.scene.add_edge(
            original_source_id, "value", target_id, "condition"
        )
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        graph_canvas = self._graph_canvas_item()
        payload = self._library_item("core.constant")
        screen_x, screen_y = self._screen_point_for_port(target_id, "condition")
        self.assertTrue(graph_canvas.isPointInCanvas(screen_x, screen_y))
        graph_canvas.updateLibraryDropPreview(screen_x, screen_y, payload)
        self.app.processEvents()

        preview = self._variant_value(graph_canvas.property("dropPreviewPort"))
        self.assertEqual(
            preview,
            {
                "node_id": target_id,
                "port_key": "condition",
                "direction": "in",
            },
        )

        graph_canvas.performLibraryDrop(screen_x, screen_y, payload)
        self.app.processEvents()

        (new_source_id,) = set(workspace.nodes).difference(before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        self.assertNotEqual(new_source_id, original_source_id)
        self.assertNotIn(original_edge_id, workspace.edges)
        self.assertEqual(len(workspace.edges), 1)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, new_source_id)
        self.assertEqual(edge.source_port_key, "value")
        self.assertEqual(edge.target_node_id, target_id)
        self.assertEqual(edge.target_port_key, "condition")

        occupied_flow_input = {
            "direction": "in",
            "kind": "flow",
            "data_type": "flow",
            "allow_multiple_connections": False,
            "connection_count": 1,
        }
        flow_output = {
            "direction": "out",
            "kind": "flow",
            "data_type": "flow",
            "exposed": True,
        }
        self.assertFalse(
            bool(graph_canvas._hasCompatiblePortForTarget(occupied_flow_input, [flow_output]))
        )
        occupied_flow_input["allow_multiple_connections"] = True
        self.assertTrue(
            bool(graph_canvas._hasCompatiblePortForTarget(occupied_flow_input, [flow_output]))
        )

    def test_qml_flowchart_connection_quick_insert_preserves_top_port_as_source(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        source_id = self.window.scene.add_node_from_type("passive.flowchart.process", x=80.0, y=140.0)
        self.app.processEvents()
        before_node_ids = set(workspace.nodes)
        selected_before = set(self.window.scene.selected_node_lookup)

        opened = self.window.request_open_connection_quick_insert(
            source_id,
            "top",
            180.0,
            80.0,
            300.0,
            160.0,
        )
        self.assertTrue(opened)
        self.app.processEvents()

        self.window.set_connection_quick_insert_query("end")
        self.app.processEvents()

        results = self.window.connection_quick_insert_results
        self.assertTrue(results)
        chosen_index = next(
            index
            for index, item in enumerate(results)
            if item.get("type_id") == "passive.flowchart.end"
        )

        created = self.window.request_connection_quick_insert_choose(chosen_index)
        self.assertTrue(created)
        self.app.processEvents()

        self.assertFalse(self.window.connection_quick_insert_open)
        self.assertEqual(len(workspace.edges), 1)
        (new_node_id,) = set(workspace.nodes).difference(before_node_ids)
        self.assertEqual(set(self.window.scene.selected_node_lookup), selected_before)
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, source_id)
        self.assertEqual(edge.source_port_key, "top")
        self.assertEqual(edge.target_node_id, new_node_id)
        self.assertEqual(edge.target_port_key, "left")

    def test_qml_subnode_library_category_contains_pin_nodes(self) -> None:
        self.window.set_library_query("")
        self.window.set_library_category("Subnode")
        self.window.set_library_direction("")
        self.window.set_library_data_type("")
        self.app.processEvents()

        library_items = {
            item["type_id"]: item
            for item in self.window.filtered_node_library_items
        }
        self.assertIn("core.subnode_input", library_items)
        self.assertIn("core.subnode_output", library_items)
        self.assertEqual(library_items["core.subnode_input"]["category"], "Subnode")
        self.assertEqual(library_items["core.subnode_output"]["category"], "Subnode")
        pin_types = self.window.pin_data_type_options
        self.assertIn(GRAPH_DATA_TYPE_ID, pin_types)
        self.assertIn(JSON_DATA_TYPE_ID, pin_types)
        self.assertIn(STRING_DATA_TYPE_ID, pin_types)

    def test_qml_selected_node_inspector_mutations_update_graph_model(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        self.assertTrue(self.window.has_selected_node)
        property_keys = {item["key"] for item in self.window.selected_node_property_items}
        self.assertIn("message", property_keys)
        port_keys = {item["key"] for item in self.window.selected_node_port_items}
        self.assertEqual(port_keys, {"message"})

        self.window.set_selected_node_property("message", "updated in qml inspector")
        self.window.set_selected_port_exposed("message", False)
        self.window.set_selected_node_collapsed(True)
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertEqual(node.properties["message"], "updated in qml inspector")
        self.assertFalse(node.exposed_ports["message"])
        self.assertTrue(node.collapsed)

    def test_qml_selected_node_inspector_shows_node_link_rows(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.assertEqual(
            self.window.scene.upsert_node_link(
                node_id,
                "link-docs",
                "url",
                "Project docs",
                "https://example.com/docs",
                "Reference",
            ),
            "link-docs",
        )
        self.app.processEvents()

        link_items = self.window.selected_node_link_items
        self.assertEqual(len(link_items), 1)
        self.assertEqual(link_items[0]["id"], "link-docs")
        self.assertEqual(link_items[0]["type_label"], "Web")
        self.assertEqual(link_items[0]["breadcrumb"], "Reference")

        inspector_pane = self._inspector_object("inspectorPane")
        links_card = self._pane_child_item(inspector_pane, "inspectorNodeLinksCard")
        links_list = self._pane_child_item(inspector_pane, "inspectorNodeLinksList")
        link_row = self._pane_child_item(inspector_pane, "inspectorNodeLinkRow_link-docs")
        add_button = self._pane_child_item(inspector_pane, "inspectorAddLinkButton")
        comment_button = self._pane_child_item(inspector_pane, "inspectorAddCommentButton")

        self.assertTrue(bool(links_card.property("visible")))
        self.assertTrue(bool(links_list.property("visible")))
        self.assertTrue(bool(link_row.property("visible")))
        self.assertTrue(bool(add_button.property("visible")))
        self.assertTrue(bool(comment_button.property("visible")))
        self.assertFalse(bool(comment_button.property("compact")))
        self.assertAlmostEqual(
            float(comment_button.property("width")),
            float(add_button.property("width")),
        )
        self.assertAlmostEqual(
            float(comment_button.property("height")),
            float(add_button.property("height")),
        )
        self.assertEqual(_color_name(links_card.property("color")), STITCH_DARK_V1.inspector_card_bg)

    def test_selected_node_link_picker_options_cover_all_workspaces_and_store_hidden_ids(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        source_node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        local_target_id = self.window.scene.add_node_from_type("core.constant", x=240.0, y=60.0)
        self.window.scene.set_node_title(local_target_id, "Local Constant")

        target_workspace_id = self.window.workspace_manager.create_workspace("Reports")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        cross_target_id = self.window.scene.add_node_from_type("core.logger", x=140.0, y=90.0)
        self.window.scene.set_node_title(cross_target_id, "PDF2")

        self.window.workspace_navigation_controller.switch_workspace(source_workspace_id)
        self.window.scene.focus_node(source_node_id)
        self.app.processEvents()

        presenter = self.window.shell_inspector_presenter
        node_options = presenter.selected_node_link_node_options
        option_pairs = {
            (str(item["target_workspace_id"]), str(item["target_node_id"])): item
            for item in node_options
        }
        self.assertNotIn((source_workspace_id, source_node_id), option_pairs)
        self.assertIn((source_workspace_id, local_target_id), option_pairs)
        self.assertIn((target_workspace_id, cross_target_id), option_pairs)

        cross_option = option_pairs[(target_workspace_id, cross_target_id)]
        self.assertEqual(cross_option["label"], "PDF2")
        self.assertEqual(cross_option["target"], cross_target_id)
        self.assertIn("Reports", cross_option["subtitle"])
        self.assertTrue(str(cross_option["instance_label"]).startswith("ID "))

        workspace_options = {
            str(item["target_workspace_id"]): item
            for item in presenter.selected_node_link_workspace_options
        }
        self.assertEqual(workspace_options[source_workspace_id]["subtitle"], "Current workspace")
        self.assertEqual(workspace_options[target_workspace_id]["label"], "Reports")
        self.assertEqual(workspace_options[target_workspace_id]["target"], target_workspace_id)

        stored_link_id = presenter.upsert_selected_node_link(
            "",
            "node",
            "PDF2",
            cross_target_id,
            cross_option["subtitle"],
            target_workspace_id,
            cross_target_id,
        )
        self.assertTrue(stored_link_id)
        source_node = self.window.model.project.workspaces[source_workspace_id].nodes[source_node_id]
        stored_link = source_node.links[0]
        self.assertEqual(stored_link.kind, "node")
        self.assertEqual(stored_link.target, cross_target_id)
        self.assertEqual(stored_link.target_workspace_id, target_workspace_id)
        self.assertEqual(stored_link.target_node_id, cross_target_id)

    def test_qml_node_link_target_pick_fills_hidden_ids_and_saves_without_raw_id_entry(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        source_node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        target_workspace_id = self.window.workspace_manager.create_workspace("Reports")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        target_node_id = self.window.scene.add_node_from_type("core.logger", x=160.0, y=100.0)
        self.window.scene.set_node_title(target_node_id, "PDF2")

        self.window.workspace_navigation_controller.switch_workspace(source_workspace_id)
        self.window.scene.focus_node(source_node_id)
        self.app.processEvents()

        inspector_pane = self._inspector_object("inspectorPane")
        QMetaObject.invokeMethod(
            inspector_pane,
            "applyLinkTargetPick",
            Q_ARG("QVariant", "node"),
            Q_ARG("QVariant", target_workspace_id),
            Q_ARG("QVariant", target_node_id),
            Q_ARG("QVariant", "PDF2"),
            Q_ARG("QVariant", "Reports - Logger - ID 1"),
        )
        self.app.processEvents()

        links_card = self._pane_child_item(inspector_pane, "inspectorNodeLinksCard")
        self.assertTrue(bool(links_card.property("editorOpen")))
        self.assertEqual(str(links_card.property("editingKind")), "node")
        self.assertEqual(str(links_card.property("editingTitle")), "PDF2")
        self.assertEqual(str(links_card.property("editingTarget")), target_node_id)
        self.assertEqual(str(links_card.property("editingTargetWorkspaceId")), target_workspace_id)
        self.assertEqual(str(links_card.property("editingTargetNodeId")), target_node_id)

        QMetaObject.invokeMethod(links_card, "saveEdit")
        self.app.processEvents()

        source_node = self.window.model.project.workspaces[source_workspace_id].nodes[source_node_id]
        self.assertEqual(len(source_node.links), 1)
        stored_link = source_node.links[0]
        self.assertEqual(stored_link.title, "PDF2")
        self.assertEqual(stored_link.target, target_node_id)
        self.assertEqual(stored_link.target_workspace_id, target_workspace_id)
        self.assertEqual(stored_link.target_node_id, target_node_id)

    def test_qml_canvas_link_popover_preserves_draft_across_node_pick_and_cancel(self) -> None:
        source_workspace_id = self.window.workspace_manager.active_workspace_id()
        source_node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.set_node_title(source_node_id, "Source Logger")
        target_workspace_id = self.window.workspace_manager.create_workspace("Reports")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        target_node_id = self.window.scene.add_node_from_type("core.logger", x=160.0, y=100.0)
        self.window.scene.set_node_title(target_node_id, "PDF2")
        self.window.workspace_navigation_controller.switch_workspace(source_workspace_id)
        self.window.scene.focus_node(source_node_id)
        self.app.processEvents()

        root_object = self.window.quick_widget.rootObject()
        self.assertIsNotNone(root_object)
        graph_canvas = self._graph_canvas_item()
        link_layer = self._inspector_object("graphNodeLinkHoverLayer")
        link_editor = self._inspector_object("graphNodeLinkPopoverEditorForm")

        QMetaObject.invokeMethod(
            graph_canvas,
            "requestAddNodeLinkForNode",
            Q_ARG("QVariant", source_node_id),
        )
        self.app.processEvents()
        self.assertTrue(bool(link_editor.property("editorOpen")))
        self.assertEqual(str(link_layer.property("activeNodeId")), source_node_id)
        self.assertEqual(str(link_layer.property("sourceWorkspaceId")), source_workspace_id)

        link_editor.setProperty("editingKind", "node")
        link_editor.setProperty("editingTitle", "Draft report link")
        link_editor.setProperty("editingSubtitle", "Keep this subtitle")
        QMetaObject.invokeMethod(link_editor, "requestPickTarget")
        self.app.processEvents()
        self.assertEqual(str(root_object.property("linkTargetPickOwner")), "canvas")
        self.assertTrue(bool(link_editor.property("pickModeActive")))

        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        self.app.processEvents()
        QMetaObject.invokeMethod(
            graph_canvas,
            "completeNodeLinkTargetPick",
            Q_ARG("QVariant", target_node_id),
        )
        wait_for_condition_or_raise(
            lambda: (
                self.window.workspace_manager.active_workspace_id() == source_workspace_id
                and self.window.shell_inspector_presenter.selected_node_id == source_node_id
                and bool(link_editor.property("editorOpen"))
                and not bool(link_editor.property("pickModeActive"))
            ),
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message=lambda: (
                "Canvas link target pick did not return to its source editor: "
                f"active={self.window.workspace_manager.active_workspace_id()!r}, "
                f"source={source_workspace_id!r}, target={target_workspace_id!r}, "
                f"selected={self.window.shell_inspector_presenter.selected_node_id!r}, "
                f"sourceNode={source_node_id!r}, targetNode={target_node_id!r}, "
                f"editorOpen={link_editor.property('editorOpen')!r}, "
                f"pickModeActive={link_editor.property('pickModeActive')!r}, "
                f"owner={root_object.property('linkTargetPickOwner')!r}, "
                f"mode={root_object.property('linkTargetPickMode')!r}"
            ),
        )

        self.assertEqual(str(link_editor.property("editingTitle")), "Draft report link")
        self.assertEqual(str(link_editor.property("editingSubtitle")), "Keep this subtitle")
        self.assertEqual(str(link_editor.property("editingTarget")), target_node_id)
        self.assertEqual(str(link_editor.property("editingTargetWorkspaceId")), target_workspace_id)
        self.assertEqual(str(link_editor.property("editingTargetNodeId")), target_node_id)
        QMetaObject.invokeMethod(link_editor, "requestSave")
        wait_for_condition_or_raise(
            lambda: len(
                self.window.model.project.workspaces[source_workspace_id].nodes[source_node_id].links
            )
            == 1,
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Canvas link popover did not save on its source node.",
        )

        stored_link = self.window.model.project.workspaces[source_workspace_id].nodes[source_node_id].links[0]
        self.assertEqual(stored_link.title, "Draft report link")
        self.assertEqual(stored_link.subtitle, "Keep this subtitle")
        self.assertEqual(stored_link.target, target_node_id)
        self.assertEqual(stored_link.target_workspace_id, target_workspace_id)
        self.assertEqual(stored_link.target_node_id, target_node_id)

        QMetaObject.invokeMethod(
            graph_canvas,
            "requestAddNodeLinkForNode",
            Q_ARG("QVariant", source_node_id),
        )
        link_editor.setProperty("editingKind", "node")
        link_editor.setProperty("editingTitle", "Unsaved draft")
        link_editor.setProperty("editingSubtitle", "Survives cancel")
        QMetaObject.invokeMethod(link_editor, "requestPickTarget")
        self.window.workspace_navigation_controller.switch_workspace(target_workspace_id)
        self.app.processEvents()
        QMetaObject.invokeMethod(graph_canvas, "forceActiveFocus")
        self.app.processEvents()
        QTest.keyClick(self.window.quick_widget, Qt.Key.Key_Escape)
        wait_for_condition_or_raise(
            lambda: (
                self.window.workspace_manager.active_workspace_id() == source_workspace_id
                and self.window.shell_inspector_presenter.selected_node_id == source_node_id
                and bool(link_editor.property("editorOpen"))
                and not bool(link_editor.property("pickModeActive"))
            ),
            timeout_ms=2500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Cancelled canvas link pick did not resume on its source.",
        )
        self.assertEqual(str(link_editor.property("editingTitle")), "Unsaved draft")
        self.assertEqual(str(link_editor.property("editingSubtitle")), "Survives cancel")
        self.assertEqual(
            len(self.window.model.project.workspaces[source_workspace_id].nodes[source_node_id].links),
            1,
        )

    def test_qml_inspector_required_port_toggle_is_disabled_and_noops(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self.window.scene.add_node_from_type("core.if", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        inspector_pane = self._inspector_object("inspectorPane")
        toggles_by_key = {
            str(item.property("portKey")): item
            for item in self._walk_items(inspector_pane)
            if item.objectName() == "inspectorPortExposedToggle"
        }

        self.assertIn("condition", toggles_by_key)
        self.assertIn("false_value", toggles_by_key)
        self.assertFalse(bool(toggles_by_key["condition"].property("enabled")))
        self.assertTrue(bool(toggles_by_key["condition"].property("checked")))
        self.assertTrue(bool(toggles_by_key["false_value"].property("enabled")))

        self.window.set_selected_port_exposed("condition", False)
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertTrue(bool(node.exposed_ports.get("condition", True)))
        port_items = {item["key"]: item for item in self.window.selected_node_port_items}
        self.assertTrue(bool(port_items["condition"]["required"]))
        self.assertTrue(bool(port_items["condition"]["exposed"]))

    def test_qml_inspector_cards_swap_between_empty_and_selected_states(self) -> None:
        empty_card = self._inspector_object("inspectorEmptyStateCard")
        node_definition_card = self._inspector_object("inspectorNodeDefinitionCard")
        port_management_card = self._inspector_object("inspectorPortManagementCard")

        self.assertTrue(bool(empty_card.property("visible")))
        self.assertFalse(bool(node_definition_card.property("visible")))
        self.assertFalse(bool(port_management_card.property("visible")))

        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        self.assertFalse(bool(empty_card.property("visible")))
        self.assertTrue(bool(node_definition_card.property("visible")))
        self.assertTrue(bool(port_management_card.property("visible")))

    def test_qml_inspector_property_variant_loader_defaults_to_smart_groups(self) -> None:
        self.window.shell_inspector_presenter.set_property_pane_variant("smart_groups")
        self.app.processEvents()

        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        loader = self._inspector_object("inspectorPropertyVariantLoader")
        self.assertTrue(bool(loader.property("visible")))
        self.assertTrue(bool(loader.property("active")))

        body = self._inspector_object("inspectorSmartGroupsBody")
        self.assertIsNotNone(body)

    def test_qml_inspector_property_variant_loader_switches_with_preference(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        presenter = self.window.shell_inspector_presenter
        try:
            presenter.set_property_pane_variant("accordion_cards")
            self.app.processEvents()
            self.assertIsNotNone(self._inspector_object("inspectorAccordionCardsBody"))

            presenter.set_property_pane_variant("palette")
            self.app.processEvents()
            self.assertIsNotNone(self._inspector_object("inspectorPaletteBody"))

            presenter.set_property_pane_variant("smart_groups")
            self.app.processEvents()
            self.assertIsNotNone(self._inspector_object("inspectorSmartGroupsBody"))
        finally:
            presenter.set_property_pane_variant("smart_groups")
            self.app.processEvents()

    def test_qml_inspector_port_direction_switch_reselects_visible_port(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.python_script", x=80.0, y=60.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        inspector_pane = self._inspector_object("inspectorPane")
        inputs_tab = self._inspector_object("inspectorInputsTab")
        outputs_tab = self._inspector_object("inspectorOutputsTab")

        input_keys = {
            item["key"]
            for item in self.window.selected_node_port_items
            if item["direction"] == "in"
        }
        output_keys = {
            item["key"]
            for item in self.window.selected_node_port_items
            if item["direction"] == "out"
        }

        self.assertIn(str(inspector_pane.property("selectedPortKey")), input_keys)
        self.assertTrue(bool(inputs_tab.property("selectedStyle")))
        self.assertFalse(bool(outputs_tab.property("selectedStyle")))

        inspector_pane.setProperty("activePortDirection", "out")
        self.app.processEvents()

        self.assertIn(str(inspector_pane.property("selectedPortKey")), output_keys)
        self.assertFalse(bool(inputs_tab.property("selectedStyle")))
        self.assertTrue(bool(outputs_tab.property("selectedStyle")))

    def test_qml_inspector_background_focus_commits_inline_port_rename(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        port_node_id = self.window.request_add_selected_subnode_pin("out")
        self.assertTrue(port_node_id)
        inspector_pane = self._inspector_object("inspectorPane")
        inspector_pane.setProperty("activePortDirection", "out")
        inspector_pane.setProperty("editingPortKey", port_node_id)
        inspector_pane.setProperty("editingPortLabel", "Committed From Pane")
        self.app.processEvents()

        QMetaObject.invokeMethod(inspector_pane, "focusInspectorBackground")
        self.app.processEvents()

        self.assertEqual(str(inspector_pane.property("editingPortKey")), "")
        self.assertEqual(workspace.nodes[port_node_id].properties["label"], "Committed From Pane")

    def test_graph_canvas_command_bridge_commits_port_label_rename(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        node_id = self.window.scene.add_node_from_type("core.logger", x=180.0, y=120.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        self.window.graph_canvas_command_bridge.set_node_port_label(
            node_id,
            "message",
            "Renamed From Canvas",
        )
        self.app.processEvents()

        self.assertEqual(workspace.nodes[node_id].port_labels["message"], "Renamed From Canvas")

    def test_graph_canvas_command_bridge_commits_subnode_shell_port_label_rename(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        port_node_id = self.window.request_add_selected_subnode_pin("out")
        self.assertTrue(port_node_id)

        self.window.graph_canvas_command_bridge.set_node_port_label(
            shell_id,
            port_node_id,
            "Renamed Shell Output",
        )
        self.app.processEvents()

        self.assertEqual(workspace.nodes[port_node_id].properties["label"], "Renamed Shell Output")

    def test_graph_canvas_command_bridge_commits_subnode_pin_port_label_rename(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        port_node_id = self.window.request_add_selected_subnode_pin("out")
        self.assertTrue(port_node_id)
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        self.window.scene.focus_node(port_node_id)
        self.app.processEvents()

        self.window.graph_canvas_command_bridge.set_node_port_label(
            port_node_id,
            "pin",
            "Renamed Inner Pin",
        )
        self.app.processEvents()

        self.assertEqual(workspace.nodes[port_node_id].properties["label"], "Renamed Inner Pin")

    def test_qml_inspector_delete_selected_subnode_port_removes_pin_node(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        first_port_id = self.window.request_add_selected_subnode_pin("out")
        second_port_id = self.window.request_add_selected_subnode_pin("out")
        self.assertTrue(first_port_id)
        self.assertTrue(second_port_id)
        inspector_pane = self._inspector_object("inspectorPane")
        inspector_pane.setProperty("activePortDirection", "out")
        inspector_pane.setProperty("selectedPortKey", second_port_id)
        self.app.processEvents()

        QMetaObject.invokeMethod(inspector_pane, "deleteSelectedPort")
        self.app.processEvents()

        self.assertIn(first_port_id, workspace.nodes)
        self.assertNotIn(second_port_id, workspace.nodes)
        remaining_output_keys = {
            item["key"]
            for item in self.window.selected_node_port_items
            if item["direction"] == "out"
        }
        self.assertEqual(remaining_output_keys, {first_port_id})
        self.assertEqual(str(inspector_pane.property("selectedPortKey")), first_port_id)

    def test_qml_selected_node_header_metadata_exposes_clean_fields(self) -> None:
        first_node_id = self.window.scene.add_node_from_type("core.constant", x=0.0, y=0.0)
        second_node_id = self.window.scene.add_node_from_type("core.constant", x=120.0, y=0.0)
        self.window.scene.focus_node(second_node_id)
        self.app.processEvents()

        self.assertEqual(self.window.selected_node_title, "Constant")
        self.assertEqual(
            self.window.selected_node_subtitle,
            "Publishes a reusable JSON-compatible value and its text representation.",
        )
        self.assertNotIn("\\n", self.window.selected_node_summary)
        self.assertIn("\n", self.window.selected_node_summary)
        self.assertNotIn(second_node_id, self.window.selected_node_summary)

        metadata = {item["label"]: item["value"] for item in self.window.selected_node_header_items}
        self.assertEqual(metadata["Category"], "Core")
        self.assertEqual(metadata["ID"], "2")
        self.assertEqual(set(metadata), {"Category", "ID"})
        self.assertNotEqual(first_node_id, second_node_id)

    def test_qml_pin_inspector_updates_parent_shell_ports(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        custom_data_type = STRING_DATA_TYPE_ID

        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        pin_id = self.window.scene.add_node_from_type("core.subnode_input", x=40.0, y=40.0)
        self.window.scene.focus_node(pin_id)
        self.app.processEvents()

        self.assertTrue(self.window.selected_node_is_subnode_pin)
        self.assertEqual(
            [item["key"] for item in self.window.selected_node_property_items],
            ["label", "kind", "data_type"],
        )
        self.assertEqual(self.window.selected_node_port_items, [])

        self.window.set_selected_node_property("label", "Payload In")
        self.window.set_selected_node_property("kind", "data")
        self.window.set_selected_node_property("data_type", custom_data_type)
        self.app.processEvents()

        self.assertTrue(self.window.request_navigate_scope_parent())
        self.window.scene.focus_node(shell_id)
        self.app.processEvents()

        shell_payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == shell_id)
        shell_ports = {port["key"]: port for port in shell_payload["ports"]}
        self.assertIn(pin_id, shell_ports)
        self.assertEqual(shell_ports[pin_id]["label"], "Payload In")
        self.assertEqual(shell_ports[pin_id]["kind"], "data")
        self.assertEqual(shell_ports[pin_id]["data_type"], custom_data_type)

        shell_port_items = {item["key"]: item for item in self.window.selected_node_port_items}
        self.assertIn(pin_id, shell_port_items)
        self.assertEqual(shell_port_items[pin_id]["label"], "Payload In")
        self.assertEqual(workspace.nodes[pin_id].parent_node_id, shell_id)
        self.assertIn(custom_data_type, self.window.pin_data_type_options)

    def test_qml_pin_inspector_hides_port_management_card(self) -> None:
        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        pin_id = self.window.scene.add_node_from_type("core.subnode_input", x=40.0, y=40.0)
        self.window.scene.focus_node(pin_id)
        self.app.processEvents()

        node_definition_card = self._inspector_object("inspectorNodeDefinitionCard")
        port_management_card = self._inspector_object("inspectorPortManagementCard")
        pin_hint_banner = self._inspector_object("inspectorPinHintBanner")

        self.assertTrue(bool(node_definition_card.property("visible")))
        self.assertFalse(bool(port_management_card.property("visible")))
        self.assertTrue(bool(pin_hint_banner.property("visible")))

    def test_qml_node_payload_port_list_tracks_exposed_ports(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.constant", x=0.0, y=0.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        initial_nodes = self.window.scene.nodes_model
        constant_payload = next(item for item in initial_nodes if item["node_id"] == node_id)
        initial_ports = {port["key"] for port in constant_payload["ports"]}
        self.assertEqual(initial_ports, {"value", "as_text"})

        self.window.scene.set_exposed_port(node_id, "value", False)
        self.app.processEvents()

        updated_nodes = self.window.scene.nodes_model
        updated_payload = next(item for item in updated_nodes if item["node_id"] == node_id)
        updated_ports = {port["key"] for port in updated_payload["ports"]}
        self.assertEqual(updated_ports, {"as_text"})

    def test_qml_optional_port_filter_is_view_local(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        primary_view_id = workspace.active_view_id
        node_id = self.window.scene.add_node_from_type("core.stream_gate", x=240.0, y=120.0)
        self.window.scene.set_node_property(node_id, "gate", 1.0)
        self.app.processEvents()

        def port_keys() -> set[str]:
            payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == node_id)
            return {str(port["key"]) for port in payload["ports"]}

        self.assertEqual(port_keys(), {"stream", "gate", "output_0", "output_1"})

        secondary_view_id = self.window.workspace_manager.create_view(workspace_id, name="Filtered")
        self.app.processEvents()
        self.window.scene.set_hide_optional_ports(True)
        wait_for_condition_or_raise(
            lambda: port_keys() == {"stream"},
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for hide-optional payload filtering.",
        )
        self.assertTrue(bool(workspace.views[secondary_view_id].hide_optional_ports))

        self.window.request_switch_view(primary_view_id)
        wait_for_condition_or_raise(
            lambda: port_keys() == {"stream", "gate", "output_0", "output_1"},
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for primary-view payload restore.",
        )
        self.assertFalse(bool(workspace.views[primary_view_id].hide_optional_ports))

        self.window.request_switch_view(secondary_view_id)
        wait_for_condition_or_raise(
            lambda: port_keys() == {"stream"},
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Timed out waiting for secondary-view payload restore.",
        )

    def test_qml_node_payload_exposes_inline_property_metadata_for_supported_nodes(self) -> None:
        node_id = self.window.scene.add_node_from_type("core.logger", x=120.0, y=80.0)
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == node_id)
        inline_items = {item["key"]: item for item in payload["inline_properties"]}
        ports = {item["key"]: item for item in payload["ports"]}
        self.assertEqual(set(inline_items), {"level"})
        self.assertEqual(ports["message"]["default_property"]["inline_editor"], "text")
        self.assertEqual(inline_items["level"]["inline_editor"], "enum")
        self.assertGreater(payload["height"], 60.0)

    def test_qml_default_property_payload_tracks_value_changes_and_input_override(self) -> None:
        logger_id = self.window.scene.add_node_from_type("core.logger", x=260.0, y=120.0)
        constant_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=120.0)
        self.window.scene.focus_node(logger_id)
        self.window.set_selected_node_property("message", "inline update")
        self.window.request_connect_ports(constant_id, "as_text", logger_id, "message")
        self.app.processEvents()

        payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == logger_id)
        ports = {item["key"]: item for item in payload["ports"]}
        default_property = ports["message"]["default_property"]
        self.assertEqual(default_property["key"], "message")
        self.assertEqual(default_property["value"], "inline update")
        self.assertTrue(default_property["overridden_by_input"])

    def test_viewport_commands_frame_all_frame_selection_and_center_selection(self) -> None:
        node_a = self.window.scene.add_node_from_type("core.constant", x=20.0, y=30.0)
        self.window.scene.add_node_from_type("core.logger", x=540.0, y=260.0)
        self.app.processEvents()

        workspace_bounds = self.window.scene.workspace_scene_bounds()
        self.assertIsNotNone(workspace_bounds)
        self.window.view.set_zoom(0.6)
        self.window.view.centerOn(-220.0, -140.0)

        self.window.action_frame_all.trigger()
        self.app.processEvents()

        expected_all_zoom = self.window.view.fit_zoom_for_scene_rect(workspace_bounds)
        self.assertAlmostEqual(self.window.view.zoom, expected_all_zoom, places=6)
        self.assertAlmostEqual(self.window.view.center_x, workspace_bounds.center().x(), places=6)
        self.assertAlmostEqual(self.window.view.center_y, workspace_bounds.center().y(), places=6)

        self.window.scene.select_node(node_a)
        selection_bounds = self.window.scene.selection_bounds()
        self.assertIsNotNone(selection_bounds)

        self.window.action_frame_selection.trigger()
        self.app.processEvents()

        expected_selection_zoom = self.window.view.fit_zoom_for_scene_rect(selection_bounds)
        self.assertAlmostEqual(self.window.view.zoom, expected_selection_zoom, places=6)
        self.assertAlmostEqual(self.window.view.center_x, selection_bounds.center().x(), places=6)
        self.assertAlmostEqual(self.window.view.center_y, selection_bounds.center().y(), places=6)

        self.window.view.set_zoom(1.3)
        self.window.view.centerOn(900.0, -400.0)
        self.window.action_center_selection.trigger()
        self.app.processEvents()

        self.assertAlmostEqual(self.window.view.zoom, 1.3, places=6)
        self.assertAlmostEqual(self.window.view.center_x, selection_bounds.center().x(), places=6)
        self.assertAlmostEqual(self.window.view.center_y, selection_bounds.center().y(), places=6)

    def test_viewport_commands_are_noops_for_empty_graph_or_empty_selection(self) -> None:
        self.window.view.set_zoom(1.2)
        self.window.view.centerOn(55.0, -75.0)
        self.window.action_frame_all.trigger()
        self.app.processEvents()
        self.assertAlmostEqual(self.window.view.zoom, 1.2, places=6)
        self.assertAlmostEqual(self.window.view.center_x, 55.0, places=6)
        self.assertAlmostEqual(self.window.view.center_y, -75.0, places=6)

        self.window.scene.add_node_from_type("core.constant", x=20.0, y=20.0)
        self.window.scene.clear_selection()
        self.window.view.set_zoom(0.9)
        self.window.view.centerOn(-25.0, 45.0)

        self.window.action_frame_selection.trigger()
        self.app.processEvents()
        self.assertAlmostEqual(self.window.view.zoom, 0.9, places=6)
        self.assertAlmostEqual(self.window.view.center_x, -25.0, places=6)
        self.assertAlmostEqual(self.window.view.center_y, 45.0, places=6)

        self.window.action_center_selection.trigger()
        self.app.processEvents()
        self.assertAlmostEqual(self.window.view.zoom, 0.9, places=6)
        self.assertAlmostEqual(self.window.view.center_x, -25.0, places=6)
        self.assertAlmostEqual(self.window.view.center_y, 45.0, places=6)


    def test_script_editor_action_focuses_editor_when_script_node_selected(self) -> None:
        script_node_id = self.window.scene.add_node_from_type("core.python_script", x=80.0, y=60.0)
        self.window.scene.focus_node(script_node_id)
        self.app.processEvents()

        self.window.action_toggle_script_editor.trigger()
        self.app.processEvents()

        self.assertTrue(self.window.script_editor.visible)
        self.assertEqual(self.window.script_editor.current_node_id, script_node_id)
        self.assertTrue(self.window.script_editor.has_focus)

    def test_multi_view_and_workspace_switch_retains_independent_camera_state(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        first_v1_id = self.window.model.project.workspaces[first_workspace_id].active_view_id

        self.window.view.set_zoom(1.4)
        self.window.view.centerOn(110.0, 210.0)
        self.app.processEvents()

        self.window.workspace_navigation_controller.save_active_view_state()
        first_v2_id = self.window.workspace_manager.create_view(first_workspace_id, name="V2")
        self.window.workspace_navigation_controller.restore_active_view_state()
        self.window.view.set_zoom(0.7)
        self.window.view.centerOn(-55.0, 75.0)
        first_node_id = self.window.scene.add_node_from_type("core.constant", x=20.0, y=30.0)
        self.app.processEvents()

        second_workspace_id = self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(second_workspace_id)
        self.window.view.set_zoom(2.0)
        self.window.view.centerOn(400.0, -125.0)
        self.app.processEvents()

        self.window.workspace_navigation_controller.switch_workspace(first_workspace_id)
        self.app.processEvents()
        self.assertEqual(
            self.window.model.project.workspaces[first_workspace_id].active_view_id,
            first_v2_id,
        )
        self.assertAlmostEqual(self.window.view.zoom, 0.7, places=2)
        self.assertAlmostEqual(self.window.view.center_x, -55.0, delta=5.0)
        self.assertAlmostEqual(self.window.view.center_y, 75.0, delta=5.0)
        self.assertIn(first_node_id, self.window.model.project.workspaces[first_workspace_id].nodes)

        self.window.workspace_navigation_controller.switch_view(first_v1_id)
        self.app.processEvents()
        self.assertAlmostEqual(self.window.view.zoom, 1.4, places=2)
        self.assertAlmostEqual(self.window.view.center_x, 110.0, delta=5.0)
        self.assertAlmostEqual(self.window.view.center_y, 210.0, delta=5.0)

    def test_scope_navigation_updates_breadcrumbs_persists_scope_path_per_view_and_restores_runtime_camera(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        primary_view_id = workspace.active_view_id

        shell_id = self.window.scene.add_node_from_type("core.subnode", x=220.0, y=120.0)
        nested_node_id = self.window.scene.add_node_from_type("core.logger", x=80.0, y=90.0)
        workspace.nodes[nested_node_id].parent_node_id = shell_id
        self.window.scene.refresh_workspace_from_model(workspace_id)
        self.app.processEvents()

        breadcrumbs = self.window.active_scope_breadcrumb_items
        self.assertEqual(len(breadcrumbs), 1)
        self.assertEqual(breadcrumbs[0]["node_id"], "")
        self.assertEqual(self.window.scene.active_scope_path, [])

        self.window.view.set_zoom(1.25)
        self.window.view.centerOn(150.0, -40.0)
        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        self.app.processEvents()

        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertEqual(workspace.views[primary_view_id].scope_path, [shell_id])
        scoped_nodes = {item["node_id"] for item in self.window.scene.nodes_model}
        self.assertIn(nested_node_id, scoped_nodes)
        self.assertNotIn(shell_id, scoped_nodes)

        self.window.view.set_zoom(0.65)
        self.window.view.centerOn(880.0, 460.0)
        self.assertTrue(self.window.request_open_scope_breadcrumb(""))
        self.app.processEvents()

        self.assertEqual(self.window.scene.active_scope_path, [])
        self.assertEqual(workspace.views[primary_view_id].scope_path, [])
        self.assertAlmostEqual(self.window.view.zoom, 1.25, places=2)
        self.assertAlmostEqual(self.window.view.center_x, 150.0, delta=5.0)
        self.assertAlmostEqual(self.window.view.center_y, -40.0, delta=5.0)

        self.assertTrue(self.window.request_open_subnode_scope(shell_id))
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertAlmostEqual(self.window.view.zoom, 0.65, places=2)
        self.assertAlmostEqual(self.window.view.center_x, 880.0, delta=5.0)
        self.assertAlmostEqual(self.window.view.center_y, 460.0, delta=5.0)

        secondary_view_id = self.window.workspace_manager.create_view(workspace_id, name="V2")
        self.window.workspace_manager.set_active_view(workspace_id, primary_view_id)
        self.window.request_switch_view(secondary_view_id)
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [])
        self.assertEqual(workspace.views[secondary_view_id].scope_path, [])

        self.window.request_switch_view(primary_view_id)
        self.app.processEvents()
        self.assertEqual(self.window.scene.active_scope_path, [shell_id])
        self.assertEqual(workspace.views[primary_view_id].scope_path, [shell_id])

    def test_qml_create_view_updates_active_view_items_and_allows_switching(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        initial_view_count = len(workspace.views)
        original_active_view_id = workspace.active_view_id
        self.window.view.set_zoom(1.7)
        self.window.view.centerOn(420.0, 315.0)

        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            return_value=("Inspection", True),
        ):
            self.window.request_create_view()
        self.app.processEvents()

        updated_workspace = self.window.model.project.workspaces[workspace_id]
        original_view = updated_workspace.views[original_active_view_id]
        active_view = updated_workspace.views[updated_workspace.active_view_id]
        self.assertEqual(len(updated_workspace.views), initial_view_count + 1)
        self.assertEqual(self.window.active_view_name, "Inspection")
        self.assertAlmostEqual(active_view.zoom, original_view.zoom, places=4)
        self.assertAlmostEqual(active_view.pan_x, original_view.pan_x, places=4)
        self.assertAlmostEqual(active_view.pan_y, original_view.pan_y, places=4)
        self.assertAlmostEqual(self.window.view.zoom_value, original_view.zoom, places=4)
        self.assertAlmostEqual(self.window.view.center_x, original_view.pan_x, places=4)
        self.assertAlmostEqual(self.window.view.center_y, original_view.pan_y, places=4)

        active_items = [item for item in self.window.active_view_items if item.get("active")]
        self.assertEqual(len(active_items), 1)
        self.assertEqual(active_items[0]["label"], "Inspection")
        self.assertEqual(updated_workspace.active_view_id, active_items[0]["view_id"])

        self.window.request_switch_view(original_active_view_id)
        self.app.processEvents()
        self.assertEqual(self.window.model.project.workspaces[workspace_id].active_view_id, original_active_view_id)

    def test_request_close_view_removes_target_view_and_restores_adjacent_view_state(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        original_view_id = workspace.active_view_id
        original_view = workspace.views[original_view_id]
        original_view.zoom = 1.2
        original_view.pan_x = 160.0
        original_view.pan_y = -80.0

        inspection_view_id = self.window.workspace_manager.create_view(workspace_id, name="Inspection")
        inspection_view = workspace.views[inspection_view_id]
        inspection_view.zoom = 1.85
        inspection_view.pan_x = 540.0
        inspection_view.pan_y = 260.0
        self.window.request_switch_view(inspection_view_id)
        self.app.processEvents()

        closed = self.window.request_close_view(inspection_view_id)
        self.app.processEvents()

        self.assertTrue(closed)
        self.assertNotIn(inspection_view_id, workspace.views)
        self.assertEqual(workspace.active_view_id, original_view_id)
        self.assertAlmostEqual(self.window.view.zoom_value, original_view.zoom, places=4)
        self.assertAlmostEqual(self.window.view.center_x, original_view.pan_x, places=4)
        self.assertAlmostEqual(self.window.view.center_y, original_view.pan_y, places=4)

    def test_request_rename_view_updates_active_view_labels(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        view_id = self.window.workspace_manager.create_view(workspace_id, name="Inspection")
        self.app.processEvents()

        with patch.object(
            self.window.shell_host_presenter,
            "prompt_text_value",
            return_value=("Inspection Renamed", True),
        ):
            renamed = self.window.request_rename_view(view_id)
        self.app.processEvents()

        self.assertTrue(renamed)
        self.assertEqual(workspace.views[view_id].name, "Inspection Renamed")
        active_items = [item for item in self.window.active_view_items if item.get("view_id") == view_id]
        self.assertEqual(len(active_items), 1)
        self.assertEqual(active_items[0]["label"], "Inspection Renamed")
        self.assertEqual(self.window.active_view_name, "Inspection Renamed")

    def test_request_move_view_tab_reorders_active_view_items(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        first_view_id = workspace.active_view_id
        second_view_id = self.window.workspace_manager.create_view(workspace_id, name="Inspection")
        third_view_id = self.window.workspace_manager.create_view(workspace_id, name="Review")
        self.app.processEvents()

        moved = self.window.request_move_view_tab(2, 0)
        self.app.processEvents()

        self.assertTrue(moved)
        self.assertEqual(list(workspace.views), [third_view_id, first_view_id, second_view_id])
        self.assertEqual(
            [item["view_id"] for item in self.window.active_view_items],
            [third_view_id, first_view_id, second_view_id],
        )
        self.assertEqual(workspace.active_view_id, third_view_id)

    def test_request_close_view_rejects_last_remaining_view(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        workspace = self.window.model.project.workspaces[workspace_id]
        only_view_id = workspace.active_view_id

        with patch.object(QMessageBox, "warning") as warning_mock:
            closed = self.window.request_close_view(only_view_id)

        self.assertFalse(closed)
        self.assertIn(only_view_id, workspace.views)
        warning_mock.assert_called_once()

    def test_closing_dirty_workspace_honors_unsaved_warning(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.window.workspace_navigation_controller.switch_workspace(first_workspace_id)
        self.window.scene.add_node_from_type("core.constant", x=0.0, y=0.0)
        self.app.processEvents()

        first_index = -1
        for index in range(self.window.workspace_tabs.count()):
            if self.window.workspace_tabs.tabData(index) == first_workspace_id:
                first_index = index
                break
        self.assertGreaterEqual(first_index, 0)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.window.workspace_navigation_controller.on_workspace_tab_close(first_index)
        self.assertIn(first_workspace_id, self.window.model.project.workspaces)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.workspace_navigation_controller.on_workspace_tab_close(first_index)
        self.assertNotIn(first_workspace_id, self.window.model.project.workspaces)

    def test_request_move_workspace_tab_reorders_workspace_tabs(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        second_workspace_id = self.window.workspace_manager.create_workspace("Second")
        third_workspace_id = self.window.workspace_manager.create_workspace("Third")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        moved = self.window.request_move_workspace_tab(2, 0)
        self.app.processEvents()

        self.assertTrue(moved)
        self.assertEqual(
            [self.window.workspace_tabs.tabData(index) for index in range(self.window.workspace_tabs.count())],
            [third_workspace_id, first_workspace_id, second_workspace_id],
        )
        self.assertEqual(self.window.workspace_manager.active_workspace_id(), third_workspace_id)

    def test_qml_workspace_tabs_allow_leftward_drag_from_non_leftmost_slots(self) -> None:
        self.window.workspace_manager.create_workspace("Second")
        self.window.workspace_manager.create_workspace("Third")
        self.window.workspace_navigation_controller.refresh_workspace_tabs()

        strip = self._inspector_object("workspaceControlsStrip")

        def ordered_tab_slots() -> list[QObject]:
            slots = strip.property("tabSlots")
            if isinstance(slots, QJSValue):
                slots = slots.toVariant()
            return sorted(slots or [], key=lambda slot: float(slot.property("x")))

        def drag_bounds_ready() -> bool:
            slots = ordered_tab_slots()
            if len(slots) < 3:
                return False
            return (
                float(slots[1].property("dragMinimumX")) < 0.0
                and float(slots[2].property("dragMinimumX")) < 0.0
                and float(slots[1].property("dragMaximumX")) > 0.0
            )

        wait_for_condition_or_raise(
            drag_bounds_ready,
            timeout_ms=150,
            poll_interval_ms=10,
            app=self.app,
            timeout_message="Timed out waiting for workspace tab drag bounds to settle.",
        )

        slots = ordered_tab_slots()
        self.assertGreaterEqual(len(slots), 3)
        self.assertAlmostEqual(float(slots[0].property("dragMinimumX")), 0.0, places=4)
        self.assertLess(float(slots[1].property("dragMinimumX")), 0.0)
        self.assertLess(float(slots[2].property("dragMinimumX")), 0.0)
        self.assertGreater(float(slots[1].property("dragMaximumX")), 0.0)

    def test_qml_workspace_tabs_chevrons_scroll_overflowed_strip_and_keep_create_visible(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        for index in range(8):
            self.window.workspace_manager.create_workspace(
                f"Overflow Workspace {index} - Static Displacement Viewer"
            )
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        strip = self._inspector_object("workspaceControlsStrip")
        backward_button = self._strip_child(strip, "tabStripScrollBackwardButton")
        forward_button = self._strip_child(strip, "tabStripScrollForwardButton")
        create_button = self._strip_child(strip, "tabStripCreateButton")

        wait_for_condition_or_raise(
            lambda: bool(strip.property("tabsOverflowActive")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not overflow for chevron test.",
        )

        self.window.workspace_tabs.activate_workspace(first_workspace_id)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) <= 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not return to the left edge.",
        )

        self.assertTrue(bool(create_button.property("visible")))
        self.assertTrue(bool(forward_button.property("visible")))
        QMetaObject.invokeMethod(
            forward_button,
            "click",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) > 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not scroll right after chevron click.",
        )

        self.assertTrue(bool(create_button.property("visible")))
        self.assertTrue(bool(backward_button.property("enabled")))

        QMetaObject.invokeMethod(
            backward_button,
            "click",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) <= 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not scroll back left after chevron click.",
        )

    def test_qml_workspace_tabs_shift_wheel_and_horizontal_delta_scroll_only_when_supported(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        for index in range(8):
            self.window.workspace_manager.create_workspace(
                f"Wheel Workspace {index} - Static Stress Norm Export"
            )
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        strip = self._inspector_object("workspaceControlsStrip")
        wait_for_condition_or_raise(
            lambda: bool(strip.property("tabsOverflowActive")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not overflow for wheel test.",
        )

        self.window.workspace_tabs.activate_workspace(first_workspace_id)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) <= 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not return to the left edge before wheel assertions.",
        )

        strip.setProperty("testWheelHorizontalDelta", 0)
        strip.setProperty("testWheelVerticalDelta", -120)
        strip.setProperty("testWheelShiftHeld", False)
        QMetaObject.invokeMethod(
            strip,
            "applyConfiguredTestWheelScroll",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()
        self.assertAlmostEqual(float(strip.property("tabsContentX")), 0.0, places=4)

        strip.setProperty("testWheelShiftHeld", True)
        QMetaObject.invokeMethod(
            strip,
            "applyConfiguredTestWheelScroll",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) > 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Shift+wheel did not scroll the overflowed workspace strip.",
        )
        shift_scroll_x = float(strip.property("tabsContentX"))

        strip.setProperty("testWheelHorizontalDelta", -120)
        strip.setProperty("testWheelVerticalDelta", 0)
        strip.setProperty("testWheelShiftHeld", False)
        QMetaObject.invokeMethod(
            strip,
            "applyConfiguredTestWheelScroll",
            Qt.ConnectionType.DirectConnection,
        )
        self.app.processEvents()

        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) > shift_scroll_x + 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Native horizontal delta did not scroll the overflowed workspace strip.",
        )

    def test_qml_workspace_tabs_auto_reveal_active_workspace_when_selection_moves_offscreen(self) -> None:
        first_workspace_id = self.window.workspace_manager.active_workspace_id()
        created_workspace_ids: list[str] = []
        for index in range(8):
            created_workspace_ids.append(
                self.window.workspace_manager.create_workspace(
                    f"Reveal Workspace {index} - Static Displacement Viewer"
                )
            )
        self.window.workspace_navigation_controller.refresh_workspace_tabs()
        self.app.processEvents()

        strip = self._inspector_object("workspaceControlsStrip")
        wait_for_condition_or_raise(
            lambda: bool(strip.property("tabsOverflowActive")),
            timeout_ms=1500,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not overflow for auto-reveal test.",
        )

        self.window.workspace_tabs.activate_workspace(first_workspace_id)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: float(strip.property("tabsContentX")) <= 0.5,
            timeout_ms=800,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not reveal the leftmost active tab.",
        )

        last_workspace_id = created_workspace_ids[-1]
        self.window.workspace_tabs.activate_workspace(last_workspace_id)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: self._tab_slot_fully_visible(strip, self._active_tab_slot(strip)),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not scroll to reveal the last workspace.",
        )

        active_slot = self._active_tab_slot(strip)
        self.assertTrue(self._tab_slot_fully_visible(strip, active_slot))

        self.window.workspace_tabs.activate_workspace(first_workspace_id)
        self.app.processEvents()
        wait_for_condition_or_raise(
            lambda: self._tab_slot_fully_visible(strip, self._active_tab_slot(strip)),
            timeout_ms=1200,
            poll_interval_ms=20,
            app=self.app,
            timeout_message="Workspace strip did not scroll back to reveal the first workspace.",
        )

        active_slot = self._active_tab_slot(strip)
        self.assertTrue(self._tab_slot_fully_visible(strip, active_slot))
