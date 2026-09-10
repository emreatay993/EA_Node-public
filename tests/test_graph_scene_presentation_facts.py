from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
from unittest import mock

import pytest

import ea_node_editor.ui_qml.graph_geometry.route_payload as route_payload
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_payloads import node_instance_to_mapping
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.node_specs import (
    NodeTypeSpec,
    PortSpec,
    PropertyConditionSpec,
    PropertySpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
    DataTree,
    Interval1D,
)
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    resolve_runtime_property_presentations,
)
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    node_surface_metrics,
    resolved_node_surface_size,
    standard_inline_property_row_height,
)
from ea_node_editor.ui_qml.graph_geometry.anchors import surface_port_local_point
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder


def test_scene_runtime_schema_focus_hook_allows_qcore_only_application() -> None:
    from tests.test_startup_import_profile import StartupImportProfileTests

    probe = StartupImportProfileTests()._run_python(
        "from PyQt6.QtCore import QCoreApplication; from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge; from ea_node_editor.ui.support.node_presentation import has_focused_selector; app=QCoreApplication([]); GraphSceneBridge(); assert not has_focused_selector('inspectorPropertyEditor')",
    )
    assert probe.returncode == 0, probe.stderr


def test_signal_inline_schema_refresh_uses_only_current_accepted_output_and_preserves_authored_values() -> None:
    from types import SimpleNamespace
    import numpy as np
    from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value
    from ea_node_editor.ui.support.solution_output_cache import current_output_value

    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    source_id = scene.add_node_from_type("core.python_script", 0., 0.)
    signal_id = scene.add_node_from_type("plot.signal", 280., 0.)
    model.add_edge(workspace.workspace_id, source_id, "result", signal_id, "values")
    scene.set_node_property(signal_id, "x_column", 0)
    value = DataTree.from_item(snapshot_scientific_value(np.ones((3, 2))))
    record = {"record_id": "accepted", "outputs_available": True, "outputs": {"result": SettledPortResult(status="value", value=value)}}
    fact = SimpleNamespace(retained_record_id="accepted", freshness=SimpleNamespace(value="current"))
    state = SimpleNamespace(node_solution_facts_by_workspace_id={workspace.workspace_id: {source_id: fact}}, cached_node_output_records_by_workspace_id={workspace.workspace_id: {source_id: {"accepted": record}}})
    scene.set_current_output_provider(lambda ws, node, port: current_output_value(state, ws, node, port))

    def choices():
        scene.refresh_current_output_properties()
        payload = next(item for item in scene.nodes_model if item["node_id"] == signal_id)
        items = {port["key"]: port["default_property"] for port in payload["ports"] if "default_property" in port}
        return items["x_column"]

    assert choices()["enum_codes"] == [0, 1]
    record["outputs"]["result"] = SettledPortResult(status="value", value=DataTree.from_item(snapshot_scientific_value(np.ones((3, 3)))))
    assert choices()["enum_codes"] == [0, 1, 2]
    for unavailable in ("expired", "missing", "evicted"):
        fact.freshness.value = "expired" if unavailable == "expired" else "current"
        record["outputs_available"] = unavailable != "missing"
        if unavailable == "evicted":
            state.cached_node_output_records_by_workspace_id.clear()
        assert choices()["enum_codes"] == []
        assert choices()["value"] == 0


def test_signal_selectors_survive_inspector_edits_undo_redo_and_project_roundtrip() -> None:
    from types import SimpleNamespace
    from ea_node_editor.persistence.project_codec import JsonProjectCodec
    from ea_node_editor.ui.shell.controllers.workspace_edit_controller import WorkspaceEditController

    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    node_id = scene.add_node_from_type("plot.signal", 0., 0.)
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    selected = SimpleNamespace(active_workspace=lambda: workspace, selected_node_context=lambda: (workspace.nodes[node_id], registry.get_spec("plot.signal")))
    effects = SimpleNamespace(after_selected_node_property_changed=lambda *args, **kwargs: None)
    controller = WorkspaceEditController(SimpleNamespace(model=model, scene=scene), selection_context=selected, effects=effects)
    controller.set_selected_node_property("x_column", " Column 1 ")
    controller.set_selected_node_property("y_columns", [0, " Signal ", "signal"])
    assert workspace.nodes[node_id].properties["x_column"] == " Column 1 "
    assert workspace.nodes[node_id].properties["y_columns"] == [0, " Signal ", "signal"]
    assert history.undo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[node_id].properties["y_columns"] == []
    assert history.redo_workspace(workspace.workspace_id, workspace) is not None
    codec = JsonProjectCodec(registry)
    restored = codec.from_document(codec.to_document(model.project))
    assert restored.workspaces[workspace.workspace_id].nodes[node_id].properties["y_columns"] == [0, " Signal ", "signal"]


