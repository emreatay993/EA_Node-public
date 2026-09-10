from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QMarginsF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtWidgets import QApplication

from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import ViewState
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref, format_staged_artifact_ref
from ea_node_editor.persistence.artifact_store import format_node_artifact_folder, format_workspace_artifact_folder
from ea_node_editor.runtime_contracts import DataTree, ImageValue
from ea_node_editor.ui.dialogs.project_review_deck_dialog import ProjectReviewDeckDialog
from ea_node_editor.ui.image_value_preview_provider import (
    set_active_image_value_preview_provider,
)
from ea_node_editor.ui.pdf_preview_provider import render_pdf_page_image
from ea_node_editor.ui.pptx_export import ProjectReviewPptxSlide, create_project_review_pptx
from ea_node_editor.ui.plot_preview_cache_provider import ViewerPreviewCacheImageProvider
from ea_node_editor.ui.project_review_deck import (
    PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
    PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
    PROJECT_REVIEW_SLIDE_CANVAS,
    PROJECT_REVIEW_SLIDE_IMAGE,
    PROJECT_REVIEW_SLIDE_PDF,
    ProjectReviewDeckOptions,
    ProjectReviewDeckPlan,
    ProjectReviewDeckSection,
    ProjectReviewDeckSlide,
    ProjectReviewDeckWriterOptions,
    build_project_review_deck_plan,
    materialize_project_review_pptx_slides,
    selected_project_review_slides,
)
import ea_node_editor.ui.shell.presenters.project_review_deck_presenter as presenter_module
from ea_node_editor.ui.shell.presenters.project_review_deck_presenter import ProjectReviewDeckPresenter


def _solid_png(path: Path, width: int = 120, height: int = 80) -> None:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#4f86c6"))
    assert image.save(str(path), "PNG")


def _write_pdf(path: Path, *, page_count: int = 3) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        painter.drawText(QRectF(80.0, 120.0, 420.0, 120.0), f"PDF page {page_index + 1}")
    painter.end()


