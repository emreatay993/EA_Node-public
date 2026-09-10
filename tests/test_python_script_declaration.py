from __future__ import annotations

from dataclasses import replace

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.python_script_declaration import PythonScriptDeclarationError
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.spec_validation import validate_node_spec
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import Interval1D
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory


def _resolve(source: str):
    registry = build_builtin_registry()
    properties = registry.normalize_properties(
        "core.python_script",
        {"script": source},
    )
    return registry, properties, registry.resolve_spec("core.python_script", properties)


def test_canvas_port_handles_edit_declarations_and_signature_without_rewriting_body() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    mutations = ValidatedGraphMutation(model, model.active_workspace.workspace_id, registry)
    source = '''# Keep café and formatting.
@corex.node
@corex.input("payload", value_type=float, required=True, section="Data")  # keep me
@corex.output("result", value_type=float)
@corex.slider("scale", default=2.0, minimum=0.0, maximum=5.0, port=True, section="Style")
def run(ctx, payload: float, scale,):  # signature comment
    # Keep this logic even when an interface change needs a manual body edit.
    return {"result": payload * scale}
'''
    node = mutations.add_node(type_id="core.python_script", title="Script", x=0, y=0,
                              properties={"script": source})
    mutations.set_node_property(node.node_id, "scale", 3.0)
    before_spec = registry.resolve_spec(node.type_id, node.properties)
    assert [group.group_id for group in before_spec.dynamic_port_groups] == ["inputs", "outputs"]
    assert mutations.insert_dynamic_port(node.node_id, "inputs", 0) == "input1"
    assert mutations.insert_dynamic_port(node.node_id, "outputs", 1) == "output1"
    edited = node.properties["script"]
    assert '@corex.input("input1", value_type=corex.Any)' in edited
    assert '@corex.output("output1", value_type=corex.Any)' in edited
    assert 'def run(ctx, payload: float, scale, input1,):  # signature comment' in edited
    assert source.split("    # Keep this logic", 1)[1] == edited.split("    # Keep this logic", 1)[1]
    assert node.properties["scale"] == 3.0
    assert registry.resolve_spec(node.type_id, node.properties).settings_groups == before_spec.settings_groups
    mutations.remove_dynamic_port(node.node_id, "inputs", "input1")
    mutations.remove_dynamic_port(node.node_id, "outputs", "output1")
    mutations.remove_dynamic_port(node.node_id, "inputs", "payload")
    assert '@corex.input("payload"' not in node.properties["script"]
    assert 'return {"result": payload * scale}' in node.properties["script"]
    assert set(node.properties) == {"script", "timeout_sec", "scale"}


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_canvas_port_source_spans_preserve_multiline_unicode_and_parentheses(newline: str) -> None:
    source = '''# café
@corex.node
@(
    corex.input("payload", value_type=float, label="é")
)  # retain trailing comment
@(corex.output("result", value_type=float))
@corex.number("input1", default=2)
def run(
    ctx,
    payload: "é", # retain parameter comment, too
    input1,
):
    return {"result": payload * input1}
'''.replace("\n", newline)
    registry = build_builtin_registry()
    model = GraphModel()
    mutation = ValidatedGraphMutation(model, model.active_workspace.workspace_id, registry)
    node = mutation.add_node(type_id="core.python_script", title="Script", x=0, y=0,
                             properties={"script": source})
    assert mutation.insert_dynamic_port(node.node_id, "inputs", 0) == "input2"
    mutation.remove_dynamic_port(node.node_id, "inputs", "payload")
    mutation.remove_dynamic_port(node.node_id, "outputs", "result")
    updated = node.properties["script"]
    assert "# retain trailing comment" in updated
    assert "# retain parameter comment, too" in updated
    assert f'    return {{"result": payload * input1}}{newline}' in updated
    assert 'value_type=float' not in updated
    assert [port.key for port in registry.resolve_spec(node.type_id, node.properties).ports] == ["input2"]


