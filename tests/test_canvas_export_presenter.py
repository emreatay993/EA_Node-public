# Purpose: Direct owner tests for canvas PNG/PPTX and project-review capture.
# Map: subsystems/graph_canvas
# Tests: tests/test_canvas_export_presenter.py
from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage

from ea_node_editor.ui.canvas_view_export import (
    CanvasExportCropRect,
    CanvasViewExportError,
    canvas_export_crop_rect_for_scene_bounds,
    canvas_export_crop_rect_with_overlay_snapshots,
    canvas_view_png_output_paths,
    collision_safe_path,
    final_export_pixel_size,
    safe_filename_component,
)
from ea_node_editor.ui.canvas_view_export_compositor import (
    CanvasViewExportCompositeError,
    composite_canvas_view_png,
)
from ea_node_editor.ui.dialogs.canvas_view_export_dialog import CanvasViewExportDialog
from ea_node_editor.ui.pptx_export import (
    CanvasViewPptxSlide,
    create_canvas_views_pptx,
    default_canvas_views_deck_path,
)
import ea_node_editor.ui.shell.presenters.canvas_export_presenter as canvas_export_presenter_module
from ea_node_editor.ui.shell.presenters.canvas_export_presenter import (
    CanvasExportPresenter,
    ProjectReviewCanvasCaptureSpec,
    ProjectReviewCanvasCaptureViewport,
)
from ea_node_editor.ui.shell.presenters.contracts import (
    _CanvasExportPresenterHostProtocol,
)
from ea_node_editor.ui_qml.native_overlay_owners import (
    PLOT_HOST_OVERLAY_OWNER,
    VIEWER_SESSION_OVERLAY_OWNER,
)
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge


def _solid_png(path, width: int, height: int, color: str) -> None:  # noqa: ANN001
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


class _FakeSignal:
    def connect(self, _slot) -> None:  # noqa: ANN001
        return None


class _FakeConsole:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []

    def append_log(self, level: str, message: str) -> None:
        self.logs.append((level, message))


class _FakeWorkspaceManager:
    def active_workspace_id(self) -> str:
        return "ws"


class _FakeWorkspace:
    def __init__(self, active_view_id: str = "view-a") -> None:
        self.name = "Workspace"
        self.active_view_id = active_view_id
        self.views = {
            "view-a": SimpleNamespace(
                view_id="view-a", name="View A", zoom=1.0, pan_x=0.0, pan_y=0.0
            ),
            "view-b": SimpleNamespace(
                view_id="view-b", name="View B", zoom=2.0, pan_x=80.0, pan_y=-30.0
            ),
        }

    def ensure_default_view(self) -> None:
        return None


class _FakeWorkspacePresenter:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.workspace = workspace
        self.switches: list[str] = []

    def request_switch_view(self, view_id: str) -> None:
        self.switches.append(view_id)
        self.workspace.active_view_id = view_id


class _FakeHost:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.graphics_preferences_changed = _FakeSignal()
        self.snap_to_grid_changed = _FakeSignal()
        self.workspace_manager = _FakeWorkspaceManager()
        self.model = SimpleNamespace(
            project=SimpleNamespace(workspaces={"ws": workspace})
        )
        self.console_panel = _FakeConsole()
        self.project_path = ""
        self.quick_widget = None
        self.shell_host_presenter = None
        self.viewer_host_service = None
        self.plot_host_service = None
        self.embedded_viewer_overlay_manager = None
        self.search_scope_state = SimpleNamespace()
        self.workspace_ui_state = SimpleNamespace()
        self.search_scope_controller = SimpleNamespace()
        self.app_preferences_controller = SimpleNamespace()
        self.scene = SimpleNamespace()
        self.view = None
        self.workspace_edit_controller = SimpleNamespace()
        self.workspace_drop_connect_controller = SimpleNamespace()
        self.hints: list[tuple[str, int]] = []

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
        self.hints.append((message, timeout_ms))

    def clear_graph_hint(self) -> None:
        return None