@pytest.fixture()
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _project_with_artifacts(tmp_path: Path) -> tuple[GraphModel, Path, Path, Path]:
    model = GraphModel()
    workspace = model.active_workspace
    workspace.name = "Main"
    registry = build_default_registry()
    image_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Image Evidence",
        100.0,
        120.0,
        properties={"source": format_managed_artifact_ref("image_artifact")},
        exposed_ports={"source": False},
    )
    pdf_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "PDF Evidence",
        280.0,
        120.0,
        properties={
            "source": format_managed_artifact_ref("pdf_artifact"),
            "page_number": 3,
        },
        exposed_ports={"source": False},
    )
    staged_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Staged Evidence",
        460.0,
        120.0,
        properties={"source": format_staged_artifact_ref("staged_artifact")},
        exposed_ports={"source": False},
    )
    staged_same_id_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Staged Same ID Evidence",
        640.0,
        120.0,
        properties={"source": format_staged_artifact_ref("image_artifact")},
        exposed_ports={"source": False},
    )
    unsupported_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Unsupported Evidence",
        820.0,
        120.0,
        properties={"source": format_managed_artifact_ref("text_artifact")},
        exposed_ports={"source": False},
    )
    model.add_node(
        workspace.workspace_id,
        "media.panel",
        "External Evidence",
        1000.0,
        120.0,
        properties={"source": str(tmp_path / "external.png")},
        exposed_ports={"source": False},
    )
    missing_node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Missing Evidence",
        1180.0,
        120.0,
        properties={"source": format_managed_artifact_ref("missing_artifact")},
        exposed_ports={"source": False},
    )
    project_path = tmp_path / "review_demo.cxproj"
    workspace_folder = format_workspace_artifact_folder(
        workspace_id=workspace.workspace_id,
        workspace_name=workspace.name,
    )

    def artifact_path(node, display_name: str, filename: str) -> tuple[Path, str]:  # noqa: ANN001
        node_folder = format_node_artifact_folder(
            workspace_id=workspace.workspace_id,
            node_id=node.node_id,
            node_title=node.title,
            node_type=display_name,
        )
        relative = f"workspaces/{workspace_folder}/nodes/{node_folder}/out/evidence/{filename}"
        return project_path.with_name("review_demo.data") / relative, relative

    image_path, image_relative = artifact_path(image_node, "Media Panel", "plot.png")
    pdf_path, pdf_relative = artifact_path(pdf_node, "Media Panel", "report.pdf")
    staged_path, staged_relative = artifact_path(staged_node, "Media Panel", "staged.png")
    staged_same_id_path, staged_same_id_relative = artifact_path(
        staged_same_id_node,
        "Media Panel",
        "same-id-staged.png",
    )
    text_path, text_relative = artifact_path(unsupported_node, "Media Panel", "notes.txt")
    _missing_path, missing_relative = artifact_path(missing_node, "Media Panel", "missing.png")
    orphan_path, orphan_relative = artifact_path(image_node, "Media Panel", "orphan.png")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    _solid_png(image_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    staged_same_id_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    _write_pdf(pdf_path, page_count=4)
    _solid_png(staged_path)
    _solid_png(staged_same_id_path)
    text_path.write_text("not embeddable", encoding="utf-8")
    _solid_png(orphan_path)
    _solid_png(tmp_path / "external.png")
    model.project.metadata = {
        "artifact_store": {
            "artifacts": {
                "image_artifact": {"relative_path": image_relative, "io_dir": "out"},
                "pdf_artifact": {"relative_path": pdf_relative, "io_dir": "out"},
                "text_artifact": {"relative_path": text_relative, "io_dir": "out"},
                "missing_artifact": {"relative_path": missing_relative, "io_dir": "out"},
                "orphan_artifact": {"relative_path": orphan_relative, "io_dir": "out"},
            },
            "staged": {
                "staged_artifact": {"relative_path": staged_relative, "io_dir": "tmp"},
                "image_artifact": {"relative_path": staged_same_id_relative, "io_dir": "tmp"},
            }
        }
    }
    assert registry.get_spec("media.panel").display_name == "Media Panel"
    return model, project_path, image_path, pdf_path


def test_project_review_plan_uses_referenced_artifacts_and_pdf_panel_page(tmp_path, qapp) -> None:  # noqa: ANN001
    model, project_path, image_path, pdf_path = _project_with_artifacts(tmp_path)

    plan = build_project_review_deck_plan(
        project=model.project,
        options=ProjectReviewDeckOptions(
            project_path=project_path,
            registry=build_default_registry(),
        ),
    )
    evidence = [
        slide
        for section in plan.sections
        for slide in section.slides
        if slide.kind in {PROJECT_REVIEW_SLIDE_IMAGE, PROJECT_REVIEW_SLIDE_PDF}
    ]

    assert [slide.kind for slide in evidence] == [
        PROJECT_REVIEW_SLIDE_IMAGE,
        PROJECT_REVIEW_SLIDE_PDF,
        PROJECT_REVIEW_SLIDE_IMAGE,
        PROJECT_REVIEW_SLIDE_IMAGE,
        PROJECT_REVIEW_SLIDE_IMAGE,
    ]
    assert [slide.slide_id for slide in evidence[:4]] == [
        "artifact:saved:image_artifact",
        "artifact:saved:pdf_artifact",
        "artifact:temp:staged_artifact",
        "artifact:temp:image_artifact",
    ]
    assert evidence[4].slide_id.startswith("media:")
    assert evidence[0].source_path == image_path
    assert evidence[1].source_path == pdf_path
    assert evidence[1].page_number == 3
    assert evidence[1].page_count == 4
    assert evidence[2].artifact_id == "staged_artifact"
    assert evidence[3].source_path is not None
    assert evidence[3].source_path.name == "same-id-staged.png"
    assert len({slide.slide_id for slide in evidence}) == len(evidence)
    assert not any(slide.artifact_id == "orphan_artifact" for slide in evidence)
    assert not any(slide.artifact_id == "missing_artifact" for slide in evidence)
    assert any("source is invalid" in warning for warning in plan.warnings)
    assert any("uses a temporary project file" in warning for warning in plan.warnings)
    assert any("source is stale" in warning for warning in plan.warnings)


def test_project_review_media_input_never_falls_back_to_dormant_source(tmp_path, qapp) -> None:  # noqa: ANN001, ARG001
    model = GraphModel()
    workspace = model.active_workspace
    dormant_path = tmp_path / "dormant.png"
    _solid_png(dormant_path)
    model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Waiting Media",
        20.0,
        30.0,
        properties={"source": str(dormant_path)},
        exposed_ports={"source": True},
    )

    plan = build_project_review_deck_plan(project=model.project)
    evidence = [
        slide
        for section in plan.sections
        for slide in section.slides
        if slide.kind in {PROJECT_REVIEW_SLIDE_IMAGE, PROJECT_REVIEW_SLIDE_PDF}
    ]

    assert evidence == []
    assert any("source is waiting" in warning for warning in plan.warnings)
    assert not any("dormant.png" in warning for warning in plan.warnings)


