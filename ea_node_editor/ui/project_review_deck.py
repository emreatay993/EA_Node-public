from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, QUrl
from PyQt6.QtGui import QImage

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.file_dialog_filters import IMAGE_FILE_SUFFIXES
from ea_node_editor.common.artifact_refs import ManagedArtifactRef, StagedArtifactRef, parse_artifact_ref
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import ImageValue
from ea_node_editor.ui.canvas_view_export import collision_safe_path, safe_filename_component
from ea_node_editor.ui.media_panel_source import resolve_media_panel_source
from ea_node_editor.ui.pdf_preview_provider import describe_pdf_preview, render_pdf_page_image
from ea_node_editor.ui.pptx_export import ProjectReviewPptxSlide

PROJECT_REVIEW_SLIDE_TITLE = "title"
PROJECT_REVIEW_SLIDE_CANVAS = "canvas"
PROJECT_REVIEW_SLIDE_IMAGE = "image"
PROJECT_REVIEW_SLIDE_PDF = "pdf"
PROJECT_REVIEW_SLIDE_ISSUE = "issue"
PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT = "snapshot"
PROJECT_REVIEW_CANVAS_CAPTURE_VIEW = "view"

_IMAGE_SUFFIXES = frozenset(IMAGE_FILE_SUFFIXES)
_PDF_RENDER_SIZE = QSize(1600, 1200)
_EXTERNAL_FILE_PROPERTY_NAMES = frozenset({"source_path", "path", "file_path", "input_path", "output_path"})


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckOptions:
    project_path: str | Path | None = None
    registry: Any | None = None
    run_state: Any | None = None


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckWriterOptions:
    output_path: Path
    slide_size: str = "16:9 landscape"
    template_path: Path | None = None
    selected_slide_ids: tuple[str, ...] = ()
    crop_canvas_snapshots: bool = True


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckSlide:
    slide_id: str
    kind: str
    title: str
    subtitle: str = ""
    checked: bool = True
    canvas_capture_mode: str = ""
    workspace_id: str = ""
    workspace_name: str = ""
    view_id: str = ""
    view_name: str = ""
    node_id: str = ""
    node_title: str = ""
    node_type: str = ""
    artifact_id: str = ""
    artifact_ref: str = ""
    source_path: Path | None = None
    source_value: str = ""
    image_value: ImageValue | None = None
    page_number: int | None = None
    page_count: int = 0
    detail_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckSection:
    section_id: str
    title: str
    slides: tuple[ProjectReviewDeckSlide, ...]
    checked: bool = True


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckPlan:
    project_name: str
    project_path: str
    sections: tuple[ProjectReviewDeckSection, ...]
    warnings: tuple[str, ...] = ()

    @property
    def slide_count(self) -> int:
        return sum(len(section.slides) for section in self.sections)


@dataclass(frozen=True, slots=True)
class ProjectReviewDeckMaterialization:
    slides: tuple[ProjectReviewPptxSlide, ...]
    warnings: tuple[str, ...] = ()


def iter_project_review_slides(plan: ProjectReviewDeckPlan) -> Iterable[ProjectReviewDeckSlide]:
    for section in plan.sections:
        yield from section.slides


def selected_project_review_slides(
    plan: ProjectReviewDeckPlan,
    selected_slide_ids: Iterable[str],
) -> tuple[ProjectReviewDeckSlide, ...]:
    order = [str(slide_id or "").strip() for slide_id in selected_slide_ids]
    selected = {slide_id for slide_id in order if slide_id}
    slides_by_id = {slide.slide_id: slide for slide in iter_project_review_slides(plan)}
    if not selected:
        return tuple(slide for slide in iter_project_review_slides(plan) if slide.checked)
    return tuple(
        slides_by_id[slide_id]
        for slide_id in order
        if slide_id in selected and slide_id in slides_by_id
    )


