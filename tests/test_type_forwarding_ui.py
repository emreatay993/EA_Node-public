# Purpose: Prove forwarding recommendations, live scene updates and rendered drag behavior.
# Map: feature_routes/workflow_library_drop_connect.md
# Tests: this file
from types import SimpleNamespace
import copy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.type_forwarding import ResolvedSourceContract
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.runtime_contracts import DOUBLE_DATA_TYPE_ID, INTEGER_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID
from ea_node_editor.ui.shell.library_projection import build_registry_library_items
from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import WorkspaceDropConnectController
from ea_node_editor.ui.shell.presenters.library_presenter import ShellLibraryPresenter
from ea_node_editor.ui.shell.presenters.state import build_connection_quick_insert_context, build_connection_quick_insert_results
from ea_node_editor.ui.shell.quick_insert_projection import build_connection_quick_insert_items
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui.shell.state import ConnectionQuickInsertState, ShellLibraryFilterState, ShellWindowSearchScopeState
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui.support.node_presentation import build_data_type_ui_projection, project_port_data_type_presentation
from tests.graph_surface.environment import GraphSurfaceInputContractTestBase

IMAGE = "COREX.DataTypes.Image"


def make_scene():
    registry = build_builtin_registry()
    for name, type_id, direction in (("integer", INTEGER_DATA_TYPE_ID, "out"),
                                     ("decimal", DOUBLE_DATA_TYPE_ID, "out"),
                                     ("image_sink", IMAGE, "in"), ("number_sink", DOUBLE_DATA_TYPE_ID, "in")):
        spec = NodeTypeSpec(type_id="tests." + name, display_name=name, category_path=("Tests",), icon="",
            ports=(PortSpec("value", direction, "data", type_id,
                required=True if direction == "in" else None,
                accepted_data_types=(INTEGER_DATA_TYPE_ID,) if name == "number_sink" else ()),), properties=())
        registry.register_descriptor(spec, lambda: None)
    model = GraphModel()
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, model.active_workspace.workspace_id)
    return model, registry, scene


def add_chain(scene):
    plot = scene.add_node_from_type("plot.signal", -460, -180)
    panel = scene.add_node_from_type("data.panel", -110, -100)
    trigger = scene.add_node_from_type("core.trigger", 190, -100)
    upstream = scene.add_edge(plot, "image", panel, "input")
    scene.add_edge(panel, "output", trigger, "input")
    return plot, panel, trigger, upstream


def port_payload(scene, node_id, key):
    return next(port for node in scene.nodes_model if node["node_id"] == node_id
                for port in node["ports"] if port["key"] == key)


class LibraryHost(QObject):
    node_library_changed = pyqtSignal()
    library_pane_reset_requested = pyqtSignal()
    graph_search_changed = pyqtSignal()
    connection_quick_insert_changed = pyqtSignal()
    graph_hint_changed = pyqtSignal()
    _CONNECTION_QUICK_INSERT_LIMIT = 100
    _CONNECTION_QUICK_INSERT_OFFSET = 30

    def __init__(self, model, registry, scene):
        super().__init__()
        self.model, self.registry, self.scene = model, registry, scene
        self.workspace_manager = SimpleNamespace(active_workspace_id=lambda: model.active_workspace.workspace_id)
        self.search_scope_state = ShellWindowSearchScopeState()
        self.library_filter_state = ShellLibraryFilterState()
        self.workflow_library_controller = SimpleNamespace(custom_workflow_library_items=lambda: [])
        self.workspace_ui_state = SimpleNamespace(passive_node_library_display_mode="text")
        self.search_scope_controller = SimpleNamespace(set_graph_search_state=lambda **kwargs: None)
        self.drops = []
        self.workspace_drop_connect_controller = SimpleNamespace(request_drop_node_from_library=self.drop)

    def drop(self, *args, **kwargs):
        self.drops.append((args, kwargs))
        return SimpleNamespace(payload="created")


