from __future__ import annotations

import copy
from collections import defaultdict
from pathlib import Path
import tempfile

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ea_node_editor.platform_open import open_path_with_default_handler
from ea_node_editor.ui.canvas_view_export import CanvasViewExportError
from ea_node_editor.ui.dialogs.project_review_deck_dialog import ProjectReviewDeckDialog
from ea_node_editor.ui.project_review_deck import (
    PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
    PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
    PROJECT_REVIEW_SLIDE_CANVAS,
    ProjectReviewDeckOptions,
    ProjectReviewDeckSlide,
    ProjectReviewDeckWriterOptions,
    build_project_review_deck_plan,
    default_project_review_deck_path,
    materialize_project_review_pptx_slides,
    selected_project_review_slides,
)
from ea_node_editor.ui.pptx_export import CanvasViewPptxExportError, create_project_review_pptx

from .contracts import _ProjectReviewDeckPresenterHostProtocol, _presenter_parent
from .canvas_export_presenter import (
    ProjectReviewCanvasCaptureSpec,
    ProjectReviewCanvasCaptureViewport,
)


class ProjectReviewDeckPresenter(QObject):
    def __init__(
        self,
        host: _ProjectReviewDeckPresenterHostProtocol,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(_presenter_parent(host, parent))
        self._host = host

    def export_project_review_deck(self) -> bool:
        try:
            project = self._host.model.project
            plan = build_project_review_deck_plan(
                project=project,
                options=ProjectReviewDeckOptions(
                    project_path=self._host.project_path,
                    registry=getattr(self._host, "registry", None),
                    run_state=getattr(self._host, "run_state", None),
                ),
            )
            dialog = ProjectReviewDeckDialog(
                plan=plan,
                output_path=default_project_review_deck_path(self._host.project_path, project.name),
                browse_output_callback=self._choose_output_path,
                browse_template_callback=self._choose_template_path,
                parent=self._dialog_parent(),
            )
            if dialog.exec() != ProjectReviewDeckDialog.DialogCode.Accepted:
                return False
            values = dialog.values()
            writer_options = ProjectReviewDeckWriterOptions(
                output_path=values.output_path,
                slide_size=values.slide_size,
                template_path=values.template_path,
                selected_slide_ids=tuple(values.slide_ids),
                crop_canvas_snapshots=values.crop_canvas_snapshots,
            )
            selected_slides = selected_project_review_slides(
                plan,
                writer_options.selected_slide_ids,
            )
            if not selected_slides:
                self._show_error("Select at least one slide to export.")
                return False

            with tempfile.TemporaryDirectory(prefix="project-review-deck-") as temp_dir:
                temp_root = Path(temp_dir)
                canvas_images, capture_warnings = self._capture_canvas_images(
                    selected_slides,
                    temp_root / "canvas",
                    crop_to_content=writer_options.crop_canvas_snapshots,
                )
                materialized = materialize_project_review_pptx_slides(
                    slides=selected_slides,
                    canvas_images_by_slide_id=canvas_images,
                    temp_dir=temp_root / "evidence",
                )
                all_warnings = (*capture_warnings, *materialized.warnings)
                deck_path = create_project_review_pptx(
                    slides=list(materialized.slides),
                    output_path=writer_options.output_path,
                    slide_size=writer_options.slide_size,
                    template_path=writer_options.template_path,
                )
            self._append_console_log("info", f"Project review PowerPoint deck saved to {deck_path}.")
            opened_deck = open_path_with_default_handler(deck_path)
            if all_warnings:
                self._append_console_log(
                    "warning",
                    "Project review deck exported with warnings: " + " ".join(all_warnings),
                )
            if not opened_deck:
                self._append_console_log(
                    "warning",
                    f"Project review PowerPoint deck could not be opened automatically: {deck_path}.",
                )
            self._host.show_graph_hint("Project review deck export complete.", 3000)
            message = (
                f"Project review deck saved and opened:\n{deck_path}"
                if opened_deck
                else f"Project review deck saved to:\n{deck_path}\n\n"
                "The deck could not be opened automatically."
            )
            QMessageBox.information(
                self._dialog_parent(),
                "Export Project Review Deck",
                message,
            )
            return True
        except (CanvasViewExportError, CanvasViewPptxExportError, OSError, RuntimeError, ValueError) as exc:
            self._show_error(str(exc or "Project review deck export failed."))
            return False

    def _capture_canvas_images(
        self,
        slides: tuple[ProjectReviewDeckSlide, ...],
        output_dir: Path,
        *,
        crop_to_content: bool = True,
    ) -> tuple[dict[str, Path], tuple[str, ...]]:
        canvas_slides = [slide for slide in slides if slide.kind == PROJECT_REVIEW_SLIDE_CANVAS]
        if not canvas_slides:
            return {}, ()
        grouped: dict[str, list[ProjectReviewDeckSlide]] = defaultdict(list)
        for slide in canvas_slides:
            grouped[slide.workspace_id].append(slide)

        original_workspace_id = str(self._host.workspace_manager.active_workspace_id() or "").strip()
        workspace_snapshots = self._workspace_view_snapshots(
            {workspace_id for workspace_id in grouped if workspace_id} | {original_workspace_id}
        )
        images: dict[str, Path] = {}
        warnings: list[str] = []
        try:
            for workspace_id, workspace_slides in grouped.items():
                active_workspace_id = str(
                    self._host.workspace_manager.active_workspace_id() or ""
                ).strip()
                if workspace_id and workspace_id != active_workspace_id:
                    self._switch_workspace(workspace_id)
                workspace = self._host.model.project.workspaces.get(workspace_id)
                if workspace is None:
                    for slide in workspace_slides:
                        warnings.append(f"{slide.title}: workspace is no longer available.")
                    continue
                capture_specs, spec_warnings = self._project_review_canvas_capture_specs(
                    workspace=workspace,
                    slides=workspace_slides,
                    crop_to_content=crop_to_content,
                )
                warnings.extend(spec_warnings)
                if not capture_specs:
                    continue
                result = self._host.canvas_export_presenter.capture_project_review_canvas_pngs(
                    capture_specs=capture_specs,
                    output_dir=output_dir,
                    scale=1,
                )
                for export in result.exports:
                    images[export.slide_id] = export.path
                for failure in result.failures:
                    warnings.append(f"{failure.view_name}: {failure.message}")
        finally:
            self._restore_workspace_view_snapshots(workspace_snapshots)
            try:
                if original_workspace_id:
                    self._switch_workspace(original_workspace_id)
            finally:
                self._restore_workspace_view_snapshots(workspace_snapshots)
        return images, tuple(warnings)

    def _project_review_canvas_capture_specs(
        self,
        *,
        workspace: object,
        slides: list[ProjectReviewDeckSlide],
        crop_to_content: bool,
    ) -> tuple[list[ProjectReviewCanvasCaptureSpec], list[str]]:
        specs: list[ProjectReviewCanvasCaptureSpec] = []
        warnings: list[str] = []
        views = getattr(workspace, "views", {})
        for slide in slides:
            mode = self._project_review_canvas_capture_mode(slide)
            if mode == PROJECT_REVIEW_CANVAS_CAPTURE_VIEW:
                view = views.get(slide.view_id) if hasattr(views, "get") else None
                if view is None:
                    warnings.append(f"{slide.title}: saved workspace view is no longer available.")
                    continue
                specs.append(
                    ProjectReviewCanvasCaptureSpec(
                        slide_id=slide.slide_id,
                        display_name=slide.title,
                        capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
                        view_id=slide.view_id,
                        viewport=ProjectReviewCanvasCaptureViewport(
                            zoom=getattr(view, "zoom", 1.0),
                            center_x=getattr(view, "pan_x", 0.0),
                            center_y=getattr(view, "pan_y", 0.0),
                        ),
                        crop_to_content=False,
                    )
                )
                continue
            specs.append(
                ProjectReviewCanvasCaptureSpec(
                    slide_id=slide.slide_id,
                    display_name=slide.title,
                    capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
                    view_id=slide.view_id,
                    viewport=None,
                    crop_to_content=crop_to_content,
                )
            )
        return specs, warnings

    @staticmethod
    def _project_review_canvas_capture_mode(slide: ProjectReviewDeckSlide) -> str:
        mode = str(slide.canvas_capture_mode or "").strip().lower()
        if mode in {PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT, PROJECT_REVIEW_CANVAS_CAPTURE_VIEW}:
            return mode
        return PROJECT_REVIEW_CANVAS_CAPTURE_VIEW if slide.view_id else PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT

    def _workspace_view_snapshots(self, workspace_ids: set[str]) -> dict[str, tuple[dict[str, object], str]]:
        project = getattr(getattr(self._host, "model", None), "project", None)
        workspaces = getattr(project, "workspaces", {})
        snapshots: dict[str, tuple[dict[str, object], str]] = {}
        for workspace_id in workspace_ids:
            workspace = workspaces.get(workspace_id) if hasattr(workspaces, "get") else None
            if workspace is None:
                continue
            snapshots[workspace_id] = (
                copy.deepcopy(getattr(workspace, "views", {})),
                str(getattr(workspace, "active_view_id", "") or ""),
            )
        return snapshots

    def _restore_workspace_view_snapshots(self, snapshots: dict[str, tuple[dict[str, object], str]]) -> None:
        project = getattr(getattr(self._host, "model", None), "project", None)
        workspaces = getattr(project, "workspaces", {})
        for workspace_id, (views, active_view_id) in snapshots.items():
            workspace = workspaces.get(workspace_id) if hasattr(workspaces, "get") else None
            if workspace is None:
                continue
            workspace.views = copy.deepcopy(views)
            workspace.active_view_id = active_view_id
            ensure_default_view = getattr(workspace, "ensure_default_view", None)
            if callable(ensure_default_view):
                ensure_default_view()

    def _switch_workspace(self, workspace_id: str) -> None:
        self._host.workspace_navigation_controller.switch_workspace(workspace_id)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def _choose_output_path(self, suggested_path: str) -> str:
        presenter = getattr(self._host, "shell_host_presenter", None)
        save_file = getattr(presenter, "save_file_dialog", None)
        if callable(save_file):
            return str(
                save_file(
                    title="Export Project Review Deck",
                    suggested_path=suggested_path,
                    file_filter="PowerPoint Deck (*.pptx)",
                    default_suffix=".pptx",
                )
                or ""
            )
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog_parent(),
            "Export Project Review Deck",
            suggested_path,
            "PowerPoint Deck (*.pptx)",
        )
        return str(selected_path or "").strip()

    def _choose_template_path(self, suggested_path: str) -> str:
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self._dialog_parent(),
            "Choose PowerPoint Template",
            suggested_path,
            "PowerPoint Deck (*.pptx)",
        )
        return str(selected_path or "").strip()

    def _dialog_parent(self):
        return self._host if isinstance(self._host, QObject) else None

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(
            self._dialog_parent(),
            "Export Project Review Deck",
            message or "Project review deck export failed.",
        )

    def _append_console_log(self, level: str, message: str) -> None:
        console = getattr(self._host, "console_panel", None)
        append = getattr(console, "append_log", None)
        if callable(append):
            append(level, message)


__all__ = ["ProjectReviewDeckPresenter"]
