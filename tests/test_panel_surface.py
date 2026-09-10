from __future__ import annotations

from ea_node_editor.ui_qml.surface_contracts import surface_spec_payload_for_values
from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase


def test_panel_surface_contract_routes_to_panel_qml() -> None:
    payload = surface_spec_payload_for_values(
        type_id="data.panel",
        family="standard",
        variant="panel",
    )
    assert payload["component_key"] == "panel"
    assert payload["qml_component"] == "passive/GraphPanelSurface.qml"
    assert payload["layout"] == {
        "content_region": "host",
        "min_body_width": 120.0,
        "min_body_height": 40.0,
        "preferred_body_height": 180.0,
    }


class PanelSurfaceTests(PassiveGraphSurfaceHostTestBase):
    def test_panel_surface_projection_actions_and_draft_editor(self) -> None:
        self._run_qml_probe(
            "panel-surface",
            r'''
            def wait_for_surface(host, object_name, attempts=200):
                for _attempt in range(attempts):
                    settle_events(2)
                    for child in walk_items(host):
                        if child.objectName() == object_name:
                            return child
                raise AssertionError(f"surface item {object_name!r} never loaded")

            def create_inline(source, name):
                component = QQmlComponent(engine)
                base_url = QUrl.fromLocalFile(str(components_dir / name))
                component.setData(source.encode("utf-8"), base_url)
                if component.status() != QQmlComponent.Status.Ready:
                    errors = "\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to load inline {name}:\n{errors}")
                obj = component.create()
                if obj is None:
                    errors = "\n".join(error.toString() for error in component.errors())
                    raise AssertionError(f"Failed to instantiate inline {name}:\n{errors}")
                settle_events(3)
                return obj

            payload = node_payload(surface_family="standard", surface_variant="panel")
            payload["type_id"] = "data.panel"
            payload["title"] = "Panel"
            payload["display_name"] = "Panel"
            payload["width"] = 280.0
            payload["height"] = 180.0
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="data.panel",
                family="standard",
                variant="panel",
            )
            payload["properties"] = {
                "value": "",
                "mode": 0,
                "font_size": 12,
                "alignment": 2,
                "auto_resize": True,
                "interpretation": "text",
            }
            payload["ports"] = [
                {
                    "key": "input",
                    "label": "Input",
                    "direction": "in",
                    "kind": "data",
                    "data_type": "any",
                    "data_access": "tree",
                    "connected": False,
                    "required": False,
                },
                {
                    "key": "output",
                    "label": "Output",
                    "direction": "out",
                    "kind": "data",
                    "data_type": "any",
                    "data_access": "tree",
                    "connected": False,
                },
            ]
            payload["inline_properties"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = wait_for_surface(host, "graphPanelSurface")
            assert bool(surface.property("placeholderVisible"))
            assert str(surface.property("placeholderText")) == "Double click to edit..."
            assert variant_list(surface.property("embeddedInteractiveRects")) == []
            assert bool(surface.requestInlineEditAt(10.0, 10.0))
            assert bool(surface.property("panelEditorOpen"))
            surface.cancelPanelSettings()

            actions = [variant_value(item) for item in variant_list(surface.property("surfaceActions"))]
            assert [item["id"] for item in actions] == [
                "panel_font_increase",
                "panel_font_decrease",
                "panel_align_left",
                "panel_align_right",
                "panel_fit_width",
                "panel_fit_height",
            ]
            assert [item["label"] for item in actions] == [
                "Increase font size",
                "Decrease font size",
                "Align left",
                "Align right",
                "Fit width",
                "Fit height",
            ]
            assert [item["description"] for item in actions] == [
                "Make the text a bit bigger.",
                "Make the text a bit smaller.",
                "Align the content with the left margin.",
                "Align the content with the right margin.",
                "Adjust the node to fit the text without line breaks.",
                "Adjust the node to fit the content without a scrollbar.",
            ]
            assert all(item["kind"] == "surface" for item in actions)
            assert [item["icon"] for item in actions] == [
                "text-increase",
                "text-decrease",
                "format-align-left",
                "format-align-right",
                "fit-width",
                "fit-height",
            ]
            assert actions[2]["checked"] is False
            assert actions[3]["checked"] is False

            metrics = variant_value(host.property("surfaceMetrics"))
            assert metrics["header_height"] == 0.0
            assert metrics["body_top"] == 0.0
            assert metrics["body_height"] == 180.0
            assert metrics["port_center_offset"] == 20.0
            assert metrics["use_host_chrome"] is True

            host_origin = host.mapToScene(QPointF(0.0, 0.0))
            for object_name in ("graphNodeInputPortDot", "graphNodeOutputPortDot"):
                dot = named_item(host, object_name)
                dot_center = dot.mapToScene(QPointF(dot.width() * 0.5, dot.height() * 0.5))
                assert abs((dot_center.y() - host_origin.y()) - 20.0) < 0.5
            assert not bool(named_item(host, "graphNodeInputPortLabel").property("visible"))
            assert not bool(named_item(host, "graphNodeOutputPortLabel").property("visible"))

            commits = []
            resizes = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append((node_id, key, variant_value(value)))
            )
            host.resizeFinished.connect(
                lambda node_id, x, y, width, height: resizes.append(
                    (node_id, float(x), float(y), float(width), float(height))
                )
            )
            assert bool(surface.dispatchSurfaceAction("panel_font_increase"))
            assert commits == [("node_surface_host_test", "font_size", 13)]
            assert bool(surface.dispatchSurfaceAction("panel_fit_height"))
            assert resizes[-1][0] == "node_surface_host_test"
            assert resizes[-1][3] == 280.0
            assert resizes[-1][4] >= 40.0

            authored_payload = dict(payload)
            authored_payload["properties"] = dict(payload["properties"])
            authored_payload["properties"].update({
                "value": "root\n* 0;1\nchild-a\nchild-b",
                "mode": 1,
                "auto_resize": False,
            })
            authored_host = create_component(graph_node_host_qml_path, {"nodeData": authored_payload})
            authored_surface = wait_for_surface(authored_host, "graphPanelSurface")
            authored_rows = [
                variant_value(item)
                for item in variant_list(authored_surface.property("displayRows"))
            ]
            assert authored_rows == [
                {"kind": "branch", "path": "0"},
                {"kind": "item", "path": "0", "index": 0, "text": "root"},
                {"kind": "branch", "path": "0;1"},
                {"kind": "item", "path": "0;1", "index": 0, "text": "child-a"},
                {"kind": "item", "path": "0;1", "index": 1, "text": "child-b"},
            ]
            assert authored_surface._authoredCopyText(False) == "root\nchild-a\nchild-b"
            assert authored_surface._authoredCopyText(True) == (
                "* 0\nroot\n* 0;1\nchild-a\nchild-b"
            )
            assert bool(named_item(authored_surface, "graphPanelDataList").property("visible"))
            assert named_item(authored_surface, "graphPanelVerticalScrollBar") is not None

            fake_host = create_inline(
                r"""
                import QtQuick 2.15
                Item {
                    width: 280
                    height: 180
                    property var nodeData: ({
                        "node_id": "node_surface_host_test",
                        "x": 30,
                        "y": 40,
                        "properties": {
                            "value": "ignored",
                            "mode": 0,
                            "font_size": 12,
                            "alignment": 2,
                            "auto_resize": false,
                            "interpretation": "text"
                        }
                    })
                    property var inputPorts: [{"key": "input", "connected": true}]
                    property var executionFacts: QtObject {
                        property var portValuePreviewLookup: ({
                            "node_surface_host_test": {
                                "output": {"rows": [
                                    {"kind": "branch", "path": "0;1"},
                                    {"kind": "item", "path": "0;1", "index": 0, "text": "10"},
                                    {"kind": "item", "path": "0;1", "index": 1, "text": "20"}
                                ]}
                            }
                        })
                    }
                    property bool graphReadOnly: false
                    property bool surfaceInteractionLocked: false
                    property color inlineInputTextColor: "#eef3ff"
                    property color outlineColor: "#586174"
                    property color headerTextColor: "#eef3ff"
                    property color inlineInputBackgroundColor: "#202530"
                    property color inlineInputBorderColor: "#586174"
                    property color selectedOutlineColor: "#60cdff"
                    property color surfaceColor: "#1b1f2a"
                    property int nodeTextRenderType: Text.CurveRendering
                    property var graphSharedTypography: null
                    property Item canvasItem: Item {
                        property var lastPayload: ({})
                        property var canvasStateBridge: QtObject {
                            property bool lastAsTree: false
                            function panel_display_rows(nodeId) {
                                return [
                                    {"kind": "branch", "path": "9"},
                                    {"kind": "item", "path": "9", "index": 0, "text": "complete"}
                                ]
                            }
                            function panel_copy_text(nodeId, asTree) {
                                lastAsTree = Boolean(asTree)
                                return asTree ? "* 0;1\n10\n20" : "10\n20"
                            }
                        }
                        function commitNodeSurfaceProperties(nodeId, payload) {
                            lastPayload = payload
                            return true
                        }
                    }
                    signal inlinePropertyCommitted(string nodeId, string key, var value)
                    signal resizeFinished(string nodeId, real x, real y, real width, real height)
                }
                """,
                "PanelFakeHost.qml",
            )
            panel_qml_path = components_dir / "graph" / "passive" / "GraphPanelSurface.qml"
            runtime_surface = create_component(panel_qml_path, {"host": fake_host})
            runtime_surface.setWidth(280)
            runtime_surface.setHeight(180)
            settle_events(5)
            runtime_rows = [
                variant_value(item)
                for item in variant_list(runtime_surface.property("displayRows"))
            ]
            assert runtime_rows == [
                {"kind": "branch", "path": "9"},
                {"kind": "item", "path": "9", "index": 0, "text": "complete"},
            ]
            assert bool(runtime_surface.property("inputConnected"))
            assert runtime_surface.property("interpretationLabel") == "Input"
            assert bool(runtime_surface.dispatchSurfaceAction("panel_copy_tree"))
            canvas_stub = fake_host.property("canvasItem")
            bridge_stub = canvas_stub.property("canvasStateBridge")
            assert bool(bridge_stub.property("lastAsTree"))
            fake_host.setProperty("inputPorts", [{"key": "input", "connected": False}])
            settle_events(3)
            assert not bool(runtime_surface.property("inputConnected"))
            QApplication.clipboard().clear()
            assert bool(runtime_surface.dispatchSurfaceAction("panel_copy"))
            settle_events(2)
            assert QApplication.clipboard().text() == "ignored"
            fake_host.setProperty("inputPorts", [{"key": "input", "connected": True}])
            settle_events(3)
            assert bool(runtime_surface.dispatchSurfaceAction("panel_edit"))

            assert bool(runtime_surface.acceptPanelSettings({
                "value": "draft",
                "mode": 1,
                "font_size": 14,
                "alignment": 0,
                "auto_resize": False,
                "interpretation": "auto",
            }))
            committed_payload = variant_value(canvas_stub.property("lastPayload"))
            assert committed_payload == {
                "value": "draft",
                "mode": 1,
                "font_size": 14,
                "alignment": 0,
                "auto_resize": False,
                "interpretation": "auto",
            }

            editor_qml_path = components_dir / "graph" / "passive" / "GraphPanelEditorPopover.qml"
            editor = create_component(editor_qml_path, {"host": fake_host})
            editor.setWidth(320)
            editor.setHeight(float(editor.property("implicitHeight")))
            accepted = []
            canceled = []
            editor.accepted.connect(lambda value: accepted.append(variant_value(value)))
            editor.canceled.connect(lambda: canceled.append(True))
            settings = {
                "value": "original",
                "mode": 0,
                "font_size": 12,
                "alignment": 2,
                "auto_resize": True,
                "interpretation": "text",
            }
            editor.openWithSettings(settings)
            interpretation_selector = named_item(editor, "graphPanelEditorInterpretationSelector")
            assert not bool(interpretation_selector.property("visible")), "Text mode selector visible"
            value_field = named_item(editor, "graphPanelEditorValueField")
            value_field.setProperty("text", "discarded")
            editor.cancelEdit()
            assert canceled == [True]
            assert accepted == []

            editor.openWithSettings(settings)
            value_field.setProperty("text", "accepted")
            editor.setProperty("modeDraft", 1)
            editor.setProperty("interpretationDraft", "number")
            editor.setProperty("autoResizeDraft", False)
            editor.acceptEdit()
            assert accepted == [{
                "value": "accepted",
                "mode": 1,
                "font_size": 12,
                "alignment": 2,
                "auto_resize": False,
                "interpretation": "number",
            }]
            editor.openWithSettings(settings)
            assert editor.property("interpretationDraft") == "text"
            editor.setProperty("modeDraft", 1)
            editor.setProperty("interpretationDraft", "auto")
            editor.cancelEdit()
            editor.openWithSettings(dict(settings, mode=1, input_connected=True))
            assert not bool(interpretation_selector.property("enabled")), "Connected selector enabled"
            editor.cancelEdit()

            root_layers_qml_path = components_dir / "graph_canvas" / "GraphCanvasRootLayers.qml"
            root_layers_component = QQmlComponent(engine, QUrl.fromLocalFile(str(root_layers_qml_path)))
            if root_layers_component.status() != QQmlComponent.Status.Ready:
                errors = "\n".join(error.toString() for error in root_layers_component.errors())
                raise AssertionError(f"Failed to load GraphCanvasRootLayers.qml:\n{errors}")

            runtime_surface.deleteLater()
            fake_host.deleteLater()
            editor.deleteLater()
            authored_host.deleteLater()
            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            ''',
        )

    def test_panel_reference_surface_details(self) -> None:
        self._run_qml_probe(
            "panel-reference-details",
            r'''
            payload = node_payload(surface_family="standard", surface_variant="panel")
            payload.update({
                "type_id": "data.panel",
                "title": "Panel",
                "display_name": "Panel",
                "width": 280.0,
                "height": 180.0,
                "surface_spec": surface_spec_payload_for_values(
                    type_id="data.panel", family="standard", variant="panel"
                ),
                "properties": {
                    "value": "* 0\n10\n20",
                    "mode": 1,
                    "font_size": 12,
                    "alignment": 2,
                    "auto_resize": False,
                    "interpretation": "text",
                },
                "inline_properties": [],
            })
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = next(
                item for item in walk_items(host)
                if item.objectName() == "graphPanelSurface"
            )
            actions = [variant_value(item) for item in variant_list(surface.property("surfaceActions"))]
            available = [variant_value(item) for item in variant_list(host.property("availableActions"))]
            assert [item["id"] for item in available] == [item["id"] for item in actions]
            assert [bool(item.get("separator_after", False)) for item in actions] == [
                False, True, False, True, False, False
            ]
            assert float(host.property("resolvedCornerRadius")) == 16.0

            rows = [variant_value(item) for item in variant_list(surface.property("displayRows"))]
            assert rows == [
                {"kind": "branch", "path": "0"},
                {"kind": "item", "path": "0", "index": 0, "text": "10"},
                {"kind": "item", "path": "0", "index": 1, "text": "20"},
            ]
            payload["read_only"] = True
            read_only_host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            read_only_surface = next(
                item for item in walk_items(read_only_host)
                if item.objectName() == "graphPanelSurface"
            )
            QApplication.clipboard().clear()
            assert bool(read_only_host.dispatchSurfaceAction("panel_copy_tree")), "read-only copy was blocked"
            settle_events(2)
            assert QApplication.clipboard().text() == "* 0\n10\n20", repr(QApplication.clipboard().text())
            assert not bool(read_only_host.dispatchSurfaceAction("panel_font_increase")), "read-only format changed"
            assert not bool(read_only_surface.property("panelEditable")), "read-only surface reported editable"
            assert not bool(read_only_surface.dispatchSurfaceAction("panel_edit"))
            assert not bool(read_only_surface.acceptPanelSettings({"interpretation": "number"}))
            settle_events(5)
            branch_path = named_item(surface, "graphPanelBranchPath")
            item_index = named_item(surface, "graphPanelItemIndex")
            item_value = named_item(surface, "graphPanelItemValue")
            assert str(item_value.property("font").family()) == "Consolas"

            commits = []
            resizes = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append((str(key), variant_value(value)))
            )
            host.resizeFinished.connect(
                lambda node_id, x, y, width, height: resizes.append((float(width), float(height)))
            )
            for action_id in (
                "panel_font_increase", "panel_font_decrease",
                "panel_align_left", "panel_align_right",
                "panel_fit_width", "panel_fit_height",
            ):
                assert bool(surface.dispatchSurfaceAction(action_id))
            assert commits == [
                ("font_size", 13), ("font_size", 11),
                ("alignment", 0), ("alignment", 1),
            ]
            assert len(resizes) == 2
            read_only_host.deleteLater()
            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            ''',
        )

    def test_real_canvas_double_click_opens_panel_editor_for_empty_and_data_modes(self) -> None:
        self._run_qml_probe(
            "panel-real-double-click",
            r'''
            from PyQt6.QtCore import QPoint
            from PyQt6.QtGui import QFont, QFontDatabase
            from PyQt6.QtTest import QTest
            from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

            # The offscreen Windows platform does not discover system fonts.
            for font_file in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf", "consola.ttf"):
                QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font_file)
            app.setFont(QFont("Segoe UI", 10))

            model = GraphModel()
            registry = build_default_registry()
            workspace_id = model.active_workspace.workspace_id
            scene = GraphSceneBridge()
            scene.set_workspace(model, registry, workspace_id)
            panel_node_id = scene.add_node_from_type("data.panel", 120.0, 120.0)

            view = ViewportBridge()
            view.set_viewport_size(800.0, 600.0)
            view.set_view_state(1.0, 260.0, 210.0)
            canvas_state_bridge = GraphCanvasStateBridge(
                scene_bridge=scene,
                view_bridge=view,
            )
            canvas_command_bridge = GraphCanvasCommandBridge(
                scene_bridge=scene,
                view_bridge=view,
            )
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 800.0,
                    "height": 600.0,
                },
            )
            window = attach_host_to_window(canvas, width=800, height=600)

            try:
                settle_events(8)
                host = next(
                    item for item in named_child_items(canvas, "graphNodeCard")
                    if str(variant_value(item.property("nodeData")).get("node_id", "")) == panel_node_id
                )
                surface = next(
                    item for item in walk_items(host)
                    if item.objectName() == "graphPanelSurface"
                )
                panel_body = named_item(surface, "graphPanelBody")
                overlay = named_item(canvas, "graphPanelOverlayLayer")
                editor = named_item(canvas, "graphPanelEditorPopover")
                empty_point = item_scene_point(panel_body)
                empty_node = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert empty_node["width"] == 280.0, empty_node
                assert empty_node["height"] == 180.0, empty_node
                mouse_double_click(window, empty_point)
                settle_events(8)
                assert bool(overlay.property("visible")), "empty Panel overlay did not open"
                assert bool(editor.property("visible")), "empty Panel editor did not open"
                assert bool(surface.property("panelEditorOpen")), "empty Panel flag stayed closed"

                QTest.keyClick(window, Qt.Key.Key_Escape)
                settle_events(5)
                assert not bool(editor.property("visible")), "Escape did not close Panel editor"

                scene.set_node_property(panel_node_id, "value", "1")
                settle_events(10)
                fitted = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert fitted["x"] == 120.0, fitted
                assert fitted["y"] == 120.0, fitted
                assert fitted["width"] == 120.0, fitted
                assert fitted["height"] == 40.0, fitted

                scene.set_node_property(panel_node_id, "value", "* 0\n10\n20")
                scene.set_node_property(panel_node_id, "mode", 1)
                settle_events(10)
                assert bool(named_item(surface, "graphPanelDataList").property("visible")), "Data rows did not render"
                fitted = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert fitted["width"] == 120.0, fitted
                assert fitted["height"] == 136.0, fitted
                badge = named_item(surface, "graphPanelInterpretationBadge")
                data_list = named_item(surface, "graphPanelDataList")
                assert badge.mapToScene(QPointF(0, badge.height())).y() < data_list.mapToScene(QPointF(0, 0)).y()
                proof_dir = repo_root / "artifacts" / "panel_interpretation"
                proof_dir.mkdir(parents=True, exist_ok=True)
                assert window.grabWindow().save(str(proof_dir / "compact-data-panel.png"))

                drag_start = item_scene_point(panel_body)
                drag_end = QPoint(drag_start.x() + 40, drag_start.y() + 30)
                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, drag_start)
                QTest.mouseMove(window, drag_end)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, drag_end)
                settle_events(10)
                moved = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert moved["x"] == 160.0, moved
                assert moved["y"] == 150.0, moved
                history = RuntimeGraphHistory()
                scene.bind_runtime_history(history)
                depth_before_edit = history.undo_depth(workspace_id)

                QTest.mouseDClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    item_scene_point(panel_body),
                )
                settle_events(8)
                assert bool(overlay.property("visible")), "Data Panel overlay did not open"
                assert bool(editor.property("visible")), "Data Panel editor did not open"

                value_field = named_item(editor, "graphPanelEditorValueField")
                selector = named_item(editor, "graphPanelEditorInterpretationSelector")
                assert bool(selector.property("visible"))
                selector.forceActiveFocus()
                QTest.keyClick(window, Qt.Key.Key_End)
                settle_events(4)
                assert editor.property("interpretationDraft") == "number", "Keyboard selection did not update the draft"
                editor.setProperty("autoResizeDraft", False)
                for theme_name, palette in (
                    ("dark", {"panel_bg": "#202530", "panel_title_fg": "#eef3ff", "muted_fg": "#a6b3c8", "input_bg": "#171e29", "input_border": "#465066", "accent": "#268cca"}),
                    ("light", {"panel_bg": "#f6f8fb", "panel_title_fg": "#182431", "muted_fg": "#526174", "input_bg": "#ffffff", "input_border": "#b2bdcc", "accent": "#167cab"}),
                ):
                    editor.setProperty("themePalette", palette)
                    QTest.qWait(220)
                    assert window.grabWindow().save(str(proof_dir / ("editor-" + theme_name + ".png")))
                value_field.forceActiveFocus()
                assert bool(value_field.property("activeFocus"))
                value_field.setProperty("text", "edited")
                value_field.setProperty("cursorPosition", len("edited"))
                QTest.keyClick(window, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
                assert str(value_field.property("text")) == "edited\n"
                value_field.setProperty("text", "edited\nline")
                QTest.keyClick(window, Qt.Key.Key_Return)
                settle_events(10)
                assert not bool(editor.property("visible")), "Enter did not accept Panel editor"
                saved = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert saved["properties"]["value"] == "edited\nline"
                assert saved["properties"]["interpretation"] == "number"
                assert history.undo_depth(workspace_id) == depth_before_edit + 1

                mouse_double_click(window, item_scene_point(panel_body))
                settle_events(8)
                value_field.setProperty("text", "discarded")
                editor.setProperty("interpretationDraft", "auto")
                QTest.keyClick(window, Qt.Key.Key_Escape)
                settle_events(8)
                saved = next(item for item in scene.nodes_model if item["node_id"] == panel_node_id)
                assert saved["properties"]["value"] == "edited\nline"
                assert saved["properties"]["interpretation"] == "number"
                assert history.undo_depth(workspace_id) == depth_before_edit + 1
                history.undo_workspace(workspace_id, model.active_workspace)
                restored = model.active_workspace.nodes[panel_node_id]
                assert restored.properties["interpretation"] == "text"
                assert restored.properties["value"] == "* 0\n10\n20"
            finally:
                dispose_host_window(canvas, window)
                scene.deleteLater()
                engine.deleteLater()
                app.processEvents()
            ''',
        )