def _presenter_for_export(
    workspace: _FakeWorkspace,
) -> tuple[CanvasExportPresenter, _FakeHost, _FakeWorkspacePresenter]:
    host = _FakeHost(workspace)
    workspace_presenter = _FakeWorkspacePresenter(workspace)
    presenter = CanvasExportPresenter(
        host,
        workspace_presenter=workspace_presenter,
    )
    return presenter, host, workspace_presenter


def _viewport(
    *,
    width: int,
    height: int,
    zoom: float = 1.0,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> ViewportBridge:
    view = ViewportBridge()
    view.set_viewport_size(width, height)
    view.set_view_state(zoom, center_x, center_y)
    return view


def _patch_presenter_export_boundaries(
    monkeypatch,  # noqa: ANN001
    presenter: CanvasExportPresenter,
    workspace: _FakeWorkspace,
    tmp_path: Path,
    *,
    failing_views: set[str] | None = None,
) -> tuple[
    list[tuple[str, tuple[int, int], float]],
    list[tuple[str, float, float]],
    list[object | None],
    list[tuple[int, Path, object, tuple[object, ...]]],
]:
    sizes_by_view = {
        "view-a": (100.0, 50.0),
        "view-b": (160.0, 90.0),
    }
    dpr_by_view = {
        "view-a": 1.0,
        "view-b": 1.5,
    }
    capture_calls: list[tuple[str, tuple[int, int], float]] = []
    composite_calls: list[tuple[str, float, float]] = []
    crop_calls: list[object | None] = []
    complete_calls: list[tuple[int, Path, object, tuple[object, ...]]] = []

    monkeypatch.setattr(presenter, "_graph_canvas_item", lambda: SimpleNamespace())
    monkeypatch.setattr(presenter, "_settle_canvas_export_frame", lambda: None)
    monkeypatch.setattr(presenter, "_sync_canvas_export_overlays", lambda: None)
    monkeypatch.setattr(presenter, "_canvas_export_overlay_snapshots", lambda: ())
    monkeypatch.setattr(
        presenter,
        "_canvas_logical_size",
        lambda _item: sizes_by_view[workspace.active_view_id],
    )
    monkeypatch.setattr(
        presenter,
        "_canvas_device_pixel_ratio",
        lambda: dpr_by_view[workspace.active_view_id],
    )
    monkeypatch.setattr(
        presenter,
        "_show_canvas_export_complete",
        lambda png_count, output_dir, deck_path, failures=(): complete_calls.append(
            (png_count, Path(output_dir), deck_path, tuple(failures))
        ),
    )

    def fake_capture(
        *,
        graph_canvas_item,  # noqa: ANN001, ARG001
        output_path: Path,
        scale: int,
        device_pixel_ratio: float,
        expected_pixel_size: tuple[int, int],
    ):
        view_id = workspace.active_view_id
        logical_size = sizes_by_view[view_id]
        assert device_pixel_ratio == dpr_by_view[view_id]
        assert expected_pixel_size == final_export_pixel_size(
            canvas_logical_width=logical_size[0],
            canvas_logical_height=logical_size[1],
            device_pixel_ratio=device_pixel_ratio,
            scale=scale,
        )
        _solid_png(
            output_path, expected_pixel_size[0], expected_pixel_size[1], "#ffffff"
        )
        capture_calls.append((view_id, expected_pixel_size, device_pixel_ratio))
        return canvas_export_presenter_module._CanvasBaseCaptureResult(
            request_id="test",
            path=output_path,
            canvas_logical_size=logical_size,
            device_pixel_ratio=device_pixel_ratio,
            output_pixel_size=expected_pixel_size,
        )

    def fake_composite(
        *,
        base_png_path,  # noqa: ANN001, ARG001
        output_png_path,
        canvas_logical_width: float,
        canvas_logical_height: float,
        overlay_snapshots,  # noqa: ANN001, ARG001
        capture_overlay_image,  # noqa: ANN001, ARG001
        crop_rect_px=None,  # noqa: ANN001
    ):
        view_id = workspace.active_view_id
        if view_id in (failing_views or set()):
            raise CanvasViewExportCompositeError(f"{view_id} missing overlay")
        composite_calls.append((view_id, canvas_logical_width, canvas_logical_height))
        crop_calls.append(crop_rect_px)
        width = int(getattr(crop_rect_px, "width", 10) or 10)
        height = int(getattr(crop_rect_px, "height", 10) or 10)
        _solid_png(output_png_path, width, height, "#ffffff")
        return output_png_path

    monkeypatch.setattr(presenter, "_capture_canvas_base_png", fake_capture)
    monkeypatch.setattr(
        canvas_export_presenter_module, "composite_canvas_view_png", fake_composite
    )
    return capture_calls, composite_calls, crop_calls, complete_calls


def test_canvas_export_host_protocol_only_declares_capture_export_dependencies() -> (
    None
):
    assert set(_CanvasExportPresenterHostProtocol.__annotations__) == {
        "scene",
        "view",
        "model",
        "workspace_manager",
        "quick_widget",
        "shell_host_presenter",
        "viewer_host_service",
        "plot_host_service",
        "embedded_viewer_overlay_manager",
        "project_path",
        "console_panel",
    }
    assert {
        name
        for name, value in _CanvasExportPresenterHostProtocol.__dict__.items()
        if not name.startswith("_") and callable(value)
    } == {"show_graph_hint", "update_notification_counters"}


def test_final_export_pixel_size_uses_canvas_logical_size_dpr_and_scale() -> None:
    assert final_export_pixel_size(
        canvas_logical_width=640,
        canvas_logical_height=360,
        device_pixel_ratio=1.5,
        scale=2,
    ) == (1920, 1080)


def test_final_export_pixel_size_rejects_invalid_scale_and_limits() -> None:
    with pytest.raises(CanvasViewExportError):
        final_export_pixel_size(
            canvas_logical_width=640,
            canvas_logical_height=360,
            device_pixel_ratio=1,
            scale=5,
        )
    with pytest.raises(CanvasViewExportError):
        final_export_pixel_size(
            canvas_logical_width=20000,
            canvas_logical_height=100,
            device_pixel_ratio=1,
            scale=1,
        )
    with pytest.raises(CanvasViewExportError):
        final_export_pixel_size(
            canvas_logical_width=9000,
            canvas_logical_height=9000,
            device_pixel_ratio=1,
            scale=1,
        )


def test_safe_filename_and_collision_paths(tmp_path) -> None:  # noqa: ANN001
    assert safe_filename_component('AUX <> "View"') == "AUX - -View"
    first = collision_safe_path(tmp_path, "Workspace-Main", ".png")
    first.write_text("existing", encoding="utf-8")
    second = collision_safe_path(tmp_path, "Workspace-Main", ".png")
    assert second.name == "Workspace-Main (2).png"


def test_canvas_view_png_output_paths_reserve_same_view_names(tmp_path) -> None:  # noqa: ANN001
    paths = canvas_view_png_output_paths(
        output_dir=tmp_path,
        workspace_name="Workspace",
        view_names_by_id={"a": "Main", "b": "Main"},
    )
    assert paths["a"].name == "Workspace-Main.png"
    assert paths["b"].name == "Workspace-Main (2).png"


def test_canvas_export_crop_rect_maps_scene_bounds_with_padding_and_scale() -> None:
    crop = canvas_export_crop_rect_for_scene_bounds(
        scene_bounds=QRectF(100.0, 50.0, 200.0, 100.0),
        center_x=200.0,
        center_y=100.0,
        zoom=1.0,
        canvas_logical_width=400.0,
        canvas_logical_height=300.0,
        output_pixel_width=800,
        output_pixel_height=600,
        padding_px=10.0,
    )

    assert crop == CanvasExportCropRect(x=180, y=180, width=440, height=240)


def test_canvas_export_crop_rect_clamps_and_falls_back_for_invalid_bounds() -> None:
    clamped = canvas_export_crop_rect_for_scene_bounds(
        scene_bounds=QRectF(-100.0, -100.0, 10.0, 10.0),
        center_x=0.0,
        center_y=0.0,
        zoom=1.0,
        canvas_logical_width=200.0,
        canvas_logical_height=200.0,
        output_pixel_width=200,
        output_pixel_height=200,
        padding_px=0.0,
    )
    assert clamped == CanvasExportCropRect(x=0, y=0, width=10, height=10)
    assert (
        canvas_export_crop_rect_for_scene_bounds(
            scene_bounds=QRectF(-500.0, -500.0, 10.0, 10.0),
            center_x=0.0,
            center_y=0.0,
            zoom=1.0,
            canvas_logical_width=200.0,
            canvas_logical_height=200.0,
            output_pixel_width=200,
            output_pixel_height=200,
            padding_px=0.0,
        )
        is None
    )
    assert (
        canvas_export_crop_rect_for_scene_bounds(
            scene_bounds=QRectF(-100.0, -100.0, 200.0, 200.0),
            center_x=0.0,
            center_y=0.0,
            zoom=1.0,
            canvas_logical_width=200.0,
            canvas_logical_height=200.0,
            output_pixel_width=200,
            output_pixel_height=200,
            padding_px=0.0,
        )
        is None
    )
    assert (
        canvas_export_crop_rect_for_scene_bounds(
            scene_bounds=QRectF(0.0, 0.0, 0.0, 20.0),
            center_x=0.0,
            center_y=0.0,
            zoom=1.0,
            canvas_logical_width=200.0,
            canvas_logical_height=200.0,
            output_pixel_width=200,
            output_pixel_height=200,
            padding_px=0.0,
        )
        is None
    )


def test_canvas_export_crop_rect_expands_for_overlay_snapshots() -> None:
    crop = canvas_export_crop_rect_with_overlay_snapshots(
        base_crop_rect=CanvasExportCropRect(20, 20, 30, 30),
        overlay_snapshots=(
            SimpleNamespace(canvas_rect=QRectF(5.0, 10.0, 10.0, 20.0)),
            SimpleNamespace(rect=QRectF(70.0, 70.0, 0.0, 10.0)),
        ),
        canvas_logical_width=100.0,
        canvas_logical_height=100.0,
        output_pixel_width=100,
        output_pixel_height=100,
    )

    assert crop == CanvasExportCropRect(5, 10, 45, 40)


def test_compositor_draws_overlay_at_scaled_canvas_rect(tmp_path) -> None:  # noqa: ANN001
    base_path = tmp_path / "base.png"
    overlay_path = tmp_path / "overlay.png"
    output_path = tmp_path / "out.png"
    _solid_png(base_path, 100, 100, "#ffffff")
    _solid_png(overlay_path, 10, 10, "#ff0000")
    overlay_image = QImage(str(overlay_path))
    snapshot = SimpleNamespace(
        owner=VIEWER_SESSION_OVERLAY_OWNER,
        workspace_id="ws",
        node_id="node",
        rect=QRectF(10.0, 20.0, 20.0, 20.0),
    )

    composite_canvas_view_png(
        base_png_path=base_path,
        output_png_path=output_path,
        canvas_logical_width=100,
        canvas_logical_height=100,
        overlay_snapshots=[snapshot],
        capture_overlay_image=lambda _snapshot: overlay_image,
    )

    result = QImage(str(output_path))
    assert QColor(result.pixel(15, 25)).name() == "#ff0000"
    assert QColor(result.pixel(5, 5)).name() == "#ffffff"


def test_compositor_crops_after_overlay_composite(tmp_path) -> None:  # noqa: ANN001
    base_path = tmp_path / "base.png"
    overlay_path = tmp_path / "overlay.png"
    output_path = tmp_path / "out.png"
    _solid_png(base_path, 100, 100, "#ffffff")
    _solid_png(overlay_path, 20, 20, "#ff0000")
    overlay_image = QImage(str(overlay_path))
    snapshot = SimpleNamespace(
        owner=VIEWER_SESSION_OVERLAY_OWNER,
        workspace_id="ws",
        node_id="node",
        rect=QRectF(10.0, 20.0, 20.0, 20.0),
    )

    composite_canvas_view_png(
        base_png_path=base_path,
        output_png_path=output_path,
        canvas_logical_width=100,
        canvas_logical_height=100,
        overlay_snapshots=[snapshot],
        capture_overlay_image=lambda _snapshot: overlay_image,
        crop_rect_px=CanvasExportCropRect(5, 15, 40, 40),
    )

    result = QImage(str(output_path))
    assert (result.width(), result.height()) == (40, 40)
    assert QColor(result.pixel(10, 10)).name() == "#ff0000"
    assert QColor(result.pixel(0, 0)).name() == "#ffffff"


def test_compositor_fails_when_visible_overlay_capture_is_missing(tmp_path) -> None:  # noqa: ANN001
    base_path = tmp_path / "base.png"
    _solid_png(base_path, 100, 100, "#ffffff")
    snapshot = SimpleNamespace(
        owner=PLOT_HOST_OVERLAY_OWNER,
        workspace_id="ws",
        node_id="plot",
        rect=QRectF(10.0, 20.0, 20.0, 20.0),
    )

    with pytest.raises(
        CanvasViewExportCompositeError, match=f"{PLOT_HOST_OVERLAY_OWNER} overlay"
    ):
        composite_canvas_view_png(
            base_png_path=base_path,
            output_png_path=tmp_path / "out.png",
            canvas_logical_width=100,
            canvas_logical_height=100,
            overlay_snapshots=[snapshot],
            capture_overlay_image=lambda _snapshot: QImage(),
        )


def test_pptx_export_builds_one_fitted_image_per_slide(tmp_path) -> None:  # noqa: ANN001
    pptx = pytest.importorskip("pptx")
    image_a = tmp_path / "a.png"
    image_b = tmp_path / "b.png"
    _solid_png(image_a, 160, 90, "#ff0000")
    _solid_png(image_b, 80, 80, "#00ff00")
    deck_path = default_canvas_views_deck_path(tmp_path, "Workspace")

    create_canvas_views_pptx(
        slides=[
            CanvasViewPptxSlide("A", image_a),
            CanvasViewPptxSlide("B", image_b),
        ],
        output_path=deck_path,
        slide_size="16:9 landscape",
    )

    presentation = pptx.Presentation(str(deck_path))
    assert len(presentation.slides) == 2
    assert presentation.slide_width > presentation.slide_height
    picture_names = []
    for slide in presentation.slides:
        pictures = [shape for shape in slide.shapes if shape.shape_type == 13]
        assert len(pictures) == 1
        assert pictures[0].width <= presentation.slide_width
        assert pictures[0].height <= presentation.slide_height
        picture_names.append(pictures[0].name)
    assert picture_names == ["Canvas View - A", "Canvas View - B"]


def test_qml_base_export_contract_includes_request_metadata_and_live_size() -> None:
    source = Path(
        "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml"
    ).read_text(encoding="utf-8")
    world_layer_source = Path(
        "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasWorldLayer.qml"
    ).read_text(encoding="utf-8")

    assert "request_id" in source
    assert "device_pixel_ratio" in source
    assert "base_logical_width" in source
    assert "output_pixel_width" in source
    assert "forceExactVisibleSceneModels" in source
    assert "flushViewStateRedraw" in source
    assert "_prepareWebPageHostsForCanvasExport" in source
    assert "canvasExportWebSettleTimer" in source
    assert "web_settle_ms" in source
    assert "function allHosts()" in world_layer_source


def test_canvas_view_export_dialog_defaults_to_content_crop_and_allows_opt_out(
    tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    dialog = CanvasViewExportDialog(
        view_items=[{"view_id": "view-a", "label": "View A"}],
        output_folder=tmp_path,
        canvas_logical_size=(100.0, 50.0),
        device_pixel_ratio=1.0,
    )
    qapp.processEvents()
    try:
        assert dialog.values().crop_to_content is True
        assert "before crop" in dialog.pixel_size_label.text()
        dialog.crop_check.setChecked(False)
        values = dialog.values()
    finally:
        dialog.deleteLater()

    assert values.crop_to_content is False


def test_export_canvas_views_recomputes_live_size_per_view_and_restores(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    presenter, host, workspace_presenter = _presenter_for_export(workspace)
    capture_calls, composite_calls, _crop_calls, complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
        )
    )

    presenter._export_canvas_views_to_paths(
        view_ids=["view-a", "view-b"],
        output_dir=tmp_path,
        scale=2,
        create_pptx=False,
        slide_size="16:9 landscape",
    )

    assert workspace.active_view_id == "view-a"
    assert workspace_presenter.switches == ["view-b", "view-a"]
    assert capture_calls == [
        ("view-a", (200, 100), 1.0),
        ("view-b", (480, 270), 1.5),
    ]
    assert composite_calls == [
        ("view-a", 100.0, 50.0),
        ("view-b", 160.0, 90.0),
    ]
    assert complete_calls == [(2, tmp_path, None, ())]
    assert any("DPR 1.5" in message for _level, message in host.console_panel.logs)


def test_capture_canvas_view_pngs_crops_to_workspace_bounds_by_default(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    presenter, host, _workspace_presenter = _presenter_for_export(workspace)
    _capture_calls, _composite_calls, crop_calls, _complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
        )
    )
    host.view = _viewport(
        width=100, height=50, zoom=1.0, center_x=-200.0, center_y=-120.0
    )
    host.scene.workspace_scene_bounds = lambda: QRectF(25.0, 15.0, 20.0, 5.0)

    result = presenter.capture_canvas_view_pngs(
        view_ids=["view-a"],
        output_dir=tmp_path,
        scale=1,
        crop_padding_px=0.0,
    )

    assert crop_calls == [CanvasExportCropRect(x=20, y=17, width=60, height=16)]
    assert result.exports[0].output_pixel_size == (60, 16)
    assert host.view.zoom_value == 1.0
    assert host.view.center_x == -200.0
    assert host.view.center_y == -120.0