def _chain_scene():
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(workspace.workspace_id, "core.python_script", "Source", 0.0, 0.0)
    middle = model.add_node(workspace.workspace_id, "core.python_script", "Middle", 280.0, 0.0)
    target = model.add_node(workspace.workspace_id, "core.python_script", "Target", 560.0, 0.0)
    first_edge = model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "result",
        middle.node_id,
        "payload",
    )
    second_edge = model.add_edge(
        workspace.workspace_id,
        middle.node_id,
        "result",
        target.node_id,
        "payload",
    )
    return registry, model, workspace, (source, middle, target), (first_edge, second_edge)


def test_library_preview_fallback_keeps_only_canonical_primary_type() -> None:
    spec = GraphScenePayloadBuilder._library_preview_fallback_spec(
        {
            "type_id": "tests.library_preview",
            "ports": [
                {
                    "key": "missing_primary",
                    "direction": "in",
                    "kind": "data",
                    "accepted_data_types": [STRING_DATA_TYPE_ID],
                },
                {
                    "key": "typed",
                    "direction": "in",
                    "kind": "data",
                    "data_type": STRING_DATA_TYPE_ID,
                    "accepted_data_types": [GRAPH_DATA_TYPE_ID, STRING_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID],
                }
            ],
        }
    )

    assert spec is not None
    assert [port.key for port in spec.ports] == ["typed"]
    assert spec.ports[0].data_type == STRING_DATA_TYPE_ID
    assert spec.ports[0].accepted_data_types == (GRAPH_DATA_TYPE_ID,)


def test_scene_payload_projects_shared_collapsible_capability() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)

    collapsible_id = scene.add_node_from_type("core.logger", 0.0, 0.0)
    fixed_id = scene.add_node_from_type("core.trigger", 280.0, 0.0)
    payloads = {payload["node_id"]: payload for payload in scene.nodes_model}

    assert payloads[collapsible_id]["collapsible"] is True
    assert payloads[fixed_id]["collapsible"] is False


class _SettingsGroupProjectionNode:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id="tests.settings_group_projection",
            display_name="Settings Group Projection",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec("values", "in", "data", 'COREX.DataTypes.Any', label="Values", required=False),
                PortSpec("width", "in", "data", 'COREX.DataTypes.Any', label="Width", required=False),
                PortSpec("height", "in", "data", 'COREX.DataTypes.Any', label="Height", required=False),
                PortSpec("font_size", "in", "data", 'COREX.DataTypes.Any', label="Font size", required=False),
                PortSpec("image", "out", "data", 'COREX.DataTypes.Any', label="Image"),
            ),
            properties=(
                PropertySpec(
                    "width",
                    "int",
                    600,
                    "Width",
                    minimum=2,
                    maximum=3840,
                    inline_editor="slider",
                ),
                PropertySpec("show_legend", "bool", False, "Show legend", inline_editor="toggle"),
                PropertySpec(
                    "font_size",
                    "int",
                    12,
                    "Font size",
                    minimum=1,
                    maximum=72,
                    inline_editor="slider",
                ),
            ),
            settings_groups=(
                SettingsGroupSpec(
                    group_id="general",
                    label="General Options",
                    items=(
                        SettingsGroupItemSpec(port_key="width", property_key="width"),
                        SettingsGroupItemSpec(port_key="height"),
                        SettingsGroupItemSpec(property_key="show_legend"),
                    ),
                ),
                SettingsGroupSpec(
                    group_id="plot",
                    label="Signal plot options",
                    items=(
                        SettingsGroupItemSpec(port_key="font_size", property_key="font_size"),
                    ),
                ),
            ),
        )

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


