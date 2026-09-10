# Purpose: Prove canvas import choices, shared gestures, batching, and owned staging rollback.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_controller.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QObject, QMimeData, QPoint, QPointF, QRect, QTimer, QUrl, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage
from PyQt6.QtWidgets import QDialogButtonBox, QStyle, QStyleOptionButton, QWidget

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.project_codec import collect_project_artifact_references, rewrite_project_artifact_refs
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.shell.canvas_import_dialog import CanvasImportDialog
from ea_node_editor.ui.shell.canvas_drop_capture import CanvasDropCapture
from ea_node_editor.ui.shell.clipboard_paste_nodes import capture_canvas_drop, capture_canvas_mime_data, classify_canvas_import
from ea_node_editor.ui.shell.controllers.canvas_import_controller import CanvasImportController
from ea_node_editor.ui.shell.controllers.project_session_services_support.project_files_service import ProjectFilesService
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.qml_host_factory import create_shell_qml_host


def test_dialog_add_action_label_fits_the_styled_button(qapp):
    sources = classify_canvas_import(capture_canvas_drop(text="Native button check"))
    dialog = CanvasImportDialog(sources, lambda _choice: "")
    try:
        dialog.show()
        qapp.processEvents()
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        option = QStyleOptionButton()
        option.initFrom(button)
        content = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
        assert button.fontMetrics().horizontalAdvance(button.text()) <= content.width()
    finally:
        dialog.close()
        dialog.deleteLater()


class _SceneParent(QObject):
    def __init__(self):
        super().__init__()
        self.invalidate_solution_for_history_action = Mock()


@pytest.fixture
def import_host(tmp_path):
    model = GraphModel()
    registry = build_default_registry()
    parent = _SceneParent()
    scene = GraphSceneBridge(parent)
    history = RuntimeGraphHistory()
    scene.bind_runtime_history(history)
    scene.set_workspace(model, registry, model.active_workspace.workspace_id)
    preferences = {"interaction": {"canvas_import_mode": "automatic"}}
    host = SimpleNamespace(
        model=model, registry=registry, scene=scene, runtime_history=history, parent=parent,
        workspace_manager=SimpleNamespace(active_workspace_id=lambda: model.active_workspace.workspace_id),
        view=SimpleNamespace(viewport=lambda: SimpleNamespace(rect=lambda: QRect(0, 0, 200, 100)),
                             mapToScene=lambda point: QPointF(point)),
        app_preferences_controller=SimpleNamespace(graphics_settings=lambda: preferences),
        preferences=preferences, project_path=None,
        session_store=SimpleNamespace(staging_workspace_root=lambda: tmp_path),
    )
    host.project_session_controller = ProjectFilesService(
        host, dialog_parent_source=host, path_browser=None, workspace_session=None,
    )
    host.effects = SimpleNamespace(after_fragment_pasted=Mock())
    host.canvas_import_controller = CanvasImportController(host, effects=host.effects)
    host.canvas_import_controller._report_failures = Mock()
    yield host
    scene.setParent(None)
    scene.deleteLater()


@pytest.mark.parametrize("gesture", ["paste", "drop"])
def test_mixed_automatic_mapping_batch_history_and_url_spelling(import_host, qapp, gesture):
    host = import_host
    urls = [QUrl.fromLocalFile("C:/Inputs/photo.png"), QUrl.fromLocalFile("C:/Inputs/report.pdf"),
            QUrl.fromLocalFile("C:/Inputs/movie.mp4"), QUrl.fromLocalFile("C:/Inputs/mail.eml"),
            QUrl.fromLocalFile("C:/Inputs/page.html"), QUrl.fromLocalFile("C:/Inputs/run.py"),
            QUrl("https://example.test/a.mp4?token=A%2Fb#t=3"), QUrl("https://example.test/page?q=X#part")]
    mime = QMimeData()
    mime.setUrls(urls)
    controller = host.canvas_import_controller
    if gesture == "paste":
        assert controller.paste(mime)
    else:
        assert controller.drop(urls, "", "", 123, 456)
        assert not host.model.active_workspace.nodes
        qapp.processEvents()
    workspace = host.model.active_workspace
    nodes = list(workspace.nodes.values())
    assert [node.type_id for node in nodes] == ["media.panel", "media.panel", "media.panel",
        "passive.media.mail_panel", "web.page_viewer", "io.path_pointer", "media.panel", "web.page_viewer"]
    assert nodes[6].properties["source"] == "https://example.test/a.mp4?token=A%2Fb#t=3"
    assert nodes[7].properties["start_location"] == "https://example.test/page?q=X#part"
    assert all(not node.exposed_ports["source"] for node in nodes if node.type_id == "media.panel")
    assert host.runtime_history.undo_depth(workspace.workspace_id) == 1
    assert host.parent.invalidate_solution_for_history_action.call_count == 1
    assert (nodes[0].x, nodes[0].y) == ((99, 49) if gesture == "paste" else (123, 456))
    host.runtime_history.undo_workspace(workspace.workspace_id, workspace)
    assert not workspace.nodes
    host.runtime_history.redo_workspace(workspace.workspace_id, workspace)
    assert len(workspace.nodes) == 8


