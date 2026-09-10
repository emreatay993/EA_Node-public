# Purpose: Verify accepted Mechanical catalogue selector projection.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

from types import SimpleNamespace

from ea_node_editor.addons.catalog import create_live_property_edit_adapters
from ea_node_editor.addons.mechanical.contracts import catalogue_table, model_handle
from ea_node_editor.addons.property_edit_adapters import (
    PropertyEditAdapterContext,
    build_property_items_with_adapters,
)
from ea_node_editor.runtime_contracts import DataTree
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.ui.shell.inspector_projection import build_selected_node_property_items
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.addons.property_edit_adapters import create_property_edit_adapters
from tests.mechanical_catalogue.test_contracts import _model_metadata, _row, _selector


def _catalogue(*, revision=2, complete=True, name="RÉSULTAT", native_id=7, omitted_rows=3):
    catalogue_id = f"00000000-0000-0000-0000-{revision:012d}"
    return catalogue_table(
        [
            _row(model_revision=revision, catalogue_id=catalogue_id, system_key="system-1", catalogue_complete=complete, omitted_rows=0 if complete else omitted_rows),
            _row(
                "object",
                model_revision=revision,
                catalogue_id=catalogue_id,
                object_id=native_id,
                object_path=f"Model/{name}",
                system_key="system-1",
                display_name=name,
                api_type="Result",
                selector_code=_selector("object", native_id, f"Model/{name}"),
            ),
        ]
    )


def _model(*, revision=2, **changes):
    metadata_changes = {
        "catalogue_id": f"00000000-0000-0000-0000-{revision:012d}",
        "model_revision": revision,
        **changes,
    }
    metadata = _model_metadata(
        **metadata_changes,
    )
    return model_handle(
        handle_id=f"model-{revision}",
        owner_scope="run-1",
        worker_generation=1,
        metadata=metadata,
    )


def _project(provider, model_tree, *, key="objects", node_type="mechanical.export_image", properties=None):
    node = SimpleNamespace(node_id="consumer", type_id=node_type, properties=dict(properties or {}))
    edge = SimpleNamespace(
        target_node_id="consumer",
        target_port_key="model",
        source_node_id="forwarder",
        source_port_key="value",
        enabled=True,
    )
    adapters = create_live_property_edit_adapters()
    return build_property_items_with_adapters(
        adapters,
        PropertyEditAdapterContext(
            node=node,
            workspace_edges=[edge],
            current_output_provider=lambda source, port: model_tree
            if (source, port) == ("forwarder", "value")
            else provider(source, port),
        ),
        [{"key": key, "searchable": True, "value": "unknown"}],
    )[0]


def test_registered_adapter_resolves_forwarded_whole_tree_and_keeps_exact_codes() -> None:
    table = _catalogue()
    calls = []

    def provider(node, port):
        calls.append((node, port))
        return DataTree({(0, 2): ("receipt", table)})

    item = _project(provider, DataTree({(8,): (_model(),)}))
    assert calls == [("open-1", "info")]
    assert item["enum_values"] == ["RÉSULTAT — Model/RÉSULTAT"]
    assert item["enum_codes"] == [_selector("object", 7, "Model/RÉSULTAT")]
    assert item["value"] == "unknown"


def test_locator_requires_path_iteration_and_unique_matching_table() -> None:
    table = _catalogue()

    def provider(_node, _port):
        return DataTree({(0, 2): (table, table)})

    invalid = _project(provider, DataTree.from_item(_model()))
    assert invalid["enum_codes"] == []
    assert invalid["metadata_notice"] == "Accepted metadata is invalid."
    wrong = _model(producer_iteration=9)
    assert _project(lambda *_: DataTree({(0, 2): (table,)}), DataTree.from_item(wrong))["enum_codes"] == []
    assert _project(lambda *_: DataTree({(4,): (table,)}), DataTree.from_item(_model()))["enum_codes"] == []


