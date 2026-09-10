from __future__ import annotations

import textwrap

import pytest

from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase


pytestmark = pytest.mark.xdist_group("select_surface")


_SELECT_PAYLOAD_HELPER = textwrap.indent(
    """
def select_payload():
    payload = node_payload(surface_family="standard", surface_variant="select")
    payload["type_id"] = "data.select"
    payload["title"] = "Select"
    payload["display_name"] = "Select <Source>"
    payload["category_path"] = ["Data", "Control"]
    payload["help_text"] = "A dropdown that allows to select a value from the list."
    payload["keywords"] = ["dropdown", "combobox", "option"]
    payload["width"] = 280.0
    payload["height"] = 40.0
    payload["surface_spec"] = surface_spec_payload_for_values(
        type_id="data.select",
        family="standard",
        variant="select",
    )
    payload["surface_metrics"] = {
        "default_width": 280.0,
        "default_height": 40.0,
        "min_width": 220.0,
        "min_height": 40.0,
        "collapsed_width": 130.0,
        "collapsed_height": 36.0,
        "header_height": 0.0,
        "header_top_margin": 0.0,
        "body_top": 0.0,
        "body_height": 40.0,
        "port_top": 0.0,
        "port_height": 40.0,
        "port_center_offset": 20.0,
        "port_side_margin": 8.0,
        "port_dot_radius": 5.0,
        "resize_handle_size": 16.0,
        "body_left_margin": 10.0,
        "body_right_margin": 10.0,
        "use_host_chrome": True,
        "use_host_shadow": True,
    }
    payload["properties"] = {
        "options": [
            {"name": "Option A", "value": "0"},
            {"name": "Option B", "value": "1"},
        ],
        "selected_index": 0,
    }
    payload["ports"] = [{
        "key": "selected_value",
        "label": "Selected value",
        "direction": "out",
        "kind": "data",
        "data_type": "str",
        "data_access": "tree",
        "connected": False,
    }]
    payload["inline_properties"] = []
    return payload

def wait_for_surface(host, object_name, attempts=200):
    for _attempt in range(attempts):
        settle_events(2)
        for child in walk_items(host):
            if child.objectName() == object_name:
                return child
    raise AssertionError(f"surface item {object_name!r} never loaded")

def wait_for_named_object(root, object_name, attempts=100):
    for _attempt in range(attempts):
        candidate = root.findChild(QObject, object_name)
        if candidate is not None:
            return candidate
        settle_events(2)
    raise AssertionError(f"object {object_name!r} never loaded")
""",
    " " * 12,
)