@pytest.mark.parametrize("gesture", ["paste", "drop"])
@pytest.mark.parametrize("kind,type_id", [
    ("screenshot", "media.panel"), ("pdf", "media.panel"), ("video", "media.panel"),
    ("tsv", "tabular.input"), ("html_table", "tabular.input"),
    ("text", "passive.annotation.text"), ("html", "passive.annotation.text"),
    ("folder", "io.path_pointer"),
])
def test_automatic_content_matrix_uses_same_pipeline_for_both_gestures(import_host, qapp, tmp_path, gesture, kind, type_id):
    host = import_host
    mime = QMimeData()
    if kind == "screenshot":
        image = QImage(2, 2, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        mime.setImageData(image)
    elif kind == "pdf":
        mime.setData("application/pdf", b"%PDF-1.7\nraw")
    elif kind == "video":
        mime.setData("video/mp4", b"\x00\x00\x00\x18ftypmp42")
    elif kind == "tsv":
        mime.setText("A\tB\n1\t2")
    elif kind == "html_table":
        mime.setHtml("<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>")
    elif kind == "text":
        mime.setText("  Keep literal text  ")
    elif kind == "html":
        mime.setHtml("<h1>Heading</h1><p>Formatted text</p>")
    else:
        folder = tmp_path / "folder"
        folder.mkdir()
        mime.setUrls([QUrl.fromLocalFile(str(folder))])
    controller = host.canvas_import_controller
    if gesture == "paste":
        assert controller.paste(mime)
    else:
        controller.capture_native_drop(mime)
        assert controller.drop([], "", "", 12, 34)
        qapp.processEvents()
    node, = host.model.active_workspace.nodes.values()
    assert node.type_id == type_id
    if kind in {"screenshot", "pdf", "video"}:
        assert node.properties["source"].startswith("temp://")
    elif kind in {"tsv", "html_table"}:
        path = host.project_session_controller.project_artifact_store().resolve_staged_path(node.properties["path"])
        assert path.read_text(encoding="utf-8") == "A\tB\n1\t2\n"
    elif kind == "text":
        assert node.properties["text"] == "  Keep literal text  "
    elif kind == "html":
        assert node.properties["format"] == "markdown"
    else:
        assert node.properties["mode"] == "folder"


@pytest.mark.parametrize("mode,expected_type", [("automatic", "media.panel"), ("ask", "data.panel")])
def test_folder_explorer_direct_release_uses_current_import_mode(import_host, qapp, mode, expected_type):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = mode
    with patch.object(host.canvas_import_controller, "_choose", return_value=("panel",)) as chooser:
        assert host.canvas_import_controller.drop_local_path("C:/images/photo.png", False, 20, 30)
        qapp.processEvents()
    node, = host.model.active_workspace.nodes.values()
    assert node.type_id == expected_type
    assert chooser.call_count == int(mode == "ask")
    if mode == "ask":
        assert node.properties["value"] == "C:/images/photo.png"


@pytest.mark.parametrize("key,property_key", [("text", "text"), ("panel", "value")])
def test_literal_choice_preserves_whitespace_and_panel_text_mode(import_host, key, property_key):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = "ask"
    mime = QMimeData()
    mime.setText("  001.20\n\tLiteral  ")
    with patch.object(host.canvas_import_controller, "_choose", return_value=(key,)):
        assert host.canvas_import_controller.paste(mime)
    node, = host.model.active_workspace.nodes.values()
    assert node.properties[property_key] == mime.text()
    if key == "panel":
        assert node.properties["mode"] == 0
        assert node.properties["interpretation"] == "text"


@pytest.mark.parametrize("change", ["cancel", "skip", "scope", "project"])
def test_chooser_cancel_or_changed_destination_has_no_effect(import_host, change):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = "ask"
    mime = QMimeData()
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    mime.setImageData(image)
    initial_metadata = dict(host.model.project.metadata)
    def choose(sources):
        if change == "scope":
            host.scene._scope_path = ("no-longer-valid",)
        if change == "project":
            host.model = GraphModel()
        return None if change == "cancel" else ("skip" if change == "skip" else "text",)
    with patch.object(host.canvas_import_controller, "_choose", side_effect=choose):
        assert not host.canvas_import_controller.paste(mime)
    assert not host.model.active_workspace.nodes
    assert host.model.project.metadata == initial_metadata
    assert host.effects.after_fragment_pasted.call_count == 0
    assert not host.project_session_controller.project_artifact_store().state.staged


@pytest.mark.parametrize("key,property_key", [("text", "text"), ("panel", "value"), ("media", "source")])
def test_raw_image_choice_stages_exact_managed_reference(import_host, key, property_key):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = "ask"
    mime = QMimeData()
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    mime.setImageData(image)
    def choose(sources):
        assert not host.project_session_controller.project_artifact_store().state.staged
        assert sources[0].choice("text").explanation
        return (key,)
    with patch.object(host.canvas_import_controller, "_choose", side_effect=choose):
        assert host.canvas_import_controller.paste(mime)
    node, = host.model.active_workspace.nodes.values()
    ref = node.properties[property_key]
    assert ref.startswith("temp://")
    store = host.project_session_controller.project_artifact_store()
    assert store.resolve_staged_path(ref).read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("key,property_key", [("text", "text"), ("panel", "value")])
def test_screenshot_literal_reference_survives_save_reopen_and_save_as(import_host, tmp_path, key, property_key):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = "ask"
    mime = QMimeData()
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    mime.setImageData(image)
    with patch.object(host.canvas_import_controller, "_choose", return_value=(key,)):
        assert host.canvas_import_controller.paste(mime)
    serializer = JsonProjectSerializer(host.registry)
    project = host.model.project
    store = host.project_session_controller.project_artifact_store()
    for name in ("first", "save-as-copy"):
        target = tmp_path / f"{name}.cxproj"
        document = serializer.to_persistent_document(project)
        refs = collect_project_artifact_references(document)
        stage = store.stage_project_save(
            destination_project_path=target, workspaces=project.workspaces,
            referenced_managed_ids=refs.managed_ids, referenced_staged_ids=refs.staged_ids,
        )
        document = rewrite_project_artifact_refs(document, stage.ref_replacements)
        document["metadata"]["artifact_store"] = stage.destination_store.metadata
        serializer.save_document(str(target), document)
        project = serializer.load(str(target))
        node, = next(iter(project.workspaces.values())).nodes.values()
        ref = node.properties[property_key]
        assert ref.startswith("saved://")
        store = ProjectArtifactStore.from_project_metadata(project_path=target, project_metadata=project.metadata)
        assert store.resolve_managed_path(ref).read_bytes().startswith(b"\x89PNG")


def test_failure_after_staging_rolls_back_only_failed_item(import_host):
    host = import_host
    controller = host.canvas_import_controller
    source = capture_canvas_drop(text="Keep this node")
    assert controller._import(source, controller._destination((0, 0)), paste=True)
    old_id, = host.model.active_workspace.nodes
    old_depth = host.runtime_history.undo_depth(host.model.active_workspace.workspace_id)
    keep_ref = host.project_session_controller.stage_node_artifact_bytes(
        b"keep", filename="keep.bin", mime_type="application/octet-stream", artifact_prefix="keep",
        subdirectory="test", artifact_kind="test", node_id=old_id,
    )
    mime = QMimeData()
    mime.setData("application/pdf", b"%PDF-1.7\nraw bytes")
    with patch.object(ValidatedGraphMutation, "set_node_properties", side_effect=ValueError("property failure")):
        assert not controller.paste(mime)
    assert set(host.model.active_workspace.nodes) == {old_id}
    store = host.project_session_controller.project_artifact_store()
    assert len(store.state.staged) == 1
    assert store.resolve_staged_path(keep_ref).read_bytes() == b"keep"
    assert host.runtime_history.undo_depth(host.model.active_workspace.workspace_id) == old_depth
    assert "property failure" in str(controller._report_failures.call_args)


def test_unavailable_auto_choice_reports_without_substitution(import_host):
    host = import_host
    mime = QMimeData()
    mime.setText("a\tb\n1\t2")
    with patch.object(host.registry, "spec_or_none", return_value=None):
        assert not host.canvas_import_controller.paste(mime)
    assert not host.model.active_workspace.nodes
    assert "unavailable" in str(host.canvas_import_controller._report_failures.call_args)


def test_post_staging_publication_failure_rolls_back_node_and_copy(import_host):
    host = import_host
    mime = QMimeData()
    mime.setData("application/pdf", b"%PDF-1.7\nraw")
    context = host.scene._scene_context
    with patch.object(context, "sync_surface_title", side_effect=ValueError("publication failed")):
        assert not host.canvas_import_controller.paste(mime)
    assert not host.model.active_workspace.nodes
    assert not host.project_session_controller.project_artifact_store().state.staged
    assert not host.runtime_history.can_undo(host.model.active_workspace.workspace_id)


def test_failed_batch_item_retains_successes_and_one_history_entry(import_host):
    host = import_host
    controller = host.canvas_import_controller
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/good.txt"), QUrl.fromLocalFile("C:/bad.png"), QUrl.fromLocalFile("C:/also-good.txt")])
    context = host.scene._scene_context
    sync = context.sync_surface_title
    def fail_image(node, spec):
        if node.type_id == "media.panel":
            raise ValueError("Cannot publish image")
        return sync(node, spec)
    with patch.object(context, "sync_surface_title", side_effect=fail_image):
        assert controller.paste(mime)
    workspace = host.model.active_workspace
    assert [node.properties["path"] for node in workspace.nodes.values()] == ["C:/good.txt", "C:/also-good.txt"]
    assert host.runtime_history.undo_depth(workspace.workspace_id) == 1
    assert "Cannot publish image" in str(controller._report_failures.call_args)


def test_repeated_paste_cascade_and_nested_scope(import_host):
    host = import_host
    subnode = host.scene.add_node_from_type("core.subnode", 0, 0)
    host.scene._scope_path = (subnode,)
    mime = QMimeData()
    mime.setText("Note")
    assert host.canvas_import_controller.paste(mime)
    assert host.canvas_import_controller.paste(mime)
    notes = [node for node in host.model.active_workspace.nodes.values() if node.node_id != subnode]
    assert [node.parent_node_id for node in notes] == [subnode, subnode]
    assert [(node.x, node.y) for node in notes] == [(99, 49), (139, 89)]


@pytest.mark.parametrize("close_kind", ["shutdown", "flag", "deleted_parent"])
def test_queued_import_aborts_after_shell_close(import_host, qapp, close_kind):
    from PyQt6 import sip
    host = import_host
    controller = host.canvas_import_controller
    assert controller.drop([], "queued before close", "", 0, 0)
    if close_kind == "shutdown":
        controller.shutdown()
    elif close_kind == "flag":
        host._shell_teardown_started = True
    else:
        host.dialog_parent_host = QWidget()
        sip.delete(host.dialog_parent_host)
    qapp.processEvents()
    assert not host.model.active_workspace.nodes
    host.effects.after_fragment_pasted.assert_not_called()


def test_shutdown_rejects_open_chooser_without_importing(import_host):
    host = import_host
    host.preferences["interaction"]["canvas_import_mode"] = "ask"
    mime = QMimeData()
    mime.setText("Do not add after close")
    QTimer.singleShot(0, host.canvas_import_controller.shutdown)
    assert not host.canvas_import_controller.paste(mime)
    assert host.canvas_import_controller._active_dialog is None
    assert not host.model.active_workspace.nodes


@pytest.mark.parametrize("host_kind", ["qquickwidget", "qquickview_container"])
@pytest.mark.parametrize("consume_target", [False, True])
def test_native_raw_drop_delivery_is_captured_before_qml_and_target_priority_preserved(import_host, qapp, tmp_path, host_kind, consume_target):
    host = import_host
    window = QWidget()
    qml_host = create_shell_qml_host(window, host_kind=host_kind)
    surface = qml_host.quick_window() if host_kind == "qquickview_container" else qml_host.event_filter_widget
    capture = CanvasDropCapture(surface, host.canvas_import_controller)
    bridge = GraphCanvasCommandBridge(canvas_import_controller=host.canvas_import_controller)
    qml_host.root_context().setContextProperty("importBridge", bridge)
    qml_path = tmp_path / "native_drop.qml"
    qml_path.write_text('''import QtQuick 2.15
Rectangle {
    width: 200; height: 100
    property bool consumeTarget: false
    DropArea {
        anchors.fill: parent
        keys: ["application/pdf"]
        onEntered: function(drag) { drag.accept(Qt.CopyAction); }
        onDropped: function(drop) {
            if (!parent.consumeTarget)
                importBridge.request_canvas_import_drop([], "", "", drop.x, drop.y);
            drop.accept(Qt.CopyAction);
        }
    }
}''', encoding="utf-8")
    qml_host.set_source(QUrl.fromLocalFile(str(qml_path)))
    qml_host.container_widget.resize(200, 100)
    qml_host.container_widget.show()
    window.show()
    qapp.processEvents()
    assert qml_host.root_object() is not None, [error.toString() for error in qml_host.errors()]
    qml_host.root_object().setProperty("consumeTarget", consume_target)
    mime = QMimeData()
    mime.setData("application/pdf", b"%PDF-1.7\nnative payload")
    try:
        enter = QDragEnterEvent(QPoint(40, 50), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(surface, enter)
        move = QDragMoveEvent(QPoint(40, 50), Qt.DropAction.CopyAction, mime,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(surface, move)
        drop = QDropEvent(QPointF(40, 50), Qt.DropAction.CopyAction, mime,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(surface, drop)
        assert drop.isAccepted()
        assert not host.model.active_workspace.nodes  # queued after native dispatch
        mime.setData("application/pdf", b"changed after dispatch")
        qapp.processEvents()
        assert host.canvas_import_controller._pending_drop is None
        if consume_target:
            assert not host.model.active_workspace.nodes
        else:
            node, = host.model.active_workspace.nodes.values()
            path = host.project_session_controller.project_artifact_store().resolve_staged_path(node.properties["source"])
            assert path.read_bytes() == b"%PDF-1.7\nnative payload"
            assert (node.x, node.y) == (40, 50)
    finally:
        surface.removeEventFilter(capture)
        qml_host.teardown()
        window.close()
        window.deleteLater()


def test_dialog_common_choices_individual_overrides_and_unavailable_explanation(import_host):
    host = import_host
    sources = classify_canvas_import(capture_canvas_drop(["C:/a.png", "C:/notes.txt"]))
    dialog = CanvasImportDialog(sources, host.canvas_import_controller.unavailable_reason)
    assert dialog.windowTitle() == "Add to Canvas"
    assert dialog.selected_keys() == ("media", "path")
    assert {dialog.bulk_combo.itemData(i) for i in range(dialog.bulk_combo.count())} == {"detected", "path", "text", "panel", "skip"}
    dialog._set_all(dialog.bulk_combo.findData("panel"))
    assert dialog.selected_keys() == ("panel", "panel")
    dialog.choice_combos[0].setCurrentIndex(dialog.choice_combos[0].findData("text"))
    assert dialog.selected_keys() == ("text", "panel")
    dialog._set_all(dialog.bulk_combo.findData("detected"))
    assert dialog.selected_keys() == ("media", "path")
    dialog.reject()
    dialog.deleteLater()
    sources = classify_canvas_import(capture_canvas_drop(text="a\tb\n1\t2"))
    dialog = CanvasImportDialog(sources, lambda choice: "Enable Tabular" if choice.key == "tabular" else "")
    combo = dialog.choice_combos[0]
    assert not combo.model().item(combo.findData("tabular")).isEnabled()
    assert combo.itemData(combo.findData("tabular"), Qt.ItemDataRole.ToolTipRole) == "Enable Tabular"
    dialog.deleteLater()