def test_incomplete_catalogue_with_unknown_omission_count_preserves_nullable_scalars() -> None:
    from ea_node_editor.addons.mechanical.property_edit import _table_rows

    table = _catalogue(complete=False, omitted_rows=None)
    rows = _table_rows(table)
    assert rows[0]["omitted_rows"] is None
    assert rows[0]["catalogue_complete"] is False
    assert rows[0]["model_revision"] == 2
    assert rows[1]["has_tabular_data"] is None
    item = _project(lambda *_: DataTree({(0, 2): (table,)}), DataTree.from_item(_model()))
    assert item["enum_codes"] == [_selector("object", 7, "Model/RÉSULTAT")]
    assert "incomplete" in item["metadata_notice"].lower()


def test_descriptor_index_is_reused_and_replaced_with_the_accepted_table(monkeypatch) -> None:
    from ea_node_editor.addons.mechanical import property_edit

    table = _catalogue(revision=12, name="First")
    replacement = _catalogue(revision=12, name="Replacement")
    calls = 0
    original = property_edit._table_rows

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(property_edit, "_table_rows", counted)
    model = DataTree.from_item(_model(revision=12))
    provider = lambda *_: DataTree({(0, 2): (table,)})
    assert "First" in _project(provider, model)["enum_values"][0]
    assert "First" in _project(provider, model)["enum_values"][0]
    assert calls == 1
    assert _project(lambda *_: DataTree({(0, 2): (table, replacement)}), model)["enum_codes"] == []
    assert "Replacement" in _project(lambda *_: DataTree({(0, 2): (replacement,)}), model)["enum_values"][0]
    assert calls == 3


def test_multiple_models_partial_notice_and_revision_replacement() -> None:
    first = _catalogue(complete=False)
    second = _catalogue(revision=3, name="Stress", native_id=8)
    models = DataTree({(0,): (_model(), _model(revision=3))})

    def provider(_node, _port):
        return DataTree({(0, 2): (first, second)})

    item = _project(provider, models)
    assert len(item["enum_codes"]) == 2
    assert item["metadata_notice"] == "Suggestions are incomplete (3 omitted rows)."


def test_discovery_only_open_reads_its_own_accepted_info_without_model() -> None:
    system = catalogue_table(
        [
            _row(status="system_required"),
            _row(
                "system",
                system_key="sys-2",
                system_label="Model B",
                selector_code=_selector("system", "sys-2", "").replace('"system_key":"system-1"', '"system_key":"sys-2"'),
            ),
        ]
    )
    node = SimpleNamespace(node_id="open-1", type_id="mechanical.open_model", properties={})
    [adapter] = [item for item in create_live_property_edit_adapters() if type(item).__name__ == "MechanicalPropertyEditAdapter"]
    item = adapter.build_property_items(
        PropertyEditAdapterContext(
            node=node,
            current_output_provider=lambda node_id, port: DataTree({(0, 2): (system,)}),
        ),
        [{"key": "system", "value": "authored"}],
    )[0]
    assert item["enum_values"] == ["Model B"]
    assert item["value"] == "authored"


def test_canvas_and_inspector_use_the_same_registered_adapter_context() -> None:
    table = _catalogue()
    model_value = DataTree.from_item(_model())
    node = NodeInstance("consumer", "mechanical.export_image", "Export", 0, 0, properties={"objects": "unknown"})
    edge = EdgeInstance("edge", "forwarder", "value", "consumer", "model")
    spec = NodeTypeSpec(
        type_id=node.type_id,
        display_name="Export",
        category_path=("Test",),
        icon="",
        ports=(
            PortSpec("model", "in", "data", "COREX.Mechanical.Model"),
            PortSpec("objects", "in", "data", "COREX.DataTypes.String", uses_property_default=True),
        ),
        properties=(PropertySpec("objects", "str", "unknown", "Objects", inline_editor="enum", searchable=True),),
    )

    def provider(node_id, port):
        if (node_id, port) == ("forwarder", "value"):
            return model_value
        return DataTree({(0, 2): (table,)})

    adapters = create_property_edit_adapters()
    inspector = build_selected_node_property_items(
        node=node,
        spec=spec,
        subnode_pin_type_ids=set(),
        workspace_nodes={node.node_id: node},
        workspace_edges=[edge],
        property_edit_adapters=adapters,
        current_output_provider=provider,
    )[0]
    builder = GraphScenePayloadBuilder(
        current_input_provider=provider,
        property_edit_adapters=adapters,
    )
    workspace = SimpleNamespace(edges={edge.edge_id: edge})
    canvas = builder.build_inline_properties_payload(
        node=node,
        spec=spec,
        workspace=workspace,
        workspace_nodes={node.node_id: node},
        enabled_input_port_keys={"model", "objects"},
        port_connection_counts={},
    )[0]
    assert canvas["enum_values"] == inspector["enum_values"]
    assert canvas["enum_codes"] == inspector["enum_codes"]
    assert canvas["value"] == inspector["value"] == "unknown"


