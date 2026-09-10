from __future__ import annotations

import json
from pathlib import Path

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.project_codec import JsonProjectCodec


def _project_with_plot_workflow(tmp_path: Path, *, rows: int = 10_000) -> tuple[GraphModel, str, str]:
    source = tmp_path / "large.csv"
    lines = ["time,value"]
    lines.extend(f"{index},{index * 0.5}" for index in range(rows))
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    tabular = model.add_node(
        workspace_id,
        "tabular.input",
        "Tabular",
        0.0,
        0.0,
        properties={"path": str(source)},
    )
    plot = model.add_node(
        workspace_id,
        "plot.scatter",
        "Line Plot",
        300.0,
        0.0,
        properties={"tabular_mapping": {"x": "time", "y": ["value"]}},
    )
    model.add_edge(workspace_id, tabular.node_id, "table_data", plot.node_id, "series")
    return model, workspace_id, plot.node_id


def test_saved_project_with_plot_workflow_stays_small_and_series_free(tmp_path: Path) -> None:
    registry = build_default_registry()
    model, workspace_id, plot_node_id = _project_with_plot_workflow(tmp_path)

    # Simulate the scene payload build that used to leak series data around.
    from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder

    GraphScenePayloadBuilder().rebuild_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )

    codec = JsonProjectCodec(registry)
    document = codec.to_persistent_document(model.project)
    serialized = json.dumps(document)

    assert '"preview_series"' not in serialized
    assert len(serialized.encode("utf-8")) < 256 * 1024
    plot_doc = next(
        node
        for workspace in document["workspaces"]
        for node in workspace["nodes"]
        if node["node_id"] == plot_node_id
    )
    assert "preview_series" not in plot_doc["properties"]


def test_legacy_preview_series_is_stripped_on_load_and_save(tmp_path: Path) -> None:
    registry = build_default_registry()
    model, _workspace_id, plot_node_id = _project_with_plot_workflow(tmp_path, rows=10)
    codec = JsonProjectCodec(registry)
    document = codec.to_persistent_document(model.project)

    legacy_series = [{"label": "legacy", "x": list(range(1000)), "y": list(range(1000))}]
    for workspace in document["workspaces"]:
        for node in workspace["nodes"]:
            if node["node_id"] == plot_node_id:
                node["properties"]["preview_series"] = legacy_series

    loaded = codec.from_document(document)
    loaded_plot = next(
        node
        for workspace in loaded.workspaces.values()
        for node in workspace.nodes.values()
        if node.node_id == plot_node_id
    )
    assert "preview_series" not in loaded_plot.properties

    resaved = codec.to_persistent_document(loaded)
    # Match the quoted JSON key: the pytest tmp_path embeds this test's name
    # (and therefore the substring "preview_series") in the source path value.
    assert '"preview_series"' not in json.dumps(resaved)
