from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
import math
from types import SimpleNamespace
import unicodedata
from unittest.mock import patch

from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import EdgeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins import ssh_sftp_runtime as ssh_runtime
from ea_node_editor.nodes.builtins.rich_value_nodes import (
    AGENT_MODEL_DATA_TYPE_ID,
    COLOR_MAP_DATA_TYPE_ID,
    NODE_VISUAL_DATA_TYPE_ID,
    PLANE_DATA_TYPE_ID,
)
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DataConversionSpec,
    DataTypeCatalog,
    DataTypeSpec,
    GRAPH_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.runtime_contracts.data_tree import DataTree
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TypedInlineValue,
)
from ea_node_editor.ui.shell.library_projection import (
    build_registry_library_items,
)
from ea_node_editor.ui.graph_theme import resolve_graph_theme
from ea_node_editor.ui.support.node_presentation import (
    build_data_type_ui_projection,
    project_port_data_type_presentation,
)
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    _missing_output_preview,
    _output_preview,
    _settled_edge_item,
)
from ea_node_editor.ui_qml.graph_geometry.route_payload import (
    _data_type_warning_reason,
)
from ea_node_editor.ui_qml.edge_routing import build_edge_payload
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload.builder import (
    GraphScenePayloadBuilder,
)
from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    _annotate_edge_payload_availability,
)

_CONVERSION_SOURCE_TYPE_ID = "COREX.Tests.UiProjectionSource"
_CONVERSION_TARGET_TYPE_ID = "COREX.Tests.UiProjectionTarget"


class _TestNode:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _context: object) -> NodeResult:
        return NodeResult()


def _node_spec(
    type_id: str,
    *ports: PortSpec,
    properties: tuple[PropertySpec, ...] = (),
    dynamic_port_groups: tuple[DynamicPortGroupSpec, ...] = (),
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name=type_id,
        category_path=("Tests",),
        icon="",
        ports=ports,
        properties=properties,
        dynamic_port_groups=dynamic_port_groups,
    )


def _register_node(registry: NodeRegistry, spec: NodeTypeSpec) -> None:
    registry.register(lambda spec=spec: _TestNode(spec))


