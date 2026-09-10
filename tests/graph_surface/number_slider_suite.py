from __future__ import annotations

import textwrap

from PyQt6.QtCore import QObject
from PyQt6.QtQml import QQmlComponent, QQmlEngine

from tests.graph_surface.environment import *  # noqa: F403

# Indented to match the probe bodies so textwrap.dedent() inside run_qml_probe
# strips one consistent prefix across helper + body.
_NUMBER_SLIDER_PAYLOAD_HELPER = textwrap.indent(
    """
def number_slider_payload(properties=None, title="Number Slider"):
    payload = node_payload(surface_family="standard", surface_variant="number_slider")
    payload["type_id"] = "data.number_slider"
    payload["title"] = title
    payload["display_name"] = "Number Slider"
    payload["category_path"] = ["Data", "Control"]
    payload["help_text"] = "Select a numeric value within a configured range."
    payload["keywords"] = ["number", "slider", "range"]
    payload["width"] = 280.0
    payload["height"] = 40.0
    payload["surface_spec"] = surface_spec_payload_for_values(
        type_id="data.number_slider",
        family="standard",
        variant="number_slider",
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
        "title_top": 0.0,
        "title_height": 0.0,
        "use_host_chrome": True,
        "use_host_shadow": True,
    }
    payload["properties"] = {
        "value": 0.5,
        "minimum": 0.0,
        "maximum": 1.0,
        "rounding": "decimal",
        "decimals": 3,
    }
    if properties:
        payload["properties"].update(properties)
    payload["ports"] = [
        {
            "key": "value",
            "label": "value",
            "direction": "out",
            "kind": "data",
            "data_type": "float",
            "connected": False,
        },
    ]
    payload["inline_properties"] = []
    return payload

def wait_for_surface(host, object_name, attempts=200):
    for _attempt in range(attempts):
        settle_events(2)
        for child in walk_items(host):
            if child.objectName() == object_name:
                return child
    raise AssertionError(f"surface item {object_name!r} never loaded")
""",
    " " * 12,
)


def test_number_slider_settings_popover_qml_uses_shared_dialog(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    qml_path = (
        _REPO_ROOT  # noqa: F405
        / "ea_node_editor/ui_qml/components/graph/passive/GraphNumberSliderSettingsPopover.qml"
    )
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path)))  # noqa: F405
    assert component.status() == QQmlComponent.Status.Ready, [
        error.toString() for error in component.errors()
    ]
    popover = component.createWithInitialProperties(
        {
            "themePalette": {
                "panel_bg": "#1b1d22",
                "panel_alt_bg": "#24262c",
                "panel_title_fg": "#f0f4fb",
                "muted_fg": "#d0d5de",
                "border": "#3a3d45",
                "input_bg": "#22242a",
                "input_border": "#4a4f5a",
                "input_fg": "#f0f2f5",
                "accent": "#60cdff",
                "accent_strong": "#1d8ce0",
                "tab_selected_fg": "#f2f4f8",
            }
        }
    )
    assert popover is not None
    qapp.processEvents()

    digits = popover.findChild(QObject, "graphNumberSliderSettingsDecimalsField")
    cancel = popover.findChild(QObject, "graphNumberSliderSettingsCancelButton")
    accept = popover.findChild(QObject, "graphNumberSliderSettingsAcceptButton")
    assert digits is not None
    assert cancel is not None
    assert accept is not None
    assert float(popover.property("implicitWidth")) == 400.0
    assert float(cancel.property("width")) == float(accept.property("width"))

    popover.setProperty("roundingDraft", "integer")
    qapp.processEvents()
    assert bool(digits.property("enabled")) is False

    popover.deleteLater()
    engine.deleteLater()
    qapp.processEvents()


