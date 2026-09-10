# Purpose: Prove staged canvas imports cross the real process runtime artifact boundary.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_runtime.py
from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QImage

from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.execution.worker_runtime import RuntimeArtifactService
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshotContext
from ea_node_editor.persistence.project_codec import collect_project_artifact_references, rewrite_project_artifact_refs
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import RuntimeArtifactRef
import pytest
from tests.test_canvas_import_controller import import_host  # noqa: F401


def test_imported_image_table_panel_and_annotation_execute_in_real_process(import_host, tmp_path):
    host = import_host
    controller = host.canvas_import_controller
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.green)
    mime = QMimeData()
    mime.setImageData(image)
    assert controller.paste(mime)
    for key in ("panel", "text"):
        host.preferences["interaction"]["canvas_import_mode"] = "ask"
        with patch.object(controller, "_choose", return_value=(key,)):
            assert controller.paste(mime)
    host.preferences["interaction"]["canvas_import_mode"] = "automatic"
    table = QMimeData()
    table.setText("Name\tValue\nOne\t1\nTwo\t2")
    assert controller.paste(table)
    workspace = host.model.active_workspace
    imported_media_id = next(node.node_id for node in workspace.nodes.values() if node.type_id == "media.panel")
    panel_id = next(node.node_id for node in workspace.nodes.values() if node.type_id == "data.panel")
    connected_media_id = host.scene.add_node_from_type("media.panel", 600, 100)
    host.scene.add_edge(panel_id, "output", connected_media_id, "source")
    project = host.model.project
    store = host.project_session_controller.project_artifact_store()
    serializer = JsonProjectSerializer(host.registry)
    for phase in ("staged", "saved", "save-as"):
        project_path = ""
        if phase != "staged":
            project_path = str(tmp_path / f"{phase}.cxproj")
            document = serializer.to_persistent_document(project)
            refs = collect_project_artifact_references(document)
            stage = store.stage_project_save(
                destination_project_path=project_path, workspaces=project.workspaces,
                referenced_managed_ids=refs.managed_ids, referenced_staged_ids=refs.staged_ids,
            )
            document = rewrite_project_artifact_refs(document, stage.ref_replacements)
            document["metadata"]["artifact_store"] = stage.destination_store.metadata
            serializer.save_document(project_path, document)
            project = serializer.load(project_path)
            store = ProjectArtifactStore.from_project_metadata(project_path=project_path, project_metadata=project.metadata)
        workspace = project.workspaces[workspace.workspace_id]
        authored = {node.node_id: dict(node.properties) for node in workspace.nodes.values()}
        runtime = CorexRuntime(registry=host.registry)
        try:
            result = runtime.run(ExecutionRequest(
                project_path=project_path,
                runtime_snapshot=build_runtime_snapshot(project, workspace_id=workspace.workspace_id, registry=host.registry),
                workspace_id=workspace.workspace_id,
                execution_backend="process_isolated",
            ), timeout=40)
            settlements = {event["node_id"]: event for event in result.events if event.get("type") == "node_settled"}
            assert result.status == "completed", result.to_dict()
            for node in workspace.nodes.values():
                if node.type_id == "passive.annotation.text":
                    assert node.properties["text"].startswith("temp://" if phase == "staged" else "saved://")
                    continue
                settled = settlements[node.node_id]
                if node.node_id == imported_media_id:
                    # Authored preview source remains separate from execution's
                    # connected-source authority, including when Source is hidden.
                    assert settled["status"] == "empty", settled
                    continue
                assert settled["status"] == "completed", (node.type_id, settled)
                if node.type_id in {"media.panel", "data.panel"}:
                    port = "_surface_source" if node.type_id == "media.panel" else "output"
                    tree = settled["outputs"][port].value
                    ref = tree.branches[0][1][0]
                    assert isinstance(ref, RuntimeArtifactRef)
                    assert ref.scope == ("staged" if phase == "staged" else "managed")
            assert authored == {node.node_id: dict(node.properties) for node in workspace.nodes.values()}
        finally:
            runtime.shutdown()


def test_authored_property_admission_preserves_runtime_ref_security(import_host):
    host = import_host
    controller = host.canvas_import_controller
    mime = QMimeData()
    mime.setData("application/pdf", b"%PDF-1.7\nbytes")
    assert controller.paste(mime)
    node, = host.model.active_workspace.nodes.values()
    raw_ref = node.properties["source"]
    store = host.project_session_controller.project_artifact_store()
    service = RuntimeArtifactService(
        runtime_context=RuntimeSnapshotContext.from_snapshot(None, artifact_store=store),
        data_types=host.registry.data_types,
    )
    admitted = service.materialize_authored_properties({"source": raw_ref})["source"]
    assert isinstance(admitted, RuntimeArtifactRef)
    for forbidden in (service.materialize_persisted_value, service.resolve_path):
        with pytest.raises(TypeError, match="RuntimeArtifactRef"):
            forbidden(raw_ref)
    with pytest.raises(TypeError, match="RuntimeArtifactRef"):
        service.normalize_outputs({"output": raw_ref})
    with pytest.raises(FileNotFoundError, match="not registered"):
        service.materialize_authored_properties({"source": "temp://unknown"})
    for malformed in (raw_ref.upper(), " " + raw_ref, "temp://bad/../id"):
        with pytest.raises(ValueError, match="malformed"):
            service.materialize_authored_properties({"source": malformed})
    path = store.resolve_staged_path(raw_ref)
    original = path.read_bytes()
    path.write_bytes(b"tampered payload")
    with pytest.raises(ValueError, match="does not match"):
        service.materialize_authored_properties({"source": raw_ref})
    path.write_bytes(original)
    entry = store.staged_entry(raw_ref)
    store.register_staged_entry(admitted.artifact_id, relative_path=entry.relative_path, extra={})
    with pytest.raises(ValueError, match="descriptor is missing"):
        service.materialize_authored_properties({"source": raw_ref})