def test_same_recommendations_through_plot_panel_and_trigger():
    model, registry, scene = make_scene()
    plot, panel, trigger, _ = add_chain(scene)
    direct_trigger = scene.add_node_from_type("core.trigger", 100, 150)
    scene.add_edge(plot, "image", direct_trigger, "input")
    host = LibraryHost(model, registry, scene)
    items = build_registry_library_items(registry_specs=registry.all_specs(), data_types=registry.data_types)
    results = []
    for node_id, key in ((plot, "image"), (direct_trigger, "output"), (panel, "output"), (trigger, "output")):
        context = build_connection_quick_insert_context(host, node_id, key)
        assert context["source_type_ids"] == [IMAGE]
        rows, _ = build_connection_quick_insert_results(host, items, "", ConnectionQuickInsertState(context=context))
        results.append(rows)
    assert results[0] == results[1] == results[2] == results[3]
    assert {"io.image_export", "media.panel"} <= {row["type_id"] for row in results[0]}
    assert port_payload(scene, panel, "input")["data_type"] == GRAPH_DATA_TYPE_ID
    for node_id in (panel, trigger):
        port = port_payload(scene, node_id, "output")
        assert port["data_type"] == GRAPH_DATA_TYPE_ID
        assert port["data_type_label"] == "Image"
        assert port["source_type_ids"] == [IMAGE]
        assert port["accepted_data_type_labels"] == []


def test_mixed_sources_require_every_member_and_use_worst_recommendation_tier():
    _, registry, _ = make_scene()
    def row(key, primary, accepted=()):
        return {"type_id": key, "display_name": key, "ports": [{"key": "in", "direction": "in",
            "kind": "data", "data_type": primary, "accepted_data_types": list(accepted)}]}
    rows = [row("number", DOUBLE_DATA_TYPE_ID, (INTEGER_DATA_TYPE_ID,)), row("image", IMAGE),
            row("mixed", INTEGER_DATA_TYPE_ID, (GRAPH_DATA_TYPE_ID,))]
    def candidates(types, query=""):
        return build_connection_quick_insert_items(combined_items=rows, data_types=registry.data_types,
            query=query, source_direction="out", source_kind="data", source_data_type=GRAPH_DATA_TYPE_ID,
            source_contract=ResolvedSourceContract(types), limit=100)
    assert [row["type_id"] for row in candidates((INTEGER_DATA_TYPE_ID, DOUBLE_DATA_TYPE_ID))] == ["number"]
    assert candidates((IMAGE, INTEGER_DATA_TYPE_ID)) == []
    assert candidates((IMAGE, INTEGER_DATA_TYPE_ID), "mixed")[0]["compatibility_kind"] == "generic"
    assert candidates((GRAPH_DATA_TYPE_ID,)) == []
    unresolved = build_connection_quick_insert_items(combined_items=rows, data_types=registry.data_types,
        query="image", source_direction="out", source_kind="data", source_data_type=GRAPH_DATA_TYPE_ID,
        source_contract=ResolvedSourceContract((IMAGE,), True))
    assert unresolved == []


def many_source_projection(registry):
    types = tuple(record["type_id"] for record in registry.data_types.snapshot()
                  if record["kind"] == "type" and registry.data_types.compatibility(record["type_id"], GRAPH_DATA_TYPE_ID).is_compatible)[:12]
    assert len(types) == 12
    source = project_port_data_type_presentation(
        data_type=GRAPH_DATA_TYPE_ID, source_type_ids=types,
        projection=build_data_type_ui_projection(registry.data_types),
    )
    assert source["source_type_ids"] == list(types)
    assert len(source["data_type_label"]) <= 160
    return {**source, "direction": "out", "kind": "data", "key": "out", "exposed": True}


def test_source_display_limit_does_not_truncate_semantic_types():
    _, registry, _ = make_scene()
    many_source_projection(registry)


def test_disabled_and_property_dependent_sources_refresh_entire_visible_chain():
    model, registry, scene = make_scene()
    script = '@corex.node\n@corex.output("value", value_type=corex.Image)\ndef run(ctx):\n    return {}\n'
    source = scene.create_node_from_type(type_id="core.python_script", x=0, y=0, parent_node_id=None,
                                         select_node=False, property_overrides={"script": script})
    panel = scene.add_node_from_type("data.panel", 250, 0)
    trigger = scene.add_node_from_type("core.trigger", 480, 0)
    sink = scene.add_node_from_type("tests.image_sink", 720, 0)
    upstream = scene.add_edge(source, "value", panel, "input")
    scene.add_edge(panel, "output", trigger, "input")
    downstream = scene.add_edge(trigger, "output", sink, "value")
    assert scene.set_edge_enabled(upstream, False)
    assert port_payload(scene, trigger, "output")["source_type_ids"] == [GRAPH_DATA_TYPE_ID]
    assert scene.set_edge_enabled(upstream, True)
    assert port_payload(scene, trigger, "output")["source_type_ids"] == [IMAGE]
    scene.set_node_property(source, "script", script.replace("corex.Image", "int"))
    assert downstream not in {edge["edge_id"] for edge in scene.edges_model}
    assert port_payload(scene, trigger, "output")["source_type_ids"] == [INTEGER_DATA_TYPE_ID]
    snapshot = scene.policy_bridge.compatible_endpoint_snapshot(trigger, "output", "target")
    assert sink not in {endpoint["node_id"] for endpoint in snapshot["compatible_endpoint_ids"]}