class _DeclarativePropertyProjectionNode:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id="tests.declarative_property_projection",
            display_name="Declarative Property Projection",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "mode",
                    "in",
                    "data",
                    'COREX.DataTypes.Any',
                    label="Mode",
                    required=False,
                    uses_property_default=True,
                ),
                PortSpec(
                    "sectors",
                    "in",
                    "data",
                    'COREX.DataTypes.Any',
                    label="Number of sectors",
                    required=False,
                    uses_property_default=True,
                ),
                PortSpec(
                    "result_bound",
                    "in",
                    "data",
                    'COREX.DataTypes.Any',
                    label="Result bound",
                    required=False,
                    uses_property_default=True,
                ),
                PortSpec("result", "out", "data", 'COREX.DataTypes.Any', label="Result"),
            ),
            properties=(
                PropertySpec(
                    "color_map",
                    "enum",
                    "Rainbow",
                    "Color map",
                    enum_values=("Rainbow", "Viridis"),
                    inline_editor="enum",
                    searchable=True,
                ),
                PropertySpec(
                    "mode",
                    "enum",
                    "None",
                    "Cyclic symmetry mode",
                    enum_values=("None", "Manual"),
                    inline_editor="enum",
                ),
                PropertySpec(
                    "sectors",
                    "int",
                    2,
                    "Number of sectors",
                    minimum=2,
                    maximum=360,
                    step=1.0,
                    inline_editor="slider",
                    enabled_when=PropertyConditionSpec("mode", ("Manual",)),
                ),
                PropertySpec(
                    "show_legend",
                    "bool",
                    False,
                    "Show legend",
                    inline_editor="toggle",
                ),
                PropertySpec(
                    "result_bound",
                    "interval_1d",
                    Interval1D(10.0, 0.0),
                    "Result bound",
                    minimum=0.0,
                    maximum=100.0,
                    step=0.001,
                    inline_editor="interval_slider",
                    interval_direction="decreasing",
                ),
            ),
            settings_groups=(
                SettingsGroupSpec(
                    group_id="general",
                    label="General",
                    items=(
                        SettingsGroupItemSpec(property_key="show_legend"),
                        SettingsGroupItemSpec(
                            port_key="sectors", property_key="sectors"
                        ),
                        SettingsGroupItemSpec(
                            port_key="result_bound", property_key="result_bound"
                        ),
                    ),
                ),
            ),
        )

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def test_grouped_node_width_measures_only_visible_rows() -> None:
    spec = _SettingsGroupProjectionNode().spec()
    long_label = "A deliberately long label belonging to a collapsed setting"
    spec = replace(
        spec,
        ports=tuple(replace(port, label=long_label) if port.key == "font_size" else port for port in spec.ports),
        properties=tuple(
            replace(prop, type="enum", inline_editor="enum", enum_values=(long_label,))
            if prop.key == "font_size" else prop for prop in spec.properties
        ),
    )
    model = GraphModel()
    node = model.add_node(model.active_workspace.workspace_id, spec.type_id, "Options", 0, 0)
    closed = node_surface_metrics(node, spec)
    node.expanded_settings_group_ids = ("plot",)
    opened = node_surface_metrics(node, spec)
    assert opened.default_width > closed.default_width
    assert closed.standard_left_label_width == opened.standard_left_label_width
    node.expanded_settings_group_ids = ()
    assert node_surface_metrics(node, spec).default_width == closed.default_width
    assert node_surface_metrics(node, spec, keep_expanded_node_width=True).default_width == opened.default_width