def _endpoint_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.data_types.register_many(
        types=(
            DataTypeSpec(
                _CONVERSION_SOURCE_TYPE_ID,
                "Projection source",
                "scalar",
                lambda _value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
            DataTypeSpec(
                _CONVERSION_TARGET_TYPE_ID,
                "Projection target",
                "scalar",
                lambda _value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
        ),
        conversions=(
            DataConversionSpec(
                _CONVERSION_SOURCE_TYPE_ID,
                _CONVERSION_TARGET_TYPE_ID,
                lambda value: value,
            ),
        ),
        owner_id="tests.data_type_ui_projection",
    )

    def dynamic_union_ports(
        properties: Mapping[str, object],
    ) -> tuple[PortSpec, ...]:
        keys = properties.get("port_ids", ())
        if type(keys) is not list:
            return ()
        return tuple(
            PortSpec(
                str(key),
                "in",
                "data",
                BOOLEAN_DATA_TYPE_ID,
                required=True,
                accepted_data_types=(STRING_DATA_TYPE_ID,),
            )
            for key in keys
        )

    specs = (
        _node_spec(
            "tests.ui.string_source",
            PortSpec("value", "out", "data", STRING_DATA_TYPE_ID),
        ),
        _node_spec(
            "tests.ui.abstract_source",
            PortSpec("value", "out", "data", GRAPH_DATA_TYPE_ID),
        ),
        _node_spec(
            "tests.ui.convertible_source",
            PortSpec("value", "out", "data", _CONVERSION_SOURCE_TYPE_ID),
        ),
        _node_spec(
            "tests.ui.string_target",
            PortSpec("value", "in", "data", STRING_DATA_TYPE_ID, required=True),
        ),
        _node_spec(
            "tests.ui.boolean_target",
            PortSpec("value", "in", "data", BOOLEAN_DATA_TYPE_ID, required=True),
        ),
        _node_spec(
            "tests.ui.conversion_target",
            PortSpec(
                "value",
                "in",
                "data",
                _CONVERSION_TARGET_TYPE_ID,
                required=True,
            ),
        ),
        _node_spec(
            "tests.ui.dynamic_union_target",
            properties=(
                PropertySpec(
                    "port_ids",
                    "json",
                    [],
                    "Port IDs",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    "inputs",
                    "port_ids",
                    "in",
                    dynamic_union_ports,
                    lambda properties: f"dynamic_{len(properties.get('port_ids', ()))}",
                ),
            ),
        ),
    )
    for spec in specs:
        _register_node(registry, spec)
    registry.freeze()
    return registry


def test_scene_and_library_ports_share_one_bounded_catalog_projection() -> None:
    registry = build_default_registry()
    projection = build_data_type_ui_projection(registry.data_types)
    assert projection["catalog_generation"] == registry.data_types.fingerprint()

    string_projection = project_port_data_type_presentation(
        data_type=STRING_DATA_TYPE_ID,
        accepted_data_types=(BOOLEAN_DATA_TYPE_ID, "Unknown." + ("x" * 400)),
        data_access="list",
        kind="data",
        projection=projection,
    )
    assert string_projection == {
        "data_type": STRING_DATA_TYPE_ID,
        "data_type_label": "Text",
        "data_type_family": "scalar",
        "data_type_family_label": "Scalar",
        "data_type_color_token": "data.scalar",
        "data_type_icon_key": "data",
        "accepted_data_type_labels": [
            "Boolean",
            "Unknown." + ("x" * 151) + "\u2026",
        ],
        "data_access": "list",
        "catalog_generation": registry.data_types.fingerprint(),
    }

    constant_spec = registry.get_spec("core.constant")
    library_item = build_registry_library_items(
        registry_specs=(constant_spec,),
        data_types=registry.data_types,
        data_type_projection=projection,
    )[0]
    library_port = next(
        port for port in library_item["ports"] if port["key"] == "as_text"
    )
    assert library_port["data_type_label"] == "Text"
    assert library_port["catalog_generation"] == registry.data_types.fingerprint()

    with (
        patch.object(
            registry.data_types,
            "snapshot",
            wraps=registry.data_types.snapshot,
        ) as snapshot,
        patch.object(
            registry.data_types,
            "fingerprint",
            wraps=registry.data_types.fingerprint,
        ) as fingerprint,
    ):
        scene_payload = GraphScenePayloadBuilder().build_library_preview_node_payload(
            model=None,
            registry=registry,
            workspace_id="",
            library_payload={
                "type_id": constant_spec.type_id,
                "display_name": constant_spec.display_name,
            },
            graph_theme_bridge=None,
        )
    assert snapshot.call_count == 1
    assert fingerprint.call_count == 1
    scene_port = next(
        port for port in scene_payload["ports"] if port["key"] == "as_text"
    )
    assert scene_port["data_type_label"] == library_port["data_type_label"]
    assert scene_port["data_type_family"] == library_port["data_type_family"]
    assert scene_port["catalog_generation"] == library_port["catalog_generation"]


def test_library_preview_fallback_keeps_node_and_only_valid_typed_ports() -> None:
    ports = [
        {"key": f"bad_{index}", "direction": "in", "kind": "data", "data_type": value}
        for index, value in enumerate((None, "", " ", 4, []))
    ]
    ports.append({
        "key": "valid", "direction": "in", "kind": "data", "data_type": STRING_DATA_TYPE_ID,
        "accepted_data_types": [BOOLEAN_DATA_TYPE_ID, STRING_DATA_TYPE_ID, BOOLEAN_DATA_TYPE_ID, None],
        "data_access": "tree",
    })
    spec = GraphScenePayloadBuilder._library_preview_fallback_spec({"type_id": "custom_workflow:test", "ports": ports})
    assert spec is not None
    assert [port.key for port in spec.ports] == ["valid"]
    assert spec.ports[0].accepted_data_types == (BOOLEAN_DATA_TYPE_ID,)
    assert spec.ports[0].data_access == "tree"
    empty = GraphScenePayloadBuilder._library_preview_fallback_spec({"type_id": "custom_workflow:test", "ports": ports[:-1]})
    assert empty is not None and empty.ports == ()
    preview = GraphScenePayloadBuilder().build_library_preview_node_payload(
        model=None, registry=None, workspace_id="",
        library_payload={"type_id": "custom_workflow:test", "ports": ports[:-1]},
        graph_theme_bridge=None,
    )
    assert preview["type_id"] == "custom_workflow:test"
    assert preview["ports"] == []


def test_flow_and_unknown_type_projection_fail_soft_without_family_styling() -> None:
    registry = build_default_registry()
    projection = build_data_type_ui_projection(registry.data_types)
    flow = project_port_data_type_presentation(
        data_type="flow",
        data_access="item",
        kind="flow",
        projection=projection,
    )
    assert flow["data_type_label"] == "Flow"
    assert flow["data_type_family"] == ""
    assert flow["data_type_color_token"] == ""
    assert flow["data_type_icon_key"] == ""

    unknown = project_port_data_type_presentation(
        data_type="Unknown.Type",
        data_access="invalid",
        kind="data",
        projection=projection,
    )
    assert unknown["data_type_label"] == "Unknown.Type"
    assert unknown["data_type_family"] == ""
    assert unknown["data_access"] == "item"


def test_compatible_endpoint_snapshot_uses_current_effective_ports_and_fingerprint() -> (
    None
):
    registry = _endpoint_registry()
    model = GraphModel()
    workspace = model.active_workspace
    nodes = {
        type_id: model.add_node(
            workspace.workspace_id,
            type_id,
            type_id,
            float(index * 180),
            0.0,
            properties=(
                {"port_ids": ["dynamic_union"]}
                if type_id == "tests.ui.dynamic_union_target"
                else None
            ),
        )
        for index, type_id in enumerate(
            (
                "tests.ui.string_source",
                "tests.ui.abstract_source",
                "tests.ui.convertible_source",
                "tests.ui.string_target",
                "tests.ui.boolean_target",
                "tests.ui.conversion_target",
                "tests.ui.dynamic_union_target",
            )
        )
    }
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    canvas = GraphCanvasStateBridge(scene_bridge=scene)

    def compatible_identities(
        node_type_id: str,
        port_key: str,
        candidate_role: str,
    ) -> set[tuple[str, str]]:
        snapshot = canvas.compatible_endpoint_snapshot(
            nodes[node_type_id].node_id,
            port_key,
            candidate_role,
        )
        assert snapshot["catalog_generation"] == registry.data_types.fingerprint()
        assert snapshot["candidate_role"] == candidate_role
        json.dumps(snapshot)
        return {
            (item["node_id"], item["port_key"])
            for item in snapshot["compatible_endpoint_ids"]
        }

    string_targets = compatible_identities(
        "tests.ui.string_source",
        "value",
        "target",
    )
    assert (
        nodes["tests.ui.dynamic_union_target"].node_id,
        "dynamic_union",
    ) in string_targets
    assert (
        nodes["tests.ui.boolean_target"].node_id,
        "value",
    ) not in string_targets

    conversion_targets = compatible_identities(
        "tests.ui.convertible_source",
        "value",
        "target",
    )
    assert (
        nodes["tests.ui.conversion_target"].node_id,
        "value",
    ) in conversion_targets

    runtime_check_targets = compatible_identities(
        "tests.ui.abstract_source",
        "value",
        "target",
    )
    assert (
        nodes["tests.ui.string_target"].node_id,
        "value",
    ) in runtime_check_targets

    source_candidates = compatible_identities(
        "tests.ui.string_target",
        "value",
        "source",
    )
    assert (
        nodes["tests.ui.string_source"].node_id,
        "value",
    ) in source_candidates
    assert (
        nodes["tests.ui.abstract_source"].node_id,
        "value",
    ) in source_candidates

    model.set_node_property(
        workspace.workspace_id,
        nodes["tests.ui.dynamic_union_target"].node_id,
        "port_ids",
        ["renamed_union"],
    )
    refreshed_targets = compatible_identities(
        "tests.ui.string_source",
        "value",
        "target",
    )
    assert (
        nodes["tests.ui.dynamic_union_target"].node_id,
        "renamed_union",
    ) in refreshed_targets
    assert (
        nodes["tests.ui.dynamic_union_target"].node_id,
        "dynamic_union",
    ) not in refreshed_targets

    assert (
        canvas.compatible_endpoint_snapshot(
            nodes["tests.ui.string_source"].node_id,
            "value",
            "invalid",
        )["compatible_endpoint_ids"]
        == []
    )


def test_type_warning_reason_is_static_and_availability_also_blocks_settlement() -> (
    None
):
    registry = build_default_registry()
    assert (
        _data_type_warning_reason(
            PortSpec("out", "out", "data", STRING_DATA_TYPE_ID),
            PortSpec("in", "in", "data", BOOLEAN_DATA_TYPE_ID),
            data_types=registry.data_types,
        )
        == "no_declared_relation"
    )
    assert (
        _data_type_warning_reason(
            PortSpec("out", "out", "flow", "flow"),
            PortSpec("in", "in", "flow", "flow"),
            data_types=registry.data_types,
        )
        == ""
    )
    assert (
        _data_type_warning_reason(
            PortSpec("out", "out", "flow", "flow"),
            PortSpec("in", "in", "data", STRING_DATA_TYPE_ID),
            data_types=registry.data_types,
        )
        == "incompatible_port_kind"
    )
    assert (
        _data_type_warning_reason(
            None,
            PortSpec("in", "in", "data", STRING_DATA_TYPE_ID),
            data_types=registry.data_types,
        )
        == "missing_source_port"
    )

    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Source",
        0.0,
        0.0,
    )
    target = model.add_node(
        workspace.workspace_id,
        "core.if",
        "Target",
        240.0,
        0.0,
    )
    invalid_edge = EdgeInstance(
        edge_id="invalid",
        source_node_id=source.node_id,
        source_port_key="as_text",
        target_node_id=target.node_id,
        target_port_key="condition",
    )
    edge_payload = build_edge_payload(
        graph_theme=resolve_graph_theme("stitch_light"),
        workspace_edges=[invalid_edge],
        workspace_nodes=dict(workspace.nodes),
        node_specs={
            source.node_id: registry.get_spec(source.type_id),
            target.node_id: registry.get_spec(target.type_id),
        },
        data_types=registry.data_types,
    )[0]
    assert edge_payload["data_type_warning"] is True
    assert edge_payload["data_type_warning_reason"] == "no_declared_relation"

    output_records = {
        "source": {
            "run": {
                "observed_at_epoch_ms": 1.0,
                "outputs": {
                    "out": SettledPortResult(
                        status="value",
                        value=DataTree.from_item("value"),
                    )
                },
                "stale": False,
            }
        }
    }
    edge = {
        "source_node_id": "source",
        "source_port_key": "out",
        "data_type_warning": False,
        "availability_warning": True,
    }
    assert _settled_edge_item(edge, output_records_by_node=output_records) == (
        False,
        None,
    )
    edge["availability_warning"] = False
    assert _settled_edge_item(edge, output_records_by_node=output_records) == (
        True,
        "value",
    )


def test_availability_annotation_does_not_create_a_type_warning() -> None:
    payload = {
        "data_type_warning": False,
        "data_type_warning_reason": "",
    }
    edge = SimpleNamespace(
        source_node_id="source",
        target_node_id="target",
    )
    source_node = object()
    target_node = object()
    source_spec = object()
    target_spec = object()
    with patch(
        "ea_node_editor.ui_qml.graph_scene_payload.normalize.edge_availability_warning",
        return_value="Port is currently unavailable.",
    ):
        _annotate_edge_payload_availability(
            payload,
            workspace=SimpleNamespace(),
            edge=edge,
            workspace_nodes={
                "source": source_node,
                "target": target_node,
            },
            node_specs={
                "source": source_spec,
                "target": target_spec,
            },
        )
    assert payload == {
        "data_type_warning": False,
        "data_type_warning_reason": "",
        "availability_warning": True,
        "availability_reason": "Port is currently unavailable.",
    }


def test_rich_preview_redacts_carrier_identity_and_uses_strict_handle_metadata() -> (
    None
):
    registry = build_default_registry()
    handle_spec = next(
        spec
        for spec in registry.data_types.all_specs()
        if spec.family_id in {"engineering", "fem", "geometry", "mesh"}
        and spec.sensitivity == "normal"
        and not spec.abstract
        and "handle" in spec.carriers
    )
    handle = RuntimeHandleRef(
        data_type_id=handle_spec.type_id,
        schema_version=handle_spec.payload_schema_version,
        handle_id="private-handle-id",
        kind="private.transport",
        owner_scope="private-owner-scope",
        worker_generation=91,
        metadata={
            "node_count": 42,
            "element_count": 12,
            "location": "Nodal",
            "unit": "MPa",
            "path": "private/model.rst",
            "scoping_ids": [1001, 1002],
            "result_id": "private-result-id",
        },
    )
    handle_preview = _output_preview(
        SettledPortResult(status="value", value=DataTree.from_item(handle)),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    rendered = repr(handle_preview)
    assert handle_preview["rich_preview"]["kind"] == "text"
    assert "nodes: 42" in handle_preview["rich_preview"]["text"]
    assert "elements: 12" in handle_preview["rich_preview"]["text"]
    for forbidden in (
        "private-handle-id",
        "private.transport",
        "private-owner-scope",
        "Nodal",
        "MPa",
        "model.rst",
        "1001",
        "private-result-id",
    ):
        assert forbidden not in rendered

    path_spec = registry.data_types.get(PATH_DATA_TYPE_ID)
    assert path_spec is not None
    artifact = RuntimeArtifactRef.staged(
        "private_artifact",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=path_spec.payload_schema_version,
        format="bin",
        size_bytes=987,
        sha256="a" * 64,
        provenance="private.provenance",
        metadata={"path_hint": "private/model.rst"},
    )
    artifact_preview = _output_preview(
        SettledPortResult(status="value", value=DataTree.from_item(artifact)),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert artifact_preview["rich_preview"]["kind"] == "text"
    assert artifact_preview["rich_preview"]["text"] == "Path artifact"
    for forbidden in (
        "private_artifact",
        "temp://",
        "987",
        "a" * 64,
        "private.provenance",
        "model.rst",
    ):
        assert forbidden not in repr(artifact_preview)

    nested_carriers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "handle": handle,
        "artifact": artifact,
    }
    nested_carrier_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(nested_carriers),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert "nodes: 42" in nested_carrier_preview["tooltip_text"]
    assert "Path artifact" in nested_carrier_preview["tooltip_text"]
    for forbidden in (
        "private-handle-id",
        "private-owner-scope",
        "private_artifact",
        "a" * 64,
        "private.provenance",
    ):
        assert forbidden not in repr(nested_carrier_preview)

    unknown = TypedInlineValue(
        data_type_id="Unknown.SecretType",
        schema_version=1,
        payload={"prompt": "private prompt", "credential": "private credential"},
    )
    unknown_preview = _output_preview(
        SettledPortResult(status="value", value=DataTree.from_item(unknown)),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert unknown_preview["rich_preview"] == {
        "kind": "none",
        "text": "",
        "swatches": [],
        "thumbnail_ref": "",
    }
    assert "private prompt" not in repr(unknown_preview)
    assert "private credential" not in repr(unknown_preview)
    assert "Unknown.SecretType" not in repr(unknown_preview)

    nested_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item({"nested": unknown}),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert nested_preview["rich_preview"]["kind"] == "none"
    assert "private prompt" not in repr(nested_preview)

    sensitive_spec = next(
        spec for spec in registry.data_types.all_specs() if spec.sensitivity != "normal"
    )
    sensitive = TypedInlineValue(
        data_type_id=sensitive_spec.type_id,
        schema_version=sensitive_spec.payload_schema_version,
        payload={"value": "private sensitive value"},
    )
    sensitive_preview = _output_preview(
        SettledPortResult(status="value", value=DataTree.from_item(sensitive)),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert sensitive_preview["rich_preview"]["kind"] == "none"
    assert "private sensitive value" not in repr(sensitive_preview)

    malformed_carriers = (
        RuntimeHandleRef(
            data_type_id=STRING_DATA_TYPE_ID,
            schema_version=1,
            handle_id="wrong-carrier-handle",
            kind="wrong.kind",
            owner_scope="wrong-scope",
            worker_generation=1,
        ),
        RuntimeHandleRef(
            data_type_id=handle_spec.type_id,
            schema_version=handle_spec.payload_schema_version + 1,
            handle_id="wrong-schema-handle",
            kind="wrong.schema",
            owner_scope="wrong-schema-scope",
            worker_generation=2,
        ),
        TypedInlineValue(
            data_type_id=GRAPH_DATA_TYPE_ID,
            schema_version=1,
            payload={"value": "abstract secret"},
        ),
    )
    for malformed in malformed_carriers:
        preview = _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item(malformed),
            ),
            "item",
            stale=False,
            data_types=registry.data_types,
        )
        assert preview["rich_preview"]["kind"] == "none"
        assert preview["tooltip_text"] == "Current\nValue unavailable"
        assert "wrong-" not in repr(preview)
        assert "abstract secret" not in repr(preview)

    get_calls: list[str] = []
    with patch.object(
        type(registry.data_types),
        "get",
        side_effect=lambda type_id: get_calls.append(type_id),
    ):
        patched_lookup_preview = _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item(handle),
            ),
            "item",
            stale=False,
            data_types=registry.data_types,
        )
    assert get_calls == []
    assert "nodes: 42" in patched_lookup_preview["tooltip_text"]
    assert "private-" not in repr(patched_lookup_preview)


