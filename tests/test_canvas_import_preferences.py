# Purpose: Verify persistent canvas import mode and its native/QML settings controls.
# Map: docs/agent_maps/feature_routes/graphics_settings_themes_preferences.md
# Tests: tests/test_canvas_import_preferences.py
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, QPoint, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem, QQuickWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from ea_node_editor.app_preferences import AppPreferencesStore, normalize_graphics_settings
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.project_codec import JsonProjectCodec
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.dialogs.graphics_settings_dialog import GraphicsSettingsDialog
from ea_node_editor.ui.shell.controllers.app_preferences_controller import AppPreferencesController
from ea_node_editor.ui.shell.host_presenter import ShellHostPresenter
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from tests.test_graphics_settings_preferences import _RuntimeTooltipHost


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def preferences(tmp_path, app):
    store = AppPreferencesStore(path_provider=lambda: tmp_path / "preferences.json")
    controller = AppPreferencesController(store=store)
    host = _RuntimeTooltipHost(controller)
    return controller, host


@pytest.mark.parametrize("value", [None, "", "invalid", True, 1, {}, []])
def test_missing_or_invalid_import_mode_defaults_to_automatic(value):
    assert normalize_graphics_settings({})["interaction"]["canvas_import_mode"] == "automatic"
    assert normalize_graphics_settings({"interaction": {"canvas_import_mode": value}})[
        "interaction"
    ]["canvas_import_mode"] == "automatic"


def test_mode_persists_reloads_and_never_enters_project(preferences):
    controller, host = preferences
    registry = build_default_registry()
    model = GraphModel()
    model.create_workspace()
    codec = JsonProjectCodec(registry)
    before = codec.to_persistent_document(model.project)
    host.model = model
    host.shell_workspace_presenter.set_graphics_canvas_import_mode("ask")
    restarted = AppPreferencesController(store=controller.store())
    assert restarted.graphics_settings()["interaction"]["canvas_import_mode"] == "ask"
    assert codec.to_persistent_document(model.project) == before
    assert "canvas_import_mode" not in json.dumps(before)
    controller.set_graphics_canvas_import_mode("invalid", host=host)
    assert host.shell_workspace_presenter.graphics_canvas_import_mode == "automatic"


def test_presenter_projection_retains_mode_on_partial_graphics_update(preferences):
    controller, host = preferences
    presenter = host.shell_workspace_presenter
    controller.set_graphics_canvas_import_mode("ask", host=host)
    resolved = presenter.apply_graphics_preferences({"canvas": {"show_grid": False}})
    assert resolved["interaction"]["canvas_import_mode"] == "ask"
    assert not resolved["canvas"]["show_grid"]
    resolved = presenter.apply_graphics_preferences(copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS))
    assert resolved["interaction"]["canvas_import_mode"] == "automatic"


@pytest.mark.parametrize("accept", [False, True])
def test_full_dialog_ok_or_cancel_uses_real_controller(preferences, app, accept):
    controller, runtime_host = preferences
    parent = QWidget()
    parent.app_preferences_controller = controller
    parent.graphics_show_tooltips = True
    parent.apply_graphics_preferences = runtime_host.apply_graphics_preferences
    presenter = SimpleNamespace(
        _host=parent,
        edit_graph_theme_settings=lambda settings: settings,
        active_renderer_label=lambda: "Software",
    )
    created = []

    def dialog_factory(**kwargs):
        dialog = GraphicsSettingsDialog(**kwargs)
        created.append(dialog)

        def choose():
            dialog.canvas_import_mode_combo.setCurrentIndex(
                dialog.canvas_import_mode_combo.findData("ask")
            )
            (dialog.ok_button if accept else dialog.cancel_button).click()

        QTimer.singleShot(0, choose)
        return dialog

    try:
        with patch("ea_node_editor.ui.dialogs.GraphicsSettingsDialog", side_effect=dialog_factory):
            ShellHostPresenter.show_graphics_settings_dialog(presenter)
        expected = "ask" if accept else "automatic"
        assert controller.graphics_settings()["interaction"]["canvas_import_mode"] == expected
        assert runtime_host.shell_workspace_presenter.graphics_canvas_import_mode == expected
        reloaded = AppPreferencesController(store=controller.store())
        assert reloaded.graphics_settings()["interaction"]["canvas_import_mode"] == expected
    finally:
        for dialog in created:
            dialog.close()
        parent.close()


