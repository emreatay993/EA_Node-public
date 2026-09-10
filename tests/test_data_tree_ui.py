from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.builtins.core import PYTHON_SCRIPT_DEFAULT_SOURCE
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.controllers.project_session_services_support.document_io_service import (
    ProjectDocumentIOService,
)
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_INSERT_DYNAMIC_PORT,
    ACTION_EDIT_NODE_PROPERTY,
    ACTION_REMOVE_DYNAMIC_PORT,
    ACTION_RENAME_DYNAMIC_PORT,
    RuntimeGraphHistory,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _stream_gate_scene() -> tuple[GraphSceneBridge, GraphModel, str, str]:
    registry = build_default_registry()
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace_id)
    gate_id = scene.add_node_from_type("core.stream_gate", 40.0, 40.0)
    sink_id = scene.add_node_from_type("core.if", 360.0, 40.0)
    return scene, model, gate_id, sink_id


def test_stream_gate_ui_mutations_keep_ids_remove_wires_and_record_history() -> None:
    scene, model, gate_id, sink_id = _stream_gate_scene()
    workspace = model.active_workspace
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)

    inserted = scene.insert_dynamic_port(gate_id, "outputs", 1)

    gate = workspace.nodes[gate_id]
    assert gate.properties["output_port_ids"] == ["output_0", inserted, "output_1"]
    assert history.undo_depth(workspace.workspace_id) == 1
    assert (
        history._undo_stacks[workspace.workspace_id][-1].action_type
        == ACTION_INSERT_DYNAMIC_PORT
    )

    edge_id = scene.add_edge(gate_id, inserted, sink_id, "true_value")
    history.clear_workspace(workspace.workspace_id)

    removed = scene.remove_dynamic_port(gate_id, "outputs", inserted)

    assert removed == {
        "port_key": inserted,
        "removed_edge_ids": [edge_id],
    }
    assert gate.properties["output_port_ids"] == ["output_0", "output_1"]
    assert edge_id not in workspace.edges
    assert history.undo_depth(workspace.workspace_id) == 1
    assert (
        history._undo_stacks[workspace.workspace_id][-1].action_type
        == ACTION_REMOVE_DYNAMIC_PORT
    )

    assert history.undo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[gate_id].properties["output_port_ids"] == [
        "output_0",
        inserted,
        "output_1",
    ]
    assert edge_id in workspace.edges


def test_stream_gate_ui_refuses_to_remove_its_last_output() -> None:
    scene, model, gate_id, _sink_id = _stream_gate_scene()
    workspace = model.active_workspace
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)

    removed = scene.remove_dynamic_port(gate_id, "outputs", "output_1")
    assert removed["port_key"] == "output_1"
    assert workspace.nodes[gate_id].properties["output_port_ids"] == ["output_0"]
    depth = history.undo_depth(workspace.workspace_id)

    error = scene.remove_dynamic_port(gate_id, "outputs", "output_0")
    assert "retain at least 1 ports" in error["error"]["message"]
    assert workspace.nodes[gate_id].properties["output_port_ids"] == ["output_0"]
    assert history.undo_depth(workspace.workspace_id) == depth


def test_dynamic_port_label_rename_records_one_history_entry_and_noop_is_empty() -> None:
    scene, model, gate_id, _sink_id = _stream_gate_scene()
    workspace = model.active_workspace
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)

    renamed = scene.rename_dynamic_port(
        gate_id,
        "outputs",
        "output_0",
        "Primary",
    )

    assert renamed == {
        "previous_port_key": "output_0",
        "port_key": "output_0",
        "removed_edge_ids": [],
    }
    assert workspace.nodes[gate_id].port_labels == {"output_0": "Primary"}
    assert history.undo_depth(workspace.workspace_id) == 1
    assert (
        history._undo_stacks[workspace.workspace_id][-1].action_type
        == ACTION_RENAME_DYNAMIC_PORT
    )

    assert scene.rename_dynamic_port(
        gate_id,
        "outputs",
        "output_0",
        "Primary",
    ) == {}
    assert history.undo_depth(workspace.workspace_id) == 1

    assert history.undo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[gate_id].port_labels == {}
    assert history.redo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[gate_id].port_labels == {"output_0": "Primary"}


def test_dynamic_port_mutations_publish_targeted_updates_and_preserve_selection() -> None:
    scene, _model, gate_id, sink_id = _stream_gate_scene()
    scene.select_node(gate_id)
    selected_events: list[str] = []
    scene.node_selected.connect(selected_events.append)

    with patch.object(
        scene._scene_context,
        "publish_node_payload_update",
        wraps=scene._scene_context.publish_node_payload_update,
    ) as publish_node:
        inserted = scene.insert_dynamic_port(gate_id, "outputs", 1)

    publish_node.assert_called_once_with(
        gate_id,
        publication_path="dynamic_port_insert",
    )
    assert selected_events == [gate_id]

    edge_id = scene.add_edge(gate_id, inserted, sink_id, "true_value")
    scene.clear_selection()
    selected_events.clear()
    with (
        patch.object(
            scene._scene_context,
            "publish_node_payload_update",
            wraps=scene._scene_context.publish_node_payload_update,
        ) as publish_node,
        patch.object(
            scene._scene_context,
            "publish_edge_topology_delta",
            wraps=scene._scene_context.publish_edge_topology_delta,
        ) as publish_edges,
    ):
        removed = scene.remove_dynamic_port(gate_id, "outputs", inserted)

    assert removed["removed_edge_ids"] == [edge_id]
    publish_node.assert_called_once_with(
        gate_id,
        publication_path="dynamic_port_remove",
    )
    assert publish_edges.call_count == 1
    assert publish_edges.call_args.kwargs["removed_edge_ids"] == {edge_id}
    assert selected_events == []


