from __future__ import annotations

import hashlib
import json
import os
import queue
from pathlib import Path
from typing import Any

import pytest

from ea_node_editor.common.scene_protocol import ENGINEERING_SELECTION_SCHEMA
from ea_node_editor.execution.protocol_codec import (
    coerce_start_run_command,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.viewer_backend_engineering import (
    ENGINEERING_VIEWER_BACKEND_ID,
)
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    VIEWER_SESSION_DATA_TYPE_ID,
    DataTree,
    RuntimeHandleRef,
    deserialize_runtime_value,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "engineering_viewer"
PROJECT_PATH = EXAMPLE_DIR / "engineering_viewer_capabilities.cxproj"
README_PATH = EXAMPLE_DIR / "README.md"
DATA_ROOT = EXAMPLE_DIR / "engineering_viewer_capabilities.data"

WORKSPACE_ID = "ws_engineering_viewer_capabilities"
VIEWER_NODE_ID = "node_engineering_viewer"
CAD_REF = "saved://engineering_viewer.cad_source"
FE_REF = "saved://engineering_viewer.fe_source"

EXPECTED_NODES = {
    "node_cad_source": "io.path_pointer",
    "node_cad_import": "engineering.cad_import",
    "node_fe_source": "io.path_pointer",
    "node_fe_import": "engineering.fe_import",
    VIEWER_NODE_ID: "model.viewer",
    "node_walkthrough": "passive.annotation.group_backdrop",
}

EXPECTED_EDGES = {
    ("node_cad_import", "scene", VIEWER_NODE_ID, "scene_1"),
    ("node_fe_import", "scene", VIEWER_NODE_ID, "scene_2"),
}


@pytest.fixture(scope="module")
def example():  # noqa: ANN201
    registry = build_default_registry()
    project = JsonProjectSerializer(registry=registry).load(str(PROJECT_PATH.resolve()))
    workspace = project.workspaces[project.active_workspace_id]
    return registry, project, workspace


def _resolved_sources(project: Any) -> tuple[Path, Path]:
    store = ProjectArtifactStore.from_project_metadata(
        project_path=PROJECT_PATH.resolve(),
        project_metadata=project.metadata,
    )
    cad_path = store.resolve_managed_path(CAD_REF)
    fe_path = store.resolve_managed_path(FE_REF)
    assert cad_path is not None
    assert fe_path is not None
    return cad_path.resolve(), fe_path.resolve()


def _edge_signatures(workspace: Any) -> set[tuple[str, str, str, str]]:
    return {
        (
            edge.source_node_id,
            edge.source_port_key,
            edge.target_node_id,
            edge.target_port_key,
        )
        for edge in workspace.edges.values()
    }


def _drain_events(event_queue: queue.Queue) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while not event_queue.empty():
        events.append(event_queue.get())
    return events


def test_example_is_discoverable_and_loads_through_the_current_serializer(
    example,
) -> None:  # noqa: ANN001
    _registry, project, workspace = example
    document = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    edge_docs = document["workspaces"][0]["edges"]
    retired_port_keys = {
        "exec",
        "exec_in",
        "exec_out",
        "completed",
        "completed_in",
        "completed_out",
        "failed",
        "failed_in",
        "failed_out",
        "on_failed",
    }

    assert PROJECT_PATH.is_file()
    assert README_PATH.is_file()
    assert document["schema_version"] == 5
    for node_doc in document["workspaces"][0]["nodes"]:
        for metadata_key in ("exposed_ports", "port_labels"):
            assert retired_port_keys.isdisjoint(node_doc.get(metadata_key, {}))
    assert all(edge_doc["enabled"] is True for edge_doc in edge_docs)
    assert all(edge_doc["input_order"] == 0 for edge_doc in edge_docs)
    group_doc = next(
        node
        for node in document["workspaces"][0]["nodes"]
        if node["node_id"] == "node_walkthrough"
    )
    assert group_doc["properties"] == {"title": "Model Viewer Capabilities"}
    assert group_doc["title"] == group_doc["properties"]["title"]
    assert project.name == "Model Viewer Capabilities"
    assert project.active_workspace_id == WORKSPACE_ID
    assert list(project.workspaces) == [WORKSPACE_ID]
    assert workspace.name == "Model Viewer Capabilities"

    readme = README_PATH.read_text(encoding="utf-8")
    assert PROJECT_PATH.name in readme
    for image_number in range(1, 9):
        assert f"Image #{image_number}" in readme
    assert "engineering_selection_set.v2" in readme
    assert "runtime-only" in readme
    assert "default `5` degrees" in readme


def test_example_contains_the_exact_source_import_viewer_dataflow(example) -> None:  # noqa: ANN001
    _registry, _project, workspace = example

    assert {
        node_id: node.type_id for node_id, node in workspace.nodes.items()
    } == EXPECTED_NODES
    assert _edge_signatures(workspace) == EXPECTED_EDGES

    cad_source = workspace.nodes["node_cad_source"]
    cad_import = workspace.nodes["node_cad_import"]
    fe_source = workspace.nodes["node_fe_source"]
    fe_import = workspace.nodes["node_fe_import"]
    assert cad_source.properties == {
        "mode": "file",
        "must_exist": True,
        "path": CAD_REF,
        "show_full_path": False,
    }
    assert fe_source.properties == {
        "mode": "file",
        "must_exist": True,
        "path": FE_REF,
        "show_full_path": False,
    }
    assert cad_import.properties == {"length_unit": "mm", "path": CAD_REF}
    assert fe_import.properties == {"length_unit": "mm", "path": FE_REF}
    assert not hasattr(cad_import, "locked_ports")
    assert not hasattr(fe_import, "locked_ports")


def test_managed_source_refs_resolve_inside_the_committed_example_sidecar(
    example,
) -> None:  # noqa: ANN001
    _registry, project, _workspace = example
    artifacts = project.metadata["artifact_store"]["artifacts"]

    assert set(artifacts) == {
        "engineering_viewer.cad_source",
        "engineering_viewer.fe_source",
    }
    assert {str(entry["artifact_kind"]) for entry in artifacts.values()} == {
        "engineering_source"
    }
    expected_runtime_artifacts = {
        "engineering_viewer.cad_source": {
            "data_type_id": "COREX.DataTypes.Path",
            "format": "step",
            "provenance": "corex.example.engineering_viewer",
            "schema_version": 1,
            "sha256": (
                "bf222e28abdd7cc6cb66c76209e1f4dde882171e8ec571929d33f8ae8508606a"
            ),
            "size_bytes": 17834,
        },
        "engineering_viewer.fe_source": {
            "data_type_id": "COREX.DataTypes.Path",
            "format": "vtu",
            "provenance": "corex.example.engineering_viewer",
            "schema_version": 1,
            "sha256": (
                "c404bc495c0c48e9b44092ff30d6e9ddaae98bc52ced4c10203685668675af4a"
            ),
            "size_bytes": 158362,
        },
    }
    assert {
        artifact_id: artifacts[artifact_id]["runtime_artifact"]
        for artifact_id in expected_runtime_artifacts
    } == expected_runtime_artifacts
    store = ProjectArtifactStore.from_project_metadata(
        project_path=PROJECT_PATH.resolve(),
        project_metadata=project.metadata,
    )
    for artifact_id, expected_descriptor in expected_runtime_artifacts.items():
        managed_entry = store.managed_entry(artifact_id)
        assert managed_entry is not None
        assert managed_entry.extra["runtime_artifact"] == expected_descriptor

    cad_path, fe_path = _resolved_sources(project)
    assert cad_path.is_file()
    assert fe_path.is_file()
    assert cad_path.is_relative_to(DATA_ROOT.resolve())
    assert fe_path.is_relative_to(DATA_ROOT.resolve())
    assert cad_path.name == "colored_housing.step"
    assert fe_path.name == "rgba_overlay.vtu"
    assert cad_path.suffix.casefold() == ".step"
    assert fe_path.suffix.casefold() == ".vtu"
    for artifact_id, source_path in (
        ("engineering_viewer.cad_source", cad_path),
        ("engineering_viewer.fe_source", fe_path),
    ):
        descriptor = expected_runtime_artifacts[artifact_id]
        assert source_path.stat().st_size == descriptor["size_bytes"]
        assert (
            hashlib.sha256(source_path.read_bytes()).hexdigest() == descriptor["sha256"]
        )
    assert "ISO-10303-21" in cad_path.read_text(encoding="utf-8", errors="strict")[:80]


def test_vtu_source_contains_strict_rgba_and_non_color_engineering_arrays(
    example,
) -> None:  # noqa: ANN001
    np = pytest.importorskip("numpy", reason="The Model Viewer fixture requires NumPy.")
    pyvista = pytest.importorskip(
        "pyvista",
        reason="The Model Viewer fixture requires the optional PyVista viewer dependency.",
    )
    _registry, project, _workspace = example
    _cad_path, fe_path = _resolved_sources(project)

    dataset = pyvista.read(fe_path)
    rgba = np.asarray(dataset.point_data["RGBA"])
    temperature = np.asarray(dataset.point_data["Temperature"])
    displacement = np.asarray(dataset.point_data["Displacement"])
    material_ids = np.asarray(dataset.cell_data["MaterialId"])

    assert rgba.dtype == np.dtype(np.uint8)
    assert rgba.shape == (dataset.n_points, 4)
    assert temperature.shape == (dataset.n_points,)
    assert displacement.shape == (dataset.n_points, 3)
    assert displacement.dtype != np.dtype(np.uint8)
    assert material_ids.shape == (dataset.n_cells,)
    assert material_ids.ndim == 1


def test_viewer_defaults_and_seeded_bookmarks_exercise_the_new_controls(
    example,
) -> None:  # noqa: ANN001
    _registry, _project, workspace = example
    properties = workspace.nodes[VIEWER_NODE_ID].properties

    assert properties["saved_selections"]["schema"] == ENGINEERING_SELECTION_SCHEMA
    assert properties["representation"] == "surface_with_edges"
    assert properties["show_mesh_edges"] is True
    assert properties["show_attribute_colors"] is True
    assert properties["show_orientation_triad"] is True
    assert properties["show_view_cube"] is True
    assert properties["show_world_axes"] is True
    assert properties["parallel_projection"] is False
    assert properties["scene_input_ids"] == ["scene_1", "scene_2"]
    assert properties["scene_styles"]["scene_2"]["opacity"] == pytest.approx(0.32)
    assert properties["scene_styles"]["scene_2"]["color"] == ""

    bookmarks = properties["camera_bookmarks"]
    assert [bookmark["name"] for bookmark in bookmarks] == [
        "ISO Perspective",
        "Front Orthographic",
    ]
    assert [
        bookmark["camera_state"]["parallel_projection"] for bookmark in bookmarks
    ] == [
        False,
        True,
    ]
    for bookmark in bookmarks:
        assert set(bookmark["camera_state"]) == {
            "focal_point",
            "parallel_projection",
            "parallel_scale",
            "position",
            "view_angle",
            "viewup",
            "zoom",
        }


def _run_example_and_get_viewer_session(
    example,
    *, additional_native_body: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:  # noqa: ANN001
    pytest.importorskip(
        "OCP",
        reason="The XCAF STEP fixture requires the optional cadquery-ocp viewer dependency.",
    )
    pytest.importorskip(
        "pyvista",
        reason="The Model Viewer runtime requires the optional PyVista viewer dependency.",
    )
    registry, project, workspace = example
    event_queue: queue.Queue = queue.Queue()
    worker_services = WorkerServices()
    worker_services.bind_data_types(registry.data_types)
    runtime_snapshot = build_runtime_snapshot(
        project,
        workspace_id=workspace.workspace_id,
        registry=registry,
    )

    run_workflow(
        coerce_start_run_command(
            {
                "run_id": "run_engineering_viewer_capabilities_example",
                "project_path": str(PROJECT_PATH.resolve()),
                "workspace_id": workspace.workspace_id,
                "runtime_snapshot": runtime_snapshot,
                "trigger": {},
                "plugin_bundles": registry.plugin_bundle_refs(),
                "plugin_fingerprint": registry.plugin_fingerprint(),
                "registry_contract_fingerprint": registry.contract_fingerprint(),
                "addon_runtime_config": registry.addon_runtime_config(),
            },
            catalog=registry.data_types,
        ),
        event_queue,
        worker_services=worker_services,
    )
    events = _drain_events(event_queue)
    event_types = [str(event.get("type", "")) for event in events]

    assert "run_started" in event_types
    assert "run_completed" in event_types
    assert "run_failed" not in event_types
    failures = [
        event
        for event in events
        if str(event.get("type", "")) == "node_settled"
        and str(event.get("status", "")) in {"failed", "blocked"}
    ]
    assert not failures, (
        f"Model Viewer example emitted failed or blocked results: {failures!r}"
    )

    settled_node_ids = {
        str(event.get("node_id", ""))
        for event in events
        if str(event.get("type", "")) == "node_settled"
        and str(event.get("status", "")) == "completed"
    }
    assert {
        "node_cad_import",
        "node_fe_import",
        VIEWER_NODE_ID,
    }.issubset(settled_node_ids)

    viewer_result = next(
        event
        for event in events
        if str(event.get("type", "")) == "node_settled"
        and str(event.get("node_id", "")) == VIEWER_NODE_ID
    )
    session_result = dict(viewer_result.get("outputs", {}))["session"]
    assert session_result["status"] == "value"
    session_tree = deserialize_runtime_value(
        session_result["value"],
        catalog=registry.data_types,
    )
    assert isinstance(session_tree, DataTree)
    assert session_tree.branch_count == 1
    assert len(session_tree.branches[0][1]) == 1
    session_ref = session_tree.branches[0][1][0]
    assert isinstance(session_ref, RuntimeHandleRef)
    assert session_ref.data_type_id == VIEWER_SESSION_DATA_TYPE_ID
    assert session_ref.kind == COREX_VIEWER_SESSION_HANDLE_KIND
    assert set(session_ref.metadata) == {
        "workspace_id",
        "node_id",
        "session_id",
        "backend_id",
    }
    if additional_native_body:
        from ea_node_editor.nodes.builtins.engineering_viewer import execute_engineering_viewer
        from ea_node_editor.nodes.builtins.geometry_primitives import execute_cylinder
        from ea_node_editor.nodes.builtins.rich_value_nodes import PLANE_DATA_TYPE_ID
        from ea_node_editor.nodes.execution_context import ExecutionContext
        from ea_node_editor.runtime_contracts import Interval1D, TypedInlineValue

        context = ExecutionContext(
            run_id="run_native_third_scene", node_id="native_body", workspace_id=WORKSPACE_ID,
            inputs={"plane": TypedInlineValue(PLANE_DATA_TYPE_ID, 1, {
                "origin": [5.0, 0.0, 0.0], "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                "normal": [0.0, 0.0, 1.0],
            }), "radius": 2.0, "interval": Interval1D(0.0, 5.0)},
            properties={}, emit_log=lambda *_args: None, worker_services=worker_services,
        )
        body = execute_cylinder(context).outputs["body"]
        record = worker_services.viewer_session_service._sessions[(WORKSPACE_ID, session_ref.metadata["session_id"])]
        context.node_id = VIEWER_NODE_ID
        context.inputs = {"scene_1": record.source_refs["scene:scene_1"],
                          "scene_2": record.source_refs["scene:scene_2"], "scene_3": body}
        context.properties = {**workspace.nodes[VIEWER_NODE_ID].properties,
                              "scene_input_ids": ["scene_1", "scene_2", "scene_3"],
                              "scene_styles": {"scene_3": {"color": "#ff0000", "opacity": 0.6}}}
        session_ref = execute_engineering_viewer(context).outputs["session"]
    session = worker_services.resolve_handle(
        session_ref,
        expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
        expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
    )
    assert isinstance(session, dict)
    return session, events


def test_example_runs_solution_and_materializes_exact_viewer_capabilities(
    example,
) -> None:  # noqa: ANN001
    session, _events = _run_example_and_get_viewer_session(example)
    summary = dict(session["summary"])
    capabilities = dict(summary["capabilities"])
    transport = dict(session["transport"])
    primary = dict(transport["layers"][0])
    overlay = dict(transport["layers"][1])

    assert session["backend_id"] == ENGINEERING_VIEWER_BACKEND_ID
    assert session["live_open_status"] == "ready"
    assert session["options"]["live_mode"] == "proxy"
    assert summary["supported_render_modes"] == [
        "surface",
        "surface_with_edges",
        "wireframe",
        "wireframe_visible_edges",
        "points",
    ]
    for capability in (
        "attribute_colors",
        "body_edges",
        "camera_bookmarks",
        "fit_selection",
        "mesh_edges",
        "orientation_triad",
        "projection",
        "selection_isolate",
        "topological_edges",
        "view_cube",
        "wireframe_visible_edges",
        "world_axes",
    ):
        assert capabilities[capability] is True

    assert primary["topological_edge_path"]
    assert primary["attribute_colors"]["available"] is True
    assert primary["attribute_colors"]["array_name"] == "corex_source_rgba"
    assert overlay["attribute_colors"]["available"] is True
    assert overlay["attribute_colors"]["array_name"] == "RGBA"
    assert overlay["attribute_colors"]["association"] == "point"
    assert session["options"]["representation"] == "surface_with_edges"
    assert session["options"]["show_attribute_colors"] is True
    assert session["options"]["show_mesh_edges"] is True


@pytest.mark.gui
@pytest.mark.parametrize("additional_native_body", [False, True])
def test_example_transport_populates_and_captures_the_real_native_viewer(
    example,
    additional_native_body,
) -> None:  # noqa: ANN001
    pytest.importorskip(
        "pyvistaqt", reason="The native Model Viewer requires PyVistaQt."
    )
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QApplication, QWidget

    from ea_node_editor.ui_qml.engineering_viewer_widget_binder import (
        EngineeringViewerWidgetBinder,
    )
    from ea_node_editor.ui_qml.viewer_widget_binder import ViewerWidgetBindRequest

    session, _events = _run_example_and_get_viewer_session(example, additional_native_body=additional_native_body)
    app = QApplication.instance() or QApplication([])
    container = QWidget()
    container.resize(QSize(640, 480))
    container.show()
    app.processEvents()
    options = dict(session["options"])
    options["live_mode"] = "full"
    render_calls: list[None] = []
    native_render = None

    def create_interactor(parent):  # noqa: ANN001, ANN202
        nonlocal native_render
        interactor = EngineeringViewerWidgetBinder._create_interactor(parent)
        native_render = interactor.render
        interactor.render = lambda: render_calls.append(None)
        return interactor

    binder = EngineeringViewerWidgetBinder(
        interactor_factory=create_interactor,
        background_loading=False,
    )
    widget = None
    try:
        request = ViewerWidgetBindRequest(
                workspace_id=WORKSPACE_ID,
                node_id=VIEWER_NODE_ID,
                session_id=str(session["session_id"]),
                backend_id=str(session["backend_id"]),
                transport_revision=int(session["transport_revision"]),
                live_mode="full",
                cache_state=str(session.get("cache_state", "proxy_ready")),
                live_open_status=str(session["live_open_status"]),
                live_open_blocker=dict(session.get("live_open_blocker", {})),
                data_refs=dict(session.get("data_refs", {})),
                transport=dict(session["transport"]),
                camera_state=dict(session.get("camera_state", {})),
                playback_state={
                    "state": str(session.get("playback_state", "paused")),
                    "step_index": int(session.get("step_index", 0)),
                },
                summary=dict(session["summary"]),
                options=options,
                session_model=session,
                container=container,
        )
        widget = binder.bind_widget(request)
        stats = binder.render_stats(widget)
        assert stats["layer_count"] == (3 if additional_native_body else 2)
        assert stats["dataset_count"] >= stats["layer_count"]
        assert not render_calls

        if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM", "").casefold() in {
            "minimal",
            "offscreen",
        }:
            pytest.skip(
                "The Windows VTK wheel requires a display-attached OpenGL renderer."
            )

        assert native_render is not None
        widget.render = native_render
        widget.resize(container.size())
        widget.show()
        binder.refresh_after_attach(widget)
        for _index in range(5):
            app.processEvents()

        if additional_native_body:
            from dataclasses import replace

            original_actor = binder._widget_state[widget].actors["scene_1"]
            actor = binder._widget_state[widget].actors["scene_3"]
            assert actor.GetProperty().GetOpacity() == pytest.approx(0.6)
            automatic = replace(request, current_widget=widget, options={
                **options, "scene_styles": {"scene_3": {"color": "", "opacity": 0.25}},
            })
            assert binder.bind_widget(automatic) is widget
            assert binder._widget_state[widget].actors["scene_1"] is original_actor
            actor = binder._widget_state[widget].actors["scene_3"]
            assert actor.GetProperty().GetOpacity() == pytest.approx(0.25)
            assert actor.GetProperty().GetColor() != (1.0, 0.0, 0.0)
            assert binder.set_layer_visibility(widget, "scene_3", False)
            assert not actor.GetVisibility()
            assert binder.set_layer_visibility(widget, "scene_3", True)

        preview = binder.capture_preview_image(widget)
        assert not preview.isNull()
        assert preview.width() > 1
        assert preview.height() > 1
        sampled_colors = {
            preview.pixelColor(x, y).rgba()
            for x in range(0, preview.width(), max(1, preview.width() // 16))
            for y in range(0, preview.height(), max(1, preview.height() // 16))
        }
        assert len(sampled_colors) > 1
    finally:
        if widget is not None:
            binder.prepare_for_reparent(widget)
            widget.close()
        binder.shutdown()
        container.close()
        app.processEvents()