@pytest.mark.parametrize("type_id", ["plot.signal", "core.logger", "core.if", "tests.settings_group_projection"])
def test_ordinary_nodes_fit_contents_despite_saved_dimensions(type_id: str) -> None:
    registry = build_default_registry()
    registry.register(_SettingsGroupProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(workspace.workspace_id, type_id, "Content sizing", 40, 60)
    spec = registry.get_spec(type_id)
    builder = GraphScenePayloadBuilder()

    def payload():
        return builder.rebuild_models(
            model=model, registry=registry, workspace_id=workspace.workspace_id,
            scope_path=(), graph_theme_bridge=None,
        )[0][0]

    for expanded in ((), tuple(group.group_id for group in spec.settings_groups), ()):
        node.expanded_settings_group_ids = expanded
        node.custom_width = node.custom_height = None
        fitted = payload()
        node.custom_width, node.custom_height = 980, 1600
        oversized = payload()
        assert (oversized["width"], oversized["height"]) == (fitted["width"], fitted["height"])
        assert (oversized["x"], oversized["y"]) == (40, 60)
        assert oversized.get("settings_band") == fitted.get("settings_band")
        assert oversized["ports"] == fitted["ports"]
        for port in spec.ports:
            if port.direction == "out":
                assert surface_port_local_point(node, spec, port.key)[0] == oversized["width"]
        if spec.settings_groups:
            metrics = oversized["surface_metrics"]
            assert oversized["settings_band"]["top"] == (
                metrics["port_top"] + metrics["port_height"] + metrics["body_bottom_margin"]
            )

    compiled_spec = replace(spec, runtime_behavior="compile_only")
    assert resolved_node_surface_size(node, compiled_spec) == resolved_node_surface_size(node, spec)


@pytest.mark.parametrize("type_id", ["plot.signal", "tests.settings_group_projection"])
def test_keep_expanded_width_uses_full_settings_metrics_in_all_payload_paths(type_id: str) -> None:
    registry = build_default_registry()
    registry.register(_SettingsGroupProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id, type_id, "Options", 40, 60,
        properties=registry.default_properties(type_id),
    )
    original_properties = copy.deepcopy(node.properties)
    sink = model.add_node(workspace.workspace_id, "core.logger", "Sink", 900, 60)
    edge = model.add_edge(workspace.workspace_id, node.node_id, "image", sink.node_id, "message")
    spec = registry.resolve_spec(type_id, node.properties)
    keep_width = True
    builder = GraphScenePayloadBuilder(keep_expanded_node_width_provider=lambda: keep_width)
    common = dict(model=model, registry=registry, workspace_id=workspace.workspace_id, graph_theme_bridge=None)

    def full_payload():
        nodes, _backdrops, minimap, edges = builder.rebuild_partitioned_models(**common, scope_path=())
        payload = next(item for item in nodes if item["node_id"] == node.node_id)
        assert next(item for item in minimap if item["node_id"] == node.node_id)["width"] == payload["width"]
        metrics = payload["surface_metrics"]
        assert edges[0]["sx"] == node.x + payload["width"] - metrics["port_side_margin"] - metrics["port_dot_radius"]
        return payload

    # The first render is collapsed: width must not depend on a previous expansion.
    collapsed = full_payload()
    node.expanded_settings_group_ids = tuple(group.group_id for group in spec.settings_groups)
    expanded = full_payload()
    assert collapsed["width"] == expanded["width"]
    assert collapsed["height"] < expanded["height"]
    keep_width = False
    assert full_payload()["width"] == expanded["width"]
    node.expanded_settings_group_ids = ()
    fitted = full_payload()
    assert fitted["width"] <= collapsed["width"]
    if type_id == "plot.signal":
        assert fitted["width"] < collapsed["width"]
    assert fitted["height"] == collapsed["height"]
    keep_width = True
    targeted = builder.build_node_payloads_for_ids(**common, scope_path=(), node_ids={node.node_id})[0][0]
    connection = builder.build_node_connection_payloads_for_ids(**common, scope_path=(), node_ids={node.node_id})[node.node_id]
    added = builder.build_added_node_payloads_for_ids(**common, scope_path=(), node_ids={node.node_id})[0][0]
    preview = builder.build_library_preview_node_payload(**common, library_payload={"type_id": type_id, "display_name": "Options"})
    for payload in (targeted, connection, added, preview):
        assert (payload["width"], payload["height"]) == (collapsed["width"], collapsed["height"])
        assert payload["surface_metrics"] == collapsed["surface_metrics"]
    targeted_edge = builder.build_edge_payloads_for_ids(**common, scope_path=(), edge_ids={edge.edge_id})[0]
    metrics = collapsed["surface_metrics"]
    assert targeted_edge["sx"] == node.x + collapsed["width"] - metrics["port_side_margin"] - metrics["port_dot_radius"]
    assert builder._node_payload_factory.layout_bounds(node=node, spec=spec, workspace_nodes=workspace.nodes).width == collapsed["width"]
    assert node.properties == original_properties  # Includes plot output-image dimensions.
    assert (node.custom_width, node.custom_height) == (None, None)


@pytest.mark.parametrize("type_id", ["media.panel", "model.viewer", "tabular.input", "io.folder_explorer", "io.path_pointer"])
def test_dedicated_surfaces_preserve_manual_dimensions(type_id: str) -> None:
    registry = build_default_registry()
    spec = registry.get_spec(type_id)
    model = GraphModel()
    node = model.add_node(model.active_workspace.workspace_id, type_id, "Sized panel", 40, 60)
    node.custom_width, node.custom_height = 980, 1600
    assert resolved_node_surface_size(node, spec) == (980, 1600)
    stable_metrics = node_surface_metrics(node, spec, keep_expanded_node_width=True)
    assert stable_metrics == node_surface_metrics(node, spec)
    assert resolved_node_surface_size(node, spec, surface_metrics=stable_metrics) == (980, 1600)


def _settings_group_scene(*, expanded_group_ids: tuple[str, ...] = ()):
    registry = build_default_registry()
    registry.register(_SettingsGroupProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(workspace.workspace_id, "core.python_script", "Source", 0.0, 0.0)
    target = model.add_node(
        workspace.workspace_id,
        "tests.settings_group_projection",
        "Signal Plot",
        320.0,
        0.0,
        properties={"width": 600, "show_legend": False, "font_size": 12},
    )
    target.expanded_settings_group_ids = expanded_group_ids
    model.add_edge(workspace.workspace_id, source.node_id, "result", target.node_id, "width")
    model.add_edge(workspace.workspace_id, source.node_id, "result", target.node_id, "height")
    builder = GraphScenePayloadBuilder()
    node_payloads, _backdrops, _minimap, edge_payloads = builder.rebuild_partitioned_models(
        model=model,
        registry=registry,
        workspace_id=workspace.workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )
    connection_payload = builder.build_node_connection_payloads_for_ids(
        model=model,
        registry=registry,
        workspace_id=workspace.workspace_id,
        scope_path=(),
        node_ids={target.node_id},
        graph_theme_bridge=None,
    )[target.node_id]
    return (
        next(payload for payload in node_payloads if payload["node_id"] == source.node_id),
        next(payload for payload in node_payloads if payload["node_id"] == target.node_id),
        edge_payloads,
        connection_payload,
    )


def test_full_scene_build_freezes_one_presentation_record_per_node_and_reuses_edge_anchors() -> None:
    registry, model, workspace, nodes, _edges = _chain_scene()
    builder = GraphScenePayloadBuilder()
    factory = builder._node_payload_factory
    built_facts = []
    original_build = factory.build_presentation_facts

    def capture_facts(**kwargs):  # noqa: ANN003, ANN202
        facts = original_build(**kwargs)
        built_facts.append(facts)
        return facts

    with (
        mock.patch.object(factory, "build_presentation_facts", side_effect=capture_facts) as facts_spy,
        mock.patch.object(route_payload, "port_scene_pos", wraps=route_payload.port_scene_pos) as fallback_spy,
    ):
        node_payloads, backdrop_payloads, minimap_payloads, edge_payloads = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )

    assert facts_spy.call_count == len(nodes)
    assert fallback_spy.call_count == 0
    assert len(node_payloads) == len(nodes)
    assert backdrop_payloads == []
    assert len(minimap_payloads) == len(nodes)
    assert len(edge_payloads) == 2
    assert {facts.original_node.node_id for facts in built_facts} == {node.node_id for node in nodes}
    assert all(facts.payload_node.node_id == facts.final_node.node_id for facts in built_facts)
    assert all(facts.bounds == facts.minimap_bounds for facts in built_facts)
    with pytest.raises(FrozenInstanceError):
        built_facts[0].width = 1.0
    with pytest.raises(TypeError):
        built_facts[0].visible_port_by_key["new"] = next(iter(built_facts[0].visible_ports))


def test_targeted_node_and_edge_builds_create_only_invocation_local_presentation_mappings() -> None:
    registry, model, workspace, nodes, edges = _chain_scene()
    builder = GraphScenePayloadBuilder()
    factory = builder._node_payload_factory

    with mock.patch.object(
        factory,
        "build_presentation_facts",
        wraps=factory.build_presentation_facts,
    ) as facts_spy:
        node_payloads, backdrop_payloads, minimap_payloads = builder.build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids={nodes[0].node_id, nodes[1].node_id},
            graph_theme_bridge=None,
        )

    assert facts_spy.call_count == 2
    assert len(node_payloads) == 2
    assert backdrop_payloads == []
    assert len(minimap_payloads) == 2

    expected_connection_payloads = {
        payload["node_id"]: {
            key: payload[key]
            for key in (
                "ports",
                "inline_properties",
                "surface_metrics",
                "width",
                "height",
            )
        }
        for payload in node_payloads
    }
    with (
        mock.patch.object(
            factory,
            "build_presentation_facts",
            wraps=factory.build_presentation_facts,
        ) as facts_spy,
        mock.patch.object(
            factory,
            "view_visible_ports",
            wraps=factory.view_visible_ports,
        ) as visible_ports_spy,
    ):
        connection_payloads = builder.build_node_connection_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids={nodes[0].node_id, nodes[1].node_id},
            graph_theme_bridge=None,
        )

    assert facts_spy.call_count == 0
    assert visible_ports_spy.call_count == 2
    assert connection_payloads == expected_connection_payloads

    with mock.patch.object(
        factory,
        "build_presentation_facts",
        wraps=factory.build_presentation_facts,
    ) as facts_spy:
        edge_payloads = builder.build_edge_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            edge_ids={edges[0].edge_id},
            graph_theme_bridge=None,
        )

    assert facts_spy.call_count == len(nodes)
    assert [payload["edge_id"] for payload in edge_payloads] == [edges[0].edge_id]
    assert not hasattr(builder, "presentation_facts_by_node_id")