def test_project_review_materializes_runtime_image_value_only_in_temp_area(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Runtime Image",
        20.0,
        30.0,
        properties={"source": ""},
        exposed_ports={"source": True},
    )
    workspace.edges["edge-1"] = SimpleNamespace(
        enabled=True,
        target_node_id=node.node_id,
        target_port_key="source",
    )
    image_path = tmp_path / "runtime.png"
    _solid_png(image_path)
    image_value = ImageValue.from_png(image_path.read_bytes())
    run_state = SimpleNamespace(
        node_execution_workspace_id=workspace.workspace_id,
        running_node_ids=set(),
        completed_node_ids={node.node_id},
        empty_node_ids=set(),
        failed_node_ids=set(),
        blocked_node_ids=set(),
        root_errors_by_node_id={},
        cached_node_output_records_by_workspace_id={
            workspace.workspace_id: {
                node.node_id: {
                    "run-1": {
                        "record_id": "run-1",
                        "observed_at_epoch_ms": 1.0,
                        "outputs": {
                            "_surface_source": SettledPortResult(
                                status="value",
                                value=DataTree.from_item(image_value),
                            )
                        },
                    }
                }
            }
        },
        node_solution_facts_by_workspace_id={
            workspace.workspace_id: {
                node.node_id: NodeSolutionFact(
                    project_id=model.project.project_id,
                    workspace_id=workspace.workspace_id,
                    node_id=node.node_id,
                    freshness=SolutionFreshness.CURRENT,
                    revision=1,
                    retained_record_id="run-1",
                    retained_solution_key="a" * 64,
                    residency=SolutionResidency.SESSION,
                    last_disposition=SolutionDisposition.RECOMPUTED,
                )
            }
        },
    )
    provider = ViewerPreviewCacheImageProvider()
    set_active_image_value_preview_provider(provider)
    try:
        plan = build_project_review_deck_plan(
            project=model.project,
            run_state=run_state,
        )
    finally:
        set_active_image_value_preview_provider(None)
    slide = next(
        slide
        for section in plan.sections
        for slide in section.slides
        if slide.kind == PROJECT_REVIEW_SLIDE_IMAGE
    )
    assert slide.source_path is None
    assert slide.image_value is image_value

    temp_root = tmp_path / "deck-temp"
    materialized = materialize_project_review_pptx_slides(
        slides=(slide,),
        canvas_images_by_slide_id={},
        temp_dir=temp_root,
    )

    assert materialized.slides[0].image_path is not None
    assert materialized.slides[0].image_path.parent == temp_root
    assert materialized.slides[0].image_path.read_bytes() == image_value.encoded_bytes


def test_project_review_plan_splits_workspace_snapshots_and_saved_views(tmp_path, qapp) -> None:  # noqa: ANN001, ARG001
    model = GraphModel()
    workspace = model.active_workspace
    workspace.name = "Main"
    workspace.views = {
        "overview": ViewState("overview", "Overview", zoom=1.25, pan_x=10.0, pan_y=-5.0),
        "detail": ViewState("detail", "Detail", zoom=2.0, pan_x=40.0, pan_y=80.0),
    }
    workspace.active_view_id = "overview"

    plan = build_project_review_deck_plan(project=model.project, project_path=tmp_path / "demo.cxproj")
    sections_by_id = {section.section_id: section for section in plan.sections}

    snapshot_slides = sections_by_id["workspace-snapshots"].slides
    view_slides = sections_by_id["workspace-views"].slides

    assert [slide.slide_id for slide in snapshot_slides] == [f"canvas:snapshot:{workspace.workspace_id}"]
    assert snapshot_slides[0].title == "Main - Snapshot"
    assert snapshot_slides[0].canvas_capture_mode == PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT
    assert snapshot_slides[0].view_id == ""
    assert [slide.slide_id for slide in view_slides] == [
        f"canvas:view:{workspace.workspace_id}:overview",
        f"canvas:view:{workspace.workspace_id}:detail",
    ]
    assert [slide.title for slide in view_slides] == ["Main - Overview", "Main - Detail"]
    assert all(slide.canvas_capture_mode == PROJECT_REVIEW_CANVAS_CAPTURE_VIEW for slide in view_slides)
    selected = selected_project_review_slides(
        plan,
        (
            f"canvas:view:{workspace.workspace_id}:detail",
            f"canvas:snapshot:{workspace.workspace_id}",
            f"canvas:view:{workspace.workspace_id}:overview",
        ),
    )
    assert [slide.slide_id for slide in selected] == [
        f"canvas:view:{workspace.workspace_id}:detail",
        f"canvas:snapshot:{workspace.workspace_id}",
        f"canvas:view:{workspace.workspace_id}:overview",
    ]