def test_capture_canvas_view_pngs_respects_crop_opt_out(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    presenter, host, _workspace_presenter = _presenter_for_export(workspace)
    _capture_calls, _composite_calls, crop_calls, _complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
        )
    )
    host.view = _viewport(
        width=100, height=50, zoom=1.0, center_x=-200.0, center_y=-120.0
    )
    host.scene.workspace_scene_bounds = lambda: QRectF(25.0, 15.0, 20.0, 10.0)

    result = presenter.capture_canvas_view_pngs(
        view_ids=["view-a"],
        output_dir=tmp_path,
        scale=1,
        crop_to_content=False,
    )

    assert crop_calls == [None]
    assert result.exports[0].output_pixel_size == (100, 50)
    assert host.view.center_x == -200.0
    assert host.view.center_y == -120.0


def test_project_review_canvas_capture_applies_supplied_viewport_and_restores(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    original_views = copy.deepcopy(workspace.views)
    presenter, host, workspace_presenter = _presenter_for_export(workspace)
    host.view = _viewport(
        width=100, height=50, zoom=0.75, center_x=-12.0, center_y=18.0
    )
    captured_view_states: list[tuple[float, float, float]] = []
    crop_calls: list[object | None] = []

    monkeypatch.setattr(presenter, "_graph_canvas_item", lambda: SimpleNamespace())
    monkeypatch.setattr(presenter, "_settle_canvas_export_frame", lambda: None)
    monkeypatch.setattr(presenter, "_sync_canvas_export_overlays", lambda: None)
    monkeypatch.setattr(presenter, "_canvas_export_overlay_snapshots", lambda: ())
    monkeypatch.setattr(presenter, "_canvas_logical_size", lambda _item: (100.0, 50.0))
    monkeypatch.setattr(presenter, "_canvas_device_pixel_ratio", lambda: 1.0)
    monkeypatch.setattr(
        presenter, "_canvas_export_scene_bounds", lambda: QRectF(0.0, 0.0, 20.0, 10.0)
    )

    def fake_capture(
        *,
        graph_canvas_item,  # noqa: ANN001, ARG001
        output_path: Path,
        scale: int,
        device_pixel_ratio: float,
        expected_pixel_size: tuple[int, int],
    ):
        captured_view_states.append(
            (host.view.zoom_value, host.view.center_x, host.view.center_y)
        )
        assert scale == 1
        assert device_pixel_ratio == 1.0
        assert expected_pixel_size == (100, 50)
        _solid_png(output_path, 100, 50, "#ffffff")
        return canvas_export_presenter_module._CanvasBaseCaptureResult(
            request_id="test",
            path=output_path,
            canvas_logical_size=(100.0, 50.0),
            device_pixel_ratio=1.0,
            output_pixel_size=(100, 50),
        )

    def fake_composite(
        *,
        base_png_path,  # noqa: ANN001, ARG001
        output_png_path,
        canvas_logical_width: float,  # noqa: ARG001
        canvas_logical_height: float,  # noqa: ARG001
        overlay_snapshots,  # noqa: ANN001, ARG001
        capture_overlay_image,  # noqa: ANN001, ARG001
        crop_rect_px=None,  # noqa: ANN001
    ):
        crop_calls.append(crop_rect_px)
        _solid_png(output_png_path, 100, 50, "#ffffff")
        return output_png_path

    monkeypatch.setattr(presenter, "_capture_canvas_base_png", fake_capture)
    monkeypatch.setattr(
        canvas_export_presenter_module, "composite_canvas_view_png", fake_composite
    )

    result = presenter.capture_project_review_canvas_pngs(
        capture_specs=(
            ProjectReviewCanvasCaptureSpec(
                slide_id="canvas:view:ws:view-b",
                display_name="View B",
                capture_mode="view",
                view_id="view-b",
                viewport=ProjectReviewCanvasCaptureViewport(
                    zoom=2.0, center_x=80.0, center_y=-30.0
                ),
                crop_to_content=True,
            ),
        ),
        output_dir=tmp_path,
        scale=1,
    )

    assert [export.slide_id for export in result.exports] == ["canvas:view:ws:view-b"]
    assert result.exports[0].path.exists()
    assert captured_view_states == [(2.0, 80.0, -30.0)]
    assert crop_calls == [None]
    assert workspace_presenter.switches == []
    assert workspace.active_view_id == "view-a"
    assert workspace.views == original_views
    assert host.view.zoom_value == 0.75
    assert host.view.center_x == -12.0
    assert host.view.center_y == 18.0


def test_capture_canvas_view_pngs_falls_back_when_content_cannot_be_framed(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    presenter, host, _workspace_presenter = _presenter_for_export(workspace)
    _capture_calls, _composite_calls, crop_calls, _complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
        )
    )
    host.view = SimpleNamespace(center_x=-200.0, center_y=-120.0, zoom_value=1.0)
    host.scene.workspace_scene_bounds = lambda: QRectF(25.0, 15.0, 20.0, 10.0)

    result = presenter.capture_canvas_view_pngs(
        view_ids=["view-a"],
        output_dir=tmp_path,
        scale=1,
        crop_padding_px=0.0,
    )

    assert crop_calls == [None]
    assert result.exports[0].output_pixel_size == (100, 50)