def default_project_review_deck_path(project_path: str | Path | None, project_name: object) -> Path:
    if project_path:
        path = Path(project_path).expanduser()
        stem = safe_filename_component(f"{path.stem}-review-deck", fallback="project-review-deck")
        return path.with_name(f"{stem}.pptx")
    stem = safe_filename_component(f"{project_name}-review-deck", fallback="project-review-deck")
    return Path.cwd() / f"{stem}.pptx"


def build_project_review_deck_plan(
    *,
    project: ProjectData,
    project_path: str | Path | None = None,
    registry: Any | None = None,
    run_state: Any | None = None,
    options: ProjectReviewDeckOptions | None = None,
) -> ProjectReviewDeckPlan:
    if options is not None:
        if project_path is None:
            project_path = options.project_path
        if registry is None:
            registry = options.registry
        if run_state is None:
            run_state = options.run_state
    project_label = _project_label(project=project, project_path=project_path)
    metadata = project.metadata if isinstance(project.metadata, dict) else {}
    artifact_store = ProjectArtifactStore.from_project_metadata(
        project_path=project_path,
        project_metadata=metadata,
    )
    sections: list[ProjectReviewDeckSection] = []
    warnings: list[str] = []

    sections.append(
        ProjectReviewDeckSection(
            section_id="summary",
            title="Summary",
            slides=(
                ProjectReviewDeckSlide(
                    slide_id="summary:title",
                    kind=PROJECT_REVIEW_SLIDE_TITLE,
                    title=project_label,
                    subtitle="Project review deck",
                    detail_lines=(
                        f"Workspaces: {len(project.workspaces)}",
                        "Generated from the open COREX project.",
                    ),
                ),
            ),
        )
    )

    snapshot_slides, view_slides = _workspace_canvas_slides(project)
    if snapshot_slides:
        sections.append(
            ProjectReviewDeckSection(
                section_id="workspace-snapshots",
                title="Workspace Snapshots",
                slides=tuple(snapshot_slides),
            )
        )
    if view_slides:
        sections.append(
            ProjectReviewDeckSection(
                section_id="workspace-views",
                title="Workspace Views",
                slides=tuple(view_slides),
            )
        )

    evidence_slides, evidence_warnings = _artifact_evidence_slides(
        project=project,
        artifact_store=artifact_store,
        registry=registry,
        project_path=project_path,
        run_state=run_state,
    )
    warnings.extend(evidence_warnings)
    if evidence_slides:
        sections.append(
            ProjectReviewDeckSection(
                section_id="evidence",
                title="Evidence",
                slides=tuple(evidence_slides),
            )
        )
    if warnings:
        sections.append(
            ProjectReviewDeckSection(
                section_id="issues",
                title="Issues",
                slides=(
                    ProjectReviewDeckSlide(
                        slide_id="issues:summary",
                        kind=PROJECT_REVIEW_SLIDE_ISSUE,
                        title="Project Files To Review",
                        subtitle="Missing, temporary, or unsupported evidence",
                        detail_lines=tuple(warnings),
                    ),
                ),
            )
        )

    return ProjectReviewDeckPlan(
        project_name=project_label,
        project_path=str(project_path or ""),
        sections=tuple(sections),
        warnings=tuple(warnings),
    )