def test_named_settings_groups_project_collapsed_and_expanded_port_anchors_without_topology_changes() -> None:
    def bottom_clearance(payload: dict[str, object]) -> float:
        groups = payload["settings_groups"]
        band = payload["settings_band"]
        content_bottom = max(
            [
                group["header"]["y"] + group["header"]["height"]
                for group in groups
            ]
            + [
                item["y"] + item["height"]
                for group in groups
                for item in group["items"]
                if item["visible"]
            ]
        )
        return band["top"] + band["height"] - content_bottom

    source_payload, collapsed_payload, collapsed_edges, connection_payload = _settings_group_scene()

    assert "settings_groups" not in source_payload
    assert "settings_band" not in source_payload
    assert all("presentation_anchor" not in port for port in source_payload["ports"])
    assert [group["group_id"] for group in collapsed_payload["settings_groups"]] == ["general", "plot"]
    assert collapsed_payload["settings_band"]["height"] > 0.0
    assert bottom_clearance(collapsed_payload) == pytest.approx(18.0)
    assert collapsed_payload["port_presentation"]["total_row_count"] == 1
    assert collapsed_payload["inline_properties"] == []

    general_group = collapsed_payload["settings_groups"][0]
    paired_item = general_group["items"][0]
    assert paired_item["kind"] == "paired"
    assert paired_item["property"]["key"] == "width"
    assert paired_item["property"]["overridden_by_input"] is True
    assert paired_item["height"] > 0.0
    assert connection_payload["settings_groups"] == collapsed_payload["settings_groups"]
    collapsed_ports = {port["key"]: port for port in collapsed_payload["ports"]}
    assert collapsed_ports["width"]["settings_property_key"] == "width"
    assert collapsed_ports["width"]["handle_visible"] is False
    assert collapsed_ports["height"]["handle_visible"] is False
    assert collapsed_ports["width"]["presentation_anchor"] == collapsed_ports["height"]["presentation_anchor"]
    assert "settings_group_id" not in collapsed_ports["image"]
    assert collapsed_ports["image"]["layout_row"] == 0
    collapsed_target_points = {
        (edge["tx"], edge["ty"])
        for edge in collapsed_edges
        if edge["target_port_key"] in {"width", "height"}
    }
    assert len(collapsed_target_points) == 1

    _source_payload, expanded_payload, expanded_edges, _connection_payload = _settings_group_scene(
        expanded_group_ids=("general",)
    )
    expanded_ports = {port["key"]: port for port in expanded_payload["ports"]}
    assert expanded_payload["settings_groups"][0]["expanded"] is True
    assert expanded_payload["settings_groups"][1]["expanded"] is False
    assert bottom_clearance(expanded_payload) == pytest.approx(18.0)
    assert expanded_ports["width"]["handle_visible"] is True
    assert expanded_ports["height"]["handle_visible"] is True
    assert expanded_ports["font_size"]["handle_visible"] is False
    assert expanded_ports["width"]["presentation_anchor"] != expanded_ports["height"]["presentation_anchor"]
    assert expanded_ports["image"] == collapsed_ports["image"]
    expanded_target_points = {
        (edge["target_port_key"], edge["tx"], edge["ty"])
        for edge in expanded_edges
        if edge["target_port_key"] in {"width", "height"}
    }
    assert len({(tx, ty) for _key, tx, ty in expanded_target_points}) == 2