def test_source_backed_group_validation_and_mutations_keep_backing_write_guards() -> None:
    registry = build_builtin_registry()
    properties = registry.default_properties("core.python_script")
    spec = registry.resolve_spec("core.python_script", properties)
    group = spec.dynamic_port_groups[0]
    port = spec.ports[0]
    bad_group = replace(group, ports_resolver=lambda _properties: (port, port))
    with pytest.raises(ValueError, match="duplicate port key"):
        validate_node_spec(replace(spec, dynamic_port_groups=(bad_group,)), data_types=registry.data_types)
    bad_group = replace(group, property_editor="untrusted")
    with pytest.raises(TypeError, match="must be callable"):
        validate_node_spec(replace(spec, dynamic_port_groups=(bad_group,)), data_types=registry.data_types)

    base = registry.get_spec("core.python_script")
    custom = replace(spec, type_id="tests.source_backed", instance_spec_resolver=base.instance_spec_resolver)
    registry.register_descriptor(custom, lambda: None)
    model = GraphModel()
    mutation = ValidatedGraphMutation(model, model.active_workspace.workspace_id, registry)
    node = mutation.add_node(type_id=custom.type_id, title="Source", x=0, y=0, properties=properties)
    with pytest.raises(ValueError, match="only through dynamic port mutations"):
        mutation.set_node_property(node.node_id, "script", properties["script"])
    assert mutation.insert_dynamic_port(node.node_id, "inputs", 0) == "input1"
    assert mutation.remove_dynamic_port(node.node_id, "inputs", "input1") == ("input1", ())
    assert [p.key for p in registry.resolve_spec(node.type_id, node.properties).ports] == ["payload", "result"]


def test_canvas_port_edits_execute_and_undo_source_wires_and_port_state_together() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    node_id = scene.add_node_from_type("core.python_script", 0, 0)
    peer_id = scene.add_node_from_type("core.python_script", 300, 0)
    assert scene.insert_dynamic_port(node_id, "inputs", 1) == "input1"
    assert scene.insert_dynamic_port(node_id, "outputs", 1) == "output1"
    node = workspace.nodes[node_id]
    ctx = ExecutionContext(run_id="test", node_id=node_id, workspace_id=workspace.workspace_id,
                           inputs={"payload": 42, "input1": 9}, properties=node.properties,
                           emit_log=lambda *_args: None)
    assert registry.create(node.type_id).execute(ctx).outputs == {"result": 42}
    input_edge = scene.add_edge(peer_id, "result", node_id, "input1")
    output_edge = scene.add_edge(node_id, "output1", peer_id, "payload")
    scene.set_port_modifiers(node_id, "input1", ["graft"])
    scene.set_principal_input_port(node_id, "input1")
    for group_id, port_key, edge_id in (("inputs", "input1", input_edge), ("outputs", "output1", output_edge)):
        before = history.capture_workspace(workspace)
        depth = history.undo_depth(workspace.workspace_id)
        result = scene.remove_dynamic_port(node_id, group_id, port_key)
        assert result["removed_edge_ids"] == [edge_id]
        assert edge_id not in workspace.edges
        assert history.undo_depth(workspace.workspace_id) == depth + 1
        after = history.capture_workspace(workspace)
        history.undo_workspace(workspace.workspace_id, workspace)
        assert history.capture_workspace(workspace) == before
        history.redo_workspace(workspace.workspace_id, workspace)
        assert history.capture_workspace(workspace) == after
    ctx.properties = workspace.nodes[node_id].properties
    assert registry.create(node.type_id).execute(ctx).outputs == {"result": 42}