def test_inline_value_previews_use_bounded_direct_payloads_only() -> None:
    registry = build_default_registry()
    catalog = registry.data_types
    colors = [f"#{index:06X}FF" for index in range(12)]
    node_refs = [f"node:{index}" for index in range(12)]
    values = {
        "plane": TypedInlineValue(
            PLANE_DATA_TYPE_ID,
            1,
            {
                "origin": [1.0, 2.0, 3.0],
                "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                "normal": [0.0, 0.0, 1.0],
            },
        ),
        "color_map": TypedInlineValue(COLOR_MAP_DATA_TYPE_ID, 1, colors),
        "node_visual": TypedInlineValue(
            NODE_VISUAL_DATA_TYPE_ID,
            1,
            {"node_refs": node_refs},
        ),
        "agent_model": TypedInlineValue(
            AGENT_MODEL_DATA_TYPE_ID,
            1,
            {"provider_id": "corex-server", "model_id": "gpt-5.1"},
        ),
    }
    for value in values.values():
        catalog.validate_carrier(value.data_type_id, value)

    with (
        patch.object(
            type(catalog),
            "validate_carrier",
            side_effect=AssertionError("preview must not invoke catalog callbacks"),
        ),
        patch("builtins.open", side_effect=AssertionError("preview must not do I/O")),
    ):
        previews = {
            name: _output_preview(
                SettledPortResult(status="value", value=DataTree.from_item(value)),
                "item",
                stale=False,
                data_types=catalog,
            )
            for name, value in values.items()
        }

    plane = previews["plane"]
    assert plane["rich_preview"]["text"] == "Plane origin: (1, 2, 3)"
    assert "axes" not in repr(plane)
    assert "normal" not in repr(plane)

    color_map = previews["color_map"]["rich_preview"]
    assert color_map == {
        "kind": "swatches",
        "text": "COREX Color Map: 12 colors",
        "swatches": colors[:8],
        "thumbnail_ref": "",
    }

    node_visual = previews["node_visual"]["rich_preview"]
    assert node_visual["kind"] == "text"
    assert "12 node references" in node_visual["text"]
    assert all(reference in node_visual["text"] for reference in node_refs[:4])
    assert node_refs[4] not in node_visual["text"]

    agent_model = previews["agent_model"]["rich_preview"]
    assert agent_model["kind"] == "text"
    assert agent_model["text"] == ("Agent Model: provider=corex-server, model=gpt-5.1")

    for preview in previews.values():
        rich = preview["rich_preview"]
        assert set(rich) == {"kind", "text", "swatches", "thumbnail_ref"}
        assert len(rich["text"]) <= 160
        assert len(rich["swatches"]) <= 8
        assert type(rich["thumbnail_ref"]) is str
        rendered = json.dumps(preview, sort_keys=True)
        for forbidden in ("QObject", "QImage", "geometry", "renderer", "surface"):
            assert forbidden not in rendered

    invalid_values = (
        TypedInlineValue(
            PLANE_DATA_TYPE_ID,
            1,
            {
                "origin": [1.0, 2.0, 3.0],
                "axes": [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                "normal": [0.0, 0.0, 1.0],
            },
        ),
        TypedInlineValue(
            NODE_VISUAL_DATA_TYPE_ID,
            1,
            {
                "node_refs": ["node:\u202eLOUD_CONTROL_SENTINEL"],
                "surface": "LOUD_RENDER_SENTINEL",
            },
        ),
        TypedInlineValue(
            AGENT_MODEL_DATA_TYPE_ID,
            1,
            {
                "provider_id": "provider",
                "model_id": "model",
                "endpoint": "LOUD_ENDPOINT_SENTINEL",
                "credentials": "LOUD_CREDENTIAL_SENTINEL",
            },
        ),
    )
    for value in invalid_values:
        preview = _output_preview(
            SettledPortResult(status="value", value=DataTree.from_item(value)),
            "item",
            stale=False,
            data_types=catalog,
        )
        assert preview["tooltip_text"] == "Current\nValue unavailable"
        assert preview["rich_preview"] == {
            "kind": "none",
            "text": "",
            "swatches": [],
            "thumbnail_ref": "",
        }
        assert "LOUD_" not in repr(preview)

    mapping_callbacks: list[str] = []

    class HostileTypeMap(dict[str, DataTypeSpec]):
        def get(self, _key: object, _default: object = None) -> object:
            mapping_callbacks.append("get")
            raise AssertionError("catalog mapping callback must not run")

    hostile_mapping_catalog = DataTypeCatalog()
    object.__setattr__(
        hostile_mapping_catalog,
        "_types",
        HostileTypeMap(
            {
                AGENT_MODEL_DATA_TYPE_ID: catalog._types[  # noqa: SLF001
                    AGENT_MODEL_DATA_TYPE_ID
                ]
            }
        ),
    )
    hostile_mapping_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(values["agent_model"]),
        ),
        "item",
        stale=False,
        data_types=hostile_mapping_catalog,
    )
    assert hostile_mapping_preview["tooltip_text"] == "Current\nValue unavailable"
    assert hostile_mapping_preview["rich_preview"]["kind"] == "none"
    assert mapping_callbacks == []

    spec_callbacks: list[str] = []

    class HostileSpec(DataTypeSpec):
        def __getattribute__(self, name: str) -> object:
            spec_callbacks.append(name)
            raise AssertionError("spec subclass callback must not run")

    hostile_spec_catalog = DataTypeCatalog()
    hostile_spec = object.__new__(HostileSpec)
    object.__setattr__(
        hostile_spec_catalog,
        "_types",
        {AGENT_MODEL_DATA_TYPE_ID: hostile_spec},
    )
    hostile_spec_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(values["agent_model"]),
        ),
        "item",
        stale=False,
        data_types=hostile_spec_catalog,
    )
    assert hostile_spec_preview["tooltip_text"] == "Current\nValue unavailable"
    assert hostile_spec_preview["rich_preview"]["kind"] == "none"
    assert spec_callbacks == []


