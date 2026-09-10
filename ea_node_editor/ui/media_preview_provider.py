from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote

from PyQt6.QtCore import QSize, QUrl
from PyQt6.QtGui import QImage, QImageReader
from PyQt6.QtQuick import QQuickImageProvider

from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver

LOCAL_MEDIA_PREVIEW_PROVIDER_ID = "local-media-preview"
_PreviewProjectContext = tuple[str | Path | None, dict[str, Any] | None]
_PreviewProjectContextProvider = Callable[[], _PreviewProjectContext | None]
_project_context_provider: _PreviewProjectContextProvider | None = None


def set_media_preview_project_context_provider(
    provider: _PreviewProjectContextProvider | None,
) -> None:
    global _project_context_provider
    _project_context_provider = provider


def _preview_resolver() -> ProjectArtifactResolver:
    context = _project_context_provider() if callable(_project_context_provider) else None
    project_path: str | Path | None = None
    project_metadata: dict[str, Any] | None = None
    if isinstance(context, tuple) and len(context) >= 2:
        project_path = context[0]
        metadata = context[1]
        if isinstance(metadata, dict):
            project_metadata = metadata
    return ProjectArtifactResolver(
        project_path=project_path,
        project_metadata=project_metadata,
    )


def _local_path_from_source(source: str) -> Path | None:
    normalized = str(source or "").strip()
    if not normalized:
        return None
    return _preview_resolver().resolve_to_path(normalized)


def _local_file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _requested_source(image_id: str) -> str:
    _path, _separator, query = str(image_id or "").partition("?")
    if not query:
        return ""
    parsed = parse_qs(query, keep_blank_values=False)
    values = parsed.get("source")
    if not values:
        return ""
    return unquote(values[-1])


def _local_image_reader(path: Path) -> QImageReader:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    return reader


def _read_local_image(path: Path) -> QImage:
    return _local_image_reader(path).read()


def _local_image_description_payload(
    *,
    state: str,
    message: str,
    resolved_source_url: str = "",
    format_name: str = "",
    source_pixel_width: int = 0,
    source_pixel_height: int = 0,
    frame_count: int = 0,
    animation_supported: bool = False,
    is_animated: bool = False,
) -> dict[str, Any]:
    return {
        "state": str(state or "error"),
        "message": str(message or ""),
        "resolved_source_url": str(resolved_source_url or ""),
        "format": str(format_name or ""),
        "source_pixel_width": max(0, int(source_pixel_width)),
        "source_pixel_height": max(0, int(source_pixel_height)),
        "frame_count": max(0, int(frame_count)),
        "animation_supported": bool(animation_supported),
        "is_animated": bool(is_animated),
    }


@lru_cache(maxsize=256)
def _cached_local_image_description(
    path_text: str,
    modified_ns: int,
    file_size: int,
) -> tuple[str, str, str, int, int, int, bool, bool]:
    del modified_ns
    del file_size
    reader = _local_image_reader(Path(path_text))
    format_name = bytes(reader.format()).decode("ascii", errors="ignore").strip().lower()
    image = reader.read()
    if image.isNull():
        message = str(reader.errorString() or "").strip() or "The selected image could not be decoded."
        return "error", message, format_name, 0, 0, 0, False, False

    try:
        frame_count = max(1, int(reader.imageCount()))
    except (TypeError, ValueError):
        frame_count = 1
    animation_supported = bool(reader.supportsAnimation())
    is_animated = bool(animation_supported and frame_count > 1)
    return (
        "ready",
        "",
        format_name,
        int(image.width()),
        int(image.height()),
        frame_count,
        animation_supported,
        is_animated,
    )


def describe_local_image(source: str) -> dict[str, Any]:
    normalized_source = str(source or "").strip()
    if not normalized_source:
        return _local_image_description_payload(state="placeholder", message="")

    path = _local_path_from_source(normalized_source)
    if path is None:
        return _local_image_description_payload(
            state="error",
            message="The selected image source could not be resolved.",
        )

    resolved_source_url = _local_file_url(path)
    if not path.exists() or not path.is_file():
        return _local_image_description_payload(
            state="error",
            message="The selected image source file could not be found.",
            resolved_source_url=resolved_source_url,
        )

    try:
        stats = path.stat()
    except OSError:
        return _local_image_description_payload(
            state="error",
            message="The selected image source file could not be inspected.",
            resolved_source_url=resolved_source_url,
        )

    state, message, format_name, width, height, frame_count, animation_supported, is_animated = (
        _cached_local_image_description(
            str(path),
            int(stats.st_mtime_ns),
            int(stats.st_size),
        )
    )
    return _local_image_description_payload(
        state=state,
        message=message,
        resolved_source_url=resolved_source_url,
        format_name=format_name,
        source_pixel_width=width,
        source_pixel_height=height,
        frame_count=frame_count,
        animation_supported=animation_supported,
        is_animated=is_animated,
    )


def local_image_dimensions(source: str) -> tuple[int, int] | None:
    description = describe_local_image(source)
    if description.get("state") != "ready":
        return None
    width = int(description.get("source_pixel_width", 0) or 0)
    height = int(description.get("source_pixel_height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    return width, height


class LocalMediaPreviewImageProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, image_id: str, requested_size: QSize) -> tuple[QImage, QSize]:  # type: ignore[override]
        source = _requested_source(image_id)
        path = _local_path_from_source(source)
        if path is None or not path.exists() or not path.is_file():
            return QImage(), QSize()

        image = _read_local_image(path)
        if image.isNull():
            return QImage(), QSize()

        return image, image.size()


__all__ = [
    "LOCAL_MEDIA_PREVIEW_PROVIDER_ID",
    "LocalMediaPreviewImageProvider",
    "describe_local_image",
    "local_image_dimensions",
    "set_media_preview_project_context_provider",
]