def test_all_python_script_decorators_resolve_to_shared_metadata() -> None:
    source = """@corex.node
@corex.input("values", value_type=float, structure="tree", required=True, section="Data")
@corex.input("image", value_type=corex.Image)
@corex.output("result", value_type="COREX.DataTypes.String")
@corex.text("title", default="Plot", section="Style", port=True)
@corex.number("count", default=2, section="Style")
@corex.switch("enabled", default=True, section="Style", port=True)
@corex.dropdown("mode", default=1, options=("Mean", "Max"), codes=(0, 1), section="Style", port=True)
@corex.slider("width", default=2.0, minimum=0.5, maximum=8.0, step=0.5, section="Style", port=True)
@corex.color("accent", default="#336699", section="Style")
@corex.path("folder", default="", file_filter="All files (*)", section="Files", port=True)
@corex.text_area("notes", default="", section="Files")
@corex.interval("bounds", default=(0.0, 1.0), section="Ranges", port=True)
@corex.list("labels", default=["A"], item_type=str, section="Data", port=True)
def run(ctx, values, image, title, count, enabled, mode, width, accent, folder, notes, bounds, labels):
    return {"result": title}
"""
    _registry, properties, spec = _resolve(source)

    assert [port.key for port in spec.ports] == [
        "values",
        "image",
        "result",
        "title",
        "enabled",
        "mode",
        "width",
        "folder",
        "bounds",
        "labels",
    ]
    assert [prop.key for prop in spec.properties] == [
        "script",
        "timeout_sec",
        "title",
        "count",
        "enabled",
        "mode",
        "width",
        "accent",
        "folder",
        "notes",
        "bounds",
        "labels",
    ]
    assert properties["bounds"] == Interval1D(0.0, 1.0)
    assert [(group.group_id, group.label) for group in spec.settings_groups] == [
        ("data", "Data"),
        ("style", "Style"),
        ("files", "Files"),
        ("ranges", "Ranges"),
    ]


def test_python_script_labels_preserve_explicit_blank_and_derive_omitted() -> None:
    source = '''@corex.node
@corex.input("omitted_input", value_type=corex.Any)
@corex.input("blank_input", value_type=corex.Any, label="")
@corex.output("omitted_output", value_type=corex.Any)
@corex.output("blank_output", value_type=corex.Any, label="")
@corex.text("omitted_control")
@corex.text("blank_control", label="")
def run(ctx, omitted_input, blank_input, omitted_control, blank_control):
    return {}
'''

    _registry, _properties, spec = _resolve(source)
    ports = {port.key: port for port in spec.ports}
    properties = {prop.key: prop for prop in spec.properties}

    assert ports["omitted_input"].label == "Omitted Input"
    assert ports["blank_input"].label == ""
    assert ports["omitted_output"].label == "Omitted Output"
    assert ports["blank_output"].label == ""
    assert properties["omitted_control"].label == "Omitted Control"
    assert properties["blank_control"].label == ""


@pytest.mark.parametrize("direction", ("input", "output"))
def test_python_script_port_types_require_explicit_source_located_declarations(
    direction: str,
) -> None:
    parameters = "ctx, value" if direction == "input" else "ctx"
    source = f'''@corex.node
@corex.{direction}("value")
def run({parameters}): return {{}}
'''
    with pytest.raises(PythonScriptDeclarationError, match="requires explicit value_type=") as caught:
        _resolve(source)
    assert "line 2, column 2" in str(caught.value)
    explicit_source = source.replace('(\"value\")', '(\"value\", value_type=corex.Any)')
    _registry, _properties, spec = _resolve(explicit_source)
    assert spec.ports[0].data_type == "COREX.DataTypes.Any"


def test_decorator_discovery_rejects_expressions_without_executing_them() -> None:
    source = """
def explode():
    raise AssertionError("must not run")

@corex.node
@corex.text("title", default=explode())
def run(ctx, title):
    return {}
"""
    registry = build_builtin_registry()
    with pytest.raises(PythonScriptDeclarationError, match="must be literals"):
        registry.normalize_properties("core.python_script", {"script": source})


def test_decorator_discovery_bounds_source_size() -> None:
    registry = build_builtin_registry()
    source = "#" * (256 * 1024 + 1)
    with pytest.raises(PythonScriptDeclarationError, match="too large"):
        registry.normalize_properties("core.python_script", {"script": source})