def materialize_project_review_pptx_slides(
    *,
    slides: Iterable[ProjectReviewDeckSlide],
    canvas_images_by_slide_id: Mapping[str, Path] | None,
    temp_dir: Path | str,
) -> ProjectReviewDeckMaterialization:
    temp_root = Path(temp_dir)
    temp_root.mkdir(parents=True, exist_ok=True)
    canvas_images = dict(canvas_images_by_slide_id or {})
    materialized: list[ProjectReviewPptxSlide] = []
    warnings: list[str] = []

    for slide in slides:
        if slide.kind == PROJECT_REVIEW_SLIDE_TITLE:
            materialized.append(
                ProjectReviewPptxSlide(
                    title=slide.title,
                    subtitle=slide.subtitle,
                    body_lines=slide.detail_lines,
                )
            )
            continue
        if slide.kind == PROJECT_REVIEW_SLIDE_CANVAS:
            image_path = canvas_images.get(slide.slide_id)
            if image_path is not None and image_path.exists():
                materialized.append(_pptx_slide_from_plan(slide, image_path=image_path))
            else:
                warnings.append(f"Canvas snapshot was not available: {slide.title}")
                materialized.append(_issue_pptx_slide(slide, "Canvas snapshot was not available."))
            continue
        if slide.kind == PROJECT_REVIEW_SLIDE_IMAGE:
            image_path = (
                _materialize_image_value(slide.image_value, slide.title, temp_root)
                if slide.image_value is not None
                else slide.source_path
            )
            if image_path is not None and _image_loads(image_path):
                materialized.append(_pptx_slide_from_plan(slide, image_path=image_path))
            else:
                warnings.append(f"Image artifact could not be read: {slide.title}")
                materialized.append(_issue_pptx_slide(slide, "Image artifact could not be read."))
            continue
        if slide.kind == PROJECT_REVIEW_SLIDE_PDF:
            rendered_path = _render_pdf_slide_image(slide, temp_root)
            if rendered_path is not None:
                footer = f"PDF page {slide.page_number or 1}"
                if slide.page_count:
                    footer = f"{footer} of {slide.page_count}"
                materialized.append(_pptx_slide_from_plan(slide, image_path=rendered_path, footer=footer))
            else:
                warnings.append(f"PDF page could not be rendered: {slide.title}")
                materialized.append(_issue_pptx_slide(slide, "PDF page could not be rendered."))
            continue
        materialized.append(
            ProjectReviewPptxSlide(
                title=slide.title,
                subtitle=slide.subtitle,
                body_lines=slide.detail_lines or ("No details available.",),
            )
        )

    return ProjectReviewDeckMaterialization(
        slides=tuple(materialized),
        warnings=tuple(warnings),
    )


def _project_label(*, project: ProjectData, project_path: str | Path | None) -> str:
    name = str(project.name or "").strip()
    if name:
        return name
    if project_path:
        return Path(project_path).stem
    return "Untitled Project"


def _workspace_canvas_slides(project: ProjectData) -> tuple[list[ProjectReviewDeckSlide], list[ProjectReviewDeckSlide]]:
    snapshot_slides: list[ProjectReviewDeckSlide] = []
    view_slides: list[ProjectReviewDeckSlide] = []
    for workspace in project.workspaces.values():
        workspace.ensure_default_view()
        workspace_name = str(workspace.name or workspace.workspace_id)
        workspace_id = str(workspace.workspace_id)
        snapshot_slides.append(
            ProjectReviewDeckSlide(
                slide_id=f"canvas:snapshot:{workspace_id}",
                kind=PROJECT_REVIEW_SLIDE_CANVAS,
                title=f"{workspace_name} - Snapshot",
                subtitle="Workspace canvas snapshot",
                canvas_capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT,
                workspace_id=workspace_id,
                workspace_name=workspace_name,
            )
        )
        for view in workspace.views.values():
            view_name = str(view.name or view.view_id)
            view_slides.append(
                ProjectReviewDeckSlide(
                    slide_id=f"canvas:view:{workspace_id}:{view.view_id}",
                    kind=PROJECT_REVIEW_SLIDE_CANVAS,
                    title=f"{workspace_name} - {view_name}",
                    subtitle="Workspace saved view",
                    canvas_capture_mode=PROJECT_REVIEW_CANVAS_CAPTURE_VIEW,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    view_id=str(view.view_id),
                    view_name=view_name,
                )
            )
    return snapshot_slides, view_slides