class SelectSurfaceTests(PassiveGraphSurfaceHostTestBase):
    def test_select_pill_renders_and_dropdown_commits_selected_index(self) -> None:
        self._run_qml_probe(
            "select-pill-dropdown",
            _SELECT_PAYLOAD_HELPER
            + """
            payload = select_payload()
            canvas_component = QQmlComponent(engine)
            canvas_component.setData(
                "\\n".join([
                    "import QtQuick 2.15",
                    "Item {",
                    "    property var sceneBridge: null",
                    "    property var prefs: null",
                    "    property var canvasStateBridgeRef: null",
                    "    property var executionFacts: QtObject {",
                    "        property var failedNodeLookup: ({})",
                    "        property var runningNodeLookup: ({})",
                    "        property var completedNodeLookup: ({})",
                    "        property var warningNodeLookup: ({})",
                    "        property var nodeDiagnosticLookup: ({})",
                    "        property var freshRunNodeLookup: ({})",
                    "        property var selectedRunPreviewNodeLookup: ({})",
                    "        property int nodeExecutionRevision: 0",
                    "        property var runningNodeStartedAtMsLookup: ({})",
                    "        property var nodeElapsedMsLookup: ({})",
                    "        property var nodeRunCountLookup: ({'node_surface_host_test': 1})",
                    "        property var portFlowStateLookup: ({})",
                    "        property string nodeElapsedTimeUnit: 'seconds'",
                    "    }",
                    "}",
                ]).encode("utf-8"),
                QUrl(),
            )
            if canvas_component.status() != QQmlComponent.Status.Ready:
                errors = "\\n".join(error.toString() for error in canvas_component.errors())
                raise AssertionError(f"Failed to create Select canvas facts stub:\\n{errors}")
            canvas_stub = canvas_component.create()
            assert canvas_stub is not None
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            surface = wait_for_surface(host, "graphSelectSurface")
            combo = named_item(host, "graphSelectComboBox")
            output_dot = named_item(host, "graphNodeOutputPortDot")
            output_label = named_item(host, "graphNodeOutputPortLabel")
            header = named_item(host, "graphNodeHeaderLayer")
            help_tooltip = wait_for_named_object(host, "graphSelectHelpToolTip")
            elapsed_timer = named_item(host, "graphNodeElapsedTimer")

            assert bool(host.property("isSelectSurface"))
            assert bool(host.property("isCompactPillSurface"))
            assert not bool(header.property("headerTitleVisible"))
            assert not bool(output_label.property("visible"))
            assert float(host.property("resolvedCornerRadius")) == 20.0
            assert str(named_item(host, "graphSelectNameLabel").property("text")) == "Select"
            name_section = named_item(host, "graphSelectNameSection")
            name_section_fill_clip = named_item(host, "graphSelectNameSectionFillClip")
            name_section_fill = named_item(host, "graphSelectNameSectionFill")
            assert bool(name_section_fill_clip.property("clip"))
            expected_extension = float(host.property("resolvedCornerRadius")) - 1.0
            actual_extension = float(name_section_fill.width()) - float(name_section.width())
            assert abs(actual_extension - expected_extension) < 0.01
            expected_help = (
                '<b>Select &lt;Source&gt;</b><br>'
                '<font color="#95a0b8">Data, Control</font><br>'
                'A dropdown that allows to select a value from the list.<br><br>'
                'Keywords: dropdown, combobox, option.'
                '<hr color="#3a4355">This node ran 1 time(s).'
            )
            assert str(host.property("nodeHelpTooltipText")) == expected_help
            assert str(help_tooltip.property("text")) == expected_help
            assert int(help_tooltip.property("textFormat")) == 1
            assert not bool(elapsed_timer.property("visible"))
            assert str(combo.property("displayText")) == "Option A"
            assert int(combo.property("currentIndex")) == 0
            assert len(variant_list(surface.property("embeddedInteractiveRects"))) == 2

            host_origin = host.mapToScene(QPointF(0.0, 0.0))
            dot_center = output_dot.mapToScene(
                QPointF(output_dot.width() * 0.5, output_dot.height() * 0.5)
            )
            assert abs((dot_center.y() - host_origin.y()) - 20.0) < 0.5

            commits = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append((node_id, key, variant_value(value)))
            )
            window = attach_host_to_window(host)
            QTest.mouseMove(window, item_scene_point(named_item(host, "graphSelectNameLabel")))
            QTest.qWait(450)
            settle_events(5)
            assert bool(help_tooltip.property("managedVisible"))
            assert bool(help_tooltip.property("visible"))
            combo.forceActiveFocus()
            QTest.keyClick(window, Qt.Key.Key_Down)
            QTest.keyClick(window, Qt.Key.Key_Return)
            settle_events(4)
            assert commits[-1] == ("node_surface_host_test", "selected_index", 1), commits

            dispose_host_window(host, window)

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            workspace_id = model.active_workspace.workspace_id
            scene.set_workspace(model, registry, workspace_id)
            long_title = "Select From A Long Descriptive Custom Value List"
            long_node_id = scene.add_node_from_type("data.select", 120.0, 80.0)
            scene.set_node_title(long_node_id, long_title)
            long_payload = next(
                item for item in scene.nodes_model if item["node_id"] == long_node_id
            )
            long_host = create_component(graph_node_host_qml_path, {"nodeData": long_payload})
            wait_for_surface(long_host, "graphSelectSurface")
            long_label = named_item(long_host, "graphSelectNameLabel")
            long_section = named_item(long_host, "graphSelectNameSection")
            long_combo = named_item(long_host, "graphSelectComboBox")
            settle_events(4)
            assert float(long_label.width()) >= float(long_label.property("implicitWidth")), (
                long_label.width(), long_label.property("implicitWidth")
            )
            assert float(long_section.x()) + float(long_section.width()) < float(long_combo.x()), (
                long_section.x(), long_section.width(), long_combo.x()
            )
            assert float(long_combo.width()) > 0.0
            assert abs(
                float(long_section.width())
                - max(float(long_label.property("implicitWidth")) + 26.0, 82.0)
            ) < 0.01
            long_host.deleteLater()
            scene.deleteLater()

            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_real_canvas_select_settings_edit_and_cancel(self) -> None:
        self._run_qml_probe(
            "select-settings-real-canvas",
            """
            def node_card_for(canvas_item, node_id):
                for item in named_child_items(canvas_item, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            def click(window, item):
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(item),
                )
                settle_events(4)

            def wait_for_named_object(root, object_name, attempts=100):
                for _attempt in range(attempts):
                    for candidate in walk_items(root):
                        if candidate.objectName() == object_name:
                            return candidate
                    settle_events(2)
                names = sorted(
                    str(candidate.objectName())
                    for candidate in walk_items(root)
                    if "graphSelectSettings" in str(candidate.objectName())
                )
                raise AssertionError(f"object {object_name!r} never loaded; found={names}")

            def replace_text(window, field, text):
                click(window, field)
                field.forceActiveFocus()
                settle_events(2)
                QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                for character in text:
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyPress,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyRelease,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                settle_events(4)

            def wait_for_text(root, object_name, expected, attempts=100):
                for _attempt in range(attempts):
                    for candidate in walk_items(root):
                        if candidate.objectName() == object_name:
                            actual = str(candidate.property("text"))
                            if actual == expected:
                                return candidate
                    settle_events(2)
                raise AssertionError(f"{object_name!r} did not show {expected!r}")

            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("data.select", 120.0, 90.0)
            scene.set_node_property(node_id, "selected_index", 1)
            scene.select_node(node_id, False)

            history = RuntimeGraphHistory()
            scene.bind_runtime_history(history)
            history.clear_workspace(workspace_id)

            view = ViewportBridge()
            view.set_viewport_size(760.0, 560.0)
            view.set_view_state(1.0, 250.0, 180.0)
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 760.0,
                    "height": 560.0,
                },
            )
            window = attach_host_to_window(canvas, width=760, height=560)
            try:
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphSelectSurface")
                settings_button = named_item(card, "graphSelectSettingsButton")
                overlay = named_item(canvas, "graphSelectOverlayLayer")
                popover = named_item(canvas, "graphSelectSettingsPopover")

                assert surface is not None
                click(window, settings_button)
                assert bool(surface.property("selectSettingsEditorOpen"))
                assert bool(overlay.property("visible"))
                assert bool(popover.property("visible"))
                assert str(wait_for_named_object(popover, "graphSelectSettingsNameField_0").property("text")) == "Option A"
                assert str(wait_for_named_object(popover, "graphSelectSettingsValueField_1").property("text")) == "1"

                click(window, named_item(popover, "graphSelectSettingsAddButton"))
                assert str(wait_for_named_object(popover, "graphSelectSettingsNameField_2").property("text")) == "Option C"
                value_c = wait_for_named_object(popover, "graphSelectSettingsValueField_2")
                assert str(value_c.property("placeholderText")) == "Enter value"
                assert str(value_c.property("text")) == ""
                replace_text(window, value_c, "2")

                click(window, named_item(popover, "graphSelectSettingsRowCheck_1"))
                click(window, named_item(popover, "graphSelectSettingsDeleteButton"))
                assert int(popover.property("selectedIndexDraft")) == 1

                click(window, named_item(popover, "graphSelectSettingsRowCheck_1"))
                click(window, named_item(popover, "graphSelectSettingsMoveUpButton"))
                wait_for_text(popover, "graphSelectSettingsNameField_0", "Option C")
                assert int(popover.property("selectedIndexDraft")) == 0
                assert int(popover.property("singleCheckedIndex")) == 0
                move_down = named_item(popover, "graphSelectSettingsMoveDownButton")
                assert bool(move_down.property("enabled"))
                click(window, move_down)
                assert int(popover.property("singleCheckedIndex")) == 1
                wait_for_text(popover, "graphSelectSettingsNameField_1", "Option C")
                assert int(popover.property("selectedIndexDraft")) == 1

                click(window, named_item(popover, "graphSelectSettingsHeaderCheck"))
                assert not bool(named_item(popover, "graphSelectSettingsDeleteButton").property("enabled"))

                click(window, named_item(popover, "graphSelectSettingsCancelButton"))
                assert not bool(surface.property("selectSettingsEditorOpen"))
                assert not bool(overlay.property("visible"))
                stored = model.active_workspace.nodes[node_id].properties
                assert stored["options"] == [
                    {"name": "Option A", "value": "0"},
                    {"name": "Option B", "value": "1"},
                ]
                assert stored["selected_index"] == 1
                assert history.undo_depth(workspace_id) == 0

            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_real_canvas_select_settings_close_does_not_commit(self) -> None:
        self._run_qml_probe(
            "select-settings-close",
            """
            def node_card_for(canvas_item, node_id):
                for item in named_child_items(canvas_item, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            def click(window, item):
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(item),
                )
                settle_events(4)

            def wait_for_named_item(root, object_name, attempts=200):
                for _attempt in range(attempts):
                    for candidate in walk_items(root):
                        if candidate.objectName() == object_name:
                            return candidate
                    settle_events(2)
                raise AssertionError(f"item {object_name!r} never loaded")

            def replace_text(window, field, text):
                click(window, field)
                field.forceActiveFocus()
                settle_events(2)
                QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                for character in text:
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyPress,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyRelease,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                settle_events(4)

            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("data.select", 120.0, 90.0)
            scene.select_node(node_id, False)
            history = RuntimeGraphHistory()
            scene.bind_runtime_history(history)
            history.clear_workspace(workspace_id)

            view = ViewportBridge()
            view.set_viewport_size(760.0, 560.0)
            view.set_view_state(1.0, 250.0, 180.0)
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 760.0,
                    "height": 560.0,
                },
            )
            window = attach_host_to_window(canvas, width=760, height=560)
            try:
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphSelectSurface")
                overlay = named_item(canvas, "graphSelectOverlayLayer")
                click(window, named_item(card, "graphSelectSettingsButton"))
                popover = named_item(canvas, "graphSelectSettingsPopover")
                replace_text(
                    window,
                    wait_for_named_item(popover, "graphSelectSettingsNameField_0"),
                    "Renamed",
                )
                click(window, named_item(popover, "dialogSurfaceCloseButton"))

                assert not bool(surface.property("selectSettingsEditorOpen"))
                assert not bool(overlay.property("visible"))
                stored = model.active_workspace.nodes[node_id].properties
                assert stored["options"] == [
                    {"name": "Option A", "value": "0"},
                    {"name": "Option B", "value": "1"},
                ]
                assert stored["selected_index"] == 0
                assert history.undo_depth(workspace_id) == 0
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_real_canvas_select_settings_accept_is_one_undoable_edit(self) -> None:
        self._run_qml_probe(
            "select-settings-atomic-accept",
            """
            def node_card_for(canvas_item, node_id):
                for item in named_child_items(canvas_item, "graphNodeCard"):
                    node_data = variant_value(item.property("nodeData")) or {}
                    if str(node_data.get("node_id", "")) == str(node_id):
                        return item
                raise AssertionError(f"Missing node card for {node_id!r}")

            def click(window, item):
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(item),
                )
                settle_events(4)

            def wait_for_named_item(root, object_name, attempts=200):
                for _attempt in range(attempts):
                    for candidate in walk_items(root):
                        if candidate.objectName() == object_name:
                            return candidate
                    settle_events(2)
                raise AssertionError(f"item {object_name!r} never loaded")

            def replace_text(window, field, text):
                click(window, field)
                field.forceActiveFocus()
                settle_events(2)
                QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                for character in text:
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyPress,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                    app.sendEvent(
                        window,
                        QKeyEvent(
                            QEvent.Type.KeyRelease,
                            0,
                            Qt.KeyboardModifier.NoModifier,
                            character,
                        ),
                    )
                settle_events(4)

            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            node_id = scene.add_node_from_type("data.select", 120.0, 90.0)
            scene.set_node_property(node_id, "selected_index", 1)
            scene.select_node(node_id, False)

            history = RuntimeGraphHistory()
            scene.bind_runtime_history(history)
            history.clear_workspace(workspace_id)

            view = ViewportBridge()
            view.set_viewport_size(760.0, 560.0)
            view.set_view_state(1.0, 250.0, 180.0)
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "sceneBridge": scene,
                    "viewBridge": view,
                    "width": 760.0,
                    "height": 560.0,
                },
            )
            window = attach_host_to_window(canvas, width=760, height=560)
            try:
                settle_events(10)
                card = node_card_for(canvas, node_id)
                surface = card.findChild(QObject, "graphSelectSurface")
                overlay = named_item(canvas, "graphSelectOverlayLayer")
                click(window, named_item(card, "graphSelectSettingsButton"))
                popover = named_item(canvas, "graphSelectSettingsPopover")

                click(window, named_item(popover, "graphSelectSettingsAddButton"))
                replace_text(
                    window,
                    wait_for_named_item(popover, "graphSelectSettingsNameField_2"),
                    "Choice C",
                )
                replace_text(
                    window,
                    wait_for_named_item(popover, "graphSelectSettingsValueField_2"),
                    "2",
                )
                click(window, wait_for_named_item(popover, "graphSelectSettingsRowCheck_1"))
                click(window, named_item(popover, "graphSelectSettingsMoveDownButton"))
                click(window, named_item(popover, "graphSelectSettingsAcceptButton"))

                assert not bool(surface.property("selectSettingsEditorOpen"))
                assert not bool(overlay.property("visible"))
                stored = model.active_workspace.nodes[node_id].properties
                assert stored["options"] == [
                    {"name": "Option A", "value": "0"},
                    {"name": "Choice C", "value": "2"},
                    {"name": "Option B", "value": "1"},
                ]
                assert stored["selected_index"] == 2
                assert history.undo_depth(workspace_id) == 1

                assert history.undo_workspace(workspace_id, model.active_workspace) is not None
                scene.refresh_workspace_from_model(workspace_id)
                settle_events(4)
                stored = model.active_workspace.nodes[node_id].properties
                assert stored["options"] == [
                    {"name": "Option A", "value": "0"},
                    {"name": "Option B", "value": "1"},
                ]
                assert stored["selected_index"] == 1
                assert history.undo_depth(workspace_id) == 0
            finally:
                dispose_host_window(canvas, window)
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_select_qml_uses_existing_controls_and_root_overlay(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        surface = (
            root
            / "ea_node_editor/ui_qml/components/graph/passive/GraphSelectSurface.qml"
        ).read_text(encoding="utf-8")
        popover = (
            root
            / "ea_node_editor/ui_qml/components/graph/passive/GraphSelectSettingsPopover.qml"
        ).read_text(encoding="utf-8")
        layers = (
            root / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"
        ).read_text(encoding="utf-8")
        overlay = (
            root
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSurfaceEditorOverlays.qml"
        ).read_text(encoding="utf-8")

        assert "SurfaceControls.GraphSurfaceComboBox" in surface
        assert "SurfaceControls.GraphSurfaceButton" in surface
        assert "commitNodeSurfaceProperties" in surface
        assert "Common.DialogSurface" in popover
        assert "Common.DialogTextField" in popover
        assert "ListModel" in popover
        assert "property alias selectEditorHost: surfaceEditorOverlays.selectEditorHost" in layers
        assert "GraphCanvasSurfaceEditorOverlays {" in layers
        assert 'String(actionId || "") === "select_edit_settings"' in overlay
        assert "GraphPassive.GraphSelectSettingsPopover" in overlay