def test_numeric_overflow_is_line_aware_and_apply_is_atomic() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script", title="Script", x=0.0, y=0.0
    )
    before = node.clone()
    huge = "9" * 400
    source = f"""@corex.node
@corex.slider("scale", default={huge}, minimum=0.0, maximum=1.0)
def run(ctx, scale):
    return {{}}
"""

    with pytest.raises(PythonScriptDeclarationError, match="line") as caught:
        mutations.apply_python_script(node.node_id, source)

    assert "column" in str(caught.value)
    assert node == before


@pytest.mark.parametrize(
    ("source", "message"),
    (
        (
            "@corex.node\n@corex.input('value', value_type=corex.Any)\ndef run(ctx):\n    return {}\n",
            "exactly match",
        ),
        (
            "@corex.node\n@corex.unknown('value')\ndef run(ctx):\n    return {}\n",
            "Unknown corex decorator",
        ),
        (
            "@corex.node\n@corex.output('value', value_type=corex.Any, section='Bad')\ndef run(ctx):\n    return {}\n",
            "does not support section",
        ),
        (
            "@corex.node\nasync def run(ctx):\n    return {}\n",
            "must be synchronous",
        ),
    ),
)
def test_invalid_declarations_have_actionable_source_errors(
    source: str,
    message: str,
) -> None:
    registry = build_builtin_registry()
    with pytest.raises(PythonScriptDeclarationError, match=message) as caught:
        registry.normalize_properties("core.python_script", {"script": source})
    assert "line" in str(caught.value)
    assert "column" in str(caught.value)


def test_registered_type_id_validation_runs_after_literal_parsing() -> None:
    source = """@corex.node
@corex.output("value", value_type="Missing.Type")
def run(ctx):
    return {}
"""
    registry = build_builtin_registry()
    with pytest.raises(ValueError, match="unknown data-type ID"):
        registry.normalize_properties("core.python_script", {"script": source})


@pytest.mark.parametrize(
    "decorator",
    (
        '@corex.text("value", _port_description="Private")',
        '@corex.text("value", _section_order=0)',
        '@corex.interval("value", _persistence_type=None)',
        '@corex.text("value", _port_required=True)',
        '@corex.text("value", _port_label="")',
        '@corex.text("value", _port_structure="tree")',
        '@corex.text("value", _port_uses_property_default=False)',
        '@corex.text("value", _port_value_type="COREX.DataTypes.Any")',
        '@corex.text("value", _port_accepted_data_types=("COREX.DataTypes.Any",))',
        '@corex.text("value", _property_type="json")',
        '@corex.text("value", _property_default={})',
        '@corex.text("value", _inline_editor="secret")',
        '@corex.text("value", _inspector_editor="secret")',
        '@corex.text("value", _inspector_visible=False)',
        '@corex.text("value", _property_group="Internal")',
        '@corex.text("value", _sensitive=True)',
        '@corex.text("value", _sensitive_scope_key="scope")',
        '@corex.input("value", value_type=corex.Any, _accepted_data_types=("COREX.DataTypes.Any",))',
    ),
)
def test_python_script_rejects_internal_control_fields(decorator: str) -> None:
    source = f'''@corex.node
{decorator}
def run(ctx, value):
    return {{}}
'''

    registry = build_builtin_registry()
    with pytest.raises(
        PythonScriptDeclarationError,
        match="Private decorator field .* is reserved for internal built-ins",
    ):
        registry.normalize_properties("core.python_script", {"script": source})


def test_python_script_rejects_internal_node_readiness_metadata() -> None:
    source = '''@corex.node(_readiness_requirements=())
@corex.output("result", value_type=corex.Any)
def run(ctx):
    return {}
'''
    registry = build_builtin_registry()
    with pytest.raises(
        PythonScriptDeclarationError,
        match="@corex.node does not accept arguments",
    ):
        registry.normalize_properties("core.python_script", {"script": source})