def test_dialog_defaults_and_full_roundtrip(preferences, app):
    controller, _host = preferences
    controller.set_graphics_canvas_import_mode("ask")
    dialog = GraphicsSettingsDialog(controller.graphics_settings())
    try:
        combo = dialog.canvas_import_mode_combo
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "Automatic", "Ask every time"
        ]
        assert combo.currentData() == "ask"
        assert "each node type" in combo.toolTip()
        assert dialog.values()["interaction"]["canvas_import_mode"] == "ask"
        dialog.set_values(copy.deepcopy(DEFAULT_GRAPHICS_SETTINGS))
        assert combo.currentData() == "automatic"
        assert dialog.values()["interaction"]["canvas_import_mode"] == "automatic"
        assert controller.graphics_settings()["interaction"]["canvas_import_mode"] == "ask"
    finally:
        dialog.close()


def test_import_mode_tooltip_respects_existing_general_tooltip_preference(app):
    dialog = GraphicsSettingsDialog(tooltips_enabled=False)
    try:
        assert dialog.canvas_import_mode_combo.toolTip() == ""
    finally:
        dialog.close()


@pytest.mark.parametrize("canvas_height,selected_wires", [(1000, False), (565, False), (565, True)])
def test_real_gear_actions_update_preference_facts_and_dialog(preferences, app, canvas_height, selected_wires):
    controller, host = preferences
    state = GraphCanvasStateBridge(graphics_source=host.shell_workspace_presenter)
    commands = GraphCanvasCommandBridge(graphics_source=host.shell_workspace_presenter)
    notifications = []
    state.graphics_preferences_changed.connect(lambda: notifications.append(state.graphics_canvas_import_mode))
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("testState", state)
    engine.rootContext().setContextProperty("testCommands", commands)
    engine.rootContext().setContextProperty("testCanvasHeight", canvas_height)
    engine.rootContext().setContextProperty("testSelectedWires", selected_wires)
    component = QQmlComponent(engine)
    qml_dir = Path(__file__).resolve().parents[1] / "ea_node_editor/ui_qml/components/graph_canvas"
    component.setData(b'''
import QtQuick 2.15
Item {
    id: canvas
    width: 1000
    height: testCanvasHeight
    property alias prefs: preferences
    property var executionFacts: ({})
    property var canvasStateBridgeRef: testState
    property var selectedEdgeIds: testSelectedWires ? ["edge-1"] : []
    function snapToGridEnabled() { return false; }
    function _normalizeEdgeIds(values) { return values; }
    function _sceneEdgePayload(edgeId) { return { active_data_wire: true }; }
    GraphCanvasPreferenceFacts { id: preferences; stateBridge: testState }
    GraphCanvasOptionsMenu {
        objectName: "testCanvasOptionsMenu"
        canvasItem: canvas
        commandBridge: testCommands
        anchorY: 52
        y: resolvedY
    }
}
''', QUrl.fromLocalFile(str(qml_dir / "ImportPreferencesProbe.qml")))
    assert component.status() == QQmlComponent.Status.Ready, [e.toString() for e in component.errors()]
    canvas = component.create()
    assert isinstance(canvas, QQuickItem)
    window = QQuickWindow()
    window.resize(1000, canvas_height)
    canvas.setParentItem(window.contentItem())
    window.show()
    app.processEvents()

    def click(item):
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
        app.processEvents()

    def wheel_to_bottom(scroll):
        point = scroll.mapToScene(QPointF(scroll.width() / 2, scroll.height() / 2))
        QTest.mouseMove(window, point.toPoint())
        QTest.qWait(20)
        app.processEvents()
        for phase, delta in (
            (Qt.ScrollPhase.ScrollBegin, -2400),
            (Qt.ScrollPhase.ScrollEnd, 0),
        ):
            event = QWheelEvent(
                point, QPointF(window.mapToGlobal(point.toPoint())),
                QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier, phase, False,
            )
            QApplication.sendEvent(window, event)
            QTest.qWait(400)
        QTest.qWait(400)
        app.processEvents()

    try:
        menu = canvas.findChild(QObject, "testCanvasOptionsMenu")
        assert 0 <= menu.y() < canvas.height()
        assert menu.y() + menu.height() <= canvas.height()
        assert menu.property("canvasImportModeValue") == "automatic"
        if canvas_height < 1000:
            scroll = canvas.findChild(QQuickItem, "canvasOptionsMainScroll")
            wheel_to_bottom(scroll)
            assert scroll.property("contentItem").property("contentY") > 0, "before clicks"
            scroll.property("contentItem").setProperty("contentY", 0)
        for mode in ("ask", "automatic"):
            row = canvas.findChild(QQuickItem, "canvasOptionsPasteAndDropRow")
            click(row)
            submenu = canvas.findChild(QQuickItem, "canvasOptionsPasteAndDropSubmenu")
            assert submenu is not None
            assert submenu.property("currentValue") == controller.graphics_settings()["interaction"]["canvas_import_mode"]
            descendants = list(submenu.childItems())
            for item in descendants:
                descendants.extend(item.childItems())
            active = [item.property("optionValue") for item in descendants if item.property("isActive")]
            assert active == [submenu.property("currentValue")]
            choices = [item for item in descendants if item.property("optionValue") == mode]
            assert len(choices) == 1
            click(choices[0])
            assert controller.graphics_settings()["interaction"]["canvas_import_mode"] == mode
            assert state.graphics_canvas_import_mode == mode
            assert menu.property("canvasImportModeValue") == mode
            if canvas_height == 1000:
                dialog = GraphicsSettingsDialog(controller.graphics_settings())
                assert dialog.canvas_import_mode_combo.currentData() == mode
                dialog.close()
        assert notifications == ["ask", "automatic"]
        if canvas_height < 1000:
            main_scroll = canvas.findChild(QQuickItem, "canvasOptionsMainScroll")
            wheel_to_bottom(main_scroll)
            assert main_scroll.property("contentItem").property("contentY") > 0
            # Submenus use the same bound when even their own content overflows.
            canvas.setHeight(80)
            menu.setProperty("activeSubmenu", "canvasImport")
            app.processEvents()
            submenu = canvas.findChild(QQuickItem, "canvasOptionsPasteAndDropSubmenu")
            submenu_scroll = submenu.findChild(QQuickItem, "canvasOptionsSubmenuScroll")
            assert menu.y() + menu.height() <= canvas.height()
            assert submenu_scroll.property("contentHeight") > submenu_scroll.height()
            wheel_to_bottom(submenu_scroll)
            assert submenu_scroll.property("contentItem").property("contentY") > 0
            descendants = list(submenu.childItems())
            for item in descendants:
                descendants.extend(item.childItems())
            ask = next(item for item in descendants if item.property("optionValue") == "ask")
            click(ask)
            assert controller.graphics_settings()["interaction"]["canvas_import_mode"] == "ask"
            canvas.setHeight(canvas_height)
            QTest.qWait(50)
            app.processEvents()

            # The footer remains reachable with native wheel scrolling, including
            # when selected-wire controls add rows to the menu.
            main_scroll = canvas.findChild(QQuickItem, "canvasOptionsMainScroll")
            assert main_scroll.property("contentHeight") > main_scroll.height()
            wheel_to_bottom(main_scroll)
            assert main_scroll.property("contentItem").property("contentY") > 0
            footer = canvas.findChild(QQuickItem, "canvasOptionsOpenGraphicsSettingsRow")
            footer_top = footer.mapToScene(QPointF()).y()
            assert menu.y() <= footer_top
            assert footer_top + footer.height() <= canvas.height()
            requests = []
            host.shell_host_presenter.show_graphics_settings_dialog = lambda: requests.append(True)
            click(footer)
            assert requests == [True]
    finally:
        window.close()
        canvas.setParentItem(None)
        canvas.deleteLater()
        app.processEvents()