class PassiveNumberSliderSurfaceTests(PassiveGraphSurfaceHostTestBase):  # noqa: F405
    def test_pill_surface_renders_row_and_suppresses_standard_header(self) -> None:
        self._run_qml_probe(
            "number-slider-pill-surface-render",
            _NUMBER_SLIDER_PAYLOAD_HELPER
            + """
            payload = number_slider_payload()
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "showShadow": True},
            )
            surface = wait_for_surface(host, "graphNumberSliderSurface")

            assert bool(host.property("isNumberSliderSurface")) is True

            # Chrome owns the pill body: shadow, state borders, and port
            # notches must stay available (regression: both were lost when the
            # surface drew its own background with chrome disabled).
            chrome_flags = {
                "use_host_chrome": bool(host.property("_useHostChrome")),
                "notched_ports": bool(host.property("_notchedPortsEffective")),
                "background_shadow": bool(host.property("_backgroundShadowVisible")),
                "show_shadow": bool(host.property("showShadow")),
                "port_layer_active": bool(host.property("portLayerActive")),
            }
            assert all(
                chrome_flags[key] for key in ("use_host_chrome", "notched_ports", "background_shadow")
            ), f"pill chrome contract broken: {chrome_flags}"

            header_layer = named_item(host, "graphNodeHeaderLayer")
            assert bool(header_layer.property("headerTitleVisible")) is False

            name_label = named_item(host, "graphNumberSliderNameLabel")
            assert str(name_label.property("text")) == "Number Slider"
            name_section = named_item(host, "graphNumberSliderNameSection")
            name_section_fill_clip = named_item(host, "graphNumberSliderNameSectionFillClip")
            name_section_fill = named_item(host, "graphNumberSliderNameSectionFill")
            assert bool(name_section_fill_clip.property("clip"))
            expected_extension = float(host.property("resolvedCornerRadius")) - 1.0
            actual_extension = float(name_section_fill.width()) - float(name_section.width())
            assert abs(actual_extension - expected_extension) < 0.01

            help_tooltip = host.findChild(QObject, "graphNumberSliderHelpToolTip")
            assert help_tooltip is not None
            expected_help = (
                '<b>Number Slider</b><br>'
                '<font color="#95a0b8">Data, Control</font><br>'
                'Select a numeric value within a configured range.<br><br>'
                'Keywords: number, slider, range.'
            )
            actual_help = str(host.property("nodeHelpTooltipText"))
            assert actual_help == expected_help
            assert str(help_tooltip.property("text")) == actual_help
            assert int(help_tooltip.property("textFormat")) == Qt.TextFormat.RichText.value
            assert "<hr" not in actual_help
            assert "This node ran" not in actual_help

            value_label = named_item(host, "graphNumberSliderValueLabel")
            assert str(value_label.property("text")) == "0.500"

            slider = named_item(host, "graphNumberSliderControl")
            assert float(slider.property("from")) == 0.0
            assert float(slider.property("to")) == 1.0
            assert float(slider.property("value")) == 0.5
            assert abs(float(slider.property("stepSize")) - 0.001) < 1e-9

            rects = variant_list(surface.property("embeddedInteractiveRects"))
            assert len(rects) >= 2

            window = attach_host_to_window(host)
            try:
                QTest.mouseMove(window, item_scene_point(name_label))
                QTest.qWait(450)
                settle_events(5)
                assert bool(help_tooltip.property("managedVisible"))
            finally:
                dispose_host_window(host, window)

            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            workspace_id = model.active_workspace.workspace_id
            scene.set_workspace(model, registry, workspace_id)
            long_title = "Number Slider With A Long Descriptive Custom Name"
            long_node_id = scene.add_node_from_type("data.number_slider", 120.0, 80.0)
            scene.set_node_title(long_node_id, long_title)
            long_payload = next(
                item for item in scene.nodes_model if item["node_id"] == long_node_id
            )
            long_host = create_component(graph_node_host_qml_path, {"nodeData": long_payload})
            wait_for_surface(long_host, "graphNumberSliderSurface")
            long_label = named_item(long_host, "graphNumberSliderNameLabel")
            long_section = named_item(long_host, "graphNumberSliderNameSection")
            long_slider = named_item(long_host, "graphNumberSliderControl")
            settle_events(4)
            assert float(long_label.width()) >= float(long_label.property("implicitWidth")), (
                long_label.width(), long_label.property("implicitWidth")
            )
            assert float(long_section.x()) + float(long_section.width()) < float(long_slider.x()), (
                long_section.x(), long_section.width(), long_slider.x()
            )
            assert float(long_slider.width()) > 0.0
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

    def test_integer_mode_formats_and_steps_whole_numbers(self) -> None:
        self._run_qml_probe(
            "number-slider-integer-mode",
            _NUMBER_SLIDER_PAYLOAD_HELPER
            + """
            payload = number_slider_payload(
                properties={
                    "value": 7.0,
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "rounding": "integer",
                    "decimals": 0,
                },
                title="Index",
            )
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = wait_for_surface(host, "graphNumberSliderSurface")

            value_label = named_item(host, "graphNumberSliderValueLabel")
            assert str(value_label.property("text")) == "7"
            slider = named_item(host, "graphNumberSliderControl")
            assert float(slider.property("stepSize")) == 1.0
            name_label = named_item(host, "graphNumberSliderNameLabel")
            assert str(name_label.property("text")) == "Index"

            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_keyboard_move_commits_value_through_inline_property_channel(self) -> None:
        self._run_qml_probe(
            "number-slider-keyboard-commit",
            _NUMBER_SLIDER_PAYLOAD_HELPER
            + """
            payload = number_slider_payload(
                properties={
                    "value": 5.0,
                    "minimum": 0.0,
                    "maximum": 10.0,
                    "rounding": "integer",
                    "decimals": 0,
                },
            )
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = wait_for_surface(host, "graphNumberSliderSurface")

            commits = []
            host.inlinePropertyCommitted.connect(
                lambda node_id, key, value: commits.append((node_id, key, variant_value(value)))
            )
            interactions = []
            host.surfaceControlInteractionStarted.connect(lambda node_id: interactions.append(node_id))

            window = attach_host_to_window(host)
            slider = named_item(host, "graphNumberSliderControl")
            slider.forceActiveFocus()
            settle_events(2)
            QTest.keyClick(window, Qt.Key.Key_Right)
            settle_events(4)

            assert commits, "keyboard move must commit through inlinePropertyCommitted"
            node_id, key, value = commits[-1]
            assert node_id == "node_surface_host_test"
            assert key == "value"
            assert float(value) == 6.0

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_double_click_value_opens_settings_and_accept_commits_payload(self) -> None:
        self._run_qml_probe(
            "number-slider-settings-contract",
            _NUMBER_SLIDER_PAYLOAD_HELPER
            + """
            canvas_item = create_surface_canvas_item()
            payload = number_slider_payload()
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_item},
            )
            surface = wait_for_surface(host, "graphNumberSliderSurface")

            assert bool(surface.property("sliderSettingsEditorOpen")) is False
            assert bool(host.dispatchSurfaceAction("number_slider_edit_settings")) is True
            assert bool(surface.property("sliderSettingsEditorOpen")) is True

            settings_payload = variant_value(surface.property("sliderSettingsPayload"))
            assert settings_payload["title"] == "Number Slider"
            assert settings_payload["rounding"] == "decimal"
            assert float(settings_payload["minimum"]) == 0.0
            assert float(settings_payload["value"]) == 0.5
            assert float(settings_payload["maximum"]) == 1.0
            assert int(settings_payload["decimals"]) == 3

            accepted = surface.acceptSliderSettings(
                {
                    "title": "Thickness",
                    "rounding": "integer",
                    "decimals": 0,
                    "minimum": 1.0,
                    "value": 4.0,
                    "maximum": 8.0,
                }
            )
            assert bool(accepted) is True
            assert bool(surface.property("sliderSettingsEditorOpen")) is False
            assert canvas_item.last_committed_node_id == "node_surface_host_test"
            committed = canvas_item.last_committed_properties
            assert committed["title"] == "Thickness"
            assert committed["rounding"] == "integer"
            assert float(committed["minimum"]) == 1.0
            assert float(committed["value"]) == 4.0
            assert float(committed["maximum"]) == 8.0

            surface.dispatchSurfaceAction("number_slider_edit_settings")
            assert bool(surface.property("sliderSettingsEditorOpen")) is True
            surface.cancelSliderSettings()
            assert bool(surface.property("sliderSettingsEditorOpen")) is False

            host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_double_click_target_covers_value_readout(self) -> None:
        self._run_qml_probe(
            "number-slider-doubleclick-target",
            _NUMBER_SLIDER_PAYLOAD_HELPER
            + """
            payload = number_slider_payload()
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            surface = wait_for_surface(host, "graphNumberSliderSurface")

            window = attach_host_to_window(host)
            target = named_item(host, "graphNumberSliderValueDoubleClickTarget")
            assert bool(target.property("enabled")) is True
            assert float(target.property("width")) > 0.0

            mouse_double_click(window, item_scene_point(target))
            settle_events(4)
            assert bool(surface.property("sliderSettingsEditorOpen")) is True

            dispose_host_window(host, window)
            engine.deleteLater()
            app.processEvents()
            """,
        )


