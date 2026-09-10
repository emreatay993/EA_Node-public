from __future__ import annotations

from pathlib import Path

from types import SimpleNamespace

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.content_fullscreen_bridge import ContentFullscreenBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class _ExecutionSignalSource(QObject):
    changed = pyqtSignal()


class _ViewerSessionBridgeStub:
    @staticmethod
    def session_state(_node_id: str) -> dict[str, object]:
        return {}


class _ScriptEditorStub:
    current_node_id = ""

    @staticmethod
    def set_node(_node: object) -> None:
        return


def _bridge_with_plot_node(
    *, render_in_canvas: bool = False
) -> tuple[
    ContentFullscreenBridge,
    str,
    str,
    GraphModel,
    str,
    RuntimeGraphHistory,
]:
    model = GraphModel()
    registry = build_default_registry()
    workspace_id = model.active_workspace.workspace_id
    node = model.add_node(
        workspace_id,
        "plot.scatter",
        "Scatter Plot",
        0.0,
        0.0,
        properties={"render_in_canvas": render_in_canvas},
    )
    other = model.add_node(
        workspace_id,
        "plot.scatter",
        "Other Scatter Plot",
        40.0,
        40.0,
        properties={"plot_options": {"plot_theme": "light"}},
    )
    history = RuntimeGraphHistory()
    scene = GraphSceneBridge()
    scene.bind_runtime_history(history)
    scene.set_workspace(model, registry, workspace_id)
    scene.select_node(other.node_id)
    execution = _ExecutionSignalSource()
    bridge = ContentFullscreenBridge(
        model_provider=lambda: model,
        registry_provider=lambda: registry,
        active_workspace_id_provider=lambda: workspace_id,
        project_context_provider=lambda: (None, dict(model.project.metadata)),
        scene_bridge=scene,
        viewer_session_bridge=_ViewerSessionBridgeStub(),  # type: ignore[arg-type]
        run_state=SimpleNamespace(),  # type: ignore[arg-type]
        execution_state_changed_signal=execution.changed,
        script_editor=_ScriptEditorStub(),  # type: ignore[arg-type]
        save_file_dialog=lambda *_args: "",
        trim_video_clip_replace=lambda *_args: {},
        trim_video_clip_copy=lambda *_args: {},
        create_web_surface_artifact_service=lambda *_args: SimpleNamespace(),
    )
    return bridge, node.node_id, other.node_id, model, workspace_id, history


def test_plot_fullscreen_bridge_opens_plot_payload_even_when_embedded_is_suppressed() -> None:
    bridge, node_id, _other_id, _model, _workspace_id, _history = (
        _bridge_with_plot_node(render_in_canvas=False)
    )

    assert bridge.request_open_node(node_id) is True

    assert bridge.open is True
    assert bridge.content_kind == "plot"
    assert bridge.node_id == node_id
    plot_payload = bridge.plot_payload
    assert plot_payload["content_kind"] == "plot"
    assert plot_payload["surface_family"] == "plot"
    assert plot_payload["surface_variant"] == "scatter"
    assert plot_payload["surface_spec"]["fullscreen"]["content_kind"] == "plot"
    assert plot_payload["surface_spec"]["native_overlay"]["required"] is True
    assert plot_payload["plot_surface"] == {
        "plot_type": "scatter",
        "live_backend_id": "pyqtgraph",
        "render_in_canvas": False,
        "lightweight_canvas": False,
        "embedded_rendering_suppressed": True,
        "embedded_rendering_suppressed_by": ["render_in_canvas"],
    }


def test_plot_fullscreen_payload_refreshes_from_scene_node_payload() -> None:
    bridge, node_id, _other_id, _model, _workspace_id, _history = (
        _bridge_with_plot_node(render_in_canvas=True)
    )

    assert bridge.request_open_node(node_id) is True

    assert bridge.content_kind == "plot"
    assert bridge.plot_payload["plot_surface"]["embedded_rendering_suppressed"] is False
    assert bridge.can_open_node(node_id) is True
    bridge.request_close()
    assert bridge.open is False
    assert bridge.plot_payload == {}


def test_plot_fullscreen_bridge_updates_only_fullscreen_node_with_one_history_entry_per_change() -> None:
    bridge, node_id, other_id, model, workspace_id, history = (
        _bridge_with_plot_node(render_in_canvas=True)
    )
    workspace = model.project.workspaces[workspace_id]
    before_history = history.undo_depth(workspace_id)

    assert bridge.request_open_node(node_id) is True
    assert bridge.set_active_plot_option("crosshair", True) is True
    assert bridge.set_active_plot_option("plot_theme", "dark") is True

    assert workspace.nodes[node_id].properties["plot_options"]["crosshair"] is True
    assert workspace.nodes[node_id].properties["plot_options"]["plot_theme"] == "dark"
    assert workspace.nodes[other_id].properties["plot_options"] == {
        "plot_theme": "light"
    }
    assert history.undo_depth(workspace_id) == before_history + 2
    assert bridge.plot_payload["properties"]["plot_options"]["crosshair"] is True
    assert bridge.plot_payload["properties"]["plot_options"]["plot_theme"] == "dark"


def test_content_fullscreen_overlay_uses_opaque_scrim() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ea_node_editor"
        / "ui_qml"
        / "ContentFullscreenOverlay.qml"
    ).read_text(encoding="utf-8")

    assert "color: root.themePalette.app_bg" in source
    assert "Qt.alpha(root.themePalette.app_bg, 0.97)" not in source


def test_content_fullscreen_overlay_exposes_plot_investigation_controls() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ea_node_editor"
        / "ui_qml"
        / "ContentFullscreenOverlay.qml"
    ).read_text(encoding="utf-8")

    assert 'objectName: "contentFullscreenPlotQuickControls"' in source
    assert 'objectName: "contentFullscreenPlotHoverReadoutButton"' in source
    assert 'objectName: "contentFullscreenPlotVerticalGuideButton"' in source
    assert 'objectName: "contentFullscreenPlotCrosshairButton"' in source
    assert 'objectName: "contentFullscreenPlotThemeCombo"' in source
    assert 'root._setPlotOption("hover_readout"' in source
    assert 'root._setPlotOption("vertical_guide"' in source
    assert 'root._setPlotOption("crosshair"' in source
    assert 'root._setPlotOption("plot_theme"' in source
