from __future__ import annotations

from tests.graph_surface.environment import (
    PassiveGraphSurfaceHostTestBase,
)


class COREXNodeControlsVisualTests(PassiveGraphSurfaceHostTestBase):
    def test_signal_plot_visual_reference_matrix(self) -> None:
        self._run_qml_probe(
            "signal-plot-visual-reference-matrix",
            r"""
            import importlib.util
            from dataclasses import replace
            from pathlib import Path

            from PyQt6.QtCore import QObject
            from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontInfo
            from PyQt6.QtQuick import QQuickWindow

            from ea_node_editor.nodes.node_specs import (
                PortSpec,
                SettingsGroupItemSpec,
            )
            from ea_node_editor.nodes.execution_context import NodeResult
            from ea_node_editor.runtime_contracts import (
                INTEGER_DATA_TYPE_ID,
                Interval1D,
            )
            from ea_node_editor.ui_qml.graph_scene_payload.builder import (
                GraphScenePayloadBuilder,
            )
            from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
            from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

            example_path = (
                repo_root
                / "tests"
                / "fixtures"
                / "node_controls"
                / "signal_plot_style_node_controls.py"
            )
            example_spec = importlib.util.spec_from_file_location(
                "p08_signal_plot_style_controls",
                example_path,
            )
            assert example_spec is not None and example_spec.loader is not None
            example = importlib.util.module_from_spec(example_spec)
            example_spec.loader.exec_module(example)

            arial_path = Path("C:/Windows/Fonts/arial.ttf")
            assert arial_path.is_file(), arial_path
            font_id = QFontDatabase.addApplicationFont(str(arial_path))
            assert font_id >= 0
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            assert font_families
            app.setFont(QFont(font_families[0]))
            assert QFontInfo(app.font()).family() == "Arial"

            base_spec = example.SignalPlotStyleControlsNode().spec()
            base_display_group = base_spec.settings_groups[1]
            fixture_spec = replace(
                base_spec,
                type_id="tests.p08_signal_plot_style_controls",
                display_name="Signal Plot Controls",
                icon="core/data_object.svg",
                show_title_icon=True,
                ports=base_spec.ports
                + (
                    PortSpec(
                        "number_of_sectors",
                        "in",
                        "data",
                        INTEGER_DATA_TYPE_ID,
                        label="Number of sectors",
                        required=False,
                        uses_property_default=True,
                        description="Optional upstream sector count.",
                    ),
                ),
                settings_groups=(
                    base_spec.settings_groups[0],
                    replace(
                        base_display_group,
                        items=(
                            base_display_group.items[0],
                            SettingsGroupItemSpec(
                                port_key="number_of_sectors",
                                property_key="number_of_sectors",
                            ),
                            *base_display_group.items[2:],
                        ),
                    ),
                ),
            )
            decreasing_spec = replace(
                fixture_spec,
                type_id="tests.p08_signal_plot_style_controls_decreasing",
                properties=tuple(
                    replace(
                        property_spec,
                        default=Interval1D(120.0, -80.0),
                        interval_direction="decreasing",
                    )
                    if property_spec.key == "result_bound"
                    else property_spec
                    for property_spec in fixture_spec.properties
                ),
            )

            class P08SignalPlotFixtureNode:
                def spec(self):
                    return fixture_spec

                def execute(self, _ctx):
                    return NodeResult()

            class P08SignalPlotDecreasingFixtureNode:
                def spec(self):
                    return decreasing_spec

                def execute(self, _ctx):
                    return NodeResult()

            class TypographyHost(QObject):
                def __init__(self, pixel_size):
                    super().__init__()
                    self.graphics_graph_label_pixel_size = int(pixel_size)
                    self.graphics_node_title_icon_pixel_size = int(pixel_size)

            def property_item(host, object_name, key):
                return named_item(host, object_name, key)

            def visual_width(host, item):
                left = item.mapToItem(host, QPointF(0.0, 0.0)).x()
                right = item.mapToItem(
                    host,
                    QPointF(float(item.width()), 0.0),
                ).x()
                return round(abs(right - left), 2)

            def assert_inside(host, item, label):
                if not bool(item.property("visible")):
                    return
                top_left = item.mapToItem(host, QPointF(0.0, 0.0))
                bottom_right = item.mapToItem(
                    host,
                    QPointF(float(item.width()), float(item.height())),
                )
                assert top_left.x() >= -1.25, (label, top_left.x())
                assert top_left.y() >= -1.25, (label, top_left.y())
                assert bottom_right.x() <= float(host.width()) + 1.25, (
                    label,
                    bottom_right.x(),
                    host.width(),
                )
                assert bottom_right.y() <= float(host.height()) + 1.25, (
                    label,
                    bottom_right.y(),
                    host.height(),
                )
                assert not bool(item.property("truncated")), (
                    label, item.property("text"), item.width(),
                    item.property("contentWidth"), host.width(),
                )

            def mutate_wired_presentation(payload, *, settled):
                ports = {port["key"]: port for port in payload["ports"]}
                signal = ports["signal_name"]["default_property"]
                interval = ports["result_bound"]["default_property"]
                if settled:
                    signal["display_value"] = "Upstream pressure"
                    signal["display_value_available"] = True
                    interval["display_value"] = {"start": 150.0, "end": -75.0}
                    interval["display_value_available"] = True
                else:
                    signal["display_value"] = None
                    signal["display_value_available"] = False
                    interval["display_value"] = None
                    interval["display_value_available"] = False
                for property_data in (signal, interval):
                    property_data["overridden_by_input"] = True
                    property_data["editor_enabled"] = False
                    property_data["editor_disabled_reason"] = (
                        "Value supplied by connected input."
                    )

            evidence_dir = (
                repo_root
                / "artifacts"
                / "verification_logs"
                / "corex_style_node_controls_p08"
            )
            evidence_dir.mkdir(parents=True, exist_ok=True)
            edge_layer_qml_path = (
                components_dir / "graph" / "EdgeLayer.qml"
            )
            captures = []

            for theme_name, pixel_size in (
                ("dark", 10),
                ("dark", 16),
                ("light", 10),
                ("light", 16),
            ):
                shell_theme_id = f"stitch_{theme_name}"
                typography_host = TypographyHost(pixel_size)
                active_theme_bridge = ThemeBridge(theme_id=shell_theme_id)
                active_graph_theme_bridge = GraphThemeBridge(
                    typography_host,
                    theme_id=shell_theme_id,
                )
                active_shell_context = ShellContextStub(
                    active_theme_bridge,
                    active_graph_theme_bridge,
                )
                engine.rootContext().setContextProperty(
                    "themeBridge",
                    active_theme_bridge,
                )
                engine.rootContext().setContextProperty(
                    "graphThemeBridge",
                    active_graph_theme_bridge,
                )
                engine.rootContext().setContextProperty(
                    "shellContext",
                    active_shell_context,
                )

                registry = build_default_registry()
                registry.register(P08SignalPlotFixtureNode)
                registry.register(P08SignalPlotDecreasingFixtureNode)
                model = GraphModel()
                workspace = model.active_workspace

                def add_controls(
                    type_id,
                    title,
                    x,
                    y,
                    *,
                    expanded,
                    properties=None,
                ):
                    node = model.add_node(
                        workspace.workspace_id,
                        type_id,
                        title,
                        float(x),
                        float(y),
                        properties=dict(properties or {}),
                    )
                    node.expanded_settings_group_ids = tuple(expanded)
                    model.set_node_size(
                        workspace.workspace_id,
                        node.node_id,
                        400.0,
                        None,
                    )
                    return node

                overview = add_controls(
                    fixture_spec.type_id,
                    "Overview: expanded + collapsed",
                    40,
                    40,
                    expanded=("signal",),
                )
                local = add_controls(
                    decreasing_spec.type_id,
                    "Local editable: decreasing",
                    500,
                    40,
                    expanded=("signal", "display"),
                    properties={
                        "cyclic_symmetry_mode": "Manual",
                        "result_bound": Interval1D(120.0, -80.0),
                    },
                )
                settled_source = model.add_node(
                    workspace.workspace_id,
                    "core.python_script",
                    "Settled upstream",
                    930.0,
                    170.0,
                )
                settled = add_controls(
                    fixture_spec.type_id,
                    "Wired: settled upstream",
                    1300,
                    40,
                    expanded=("signal", "display"),
                    properties={"cyclic_symmetry_mode": "Manual"},
                )
                disabled = add_controls(
                    fixture_spec.type_id,
                    "Condition: disabled",
                    40,
                    700,
                    expanded=("display",),
                    properties={
                        "cyclic_symmetry_mode": "None",
                        "result_bound": Interval1D(25.0, 25.0),
                    },
                )
                enabled = add_controls(
                    fixture_spec.type_id,
                    "Condition: re-enabled",
                    500,
                    700,
                    expanded=("display",),
                    properties={
                        "cyclic_symmetry_mode": "Manual",
                        "result_bound": Interval1D(0.0, 100.0),
                    },
                )
                unavailable_source = model.add_node(
                    workspace.workspace_id,
                    "core.python_script",
                    "Unavailable upstream",
                    930.0,
                    830.0,
                )
                unavailable = add_controls(
                    fixture_spec.type_id,
                    "Wired: unavailable upstream",
                    1300,
                    700,
                    expanded=("signal", "display"),
                    properties={"cyclic_symmetry_mode": "Manual"},
                )

                for source, target in (
                    (settled_source, settled),
                    (unavailable_source, unavailable),
                ):
                    model.add_edge(
                        workspace.workspace_id,
                        source.node_id,
                        "result",
                        target.node_id,
                        "signal_name",
                    )
                    model.add_edge(
                        workspace.workspace_id,
                        source.node_id,
                        "result",
                        target.node_id,
                        "result_bound",
                    )

                node_payloads, _backdrops, _minimap, edge_payloads = (
                    GraphScenePayloadBuilder().rebuild_partitioned_models(
                        model=model,
                        registry=registry,
                        workspace_id=workspace.workspace_id,
                        scope_path=(),
                        graph_theme_bridge=active_graph_theme_bridge,
                        graph_label_pixel_size=pixel_size,
                        graph_node_icon_pixel_size=pixel_size,
                    )
                )
                payload_by_id = {
                    payload["node_id"]: payload for payload in node_payloads
                }
                mutate_wired_presentation(
                    payload_by_id[settled.node_id],
                    settled=True,
                )
                mutate_wired_presentation(
                    payload_by_id[unavailable.node_id],
                    settled=False,
                )

                window_width = 1900
                window_height = 1900
                window = QQuickWindow()
                window.resize(window_width, window_height)
                window.setColor(QColor(active_theme_bridge.palette["canvas_bg"]))
                viewport = ViewportBridge()
                viewport.set_viewport_size(
                    float(window_width),
                    float(window_height),
                )
                viewport.centerOn(
                    float(window_width) * 0.5,
                    float(window_height) * 0.5,
                )

                edge_layer = create_component(
                    edge_layer_qml_path,
                    {
                        "edges": edge_payloads,
                        "nodes": node_payloads,
                        "viewBridge": viewport,
                        "edgeRendererPreference": "canvas",
                        "visibleSceneRectPayload": {
                            "x": 0.0,
                            "y": 0.0,
                            "width": float(window_width),
                            "height": float(window_height),
                        },
                        "width": float(window_width),
                        "height": float(window_height),
                    },
                )
                edge_layer.setParentItem(window.contentItem())

                hosts = {}
                for payload in node_payloads:
                    host = create_component(
                        graph_node_host_qml_path,
                        {
                            "nodeData": payload,
                            "graphLabelPixelSize": pixel_size,
                        },
                    )
                    host.setParentItem(window.contentItem())
                    hosts[payload["node_id"]] = host

                window.show()
                settle_events(12)

                capture_margin = 60
                window_width = int(
                    max(float(host.x()) + float(host.width()) for host in hosts.values())
                    + capture_margin
                )
                window_height = int(
                    max(float(host.y()) + float(host.height()) for host in hosts.values())
                    + capture_margin
                )
                window.resize(window_width, window_height)
                viewport.set_viewport_size(
                    float(window_width),
                    float(window_height),
                )
                viewport.centerOn(
                    float(window_width) * 0.5,
                    float(window_height) * 0.5,
                )
                edge_layer.setProperty("width", float(window_width))
                edge_layer.setProperty("height", float(window_height))
                edge_layer.setProperty(
                    "visibleSceneRectPayload",
                    {
                        "x": 0.0,
                        "y": 0.0,
                        "width": float(window_width),
                        "height": float(window_height),
                    },
                )
                assert edge_layer.requestImmediateRedraw()
                settle_events(12)

                overview_host = hosts[overview.node_id]
                local_host = hosts[local.node_id]
                settled_host = hosts[settled.node_id]
                disabled_host = hosts[disabled.node_id]
                enabled_host = hosts[enabled.node_id]
                unavailable_host = hosts[unavailable.node_id]

                assert len(
                    named_child_items(
                        overview_host,
                        "graphNodeSettingsGroupHeader",
                    )
                ) == 2
                assert len(
                    [
                        item
                        for item in named_child_items(
                            overview_host,
                            "graphNodeSettingsGroupAggregateSocket",
                        )
                        if bool(item.property("visible"))
                    ]
                ) == 1

                ordinary_enum = property_item(
                    local_host,
                    "graphNodeInlineEnumEditor",
                    "cyclic_symmetry_mode",
                )
                searchable_enum = property_item(
                    local_host,
                    "graphNodeInlineSearchableEnumEditor",
                    "color_map",
                )
                local_scalar = property_item(
                    local_host,
                    "graphNodeInlineSliderEditor",
                    "sample_rate_hz",
                )
                local_interval = property_item(
                    local_host,
                    "graphNodeInlineIntervalSliderEditor",
                    "result_bound",
                )
                local_text = property_item(
                    local_host,
                    "graphNodeInlineValueEditor",
                    "signal_name",
                )
                assert all(
                    bool(item.property("visible"))
                    for item in (
                        ordinary_enum,
                        searchable_enum,
                        local_scalar,
                        local_interval,
                        local_text,
                    )
                )
                assert all(
                    bool(item.property("enabled"))
                    for item in (
                        ordinary_enum,
                        searchable_enum,
                        local_scalar,
                        local_interval,
                        local_text,
                    )
                )
                widths = {
                    "ordinary_enum": visual_width(local_host, ordinary_enum),
                    "searchable_enum": visual_width(
                        local_host,
                        searchable_enum,
                    ),
                    "scalar": visual_width(local_host, local_scalar),
                    "interval": visual_width(local_host, local_interval),
                    "text": visual_width(local_host, local_text),
                }
                assert max(widths.values()) - min(widths.values()) < 0.75, widths
                assert (
                    str(local_interval.property("intervalDirection"))
                    == "decreasing"
                )
                assert bool(local_interval.property("activeFocusOnTab"))
                local_interval.forceActiveFocus()
                settle_events(3)
                assert bool(local_interval.property("activeFocus"))

                settled_text = property_item(
                    settled_host,
                    "graphNodeInlineValueEditor",
                    "signal_name",
                )
                settled_interval = property_item(
                    settled_host,
                    "graphNodeInlineIntervalSliderEditor",
                    "result_bound",
                )
                assert str(settled_text.property("text")) == "Upstream pressure"
                assert not bool(settled_text.property("enabled"))
                assert not bool(settled_interval.property("enabled"))
                assert float(settled_interval.property("semanticStart")) == 150.0
                assert float(settled_interval.property("semanticEnd")) == -75.0

                unavailable_text = property_item(
                    unavailable_host,
                    "graphNodeInlineValueEditor",
                    "signal_name",
                )
                unavailable_interval = property_item(
                    unavailable_host,
                    "graphNodeInlineIntervalSliderEditor",
                    "result_bound",
                )
                assert str(unavailable_text.property("text")) == "\u2014"
                assert not bool(unavailable_text.property("enabled"))
                assert not bool(
                    unavailable_interval.property("displayValueAvailable")
                )
                assert not bool(unavailable_interval.property("enabled"))

                disabled_sectors = property_item(
                    disabled_host,
                    "graphNodeInlineSliderEditor",
                    "number_of_sectors",
                )
                enabled_sectors = property_item(
                    enabled_host,
                    "graphNodeInlineSliderEditor",
                    "number_of_sectors",
                )
                disabled_grip = property_item(
                    disabled_host,
                    "graphNodeInputPortDot",
                    "number_of_sectors",
                )
                enabled_grip = property_item(
                    enabled_host,
                    "graphNodeInputPortDot",
                    "number_of_sectors",
                )
                assert not bool(disabled_sectors.property("enabled"))
                assert bool(enabled_sectors.property("enabled"))
                assert bool(disabled_grip.property("visible"))
                assert bool(enabled_grip.property("visible"))
                assert abs(
                    disabled_sectors.mapToItem(
                        disabled_host,
                        QPointF(0.0, 0.0),
                    ).y()
                    - enabled_sectors.mapToItem(
                        enabled_host,
                        QPointF(0.0, 0.0),
                    ).y()
                ) < 0.75
                assert abs(
                    float(disabled_host.height())
                    - float(enabled_host.height())
                ) < 0.75

                equal_interval = property_item(
                    disabled_host,
                    "graphNodeInlineIntervalSliderEditor",
                    "result_bound",
                )
                equal_handles = (
                    named_item(
                        equal_interval,
                        "graphSurfaceIntervalFirstHandle",
                    ),
                    named_item(
                        equal_interval,
                        "graphSurfaceIntervalSecondHandle",
                    ),
                )
                handle_centers = [
                    handle.mapToItem(
                        equal_interval,
                        QPointF(
                            float(handle.width()) * 0.5,
                            float(handle.height()) * 0.5,
                        ),
                    ).x()
                    for handle in equal_handles
                ]
                assert abs(handle_centers[1] - handle_centers[0]) >= 3.0

                assert int(edge_layer.property("profileVisibleEdgeCount")) >= 4
                assert len(
                    named_child_items(
                        settled_host,
                        "graphNodeInputPortDot",
                    )
                ) >= 3
                assert bool(
                    named_item(
                        local_host,
                        "graphNodeTitleIcon",
                    ).property("visible")
                )

                for host in (
                    overview_host,
                    local_host,
                    settled_host,
                    disabled_host,
                    enabled_host,
                    unavailable_host,
                ):
                    for object_name in (
                        "graphNodeTitle",
                        "graphNodeSettingsGroupLabel",
                        "graphNodeSettingsGroupChevron",
                        "graphNodeInlinePropertyLabel",
                        "graphSurfaceSliderMinimumCaption",
                        "graphSurfaceSliderCurrentCaption",
                        "graphSurfaceSliderMaximumCaption",
                        "graphSurfaceIntervalFirstHandle",
                        "graphSurfaceIntervalSecondHandle",
                        "graphSurfaceIntervalLeftCaption",
                        "graphSurfaceIntervalRightCaption",
                    ):
                        for item in named_child_items(host, object_name):
                            assert_inside(
                                host,
                                item,
                                (
                                    f"{theme_name}/{pixel_size}/"
                                    f"{host.property('nodeId')}/{object_name}"
                                ),
                            )

                output_path = evidence_dir / (
                    f"signal_plot_matrix_{theme_name}_font_{pixel_size}.png"
                )
                image = window.grabWindow()
                assert not image.isNull()
                assert image.save(str(output_path)), output_path
                assert output_path.is_file() and output_path.stat().st_size > 0
                captures.append(output_path)

                window.close()
                for host in hosts.values():
                    host.setParentItem(None)
                    host.deleteLater()
                edge_layer.setParentItem(None)
                edge_layer.deleteLater()
                window.deleteLater()
                settle_events(5)

            assert len(captures) == 4
            engine.deleteLater()
            app.processEvents()
            """,
        )