def _artifact_evidence_slides(
    *,
    project: ProjectData,
    artifact_store: ProjectArtifactStore,
    registry: Any | None,
    project_path: str | Path | None,
    run_state: Any | None,
) -> tuple[list[ProjectReviewDeckSlide], list[str]]:
    slides: list[ProjectReviewDeckSlide] = []
    warnings: list[str] = []
    seen_artifact_refs: set[str] = set()

    for workspace in project.workspaces.values():
        workspace_name = str(workspace.name or workspace.workspace_id)
        for node in workspace.nodes.values():
            node_type_label = _node_type_label(registry, node)
            if str(node.type_id) == MEDIA_PANEL_TYPE_ID:
                _append_media_panel_evidence(
                    slides=slides,
                    warnings=warnings,
                    seen_artifact_refs=seen_artifact_refs,
                    workspace=workspace,
                    node=node,
                    node_type_label=node_type_label,
                    artifact_store=artifact_store,
                    project=project,
                    project_path=project_path,
                    run_state=run_state,
                )
                continue
            for artifact_ref in _node_artifact_refs(node):
                artifact_id = artifact_ref.artifact_id
                artifact_ref_key = artifact_ref.as_string()
                if artifact_ref_key in seen_artifact_refs:
                    continue
                seen_artifact_refs.add(artifact_ref_key)
                if isinstance(artifact_ref, ManagedArtifactRef):
                    entry = artifact_store.state.artifacts.get(artifact_id)
                else:
                    entry = artifact_store.state.staged.get(artifact_id)
                resolved_path = (
                    artifact_store.resolve_managed_path(artifact_id)
                    if isinstance(artifact_ref, ManagedArtifactRef)
                    else artifact_store.resolve_staged_path(artifact_id)
                )
                artifact_label = _artifact_title(
                    workspace_name=workspace_name,
                    node=node,
                    node_type=node_type_label,
                    path=resolved_path,
                )
                if entry is None:
                    warnings.append(f"{artifact_label}: referenced artifact metadata is missing.")
                    continue
                if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
                    warnings.append(f"{artifact_label}: referenced file is missing.")
                    continue
                suffix = resolved_path.suffix.lower()
                if suffix in _IMAGE_SUFFIXES:
                    slides.append(
                        ProjectReviewDeckSlide(
                            slide_id=_artifact_slide_id(artifact_ref),
                            kind=PROJECT_REVIEW_SLIDE_IMAGE,
                            title=artifact_label,
                            subtitle="Image evidence",
                            workspace_id=str(workspace.workspace_id),
                            workspace_name=workspace_name,
                            node_id=str(node.node_id),
                            node_title=str(node.title),
                            node_type=node_type_label,
                            artifact_id=artifact_id,
                            artifact_ref=artifact_ref.as_string(),
                            source_path=resolved_path,
                            source_value=artifact_ref.as_string(),
                            detail_lines=_artifact_details(
                                resolved_path=resolved_path,
                                entry_extra=getattr(entry, "extra", {}),
                            ),
                        )
                    )
                    if isinstance(artifact_ref, StagedArtifactRef):
                        warnings.append(
                            f"{artifact_label}: uses a temporary project file; "
                            "save the project to promote it."
                        )
                    continue
                if suffix == ".pdf":
                    page_number = _pdf_panel_page_number(node)
                    info = describe_pdf_preview(str(resolved_path), page_number)
                    resolved_page = _int_value(info.get("resolved_page_number"), page_number)
                    page_count = _int_value(info.get("page_count"), 0)
                    slides.append(
                        ProjectReviewDeckSlide(
                            slide_id=_artifact_slide_id(artifact_ref),
                            kind=PROJECT_REVIEW_SLIDE_PDF,
                            title=artifact_label,
                            subtitle="PDF evidence",
                            workspace_id=str(workspace.workspace_id),
                            workspace_name=workspace_name,
                            node_id=str(node.node_id),
                            node_title=str(node.title),
                            node_type=node_type_label,
                            artifact_id=artifact_id,
                            artifact_ref=artifact_ref.as_string(),
                            source_path=resolved_path,
                            source_value=artifact_ref.as_string(),
                            page_number=max(1, resolved_page),
                            page_count=max(0, page_count),
                            detail_lines=_artifact_details(
                                resolved_path=resolved_path,
                                entry_extra=getattr(entry, "extra", {}),
                            ),
                        )
                    )
                    if isinstance(artifact_ref, StagedArtifactRef):
                        warnings.append(
                            f"{artifact_label}: uses a temporary project file; "
                            "save the project to promote it."
                        )
                    continue
                warnings.append(f"{artifact_label}: unsupported evidence file type '{suffix or '(none)'}'.")
            for external_source in _node_external_file_sources(node):
                external_path = Path(external_source).expanduser()
                artifact_label = _artifact_title(
                    workspace_name=workspace_name,
                    node=node,
                    node_type=node_type_label,
                    path=external_path,
                )
                warnings.append(
                    f"{artifact_label}: external file paths are listed but not embedded "
                    "in Project Review Deck v1."
                )

    return slides, warnings