def test_runtime_carrier_preview_rejects_hostile_catalog_keys_without_callbacks() -> (
    None
):
    registry = build_default_registry()
    valid_spec = registry.data_types._types[AGENT_MODEL_DATA_TYPE_ID]  # noqa: SLF001
    callbacks: list[str] = []

    class HostileCatalogKey:
        def __hash__(self) -> int:
            return hash(AGENT_MODEL_DATA_TYPE_ID)

        def __eq__(self, _other: object) -> bool:
            callbacks.append("eq")
            return False

    catalog_types: dict[object, DataTypeSpec] = {}
    catalog_types[HostileCatalogKey()] = valid_spec
    catalog_types[AGENT_MODEL_DATA_TYPE_ID] = valid_spec
    callbacks.clear()

    catalog = DataTypeCatalog()
    object.__setattr__(catalog, "_types", catalog_types)
    preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(
                TypedInlineValue(
                    AGENT_MODEL_DATA_TYPE_ID,
                    1,
                    {"provider_id": "provider", "model_id": "model"},
                )
            ),
        ),
        "item",
        stale=False,
        data_types=catalog,
    )

    assert preview["tooltip_text"] == "Current\nValue unavailable"
    assert preview["rich_preview"]["kind"] == "none"
    assert callbacks == []


