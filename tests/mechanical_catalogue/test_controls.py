# Purpose: Lock the Mechanical catalogue's shared control, grouping, port, and icon contracts.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ea_node_editor.addons.mechanical.property_edit import MechanicalPropertyEditAdapter
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.icon_catalog import BUILTIN_NODE_ICONS
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_canvas_state.execution_state_props import (
    resolve_runtime_property_presentations,
)


MECHANICAL_NODE_IDS = (
    "mechanical.open_model",
    "mechanical.search_tree",
    "mechanical.fea_table",
    "mechanical.camera_views",
    "mechanical.export_image",
    "mechanical.run_script",
    "mechanical.apdl_snippet",
    "mechanical.save_model",
)

EXPECTED_GROUPS = {
    "mechanical.open_model": (
        ("open_options", "Open options", ("file", "system", "mode", "version")),
        ("session_options", "Session options", ("working_folder", "timeout_s")),
    ),
    "mechanical.search_tree": (
        ("search", "Search", ("filter", "query")),
        (
            "match_options",
            "Match options",
            ("match", "case_sensitive", "include_hidden_properties", "invert"),
        ),
    ),
    "mechanical.fea_table": (
        (
            "table_selection",
            "Table selection",
            ("source", "family", "table", "component"),
        ),
        ("values_and_units", "Values and units", ("units", "sets")),
    ),
    "mechanical.camera_views": (
        ("view_selection", "View selection", ("include",)),
    ),
    "mechanical.export_image": (
        ("selection", "Selection", ("objects", "views")),
        (
            "image_options",
            "Image options",
            ("width", "height", "background", "fit_view"),
        ),
        ("save_to_disk", "Save to disk", ("folder", "file_name", "overwrite")),
    ),
    "mechanical.run_script": (
        ("script", "Script", ("environments", "scope", "code")),
        ("execution_options", "Execution options", ("timeout_s", "stop_on_error")),
    ),
    "mechanical.apdl_snippet": (
        ("command_snippet", "Command snippet", ("environments", "name", "commands")),
        (
            "solver_placement",
            "Solver placement",
            ("steps", "selected_steps", "issue_solve_command"),
        ),
    ),
    "mechanical.save_model": (
        ("destination", "Destination", ("file", "format")),
        (
            "save_options",
            "Save options",
            (
                "include_results",
                "include_user_files",
                "include_external_imported_files",
                "overwrite",
            ),
        ),
    ),
}

EXPECTED_ICONS = {
    "mechanical.open_model": "mechanical/open.svg",
    "mechanical.search_tree": "mechanical/search.svg",
    "mechanical.fea_table": "mechanical/table.svg",
    "mechanical.camera_views": "mechanical/views.svg",
    "mechanical.export_image": "mechanical/image.svg",
    "mechanical.run_script": "mechanical/script.svg",
    "mechanical.apdl_snippet": "mechanical/snippet.svg",
    "mechanical.save_model": "mechanical/save.svg",
}


def _registry(tmp_path: Path):
    return build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
        generation_root=tmp_path / "generations",
    )


def _projected_items(node_type: str, properties: dict[str, object]):
    adapter = MechanicalPropertyEditAdapter()
    context = PropertyEditAdapterContext(
        node=SimpleNamespace(
            node_id="mechanical-node",
            type_id=node_type,
            properties=properties,
        ),
        workspace_edges=(),
        current_output_provider=None,
    )
    return {
        item["key"]: item
        for item in adapter.build_property_items(
            context,
            (
                {
                    "key": key,
                    "condition_enabled": True,
                    "editor_enabled": True,
                }
                for key in properties
            ),
        )
    }


