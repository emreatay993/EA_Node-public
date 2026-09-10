from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine

from ea_node_editor.common.optimization_links import (
    OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
    OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
    OPTIMIZATION_RESPONSE_POOL_TYPE_ID,
    PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
    PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE,
    PARAMETER_SETUP_RESPONSE_POOL_LINK_ID,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_payloads import (
    node_instance_from_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _scene_fixture() -> tuple[
    GraphModel,
    str,
    GraphSceneBridge,
    GraphCanvasCommandBridge,
]:
    registry = build_default_registry()
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace_id)
    return model, workspace_id, scene, GraphCanvasCommandBridge(scene_bridge=scene)


def test_parameter_setup_pool_links_move_atomically_and_preserve_payload_order(
    qapp,  # noqa: ANN001
) -> None:
    model, workspace_id, scene, canvas = _scene_fixture()
    setup_one = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
        20.0,
        20.0,
    )
    setup_two = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
        240.0,
        20.0,
    )
    parameter_pool = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
        20.0,
        180.0,
    )
    response_pool = scene.add_node_from_type(
        OPTIMIZATION_RESPONSE_POOL_TYPE_ID,
        240.0,
        180.0,
    )
    workspace = model.project.workspaces[workspace_id]

    assert scene.upsert_node_link(
        setup_one,
        "docs",
        "url",
        "Docs",
        "https://example.com",
    ) == "docs"
    options = canvas.parameter_setup_link_options(parameter_pool)
    assert [item["setup_node_id"] for item in options] == [setup_one, setup_two]
    assert canvas.parameter_setup_link_options(setup_one) == []

    assert canvas.link_parameter_setup(parameter_pool, setup_one) is True
    assert set(scene._selected_node_ids) == {parameter_pool, setup_one}
    assert canvas.link_parameter_setup(response_pool, setup_two) is True
    parameter_record = workspace.nodes[setup_one].links[-1]
    assert [record.link_id for record in workspace.nodes[setup_one].links] == [
        "docs",
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
    ]
    assert parameter_record.kind == "node"
    assert parameter_record.title == PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE
    assert parameter_record.target == parameter_pool
    assert parameter_record.target_workspace_id == workspace_id
    assert parameter_record.target_node_id == parameter_pool
    assert workspace.nodes[setup_two].links[0].link_id == (
        PARAMETER_SETUP_RESPONSE_POOL_LINK_ID
    )
    payload = node_instance_to_mapping(
        workspace.nodes[setup_one],
        source_workspace_id=workspace_id,
    )
    restored = node_instance_from_mapping(payload, source_workspace_id=workspace_id)
    assert restored is not None
    assert [record.link_id for record in restored.links] == [
        "docs",
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
    ]
    assert restored.links[-1] == parameter_record

    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    history.clear_workspace(workspace_id)

    assert canvas.link_parameter_setup(parameter_pool, setup_two) is True
    assert history.undo_depth(workspace_id) == 1
    assert [record.link_id for record in workspace.nodes[setup_one].links] == ["docs"]
    assert [record.link_id for record in workspace.nodes[setup_two].links] == [
        PARAMETER_SETUP_RESPONSE_POOL_LINK_ID,
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
    ]
    assert canvas.parameter_setup_link_status(parameter_pool)["setup_node_id"] == (
        setup_two
    )

    assert history.undo_workspace(workspace_id, workspace) is not None
    scene.refresh_workspace_from_model(workspace_id)
    assert canvas.parameter_setup_link_status(parameter_pool)["setup_node_id"] == (
        setup_one
    )
    assert history.redo_workspace(workspace_id, workspace) is not None
    scene.refresh_workspace_from_model(workspace_id)
    assert canvas.parameter_setup_link_status(parameter_pool)["setup_node_id"] == (
        setup_two
    )

    assert canvas.unlink_parameter_setup(parameter_pool) is True
    assert canvas.parameter_setup_link_status(parameter_pool)["linked"] is False


