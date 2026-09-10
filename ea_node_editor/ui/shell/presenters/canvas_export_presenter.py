# Purpose: Plain presenter for graph-canvas PNG/PPTX and project-review capture.
# Map: subsystems/ui_shell
# Tests: tests/test_canvas_export_presenter.py
# Landmarks: CanvasExportPresenter, CanvasViewPngExport, ProjectReviewCanvasCaptureSpec
from __future__ import annotations

import copy
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from PyQt6.QtCore import Q_ARG, QEventLoop, QMetaObject, QObject, Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from ea_node_editor.ui.canvas_view_export import (
    DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX,
    CanvasExportCropRect,
    CanvasViewExportError,
    canvas_export_crop_rect_for_scene_bounds,
    canvas_export_crop_rect_with_overlay_snapshots,
    canvas_view_png_output_paths,
    collision_safe_path,
    final_export_pixel_size,
    validate_export_pixel_size,
)
from ea_node_editor.ui.canvas_view_export_compositor import (
    CanvasViewExportCompositeError,
    composite_canvas_view_png,
)
from ea_node_editor.ui.dialogs.canvas_view_export_dialog import CanvasViewExportDialog
from ea_node_editor.ui.pptx_export import (
    CanvasViewPptxExportError,
    CanvasViewPptxSlide,
    create_canvas_views_pptx,
    default_canvas_views_deck_path,
)
from ea_node_editor.ui_qml.native_overlay_owners import (
    PLOT_HOST_OVERLAY_OWNER,
    VIEWER_SESSION_OVERLAY_OWNER,
)

from .contracts import _CanvasExportPresenterHostProtocol

if TYPE_CHECKING:
    from .workspace_presenter import ShellWorkspacePresenter


@dataclass(frozen=True, slots=True)
class _CanvasBaseCaptureResult:
    request_id: str
    path: Path
    canvas_logical_size: tuple[float, float]
    device_pixel_ratio: float
    output_pixel_size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _CanvasExportViewState:
    zoom: float
    center_x: float
    center_y: float


@dataclass(frozen=True, slots=True)
class ProjectReviewCanvasCaptureViewport:
    zoom: float
    center_x: float
    center_y: float


@dataclass(frozen=True, slots=True)
class ProjectReviewCanvasCaptureSpec:
    slide_id: str
    display_name: str
    capture_mode: str
    view_id: str = ""
    viewport: ProjectReviewCanvasCaptureViewport | None = None
    crop_to_content: bool = True


@dataclass(frozen=True, slots=True)
class _CanvasViewExportFailure:
    view_name: str
    message: str


@dataclass(frozen=True, slots=True)
class _ActiveCanvasPngCapture:
    path: Path
    output_pixel_size: tuple[int, int]
    device_pixel_ratio: float


@dataclass(frozen=True, slots=True)
class CanvasViewPngExport:
    view_id: str
    view_name: str
    path: Path
    output_pixel_size: tuple[int, int]
    device_pixel_ratio: float


@dataclass(frozen=True, slots=True)
class CanvasViewPngExportResult:
    exports: tuple[CanvasViewPngExport, ...]
    failures: tuple[_CanvasViewExportFailure, ...]


@dataclass(frozen=True, slots=True)
class ProjectReviewCanvasPngExport:
    slide_id: str
    view_id: str
    view_name: str
    path: Path
    output_pixel_size: tuple[int, int]
    device_pixel_ratio: float


@dataclass(frozen=True, slots=True)
class ProjectReviewCanvasPngExportResult:
    exports: tuple[ProjectReviewCanvasPngExport, ...]
    failures: tuple[_CanvasViewExportFailure, ...]


_CANVAS_BASE_CAPTURE_TIMEOUT_MS = 15000


def _mapping(value: Any) -> dict[str, Any]:
    normalized = value.toVariant() if hasattr(value, "toVariant") else value
    if isinstance(normalized, Mapping):
        return dict(normalized)
    if hasattr(normalized, "items"):
        try:
            return dict(normalized.items())
        except Exception:  # noqa: BLE001
            return {}
    return {}