def test_export_canvas_views_reports_partial_failures_and_keeps_successes(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-a")
    presenter, _host, _workspace_presenter = _presenter_for_export(workspace)
    _capture_calls, composite_calls, _crop_calls, complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
            failing_views={"view-a"},
        )
    )

    presenter._export_canvas_views_to_paths(
        view_ids=["view-a", "view-b"],
        output_dir=tmp_path,
        scale=1,
        create_pptx=False,
        slide_size="16:9 landscape",
    )

    assert workspace.active_view_id == "view-a"
    assert composite_calls == [("view-b", 160.0, 90.0)]
    png_count, output_dir, deck_path, failures = complete_calls[-1]
    assert png_count == 1
    assert output_dir == tmp_path
    assert deck_path is None
    assert len(failures) == 1
    assert failures[0].view_name == "View A"
    assert "missing overlay" in failures[0].message


def test_export_canvas_views_restores_original_view_when_all_views_fail(
    monkeypatch, tmp_path, qapp
) -> None:  # noqa: ANN001, ARG001
    workspace = _FakeWorkspace(active_view_id="view-b")
    presenter, _host, _workspace_presenter = _presenter_for_export(workspace)
    _capture_calls, _composite_calls, _crop_calls, _complete_calls = (
        _patch_presenter_export_boundaries(
            monkeypatch,
            presenter,
            workspace,
            tmp_path,
            failing_views={"view-a"},
        )
    )

    with pytest.raises(CanvasViewExportError, match="failed for all selected views"):
        presenter._export_canvas_views_to_paths(
            view_ids=["view-a"],
            output_dir=tmp_path,
            scale=1,
            create_pptx=False,
            slide_size="16:9 landscape",
        )

    assert workspace.active_view_id == "view-b"