def test_python_script_decorator_apply_prunes_edges_and_sparse_state_with_undo_redo() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    source_id = scene.add_node_from_type("core.python_script", 40.0, 40.0)
    target_id = scene.add_node_from_type("core.python_script", 360.0, 40.0)
    edge_id = scene.add_edge(source_id, "result", target_id, "payload")
    assert scene.set_port_modifiers(target_id, "payload", ["graft"])
    assert scene.set_principal_input_port(target_id, "payload")
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)

    renamed_source = '''@corex.node
@corex.input("renamed_payload", value_type=corex.Any)
@corex.output("result", value_type=corex.Any)
def run(ctx, renamed_payload):
    return {"result": renamed_payload}
'''
    scene.set_node_property(target_id, "script", renamed_source)

    assert workspace.nodes[target_id].properties["script"] == renamed_source
    assert edge_id not in workspace.edges
    assert workspace.nodes[target_id].port_modifiers == {}
    assert workspace.nodes[target_id].principal_input_port_id is None
    assert history.undo_depth(workspace.workspace_id) == 1
    assert (
        history._undo_stacks[workspace.workspace_id][-1].action_type  # noqa: SLF001
        == ACTION_EDIT_NODE_PROPERTY
    )

    assert history.undo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[target_id].properties["script"] == PYTHON_SCRIPT_DEFAULT_SOURCE
    assert edge_id in workspace.edges
    assert workspace.nodes[target_id].port_modifiers == {"payload": ("graft",)}
    assert workspace.nodes[target_id].principal_input_port_id == "payload"

    assert history.redo_workspace(workspace.workspace_id, workspace) is not None
    assert workspace.nodes[target_id].properties["script"] == renamed_source
    assert edge_id not in workspace.edges
    assert workspace.nodes[target_id].port_modifiers == {}
    assert workspace.nodes[target_id].principal_input_port_id is None


def test_python_script_declaration_errors_leave_scene_unchanged() -> None:
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    script_id = scene.add_node_from_type("core.python_script", 40.0, 40.0)

    before = workspace.nodes[script_id].clone()
    with pytest.raises(ValueError, match="line"):
        scene.set_node_property(script_id, "script", "@corex.node\ndef run(")
    assert workspace.nodes[script_id] == before


def test_open_project_shows_migration_report_after_finalization_without_overwriting_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.cxproj"
    source.write_text("legacy-source", encoding="utf-8")
    project = SimpleNamespace(
        migration_report=("Removed Z", "Removed A"),
        migration_source_schema_version=4,
    )
    events: list[str] = []
    service = object.__new__(ProjectDocumentIOService)
    service._save_guard = threading.Lock()
    service._host = SimpleNamespace(
        serializer=SimpleNamespace(load=lambda _path: project),
        model=SimpleNamespace(project=SimpleNamespace(workspaces={})),
    )
    service._project_files = SimpleNamespace(
        build_project_files_snapshot=lambda **_kwargs: object(),
        _project_files_prompt_headline=lambda _snapshot: "Open migrated project?",
        prompt_project_files_action=lambda **_kwargs: True,
    )
    service._finalize_loaded_project = lambda *_args, **_kwargs: events.append(
        "finalized"
    )
    service._show_migration_report = lambda loaded: events.append(
        "reported" if loaded is project else "wrong-project"
    )

    assert service.open_project_path(source)
    assert events == ["finalized", "reported"]
    assert source.read_text(encoding="utf-8") == "legacy-source"


def test_migration_report_is_one_sorted_dialog_with_source_version() -> None:
    service = object.__new__(ProjectDocumentIOService)
    dialog_parent = object()
    service._dialog_parent_source = SimpleNamespace(dialog_parent=lambda: dialog_parent)
    project = SimpleNamespace(
        migration_report=("Removed Z", "Removed A", "Removed Z", ""),
        migration_source_schema_version=4,
    )

    with patch("PyQt6.QtWidgets.QMessageBox.information") as information:
        service._show_migration_report(project)

    information.assert_called_once()
    parent, title, text = information.call_args.args
    assert parent is dialog_parent
    assert title == "Project Migration Report"
    assert "schema v4" in text
    assert "has not been overwritten" in text
    assert text.index("- Removed A") < text.index("- Removed Z")
    assert project.migration_report == ("Removed Z", "Removed A", "Removed Z", "")


def test_data_tree_node_error_source_contracts() -> None:
    graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
    host_text = (graph_dir / "GraphNodeHost.qml").read_text(encoding="utf-8")

    header_text = (graph_dir / "GraphNodeHeaderLayer.qml").read_text(encoding="utf-8")
    assert 'objectName: "graphNodeFailureBadge"' in header_text
    assert 'objectName: "graphNodeFailureBadgeText"' in header_text
    assert 'if (state === "flowing")' in host_text
    assert 'if (state === "waiting")' in host_text
    assert 'if (state === "idle")' in host_text
    assert 'state === "default" || state === "waiting" || state === "idle"' in host_text