def test_parameter_setup_pool_status_rejects_malformed_reserved_links_and_cardinality(
    qapp,  # noqa: ANN001
) -> None:
    model, workspace_id, scene, canvas = _scene_fixture()
    setup_one = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
        20.0,
        20.0,
    )
    setup_two = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
        240.0,
        20.0,
    )
    pool_one = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
        20.0,
        180.0,
    )
    pool_two = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
        240.0,
        180.0,
    )
    workspace = model.project.workspaces[workspace_id]

    assert scene.upsert_node_link(
        setup_one,
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
        "node",
        "Forged title",
        pool_one,
        "",
        workspace_id,
        pool_one,
    ) == PARAMETER_SETUP_PARAMETER_POOL_LINK_ID
    status = canvas.parameter_setup_link_status(pool_one)
    assert status["eligible"] is True
    assert status["linked"] is False
    assert status["conflict"] is False
    assert all(item["linked"] is False for item in canvas.parameter_setup_link_options(pool_one))

    assert canvas.link_parameter_setup(pool_one, setup_one) is True
    repaired = workspace.nodes[setup_one].links[0]
    assert repaired.title == PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE
    assert canvas.parameter_setup_link_status(pool_one)["setup_node_id"] == setup_one

    assert canvas.link_parameter_setup(pool_one, setup_two) is True
    assert canvas.parameter_setup_link_status(pool_one)["setup_node_id"] == setup_two
    assert not any(
        record.link_id == PARAMETER_SETUP_PARAMETER_POOL_LINK_ID
        for record in workspace.nodes[setup_one].links
    )

    assert scene.upsert_node_link(
        setup_one,
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
        "node",
        PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE,
        pool_one,
        "",
        workspace_id,
        pool_one,
    ) == PARAMETER_SETUP_PARAMETER_POOL_LINK_ID
    conflicted = canvas.parameter_setup_link_status(pool_one)
    assert conflicted["linked"] is False
    assert conflicted["conflict"] is True
    assert canvas.link_parameter_setup(pool_one, setup_two) is True
    assert canvas.parameter_setup_link_status(pool_one)["setup_node_id"] == setup_two

    assert scene.upsert_node_link(
        setup_two,
        "unrelated-link",
        "url",
        "Documentation",
        "https://example.invalid",
        "",
        "",
        "",
    ) == "unrelated-link"
    canonical = next(
        record
        for record in workspace.nodes[setup_two].links
        if record.link_id == PARAMETER_SETUP_PARAMETER_POOL_LINK_ID
    )
    workspace.nodes[setup_two].links.append(canonical.clone())
    duplicate_status = canvas.parameter_setup_link_status(pool_one)
    assert duplicate_status["linked"] is False
    assert duplicate_status["conflict"] is False

    assert canvas.link_parameter_setup(pool_one, setup_two) is True
    repaired_links = workspace.nodes[setup_two].links
    assert [record.link_id for record in repaired_links] == [
        PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
        "unrelated-link",
    ]
    repaired_status = canvas.parameter_setup_link_status(pool_one)
    assert repaired_status["linked"] is True
    assert repaired_status["conflict"] is False
    assert repaired_status["setup_node_id"] == setup_two

    assert canvas.link_parameter_setup(pool_two, setup_two) is True
    assert canvas.parameter_setup_link_status(pool_one)["linked"] is False
    assert canvas.parameter_setup_link_status(pool_two)["setup_node_id"] == setup_two
    assert canvas.link_parameter_setup(pool_two, pool_one) is False


def test_same_workspace_target_deletion_cleans_incoming_links_with_undo_redo(
    qapp,  # noqa: ANN001
) -> None:
    model, workspace_id, scene, canvas = _scene_fixture()
    setup = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
        20.0,
        20.0,
    )
    pool = scene.add_node_from_type(
        OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
        20.0,
        180.0,
    )
    ordinary_source = scene.add_node_from_type("core.logger", 260.0, 20.0)
    workspace = model.project.workspaces[workspace_id]
    assert canvas.link_parameter_setup(pool, setup) is True
    assert scene.upsert_node_link(
        ordinary_source,
        "ordinary-node-link",
        "node",
        "Pool reference",
        pool,
        "",
        workspace_id,
        pool,
    ) == "ordinary-node-link"

    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    history.clear_workspace(workspace_id)

    assert scene.remove_workspace_node(pool) is True
    assert pool not in workspace.nodes
    assert workspace.nodes[setup].links == []
    assert workspace.nodes[ordinary_source].links == []
    assert history.undo_depth(workspace_id) == 1

    assert history.undo_workspace(workspace_id, workspace) is not None
    scene.refresh_workspace_from_model(workspace_id)
    assert pool in workspace.nodes
    assert workspace.nodes[setup].links[0].target_node_id == pool
    assert workspace.nodes[ordinary_source].links[0].target_node_id == pool

    assert history.redo_workspace(workspace_id, workspace) is not None
    scene.refresh_workspace_from_model(workspace_id)
    assert pool not in workspace.nodes
    assert workspace.nodes[setup].links == []
    assert workspace.nodes[ordinary_source].links == []


def test_pool_context_menu_routes_only_pool_link_actions(qapp) -> None:  # noqa: ANN001
    source = (
        _REPO_ROOT
        / "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasContextMenus.qml"
    ).read_text(encoding="utf-8")

    assert 'typeId === "optimization.parameter_pool"' in source
    assert 'typeId === "optimization.response_pool"' in source
    assert "parameter_setup_link_options(nodeId)" in source
    assert "parameter_setup_link_status(nodeId)" in source
    assert '"text": "Unlink from Parameter Setup"' in source
    assert '"Link to Parameter Setup: " + title' in source
    assert "bridge.link_parameter_setup(nodeId, setupNodeId)" in source
    assert "bridge.unlink_parameter_setup(nodeId)" in source

    component_directory = (
        _REPO_ROOT / "ea_node_editor/ui_qml/components/graph_canvas"
    ).as_posix()
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{component_directory}" as GraphCanvasComponents

        Item {{
            GraphCanvasComponents.GraphCanvasContextMenus {{}}
        }}
        """.encode("utf-8"),
        QUrl("parameter-setup-pool-context-menu-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, "\n".join(
        error.toString() for error in component.errors()
    )
    probe = component.create()
    assert probe is not None
    qapp.processEvents()