def test_project_review_materialization_renders_pdf_page_and_keeps_selected_order(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    model, project_path, _image_path, _pdf_path = _project_with_artifacts(tmp_path)
    plan = build_project_review_deck_plan(
        project=model.project,
        project_path=project_path,
        registry=build_default_registry(),
    )
    selected = selected_project_review_slides(
        plan,
        [
            "summary:title",
            "artifact:saved:pdf_artifact",
            "artifact:saved:image_artifact",
        ],
    )

    materialized = materialize_project_review_pptx_slides(
        slides=selected,
        canvas_images_by_slide_id={},
        temp_dir=tmp_path / "deck-images",
    )

    assert [slide.title for slide in materialized.slides][0] == model.project.name
    assert materialized.slides[1].image_path is not None
    assert materialized.slides[1].image_path.exists()
    assert "PDF page 3 of 4" == materialized.slides[1].footer
    assert materialized.slides[2].image_path is not None
    assert not materialized.warnings


def test_render_pdf_page_image_public_helper_clamps_and_returns_info(tmp_path, qapp) -> None:  # noqa: ANN001
    pdf_path = tmp_path / "manual.pdf"
    _write_pdf(pdf_path, page_count=2)

    image, info = render_pdf_page_image(str(pdf_path), 99, (300, 300))

    assert info["state"] == "ready"
    assert info["requested_page_number"] == 99
    assert info["resolved_page_number"] == 2
    assert not image.isNull()
    assert image.width() <= 300
    assert image.height() <= 300


def test_project_review_pptx_writer_uses_optional_template(tmp_path, qapp) -> None:  # noqa: ANN001
    pptx = pytest.importorskip("pptx")
    image_path = tmp_path / "evidence.png"
    blank_output_path = tmp_path / "review-blank.pptx"
    template_path = tmp_path / "template.pptx"
    output_path = tmp_path / "review.pptx"
    _solid_png(image_path)
    pptx.Presentation().save(str(template_path))
    create_project_review_pptx(
        slides=[ProjectReviewPptxSlide(title="Blank Fallback", body_lines=("One",))],
        output_path=blank_output_path,
    )
    writer_options = ProjectReviewDeckWriterOptions(
        output_path=output_path,
        template_path=template_path,
        selected_slide_ids=("title", "evidence"),
    )

    create_project_review_pptx(
        slides=[
            ProjectReviewPptxSlide(title="Title", body_lines=("One", "Two")),
            ProjectReviewPptxSlide(title="Evidence", image_path=image_path, footer="Footer"),
        ],
        output_path=writer_options.output_path,
        slide_size=writer_options.slide_size,
        template_path=writer_options.template_path,
    )

    presentation = pptx.Presentation(str(output_path))
    blank_presentation = pptx.Presentation(str(blank_output_path))
    assert len(blank_presentation.slides) == 1
    assert len(presentation.slides) == 2
    assert presentation.slide_width > presentation.slide_height
    pictures = [shape for shape in presentation.slides[1].shapes if shape.shape_type == 13]
    assert len(pictures) == 1


def test_project_review_deck_dialog_collects_checked_tree_order(tmp_path, qapp) -> None:  # noqa: ANN001
    plan = ProjectReviewDeckPlan(
        project_name="Demo",
        project_path=str(tmp_path / "demo.cxproj"),
        sections=(
            ProjectReviewDeckSection(
                section_id="evidence",
                title="Evidence",
                slides=(
                    ProjectReviewDeckSlide("slide-a", "image", "A"),
                    ProjectReviewDeckSlide("slide-b", "image", "B"),
                ),
            ),
        ),
    )
    dialog = ProjectReviewDeckDialog(plan=plan, output_path=tmp_path / "review.pptx")
    qapp.processEvents()
    try:
        section = dialog.tree.topLevelItem(0)
        dialog.tree.setCurrentItem(section.child(0))
        dialog.move_down_button.click()
        section.child(1).setCheckState(0, Qt.CheckState.Unchecked)
        values = dialog.values()
    finally:
        dialog.deleteLater()

    assert values.slide_ids == ["slide-b"]
    assert values.output_path == tmp_path / "review.pptx"
    assert values.crop_canvas_snapshots is True


def test_project_review_deck_dialog_reorders_slides_across_sections(tmp_path, qapp) -> None:  # noqa: ANN001
    plan = ProjectReviewDeckPlan(
        project_name="Demo",
        project_path=str(tmp_path / "demo.cxproj"),
        sections=(
            ProjectReviewDeckSection(
                section_id="summary",
                title="Summary",
                slides=(ProjectReviewDeckSlide("title", "title", "Title"),),
            ),
            ProjectReviewDeckSection(
                section_id="evidence",
                title="Evidence",
                slides=(
                    ProjectReviewDeckSlide("slide-a", "image", "A"),
                    ProjectReviewDeckSlide("slide-b", "image", "B"),
                ),
            ),
            ProjectReviewDeckSection(
                section_id="issues",
                title="Issues",
                slides=(ProjectReviewDeckSlide("slide-c", "issue", "C"),),
            ),
        ),
    )
    dialog = ProjectReviewDeckDialog(plan=plan, output_path=tmp_path / "review.pptx")
    qapp.processEvents()
    try:
        evidence = dialog.tree.topLevelItem(1)
        dialog.tree.setCurrentItem(evidence.child(0))
        dialog.move_up_button.click()
        dialog.move_up_button.click()
        assert dialog.values().slide_ids == ["slide-a", "title", "slide-b", "slide-c"]

        issues = dialog.tree.topLevelItem(2)
        dialog.tree.setCurrentItem(issues)
        dialog.move_up_button.click()
        dialog.crop_check.setChecked(False)
        values = dialog.values()
    finally:
        dialog.deleteLater()

    assert values.slide_ids == ["slide-a", "title", "slide-c", "slide-b"]
    assert values.crop_canvas_snapshots is False


def test_project_review_deck_presenter_opens_exported_powerpoint_on_success(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "review.pptx"
    slide = ProjectReviewDeckSlide("summary:title", "title", "Title")
    plan = ProjectReviewDeckPlan(
        project_name="Demo",
        project_path=str(tmp_path / "demo.cxproj"),
        sections=(
            ProjectReviewDeckSection(
                section_id="summary",
                title="Summary",
                slides=(slide,),
            ),
        ),
    )
    materialized_slide = SimpleNamespace(title="Title")
    opened_paths: list[Path] = []
    information_messages: list[tuple[object, str, str]] = []
    hints: list[tuple[str, int]] = []
    logs: list[tuple[str, str]] = []

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            assert kwargs["plan"] is plan
            assert kwargs["output_path"] == output_path

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def values(self) -> SimpleNamespace:
            return SimpleNamespace(
                output_path=output_path,
                slide_size="16:9 landscape",
                template_path=None,
                slide_ids=("summary:title",),
                crop_canvas_snapshots=True,
            )

    def _materialize(**kwargs) -> SimpleNamespace:  # noqa: ANN003
        assert kwargs["slides"] == (slide,)
        assert kwargs["canvas_images_by_slide_id"] == {}
        return SimpleNamespace(slides=(materialized_slide,), warnings=())

    def _create_pptx(**kwargs) -> Path:  # noqa: ANN003
        assert kwargs["slides"] == [materialized_slide]
        assert kwargs["output_path"] == output_path
        output_path.write_text("pptx placeholder", encoding="utf-8")
        return output_path

    monkeypatch.setattr(presenter_module, "build_project_review_deck_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(
        presenter_module,
        "default_project_review_deck_path",
        lambda _project_path, _project_name: output_path,
    )
    monkeypatch.setattr(presenter_module, "ProjectReviewDeckDialog", _Dialog)
    monkeypatch.setattr(presenter_module, "materialize_project_review_pptx_slides", _materialize)
    monkeypatch.setattr(presenter_module, "create_project_review_pptx", _create_pptx)
    monkeypatch.setattr(
        presenter_module,
        "open_path_with_default_handler",
        lambda path: opened_paths.append(Path(path)) or True,
    )
    monkeypatch.setattr(
        presenter_module.QMessageBox,
        "information",
        lambda parent, title, message: information_messages.append((parent, title, message)),
    )

    host = SimpleNamespace(
        model=SimpleNamespace(project=SimpleNamespace(name="Demo")),
        project_path=tmp_path / "demo.cxproj",
        registry=None,
        workspace_manager=SimpleNamespace(active_workspace_id=lambda: "ws"),
        workspace_navigation_controller=SimpleNamespace(
            switch_workspace=lambda _workspace_id: None
        ),
        canvas_export_presenter=SimpleNamespace(),
        console_panel=SimpleNamespace(append_log=lambda level, message: logs.append((level, message))),
        show_graph_hint=lambda message, timeout: hints.append((message, timeout)),
    )
    presenter = ProjectReviewDeckPresenter(host)

    assert presenter.export_project_review_deck() is True

    assert opened_paths == [output_path]
    assert hints == [("Project review deck export complete.", 3000)]
    assert information_messages == [
        (None, "Export Project Review Deck", f"Project review deck saved and opened:\n{output_path}")
    ]
    assert logs == [("info", f"Project review PowerPoint deck saved to {output_path}.")]


def test_project_review_deck_presenter_forwards_crop_opt_out_for_canvas_slide(
    tmp_path: Path,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "review.pptx"
    slide = ProjectReviewDeckSlide(
        "canvas:ws:view",
        PROJECT_REVIEW_SLIDE_CANVAS,
        "Canvas",
        canvas_capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
        workspace_id="ws",
    )
    plan = ProjectReviewDeckPlan(
        project_name="Demo",
        project_path=str(tmp_path / "demo.cxproj"),
        sections=(
            ProjectReviewDeckSection(
                section_id="canvas",
                title="Canvas",
                slides=(slide,),
            ),
        ),
    )
    materialized_slide = SimpleNamespace(title="Canvas")
    crop_values: list[bool] = []
    information_messages: list[tuple[object, str, str]] = []
    logs: list[tuple[str, str]] = []

    class _Dialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            assert kwargs["plan"] is plan

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def values(self) -> SimpleNamespace:
            return SimpleNamespace(
                output_path=output_path,
                slide_size="16:9 landscape",
                template_path=None,
                slide_ids=(slide.slide_id,),
                crop_canvas_snapshots=False,
            )

    class _CanvasPresenter:
        def capture_project_review_canvas_pngs(self, *, capture_specs, output_dir, scale):  # noqa: ANN001
            assert scale == 1
            crop_values.extend(bool(spec.crop_to_content) for spec in capture_specs)
            output_path = Path(output_dir) / "snapshot.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _solid_png(output_path)
            return SimpleNamespace(
                exports=(SimpleNamespace(slide_id=capture_specs[0].slide_id, path=output_path),),
                failures=(),
            )

    def _materialize(**kwargs) -> SimpleNamespace:  # noqa: ANN003
        assert kwargs["slides"] == (slide,)
        canvas_images = kwargs["canvas_images_by_slide_id"]
        assert set(canvas_images) == {slide.slide_id}
        assert canvas_images[slide.slide_id].exists()
        return SimpleNamespace(slides=(materialized_slide,), warnings=())

    def _create_pptx(**kwargs) -> Path:  # noqa: ANN003
        assert kwargs["slides"] == [materialized_slide]
        output_path.write_text("pptx placeholder", encoding="utf-8")
        return output_path

    monkeypatch.setattr(presenter_module, "build_project_review_deck_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(
        presenter_module,
        "default_project_review_deck_path",
        lambda _project_path, _project_name: output_path,
    )
    monkeypatch.setattr(presenter_module, "ProjectReviewDeckDialog", _Dialog)
    monkeypatch.setattr(presenter_module, "materialize_project_review_pptx_slides", _materialize)
    monkeypatch.setattr(presenter_module, "create_project_review_pptx", _create_pptx)
    monkeypatch.setattr(presenter_module, "open_path_with_default_handler", lambda _path: True)
    monkeypatch.setattr(
        presenter_module.QMessageBox,
        "information",
        lambda parent, title, message: information_messages.append((parent, title, message)),
    )

    host = SimpleNamespace(
        model=SimpleNamespace(
            project=SimpleNamespace(
                name="Demo",
                workspaces={
                    "ws": SimpleNamespace(
                        views={},
                        active_view_id="",
                        ensure_default_view=lambda: None,
                    ),
                },
            ),
        ),
        project_path=tmp_path / "demo.cxproj",
        registry=None,
        workspace_manager=SimpleNamespace(active_workspace_id=lambda: "ws"),
        workspace_navigation_controller=SimpleNamespace(
            switch_workspace=lambda _workspace_id: None
        ),
        canvas_export_presenter=_CanvasPresenter(),
        console_panel=SimpleNamespace(append_log=lambda level, message: logs.append((level, message))),
        show_graph_hint=lambda _message, _timeout: None,
    )
    presenter = ProjectReviewDeckPresenter(host)

    assert presenter.export_project_review_deck() is True

    assert crop_values == [False]
    assert output_path.read_text(encoding="utf-8") == "pptx placeholder"
    assert information_messages


def test_project_review_deck_presenter_passes_crop_option_to_canvas_capture(tmp_path, qapp) -> None:  # noqa: ANN001
    class _WorkspaceManager:
        def active_workspace_id(self) -> str:
            return "ws"

    class _CanvasPresenter:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple[object, ...], Path, int]] = []

        def capture_project_review_canvas_pngs(self, *, capture_specs, output_dir, scale):  # noqa: ANN001
            self.calls.append((tuple(capture_specs), Path(output_dir), int(scale)))
            exports = []
            for spec in capture_specs:
                output_path = Path(output_dir) / f"{spec.slide_id.replace(':', '-')}.png"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _solid_png(output_path)
                exports.append(SimpleNamespace(slide_id=spec.slide_id, path=output_path))
            return SimpleNamespace(
                exports=tuple(exports),
                failures=(),
            )

    workspace = SimpleNamespace(
        views={
            "view": ViewState("view", "View", zoom=2.5, pan_x=120.0, pan_y=-40.0),
        },
        active_view_id="view",
        ensure_default_view=lambda: None,
    )
    canvas_presenter = _CanvasPresenter()
    host = SimpleNamespace(
        model=SimpleNamespace(project=SimpleNamespace(workspaces={"ws": workspace})),
        workspace_manager=_WorkspaceManager(),
        workspace_navigation_controller=SimpleNamespace(
            switch_workspace=lambda _workspace_id: None
        ),
        canvas_export_presenter=canvas_presenter,
    )
    presenter = ProjectReviewDeckPresenter(host)
    snapshot_slide = ProjectReviewDeckSlide(
        "canvas:snapshot:ws",
        PROJECT_REVIEW_SLIDE_CANVAS,
        "Workspace - Snapshot",
        canvas_capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
        workspace_id="ws",
    )
    view_slide = ProjectReviewDeckSlide(
        "canvas:view:ws:view",
        PROJECT_REVIEW_SLIDE_CANVAS,
        "Workspace - View",
        canvas_capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
        workspace_id="ws",
        view_id="view",
    )

    images, warnings = presenter._capture_canvas_images(
        (snapshot_slide, view_slide),
        tmp_path / "canvas",
        crop_to_content=True,
    )

    capture_specs, output_dir, scale = canvas_presenter.calls[0]
    assert output_dir == tmp_path / "canvas"
    assert scale == 1
    assert [spec.slide_id for spec in capture_specs] == [
        "canvas:snapshot:ws",
        "canvas:view:ws:view",
    ]
    assert [spec.capture_mode for spec in capture_specs] == [
        PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
        PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
    ]
    assert [spec.crop_to_content for spec in capture_specs] == [True, False]
    assert capture_specs[1].viewport.zoom == 2.5
    assert capture_specs[1].viewport.center_x == 120.0
    assert capture_specs[1].viewport.center_y == -40.0
    assert images == {
        "canvas:snapshot:ws": tmp_path / "canvas" / "canvas-snapshot-ws.png",
        "canvas:view:ws:view": tmp_path / "canvas" / "canvas-view-ws-view.png",
    }
    assert warnings == ()