class NumberSliderSurfaceContractTests(unittest.TestCase):  # noqa: F405
    def test_surface_qml_uses_only_sanctioned_pointer_controls(self) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph/passive/GraphNumberSliderSurface.qml"  # noqa: F405
        ).read_text(encoding="utf-8")
        for snippet in (
            "GraphShared.GraphSurfaceBase {",
            'objectName: "graphNumberSliderSurface"',
            "SurfaceControls.GraphSurfaceSlider {",
            "SurfaceControls.GraphSurfaceDoubleClickTarget {",
            "radius: Math.max(0.0, surface.pillRadius - 1.0)",
            "when: !sliderControl.pressed",
            'host.dispatchSurfaceAction("number_slider_edit_settings")',
            "commitNodeSurfaceProperties",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)
        self.assertNotIn("MouseArea", qml_text)
        self.assertNotIn("TapHandler", qml_text)

    def test_canvas_root_layers_route_number_slider_overlay(self) -> None:
        root_layers_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"  # noqa: F405
        ).read_text(encoding="utf-8")
        overlay_text = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSurfaceEditorOverlays.qml"  # noqa: F405
        ).read_text(encoding="utf-8")
        for snippet in (
            "property alias numberSliderEditorHost: surfaceEditorOverlays.numberSliderEditorHost",
            "property alias numberSliderOverlayOpen: surfaceEditorOverlays.numberSliderOverlayOpen",
            "GraphCanvasSurfaceEditorOverlays {",
            "return surfaceEditorOverlays.openSurfaceActionOverlayForHost(host, actionId, surface);",
        ):
            with self.subTest(owner="root", snippet=snippet):
                self.assertIn(snippet, root_layers_text)
        for snippet in (
            "property Item numberSliderEditorHost: null",
            "property bool numberSliderOverlayOpen: false",
            'String(actionId || "") === "number_slider_edit_settings"',
            "GraphPassive.GraphNumberSliderSettingsPopover {",
            "onSliderSettingsEditorOpenChanged",
            'objectName: "graphNumberSliderOverlayLayer"',
        ):
            with self.subTest(owner="overlay", snippet=snippet):
                self.assertIn(snippet, overlay_text)

    def test_settings_popover_uses_shared_theme_dialog_controls(self) -> None:
        common_root = _REPO_ROOT / "ea_node_editor/ui_qml/components/common"  # noqa: F405
        surface_text = (common_root / "DialogSurface.qml").read_text(encoding="utf-8")
        field_text = (common_root / "DialogTextField.qml").read_text(encoding="utf-8")
        button_text = (common_root / "DialogButton.qml").read_text(encoding="utf-8")
        popover_text = (
            _REPO_ROOT  # noqa: F405
            / "ea_node_editor/ui_qml/components/graph/passive/GraphNumberSliderSettingsPopover.qml"
        ).read_text(encoding="utf-8")
        overlay_text = (
            _REPO_ROOT
            / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSurfaceEditorOverlays.qml"  # noqa: F405
        ).read_text(encoding="utf-8")

        for text, snippets in (
            (
                surface_text,
                (
                    "default property alias contentData: contentHost.data",
                    "property var themePalette",
                    "property string title",
                    "property bool closeButtonVisible",
                    "signal closeRequested()",
                    'Accessible.name: root.title.length > 0 ? "Close " + root.title : "Close dialog"',
                ),
            ),
            (field_text, ("property var themePalette", "property real controlHeight", "control.activeFocus")),
            (
                button_text,
                (
                    "property var themePalette",
                    "property bool primary",
                    "property bool selected",
                    "property real controlHeight",
                ),
            ),
            (
                popover_text,
                (
                    'import "../../common" as Common',
                    "Common.DialogSurface {",
                    "onCloseRequested: root.cancelEdit()",
                    'placeholderText: "Custom name..."',
                    'text: "ℤ"',
                    'text: "ℚ"',
                    'text: "Digits"',
                    "Layout.preferredWidth: 160",
                    "primary: true",
                ),
            ),
            (overlay_text, ("Math.min(400, Math.max(320, numberSliderOverlayLayer.width - 48))",)),
        ):
            for snippet in snippets:
                with self.subTest(snippet=snippet):
                    self.assertIn(snippet, text)

        self.assertNotIn("GraphSurfaceControls", popover_text)
        self.assertNotIn("root.host.surfaceColor", popover_text)
        self.assertEqual(popover_text.count("controlHeight: 44"), 9)

    def test_node_browser_smart_insert_wiring_present(self) -> None:
        qml_text = (
            _REPO_ROOT / "ea_node_editor/ui_qml/components/shell/NodeBrowserOverlay.qml"  # noqa: F405
        ).read_text(encoding="utf-8")
        for snippet in (
            "parse_number_slider_query(root.queryText)",
            "smart_insert_properties",
            "request_drop_node_from_library_with_properties",
            "request_add_node_from_library_with_properties",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, qml_text)