def test_search_query_suggestions_preserve_difficult_mode_meanings_and_duplicate_scope_identity():
    catalogue_id = "00000000-0000-0000-0000-000000000002"
    rows = [
        _row(catalogue_id=catalogue_id, system_key="system-1"),
        _row(
            "object", catalogue_id=catalogue_id, system_key="system-1",
            object_id=7, object_path="Model/Load A", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            selector_code=_selector("object", 7, "Model/Load A"),
        ),
        _row(
            "object", catalogue_id=catalogue_id, system_key="system-1",
            object_id=8, object_path="Model/Load B", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            selector_code=_selector("object", 8, "Model/Load B"),
        ),
        _row(
            "relation", catalogue_id=catalogue_id, system_key="system-1",
            object_id=7, object_path="Model/Load A", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            relation_kind="coordinate_system", relation_role="CoordinateSystem",
            related_label="Frame", related_object_id=20, relation_status="available",
        ),
        _row(
            "relation", catalogue_id=catalogue_id, system_key="system-1",
            object_id=7, object_path="Model/Load A", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            relation_kind="source_model", relation_role="source",
            related_label="Current document", raw_source_id="Opaque::ID",
            relation_status="available",
        ),
        _row(
            "relation", catalogue_id=catalogue_id, system_key="system-1",
            object_id=7, object_path="Model/Load A", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            relation_kind="body_visibility", relation_role="body",
            body_hidden=True, relation_status="available",
        ),
        _row(
            "relation", catalogue_id=catalogue_id, system_key="system-1",
            object_id=7, object_path="Model/Load A", display_name="Load",
            api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
            relation_kind="environment", relation_role="owner",
            related_label="Analysis A", related_object_id=1,
            activation_state="ObjectActive", relation_status="available",
        ),
        *[
            _row(
                "relation", catalogue_id=catalogue_id, system_key="system-1",
                object_id=object_id, object_path=f"Model/Load {label}", display_name="Load",
                api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
                relation_kind="scope", relation_role="primary",
                related_label="Top face", related_object_id=9,
                scope_kind="named_selection", scope_count=1, relation_status="available",
            )
            for object_id, label in ((7, "A"), (8, "B"))
        ],
    ]
    table = catalogue_table(rows)
    provider = lambda *_: DataTree({(0, 2): (table,)})
    model = DataTree.from_item(_model())

    def query(filter_code):
        return _project(
            provider, model, key="query", node_type="mechanical.search_tree",
            properties={"filter": filter_code},
        )

    assert "Force" in query("type")["enum_codes"]
    assert "Frame" in query("coordinate_system")["enum_codes"]
    assert "Opaque::ID" in query("model")["enum_codes"]
    assert "Hidden bodies" in query("graphics")["enum_codes"]
    assert "Analysis A" in query("environment")["enum_codes"]
    scoping = query("scoping")
    assert scoping["enum_codes"].count("Top face") == 1
    typed = [code for code in scoping["enum_codes"] if str(code).startswith("{")]
    assert _selector("object", 7, "Model/Load A") in typed
    assert _selector("object", 8, "Model/Load B") in typed