@pytest.mark.parametrize(
    "field",
    (
        "_collapsible=False",
        '_property_output_collisions=("value",)',
        '_surface_family="viewer"',
        '_surface_variant="embedded"',
        '_render_quality_tiers=("full", "proxy")',
    ),
)
def test_python_script_rejects_internal_node_surface_metadata(field: str) -> None:
    source = f'''@corex.node({field})
@corex.output("result", value_type=corex.Any)
def run(ctx):
    return {{}}
'''
    registry = build_builtin_registry()
    with pytest.raises(
        PythonScriptDeclarationError,
        match="@corex.node does not accept arguments",
    ):
        registry.normalize_properties("core.python_script", {"script": source})


def test_apply_is_atomic_and_reconciles_values_wires_and_structure() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    source_node = mutations.add_node(
        type_id="core.python_script", title="Source", x=0.0, y=0.0
    )
    target_node = mutations.add_node(
        type_id="core.python_script", title="Target", x=300.0, y=0.0
    )
    edge = mutations.add_edge(
        source_node_id=source_node.node_id,
        source_port_key="result",
        target_node_id=target_node.node_id,
        target_port_key="payload",
    )
    item_source = """@corex.node
@corex.input("payload", value_type=corex.Any)
@corex.output("result", value_type=corex.Any)
@corex.slider("scale", default=2.0, minimum=0.5, maximum=8.0, step=0.5, section="Style")
def run(ctx, payload, scale):
    return {"result": payload}
"""
    assert mutations.apply_python_script(target_node.node_id, item_source) == ((), ())
    assert edge.edge_id in workspace.edges
    mutations.set_node_property(target_node.node_id, "scale", 7.0)

    narrowed_source = item_source.replace("maximum=8.0", "maximum=5.0")
    reset_keys, removed_edge_ids = mutations.apply_python_script(
        target_node.node_id,
        narrowed_source,
    )
    assert reset_keys == ("scale",)
    assert removed_edge_ids == ()
    assert target_node.properties["scale"] == 2.0

    before_node = target_node.clone()
    before_edges = dict(workspace.edges)
    with pytest.raises(PythonScriptDeclarationError):
        mutations.apply_python_script(target_node.node_id, "@corex.node\ndef run(")
    assert target_node == before_node
    assert workspace.edges == before_edges

    tree_source = narrowed_source.replace(
        '@corex.input("payload", value_type=corex.Any)',
        '@corex.input("payload", value_type=corex.Any, structure="tree")',
    )
    assert mutations.set_port_modifiers(target_node.node_id, "payload", ("graft",))
    assert mutations.set_principal_input_port(target_node.node_id, "payload")
    before_node = target_node.clone()
    before_edges = dict(workspace.edges)
    with pytest.raises(ValueError, match="cannot be mixed"):
        mutations.set_node_properties(
            target_node.node_id,
            {"script": tree_source, "scale": 3.0},
        )
    assert target_node == before_node
    assert workspace.edges == before_edges

    assert mutations.set_node_properties(
        target_node.node_id,
        {"script": tree_source},
    ) == {"script": tree_source}
    removed_edge_ids = tuple(set(before_edges) - set(workspace.edges))
    assert removed_edge_ids == (edge.edge_id,)
    assert edge.edge_id not in workspace.edges
    assert target_node.port_modifiers == {}
    assert target_node.principal_input_port_id is None