def _append_media_panel_evidence(
    *,
    slides: list[ProjectReviewDeckSlide],
    warnings: list[str],
    seen_artifact_refs: set[str],
    workspace: Any,
    node: NodeInstance,
    node_type_label: str,
    artifact_store: ProjectArtifactStore,
    project: ProjectData,
    project_path: str | Path | None,
    run_state: Any | None,
) -> None:
    workspace_name = str(workspace.name or workspace.workspace_id)
    node_label = _artifact_title(
        workspace_name=workspace_name,
        node=node,
        node_type=node_type_label,
        path=None,
    )
    try:
        resolution = resolve_media_panel_source(
            node=node,
            workspace=workspace,
            run_state=run_state,
            project_path=project_path,
            project_metadata=(
                dict(project.metadata)
                if isinstance(project.metadata, Mapping)
                else None
            ),
        )
    except (OSError, TypeError, ValueError):
        warnings.append(f"{node_label}: Media Panel source could not be resolved.")
        return
    if resolution.state != "ready":
        detail = str(resolution.message or "").strip()
        warnings.append(
            f"{node_label}: Media Panel source is {resolution.state}."
            + (f" {detail}" if detail else "")
        )
        return
    if type(resolution.raw_value) is ImageValue:
        slides.append(
            ProjectReviewDeckSlide(
                slide_id=f"media:{workspace.workspace_id}:{node.node_id}:image-value",
                kind=PROJECT_REVIEW_SLIDE_IMAGE,
                title=str(node.title or node_type_label),
                subtitle="Image evidence",
                workspace_id=str(workspace.workspace_id),
                workspace_name=workspace_name,
                node_id=str(node.node_id),
                node_title=str(node.title),
                node_type=node_type_label,
                image_value=resolution.raw_value,
                detail_lines=(
                    f"Runtime Image: {resolution.raw_value.width} x {resolution.raw_value.height}",
                ),
            )
        )
        return
    if resolution.media_kind not in {"image", "pdf"}:
        warnings.append(
            f"{node_label}: effective {resolution.media_kind or 'media'} source is not supported as deck evidence."
        )
        return

    source_url = QUrl(str(resolution.resolved_source_url or ""))
    source_path = Path(source_url.toLocalFile()) if source_url.isLocalFile() else None
    if source_path is None or not source_path.exists() or not source_path.is_file():
        warnings.append(
            f"{node_label}: effective source is not a ready local file and cannot be embedded."
        )
        return

    artifact_ref = parse_artifact_ref(resolution.source_ref)
    artifact_key = artifact_ref.as_string() if artifact_ref is not None else ""
    if artifact_key and artifact_key in seen_artifact_refs:
        return
    if artifact_key:
        seen_artifact_refs.add(artifact_key)
    artifact_id = artifact_ref.artifact_id if artifact_ref is not None else ""
    entry = None
    if isinstance(artifact_ref, ManagedArtifactRef):
        entry = artifact_store.state.artifacts.get(artifact_id)
    elif isinstance(artifact_ref, StagedArtifactRef):
        entry = artifact_store.state.staged.get(artifact_id)
    artifact_label = _artifact_title(
        workspace_name=workspace_name,
        node=node,
        node_type=node_type_label,
        path=source_path,
    )
    slide_id = (
        _artifact_slide_id(artifact_ref)
        if artifact_ref is not None
        else f"media:{workspace.workspace_id}:{node.node_id}:{resolution.media_kind}"
    )
    detail_lines = _artifact_details(
        resolved_path=source_path,
        entry_extra=getattr(entry, "extra", {}),
    )
    if resolution.media_kind == "image":
        slides.append(
            ProjectReviewDeckSlide(
                slide_id=slide_id,
                kind=PROJECT_REVIEW_SLIDE_IMAGE,
                title=artifact_label,
                subtitle="Image evidence",
                workspace_id=str(workspace.workspace_id),
                workspace_name=workspace_name,
                node_id=str(node.node_id),
                node_title=str(node.title),
                node_type=node_type_label,
                artifact_id=artifact_id,
                artifact_ref=artifact_key,
                source_path=source_path,
                source_value=resolution.source_ref,
                detail_lines=detail_lines,
            )
        )
    else:
        page_number = _pdf_panel_page_number(node)
        info = describe_pdf_preview(str(source_path), page_number)
        resolved_page = _int_value(info.get("resolved_page_number"), page_number)
        slides.append(
            ProjectReviewDeckSlide(
                slide_id=slide_id,
                kind=PROJECT_REVIEW_SLIDE_PDF,
                title=artifact_label,
                subtitle="PDF evidence",
                workspace_id=str(workspace.workspace_id),
                workspace_name=workspace_name,
                node_id=str(node.node_id),
                node_title=str(node.title),
                node_type=node_type_label,
                artifact_id=artifact_id,
                artifact_ref=artifact_key,
                source_path=source_path,
                source_value=resolution.source_ref,
                page_number=max(1, resolved_page),
                page_count=max(0, _int_value(info.get("page_count"), 0)),
                detail_lines=detail_lines,
            )
        )
    if isinstance(artifact_ref, StagedArtifactRef):
        warnings.append(
            f"{artifact_label}: uses a temporary project file; save the project to promote it."
        )