def test_property_default_projects_on_the_input_and_is_removed_from_body_rows() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(workspace.workspace_id, "core.logger", "Logger", 0.0, 0.0)

    node_payloads, _backdrops, _minimap, _edges = (
        GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
    )

    payload = next(item for item in node_payloads if item["node_id"] == node.node_id)
    message_port = next(port for port in payload["ports"] if port["key"] == "message")
    assert message_port["flow_state"] == "default"
    assert message_port["default_property"]["key"] == "message"
    assert message_port["default_property"]["value"] == "log message"
    assert message_port["default_property"]["inline_editor"] == "text"
    assert message_port["default_property"]["overridden_by_input"] is False
    assert [item["key"] for item in payload["inline_properties"]] == ["level"]
    assert "locked" not in message_port
    assert "lockable" not in message_port


def test_common_property_projection_covers_ordinary_grouped_and_default_rows() -> None:
    registry = build_default_registry()
    registry.register(_DeclarativePropertyProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "tests.declarative_property_projection",
        "Controls",
        0.0,
        0.0,
        properties={"result_bound": Interval1D(10.0, 0.0)},
    )
    node.expanded_settings_group_ids = ("general",)

    node_payloads, _backdrops, _minimap, _edges = (
        GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
    )
    payload = next(item for item in node_payloads if item["node_id"] == node.node_id)
    ordinary = next(
        item for item in payload["inline_properties"] if item["key"] == "color_map"
    )
    grouped = next(
        item["property"]
        for item in payload["settings_groups"][0]["items"]
        if item["property_key"] == "show_legend"
    )
    ports = {port["key"]: port for port in payload["ports"]}
    interval_default = ports["result_bound"]["default_property"]
    conditional_default = ports["sectors"]["default_property"]
    group_items = payload["settings_groups"][0]["items"]
    scalar_default_item = next(
        item for item in group_items if item["port_key"] == "sectors"
    )
    interval_default_item = next(
        item for item in group_items if item["port_key"] == "result_bound"
    )
    required_fields = {
        "value",
        "display_value",
        "display_value_available",
        "overridden_by_input",
        "condition_enabled",
        "editor_enabled",
        "searchable",
    }

    assert required_fields <= ordinary.keys()
    assert required_fields <= grouped.keys()
    assert required_fields <= interval_default.keys()
    assert ordinary["searchable"] is True
    assert grouped["display_value"] is False
    assert grouped["editor_enabled"] is True
    assert interval_default["value"] == {"start": 10.0, "end": 0.0}
    assert interval_default["display_value"] == {"start": 10.0, "end": 0.0}
    assert interval_default["interval_direction"] == "decreasing"
    assert interval_default["minimum"] == 0.0
    assert interval_default["maximum"] == 100.0
    assert interval_default["step"] == 0.001
    assert conditional_default["condition_enabled"] is False
    assert conditional_default["editor_enabled"] is False
    assert conditional_default["editor_disabled_reason"] == (
        "Available when Cyclic symmetry mode is Manual."
    )
    assert payload["properties"]["result_bound"] == {"start": 10.0, "end": 0.0}
    expected_slider_height = standard_inline_property_row_height(
        "slider", graph_label_pixel_size=10
    )
    expected_interval_height = standard_inline_property_row_height(
        "interval_slider", graph_label_pixel_size=10
    )
    assert standard_inline_property_row_height(
        "list", graph_label_pixel_size=10, list_value=[]
    ) == 56.0
    assert standard_inline_property_row_height(
        "list", graph_label_pixel_size=10, list_value=["A"]
    ) == 84.0
    assert standard_inline_property_row_height(
        "list", graph_label_pixel_size=10, list_value=["A", "B", "C"]
    ) == 146.0
    assert standard_inline_property_row_height(
        "list", graph_label_pixel_size=10, list_value=["A", "B", "C", "D"]
    ) == 146.0
    assert standard_inline_property_row_height(
        "interval_fields", graph_label_pixel_size=10
    ) > standard_inline_property_row_height("toggle", graph_label_pixel_size=10)
    assert scalar_default_item["property_key"] == ""
    assert interval_default_item["property_key"] == ""
    assert "property" not in scalar_default_item
    assert "property" not in interval_default_item
    assert scalar_default_item["height"] == expected_slider_height
    assert interval_default_item["height"] == expected_interval_height
    for previous, following in zip(group_items, group_items[1:]):
        assert following["y"] >= previous["y"] + previous["height"]
    settings_bottom = (
        payload["settings_band"]["top"] + payload["settings_band"]["height"]
    )
    assert interval_default_item["y"] + interval_default_item["height"] <= settings_bottom
    assert payload["height"] >= settings_bottom