def test_scene_bulk_apply_and_decorator_section_toggle_use_production_routes() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script", title="Script", x=0.0, y=0.0
    )
    source = """@corex.node
@corex.output("result", value_type=str)
@corex.text("title", default="Plot", section="Style")
def run(ctx, title):
    return {"result": title}
"""
    mutations.apply_python_script(node.node_id, source)
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)

    before = node.clone()
    with pytest.raises(ValueError, match="cannot be mixed"):
        scene.set_node_properties(
            node.node_id,
            {"script": source.replace("Plot", "Chart"), "timeout_sec": 1.0},
        )
    assert node == before
    assert scene.set_node_settings_group_expanded(node.node_id, "style", True)
    assert node.expanded_settings_group_ids == ("style",)

    document = JsonProjectSerializer(registry).to_persistent_document(model.project)
    saved_node = document["workspaces"][0]["nodes"][0]
    assert saved_node["expanded_settings_group_ids"] == ["style"]


def test_fragment_copy_preserves_decorator_section_expansion() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script", title="Script", x=0.0, y=0.0
    )
    source = """@corex.node
@corex.output("result", value_type=str)
@corex.text("title", default="Plot", section="Style")
def run(ctx, title):
    return {"result": title}
"""
    mutations.apply_python_script(node.node_id, source)
    node.expanded_settings_group_ids = ("style",)
    fragment_data = build_subtree_fragment_payload_data(
        workspace=workspace,
        selected_node_ids=(node.node_id,),
    )
    assert fragment_data is not None
    pasted_ids = insert_graph_fragment(
        model=model,
        workspace_id=workspace.workspace_id,
        fragment_payload=build_graph_fragment_payload(**fragment_data),
        delta_x=200.0,
        delta_y=0.0,
        registry=registry,
    )

    assert len(pasted_ids) == 1
    assert workspace.nodes[pasted_ids[0]].expanded_settings_group_ids == ("style",)


def test_decorated_controls_use_the_shared_settings_group_payload() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script", title="Script", x=0.0, y=0.0
    )
    source = """@corex.node
@corex.input("values", value_type=float, structure="tree", section="Data")
@corex.output("result", value_type=float)
@corex.switch("enabled", default=True, section="Display", port=True)
@corex.slider("width", default=2.0, minimum=0.5, maximum=8.0, section="Display")
def run(ctx, values, enabled, width):
    return {"result": width}
"""
    mutations.apply_python_script(node.node_id, source)

    payloads, _backdrops, _minimap = (
        GraphScenePayloadBuilder().build_node_payloads_for_ids(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            scope_path=(),
            node_ids={node.node_id},
            graph_theme_bridge=None,
        )
    )
    payload = payloads[0]
    assert [group["group_id"] for group in payload["settings_groups"]] == [
        "data",
        "display",
    ]
    assert payload["settings_groups"][1]["items"][0]["kind"] == "port"
    enabled_port = next(port for port in payload["ports"] if port["key"] == "enabled")
    assert enabled_port["default_property"]["inline_editor"] == "toggle"
    assert (
        payload["settings_groups"][1]["items"][1]["property"]["inline_editor"]
        == "slider"
    )
    assert payload["inline_properties"] == []


def test_decorated_script_settings_round_trip_without_a_manifest_copy() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = ValidatedGraphMutation(model, workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id="core.python_script", title="Script", x=0.0, y=0.0
    )
    source = """@corex.node
@corex.output("result", value_type=corex.Interval)
@corex.interval("bounds", default=(0.0, 1.0), section="Ranges")
def run(ctx, bounds):
    return {"result": bounds}
"""
    mutations.apply_python_script(node.node_id, source)
    node.properties["bounds"] = Interval1D(2.0, 3.0)
    model.set_node_expanded_settings_group_ids(
        workspace.workspace_id,
        node.node_id,
        ("ranges",),
    )

    serializer = JsonProjectSerializer(registry)
    document = serializer.to_persistent_document(model.project)
    node_document = document["workspaces"][0]["nodes"][0]
    assert set(node_document["properties"]) == {
        "script",
        "timeout_sec",
        "bounds",
    }
    loaded = serializer.from_document(document)
    loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
    assert loaded_node.properties["script"] == source
    assert loaded_node.properties["bounds"] == Interval1D(2.0, 3.0)
    assert loaded_node.expanded_settings_group_ids == ("ranges",)