def test_open_popup_refreshes_and_selection_revalidates_item_and_port_identity():
    model, registry, scene = make_scene()
    _, panel, trigger, _ = add_chain(scene)
    host = LibraryHost(model, registry, scene)
    presenter = ShellLibraryPresenter(host)
    assert presenter.request_open_connection_quick_insert(trigger, "output", 10, 20, 30, 40, True)
    state = host.search_scope_state.connection_quick_insert
    export_index = next(i for i, row in enumerate(state.results) if row["type_id"] == "io.image_export")
    assert presenter.request_connection_quick_insert_choose(export_index)
    args, kwargs = host.drops.pop()
    assert args[4:6] == (trigger, "output")
    assert args[7] is True
    assert kwargs["compatible_port_keys"] == ("image",)
    assert presenter.request_open_connection_quick_insert(trigger, "output", 10, 20, 30, 40)
    old_rows = list(state.results)
    presenter.request_connection_quick_insert_highlight(next(i for i, row in enumerate(state.results) if row["type_id"] == "io.image_export"))
    integer = scene.add_node_from_type("tests.integer", -300, 220)
    scene.add_edge(integer, "value", panel, "input")
    assert state.context["source_type_ids"] == [INTEGER_DATA_TYPE_ID]
    assert state.context["overlay_x"] == 30
    assert "io.image_export" not in {row["type_id"] for row in state.results}
    assert state.highlight_index == -1
    assert not presenter.request_connection_quick_insert_accept()
    # Simulate a selection event queued before the graph publication.
    state.results = old_rows
    export_index = next(i for i, row in enumerate(old_rows) if row["type_id"] == "io.image_export")
    assert not presenter.request_connection_quick_insert_choose(export_index)
    assert host.drops == []
    scene.remove_node(trigger)
    assert not state.open


def test_pruned_edges_and_transitive_payloads_publish_and_undo_together():
    model, registry, scene = make_scene()
    _, panel, trigger, _ = add_chain(scene)
    sink = scene.add_node_from_type("tests.image_sink", 460, -100)
    downstream = scene.add_edge(trigger, "output", sink, "value")
    integer = scene.add_node_from_type("tests.integer", -300, 220)
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    import ea_node_editor.ui_qml.graph_scene.context as context_module
    with patch.object(context_module, "GraphTypeResolver", wraps=context_module.GraphTypeResolver) as resolve:
        scene.add_edge(integer, "value", panel, "input")
        assert resolve.call_count == 1
    assert downstream not in {edge["edge_id"] for edge in scene.edges_model}

    assert downstream in scene.edge_delta_payload["removed_edge_ids"]
    assert trigger in {row["node_id"] for row in scene.state_bridge.node_delta_payload["nodes"]}
    assert port_payload(scene, trigger, "output")["source_type_ids"] == [INTEGER_DATA_TYPE_ID]
    assert history.undo_depth(model.active_workspace.workspace_id) == 1
    history.undo_workspace(model.active_workspace.workspace_id, model.active_workspace)
    scene.refresh_workspace_from_model(model.active_workspace.workspace_id)
    assert downstream in {edge["edge_id"] for edge in scene.edges_model}
    assert port_payload(scene, trigger, "output")["source_type_ids"] == [IMAGE]
    history.redo_workspace(model.active_workspace.workspace_id, model.active_workspace)
    scene.refresh_workspace_from_model(model.active_workspace.workspace_id)
    assert downstream not in {edge["edge_id"] for edge in scene.edges_model}

