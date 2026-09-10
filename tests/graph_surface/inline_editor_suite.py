from __future__ import annotations

from tests.graph_surface.environment import *  # noqa: F403

class PassiveGraphSurfaceInlineEditorTests(PassiveGraphSurfaceHostTestBase):
    def test_passive_annotation_text_double_click_edits_markdown_source_and_commits(self) -> None:
        self._run_qml_probe(
            "annotation-text-inline-edit-host",
            """
            from urllib.parse import quote
            payload = flowchart_payload("decision")
            payload["type_id"] = "passive.annotation.text"
            payload["display_name"] = "Text"
            payload["title"] = "Text"
            payload["surface_family"] = "annotation"
            payload["surface_variant"] = "text"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="passive.annotation.text",
                family="annotation",
                variant="text",
            )
            payload["surface_metrics"] = {
                "default_width": 240.0,
                "default_height": 96.0,
                "min_width": 80.0,
                "min_height": 32.0,
                "body_top": 4.0,
                "body_height": 88.0,
                "body_left_margin": 4.0,
                "body_right_margin": 4.0,
                "body_bottom_margin": 4.0,
                "port_top": 92.0,
                "port_height": 0.0,
                "port_center_offset": 0.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
                "use_host_chrome": False,
            }
            payload["width"] = 240.0
            payload["height"] = 96.0
            payload["properties"] = {
                "text": "**Markdown** note",
                "format": "markdown",
                "font_family": "",
                "font_size": 20,
                "font_weight": "bold",
                "italic": False,
                "underline": False,
                "strikeout": False,
                "text_color": "#AABBCC",
                "background_color": "",
                "horizontal_alignment": "center",
                "vertical_alignment": "middle",
                "wrap_mode": "word",
                "line_height": 1.2,
                "letter_spacing": 0.0,
                "padding": 4,
                "opacity": 100,
            }
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                rendered = host.findChild(QObject, "graphBareTextRenderedText")
                editor = host.findChild(QObject, "graphBareTextEditor")
                editor_probe = host.findChild(QObject, "graphBareTextEditorLayoutProbe")
                surface = host.findChild(QObject, "graphBareTextSurface")
                loader = host.findChild(QObject, "graphNodeSurfaceLoader")
                drag_area = host.findChild(QObject, "graphNodeDragArea")
                assert rendered is not None
                assert editor is not None
                assert editor_probe is not None
                assert surface is not None
                assert loader is not None
                assert drag_area is not None
                assert bool(rendered.property("visible"))
                assert not bool(editor.property("visible"))
                assert str(rendered.property("text") or "") == "**Markdown** note"
                assert rendered.property("color").name().lower() == "#aabbcc"
                assert rendered.property("font").pixelSize() == 20
                assert rendered.property("font").bold()
                assert str(surface.property("resolvedFontFamily") or "")
                assert rendered.property("font").family() == str(surface.property("resolvedFontFamily"))
                assert bool(surface.property("renderedTextRendererHighQualityActive"))
                assert bool(surface.property("placeholderTextRendererHighQualityActive"))
                assert bool(surface.property("editorTextRendererHighQualityActive"))
                assert variant_list(loader.property("embeddedInteractiveRects")) == []

                committed = []
                events = host_pointer_events(host)
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                text_point = item_scene_point(rendered)
                mouse_click(window, text_point)
                settle_events(4)
                assert events["clicked"] == [("node_surface_host_test", False)]
                assert not bool(editor.property("visible"))

                QTest.mouseMove(window, text_point)
                settle_events(4)
                assert drag_area.property("cursorShape") == Qt.CursorShape.OpenHandCursor

                mouse_double_click(window, item_scene_point(rendered))
                settle_events(5)

                assert bool(editor.property("visible"))
                assert bool(editor.property("activeFocus"))
                assert str(editor.property("text") or "") == "**Markdown** note"
                assert len(variant_list(loader.property("embeddedInteractiveRects"))) == 1
                expected_vertical_padding = round(
                    max(0.0, float(host.property("height")) - 8.0 - float(editor_probe.property("contentHeight"))) / 2.0
                )
                assert abs(float(editor.property("topPadding")) - expected_vertical_padding) <= 1.0, (
                    editor.property("topPadding"),
                    expected_vertical_padding,
                )

                editor.setProperty("text", "Updated **markdown**")
                app.processEvents()
                QTest.keyClick(window, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
                settle_events(5)

                assert committed == [("node_surface_host_test", "text", "Updated **markdown**")]
                assert not bool(editor.property("visible"))

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_toggle_bold"))
                assert bool(surface.dispatchSurfaceAction("text_align_right"))
                assert committed == []
                assert not bool(rendered.property("font").bold())
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [
                    ("node_surface_host_test", "font_weight", "normal"),
                    ("node_surface_host_test", "horizontal_alignment", "right"),
                ]

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_toggle_underline"))
                assert bool(surface.dispatchSurfaceAction("text_toggle_strikeout"))
                assert bool(surface.dispatchSurfaceAction("text_wrap_none"))
                actions_after_draft = variant_list(surface.property("surfaceActions"))
                draft_actions_by_id = {
                    str(action.get("id", "")): action
                    for action in actions_after_draft
                }
                draft_style_actions = variant_list(draft_actions_by_id["text_style_group"].get("popoverActions", []))
                draft_wrap_actions = variant_list(draft_actions_by_id["text_wrap_group"].get("popoverActions", []))
                assert bool(draft_style_actions[2].get("checked", False))
                assert bool(draft_style_actions[3].get("checked", False))
                assert bool(draft_wrap_actions[2].get("checked", False))
                assert committed == []
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [
                    ("node_surface_host_test", "underline", True),
                    ("node_surface_host_test", "strikeout", True),
                    ("node_surface_host_test", "wrap_mode", "none"),
                ]

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_color_recent:#334455"))
                assert rendered.property("color").name().lower() == "#334455"
                assert committed == []
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [("node_surface_host_test", "text_color", "#334455")]

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_toggle_bullet_list"))
                assert str(rendered.property("text") or "") == "- **Markdown** note"
                assert committed == [("node_surface_host_test", "text", "- **Markdown** note")]

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_toggle_numbered_list"))
                assert str(rendered.property("text") or "") == "1. **Markdown** note"
                assert committed == [("node_surface_host_test", "text", "1. **Markdown** note")]

                actions = variant_list(surface.property("surfaceActions"))
                action_ids = [str(action.get("id", "")) for action in actions]
                assert action_ids == [
                    "text_font_size_group",
                    "text_font_family_group",
                    "text_style_group",
                    "text_alignment_group",
                    "text_wrap_group",
                    "text_color_group",
                    "text_copy_style",
                    "text_paste_style",
                ], action_ids
                actions_by_id = {str(action.get("id", "")): action for action in actions}
                font_size_action = actions_by_id["text_font_size_group"]
                assert str(font_size_action.get("popover_layout", "")) == "font_size"
                assert int(font_size_action.get("font_size_value", 0)) == 20
                assert int(font_size_action.get("font_size_min", 0)) == 6
                assert int(font_size_action.get("font_size_max", 0)) == 144
                assert str(font_size_action.get("font_size_set_action_prefix", "")) == "text_font_size_set:"
                assert str(font_size_action.get("font_size_preview_action_prefix", "")) == "text_font_size_preview:"
                font_family_action = actions_by_id["text_font_family_group"]
                assert str(font_family_action.get("popover_layout", "")) == "font_family"
                assert str(font_family_action.get("toolbar_text", "")) == "Default"
                font_family_actions = variant_list(font_family_action.get("popoverActions", []))
                assert str(font_family_actions[0].get("id", "")) == "text_font_family_clear"
                assert str(font_family_actions[0].get("label", "")) == "Default"
                assert bool(font_family_actions[0].get("checked", False)), font_family_actions[0]
                assert len(font_family_actions) > 1, font_family_actions
                assert str(actions_by_id["text_color_group"].get("icon", "")) == "color-picker"
                assert str(actions_by_id["text_copy_style"].get("icon", "")) == "copy-text-style"
                assert str(actions_by_id["text_paste_style"].get("icon", "")) == "paste-text-style"
                color_actions = variant_list(actions_by_id["text_color_group"].get("popoverActions", []))
                assert str(color_actions[0].get("icon", "")) == "color-picker"
                style_actions = variant_list(actions_by_id["text_style_group"].get("popoverActions", []))
                assert [str(action.get("id", "")) for action in style_actions] == [
                    "text_toggle_bold",
                    "text_toggle_italic",
                    "text_toggle_underline",
                    "text_toggle_strikeout",
                    "text_toggle_bullet_list",
                    "text_toggle_numbered_list",
                ]
                assert str(style_actions[4].get("icon", "")) == "format-list-bulleted"
                assert bool(style_actions[5].get("checked", False))
                assert str(style_actions[5].get("icon", "")) == "format-list-numbered"
                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_font_size_preview:32"))
                assert int(rendered.property("font").pixelSize()) == 32
                assert bool(surface.dispatchSurfaceAction("text_font_size_preview:40"))
                assert int(rendered.property("font").pixelSize()) == 40
                assert committed == []
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [("node_surface_host_test", "font_size", 40)]

                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_font_size_set:999"))
                assert committed == [("node_surface_host_test", "font_size", 144)]

                committed.clear()
                current_family = str(surface.property("resolvedFontFamily") or "")
                target_family = next(
                    (
                        str(action.get("font_family") or action.get("label") or "").strip()
                        for action in font_family_actions[1:]
                        if str(action.get("font_family") or action.get("label") or "").strip() != current_family
                    ),
                    str(font_family_actions[1].get("font_family") or font_family_actions[1].get("label") or "").strip(),
                )
                assert bool(surface.dispatchSurfaceAction("text_font_family_set:" + quote(target_family, safe=""))), target_family
                assert str(surface.property("resolvedFontFamily") or "") == target_family, (
                    surface.property("resolvedFontFamily"),
                    target_family,
                )
                assert rendered.property("font").family() == target_family, (
                    rendered.property("font").family(),
                    target_family,
                )
                assert committed == []
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [("node_surface_host_test", "font_family", target_family)]

                refreshed_payload = dict(payload)
                refreshed_payload["properties"] = dict(payload["properties"])
                refreshed_payload["properties"]["font_family"] = target_family
                host.setProperty("nodeData", refreshed_payload)
                settle_events(5)
                committed.clear()
                assert bool(surface.dispatchSurfaceAction("text_font_family_clear")), surface.property("fontFamilyValue")
                assert str(surface.property("resolvedFontFamily") or "")
                QTest.qWait(int(surface.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [("node_surface_host_test", "font_family", "")], committed
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_planning_card_body_uses_reusable_rich_text_block(self) -> None:
        self._run_qml_probe(
            "planning-card-reusable-rich-text-block-host",
            """
            payload = flowchart_payload("decision")
            payload["type_id"] = "passive.planning.task_card"
            payload["display_name"] = "Task Card"
            payload["title"] = "Task"
            payload["surface_family"] = "planning"
            payload["surface_variant"] = "task_card"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="passive.planning.task_card",
                family="planning",
                variant="task_card",
            )
            payload["surface_metrics"] = {
                "default_width": 260.0,
                "default_height": 180.0,
                "min_width": 180.0,
                "min_height": 120.0,
                "body_top": 44.0,
                "body_height": 120.0,
                "body_left_margin": 14.0,
                "body_right_margin": 14.0,
                "body_bottom_margin": 12.0,
                "port_top": 176.0,
                "port_height": 0.0,
                "port_center_offset": 0.0,
                "port_side_margin": 8.0,
                "port_dot_radius": 3.5,
                "resize_handle_size": 16.0,
            }
            payload["width"] = 260.0
            payload["height"] = 180.0
            payload["properties"] = {
                "title": "Task",
                "body": "**Reusable** markdown",
                "body_format": "markdown",
                "status": "todo",
                "owner": "",
                "due_date": "",
            }
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                rich_block = host.findChild(QObject, "graphNodePlanningRichTextBlock")
                rendered = host.findChild(QObject, "graphNodePlanningBodyText")
                editor = host.findChild(QObject, "graphNodePlanningBodyEditorField")
                assert rich_block is not None
                assert rendered is not None
                assert editor is not None
                assert str(rendered.property("text") or "") == "**Reusable** markdown"

                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(rendered))
                settle_events(5)
                assert bool(editor.property("visible"))
                editor.setProperty("text", "Updated **planning**")
                app.processEvents()
                QTest.keyClick(window, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
                settle_events(5)
                assert committed == [("node_surface_host_test", "body", "Updated **planning**")]

                committed.clear()
                assert bool(rich_block.dispatchSurfaceAction("text_toggle_bold"))
                QTest.qWait(int(rich_block.property("styleCommitDelayMs")) + 30)
                settle_events(5)
                assert committed == [("node_surface_host_test", "body_font_weight", "bold")]
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_passive_annotation_text_copy_paste_style_uses_internal_clipboard_and_bulk_commit(self) -> None:
        self._run_qml_probe(
            "annotation-text-copy-paste-style-host",
            """
            class TextStyleClipboardBridge(QObject):
                def __init__(self):
                    super().__init__()
                    self.copied = {}

                @pyqtSlot("QVariantMap", result=bool)
                def copy_text_annotation_style(self, style):
                    self.copied = dict(style or {})
                    return bool(self.copied)

                @pyqtSlot(result="QVariantMap")
                def paste_text_annotation_style(self):
                    return dict(self.copied)

                @pyqtSlot(result=bool)
                def has_text_annotation_style(self):
                    return bool(self.copied)

            class TextStyleCanvasItem(QQuickItem):
                def __init__(self, bridge):
                    super().__init__()
                    self._bridge = bridge
                    self.batch_commits = []

                @pyqtProperty(QObject, constant=True)
                def canvasCommandBridgeRef(self):
                    return self._bridge

                @pyqtSlot(str, "QVariantMap", result=bool)
                def commitNodeSurfaceProperties(self, node_id, properties):
                    self.batch_commits.append((str(node_id), dict(properties or {})))
                    return True

            def text_payload(node_id, properties):
                payload = flowchart_payload("decision")
                payload["node_id"] = node_id
                payload["type_id"] = "passive.annotation.text"
                payload["display_name"] = "Text"
                payload["title"] = "Text"
                payload["surface_family"] = "annotation"
                payload["surface_variant"] = "text"
                payload["surface_spec"] = surface_spec_payload_for_values(
                    type_id="passive.annotation.text",
                    family="annotation",
                    variant="text",
                )
                payload["surface_metrics"] = {
                    "default_width": 240.0,
                    "default_height": 96.0,
                    "min_width": 80.0,
                    "min_height": 32.0,
                    "body_top": 4.0,
                    "body_height": 88.0,
                    "body_left_margin": 4.0,
                    "body_right_margin": 4.0,
                    "body_bottom_margin": 4.0,
                    "port_top": 92.0,
                    "port_height": 0.0,
                    "port_center_offset": 0.0,
                    "port_side_margin": 8.0,
                    "port_dot_radius": 3.5,
                    "resize_handle_size": 16.0,
                    "use_host_chrome": False,
                }
                payload["width"] = 240.0
                payload["height"] = 96.0
                base_properties = {
                    "text": "Text",
                    "format": "markdown",
                    "font_family": "",
                    "font_size": 18,
                    "font_weight": "normal",
                    "italic": False,
                    "underline": False,
                    "strikeout": False,
                    "text_color": "",
                    "background_color": "",
                    "horizontal_alignment": "center",
                    "vertical_alignment": "middle",
                    "wrap_mode": "word",
                    "line_height": 1.2,
                    "letter_spacing": 0.0,
                    "padding": 4,
                    "opacity": 100,
                }
                base_properties.update(properties)
                payload["properties"] = base_properties
                return payload

            bridge = TextStyleClipboardBridge()
            canvas_item = TextStyleCanvasItem(bridge)
            source_payload = text_payload(
                "source_text",
                {
                    "text": "Source content",
                    "font_size": 22,
                    "italic": False,
                    "text_color": "#112233",
                    "horizontal_alignment": "left",
                },
            )
            target_payload = text_payload(
                "target_text",
                {
                    "text": "Target content",
                    "font_size": 11,
                    "italic": False,
                    "text_color": "#445566",
                    "horizontal_alignment": "right",
                },
            )
            source_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": source_payload, "canvasItem": canvas_item},
            )
            target_host = create_component(
                graph_node_host_qml_path,
                {"nodeData": target_payload, "canvasItem": canvas_item},
            )
            source_window = attach_host_to_window(source_host, width=640, height=480)
            target_window = attach_host_to_window(target_host, width=640, height=480)
            try:
                source_surface = source_host.findChild(QObject, "graphBareTextSurface")
                target_surface = target_host.findChild(QObject, "graphBareTextSurface")
                target_rendered = target_host.findChild(QObject, "graphBareTextRenderedText")
                assert source_surface is not None
                assert target_surface is not None
                assert target_rendered is not None

                assert not bool(target_surface.dispatchSurfaceAction("text_paste_style"))
                assert canvas_item.batch_commits == []

                assert bool(source_surface.dispatchSurfaceAction("text_font_size_preview:37"))
                assert bool(source_surface.dispatchSurfaceAction("text_toggle_italic"))
                assert bool(source_surface.dispatchSurfaceAction("text_copy_style"))
                assert bridge.copied["font_size"] == 37
                assert bridge.copied["italic"] is True
                assert bridge.copied["text_color"] == "#112233"
                assert bridge.copied["horizontal_alignment"] == "left"
                assert "text" not in bridge.copied
                assert "format" not in bridge.copied

                assert int(target_rendered.property("font").pixelSize()) == 11
                assert not bool(target_rendered.property("font").italic())
                assert target_rendered.property("color").name().lower() == "#445566"

                assert bool(target_surface.dispatchSurfaceAction("text_paste_style"))
                assert int(target_rendered.property("font").pixelSize()) == 37
                assert bool(target_rendered.property("font").italic())
                assert target_rendered.property("color").name().lower() == "#112233"
                assert canvas_item.batch_commits, canvas_item.batch_commits
                node_id, payload = canvas_item.batch_commits[-1]
                assert node_id == "target_text"
                assert payload["font_size"] == 37
                assert payload["italic"] is True
                assert payload["text_color"] == "#112233"
                assert payload["horizontal_alignment"] == "left"
                assert "text" not in payload
                assert "format" not in payload
            finally:
                dispose_host_window(source_host, source_window)
                dispose_host_window(target_host, target_window)
            """,
        )

    def test_passive_annotation_text_auto_color_and_shadow_suppression(self) -> None:
        self._run_qml_probe(
            "annotation-text-auto-color-shadow-host",
            """
            def canvas_stub(background_variant):
                qml = '''
                import QtQuick 2.15
                Item {
                    property string canvasBackgroundVariant: "__VARIANT__"
                    property var themePalette: ({ "canvas_bg": "#101217" })
                }
                '''.replace("__VARIANT__", background_variant)
                component = QQmlComponent(engine)
                component.setData(qml.encode("utf-8"), QUrl())
                if component.status() != QQmlComponent.Status.Ready:
                    raise AssertionError("\\n".join(error.toString() for error in component.errors()))
                item = component.create()
                if item is None:
                    raise AssertionError("\\n".join(error.toString() for error in component.errors()))
                return item

            def text_payload(background_variant):
                payload = flowchart_payload("decision")
                payload["type_id"] = "passive.annotation.text"
                payload["display_name"] = "Text"
                payload["title"] = "Text"
                payload["surface_family"] = "annotation"
                payload["surface_variant"] = "text"
                payload["surface_spec"] = surface_spec_payload_for_values(
                    type_id="passive.annotation.text",
                    family="annotation",
                    variant="text",
                )
                payload["surface_metrics"] = {
                    "default_width": 240.0,
                    "default_height": 96.0,
                    "min_width": 80.0,
                    "min_height": 32.0,
                    "body_top": 4.0,
                    "body_height": 88.0,
                    "body_left_margin": 4.0,
                    "body_right_margin": 4.0,
                    "body_bottom_margin": 4.0,
                    "port_top": 92.0,
                    "port_height": 0.0,
                    "port_center_offset": 0.0,
                    "port_side_margin": 8.0,
                    "port_dot_radius": 3.5,
                    "resize_handle_size": 16.0,
                    "use_host_chrome": False,
                    "use_host_shadow": False,
                }
                payload["width"] = 240.0
                payload["height"] = 96.0
                payload["properties"] = {
                    "text": "Auto text",
                    "format": "plain",
                    "font_size": 18,
                    "text_color": "",
                    "background_color": "",
                    "horizontal_alignment": "left",
                    "vertical_alignment": "top",
                    "wrap_mode": "word",
                    "padding": 4,
                    "opacity": 100,
                }
                return payload, canvas_stub(background_variant)

            class SelectedSceneBridge(QObject):
                def __init__(self, node_id):
                    super().__init__()
                    self._node_id = str(node_id)

                @pyqtProperty("QVariantMap", constant=True)
                def selected_node_lookup(self):
                    return {self._node_id: True}

            class SelectedCanvasItem(QQuickItem):
                def __init__(self, node_id):
                    super().__init__()
                    self._scene_bridge = SelectedSceneBridge(node_id)

                @pyqtProperty(QObject, constant=True)
                def sceneBridge(self):
                    return self._scene_bridge

                @pyqtProperty(str, constant=True)
                def canvasBackgroundVariant(self):
                    return "dark"

                @pyqtProperty("QVariantMap", constant=True)
                def themePalette(self):
                    return {"canvas_bg": "#101217"}

            for variant, expected_color in (("white", "#000000"), ("dark", "#ffffff")):
                payload, canvas = text_payload(variant)
                host = create_component(
                    graph_node_host_qml_path,
                    {"nodeData": payload, "canvasItem": canvas, "showShadow": True},
                )
                window = attach_host_to_window(host, width=640, height=480)
                try:
                    rendered = host.findChild(QObject, "graphBareTextRenderedText")
                    assert rendered is not None
                    actual_color = rendered.property("color").name().lower()
                    assert actual_color == expected_color, (variant, actual_color, expected_color)
                    assert not bool(host.property("_useHostChrome")), variant
                    assert not bool(host.property("_backgroundShadowVisible")), (
                        variant,
                        host.property("surfaceMetrics"),
                    )
                    assert not bool(host.property("_shadowVisible")), variant
                finally:
                    dispose_host_window(host, window)

            selected_payload, _ = text_payload("dark")
            selected_canvas = SelectedCanvasItem(selected_payload["node_id"])
            selected_host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": selected_payload,
                    "canvasItem": selected_canvas,
                    "showShadow": True,
                },
            )
            selected_window = attach_host_to_window(selected_host, width=640, height=480)
            try:
                background_layer = selected_host.findChild(QObject, "graphNodeChromeBackgroundLayer")
                chrome_item = selected_host.findChild(QObject, "graphNodeChrome")
                selected_halo = selected_host.findChild(QObject, "graphNodeSelectedHalo")
                assert background_layer is not None
                assert chrome_item is not None
                assert selected_halo is not None
                assert bool(selected_host.property("isSelected")), selected_host.property("selectedNodeLookup")
                assert bool(background_layer.property("selectedChromeFreeOutlineOnly"))
                assert not bool(selected_halo.property("visible")), selected_halo.property("visible")
                assert float(selected_halo.property("opacity")) < 0.01, selected_halo.property("opacity")
                assert bool(chrome_item.property("visible")), chrome_item.property("visible")
                assert chrome_item.property("color").alpha() == 0, chrome_item.property("color")
            finally:
                dispose_host_window(selected_host, selected_window)
            """,
        )

    def test_expanded_flowchart_body_text_replaces_visible_header_title_and_double_click_enters_inline_edit(self) -> None:
        self._run_qml_probe(
            "flowchart-body-text-host",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": flowchart_payload("decision")})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                title_item = host.findChild(QObject, "graphNodeTitle")
                title_editor = host.findChild(QObject, "graphNodeTitleEditor")
                body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
                body_editor = host.findChild(QObject, "graphNodeFlowchartBodyEditor")
                body_field = host.findChild(QObject, "graphNodeFlowchartBodyEditorField")
                assert title_item is not None
                assert title_editor is not None
                assert body_text is not None
                assert body_editor is not None
                assert body_field is not None

                events = host_pointer_events(host)
                interactions = []
                host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
                body_point = item_scene_point(body_text)

                assert not bool(title_item.property("visible"))
                assert not bool(title_editor.property("visible"))
                assert str(body_text.property("text") or "") == "Review the decision criteria and route accordingly."
                assert bool(body_text.property("visible"))
                assert not bool(body_editor.property("visible"))

                mouse_click(window, body_point)
                assert events["clicked"] == [("node_surface_host_test", False)]
                assert events["opened"] == []
                assert not bool(body_editor.property("visible"))

                events["clicked"].clear()
                events["opened"].clear()
                events["contexts"].clear()

                mouse_double_click(window, body_point)
                settle_events(5)

                assert not bool(title_editor.property("visible"))
                assert not bool(body_text.property("visible"))
                assert bool(body_editor.property("visible"))
                assert bool(body_field.property("activeFocus"))
                assert str(body_field.property("text") or "") == "Review the decision criteria and route accordingly."
                assert int(body_field.property("cursorPosition")) == len(str(body_field.property("text") or ""))
                assert len(interactions) >= 1
                assert all(node_id == "node_surface_host_test" for node_id in interactions)
                assert events["opened"] == []
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_expanded_flowchart_context_rename_edits_title_not_body(self) -> None:
        self._run_qml_probe(
            "flowchart-context-rename-title-host",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": flowchart_payload(
                        "decision",
                        title="Decision",
                        properties={"title": "Decision", "body": "   "},
                    ),
                },
            )
            window = attach_host_to_window(host, width=640, height=480)
            try:
                title_item = host.findChild(QObject, "graphNodeTitle")
                title_editor = host.findChild(QObject, "graphNodeFlowchartTitleEditor")
                header_title_editor = host.findChild(QObject, "graphNodeTitleEditor")
                body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
                body_editor = host.findChild(QObject, "graphNodeFlowchartBodyEditor")
                body_field = host.findChild(QObject, "graphNodeFlowchartBodyEditorField")
                assert title_item is not None
                assert title_editor is not None
                assert header_title_editor is not None
                assert body_text is not None
                assert body_editor is not None
                assert body_field is not None

                committed = []
                interactions = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )
                host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))

                assert not bool(title_item.property("visible"))
                assert not bool(header_title_editor.property("visible"))
                assert str(body_text.property("text") or "") == "Decision"
                assert bool(body_text.property("visible"))
                assert not bool(title_editor.property("visible"))
                assert bool(host.beginInlineTitleEdit())
                settle_events(5)

                assert not bool(header_title_editor.property("visible"))
                assert not bool(body_text.property("visible"))
                assert not bool(body_editor.property("visible"))
                assert bool(title_editor.property("visible"))
                assert bool(title_editor.property("activeFocus"))
                assert str(title_editor.property("text") or "") == "Decision"
                assert interactions == ["node_surface_host_test"]

                title_editor.setProperty("text", " Approved route ")
                app.processEvents()
                app.sendEvent(
                    title_editor,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    title_editor,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == [("node_surface_host_test", "title", "Approved route")]
                assert not bool(title_editor.property("visible"))
                assert not bool(body_editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_expanded_flowchart_body_text_uses_fallback_chain_and_passive_style_hooks(self) -> None:
        self._run_qml_probe(
            "flowchart-body-fallback-style-host",
            """
            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": flowchart_payload(
                        "decision",
                        title="Archive",
                        properties={"title": "Archive", "body": "   "},
                        visual_style={
                            "text_color": "#204060",
                            "font_size": 17,
                            "font_weight": "bold",
                        },
                    ),
                },
            )
            title_item = host.findChild(QObject, "graphNodeTitle")
            body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
            assert title_item is not None
            assert body_text is not None
            assert not bool(title_item.property("visible"))
            assert bool(body_text.property("visible"))
            assert str(body_text.property("text") or "") == "Archive"
            body_font = body_text.property("font")
            assert body_font.pixelSize() == 17
            assert body_font.bold()
            assert body_text.property("color").name().lower() == "#204060"
            """,
        )

    def test_expanded_flowchart_body_editor_commits_from_external_click_path(self) -> None:
        self._run_qml_probe(
            "flowchart-body-external-click-commit-host",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": flowchart_payload("decision")})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
                body_editor = host.findChild(QObject, "graphNodeFlowchartBodyEditor")
                body_field = host.findChild(QObject, "graphNodeFlowchartBodyEditorField")
                assert body_text is not None
                assert body_editor is not None
                assert body_field is not None

                events = host_pointer_events(host)
                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(body_text))
                settle_events(5)
                assert bool(body_editor.property("visible"))
                assert bool(body_field.property("activeFocus"))

                body_field.setProperty("text", "Approve request\\nNotify requester")
                app.processEvents()

                events["clicked"].clear()
                events["opened"].clear()
                events["contexts"].clear()

                mouse_click(window, host_scene_point(host, 24.0, 6.0))
                settle_events(5)

                assert committed == [("node_surface_host_test", "body", "Approve request\\nNotify requester")]
                assert events["clicked"] == [("node_surface_host_test", False)]
                assert events["opened"] == []
                assert events["contexts"] == []
                assert bool(body_text.property("visible"))
                assert not bool(body_editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_expanded_flowchart_body_editor_cancels_and_closes_on_escape(self) -> None:
        self._run_qml_probe(
            "flowchart-body-escape-cancel-host",
            """
            host = create_component(graph_node_host_qml_path, {"nodeData": flowchart_payload("decision")})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
                body_editor = host.findChild(QObject, "graphNodeFlowchartBodyEditor")
                body_field = host.findChild(QObject, "graphNodeFlowchartBodyEditorField")
                assert body_text is not None
                assert body_editor is not None
                assert body_field is not None

                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(body_text))
                settle_events(5)
                assert bool(body_editor.property("visible"))

                body_field.setProperty("text", "Discard this draft")
                app.processEvents()
                app.sendEvent(
                    body_field,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    body_field,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == []
                assert bool(body_text.property("visible"))
                assert not bool(body_editor.property("visible"))
                assert str(body_field.property("text") or "") == "Review the decision criteria and route accordingly."
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_passive_planning_body_text_double_click_commits_and_cancels_inline_edits(self) -> None:
        self._run_qml_probe(
            "planning-inline-body-edit-host",
            """
            payload = flowchart_payload("decision")
            payload["type_id"] = "passive.planning.decision_card"
            payload["surface_family"] = "planning"
            payload["surface_variant"] = "decision_card"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="passive.planning.decision_card",
                family="planning",
                variant="decision_card",
            )
            payload["width"] = 252.0
            payload["height"] = 180.0
            payload["surface_metrics"].update({
                "default_width": 252.0,
                "default_height": 180.0,
                "min_width": 196.0,
                "min_height": 156.0,
                "body_top": 44.0,
                "body_height": 124.0,
                "body_left_margin": 14.0,
                "body_right_margin": 14.0,
                "body_bottom_margin": 12.0,
                "port_top": 176.0,
            })
            payload["properties"] = {
                "body": "Review the decision criteria and route accordingly.",
                "state": "open",
                "status": "open",
                "outcome": "",
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                body_text = host.findChild(QObject, "graphNodePlanningBodyText")
                body_editor = host.findChild(QObject, "graphNodePlanningBodyEditor")
                body_field = host.findChild(QObject, "graphNodePlanningBodyEditorField")
                assert body_text is not None
                assert body_editor is not None
                assert body_field is not None

                events = host_pointer_events(host)
                interactions = []
                committed = []
                host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                body_point = item_scene_point(body_text)
                mouse_double_click(window, body_point)
                settle_events(5)

                assert bool(body_editor.property("visible"))
                assert bool(body_field.property("activeFocus"))
                assert str(body_field.property("text") or "") == "Review the decision criteria and route accordingly."
                assert len(interactions) >= 1
                assert all(node_id == "node_surface_host_test" for node_id in interactions)
                assert events["opened"] == []

                body_field.setProperty("text", "Approve path A\\nNotify the team")
                app.processEvents()
                events["clicked"].clear()
                events["opened"].clear()
                events["contexts"].clear()

                mouse_click(window, host_scene_point(host, 24.0, 8.0))
                settle_events(5)

                assert committed == [("node_surface_host_test", "body", "Approve path A\\nNotify the team")]
                assert events["opened"] == []
                assert not bool(body_editor.property("visible"))
                assert bool(body_text.property("visible"))

                committed.clear()
                events["clicked"].clear()
                events["opened"].clear()
                events["contexts"].clear()

                mouse_double_click(window, body_point)
                settle_events(5)
                assert bool(body_editor.property("visible"))

                body_field.setProperty("text", "Discard this draft")
                app.processEvents()
                app.sendEvent(
                    body_field,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    body_field,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == []
                assert not bool(body_editor.property("visible"))
                assert bool(body_text.property("visible"))
                assert events["opened"] == []
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_passive_annotation_body_text_double_click_edits_body_and_subtitle_inline(self) -> None:
        self._run_qml_probe(
            "annotation-inline-edit-host",
            """
            def run_annotation_case(
                label,
                payload,
                text_object_name,
                editor_object_name,
                field_object_name,
                key,
                *,
                commit_via_keyboard=False,
            ):
                host = create_component(graph_node_host_qml_path, {"nodeData": payload})
                window = attach_host_to_window(host, width=640, height=480)
                try:
                    text_item = host.findChild(QObject, text_object_name)
                    editor = host.findChild(QObject, editor_object_name)
                    field = host.findChild(QObject, field_object_name)
                    assert text_item is not None, label
                    assert editor is not None, label
                    assert field is not None, label

                    events = host_pointer_events(host)
                    interactions = []
                    committed = []
                    host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
                    host.inlinePropertyCommitted.connect(
                        lambda node_id, committed_key, value: committed.append((node_id, committed_key, variant_value(value)))
                    )

                    text_point = item_scene_point(text_item)
                    mouse_double_click(window, text_point)
                    settle_events(10 if commit_via_keyboard else 5)

                    assert bool(editor.property("visible")), label
                    assert bool(field.property("activeFocus")), label
                    assert len(interactions) >= 1, label
                    assert all(node_id == "node_surface_host_test" for node_id in interactions), label
                    assert events["opened"] == [], label

                    field.setProperty("text", f"Edited {label}")
                    app.processEvents()
                    events["clicked"].clear()
                    events["opened"].clear()
                    events["contexts"].clear()

                    if commit_via_keyboard:
                        app.sendEvent(
                            field,
                            QKeyEvent(
                                QEvent.Type.KeyPress,
                                Qt.Key.Key_Enter,
                                Qt.KeyboardModifier.ControlModifier,
                            ),
                        )
                        app.sendEvent(
                            field,
                            QKeyEvent(
                                QEvent.Type.KeyRelease,
                                Qt.Key.Key_Enter,
                                Qt.KeyboardModifier.ControlModifier,
                            ),
                        )
                    else:
                        mouse_click(window, host_scene_point(host, 24.0, 8.0))
                    settle_events(10 if commit_via_keyboard else 5)

                    assert committed == [("node_surface_host_test", key, f"Edited {label}")], label
                    assert not bool(editor.property("visible")), label
                    assert events["opened"] == [], label
                finally:
                    dispose_host_window(host, window)

            sticky_payload = node_payload(surface_family="annotation", surface_variant="sticky_note")
            sticky_payload["runtime_behavior"] = "passive"
            sticky_payload["type_id"] = "passive.annotation.sticky_note"
            sticky_payload["properties"] = {"body": "Sticky note body"}
            run_annotation_case(
                "sticky-note-body",
                sticky_payload,
                "graphNodeAnnotationBodyText",
                "graphNodeAnnotationBodyEditor",
                "graphNodeAnnotationBodyEditorField",
                "body",
            )

            section_payload = node_payload(surface_family="annotation", surface_variant="section_header")
            section_payload["runtime_behavior"] = "passive"
            section_payload["type_id"] = "passive.annotation.section_header"
            section_payload["properties"] = {"subtitle": "Section subtitle"}
            run_annotation_case(
                "section-header-subtitle",
                section_payload,
                "graphNodeAnnotationSubtitleText",
                "graphNodeAnnotationBodyEditor",
                "graphNodeAnnotationSubtitleEditorField",
                "subtitle",
                commit_via_keyboard=True,
            )
            """,
        )

    def test_passive_planning_empty_body_area_double_click_enters_edit_and_blur_closes_without_commit(self) -> None:
        self._run_qml_probe(
            "planning-empty-body-inline-edit-host",
            """
            payload = flowchart_payload("decision")
            payload["type_id"] = "passive.planning.decision_card"
            payload["surface_family"] = "planning"
            payload["surface_variant"] = "decision_card"
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="passive.planning.decision_card",
                family="planning",
                variant="decision_card",
            )
            payload["width"] = 252.0
            payload["height"] = 180.0
            payload["surface_metrics"].update({
                "default_width": 252.0,
                "default_height": 180.0,
                "min_width": 196.0,
                "min_height": 156.0,
                "body_top": 44.0,
                "body_height": 124.0,
                "body_left_margin": 14.0,
                "body_right_margin": 14.0,
                "body_bottom_margin": 12.0,
                "port_top": 176.0,
            })
            payload["properties"] = {
                "body": "",
                "state": "open",
                "status": "open",
                "outcome": "",
            }

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                rich_block = host.findChild(QObject, "graphNodePlanningRichTextBlock")
                body_editor = host.findChild(QObject, "graphNodePlanningBodyEditor")
                body_field = host.findChild(QObject, "graphNodePlanningBodyEditorField")
                assert rich_block is not None
                assert body_editor is not None
                assert body_field is not None

                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(rich_block))
                settle_events(5)

                assert bool(body_editor.property("visible"))
                assert bool(body_field.property("activeFocus"))
                assert str(body_field.property("text") or "") == ""

                mouse_click(window, host_scene_point(host, 24.0, 8.0))
                settle_events(5)

                assert committed == []
                assert not bool(body_editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_passive_annotation_empty_body_area_double_click_enters_edit_and_blur_closes_without_commit(self) -> None:
        self._run_qml_probe(
            "annotation-empty-body-inline-edit-host",
            """
            payload = node_payload(surface_family="annotation", surface_variant="sticky_note")
            payload["runtime_behavior"] = "passive"
            payload["type_id"] = "passive.annotation.sticky_note"
            payload["properties"] = {"body": ""}

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                rich_block = host.findChild(QObject, "graphNodeAnnotationRichTextBlock")
                body_editor = host.findChild(QObject, "graphNodeAnnotationBodyEditor")
                body_field = host.findChild(QObject, "graphNodeAnnotationBodyEditorField")
                assert rich_block is not None
                assert body_editor is not None
                assert body_field is not None

                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(rich_block))
                settle_events(5)

                assert bool(body_editor.property("visible"))
                assert bool(body_field.property("activeFocus"))
                assert str(body_field.property("text") or "") == ""

                mouse_click(window, host_scene_point(host, 24.0, 8.0))
                settle_events(5)

                assert committed == []
                assert not bool(body_editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_collapsed_flowchart_keeps_compact_header_title_behavior(self) -> None:
        self._run_qml_probe(
            "flowchart-collapsed-title-host",
            """
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": flowchart_payload("decision", title="Archive", collapsed=True)},
            )
            app.processEvents()
            loader = host.findChild(QObject, "graphNodeSurfaceLoader")
            title_item = host.findChild(QObject, "graphNodeTitle")
            editor = host.findChild(QObject, "graphNodeTitleEditor")
            body_text = host.findChild(QObject, "graphNodeFlowchartBodyText")
            metrics = variant_value(host.property("surfaceMetrics"))
            assert loader is not None
            assert title_item is not None
            assert editor is not None
            assert body_text is None
            assert abs(float(host.width()) - float(metrics["collapsed_width"])) < 0.5, (
                float(host.width()),
                metrics,
            )
            assert abs(float(host.height()) - float(metrics["collapsed_height"])) < 0.5, (
                float(host.height()),
                metrics,
            )
            assert float(host.height()) < float(metrics["min_height"]), (float(host.height()), metrics)
            assert not bool(loader.property("surfaceLoaded"))
            assert bool(title_item.property("visible"))
            assert str(title_item.property("text") or "") == "Archive"
            assert not bool(editor.property("visible"))
            """,
        )

    def test_collapsed_standard_node_grows_to_fit_long_header_title(self) -> None:
        self._run_qml_probe(
            "standard-collapsed-long-title-host",
            """
            payload = node_payload()
            payload["title"] = "Reaction Force Probe Result Summary"
            payload["collapsed"] = True

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            app.processEvents()
            title_item = host.findChild(QObject, "graphNodeTitle")
            metrics = variant_value(host.property("surfaceMetrics"))
            assert title_item is not None
            collapsed_width = float(metrics["collapsed_width"])
            # The collapsed standard chip must widen past its fixed collapsed width
            # so the full header title stays readable.
            assert float(host.width()) > collapsed_width + 0.5, (float(host.width()), collapsed_width)
            assert bool(title_item.property("visible"))
            assert str(title_item.property("text") or "") == "Reaction Force Probe Result Summary"
            assert not bool(title_item.property("truncated")), (
                float(host.width()),
                float(title_item.property("contentWidth") or 0.0),
                float(title_item.property("width") or 0.0),
            )
            """,
        )

    def test_collapsed_viewer_grows_to_fit_header_title(self) -> None:
        self._run_qml_probe(
            "viewer-collapsed-title-host",
            """
            payload = node_payload(surface_family="viewer")
            payload["title"] = "Model Viewer"
            payload["collapsed"] = True

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            app.processEvents()
            title_item = host.findChild(QObject, "graphNodeTitle")
            metrics = variant_value(host.property("surfaceMetrics"))
            assert title_item is not None
            assert float(host.width()) > float(metrics["collapsed_width"]) + 0.5, (
                float(host.width()),
                metrics,
            )
            assert not bool(title_item.property("truncated")), (
                float(host.width()),
                float(title_item.property("contentWidth") or 0.0),
                float(title_item.property("width") or 0.0),
            )
            """,
        )

    def test_non_scoped_standard_and_passive_titles_use_shared_header_editor_without_pointer_leaks(self) -> None:
        self._run_qml_probe(
            "shared-header-title-rollout-host",
            """
            def passive_standard_payload():
                payload = node_payload()
                payload["runtime_behavior"] = "passive"
                payload["type_id"] = "passive.standard.note"
                payload["title"] = "Passive Note"
                payload["properties"] = {"title": "Passive Note"}
                payload["visual_style"] = {
                    "fill_color": "#f3f8fd",
                    "border_color": "#6f88a3",
                    "text_color": "#173247",
                    "header_color": "#deebf7",
                }
                return payload

            scenarios = [
                ("standard", node_payload(), "Approved"),
                ("passive", passive_standard_payload(), "Reviewed"),
            ]

            for label, payload, committed_title in scenarios:
                def scenario_check(condition, step):
                    assert condition, f"{label}: {step}"

                host = create_component(graph_node_host_qml_path, {"nodeData": payload})
                window = attach_host_to_window(host, width=640, height=480)
                try:
                    title_item = host.findChild(QObject, "graphNodeTitle")
                    editor = host.findChild(QObject, "graphNodeTitleEditor")
                    scenario_check(title_item is not None, "title item missing")
                    scenario_check(editor is not None, "title editor missing")
                    scenario_check(
                        bool(host.property("sharedHeaderTitleEditable")),
                        "shared header title editing disabled",
                    )

                    events = host_pointer_events(host)
                    interactions = []
                    committed = []
                    host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))
                    host.inlinePropertyCommitted.connect(
                        lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                    )

                    title_point = item_scene_point(title_item)
                    body_point = host_scene_point(
                        host,
                        24.0,
                        44.0,
                    )

                    mouse_click(window, title_point)
                    scenario_check(
                        events["clicked"] == [(payload["node_id"], False)],
                        f"single-click title routed unexpectedly: clicked={events['clicked']!r}",
                    )
                    scenario_check(
                        events["opened"] == [],
                        f"single-click title unexpectedly opened node: opened={events['opened']!r}",
                    )
                    scenario_check(
                        not bool(editor.property("visible")),
                        "single-click title unexpectedly opened editor",
                    )

                    events["clicked"].clear()
                    events["opened"].clear()
                    events["contexts"].clear()

                    mouse_double_click(window, title_point)
                    settle_events(5)
                    scenario_check(bool(editor.property("visible")), "double-click title did not open editor")
                    scenario_check(
                        str(editor.property("selectedText") or "") == "",
                        f"editor selected unexpected title text: {editor.property('selectedText')!r}",
                    )
                    scenario_check(
                        int(editor.property("cursorPosition")) == len(str(payload["title"])),
                        f"cursor positioned incorrectly: cursor={editor.property('cursorPosition')!r}",
                    )
                    scenario_check(
                        interactions == [payload["node_id"]],
                        f"title edit interaction event mismatch: {interactions!r}",
                    )
                    scenario_check(
                        events["opened"] == [],
                        f"double-click title unexpectedly opened node: opened={events['opened']!r}",
                    )

                    editor.setProperty("text", f" {committed_title} ")
                    app.processEvents()
                    app.sendEvent(
                        editor,
                        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                    )
                    app.sendEvent(
                        editor,
                        QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                    )
                    settle_events(5)
                    scenario_check(
                        committed == [(payload["node_id"], "title", committed_title)],
                        f"title commit mismatch: {committed!r}",
                    )
                    scenario_check(not bool(editor.property("visible")), "editor stayed visible after commit")

                    committed.clear()
                    events["clicked"].clear()
                    events["opened"].clear()
                    events["contexts"].clear()

                    mouse_double_click(window, title_point)
                    settle_events(5)
                    scenario_check(bool(editor.property("visible")), "second title double-click did not reopen editor")

                    events["clicked"].clear()
                    events["opened"].clear()
                    events["contexts"].clear()
                    editor_point = item_scene_point(editor)
                    mouse_click(window, editor_point)
                    mouse_double_click(window, editor_point)
                    mouse_click(window, editor_point, Qt.MouseButton.RightButton)
                    settle_events(5)
                    scenario_check(
                        events["clicked"] == [],
                        f"editor click leaked node clicks: {events['clicked']!r}",
                    )
                    scenario_check(
                        events["opened"] == [],
                        f"editor click leaked node opens: {events['opened']!r}",
                    )
                    scenario_check(
                        events["contexts"] == [],
                        f"editor click leaked node context menu: {events['contexts']!r}",
                    )

                    app.sendEvent(
                        editor,
                        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                    )
                    app.sendEvent(
                        editor,
                        QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
                    )
                    settle_events(5)
                    scenario_check(committed == [], f"escape unexpectedly committed title: {committed!r}")
                    scenario_check(not bool(editor.property("visible")), "editor stayed visible after escape")

                    events["clicked"].clear()
                    events["opened"].clear()
                    events["contexts"].clear()
                    mouse_double_click(window, body_point)
                    settle_events(5)
                    scenario_check(
                        events["opened"] == [payload["node_id"]],
                        f"body double-click did not open node: {events['opened']!r}",
                    )
                finally:
                    dispose_host_window(host, window)
            """,
        )

    def test_collapsed_nodes_use_shared_header_editor_for_title_commits(self) -> None:
        self._run_qml_probe(
            "shared-header-title-rollout-collapsed-host",
            """
            payload = node_payload()
            payload["collapsed"] = True

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            window = attach_host_to_window(host, width=640, height=480)
            try:
                title_item = host.findChild(QObject, "graphNodeTitle")
                editor = host.findChild(QObject, "graphNodeTitleEditor")
                assert title_item is not None
                assert editor is not None
                assert bool(host.property("sharedHeaderTitleEditable"))

                committed = []
                events = host_pointer_events(host)
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(title_item))
                settle_events(5)
                assert bool(editor.property("visible"))
                assert events["opened"] == []

                editor.setProperty("text", " Collapsed Logger ")
                app.processEvents()
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == [("node_surface_host_test", "title", "Collapsed Logger")]
                assert not bool(editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

    def test_title_icon_hit_region_opens_shared_header_editor(self) -> None:
        self._run_qml_probe(
            "title-icon-shared-header-editor-host",
            """
            from pathlib import Path

            icon_source = (Path.cwd() / "ea_node_editor" / "assets" / "app_icon" / "corex_app_minimal.svg").as_uri()
            canvas_item = create_surface_canvas_item()
            canvas_item.setProperty("nodeTitleIconPixelSize", 11)

            payload = node_payload()
            payload["icon_source"] = icon_source

            host = create_component(
                graph_node_host_qml_path,
                {
                    "nodeData": payload,
                    "canvasItem": canvas_item,
                },
            )
            window = attach_host_to_window(host, width=640, height=480)
            try:
                title_icon = host.findChild(QObject, "graphNodeTitleIcon")
                title_item = host.findChild(QObject, "graphNodeTitle")
                editor = host.findChild(QObject, "graphNodeTitleEditor")
                assert title_icon is not None
                assert title_item is not None
                assert editor is not None
                assert bool(title_icon.property("visible"))

                events = host_pointer_events(host)
                committed = []
                host.inlinePropertyCommitted.connect(
                    lambda node_id, key, value: committed.append((node_id, key, variant_value(value)))
                )

                mouse_double_click(window, item_scene_point(title_icon))
                settle_events(5)

                assert bool(editor.property("visible"))
                assert events["opened"] == []
                assert events["contexts"] == []
                assert str(editor.property("text") or "") == "Logger"

                editor.setProperty("text", " Icon Logger ")
                app.processEvents()
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                app.sendEvent(
                    editor,
                    QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
                )
                settle_events(5)

                assert committed == [("node_surface_host_test", "title", "Icon Logger")]
                assert not bool(editor.property("visible"))
            finally:
                dispose_host_window(host, window)
            """,
        )

class GraphSurfaceInlineEditorContractTests(GraphSurfaceInputContractTestBase):
    def test_graph_canvas_routes_surface_control_edits_by_explicit_node_id(self) -> None:
        self._run_qml_probe(
            "graph-canvas-surface-control-bridge",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

            class SceneBridgeStub(QObject):
                nodes_changed = pyqtSignal()
                edges_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.select_calls = []
                    self.set_node_property_calls = []
                    self._nodes_model = [node_payload()]
                    self._selected_node_lookup = {}

                @pyqtProperty("QVariantList", notify=nodes_changed)
                def nodes_model(self):
                    return self._nodes_model

                @pyqtProperty("QVariantList", notify=edges_changed)
                def edges_model(self):
                    return []

                @pyqtProperty("QVariantMap", notify=nodes_changed)
                def selected_node_lookup(self):
                    return self._selected_node_lookup

                @pyqtSlot(str)
                @pyqtSlot(str, bool)
                def select_node(self, node_id, additive=False):
                    normalized_node_id = str(node_id or "")
                    self.select_calls.append((normalized_node_id, bool(additive)))
                    self._selected_node_lookup = {normalized_node_id: True} if normalized_node_id else {}
                    self.nodes_changed.emit()

                @pyqtSlot(str, str, "QVariant")
                def set_node_property(self, node_id, key, value):
                    self.set_node_property_calls.append((str(node_id or ""), str(key or ""), variant_value(value)))

                @pyqtSlot(str, str, str)
                def set_node_port_label(self, node_id, port_key, label):
                    pass

                @pyqtSlot(str, str, result=bool)
                def are_port_kinds_compatible(self, _source_kind, _target_kind):
                    return True

                @pyqtSlot(str, str, result=bool)
                def are_data_types_compatible(self, _source_type, _target_type):
                    return True

            class MainWindowBridgeStub(QObject):
                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                def __init__(self):
                    super().__init__()
                    self.set_selected_node_property_calls = []

                @pyqtSlot(str, "QVariant")
                def set_selected_node_property(self, key, value):
                    self.set_selected_node_property_calls.append((str(key or ""), variant_value(value)))

            scene_bridge = SceneBridgeStub()
            window_bridge = MainWindowBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=window_bridge,
                scene_bridge=scene_bridge,
            )
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                },
            )
            def walk_items(item):
                yield item
                for child in item.childItems():
                    yield from walk_items(child)

            node_card = next((item for item in walk_items(canvas) if item.objectName() == "graphNodeCard"), None)
            assert node_card is not None

            canvas.setProperty(
                "pendingConnectionPort",
                {
                    "node_id": "pending-node",
                    "port_key": "result",
                    "direction": "out",
                    "allow_multiple_connections": False,
                    "scene_x": 10.0,
                    "scene_y": 12.0,
                },
            )
            canvas.setProperty(
                "wireDragState",
                {
                    "node_id": "pending-node",
                    "port_key": "result",
                    "source_direction": "out",
                    "start_x": 10.0,
                    "start_y": 12.0,
                    "cursor_x": 20.0,
                    "cursor_y": 30.0,
                    "press_screen_x": 40.0,
                    "press_screen_y": 50.0,
                    "active": True,
                },
            )
            canvas.setProperty(
                "wireDropCandidate",
                {
                    "node_id": "candidate-node",
                    "port_key": "payload",
                    "direction": "in",
                    "scene_x": 20.0,
                    "scene_y": 30.0,
                    "valid_drop": True,
                },
            )
            canvas.setProperty("edgeContextVisible", True)
            canvas.setProperty("nodeContextVisible", True)
            canvas.setProperty("selectedEdgeIds", ["edge-1"])
            app.processEvents()

            node_card.surfaceControlInteractionStarted.emit("node_surface_contract_test")
            app.processEvents()

            assert scene_bridge.select_calls == []
            assert canvas.property("pendingConnectionPort") is None
            assert canvas.property("wireDragState") is None
            assert canvas.property("wireDropCandidate") is None
            assert not bool(canvas.property("edgeContextVisible"))
            assert not bool(canvas.property("nodeContextVisible"))
            assert variant_list(canvas.property("selectedEdgeIds")) == []

            node_card.inlinePropertyCommitted.emit(
                "node_surface_contract_test",
                "message",
                "updated from graph surface",
            )
            app.processEvents()

            assert scene_bridge.set_node_property_calls == [
                ("node_surface_contract_test", "message", "updated from graph surface")
            ]
            assert window_bridge.set_selected_node_property_calls == []
            assert scene_bridge.select_calls == []

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_graph_canvas_routes_non_scoped_shared_header_title_edits_without_body_pointer_regressions(self) -> None:
        self._run_qml_probe(
            "graph-canvas-shared-header-title-editor",
            """
            from PyQt6.QtCore import QObject, QPointF, pyqtProperty, pyqtSignal, pyqtSlot

            class SceneBridgeStub(QObject):
                nodes_changed = pyqtSignal()
                edges_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.select_calls = []
                    self.set_node_property_calls = []
                    self._nodes_model = [node_payload()]
                    self._selected_node_lookup = {}

                @pyqtProperty("QVariantList", notify=nodes_changed)
                def nodes_model(self):
                    return self._nodes_model

                @pyqtProperty("QVariantList", notify=edges_changed)
                def edges_model(self):
                    return []

                @pyqtProperty("QVariantMap", notify=nodes_changed)
                def selected_node_lookup(self):
                    return self._selected_node_lookup

                @pyqtSlot(str)
                @pyqtSlot(str, bool)
                def select_node(self, node_id, additive=False):
                    normalized_node_id = str(node_id or "")
                    self.select_calls.append((normalized_node_id, bool(additive)))
                    self._selected_node_lookup = {normalized_node_id: True} if normalized_node_id else {}
                    self.nodes_changed.emit()

                @pyqtSlot(str, str, "QVariant")
                def set_node_property(self, node_id, key, value):
                    self.set_node_property_calls.append((str(node_id or ""), str(key or ""), variant_value(value)))

                @pyqtSlot(str, str, str)
                def set_node_port_label(self, node_id, port_key, label):
                    pass

                @pyqtSlot(str, str, result=bool)
                def are_port_kinds_compatible(self, _source_kind, _target_kind):
                    return True

                @pyqtSlot(str, str, result=bool)
                def are_data_types_compatible(self, _source_type, _target_type):
                    return True

            class MainWindowBridgeStub(QObject):
                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

            scene_bridge = SceneBridgeStub()
            window_bridge = MainWindowBridgeStub()
            canvas_state_bridge, canvas_command_bridge = build_canvas_bridges(
                shell_bridge=window_bridge,
                scene_bridge=scene_bridge,
            )
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )
            try:
                node_card = next((item for item in walk_items(canvas) if item.objectName() == "graphNodeCard"), None)
                assert node_card is not None
                title_item = node_card.findChild(QObject, "graphNodeTitle")
                editor = node_card.findChild(QObject, "graphNodeTitleEditor")
                assert title_item is not None
                assert editor is not None
                assert bool(node_card.property("sharedHeaderTitleEditable"))

                open_requests = []
                node_card.nodeOpenRequested.connect(lambda node_id: open_requests.append(node_id))

                title_point = title_item.mapToItem(
                    node_card,
                    QPointF(float(title_item.width()) * 0.5, float(title_item.height()) * 0.5),
                )
                body_local_x = float(node_card.property("width")) * 0.5
                body_local_y = float(node_card.property("height")) * 0.78

                assert not node_card.requestInlineTitleEditAt(body_local_x, body_local_y)
                assert not bool(editor.property("visible"))
                assert node_card.requestInlineTitleEditAt(title_point.x(), title_point.y())
                settle_events(5)
                assert bool(editor.property("visible"))
                assert open_requests == []
                assert scene_bridge.select_calls == []

                assert not node_card.commitInlineTitleEditAt(title_point.x(), title_point.y())
                assert bool(editor.property("visible"))

                scene_bridge.set_node_property_calls.clear()
                editor.setProperty("text", " Updated Logger ")
                app.processEvents()
                assert node_card.commitInlineTitleEditAt(body_local_x, body_local_y)
                settle_events(5)

                assert scene_bridge.set_node_property_calls == [
                    ("node_surface_contract_test", "title", "Updated Logger")
                ]
                assert scene_bridge.select_calls == []
                assert not bool(editor.property("visible"))
                assert open_requests == []
            finally:
                canvas.deleteLater()
                app.processEvents()
                engine.deleteLater()
                app.processEvents()
            """,
        )

    def test_graph_canvas_supports_surface_control_edits_via_split_canvas_bridges(self) -> None:
        self._run_qml_probe(
            "graph-canvas-split-bridge-surface-control",
            """
            from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

            class CanvasStateBridgeStub(QObject):
                graphics_preferences_changed = pyqtSignal()
                snap_to_grid_changed = pyqtSignal()
                scene_nodes_changed = pyqtSignal()
                scene_edges_changed = pyqtSignal()
                scene_selection_changed = pyqtSignal()
                view_state_changed = pyqtSignal()

                def __init__(self):
                    super().__init__()
                    self.select_calls = []
                    self.set_node_property_calls = []
                    self._nodes_model = [node_payload()]
                    self._selected_node_lookup = {}
                    self._width = 640.0
                    self._height = 480.0

                @pyqtProperty(bool, constant=True)
                def graphics_minimap_expanded(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_grid(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_show_minimap(self):
                    return True

                @pyqtProperty(bool, constant=True)
                def graphics_node_shadow(self):
                    return True

                @pyqtProperty(int, constant=True)
                def graphics_shadow_strength(self):
                    return 70

                @pyqtProperty(int, constant=True)
                def graphics_shadow_softness(self):
                    return 50

                @pyqtProperty(int, constant=True)
                def graphics_shadow_offset(self):
                    return 4

                @pyqtProperty(bool, constant=True)
                def snap_to_grid_enabled(self):
                    return False

                @pyqtProperty(float, constant=True)
                def snap_grid_size(self):
                    return 20.0

                @pyqtProperty(float, constant=True)
                def center_x(self):
                    return 0.0

                @pyqtProperty(float, constant=True)
                def center_y(self):
                    return 0.0

                @pyqtProperty(float, constant=True)
                def zoom_value(self):
                    return 1.0

                @pyqtProperty("QVariantMap", notify=view_state_changed)
                def visible_scene_rect_payload(self):
                    return {
                        "x": -(self._width * 0.5),
                        "y": -(self._height * 0.5),
                        "width": self._width,
                        "height": self._height,
                    }

                @pyqtProperty("QVariantList", notify=scene_nodes_changed)
                def nodes_model(self):
                    return self._nodes_model

                @pyqtProperty("QVariantList", notify=scene_nodes_changed)
                def minimap_nodes_model(self):
                    return self._nodes_model

                @pyqtProperty("QVariantMap", notify=scene_nodes_changed)
                def workspace_scene_bounds_payload(self):
                    return {
                        "x": 0.0,
                        "y": 0.0,
                        "width": 640.0,
                        "height": 480.0,
                    }

                @pyqtProperty("QVariantList", notify=scene_edges_changed)
                def edges_model(self):
                    return []

                @pyqtProperty("QVariantMap", notify=scene_selection_changed)
                def selected_node_lookup(self):
                    return self._selected_node_lookup

                @pyqtSlot(str, str, result=bool)
                def are_port_kinds_compatible(self, _source_kind, _target_kind):
                    return True

                @pyqtSlot(str, str, result=bool)
                def are_data_types_compatible(self, _source_type, _target_type):
                    return True

            class CanvasCommandBridgeStub(QObject):
                def __init__(self, state_bridge):
                    super().__init__()
                    self._state_bridge = state_bridge

                @pyqtSlot(float, float)
                def set_viewport_size(self, width, height):
                    self._state_bridge._width = float(width)
                    self._state_bridge._height = float(height)
                    self._state_bridge.view_state_changed.emit()

                @pyqtSlot(str)
                @pyqtSlot(str, bool)
                def select_node(self, node_id, additive=False):
                    normalized_node_id = str(node_id or "")
                    self._state_bridge.select_calls.append((normalized_node_id, bool(additive)))
                    self._state_bridge._selected_node_lookup = (
                        {normalized_node_id: True} if normalized_node_id else {}
                    )
                    self._state_bridge.scene_selection_changed.emit()

                @pyqtSlot(str, str, "QVariant")
                def set_node_property(self, node_id, key, value):
                    self._state_bridge.set_node_property_calls.append(
                        (str(node_id or ""), str(key or ""), variant_value(value))
                    )

                @pyqtSlot(str, str, str)
                def set_node_port_label(self, node_id, port_key, label):
                    pass

            canvas_state_bridge = CanvasStateBridgeStub()
            canvas_command_bridge = CanvasCommandBridgeStub(canvas_state_bridge)
            canvas = create_component(
                graph_canvas_qml_path,
                {
                    "canvasStateBridge": canvas_state_bridge,
                    "canvasCommandBridge": canvas_command_bridge,
                    "width": 640.0,
                    "height": 480.0,
                },
            )

            def walk_items(item):
                yield item
                for child in item.childItems():
                    yield from walk_items(child)

            node_card = next((item for item in walk_items(canvas) if item.objectName() == "graphNodeCard"), None)
            assert node_card is not None

            node_card.surfaceControlInteractionStarted.emit("node_surface_contract_test")
            app.processEvents()
            node_card.inlinePropertyCommitted.emit(
                "node_surface_contract_test",
                "message",
                "updated through split bridges",
            )
            app.processEvents()

            assert canvas_state_bridge.select_calls == []
            assert canvas_state_bridge.set_node_property_calls == [
                ("node_surface_contract_test", "message", "updated through split bridges")
            ]

            canvas.deleteLater()
            app.processEvents()
            engine.deleteLater()
            app.processEvents()
            """,
        )
