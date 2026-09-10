from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage
from PyQt6.QtQuick import QQuickImageProvider

PLOT_PREVIEW_CACHE_PROVIDER_ID = "plot-preview-cache"
VIEWER_PREVIEW_CACHE_PROVIDER_ID = "viewer-preview-cache"

_CacheKey = tuple[str, str]


def _string(value: Any) -> str:
    return str(value or "").strip()


def _cache_key(workspace_id: str, node_id: str) -> _CacheKey | None:
    normalized_workspace_id = _string(workspace_id)
    normalized_node_id = _string(node_id)
    if not normalized_workspace_id or not normalized_node_id:
        return None
    return normalized_workspace_id, normalized_node_id


def _requested_key(image_id: str) -> _CacheKey | None:
    _path, _separator, query = str(image_id or "").partition("?")
    if not query:
        return None
    parsed = parse_qs(query, keep_blank_values=False)
    workspace_values = parsed.get("workspace")
    node_values = parsed.get("node")
    if not workspace_values or not node_values:
        return None
    return _cache_key(workspace_values[-1], node_values[-1])


class _PreviewCacheImageProvider(QQuickImageProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._provider_id = provider_id
        self._images: dict[_CacheKey, QImage] = {}
        self._signatures: dict[_CacheKey, object] = {}
        self._revisions: dict[_CacheKey, int] = {}

    def set_preview(
        self,
        workspace_id: str,
        node_id: str,
        image: QImage,
        *,
        signature: object,
    ) -> bool:
        key = _cache_key(workspace_id, node_id)
        if key is None or image.isNull():
            return False
        self._images[key] = image.copy()
        self._signatures[key] = signature
        self._revisions[key] = self._revisions.get(key, 0) + 1
        return True

    def clear_preview(self, workspace_id: str, node_id: str) -> bool:
        key = _cache_key(workspace_id, node_id)
        if key is None:
            return False
        existed = key in self._images or key in self._signatures
        self._images.pop(key, None)
        self._signatures.pop(key, None)
        if existed:
            self._revisions[key] = self._revisions.get(key, 0) + 1
        return existed

    def clear_all(self) -> bool:
        if not self._images and not self._signatures:
            return False
        keys = set(self._images) | set(self._signatures)
        self._images.clear()
        self._signatures.clear()
        for key in keys:
            self._revisions[key] = self._revisions.get(key, 0) + 1
        return True

    def preview_signature(self, workspace_id: str, node_id: str) -> object | None:
        key = _cache_key(workspace_id, node_id)
        return self._signatures.get(key) if key is not None else None

    def has_preview(self, workspace_id: str, node_id: str) -> bool:
        key = _cache_key(workspace_id, node_id)
        return key in self._images if key is not None else False

    def preview_source(self, workspace_id: str, node_id: str) -> str:
        key = _cache_key(workspace_id, node_id)
        if key is None or key not in self._images:
            return ""
        workspace, node = key
        revision = self._revisions.get(key, 0)
        query = (
            f"workspace={quote(workspace, safe='')}"
            f"&node={quote(node, safe='')}"
            f"&revision={revision}"
        )
        return f"image://{self._provider_id}/preview?{query}"

    def requestImage(self, image_id: str, requested_size: QSize) -> tuple[QImage, QSize]:  # type: ignore[override]
        del requested_size
        key = _requested_key(image_id)
        if key is None:
            return QImage(), QSize()
        image = self._images.get(key)
        if image is None or image.isNull():
            return QImage(), QSize()
        copied = image.copy()
        return copied, copied.size()


class PlotPreviewCacheImageProvider(_PreviewCacheImageProvider):
    def __init__(self) -> None:
        super().__init__(PLOT_PREVIEW_CACHE_PROVIDER_ID)


class ViewerPreviewCacheImageProvider(_PreviewCacheImageProvider):
    def __init__(self) -> None:
        super().__init__(VIEWER_PREVIEW_CACHE_PROVIDER_ID)


__all__ = [
    "PLOT_PREVIEW_CACHE_PROVIDER_ID",
    "PlotPreviewCacheImageProvider",
    "VIEWER_PREVIEW_CACHE_PROVIDER_ID",
    "ViewerPreviewCacheImageProvider",
]