def test_runtime_carrier_preview_rejects_hostile_spec_fields_without_callbacks() -> (
    None
):
    registry = build_default_registry()
    valid_spec = registry.data_types._types[AGENT_MODEL_DATA_TYPE_ID]  # noqa: SLF001
    value = TypedInlineValue(
        AGENT_MODEL_DATA_TYPE_ID,
        1,
        {"provider_id": "provider", "model_id": "model"},
    )
    callbacks: list[str] = []

    class HostileFrozenset(frozenset[str]):
        def __contains__(self, _item: object) -> bool:
            callbacks.append("contains")
            return True

        def __iter__(self):  # noqa: ANN204
            callbacks.append("iter")
            return super().__iter__()

    class HostileStr(str):
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            callbacks.append("str_eq")
            return super().__eq__(other)

    class HostileInt(int):
        def __eq__(self, other: object) -> bool:
            callbacks.append("int_eq")
            return super().__eq__(other)

    hostile_member_carriers = frozenset({HostileStr("inline")})
    callbacks.clear()
    field_overrides = (
        {"type_id": HostileStr(AGENT_MODEL_DATA_TYPE_ID)},
        {"display_name": HostileStr(valid_spec.display_name)},
        {"family_id": HostileStr(valid_spec.family_id)},
        {"abstract": 0},
        {"carriers": HostileFrozenset({"inline"})},
        {"carriers": hostile_member_carriers},
        {"sensitivity": HostileStr("normal")},
        {"payload_schema_version": HostileInt(1)},
    )
    for overrides in field_overrides:
        catalog = DataTypeCatalog()
        object.__setattr__(
            catalog,
            "_types",
            {AGENT_MODEL_DATA_TYPE_ID: replace(valid_spec, **overrides)},
        )
        preview = _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item(value),
            ),
            "item",
            stale=False,
            data_types=catalog,
        )
        assert preview["tooltip_text"] == "Current\nValue unavailable"
        assert preview["rich_preview"]["kind"] == "none"

    assert callbacks == []


