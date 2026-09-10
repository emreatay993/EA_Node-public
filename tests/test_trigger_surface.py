from __future__ import annotations

import textwrap

import pytest

from tests.graph_surface.environment import PassiveGraphSurfaceHostTestBase


pytestmark = pytest.mark.xdist_group("trigger_surface")


_TRIGGER_PAYLOAD_HELPER = textwrap.indent(
    """
def trigger_payload():
    payload = node_payload(surface_family="standard", surface_variant="trigger")
    payload["type_id"] = "core.trigger"
    payload["title"] = "Trigger"
    payload["display_name"] = "Trigger"
    payload["category_path"] = ["Data", "Control"]
    payload["help_text"] = "Stop downstream nodes from running until you click the button."
    payload["keywords"] = ["button", "action", "run", "dam", "gate", "block"]
    payload["width"] = 160.0
    payload["height"] = 40.0
    payload["surface_spec"] = surface_spec_payload_for_values(
        type_id="core.trigger",
        family="standard",
        variant="trigger",
    )
    payload["surface_metrics"] = {
        "default_width": 160.0,
        "default_height": 40.0,
        "min_width": 120.0,
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
    payload["properties"] = {}
    payload["ports"] = [
        {
            "key": "input",
            "label": "Input",
            "direction": "in",
            "kind": "data",
            "data_type": "any",
            "data_access": "tree",
            "connected": False,
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


class TriggerSurfaceTests(PassiveGraphSurfaceHostTestBase):
    def test_trigger_pill_renders_button_and_emits_trigger_request(self) -> None:
        self._run_qml_probe(
            "trigger-pill-button",
            _TRIGGER_PAYLOAD_HELPER
            + """
            payload = trigger_payload()
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
                raise AssertionError(f"Failed to create Trigger canvas facts stub:\\n{errors}")
            canvas_stub = canvas_component.create()
            assert canvas_stub is not None
            host = create_component(
                graph_node_host_qml_path,
                {"nodeData": payload, "canvasItem": canvas_stub},
            )
            surface = wait_for_surface(host, "graphTriggerSurface")
            button = named_item(host, "graphTriggerNodeControl")
            input_dot = named_item(host, "graphNodeInputPortDot")
            input_label = named_item(host, "graphNodeInputPortLabel")
            output_dot = named_item(host, "graphNodeOutputPortDot")
            output_label = named_item(host, "graphNodeOutputPortLabel")
            header = named_item(host, "graphNodeHeaderLayer")
            help_tooltip = wait_for_named_object(host, "graphTriggerHelpToolTip")
            button_tooltip = wait_for_named_object(host, "graphTriggerNodeControl_tooltip")
            elapsed_timer = named_item(host, "graphNodeElapsedTimer")

            assert bool(host.property("isTriggerSurface"))
            assert bool(host.property("isCompactPillSurface"))
            assert not bool(header.property("headerTitleVisible"))
            assert not bool(input_label.property("visible"))
            assert not bool(output_label.property("visible"))
            assert float(host.property("resolvedCornerRadius")) == 20.0
            assert str(button.property("text")) == "Trigger"
            assert bool(host.property("elapsedTimeSuppressedForNode"))
            assert not bool(elapsed_timer.property("visible"))
            expected_help = (
                '<b>Trigger</b><br>'
                '<font color="#95a0b8">Data, Control</font><br>'
                'Stop downstream nodes from running until you click the button.<br><br>'
                'Keywords: button, action, run, dam, gate, block.'
                '<hr color="#3a4355">This node ran 1 time(s).'
            )
            assert str(host.property("nodeHelpTooltipText")) == expected_help
            assert str(help_tooltip.property("text")) == expected_help
            assert int(help_tooltip.property("textFormat")) == 1
            assert str(button_tooltip.property("text")) == expected_help
            assert int(button_tooltip.property("textFormat")) == 1
            assert len(variant_list(surface.property("embeddedInteractiveRects"))) == 1

            host_origin = host.mapToScene(QPointF(0.0, 0.0))
            for dot in (input_dot, output_dot):
                dot_center = dot.mapToScene(
                    QPointF(dot.width() * 0.5, dot.height() * 0.5)
                )
                assert abs((dot_center.y() - host_origin.y()) - 20.0) < 0.5

            requests = []
            host.triggerNodeRequested.connect(lambda node_id: requests.append(str(node_id)))
            window = attach_host_to_window(host)
            QTest.mouseMove(window, item_scene_point(button))
            QTest.qWait(450)
            settle_events(5)
            assert bool(button_tooltip.property("managedVisible"))
            assert bool(button_tooltip.property("visible"))
            assert not bool(help_tooltip.property("visible"))
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                item_scene_point(button),
            )
            settle_events(4)
            assert requests == ["node_surface_host_test"]

            dispose_host_window(host, window)
            canvas_stub.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_trigger_button_label_follows_rename(self) -> None:
        self._run_qml_probe(
            "trigger-button-label-rename",
            _TRIGGER_PAYLOAD_HELPER
            + """
            model = GraphModel()
            registry = build_default_registry()
            scene = GraphSceneBridge()
            workspace_id = model.active_workspace.workspace_id
            scene.set_workspace(model, registry, workspace_id)
            long_title = "Trigger A Long Descriptive Custom Publication Gate"
            node_id = scene.add_node_from_type("core.trigger", 120.0, 80.0)
            scene.set_node_title(node_id, long_title)
            payload = next(item for item in scene.nodes_model if item["node_id"] == node_id)
            host = create_component(graph_node_host_qml_path, {"nodeData": payload})
            wait_for_surface(host, "graphTriggerSurface")
            button = named_item(host, "graphTriggerNodeControl")
            assert str(button.property("text")) == payload["title"]
            assert float(button.width()) >= float(button.property("implicitWidth"))
            assert float(button.x()) >= 0.0
            assert float(button.x()) + float(button.width()) <= float(host.width())
            host.deleteLater()
            scene.deleteLater()

            untitled = trigger_payload()
            untitled["title"] = ""
            fallback_host = create_component(graph_node_host_qml_path, {"nodeData": untitled})
            wait_for_surface(fallback_host, "graphTriggerSurface")
            assert str(named_item(fallback_host, "graphTriggerNodeControl").property("text")) == "Trigger"
            fallback_host.deleteLater()
            engine.deleteLater()
            app.processEvents()
            """,
        )

    def test_trigger_qml_uses_shared_button_and_host_owns_no_trigger_control(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        surface = (
            root
            / "ea_node_editor/ui_qml/components/graph/passive/GraphTriggerSurface.qml"
        ).read_text(encoding="utf-8")
        host = (
            root / "ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml"
        ).read_text(encoding="utf-8")

        assert "SurfaceControls.GraphSurfaceButton" in surface
        assert "triggerNodeRequested" in surface
        assert 'objectName: "graphTriggerNodeControl"' in surface
        assert "graphTriggerNodeControl" not in host
        assert "isTriggerNode" not in host