class CanvasExportPresenter:
    def __init__(
        self,
        host: _CanvasExportPresenterHostProtocol,
        *,
        workspace_presenter: "ShellWorkspacePresenter",
    ) -> None:
        self._host = host
        self._workspace_presenter = workspace_presenter

    def export_canvas_views(self, view_ids: Sequence[str] | None = None) -> bool:
        try:
            context = self._canvas_export_context(view_ids)
            graph_canvas_item = self._graph_canvas_item()
            canvas_logical_size = self._canvas_logical_size(graph_canvas_item)
            device_pixel_ratio = self._canvas_device_pixel_ratio()
            dialog = CanvasViewExportDialog(
                view_items=context["view_items"],
                initial_view_ids=context["initial_view_ids"],
                output_folder=self._default_canvas_export_folder(),
                canvas_logical_size=canvas_logical_size,
                device_pixel_ratio=device_pixel_ratio,
                browse_folder_callback=self._choose_canvas_export_folder,
                parent=self._dialog_parent(),
            )
            if dialog.exec() != CanvasViewExportDialog.DialogCode.Accepted:
                return False
            values = dialog.values()
            self._export_canvas_views_to_paths(
                view_ids=values.view_ids,
                output_dir=values.output_folder,
                scale=values.scale,
                create_pptx=values.create_pptx,
                slide_size=values.slide_size,
                crop_to_content=values.crop_to_content,
            )
            return True
        except (
            CanvasViewExportError,
            CanvasViewExportCompositeError,
            CanvasViewPptxExportError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._show_canvas_export_error(str(exc))
            return False

    def _canvas_export_context(self, view_ids: Sequence[str] | None) -> dict[str, Any]:
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            raise CanvasViewExportError("No active workspace is available for export.")
        workspace.ensure_default_view()
        view_items = [
            {
                "view_id": view.view_id,
                "label": view.name,
            }
            for view in workspace.views.values()
        ]
        requested_ids = [str(view_id or "").strip() for view_id in view_ids or []]
        initial_view_ids = [
            view_id for view_id in requested_ids if view_id in workspace.views
        ]
        if requested_ids and not initial_view_ids:
            raise CanvasViewExportError("The requested view is no longer available.")
        return {
            "view_items": view_items,
            "initial_view_ids": initial_view_ids,
        }

    def _export_canvas_views_to_paths(
        self,
        *,
        view_ids: Sequence[str],
        output_dir: Path,
        scale: int,
        create_pptx: bool,
        slide_size: str,
        crop_to_content: bool = True,
    ) -> None:
        result = self.capture_canvas_view_pngs(
            view_ids=view_ids,
            output_dir=output_dir,
            scale=scale,
            crop_to_content=crop_to_content,
        )
        exports = list(result.exports)
        failures = list(result.failures)
        output_dir = Path(output_dir).expanduser()
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            raise CanvasViewExportError("No active workspace is available for export.")

        deck_path: Path | None = None
        if create_pptx and exports:
            exported_slides = [
                CanvasViewPptxSlide(title=export.view_name, image_path=export.path)
                for export in exports
            ]
            default_deck_path = default_canvas_views_deck_path(
                output_dir, workspace.name
            )
            deck_path = collision_safe_path(output_dir, default_deck_path.stem, ".pptx")
            create_canvas_views_pptx(
                slides=exported_slides,
                output_path=deck_path,
                slide_size=slide_size,
            )

        self._append_console_log(
            "info",
            f"Exported {len(exports)} canvas view PNG"
            f"{'' if len(exports) == 1 else 's'} to {output_dir}.",
        )
        if deck_path is not None:
            self._append_console_log(
                "info", f"Canvas view PowerPoint deck saved to {deck_path}."
            )
        if failures:
            self._append_console_log(
                "warning",
                self._format_canvas_export_failures(failures, all_failed=False),
            )
        self._host.show_graph_hint(
            "Canvas view export complete."
            if not failures
            else "Canvas view export completed with failures.",
            3000,
        )
        self._show_canvas_export_complete(len(exports), output_dir, deck_path, failures)

    def capture_canvas_view_pngs(
        self,
        *,
        view_ids: Sequence[str],
        output_dir: Path | str,
        scale: int,
        crop_to_content: bool = True,
        crop_padding_px: float = DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX,
    ) -> CanvasViewPngExportResult:
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            raise CanvasViewExportError("No active workspace is available for export.")
        workspace.ensure_default_view()
        selected_view_ids = [
            str(view_id or "").strip()
            for view_id in view_ids
            if str(view_id or "").strip()
        ]
        selected_view_ids = [
            view_id for view_id in selected_view_ids if view_id in workspace.views
        ]
        if not selected_view_ids:
            raise CanvasViewExportError("Select at least one view to export.")

        output_dir = Path(output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        selected_names_by_id = {
            view_id: workspace.views[view_id].name for view_id in selected_view_ids
        }
        output_paths_by_id = canvas_view_png_output_paths(
            output_dir=output_dir,
            workspace_name=workspace.name,
            view_names_by_id=selected_names_by_id,
        )
        original_view_id = str(workspace.active_view_id or "").strip()
        exports: list[CanvasViewPngExport] = []
        failures: list[_CanvasViewExportFailure] = []

        try:
            with tempfile.TemporaryDirectory(prefix="canvas-view-export-") as temp_dir:
                temp_root = Path(temp_dir)
                for index, view_id in enumerate(selected_view_ids, start=1):
                    workspace = self._host.model.project.workspaces.get(workspace_id)
                    if workspace is None or view_id not in workspace.views:
                        failures.append(
                            _CanvasViewExportFailure(
                                view_id, "A selected view is no longer available."
                            )
                        )
                        continue
                    view_name = str(workspace.views[view_id].name or view_id)
                    try:
                        if workspace.active_view_id != view_id:
                            self._workspace_presenter.request_switch_view(view_id)
                        capture = self._capture_active_canvas_png(
                            output_path=output_paths_by_id[view_id],
                            base_path=temp_root / f"canvas-view-{index}.base.png",
                            scale=scale,
                            crop_to_content=crop_to_content,
                            crop_padding_px=crop_padding_px,
                        )
                    except (
                        CanvasViewExportError,
                        CanvasViewExportCompositeError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as exc:
                        message = str(exc or "View export failed.")
                        failures.append(_CanvasViewExportFailure(view_name, message))
                        self._append_console_log(
                            "error",
                            f"Canvas view export failed for {view_name}: {message}",
                        )
                        continue
                    exports.append(
                        CanvasViewPngExport(
                            view_id=view_id,
                            view_name=view_name,
                            path=capture.path,
                            output_pixel_size=capture.output_pixel_size,
                            device_pixel_ratio=capture.device_pixel_ratio,
                        )
                    )
                    self._append_console_log(
                        "info",
                        "Canvas view exported: "
                        f"{view_name} -> {capture.path} "
                        f"({capture.output_pixel_size[0]} x {capture.output_pixel_size[1]} px, "
                        f"DPR {capture.device_pixel_ratio:g}).",
                    )
        finally:
            self._restore_canvas_export_view(workspace_id, original_view_id)

        if failures and not exports:
            raise CanvasViewExportError(
                self._format_canvas_export_failures(failures, all_failed=True)
            )

        return CanvasViewPngExportResult(
            exports=tuple(exports), failures=tuple(failures)
        )

    def capture_project_review_canvas_pngs(
        self,
        *,
        capture_specs: Sequence[ProjectReviewCanvasCaptureSpec],
        output_dir: Path | str,
        scale: int,
        crop_padding_px: float = DEFAULT_CANVAS_EXPORT_CROP_PADDING_PX,
    ) -> ProjectReviewCanvasPngExportResult:
        workspace_id = str(
            self._host.workspace_manager.active_workspace_id() or ""
        ).strip()
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if workspace is None:
            raise CanvasViewExportError("No active workspace is available for export.")
        workspace.ensure_default_view()
        specs = [spec for spec in capture_specs if str(spec.slide_id or "").strip()]
        if not specs:
            raise CanvasViewExportError("Select at least one canvas slide to export.")

        output_dir = Path(output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_paths_by_slide_id = self._project_review_canvas_png_output_paths(
            output_dir=output_dir,
            workspace_name=workspace.name,
            capture_specs=specs,
        )
        original_view_id = str(workspace.active_view_id or "").strip()
        original_views = copy.deepcopy(workspace.views)
        original_live_view_state = self._canvas_export_view_state()
        exports: list[ProjectReviewCanvasPngExport] = []
        failures: list[_CanvasViewExportFailure] = []

        try:
            with tempfile.TemporaryDirectory(
                prefix="project-review-canvas-export-"
            ) as temp_dir:
                temp_root = Path(temp_dir)
                for index, spec in enumerate(specs, start=1):
                    display_name = str(
                        spec.display_name or spec.view_id or spec.slide_id
                    )
                    capture_mode = str(spec.capture_mode or "").strip().lower()
                    live_view_state = self._canvas_export_view_state()
                    try:
                        if capture_mode == "view":
                            viewport = self._project_review_canvas_viewport_state(
                                spec.viewport
                            )
                            if viewport is None:
                                raise CanvasViewExportError(
                                    "Saved workspace view state is not available."
                                )
                            if not self._set_canvas_export_live_view_state(viewport):
                                raise CanvasViewExportError(
                                    "Saved workspace view could not be applied."
                                )
                            effective_crop_to_content = False
                        elif capture_mode == "snapshot":
                            effective_crop_to_content = bool(spec.crop_to_content)
                        else:
                            raise CanvasViewExportError(
                                "Unsupported review deck canvas capture mode."
                            )
                        capture = self._capture_active_canvas_png(
                            output_path=output_paths_by_slide_id[spec.slide_id],
                            base_path=temp_root
                            / f"project-review-canvas-{index}.base.png",
                            scale=scale,
                            crop_to_content=effective_crop_to_content,
                            crop_padding_px=crop_padding_px,
                        )
                    except (
                        CanvasViewExportError,
                        CanvasViewExportCompositeError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as exc:
                        message = str(exc or "Canvas capture failed.")
                        failures.append(_CanvasViewExportFailure(display_name, message))
                        self._append_console_log(
                            "error",
                            f"Project review canvas export failed for {display_name}: {message}",
                        )
                        continue
                    finally:
                        self._restore_canvas_export_live_view_state(live_view_state)
                    exports.append(
                        ProjectReviewCanvasPngExport(
                            slide_id=spec.slide_id,
                            view_id=spec.view_id,
                            view_name=display_name,
                            path=capture.path,
                            output_pixel_size=capture.output_pixel_size,
                            device_pixel_ratio=capture.device_pixel_ratio,
                        )
                    )
        finally:
            workspace = self._host.model.project.workspaces.get(workspace_id)
            if workspace is not None:
                workspace.views = copy.deepcopy(original_views)
                workspace.active_view_id = original_view_id
                workspace.ensure_default_view()
            self._restore_canvas_export_live_view_state(original_live_view_state)

        if failures and not exports:
            raise CanvasViewExportError(
                self._format_canvas_export_failures(failures, all_failed=True)
            )

        return ProjectReviewCanvasPngExportResult(
            exports=tuple(exports), failures=tuple(failures)
        )

    def _capture_active_canvas_png(
        self,
        *,
        output_path: Path,
        base_path: Path,
        scale: int,
        crop_to_content: bool,
        crop_padding_px: float,
    ) -> _ActiveCanvasPngCapture:
        live_view_state = self._canvas_export_view_state() if crop_to_content else None
        try:
            scene_bounds = (
                self._canvas_export_scene_bounds() if crop_to_content else None
            )
            framed_for_crop = (
                self._frame_canvas_export_scene_bounds(
                    scene_bounds, padding_px=crop_padding_px
                )
                if live_view_state is not None and scene_bounds is not None
                else False
            )
            self._settle_canvas_export_frame()
            graph_canvas_item = self._graph_canvas_item()
            canvas_logical_size = self._canvas_logical_size(graph_canvas_item)
            device_pixel_ratio = self._canvas_device_pixel_ratio()
            expected_pixel_size = final_export_pixel_size(
                canvas_logical_width=canvas_logical_size[0],
                canvas_logical_height=canvas_logical_size[1],
                device_pixel_ratio=device_pixel_ratio,
                scale=scale,
            )
            self._sync_canvas_export_overlays()
            overlay_snapshots = self._canvas_export_overlay_snapshots()
            base_capture = self._capture_canvas_base_png(
                graph_canvas_item=graph_canvas_item,
                output_path=base_path,
                scale=scale,
                device_pixel_ratio=device_pixel_ratio,
                expected_pixel_size=expected_pixel_size,
            )
            content_crop_rect_px = (
                self._canvas_export_content_crop_rect(
                    scene_bounds=scene_bounds,
                    canvas_logical_size=base_capture.canvas_logical_size,
                    output_pixel_size=base_capture.output_pixel_size,
                    padding_px=crop_padding_px,
                )
                if crop_to_content and framed_for_crop
                else None
            )
            crop_rect_px = canvas_export_crop_rect_with_overlay_snapshots(
                base_crop_rect=content_crop_rect_px,
                overlay_snapshots=overlay_snapshots,
                canvas_logical_width=base_capture.canvas_logical_size[0],
                canvas_logical_height=base_capture.canvas_logical_size[1],
                output_pixel_width=base_capture.output_pixel_size[0],
                output_pixel_height=base_capture.output_pixel_size[1],
            )
            composite_canvas_view_png(
                base_png_path=base_capture.path,
                output_png_path=output_path,
                canvas_logical_width=base_capture.canvas_logical_size[0],
                canvas_logical_height=base_capture.canvas_logical_size[1],
                overlay_snapshots=overlay_snapshots,
                capture_overlay_image=self._capture_canvas_export_overlay_image,
                crop_rect_px=crop_rect_px,
            )
            final_pixel_size = (
                (crop_rect_px.width, crop_rect_px.height)
                if crop_rect_px is not None
                else base_capture.output_pixel_size
            )
            return _ActiveCanvasPngCapture(
                path=output_path,
                output_pixel_size=final_pixel_size,
                device_pixel_ratio=base_capture.device_pixel_ratio,
            )
        finally:
            self._restore_canvas_export_live_view_state(live_view_state)

    def _project_review_canvas_png_output_paths(
        self,
        *,
        output_dir: Path,
        workspace_name: object,
        capture_specs: Sequence[ProjectReviewCanvasCaptureSpec],
    ) -> dict[str, Path]:
        reserved: set[Path] = set()
        paths: dict[str, Path] = {}
        for spec in capture_specs:
            paths[str(spec.slide_id)] = collision_safe_path(
                output_dir,
                f"{workspace_name}-{spec.display_name}",
                ".png",
                reserved=reserved,
            )
        return paths

    def _project_review_canvas_viewport_state(
        self,
        viewport: ProjectReviewCanvasCaptureViewport | None,
    ) -> _CanvasExportViewState | None:
        if viewport is None:
            return None
        zoom = self._numeric_export_value(getattr(viewport, "zoom", None))
        center_x = self._numeric_export_value(getattr(viewport, "center_x", None))
        center_y = self._numeric_export_value(getattr(viewport, "center_y", None))
        if zoom is None or center_x is None or center_y is None or zoom <= 0.0:
            return None
        return _CanvasExportViewState(zoom=zoom, center_x=center_x, center_y=center_y)

    def _canvas_export_content_crop_rect(
        self,
        *,
        scene_bounds: object,
        canvas_logical_size: tuple[float, float],
        output_pixel_size: tuple[int, int],
        padding_px: float,
    ) -> CanvasExportCropRect | None:
        if scene_bounds is None:
            return None
        view = getattr(self._host, "view", None)
        if view is None:
            return None
        return canvas_export_crop_rect_for_scene_bounds(
            scene_bounds=scene_bounds,
            center_x=getattr(view, "center_x", None),
            center_y=getattr(view, "center_y", None),
            zoom=getattr(view, "zoom_value", getattr(view, "zoom", None)),
            canvas_logical_width=canvas_logical_size[0],
            canvas_logical_height=canvas_logical_size[1],
            output_pixel_width=output_pixel_size[0],
            output_pixel_height=output_pixel_size[1],
            padding_px=padding_px,
        )

    def _canvas_export_scene_bounds(self) -> object | None:
        scene = getattr(self._host, "scene", None)
        bounds = getattr(scene, "workspace_scene_bounds", None)
        if not callable(bounds):
            return None
        try:
            scene_bounds = bounds()
        except (RuntimeError, TypeError, ValueError):
            return None
        if scene_bounds is None:
            return None
        width = self._numeric_export_value(getattr(scene_bounds, "width", None))
        height = self._numeric_export_value(getattr(scene_bounds, "height", None))
        if width is None or height is None or width <= 0.0 or height <= 0.0:
            return None
        return scene_bounds

    def _frame_canvas_export_scene_bounds(
        self, scene_bounds: object, *, padding_px: float
    ) -> bool:
        view = getattr(self._host, "view", None)
        if view is None:
            return False
        frame_scene_rect = getattr(view, "frame_scene_rect", None)
        if callable(frame_scene_rect):
            try:
                frame_scene_rect(scene_bounds, padding_px=float(padding_px))
                return True
            except TypeError:
                try:
                    frame_scene_rect(scene_bounds, float(padding_px))
                    return True
                except (RuntimeError, TypeError, ValueError):
                    return False
            except (RuntimeError, ValueError):
                return False

        fit_zoom_for_scene_rect = getattr(view, "fit_zoom_for_scene_rect", None)
        center = getattr(scene_bounds, "center", None)
        set_view_state = getattr(view, "set_view_state", None)
        if (
            not callable(fit_zoom_for_scene_rect)
            or not callable(center)
            or not callable(set_view_state)
        ):
            return False
        try:
            fitted_zoom = fit_zoom_for_scene_rect(
                scene_bounds, padding_px=float(padding_px)
            )
            scene_center = center()
            center_x = self._numeric_export_value(getattr(scene_center, "x", None))
            center_y = self._numeric_export_value(getattr(scene_center, "y", None))
            if center_x is None or center_y is None:
                return False
            set_view_state(float(fitted_zoom), center_x, center_y)
            return True
        except (RuntimeError, TypeError, ValueError):
            return False

    def _canvas_export_view_state(self) -> _CanvasExportViewState | None:
        view = getattr(self._host, "view", None)
        if view is None:
            return None
        zoom = self._numeric_export_value(
            getattr(view, "zoom_value", getattr(view, "zoom", None))
        )
        center_x = self._numeric_export_value(getattr(view, "center_x", None))
        center_y = self._numeric_export_value(getattr(view, "center_y", None))
        if zoom is None or center_x is None or center_y is None or zoom <= 0.0:
            return None
        return _CanvasExportViewState(zoom=zoom, center_x=center_x, center_y=center_y)

    def _restore_canvas_export_live_view_state(
        self, state: _CanvasExportViewState | None
    ) -> None:
        if state is None:
            return
        self._set_canvas_export_live_view_state(state)

    def _set_canvas_export_live_view_state(
        self, state: _CanvasExportViewState | None
    ) -> bool:
        if state is None:
            return False
        view = getattr(self._host, "view", None)
        if view is None:
            return False
        try:
            set_view_state = getattr(view, "set_view_state", None)
            if callable(set_view_state):
                set_view_state(state.zoom, state.center_x, state.center_y)
            else:
                set_zoom = getattr(view, "set_zoom", None)
                center_on = getattr(view, "centerOn", None)
                if not callable(set_zoom) or not callable(center_on):
                    return False
                if callable(set_zoom):
                    set_zoom(state.zoom)
                center_on(state.center_x, state.center_y)
        except (RuntimeError, TypeError, ValueError):
            return False
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        return True

    @staticmethod
    def _numeric_export_value(value: object) -> float | None:
        raw = value() if callable(value) else value
        try:
            resolved = float(raw)
        except (TypeError, ValueError):
            return None
        return resolved if isfinite(resolved) else None

    def _graph_canvas_item(self) -> QObject:
        quick_widget = getattr(self._host, "quick_widget", None)
        root_object = quick_widget.rootObject() if quick_widget is not None else None
        graph_canvas_item = (
            root_object.findChild(QObject, "graphCanvas")
            if root_object is not None
            else None
        )
        if graph_canvas_item is None:
            raise CanvasViewExportError("Graph canvas is not ready for export.")
        return graph_canvas_item

    def _canvas_logical_size(self, graph_canvas_item: QObject) -> tuple[float, float]:
        width = self._positive_capture_dimension(
            self._numeric_qobject_value(graph_canvas_item, "width")
        )
        height = self._positive_capture_dimension(
            self._numeric_qobject_value(graph_canvas_item, "height")
        )
        if width is None or height is None:
            raise CanvasViewExportError("Graph canvas size is not ready for export.")
        return width, height

    @staticmethod
    def _numeric_qobject_value(obj: QObject, name: str) -> object:
        attr = getattr(obj, name, None)
        if callable(attr):
            return attr()
        value = obj.property(name)
        return value if value is not None else attr

    def _canvas_device_pixel_ratio(self) -> float:
        quick_widget = getattr(self._host, "quick_widget", None)
        candidates = [
            getattr(quick_widget, "devicePixelRatioF", lambda: 0.0)(),
        ]
        quick_window = quick_widget.quickWindow() if quick_widget is not None else None
        if quick_window is not None:
            candidates.append(
                getattr(quick_window, "effectiveDevicePixelRatio", lambda: 0.0)()
            )
        for candidate in candidates:
            try:
                value = float(candidate)
            except (TypeError, ValueError):
                continue
            if isfinite(value) and value > 0.0:
                return value
        return 1.0

    def _default_canvas_export_folder(self) -> Path:
        project_path = str(getattr(self._host, "project_path", "") or "").strip()
        if project_path:
            parent = Path(project_path).expanduser().parent
            if str(parent):
                return parent
        return Path.cwd()

    def _choose_canvas_export_folder(self, suggested_path: str) -> str:
        presenter = getattr(self._host, "shell_host_presenter", None)
        choose = getattr(presenter, "choose_output_folder_dialog", None)
        if not callable(choose):
            return ""
        return str(
            choose(
                title="Choose Canvas Export Folder",
                suggested_path=str(suggested_path or ""),
            )
            or ""
        ).strip()

    def _capture_canvas_base_png(
        self,
        *,
        graph_canvas_item: QObject,
        output_path: Path,
        scale: int,
        device_pixel_ratio: float,
        expected_pixel_size: tuple[int, int],
    ) -> _CanvasBaseCaptureResult:
        result_box: dict[str, Any] = {}
        timed_out = {"value": False}
        loop = QEventLoop()
        request_id = f"canvas_export_{uuid4().hex}"

        def _finished(result: Any) -> None:
            result_box["result"] = _mapping(result)
            if loop.isRunning():
                loop.quit()

        signal = getattr(graph_canvas_item, "canvasBasePngExportFinished", None)
        if signal is None or not hasattr(signal, "connect"):
            raise CanvasViewExportError("Canvas base capture signal is not available.")
        signal.connect(_finished)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda: self._mark_canvas_capture_timeout(loop, timed_out)
        )
        try:
            timer.start(_CANVAS_BASE_CAPTURE_TIMEOUT_MS)
            request = {
                "request_id": request_id,
                "path": str(output_path),
                "scale": int(scale),
                "device_pixel_ratio": float(device_pixel_ratio),
                "width": int(expected_pixel_size[0]),
                "height": int(expected_pixel_size[1]),
            }
            try:
                invoked = QMetaObject.invokeMethod(
                    graph_canvas_item,
                    "exportCanvasBasePng",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG("QVariant", request),
                )
            except (RuntimeError, TypeError) as exc:
                raise CanvasViewExportError(
                    "Canvas base capture could not be started."
                ) from exc
            if invoked is False:
                raise CanvasViewExportError("Canvas base capture could not be started.")
            loop.exec()
        finally:
            timer.stop()
            try:
                signal.disconnect(_finished)
            except (TypeError, RuntimeError):
                pass
        if timed_out["value"]:
            raise CanvasViewExportError("Canvas base capture timed out.")
        result = result_box.get("result", {})
        if not bool(result.get("success")):
            message = str(
                result.get("error")
                or result.get("message")
                or "Canvas base capture failed."
            )
            raise CanvasViewExportError(message)
        result_request_id = str(result.get("request_id") or "").strip()
        if result_request_id != request_id:
            raise CanvasViewExportError(
                "Canvas base capture returned an unexpected request id."
            )
        result_path = Path(str(result.get("path") or "")).expanduser()
        if result_path != output_path:
            raise CanvasViewExportError(
                "Canvas base capture returned an unexpected output path."
            )
        if not output_path.exists():
            raise CanvasViewExportError("Canvas base PNG was not written.")
        canvas_logical_width = self._positive_capture_dimension(
            result.get("base_logical_width")
        )
        canvas_logical_height = self._positive_capture_dimension(
            result.get("base_logical_height")
        )
        if canvas_logical_width is None or canvas_logical_height is None:
            raise CanvasViewExportError(
                "Canvas base capture returned an invalid logical size."
            )
        output_width = self._positive_capture_integer(
            result.get("output_pixel_width", result.get("width"))
        )
        output_height = self._positive_capture_integer(
            result.get("output_pixel_height", result.get("height"))
        )
        if output_width is None or output_height is None:
            raise CanvasViewExportError(
                "Canvas base capture returned an invalid pixel size."
            )
        validate_export_pixel_size(output_width, output_height)
        result_dpr = self._positive_capture_dimension(result.get("device_pixel_ratio"))
        if result_dpr is None:
            raise CanvasViewExportError(
                "Canvas base capture returned an invalid device pixel ratio."
            )
        return _CanvasBaseCaptureResult(
            request_id=request_id,
            path=output_path,
            canvas_logical_size=(canvas_logical_width, canvas_logical_height),
            device_pixel_ratio=result_dpr,
            output_pixel_size=(output_width, output_height),
        )

    @staticmethod
    def _mark_canvas_capture_timeout(
        loop: QEventLoop, timed_out: dict[str, bool]
    ) -> None:
        timed_out["value"] = True
        if loop.isRunning():
            loop.quit()

    def _settle_canvas_export_frame(self) -> None:
        graph_canvas_item = self._graph_canvas_item()
        try:
            QMetaObject.invokeMethod(
                graph_canvas_item,
                "forceExactVisibleSceneModels",
                Qt.ConnectionType.DirectConnection,
            )
            QMetaObject.invokeMethod(
                graph_canvas_item,
                "flushViewStateRedraw",
                Qt.ConnectionType.DirectConnection,
            )
        except RuntimeError:
            pass
        for _index in range(3):
            QApplication.processEvents()

    def _sync_canvas_export_overlays(self) -> None:
        for service_name in ("viewer_host_service", "plot_host_service"):
            service = getattr(self._host, service_name, None)
            sync = getattr(service, "sync", None)
            if callable(sync):
                sync()
        overlay_manager = getattr(self._host, "embedded_viewer_overlay_manager", None)
        sync = getattr(overlay_manager, "sync", None)
        if callable(sync):
            sync()
        QApplication.processEvents()

    def _canvas_export_overlay_snapshots(self) -> tuple[Any, ...]:
        overlay_manager = getattr(self._host, "embedded_viewer_overlay_manager", None)
        snapshots = getattr(overlay_manager, "export_overlay_snapshots", None)
        if not callable(snapshots):
            return ()
        return tuple(snapshots())

    def _capture_canvas_export_overlay_image(self, snapshot: Any) -> QImage:
        owner = str(getattr(snapshot, "owner", "") or "").strip()
        if owner == VIEWER_SESSION_OVERLAY_OWNER:
            service = getattr(self._host, "viewer_host_service", None)
        elif owner == PLOT_HOST_OVERLAY_OWNER:
            service = getattr(self._host, "plot_host_service", None)
        else:
            return QImage()
        capture = getattr(service, "capture_overlay_preview_image", None)
        if not callable(capture):
            return QImage()
        return capture(
            str(getattr(snapshot, "node_id", "") or ""),
            workspace_id=str(getattr(snapshot, "workspace_id", "") or ""),
        )

    def _restore_canvas_export_view(self, workspace_id: str, view_id: str) -> None:
        if not view_id:
            return
        workspace = self._host.model.project.workspaces.get(workspace_id)
        if (
            workspace is None
            or view_id not in workspace.views
            or workspace.active_view_id == view_id
        ):
            return
        try:
            self._workspace_presenter.request_switch_view(view_id)
            self._settle_canvas_export_frame()
        except (RuntimeError, ValueError, CanvasViewExportError):
            pass

    @staticmethod
    def _format_canvas_export_failures(
        failures: Sequence[_CanvasViewExportFailure],
        *,
        all_failed: bool,
    ) -> str:
        prefix = (
            "Canvas view export failed for all selected views."
            if all_failed
            else (
                f"{len(failures)} canvas view export"
                f"{'' if len(failures) == 1 else 's'} failed."
            )
        )
        details = [
            f"{failure.view_name}: {failure.message}" for failure in failures[:5]
        ]
        if len(failures) > len(details):
            details.append(f"{len(failures) - len(details)} more failure(s) omitted.")
        return "\n".join([prefix, *details])

    def _dialog_parent(self) -> QWidget | None:
        return self._host if isinstance(self._host, QWidget) else None

    def _show_canvas_export_error(self, message: str) -> None:
        normalized = str(message or "Canvas view export failed.").strip()
        self._append_console_log("error", f"Canvas view export failed: {normalized}")
        self._host.show_graph_hint(normalized, 4200)
        QMessageBox.warning(self._dialog_parent(), "Export Canvas Views", normalized)

    def _show_canvas_export_complete(
        self,
        png_count: int,
        output_dir: Path,
        deck_path: Path | None,
        failures: Sequence[_CanvasViewExportFailure] = (),
    ) -> None:
        deck_text = f"\nPowerPoint deck: {deck_path}" if deck_path is not None else ""
        failure_text = (
            "\n\n" + self._format_canvas_export_failures(failures, all_failed=False)
            if failures
            else ""
        )
        QMessageBox.information(
            self._dialog_parent(),
            "Export Canvas Views",
            f"Exported {png_count} PNG file{'' if png_count == 1 else 's'} to:\n"
            f"{output_dir}{deck_text}{failure_text}",
        )

    def _append_console_log(self, level: str, message: str) -> None:
        console = getattr(self._host, "console_panel", None)
        append = getattr(console, "append_log", None)
        if callable(append):
            append(level, message)

    def _update_notification_counters(self) -> None:
        console = getattr(self._host, "console_panel", None)
        updater = getattr(self._host, "update_notification_counters", None)
        if callable(updater) and console is not None:
            updater(
                getattr(console, "warning_count", 0), getattr(console, "error_count", 0)
            )


__all__ = [
    "CanvasExportPresenter",
    "CanvasViewPngExport",
    "CanvasViewPngExportResult",
    "ProjectReviewCanvasCaptureSpec",
    "ProjectReviewCanvasCaptureViewport",
    "ProjectReviewCanvasPngExport",
    "ProjectReviewCanvasPngExportResult",
]