def test_ssh_runtime_marker_previews_redact_every_container_position() -> None:
    registry = build_default_registry()
    secret = {
        ssh_runtime.RUNTIME_VALUE_TAG: ssh_runtime.SECRET_RUNTIME_TYPE,
        "revision": 1,
        "provider": "windows_dpapi",
        "scope": "CurrentUser",
        "ciphertext_b64": "LOUD_CIPHERTEXT_SENTINEL",
    }
    passphrase = {
        **secret,
        "ciphertext_b64": "LOUD_PASSPHRASE_SENTINEL",
    }
    host = {
        ssh_runtime.RUNTIME_VALUE_TAG: ssh_runtime.HOST_RUNTIME_TYPE,
        "revision": 1,
        "address": "LOUD_ADDRESS_SENTINEL.invalid",
        "port": 2222,
        "username": "LOUD_PLAINTEXT_USERNAME",
        "password": secret,
        "private_key_path": "C:/LOUD_PRIVATE_KEY_SENTINEL.pem",
        "private_key_passphrase": passphrase,
        "use_openssh_agent": False,
        "use_pageant": False,
    }
    cases = (
        ("item", DataTree.from_item(secret)),
        ("list", DataTree.from_list([secret, host])),
        ("tree", DataTree((((0,), (secret,)), ((1,), (host,))))),
        (
            "item",
            DataTree.from_item({"level0": {"level1": {"level2": host}}}),
        ),
    )
    forbidden = (
        ssh_runtime.RUNTIME_VALUE_TAG,
        ssh_runtime.SECRET_RUNTIME_TYPE,
        ssh_runtime.HOST_RUNTIME_TYPE,
        "provider",
        "windows_dpapi",
        "scope",
        "CurrentUser",
        "ciphertext_b64",
        "LOUD_CIPHERTEXT_SENTINEL",
        "LOUD_PASSPHRASE_SENTINEL",
        "address",
        "LOUD_ADDRESS_SENTINEL",
        "username",
        "LOUD_PLAINTEXT_USERNAME",
        "private_key_path",
        "LOUD_PRIVATE_KEY_SENTINEL",
    )
    for access, tree in cases:
        preview = _output_preview(
            SettledPortResult(status="value", value=tree),
            access,
            stale=False,
            data_types=registry.data_types,
        )
        assert "Value unavailable" in preview["tooltip_text"]
        assert preview["rich_preview"]["kind"] == "none"
        outputs = (
            preview["tooltip_text"],
            json.dumps(preview["rows"], sort_keys=True),
            json.dumps(preview["rich_preview"], sort_keys=True),
        )
        for value in forbidden:
            assert all(value not in output for output in outputs)

    key_callbacks: list[str] = []

    class HostileKey:
        def __hash__(self) -> int:
            return hash(ssh_runtime.RUNTIME_VALUE_TAG)

        def __eq__(self, _other: object) -> bool:
            key_callbacks.append("eq")
            raise AssertionError("hostile key equality must not run")

        def __str__(self) -> str:
            key_callbacks.append("str")
            raise AssertionError("hostile key string conversion must not run")

        def __repr__(self) -> str:
            key_callbacks.append("repr")
            raise AssertionError("hostile key repr must not run")

    near_marker = {
        HostileKey(): "decoy",
        "__ea_runtime_value__near": "ordinary-visible-value",
    }
    key_callbacks.clear()
    near_marker_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(near_marker),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert key_callbacks == []
    assert "__ea_runtime_value__near" in near_marker_preview["tooltip_text"]
    assert "ordinary-visible-value" in near_marker_preview["tooltip_text"]