def test_popup_closes_on_scope_and_project_replacement_with_same_ids():
    model, registry, scene = make_scene()
    _, _, trigger, _ = add_chain(scene)
    shell = scene.add_node_from_type("core.subnode", 0, 200)
    host = LibraryHost(model, registry, scene)
    presenter = ShellLibraryPresenter(host)
    assert presenter.request_open_connection_quick_insert(trigger, "output", 0, 0, 0, 0)
    assert scene.open_subnode_scope(shell)
    assert not host.search_scope_state.connection_quick_insert.open
    assert build_connection_quick_insert_context(host, trigger, "output") is None
    scene.navigate_scope_root()
    assert presenter.request_open_connection_quick_insert(trigger, "output", 0, 0, 0, 0)
    replacement = GraphModel()
    replacement.project = copy.deepcopy(model.project)
    host.model = replacement
    scene.set_workspace(replacement, registry, model.active_workspace.workspace_id)
    assert not host.search_scope_state.connection_quick_insert.open



@pytest.mark.parametrize("type_id, input_key", [("io.image_export", "image"), ("media.panel", "source")])
def test_recommended_node_connects_from_the_dragged_trigger_through_real_controller(type_id, input_key):
    model, registry, scene = make_scene()
    plot, panel, trigger, _ = add_chain(scene)
    host = LibraryHost(model, registry, scene)
    host.runtime_history = RuntimeGraphHistory()
    scene.bind_runtime_history(host.runtime_history)
    host.workspace_drop_connect_controller = WorkspaceDropConnectController(
        host, active_workspace=lambda: model.active_workspace,
        resolve_custom_workflow_definition=lambda _key: None,
        prompt_connection_candidate=lambda **kwargs: kwargs["candidates"][0] if kwargs["candidates"] else None,
        effects=SimpleNamespace(),
    )
    presenter = ShellLibraryPresenter(host)
    assert presenter.request_open_connection_quick_insert(trigger, "output", 420, 120, 600, 400)
    state = host.search_scope_state.connection_quick_insert
    index = next(i for i, item in enumerate(state.results) if item["type_id"] == type_id)
    assert presenter.request_connection_quick_insert_choose(index)
    inserted = next(node for node in model.active_workspace.nodes.values() if node.type_id == type_id)
    connections = [edge for edge in model.active_workspace.edges.values() if edge.target_node_id == inserted.node_id]
    assert [(edge.source_node_id, edge.source_port_key, edge.target_port_key) for edge in connections] == [
        (trigger, "output", input_key)]
    assert host.runtime_history.undo_depth(model.active_workspace.workspace_id) == 1
    host.runtime_history.undo_workspace(model.active_workspace.workspace_id, model.active_workspace)
    assert inserted.node_id not in model.active_workspace.nodes
    assert {plot, panel, trigger} <= model.active_workspace.nodes.keys()


