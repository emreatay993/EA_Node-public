from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

import ea_node_editor.ui.shell.presenters.graph_canvas_host_presenter as presenter_module
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.presenters.graph_canvas_host_presenter import GraphCanvasHostPresenter
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class _RecordingTabularPreviewProvider:
    instances: list["_RecordingTabularPreviewProvider"] = []

    def __init__(self, *, project_context_provider: Any) -> None:
        self.project_context_provider = project_context_provider
        self.calls: list[tuple[Any, Any, str]] = []
        self.contexts: list[tuple[str | None, dict[str, Any] | None]] = []
        self.instances.append(self)

    def describe_preview(
        self,
        properties_or_source: Any,
        request: Any = None,
        *,
        mode: str = "inline",
    ) -> dict[str, Any]:
        self.calls.append((properties_or_source, request, mode))
        self.contexts.append(self.project_context_provider())
        return {"call_count": len(self.calls)}


class _SignalStub:
    def __init__(self) -> None:
        self.emit_count = 0

    def emit(self) -> None:
        self.emit_count += 1


class _ProjectSessionStub:
    def __init__(self) -> None:
        self.persist_count = 0

    def ensure_project_metadata_defaults(self) -> None:
        return None

    def persist_session(self) -> None:
        self.persist_count += 1


class _CursorTarget:
    def __init__(self) -> None:
        self.shapes: list[Qt.CursorShape] = []
        self.clear_count = 0

    def setCursor(self, cursor) -> None:  # noqa: N802, ANN001
        self.shapes.append(cursor.shape())

    def unsetCursor(self) -> None:  # noqa: N802
        self.clear_count += 1


class _QuickWidgetStub(_CursorTarget):
    def __init__(self) -> None:
        super().__init__()
        self.window = _CursorTarget()

    def quickWindow(self):  # noqa: N802, ANN201
        return self.window


def _style_fixture(
    *,
    quick_widget: object | None = None,
) -> tuple[
    GraphCanvasHostPresenter,
    SimpleNamespace,
    GraphModel,
    GraphSceneBridge,
    _ProjectSessionStub,
    _SignalStub,
]:
    QApplication.instance() or QApplication([])
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace_id)
    session = _ProjectSessionStub()
    project_meta_changed = _SignalStub()
    host = SimpleNamespace(
        project_path="",
        model=model,
        registry=registry,
        workspace_manager=SimpleNamespace(
            active_workspace_id=lambda: model.active_workspace.workspace_id
        ),
        scene=scene,
        project_session_controller=session,
        project_meta_changed=project_meta_changed,
        search_scope_controller=SimpleNamespace(),
        workspace_edit_controller=SimpleNamespace(),
        quick_widget=quick_widget,
    )
    return (
        GraphCanvasHostPresenter(host),
        host,
        model,
        scene,
        session,
        project_meta_changed,
    )


def test_graph_canvas_host_presenter_reuses_tabular_preview_provider(monkeypatch) -> None:
    _RecordingTabularPreviewProvider.instances = []
    monkeypatch.setattr(
        presenter_module,
        "TabularPreviewProvider",
        _RecordingTabularPreviewProvider,
    )
    host = SimpleNamespace(
        project_path="C:/project/example.cxproj",
        model=SimpleNamespace(project=SimpleNamespace(metadata={"artifact_root": "assets"})),
        search_scope_controller=SimpleNamespace(),
        scene=SimpleNamespace(),
        shell_host_presenter=SimpleNamespace(),
        workspace_edit_controller=SimpleNamespace(),
    )
    presenter = GraphCanvasHostPresenter(host)

    first = presenter.describe_tabular_preview({"source": "table.csv"}, {"row_limit": 50})
    second = presenter.describe_tabular_preview({"source": "table.csv"}, {"row_limit": 50})

    assert first == {"call_count": 1}
    assert second == {"call_count": 2}
    assert len(_RecordingTabularPreviewProvider.instances) == 1
    provider = _RecordingTabularPreviewProvider.instances[0]
    assert provider.calls == [
        ({"source": "table.csv"}, {"row_limit": 50}, "inline"),
        ({"source": "table.csv"}, {"row_limit": 50}, "inline"),
    ]
    assert provider.contexts == [
        ("C:/project/example.cxproj", {"artifact_root": "assets"}),
        ("C:/project/example.cxproj", {"artifact_root": "assets"}),
    ]
    presenter.shutdown()


