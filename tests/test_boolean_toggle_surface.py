from __future__ import annotations

from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase


class BooleanToggleSurfaceTests(PassiveGraphSurfaceHostTestBase):
    def test_pill_toggle_renders_and_commits(self) -> None:
        self._run_qml_probe(
            "boolean-toggle-pill",
            """
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

            payload = node_payload(surface_family="standard", surface_variant="boolean_toggle")
            payload["type_id"] = "data.boolean_toggle"
            payload["title"] = "Boolean Toggle"
            payload["display_name"] = "Boolean Toggle"
            payload["category_path"] = ["Data", "Control"]
            payload["help_text"] = "A switch that emits a Boolean value."
            payload["keywords"] = ["boolean", "toggle", "switch"]
            payload["width"] = 280.0
            payload["height"] = 40.0
            payload["surface_spec"] = surface_spec_payload_for_values(
                type_id="data.boolean_toggle",
                family="standard",
                variant="boolean_toggle",
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
            payload["properties"] = {"value": False}
            payload["ports"] = [{
                "key": "boolean",
                "label": "Boolean",
                "direction": "out",
                "kind": "data",
                "data_type": "bool",
                "data_access": "tree",
                "connected": False,
            }]
            payload["inline_properties"] = []

            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = wait_for_surface(host, "graphBooleanToggleSurface")
            toggle = named_item(host, "graphBooleanToggleControl")
            output_dot = named_item(host, "graphNodeOutputPortDot")
            output_label = named_item(host, "graphNodeOutputPortLabel")
            header = named_item(host, "graphNodeHeaderLayer")
            help_tooltip = wait_for_named_object(host, "graphBooleanToggleHelpToolTip")

            assert bool(host.property("isBooleanToggleSurface"))
            assert bool(host.property("isCompactPillSurface"))
            assert not bool(header.property("headerTitleVisible"))
            assert not bool(output_label.property("visible"))
            assert float(host.property("resolvedCornerRadius")) == 20.0
            assert str(named_item(host, "graphBooleanToggleNameLabel").property("text")) == "Boolean Toggle"
            name_section = named_item(host, "graphBooleanToggleNameSection")
            name_section_fill_clip = named_item(host, "graphBooleanToggleNameSectionFillClip")
            name_section_fill = named_item(host, "graphBooleanToggleNameSectionFill")
            assert bool(name_section_fill_clip.property("clip"))
            expected_extension = float(host.property("resolvedCornerRadius")) - 1.0
            actual_extension = float(name_section_fill.width()) - float(name_section.width())
            assert abs(actual_extension - expected_extension) < 0.01
            assert not bool(toggle.property("checked"))
            assert float(toggle.width()) == 64.0
            assert float(toggle.height()) == 24.0
            assert float(toggle.property("switchTrackWidth")) == 40.0
            assert float(toggle.property("switchTrackHeight")) == 20.0
            assert variant_list(surface.property("embeddedInteractiveRects"))
            expected_help = (
                '<b>Boolean Toggle</b><br>'
                '<font color="#95a0b8">Data, Control</font><br>'
                'A switch that emits a Boolean value.<br><br>'
                'Keywords: boolean, toggle, switch.'
            )
            assert str(host.property("nodeHelpTooltipText")) == expected_help
            assert str(help_tooltip.property("text")) == expected_help
            assert int(help_tooltip.property("textFormat")) == 1

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
            QTest.mouseMove(window, item_scene_point(named_item(host, "graphBooleanToggleNameLabel")))
            QTest.qWait(450)
            settle_events(5)
            assert bool(help_tooltip.property("managedVisible"))
            assert bool(help_tooltip.property("visible"))
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                item_scene_point(toggle),
            )
            settle_events(4)
            assert commits == [("node_surface_host_test", "value", True)]
            assert str(toggle.property("text")) == "On"

            dispose_host_window(host, window)

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            workspace_id = model.active_workspace.workspace_id
            scene.set_workspace(model, registry, workspace_id)
            long_title = "Boolean Toggle With A Long Descriptive Custom Name"
            long_node_id = scene.add_node_from_type("data.boolean_toggle", 120.0, 80.0)
            scene.set_node_title(long_node_id, long_title)
            long_payload = next(
                item for item in scene.nodes_model if item["node_id"] == long_node_id
            )
            long_host = create_component(graph_node_host_qml_path, {"nodeData": long_payload})
            wait_for_surface(long_host, "graphBooleanToggleSurface")
            long_label = named_item(long_host, "graphBooleanToggleNameLabel")
            long_section = named_item(long_host, "graphBooleanToggleNameSection")
            long_toggle = named_item(long_host, "graphBooleanToggleControl")
            settle_events(4)
            assert float(long_label.width()) >= float(long_label.property("implicitWidth")), (
                long_label.width(), long_label.property("implicitWidth")
            )
            assert float(long_section.x()) + float(long_section.width()) < float(long_toggle.x()), (
                long_section.x(), long_section.width(), long_toggle.x()
            )
            assert abs(
                float(long_section.width())
                - max(float(long_label.property("implicitWidth")) + 26.0, 82.0)
            ) < 0.01
            long_host.deleteLater()
            scene.deleteLater()

            engine.deleteLater()
            app.processEvents()
            """,
        )