def test_disabled_edge_does_not_override_and_disconnect_restores_authored_condition_value() -> None:
    registry = build_default_registry()
    registry.register(_DeclarativePropertyProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    source = mutations.add_node(
        type_id="core.python_script", title="Source", x=0.0, y=0.0
    )
    target = mutations.add_node(
        type_id="tests.declarative_property_projection",
        title="Controls",
        x=300.0,
        y=0.0,
    )
    mutations.set_node_property(target.node_id, "mode", "Manual")
    edge = mutations.add_edge(
        source_node_id=source.node_id,
        source_port_key="result",
        target_node_id=target.node_id,
        target_port_key="mode",
    )
    builder = GraphScenePayloadBuilder()

    def projected_defaults() -> tuple[dict[str, object], dict[str, object]]:
        nodes, _backdrops, _minimap, _edges = builder.rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
        payload = next(item for item in nodes if item["node_id"] == target.node_id)
        ports = {port["key"]: port for port in payload["ports"]}
        return ports["mode"]["default_property"], ports["sectors"]["default_property"]

    connected_mode, connected_sectors = projected_defaults()
    assert connected_mode["value"] == "Manual"
    assert connected_mode["display_value_available"] is False
    assert connected_mode["overridden_by_input"] is True
    assert connected_sectors["condition_enabled"] is False

    mutations.set_edge_enabled(edge.edge_id, False)
    disabled_mode, disabled_sectors = projected_defaults()
    assert disabled_mode["value"] == "Manual"
    assert disabled_mode["display_value"] == "Manual"
    assert disabled_mode["display_value_available"] is True
    assert disabled_mode["overridden_by_input"] is False
    assert disabled_sectors["condition_enabled"] is True
    assert disabled_sectors["editor_enabled"] is True

    mutations.move_edge_endpoint(edge.edge_id, "target", "", "")
    disconnected_mode, disconnected_sectors = projected_defaults()
    assert disconnected_mode == disabled_mode
    assert disconnected_sectors == disabled_sectors
    assert target.properties["mode"] == "Manual"


def test_upstream_interval_display_refresh_never_mutates_authored_serialization() -> None:
    registry = build_default_registry()
    registry.register(_DeclarativePropertyProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id, "core.python_script", "Source", 0.0, 0.0
    )
    target = model.add_node(
        workspace.workspace_id,
        "tests.declarative_property_projection",
        "Controls",
        300.0,
        0.0,
        properties={"result_bound": Interval1D(10.0, 0.0)},
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "result",
        target.node_id,
        "result_bound",
    )
    nodes, _backdrops, _minimap, edges = (
        GraphScenePayloadBuilder().rebuild_partitioned_models(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
    )
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    undo_depth_before = history.undo_depth(workspace.workspace_id)
    assert undo_depth_before == 0
    before = node_instance_to_mapping(target)
    output_record = {
        "observed_at_epoch_ms": 1.0,
        "outputs": {
            "result": SettledPortResult(
                status="value", value=DataTree.from_item(Interval1D(0.0, 10.0))
            )
        },
        "stale": False,
    }

    first = resolve_runtime_property_presentations(
        node_payloads=nodes,
        edge_payloads=edges,
        output_records_by_node={source.node_id: {"run": output_record}},
    )[target.node_id]["result_bound"]
    assert first["value"] == {"start": 10.0, "end": 0.0}
    assert first["display_value"] == {"start": 0.0, "end": 10.0}
    assert first["interval_direction"] == "decreasing"
    assert history.undo_depth(workspace.workspace_id) == undo_depth_before

    output_record["outputs"]["result"] = SettledPortResult(
        status="value", value=DataTree.from_item(Interval1D(5.0, 5.0))
    )
    refreshed = resolve_runtime_property_presentations(
        node_payloads=nodes,
        edge_payloads=edges,
        output_records_by_node={source.node_id: {"run": output_record}},
    )[target.node_id]["result_bound"]
    assert history.undo_depth(workspace.workspace_id) == undo_depth_before
    disabled_edges = [dict(edge) for edge in edges]
    disabled_edges[0]["enabled"] = False
    disabled_restored = resolve_runtime_property_presentations(
        node_payloads=nodes,
        edge_payloads=disabled_edges,
        output_records_by_node={source.node_id: {"run": output_record}},
    )[target.node_id]["result_bound"]
    restored = resolve_runtime_property_presentations(
        node_payloads=nodes,
        edge_payloads=[],
        output_records_by_node={source.node_id: {"run": output_record}},
    )[target.node_id]["result_bound"]

    assert refreshed["display_value"] == {"start": 5.0, "end": 5.0}
    assert disabled_restored["display_value"] == {"start": 10.0, "end": 0.0}
    assert disabled_restored["overridden_by_input"] is False
    assert restored["display_value"] == {"start": 10.0, "end": 0.0}
    assert restored["overridden_by_input"] is False
    assert node_instance_to_mapping(target) == before
    assert history.undo_depth(workspace.workspace_id) == undo_depth_before


def test_direct_ports_payload_fallback_uses_enabled_edge_projection() -> None:
    registry = build_default_registry()
    registry.register(_DeclarativePropertyProjectionNode)
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "core.python_script",
        "Source",
        -300.0,
        0.0,
    )
    node = model.add_node(
        workspace.workspace_id,
        "tests.declarative_property_projection",
        "Controls",
        0.0,
        0.0,
        properties={"result_bound": Interval1D(10.0, 0.0)},
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "result",
        node.node_id,
        "result_bound",
    )
    builder = GraphScenePayloadBuilder()

    ports = builder._node_payload_factory.build_ports_payload(
        node=node,
        spec=registry.get_spec(node.type_id),
        workspace=workspace,
        workspace_nodes=dict(workspace.nodes),
        port_connection_counts={(node.node_id, "result_bound"): 1},
        hide_optional_ports=False,
    )

    interval = next(port for port in ports if port["key"] == "result_bound")
    assert interval["default_property"]["value"] == {
        "start": 10.0,
        "end": 0.0,
    }
    assert interval["default_property"]["display_value_available"] is False
    assert interval["default_property"]["overridden_by_input"] is True