def test_graph_canvas_host_presenter_opens_local_file_sources(monkeypatch, tmp_path) -> None:
    host = SimpleNamespace(
        project_path="",
        model=SimpleNamespace(project=SimpleNamespace(metadata={})),
        search_scope_controller=SimpleNamespace(),
        scene=SimpleNamespace(),
        shell_host_presenter=SimpleNamespace(),
        workspace_edit_controller=SimpleNamespace(),
    )
    presenter = GraphCanvasHostPresenter(host)
    mail_path = tmp_path / "message.eml"
    mail_path.write_text("Subject: Hello\n\nBody", encoding="utf-8")
    default_opened: list[object] = []
    chooser_opened: list[object] = []

    monkeypatch.setattr(
        presenter_module,
        "open_path_with_default_handler",
        lambda path: default_opened.append(path) or True,
    )
    monkeypatch.setattr(
        presenter_module,
        "open_path_with_app_chooser",
        lambda path: chooser_opened.append(path) or True,
    )

    default_result = presenter.open_local_file_source(str(mail_path), False)
    chooser_result = presenter.open_local_file_source(str(mail_path), True)
    missing_result = presenter.open_local_file_source(str(tmp_path / "missing.eml"), False)
    monkeypatch.setattr(presenter_module, "open_path_with_default_handler", lambda _path: False)
    failed_result = presenter.open_local_file_source(str(mail_path), False)

    assert default_result == {"success": True, "path": str(mail_path), "error": {}}
    assert chooser_result == {"success": True, "path": str(mail_path), "error": {}}
    assert missing_result["success"] is False
    assert missing_result["error"]["code"] == "missing_file"
    assert failed_result["success"] is False
    assert failed_result["error"]["code"] == "open_failed"
    assert default_opened == [mail_path]
    assert chooser_opened == [mail_path]
    presenter.shutdown()