def test_panel_rows_and_copy_use_the_safe_catalog_projection() -> None:
    registry = build_default_registry()
    callbacks: list[str] = []

    class HostileValue:
        def __str__(self) -> str:
            callbacks.append("str")
            raise AssertionError("Panel must not call str")

        def __repr__(self) -> str:
            callbacks.append("repr")
            raise AssertionError("Panel must not call repr")

    secret = {
        ssh_runtime.RUNTIME_VALUE_TAG: ssh_runtime.SECRET_RUNTIME_TYPE,
        "revision": 1,
        "provider": "windows_dpapi",
        "scope": "CurrentUser",
        "ciphertext_b64": "LOUD_PANEL_CIPHERTEXT",
    }
    host = {
        ssh_runtime.RUNTIME_VALUE_TAG: ssh_runtime.HOST_RUNTIME_TYPE,
        "revision": 1,
        "address": "LOUD_PANEL_ADDRESS.invalid",
        "port": 2222,
        "username": "LOUD_PANEL_USERNAME",
        "password": secret,
        "private_key_path": "C:/LOUD_PANEL_KEY.pem",
        "private_key_passphrase": secret,
        "use_openssh_agent": False,
        "use_pageant": False,
    }
    agent_model = TypedInlineValue(
        AGENT_MODEL_DATA_TYPE_ID,
        1,
        {"provider_id": "corex-server", "model_id": "gpt-5.1"},
    )
    tree = DataTree(
        (
            ((0,), (secret,)),
            ((1,), ([host],)),
            ((2,), ({"nested": {"host": host}},)),
            (
                (3,),
                (
                    {"__ea_runtime_value__near": "ordinary-visible-value"},
                    HostileValue(),
                    agent_model,
                ),
            ),
        )
    )
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    bridge = GraphCanvasStateBridge(scene_bridge=scene)
    bridge._execution_source = SimpleNamespace(  # noqa: SLF001
        run_state=SimpleNamespace(
            cached_node_output_records_by_workspace_id={
                workspace.workspace_id: {
                    "panel": {
                        "run": {
                            "record_id": "run",
                            "observed_at_epoch_ms": 1.0,
                            "outputs": {
                                "output": SettledPortResult(
                                    status="value",
                                    value=tree,
                                )
                            },
                        }
                    }
                }
            },
            node_solution_facts_by_workspace_id={
                workspace.workspace_id: {
                    "panel": NodeSolutionFact(
                        project_id=model.project.project_id,
                        workspace_id=workspace.workspace_id,
                        node_id="panel",
                        freshness=SolutionFreshness.CURRENT,
                        revision=1,
                        retained_record_id="run",
                        retained_solution_key="a" * 64,
                        residency=SolutionResidency.SESSION,
                        last_disposition=SolutionDisposition.RECOMPUTED,
                    )
                }
            },
        )
    )

    rows = bridge.panel_display_rows("panel")
    copied = bridge.panel_copy_text("panel", False)
    copied_tree = bridge.panel_copy_text("panel", True)
    rendered = json.dumps(rows, sort_keys=True) + copied + copied_tree

    assert callbacks == []
    assert rendered.count("Value unavailable") >= 6
    assert "__ea_runtime_value__near" in rendered
    assert "ordinary-visible-value" in rendered
    assert "{__ea_runtime_value__: " not in rendered
    assert "Unsupported value" in rendered
    assert "Agent Model: provider=corex-server, model=gpt-5.1" in rendered
    for forbidden in (
        ssh_runtime.SECRET_RUNTIME_TYPE,
        ssh_runtime.HOST_RUNTIME_TYPE,
        "windows_dpapi",
        "CurrentUser",
        "LOUD_PANEL_CIPHERTEXT",
        "LOUD_PANEL_ADDRESS",
        "LOUD_PANEL_USERNAME",
        "LOUD_PANEL_KEY",
    ):
        assert forbidden not in rendered