def test_all_eight_nodes_have_exact_typed_connectable_control_inventory(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    specs = tuple(registry.get_spec(type_id) for type_id in MECHANICAL_NODE_IDS)
    inputs = tuple(port for spec in specs for port in spec.ports if port.direction == "in")
    outputs = tuple(port for spec in specs for port in spec.ports if port.direction == "out")

    assert len(inputs) == 52
    assert len(outputs) == 22
    assert all(port.exposed and port.kind == "data" for port in (*inputs, *outputs))
    assert all(port.data_type and port.data_type != "COREX.DataTypes.Any" for port in inputs)
    assert all(port.label and port.description for port in (*inputs, *outputs))

    for spec in specs:
        input_by_key = {
            port.key: port for port in spec.ports if port.direction == "in"
        }
        assert len(input_by_key) == len(
            [port for port in spec.ports if port.direction == "in"]
        )
        for prop in spec.properties:
            port = input_by_key[prop.key]
            assert port.uses_property_default
            assert port.exposed
            assert prop.inline_editor

    save_inputs = {
        port.key: port
        for port in registry.get_spec("mechanical.save_model").ports
        if port.direction == "in"
    }
    for key in (
        "include_results",
        "include_user_files",
        "include_external_imported_files",
    ):
        assert save_inputs[key].data_type == "COREX.DataTypes.Bool"


def test_settings_groups_match_the_approved_order_and_keep_one_port_per_row(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    for type_id, expected_groups in EXPECTED_GROUPS.items():
        spec = registry.get_spec(type_id)
        actual = tuple(
            (
                group.group_id,
                group.label,
                tuple(item.port_key for item in group.items),
            )
            for group in spec.settings_groups
        )
        assert actual == expected_groups
        assert spec.default_expanded_settings_group_ids == (
            expected_groups[0][0],
        )
        grouped_keys = [key for _group_id, _label, keys in actual for key in keys]
        assert len(grouped_keys) == len(set(grouped_keys))
        for group in spec.settings_groups:
            for item in group.items:
                assert item.port_key
                assert item.property_key in {"", item.port_key}

    run_properties = {
        prop.key: prop for prop in registry.get_spec("mechanical.run_script").properties
    }
    snippet_properties = {
        prop.key: prop
        for prop in registry.get_spec("mechanical.apdl_snippet").properties
    }
    assert run_properties["code"].inline_editor == "textarea"
    assert snippet_properties["commands"].inline_editor == "textarea"


def test_contextual_conditions_disable_editors_without_removing_ports() -> None:
    standalone = _projected_items(
        "mechanical.open_model",
        {"file": "model.mechdb", "system": "SYS"},
    )
    workbench = _projected_items(
        "mechanical.open_model",
        {"file": "project.wbpj", "system": "SYS"},
    )
    assert not standalone["system"]["condition_enabled"]
    assert not standalone["system"]["editor_enabled"]
    assert workbench["system"]["condition_enabled"]
    for suffix in ("mechdb", "mechdat", "mechpz"):
        assert not _projected_items(
            "mechanical.open_model",
            {"file": f"model.{suffix}", "system": "SYS"},
        )["system"]["condition_enabled"]
    for draft in ("", "model", "unknown.txt", "model.custom"):
        assert _projected_items(
            "mechanical.open_model",
            {"file": draft, "system": "SYS"},
        )["system"]["condition_enabled"]

    definition = _projected_items(
        "mechanical.fea_table",
        {"family": "model_definition", "sets": [1]},
    )
    history = _projected_items(
        "mechanical.fea_table",
        {"family": "result_history_summary", "sets": [1]},
    )
    assert not definition["sets"]["condition_enabled"]
    assert history["sets"]["condition_enabled"]

    all_steps = _projected_items(
        "mechanical.apdl_snippet",
        {"steps": "all", "selected_steps": [1]},
    )
    selected_steps = _projected_items(
        "mechanical.apdl_snippet",
        {"steps": "selected", "selected_steps": [1]},
    )
    assert not all_steps["selected_steps"]["condition_enabled"]
    assert selected_steps["selected_steps"]["condition_enabled"]

    nonarchive = _projected_items(
        "mechanical.save_model",
        {
            "file": "model.mechdb",
            "format": "auto",
            "include_results": True,
            "include_user_files": True,
            "include_external_imported_files": True,
        },
    )
    workbench_archive = _projected_items(
        "mechanical.save_model",
        {
            "file": "project.wbpz",
            "format": "auto",
            "include_results": True,
            "include_user_files": True,
            "include_external_imported_files": True,
        },
    )
    assert all(
        not nonarchive[key]["condition_enabled"]
        for key in (
            "include_results",
            "include_user_files",
            "include_external_imported_files",
        )
    )
    assert all(
        workbench_archive[key]["condition_enabled"]
        for key in (
            "include_results",
            "include_user_files",
            "include_external_imported_files",
        )
    )


def test_runtime_value_overlay_preserves_adapter_disabled_state() -> None:
    disabled = {
        "key": "system",
        "value": "",
        "condition_enabled": False,
        "adapter_condition_enabled": False,
        "adapter_condition_reason": "Workbench sources only.",
        "editor_enabled": False,
        "editor_disabled_reason": "Workbench sources only.",
        "override_input_port_keys": ["system"],
    }
    lookup = resolve_runtime_property_presentations(
        node_payloads=[
            {
                "node_id": "open",
                "inline_properties": [],
                "settings_groups": [],
                "ports": [{"default_property": disabled}],
            }
        ],
        edge_payloads=[],
        output_records_by_node={},
    )

    assert lookup["open"]["system"]["condition_enabled"] is False
    assert lookup["open"]["system"]["editor_enabled"] is False
    assert lookup["open"]["system"]["editor_disabled_reason"] == (
        "Workbench sources only."
    )


def test_matching_declarative_condition_cannot_override_adapter_constraint() -> None:
    mode = {
        "key": "mode",
        "type": "enum",
        "value": "Manual",
        "display_value": "Manual",
        "display_value_available": True,
        "override_input_port_keys": ["mode"],
    }
    dependent = {
        "key": "dependent",
        "type": "int",
        "value": 1,
        "display_value": 1,
        "display_value_available": True,
        "override_input_port_keys": ["dependent"],
        "enabled_when": {
            "property_key": "mode",
            "values": ["Manual"],
            "source_type": "enum",
            "source_enum_values": ["Manual"],
            "source_value": "Manual",
            "source_override_input_port_keys": ["mode"],
        },
        "condition_enabled": False,
        "condition_reason": "Available when Mode is Manual.",
        "adapter_condition_enabled": False,
        "adapter_condition_reason": "Unavailable for this source family.",
    }
    node = {
        "node_id": "node",
        "inline_properties": [mode, dependent],
        "settings_groups": [],
        "ports": [],
    }
    constrained = resolve_runtime_property_presentations(
        node_payloads=[node],
        edge_payloads=[],
        output_records_by_node={},
    )["node"]["dependent"]
    assert constrained["condition_enabled"] is False
    assert constrained["editor_enabled"] is False
    assert constrained["editor_disabled_reason"] == (
        "Unavailable for this source family."
    )

    dependent.pop("adapter_condition_enabled")
    dependent.pop("adapter_condition_reason")
    restored = resolve_runtime_property_presentations(
        node_payloads=[node],
        edge_payloads=[],
        output_records_by_node={},
    )["node"]["dependent"]
    assert restored["condition_enabled"] is True
    assert restored["editor_enabled"] is True


def test_fresh_node_defaults_and_persisted_overrides_use_shared_group_state(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    model = GraphModel()
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, model.active_workspace.workspace_id)

    node_ids = {}
    for type_id in MECHANICAL_NODE_IDS:
        before_revision = model.active_workspace.mutation_revision
        node_ids[type_id] = scene.add_node_from_type(type_id)
        assert model.active_workspace.mutation_revision == before_revision + 1
    for type_id, node_id in node_ids.items():
        spec = registry.get_spec(type_id)
        node = model.active_workspace.nodes[node_id]
        assert node.expanded_settings_group_ids == (
            EXPECTED_GROUPS[type_id][0][0],
        )
        payload = next(
            item for item in scene.nodes_model if item["node_id"] == node_id
        )
        assert tuple(
            group["group_id"]
            for group in payload["settings_groups"]
            if group["expanded"]
        ) == node.expanded_settings_group_ids

    open_id = node_ids["mechanical.open_model"]
    before_ports = tuple(
        port.key for port in registry.get_spec("mechanical.open_model").ports
    )
    assert scene.set_node_settings_group_expanded(
        open_id,
        "open_options",
        False,
    )
    assert scene.set_node_settings_group_expanded(
        open_id,
        "session_options",
        True,
    )
    assert model.active_workspace.nodes[open_id].expanded_settings_group_ids == (
        "session_options",
    )
    assert tuple(
        port.key for port in registry.get_spec("mechanical.open_model").ports
    ) == before_ports
    search_id = node_ids["mechanical.search_tree"]
    assert scene.set_node_settings_group_expanded(search_id, "search", False)
    assert model.active_workspace.nodes[search_id].expanded_settings_group_ids == ()

    serializer = JsonProjectSerializer(registry)
    loaded = serializer.from_document(serializer.to_persistent_document(model.project))
    assert loaded.workspaces[model.active_workspace.workspace_id].nodes[
        open_id
    ].expanded_settings_group_ids == ("session_options",)
    assert loaded.workspaces[model.active_workspace.workspace_id].nodes[
        search_id
    ].expanded_settings_group_ids == ()


def test_icons_and_help_text_use_distinct_production_contracts(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    asset_root = (
        Path(__file__).resolve().parents[2]
        / "ea_node_editor"
        / "assets"
        / "node_title_icons"
    )
    assert {
        type_id: BUILTIN_NODE_ICONS[type_id] for type_id in MECHANICAL_NODE_IDS
    } == EXPECTED_ICONS
    for type_id, relative_path in EXPECTED_ICONS.items():
        spec = registry.get_spec(type_id)
        assert spec.icon == relative_path
        assert (asset_root / relative_path).is_file()

    assert "fresh isolated" in registry.get_spec("mechanical.open_model").description
    assert "without solving" in registry.get_spec("mechanical.fea_table").description
    assert "may explicitly solve or save" in registry.get_spec(
        "mechanical.run_script"
    ).description
    assert "without solving or saving" in registry.get_spec(
        "mechanical.apdl_snippet"
    ).description
    assert "Explicitly saves" in registry.get_spec("mechanical.save_model").description