def test_graph_canvas_host_presenter_applies_cursor_to_widget_and_quick_window() -> None:
    quick_widget = _QuickWidgetStub()
    presenter, _host, _model, _scene, _session, _signal = _style_fixture(
        quick_widget=quick_widget,
    )
    try:
        presenter.set_graph_cursor_shape(Qt.CursorShape.CrossCursor.value)
        presenter.set_graph_cursor_shape(999_999)
        presenter.clear_graph_cursor_shape()

        assert quick_widget.shapes == [
            Qt.CursorShape.CrossCursor,
            Qt.CursorShape.ArrowCursor,
        ]
        assert quick_widget.window.shapes == quick_widget.shapes
        assert quick_widget.clear_count == 1
        assert quick_widget.window.clear_count == 1
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_edits_styles_through_exact_scene_owner() -> None:
    presenter, _host, model, scene, _session, _signal = _style_fixture()
    workspace = model.active_workspace
    node_id = scene.add_node_from_type("passive.flowchart.process", 100.0, 80.0)
    target_id = scene.add_node_from_type("passive.flowchart.decision", 360.0, 80.0)
    edge_id = scene.add_edge(node_id, "right", target_id, "left")
    try:
        presenter.edit_passive_node_style = lambda _node_id: {"fill_color": "#112233"}  # type: ignore[method-assign]
        presenter.edit_flow_edge_style = lambda _edge_id: {"stroke_color": "#445566"}  # type: ignore[method-assign]

        assert presenter.request_edit_passive_node_style(node_id)
        assert presenter.request_edit_flow_edge_style(edge_id)
        assert workspace.nodes[node_id].visual_style == {"fill_color": "#112233"}
        assert workspace.edges[edge_id].visual_style == {"stroke_color": "#445566"}
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_owns_passive_style_clipboard_and_mutations() -> None:
    presenter, _host, model, scene, _session, _signal = _style_fixture()
    workspace = model.active_workspace
    app = QApplication.instance()
    assert app is not None
    clipboard = app.clipboard()
    source_id = scene.add_node_from_type("passive.flowchart.process", 100.0, 80.0)
    target_id = scene.add_node_from_type("passive.flowchart.decision", 360.0, 80.0)
    disconnected_id = scene.add_node_from_type("passive.flowchart.process", 620.0, 80.0)
    standard_id = scene.add_node_from_type("core.logger", 900.0, 80.0)
    scene.add_edge(source_id, "right", target_id, "left")
    style = {
        "fill_color": "#00CEC9",
        "border_color": "#0984E3",
        "text_color": "#2D3436",
        "border_width": 3.0,
    }
    legacy_style = {
        **style,
        "accent_color": "#112233",
        "header_color": "#223344",
    }
    scene.set_node_visual_style(source_id, legacy_style)
    workspace.nodes[target_id].visual_style = {"fill_color": "#FFEAA7"}
    workspace.nodes[disconnected_id].visual_style = {"fill_color": "#FAB1A0"}
    workspace.nodes[standard_id].visual_style = {"fill_color": "#D63031"}
    clipboard.setText("external clipboard text")
    app.setProperty(
        f"{presenter_module._STYLE_CLIPBOARD_APP_PROPERTY}:"
        f"{presenter_module._PASSIVE_NODE_STYLE_CLIPBOARD_KIND}",
        "",
    )
    try:
        assert not presenter.request_edit_passive_node_style(standard_id)
        assert presenter.request_copy_passive_node_style(source_id)
        assert clipboard.text() == "external clipboard text"
        assert presenter.request_paste_passive_node_style(target_id)
        assert workspace.nodes[target_id].visual_style == style
        assert presenter.request_reset_passive_node_style(target_id)
        assert workspace.nodes[target_id].visual_style == {}

        app.setProperty(
            f"{presenter_module._STYLE_CLIPBOARD_APP_PROPERTY}:"
            f"{presenter_module._PASSIVE_NODE_STYLE_CLIPBOARD_KIND}",
            "",
        )
        clipboard.setText(
            '{"kind":"passive-node-style","version":1,"style":{"fill_color":"#FFEAA7"}}'
        )
        assert not presenter.request_paste_passive_node_style(target_id)
        assert workspace.nodes[target_id].visual_style == {}

        scene.set_node_visual_style(source_id, legacy_style)
        assert presenter.request_propagate_passive_node_style(source_id)
        assert workspace.nodes[source_id].visual_style == legacy_style
        assert workspace.nodes[target_id].visual_style == style
        assert workspace.nodes[disconnected_id].visual_style == {"fill_color": "#FAB1A0"}
        assert workspace.nodes[standard_id].visual_style == {"fill_color": "#D63031"}
        assert not presenter.request_copy_passive_node_style(standard_id)
        assert not presenter.request_paste_passive_node_style(standard_id)
        assert not presenter.request_propagate_passive_node_style(standard_id)
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_owns_flow_style_label_and_clipboard(monkeypatch) -> None:
    presenter, host, model, scene, _session, _signal = _style_fixture()
    workspace = model.active_workspace
    app = QApplication.instance()
    assert app is not None
    clipboard = app.clipboard()
    source_id = scene.add_node_from_type("passive.flowchart.process", 80.0, 60.0)
    target_id = scene.add_node_from_type("passive.flowchart.decision", 360.0, 60.0)
    flow_edge_id = scene.add_edge(source_id, "top", target_id, "bottom")
    sibling_edge_id = scene.add_edge(target_id, "right", source_id, "left")
    constant_id = scene.add_node_from_type("core.constant", 80.0, 260.0)
    logger_id = scene.add_node_from_type("core.logger", 380.0, 260.0)
    data_edge_id = scene.add_edge(constant_id, "as_text", logger_id, "message")
    style = {
        "stroke_color": "#224466",
        "stroke_width": 3.5,
        "stroke_pattern": "dashed",
        "arrow_head": "open",
        "path_mode": "pipe",
        "label_text_color": "#F0F4FB",
        "label_background_color": "#223344",
    }
    scene.set_edge_visual_style(flow_edge_id, style)
    edge_payload = {item["edge_id"]: item for item in scene.edges_model}
    assert edge_payload[flow_edge_id]["flow_style"] == style
    clipboard.setText("external clipboard text")
    app.setProperty(
        f"{presenter_module._STYLE_CLIPBOARD_APP_PROPERTY}:"
        f"{presenter_module._FLOW_EDGE_STYLE_CLIPBOARD_KIND}",
        "",
    )
    try:
        assert not presenter.request_edit_flow_edge_style(data_edge_id)
        assert presenter.request_copy_flow_edge_style(flow_edge_id)
        assert clipboard.text() == "external clipboard text"
        assert presenter.request_paste_flow_edge_style(sibling_edge_id)
        assert workspace.edges[sibling_edge_id].visual_style == style
        assert presenter.request_reset_flow_edge_style(sibling_edge_id)
        assert workspace.edges[sibling_edge_id].visual_style == {}

        get_text_calls: list[tuple[object, str, str, str]] = []

        def get_text(parent, title, label, *, text):  # noqa: ANN001, ANN202
            get_text_calls.append((parent, title, label, text))
            return "Primary Path", True

        monkeypatch.setattr(presenter_module.QInputDialog, "getText", get_text)
        assert presenter.request_edit_flow_edge_label(flow_edge_id)
        assert get_text_calls == [(host, "Edit Flow Edge Label", "Label:", "")]
        assert workspace.edges[flow_edge_id].label == "Primary Path"

        monkeypatch.setattr(
            presenter_module.QInputDialog,
            "getText",
            lambda *_args, **_kwargs: ("Ignored", False),
        )
        assert not presenter.request_edit_flow_edge_label(flow_edge_id)
        assert workspace.edges[flow_edge_id].label == "Primary Path"

        app.setProperty(
            f"{presenter_module._STYLE_CLIPBOARD_APP_PROPERTY}:"
            f"{presenter_module._FLOW_EDGE_STYLE_CLIPBOARD_KIND}",
            "",
        )
        clipboard.setText(
            '{"kind":"flow-edge-style","version":1,"style":{"stroke_pattern":"dashed"}}'
        )
        assert not presenter.request_paste_flow_edge_style(sibling_edge_id)
        assert not presenter.request_copy_flow_edge_style(data_edge_id)
        assert not presenter.request_paste_flow_edge_style(data_edge_id)
        assert not presenter.request_edit_flow_edge_label(data_edge_id)
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_persists_dialog_presets_on_cancel(monkeypatch) -> None:
    presenter, host, model, scene, session, project_meta_changed = _style_fixture()
    node_id = scene.add_node_from_type("passive.annotation.sticky_note", 100.0, 80.0)
    seen_parents: list[object] = []

    class _RejectedDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, initial_style=None, parent=None, *, user_presets=None) -> None:  # noqa: ANN001
            del initial_style, user_presets
            seen_parents.append(parent)

        @staticmethod
        def exec() -> int:
            return int(QDialog.DialogCode.Rejected)

        @staticmethod
        def user_presets() -> list[dict[str, object]]:
            return [
                {
                    "preset_id": "node_preset_aa11bb22",
                    "name": "Saved On Cancel",
                    "style": {"fill_color": "#112233"},
                }
            ]

        @staticmethod
        def node_style() -> dict[str, object]:
            raise AssertionError("Rejected dialog must not return a style")

    try:
        monkeypatch.setattr("ea_node_editor.ui.dialogs.PassiveNodeStyleDialog", _RejectedDialog)
        assert presenter.edit_passive_node_style(node_id) is None

        presets = model.project.metadata["ui"]["passive_style_presets"]
        assert presets["node_presets"][0]["name"] == "Saved On Cancel"
        assert seen_parents == [host]
        assert session.persist_count == 1
        assert project_meta_changed.emit_count == 1
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_uses_current_project_presets_after_model_switch(monkeypatch) -> None:
    presenter, host, model, scene, session, project_meta_changed = _style_fixture()

    class _RejectedDialog:
        DialogCode = QDialog.DialogCode
        seen_user_presets: list[list[dict[str, object]]] = []
        seen_parents: list[object] = []
        next_user_presets: list[dict[str, object]] = []

        def __init__(self, initial_style=None, parent=None, *, user_presets=None) -> None:  # noqa: ANN001
            del initial_style
            self.seen_user_presets.append(copy.deepcopy(user_presets or []))
            self.seen_parents.append(parent)

        @staticmethod
        def exec() -> int:
            return int(QDialog.DialogCode.Rejected)

        def user_presets(self) -> list[dict[str, object]]:
            return copy.deepcopy(self.next_user_presets)

        @staticmethod
        def node_style() -> dict[str, object]:
            raise AssertionError("Rejected dialog must not return a style")

    project_a_initial_presets = [
        {
            "preset_id": "node_preset_aa11bb22",
            "name": "A Only",
            "style": {"fill_color": "#112233"},
        }
    ]
    project_a_updated_presets = [
        {
            "preset_id": "node_preset_cc33dd44",
            "name": "A Updated",
            "style": {"fill_color": "#445566"},
        }
    ]
    project_b_presets = [
        {
            "preset_id": "node_preset_ee55ff66",
            "name": "B Only",
            "style": {"fill_color": "#AABBCC"},
        }
    ]
    project_a = ProjectData(
        project_id="proj_a",
        name="Project A",
        metadata={
            "ui": {
                "passive_style_presets": {
                    "node_presets": copy.deepcopy(project_a_initial_presets),
                    "edge_presets": [],
                }
            }
        },
    )
    project_b = ProjectData(
        project_id="proj_b",
        name="Project B",
        metadata={
            "ui": {
                "passive_style_presets": {
                    "node_presets": copy.deepcopy(project_b_presets),
                    "edge_presets": [],
                }
            }
        },
    )

    def add_project_node(project: ProjectData, *, x: float, y: float) -> str:
        model.project = project
        workspace_id = model.active_workspace.workspace_id
        scene.set_workspace(model, host.registry, workspace_id)
        return scene.add_node_from_type("passive.flowchart.process", x, y)

    monkeypatch.setattr("ea_node_editor.ui.dialogs.PassiveNodeStyleDialog", _RejectedDialog)
    try:
        node_a = add_project_node(project_a, x=10.0, y=20.0)
        _RejectedDialog.next_user_presets = copy.deepcopy(project_a_updated_presets)
        assert presenter.edit_passive_node_style(node_a) is None
        assert _RejectedDialog.seen_user_presets[0] == project_a_initial_presets
        assert (
            project_a.metadata["ui"]["passive_style_presets"]["node_presets"]
            == project_a_updated_presets
        )
        assert session.persist_count == 1
        assert project_meta_changed.emit_count == 1

        node_b = add_project_node(project_b, x=40.0, y=50.0)
        _RejectedDialog.next_user_presets = copy.deepcopy(project_b_presets)
        assert presenter.edit_passive_node_style(node_b) is None
        assert _RejectedDialog.seen_user_presets[1] == project_b_presets
        assert (
            project_a.metadata["ui"]["passive_style_presets"]["node_presets"]
            == project_a_updated_presets
        )
        assert (
            project_b.metadata["ui"]["passive_style_presets"]["node_presets"]
            == project_b_presets
        )
        assert _RejectedDialog.seen_parents == [host, host]
        assert session.persist_count == 1
        assert project_meta_changed.emit_count == 1
    finally:
        presenter.shutdown()


def test_graph_canvas_host_presenter_uses_current_registry_for_style_eligibility() -> None:
    presenter, host, _model, scene, _session, _signal = _style_fixture()
    node_id = scene.add_node_from_type("passive.annotation.sticky_note", 100.0, 80.0)
    registry = host.registry

    class _ActiveOverrideRegistry:
        @staticmethod
        def get_spec(type_id: str):  # noqa: ANN205
            return replace(registry.get_spec(type_id), runtime_behavior="active")

    try:
        host.registry = _ActiveOverrideRegistry()
        assert not presenter.request_reset_passive_node_style(node_id)
        host.registry = registry
        assert presenter.request_reset_passive_node_style(node_id)
    finally:
        presenter.shutdown()