def test_preview_renderer_is_control_safe_bounded_and_callback_free() -> None:
    registry = build_default_registry()
    callbacks: list[str] = []

    class HostileValue:
        def __repr__(self) -> str:
            callbacks.append("repr")
            raise AssertionError("repr must not run")

        def __str__(self) -> str:
            callbacks.append("str")
            raise AssertionError("str must not run")

    class HostileMapping(Mapping[object, object]):
        def __getitem__(self, _key: object) -> object:
            callbacks.append("mapping_getitem")
            raise AssertionError("mapping access must not run")

        def __iter__(self):
            callbacks.append("mapping_iter")
            raise AssertionError("mapping iteration must not run")

        def __len__(self) -> int:
            callbacks.append("mapping_len")
            raise AssertionError("mapping length must not run")

        def items(self):
            callbacks.append("mapping_items")
            raise AssertionError("mapping items must not run")

    class HostileIterable:
        def __iter__(self):
            callbacks.append("iter")
            raise AssertionError("iteration must not run")

    class HostileList(list[object]):
        def __len__(self) -> int:
            callbacks.append("list_len")
            raise AssertionError("subclass length must not run")

        def __getitem__(self, _key: object) -> object:
            callbacks.append("list_getitem")
            raise AssertionError("subclass indexing must not run")

        def __iter__(self):
            callbacks.append("list_iter")
            raise AssertionError("subclass iteration must not run")

    class HostileString(str):
        def __str__(self) -> str:
            callbacks.append("string_str")
            raise AssertionError("subclass string conversion must not run")

        def split(self, *_args: object, **_kwargs: object):
            callbacks.append("string_split")
            raise AssertionError("subclass split must not run")

    hostile_values = (
        HostileValue(),
        HostileMapping(),
        HostileIterable(),
        HostileList([1, 2, 3]),
        HostileString("private"),
    )
    with patch("builtins.open", side_effect=AssertionError("preview must not do I/O")):
        for value in hostile_values:
            preview = _output_preview(
                SettledPortResult(
                    status="value",
                    value=DataTree.from_item(value),
                ),
                "item",
                stale=False,
                data_types=registry.data_types,
            )
            assert preview["tooltip_text"] == "Current\nUnsupported value"
            assert preview["rich_preview"]["kind"] == "none"
    assert callbacks == []

    huge_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(list(range(100_000))),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert len(huge_preview["rich_preview"]["text"]) <= 160
    assert "99999" not in repr(huge_preview)
    assert "\u2026" in huge_preview["rich_preview"]["text"]

    recursive: list[object] = []
    recursive.append(recursive)
    recursive_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(recursive),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    assert recursive_preview["tooltip_text"] == "Current\n[Recursive value]"
    assert recursive_preview["rich_preview"]["kind"] == "none"

    controlled = "safe\x00text\u202eevil\u2066\nline"
    control_preview = _output_preview(
        SettledPortResult(
            status="value",
            value=DataTree.from_item(controlled),
        ),
        "item",
        stale=False,
        data_types=registry.data_types,
    )
    rendered_text = control_preview["rich_preview"]["text"]
    assert rendered_text == "safetextevilline"
    assert all(
        not unicodedata.category(character).startswith("C")
        for character in rendered_text
    )

    for non_finite in (math.nan, math.inf, -math.inf):
        preview = _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item(non_finite),
            ),
            "item",
            stale=False,
            data_types=registry.data_types,
        )
        assert preview["tooltip_text"] == "Current\nNumber unavailable"
        assert preview["rich_preview"]["kind"] == "none"


def test_preview_states_always_publish_the_fixed_rich_preview_shape() -> None:
    registry = build_default_registry()
    previews = {
        "never": _missing_output_preview("item", never_run=True),
        "empty": _output_preview(
            SettledPortResult(status="empty"),
            "item",
            stale=False,
            data_types=registry.data_types,
        ),
        "failed": _output_preview(
            SettledPortResult(
                status="failed",
                errors=(RootExecutionError(error="preview failed"),),
            ),
            "item",
            stale=False,
            data_types=registry.data_types,
        ),
        "stale": _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item("stale"),
            ),
            "item",
            stale=True,
            data_types=registry.data_types,
        ),
        "current": _output_preview(
            SettledPortResult(
                status="value",
                value=DataTree.from_item("current"),
            ),
            "item",
            stale=False,
            data_types=registry.data_types,
        ),
    }
    assert {key: preview["state"] for key, preview in previews.items()} == {
        "never": "never",
        "empty": "empty",
        "failed": "failed",
        "stale": "stale",
        "current": "current",
    }
    for preview in previews.values():
        rich = preview["rich_preview"]
        assert set(rich) == {"kind", "text", "swatches", "thumbnail_ref"}
        assert rich["kind"] in {"none", "text", "swatches", "thumbnail"}
        assert type(rich["text"]) is str
        assert len(rich["text"]) <= 160
        assert type(rich["swatches"]) is list
        assert len(rich["swatches"]) <= 8
        assert type(rich["thumbnail_ref"]) is str
        assert len(rich["thumbnail_ref"]) <= 160