def _artifact_slide_id(artifact_ref: ManagedArtifactRef | StagedArtifactRef) -> str:
    scheme = "saved" if isinstance(artifact_ref, ManagedArtifactRef) else "temp"
    return f"artifact:{scheme}:{artifact_ref.artifact_id}"


def _node_artifact_refs(node: NodeInstance) -> tuple[ManagedArtifactRef | StagedArtifactRef, ...]:
    refs: list[ManagedArtifactRef | StagedArtifactRef] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            parsed = parse_artifact_ref(value)
            if parsed is None:
                return
            key = parsed.as_string()
            if key not in seen:
                seen.add(key)
                refs.append(parsed)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, list | tuple | set | frozenset):
            for item in value:
                visit(item)

    visit(node.properties)
    return tuple(refs)


def _node_external_file_sources(node: NodeInstance) -> tuple[str, ...]:
    sources: list[str] = []
    seen: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, str):
            text = value.strip()
            if not text or parse_artifact_ref(text) is not None:
                return
            if "://" in text and not text.lower().startswith("file://"):
                return
            if key not in _EXTERNAL_FILE_PROPERTY_NAMES:
                return
            if text not in seen:
                seen.add(text)
                sources.append(text)
            return
        if isinstance(value, Mapping):
            for item_key, item in value.items():
                visit(item, str(item_key))
            return
        if isinstance(value, list | tuple | set | frozenset):
            for item in value:
                visit(item, key)

    visit(node.properties)
    return tuple(sources)


def _node_type_label(registry: Any | None, node: NodeInstance) -> str:
    if registry is not None:
        try:
            spec = registry.get_spec(node.type_id)
            display_name = str(getattr(spec, "display_name", "") or "").strip()
            if display_name:
                return display_name
        except (AttributeError, KeyError, TypeError):
            pass
    return str(node.type_id or "Node")


def _artifact_title(
    *,
    workspace_name: str,
    node: NodeInstance,
    node_type: str,
    path: Path | None,
) -> str:
    node_label = str(node.title or node_type or node.node_id)
    file_label = path.name if path is not None else "artifact"
    return f"{workspace_name} / {node_label} / {file_label}"