class ForwardingDragRenderTests(GraphSurfaceInputContractTestBase):
    def test_graph_contract_changes_refresh_an_active_drag(self):
        self._run_qml_probe("forwarding-contract-drag-refresh", """
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QFont, QFontDatabase
            from PyQt6.QtTest import QTest
            from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
            from tests.test_type_forwarding_ui import make_scene, add_chain, many_source_projection

            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
            if font_path.is_file():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                assert font_id >= 0, "test text font unavailable"
                app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
            else:
                app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
            model, registry, scene = make_scene()
            plot, panel, trigger, upstream = add_chain(scene)
            sink = scene.add_node_from_type("tests.image_sink", 460, -100)
            number = scene.add_node_from_type("tests.number_sink", 460, 160)
            integer = scene.add_node_from_type("tests.integer", -440, 240)
            view = ViewportBridge()
            view.set_viewport_size(1480.0, 850.0)
            state, commands = build_canvas_bridges(scene_bridge=scene, view_bridge=view)
            canvas = create_component(graph_canvas_qml_path, {
                "canvasStateBridge": state, "canvasCommandBridge": commands, "width": 1480.0, "height": 850.0})
            window = attach_host_to_window(canvas, 1480, 850)
            view.frame_scene_rect_payload(-500, -230, 1310, 650, 60)
            settle_events(8)
            many_source = many_source_projection(registry)
            any_target = {"key": "in", "kind": "data", "direction": "in", "data_type": "COREX.DataTypes.Any", "exposed": True}
            assert canvas._portsCompatibleForAuto(many_source, any_target), "display cap rejected valid mixed source"
            bad_last = dict(many_source, source_type_ids=many_source["source_type_ids"] + ["missing.type"])
            assert not canvas._portsCompatibleForAuto(bad_last, any_target), "compatibility ignored late source member"

            def dot(node_id, key, direction):
                for host in named_child_items(canvas, "graphNodeCard"):
                    if variant_value(host.property("nodeData"))["node_id"] == node_id:
                        return named_item(host, "graphNodeOutputPortDot" if direction == "out" else "graphNodeInputPortDot", key)
                raise AssertionError("missing node " + node_id)

            origin = item_scene_point(dot(trigger, "output", "out"))
            destination = item_scene_point(dot(sink, "value", "in"))
            sx, sy = canvas.screenToSceneX(origin.x()), canvas.screenToSceneY(origin.y())
            canvas.handlePortClick(trigger, "output", "out", sx, sy, 0)
            QTest.mouseMove(window, destination)
            settle_events(4)
            assert variant_value(canvas.wireDragPreviewConnection())["valid_drop"], "image click-hover rejected"
            number_point = item_scene_point(dot(number, "value", "in"))
            QTest.mouseMove(window, number_point)
            settle_events(4)
            assert not variant_value(canvas.wireDragPreviewConnection())["valid_drop"], "number click-hover accepted Image"
            canvas.clearPendingConnection()
            canvas.beginPortWireDrag(trigger, "output", "out", sx, sy, origin.x(), origin.y(), 0)
            canvas.updatePortWireDrag(trigger, "output", "out", sx, sy, destination.x(), destination.y(), True, 0)
            settle_events(3)
            assert variant_value(canvas.property("wireDragState"))["active"]
            assert bool(dot(sink, "value", "in").property("compatibleTargetState")), "initial image target not highlighted"
            artifact = repo_root / "artifacts" / "type_forwarding" / "forwarding-image-drag.png"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            QTest.qWait(60)
            assert window.grabWindow().save(str(artifact)), "could not capture rendered drag"
            scene.add_edge(integer, "value", panel, "input")
            settle_events(5)
            assert variant_value(canvas.property("wireDragState"))["active"], "same-workspace update cancelled drag"
            assert not bool(dot(sink, "value", "in").property("compatibleTargetState")), "image target still highlighted after type change"
            assert bool(dot(number, "value", "in").property("compatibleTargetState")), "number target not highlighted after type change"
            canvas.cancelWireDrag()
            # Ctrl-dragging the moving source must cancel when its wire is removed,
            # even though the fixed target endpoint still exists.
            moving = scene.add_edge(trigger, "output", number, "value")
            settle_events(4)
            ctrl = Qt.KeyboardModifier.ControlModifier.value
            canvas.beginPortWireDrag(trigger, "output", "out", sx, sy, origin.x(), origin.y(), ctrl)
            canvas.updatePortWireDrag(trigger, "output", "out", sx, sy, origin.x()+50, origin.y()+70, True, ctrl)
            settle_events(3)
            assert variant_value(canvas.property("wireDragState"))["rewire"]
            scene.remove_edge(moving)
            settle_events(4)
            assert not variant_value(canvas.property("wireDragState")), "removed moving edge kept drag alive"
            canvas.beginPortWireDrag(trigger, "output", "out", sx, sy, origin.x(), origin.y(), 0)
            canvas.updatePortWireDrag(trigger, "output", "out", sx, sy, destination.x(), destination.y(), True, 0)
            scene.remove_node(trigger)
            settle_events(4)
            assert not variant_value(canvas.property("wireDragState")), "deleted anchor kept drag alive"
            # A fresh model with identical graph IDs is a new editing session.
            import copy
            from ea_node_editor.graph.model import GraphModel
            canvas.beginPortWireDrag(plot, "image", "out", 0, 0, 100, 100, 0)
            canvas.updatePortWireDrag(plot, "image", "out", 0, 0, 180, 180, True, 0)
            replacement = GraphModel()
            replacement.project = copy.deepcopy(model.project)
            scene.set_workspace(replacement, registry, model.active_workspace.workspace_id)
            settle_events(4)
            assert not variant_value(canvas.property("wireDragState")), "new project inherited previous gesture"
            window.close()
            canvas.deleteLater()
            app.processEvents()
        """)