def _artifact_details(*, resolved_path: Path, entry_extra: Mapping[str, Any]) -> tuple[str, ...]:
    details = [f"File: {resolved_path.name}"]
    io_dir = str(entry_extra.get("io_dir", "") or "").strip()
    artifact_kind = str(entry_extra.get("artifact_kind", "") or "").strip()
    if io_dir:
        details.append(f"Project folder: {io_dir}")
    if artifact_kind:
        details.append(f"Kind: {artifact_kind}")
    return tuple(details)


def _pdf_panel_page_number(node: NodeInstance) -> int:
    if node.type_id != MEDIA_PANEL_TYPE_ID:
        return 1
    return _int_value(node.properties.get("page_number"), 1)


def _int_value(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _image_loads(path: Path) -> bool:
    image = QImage(str(path))
    return not image.isNull() and image.width() > 0 and image.height() > 0


def _materialize_image_value(
    value: ImageValue,
    title: str,
    temp_root: Path,
) -> Path | None:
    image = QImage.fromData(value.encoded_bytes, "PNG")
    if image.isNull() or image.width() != value.width or image.height() != value.height:
        return None
    output_path = collision_safe_path(
        temp_root,
        safe_filename_component(title, fallback="runtime-image"),
        ".png",
    )
    return output_path if image.save(str(output_path), "PNG") else None


def _render_pdf_slide_image(slide: ProjectReviewDeckSlide, temp_root: Path) -> Path | None:
    source = str(slide.source_path or slide.source_value or "").strip()
    if not source:
        return None
    image, info = render_pdf_page_image(source, slide.page_number or 1, _PDF_RENDER_SIZE)
    if str(info.get("state", "")) != "ready" or image.isNull():
        return None
    stem = safe_filename_component(f"{slide.title}-page-{info.get('resolved_page_number', 1)}", fallback="pdf-page")
    output_path = collision_safe_path(temp_root, stem, ".png")
    if not image.save(str(output_path), "PNG"):
        return None
    return output_path


def _pptx_slide_from_plan(
    slide: ProjectReviewDeckSlide,
    *,
    image_path: Path,
    footer: str = "",
) -> ProjectReviewPptxSlide:
    return ProjectReviewPptxSlide(
        title=slide.title,
        subtitle=slide.subtitle,
        image_path=image_path,
        body_lines=slide.detail_lines,
        footer=footer,
    )


def _issue_pptx_slide(slide: ProjectReviewDeckSlide, message: str) -> ProjectReviewPptxSlide:
    return ProjectReviewPptxSlide(
        title=slide.title,
        subtitle=slide.subtitle or "Export issue",
        body_lines=(message, *slide.detail_lines),
    )


def with_slide_checked(slide: ProjectReviewDeckSlide, checked: bool) -> ProjectReviewDeckSlide:
    return replace(slide, checked=bool(checked))


__all__ = [
    "PROJECT_REVIEW_CANVAS_CAPTURE_SNAPSHOT",
    "PROJECT_REVIEW_CANVAS_CAPTURE_VIEW",
    "PROJECT_REVIEW_SLIDE_CANVAS",
    "PROJECT_REVIEW_SLIDE_IMAGE",
    "PROJECT_REVIEW_SLIDE_ISSUE",
    "PROJECT_REVIEW_SLIDE_PDF",
    "PROJECT_REVIEW_SLIDE_TITLE",
    "ProjectReviewDeckMaterialization",
    "ProjectReviewDeckOptions",
    "ProjectReviewDeckPlan",
    "ProjectReviewDeckSection",
    "ProjectReviewDeckSlide",
    "ProjectReviewDeckWriterOptions",
    "build_project_review_deck_plan",
    "default_project_review_deck_path",
    "iter_project_review_slides",
    "materialize_project_review_pptx_slides",
    "selected_project_review_slides",
    "with_slide_checked",
]
